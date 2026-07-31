from __future__ import annotations

import hashlib
import inspect
import json
import multiprocessing
import os
from pathlib import Path

import pytest

import hsconfig.runtime_installer as runtime_installer
from hsconfig.atomic_io import no_fault
from hsconfig.deck_config_ini import read_deck_config
from hsconfig.output_publisher import PublishedOutput, publish_configure_run
from hsconfig.runtime_installer import (
    RuntimeInstallPlan,
    install_runtime_package,
    plan_runtime_install,
    recover_runtime_state,
)
from hsconfig.runtime_transaction_journal import (
    load_runtime_transaction_journals,
)
from tests.test_runtime_installer import (
    build_rendered_run,
    expected_runtime_entries,
    seed_owned_old_revision,
    state_key_for_test,
)


CHECKPOINTS = (
    "after_lock",
    "after_runtime_staging_copy",
    "after_runtime_staging_verify",
    "after_runtime_revision_rename",
    "before_ini_compare_and_swap",
    "after_ini_compare_and_swap",
    "before_state_write",
    "after_state_write",
    "before_receipt_write",
    "during_receipt_write",
    "before_old_revision_cleanup",
    "during_old_revision_cleanup",
)
PRE_COMMIT_CHECKPOINTS = frozenset(
    {
        "after_lock",
        "after_runtime_staging_copy",
        "after_runtime_staging_verify",
        "after_runtime_revision_rename",
        "before_ini_compare_and_swap",
    }
)


@pytest.fixture(scope="session")
def published_output(
    tmp_path_factory: pytest.TempPathFactory,
) -> PublishedOutput:
    root = tmp_path_factory.mktemp("runtime-installer-source")
    rendered = build_rendered_run(root / "source", 1)
    return publish_configure_run(rendered, root / "published")


def _prepare_plan(
    root: Path,
    published: PublishedOutput,
) -> RuntimeInstallPlan:
    runtime_root = root / "runtime"
    old = runtime_root / "CustomConfig" / "old-complete"
    old.mkdir(parents=True)
    (old / "sentinel.json").write_text('{"old":true}\n', encoding="utf-8")
    (runtime_root / "CustomConfig" / "deck_config.ini").write_text(
        "[CONFIGS]\nShadowPriest = old-complete\n",
        encoding="utf-8",
    )
    return plan_runtime_install(
        published_output=published,
        runtime_root=runtime_root,
    )


def _assert_recovered_contract(
    plan: RuntimeInstallPlan,
    published: PublishedOutput,
    checkpoint: str,
) -> None:
    state = recover_runtime_state(plan.runtime_root)
    snapshot = read_deck_config(
        plan.runtime_root / "CustomConfig" / "deck_config.ini",
        deck_name=plan.deck_name,
    )
    old = plan.runtime_root / "CustomConfig" / "old-complete"
    assert (old / "sentinel.json").read_text(encoding="utf-8") == (
        '{"old":true}\n'
    )

    if checkpoint in PRE_COMMIT_CHECKPOINTS:
        assert snapshot.selected_config_dir == "old-complete"
        assert state is None or all(
            deck.deck_name.casefold() != plan.deck_name.casefold()
            for deck in state.decks
        )
        assert not (
            plan.runtime_root
            / "CustomConfig"
            / plan.versioned_config_dir
        ).exists()
        assert not list(
            (plan.runtime_root / ".hsconfig" / "receipts").rglob("*.json")
        )
    else:
        assert snapshot.selected_config_dir == plan.versioned_config_dir
        target = (
            plan.runtime_root
            / "CustomConfig"
            / plan.versioned_config_dir
        )
        logical, expected, digest = expected_runtime_entries(published)
        del logical
        assert digest == plan.package_root_sha256
        assert {
            path.relative_to(target).as_posix(): path.read_bytes()
            for path in target.rglob("*")
            if path.is_file()
        } == expected
        assert state is not None
        matching = [
            deck
            for deck in state.decks
            if deck.deck_name.casefold() == plan.deck_name.casefold()
        ]
        assert len(matching) == 1
        assert matching[0].config_dir == plan.versioned_config_dir
        receipt = (
            plan.runtime_root
            / ".hsconfig"
            / "receipts"
            / matching[0].state_key
            / "last_apply_receipt.json"
        )
        assert receipt.is_file()
        assert list(
            (plan.runtime_root / ".hsconfig" / "receipts").rglob("*.json")
        ) == [receipt]

    assert recover_runtime_state(plan.runtime_root) == state
    staging = plan.runtime_root / ".hsconfig" / "staging"
    assert list(staging.iterdir()) == []
    assert not list(plan.runtime_root.rglob("*.tmp"))
    journals = list(
        (plan.runtime_root / ".hsconfig" / "transactions").glob("*.json")
    )
    assert len(journals) <= 1


