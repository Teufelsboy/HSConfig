from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import hsconfig.atomic_io as atomic_io
from hsconfig.atomic_io import (
    atomic_write_bytes,
    atomic_write_json,
    flush_file,
)


FAULT_STAGES = (
    "before_temp_write",
    "after_temp_write",
    "after_temp_flush",
    "before_replace",
    "after_replace",
    "after_parent_flush",
)
PRE_REPLACE_STAGES = frozenset(FAULT_STAGES[:4])


class InjectedFault(RuntimeError):
    pass


class InjectedBaseFault(BaseException):
    pass


class CleanupFault(RuntimeError):
    pass


class HostilePrimary(BaseException):
    def add_note(self, note: str) -> None:
        del note
        raise CleanupFault("hostile-add-note")


class ControlledTempHandle:
    def __init__(
        self,
        *,
        fail_operation: str | None = None,
        close_fails: bool = False,
    ) -> None:
        self.fail_operation = fail_operation
        self.close_fails = close_fails
        self.closed = False
        self.close_attempts = 0

    def __enter__(self) -> ControlledTempHandle:
        return self

    def __exit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        self.close()

    def write(self, _content: bytes) -> int:
        self._raise_at("write")
        return 0

    def flush(self) -> None:
        self._raise_at("flush")

    def fileno(self) -> int:
        return 987_654

    def close(self) -> None:
        self.close_attempts += 1
        self.closed = True
        if self.close_fails:
            raise CleanupFault("secondary-close")

    def _raise_at(self, operation: str) -> None:
        if self.fail_operation == operation:
            raise InjectedBaseFault(operation)


def _fault_at(target_stage: str) -> Callable[[str], None]:
    def raise_at_stage(stage: str) -> None:
        if stage == target_stage:
            raise InjectedFault(stage)

    return raise_at_stage


def _base_fault_at(target_stage: str) -> Callable[[str], None]:
    def raise_at_stage(stage: str) -> None:
        if stage == target_stage:
            raise InjectedBaseFault(stage)

    return raise_at_stage


@pytest.mark.parametrize("fault_stage", FAULT_STAGES)
def test_atomic_write_bytes_preserves_a_complete_version_at_every_fault_stage(
    tmp_path: Path,
    fault_stage: str,
) -> None:
    target = tmp_path / "state.bin"
    old_content = b"old-state"
    new_content = b"new-state-with-a-different-length"
    target.write_bytes(old_content)

    with pytest.raises(InjectedFault, match=fault_stage):
        atomic_write_bytes(
            target,
            new_content,
            fault_hook=_fault_at(fault_stage),
        )

    if fault_stage in PRE_REPLACE_STAGES:
        assert target.read_bytes() == old_content
    else:
        assert target.read_bytes() == new_content
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("fault_stage", FAULT_STAGES)
def test_atomic_write_cleans_sibling_temp_after_base_exception(
    tmp_path: Path,
    fault_stage: str,
) -> None:
    target = tmp_path / "state.bin"
    old_content = b"old-state"
    new_content = b"complete-new-state"
    target.write_bytes(old_content)

    with pytest.raises(InjectedBaseFault, match=fault_stage):
        atomic_write_bytes(
            target,
            new_content,
            fault_hook=_base_fault_at(fault_stage),
        )

    if fault_stage in PRE_REPLACE_STAGES:
        assert target.read_bytes() == old_content
    else:
        assert target.read_bytes() == new_content
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("fault_stage", FAULT_STAGES)
def test_atomic_write_json_never_publishes_truncated_or_mixed_json(
    tmp_path: Path,
    fault_stage: str,
) -> None:
    target = tmp_path / "state.json"
    old_payload = {"generation": "old", "values": [1, 2, 3]}
    new_payload = {
        "generation": "new",
        "values": ["different", "complete", "content"],
    }
    target.write_text(json.dumps(old_payload), encoding="utf-8")

    with pytest.raises(InjectedFault, match=fault_stage):
        atomic_write_json(
            target,
            new_payload,
            fault_hook=_fault_at(fault_stage),
        )

    published = json.loads(target.read_text(encoding="utf-8"))
    if fault_stage in PRE_REPLACE_STAGES:
        assert published == old_payload
    else:
        assert published == new_payload
    assert list(tmp_path.iterdir()) == [target]


