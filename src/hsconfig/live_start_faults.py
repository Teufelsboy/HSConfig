"""Closed internal fault vocabulary for the live-start controller."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol


class LiveStartFaultPoint(StrEnum):
    AFTER_PENDING_TRANSITION_CAS = "after_pending_transition_cas"
    AFTER_TRANSITION_PRIMARY_ARTIFACT = "after_transition_primary_artifact"
    AFTER_TRANSITION_SECONDARY_ARTIFACT = "after_transition_secondary_artifact"
    BEFORE_TRANSITION_PHASE_CAS = "before_transition_phase_cas"
    AFTER_PREPUBLICATION_CAS = "after_prepublication_cas"
    AFTER_OUTPUT_OPERATION_ADMISSION_PREPARED = "after_output_operation_admission_prepared"
    AFTER_OUTPUT_OPERATION_ADMISSION_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS = "after_output_operation_admission_staging_flush_before_staging_bound_cas"
    AFTER_OUTPUT_OPERATION_ADMISSION_STAGING_BOUND = "after_output_operation_admission_staging_bound"
    AFTER_OUTPUT_OPERATION_ADMISSION_BOUND_COMMIT_BEFORE_CAS = "after_output_operation_admission_bound_commit_before_cas"
    AFTER_OUTPUT_OPERATION_ADMISSION_BOUND = "after_output_operation_admission_bound"
    AFTER_OUTPUT_CHILD_BOOTSTRAP_PREPARED = "after_output_child_bootstrap_prepared"
    AFTER_OUTPUT_CHILD_CLAIM_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS = "after_output_child_claim_staging_flush_before_staging_bound_cas"
    AFTER_OUTPUT_CHILD_CLAIM_STAGING_BOUND = "after_output_child_claim_staging_bound"
    AFTER_OUTPUT_CHILD_CLAIM_BOUND_COMMIT_BEFORE_CAS = "after_output_child_claim_bound_commit_before_cas"
    AFTER_OUTPUT_CHILD_CLAIM_BOUND = "after_output_child_claim_bound"
    AFTER_OUTPUT_CHILD_CREATE_BEFORE_CAS = "after_output_child_create_before_cas"
    AFTER_OUTPUT_CHILD_BOUND = "after_output_child_bound"
    AFTER_PUBLICATION_COMMIT_BEFORE_OUTPUT_CHILD_CLAIM_RETIREMENT = "after_publication_commit_before_output_child_claim_retirement"
    AFTER_OUTPUT_CHILD_CLAIM_RETIREMENT_PREPARED = "after_output_child_claim_retirement_prepared"
    AFTER_OUTPUT_CHILD_CLAIM_UNLINK_BEFORE_CAS = "after_output_child_claim_unlink_before_cas"
    AFTER_OUTPUT_CHILD_CLAIM_UNLINK_CAS = "after_output_child_claim_unlink_cas"
    AFTER_OUTPUT_CHILD_CLAIM_CONFIRMATION_BEFORE_RETIRED_CAS = "after_output_child_claim_confirmation_before_retired_cas"
    AFTER_OUTPUT_CHILD_CLAIM_RETIRED = "after_output_child_claim_retired"
    AFTER_OUTPUT_OPERATION_RELEASE_AUTHORIZED = "after_output_operation_release_authorized"
    AFTER_OUTPUT_OPERATION_ADMISSION_UNLINK = "after_output_operation_admission_unlink"
    AFTER_PREPUBLICATION_CLEANUP_INVENTORY_UNBOUND_STAGING_RETIRE_BEFORE_CAS = "after_prepublication_cleanup_inventory_unbound_staging_retire_before_cas"
    AFTER_PREPUBLICATION_CLEANUP_INVENTORY_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS = "after_prepublication_cleanup_inventory_staging_flush_before_staging_bound_cas"
    AFTER_PREPUBLICATION_CLEANUP_INVENTORY_STAGING_BOUND = "after_prepublication_cleanup_inventory_staging_bound"
    AFTER_PREPUBLICATION_CLEANUP_INVENTORY_BOUND_COMMIT_BEFORE_PRIMARY_APPLIED_CAS = "after_prepublication_cleanup_inventory_bound_commit_before_primary_applied_cas"
    AFTER_PREPUBLICATION_QUARANTINE = "after_prepublication_quarantine"
    AFTER_PREPUBLICATION_CLEANUP_ENTRY = "after_prepublication_cleanup_entry"
    AFTER_PREPUBLICATION_CLEANUP_INVENTORY_DELETE = "after_prepublication_cleanup_inventory_delete"
    AFTER_PREPUBLICATION_CLEANUP_BEFORE_CAS = "after_prepublication_cleanup_before_cas"
    AFTER_INVOCATION_PREPARED_BEFORE_ADMISSION = "after_invocation_prepared_before_admission"
    AFTER_RUNTIME_ADMISSION_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS = "after_runtime_admission_staging_flush_before_staging_bound_cas"
    AFTER_RUNTIME_ADMISSION_STAGING_BOUND = "after_runtime_admission_staging_bound"
    AFTER_RUNTIME_ADMISSION_BOUND_COMMIT_BEFORE_CAS = "after_runtime_admission_bound_commit_before_cas"
    AFTER_RUNTIME_LAYOUT_INTENT = "after_runtime_layout_intent"
    AFTER_RUNTIME_LAYOUT_DIRECTORY_CREATE_BEFORE_RECEIPT_CAS = "after_runtime_layout_directory_create_before_receipt_cas"
    AFTER_RUNTIME_LAYOUT_DIRECTORY_BOUND = "after_runtime_layout_directory_bound"
    AFTER_BOUND_STAGING_POSIX_LINK_BEFORE_UNLINK = "after_bound_staging_posix_link_before_unlink"
    AFTER_AUTHORIZATION_CONSUMED_BEFORE_PHYSICAL_CALLBACK = "after_authorization_consumed_before_physical_callback"
    AFTER_GENERIC_FILE_INNER_TEMP_CREATED = "after_generic_file_inner_temp_created"
    AFTER_GENERIC_FILE_INNER_TEMP_PARTIAL = "after_generic_file_inner_temp_partial"
    AFTER_GENERIC_FILE_INNER_TEMP_FULL = "after_generic_file_inner_temp_full"
    AFTER_GENERIC_FILE_INNER_TEMP_FLUSHED = "after_generic_file_inner_temp_flushed"
    AFTER_GENERIC_FILE_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS = "after_generic_file_staging_flush_before_staging_bound_cas"
    AFTER_GENERIC_FILE_BOUND_COMMIT_BEFORE_CAS = "after_generic_file_bound_commit_before_cas"
    AFTER_ADMISSION_BOUND_BEFORE_INVOCATION_WRITE = "after_admission_bound_before_invocation_write"
    AFTER_INVOCATION_RECEIPT_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS = "after_invocation_receipt_staging_flush_before_staging_bound_cas"
    AFTER_INVOCATION_RECEIPT_BOUND_COMMIT_BEFORE_CAS = "after_invocation_receipt_bound_commit_before_cas"
    AFTER_INVOCATION_WRITE_BEFORE_APPLY_STARTED = "after_invocation_write_before_apply_started"
    AFTER_APPLY_STARTED = "after_apply_started"
    AFTER_INITIAL_ATTEMPT_RECORD_COMMIT_BEFORE_CAS = "after_initial_attempt_record_commit_before_cas"
    AFTER_ROUTE_ATTEMPT_RECORD_COMMIT_BEFORE_CAS = "after_route_attempt_record_commit_before_cas"
    AFTER_RUNTIME_JOURNAL_CREATED = "after_runtime_journal_created"
    AFTER_RUNTIME_CANDIDATE_JOURNAL_BOUND_BEFORE_CANDIDATE_CREATE = "after_runtime_candidate_journal_bound_before_candidate_create"
    AFTER_RUNTIME_CANDIDATE_CREATE_BEFORE_CANDIDATE_IDENTITY_RECEIPT_CAS = "after_runtime_candidate_create_before_candidate_identity_receipt_cas"
    AFTER_CANDIDATE_TREE_ENTRY_BEFORE_CURSOR_CAS = "after_candidate_tree_entry_before_cursor_cas"
    AFTER_CANDIDATE_TREE_VERIFICATION_BEFORE_CAS = "after_candidate_tree_verification_before_cas"
    AFTER_CANDIDATE_TO_TARGET_RENAME_BEFORE_CAS = "after_candidate_to_target_rename_before_cas"
    AFTER_NEW_TARGET_INI_WRITE_BEFORE_CAS = "after_new_target_ini_write_before_cas"
    AFTER_PRIOR_OWNER_PLANNED_BEFORE_JOURNAL = "after_prior_owner_planned_before_journal"
    AFTER_PRIOR_OWNER_JOURNAL_CREATED_BEFORE_BOUND = "after_prior_owner_journal_created_before_bound"
    AFTER_PRIOR_OWNER_BOUND_BEFORE_INI = "after_prior_owner_bound_before_ini"
    AFTER_NONOWNING_INI_WRITE_BEFORE_JOURNAL_CAS = "after_nonowning_ini_write_before_journal_cas"
    AFTER_PHYSICAL_COMMIT_BEFORE_INSTALLER_RETURN = "after_physical_commit_before_installer_return"
    AFTER_INSTALLER_RETURN_BEFORE_APPLY_COMMITTED = "after_installer_return_before_apply_committed"
    AFTER_RESULT_INTENT = "after_result_intent"
    AFTER_ACKNOWLEDGEMENT_INTENT = "after_acknowledgement_intent"
    AFTER_RESULT_JSON_TEMP_CREATED = "after_result_json_temp_created"
    AFTER_RESULT_JSON_TEMP_PARTIAL = "after_result_json_temp_partial"
    AFTER_RESULT_JSON_TEMP_FULL = "after_result_json_temp_full"
    AFTER_RESULT_JSON_TEMP_FLUSHED = "after_result_json_temp_flushed"
    BEFORE_RESULT_JSON_REPLACE = "before_result_json_replace"
    AFTER_RESULT_JSON = "after_result_json"
    AFTER_RESULT_MARKDOWN_TEMP_CREATED = "after_result_markdown_temp_created"
    AFTER_RESULT_MARKDOWN_TEMP_PARTIAL = "after_result_markdown_temp_partial"
    AFTER_RESULT_MARKDOWN_TEMP_FULL = "after_result_markdown_temp_full"
    AFTER_RESULT_MARKDOWN_TEMP_FLUSHED = "after_result_markdown_temp_flushed"
    BEFORE_RESULT_MARKDOWN_REPLACE = "before_result_markdown_replace"
    AFTER_RESULT_MARKDOWN = "after_result_markdown"
    BEFORE_TERMINAL_CAS = "before_terminal_cas"
    AFTER_TERMINAL_CAS_BEFORE_ACK = "after_terminal_cas_before_ack"
    AFTER_TERMINAL_RETIREMENT_PREPARED = "after_terminal_retirement_prepared"
    AFTER_SUCCESS_ACK_JOURNAL_DELETE_BEFORE_STAGE_CAS = "after_success_ack_journal_delete_before_stage_cas"
    AFTER_SUCCESS_ACK_JOURNAL_RETIRED_CAS = "after_success_ack_journal_retired_cas"
    AFTER_SUCCESS_ACK_FENCE_DELETE_BEFORE_EVIDENCE_CAS = "after_success_ack_fence_delete_before_evidence_cas"
    AFTER_SUCCESS_ACK_EVIDENCE_RETIRED_CAS = "after_success_ack_evidence_retired_cas"
    AFTER_ATTEMPT_EVIDENCE_PHYSICAL_RETIREMENT_BEFORE_CAS = "after_attempt_evidence_physical_retirement_before_cas"
    AFTER_ATTEMPT_EVIDENCE_RETIRED_BEFORE_ADMISSION_RELEASE = "after_attempt_evidence_retired_before_admission_release"
    AFTER_TERMINAL_RECOVERY_RESOLUTION_PREPARED = "after_terminal_recovery_resolution_prepared"
    AFTER_TERMINAL_RECOVERY_METADATA_SUCCESSOR = "after_terminal_recovery_metadata_successor"
    AFTER_NONTERMINAL_RECOVERY_PHYSICAL_STEP_BEFORE_CURSOR_CAS = "after_nonterminal_recovery_physical_step_before_cursor_cas"
    AFTER_NONTERMINAL_RECOVERY_CURSOR_CAS = "after_nonterminal_recovery_cursor_cas"
    AFTER_FIRST_INSTALL_OBSERVATION_BEFORE_PREPARE_CAS = "after_first_install_observation_before_prepare_cas"
    AFTER_NONTERMINAL_OBSERVATION_BEFORE_PREPARE_CAS = "after_nonterminal_observation_before_prepare_cas"
    AFTER_TERMINAL_RESOLUTION_OBSERVATION_BEFORE_PREPARE_CAS = "after_terminal_resolution_observation_before_prepare_cas"
    AFTER_TERMINAL_CLASSIFICATION_OBSERVATION_BEFORE_SELECTION_CAS = "after_terminal_classification_observation_before_selection_cas"
    AFTER_TERMINAL_CLASSIFICATION_SELECTION_CAS = "after_terminal_classification_selection_cas"
    AFTER_RECOVERY_CLOSED_CAS_BEFORE_RESULT_INTENT = "after_recovery_closed_cas_before_result_intent"
    AFTER_CANDIDATE_LEAF_COPY_BEFORE_RECEIPT_CAS = "after_candidate_leaf_copy_before_receipt_cas"
    AFTER_CANDIDATE_TREE_VERIFY_BEFORE_RENAME = "after_candidate_tree_verify_before_rename"
    AFTER_TERMINAL_CLEANUP_INVENTORY_UNBOUND_STAGING_RETIRE_BEFORE_CAS = "after_terminal_cleanup_inventory_unbound_staging_retire_before_cas"
    AFTER_TERMINAL_CLEANUP_INVENTORY_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS = "after_terminal_cleanup_inventory_staging_flush_before_staging_bound_cas"
    AFTER_TERMINAL_CLEANUP_INVENTORY_STAGING_BOUND = "after_terminal_cleanup_inventory_staging_bound"
    AFTER_TERMINAL_CLEANUP_INVENTORY_BOUND_COMMIT_BEFORE_INVENTORY_BOUND_CAS = "after_terminal_cleanup_inventory_bound_commit_before_inventory_bound_cas"
    AFTER_TERMINAL_CLEANUP_INVENTORY_BOUND = "after_terminal_cleanup_inventory_bound"
    AFTER_TERMINAL_CLEANUP_STARTED = "after_terminal_cleanup_started"
    AFTER_TERMINAL_CLEANUP_ENTRY_DELETE_BEFORE_CURSOR_CAS = "after_terminal_cleanup_entry_delete_before_cursor_cas"
    AFTER_TERMINAL_CLEANUP_CURSOR_CAS = "after_terminal_cleanup_cursor_cas"
    AFTER_TERMINAL_CLEANUP_JOURNAL_DELETE_BEFORE_STAGE_CAS = "after_terminal_cleanup_journal_delete_before_stage_cas"
    AFTER_TERMINAL_CLEANUP_JOURNAL_RETIRED_CAS = "after_terminal_cleanup_journal_retired_cas"
    AFTER_TERMINAL_CLEANUP_FENCE_DELETE_BEFORE_STAGE_CAS = "after_terminal_cleanup_fence_delete_before_stage_cas"
    AFTER_TERMINAL_CLEANUP_FENCE_RETIRED_CAS = "after_terminal_cleanup_fence_retired_cas"
    AFTER_TERMINAL_CLEANUP_SIDECAR_DELETE_BEFORE_STAGE_CAS = "after_terminal_cleanup_sidecar_delete_before_stage_cas"
    AFTER_TERMINAL_CLEANUP_INVENTORY_RETIRED_CAS = "after_terminal_cleanup_inventory_retired_cas"
    AFTER_TERMINAL_RECOVERY_STABILIZED = "after_terminal_recovery_stabilized"
    AFTER_ADMISSION_RELEASE_AUTHORIZED_BEFORE_RUNTIME_ADMISSION_UNLINK = "after_admission_release_authorized_before_runtime_admission_unlink"
    AFTER_RUNTIME_ADMISSION_UNLINK = "after_runtime_admission_unlink"
    AFTER_OWNER_RETIREMENT_MANIFEST_BOUND_BEFORE_PREPARED_STAGING = "after_owner_retirement_manifest_bound_before_prepared_staging"
    AFTER_OWNER_RETIREMENT_PREPARED_STAGING_FLUSH_BEFORE_BOUND_CAS = "after_owner_retirement_prepared_staging_flush_before_bound_cas"
    AFTER_OWNER_RETIREMENT_PREPARED_COMMIT_BEFORE_CAS = "after_owner_retirement_prepared_commit_before_cas"
    AFTER_OWNER_CLEANUP_INITIAL_JOURNAL_STAGING_FLUSH_BEFORE_BOUND_CAS = "after_owner_cleanup_initial_journal_staging_flush_before_bound_cas"
    AFTER_OWNER_CLEANUP_INITIAL_JOURNAL_COMMIT_BEFORE_CAS = "after_owner_cleanup_initial_journal_commit_before_cas"
    AFTER_OWNER_CLEANUP_INITIALIZED_CURSOR_ZERO_CAS = "after_owner_cleanup_initialized_cursor_zero_cas"
    AFTER_OWNER_CLEANUP_ENTRY_BEFORE_RECEIPT_CAS = "after_owner_cleanup_entry_before_receipt_cas"
    AFTER_OWNER_CLEANUP_JOURNAL_COMMIT_BEFORE_CAS = "after_owner_cleanup_journal_commit_before_cas"
    AFTER_OWNER_COMPLETED_TOMBSTONE_COMMITMENT_CAS = "after_owner_completed_tombstone_commitment_cas"
    AFTER_OWNER_TARGET_ROOT_DELETE_BEFORE_RECEIPT_CAS = "after_owner_target_root_delete_before_receipt_cas"
    AFTER_OWNER_TARGET_ROOT_RETIRED_CAS = "after_owner_target_root_retired_cas"
    AFTER_OWNER_RETIREMENT_COMPLETED_STAGING_FLUSH_BEFORE_BOUND_CAS = "after_owner_retirement_completed_staging_flush_before_bound_cas"
    AFTER_OWNER_RETIREMENT_COMPLETED_COMMIT_BEFORE_CAS = "after_owner_retirement_completed_commit_before_cas"
    AFTER_OWNER_JOURNAL_DELETE_BEFORE_RECEIPT_CAS = "after_owner_journal_delete_before_receipt_cas"


class LiveStartFaultHook(Protocol):
    """One internal failure-injection callback over the closed vocabulary."""

    def __call__(self, point: LiveStartFaultPoint, /) -> None: ...


def no_live_start_fault(_point: LiveStartFaultPoint) -> None:
    """Default public fault hook; it never interrupts the controller."""


def invoke_live_start_fault(
    hook: LiveStartFaultHook,
    point: LiveStartFaultPoint,
) -> None:
    """Invoke one typed internal fault boundary."""

    if not isinstance(point, LiveStartFaultPoint):
        raise TypeError("live_start_fault_point_invalid")
    hook(point)


__all__ = (
    "LiveStartFaultHook",
    "LiveStartFaultPoint",
    "invoke_live_start_fault",
    "no_live_start_fault",
)
