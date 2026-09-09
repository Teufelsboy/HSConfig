from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig.apply_invocation import load_apply_invocation
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.operator_profile import derive_deck_output_binding, operator_profile_path
from hsconfig.package_io import path_identity
from hsconfig.runtime_live_admission import load_runtime_live_attempt_admission
from hsconfig.runtime_transaction_journal import (
    RuntimeTransactionPhase,
    load_runtime_transaction_journals,
)
from tests.test_codex_first_live_e2e import _local_state, _prepare_approved
from tests.test_configure_prepublication_apply import (
    _file_fingerprint,
    _physical_tree,
    _persist_worker_oracle,
)
from tests.test_controller_output_hard_kills import (
    _expected_apply_entry_counts,
    _frozen_identity,
    _public_resume_worker,
    _sha256_bytes,
    _spawn_and_join,
    _start_apply_entry_observer,
)
from tests.test_controller_runtime_hard_kills import (
    _assert_complete_layout,
    _assert_final_state,
    _assert_physical_runtime_admission,
    _assert_post_kill_apply_lock,
    _publication_transaction_snapshot,
)


_INNER_CREATED = "after_generic_file_inner_temp_created"
_INNER_PARTIAL = "after_generic_file_inner_temp_partial"
_INNER_FULL = "after_generic_file_inner_temp_full"
_INNER_FLUSHED = "after_generic_file_inner_temp_flushed"
_STAGING_FLUSHED = (
    LiveStartFaultPoint.AFTER_GENERIC_FILE_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS.value
)
_STAGING_BOUND = LiveStartFaultPoint.AFTER_NONTERMINAL_RECOVERY_CURSOR_CAS.value
_POSIX_LINKED = LiveStartFaultPoint.AFTER_BOUND_STAGING_POSIX_LINK_BEFORE_UNLINK.value
_FINAL_COMMITTED = LiveStartFaultPoint.AFTER_GENERIC_FILE_BOUND_COMMIT_BEFORE_CAS.value
_PHYSICAL_STEP = (
    LiveStartFaultPoint.AFTER_NONTERMINAL_RECOVERY_PHYSICAL_STEP_BEFORE_CURSOR_CAS.value
)
_JOURNAL_CREATED = LiveStartFaultPoint.AFTER_RUNTIME_JOURNAL_CREATED.value


@dataclass(frozen=True, slots=True)
class _AtomicJournalCase:
    name: str
    fault_value: str
    cursor_stage: str
    physical_state: str
    requires_unbound_retirement: bool = False
    posix_only: bool = False


_CASES = (
    _AtomicJournalCase(
        "inner-created",
        _INNER_CREATED,
        "PLANNED",
        "inner_created",
        requires_unbound_retirement=True,
    ),
    _AtomicJournalCase(
        "inner-partial",
        _INNER_PARTIAL,
        "PLANNED",
        "inner_partial",
        requires_unbound_retirement=True,
    ),
    _AtomicJournalCase(
        "inner-full",
        _INNER_FULL,
        "PLANNED",
        "inner_full",
        requires_unbound_retirement=True,
    ),
    _AtomicJournalCase(
        "inner-flushed",
        _INNER_FLUSHED,
        "PLANNED",
        "inner_flushed",
        requires_unbound_retirement=True,
    ),
    _AtomicJournalCase(
        "staging-flushed-before-bound-cas",
        _STAGING_FLUSHED,
        "PLANNED",
        "staging",
        requires_unbound_retirement=True,
    ),
    _AtomicJournalCase(
        "after-staging-bound-cas",
        _STAGING_BOUND,
        "STAGING_BOUND",
        "staging",
    ),
    _AtomicJournalCase(
        "posix-link-before-unlink",
        _POSIX_LINKED,
        "STAGING_BOUND",
        "linked",
        posix_only=True,
    ),
    _AtomicJournalCase(
        "final-commit-before-receipt-cas",
        _FINAL_COMMITTED,
        "STAGING_BOUND",
        "final",
    ),
)


def _point_value(point: object) -> str:
    value = getattr(point, "value", point)
    return str(value)


def _path_lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _raw_held_session(session_root: Path) -> session.LiveStartSession:
    session_path = session_root / "session.json"
    return session._load_session_bytes(
        session_path.read_bytes(),
        session_identity=path_identity(session_path),
    )