@pytest.mark.parametrize("checkpoint", CHECKPOINTS)
def test_ordinary_exception_at_every_checkpoint_recovers(
    tmp_path: Path,
    published_output: PublishedOutput,
    checkpoint: str,
) -> None:
    plan = _prepare_plan(tmp_path, published_output)

    def inject(stage: str) -> None:
        if stage == checkpoint:
            raise RuntimeError(f"fault:{checkpoint}")

    if checkpoint in {"before_receipt_write", "during_receipt_write"}:
        result = install_runtime_package(plan, fault_hook=inject)
        assert result.status == "committed_receipt_pending"
    else:
        with pytest.raises(RuntimeError, match=f"fault:{checkpoint}"):
            install_runtime_package(plan, fault_hook=inject)

    _assert_recovered_contract(plan, published_output, checkpoint)


@pytest.mark.parametrize("checkpoint", CHECKPOINTS)
def test_base_exception_at_every_checkpoint_is_reraised_then_recovers(
    tmp_path: Path,
    published_output: PublishedOutput,
    checkpoint: str,
) -> None:
    plan = _prepare_plan(tmp_path, published_output)

    def inject(stage: str) -> None:
        if stage == checkpoint:
            raise KeyboardInterrupt(f"base-fault:{checkpoint}")

    with pytest.raises(KeyboardInterrupt, match=f"base-fault:{checkpoint}"):
        install_runtime_package(plan, fault_hook=inject)

    _assert_recovered_contract(plan, published_output, checkpoint)


def _hard_exit_worker(plan: RuntimeInstallPlan, checkpoint: str) -> None:
    def terminate(stage: str) -> None:
        if stage == checkpoint:
            os._exit(77)

    install_runtime_package(plan, fault_hook=terminate)
    os._exit(0)


@pytest.mark.parametrize("checkpoint", CHECKPOINTS)
def test_process_termination_at_every_persisted_checkpoint_recovers(
    tmp_path: Path,
    published_output: PublishedOutput,
    checkpoint: str,
) -> None:
    plan = _prepare_plan(tmp_path, published_output)
    process = multiprocessing.get_context("spawn").Process(
        target=_hard_exit_worker,
        args=(plan, checkpoint),
    )
    process.start()
    process.join(60)
    if process.is_alive():
        process.terminate()
        process.join(10)
        pytest.fail(f"worker hung at {checkpoint}")
    assert process.exitcode == 77

    _assert_recovered_contract(plan, published_output, checkpoint)


def _locking_worker(
    plan: RuntimeInstallPlan,
    started: object,
    release: object,
    result: object,
) -> None:
    def block_after_lock(stage: str) -> None:
        if stage == "after_lock":
            started.set()  # type: ignore[attr-defined]
            if not release.wait(30):  # type: ignore[attr-defined]
                raise TimeoutError("release timeout")

    try:
        applied = install_runtime_package(plan, fault_hook=block_after_lock)
    except BaseException as error:
        result.put(("error", repr(error)))  # type: ignore[attr-defined]
        return
    result.put(("ok", applied.status))  # type: ignore[attr-defined]


def test_apply_lock_serializes_processes_without_partial_selection(
    tmp_path: Path,
    published_output: PublishedOutput,
) -> None:
    plan = _prepare_plan(tmp_path, published_output)
    context = multiprocessing.get_context("spawn")
    first_started = context.Event()
    first_release = context.Event()
    second_started = context.Event()
    second_release = context.Event()
    second_release.set()
    results = context.Queue()
    first = context.Process(
        target=_locking_worker,
        args=(plan, first_started, first_release, results),
    )
    second = context.Process(
        target=_locking_worker,
        args=(plan, second_started, second_release, results),
    )
    first.start()
    assert first_started.wait(30)
    second.start()
    assert not second_started.wait(0.5)
    first_release.set()
    first.join(60)
    second.join(60)
    assert first.exitcode == 0
    assert second.exitcode == 0
    outcomes = {results.get(timeout=10), results.get(timeout=10)}
    assert outcomes == {("ok", "applied"), ("ok", "already_current")}
    _assert_recovered_contract(
        plan,
        published_output,
        "after_ini_compare_and_swap",
    )


