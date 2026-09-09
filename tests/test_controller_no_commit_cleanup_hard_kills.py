from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from typing import Any

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.operator_profile import derive_deck_output_binding, operator_profile_path
from hsconfig.package_io import path_identity
from hsconfig.runtime_transaction_journal import load_runtime_transaction_journals
from tests.test_codex_first_live_e2e import _local_state, _prepare_approved
from tests.test_configure_prepublication_apply import (
    _file_fingerprint,
    _persist_worker_oracle,
    _physical_tree,
)
from tests.test_controller_output_hard_kills import (
    _expected_apply_entry_counts,
    _frozen_identity,
    _public_resume_worker,
    _spawn_and_join,
    _start_apply_entry_observer,
)


_HARD_EXIT = 93
_CONSUMED = LiveStartFaultPoint.AFTER_AUTHORIZATION_CONSUMED_BEFORE_PHYSICAL_CALLBACK
_CLASSIFIED = (
    LiveStartFaultPoint.AFTER_TERMINAL_CLASSIFICATION_OBSERVATION_BEFORE_SELECTION_CAS
)
_SELECTED = LiveStartFaultPoint.AFTER_TERMINAL_CLASSIFICATION_SELECTION_CAS
_RESOLUTION_PREPARED = LiveStartFaultPoint.AFTER_TERMINAL_RECOVERY_RESOLUTION_PREPARED
_INVENTORY_STAGING_FLUSH = LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_INVENTORY_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS
_INVENTORY_UNBOUND_RETIRED = LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_INVENTORY_UNBOUND_STAGING_RETIRE_BEFORE_CAS
_INVENTORY_STAGING_BOUND = (
    LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_INVENTORY_STAGING_BOUND
)
_INVENTORY_COMMITTED = LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_INVENTORY_BOUND_COMMIT_BEFORE_INVENTORY_BOUND_CAS
_INVENTORY_BOUND = LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_INVENTORY_BOUND
_CLEANING_STARTED = LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_STARTED
_ENTRY_DELETED = (
    LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_ENTRY_DELETE_BEFORE_CURSOR_CAS
)
_CURSOR_ADVANCED = LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_CURSOR_CAS
_JOURNAL_DELETED = (
    LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_JOURNAL_DELETE_BEFORE_STAGE_CAS
)
_JOURNAL_RETIRED = LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_JOURNAL_RETIRED_CAS
_FENCE_DELETED = (
    LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_FENCE_DELETE_BEFORE_STAGE_CAS
)
_FENCE_RETIRED = LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_FENCE_RETIRED_CAS
_SIDECAR_DELETED = (
    LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_SIDECAR_DELETE_BEFORE_STAGE_CAS
)
_INVENTORY_RETIRED = LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_INVENTORY_RETIRED_CAS
_STABILIZED = LiveStartFaultPoint.AFTER_TERMINAL_RECOVERY_STABILIZED
_EVIDENCE_RETIRED = (
    LiveStartFaultPoint.AFTER_ATTEMPT_EVIDENCE_RETIRED_BEFORE_ADMISSION_RELEASE
)
_RELEASE_AUTHORIZED = LiveStartFaultPoint.AFTER_ADMISSION_RELEASE_AUTHORIZED_BEFORE_RUNTIME_ADMISSION_UNLINK
_ADMISSION_UNLINKED = LiveStartFaultPoint.AFTER_RUNTIME_ADMISSION_UNLINK


def _sha256_bytes(raw: bytes) -> str:
    return "sha256:" + sha256(raw).hexdigest()


def _load_held_session(session_root: Path) -> session.LiveStartSession:
    session_path = session_root / "session.json"
    return session._load_session_bytes(
        session_path.read_bytes(),
        session_identity=path_identity(session_path),
    )


def _terminal_resolution(current: session.LiveStartSession) -> Mapping[str, Any]:
    retirement = current.terminal_retirement
    assert isinstance(retirement, Mapping)
    resolution = retirement.get("terminal_resolution_evidence")
    assert isinstance(resolution, Mapping)
    return resolution


def _result_pair(session_root: Path) -> dict[str, bytes]:
    return {
        relative: (session_root / relative).read_bytes()
        for relative in ("result/summary.json", "result/summary.md")
    }


def _entry_path(entry: Mapping[str, Any], roots: Mapping[str, Path]) -> Path:
    root = roots[str(entry["root_role"])]
    relative = str(entry["relative_path"])
    return root if relative == "." else root / Path(*relative.split("/"))


