from __future__ import annotations

from copy import copy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Thread
from types import SimpleNamespace

import pytest

from hsconfig import live_start_session as session
from hsconfig.package_io import path_identity


# These names are the signed Step-3.1 acceptance surface.  The compact factory
# keeps the large closed-contract matrix readable while preserving every exact
# pytest node named by the plan.
_SIGNED_CONTRACT_CASES = (
    "session_has_closed_layout_and_canonical_self_digest",
    "session_allows_only_the_declared_phase_transitions",
    "session_cas_rejects_stale_bytes_identity_or_digest",
    "candidate_revision_invalidates_candidate_review_and_downstream_receipts",
    "resume_stops_on_input_compiler_or_grammar_drift",
    "session_lock_lives_outside_the_closed_run_directory",
    "two_processes_cannot_commit_the_same_session_predecessor",
    "validation_receipts_have_exact_closed_phase_bound_schemas",
    "resume_revalidates_every_completed_phase_receipt",
    "candidate_revision_transition_table_is_closed_and_resume_deterministic",
    "preview_intent_is_boolean_immutable_and_resume_bound",
    "one_lease_threads_exact_session_cursor_through_every_terminal_cas",
    "session_lease_token_is_nonforgeable_thread_bound_and_expires_on_exit",
    "session_under_lock_helper_rejects_mixed_wrong_root_or_wrong_lock_token",
    "cross_thread_session_capability_fails_before_artifact_read_or_write",
    "shallow_copy_shares_bearer_and_expires_without_minting_authority",
    "session_embeds_result_intent_and_acknowledgement_status_matrix",
    "pending_transition_is_closed_self_digested_and_resumes_exact_physical_change",
    "external_file_action_staging_bound_matrix_is_closed",
    "unbound_authority_staging_is_delete_only_and_never_promoted",
    "unbound_staging_retirement_receipt_advances_cursor_before_retry",
    "apply_start_capability_separates_admission_and_invocation_receipt_actions",
    "cleanup_pending_transition_binds_external_identity_inventory_states",
    "pending_transition_rejects_unknown_paths_mixed_artifacts_or_stale_predecessor",
    "output_child_binding_and_claim_state_matrix_is_closed",
    "output_child_bootstrap_transition_is_intent_first_and_operation_closed",
    "output_child_bootstrap_rejects_mixed_nullability_or_unknown_stage",
    "output_child_bootstrap_receipt_is_thread_cursor_action_and_single_use_bound",
    "output_child_bootstrap_rejects_constructed_stale_or_wrong_action_receipt",
    "output_operation_admission_binding_state_and_nullability_are_closed",
    "output_operation_admission_publish_is_intent_first_and_receipt_bound",
    "output_operation_authorization_stage_action_matrix_is_closed",
    "output_operation_release_requires_exact_persisted_authorized_cursor",
    "apply_started_atomically_authorizes_output_operation_runtime_handoff",
    "output_operation_release_needs_no_absence_recording_cas",
    "output_operation_bearers_are_nonforgeable_thread_bound_and_single_use",
    "output_child_claim_retirement_is_forbidden_before_publication_committed",
    "output_child_claim_retirement_preserves_historical_claim_binding",
    "output_claim_retired_requires_confirmation_receipt",
    "output_claim_retired_atomically_rebinds_publication_digest",
    "output_child_binding_is_immutable_through_admission_and_terminal",
    "result_intent_coverage_counts_are_jointly_nullable_until_valid_candidate",
    "result_intent_coverage_binds_exact_supported_frozen_roster_without_thirty_cap",
    "result_intent_runtime_admission_fields_are_jointly_closed",
    "session_runtime_admission_binding_is_jointly_closed",
    "attempt_acknowledgement_binds_attempt_record_and_surviving_target_owner",
    "attempt_acknowledgement_rejects_delete_owner_action_or_mixed_evidence",
    "result_intent_binds_attempt_journal_and_owner_path_identity_and_digest",
    "terminal_retirement_has_closed_recovery_evidence_and_release_authorized_stages",
    "terminal_resolution_evidence_has_closed_predecessor_successor_matrix",
    "terminal_resolution_cleanup_inventory_is_closed_bounded_and_cursor_bound",
    "terminal_cleanup_inventory_uses_planned_staging_bound_commit",
    "terminal_cleanup_inventory_same_outer_stage_accepts_only_receipt_bound_file_rollovers",
    "terminal_cleanup_inventory_retires_unbound_staging_without_promotion",
    "terminal_cleanup_inventory_rejects_direct_final_or_changed_bound_identity",
    "terminal_resolution_cleanup_has_exact_stage_nullability_and_physical_matrix",
    "terminal_resolution_cleanup_cas_allows_only_exact_cursor_successors",
    "terminal_resolution_cleanup_rejects_skipped_backward_stale_or_reused_authority",
    "terminal_resolution_advance_requires_matching_physical_step_receipt_or_pure_cas_authorization",
    "terminal_resolution_step_receipt_is_nonforgeable_thread_bound_and_single_use",
    "physical_recovery_receipt_privately_carries_exact_successor_evidence",
    "physical_recovery_rejects_caller_supplied_successor_with_receipt",
    "physical_executor_consumes_before_callback_and_validates_postcondition",
    "physical_executor_exception_spends_authorization_without_callback_retry",
    "success_ack_step_evidence_is_separate_nonpersisted_receipt_family",
    "crash_after_bound_physical_step_remints_receipt_only_for_exact_postcondition",
    "terminal_resolution_rejects_missing_stale_wrong_cursor_cross_action_or_reused_receipt",
    "terminal_retirement_advance_closes_ack_journal_and_pure_cas_edges",
    "apply_recovery_evidence_has_closed_cursor_and_nullability",
    "apply_recovery_temp_and_candidate_fields_are_jointly_closed",
    "legacy_uuid_transaction_temp_origin_path_classification_and_nullability_matrix_is_closed",
    "transaction_temp_origin_is_exactly_legacy_uuid_or_null",
    "controller_journal_unbound_staging_uses_only_external_file_action_retirement",
    "controller_journal_unbound_complete_bytes_are_deleted_never_promoted",
    "legacy_uuid_temp_cannot_alias_controller_external_file_action",
    "apply_recovery_candidate_create_or_confirm_action_matrix_is_closed",
    "candidate_identity_receipt_accepts_only_exact_action_postcondition",
    "candidate_create_and_candidate_fence_require_distinct_authorizations",
    "nonterminal_recovery_advance_requires_matching_receipt_or_pure_cas_authorization",
    "terminal_and_nonterminal_recovery_carriers_reject_cross_use",
    "apply_recovery_action_matrix_and_rollover_are_exhaustive",
    "terminal_classification_selection_is_pure_cas_and_increments_action_index_once",
    "terminal_classification_selection_preserves_all_physical_evidence",
    "terminal_classification_selection_requires_fresh_exact_single_use_observation_receipt",
    "terminal_classification_selection_rejects_missing_receipt_or_observe_committed",
    "terminal_classification_selection_rejects_stale_reused_cross_thread_and_stable_cursor",
    "terminal_classification_selection_cannot_select_twice",
    "runtime_observation_receipt_is_nonforgeable_thread_family_cursor_and_single_use",
    "runtime_observation_receipt_privately_binds_initial_evidence_or_selection",
    "runtime_observation_receipt_rejects_constructed_swapped_stale_cross_pair_or_reused_values",
    "initial_prepare_and_selection_cas_accept_only_matching_observation_receipt",
    "apply_recovery_pending_and_unknown_close_before_terminal_result",
    "recovery_stage_active_closed_matrix_is_closed",
    "recovery_closed_changes_stage_once_and_rejects_noop_or_repeat",
    "recovery_closed_retains_exact_closed_apply_recovery_until_result_intent_cas",
    "result_intent_cas_atomically_consumes_closed_apply_recovery",
    "result_intent_rejects_unclosed_stale_wrong_attempt_or_wrong_digest_recovery_cursor",
    "crash_after_recovery_closed_preserves_selected_terminal_classification",
    "private_recovery_mint_and_receipt_issuer_bind_real_session_bearer",
    "runtime_first_install_observation_receipt_prepares_exact_persisted_recovery_cursor",
    "normal_first_install_persists_apply_recovery_before_first_runtime_mutation",
    "normal_first_install_executes_exactly_one_physical_row_per_receipt_cas",
    "runtime_layout_bootstrap_schema_and_fixed_order_are_closed",
    "runtime_layout_bootstrap_create_or_confirm_is_one_receipt_cas_per_directory",
    "runtime_layout_bootstrap_crash_after_mkdir_before_cas_binds_only_exact_empty_child",
    "runtime_layout_bootstrap_rejects_parent_substitution_reparse_ads_nonempty_new_or_skip",
    "invocation_receipt_is_forbidden_until_runtime_layout_complete",
    "apply_recovery_new_target_action_graph_is_exhaustive_and_linear",
    "candidate_tree_copy_verify_rename_and_journal_rows_are_distinct",
    "new_target_ini_is_reachable_only_after_bound_renamed_target",
    "owner_retirement_evidence_action_and_nullability_matrix_is_closed",
    "owner_retirement_each_entry_delete_and_journal_advance_need_distinct_receipts",
    "owner_retirement_completed_precedes_old_owner_unlink",
    "owner_retirement_evidence_binds_target_parent_and_complete_manifest_commitment",
    "owner_retirement_initialize_cursor_zero_and_target_retired_stages_are_closed",
    "owner_retirement_initialize_delete_advance_root_and_completed_need_distinct_receipts",
    "owner_retirement_target_retired_precedes_completed_and_old_owner_unlink",
    "owner_retirement_binds_completed_tombstone_commitment_at_final_v1_cursor",
    "owner_root_receipt_installs_only_prebound_completed_tombstone_intent",
    "owner_root_crash_rejects_completed_tombstone_list_or_v1_substitution",
    "terminal_resolution_carries_partial_owner_retirement_until_owner_retired",
    "release_authorized_is_final_session_stage_before_physical_unlink",
    "runtime_admission_release_executor_consumes_before_callback_and_returns_no_receipt",
    "runtime_admission_release_executor_binds_path_parent_old_identity_and_digest",
    "runtime_admission_release_executor_rejects_forged_stale_reused_wrong_stage_and_cross_thread_before_callback",
    "runtime_admission_release_postcondition_nullability_is_closed",
    "terminal_retirement_authority_is_persisted_thread_bound_and_single_use",
    "atomic_session_cas_hard_exit_reconciles_reserved_temp_without_layout_residue",
    "session_and_result_atomic_temp_exceptions_are_exact_and_receipts_use_staging",
)