def _fresh_plan_with_owned_old(
    root: Path,
    published: PublishedOutput,
) -> tuple[RuntimeInstallPlan, Path]:
    runtime_root = root / "runtime"
    runtime_root.mkdir()
    (runtime_root / "CustomConfig").mkdir()
    plan = plan_runtime_install(
        published_output=published,
        runtime_root=runtime_root,
    )
    old_target, _journal = seed_owned_old_revision(runtime_root)
    return plan, old_target


def test_exception_after_real_old_file_unlink_resumes_cleanup(
    tmp_path: Path,
    published_output: PublishedOutput,
) -> None:
    plan, old_target = _fresh_plan_with_owned_old(
        tmp_path,
        published_output,
    )
    observed_counts: list[int] = []

    def inject(stage: str) -> None:
        if stage != "during_old_revision_cleanup":
            return
        count = len(list(old_target.glob("*.json")))
        observed_counts.append(count)
        if count < 3:
            raise RuntimeError("fault-after-real-old-unlink")

    with pytest.raises(RuntimeError, match="fault-after-real-old-unlink"):
        install_runtime_package(plan, fault_hook=inject)

    assert observed_counts and observed_counts[0] < 3
    assert not old_target.exists()
    assert recover_runtime_state(plan.runtime_root) is not None
    assert len(load_runtime_transaction_journals(plan.runtime_root)) == 1
    assert recover_runtime_state(plan.runtime_root) is not None
    assert len(load_runtime_transaction_journals(plan.runtime_root)) == 1


def _old_cleanup_hard_exit_worker(
    plan: RuntimeInstallPlan,
    old_target: Path,
    mode: str,
) -> None:
    def terminate(stage: str) -> None:
        if stage != "during_old_revision_cleanup":
            return
        if mode == "after_first_unlink":
            os._exit(77)
        if mode == "after_tree_delete" and not old_target.exists():
            os._exit(78)

    install_runtime_package(plan, fault_hook=terminate)


def test_hard_kill_after_real_unlink_recovers_partial_owned_tree(
    tmp_path: Path,
    published_output: PublishedOutput,
) -> None:
    plan, old_target = _fresh_plan_with_owned_old(
        tmp_path,
        published_output,
    )
    process = multiprocessing.get_context("spawn").Process(
        target=_old_cleanup_hard_exit_worker,
        args=(plan, old_target, "after_first_unlink"),
    )
    process.start()
    process.join(60)
    assert process.exitcode == 77
    remaining = list(old_target.glob("*.json"))
    assert 0 < len(remaining) < 3

    assert recover_runtime_state(plan.runtime_root) is not None
    assert not old_target.exists()
    assert len(load_runtime_transaction_journals(plan.runtime_root)) == 1
    assert recover_runtime_state(plan.runtime_root) is not None
    assert len(load_runtime_transaction_journals(plan.runtime_root)) == 1


def test_hard_kill_after_tree_delete_removes_stale_owner_journal(
    tmp_path: Path,
    published_output: PublishedOutput,
) -> None:
    plan, old_target = _fresh_plan_with_owned_old(
        tmp_path,
        published_output,
    )
    process = multiprocessing.get_context("spawn").Process(
        target=_old_cleanup_hard_exit_worker,
        args=(plan, old_target, "after_tree_delete"),
    )
    process.start()
    process.join(60)
    assert process.exitcode == 78
    assert not old_target.exists()
    assert len(load_runtime_transaction_journals(plan.runtime_root)) == 2

    assert recover_runtime_state(plan.runtime_root) is not None
    assert len(load_runtime_transaction_journals(plan.runtime_root)) == 1

    assert recover_runtime_state(plan.runtime_root) is not None
    assert len(load_runtime_transaction_journals(plan.runtime_root)) == 1


@pytest.mark.parametrize("tamper", ["unknown", "identity_changed"])
def test_partial_cleanup_never_deletes_unknown_or_identity_changed_child(
    tmp_path: Path,
    published_output: PublishedOutput,
    tamper: str,
) -> None:
    plan, old_target = _fresh_plan_with_owned_old(
        tmp_path,
        published_output,
    )
    process = multiprocessing.get_context("spawn").Process(
        target=_old_cleanup_hard_exit_worker,
        args=(plan, old_target, "after_first_unlink"),
    )
    process.start()
    process.join(60)
    assert process.exitcode == 77
    remaining = sorted(old_target.glob("*.json"))
    assert remaining
    if tamper == "unknown":
        retained = old_target / "UNKNOWN.json"
        retained.write_text('{"unknown":true}\n', encoding="utf-8")
    else:
        retained = remaining[0]
        retained.unlink()
        retained.write_text('{"replacement":true}\n', encoding="utf-8")

    with pytest.raises(
        RuntimeError,
        match="runtime_recovery_ownership_ambiguous",
    ):
        recover_runtime_state(plan.runtime_root)

    assert retained.is_file()
    assert old_target.is_dir()