def _cleanup_root_projection(value: object) -> tuple[tuple[object, ...], ...]:
    assert isinstance(value, (list, tuple))
    rows: list[tuple[object, ...]] = []
    for row in value:
        assert isinstance(row, Mapping)
        rows.append(
            (
                row["root_role"],
                row["source_path"],
                tuple(row["source_identity"]),
                tuple(row["expected_parent_identity"]),
            )
        )
    return tuple(rows)


def _prepare_failed_cleanup_worker(
    session_root_text: str,
    oracle_path_text: str,
) -> None:
    session_root = Path(session_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    counts, previous_profile = _start_apply_entry_observer()
    failure_count = 0
    classification_count = 0
    selection_count = 0

    def fail_rename_then_kill_prepared(point: LiveStartFaultPoint) -> None:
        nonlocal failure_count, classification_count, selection_count
        if point is _CONSUMED:
            current = _load_held_session(session_root)
            recovery = current.apply_recovery
            if (
                failure_count == 0
                and isinstance(recovery, Mapping)
                and recovery.get("expected_action") == "rename_candidate_to_target"
            ):
                assert current.phase.value == "APPLY_STARTED"
                assert current.pending_transition is None
                assert recovery["install_route"] == "new_target"
                assert recovery["runtime_match_status"] == "not_run"
                assert recovery["stable_physical_disposition"] is None
                assert recovery["external_file_action"] is None
                assert recovery["candidate_tree_entry_count"] > 0
                assert (
                    recovery["candidate_tree_cursor"]
                    == recovery["candidate_tree_entry_count"]
                )
                assert (
                    recovery["candidate_tree_verified_sha256"]
                    == recovery["candidate_tree_manifest_sha256"]
                )
                candidate = Path(str(recovery["candidate_path"]))
                target = Path(str(recovery["renamed_target_path"]))
                assert path_identity(candidate) == tuple(
                    recovery["successor_candidate_identity"]
                )
                assert not os.path.lexists(target)
                failure_count += 1
                raise OSError("test-only rename failure before physical callback")
        elif point is _CLASSIFIED:
            assert failure_count == 1
            assert selection_count == 0
            classification_count += 1
            assert classification_count == 1
            current = _load_held_session(session_root)
            assert current.apply_recovery["expected_action"] == (
                "rename_candidate_to_target"
            )
            assert current.result_intent is None
            assert current.terminal_status is None
        elif point is _SELECTED:
            assert failure_count == classification_count == 1
            selection_count += 1
            assert selection_count == 1
            current = _load_held_session(session_root)
            recovery = current.apply_recovery
            assert recovery["expected_action"] == "observe_not_committed"
            assert recovery["external_file_action"] is None
            assert current.result_intent is None
            assert current.terminal_status is None
        elif point is _RESOLUTION_PREPARED:
            assert failure_count == classification_count == selection_count == 1
            current = _load_held_session(session_root)
            retirement = current.terminal_retirement
            resolution = _terminal_resolution(current)
            assert current.terminal_status == "FAILED_PRESERVED"
            assert current.result_intent["physical_disposition"] == "NOT_COMMITTED"
            assert current.result_intent["runtime_match_status"] == "not_run"
            assert current.attempt_acknowledgement is None
            assert retirement["operation"] == "release_resolved_terminal"
            assert retirement["stage"] == "RECOVERY_PREPARED"
            assert resolution["resolved_physical_disposition"] == "NOT_COMMITTED"
            assert resolution["cleanup_stage"] == "PREPARED"
            assert resolution["cleanup_cursor"] == 0
            assert resolution["cleanup_entry_count"] > 0
            external = resolution["external_file_action"]
            assert external["stage"] == "PLANNED"
            assert external["action_kind"] == (
                "commit_bound_terminal_cleanup_inventory"
            )
            inventory_path = Path(str(resolution["cleanup_inventory_path"]))
            assert not os.path.lexists(inventory_path)
            assert not os.path.lexists(Path(str(external["staging_path"])))
            assert not os.path.lexists(Path(str(external["inner_temp_path"])))
            _persist_worker_oracle(
                Path(oracle_path_text),
                {
                    "apply_entry_counts": counts,
                    "failure_count": failure_count,
                    "classification_count": classification_count,
                    "selection_count": selection_count,
                    "apply_attempt_id": resolution["apply_attempt_id"],
                    "cleanup_entry_count": resolution["cleanup_entry_count"],
                },
            )
            os._exit(_HARD_EXIT)

    try:
        controller._finalize_live_start(
            session_root=session_root,
            resume_intake=True,
            fault_hook=fail_rename_then_kill_prepared,
        )
    finally:
        sys.setprofile(previous_profile)
    os._exit(_HARD_EXIT + 1)


def _cleanup_hard_kill_worker(
    session_root_text: str,
    fault_value: str,
    oracle_path_text: str,
) -> None:
    session_root = Path(session_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    selected = LiveStartFaultPoint(fault_value)
    counts, previous_profile = _start_apply_entry_observer()
    occurrence = 0

    def hard_kill(point: LiveStartFaultPoint) -> None:
        nonlocal occurrence
        if point is not selected:
            return
        occurrence += 1
        current = _load_held_session(session_root)
        resolution = _terminal_resolution(current)
        _persist_worker_oracle(
            Path(oracle_path_text),
            {
                "fault_value": point.value,
                "occurrence": occurrence,
                "apply_entry_counts": counts,
                "terminal_status": current.terminal_status,
                "result_intent": current.to_value()["result_intent"],
                "retirement_stage": current.terminal_retirement["stage"],
                "cleanup_stage": resolution["cleanup_stage"],
                "cleanup_cursor": resolution["cleanup_cursor"],
                "cleanup_entry_count": resolution["cleanup_entry_count"],
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


def _rejected_resume_worker(
    session_root_text: str,
    oracle_path_text: str,
) -> None:
    session_root = Path(session_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    counts, previous_profile = _start_apply_entry_observer()
    try:
        try:
            controller.resume_live_start(session_root=session_root)
        except Exception as error:
            _persist_worker_oracle(
                Path(oracle_path_text),
                {
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "apply_entry_counts": counts,
                },
            )
            return
    finally:
        sys.setprofile(previous_profile)
    raise AssertionError("identity-substituted cleanup unexpectedly resumed")


def _prepare_real_cleanup_cursor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Any, Any, session.LiveStartSession, dict[str, Any]]:
    fixture, prepared = _prepare_approved(tmp_path / "approved", monkeypatch)
    oracle_path = tmp_path / "terminal-cleanup-prepared-oracle.json"
    _spawn_and_join(
        target=_prepare_failed_cleanup_worker,
        args=(str(prepared.run_root), str(oracle_path)),
        expected_exitcode=_HARD_EXIT,
        timeout_seconds=360,
    )
    current = session.load_live_start_session(prepared.run_root)
    oracle = json.loads(oracle_path.read_bytes())
    assert oracle["apply_entry_counts"] == _expected_apply_entry_counts(
        fresh=1,
        install_prepare=1,
        attempt_prepare=1,
    )
    assert oracle["failure_count"] == 1
    assert oracle["classification_count"] == 1
    assert oracle["selection_count"] == 1
    resolution = _terminal_resolution(current)
    assert oracle["apply_attempt_id"] == resolution["apply_attempt_id"]
    assert oracle["cleanup_entry_count"] == resolution["cleanup_entry_count"]
    return fixture, prepared, current, oracle


def _assert_frozen_terminal_surfaces(
    *,
    current: session.LiveStartSession,
    initial: session.LiveStartSession,
    result_intent: Mapping[str, Any],
    result_pair: Mapping[str, bytes],
    result_tree: Mapping[str, Any],
    session_root: Path,
    output_root: Path,
    output_tree: Mapping[str, Any],
    profile_fingerprint: tuple[tuple[int, int, int], int, str],
    invocation_path: Path,
    invocation_fingerprint: tuple[tuple[int, int, int], int, str],
) -> None:
    assert current.phase.value == "APPLY_STARTED"
    assert current.pending_transition is None
    assert current.terminal_status == "FAILED_PRESERVED"
    assert current.result_intent == result_intent
    assert current.attempt_acknowledgement is None
    assert current.apply_recovery is None
    assert _frozen_identity(current) == _frozen_identity(initial)
    for field in (
        "apply_invocation_sha256",
        "runtime_admission_binding",
        "runtime_layout_bootstrap",
        "output_operation_admission_binding",
        "output_child_binding",
        "publication_binding",
    ):
        assert getattr(current, field) == getattr(initial, field)
    assert current.artifact_bindings == initial.artifact_bindings
    assert _result_pair(session_root) == result_pair
    assert _physical_tree(session_root / "result") == result_tree
    assert _physical_tree(output_root) == output_tree
    assert _file_fingerprint(operator_profile_path()) == profile_fingerprint
    assert _file_fingerprint(invocation_path) == invocation_fingerprint
    assert tuple(session_root.rglob("*apply_invocation*.json")) == (invocation_path,)


def _kill_cleanup_at(
    *,
    session_root: Path,
    point: LiveStartFaultPoint,
    oracle_root: Path,
    ordinal: int,
) -> tuple[session.LiveStartSession, dict[str, Any]]:
    oracle_path = oracle_root / f"{ordinal:02d}-{point.value}.json"
    _spawn_and_join(
        target=_cleanup_hard_kill_worker,
        args=(str(session_root), point.value, str(oracle_path)),
        expected_exitcode=_HARD_EXIT,
        timeout_seconds=360,
    )
    oracle = json.loads(oracle_path.read_bytes())
    assert oracle["fault_value"] == point.value
    assert oracle["occurrence"] == 1
    assert oracle["apply_entry_counts"] == (
        _expected_apply_entry_counts()
        if point is _ADMISSION_UNLINKED
        else _expected_apply_entry_counts(recovery=1)
    )
    current = session.load_live_start_session(session_root)
    assert oracle["terminal_status"] == current.terminal_status
    assert oracle["result_intent"] == current.to_value()["result_intent"]
    assert oracle["retirement_stage"] == current.terminal_retirement["stage"]
    resolution = _terminal_resolution(current)
    assert oracle["cleanup_stage"] == resolution["cleanup_stage"]
    assert oracle["cleanup_cursor"] == resolution["cleanup_cursor"]
    assert oracle["cleanup_entry_count"] == resolution["cleanup_entry_count"]
    return current, oracle


def test_terminal_no_commit_cleanup_crashes_preserve_failed_preserved_and_resume_each_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared, initial, _ = _prepare_real_cleanup_cursor(
        tmp_path / "chain", monkeypatch
    )
    session_root = prepared.run_root
    runtime_root = fixture.profile.runtime_root
    output_root = derive_deck_output_binding(
        fixture.profile, fixture.deck_name
    ).output_root
    result_intent = initial.result_intent
    assert isinstance(result_intent, Mapping)
    assert result_intent["physical_disposition"] == "NOT_COMMITTED"
    assert result_intent["runtime_match_status"] == "not_run"
    attempt_id = str(result_intent["apply_attempt_id"])
    assert result_intent["retained_candidate_identity"] is not None
    journal_path = Path(str(result_intent["retained_journal_path"]))
    fence_path = Path(str(result_intent["retained_attempt_record_path"]))
    journal_fingerprint = _file_fingerprint(journal_path)
    fence_fingerprint = _file_fingerprint(fence_path)
    assert journal_fingerprint is not None
    assert fence_fingerprint is not None
    journals = load_runtime_transaction_journals(runtime_root)
    assert len(journals) == 1
    assert journals[0].transaction_id == attempt_id
    assert journals[0].phase.name == "RUNTIME_VERIFIED"
    assert journals[0].owns_target is False
    assert journals[0].candidate_identity == tuple(
        result_intent["retained_candidate_identity"]
    )

    resolution = _terminal_resolution(initial)
    assert resolution["apply_attempt_id"] == attempt_id
    assert resolution["resolved_physical_disposition"] == "NOT_COMMITTED"
    assert resolution["cleanup_stage"] == "PREPARED"
    assert resolution["cleanup_cursor"] == 0
    assert resolution["cleanup_entry_count"] > 0
    roots = {
        str(row["root_role"]): Path(str(row["source_path"]))
        for row in resolution["cleanup_roots"]
    }
    assert set(roots) == {"candidate"}
    candidate_root = roots["candidate"]
    assert path_identity(candidate_root) == tuple(
        resolution["cleanup_roots"][0]["source_identity"]
    )
    assert path_identity(candidate_root.parent) == tuple(
        resolution["cleanup_roots"][0]["expected_parent_identity"]
    )

    inventory_path = Path(str(resolution["cleanup_inventory_path"]))
    inventory_staging = inventory_path.with_name(f"{inventory_path.name}.staged")
    inventory_inner = inventory_staging.with_name(
        f".{inventory_staging.name}.live-start-atomic.tmp"
    )
    assert Path(str(resolution["external_file_action"]["staging_path"])) == (
        inventory_staging
    )
    assert Path(str(resolution["external_file_action"]["inner_temp_path"])) == (
        inventory_inner
    )
    assert not any(
        os.path.lexists(path)
        for path in (inventory_path, inventory_staging, inventory_inner)
    )

    result_pair = _result_pair(session_root)
    result_tree = _physical_tree(session_root / "result")
    output_tree = _physical_tree(output_root)
    profile_fingerprint = _file_fingerprint(operator_profile_path())
    invocation_path = session_root / "receipts/apply_invocation.json"
    invocation_fingerprint = _file_fingerprint(invocation_path)
    admission_path = Path(str(initial.runtime_admission_binding["admission_path"]))
    admission_fingerprint = _file_fingerprint(admission_path)
    assert profile_fingerprint is not None
    assert invocation_fingerprint is not None
    assert admission_fingerprint is not None
    initial_runtime_tree = _physical_tree(runtime_root)
    immutable_kwargs = {
        "initial": initial,
        "result_intent": result_intent,
        "result_pair": result_pair,
        "result_tree": result_tree,
        "session_root": session_root,
        "output_root": output_root,
        "output_tree": output_tree,
        "profile_fingerprint": profile_fingerprint,
        "invocation_path": invocation_path,
        "invocation_fingerprint": invocation_fingerprint,
    }
    oracle_root = tmp_path / "chain-oracles"
    oracle_root.mkdir()
    ordinal = 0

    def kill(point: LiveStartFaultPoint) -> session.LiveStartSession:
        nonlocal ordinal
        ordinal += 1
        current, _ = _kill_cleanup_at(
            session_root=session_root,
            point=point,
            oracle_root=oracle_root,
            ordinal=ordinal,
        )
        _assert_frozen_terminal_surfaces(current=current, **immutable_kwargs)
        if point is _ADMISSION_UNLINKED:
            assert not os.path.lexists(admission_path)
        else:
            assert _file_fingerprint(admission_path) == admission_fingerprint
        return current

    current = kill(_INVENTORY_STAGING_FLUSH)
    resolution = _terminal_resolution(current)
    external = resolution["external_file_action"]
    assert current.terminal_retirement["stage"] == "RECOVERY_PREPARED"
    assert resolution["cleanup_stage"] == "PREPARED"
    assert external["stage"] == "PLANNED"
    first_unbound = _file_fingerprint(inventory_staging)
    assert first_unbound is not None
    assert first_unbound[1:] == (
        external["planned_successor_size"],
        external["planned_successor_sha256"],
    )
    assert not os.path.lexists(inventory_path)
    assert not os.path.lexists(inventory_inner)
    assert _physical_tree(runtime_root) == initial_runtime_tree

    current = kill(_INVENTORY_UNBOUND_RETIRED)
    resolution = _terminal_resolution(current)
    assert current.terminal_retirement["stage"] == "RECOVERY_PREPARED"
    assert resolution["cleanup_stage"] == "PREPARED"
    assert resolution["external_file_action"]["stage"] == "PLANNED"
    assert not any(
        os.path.lexists(path)
        for path in (inventory_path, inventory_staging, inventory_inner)
    )
    assert _physical_tree(runtime_root) == initial_runtime_tree

    current = kill(_INVENTORY_STAGING_BOUND)
    resolution = _terminal_resolution(current)
    external = resolution["external_file_action"]
    assert current.terminal_retirement["stage"] == "RECOVERY_PREPARED"
    assert resolution["cleanup_stage"] == "PREPARED"
    assert external["stage"] == "STAGING_BOUND"
    bound_staging = _file_fingerprint(inventory_staging)
    assert bound_staging is not None
    assert bound_staging == (
        tuple(external["staging_identity"]),
        external["staging_size"],
        external["staging_sha256"],
    )
    assert bound_staging[1:] == (
        external["planned_successor_size"],
        external["planned_successor_sha256"],
    )
    assert not os.path.lexists(inventory_path)
    assert not os.path.lexists(inventory_inner)
    assert _physical_tree(runtime_root) == initial_runtime_tree

    current = kill(_INVENTORY_COMMITTED)
    resolution = _terminal_resolution(current)
    assert current.terminal_retirement["stage"] == "RECOVERY_PREPARED"
    assert resolution["cleanup_stage"] == "PREPARED"
    assert resolution["external_file_action"]["stage"] == "STAGING_BOUND"
    assert _file_fingerprint(inventory_path) == bound_staging
    assert not os.path.lexists(inventory_staging)
    assert not os.path.lexists(inventory_inner)
    assert _physical_tree(runtime_root) == initial_runtime_tree

    current = kill(_INVENTORY_BOUND)
    resolution = _terminal_resolution(current)
    assert current.terminal_retirement["stage"] == "RECOVERY_INVENTORY_BOUND"
    assert resolution["cleanup_stage"] == "INVENTORY_BOUND"
    assert resolution["cleanup_cursor"] == 0
    assert resolution["external_file_action"] is None
    assert tuple(resolution["cleanup_inventory_identity"]) == bound_staging[0]
    assert resolution["cleanup_inventory_size"] == bound_staging[1]
    assert resolution["cleanup_inventory_sha256"] == bound_staging[2]
    inventory_raw = inventory_path.read_bytes()
    inventory = session.TerminalResolutionCleanupInventory(json.loads(inventory_raw))
    assert inventory.canonical_json == inventory_raw
    assert inventory.sha256 == resolution["cleanup_inventory_sha256"]
    assert inventory.size == resolution["cleanup_inventory_size"]
    assert (
        inventory.value["cleanup_manifest_sha256"]
        == (resolution["cleanup_manifest_sha256"])
    )
    assert inventory.value["cleanup_entry_count"] == (resolution["cleanup_entry_count"])
    assert _cleanup_root_projection(
        inventory.value["cleanup_roots"]
    ) == _cleanup_root_projection(resolution["cleanup_roots"])
    entries = tuple(inventory.value["entries"])
    assert len(entries) == resolution["cleanup_entry_count"]
    inventory_roots = {
        str(row["root_role"]): Path(str(row["source_path"]))
        for row in inventory.value["cleanup_roots"]
    }
    assert inventory_roots == roots
    assert _physical_tree(runtime_root) == initial_runtime_tree

    runtime_tree = _physical_tree(runtime_root)
    current = kill(_CLEANING_STARTED)
    resolution = _terminal_resolution(current)
    assert current.terminal_retirement["stage"] == "RECOVERY_CLEANING"
    assert resolution["cleanup_stage"] == "CLEANING"
    assert resolution["cleanup_cursor"] == 0
    assert _physical_tree(runtime_root) == runtime_tree

    expected_runtime_tree = dict(runtime_tree)
    for index, entry in enumerate(entries):
        path = _entry_path(entry, inventory_roots)
        relative = path.relative_to(runtime_root).as_posix()
        before = expected_runtime_tree[relative]
        assert tuple(entry["identity"]) == before[1]
        if entry["entry_kind"] == "file":
            assert entry["size"] == len(before[2])
            assert entry["sha256"] == _sha256_bytes(before[2])
        else:
            assert entry["entry_kind"] == "directory"
            assert entry["size"] is None
            assert entry["sha256"] is None

        current = kill(_ENTRY_DELETED)
        resolution = _terminal_resolution(current)
        assert current.terminal_retirement["stage"] == "RECOVERY_CLEANING"
        assert resolution["cleanup_cursor"] == index
        assert not os.path.lexists(path)
        del expected_runtime_tree[relative]
        assert _physical_tree(runtime_root) == expected_runtime_tree

        current = kill(_CURSOR_ADVANCED)
        resolution = _terminal_resolution(current)
        assert current.terminal_retirement["stage"] == "RECOVERY_CLEANING"
        assert resolution["cleanup_cursor"] == index + 1
        assert _physical_tree(runtime_root) == expected_runtime_tree

    assert not os.path.lexists(candidate_root)
    assert resolution["cleanup_cursor"] == len(entries)

    current = kill(_JOURNAL_DELETED)
    resolution = _terminal_resolution(current)
    assert current.terminal_retirement["stage"] == "RECOVERY_CLEANING"
    assert not os.path.lexists(journal_path)
    del expected_runtime_tree[journal_path.relative_to(runtime_root).as_posix()]
    assert _physical_tree(runtime_root) == expected_runtime_tree

    current = kill(_JOURNAL_RETIRED)
    resolution = _terminal_resolution(current)
    assert current.terminal_retirement["stage"] == "RECOVERY_JOURNAL_RETIRED"
    assert resolution["cleanup_stage"] == "JOURNAL_RETIRED"
    assert _physical_tree(runtime_root) == expected_runtime_tree

    current = kill(_FENCE_DELETED)
    resolution = _terminal_resolution(current)
    assert current.terminal_retirement["stage"] == "RECOVERY_JOURNAL_RETIRED"
    assert not os.path.lexists(fence_path)
    del expected_runtime_tree[fence_path.relative_to(runtime_root).as_posix()]
    assert _physical_tree(runtime_root) == expected_runtime_tree

    current = kill(_FENCE_RETIRED)
    resolution = _terminal_resolution(current)
    assert current.terminal_retirement["stage"] == "RECOVERY_FENCE_RETIRED"
    assert resolution["cleanup_stage"] == "FENCE_RETIRED"
    assert _physical_tree(runtime_root) == expected_runtime_tree

    current = kill(_SIDECAR_DELETED)
    resolution = _terminal_resolution(current)
    assert current.terminal_retirement["stage"] == "RECOVERY_FENCE_RETIRED"
    assert not os.path.lexists(inventory_path)
    assert _physical_tree(runtime_root) == expected_runtime_tree

    current = kill(_INVENTORY_RETIRED)
    resolution = _terminal_resolution(current)
    assert current.terminal_retirement["stage"] == "RECOVERY_INVENTORY_RETIRED"
    assert resolution["cleanup_stage"] == "INVENTORY_RETIRED"
    assert _physical_tree(runtime_root) == expected_runtime_tree

    current = kill(_STABILIZED)
    resolution = _terminal_resolution(current)
    assert current.terminal_retirement["stage"] == "RECOVERY_STABILIZED"
    assert resolution["cleanup_stage"] == "COMPLETE"
    assert _physical_tree(runtime_root) == expected_runtime_tree

    current = kill(_EVIDENCE_RETIRED)
    resolution = _terminal_resolution(current)
    assert current.terminal_retirement["stage"] == "EVIDENCE_RETIRED"
    assert resolution["cleanup_stage"] == "COMPLETE"
    assert _file_fingerprint(admission_path) == admission_fingerprint
    assert _physical_tree(runtime_root) == expected_runtime_tree

    current = kill(_RELEASE_AUTHORIZED)
    resolution = _terminal_resolution(current)
    assert current.terminal_retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"
    assert resolution["cleanup_stage"] == "COMPLETE"
    assert _file_fingerprint(admission_path) == admission_fingerprint
    assert _physical_tree(runtime_root) == expected_runtime_tree

    current = kill(_ADMISSION_UNLINKED)
    resolution = _terminal_resolution(current)
    assert current.terminal_retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"
    assert resolution["cleanup_stage"] == "COMPLETE"
    assert not os.path.lexists(admission_path)
    assert _physical_tree(runtime_root) == expected_runtime_tree
    assert load_runtime_transaction_journals(runtime_root) == ()
    assert not any(
        os.path.lexists(path)
        for path in (candidate_root, inventory_path, inventory_staging, inventory_inner)
    )

    terminal_session_tree = _physical_tree(session_root)
    replay_oracle = tmp_path / "chain-terminal-replay.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(session_root), str(replay_oracle)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    replayed = json.loads(replay_oracle.read_bytes())
    assert replayed["status"] == "FAILED_PRESERVED"
    assert replayed["run_root"] == str(session_root)
    assert replayed["summary_sha256"] == _sha256_bytes(
        result_pair["result/summary.json"]
    )
    assert replayed.pop("apply_entry_counts") == _expected_apply_entry_counts()
    replayed_terminal = session.load_live_start_session(session_root)
    assert replayed["session_sha256"] == replayed_terminal.content_sha256
    _assert_frozen_terminal_surfaces(
        current=replayed_terminal,
        **immutable_kwargs,
    )
    assert replayed_terminal.canonical_json == current.canonical_json
    assert replayed_terminal.session_identity == current.session_identity
    assert _physical_tree(session_root) == terminal_session_tree
    assert _physical_tree(runtime_root) == expected_runtime_tree


def test_terminal_inventory_prepared_hard_kill_rejects_identity_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared, initial, _ = _prepare_real_cleanup_cursor(
        tmp_path / "substitution", monkeypatch
    )
    session_root = prepared.run_root
    runtime_root = fixture.profile.runtime_root
    output_root = derive_deck_output_binding(
        fixture.profile, fixture.deck_name
    ).output_root
    retirement = initial.terminal_retirement
    resolution = _terminal_resolution(initial)
    result_intent = initial.result_intent
    assert isinstance(result_intent, Mapping)
    assert retirement["stage"] == "RECOVERY_PREPARED"
    assert resolution["cleanup_stage"] == "PREPARED"
    assert resolution["cleanup_cursor"] == 0
    assert resolution["cleanup_entry_count"] > 0
    assert resolution["cleanup_inventory_identity"] is None
    external = resolution["external_file_action"]
    assert external["stage"] == "PLANNED"
    assert external["action_kind"] == "commit_bound_terminal_cleanup_inventory"
    inventory_path = Path(str(resolution["cleanup_inventory_path"]))
    inventory_staging = Path(str(external["staging_path"]))
    inventory_inner = Path(str(external["inner_temp_path"]))
    assert not any(
        os.path.lexists(path)
        for path in (inventory_path, inventory_staging, inventory_inner)
    )

    cleanup_roots = tuple(resolution["cleanup_roots"])
    assert len(cleanup_roots) == 1
    root_row = cleanup_roots[0]
    assert root_row["root_role"] == "candidate"
    candidate_root = Path(str(root_row["source_path"]))
    assert path_identity(candidate_root) == tuple(root_row["source_identity"])
    assert path_identity(candidate_root.parent) == tuple(
        root_row["expected_parent_identity"]
    )
    before_root = _physical_tree(candidate_root)
    forged_path = next(
        path for path in sorted(candidate_root.rglob("*")) if path.is_file()
    )
    forged_raw = forged_path.read_bytes()
    original_identity = path_identity(forged_path)
    escrow_root = tmp_path / "identity-substitution-escrow"
    escrow_root.mkdir()
    escrow_path = escrow_root / "original-candidate-leaf"
    for protected_root in (runtime_root, session_root, output_root):
        assert not escrow_path.is_relative_to(protected_root)
    forged_path.replace(escrow_path)
    assert path_identity(escrow_path) == original_identity
    assert escrow_path.read_bytes() == forged_raw
    with forged_path.open("xb") as replacement:
        replacement.write(forged_raw)
        replacement.flush()
        os.fsync(replacement.fileno())
    forged_identity = path_identity(forged_path)
    assert forged_identity != original_identity
    assert forged_path.read_bytes() == forged_raw
    escrow_tree = _physical_tree(escrow_root)
    assert escrow_tree["original-candidate-leaf"] == (
        "file",
        original_identity,
        forged_raw,
    )
    after_root = _physical_tree(candidate_root)
    relative_forged = forged_path.relative_to(candidate_root).as_posix()
    assert set(after_root) == set(before_root)
    assert after_root[relative_forged][0] == "file"
    assert after_root[relative_forged][1] == forged_identity
    assert after_root[relative_forged][2] == forged_raw
    assert before_root[relative_forged][1] == original_identity
    assert {
        key: value for key, value in after_root.items() if key != relative_forged
    } == {key: value for key, value in before_root.items() if key != relative_forged}

    result_pair = _result_pair(session_root)
    result_tree = _physical_tree(session_root / "result")
    session_bytes = (session_root / "session.json").read_bytes()
    session_tree = _physical_tree(session_root)
    runtime_tree = _physical_tree(runtime_root)
    output_tree = _physical_tree(output_root)
    profile_fingerprint = _file_fingerprint(operator_profile_path())
    invocation_path = session_root / "receipts/apply_invocation.json"
    invocation_fingerprint = _file_fingerprint(invocation_path)
    admission_path = Path(str(initial.runtime_admission_binding["admission_path"]))
    admission_fingerprint = _file_fingerprint(admission_path)
    assert profile_fingerprint is not None
    assert invocation_fingerprint is not None
    assert admission_fingerprint is not None
    immutable_kwargs = {
        "initial": initial,
        "result_intent": result_intent,
        "result_pair": result_pair,
        "result_tree": result_tree,
        "session_root": session_root,
        "output_root": output_root,
        "output_tree": output_tree,
        "profile_fingerprint": profile_fingerprint,
        "invocation_path": invocation_path,
        "invocation_fingerprint": invocation_fingerprint,
    }

    for ordinal in (1, 2):
        oracle_path = tmp_path / f"substitution-rejection-{ordinal}.json"
        _spawn_and_join(
            target=_rejected_resume_worker,
            args=(str(session_root), str(oracle_path)),
            expected_exitcode=0,
            timeout_seconds=360,
        )
        rejected = json.loads(oracle_path.read_bytes())
        assert rejected["error_type"] == "ValueError"
        assert rejected["error"] == (
            "runtime_terminal_cleanup_replay_commitment_changed"
        )
        assert rejected["apply_entry_counts"] == _expected_apply_entry_counts(
            recovery=1
        )
        assert (session_root / "session.json").read_bytes() == session_bytes
        rejected_current = session.load_live_start_session(session_root)
        _assert_frozen_terminal_surfaces(
            current=rejected_current,
            **immutable_kwargs,
        )
        assert rejected_current.canonical_json == initial.canonical_json
        assert _physical_tree(session_root) == session_tree
        assert _result_pair(session_root) == result_pair
        assert _physical_tree(runtime_root) == runtime_tree
        assert _physical_tree(candidate_root) == after_root
        assert path_identity(forged_path) == forged_identity
        assert forged_path.read_bytes() == forged_raw
        assert _physical_tree(escrow_root) == escrow_tree
        assert path_identity(escrow_path) == original_identity
        assert escrow_path.read_bytes() == forged_raw
        assert _physical_tree(output_root) == output_tree
        assert _file_fingerprint(operator_profile_path()) == profile_fingerprint
        assert _file_fingerprint(invocation_path) == invocation_fingerprint
        assert _file_fingerprint(admission_path) == admission_fingerprint
        assert not any(
            os.path.lexists(path)
            for path in (inventory_path, inventory_staging, inventory_inner)
        )