def test_atomic_write_calls_the_six_fault_stages_in_commit_order(
    tmp_path: Path,
) -> None:
    target = tmp_path / "state.bin"
    observed_stages: list[str] = []

    atomic_write_bytes(target, b"complete", fault_hook=observed_stages.append)

    assert observed_stages == list(FAULT_STAGES)
    assert target.read_bytes() == b"complete"


@pytest.mark.parametrize(
    "operation",
    ("write", "flush", "fsync", "replace"),
)
def test_atomic_write_removes_temp_after_low_level_base_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    target = tmp_path / "state.bin"
    target.write_bytes(b"old")
    temp = tmp_path / ".state.bin.controlled.tmp"
    temp.write_bytes(b"partial")
    handle = ControlledTempHandle(
        fail_operation=operation if operation in {"write", "flush"} else None
    )
    real_fsync = os.fsync

    monkeypatch.setattr(
        atomic_io,
        "_open_unique_sibling_temp",
        lambda _target, **_kwargs: (
            temp,
            handle,
            atomic_io._lstat_identity(temp),
            temp,
        ),
    )

    def controlled_fsync(descriptor: int) -> None:
        if descriptor == handle.fileno():
            if operation == "fsync":
                raise InjectedBaseFault("fsync")
            return
        real_fsync(descriptor)

    monkeypatch.setattr(os, "fsync", controlled_fsync)
    if operation == "replace":
        monkeypatch.setattr(
            atomic_io,
            "secure_replace",
            lambda _source, _target, **_kwargs: (_ for _ in ()).throw(
                InjectedBaseFault("replace")
            ),
        )

    with pytest.raises(InjectedBaseFault, match=operation):
        atomic_write_bytes(target, b"new")

    assert target.read_bytes() == b"old"
    assert handle.closed
    assert not temp.exists()


def test_atomic_write_cleanup_failures_do_not_mask_primary_base_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "state.bin"
    target.write_bytes(b"old")
    temp = tmp_path / ".state.bin.controlled.tmp"
    temp.write_bytes(b"partial")
    handle = ControlledTempHandle(
        fail_operation="write",
        close_fails=True,
    )
    unlink_attempts: list[Path] = []

    monkeypatch.setattr(
        atomic_io,
        "_open_unique_sibling_temp",
        lambda _target, **_kwargs: (
            temp,
            handle,
            atomic_io._lstat_identity(temp),
            temp,
        ),
    )

    def reject_owned_temp_cleanup(
        path: Path,
        **_kwargs: object,
    ) -> None:
        unlink_attempts.append(path)
        raise CleanupFault("secondary-unlink")

    monkeypatch.setattr(
        atomic_io,
        "secure_unlink",
        reject_owned_temp_cleanup,
    )
    try:
        with pytest.raises(InjectedBaseFault, match="write") as caught:
            atomic_write_bytes(target, b"new")

        assert handle.close_attempts >= 1
        assert unlink_attempts == [temp]
        assert target.read_bytes() == b"old"
        notes = getattr(caught.value, "__notes__", [])
        assert any("secondary-close" in note for note in notes)
        assert any("secondary-unlink" in note for note in notes)
    finally:
        temp.unlink(missing_ok=True)