def _selected_initial_journal_cursor(
    persisted: session.LiveStartSession,
    *,
    cursor_stage: str,
) -> tuple[Mapping[str, object], Mapping[str, object]] | None:
    if (
        persisted.phase.value != "APPLY_STARTED"
        or persisted.pending_transition is not None
    ):
        return None
    recovery = persisted.apply_recovery
    if not isinstance(recovery, Mapping):
        return None
    external = recovery.get("external_file_action")
    if not isinstance(external, Mapping):
        return None
    expected_action, action_kind = (
        ("materialize_file_action_staging", "materialize_file_action_staging")
        if cursor_stage == "PLANNED"
        else (
            "advance_controller_transaction_journal_write",
            "advance_controller_transaction_journal_write",
        )
    )
    selected = (
        recovery.get("recovery_stage") == "ACTIVE"
        and recovery.get("install_route") == "new_target"
        and recovery.get("runtime_match_status") == "not_run"
        and recovery.get("stable_physical_disposition") is None
        and recovery.get("expected_action") == expected_action
        and recovery.get("planned_journal_successor_phase") == "PREPARED"
        and recovery.get("successor_journal_path") is None
        and recovery.get("successor_journal_identity") is None
        and recovery.get("successor_journal_sha256") is None
        and recovery.get("successor_candidate_identity") is None
        and external.get("stage") == cursor_stage
        and external.get("action_kind") == action_kind
        and external.get("commit_mode") == "create_no_replace"
        and external.get("predecessor_state") == "absent"
        and external.get("predecessor_identity") is None
        and external.get("predecessor_size") is None
        and external.get("predecessor_sha256") is None
        and external.get("final_path") == recovery.get("planned_journal_successor_path")
        and external.get("parent_identity")
        == recovery.get("planned_journal_successor_parent_identity")
        and external.get("planned_successor_size")
        == recovery.get("planned_journal_successor_size")
        and external.get("planned_successor_sha256")
        == recovery.get("planned_journal_successor_sha256")
    )
    return (recovery, external) if selected else None


def _path_observation(path: Path, *, read_content: bool) -> dict[str, object]:
    if not _path_lexists(path):
        return {"exists": False}
    status = path.lstat()
    assert stat.S_ISREG(status.st_mode)
    assert not path.is_symlink()
    result: dict[str, object] = {
        "exists": True,
        "identity": path_identity(path),
        "size": status.st_size,
        "nlink": status.st_nlink,
        "sha256": None,
    }
    if read_content:
        result["sha256"] = _sha256_bytes(path.read_bytes())
    return result


def _runtime_tree_for_oracle(
    runtime_root: Path,
    *,
    opaque_paths: frozenset[Path],
) -> dict[str, dict[str, object]]:
    paths = (runtime_root, *sorted(runtime_root.rglob("*")))
    result: dict[str, dict[str, object]] = {}
    for path in paths:
        relative = (
            "." if path == runtime_root else path.relative_to(runtime_root).as_posix()
        )
        status = path.lstat()
        if stat.S_ISDIR(status.st_mode):
            result[relative] = {
                "kind": "directory",
                "identity": path_identity(path),
            }
        elif stat.S_ISREG(status.st_mode):
            row: dict[str, object] = {
                "kind": "file",
                "identity": path_identity(path),
                "size": status.st_size,
                "sha256": None,
            }
            if path not in opaque_paths:
                row["sha256"] = _sha256_bytes(path.read_bytes())
            result[relative] = row
        else:
            result[relative] = {
                "kind": "unsafe",
                "identity": path_identity(path),
            }
    return result


