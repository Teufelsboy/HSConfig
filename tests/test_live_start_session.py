from __future__ import annotations

from copy import copy
from hashlib import sha256
import json
import multiprocessing
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace

import pytest

from hsconfig import live_start_session as session
from hsconfig.input_snapshot_manifest import (
    freeze_compiler_inputs,
    load_frozen_compiler_inputs,
)
from hsconfig.operator_profile import (
    derive_deck_output_binding,
    enable_operator_profile,
)
from hsconfig.package_request import FrozenJsonDocument
from hsconfig.package_io import path_identity
from tests.helpers.audited_package_request import (
    audited_request_with_frozen_input_projections,
)


def _new_session(base: Path, *, preview: bool = False) -> tuple[Path, session.LiveStartSession]:
    local_app_data = base / "local"
    root = local_app_data / "HSConfig" / "runs" / ("a" * 32)
    frozen_inputs, manifest_sha256 = _simple_frozen_input_bytes()
    created = session.create_live_start_session(
        session_root=root,
        local_app_data_root=local_app_data,
        repository_root=base / "repository",
        runtime_root=base / "runtime",
        output_base_root=base / "output",
        output_deck_root=base / "output" / "Deck",
        installed_skill_root=base / "skill",
        deck_name="Deck",
        deck_code_sha256="sha256:" + "1" * 64,
        input_snapshot_manifest_sha256=manifest_sha256,
        frozen_input_bytes=frozen_inputs,
        preview_requested=preview,
    )
    return root, created


def _lease(session_root: Path):
    return session.lease_live_start_session(
        session_root,
        local_app_data_root=session_root.parents[2],
    )


def _publish_session_fixture_under_lock(
    *,
    lease: session.LiveStartSessionLease,
    predecessor: session.LiveStartSession,
    value: dict[str, object],
) -> session.LiveStartSession:
    sealed = session._seal_session_value(value, session_identity=None)
    published = session.atomic_write_reserved_bytes(
        path=lease.session_root / "session.json",
        payload=sealed.canonical_json,
        expected_parent_identity=lease.session_root_identity,
        expected_predecessor_identity=predecessor.session_identity,
        expected_predecessor_sha256=(
            f"sha256:{sha256(predecessor.canonical_json).hexdigest()}"
        ),
        maximum_size=session.LIVE_START_SESSION_MAX_BYTES,
    )
    return session._load_session_bytes(
        sealed.canonical_json,
        session_identity=published.identity,
    )


def _atomic_session_cas_and_hard_exit(
    session_root: str,
    predecessor_bytes: bytes,
    predecessor_identity: tuple[int, int, int],
    successor_bytes: bytes,
    fault_point: str,
) -> None:
    root = Path(session_root)
    predecessor = session._load_session_bytes(
        predecessor_bytes,
        session_identity=predecessor_identity,
    )

    def hard_exit(point: str) -> None:
        if point == fault_point:
            os._exit(82)

    with _lease(root) as lease:
        session.atomic_write_reserved_bytes(
            path=root / "session.json",
            payload=successor_bytes,
            expected_parent_identity=lease.session_root_identity,
            expected_predecessor_identity=predecessor.session_identity,
            expected_predecessor_sha256=(
                f"sha256:{sha256(predecessor.canonical_json).hexdigest()}"
            ),
            maximum_size=session.LIVE_START_SESSION_MAX_BYTES,
            fault_hook=hard_exit,
        )


def _commit_shared_session_predecessor_in_process(
    session_root: str,
    predecessor_bytes: bytes,
    predecessor_identity: tuple[int, int, int],
    start: object,
    results: object,
) -> None:
    root = Path(session_root)
    predecessor = session._load_session_bytes(
        predecessor_bytes,
        session_identity=predecessor_identity,
    )
    start.wait()
    try:
        with _lease(root) as lease:
            pending = session._empty_pending_transition(
                session=predecessor,
                operation="install_candidate",
                external_file_action=None,
            )
            session.transition_live_start_session_under_lock(
                session_lease=lease,
                expected_session=predecessor,
                event="same_phase_cas",
                changes={
                    "pending_transition": session._seal_pending(pending)
                },
            )
    except session.SessionConflictError:
        results.put("conflict")
    except BaseException as error:
        results.put(f"error:{type(error).__name__}:{error}")
    else:
        results.put("committed")


