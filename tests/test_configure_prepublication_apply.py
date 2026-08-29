from __future__ import annotations

import importlib
import json
import multiprocessing
import os
import pickle
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from inspect import signature
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from typing import Any, Iterator

import pytest

from hsconfig import live_start_session as session
from hsconfig.atomic_io import (
    ExclusiveFileLock,
    atomic_commit_bound_staging_no_replace,
    atomic_materialize_staging_bytes,
    atomic_write_reserved_bytes,
)
from hsconfig.configure_run_model import write_rendered_configure_run
from hsconfig.operator_profile import (
    lease_operator_profile,
    load_operator_profile,
    operator_profile_path,
)
from hsconfig.output_operation_admission import (
    lease_output_operation_admission,
    output_operation_admission_path,
    output_operation_admission_reserved_temp_path,
    output_operation_admission_staging_path,
)
from hsconfig.package_io import path_identity
from tests.test_starter_compiler import _single_candidate_request


EXPECTED_COMMITTED_EVENTS = [
    "rendered",
    "strict_validated",
    "derivation_replayed",
    "operator_summary_recomputed",
    "package_validation_receipt_written",
    "package_validated_cas",
    "fake_apply_planned",
    "diagnostic_receipt_written",
    "prepublication_check_passed_cas",
    "profile_lease_enter",
    "profile_rebound_under_lease",
    "output_precondition_rebound",
    "output_operation_lock_enter",
    "output_child_bootstrap_lock_enter",
    "output_base_identity_lease_enter",
    "output_operation_admission_prepared_cas",
    "output_operation_admission_staging_flushed",
    "output_operation_admission_publish",
    "output_operation_admission_bound_cas",
    "output_child_bootstrap_prepared_cas",
    "output_child_claim_publish",
    "output_child_claim_bound_cas",
    "output_child_created_or_confirmed",
    "output_child_bound_cas",
    "output_deck_identity_lease_enter",
    "published",
    "publication_committed_cas",
    "output_child_claim_retirement_prepared",
    "output_child_claim_unlink",
    "output_child_claim_unlink_cas",
    "output_child_claim_absence_current_confirmed",
    "output_child_claim_retired_cas",
    "output_operation_admission_still_active",
    "output_child_bootstrap_lock_exit",
    "prepublication_cleanup_inventory_staging_flushed",
    "prepublication_cleanup_inventory_staging_bound_cas",
    "prepublication_cleanup_inventory_bound_commit",
    "prepublication_cleanup_inventory_primary_applied_cas",
    "prepublication_quarantine",
    "prepublication_cleanup_inventory_deleted",
    "prepublication_cleanup_complete_cas",
    "output_deck_identity_lease_exit",
    "output_base_identity_lease_exit",
    "profile_lease_still_active",
    "output_operation_lock_still_active",
]


_EXPECTED_LIVE_START_FAULT_VALUES = tuple(
    """after_pending_transition_cas
after_transition_primary_artifact
after_transition_secondary_artifact
before_transition_phase_cas
after_prepublication_cas
after_output_operation_admission_prepared
after_output_operation_admission_staging_flush_before_staging_bound_cas
after_output_operation_admission_staging_bound
after_output_operation_admission_bound_commit_before_cas
after_output_operation_admission_bound
after_output_child_bootstrap_prepared
after_output_child_claim_staging_flush_before_staging_bound_cas
after_output_child_claim_staging_bound
after_output_child_claim_bound_commit_before_cas
after_output_child_claim_bound
after_output_child_create_before_cas
after_output_child_bound
after_publication_commit_before_output_child_claim_retirement
after_output_child_claim_retirement_prepared
after_output_child_claim_unlink_before_cas
after_output_child_claim_unlink_cas
after_output_child_claim_confirmation_before_retired_cas
after_output_child_claim_retired
after_output_operation_release_authorized
after_output_operation_admission_unlink
after_prepublication_cleanup_inventory_unbound_staging_retire_before_cas
after_prepublication_cleanup_inventory_staging_flush_before_staging_bound_cas
after_prepublication_cleanup_inventory_staging_bound
after_prepublication_cleanup_inventory_bound_commit_before_primary_applied_cas
after_prepublication_quarantine
after_prepublication_cleanup_entry
after_prepublication_cleanup_inventory_delete
after_prepublication_cleanup_before_cas
after_invocation_prepared_before_admission
after_runtime_admission_staging_flush_before_staging_bound_cas
after_runtime_admission_staging_bound
after_runtime_admission_bound_commit_before_cas
after_runtime_layout_intent
after_runtime_layout_directory_create_before_receipt_cas
after_runtime_layout_directory_bound
after_bound_staging_posix_link_before_unlink
after_authorization_consumed_before_physical_callback
after_generic_file_staging_flush_before_staging_bound_cas
after_generic_file_bound_commit_before_cas
after_admission_bound_before_invocation_write
after_invocation_receipt_staging_flush_before_staging_bound_cas
after_invocation_receipt_bound_commit_before_cas
after_invocation_write_before_apply_started
after_apply_started
after_initial_attempt_record_commit_before_cas
after_route_attempt_record_commit_before_cas
after_runtime_journal_created
after_runtime_candidate_journal_bound_before_candidate_create
after_runtime_candidate_create_before_candidate_identity_receipt_cas
after_candidate_tree_entry_before_cursor_cas
after_candidate_tree_verification_before_cas
after_candidate_to_target_rename_before_cas
after_new_target_ini_write_before_cas
after_prior_owner_planned_before_journal
after_prior_owner_journal_created_before_bound
after_prior_owner_bound_before_ini
after_nonowning_ini_write_before_journal_cas
after_physical_commit_before_installer_return
after_installer_return_before_apply_committed
after_result_intent
after_acknowledgement_intent
after_result_json_temp_created
after_result_json_temp_partial
after_result_json_temp_full
after_result_json_temp_flushed
before_result_json_replace
after_result_json
after_result_markdown_temp_created
after_result_markdown_temp_partial
after_result_markdown_temp_full
after_result_markdown_temp_flushed
before_result_markdown_replace
after_result_markdown
before_terminal_cas
after_terminal_cas_before_ack
after_terminal_retirement_prepared
after_success_ack_journal_delete_before_stage_cas
after_success_ack_journal_retired_cas
after_success_ack_fence_delete_before_evidence_cas
after_success_ack_evidence_retired_cas
after_attempt_evidence_physical_retirement_before_cas
after_attempt_evidence_retired_before_admission_release
after_terminal_recovery_resolution_prepared
after_terminal_recovery_metadata_successor
after_nonterminal_recovery_physical_step_before_cursor_cas
after_nonterminal_recovery_cursor_cas
after_first_install_observation_before_prepare_cas
after_nonterminal_observation_before_prepare_cas
after_terminal_resolution_observation_before_prepare_cas
after_terminal_classification_observation_before_selection_cas
after_terminal_classification_selection_cas
after_recovery_closed_cas_before_result_intent
after_candidate_leaf_copy_before_receipt_cas
after_candidate_tree_verify_before_rename
after_terminal_cleanup_inventory_unbound_staging_retire_before_cas
after_terminal_cleanup_inventory_staging_flush_before_staging_bound_cas
after_terminal_cleanup_inventory_staging_bound
after_terminal_cleanup_inventory_bound_commit_before_inventory_bound_cas
after_terminal_cleanup_inventory_bound
after_terminal_cleanup_started
after_terminal_cleanup_entry_delete_before_cursor_cas
after_terminal_cleanup_cursor_cas
after_terminal_cleanup_journal_delete_before_stage_cas
after_terminal_cleanup_journal_retired_cas
after_terminal_cleanup_fence_delete_before_stage_cas
after_terminal_cleanup_fence_retired_cas
after_terminal_cleanup_sidecar_delete_before_stage_cas
after_terminal_cleanup_inventory_retired_cas
after_terminal_recovery_stabilized
after_admission_release_authorized_before_runtime_admission_unlink
after_runtime_admission_unlink
after_owner_retirement_manifest_bound_before_prepared_staging
after_owner_retirement_prepared_staging_flush_before_bound_cas
after_owner_retirement_prepared_commit_before_cas
after_owner_cleanup_initial_journal_staging_flush_before_bound_cas
after_owner_cleanup_initial_journal_commit_before_cas
after_owner_cleanup_initialized_cursor_zero_cas
after_owner_cleanup_entry_before_receipt_cas
after_owner_cleanup_journal_commit_before_cas
after_owner_completed_tombstone_commitment_cas
after_owner_target_root_delete_before_receipt_cas
after_owner_target_root_retired_cas
after_owner_retirement_completed_staging_flush_before_bound_cas
after_owner_retirement_completed_commit_before_cas
after_owner_journal_delete_before_receipt_cas""".splitlines()
)


def _expected_committed_event_records(
    disposition: str,
) -> list[tuple[str, dict[str, str] | None]]:
    assert disposition in {"created", "confirmed"}
    return [
        (
            event,
            {"disposition": disposition}
            if event == "output_child_created_or_confirmed"
            else None,
        )
        for event in EXPECTED_COMMITTED_EVENTS
    ]


def _event_recorder(
    records: list[tuple[str, dict[str, str] | None]],
):
    def record(
        event: str,
        payload: dict[str, str] | None = None,
    ) -> None:
        records.append((event, payload))

    return record


def _controller() -> Any:
    """Load the Task-8 composition root at test execution, not collection."""

    return importlib.import_module("hsconfig.live_start_controller")


def _publisher_lock_contender(
    lock_path: str,
    attempted: Any,
    acquired: Any,
    release: Any,
) -> None:
    attempted.set()
    with ExclusiveFileLock(Path(lock_path)):
        acquired.set()
        if not release.wait(30):
            raise AssertionError("publisher_lock_contender_release_timeout")


def _faults() -> Any:
    return importlib.import_module("hsconfig.live_start_faults")