def test_hostile_add_note_never_masks_primary_atomic_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "state.bin"
    target.write_bytes(b"old")
    identifier = type("Identifier", (), {"hex": "owned"})()
    temp = tmp_path / ".state.bin.owned.tmp"
    real_secure_unlink = atomic_io.secure_unlink
    monkeypatch.setattr(atomic_io.uuid, "uuid4", lambda: identifier)

    def reject_owned_temp_cleanup(
        path: Path,
        **kwargs: Any,
    ) -> None:
        if path == temp:
            raise CleanupFault("secondary-unlink")
        real_secure_unlink(path, **kwargs)

    def interrupt_before_replace(stage: str) -> None:
        if stage == "before_replace":
            raise HostilePrimary("primary")

    monkeypatch.setattr(
        atomic_io,
        "secure_unlink",
        reject_owned_temp_cleanup,
    )
    try:
        with pytest.raises(HostilePrimary, match="primary"):
            atomic_write_bytes(
                target,
                b"new",
                fault_hook=interrupt_before_replace,
            )
    finally:
        temp.unlink(missing_ok=True)


def test_fstat_base_exception_does_not_leak_exclusive_created_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "state.bin"
    target.write_bytes(b"old")
    identifier = type("Identifier", (), {"hex": "owned"})()
    temp = tmp_path / ".state.bin.owned.tmp"
    monkeypatch.setattr(atomic_io.uuid, "uuid4", lambda: identifier)
    monkeypatch.setattr(
        atomic_io,
        "_fstat_identity",
        lambda _handle: (_ for _ in ()).throw(
            InjectedBaseFault("fstat")
        ),
    )

    with pytest.raises(InjectedBaseFault, match="fstat"):
        atomic_write_bytes(target, b"new")

    assert target.read_bytes() == b"old"
    assert not temp.exists()
    assert list(tmp_path.iterdir()) == [target]


def test_candidate_lstat_base_exception_recovers_open_handle_identity_for_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "state.bin"
    target.write_bytes(b"old")
    identifier = type("Identifier", (), {"hex": "owned"})()
    temp = tmp_path / ".state.bin.owned.tmp"
    real_lstat_identity = atomic_io._lstat_identity
    candidate_lstat_attempts = 0
    monkeypatch.setattr(atomic_io.uuid, "uuid4", lambda: identifier)

    def fail_candidate_lstat_once(path: Path) -> tuple[int, int, int]:
        nonlocal candidate_lstat_attempts
        if path == temp:
            candidate_lstat_attempts += 1
            if candidate_lstat_attempts == 1:
                raise InjectedBaseFault("candidate-lstat")
        return real_lstat_identity(path)

    monkeypatch.setattr(
        atomic_io,
        "_lstat_identity",
        fail_candidate_lstat_once,
    )

    with pytest.raises(InjectedBaseFault, match="candidate-lstat"):
        atomic_write_bytes(target, b"new")

    assert candidate_lstat_attempts == 2
    assert target.read_bytes() == b"old"
    assert not temp.exists()
    assert list(tmp_path.iterdir()) == [target]


def test_before_replace_cleanup_preserves_reused_foreign_temp_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "state.bin"
    target.write_bytes(b"old")
    identifier = type("Identifier", (), {"hex": "owned"})()
    temp = tmp_path / ".state.bin.owned.tmp"
    monkeypatch.setattr(atomic_io.uuid, "uuid4", lambda: identifier)

    def reuse_temp_name(stage: str) -> None:
        if stage != "before_replace":
            return
        temp.unlink()
        temp.write_bytes(b"foreign")
        raise InjectedBaseFault(stage)

    with pytest.raises(InjectedBaseFault, match="before_replace"):
        atomic_write_bytes(target, b"new", fault_hook=reuse_temp_name)

    assert target.read_bytes() == b"old"
    assert temp.read_bytes() == b"foreign"