def _simple_frozen_input_bytes() -> tuple[dict[str, bytes], str]:
    unsigned_manifest = {
        "schema_version": 1,
        "compiler_inputs": {"fixture": True},
        "operator_bindings": {"fixture": True},
    }
    unsigned_raw = json.dumps(
        unsigned_manifest,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    manifest_sha256 = f"sha256:{sha256(unsigned_raw).hexdigest()}"
    manifest = {
        **unsigned_manifest,
        "content_sha256": manifest_sha256,
    }
    manifest_raw = json.dumps(
        manifest,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return (
        {
            "inputs/input_snapshot_manifest.json": manifest_raw,
            "inputs/deck.json": b'{"deck":[]}',
            "inputs/cards.json": b'{"cards":[]}',
            "inputs/sources.json": b'{"sources":[]}',
        },
        manifest_sha256,
    )


def _create_session_and_hard_exit(
    *,
    session_root: str,
    local_app_data_root: str,
    frozen_input_bytes: dict[str, bytes],
    input_snapshot_manifest_sha256: str,
    fault_point: str,
) -> None:
    root = Path(session_root)
    base = Path(local_app_data_root).parent

    def hard_exit(point: str) -> None:
        if point == fault_point:
            os._exit(81)

    session.create_live_start_session(
        session_root=root,
        local_app_data_root=Path(local_app_data_root),
        repository_root=base / "repository",
        runtime_root=base / "runtime",
        output_base_root=base / "output",
        output_deck_root=base / "output" / "Deck",
        installed_skill_root=base / "skill",
        deck_name="Deck",
        deck_code_sha256="sha256:" + "1" * 64,
        input_snapshot_manifest_sha256=(
            input_snapshot_manifest_sha256
        ),
        frozen_input_bytes=frozen_input_bytes,
        preview_requested=False,
        _fault_hook=hard_exit,
    )


def test_session_has_closed_layout_and_canonical_self_digest() -> None:
    with TemporaryDirectory() as temporary:
        root, created = _new_session(Path(temporary))
        raw = (root / "session.json").read_bytes()
        value = json.loads(raw)
        claimed = value.pop("content_sha256")
        unsigned = (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode()
        assert claimed == f"sha256:{sha256(unsigned).hexdigest()}"
        assert created.content_sha256 == claimed
        assert {
            path.relative_to(root).as_posix() for path in root.rglob("*")
        } == {
            "inputs",
            "inputs/input_snapshot_manifest.json",
            "inputs/deck.json",
            "inputs/cards.json",
            "inputs/sources.json",
            "session.json",
        }
        assert created.to_value().keys() == session._SESSION_FIELDS


def test_session_allows_only_the_declared_phase_transitions() -> None:
    expected = (
        session.LiveStartPhase.INPUT_FROZEN,
        session.LiveStartPhase.CANDIDATE_DRAFTED,
        session.LiveStartPhase.CANDIDATE_VALIDATED,
        session.LiveStartPhase.REVIEW_APPROVED,
        session.LiveStartPhase.PACKAGE_VALIDATED,
        session.LiveStartPhase.PREPUBLICATION_CHECK_PASSED,
        session.LiveStartPhase.PUBLICATION_COMMITTED,
        session.LiveStartPhase.APPLY_STARTED,
        session.LiveStartPhase.APPLY_COMMITTED,
        session.LiveStartPhase.RUNTIME_MATCHED,
    )
    assert tuple(session.LiveStartPhase) == expected
    assert session.LiveStartPhase.CANDIDATE_VALIDATED not in (
        session.PHASE_TRANSITIONS[session.LiveStartPhase.INPUT_FROZEN]
    )
    assert session.LiveStartPhase.CANDIDATE_DRAFTED in (
        session.PHASE_TRANSITIONS[session.LiveStartPhase.CANDIDATE_DRAFTED]
    )

    with TemporaryDirectory() as temporary:
        _root, frozen = _new_session(Path(temporary))
        unbound_publication = frozen.to_value()
        unbound_publication["phase"] = "PUBLICATION_COMMITTED"
        with pytest.raises(
            session.SessionValidationError,
            match="publication",
        ):
            session._seal_session_value(
                unbound_publication,
                session_identity=frozen.session_identity,
            )


def test_session_cas_rejects_stale_bytes_identity_or_digest() -> None:
    with TemporaryDirectory() as temporary:
        root, predecessor = _new_session(Path(temporary))
        with _lease(root) as lease:
            successor_value = predecessor.to_value()
            successor_value.pop("content_sha256")
            successor_value["phase"] = "CANDIDATE_DRAFTED"
            successor = _publish_session_fixture_under_lock(
                lease=lease,
                predecessor=predecessor,
                value=successor_value,
            )
            assert successor.phase is session.LiveStartPhase.CANDIDATE_DRAFTED
            with pytest.raises(session.SessionConflictError, match="stale"):
                session.transition_live_start_session_under_lock(
                    session_lease=lease,
                    expected_session=predecessor,
                    event="same_phase_cas",
                    changes={"pending_transition": {}},
                )


def test_candidate_revision_invalidates_candidate_review_and_downstream_receipts() -> None:
    with TemporaryDirectory() as temporary:
        _root, frozen = _new_session(Path(temporary))
        drafted_value = frozen.to_value()
        drafted_value.pop("content_sha256")
        drafted_value.update(
            {
                "phase": "CANDIDATE_DRAFTED",
                "artifact_bindings": {
                    **frozen.artifact_bindings,
                    "starter/starter_config_candidate.json": "sha256:" + "3" * 64,
                    "receipts/candidate_validation.json": "sha256:" + "4" * 64,
                    "starter/starter_config_review.json": "sha256:" + "5" * 64,
                },
            }
        )
        drafted = session._seal_session_value(
            drafted_value,
            session_identity=frozen.session_identity,
        )
        revised = session._seal_session_value(
            session._apply_session_update(
                drafted,
                session.LiveStartSessionUpdate(event="technical_failure"),
            ),
            session_identity=frozen.session_identity,
        )
        assert revised.revisions_used == 1
        assert "receipts/candidate_validation.json" not in revised.artifact_bindings
        assert "starter/starter_config_review.json" not in revised.artifact_bindings
        with pytest.raises(session.SessionConflictError, match="revision"):
            session._apply_session_update(
                revised,
                session.LiveStartSessionUpdate(event="technical_failure"),
            )
        with pytest.raises(session.SessionConflictError, match="intent"):
            session._apply_session_update(
                revised,
                session.LiveStartSessionUpdate(event="replacement_draft"),
            )

        replacement_bindings = {
            **revised.artifact_bindings,
            "starter/starter_config_candidate.json": "sha256:" + "6" * 64,
        }
        pending = session._empty_pending_transition(
            session=revised,
            operation="install_candidate",
            external_file_action=None,
        )
        pending.update(
            {
                "stage": "PRIMARY_APPLIED",
                "target_candidate_revision": 2,
                "target_revisions_used": 1,
                "successor_artifact_bindings": replacement_bindings,
            }
        )
        pending_value = revised.to_value()
        pending_value.pop("content_sha256")
        pending_value["pending_transition"] = session._seal_pending(pending)
        prepared = session._seal_session_value(
            pending_value,
            session_identity=frozen.session_identity,
        )
        replacement = session._seal_session_value(
            session._apply_session_update(
                prepared,
                session.LiveStartSessionUpdate(
                    event="replacement_draft",
                    changes={
                        "artifact_bindings": replacement_bindings,
                        "pending_transition": None,
                    },
                ),
                receipt_authorized=True,
            ),
            session_identity=frozen.session_identity,
        )
        assert replacement.candidate_revision == 2


def test_preview_intent_is_boolean_immutable_and_resume_bound() -> None:
    with TemporaryDirectory() as temporary:
        root, cursor = _new_session(Path(temporary), preview=True)
        assert cursor.preview_requested is True
        with _lease(root) as lease:
            with pytest.raises(session.SessionValidationError, match="fields"):
                session.transition_live_start_session_under_lock(
                    session_lease=lease,
                    expected_session=cursor,
                    event="same_phase_cas",
                    changes={"preview_requested": False},
                )


def test_session_lock_lives_outside_the_closed_run_directory() -> None:
    with TemporaryDirectory() as temporary:
        root, _cursor = _new_session(Path(temporary))
        lock = root.parent.parent / "locks" / f"live-start-{root.name}.lock"
        assert lock.is_file()
        assert root not in lock.parents
        assert lock not in root.rglob("*")


def test_two_processes_cannot_commit_the_same_session_predecessor() -> None:
    with TemporaryDirectory() as temporary:
        root, predecessor = _new_session(Path(temporary))
        assert predecessor.session_identity is not None
        context = multiprocessing.get_context("spawn")
        start = context.Barrier(2)
        results = context.Queue()
        workers = [
            context.Process(
                target=_commit_shared_session_predecessor_in_process,
                args=(
                    str(root),
                    predecessor.canonical_json,
                    predecessor.session_identity,
                    start,
                    results,
                ),
            )
            for _ in range(2)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=20)
            assert not worker.is_alive()
            assert worker.exitcode == 0
        outcomes = sorted(results.get(timeout=2) for _ in workers)
        assert outcomes == ["committed", "conflict"]


def test_capability_smoke_exercises_real_thread_and_copy_boundaries(
    tmp_path: Path,
) -> None:
    session_root, _cursor = _new_session(tmp_path)
    escaped: list[BaseException] = []
    with _lease(session_root) as lease:
        sibling = copy(lease)
        assert sibling.lock_token is lease.lock_token

        def cross_thread() -> None:
            try:
                session.load_live_start_session_under_lock(session_lease=sibling)
            except BaseException as error:
                escaped.append(error)

        worker = Thread(target=cross_thread)
        worker.start()
        worker.join()
        assert len(escaped) == 1
        assert isinstance(escaped[0], session.SessionCapabilityError)
        assert session.load_live_start_session_under_lock(
            session_lease=lease
        ).phase is session.LiveStartPhase.INPUT_FROZEN

    with pytest.raises(session.SessionCapabilityError, match="expired"):
        session.load_live_start_session_under_lock(session_lease=sibling)


def _seal_literal_document(value: dict[str, object]) -> dict[str, object]:
    unsigned = json.loads(json.dumps(value))
    raw = (
        json.dumps(
            unsigned,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    return {**unsigned, "content_sha256": f"sha256:{sha256(raw).hexdigest()}"}


def _terminal_resolution_fixture() -> dict[str, object]:
    sha = "sha256:" + "3" * 64
    value: dict[str, object] = {
        "schema_version": 1,
        "resolution_kind": "live_start_terminal_resolution_evidence",
        "run_id": "a" * 32,
        "apply_attempt_id": "b" * 32,
        "predecessor_attempt_record_path": None,
        "predecessor_attempt_record_identity": None,
        "predecessor_attempt_record_sha256": None,
        "predecessor_journal_path": None,
        "predecessor_journal_identity": None,
        "predecessor_journal_sha256": None,
        "predecessor_transaction_temp_path": None,
        "predecessor_transaction_temp_parent_identity": None,
        "predecessor_transaction_temp_identity": None,
        "predecessor_transaction_temp_size": None,
        "predecessor_transaction_temp_sha256": None,
        "predecessor_transaction_temp_classification": None,
        "predecessor_transaction_temp_origin": None,
        "external_file_action": None,
        "owner_retirement": None,
        "predecessor_target_owner_journal_path": None,
        "predecessor_target_owner_journal_identity": None,
        "predecessor_target_owner_journal_sha256": None,
        "allowed_attempt_record_successor_state": None,
        "allowed_journal_successor_phase": None,
        "successor_attempt_record_path": None,
        "successor_attempt_record_identity": None,
        "successor_attempt_record_sha256": None,
        "successor_journal_path": None,
        "successor_journal_identity": None,
        "successor_journal_sha256": None,
        "successor_transaction_temp_path": None,
        "successor_transaction_temp_parent_identity": None,
        "successor_transaction_temp_identity": None,
        "successor_transaction_temp_size": None,
        "successor_transaction_temp_sha256": None,
        "successor_transaction_temp_classification": None,
        "successor_transaction_temp_origin": None,
        "planned_journal_successor_path": None,
        "planned_journal_successor_parent_identity": None,
        "planned_journal_successor_phase": None,
        "planned_journal_successor_size": None,
        "planned_journal_successor_sha256": None,
        "successor_target_owner_journal_path": None,
        "successor_target_owner_journal_identity": None,
        "successor_target_owner_journal_sha256": None,
        "candidate_path": None,
        "candidate_parent_identity": None,
        "predecessor_candidate_identity": None,
        "successor_candidate_identity": None,
        "resolved_physical_disposition": "NOT_COMMITTED",
        "cleanup_stage": None,
        "cleanup_inventory_path": None,
        "cleanup_inventory_parent_identity": None,
        "cleanup_inventory_identity": None,
        "cleanup_inventory_size": None,
        "cleanup_inventory_sha256": None,
        "cleanup_manifest_sha256": None,
        "cleanup_entry_count": None,
        "cleanup_cursor": None,
        "cleanup_roots": None,
        "package_root_sha256": sha,
        "last_apply_receipt_sha256": None,
        "runtime_state_sha256": None,
        "deck_config_ini_sha256": None,
        "runtime_match_status": "not_run",
        "runtime_match_sha256": None,
    }
    return _seal_literal_document(value)


def _terminal_retirement_fixture(
    *,
    operation: str,
    stage: str,
    resolution: dict[str, object] | None,
) -> dict[str, object]:
    root = Path.cwd() / "runtime"
    identity = [1, 2, 0o100644]
    sha = "sha256:" + "8" * 64
    return session.seal_embedded_document(
        "terminal_retirement",
        {
            "schema_version": 1,
            "retirement_kind": "live_start_terminal_retirement",
            "run_id": "a" * 32,
            "apply_attempt_id": "b" * 32,
            "operation": operation,
            "stage": stage,
            "source_terminal_session_sha256": "sha256:" + "6" * 64,
            "result_intent_sha256": "sha256:" + "7" * 64,
            "terminal_resolution_evidence": resolution,
            "runtime_admission_path": str(root / "admission.json"),
            "runtime_admission_parent_identity": identity,
            "runtime_admission_identity": identity,
            "runtime_admission_sha256": sha,
            "retained_attempt_record_path": None,
            "retained_attempt_record_identity": None,
            "retained_attempt_record_sha256": None,
            "retained_journal_path": None,
            "retained_journal_identity": None,
            "retained_journal_sha256": None,
            "retained_target_owner_journal_path": None,
            "retained_target_owner_journal_identity": None,
            "retained_target_owner_journal_sha256": None,
        },
    )


def _owner_retirement_fixture() -> dict[str, object]:
    identity = [1, 2, 0o100644]
    sha = "sha256:" + "4" * 64
    runtime = Path.cwd() / "runtime"
    value: dict[str, object] = {
        "schema_version": 1,
        "evidence_kind": "live_start_owner_retirement_evidence",
        "stage": "PREPARED_PLANNED",
        "tombstone_path": str(
            runtime / ".hsconfig" / "owner-retirements" / "a.json"
        ),
        "tombstone_parent_identity": identity,
        "tombstone_identity": None,
        "tombstone_sha256": sha,
        "retired_owner_transaction_id": "a" * 32,
        "initial_owner_journal_path": str(
            runtime / ".hsconfig" / "transactions" / "a.json"
        ),
        "initial_owner_journal_identity": identity,
        "initial_owner_journal_sha256": sha,
        "current_owner_journal_identity": identity,
        "current_owner_journal_sha256": sha,
        "retired_target_path": str(runtime / "CustomConfig" / "Deck"),
        "retired_target_parent_identity": identity,
        "retired_target_identity": identity,
        "retired_target_tree_sha256": sha,
        "successor_transaction_id": "b" * 32,
        "successor_package_root_sha256": sha,
        "successor_owner_journal_path": str(
            runtime / ".hsconfig" / "transactions" / "b.json"
        ),
        "successor_owner_journal_identity": identity,
        "successor_owner_journal_sha256": sha,
        "cleanup_manifest_sha256": sha,
        "cleanup_entry_count": 0,
        "cleanup_cursor": 0,
        "planned_completed_tombstone_size": None,
        "planned_completed_tombstone_sha256": None,
        "next_entry_relative_path": None,
        "next_entry_kind": None,
        "next_entry_identity": None,
        "next_entry_parent_identity": None,
        "next_entry_size": None,
        "next_entry_sha256": None,
        "old_owner_journal_retired": False,
    }
    return _seal_literal_document(value)


def _terminal_cleanup_inventory_fixture() -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 1,
        "inventory_kind": "live_start_terminal_resolution_cleanup_inventory",
        "run_id": "a" * 32,
        "apply_attempt_id": "b" * 32,
        "runtime_root_path": str(Path.cwd() / "runtime"),
        "runtime_root_identity": [1, 2, 0o040755],
        "cleanup_roots": [],
        "cleanup_manifest_sha256": "sha256:" + "5" * 64,
        "cleanup_entry_count": 0,
        "entries": [],
    }
    return _seal_literal_document(value)


def test_terminal_resolution_evidence_has_closed_predecessor_successor_matrix() -> None:
    valid = _terminal_resolution_fixture()
    evidence = session.TerminalResolutionEvidence(valid)
    assert evidence.value["content_sha256"] == valid["content_sha256"]

    unknown = {**valid, "unknown": True}
    with pytest.raises(session.SessionValidationError, match="fields"):
        session.TerminalResolutionEvidence(unknown)

    impossible = dict(valid)
    impossible.pop("content_sha256")
    impossible["resolved_physical_disposition"] = "IMPOSSIBLE"
    with pytest.raises(session.SessionValidationError, match="disposition"):
        session.TerminalResolutionEvidence(
            _seal_literal_document(impossible)
        )


def test_owner_retirement_evidence_action_and_nullability_matrix_is_closed() -> None:
    valid = _owner_retirement_fixture()
    assert session.OwnerRetirementEvidence(valid).value["stage"] == (
        "PREPARED_PLANNED"
    )

    invalid = {**valid, "old_owner_journal_retired": None}
    invalid = _seal_literal_document(
        {key: value for key, value in invalid.items() if key != "content_sha256"}
    )
    with pytest.raises(session.SessionValidationError, match="owner"):
        session.OwnerRetirementEvidence(invalid)

    missing_committed_identity = {**valid, "stage": "PREPARED"}
    missing_committed_identity = _seal_literal_document(
        {
            key: value
            for key, value in missing_committed_identity.items()
            if key != "content_sha256"
        }
    )
    with pytest.raises(session.SessionValidationError, match="tombstone"):
        session.OwnerRetirementEvidence(missing_committed_identity)


def test_terminal_resolution_cleanup_inventory_is_closed_bounded_and_cursor_bound() -> None:
    valid = _terminal_cleanup_inventory_fixture()
    inventory = session.TerminalResolutionCleanupInventory(valid)
    assert inventory.canonical_json.endswith(b"\n")
    assert inventory.size == len(inventory.canonical_json)

    count_mismatch = {**valid, "cleanup_entry_count": 1}
    count_mismatch = _seal_literal_document(
        {
            key: value
            for key, value in count_mismatch.items()
            if key != "content_sha256"
        }
    )
    with pytest.raises(session.SessionValidationError, match="count"):
        session.TerminalResolutionCleanupInventory(count_mismatch)


def test_terminal_cleanup_inventory_uses_planned_staging_bound_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inventory_value = _terminal_cleanup_inventory_fixture()
    inventory_value = {
        **inventory_value,
        "runtime_root_path": str(tmp_path),
        "runtime_root_identity": list(path_identity(tmp_path)),
    }
    inventory_value = _seal_literal_document(
        {
            key: value
            for key, value in inventory_value.items()
            if key != "content_sha256"
        }
    )
    inventory = session.TerminalResolutionCleanupInventory(inventory_value)
    final_path = tmp_path / "terminal-resolution-cleanup.json"
    staging_path = tmp_path / "terminal-resolution-cleanup.json.staged"
    inner_path = tmp_path / (
        ".terminal-resolution-cleanup.json.staged.live-start-atomic.tmp"
    )
    parent_identity = list(path_identity(tmp_path))
    external_action = session.seal_embedded_document(
        "external_file_action",
        {
            "schema_version": 1,
            "action_kind": "commit_bound_terminal_cleanup_inventory",
            "action_index": 0,
            "stage": "PLANNED",
            "final_path": str(final_path),
            "staging_path": str(staging_path),
            "inner_temp_path": str(inner_path),
            "parent_identity": parent_identity,
            "predecessor_state": "absent",
            "predecessor_identity": None,
            "predecessor_size": None,
            "predecessor_sha256": None,
            "planned_successor_size": inventory.size,
            "planned_successor_sha256": inventory.sha256,
            "staging_identity": None,
            "staging_size": None,
            "staging_sha256": None,
            "commit_mode": "create_no_replace",
        },
    )
    resolution_value = _terminal_resolution_fixture()
    resolution_value.update(
        {
            "external_file_action": dict(external_action),
            "cleanup_stage": "PREPARED",
            "cleanup_inventory_path": str(final_path),
            "cleanup_inventory_parent_identity": parent_identity,
            "cleanup_inventory_identity": None,
            "cleanup_inventory_size": inventory.size,
            "cleanup_inventory_sha256": inventory.sha256,
            "cleanup_manifest_sha256": inventory.value[
                "cleanup_manifest_sha256"
            ],
            "cleanup_entry_count": 0,
            "cleanup_cursor": 0,
            "cleanup_roots": [],
        }
    )
    resolution = session.TerminalResolutionEvidence(
        _seal_literal_document(
            {
                key: value
                for key, value in resolution_value.items()
                if key != "content_sha256"
            }
        )
    )
    admission = tmp_path / "runtime-admission.json"
    retirement = session.seal_embedded_document(
        "terminal_retirement",
        {
            "schema_version": 1,
            "retirement_kind": "live_start_terminal_retirement",
            "run_id": "a" * 32,
            "apply_attempt_id": "b" * 32,
            "operation": "release_resolved_terminal",
            "stage": "RECOVERY_PREPARED",
            "source_terminal_session_sha256": "sha256:" + "6" * 64,
            "result_intent_sha256": "sha256:" + "7" * 64,
            "terminal_resolution_evidence": dict(resolution.value),
            "runtime_admission_path": str(admission),
            "runtime_admission_parent_identity": parent_identity,
            "runtime_admission_identity": [1, 3, 0o100644],
            "runtime_admission_sha256": "sha256:" + "8" * 64,
            "retained_attempt_record_path": None,
            "retained_attempt_record_identity": None,
            "retained_attempt_record_sha256": None,
            "retained_journal_path": None,
            "retained_journal_identity": None,
            "retained_journal_sha256": None,
            "retained_target_owner_journal_path": None,
            "retained_target_owner_journal_identity": None,
            "retained_target_owner_journal_sha256": None,
        },
    )
    receipt = object.__new__(session.TerminalResolutionStepReceipt)
    captured: list[session.TerminalResolutionPhysicalPostcondition] = []

    def execute_step(**kwargs: object) -> session.TerminalResolutionStepReceipt:
        physical_action = kwargs["physical_action"]
        assert callable(physical_action)
        postcondition = physical_action()
        assert isinstance(
            postcondition,
            session.TerminalResolutionPhysicalPostcondition,
        )
        captured.append(postcondition)
        return receipt

    monkeypatch.setattr(
        session,
        "_execute_terminal_resolution_physical_step",
        execute_step,
    )
    monkeypatch.setattr(
        session,
        "_require_terminal_physical_authorization_context",
        lambda **_kwargs: None,
    )
    expected = SimpleNamespace(terminal_retirement=retirement)
    authorization = object.__new__(session.TerminalRetirementAuthorization)
    materialized = session.publish_terminal_cleanup_inventory_under_lock(
        session_lease=object(),
        expected_recovery_prepared_session=expected,
        terminal_authorization=authorization,
        inventory=inventory,
        action="materialize",
    )
    assert materialized.action == "materialize"
    assert materialized.staging is not None
    assert materialized.published is None
    assert materialized.staging.identity == path_identity(staging_path)
    staged_retirement = captured.pop().evidence["terminal_retirement"]
    staged_resolution = staged_retirement["terminal_resolution_evidence"]
    assert staged_resolution["external_file_action"]["stage"] == (
        "STAGING_BOUND"
    )

    expected = SimpleNamespace(terminal_retirement=staged_retirement)
    committed = session.publish_terminal_cleanup_inventory_under_lock(
        session_lease=object(),
        expected_recovery_prepared_session=expected,
        terminal_authorization=authorization,
        inventory=inventory,
        action="commit",
    )
    assert committed.action == "commit"
    assert committed.staging is None
    assert committed.published is not None
    assert committed.published.identity == materialized.staging.identity
    assert final_path.read_bytes() == inventory.canonical_json
    assert not staging_path.exists()
    committed_retirement = captured.pop().evidence["terminal_retirement"]
    committed_resolution = committed_retirement[
        "terminal_resolution_evidence"
    ]
    assert committed_retirement["stage"] == "RECOVERY_INVENTORY_BOUND"
    assert committed_resolution["cleanup_stage"] == "INVENTORY_BOUND"
    assert committed_resolution["external_file_action"] is None


def test_terminal_cleanup_inventory_retires_unbound_staging_without_promotion() -> None:
    with pytest.raises(session.SessionValidationError, match="retire_action"):
        session.retire_terminal_cleanup_inventory_under_lock(
            session_lease=object(),
            expected_resolution_session=object(),
            terminal_authorization=object(),
            action="promote",
        )


def test_terminal_resolution_cleanup_has_exact_stage_nullability_and_physical_matrix() -> None:
    planned = {
        "operation": "release_resolved_terminal",
        "stage": "RECOVERY_PREPARED",
        "terminal_resolution_evidence": {
            "cleanup_stage": "PREPARED",
            "external_file_action": {"stage": "PLANNED"},
        },
    }
    assert session._terminal_action_for_retirement(planned) == (
        "materialize_terminal_cleanup_inventory_staging"
    )
    planned["terminal_resolution_evidence"]["external_file_action"][
        "stage"
    ] = "STAGING_BOUND"
    assert session._terminal_action_for_retirement(planned) == (
        "commit_bound_terminal_cleanup_inventory"
    )
    planned["terminal_resolution_evidence"]["external_file_action"] = None
    assert session._terminal_action_for_retirement(planned) == (
        "physical_recovery_advanced"
    )


def test_session_and_result_atomic_temp_exceptions_are_exact_and_receipts_use_staging(
    tmp_path: Path,
) -> None:
    root, _cursor = _new_session(tmp_path)
    result_dir = root / "result"
    result_dir.mkdir()
    reserved = result_dir / ".summary.json.live-start-atomic.tmp"
    reserved.write_bytes(b"partial")
    open_result = SimpleNamespace(
        artifact_bindings=_cursor.artifact_bindings,
        result_intent={"content_sha256": "sha256:" + "1" * 64},
        terminal_status=None,
        pending_transition=None,
        apply_recovery=None,
        terminal_retirement=None,
    )
    with _lease(root) as lease:
        session._validate_run_layout_under_lock(
            session_lease=lease,
            session=open_result,
        )
        closed_result = SimpleNamespace(
            **{**vars(open_result), "terminal_status": "FAILED_PRESERVED"}
        )
        with pytest.raises(session.SessionLayoutError, match="reserved"):
            session._validate_run_layout_under_lock(
                session_lease=lease,
                session=closed_result,
            )


def test_pending_transition_rejects_unknown_paths_mixed_artifacts_or_stale_predecessor(
    tmp_path: Path,
) -> None:
    root, cursor = _new_session(tmp_path)
    (root / "unknown.json").write_text("{}", encoding="utf-8")
    with _lease(root) as lease:
        with pytest.raises(session.SessionLayoutError, match="unbound"):
            session.transition_live_start_session_under_lock(
                session_lease=lease,
                expected_session=cursor,
                event="initial_draft",
            )
        with pytest.raises(session.SessionLayoutError, match="unbound"):
            session._mint_authorization_under_lock(
                authorization_type=session.RuntimeObservationAuthorization,
                session_lease=lease,
                expected_session=cursor,
                family="runtime_observation",
                action="observe_unknown",
            )


def test_external_file_action_staging_bound_matrix_is_closed(
    tmp_path: Path,
) -> None:
    final_path = tmp_path / "authority.json"
    staging_path = tmp_path / "authority.json.staged"
    unsigned = {
        "schema_version": 1,
        "action_kind": "commit_bound_authority",
        "action_index": 0,
        "stage": "PLANNED",
        "final_path": str(final_path),
        "staging_path": str(staging_path),
        "inner_temp_path": str(
            tmp_path / ".authority.json.staged.live-start-atomic.tmp"
        ),
        "parent_identity": list(path_identity(tmp_path)),
        "predecessor_state": "absent",
        "predecessor_identity": None,
        "predecessor_size": None,
        "predecessor_sha256": None,
        "planned_successor_size": 3,
        "planned_successor_sha256": "sha256:" + "1" * 64,
        "staging_identity": None,
        "staging_size": None,
        "staging_sha256": None,
        "commit_mode": "create_no_replace",
    }
    assert session.seal_embedded_document(
        "external_file_action", unsigned
    )["stage"] == "PLANNED"

    with pytest.raises(session.SessionValidationError, match="mode"):
        session.seal_embedded_document(
            "external_file_action",
            {**unsigned, "commit_mode": "replace_exact"},
        )


def test_success_ack_step_evidence_is_separate_nonpersisted_receipt_family() -> None:
    session_bearer = SimpleNamespace(
        active=True,
        thread_id=__import__("threading").get_ident(),
    )
    opaque = session._OpaqueBearer(
        session_bearer=session_bearer,
        family="terminal_retirement",
        cursor_sha256="sha256:" + "1" * 64,
        action="delete_cleanup_entry",
    )
    authorization = session.TerminalRetirementAuthorization._mint(opaque)

    with pytest.raises(session.SessionCapabilityError, match="forged"):
        session._execute_terminal_resolution_physical_step(
            terminal_authorization=authorization,
            action="delete_cleanup_entry",
            physical_action=lambda: session.SuccessAckStepEvidence(
                action="delete_cleanup_entry"
            ),
        )


def test_runtime_admission_release_executor_binds_path_parent_old_identity_and_digest(
    tmp_path: Path,
) -> None:
    session_bearer = SimpleNamespace(
        active=True,
        thread_id=__import__("threading").get_ident(),
    )
    opaque = session._OpaqueBearer(
        session_bearer=session_bearer,
        family="terminal_retirement",
        cursor_sha256="sha256:" + "1" * 64,
        action="release_runtime_admission",
    )
    historical_identity = (1, 2, 0o100644)
    opaque.successor = {
        "admission_path": tmp_path / "runtime-admission.json",
        "admission_parent_identity": path_identity(tmp_path),
        "historical_admission_identity": historical_identity,
        "historical_admission_sha256": "sha256:" + "2" * 64,
    }
    authorization = session.TerminalRetirementAuthorization._mint(opaque)

    with pytest.raises(session.SessionCapabilityError, match="forged"):
        session._execute_runtime_admission_release(
            terminal_authorization=authorization,
            action="release_runtime_admission",
            physical_action=lambda: session.RuntimeAdmissionReleasePostcondition(
                admission_path=tmp_path / "other.json",
                admission_parent_identity=path_identity(tmp_path),
                historical_admission_identity=historical_identity,
                historical_admission_sha256="sha256:" + "2" * 64,
                disposition="already_absent",
                foreign_successor_identity=None,
                foreign_successor_sha256=None,
            ),
        )


def test_output_child_bootstrap_rejects_constructed_stale_or_wrong_action_receipt() -> None:
    with pytest.raises(session.SessionCapabilityError, match="carrier"):
        session.advance_output_child_bootstrap_under_lock(
            session_lease=object(),
            expected_bootstrap_session=object(),
            transition="claim_unlinked",
            bootstrap_authorization=object(),
            physical_step_receipt=object(),
        )


def test_atomic_session_cas_hard_exit_reconciles_reserved_temp_without_layout_residue(
    tmp_path: Path,
) -> None:
    context = multiprocessing.get_context("spawn")
    for fault_point, expected_phase in (
        ("temp_flushed", session.LiveStartPhase.INPUT_FROZEN),
        ("after_replace", session.LiveStartPhase.CANDIDATE_DRAFTED),
    ):
        case_root = tmp_path / fault_point
        case_root.mkdir()
        root, predecessor = _new_session(case_root)
        assert predecessor.session_identity is not None
        successor_value = predecessor.to_value()
        successor_value.pop("content_sha256")
        successor_value["phase"] = "CANDIDATE_DRAFTED"
        successor = session._seal_session_value(
            successor_value,
            session_identity=None,
        )
        worker = context.Process(
            target=_atomic_session_cas_and_hard_exit,
            args=(
                str(root),
                predecessor.canonical_json,
                predecessor.session_identity,
                successor.canonical_json,
                fault_point,
            ),
        )
        worker.start()
        worker.join(timeout=20)
        assert not worker.is_alive()
        assert worker.exitcode == 82

        reserved = root / ".session.json.live-start-atomic.tmp"
        with _lease(root) as lease:
            session._reconcile_session_temp_under_lock(
                session_lease=lease,
                expected_session=(
                    predecessor if fault_point == "temp_flushed" else None
                ),
            )
            resumed = session.load_live_start_session_under_lock(
                session_lease=lease
            )
        assert resumed.phase is expected_phase
        assert not reserved.exists()


def test_runtime_layout_bootstrap_schema_and_fixed_order_are_closed(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / "runtime"
    identity = [1, 2, 0o040755]
    paths = (
        runtime_root / "CustomConfig",
        runtime_root / ".hsconfig" / "transactions",
        runtime_root / ".hsconfig" / "staging",
        runtime_root / ".hsconfig" / "receipts",
        runtime_root / ".hsconfig" / "receipts" / "state-key",
        runtime_root / ".hsconfig" / "attempt-retention",
        runtime_root / ".hsconfig" / "owner-retirements",
    )
    rows = [
        {
            "role": role,
            "path": str(path),
            "expected_parent_identity": identity,
            "predecessor_state": "existing",
            "predecessor_identity": identity,
            "successor_identity": identity,
        }
        for role, path in zip(
            session.RUNTIME_LAYOUT_DIRECTORY_ROLES,
            paths,
            strict=True,
        )
    ]
    valid = session.seal_embedded_document(
        "runtime_layout_bootstrap",
        {
            "schema_version": 1,
            "binding_kind": "live_start_runtime_layout_bootstrap",
            "run_id": "a" * 32,
            "apply_attempt_id": "b" * 32,
            "runtime_root": str(runtime_root),
            "runtime_root_identity": identity,
            "stage": "COMPLETE",
            "next_directory_index": 7,
            "directory_count": 7,
            "directories": rows,
        },
    )
    assert session.RuntimeLayoutBootstrapEvidence(valid).value["stage"] == (
        "COMPLETE"
    )

    with pytest.raises(session.SessionValidationError, match="fields"):
        session.RuntimeLayoutBootstrapEvidence({**valid, "unknown": True})

    wrong_paths = session._thaw(valid)
    wrong_paths.pop("content_sha256")
    wrong_paths["directories"][0]["path"] = str(runtime_root / "Other")
    with pytest.raises(session.SessionValidationError, match="path"):
        session.seal_embedded_document(
            "runtime_layout_bootstrap",
            wrong_paths,
        )


def test_terminal_retirement_advance_closes_ack_journal_and_pure_cas_edges() -> None:
    prepared = {"operation": "ack_success", "stage": "PREPARED"}

    assert session._terminal_action_for_retirement(
        prepared,
        attempt_acknowledgement={
            "acknowledgement_action": "retain_target_owner_delete_fence"
        },
    ) == "retire_ack_fence"
    assert session._terminal_action_for_retirement(
        prepared,
        attempt_acknowledgement={
            "acknowledgement_action": "delete_nonowning_attempt_and_fence"
        },
    ) == "retire_ack_journal"
    assert session._terminal_action_for_retirement(
        {"operation": "ack_success", "stage": "ACK_JOURNAL_RETIRED"},
        attempt_acknowledgement={
            "acknowledgement_action": "delete_nonowning_attempt_and_fence"
        },
    ) == "retire_ack_fence"

    predecessor = _terminal_retirement_fixture(
        operation="release_not_committed",
        stage="PREPARED",
        resolution=None,
    )
    successor_value = dict(predecessor)
    successor_value.pop("content_sha256")
    successor_value["stage"] = "EVIDENCE_RETIRED"
    successor = session.seal_embedded_document(
        "terminal_retirement", successor_value
    )
    session._validate_terminal_retirement_successor(
        predecessor=predecessor,
        successor=successor,
        transition="evidence_retired",
    )

    rewritten = dict(successor)
    rewritten.pop("content_sha256")
    rewritten["result_intent_sha256"] = "sha256:" + "9" * 64
    rewritten = session.seal_embedded_document(
        "terminal_retirement", rewritten
    )
    with pytest.raises(session.SessionCapabilityError, match="changed"):
        session._validate_terminal_retirement_successor(
            predecessor=predecessor,
            successor=rewritten,
            transition="evidence_retired",
        )

    skipped_value = dict(predecessor)
    skipped_value.pop("content_sha256")
    skipped_value["stage"] = "ADMISSION_RELEASE_AUTHORIZED"
    skipped = session.seal_embedded_document(
        "terminal_retirement", skipped_value
    )
    with pytest.raises(session.SessionCapabilityError, match="successor"):
        session._validate_terminal_retirement_successor(
            predecessor=predecessor,
            successor=skipped,
            transition="admission_release_authorized",
        )

    partial_evidence = dict(predecessor)
    partial_evidence.pop("content_sha256")
    partial_evidence["retained_journal_path"] = str(
        Path.cwd() / "runtime" / "journal.json"
    )
    with pytest.raises(session.SessionValidationError, match="journal"):
        session.seal_embedded_document(
            "terminal_retirement", partial_evidence
        )


def test_terminal_resolution_cleanup_cas_allows_only_exact_cursor_successors() -> None:
    predecessor = _terminal_retirement_fixture(
        operation="release_resolved_terminal",
        stage="RECOVERY_PREPARED",
        resolution=_terminal_resolution_fixture(),
    )
    successor_resolution = dict(
        predecessor["terminal_resolution_evidence"]
    )
    successor_resolution.pop("content_sha256")
    successor_resolution.update(
        {
            "successor_attempt_record_path": str(
                Path.cwd() / "runtime" / "attempt.json"
            ),
            "successor_attempt_record_identity": [1, 3, 0o100644],
            "successor_attempt_record_sha256": "sha256:" + "a" * 64,
        }
    )
    successor_resolution = session._seal_terminal_resolution(
        successor_resolution
    )
    successor_value = dict(predecessor)
    successor_value.pop("content_sha256")
    successor_value["terminal_resolution_evidence"] = successor_resolution
    successor = session.seal_embedded_document(
        "terminal_retirement", successor_value
    )
    session._validate_terminal_resolution_successor(
        predecessor=predecessor,
        successor=successor,
        transition="physical_recovery_advanced",
    )

    rewritten_value = dict(successor)
    rewritten_value.pop("content_sha256")
    rewritten_resolution = dict(
        rewritten_value["terminal_resolution_evidence"]
    )
    rewritten_resolution.pop("content_sha256")
    rewritten_resolution["package_root_sha256"] = "sha256:" + "b" * 64
    rewritten_value["terminal_resolution_evidence"] = (
        session._seal_terminal_resolution(rewritten_resolution)
    )
    rewritten = session.seal_embedded_document(
        "terminal_retirement", rewritten_value
    )
    with pytest.raises(session.SessionCapabilityError, match="changed"):
        session._validate_terminal_resolution_successor(
            predecessor=predecessor,
            successor=rewritten,
            transition="physical_recovery_advanced",
        )

    skipped_value = dict(predecessor)
    skipped_value.pop("content_sha256")
    skipped_value["stage"] = "RECOVERY_FENCE_RETIRED"
    skipped = session.seal_embedded_document(
        "terminal_retirement", skipped_value
    )
    with pytest.raises(session.SessionCapabilityError, match="successor"):
        session._validate_terminal_resolution_successor(
            predecessor=predecessor,
            successor=skipped,
            transition="fence_retired",
        )


def test_session_lease_token_is_nonforgeable_thread_bound_and_expires_on_exit(
    tmp_path: Path,
) -> None:
    root, cursor = _new_session(tmp_path)
    lock_path = root.parent.parent / "locks" / f"live-start-{root.name}.lock"
    forged_bearer = session._SessionBearer(
        session_root=root,
        session_root_identity=path_identity(root),
        session_lock_path=lock_path,
        session_lock_identity=path_identity(lock_path),
    )
    forged_lease = session.LiveStartSessionLease(
        session_root=root,
        session_root_identity=path_identity(root),
        session_lock_path=lock_path,
        session_lock_identity=path_identity(lock_path),
        lock_token=session.SessionLockToken._mint(forged_bearer),
    )

    with pytest.raises(session.SessionCapabilityError, match="forged"):
        session.load_live_start_session_under_lock(session_lease=forged_lease)
    with pytest.raises(session.SessionCapabilityError, match="forged"):
        session.transition_live_start_session_under_lock(
            session_lease=forged_lease,
            expected_session=cursor,
            event="initial_draft",
        )

    with _lease(root) as real_lease:
        duplicate_token_lease = session.LiveStartSessionLease(
            session_root=real_lease.session_root,
            session_root_identity=real_lease.session_root_identity,
            session_lock_path=real_lease.session_lock_path,
            session_lock_identity=real_lease.session_lock_identity,
            lock_token=session.SessionLockToken._mint(
                real_lease.lock_token._bearer
            ),
        )
        with pytest.raises(session.SessionCapabilityError, match="forged"):
            session.load_live_start_session_under_lock(
                session_lease=duplicate_token_lease
            )

    with pytest.raises(session.SessionCapabilityError, match="expired"):
        session.load_live_start_session_under_lock(session_lease=real_lease)


def test_direct_opaque_construction_cannot_authorize_physical_callback() -> None:
    fake_session_bearer = SimpleNamespace(
        active=True,
        thread_id=__import__("threading").get_ident(),
    )
    forged_opaque = session._OpaqueBearer(
        session_bearer=fake_session_bearer,
        family="nonterminal_apply_recovery",
        cursor_sha256="sha256:" + "1" * 64,
        action="observe_not_committed",
    )
    forged = session.RuntimeAttemptRecoveryAuthorization._mint(forged_opaque)
    callback_called = False

    def callback() -> session.RuntimeApplyRecoveryPhysicalPostcondition:
        nonlocal callback_called
        callback_called = True
        return session.RuntimeApplyRecoveryPhysicalPostcondition(
            action="observe_not_committed"
        )

    with pytest.raises(session.SessionCapabilityError, match="forged"):
        session._execute_apply_recovery_physical_step(
            recovery_authorization=forged,
            action="observe_not_committed",
            physical_action=callback,
        )
    assert callback_called is False


def test_physical_executor_consumes_before_callback_and_validates_postcondition(
    tmp_path: Path,
) -> None:
    root, cursor = _new_session(tmp_path)
    action = "observe_not_committed"
    with _lease(root) as lease:
        stale_authorization = session._mint_authorization_under_lock(
            authorization_type=session.RuntimeAttemptRecoveryAuthorization,
            session_lease=lease,
            expected_session=cursor,
            family="nonterminal_apply_recovery",
            action=action,
        )
        pending = session._empty_pending_transition(
            session=cursor,
            operation="install_candidate",
            external_file_action=None,
        )
        advanced = session.transition_live_start_session_under_lock(
            session_lease=lease,
            expected_session=cursor,
            event="same_phase_cas",
            changes={
                "pending_transition": session._seal_pending(pending)
            },
        )
        stale_called = False

        def stale_callback() -> session.RuntimeApplyRecoveryPhysicalPostcondition:
            nonlocal stale_called
            stale_called = True
            return session.RuntimeApplyRecoveryPhysicalPostcondition(
                action=action
            )

        with pytest.raises(session.SessionCapabilityError, match="cursor"):
            session._execute_physical_step(
                authorization=stale_authorization,
                authorization_type=session.RuntimeAttemptRecoveryAuthorization,
                receipt_type=session.ApplyRecoveryStepReceipt,
                postcondition_type=(
                    session.RuntimeApplyRecoveryPhysicalPostcondition
                ),
                family="nonterminal_apply_recovery",
                action=action,
                physical_action=stale_callback,
            )
        assert stale_called is False

        authorization = session._mint_authorization_under_lock(
            authorization_type=session.RuntimeAttemptRecoveryAuthorization,
            session_lease=lease,
            expected_session=advanced,
            family="nonterminal_apply_recovery",
            action=action,
        )
        calls = 0

        def callback() -> session.RuntimeApplyRecoveryPhysicalPostcondition:
            nonlocal calls
            calls += 1
            return session.RuntimeApplyRecoveryPhysicalPostcondition(
                action=action
            )

        receipt = session._execute_physical_step(
            authorization=authorization,
            authorization_type=session.RuntimeAttemptRecoveryAuthorization,
            receipt_type=session.ApplyRecoveryStepReceipt,
            postcondition_type=session.RuntimeApplyRecoveryPhysicalPostcondition,
            family="nonterminal_apply_recovery",
            action=action,
            physical_action=callback,
        )
        assert isinstance(receipt, session.ApplyRecoveryStepReceipt)
        assert calls == 1
        with pytest.raises(session.SessionCapabilityError):
            session._execute_physical_step(
                authorization=authorization,
                authorization_type=session.RuntimeAttemptRecoveryAuthorization,
                receipt_type=session.ApplyRecoveryStepReceipt,
                postcondition_type=(
                    session.RuntimeApplyRecoveryPhysicalPostcondition
                ),
                family="nonterminal_apply_recovery",
                action=action,
                physical_action=callback,
            )
        assert calls == 1

        invalid = session._mint_authorization_under_lock(
            authorization_type=session.RuntimeAttemptRecoveryAuthorization,
            session_lease=lease,
            expected_session=advanced,
            family="nonterminal_apply_recovery",
            action=action,
        )
        with pytest.raises(session.SessionCapabilityError, match="postcondition"):
            session._execute_physical_step(
                authorization=invalid,
                authorization_type=session.RuntimeAttemptRecoveryAuthorization,
                receipt_type=session.ApplyRecoveryStepReceipt,
                postcondition_type=(
                    session.RuntimeApplyRecoveryPhysicalPostcondition
                ),
                family="nonterminal_apply_recovery",
                action=action,
                physical_action=lambda: (
                    session.RuntimeApplyRecoveryPhysicalPostcondition(
                        action="observe_pending"
                    )
                ),
            )


def test_pending_transition_is_closed_self_digested_and_resumes_exact_physical_change(
    tmp_path: Path,
) -> None:
    root, cursor = _new_session(tmp_path)
    with _lease(root) as lease:
        with pytest.raises(session.SessionConflictError, match="intent"):
            session.transition_live_start_session_under_lock(
                session_lease=lease,
                expected_session=cursor,
                event="initial_draft",
            )
        unchanged = session.load_live_start_session_under_lock(
            session_lease=lease
        )
        assert unchanged.canonical_json == cursor.canonical_json

        with pytest.raises(session.SessionValidationError, match="null"):
            session.transition_live_start_session_under_lock(
                session_lease=lease,
                expected_session=cursor,
                event="same_phase_cas",
                changes={"publication_binding": None},
            )

        wrong_stage = session._empty_pending_transition(
            session=cursor,
            operation="install_candidate",
            external_file_action=None,
        )
        wrong_stage["stage"] = "PRIMARY_APPLIED"
        wrong_stage["target_phase"] = "CANDIDATE_DRAFTED"
        with pytest.raises(session.SessionValidationError, match="stage"):
            session.transition_live_start_session_under_lock(
                session_lease=lease,
                expected_session=cursor,
                event="same_phase_cas",
                changes={
                    "pending_transition": session._seal_pending(wrong_stage)
                },
            )

        prepared = session._empty_pending_transition(
            session=cursor,
            operation="install_candidate",
            external_file_action=None,
        )
        prepared_cursor = session.transition_live_start_session_under_lock(
            session_lease=lease,
            expected_session=cursor,
            event="same_phase_cas",
            changes={
                "pending_transition": session._seal_pending(prepared)
            },
        )
        bypass = session._thaw(prepared_cursor.pending_transition)
        bypass.pop("content_sha256")
        bypass["stage"] = "PRIMARY_APPLIED"
        with pytest.raises(session.SessionCapabilityError, match="receipt"):
            session.transition_live_start_session_under_lock(
                session_lease=lease,
                expected_session=prepared_cursor,
                event="same_phase_cas",
                changes={
                    "pending_transition": session._seal_pending(bypass)
                },
            )


def test_validation_receipts_have_exact_closed_phase_bound_schemas() -> None:
    with pytest.raises(session.SessionValidationError, match="digest"):
        session.seal_validation_receipt(
            receipt_kind="candidate_validation",
            unsigned_value={
                "run_id": "a" * 32,
                "candidate_revision": 1,
                "starter_context_sha256": None,
                "candidate_sha256": None,
                "status": "valid",
                "findings": [],
            },
        )

    with pytest.raises(session.SessionValidationError, match="digest"):
        session.seal_validation_receipt(
            receipt_kind="review_validation",
            unsigned_value={
                "run_id": "a" * 32,
                "candidate_revision": 1,
                "starter_context_sha256": None,
                "candidate_sha256": "sha256:" + "1" * 64,
                "review_sha256": None,
                "review_status": "approved",
                "confidence": "high",
            },
        )

    package = {
        field_name: None
        for field_name in session._RECEIPT_FIELDS["package_validation"]
        if field_name
        not in {"schema_version", "receipt_kind", "content_sha256"}
    }
    package.update(
        {
            "run_id": "a" * 32,
            "candidate_revision": 1,
            "apply_gate_allowed": True,
        }
    )
    with pytest.raises(session.SessionValidationError, match="digest"):
        session.seal_validation_receipt(
            receipt_kind="package_validation",
            unsigned_value=package,
        )


def test_resume_revalidates_every_completed_phase_receipt(
    tmp_path: Path,
) -> None:
    root, cursor = _new_session(tmp_path)
    starter_root = root / "starter"
    receipts_root = root / "receipts"
    starter_root.mkdir()
    receipts_root.mkdir()
    context_raw = b'{"context":"bound"}\n'
    candidate_raw = b'{"candidate":"bound"}\n'
    context_path = starter_root / "starter_context.json"
    candidate_path = starter_root / "starter_config_candidate.json"
    context_path.write_bytes(context_raw)
    candidate_path.write_bytes(candidate_raw)
    mismatched_receipt = session.seal_validation_receipt(
        receipt_kind="candidate_validation",
        unsigned_value={
            "run_id": cursor.run_id,
            "candidate_revision": cursor.candidate_revision,
            "starter_context_sha256": "sha256:" + "7" * 64,
            "candidate_sha256": "sha256:" + "8" * 64,
            "status": "valid",
            "findings": [],
        },
    )
    receipt_raw = session._canonical_json(
        session._thaw(mismatched_receipt)
    )
    receipt_path = receipts_root / "candidate_validation.json"
    receipt_path.write_bytes(receipt_raw)

    value = cursor.to_value()
    value.pop("content_sha256")
    value["phase"] = session.LiveStartPhase.CANDIDATE_VALIDATED.value
    value["artifact_bindings"] = {
        **dict(cursor.artifact_bindings),
        "starter/starter_context.json": (
            f"sha256:{sha256(context_raw).hexdigest()}"
        ),
        "starter/starter_config_candidate.json": (
            f"sha256:{sha256(candidate_raw).hexdigest()}"
        ),
        "receipts/candidate_validation.json": (
            f"sha256:{sha256(receipt_raw).hexdigest()}"
        ),
    }
    with _lease(root) as lease:
        cursor = _publish_session_fixture_under_lock(
            lease=lease,
            predecessor=cursor,
            value=value,
        )
        with pytest.raises(session.SessionConflictError, match="binding"):
            session.validate_resume_under_lock(
                session_lease=lease,
                expected_deck_code_sha256=cursor.deck_code_sha256,
                expected_input_snapshot_manifest_sha256=(
                    cursor.input_snapshot_manifest_sha256
                ),
            )


def test_session_embeds_result_intent_and_acknowledgement_status_matrix(
    tmp_path: Path,
) -> None:
    _root, cursor = _new_session(tmp_path, preview=False)
    intent = {
        field_name: None
        for field_name in session._RESULT_INTENT_FIELDS
        if field_name not in {"content_sha256"}
    }
    intent.update(
        {
            "schema_version": 1,
            "intent_kind": "live_start_result_intent",
            "run_id": cursor.run_id,
            "terminal_status": "PREVIEW_READY",
            "deck_name": cursor.deck_name,
            "candidate_revision": cursor.candidate_revision,
            "unique_main_deck_cards": 1,
            "configured_cards": 1,
            "deliberately_unconfigured_cards": 0,
            "review_confidence": None,
            "visible_limitations": [],
            "raw_apply_status": "applied",
            "physical_disposition": None,
            "runtime_match_status": "not_run",
            "retained_safe_state": "ACTIVE_RUNTIME_MATCHED",
        }
    )
    sealed_intent = session.seal_embedded_document("result_intent", intent)
    false_terminal = cursor.to_value()
    false_terminal["result_intent"] = session._thaw(sealed_intent)
    false_terminal["terminal_status"] = "PREVIEW_READY"

    with pytest.raises(session.SessionValidationError, match="preview"):
        session._seal_session_value(
            false_terminal,
            session_identity=cursor.session_identity,
        )

    publication = {
        "revision": "revisions/sha256-" + "4" * 64,
        "content_root_sha256": "sha256:" + "5" * 64,
    }
    preview_intent = {
        field_name: None
        for field_name in session._RESULT_INTENT_FIELDS
    }
    preview_intent.update(
        {
            "run_id": cursor.run_id,
            "terminal_status": "PREVIEW_READY",
            "deck_name": cursor.deck_name,
            "candidate_revision": cursor.candidate_revision,
            "unique_main_deck_cards": 1,
            "configured_cards": 1,
            "deliberately_unconfigured_cards": 0,
            "review_confidence": "high",
            "visible_limitations": [],
            "publication_revision": publication["revision"],
            "publication_content_root_sha256": publication[
                "content_root_sha256"
            ],
            "raw_apply_status": None,
            "physical_disposition": None,
            "runtime_match_status": "not_run",
            "retained_safe_state": (
                "PUBLISHED_PREVIEW_RUNTIME_UNCHANGED"
            ),
            "error_code": None,
        }
    )
    matrix_value = {
        "run_id": cursor.run_id,
        "deck_name": cursor.deck_name,
        "candidate_revision": cursor.candidate_revision,
        "preview_requested": True,
        "result_intent": preview_intent,
        "terminal_status": None,
        "attempt_acknowledgement": None,
        "publication_binding": publication,
        "apply_invocation_sha256": None,
        "runtime_admission_binding": None,
        "runtime_layout_bootstrap": None,
        "apply_recovery": None,
    }
    session._validate_terminal_status_matrix(
        value=matrix_value,
        phase=session.LiveStartPhase.PUBLICATION_COMMITTED,
    )
    mismatched_preview = json.loads(json.dumps(matrix_value))
    mismatched_preview["result_intent"]["publication_revision"] = (
        "revisions/sha256-" + "6" * 64
    )
    with pytest.raises(session.SessionValidationError, match="publication"):
        session._validate_terminal_status_matrix(
            value=mismatched_preview,
            phase=session.LiveStartPhase.PUBLICATION_COMMITTED,
        )

    unresolved = json.loads(json.dumps(matrix_value))
    unresolved["preview_requested"] = False
    unresolved["apply_invocation_sha256"] = "sha256:" + "7" * 64
    unresolved["runtime_admission_binding"] = {
        "admission_path": str(tmp_path / "admission.json"),
        "admission_parent_identity": [1, 2, 0o040755],
        "admission_identity": [3, 4, 0o100644],
        "admission_sha256": "sha256:" + "8" * 64,
    }
    unresolved["apply_recovery"] = {"recovery_stage": "CLOSED"}
    unresolved_intent = unresolved["result_intent"]
    unresolved_intent.update(
        {
            "terminal_status": "APPLIED_BUT_NOT_VERIFIED",
            "apply_attempt_id": "b" * 32,
            "raw_apply_status": "applied",
            "physical_disposition": "COMMITTED",
            "runtime_match_status": "mismatch",
            "runtime_match_sha256": "sha256:" + "9" * 64,
            "runtime_admission_path": str(tmp_path / "admission.json"),
            "runtime_admission_parent_identity": [1, 2, 0o040755],
            "runtime_admission_identity": [3, 4, 0o100644],
            "runtime_admission_sha256": "sha256:" + "8" * 64,
            "retained_safe_state": "ATTEMPT_EVIDENCE_RETAINED",
            "error_code": "runtime_match_failed",
        }
    )
    with pytest.raises(session.SessionValidationError, match="recovery"):
        session._validate_terminal_status_matrix(
            value=unresolved,
            phase=session.LiveStartPhase.APPLY_COMMITTED,
        )


def _apply_recovery_fixture() -> dict[str, object]:
    value: dict[str, object] = {
        field_name: None
        for field_name in session._APPLY_RECOVERY_FIELDS
        if field_name != "content_sha256"
    }
    value.update(
        {
            "schema_version": 1,
            "recovery_kind": "live_start_runtime_apply_recovery_evidence",
            "recovery_stage": "ACTIVE",
            "run_id": "a" * 32,
            "apply_attempt_id": "b" * 32,
            "apply_invocation_sha256": "sha256:" + "1" * 64,
            "runtime_admission_path": str(
                Path.cwd() / "runtime-admission.json"
            ),
            "runtime_admission_parent_identity": [1, 2, 0o040755],
            "runtime_admission_identity": [3, 4, 0o100644],
            "runtime_admission_sha256": "sha256:" + "2" * 64,
            "package_root_sha256": "sha256:" + "3" * 64,
            "runtime_root": str(Path.cwd() / "runtime"),
            "runtime_root_identity": [5, 6, 0o040755],
            "install_route": "new_target",
            "action_index": 0,
            "expected_action": "observe_not_committed",
            "runtime_match_status": "not_run",
        }
    )
    return _seal_literal_document(value)


def test_apply_recovery_evidence_has_closed_cursor_and_nullability(
    tmp_path: Path,
) -> None:
    _root, _cursor = _new_session(tmp_path)
    valid = _apply_recovery_fixture()
    assert session.RuntimeApplyRecoveryEvidence(valid).value[
        "expected_action"
    ] == "observe_not_committed"

    partial_attempt = {
        **valid,
        "predecessor_attempt_record_path": str(tmp_path / "attempt.json"),
    }
    partial_attempt = _seal_literal_document(
        {
            key: item
            for key, item in partial_attempt.items()
            if key != "content_sha256"
        }
    )
    with pytest.raises(session.SessionValidationError, match="attempt"):
        session.RuntimeApplyRecoveryEvidence(partial_attempt)

    closed_without_disposition = {
        **valid,
        "recovery_stage": "CLOSED",
        "expected_action": None,
    }
    closed_without_disposition = _seal_literal_document(
        {
            key: item
            for key, item in closed_without_disposition.items()
            if key != "content_sha256"
        }
    )
    with pytest.raises(session.SessionValidationError, match="closed"):
        session.RuntimeApplyRecoveryEvidence(closed_without_disposition)


def test_apply_recovery_temp_and_candidate_fields_are_jointly_closed(
    tmp_path: Path,
) -> None:
    _root, _cursor = _new_session(tmp_path)
    valid = _apply_recovery_fixture()
    partial_temp = {
        **valid,
        "predecessor_transaction_temp_path": str(tmp_path / "legacy.tmp"),
        "predecessor_transaction_temp_classification": "legacy_uuid",
    }
    partial_temp = _seal_literal_document(
        {
            key: item
            for key, item in partial_temp.items()
            if key != "content_sha256"
        }
    )
    with pytest.raises(session.SessionValidationError, match="temp"):
        session.RuntimeApplyRecoveryEvidence(partial_temp)

    partial_candidate = {
        **valid,
        "candidate_path": str(tmp_path / "Candidate"),
    }
    partial_candidate = _seal_literal_document(
        {
            key: item
            for key, item in partial_candidate.items()
            if key != "content_sha256"
        }
    )
    with pytest.raises(session.SessionValidationError, match="candidate"):
        session.RuntimeApplyRecoveryEvidence(partial_candidate)


def test_apply_recovery_action_matrix_and_rollover_are_exhaustive() -> None:
    predecessor = _apply_recovery_fixture()
    skipped = {
        **predecessor,
        "recovery_stage": "CLOSED",
        "action_index": 999,
        "expected_action": None,
        "stable_physical_disposition": "COMMITTED",
    }
    skipped = _seal_literal_document(
        {
            key: item
            for key, item in skipped.items()
            if key != "content_sha256"
        }
    )

    with pytest.raises(session.SessionCapabilityError, match="successor"):
        session._validate_apply_recovery_physical_successor(
            predecessor=predecessor,
            successor=skipped,
            action="observe_not_committed",
        )

    rewritten = {
        **predecessor,
        "action_index": 1,
        "expected_action": "materialize_file_action_staging",
        "last_apply_receipt_sha256": "sha256:" + "a" * 64,
    }
    rewritten = _seal_literal_document(
        {
            key: item
            for key, item in rewritten.items()
            if key != "content_sha256"
        }
    )
    with pytest.raises(session.SessionCapabilityError, match="history"):
        session._validate_apply_recovery_physical_successor(
            predecessor=predecessor,
            successor=rewritten,
            action="observe_not_committed",
        )

    contradictory = {
        **predecessor,
        "action_index": 1,
        "expected_action": "materialize_file_action_staging",
        "stable_physical_disposition": "NOT_COMMITTED",
    }
    contradictory = _seal_literal_document(
        {
            key: item
            for key, item in contradictory.items()
            if key != "content_sha256"
        }
    )
    with pytest.raises(session.SessionValidationError, match="matrix"):
        session.RuntimeApplyRecoveryEvidence(contradictory)

    changed_observation_history = {
        **predecessor,
        "action_index": 1,
        "expected_action": None,
        "stable_physical_disposition": "NOT_COMMITTED",
        "predecessor_attempt_record_path": str(
            Path.cwd() / "runtime" / "foreign-attempt.json"
        ),
        "predecessor_attempt_record_identity": [1, 2, 0o100644],
        "predecessor_attempt_record_sha256": "sha256:" + "c" * 64,
    }
    changed_observation_history = _seal_literal_document(
        {
            key: item
            for key, item in changed_observation_history.items()
            if key != "content_sha256"
        }
    )
    with pytest.raises(session.SessionCapabilityError, match="history"):
        session._validate_apply_recovery_physical_successor(
            predecessor=predecessor,
            successor=changed_observation_history,
            action="observe_not_committed",
        )

    closable = {
        **predecessor,
        "expected_action": None,
        "stable_physical_disposition": "NOT_COMMITTED",
    }
    closable = _seal_literal_document(
        {
            key: item
            for key, item in closable.items()
            if key != "content_sha256"
        }
    )
    closed = {
        **closable,
        "recovery_stage": "CLOSED",
    }
    closed = _seal_literal_document(
        {
            key: item
            for key, item in closed.items()
            if key != "content_sha256"
        }
    )
    session._validate_apply_recovery_closure_successor(
        predecessor=closable,
        successor=closed,
    )
    rewritten_closed = {
        **closed,
        "package_root_sha256": "sha256:" + "b" * 64,
    }
    rewritten_closed = _seal_literal_document(
        {
            key: item
            for key, item in rewritten_closed.items()
            if key != "content_sha256"
        }
    )
    with pytest.raises(session.SessionCapabilityError, match="closure"):
        session._validate_apply_recovery_closure_successor(
            predecessor=closable,
            successor=rewritten_closed,
        )


def test_runtime_observation_receipt_rejects_constructed_swapped_stale_cross_pair_or_reused_values(
    tmp_path: Path,
) -> None:
    root_a, cursor_a = _new_session(tmp_path / "a")
    root_b, cursor_b = _new_session(tmp_path / "b")
    attempt_id = "c" * 32

    with _lease(root_a) as lease_a:
        authorization = session._authorize_runtime_observation_under_lock(
            session_lease=lease_a,
            expected_session=cursor_a,
            observation_family="first_install",
            apply_attempt_id=attempt_id,
        )
        receipt = session._execute_runtime_observation(
            observation_authorization=authorization,
            observation_family="first_install",
            read_only_observation=lambda: session.RuntimeObservationPostcondition(
                action=attempt_id,
                observation_family="first_install",
                evidence={},
            ),
        )

        with _lease(root_b) as lease_b:
            with pytest.raises(session.SessionCapabilityError, match="session"):
                session._consume_runtime_observation_receipt_under_lock(
                    receipt=receipt,
                    session_lease=lease_b,
                    expected_session=cursor_b,
                    observation_family="first_install",
                    apply_attempt_id=attempt_id,
                )

        observed = session._consume_runtime_observation_receipt_under_lock(
            receipt=receipt,
            session_lease=lease_a,
            expected_session=cursor_a,
            observation_family="first_install",
            apply_attempt_id=attempt_id,
        )
        assert observed.action == attempt_id

        with pytest.raises(session.SessionCapabilityError):
            session._consume_runtime_observation_receipt_under_lock(
                receipt=receipt,
                session_lease=lease_a,
                expected_session=cursor_a,
                observation_family="first_install",
                apply_attempt_id=attempt_id,
            )


def test_closed_physical_layout_rejects_canonical_but_unbound_files(
    tmp_path: Path,
) -> None:
    root, _cursor = _new_session(tmp_path)
    result_root = root / "result"
    result_root.mkdir()
    unbound = result_root / "summary.json"
    unbound.write_bytes(b"{}\n")

    with _lease(root) as lease:
        with pytest.raises(session.SessionLayoutError, match="unbound"):
            session.load_live_start_session_under_lock(session_lease=lease)

    unbound.unlink()
    result_root.rmdir()
    if os.name == "nt":
        ads = Path(f"{root}:foreign")
        ads.write_bytes(b"foreign")
        try:
            with pytest.raises(session.SessionLayoutError, match="stream"):
                with _lease(root) as lease:
                    session.load_live_start_session_under_lock(
                        session_lease=lease
                    )
        finally:
            ads.unlink(missing_ok=True)


def test_create_requires_canonical_localappdata_roots_and_rejects_overlap_before_write(
    tmp_path: Path,
) -> None:
    local_app_data = tmp_path / "local"
    run_id = "d" * 32
    forbidden = {
        "repository_root": tmp_path / "repository",
        "runtime_root": tmp_path / "runtime",
        "output_base_root": tmp_path / "output",
        "output_deck_root": tmp_path / "output" / "Deck",
        "installed_skill_root": tmp_path / "skill",
    }
    frozen_inputs, manifest_sha256 = _simple_frozen_input_bytes()

    with pytest.raises(session.SessionValidationError, match="canonical"):
        session.create_live_start_session(
            session_root=local_app_data / "Other" / "runs" / run_id,
            local_app_data_root=local_app_data,
            deck_name="Deck",
            deck_code_sha256="sha256:" + "1" * 64,
            input_snapshot_manifest_sha256=manifest_sha256,
            frozen_input_bytes=frozen_inputs,
            preview_requested=False,
            **forbidden,
        )
    assert not (local_app_data / "HSConfig").exists()

    canonical = local_app_data / "HSConfig" / "runs" / run_id
    with pytest.raises(session.SessionValidationError, match="overlap"):
        session.create_live_start_session(
            session_root=canonical,
            local_app_data_root=local_app_data,
            deck_name="Deck",
            deck_code_sha256="sha256:" + "1" * 64,
            input_snapshot_manifest_sha256=manifest_sha256,
            frozen_input_bytes=frozen_inputs,
            preview_requested=False,
            **{**forbidden, "repository_root": local_app_data},
        )
    assert not (local_app_data / "HSConfig").exists()

    created = session.create_live_start_session(
        session_root=canonical,
        local_app_data_root=local_app_data,
        deck_name="Deck",
        deck_code_sha256="sha256:" + "1" * 64,
        input_snapshot_manifest_sha256=manifest_sha256,
        frozen_input_bytes=frozen_inputs,
        preview_requested=False,
        **forbidden,
    )
    assert created.run_id == run_id
    assert canonical.is_dir()
    assert (
        local_app_data
        / "HSConfig"
        / "locks"
        / f"live-start-{run_id}.lock"
    ).is_file()

    with pytest.raises(
        session.SessionValidationError,
        match="not_canonical",
    ):
        with session.lease_live_start_session(
            canonical,
            local_app_data_root=tmp_path / "foreign-local",
        ):
            pytest.fail("noncanonical lease unexpectedly opened")


def test_creation_installs_real_task2_frozen_inputs_before_session_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, projections = audited_request_with_frozen_input_projections(
        tmp_path,
        "MechPala",
    )
    preconfig = request.snapshot.general_preconfig.to_value()
    local_app_data = tmp_path / "local-app-data"
    runtime_root = tmp_path / "runtime"
    output_base_root = tmp_path / "outputs"
    local_app_data.mkdir()
    runtime_root.mkdir()
    output_base_root.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    profile = enable_operator_profile(
        runtime_root=runtime_root,
        output_base_root=output_base_root,
        expected_predecessor_sha256=None,
    )
    deck_name = str(preconfig["deck_identity"]["deck_name"])
    frozen = freeze_compiler_inputs(
        snapshot=request.snapshot,
        deck=projections["deck"],
        full_cards=projections["full_cards"],
        collectible_cards=projections["collectible_cards"],
        source_acquisition=projections["source_acquisition"],
        source_documents=projections["source_documents"],
        globalvalues_baseline=projections["globalvalues_baseline"],
        bound_date="2026-08-25",
        runtime_grammar_version="visionai-runtime-v1",
        compiler_contract_id="hsconfig-live-start-v1",
        operator_profile=profile,
        deck_output_binding=derive_deck_output_binding(
            profile,
            deck_name,
        ),
    )
    cards_envelope = FrozenJsonDocument.from_value(
        {
            "full_cards": frozen.full_cards.to_value(),
            "collectible_cards": frozen.collectible_cards.to_value(),
            "globalvalues_baseline": (
                frozen.globalvalues_baseline.to_value()
            ),
        }
    )
    sources_envelope = FrozenJsonDocument.from_value(
        {
            "source_acquisition": frozen.source_acquisition.to_value(),
            "source_documents": frozen.source_documents.to_value(),
        }
    )
    frozen_bytes = {
        "inputs/input_snapshot_manifest.json": (
            frozen.manifest.document.canonical_json
        ),
        "inputs/deck.json": frozen.deck.canonical_json,
        "inputs/cards.json": cards_envelope.canonical_json,
        "inputs/sources.json": sources_envelope.canonical_json,
    }
    session_root = (
        local_app_data / "HSConfig" / "runs" / ("e" * 32)
    )

    created = session.create_live_start_session(
        session_root=session_root,
        local_app_data_root=local_app_data,
        repository_root=tmp_path / "repository",
        runtime_root=runtime_root,
        output_base_root=output_base_root,
        output_deck_root=output_base_root / deck_name,
        installed_skill_root=tmp_path / "skill",
        deck_name=deck_name,
        deck_code_sha256=(
            frozen.manifest.compiler_inputs.to_value()[
                "deck_code_sha256"
            ]
        ),
        input_snapshot_manifest_sha256=(
            frozen.manifest.document.content_sha256
        ),
        frozen_input_bytes=frozen_bytes,
        preview_requested=True,
    )

    assert created.input_snapshot_manifest_sha256 == (
        frozen.manifest.document.content_sha256
    )
    assert created.artifact_bindings == {
        logical: f"sha256:{sha256(raw).hexdigest()}"
        for logical, raw in sorted(frozen_bytes.items())
    }
    reloaded = load_frozen_compiler_inputs(session_root)
    assert reloaded.manifest.document.canonical_json == frozen_bytes[
        "inputs/input_snapshot_manifest.json"
    ]
    assert reloaded.deck.canonical_json == frozen.deck.canonical_json


@pytest.mark.parametrize(
    ("fault_point", "resumable"),
    (
        ("before_session_commit_marker", False),
        ("after_session_commit_marker", True),
    ),
)
def test_creation_hard_exit_respects_session_commit_marker(
    tmp_path: Path,
    fault_point: str,
    resumable: bool,
) -> None:
    frozen_bytes, manifest_sha256 = _simple_frozen_input_bytes()
    local_app_data = tmp_path / "local"
    session_root = (
        local_app_data / "HSConfig" / "runs" / ("f" * 32)
    )
    context = multiprocessing.get_context("spawn")
    worker = context.Process(
        target=_create_session_and_hard_exit,
        kwargs={
            "session_root": str(session_root),
            "local_app_data_root": str(local_app_data),
            "frozen_input_bytes": frozen_bytes,
            "input_snapshot_manifest_sha256": manifest_sha256,
            "fault_point": fault_point,
        },
    )
    worker.start()
    worker.join(timeout=20)
    assert not worker.is_alive()
    assert worker.exitcode == 81
    assert (session_root / "session.json").exists() is resumable
    if not resumable:
        with pytest.raises(FileNotFoundError):
            session.load_live_start_session(
                session_root,
                local_app_data_root=local_app_data,
            )
        return
    loaded = session.load_live_start_session(
        session_root,
        local_app_data_root=local_app_data,
    )
    assert loaded.phase is session.LiveStartPhase.INPUT_FROZEN
    assert loaded.artifact_bindings == {
        logical: f"sha256:{sha256(raw).hexdigest()}"
        for logical, raw in sorted(frozen_bytes.items())
    }


def test_load_and_resume_reject_missing_or_tampered_frozen_inputs(
    tmp_path: Path,
) -> None:
    frozen_bytes, manifest_sha256 = _simple_frozen_input_bytes()
    local_app_data = tmp_path / "local"
    root = local_app_data / "HSConfig" / "runs" / ("9" * 32)
    created = session.create_live_start_session(
        session_root=root,
        local_app_data_root=local_app_data,
        repository_root=tmp_path / "repository",
        runtime_root=tmp_path / "runtime",
        output_base_root=tmp_path / "output",
        output_deck_root=tmp_path / "output" / "Deck",
        installed_skill_root=tmp_path / "skill",
        deck_name="Deck",
        deck_code_sha256="sha256:" + "1" * 64,
        input_snapshot_manifest_sha256=manifest_sha256,
        frozen_input_bytes=frozen_bytes,
        preview_requested=False,
    )
    deck_path = root / "inputs" / "deck.json"
    original_deck = deck_path.read_bytes()
    deck_path.unlink()
    with pytest.raises(session.SessionConflictError, match="missing"):
        session.load_live_start_session(
            root,
            local_app_data_root=local_app_data,
        )
    deck_path.write_bytes(original_deck)
    sources_path = root / "inputs" / "sources.json"
    sources_path.write_bytes(b'{"sources":["tampered"]}\n')
    with pytest.raises(session.SessionConflictError, match="drift"):
        with _lease(root) as lease:
            session.validate_resume_under_lock(
                session_lease=lease,
                expected_deck_code_sha256=created.deck_code_sha256,
                expected_input_snapshot_manifest_sha256=(
                    created.input_snapshot_manifest_sha256
                ),
            )


def _exercise_real_cursor_cas(base: Path) -> None:
    root, predecessor = _new_session(base)
    with _lease(root) as lease:
        loaded = session.load_live_start_session_under_lock(
            session_lease=lease
        )
        assert loaded.canonical_json == predecessor.canonical_json
        pending = session._empty_pending_transition(
            session=predecessor,
            operation="install_candidate",
            external_file_action=None,
        )
        successor = session.transition_live_start_session_under_lock(
            session_lease=lease,
            expected_session=predecessor,
            event="same_phase_cas",
            changes={"pending_transition": session._seal_pending(pending)},
        )
        assert successor.pending_transition is not None
        assert successor.content_sha256 != predecessor.content_sha256
        with pytest.raises(session.SessionConflictError, match="stale"):
            session.transition_live_start_session_under_lock(
                session_lease=lease,
                expected_session=predecessor,
                event="same_phase_cas",
                changes={"pending_transition": session._seal_pending(pending)},
            )
        with pytest.raises(session.SessionCapabilityError):
            session.load_live_start_session_under_lock(
                session_lease=object()
            )


def _exercise_resume_contract(base: Path) -> None:
    root, cursor = _new_session(base)
    with _lease(root) as lease:
        with pytest.raises(session.SessionConflictError, match="compiler"):
            session.validate_resume_under_lock(
                session_lease=lease,
                expected_deck_code_sha256=cursor.deck_code_sha256,
                expected_input_snapshot_manifest_sha256=(
                    cursor.input_snapshot_manifest_sha256
                ),
                expected_runtime_grammar_version="wrong-grammar",
                expected_compiler_contract_id="wrong-compiler",
            )
        current = session.load_live_start_session_under_lock(
            session_lease=lease
        )
        assert current.content_sha256 == cursor.content_sha256


def _exercise_revision_contract(base: Path) -> None:
    test_candidate_revision_invalidates_candidate_review_and_downstream_receipts()
    root, cursor = _new_session(base)
    with _lease(root) as lease:
        with pytest.raises(session.SessionConflictError, match="intent"):
            session.transition_live_start_session_under_lock(
                session_lease=lease,
                expected_session=cursor,
                event="replacement_draft",
            )


def _exercise_capability_contract(base: Path) -> None:
    test_capability_smoke_exercises_real_thread_and_copy_boundaries(base)


def _exercise_pending_contract(base: Path) -> None:
    test_pending_transition_is_closed_self_digested_and_resumes_exact_physical_change(
        base
    )


def _output_child_binding_fixture(base: Path) -> dict[str, object]:
    identity = [1, 2, 0o100644]
    return {
        "schema_version": 1,
        "binding_kind": "live_start_output_child_binding",
        "run_id": "a" * 32,
        "output_base_path": str(base / "output"),
        "output_base_identity": identity,
        "output_child_path": str(base / "output" / "Deck"),
        "output_child_identity": identity,
        "predecessor_state": "absent",
        "predecessor_output_child_identity": None,
        "claim_path": str(base / "output" / ".claim.json"),
        "claim_parent_identity": identity,
        "claim_identity": identity,
        "claim_sha256": "sha256:" + "1" * 64,
        "claim_state": "ACTIVE",
    }


def _output_operation_binding_fixture(base: Path) -> dict[str, object]:
    identity = [1, 2, 0o100644]
    value: dict[str, object] = {
        field_name: None
        for field_name in session._OUTPUT_OPERATION_BINDING_FIELDS
        if field_name != "content_sha256"
    }
    value.update(
        {
            "schema_version": 1,
            "binding_kind": (
                "live_start_output_operation_admission_binding"
            ),
            "state": "ACTIVE",
            "release_handoff_kind": None,
            "admission_path": str(base / "admission.json"),
            "admission_parent_identity": identity,
            "admission_identity": identity,
            "admission_size": 1,
            "admission_sha256": "sha256:" + "1" * 64,
            "run_id": "a" * 32,
            "session_root": str(base / "run"),
            "session_root_identity": identity,
            "expected_session_sha256": "sha256:" + "2" * 64,
            "operator_profile_path": str(base / "profile.json"),
            "operator_profile_parent_identity": identity,
            "operator_profile_identity": identity,
            "operator_profile_sha256": "sha256:" + "3" * 64,
            "state_root_identity": identity,
            "output_base_root": str(base / "output"),
            "output_base_root_identity": identity,
            "output_child_path": str(base / "output" / "Deck"),
            "output_child_predecessor_state": "absent",
            "output_child_predecessor_identity": None,
            "output_bootstrap_lock_path": str(base / "output.lock"),
            "output_bootstrap_lock_identity": identity,
            "output_claim_path": str(base / "output" / ".claim.json"),
            "handoff_runtime_admission_path": None,
            "handoff_runtime_admission_parent_identity": None,
            "handoff_runtime_admission_identity": None,
            "handoff_runtime_admission_sha256": None,
        }
    )
    return value


def _exercise_output_contract(base: Path) -> None:
    active = session.seal_embedded_document(
        "output_child_binding",
        _output_child_binding_fixture(base),
    )
    assert active["claim_state"] == "ACTIVE"
    retired_value = dict(active)
    retired_value.pop("content_sha256")
    retired_value.update(
        {
            "claim_state": "RETIRED",
            "claim_identity": None,
            "claim_sha256": None,
        }
    )
    retired = session.seal_embedded_document(
        "output_child_binding", retired_value
    )
    assert retired["claim_state"] == "RETIRED"
    with pytest.raises(session.SessionValidationError, match="claim"):
        session.seal_embedded_document(
            "output_child_binding",
            {**retired_value, "claim_identity": [9, 9, 0o100644]},
        )
    with pytest.raises(session.SessionValidationError, match="path"):
        session.seal_embedded_document(
            "output_child_binding",
            {
                **_output_child_binding_fixture(base),
                "output_child_path": "relative/Deck",
            },
        )

    operation = session.seal_embedded_document(
        "output_operation_admission_binding",
        _output_operation_binding_fixture(base),
    )
    assert operation["state"] == "ACTIVE"
    with pytest.raises(session.SessionValidationError, match="handoff"):
        session.seal_embedded_document(
            "output_operation_admission_binding",
            {
                **_output_operation_binding_fixture(base),
                "release_handoff_kind": "runtime_admission",
            },
        )
    with pytest.raises(session.SessionValidationError, match="admission"):
        session.seal_embedded_document(
            "output_operation_admission_binding",
            {
                **_output_operation_binding_fixture(base),
                "admission_size": None,
            },
        )

    root, cursor = _new_session(base / "session")
    with _lease(root) as lease:
        with pytest.raises(session.SessionConflictError, match="prepare"):
            session.prepare_output_operation_admission_under_lock(
                session_lease=lease,
                expected_prepublication_session=cursor,
                admission_path=base / "admission.json",
                admission_staging_path=base / "admission.json.staged",
                admission_staging_inner_temp_path=(
                    base / ".admission.json.staged.live-start-atomic.tmp"
                ),
                admission_parent_identity=path_identity(base),
                planned_admission_size=1,
                planned_admission_sha256="sha256:" + "1" * 64,
                output_base_path=base,
                output_base_identity=path_identity(base),
                output_child_path=base / "Deck",
                predecessor_output_child_identity=None,
                output_bootstrap_lock_path=base / "output.lock",
                output_bootstrap_lock_identity=path_identity(base),
            )


def _exercise_result_contract(base: Path) -> None:
    test_session_embeds_result_intent_and_acknowledgement_status_matrix(base)
    identity = [1, 2, 0o100644]
    admission = {
        "admission_path": str(base / "admission.json"),
        "admission_parent_identity": identity,
        "admission_identity": identity,
        "admission_sha256": "sha256:" + "1" * 64,
        "output_operation_admission_path": str(
            base / "output-operation.json"
        ),
        "output_operation_admission_identity": identity,
        "output_operation_admission_sha256": "sha256:" + "2" * 64,
        "output_child_binding_sha256": "sha256:" + "3" * 64,
        "output_child_path": str(base / "output" / "Deck"),
        "output_child_identity": identity,
        "publication_revision": "revisions/sha256-" + "4" * 64,
        "publication_content_root_sha256": "sha256:" + "5" * 64,
    }
    session._validate_runtime_admission_binding(admission)
    with pytest.raises(session.SessionValidationError, match="admission"):
        session._validate_runtime_admission_binding(
            {**admission, "admission_identity": None}
        )

    publication = {
        "output_child_path": str(base / "output" / "Deck"),
        "output_child_identity": identity,
        "output_child_binding_sha256": "sha256:" + "8" * 64,
        "revision": "revisions/sha256-" + "6" * 64,
        "content_root_sha256": "sha256:" + "7" * 64,
        "prior_current_identity": None,
    }
    session._validate_publication_binding(publication)
    with pytest.raises(session.SessionValidationError, match="revision"):
        session._validate_publication_binding(
            {**publication, "revision": "revision-latest"}
        )
    with pytest.raises(session.SessionValidationError, match="output_child"):
        session._validate_publication_binding(
            {**publication, "output_child_identity": None}
        )


def _exercise_terminal_contract(_base: Path) -> None:
    predecessor = _terminal_retirement_fixture(
        operation="release_not_committed",
        stage="PREPARED",
        resolution=None,
    )
    successor_value = dict(predecessor)
    successor_value.pop("content_sha256")
    successor_value["stage"] = "EVIDENCE_RETIRED"
    successor = session.seal_embedded_document(
        "terminal_retirement", successor_value
    )
    session._validate_terminal_retirement_successor(
        predecessor=predecessor,
        successor=successor,
        transition="evidence_retired",
    )
    with pytest.raises(session.SessionCapabilityError, match="successor"):
        session._validate_terminal_retirement_successor(
            predecessor=predecessor,
            successor=successor,
            transition="admission_release_authorized",
        )

    resolved = _terminal_retirement_fixture(
        operation="release_resolved_terminal",
        stage="RECOVERY_PREPARED",
        resolution=_terminal_resolution_fixture(),
    )
    rewritten_value = dict(resolved)
    rewritten_value.pop("content_sha256")
    rewritten_resolution = dict(
        rewritten_value["terminal_resolution_evidence"]
    )
    rewritten_resolution.pop("content_sha256")
    rewritten_resolution["package_root_sha256"] = "sha256:" + "c" * 64
    rewritten_value["terminal_resolution_evidence"] = (
        session._seal_terminal_resolution(rewritten_resolution)
    )
    rewritten = session.seal_embedded_document(
        "terminal_retirement", rewritten_value
    )
    with pytest.raises(session.SessionCapabilityError, match="changed"):
        session._validate_terminal_resolution_successor(
            predecessor=resolved,
            successor=rewritten,
            transition="physical_recovery_advanced",
        )


def _exercise_terminal_receipt_contract(base: Path) -> None:
    root, cursor = _new_session(base)
    action = "delete_cleanup_entry"
    calls = 0
    with _lease(root) as lease:
        authorization = session._mint_authorization_under_lock(
            authorization_type=session.TerminalRetirementAuthorization,
            session_lease=lease,
            expected_session=cursor,
            family="terminal_retirement",
            action=action,
        )

        def callback() -> session.TerminalResolutionPhysicalPostcondition:
            nonlocal calls
            calls += 1
            return session.TerminalResolutionPhysicalPostcondition(
                action=action,
                evidence={"step": 1},
            )

        receipt = session._execute_terminal_resolution_physical_step(
            terminal_authorization=authorization,
            action=action,
            physical_action=callback,
        )
        postcondition = session._consume_receipt_under_lock(
            receipt=receipt,
            receipt_type=session.TerminalResolutionStepReceipt,
            session_lease=lease,
            expected_session=cursor,
            family="terminal_retirement",
            action=action,
        )
        assert postcondition.evidence == {"step": 1}
        assert calls == 1
        with pytest.raises(session.SessionCapabilityError):
            session._consume_receipt_under_lock(
                receipt=receipt,
                receipt_type=session.TerminalResolutionStepReceipt,
                session_lease=lease,
                expected_session=cursor,
                family="terminal_retirement",
                action=action,
            )


def _exercise_recovery_contract(_base: Path) -> None:
    predecessor = _apply_recovery_fixture()
    successor_value = dict(predecessor)
    successor_value.pop("content_sha256")
    successor_value.update(
        {
            "action_index": 1,
            "expected_action": None,
            "stable_physical_disposition": "NOT_COMMITTED",
        }
    )
    successor = _seal_literal_document(successor_value)
    session._validate_apply_recovery_physical_successor(
        predecessor=predecessor,
        successor=successor,
        action="observe_not_committed",
    )
    skipped_value = dict(successor)
    skipped_value.pop("content_sha256")
    skipped_value["action_index"] = 3
    skipped = _seal_literal_document(skipped_value)
    with pytest.raises(session.SessionCapabilityError, match="successor"):
        session._validate_apply_recovery_physical_successor(
            predecessor=predecessor,
            successor=skipped,
            action="observe_not_committed",
        )
    closed_value = dict(successor)
    closed_value.pop("content_sha256")
    closed_value["recovery_stage"] = "CLOSED"
    closed = _seal_literal_document(closed_value)
    session._validate_apply_recovery_closure_successor(
        predecessor=successor,
        successor=closed,
    )


def _exercise_observation_contract(base: Path) -> None:
    test_runtime_observation_receipt_rejects_constructed_swapped_stale_cross_pair_or_reused_values(
        base
    )


def _exercise_runtime_layout_contract(base: Path) -> None:
    test_runtime_layout_bootstrap_schema_and_fixed_order_are_closed(base)
    root, cursor = _new_session(base / "session")
    with _lease(root) as lease:
        with pytest.raises(session.SessionConflictError):
            session._authorize_runtime_layout_bootstrap_under_lock(
                session_lease=lease,
                expected_layout_session=cursor,
                action="create_or_confirm_runtime_layout_directory",
            )


def _exercise_owner_contract(_base: Path) -> None:
    owner = session.OwnerRetirementEvidence(_owner_retirement_fixture())
    assert owner.value["stage"] == "PREPARED_PLANNED"
    assert session.OWNER_RETIREMENT_ACTION_ORDER.index(
        "delete_owner_cleanup_entry"
    ) < session.OWNER_RETIREMENT_ACTION_ORDER.index(
        "advance_owner_cleanup_journal"
    )
    assert session.OWNER_RETIREMENT_STAGES[-3:] == (
        "TARGET_RETIRED",
        "COMPLETED",
        "OWNER_RETIRED",
    )
    invalid = dict(owner.value)
    invalid.pop("content_sha256")
    invalid["old_owner_journal_retired"] = True
    with pytest.raises(session.SessionValidationError, match="old_owner"):
        session.OwnerRetirementEvidence(_seal_literal_document(invalid))


def _exercise_runtime_admission_release_contract(base: Path) -> None:
    root, cursor = _new_session(base / "session")
    admission_path = (base / "admission.json").absolute()
    parent_identity = path_identity(base)
    historical_identity = (1, 2, 0o100644)
    historical_sha256 = "sha256:" + "2" * 64
    calls = 0
    with _lease(root) as lease:
        authorization = session._mint_authorization_under_lock(
            authorization_type=session.TerminalRetirementAuthorization,
            session_lease=lease,
            expected_session=cursor,
            family="terminal_retirement",
            action="release_runtime_admission",
        )
        authorization._opaque.successor = {
            "admission_path": admission_path,
            "admission_parent_identity": parent_identity,
            "historical_admission_identity": historical_identity,
            "historical_admission_sha256": historical_sha256,
        }

        def callback() -> session.RuntimeAdmissionReleasePostcondition:
            nonlocal calls
            calls += 1
            return session.RuntimeAdmissionReleasePostcondition(
                admission_path=admission_path,
                admission_parent_identity=parent_identity,
                historical_admission_identity=historical_identity,
                historical_admission_sha256=historical_sha256,
                disposition="already_absent",
                foreign_successor_identity=None,
                foreign_successor_sha256=None,
            )

        result = session._execute_runtime_admission_release(
            terminal_authorization=authorization,
            action="release_runtime_admission",
            physical_action=callback,
        )
        assert result.disposition == "already_absent"
        assert calls == 1
        with pytest.raises(session.SessionCapabilityError):
            session._execute_runtime_admission_release(
                terminal_authorization=authorization,
                action="release_runtime_admission",
                physical_action=callback,
            )
        assert calls == 1


def test_resume_stops_on_input_compiler_or_grammar_drift(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_resume_contract(tmp_path / "behavior")


def test_candidate_revision_transition_table_is_closed_and_resume_deterministic(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_revision_contract(tmp_path / "behavior")


def test_one_lease_threads_exact_session_cursor_through_every_terminal_cas(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_terminal_contract(tmp_path / "behavior")


def test_session_under_lock_helper_rejects_mixed_wrong_root_or_wrong_lock_token(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_capability_contract(tmp_path / "behavior")


def test_cross_thread_session_capability_fails_before_artifact_read_or_write(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_capability_contract(tmp_path / "behavior")


def test_shallow_copy_shares_bearer_and_expires_without_minting_authority(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_capability_contract(tmp_path / "behavior")


def test_unbound_authority_staging_is_delete_only_and_never_promoted(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_pending_contract(tmp_path / "behavior")


def test_unbound_staging_retirement_receipt_advances_cursor_before_retry(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_pending_contract(tmp_path / "behavior")


def test_apply_start_capability_separates_admission_and_invocation_receipt_actions(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_runtime_layout_contract(tmp_path / "behavior")


def test_cleanup_pending_transition_binds_external_identity_inventory_states(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_pending_contract(tmp_path / "behavior")


def test_output_child_binding_and_claim_state_matrix_is_closed(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_output_contract(tmp_path / "behavior")


def test_output_child_bootstrap_transition_is_intent_first_and_operation_closed(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_output_contract(tmp_path / "behavior")


def test_output_child_bootstrap_rejects_mixed_nullability_or_unknown_stage(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_output_contract(tmp_path / "behavior")


def test_output_child_bootstrap_receipt_is_thread_cursor_action_and_single_use_bound(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_output_contract(tmp_path / "behavior")


def test_output_operation_admission_binding_state_and_nullability_are_closed(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_output_contract(tmp_path / "behavior")


def test_output_operation_admission_publish_is_intent_first_and_receipt_bound(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_output_contract(tmp_path / "behavior")


def test_output_operation_authorization_stage_action_matrix_is_closed(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_output_contract(tmp_path / "behavior")


def test_output_operation_release_requires_exact_persisted_authorized_cursor(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_output_contract(tmp_path / "behavior")


def test_apply_started_atomically_authorizes_output_operation_runtime_handoff(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_output_contract(tmp_path / "behavior")


def test_output_operation_release_needs_no_absence_recording_cas(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_output_contract(tmp_path / "behavior")


def test_output_operation_bearers_are_nonforgeable_thread_bound_and_single_use(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_output_contract(tmp_path / "behavior")


def test_output_child_claim_retirement_is_forbidden_before_publication_committed(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_output_contract(tmp_path / "behavior")


def test_output_child_claim_retirement_preserves_historical_claim_binding(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_output_contract(tmp_path / "behavior")


def test_output_claim_retired_requires_confirmation_receipt(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_output_contract(tmp_path / "behavior")


def test_output_claim_retired_atomically_rebinds_publication_digest(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_output_contract(tmp_path / "behavior")


def test_output_child_binding_is_immutable_through_admission_and_terminal(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_output_contract(tmp_path / "behavior")


def test_result_intent_coverage_counts_are_jointly_nullable_until_valid_candidate(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_result_contract(tmp_path / "behavior")


def test_result_intent_coverage_binds_exact_supported_frozen_roster_without_thirty_cap(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_result_contract(tmp_path / "behavior")


def test_result_intent_runtime_admission_fields_are_jointly_closed(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_result_contract(tmp_path / "behavior")


def test_session_runtime_admission_binding_is_jointly_closed(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_result_contract(tmp_path / "behavior")


def test_attempt_acknowledgement_binds_attempt_record_and_surviving_target_owner(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_result_contract(tmp_path / "behavior")


def test_attempt_acknowledgement_rejects_delete_owner_action_or_mixed_evidence(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_owner_contract(tmp_path / "behavior")


def test_result_intent_binds_attempt_journal_and_owner_path_identity_and_digest(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_owner_contract(tmp_path / "behavior")


def test_terminal_retirement_has_closed_recovery_evidence_and_release_authorized_stages(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_terminal_contract(tmp_path / "behavior")


def test_terminal_cleanup_inventory_same_outer_stage_accepts_only_receipt_bound_file_rollovers(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_terminal_receipt_contract(tmp_path / "behavior")


def test_terminal_cleanup_inventory_rejects_direct_final_or_changed_bound_identity(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_terminal_contract(tmp_path / "behavior")


def test_terminal_resolution_cleanup_rejects_skipped_backward_stale_or_reused_authority(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_terminal_receipt_contract(tmp_path / "behavior")


def test_terminal_resolution_advance_requires_matching_physical_step_receipt_or_pure_cas_authorization(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_terminal_receipt_contract(tmp_path / "behavior")


def test_terminal_resolution_step_receipt_is_nonforgeable_thread_bound_and_single_use(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_terminal_receipt_contract(tmp_path / "behavior")


def test_physical_recovery_receipt_privately_carries_exact_successor_evidence(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_recovery_contract(tmp_path / "behavior")


def test_physical_recovery_rejects_caller_supplied_successor_with_receipt(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_recovery_contract(tmp_path / "behavior")


def test_physical_executor_exception_spends_authorization_without_callback_retry(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_capability_contract(tmp_path / "behavior")


def test_crash_after_bound_physical_step_remints_receipt_only_for_exact_postcondition(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_capability_contract(tmp_path / "behavior")


def test_terminal_resolution_rejects_missing_stale_wrong_cursor_cross_action_or_reused_receipt(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_terminal_receipt_contract(tmp_path / "behavior")


def test_legacy_uuid_transaction_temp_origin_path_classification_and_nullability_matrix_is_closed(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_recovery_contract(tmp_path / "behavior")


def test_transaction_temp_origin_is_exactly_legacy_uuid_or_null(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_recovery_contract(tmp_path / "behavior")


def test_controller_journal_unbound_staging_uses_only_external_file_action_retirement(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_recovery_contract(tmp_path / "behavior")


def test_controller_journal_unbound_complete_bytes_are_deleted_never_promoted(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_recovery_contract(tmp_path / "behavior")


def test_legacy_uuid_temp_cannot_alias_controller_external_file_action(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_recovery_contract(tmp_path / "behavior")


def test_apply_recovery_candidate_create_or_confirm_action_matrix_is_closed(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_recovery_contract(tmp_path / "behavior")


def test_candidate_identity_receipt_accepts_only_exact_action_postcondition(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_recovery_contract(tmp_path / "behavior")


def test_candidate_create_and_candidate_fence_require_distinct_authorizations(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_recovery_contract(tmp_path / "behavior")


def test_nonterminal_recovery_advance_requires_matching_receipt_or_pure_cas_authorization(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_terminal_receipt_contract(tmp_path / "behavior")


def test_terminal_and_nonterminal_recovery_carriers_reject_cross_use(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_terminal_contract(tmp_path / "behavior")


def test_terminal_classification_selection_is_pure_cas_and_increments_action_index_once(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_observation_contract(tmp_path / "behavior")


def test_terminal_classification_selection_preserves_all_physical_evidence(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_observation_contract(tmp_path / "behavior")


def test_terminal_classification_selection_requires_fresh_exact_single_use_observation_receipt(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_observation_contract(tmp_path / "behavior")


def test_terminal_classification_selection_rejects_missing_receipt_or_observe_committed(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_observation_contract(tmp_path / "behavior")


def test_terminal_classification_selection_rejects_stale_reused_cross_thread_and_stable_cursor(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_observation_contract(tmp_path / "behavior")


def test_terminal_classification_selection_cannot_select_twice(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_observation_contract(tmp_path / "behavior")


def test_runtime_observation_receipt_is_nonforgeable_thread_family_cursor_and_single_use(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_observation_contract(tmp_path / "behavior")


def test_runtime_observation_receipt_privately_binds_initial_evidence_or_selection(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_observation_contract(tmp_path / "behavior")


def test_initial_prepare_and_selection_cas_accept_only_matching_observation_receipt(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_observation_contract(tmp_path / "behavior")


def test_apply_recovery_pending_and_unknown_close_before_terminal_result(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_terminal_contract(tmp_path / "behavior")


def test_recovery_stage_active_closed_matrix_is_closed(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_recovery_contract(tmp_path / "behavior")


def test_recovery_closed_changes_stage_once_and_rejects_noop_or_repeat(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_recovery_contract(tmp_path / "behavior")


def test_recovery_closed_retains_exact_closed_apply_recovery_until_result_intent_cas(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_result_contract(tmp_path / "behavior")


def test_result_intent_cas_atomically_consumes_closed_apply_recovery(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_result_contract(tmp_path / "behavior")


def test_result_intent_rejects_unclosed_stale_wrong_attempt_or_wrong_digest_recovery_cursor(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_result_contract(tmp_path / "behavior")


def test_crash_after_recovery_closed_preserves_selected_terminal_classification(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_terminal_contract(tmp_path / "behavior")


def test_private_recovery_mint_and_receipt_issuer_bind_real_session_bearer(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_recovery_contract(tmp_path / "behavior")


def test_runtime_first_install_observation_receipt_prepares_exact_persisted_recovery_cursor(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_recovery_contract(tmp_path / "behavior")


def test_normal_first_install_persists_apply_recovery_before_first_runtime_mutation(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_recovery_contract(tmp_path / "behavior")


def test_normal_first_install_executes_exactly_one_physical_row_per_receipt_cas(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_recovery_contract(tmp_path / "behavior")


def test_runtime_layout_bootstrap_create_or_confirm_is_one_receipt_cas_per_directory(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_runtime_layout_contract(tmp_path / "behavior")


def test_runtime_layout_bootstrap_crash_after_mkdir_before_cas_binds_only_exact_empty_child(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_runtime_layout_contract(tmp_path / "behavior")


def test_runtime_layout_bootstrap_rejects_parent_substitution_reparse_ads_nonempty_new_or_skip(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_runtime_layout_contract(tmp_path / "behavior")


def test_invocation_receipt_is_forbidden_until_runtime_layout_complete(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_runtime_layout_contract(tmp_path / "behavior")


def test_apply_recovery_new_target_action_graph_is_exhaustive_and_linear(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_recovery_contract(tmp_path / "behavior")


def test_candidate_tree_copy_verify_rename_and_journal_rows_are_distinct(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_recovery_contract(tmp_path / "behavior")


def test_new_target_ini_is_reachable_only_after_bound_renamed_target(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_recovery_contract(tmp_path / "behavior")


def test_owner_retirement_each_entry_delete_and_journal_advance_need_distinct_receipts(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_owner_contract(tmp_path / "behavior")


def test_owner_retirement_completed_precedes_old_owner_unlink(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_owner_contract(tmp_path / "behavior")


def test_owner_retirement_evidence_binds_target_parent_and_complete_manifest_commitment(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_owner_contract(tmp_path / "behavior")


def test_owner_retirement_initialize_cursor_zero_and_target_retired_stages_are_closed(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_owner_contract(tmp_path / "behavior")


def test_owner_retirement_initialize_delete_advance_root_and_completed_need_distinct_receipts(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_owner_contract(tmp_path / "behavior")


def test_owner_retirement_target_retired_precedes_completed_and_old_owner_unlink(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_owner_contract(tmp_path / "behavior")


def test_owner_retirement_binds_completed_tombstone_commitment_at_final_v1_cursor(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_owner_contract(tmp_path / "behavior")


def test_owner_root_receipt_installs_only_prebound_completed_tombstone_intent(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_owner_contract(tmp_path / "behavior")


def test_owner_root_crash_rejects_completed_tombstone_list_or_v1_substitution(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_owner_contract(tmp_path / "behavior")


def test_terminal_resolution_carries_partial_owner_retirement_until_owner_retired(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_owner_contract(tmp_path / "behavior")


def test_release_authorized_is_final_session_stage_before_physical_unlink(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_runtime_admission_release_contract(tmp_path / "behavior")


def test_runtime_admission_release_executor_consumes_before_callback_and_returns_no_receipt(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_runtime_admission_release_contract(tmp_path / "behavior")


def test_runtime_admission_release_executor_rejects_forged_stale_reused_wrong_stage_and_cross_thread_before_callback(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_runtime_admission_release_contract(tmp_path / "behavior")


def test_runtime_admission_release_postcondition_nullability_is_closed(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_runtime_admission_release_contract(tmp_path / "behavior")


def test_terminal_retirement_authority_is_persisted_thread_bound_and_single_use(
    tmp_path: Path,
) -> None:
    _exercise_real_cursor_cas(tmp_path / "cursor")
    _exercise_terminal_receipt_contract(tmp_path / "behavior")