def _assert_live_start_fault_contract_and_public_default(
    controller: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    faults = _faults()
    actual = tuple(point.value for point in faults.LiveStartFaultPoint)
    assert actual == _EXPECTED_LIVE_START_FAULT_VALUES
    assert len(actual) == len(set(actual)) == 130
    assert "fault_hook" not in signature(
        controller.lease_validated_prepublication
    ).parameters
    assert "fault_hook" not in signature(
        controller.publish_validated_prepublication
    ).parameters

    observed_hooks: list[Any] = []
    marker = object()

    @contextmanager
    def observe_internal(**kwargs: Any) -> Iterator[object]:
        observed_hooks.append(kwargs["fault_hook"])
        yield marker

    with monkeypatch.context() as seam_patch:
        seam_patch.setattr(
            controller,
            "_lease_validated_prepublication",
            observe_internal,
        )
        with controller.lease_validated_prepublication(
            run_model=object(),
            session_lease=object(),
            expected_session=object(),
            runtime_root=Path("unused"),
        ) as yielded:
            assert yielded is marker
    assert observed_hooks == [faults.no_live_start_fault]


def _poison_frozen_authority_reloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def poison(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("frozen_authority_reload_attempted")

    reload_surfaces = {
        "hsconfig.input_loading": (
            "load_guide_sources",
            "load_source_documents",
            "load_source_evidence",
            "load_source_search_records",
        ),
        "hsconfig.build_input_catalog": (
            "load_packaged_audited_build_inputs",
            "load_packaged_audited_build_resource_store",
        ),
        "hsconfig.package_request": (
            "load_packaged_audited_build_inputs",
            "load_packaged_audited_build_resource_store",
            "load_policy_profile",
            "load_globalvalues_baseline",
        ),
        "hsconfig.starter_decision": ("load_validated_starter_selection",),
        "hsconfig.package_compiler": (
            "_compile_conservative_package_decisions",
            "_compile_legacy_optimized_package_decisions",
        ),
    }
    for module_name, names in reload_surfaces.items():
        module = importlib.import_module(module_name)
        for name in names:
            monkeypatch.setattr(module, name, poison)


def _assert_exact_frozen_stage_authority(
    run_model: Any,
    request: Any,
) -> None:
    expected = {
        "01_manifest/input_snapshot_manifest.json": (
            request.frozen_compiler_inputs.manifest.document.canonical_json
        ),
        "02_source_documents/source_documents.json": (
            request.frozen_compiler_inputs.source_documents.canonical_json
        ),
        "03_research/starter_context.json": (
            request.starter_approval.context.document.canonical_json
        ),
    }
    actual = {
        artifact.relative_path: artifact.content
        for artifact in run_model.stage_artifacts
        if artifact.relative_path != "configure_summary.json"
    }
    assert actual == expected
    assert {artifact.relative_path for artifact in run_model.stage_artifacts} == {
        *expected,
        "configure_summary.json",
    }


def _tree_bytes(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _physical_tree(root: Path) -> dict[str, tuple[str, tuple[int, int, int], bytes | None]]:
    if not root.exists():
        return {}
    snapshot: dict[str, tuple[str, tuple[int, int, int], bytes | None]] = {
        ".": ("directory", path_identity(root), None)
    }
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            snapshot[relative] = ("directory", path_identity(path), None)
        elif path.is_file():
            snapshot[relative] = ("file", path_identity(path), path.read_bytes())
        else:
            snapshot[relative] = ("unsafe", path_identity(path), None)
    return snapshot


def _file_fingerprint(
    path: Path,
) -> tuple[tuple[int, int, int], int, str] | None:
    if not path.is_file():
        return None
    raw = path.read_bytes()
    return path_identity(path), len(raw), "sha256:" + sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class _HardKillExpectation:
    occurrence: int
    durable_cas_count_at_kill: int
    phase: str
    pending_operation: str | None
    pending_stage: str | None
    external_action_kind: str | None
    external_action_stage: str | None
    external_action_index: int | None
    cleanup_cursor: int | None
    first_resumed_fault: str
    durable_rows_before_first_fault: int
    remaining_rows_offset: int
    remaining_rows_per_cleanup_entry: int
    receipt_paths: tuple[str, ...]
    durable_rows: dict[str, object]


_REVIEW_RECEIPTS = (
    "receipts/candidate_validation.json",
    "receipts/review_validation.json",
)
_PACKAGE_RECEIPTS = (
    "receipts/candidate_validation.json",
    "receipts/package_validation.json",
    "receipts/review_validation.json",
)
_ALL_PREPUBLICATION_RECEIPTS = (
    "receipts/candidate_validation.json",
    "receipts/package_validation.json",
    "receipts/prepublication_apply_check.json",
    "receipts/review_validation.json",
)
_PREPUBLICATION_MATERIALIZATION_DURABLE_CAS_DELTA = 68


def _expected_durable_rows(
    *,
    receipts: tuple[str, ...] = _ALL_PREPUBLICATION_RECEIPTS,
    published: bool = False,
    operation_final: bool = False,
    operation_staging: bool = False,
    claim_surfaces: int = 0,
    work_present: bool = True,
    generic_staging: int = 0,
) -> dict[str, object]:
    return {
        "receipts": receipts,
        "current_count": int(published),
        "revision_count": int(published),
        "transaction_count": int(published),
        "operation_final_count": int(operation_final),
        "operation_staging_count": int(operation_staging),
        "operation_inner_temp_count": 0,
        "claim_surface_count": claim_surfaces,
        "work_present": work_present,
        "generic_staging_count": generic_staging,
        "generic_inner_temp_count": 0,
    }


def _hard_kill_expectation(
    fault_name: str,
    *,
    occurrence: int = 1,
) -> _HardKillExpectation:
    common: dict[str, object] = {
        "phase": "PREPUBLICATION_CHECK_PASSED",
        "pending_operation": None,
        "pending_stage": None,
        "external_action_kind": None,
        "external_action_stage": None,
        "external_action_index": None,
        "cleanup_cursor": None,
        "receipt_paths": _ALL_PREPUBLICATION_RECEIPTS,
        "remaining_rows_per_cleanup_entry": 1,
    }
    if fault_name == "AFTER_PREPUBLICATION_CLEANUP_ENTRY":
        if occurrence < 1:
            raise AssertionError("cleanup occurrence must be positive")
        return _HardKillExpectation(
            occurrence=occurrence,
            **{
                **common,
                "durable_cas_count_at_kill": (
                    21
                    + _PREPUBLICATION_MATERIALIZATION_DURABLE_CAS_DELTA
                    + occurrence
                ),
                "phase": "PUBLICATION_COMMITTED",
                "pending_operation": "cleanup_prepublication",
                "pending_stage": "CLEANUP_DELETING",
                "cleanup_cursor": occurrence - 1,
                "first_resumed_fault": "after_prepublication_cleanup_entry",
                "durable_rows_before_first_fault": 0,
                "remaining_rows_offset": 2 - occurrence,
                "durable_rows": _expected_durable_rows(
                    published=True,
                    operation_final=True,
                    work_present=False,
                ),
            },
        )

    receipt_cases: dict[tuple[str, int], dict[str, object]] = {
        ("AFTER_PENDING_TRANSITION_CAS", 2): {
            "durable_cas_count_at_kill": 2,
            "phase": "REVIEW_APPROVED",
            "pending_operation": "install_package_validation",
            "pending_stage": "PREPARED",
            "first_resumed_fault": "after_transition_primary_artifact",
            "durable_rows_before_first_fault": 0,
            "remaining_rows_offset": 21,
            "receipt_paths": _REVIEW_RECEIPTS,
            "durable_rows": _expected_durable_rows(
                receipts=_REVIEW_RECEIPTS,
            ),
        },
        ("AFTER_TRANSITION_PRIMARY_ARTIFACT", 2): {
            "durable_cas_count_at_kill": 2,
            "phase": "REVIEW_APPROVED",
            "pending_operation": "install_package_validation",
            "pending_stage": "PREPARED",
            "first_resumed_fault": "before_transition_phase_cas",
            "durable_rows_before_first_fault": 1,
            "remaining_rows_offset": 21,
            "receipt_paths": _REVIEW_RECEIPTS,
            "durable_rows": _expected_durable_rows(
                receipts=_PACKAGE_RECEIPTS,
            ),
        },
        ("BEFORE_TRANSITION_PHASE_CAS", 1): {
            "durable_cas_count_at_kill": 3,
            "phase": "REVIEW_APPROVED",
            "pending_operation": "install_package_validation",
            "pending_stage": "PRIMARY_APPLIED",
            "first_resumed_fault": "before_transition_phase_cas",
            "durable_rows_before_first_fault": 0,
            "remaining_rows_offset": 20,
            "receipt_paths": _REVIEW_RECEIPTS,
            "durable_rows": _expected_durable_rows(
                receipts=_PACKAGE_RECEIPTS,
            ),
        },
        ("AFTER_PENDING_TRANSITION_CAS", 3): {
            "durable_cas_count_at_kill": 5,
            "phase": "PACKAGE_VALIDATED",
            "pending_operation": "install_prepublication_validation",
            "pending_stage": "PREPARED",
            "first_resumed_fault": "after_transition_primary_artifact",
            "durable_rows_before_first_fault": 0,
            "remaining_rows_offset": 18,
            "receipt_paths": _PACKAGE_RECEIPTS,
            "durable_rows": _expected_durable_rows(
                receipts=_PACKAGE_RECEIPTS,
            ),
        },
        ("AFTER_TRANSITION_PRIMARY_ARTIFACT", 3): {
            "durable_cas_count_at_kill": 5,
            "phase": "PACKAGE_VALIDATED",
            "pending_operation": "install_prepublication_validation",
            "pending_stage": "PREPARED",
            "first_resumed_fault": "before_transition_phase_cas",
            "durable_rows_before_first_fault": 1,
            "remaining_rows_offset": 18,
            "receipt_paths": _PACKAGE_RECEIPTS,
            "durable_rows": _expected_durable_rows(),
        },
        ("BEFORE_TRANSITION_PHASE_CAS", 2): {
            "durable_cas_count_at_kill": 6,
            "phase": "PACKAGE_VALIDATED",
            "pending_operation": "install_prepublication_validation",
            "pending_stage": "PRIMARY_APPLIED",
            "first_resumed_fault": "before_transition_phase_cas",
            "durable_rows_before_first_fault": 0,
            "remaining_rows_offset": 17,
            "receipt_paths": _PACKAGE_RECEIPTS,
            "durable_rows": _expected_durable_rows(),
        },
    }
    receipt_case = receipt_cases.get((fault_name, occurrence))
    if receipt_case is not None:
        receipt_case = dict(receipt_case)
        receipt_case["durable_cas_count_at_kill"] = int(
            receipt_case["durable_cas_count_at_kill"]
        ) + _PREPUBLICATION_MATERIALIZATION_DURABLE_CAS_DELTA
        return _HardKillExpectation(
            occurrence=occurrence,
            **{**common, **receipt_case},
        )

    cases: dict[str, dict[str, object]] = {
        "AFTER_PREPUBLICATION_CAS": {
            "durable_cas_count_at_kill": 7,
            "first_resumed_fault": "after_output_operation_admission_prepared",
            "durable_rows_before_first_fault": 1,
            "remaining_rows_offset": 16,
            "durable_rows": _expected_durable_rows(),
        },
        "AFTER_OUTPUT_OPERATION_ADMISSION_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS": {
            "durable_cas_count_at_kill": 8,
            "pending_operation": "install_output_operation_admission",
            "pending_stage": "PREPARED",
            "external_action_kind": (
                "materialize_output_operation_admission_staging"
            ),
            "external_action_stage": "PLANNED",
            "external_action_index": 0,
            "first_resumed_fault": (
                "after_output_operation_admission_staging_flush_before_staging_bound_cas"
            ),
            "durable_rows_before_first_fault": 1,
            "remaining_rows_offset": 16,
            "durable_rows": _expected_durable_rows(
                operation_staging=True,
                generic_staging=1,
            ),
        },
        "AFTER_OUTPUT_OPERATION_ADMISSION_BOUND": {
            "durable_cas_count_at_kill": 10,
            "first_resumed_fault": "after_output_child_bootstrap_prepared",
            "durable_rows_before_first_fault": 1,
            "remaining_rows_offset": 13,
            "durable_rows": _expected_durable_rows(operation_final=True),
        },
        "AFTER_OUTPUT_CHILD_BOOTSTRAP_PREPARED": {
            "durable_cas_count_at_kill": 11,
            "pending_operation": "bootstrap_output_child",
            "pending_stage": "PREPARED",
            "external_action_kind": "materialize_claim_staging",
            "external_action_stage": "PLANNED",
            "external_action_index": 0,
            "first_resumed_fault": (
                "after_output_child_claim_staging_flush_before_staging_bound_cas"
            ),
            "durable_rows_before_first_fault": 0,
            "remaining_rows_offset": 12,
            "durable_rows": _expected_durable_rows(operation_final=True),
        },
        "AFTER_OUTPUT_CHILD_CLAIM_BOUND": {
            "durable_cas_count_at_kill": 13,
            "pending_operation": "bootstrap_output_child",
            "pending_stage": "PRIMARY_APPLIED",
            "first_resumed_fault": "after_output_child_create_before_cas",
            "durable_rows_before_first_fault": 0,
            "remaining_rows_offset": 10,
            "durable_rows": _expected_durable_rows(
                operation_final=True,
                claim_surfaces=1,
            ),
        },
        "AFTER_OUTPUT_CHILD_CREATE_BEFORE_CAS": {
            "durable_cas_count_at_kill": 13,
            "pending_operation": "bootstrap_output_child",
            "pending_stage": "PRIMARY_APPLIED",
            "first_resumed_fault": "after_output_child_create_before_cas",
            "durable_rows_before_first_fault": 0,
            "remaining_rows_offset": 10,
            "durable_rows": _expected_durable_rows(
                operation_final=True,
                claim_surfaces=1,
            ),
        },
        "AFTER_OUTPUT_CHILD_BOUND": {
            "durable_cas_count_at_kill": 14,
            "first_resumed_fault": (
                "after_publication_commit_before_output_child_claim_retirement"
            ),
            "durable_rows_before_first_fault": 0,
            "remaining_rows_offset": 9,
            "durable_rows": _expected_durable_rows(
                operation_final=True,
                claim_surfaces=1,
            ),
        },
        "AFTER_PUBLICATION_COMMIT_BEFORE_OUTPUT_CHILD_CLAIM_RETIREMENT": {
            "durable_cas_count_at_kill": 14,
            "first_resumed_fault": (
                "after_publication_commit_before_output_child_claim_retirement"
            ),
            "durable_rows_before_first_fault": 0,
            "remaining_rows_offset": 9,
            "durable_rows": _expected_durable_rows(
                published=True,
                operation_final=True,
                claim_surfaces=1,
            ),
        },
        "AFTER_OUTPUT_CHILD_CLAIM_RETIREMENT_PREPARED": {
            "durable_cas_count_at_kill": 16,
            "phase": "PUBLICATION_COMMITTED",
            "pending_operation": "retire_output_child_claim",
            "pending_stage": "PREPARED",
            "first_resumed_fault": "after_output_child_claim_unlink_before_cas",
            "durable_rows_before_first_fault": 0,
            "remaining_rows_offset": 7,
            "durable_rows": _expected_durable_rows(
                published=True,
                operation_final=True,
                claim_surfaces=1,
            ),
        },
        "AFTER_OUTPUT_CHILD_CLAIM_UNLINK_BEFORE_CAS": {
            "durable_cas_count_at_kill": 16,
            "phase": "PUBLICATION_COMMITTED",
            "pending_operation": "retire_output_child_claim",
            "pending_stage": "PREPARED",
            "first_resumed_fault": "after_output_child_claim_unlink_before_cas",
            "durable_rows_before_first_fault": 0,
            "remaining_rows_offset": 7,
            "durable_rows": _expected_durable_rows(
                published=True,
                operation_final=True,
                work_present=True,
            ),
        },
        "AFTER_OUTPUT_CHILD_CLAIM_CONFIRMATION_BEFORE_RETIRED_CAS": {
            "durable_cas_count_at_kill": 17,
            "phase": "PUBLICATION_COMMITTED",
            "pending_operation": "retire_output_child_claim",
            "pending_stage": "PRIMARY_APPLIED",
            "first_resumed_fault": (
                "after_output_child_claim_confirmation_before_retired_cas"
            ),
            "durable_rows_before_first_fault": 0,
            "remaining_rows_offset": 6,
            "durable_rows": _expected_durable_rows(
                published=True,
                operation_final=True,
            ),
        },
        "AFTER_PREPUBLICATION_CLEANUP_INVENTORY_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS": {
            "durable_cas_count_at_kill": 19,
            "phase": "PUBLICATION_COMMITTED",
            "pending_operation": "cleanup_prepublication",
            "pending_stage": "PREPARED",
            "external_action_kind": (
                "materialize_prepublication_cleanup_inventory_staging"
            ),
            "external_action_stage": "PLANNED",
            "external_action_index": 0,
            "cleanup_cursor": 0,
            "first_resumed_fault": (
                "after_prepublication_cleanup_inventory_unbound_staging_retire_before_cas"
            ),
            "durable_rows_before_first_fault": 0,
            "remaining_rows_offset": 5,
            "durable_rows": _expected_durable_rows(
                published=True,
                operation_final=True,
                generic_staging=1,
            ),
        },
        "AFTER_PREPUBLICATION_CLEANUP_INVENTORY_STAGING_BOUND": {
            "durable_cas_count_at_kill": 20,
            "phase": "PUBLICATION_COMMITTED",
            "pending_operation": "cleanup_prepublication",
            "pending_stage": "STAGING_BOUND",
            "external_action_kind": (
                "commit_bound_prepublication_cleanup_inventory"
            ),
            "external_action_stage": "STAGING_BOUND",
            "external_action_index": 0,
            "cleanup_cursor": 0,
            "first_resumed_fault": (
                "after_prepublication_cleanup_inventory_bound_commit_before_primary_applied_cas"
            ),
            "durable_rows_before_first_fault": 0,
            "remaining_rows_offset": 3,
            "durable_rows": _expected_durable_rows(
                published=True,
                operation_final=True,
                generic_staging=1,
            ),
        },
        "AFTER_PREPUBLICATION_CLEANUP_INVENTORY_BOUND_COMMIT_BEFORE_PRIMARY_APPLIED_CAS": {
            "durable_cas_count_at_kill": 20,
            "phase": "PUBLICATION_COMMITTED",
            "pending_operation": "cleanup_prepublication",
            "pending_stage": "STAGING_BOUND",
            "external_action_kind": (
                "commit_bound_prepublication_cleanup_inventory"
            ),
            "external_action_stage": "STAGING_BOUND",
            "external_action_index": 0,
            "cleanup_cursor": 0,
            "first_resumed_fault": (
                "after_prepublication_cleanup_inventory_bound_commit_before_primary_applied_cas"
            ),
            "durable_rows_before_first_fault": 0,
            "remaining_rows_offset": 3,
            "durable_rows": _expected_durable_rows(
                published=True,
                operation_final=True,
            ),
        },
        "AFTER_PREPUBLICATION_QUARANTINE": {
            "durable_cas_count_at_kill": 21,
            "phase": "PUBLICATION_COMMITTED",
            "pending_operation": "cleanup_prepublication",
            "pending_stage": "PRIMARY_APPLIED",
            "cleanup_cursor": 0,
            "first_resumed_fault": "after_prepublication_quarantine",
            "durable_rows_before_first_fault": 0,
            "remaining_rows_offset": 2,
            "durable_rows": _expected_durable_rows(
                published=True,
                operation_final=True,
                work_present=False,
            ),
        },
        "AFTER_PREPUBLICATION_CLEANUP_BEFORE_CAS": {
            "durable_cas_count_at_kill": -1,
            "phase": "PUBLICATION_COMMITTED",
            "pending_operation": "cleanup_prepublication",
            "pending_stage": "CLEANUP_DELETING",
            "cleanup_cursor": -1,
            "first_resumed_fault": "after_prepublication_cleanup_before_cas",
            "durable_rows_before_first_fault": 0,
            "remaining_rows_offset": 1,
            "remaining_rows_per_cleanup_entry": 0,
            "durable_rows": _expected_durable_rows(
                published=True,
                operation_final=True,
                work_present=False,
            ),
        },
        "AFTER_PREPUBLICATION_CLEANUP_INVENTORY_DELETE": {
            "durable_cas_count_at_kill": -1,
            "phase": "PUBLICATION_COMMITTED",
            "pending_operation": "cleanup_prepublication",
            "pending_stage": "CLEANUP_DELETING",
            "cleanup_cursor": -1,
            "first_resumed_fault": "after_prepublication_cleanup_before_cas",
            "durable_rows_before_first_fault": 0,
            "remaining_rows_offset": 1,
            "remaining_rows_per_cleanup_entry": 0,
            "durable_rows": _expected_durable_rows(
                published=True,
                operation_final=True,
                work_present=False,
            ),
        },
    }
    case = cases.get(fault_name)
    if case is None:
        raise AssertionError(
            f"hard-kill expectation missing: {fault_name} occurrence {occurrence}"
        )
    case = dict(case)
    durable_cas_count = int(case["durable_cas_count_at_kill"])
    if durable_cas_count >= 0:
        case["durable_cas_count_at_kill"] = (
            durable_cas_count
            + _PREPUBLICATION_MATERIALIZATION_DURABLE_CAS_DELTA
        )
    return _HardKillExpectation(
        occurrence=occurrence,
        **{**common, **case},
    )


def _crash_cursor_projection(current: session.LiveStartSession) -> dict[str, object]:
    value = current.to_value()
    pending = value.get("pending_transition")
    pending_value = pending if isinstance(pending, dict) else {}
    external = pending_value.get("external_file_action")
    external_value = external if isinstance(external, dict) else {}
    return {
        "content_sha256": value["content_sha256"],
        "phase": value["phase"],
        "pending_operation": pending_value.get("operation"),
        "pending_stage": pending_value.get("stage"),
        "external_action_kind": external_value.get("action_kind"),
        "external_action_stage": external_value.get("stage"),
        "external_action_index": external_value.get("action_index"),
        "cleanup_cursor": pending_value.get("cleanup_cursor"),
        "artifact_receipts": {
            path: digest
            for path, digest in value["artifact_bindings"].items()
            if path.startswith("receipts/")
        },
        "prepublication_work_binding": value.get(
            "prepublication_work_binding"
        ),
        "output_operation_admission_binding": value.get(
            "output_operation_admission_binding"
        ),
        "output_child_binding": value.get("output_child_binding"),
        "publication_binding": value.get("publication_binding"),
    }


def _persist_worker_oracle(path: Path, value: dict[str, object]) -> None:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        assert os.write(descriptor, raw) == len(raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _append_durable_jsonl(path: Path, value: dict[str, object]) -> None:
    raw = (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        assert os.write(descriptor, raw) == len(raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _cas_trace_row(
    *,
    ordinal: int,
    predecessor: session.LiveStartSession,
    successor: session.LiveStartSession,
) -> dict[str, object]:
    cursor = _crash_cursor_projection(successor)
    return {
        "ordinal": ordinal,
        "predecessor_sha256": predecessor.content_sha256,
        "successor_sha256": successor.content_sha256,
        "phase": cursor["phase"],
        "operation": cursor["pending_operation"],
        "stage": cursor["pending_stage"],
        "external_action_kind": cursor["external_action_kind"],
        "external_stage": cursor["external_action_stage"],
        "cleanup_cursor": cursor["cleanup_cursor"],
    }


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _assert_cas_trace_chain(
    rows: list[dict[str, object]],
    *,
    predecessor_sha256: str,
    successor_sha256: str,
) -> None:
    assert rows
    assert [row["ordinal"] for row in rows] == list(range(1, len(rows) + 1))
    assert rows[0]["predecessor_sha256"] == predecessor_sha256
    for previous, current in zip(rows, rows[1:], strict=False):
        assert current["predecessor_sha256"] == previous["successor_sha256"]
    assert rows[-1]["successor_sha256"] == successor_sha256
    successor_digests = [row["successor_sha256"] for row in rows]
    duplicate_count = len(successor_digests) - len(set(successor_digests))
    if duplicate_count:
        assert duplicate_count == 1
        stable_digest = successor_digests[-1]
        assert successor_digests.count(stable_digest) == 2
        first_stable = rows[successor_digests.index(stable_digest)]
        assert (
            first_stable["phase"],
            first_stable["operation"],
            first_stable["stage"],
            rows[-1]["phase"],
            rows[-1]["operation"],
            rows[-1]["stage"],
        ) == (
            "PUBLICATION_COMMITTED",
            None,
            None,
            "PUBLICATION_COMMITTED",
            None,
            None,
        )


def _durable_rows(
    prepared: SimpleNamespace,
    current: session.LiveStartSession,
) -> dict[str, object]:
    receipts = tuple(
        sorted(
            path.relative_to(prepared.session_root).as_posix()
            for path in (prepared.session_root / "receipts").glob("*.json")
        )
    )
    output_root = prepared.output_child_root
    revisions = (
        tuple(sorted(path.name for path in (output_root / "revisions").glob("sha256-*")))
        if (output_root / "revisions").is_dir()
        else ()
    )
    transactions = (
        tuple(
            sorted(
                path.name
                for path in (output_root / ".publisher" / "transactions").glob(
                    "*.json"
                )
            )
        )
        if (output_root / ".publisher" / "transactions").is_dir()
        else ()
    )
    work = current.prepublication_work_binding
    work_present = (
        Path(str(work["work_root"])).exists()
        if isinstance(work, Mapping)
        else False
    )
    return {
        "receipts": receipts,
        "current_count": int((output_root / "current.json").is_file()),
        "revision_count": len(revisions),
        "transaction_count": len(transactions),
        "operation_final_count": int(output_operation_admission_path().is_file()),
        "operation_staging_count": int(
            output_operation_admission_staging_path().is_file()
        ),
        "operation_inner_temp_count": int(
            output_operation_admission_reserved_temp_path().is_file()
        ),
        "claim_surface_count": len(
            list(prepared.output_base_root.glob("*.claim.json*"))
        ),
        "work_present": work_present,
        "generic_staging_count": len(
            list(prepared.local_app_data.rglob("*.staged"))
        ),
        "generic_inner_temp_count": len(
            list(prepared.local_app_data.rglob("*.live-start-atomic.tmp"))
        ),
    }


def _assert_receipt_bindings_are_physical(
    current: session.LiveStartSession,
    *,
    session_root: Path,
) -> None:
    for logical_path, expected_digest in current.artifact_bindings.items():
        if not logical_path.startswith("receipts/"):
            continue
        raw = (session_root / logical_path).read_bytes()
        assert _sha256(raw) == expected_digest


def _pipeline_hard_kill_worker(
    request_pickle_path: str,
    session_root_text: str,
    fault_value: str,
    fault_occurrence: int,
    fault_log_path: str,
    oracle_path: str,
    cas_trace_path: str,
) -> None:
    request = pickle.loads(Path(request_pickle_path).read_bytes())
    session_root = Path(session_root_text)
    local_app_data = session_root.parents[2]
    os.environ["LOCALAPPDATA"] = str(local_app_data)
    controller = _controller()
    point_type = _faults().LiveStartFaultPoint
    selected = point_type(fault_value)
    selected_occurrences = 0
    durable_cas_count = 0
    real_publish_session_successor = session._publish_session_successor_under_lock

    def traced_publish_session_successor(**kwargs: Any) -> session.LiveStartSession:
        nonlocal durable_cas_count
        predecessor = kwargs["current"]
        successor = real_publish_session_successor(**kwargs)
        durable_cas_count += 1
        _append_durable_jsonl(
            Path(cas_trace_path),
            _cas_trace_row(
                ordinal=durable_cas_count,
                predecessor=predecessor,
                successor=successor,
            ),
        )
        return successor

    session._publish_session_successor_under_lock = traced_publish_session_successor

    def hard_kill(point: Any) -> None:
        nonlocal selected_occurrences
        descriptor = os.open(
            fault_log_path,
            os.O_APPEND | os.O_CREAT | os.O_WRONLY,
            0o600,
        )
        try:
            os.write(descriptor, (point.value + "\n").encode("ascii"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        if point is selected:
            selected_occurrences += 1
            if selected_occurrences == fault_occurrence:
                session_path = session_root / "session.json"
                persisted = session._load_session_bytes(
                    session_path.read_bytes(),
                    session_identity=path_identity(session_path),
                )
                _persist_worker_oracle(
                    Path(oracle_path),
                    _crash_cursor_projection(persisted),
                )
                os._exit(93)

    model = controller.build_frozen_live_configure_run(request=request)
    with session.lease_live_start_session(
        session_root,
        local_app_data_root=local_app_data,
    ) as session_lease:
        current = session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        profile = load_operator_profile()
        with lease_operator_profile(expected_profile=profile) as profile_lease:
            with lease_output_operation_admission() as operation_lease:
                controller._drive_live_start_pipeline(
                    run_model=model,
                    session_lease=session_lease,
                    expected_session=current,
                    runtime_root=profile.runtime_root,
                    profile_lease=profile_lease,
                    operation_lease=operation_lease,
                    fault_hook=hard_kill,
                )


def _pipeline_publication_cas_hard_kill_worker(
    request_pickle_path: str,
    session_root_text: str,
) -> None:
    request = pickle.loads(Path(request_pickle_path).read_bytes())
    session_root = Path(session_root_text)
    local_app_data = session_root.parents[2]
    os.environ["LOCALAPPDATA"] = str(local_app_data)
    controller = _controller()

    def hard_kill_after_publication_cas(
        event: str,
        _payload: dict[str, str] | None = None,
    ) -> None:
        if event == "publication_committed_cas":
            os._exit(94)

    controller._emit_pipeline_event = hard_kill_after_publication_cas
    model = controller.build_frozen_live_configure_run(request=request)
    with session.lease_live_start_session(
        session_root,
        local_app_data_root=local_app_data,
    ) as session_lease:
        current = session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        profile = load_operator_profile()
        with lease_operator_profile(expected_profile=profile) as profile_lease:
            with lease_output_operation_admission() as operation_lease:
                controller._drive_live_start_pipeline(
                    run_model=model,
                    session_lease=session_lease,
                    expected_session=current,
                    runtime_root=profile.runtime_root,
                    profile_lease=profile_lease,
                    operation_lease=operation_lease,
                    fault_hook=_faults().no_live_start_fault,
                )


def _prepare_pipeline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    preview: bool = False,
    existing_child_precondition: bool = False,
) -> SimpleNamespace:
    if existing_child_precondition:
        import tests.test_optimized_start_authority as authority_fixture

        original_derive = authority_fixture.derive_deck_output_binding

        def derive_after_existing_child(profile: Any, deck_name: str) -> Any:
            absent = original_derive(profile, deck_name)
            absent.output_root.mkdir()
            return original_derive(profile, deck_name)

        monkeypatch.setattr(
            authority_fixture,
            "derive_deck_output_binding",
            derive_after_existing_child,
        )
    request = _single_candidate_request(tmp_path / "authority")
    session_root, approved = _force_review_approved_session(
        root=tmp_path,
        request=request,
        preview=preview,
    )
    local_app_data = session_root.parents[2]
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    profile = load_operator_profile()
    return SimpleNamespace(
        request=request,
        run_model=_controller().build_frozen_live_configure_run(request=request),
        session_root=session_root,
        local_app_data=local_app_data,
        approved=approved,
        profile=profile,
        runtime_root=profile.runtime_root,
        output_base_root=profile.output_base_root,
        output_child_root=Path(
            request.frozen_compiler_inputs.manifest.operator_bindings.to_value()[
                "output_base_root"
            ]
        )
        / str(
            request.frozen_compiler_inputs.manifest.operator_bindings.to_value()[
                "deck_output_name"
            ]
        ),
    )


def _drive_pipeline(
    prepared: SimpleNamespace,
    *,
    expected: session.LiveStartSession | None = None,
    fault_hook: Any | None = None,
) -> session.LiveStartSession:
    controller = _controller()
    with session.lease_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    ) as session_lease:
        current = expected or session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        profile = load_operator_profile()
        with lease_operator_profile(expected_profile=profile) as profile_lease:
            with lease_output_operation_admission() as operation_lease:
                return controller._drive_live_start_pipeline(
                    run_model=prepared.run_model,
                    session_lease=session_lease,
                    expected_session=current,
                    runtime_root=prepared.runtime_root,
                    profile_lease=profile_lease,
                    operation_lease=operation_lease,
                    fault_hook=(
                        _faults().no_live_start_fault
                        if fault_hook is None
                        else fault_hook
                    ),
                )


@contextmanager
def _lease_prepublication_capabilities(
    prepared: SimpleNamespace,
) -> Iterator[tuple[Any, Any, Any, Any]]:
    controller = _controller()
    with session.lease_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    ) as session_lease:
        current = session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        with controller._lease_validated_prepublication(
            run_model=prepared.run_model,
            session_lease=session_lease,
            expected_session=current,
            runtime_root=prepared.runtime_root,
            fault_hook=_faults().no_live_start_fault,
        ) as validated:
            profile = load_operator_profile()
            with lease_operator_profile(expected_profile=profile) as profile_lease:
                with lease_output_operation_admission() as operation_lease:
                    yield (
                        validated,
                        session_lease,
                        profile_lease,
                        operation_lease,
                    )


def _join_hard_kill_process(
    process: multiprocessing.Process,
    *,
    expected_exitcode: int,
) -> None:
    timeout_seconds = 120
    cleanup_timeout_seconds = 10
    process.join(timeout_seconds)
    timed_out = process.is_alive()
    if timed_out:
        process.terminate()
        process.join(cleanup_timeout_seconds)
        if process.is_alive():
            process.kill()
            process.join(cleanup_timeout_seconds)
        if process.is_alive():
            pytest.fail("pipeline hard-kill worker could not be stopped")
    exitcode = process.exitcode
    process.close()
    if timed_out:
        pytest.fail(
            "pipeline hard-kill worker did not reach the selected fault "
            f"within {timeout_seconds} seconds"
        )
    assert exitcode == expected_exitcode


def _assert_hard_kill_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault_name: str,
    *,
    expectation: _HardKillExpectation | None = None,
    mutate_after_kill: (
        Callable[
            [SimpleNamespace, session.LiveStartSession],
            tuple[Path, ...],
        ]
        | None
    ) = None,
    resume_error_match: str | None = None,
) -> None:
    if expectation is None:
        expectation = _hard_kill_expectation(fault_name)
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    request_pickle = tmp_path / "request.pickle"
    request_pickle.write_bytes(pickle.dumps(prepared.request))
    fault_log = tmp_path / "faults.log"
    oracle_path = tmp_path / "pre-kill-oracle.json"
    cas_trace_path = tmp_path / "pre-kill-session-cas.jsonl"
    occurrence = expectation.occurrence
    context = multiprocessing.get_context("spawn")
    process = context.Process(
        target=_pipeline_hard_kill_worker,
        args=(
            str(request_pickle),
            str(prepared.session_root),
            getattr(_faults().LiveStartFaultPoint, fault_name).value,
            occurrence,
            str(fault_log),
            str(oracle_path),
            str(cas_trace_path),
        ),
    )
    process.start()
    _join_hard_kill_process(process, expected_exitcode=93)
    assert fault_log.read_text(encoding="ascii").splitlines().count(
        getattr(_faults().LiveStartFaultPoint, fault_name).value
    ) == occurrence

    interrupted = session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    worker_oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
    assert worker_oracle == _crash_cursor_projection(interrupted)
    prekill_cas_rows = _read_jsonl(cas_trace_path)
    _assert_cas_trace_chain(
        prekill_cas_rows,
        predecessor_sha256=prepared.approved.content_sha256,
        successor_sha256=interrupted.content_sha256,
    )
    _assert_receipt_bindings_are_physical(
        interrupted,
        session_root=prepared.session_root,
    )
    cleanup_entry_count = int(
        (
            interrupted.prepublication_work_binding
            or interrupted.pending_transition
        )["cleanup_entry_count"]
    )
    durable_cas_count_at_kill = expectation.durable_cas_count_at_kill
    if durable_cas_count_at_kill < 0:
        durable_cas_count_at_kill = (
            22
            + _PREPUBLICATION_MATERIALIZATION_DURABLE_CAS_DELTA
            + cleanup_entry_count
        )
    cleanup_cursor = expectation.cleanup_cursor
    if cleanup_cursor is not None and cleanup_cursor < 0:
        cleanup_cursor = cleanup_entry_count
    assert len(prekill_cas_rows) == durable_cas_count_at_kill
    assert worker_oracle["phase"] == expectation.phase
    assert worker_oracle["pending_operation"] == expectation.pending_operation
    assert worker_oracle["pending_stage"] == expectation.pending_stage
    assert worker_oracle["external_action_kind"] == expectation.external_action_kind
    assert worker_oracle["external_action_stage"] == expectation.external_action_stage
    assert worker_oracle["external_action_index"] == expectation.external_action_index
    assert worker_oracle["cleanup_cursor"] == cleanup_cursor
    assert tuple(worker_oracle["artifact_receipts"]) == expectation.receipt_paths
    assert _durable_rows(prepared, interrupted) == expectation.durable_rows
    receipt_tree_at_kill = _physical_tree(prepared.session_root / "receipts")
    operation_at_kill = _file_fingerprint(output_operation_admission_path())
    child_identity_at_kill = (
        path_identity(prepared.output_child_root)
        if prepared.output_child_root.is_dir()
        else None
    )
    publication_tree_at_kill = (
        _physical_tree(prepared.output_child_root)
        if (prepared.output_child_root / "current.json").is_file()
        else None
    )
    pending_at_kill = interrupted.pending_transition
    child_binding_at_kill = interrupted.output_child_binding
    claim_path_value = None
    claim_identity_value = None
    claim_sha256_value = None
    for claim_source in (pending_at_kill, child_binding_at_kill):
        if isinstance(claim_source, Mapping) and claim_source.get(
            "output_claim_path",
            claim_source.get("claim_path"),
        ) is not None:
            claim_path_value = claim_source.get(
                "output_claim_path",
                claim_source.get("claim_path"),
            )
            claim_identity_value = claim_source.get(
                "output_claim_identity",
                claim_source.get("claim_identity"),
            )
            claim_sha256_value = claim_source.get(
                "output_claim_sha256",
                claim_source.get("claim_sha256"),
            )
            break
    if claim_identity_value is not None and expectation.durable_rows[
        "claim_surface_count"
    ]:
        claim_fingerprint = _file_fingerprint(Path(str(claim_path_value)))
        assert claim_fingerprint is not None
        assert claim_fingerprint[0] == tuple(claim_identity_value)
        assert claim_fingerprint[2] == claim_sha256_value
    elif claim_identity_value is not None:
        assert _file_fingerprint(Path(str(claim_path_value))) is None
    external_at_kill = (
        pending_at_kill.get("external_file_action")
        if isinstance(pending_at_kill, Mapping)
        else None
    )
    staging_at_kill = None
    if isinstance(external_at_kill, Mapping):
        staging_at_kill = _file_fingerprint(
            Path(str(external_at_kill["staging_path"]))
        )
        if external_at_kill["stage"] == "STAGING_BOUND":
            final_at_kill = _file_fingerprint(
                Path(str(external_at_kill["final_path"]))
            )
            bound_surfaces = tuple(
                surface
                for surface in (staging_at_kill, final_at_kill)
                if surface is not None
            )
            assert bound_surfaces
            assert all(
                surface[0] == tuple(external_at_kill["staging_identity"])
                and surface[1] == external_at_kill["staging_size"]
                and surface[2] == external_at_kill["staging_sha256"]
                for surface in bound_surfaces
            )
    mutation_roots: tuple[Path, ...] = ()
    mutation_snapshots: tuple[
        dict[str, tuple[str, tuple[int, int, int], bytes | None]],
        ...,
    ] = ()
    if mutate_after_kill is not None:
        mutation_roots = mutate_after_kill(prepared, interrupted)
        mutation_snapshots = tuple(_physical_tree(root) for root in mutation_roots)
    interrupted_sha256 = interrupted.content_sha256
    resumed_events: list[tuple[Any, int]] = []
    resumed_cas_rows: list[dict[str, object]] = []
    real_publish_session_successor = session._publish_session_successor_under_lock

    def trace_resumed_session_successor(**kwargs: Any) -> session.LiveStartSession:
        successor = real_publish_session_successor(**kwargs)
        resumed_cas_rows.append(
            _cas_trace_row(
                ordinal=len(resumed_cas_rows) + 1,
                predecessor=kwargs["current"],
                successor=successor,
            )
        )
        return successor

    def observe_resumed_fault(point: Any) -> None:
        resumed_events.append((point, len(resumed_cas_rows)))

    monkeypatch.setattr(
        session,
        "_publish_session_successor_under_lock",
        trace_resumed_session_successor,
    )
    if resume_error_match is not None:
        with pytest.raises(
            (ValueError, session.SessionConflictError),
            match=resume_error_match,
        ):
            _drive_pipeline(
                prepared,
                expected=interrupted,
                fault_hook=observe_resumed_fault,
            )
        assert resumed_events == []
        assert resumed_cas_rows == []
        assert tuple(_physical_tree(root) for root in mutation_roots) == (
            mutation_snapshots
        )
        assert _physical_tree(prepared.session_root / "receipts") == (
            receipt_tree_at_kill
        )
        preserved = session.load_live_start_session(
            prepared.session_root,
            local_app_data_root=prepared.local_app_data,
        )
        assert preserved.content_sha256 == interrupted.content_sha256
        return
    try:
        resumed = _drive_pipeline(
            prepared,
            expected=interrupted,
            fault_hook=observe_resumed_fault,
        )
    except BaseException:
        assert resumed_events
        first_fault, durable_rows = resumed_events[0]
        assert first_fault.value == expectation.first_resumed_fault
        assert durable_rows == expectation.durable_rows_before_first_fault
        raise
    assert resumed_events
    first_fault, durable_rows = resumed_events[0]
    assert first_fault.value == expectation.first_resumed_fault
    assert durable_rows == expectation.durable_rows_before_first_fault
    assert len(resumed_cas_rows) == (
        expectation.remaining_rows_offset
        + expectation.remaining_rows_per_cleanup_entry * cleanup_entry_count
    )
    _assert_cas_trace_chain(
        resumed_cas_rows,
        predecessor_sha256=interrupted.content_sha256,
        successor_sha256=resumed.content_sha256,
    )
    assert resumed.phase is session.LiveStartPhase.PUBLICATION_COMMITTED
    assert resumed.pending_transition is None
    assert resumed.output_child_binding is not None
    assert resumed.output_child_binding["claim_state"] == "RETIRED"
    assert resumed.output_operation_admission_binding is not None
    assert resumed.output_operation_admission_binding["state"] == "ACTIVE"
    assert resumed.content_sha256 != interrupted_sha256
    if interrupted.prepublication_work_binding is None:
        assert resumed.prepublication_work_binding is not None
    else:
        assert (
            resumed.prepublication_work_binding
            == interrupted.prepublication_work_binding
        )
    resumed_receipt_tree = _physical_tree(prepared.session_root / "receipts")
    assert {
        path: resumed_receipt_tree[path] for path in receipt_tree_at_kill
    } == receipt_tree_at_kill
    if operation_at_kill is not None:
        assert _file_fingerprint(output_operation_admission_path()) == (
            operation_at_kill
        )
    if child_identity_at_kill is not None:
        assert path_identity(prepared.output_child_root) == child_identity_at_kill
    if publication_tree_at_kill is not None:
        assert _physical_tree(prepared.output_child_root) == publication_tree_at_kill
    if (
        isinstance(external_at_kill, Mapping)
        and external_at_kill["stage"] == "PLANNED"
        and staging_at_kill is not None
    ):
        assert not Path(str(external_at_kill["staging_path"])).exists()
        final_fingerprint = _file_fingerprint(Path(str(external_at_kill["final_path"])))
        if final_fingerprint is not None:
            assert final_fingerprint[0] != staging_at_kill[0]
    for logical_path, digest in interrupted.artifact_bindings.items():
        if logical_path.startswith("receipts/"):
            assert resumed.artifact_bindings[logical_path] == digest
    _assert_receipt_bindings_are_physical(
        resumed,
        session_root=prepared.session_root,
    )
    assert (prepared.output_child_root / "current.json").is_file()
    assert len(list((prepared.output_child_root / "revisions").glob("sha256-*"))) == 1
    assert not list(prepared.local_app_data.rglob("*.staged"))
    assert not list(prepared.local_app_data.rglob("*.live-start-atomic.tmp"))
    assert not Path(resumed.prepublication_work_binding["work_root"]).exists()
    assert _durable_rows(prepared, resumed) == {
        "receipts": (
            "receipts/candidate_validation.json",
            "receipts/package_validation.json",
            "receipts/prepublication_apply_check.json",
            "receipts/review_validation.json",
        ),
        "current_count": 1,
        "revision_count": 1,
        "transaction_count": 1,
        "operation_final_count": 1,
        "operation_staging_count": 0,
        "operation_inner_temp_count": 0,
        "claim_surface_count": 0,
        "work_present": False,
        "generic_staging_count": 0,
        "generic_inner_temp_count": 0,
    }


def _interrupt_pipeline(
    prepared: SimpleNamespace,
    fault_name: str,
    *,
    occurrence: int = 1,
) -> session.LiveStartSession:
    target = getattr(_faults().LiveStartFaultPoint, fault_name)
    observed = 0

    def stop(point: Any) -> None:
        nonlocal observed
        if point is target:
            observed += 1
        if point is target and observed == occurrence:
            raise RuntimeError("injected:" + target.value)

    with pytest.raises(RuntimeError, match="^injected:"):
        _drive_pipeline(prepared, fault_hook=stop)
    return session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )


def _replace_plain_empty_output_child(
    prepared: SimpleNamespace,
    _interrupted: session.LiveStartSession,
) -> tuple[Path, ...]:
    child = prepared.output_child_root
    original_identity = path_identity(child)
    child.rmdir()
    child.mkdir()
    assert path_identity(child) != original_identity
    return (prepared.output_base_root,)


def _replace_publication_current_same_bytes(
    prepared: SimpleNamespace,
    _interrupted: session.LiveStartSession,
) -> tuple[Path, ...]:
    current = prepared.output_child_root / "current.json"
    raw = current.read_bytes()
    original_identity = path_identity(current)
    current.unlink()
    current.write_bytes(raw)
    assert path_identity(current) != original_identity
    return (prepared.output_base_root,)


def _replace_output_claim_same_bytes(
    prepared: SimpleNamespace,
    _interrupted: session.LiveStartSession,
) -> tuple[Path, ...]:
    claim = _controller().output_child_claim_path(prepared.output_child_root)
    raw = claim.read_bytes()
    original_identity = path_identity(claim)
    claim.unlink()
    claim.write_bytes(raw)
    assert path_identity(claim) != original_identity
    return (prepared.output_base_root,)


def _sha256(raw: bytes) -> str:
    return "sha256:" + sha256(raw).hexdigest()


def _write_bound(path: Path, raw: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return _sha256(raw)


def _force_review_approved_session(
    *,
    root: Path,
    request: Any,
    preview: bool = False,
) -> tuple[Path, session.LiveStartSession]:
    frozen = request.frozen_compiler_inputs
    approval = request.starter_approval
    assert frozen is not None
    assert approval is not None
    operator = frozen.manifest.operator_bindings.to_value()
    compiler = frozen.manifest.compiler_inputs.to_value()
    local_app_data = Path(operator["output_base_root"]).parent / "local-app-data"
    session_root = local_app_data / "HSConfig" / "runs" / ("8" * 32)
    created = session.create_live_start_session(
        session_root=session_root,
        local_app_data_root=local_app_data,
        repository_root=root / "repository",
        runtime_root=Path(operator["runtime_root"]),
        output_base_root=Path(operator["output_base_root"]),
        output_deck_root=(
            Path(operator["output_base_root"])
            / str(operator["deck_output_name"])
        ),
        installed_skill_root=root / "skill",
        deck_name=request.snapshot.general_preconfig.to_value()["deck_identity"][
            "deck_name"
        ],
        deck_code_sha256=str(compiler["deck_code_sha256"]),
        frozen_compiler_inputs=frozen,
        preview_requested=preview,
    )
    context_raw = approval.context.document.canonical_json
    candidate_raw = approval.candidate.document.canonical_json
    review_raw = approval.review.document.canonical_json
    candidate_receipt = session.seal_validation_receipt(
        receipt_kind="candidate_validation",
        unsigned_value={
            "run_id": created.run_id,
            "candidate_revision": approval.candidate.candidate_revision,
            "starter_context_sha256": _sha256(context_raw),
            "candidate_sha256": _sha256(candidate_raw),
            "status": "valid",
            "findings": [],
        },
    )
    review_receipt = session.seal_validation_receipt(
        receipt_kind="review_validation",
        unsigned_value={
            "run_id": created.run_id,
            "candidate_revision": approval.candidate.candidate_revision,
            "starter_context_sha256": _sha256(context_raw),
            "candidate_sha256": _sha256(candidate_raw),
            "review_sha256": _sha256(review_raw),
            "review_status": "approved",
            "confidence": approval.review.confidence,
        },
    )
    candidate_receipt_raw = session._canonical_json(dict(candidate_receipt))
    review_receipt_raw = session._canonical_json(dict(review_receipt))
    bindings = dict(created.artifact_bindings)
    for logical, raw in (
        ("starter/starter_context.json", context_raw),
        ("starter/starter_config_candidate.json", candidate_raw),
        ("receipts/candidate_validation.json", candidate_receipt_raw),
        ("starter/starter_config_review.json", review_raw),
        ("receipts/review_validation.json", review_receipt_raw),
    ):
        bindings[logical] = _write_bound(session_root / logical, raw)
    value = created.to_value()
    value.pop("content_sha256")
    value.update(
        {
            "phase": session.LiveStartPhase.REVIEW_APPROVED.value,
            "candidate_revision": approval.candidate.candidate_revision,
            "artifact_bindings": bindings,
        }
    )
    sealed = session._seal_session_value(value, session_identity=None)
    with session.lease_live_start_session(
        session_root,
        local_app_data_root=local_app_data,
    ) as lease:
        published = atomic_write_reserved_bytes(
            path=session_root / "session.json",
            payload=sealed.canonical_json,
            expected_parent_identity=lease.session_root_identity,
            expected_predecessor_identity=created.session_identity,
            expected_predecessor_sha256=_sha256(created.canonical_json),
            maximum_size=session.LIVE_START_SESSION_MAX_BYTES,
        )
        approved = session._load_session_bytes(
            sealed.canonical_json,
            session_identity=published.identity,
        )
    return session_root, approved


@contextmanager
def _validated_prepublication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    preview: bool = False,
    fault_hook: Any | None = None,
) -> Iterator[tuple[Any, Any, Path, session.LiveStartSession]]:
    request = _single_candidate_request(tmp_path / "authority")
    model = _controller().build_frozen_live_configure_run(request=request)
    session_root, approved = _force_review_approved_session(
        root=tmp_path,
        request=request,
        preview=preview,
    )
    local_app_data = session_root.parents[2]
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    with session.lease_live_start_session(
        session_root,
        local_app_data_root=local_app_data,
    ) as lease:
        factory = (
            _controller().lease_validated_prepublication
            if fault_hook is None
            else _controller()._lease_validated_prepublication
        )
        kwargs = {
            "run_model": model,
            "session_lease": lease,
            "expected_session": approved,
            "runtime_root": Path(
                request.frozen_compiler_inputs.manifest.operator_bindings.to_value()[
                    "runtime_root"
                ]
            ),
        }
        if fault_hook is not None:
            kwargs["fault_hook"] = fault_hook
        with factory(**kwargs) as validated:
            yield request, validated, session_root, approved


def _fault_once(point: Any, events: list[Any]):
    def hook(observed: Any) -> None:
        events.append(observed)
        if observed is point:
            raise RuntimeError(f"fault:{point.value}")

    return hook


def _interrupt_prepublication_materialization(
    prepared: SimpleNamespace,
    *,
    occurrence: int,
) -> tuple[session.LiveStartSession, int]:
    selected = _faults().LiveStartFaultPoint.AFTER_TRANSITION_SECONDARY_ARTIFACT
    observed = 0

    def stop(point: Any) -> None:
        nonlocal observed
        if point is selected:
            observed += 1
            if observed == occurrence:
                raise RuntimeError("injected:" + selected.value)

    controller = _controller()
    with session.lease_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    ) as session_lease:
        current = session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        with pytest.raises(RuntimeError, match="^injected:"):
            with controller._lease_validated_prepublication(
                run_model=prepared.run_model,
                session_lease=session_lease,
                expected_session=current,
                runtime_root=prepared.runtime_root,
                fault_hook=stop,
            ):
                raise AssertionError("materialization fault did not interrupt")
    interrupted = session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    return interrupted, observed


def test_prepublication_materialization_resumes_first_exact_artifact_without_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    interrupted, observed = _interrupt_prepublication_materialization(
        prepared,
        occurrence=1,
    )
    pending = interrupted.pending_transition
    assert isinstance(pending, Mapping)
    assert pending["operation"] == "materialize_prepublication_work"
    assert pending["stage"] == "PRIMARY_APPLIED"
    assert pending["next_action_index"] == 0
    actions = pending["actions"]
    assert isinstance(actions, tuple)
    assert len(actions) == len(
        _controller().render_configure_run_model(prepared.run_model).artifacts
    )
    first_path = Path(str(pending["work_root"])) / str(
        actions[0]["relative_path"]
    )
    first_before = _file_fingerprint(first_path)
    assert first_before is not None
    assert observed == 1

    controller = _controller()
    with session.lease_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    ) as session_lease:
        current = session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        assert current.content_sha256 == interrupted.content_sha256
        with controller._lease_validated_prepublication(
            run_model=prepared.run_model,
            session_lease=session_lease,
            expected_session=current,
            runtime_root=prepared.runtime_root,
            fault_hook=_faults().no_live_start_fault,
        ) as validated:
            assert validated.updated_session.phase is (
                session.LiveStartPhase.PREPUBLICATION_CHECK_PASSED
            )
            assert validated.updated_session.pending_transition is None
            assert validated.updated_session.prepublication_work_binding is not None
    assert _file_fingerprint(first_path) == first_before


def test_prepublication_empty_created_root_is_bound_once_then_resumed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    selected = _faults().LiveStartFaultPoint.AFTER_TRANSITION_PRIMARY_ARTIFACT

    def stop_after_root_create(point: Any) -> None:
        if point is selected:
            raise RuntimeError("injected:" + selected.value)

    controller = _controller()
    with session.lease_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    ) as session_lease:
        current = session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        with pytest.raises(RuntimeError, match="^injected:"):
            with controller._lease_validated_prepublication(
                run_model=prepared.run_model,
                session_lease=session_lease,
                expected_session=current,
                runtime_root=prepared.runtime_root,
                fault_hook=stop_after_root_create,
            ):
                raise AssertionError("root-create fault did not interrupt")

    interrupted = session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    pending = interrupted.pending_transition
    assert isinstance(pending, Mapping)
    assert pending["operation"] == "materialize_prepublication_work"
    assert pending["stage"] == "PREPARED"
    assert pending["next_action_index"] == 0
    assert pending["work_root_identity"] is None
    work_root = Path(str(pending["work_root"]))
    created_identity = path_identity(work_root)
    assert work_root.is_dir()
    assert not any(work_root.iterdir())
    root_binding_cas = 0
    real_transition = session._transition_receipt_authorized_under_lock

    def count_root_binding(*args: Any, **kwargs: Any) -> session.LiveStartSession:
        nonlocal root_binding_cas
        predecessor = kwargs.get("expected_session")
        changes = kwargs.get("changes")
        prior = (
            predecessor.pending_transition
            if isinstance(predecessor, session.LiveStartSession)
            else None
        )
        successor = (
            changes.get("pending_transition")
            if isinstance(changes, Mapping)
            else None
        )
        if (
            isinstance(prior, Mapping)
            and prior.get("operation") == "materialize_prepublication_work"
            and prior.get("stage") == "PREPARED"
            and isinstance(successor, Mapping)
            and successor.get("stage") == "PRIMARY_APPLIED"
        ):
            root_binding_cas += 1
            assert tuple(successor["work_root_identity"]) == created_identity
        return real_transition(*args, **kwargs)

    monkeypatch.setattr(
        session,
        "_transition_receipt_authorized_under_lock",
        count_root_binding,
    )
    with session.lease_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    ) as session_lease:
        current = session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        with controller._lease_validated_prepublication(
            run_model=prepared.run_model,
            session_lease=session_lease,
            expected_session=current,
            runtime_root=prepared.runtime_root,
            fault_hook=_faults().no_live_start_fault,
        ) as validated:
            assert validated.work_root_identity == created_identity
            assert tuple(
                validated.updated_session.prepublication_work_binding[
                    "work_root_identity"
                ]
            ) == created_identity
    assert root_binding_cas == 1