def _atomic_journal_hard_kill_worker(
    session_root_text: str,
    fault_value: str,
    cursor_stage: str,
    physical_state: str,
    oracle_path_text: str,
) -> None:
    session_root = Path(session_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    apply_entry_counts, previous_profile = _start_apply_entry_observer()

    def hard_kill(point: object) -> None:
        if _point_value(point) != fault_value:
            return
        persisted = _raw_held_session(session_root)
        selected = _selected_initial_journal_cursor(
            persisted,
            cursor_stage=cursor_stage,
        )
        if selected is None:
            return
        recovery, external = selected
        final_path = Path(str(external["final_path"]))
        staging_path = Path(str(external["staging_path"]))
        inner_path = Path(str(external["inner_temp_path"]))
        read_inner = physical_state == "inner_flushed"
        read_staging = physical_state in {"staging", "linked"}
        read_final = physical_state in {"linked", "final"}
        physical = {
            "final": _path_observation(final_path, read_content=read_final),
            "staging": _path_observation(staging_path, read_content=read_staging),
            "inner": _path_observation(inner_path, read_content=read_inner),
        }
        runtime_root = Path(str(recovery["runtime_root"]))
        lock_path = runtime_root / ".hsconfig" / "apply.lock"
        opaque = {lock_path}
        if physical_state in {"inner_created", "inner_partial", "inner_full"}:
            opaque.add(inner_path)
        _persist_worker_oracle(
            Path(oracle_path_text),
            {
                "fault_value": _point_value(point),
                "cursor_stage": cursor_stage,
                "physical_state": physical_state,
                "session": persisted.to_value(),
                "session_identity": persisted.session_identity,
                "session_sha256": persisted.content_sha256,
                "apply_entry_counts": apply_entry_counts,
                "physical": physical,
                "runtime_tree": _runtime_tree_for_oracle(
                    runtime_root,
                    opaque_paths=frozenset(opaque),
                ),
            },
        )
        os._exit(93)

    try:
        controller._finalize_live_start(
            session_root=session_root,
            resume_intake=True,
            fault_hook=hard_kill,
        )
    finally:
        sys.setprofile(previous_profile)
    os._exit(94)


def _observed_public_resume_worker(
    session_root_text: str,
    apply_attempt_id: str,
    final_path_text: str,
    staging_path_text: str,
    inner_path_text: str,
    initial_cursor_stage: str,
    expected_bound_json: str,
    oracle_path_text: str,
) -> None:
    session_root = Path(session_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    final_path = Path(final_path_text)
    staging_path = Path(staging_path_text)
    inner_path = Path(inner_path_text)
    expected_bound = json.loads(expected_bound_json)
    assert expected_bound is None or isinstance(expected_bound, dict)
    events: list[str] = []
    fresh_staging: dict[str, object] | None = None
    apply_entry_counts, previous_profile = _start_apply_entry_observer()
    previous_fault = controller.no_live_start_fault

    def observe(point: object) -> None:
        nonlocal fresh_staging
        label = _point_value(point)
        if label not in {
            _PHYSICAL_STEP,
            _INNER_CREATED,
            _STAGING_FLUSHED,
            _JOURNAL_CREATED,
        }:
            return
        persisted = _raw_held_session(session_root)
        cursor_stage = "STAGING_BOUND" if label == _JOURNAL_CREATED else "PLANNED"
        selected = _selected_initial_journal_cursor(
            persisted,
            cursor_stage=cursor_stage,
        )
        if selected is None:
            return
        recovery, external = selected
        if (
            recovery.get("apply_attempt_id") != apply_attempt_id
            or Path(str(external["final_path"])) != final_path
            or Path(str(external["staging_path"])) != staging_path
            or Path(str(external["inner_temp_path"])) != inner_path
        ):
            return
        if label == _PHYSICAL_STEP:
            if (
                initial_cursor_stage == "PLANNED"
                and not events
                and not _path_lexists(final_path)
                and not _path_lexists(staging_path)
                and not _path_lexists(inner_path)
            ):
                events.append("unbound_residue_retired_before_cursor_cas")
            return
        if label == _INNER_CREATED:
            if initial_cursor_stage != "PLANNED":
                return
            assert events == ["unbound_residue_retired_before_cursor_cas"]
            assert not _path_lexists(final_path)
            assert not _path_lexists(staging_path)
            created = _path_observation(inner_path, read_content=False)
            assert created["exists"] is True
            assert created["size"] == 0
            assert created["nlink"] == 1
            events.append("fresh_inner_created_after_retirement")
            return
        if label == _STAGING_FLUSHED:
            if initial_cursor_stage != "PLANNED":
                return
            assert events == [
                "unbound_residue_retired_before_cursor_cas",
                "fresh_inner_created_after_retirement",
            ]
            assert not _path_lexists(final_path)
            assert not _path_lexists(inner_path)
            fresh_staging = _path_observation(staging_path, read_content=True)
            assert fresh_staging["exists"] is True
            assert fresh_staging["size"] == external["planned_successor_size"]
            assert fresh_staging["sha256"] == external["planned_successor_sha256"]
            assert fresh_staging["nlink"] == 1
            events.append("fresh_staging_bound_before_cursor_cas")
            return

        assert label == _JOURNAL_CREATED
        expected = (
            fresh_staging if initial_cursor_stage == "PLANNED" else expected_bound
        )
        assert isinstance(expected, dict)
        assert not _path_lexists(staging_path)
        assert not _path_lexists(inner_path)
        committed = _path_observation(final_path, read_content=True)
        assert committed["exists"] is True
        assert tuple(committed["identity"]) == tuple(expected["identity"])
        assert committed["size"] == expected["size"]
        assert committed["sha256"] == expected["sha256"]
        assert tuple(committed["identity"]) == tuple(external["staging_identity"])
        assert committed["size"] == external["staging_size"]
        assert committed["sha256"] == external["staging_sha256"]
        assert committed["nlink"] == 1
        journal = json.loads(final_path.read_bytes())
        assert journal["transaction_id"] == apply_attempt_id
        assert journal["phase"] == RuntimeTransactionPhase.PREPARED.value
        events.append("initial_prepared_journal_committed_before_cursor_cas")

    controller.no_live_start_fault = observe
    try:
        result = controller.resume_live_start(session_root=session_root)
        if not isinstance(result, controller.LiveStartResult):
            raise AssertionError("public resume did not return a terminal result")
        terminal = session.load_live_start_session(
            session_root,
            local_app_data_root=session_root.parents[2],
        )
    finally:
        controller.no_live_start_fault = previous_fault
        sys.setprofile(previous_profile)
    expected_events = ["initial_prepared_journal_committed_before_cursor_cas"]
    if initial_cursor_stage == "PLANNED":
        expected_events = [
            "unbound_residue_retired_before_cursor_cas",
            "fresh_inner_created_after_retirement",
            "fresh_staging_bound_before_cursor_cas",
            *expected_events,
        ]
    assert events == expected_events
    _persist_worker_oracle(
        Path(oracle_path_text),
        {
            "status": result.status,
            "run_root": str(result.run_root),
            "summary_sha256": _sha256_bytes(result.summary.canonical_json),
            "session_sha256": terminal.content_sha256,
            "apply_entry_counts": apply_entry_counts,
            "events": events,
        },
    )


def _assert_path_matches_observation(
    path: Path,
    observation: Mapping[str, object],
) -> None:
    if observation["exists"] is False:
        assert not _path_lexists(path)
        return
    status = path.lstat()
    assert stat.S_ISREG(status.st_mode)
    assert not path.is_symlink()
    assert path_identity(path) == tuple(observation["identity"])
    assert status.st_size == observation["size"]
    assert status.st_nlink == observation["nlink"]
    digest = observation["sha256"]
    if digest is not None:
        assert _sha256_bytes(path.read_bytes()) == digest


def _assert_interrupted_first_journal(
    *,
    interrupted: session.LiveStartSession,
    oracle: Mapping[str, object],
    case: _AtomicJournalCase,
) -> tuple[str, Path, Path, Path]:
    selected = _selected_initial_journal_cursor(
        interrupted,
        cursor_stage=case.cursor_stage,
    )
    assert selected is not None
    recovery, external = selected
    _assert_complete_layout(interrupted)
    _assert_physical_runtime_admission(interrupted)
    assert interrupted.closed_apply_recovery_commitment is None
    assert interrupted.result_intent is None
    assert interrupted.attempt_acknowledgement is None
    assert interrupted.terminal_retirement is None

    attempt_id = str(recovery["apply_attempt_id"])
    assert interrupted.runtime_layout_bootstrap["apply_attempt_id"] == attempt_id
    assert recovery["apply_invocation_sha256"] == interrupted.apply_invocation_sha256
    final_path = Path(str(external["final_path"]))
    staging_path = Path(str(external["staging_path"]))
    inner_path = Path(str(external["inner_temp_path"]))
    assert final_path.name == f"{attempt_id}.json"
    assert staging_path == final_path.with_name(f"{final_path.name}.staged")
    assert inner_path == staging_path.with_name(
        f".{staging_path.name}.live-start-atomic.tmp"
    )
    assert path_identity(final_path.parent) == tuple(external["parent_identity"])

    fence_path = Path(str(recovery["successor_attempt_record_path"]))
    fence_raw = fence_path.read_bytes()
    fence = json.loads(fence_raw)
    assert fence["state"] == "CANDIDATE_PLANNED"
    assert fence["apply_attempt_id"] == attempt_id
    assert fence["candidate_identity"] is None
    assert _file_fingerprint(fence_path) == (
        tuple(recovery["successor_attempt_record_identity"]),
        len(fence_raw),
        recovery["successor_attempt_record_sha256"],
    )
    assert not Path(str(recovery["candidate_path"])).exists()

    physical = oracle["physical"]
    assert isinstance(physical, Mapping)
    for name, path in (
        ("final", final_path),
        ("staging", staging_path),
        ("inner", inner_path),
    ):
        row = physical[name]
        assert isinstance(row, Mapping)
        _assert_path_matches_observation(path, row)

    final_row = physical["final"]
    staging_row = physical["staging"]
    inner_row = physical["inner"]
    assert isinstance(final_row, Mapping)
    assert isinstance(staging_row, Mapping)
    assert isinstance(inner_row, Mapping)
    planned_size = int(external["planned_successor_size"])
    planned_sha256 = str(external["planned_successor_sha256"])
    exact_journal_path: Path | None = None
    if case.physical_state.startswith("inner_"):
        assert final_row["exists"] is False
        assert staging_row["exists"] is False
        assert inner_row["exists"] is True
        assert inner_row["nlink"] == 1
        if case.physical_state == "inner_created":
            assert inner_row["size"] == 0
        elif case.physical_state in {"inner_partial", "inner_full"}:
            assert 0 <= int(inner_row["size"]) <= planned_size
            assert inner_row["sha256"] is None
        else:
            assert inner_row["size"] == planned_size
            assert inner_row["sha256"] == planned_sha256
            exact_journal_path = inner_path
    elif case.physical_state == "staging":
        assert final_row["exists"] is False
        assert staging_row["exists"] is True
        assert inner_row["exists"] is False
        assert staging_row["size"] == planned_size
        assert staging_row["sha256"] == planned_sha256
        assert staging_row["nlink"] == 1
        exact_journal_path = staging_path
    elif case.physical_state == "linked":
        assert final_row["exists"] is True
        assert staging_row["exists"] is True
        assert inner_row["exists"] is False
        assert final_row["identity"] == staging_row["identity"]
        assert tuple(final_row["identity"]) == tuple(external["staging_identity"])
        assert final_row["size"] == staging_row["size"] == planned_size
        assert final_row["sha256"] == staging_row["sha256"] == planned_sha256
        assert final_row["nlink"] == staging_row["nlink"] == 2
        exact_journal_path = final_path
    else:
        assert case.physical_state == "final"
        assert final_row["exists"] is True
        assert staging_row["exists"] is False
        assert inner_row["exists"] is False
        assert tuple(final_row["identity"]) == tuple(external["staging_identity"])
        assert final_row["size"] == planned_size
        assert final_row["sha256"] == planned_sha256
        assert final_row["nlink"] == 1
        exact_journal_path = final_path
    if case.cursor_stage == "STAGING_BOUND" and case.physical_state == "staging":
        assert tuple(staging_row["identity"]) == tuple(external["staging_identity"])

    if exact_journal_path is not None:
        journal_raw = exact_journal_path.read_bytes()
        journal = json.loads(journal_raw)
        assert journal["transaction_id"] == attempt_id
        assert journal["phase"] == RuntimeTransactionPhase.PREPARED.value
        assert len(journal_raw) == planned_size
        assert _sha256_bytes(journal_raw) == planned_sha256

    runtime_root = Path(str(recovery["runtime_root"]))
    assert not (runtime_root / "CustomConfig/deck_config.ini").exists()
    assert not (runtime_root / ".hsconfig/state.json").exists()
    assert not tuple((runtime_root / ".hsconfig/receipts").rglob("*.json"))
    runtime_tree = oracle["runtime_tree"]
    assert isinstance(runtime_tree, Mapping)
    layout = interrupted.runtime_layout_bootstrap
    assert isinstance(layout, Mapping)
    expected_paths = {".", ".hsconfig", ".hsconfig/apply.lock"}
    expected_paths.update(
        Path(str(row["path"])).relative_to(runtime_root).as_posix()
        for row in layout["directories"]
    )
    expected_paths.add(fence_path.relative_to(runtime_root).as_posix())
    for path in (final_path, staging_path, inner_path):
        if _path_lexists(path):
            expected_paths.add(path.relative_to(runtime_root).as_posix())
    assert set(runtime_tree) == expected_paths
    assert all(row["kind"] != "unsafe" for row in runtime_tree.values())
    return attempt_id, final_path, staging_path, inner_path


def _terminal_snapshot(
    *,
    session_root: Path,
    runtime_root: Path,
    output_root: Path,
) -> dict[str, object]:
    return {
        "session": _file_fingerprint(session_root / "session.json"),
        "summary_json": _file_fingerprint(session_root / "result/summary.json"),
        "summary_markdown": _file_fingerprint(session_root / "result/summary.md"),
        "invocation": _file_fingerprint(
            session_root / "receipts/apply_invocation.json"
        ),
        "profile": _file_fingerprint(operator_profile_path()),
        "runtime": _physical_tree(runtime_root),
        "publication": _physical_tree(output_root),
    }


def _exercise_atomic_journal_hard_kill(
    *,
    fixture: Any,
    prepared: Any,
    case: _AtomicJournalCase,
) -> None:
    approved = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    frozen = _frozen_identity(approved)
    profile_before = _file_fingerprint(operator_profile_path())
    assert profile_before is not None
    output_root = derive_deck_output_binding(
        fixture.profile,
        fixture.deck_name,
    ).output_root
    assert _publication_transaction_snapshot(output_root) == {}

    oracle_path = prepared.run_root.parent / f"atomic-{case.name}-kill.json"
    _spawn_and_join(
        target=_atomic_journal_hard_kill_worker,
        args=(
            str(prepared.run_root),
            case.fault_value,
            case.cursor_stage,
            case.physical_state,
            str(oracle_path),
        ),
        expected_exitcode=93,
        timeout_seconds=360,
    )
    oracle = json.loads(oracle_path.read_bytes())
    assert oracle["fault_value"] == case.fault_value
    assert oracle["cursor_stage"] == case.cursor_stage
    assert oracle["physical_state"] == case.physical_state
    assert oracle["apply_entry_counts"] == _expected_apply_entry_counts(
        fresh=1,
        install_prepare=1,
        attempt_prepare=1,
    )

    interrupted = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    assert oracle["session"] == interrupted.to_value()
    assert tuple(oracle["session_identity"]) == interrupted.session_identity
    assert oracle["session_sha256"] == interrupted.content_sha256
    assert _frozen_identity(interrupted) == frozen
    assert _file_fingerprint(operator_profile_path()) == profile_before
    attempt_id, final_path, staging_path, inner_path = (
        _assert_interrupted_first_journal(
            interrupted=interrupted,
            oracle=oracle,
            case=case,
        )
    )
    _assert_post_kill_apply_lock(
        runtime_root=fixture.profile.runtime_root,
        oracle=oracle,
    )

    invocation_path = prepared.run_root / "receipts/apply_invocation.json"
    invocation = load_apply_invocation(invocation_path)
    assert invocation.apply_attempt_id == attempt_id
    assert invocation.content_sha256 == interrupted.apply_invocation_sha256
    assert tuple(prepared.run_root.rglob("apply_invocation.json")) == (invocation_path,)
    invocation_before_resume = _file_fingerprint(invocation_path)
    assert invocation_before_resume is not None
    admission = load_runtime_live_attempt_admission()
    assert admission is not None
    assert admission.apply_attempt_id == attempt_id
    publication_at_kill = _physical_tree(output_root)
    publication_transactions_at_kill = _publication_transaction_snapshot(output_root)
    assert len(publication_transactions_at_kill) == 1

    resume_oracle_path = prepared.run_root.parent / f"atomic-{case.name}-resume.json"
    selected = _selected_initial_journal_cursor(
        interrupted,
        cursor_stage=case.cursor_stage,
    )
    assert selected is not None
    _, interrupted_external = selected
    expected_bound = (
        None
        if case.cursor_stage == "PLANNED"
        else {
            "identity": interrupted_external["staging_identity"],
            "size": interrupted_external["staging_size"],
            "sha256": interrupted_external["staging_sha256"],
        }
    )
    _spawn_and_join(
        target=_observed_public_resume_worker,
        args=(
            str(prepared.run_root),
            attempt_id,
            str(final_path),
            str(staging_path),
            str(inner_path),
            case.cursor_stage,
            json.dumps(expected_bound),
            str(resume_oracle_path),
        ),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    resume_oracle = json.loads(resume_oracle_path.read_bytes())
    resume_events = ["initial_prepared_journal_committed_before_cursor_cas"]
    if case.requires_unbound_retirement:
        resume_events = [
            "unbound_residue_retired_before_cursor_cas",
            "fresh_inner_created_after_retirement",
            "fresh_staging_bound_before_cursor_cas",
            *resume_events,
        ]
    assert resume_oracle.pop("events") == resume_events
    assert resume_oracle.pop("apply_entry_counts") == _expected_apply_entry_counts(
        recovery=1
    )
    assert resume_oracle["status"] == "LIVE_AND_MATCHED"

    terminal = _assert_final_state(
        fixture=fixture,
        session_root=prepared.run_root,
        frozen_identity=frozen,
        output_root=output_root,
        publication_at_kill=publication_at_kill,
        publication_transactions_at_kill=publication_transactions_at_kill,
        profile_before=profile_before,
        expected_attempt_id=attempt_id,
        expected_owner_id=None,
        prior_owner_state=None,
    )
    assert resume_oracle["session_sha256"] == terminal.content_sha256
    assert terminal.runtime_layout_bootstrap["apply_attempt_id"] == attempt_id
    assert terminal.result_intent["apply_attempt_id"] == attempt_id
    assert terminal.attempt_acknowledgement["apply_attempt_id"] == attempt_id
    owners = load_runtime_transaction_journals(fixture.profile.runtime_root)
    assert len(owners) == 1
    assert owners[0].transaction_id == attempt_id
    assert owners[0].phase is RuntimeTransactionPhase.FINALIZED
    terminal_invocation = load_apply_invocation(invocation_path)
    assert terminal_invocation.apply_attempt_id == attempt_id
    assert terminal_invocation.content_sha256 == terminal.apply_invocation_sha256
    assert _file_fingerprint(invocation_path) == invocation_before_resume
    terminal_state = _terminal_snapshot(
        session_root=prepared.run_root,
        runtime_root=fixture.profile.runtime_root,
        output_root=output_root,
    )

    replay_oracle_path = prepared.run_root.parent / f"atomic-{case.name}-replay.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(replay_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    replay_oracle = json.loads(replay_oracle_path.read_bytes())
    assert replay_oracle.pop("apply_entry_counts") == _expected_apply_entry_counts()
    assert replay_oracle == resume_oracle
    replayed = _assert_final_state(
        fixture=fixture,
        session_root=prepared.run_root,
        frozen_identity=frozen,
        output_root=output_root,
        publication_at_kill=publication_at_kill,
        publication_transactions_at_kill=publication_transactions_at_kill,
        profile_before=profile_before,
        expected_attempt_id=attempt_id,
        expected_owner_id=None,
        prior_owner_state=None,
    )
    assert replayed.content_sha256 == terminal.content_sha256
    assert load_apply_invocation(invocation_path) == terminal_invocation
    assert (
        _terminal_snapshot(
            session_root=prepared.run_root,
            runtime_root=fixture.profile.runtime_root,
            output_root=output_root,
        )
        == terminal_state
    )


@pytest.mark.parametrize("case", _CASES, ids=[case.name for case in _CASES])
def test_first_new_target_prepared_journal_atomic_hard_kills_resume_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: _AtomicJournalCase,
) -> None:
    if case.posix_only and os.name != "posix":
        pytest.skip("the link-before-unlink boundary exists only on POSIX")
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / case.name, monkeypatch)
    _exercise_atomic_journal_hard_kill(
        fixture=fixture,
        prepared=prepared,
        case=case,
    )