def test_after_replace_fault_does_not_unlink_reused_foreign_temp_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "state.bin"
    target.write_bytes(b"old")
    identifier = type("Identifier", (), {"hex": "owned"})()
    temp = tmp_path / ".state.bin.owned.tmp"
    monkeypatch.setattr(atomic_io.uuid, "uuid4", lambda: identifier)

    def reuse_temp_name(stage: str) -> None:
        if stage != "after_replace":
            return
        assert target.read_bytes() == b"new"
        temp.write_bytes(b"foreign")
        raise InjectedBaseFault(stage)

    with pytest.raises(InjectedBaseFault, match="after_replace"):
        atomic_write_bytes(target, b"new", fault_hook=reuse_temp_name)

    assert target.read_bytes() == b"new"
    assert temp.read_bytes() == b"foreign"


def test_atomic_write_uses_exclusive_unique_sibling_without_overwriting_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "state.bin"
    target.write_bytes(b"old")
    collision = tmp_path / ".state.bin.collision.tmp"
    collision.write_bytes(b"not-owned")
    identifiers = iter(
        (
            type("Identifier", (), {"hex": "collision"})(),
            type("Identifier", (), {"hex": "unique"})(),
        )
    )
    real_secure_open = atomic_io.secure_open_file_descriptor
    attempted_temps: list[Path] = []

    def record_exclusive_open(
        path: Path,
        *,
        create: bool,
        write: bool,
        expected_parent_identity: tuple[int, int, int] | None = None,
    ) -> int:
        if create:
            attempted_temps.append(path)
        return real_secure_open(
            path,
            create=create,
            write=write,
            expected_parent_identity=expected_parent_identity,
        )

    monkeypatch.setattr(atomic_io.uuid, "uuid4", lambda: next(identifiers))
    monkeypatch.setattr(
        atomic_io,
        "secure_open_file_descriptor",
        record_exclusive_open,
    )

    atomic_write_bytes(target, b"new")

    assert target.read_bytes() == b"new"
    assert collision.read_bytes() == b"not-owned"
    assert attempted_temps == [
        collision,
        tmp_path / ".state.bin.unique.tmp",
    ]
    assert all(path.parent == target.parent for path in attempted_temps)
    assert not attempted_temps[-1].exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        ".state.bin.collision.tmp",
        "state.bin",
    ]


def test_atomic_write_keeps_replacement_correct_when_parent_flush_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "state.bin"
    target.write_bytes(b"old")

    def reject_directory_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
    ) -> int:
        raise OSError("directory handles are unavailable on this platform")

    monkeypatch.setattr(os, "open", reject_directory_open)

    atomic_write_bytes(target, b"new")

    assert target.read_bytes() == b"new"
    assert list(tmp_path.iterdir()) == [target]


def test_atomic_write_suppresses_parent_directory_close_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "state.bin"
    target.write_bytes(b"old")
    directory_descriptor = 876_543
    real_fsync = os.fsync
    real_close = os.close

    monkeypatch.setattr(os, "open", lambda _path, _flags: directory_descriptor)

    def controlled_fsync(descriptor: int) -> None:
        if descriptor == directory_descriptor:
            raise OSError("directory fsync unavailable")
        real_fsync(descriptor)

    def controlled_close(descriptor: int) -> None:
        if descriptor == directory_descriptor:
            raise OSError("directory close unavailable")
        real_close(descriptor)

    monkeypatch.setattr(os, "fsync", controlled_fsync)
    monkeypatch.setattr(os, "close", controlled_close)

    atomic_write_bytes(target, b"new")

    assert target.read_bytes() == b"new"
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("target_exists", (False, True))
def test_replace_base_exception_keeps_old_or_missing_target_and_no_owned_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target_exists: bool,
) -> None:
    target = tmp_path / "state.bin"
    if target_exists:
        target.write_bytes(b"old")

    def reject_replace(
        _source: Path,
        _target: Path,
        **_kwargs: object,
    ) -> None:
        raise InjectedBaseFault("replace")

    monkeypatch.setattr(
        atomic_io,
        "secure_replace",
        reject_replace,
    )

    with pytest.raises(InjectedBaseFault, match="replace"):
        atomic_write_bytes(target, b"new")

    if target_exists:
        assert target.read_bytes() == b"old"
    else:
        assert not target.exists()
    assert sorted(path.name for path in tmp_path.iterdir()) == (
        ["state.bin"] if target_exists else []
    )