def test_prepublication_materialization_rejects_fully_written_root_swap_before_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    rendered = _controller().render_configure_run_model(prepared.run_model)
    interrupted, observed = _interrupt_prepublication_materialization(
        prepared,
        occurrence=len(rendered.artifacts),
    )
    pending = interrupted.pending_transition
    assert isinstance(pending, Mapping)
    assert pending["operation"] == "materialize_prepublication_work"
    assert pending["next_action_index"] == len(rendered.artifacts) - 1
    work_root = Path(str(pending["work_root"]))
    expected_identity = tuple(pending["work_root_identity"])
    assert path_identity(work_root) == expected_identity
    assert _tree_bytes(work_root) == {
        artifact.relative_path: artifact.content for artifact in rendered.artifacts
    }
    assert observed == len(rendered.artifacts)

    retired = work_root.with_name(work_root.name + ".retired")
    work_root.rename(retired)
    write_rendered_configure_run(rendered, work_root)
    assert path_identity(retired) == expected_identity
    assert path_identity(work_root) != expected_identity
    assert _tree_bytes(work_root) == _tree_bytes(retired)
    receipt_tree = _physical_tree(prepared.session_root / "receipts")
    output_tree = _physical_tree(prepared.output_base_root)

    with session.lease_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    ) as session_lease:
        current = session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        with pytest.raises(
            ValueError,
            match="^live_start_prepublication_work_identity_changed$",
        ):
            with _controller()._lease_validated_prepublication(
                run_model=prepared.run_model,
                session_lease=session_lease,
                expected_session=current,
                runtime_root=prepared.runtime_root,
                fault_hook=_faults().no_live_start_fault,
            ):
                raise AssertionError("swapped work root reached validation")
    assert _physical_tree(prepared.session_root / "receipts") == receipt_tree
    assert _physical_tree(prepared.output_base_root) == output_tree


