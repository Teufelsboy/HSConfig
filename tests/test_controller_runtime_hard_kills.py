from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
from typing import Any

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig import output_publisher as publisher
from hsconfig.apply_invocation import load_apply_invocation
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.operator_profile import derive_deck_output_binding, operator_profile_path
from hsconfig.output_operation_admission import (
    output_operation_admission_path,
    output_operation_admission_reserved_temp_path,
    output_operation_admission_staging_path,
)
from hsconfig.output_publisher import output_child_claim_path
from hsconfig.package_io import path_identity
from hsconfig.runtime_live_admission import load_runtime_live_attempt_admission
from hsconfig.runtime_transaction_journal import (
    RuntimeTransactionPhase,
    load_runtime_transaction_journals,
    runtime_transaction_journal_path,
)
from tests.test_codex_first_live_e2e import (
    _local_state,
    _matched_package,
    _prepare_approved,
)
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


@dataclass(frozen=True, slots=True)
class _RuntimeCase:
    fault: LiveStartFaultPoint
    occurrence: int = 1
    layout_role: str | None = None
    route: str = "new_target"


@dataclass(frozen=True, slots=True)
class _PriorOwnerState:
    owner_id: str
    owner_journal_path: Path
    owner_journal_fingerprint: tuple[tuple[int, int, int], int, str]
    target_path: Path
    target_identity: tuple[int, int, int]
    target_tree: dict[str, object]
    current_path: Path
    current_fingerprint: tuple[tuple[int, int, int], int, str]
    current_value: dict[str, object]
    transaction_id: str
    revision: str


_LAYOUT_CASES = tuple(
    _RuntimeCase(
        LiveStartFaultPoint.AFTER_RUNTIME_LAYOUT_DIRECTORY_CREATE_BEFORE_RECEIPT_CAS,
        occurrence=index,
        layout_role=role,
    )
    for index, role in enumerate(session.RUNTIME_LAYOUT_DIRECTORY_ROLES, start=1)
)

_INITIAL_RUNTIME_CASES = (
    _RuntimeCase(LiveStartFaultPoint.AFTER_RUNTIME_JOURNAL_CREATED),
    _RuntimeCase(
        LiveStartFaultPoint.AFTER_RUNTIME_CANDIDATE_JOURNAL_BOUND_BEFORE_CANDIDATE_CREATE
    ),
    _RuntimeCase(
        LiveStartFaultPoint.AFTER_RUNTIME_CANDIDATE_CREATE_BEFORE_CANDIDATE_IDENTITY_RECEIPT_CAS
    ),
)

_COMMITTED_CASES = (
    _RuntimeCase(LiveStartFaultPoint.AFTER_PHYSICAL_COMMIT_BEFORE_INSTALLER_RETURN),
    _RuntimeCase(
        LiveStartFaultPoint.AFTER_INSTALLER_RETURN_BEFORE_APPLY_COMMITTED,
        route="prior_owner",
    ),
)


def _tree_projection(
    root: Path,
    *,
    held_lock_path: Path | None = None,
) -> dict[str, dict[str, object]]:
    if not root.exists():
        return {}
    paths = (root, *sorted(root.rglob("*")))
    result: dict[str, dict[str, object]] = {}
    for path in paths:
        relative = "." if path == root else path.relative_to(root).as_posix()
        status = path.lstat()
        identity = list(path_identity(path))
        if stat.S_ISDIR(status.st_mode):
            result[relative] = {"kind": "directory", "identity": identity}
        elif stat.S_ISREG(status.st_mode):
            row: dict[str, object] = {
                "kind": "file",
                "identity": identity,
                "size": status.st_size,
            }
            if held_lock_path is None or path != held_lock_path:
                raw = path.read_bytes()
                row["sha256"] = _sha256_bytes(raw)
            else:
                assert status.st_nlink == 1
                assert status.st_size == 0
                row["sha256"] = None
            result[relative] = row
        else:
            result[relative] = {"kind": "unsafe", "identity": identity}
    return result


def _publication_transaction_snapshot(
    output_root: Path,
) -> dict[str, dict[str, object]]:
    if not output_root.is_dir():
        return {}
    loaded = publisher._load_valid_transactions(output_root)
    return {
        transaction.transaction_id: {
            "path": path.relative_to(output_root).as_posix(),
            "identity": loaded.identities[path],
            "fingerprint": _file_fingerprint(path),
            "phase": transaction.phase,
            "revision": transaction.revision,
            "owns_revision": transaction.owns_revision,
        }
        for path, transaction in loaded
    }


def _assert_post_kill_apply_lock(
    *,
    runtime_root: Path,
    oracle: Mapping[str, object],
) -> None:
    runtime_tree = oracle["runtime_tree"]
    assert isinstance(runtime_tree, Mapping)
    lock_row = runtime_tree[".hsconfig/apply.lock"]
    assert isinstance(lock_row, Mapping)
    assert lock_row["kind"] == "file"
    assert lock_row["size"] == 0
    assert lock_row["sha256"] is None
    assert _file_fingerprint(runtime_root / ".hsconfig/apply.lock") == (
        tuple(lock_row["identity"]),
        0,
        _sha256_bytes(b""),
    )