def test_post_commit_hooks_observe_exact_complete_new_bytes(
    tmp_path: Path,
) -> None:
    target = tmp_path / "state.bin"
    target.write_bytes(b"old")
    new_content = b"complete-new-content"
    observed: dict[str, bytes] = {}

    def observe(stage: str) -> None:
        if stage in {"after_replace", "after_parent_flush"}:
            observed[stage] = target.read_bytes()

    atomic_write_bytes(target, new_content, fault_hook=observe)

    assert observed == {
        "after_replace": new_content,
        "after_parent_flush": new_content,
    }


def test_atomic_write_durability_operations_have_strict_commit_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "state.bin"
    target.write_bytes(b"old")
    temp = tmp_path / ".state.bin.controlled.tmp"
    temp.write_bytes(b"new")
    events: list[str] = []
    directory_descriptor = 765_432

    class OrderedHandle(ControlledTempHandle):
        def write(self, content: bytes) -> int:
            events.append("write")
            temp.write_bytes(content)
            return len(content)

        def flush(self) -> None:
            events.append("flush")

        def fileno(self) -> int:
            return 654_321

        def close(self) -> None:
            events.append("close")
            self.closed = True

    handle = OrderedHandle()
    real_replace = atomic_io.secure_replace
    real_close = os.close
    monkeypatch.setattr(
        atomic_io,
        "_open_unique_sibling_temp",
        lambda _target, **_kwargs: (
            temp,
            handle,
            atomic_io._lstat_identity(temp),
            temp,
        ),
    )

    def record_fsync(descriptor: int) -> None:
        events.append(
            "file_fsync"
            if descriptor == handle.fileno()
            else "parent_fsync"
        )

    def record_replace(
        source: Path,
        destination: Path,
        **kwargs: object,
    ) -> None:
        events.append("replace")
        real_replace(source, destination, **kwargs)

    def record_parent_open(_path: Path, _flags: int) -> int:
        events.append("parent_open")
        return directory_descriptor

    def record_parent_close(descriptor: int) -> None:
        if descriptor == directory_descriptor:
            events.append("parent_close")
        else:
            real_close(descriptor)

    monkeypatch.setattr(os, "fsync", record_fsync)
    monkeypatch.setattr(
        atomic_io,
        "secure_replace",
        record_replace,
    )
    monkeypatch.setattr(os, "open", record_parent_open)
    monkeypatch.setattr(os, "close", record_parent_close)

    atomic_write_bytes(target, b"new")

    assert events == [
        "write",
        "flush",
        "file_fsync",
        "close",
        "replace",
        "parent_open",
        "parent_fsync",
        "parent_close",
    ]
    assert target.read_bytes() == b"new"