def test_fake_apply_plans_exact_temporary_package_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _controller()
    _assert_live_start_fault_contract_and_public_default(controller, monkeypatch)
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    _poison_frozen_authority_reloads(monkeypatch)
    prepared.run_model = controller.build_frozen_live_configure_run(
        request=prepared.request
    )
    _assert_exact_frozen_stage_authority(
        prepared.run_model,
        prepared.request,
    )
    events: list[tuple[str, dict[str, str] | None]] = []
    monkeypatch.setattr(controller, "_emit_pipeline_event", _event_recorder(events))
    real_plan = controller.plan_apply_package

    def observed_plan(*args: Any, **kwargs: Any) -> Any:
        package_root = Path(kwargs.get("package_root", args[0] if args else ""))
        assert package_root.parts[-1] == "04_package"
        assert "work" in package_root.parts
        assert not list(prepared.output_base_root.rglob("current.json"))
        return real_plan(*args, **kwargs)

    monkeypatch.setattr(controller, "plan_apply_package", observed_plan)
    completed = _drive_pipeline(prepared)
    assert completed.phase is session.LiveStartPhase.PUBLICATION_COMMITTED
    assert (prepared.output_child_root / "current.json").is_file()
    assert events == _expected_committed_event_records("created")


def test_prepublication_receipt_is_external_diagnostic_only_and_path_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _validated_prepublication(tmp_path, monkeypatch) as (
        request,
        validated,
        session_root,
        _approved,
    ):
        receipt = validated.diagnostic_receipt.to_value()
        bound_date = request.frozen_compiler_inputs.manifest.compiler_inputs.to_value()[
            "bound_date"
        ]
        diagnostic_path = session_root / "receipts/prepublication_apply_check.json"
        package_snapshot = _physical_tree(validated.package_root)
        assert receipt["diagnostic_only"] is True
        assert receipt["created_at_utc"] == f"{bound_date}T00:00:00+00:00"
        assert receipt["package_root"] == str(validated.package_root.resolve())
        assert receipt["package_root_sha256"] == validated.package_validation_receipt.to_value()[
            "package_root_sha256"
        ]
        assert diagnostic_path.is_file()
        assert diagnostic_path.read_bytes() == validated.diagnostic_receipt.canonical_json
        assert validated.package_root not in diagnostic_path.parents
        assert validated.updated_session.artifact_bindings[
            "receipts/prepublication_apply_check.json"
        ] == "sha256:" + sha256(validated.diagnostic_receipt.canonical_json).hexdigest()
        assert not any(
            relative.endswith("prepublication_apply_check.json")
            or row[2] == validated.diagnostic_receipt.canonical_json
            for relative, row in package_snapshot.items()
        )