def _expected_receipt_bytes(plan: RuntimeInstallPlan) -> bytes:
    from hsconfig.deck_config_ini import render_deck_config

    next_ini = render_deck_config(
        plan.ini_snapshot,
        deck_name=plan.deck_name,
        config_dir=plan.versioned_config_dir,
    )
    payload = {
        "schema_version": 1,
        "state_key": state_key_for_test(plan.deck_name),
        "deck_name": plan.deck_name,
        "logical_config_dir": plan.logical_config_dir,
        "config_dir": plan.versioned_config_dir,
        "package_root_sha256": plan.package_root_sha256,
        "source_manifest_sha256": plan.source_revision_root.name.removeprefix(
            "sha256-"
        ),
        "ini_sha256": hashlib.sha256(next_ini).hexdigest(),
    }
    return (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")


@pytest.mark.parametrize("initial_receipt", ["missing", "old", "new"])
@pytest.mark.parametrize("exception_type", [RuntimeError, KeyboardInterrupt])
def test_receipt_fault_runs_inside_atomic_replace_and_recovers_canonical_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    published_output: PublishedOutput,
    initial_receipt: str,
    exception_type: type[BaseException],
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    plan = plan_runtime_install(
        published_output=published_output,
        runtime_root=runtime_root,
    )
    expected = _expected_receipt_bytes(plan)
    receipt = (
        runtime_root
        / ".hsconfig"
        / "receipts"
        / state_key_for_test(plan.deck_name)
        / "last_apply_receipt.json"
    )
    if initial_receipt != "missing":
        receipt.parent.mkdir(parents=True)
        receipt.write_bytes(
            expected if initial_receipt == "new" else b'{"old":true}\n'
        )

    real_atomic_write = runtime_installer.atomic_write_bytes
    atomic_stage: str | None = None
    observed: list[str | None] = []

    def observing_atomic_write(
        path: Path,
        content: bytes,
        *,
        fault_hook: object = no_fault,
    ) -> None:
        def observe_stage(stage: str) -> None:
            nonlocal atomic_stage
            atomic_stage = stage
            fault_hook(stage)  # type: ignore[operator]
            atomic_stage = None

        real_atomic_write(path, content, fault_hook=observe_stage)

    monkeypatch.setattr(
        runtime_installer,
        "atomic_write_bytes",
        observing_atomic_write,
    )

    def inject(stage: str) -> None:
        if stage == "during_receipt_write":
            observed.append(atomic_stage)
            raise exception_type("inner-receipt-fault")

    if exception_type is RuntimeError:
        result = install_runtime_package(plan, fault_hook=inject)
        assert result.status == "committed_receipt_pending"
    else:
        with pytest.raises(KeyboardInterrupt, match="inner-receipt-fault"):
            install_runtime_package(plan, fault_hook=inject)

    assert observed and observed[0] in {
        "after_temp_flush",
        "before_replace",
        "after_replace",
    }
    recover_runtime_state(runtime_root)
    assert receipt.read_bytes() == expected
    assert list(receipt.parent.iterdir()) == [receipt]


def _receipt_hard_exit_worker(plan: RuntimeInstallPlan) -> None:
    def terminate(stage: str) -> None:
        if stage != "during_receipt_write":
            return
        inside_atomic = any(
            frame.function == "atomic_write_bytes" for frame in inspect.stack()
        )
        os._exit(77 if inside_atomic else 78)

    install_runtime_package(plan, fault_hook=terminate)


def test_receipt_hard_kill_occurs_inside_atomic_write_and_recovers(
    tmp_path: Path,
    published_output: PublishedOutput,
) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    plan = plan_runtime_install(
        published_output=published_output,
        runtime_root=runtime_root,
    )
    expected = _expected_receipt_bytes(plan)
    receipt = (
        runtime_root
        / ".hsconfig"
        / "receipts"
        / state_key_for_test(plan.deck_name)
        / "last_apply_receipt.json"
    )
    receipt.parent.mkdir(parents=True)
    receipt.write_bytes(b'{"old":true}\n')
    process = multiprocessing.get_context("spawn").Process(
        target=_receipt_hard_exit_worker,
        args=(plan,),
    )
    process.start()
    process.join(60)
    assert process.exitcode == 77

    recover_runtime_state(runtime_root)
    assert receipt.read_bytes() == expected
    assert list(receipt.parent.iterdir()) == [receipt]