def _assert_prior_owner_runtime(state: _PriorOwnerState) -> None:
    assert _file_fingerprint(state.owner_journal_path) == (
        state.owner_journal_fingerprint
    )
    assert path_identity(state.target_path) == state.target_identity
    assert _physical_tree(state.target_path) == state.target_tree


def _assert_prior_publication_replaced(
    *,
    current: session.LiveStartSession,
    output_root: Path,
    state: _PriorOwnerState,
) -> None:
    publication = current.publication_binding
    assert isinstance(publication, Mapping)
    assert (
        tuple(publication["prior_current_identity"]) == (state.current_fingerprint[0])
    )
    current_value = json.loads(state.current_path.read_bytes())
    current_fingerprint = _file_fingerprint(state.current_path)
    assert current_fingerprint is not None
    assert current_fingerprint != state.current_fingerprint
    assert current_value != state.current_value
    assert current_value["revision"] != state.revision
    assert current_value["revision"] == publication["revision"]
    assert (
        "sha256:" + str(current_value["content_root_sha256"])
        == (publication["content_root_sha256"])
    )

    transactions = publisher._load_valid_transactions(output_root)
    assert len(transactions) == 1
    transaction_path, transaction = transactions[0]
    assert transaction.transaction_id != state.transaction_id
    assert transaction.phase == "finalized"
    assert transaction.owns_revision is True
    assert transaction.revision == current_value["revision"]
    assert transaction.content_root_sha256 == current_value["content_root_sha256"]
    receipt = transaction.live_start_commit_receipt
    assert receipt is not None
    assert receipt.pointer_predecessor_identity == state.current_fingerprint[0]
    assert receipt.pointer_predecessor_size == state.current_fingerprint[1]
    assert receipt.pointer_predecessor_sha256 == state.current_fingerprint[2]
    assert _file_fingerprint(transaction_path) is not None
    assert not (transaction_path.parent / f"{state.transaction_id}.json").exists()
    assert not (output_root / state.revision).exists()