def test_fault_through_fake_apply_preserves_current_pointer_and_runtime_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _controller()
    request = _single_candidate_request(tmp_path / "authority")
    runtime = Path(
        request.frozen_compiler_inputs.manifest.operator_bindings.to_value()[
            "runtime_root"
        ]
    )
    output = Path(
        request.frozen_compiler_inputs.manifest.operator_bindings.to_value()[
            "output_base_root"
        ]
    )
    before_runtime = _physical_tree(runtime)
    before_output = _physical_tree(output)
    model = controller.build_frozen_live_configure_run(request=request)
    session_root, approved = _force_review_approved_session(root=tmp_path, request=request)
    monkeypatch.setenv("LOCALAPPDATA", str(session_root.parents[2]))

    def fail_plan(**_kwargs: Any) -> Any:
        raise RuntimeError("planned-failure")

    monkeypatch.setattr(controller, "plan_apply_package", fail_plan)
    with session.lease_live_start_session(
        session_root,
        local_app_data_root=session_root.parents[2],
    ) as lease:
        with pytest.raises(RuntimeError, match="planned-failure"):
            with controller.lease_validated_prepublication(
                run_model=model,
                session_lease=lease,
                expected_session=approved,
                runtime_root=runtime,
            ):
                raise AssertionError("prepublication yielded after failed plan")
    assert _physical_tree(runtime) == before_runtime
    assert _physical_tree(output) == before_output


def test_profile_or_output_precondition_drift_blocks_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for dimension in (
        "profile_bytes",
        "profile_identity",
        "profile_digest",
        "output_identity",
    ):
        prepared = _prepare_pipeline(tmp_path / dimension, monkeypatch)
        with _lease_prepublication_capabilities(prepared) as capabilities:
            validated, session_lease, profile_lease, operation_lease = capabilities
            profile_path = operator_profile_path()
            profile_raw = profile_path.read_bytes()
            original_profile_identity = path_identity(profile_path)
            replacement: Path | None = None
            original_profile: Path | None = None
            if dimension == "profile_bytes":
                profile_path.write_bytes(profile_raw + b" ")
                assert path_identity(profile_path) == original_profile_identity
            elif dimension == "profile_identity":
                original_profile = profile_path.with_name("operator-profile.original")
                profile_path.rename(original_profile)
                profile_path.write_bytes(profile_raw)
                assert path_identity(profile_path) != original_profile_identity
            elif dimension == "profile_digest":
                profile_value = json.loads(profile_raw)
                profile_value.pop("content_sha256")
                profile_value["live_by_default"] = not profile_value[
                    "live_by_default"
                ]
                unsigned = json.dumps(
                    profile_value,
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
                profile_value["content_sha256"] = (
                    "sha256:" + sha256(unsigned).hexdigest()
                )
                changed_profile = json.dumps(
                    profile_value,
                    allow_nan=False,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
                profile_path.write_bytes(changed_profile)
                assert path_identity(profile_path) == original_profile_identity
                assert changed_profile != profile_raw
                assert json.loads(changed_profile)["content_sha256"] != (
                    prepared.profile.content_sha256
                )
            else:
                replacement = prepared.output_base_root.with_name(
                    "outputs-original"
                )
                prepared.output_base_root.rename(replacement)
                prepared.output_base_root.mkdir()
                assert path_identity(prepared.output_base_root) != (
                    prepared.profile.output_base_root_identity
                )

            session_before = _physical_tree(prepared.session_root)
            work_before = _physical_tree(validated.work_root)
            runtime_before = _physical_tree(prepared.runtime_root)
            visible_output_before = _physical_tree(prepared.output_base_root)
            profile_before = _file_fingerprint(profile_path)
            original_profile_before = (
                _file_fingerprint(original_profile)
                if original_profile is not None
                else None
            )
            operation_surfaces = (
                output_operation_admission_path(),
                output_operation_admission_staging_path(),
                output_operation_admission_reserved_temp_path(),
            )
            operation_before = tuple(
                _file_fingerprint(path) for path in operation_surfaces
            )
            replacement_before = (
                _physical_tree(replacement)
                if replacement is not None
                else None
            )
            with pytest.raises(
                (ValueError, session.SessionCapabilityError),
                match="profile|output|identity|digest|bytes|canonical",
            ):
                _controller().publish_validated_prepublication(
                    validated=validated,
                    session_lease=session_lease,
                    expected_session=validated.updated_session,
                    profile_lease=profile_lease,
                    operation_lease=operation_lease,
                )
            assert _physical_tree(prepared.session_root) == session_before
            assert _physical_tree(validated.work_root) == work_before
            assert _physical_tree(prepared.runtime_root) == runtime_before
            assert _physical_tree(prepared.output_base_root) == visible_output_before
            assert _file_fingerprint(profile_path) == profile_before
            if original_profile is not None:
                assert _file_fingerprint(original_profile) == original_profile_before
            assert tuple(
                _file_fingerprint(path) for path in operation_surfaces
            ) == operation_before
            if replacement is not None:
                assert _physical_tree(replacement) == replacement_before


def test_preview_publishes_but_creates_no_runtime_lock_journal_state_or_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch, preview=True)
    before_runtime = _physical_tree(prepared.runtime_root)
    completed = _drive_pipeline(prepared)
    assert completed.phase is session.LiveStartPhase.PUBLICATION_COMMITTED
    current = prepared.output_child_root / "current.json"
    assert current.is_file()
    assert len(list((prepared.output_child_root / "revisions").glob("sha256-*"))) == 1
    assert _physical_tree(prepared.runtime_root) == before_runtime
    forbidden_names = {
        ".hsconfig",
        "apply.lock",
        "apply-journal.json",
        "runtime-state.json",
        "apply-receipt.json",
        "deck_config.ini",
    }
    assert not any(
        path.name in forbidden_names
        for path in prepared.runtime_root.rglob("*")
    )


def test_receipt_install_rejects_replaced_persisted_parent_before_foreign_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    receipts = prepared.session_root / "receipts"
    original_receipts = receipts.with_name("receipts-original")
    original_tree = _physical_tree(receipts)
    pending_cas_count = 0

    def replace_receipts_after_package_prepare(point: Any) -> None:
        nonlocal pending_cas_count
        if point is not _faults().LiveStartFaultPoint.AFTER_PENDING_TRANSITION_CAS:
            return
        pending_cas_count += 1
        if pending_cas_count != 2:
            return
        receipts.rename(original_receipts)
        receipts.mkdir()
        assert _physical_tree(receipts) == {
            ".": ("directory", path_identity(receipts), None)
        }

    controller = _controller()
    with session.lease_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    ) as session_lease:
        current = session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        with pytest.raises(
            session.SessionCapabilityError,
            match="^live_start_receipt_parent_binding_changed$",
        ):
            with controller._lease_validated_prepublication(
                run_model=prepared.run_model,
                session_lease=session_lease,
                expected_session=current,
                runtime_root=prepared.runtime_root,
                fault_hook=replace_receipts_after_package_prepare,
            ):
                raise AssertionError("replaced receipt parent accepted")

    assert pending_cas_count == 2
    assert _physical_tree(original_receipts) == original_tree
    assert _physical_tree(receipts) == {
        ".": ("directory", path_identity(receipts), None)
    }


def test_validation_receipts_are_durable_before_package_and_prepublication_phase_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ) -> None:
    faults = _faults().LiveStartFaultPoint
    target_faults = {
        faults.AFTER_PENDING_TRANSITION_CAS,
        faults.AFTER_TRANSITION_PRIMARY_ARTIFACT,
        faults.BEFORE_TRANSITION_PHASE_CAS,
    }
    records: list[
        tuple[str, str, str, str, bytes | None, bytes | None]
    ] = []

    def observe(point: Any) -> None:
        if point not in target_faults:
            return
        session_paths = tuple(tmp_path.rglob("session.json"))
        assert len(session_paths) == 1
        session_path = session_paths[0]
        persisted = session._load_session_bytes(
            session_path.read_bytes(),
            session_identity=path_identity(session_path),
        )
        pending = persisted.pending_transition
        if not isinstance(pending, Mapping) or pending.get("operation") not in {
            "install_package_validation",
            "install_prepublication_validation",
        }:
            return
        package_path = session_path.parent / "receipts/package_validation.json"
        prepublication_path = (
            session_path.parent / "receipts/prepublication_apply_check.json"
        )
        records.append(
            (
                point.value,
                persisted.phase.value,
                str(pending["operation"]),
                str(pending["stage"]),
                package_path.read_bytes() if package_path.is_file() else None,
                (
                    prepublication_path.read_bytes()
                    if prepublication_path.is_file()
                    else None
                ),
            )
        )

    with _validated_prepublication(
        tmp_path,
        monkeypatch,
        fault_hook=observe,
    ) as (_request, validated, session_root, _approved):
        package_path = session_root / "receipts/package_validation.json"
        prepublication_path = session_root / "receipts/prepublication_apply_check.json"
        assert package_path.read_bytes() == validated.package_validation_receipt.canonical_json
        assert prepublication_path.read_bytes() == validated.diagnostic_receipt.canonical_json
        package_raw = validated.package_validation_receipt.canonical_json
        prepublication_raw = validated.diagnostic_receipt.canonical_json
        assert records == [
            (
                "after_pending_transition_cas",
                "REVIEW_APPROVED",
                "install_package_validation",
                "PREPARED",
                None,
                None,
            ),
            (
                "after_transition_primary_artifact",
                "REVIEW_APPROVED",
                "install_package_validation",
                "PREPARED",
                package_raw,
                None,
            ),
            (
                "before_transition_phase_cas",
                "REVIEW_APPROVED",
                "install_package_validation",
                "PRIMARY_APPLIED",
                package_raw,
                None,
            ),
            (
                "after_pending_transition_cas",
                "PACKAGE_VALIDATED",
                "install_prepublication_validation",
                "PREPARED",
                package_raw,
                None,
            ),
            (
                "after_transition_primary_artifact",
                "PACKAGE_VALIDATED",
                "install_prepublication_validation",
                "PREPARED",
                package_raw,
                prepublication_raw,
            ),
            (
                "before_transition_phase_cas",
                "PACKAGE_VALIDATED",
                "install_prepublication_validation",
                "PRIMARY_APPLIED",
                package_raw,
                prepublication_raw,
            ),
        ]


