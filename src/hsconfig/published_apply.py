"""Compose one published package apply and exact runtime match under held locks."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterator, Literal, Mapping, cast

from hsconfig import live_start_session
from hsconfig.apply_invocation import (
    ApplyInvocation,
    build_apply_invocation,
    capture_pre_apply_runtime_snapshot,
    load_apply_invocation,
    require_apply_invocation_admission_capacity,
)
from hsconfig.current_output import (
    PackageInputLease,
    lease_package_input,
    revalidate_package_input_lease,
)
from hsconfig.live_start_faults import (
    LiveStartFaultHook,
    LiveStartFaultPoint,
    invoke_live_start_fault,
    no_live_start_fault,
)
from hsconfig.live_start_session import (
    LiveStartPhase,
    LiveStartSession,
    LiveStartSessionLease,
    RuntimeApplyRecoveryEvidence,
    RuntimeLayoutBootstrapEvidence,
    TerminalResolutionCleanupInventory,
    TerminalResolutionEvidence,
)
from hsconfig.operator_profile import (
    OperatorProfileLease,
    lease_operator_profile,
    load_operator_profile,
    revalidate_operator_profile_lease,
)
from hsconfig.output_operation_admission import (
    OutputOperationAdmissionEvidence,
    OutputOperationAdmissionLease,
    build_output_operation_admission_bytes,
    lease_output_operation_admission,
    observe_output_operation_admission_under_lease,
)
from hsconfig.output_publisher import (
    PublishedOutput,
    _admission_raw_sha256,
    release_output_operation_admission_under_lease,
)
from hsconfig.package_io import (
    MAX_FILESYSTEM_ENTRIES_PER_DIRECTORY,
    MAX_FILESYSTEM_NODES,
    PathIdentity,
    path_identity,
    path_identity_from_status,
    read_file_no_follow,
    require_plain_directory,
    snapshot_bounded_filesystem_package,
    status_is_reparse,
)
from hsconfig.package_domain import canonical_relative_path
from hsconfig.package_request import FrozenJsonDocument
from hsconfig.run_manifest import (
    MAX_RUN_FILES,
    MAX_RUN_PATH_BYTES,
    MAX_RUN_TOTAL_BYTES,
)
from hsconfig.starter_contract import STARTER_CANDIDATE_MAX_BYTES
from hsconfig.runtime_apply import (
    PreparedPackageInstall,
    prepare_package_install_from_lease,
)
from hsconfig.runtime_installer import (
    ControllerApplyLeasePair,
    RuntimeInstallPlan,
    _authenticate_controller_apply_pair_binding,
    _bind_controller_apply_pair_runtime_admission,
    _execute_runtime_admission_file_action_from_pair,
    _require_active_controller_apply_pair,
    _require_active_runtime_apply_lease,
    _require_retained_child_absent,
    _retire_success_attempt_evidence_step_from_pair,
    _seal_apply_recovery_successor,
    _source_manifest_sha256,
    _state_key,
    _validated_complete_layout_successor_identities,
    bootstrap_runtime_layout_directory_from_pair,
    classify_runtime_failure_from_pair,
    delete_runtime_no_commit_entry_from_pair,
    lease_controller_apply_pair,
    load_bound_runtime_no_commit_inventory_from_pair,
    observe_initial_runtime_install_from_pair,
    plan_runtime_install,
    observe_runtime_failure_selection_from_pair,
    recover_runtime_attempt_from_pair,
    reconstruct_runtime_no_commit_inventory_from_pair,
    revalidate_committed_mismatch_terminal_evidence_retired_from_pair,
    revalidate_resolved_terminal_evidence_retired_from_pair,
    revalidate_success_candidate_runtime_parity_from_pair,
    revalidate_success_terminal_evidence_retired_from_pair,
    revalidate_committed_runtime_control_plane_from_pair,
    retire_runtime_no_commit_metadata_from_pair,
)
from hsconfig.runtime_live_admission import (
    RuntimeLiveAttemptAdmissionEvidence,
    _project_runtime_live_attempt_admission_bytes,
    build_runtime_live_attempt_admission_bytes,
    load_runtime_live_attempt_admission,
    release_runtime_live_attempt_exact,
    runtime_live_attempt_admission_path,
)
from hsconfig.runtime_package_match import (
    build_runtime_package_match_report_from_pair,
)


class PhysicalApplyDisposition(StrEnum):
    NOT_COMMITTED = "NOT_COMMITTED"
    COMMITTED = "COMMITTED"
    COMMITTED_RECOVERY_PENDING = "COMMITTED_RECOVERY_PENDING"
    UNKNOWN_REQUIRES_RECOVERY = "UNKNOWN_REQUIRES_RECOVERY"


@dataclass(frozen=True, slots=True)
class ApplyAndMatchPublishedResult:
    raw_apply_status: Literal[
        "applied",
        "already_current",
        "recovered",
        "committed_receipt_pending",
    ] | None
    physical_disposition: PhysicalApplyDisposition
    runtime_match_status: Literal["not_run", "matched", "mismatch", "unknown"]
    runtime_match_sha256: str | None
    package_root_sha256: str | None
    last_apply_receipt_sha256: str | None
    runtime_state_sha256: str | None
    deck_config_ini_sha256: str | None
    retained_attempt_record_path: Path | None
    retained_attempt_record_identity: PathIdentity | None
    retained_attempt_record_sha256: str | None
    retained_journal_path: Path | None
    retained_journal_identity: PathIdentity | None
    retained_journal_sha256: str | None
    retained_target_owner_journal_path: Path | None
    retained_target_owner_journal_identity: PathIdentity | None
    retained_target_owner_journal_sha256: str | None
    runtime_admission_path: Path | None
    runtime_admission_parent_identity: PathIdentity | None
    runtime_admission_identity: PathIdentity | None
    runtime_admission_sha256: str | None
    terminal_status: Literal[
        "LIVE_AND_MATCHED",
        "ALREADY_LIVE",
        "FAILED_PRESERVED",
        "APPLIED_BUT_NOT_VERIFIED",
    ]
    error_code: str | None


@dataclass(frozen=True, slots=True)
class RecoverApplyNotStarted:
    status: Literal["apply_not_started"]
    run_id: str
    session_root: Path
    session_root_identity: PathIdentity
    persisted_session_sha256: str
    runtime_write_performed: Literal[False]


RecoverApplyResult = ApplyAndMatchPublishedResult | RecoverApplyNotStarted


@dataclass(frozen=True, slots=True)
class AttemptAcknowledgementEvidence:
    apply_attempt_id: str
    retention_owner_run_id: str
    retention_fence_path: Path
    retention_fence_identity: PathIdentity
    retention_fence_sha256: str
    journal_path: Path
    journal_identity: PathIdentity
    journal_sha256: str
    target_owner_journal_path: Path
    target_owner_journal_identity: PathIdentity
    target_owner_journal_sha256: str
    target_path: Path
    target_identity: PathIdentity
    package_root_sha256: str
    runtime_admission_path: Path
    runtime_admission_parent_identity: PathIdentity
    runtime_admission_identity: PathIdentity
    runtime_admission_sha256: str
    journal_owns_target: bool
    acknowledgement_action: Literal[
        "retain_target_owner_delete_fence",
        "delete_nonowning_attempt_and_fence",
    ]


def _sealed_attempt_acknowledgement(
    *,
    run_id: str,
    evidence: AttemptAcknowledgementEvidence,
) -> Mapping[str, Any]:
    return live_start_session.seal_embedded_document(
        "attempt_acknowledgement",
        {
            "schema_version": 1,
            "acknowledgement_kind": (
                live_start_session.LIVE_START_ATTEMPT_ACKNOWLEDGEMENT_KIND
            ),
            "run_id": run_id,
            "apply_attempt_id": evidence.apply_attempt_id,
            "retention_owner_run_id": evidence.retention_owner_run_id,
            "retention_fence_path": str(evidence.retention_fence_path),
            "retention_fence_identity": list(evidence.retention_fence_identity),
            "retention_fence_sha256": evidence.retention_fence_sha256,
            "journal_path": str(evidence.journal_path),
            "journal_identity": list(evidence.journal_identity),
            "journal_sha256": evidence.journal_sha256,
            "target_owner_journal_path": str(
                evidence.target_owner_journal_path
            ),
            "target_owner_journal_identity": list(
                evidence.target_owner_journal_identity
            ),
            "target_owner_journal_sha256": (
                evidence.target_owner_journal_sha256
            ),
            "target_path": str(evidence.target_path),
            "target_identity": list(evidence.target_identity),
            "package_root_sha256": evidence.package_root_sha256,
            "runtime_admission_path": str(evidence.runtime_admission_path),
            "runtime_admission_parent_identity": list(
                evidence.runtime_admission_parent_identity
            ),
            "runtime_admission_identity": list(
                evidence.runtime_admission_identity
            ),
            "runtime_admission_sha256": evidence.runtime_admission_sha256,
            "journal_owns_target": evidence.journal_owns_target,
            "acknowledgement_action": evidence.acknowledgement_action,
        },
    )


def _terminal_resolution_cleanup_stage_successor(
    resolution: Mapping[str, Any],
    *,
    expected_stage: str,
    successor_stage: str,
) -> TerminalResolutionEvidence:
    if resolution.get("cleanup_stage") != expected_stage:
        raise live_start_session.SessionConflictError(
            "published_apply_terminal_cleanup_stage_invalid"
        )
    successor = live_start_session._thaw(resolution)
    successor.pop("content_sha256", None)
    successor["cleanup_stage"] = successor_stage
    return TerminalResolutionEvidence(
        live_start_session._seal_terminal_resolution(successor)
    )


class HeldApplyAndMatchPublished:
    """Nonserializable result authority valid only inside its outer context."""

    __slots__ = (
        "_acknowledgement_evidence",
        "_active",
        "_acknowledged",
        "_fault_hook",
        "_invocation",
        "_lease_pair",
        "_profile_lease",
        "_result",
        "_runtime_admission",
        "_session_lease",
        "_updated_session",
    )

    def __init__(
        self,
        *,
        updated_session: LiveStartSession,
        invocation: ApplyInvocation,
        result: ApplyAndMatchPublishedResult,
        acknowledgement_evidence: AttemptAcknowledgementEvidence | None,
        runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
        session_lease: LiveStartSessionLease,
        profile_lease: OperatorProfileLease,
        lease_pair: ControllerApplyLeasePair,
        fault_hook: LiveStartFaultHook = no_live_start_fault,
    ) -> None:
        self._updated_session = updated_session
        self._invocation = invocation
        self._result = result
        self._acknowledgement_evidence = acknowledgement_evidence
        self._runtime_admission = runtime_admission
        self._session_lease = session_lease
        self._profile_lease = profile_lease
        self._lease_pair = lease_pair
        self._fault_hook = fault_hook
        self._active = True
        self._acknowledged = False

    def __reduce__(self) -> object:
        raise TypeError("held_apply_and_match_not_serializable")

    def _require_active(self) -> None:
        if not self._active:
            raise ValueError("held_apply_and_match_expired")
        revalidate_operator_profile_lease(self._profile_lease)
        if self._acknowledged:
            _authenticate_controller_apply_pair_binding(self._lease_pair)
            revalidate_package_input_lease(self._lease_pair.package_lease)
        else:
            _require_active_controller_apply_pair(self._lease_pair)

    @property
    def updated_session(self) -> LiveStartSession:
        self._require_active()
        return self._updated_session

    @property
    def invocation(self) -> ApplyInvocation:
        self._require_active()
        return self._invocation

    @property
    def result(self) -> ApplyAndMatchPublishedResult:
        self._require_active()
        return self._result

    @property
    def acknowledgement_evidence(self) -> AttemptAcknowledgementEvidence | None:
        self._require_active()
        return self._acknowledgement_evidence

    @property
    def runtime_admission_evidence(self) -> RuntimeLiveAttemptAdmissionEvidence:
        self._require_active()
        return self._runtime_admission

    def _require_unresolved_active(self) -> None:
        if not self._active:
            raise ValueError("held_apply_and_match_expired")
        if self._acknowledged:
            _authenticate_controller_apply_pair_binding(self._lease_pair)
            raise ValueError("held_apply_and_match_already_resolved")
        self._require_active()

    def _expected_result_intent_fields(self, *, run_id: str) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "apply_attempt_id": self._invocation.apply_attempt_id,
            "terminal_status": self._result.terminal_status,
            "raw_apply_status": self._result.raw_apply_status,
            "physical_disposition": self._result.physical_disposition.value,
            "runtime_match_status": self._result.runtime_match_status,
            "runtime_match_sha256": self._result.runtime_match_sha256,
            "package_root_sha256": self._result.package_root_sha256,
            "last_apply_receipt_sha256": self._result.last_apply_receipt_sha256,
            "runtime_state_sha256": self._result.runtime_state_sha256,
            "deck_config_ini_sha256": self._result.deck_config_ini_sha256,
            "retained_attempt_record_path": (
                None
                if self._result.retained_attempt_record_path is None
                else str(self._result.retained_attempt_record_path)
            ),
            "retained_attempt_record_identity": (
                self._result.retained_attempt_record_identity
            ),
            "retained_attempt_record_sha256": (
                self._result.retained_attempt_record_sha256
            ),
            "retained_journal_path": (
                None
                if self._result.retained_journal_path is None
                else str(self._result.retained_journal_path)
            ),
            "retained_journal_identity": self._result.retained_journal_identity,
            "retained_journal_sha256": self._result.retained_journal_sha256,
            "retained_target_owner_journal_path": (
                None
                if self._result.retained_target_owner_journal_path is None
                else str(self._result.retained_target_owner_journal_path)
            ),
            "retained_target_owner_journal_identity": (
                self._result.retained_target_owner_journal_identity
            ),
            "retained_target_owner_journal_sha256": (
                self._result.retained_target_owner_journal_sha256
            ),
            "runtime_admission_path": str(self._runtime_admission.admission_path),
            "runtime_admission_parent_identity": (
                self._runtime_admission.admission_parent_identity
            ),
            "runtime_admission_identity": self._runtime_admission.admission_identity,
            "runtime_admission_sha256": self._runtime_admission.admission_sha256,
            "error_code": self._result.error_code,
        }

    def _require_terminal_cursor(
        self,
        *,
        session_lease: LiveStartSessionLease,
        expected_terminal_session: LiveStartSession,
        acknowledgement: Literal["required", "forbidden"],
    ) -> LiveStartSession:
        self._require_unresolved_active()
        if session_lease is not self._session_lease:
            raise ValueError("held_apply_and_match_session_lease_invalid")
        if not isinstance(expected_terminal_session, LiveStartSession):
            raise TypeError("held_apply_and_match_terminal_cursor_invalid")
        persisted = live_start_session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        evidence = self._acknowledgement_evidence
        expected_acknowledgement = (
            None
            if evidence is None
            else _sealed_attempt_acknowledgement(
                run_id=persisted.run_id,
                evidence=evidence,
            )
        )
        intent = persisted.result_intent
        acknowledgement_valid = (
            evidence is not None
            and persisted.attempt_acknowledgement == expected_acknowledgement
            if acknowledgement == "required"
            else evidence is None and persisted.attempt_acknowledgement is None
        )
        if (
            persisted != expected_terminal_session
            or persisted.canonical_json != expected_terminal_session.canonical_json
            or persisted.content_sha256 != expected_terminal_session.content_sha256
            or persisted.session_identity != expected_terminal_session.session_identity
            or persisted.terminal_status != self._result.terminal_status
            or not acknowledgement_valid
            or not isinstance(intent, Mapping)
            or any(
                intent.get(field_name) != expected_value
                for field_name, expected_value in self._expected_result_intent_fields(
                    run_id=persisted.run_id
                ).items()
            )
        ):
            raise ValueError("held_apply_and_match_terminal_cursor_invalid")
        return persisted

    def _revalidate_terminal_release_current_facts(
        self,
        *,
        session_lease: LiveStartSessionLease,
        cursor: LiveStartSession,
    ) -> None:
        retirement = cursor.terminal_retirement
        if (
            not isinstance(retirement, Mapping)
            or retirement.get("stage") != "EVIDENCE_RETIRED"
        ):
            raise ValueError(
                "held_apply_and_match_terminal_release_cursor_invalid"
            )
        operation = retirement.get("operation")
        if operation == "ack_success":
            revalidate_success_terminal_evidence_retired_from_pair(
                lease_pair=self._lease_pair,
                session_lease=session_lease,
                expected_retirement_session=cursor,
                runtime_admission=self._runtime_admission,
            )
        elif operation == "release_committed_mismatch":
            try:
                revalidate_committed_mismatch_terminal_evidence_retired_from_pair(
                    lease_pair=self._lease_pair,
                    session_lease=session_lease,
                    expected_retirement_session=cursor,
                    runtime_admission=self._runtime_admission,
                )
                package_lease = self._lease_pair.package_lease
                publication = package_lease.publication
                if publication is None:
                    raise ValueError("publication")
                plan = plan_runtime_install(
                    published_output=PublishedOutput(
                        output_root=package_lease.output_root,
                        revision_root=package_lease.package_root.parent,
                        package_root=package_lease.package_root,
                        content_root_sha256=(
                            publication.content_root_sha256
                        ),
                        reused_existing_revision=True,
                    ),
                    runtime_root=self._runtime_admission.runtime_root,
                )
                report = build_runtime_package_match_report_from_pair(
                    lease_pair=self._lease_pair,
                    logical_config_dir=plan.logical_config_dir,
                    runtime_config_dir=plan.versioned_config_dir,
                )
                if (
                    report.get("status") != "mismatch"
                    or _match_digest(report)
                    != self._result.runtime_match_sha256
                    or live_start_session.load_live_start_session_under_lock(
                        session_lease=session_lease
                    )
                    != cursor
                ):
                    raise ValueError("mismatch")
            except Exception as error:
                raise ValueError(
                    "runtime_terminal_release_current_facts_changed"
                ) from error
        elif operation == "release_not_committed":
            self._revalidate_not_committed_terminal_evidence_retired(
                session_lease=session_lease,
                cursor=cursor,
            )
        elif operation == "release_resolved_terminal":
            revalidate_resolved_terminal_evidence_retired_from_pair(
                lease_pair=self._lease_pair,
                session_lease=session_lease,
                expected_retirement_session=cursor,
                runtime_admission=self._runtime_admission,
            )
        else:
            raise ValueError(
                "held_apply_and_match_terminal_release_cursor_invalid"
            )

    def _terminal_release_observation_receipt(
        self,
        *,
        session_lease: LiveStartSessionLease,
        cursor: LiveStartSession,
    ) -> live_start_session.RuntimeObservationReceipt:
        retirement = cursor.terminal_retirement
        if not isinstance(retirement, Mapping):
            raise ValueError(
                "held_apply_and_match_terminal_release_cursor_invalid"
            )
        observation_authorization = (
            live_start_session._authorize_runtime_observation_under_lock(
                session_lease=session_lease,
                expected_session=cursor,
                observation_family="terminal_release",
                apply_attempt_id=self._runtime_admission.apply_attempt_id,
            )
        )

        def observe() -> live_start_session.RuntimeObservationPostcondition:
            self._revalidate_terminal_release_current_facts(
                session_lease=session_lease,
                cursor=cursor,
            )
            return live_start_session.RuntimeObservationPostcondition(
                action=self._runtime_admission.apply_attempt_id,
                observation_family="terminal_release",
                evidence={
                    "terminal_retirement_sha256": retirement[
                        "content_sha256"
                    ]
                },
            )

        return live_start_session._execute_runtime_observation(
            observation_authorization=observation_authorization,
            observation_family="terminal_release",
            read_only_observation=observe,
        )

    def _release_runtime_admission_after_evidence_retired(
        self,
        *,
        session_lease: LiveStartSessionLease,
        cursor: LiveStartSession,
    ) -> LiveStartSession:
        retirement = cursor.terminal_retirement
        stage = retirement.get("stage") if isinstance(retirement, Mapping) else None
        if stage == "EVIDENCE_RETIRED":
            invoke_live_start_fault(
                self._fault_hook,
                LiveStartFaultPoint.AFTER_ATTEMPT_EVIDENCE_RETIRED_BEFORE_ADMISSION_RELEASE,
            )
            current_facts_receipt = self._terminal_release_observation_receipt(
                session_lease=session_lease,
                cursor=cursor,
            )
            release_transition_authorization = (
                live_start_session.authorize_terminal_retirement_under_lock(
                    session_lease=session_lease,
                    expected_retirement_session=cursor,
                    runtime_observation_receipt=current_facts_receipt,
                )
            )
            cursor = live_start_session.advance_terminal_retirement_under_lock(
                session_lease=session_lease,
                expected_retirement_session=cursor,
                transition="admission_release_authorized",
                terminal_authorization=release_transition_authorization,
                physical_step_receipt=None,
            )
            self._updated_session = cursor
        elif stage != "ADMISSION_RELEASE_AUTHORIZED":
            raise ValueError("held_apply_and_match_terminal_release_cursor_invalid")
        release_authorization = (
            live_start_session.authorize_terminal_retirement_under_lock(
                session_lease=session_lease,
                expected_retirement_session=cursor,
            )
        )
        _release_runtime_live_attempt_from_pair(
            session_lease=session_lease,
            expected_release_authorized_session=cursor,
            terminal_authorization=release_authorization,
            profile_lease=self._profile_lease,
            lease_pair=self._lease_pair,
            expected=self._runtime_admission,
            fault_hook=self._fault_hook,
        )
        self._acknowledged = True
        return cursor

    def _revalidate_not_committed_terminal_evidence_retired(
        self,
        *,
        session_lease: LiveStartSessionLease,
        cursor: LiveStartSession,
    ) -> None:
        try:
            binding = _require_active_controller_apply_pair(self._lease_pair)
            persisted = live_start_session.load_live_start_session_under_lock(
                session_lease=session_lease
            )
            retirement = persisted.terminal_retirement
            intent = persisted.result_intent
            if (
                binding.session_lease is not session_lease
                or binding.profile_lease is not self._profile_lease
                or binding.runtime_admission is not self._runtime_admission
                or persisted != cursor
                or persisted.canonical_json != cursor.canonical_json
                or persisted.session_identity != cursor.session_identity
                or not isinstance(retirement, Mapping)
                or retirement.get("operation") != "release_not_committed"
                or retirement.get("stage") != "EVIDENCE_RETIRED"
                or not isinstance(intent, Mapping)
                or persisted.terminal_status != "FAILED_PRESERVED"
                or intent.get("terminal_status") != persisted.terminal_status
                or intent.get("physical_disposition") != "NOT_COMMITTED"
                or intent.get("runtime_match_status") != "not_run"
                or persisted.attempt_acknowledgement is not None
                or persisted.closed_apply_recovery_commitment is not None
                or any(
                    intent.get(name) is not None
                    for name in (
                        "retained_attempt_record_path",
                        "retained_journal_path",
                        "retained_target_owner_journal_path",
                    )
                )
            ):
                raise ValueError("cursor")
            current_admission = load_runtime_live_attempt_admission()
            if current_admission != self._runtime_admission:
                raise ValueError("admission")
            current_snapshot = capture_pre_apply_runtime_snapshot(
                runtime_root=self._runtime_admission.runtime_root,
                expected_runtime_root_identity=(
                    self._runtime_admission.runtime_root_identity
                ),
                deck_name=cursor.deck_name,
                state_key=_state_key(cursor.deck_name),
                profile_lease=self._profile_lease,
            )
            if (
                current_snapshot.canonical_json
                != self._invocation.pre_apply_runtime_snapshot.canonical_json
                or current_snapshot.content_sha256
                != self._invocation.pre_apply_runtime_snapshot.content_sha256
            ):
                raise ValueError("pre-apply snapshot")
            layout = persisted.runtime_layout_bootstrap
            if not isinstance(layout, Mapping):
                raise ValueError("layout")
            identities = _validated_complete_layout_successor_identities(
                layout=layout,
                runtime_root=self._runtime_admission.runtime_root,
            )
            _require_retained_child_absent(
                self._runtime_admission.retention_fence_path,
                expected_parent_identity=identities["attempt_retention"],
            )
            _require_retained_child_absent(
                self._runtime_admission.runtime_root
                / ".hsconfig"
                / "transactions"
                / f"{self._runtime_admission.apply_attempt_id}.json",
                expected_parent_identity=identities["transactions"],
            )
            _require_retained_child_absent(
                self._runtime_admission.runtime_root
                / ".hsconfig"
                / "staging"
                / self._runtime_admission.apply_attempt_id,
                expected_parent_identity=identities["staging"],
            )
            post = live_start_session.load_live_start_session_under_lock(
                session_lease=session_lease
            )
            if (
                post != persisted
                or post.canonical_json != persisted.canonical_json
                or post.session_identity != persisted.session_identity
                or load_runtime_live_attempt_admission()
                != self._runtime_admission
            ):
                raise ValueError("postcondition")
        except Exception as error:
            raise ValueError(
                "runtime_terminal_release_current_facts_changed"
            ) from error

    def acknowledge_after_terminal(
        self,
        *,
        session_lease: LiveStartSessionLease,
        expected_terminal_session: LiveStartSession,
    ) -> LiveStartSession:
        persisted = self._require_terminal_cursor(
            session_lease=session_lease,
            expected_terminal_session=expected_terminal_session,
            acknowledgement="required",
        )
        evidence = self._acknowledgement_evidence
        if evidence is None:
            raise live_start_session.SessionCapabilityError(
                "published_apply_acknowledgement_evidence_missing"
            )

        retirement = persisted.terminal_retirement
        if retirement is None:
            cursor = live_start_session.prepare_terminal_retirement_under_lock(
                session_lease=session_lease,
                expected_terminal_session=persisted,
                operation="ack_success",
                runtime_observation_receipt=None,
            )
            self._updated_session = cursor
            invoke_live_start_fault(
                self._fault_hook,
                LiveStartFaultPoint.AFTER_TERMINAL_RETIREMENT_PREPARED,
            )
            stage = "PREPARED"
        else:
            if (
                not isinstance(retirement, Mapping)
                or retirement.get("operation") != "ack_success"
            ):
                raise ValueError(
                    "held_apply_and_match_terminal_release_cursor_invalid"
                )
            cursor = persisted
            stage = retirement.get("stage")
        if evidence.journal_owns_target:
            evidence_actions: tuple[Literal["journal", "fence"], ...] = (
                ("fence",) if stage == "PREPARED" else ()
            )
            valid_stages = {
                "PREPARED",
                "EVIDENCE_RETIRED",
                "ADMISSION_RELEASE_AUTHORIZED",
            }
        else:
            evidence_actions = (
                ("journal", "fence")
                if stage == "PREPARED"
                else (("fence",) if stage == "ACK_JOURNAL_RETIRED" else ())
            )
            valid_stages = {
                "PREPARED",
                "ACK_JOURNAL_RETIRED",
                "EVIDENCE_RETIRED",
                "ADMISSION_RELEASE_AUTHORIZED",
            }
        if stage not in valid_stages:
            raise ValueError(
                "held_apply_and_match_terminal_release_cursor_invalid"
            )
        for action in evidence_actions:
            authorization = (
                live_start_session.authorize_terminal_retirement_under_lock(
                    session_lease=session_lease,
                    expected_retirement_session=cursor,
                )
            )
            step = _retire_success_attempt_evidence_step_from_pair(
                lease_pair=self._lease_pair,
                session_lease=session_lease,
                expected_retirement_session=cursor,
                terminal_authorization=authorization,
                transaction_id=evidence.apply_attempt_id,
                expected_retention_owner_run_id=evidence.retention_owner_run_id,
                expected_package_root_sha256=evidence.package_root_sha256,
                expected_retention_fence_path=evidence.retention_fence_path,
                expected_retention_fence_identity=(
                    evidence.retention_fence_identity
                ),
                expected_retention_fence_sha256=(
                    evidence.retention_fence_sha256
                ),
                expected_journal_path=evidence.journal_path,
                expected_journal_identity=evidence.journal_identity,
                expected_journal_sha256=evidence.journal_sha256,
                expected_target_owner_journal_path=(
                    evidence.target_owner_journal_path
                ),
                expected_target_owner_journal_identity=(
                    evidence.target_owner_journal_identity
                ),
                expected_target_owner_journal_sha256=(
                    evidence.target_owner_journal_sha256
                ),
                expected_target_path=evidence.target_path,
                expected_target_identity=evidence.target_identity,
                expected_runtime_admission_path=evidence.runtime_admission_path,
                expected_runtime_admission_parent_identity=(
                    evidence.runtime_admission_parent_identity
                ),
                expected_runtime_admission_identity=(
                    evidence.runtime_admission_identity
                ),
                expected_runtime_admission_sha256=(
                    evidence.runtime_admission_sha256
                ),
                action=action,
            )
            invoke_live_start_fault(
                self._fault_hook,
                (
                    LiveStartFaultPoint.AFTER_SUCCESS_ACK_JOURNAL_DELETE_BEFORE_STAGE_CAS
                    if action == "journal"
                    else LiveStartFaultPoint.AFTER_SUCCESS_ACK_FENCE_DELETE_BEFORE_EVIDENCE_CAS
                ),
            )
            if action == "fence":
                invoke_live_start_fault(
                    self._fault_hook,
                    LiveStartFaultPoint.AFTER_ATTEMPT_EVIDENCE_PHYSICAL_RETIREMENT_BEFORE_CAS,
                )
            cursor = live_start_session.advance_terminal_retirement_under_lock(
                session_lease=session_lease,
                expected_retirement_session=cursor,
                transition=(
                    "ack_journal_retired"
                    if action == "journal"
                    else "evidence_retired"
                ),
                terminal_authorization=None,
                physical_step_receipt=step.step_receipt,
            )
            self._updated_session = cursor
            invoke_live_start_fault(
                self._fault_hook,
                (
                    LiveStartFaultPoint.AFTER_SUCCESS_ACK_JOURNAL_RETIRED_CAS
                    if action == "journal"
                    else LiveStartFaultPoint.AFTER_SUCCESS_ACK_EVIDENCE_RETIRED_CAS
                ),
            )

        return self._release_runtime_admission_after_evidence_retired(
            session_lease=session_lease,
            cursor=cursor,
        )

    def _release_stable_non_success(
        self,
        *,
        session_lease: LiveStartSessionLease,
        expected_terminal_session: LiveStartSession,
        operation: Literal[
            "release_not_committed",
            "release_committed_mismatch",
        ],
    ) -> LiveStartSession:
        persisted = self._require_terminal_cursor(
            session_lease=session_lease,
            expected_terminal_session=expected_terminal_session,
            acknowledgement="forbidden",
        )
        if operation == "release_committed_mismatch":
            correct_result = (
                self._result.terminal_status == "APPLIED_BUT_NOT_VERIFIED"
                and self._result.physical_disposition
                is PhysicalApplyDisposition.COMMITTED
                and self._result.runtime_match_status == "mismatch"
            )
        else:
            correct_result = (
                self._result.terminal_status == "FAILED_PRESERVED"
                and self._result.physical_disposition
                is PhysicalApplyDisposition.NOT_COMMITTED
                and all(
                    value is None
                    for value in (
                        self._result.retained_attempt_record_path,
                        self._result.retained_journal_path,
                        self._result.retained_target_owner_journal_path,
                    )
                )
            )
        if not correct_result:
            raise ValueError("held_apply_and_match_terminal_release_invalid")
        retirement = persisted.terminal_retirement
        if retirement is None:
            cursor = live_start_session.prepare_terminal_retirement_under_lock(
                session_lease=session_lease,
                expected_terminal_session=persisted,
                operation=operation,
                runtime_observation_receipt=None,
            )
            self._updated_session = cursor
            invoke_live_start_fault(
                self._fault_hook,
                LiveStartFaultPoint.AFTER_TERMINAL_RETIREMENT_PREPARED,
            )
            stage = "PREPARED"
        else:
            if (
                not isinstance(retirement, Mapping)
                or retirement.get("operation") != operation
            ):
                raise ValueError(
                    "held_apply_and_match_terminal_release_cursor_invalid"
                )
            cursor = persisted
            stage = retirement.get("stage")
        if stage == "PREPARED":
            retirement_authorization = (
                live_start_session.authorize_terminal_retirement_under_lock(
                    session_lease=session_lease,
                    expected_retirement_session=cursor,
                )
            )
            cursor = live_start_session.advance_terminal_retirement_under_lock(
                session_lease=session_lease,
                expected_retirement_session=cursor,
                transition="evidence_retired",
                terminal_authorization=retirement_authorization,
                physical_step_receipt=None,
            )
            self._updated_session = cursor
        elif stage not in {
            "EVIDENCE_RETIRED",
            "ADMISSION_RELEASE_AUTHORIZED",
        }:
            raise ValueError(
                "held_apply_and_match_terminal_release_cursor_invalid"
            )
        return self._release_runtime_admission_after_evidence_retired(
            session_lease=session_lease,
            cursor=cursor,
        )

    def release_admission_after_terminal(
        self,
        *,
        session_lease: LiveStartSessionLease,
        expected_terminal_session: LiveStartSession,
    ) -> LiveStartSession:
        return self._release_stable_non_success(
            session_lease=session_lease,
            expected_terminal_session=expected_terminal_session,
            operation="release_not_committed",
        )

    def resolve_and_release_after_terminal(
        self,
        *,
        session_lease: LiveStartSessionLease,
        expected_terminal_session: LiveStartSession,
    ) -> LiveStartSession:
        if (
            self._result.physical_disposition
            is PhysicalApplyDisposition.COMMITTED
            and self._result.runtime_match_status == "mismatch"
        ):
            return self._release_stable_non_success(
                session_lease=session_lease,
                expected_terminal_session=expected_terminal_session,
                operation="release_committed_mismatch",
            )
        cursor = self._require_terminal_cursor(
            session_lease=session_lease,
            expected_terminal_session=expected_terminal_session,
            acknowledgement="forbidden",
        )
        intent = cursor.result_intent
        if not isinstance(intent, Mapping):
            raise live_start_session.SessionConflictError(
                "published_apply_terminal_result_intent_invalid"
            )
        has_historical_evidence = any(
            intent.get(field_name) is not None
            for field_name in (
                "retained_attempt_record_path",
                "retained_journal_path",
                "retained_candidate_identity",
            )
        )
        resolution_required = (
            self._result.terminal_status == "APPLIED_BUT_NOT_VERIFIED"
            and self._result.physical_disposition
            in {
                PhysicalApplyDisposition.COMMITTED_RECOVERY_PENDING,
                PhysicalApplyDisposition.UNKNOWN_REQUIRES_RECOVERY,
            }
        ) or (
            self._result.terminal_status == "FAILED_PRESERVED"
            and self._result.physical_disposition
            is PhysicalApplyDisposition.NOT_COMMITTED
            and has_historical_evidence
        )
        if not resolution_required:
            raise ValueError("held_apply_and_match_terminal_release_invalid")

        cleanup_inventory: TerminalResolutionCleanupInventory | None = None
        retirement = cursor.terminal_retirement
        if retirement is None:
            observation_authorization = (
                live_start_session._authorize_runtime_observation_under_lock(
                    session_lease=session_lease,
                    expected_session=cursor,
                    observation_family="terminal_resolution",
                    apply_attempt_id=self._runtime_admission.apply_attempt_id,
                )
            )
            observed = recover_runtime_attempt_from_pair(
                lease_pair=self._lease_pair,
                transaction_id=self._runtime_admission.apply_attempt_id,
                expected_retention_owner_run_id=(
                    self._runtime_admission.retention_owner_run_id
                ),
                expected_package_root_sha256=(
                    self._runtime_admission.package_root_sha256
                ),
                expected_deck_name=cursor.deck_name,
                runtime_admission=self._runtime_admission,
                observation_family="terminal_resolution",
                runtime_observation_authorization=(
                    observation_authorization
                ),
            )
            if observed.runtime_observation_receipt is None:
                raise ValueError(
                    "published_apply_terminal_observation_receipt_missing"
                )
            cleanup_inventory = observed.terminal_cleanup_inventory
            invoke_live_start_fault(
                self._fault_hook,
                LiveStartFaultPoint.AFTER_TERMINAL_RESOLUTION_OBSERVATION_BEFORE_PREPARE_CAS,
            )
            cursor = live_start_session.prepare_terminal_retirement_under_lock(
                session_lease=session_lease,
                expected_terminal_session=cursor,
                operation="release_resolved_terminal",
                runtime_observation_receipt=(
                    observed.runtime_observation_receipt
                ),
            )
            self._updated_session = cursor
            invoke_live_start_fault(
                self._fault_hook,
                LiveStartFaultPoint.AFTER_TERMINAL_RECOVERY_RESOLUTION_PREPARED,
            )
        elif (
            not isinstance(retirement, Mapping)
            or retirement.get("operation") != "release_resolved_terminal"
        ):
            raise ValueError("held_apply_and_match_terminal_release_cursor_invalid")

        while True:
            retirement = cursor.terminal_retirement
            if (
                not isinstance(retirement, Mapping)
                or retirement.get("operation") != "release_resolved_terminal"
            ):
                raise ValueError(
                    "held_apply_and_match_terminal_resolution_cursor_invalid"
                )
            stage = retirement.get("stage")
            if stage in {"EVIDENCE_RETIRED", "ADMISSION_RELEASE_AUTHORIZED"}:
                break
            resolution_value = retirement.get("terminal_resolution_evidence")
            if not isinstance(resolution_value, Mapping):
                raise ValueError(
                    "held_apply_and_match_terminal_resolution_missing"
                )
            if (
                stage == "RECOVERY_PREPARED"
                and resolution_value.get("cleanup_stage") == "PREPARED"
                and cleanup_inventory is None
            ):
                cleanup_inventory = (
                    reconstruct_runtime_no_commit_inventory_from_pair(
                        lease_pair=self._lease_pair,
                        transaction_id=self._runtime_admission.apply_attempt_id,
                        runtime_admission=self._runtime_admission,
                    )
                )
            elif stage in {
                "RECOVERY_INVENTORY_BOUND",
                "RECOVERY_CLEANING",
                "RECOVERY_JOURNAL_RETIRED",
                "RECOVERY_FENCE_RETIRED",
            } and resolution_value.get("cleanup_stage") is not None:
                inventory_path = Path(
                    str(resolution_value.get("cleanup_inventory_path"))
                )
                if not (
                    stage == "RECOVERY_FENCE_RETIRED"
                    and not os.path.lexists(inventory_path)
                ):
                    cleanup_inventory = (
                        load_bound_runtime_no_commit_inventory_from_pair(
                            lease_pair=self._lease_pair,
                            session_lease=session_lease,
                            expected_resolution_session=cursor,
                        )
                    )
            authorization = (
                live_start_session.authorize_terminal_retirement_under_lock(
                    session_lease=session_lease,
                    expected_retirement_session=cursor,
                )
            )
            action = authorization._opaque.action
            if action == "physical_recovery_advanced":
                physical = recover_runtime_attempt_from_pair(
                    lease_pair=self._lease_pair,
                    transaction_id=self._runtime_admission.apply_attempt_id,
                    expected_retention_owner_run_id=(
                        self._runtime_admission.retention_owner_run_id
                    ),
                    expected_package_root_sha256=(
                        self._runtime_admission.package_root_sha256
                    ),
                    expected_deck_name=cursor.deck_name,
                    runtime_admission=self._runtime_admission,
                    terminal_authorization=authorization,
                )
                if physical.terminal_resolution_step_receipt is None:
                    raise ValueError(
                        "published_apply_terminal_resolution_receipt_missing"
                    )
                invoke_live_start_fault(
                    self._fault_hook,
                    LiveStartFaultPoint.AFTER_TERMINAL_RECOVERY_METADATA_SUCCESSOR,
                )
                cursor = (
                    live_start_session.advance_terminal_resolution_under_lock(
                        session_lease=session_lease,
                        expected_resolution_session=cursor,
                        transition="physical_recovery_advanced",
                        resolved_evidence=None,
                        terminal_authorization=None,
                        physical_step_receipt=(
                            physical.terminal_resolution_step_receipt
                        ),
                    )
                )
            elif action in {
                "retire_cleanup_journal",
                "retire_cleanup_fence",
            }:
                metadata_action: Literal["journal", "fence"] = (
                    "journal"
                    if action == "retire_cleanup_journal"
                    else "fence"
                )
                step = retire_runtime_no_commit_metadata_from_pair(
                    lease_pair=self._lease_pair,
                    terminal_authorization=authorization,
                    action=metadata_action,
                    session_lease=session_lease,
                    expected_resolution_session=cursor,
                )
                invoke_live_start_fault(
                    self._fault_hook,
                    (
                        LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_JOURNAL_DELETE_BEFORE_STAGE_CAS
                        if metadata_action == "journal"
                        else LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_FENCE_DELETE_BEFORE_STAGE_CAS
                    ),
                )
                cursor = (
                    live_start_session.advance_terminal_resolution_under_lock(
                        session_lease=session_lease,
                        expected_resolution_session=cursor,
                        transition=(
                            "journal_retired"
                            if metadata_action == "journal"
                            else "fence_retired"
                        ),
                        resolved_evidence=None,
                        terminal_authorization=None,
                        physical_step_receipt=step.step_receipt,
                    )
                )
            elif action == "stabilized":
                resolved_evidence = (
                    _terminal_resolution_cleanup_stage_successor(
                        resolution_value,
                        expected_stage="INVENTORY_RETIRED",
                        successor_stage="COMPLETE",
                    )
                    if resolution_value.get("cleanup_stage")
                    == "INVENTORY_RETIRED"
                    else TerminalResolutionEvidence(resolution_value)
                )
                cursor = (
                    live_start_session.advance_terminal_resolution_under_lock(
                        session_lease=session_lease,
                        expected_resolution_session=cursor,
                        transition="stabilized",
                        resolved_evidence=resolved_evidence,
                        terminal_authorization=authorization,
                        physical_step_receipt=None,
                    )
                )
            elif action == "evidence_retired":
                cursor = live_start_session.advance_terminal_retirement_under_lock(
                    session_lease=session_lease,
                    expected_retirement_session=cursor,
                    transition="evidence_retired",
                    terminal_authorization=authorization,
                    physical_step_receipt=None,
                )
            elif action in {
                "materialize_terminal_cleanup_inventory_staging",
                "commit_bound_terminal_cleanup_inventory",
                "retire_unbound_terminal_cleanup_inventory_staging",
                "cleaning_started",
                "delete_cleanup_entry",
                "retire_cleanup_inventory",
            }:
                if action == "retire_unbound_terminal_cleanup_inventory_staging":
                    step = (
                        live_start_session.retire_terminal_cleanup_inventory_under_lock(
                            session_lease=session_lease,
                            expected_resolution_session=cursor,
                            terminal_authorization=authorization,
                            action="unbound_staging",
                        )
                    )
                    invoke_live_start_fault(
                        self._fault_hook,
                        LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_INVENTORY_UNBOUND_STAGING_RETIRE_BEFORE_CAS,
                    )
                    cursor = live_start_session.advance_terminal_resolution_under_lock(
                        session_lease=session_lease,
                        expected_resolution_session=cursor,
                        transition="cleanup_inventory_unbound_staging_retired",
                        resolved_evidence=None,
                        terminal_authorization=None,
                        physical_step_receipt=step.step_receipt,
                    )
                elif action == "cleaning_started":
                    cleaning_evidence = (
                        _terminal_resolution_cleanup_stage_successor(
                            resolution_value,
                            expected_stage="INVENTORY_BOUND",
                            successor_stage="CLEANING",
                        )
                    )
                    cursor = live_start_session.advance_terminal_resolution_under_lock(
                        session_lease=session_lease,
                        expected_resolution_session=cursor,
                        transition="cleaning_started",
                        resolved_evidence=cleaning_evidence,
                        terminal_authorization=authorization,
                        physical_step_receipt=None,
                    )
                elif action == "retire_cleanup_inventory":
                    step = (
                        live_start_session.retire_terminal_cleanup_inventory_under_lock(
                            session_lease=session_lease,
                            expected_resolution_session=cursor,
                            terminal_authorization=authorization,
                            action="final_sidecar",
                        )
                    )
                    invoke_live_start_fault(
                        self._fault_hook,
                        LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_SIDECAR_DELETE_BEFORE_STAGE_CAS,
                    )
                    cursor = live_start_session.advance_terminal_resolution_under_lock(
                        session_lease=session_lease,
                        expected_resolution_session=cursor,
                        transition="inventory_retired",
                        resolved_evidence=None,
                        terminal_authorization=None,
                        physical_step_receipt=step.step_receipt,
                    )
                else:
                    if cleanup_inventory is None:
                        raise ValueError(
                            "published_apply_terminal_cleanup_inventory_missing"
                        )
                    if action == "delete_cleanup_entry":
                        cleanup_cursor = resolution_value.get("cleanup_cursor")
                        if type(cleanup_cursor) is not int:
                            raise ValueError(
                                "published_apply_terminal_cleanup_cursor_invalid"
                            )
                        step = delete_runtime_no_commit_entry_from_pair(
                            lease_pair=self._lease_pair,
                            terminal_authorization=authorization,
                            inventory=cleanup_inventory,
                            expected_cursor=cleanup_cursor,
                            session_lease=session_lease,
                            expected_resolution_session=cursor,
                        )
                        invoke_live_start_fault(
                            self._fault_hook,
                            LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_ENTRY_DELETE_BEFORE_CURSOR_CAS,
                        )
                        cursor = live_start_session.advance_terminal_resolution_under_lock(
                            session_lease=session_lease,
                            expected_resolution_session=cursor,
                            transition="cleanup_cursor_advanced",
                            resolved_evidence=None,
                            terminal_authorization=None,
                            physical_step_receipt=step.step_receipt,
                        )
                    else:
                        publish_action: Literal["materialize", "commit"] = (
                            "materialize"
                            if action
                            == "materialize_terminal_cleanup_inventory_staging"
                            else "commit"
                        )
                        step = live_start_session.publish_terminal_cleanup_inventory_under_lock(
                            session_lease=session_lease,
                            expected_recovery_prepared_session=cursor,
                            terminal_authorization=authorization,
                            inventory=cleanup_inventory,
                            action=publish_action,
                        )
                        invoke_live_start_fault(
                            self._fault_hook,
                            (
                                LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_INVENTORY_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS
                                if publish_action == "materialize"
                                else LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_INVENTORY_BOUND_COMMIT_BEFORE_INVENTORY_BOUND_CAS
                            ),
                        )
                        cursor = live_start_session.advance_terminal_resolution_under_lock(
                            session_lease=session_lease,
                            expected_resolution_session=cursor,
                            transition=(
                                "cleanup_inventory_staging_bound"
                                if publish_action == "materialize"
                                else "inventory_bound"
                            ),
                            resolved_evidence=None,
                            terminal_authorization=None,
                            physical_step_receipt=step.step_receipt,
                        )
            else:
                raise ValueError(
                    "published_apply_terminal_resolution_action_invalid"
                )
            self._updated_session = cursor
            after_cas_point = {
                "materialize_terminal_cleanup_inventory_staging": (
                    LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_INVENTORY_STAGING_BOUND
                ),
                "commit_bound_terminal_cleanup_inventory": (
                    LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_INVENTORY_BOUND
                ),
                "cleaning_started": LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_STARTED,
                "delete_cleanup_entry": LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_CURSOR_CAS,
                "retire_cleanup_journal": LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_JOURNAL_RETIRED_CAS,
                "retire_cleanup_fence": LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_FENCE_RETIRED_CAS,
                "retire_cleanup_inventory": LiveStartFaultPoint.AFTER_TERMINAL_CLEANUP_INVENTORY_RETIRED_CAS,
                "stabilized": LiveStartFaultPoint.AFTER_TERMINAL_RECOVERY_STABILIZED,
            }.get(action)
            if after_cas_point is not None:
                invoke_live_start_fault(self._fault_hook, after_cas_point)

        return self._release_runtime_admission_after_evidence_retired(
            session_lease=session_lease,
            cursor=cursor,
        )

    def _expire(self) -> None:
        self._active = False


@dataclass(frozen=True, slots=True)
class HeldRecoveredApplyAndMatch:
    held: HeldApplyAndMatchPublished

    @property
    def updated_session(self) -> LiveStartSession:
        return self.held.updated_session


def _validate_held_token_context_after_yield(
    held: HeldApplyAndMatchPublished,
) -> None:
    if not held._active:
        raise live_start_session.SessionCapabilityError(
            "published_apply_held_context_expired"
        )
    pair = held._lease_pair
    binding = _authenticate_controller_apply_pair_binding(pair)
    if (
        binding.pair is not pair
        or binding.session_lease is not held._session_lease
        or binding.profile_lease is not held._profile_lease
        or binding.package_lease is not pair.package_lease
        or binding.runtime_lease is not pair.runtime_lease
        or binding.session_token is not held._session_lease.lock_token
        or binding.profile_token is not held._profile_lease.lock_token
        or binding.output_operation_token
        is not binding.output_operation_lease.lock_token
        or binding.package_token is not pair.package_lease.lock_token
        or binding.runtime_token is not pair.runtime_lease.lock_token
        or binding.runtime_admission is not held._runtime_admission
    ):
        raise live_start_session.SessionCapabilityError(
            "published_apply_held_context_changed"
        )
    live_start_session.load_live_start_session_under_lock(
        session_lease=held._session_lease
    )
    revalidate_operator_profile_lease(held._profile_lease)
    observe_output_operation_admission_under_lease(
        binding.output_operation_lease
    )
    revalidate_package_input_lease(pair.package_lease)
    _require_active_runtime_apply_lease(pair.runtime_lease)


@contextmanager
def _validated_held_yield(
    *,
    held: HeldApplyAndMatchPublished,
    exposed: HeldApplyAndMatchPublished | HeldRecoveredApplyAndMatch,
) -> Iterator[HeldApplyAndMatchPublished | HeldRecoveredApplyAndMatch]:
    try:
        yield exposed
    except BaseException as primary:
        try:
            _validate_held_token_context_after_yield(held)
        except BaseException as validation_error:
            primary.add_note(
                "held context validation failed: "
                f"{type(validation_error).__name__}: {validation_error}"
            )
        raise
    else:
        _validate_held_token_context_after_yield(held)
    finally:
        held._expire()


def _read_bound_run_document(
    *,
    session_lease: LiveStartSessionLease,
    session: LiveStartSession,
    logical_path: str,
    maximum_size: int,
) -> Mapping[str, Any]:
    path = session_lease.session_root / logical_path
    raw, _identity = live_start_session._read_bound_file(
        path,
        expected_parent_identity=path_identity(path.parent),
        maximum_size=maximum_size,
    )
    if (
        "sha256:" + hashlib.sha256(raw).hexdigest()
        != session.artifact_bindings.get(logical_path)
    ):
        raise live_start_session.SessionConflictError(
            "published_apply_result_authority_drift"
        )
    document = FrozenJsonDocument.from_json_bytes(raw)
    value = document.to_value()
    if not isinstance(value, Mapping):
        raise live_start_session.SessionValidationError(
            "published_apply_result_authority_invalid"
        )
    return value


def _result_presentation_authority(
    *,
    session_lease: LiveStartSessionLease,
    session: LiveStartSession,
) -> tuple[int, int, int, Literal["high", "limited"]]:
    unique_cards = live_start_session._frozen_main_roster_count_under_lock(
        session_lease=session_lease,
        session_value=session,
    )
    candidate = _read_bound_run_document(
        session_lease=session_lease,
        session=session,
        logical_path="starter/starter_config_candidate.json",
        maximum_size=STARTER_CANDIDATE_MAX_BYTES,
    )
    dispositions = candidate.get("card_dispositions")
    if (
        candidate.get("candidate_revision") != session.candidate_revision
        or not isinstance(dispositions, list)
        or len(dispositions) != unique_cards
    ):
        raise live_start_session.SessionValidationError(
            "published_apply_result_coverage_authority_invalid"
        )
    seen_cards: set[str] = set()
    configured_cards = 0
    deliberately_unconfigured_cards = 0
    for row in dispositions:
        if not isinstance(row, Mapping):
            raise live_start_session.SessionValidationError(
                "published_apply_result_coverage_authority_invalid"
            )
        card_id = row.get("card_id")
        disposition = row.get("disposition")
        if (
            not isinstance(card_id, str)
            or not card_id
            or card_id in seen_cards
            or disposition
            not in {"configured", "deliberately_unconfigured"}
        ):
            raise live_start_session.SessionValidationError(
                "published_apply_result_coverage_authority_invalid"
            )
        seen_cards.add(card_id)
        if disposition == "configured":
            configured_cards += 1
        else:
            deliberately_unconfigured_cards += 1
    if configured_cards + deliberately_unconfigured_cards != unique_cards:
        raise live_start_session.SessionValidationError(
            "published_apply_result_coverage_authority_invalid"
        )

    review = _read_bound_run_document(
        session_lease=session_lease,
        session=session,
        logical_path="receipts/review_validation.json",
        maximum_size=256 * 1024,
    )
    validated_review = live_start_session.validate_validation_receipt(
        receipt_kind="review_validation",
        value=review,
        run_id=session.run_id,
        candidate_revision=session.candidate_revision,
    )
    confidence = validated_review.get("confidence")
    if confidence not in {"high", "limited"}:
        raise live_start_session.SessionValidationError(
            "published_apply_result_review_authority_invalid"
        )
    return (
        unique_cards,
        configured_cards,
        deliberately_unconfigured_cards,
        cast(Literal["high", "limited"], confidence),
    )


def _sealed_result_intent_from_held(
    *,
    session_lease: LiveStartSessionLease,
    held: HeldApplyAndMatchPublished,
) -> Mapping[str, Any]:
    cursor = held.updated_session
    recovery = cursor.apply_recovery
    publication = cursor.publication_binding
    if (
        not isinstance(recovery, Mapping)
        or recovery.get("recovery_stage") != "CLOSED"
        or not isinstance(publication, Mapping)
    ):
        raise live_start_session.SessionConflictError(
            "published_apply_result_cursor_invalid"
        )
    result = held.result
    runtime_admission = held.runtime_admission_evidence
    (
        unique_cards,
        configured_cards,
        deliberately_unconfigured_cards,
        review_confidence,
    ) = _result_presentation_authority(
        session_lease=session_lease,
        session=cursor,
    )
    if result.runtime_match_status == "matched":
        retained_safe_state = "ACTIVE_RUNTIME_MATCHED"
    elif result.physical_disposition is PhysicalApplyDisposition.NOT_COMMITTED:
        retained_safe_state = "PREVIOUS_RUNTIME_UNCHANGED"
    else:
        retained_safe_state = "ATTEMPT_EVIDENCE_RETAINED"

    def optional_path(value: Path | None) -> str | None:
        return None if value is None else str(value)

    def optional_identity(value: PathIdentity | None) -> list[int] | None:
        return None if value is None else list(value)

    return live_start_session.seal_embedded_document(
        "result_intent",
        {
            "schema_version": 1,
            "intent_kind": live_start_session.LIVE_START_RESULT_INTENT_KIND,
            "run_id": cursor.run_id,
            "terminal_status": result.terminal_status,
            "deck_name": cursor.deck_name,
            "candidate_revision": cursor.candidate_revision,
            "unique_main_deck_cards": unique_cards,
            "configured_cards": configured_cards,
            "deliberately_unconfigured_cards": (
                deliberately_unconfigured_cards
            ),
            "review_confidence": review_confidence,
            "visible_limitations": [],
            "apply_attempt_id": held.invocation.apply_attempt_id,
            "publication_revision": publication["revision"],
            "publication_content_root_sha256": publication[
                "content_root_sha256"
            ],
            "raw_apply_status": result.raw_apply_status,
            "physical_disposition": result.physical_disposition.value,
            "runtime_match_status": result.runtime_match_status,
            "runtime_match_sha256": result.runtime_match_sha256,
            "package_root_sha256": result.package_root_sha256,
            "last_apply_receipt_sha256": result.last_apply_receipt_sha256,
            "runtime_state_sha256": result.runtime_state_sha256,
            "deck_config_ini_sha256": result.deck_config_ini_sha256,
            "retained_attempt_record_path": optional_path(
                result.retained_attempt_record_path
            ),
            "retained_attempt_record_identity": optional_identity(
                result.retained_attempt_record_identity
            ),
            "retained_attempt_record_sha256": (
                result.retained_attempt_record_sha256
            ),
            "retained_journal_path": optional_path(
                result.retained_journal_path
            ),
            "retained_journal_identity": optional_identity(
                result.retained_journal_identity
            ),
            "retained_journal_sha256": result.retained_journal_sha256,
            "retained_target_owner_journal_path": optional_path(
                result.retained_target_owner_journal_path
            ),
            "retained_target_owner_journal_identity": optional_identity(
                result.retained_target_owner_journal_identity
            ),
            "retained_target_owner_journal_sha256": (
                result.retained_target_owner_journal_sha256
            ),
            "retained_candidate_identity": recovery.get(
                "predecessor_candidate_identity"
            )
            if result.physical_disposition
            is PhysicalApplyDisposition.NOT_COMMITTED
            else None,
            "runtime_admission_path": str(
                runtime_admission.admission_path
            ),
            "runtime_admission_parent_identity": list(
                runtime_admission.admission_parent_identity
            ),
            "runtime_admission_identity": list(
                runtime_admission.admission_identity
            ),
            "runtime_admission_sha256": (
                runtime_admission.admission_sha256
            ),
            "error_code": result.error_code,
            "retained_safe_state": retained_safe_state,
        },
    )


def _terminalize_held_recovery_result(
    *,
    session_lease: LiveStartSessionLease,
    held: HeldApplyAndMatchPublished,
) -> LiveStartSession:
    cursor = held.updated_session
    intent = _sealed_result_intent_from_held(
        session_lease=session_lease,
        held=held,
    )
    evidence = held.acknowledgement_evidence
    acknowledgement = (
        None
        if evidence is None
        else _sealed_attempt_acknowledgement(
            run_id=cursor.run_id,
            evidence=evidence,
        )
    )
    cursor = live_start_session.bind_result_intent_under_lock(
        session_lease=session_lease,
        expected_session=cursor,
        result_intent=intent,
        attempt_acknowledgement=acknowledgement,
    )
    return live_start_session.complete_live_start_under_lock(
        session_lease=session_lease,
        expected_result_session=cursor,
    )


def _require_entry_context(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    output_operation_admission: OutputOperationAdmissionEvidence,
    output_root: Path,
    publication_content_root_sha256: str,
    runtime_root: Path,
) -> OutputOperationAdmissionEvidence:
    if (
        not isinstance(session_lease, LiveStartSessionLease)
        or not isinstance(expected_session, LiveStartSession)
        or not isinstance(profile_lease, OperatorProfileLease)
        or not isinstance(output_operation_lease, OutputOperationAdmissionLease)
        or type(output_operation_admission) is not OutputOperationAdmissionEvidence
        or not isinstance(output_root, Path)
        or not isinstance(runtime_root, Path)
    ):
        raise TypeError("published_apply_context_invalid")
    persisted = live_start_session.load_live_start_session_under_lock(
        session_lease=session_lease
    )
    publication = persisted.publication_binding
    operation = persisted.output_operation_admission_binding
    profile = revalidate_operator_profile_lease(profile_lease)
    observed = observe_output_operation_admission_under_lease(
        output_operation_lease
    )
    operation_evidence_matches = (
        observed is not None
        and replace(
            observed,
            admission_sha256=output_operation_admission.admission_sha256,
        )
        == output_operation_admission
        and _admission_raw_sha256(observed)
        == output_operation_admission.admission_sha256
        and isinstance(operation, Mapping)
        and operation.get("admission_sha256")
        == output_operation_admission.admission_sha256
    )
    violations = [
        name
        for name, invalid in (
            ("session", persisted != expected_session),
            (
                "session_bytes",
                persisted.canonical_json != expected_session.canonical_json,
            ),
            ("phase", persisted.phase is not LiveStartPhase.PUBLICATION_COMMITTED),
            ("pending", persisted.pending_transition is not None),
            ("preview", persisted.preview_requested),
            ("publication", not isinstance(publication, Mapping)),
            ("operation", not isinstance(operation, Mapping)),
            (
                "operation_state",
                not isinstance(operation, Mapping)
                or operation.get("state") != "ACTIVE",
            ),
            ("operation_evidence", not operation_evidence_matches),
            (
                "operation_session",
                output_operation_admission.session_root
                != session_lease.session_root,
            ),
            (
                "operation_profile",
                output_operation_admission.operator_profile_sha256
                != profile.content_sha256,
            ),
            (
                "output_root",
                not isinstance(publication, Mapping)
                or Path(str(publication.get("output_child_path")))
                != output_root,
            ),
            (
                "publication_digest",
                not isinstance(publication, Mapping)
                or publication.get("content_root_sha256")
                != publication_content_root_sha256,
            ),
            ("runtime_root", profile.runtime_root != runtime_root),
        )
        if invalid
    ]
    if violations:
        raise live_start_session.SessionConflictError(
            "published_apply_context_changed:" + ",".join(violations)
        )
    if observed is None:
        raise live_start_session.SessionConflictError(
            "published_apply_output_operation_admission_missing"
        )
    return observed


def _semantic_historical_output_operation_evidence(
    *,
    evidence: OutputOperationAdmissionEvidence,
    profile_lease: OperatorProfileLease,
    expected_session: LiveStartSession,
) -> OutputOperationAdmissionEvidence:
    """Adapt the sealed raw-file digest to the observer self-digest form."""

    operation = expected_session.output_operation_admission_binding
    if not isinstance(operation, Mapping):
        raise ValueError("published_apply_output_operation_binding_missing")
    rebuilt = build_output_operation_admission_bytes(
        run_id=evidence.run_id,
        session_root=evidence.session_root,
        session_root_identity=evidence.session_root_identity,
        expected_session_sha256=evidence.expected_session_sha256,
        operator_profile=profile_lease.profile,
        operator_profile_path=evidence.operator_profile_path,
        operator_profile_parent_identity=(
            evidence.operator_profile_parent_identity
        ),
        operator_profile_identity=evidence.operator_profile_identity,
        state_root_identity=evidence.state_root_identity,
        output_base_root=evidence.output_base_root,
        output_base_root_identity=evidence.output_base_root_identity,
        output_child_path=evidence.output_child_path,
        output_child_predecessor_state=(
            evidence.output_child_predecessor_state
        ),
        output_child_predecessor_identity=(
            evidence.output_child_predecessor_identity
        ),
        output_bootstrap_lock_path=evidence.output_bootstrap_lock_path,
        output_bootstrap_lock_identity=evidence.output_bootstrap_lock_identity,
        output_claim_path=evidence.output_claim_path,
    )
    raw_sha256 = "sha256:" + hashlib.sha256(rebuilt).hexdigest()
    document = json.loads(rebuilt)
    content_sha256 = document.get("content_sha256")
    if (
        len(rebuilt) != evidence.admission_size
        or evidence.admission_sha256 != raw_sha256
        or operation.get("admission_sha256") != raw_sha256
        or not isinstance(content_sha256, str)
    ):
        raise ValueError("published_apply_output_operation_binding_changed")
    return replace(evidence, admission_sha256=content_sha256)


def _require_package_binding(
    *,
    package_lease: PackageInputLease,
    expected_session: LiveStartSession,
    output_root: Path,
    publication_content_root_sha256: str,
) -> None:
    revalidate_package_input_lease(package_lease)
    publication = expected_session.publication_binding
    child = expected_session.output_child_binding
    if (
        not isinstance(publication, Mapping)
        or not isinstance(child, Mapping)
        or package_lease.publication is None
        or package_lease.snapshot is None
        or package_lease.output_root != output_root
        or package_lease.output_root != Path(str(publication["output_child_path"]))
        or path_identity(output_root) != tuple(child["output_child_identity"])
        or package_lease.publication.revision != publication["revision"]
        or "sha256:" + str(package_lease.content_root_sha256)
        != publication_content_root_sha256
        or package_lease.package_root
        != output_root / str(publication["revision"]) / "04_package"
    ):
        raise ValueError("published_apply_package_binding_changed")


def _build_apply_authority(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_admission: OutputOperationAdmissionEvidence,
    package_lease: PackageInputLease,
    lease_pair: ControllerApplyLeasePair,
    runtime_root: Path,
    apply_attempt_id: str,
) -> tuple[ApplyInvocation, bytes, Path, Path, Path, str]:
    publication = expected_session.publication_binding
    child = expected_session.output_child_binding
    operation = expected_session.output_operation_admission_binding
    if not isinstance(publication, Mapping):
        raise live_start_session.SessionCapabilityError(
            "published_apply_publication_binding_missing"
        )
    if not isinstance(child, Mapping):
        raise live_start_session.SessionCapabilityError(
            "published_apply_output_child_binding_missing"
        )
    if not isinstance(operation, Mapping):
        raise live_start_session.SessionCapabilityError(
            "published_apply_output_operation_binding_missing"
        )
    inventory_sha256 = _runtime_inventory_sha256(runtime_root)
    snapshot = capture_pre_apply_runtime_snapshot(
        runtime_root=runtime_root,
        expected_runtime_root_identity=lease_pair.runtime_lease.runtime_root_identity,
        deck_name=expected_session.deck_name,
        state_key=_state_key(expected_session.deck_name),
        profile_lease=profile_lease,
    )
    if _runtime_inventory_sha256(runtime_root) != inventory_sha256:
        raise ValueError("pre_apply_runtime_inventory_changed")
    invocation = build_apply_invocation(
        apply_attempt_id=apply_attempt_id,
        run_id=expected_session.run_id,
        publication_revision=str(publication["revision"]),
        publication_content_root_sha256=str(
            publication["content_root_sha256"]
        ),
        output_operation_admission_path=(
            output_operation_admission.admission_path
        ),
        output_operation_admission_identity=(
            output_operation_admission.admission_identity
        ),
        output_operation_admission_sha256=str(operation["admission_sha256"]),
        output_child_binding_sha256=str(child["content_sha256"]),
        output_child_path=package_lease.output_root,
        output_child_identity=tuple(child["output_child_identity"]),
        operator_profile_sha256=profile_lease.profile.content_sha256,
        runtime_root=runtime_root,
        runtime_root_identity=lease_pair.runtime_lease.runtime_root_identity,
        pre_apply_runtime_snapshot=snapshot,
    )
    require_apply_invocation_admission_capacity(invocation)
    admission_path = runtime_live_attempt_admission_path()
    admission_staging_path = admission_path.with_name(
        ".live-start-active-attempt."
        f"{expected_session.run_id}.{apply_attempt_id}.staged"
    )
    admission_inner_temp_path = admission_staging_path.with_name(
        f".{admission_staging_path.name}.live-start-atomic.tmp"
    )
    admission_raw = build_runtime_live_attempt_admission_bytes(
        run_id=expected_session.run_id,
        apply_attempt_id=apply_attempt_id,
        retention_owner_run_id=expected_session.run_id,
        session_root=session_lease.session_root,
        session_root_identity=session_lease.session_root_identity,
        operator_profile_sha256=profile_lease.profile.content_sha256,
        state_root_identity=output_operation_admission.state_root_identity,
        runtime_root=runtime_root,
        runtime_root_identity=lease_pair.runtime_lease.runtime_root_identity,
        output_base_root=profile_lease.profile.output_base_root,
        output_base_root_identity=(
            profile_lease.profile.output_base_root_identity
        ),
        output_root=package_lease.output_root,
        output_root_identity=tuple(child["output_child_identity"]),
        output_operation_admission_path=(
            output_operation_admission.admission_path
        ),
        output_operation_admission_identity=(
            output_operation_admission.admission_identity
        ),
        output_operation_admission_sha256=str(operation["admission_sha256"]),
        output_child_binding_sha256=str(child["content_sha256"]),
        publication_revision=str(publication["revision"]),
        publication_content_root_sha256=str(
            publication["content_root_sha256"]
        ),
        package_root_sha256=str(publication["content_root_sha256"]),
        pre_apply_runtime_snapshot_sha256=snapshot.content_sha256,
        apply_invocation_sha256=invocation.content_sha256,
        retention_fence_path=(
            runtime_root
            / ".hsconfig"
            / "attempt-retention"
            / f"{apply_attempt_id}.json"
        ),
    )
    return (
        invocation,
        admission_raw,
        admission_path,
        admission_staging_path,
        admission_inner_temp_path,
        inventory_sha256,
    )


def _require_recovery_invocation_context(
    *,
    lease_pair: ControllerApplyLeasePair,
    session_lease: LiveStartSessionLease,
    cursor: LiveStartSession,
    profile_lease: OperatorProfileLease,
    historical: OutputOperationAdmissionEvidence,
    package_lease: PackageInputLease,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    invocation: ApplyInvocation,
) -> None:
    binding = _require_active_controller_apply_pair(lease_pair)
    persisted = live_start_session.load_live_start_session_under_lock(
        session_lease=session_lease
    )
    revalidate_operator_profile_lease(profile_lease)
    revalidate_package_input_lease(package_lease)
    publication = cursor.publication_binding
    child = cursor.output_child_binding
    operation = cursor.output_operation_admission_binding
    pending = cursor.pending_transition
    expected_invocation_sha256 = cursor.apply_invocation_sha256
    if expected_invocation_sha256 is None and isinstance(pending, Mapping):
        expected_invocation_sha256 = pending.get("apply_invocation_sha256")
    raw_invocation_sha256 = (
        "sha256:" + hashlib.sha256(invocation.canonical_json).hexdigest()
    )
    artifact_sha256 = cursor.artifact_bindings.get(
        "receipts/apply_invocation.json"
    )
    artifact_binding_valid = (
        artifact_sha256 == raw_invocation_sha256
        if cursor.apply_invocation_sha256 is not None
        else artifact_sha256 is None
    )
    if (
        binding.session_lease is not session_lease
        or binding.profile_lease is not profile_lease
        or binding.package_lease is not package_lease
        or binding.runtime_admission is not runtime_admission
        or persisted != cursor
        or persisted.canonical_json != cursor.canonical_json
        or persisted.session_identity != cursor.session_identity
        or not isinstance(publication, Mapping)
        or not isinstance(child, Mapping)
        or not isinstance(operation, Mapping)
        or package_lease.publication is None
        or package_lease.snapshot is None
        or invocation.content_sha256 != expected_invocation_sha256
        or not artifact_binding_valid
        or invocation.run_id != cursor.run_id
        or invocation.apply_attempt_id != runtime_admission.apply_attempt_id
        or runtime_admission.run_id != cursor.run_id
        or runtime_admission.session_root != session_lease.session_root
        or runtime_admission.session_root_identity
        != session_lease.session_root_identity
        or invocation.publication_revision != publication.get("revision")
        or invocation.publication_revision
        != runtime_admission.publication_revision
        or invocation.publication_revision
        != package_lease.publication.revision
        or invocation.publication_content_root_sha256
        != publication.get("content_root_sha256")
        or invocation.publication_content_root_sha256
        != runtime_admission.publication_content_root_sha256
        or invocation.publication_content_root_sha256
        != runtime_admission.package_root_sha256
        or invocation.publication_content_root_sha256
        != "sha256:" + str(package_lease.content_root_sha256)
        or invocation.output_operation_admission_path
        != historical.admission_path
        or invocation.output_operation_admission_path
        != runtime_admission.output_operation_admission_path
        or str(invocation.output_operation_admission_path)
        != operation.get("admission_path")
        or invocation.output_operation_admission_identity
        != historical.admission_identity
        or invocation.output_operation_admission_identity
        != runtime_admission.output_operation_admission_identity
        or tuple(operation.get("admission_identity", ()))
        != invocation.output_operation_admission_identity
        or invocation.output_operation_admission_sha256
        != operation.get("admission_sha256")
        or invocation.output_operation_admission_sha256
        != runtime_admission.output_operation_admission_sha256
        or invocation.output_child_binding_sha256 != child.get("content_sha256")
        or invocation.output_child_binding_sha256
        != runtime_admission.output_child_binding_sha256
        or invocation.output_child_path != package_lease.output_root
        or invocation.output_child_path != runtime_admission.output_root
        or str(invocation.output_child_path) != child.get("output_child_path")
        or invocation.output_child_identity
        != tuple(child.get("output_child_identity", ()))
        or invocation.output_child_identity != runtime_admission.output_root_identity
        or invocation.operator_profile_sha256
        != profile_lease.profile.content_sha256
        or invocation.operator_profile_sha256
        != runtime_admission.operator_profile_sha256
        or invocation.runtime_root != runtime_admission.runtime_root
        or invocation.runtime_root_identity
        != runtime_admission.runtime_root_identity
        or invocation.pre_apply_runtime_snapshot.content_sha256
        != runtime_admission.pre_apply_runtime_snapshot_sha256
        or runtime_admission.apply_invocation_sha256
        != invocation.content_sha256
    ):
        raise live_start_session.SessionCapabilityError(
            "published_apply_recovery_invocation_context_invalid"
        )


def _claim_runtime_admission(
    *,
    lease_pair: ControllerApplyLeasePair,
    session_lease: LiveStartSessionLease,
    cursor: LiveStartSession,
    invocation: ApplyInvocation,
    admission_raw: bytes,
    admission_path: Path,
    admission_staging_path: Path,
    admission_inner_temp_path: Path,
    profile_lease: OperatorProfileLease,
    runtime_inventory_sha256: str,
    fault_hook: LiveStartFaultHook,
) -> tuple[LiveStartSession, RuntimeLiveAttemptAdmissionEvidence]:
    if (
        _runtime_inventory_sha256(invocation.runtime_root)
        != runtime_inventory_sha256
    ):
        raise ValueError("pre_apply_runtime_inventory_changed")
    admission_sha256 = "sha256:" + hashlib.sha256(admission_raw).hexdigest()
    pending = cursor.pending_transition
    if pending is None:
        cursor = live_start_session.prepare_apply_attempt_under_lock(
            session_lease=session_lease,
            expected_session=cursor,
            invocation=invocation,
            planned_admission_path=admission_path,
            planned_admission_staging_path=admission_staging_path,
            planned_admission_staging_inner_temp_path=admission_inner_temp_path,
            planned_admission_parent_identity=(
                profile_lease.profile_parent_identity
            ),
            planned_admission_document_size=len(admission_raw),
            planned_admission_document_sha256=admission_sha256,
        )
        invoke_live_start_fault(
            fault_hook,
            LiveStartFaultPoint.AFTER_INVOCATION_PREPARED_BEFORE_ADMISSION,
        )
        actions = (
            ("materialize_runtime_admission_staging", "staging_bound"),
            ("commit_bound_runtime_admission", "admission_primary_applied"),
        )
    elif (
        isinstance(pending, Mapping)
        and pending.get("operation") == "install_apply_invocation"
        and pending.get("stage") == "STAGING_BOUND"
        and pending.get("apply_attempt_id") == invocation.apply_attempt_id
        and pending.get("apply_invocation_sha256") == invocation.content_sha256
        and pending.get("runtime_admission_path") == str(admission_path)
        and pending.get("runtime_admission_staging_path")
        == str(admission_staging_path)
        and pending.get("runtime_admission_staging_inner_temp_path")
        == str(admission_inner_temp_path)
        and tuple(pending.get("runtime_admission_parent_identity", ()))
        == profile_lease.profile_parent_identity
        and pending.get("runtime_admission_document_size")
        == len(admission_raw)
        and pending.get("runtime_admission_document_sha256")
        == admission_sha256
    ):
        actions = (
            ("commit_bound_runtime_admission", "admission_primary_applied"),
        )
    else:
        raise live_start_session.SessionConflictError(
            "published_apply_runtime_admission_cursor_invalid"
        )
    for action, transition in actions:
        authorization = (
            live_start_session._authorize_runtime_admission_under_lock(
                session_lease=session_lease,
                expected_admission_session=cursor,
                action=action,
            )
        )
        receipt = _execute_runtime_admission_file_action_from_pair(
            lease_pair=lease_pair,
            session_lease=session_lease,
            expected_session=cursor,
            admission_authorization=authorization,
            payload=admission_raw,
            fault_hook=fault_hook,
        )
        if action == "materialize_runtime_admission_staging":
            invoke_live_start_fault(
                fault_hook,
                LiveStartFaultPoint.AFTER_RUNTIME_ADMISSION_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS,
            )
        else:
            invoke_live_start_fault(
                fault_hook,
                LiveStartFaultPoint.AFTER_RUNTIME_ADMISSION_BOUND_COMMIT_BEFORE_CAS,
            )
        cursor = live_start_session.advance_runtime_admission_under_lock(
            session_lease=session_lease,
            expected_admission_session=cursor,
            transition=transition,
            physical_step_receipt=receipt,
        )
        if transition == "staging_bound":
            invoke_live_start_fault(
                fault_hook,
                LiveStartFaultPoint.AFTER_RUNTIME_ADMISSION_STAGING_BOUND,
            )
    pair_binding = _authenticate_controller_apply_pair_binding(lease_pair)
    runtime_admission = pair_binding.runtime_admission
    if runtime_admission is None:
        runtime_admission = load_runtime_live_attempt_admission()
    if runtime_admission is None:
        raise ValueError("published_apply_runtime_admission_missing")
    _bind_controller_apply_pair_runtime_admission(
        lease_pair=lease_pair,
        session_lease=session_lease,
        expected_session=cursor,
        runtime_admission=runtime_admission,
    )
    return cursor, runtime_admission


def _complete_layout_and_receipt(
    *,
    prepared: PreparedPackageInstall,
    lease_pair: ControllerApplyLeasePair,
    session_lease: LiveStartSessionLease,
    cursor: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    output_operation_admission: OutputOperationAdmissionEvidence,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    invocation: ApplyInvocation,
    fault_hook: LiveStartFaultHook,
) -> LiveStartSession:
    resumed_layout = cursor.runtime_layout_bootstrap is not None
    if not resumed_layout:
        cursor = live_start_session.prepare_runtime_layout_bootstrap_under_lock(
            session_lease=session_lease,
            expected_admission_committed_session=cursor,
            layout_evidence=prepared.runtime_layout_evidence,
        )
        invoke_live_start_fault(
            fault_hook,
            LiveStartFaultPoint.AFTER_RUNTIME_LAYOUT_INTENT,
        )
    elif cursor.runtime_layout_bootstrap != prepared.runtime_layout_evidence.value:
        raise live_start_session.SessionConflictError(
            "published_apply_runtime_layout_cursor_invalid"
        )
    while True:
        layout = cursor.runtime_layout_bootstrap
        if not isinstance(layout, Mapping):
            raise live_start_session.SessionConflictError(
                "published_apply_runtime_layout_cursor_invalid"
            )
        if layout.get("stage") == "COMPLETE":
            break
        if layout.get("stage") != "INCOMPLETE":
            raise live_start_session.SessionConflictError(
                "published_apply_runtime_layout_cursor_invalid"
            )
        authorization = (
            live_start_session._authorize_runtime_layout_bootstrap_under_lock(
                session_lease=session_lease,
                expected_layout_session=cursor,
                action="create_or_confirm_runtime_layout_directory",
            )
        )
        receipt = bootstrap_runtime_layout_directory_from_pair(
            lease_pair=lease_pair,
            session_lease=session_lease,
            expected_layout_session=cursor,
            profile_lease=profile_lease,
            output_operation_lease=output_operation_lease,
            output_operation_admission=output_operation_admission,
            runtime_admission=runtime_admission,
            layout_authorization=authorization,
        )
        invoke_live_start_fault(
            fault_hook,
            LiveStartFaultPoint.AFTER_RUNTIME_LAYOUT_DIRECTORY_CREATE_BEFORE_RECEIPT_CAS,
        )
        cursor = live_start_session.advance_runtime_layout_bootstrap_under_lock(
            session_lease=session_lease,
            expected_layout_session=cursor,
            transition="directory_bound",
            physical_step_receipt=receipt,
        )
        invoke_live_start_fault(
            fault_hook,
            LiveStartFaultPoint.AFTER_RUNTIME_LAYOUT_DIRECTORY_BOUND,
        )
    _validated_complete_layout_successor_identities(
        layout=layout,
        runtime_root=invocation.runtime_root,
    )
    retire_unbound_receipt = resumed_layout
    while True:
        pending = cursor.pending_transition
        if not isinstance(pending, Mapping):
            raise live_start_session.SessionConflictError(
                "published_apply_invocation_receipt_cursor_invalid"
            )
        external = pending.get("external_file_action")
        if external is None:
            if pending.get("next_action_index") != 1:
                raise live_start_session.SessionConflictError(
                    "published_apply_invocation_receipt_cursor_invalid"
                )
            break
        if not isinstance(external, Mapping):
            raise live_start_session.SessionConflictError(
                "published_apply_invocation_receipt_cursor_invalid"
            )
        external_stage = external.get("stage")
        external_action = external.get("action_kind")
        if (
            external_stage == "PLANNED"
            and external_action == "materialize_invocation_receipt_staging"
        ):
            if retire_unbound_receipt:
                action = "retire_unbound_invocation_receipt_staging"
                transition = "invocation_receipt_unbound_staging_retired"
                retire_unbound_receipt = False
            else:
                action = "materialize_invocation_receipt_staging"
                transition = "invocation_receipt_staging_bound"
        elif (
            external_stage == "STAGING_BOUND"
            and external_action == "commit_bound_invocation_receipt"
        ):
            action = "commit_bound_invocation_receipt"
            transition = "invocation_receipt_committed"
        else:
            raise live_start_session.SessionConflictError(
                "published_apply_invocation_receipt_cursor_invalid"
            )
        authorization = (
            live_start_session._authorize_runtime_admission_under_lock(
                session_lease=session_lease,
                expected_admission_session=cursor,
                action=action,
            )
        )
        receipt = _execute_runtime_admission_file_action_from_pair(
            lease_pair=lease_pair,
            session_lease=session_lease,
            expected_session=cursor,
            admission_authorization=authorization,
            payload=invocation.canonical_json,
        )
        if action != "retire_unbound_invocation_receipt_staging":
            invoke_live_start_fault(
                fault_hook,
                (
                    LiveStartFaultPoint.AFTER_INVOCATION_RECEIPT_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS
                    if action == "materialize_invocation_receipt_staging"
                    else LiveStartFaultPoint.AFTER_INVOCATION_RECEIPT_BOUND_COMMIT_BEFORE_CAS
                ),
            )
        cursor = live_start_session.advance_runtime_admission_under_lock(
            session_lease=session_lease,
            expected_admission_session=cursor,
            transition=transition,
            physical_step_receipt=receipt,
        )
    return _complete_apply_started_from_context(
        session_lease=session_lease,
        expected_receipt_committed_session=cursor,
        profile_lease=profile_lease,
        output_operation_lease=output_operation_lease,
        output_operation_admission=output_operation_admission,
        lease_pair=lease_pair,
        invocation=invocation,
        runtime_admission=runtime_admission,
        fault_hook=fault_hook,
    )


def _complete_apply_started_from_context(
    *,
    session_lease: LiveStartSessionLease,
    expected_receipt_committed_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    output_operation_admission: OutputOperationAdmissionEvidence,
    lease_pair: ControllerApplyLeasePair,
    invocation: ApplyInvocation,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    fault_hook: LiveStartFaultHook = no_live_start_fault,
) -> LiveStartSession:
    invoke_live_start_fault(
        fault_hook,
        LiveStartFaultPoint.AFTER_INVOCATION_WRITE_BEFORE_APPLY_STARTED,
    )
    binding = _authenticate_controller_apply_pair_binding(lease_pair)
    if (
        binding.session_lease is not session_lease
        or binding.profile_lease is not profile_lease
        or binding.output_operation_lease is not output_operation_lease
        or binding.output_operation_admission
        is not output_operation_admission
        or binding.package_lease is not lease_pair.package_lease
        or binding.runtime_admission is not runtime_admission
    ):
        raise live_start_session.SessionCapabilityError(
            "published_apply_recovery_invocation_context_invalid"
        )
    _require_recovery_invocation_context(
        lease_pair=lease_pair,
        session_lease=session_lease,
        cursor=expected_receipt_committed_session,
        profile_lease=profile_lease,
        historical=output_operation_admission,
        package_lease=lease_pair.package_lease,
        runtime_admission=runtime_admission,
        invocation=invocation,
    )
    cursor = live_start_session._complete_apply_started_under_lock(
        session_lease=session_lease,
        expected_receipt_committed_session=(
            expected_receipt_committed_session
        ),
        invocation=invocation,
        runtime_admission=runtime_admission,
    )
    invoke_live_start_fault(
        fault_hook,
        LiveStartFaultPoint.AFTER_APPLY_STARTED,
    )
    return cursor


def _authorize_output_operation_runtime_handoff_release_from_context(
    *,
    lease_pair: ControllerApplyLeasePair,
    session_lease: LiveStartSessionLease,
    cursor: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    historical: OutputOperationAdmissionEvidence,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
) -> live_start_session.OutputOperationAdmissionReleaseAuthorization:
    binding = _require_active_controller_apply_pair(lease_pair)
    persisted = live_start_session.load_live_start_session_under_lock(
        session_lease=session_lease
    )
    if (
        binding.session_lease is not session_lease
        or binding.profile_lease is not profile_lease
        or binding.output_operation_lease is not output_operation_lease
        or binding.output_operation_admission is not historical
        or binding.package_lease is not lease_pair.package_lease
        or binding.runtime_lease is not lease_pair.runtime_lease
        or binding.runtime_admission is not runtime_admission
        or persisted != cursor
        or persisted.canonical_json != cursor.canonical_json
        or persisted.session_identity != cursor.session_identity
    ):
        raise ValueError("published_apply_output_handoff_context_invalid")
    return (
        live_start_session._authorize_output_operation_admission_release_under_lock(
            session_lease=session_lease,
            expected_release_authorized_session=cursor,
        )
    )


def _release_output_operation_handoff(
    *,
    lease_pair: ControllerApplyLeasePair,
    session_lease: LiveStartSessionLease,
    cursor: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    historical: OutputOperationAdmissionEvidence,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    fault_hook: LiveStartFaultHook,
) -> None:
    authorization = _authorize_output_operation_runtime_handoff_release_from_context(
        lease_pair=lease_pair,
        session_lease=session_lease,
        cursor=cursor,
        profile_lease=profile_lease,
        output_operation_lease=output_operation_lease,
        historical=historical,
        runtime_admission=runtime_admission,
    )
    invoke_live_start_fault(
        fault_hook,
        LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_RELEASE_AUTHORIZED,
    )
    release_output_operation_admission_under_lease(
        operation_lease=output_operation_lease,
        session_lease=session_lease,
        expected_release_authorized_session=cursor,
        expected=historical,
        release_authorization=authorization,
        fault_hook=fault_hook,
    )
    _require_active_controller_apply_pair(lease_pair)


def _observe_runtime_recovery_from_context(
    *,
    plan: RuntimeInstallPlan,
    lease_pair: ControllerApplyLeasePair,
    session_lease: LiveStartSessionLease,
    cursor: LiveStartSession,
    profile_lease: OperatorProfileLease,
    historical: OutputOperationAdmissionEvidence,
    package_lease: PackageInputLease,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    invocation: ApplyInvocation,
) -> live_start_session.RuntimeObservationReceipt:
    binding = _require_active_controller_apply_pair(lease_pair)
    _require_recovery_invocation_context(
        lease_pair=lease_pair,
        session_lease=session_lease,
        cursor=cursor,
        profile_lease=profile_lease,
        historical=historical,
        package_lease=package_lease,
        runtime_admission=runtime_admission,
        invocation=invocation,
    )
    persisted = live_start_session.load_live_start_session_under_lock(
        session_lease=session_lease
    )
    operation = persisted.output_operation_admission_binding
    layout = persisted.runtime_layout_bootstrap
    admission = persisted.runtime_admission_binding
    if (
        persisted != cursor
        or persisted.canonical_json != cursor.canonical_json
        or persisted.phase is not LiveStartPhase.APPLY_STARTED
        or persisted.pending_transition is not None
        or persisted.apply_recovery is not None
        or persisted.result_intent is not None
        or persisted.terminal_status is not None
        or binding.entry_mode != "POST_HANDOFF_READY"
        or binding.reentry_output_disposition not in {"absent", "valid_foreign"}
        or binding.runtime_admission is not runtime_admission
        or not isinstance(operation, Mapping)
        or operation.get("state") != "RUNTIME_HANDOFF_RELEASE_AUTHORIZED"
        or operation.get("release_handoff_kind") != "runtime_admission"
        or not isinstance(layout, Mapping)
        or layout.get("stage") != "COMPLETE"
        or layout.get("run_id") != persisted.run_id
        or layout.get("apply_attempt_id") != runtime_admission.apply_attempt_id
        or layout.get("runtime_root") != str(plan.runtime_root)
        or tuple(layout.get("runtime_root_identity", ()))
        != runtime_admission.runtime_root_identity
        or not isinstance(admission, Mapping)
        or admission.get("admission_path")
        != str(runtime_admission.admission_path)
        or tuple(admission.get("admission_parent_identity", ()))
        != runtime_admission.admission_parent_identity
        or tuple(admission.get("admission_identity", ()))
        != runtime_admission.admission_identity
        or admission.get("admission_sha256")
        != runtime_admission.admission_sha256
        or admission.get("output_operation_admission_path")
        != str(runtime_admission.output_operation_admission_path)
        or tuple(admission.get("output_operation_admission_identity", ()))
        != runtime_admission.output_operation_admission_identity
        or admission.get("output_operation_admission_sha256")
        != runtime_admission.output_operation_admission_sha256
        or admission.get("output_child_binding_sha256")
        != runtime_admission.output_child_binding_sha256
        or admission.get("output_child_path") != str(runtime_admission.output_root)
        or tuple(admission.get("output_child_identity", ()))
        != runtime_admission.output_root_identity
        or admission.get("publication_revision")
        != runtime_admission.publication_revision
        or admission.get("publication_content_root_sha256")
        != runtime_admission.publication_content_root_sha256
        or plan.deck_name != persisted.deck_name
        or plan.runtime_root != runtime_admission.runtime_root
        or "sha256:" + _source_manifest_sha256(plan)
        != runtime_admission.package_root_sha256
    ):
        raise live_start_session.SessionCapabilityError(
            "published_apply_initial_recovery_context_invalid"
        )
    authorization = live_start_session._authorize_runtime_observation_under_lock(
        session_lease=session_lease,
        expected_session=persisted,
        observation_family="first_install",
        apply_attempt_id=runtime_admission.apply_attempt_id,
    )
    return observe_initial_runtime_install_from_pair(
        plan,
        lease_pair=lease_pair,
        observation_authorization=authorization,
        transaction_id=runtime_admission.apply_attempt_id,
        retention_owner_run_id=runtime_admission.retention_owner_run_id,
        runtime_admission=runtime_admission,
    )


def _prepare_initial_recovery(
    *,
    plan: RuntimeInstallPlan,
    lease_pair: ControllerApplyLeasePair,
    session_lease: LiveStartSessionLease,
    cursor: LiveStartSession,
    profile_lease: OperatorProfileLease,
    historical: OutputOperationAdmissionEvidence,
    package_lease: PackageInputLease,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    invocation: ApplyInvocation,
    fault_hook: LiveStartFaultHook,
) -> LiveStartSession:
    receipt = _observe_runtime_recovery_from_context(
        plan=plan,
        lease_pair=lease_pair,
        session_lease=session_lease,
        cursor=cursor,
        profile_lease=profile_lease,
        historical=historical,
        package_lease=package_lease,
        runtime_admission=runtime_admission,
        invocation=invocation,
    )
    invoke_live_start_fault(
        fault_hook,
        LiveStartFaultPoint.AFTER_FIRST_INSTALL_OBSERVATION_BEFORE_PREPARE_CAS,
    )
    return live_start_session.prepare_first_runtime_install_under_lock(
        session_lease=session_lease,
        expected_apply_started_session=cursor,
        runtime_observation_receipt=receipt,
    )


def _drive_recovery_rows(
    *,
    plan: RuntimeInstallPlan,
    lease_pair: ControllerApplyLeasePair,
    session_lease: LiveStartSessionLease,
    cursor: LiveStartSession,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    fault_hook: LiveStartFaultHook,
) -> LiveStartSession:
    retried_actions: set[tuple[str, int, str]] = set()
    while True:
        recovery = cursor.apply_recovery
        if not isinstance(recovery, Mapping):
            raise ValueError("published_apply_recovery_missing")
        action = recovery.get("expected_action")
        if action is None:
            return cursor
        if not isinstance(action, str):
            raise ValueError("published_apply_recovery_action_invalid")
        _require_active_controller_apply_pair(lease_pair)
        external = recovery.get("external_file_action")
        if (
            action == "materialize_file_action_staging"
            and isinstance(external, Mapping)
            and external.get("stage") == "PLANNED"
            and any(
                os.path.lexists(Path(str(external[field_name])))
                for field_name in ("staging_path", "inner_temp_path")
            )
        ):
            action = "retire_unbound_file_action_staging"
        initial_new_target_prepared_journal_commit = (
            action == "advance_controller_transaction_journal_write"
            and recovery.get("install_route") == "new_target"
            and recovery.get("planned_journal_successor_phase") == "PREPARED"
            and recovery.get("successor_journal_path") is None
            and recovery.get("successor_journal_identity") is None
            and recovery.get("successor_journal_sha256") is None
            and isinstance(external, Mapping)
            and external.get("stage") == "STAGING_BOUND"
            and external.get("action_kind")
            == "advance_controller_transaction_journal_write"
            and external.get("commit_mode") == "create_no_replace"
            and external.get("final_path")
            == recovery.get("planned_journal_successor_path")
            and external.get("planned_successor_size")
            == recovery.get("planned_journal_successor_size")
            and external.get("planned_successor_sha256")
            == recovery.get("planned_journal_successor_sha256")
        )
        created_candidate_before_identity_cas = (
            action == "bind_created_candidate"
            and recovery.get("install_route") == "new_target"
            and external is None
            and recovery.get("successor_journal_path") is not None
            and recovery.get("successor_journal_identity") is not None
            and recovery.get("successor_journal_sha256") is not None
            and recovery.get("planned_journal_successor_path") is None
            and recovery.get("planned_journal_successor_parent_identity") is None
            and recovery.get("planned_journal_successor_phase") is None
            and recovery.get("planned_journal_successor_size") is None
            and recovery.get("planned_journal_successor_sha256") is None
            and recovery.get("candidate_path") is not None
            and recovery.get("candidate_parent_identity") is not None
            and recovery.get("predecessor_candidate_identity") is None
            and recovery.get("successor_candidate_identity") is None
        )
        authorization = (
            live_start_session._authorize_nonterminal_apply_recovery_under_lock(
                session_lease=session_lease,
                expected_recovery_session=cursor,
                expected_action=action,
            )
        )
        try:
            physical = recover_runtime_attempt_from_pair(
                lease_pair=lease_pair,
                transaction_id=runtime_admission.apply_attempt_id,
                expected_retention_owner_run_id=(
                    runtime_admission.retention_owner_run_id
                ),
                expected_package_root_sha256=(
                    runtime_admission.package_root_sha256
                ),
                expected_deck_name=plan.deck_name,
                runtime_admission=runtime_admission,
                nonterminal_recovery_authorization=authorization,
                fault_hook=fault_hook,
            )
        except BaseException as primary:
            try:
                authorization_discarded = (
                    live_start_session._discard_unused_nonterminal_apply_recovery_authorization(
                        authorization,
                        expected_action=action,
                    )
                )
            except BaseException as discard_error:
                discard_error.add_note(
                    "original paired recovery error: "
                    f"{type(primary).__name__}: {primary}"
                )
                raise
            if authorization_discarded:
                raise
            expected_recovery = RuntimeApplyRecoveryEvidence(recovery)
            selection = classify_runtime_failure_from_pair(
                lease_pair=lease_pair,
                transaction_id=runtime_admission.apply_attempt_id,
                runtime_admission=runtime_admission,
                expected_recovery=expected_recovery,
            )
            retry_key = (
                str(recovery["content_sha256"]),
                int(recovery["action_index"]),
                action,
            )
            if selection.disposition == "resume_current_action":
                if retry_key in retried_actions:
                    raise
                retried_actions.add(retry_key)
                continue
            if (
                selection.disposition != "select_terminal_observation"
                or selection.selected_observation is None
            ):
                raise ValueError("published_apply_failure_selection_invalid")
            observation_authorization = (
                live_start_session._authorize_runtime_observation_under_lock(
                    session_lease=session_lease,
                    expected_session=cursor,
                    observation_family="terminal_classification",
                    apply_attempt_id=runtime_admission.apply_attempt_id,
                )
            )
            selection_receipt = observe_runtime_failure_selection_from_pair(
                lease_pair=lease_pair,
                transaction_id=runtime_admission.apply_attempt_id,
                runtime_admission=runtime_admission,
                expected_recovery=expected_recovery,
                observation_authorization=observation_authorization,
            )
            invoke_live_start_fault(
                fault_hook,
                LiveStartFaultPoint.AFTER_TERMINAL_CLASSIFICATION_OBSERVATION_BEFORE_SELECTION_CAS,
            )
            cursor = (
                live_start_session.advance_nonterminal_apply_recovery_under_lock(
                    session_lease=session_lease,
                    expected_recovery_session=cursor,
                    transition="select_terminal_classification",
                    recovery_evidence=None,
                    recovery_authorization=None,
                    physical_step_receipt=None,
                    runtime_observation_receipt=selection_receipt,
                )
            )
            invoke_live_start_fault(
                fault_hook,
                LiveStartFaultPoint.AFTER_TERMINAL_CLASSIFICATION_SELECTION_CAS,
            )
            continue
        if physical.apply_recovery_step_receipt is None:
            raise ValueError("published_apply_recovery_receipt_missing")
        if initial_new_target_prepared_journal_commit:
            invoke_live_start_fault(
                fault_hook,
                LiveStartFaultPoint.AFTER_RUNTIME_JOURNAL_CREATED,
            )
        if created_candidate_before_identity_cas:
            invoke_live_start_fault(
                fault_hook,
                LiveStartFaultPoint.AFTER_RUNTIME_CANDIDATE_CREATE_BEFORE_CANDIDATE_IDENTITY_RECEIPT_CAS,
            )
        invoke_live_start_fault(
            fault_hook,
            LiveStartFaultPoint.AFTER_NONTERMINAL_RECOVERY_PHYSICAL_STEP_BEFORE_CURSOR_CAS,
        )
        cursor = live_start_session.advance_nonterminal_apply_recovery_under_lock(
            session_lease=session_lease,
            expected_recovery_session=cursor,
            transition="physical_recovery_advanced",
            recovery_evidence=None,
            recovery_authorization=None,
            physical_step_receipt=physical.apply_recovery_step_receipt,
            runtime_observation_receipt=None,
        )
        if initial_new_target_prepared_journal_commit:
            successor = cursor.apply_recovery
            if (
                isinstance(successor, Mapping)
                and successor.get("recovery_stage") == "ACTIVE"
                and successor.get("install_route") == "new_target"
                and successor.get("expected_action") == "bind_created_candidate"
                and successor.get("external_file_action") is None
                and successor.get("successor_journal_path") is not None
                and successor.get("successor_journal_identity") is not None
                and successor.get("successor_journal_sha256") is not None
                and successor.get("planned_journal_successor_path") is None
                and successor.get("planned_journal_successor_parent_identity")
                is None
                and successor.get("planned_journal_successor_phase") is None
                and successor.get("planned_journal_successor_size") is None
                and successor.get("planned_journal_successor_sha256") is None
                and successor.get("predecessor_candidate_identity") is None
                and successor.get("successor_candidate_identity") is None
            ):
                invoke_live_start_fault(
                    fault_hook,
                    LiveStartFaultPoint.AFTER_RUNTIME_CANDIDATE_JOURNAL_BOUND_BEFORE_CANDIDATE_CREATE,
                )
        invoke_live_start_fault(
            fault_hook,
            LiveStartFaultPoint.AFTER_NONTERMINAL_RECOVERY_CURSOR_CAS,
        )


def _sealed_recovery(
    recovery: Mapping[str, Any],
    *,
    changes: Mapping[str, Any],
) -> RuntimeApplyRecoveryEvidence:
    return RuntimeApplyRecoveryEvidence(
        _seal_apply_recovery_successor(recovery, changes=changes)
    )


def _match_digest(report: Mapping[str, Any]) -> str:
    raw = (
        json.dumps(
            report,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _revalidate_success_candidate_current_facts_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    result: ApplyAndMatchPublishedResult,
    acknowledgement: AttemptAcknowledgementEvidence,
    logical_config_dir: str | None,
    runtime_config_dir: str,
) -> None:
    """Revalidate a stored matched result before any further durable write."""

    try:
        recovery = (
            expected_session.apply_recovery
            if isinstance(expected_session.apply_recovery, Mapping)
            else expected_session.closed_apply_recovery_commitment
        )
        if (
            result.terminal_status not in {"LIVE_AND_MATCHED", "ALREADY_LIVE"}
            or result.physical_disposition is not PhysicalApplyDisposition.COMMITTED
            or result.runtime_match_status != "matched"
            or not isinstance(result.runtime_match_sha256, str)
            or not isinstance(result.last_apply_receipt_sha256, str)
            or not isinstance(result.runtime_state_sha256, str)
            or not isinstance(result.deck_config_ini_sha256, str)
            or not isinstance(recovery, Mapping)
            or recovery.get("stable_physical_disposition") != "COMMITTED"
            or recovery.get("runtime_match_status") != "matched"
            or recovery.get("runtime_match_sha256")
            != result.runtime_match_sha256
            or acknowledgement.apply_attempt_id
            != runtime_admission.apply_attempt_id
            or acknowledgement.retention_owner_run_id
            != runtime_admission.retention_owner_run_id
            or acknowledgement.package_root_sha256
            != runtime_admission.package_root_sha256
            or result.package_root_sha256
            != runtime_admission.package_root_sha256
            or acknowledgement.runtime_admission_path
            != runtime_admission.admission_path
            or acknowledgement.runtime_admission_parent_identity
            != runtime_admission.admission_parent_identity
            or acknowledgement.runtime_admission_identity
            != runtime_admission.admission_identity
            or acknowledgement.runtime_admission_sha256
            != runtime_admission.admission_sha256
            or acknowledgement.target_path
            != runtime_admission.runtime_root
            / "CustomConfig"
            / runtime_config_dir
        ):
            raise ValueError("binding")
        report = build_runtime_package_match_report_from_pair(
            lease_pair=lease_pair,
            logical_config_dir=logical_config_dir,
            runtime_config_dir=runtime_config_dir,
        )
        if (
            report.get("status") != "matched"
            or _match_digest(report) != result.runtime_match_sha256
        ):
            raise ValueError("match")
        revalidate_success_candidate_runtime_parity_from_pair(
            lease_pair=lease_pair,
            session_lease=session_lease,
            expected_session=expected_session,
            runtime_admission=runtime_admission,
            expected_transaction_id=acknowledgement.apply_attempt_id,
            expected_retention_owner_run_id=(
                acknowledgement.retention_owner_run_id
            ),
            expected_package_root_sha256=(
                acknowledgement.package_root_sha256
            ),
            expected_target_owner_journal_path=(
                acknowledgement.target_owner_journal_path
            ),
            expected_target_owner_journal_identity=(
                acknowledgement.target_owner_journal_identity
            ),
            expected_target_owner_journal_sha256=(
                acknowledgement.target_owner_journal_sha256
            ),
            expected_target_path=acknowledgement.target_path,
            expected_target_identity=acknowledgement.target_identity,
            expected_deck_config_ini_sha256=(
                result.deck_config_ini_sha256
            ),
            expected_runtime_state_sha256=result.runtime_state_sha256,
            expected_last_apply_receipt_sha256=(
                result.last_apply_receipt_sha256
            ),
        )
    except Exception as error:
        raise ValueError(
            "published_apply_success_candidate_current_facts_changed"
        ) from error


def _runtime_inventory_sha256(runtime_root: Path) -> str:
    root = Path(runtime_root)
    require_plain_directory(root)
    root_identity = path_identity(root)
    rows = bytearray()
    node_count = 0
    file_count = 0
    total_size = 0

    def immediate_inventory(
        directory: Path,
    ) -> tuple[tuple[str, Path, os.stat_result, bool], ...]:
        entries: list[os.DirEntry[str]] = []
        with os.scandir(directory) as iterator:
            for entry in iterator:
                if len(entries) >= MAX_FILESYSTEM_ENTRIES_PER_DIRECTORY:
                    raise ValueError("runtime_inventory_entry_limit")
                entries.append(entry)
        observed: list[tuple[str, Path, os.stat_result, bool]] = []
        for entry in sorted(entries, key=lambda item: item.name):
            child = Path(entry.path)
            status = child.lstat()
            if status_is_reparse(status) or entry.is_symlink():
                raise ValueError("runtime_inventory_reparse_forbidden")
            is_directory = stat.S_ISDIR(status.st_mode)
            if not is_directory and (
                not stat.S_ISREG(status.st_mode) or status.st_nlink != 1
            ):
                raise ValueError("runtime_inventory_entry_invalid")
            observed.append((entry.name, child, status, is_directory))
        return tuple(observed)

    def require_relative(relative: str) -> str:
        if (
            len(relative.encode("utf-8")) > MAX_RUN_PATH_BYTES
            or canonical_relative_path(relative) != relative
        ):
            raise ValueError("runtime_inventory_path_invalid")
        return relative

    def inventory_signature(
        inventory: tuple[tuple[str, Path, os.stat_result, bool], ...],
    ) -> tuple[tuple[object, ...], ...]:
        return tuple(
            (
                name,
                is_directory,
                path_identity_from_status(status),
                status.st_size,
                status.st_mtime_ns,
                None if os.name == "nt" else status.st_ctime_ns,
            )
            for name, _path, status, is_directory in inventory
        )

    def count_node(*, file_size: int | None = None) -> None:
        nonlocal node_count, file_count, total_size
        node_count += 1
        if node_count > MAX_FILESYSTEM_NODES:
            raise ValueError("runtime_inventory_node_limit")
        if file_size is not None:
            file_count += 1
            total_size += file_size
            if file_count > MAX_RUN_FILES:
                raise ValueError("runtime_inventory_file_limit")
            if total_size > MAX_RUN_TOTAL_BYTES:
                raise ValueError("runtime_inventory_size_limit")

    def append_file(
        *,
        relative: str,
        path: Path,
        status: os.stat_result,
    ) -> None:
        relative = require_relative(relative)
        count_node(file_size=status.st_size)
        raw = read_file_no_follow(
            path,
            expected_status=status,
            maximum_size=MAX_RUN_TOTAL_BYTES,
        )
        rows.extend(
            (
                f"F\0{relative}\0{len(raw)}\0"
                f"{hashlib.sha256(raw).hexdigest()}\n"
            ).encode("utf-8")
        )

    def append_snapshot(*, relative: str, path: Path) -> None:
        relative = require_relative(relative)
        count_node()
        rows.extend(f"D\0{relative}\n".encode("utf-8"))
        snapshot = snapshot_bounded_filesystem_package(path)
        for directory_name in snapshot.directory_names:
            nested = require_relative(f"{relative}/{directory_name}")
            count_node()
            rows.extend(f"D\0{nested}\n".encode("utf-8"))
        for file_name in snapshot.file_names():
            raw = snapshot.read_bytes(file_name)
            nested = require_relative(f"{relative}/{file_name}")
            count_node(file_size=len(raw))
            rows.extend(
                (
                    f"F\0{nested}\0{len(raw)}\0"
                    f"{hashlib.sha256(raw).hexdigest()}\n"
                ).encode("utf-8")
            )

    root_before = immediate_inventory(root)
    for name, child, status, is_directory in root_before:
        relative = require_relative(name)
        if not is_directory:
            append_file(relative=relative, path=child, status=status)
            continue
        if name != ".hsconfig":
            append_snapshot(relative=relative, path=child)
            continue
        count_node()
        rows.extend(b"D\0.hsconfig\n")
        hsconfig_identity = path_identity_from_status(status)
        hsconfig_before = immediate_inventory(child)
        for nested_name, nested_path, nested_status, nested_is_directory in (
            hsconfig_before
        ):
            nested_relative = require_relative(f".hsconfig/{nested_name}")
            if nested_is_directory:
                append_snapshot(relative=nested_relative, path=nested_path)
            elif nested_name == "apply.lock":
                count_node(file_size=nested_status.st_size)
                lock_identity = path_identity_from_status(nested_status)
                rows.extend(
                    (
                        f"L\0{nested_relative}\0{nested_status.st_size}\0"
                        f"{lock_identity[0]}:{lock_identity[1]}:"
                        f"{lock_identity[2]}\n"
                    ).encode("utf-8")
                )
            else:
                append_file(
                    relative=nested_relative,
                    path=nested_path,
                    status=nested_status,
                )
        if inventory_signature(immediate_inventory(child)) != inventory_signature(
            hsconfig_before
        ):
            raise ValueError("runtime_inventory_membership_changed")
        if path_identity(child) != hsconfig_identity:
            raise ValueError("runtime_inventory_identity_changed")
    if inventory_signature(immediate_inventory(root)) != inventory_signature(
        root_before
    ):
        raise ValueError("runtime_inventory_membership_changed")
    if path_identity(root) != root_identity:
        raise ValueError("runtime_inventory_identity_changed")
    return "sha256:" + hashlib.sha256(rows).hexdigest()


def _finish_stable_recovery(
    *,
    plan: RuntimeInstallPlan,
    lease_pair: ControllerApplyLeasePair,
    session_lease: LiveStartSessionLease,
    cursor: LiveStartSession,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    raw_apply_status: Literal["applied", "already_current", "recovered"],
    fault_hook: LiveStartFaultHook,
    fire_installer_faults: bool,
) -> tuple[
    LiveStartSession,
    ApplyAndMatchPublishedResult,
    AttemptAcknowledgementEvidence | None,
]:
    recovery = cursor.apply_recovery
    if (
        isinstance(recovery, Mapping)
        and recovery.get("stable_physical_disposition") == "COMMITTED"
        and recovery.get("runtime_match_status") == "matched"
    ):
        stored_result = _result_from_closed_recovery(
            recovery=recovery,
            runtime_admission=runtime_admission,
            raw_apply_status=raw_apply_status,
        )
        stored_acknowledgement = _acknowledgement_from_closed_recovery(
            recovery=recovery,
            runtime_admission=runtime_admission,
        )
        if stored_acknowledgement is None:
            raise ValueError("published_apply_acknowledgement_evidence_missing")
        _revalidate_success_candidate_current_facts_from_pair(
            lease_pair=lease_pair,
            session_lease=session_lease,
            expected_session=cursor,
            runtime_admission=runtime_admission,
            result=stored_result,
            acknowledgement=stored_acknowledgement,
            logical_config_dir=plan.logical_config_dir,
            runtime_config_dir=plan.versioned_config_dir,
        )
    if (
        isinstance(recovery, Mapping)
        and recovery.get("recovery_stage") == "CLOSED"
    ):
        result = _result_from_closed_recovery(
            recovery=recovery,
            runtime_admission=runtime_admission,
            raw_apply_status=raw_apply_status,
        )
        acknowledgement = _acknowledgement_from_closed_recovery(
            recovery=recovery,
            runtime_admission=runtime_admission,
        )
        return cursor, result, acknowledgement
    stable_disposition = (
        recovery.get("stable_physical_disposition")
        if isinstance(recovery, Mapping)
        else None
    )
    if (
        not isinstance(recovery, Mapping)
        or recovery.get("expected_action") is not None
        or stable_disposition
        not in {
            "NOT_COMMITTED",
            "COMMITTED",
            "COMMITTED_RECOVERY_PENDING",
            "UNKNOWN_REQUIRES_RECOVERY",
        }
    ):
        raise ValueError("published_apply_stable_recovery_missing")
    if stable_disposition != "COMMITTED":
        closed_recovery = _sealed_recovery(
            recovery,
            changes={"recovery_stage": "CLOSED"},
        )
        authorization = (
            live_start_session._authorize_nonterminal_apply_recovery_under_lock(
                session_lease=session_lease,
                expected_recovery_session=cursor,
                expected_action="recovery_closed",
            )
        )
        cursor = live_start_session.advance_nonterminal_apply_recovery_under_lock(
            session_lease=session_lease,
            expected_recovery_session=cursor,
            transition="recovery_closed",
            recovery_evidence=closed_recovery,
            recovery_authorization=authorization,
            physical_step_receipt=None,
            runtime_observation_receipt=None,
        )
        invoke_live_start_fault(
            fault_hook,
            LiveStartFaultPoint.AFTER_RECOVERY_CLOSED_CAS_BEFORE_RESULT_INTENT,
        )
        recovery = cursor.apply_recovery
        if not isinstance(recovery, Mapping):
            raise live_start_session.SessionConflictError(
                "published_apply_recovery_cursor_missing"
            )
        result = _result_from_closed_recovery(
            recovery=recovery,
            runtime_admission=runtime_admission,
            raw_apply_status=raw_apply_status,
        )
        return cursor, result, None
    if fire_installer_faults:
        invoke_live_start_fault(
            fault_hook,
            LiveStartFaultPoint.AFTER_PHYSICAL_COMMIT_BEFORE_INSTALLER_RETURN,
        )
        invoke_live_start_fault(
            fault_hook,
            LiveStartFaultPoint.AFTER_INSTALLER_RETURN_BEFORE_APPLY_COMMITTED,
        )
    if cursor.phase in {
        LiveStartPhase.APPLY_STARTED,
        LiveStartPhase.APPLY_COMMITTED,
    }:
        revalidate_committed_runtime_control_plane_from_pair(
            lease_pair=lease_pair,
            transaction_id=runtime_admission.apply_attempt_id,
            expected_retention_owner_run_id=(
                runtime_admission.retention_owner_run_id
            ),
            expected_package_root_sha256=(
                runtime_admission.package_root_sha256
            ),
            expected_deck_name=plan.deck_name,
            runtime_admission=runtime_admission,
            expected_recovery=RuntimeApplyRecoveryEvidence(recovery),
        )
    if cursor.phase is LiveStartPhase.APPLY_STARTED:
        authorization = (
            live_start_session._authorize_nonterminal_apply_recovery_under_lock(
                session_lease=session_lease,
                expected_recovery_session=cursor,
                expected_action="apply_committed",
            )
        )
        cursor = live_start_session.advance_nonterminal_apply_recovery_under_lock(
            session_lease=session_lease,
            expected_recovery_session=cursor,
            transition="apply_committed",
            recovery_evidence=RuntimeApplyRecoveryEvidence(recovery),
            recovery_authorization=authorization,
            physical_step_receipt=None,
            runtime_observation_receipt=None,
        )
    elif cursor.phase is LiveStartPhase.APPLY_COMMITTED:
        if (
            recovery.get("runtime_match_status") != "unknown"
            or recovery.get("runtime_match_sha256") is not None
        ):
            raise live_start_session.SessionConflictError(
                "published_apply_committed_recovery_invalid"
            )
    elif cursor.phase is LiveStartPhase.RUNTIME_MATCHED:
        if (
            recovery.get("runtime_match_status") != "matched"
            or not isinstance(recovery.get("runtime_match_sha256"), str)
        ):
            raise live_start_session.SessionConflictError(
                "published_apply_matched_recovery_invalid"
            )
    else:
        raise live_start_session.SessionConflictError(
            "published_apply_committed_recovery_phase_invalid"
        )
    if cursor.phase is LiveStartPhase.RUNTIME_MATCHED:
        closure_changes: dict[str, Any] = {"recovery_stage": "CLOSED"}
    else:
        report = build_runtime_package_match_report_from_pair(
            lease_pair=lease_pair,
            logical_config_dir=plan.logical_config_dir,
            runtime_config_dir=plan.versioned_config_dir,
        )
        match_status = str(report.get("status"))
        if match_status not in {"matched", "mismatch"}:
            raise ValueError("published_apply_runtime_match_invalid")
        match_sha256 = _match_digest(report)
        recovery = cursor.apply_recovery
        if not isinstance(recovery, Mapping):
            raise live_start_session.SessionConflictError(
                "published_apply_recovery_cursor_missing"
            )
        if match_status == "matched":
            matched_recovery = _sealed_recovery(
                recovery,
                changes={
                    "runtime_match_status": "matched",
                    "runtime_match_sha256": match_sha256,
                },
            )
            authorization = (
                live_start_session._authorize_nonterminal_apply_recovery_under_lock(
                    session_lease=session_lease,
                    expected_recovery_session=cursor,
                    expected_action="runtime_matched",
                )
            )
            cursor = (
                live_start_session.advance_nonterminal_apply_recovery_under_lock(
                    session_lease=session_lease,
                    expected_recovery_session=cursor,
                    transition="runtime_matched",
                    recovery_evidence=matched_recovery,
                    recovery_authorization=authorization,
                    physical_step_receipt=None,
                    runtime_observation_receipt=None,
                )
            )
            closure_changes = {"recovery_stage": "CLOSED"}
        else:
            closure_changes = {
                "recovery_stage": "CLOSED",
                "runtime_match_status": "mismatch",
                "runtime_match_sha256": match_sha256,
            }
    recovery = cursor.apply_recovery
    if not isinstance(recovery, Mapping):
        raise live_start_session.SessionConflictError(
            "published_apply_recovery_cursor_missing"
        )
    closed_recovery = _sealed_recovery(recovery, changes=closure_changes)
    authorization = (
        live_start_session._authorize_nonterminal_apply_recovery_under_lock(
            session_lease=session_lease,
            expected_recovery_session=cursor,
            expected_action="recovery_closed",
        )
    )
    cursor = live_start_session.advance_nonterminal_apply_recovery_under_lock(
        session_lease=session_lease,
        expected_recovery_session=cursor,
        transition="recovery_closed",
        recovery_evidence=closed_recovery,
        recovery_authorization=authorization,
        physical_step_receipt=None,
        runtime_observation_receipt=None,
    )
    invoke_live_start_fault(
        fault_hook,
        LiveStartFaultPoint.AFTER_RECOVERY_CLOSED_CAS_BEFORE_RESULT_INTENT,
    )
    recovery = cursor.apply_recovery
    if not isinstance(recovery, Mapping):
        raise live_start_session.SessionConflictError(
            "published_apply_recovery_cursor_missing"
        )
    result = _result_from_closed_recovery(
        recovery=recovery,
        runtime_admission=runtime_admission,
        raw_apply_status=raw_apply_status,
    )
    acknowledgement = _acknowledgement_from_closed_recovery(
        recovery=recovery,
        runtime_admission=runtime_admission,
    )
    return cursor, result, acknowledgement


def _triplet(
    recovery: Mapping[str, Any],
    prefix: str,
) -> tuple[Path | None, PathIdentity | None, str | None]:
    path_value = recovery.get(f"{prefix}_path")
    identity_value = recovery.get(f"{prefix}_identity")
    digest = recovery.get(f"{prefix}_sha256")
    return (
        None if path_value is None else Path(str(path_value)),
        None if identity_value is None else tuple(identity_value),
        None if digest is None else str(digest),
    )


def _runtime_admission_release_postcondition(
    *,
    expected: RuntimeLiveAttemptAdmissionEvidence,
    fault_hook: LiveStartFaultHook = no_live_start_fault,
) -> live_start_session.RuntimeAdmissionReleasePostcondition:
    invoke_live_start_fault(
        fault_hook,
        LiveStartFaultPoint.AFTER_ADMISSION_RELEASE_AUTHORIZED_BEFORE_RUNTIME_ADMISSION_UNLINK,
    )
    observation = release_runtime_live_attempt_exact(expected=expected)
    invoke_live_start_fault(
        fault_hook, LiveStartFaultPoint.AFTER_RUNTIME_ADMISSION_UNLINK
    )
    return live_start_session.RuntimeAdmissionReleasePostcondition(
        admission_path=observation.admission_path,
        admission_parent_identity=observation.admission_parent_identity,
        historical_admission_identity=(
            observation.historical_admission_identity
        ),
        historical_admission_sha256=(
            observation.historical_admission_sha256
        ),
        disposition=observation.disposition,
        foreign_successor_identity=observation.foreign_successor_identity,
        foreign_successor_sha256=observation.foreign_successor_sha256,
    )


def _require_release_authorized_runtime_cursor(
    *,
    session_lease: LiveStartSessionLease,
    expected_release_authorized_session: LiveStartSession,
    expected: RuntimeLiveAttemptAdmissionEvidence,
) -> None:
    if (
        not isinstance(session_lease, LiveStartSessionLease)
        or not isinstance(expected_release_authorized_session, LiveStartSession)
        or type(expected) is not RuntimeLiveAttemptAdmissionEvidence
    ):
        raise TypeError("published_apply_terminal_release_context_invalid")
    persisted = live_start_session.load_live_start_session_under_lock(
        session_lease=session_lease
    )
    retirement = persisted.terminal_retirement
    admission = persisted.runtime_admission_binding
    intent = persisted.result_intent
    historical = {
        "runtime_admission_path": str(expected.admission_path),
        "runtime_admission_parent_identity": tuple(
            expected.admission_parent_identity
        ),
        "runtime_admission_identity": tuple(expected.admission_identity),
        "runtime_admission_sha256": expected.admission_sha256,
    }
    if (
        persisted != expected_release_authorized_session
        or persisted.canonical_json
        != expected_release_authorized_session.canonical_json
        or persisted.content_sha256
        != expected_release_authorized_session.content_sha256
        or persisted.session_identity
        != expected_release_authorized_session.session_identity
        or persisted.pending_transition is not None
        or persisted.apply_recovery is not None
        or persisted.terminal_status is None
        or not isinstance(retirement, Mapping)
        or retirement.get("stage") != "ADMISSION_RELEASE_AUTHORIZED"
        or not isinstance(admission, Mapping)
        or not isinstance(intent, Mapping)
        or any(
            retirement.get(field_name) != expected_value
            for field_name, expected_value in historical.items()
        )
        or any(
            intent.get(field_name) != expected_value
            for field_name, expected_value in historical.items()
        )
        or admission.get("admission_path") != historical["runtime_admission_path"]
        or tuple(admission.get("admission_parent_identity", ()))
        != historical["runtime_admission_parent_identity"]
        or tuple(admission.get("admission_identity", ()))
        != historical["runtime_admission_identity"]
        or admission.get("admission_sha256")
        != historical["runtime_admission_sha256"]
    ):
        raise live_start_session.SessionCapabilityError(
            "published_apply_terminal_release_context_invalid"
        )


def _release_runtime_live_attempt_from_pair(
    *,
    session_lease: LiveStartSessionLease,
    expected_release_authorized_session: LiveStartSession,
    terminal_authorization: live_start_session.TerminalRetirementAuthorization,
    profile_lease: OperatorProfileLease,
    lease_pair: ControllerApplyLeasePair,
    expected: RuntimeLiveAttemptAdmissionEvidence,
    fault_hook: LiveStartFaultHook = no_live_start_fault,
) -> live_start_session.RuntimeAdmissionReleasePostcondition:
    _require_release_authorized_runtime_cursor(
        session_lease=session_lease,
        expected_release_authorized_session=(
            expected_release_authorized_session
        ),
        expected=expected,
    )

    def release_runtime_admission(
    ) -> live_start_session.RuntimeAdmissionReleasePostcondition:
        binding = _require_active_controller_apply_pair(lease_pair)
        if (
            binding.session_lease is not session_lease
            or binding.profile_lease is not profile_lease
            or binding.package_lease is not lease_pair.package_lease
            or binding.runtime_admission is not expected
        ):
            raise live_start_session.SessionCapabilityError(
                "published_apply_terminal_release_pair_invalid"
            )
        revalidate_operator_profile_lease(profile_lease)
        revalidate_package_input_lease(lease_pair.package_lease)
        return _runtime_admission_release_postcondition(
            expected=expected, fault_hook=fault_hook
        )

    return live_start_session._execute_runtime_admission_release(
        terminal_authorization=terminal_authorization,
        action="release_runtime_admission",
        physical_action=release_runtime_admission,
    )


def _release_or_confirm_runtime_live_attempt_without_old_leases(
    *,
    session_lease: LiveStartSessionLease,
    expected_release_authorized_session: LiveStartSession,
    terminal_authorization: live_start_session.TerminalRetirementAuthorization,
    expected: RuntimeLiveAttemptAdmissionEvidence,
    fault_hook: LiveStartFaultHook = no_live_start_fault,
) -> live_start_session.RuntimeAdmissionReleasePostcondition:
    _require_release_authorized_runtime_cursor(
        session_lease=session_lease,
        expected_release_authorized_session=(
            expected_release_authorized_session
        ),
        expected=expected,
    )
    return live_start_session._execute_runtime_admission_release(
        terminal_authorization=terminal_authorization,
        action="release_runtime_admission",
        physical_action=lambda: _runtime_admission_release_postcondition(
            expected=expected, fault_hook=fault_hook
        ),
    )


def _terminal_result_requires_resolution(intent: Mapping[str, Any]) -> bool:
    pending_or_unknown = (
        intent.get("terminal_status") == "APPLIED_BUT_NOT_VERIFIED"
        and intent.get("physical_disposition")
        in {
            PhysicalApplyDisposition.COMMITTED_RECOVERY_PENDING.value,
            PhysicalApplyDisposition.UNKNOWN_REQUIRES_RECOVERY.value,
        }
        and intent.get("raw_apply_status")
        in {
            None,
            "committed_receipt_pending",
        }
        and intent.get("runtime_match_status") in {"not_run", "unknown"}
    )
    retained_no_commit = (
        intent.get("terminal_status") == "FAILED_PRESERVED"
        and intent.get("physical_disposition")
        == PhysicalApplyDisposition.NOT_COMMITTED.value
        and intent.get("runtime_match_status") == "not_run"
        and any(
            intent.get(field_name) is not None
            for field_name in (
                "retained_attempt_record_path",
                "retained_journal_path",
                "retained_candidate_identity",
            )
        )
    )
    return pending_or_unknown or retained_no_commit


def _result_from_terminal_intent(
    *,
    intent: Mapping[str, Any],
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
) -> ApplyAndMatchPublishedResult:
    if not _terminal_result_requires_resolution(intent):
        raise live_start_session.SessionConflictError(
            "published_apply_terminal_result_intent_invalid"
        )
    return _result_from_bound_terminal_intent(
        intent=intent,
        runtime_admission=runtime_admission,
    )


def _result_from_bound_terminal_intent(
    *,
    intent: Mapping[str, Any],
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
) -> ApplyAndMatchPublishedResult:
    raw_apply_status = intent.get("raw_apply_status")
    runtime_match_status = intent.get("runtime_match_status")
    physical_disposition = PhysicalApplyDisposition(
        str(intent.get("physical_disposition"))
    )
    if intent.get("terminal_status") not in {
        "LIVE_AND_MATCHED",
        "ALREADY_LIVE",
        "FAILED_PRESERVED",
        "APPLIED_BUT_NOT_VERIFIED",
    }:
        raise live_start_session.SessionConflictError(
            "published_apply_terminal_result_intent_invalid"
        )
    attempt = _triplet(intent, "retained_attempt_record")
    journal = _triplet(intent, "retained_journal")
    owner = _triplet(intent, "retained_target_owner_journal")
    expected_admission = {
        "runtime_admission_path": str(runtime_admission.admission_path),
        "runtime_admission_parent_identity": tuple(
            runtime_admission.admission_parent_identity
        ),
        "runtime_admission_identity": tuple(runtime_admission.admission_identity),
        "runtime_admission_sha256": runtime_admission.admission_sha256,
    }
    if any(
        intent.get(field_name) != expected_value
        for field_name, expected_value in expected_admission.items()
    ):
        raise live_start_session.SessionCapabilityError(
            "published_apply_terminal_runtime_admission_changed"
        )
    return ApplyAndMatchPublishedResult(
        raw_apply_status=cast(
            Literal[
                "applied",
                "already_current",
                "recovered",
                "committed_receipt_pending",
            ]
            | None,
            raw_apply_status,
        ),
        physical_disposition=physical_disposition,
        runtime_match_status=cast(
            Literal["not_run", "matched", "mismatch", "unknown"],
            runtime_match_status,
        ),
        runtime_match_sha256=cast(str | None, intent.get("runtime_match_sha256")),
        package_root_sha256=cast(str | None, intent.get("package_root_sha256")),
        last_apply_receipt_sha256=cast(
            str | None,
            intent.get("last_apply_receipt_sha256"),
        ),
        runtime_state_sha256=cast(str | None, intent.get("runtime_state_sha256")),
        deck_config_ini_sha256=cast(
            str | None,
            intent.get("deck_config_ini_sha256"),
        ),
        retained_attempt_record_path=attempt[0],
        retained_attempt_record_identity=attempt[1],
        retained_attempt_record_sha256=attempt[2],
        retained_journal_path=journal[0],
        retained_journal_identity=journal[1],
        retained_journal_sha256=journal[2],
        retained_target_owner_journal_path=owner[0],
        retained_target_owner_journal_identity=owner[1],
        retained_target_owner_journal_sha256=owner[2],
        runtime_admission_path=runtime_admission.admission_path,
        runtime_admission_parent_identity=(
            runtime_admission.admission_parent_identity
        ),
        runtime_admission_identity=runtime_admission.admission_identity,
        runtime_admission_sha256=runtime_admission.admission_sha256,
        terminal_status=cast(
            Literal[
                "LIVE_AND_MATCHED",
                "ALREADY_LIVE",
                "FAILED_PRESERVED",
                "APPLIED_BUT_NOT_VERIFIED",
            ],
            intent["terminal_status"],
        ),
        error_code=cast(str | None, intent.get("error_code")),
    )


def _result_from_closed_recovery(
    *,
    recovery: Mapping[str, Any],
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    raw_apply_status: Literal["applied", "already_current", "recovered"],
) -> ApplyAndMatchPublishedResult:
    attempt = _triplet(recovery, "predecessor_attempt_record")
    journal = _triplet(recovery, "predecessor_journal")
    owner = _triplet(recovery, "predecessor_target_owner_journal")
    match_status = str(recovery["runtime_match_status"])
    disposition = PhysicalApplyDisposition(
        str(recovery["stable_physical_disposition"])
    )
    result_raw_apply_status: Literal[
        "applied",
        "already_current",
        "recovered",
        "committed_receipt_pending",
    ] | None = raw_apply_status
    terminal_status: Literal[
        "LIVE_AND_MATCHED",
        "ALREADY_LIVE",
        "FAILED_PRESERVED",
        "APPLIED_BUT_NOT_VERIFIED",
    ]
    if disposition is PhysicalApplyDisposition.NOT_COMMITTED:
        result_raw_apply_status = None
        terminal_status = "FAILED_PRESERVED"
        error_code = "apply_not_committed"
    elif disposition in {
        PhysicalApplyDisposition.COMMITTED_RECOVERY_PENDING,
        PhysicalApplyDisposition.UNKNOWN_REQUIRES_RECOVERY,
    }:
        terminal_status = "APPLIED_BUT_NOT_VERIFIED"
        result_raw_apply_status = (
            "committed_receipt_pending"
            if disposition
            is PhysicalApplyDisposition.COMMITTED_RECOVERY_PENDING
            else None
        )
        error_code = (
            "apply_recovery_pending"
            if disposition is PhysicalApplyDisposition.COMMITTED_RECOVERY_PENDING
            else "apply_recovery_unknown"
        )
    elif match_status == "matched":
        terminal_status = (
            "ALREADY_LIVE"
            if raw_apply_status == "already_current"
            else "LIVE_AND_MATCHED"
        )
        error_code = None
    else:
        terminal_status = "APPLIED_BUT_NOT_VERIFIED"
        error_code = "runtime_mismatch"
    return ApplyAndMatchPublishedResult(
        raw_apply_status=result_raw_apply_status,
        physical_disposition=disposition,
        runtime_match_status=match_status,  # type: ignore[arg-type]
        runtime_match_sha256=recovery.get("runtime_match_sha256"),
        package_root_sha256=str(recovery["package_root_sha256"]),
        last_apply_receipt_sha256=recovery.get("last_apply_receipt_sha256"),
        runtime_state_sha256=recovery.get("runtime_state_sha256"),
        deck_config_ini_sha256=recovery.get("deck_config_ini_sha256"),
        retained_attempt_record_path=attempt[0],
        retained_attempt_record_identity=attempt[1],
        retained_attempt_record_sha256=attempt[2],
        retained_journal_path=journal[0],
        retained_journal_identity=journal[1],
        retained_journal_sha256=journal[2],
        retained_target_owner_journal_path=owner[0],
        retained_target_owner_journal_identity=owner[1],
        retained_target_owner_journal_sha256=owner[2],
        runtime_admission_path=runtime_admission.admission_path,
        runtime_admission_parent_identity=(
            runtime_admission.admission_parent_identity
        ),
        runtime_admission_identity=runtime_admission.admission_identity,
        runtime_admission_sha256=runtime_admission.admission_sha256,
        terminal_status=terminal_status,
        error_code=error_code,
    )


def _acknowledgement_from_closed_recovery(
    *,
    recovery: Mapping[str, Any],
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
) -> AttemptAcknowledgementEvidence | None:
    if (
        recovery.get("stable_physical_disposition") != "COMMITTED"
        or recovery.get("runtime_match_status") != "matched"
    ):
        return None
    attempt = _triplet(recovery, "predecessor_attempt_record")
    journal = _triplet(recovery, "predecessor_journal")
    owner = _triplet(recovery, "predecessor_target_owner_journal")
    route = recovery.get("install_route")
    owns_target = route == "new_target"
    if owns_target and owner[0] is None:
        owner = journal
    target_path_value = recovery.get("renamed_target_path")
    target_identity_value = recovery.get("predecessor_renamed_target_identity")
    if any(value is None for value in (*attempt, *journal, *owner)) or (
        target_path_value is None or target_identity_value is None
    ):
        raise ValueError("published_apply_acknowledgement_evidence_missing")
    return AttemptAcknowledgementEvidence(
        apply_attempt_id=runtime_admission.apply_attempt_id,
        retention_owner_run_id=runtime_admission.retention_owner_run_id,
        retention_fence_path=attempt[0],  # type: ignore[arg-type]
        retention_fence_identity=attempt[1],  # type: ignore[arg-type]
        retention_fence_sha256=attempt[2],  # type: ignore[arg-type]
        journal_path=journal[0],  # type: ignore[arg-type]
        journal_identity=journal[1],  # type: ignore[arg-type]
        journal_sha256=journal[2],  # type: ignore[arg-type]
        target_owner_journal_path=owner[0],  # type: ignore[arg-type]
        target_owner_journal_identity=owner[1],  # type: ignore[arg-type]
        target_owner_journal_sha256=owner[2],  # type: ignore[arg-type]
        target_path=Path(str(target_path_value)),
        target_identity=tuple(target_identity_value),
        package_root_sha256=runtime_admission.package_root_sha256,
        runtime_admission_path=runtime_admission.admission_path,
        runtime_admission_parent_identity=(
            runtime_admission.admission_parent_identity
        ),
        runtime_admission_identity=runtime_admission.admission_identity,
        runtime_admission_sha256=runtime_admission.admission_sha256,
        journal_owns_target=owns_target,
        acknowledgement_action=(
            "retain_target_owner_delete_fence"
            if owns_target
            else "delete_nonowning_attempt_and_fence"
        ),
    )


def _acknowledgement_from_terminal_cursor(
    cursor: LiveStartSession,
) -> AttemptAcknowledgementEvidence | None:
    acknowledgement = cursor.attempt_acknowledgement
    if acknowledgement is None:
        return None
    if not isinstance(acknowledgement, Mapping):
        raise live_start_session.SessionConflictError(
            "published_apply_acknowledgement_evidence_missing"
        )
    action = acknowledgement.get("acknowledgement_action")
    if action not in {
        "retain_target_owner_delete_fence",
        "delete_nonowning_attempt_and_fence",
    }:
        raise live_start_session.SessionConflictError(
            "published_apply_acknowledgement_evidence_missing"
        )
    evidence = AttemptAcknowledgementEvidence(
        apply_attempt_id=str(acknowledgement.get("apply_attempt_id")),
        retention_owner_run_id=str(
            acknowledgement.get("retention_owner_run_id")
        ),
        retention_fence_path=Path(
            str(acknowledgement.get("retention_fence_path"))
        ),
        retention_fence_identity=tuple(
            acknowledgement.get("retention_fence_identity", ())
        ),
        retention_fence_sha256=str(
            acknowledgement.get("retention_fence_sha256")
        ),
        journal_path=Path(str(acknowledgement.get("journal_path"))),
        journal_identity=tuple(acknowledgement.get("journal_identity", ())),
        journal_sha256=str(acknowledgement.get("journal_sha256")),
        target_owner_journal_path=Path(
            str(acknowledgement.get("target_owner_journal_path"))
        ),
        target_owner_journal_identity=tuple(
            acknowledgement.get("target_owner_journal_identity", ())
        ),
        target_owner_journal_sha256=str(
            acknowledgement.get("target_owner_journal_sha256")
        ),
        target_path=Path(str(acknowledgement.get("target_path"))),
        target_identity=tuple(acknowledgement.get("target_identity", ())),
        package_root_sha256=str(
            acknowledgement.get("package_root_sha256")
        ),
        runtime_admission_path=Path(
            str(acknowledgement.get("runtime_admission_path"))
        ),
        runtime_admission_parent_identity=tuple(
            acknowledgement.get("runtime_admission_parent_identity", ())
        ),
        runtime_admission_identity=tuple(
            acknowledgement.get("runtime_admission_identity", ())
        ),
        runtime_admission_sha256=str(
            acknowledgement.get("runtime_admission_sha256")
        ),
        journal_owns_target=bool(
            acknowledgement.get("journal_owns_target")
        ),
        acknowledgement_action=cast(
            Literal[
                "retain_target_owner_delete_fence",
                "delete_nonowning_attempt_and_fence",
            ],
            action,
        ),
    )
    if (
        _sealed_attempt_acknowledgement(
            run_id=cursor.run_id,
            evidence=evidence,
        )
        != acknowledgement
    ):
        raise live_start_session.SessionConflictError(
            "published_apply_acknowledgement_evidence_missing"
        )
    return evidence


def _recover_prepared_apply_not_started_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
) -> LiveStartSession:
    pending = expected_session.pending_transition
    if (
        expected_session.phase is not LiveStartPhase.PUBLICATION_COMMITTED
        or not isinstance(pending, Mapping)
        or pending.get("operation") != "install_apply_invocation"
        or pending.get("stage") != "PREPARED"
        or expected_session.apply_recovery is not None
        or expected_session.apply_invocation_sha256 is not None
        or expected_session.runtime_admission_binding is not None
        or expected_session.runtime_layout_bootstrap is not None
    ):
        raise live_start_session.SessionConflictError(
            "published_apply_prepared_rollback_invalid"
        )
    from hsconfig.live_start_controller import (
        load_bound_output_operation_admission,
    )

    historical = _semantic_historical_output_operation_evidence(
        evidence=load_bound_output_operation_admission(expected_session),
        profile_lease=profile_lease,
        expected_session=expected_session,
    )
    publication = expected_session.publication_binding
    if not isinstance(publication, Mapping):
        raise ValueError("published_apply_publication_missing")
    output_root = Path(str(publication["output_child_path"]))
    with lease_package_input(output_root) as package_lease:
        _require_package_binding(
            package_lease=package_lease,
            expected_session=expected_session,
            output_root=output_root,
            publication_content_root_sha256=str(
                publication["content_root_sha256"]
            ),
        )
        runtime_root = profile_lease.profile.runtime_root
        with lease_controller_apply_pair(
            package_lease=package_lease,
            session_lease=session_lease,
            expected_session=expected_session,
            profile_lease=profile_lease,
            output_operation_lease=output_operation_lease,
            output_operation_admission=historical,
            runtime_admission=None,
            runtime_root=runtime_root,
            expected_root_identity=path_identity(runtime_root),
            allow_runtime_lock_bootstrap=False,
        ) as lease_pair:
            apply_attempt_id = pending.get("apply_attempt_id")
            if not isinstance(apply_attempt_id, str):
                raise ValueError("published_apply_attempt_id_missing")
            authority = _build_apply_authority(
                session_lease=session_lease,
                expected_session=expected_session,
                profile_lease=profile_lease,
                output_operation_admission=historical,
                package_lease=package_lease,
                lease_pair=lease_pair,
                runtime_root=runtime_root,
                apply_attempt_id=apply_attempt_id,
            )
            invocation, raw, final_path, staging_path, inner_path, _inventory = (
                authority
            )
            if (
                invocation.content_sha256
                != pending.get("apply_invocation_sha256")
                or len(invocation.canonical_json)
                != pending.get("apply_invocation_document_size")
                or str(final_path) != pending.get("runtime_admission_path")
                or str(staging_path)
                != pending.get("runtime_admission_staging_path")
                or str(inner_path)
                != pending.get("runtime_admission_staging_inner_temp_path")
                or load_runtime_live_attempt_admission() is not None
                or os.path.lexists(final_path)
            ):
                raise live_start_session.SessionCapabilityError(
                    "published_apply_prepared_rollback_surfaces_invalid"
                )
            cleanup_authorization = (
                live_start_session._authorize_runtime_admission_under_lock(
                    session_lease=session_lease,
                    expected_admission_session=expected_session,
                    action="retire_unbound_runtime_admission_staging",
                )
            )
            cleanup_receipt = _execute_runtime_admission_file_action_from_pair(
                lease_pair=lease_pair,
                session_lease=session_lease,
                expected_session=expected_session,
                admission_authorization=cleanup_authorization,
                payload=raw,
            )
            return live_start_session.resume_pending_apply_invocation_under_lock(
                session_lease=session_lease,
                expected_session=expected_session,
                invocation=invocation,
                runtime_admission=None,
                transition="rollback_prepared",
                physical_step_receipt=cleanup_receipt,
            )


@contextmanager
def apply_and_match_published(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    output_operation_admission: OutputOperationAdmissionEvidence,
    output_root: Path,
    publication_content_root_sha256: str,
    runtime_root: Path,
    apply_attempt_id: str,
) -> Iterator[HeldApplyAndMatchPublished]:
    with _apply_and_match_published(
        session_lease=session_lease,
        expected_session=expected_session,
        profile_lease=profile_lease,
        output_operation_lease=output_operation_lease,
        output_operation_admission=output_operation_admission,
        output_root=output_root,
        publication_content_root_sha256=publication_content_root_sha256,
        runtime_root=runtime_root,
        apply_attempt_id=apply_attempt_id,
        fault_hook=no_live_start_fault,
    ) as held:
        yield held


@contextmanager
def _apply_and_match_published(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    output_operation_admission: OutputOperationAdmissionEvidence,
    output_root: Path,
    publication_content_root_sha256: str,
    runtime_root: Path,
    apply_attempt_id: str,
    fault_hook: LiveStartFaultHook,
) -> Iterator[HeldApplyAndMatchPublished]:
    physical_output_operation_admission = _require_entry_context(
        session_lease=session_lease,
        expected_session=expected_session,
        profile_lease=profile_lease,
        output_operation_lease=output_operation_lease,
        output_operation_admission=output_operation_admission,
        output_root=output_root,
        publication_content_root_sha256=publication_content_root_sha256,
        runtime_root=runtime_root,
    )
    with lease_package_input(output_root) as package_lease:
        _require_package_binding(
            package_lease=package_lease,
            expected_session=expected_session,
            output_root=output_root,
            publication_content_root_sha256=publication_content_root_sha256,
        )
        with lease_controller_apply_pair(
            package_lease=package_lease,
            session_lease=session_lease,
            expected_session=expected_session,
            profile_lease=profile_lease,
            output_operation_lease=output_operation_lease,
            output_operation_admission=physical_output_operation_admission,
            runtime_admission=None,
            runtime_root=runtime_root,
            expected_root_identity=path_identity(runtime_root),
        ) as lease_pair:
            authority = _build_apply_authority(
                session_lease=session_lease,
                expected_session=expected_session,
                profile_lease=profile_lease,
                output_operation_admission=physical_output_operation_admission,
                package_lease=package_lease,
                lease_pair=lease_pair,
                runtime_root=runtime_root,
                apply_attempt_id=apply_attempt_id,
            )
            (
                invocation,
                admission_raw,
                admission_path,
                staging,
                inner,
                runtime_inventory_sha256,
            ) = authority
            cursor, runtime_admission = _claim_runtime_admission(
                lease_pair=lease_pair,
                session_lease=session_lease,
                cursor=expected_session,
                invocation=invocation,
                admission_raw=admission_raw,
                admission_path=admission_path,
                admission_staging_path=staging,
                admission_inner_temp_path=inner,
                profile_lease=profile_lease,
                runtime_inventory_sha256=runtime_inventory_sha256,
                fault_hook=fault_hook,
            )
            invoke_live_start_fault(
                fault_hook,
                LiveStartFaultPoint.AFTER_ADMISSION_BOUND_BEFORE_INVOCATION_WRITE,
            )
            prepared = prepare_package_install_from_lease(
                lease_pair=lease_pair,
                invocation=invocation,
                runtime_admission=runtime_admission,
            )
            cursor = _complete_layout_and_receipt(
                prepared=prepared,
                lease_pair=lease_pair,
                session_lease=session_lease,
                cursor=cursor,
                profile_lease=profile_lease,
                output_operation_lease=output_operation_lease,
                output_operation_admission=physical_output_operation_admission,
                runtime_admission=runtime_admission,
                invocation=invocation,
                fault_hook=fault_hook,
            )
            _release_output_operation_handoff(
                lease_pair=lease_pair,
                session_lease=session_lease,
                cursor=cursor,
                profile_lease=profile_lease,
                output_operation_lease=output_operation_lease,
                historical=physical_output_operation_admission,
                runtime_admission=runtime_admission,
                fault_hook=fault_hook,
            )

            cursor = _prepare_initial_recovery(
                plan=prepared.plan,
                lease_pair=lease_pair,
                session_lease=session_lease,
                cursor=cursor,
                profile_lease=profile_lease,
                historical=physical_output_operation_admission,
                package_lease=package_lease,
                runtime_admission=runtime_admission,
                invocation=invocation,
                fault_hook=fault_hook,
            )
            cursor = _drive_recovery_rows(
                plan=prepared.plan,
                lease_pair=lease_pair,
                session_lease=session_lease,
                cursor=cursor,
                runtime_admission=runtime_admission,
                fault_hook=fault_hook,
            )
            raw_status: Literal["applied", "already_current", "recovered"] = (
                "already_current"
                if invocation.pre_apply_runtime_snapshot.mapping_value
                == prepared.plan.versioned_config_dir
                else "applied"
            )
            cursor, result, acknowledgement = _finish_stable_recovery(
                plan=prepared.plan,
                lease_pair=lease_pair,
                session_lease=session_lease,
                cursor=cursor,
                runtime_admission=runtime_admission,
                raw_apply_status=raw_status,
                fault_hook=fault_hook,
                fire_installer_faults=True,
            )
            revalidate_package_input_lease(package_lease)
            held = HeldApplyAndMatchPublished(
                updated_session=cursor,
                invocation=invocation,
                result=result,
                acknowledgement_evidence=acknowledgement,
                runtime_admission=runtime_admission,
                session_lease=session_lease,
                profile_lease=profile_lease,
                lease_pair=lease_pair,
                fault_hook=fault_hook,
            )
            with _validated_held_yield(held=held, exposed=held):
                yield held


def _is_terminal_resolution_recovery(
    cursor: LiveStartSession,
) -> bool:
    intent = cursor.result_intent
    retirement = cursor.terminal_retirement
    closed_recovery = cursor.closed_apply_recovery_commitment
    terminal_authority_valid = (
        retirement is None
        and isinstance(closed_recovery, Mapping)
        and closed_recovery.get("recovery_stage") == "CLOSED"
    ) or (
        isinstance(retirement, Mapping)
        and retirement.get("operation") == "release_resolved_terminal"
        and closed_recovery is None
    )
    return (
        cursor.phase
        in {
            LiveStartPhase.APPLY_STARTED,
            LiveStartPhase.APPLY_COMMITTED,
            LiveStartPhase.RUNTIME_MATCHED,
        }
        and cursor.pending_transition is None
        and cursor.apply_recovery is None
        and cursor.terminal_status
        in {
            "APPLIED_BUT_NOT_VERIFIED",
            "FAILED_PRESERVED",
        }
        and isinstance(intent, Mapping)
        and intent.get("terminal_status") == cursor.terminal_status
        and _terminal_result_requires_resolution(intent)
        and cursor.attempt_acknowledgement is None
        and terminal_authority_valid
    )


def _is_result_completion_recovery(cursor: LiveStartSession) -> bool:
    intent = cursor.result_intent
    closed_recovery = cursor.closed_apply_recovery_commitment
    terminal_status = (
        intent.get("terminal_status") if isinstance(intent, Mapping) else None
    )
    success = terminal_status in {"LIVE_AND_MATCHED", "ALREADY_LIVE"}
    failure = terminal_status in {
        "FAILED_PRESERVED",
        "APPLIED_BUT_NOT_VERIFIED",
    }
    acknowledgement = cursor.attempt_acknowledgement
    return (
        cursor.phase
        in {
            LiveStartPhase.APPLY_STARTED,
            LiveStartPhase.APPLY_COMMITTED,
            LiveStartPhase.RUNTIME_MATCHED,
        }
        and cursor.pending_transition is None
        and cursor.apply_recovery is None
        and cursor.terminal_status is None
        and cursor.terminal_retirement is None
        and isinstance(closed_recovery, Mapping)
        and closed_recovery.get("recovery_stage") == "CLOSED"
        and isinstance(intent, Mapping)
        and (success or failure)
        and (
            isinstance(acknowledgement, Mapping)
            if success
            else acknowledgement is None
        )
        and all(
            logical_path not in cursor.artifact_bindings
            for logical_path in ("result/summary.json", "result/summary.md")
        )
    )


def _stable_terminal_operation_without_retirement(
    cursor: LiveStartSession,
) -> Literal[
    "ack_success",
    "release_not_committed",
    "release_committed_mismatch",
] | None:
    intent = cursor.result_intent
    closed_recovery = cursor.closed_apply_recovery_commitment
    if (
        cursor.phase
        not in {
            LiveStartPhase.APPLY_STARTED,
            LiveStartPhase.APPLY_COMMITTED,
            LiveStartPhase.RUNTIME_MATCHED,
        }
        or cursor.pending_transition is not None
        or cursor.apply_recovery is not None
        or cursor.terminal_retirement is not None
        or cursor.terminal_status is None
        or not isinstance(intent, Mapping)
        or intent.get("terminal_status") != cursor.terminal_status
        or not isinstance(closed_recovery, Mapping)
        or closed_recovery.get("recovery_stage") != "CLOSED"
    ):
        return None
    matches = tuple(
        operation
        for operation in (
            "ack_success",
            "release_not_committed",
            "release_committed_mismatch",
        )
        if live_start_session._terminal_operation_matches_authority(
            operation=operation,
            terminal_status=cursor.terminal_status,
            result_intent=intent,
            attempt_acknowledgement=cursor.attempt_acknowledgement,
            has_resolution=False,
        )
    )
    if len(matches) > 1:
        raise live_start_session.SessionConflictError(
            "published_apply_terminal_operation_ambiguous"
        )
    return cast(
        Literal[
            "ack_success",
            "release_not_committed",
            "release_committed_mismatch",
        ]
        | None,
        matches[0] if matches else None,
    )


def _is_stable_terminal_retirement_recovery(
    cursor: LiveStartSession,
) -> bool:
    retirement = cursor.terminal_retirement
    intent = cursor.result_intent
    if retirement is None:
        return _stable_terminal_operation_without_retirement(cursor) is not None
    if not isinstance(retirement, Mapping) or not isinstance(intent, Mapping):
        return False
    operation = retirement.get("operation")
    stage = retirement.get("stage")
    allowed_stages = {
        "ack_success": {
            "PREPARED",
            "ACK_JOURNAL_RETIRED",
            "EVIDENCE_RETIRED",
        },
        "release_not_committed": {"PREPARED", "EVIDENCE_RETIRED"},
        "release_committed_mismatch": {"PREPARED", "EVIDENCE_RETIRED"},
    }
    acknowledgement_valid = (
        isinstance(cursor.attempt_acknowledgement, Mapping)
        if operation == "ack_success"
        else cursor.attempt_acknowledgement is None
    )
    return (
        operation in allowed_stages
        and stage in allowed_stages[operation]
        and cursor.phase
        in {
            LiveStartPhase.APPLY_STARTED,
            LiveStartPhase.APPLY_COMMITTED,
            LiveStartPhase.RUNTIME_MATCHED,
        }
        and cursor.pending_transition is None
        and cursor.apply_recovery is None
        and cursor.closed_apply_recovery_commitment is None
        and cursor.terminal_status is not None
        and intent.get("terminal_status") == cursor.terminal_status
        and retirement.get("result_intent_sha256")
        == intent.get("content_sha256")
        and acknowledgement_valid
    )


def _load_release_authorized_runtime_context(
    *,
    session_lease: LiveStartSessionLease,
    cursor: LiveStartSession,
) -> tuple[
    RuntimeLiveAttemptAdmissionEvidence,
    ApplyAndMatchPublishedResult,
]:
    retirement = cursor.terminal_retirement
    intent = cursor.result_intent
    admission = cursor.runtime_admission_binding
    operation = cursor.output_operation_admission_binding
    child = cursor.output_child_binding
    publication = cursor.publication_binding
    layout = cursor.runtime_layout_bootstrap
    if not all(
        isinstance(value, Mapping)
        for value in (
            retirement,
            intent,
            admission,
            operation,
            child,
            publication,
            layout,
        )
    ):
        raise live_start_session.SessionCapabilityError(
            "published_apply_terminal_release_context_invalid"
        )
    if not isinstance(retirement, Mapping):
        raise live_start_session.SessionCapabilityError(
            "published_apply_terminal_retirement_missing"
        )
    if not isinstance(intent, Mapping):
        raise live_start_session.SessionCapabilityError(
            "published_apply_terminal_result_intent_invalid"
        )
    if not isinstance(admission, Mapping):
        raise live_start_session.SessionCapabilityError(
            "published_apply_runtime_admission_missing"
        )
    if not isinstance(operation, Mapping):
        raise live_start_session.SessionCapabilityError(
            "published_apply_output_operation_binding_missing"
        )
    if not isinstance(child, Mapping):
        raise live_start_session.SessionCapabilityError(
            "published_apply_output_child_binding_missing"
        )
    if not isinstance(publication, Mapping):
        raise live_start_session.SessionCapabilityError(
            "published_apply_publication_binding_missing"
        )
    if not isinstance(layout, Mapping):
        raise live_start_session.SessionCapabilityError(
            "published_apply_runtime_layout_binding_missing"
        )

    invocation_path = session_lease.session_root / "receipts" / "apply_invocation.json"
    invocation = load_apply_invocation(
        invocation_path,
        expected_parent_identity=path_identity(invocation_path.parent),
    )
    expected = RuntimeLiveAttemptAdmissionEvidence(
        admission_path=Path(str(admission.get("admission_path"))),
        admission_parent_identity=tuple(
            admission.get("admission_parent_identity", ())
        ),
        admission_identity=tuple(admission.get("admission_identity", ())),
        admission_sha256=str(admission.get("admission_sha256")),
        run_id=cursor.run_id,
        apply_attempt_id=invocation.apply_attempt_id,
        retention_owner_run_id=cursor.run_id,
        session_root=session_lease.session_root,
        session_root_identity=session_lease.session_root_identity,
        operator_profile_sha256=invocation.operator_profile_sha256,
        state_root_identity=tuple(operation.get("state_root_identity", ())),
        runtime_root=invocation.runtime_root,
        runtime_root_identity=invocation.runtime_root_identity,
        output_base_root=Path(str(operation.get("output_base_root"))),
        output_base_root_identity=tuple(
            operation.get("output_base_root_identity", ())
        ),
        output_root=invocation.output_child_path,
        output_root_identity=invocation.output_child_identity,
        output_operation_admission_path=(
            invocation.output_operation_admission_path
        ),
        output_operation_admission_identity=(
            invocation.output_operation_admission_identity
        ),
        output_operation_admission_sha256=(
            invocation.output_operation_admission_sha256
        ),
        output_child_binding_sha256=(
            invocation.output_child_binding_sha256
        ),
        publication_revision=invocation.publication_revision,
        publication_content_root_sha256=(
            invocation.publication_content_root_sha256
        ),
        package_root_sha256=invocation.publication_content_root_sha256,
        pre_apply_runtime_snapshot_sha256=(
            invocation.pre_apply_runtime_snapshot.content_sha256
        ),
        apply_invocation_sha256=invocation.content_sha256,
        retention_fence_path=(
            invocation.runtime_root
            / ".hsconfig"
            / "attempt-retention"
            / f"{invocation.apply_attempt_id}.json"
        ),
    )
    quartet = {
        "runtime_admission_path": str(expected.admission_path),
        "runtime_admission_parent_identity": (
            expected.admission_parent_identity
        ),
        "runtime_admission_identity": expected.admission_identity,
        "runtime_admission_sha256": expected.admission_sha256,
    }
    handoff_quartet = {
        "handoff_runtime_admission_path": str(expected.admission_path),
        "handoff_runtime_admission_parent_identity": (
            expected.admission_parent_identity
        ),
        "handoff_runtime_admission_identity": expected.admission_identity,
        "handoff_runtime_admission_sha256": expected.admission_sha256,
    }
    invalid = (
        expected.admission_path != runtime_live_attempt_admission_path()
        or cursor.phase
        not in {
            LiveStartPhase.APPLY_STARTED,
            LiveStartPhase.APPLY_COMMITTED,
            LiveStartPhase.RUNTIME_MATCHED,
        }
        or cursor.pending_transition is not None
        or cursor.apply_recovery is not None
        or cursor.terminal_status is None
        or cursor.terminal_status != intent.get("terminal_status")
        or retirement.get("stage") != "ADMISSION_RELEASE_AUTHORIZED"
        or retirement.get("run_id") != cursor.run_id
        or retirement.get("apply_attempt_id") != invocation.apply_attempt_id
        or intent.get("run_id") != cursor.run_id
        or intent.get("apply_attempt_id") != invocation.apply_attempt_id
        or cursor.apply_invocation_sha256 != invocation.content_sha256
        or cursor.artifact_bindings.get("receipts/apply_invocation.json")
        != "sha256:" + hashlib.sha256(invocation.canonical_json).hexdigest()
        or invocation.run_id != cursor.run_id
        or operation.get("state") != "RUNTIME_HANDOFF_RELEASE_AUTHORIZED"
        or operation.get("release_handoff_kind") != "runtime_admission"
        or operation.get("session_root") != str(session_lease.session_root)
        or tuple(operation.get("session_root_identity", ()))
        != session_lease.session_root_identity
        or operation.get("operator_profile_sha256")
        != invocation.operator_profile_sha256
        or tuple(operation.get("state_root_identity", ()))
        != expected.admission_parent_identity
        or child.get("output_base_path") != str(expected.output_base_root)
        or tuple(child.get("output_base_identity", ()))
        != expected.output_base_root_identity
        or child.get("output_child_path") != str(expected.output_root)
        or tuple(child.get("output_child_identity", ()))
        != expected.output_root_identity
        or child.get("content_sha256")
        != expected.output_child_binding_sha256
        or publication.get("output_child_path") != str(expected.output_root)
        or tuple(publication.get("output_child_identity", ()))
        != expected.output_root_identity
        or publication.get("output_child_binding_sha256")
        != expected.output_child_binding_sha256
        or publication.get("revision") != expected.publication_revision
        or publication.get("content_root_sha256")
        != expected.publication_content_root_sha256
        or intent.get("publication_revision")
        != expected.publication_revision
        or intent.get("publication_content_root_sha256")
        != expected.publication_content_root_sha256
        or layout.get("stage") != "COMPLETE"
        or layout.get("run_id") != cursor.run_id
        or layout.get("apply_attempt_id") != invocation.apply_attempt_id
        or layout.get("runtime_root") != str(expected.runtime_root)
        or tuple(layout.get("runtime_root_identity", ()))
        != expected.runtime_root_identity
        or admission.get("output_operation_admission_path")
        != str(expected.output_operation_admission_path)
        or tuple(admission.get("output_operation_admission_identity", ()))
        != expected.output_operation_admission_identity
        or admission.get("output_operation_admission_sha256")
        != expected.output_operation_admission_sha256
        or admission.get("output_child_binding_sha256")
        != expected.output_child_binding_sha256
        or admission.get("output_child_path") != str(expected.output_root)
        or tuple(admission.get("output_child_identity", ()))
        != expected.output_root_identity
        or admission.get("publication_revision")
        != expected.publication_revision
        or admission.get("publication_content_root_sha256")
        != expected.publication_content_root_sha256
        or any(
            retirement.get(field_name) != expected_value
            for field_name, expected_value in quartet.items()
        )
        or any(
            intent.get(field_name) != expected_value
            for field_name, expected_value in quartet.items()
        )
        or any(
            operation.get(field_name) != expected_value
            for field_name, expected_value in handoff_quartet.items()
        )
    )
    if invalid:
        raise live_start_session.SessionCapabilityError(
            "published_apply_terminal_release_context_invalid"
        )
    try:
        projected_admission = _project_runtime_live_attempt_admission_bytes(
            run_id=expected.run_id,
            apply_attempt_id=expected.apply_attempt_id,
            retention_owner_run_id=expected.retention_owner_run_id,
            session_root=expected.session_root,
            session_root_identity=expected.session_root_identity,
            operator_profile_sha256=expected.operator_profile_sha256,
            state_root_identity=expected.state_root_identity,
            runtime_root=expected.runtime_root,
            runtime_root_identity=expected.runtime_root_identity,
            output_base_root=expected.output_base_root,
            output_base_root_identity=expected.output_base_root_identity,
            output_root=expected.output_root,
            output_root_identity=expected.output_root_identity,
            output_operation_admission_path=(
                expected.output_operation_admission_path
            ),
            output_operation_admission_identity=(
                expected.output_operation_admission_identity
            ),
            output_operation_admission_sha256=(
                expected.output_operation_admission_sha256
            ),
            output_child_binding_sha256=(
                expected.output_child_binding_sha256
            ),
            publication_revision=expected.publication_revision,
            publication_content_root_sha256=(
                expected.publication_content_root_sha256
            ),
            package_root_sha256=expected.package_root_sha256,
            pre_apply_runtime_snapshot_sha256=(
                expected.pre_apply_runtime_snapshot_sha256
            ),
            apply_invocation_sha256=expected.apply_invocation_sha256,
            retention_fence_path=expected.retention_fence_path,
        )
    except (TypeError, ValueError) as error:
        raise live_start_session.SessionCapabilityError(
            "published_apply_terminal_release_context_invalid"
        ) from error
    projected_admission_sha256 = (
        "sha256:" + hashlib.sha256(projected_admission).hexdigest()
    )
    if projected_admission_sha256 != expected.admission_sha256:
        raise live_start_session.SessionCapabilityError(
            "published_apply_terminal_release_context_invalid"
        )
    return (
        expected,
        _result_from_bound_terminal_intent(
            intent=intent,
            runtime_admission=expected,
        ),
    )


def recover_apply_attempt(*, session_root: Path) -> RecoverApplyResult:
    with live_start_session.lease_live_start_session(
        session_root,
    ) as session_lease:
        root = session_lease.session_root
        cursor = live_start_session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        retirement = cursor.terminal_retirement
        if (
            isinstance(retirement, Mapping)
            and retirement.get("stage") == "ADMISSION_RELEASE_AUTHORIZED"
        ):
            runtime_admission, historical_result = (
                _load_release_authorized_runtime_context(
                    session_lease=session_lease,
                    cursor=cursor,
                )
            )
            terminal_authorization = (
                live_start_session.authorize_terminal_retirement_under_lock(
                    session_lease=session_lease,
                    expected_retirement_session=cursor,
                )
            )
            _release_or_confirm_runtime_live_attempt_without_old_leases(
                session_lease=session_lease,
                expected_release_authorized_session=cursor,
                terminal_authorization=terminal_authorization,
                expected=runtime_admission,
            )
            return historical_result
        terminal_resolution_recovery = _is_terminal_resolution_recovery(cursor)
        stable_terminal_retirement_recovery = (
            _is_stable_terminal_retirement_recovery(cursor)
        )
        stable_terminal_operation = (
            str(cursor.terminal_retirement["operation"])
            if stable_terminal_retirement_recovery
            and isinstance(cursor.terminal_retirement, Mapping)
            else _stable_terminal_operation_without_retirement(cursor)
        )
        if (
            cursor.phase is LiveStartPhase.PUBLICATION_COMMITTED
            and cursor.pending_transition is None
            and cursor.apply_recovery is None
        ):
            return RecoverApplyNotStarted(
                status="apply_not_started",
                run_id=cursor.run_id,
                session_root=root,
                session_root_identity=session_lease.session_root_identity,
                persisted_session_sha256=cursor.content_sha256,
                runtime_write_performed=False,
            )
        profile = load_operator_profile()
        with lease_operator_profile(expected_profile=profile) as profile_lease:
            with lease_output_operation_admission() as operation_lease:
                pending = cursor.pending_transition
                if (
                    cursor.phase is LiveStartPhase.PUBLICATION_COMMITTED
                    and isinstance(pending, Mapping)
                    and pending.get("operation") == "install_apply_invocation"
                    and pending.get("stage") == "PREPARED"
                ):
                    cursor = _recover_prepared_apply_not_started_under_lock(
                        session_lease=session_lease,
                        expected_session=cursor,
                        profile_lease=profile_lease,
                        output_operation_lease=operation_lease,
                    )
                    return RecoverApplyNotStarted(
                        status="apply_not_started",
                        run_id=cursor.run_id,
                        session_root=root,
                        session_root_identity=(
                            session_lease.session_root_identity
                        ),
                        persisted_session_sha256=cursor.content_sha256,
                        runtime_write_performed=False,
                    )
                with recover_apply_attempt_under_lock(
                    session_lease=session_lease,
                    profile_lease=profile_lease,
                    expected_session=cursor,
                    output_operation_lease=operation_lease,
                ) as recovered:
                    result = recovered.held.result
                    terminal_cursor = recovered.updated_session
                    newly_terminalized = terminal_cursor.terminal_status is None
                    if newly_terminalized:
                        if terminal_cursor.result_intent is None:
                            terminal_cursor = _terminalize_held_recovery_result(
                                session_lease=session_lease,
                                held=recovered.held,
                            )
                        else:
                            terminal_cursor = (
                                live_start_session.complete_live_start_under_lock(
                                    session_lease=session_lease,
                                    expected_result_session=terminal_cursor,
                                )
                            )
                        stable_terminal_operation = (
                            _stable_terminal_operation_without_retirement(
                                terminal_cursor
                            )
                        )
                        terminal_resolution_recovery = (
                            _is_terminal_resolution_recovery(terminal_cursor)
                            and result.physical_disposition
                            is PhysicalApplyDisposition.NOT_COMMITTED
                        )
                    if stable_terminal_operation == "ack_success":
                        terminal_cursor = (
                            recovered.held.acknowledge_after_terminal(
                                session_lease=session_lease,
                                expected_terminal_session=terminal_cursor,
                            )
                        )
                    elif stable_terminal_operation == "release_not_committed":
                        terminal_cursor = (
                            recovered.held.release_admission_after_terminal(
                                session_lease=session_lease,
                                expected_terminal_session=terminal_cursor,
                            )
                        )
                    elif (
                        stable_terminal_operation
                        == "release_committed_mismatch"
                    ):
                        terminal_cursor = (
                            recovered.held.resolve_and_release_after_terminal(
                                session_lease=session_lease,
                                expected_terminal_session=terminal_cursor,
                            )
                        )
                    elif terminal_resolution_recovery:
                        terminal_cursor = (
                            recovered.held.resolve_and_release_after_terminal(
                                session_lease=session_lease,
                                expected_terminal_session=terminal_cursor,
                            )
                        )
                    return result


@contextmanager
def recover_apply_attempt_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    expected_session: LiveStartSession,
) -> Iterator[HeldRecoveredApplyAndMatch]:
    with _recover_apply_attempt_under_lock(
        session_lease=session_lease,
        profile_lease=profile_lease,
        output_operation_lease=output_operation_lease,
        expected_session=expected_session,
        fault_hook=no_live_start_fault,
    ) as recovered:
        yield recovered


@contextmanager
def _recover_apply_attempt_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    expected_session: LiveStartSession,
    fault_hook: LiveStartFaultHook,
) -> Iterator[HeldRecoveredApplyAndMatch]:
    if (
        not isinstance(session_lease, LiveStartSessionLease)
        or not isinstance(profile_lease, OperatorProfileLease)
        or not isinstance(output_operation_lease, OutputOperationAdmissionLease)
        or not isinstance(expected_session, LiveStartSession)
    ):
        raise TypeError("published_apply_recovery_context_invalid")
    persisted = live_start_session.load_live_start_session_under_lock(
        session_lease=session_lease
    )
    if (
        persisted != expected_session
        or persisted.canonical_json != expected_session.canonical_json
        or persisted.session_identity != expected_session.session_identity
    ):
        raise live_start_session.SessionConflictError(
            "published_apply_recovery_session_invalid"
        )
    cursor = expected_session
    pending = cursor.pending_transition
    pre_admission_continuation = (
        cursor.phase is LiveStartPhase.PUBLICATION_COMMITTED
        and isinstance(pending, Mapping)
        and pending.get("operation") == "install_apply_invocation"
        and pending.get("stage") == "STAGING_BOUND"
        and cursor.apply_recovery is None
    )
    pre_receipt_continuation = (
        cursor.phase is LiveStartPhase.PUBLICATION_COMMITTED
        and isinstance(pending, Mapping)
        and pending.get("operation") == "install_apply_invocation"
        and pending.get("stage") == "PRIMARY_APPLIED"
        and cursor.apply_recovery is None
    )
    nonterminal_recovery = (
        cursor.phase
        in {
            LiveStartPhase.APPLY_STARTED,
            LiveStartPhase.APPLY_COMMITTED,
            LiveStartPhase.RUNTIME_MATCHED,
        }
        and pending is None
    )
    terminal_resolution_recovery = _is_terminal_resolution_recovery(cursor)
    result_completion_recovery = _is_result_completion_recovery(cursor)
    stable_terminal_retirement_recovery = (
        _is_stable_terminal_retirement_recovery(cursor)
    )
    if (
        not (
            pre_receipt_continuation
            or pre_admission_continuation
            or nonterminal_recovery
            or result_completion_recovery
            or terminal_resolution_recovery
            or stable_terminal_retirement_recovery
        )
        or (
            not (
                terminal_resolution_recovery
                or result_completion_recovery
                or stable_terminal_retirement_recovery
            )
            and (
                cursor.result_intent is not None
                or cursor.terminal_status is not None
            )
        )
    ):
        raise live_start_session.SessionConflictError(
            "published_apply_recovery_session_invalid"
        )
    revalidate_operator_profile_lease(profile_lease)
    from hsconfig.live_start_controller import (
        load_bound_output_operation_admission,
    )

    historical = _semantic_historical_output_operation_evidence(
        evidence=load_bound_output_operation_admission(cursor),
        profile_lease=profile_lease,
        expected_session=cursor,
    )
    publication = cursor.publication_binding
    if not isinstance(publication, Mapping):
        raise ValueError("published_apply_publication_missing")
    output_root = Path(str(publication["output_child_path"]))
    publication_sha256 = str(publication["content_root_sha256"])
    runtime_admission = load_runtime_live_attempt_admission()
    if runtime_admission is None and not pre_admission_continuation:
        raise live_start_session.SessionCapabilityError(
            "published_apply_runtime_admission_missing"
        )
    if runtime_admission is not None and (
        runtime_admission.run_id != cursor.run_id
        or runtime_admission.session_root != session_lease.session_root
        or runtime_admission.session_root_identity
        != session_lease.session_root_identity
    ):
        raise live_start_session.SessionCapabilityError(
            "published_apply_recovery_invocation_invalid"
        )
    runtime_root = (
        profile_lease.profile.runtime_root
        if runtime_admission is None
        else runtime_admission.runtime_root
    )
    runtime_root_identity = (
        profile_lease.profile.runtime_root_identity
        if runtime_admission is None
        else runtime_admission.runtime_root_identity
    )
    with lease_package_input(output_root) as package_lease:
        _require_package_binding(
            package_lease=package_lease,
            expected_session=cursor,
            output_root=output_root,
            publication_content_root_sha256=publication_sha256,
        )
        with lease_controller_apply_pair(
            package_lease=package_lease,
            session_lease=session_lease,
            expected_session=cursor,
            profile_lease=profile_lease,
            output_operation_lease=output_operation_lease,
            output_operation_admission=historical,
            runtime_admission=runtime_admission,
            runtime_root=runtime_root,
            expected_root_identity=runtime_root_identity,
        ) as lease_pair:
            pair_binding = _authenticate_controller_apply_pair_binding(lease_pair)
            if pair_binding.entry_mode == "POST_HANDOFF_RELEASE_ONLY":
                if runtime_admission is None:
                    raise live_start_session.SessionCapabilityError(
                        "published_apply_runtime_admission_missing"
                    )
                _release_output_operation_handoff(
                    lease_pair=lease_pair,
                    session_lease=session_lease,
                    cursor=cursor,
                    profile_lease=profile_lease,
                    output_operation_lease=output_operation_lease,
                    historical=historical,
                    runtime_admission=runtime_admission,
                    fault_hook=fault_hook,
                )
                pair_binding = _authenticate_controller_apply_pair_binding(
                    lease_pair
                )
                if (
                    pair_binding.entry_mode != "POST_HANDOFF_READY"
                    or pair_binding.reentry_output_disposition
                    not in {"absent", "valid_foreign"}
                ):
                    raise live_start_session.SessionCapabilityError(
                        "published_apply_output_handoff_context_invalid"
                    )
            publication_value = package_lease.publication
            if publication_value is None:
                raise ValueError("published_apply_package_missing")
            if pre_admission_continuation or pre_receipt_continuation:
                if not isinstance(pending, Mapping):
                    raise live_start_session.SessionConflictError(
                        "published_apply_recovery_pending_missing"
                    )
                apply_attempt_id = pending.get("apply_attempt_id")
                if not isinstance(apply_attempt_id, str):
                    raise ValueError("published_apply_attempt_id_missing")
                authority = _build_apply_authority(
                    session_lease=session_lease,
                    expected_session=cursor,
                    profile_lease=profile_lease,
                    output_operation_admission=historical,
                    package_lease=package_lease,
                    lease_pair=lease_pair,
                    runtime_root=runtime_root,
                    apply_attempt_id=apply_attempt_id,
                )
                (
                    invocation,
                    admission_raw,
                    admission_path,
                    admission_staging_path,
                    admission_inner_temp_path,
                    runtime_inventory_sha256,
                ) = authority
                if (
                    invocation.content_sha256
                    != pending.get("apply_invocation_sha256")
                    or len(invocation.canonical_json)
                    != pending.get("apply_invocation_document_size")
                ):
                    raise live_start_session.SessionCapabilityError(
                        "published_apply_recovery_invocation_invalid"
                    )
                # A final receipt, even before its receipt CAS, makes this an
                # observation-only recovery. Only an absent receipt may still
                # complete the already admitted first-install continuation.
                receipt_was_present = False
                if pre_receipt_continuation:
                    invocation_path = (
                        session_lease.session_root / "receipts/apply_invocation.json"
                    )
                    try:
                        prior_invocation = load_apply_invocation(
                            invocation_path,
                            expected_parent_identity=path_identity(invocation_path.parent),
                        )
                    except FileNotFoundError:
                        pass
                    else:
                        if (
                            prior_invocation.canonical_json != invocation.canonical_json
                            or prior_invocation.content_sha256 != invocation.content_sha256
                        ):
                            raise live_start_session.SessionCapabilityError(
                                "published_apply_recovery_invocation_invalid"
                            )
                        receipt_was_present = True
                if pre_admission_continuation:
                    cursor, runtime_admission = _claim_runtime_admission(
                        lease_pair=lease_pair,
                        session_lease=session_lease,
                        cursor=cursor,
                        invocation=invocation,
                        admission_raw=admission_raw,
                        admission_path=admission_path,
                        admission_staging_path=admission_staging_path,
                        admission_inner_temp_path=admission_inner_temp_path,
                        profile_lease=profile_lease,
                        runtime_inventory_sha256=runtime_inventory_sha256,
                        fault_hook=fault_hook,
                    )
                if runtime_admission is None or (
                    runtime_admission.apply_invocation_sha256
                    != invocation.content_sha256
                    or runtime_admission.apply_attempt_id
                    != invocation.apply_attempt_id
                ):
                    raise live_start_session.SessionCapabilityError(
                        "published_apply_recovery_invocation_invalid"
                    )
                _require_recovery_invocation_context(
                    lease_pair=lease_pair,
                    session_lease=session_lease,
                    cursor=cursor,
                    profile_lease=profile_lease,
                    historical=historical,
                    package_lease=package_lease,
                    runtime_admission=runtime_admission,
                    invocation=invocation,
                )
                layout_value = cursor.runtime_layout_bootstrap
                resumed_layout = (
                    None
                    if layout_value is None
                    else RuntimeLayoutBootstrapEvidence(layout_value)
                )
                prepared = prepare_package_install_from_lease(
                    lease_pair=lease_pair,
                    invocation=invocation,
                    runtime_admission=runtime_admission,
                    runtime_layout_evidence=resumed_layout,
                )
                cursor = _complete_layout_and_receipt(
                    prepared=prepared,
                    lease_pair=lease_pair,
                    session_lease=session_lease,
                    cursor=cursor,
                    profile_lease=profile_lease,
                    output_operation_lease=output_operation_lease,
                    output_operation_admission=historical,
                    runtime_admission=runtime_admission,
                    invocation=invocation,
                    fault_hook=fault_hook,
                )
                _release_output_operation_handoff(
                    lease_pair=lease_pair,
                    session_lease=session_lease,
                    cursor=cursor,
                    profile_lease=profile_lease,
                    output_operation_lease=output_operation_lease,
                    historical=historical,
                    runtime_admission=runtime_admission,
                    fault_hook=fault_hook,
                )
                if not receipt_was_present:
                    cursor = _prepare_initial_recovery(
                        plan=prepared.plan,
                        lease_pair=lease_pair,
                        session_lease=session_lease,
                        cursor=cursor,
                        profile_lease=profile_lease,
                        historical=historical,
                        package_lease=package_lease,
                        runtime_admission=runtime_admission,
                        invocation=invocation,
                        fault_hook=fault_hook,
                    )
                plan = prepared.plan
            else:
                invocation_path = (
                    session_lease.session_root
                    / "receipts"
                    / "apply_invocation.json"
                )
                invocation = load_apply_invocation(
                    invocation_path,
                    expected_parent_identity=path_identity(
                        invocation_path.parent
                    ),
                )
                if (
                    cursor.apply_invocation_sha256
                    != invocation.content_sha256
                    or runtime_admission.apply_invocation_sha256
                    != invocation.content_sha256
                    or runtime_admission.apply_attempt_id
                    != invocation.apply_attempt_id
                ):
                    raise live_start_session.SessionCapabilityError(
                        "published_apply_recovery_invocation_invalid"
                    )
                _require_recovery_invocation_context(
                    lease_pair=lease_pair,
                    session_lease=session_lease,
                    cursor=cursor,
                    profile_lease=profile_lease,
                    historical=historical,
                    package_lease=package_lease,
                    runtime_admission=runtime_admission,
                    invocation=invocation,
                )
                if result_completion_recovery:
                    intent = cursor.result_intent
                    if not isinstance(intent, Mapping):
                        raise live_start_session.SessionConflictError(
                            "published_apply_terminal_result_intent_invalid"
                        )
                    result = _result_from_bound_terminal_intent(
                        intent=intent,
                        runtime_admission=runtime_admission,
                    )
                    acknowledgement = _acknowledgement_from_terminal_cursor(
                        cursor
                    )
                    if (
                        intent.get("terminal_status")
                        in {"LIVE_AND_MATCHED", "ALREADY_LIVE"}
                        and acknowledgement is None
                    ):
                        raise live_start_session.SessionConflictError(
                            "published_apply_acknowledgement_evidence_missing"
                        )
                    if acknowledgement is not None:
                        _revalidate_success_candidate_current_facts_from_pair(
                            lease_pair=lease_pair,
                            session_lease=session_lease,
                            expected_session=cursor,
                            runtime_admission=runtime_admission,
                            result=result,
                            acknowledgement=acknowledgement,
                            logical_config_dir=None,
                            runtime_config_dir=(
                                acknowledgement.target_path.name
                            ),
                        )
                    revalidate_package_input_lease(package_lease)
                    held = HeldApplyAndMatchPublished(
                        updated_session=cursor,
                        invocation=invocation,
                        result=result,
                        acknowledgement_evidence=acknowledgement,
                        runtime_admission=runtime_admission,
                        session_lease=session_lease,
                        profile_lease=profile_lease,
                        lease_pair=lease_pair,
                        fault_hook=fault_hook,
                    )
                    recovered = HeldRecoveredApplyAndMatch(held=held)
                    with _validated_held_yield(
                        held=held,
                        exposed=recovered,
                    ):
                        yield recovered
                    return
                if stable_terminal_retirement_recovery:
                    intent = cursor.result_intent
                    if not isinstance(intent, Mapping):
                        raise live_start_session.SessionConflictError(
                            "published_apply_terminal_result_intent_invalid"
                        )
                    result = _result_from_bound_terminal_intent(
                        intent=intent,
                        runtime_admission=runtime_admission,
                    )
                    acknowledgement = _acknowledgement_from_terminal_cursor(
                        cursor
                    )
                    if (
                        cursor.terminal_retirement is not None
                        and cursor.terminal_retirement.get("operation")
                        == "ack_success"
                        and acknowledgement is None
                    ):
                        raise live_start_session.SessionConflictError(
                            "published_apply_acknowledgement_evidence_missing"
                        )
                    revalidate_package_input_lease(package_lease)
                    held = HeldApplyAndMatchPublished(
                        updated_session=cursor,
                        invocation=invocation,
                        result=result,
                        acknowledgement_evidence=acknowledgement,
                        runtime_admission=runtime_admission,
                        session_lease=session_lease,
                        profile_lease=profile_lease,
                        lease_pair=lease_pair,
                        fault_hook=fault_hook,
                    )
                    recovered = HeldRecoveredApplyAndMatch(held=held)
                    with _validated_held_yield(
                        held=held,
                        exposed=recovered,
                    ):
                        yield recovered
                    return
                if terminal_resolution_recovery:
                    intent = cursor.result_intent
                    if not isinstance(intent, Mapping):
                        raise live_start_session.SessionConflictError(
                            "published_apply_terminal_result_intent_invalid"
                        )
                    result = _result_from_terminal_intent(
                        intent=intent,
                        runtime_admission=runtime_admission,
                    )
                    revalidate_package_input_lease(package_lease)
                    held = HeldApplyAndMatchPublished(
                        updated_session=cursor,
                        invocation=invocation,
                        result=result,
                        acknowledgement_evidence=None,
                        runtime_admission=runtime_admission,
                        session_lease=session_lease,
                        profile_lease=profile_lease,
                        lease_pair=lease_pair,
                        fault_hook=fault_hook,
                    )
                    recovered = HeldRecoveredApplyAndMatch(held=held)
                    with _validated_held_yield(
                        held=held,
                        exposed=recovered,
                    ):
                        yield recovered
                    return
                from hsconfig.output_publisher import PublishedOutput
                from hsconfig.runtime_installer import plan_runtime_install

                plan = plan_runtime_install(
                    published_output=PublishedOutput(
                        output_root=package_lease.output_root,
                        revision_root=package_lease.package_root.parent,
                        package_root=package_lease.package_root,
                        content_root_sha256=(
                            publication_value.content_root_sha256
                        ),
                        reused_existing_revision=True,
                    ),
                    runtime_root=runtime_admission.runtime_root,
                )
            if cursor.apply_recovery is None:
                observation_authorization = (
                    live_start_session._authorize_runtime_observation_under_lock(
                        session_lease=session_lease,
                        expected_session=cursor,
                        observation_family="nonterminal_apply",
                        apply_attempt_id=runtime_admission.apply_attempt_id,
                    )
                )
                observed = recover_runtime_attempt_from_pair(
                    lease_pair=lease_pair,
                    transaction_id=runtime_admission.apply_attempt_id,
                    expected_retention_owner_run_id=(
                        runtime_admission.retention_owner_run_id
                    ),
                    expected_package_root_sha256=(
                        runtime_admission.package_root_sha256
                    ),
                    expected_deck_name=cursor.deck_name,
                    runtime_admission=runtime_admission,
                    observation_family="nonterminal_apply",
                    runtime_observation_authorization=(
                        observation_authorization
                    ),
                )
                if observed.runtime_observation_receipt is None:
                    raise ValueError(
                        "published_apply_recovery_observation_receipt_missing"
                    )
                invoke_live_start_fault(
                    fault_hook,
                    LiveStartFaultPoint.AFTER_NONTERMINAL_OBSERVATION_BEFORE_PREPARE_CAS,
                )
                cursor = (
                    live_start_session.prepare_nonterminal_apply_recovery_under_lock(
                        session_lease=session_lease,
                        expected_nonterminal_session=cursor,
                        runtime_observation_receipt=(
                            observed.runtime_observation_receipt
                        ),
                    )
                )
            cursor = _drive_recovery_rows(
                plan=plan,
                lease_pair=lease_pair,
                session_lease=session_lease,
                cursor=cursor,
                runtime_admission=runtime_admission,
                fault_hook=fault_hook,
            )
            cursor, result, acknowledgement = _finish_stable_recovery(
                plan=plan,
                lease_pair=lease_pair,
                session_lease=session_lease,
                cursor=cursor,
                runtime_admission=runtime_admission,
                raw_apply_status="recovered",
                fault_hook=fault_hook,
                fire_installer_faults=False,
            )
            revalidate_package_input_lease(package_lease)
            held = HeldApplyAndMatchPublished(
                updated_session=cursor,
                invocation=invocation,
                result=result,
                acknowledgement_evidence=acknowledgement,
                runtime_admission=runtime_admission,
                session_lease=session_lease,
                profile_lease=profile_lease,
                lease_pair=lease_pair,
                fault_hook=fault_hook,
            )
            recovered = HeldRecoveredApplyAndMatch(held=held)
            with _validated_held_yield(
                held=held,
                exposed=recovered,
            ):
                yield recovered


__all__ = (
    "ApplyAndMatchPublishedResult",
    "AttemptAcknowledgementEvidence",
    "HeldApplyAndMatchPublished",
    "HeldRecoveredApplyAndMatch",
    "PhysicalApplyDisposition",
    "RecoverApplyNotStarted",
    "RecoverApplyResult",
    "apply_and_match_published",
    "recover_apply_attempt",
    "recover_apply_attempt_under_lock",
)
