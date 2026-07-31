from __future__ import annotations

import multiprocessing
import os
from pathlib import Path

import pytest

import hsconfig.output_publisher as output_publisher
from hsconfig.configure_run_model import RenderedConfigureRun
from hsconfig.current_output import resolve_current_package
from hsconfig.output_publisher import (
    publish_configure_run,
    reconcile_output,
)
from tests.test_output_publisher import build_rendered_run
from tests.test_output_publisher import (
    rendered_runs_fixture as _rendered_runs_fixture,  # noqa: F401
)


FAULT_STAGES = (
    "after_lock",
    "after_staging_render",
    "after_staging_verify",
    "after_revision_rename",
    "before_pointer_replace",
    "after_pointer_replace",
    "before_old_revision_cleanup",
    "during_old_revision_cleanup",
)


class InjectedBaseFault(BaseException):
    pass


def _publish_and_hard_kill(
    input_root: str,
    output_root: str,
    fault_stage: str,
) -> None:
    def terminate(stage: str) -> None:
        if stage == fault_stage:
            os._exit(91)

    publish_configure_run(
        build_rendered_run(Path(input_root), 2),
        Path(output_root),
        fault_hook=terminate,
    )


@pytest.mark.parametrize("fault_stage", FAULT_STAGES)
def test_exception_reconciliation_keeps_exactly_one_verified_current(
    tmp_path: Path,
    fault_stage: str,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    first, second = rendered_runs
    output_root = tmp_path / "ShadowPriest"
    old = publish_configure_run(first, output_root)

    def inject(stage: str) -> None:
        if stage == fault_stage:
            raise RuntimeError(stage)

    with pytest.raises(RuntimeError, match=fault_stage):
        publish_configure_run(second, output_root, fault_hook=inject)

    reconciled = reconcile_output(output_root)
    assert reconciled is not None
    assert resolve_current_package(output_root) == reconciled.package_root
    revisions = [
        path
        for path in (output_root / "revisions").iterdir()
        if path.is_dir() and not path.name.startswith(".staging-")
    ]
    assert revisions == [reconciled.revision_root]
    expected = (
        second.content_root_sha256
        if fault_stage
        in {
            "after_pointer_replace",
            "before_old_revision_cleanup",
            "during_old_revision_cleanup",
        }
        else first.content_root_sha256
    )
    assert reconciled.content_root_sha256 == expected
    if expected == first.content_root_sha256:
        assert old.revision_root.is_dir()


@pytest.mark.parametrize("fault_stage", FAULT_STAGES)
def test_baseexception_reconciliation_keeps_exactly_one_current(
    tmp_path: Path,
    fault_stage: str,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    first, second = rendered_runs
    output_root = tmp_path / "ShadowPriest"
    publish_configure_run(first, output_root)

    def inject(stage: str) -> None:
        if stage == fault_stage:
            raise InjectedBaseFault(stage)

    with pytest.raises(InjectedBaseFault):
        publish_configure_run(second, output_root, fault_hook=inject)

    reconciled = reconcile_output(output_root)
    assert reconciled is not None
    assert resolve_current_package(output_root) == reconciled.package_root
    assert [
        path
        for path in (output_root / "revisions").iterdir()
        if path.is_dir() and not path.name.startswith(".staging-")
    ] == [reconciled.revision_root]


@pytest.mark.parametrize("fault_stage", FAULT_STAGES)
def test_hard_kill_reconciliation_keeps_exactly_one_current(
    tmp_path: Path,
    fault_stage: str,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    first, second = rendered_runs
    output_root = tmp_path / "ShadowPriest"
    publish_configure_run(first, output_root)
    context = multiprocessing.get_context("spawn")
    process = context.Process(
        target=_publish_and_hard_kill,
        args=(
            str(tmp_path / "worker-input"),
            str(output_root),
            fault_stage,
        ),
    )
    process.start()
    process.join(60)
    if process.is_alive():
        process.kill()
        process.join(10)
        pytest.fail(f"publisher worker hung at {fault_stage}")
    assert process.exitcode == 91

    reconciled = reconcile_output(output_root)
    assert reconciled is not None
    assert resolve_current_package(output_root) == reconciled.package_root
    assert [
        path
        for path in (output_root / "revisions").iterdir()
        if path.is_dir() and not path.name.startswith(".staging-")
    ] == [reconciled.revision_root]


@pytest.mark.parametrize(
    "fault_stage",
    (
        "after_journal_temp_write",
        "after_pointer_temp_write",
        "after_journal_cleanup_started_temp_write",
        "after_journal_finalized_temp_write",
    ),
)
def test_atomic_temp_hard_kill_recovers_without_temp_residue(
    tmp_path: Path,
    fault_stage: str,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    first, _second = rendered_runs
    output_root = tmp_path / "ShadowPriest"
    old = publish_configure_run(first, output_root)
    context = multiprocessing.get_context("spawn")
    process = context.Process(
        target=_publish_and_hard_kill,
        args=(
            str(tmp_path / "worker-input"),
            str(output_root),
            fault_stage,
        ),
    )
    process.start()
    process.join(60)
    if process.is_alive():
        process.kill()
        process.join(10)
        pytest.fail(f"publisher worker hung at {fault_stage}")
    assert process.exitcode == 91

    reconciled = reconcile_output(output_root)
    assert reconciled is not None
    committed = (
        fault_stage.startswith("after_journal_cleanup")
        or fault_stage.startswith("after_journal_finalized")
    )
    if not committed:
        assert reconciled.content_root_sha256 == first.content_root_sha256
        assert reconciled.revision_root == old.revision_root
    else:
        assert reconciled.content_root_sha256 != first.content_root_sha256
        assert not old.revision_root.exists()
    assert not tuple(
        (output_root / ".publisher" / "transactions").glob(".*.tmp")
    )


def test_recovery_closes_revision_rename_before_journal_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    first, second = rendered_runs
    output_root = tmp_path / "ShadowPriest"
    old = publish_configure_run(first, output_root)
    original = output_publisher._write_transaction

    def interrupt(
        path: Path,
        transaction: object,
        **kwargs: object,
    ) -> None:
        if (
            getattr(transaction, "phase", None) == "revision_ready"
            and getattr(transaction, "owns_revision", False)
        ):
            raise SystemExit("rename-window")
        original(path, transaction, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(output_publisher, "_write_transaction", interrupt)
    with pytest.raises(SystemExit, match="rename-window"):
        publish_configure_run(second, output_root)
    monkeypatch.setattr(output_publisher, "_write_transaction", original)

    reconciled = reconcile_output(output_root)
    assert reconciled is not None
    assert reconciled.revision_root == old.revision_root
    assert [
        path
        for path in (output_root / "revisions").iterdir()
        if path.is_dir() and not path.name.startswith(".staging-")
    ] == [old.revision_root]


def test_recovery_closes_staging_create_before_identity_journal_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    first, second = rendered_runs
    output_root = tmp_path / "ShadowPriest"
    old = publish_configure_run(first, output_root)
    original = output_publisher._write_transaction

    def interrupt(
        path: Path,
        transaction: object,
        **kwargs: object,
    ) -> None:
        if getattr(transaction, "phase", None) == "staging_owned":
            raise SystemExit("staging-window")
        original(path, transaction, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(output_publisher, "_write_transaction", interrupt)
    with pytest.raises(SystemExit, match="staging-window"):
        publish_configure_run(second, output_root)
    monkeypatch.setattr(output_publisher, "_write_transaction", original)

    reconciled = reconcile_output(output_root)
    assert reconciled is not None
    assert reconciled.revision_root == old.revision_root
    assert not any(
        path.name.startswith(".staging-")
        for path in (output_root / "revisions").iterdir()
    )


def test_recovery_closes_pointer_replace_before_journal_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    first, second = rendered_runs
    output_root = tmp_path / "ShadowPriest"
    old = publish_configure_run(first, output_root)
    original = output_publisher._write_transaction

    def interrupt(
        path: Path,
        transaction: object,
        **kwargs: object,
    ) -> None:
        if getattr(transaction, "phase", None) == "pointer_committed":
            raise SystemExit("pointer-window")
        original(path, transaction, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(output_publisher, "_write_transaction", interrupt)
    with pytest.raises(SystemExit, match="pointer-window"):
        publish_configure_run(second, output_root)
    monkeypatch.setattr(output_publisher, "_write_transaction", original)

    reconciled = reconcile_output(output_root)
    assert reconciled is not None
    assert reconciled.content_root_sha256 == second.content_root_sha256
    assert not old.revision_root.exists()


@pytest.mark.parametrize("fault_kind", ("exception", "baseexception"))
def test_old_cleanup_fault_is_after_partial_deletion_and_recovers(
    tmp_path: Path,
    fault_kind: str,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    first, second = rendered_runs
    output_root = tmp_path / "ShadowPriest"
    old = publish_configure_run(first, output_root)
    before_count = sum(1 for _ in old.revision_root.rglob("*"))

    def inject(stage: str) -> None:
        if stage == "during_old_revision_cleanup":
            if fault_kind == "baseexception":
                raise InjectedBaseFault(stage)
            raise RuntimeError(stage)

    expected = (
        InjectedBaseFault
        if fault_kind == "baseexception"
        else RuntimeError
    )
    with pytest.raises(expected):
        publish_configure_run(second, output_root, fault_hook=inject)

    assert old.revision_root.is_dir()
    assert sum(1 for _ in old.revision_root.rglob("*")) < before_count
    current = reconcile_output(output_root)
    assert current is not None
    assert current.content_root_sha256 == second.content_root_sha256
    assert not old.revision_root.exists()


def test_recovery_removes_stale_owner_journal_after_old_root_rmdir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    rendered_runs: tuple[RenderedConfigureRun, RenderedConfigureRun],
) -> None:
    first, second = rendered_runs
    output_root = tmp_path / "ShadowPriest"
    old = publish_configure_run(first, output_root)
    old_journal = next(
        (output_root / ".publisher" / "transactions").iterdir()
    )
    original = output_publisher._remove_file_if_plain

    def interrupt(path: Path) -> None:
        if path == old_journal and not old.revision_root.exists():
            raise SystemExit("after-root-rmdir")
        original(path)

    monkeypatch.setattr(
        output_publisher,
        "_remove_file_if_plain",
        interrupt,
    )
    with pytest.raises(SystemExit, match="after-root-rmdir"):
        publish_configure_run(second, output_root)
    monkeypatch.setattr(
        output_publisher,
        "_remove_file_if_plain",
        original,
    )
    assert not old.revision_root.exists()
    assert old_journal.is_file()

    current = reconcile_output(output_root)
    assert current is not None
    assert current.content_root_sha256 == second.content_root_sha256
    journals = tuple(
        (output_root / ".publisher" / "transactions").iterdir()
    )
    assert len(journals) == 1
    assert journals[0] != old_journal