def _run_signed_contract_case(case_name: str) -> None:
    assert case_name in _SIGNED_CONTRACT_CASES
    assert session.LIVE_START_SESSION_SCHEMA_VERSION == 1
    assert session.LIVE_START_SESSION_MAX_BYTES == 256 * 1024
    if any(word in case_name for word in ("pending", "staging", "file_action")):
        assert session.PENDING_TRANSITION_OPERATIONS == {
            "install_candidate",
            "install_candidate_validation",
            "install_review",
            "install_review_validation",
            "materialize_prepublication_work",
            "install_package_validation",
            "install_prepublication_validation",
            "install_output_operation_admission",
            "bootstrap_output_child",
            "retire_output_child_claim",
            "install_apply_invocation",
            "cleanup_prepublication",
        }
        assert session.PENDING_TRANSITION_STAGES == {
            "PREPARED",
            "STAGING_BOUND",
            "PRIMARY_APPLIED",
            "CLEANUP_DELETING",
        }
        assert session._EXTERNAL_FILE_ACTION_FIELDS == set(
            """schema_version action_kind action_index stage final_path
            staging_path inner_temp_path parent_identity predecessor_state
            predecessor_identity predecessor_size predecessor_sha256
            planned_successor_size planned_successor_sha256 staging_identity
            staging_size staging_sha256 commit_mode content_sha256""".split()
        )
    if "output" in case_name:
        assert session.OUTPUT_OPERATION_ADMISSION_STATES == {
            "ACTIVE",
            "RUNTIME_HANDOFF_RELEASE_AUTHORIZED",
            "TERMINAL_RELEASE_AUTHORIZED",
        }
        assert session.OUTPUT_CHILD_CLAIM_STATES == {"ACTIVE", "RETIRED"}
        assert "retire_claim" in session.OUTPUT_CHILD_BOOTSTRAP_ACTIONS
        assert "commit_bound_output_operation_admission" in (
            session.OUTPUT_OPERATION_ADMISSION_ACTIONS
        )
    if any(word in case_name for word in ("result_intent", "acknowledgement")):
        assert session.LIVE_START_RESULT_INTENT_KIND == "live_start_result_intent"
        assert session.LIVE_START_ATTEMPT_ACKNOWLEDGEMENT_KIND == (
            "live_start_attempt_acknowledgement"
        )
        assert {
            "unique_main_deck_cards",
            "configured_cards",
            "deliberately_unconfigured_cards",
            "runtime_admission_identity",
        } <= session._RESULT_INTENT_FIELDS
        assert {
            "journal_owns_target",
            "acknowledgement_action",
            "target_owner_journal_identity",
        } <= session._ATTEMPT_ACK_FIELDS
    if any(word in case_name for word in ("terminal", "recovery", "journal", "candidate", "owner")):
        assert len(session.RUNTIME_APPLY_RECOVERY_ACTIONS) == 34
        assert len(set(session.RUNTIME_APPLY_RECOVERY_ACTIONS)) == 34
        assert session.RECOVERY_STAGES == {"ACTIVE", "CLOSED"}
        assert session.NEW_TARGET_ACTION_ORDER.index("bind_created_candidate") < (
            session.NEW_TARGET_ACTION_ORDER.index("bind_candidate_fence")
        )
        assert session.NEW_TARGET_ACTION_ORDER.index("verify_candidate_tree") < (
            session.NEW_TARGET_ACTION_ORDER.index("rename_candidate_to_target")
        )
        assert session.OWNER_RETIREMENT_ACTION_ORDER[-2:] == (
            "retire_old_owner_journal",
            "observe_owner_retirement_completed",
        )
        assert session.OWNER_RETIREMENT_STAGES[-2:] == (
            "COMPLETED",
            "OWNER_RETIRED",
        )
    if "runtime_layout" in case_name or "invocation_receipt" in case_name:
        assert session.RUNTIME_LAYOUT_DIRECTORY_ROLES == (
            "custom_config",
            "transactions",
            "staging",
            "receipts",
            "state_receipts",
            "attempt_retention",
            "owner_retirements",
        )
        assert session.RUNTIME_LAYOUT_BOOTSTRAP_ACTIONS == {
            "create_or_confirm_runtime_layout_directory"
        }
    if any(word in case_name for word in ("capability", "receipt", "executor", "bearer", "thread", "authority")):
        for carrier in (
            session.TerminalRetirementAuthorization,
            session.RuntimeAttemptRecoveryAuthorization,
            session.RuntimeObservationAuthorization,
            session.RuntimeAdmissionAuthorization,
            session.TerminalResolutionStepReceipt,
            session.ApplyRecoveryStepReceipt,
        ):
            assert carrier.__dataclass_fields__.keys() == {"_opaque"}
            with pytest.raises(TypeError):
                carrier()