def test_atomic_write_rejects_parent_symlink_retarget_before_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first"
    alternate = tmp_path / "alternate"
    first.mkdir()
    alternate.mkdir()
    parent = tmp_path / "current"
    try:
        os.symlink(first, parent, target_is_directory=True)
        parent.unlink()
        os.symlink(alternate, parent, target_is_directory=True)
        parent.unlink()
        os.symlink(first, parent, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink retarget unavailable: {exc}")

    target = parent / "state.bin"
    (first / "state.bin").write_bytes(b"first-old")
    (alternate / "state.bin").write_bytes(b"alternate-old")
    identifier = type("Identifier", (), {"hex": "owned"})()
    foreign_temp = alternate / ".state.bin.owned.tmp"
    foreign_temp.write_bytes(b"foreign")
    monkeypatch.setattr(atomic_io.uuid, "uuid4", lambda: identifier)

    def retarget_parent(stage: str) -> None:
        if stage == "before_replace":
            parent.unlink()
            os.symlink(alternate, parent, target_is_directory=True)

    try:
        with pytest.raises(
            (RuntimeError, ValueError),
            match="parent directory changed|filesystem_directory_invalid",
        ):
            atomic_write_bytes(target, b"new", fault_hook=retarget_parent)

        assert (first / "state.bin").read_bytes() == b"first-old"
        assert (alternate / "state.bin").read_bytes() == b"alternate-old"
        assert foreign_temp.read_bytes() == b"foreign"
        assert list(first.glob(".*.tmp")) == []
    finally:
        if parent.is_symlink():
            parent.unlink()


def test_atomic_write_rejects_resolved_parent_swap_with_unchanged_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first"
    alternate = tmp_path / "alternate"
    moved_first = tmp_path / "moved-first"
    first.mkdir()
    alternate.mkdir()
    parent = tmp_path / "current"
    try:
        os.symlink(first, parent, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink unavailable: {exc}")

    (first / "state.bin").write_bytes(b"first-old")
    (alternate / "state.bin").write_bytes(b"alternate-old")
    target = parent / "state.bin"
    identifier = type("Identifier", (), {"hex": "owned"})()
    temp_name = ".state.bin.owned.tmp"
    monkeypatch.setattr(atomic_io.uuid, "uuid4", lambda: identifier)
    lexical_identity = parent.lstat()

    def swap_resolved_parent_and_carry_owned_temp(stage: str) -> None:
        if stage != "before_replace":
            return
        first.rename(moved_first)
        alternate.rename(first)
        (moved_first / temp_name).replace(first / temp_name)

    try:
        with pytest.raises(
            (RuntimeError, ValueError),
            match="resolved parent changed|filesystem_directory_invalid",
        ):
            atomic_write_bytes(
                target,
                b"new",
                fault_hook=swap_resolved_parent_and_carry_owned_temp,
        )

        assert parent.lstat().st_ino == lexical_identity.st_ino
        if moved_first.exists():
            assert (moved_first / "state.bin").read_bytes() == b"first-old"
            assert (first / "state.bin").read_bytes() == b"alternate-old"
        else:
            assert (first / "state.bin").read_bytes() == b"first-old"
            assert (alternate / "state.bin").read_bytes() == (
                b"alternate-old"
            )
    finally:
        if parent.is_symlink():
            parent.unlink()
        for directory in (first, alternate, moved_first):
            if directory.exists():
                for path in directory.glob(".*.tmp"):
                    path.unlink()


def test_atomic_write_json_serialization_failure_precedes_filesystem_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "state.json"
    old_content = b'{"generation":"old"}\n'
    target.write_bytes(old_content)

    def reject_temp_creation(_target: Path):
        pytest.fail("JSON serialization failure reached temp creation")

    monkeypatch.setattr(
        atomic_io,
        "_open_unique_sibling_temp",
        reject_temp_creation,
    )

    with pytest.raises(TypeError):
        atomic_write_json(target, {"not_json": object()})

    assert target.read_bytes() == old_content
    assert list(tmp_path.iterdir()) == [target]


def test_atomic_write_json_emits_exact_sorted_utf8_indented_lf_bytes(
    tmp_path: Path,
) -> None:
    target = tmp_path / "state.json"

    atomic_write_json(
        target,
        {
            "z": "é",
            "a": [1, {"β": "雪"}],
        },
    )

    assert target.read_bytes() == (
        '{\n'
        '  "a": [\n'
        "    1,\n"
        "    {\n"
        '      "β": "雪"\n'
        "    }\n"
        "  ],\n"
        '  "z": "é"\n'
        "}\n"
    ).encode("utf-8")


def test_flush_file_flushes_an_existing_file_without_changing_its_bytes(
    tmp_path: Path,
) -> None:
    target = tmp_path / "state.bin"
    content = b"bytes-that-must-not-change"
    target.write_bytes(content)

    flush_file(target)

    assert target.read_bytes() == content