def _runtime_hard_kill_worker(
    session_root_text: str,
    fault_value: str,
    occurrence: int,
    oracle_path_text: str,
) -> None:
    session_root = Path(session_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    selected = LiveStartFaultPoint(fault_value)
    seen = 0
    apply_entry_counts, previous_profile = _start_apply_entry_observer()

    def hard_kill(point: LiveStartFaultPoint) -> None:
        nonlocal seen
        if point is not selected:
            return
        seen += 1
        if seen != occurrence:
            return
        session_path = session_root / "session.json"
        persisted = session._load_session_bytes(
            session_path.read_bytes(),
            session_identity=path_identity(session_path),
        )
        layout = persisted.runtime_layout_bootstrap
        assert isinstance(layout, Mapping)
        runtime_root = Path(str(layout["runtime_root"]))
        lock_path = runtime_root / ".hsconfig" / "apply.lock"
        recovery = persisted.apply_recovery
        candidate_identity = None
        if isinstance(recovery, Mapping) and recovery.get("candidate_path") is not None:
            candidate_path = Path(str(recovery["candidate_path"]))
            if candidate_path.is_dir():
                candidate_identity = path_identity(candidate_path)
        current_layout_identity = None
        if (
            point
            is LiveStartFaultPoint.AFTER_RUNTIME_LAYOUT_DIRECTORY_CREATE_BEFORE_RECEIPT_CAS
        ):
            current_row = layout["directories"][layout["next_directory_index"]]
            current_layout_identity = path_identity(Path(str(current_row["path"])))
        _persist_worker_oracle(
            Path(oracle_path_text),
            {
                "fault_value": point.value,
                "occurrence": seen,
                "session": persisted.to_value(),
                "apply_entry_counts": apply_entry_counts,
                "runtime_tree": _tree_projection(
                    runtime_root,
                    held_lock_path=lock_path,
                ),
                "candidate_identity": candidate_identity,
                "current_layout_identity": current_layout_identity,
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
        import sys

        sys.setprofile(previous_profile)
    os._exit(94)


def _assert_physical_runtime_admission(current: session.LiveStartSession) -> None:
    pending = current.pending_transition
    if (
        isinstance(pending, Mapping)
        and pending.get("runtime_admission_identity") is not None
    ):
        path = Path(str(pending["runtime_admission_path"]))
        expected = (
            tuple(pending["runtime_admission_identity"]),
            pending["runtime_admission_document_size"],
            pending["runtime_admission_sha256"],
        )
        assert _file_fingerprint(path) == expected
    else:
        binding = current.runtime_admission_binding
        assert isinstance(binding, Mapping)
        path = Path(str(binding["admission_path"]))
        fingerprint = _file_fingerprint(path)
        assert fingerprint is not None
        assert (fingerprint[0], fingerprint[2]) == (
            tuple(binding["admission_identity"]),
            binding["admission_sha256"],
        )
        assert path_identity(path.parent) == tuple(binding["admission_parent_identity"])


def _assert_complete_layout(current: session.LiveStartSession) -> None:
    layout = current.runtime_layout_bootstrap
    assert isinstance(layout, Mapping)
    assert layout["stage"] == "COMPLETE"
    assert layout["next_directory_index"] == layout["directory_count"] == 7
    assert tuple(row["role"] for row in layout["directories"]) == (
        session.RUNTIME_LAYOUT_DIRECTORY_ROLES
    )
    for row in layout["directories"]:
        path = Path(str(row["path"]))
        assert path.is_dir()
        assert path_identity(path) == tuple(row["successor_identity"])


def _assert_layout_interruption(
    current: session.LiveStartSession,
    oracle: dict[str, object],
    case: _RuntimeCase,
) -> None:
    assert current.phase.value == "PUBLICATION_COMMITTED"
    pending = current.pending_transition
    assert isinstance(pending, Mapping)
    assert pending["operation"] == "install_apply_invocation"
    assert pending["stage"] == "PRIMARY_APPLIED"
    assert pending["next_action_index"] == 0
    assert pending["external_file_action"] is None
    assert current.apply_invocation_sha256 is None
    assert current.runtime_admission_binding is None
    assert current.apply_recovery is None
    _assert_physical_runtime_admission(current)

    layout = current.runtime_layout_bootstrap
    assert isinstance(layout, Mapping)
    assert layout["stage"] == "INCOMPLETE"
    assert layout["next_directory_index"] == case.occurrence - 1
    assert layout["directory_count"] == 7
    rows = layout["directories"]
    assert tuple(row["role"] for row in rows) == session.RUNTIME_LAYOUT_DIRECTORY_ROLES
    current_index = case.occurrence - 1
    assert rows[current_index]["role"] == case.layout_role
    assert rows[current_index]["predecessor_state"] == "absent"
    assert rows[current_index]["predecessor_identity"] is None
    assert rows[current_index]["successor_identity"] is None
    captured_identity = tuple(oracle["current_layout_identity"])
    current_path = Path(str(rows[current_index]["path"]))
    assert path_identity(current_path) == captured_identity
    assert not tuple(current_path.iterdir())
    for index, row in enumerate(rows):
        path = Path(str(row["path"]))
        if index < current_index:
            assert path_identity(path) == tuple(row["successor_identity"])
        elif index > current_index:
            assert not path.exists()

    runtime_root = Path(str(layout["runtime_root"]))
    expected_paths = {".", ".hsconfig", ".hsconfig/apply.lock"}
    expected_paths.update(
        Path(str(row["path"])).relative_to(runtime_root).as_posix()
        for row in rows[: case.occurrence]
    )
    runtime_tree = oracle["runtime_tree"]
    assert isinstance(runtime_tree, Mapping)
    assert set(runtime_tree) == expected_paths
    assert runtime_tree[".hsconfig/apply.lock"]["size"] == 0
    assert runtime_tree[".hsconfig/apply.lock"]["sha256"] is None
    output_operation = current.output_operation_admission_binding
    assert isinstance(output_operation, Mapping)
    session_root = Path(str(output_operation["session_root"]))
    assert not (session_root / "receipts/apply_invocation.json").exists()
    assert output_operation_admission_path().is_file()


def _assert_initial_runtime_interruption(
    current: session.LiveStartSession,
    oracle: dict[str, object],
    case: _RuntimeCase,
) -> None:
    assert current.phase.value == "APPLY_STARTED"
    assert current.pending_transition is None
    assert current.apply_invocation_sha256 is not None
    assert isinstance(current.runtime_admission_binding, Mapping)
    assert current.closed_apply_recovery_commitment is None
    assert current.result_intent is None
    assert current.attempt_acknowledgement is None
    assert current.terminal_retirement is None
    _assert_physical_runtime_admission(current)
    _assert_complete_layout(current)
    assert not output_operation_admission_path().exists()

    recovery = current.apply_recovery
    assert isinstance(recovery, Mapping)
    assert recovery["recovery_stage"] == "ACTIVE"
    assert recovery["install_route"] == "new_target"
    assert recovery["runtime_match_status"] == "not_run"
    assert recovery["stable_physical_disposition"] is None
    assert recovery["run_id"] == current.run_id
    assert (
        recovery["apply_attempt_id"]
        == current.runtime_layout_bootstrap["apply_attempt_id"]
    )
    assert recovery["apply_invocation_sha256"] == current.apply_invocation_sha256
    assert recovery["deck_config_ini_sha256"] is None
    assert recovery["runtime_state_sha256"] is None
    assert recovery["last_apply_receipt_sha256"] is None
    assert recovery["successor_renamed_target_identity"] is None

    fence_path = Path(str(recovery["successor_attempt_record_path"]))
    fence_raw = fence_path.read_bytes()
    fence = json.loads(fence_raw)
    assert fence["state"] == "CANDIDATE_PLANNED"
    assert fence["candidate_identity"] is None
    assert _file_fingerprint(fence_path) == (
        tuple(recovery["successor_attempt_record_identity"]),
        len(fence_raw),
        recovery["successor_attempt_record_sha256"],
    )
    candidate_path = Path(str(recovery["candidate_path"]))

    if case.fault is LiveStartFaultPoint.AFTER_RUNTIME_JOURNAL_CREATED:
        external = recovery["external_file_action"]
        assert isinstance(external, Mapping)
        assert recovery["expected_action"] == (
            "advance_controller_transaction_journal_write"
        )
        assert external["stage"] == "STAGING_BOUND"
        assert external["action_kind"] == (
            "advance_controller_transaction_journal_write"
        )
        assert external["commit_mode"] == "create_no_replace"
        assert external["final_path"] == recovery["planned_journal_successor_path"]
        assert recovery["planned_journal_successor_phase"] == "PREPARED"
        assert recovery["successor_journal_path"] is None
        assert recovery["successor_journal_identity"] is None
        assert recovery["successor_journal_sha256"] is None
        journal_path = Path(str(external["final_path"]))
        journal_raw = journal_path.read_bytes()
        assert (
            json.loads(journal_raw)["phase"] == RuntimeTransactionPhase.PREPARED.value
        )
        assert len(journal_raw) == recovery["planned_journal_successor_size"]
        assert (
            _sha256_bytes(journal_raw) == recovery["planned_journal_successor_sha256"]
        )
        assert path_identity(journal_path) == tuple(external["staging_identity"])
        assert not candidate_path.exists()
    else:
        assert recovery["expected_action"] == "bind_created_candidate"
        assert recovery["external_file_action"] is None
        assert recovery["planned_journal_successor_path"] is None
        assert recovery["planned_journal_successor_parent_identity"] is None
        assert recovery["planned_journal_successor_sha256"] is None
        assert recovery["successor_candidate_identity"] is None
        journal_path = Path(str(recovery["successor_journal_path"]))
        journal_raw = journal_path.read_bytes()
        assert (
            json.loads(journal_raw)["phase"] == RuntimeTransactionPhase.PREPARED.value
        )
        assert _file_fingerprint(journal_path) == (
            tuple(recovery["successor_journal_identity"]),
            len(journal_raw),
            recovery["successor_journal_sha256"],
        )
        if (
            case.fault
            is LiveStartFaultPoint.AFTER_RUNTIME_CANDIDATE_JOURNAL_BOUND_BEFORE_CANDIDATE_CREATE
        ):
            assert not candidate_path.exists()
            assert oracle["candidate_identity"] is None
        else:
            assert candidate_path.is_dir()
            assert not tuple(candidate_path.iterdir())
            assert path_identity(candidate_path) == tuple(oracle["candidate_identity"])

    runtime_root = Path(str(recovery["runtime_root"]))
    assert not (runtime_root / "CustomConfig/deck_config.ini").exists()
    assert not (runtime_root / ".hsconfig/state.json").exists()
    assert not tuple((runtime_root / ".hsconfig/receipts").rglob("*.json"))
    runtime_tree = oracle["runtime_tree"]
    assert isinstance(runtime_tree, Mapping)
    layout = current.runtime_layout_bootstrap
    assert isinstance(layout, Mapping)
    expected_paths = {".", ".hsconfig", ".hsconfig/apply.lock"}
    expected_paths.update(
        Path(str(row["path"])).relative_to(runtime_root).as_posix()
        for row in layout["directories"]
    )
    expected_paths.add(fence_path.relative_to(runtime_root).as_posix())
    expected_paths.add(journal_path.relative_to(runtime_root).as_posix())
    if (
        case.fault
        is LiveStartFaultPoint.AFTER_RUNTIME_CANDIDATE_CREATE_BEFORE_CANDIDATE_IDENTITY_RECEIPT_CAS
    ):
        expected_paths.add(candidate_path.relative_to(runtime_root).as_posix())
    assert set(runtime_tree) == expected_paths


def _assert_committed_interruption(
    current: session.LiveStartSession,
    case: _RuntimeCase,
    expected_owner_id: str | None,
) -> tuple[str, Path, Path]:
    assert current.phase.value == "APPLY_STARTED"
    assert current.pending_transition is None
    assert current.apply_invocation_sha256 is not None
    assert isinstance(current.runtime_admission_binding, Mapping)
    assert current.closed_apply_recovery_commitment is None
    assert current.result_intent is None
    assert current.attempt_acknowledgement is None
    assert current.terminal_retirement is None
    _assert_physical_runtime_admission(current)
    _assert_complete_layout(current)
    recovery = current.apply_recovery
    assert isinstance(recovery, Mapping)
    assert recovery["recovery_stage"] == "ACTIVE"
    assert recovery["install_route"] == case.route
    assert recovery["expected_action"] is None
    assert recovery["stable_physical_disposition"] == "COMMITTED"
    assert recovery["runtime_match_status"] == "unknown"
    assert recovery["runtime_match_sha256"] is None
    assert recovery["deck_config_ini_sha256"] is not None
    assert recovery["runtime_state_sha256"] is not None
    assert recovery["last_apply_receipt_sha256"] is not None

    attempt_id = str(recovery["apply_attempt_id"])
    runtime_root = Path(str(recovery["runtime_root"]))
    for family in ("attempt_record", "journal"):
        for field in ("path", "identity", "sha256"):
            assert recovery[f"successor_{family}_{field}"] is None
    attempt_path = Path(str(recovery["predecessor_attempt_record_path"]))
    assert attempt_path == (
        runtime_root / ".hsconfig/attempt-retention" / f"{attempt_id}.json"
    )
    assert _file_fingerprint(attempt_path) == (
        tuple(recovery["predecessor_attempt_record_identity"]),
        attempt_path.stat().st_size,
        recovery["predecessor_attempt_record_sha256"],
    )
    journals = {
        journal.transaction_id: journal
        for journal in load_runtime_transaction_journals(runtime_root)
    }
    attempt = journals[attempt_id]
    assert attempt.phase is RuntimeTransactionPhase.FINALIZED
    assert attempt.owns_target is (case.route == "new_target")
    attempt_journal_path = runtime_transaction_journal_path(runtime_root, attempt_id)
    assert str(attempt_journal_path) == recovery["predecessor_journal_path"]
    assert _file_fingerprint(attempt_journal_path) == (
        tuple(recovery["predecessor_journal_identity"]),
        attempt_journal_path.stat().st_size,
        recovery["predecessor_journal_sha256"],
    )
    target_path = runtime_root / attempt.target_path
    assert target_path.is_dir()
    assert path_identity(target_path) == tuple(attempt.target_identity)
    if case.route == "prior_owner":
        assert expected_owner_id is not None
        assert set(journals) == {attempt_id, expected_owner_id}
        owner = journals[expected_owner_id]
        assert owner.phase is RuntimeTransactionPhase.FINALIZED
        assert owner.owns_target is True
        assert owner.target_path == attempt.target_path
        assert owner.target_identity == attempt.target_identity
    else:
        assert expected_owner_id is None
        assert set(journals) == {attempt_id}
    return attempt_id, attempt_path, attempt_journal_path


def _assert_final_state(
    *,
    fixture: Any,
    session_root: Path,
    frozen_identity: dict[str, object],
    output_root: Path,
    publication_at_kill: dict[str, object],
    publication_transactions_at_kill: dict[str, dict[str, object]],
    profile_before: tuple[tuple[int, int, int], int, str],
    expected_attempt_id: str,
    expected_owner_id: str | None,
    prior_owner_state: _PriorOwnerState | None,
) -> session.LiveStartSession:
    terminal = session.load_live_start_session(
        session_root,
        local_app_data_root=session_root.parents[2],
    )
    assert terminal.terminal_status == "LIVE_AND_MATCHED"
    assert _frozen_identity(terminal) == frozen_identity
    assert terminal.pending_transition is None
    assert terminal.apply_recovery is None
    assert isinstance(terminal.output_child_binding, Mapping)
    assert isinstance(terminal.runtime_layout_bootstrap, Mapping)
    assert isinstance(terminal.result_intent, Mapping)
    assert isinstance(terminal.terminal_retirement, Mapping)
    assert isinstance(terminal.attempt_acknowledgement, Mapping)
    _assert_complete_layout(terminal)
    assert terminal.output_child_binding["claim_state"] == "RETIRED"
    assert terminal.runtime_layout_bootstrap["apply_attempt_id"] == expected_attempt_id
    assert terminal.result_intent["apply_attempt_id"] == expected_attempt_id
    assert terminal.terminal_retirement["apply_attempt_id"] == expected_attempt_id
    assert terminal.attempt_acknowledgement["apply_attempt_id"] == expected_attempt_id
    assert _file_fingerprint(operator_profile_path()) == profile_before
    assert _physical_tree(output_root) == publication_at_kill
    assert (
        _publication_transaction_snapshot(output_root)
        == publication_transactions_at_kill
    )

    invocation_path = session_root / "receipts/apply_invocation.json"
    invocation = load_apply_invocation(invocation_path)
    assert invocation.apply_attempt_id == expected_attempt_id
    assert invocation.content_sha256 == terminal.apply_invocation_sha256

    _output, package, runtime_target = _matched_package(fixture)
    journals = load_runtime_transaction_journals(fixture.profile.runtime_root)
    owners = [
        journal
        for journal in journals
        if journal.owns_target
        and fixture.profile.runtime_root / journal.target_path == runtime_target
    ]
    assert len(journals) == len(owners) == 1
    assert owners[0].phase is RuntimeTransactionPhase.FINALIZED
    if expected_owner_id is not None:
        assert owners[0].transaction_id == expected_owner_id
        assert owners[0].transaction_id != expected_attempt_id
        assert prior_owner_state is not None
        assert prior_owner_state.owner_id == expected_owner_id
        _assert_prior_owner_runtime(prior_owner_state)
        _assert_prior_publication_replaced(
            current=terminal,
            output_root=output_root,
            state=prior_owner_state,
        )
    else:
        assert owners[0].transaction_id == expected_attempt_id
        assert prior_owner_state is None
    assert path_identity(runtime_target) == tuple(owners[0].target_identity)
    target_directories = tuple(
        path
        for path in (fixture.profile.runtime_root / "CustomConfig").iterdir()
        if path.is_dir()
    )
    assert target_directories == (runtime_target,)
    runtime_root = fixture.profile.runtime_root
    owner = owners[0]
    expected_kinds = dict.fromkeys(
        (
            ".",
            "CustomConfig",
            ".hsconfig",
            ".hsconfig/transactions",
            ".hsconfig/staging",
            ".hsconfig/receipts",
            f".hsconfig/receipts/{owner.state_key}",
            ".hsconfig/attempt-retention",
            ".hsconfig/owner-retirements",
        ),
        "directory",
    )
    expected_kinds.update(
        dict.fromkeys(
            (
                "CustomConfig/deck_config.ini",
                ".hsconfig/apply.lock",
                ".hsconfig/state.json",
                f".hsconfig/transactions/{owner.transaction_id}.json",
                f".hsconfig/receipts/{owner.state_key}/last_apply_receipt.json",
            ),
            "file",
        )
    )
    package_config = package / "CustomConfig" / owner.logical_config_dir
    package_tree = _tree_projection(package_config)
    assert package_tree["."]["kind"] == "directory"
    target_relative = runtime_target.relative_to(runtime_root).as_posix()
    for relative, row in package_tree.items():
        assert row["kind"] in {"directory", "file"}
        target_member = (
            target_relative if relative == "." else f"{target_relative}/{relative}"
        )
        expected_kinds[target_member] = row["kind"]
    final_tree = _tree_projection(runtime_root)
    assert {relative: row["kind"] for relative, row in final_tree.items()} == (
        expected_kinds
    )
    assert final_tree[".hsconfig/apply.lock"]["size"] == 0
    assert final_tree[".hsconfig/apply.lock"]["sha256"] == _sha256_bytes(b"")
    assert not tuple((fixture.profile.runtime_root / ".hsconfig/staging").iterdir())
    assert not tuple(
        (fixture.profile.runtime_root / ".hsconfig/attempt-retention").iterdir()
    )
    assert not output_operation_admission_path().exists()
    assert not output_operation_admission_staging_path().exists()
    assert not output_operation_admission_reserved_temp_path().exists()
    assert not output_child_claim_path(output_root).exists()
    assert load_runtime_live_attempt_admission() is None
    assert not tuple(session_root.parents[2].rglob("*.staged"))
    assert not tuple(session_root.parents[2].rglob("*.live-start-atomic.tmp"))
    return terminal


def _exercise_runtime_hard_kill(
    *,
    fixture: Any,
    prepared: Any,
    case: _RuntimeCase,
    expected_owner_id: str | None = None,
    prior_owner_state: _PriorOwnerState | None = None,
) -> None:
    approved = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    frozen = _frozen_identity(approved)
    profile_before = _file_fingerprint(operator_profile_path())
    assert profile_before is not None
    output_root = derive_deck_output_binding(
        fixture.profile, fixture.deck_name
    ).output_root
    if prior_owner_state is None:
        assert _publication_transaction_snapshot(output_root) == {}
    else:
        assert prior_owner_state.current_path == output_root / "current.json"
        assert _file_fingerprint(prior_owner_state.current_path) == (
            prior_owner_state.current_fingerprint
        )
        assert json.loads(prior_owner_state.current_path.read_bytes()) == (
            prior_owner_state.current_value
        )
    oracle_path = prepared.run_root.parent / "runtime-hard-kill-oracle.json"
    _spawn_and_join(
        target=_runtime_hard_kill_worker,
        args=(
            str(prepared.run_root),
            case.fault.value,
            case.occurrence,
            str(oracle_path),
        ),
        expected_exitcode=93,
        timeout_seconds=360,
    )
    oracle = json.loads(oracle_path.read_bytes())
    assert oracle.pop("fault_value") == case.fault.value
    assert oracle.pop("occurrence") == case.occurrence
    kill_counts = oracle.pop("apply_entry_counts")
    assert kill_counts == _expected_apply_entry_counts(
        fresh=1,
        install_prepare=1,
        attempt_prepare=1,
    )
    interrupted = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    assert oracle["session"] == interrupted.to_value()
    assert _frozen_identity(interrupted) == frozen
    assert _file_fingerprint(operator_profile_path()) == profile_before
    publication_at_kill = _physical_tree(output_root)
    publication_transactions_at_kill = _publication_transaction_snapshot(output_root)
    assert len(publication_transactions_at_kill) == 1

    interrupted_layout = interrupted.runtime_layout_bootstrap
    assert isinstance(interrupted_layout, Mapping)
    expected_attempt_id = str(interrupted_layout["apply_attempt_id"])
    physical_admission = load_runtime_live_attempt_admission()
    assert physical_admission is not None
    assert physical_admission.apply_attempt_id == expected_attempt_id
    _assert_post_kill_apply_lock(
        runtime_root=fixture.profile.runtime_root,
        oracle=oracle,
    )
    if prior_owner_state is not None:
        _assert_prior_owner_runtime(prior_owner_state)
        _assert_prior_publication_replaced(
            current=interrupted,
            output_root=output_root,
            state=prior_owner_state,
        )
    invocation_path = prepared.run_root / "receipts/apply_invocation.json"
    if invocation_path.is_file():
        interrupted_invocation = load_apply_invocation(invocation_path)
        assert interrupted_invocation.apply_attempt_id == expected_attempt_id
        assert (
            interrupted_invocation.content_sha256 == interrupted.apply_invocation_sha256
        )
    else:
        pending = interrupted.pending_transition
        assert isinstance(pending, Mapping)
        assert pending["apply_attempt_id"] == expected_attempt_id

    committed_paths: tuple[str, Path, Path] | None = None
    prior_layout_identities: tuple[tuple[int, int, int], ...] = ()
    if case.layout_role is not None:
        _assert_layout_interruption(interrupted, oracle, case)
        rows = interrupted.runtime_layout_bootstrap["directories"]
        prior_layout_identities = tuple(
            tuple(row["successor_identity"]) for row in rows[: case.occurrence - 1]
        )
    elif case.fault in {row.fault for row in _INITIAL_RUNTIME_CASES}:
        _assert_initial_runtime_interruption(interrupted, oracle, case)
    else:
        committed_paths = _assert_committed_interruption(
            interrupted,
            case,
            expected_owner_id,
        )

    resume_oracle_path = prepared.run_root.parent / "runtime-resume-oracle.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(resume_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    resume_oracle = json.loads(resume_oracle_path.read_bytes())
    resume_counts = resume_oracle.pop("apply_entry_counts")
    assert resume_counts == (
        _expected_apply_entry_counts(recovery=1, install_prepare=1)
        if case.layout_role is not None
        else _expected_apply_entry_counts(recovery=1)
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
        expected_attempt_id=expected_attempt_id,
        expected_owner_id=expected_owner_id,
        prior_owner_state=prior_owner_state,
    )
    assert resume_oracle["session_sha256"] == terminal.content_sha256

    if case.layout_role is not None:
        _assert_complete_layout(terminal)
        terminal_rows = terminal.runtime_layout_bootstrap["directories"]
        assert (
            tuple(
                tuple(row["successor_identity"])
                for row in terminal_rows[: case.occurrence - 1]
            )
            == prior_layout_identities
        )
        assert tuple(terminal_rows[case.occurrence - 1]["successor_identity"]) == tuple(
            oracle["current_layout_identity"]
        )
    elif (
        case.fault
        is LiveStartFaultPoint.AFTER_RUNTIME_CANDIDATE_CREATE_BEFORE_CANDIDATE_IDENTITY_RECEIPT_CAS
    ):
        owner = load_runtime_transaction_journals(fixture.profile.runtime_root)[0]
        assert tuple(owner.target_identity) == tuple(oracle["candidate_identity"])

    if committed_paths is not None:
        attempt_id, attempt_path, attempt_journal_path = committed_paths
        expected_tree = dict(oracle["runtime_tree"])
        del expected_tree[
            attempt_path.relative_to(fixture.profile.runtime_root).as_posix()
        ]
        if case.route == "prior_owner":
            del expected_tree[
                attempt_journal_path.relative_to(
                    fixture.profile.runtime_root
                ).as_posix()
            ]
            assert attempt_id != expected_owner_id
        final_tree = _tree_projection(fixture.profile.runtime_root)
        final_tree[".hsconfig/apply.lock"]["sha256"] = None
        assert final_tree == expected_tree

    terminal_bytes = {
        "session": (prepared.run_root / "session.json").read_bytes(),
        "summary_json": (prepared.run_root / "result/summary.json").read_bytes(),
        "summary_markdown": (prepared.run_root / "result/summary.md").read_bytes(),
        "runtime": _physical_tree(fixture.profile.runtime_root),
        "publication": _physical_tree(output_root),
    }
    replay_oracle_path = prepared.run_root.parent / "runtime-replay-oracle.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(replay_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    replay_oracle = json.loads(replay_oracle_path.read_bytes())
    assert replay_oracle.pop("apply_entry_counts") == _expected_apply_entry_counts()
    assert replay_oracle == resume_oracle
    assert (prepared.run_root / "session.json").read_bytes() == terminal_bytes[
        "session"
    ]
    assert (prepared.run_root / "result/summary.json").read_bytes() == terminal_bytes[
        "summary_json"
    ]
    assert (prepared.run_root / "result/summary.md").read_bytes() == terminal_bytes[
        "summary_markdown"
    ]
    assert _physical_tree(fixture.profile.runtime_root) == terminal_bytes["runtime"]
    assert _physical_tree(output_root) == terminal_bytes["publication"]


@pytest.mark.parametrize(
    "case",
    _LAYOUT_CASES,
    ids=[case.layout_role for case in _LAYOUT_CASES],
)
def test_runtime_layout_directory_create_hard_kills_resume_each_bound_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: _RuntimeCase,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "layout", monkeypatch)
    _exercise_runtime_hard_kill(fixture=fixture, prepared=prepared, case=case)


@pytest.mark.parametrize(
    "case",
    _INITIAL_RUNTIME_CASES,
    ids=[case.fault.name.lower() for case in _INITIAL_RUNTIME_CASES],
)
def test_initial_runtime_journal_and_candidate_hard_kills_resume_same_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: _RuntimeCase,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "initial", monkeypatch)
    _exercise_runtime_hard_kill(fixture=fixture, prepared=prepared, case=case)


@pytest.mark.parametrize(
    "case",
    _COMMITTED_CASES,
    ids=("new_target_physical_commit", "prior_owner_installer_return"),
)
def test_committed_runtime_hard_kills_resume_without_second_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: _RuntimeCase,
) -> None:
    _local_state(tmp_path, monkeypatch)
    expected_owner_id = None
    prior_owner_state = None
    if case.route == "prior_owner":
        first_fixture, first = _prepare_approved(tmp_path / "first", monkeypatch)
        assert controller.finalize_live_start(session_root=first.run_root).status == (
            "LIVE_AND_MATCHED"
        )
        _output, _package, first_target = _matched_package(first_fixture)
        owners = [
            journal
            for journal in load_runtime_transaction_journals(
                first_fixture.profile.runtime_root
            )
            if journal.owns_target
            and first_fixture.profile.runtime_root / journal.target_path == first_target
        ]
        assert len(owners) == 1
        expected_owner_id = owners[0].transaction_id
        owner_journal_path = runtime_transaction_journal_path(
            first_fixture.profile.runtime_root,
            expected_owner_id,
        )
        owner_journal_fingerprint = _file_fingerprint(owner_journal_path)
        assert owner_journal_fingerprint is not None
        first_output_root = derive_deck_output_binding(
            first_fixture.profile, first_fixture.deck_name
        ).output_root
        first_transactions = publisher._load_valid_transactions(first_output_root)
        assert len(first_transactions) == 1
        _first_transaction_path, first_transaction = first_transactions[0]
        first_current_path = first_output_root / "current.json"
        first_current_fingerprint = _file_fingerprint(first_current_path)
        assert first_current_fingerprint is not None
        first_current_value = json.loads(first_current_path.read_bytes())
        assert first_transaction.revision == first_current_value["revision"]
        prior_owner_state = _PriorOwnerState(
            owner_id=expected_owner_id,
            owner_journal_path=owner_journal_path,
            owner_journal_fingerprint=owner_journal_fingerprint,
            target_path=first_target,
            target_identity=path_identity(first_target),
            target_tree=_physical_tree(first_target),
            current_path=first_current_path,
            current_fingerprint=first_current_fingerprint,
            current_value=first_current_value,
            transaction_id=first_transaction.transaction_id,
            revision=first_transaction.revision,
        )
        ini_path = first_fixture.profile.runtime_root / "CustomConfig/deck_config.ini"
        ini_path.write_text(
            "[CONFIGS]\n"
            "ShadowPriest = shadowpriest-previous\n"
            f"OtherDeck = {first_target.name}",
            encoding="utf-8",
        )
        fixture, prepared = _prepare_approved(
            tmp_path / "second",
            monkeypatch,
            profile=first_fixture.profile,
        )
    else:
        fixture, prepared = _prepare_approved(tmp_path / "new-target", monkeypatch)
    _exercise_runtime_hard_kill(
        fixture=fixture,
        prepared=prepared,
        case=case,
        expected_owner_id=expected_owner_id,
        prior_owner_state=prior_owner_state,
    )