def test_tampered_review_package_or_prepublication_receipt_stops_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for index, logical_path in enumerate(
        (
            "starter/starter_config_review.json",
            "receipts/package_validation.json",
            "receipts/prepublication_apply_check.json",
        )
    ):
        case_root = tmp_path / str(index)
        prepared = _prepare_pipeline(case_root, monkeypatch)
        interrupted = _interrupt_pipeline(prepared, "AFTER_PREPUBLICATION_CAS")
        target = prepared.session_root / logical_path
        target.write_bytes(target.read_bytes() + b" ")
        before_output = _physical_tree(prepared.output_base_root)
        with pytest.raises(
            (session.SessionConflictError, session.SessionValidationError, ValueError),
            match="artifact|receipt|review|canonical|digest",
        ):
            _drive_pipeline(prepared, expected=interrupted)
        assert _physical_tree(prepared.output_base_root) == before_output


def test_deck_output_identity_is_held_through_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    observed: list[tuple[int, int, int]] = []
    context = multiprocessing.get_context("spawn")
    attempted = context.Event()
    acquired = context.Event()
    release = context.Event()
    contender: multiprocessing.Process | None = None

    def observe(event: str, _payload: object | None = None) -> None:
        nonlocal contender
        if event in {"published", "publication_committed_cas"}:
            observed.append(path_identity(prepared.output_child_root))
        if event == "published":
            contender = context.Process(
                target=_publisher_lock_contender,
                args=(
                    str(prepared.output_child_root / ".publish.lock"),
                    attempted,
                    acquired,
                    release,
                ),
            )
            contender.start()
            assert attempted.wait(10)
        elif event == "publication_committed_cas":
            assert contender is not None
            assert not acquired.wait(0.5)

    monkeypatch.setattr(_controller(), "_emit_pipeline_event", observe)
    try:
        completed = _drive_pipeline(prepared)
        assert acquired.wait(10)
    finally:
        release.set()
        if contender is not None:
            contender.join(10)
            if contender.is_alive():
                contender.terminate()
                contender.join(10)
    assert contender is not None
    assert contender.exitcode == 0
    assert len(observed) == 2
    assert observed[0] == observed[1] == tuple(
        completed.publication_binding["output_child_identity"]
    )


def test_prepublication_work_tree_is_retained_for_resume_then_identity_cleaned_before_apply_or_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    with _lease_prepublication_capabilities(prepared) as (validated, *_):
        work_identity = path_identity(validated.work_root)
        assert work_identity == validated.work_root_identity
        assert validated.updated_session.prepublication_work_binding["work_root_identity"] == work_identity
    assert path_identity(validated.work_root) == work_identity
    completed = _drive_pipeline(prepared, expected=validated.updated_session)
    assert completed.prepublication_work_binding is not None
    assert completed.prepublication_work_binding["work_root_identity"] == work_identity
    assert not validated.work_root.exists()
    assert completed.pending_transition is None


