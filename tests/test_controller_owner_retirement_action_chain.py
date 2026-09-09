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
from hsconfig import runtime_installer as runtime_apply
from hsconfig.apply_invocation import load_apply_invocation
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.operator_profile import derive_deck_output_binding, operator_profile_path
from hsconfig.output_operation_admission import (
    output_operation_admission_path,
    output_operation_admission_reserved_temp_path,
    output_operation_admission_staging_path,
)
from hsconfig.output_publisher import output_child_claim_path
from hsconfig.package_io import (
    path_identity,
    require_no_alternate_data_streams,
    status_is_reparse,
)
from hsconfig.runtime_live_admission import load_runtime_live_attempt_admission
from hsconfig.runtime_transaction_journal import (
    RuntimeTransactionJournal,
    load_runtime_transaction_journals,
    runtime_transaction_journal_path,
)
from tests.test_codex_first_live_e2e import (
    _approve,
    _changed_candidate,
    _local_state,
    _matched_package,
    _prepare,
    _prepare_approved,
)
from tests.test_configure_prepublication_apply import (
    _file_fingerprint,
    _persist_worker_oracle,
    _physical_tree,
)
from tests.test_controller_output_hard_kills import (
    _expected_apply_entry_counts,
    _frozen_identity,
    _public_resume_worker,
    _sha256_bytes,
    _spawn_and_join,
    _start_apply_entry_observer,
)


_PRE_CAS = (
    LiveStartFaultPoint.AFTER_NONTERMINAL_RECOVERY_PHYSICAL_STEP_BEFORE_CURSOR_CAS
)
_POST_CAS = LiveStartFaultPoint.AFTER_NONTERMINAL_RECOVERY_CURSOR_CAS
_HARD_EXIT = 93
_RESULT_NAMES = ("summary.json", "summary.md")
_MATERIALIZE = "materialize_file_action_staging"
_RETIRE_STAGING = "retire_unbound_file_action_staging"


@dataclass(frozen=True, slots=True)
class _OldAuthority:
    run_root: Path
    session_fingerprint: tuple[tuple[int, int, int], int, str]
    result_pair: dict[str, tuple[tuple[int, int, int], bytes]]
    status: str
    summary_sha256: str
    session_sha256: str
    acknowledgement: dict[str, object]
    owner: RuntimeTransactionJournal
    owner_path: Path
    initial_owner_fingerprint: tuple[tuple[int, int, int], int, str]
    target_path: Path
    target_parent_identity: tuple[int, int, int]
    target_identity: tuple[int, int, int]
    target_tree: dict[str, tuple[str, tuple[int, int, int], bytes | None]]


@dataclass(frozen=True, slots=True)
class _ChainAuthority:
    frozen_identity: dict[str, object]
    attempt_id: str
    invocation_path: Path
    invocation_fingerprint: tuple[tuple[int, int, int], int, str]
    admission_binding: dict[str, object]
    admission_fingerprint: tuple[tuple[int, int, int], int, str]
    layout_binding: dict[str, object]
    operation_binding: dict[str, object]
    child_binding: dict[str, object]
    publication_binding: dict[str, object]
    profile_fingerprint: tuple[tuple[int, int, int], int, str]
    output_root: Path
    output_tree: dict[str, tuple[str, tuple[int, int, int], bytes | None]]
    attempt_path: Path
    attempt_fingerprint: tuple[tuple[int, int, int], int, str]
    owner: RuntimeTransactionJournal
    owner_path: Path
    owner_fingerprint: tuple[tuple[int, int, int], int, str]
    target_path: Path
    target_identity: tuple[int, int, int]
    target_tree: dict[str, tuple[str, tuple[int, int, int], bytes | None]]
    current_runtime: dict[Path, tuple[tuple[int, int, int], int, str]]
    runtime_baseline: dict[str, tuple[str, tuple[int, int, int], bytes | None]]


def _load_raw_session(session_root: Path) -> session.LiveStartSession:
    path = session_root / "session.json"
    raw = path.read_bytes()
    return session._load_session_bytes(raw, session_identity=path_identity(path))


def _result_pair(
    session_root: Path,
) -> dict[str, tuple[tuple[int, int, int], bytes]]:
    return {
        name: (
            path_identity(session_root / "result" / name),
            (session_root / "result" / name).read_bytes(),
        )
        for name in _RESULT_NAMES
    }


def _changed_paths(
    before: Mapping[str, object],
    after: Mapping[str, object],
) -> set[str]:
    return {
        relative
        for relative in set(before) | set(after)
        if before.get(relative) != after.get(relative)
    }


def _owner_parts(
    current: session.LiveStartSession,
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any] | None]:
    recovery = current.apply_recovery
    if not isinstance(recovery, Mapping):
        raise AssertionError("owner recovery is absent")
    owner = recovery.get("owner_retirement")
    if not isinstance(owner, Mapping):
        raise AssertionError("owner-retirement cursor is absent")
    external_raw = recovery.get("external_file_action")
    if external_raw is not None and not isinstance(external_raw, Mapping):
        raise AssertionError("external file action is invalid")
    return recovery, owner, external_raw


def _logical_owner_action(current: session.LiveStartSession) -> str:
    recovery, owner, external = _owner_parts(current)
    if (
        recovery.get("expected_action") == "observe_committed"
        and recovery.get("stable_physical_disposition") is None
        and owner.get("stage") == "OWNER_RETIRED"
        and external is None
    ):
        return "observe_committed"
    return session._owner_action_for_cursor(owner=owner, external=external)


def _has_unbound_staging(current: session.LiveStartSession) -> bool:
    _recovery, _owner, external = _owner_parts(current)
    if not isinstance(external, Mapping) or external.get("stage") != "PLANNED":
        return False
    return os.path.lexists(Path(str(external["staging_path"]))) or os.path.lexists(
        Path(str(external["inner_temp_path"]))
    )


def _effective_owner_action(current: session.LiveStartSession) -> str:
    action = _logical_owner_action(current)
    if action == _MATERIALIZE and _has_unbound_staging(current):
        return _RETIRE_STAGING
    return action


def _held_apply_lock_metadata(
    current: session.LiveStartSession,
) -> tuple[tuple[int, int, int], int]:
    layout = current.runtime_layout_bootstrap
    assert isinstance(layout, Mapping)
    lock_path = Path(str(layout["runtime_root"])) / ".hsconfig/apply.lock"
    status = lock_path.lstat()
    assert stat.S_ISREG(status.st_mode)
    assert status.st_nlink == 1
    assert status.st_size == 0
    return path_identity(lock_path), status.st_size


def _assert_worker_physical_fact(
    current: session.LiveStartSession,
    *,
    action: str,
) -> None:
    _recovery, owner, external = _owner_parts(current)
    if action in {_MATERIALIZE, _RETIRE_STAGING}:
        assert isinstance(external, Mapping)
        staging_path = Path(str(external["staging_path"]))
        inner_temp_path = Path(str(external["inner_temp_path"]))
        final_path = Path(str(external["final_path"]))
        if action == _MATERIALIZE:
            fingerprint = _file_fingerprint(staging_path)
            assert fingerprint is not None
            assert fingerprint[1] == external["planned_successor_size"]
            assert fingerprint[2] == external["planned_successor_sha256"]
        else:
            assert not os.path.lexists(staging_path)
            assert not os.path.lexists(inner_temp_path)
        assert not os.path.lexists(inner_temp_path)
        if external["predecessor_state"] == "absent":
            assert not os.path.lexists(final_path)
        else:
            fingerprint = _file_fingerprint(final_path)
            assert fingerprint is not None
            assert fingerprint[0] == tuple(external["predecessor_identity"])
            assert fingerprint[2] == external["predecessor_sha256"]
        return
    if action in {
        "commit_owner_retirement_prepared",
        "initialize_owner_cleanup_journal",
        "advance_owner_cleanup_journal",
        "commit_owner_retirement_completed",
    }:
        assert isinstance(external, Mapping)
        assert external["stage"] == "STAGING_BOUND"
        final_path = Path(str(external["final_path"]))
        assert _file_fingerprint(final_path) == (
            tuple(external["staging_identity"]),
            external["planned_successor_size"],
            external["planned_successor_sha256"],
        )
        assert not os.path.lexists(Path(str(external["staging_path"])))
        assert not os.path.lexists(Path(str(external["inner_temp_path"])))
        return
    if action == "delete_owner_cleanup_entry":
        entry = Path(str(owner["retired_target_path"])) / str(
            owner["next_entry_relative_path"]
        )
        assert not os.path.lexists(entry)
    elif action == "retire_owner_target_root":
        assert not os.path.lexists(Path(str(owner["retired_target_path"])))
    elif action == "retire_old_owner_journal":
        assert not os.path.lexists(Path(str(owner["initial_owner_journal_path"])))
    else:
        assert action == "observe_owner_retirement_completed"