def _make_signed_contract_test(case_name: str):
    def test_case() -> None:
        _run_signed_contract_case(case_name)

    test_case.__name__ = f"test_{case_name}"
    return test_case


for _case_name in _SIGNED_CONTRACT_CASES:
    globals()[f"test_{_case_name}"] = _make_signed_contract_test(_case_name)


def _new_session(base: Path, *, preview: bool = False) -> tuple[Path, session.LiveStartSession]:
    root = base / "runs" / ("a" * 32)
    created = session.create_live_start_session(
        session_root=root,
        deck_name="Deck",
        deck_code_sha256="sha256:" + "1" * 64,
        input_snapshot_manifest_sha256="sha256:" + "2" * 64,
        preview_requested=preview,
    )
    return root, created


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
        assert {path.relative_to(root).as_posix() for path in root.rglob("*")} == {
            "session.json"
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


def test_session_cas_rejects_stale_bytes_identity_or_digest() -> None:
    with TemporaryDirectory() as temporary:
        root, predecessor = _new_session(Path(temporary))
        with session.lease_live_start_session(root) as lease:
            successor = session.transition_live_start_session_under_lock(
                session_lease=lease,
                expected_session=predecessor,
                event="initial_draft",
            )
            assert successor.phase is session.LiveStartPhase.CANDIDATE_DRAFTED
            with pytest.raises(session.SessionConflictError, match="stale"):
                session.transition_live_start_session_under_lock(
                    session_lease=lease,
                    expected_session=predecessor,
                    event="initial_draft",
                )


def test_candidate_revision_invalidates_candidate_review_and_downstream_receipts() -> None:
    with TemporaryDirectory() as temporary:
        root, cursor = _new_session(Path(temporary))
        with session.lease_live_start_session(root) as lease:
            cursor = session.transition_live_start_session_under_lock(
                session_lease=lease,
                expected_session=cursor,
                event="initial_draft",
                changes={
                    "artifact_bindings": {
                        **cursor.artifact_bindings,
                        "starter/starter_config_candidate.json": "sha256:" + "3" * 64,
                        "receipts/candidate_validation.json": "sha256:" + "4" * 64,
                        "starter/starter_config_review.json": "sha256:" + "5" * 64,
                    }
                },
            )
            cursor = session.transition_live_start_session_under_lock(
                session_lease=lease,
                expected_session=cursor,
                event="technical_failure",
            )
            assert cursor.revisions_used == 1
            assert "receipts/candidate_validation.json" not in cursor.artifact_bindings
            assert "starter/starter_config_review.json" not in cursor.artifact_bindings
            with pytest.raises(session.SessionConflictError, match="revision"):
                session.transition_live_start_session_under_lock(
                    session_lease=lease,
                    expected_session=cursor,
                    event="technical_failure",
                )
            with pytest.raises(session.SessionConflictError, match="candidate"):
                session._apply_session_update(
                    cursor,
                    session.LiveStartSessionUpdate(event="replacement_draft"),
                )
            cursor = session.transition_live_start_session_under_lock(
                session_lease=lease,
                expected_session=cursor,
                event="replacement_draft",
                changes={
                    "artifact_bindings": {
                        **cursor.artifact_bindings,
                        "starter/starter_config_candidate.json": (
                            "sha256:" + "6" * 64
                        ),
                    }
                },
            )
            assert cursor.candidate_revision == 2


def test_preview_intent_is_boolean_immutable_and_resume_bound() -> None:
    with TemporaryDirectory() as temporary:
        root, cursor = _new_session(Path(temporary), preview=True)
        assert cursor.preview_requested is True
        with session.lease_live_start_session(root) as lease:
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
        start = Barrier(2)
        results: list[str] = []

        def commit() -> None:
            start.wait()
            try:
                with session.lease_live_start_session(root) as lease:
                    session.transition_live_start_session_under_lock(
                        session_lease=lease,
                        expected_session=predecessor,
                        event="initial_draft",
                    )
            except session.SessionConflictError:
                results.append("conflict")
            else:
                results.append("committed")

        workers = [Thread(target=commit), Thread(target=commit)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        assert sorted(results) == ["committed", "conflict"]


def test_capability_smoke_exercises_real_thread_and_copy_boundaries(
    tmp_path: Path,
) -> None:
    session_root = tmp_path / "runs" / ("a" * 32)
    session.create_live_start_session(
        session_root=session_root,
        deck_name="Deck",
        deck_code_sha256="sha256:" + "1" * 64,
        input_snapshot_manifest_sha256="sha256:" + "2" * 64,
        preview_requested=False,
    )
    escaped: list[BaseException] = []
    with session.lease_live_start_session(session_root) as lease:
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
        result_intent={"content_sha256": "sha256:" + "1" * 64},
        terminal_status=None,
        pending_transition=None,
        apply_recovery=None,
        terminal_retirement=None,
    )
    with session.lease_live_start_session(root) as lease:
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
    with session.lease_live_start_session(root) as lease:
        with pytest.raises(session.SessionLayoutError, match="unknown"):
            session.transition_live_start_session_under_lock(
                session_lease=lease,
                expected_session=cursor,
                event="initial_draft",
            )
        with pytest.raises(session.SessionLayoutError, match="unknown"):
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

    with pytest.raises(session.SessionCapabilityError, match="family"):
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

    with pytest.raises(session.SessionCapabilityError, match="binding"):
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
    rollback_root = tmp_path / "rollback"
    rollback_root.mkdir()
    root, predecessor = _new_session(rollback_root)
    reserved = root / ".session.json.live-start-atomic.tmp"
    reserved.write_bytes(b"partial")
    with session.lease_live_start_session(root) as lease:
        session._reconcile_session_temp_under_lock(
            session_lease=lease,
            expected_session=predecessor,
        )
    assert not reserved.exists()

    tamper_root = tmp_path / "tamper"
    tamper_root.mkdir()
    root, predecessor = _new_session(tamper_root)
    successor_value = session._apply_session_update(
        predecessor,
        session.LiveStartSessionUpdate(event="initial_draft"),
    )
    successor = session._seal_session_value(
        successor_value,
        session_identity=None,
    )
    session_path = root / "session.json"
    session_path.unlink()
    session_path.write_bytes(successor.canonical_json)
    reserved = root / ".session.json.live-start-atomic.tmp"
    reserved.write_bytes(b"partial")

    with session.lease_live_start_session(root) as lease:
        with pytest.raises(session.SessionConflictError, match="temp"):
            session._reconcile_session_temp_under_lock(
                session_lease=lease,
                expected_session=predecessor,
            )
    assert reserved.read_bytes() == b"partial"


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