def test_crash_after_prepublication_cas_resumes_same_tree_and_receipt_without_rebuild(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_hard_kill_resume(
        tmp_path,
        monkeypatch,
        "AFTER_PREPUBLICATION_CAS",
    )


def test_publication_requires_active_profile_and_output_capabilities(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    with _lease_prepublication_capabilities(prepared) as capabilities:
        validated, session_lease, profile_lease, operation_lease = capabilities
        before = _physical_tree(prepared.output_base_root)
        for wrong_field in ("session_lease", "profile_lease", "operation_lease"):
            kwargs = {
                "validated": validated,
                "session_lease": session_lease,
                "expected_session": validated.updated_session,
                "profile_lease": profile_lease,
                "operation_lease": operation_lease,
            }
            kwargs[wrong_field] = object()
            with pytest.raises(
                session.SessionCapabilityError,
                match="publication_capability_invalid",
            ):
                _controller().publish_validated_prepublication(**kwargs)
            assert _physical_tree(prepared.output_base_root) == before


def test_publication_rejects_mixed_validated_prepublication_before_any_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared_a = _prepare_pipeline(tmp_path / "a", monkeypatch)
    prepared_b = _prepare_pipeline(tmp_path / "b", monkeypatch)
    monkeypatch.setenv("LOCALAPPDATA", str(prepared_a.local_app_data))
    controller = _controller()
    rendered_b = controller.render_configure_run_model(prepared_b.run_model)

    with _lease_prepublication_capabilities(prepared_a) as capabilities:
        validated_a, session_lease, profile_lease, operation_lease = capabilities
        forged = controller.ValidatedPrepublication(
            rendered=rendered_b,
            work_root=validated_a.work_root,
            work_root_identity=validated_a.work_root_identity,
            package_root=validated_a.package_root,
            package_validation_receipt=(
                validated_a.package_validation_receipt
            ),
            diagnostic_receipt=validated_a.diagnostic_receipt,
            updated_session=validated_a.updated_session,
        )
        session_before = _physical_tree(prepared_a.session_root)
        output_before = _physical_tree(prepared_a.output_base_root)

        with pytest.raises(
            session.SessionCapabilityError,
            match="^live_start_validated_prepublication_binding_mismatch$",
        ):
            controller.publish_validated_prepublication(
                validated=forged,
                session_lease=session_lease,
                expected_session=validated_a.updated_session,
                profile_lease=profile_lease,
                operation_lease=operation_lease,
            )

        assert _physical_tree(prepared_a.session_root) == session_before
        assert _physical_tree(prepared_a.output_base_root) == output_before


def test_profile_disable_waits_through_publication_committed_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    profile = load_operator_profile()
    entered = Event()
    acquired = Event()
    publication_cas_seen = Event()
    thread: Thread | None = None

    def contender() -> None:
        entered.set()
        with lease_operator_profile(expected_profile=profile):
            acquired.set()

    def observe(event: str, _payload: object | None = None) -> None:
        nonlocal thread
        if event == "published":
            thread = Thread(target=contender)
            thread.start()
            assert entered.wait(5)
            assert not acquired.wait(0.1)
        elif event == "publication_committed_cas":
            assert not acquired.is_set()
            publication_cas_seen.set()

    monkeypatch.setattr(_controller(), "_emit_pipeline_event", observe)
    completed = _drive_pipeline(prepared)
    assert completed.phase is session.LiveStartPhase.PUBLICATION_COMMITTED
    assert publication_cas_seen.is_set()
    assert thread is not None
    thread.join(5)
    assert acquired.is_set()


def test_output_child_bootstrap_prepared_cas_precedes_absent_child_create(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_hard_kill_resume(
        tmp_path,
        monkeypatch,
        "AFTER_OUTPUT_CHILD_BOOTSTRAP_PREPARED",
    )


def test_output_child_bootstrap_crash_before_identity_cas_never_adopts_or_deletes_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_hard_kill_resume(
        tmp_path,
        monkeypatch,
        "AFTER_OUTPUT_CHILD_CREATE_BEFORE_CAS",
        mutate_after_kill=_replace_plain_empty_output_child,
        resume_error_match="^live_start_output_child_create_postcondition_changed$",
    )


def test_output_child_bootstrap_bound_identity_resumes_and_rejects_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_hard_kill_resume(
        tmp_path,
        monkeypatch,
        "AFTER_OUTPUT_CHILD_BOUND",
        mutate_after_kill=_replace_plain_empty_output_child,
        resume_error_match="^live_start_output_child_identity_changed$",
    )


def test_publisher_commit_before_publication_cas_reconciles_only_bound_output_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_hard_kill_resume(
        tmp_path,
        monkeypatch,
        "AFTER_PUBLICATION_COMMIT_BEFORE_OUTPUT_CHILD_CLAIM_RETIREMENT",
        mutate_after_kill=_replace_publication_current_same_bytes,
        resume_error_match="^live_start_publication_current_identity_changed$",
    )


def test_publication_committed_resume_finalizes_owner_before_claim_retirement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    request_pickle = tmp_path / "request.pickle"
    request_pickle.write_bytes(pickle.dumps(prepared.request))
    process = multiprocessing.get_context("spawn").Process(
        target=_pipeline_publication_cas_hard_kill_worker,
        args=(str(request_pickle), str(prepared.session_root)),
    )
    process.start()
    _join_hard_kill_process(process, expected_exitcode=94)
    interrupted = session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert interrupted.phase is session.LiveStartPhase.PUBLICATION_COMMITTED

    def owner_phase() -> str:
        publisher = importlib.import_module("hsconfig.output_publisher")
        owners = [
            transaction
            for _path, transaction in publisher._load_valid_transactions(
                prepared.output_child_root
            )
            if transaction.owns_revision
            and transaction.live_start_commit_receipt is not None
        ]
        assert len(owners) == 1
        return str(owners[0].phase)

    assert owner_phase() == "pointer_committed"
    observed_before_retirement: list[str] = []

    def observe(point: Any) -> None:
        if point is _faults().LiveStartFaultPoint.AFTER_OUTPUT_CHILD_CLAIM_RETIREMENT_PREPARED:
            observed_before_retirement.append(owner_phase())

    _drive_pipeline(
        prepared,
        expected=interrupted,
        fault_hook=observe,
    )
    assert observed_before_retirement == ["finalized"]
    assert owner_phase() == "finalized"


def test_publication_committed_resume_acquires_bootstrap_before_base_and_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    request_pickle = tmp_path / "request.pickle"
    request_pickle.write_bytes(pickle.dumps(prepared.request))
    process = multiprocessing.get_context("spawn").Process(
        target=_pipeline_publication_cas_hard_kill_worker,
        args=(str(request_pickle), str(prepared.session_root)),
    )
    process.start()
    _join_hard_kill_process(process, expected_exitcode=94)
    interrupted = session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert interrupted.phase is session.LiveStartPhase.PUBLICATION_COMMITTED

    controller = _controller()
    real_bootstrap = controller._publisher.lease_output_child_bootstrap
    real_hold = controller.hold_plain_directory
    entries: list[str] = []

    @contextmanager
    def trace_bootstrap(*, output_root: Path) -> Iterator[Any]:
        entries.append("bootstrap")
        with real_bootstrap(output_root=output_root) as lease:
            yield lease

    @contextmanager
    def trace_hold(path: Path, **kwargs: Any) -> Iterator[Any]:
        resolved = Path(path)
        if resolved == prepared.output_base_root:
            entries.append("base")
        elif resolved == prepared.output_child_root:
            entries.append("child")
        with real_hold(path, **kwargs) as guard:
            yield guard

    monkeypatch.setattr(
        controller._publisher,
        "lease_output_child_bootstrap",
        trace_bootstrap,
    )
    monkeypatch.setattr(controller, "hold_plain_directory", trace_hold)
    _drive_pipeline(prepared, expected=interrupted)
    assert entries[:3] == ["bootstrap", "base", "child"]


def test_absent_output_child_claim_is_durable_before_create(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_hard_kill_resume(tmp_path, monkeypatch, "AFTER_OUTPUT_CHILD_CLAIM_BOUND")


def test_existing_output_child_binds_without_create(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(
        tmp_path,
        monkeypatch,
        existing_child_precondition=True,
    )
    expected_identity = path_identity(prepared.output_child_root)
    events: list[tuple[str, dict[str, str] | None]] = []
    monkeypatch.setattr(
        _controller(),
        "_emit_pipeline_event",
        _event_recorder(events),
    )
    completed = _drive_pipeline(prepared)
    assert completed.output_child_binding["predecessor_state"] == "existing"
    assert completed.output_child_binding["output_child_identity"] == expected_identity
    assert path_identity(prepared.output_child_root) == expected_identity
    assert events == _expected_committed_event_records("confirmed")


def test_claimless_empty_output_child_is_never_adopted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    prepared.output_child_root.mkdir()
    before = _physical_tree(prepared.output_child_root)
    with pytest.raises(ValueError, match="precondition|claim|child"):
        _drive_pipeline(prepared)
    assert _physical_tree(prepared.output_child_root) == before


def test_output_child_create_before_cas_resumes_only_under_exact_active_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_hard_kill_resume(
        tmp_path,
        monkeypatch,
        "AFTER_OUTPUT_CHILD_CREATE_BEFORE_CAS",
    )


def test_output_child_claim_remains_exact_until_publication_committed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_hard_kill_resume(
        tmp_path,
        monkeypatch,
        "AFTER_PUBLICATION_COMMIT_BEFORE_OUTPUT_CHILD_CLAIM_RETIREMENT",
        mutate_after_kill=_replace_output_claim_same_bytes,
        resume_error_match="^live_start_output_claim_identity_changed$",
    )


def test_output_child_claim_retirement_is_intent_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_hard_kill_resume(
        tmp_path,
        monkeypatch,
        "AFTER_OUTPUT_CHILD_CLAIM_RETIREMENT_PREPARED",
    )


def test_output_child_claim_unlink_before_cas_resumes_from_exact_absence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_hard_kill_resume(
        tmp_path,
        monkeypatch,
        "AFTER_OUTPUT_CHILD_CLAIM_UNLINK_BEFORE_CAS",
    )


def test_claim_retirement_confirmation_stops_after_foreign_current_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    target = _faults().LiveStartFaultPoint.AFTER_OUTPUT_CHILD_CLAIM_UNLINK_CAS

    def stop(point: Any) -> None:
        if point is target:
            raise RuntimeError("claim-unlinked")

    with pytest.raises(RuntimeError, match="claim-unlinked"):
        _drive_pipeline(prepared, fault_hook=stop)
    current = prepared.output_child_root / "current.json"
    current.write_bytes(current.read_bytes() + b" ")
    interrupted = session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    with pytest.raises(ValueError, match="current|publication|canonical"):
        _drive_pipeline(prepared, expected=interrupted)


def test_claim_retired_cas_atomically_rebinds_publication_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_hard_kill_resume(
        tmp_path,
        monkeypatch,
        "AFTER_OUTPUT_CHILD_CLAIM_CONFIRMATION_BEFORE_RETIRED_CAS",
    )


def test_output_child_claim_is_never_recreated_after_retired(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    target = _faults().LiveStartFaultPoint.AFTER_OUTPUT_CHILD_CLAIM_RETIRED

    def stop(point: Any) -> None:
        if point is target:
            raise RuntimeError("claim-retired")

    with pytest.raises(RuntimeError, match="claim-retired"):
        _drive_pipeline(prepared, fault_hook=stop)
    claim = _controller().output_child_claim_path(prepared.output_child_root)
    assert not claim.exists()
    interrupted = session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    _drive_pipeline(prepared, expected=interrupted)
    assert not claim.exists()


def test_output_operation_admission_precedes_per_child_claim_and_survives_claim_retirement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    events: list[tuple[str, dict[str, str] | None]] = []
    monkeypatch.setattr(
        _controller(),
        "_emit_pipeline_event",
        _event_recorder(events),
    )
    completed = _drive_pipeline(prepared)
    assert events == _expected_committed_event_records("created")
    assert completed.output_operation_admission_binding["state"] == "ACTIVE"
    admission = Path(completed.output_operation_admission_binding["admission_path"])
    assert admission.is_file()


def test_output_operation_admission_unlink_requires_persisted_release_authorized_cursor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    completed = _drive_pipeline(prepared)
    with session.lease_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    ) as session_lease:
        with pytest.raises(session.SessionConflictError, match="release"):
            session._authorize_output_operation_admission_release_under_lock(
                session_lease=session_lease,
                expected_release_authorized_session=completed,
            )


def test_output_operation_terminal_release_adapter_requires_exact_terminal_no_runtime_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    completed = _drive_pipeline(prepared)
    with session.lease_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    ) as session_lease:
        profile = load_operator_profile()
        with lease_operator_profile(expected_profile=profile) as profile_lease:
            with lease_output_operation_admission() as operation_lease:
                with pytest.raises(
                    (ValueError, session.SessionConflictError),
                    match="terminal|release",
                ):
                    _controller().authorize_output_operation_terminal_release_from_context(
                        operation_lease=operation_lease,
                        session_lease=session_lease,
                        expected_terminal_session=completed,
                        profile_lease=profile_lease,
                        expected=_controller().load_bound_output_operation_admission(
                            completed
                        ),
                    )


def test_output_operation_admission_crashes_resume_without_profile_or_publisher_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_hard_kill_resume(
        tmp_path,
        monkeypatch,
        "AFTER_OUTPUT_OPERATION_ADMISSION_BOUND",
    )


def test_output_operation_staging_flush_crash_retires_then_retries_without_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_hard_kill_resume(
        tmp_path,
        monkeypatch,
        "AFTER_OUTPUT_OPERATION_ADMISSION_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS",
    )


def test_output_claim_binds_exact_final_staging_and_inner_temp_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    interrupted = _interrupt_pipeline(
        prepared,
        "AFTER_OUTPUT_CHILD_CLAIM_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS",
    )
    pending = interrupted.pending_transition
    external = pending["external_file_action"]
    final = Path(external["final_path"])
    staging = Path(external["staging_path"])
    inner = Path(external["inner_temp_path"])
    assert staging == final.with_name(final.name + ".staged")
    assert inner == staging.with_name("." + staging.name + ".live-start-atomic.tmp")
    assert staging.is_file()
    assert not final.exists()
    assert not inner.exists()
    completed = _drive_pipeline(prepared, expected=interrupted)
    assert completed.output_child_binding["claim_state"] == "RETIRED"


def test_receipt_transitions_resume_every_write_before_phase_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for index, (fault_name, occurrence) in enumerate(
        (
            ("AFTER_PENDING_TRANSITION_CAS", 2),
            ("AFTER_TRANSITION_PRIMARY_ARTIFACT", 2),
            ("BEFORE_TRANSITION_PHASE_CAS", 1),
            ("AFTER_PENDING_TRANSITION_CAS", 3),
            ("AFTER_TRANSITION_PRIMARY_ARTIFACT", 3),
            ("BEFORE_TRANSITION_PHASE_CAS", 2),
        )
    ):
        _assert_hard_kill_resume(
            tmp_path / str(index),
            monkeypatch,
            fault_name,
            expectation=_hard_kill_expectation(
                fault_name,
                occurrence=occurrence,
            ),
        )


def test_prepublication_cleanup_quarantine_is_forward_resumable_before_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_hard_kill_resume(
        tmp_path,
        monkeypatch,
        "AFTER_PREPUBLICATION_QUARANTINE",
    )


def test_quarantine_resume_rejects_in_place_file_tamper_before_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def tamper_quarantined_file(
        _prepared: SimpleNamespace,
        interrupted: session.LiveStartSession,
    ) -> tuple[Path, ...]:
        pending = interrupted.pending_transition
        assert isinstance(pending, Mapping)
        quarantine = Path(str(pending["quarantine_path"]))
        victim = next(path for path in quarantine.rglob("*") if path.is_file())
        original_identity = path_identity(victim)
        raw = victim.read_bytes()
        assert raw
        with victim.open("r+b") as stream:
            stream.write(bytes((raw[0] ^ 1,)))
        assert path_identity(victim) == original_identity
        return (quarantine,)

    _assert_hard_kill_resume(
        tmp_path,
        monkeypatch,
        "AFTER_PREPUBLICATION_QUARANTINE",
        mutate_after_kill=tamper_quarantined_file,
        resume_error_match="cleanup.*digest|inventory.*tree|quarantine.*changed",
    )


def test_work_parent_identity_is_bound_in_session_receipt_and_cleanup_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _validated_prepublication(tmp_path, monkeypatch) as (_request, validated, *_):
        receipt = validated.package_validation_receipt.to_value()
        assert tuple(receipt["prepublication_work_parent_identity"]) == tuple(
            validated.updated_session.prepublication_work_binding[
                "work_parent_identity"
            ]
        )


def test_cleanup_identity_inventory_is_durable_before_quarantine_rename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_hard_kill_resume(
        tmp_path,
        monkeypatch,
        "AFTER_PREPUBLICATION_CLEANUP_INVENTORY_BOUND_COMMIT_BEFORE_PRIMARY_APPLIED_CAS",
    )


def test_cleanup_prepared_before_sidecar_reconstructs_only_exact_committed_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    interrupted = _interrupt_pipeline(
        prepared,
        "AFTER_PENDING_TRANSITION_CAS",
        occurrence=4,
    )
    work_root = Path(interrupted.prepublication_work_binding["work_root"])
    victim = next(path for path in work_root.rglob("*") if path.is_file())
    victim.write_bytes(victim.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="inventory|digest|work"):
        _drive_pipeline(prepared, expected=interrupted)


def test_cleanup_parent_rejects_swapped_state_root_from_active_operation_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    foreign_state_root = tmp_path / "foreign" / "HSConfig"
    foreign_state_root.mkdir(parents=True)
    forged_session_lease = SimpleNamespace(
        session_root=(
            foreign_state_root / "runs" / prepared.session_root.name
        )
    )
    controller = _controller()

    with lease_output_operation_admission() as operation_lease:
        kwargs: dict[str, Any] = {
            "create_if_missing": True,
        }
        if "operation_lease" in signature(controller._cleanup_parent).parameters:
            kwargs["operation_lease"] = operation_lease
        with pytest.raises(
            session.SessionCapabilityError,
            match="^live_start_cleanup_state_root_binding_changed$",
        ):
            controller._cleanup_parent(forged_session_lease, **kwargs)

    assert not any(foreign_state_root.iterdir())


def test_cleanup_prepared_rejects_foreign_quarantine_before_inventory_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    interrupted = _interrupt_pipeline(
        prepared,
        "AFTER_PENDING_TRANSITION_CAS",
        occurrence=4,
    )
    pending = interrupted.pending_transition
    assert isinstance(pending, Mapping)
    assert pending["operation"] == "cleanup_prepublication"
    assert pending["stage"] == "PREPARED"
    quarantine = Path(str(pending["quarantine_path"]))
    inventory = Path(str(pending["cleanup_inventory_path"]))
    staging = Path(str(pending["external_file_action"]["staging_path"]))
    inner = Path(str(pending["external_file_action"]["inner_temp_path"]))
    quarantine.write_bytes(b"foreign-quarantine")
    session_before = _physical_tree(prepared.session_root)

    with pytest.raises(
        ValueError,
        match="^live_start_cleanup_foreign_residue_present$",
    ):
        _drive_pipeline(prepared, expected=interrupted)

    assert quarantine.read_bytes() == b"foreign-quarantine"
    assert not inventory.exists()
    assert not staging.exists()
    assert not inner.exists()
    assert _physical_tree(prepared.session_root) == session_before


def test_cleanup_inventory_staged_hard_kills_reconcile_without_unknown_child(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for index, fault_name in enumerate(
        (
            "AFTER_PREPUBLICATION_CLEANUP_INVENTORY_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS",
            "AFTER_PREPUBLICATION_CLEANUP_INVENTORY_STAGING_BOUND",
            "AFTER_PREPUBLICATION_CLEANUP_INVENTORY_BOUND_COMMIT_BEFORE_PRIMARY_APPLIED_CAS",
        )
    ):
        _assert_hard_kill_resume(
            tmp_path / str(index),
            monkeypatch,
            fault_name,
        )


def test_cleanup_prepared_resume_never_recreates_missing_bound_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    interrupted = _interrupt_pipeline(
        prepared,
        "AFTER_PENDING_TRANSITION_CAS",
        occurrence=4,
    )
    pending = interrupted.pending_transition
    assert isinstance(pending, Mapping)
    assert pending["operation"] == "cleanup_prepublication"
    assert pending["stage"] == "PREPARED"
    cleanup_parent = Path(str(pending["cleanup_inventory_path"])).parent
    assert not any(cleanup_parent.iterdir())
    cleanup_parent.rmdir()
    session_before = _physical_tree(prepared.session_root)

    with pytest.raises(
        ValueError,
        match="^live_start_cleanup_parent_identity_changed$",
    ):
        _drive_pipeline(prepared, expected=interrupted)
    assert not cleanup_parent.exists()
    assert _physical_tree(prepared.session_root) == session_before


def test_prepublication_cleanup_inventory_uses_planned_staging_bound_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    staging_bound = _interrupt_pipeline(
        prepared,
        "AFTER_PREPUBLICATION_CLEANUP_INVENTORY_STAGING_BOUND",
    )
    external = staging_bound.pending_transition["external_file_action"]
    staging = Path(external["staging_path"])
    final = Path(external["final_path"])
    captured_staging = _file_fingerprint(staging)
    assert captured_staging is not None
    assert captured_staging[0] == tuple(external["staging_identity"])

    committed = _interrupt_pipeline(
        prepared,
        "AFTER_PREPUBLICATION_CLEANUP_INVENTORY_BOUND_COMMIT_BEFORE_PRIMARY_APPLIED_CAS",
    )
    assert committed.content_sha256 == staging_bound.content_sha256
    assert not staging.exists()
    assert _file_fingerprint(final) == captured_staging
    _drive_pipeline(prepared, expected=committed)
    assert not final.exists()


def test_prepublication_cleanup_inventory_retires_unbound_staging_without_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    unbound = _interrupt_pipeline(
        prepared,
        "AFTER_PREPUBLICATION_CLEANUP_INVENTORY_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS",
    )
    external = unbound.pending_transition["external_file_action"]
    staging = Path(external["staging_path"])
    residue = _file_fingerprint(staging)
    assert residue is not None
    assert external["stage"] == "PLANNED"
    assert external["staging_identity"] is None

    rebound = _interrupt_pipeline(
        prepared,
        "AFTER_PREPUBLICATION_CLEANUP_INVENTORY_STAGING_BOUND",
    )
    rebound_external = rebound.pending_transition["external_file_action"]
    rebound_staging = _file_fingerprint(Path(rebound_external["staging_path"]))
    assert rebound_staging is not None
    assert rebound_staging[0] == tuple(rebound_external["staging_identity"])
    assert rebound_staging[0] != residue[0]
    _drive_pipeline(prepared, expected=rebound)


def test_prepublication_cleanup_inventory_rejects_direct_final_from_planned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    interrupted = _interrupt_pipeline(
        prepared,
        "AFTER_PENDING_TRANSITION_CAS",
        occurrence=4,
    )
    pending = interrupted.pending_transition
    assert pending is not None
    final = Path(pending["external_file_action"]["final_path"])
    final.write_bytes(b"foreign-direct-final")
    before = final.read_bytes()
    with pytest.raises(ValueError, match="direct|final|inventory"):
        _drive_pipeline(prepared, expected=interrupted)
    assert final.read_bytes() == before


@pytest.mark.skipif(os.name == "nt", reason="POSIX hard-link convergence")
def test_prepublication_cleanup_inventory_posix_two_link_commit_preserves_identity(
    tmp_path: Path,
) -> None:
    cleanup_parent = tmp_path / "cleanup"
    cleanup_parent.mkdir()
    final = cleanup_parent / ("live-start-" + "8" * 32 + ".inventory.json")
    staging = final.with_name(final.name + ".staged")
    payload = b'{"inventory":"sealed"}'
    materialized = atomic_materialize_staging_bytes(
        staging_path=staging,
        inner_temp_path=staging.with_name(
            "." + staging.name + ".live-start-atomic.tmp"
        ),
        payload=payload,
        expected_parent_identity=path_identity(cleanup_parent),
        maximum_size=1024,
    )
    os.link(staging, final)
    assert path_identity(staging) == path_identity(final) == materialized.identity
    assert staging.stat().st_nlink == final.stat().st_nlink == 2

    committed = atomic_commit_bound_staging_no_replace(
        path=final,
        staging_path=staging,
        expected_staging_identity=materialized.identity,
        expected_size=materialized.size,
        expected_sha256=materialized.sha256,
        expected_parent_identity=path_identity(cleanup_parent),
    )

    assert committed.identity == materialized.identity == path_identity(final)
    assert final.stat().st_nlink == 1
    assert final.read_bytes() == payload
    assert not staging.exists()


def test_prepublication_cleanup_inventory_rejects_staging_or_parent_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    interrupted = _interrupt_pipeline(
        prepared,
        "AFTER_PREPUBLICATION_CLEANUP_INVENTORY_STAGING_BOUND",
    )
    pending = interrupted.pending_transition
    staging = Path(pending["external_file_action"]["staging_path"])
    original = staging.read_bytes()
    staging.unlink()
    staging.write_bytes(original)
    with pytest.raises(ValueError, match="identity|staging|inventory"):
        _drive_pipeline(prepared, expected=interrupted)


def test_cleanup_staging_bound_rejects_foreign_quarantine_before_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    interrupted = _interrupt_pipeline(
        prepared,
        "AFTER_PREPUBLICATION_CLEANUP_INVENTORY_STAGING_BOUND",
    )
    pending = interrupted.pending_transition
    assert isinstance(pending, Mapping)
    assert pending["stage"] == "STAGING_BOUND"
    external = pending["external_file_action"]
    final = Path(str(external["final_path"]))
    staging = Path(str(external["staging_path"]))
    quarantine = Path(str(pending["quarantine_path"]))
    staging_before = _file_fingerprint(staging)
    assert staging_before is not None
    assert not final.exists()
    quarantine.write_bytes(b"foreign-staging-bound-quarantine")
    session_before = (prepared.session_root / "session.json").read_bytes()

    with pytest.raises(
        ValueError,
        match="^live_start_cleanup_foreign_residue_present$",
    ):
        _drive_pipeline(prepared, expected=interrupted)

    assert (prepared.session_root / "session.json").read_bytes() == session_before
    assert not final.exists()
    assert _file_fingerprint(staging) == staging_before
    assert quarantine.read_bytes() == b"foreign-staging-bound-quarantine"


def test_cleanup_resume_rejects_replaced_work_parent_after_prepared_or_inventory_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    interrupted = _interrupt_pipeline(
        prepared,
        "AFTER_PENDING_TRANSITION_CAS",
        occurrence=4,
    )
    work_parent = Path(interrupted.prepublication_work_binding["work_parent_path"])
    retired = work_parent.with_name("work-retired")
    work_parent.rename(retired)
    work_parent.mkdir()
    with pytest.raises(ValueError, match="parent|identity"):
        _drive_pipeline(prepared, expected=interrupted)


def test_cleanup_resume_rejects_same_bytes_file_identity_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    interrupted = _interrupt_pipeline(
        prepared,
        "AFTER_PREPUBLICATION_CLEANUP_INVENTORY_BOUND_COMMIT_BEFORE_PRIMARY_APPLIED_CAS",
    )
    work_root = Path(interrupted.prepublication_work_binding["work_root"])
    victim = next(path for path in work_root.rglob("*") if path.is_file())
    raw = victim.read_bytes()
    old_identity = path_identity(victim)
    victim.unlink()
    victim.write_bytes(raw)
    assert path_identity(victim) != old_identity
    with pytest.raises(ValueError, match="identity|inventory"):
        _drive_pipeline(prepared, expected=interrupted)


def test_cleanup_resume_rejects_empty_directory_identity_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _controller()
    real_rebuild = controller._rebuild_prepublication_work_binding

    def rebuild_with_empty_directory(**kwargs: Any) -> dict[str, Any]:
        empty = kwargs["work_root"] / "empty-cleanup-entry"
        empty.mkdir(exist_ok=True)
        return real_rebuild(**kwargs)

    monkeypatch.setattr(
        controller,
        "_rebuild_prepublication_work_binding",
        rebuild_with_empty_directory,
    )
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    interrupted = _interrupt_pipeline(
        prepared,
        "AFTER_PREPUBLICATION_CLEANUP_INVENTORY_BOUND_COMMIT_BEFORE_PRIMARY_APPLIED_CAS",
    )
    work_root = Path(interrupted.prepublication_work_binding["work_root"])
    victim = next(
        path for path in work_root.rglob("*") if path.is_dir() and not any(path.iterdir())
    )
    old_identity = path_identity(victim)
    victim.rmdir()
    victim.mkdir()
    assert path_identity(victim) != old_identity
    with pytest.raises(ValueError, match="identity|inventory"):
        _drive_pipeline(prepared, expected=interrupted)


def test_cleanup_fault_after_each_entry_class_and_cursor_resumes_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    probe = _prepare_pipeline(tmp_path / "probe", monkeypatch)
    with _lease_prepublication_capabilities(probe) as (validated, *_):
        cleanup_entry_count = int(
            validated.updated_session.prepublication_work_binding[
                "cleanup_entry_count"
            ]
        )
        observed_entry_classes = {"root"}
        for path in validated.work_root.rglob("*"):
            observed_entry_classes.add(
                "directory" if path.is_dir() else "file"
            )
        assert observed_entry_classes == {"file", "directory", "root"}
        assert cleanup_entry_count == 1 + sum(
            1 for _path in validated.work_root.rglob("*")
        )
    for occurrence in range(1, cleanup_entry_count + 1):
        _assert_hard_kill_resume(
            tmp_path / f"cursor-{occurrence}",
            monkeypatch,
            "AFTER_PREPUBLICATION_CLEANUP_ENTRY",
            expectation=_hard_kill_expectation(
                "AFTER_PREPUBLICATION_CLEANUP_ENTRY",
                occurrence=occurrence,
            ),
        )


def test_cleanup_deleting_resume_rejects_replaced_work_parent_and_foreign_work_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    foreign_raw = b"foreign-work-root-after-cleanup-start"

    def replace_bound_work_parent(
        _prepared: SimpleNamespace,
        interrupted: session.LiveStartSession,
    ) -> tuple[Path, ...]:
        pending = interrupted.pending_transition
        assert isinstance(pending, Mapping)
        assert pending["stage"] == "CLEANUP_DELETING"
        assert pending["cleanup_cursor"] == 0
        work_parent = Path(str(pending["work_parent_path"]))
        work_root = Path(str(pending["work_root"]))
        retired = work_parent.with_name(
            f"{work_parent.name}-retired-{interrupted.run_id}"
        )
        assert path_identity(work_parent) == tuple(pending["work_parent_identity"])
        assert not work_root.exists()
        assert not any(work_parent.iterdir())
        work_parent.rename(retired)
        work_parent.mkdir()
        work_root.mkdir()
        (work_root / "foreign.bin").write_bytes(foreign_raw)
        assert path_identity(retired) == tuple(pending["work_parent_identity"])
        assert path_identity(work_parent) != tuple(pending["work_parent_identity"])
        assert (work_root / "foreign.bin").read_bytes() == foreign_raw
        return retired, work_parent

    _assert_hard_kill_resume(
        tmp_path,
        monkeypatch,
        "AFTER_PREPUBLICATION_CLEANUP_ENTRY",
        expectation=_hard_kill_expectation(
            "AFTER_PREPUBLICATION_CLEANUP_ENTRY",
            occurrence=1,
        ),
        mutate_after_kill=replace_bound_work_parent,
        resume_error_match="^live_start_cleanup_work_parent_identity_changed$",
    )


def test_cleanup_final_cas_revalidates_cleanup_parent_identity_after_fault_hook(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    interrupted = _interrupt_pipeline(
        prepared,
        "AFTER_PREPUBLICATION_CLEANUP_INVENTORY_DELETE",
    )
    pending = interrupted.pending_transition
    assert isinstance(pending, Mapping)
    assert pending["stage"] == "CLEANUP_DELETING"
    assert pending["cleanup_cursor"] == pending["cleanup_entry_count"]
    cleanup_parent = Path(str(pending["cleanup_inventory_path"])).parent
    retired = cleanup_parent.with_name(
        f"{cleanup_parent.name}-retired-{interrupted.run_id}"
    )
    expected_identity = tuple(pending["cleanup_parent_identity"])
    assert path_identity(cleanup_parent) == expected_identity
    assert not any(cleanup_parent.iterdir())
    session_before = _physical_tree(prepared.session_root)
    foreign_raw = b"foreign-cleanup-parent-after-final-fault"
    foreign_path = cleanup_parent / "foreign.bin"
    swap_attempted = False
    swapped = False

    def swap_cleanup_parent_at_final_fault(point: Any) -> None:
        nonlocal swap_attempted, swapped
        if point is not (
            _faults().LiveStartFaultPoint.AFTER_PREPUBLICATION_CLEANUP_BEFORE_CAS
        ):
            return
        assert not swapped
        assert path_identity(cleanup_parent) == expected_identity
        assert not any(cleanup_parent.iterdir())
        swap_attempted = True
        cleanup_parent.rename(retired)
        cleanup_parent.mkdir()
        foreign_path.write_bytes(foreign_raw)
        assert path_identity(retired) == expected_identity
        assert path_identity(cleanup_parent) != expected_identity
        assert foreign_path.read_bytes() == foreign_raw
        swapped = True

    expected_error: type[BaseException]
    expected_match: str
    if os.name == "nt":
        expected_error = PermissionError
        expected_match = "used by another process|anderen Prozess verwendet"
    else:
        expected_error = ValueError
        expected_match = "^live_start_cleanup_parent_identity_changed$"
    with pytest.raises(expected_error, match=expected_match):
        _drive_pipeline(
            prepared,
            expected=interrupted,
            fault_hook=swap_cleanup_parent_at_final_fault,
        )

    assert swap_attempted
    preserved = session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert preserved.content_sha256 == interrupted.content_sha256
    assert preserved.pending_transition == interrupted.pending_transition
    assert _physical_tree(prepared.session_root) == session_before
    if swapped:
        assert path_identity(retired) == expected_identity
        assert path_identity(cleanup_parent) != expected_identity
        assert foreign_path.read_bytes() == foreign_raw
        assert not any(retired.iterdir())
    else:
        assert path_identity(cleanup_parent) == expected_identity
        assert not retired.exists()
        assert not foreign_path.exists()
        assert not any(cleanup_parent.iterdir())


def test_cleanup_entry_delete_revalidates_later_file_digest_after_fault_hook(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    interrupted = _interrupt_pipeline(
        prepared,
        "AFTER_PREPUBLICATION_QUARANTINE",
    )
    pending = interrupted.pending_transition
    assert isinstance(pending, Mapping)
    inventory_path = Path(str(pending["cleanup_inventory_path"]))
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    quarantine = Path(str(pending["quarantine_path"]))
    victim_index, victim_row = next(
        (index, row)
        for index, row in enumerate(inventory["entries"])
        if index > 0 and row["entry_kind"] == "file" and row["size"] > 0
    )
    victim = quarantine / str(victim_row["relative_path"])
    original_raw = victim.read_bytes()
    original_identity = path_identity(victim)
    assert len(original_raw) == victim_row["size"]
    assert victim_index < pending["cleanup_entry_count"]
    tampered_raw: bytes | None = None

    def tamper_after_first_cleanup_entry(point: Any) -> None:
        nonlocal tampered_raw
        if (
            point
            is not _faults().LiveStartFaultPoint.AFTER_PREPUBLICATION_CLEANUP_ENTRY
            or tampered_raw is not None
        ):
            return
        tampered_raw = bytes((original_raw[0] ^ 1,)) + original_raw[1:]
        with victim.open("r+b") as stream:
            assert stream.write(tampered_raw) == len(tampered_raw)
            stream.truncate()
            stream.flush()
            os.fsync(stream.fileno())
        assert path_identity(victim) == original_identity
        assert victim.read_bytes() == tampered_raw

    with pytest.raises(
        ValueError,
        match="^live_start_cleanup_entry_digest_changed$",
    ):
        _drive_pipeline(
            prepared,
            expected=interrupted,
            fault_hook=tamper_after_first_cleanup_entry,
        )

    assert tampered_raw is not None
    assert victim.read_bytes() == tampered_raw
    assert path_identity(victim) == original_identity
    preserved = session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    preserved_pending = preserved.pending_transition
    assert isinstance(preserved_pending, Mapping)
    assert preserved_pending["stage"] == "CLEANUP_DELETING"
    assert 1 <= preserved_pending["cleanup_cursor"] <= victim_index
    assert preserved_pending["cleanup_cursor"] < pending["cleanup_entry_count"]


def test_cleanup_retains_parent_guards_from_quarantine_through_final_clear(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _controller()
    real_cleanup_parent_guard = controller._hold_cleanup_parent_binding
    real_work_parent_guard = controller._hold_cleanup_work_parent_binding
    real_transition = session._transition_receipt_authorized_under_lock
    parent_depth = 0
    work_depth = 0
    parent_acquisitions = 0
    work_acquisitions = 0
    cleanup_window_started = False
    final_clear_seen = False
    parent_dropped_before_final = False
    work_dropped_before_final = False
    observed: list[Any] = []

    @contextmanager
    def track_cleanup_parent_guard(
        *args: Any,
        **kwargs: Any,
    ) -> Iterator[Any]:
        nonlocal parent_acquisitions, parent_depth, parent_dropped_before_final
        parent_acquisitions += 1
        with real_cleanup_parent_guard(*args, **kwargs) as guard:
            parent_depth += 1
            try:
                yield guard
            finally:
                parent_depth -= 1
                if cleanup_window_started and not final_clear_seen and parent_depth == 0:
                    parent_dropped_before_final = True

    @contextmanager
    def track_work_parent_guard(
        *args: Any,
        **kwargs: Any,
    ) -> Iterator[Any]:
        nonlocal work_acquisitions, work_depth, work_dropped_before_final
        work_acquisitions += 1
        with real_work_parent_guard(*args, **kwargs) as guard:
            work_depth += 1
            try:
                yield guard
            finally:
                work_depth -= 1
                if cleanup_window_started and not final_clear_seen and work_depth == 0:
                    work_dropped_before_final = True

    def track_final_clear(*args: Any, **kwargs: Any) -> session.LiveStartSession:
        nonlocal final_clear_seen
        expected = kwargs.get("expected_session")
        changes = kwargs.get("changes")
        pending = (
            expected.pending_transition
            if isinstance(expected, session.LiveStartSession)
            else None
        )
        is_cleanup_clear = (
            isinstance(pending, Mapping)
            and pending.get("operation") == "cleanup_prepublication"
            and changes == {"pending_transition": None}
        )
        if is_cleanup_clear:
            assert (parent_depth, work_depth) == (1, 1)
        successor = real_transition(*args, **kwargs)
        if is_cleanup_clear:
            assert (parent_depth, work_depth) == (1, 1)
            final_clear_seen = True
        return successor

    relevant = {
        _faults().LiveStartFaultPoint.AFTER_PREPUBLICATION_QUARANTINE,
        _faults().LiveStartFaultPoint.AFTER_PREPUBLICATION_CLEANUP_ENTRY,
        _faults().LiveStartFaultPoint.AFTER_PREPUBLICATION_CLEANUP_INVENTORY_DELETE,
        _faults().LiveStartFaultPoint.AFTER_PREPUBLICATION_CLEANUP_BEFORE_CAS,
    }

    def observe_guard_lifetime(point: Any) -> None:
        nonlocal cleanup_window_started
        if point not in relevant:
            return
        if point is _faults().LiveStartFaultPoint.AFTER_PREPUBLICATION_QUARANTINE:
            cleanup_window_started = True
        assert (parent_depth, work_depth) == (1, 1)
        observed.append(point)

    monkeypatch.setattr(
        controller,
        "_hold_cleanup_parent_binding",
        track_cleanup_parent_guard,
    )
    monkeypatch.setattr(
        controller,
        "_hold_cleanup_work_parent_binding",
        track_work_parent_guard,
    )
    monkeypatch.setattr(
        session,
        "_transition_receipt_authorized_under_lock",
        track_final_clear,
    )
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    completed = _drive_pipeline(
        prepared,
        fault_hook=observe_guard_lifetime,
    )

    assert completed.pending_transition is None
    assert final_clear_seen
    assert parent_acquisitions == 1
    assert work_acquisitions == 1
    assert not parent_dropped_before_final
    assert not work_dropped_before_final
    assert (parent_depth, work_depth) == (0, 0)
    assert observed[0] is _faults().LiveStartFaultPoint.AFTER_PREPUBLICATION_QUARANTINE
    assert observed[-2:] == [
        _faults().LiveStartFaultPoint.AFTER_PREPUBLICATION_CLEANUP_INVENTORY_DELETE,
        _faults().LiveStartFaultPoint.AFTER_PREPUBLICATION_CLEANUP_BEFORE_CAS,
    ]
    assert observed.count(
        _faults().LiveStartFaultPoint.AFTER_PREPUBLICATION_CLEANUP_ENTRY
    ) == int(completed.prepublication_work_binding["cleanup_entry_count"])


@pytest.mark.skipif(os.name == "nt", reason="POSIX verified cleanup pipeline")
def test_posix_pipeline_cleanup_completes_with_no_pending_transition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)

    completed = _drive_pipeline(prepared)

    assert completed.phase is session.LiveStartPhase.PUBLICATION_COMMITTED
    assert completed.pending_transition is None


def test_cleanup_substitution_or_unknown_entry_preserves_nonterminal_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    interrupted = _interrupt_pipeline(
        prepared,
        "AFTER_PREPUBLICATION_CLEANUP_INVENTORY_BOUND_COMMIT_BEFORE_PRIMARY_APPLIED_CAS",
    )
    work_root = Path(interrupted.prepublication_work_binding["work_root"])
    unknown = work_root / "unknown-entry"
    unknown.write_bytes(b"foreign")
    with pytest.raises(ValueError, match="unknown|inventory"):
        _drive_pipeline(prepared, expected=interrupted)
    preserved = session.load_live_start_session(
        prepared.session_root,
        local_app_data_root=prepared.local_app_data,
    )
    assert preserved.pending_transition is not None
    assert unknown.read_bytes() == b"foreign"


def test_cleanup_clears_transition_last_before_apply_or_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for index, fault_name in enumerate(
        (
            "AFTER_PREPUBLICATION_CLEANUP_INVENTORY_DELETE",
            "AFTER_PREPUBLICATION_CLEANUP_BEFORE_CAS",
        )
    ):
        _assert_hard_kill_resume(
            tmp_path / str(index),
            monkeypatch,
            fault_name,
        )


@pytest.mark.parametrize(
    "foreign_surface",
    ("quarantine_file", "quarantine_directory", "staging", "inner_temp"),
)
def test_cleanup_final_cas_rejects_recreated_owned_surface_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    foreign_surface: str,
) -> None:
    def recreate_surface(
        _prepared: SimpleNamespace,
        interrupted: session.LiveStartSession,
    ) -> tuple[Path, ...]:
        pending = interrupted.pending_transition
        assert isinstance(pending, Mapping)
        inventory = Path(str(pending["cleanup_inventory_path"]))
        staging = inventory.with_name(inventory.name + ".staged")
        inner = staging.with_name(
            "." + staging.name + ".live-start-atomic.tmp"
        )
        quarantine = Path(str(pending["quarantine_path"]))
        target = {
            "quarantine_file": quarantine,
            "quarantine_directory": quarantine,
            "staging": staging,
            "inner_temp": inner,
        }[foreign_surface]
        if foreign_surface == "quarantine_directory":
            target.mkdir()
        else:
            target.write_bytes(b"foreign-cleanup-surface")
        return (inventory.parent,)

    _assert_hard_kill_resume(
        tmp_path,
        monkeypatch,
        "AFTER_PREPUBLICATION_CLEANUP_INVENTORY_DELETE",
        mutate_after_kill=recreate_surface,
        resume_error_match="cleanup|quarantine|staging|residue|surface",
    )


def test_cleanup_delete_fault_precedes_immediate_final_cas_with_no_surfaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    cleanup_parent = prepared.session_root.parent.parent / "cleanup"
    inventory = cleanup_parent / (
        f"live-start-{prepared.session_root.name}.inventory.json"
    )
    staging = inventory.with_name(inventory.name + ".staged")
    inner = staging.with_name("." + staging.name + ".live-start-atomic.tmp")
    quarantine = cleanup_parent / (
        f"live-start-{prepared.session_root.name}.quarantine"
    )
    relevant = {
        _faults().LiveStartFaultPoint.AFTER_PREPUBLICATION_CLEANUP_INVENTORY_DELETE,
        _faults().LiveStartFaultPoint.AFTER_PREPUBLICATION_CLEANUP_BEFORE_CAS,
    }
    observed: list[Any] = []

    def observe(point: Any) -> None:
        if point not in relevant:
            return
        assert not any(
            path.exists() for path in (inventory, staging, inner, quarantine)
        )
        observed.append(point)

    completed = _drive_pipeline(prepared, fault_hook=observe)
    assert completed.pending_transition is None
    assert observed == [
        _faults().LiveStartFaultPoint.AFTER_PREPUBLICATION_CLEANUP_INVENTORY_DELETE,
        _faults().LiveStartFaultPoint.AFTER_PREPUBLICATION_CLEANUP_BEFORE_CAS,
    ]