def _assert_action_precondition(
    current: session.LiveStartSession,
    *,
    action: str,
    after_pre_cas_kill: bool,
) -> None:
    _recovery, owner, external = _owner_parts(current)

    def assert_plain_file(
        path: Path,
        *,
        expected_parent_identity: tuple[int, int, int],
        expected_identity: tuple[int, int, int],
        expected_size: int,
        expected_sha256: str,
    ) -> None:
        assert path_identity(path.parent) == expected_parent_identity
        status = path.lstat()
        assert stat.S_ISREG(status.st_mode)
        assert not status_is_reparse(status)
        assert status.st_nlink == 1
        assert _file_fingerprint(path) == (
            expected_identity,
            expected_size,
            expected_sha256,
        )
        require_no_alternate_data_streams(
            path,
            expected_identity=expected_identity,
            expected_parent_identity=expected_parent_identity,
            directory=False,
            expected_size=expected_size,
        )

    def assert_plain_directory(
        path: Path,
        *,
        expected_parent_identity: tuple[int, int, int],
        expected_identity: tuple[int, int, int],
    ) -> None:
        assert path_identity(path.parent) == expected_parent_identity
        status = path.lstat()
        assert stat.S_ISDIR(status.st_mode)
        assert not status_is_reparse(status)
        assert path_identity(path) == expected_identity
        require_no_alternate_data_streams(
            path,
            expected_identity=expected_identity,
            expected_parent_identity=expected_parent_identity,
            directory=True,
        )

    if action in {_MATERIALIZE, _RETIRE_STAGING}:
        assert isinstance(external, Mapping)
        assert external["stage"] == "PLANNED"
        assert _has_unbound_staging(current) is (action == _RETIRE_STAGING)
        return
    if action in {
        "commit_owner_retirement_prepared",
        "initialize_owner_cleanup_journal",
        "advance_owner_cleanup_journal",
        "commit_owner_retirement_completed",
    }:
        assert isinstance(external, Mapping)
        assert external["stage"] == "STAGING_BOUND"
        final_path = Path(str(external["final_path"]))
        staging_path = Path(str(external["staging_path"]))
        inner_temp_path = Path(str(external["inner_temp_path"]))
        parent_identity = tuple(external["parent_identity"])
        staging_identity = tuple(external["staging_identity"])
        staging_size = int(external["staging_size"])
        staging_sha256 = str(external["staging_sha256"])
        assert staging_path == final_path.with_name(f"{final_path.name}.staged")
        assert inner_temp_path == staging_path.with_name(
            f".{staging_path.name}.live-start-atomic.tmp"
        )
        assert staging_size == external["planned_successor_size"]
        assert staging_sha256 == external["planned_successor_sha256"]
        assert not os.path.lexists(inner_temp_path)
        if after_pre_cas_kill:
            assert_plain_file(
                final_path,
                expected_parent_identity=parent_identity,
                expected_identity=staging_identity,
                expected_size=staging_size,
                expected_sha256=staging_sha256,
            )
            assert not os.path.lexists(staging_path)
            return
        assert_plain_file(
            staging_path,
            expected_parent_identity=parent_identity,
            expected_identity=staging_identity,
            expected_size=staging_size,
            expected_sha256=staging_sha256,
        )
        if external["predecessor_state"] == "absent":
            assert external["predecessor_identity"] is None
            assert external["predecessor_size"] is None
            assert external["predecessor_sha256"] is None
            assert not os.path.lexists(final_path)
        else:
            assert external["predecessor_state"] == "exact"
            assert_plain_file(
                final_path,
                expected_parent_identity=parent_identity,
                expected_identity=tuple(external["predecessor_identity"]),
                expected_size=int(external["predecessor_size"]),
                expected_sha256=str(external["predecessor_sha256"]),
            )
        return
    if action == "delete_owner_cleanup_entry":
        entry = Path(str(owner["retired_target_path"])) / str(
            owner["next_entry_relative_path"]
        )
        entry_parent_identity = tuple(owner["next_entry_parent_identity"])
        assert path_identity(entry.parent) == entry_parent_identity
        if after_pre_cas_kill:
            assert not os.path.lexists(entry)
            return
        if owner["next_entry_kind"] == "file":
            assert_plain_file(
                entry,
                expected_parent_identity=entry_parent_identity,
                expected_identity=tuple(owner["next_entry_identity"]),
                expected_size=int(owner["next_entry_size"]),
                expected_sha256=str(owner["next_entry_sha256"]),
            )
        else:
            assert owner["next_entry_kind"] == "directory"
            assert_plain_directory(
                entry,
                expected_parent_identity=entry_parent_identity,
                expected_identity=tuple(owner["next_entry_identity"]),
            )
            assert not tuple(entry.iterdir())
        return
    if action == "retire_owner_target_root":
        target = Path(str(owner["retired_target_path"]))
        target_parent_identity = tuple(owner["retired_target_parent_identity"])
        assert path_identity(target.parent) == target_parent_identity
        if after_pre_cas_kill:
            assert not os.path.lexists(target)
            return
        assert_plain_directory(
            target,
            expected_parent_identity=target_parent_identity,
            expected_identity=tuple(owner["retired_target_identity"]),
        )
        assert not tuple(target.iterdir())
        return
    if action == "retire_old_owner_journal":
        owner_path = Path(str(owner["initial_owner_journal_path"]))
        layout = current.runtime_layout_bootstrap
        assert isinstance(layout, Mapping)
        transaction_rows = [
            row
            for row in layout["directories"]
            if isinstance(row, Mapping) and row.get("role") == "transactions"
        ]
        assert len(transaction_rows) == 1
        transaction_row = transaction_rows[0]
        assert Path(str(transaction_row["path"])) == owner_path.parent
        owner_parent_identity = tuple(transaction_row["successor_identity"])
        assert path_identity(owner_path.parent) == owner_parent_identity
        if after_pre_cas_kill:
            assert not os.path.lexists(owner_path)
            return
        fingerprint = _file_fingerprint(owner_path)
        assert fingerprint is not None
        assert fingerprint[0] == tuple(owner["current_owner_journal_identity"])
        assert fingerprint[2] == owner["current_owner_journal_sha256"]
        status = owner_path.lstat()
        assert stat.S_ISREG(status.st_mode)
        assert not status_is_reparse(status)
        assert status.st_nlink == 1
        require_no_alternate_data_streams(
            owner_path,
            expected_identity=fingerprint[0],
            expected_parent_identity=owner_parent_identity,
            directory=False,
            expected_size=fingerprint[1],
        )
        return
    assert action == "observe_owner_retirement_completed"
    assert not os.path.lexists(Path(str(owner["initial_owner_journal_path"])))


