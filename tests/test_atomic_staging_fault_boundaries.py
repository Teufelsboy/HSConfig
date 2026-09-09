from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import stat

import pytest

from hsconfig import atomic_io, runtime_installer
from hsconfig.atomic_io import (
    NO_REPLACE_COMMIT_FAULT_POINT,
    NO_REPLACE_POSIX_LINK_FAULT_POINT,
    STAGING_MATERIALIZE_FAULT_POINT,
    atomic_materialize_staging_bytes,
)
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.package_io import path_identity


_INNER_TEMP_STAGES = (
    "inner_temp_created",
    "inner_temp_partial",
    "inner_temp_full",
    "inner_temp_flushed",
)


class _InjectedStagingFault(RuntimeError):
    pass


@pytest.mark.parametrize("surface", ("initial", "rewrite", "retention", "ini"))
def test_journal_materialization_selector_uses_planned_journal_binding(
    tmp_path: Path, surface: str
) -> None:
    journal_path = str(tmp_path / "transactions" / ("a" * 32 + ".json"))
    final_path = {
        "initial": journal_path,
        "rewrite": journal_path,
        "retention": str(tmp_path / "attempt-retention" / ("a" * 32 + ".json")),
        "ini": str(tmp_path / "CustomConfig" / "deck_config.ini"),
    }[surface]
    external = {
        "action_kind": "materialize_file_action_staging",
        "stage": "PLANNED",
        "final_path": final_path,
    }
    cursor = {
        "external_file_action": external,
        "planned_journal_successor_path": journal_path,
        "successor_journal_path": None if surface == "initial" else journal_path,
    }
    selected = runtime_installer._controller_transaction_external_action(cursor)
    if surface in {"initial", "rewrite"}:
        assert selected is external
    else:
        assert selected is None


def _assert_plain_owned_file(path: Path) -> tuple[int, int, int]:
    status = path.lstat()
    assert stat.S_ISREG(status.st_mode)
    assert status.st_nlink == 1
    assert not path.is_symlink()
    return path_identity(path)


@pytest.mark.parametrize(
    "payload",
    (b"", b"x", b"xy", b'{"authority":"inner-boundaries"}\n'),
    ids=("empty", "one-byte", "two-bytes", "journal"),
)
def test_atomic_materialize_reports_inner_temp_boundaries_before_staging_commit(
    tmp_path: Path,
    payload: bytes,
) -> None:
    final = tmp_path / "authority.json"
    staging = tmp_path / "authority.json.staged"
    inner = tmp_path / ".authority.json.staged.live-start-atomic.tmp"
    observed: list[str] = []
    inner_identity: tuple[int, int, int] | None = None

    def observe(stage: str) -> None:
        nonlocal inner_identity
        if stage in _INNER_TEMP_STAGES:
            assert not final.exists()
            assert not staging.exists()
            current_identity = _assert_plain_owned_file(inner)
            if inner_identity is None:
                inner_identity = current_identity
            assert current_identity == inner_identity
            if stage == "inner_temp_created":
                assert inner.stat().st_size == 0
            elif stage == "inner_temp_flushed":
                assert inner.read_bytes() == payload
                assert inner.stat().st_size == len(payload)
            observed.append(stage)
            return
        assert stage == STAGING_MATERIALIZE_FAULT_POINT
        assert observed == list(_INNER_TEMP_STAGES)
        assert not final.exists()
        assert not inner.exists()
        assert staging.read_bytes() == payload
        assert path_identity(staging) == inner_identity
        observed.append(stage)

    materialized = atomic_materialize_staging_bytes(
        staging_path=staging,
        inner_temp_path=inner,
        payload=payload,
        expected_parent_identity=path_identity(tmp_path),
        maximum_size=1024,
        fault_hook=observe,
        inner_temp_fault_hook=observe,
    )

    assert observed == [*_INNER_TEMP_STAGES, STAGING_MATERIALIZE_FAULT_POINT]
    assert materialized.identity == inner_identity == path_identity(staging)
    assert materialized.size == len(payload)
    assert materialized.sha256 == "sha256:" + sha256(payload).hexdigest()


@pytest.mark.parametrize("fault_stage", _INNER_TEMP_STAGES)
def test_atomic_materialize_inner_temp_fault_cleans_owned_residue_and_retries(
    tmp_path: Path,
    fault_stage: str,
) -> None:
    final = tmp_path / "authority.json"
    staging = tmp_path / "authority.json.staged"
    inner = tmp_path / ".authority.json.staged.live-start-atomic.tmp"
    payload = b'{"authority":"retry-after-inner-fault"}\n'
    observed: list[str] = []
    owned_identity: tuple[int, int, int] | None = None

    def interrupt(stage: str) -> None:
        nonlocal owned_identity
        observed.append(stage)
        if stage != fault_stage:
            return
        assert not final.exists()
        assert not staging.exists()
        owned_identity = _assert_plain_owned_file(inner)
        if stage == "inner_temp_created":
            assert inner.stat().st_size == 0
        elif stage == "inner_temp_flushed":
            assert inner.read_bytes() == payload
            assert inner.stat().st_size == len(payload)
        raise _InjectedStagingFault(stage)

    with pytest.raises(_InjectedStagingFault, match=f"^{fault_stage}$"):
        atomic_materialize_staging_bytes(
            staging_path=staging,
            inner_temp_path=inner,
            payload=payload,
            expected_parent_identity=path_identity(tmp_path),
            maximum_size=1024,
            inner_temp_fault_hook=interrupt,
        )

    assert observed == list(
        _INNER_TEMP_STAGES[: _INNER_TEMP_STAGES.index(fault_stage) + 1]
    )
    assert owned_identity is not None
    assert not final.exists()
    assert not staging.exists()
    assert not inner.exists()

    retried = atomic_materialize_staging_bytes(
        staging_path=staging,
        inner_temp_path=inner,
        payload=payload,
        expected_parent_identity=path_identity(tmp_path),
        maximum_size=1024,
    )
    assert not final.exists()
    assert not inner.exists()
    assert staging.read_bytes() == payload
    assert retried.identity == path_identity(staging)
    assert retried.size == len(payload)
    assert retried.sha256 == "sha256:" + sha256(payload).hexdigest()


@pytest.mark.parametrize("short_write_index", (1, 2), ids=("head", "tail"))
def test_atomic_inner_short_write_cleans_owned_residue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    short_write_index: int,
) -> None:
    staging = tmp_path / "authority.json.staged"
    inner = tmp_path / ".authority.json.staged.live-start-atomic.tmp"
    payload = b"abcd"
    real_fdopen = atomic_io.os.fdopen

    class ShortWriter:
        def __init__(self, *args, **kwargs):
            self.handle = real_fdopen(*args, **kwargs)
            self.writes = 0

        def __enter__(self):
            self.handle.__enter__()
            return self

        def __exit__(self, *args):
            return self.handle.__exit__(*args)

        def write(self, content):
            self.writes += 1
            if self.writes == short_write_index:
                return self.handle.write(content[:-1])
            return self.handle.write(content)

        def flush(self):
            self.handle.flush()

    with monkeypatch.context() as patch:
        patch.setattr(atomic_io.os, "fdopen", ShortWriter)
        with pytest.raises(OSError, match="atomic staging short write"):
            atomic_materialize_staging_bytes(
                staging_path=staging,
                inner_temp_path=inner,
                payload=payload,
                expected_parent_identity=path_identity(tmp_path),
                maximum_size=1024,
            )
    assert not staging.exists()
    assert not inner.exists()
    retried = atomic_materialize_staging_bytes(
        staging_path=staging,
        inner_temp_path=inner,
        payload=payload,
        expected_parent_identity=path_identity(tmp_path),
        maximum_size=1024,
    )
    assert staging.read_bytes() == payload
    assert retried.identity == path_identity(staging)


def test_runtime_atomic_fault_adapter_exposes_only_closed_points() -> None:
    received: list[LiveStartFaultPoint] = []
    hook = runtime_installer._runtime_atomic_fault_hook(received.append)
    raw_stages = (
        *_INNER_TEMP_STAGES,
        STAGING_MATERIALIZE_FAULT_POINT,
        NO_REPLACE_POSIX_LINK_FAULT_POINT,
        NO_REPLACE_COMMIT_FAULT_POINT,
    )
    expected = (
        "after_generic_file_inner_temp_created",
        "after_generic_file_inner_temp_partial",
        "after_generic_file_inner_temp_full",
        "after_generic_file_inner_temp_flushed",
        "after_generic_file_staging_flush_before_staging_bound_cas",
        "after_bound_staging_posix_link_before_unlink",
        "after_generic_file_bound_commit_before_cas",
    )
    for stage in raw_stages:
        hook(stage)
    assert received == [LiveStartFaultPoint(value) for value in expected]
    assert all(isinstance(point, LiveStartFaultPoint) for point in received)
    with pytest.raises(ValueError, match="^runtime_atomic_fault_point_invalid$"):
        hook("unexpected-atomic-stage")
    assert received == [LiveStartFaultPoint(value) for value in expected]