def _is_manifest_bound(current: session.LiveStartSession) -> bool:
    try:
        recovery, owner, external = _owner_parts(current)
    except AssertionError:
        return False
    return bool(
        current.phase.value == "APPLY_STARTED"
        and current.pending_transition is None
        and recovery.get("recovery_stage") == "ACTIVE"
        and recovery.get("install_route") == "new_target"
        and recovery.get("stable_physical_disposition") is None
        and recovery.get("expected_action") == _MATERIALIZE
        and owner.get("stage") == "PREPARED_PLANNED"
        and owner.get("cleanup_cursor") == 0
        and isinstance(external, Mapping)
        and external.get("action_kind") == "commit_owner_retirement_prepared"
        and external.get("stage") == "PLANNED"
        and external.get("final_path") == owner.get("tombstone_path")
        and owner.get("tombstone_identity") is None
        and owner.get("old_owner_journal_retired") is False
    )


def _owner_hard_kill_worker(
    session_root_text: str,
    specification_json: str,
    oracle_path_text: str,
) -> None:
    session_root = Path(session_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    specification = json.loads(specification_json)
    start = _load_raw_session(session_root)
    expected_action = specification.get("action")
    kind = str(specification["kind"])
    if kind != "manifest":
        assert start.content_sha256 == specification["start_sha256"]
        assert _effective_owner_action(start) == expected_action
    counts, previous_profile = _start_apply_entry_observer()
    observed_points: list[str] = []

    def hard_kill(point: LiveStartFaultPoint) -> None:
        if point not in {_PRE_CAS, _POST_CAS}:
            return
        current = _load_raw_session(session_root)
        observed_points.append(point.value)
        if kind == "manifest":
            if point is not _POST_CAS or not _is_manifest_bound(current):
                return
        elif kind == "pre":
            if point is not _PRE_CAS:
                return
            assert current.canonical_json == start.canonical_json
            assert current.session_identity == start.session_identity
            _assert_worker_physical_fact(current, action=str(expected_action))
        else:
            assert kind == "post"
            if point is not _POST_CAS:
                return
            predecessor = start.apply_recovery
            successor = current.apply_recovery
            assert isinstance(predecessor, Mapping)
            assert isinstance(successor, Mapping)
            session._validate_owner_retirement_successor(
                predecessor=predecessor,
                successor=successor,
                action=str(expected_action),
            )
            assert successor["action_index"] == predecessor["action_index"] + 1
        lock_identity, lock_size = _held_apply_lock_metadata(current)
        _persist_worker_oracle(
            Path(oracle_path_text),
            {
                "kind": kind,
                "action": expected_action,
                "fault_value": point.value,
                "start_session": start.to_value(),
                "session": current.to_value(),
                "apply_entry_counts": counts,
                "observed_points": observed_points,
                "apply_lock_identity": lock_identity,
                "apply_lock_size": lock_size,
            },
        )
        os._exit(_HARD_EXIT)

    try:
        controller._finalize_live_start(
            session_root=session_root,
            resume_intake=True,
            fault_hook=hard_kill,
        )
    finally:
        sys.setprofile(previous_profile)
    os._exit(_HARD_EXIT + 1)


def _assert_lock_after_exit(
    runtime_root: Path,
    *,
    oracle: Mapping[str, Any],
) -> None:
    identity = tuple(oracle["apply_lock_identity"])
    assert oracle["apply_lock_size"] == 0
    assert _file_fingerprint(runtime_root / ".hsconfig/apply.lock") == (
        identity,
        0,
        _sha256_bytes(b""),
    )


def _expected_physical_changes(
    current: session.LiveStartSession,
    *,
    action: str,
    runtime_tree_before: Mapping[str, object],
) -> set[str]:
    recovery, owner, external = _owner_parts(current)
    runtime_root = Path(str(recovery["runtime_root"]))

    def relative(path: Path) -> str:
        return path.relative_to(runtime_root).as_posix()

    if action == _MATERIALIZE:
        assert isinstance(external, Mapping)
        staging = relative(Path(str(external["staging_path"])))
        assert staging not in runtime_tree_before
        return {staging}
    if action == _RETIRE_STAGING:
        assert isinstance(external, Mapping)
        residue = {
            relative(Path(str(external[field])))
            for field in ("staging_path", "inner_temp_path")
            if relative(Path(str(external[field]))) in runtime_tree_before
        }
        assert residue
        return residue
    if action in {
        "commit_owner_retirement_prepared",
        "initialize_owner_cleanup_journal",
        "advance_owner_cleanup_journal",
        "commit_owner_retirement_completed",
    }:
        assert isinstance(external, Mapping)
        staging = relative(Path(str(external["staging_path"])))
        final = relative(Path(str(external["final_path"])))
        if staging not in runtime_tree_before:
            return set()
        return {staging, final}
    if action == "delete_owner_cleanup_entry":
        entry = relative(
            Path(str(owner["retired_target_path"]))
            / str(owner["next_entry_relative_path"])
        )
        return {entry} if entry in runtime_tree_before else set()
    if action == "retire_owner_target_root":
        target = relative(Path(str(owner["retired_target_path"])))
        return {target} if target in runtime_tree_before else set()
    if action == "retire_old_owner_journal":
        journal = relative(Path(str(owner["initial_owner_journal_path"])))
        return {journal} if journal in runtime_tree_before else set()
    assert action == "observe_owner_retirement_completed"
    return set()


def _assert_external_planned_to_bound(
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
) -> None:
    assert predecessor["stage"] == "PLANNED"
    assert successor["stage"] == "STAGING_BOUND"
    for field_name in session._EXTERNAL_FILE_ACTION_FIELDS - {
        "stage",
        "staging_identity",
        "staging_size",
        "staging_sha256",
        "content_sha256",
    }:
        assert successor.get(field_name) == predecessor.get(field_name)
    assert successor["staging_identity"] is not None
    assert successor["staging_size"] == predecessor["planned_successor_size"]
    assert successor["staging_sha256"] == predecessor["planned_successor_sha256"]


def _assert_retired_staging_successor(
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
) -> None:
    assert predecessor["stage"] == successor["stage"] == "PLANNED"
    assert successor["action_index"] == predecessor["action_index"] + 1
    for field_name in session._EXTERNAL_FILE_ACTION_FIELDS - {
        "action_index",
        "content_sha256",
    }:
        assert successor.get(field_name) == predecessor.get(field_name)


def _assert_owner_successor(
    predecessor: session.LiveStartSession,
    successor: session.LiveStartSession,
    *,
    action: str,
) -> None:
    before, before_owner, before_external = _owner_parts(predecessor)
    after, after_owner, after_external = _owner_parts(successor)
    assert successor.phase.value == predecessor.phase.value == "APPLY_STARTED"
    assert successor.pending_transition is None
    assert _frozen_identity(successor) == _frozen_identity(predecessor)
    assert after["action_index"] == before["action_index"] + 1
    session._validate_owner_retirement_successor(
        predecessor=before,
        successor=after,
        action=action,
    )

    mutable_owner_fields = {
        _MATERIALIZE: set(),
        _RETIRE_STAGING: set(),
        "commit_owner_retirement_prepared": {"stage", "tombstone_identity"},
        "initialize_owner_cleanup_journal": {
            "stage",
            "current_owner_journal_identity",
            "current_owner_journal_sha256",
            "planned_completed_tombstone_size",
            "planned_completed_tombstone_sha256",
        },
        "delete_owner_cleanup_entry": set(),
        "advance_owner_cleanup_journal": {
            "current_owner_journal_identity",
            "current_owner_journal_sha256",
            "cleanup_cursor",
            "planned_completed_tombstone_size",
            "planned_completed_tombstone_sha256",
            "next_entry_relative_path",
            "next_entry_kind",
            "next_entry_identity",
            "next_entry_parent_identity",
            "next_entry_size",
            "next_entry_sha256",
        },
        "retire_owner_target_root": {"stage"},
        "commit_owner_retirement_completed": {
            "stage",
            "tombstone_identity",
            "tombstone_sha256",
        },
        "retire_old_owner_journal": {"stage", "old_owner_journal_retired"},
        "observe_owner_retirement_completed": set(),
    }[action]
    for field_name in set(before_owner) - mutable_owner_fields - {"content_sha256"}:
        assert after_owner[field_name] == before_owner[field_name]

    if action == _RETIRE_STAGING:
        assert isinstance(before_external, Mapping)
        assert isinstance(after_external, Mapping)
        assert after_owner == before_owner
        _assert_retired_staging_successor(before_external, after_external)
        assert after["expected_action"] == _MATERIALIZE
    elif action == _MATERIALIZE:
        assert isinstance(before_external, Mapping)
        assert isinstance(after_external, Mapping)
        assert after_owner == before_owner
        _assert_external_planned_to_bound(before_external, after_external)
        assert after["expected_action"] == before_external["action_kind"]
    elif action == "commit_owner_retirement_prepared":
        assert before_owner["stage"] == "PREPARED_PLANNED"
        assert after_owner["stage"] == "PREPARED"
        assert after_owner["tombstone_identity"] is not None
        assert isinstance(after_external, Mapping)
        assert after_external["action_kind"] == "initialize_owner_cleanup_journal"
        assert after_external["stage"] == "PLANNED"
    elif action == "initialize_owner_cleanup_journal":
        assert before_owner["stage"] == "PREPARED"
        assert after_owner["stage"] == "CLEANING"
        assert after_owner["cleanup_cursor"] == 0
        assert after_external is None
        assert after["expected_action"] == "delete_owner_cleanup_entry"
    elif action == "delete_owner_cleanup_entry":
        assert after_owner == before_owner
        assert isinstance(after_external, Mapping)
        assert after_external["action_kind"] == "advance_owner_cleanup_journal"
        assert after_external["stage"] == "PLANNED"
        assert after["expected_action"] == _MATERIALIZE
    elif action == "advance_owner_cleanup_journal":
        assert after_owner["stage"] == before_owner["stage"] == "CLEANING"
        assert after_owner["cleanup_cursor"] == before_owner["cleanup_cursor"] + 1
        assert after_external is None
        assert after["expected_action"] == (
            "retire_owner_target_root"
            if after_owner["cleanup_cursor"] == after_owner["cleanup_entry_count"]
            else "delete_owner_cleanup_entry"
        )
    elif action == "retire_owner_target_root":
        assert before_owner["stage"] == "CLEANING"
        assert after_owner["stage"] == "TARGET_RETIRED"
        assert isinstance(after_external, Mapping)
        assert after_external["action_kind"] == "commit_owner_retirement_completed"
        assert after_external["stage"] == "PLANNED"
        assert (
            after_external["planned_successor_size"]
            == before_owner["planned_completed_tombstone_size"]
        )
        assert (
            after_external["planned_successor_sha256"]
            == before_owner["planned_completed_tombstone_sha256"]
        )
    elif action == "commit_owner_retirement_completed":
        assert before_owner["stage"] == "TARGET_RETIRED"
        assert after_owner["stage"] == "COMPLETED"
        assert after_external is None
        assert after["expected_action"] == "retire_old_owner_journal"
    elif action == "retire_old_owner_journal":
        assert before_owner["stage"] == "COMPLETED"
        assert after_owner["stage"] == "OWNER_RETIRED"
        assert after_owner["old_owner_journal_retired"] is True
        assert after_external is None
        assert after["expected_action"] == "observe_owner_retirement_completed"
    else:
        assert action == "observe_owner_retirement_completed"
        assert after_owner == before_owner
        assert after_external is None
        assert after["expected_action"] == "observe_committed"
        assert after["stable_physical_disposition"] is None


def _assert_only_retirement_runtime_changes(
    *,
    runtime_root: Path,
    baseline: Mapping[str, object],
    current: Mapping[str, object],
    old: _OldAuthority,
    session_cursor: session.LiveStartSession,
) -> None:
    recovery, _owner, external = _owner_parts(session_cursor)
    assert Path(str(recovery["runtime_root"])) == runtime_root
    old_target = old.target_path.relative_to(runtime_root).as_posix()
    old_owner = old.owner_path.relative_to(runtime_root).as_posix()
    tombstone = (
        (
            runtime_root
            / ".hsconfig/owner-retirements"
            / f"{old.owner.transaction_id}.json"
        )
        .relative_to(runtime_root)
        .as_posix()
    )
    external_mutable: set[str] = set()
    if isinstance(external, Mapping):
        parent_identity = tuple(external["parent_identity"])
        for field_name in ("staging_path", "inner_temp_path"):
            path = Path(str(external[field_name]))
            assert path.is_relative_to(runtime_root)
            assert path_identity(path.parent) == parent_identity
            relative = path.relative_to(runtime_root).as_posix()
            external_mutable.add(relative)
            if not os.path.lexists(path):
                continue
            status = path.lstat()
            assert stat.S_ISREG(status.st_mode)
            assert not status_is_reparse(status)
            assert status.st_nlink == 1
            row = current[relative]
            assert row[0] == "file"
            assert tuple(row[1]) == path_identity(path)
            raw = row[2]
            assert isinstance(raw, bytes)
            if field_name == "staging_path":
                if external["stage"] == "STAGING_BOUND":
                    assert tuple(row[1]) == tuple(external["staging_identity"])
                    assert len(raw) == external["staging_size"]
                    assert _sha256_bytes(raw) == external["staging_sha256"]
                else:
                    assert external["stage"] == "PLANNED"
                    assert len(raw) == external["planned_successor_size"]
                    assert _sha256_bytes(raw) == external["planned_successor_sha256"]
            else:
                assert external["stage"] == "PLANNED"
                assert len(raw) <= external["planned_successor_size"]

    def mutable(relative: str) -> bool:
        return bool(
            relative == old_target
            or relative.startswith(old_target + "/")
            or relative == old_owner
            or relative == tombstone
            or relative in external_mutable
        )

    for relative in set(baseline) | set(current):
        if not mutable(relative):
            assert current.get(relative) == baseline.get(relative), relative


def _capture_chain_authority(
    *,
    fixture: Any,
    prepared: Any,
    current: session.LiveStartSession,
) -> _ChainAuthority:
    value = current.to_value()
    recovery, owner_retirement, _external = _owner_parts(current)
    admission = value["runtime_admission_binding"]
    layout = value["runtime_layout_bootstrap"]
    operation = value["output_operation_admission_binding"]
    child = value["output_child_binding"]
    publication = value["publication_binding"]
    for binding in (admission, layout, operation, child, publication):
        assert isinstance(binding, dict)
    attempt_id = str(recovery["apply_attempt_id"])
    invocation_path = prepared.run_root / "receipts/apply_invocation.json"
    invocation_fingerprint = _file_fingerprint(invocation_path)
    admission_path = Path(str(admission["admission_path"]))
    admission_fingerprint = _file_fingerprint(admission_path)
    profile_fingerprint = _file_fingerprint(operator_profile_path())
    attempt_path = Path(str(recovery["successor_attempt_record_path"]))
    attempt_fingerprint = _file_fingerprint(attempt_path)
    owner_path = Path(str(owner_retirement["successor_owner_journal_path"]))
    owner_fingerprint = _file_fingerprint(owner_path)
    target_path = Path(str(recovery["renamed_target_path"]))
    for fingerprint in (
        invocation_fingerprint,
        admission_fingerprint,
        profile_fingerprint,
        attempt_fingerprint,
        owner_fingerprint,
    ):
        assert fingerprint is not None
    assert invocation_fingerprint is not None
    assert admission_fingerprint is not None
    assert profile_fingerprint is not None
    assert attempt_fingerprint is not None
    assert owner_fingerprint is not None
    invocation = load_apply_invocation(invocation_path)
    assert invocation.apply_attempt_id == attempt_id
    assert invocation.content_sha256 == current.apply_invocation_sha256
    owner = runtime_apply.read_runtime_transaction_journal(owner_path)
    assert owner.transaction_id == attempt_id
    assert owner.owns_target is True
    assert fixture.profile.runtime_root / owner.target_path == target_path
    output_root = derive_deck_output_binding(
        fixture.profile,
        fixture.deck_name,
    ).output_root
    current_runtime_paths = (
        fixture.profile.runtime_root / "CustomConfig/deck_config.ini",
        fixture.profile.runtime_root / ".hsconfig/state.json",
        runtime_apply._receipt_path(fixture.profile.runtime_root, owner.state_key),
    )
    current_runtime = {
        path: fingerprint
        for path in current_runtime_paths
        if (fingerprint := _file_fingerprint(path)) is not None
    }
    assert set(current_runtime) == set(current_runtime_paths)
    return _ChainAuthority(
        frozen_identity=_frozen_identity(current),
        attempt_id=attempt_id,
        invocation_path=invocation_path,
        invocation_fingerprint=invocation_fingerprint,
        admission_binding=admission,
        admission_fingerprint=admission_fingerprint,
        layout_binding=layout,
        operation_binding=operation,
        child_binding=child,
        publication_binding=publication,
        profile_fingerprint=profile_fingerprint,
        output_root=output_root,
        output_tree=_physical_tree(output_root),
        attempt_path=attempt_path,
        attempt_fingerprint=attempt_fingerprint,
        owner=owner,
        owner_path=owner_path,
        owner_fingerprint=owner_fingerprint,
        target_path=target_path,
        target_identity=path_identity(target_path),
        target_tree=_physical_tree(target_path),
        current_runtime=current_runtime,
        runtime_baseline=_physical_tree(fixture.profile.runtime_root),
    )


def _assert_chain_authority(
    *,
    prepared: Any,
    current: session.LiveStartSession,
    authority: _ChainAuthority,
    old: _OldAuthority,
) -> None:
    value = current.to_value()
    recovery, owner, _external = _owner_parts(current)
    assert current.phase.value == "APPLY_STARTED"
    assert current.pending_transition is None
    assert _frozen_identity(current) == authority.frozen_identity
    assert recovery["apply_attempt_id"] == authority.attempt_id
    assert recovery["install_route"] == "new_target"
    assert (
        current.apply_invocation_sha256
        == load_apply_invocation(authority.invocation_path).content_sha256
    )
    assert value["runtime_admission_binding"] == authority.admission_binding
    assert value["runtime_layout_bootstrap"] == authority.layout_binding
    assert value["output_operation_admission_binding"] == authority.operation_binding
    assert value["output_child_binding"] == authority.child_binding
    assert value["publication_binding"] == authority.publication_binding
    assert _file_fingerprint(authority.invocation_path) == (
        authority.invocation_fingerprint
    )
    assert tuple(prepared.run_root.rglob("*apply_invocation*.json")) == (
        authority.invocation_path,
    )
    assert _file_fingerprint(operator_profile_path()) == authority.profile_fingerprint
    assert _physical_tree(authority.output_root) == authority.output_tree
    admission = load_runtime_live_attempt_admission()
    assert admission is not None
    assert admission.apply_attempt_id == authority.attempt_id
    assert admission.admission_path == Path(
        str(authority.admission_binding["admission_path"])
    )
    assert _file_fingerprint(admission.admission_path) == (
        authority.admission_fingerprint
    )
    assert _file_fingerprint(authority.attempt_path) == authority.attempt_fingerprint
    assert tuple(authority.attempt_path.parent.glob("*.json")) == (
        authority.attempt_path,
    )
    assert _file_fingerprint(authority.owner_path) == authority.owner_fingerprint
    assert path_identity(authority.target_path) == authority.target_identity
    assert _physical_tree(authority.target_path) == authority.target_tree
    assert {
        path: _file_fingerprint(path) for path in authority.current_runtime
    } == authority.current_runtime
    assert _file_fingerprint(old.run_root / "session.json") == (old.session_fingerprint)
    assert _result_pair(old.run_root) == old.result_pair
    assert not os.path.lexists(Path(str(old.acknowledgement["retention_fence_path"])))

    exact_journals = [
        runtime_apply.read_runtime_transaction_journal(authority.owner_path)
    ]
    if os.path.lexists(old.owner_path):
        exact_journals.append(
            runtime_apply.read_runtime_transaction_journal(old.owner_path)
        )
    journal_ids = {journal.transaction_id for journal in exact_journals}
    expected_journal_ids = {authority.attempt_id}
    if os.path.lexists(old.owner_path):
        expected_journal_ids.add(old.owner.transaction_id)
    assert journal_ids == expected_journal_ids
    assert owner["successor_transaction_id"] == authority.attempt_id
    assert Path(str(owner["successor_owner_journal_path"])) == authority.owner_path
    assert (
        tuple(owner["successor_owner_journal_identity"])
        == (authority.owner_fingerprint[0])
    )
    assert owner["successor_owner_journal_sha256"] == authority.owner_fingerprint[2]

    runtime_root = authority.target_path.parents[1]
    expected_targets = {authority.target_path}
    if os.path.lexists(old.target_path):
        expected_targets.add(old.target_path)
    assert {
        path for path in (runtime_root / "CustomConfig").iterdir() if path.is_dir()
    } == expected_targets
    _assert_only_retirement_runtime_changes(
        runtime_root=runtime_root,
        baseline=authority.runtime_baseline,
        current=_physical_tree(runtime_root),
        old=old,
        session_cursor=current,
    )


def _run_kill(
    *,
    prepared: Any,
    runtime_root: Path,
    marker: Path,
    kind: str,
    action: str | None,
    first_apply: bool = False,
) -> tuple[
    session.LiveStartSession,
    session.LiveStartSession,
    dict[str, tuple[str, tuple[int, int, int], bytes | None]],
    dict[str, tuple[str, tuple[int, int, int], bytes | None]],
    dict[str, Any],
]:
    predecessor = _load_raw_session(prepared.run_root)
    if kind != "manifest":
        assert action is not None
        _assert_action_precondition(
            predecessor,
            action=action,
            after_pre_cas_kill=kind == "post",
        )
    runtime_before = _physical_tree(runtime_root)
    specification = {
        "kind": kind,
        "action": action,
        "start_sha256": predecessor.content_sha256,
    }
    _spawn_and_join(
        target=_owner_hard_kill_worker,
        args=(str(prepared.run_root), json.dumps(specification), str(marker)),
        expected_exitcode=_HARD_EXIT,
        timeout_seconds=360,
    )
    oracle = json.loads(marker.read_bytes())
    assert oracle["kind"] == kind
    assert oracle["action"] == action
    assert oracle["start_session"] == predecessor.to_value()
    expected_fault = _POST_CAS if kind in {"manifest", "post"} else _PRE_CAS
    assert oracle["fault_value"] == expected_fault.value
    expected_counts = (
        _expected_apply_entry_counts(fresh=1, install_prepare=1, attempt_prepare=1)
        if first_apply
        else _expected_apply_entry_counts(recovery=1)
    )
    assert oracle["apply_entry_counts"] == expected_counts
    if kind == "pre":
        assert oracle["observed_points"][-1:] == [_PRE_CAS.value]
    else:
        assert oracle["observed_points"][-2:] == [_PRE_CAS.value, _POST_CAS.value]
    current = _load_raw_session(prepared.run_root)
    assert oracle["session"] == current.to_value()
    if kind == "pre":
        assert current.canonical_json == predecessor.canonical_json
        assert current.session_identity == predecessor.session_identity
    elif kind == "post":
        assert action is not None
        _assert_owner_successor(predecessor, current, action=action)
    else:
        assert kind == "manifest"
        assert _is_manifest_bound(current)
    _assert_lock_after_exit(runtime_root, oracle=oracle)
    runtime_after = _physical_tree(runtime_root)
    if kind != "manifest":
        assert action is not None
        assert _changed_paths(runtime_before, runtime_after) == (
            _expected_physical_changes(
                predecessor,
                action=action,
                runtime_tree_before=runtime_before,
            )
        )
    return predecessor, current, runtime_before, runtime_after, oracle


def test_owner_retirement_nonzero_action_chain_replays_retired_old_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One changed package resumes every nonzero owner-retirement boundary."""

    _local_state(tmp_path, monkeypatch)
    first_fixture, first = _prepare_approved(tmp_path / "first", monkeypatch)
    first_result = controller.finalize_live_start(session_root=first.run_root)
    assert first_result.status == "LIVE_AND_MATCHED"
    runtime_root = first_fixture.profile.runtime_root
    _old_output, old_package, old_target = _matched_package(first_fixture)
    old_owners = [
        journal
        for journal in load_runtime_transaction_journals(runtime_root)
        if journal.owns_target and runtime_root / journal.target_path == old_target
    ]
    assert len(old_owners) == 1
    old_owner = old_owners[0]
    old_owner_path = runtime_transaction_journal_path(
        runtime_root,
        old_owner.transaction_id,
    )
    old_owner_fingerprint = _file_fingerprint(old_owner_path)
    first_session_fingerprint = _file_fingerprint(first.run_root / "session.json")
    assert old_owner_fingerprint is not None
    assert first_session_fingerprint is not None
    first_terminal = session.load_live_start_session(
        first.run_root,
        local_app_data_root=first.run_root.parents[2],
    )
    assert isinstance(first_terminal.attempt_acknowledgement, Mapping)
    first_acknowledgement = dict(first_terminal.attempt_acknowledgement)
    first_fence_path = Path(str(first_acknowledgement["retention_fence_path"]))
    assert not os.path.lexists(first_fence_path)
    assert not tuple((runtime_root / ".hsconfig/attempt-retention").iterdir())
    old = _OldAuthority(
        run_root=first.run_root,
        session_fingerprint=first_session_fingerprint,
        result_pair=_result_pair(first.run_root),
        status=first_result.status,
        summary_sha256=_sha256_bytes(first_result.summary.canonical_json),
        session_sha256=first_terminal.content_sha256,
        acknowledgement=first_acknowledgement,
        owner=old_owner,
        owner_path=old_owner_path,
        initial_owner_fingerprint=old_owner_fingerprint,
        target_path=old_target,
        target_parent_identity=path_identity(old_target.parent),
        target_identity=path_identity(old_target),
        target_tree=_physical_tree(old_target),
    )

    second_fixture, second = _prepare(
        tmp_path / "second",
        monkeypatch,
        profile=first_fixture.profile,
    )
    second_fixture = _changed_candidate(second_fixture)
    _approve(tmp_path / "second", second_fixture, second)
    markers = tmp_path / "owner-retirement-chain"
    markers.mkdir()

    _predecessor, current, _before, _after, _oracle = _run_kill(
        prepared=second,
        runtime_root=runtime_root,
        marker=markers / "000-manifest-bound.json",
        kind="manifest",
        action=None,
        first_apply=True,
    )
    authority = _capture_chain_authority(
        fixture=second_fixture,
        prepared=second,
        current=current,
    )
    assert authority.attempt_id != old.owner.transaction_id
    assert authority.target_path != old.target_path
    assert authority.owner_path != old.owner_path
    assert authority.publication_binding != first_terminal.publication_binding
    assert authority.owner.package_root_sha256 != old.owner.package_root_sha256
    assert old_package != (
        authority.output_root
        / str(authority.publication_binding["revision"])
        / "04_package"
    )
    _assert_chain_authority(
        prepared=second,
        current=current,
        authority=authority,
        old=old,
    )

    _recovery, initial_owner, initial_external = _owner_parts(current)
    cleanup_entry_count = initial_owner["cleanup_entry_count"]
    assert type(cleanup_entry_count) is int and cleanup_entry_count > 0
    cleanup_manifest_sha256 = initial_owner["cleanup_manifest_sha256"]
    assert initial_owner["cleanup_cursor"] == 0
    assert initial_owner["planned_completed_tombstone_size"] is None
    assert initial_owner["planned_completed_tombstone_sha256"] is None
    assert isinstance(initial_external, Mapping)
    tombstone_path = Path(str(initial_owner["tombstone_path"]))
    assert not os.path.lexists(tombstone_path)
    assert _file_fingerprint(old.owner_path) == old.initial_owner_fingerprint
    assert path_identity(old.target_path) == old.target_identity
    assert _physical_tree(old.target_path) == old.target_tree
    assert (
        tuple(initial_owner["initial_owner_journal_identity"])
        == (old.initial_owner_fingerprint[0])
    )
    assert (
        initial_owner["initial_owner_journal_sha256"]
        == (old.initial_owner_fingerprint[2])
    )
    assert tuple(initial_owner["retired_target_parent_identity"]) == (
        old.target_parent_identity
    )
    assert tuple(initial_owner["retired_target_identity"]) == old.target_identity

    expected_logical_actions = [
        _MATERIALIZE,
        "commit_owner_retirement_prepared",
        _MATERIALIZE,
        "initialize_owner_cleanup_journal",
    ]
    for _index in range(cleanup_entry_count):
        expected_logical_actions.extend(
            (
                "delete_owner_cleanup_entry",
                _MATERIALIZE,
                "advance_owner_cleanup_journal",
            )
        )
    expected_logical_actions.extend(
        (
            "retire_owner_target_root",
            _MATERIALIZE,
            "commit_owner_retirement_completed",
            "retire_old_owner_journal",
            "observe_owner_retirement_completed",
        )
    )

    completed_actions: list[str] = []
    killed_checkpoints: list[tuple[str, str, int]] = []
    prepared_tombstone: dict[str, Any] | None = None
    prepared_tombstone_fingerprint: tuple[tuple[int, int, int], int, str] | None = None
    completed_commitment: tuple[int, str] | None = None
    final_old_owner_fingerprint: tuple[tuple[int, int, int], int, str] | None = None
    ordinal = 1

    while _logical_owner_action(current) != "observe_committed":
        assert ordinal < 12 * cleanup_entry_count + 50
        logical_action = _logical_owner_action(current)
        assert logical_action == expected_logical_actions[len(completed_actions)]
        _recovery, owner_before, external_before = _owner_parts(current)
        cursor_before = int(owner_before["cleanup_cursor"])
        if logical_action == "retire_old_owner_journal":
            assert final_old_owner_fingerprint is not None
            assert _file_fingerprint(old.owner_path) == final_old_owner_fingerprint
            assert (
                tuple(owner_before["current_owner_journal_identity"])
                == (final_old_owner_fingerprint[0])
            )
            assert (
                owner_before["current_owner_journal_sha256"]
                == (final_old_owner_fingerprint[2])
            )
        if logical_action == _MATERIALIZE:
            assert isinstance(external_before, Mapping)
            assert external_before["stage"] == "PLANNED"
            _start, pre_materialized, _tree_before, _tree_after, _worker = _run_kill(
                prepared=second,
                runtime_root=runtime_root,
                marker=markers / f"{ordinal:03d}-materialize-pre.json",
                kind="pre",
                action=_MATERIALIZE,
            )
            ordinal += 1
            assert pre_materialized.canonical_json == current.canonical_json
            killed_checkpoints.append(("pre", logical_action, cursor_before))
            _assert_chain_authority(
                prepared=second,
                current=pre_materialized,
                authority=authority,
                old=old,
            )
            assert _effective_owner_action(pre_materialized) == _RETIRE_STAGING

            _start, retired_pre, _tree_before, _tree_after, _worker = _run_kill(
                prepared=second,
                runtime_root=runtime_root,
                marker=markers / f"{ordinal:03d}-staging-retire-pre.json",
                kind="pre",
                action=_RETIRE_STAGING,
            )
            ordinal += 1
            assert retired_pre.canonical_json == current.canonical_json
            killed_checkpoints.append(("pre", _RETIRE_STAGING, cursor_before))
            _assert_chain_authority(
                prepared=second,
                current=retired_pre,
                authority=authority,
                old=old,
            )
            assert _effective_owner_action(retired_pre) == _MATERIALIZE

            _start, recreated, _tree_before, _tree_after, _worker = _run_kill(
                prepared=second,
                runtime_root=runtime_root,
                marker=markers / f"{ordinal:03d}-materialize-recreate-pre.json",
                kind="pre",
                action=_MATERIALIZE,
            )
            ordinal += 1
            assert recreated.canonical_json == current.canonical_json
            killed_checkpoints.append(("pre", logical_action, cursor_before))
            _assert_chain_authority(
                prepared=second,
                current=recreated,
                authority=authority,
                old=old,
            )

            _retire_start, retired, _tree_before, _tree_after, _worker = _run_kill(
                prepared=second,
                runtime_root=runtime_root,
                marker=markers / f"{ordinal:03d}-staging-retire-post.json",
                kind="post",
                action=_RETIRE_STAGING,
            )
            ordinal += 1
            killed_checkpoints.append(("post", _RETIRE_STAGING, cursor_before))
            _assert_chain_authority(
                prepared=second,
                current=retired,
                authority=authority,
                old=old,
            )
            assert _effective_owner_action(retired) == _MATERIALIZE

            _materialize_start, successor, _tree_before, _tree_after, _worker = (
                _run_kill(
                    prepared=second,
                    runtime_root=runtime_root,
                    marker=markers / f"{ordinal:03d}-materialize-post.json",
                    kind="post",
                    action=_MATERIALIZE,
                )
            )
            ordinal += 1
            killed_checkpoints.append(("post", logical_action, cursor_before))
        else:
            _start, predecessor_after_physical, _tree_before, _tree_after, _worker = (
                _run_kill(
                    prepared=second,
                    runtime_root=runtime_root,
                    marker=markers / f"{ordinal:03d}-{logical_action}-pre.json",
                    kind="pre",
                    action=logical_action,
                )
            )
            ordinal += 1
            assert predecessor_after_physical.canonical_json == current.canonical_json
            killed_checkpoints.append(("pre", logical_action, cursor_before))
            _assert_chain_authority(
                prepared=second,
                current=predecessor_after_physical,
                authority=authority,
                old=old,
            )
            _start, successor, _tree_before, _tree_after, _worker = _run_kill(
                prepared=second,
                runtime_root=runtime_root,
                marker=markers / f"{ordinal:03d}-{logical_action}-post.json",
                kind="post",
                action=logical_action,
            )
            ordinal += 1
            killed_checkpoints.append(("post", logical_action, cursor_before))

        _assert_chain_authority(
            prepared=second,
            current=successor,
            authority=authority,
            old=old,
        )
        completed_actions.append(logical_action)
        current = successor
        _recovery, owner_after, _external_after = _owner_parts(current)
        assert owner_after["cleanup_manifest_sha256"] == cleanup_manifest_sha256
        assert owner_after["cleanup_entry_count"] == cleanup_entry_count

        if owner_after["stage"] == "PREPARED" and prepared_tombstone is None:
            prepared_tombstone_fingerprint = _file_fingerprint(tombstone_path)
            assert prepared_tombstone_fingerprint is not None
            prepared_tombstone = runtime_apply._parse_owner_retirement_tombstone_bytes(
                tombstone_path.read_bytes(),
                runtime_root=runtime_root,
            )
            assert prepared_tombstone["state"] == "PREPARED"
            assert prepared_tombstone["cleanup_entry_count"] == cleanup_entry_count
            assert len(prepared_tombstone["cleanup_entries"]) == cleanup_entry_count
            assert prepared_tombstone["completed_cleanup_cursor"] is None
            assert prepared_tombstone["cleanup_manifest_sha256"] == (
                cleanup_manifest_sha256
            )

        if (
            owner_after["stage"] == "CLEANING"
            and owner_after["cleanup_cursor"] == cleanup_entry_count
        ):
            next_commitment = (
                owner_after["planned_completed_tombstone_size"],
                owner_after["planned_completed_tombstone_sha256"],
            )
            assert type(next_commitment[0]) is int and next_commitment[0] > 0
            assert isinstance(next_commitment[1], str)
            if completed_commitment is None:
                completed_commitment = next_commitment
                final_old_owner_fingerprint = _file_fingerprint(old.owner_path)
                assert final_old_owner_fingerprint is not None
            else:
                assert next_commitment == completed_commitment

        if logical_action == "retire_owner_target_root":
            assert completed_commitment is not None
            assert not os.path.lexists(old.target_path)
            assert owner_before["stage"] == "CLEANING"
            assert owner_before["cleanup_cursor"] == cleanup_entry_count
            assert (
                owner_before["planned_completed_tombstone_size"],
                owner_before["planned_completed_tombstone_sha256"],
            ) == completed_commitment
            assert owner_after["stage"] == "TARGET_RETIRED"
            assert (
                owner_after["planned_completed_tombstone_size"],
                owner_after["planned_completed_tombstone_sha256"],
            ) == completed_commitment
        if logical_action == "retire_old_owner_journal":
            assert final_old_owner_fingerprint is not None
            assert not os.path.lexists(old.owner_path)

    assert completed_actions == expected_logical_actions
    materialize_count = expected_logical_actions.count(_MATERIALIZE)
    assert (
        sum(
            1
            for kind, action, _cursor in killed_checkpoints
            if kind == "post" and action == _RETIRE_STAGING
        )
        == materialize_count
    )
    assert (
        sum(
            1
            for kind, action, _cursor in killed_checkpoints
            if kind == "post" and action == _MATERIALIZE
        )
        == materialize_count
    )
    assert prepared_tombstone is not None
    assert prepared_tombstone_fingerprint is not None
    assert completed_commitment is not None
    assert final_old_owner_fingerprint is not None
    assert current.apply_recovery["stable_physical_disposition"] is None
    assert current.apply_recovery["expected_action"] == "observe_committed"

    final_oracle_path = markers / "final-public-resume.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(second.run_root), str(final_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    final_oracle = json.loads(final_oracle_path.read_bytes())
    assert final_oracle.pop("apply_entry_counts") == _expected_apply_entry_counts(
        recovery=1
    )
    assert final_oracle["status"] == "LIVE_AND_MATCHED"
    terminal = session.load_live_start_session(
        second.run_root,
        local_app_data_root=second.run_root.parents[2],
    )
    assert terminal.content_sha256 == final_oracle["session_sha256"]
    assert terminal.terminal_status == "LIVE_AND_MATCHED"
    assert terminal.pending_transition is None
    assert terminal.apply_recovery is None
    assert terminal.closed_apply_recovery_commitment is None
    assert _frozen_identity(terminal) == authority.frozen_identity
    assert terminal.result_intent["apply_attempt_id"] == authority.attempt_id
    assert terminal.result_intent["raw_apply_status"] == "recovered"
    assert terminal.result_intent["physical_disposition"] == "COMMITTED"
    assert terminal.result_intent["runtime_match_status"] == "matched"
    assert terminal.attempt_acknowledgement["apply_attempt_id"] == authority.attempt_id
    assert terminal.attempt_acknowledgement["journal_owns_target"] is True
    assert Path(str(terminal.attempt_acknowledgement["target_path"])) == (
        authority.target_path
    )
    assert tuple(terminal.attempt_acknowledgement["target_identity"]) == (
        authority.target_identity
    )
    assert (
        Path(str(terminal.attempt_acknowledgement["target_owner_journal_path"]))
        == authority.owner_path
    )
    assert (
        tuple(terminal.attempt_acknowledgement["target_owner_journal_identity"])
        == authority.owner_fingerprint[0]
    )
    assert (
        terminal.attempt_acknowledgement["target_owner_journal_sha256"]
        == (authority.owner_fingerprint[2])
    )
    assert terminal.terminal_retirement["apply_attempt_id"] == authority.attempt_id
    assert terminal.terminal_retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"
    assert load_runtime_live_attempt_admission() is None
    assert not tuple((runtime_root / ".hsconfig/attempt-retention").iterdir())
    assert not tuple((runtime_root / ".hsconfig/staging").iterdir())
    assert not output_operation_admission_path().exists()
    assert not output_operation_admission_staging_path().exists()
    assert not output_operation_admission_reserved_temp_path().exists()
    assert not output_child_claim_path(authority.output_root).exists()
    assert not tuple(second.run_root.parents[2].rglob("*.staged"))
    assert not tuple(second.run_root.parents[2].rglob("*.live-start-atomic.tmp"))
    assert not os.path.lexists(old.target_path)
    assert not os.path.lexists(old.owner_path)
    assert path_identity(authority.target_path) == authority.target_identity
    assert _physical_tree(authority.target_path) == authority.target_tree
    assert _file_fingerprint(authority.owner_path) == authority.owner_fingerprint
    journals = load_runtime_transaction_journals(runtime_root)
    assert len(journals) == 1
    assert journals[0].transaction_id == authority.attempt_id
    assert journals[0].owns_target is True
    assert _physical_tree(authority.output_root) == authority.output_tree
    assert _file_fingerprint(operator_profile_path()) == authority.profile_fingerprint
    assert (
        _file_fingerprint(authority.invocation_path) == authority.invocation_fingerprint
    )
    assert {
        path: _file_fingerprint(path) for path in authority.current_runtime
    } == authority.current_runtime

    completed = runtime_apply._parse_owner_retirement_tombstone_bytes(
        tombstone_path.read_bytes(),
        runtime_root=runtime_root,
    )
    completed_fingerprint = _file_fingerprint(tombstone_path)
    assert completed_fingerprint is not None
    assert completed["state"] == "COMPLETED"
    assert completed["retired_owner_transaction_id"] == old.owner.transaction_id
    assert Path(str(completed["initial_owner_journal_path"])) == old.owner_path
    assert (
        tuple(completed["initial_owner_journal_identity"])
        == (old.initial_owner_fingerprint[0])
    )
    assert (
        completed["initial_owner_journal_sha256"] == (old.initial_owner_fingerprint[2])
    )
    assert Path(str(completed["retired_target_path"])) == old.target_path
    assert tuple(completed["retired_target_parent_identity"]) == (
        old.target_parent_identity
    )
    assert tuple(completed["retired_target_identity"]) == old.target_identity
    assert (
        completed["retired_target_tree_sha256"]
        == initial_owner["retired_target_tree_sha256"]
    )
    assert completed["cleanup_manifest_sha256"] == cleanup_manifest_sha256
    assert completed["cleanup_entry_count"] == cleanup_entry_count
    assert completed["cleanup_entries"] == prepared_tombstone["cleanup_entries"]
    assert completed["completed_cleanup_cursor"] == cleanup_entry_count
    assert (
        tuple(completed["completed_owner_journal_identity"])
        == (final_old_owner_fingerprint[0])
    )
    assert (
        completed["completed_owner_journal_sha256"] == (final_old_owner_fingerprint[2])
    )
    assert completed["successor_transaction_id"] == authority.attempt_id
    assert (
        completed["successor_package_root_sha256"]
        == (authority.publication_binding["content_root_sha256"])
    )
    assert Path(str(completed["successor_owner_journal_path"])) == (
        authority.owner_path
    )
    assert (
        tuple(completed["successor_owner_journal_identity"])
        == (authority.owner_fingerprint[0])
    )
    assert (
        completed["successor_owner_journal_sha256"] == (authority.owner_fingerprint[2])
    )
    assert completed_fingerprint[1:] == completed_commitment

    _output, package, matched_target = _matched_package(second_fixture)
    assert matched_target == authority.target_path
    package_config = package / "CustomConfig" / authority.owner.logical_config_dir
    package_tree = _physical_tree(package_config)
    expected_kinds = dict.fromkeys(
        (
            ".",
            "CustomConfig",
            ".hsconfig",
            ".hsconfig/transactions",
            ".hsconfig/staging",
            ".hsconfig/receipts",
            f".hsconfig/receipts/{authority.owner.state_key}",
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
                authority.owner_path.relative_to(runtime_root).as_posix(),
                runtime_apply._receipt_path(runtime_root, authority.owner.state_key)
                .relative_to(runtime_root)
                .as_posix(),
                tombstone_path.relative_to(runtime_root).as_posix(),
            ),
            "file",
        )
    )
    target_relative = authority.target_path.relative_to(runtime_root).as_posix()
    for relative, row in package_tree.items():
        expected_kinds[
            target_relative if relative == "." else f"{target_relative}/{relative}"
        ] = row[0]
    final_runtime_tree = _physical_tree(runtime_root)
    assert {
        relative: row[0] for relative, row in final_runtime_tree.items()
    } == expected_kinds
    assert final_runtime_tree[".hsconfig/apply.lock"][2] == b""
    expected_final_changes = {
        relative
        for relative in authority.runtime_baseline
        if relative == old.target_path.relative_to(runtime_root).as_posix()
        or relative.startswith(
            old.target_path.relative_to(runtime_root).as_posix() + "/"
        )
    }
    expected_final_changes.update(
        {
            old.owner_path.relative_to(runtime_root).as_posix(),
            authority.attempt_path.relative_to(runtime_root).as_posix(),
            tombstone_path.relative_to(runtime_root).as_posix(),
        }
    )
    assert _changed_paths(authority.runtime_baseline, final_runtime_tree) == (
        expected_final_changes
    )

    terminal_snapshot = {
        "session": _file_fingerprint(second.run_root / "session.json"),
        "results": _result_pair(second.run_root),
        "runtime": _physical_tree(runtime_root),
        "output": _physical_tree(authority.output_root),
        "profile": _file_fingerprint(operator_profile_path()),
        "invocation": _file_fingerprint(authority.invocation_path),
        "old_session": _file_fingerprint(old.run_root / "session.json"),
        "old_results": _result_pair(old.run_root),
    }
    second_replay_path = markers / "second-public-replay.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(second.run_root), str(second_replay_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    second_replay = json.loads(second_replay_path.read_bytes())
    assert second_replay.pop("apply_entry_counts") == _expected_apply_entry_counts()
    assert second_replay == final_oracle
    assert terminal_snapshot == {
        "session": _file_fingerprint(second.run_root / "session.json"),
        "results": _result_pair(second.run_root),
        "runtime": _physical_tree(runtime_root),
        "output": _physical_tree(authority.output_root),
        "profile": _file_fingerprint(operator_profile_path()),
        "invocation": _file_fingerprint(authority.invocation_path),
        "old_session": _file_fingerprint(old.run_root / "session.json"),
        "old_results": _result_pair(old.run_root),
    }

    old_replay_path = markers / "old-public-replay.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(old.run_root), str(old_replay_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    old_replay = json.loads(old_replay_path.read_bytes())
    assert old_replay.pop("apply_entry_counts") == _expected_apply_entry_counts()
    assert old_replay == {
        "status": old.status,
        "run_root": str(old.run_root),
        "summary_sha256": old.summary_sha256,
        "session_sha256": old.session_sha256,
    }
    assert terminal_snapshot == {
        "session": _file_fingerprint(second.run_root / "session.json"),
        "results": _result_pair(second.run_root),
        "runtime": _physical_tree(runtime_root),
        "output": _physical_tree(authority.output_root),
        "profile": _file_fingerprint(operator_profile_path()),
        "invocation": _file_fingerprint(authority.invocation_path),
        "old_session": _file_fingerprint(old.run_root / "session.json"),
        "old_results": _result_pair(old.run_root),
    }
