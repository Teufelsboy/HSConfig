"""Transactional installation of one verified published runtime package."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import unicodedata
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Lock, get_ident
from types import MappingProxyType
from typing import Any, Callable, Iterator, Literal, Mapping

from hsconfig import apply_invocation as apply_invocation_module
from hsconfig.apply_invocation import APPLY_INVOCATION_MAX_BYTES
from hsconfig.atomic_io import (
    ExclusiveFileLock,
    FaultHook,
    atomic_commit_bound_staging_no_replace,
    atomic_commit_bound_staging_replace,
    atomic_materialize_staging_bytes,
    atomic_write_bytes,
    no_fault,
)
from hsconfig.current_output import (
    PackageInputLease,
    _require_active_package_input_lease,
    lease_package_input,
    snapshot_and_verify_revision,
)
from hsconfig.deck_config_ini import (
    DeckConfigSnapshot,
    MAX_DECK_CONFIG_BYTES,
    read_deck_config,
    render_deck_config,
    replace_deck_config_if_unchanged,
)
from hsconfig.output_publisher import (
    PublishedOutput,
    _bootstrap_neutral_output_locks,
)
from hsconfig.output_operation_admission import (
    OutputOperationAdmissionEvidence,
    OutputOperationAdmissionLease,
    build_output_operation_admission_bytes,
    lease_output_operation_admission,
    observe_output_operation_admission_under_lease,
    require_output_operation_allows_runtime_mutation,
)
from hsconfig.live_start_session import (
    ApplyRecoveryStepReceipt,
    LiveStartSession,
    LiveStartSessionLease,
    RuntimeAttemptRecoveryAuthorization,
    RuntimeAdmissionAuthorization,
    RuntimeAdmissionPhysicalPostcondition,
    RuntimeAdmissionStepReceipt,
    RuntimeLayoutBootstrapAuthorization,
    RuntimeLayoutBootstrapEvidence,
    RuntimeLayoutBootstrapPhysicalPostcondition,
    RuntimeLayoutBootstrapStepReceipt,
    RuntimeApplyRecoveryPhysicalPostcondition,
    RUNTIME_APPLY_RECOVERY_ACTIONS,
    RUNTIME_TERMINAL_OBSERVATION_ACTIONS,
    RuntimeApplyRecoveryEvidence,
    RuntimeObservationReceipt,
    RuntimeObservationAuthorization,
    RuntimeObservationPostcondition,
    TerminalRetirementAuthorization,
    TerminalResolutionCleanupInventory,
    TerminalResolutionEvidence,
    TerminalResolutionPhysicalPostcondition,
    TerminalResolutionStepReceipt,
    SuccessAckStepEvidence,
    LIVE_START_TERMINAL_CLEANUP_INVENTORY_MAX_BYTES,
    LIVE_START_TERMINAL_CLEANUP_INVENTORY_MAX_ENTRIES,
    _execute_apply_recovery_physical_step,
    _execute_runtime_admission_physical_step,
    _execute_runtime_layout_bootstrap_physical_step,
    _execute_runtime_observation,
    _execute_terminal_resolution_physical_step,
    _require_terminal_physical_authorization_context,
    _APPLY_RECOVERY_FIELDS,
    _TERMINAL_RESOLUTION_FIELDS,
    _owner_action_for_cursor,
    _is_unbound_file_action_retirement_alternate,
    _build_external_file_action,
    _require_opaque_carrier,
    _terminal_owner_context_for_authorization,
    _seal_terminal_resolution,
    RUNTIME_LAYOUT_DIRECTORY_ROLES,
    load_live_start_session_under_lock,
    seal_embedded_document,
)
from hsconfig.operator_profile import (
    OperatorProfileLease,
    revalidate_operator_profile_lease,
)
from hsconfig.package_io import (
    BoundedFilesystemPackageView,
    FilesystemPathGuard,
    PathIdentity,
    MAX_FILESYSTEM_DEPTH,
    MAX_FILESYSTEM_ENTRIES_PER_DIRECTORY,
    capture_plain_ancestor_guard,
    path_identity,
    path_identity_from_status,
    path_lexists,
    plain_file_status,
    read_file_no_follow,
    require_no_alternate_data_streams,
    require_plain_directory,
    require_same_identity_resolution,
    secure_create_directory,
    secure_open_file_descriptor,
    secure_replace,
    secure_rmdir,
    secure_rmdir_verified,
    secure_unlink,
    secure_unlink_verified,
    snapshot_bounded_filesystem_package,
    status_is_reparse,
)
from hsconfig.run_manifest import (
    MAX_RUN_FILES,
    ManifestEntry,
    TreeManifest,
    verify_tree_manifest,
)
from hsconfig.runtime_state import (
    RuntimeDeckState,
    RuntimeState,
    read_runtime_state,
    serialize_runtime_state,
)
from hsconfig.runtime_live_admission import (
    RUNTIME_LIVE_ATTEMPT_ADMISSION_MAX_BYTES,
    RuntimeLiveAttemptAdmissionEvidence,
    load_runtime_live_attempt_admission,
    require_live_admission_allows_runtime_mutation,
)
from hsconfig.runtime_transaction_journal import (
    MAX_RUNTIME_TRANSACTION_BYTES,
    MAX_RUNTIME_TRANSACTION_FILES,
    RuntimeCleanupEntry,
    RuntimeTransactionJournal,
    RuntimeTransactionPhase,
    load_runtime_transaction_journals,
    parse_runtime_transaction_journal_bytes,
    read_runtime_transaction_journal,
    runtime_transaction_journal_path,
    runtime_transaction_journal_bytes,
    write_runtime_transaction_journal,
    _is_monotonic_successor,
)


_SAFE_COMPONENT_LIMIT = 255
_STATE_SLUG_LIMIT = 48
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_VERSIONED_CONFIG = re.compile(r"^.+--sha256-[0-9a-f]{64}$")
_STATE_IDENTITY_DOMAIN = b"hsconfig-runtime-deck-state-v1\0"
_RECEIPT_SCHEMA_VERSION = 1
_RUNTIME_APPLY_TOKEN_AUTHORITY = object()
_CONTROLLER_PAIR_TOKEN_AUTHORITY = object()
RUNTIME_ATTEMPT_RETENTION_SCHEMA_VERSION = 2
RUNTIME_ATTEMPT_RETENTION_MAX_BYTES = 64 * 1024
RUNTIME_ATTEMPT_RETENTION_KIND = "live_start_runtime_attempt_retention"
RUNTIME_ATTEMPT_RETENTION_FIELDS = frozenset(
    {
        "schema_version",
        "record_kind",
        "state",
        "apply_attempt_id",
        "retention_owner_run_id",
        "journal_path",
        "journal_identity",
        "journal_sha256",
        "package_root_sha256",
        "target_path",
        "target_identity",
        "owns_target",
        "target_owner_journal_path",
        "target_owner_journal_identity",
        "target_owner_journal_sha256",
        "planned_journal_path",
        "planned_journal_size",
        "planned_journal_sha256",
        "candidate_path",
        "candidate_parent_identity",
        "candidate_identity",
        "content_sha256",
    }
)
_ATTEMPT_ID = re.compile(r"^[0-9a-f]{32}$")
_PREFIXED_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_ATTEMPT_RETENTION_ENTRY = re.compile(r"^(?P<attempt>[0-9a-f]{32})\.json$")
_ATTEMPT_RETENTION_RESERVED_TEMP = re.compile(
    r"^\.(?P<attempt>[0-9a-f]{32})\.json\.staged"
    r"\.live-start-atomic\.tmp$"
)
_ATTEMPT_RETENTION_STATES = frozenset(
    {
        "ACTIVE",
        "CANDIDATE_PLANNED",
        "CANDIDATE_BOUND",
        "PRIOR_OWNER_PLANNED",
        "PRIOR_OWNER_BOUND",
        "FINALIZED",
    }
)
RUNTIME_OWNER_RETIREMENT_SCHEMA_VERSION = 1
RUNTIME_OWNER_RETIREMENT_MAX_BYTES = 4 * MAX_RUNTIME_TRANSACTION_BYTES
RUNTIME_OWNER_RETIREMENT_MAX_ENTRIES = MAX_RUN_FILES
RUNTIME_OWNER_RETIREMENT_KIND = "runtime_owner_retirement"
RUNTIME_OWNER_RETIREMENT_FIELDS = frozenset(
    {
        "schema_version",
        "record_kind",
        "state",
        "retired_owner_transaction_id",
        "initial_owner_journal_path",
        "initial_owner_journal_identity",
        "initial_owner_journal_sha256",
        "retired_target_path",
        "retired_target_parent_identity",
        "retired_target_identity",
        "retired_target_tree_sha256",
        "successor_transaction_id",
        "successor_package_root_sha256",
        "successor_owner_journal_path",
        "successor_owner_journal_identity",
        "successor_owner_journal_sha256",
        "cleanup_manifest_sha256",
        "cleanup_entry_count",
        "cleanup_entries",
        "completed_cleanup_cursor",
        "completed_owner_journal_identity",
        "completed_owner_journal_sha256",
        "content_sha256",
    }
)
RUNTIME_OWNER_RETIREMENT_CLEANUP_ENTRY_FIELDS = frozenset(
    {
        "relative_path",
        "entry_kind",
        "identity",
        "expected_parent_identity",
        "size",
        "sha256",
    }
)


def _validate_runtime_admission_handoff_bindings(
    *,
    invocation: Mapping[str, Any],
    runtime_admission: Mapping[str, Any],
    output_operation_admission: Mapping[str, Any],
    output_child_binding: Mapping[str, Any],
    publication_binding: Mapping[str, Any],
    observe_filesystem: bool = False,
) -> None:
    """Require one exact publication/output handoff across all authorities."""

    authorities = (
        invocation,
        runtime_admission,
        output_operation_admission,
        output_child_binding,
        publication_binding,
    )
    if any(not isinstance(authority, Mapping) for authority in authorities):
        raise TypeError("runtime_admission_handoff_authority_invalid")
    required_invocation_fields = (
        "output_operation_admission_path",
        "output_operation_admission_identity",
        "output_operation_admission_sha256",
        "output_child_binding_sha256",
        "output_child_path",
        "output_child_identity",
        "publication_revision",
        "publication_content_root_sha256",
    )
    if any(
        field not in invocation or invocation.get(field) is None
        for field in required_invocation_fields
    ):
        raise ValueError("runtime_admission_handoff_binding_missing")
    if any(
        field not in runtime_admission or runtime_admission.get(field) is None
        for field in required_invocation_fields
    ):
        raise ValueError("runtime_admission_handoff_binding_missing")
    for authority, required_fields in (
        (
            output_operation_admission,
            ("admission_path", "admission_identity", "admission_sha256"),
        ),
        (
            output_child_binding,
            ("output_child_path", "output_child_identity", "content_sha256"),
        ),
        (
            publication_binding,
            ("revision", "content_root_sha256"),
        ),
    ):
        if any(
            field not in authority or authority.get(field) is None
            for field in required_fields
        ):
            raise ValueError("runtime_admission_handoff_binding_missing")

    operation_fields = {
        "output_operation_admission_path": "admission_path",
        "output_operation_admission_identity": "admission_identity",
        "output_operation_admission_sha256": "admission_sha256",
    }
    for handoff_name, authority_name in operation_fields.items():
        expected = invocation.get(handoff_name)
        if (
            runtime_admission.get(handoff_name) != expected
            or output_operation_admission.get(authority_name) != expected
        ):
            raise ValueError("runtime_admission_output_operation_mismatch")

    child_fields = {
        "output_child_path": "output_child_path",
        "output_child_identity": "output_child_identity",
        "output_child_binding_sha256": "content_sha256",
    }
    for handoff_name, authority_name in child_fields.items():
        expected = invocation.get(handoff_name)
        if (
            runtime_admission.get(handoff_name) != expected
            or output_child_binding.get(authority_name) != expected
        ):
            raise ValueError("runtime_admission_output_child_mismatch")

    publication_fields = {
        "publication_revision": "revision",
        "publication_content_root_sha256": "content_root_sha256",
    }
    for handoff_name, authority_name in publication_fields.items():
        expected = invocation.get(handoff_name)
        if (
            runtime_admission.get(handoff_name) != expected
            or publication_binding.get(authority_name) != expected
        ):
            raise ValueError("runtime_admission_publication_mismatch")

    if observe_filesystem:
        operation_path = invocation.get("output_operation_admission_path")
        child_path = invocation.get("output_child_path")
        if not isinstance(operation_path, Path) or not isinstance(child_path, Path):
            raise ValueError("runtime_admission_handoff_path_invalid")
        try:
            observed_operation = path_identity(operation_path)
            observed_child = path_identity(child_path)
        except (FileNotFoundError, OSError) as error:
            raise ValueError("runtime_admission_handoff_missing") from error
        if observed_operation != invocation.get("output_operation_admission_identity"):
            raise ValueError("runtime_admission_output_operation_mismatch")
        if observed_child != invocation.get("output_child_identity"):
            raise ValueError("runtime_admission_output_child_mismatch")


@dataclass(frozen=True, slots=True)
class RuntimeInstallPlan:
    deck_name: str
    logical_config_dir: str
    versioned_config_dir: str
    package_root_sha256: str
    source_revision_root: Path
    source_package_root: Path
    runtime_root: Path
    ini_snapshot: DeckConfigSnapshot

    def __post_init__(self) -> None:
        expected = f"{self.logical_config_dir}--sha256-{self.package_root_sha256}"
        if (
            not _valid_deck_name(self.deck_name)
            or not _valid_component(self.logical_config_dir)
            or not _SHA256.fullmatch(self.package_root_sha256)
            or self.versioned_config_dir != expected
            or not _valid_component(self.versioned_config_dir)
            or not isinstance(self.source_revision_root, Path)
            or not isinstance(self.source_package_root, Path)
            or not isinstance(self.runtime_root, Path)
            or not isinstance(self.ini_snapshot, DeckConfigSnapshot)
        ):
            code = (
                "runtime_config_component_too_long"
                if isinstance(self.versioned_config_dir, str)
                and len(self.versioned_config_dir) > _SAFE_COMPONENT_LIMIT
                else "runtime_install_plan_invalid"
            )
            raise ValueError(code)


@dataclass(frozen=True, slots=True)
class RuntimeInstallResult:
    status: Literal[
        "applied",
        "already_current",
        "recovered",
        "committed_receipt_pending",
    ]
    config_dir: str
    package_root_sha256: str
    previous_config_dir: str | None
    receipt_path: Path | None


RuntimeRecoveryObservationFamily = Literal[
    "nonterminal_apply",
    "terminal_resolution",
]


@dataclass(frozen=True, slots=True)
class RuntimeAttemptRetentionRecord:
    schema_version: int
    record_kind: str
    state: str
    apply_attempt_id: str
    retention_owner_run_id: str
    journal_path: Path | None
    journal_identity: PathIdentity | None
    journal_sha256: str | None
    package_root_sha256: str | None
    target_path: Path | None
    target_identity: PathIdentity | None
    owns_target: bool | None
    target_owner_journal_path: Path | None
    target_owner_journal_identity: PathIdentity | None
    target_owner_journal_sha256: str | None
    planned_journal_path: Path | None
    planned_journal_size: int | None
    planned_journal_sha256: str | None
    candidate_path: Path | None
    candidate_parent_identity: PathIdentity | None
    candidate_identity: PathIdentity | None
    content_sha256: str


@dataclass(frozen=True, slots=True)
class RuntimeAttemptRecovery:
    transaction_id: str
    status: Literal[
        "not_committed",
        "committed",
        "recovered",
        "committed_receipt_pending",
        "unknown",
    ]
    package_root_sha256: str | None
    receipt_path: Path | None
    retained_attempt_record_path: Path | None
    retained_attempt_record_identity: PathIdentity | None
    retained_attempt_record_sha256: str | None
    retained_journal_path: Path | None
    retained_journal_identity: PathIdentity | None
    retained_journal_sha256: str | None
    target_owner_journal_path: Path | None
    target_owner_journal_identity: PathIdentity | None
    target_owner_journal_sha256: str | None
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence | None
    observation_family: RuntimeRecoveryObservationFamily | None
    initial_apply_recovery_evidence: RuntimeApplyRecoveryEvidence | None
    initial_terminal_resolution_evidence: TerminalResolutionEvidence | None
    runtime_observation_receipt: RuntimeObservationReceipt | None
    apply_recovery_step_receipt: ApplyRecoveryStepReceipt | None
    terminal_resolution_step_receipt: TerminalResolutionStepReceipt | None
    terminal_cleanup_inventory: TerminalResolutionCleanupInventory | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.transaction_id, str)
            or _ATTEMPT_ID.fullmatch(self.transaction_id) is None
            or self.status
            not in {
                "not_committed",
                "committed",
                "recovered",
                "committed_receipt_pending",
                "unknown",
            }
            or (
                self.package_root_sha256 is not None
                and (
                    not isinstance(self.package_root_sha256, str)
                    or _PREFIXED_SHA256.fullmatch(
                        self.package_root_sha256
                    )
                    is None
                )
            )
        ):
            raise ValueError("runtime_attempt_recovery_result_invalid")
        for prefix in (
            "retained_attempt_record",
            "retained_journal",
            "target_owner_journal",
        ):
            triplet = (
                getattr(self, f"{prefix}_path"),
                getattr(self, f"{prefix}_identity"),
                getattr(self, f"{prefix}_sha256"),
            )
            if not all(item is None for item in triplet) and (
                any(item is None for item in triplet)
                or not isinstance(triplet[0], Path)
                or not triplet[0].is_absolute()
                or not _valid_path_identity(triplet[1])
                or not isinstance(triplet[2], str)
                or _PREFIXED_SHA256.fullmatch(triplet[2]) is None
            ):
                raise ValueError(
                    "runtime_attempt_recovery_result_evidence_invalid"
                )
        paired_receipts = (
            self.runtime_observation_receipt,
            self.apply_recovery_step_receipt,
            self.terminal_resolution_step_receipt,
        )
        if self.terminal_cleanup_inventory is not None and (
            type(self.terminal_cleanup_inventory)
            is not TerminalResolutionCleanupInventory
            or type(self.runtime_admission)
            is not RuntimeLiveAttemptAdmissionEvidence
            or self.observation_family != "terminal_resolution"
            or self.runtime_observation_receipt is None
            or self.status != "not_committed"
            or self.terminal_cleanup_inventory.value.get("run_id")
            != self.runtime_admission.run_id
            or self.terminal_cleanup_inventory.value.get("apply_attempt_id")
            != self.runtime_admission.apply_attempt_id
            or self.transaction_id != self.runtime_admission.apply_attempt_id
            or self.terminal_cleanup_inventory.value.get("runtime_root_path")
            != str(self.runtime_admission.runtime_root)
            or tuple(
                self.terminal_cleanup_inventory.value.get(
                    "runtime_root_identity", ()
                )
            )
            != self.runtime_admission.runtime_root_identity
        ):
            raise ValueError(
                "runtime_attempt_recovery_family_nullability_invalid"
            )
        if self.runtime_admission is None:
            if (
                self.observation_family is not None
                or self.initial_apply_recovery_evidence is not None
                or self.initial_terminal_resolution_evidence is not None
                or any(item is not None for item in paired_receipts)
            ):
                raise ValueError(
                    "runtime_attempt_recovery_family_nullability_invalid"
                )
            return
        if type(
            self.runtime_admission
        ) is not RuntimeLiveAttemptAdmissionEvidence or any(
            item is not None
            for item in (
                self.initial_apply_recovery_evidence,
                self.initial_terminal_resolution_evidence,
            )
        ):
            raise ValueError(
                "runtime_attempt_recovery_family_nullability_invalid"
            )
        present = tuple(item is not None for item in paired_receipts)
        if sum(present) != 1:
            raise ValueError(
                "runtime_attempt_recovery_family_nullability_invalid"
            )
        if present[0]:
            if (
                self.observation_family
                not in {"nonterminal_apply", "terminal_resolution"}
                or type(self.runtime_observation_receipt)
                is not RuntimeObservationReceipt
            ):
                raise ValueError(
                    "runtime_attempt_recovery_family_nullability_invalid"
                )
        elif self.observation_family is not None:
            raise ValueError(
                "runtime_attempt_recovery_family_nullability_invalid"
            )
        if present[1] and type(
            self.apply_recovery_step_receipt
        ) is not ApplyRecoveryStepReceipt:
            raise ValueError(
                "runtime_attempt_recovery_family_nullability_invalid"
            )
        if present[2] and type(
            self.terminal_resolution_step_receipt
        ) is not TerminalResolutionStepReceipt:
            raise ValueError(
                "runtime_attempt_recovery_family_nullability_invalid"
            )


@dataclass(frozen=True, slots=True)
class RuntimeFailureSelection:
    disposition: Literal[
        "resume_current_action",
        "select_terminal_observation",
    ]
    expected_recovery_sha256: str
    expected_action_index: int
    expected_action: str
    selected_observation: str | None

    def __post_init__(self) -> None:
        if (
            self.disposition
            not in {"resume_current_action", "select_terminal_observation"}
            or not isinstance(self.expected_recovery_sha256, str)
            or _PREFIXED_SHA256.fullmatch(self.expected_recovery_sha256) is None
            or type(self.expected_action_index) is not int
            or self.expected_action_index < 0
            or self.expected_action not in RUNTIME_APPLY_RECOVERY_ACTIONS
            or (
                self.disposition == "resume_current_action"
                and self.selected_observation is not None
            )
            or (
                self.disposition == "select_terminal_observation"
                and self.selected_observation
                not in {"observe_not_committed", "observe_pending", "observe_unknown"}
            )
        ):
            raise ValueError("runtime_failure_selection_invalid")


@dataclass(frozen=True, slots=True)
class _ObservedRuntimeAttemptRetention:
    record: RuntimeAttemptRetentionRecord
    path: Path
    identity: PathIdentity
    raw_sha256: str


@dataclass(frozen=True, slots=True)
class _RuntimeAttemptPreservationIndex:
    transaction_ids: frozenset[str]
    candidate_identities: Mapping[str, PathIdentity]
    target_identities: Mapping[str, PathIdentity]


_RUNTIME_APPLY_RECOVERY_ACTION_MATRIX = MappingProxyType(
    {
        **{
            action: "runtime_action"
            for action in RUNTIME_APPLY_RECOVERY_ACTIONS
        },
        "materialize_file_action_staging": "external_materialize",
        "retire_unbound_file_action_staging": "external_retire",
        "advance_controller_transaction_journal_write": "external_commit",
        "promote_legacy_uuid_transaction_temp": "legacy_promote",
        "retire_legacy_uuid_transaction_temp": "legacy_retire",
    }
)
_LEGACY_UUID_TEMP_ACTION_BY_CLASSIFICATION = MappingProxyType(
    {
        "legacy_complete_valid": "promote_legacy_uuid_transaction_temp",
        "legacy_monotone_successor": (
            "promote_legacy_uuid_transaction_temp"
        ),
        "legacy_redundant_equal": "retire_legacy_uuid_transaction_temp",
        "legacy_partial_invalid": "retire_legacy_uuid_transaction_temp",
    }
)
_LEGACY_UUID_TRANSACTION_TEMP = re.compile(
    r"^\.(?P<transaction>[0-9a-f]{32})\.json\."
    r"(?P<nonce>[0-9a-f]{32})\.tmp$"
)


@dataclass(frozen=True, slots=True)
class _ExactRuntimeTransactionObservation:
    journal_path: Path
    journal: RuntimeTransactionJournal | None
    journal_identity: PathIdentity | None
    journal_size: int | None
    journal_sha256: str | None
    controller_staging_path: Path | None
    controller_staging_identity: PathIdentity | None
    controller_staging_size: int | None
    controller_staging_sha256: str | None
    legacy_temp_path: Path | None
    legacy_temp_parent_identity: PathIdentity | None
    legacy_temp_identity: PathIdentity | None
    legacy_temp_size: int | None
    legacy_temp_sha256: str | None
    legacy_temp_classification: str | None
    legacy_temp_origin: str | None


@dataclass(frozen=True, slots=True)
class _BoundedRuntimeAuthorityContradiction:
    surface: Literal[
        "candidate_root", "prior_owner_target", "prior_owner_journal"
    ]
    kind: Literal["missing", "identity"]


@dataclass(frozen=True, slots=True)
class _ExactPairedRuntimeAttemptObservation:
    retention: _ObservedRuntimeAttemptRetention | None
    transaction: _ExactRuntimeTransactionObservation
    status: Literal[
        "not_committed",
        "committed",
        "committed_receipt_pending",
        "unknown",
    ]
    receipt_path: Path | None
    validated_unbound_candidate_identity: PathIdentity | None = None
    authority_contradiction: _BoundedRuntimeAuthorityContradiction | None = None


class RuntimeInstallRecoveryRequiredError(RuntimeError):
    """The selected transaction already has durable recovery evidence."""


@dataclass(frozen=True, slots=True)
class RuntimeNoCommitCleanupStep:
    """One identity-bound no-commit cleanup row and its separate CAS receipt."""

    next_cursor: int
    current_entry_was_already_absent: bool
    cleanup_roots_absent: bool
    step_receipt: TerminalResolutionStepReceipt

    def __post_init__(self) -> None:
        if (
            type(self.next_cursor) is not int
            or self.next_cursor < 1
            or type(self.current_entry_was_already_absent) is not bool
            or type(self.cleanup_roots_absent) is not bool
            or type(self.step_receipt) is not TerminalResolutionStepReceipt
        ):
            raise ValueError("runtime_no_commit_cleanup_step_invalid")


@dataclass(frozen=True, slots=True)
class RuntimeNoCommitMetadataStep:
    """One retained metadata unlink and its separate terminal CAS receipt."""

    action: Literal["journal", "fence"]
    object_was_already_absent: bool
    step_receipt: TerminalResolutionStepReceipt

    def __post_init__(self) -> None:
        if (
            self.action not in {"journal", "fence"}
            or type(self.object_was_already_absent) is not bool
            or type(self.step_receipt) is not TerminalResolutionStepReceipt
        ):
            raise ValueError("runtime_no_commit_metadata_step_invalid")


@dataclass(frozen=True, slots=True)
class RuntimeAttemptEvidenceRetirementStep:
    """One successful-attempt evidence row and its separate terminal CAS receipt."""

    action: Literal["journal", "fence"]
    object_was_already_absent: bool
    step_receipt: TerminalResolutionStepReceipt

    def __post_init__(self) -> None:
        if (
            self.action not in {"journal", "fence"}
            or type(self.object_was_already_absent) is not bool
            or type(self.step_receipt) is not TerminalResolutionStepReceipt
        ):
            raise ValueError("runtime_attempt_evidence_retirement_step_invalid")


@dataclass(frozen=True, slots=True)
class _RuntimeNoCommitMetadataSurface:
    attempt_path: Path
    attempt_identity: PathIdentity | None
    attempt_raw: bytes | None
    record: RuntimeAttemptRetentionRecord | None
    journal_path: Path
    journal_identity: PathIdentity | None
    journal_raw: bytes | None
    journal: RuntimeTransactionJournal | None
    owner_path: Path | None
    owner_identity: PathIdentity | None
    owner_raw: bytes | None
    target_path: Path | None
    target_identity: PathIdentity | None
    inventory_path: Path | None
    inventory_identity: PathIdentity | None
    inventory_raw: bytes | None


def build_runtime_attempt_retention_bytes(
    *,
    runtime_root: Path,
    state: str,
    apply_attempt_id: str,
    retention_owner_run_id: str,
    journal_path: Path | None,
    journal_identity: PathIdentity | None,
    journal_sha256: str | None,
    package_root_sha256: str | None,
    target_path: Path | None,
    target_identity: PathIdentity | None,
    owns_target: bool | None,
    target_owner_journal_path: Path | None,
    target_owner_journal_identity: PathIdentity | None,
    target_owner_journal_sha256: str | None,
    planned_journal_path: Path | None,
    planned_journal_size: int | None,
    planned_journal_sha256: str | None,
    candidate_path: Path | None,
    candidate_parent_identity: PathIdentity | None,
    candidate_identity: PathIdentity | None,
) -> bytes:
    """Build one closed canonical controller-attempt retention record."""

    root = Path(runtime_root)
    record = RuntimeAttemptRetentionRecord(
        schema_version=RUNTIME_ATTEMPT_RETENTION_SCHEMA_VERSION,
        record_kind=RUNTIME_ATTEMPT_RETENTION_KIND,
        state=state,
        apply_attempt_id=apply_attempt_id,
        retention_owner_run_id=retention_owner_run_id,
        journal_path=journal_path,
        journal_identity=journal_identity,
        journal_sha256=journal_sha256,
        package_root_sha256=package_root_sha256,
        target_path=target_path,
        target_identity=target_identity,
        owns_target=owns_target,
        target_owner_journal_path=target_owner_journal_path,
        target_owner_journal_identity=target_owner_journal_identity,
        target_owner_journal_sha256=target_owner_journal_sha256,
        planned_journal_path=planned_journal_path,
        planned_journal_size=planned_journal_size,
        planned_journal_sha256=planned_journal_sha256,
        candidate_path=candidate_path,
        candidate_parent_identity=candidate_parent_identity,
        candidate_identity=candidate_identity,
        content_sha256="",
    )
    _validate_runtime_attempt_retention_record(
        record,
        runtime_root=root,
        validate_content_digest=False,
    )
    unsigned = _runtime_attempt_retention_payload(record, include_digest=False)
    sealed = replace(record, content_sha256=_runtime_attempt_self_digest(unsigned))
    _validate_runtime_attempt_retention_record(
        sealed,
        runtime_root=root,
        validate_content_digest=True,
    )
    raw = _canonical_runtime_attempt_json(
        _runtime_attempt_retention_payload(sealed, include_digest=True)
    )
    if not raw or len(raw) > RUNTIME_ATTEMPT_RETENTION_MAX_BYTES:
        raise ValueError("runtime_attempt_retention_too_large")
    return raw


def _runtime_attempt_retention_payload(
    record: RuntimeAttemptRetentionRecord,
    *,
    include_digest: bool,
) -> dict[str, object]:
    def identity(value: PathIdentity | None) -> list[int] | None:
        return list(value) if value is not None else None

    payload: dict[str, object] = {
        "schema_version": record.schema_version,
        "record_kind": record.record_kind,
        "state": record.state,
        "apply_attempt_id": record.apply_attempt_id,
        "retention_owner_run_id": record.retention_owner_run_id,
        "journal_path": (
            str(record.journal_path) if record.journal_path is not None else None
        ),
        "journal_identity": identity(record.journal_identity),
        "journal_sha256": record.journal_sha256,
        "package_root_sha256": record.package_root_sha256,
        "target_path": (
            str(record.target_path) if record.target_path is not None else None
        ),
        "target_identity": identity(record.target_identity),
        "owns_target": record.owns_target,
        "target_owner_journal_path": (
            str(record.target_owner_journal_path)
            if record.target_owner_journal_path is not None
            else None
        ),
        "target_owner_journal_identity": identity(
            record.target_owner_journal_identity
        ),
        "target_owner_journal_sha256": record.target_owner_journal_sha256,
        "planned_journal_path": (
            str(record.planned_journal_path)
            if record.planned_journal_path is not None
            else None
        ),
        "planned_journal_size": record.planned_journal_size,
        "planned_journal_sha256": record.planned_journal_sha256,
        "candidate_path": (
            str(record.candidate_path) if record.candidate_path is not None else None
        ),
        "candidate_parent_identity": identity(record.candidate_parent_identity),
        "candidate_identity": identity(record.candidate_identity),
    }
    if include_digest:
        payload["content_sha256"] = record.content_sha256
    return payload


def _canonical_runtime_attempt_json(payload: Mapping[str, object]) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _canonical_owner_retirement_json(payload: Mapping[str, object]) -> bytes:
    return (
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _build_owner_retirement_tombstone_bytes(
    *,
    state: Literal["PREPARED", "COMPLETED"],
    retired_owner_transaction_id: str,
    initial_owner_journal_path: Path,
    initial_owner_journal_identity: PathIdentity,
    initial_owner_journal_sha256: str,
    retired_target_path: Path,
    retired_target_parent_identity: PathIdentity,
    retired_target_identity: PathIdentity,
    retired_target_tree_sha256: str,
    successor_transaction_id: str,
    successor_package_root_sha256: str,
    successor_owner_journal_path: Path,
    successor_owner_journal_identity: PathIdentity,
    successor_owner_journal_sha256: str,
    cleanup_entries: tuple[Mapping[str, object], ...],
    completed_cleanup_cursor: int | None,
    completed_owner_journal_identity: PathIdentity | None,
    completed_owner_journal_sha256: str | None,
) -> bytes:
    """Seal the immutable physical inventory for one old-owner retirement."""

    if (
        state not in {"PREPARED", "COMPLETED"}
        or _ATTEMPT_ID.fullmatch(retired_owner_transaction_id) is None
        or _ATTEMPT_ID.fullmatch(successor_transaction_id) is None
        or any(
            _PREFIXED_SHA256.fullmatch(value) is None
            for value in (
                initial_owner_journal_sha256,
                retired_target_tree_sha256,
                successor_package_root_sha256,
                successor_owner_journal_sha256,
            )
        )
        or any(
            not _valid_path_identity(value)
            for value in (
                initial_owner_journal_identity,
                retired_target_parent_identity,
                retired_target_identity,
                successor_owner_journal_identity,
            )
        )
        or len(cleanup_entries) > RUNTIME_OWNER_RETIREMENT_MAX_ENTRIES
    ):
        raise ValueError("runtime_owner_retirement_tombstone_invalid")
    runtime_root = retired_target_path.parent.parent
    if (
        not all(
            path.is_absolute() and path.resolve(strict=False) == path
            for path in (
                initial_owner_journal_path,
                retired_target_path,
                successor_owner_journal_path,
            )
        )
        or initial_owner_journal_path
        != runtime_transaction_journal_path(
            runtime_root, retired_owner_transaction_id
        )
        or successor_owner_journal_path
        != runtime_transaction_journal_path(runtime_root, successor_transaction_id)
        or retired_target_path.parent != runtime_root / "CustomConfig"
    ):
        raise ValueError("runtime_owner_retirement_tombstone_path_invalid")
    normalized_entries: list[dict[str, object]] = []
    seen_paths: set[str] = set()
    previous_key: tuple[int, int, str] | None = None
    for value in cleanup_entries:
        entry = dict(value)
        if set(entry) != RUNTIME_OWNER_RETIREMENT_CLEANUP_ENTRY_FIELDS:
            raise ValueError("runtime_owner_retirement_tombstone_entry_invalid")
        relative = entry.get("relative_path")
        kind = entry.get("entry_kind")
        if (
            not isinstance(relative, str)
            or not relative
            or Path(relative).is_absolute()
            or "\\" in relative
            or any(part in {"", ".", ".."} for part in relative.split("/"))
            or relative in seen_paths
            or kind not in {"file", "directory"}
            or not _valid_path_identity(entry.get("identity"))
            or not _valid_path_identity(entry.get("expected_parent_identity"))
        ):
            raise ValueError("runtime_owner_retirement_tombstone_entry_invalid")
        if kind == "file":
            if (
                type(entry.get("size")) is not int
                or not 0 <= entry["size"] <= 64 * 1024 * 1024
                or not isinstance(entry.get("sha256"), str)
                or _PREFIXED_SHA256.fullmatch(str(entry["sha256"])) is None
            ):
                raise ValueError("runtime_owner_retirement_tombstone_entry_invalid")
        elif entry.get("size") is not None or entry.get("sha256") is not None:
            raise ValueError("runtime_owner_retirement_tombstone_entry_invalid")
        key = (0 if kind == "file" else 1, relative.count("/"), relative)
        if previous_key is not None and (
            key[0] < previous_key[0]
            or (key[0] == previous_key[0] and key[1:] > previous_key[1:])
        ):
            raise ValueError("runtime_owner_retirement_tombstone_entry_order_invalid")
        previous_key = key
        seen_paths.add(relative)
        normalized_entries.append(entry)
    entry_bytes = _canonical_owner_retirement_json(normalized_entries)
    manifest_sha256 = "sha256:" + hashlib.sha256(entry_bytes).hexdigest()
    if state == "PREPARED":
        if any(
            value is not None
            for value in (
                completed_cleanup_cursor,
                completed_owner_journal_identity,
                completed_owner_journal_sha256,
            )
        ):
            raise ValueError("runtime_owner_retirement_tombstone_completed_invalid")
    elif (
        completed_cleanup_cursor != len(normalized_entries)
        or not _valid_path_identity(completed_owner_journal_identity)
        or not isinstance(completed_owner_journal_sha256, str)
        or _PREFIXED_SHA256.fullmatch(completed_owner_journal_sha256) is None
    ):
        raise ValueError("runtime_owner_retirement_tombstone_completed_invalid")
    payload: dict[str, object] = {
        "schema_version": RUNTIME_OWNER_RETIREMENT_SCHEMA_VERSION,
        "record_kind": RUNTIME_OWNER_RETIREMENT_KIND,
        "state": state,
        "retired_owner_transaction_id": retired_owner_transaction_id,
        "initial_owner_journal_path": str(initial_owner_journal_path),
        "initial_owner_journal_identity": list(initial_owner_journal_identity),
        "initial_owner_journal_sha256": initial_owner_journal_sha256,
        "retired_target_path": str(retired_target_path),
        "retired_target_parent_identity": list(retired_target_parent_identity),
        "retired_target_identity": list(retired_target_identity),
        "retired_target_tree_sha256": retired_target_tree_sha256,
        "successor_transaction_id": successor_transaction_id,
        "successor_package_root_sha256": successor_package_root_sha256,
        "successor_owner_journal_path": str(successor_owner_journal_path),
        "successor_owner_journal_identity": list(successor_owner_journal_identity),
        "successor_owner_journal_sha256": successor_owner_journal_sha256,
        "cleanup_manifest_sha256": manifest_sha256,
        "cleanup_entry_count": len(normalized_entries),
        "cleanup_entries": normalized_entries,
        "completed_cleanup_cursor": completed_cleanup_cursor,
        "completed_owner_journal_identity": (
            list(completed_owner_journal_identity)
            if completed_owner_journal_identity is not None
            else None
        ),
        "completed_owner_journal_sha256": completed_owner_journal_sha256,
        "content_sha256": "",
    }
    unsigned = dict(payload)
    unsigned.pop("content_sha256")
    payload["content_sha256"] = "sha256:" + hashlib.sha256(
        _canonical_owner_retirement_json(unsigned)
    ).hexdigest()
    raw = _canonical_owner_retirement_json(payload)
    if len(raw) > RUNTIME_OWNER_RETIREMENT_MAX_BYTES:
        raise ValueError("runtime_owner_retirement_tombstone_too_large")
    return raw


def _owner_retirement_identity_from_json(value: object) -> PathIdentity | None:
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(type(part) is not int or part < 0 for part in value)
    ):
        raise ValueError("runtime_owner_retirement_tombstone_identity_invalid")
    return value[0], value[1], value[2]


def _collect_owner_retirement_cleanup_entries(
    target: Path,
) -> tuple[Mapping[str, object], ...]:
    """Capture the immutable, deepest-first old-owner cleanup inventory."""

    require_plain_directory(target)
    target_identity = path_identity(target)
    require_no_alternate_data_streams(
        target,
        expected_identity=target_identity,
        expected_parent_identity=path_identity(target.parent),
        directory=True,
    )
    snapshot = snapshot_bounded_filesystem_package(target)
    entries: list[Mapping[str, object]] = []
    file_names = sorted(
        snapshot.file_names(),
        key=lambda value: (value.count("/"), value),
        reverse=True,
    )
    directory_names = sorted(
        snapshot.directory_names,
        key=lambda value: (value.count("/"), value),
        reverse=True,
    )
    for relative in file_names:
        path = target / Path(relative)
        parent = path.parent
        status = plain_file_status(path)
        identity = path_identity_from_status(status)
        parent_identity = path_identity(parent)
        require_same_identity_resolution(path, expected_status=status)
        if status.st_nlink != 1:
            raise ValueError("runtime_owner_retirement_cleanup_file_invalid")
        require_no_alternate_data_streams(
            path,
            expected_identity=identity,
            expected_parent_identity=parent_identity,
            directory=False,
            expected_size=status.st_size,
        )
        raw = read_file_no_follow(
            path,
            expected_status=status,
            maximum_size=64 * 1024 * 1024,
        )
        entries.append(
            MappingProxyType(
                {
                    "relative_path": relative,
                    "entry_kind": "file",
                    "identity": identity,
                    "expected_parent_identity": parent_identity,
                    "size": len(raw),
                    "sha256": "sha256:"
                    + hashlib.sha256(raw).hexdigest(),
                }
            )
        )
    for relative in directory_names:
        path = target / Path(relative)
        parent_identity = path_identity(path.parent)
        require_plain_directory(path)
        identity = path_identity(path)
        require_no_alternate_data_streams(
            path,
            expected_identity=identity,
            expected_parent_identity=parent_identity,
            directory=True,
        )
        entries.append(
            MappingProxyType(
                {
                    "relative_path": relative,
                    "entry_kind": "directory",
                    "identity": identity,
                    "expected_parent_identity": parent_identity,
                    "size": None,
                    "sha256": None,
                }
            )
        )
    if len(entries) > RUNTIME_OWNER_RETIREMENT_MAX_ENTRIES:
        raise ValueError("runtime_owner_retirement_cleanup_entries_invalid")
    return tuple(entries)


def _owner_retirement_tree_sha256(
    *,
    target_identity: PathIdentity,
    entries: tuple[Mapping[str, object], ...],
) -> str:
    """Digest the exact root plus the same immutable cleanup inventory."""

    value = {
        "schema_version": 1,
        "tree_kind": "runtime_owner_retirement_target",
        "target_identity": list(target_identity),
        "entries": _plain_json_value(entries),
    }
    return "sha256:" + hashlib.sha256(
        _canonical_owner_retirement_json(value)
    ).hexdigest()


def _owner_retirement_package_digest(
    entries: tuple[Mapping[str, object], ...],
) -> str:
    """Derive the historical package digest from the captured file rows."""

    files = sorted(
        (
            entry
            for entry in entries
            if entry.get("entry_kind") == "file"
        ),
        key=lambda entry: str(entry["relative_path"]),
    )
    records = b"".join(
        (
            f"{entry['relative_path']}\0{entry['size']}\0"
            f"{str(entry['sha256']).removeprefix('sha256:')}\n"
        ).encode("utf-8")
        for entry in files
    )
    return hashlib.sha256(records).hexdigest()


def _parse_owner_retirement_tombstone_bytes(
    raw: bytes,
    *,
    runtime_root: Path,
) -> Mapping[str, object]:
    """Parse and fully rederive one canonical owner-retirement tombstone."""

    try:
        if not raw or len(raw) > RUNTIME_OWNER_RETIREMENT_MAX_BYTES:
            raise ValueError("bounds")
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_runtime_attempt_unique_object,
            parse_constant=_reject_runtime_attempt_constant,
        )
        if (
            not isinstance(value, dict)
            or set(value) != RUNTIME_OWNER_RETIREMENT_FIELDS
            or raw != _canonical_owner_retirement_json(value)
            or value.get("schema_version")
            != RUNTIME_OWNER_RETIREMENT_SCHEMA_VERSION
            or value.get("record_kind") != RUNTIME_OWNER_RETIREMENT_KIND
            or value.get("state") not in {"PREPARED", "COMPLETED"}
            or not isinstance(value.get("cleanup_entries"), list)
        ):
            raise ValueError("schema")
        entries: list[dict[str, object]] = []
        for raw_entry in value["cleanup_entries"]:
            if not isinstance(raw_entry, dict):
                raise ValueError("entry")
            entry = dict(raw_entry)
            entry["identity"] = _owner_retirement_identity_from_json(
                entry.get("identity")
            )
            entry["expected_parent_identity"] = (
                _owner_retirement_identity_from_json(
                    entry.get("expected_parent_identity")
                )
            )
            entries.append(entry)
        rebuilt = _build_owner_retirement_tombstone_bytes(
            state=value["state"],
            retired_owner_transaction_id=value["retired_owner_transaction_id"],
            initial_owner_journal_path=Path(
                value["initial_owner_journal_path"]
            ),
            initial_owner_journal_identity=_owner_retirement_identity_from_json(
                value["initial_owner_journal_identity"]
            ),
            initial_owner_journal_sha256=value["initial_owner_journal_sha256"],
            retired_target_path=Path(value["retired_target_path"]),
            retired_target_parent_identity=_owner_retirement_identity_from_json(
                value["retired_target_parent_identity"]
            ),
            retired_target_identity=_owner_retirement_identity_from_json(
                value["retired_target_identity"]
            ),
            retired_target_tree_sha256=value["retired_target_tree_sha256"],
            successor_transaction_id=value["successor_transaction_id"],
            successor_package_root_sha256=value[
                "successor_package_root_sha256"
            ],
            successor_owner_journal_path=Path(
                value["successor_owner_journal_path"]
            ),
            successor_owner_journal_identity=_owner_retirement_identity_from_json(
                value["successor_owner_journal_identity"]
            ),
            successor_owner_journal_sha256=value[
                "successor_owner_journal_sha256"
            ],
            cleanup_entries=tuple(entries),
            completed_cleanup_cursor=value["completed_cleanup_cursor"],
            completed_owner_journal_identity=(
                _owner_retirement_identity_from_json(
                    value["completed_owner_journal_identity"]
                )
            ),
            completed_owner_journal_sha256=value[
                "completed_owner_journal_sha256"
            ],
        )
        if rebuilt != raw:
            raise ValueError("digest")
        target_path = Path(value["retired_target_path"])
        if target_path.parent.parent != Path(runtime_root):
            raise ValueError("runtime_root")
        return MappingProxyType(value)
    except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("runtime_owner_retirement_tombstone_invalid") from error


def _seal_owner_retirement_document(
    owner: Mapping[str, Any],
    *,
    changes: Mapping[str, object] | None = None,
) -> Mapping[str, object]:
    """Return one canonical Session owner-retirement cursor document.

    The Session owns the cursor schema, while this module owns the durable
    tombstone.  Keeping the tiny sealing bridge here makes every physical
    callback derive its successor from the authenticated predecessor rather
    than accepting caller-supplied owner evidence.
    """

    value = _plain_json_value(owner)
    if not isinstance(value, dict):
        raise ValueError("runtime_owner_retirement_cursor_invalid")
    value.pop("content_sha256", None)
    if changes is not None:
        value.update(_plain_json_value(changes))
    raw = (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    value["content_sha256"] = "sha256:" + hashlib.sha256(raw).hexdigest()
    return MappingProxyType(value)


def _owner_retirement_digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _owner_retirement_completed_commitment(
    owner: Mapping[str, Any],
) -> tuple[int, str]:
    planned_size = owner.get("planned_completed_tombstone_size")
    planned_sha256 = owner.get("planned_completed_tombstone_sha256")
    if (
        type(planned_size) is not int
        or planned_size <= 0
        or planned_size > RUNTIME_OWNER_RETIREMENT_MAX_BYTES
        or not isinstance(planned_sha256, str)
        or _PREFIXED_SHA256.fullmatch(planned_sha256) is None
    ):
        raise ValueError(
            "runtime_owner_retirement_completed_commitment_changed"
        )
    return planned_size, planned_sha256


def _owner_retirement_external_action(
    *,
    recovery: Mapping[str, Any],
    action_kind: str,
    final_path: Path,
    parent_identity: PathIdentity,
    predecessor_identity: PathIdentity | None,
    predecessor_raw: bytes | None,
    payload: bytes,
) -> Mapping[str, Any]:
    if not payload or len(payload) > RUNTIME_OWNER_RETIREMENT_MAX_BYTES:
        raise ValueError("runtime_owner_retirement_payload_invalid")
    return _owner_retirement_external_action_from_commitment(
        recovery=recovery,
        action_kind=action_kind,
        final_path=final_path,
        parent_identity=parent_identity,
        predecessor_identity=predecessor_identity,
        predecessor_raw=predecessor_raw,
        planned_successor_size=len(payload),
        planned_successor_sha256=_owner_retirement_digest(payload),
    )


def _owner_retirement_external_action_from_commitment(
    *,
    recovery: Mapping[str, Any],
    action_kind: str,
    final_path: Path,
    parent_identity: PathIdentity,
    predecessor_identity: PathIdentity | None,
    predecessor_raw: bytes | None,
    planned_successor_size: int,
    planned_successor_sha256: str,
) -> Mapping[str, Any]:
    if (
        type(planned_successor_size) is not int
        or planned_successor_size <= 0
        or planned_successor_size > RUNTIME_OWNER_RETIREMENT_MAX_BYTES
        or not isinstance(planned_successor_sha256, str)
        or _PREFIXED_SHA256.fullmatch(planned_successor_sha256) is None
    ):
        raise ValueError("runtime_owner_retirement_payload_invalid")
    if predecessor_identity is None and predecessor_raw is not None:
        raise ValueError("runtime_owner_retirement_external_invalid")
    staging_path = final_path.with_name(f"{final_path.name}.staged")
    inner_temp_path = staging_path.with_name(
        f".{staging_path.name}.live-start-atomic.tmp"
    )
    return _build_external_file_action(
        action_kind=action_kind,
        action_index=int(recovery["action_index"]) + 1,
        final_path=final_path,
        staging_path=staging_path,
        inner_temp_path=inner_temp_path,
        parent_identity=parent_identity,
        predecessor_identity=predecessor_identity,
        predecessor_size=(
            None if predecessor_raw is None else len(predecessor_raw)
        ),
        predecessor_sha256=(
            None
            if predecessor_raw is None
            else _owner_retirement_digest(predecessor_raw)
        ),
        planned_successor_size=planned_successor_size,
        planned_successor_sha256=planned_successor_sha256,
        commit_mode=(
            "create_no_replace"
            if predecessor_identity is None
            else "replace_exact"
        ),
    )


def _owner_retirement_read_bound_file(
    path: Path,
    *,
    parent_identity: PathIdentity,
    identity: PathIdentity,
    sha256: str,
) -> bytes:
    raw, observed_identity = _read_exact_runtime_external_file(
        path,
        expected_parent_identity=parent_identity,
        maximum_size=RUNTIME_OWNER_RETIREMENT_MAX_BYTES,
    )
    if observed_identity != identity or _owner_retirement_digest(raw) != sha256:
        raise ValueError("runtime_owner_retirement_authority_changed")
    return raw


def _owner_retirement_prepared_tombstone(
    *,
    owner: Mapping[str, Any],
    runtime_root: Path,
    owner_retirements_parent_identity: PathIdentity,
) -> tuple[Mapping[str, object], bytes]:
    path = Path(str(owner.get("tombstone_path")))
    parent_identity = tuple(owner.get("tombstone_parent_identity", ()))
    identity = tuple(owner.get("tombstone_identity", ()))
    digest = owner.get("tombstone_sha256")
    if (
        path.parent != runtime_root / ".hsconfig" / "owner-retirements"
        or parent_identity != owner_retirements_parent_identity
        or not _valid_path_identity(parent_identity)
        or not _valid_path_identity(identity)
        or not isinstance(digest, str)
        or _PREFIXED_SHA256.fullmatch(digest) is None
    ):
        raise ValueError("runtime_owner_retirement_cursor_invalid")
    raw = _owner_retirement_read_bound_file(
        path,
        parent_identity=parent_identity,
        identity=identity,
        sha256=digest,
    )
    tombstone = _parse_owner_retirement_tombstone_bytes(
        raw, runtime_root=runtime_root
    )
    if tombstone.get("state") != "PREPARED":
        raise ValueError("runtime_owner_retirement_tombstone_state_invalid")
    bindings = (
        "retired_owner_transaction_id",
        "initial_owner_journal_path",
        "initial_owner_journal_identity",
        "initial_owner_journal_sha256",
        "retired_target_path",
        "retired_target_parent_identity",
        "retired_target_identity",
        "retired_target_tree_sha256",
        "successor_transaction_id",
        "successor_package_root_sha256",
        "successor_owner_journal_path",
        "successor_owner_journal_identity",
        "successor_owner_journal_sha256",
        "cleanup_manifest_sha256",
        "cleanup_entry_count",
    )
    for key in bindings:
        observed = tombstone.get(key)
        expected = owner.get(key)
        if key.endswith("identity"):
            if tuple(observed or ()) != tuple(expected or ()):
                raise ValueError("runtime_owner_retirement_tombstone_changed")
        elif observed != expected:
            raise ValueError("runtime_owner_retirement_tombstone_changed")
    return tombstone, raw


def _require_owner_retirement_prepared_tree_binding(
    *,
    owner: Mapping[str, Any],
    runtime_root: Path,
    runtime_root_identity: PathIdentity,
    custom_config_identity: PathIdentity,
) -> Path:
    target = Path(str(owner.get("retired_target_path")))
    parent_identity = tuple(owner.get("retired_target_parent_identity", ()))
    target_identity = tuple(owner.get("retired_target_identity", ()))
    if not _valid_path_identity(runtime_root_identity):
        raise ValueError("runtime_owner_retirement_runtime_root_changed")
    if (
        not _valid_path_identity(parent_identity)
        or not _valid_path_identity(custom_config_identity)
        or parent_identity != custom_config_identity
        or target.parent != runtime_root / "CustomConfig"
    ):
        raise ValueError("runtime_owner_retirement_target_parent_changed")
    if not _valid_path_identity(target_identity):
        raise ValueError("runtime_owner_retirement_target_changed")
    try:
        _require_exact_runtime_root(
            runtime_root,
            expected_root_identity=runtime_root_identity,
        )
    except (OSError, ValueError) as error:
        raise ValueError(
            "runtime_owner_retirement_runtime_root_changed"
        ) from error
    try:
        _require_exact_plain_directory(
            target.parent,
            expected_parent_identity=runtime_root_identity,
            expected_identity=custom_config_identity,
            error="runtime_owner_retirement_target_parent_changed",
        )
    except (OSError, ValueError) as error:
        raise ValueError(
            "runtime_owner_retirement_target_parent_changed"
        ) from error
    try:
        _require_exact_plain_directory(
            target,
            expected_parent_identity=custom_config_identity,
            expected_identity=target_identity,
            error="runtime_owner_retirement_target_changed",
        )
    except (OSError, ValueError) as error:
        raise ValueError("runtime_owner_retirement_target_changed") from error
    return target


def _owner_retirement_prepared_bytes_from_cursor(
    *,
    owner: Mapping[str, Any],
    runtime_root: Path,
    runtime_root_identity: PathIdentity,
    custom_config_identity: PathIdentity,
) -> bytes:
    target = _require_owner_retirement_prepared_tree_binding(
        owner=owner,
        runtime_root=runtime_root,
        runtime_root_identity=runtime_root_identity,
        custom_config_identity=custom_config_identity,
    )
    parent_identity = tuple(owner["retired_target_parent_identity"])
    target_identity = tuple(owner["retired_target_identity"])
    try:
        entries = _collect_owner_retirement_cleanup_entries(target)
    except (OSError, ValueError) as error:
        raise ValueError("runtime_owner_retirement_inventory_changed") from error
    _require_owner_retirement_prepared_tree_binding(
        owner=owner,
        runtime_root=runtime_root,
        runtime_root_identity=runtime_root_identity,
        custom_config_identity=custom_config_identity,
    )
    tree_sha256 = _owner_retirement_tree_sha256(
        target_identity=target_identity,
        entries=entries,
    )
    if tree_sha256 != owner.get("retired_target_tree_sha256"):
        raise ValueError("runtime_owner_retirement_target_tree_changed")
    raw = _build_owner_retirement_tombstone_bytes(
        state="PREPARED",
        retired_owner_transaction_id=str(owner["retired_owner_transaction_id"]),
        initial_owner_journal_path=Path(str(owner["initial_owner_journal_path"])),
        initial_owner_journal_identity=tuple(owner["initial_owner_journal_identity"]),
        initial_owner_journal_sha256=str(owner["initial_owner_journal_sha256"]),
        retired_target_path=target,
        retired_target_parent_identity=parent_identity,
        retired_target_identity=target_identity,
        retired_target_tree_sha256=tree_sha256,
        successor_transaction_id=str(owner["successor_transaction_id"]),
        successor_package_root_sha256=str(owner["successor_package_root_sha256"]),
        successor_owner_journal_path=Path(str(owner["successor_owner_journal_path"])),
        successor_owner_journal_identity=tuple(owner["successor_owner_journal_identity"]),
        successor_owner_journal_sha256=str(owner["successor_owner_journal_sha256"]),
        cleanup_entries=entries,
        completed_cleanup_cursor=None,
        completed_owner_journal_identity=None,
        completed_owner_journal_sha256=None,
    )
    parsed = _parse_owner_retirement_tombstone_bytes(
        raw, runtime_root=runtime_root
    )
    if (
        parsed["cleanup_manifest_sha256"]
        != owner.get("cleanup_manifest_sha256")
        or parsed["cleanup_entry_count"] != owner.get("cleanup_entry_count")
    ):
        raise ValueError("runtime_owner_retirement_inventory_changed")
    _require_owner_retirement_prepared_tree_binding(
        owner=owner,
        runtime_root=runtime_root,
        runtime_root_identity=runtime_root_identity,
        custom_config_identity=custom_config_identity,
    )
    return raw


def _owner_retirement_current_journal(
    *,
    owner: Mapping[str, Any],
    runtime_root: Path,
    expected_cursor: int,
    cleanup_started: bool,
    transactions_parent_identity: PathIdentity,
) -> tuple[RuntimeTransactionJournal, bytes, PathIdentity]:
    path = Path(str(owner.get("initial_owner_journal_path")))
    identity = tuple(owner.get("current_owner_journal_identity", ()))
    digest = owner.get("current_owner_journal_sha256")
    if (
        path != runtime_transaction_journal_path(
            runtime_root, str(owner.get("retired_owner_transaction_id"))
        )
        or path.parent != runtime_root / ".hsconfig" / "transactions"
        or not _valid_path_identity(identity)
        or not isinstance(digest, str)
    ):
        raise ValueError("runtime_owner_retirement_journal_invalid")
    raw = _owner_retirement_read_bound_file(
        path,
        parent_identity=transactions_parent_identity,
        identity=identity,
        sha256=digest,
    )
    journal = parse_runtime_transaction_journal_bytes(
        raw,
        expected_transaction_id=str(owner["retired_owner_transaction_id"]),
    )
    if (
        journal.phase != RuntimeTransactionPhase.FINALIZED
        or not journal.owns_target
        or journal.cleanup_started != cleanup_started
        or journal.cleanup_cursor != expected_cursor
        or journal.target_identity != tuple(owner["retired_target_identity"])
        or runtime_root / journal.target_path
        != Path(str(owner["retired_target_path"]))
    ):
        raise ValueError("runtime_owner_retirement_journal_invalid")
    return journal, raw, identity


def _owner_retirement_journal_successor_bytes(
    *,
    owner: Mapping[str, Any],
    runtime_root: Path,
    cursor: int,
    cleanup_started: bool,
    transactions_parent_identity: PathIdentity,
    owner_retirements_parent_identity: PathIdentity,
) -> bytes:
    tombstone, _ = _owner_retirement_prepared_tombstone(
        owner=owner,
        runtime_root=runtime_root,
        owner_retirements_parent_identity=owner_retirements_parent_identity,
    )
    current_cursor = int(owner["cleanup_cursor"])
    journal, _raw, _identity = _owner_retirement_current_journal(
        owner=owner,
        runtime_root=runtime_root,
        expected_cursor=current_cursor,
        cleanup_started=(current_cursor != 0 or owner.get("stage") == "CLEANING"),
        transactions_parent_identity=transactions_parent_identity,
    )
    entries = tuple(
        RuntimeCleanupEntry(
            kind=str(entry["entry_kind"]),
            relative_path=str(entry["relative_path"]),
            identity=tuple(entry["identity"]),
        )
        for entry in tombstone["cleanup_entries"]
    )
    successor = replace(
        journal,
        cleanup_started=cleanup_started,
        cleanup_entries=entries,
        cleanup_cursor=cursor,
    )
    return runtime_transaction_journal_bytes(successor)


def _owner_retirement_completed_bytes(
    *,
    owner: Mapping[str, Any],
    runtime_root: Path,
    journal_identity: PathIdentity,
    journal_sha256: str,
    owner_retirements_parent_identity: PathIdentity,
) -> bytes:
    tombstone, _ = _owner_retirement_prepared_tombstone(
        owner=owner,
        runtime_root=runtime_root,
        owner_retirements_parent_identity=owner_retirements_parent_identity,
    )
    return _build_owner_retirement_tombstone_bytes(
        state="COMPLETED",
        retired_owner_transaction_id=str(tombstone["retired_owner_transaction_id"]),
        initial_owner_journal_path=Path(str(tombstone["initial_owner_journal_path"])),
        initial_owner_journal_identity=tuple(tombstone["initial_owner_journal_identity"]),
        initial_owner_journal_sha256=str(tombstone["initial_owner_journal_sha256"]),
        retired_target_path=Path(str(tombstone["retired_target_path"])),
        retired_target_parent_identity=tuple(tombstone["retired_target_parent_identity"]),
        retired_target_identity=tuple(tombstone["retired_target_identity"]),
        retired_target_tree_sha256=str(tombstone["retired_target_tree_sha256"]),
        successor_transaction_id=str(tombstone["successor_transaction_id"]),
        successor_package_root_sha256=str(tombstone["successor_package_root_sha256"]),
        successor_owner_journal_path=Path(str(tombstone["successor_owner_journal_path"])),
        successor_owner_journal_identity=tuple(tombstone["successor_owner_journal_identity"]),
        successor_owner_journal_sha256=str(tombstone["successor_owner_journal_sha256"]),
        cleanup_entries=tuple(
            {
                **dict(entry),
                "identity": tuple(entry["identity"]),
                "expected_parent_identity": tuple(
                    entry["expected_parent_identity"]
                ),
            }
            for entry in tombstone["cleanup_entries"]
        ),
        completed_cleanup_cursor=int(tombstone["cleanup_entry_count"]),
        completed_owner_journal_identity=journal_identity,
        completed_owner_journal_sha256=journal_sha256,
    )


def _owner_retirement_initial_preflight_payloads(
    *,
    old_journal: RuntimeTransactionJournal,
    cleanup_entries: tuple[Mapping[str, object], ...],
    initial_owner_journal_path: Path,
    initial_owner_journal_identity: PathIdentity,
    initial_owner_journal_sha256: str,
    retired_target_path: Path,
    retired_target_parent_identity: PathIdentity,
    retired_target_identity: PathIdentity,
    retired_target_tree_sha256: str,
    successor_transaction_id: str,
    successor_package_root_sha256: str,
    successor_owner_journal_path: Path,
    successor_owner_journal_identity: PathIdentity,
    successor_owner_journal_sha256: str,
) -> Mapping[str, bytes]:
    """Build every pre-cursor owner payload solely to enforce its byte bound.

    The final cleanup-journal identity is created only by the later exact
    replacement.  Its three platform identity integers are nevertheless
    bounded native stat values, so the completed-tombstone probe uses the
    widest portable unsigned representation.  This is a size preflight only;
    it is never persisted or used as replacement authority.
    """

    journal_entries = tuple(
        RuntimeCleanupEntry(
            kind=str(entry["entry_kind"]),
            relative_path=str(entry["relative_path"]),
            identity=tuple(entry["identity"]),
        )
        for entry in cleanup_entries
    )
    cursor_zero = replace(
        old_journal,
        cleanup_started=True,
        cleanup_entries=journal_entries,
        cleanup_cursor=0,
    )
    final = replace(cursor_zero, cleanup_cursor=len(journal_entries))
    cursor_zero_raw = runtime_transaction_journal_bytes(cursor_zero)
    final_raw = runtime_transaction_journal_bytes(final)
    prepared = _build_owner_retirement_tombstone_bytes(
        state="PREPARED",
        retired_owner_transaction_id=old_journal.transaction_id,
        initial_owner_journal_path=initial_owner_journal_path,
        initial_owner_journal_identity=initial_owner_journal_identity,
        initial_owner_journal_sha256=initial_owner_journal_sha256,
        retired_target_path=retired_target_path,
        retired_target_parent_identity=retired_target_parent_identity,
        retired_target_identity=retired_target_identity,
        retired_target_tree_sha256=retired_target_tree_sha256,
        successor_transaction_id=successor_transaction_id,
        successor_package_root_sha256=successor_package_root_sha256,
        successor_owner_journal_path=successor_owner_journal_path,
        successor_owner_journal_identity=successor_owner_journal_identity,
        successor_owner_journal_sha256=successor_owner_journal_sha256,
        cleanup_entries=cleanup_entries,
        completed_cleanup_cursor=None,
        completed_owner_journal_identity=None,
        completed_owner_journal_sha256=None,
    )
    completed = _build_owner_retirement_tombstone_bytes(
        state="COMPLETED",
        retired_owner_transaction_id=old_journal.transaction_id,
        initial_owner_journal_path=initial_owner_journal_path,
        initial_owner_journal_identity=initial_owner_journal_identity,
        initial_owner_journal_sha256=initial_owner_journal_sha256,
        retired_target_path=retired_target_path,
        retired_target_parent_identity=retired_target_parent_identity,
        retired_target_identity=retired_target_identity,
        retired_target_tree_sha256=retired_target_tree_sha256,
        successor_transaction_id=successor_transaction_id,
        successor_package_root_sha256=successor_package_root_sha256,
        successor_owner_journal_path=successor_owner_journal_path,
        successor_owner_journal_identity=successor_owner_journal_identity,
        successor_owner_journal_sha256=successor_owner_journal_sha256,
        cleanup_entries=cleanup_entries,
        completed_cleanup_cursor=len(journal_entries),
        completed_owner_journal_identity=(
            (1 << 64) - 1,
            (1 << 64) - 1,
            (1 << 64) - 1,
        ),
        completed_owner_journal_sha256=_owner_retirement_digest(final_raw),
    )
    return MappingProxyType(
        {
            "cursor_zero_v1": cursor_zero_raw,
            "final_v1": final_raw,
            "prepared_tombstone": prepared,
            "completed_tombstone": completed,
        }
    )


def _initial_owner_retirement_cursor(
    *,
    recovery: Mapping[str, Any],
    runtime_root: Path,
    layout_identities: Mapping[str, PathIdentity],
) -> tuple[Mapping[str, object], Mapping[str, Any]] | None:
    """Capture one stale owned revision before its first tombstone byte.

    This is deliberately called only from the physical final-attempt-record
    callback.  The new finalized owner and the old owner are both read under
    the persisted transactions parent, and the cleanup inventory is sealed
    before Session is offered the first ``PREPARED_PLANNED`` cursor.
    """

    install_route = recovery.get("install_route")
    if install_route == "prior_owner":
        return None
    if install_route != "new_target":
        raise ValueError("runtime_owner_retirement_initial_authority_invalid")

    transactions_parent = layout_identities["transactions"]
    retirements_parent = layout_identities["owner_retirements"]
    successor_path_raw = recovery.get("successor_journal_path")
    successor_identity_raw = recovery.get("successor_journal_identity")
    successor_sha256 = recovery.get("successor_journal_sha256")
    if (
        not isinstance(successor_path_raw, str)
        or not isinstance(successor_sha256, str)
        or not isinstance(successor_identity_raw, (list, tuple))
        or not _valid_path_identity(tuple(successor_identity_raw or ()))
    ):
        raise ValueError("runtime_owner_retirement_initial_authority_invalid")
    successor_path = Path(successor_path_raw)
    if successor_path != runtime_transaction_journal_path(
        runtime_root, str(recovery["apply_attempt_id"])
    ):
        raise ValueError("runtime_owner_retirement_initial_authority_invalid")
    successor_raw = _owner_retirement_read_bound_file(
        successor_path,
        parent_identity=transactions_parent,
        identity=tuple(successor_identity_raw),
        sha256=successor_sha256,
    )
    successor_journal = parse_runtime_transaction_journal_bytes(
        successor_raw,
        expected_transaction_id=str(recovery["apply_attempt_id"]),
    )
    if (
        successor_journal.phase != RuntimeTransactionPhase.FINALIZED
        or successor_journal.owns_target is not True
        or successor_journal.target_identity
        != tuple(recovery["successor_renamed_target_identity"])
        or runtime_root / successor_journal.target_path
        != Path(str(recovery["renamed_target_path"]))
        or successor_journal.next_config_dir
        != Path(str(recovery["renamed_target_path"])).name
        or recovery.get("successor_target_owner_journal_path")
        != str(successor_path)
        or tuple(
            recovery.get("successor_target_owner_journal_identity") or ()
        )
        != tuple(successor_identity_raw)
        or recovery.get("successor_target_owner_journal_sha256")
        != successor_sha256
    ):
        raise ValueError("runtime_owner_retirement_initial_authority_invalid")

    previous_config_dir = successor_journal.previous_config_dir
    if (
        previous_config_dir is None
        or previous_config_dir == successor_journal.next_config_dir
    ):
        return None
    retired_target = runtime_root / "CustomConfig" / previous_config_dir
    if (
        retired_target == Path(str(recovery["renamed_target_path"]))
        or retired_target.parent != runtime_root / "CustomConfig"
        or path_identity(retired_target.parent)
        != layout_identities["custom_config"]
        or not path_lexists(retired_target)
    ):
        return None
    active_config_dirs = _active_config_dirs(runtime_root)
    if (
        active_config_dirs is None
        or previous_config_dir.casefold() in active_config_dirs
    ):
        return None
    require_plain_directory(retired_target)
    retired_identity = path_identity(retired_target)
    matching_old: list[tuple[Path, RuntimeTransactionJournal, PathIdentity, bytes]] = []
    for journal in load_runtime_transaction_journals(runtime_root):
        if (
            journal.transaction_id == successor_journal.transaction_id
            or journal.phase != RuntimeTransactionPhase.FINALIZED
            or journal.owns_target is not True
            or journal.target_path
            != retired_target.relative_to(runtime_root).as_posix()
            or journal.target_identity != retired_identity
            or journal.next_config_dir != previous_config_dir
        ):
            continue
        path = runtime_transaction_journal_path(runtime_root, journal.transaction_id)
        raw, identity = _read_exact_runtime_external_file(
            path,
            expected_parent_identity=transactions_parent,
            maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
        )
        parsed = parse_runtime_transaction_journal_bytes(
            raw, expected_transaction_id=journal.transaction_id
        )
        if parsed != journal:
            raise ValueError("runtime_owner_retirement_initial_authority_invalid")
        matching_old.append((path, parsed, identity, raw))
    if len(matching_old) != 1:
        raise ValueError("runtime_owner_retirement_initial_authority_invalid")
    old_path, old_journal, old_identity, old_raw = matching_old[0]
    old_sha256 = _owner_retirement_digest(old_raw)
    if (
        old_journal.cleanup_started
        or old_journal.cleanup_cursor != 0
        or old_journal.cleanup_entries
    ):
        raise ValueError("runtime_owner_retirement_initial_authority_invalid")
    entries = _collect_owner_retirement_cleanup_entries(retired_target)
    if (
        _owner_retirement_package_digest(entries)
        != old_journal.package_root_sha256
        or path_identity(retired_target.parent)
        != layout_identities["custom_config"]
        or path_identity(retired_target) != retired_identity
    ):
        raise ValueError("runtime_owner_retirement_initial_authority_invalid")

    tombstone_path = (
        runtime_root
        / ".hsconfig"
        / "owner-retirements"
        / f"{old_journal.transaction_id}.json"
    )
    if (
        tombstone_path.parent != runtime_root / ".hsconfig" / "owner-retirements"
        or path_identity(tombstone_path.parent) != retirements_parent
        or path_lexists(tombstone_path)
    ):
        raise ValueError("runtime_owner_retirement_initial_authority_invalid")
    tree_sha256 = _owner_retirement_tree_sha256(
        target_identity=retired_identity,
        entries=entries,
    )
    preflight_payloads = _owner_retirement_initial_preflight_payloads(
        old_journal=old_journal,
        cleanup_entries=entries,
        initial_owner_journal_path=old_path,
        initial_owner_journal_identity=old_identity,
        initial_owner_journal_sha256=old_sha256,
        retired_target_path=retired_target,
        retired_target_parent_identity=layout_identities["custom_config"],
        retired_target_identity=retired_identity,
        retired_target_tree_sha256=tree_sha256,
        successor_transaction_id=str(recovery["apply_attempt_id"]),
        successor_package_root_sha256=str(recovery["package_root_sha256"]),
        successor_owner_journal_path=successor_path,
        successor_owner_journal_identity=tuple(successor_identity_raw),
        successor_owner_journal_sha256=successor_sha256,
    )
    prepared_raw = preflight_payloads["prepared_tombstone"]
    prepared = _parse_owner_retirement_tombstone_bytes(
        prepared_raw, runtime_root=runtime_root
    )
    next_entry = _owner_retirement_next_entry_changes(prepared, cursor=0)
    owner = _seal_owner_retirement_document(
        {
            "schema_version": 1,
            "evidence_kind": "live_start_owner_retirement_evidence",
            "stage": "PREPARED_PLANNED",
            "tombstone_path": str(tombstone_path),
            "tombstone_parent_identity": retirements_parent,
            "tombstone_identity": None,
            "tombstone_sha256": _owner_retirement_digest(prepared_raw),
            "retired_owner_transaction_id": old_journal.transaction_id,
            "initial_owner_journal_path": str(old_path),
            "initial_owner_journal_identity": old_identity,
            "initial_owner_journal_sha256": old_sha256,
            "current_owner_journal_identity": old_identity,
            "current_owner_journal_sha256": old_sha256,
            "retired_target_path": str(retired_target),
            "retired_target_parent_identity": layout_identities["custom_config"],
            "retired_target_identity": retired_identity,
            "retired_target_tree_sha256": tree_sha256,
            "successor_transaction_id": str(recovery["apply_attempt_id"]),
            "successor_package_root_sha256": str(recovery["package_root_sha256"]),
            "successor_owner_journal_path": str(successor_path),
            "successor_owner_journal_identity": tuple(successor_identity_raw),
            "successor_owner_journal_sha256": successor_sha256,
            "cleanup_manifest_sha256": prepared["cleanup_manifest_sha256"],
            "cleanup_entry_count": prepared["cleanup_entry_count"],
            "cleanup_cursor": 0,
            "planned_completed_tombstone_size": None,
            "planned_completed_tombstone_sha256": None,
            **next_entry,
            "old_owner_journal_retired": False,
        }
    )
    external = _owner_retirement_external_action(
        recovery=recovery,
        action_kind="commit_owner_retirement_prepared",
        final_path=tombstone_path,
        parent_identity=retirements_parent,
        predecessor_identity=None,
        predecessor_raw=None,
        payload=prepared_raw,
    )
    return owner, external


def _require_owner_retirement_staging_reconciled(
    *,
    external: Mapping[str, Any],
) -> tuple[Path, Path]:
    final_path = Path(str(external.get("final_path")))
    staging_path = Path(str(external.get("staging_path")))
    inner_temp_path = Path(str(external.get("inner_temp_path")))
    if (
        not all(
            path.is_absolute()
            for path in (final_path, staging_path, inner_temp_path)
        )
        or staging_path != final_path.with_name(f"{final_path.name}.staged")
        or inner_temp_path
        != staging_path.with_name(
            f".{staging_path.name}.live-start-atomic.tmp"
        )
    ):
        raise ValueError("runtime_owner_retirement_materialization_invalid")
    if path_lexists(staging_path) or path_lexists(inner_temp_path):
        raise ValueError(
            "runtime_owner_retirement_staging_reconciliation_required"
        )
    return staging_path, inner_temp_path


def _owner_retirement_materialize_staging(
    *,
    recovery: Mapping[str, Any],
    payload: bytes,
    commit_action: str,
    terminal_retirement: Mapping[str, Any] | None = None,
) -> (
    RuntimeApplyRecoveryPhysicalPostcondition
    | TerminalResolutionPhysicalPostcondition
):
    external = recovery.get("external_file_action")
    owner = recovery.get("owner_retirement")
    if (
        not isinstance(owner, Mapping)
        or not isinstance(external, Mapping)
        or external.get("stage") != "PLANNED"
        or external.get("action_kind") != commit_action
    ):
        raise ValueError("runtime_owner_retirement_materialization_invalid")
    if (
        len(payload) != external.get("planned_successor_size")
        or _owner_retirement_digest(payload)
        != external.get("planned_successor_sha256")
    ):
        raise ValueError("runtime_owner_retirement_payload_changed")
    final_path = Path(str(external.get("final_path")))
    staging_path, inner_temp_path = (
        _require_owner_retirement_staging_reconciled(external=external)
    )
    parent_identity = tuple(external.get("parent_identity", ()))
    if not _valid_path_identity(parent_identity):
        raise ValueError("runtime_owner_retirement_materialization_invalid")
    if external.get("predecessor_state") == "absent":
        if path_lexists(final_path):
            raise ValueError("runtime_owner_retirement_final_changed")
    elif external.get("predecessor_state") == "exact":
        predecessor_raw, predecessor_identity = _read_exact_runtime_external_file(
            final_path,
            expected_parent_identity=parent_identity,
            maximum_size=RUNTIME_OWNER_RETIREMENT_MAX_BYTES,
        )
        if (
            predecessor_identity != tuple(external.get("predecessor_identity", ()))
            or len(predecessor_raw) != external.get("predecessor_size")
            or _owner_retirement_digest(predecessor_raw)
            != external.get("predecessor_sha256")
        ):
            raise ValueError("runtime_owner_retirement_final_changed")
    else:
        raise ValueError("runtime_owner_retirement_materialization_invalid")
    materialized = atomic_materialize_staging_bytes(
        staging_path=staging_path,
        inner_temp_path=inner_temp_path,
        payload=payload,
        expected_parent_identity=parent_identity,
        maximum_size=RUNTIME_OWNER_RETIREMENT_MAX_BYTES,
    )
    staging_identity = materialized.identity
    staging_size = materialized.size
    staging_sha256 = materialized.sha256
    next_external = _plain_json_value(external)
    if not isinstance(next_external, dict):
        raise RuntimeError("runtime_owner_retirement_external_invalid")
    next_external.pop("content_sha256", None)
    next_external.update(
        {
            "stage": "STAGING_BOUND",
            "staging_identity": staging_identity,
            "staging_size": staging_size,
            "staging_sha256": staging_sha256,
        }
    )
    return _owner_retirement_owner_external_postcondition(
        recovery=recovery,
        action="materialize_file_action_staging",
        owner=owner,
        next_owner=_seal_owner_retirement_document(owner),
        next_action=commit_action,
        next_external=seal_embedded_document(
            "external_file_action", next_external
        ),
        terminal_retirement=terminal_retirement,
    )


def _owner_retirement_commit_external(
    *,
    external: Mapping[str, Any],
    payload: bytes,
) -> tuple[PathIdentity, bytes]:
    if external.get("stage") != "STAGING_BOUND":
        raise ValueError("runtime_owner_retirement_commit_invalid")
    final_path = Path(str(external.get("final_path")))
    staging_path = Path(str(external.get("staging_path")))
    inner_temp_path = Path(str(external.get("inner_temp_path")))
    parent_identity = tuple(external.get("parent_identity", ()))
    staging_identity = tuple(external.get("staging_identity", ()))
    if (
        not _valid_path_identity(parent_identity)
        or not _valid_path_identity(staging_identity)
        or external.get("staging_size") != len(payload)
        or external.get("staging_sha256") != _owner_retirement_digest(payload)
        or external.get("planned_successor_size") != len(payload)
        or external.get("planned_successor_sha256")
        != _owner_retirement_digest(payload)
        or path_lexists(inner_temp_path)
    ):
        raise ValueError("runtime_owner_retirement_commit_invalid")
    if path_lexists(final_path) and not path_lexists(staging_path):
        raw, final_identity = _read_exact_runtime_external_file(
            final_path,
            expected_parent_identity=parent_identity,
            maximum_size=RUNTIME_OWNER_RETIREMENT_MAX_BYTES,
        )
    elif external.get("commit_mode") == "create_no_replace":
        committed = atomic_commit_bound_staging_no_replace(
            path=final_path,
            staging_path=staging_path,
            expected_staging_identity=staging_identity,
            expected_size=len(payload),
            expected_sha256=_owner_retirement_digest(payload),
            expected_parent_identity=parent_identity,
        )
        final_identity = committed.identity
        raw, observed_identity = _read_exact_runtime_external_file(
            final_path,
            expected_parent_identity=parent_identity,
            maximum_size=RUNTIME_OWNER_RETIREMENT_MAX_BYTES,
        )
        if observed_identity != final_identity:
            raise ValueError("runtime_owner_retirement_commit_changed")
    elif external.get("commit_mode") == "replace_exact":
        predecessor_identity = tuple(external.get("predecessor_identity", ()))
        if not _valid_path_identity(predecessor_identity):
            raise ValueError("runtime_owner_retirement_commit_invalid")
        committed = atomic_commit_bound_staging_replace(
            path=final_path,
            staging_path=staging_path,
            expected_predecessor_identity=predecessor_identity,
            expected_staging_identity=staging_identity,
            expected_size=len(payload),
            expected_sha256=_owner_retirement_digest(payload),
            expected_parent_identity=parent_identity,
        )
        final_identity = committed.identity
        raw, observed_identity = _read_exact_runtime_external_file(
            final_path,
            expected_parent_identity=parent_identity,
            maximum_size=RUNTIME_OWNER_RETIREMENT_MAX_BYTES,
        )
        if observed_identity != final_identity:
            raise ValueError("runtime_owner_retirement_commit_changed")
    else:
        raise ValueError("runtime_owner_retirement_commit_invalid")
    if (
        final_identity != staging_identity
        or raw != payload
        or path_lexists(staging_path)
        or path_lexists(inner_temp_path)
    ):
        raise ValueError("runtime_owner_retirement_commit_changed")
    return final_identity, raw


def _owner_retirement_visible_bound_commit_payload(
    *,
    external: Mapping[str, Any],
    expected_action: str,
) -> bytes | None:
    if (
        external.get("stage") != "STAGING_BOUND"
        or external.get("action_kind") != expected_action
    ):
        raise ValueError("runtime_owner_retirement_commit_invalid")
    final_path = Path(str(external.get("final_path")))
    staging_path = Path(str(external.get("staging_path")))
    inner_temp_path = Path(str(external.get("inner_temp_path")))
    if (
        staging_path
        != final_path.with_name(f"{final_path.name}.staged")
        or inner_temp_path
        != staging_path.with_name(
            f".{staging_path.name}.live-start-atomic.tmp"
        )
    ):
        raise ValueError("runtime_owner_retirement_commit_invalid")
    if not path_lexists(final_path) or path_lexists(staging_path):
        return None
    try:
        parent_identity = tuple(external.get("parent_identity", ()))
        staging_identity = tuple(external.get("staging_identity", ()))
    except TypeError as error:
        raise ValueError(
            "runtime_owner_retirement_commit_invalid"
        ) from error
    if (
        not _valid_path_identity(parent_identity)
        or not _valid_path_identity(staging_identity)
        or path_lexists(inner_temp_path)
        or external.get("staging_size")
        != external.get("planned_successor_size")
        or external.get("staging_sha256")
        != external.get("planned_successor_sha256")
    ):
        raise ValueError("runtime_owner_retirement_commit_invalid")
    raw, observed_identity = _read_exact_runtime_external_file(
        final_path,
        expected_parent_identity=parent_identity,
        maximum_size=RUNTIME_OWNER_RETIREMENT_MAX_BYTES,
    )
    if (
        observed_identity != staging_identity
        or len(raw) != external.get("staging_size")
        or _owner_retirement_digest(raw)
        != external.get("staging_sha256")
    ):
        raise ValueError("runtime_owner_retirement_commit_changed")
    return raw


def _validate_owner_retirement_visible_journal_commit(
    *,
    owner: Mapping[str, Any],
    prepared_tombstone: Mapping[str, object],
    raw: bytes,
    runtime_root: Path,
    expected_cursor: int,
) -> None:
    try:
        journal = parse_runtime_transaction_journal_bytes(
            raw,
            expected_transaction_id=str(
                owner["retired_owner_transaction_id"]
            ),
        )
        expected_entries = tuple(
            RuntimeCleanupEntry(
                kind=str(entry["entry_kind"]),
                relative_path=str(entry["relative_path"]),
                identity=tuple(entry["identity"]),
            )
            for entry in prepared_tombstone["cleanup_entries"]
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(
            "runtime_owner_retirement_visible_journal_invalid"
        ) from error
    if (
        journal.phase != RuntimeTransactionPhase.FINALIZED
        or not journal.owns_target
        or not journal.cleanup_started
        or journal.cleanup_cursor != expected_cursor
        or journal.target_identity
        != tuple(owner["retired_target_identity"])
        or runtime_root / journal.target_path
        != Path(str(owner["retired_target_path"]))
        or journal.cleanup_entries != expected_entries
    ):
        raise ValueError(
            "runtime_owner_retirement_visible_journal_invalid"
        )


def _validate_owner_retirement_visible_completed_commit(
    *,
    owner: Mapping[str, Any],
    raw: bytes,
    runtime_root: Path,
) -> None:
    completed = _parse_owner_retirement_tombstone_bytes(
        raw,
        runtime_root=runtime_root,
    )
    direct_bindings = (
        "retired_owner_transaction_id",
        "initial_owner_journal_path",
        "initial_owner_journal_identity",
        "initial_owner_journal_sha256",
        "retired_target_path",
        "retired_target_parent_identity",
        "retired_target_identity",
        "retired_target_tree_sha256",
        "successor_transaction_id",
        "successor_package_root_sha256",
        "successor_owner_journal_path",
        "successor_owner_journal_identity",
        "successor_owner_journal_sha256",
        "cleanup_manifest_sha256",
        "cleanup_entry_count",
    )
    for key in direct_bindings:
        observed = completed.get(key)
        expected = owner.get(key)
        if key.endswith("identity"):
            if tuple(observed or ()) != tuple(expected or ()):
                raise ValueError(
                    "runtime_owner_retirement_completed_commit_changed"
                )
        elif observed != expected:
            raise ValueError(
                "runtime_owner_retirement_completed_commit_changed"
            )
    if (
        completed.get("state") != "COMPLETED"
        or owner.get("cleanup_cursor")
        != owner.get("cleanup_entry_count")
        or completed.get("completed_cleanup_cursor")
        != owner.get("cleanup_entry_count")
        or tuple(completed.get("completed_owner_journal_identity") or ())
        != tuple(owner.get("current_owner_journal_identity") or ())
        or completed.get("completed_owner_journal_sha256")
        != owner.get("current_owner_journal_sha256")
        or path_lexists(Path(str(owner["retired_target_path"])))
    ):
        raise ValueError(
            "runtime_owner_retirement_completed_commit_changed"
        )


def _owner_retirement_owner_external_postcondition(
    *,
    recovery: Mapping[str, Any],
    action: str,
    owner: Mapping[str, Any],
    next_owner: Mapping[str, object],
    next_action: str,
    next_external: Mapping[str, Any] | None,
    evidence: Mapping[str, object] | None = None,
    terminal_retirement: Mapping[str, Any] | None = None,
    terminal_disposition: str | None = None,
) -> (
    RuntimeApplyRecoveryPhysicalPostcondition
    | TerminalResolutionPhysicalPostcondition
):
    if terminal_retirement is not None:
        current_resolution = terminal_retirement.get(
            "terminal_resolution_evidence"
        )
        if (
            not isinstance(current_resolution, Mapping)
            or current_resolution.get("owner_retirement") != owner
            or current_resolution.get("external_file_action")
            != recovery.get("external_file_action")
            or current_resolution.get("action_index")
            != recovery.get("action_index")
        ):
            raise ValueError("runtime_terminal_owner_cursor_mismatch")
        current_disposition = current_resolution.get(
            "resolved_physical_disposition"
        )
        if action == "observe_owner_retirement_completed":
            if (
                terminal_disposition != "COMMITTED"
                or current_disposition
                not in {
                    "COMMITTED_RECOVERY_PENDING",
                    "UNKNOWN_REQUIRES_RECOVERY",
                }
            ):
                raise ValueError(
                    "runtime_terminal_owner_disposition_invalid"
                )
        elif terminal_disposition is not None:
            raise ValueError(
                "runtime_terminal_owner_disposition_invalid"
            )
        next_resolution = _plain_json_value(current_resolution)
        next_retirement = _plain_json_value(terminal_retirement)
        if not isinstance(next_resolution, dict) or not isinstance(
            next_retirement,
            dict,
        ):
            raise ValueError("runtime_terminal_owner_cursor_mismatch")
        next_resolution.pop("content_sha256", None)
        next_resolution.update(
            {
                "action_index": int(recovery["action_index"]) + 1,
                "owner_retirement": next_owner,
                "external_file_action": next_external,
            }
        )
        if terminal_disposition is not None:
            next_resolution["resolved_physical_disposition"] = (
                terminal_disposition
            )
        next_retirement.pop("content_sha256", None)
        next_retirement["terminal_resolution_evidence"] = (
            _plain_json_value(_seal_terminal_resolution(next_resolution))
        )
        value: dict[str, object] = {
            "terminal_retirement": seal_embedded_document(
                "terminal_retirement",
                next_retirement,
            )
        }
        if evidence is not None:
            value.update(evidence)
        return TerminalResolutionPhysicalPostcondition(
            action="physical_recovery_advanced",
            evidence=value,
        )
    if terminal_disposition is not None:
        raise ValueError("runtime_terminal_owner_disposition_invalid")
    successor = _seal_apply_recovery_successor(
        recovery,
        changes={
            "action_index": int(recovery["action_index"]) + 1,
            "expected_action": next_action,
            "owner_retirement": next_owner,
            "external_file_action": next_external,
        },
    )
    value: dict[str, object] = {"apply_recovery": successor}
    if evidence is not None:
        value.update(evidence)
    return RuntimeApplyRecoveryPhysicalPostcondition(action=action, evidence=value)


def _owner_retirement_next_entry_changes(
    tombstone: Mapping[str, object],
    *,
    cursor: int,
) -> Mapping[str, object]:
    entries = tombstone["cleanup_entries"]
    if not isinstance(entries, list):
        raise ValueError("runtime_owner_retirement_tombstone_invalid")
    if cursor == len(entries):
        return MappingProxyType(
            {
                "next_entry_relative_path": None,
                "next_entry_kind": None,
                "next_entry_identity": None,
                "next_entry_parent_identity": None,
                "next_entry_size": None,
                "next_entry_sha256": None,
            }
        )
    entry = entries[cursor]
    if not isinstance(entry, Mapping):
        raise ValueError("runtime_owner_retirement_tombstone_invalid")
    return MappingProxyType(
        {
            "next_entry_relative_path": entry["relative_path"],
            "next_entry_kind": entry["entry_kind"],
            "next_entry_identity": entry["identity"],
            "next_entry_parent_identity": entry["expected_parent_identity"],
            "next_entry_size": entry["size"],
            "next_entry_sha256": entry["sha256"],
        }
    )


def _owner_retirement_materialize_action(
    *,
    recovery: Mapping[str, Any],
    runtime_root: Path,
    layout_identities: Mapping[str, PathIdentity],
    terminal_retirement: Mapping[str, Any] | None = None,
) -> (
    RuntimeApplyRecoveryPhysicalPostcondition
    | TerminalResolutionPhysicalPostcondition
):
    external = recovery.get("external_file_action")
    if not isinstance(external, Mapping):
        raise ValueError("runtime_owner_retirement_materialization_invalid")
    _require_owner_retirement_staging_reconciled(external=external)
    owner = recovery.get("owner_retirement")
    if not isinstance(owner, Mapping):
        raise ValueError("runtime_owner_retirement_cursor_missing")
    stage = owner.get("stage")
    if stage == "PREPARED_PLANNED":
        payload = _owner_retirement_prepared_bytes_from_cursor(
            owner=owner,
            runtime_root=runtime_root,
            runtime_root_identity=tuple(
                recovery.get("runtime_root_identity", ())
            ),
            custom_config_identity=tuple(
                layout_identities.get("custom_config", ())
            ),
        )
        action = "commit_owner_retirement_prepared"
    elif stage == "PREPARED":
        payload = _owner_retirement_journal_successor_bytes(
            owner=owner,
            runtime_root=runtime_root,
            cursor=0,
            cleanup_started=True,
            transactions_parent_identity=layout_identities["transactions"],
            owner_retirements_parent_identity=layout_identities["owner_retirements"],
        )
        action = "initialize_owner_cleanup_journal"
    elif stage == "CLEANING":
        payload = _owner_retirement_journal_successor_bytes(
            owner=owner,
            runtime_root=runtime_root,
            cursor=int(owner["cleanup_cursor"]) + 1,
            cleanup_started=True,
            transactions_parent_identity=layout_identities["transactions"],
            owner_retirements_parent_identity=layout_identities["owner_retirements"],
        )
        action = "advance_owner_cleanup_journal"
    elif stage == "TARGET_RETIRED":
        payload = _owner_retirement_completed_bytes(
            owner=owner,
            runtime_root=runtime_root,
            journal_identity=tuple(owner["current_owner_journal_identity"]),
            journal_sha256=str(owner["current_owner_journal_sha256"]),
            owner_retirements_parent_identity=layout_identities["owner_retirements"],
        )
        action = "commit_owner_retirement_completed"
    else:
        raise ValueError("runtime_owner_retirement_materialization_stage_invalid")
    return _owner_retirement_materialize_staging(
        recovery=recovery,
        payload=payload,
        commit_action=action,
        terminal_retirement=terminal_retirement,
    )


def _owner_retirement_commit_prepared_action(
    *,
    recovery: Mapping[str, Any],
    runtime_root: Path,
    layout_identities: Mapping[str, PathIdentity],
    terminal_retirement: Mapping[str, Any] | None = None,
) -> (
    RuntimeApplyRecoveryPhysicalPostcondition
    | TerminalResolutionPhysicalPostcondition
):
    owner = recovery.get("owner_retirement")
    external = recovery.get("external_file_action")
    if (
        not isinstance(owner, Mapping)
        or not isinstance(external, Mapping)
        or owner.get("stage") != "PREPARED_PLANNED"
        or external.get("action_kind") != "commit_owner_retirement_prepared"
    ):
        raise ValueError("runtime_owner_retirement_prepared_commit_invalid")
    payload = _owner_retirement_prepared_bytes_from_cursor(
        owner=owner,
        runtime_root=runtime_root,
        runtime_root_identity=tuple(recovery.get("runtime_root_identity", ())),
        custom_config_identity=tuple(
            layout_identities.get("custom_config", ())
        ),
    )
    identity, raw = _owner_retirement_commit_external(
        external=external, payload=payload
    )
    if _owner_retirement_digest(raw) != owner.get("tombstone_sha256"):
        raise ValueError("runtime_owner_retirement_prepared_commit_changed")
    next_owner = _seal_owner_retirement_document(
        owner,
        changes={"stage": "PREPARED", "tombstone_identity": identity},
    )
    journal_payload = _owner_retirement_journal_successor_bytes(
        owner=next_owner,
        runtime_root=runtime_root,
        cursor=0,
        cleanup_started=True,
        transactions_parent_identity=layout_identities["transactions"],
        owner_retirements_parent_identity=layout_identities["owner_retirements"],
    )
    next_external = _owner_retirement_external_action(
        recovery=recovery,
        action_kind="initialize_owner_cleanup_journal",
        final_path=Path(str(next_owner["initial_owner_journal_path"])),
        parent_identity=layout_identities["transactions"],
        predecessor_identity=tuple(next_owner["current_owner_journal_identity"]),
        predecessor_raw=_owner_retirement_read_bound_file(
            Path(str(next_owner["initial_owner_journal_path"])),
            parent_identity=layout_identities["transactions"],
            identity=tuple(next_owner["current_owner_journal_identity"]),
            sha256=str(next_owner["current_owner_journal_sha256"]),
        ),
        payload=journal_payload,
    )
    return _owner_retirement_owner_external_postcondition(
        recovery=recovery,
        action="commit_owner_retirement_prepared",
        owner=owner,
        next_owner=next_owner,
        next_action="materialize_file_action_staging",
        next_external=next_external,
        terminal_retirement=terminal_retirement,
    )


def _owner_retirement_initialize_journal_action(
    *,
    recovery: Mapping[str, Any],
    runtime_root: Path,
    layout_identities: Mapping[str, PathIdentity],
    terminal_retirement: Mapping[str, Any] | None = None,
) -> (
    RuntimeApplyRecoveryPhysicalPostcondition
    | TerminalResolutionPhysicalPostcondition
):
    owner = recovery.get("owner_retirement")
    external = recovery.get("external_file_action")
    if (
        not isinstance(owner, Mapping)
        or not isinstance(external, Mapping)
        or owner.get("stage") != "PREPARED"
        or external.get("action_kind") != "initialize_owner_cleanup_journal"
    ):
        raise ValueError("runtime_owner_retirement_initialize_invalid")
    visible_payload = _owner_retirement_visible_bound_commit_payload(
        external=external,
        expected_action="initialize_owner_cleanup_journal",
    )
    payload = visible_payload
    if payload is None:
        payload = _owner_retirement_journal_successor_bytes(
            owner=owner,
            runtime_root=runtime_root,
            cursor=0,
            cleanup_started=True,
            transactions_parent_identity=layout_identities["transactions"],
            owner_retirements_parent_identity=layout_identities[
                "owner_retirements"
            ],
        )
    else:
        prepared_tombstone, _ = _owner_retirement_prepared_tombstone(
            owner=owner,
            runtime_root=runtime_root,
            owner_retirements_parent_identity=layout_identities[
                "owner_retirements"
            ],
        )
        _validate_owner_retirement_visible_journal_commit(
            owner=owner,
            prepared_tombstone=prepared_tombstone,
            raw=payload,
            runtime_root=runtime_root,
            expected_cursor=0,
        )
    identity, raw = _owner_retirement_commit_external(
        external=external, payload=payload
    )
    tombstone, _ = _owner_retirement_prepared_tombstone(
        owner=owner,
        runtime_root=runtime_root,
        owner_retirements_parent_identity=layout_identities["owner_retirements"],
    )
    changes: dict[str, object] = {
        "stage": "CLEANING",
        "current_owner_journal_identity": identity,
        "current_owner_journal_sha256": _owner_retirement_digest(raw),
    }
    if int(owner["cleanup_entry_count"]) == 0:
        completed = _owner_retirement_completed_bytes(
            owner=owner,
            runtime_root=runtime_root,
            journal_identity=identity,
            journal_sha256=_owner_retirement_digest(raw),
            owner_retirements_parent_identity=layout_identities["owner_retirements"],
        )
        changes.update(
            {
                "planned_completed_tombstone_size": len(completed),
                "planned_completed_tombstone_sha256": _owner_retirement_digest(
                    completed
                ),
            }
        )
    next_owner = _seal_owner_retirement_document(owner, changes=changes)
    next_action = (
        "retire_owner_target_root"
        if int(tombstone["cleanup_entry_count"]) == 0
        else "delete_owner_cleanup_entry"
    )
    return _owner_retirement_owner_external_postcondition(
        recovery=recovery,
        action="initialize_owner_cleanup_journal",
        owner=owner,
        next_owner=next_owner,
        next_action=next_action,
        next_external=None,
        terminal_retirement=terminal_retirement,
    )


def _owner_retirement_delete_entry_action(
    *,
    recovery: Mapping[str, Any],
    runtime_root: Path,
    layout_identities: Mapping[str, PathIdentity],
    terminal_retirement: Mapping[str, Any] | None = None,
) -> (
    RuntimeApplyRecoveryPhysicalPostcondition
    | TerminalResolutionPhysicalPostcondition
):
    owner = recovery.get("owner_retirement")
    if not isinstance(owner, Mapping) or owner.get("stage") != "CLEANING":
        raise ValueError("runtime_owner_retirement_delete_invalid")
    tombstone, _ = _owner_retirement_prepared_tombstone(
        owner=owner,
        runtime_root=runtime_root,
        owner_retirements_parent_identity=layout_identities["owner_retirements"],
    )
    cursor = int(owner["cleanup_cursor"])
    entries = tombstone["cleanup_entries"]
    if not isinstance(entries, list) or cursor >= len(entries):
        raise ValueError("runtime_owner_retirement_delete_invalid")
    entry = entries[cursor]
    if not isinstance(entry, Mapping):
        raise ValueError("runtime_owner_retirement_delete_invalid")
    target = Path(str(owner["retired_target_path"]))
    target_parent_identity = tuple(owner["retired_target_parent_identity"])
    target_identity = tuple(owner["retired_target_identity"])
    if (
        path_identity(target.parent) != target_parent_identity
        or path_identity(target) != target_identity
    ):
        raise ValueError("runtime_owner_retirement_target_changed")
    entry_path = target / Path(str(entry["relative_path"]))
    expected_parent_identity = tuple(entry["expected_parent_identity"])
    if path_identity(entry_path.parent) != expected_parent_identity:
        raise ValueError("runtime_owner_retirement_entry_parent_changed")
    preexisting = path_lexists(entry_path)
    if preexisting:
        expected_identity = tuple(entry["identity"])
        if entry["entry_kind"] == "file":
            raw, identity = _read_exact_runtime_external_file(
                entry_path,
                expected_parent_identity=expected_parent_identity,
                maximum_size=64 * 1024 * 1024,
            )
            if (
                identity != expected_identity
                or len(raw) != entry["size"]
                or _owner_retirement_digest(raw) != entry["sha256"]
            ):
                raise ValueError("runtime_owner_retirement_entry_changed")
            secure_unlink_verified(
                entry_path,
                expected_identity=identity,
                expected_parent_identity=expected_parent_identity,
                expected_size=len(raw),
                expected_sha256=_owner_retirement_digest(raw).removeprefix(
                    "sha256:"
                ),
            )
        else:
            require_plain_directory(entry_path)
            if (
                path_identity(entry_path.parent) != expected_parent_identity
                or path_identity(entry_path) != expected_identity
            ):
                raise ValueError("runtime_owner_retirement_entry_changed")
            secure_rmdir_verified(
                entry_path,
                expected_identity=expected_identity,
                expected_parent_identity=expected_parent_identity,
            )
    journal_payload = _owner_retirement_journal_successor_bytes(
        owner=owner,
        runtime_root=runtime_root,
        cursor=cursor + 1,
        cleanup_started=True,
        transactions_parent_identity=layout_identities["transactions"],
        owner_retirements_parent_identity=layout_identities["owner_retirements"],
    )
    journal_path = Path(str(owner["initial_owner_journal_path"]))
    current_raw = _owner_retirement_read_bound_file(
        journal_path,
        parent_identity=layout_identities["transactions"],
        identity=tuple(owner["current_owner_journal_identity"]),
        sha256=str(owner["current_owner_journal_sha256"]),
    )
    next_external = _owner_retirement_external_action(
        recovery=recovery,
        action_kind="advance_owner_cleanup_journal",
        final_path=journal_path,
        parent_identity=layout_identities["transactions"],
        predecessor_identity=tuple(owner["current_owner_journal_identity"]),
        predecessor_raw=current_raw,
        payload=journal_payload,
    )
    postcondition = {
        "target_path": owner["retired_target_path"],
        "historical_target_identity": owner["retired_target_identity"],
        "target_parent_identity": owner["retired_target_parent_identity"],
        "entry_relative_path": owner["next_entry_relative_path"],
        "entry_kind": owner["next_entry_kind"],
        "entry_identity": owner["next_entry_identity"],
        "entry_parent_identity": owner["next_entry_parent_identity"],
        "entry_size": owner["next_entry_size"],
        "entry_sha256": owner["next_entry_sha256"],
        "prepared_tombstone_path": owner["tombstone_path"],
        "prepared_tombstone_identity": owner["tombstone_identity"],
        "prepared_tombstone_sha256": owner["tombstone_sha256"],
        "current_owner_journal_path": owner["initial_owner_journal_path"],
        "current_owner_journal_identity": owner["current_owner_journal_identity"],
        "current_owner_journal_sha256": owner["current_owner_journal_sha256"],
        "cleanup_manifest_sha256": owner["cleanup_manifest_sha256"],
        "cleanup_entry_count": owner["cleanup_entry_count"],
        "cleanup_cursor": owner["cleanup_cursor"],
        "disposition": "removed" if preexisting else "already_absent",
    }
    return _owner_retirement_owner_external_postcondition(
        recovery=recovery,
        action="delete_owner_cleanup_entry",
        owner=owner,
        next_owner=_seal_owner_retirement_document(owner),
        next_action="materialize_file_action_staging",
        next_external=next_external,
        evidence={"owner_delete_postcondition": postcondition},
        terminal_retirement=terminal_retirement,
    )


def _owner_retirement_advance_journal_action(
    *,
    recovery: Mapping[str, Any],
    runtime_root: Path,
    layout_identities: Mapping[str, PathIdentity],
    terminal_retirement: Mapping[str, Any] | None = None,
) -> (
    RuntimeApplyRecoveryPhysicalPostcondition
    | TerminalResolutionPhysicalPostcondition
):
    owner = recovery.get("owner_retirement")
    external = recovery.get("external_file_action")
    if (
        not isinstance(owner, Mapping)
        or not isinstance(external, Mapping)
        or owner.get("stage") != "CLEANING"
        or external.get("action_kind") != "advance_owner_cleanup_journal"
    ):
        raise ValueError("runtime_owner_retirement_advance_invalid")
    cursor = int(owner["cleanup_cursor"])
    visible_payload = _owner_retirement_visible_bound_commit_payload(
        external=external,
        expected_action="advance_owner_cleanup_journal",
    )
    payload = visible_payload
    if payload is None:
        payload = _owner_retirement_journal_successor_bytes(
            owner=owner,
            runtime_root=runtime_root,
            cursor=cursor + 1,
            cleanup_started=True,
            transactions_parent_identity=layout_identities["transactions"],
            owner_retirements_parent_identity=layout_identities[
                "owner_retirements"
            ],
        )
    else:
        prepared_tombstone, _ = _owner_retirement_prepared_tombstone(
            owner=owner,
            runtime_root=runtime_root,
            owner_retirements_parent_identity=layout_identities[
                "owner_retirements"
            ],
        )
        _validate_owner_retirement_visible_journal_commit(
            owner=owner,
            prepared_tombstone=prepared_tombstone,
            raw=payload,
            runtime_root=runtime_root,
            expected_cursor=cursor + 1,
        )
    identity, raw = _owner_retirement_commit_external(
        external=external, payload=payload
    )
    tombstone, _ = _owner_retirement_prepared_tombstone(
        owner=owner,
        runtime_root=runtime_root,
        owner_retirements_parent_identity=layout_identities["owner_retirements"],
    )
    next_cursor = cursor + 1
    changes: dict[str, object] = {
        "current_owner_journal_identity": identity,
        "current_owner_journal_sha256": _owner_retirement_digest(raw),
        "cleanup_cursor": next_cursor,
    }
    changes.update(_owner_retirement_next_entry_changes(tombstone, cursor=next_cursor))
    if next_cursor == int(tombstone["cleanup_entry_count"]):
        completed = _owner_retirement_completed_bytes(
            owner=owner,
            runtime_root=runtime_root,
            journal_identity=identity,
            journal_sha256=_owner_retirement_digest(raw),
            owner_retirements_parent_identity=layout_identities["owner_retirements"],
        )
        changes.update(
            {
                "planned_completed_tombstone_size": len(completed),
                "planned_completed_tombstone_sha256": _owner_retirement_digest(
                    completed
                ),
            }
        )
    next_owner = _seal_owner_retirement_document(owner, changes=changes)
    return _owner_retirement_owner_external_postcondition(
        recovery=recovery,
        action="advance_owner_cleanup_journal",
        owner=owner,
        next_owner=next_owner,
        next_action=(
            "retire_owner_target_root"
            if next_cursor == int(tombstone["cleanup_entry_count"])
            else "delete_owner_cleanup_entry"
        ),
        next_external=None,
        terminal_retirement=terminal_retirement,
    )


def _require_owner_retirement_target_parent_binding(
    *,
    recovery: Mapping[str, Any],
    owner: Mapping[str, Any],
    runtime_root: Path,
    layout_identities: Mapping[str, PathIdentity],
) -> tuple[Path, PathIdentity]:
    target = Path(str(owner.get("retired_target_path")))
    try:
        parent_identity = tuple(owner["retired_target_parent_identity"])
        custom_config_identity = tuple(layout_identities["custom_config"])
        runtime_root_identity = tuple(recovery["runtime_root_identity"])
    except (KeyError, TypeError) as error:
        raise ValueError(
            "runtime_owner_retirement_target_parent_changed"
        ) from error
    if (
        target.parent != runtime_root / "CustomConfig"
        or not _valid_path_identity(parent_identity)
        or not _valid_path_identity(custom_config_identity)
        or not _valid_path_identity(runtime_root_identity)
        or parent_identity != custom_config_identity
    ):
        raise ValueError("runtime_owner_retirement_target_parent_changed")
    try:
        _require_exact_plain_directory(
            target.parent,
            expected_parent_identity=runtime_root_identity,
            expected_identity=custom_config_identity,
            error="runtime_owner_retirement_target_parent_changed",
        )
    except (OSError, ValueError) as error:
        raise ValueError(
            "runtime_owner_retirement_target_parent_changed"
        ) from error
    return target, parent_identity


def _owner_retirement_retire_root_action(
    *,
    recovery: Mapping[str, Any],
    runtime_root: Path,
    layout_identities: Mapping[str, PathIdentity],
    terminal_retirement: Mapping[str, Any] | None = None,
) -> (
    RuntimeApplyRecoveryPhysicalPostcondition
    | TerminalResolutionPhysicalPostcondition
):
    owner = recovery.get("owner_retirement")
    if not isinstance(owner, Mapping) or owner.get("stage") != "CLEANING":
        raise ValueError("runtime_owner_retirement_root_invalid")
    planned_completed_size, planned_completed_sha256 = (
        _owner_retirement_completed_commitment(owner)
    )
    target, parent_identity = _require_owner_retirement_target_parent_binding(
        recovery=recovery,
        owner=owner,
        runtime_root=runtime_root,
        layout_identities=layout_identities,
    )
    tombstone, prepared_raw = _owner_retirement_prepared_tombstone(
        owner=owner,
        runtime_root=runtime_root,
        owner_retirements_parent_identity=layout_identities["owner_retirements"],
    )
    if int(owner["cleanup_cursor"]) != int(tombstone["cleanup_entry_count"]):
        raise ValueError("runtime_owner_retirement_root_invalid")
    target_identity = tuple(owner["retired_target_identity"])
    preexisting = path_lexists(target)
    if preexisting:
        try:
            _require_exact_plain_directory(
                target,
                expected_parent_identity=parent_identity,
                expected_identity=target_identity,
                error="runtime_owner_retirement_target_changed",
            )
        except (OSError, ValueError) as error:
            raise ValueError("runtime_owner_retirement_target_changed") from error
        secure_rmdir_verified(
            target,
            expected_identity=target_identity,
            expected_parent_identity=parent_identity,
        )
    _require_owner_retirement_target_parent_binding(
        recovery=recovery,
        owner=owner,
        runtime_root=runtime_root,
        layout_identities=layout_identities,
    )
    final_tombstone, final_prepared_raw = (
        _owner_retirement_prepared_tombstone(
            owner=owner,
            runtime_root=runtime_root,
            owner_retirements_parent_identity=layout_identities[
                "owner_retirements"
            ],
        )
    )
    if final_tombstone != tombstone or final_prepared_raw != prepared_raw:
        raise ValueError("runtime_owner_retirement_authority_changed")
    prepared_raw = final_prepared_raw
    journal_path = Path(str(owner["initial_owner_journal_path"]))
    _owner_retirement_read_bound_file(
        journal_path,
        parent_identity=layout_identities["transactions"],
        identity=tuple(owner["current_owner_journal_identity"]),
        sha256=str(owner["current_owner_journal_sha256"]),
    )
    next_external = _owner_retirement_external_action_from_commitment(
        recovery=recovery,
        action_kind="commit_owner_retirement_completed",
        final_path=Path(str(owner["tombstone_path"])),
        parent_identity=layout_identities["owner_retirements"],
        predecessor_identity=tuple(owner["tombstone_identity"]),
        predecessor_raw=prepared_raw,
        planned_successor_size=planned_completed_size,
        planned_successor_sha256=planned_completed_sha256,
    )
    postcondition = {
        "target_path": owner["retired_target_path"],
        "historical_target_identity": owner["retired_target_identity"],
        "target_parent_identity": owner["retired_target_parent_identity"],
        "prepared_tombstone_path": owner["tombstone_path"],
        "prepared_tombstone_identity": owner["tombstone_identity"],
        "prepared_tombstone_sha256": owner["tombstone_sha256"],
        "final_owner_journal_path": owner["initial_owner_journal_path"],
        "final_owner_journal_identity": owner["current_owner_journal_identity"],
        "final_owner_journal_sha256": owner["current_owner_journal_sha256"],
        "cleanup_manifest_sha256": owner["cleanup_manifest_sha256"],
        "cleanup_entry_count": owner["cleanup_entry_count"],
        "planned_completed_tombstone_size": owner[
            "planned_completed_tombstone_size"
        ],
        "planned_completed_tombstone_sha256": owner[
            "planned_completed_tombstone_sha256"
        ],
        "disposition": "removed" if preexisting else "already_absent",
    }
    result = _owner_retirement_owner_external_postcondition(
        recovery=recovery,
        action="retire_owner_target_root",
        owner=owner,
        next_owner=_seal_owner_retirement_document(
            owner, changes={"stage": "TARGET_RETIRED"}
        ),
        next_action="materialize_file_action_staging",
        next_external=next_external,
        evidence={"owner_root_postcondition": postcondition},
        terminal_retirement=terminal_retirement,
    )
    final_tombstone, final_prepared_raw = _owner_retirement_prepared_tombstone(
        owner=owner,
        runtime_root=runtime_root,
        owner_retirements_parent_identity=layout_identities["owner_retirements"],
    )
    if final_tombstone != tombstone or final_prepared_raw != prepared_raw:
        raise ValueError("runtime_owner_retirement_authority_changed")
    _owner_retirement_read_bound_file(
        journal_path,
        parent_identity=layout_identities["transactions"],
        identity=tuple(owner["current_owner_journal_identity"]),
        sha256=str(owner["current_owner_journal_sha256"]),
    )
    return result


def _owner_retirement_commit_completed_action(
    *,
    recovery: Mapping[str, Any],
    runtime_root: Path,
    layout_identities: Mapping[str, PathIdentity],
    terminal_retirement: Mapping[str, Any] | None = None,
) -> (
    RuntimeApplyRecoveryPhysicalPostcondition
    | TerminalResolutionPhysicalPostcondition
):
    owner = recovery.get("owner_retirement")
    external = recovery.get("external_file_action")
    if (
        not isinstance(owner, Mapping)
        or not isinstance(external, Mapping)
        or owner.get("stage") != "TARGET_RETIRED"
        or external.get("action_kind") != "commit_owner_retirement_completed"
    ):
        raise ValueError("runtime_owner_retirement_completed_commit_invalid")
    visible_payload = _owner_retirement_visible_bound_commit_payload(
        external=external,
        expected_action="commit_owner_retirement_completed",
    )
    payload = visible_payload
    if payload is None:
        payload = _owner_retirement_completed_bytes(
            owner=owner,
            runtime_root=runtime_root,
            journal_identity=tuple(
                owner["current_owner_journal_identity"]
            ),
            journal_sha256=str(owner["current_owner_journal_sha256"]),
            owner_retirements_parent_identity=layout_identities[
                "owner_retirements"
            ],
        )
    else:
        _validate_owner_retirement_visible_completed_commit(
            owner=owner,
            raw=payload,
            runtime_root=runtime_root,
        )
    if (
        len(payload) != owner.get("planned_completed_tombstone_size")
        or _owner_retirement_digest(payload)
        != owner.get("planned_completed_tombstone_sha256")
    ):
        raise ValueError("runtime_owner_retirement_completed_commitment_changed")
    identity, raw = _owner_retirement_commit_external(
        external=external, payload=payload
    )
    next_owner = _seal_owner_retirement_document(
        owner,
        changes={
            "stage": "COMPLETED",
            "tombstone_identity": identity,
            "tombstone_sha256": _owner_retirement_digest(raw),
        },
    )
    return _owner_retirement_owner_external_postcondition(
        recovery=recovery,
        action="commit_owner_retirement_completed",
        owner=owner,
        next_owner=next_owner,
        next_action="retire_old_owner_journal",
        next_external=None,
        terminal_retirement=terminal_retirement,
    )


def _owner_retirement_retire_old_journal_action(
    *,
    recovery: Mapping[str, Any],
    runtime_root: Path,
    layout_identities: Mapping[str, PathIdentity],
    terminal_retirement: Mapping[str, Any] | None = None,
) -> (
    RuntimeApplyRecoveryPhysicalPostcondition
    | TerminalResolutionPhysicalPostcondition
):
    owner = recovery.get("owner_retirement")
    if not isinstance(owner, Mapping) or owner.get("stage") != "COMPLETED":
        raise ValueError("runtime_owner_retirement_old_journal_invalid")
    completed_path = Path(str(owner["tombstone_path"]))
    completed_raw = _owner_retirement_read_bound_file(
        completed_path,
        parent_identity=layout_identities["owner_retirements"],
        identity=tuple(owner["tombstone_identity"]),
        sha256=str(owner["tombstone_sha256"]),
    )
    completed = _parse_owner_retirement_tombstone_bytes(
        completed_raw, runtime_root=runtime_root
    )
    if completed.get("state") != "COMPLETED":
        raise ValueError("runtime_owner_retirement_completed_tombstone_invalid")
    journal_path = Path(str(owner["initial_owner_journal_path"]))
    preexisting = path_lexists(journal_path)
    if preexisting:
        raw, identity = _read_exact_runtime_external_file(
            journal_path,
            expected_parent_identity=layout_identities["transactions"],
            maximum_size=RUNTIME_OWNER_RETIREMENT_MAX_BYTES,
        )
        if (
            identity != tuple(owner["current_owner_journal_identity"])
            or _owner_retirement_digest(raw)
            != owner["current_owner_journal_sha256"]
        ):
            raise ValueError("runtime_owner_retirement_old_journal_changed")
        secure_unlink_verified(
            journal_path,
            expected_identity=identity,
            expected_parent_identity=layout_identities["transactions"],
            expected_size=len(raw),
            expected_sha256=_owner_retirement_digest(raw).removeprefix(
                "sha256:"
            ),
        )
    postcondition = {
        "journal_path": owner["initial_owner_journal_path"],
        "historical_journal_identity": owner["current_owner_journal_identity"],
        "historical_journal_sha256": owner["current_owner_journal_sha256"],
        "completed_tombstone_path": owner["tombstone_path"],
        "completed_tombstone_identity": owner["tombstone_identity"],
        "completed_tombstone_sha256": owner["tombstone_sha256"],
        "successor_owner_journal_path": owner["successor_owner_journal_path"],
        "successor_owner_journal_identity": owner["successor_owner_journal_identity"],
        "successor_owner_journal_sha256": owner["successor_owner_journal_sha256"],
        "disposition": "removed" if preexisting else "already_absent",
    }
    return _owner_retirement_owner_external_postcondition(
        recovery=recovery,
        action="retire_old_owner_journal",
        owner=owner,
        next_owner=_seal_owner_retirement_document(
            owner,
            changes={"stage": "OWNER_RETIRED", "old_owner_journal_retired": True},
        ),
        next_action="observe_owner_retirement_completed",
        next_external=None,
        evidence={"owner_old_journal_postcondition": postcondition},
        terminal_retirement=terminal_retirement,
    )


def _owner_retirement_observe_completed_action(
    *,
    recovery: Mapping[str, Any],
    runtime_root: Path,
    layout_identities: Mapping[str, PathIdentity],
    terminal_retirement: Mapping[str, Any] | None = None,
    observation_status: str | None = None,
) -> (
    RuntimeApplyRecoveryPhysicalPostcondition
    | TerminalResolutionPhysicalPostcondition
):
    owner = recovery.get("owner_retirement")
    if not isinstance(owner, Mapping) or owner.get("stage") != "OWNER_RETIRED":
        raise ValueError("runtime_owner_retirement_observation_invalid")
    completed_path = Path(str(owner["tombstone_path"]))
    completed_raw = _owner_retirement_read_bound_file(
        completed_path,
        parent_identity=layout_identities["owner_retirements"],
        identity=tuple(owner["tombstone_identity"]),
        sha256=str(owner["tombstone_sha256"]),
    )
    completed = _parse_owner_retirement_tombstone_bytes(
        completed_raw, runtime_root=runtime_root
    )
    successor_path = Path(str(owner["successor_owner_journal_path"]))
    _owner_retirement_read_bound_file(
        successor_path,
        parent_identity=layout_identities["transactions"],
        identity=tuple(owner["successor_owner_journal_identity"]),
        sha256=str(owner["successor_owner_journal_sha256"]),
    )
    if (
        completed.get("state") != "COMPLETED"
        or path_lexists(Path(str(owner["initial_owner_journal_path"])))
    ):
        raise ValueError("runtime_owner_retirement_observation_invalid")
    if terminal_retirement is not None:
        if observation_status != "committed":
            raise ValueError(
                "runtime_terminal_owner_observation_not_committed"
            )
    elif observation_status is not None:
        raise ValueError(
            "runtime_owner_retirement_observation_status_invalid"
        )
    return _owner_retirement_owner_external_postcondition(
        recovery=recovery,
        action="observe_owner_retirement_completed",
        owner=owner,
        next_owner=_seal_owner_retirement_document(owner),
        next_action="observe_committed",
        next_external=None,
        terminal_retirement=terminal_retirement,
        terminal_disposition=(
            "COMMITTED" if terminal_retirement is not None else None
        ),
    )


def _execute_terminal_owner_retirement_action(
    *,
    action: str,
    recovery: Mapping[str, Any],
    terminal_retirement: Mapping[str, Any],
    runtime_root: Path,
    layout_identities: Mapping[str, PathIdentity],
    observation_status: str,
) -> TerminalResolutionPhysicalPostcondition:
    if action == "retire_unbound_file_action_staging":
        result = _retire_unbound_recovery_external_file_action(
            recovery=recovery,
            terminal_retirement=terminal_retirement,
        )
    elif action == "materialize_file_action_staging":
        result = _owner_retirement_materialize_action(
            recovery=recovery,
            runtime_root=runtime_root,
            layout_identities=layout_identities,
            terminal_retirement=terminal_retirement,
        )
    elif action == "commit_owner_retirement_prepared":
        result = _owner_retirement_commit_prepared_action(
            recovery=recovery,
            runtime_root=runtime_root,
            layout_identities=layout_identities,
            terminal_retirement=terminal_retirement,
        )
    elif action == "initialize_owner_cleanup_journal":
        result = _owner_retirement_initialize_journal_action(
            recovery=recovery,
            runtime_root=runtime_root,
            layout_identities=layout_identities,
            terminal_retirement=terminal_retirement,
        )
    elif action == "delete_owner_cleanup_entry":
        result = _owner_retirement_delete_entry_action(
            recovery=recovery,
            runtime_root=runtime_root,
            layout_identities=layout_identities,
            terminal_retirement=terminal_retirement,
        )
    elif action == "advance_owner_cleanup_journal":
        result = _owner_retirement_advance_journal_action(
            recovery=recovery,
            runtime_root=runtime_root,
            layout_identities=layout_identities,
            terminal_retirement=terminal_retirement,
        )
    elif action == "retire_owner_target_root":
        result = _owner_retirement_retire_root_action(
            recovery=recovery,
            runtime_root=runtime_root,
            layout_identities=layout_identities,
            terminal_retirement=terminal_retirement,
        )
    elif action == "commit_owner_retirement_completed":
        result = _owner_retirement_commit_completed_action(
            recovery=recovery,
            runtime_root=runtime_root,
            layout_identities=layout_identities,
            terminal_retirement=terminal_retirement,
        )
    elif action == "retire_old_owner_journal":
        result = _owner_retirement_retire_old_journal_action(
            recovery=recovery,
            runtime_root=runtime_root,
            layout_identities=layout_identities,
            terminal_retirement=terminal_retirement,
        )
    elif action == "observe_owner_retirement_completed":
        result = _owner_retirement_observe_completed_action(
            recovery=recovery,
            runtime_root=runtime_root,
            layout_identities=layout_identities,
            terminal_retirement=terminal_retirement,
            observation_status=observation_status,
        )
    else:
        raise ValueError("runtime_terminal_owner_action_not_implemented")
    if not isinstance(result, TerminalResolutionPhysicalPostcondition):
        raise RuntimeError("runtime_terminal_owner_postcondition_invalid")
    return result


def _runtime_attempt_self_digest(payload: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(
        _canonical_runtime_attempt_json(payload)
    ).hexdigest()


def _retention_identity_from_json(value: object) -> PathIdentity | None:
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(type(part) is not int or part < 0 for part in value)
    ):
        raise ValueError("runtime_attempt_retention_identity_invalid")
    return value[0], value[1], value[2]


def _retention_path_from_json(value: object) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError("runtime_attempt_retention_path_invalid")
    return Path(value)


def _validate_runtime_attempt_retention_record(
    record: RuntimeAttemptRetentionRecord,
    *,
    runtime_root: Path,
    validate_content_digest: bool,
) -> None:
    root = Path(runtime_root)
    if not root.is_absolute() or root.resolve(strict=False) != root:
        raise ValueError("runtime_attempt_retention_runtime_root_invalid")
    if (
        type(record.schema_version) is not int
        or record.schema_version != RUNTIME_ATTEMPT_RETENTION_SCHEMA_VERSION
        or record.record_kind != RUNTIME_ATTEMPT_RETENTION_KIND
        or record.state not in _ATTEMPT_RETENTION_STATES
        or not isinstance(record.apply_attempt_id, str)
        or _ATTEMPT_ID.fullmatch(record.apply_attempt_id) is None
        or not isinstance(record.retention_owner_run_id, str)
        or _ATTEMPT_ID.fullmatch(record.retention_owner_run_id) is None
    ):
        raise ValueError("runtime_attempt_retention_header_invalid")

    path_fields = (
        record.journal_path,
        record.target_path,
        record.target_owner_journal_path,
        record.planned_journal_path,
        record.candidate_path,
    )
    if any(
        path is not None
        and (
            not path.is_absolute()
            or path.resolve(strict=False) != path
        )
        for path in path_fields
    ):
        raise ValueError("runtime_attempt_retention_path_invalid")
    identity_fields = (
        record.journal_identity,
        record.target_identity,
        record.target_owner_journal_identity,
        record.candidate_parent_identity,
        record.candidate_identity,
    )
    if any(identity is not None and not _valid_path_identity(identity) for identity in identity_fields):
        raise ValueError("runtime_attempt_retention_identity_invalid")
    digest_fields = (
        record.journal_sha256,
        record.package_root_sha256,
        record.target_owner_journal_sha256,
        record.planned_journal_sha256,
    )
    if any(
        digest is not None
        and (
            not isinstance(digest, str)
            or _PREFIXED_SHA256.fullmatch(digest) is None
        )
        for digest in digest_fields
    ):
        raise ValueError("runtime_attempt_retention_digest_invalid")
    if record.owns_target is not None and type(record.owns_target) is not bool:
        raise ValueError("runtime_attempt_retention_ownership_invalid")
    if record.planned_journal_size is not None and (
        type(record.planned_journal_size) is not int
        or not 0 < record.planned_journal_size <= MAX_RUNTIME_TRANSACTION_BYTES
    ):
        raise ValueError("runtime_attempt_retention_size_invalid")

    attempt_journal = runtime_transaction_journal_path(
        root,
        record.apply_attempt_id,
    )
    candidate = root / ".hsconfig" / "staging" / record.apply_attempt_id
    if record.journal_path is not None and record.journal_path != attempt_journal:
        raise ValueError("runtime_attempt_retention_journal_path_invalid")
    if (
        record.planned_journal_path is not None
        and record.planned_journal_path != attempt_journal
    ):
        raise ValueError("runtime_attempt_retention_planned_path_invalid")
    if record.candidate_path is not None and record.candidate_path != candidate:
        raise ValueError("runtime_attempt_retention_candidate_path_invalid")
    if record.target_path is not None and (
        record.target_path.parent != root / "CustomConfig"
        or not _valid_component(record.target_path.name)
    ):
        raise ValueError("runtime_attempt_retention_target_path_invalid")
    if record.target_owner_journal_path is not None:
        owner_id = record.target_owner_journal_path.stem
        if (
            _ATTEMPT_ID.fullmatch(owner_id) is None
            or record.target_owner_journal_path
            != runtime_transaction_journal_path(root, owner_id)
        ):
            raise ValueError("runtime_attempt_retention_owner_path_invalid")

    journal_triplet = (
        record.journal_path,
        record.journal_identity,
        record.journal_sha256,
    )
    target_triplet = (
        record.target_path,
        record.target_identity,
        record.owns_target,
    )
    owner_triplet = (
        record.target_owner_journal_path,
        record.target_owner_journal_identity,
        record.target_owner_journal_sha256,
    )
    planned_triplet = (
        record.planned_journal_path,
        record.planned_journal_size,
        record.planned_journal_sha256,
    )
    candidate_triplet = (
        record.candidate_path,
        record.candidate_parent_identity,
        record.candidate_identity,
    )

    def all_null(values: tuple[object, ...]) -> bool:
        return all(value is None for value in values)

    def all_bound(values: tuple[object, ...]) -> bool:
        return all(value is not None for value in values)

    invalid_state = False
    if record.state == "ACTIVE":
        invalid_state = not all_null(
            (
                *journal_triplet,
                record.package_root_sha256,
                *target_triplet,
                *owner_triplet,
                *planned_triplet,
                *candidate_triplet,
            )
        )
    elif record.state in {"CANDIDATE_PLANNED", "CANDIDATE_BOUND"}:
        expected_journal_bound = record.state == "CANDIDATE_BOUND"
        invalid_state = (
            (not all_bound(journal_triplet) if expected_journal_bound else not all_null(journal_triplet))
            or record.package_root_sha256 is None
            or not all_null(target_triplet[:2])
            or record.owns_target is not False
            or not all_null(owner_triplet)
            or not all_bound(planned_triplet)
            or record.candidate_path is None
            or record.candidate_parent_identity is None
            or (
                (record.candidate_identity is None)
                if expected_journal_bound
                else (record.candidate_identity is not None)
            )
        )
    elif record.state in {"PRIOR_OWNER_PLANNED", "PRIOR_OWNER_BOUND"}:
        expected_journal_bound = record.state == "PRIOR_OWNER_BOUND"
        invalid_state = (
            (not all_bound(journal_triplet) if expected_journal_bound else not all_null(journal_triplet))
            or record.package_root_sha256 is None
            or record.target_path is None
            or record.target_identity is None
            or record.owns_target is not False
            or not all_bound(owner_triplet)
            or not all_bound(planned_triplet)
            or not all_null(candidate_triplet)
        )
    else:
        invalid_state = (
            not all_bound(journal_triplet)
            or record.package_root_sha256 is None
            or record.target_path is None
            or record.target_identity is None
            or type(record.owns_target) is not bool
            or not all_bound(owner_triplet)
            or not all_bound(planned_triplet)
            or not (
                all_null(candidate_triplet)
                or all_bound(candidate_triplet)
            )
        )
    if invalid_state:
        raise ValueError("runtime_attempt_retention_state_invalid")

    if validate_content_digest:
        if (
            not isinstance(record.content_sha256, str)
            or _PREFIXED_SHA256.fullmatch(record.content_sha256) is None
            or record.content_sha256
            != _runtime_attempt_self_digest(
                _runtime_attempt_retention_payload(record, include_digest=False)
            )
        ):
            raise ValueError("runtime_attempt_retention_content_sha256_invalid")


def _runtime_attempt_unique_object(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("runtime_attempt_retention_duplicate_key")
        result[key] = value
    return result


def _reject_runtime_attempt_constant(value: str) -> None:
    raise ValueError(f"runtime_attempt_retention_constant_invalid:{value}")


def _runtime_attempt_retention_from_raw(
    raw: bytes,
    *,
    runtime_root: Path,
) -> RuntimeAttemptRetentionRecord:
    try:
        if not raw or len(raw) > RUNTIME_ATTEMPT_RETENTION_MAX_BYTES:
            raise ValueError("bounds")
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_runtime_attempt_unique_object,
            parse_constant=_reject_runtime_attempt_constant,
        )
        if not isinstance(value, dict) or set(value) != RUNTIME_ATTEMPT_RETENTION_FIELDS:
            raise ValueError("schema")
        record = RuntimeAttemptRetentionRecord(
            schema_version=value["schema_version"],
            record_kind=value["record_kind"],
            state=value["state"],
            apply_attempt_id=value["apply_attempt_id"],
            retention_owner_run_id=value["retention_owner_run_id"],
            journal_path=_retention_path_from_json(value["journal_path"]),
            journal_identity=_retention_identity_from_json(value["journal_identity"]),
            journal_sha256=value["journal_sha256"],
            package_root_sha256=value["package_root_sha256"],
            target_path=_retention_path_from_json(value["target_path"]),
            target_identity=_retention_identity_from_json(value["target_identity"]),
            owns_target=value["owns_target"],
            target_owner_journal_path=_retention_path_from_json(
                value["target_owner_journal_path"]
            ),
            target_owner_journal_identity=_retention_identity_from_json(
                value["target_owner_journal_identity"]
            ),
            target_owner_journal_sha256=value["target_owner_journal_sha256"],
            planned_journal_path=_retention_path_from_json(
                value["planned_journal_path"]
            ),
            planned_journal_size=value["planned_journal_size"],
            planned_journal_sha256=value["planned_journal_sha256"],
            candidate_path=_retention_path_from_json(value["candidate_path"]),
            candidate_parent_identity=_retention_identity_from_json(
                value["candidate_parent_identity"]
            ),
            candidate_identity=_retention_identity_from_json(
                value["candidate_identity"]
            ),
            content_sha256=value["content_sha256"],
        )
        _validate_runtime_attempt_retention_record(
            record,
            runtime_root=runtime_root,
            validate_content_digest=True,
        )
        if raw != _canonical_runtime_attempt_json(
            _runtime_attempt_retention_payload(record, include_digest=True)
        ):
            raise ValueError("noncanonical")
        return record
    except Exception as error:
        raise ValueError("runtime_attempt_retention_invalid") from error


@dataclass(frozen=True, slots=True, init=False)
class RuntimeApplyLockToken:
    """Opaque process-local capability for one held Runtime apply lock."""

    _nonce: object
    _thread_id: int

    def __init__(self, authority: object | None = None) -> None:
        if authority is not _RUNTIME_APPLY_TOKEN_AUTHORITY:
            raise TypeError("runtime_apply_lock_token_not_constructible")
        object.__setattr__(self, "_nonce", object())
        object.__setattr__(self, "_thread_id", get_ident())

    def __copy__(self) -> RuntimeApplyLockToken:
        raise TypeError("runtime_apply_lock_token_not_copyable")

    def __deepcopy__(self, memo: dict[int, object]) -> RuntimeApplyLockToken:
        del memo
        raise TypeError("runtime_apply_lock_token_not_copyable")

    def __reduce__(self) -> object:
        raise TypeError("runtime_apply_lock_token_not_serializable")


@dataclass(frozen=True, slots=True)
class RuntimeApplyLease:
    runtime_root: Path
    runtime_root_identity: PathIdentity
    apply_lock_path: Path
    apply_lock_identity: PathIdentity
    lock_token: RuntimeApplyLockToken


@dataclass(frozen=True, slots=True, init=False)
class ControllerApplyLeasePairToken:
    """Opaque capability for one active controller-owned lease pair."""

    _nonce: object
    _thread_id: int

    def __init__(self, authority: object | None = None) -> None:
        if authority is not _CONTROLLER_PAIR_TOKEN_AUTHORITY:
            raise TypeError("controller_apply_pair_token_not_constructible")
        object.__setattr__(self, "_nonce", object())
        object.__setattr__(self, "_thread_id", get_ident())

    def __copy__(self) -> ControllerApplyLeasePairToken:
        raise TypeError("controller_apply_pair_token_not_copyable")

    def __deepcopy__(self, memo: dict[int, object]) -> ControllerApplyLeasePairToken:
        del memo
        raise TypeError("controller_apply_pair_token_not_copyable")

    def __reduce__(self) -> object:
        raise TypeError("controller_apply_pair_token_not_serializable")


@dataclass(frozen=True, slots=True)
class ControllerApplyLeasePair:
    package_lease: PackageInputLease
    runtime_lease: RuntimeApplyLease
    pair_token: ControllerApplyLeasePairToken


@dataclass(frozen=True, slots=True)
class _ControllerApplyLeasePairBinding:
    token: ControllerApplyLeasePairToken
    pair: ControllerApplyLeasePair
    thread_id: int
    session_lease: LiveStartSessionLease
    expected_session: LiveStartSession
    profile_lease: OperatorProfileLease
    output_operation_lease: OutputOperationAdmissionLease
    output_operation_admission: OutputOperationAdmissionEvidence
    package_lease: PackageInputLease
    runtime_lease: RuntimeApplyLease
    session_token: object
    profile_token: object
    output_operation_token: object
    package_token: object
    runtime_token: object
    session_root: Path
    session_root_identity: PathIdentity
    run_id: str
    deck_name: str
    deck_code_sha256: str
    preview_requested: bool
    candidate_revision: int
    revisions_used: int
    input_snapshot_manifest_sha256: str
    entry_session_identity: PathIdentity
    entry_session_sha256: str
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence | None
    entry_mode: Literal[
        "PRE_HANDOFF_READY",
        "POST_HANDOFF_RELEASE_ONLY",
        "POST_HANDOFF_READY",
    ]
    reentry_output_disposition: Literal[
        "exact_old",
        "absent",
        "valid_foreign",
    ]


def _identity_field_matches(
    value: object,
    expected: PathIdentity | None,
) -> bool:
    if expected is None:
        return value is None
    if not isinstance(value, (list, tuple)):
        return False
    return tuple(value) == expected


def _validate_historical_output_operation_binding(
    *,
    persisted: LiveStartSession,
    evidence: OutputOperationAdmissionEvidence,
    profile_lease: OperatorProfileLease,
) -> None:
    operation = persisted.output_operation_admission_binding
    if not isinstance(operation, Mapping) or evidence.state != "ACTIVE":
        raise ValueError("controller_apply_pair_output_operation_invalid")
    scalar_fields: tuple[tuple[str, object], ...] = (
        ("admission_path", str(evidence.admission_path)),
        ("admission_size", evidence.admission_size),
        ("run_id", evidence.run_id),
        ("session_root", str(evidence.session_root)),
        ("expected_session_sha256", evidence.expected_session_sha256),
        ("operator_profile_path", str(evidence.operator_profile_path)),
        ("operator_profile_sha256", evidence.operator_profile_sha256),
        ("output_base_root", str(evidence.output_base_root)),
        ("output_child_path", str(evidence.output_child_path)),
        (
            "output_child_predecessor_state",
            evidence.output_child_predecessor_state,
        ),
        (
            "output_bootstrap_lock_path",
            str(evidence.output_bootstrap_lock_path),
        ),
        ("output_claim_path", str(evidence.output_claim_path)),
    )
    identity_fields: tuple[tuple[str, PathIdentity | None], ...] = (
        ("admission_parent_identity", evidence.admission_parent_identity),
        ("admission_identity", evidence.admission_identity),
        ("session_root_identity", evidence.session_root_identity),
        (
            "operator_profile_parent_identity",
            evidence.operator_profile_parent_identity,
        ),
        ("operator_profile_identity", evidence.operator_profile_identity),
        ("state_root_identity", evidence.state_root_identity),
        ("output_base_root_identity", evidence.output_base_root_identity),
        (
            "output_child_predecessor_identity",
            evidence.output_child_predecessor_identity,
        ),
        (
            "output_bootstrap_lock_identity",
            evidence.output_bootstrap_lock_identity,
        ),
    )
    if any(operation.get(name) != expected for name, expected in scalar_fields) or any(
        not _identity_field_matches(operation.get(name), expected)
        for name, expected in identity_fields
    ):
        raise ValueError("controller_apply_pair_output_operation_invalid")
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
    rebuilt_document = json.loads(rebuilt)
    if (
        len(rebuilt) != evidence.admission_size
        or "sha256:" + hashlib.sha256(rebuilt).hexdigest()
        != operation.get("admission_sha256")
        or rebuilt_document.get("content_sha256") != evidence.admission_sha256
    ):
        raise ValueError("controller_apply_pair_output_operation_invalid")


def _validate_post_handoff_runtime_admission(
    *,
    persisted: LiveStartSession,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    profile_lease: OperatorProfileLease,
    output_operation_admission: OutputOperationAdmissionEvidence,
    package_lease: PackageInputLease,
    runtime_root: Path,
    expected_root_identity: PathIdentity,
) -> None:
    operation = persisted.output_operation_admission_binding
    admission = persisted.runtime_admission_binding
    child = persisted.output_child_binding
    publication = persisted.publication_binding
    if not all(
        isinstance(value, Mapping)
        for value in (operation, admission, child, publication)
    ):
        raise ValueError("controller_apply_pair_runtime_admission_invalid")
    assert isinstance(operation, Mapping)
    assert isinstance(admission, Mapping)
    assert isinstance(child, Mapping)
    assert isinstance(publication, Mapping)
    if (
        persisted.phase.value
        not in {"APPLY_STARTED", "APPLY_COMMITTED", "RUNTIME_MATCHED"}
        or persisted.apply_invocation_sha256 is None
        or operation.get("state") != "RUNTIME_HANDOFF_RELEASE_AUTHORIZED"
        or operation.get("release_handoff_kind") != "runtime_admission"
    ):
        raise ValueError("controller_apply_pair_release_handoff_invalid")
    handoff_fields: tuple[tuple[str, object], ...] = (
        ("handoff_runtime_admission_path", str(runtime_admission.admission_path)),
        (
            "handoff_runtime_admission_parent_identity",
            runtime_admission.admission_parent_identity,
        ),
        (
            "handoff_runtime_admission_identity",
            runtime_admission.admission_identity,
        ),
        (
            "handoff_runtime_admission_sha256",
            runtime_admission.admission_sha256,
        ),
    )
    for name, expected in handoff_fields:
        current = operation.get(name)
        if name.endswith("identity"):
            if not _identity_field_matches(current, expected):
                raise ValueError("controller_apply_pair_release_handoff_invalid")
        elif current != expected:
            raise ValueError("controller_apply_pair_release_handoff_invalid")
    runtime_binding_fields: tuple[tuple[str, object], ...] = (
        ("admission_path", str(runtime_admission.admission_path)),
        (
            "admission_parent_identity",
            runtime_admission.admission_parent_identity,
        ),
        ("admission_identity", runtime_admission.admission_identity),
        ("admission_sha256", runtime_admission.admission_sha256),
        (
            "output_operation_admission_path",
            str(runtime_admission.output_operation_admission_path),
        ),
        (
            "output_operation_admission_identity",
            runtime_admission.output_operation_admission_identity,
        ),
        (
            "output_operation_admission_sha256",
            runtime_admission.output_operation_admission_sha256,
        ),
        (
            "output_child_binding_sha256",
            runtime_admission.output_child_binding_sha256,
        ),
        ("output_child_path", str(runtime_admission.output_root)),
        ("output_child_identity", runtime_admission.output_root_identity),
        ("publication_revision", runtime_admission.publication_revision),
        (
            "publication_content_root_sha256",
            runtime_admission.publication_content_root_sha256,
        ),
    )
    for name, expected in runtime_binding_fields:
        current = admission.get(name)
        if name.endswith("identity"):
            if not _identity_field_matches(current, expected):
                raise ValueError("controller_apply_pair_runtime_admission_invalid")
        elif current != expected:
            raise ValueError("controller_apply_pair_runtime_admission_invalid")
    if (
        runtime_admission.run_id != persisted.run_id
        or runtime_admission.retention_owner_run_id != persisted.run_id
        or runtime_admission.session_root
        != output_operation_admission.session_root
        or runtime_admission.session_root_identity
        != output_operation_admission.session_root_identity
        or runtime_admission.operator_profile_sha256
        != profile_lease.profile.content_sha256
        or runtime_admission.state_root_identity
        != output_operation_admission.state_root_identity
        or runtime_admission.runtime_root != runtime_root
        or runtime_admission.runtime_root_identity != expected_root_identity
        or runtime_admission.output_base_root
        != profile_lease.profile.output_base_root
        or runtime_admission.output_base_root_identity
        != profile_lease.profile.output_base_root_identity
        or runtime_admission.output_root != package_lease.output_root
        or runtime_admission.output_root_identity != path_identity(
            package_lease.output_root
        )
        or runtime_admission.output_operation_admission_path
        != output_operation_admission.admission_path
        or runtime_admission.output_operation_admission_identity
        != output_operation_admission.admission_identity
        or runtime_admission.output_operation_admission_sha256
        != operation.get("admission_sha256")
        or runtime_admission.output_child_binding_sha256
        != child.get("content_sha256")
        or runtime_admission.publication_revision != publication.get("revision")
        or runtime_admission.publication_content_root_sha256
        != publication.get("content_root_sha256")
        or package_lease.content_root_sha256 is None
        or runtime_admission.package_root_sha256
        != "sha256:" + package_lease.content_root_sha256
        or runtime_admission.apply_invocation_sha256
        != persisted.apply_invocation_sha256
        or runtime_admission.retention_fence_path
        != (
            runtime_root
            / ".hsconfig"
            / "attempt-retention"
            / f"{runtime_admission.apply_attempt_id}.json"
        )
    ):
        raise ValueError("controller_apply_pair_runtime_admission_invalid")


def _validate_pre_handoff_runtime_admission(
    *,
    persisted: LiveStartSession,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    profile_lease: OperatorProfileLease,
    output_operation_admission: OutputOperationAdmissionEvidence,
    package_lease: PackageInputLease,
    runtime_root: Path,
    expected_root_identity: PathIdentity,
) -> None:
    """Bind the exact committed admission to its still-active session intent."""

    pending = persisted.pending_transition
    operation = persisted.output_operation_admission_binding
    child = persisted.output_child_binding
    publication = persisted.publication_binding
    if not all(
        isinstance(value, Mapping)
        for value in (pending, operation, child, publication)
    ):
        raise ValueError("controller_apply_pair_runtime_admission_invalid")
    assert isinstance(pending, Mapping)
    assert isinstance(operation, Mapping)
    assert isinstance(child, Mapping)
    assert isinstance(publication, Mapping)
    pending_stage = pending.get("stage")
    if pending_stage == "STAGING_BOUND":
        _validate_bound_runtime_admission_commit_reentry(
            pending=pending,
            runtime_admission=runtime_admission,
        )
        expected_admission_identity = tuple(
            pending.get("runtime_admission_staging_identity", ())
        )
        expected_admission_sha256 = pending.get(
            "runtime_admission_staging_sha256"
        )
    else:
        expected_admission_identity = tuple(
            pending.get("runtime_admission_identity", ())
        )
        expected_admission_sha256 = pending.get(
            "runtime_admission_sha256"
        )
    if (
        persisted.phase.value != "PUBLICATION_COMMITTED"
        or operation.get("state") != "ACTIVE"
        or pending.get("operation") != "install_apply_invocation"
        or pending_stage not in {"STAGING_BOUND", "PRIMARY_APPLIED"}
        or runtime_admission.admission_path
        != Path(str(pending.get("runtime_admission_path")))
        or runtime_admission.admission_parent_identity
        != tuple(pending.get("runtime_admission_parent_identity", ()))
        or runtime_admission.admission_identity
        != expected_admission_identity
        or runtime_admission.admission_sha256
        != expected_admission_sha256
        or runtime_admission.admission_sha256
        != pending.get("runtime_admission_document_sha256")
        or runtime_admission.run_id != persisted.run_id
        or runtime_admission.apply_attempt_id != pending.get("apply_attempt_id")
        or runtime_admission.retention_owner_run_id != persisted.run_id
        or runtime_admission.session_root
        != output_operation_admission.session_root
        or runtime_admission.session_root_identity
        != output_operation_admission.session_root_identity
        or runtime_admission.operator_profile_sha256
        != profile_lease.profile.content_sha256
        or runtime_admission.state_root_identity
        != output_operation_admission.state_root_identity
        or runtime_admission.runtime_root != runtime_root
        or runtime_admission.runtime_root_identity != expected_root_identity
        or runtime_admission.output_base_root
        != profile_lease.profile.output_base_root
        or runtime_admission.output_base_root_identity
        != profile_lease.profile.output_base_root_identity
        or runtime_admission.output_root != package_lease.output_root
        or runtime_admission.output_root_identity
        != path_identity(package_lease.output_root)
        or runtime_admission.output_operation_admission_path
        != output_operation_admission.admission_path
        or runtime_admission.output_operation_admission_identity
        != output_operation_admission.admission_identity
        or runtime_admission.output_operation_admission_sha256
        != operation.get("admission_sha256")
        or runtime_admission.output_child_binding_sha256
        != child.get("content_sha256")
        or runtime_admission.publication_revision != publication.get("revision")
        or runtime_admission.publication_content_root_sha256
        != publication.get("content_root_sha256")
        or package_lease.content_root_sha256 is None
        or runtime_admission.package_root_sha256
        != "sha256:" + package_lease.content_root_sha256
        or runtime_admission.apply_invocation_sha256
        != pending.get("apply_invocation_sha256")
        or runtime_admission.retention_fence_path
        != (
            runtime_root
            / ".hsconfig"
            / "attempt-retention"
            / f"{runtime_admission.apply_attempt_id}.json"
        )
        or path_lexists(Path(str(pending.get("runtime_admission_staging_path"))))
        or path_lexists(
            Path(
                str(
                    pending.get(
                        "runtime_admission_staging_inner_temp_path"
                    )
                )
            )
        )
    ):
        raise ValueError("controller_apply_pair_runtime_admission_invalid")


def _validate_bound_runtime_admission_commit_reentry(
    *,
    pending: Mapping[str, Any],
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
) -> None:
    """Validate only the exact STAGING_BOUND action-before-CAS state."""

    external = pending.get("external_file_action")
    final_path = Path(str(pending.get("runtime_admission_path")))
    staging_path = Path(
        str(pending.get("runtime_admission_staging_path"))
    )
    inner_temp_path = Path(
        str(pending.get("runtime_admission_staging_inner_temp_path"))
    )
    parent_identity = tuple(
        pending.get("runtime_admission_parent_identity", ())
    )
    staging_identity = tuple(
        pending.get("runtime_admission_staging_identity", ())
    )
    staging_size = pending.get("runtime_admission_staging_size")
    staging_sha256 = pending.get("runtime_admission_staging_sha256")
    planned_size = pending.get("runtime_admission_document_size")
    planned_sha256 = pending.get("runtime_admission_document_sha256")
    if (
        pending.get("stage") != "STAGING_BOUND"
        or not isinstance(external, Mapping)
        or external.get("stage") != "STAGING_BOUND"
        or external.get("action_kind")
        != "commit_bound_runtime_admission"
        or external.get("commit_mode") != "create_no_replace"
        or external.get("predecessor_state") != "absent"
        or Path(str(external.get("final_path"))) != final_path
        or Path(str(external.get("staging_path"))) != staging_path
        or Path(str(external.get("inner_temp_path")))
        != inner_temp_path
        or tuple(external.get("parent_identity", ())) != parent_identity
        or tuple(external.get("staging_identity", ()))
        != staging_identity
        or external.get("staging_size") != staging_size
        or external.get("staging_sha256") != staging_sha256
        or external.get("planned_successor_size") != planned_size
        or external.get("planned_successor_sha256") != planned_sha256
        or type(planned_size) is not int
        or planned_size < 0
        or staging_size != planned_size
        or staging_sha256 != planned_sha256
        or runtime_admission.admission_path != final_path
        or runtime_admission.admission_parent_identity != parent_identity
        or runtime_admission.admission_identity != staging_identity
        or runtime_admission.admission_sha256 != planned_sha256
        or path_lexists(staging_path)
        or path_lexists(inner_temp_path)
    ):
        raise ValueError("controller_apply_pair_runtime_admission_invalid")
    try:
        raw, identity = _read_exact_runtime_external_file(
            final_path,
            expected_parent_identity=parent_identity,
            maximum_size=max(planned_size, 1),
        )
    except (OSError, ValueError) as error:
        raise ValueError(
            "controller_apply_pair_runtime_admission_invalid"
        ) from error
    if (
        identity != staging_identity
        or len(raw) != planned_size
        or "sha256:" + hashlib.sha256(raw).hexdigest()
        != planned_sha256
        or path_lexists(staging_path)
        or path_lexists(inner_temp_path)
    ):
        raise ValueError("controller_apply_pair_runtime_admission_invalid")


def _classify_controller_pair_output_operation(
    *,
    persisted: LiveStartSession,
    historical: OutputOperationAdmissionEvidence,
    observed: OutputOperationAdmissionEvidence | None,
) -> tuple[
    Literal[
        "PRE_HANDOFF_READY",
        "POST_HANDOFF_RELEASE_ONLY",
        "POST_HANDOFF_READY",
    ],
    Literal["exact_old", "absent", "valid_foreign"],
]:
    operation = persisted.output_operation_admission_binding
    if not isinstance(operation, Mapping):
        raise ValueError("controller_apply_pair_output_operation_invalid")
    state = operation.get("state")
    if state == "ACTIVE":
        if observed != historical:
            raise ValueError("controller_apply_pair_output_operation_invalid")
        return "PRE_HANDOFF_READY", "exact_old"
    if state != "RUNTIME_HANDOFF_RELEASE_AUTHORIZED":
        raise ValueError("controller_apply_pair_output_operation_invalid")
    if observed is None:
        return "POST_HANDOFF_READY", "absent"
    if observed == historical:
        return "POST_HANDOFF_RELEASE_ONLY", "exact_old"
    if (
        observed.admission_identity == historical.admission_identity
        or observed.admission_sha256 == historical.admission_sha256
        or observed.run_id == historical.run_id
    ):
        raise ValueError("controller_apply_pair_output_operation_replaced")
    return "POST_HANDOFF_READY", "valid_foreign"


def _validate_controller_pair_projection(
    *,
    persisted: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_admission: OutputOperationAdmissionEvidence,
    package_lease: PackageInputLease,
    runtime_root: Path,
    expected_root_identity: PathIdentity,
    entry_mode: Literal[
        "PRE_HANDOFF_READY",
        "POST_HANDOFF_RELEASE_ONLY",
        "POST_HANDOFF_READY",
    ],
) -> None:
    operation = persisted.output_operation_admission_binding
    child = persisted.output_child_binding
    publication = persisted.publication_binding
    package_publication = package_lease.publication
    expected_operation_state = (
        "ACTIVE"
        if entry_mode == "PRE_HANDOFF_READY"
        else "RUNTIME_HANDOFF_RELEASE_AUTHORIZED"
    )
    if (
        persisted.preview_requested is not False
        or profile_lease.profile.live_by_default is not True
        or profile_lease.profile.runtime_root != runtime_root
        or profile_lease.profile.runtime_root_identity != expected_root_identity
    ):
        raise ValueError("controller_apply_pair_profile_runtime_invalid")
    violations = [
        name
        for name, invalid in (
            ("operation_type", not isinstance(operation, Mapping)),
            (
                "operation_state",
                isinstance(operation, Mapping)
                and operation.get("state") != expected_operation_state,
            ),
            (
                "operation_path",
                isinstance(operation, Mapping)
                and operation.get("admission_path")
                != str(output_operation_admission.admission_path),
            ),
            (
                "operation_identity",
                isinstance(operation, Mapping)
                and tuple(operation.get("admission_identity", ()))
                != output_operation_admission.admission_identity,
            ),
            ("child_type", not isinstance(child, Mapping)),
            (
                "child_claim",
                isinstance(child, Mapping) and child.get("claim_state") != "RETIRED",
            ),
            (
                "child_path",
                isinstance(child, Mapping)
                and child.get("output_child_path") != str(package_lease.output_root),
            ),
            ("publication_type", not isinstance(publication, Mapping)),
            (
                "child_binding",
                isinstance(child, Mapping)
                and isinstance(publication, Mapping)
                and child.get("content_sha256")
                != publication.get("output_child_binding_sha256"),
            ),
            ("package_publication", package_publication is None),
            (
                "publication_revision",
                package_publication is not None
                and isinstance(publication, Mapping)
                and package_publication.revision != publication.get("revision"),
            ),
            (
                "publication_sha256",
                package_publication is not None
                and isinstance(publication, Mapping)
                and package_publication.content_root_sha256
                != str(publication.get("content_root_sha256")).removeprefix("sha256:"),
            ),
            (
                "package_sha256",
                isinstance(publication, Mapping)
                and package_lease.content_root_sha256
                != str(publication.get("content_root_sha256")).removeprefix("sha256:"),
            ),
        )
        if invalid
    ]
    if violations:
        raise ValueError(
            "controller_apply_pair_publication_projection_invalid:"
            + ",".join(violations)
        )
    _validate_historical_output_operation_binding(
        persisted=persisted,
        evidence=output_operation_admission,
        profile_lease=profile_lease,
    )


_active_controller_apply_pairs: dict[int, _ControllerApplyLeasePairBinding] = {}
_active_controller_apply_pairs_lock = Lock()


@dataclass(frozen=True, slots=True)
class _RuntimeApplyLeaseBinding:
    token: RuntimeApplyLockToken
    lease: RuntimeApplyLease
    thread_id: int
    runtime_root: Path
    runtime_root_identity: PathIdentity
    metadata_root: Path
    metadata_root_identity: PathIdentity
    apply_lock_path: Path
    apply_lock_identity: PathIdentity
    path_guard: FilesystemPathGuard


_active_runtime_apply_leases: dict[int, _RuntimeApplyLeaseBinding] = {}
_active_runtime_apply_leases_lock = Lock()


@dataclass(frozen=True, slots=True)
class _RuntimeFile:
    relative_path: str
    size: int
    sha256: str
    source_path: str


@dataclass(frozen=True, slots=True)
class _RuntimePackageSpec:
    deck_name: str
    logical_config_dir: str
    package_root_sha256: str
    files: tuple[_RuntimeFile, ...]


@dataclass(frozen=True, slots=True)
class _RecoveryOutcome:
    state: RuntimeState | None
    repaired: bool


@contextmanager
def lease_runtime_apply(
    runtime_root: Path,
    *,
    expected_root_identity: PathIdentity,
) -> Iterator[RuntimeApplyLease]:
    """Hold the Runtime apply lock after the root-scoped live-admission gate."""

    root = _require_exact_runtime_root(
        runtime_root,
        expected_root_identity=expected_root_identity,
    )
    _bootstrap_neutral_output_locks()
    with lease_output_operation_admission() as operation_lease:
        with _lease_runtime_apply_under_output_operation(
            output_operation_lease=operation_lease,
            runtime_root=root,
            expected_root_identity=expected_root_identity,
        ) as lease:
            yield lease


@contextmanager
def _lease_runtime_apply_under_output_operation(
    *,
    output_operation_lease: OutputOperationAdmissionLease,
    runtime_root: Path,
    expected_root_identity: PathIdentity,
) -> Iterator[RuntimeApplyLease]:
    """Hold Runtime beneath one already-active output-operation lease."""

    root = _require_exact_runtime_root(
        runtime_root,
        expected_root_identity=expected_root_identity,
    )

    def require_gates() -> None:
        require_output_operation_allows_runtime_mutation(
            lease=output_operation_lease,
        )
        require_live_admission_allows_runtime_mutation(
            runtime_root=root,
            runtime_root_identity=expected_root_identity,
        )

    with _lease_runtime_apply_after_gates(
        runtime_root=root,
        expected_root_identity=expected_root_identity,
        require_gates=require_gates,
    ) as lease:
        yield lease


@contextmanager
def lease_controller_apply_pair(
    *,
    package_lease: PackageInputLease,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    output_operation_admission: OutputOperationAdmissionEvidence,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence | None,
    runtime_root: Path,
    expected_root_identity: PathIdentity,
) -> Iterator[ControllerApplyLeasePair]:
    """Mint the narrow normal or exact post-handoff reentry pair."""

    validated_entry_mode: Literal[
        "PRE_HANDOFF_READY",
        "POST_HANDOFF_RELEASE_ONLY",
        "POST_HANDOFF_READY",
    ] | None = None
    validated_output_disposition: Literal[
        "exact_old",
        "absent",
        "valid_foreign",
    ] | None = None

    def require_outer_capabilities() -> None:
        nonlocal validated_entry_mode, validated_output_disposition
        if not isinstance(session_lease, LiveStartSessionLease):
            raise TypeError("controller_apply_pair_session_lease_invalid")
        if not isinstance(expected_session, LiveStartSession):
            raise TypeError("controller_apply_pair_session_cursor_invalid")
        if not isinstance(profile_lease, OperatorProfileLease):
            raise TypeError("controller_apply_pair_profile_lease_invalid")
        if not isinstance(
            output_operation_lease,
            OutputOperationAdmissionLease,
        ):
            raise TypeError("controller_apply_pair_output_operation_lease_invalid")
        if type(output_operation_admission) is not OutputOperationAdmissionEvidence:
            raise TypeError("controller_apply_pair_output_operation_invalid")
        if not isinstance(package_lease, PackageInputLease):
            raise TypeError("controller_apply_pair_package_lease_invalid")
        persisted = load_live_start_session_under_lock(session_lease=session_lease)
        if (
            persisted != expected_session
            or persisted.canonical_json != expected_session.canonical_json
            or persisted.session_identity != expected_session.session_identity
        ):
            raise ValueError("controller_apply_pair_session_cursor_invalid")
        pending = persisted.pending_transition
        operation = persisted.output_operation_admission_binding
        if not isinstance(operation, Mapping):
            raise ValueError("controller_apply_pair_session_cursor_invalid")
        operation_state = operation.get("state")
        if operation_state == "ACTIVE":
            if (
                persisted.phase.value != "PUBLICATION_COMMITTED"
                or not isinstance(pending, Mapping)
                or pending.get("operation") != "install_apply_invocation"
                or pending.get("stage")
                not in {"PREPARED", "STAGING_BOUND", "PRIMARY_APPLIED"}
                or not isinstance(
                    pending.get("apply_invocation_sha256"),
                    str,
                )
                or (
                    runtime_admission is not None
                    and (
                        type(runtime_admission)
                        is not RuntimeLiveAttemptAdmissionEvidence
                        or pending.get("stage")
                        not in {"STAGING_BOUND", "PRIMARY_APPLIED"}
                    )
                )
            ):
                raise ValueError("controller_apply_pair_session_cursor_invalid")
        elif operation_state == "RUNTIME_HANDOFF_RELEASE_AUTHORIZED":
            if type(runtime_admission) is not RuntimeLiveAttemptAdmissionEvidence:
                raise ValueError("controller_apply_pair_runtime_admission_invalid")
        else:
            raise ValueError("controller_apply_pair_session_cursor_invalid")
        revalidate_operator_profile_lease(profile_lease)
        observed_operation = observe_output_operation_admission_under_lease(
            lease=output_operation_lease
        )
        if (
            output_operation_admission.session_root != session_lease.session_root
            or output_operation_admission.session_root_identity
            != session_lease.session_root_identity
            or output_operation_admission.operator_profile_path
            != profile_lease.profile_path
            or output_operation_admission.operator_profile_identity
            != profile_lease.profile_identity
            or output_operation_admission.operator_profile_sha256
            != profile_lease.profile.content_sha256
        ):
            raise ValueError("controller_apply_pair_output_operation_invalid")
        _require_active_package_input_lease(package_lease)
        if (
            package_lease.publication is None
            or package_lease.snapshot is None
            or package_lease.output_root is None
            or package_lease.output_root != output_operation_admission.output_child_path
        ):
            raise ValueError("controller_apply_pair_package_invalid")
        physical_runtime_admission = load_runtime_live_attempt_admission()
        if operation_state == "ACTIVE":
            if runtime_admission is None:
                if physical_runtime_admission is not None:
                    raise ValueError(
                        "controller_apply_pair_runtime_admission_present"
                    )
            elif physical_runtime_admission != runtime_admission:
                raise ValueError("controller_apply_pair_runtime_admission_invalid")
        elif physical_runtime_admission != runtime_admission:
            raise ValueError("controller_apply_pair_runtime_admission_invalid")
        entry_mode, output_disposition = (
            _classify_controller_pair_output_operation(
                persisted=persisted,
                historical=output_operation_admission,
                observed=observed_operation,
            )
        )
        _validate_controller_pair_projection(
            persisted=persisted,
            profile_lease=profile_lease,
            output_operation_admission=output_operation_admission,
            package_lease=package_lease,
            runtime_root=runtime_root,
            expected_root_identity=expected_root_identity,
            entry_mode=entry_mode,
        )
        if type(runtime_admission) is RuntimeLiveAttemptAdmissionEvidence:
            if operation_state == "ACTIVE":
                _validate_pre_handoff_runtime_admission(
                    persisted=persisted,
                    runtime_admission=runtime_admission,
                    profile_lease=profile_lease,
                    output_operation_admission=output_operation_admission,
                    package_lease=package_lease,
                    runtime_root=runtime_root,
                    expected_root_identity=expected_root_identity,
                )
            else:
                _validate_post_handoff_runtime_admission(
                    persisted=persisted,
                    runtime_admission=runtime_admission,
                    profile_lease=profile_lease,
                    output_operation_admission=output_operation_admission,
                    package_lease=package_lease,
                    runtime_root=runtime_root,
                    expected_root_identity=expected_root_identity,
                )
        validated_entry_mode = entry_mode
        validated_output_disposition = output_disposition

    require_outer_capabilities()
    with _lease_runtime_apply_after_gates(
        runtime_root=runtime_root,
        expected_root_identity=expected_root_identity,
        require_gates=require_outer_capabilities,
    ) as runtime_lease:
        if validated_entry_mode is None or validated_output_disposition is None:
            raise AssertionError("controller_apply_pair_validation_missing")
        token = ControllerApplyLeasePairToken(_CONTROLLER_PAIR_TOKEN_AUTHORITY)
        pair = ControllerApplyLeasePair(
            package_lease=package_lease,
            runtime_lease=runtime_lease,
            pair_token=token,
        )
        binding = _ControllerApplyLeasePairBinding(
            token=token,
            pair=pair,
            thread_id=get_ident(),
            session_lease=session_lease,
            expected_session=expected_session,
            profile_lease=profile_lease,
            output_operation_lease=output_operation_lease,
            output_operation_admission=output_operation_admission,
            package_lease=package_lease,
            runtime_lease=runtime_lease,
            session_token=session_lease.lock_token,
            profile_token=profile_lease.lock_token,
            output_operation_token=output_operation_lease.lock_token,
            package_token=package_lease.lock_token,
            runtime_token=runtime_lease.lock_token,
            session_root=session_lease.session_root,
            session_root_identity=session_lease.session_root_identity,
            run_id=expected_session.run_id,
            deck_name=expected_session.deck_name,
            deck_code_sha256=expected_session.deck_code_sha256,
            preview_requested=expected_session.preview_requested,
            candidate_revision=expected_session.candidate_revision,
            revisions_used=expected_session.revisions_used,
            input_snapshot_manifest_sha256=(
                expected_session.input_snapshot_manifest_sha256
            ),
            entry_session_identity=expected_session.session_identity,
            entry_session_sha256=expected_session.content_sha256,
            runtime_admission=runtime_admission,
            entry_mode=validated_entry_mode,
            reentry_output_disposition=validated_output_disposition,
        )
        with _active_controller_apply_pairs_lock:
            _active_controller_apply_pairs[id(token)] = binding
        try:
            yield pair
        finally:
            with _active_controller_apply_pairs_lock:
                active = _active_controller_apply_pairs.get(id(token))
                if active is binding:
                    del _active_controller_apply_pairs[id(token)]


def _authenticate_controller_apply_pair_binding(
    pair: ControllerApplyLeasePair,
) -> _ControllerApplyLeasePairBinding:
    """Authenticate pair registry and independently captured component bearers."""

    if not isinstance(pair, ControllerApplyLeasePair):
        raise ValueError("controller_apply_pair_invalid")
    token = pair.pair_token
    if not isinstance(token, ControllerApplyLeasePairToken):
        raise ValueError("controller_apply_pair_invalid")
    with _active_controller_apply_pairs_lock:
        binding = _active_controller_apply_pairs.get(id(token))
    if binding is None or binding.token is not token or binding.pair is not pair:
        raise ValueError("controller_apply_pair_inactive_or_forged")
    if binding.thread_id != get_ident() or token._thread_id != get_ident():
        raise ValueError("controller_apply_pair_wrong_thread")
    if (
        pair.package_lease is not binding.package_lease
        or pair.runtime_lease is not binding.runtime_lease
        or binding.session_lease.lock_token is not binding.session_token
        or binding.profile_lease.lock_token is not binding.profile_token
        or binding.output_operation_lease.lock_token
        is not binding.output_operation_token
        or binding.pair.package_lease.lock_token is not binding.package_token
        or binding.pair.runtime_lease.lock_token is not binding.runtime_token
    ):
        raise ValueError("controller_apply_pair_invalid")
    return binding


def _validate_controller_pair_session_provenance(
    *,
    binding: _ControllerApplyLeasePairBinding,
    persisted: LiveStartSession,
) -> None:
    if (
        binding.session_lease.session_root != binding.session_root
        or binding.session_lease.session_root_identity
        != binding.session_root_identity
        or persisted.run_id != binding.run_id
        or persisted.deck_name != binding.deck_name
        or persisted.deck_code_sha256 != binding.deck_code_sha256
        or persisted.preview_requested is not binding.preview_requested
        or persisted.candidate_revision != binding.candidate_revision
        or persisted.revisions_used != binding.revisions_used
        or persisted.input_snapshot_manifest_sha256
        != binding.input_snapshot_manifest_sha256
    ):
        raise ValueError("controller_apply_pair_session_lineage_invalid")


def _require_controller_pair_session_cursor(
    *,
    lease_pair: ControllerApplyLeasePair,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
) -> _ControllerApplyLeasePairBinding:
    """Bind an action to the exact current cursor under the originating lease."""

    binding = _authenticate_controller_apply_pair_binding(lease_pair)
    if (
        session_lease is not binding.session_lease
        or session_lease.lock_token is not binding.session_token
    ):
        raise ValueError("controller_apply_pair_session_lease_invalid")
    if not isinstance(expected_session, LiveStartSession):
        raise TypeError("controller_apply_pair_session_cursor_invalid")
    persisted = load_live_start_session_under_lock(session_lease=session_lease)
    if (
        persisted != expected_session
        or persisted.canonical_json != expected_session.canonical_json
        or persisted.content_sha256 != expected_session.content_sha256
        or persisted.session_identity != expected_session.session_identity
    ):
        raise ValueError("controller_apply_pair_session_cursor_invalid")
    _validate_controller_pair_session_provenance(
        binding=binding,
        persisted=persisted,
    )
    return binding


def _require_active_controller_apply_pair(
    pair: ControllerApplyLeasePair,
) -> _ControllerApplyLeasePairBinding:
    """Authenticate exact-object, same-thread and still-active pair authority."""

    binding = _authenticate_controller_apply_pair_binding(pair)
    persisted = load_live_start_session_under_lock(session_lease=binding.session_lease)
    _validate_controller_pair_session_provenance(
        binding=binding,
        persisted=persisted,
    )
    revalidate_operator_profile_lease(binding.profile_lease)
    observed_operation = observe_output_operation_admission_under_lease(
        binding.output_operation_lease
    )
    _require_active_package_input_lease(pair.package_lease)
    _require_active_runtime_apply_lease(pair.runtime_lease)
    physical_runtime_admission = load_runtime_live_attempt_admission()
    operation = persisted.output_operation_admission_binding
    operation_state = (
        operation.get("state") if isinstance(operation, Mapping) else None
    )
    if binding.runtime_admission is None:
        if physical_runtime_admission is not None:
            raise ValueError("controller_apply_pair_runtime_admission_present")
    else:
        if physical_runtime_admission != binding.runtime_admission:
            raise ValueError("controller_apply_pair_runtime_admission_invalid")
        if operation_state == "ACTIVE":
            _validate_pre_handoff_runtime_admission(
                persisted=persisted,
                runtime_admission=binding.runtime_admission,
                profile_lease=binding.profile_lease,
                output_operation_admission=(
                    binding.output_operation_admission
                ),
                package_lease=pair.package_lease,
                runtime_root=pair.runtime_lease.runtime_root,
                expected_root_identity=(
                    pair.runtime_lease.runtime_root_identity
                ),
            )
        else:
            _validate_post_handoff_runtime_admission(
                persisted=persisted,
                runtime_admission=binding.runtime_admission,
                profile_lease=binding.profile_lease,
                output_operation_admission=(
                    binding.output_operation_admission
                ),
                package_lease=pair.package_lease,
                runtime_root=pair.runtime_lease.runtime_root,
                expected_root_identity=(
                    pair.runtime_lease.runtime_root_identity
                ),
            )
    entry_mode, output_disposition = _classify_controller_pair_output_operation(
        persisted=persisted,
        historical=binding.output_operation_admission,
        observed=observed_operation,
    )
    _validate_controller_pair_projection(
        persisted=persisted,
        profile_lease=binding.profile_lease,
        output_operation_admission=binding.output_operation_admission,
        package_lease=pair.package_lease,
        runtime_root=pair.runtime_lease.runtime_root,
        expected_root_identity=pair.runtime_lease.runtime_root_identity,
        entry_mode=entry_mode,
    )
    if (
        entry_mode != binding.entry_mode
        or output_disposition != binding.reentry_output_disposition
    ):
        refreshed = replace(
            binding,
            entry_mode=entry_mode,
            reentry_output_disposition=output_disposition,
        )
        with _active_controller_apply_pairs_lock:
            if _active_controller_apply_pairs.get(id(binding.token)) is not binding:
                raise ValueError("controller_apply_pair_inactive_or_forged")
            _active_controller_apply_pairs[id(binding.token)] = refreshed
        binding = refreshed
    return binding


_RUNTIME_EXTERNAL_FILE_ACTION_MAX_BYTES = 64 * 1024 * 1024


def _read_exact_runtime_external_file(
    path: Path,
    *,
    expected_parent_identity: PathIdentity,
    maximum_size: int,
) -> tuple[bytes, PathIdentity]:
    if path_identity(path.parent) != expected_parent_identity:
        raise ValueError("runtime_external_file_action_parent_changed")
    status = plain_file_status(path)
    identity = path_identity_from_status(status)
    require_no_alternate_data_streams(
        path,
        expected_identity=identity,
        expected_parent_identity=expected_parent_identity,
        directory=False,
        expected_size=status.st_size,
    )
    raw = read_file_no_follow(
        path,
        expected_status=status,
        maximum_size=maximum_size,
    )
    return raw, identity


def _retire_unbound_runtime_external_file(
    path: Path,
    *,
    expected_parent_identity: PathIdentity,
    maximum_size: int,
    expected_size: int | None = None,
    expected_sha256: str | None = None,
    expected_identity: PathIdentity | None = None,
) -> tuple[PathIdentity, int, str] | None:
    if not path_lexists(path):
        return None
    raw, identity = _read_exact_runtime_external_file(
        path,
        expected_parent_identity=expected_parent_identity,
        maximum_size=maximum_size,
    )
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    if (
        (expected_identity is not None and identity != expected_identity)
        or
        (expected_size is not None and len(raw) != expected_size)
        or (expected_sha256 is not None and digest != expected_sha256)
    ):
        raise ValueError("runtime_external_file_action_residue_changed")
    secure_unlink(
        path,
        expected_identity=identity,
        expected_parent_identity=expected_parent_identity,
        missing_ok=False,
    )
    return identity, len(raw), digest


def _runtime_admission_action_row(
    *,
    session: LiveStartSession,
    action: str,
) -> Mapping[str, Any]:
    pending = session.pending_transition
    if (
        not isinstance(pending, Mapping)
        or pending.get("operation") != "install_apply_invocation"
    ):
        raise ValueError("runtime_admission_file_action_cursor_invalid")
    external = pending.get("external_file_action")
    if not isinstance(external, Mapping):
        raise ValueError("runtime_admission_file_action_missing")
    expected_rows = {
        "materialize_runtime_admission_staging": (
            "PREPARED",
            "PLANNED",
            "materialize_runtime_admission_staging",
        ),
        "retire_unbound_runtime_admission_staging": (
            "PREPARED",
            "PLANNED",
            "materialize_runtime_admission_staging",
        ),
        "commit_bound_runtime_admission": (
            "STAGING_BOUND",
            "STAGING_BOUND",
            "commit_bound_runtime_admission",
        ),
        "materialize_invocation_receipt_staging": (
            "PRIMARY_APPLIED",
            "PLANNED",
            "materialize_invocation_receipt_staging",
        ),
        "retire_unbound_invocation_receipt_staging": (
            "PRIMARY_APPLIED",
            "PLANNED",
            "materialize_invocation_receipt_staging",
        ),
        "commit_bound_invocation_receipt": (
            "PRIMARY_APPLIED",
            "STAGING_BOUND",
            "commit_bound_invocation_receipt",
        ),
    }
    try:
        expected = expected_rows[action]
    except KeyError as error:
        raise ValueError("runtime_admission_file_action_invalid") from error
    if (
        pending.get("stage") != expected[0]
        or external.get("stage") != expected[1]
        or external.get("action_kind") != expected[2]
    ):
        raise ValueError("runtime_admission_file_action_cursor_invalid")
    if action.startswith(
        (
            "materialize_invocation",
            "retire_unbound_invocation",
            "commit_bound_invocation",
        )
    ):
        layout = session.runtime_layout_bootstrap
        if not isinstance(layout, Mapping) or layout.get("stage") != "COMPLETE":
            raise ValueError("runtime_invocation_receipt_before_layout_complete")
    return external


def _execute_runtime_admission_file_action_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    admission_authorization: RuntimeAdmissionAuthorization,
    payload: bytes,
) -> RuntimeAdmissionStepReceipt:
    """Execute one admission/receipt file row under the exact active pair."""

    binding = _require_active_controller_apply_pair(lease_pair)
    _require_controller_pair_session_cursor(
        lease_pair=lease_pair,
        session_lease=session_lease,
        expected_session=expected_session,
    )
    if not isinstance(admission_authorization, RuntimeAdmissionAuthorization):
        raise TypeError("runtime_admission_file_action_capability_invalid")
    bearer = admission_authorization._opaque
    action = bearer.action
    _require_opaque_carrier(
        admission_authorization,
        carrier_type=RuntimeAdmissionAuthorization,
        family="runtime_admission",
        action=action,
        consume=False,
    )
    if (
        bearer.session_bearer is not session_lease.lock_token._bearer
        or bearer.session_bearer is not binding.session_token._bearer
        or bearer.cursor_sha256 != expected_session.content_sha256
    ):
        raise ValueError("runtime_admission_file_action_capability_changed")
    external = _runtime_admission_action_row(
        session=expected_session,
        action=action,
    )
    if type(payload) is not bytes:
        raise TypeError("runtime_admission_file_action_payload_invalid")
    content = payload
    planned_size = external.get("planned_successor_size")
    planned_sha256 = external.get("planned_successor_sha256")
    if (
        type(planned_size) is not int
        or planned_size < 0
        or planned_size > _RUNTIME_EXTERNAL_FILE_ACTION_MAX_BYTES
        or len(content) != planned_size
        or "sha256:" + hashlib.sha256(content).hexdigest() != planned_sha256
    ):
        raise ValueError("runtime_admission_file_action_payload_changed")

    final_path = Path(str(external["final_path"]))
    staging_path = Path(str(external["staging_path"]))
    inner_temp_path = Path(str(external["inner_temp_path"]))
    parent_identity = tuple(external["parent_identity"])
    if (
        not all(path.is_absolute() for path in (final_path, staging_path, inner_temp_path))
        or final_path.parent != staging_path.parent
        or staging_path.parent != inner_temp_path.parent
        or path_identity(final_path.parent) != parent_identity
    ):
        raise ValueError("runtime_admission_file_action_paths_changed")

    def perform() -> RuntimeAdmissionPhysicalPostcondition:
        _require_active_controller_apply_pair(lease_pair)
        _require_controller_pair_session_cursor(
            lease_pair=lease_pair,
            session_lease=session_lease,
            expected_session=expected_session,
        )
        current_external = _runtime_admission_action_row(
            session=expected_session,
            action=action,
        )
        if current_external != external:
            raise ValueError("runtime_admission_file_action_cursor_changed")

        if action.startswith("retire_unbound_"):
            if path_lexists(final_path):
                raise ValueError("runtime_admission_file_action_direct_final")
            _retire_unbound_runtime_external_file(
                inner_temp_path,
                expected_parent_identity=parent_identity,
                maximum_size=max(planned_size, 1),
            )
            historical = _retire_unbound_runtime_external_file(
                staging_path,
                expected_parent_identity=parent_identity,
                maximum_size=max(planned_size, 1),
                expected_size=planned_size,
                expected_sha256=str(planned_sha256),
            )
            historical_identity = historical[0] if historical is not None else None
            historical_size = historical[1] if historical is not None else None
            historical_sha256 = historical[2] if historical is not None else None
            if action == "retire_unbound_runtime_admission_staging":
                invocation_receipt_path = (
                    session_lease.session_root
                    / "receipts"
                    / "apply_invocation.json"
                )
                if path_lexists(invocation_receipt_path):
                    raise ValueError("runtime_invocation_receipt_created_early")
                evidence = {
                    "admission_path": str(final_path),
                    "admission_absent": True,
                    "staging_path": str(staging_path),
                    "historical_staging_identity": historical_identity,
                    "historical_staging_size": historical_size,
                    "historical_staging_sha256": historical_sha256,
                    "staging_absent": True,
                    "inner_temp_path": str(inner_temp_path),
                    "inner_temp_absent": True,
                    "invocation_receipt_path": str(invocation_receipt_path),
                    "invocation_receipt_absent": True,
                }
            else:
                pending = expected_session.pending_transition
                assert isinstance(pending, Mapping)
                evidence = {
                    "invocation_receipt_path": str(final_path),
                    "invocation_receipt_absent": True,
                    "staging_path": str(staging_path),
                    "historical_staging_identity": historical_identity,
                    "historical_staging_size": historical_size,
                    "historical_staging_sha256": historical_sha256,
                    "staging_absent": True,
                    "inner_temp_path": str(inner_temp_path),
                    "inner_temp_absent": True,
                    "admission_path": pending["runtime_admission_path"],
                    "admission_identity": pending["runtime_admission_identity"],
                    "admission_sha256": pending["runtime_admission_sha256"],
                }
        elif action.startswith("materialize_"):
            if path_lexists(final_path):
                raise ValueError("runtime_admission_file_action_direct_final")
            materialized = atomic_materialize_staging_bytes(
                staging_path=staging_path,
                inner_temp_path=inner_temp_path,
                payload=content,
                expected_parent_identity=parent_identity,
                maximum_size=max(planned_size, 1),
            )
            if path_lexists(final_path):
                raise ValueError("runtime_admission_file_action_direct_final")
            evidence = {
                "staging_path": str(materialized.path),
                "staging_parent_identity": parent_identity,
                "staging_identity": materialized.identity,
                "staging_size": materialized.size,
                "staging_sha256": materialized.sha256,
                "final_absent": True,
                "inner_temp_absent": True,
            }
        else:
            staging_identity = tuple(external["staging_identity"])
            if path_lexists(inner_temp_path):
                raise ValueError("runtime_admission_file_action_inner_temp_present")
            if (
                action == "commit_bound_runtime_admission"
                and path_lexists(final_path)
                and not path_lexists(staging_path)
            ):
                raw, final_identity = _read_exact_runtime_external_file(
                    final_path,
                    expected_parent_identity=parent_identity,
                    maximum_size=max(planned_size, 1),
                )
                committed_identity = final_identity
            else:
                committed = atomic_commit_bound_staging_no_replace(
                    path=final_path,
                    staging_path=staging_path,
                    expected_staging_identity=staging_identity,
                    expected_size=int(external["staging_size"]),
                    expected_sha256=str(external["staging_sha256"]),
                    expected_parent_identity=parent_identity,
                )
                committed_identity = committed.identity
                raw, final_identity = _read_exact_runtime_external_file(
                    final_path,
                    expected_parent_identity=parent_identity,
                    maximum_size=max(planned_size, 1),
                )
            if (
                final_identity != committed_identity
                or final_identity != staging_identity
                or raw != content
                or len(raw) != planned_size
                or "sha256:" + hashlib.sha256(raw).hexdigest()
                != planned_sha256
                or path_lexists(staging_path)
                or path_lexists(inner_temp_path)
            ):
                raise ValueError("runtime_admission_file_action_commit_changed")
            if action == "commit_bound_runtime_admission":
                evidence = {
                    "admission_path": str(final_path),
                    "admission_parent_identity": parent_identity,
                    "admission_identity": final_identity,
                    "admission_size": len(raw),
                    "admission_sha256": (
                        "sha256:" + hashlib.sha256(raw).hexdigest()
                    ),
                    "staging_path": str(staging_path),
                    "staging_absent": True,
                    "inner_temp_path": str(inner_temp_path),
                    "inner_temp_absent": True,
                }
            else:
                pending = expected_session.pending_transition
                assert isinstance(pending, Mapping)
                evidence = {
                    "invocation_receipt_path": str(final_path),
                    "invocation_receipt_parent_identity": parent_identity,
                    "invocation_receipt_identity": final_identity,
                    "invocation_receipt_size": len(raw),
                    "invocation_receipt_sha256": (
                        "sha256:" + hashlib.sha256(raw).hexdigest()
                    ),
                    "apply_invocation_sha256": pending[
                        "apply_invocation_sha256"
                    ],
                    "staging_absent": True,
                    "inner_temp_absent": True,
                }
        return RuntimeAdmissionPhysicalPostcondition(
            action=action,
            evidence=evidence,
        )

    return _execute_runtime_admission_physical_step(
        admission_authorization=admission_authorization,
        action=action,
        physical_action=perform,
    )


def _runtime_layout_paths(
    runtime_root: Path,
    *,
    state_key: str,
) -> tuple[Path, ...]:
    internal = runtime_root / ".hsconfig"
    return (
        runtime_root / "CustomConfig",
        internal / "transactions",
        internal / "staging",
        internal / "receipts",
        internal / "receipts" / state_key,
        internal / "attempt-retention",
        internal / "owner-retirements",
    )


def _require_layout_parent_identity(
    path: Path,
    *,
    expected_identity: PathIdentity,
) -> None:
    parent = Path(path)
    require_plain_directory(parent)
    status = parent.lstat()
    if (
        status_is_reparse(status)
        or path_identity_from_status(status) != expected_identity
    ):
        raise ValueError("runtime_layout_bootstrap_parent_changed")
    require_same_identity_resolution(parent, expected_status=status)
    require_no_alternate_data_streams(
        parent,
        expected_identity=expected_identity,
        expected_parent_identity=path_identity(parent.parent),
        directory=True,
    )
    if path_identity(parent) != expected_identity:
        raise ValueError("runtime_layout_bootstrap_parent_changed")


def _require_runtime_layout_directory(
    path: Path,
    *,
    expected_parent_identity: PathIdentity,
    expected_identity: PathIdentity | None,
    require_empty: bool,
) -> PathIdentity:
    _require_layout_parent_identity(
        path.parent,
        expected_identity=expected_parent_identity,
    )
    status = path.lstat()
    if not stat.S_ISDIR(status.st_mode) or status_is_reparse(status):
        raise ValueError("runtime_layout_bootstrap_directory_unsafe")
    identity = path_identity_from_status(status)
    if expected_identity is not None and identity != expected_identity:
        raise ValueError("runtime_layout_bootstrap_directory_replaced")
    require_same_identity_resolution(path, expected_status=status)
    require_no_alternate_data_streams(
        path,
        expected_identity=identity,
        expected_parent_identity=expected_parent_identity,
        directory=True,
    )
    if require_empty:
        expected_link_count = 1 if os.name == "nt" else 2
        if status.st_nlink != expected_link_count:
            raise ValueError("runtime_layout_bootstrap_directory_unsafe")
        with os.scandir(path) as entries:
            if next(entries, None) is not None:
                raise ValueError(
                    "runtime_layout_bootstrap_created_directory_nonempty"
                )
    after = path.lstat()
    if (
        path_identity_from_status(after) != identity
        or status_is_reparse(after)
        or path_identity(path.parent) != expected_parent_identity
    ):
        raise ValueError("runtime_layout_bootstrap_directory_changed")
    return identity


def _validate_runtime_layout_pair_context(
    *,
    lease_pair: ControllerApplyLeasePair,
    session_lease: LiveStartSessionLease,
    expected_layout_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    output_operation_admission: OutputOperationAdmissionEvidence,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    layout_authorization: RuntimeLayoutBootstrapAuthorization,
    authorization_consumed: bool = False,
) -> tuple[
    _ControllerApplyLeasePairBinding,
    Mapping[str, Any],
    Mapping[str, Any],
    int,
    tuple[Path, ...],
]:
    if type(layout_authorization) is not RuntimeLayoutBootstrapAuthorization:
        raise TypeError("runtime_layout_bootstrap_capability_invalid")
    if type(runtime_admission) is not RuntimeLiveAttemptAdmissionEvidence:
        raise TypeError("runtime_layout_bootstrap_admission_invalid")
    if type(output_operation_admission) is not OutputOperationAdmissionEvidence:
        raise TypeError("runtime_layout_bootstrap_output_operation_invalid")
    binding = _require_active_controller_apply_pair(lease_pair)
    _require_controller_pair_session_cursor(
        lease_pair=lease_pair,
        session_lease=session_lease,
        expected_session=expected_layout_session,
    )
    if (
        profile_lease is not binding.profile_lease
        or profile_lease.lock_token is not binding.profile_token
        or output_operation_lease is not binding.output_operation_lease
        or output_operation_lease.lock_token
        is not binding.output_operation_token
        or output_operation_admission
        is not binding.output_operation_admission
        or runtime_admission is not binding.runtime_admission
        or binding.entry_mode != "PRE_HANDOFF_READY"
    ):
        raise ValueError("runtime_layout_bootstrap_capability_mismatch")
    if authorization_consumed:
        bearer = layout_authorization._opaque
        if (
            bearer.active
            or bearer.family != "runtime_layout_bootstrap"
            or bearer.action
            != "create_or_confirm_runtime_layout_directory"
        ):
            raise ValueError("runtime_layout_bootstrap_capability_changed")
    else:
        bearer = _require_opaque_carrier(
            layout_authorization,
            carrier_type=RuntimeLayoutBootstrapAuthorization,
            family="runtime_layout_bootstrap",
            action="create_or_confirm_runtime_layout_directory",
            consume=False,
        )
    if (
        bearer.session_bearer is not binding.session_token._bearer
        or bearer.cursor_sha256 != expected_layout_session.content_sha256
    ):
        raise ValueError("runtime_layout_bootstrap_capability_changed")
    pending = expected_layout_session.pending_transition
    layout = expected_layout_session.runtime_layout_bootstrap
    if (
        not isinstance(pending, Mapping)
        or pending.get("operation") != "install_apply_invocation"
        or pending.get("stage") != "PRIMARY_APPLIED"
        or pending.get("external_file_action") is not None
        or pending.get("next_action_index") != 0
        or not isinstance(layout, Mapping)
        or layout.get("stage") != "INCOMPLETE"
        or layout.get("run_id") != expected_layout_session.run_id
        or layout.get("apply_attempt_id")
        != runtime_admission.apply_attempt_id
        or pending.get("apply_attempt_id")
        != runtime_admission.apply_attempt_id
        or not _identity_field_matches(
            pending.get("runtime_admission_identity"),
            runtime_admission.admission_identity,
        )
        or pending.get("runtime_admission_sha256")
        != runtime_admission.admission_sha256
        or layout.get("runtime_root")
        != str(lease_pair.runtime_lease.runtime_root)
        or not _identity_field_matches(
            layout.get("runtime_root_identity"),
            lease_pair.runtime_lease.runtime_root_identity,
        )
    ):
        raise ValueError("runtime_layout_bootstrap_cursor_invalid")
    current_index = layout.get("next_directory_index")
    rows = layout.get("directories")
    if (
        type(current_index) is not int
        or not isinstance(rows, (list, tuple))
        or not 0 <= current_index < len(RUNTIME_LAYOUT_DIRECTORY_ROLES)
    ):
        raise ValueError("runtime_layout_bootstrap_cursor_invalid")
    state_key = _state_key(expected_layout_session.deck_name)
    expected_paths = _runtime_layout_paths(
        lease_pair.runtime_lease.runtime_root,
        state_key=state_key,
    )
    if (
        tuple(row.get("role") for row in rows if isinstance(row, Mapping))
        != RUNTIME_LAYOUT_DIRECTORY_ROLES
        or tuple(Path(str(row.get("path"))) for row in rows)
        != expected_paths
    ):
        raise ValueError("runtime_layout_bootstrap_layout_changed")
    return binding, pending, layout, current_index, expected_paths


def _validate_runtime_layout_physical_rows(
    *,
    layout: Mapping[str, Any],
    current_index: int,
    paths: tuple[Path, ...],
) -> tuple[Mapping[str, Any], PathIdentity]:
    rows = layout["directories"]
    current_row = rows[current_index]
    if not isinstance(current_row, Mapping):
        raise ValueError("runtime_layout_bootstrap_cursor_invalid")
    for index, (row, path) in enumerate(zip(rows, paths, strict=True)):
        if not isinstance(row, Mapping):
            raise ValueError("runtime_layout_bootstrap_cursor_invalid")
        parent_identity_value = row.get("expected_parent_identity")
        if index == current_index and row.get("role") == "state_receipts":
            receipts_row = rows[index - 1]
            parent_identity_value = receipts_row.get("successor_identity")
        if parent_identity_value is None:
            if index <= current_index:
                raise ValueError("runtime_layout_bootstrap_parent_unbound")
            continue
        parent_identity = tuple(parent_identity_value)
        _require_layout_parent_identity(
            path.parent,
            expected_identity=parent_identity,
        )
        successor_identity = row.get("successor_identity")
        predecessor_state = row.get("predecessor_state")
        predecessor_identity = row.get("predecessor_identity")
        if index < current_index:
            if successor_identity is None:
                raise ValueError("runtime_layout_bootstrap_prior_row_unbound")
            _require_runtime_layout_directory(
                path,
                expected_parent_identity=parent_identity,
                expected_identity=tuple(successor_identity),
                require_empty=False,
            )
        elif index == current_index:
            if successor_identity is not None:
                raise ValueError("runtime_layout_bootstrap_current_row_bound")
            if predecessor_state == "existing":
                if predecessor_identity is None:
                    raise ValueError(
                        "runtime_layout_bootstrap_predecessor_invalid"
                    )
                _require_runtime_layout_directory(
                    path,
                    expected_parent_identity=parent_identity,
                    expected_identity=tuple(predecessor_identity),
                    require_empty=False,
                )
            elif predecessor_state == "absent":
                if path_lexists(path):
                    _require_runtime_layout_directory(
                        path,
                        expected_parent_identity=parent_identity,
                        expected_identity=None,
                        require_empty=True,
                    )
            else:
                raise ValueError(
                    "runtime_layout_bootstrap_predecessor_invalid"
                )
        elif predecessor_state == "existing":
            if predecessor_identity is None:
                raise ValueError("runtime_layout_bootstrap_predecessor_invalid")
            _require_runtime_layout_directory(
                path,
                expected_parent_identity=parent_identity,
                expected_identity=tuple(predecessor_identity),
                require_empty=False,
            )
        elif predecessor_state == "absent" and path_lexists(path):
            raise ValueError("runtime_layout_bootstrap_future_row_created")
    current_parent_value = current_row.get("expected_parent_identity")
    if current_row.get("role") == "state_receipts":
        current_parent_value = rows[current_index - 1].get(
            "successor_identity"
        )
    if current_parent_value is None:
        raise ValueError("runtime_layout_bootstrap_parent_unbound")
    return current_row, tuple(current_parent_value)


def observe_runtime_layout_bootstrap_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    transaction_id: str,
    retention_owner_run_id: str,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    state_key: str,
) -> RuntimeLayoutBootstrapEvidence:
    """Observe the fixed runtime directory layout without creating a row."""

    if (
        not isinstance(transaction_id, str)
        or _ATTEMPT_ID.fullmatch(transaction_id) is None
        or not isinstance(retention_owner_run_id, str)
        or _ATTEMPT_ID.fullmatch(retention_owner_run_id) is None
        or not _valid_component(state_key)
        or type(runtime_admission) is not RuntimeLiveAttemptAdmissionEvidence
    ):
        raise ValueError("runtime_layout_bootstrap_arguments_invalid")
    binding = _require_active_controller_apply_pair(lease_pair)
    persisted = load_live_start_session_under_lock(
        session_lease=binding.session_lease
    )
    pending = persisted.pending_transition
    if (
        runtime_admission is not binding.runtime_admission
        or binding.entry_mode != "PRE_HANDOFF_READY"
        or transaction_id != runtime_admission.apply_attempt_id
        or retention_owner_run_id
        != runtime_admission.retention_owner_run_id
        or retention_owner_run_id != persisted.run_id
        or state_key != _state_key(persisted.deck_name)
        or not isinstance(pending, Mapping)
        or pending.get("operation") != "install_apply_invocation"
        or pending.get("stage") != "PRIMARY_APPLIED"
        or pending.get("external_file_action") is not None
        or pending.get("next_action_index") != 0
        or pending.get("apply_attempt_id") != transaction_id
        or persisted.runtime_layout_bootstrap is not None
    ):
        raise ValueError("runtime_layout_bootstrap_pair_mismatch")
    runtime_root = lease_pair.runtime_lease.runtime_root
    if (
        path_identity(runtime_root)
        != lease_pair.runtime_lease.runtime_root_identity
        or runtime_admission.runtime_root != runtime_root
        or runtime_admission.runtime_root_identity
        != lease_pair.runtime_lease.runtime_root_identity
    ):
        raise ValueError("runtime_layout_bootstrap_runtime_changed")
    paths = _runtime_layout_paths(runtime_root, state_key=state_key)
    rows: list[dict[str, Any]] = []
    for role, path in zip(
        RUNTIME_LAYOUT_DIRECTORY_ROLES,
        paths,
        strict=True,
    ):
        if role == "state_receipts" and not path_lexists(path.parent):
            parent_identity: PathIdentity | None = None
        else:
            parent_identity = path_identity(path.parent)
            _require_layout_parent_identity(
                path.parent,
                expected_identity=parent_identity,
            )
        if path_lexists(path):
            if parent_identity is None:
                raise ValueError("runtime_layout_bootstrap_parent_unbound")
            predecessor_identity = _require_runtime_layout_directory(
                path,
                expected_parent_identity=parent_identity,
                expected_identity=None,
                require_empty=False,
            )
            predecessor_state = "existing"
        else:
            predecessor_identity = None
            predecessor_state = "absent"
        rows.append(
            {
                "role": role,
                "path": str(path),
                "expected_parent_identity": (
                    None
                    if parent_identity is None
                    else list(parent_identity)
                ),
                "predecessor_state": predecessor_state,
                "predecessor_identity": (
                    None
                    if predecessor_identity is None
                    else list(predecessor_identity)
                ),
                "successor_identity": None,
            }
        )
    return RuntimeLayoutBootstrapEvidence(
        seal_embedded_document(
            "runtime_layout_bootstrap",
            {
                "schema_version": 1,
                "binding_kind": "live_start_runtime_layout_bootstrap",
                "run_id": persisted.run_id,
                "apply_attempt_id": transaction_id,
                "runtime_root": str(runtime_root),
                "runtime_root_identity": list(
                    lease_pair.runtime_lease.runtime_root_identity
                ),
                "stage": "INCOMPLETE",
                "next_directory_index": 0,
                "directory_count": len(rows),
                "directories": rows,
            },
        )
    )


def _planned_prepared_runtime_journal_bytes(
    plan: RuntimeInstallPlan,
    *,
    transaction_id: str,
    state_key: str,
) -> bytes:
    current_ini = plan.ini_snapshot
    next_ini = render_deck_config(
        current_ini,
        deck_name=plan.deck_name,
        config_dir=plan.versioned_config_dir,
    )
    journal = RuntimeTransactionJournal(
        schema_version=1,
        transaction_id=transaction_id,
        deck_name=plan.deck_name,
        source_manifest_sha256=_source_manifest_sha256(plan),
        state_key=state_key,
        logical_config_dir=plan.logical_config_dir,
        package_root_sha256=plan.package_root_sha256,
        candidate_path=f".hsconfig/staging/{transaction_id}",
        target_path=f"CustomConfig/{plan.versioned_config_dir}",
        candidate_identity=None,
        target_identity=None,
        owns_target=False,
        previous_config_dir=current_ini.selected_config_dir,
        next_config_dir=plan.versioned_config_dir,
        previous_ini_sha256=current_ini.sha256,
        next_ini_sha256=hashlib.sha256(next_ini).hexdigest(),
        phase=RuntimeTransactionPhase.PREPARED,
    )
    return runtime_transaction_journal_bytes(journal)


def _initial_new_target_apply_recovery(
    *,
    plan: RuntimeInstallPlan,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    layout_identities: Mapping[str, PathIdentity],
    state_key: str,
) -> RuntimeApplyRecoveryEvidence:
    attempt_id = runtime_admission.apply_attempt_id
    runtime_root = runtime_admission.runtime_root
    retention_path = _runtime_attempt_retention_path(runtime_root, attempt_id)
    retention_parent_identity = layout_identities["attempt_retention"]
    journal_path = runtime_transaction_journal_path(runtime_root, attempt_id)
    journal_raw = _planned_prepared_runtime_journal_bytes(
        plan,
        transaction_id=attempt_id,
        state_key=state_key,
    )
    journal_sha256 = "sha256:" + hashlib.sha256(journal_raw).hexdigest()
    candidate_path = runtime_root / ".hsconfig" / "staging" / attempt_id
    active_raw = build_runtime_attempt_retention_bytes(
        runtime_root=runtime_root,
        state="ACTIVE",
        apply_attempt_id=attempt_id,
        retention_owner_run_id=runtime_admission.retention_owner_run_id,
        journal_path=None,
        journal_identity=None,
        journal_sha256=None,
        package_root_sha256=None,
        target_path=None,
        target_identity=None,
        owns_target=None,
        target_owner_journal_path=None,
        target_owner_journal_identity=None,
        target_owner_journal_sha256=None,
        planned_journal_path=None,
        planned_journal_size=None,
        planned_journal_sha256=None,
        candidate_path=None,
        candidate_parent_identity=None,
        candidate_identity=None,
    )
    active_sha256 = "sha256:" + hashlib.sha256(active_raw).hexdigest()
    external = _build_external_file_action(
        action_kind="materialize_file_action_staging",
        action_index=0,
        final_path=retention_path,
        staging_path=retention_path.with_name(f"{retention_path.name}.staged"),
        inner_temp_path=retention_path.with_name(
            f".{retention_path.name}.staged.live-start-atomic.tmp"
        ),
        parent_identity=retention_parent_identity,
        predecessor_identity=None,
        predecessor_size=None,
        predecessor_sha256=None,
        planned_successor_size=len(active_raw),
        planned_successor_sha256=active_sha256,
        commit_mode="create_no_replace",
    )
    value: dict[str, Any] = {
        field: None for field in _APPLY_RECOVERY_FIELDS if field != "content_sha256"
    }
    value.update(
        {
            "schema_version": 1,
            "recovery_kind": "live_start_runtime_apply_recovery_evidence",
            "recovery_stage": "ACTIVE",
            "run_id": runtime_admission.run_id,
            "apply_attempt_id": attempt_id,
            "apply_invocation_sha256": runtime_admission.apply_invocation_sha256,
            "runtime_admission_path": str(runtime_admission.admission_path),
            "runtime_admission_parent_identity": runtime_admission.admission_parent_identity,
            "runtime_admission_identity": runtime_admission.admission_identity,
            "runtime_admission_sha256": runtime_admission.admission_sha256,
            "package_root_sha256": runtime_admission.package_root_sha256,
            "runtime_root": str(runtime_root),
            "runtime_root_identity": runtime_admission.runtime_root_identity,
            "install_route": "new_target",
            "action_index": 0,
            "expected_action": "materialize_file_action_staging",
            "external_file_action": external,
            "runtime_match_status": "not_run",
            "candidate_path": str(candidate_path),
            "candidate_parent_identity": layout_identities["staging"],
            "predecessor_candidate_identity": None,
            "renamed_target_path": str(
                runtime_root / "CustomConfig" / plan.versioned_config_dir
            ),
            "planned_journal_successor_path": str(journal_path),
            "planned_journal_successor_parent_identity": layout_identities[
                "transactions"
            ],
            "planned_journal_successor_phase": "PREPARED",
            "planned_journal_successor_size": len(journal_raw),
            "planned_journal_successor_sha256": journal_sha256,
        }
    )
    return RuntimeApplyRecoveryEvidence(
        _seal_apply_recovery_successor(value, changes={})
    )


def _initial_prior_owner_apply_recovery(
    *,
    plan: RuntimeInstallPlan,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    layout_identities: Mapping[str, PathIdentity],
    state_key: str,
    target_identity: PathIdentity,
    owner_path: Path,
    owner_identity: PathIdentity,
    owner_sha256: str,
) -> RuntimeApplyRecoveryEvidence:
    target = runtime_admission.runtime_root / "CustomConfig" / plan.versioned_config_dir
    if (
        path_identity(target.parent) != layout_identities["custom_config"]
        or path_identity(target) != target_identity
    ):
        raise ValueError("runtime_initial_prior_owner_target_changed")
    owner_raw, observed_owner_identity = _read_exact_runtime_external_file(
        owner_path,
        expected_parent_identity=layout_identities["transactions"],
        maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
    )
    owner = parse_runtime_transaction_journal_bytes(
        owner_raw,
        expected_transaction_id=owner_path.stem,
    )
    if (
        observed_owner_identity != owner_identity
        or "sha256:" + hashlib.sha256(owner_raw).hexdigest() != owner_sha256
        or owner.phase != RuntimeTransactionPhase.FINALIZED
        or owner.owns_target is not True
        or owner.target_identity != target_identity
    ):
        raise ValueError("runtime_initial_prior_owner_changed")
    base = _plain_json_value(
        _initial_new_target_apply_recovery(
            plan=plan,
            runtime_admission=runtime_admission,
            layout_identities=layout_identities,
            state_key=state_key,
        ).value
    )
    assert isinstance(base, dict)
    journal_raw = _planned_prepared_runtime_journal_bytes(
        plan,
        transaction_id=runtime_admission.apply_attempt_id,
        state_key=state_key,
    )
    base.update(
        {
            "install_route": "prior_owner",
            "candidate_path": None,
            "candidate_parent_identity": None,
            "predecessor_candidate_identity": None,
            "successor_candidate_identity": None,
            "renamed_target_path": str(target),
            "predecessor_renamed_target_identity": target_identity,
            "successor_renamed_target_identity": target_identity,
            "predecessor_target_owner_journal_path": str(owner_path),
            "predecessor_target_owner_journal_identity": owner_identity,
            "predecessor_target_owner_journal_sha256": owner_sha256,
            "planned_journal_successor_size": len(journal_raw),
            "planned_journal_successor_sha256": (
                "sha256:" + hashlib.sha256(journal_raw).hexdigest()
            ),
        }
    )
    return RuntimeApplyRecoveryEvidence(
        _seal_apply_recovery_successor(base, changes={})
    )


def _validated_complete_layout_successor_identities(
    *,
    layout: Mapping[str, Any],
    runtime_root: Path,
) -> Mapping[str, PathIdentity]:
    rows = layout.get("directories")
    if not isinstance(rows, (list, tuple)) or len(rows) != len(
        RUNTIME_LAYOUT_DIRECTORY_ROLES
    ):
        raise ValueError("runtime_initial_install_layout_invalid")
    if not isinstance(rows[4], Mapping):
        raise ValueError("runtime_initial_install_layout_invalid")
    state_receipts_path = Path(str(rows[4].get("path")))
    if not _valid_component(state_receipts_path.name):
        raise ValueError("runtime_initial_install_layout_invalid")
    paths = _runtime_layout_paths(
        runtime_root,
        state_key=state_receipts_path.name,
    )
    if (
        layout.get("stage") != "COMPLETE"
        or layout.get("next_directory_index") != len(paths)
        or layout.get("directory_count") != len(paths)
        or len(rows) != len(paths)
    ):
        raise ValueError("runtime_initial_install_layout_invalid")
    identities: dict[str, PathIdentity] = {}
    for index, (role, path) in enumerate(
        zip(RUNTIME_LAYOUT_DIRECTORY_ROLES, paths, strict=True)
    ):
        row = rows[index]
        if not isinstance(row, Mapping):
            raise ValueError("runtime_initial_install_layout_invalid")
        successor = row.get("successor_identity")
        parent = row.get("expected_parent_identity")
        if role == "state_receipts":
            parent = rows[index - 1].get("successor_identity")
        if (
            row.get("role") != role
            or row.get("path") != str(path)
            or not isinstance(successor, (list, tuple))
            or not isinstance(parent, (list, tuple))
        ):
            raise ValueError("runtime_initial_install_layout_invalid")
        identity = tuple(successor)
        _require_runtime_layout_directory(
            path,
            expected_parent_identity=tuple(parent),
            expected_identity=identity,
            require_empty=False,
        )
        identities[role] = identity
    return MappingProxyType(identities)


def observe_initial_runtime_install_from_pair(
    plan: RuntimeInstallPlan,
    *,
    lease_pair: ControllerApplyLeasePair,
    observation_authorization: RuntimeObservationAuthorization,
    transaction_id: str,
    retention_owner_run_id: str,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
) -> RuntimeObservationReceipt:
    """Observe the exact empty New-Target attempt and mint its initial cursor."""

    if (
        type(plan) is not RuntimeInstallPlan
        or type(observation_authorization) is not RuntimeObservationAuthorization
        or type(runtime_admission) is not RuntimeLiveAttemptAdmissionEvidence
        or transaction_id != runtime_admission.apply_attempt_id
        or retention_owner_run_id != runtime_admission.retention_owner_run_id
    ):
        raise ValueError("runtime_initial_install_arguments_invalid")
    binding = _require_active_controller_apply_pair(lease_pair)
    persisted = load_live_start_session_under_lock(
        session_lease=binding.session_lease
    )
    _validate_controller_pair_session_provenance(binding=binding, persisted=persisted)
    _validate_leased_source(plan, lease_pair.package_lease)
    layout = persisted.runtime_layout_bootstrap
    bearer = _require_opaque_carrier(
        observation_authorization,
        carrier_type=RuntimeObservationAuthorization,
        family="runtime_observation:first_install",
        action=transaction_id,
        consume=False,
    )
    if (
        runtime_admission is not binding.runtime_admission
        or persisted.phase.value != "APPLY_STARTED"
        or persisted.apply_recovery is not None
        or not isinstance(layout, Mapping)
        or layout.get("stage") != "COMPLETE"
        or persisted.run_id != retention_owner_run_id
        or plan.runtime_root != runtime_admission.runtime_root
        or bearer.session_bearer is not binding.session_token._bearer
        or bearer.cursor_sha256 != persisted.content_sha256
    ):
        raise ValueError("runtime_initial_install_pair_mismatch")
    layout_identities = _validated_complete_layout_successor_identities(
        layout=layout,
        runtime_root=plan.runtime_root,
    )

    observed: _ExactPairedRuntimeAttemptObservation | None = None

    def observe() -> RuntimeObservationPostcondition:
        nonlocal observed
        observed = _observe_exact_paired_runtime_attempt(
            plan.runtime_root,
            transaction_id=transaction_id,
            expected_retention_owner_run_id=retention_owner_run_id,
            expected_package_root_sha256=runtime_admission.package_root_sha256,
            expected_deck_name=plan.deck_name,
            recovery_cursor=None,
        )
        candidate_path = plan.runtime_root / ".hsconfig" / "staging" / transaction_id
        target_path = plan.runtime_root / "CustomConfig" / plan.versioned_config_dir
        prior_owner: tuple[Path, RuntimeTransactionJournal, PathIdentity, str] | None = None
        if path_lexists(target_path):
            target_identity = path_identity(target_path)
            manifest, manifest_sha256 = _candidate_manifest_from_pair(
                package_lease=lease_pair.package_lease,
                deck_name=plan.deck_name,
            )
            entries = tuple(manifest["entries"])
            _verify_candidate_tree_prefix(
                root=target_path,
                root_identity=target_identity,
                expected_parent_identity=layout_identities["custom_config"],
                entries=entries,
                cursor=len(entries),
            )
            if not manifest_sha256:
                raise ValueError("runtime_initial_prior_owner_manifest_invalid")
            owners = [
                row
                for row in load_runtime_transaction_journals(plan.runtime_root)
                if row.transaction_id != transaction_id
                and row.phase == RuntimeTransactionPhase.FINALIZED
                and row.owns_target is True
                and row.target_path
                == target_path.relative_to(plan.runtime_root).as_posix()
                and row.target_identity == target_identity
                and row.package_root_sha256 == plan.package_root_sha256
            ]
            if len(owners) != 1:
                raise ValueError("runtime_initial_prior_owner_invalid")
            owner = owners[0]
            owner_path = runtime_transaction_journal_path(
                plan.runtime_root, owner.transaction_id
            )
            owner_raw, owner_identity = _read_exact_runtime_external_file(
                owner_path,
                expected_parent_identity=layout_identities["transactions"],
                maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
            )
            if parse_runtime_transaction_journal_bytes(
                owner_raw, expected_transaction_id=owner.transaction_id
            ) != owner:
                raise ValueError("runtime_initial_prior_owner_changed")
            prior_owner = (
                owner_path,
                owner,
                owner_identity,
                "sha256:" + hashlib.sha256(owner_raw).hexdigest(),
            )
        if (
            observed.retention is not None
            or observed.transaction.journal is not None
            or observed.transaction.controller_staging_path is not None
            or observed.transaction.legacy_temp_path is not None
            or path_lexists(candidate_path)
            or (path_lexists(target_path) and prior_owner is None)
        ):
            raise ValueError("runtime_initial_install_surfaces_not_absent")
        if prior_owner is None:
            recovery = _initial_new_target_apply_recovery(
                plan=plan,
                runtime_admission=runtime_admission,
                layout_identities=layout_identities,
                state_key=Path(str(layout["directories"][4]["path"])).name,
            )
        else:
            owner_path, _owner, owner_identity, owner_sha256 = prior_owner
            recovery = _initial_prior_owner_apply_recovery(
                plan=plan,
                runtime_admission=runtime_admission,
                layout_identities=layout_identities,
                state_key=Path(str(layout["directories"][4]["path"])).name,
                target_identity=target_identity,
                owner_path=owner_path,
                owner_identity=owner_identity,
                owner_sha256=owner_sha256,
            )
        return RuntimeObservationPostcondition(
            action=transaction_id,
            observation_family="first_install",
            evidence={"apply_recovery": recovery.value},
        )

    return _execute_runtime_observation(
        observation_authorization=observation_authorization,
        observation_family="first_install",
        read_only_observation=observe,
    )


def bootstrap_runtime_layout_directory_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    session_lease: LiveStartSessionLease,
    expected_layout_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    output_operation_lease: OutputOperationAdmissionLease,
    output_operation_admission: OutputOperationAdmissionEvidence,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    layout_authorization: RuntimeLayoutBootstrapAuthorization,
) -> RuntimeLayoutBootstrapStepReceipt:
    """Create or confirm exactly the current persisted layout row."""

    context = _validate_runtime_layout_pair_context(
        lease_pair=lease_pair,
        session_lease=session_lease,
        expected_layout_session=expected_layout_session,
        profile_lease=profile_lease,
        output_operation_lease=output_operation_lease,
        output_operation_admission=output_operation_admission,
        runtime_admission=runtime_admission,
        layout_authorization=layout_authorization,
    )
    _binding, pending, layout, current_index, paths = context
    current_row, current_parent_identity = (
        _validate_runtime_layout_physical_rows(
            layout=layout,
            current_index=current_index,
            paths=paths,
        )
    )
    current_path = paths[current_index]

    def perform() -> RuntimeLayoutBootstrapPhysicalPostcondition:
        refreshed = _validate_runtime_layout_pair_context(
            lease_pair=lease_pair,
            session_lease=session_lease,
            expected_layout_session=expected_layout_session,
            profile_lease=profile_lease,
            output_operation_lease=output_operation_lease,
            output_operation_admission=output_operation_admission,
            runtime_admission=runtime_admission,
            layout_authorization=layout_authorization,
            authorization_consumed=True,
        )
        _, refreshed_pending, refreshed_layout, refreshed_index, refreshed_paths = (
            refreshed
        )
        refreshed_row, refreshed_parent_identity = (
            _validate_runtime_layout_physical_rows(
                layout=refreshed_layout,
                current_index=refreshed_index,
                paths=refreshed_paths,
            )
        )
        if (
            refreshed_pending != pending
            or refreshed_layout != layout
            or refreshed_index != current_index
            or refreshed_paths != paths
            or refreshed_row != current_row
            or refreshed_parent_identity != current_parent_identity
        ):
            raise ValueError("runtime_layout_bootstrap_cursor_changed")
        if refreshed_row.get("predecessor_state") == "absent":
            if path_lexists(current_path):
                successor_identity = _require_runtime_layout_directory(
                    current_path,
                    expected_parent_identity=current_parent_identity,
                    expected_identity=None,
                    require_empty=True,
                )
            else:
                successor_identity = secure_create_directory(
                    current_path,
                    expected_parent_identity=current_parent_identity,
                )
                successor_identity = _require_runtime_layout_directory(
                    current_path,
                    expected_parent_identity=current_parent_identity,
                    expected_identity=successor_identity,
                    require_empty=True,
                )
        else:
            successor_identity = _require_runtime_layout_directory(
                current_path,
                expected_parent_identity=current_parent_identity,
                expected_identity=tuple(
                    refreshed_row["predecessor_identity"]
                ),
                require_empty=False,
            )
        successor = _plain_json_value(refreshed_layout)
        assert isinstance(successor, dict)
        successor.pop("content_sha256", None)
        successor_rows = successor["directories"]
        successor_row = successor_rows[current_index]
        if (
            successor_row["role"] == "state_receipts"
            and successor_row["expected_parent_identity"] is None
        ):
            successor_row["expected_parent_identity"] = list(
                current_parent_identity
            )
        successor_row["successor_identity"] = list(successor_identity)
        successor["next_directory_index"] = current_index + 1
        complete = current_index + 1 == len(paths)
        successor["stage"] = "COMPLETE" if complete else "INCOMPLETE"
        sealed_successor = seal_embedded_document(
            "runtime_layout_bootstrap",
            successor,
        )
        evidence: dict[str, Any] = {
            "runtime_layout_bootstrap": sealed_successor,
            "directory_path": str(current_path),
            "directory_parent_identity": list(current_parent_identity),
            "directory_identity": list(successor_identity),
        }
        if complete:
            invocation_size = refreshed_pending.get(
                "apply_invocation_document_size"
            )
            successor_bindings = refreshed_pending.get(
                "successor_artifact_bindings"
            )
            invocation_sha256 = (
                successor_bindings.get("receipts/apply_invocation.json")
                if isinstance(successor_bindings, Mapping)
                else None
            )
            if (
                type(invocation_size) is not int
                or not 1 <= invocation_size <= APPLY_INVOCATION_MAX_BYTES
                or not isinstance(invocation_sha256, str)
                or _PREFIXED_SHA256.fullmatch(invocation_sha256) is None
            ):
                raise ValueError(
                    "runtime_layout_bootstrap_invocation_binding_invalid"
                )
            receipt_path = (
                session_lease.session_root
                / "receipts"
                / "apply_invocation.json"
            )
            receipt_parent_identity = path_identity(receipt_path.parent)
            _require_layout_parent_identity(
                receipt_path.parent,
                expected_identity=receipt_parent_identity,
            )
            receipt_staging_path = receipt_path.with_name(
                f"{receipt_path.name}.staged"
            )
            receipt_inner_temp_path = receipt_staging_path.with_name(
                f".{receipt_staging_path.name}.live-start-atomic.tmp"
            )
            evidence["invocation_receipt_file_action"] = (
                _build_external_file_action(
                    action_kind="materialize_invocation_receipt_staging",
                    action_index=0,
                    final_path=receipt_path,
                    staging_path=receipt_staging_path,
                    inner_temp_path=receipt_inner_temp_path,
                    parent_identity=receipt_parent_identity,
                    predecessor_identity=None,
                    predecessor_size=None,
                    predecessor_sha256=None,
                    planned_successor_size=invocation_size,
                    planned_successor_sha256=invocation_sha256,
                    commit_mode="create_no_replace",
                )
            )
        return RuntimeLayoutBootstrapPhysicalPostcondition(
            action="create_or_confirm_runtime_layout_directory",
            evidence=evidence,
        )

    return _execute_runtime_layout_bootstrap_physical_step(
        layout_authorization=layout_authorization,
        action="create_or_confirm_runtime_layout_directory",
        physical_action=perform,
    )


def _plain_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _plain_json_value(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return [_plain_json_value(item) for item in value]
    if isinstance(value, list):
        return [_plain_json_value(item) for item in value]
    return value


def _seal_apply_recovery_successor(
    recovery: Mapping[str, Any],
    *,
    changes: Mapping[str, Any],
) -> Mapping[str, Any]:
    value = _plain_json_value(recovery)
    if not isinstance(value, dict):
        raise ValueError("runtime_apply_recovery_cursor_invalid")
    value.pop("content_sha256", None)
    value.update(_plain_json_value(changes))
    raw = (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    value["content_sha256"] = "sha256:" + hashlib.sha256(raw).hexdigest()
    return RuntimeApplyRecoveryEvidence(value).value


def _observe_exact_runtime_transaction_store(
    runtime_root: Path,
    *,
    transaction_id: str,
    external_file_action: Mapping[str, Any] | None,
) -> _ExactRuntimeTransactionObservation:
    """Boundedly observe one transaction family without store mutation."""

    root = Path(runtime_root)
    final_path = runtime_transaction_journal_path(root, transaction_id)
    transactions = final_path.parent
    if not path_lexists(transactions):
        if path_lexists(final_path):
            raise ValueError("runtime_transaction_store_invalid")
        return _ExactRuntimeTransactionObservation(
            final_path,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
    transactions_guard = capture_plain_ancestor_guard(transactions)
    require_plain_directory(transactions)
    transactions_status = transactions.lstat()
    require_same_identity_resolution(
        transactions,
        expected_status=transactions_status,
    )
    parent_identity = path_identity_from_status(transactions_status)
    transactions_parent_identity = path_identity(transactions.parent)
    require_no_alternate_data_streams(
        transactions,
        expected_identity=parent_identity,
        expected_parent_identity=transactions_parent_identity,
        directory=True,
    )
    transactions_guard.validate()

    journal: RuntimeTransactionJournal | None = None
    journal_identity: PathIdentity | None = None
    journal_size: int | None = None
    journal_sha256: str | None = None
    if path_lexists(final_path):
        final_raw, journal_identity = _read_exact_runtime_external_file(
            final_path,
            expected_parent_identity=parent_identity,
            maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
        )
        journal = parse_runtime_transaction_journal_bytes(
            final_raw,
            expected_transaction_id=transaction_id,
        )
        journal_size = len(final_raw)
        journal_sha256 = "sha256:" + hashlib.sha256(final_raw).hexdigest()

    controller_path: Path | None = None
    controller_identity: PathIdentity | None = None
    controller_size: int | None = None
    controller_sha256: str | None = None
    expected_controller_staging = final_path.with_name(
        f"{final_path.name}.staged"
    )
    expected_controller_inner = expected_controller_staging.with_name(
        f".{expected_controller_staging.name}.live-start-atomic.tmp"
    )
    if external_file_action is not None:
        if not isinstance(external_file_action, Mapping):
            raise ValueError("runtime_controller_file_action_invalid")
        if (
            Path(str(external_file_action.get("final_path"))) != final_path
            or Path(str(external_file_action.get("staging_path")))
            != expected_controller_staging
            or Path(str(external_file_action.get("inner_temp_path")))
            != expected_controller_inner
            or tuple(external_file_action.get("parent_identity", ()))
            != parent_identity
                or external_file_action.get("action_kind")
                    not in {
                        "materialize_file_action_staging",
                        "advance_controller_transaction_journal_write",
                        "bind_renamed_target",
                        "commit_ini_journal",
                        "commit_state_journal",
                        "finalize_journal",
                    }
        ):
            raise ValueError("runtime_controller_file_action_invalid")
        if path_lexists(expected_controller_inner) and not (
            external_file_action.get("stage") == "PLANNED"
            and external_file_action.get("action_kind")
            == "materialize_file_action_staging"
        ):
            raise ValueError("runtime_controller_file_action_incomplete")
        if path_lexists(expected_controller_staging):
            controller_raw, controller_identity = (
                _read_exact_runtime_external_file(
                    expected_controller_staging,
                    expected_parent_identity=parent_identity,
                    maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
                )
            )
            parse_runtime_transaction_journal_bytes(
                controller_raw,
                expected_transaction_id=transaction_id,
            )
            controller_size = len(controller_raw)
            controller_sha256 = (
                "sha256:" + hashlib.sha256(controller_raw).hexdigest()
            )
            if (
                controller_size
                != external_file_action.get("planned_successor_size")
                or controller_sha256
                != external_file_action.get("planned_successor_sha256")
            ):
                raise ValueError("runtime_controller_file_action_changed")
            controller_path = expected_controller_staging
    elif path_lexists(expected_controller_staging) or path_lexists(
        expected_controller_inner
    ):
        raise ValueError("runtime_controller_file_action_unbound")

    legacy_rows: list[Path] = []
    with os.scandir(transactions) as iterator:
        for index, entry in enumerate(iterator):
            if index >= MAX_RUNTIME_TRANSACTION_FILES:
                raise ValueError("runtime_transaction_store_bounds")
            match = _LEGACY_UUID_TRANSACTION_TEMP.fullmatch(entry.name)
            if match is not None and match.group("transaction") == transaction_id:
                legacy_rows.append(Path(entry.path))
    if len(legacy_rows) > 1 or (legacy_rows and controller_path is not None):
        raise ValueError("runtime_transaction_store_ambiguous")

    legacy_path: Path | None = None
    legacy_identity: PathIdentity | None = None
    legacy_size: int | None = None
    legacy_sha256: str | None = None
    legacy_classification: str | None = None
    if legacy_rows:
        legacy_path = legacy_rows[0]
        legacy_raw, legacy_identity = _read_exact_runtime_external_file(
            legacy_path,
            expected_parent_identity=parent_identity,
            maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
        )
        legacy_journal = parse_runtime_transaction_journal_bytes(
            legacy_raw,
            expected_transaction_id=transaction_id,
        )
        legacy_size = len(legacy_raw)
        legacy_sha256 = "sha256:" + hashlib.sha256(legacy_raw).hexdigest()
        if journal is None:
            if (
                legacy_journal.phase != RuntimeTransactionPhase.PREPARED
                or legacy_journal.candidate_identity is not None
                or legacy_journal.target_identity is not None
            ):
                raise ValueError("runtime_transaction_temp_incomplete")
            legacy_classification = "legacy_complete_valid"
        elif legacy_journal == journal:
            legacy_classification = "legacy_redundant_equal"
        elif _is_monotonic_successor(journal, legacy_journal):
            legacy_classification = "legacy_monotone_successor"
        else:
            legacy_classification = "legacy_partial_invalid"

    require_plain_directory(transactions)
    require_same_identity_resolution(
        transactions,
        expected_status=transactions_status,
    )
    if (
        path_identity(transactions) != parent_identity
        or path_identity(transactions.parent) != transactions_parent_identity
    ):
        raise ValueError("runtime_transaction_store_changed")
    require_no_alternate_data_streams(
        transactions,
        expected_identity=parent_identity,
        expected_parent_identity=transactions_parent_identity,
        directory=True,
    )
    transactions_guard.validate()

    return _ExactRuntimeTransactionObservation(
        journal_path=final_path,
        journal=journal,
        journal_identity=journal_identity,
        journal_size=journal_size,
        journal_sha256=journal_sha256,
        controller_staging_path=controller_path,
        controller_staging_identity=controller_identity,
        controller_staging_size=controller_size,
        controller_staging_sha256=controller_sha256,
        legacy_temp_path=legacy_path,
        legacy_temp_parent_identity=(
            parent_identity if legacy_path is not None else None
        ),
        legacy_temp_identity=legacy_identity,
        legacy_temp_size=legacy_size,
        legacy_temp_sha256=legacy_sha256,
        legacy_temp_classification=legacy_classification,
        legacy_temp_origin=("legacy_uuid" if legacy_path is not None else None),
    )


def _execute_bound_legacy_uuid_temp_action(
    *,
    recovery: Mapping[str, Any],
    action: Literal[
        "promote_legacy_uuid_transaction_temp",
        "retire_legacy_uuid_transaction_temp",
    ],
) -> RuntimeApplyRecoveryPhysicalPostcondition:
    """Mutate or confirm only the exact legacy UUID temp bound by recovery."""

    if action not in {
        "promote_legacy_uuid_transaction_temp",
        "retire_legacy_uuid_transaction_temp",
    }:
        raise ValueError("runtime_legacy_temp_action_invalid")
    prefix = "predecessor_transaction_temp"
    path_value = recovery.get(f"{prefix}_path")
    parent_value = recovery.get(f"{prefix}_parent_identity")
    identity_value = recovery.get(f"{prefix}_identity")
    expected_size = recovery.get(f"{prefix}_size")
    expected_sha256 = recovery.get(f"{prefix}_sha256")
    classification = recovery.get(f"{prefix}_classification")
    if (
        not isinstance(path_value, str)
        or not isinstance(parent_value, (list, tuple))
        or not isinstance(identity_value, (list, tuple))
        or type(expected_size) is not int
        or not isinstance(expected_sha256, str)
        or recovery.get(f"{prefix}_origin") != "legacy_uuid"
        or _LEGACY_UUID_TEMP_ACTION_BY_CLASSIFICATION.get(classification)
        != action
    ):
        raise ValueError("runtime_legacy_temp_authority_invalid")
    temp_path = Path(path_value)
    match = _LEGACY_UUID_TRANSACTION_TEMP.fullmatch(temp_path.name)
    parent_identity = tuple(parent_value)
    temp_identity = tuple(identity_value)
    if (
        match is None
        or not temp_path.is_absolute()
        or path_identity(temp_path.parent) != parent_identity
    ):
        raise ValueError("runtime_legacy_temp_authority_invalid")
    transaction_id = match.group("transaction")
    final_path = temp_path.parent / f"{transaction_id}.json"
    matching_temps: list[Path] = []
    with os.scandir(temp_path.parent) as iterator:
        for index, entry in enumerate(iterator):
            if index >= MAX_RUNTIME_TRANSACTION_FILES:
                raise ValueError("runtime_legacy_temp_store_bounds")
            sibling_match = _LEGACY_UUID_TRANSACTION_TEMP.fullmatch(
                entry.name
            )
            if (
                sibling_match is not None
                and sibling_match.group("transaction") == transaction_id
            ):
                matching_temps.append(Path(entry.path))
    if len(matching_temps) > 1 or (
        matching_temps and matching_temps[0] != temp_path
    ):
        raise ValueError("runtime_legacy_temp_store_ambiguous")

    temp_present = bool(matching_temps)
    if temp_present:
        raw, observed_identity = _read_exact_runtime_external_file(
            temp_path,
            expected_parent_identity=parent_identity,
            maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
        )
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        if (
            observed_identity != temp_identity
            or len(raw) != expected_size
            or digest != expected_sha256
        ):
            raise ValueError("runtime_legacy_temp_changed")
        candidate = parse_runtime_transaction_journal_bytes(
            raw,
            expected_transaction_id=transaction_id,
        )
    else:
        raw = b""
        digest = expected_sha256
        candidate = None

    predecessor: RuntimeTransactionJournal | None = None
    predecessor_identity: PathIdentity | None = None
    if classification != "legacy_complete_valid" or not temp_present:
        final_raw, predecessor_identity = _read_exact_runtime_external_file(
            final_path,
            expected_parent_identity=parent_identity,
            maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
        )
        final_digest = "sha256:" + hashlib.sha256(final_raw).hexdigest()
        predecessor = parse_runtime_transaction_journal_bytes(
            final_raw,
            expected_transaction_id=transaction_id,
        )
        if temp_present:
            predecessor_path_value = recovery.get(
                "predecessor_journal_path"
            )
            predecessor_identity_value = recovery.get(
                "predecessor_journal_identity"
            )
            predecessor_sha256 = recovery.get(
                "predecessor_journal_sha256"
            )
            if (
                predecessor_path_value != str(final_path)
                or not isinstance(
                    predecessor_identity_value,
                    (list, tuple),
                )
                or tuple(predecessor_identity_value)
                != predecessor_identity
                or predecessor_sha256 != final_digest
            ):
                raise ValueError(
                    "runtime_legacy_temp_predecessor_changed"
                )
        elif action == "promote_legacy_uuid_transaction_temp" and (
            predecessor_identity != temp_identity
            or len(final_raw) != expected_size
            or final_digest != expected_sha256
        ):
            raise ValueError("runtime_legacy_temp_promotion_changed")
        elif action == "retire_legacy_uuid_transaction_temp":
            predecessor_path_value = recovery.get(
                "predecessor_journal_path"
            )
            predecessor_identity_value = recovery.get(
                "predecessor_journal_identity"
            )
            if (
                predecessor_path_value != str(final_path)
                or not isinstance(
                    predecessor_identity_value,
                    (list, tuple),
                )
                or tuple(predecessor_identity_value)
                != predecessor_identity
                or recovery.get("predecessor_journal_sha256")
                != final_digest
            ):
                raise ValueError(
                    "runtime_legacy_temp_predecessor_changed"
                )

    if action == "promote_legacy_uuid_transaction_temp":
        if not temp_present:
            final_identity = predecessor_identity
        elif classification == "legacy_complete_valid":
            if path_lexists(final_path):
                raise ValueError("runtime_legacy_temp_final_changed")
            secure_replace(
                temp_path,
                final_path,
                expected_source_identity=temp_identity,
                expected_source_parent_identity=parent_identity,
                expected_target_parent_identity=parent_identity,
                expected_target_absent=True,
            )
        else:
            if (
                predecessor is None
                or candidate is None
                or not _is_monotonic_successor(predecessor, candidate)
            ):
                raise ValueError("runtime_legacy_temp_successor_changed")
            secure_replace(
                temp_path,
                final_path,
                expected_source_identity=temp_identity,
                expected_source_parent_identity=parent_identity,
                expected_target_parent_identity=parent_identity,
                expected_target_identity=predecessor_identity,
            )
        final_raw, final_identity = _read_exact_runtime_external_file(
            final_path,
            expected_parent_identity=parent_identity,
            maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
        )
        if (
            (temp_present and final_raw != raw)
            or len(final_raw) != expected_size
            or "sha256:" + hashlib.sha256(final_raw).hexdigest()
            != expected_sha256
            or path_lexists(temp_path)
        ):
            raise ValueError("runtime_legacy_temp_promotion_changed")
        successor_changes: dict[str, Any] = {
            "successor_journal_path": str(final_path),
            "successor_journal_identity": final_identity,
            "successor_journal_sha256": digest,
        }
    else:
        if temp_present:
            if (
                predecessor is None
                or candidate is None
                or (
                    classification == "legacy_redundant_equal"
                    and candidate != predecessor
                )
                or (
                    classification == "legacy_partial_invalid"
                    and (
                        candidate == predecessor
                        or _is_monotonic_successor(
                            predecessor,
                            candidate,
                        )
                    )
                )
            ):
                raise ValueError(
                    "runtime_legacy_temp_classification_changed"
                )
            secure_unlink(
                temp_path,
                expected_identity=temp_identity,
                expected_parent_identity=parent_identity,
                missing_ok=False,
            )
        if path_lexists(temp_path):
            raise ValueError("runtime_legacy_temp_retirement_changed")
        successor_changes = {}

    for field_name in (
        "path",
        "parent_identity",
        "identity",
        "size",
        "sha256",
        "classification",
        "origin",
    ):
        successor_changes[f"successor_transaction_temp_{field_name}"] = None
    successor_changes.update(
        {
            "action_index": int(recovery.get("action_index")) + 1,
            "expected_action": (
                "observe_committed"
                if (
                    candidate is not None
                    and candidate.phase == RuntimeTransactionPhase.FINALIZED
                )
                or (
                    candidate is None
                    and predecessor is not None
                    and predecessor.phase
                    == RuntimeTransactionPhase.FINALIZED
                )
                else (
                    "bind_created_candidate"
                    if recovery.get("install_route") == "new_target"
                    else "write_deck_config_ini"
                )
            ),
            "external_file_action": None,
        }
    )
    successor = _seal_apply_recovery_successor(
        recovery,
        changes=successor_changes,
    )
    return RuntimeApplyRecoveryPhysicalPostcondition(
        action=action,
        evidence={"apply_recovery": successor},
    )


def _execute_bound_controller_journal_action(
    *,
    external_file_action: Mapping[str, Any],
    transaction_id: str,
) -> _ExactRuntimeTransactionObservation:
    """Commit or confirm exactly one identity-bound controller v1 staging."""

    if not isinstance(external_file_action, Mapping):
        raise TypeError("runtime_controller_journal_action_invalid")
    if not isinstance(transaction_id, str) or _ATTEMPT_ID.fullmatch(
        transaction_id
    ) is None:
        raise ValueError("runtime_controller_journal_transaction_invalid")
    final_path = Path(str(external_file_action.get("final_path")))
    if (
        not final_path.is_absolute()
        or final_path.name != f"{transaction_id}.json"
    ):
        raise ValueError("runtime_controller_journal_path_invalid")
    staging_path = final_path.with_name(f"{final_path.name}.staged")
    inner_temp_path = staging_path.with_name(
        f".{staging_path.name}.live-start-atomic.tmp"
    )
    parent_identity = tuple(external_file_action.get("parent_identity", ()))
    if (
        external_file_action.get("stage") != "STAGING_BOUND"
        or external_file_action.get("action_kind")
        not in {
            "advance_controller_transaction_journal_write",
            "bind_renamed_target",
            "commit_ini_journal",
            "commit_state_journal",
            "finalize_journal",
        }
        or Path(str(external_file_action.get("final_path"))) != final_path
        or Path(str(external_file_action.get("staging_path"))) != staging_path
        or Path(str(external_file_action.get("inner_temp_path")))
        != inner_temp_path
        or len(parent_identity) != 3
        or path_identity(final_path.parent) != parent_identity
    ):
        raise ValueError("runtime_controller_journal_staging_bound_invalid")
    staging_identity = tuple(
        external_file_action.get("staging_identity", ())
    )
    staging_size = external_file_action.get("staging_size")
    staging_sha256 = external_file_action.get("staging_sha256")
    if (
        len(staging_identity) != 3
        or type(staging_size) is not int
        or not isinstance(staging_sha256, str)
        or staging_size
        != external_file_action.get("planned_successor_size")
        or staging_sha256
        != external_file_action.get("planned_successor_sha256")
    ):
        raise ValueError("runtime_controller_journal_staging_bound_invalid")
    if path_lexists(inner_temp_path):
        raise ValueError("runtime_controller_journal_inner_temp_present")

    mode = external_file_action.get("commit_mode")
    if mode == "create_no_replace":
        committed = atomic_commit_bound_staging_no_replace(
            path=final_path,
            staging_path=staging_path,
            expected_staging_identity=staging_identity,
            expected_size=staging_size,
            expected_sha256=staging_sha256,
            expected_parent_identity=parent_identity,
        )
    elif mode == "replace_exact":
        predecessor_identity = tuple(
            external_file_action.get("predecessor_identity", ())
        )
        if len(predecessor_identity) != 3:
            raise ValueError("runtime_controller_journal_predecessor_invalid")
        committed = atomic_commit_bound_staging_replace(
            path=final_path,
            staging_path=staging_path,
            expected_predecessor_identity=predecessor_identity,
            expected_staging_identity=staging_identity,
            expected_size=staging_size,
            expected_sha256=staging_sha256,
            expected_parent_identity=parent_identity,
        )
    else:
        raise ValueError("runtime_controller_journal_commit_mode_invalid")
    raw, observed_identity = _read_exact_runtime_external_file(
        final_path,
        expected_parent_identity=parent_identity,
        maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
    )
    journal = parse_runtime_transaction_journal_bytes(
        raw,
        expected_transaction_id=transaction_id,
    )
    if (
        observed_identity != committed.identity
        or observed_identity != staging_identity
        or len(raw) != staging_size
        or "sha256:" + hashlib.sha256(raw).hexdigest() != staging_sha256
        or path_lexists(staging_path)
        or path_lexists(inner_temp_path)
    ):
        raise ValueError("runtime_controller_journal_commit_changed")
    return _ExactRuntimeTransactionObservation(
        journal_path=final_path,
        journal=journal,
        journal_identity=observed_identity,
        journal_size=len(raw),
        journal_sha256=staging_sha256,
        controller_staging_path=None,
        controller_staging_identity=None,
        controller_staging_size=None,
        controller_staging_sha256=None,
        legacy_temp_path=None,
        legacy_temp_parent_identity=None,
        legacy_temp_identity=None,
        legacy_temp_size=None,
        legacy_temp_sha256=None,
        legacy_temp_classification=None,
        legacy_temp_origin=None,
    )


def _legacy_uuid_temp_evidence(
    *,
    observation: _ExactRuntimeTransactionObservation,
    family: RuntimeRecoveryObservationFamily,
) -> Mapping[str, Any]:
    """Export the same closed legacy-temp septuple to either recovery family."""

    if family not in {"nonterminal_apply", "terminal_resolution"}:
        raise ValueError("runtime_recovery_observation_family_invalid")
    values = (
        observation.legacy_temp_path,
        observation.legacy_temp_parent_identity,
        observation.legacy_temp_identity,
        observation.legacy_temp_size,
        observation.legacy_temp_sha256,
        observation.legacy_temp_classification,
        observation.legacy_temp_origin,
    )
    if all(value is None for value in values):
        return MappingProxyType(
            {
                "predecessor_transaction_temp_path": None,
                "predecessor_transaction_temp_parent_identity": None,
                "predecessor_transaction_temp_identity": None,
                "predecessor_transaction_temp_size": None,
                "predecessor_transaction_temp_sha256": None,
                "predecessor_transaction_temp_classification": None,
                "predecessor_transaction_temp_origin": None,
            }
        )
    if any(value is None for value in values):
        raise ValueError("runtime_legacy_temp_evidence_incomplete")
    return MappingProxyType(
        {
            "predecessor_transaction_temp_path": str(
                observation.legacy_temp_path
            ),
            "predecessor_transaction_temp_parent_identity": (
                observation.legacy_temp_parent_identity
            ),
            "predecessor_transaction_temp_identity": (
                observation.legacy_temp_identity
            ),
            "predecessor_transaction_temp_size": (
                observation.legacy_temp_size
            ),
            "predecessor_transaction_temp_sha256": (
                observation.legacy_temp_sha256
            ),
            "predecessor_transaction_temp_classification": (
                observation.legacy_temp_classification
            ),
            "predecessor_transaction_temp_origin": (
                observation.legacy_temp_origin
            ),
        }
    )


def _controller_transaction_external_action(
    value: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    external = value.get("external_file_action")
    if (
        isinstance(external, Mapping)
        and (
            external.get("action_kind")
            in {
                "advance_controller_transaction_journal_write",
                "bind_renamed_target",
                "commit_ini_journal",
                "commit_state_journal",
                "finalize_journal",
            }
            or (
                external.get("action_kind")
                == "materialize_file_action_staging"
                and external.get("final_path")
                == value.get("successor_journal_path")
            )
        )
    ):
        return external
    return None


def _validate_exact_paired_retention_projection(
    runtime_root: Path,
    *,
    observed: _ObservedRuntimeAttemptRetention,
    transaction: _ExactRuntimeTransactionObservation,
    action_bound_candidate_identity: PathIdentity | None = None,
    allow_unbound_empty_candidate: bool = False,
    recovery_journal_triplet: tuple[str, PathIdentity, str] | None = None,
    action_bound_target: tuple[Path, PathIdentity] | None = None,
    recovery_cursor: Mapping[str, Any] | None = None,
    layout_identities: Mapping[str, PathIdentity] | None = None,
    tolerate_bounded_authority_contradiction: bool = False,
) -> _BoundedRuntimeAuthorityContradiction | None:
    record = observed.record
    journal = transaction.journal
    if tolerate_bounded_authority_contradiction:
        if (
            not isinstance(layout_identities, Mapping)
            or any(
                not _valid_path_identity(layout_identities.get(name))
                for name in ("staging", "custom_config", "transactions")
            )
        ):
            raise ValueError("runtime_bounded_authority_layout_missing")
        staging_parent_identity = layout_identities["staging"]
        custom_config_parent_identity = layout_identities["custom_config"]
        transactions_parent_identity = layout_identities["transactions"]
    else:
        staging_parent_identity = None
        custom_config_parent_identity = None
        transactions_parent_identity = None
    markers: list[_BoundedRuntimeAuthorityContradiction] = []

    def record_marker(
        value: _BoundedRuntimeAuthorityContradiction | None,
    ) -> bool:
        if value is None:
            return False
        markers.append(value)
        return True
    if record.state == "ACTIVE":
        if journal is not None or transaction.legacy_temp_path is not None:
            raise ValueError(
                "runtime_attempt_retention_active_projection_invalid"
            )
        return None
    if (
        record.planned_journal_path != transaction.journal_path
        or record.planned_journal_size is None
        or record.planned_journal_sha256 is None
    ):
        raise ValueError("runtime_attempt_retention_planned_journal_missing")
    if journal is not None:
        recovery_journal_matches = recovery_journal_triplet == (
            str(transaction.journal_path),
            transaction.journal_identity,
            transaction.journal_sha256,
        )
        if (
            (
                not recovery_journal_matches
                and (
                    transaction.journal_size != record.planned_journal_size
                    or transaction.journal_sha256
                    != record.planned_journal_sha256
                )
            )
            or record.package_root_sha256
            != "sha256:" + journal.package_root_sha256
        ):
            raise ValueError("runtime_attempt_retention_journal_mismatch")
        if record.journal_path is not None and not recovery_journal_matches and (
            record.journal_path != transaction.journal_path
            or record.journal_identity != transaction.journal_identity
            or record.journal_sha256 != transaction.journal_sha256
        ):
            raise ValueError("runtime_attempt_retention_journal_mismatch")
    elif record.journal_path is not None:
        raise ValueError("runtime_attempt_retention_journal_missing")

    if record.candidate_path is not None:
        expected_candidate_path = (
            runtime_root
            / ".hsconfig"
            / "staging"
            / record.apply_attempt_id
        )
        if record.candidate_path != expected_candidate_path:
            raise ValueError("runtime_attempt_retention_candidate_path_invalid")
        candidate_parent_identity = (
            staging_parent_identity
            if tolerate_bounded_authority_contradiction
            else record.candidate_parent_identity
        )
        if (
            candidate_parent_identity is None
            or record.candidate_parent_identity is None
            or (
                tolerate_bounded_authority_contradiction
                and record.candidate_parent_identity
                != candidate_parent_identity
            )
        ):
            raise ValueError("runtime_attempt_retention_candidate_parent_missing")
        candidate_target_path = (
            action_bound_target[0]
            if action_bound_target is not None
            else None
        )
        candidate_target_identity = (
            action_bound_target[1]
            if action_bound_target is not None
            else None
        )
        if (
            tolerate_bounded_authority_contradiction
            and isinstance(recovery_cursor, Mapping)
            and recovery_cursor.get("install_route") == "new_target"
        ):
            recovered_target_path = Path(
                str(recovery_cursor.get("renamed_target_path"))
            )
            if (
                candidate_target_path is not None
                and candidate_target_path != recovered_target_path
            ):
                raise ValueError("runtime_attempt_retention_target_path_invalid")
            candidate_target_path = recovered_target_path
        if record.candidate_identity is None:
            if action_bound_candidate_identity is None and not (
                allow_unbound_empty_candidate
                and path_lexists(record.candidate_path)
            ):
                _require_retained_child_absent(
                    record.candidate_path,
                    expected_parent_identity=candidate_parent_identity,
                )
            else:
                _require_runtime_layout_directory(
                    record.candidate_path,
                    expected_parent_identity=candidate_parent_identity,
                    expected_identity=action_bound_candidate_identity,
                    require_empty=True,
                )
        else:
            if path_lexists(record.candidate_path):
                candidate_marker = (
                    _bounded_directory_authority_contradiction(
                        path=record.candidate_path,
                        expected_identity=record.candidate_identity,
                        expected_parent_identity=candidate_parent_identity,
                        surface="candidate_root",
                    )
                    if tolerate_bounded_authority_contradiction
                    and isinstance(recovery_cursor, Mapping)
                    and recovery_cursor.get("install_route") == "new_target"
                    else None
                )
                if not record_marker(candidate_marker):
                    _observe_retained_directory(
                        record.candidate_path,
                        expected_identity=record.candidate_identity,
                        expected_parent_identity=candidate_parent_identity,
                    )
                if candidate_target_path is not None:
                    target_path = candidate_target_path
                    target_parent_identity = (
                        custom_config_parent_identity
                        if tolerate_bounded_authority_contradiction
                        else path_identity(target_path.parent)
                    )
                    if (
                        target_path.parent != runtime_root / "CustomConfig"
                        or (
                            tolerate_bounded_authority_contradiction
                            and target_parent_identity
                            != custom_config_parent_identity
                        )
                    ):
                        raise ValueError(
                            "runtime_attempt_retention_target_path_invalid"
                        )
                    _require_retained_child_absent(
                        target_path,
                        expected_parent_identity=target_parent_identity,
                    )
            elif candidate_target_path is not None:
                target_path = candidate_target_path
                target_identity = candidate_target_identity
                if target_path.parent != runtime_root / "CustomConfig":
                    raise ValueError("runtime_attempt_retention_target_path_invalid")
                target_parent_identity = (
                    custom_config_parent_identity
                    if tolerate_bounded_authority_contradiction
                    else path_identity(target_path.parent)
                )
                if (
                    tolerate_bounded_authority_contradiction
                    and (
                        not path_lexists(target_path.parent)
                        or path_identity(target_path.parent)
                        != custom_config_parent_identity
                    )
                ):
                    raise ValueError("runtime_bounded_authority_parent_changed")
                if path_lexists(target_path):
                    if target_identity != record.candidate_identity:
                        raise ValueError(
                            "runtime_attempt_retention_candidate_replaced"
                        )
                    _observe_retained_directory(
                        target_path,
                        expected_identity=target_identity,
                        expected_parent_identity=target_parent_identity,
                    )
                else:
                    _require_retained_child_absent(
                        target_path,
                        expected_parent_identity=target_parent_identity,
                    )
                    candidate_marker = (
                        _bounded_directory_authority_contradiction(
                            path=record.candidate_path,
                            expected_identity=record.candidate_identity,
                            expected_parent_identity=candidate_parent_identity,
                            surface="candidate_root",
                        )
                        if tolerate_bounded_authority_contradiction
                        and isinstance(recovery_cursor, Mapping)
                        and recovery_cursor.get("install_route") == "new_target"
                        else None
                    )
                    if not record_marker(candidate_marker):
                        raise ValueError(
                            "runtime_attempt_retention_candidate_missing"
                        )
            else:
                candidate_marker = (
                    _bounded_directory_authority_contradiction(
                        path=record.candidate_path,
                        expected_identity=record.candidate_identity,
                        expected_parent_identity=candidate_parent_identity,
                        surface="candidate_root",
                    )
                    if tolerate_bounded_authority_contradiction
                    and isinstance(recovery_cursor, Mapping)
                    and recovery_cursor.get("install_route") == "new_target"
                    else None
                )
                if not record_marker(candidate_marker):
                    raise ValueError("runtime_attempt_retention_candidate_missing")
    if record.target_path is not None:
        if record.target_identity is None:
            raise ValueError(
                "runtime_attempt_retention_target_identity_missing"
            )
        if record.target_path.parent != runtime_root / "CustomConfig":
            raise ValueError("runtime_attempt_retention_target_path_invalid")
        if (
            tolerate_bounded_authority_contradiction
            and isinstance(recovery_cursor, Mapping)
            and recovery_cursor.get("install_route") == "prior_owner"
            and record.target_path
            != Path(str(recovery_cursor.get("renamed_target_path")))
        ):
            raise ValueError("runtime_attempt_retention_target_path_invalid")
        target_marker = (
            _bounded_directory_authority_contradiction(
                path=record.target_path,
                expected_identity=record.target_identity,
                expected_parent_identity=(
                    custom_config_parent_identity
                    if tolerate_bounded_authority_contradiction
                    else path_identity(record.target_path.parent)
                ),
                surface="prior_owner_target",
            )
            if tolerate_bounded_authority_contradiction
            and isinstance(recovery_cursor, Mapping)
            and recovery_cursor.get("install_route") == "prior_owner"
            else None
        )
        if not record_marker(target_marker):
            _observe_retained_directory(
                record.target_path,
                expected_identity=record.target_identity,
                expected_parent_identity=(
                    custom_config_parent_identity
                    if tolerate_bounded_authority_contradiction
                    else None
                ),
            )
    if record.target_owner_journal_path is not None:
        owner_id = record.target_owner_journal_path.stem
        expected_owner_path = runtime_transaction_journal_path(
            runtime_root,
            owner_id,
        )
        if record.target_owner_journal_path != expected_owner_path:
            raise ValueError("runtime_attempt_retention_owner_path_invalid")
        if (
            tolerate_bounded_authority_contradiction
            and isinstance(recovery_cursor, Mapping)
            and recovery_cursor.get("install_route") == "prior_owner"
            and record.target_owner_journal_path
            != Path(
                str(
                    recovery_cursor.get(
                        "predecessor_target_owner_journal_path"
                    )
                )
            )
        ):
            raise ValueError("runtime_attempt_retention_owner_path_invalid")
        owner_marker = None
        owner: RuntimeTransactionJournal | None
        identity: PathIdentity | None
        digest: str | None
        if (
            tolerate_bounded_authority_contradiction
            and isinstance(recovery_cursor, Mapping)
            and recovery_cursor.get("install_route") == "prior_owner"
        ):
            owner_parent_identity = transactions_parent_identity
            if owner_parent_identity is None:
                raise ValueError("runtime_bounded_authority_layout_missing")
            require_plain_directory(record.target_owner_journal_path.parent)
            if (
                path_identity(record.target_owner_journal_path.parent)
                != owner_parent_identity
            ):
                raise ValueError("runtime_bounded_authority_parent_changed")
            if not path_lexists(record.target_owner_journal_path):
                owner_marker = _BoundedRuntimeAuthorityContradiction(
                    "prior_owner_journal", "missing"
                )
                owner = None
                identity = None
                digest = None
            else:
                raw, identity = _read_exact_runtime_external_file(
                    record.target_owner_journal_path,
                    expected_parent_identity=owner_parent_identity,
                    maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
                )
                digest = "sha256:" + hashlib.sha256(raw).hexdigest()
                if digest != record.target_owner_journal_sha256:
                    raise ValueError("runtime_attempt_retained_journal_invalid")
                owner = parse_runtime_transaction_journal_bytes(
                    raw, expected_transaction_id=owner_id
                )
                if identity != record.target_owner_journal_identity:
                    owner_marker = _BoundedRuntimeAuthorityContradiction(
                        "prior_owner_journal", "identity"
                    )
        else:
            owner, identity, digest = _observe_retained_transaction(
                record.target_owner_journal_path,
                expected_transaction_id=owner_id,
                expected_identity=record.target_owner_journal_identity,
                expected_size=None,
                expected_sha256=record.target_owner_journal_sha256,
            )
        if (
            (
                identity is not None
                and identity != record.target_owner_journal_identity
                and owner_marker is None
            )
            or (digest is not None and digest != record.target_owner_journal_sha256)
            or (owner is not None and owner.phase != RuntimeTransactionPhase.FINALIZED)
            or (owner is not None and not owner.owns_target)
            or record.target_path is None
            or (owner is not None and owner.target_path
            != record.target_path.relative_to(runtime_root).as_posix()
            )
            or (owner is not None and owner.target_identity != record.target_identity)
        ):
            raise ValueError("runtime_attempt_retention_owner_mismatch")
        if owner_marker is not None:
            record_marker(owner_marker)
    if len(markers) > 1:
        raise ValueError("runtime_bounded_authority_contradiction_ambiguous")
    return markers[0] if markers else None


def _bounded_directory_authority_contradiction(
    *,
    path: Path,
    expected_identity: PathIdentity,
    expected_parent_identity: PathIdentity,
    surface: Literal["candidate_root", "prior_owner_target"],
) -> _BoundedRuntimeAuthorityContradiction | None:
    """Observe only the narrowly approved missing/identity alternatives."""

    require_plain_directory(path.parent)
    if path_identity(path.parent) != expected_parent_identity:
        raise ValueError("runtime_bounded_authority_parent_changed")
    if not path_lexists(path):
        return _BoundedRuntimeAuthorityContradiction(surface, "missing")
    status = path.lstat()
    require_plain_directory(path)
    identity = path_identity_from_status(status)
    require_same_identity_resolution(path, expected_status=status)
    require_no_alternate_data_streams(
        path,
        expected_identity=identity,
        expected_parent_identity=expected_parent_identity,
        directory=True,
    )
    return (
        None
        if identity == expected_identity
        else _BoundedRuntimeAuthorityContradiction(surface, "identity")
    )


def _require_bounded_authority_marker_content_exact(
    *,
    marker: _BoundedRuntimeAuthorityContradiction,
    recovery: Mapping[str, Any],
    package_lease: PackageInputLease,
    deck_name: str,
    layout_identities: Mapping[str, PathIdentity],
) -> None:
    if marker.surface == "candidate_root":
        path = Path(str(recovery["candidate_path"]))
        expected_identity_value = recovery.get("successor_candidate_identity")
        expected_parent_identity = layout_identities["staging"]
    elif marker.surface == "prior_owner_target":
        path = Path(str(recovery["renamed_target_path"]))
        expected_identity_value = recovery.get("successor_renamed_target_identity")
        expected_parent_identity = layout_identities["custom_config"]
    elif marker.surface == "prior_owner_journal":
        return
    else:
        raise ValueError("runtime_bounded_authority_contradiction_invalid")
    if not _valid_path_identity(expected_identity_value):
        raise ValueError("runtime_bounded_authority_contradiction_invalid")
    expected_identity = tuple(expected_identity_value)
    if marker.kind == "missing":
        _require_retained_child_absent(
            path,
            expected_parent_identity=expected_parent_identity,
        )
        return
    if marker.kind != "identity":
        raise ValueError("runtime_bounded_authority_contradiction_invalid")
    actual_identity = path_identity(path)
    if actual_identity == expected_identity:
        raise ValueError("runtime_bounded_authority_contradiction_invalid")
    manifest, _ = _candidate_manifest_from_pair(
        package_lease=package_lease,
        deck_name=deck_name,
    )
    entries = tuple(manifest["entries"])
    _verify_candidate_tree_prefix(
        root=path,
        root_identity=actual_identity,
        expected_parent_identity=expected_parent_identity,
        entries=entries,
        cursor=len(entries),
    )


def _observe_exact_paired_runtime_attempt(
    runtime_root: Path,
    *,
    transaction_id: str,
    expected_retention_owner_run_id: str,
    expected_package_root_sha256: str,
    expected_deck_name: str,
    recovery_cursor: Mapping[str, Any] | None,
    action_bound_candidate_identity: PathIdentity | None = None,
    action_bound_journal_triplet: tuple[str, PathIdentity, str] | None = None,
    action_bound_target: tuple[Path, PathIdentity] | None = None,
    tolerate_bounded_authority_contradiction: bool = False,
    layout_identities: Mapping[str, PathIdentity] | None = None,
) -> _ExactPairedRuntimeAttemptObservation:
    if tolerate_bounded_authority_contradiction and (
        not isinstance(layout_identities, Mapping)
        or any(
            not _valid_path_identity(layout_identities.get(name))
            for name in ("staging", "custom_config", "transactions")
        )
    ):
        raise ValueError("runtime_bounded_authority_layout_missing")
    external = _controller_transaction_external_action(recovery_cursor)
    transaction = _observe_exact_runtime_transaction_store(
        runtime_root,
        transaction_id=transaction_id,
        external_file_action=external,
    )
    retention_staging = _runtime_attempt_retention_path(
        runtime_root,
        transaction_id,
    ).with_name(f"{transaction_id}.json.staged")
    retention_inner = retention_staging.with_name(
        f".{retention_staging.name}.live-start-atomic.tmp"
    )
    recovery_external = (
        recovery_cursor.get("external_file_action")
        if isinstance(recovery_cursor, Mapping)
        else None
    )
    bound_retention_staging = (
        isinstance(recovery_external, Mapping)
        and Path(str(recovery_external.get("staging_path")))
        == retention_staging
    )
    if (
        (path_lexists(retention_staging) or path_lexists(retention_inner))
        and not bound_retention_staging
    ):
        raise ValueError("runtime_attempt_retention_store_invalid")
    observed = _observe_runtime_attempt_retention(
        runtime_root,
        apply_attempt_id=transaction_id,
    )
    intended_package_digest = expected_package_root_sha256
    if isinstance(recovery_cursor, Mapping):
        target_value = recovery_cursor.get("renamed_target_path")
        if isinstance(target_value, str) and "--sha256-" in Path(
            target_value
        ).name:
            intended_package_digest = (
                "sha256:"
                + Path(target_value).name.rsplit("--sha256-", 1)[1]
            )
    validated_unbound_candidate_identity: PathIdentity | None = None
    if observed is not None:
        recovery_journal_triplet = action_bound_journal_triplet
        if isinstance(recovery_cursor, Mapping):
            external = recovery_cursor.get("external_file_action")
            exact_committed_successor = (
                recovery_cursor.get("expected_action")
                    in {
                        "bind_renamed_target",
                        "commit_ini_journal",
                    "commit_state_journal",
                    "finalize_journal",
                }
                and isinstance(external, Mapping)
                and external.get("stage") == "STAGING_BOUND"
                and transaction.journal_path
                == Path(str(external.get("final_path")))
                and transaction.journal_identity is not None
                and transaction.journal_sha256
                == external.get("planned_successor_sha256")
                and transaction.controller_staging_path is None
            )
            if exact_committed_successor:
                recovery_journal_triplet = (
                    str(transaction.journal_path),
                    transaction.journal_identity,
                    str(transaction.journal_sha256),
                )
            elif (
                recovery_cursor.get("successor_journal_path") is not None
                and recovery_cursor.get("successor_journal_identity")
                is not None
                and recovery_cursor.get("successor_journal_sha256") is not None
            ):
                recovery_journal_triplet = (
                    str(recovery_cursor["successor_journal_path"]),
                    tuple(recovery_cursor["successor_journal_identity"]),
                    str(recovery_cursor["successor_journal_sha256"]),
                )
        if (
            observed.record.retention_owner_run_id
            != expected_retention_owner_run_id
            or (
                observed.record.package_root_sha256 is not None
                and observed.record.package_root_sha256
                != intended_package_digest
            )
        ):
            raise ValueError("runtime_attempt_recovery_retention_mismatch")
        candidate_identity_authority = (
            tuple(recovery_cursor["successor_candidate_identity"])
            if isinstance(recovery_cursor, Mapping)
            and isinstance(
                recovery_cursor.get("successor_candidate_identity"),
                (list, tuple),
            )
            else action_bound_candidate_identity
        )
        authority_contradiction = _validate_exact_paired_retention_projection(
            runtime_root,
            observed=observed,
            transaction=transaction,
            action_bound_candidate_identity=candidate_identity_authority,
            allow_unbound_empty_candidate=(
                isinstance(recovery_cursor, Mapping)
                and recovery_cursor.get("expected_action")
                == "bind_created_candidate"
            ),
            recovery_journal_triplet=recovery_journal_triplet,
            action_bound_target=(
                (
                    Path(str(recovery_cursor["renamed_target_path"])),
                    tuple(
                        recovery_cursor[
                            (
                                "successor_candidate_identity"
                                if recovery_cursor.get("expected_action")
                                == "rename_candidate_to_target"
                                else "successor_renamed_target_identity"
                            )
                        ]
                    ),
                )
                if isinstance(recovery_cursor, Mapping)
                and (
                    (
                        recovery_cursor.get("expected_action")
                        == "rename_candidate_to_target"
                        and recovery_cursor.get("successor_candidate_identity")
                        is not None
                    )
                    or recovery_cursor.get("successor_renamed_target_identity")
                    is not None
                )
                else action_bound_target
            ),
            recovery_cursor=recovery_cursor,
            layout_identities=layout_identities,
            tolerate_bounded_authority_contradiction=(
                tolerate_bounded_authority_contradiction
            ),
        )
        if (
            observed.record.candidate_path is not None
            and observed.record.candidate_identity is None
        ):
            validated_unbound_candidate_identity = candidate_identity_authority
    else:
        authority_contradiction = None
    journal = transaction.journal
    if journal is not None and (
        journal.deck_name != expected_deck_name
        or "sha256:" + journal.package_root_sha256
        != intended_package_digest
    ):
        raise ValueError("runtime_attempt_recovery_journal_mismatch")

    receipt_path: Path | None = None
    if journal is None:
        status = (
            "unknown"
            if transaction.legacy_temp_path is not None
            else "not_committed"
        )
    elif journal.phase == RuntimeTransactionPhase.FINALIZED:
        candidate_receipt = _receipt_path(runtime_root, journal.state_key)
        if path_lexists(candidate_receipt):
            _read_exact_runtime_external_file(
                candidate_receipt,
                expected_parent_identity=path_identity(
                    candidate_receipt.parent
                ),
                maximum_size=_RUNTIME_EXTERNAL_FILE_ACTION_MAX_BYTES,
            )
            receipt_path = candidate_receipt
            status = "committed"
        else:
            status = "committed_receipt_pending"
    else:
        status = "unknown"
    return _ExactPairedRuntimeAttemptObservation(
        retention=observed,
        transaction=transaction,
        status=status,
        receipt_path=receipt_path,
        validated_unbound_candidate_identity=(
            validated_unbound_candidate_identity
        ),
        authority_contradiction=authority_contradiction,
    )


def _initial_apply_recovery_from_observation(
    *,
    observation: _ExactPairedRuntimeAttemptObservation,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
) -> RuntimeApplyRecoveryEvidence:
    value: dict[str, Any] = {
        field_name: None
        for field_name in _APPLY_RECOVERY_FIELDS
        if field_name != "content_sha256"
    }
    retained = observation.retention
    record = retained.record if retained is not None else None
    transaction = observation.transaction
    if transaction.legacy_temp_classification is not None:
        expected_action = _LEGACY_UUID_TEMP_ACTION_BY_CLASSIFICATION[
            transaction.legacy_temp_classification
        ]
    elif (
        record is not None
        and record.state == "CANDIDATE_PLANNED"
        and transaction.journal is not None
        and transaction.journal.phase == RuntimeTransactionPhase.PREPARED
    ):
        expected_action = "bind_created_candidate"
    elif transaction.journal is None:
        expected_action = "observe_not_committed"
    elif transaction.journal.phase == RuntimeTransactionPhase.FINALIZED:
        expected_action = "observe_committed"
    else:
        expected_action = "observe_pending"
    install_route = (
        "prior_owner"
        if record is not None
        and record.state.startswith("PRIOR_OWNER_")
        else "new_target"
    )
    value.update(
        {
            "schema_version": 1,
            "recovery_kind": (
                "live_start_runtime_apply_recovery_evidence"
            ),
            "recovery_stage": "ACTIVE",
            "run_id": runtime_admission.run_id,
            "apply_attempt_id": runtime_admission.apply_attempt_id,
            "apply_invocation_sha256": (
                runtime_admission.apply_invocation_sha256
            ),
            "runtime_admission_path": str(
                runtime_admission.admission_path
            ),
            "runtime_admission_parent_identity": (
                runtime_admission.admission_parent_identity
            ),
            "runtime_admission_identity": (
                runtime_admission.admission_identity
            ),
            "runtime_admission_sha256": (
                runtime_admission.admission_sha256
            ),
            "package_root_sha256": (
                runtime_admission.package_root_sha256
            ),
            "runtime_root": str(runtime_admission.runtime_root),
            "runtime_root_identity": (
                runtime_admission.runtime_root_identity
            ),
            "install_route": install_route,
            "action_index": 0,
            "expected_action": expected_action,
            "runtime_match_status": "not_run",
            "predecessor_attempt_record_path": (
                str(retained.path) if retained is not None else None
            ),
            "predecessor_attempt_record_identity": (
                retained.identity if retained is not None else None
            ),
            "predecessor_attempt_record_sha256": (
                retained.raw_sha256 if retained is not None else None
            ),
            "predecessor_journal_path": (
                str(transaction.journal_path)
                if transaction.journal is not None
                else None
            ),
            "predecessor_journal_identity": (
                transaction.journal_identity
            ),
            "predecessor_journal_sha256": transaction.journal_sha256,
            "predecessor_target_owner_journal_path": (
                str(record.target_owner_journal_path)
                if record is not None
                and record.target_owner_journal_path is not None
                else None
            ),
            "predecessor_target_owner_journal_identity": (
                record.target_owner_journal_identity
                if record is not None
                else None
            ),
            "predecessor_target_owner_journal_sha256": (
                record.target_owner_journal_sha256
                if record is not None
                else None
            ),
        }
    )
    value.update(
        _legacy_uuid_temp_evidence(
            observation=transaction,
            family="nonterminal_apply",
        )
    )
    if record is not None and record.candidate_path is not None and (
        record.candidate_identity is not None
        or expected_action == "bind_created_candidate"
    ):
        value.update(
            {
                "candidate_path": str(record.candidate_path),
                "candidate_parent_identity": (
                    record.candidate_parent_identity
                ),
                "predecessor_candidate_identity": (
                    record.candidate_identity
                ),
            }
        )
    return RuntimeApplyRecoveryEvidence(
        _seal_apply_recovery_successor(value, changes={})
    )


def _initial_terminal_resolution_from_observation(
    *,
    observation: _ExactPairedRuntimeAttemptObservation,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    closed_recovery: Mapping[str, Any],
) -> TerminalResolutionEvidence:
    if (
        closed_recovery.get("recovery_stage") != "CLOSED"
        or closed_recovery.get("run_id") != runtime_admission.run_id
        or closed_recovery.get("apply_attempt_id")
        != runtime_admission.apply_attempt_id
        or closed_recovery.get("runtime_admission_path")
        != str(runtime_admission.admission_path)
        or tuple(closed_recovery.get("runtime_admission_identity", ()))
        != runtime_admission.admission_identity
        or closed_recovery.get("runtime_admission_sha256")
        != runtime_admission.admission_sha256
        or closed_recovery.get("package_root_sha256")
        != runtime_admission.package_root_sha256
        or closed_recovery.get("runtime_root")
        != str(runtime_admission.runtime_root)
        or tuple(closed_recovery.get("runtime_root_identity", ()))
        != runtime_admission.runtime_root_identity
        or closed_recovery.get("external_file_action") is not None
    ):
        raise ValueError("runtime_terminal_resolution_closed_recovery_invalid")
    value: dict[str, Any] = {
        field_name: None
        for field_name in _TERMINAL_RESOLUTION_FIELDS
        if field_name != "content_sha256"
    }
    retained = observation.retention
    record = retained.record if retained is not None else None
    transaction = observation.transaction
    disposition = closed_recovery.get("stable_physical_disposition")
    if disposition not in {
        "NOT_COMMITTED",
        "COMMITTED",
        "COMMITTED_RECOVERY_PENDING",
        "UNKNOWN_REQUIRES_RECOVERY",
    }:
        raise ValueError("runtime_terminal_resolution_closed_recovery_invalid")
    value.update(
        {
            "schema_version": 1,
            "resolution_kind": (
                "live_start_terminal_resolution_evidence"
            ),
            "run_id": runtime_admission.run_id,
            "apply_attempt_id": runtime_admission.apply_attempt_id,
            "resolved_physical_disposition": disposition,
        }
    )
    for field_name in _TERMINAL_RESOLUTION_FIELDS:
        if field_name in closed_recovery and field_name not in {
            "schema_version",
            "resolution_kind",
            "resolved_physical_disposition",
            "content_sha256",
        }:
            value[field_name] = closed_recovery[field_name]
    observed_attempt = (
        str(retained.path) if retained is not None else None,
        retained.identity if retained is not None else None,
        retained.raw_sha256 if retained is not None else None,
    )
    source_attempt = tuple(
        closed_recovery.get(f"predecessor_attempt_record_{suffix}")
        for suffix in ("path", "identity", "sha256")
    )
    observed_journal = (
        str(transaction.journal_path) if transaction.journal is not None else None,
        transaction.journal_identity,
        transaction.journal_sha256,
    )
    source_journal = tuple(
        closed_recovery.get(f"predecessor_journal_{suffix}")
        for suffix in ("path", "identity", "sha256")
    )
    if observed_attempt != source_attempt or observed_journal != source_journal:
        raise ValueError("runtime_terminal_resolution_closed_recovery_changed")
    source_owner = tuple(
        closed_recovery.get(f"predecessor_target_owner_journal_{suffix}")
        for suffix in ("path", "identity", "sha256")
    )
    observed_owner = (
        str(record.target_owner_journal_path)
        if record is not None and record.target_owner_journal_path is not None
        else None,
        record.target_owner_journal_identity if record is not None else None,
        record.target_owner_journal_sha256 if record is not None else None,
    )
    if observed_owner != source_owner:
        raise ValueError("runtime_terminal_resolution_closed_recovery_changed")
    if _legacy_uuid_temp_evidence(
        observation=transaction,
        family="terminal_resolution",
    ) != {
        field_name: closed_recovery.get(field_name)
        for field_name in (
            "predecessor_transaction_temp_path",
            "predecessor_transaction_temp_parent_identity",
            "predecessor_transaction_temp_identity",
            "predecessor_transaction_temp_size",
            "predecessor_transaction_temp_sha256",
            "predecessor_transaction_temp_classification",
            "predecessor_transaction_temp_origin",
        )
    }:
        raise ValueError("runtime_terminal_resolution_closed_recovery_changed")
    observed_candidate = (
        str(record.candidate_path)
        if record is not None and record.candidate_path is not None
        else None,
        record.candidate_parent_identity if record is not None else None,
        record.candidate_identity if record is not None else None,
    )
    source_candidate = (
        closed_recovery.get("candidate_path"),
        closed_recovery.get("candidate_parent_identity"),
        closed_recovery.get("predecessor_candidate_identity"),
    )
    if disposition in {"NOT_COMMITTED", "UNKNOWN_REQUIRES_RECOVERY"}:
        # A schema-2 CANDIDATE_PLANNED fence can survive either before the
        # candidate is created or after create-before-fence-bind.  The paired
        # observer has already proved exact absence or validated the CLOSED-bound
        # empty-directory identity.  Project only those two complete shapes.
        planned_candidate_projection = (
            disposition == "NOT_COMMITTED"
            and record is not None
            and record.state == "CANDIDATE_PLANNED"
            and record.candidate_path is not None
            and record.candidate_parent_identity is not None
            and record.candidate_identity is None
            and record.planned_journal_path == transaction.journal_path
            and record.planned_journal_size is not None
            and record.planned_journal_sha256 is not None
            and closed_recovery.get("successor_candidate_identity") is None
            and transaction.journal is not None
            and transaction.journal.phase
            == RuntimeTransactionPhase.PREPARED
            and transaction.journal.candidate_identity is None
        )
        tree_bearing_projection = (
            planned_candidate_projection
            and source_candidate[:2] == observed_candidate[:2]
            and source_candidate[2] is not None
            and observation.validated_unbound_candidate_identity
            == source_candidate[2]
        )
        no_tree_projection = (
            planned_candidate_projection
            and source_candidate == (None, None, None)
            and observation.validated_unbound_candidate_identity is None
        )
        if tree_bearing_projection:
            pass
        elif no_tree_projection:
            value["candidate_path"] = observed_candidate[0]
            value["candidate_parent_identity"] = observed_candidate[1]
        elif planned_candidate_projection or observed_candidate != source_candidate:
            raise ValueError("runtime_terminal_candidate_identity_changed")
    else:
        install_route = closed_recovery.get("install_route")
        expected_target = (
            closed_recovery.get("renamed_target_path"),
            closed_recovery.get("predecessor_renamed_target_identity"),
        )
        observed_target = (
            str(record.target_path)
            if record is not None and record.target_path is not None
            else None,
            record.target_identity if record is not None else None,
        )
        if (
            record is None
            or record.state != "FINALIZED"
            or observed_candidate != (None, None, None)
            or observed_target != expected_target
            or install_route not in {"new_target", "prior_owner"}
            or record.owns_target != (install_route != "prior_owner")
        ):
            raise ValueError("runtime_terminal_committed_record_changed")
        if install_route == "new_target":
            if (
                any(value is None for value in source_candidate)
                or source_candidate[2]
                != closed_recovery.get("predecessor_renamed_target_identity")
            ):
                raise ValueError("runtime_terminal_candidate_identity_changed")
        elif source_candidate != (None, None, None):
            raise ValueError("runtime_terminal_candidate_identity_changed")
    return TerminalResolutionEvidence(_seal_terminal_resolution(value))


def _closed_recovery_result_intent_binding_is_exact(
    *,
    closed_recovery: Mapping[str, Any],
    result_intent: Mapping[str, Any],
) -> bool:
    """Mirror the Session's CLOSED-to-result retained-evidence selection."""

    expected_values = {
        "apply_attempt_id": closed_recovery.get("apply_attempt_id"),
        "package_root_sha256": closed_recovery.get("package_root_sha256"),
        "last_apply_receipt_sha256": closed_recovery.get(
            "last_apply_receipt_sha256"
        ),
        "runtime_state_sha256": closed_recovery.get("runtime_state_sha256"),
        "deck_config_ini_sha256": closed_recovery.get(
            "deck_config_ini_sha256"
        ),
        "runtime_match_status": closed_recovery.get("runtime_match_status"),
        "runtime_match_sha256": closed_recovery.get("runtime_match_sha256"),
        "physical_disposition": closed_recovery.get(
            "stable_physical_disposition"
        ),
        "retained_candidate_identity": (
            closed_recovery.get("predecessor_candidate_identity")
            if closed_recovery.get("stable_physical_disposition")
            == "NOT_COMMITTED"
            else None
        ),
    }
    for intent_prefix, recovery_prefix in (
        ("retained_attempt_record", "predecessor_attempt_record"),
        ("retained_journal", "predecessor_journal"),
        (
            "retained_target_owner_journal",
            "predecessor_target_owner_journal",
        ),
    ):
        for suffix in ("path", "identity", "sha256"):
            expected_values[f"{intent_prefix}_{suffix}"] = closed_recovery.get(
                f"{recovery_prefix}_{suffix}"
            )
    return all(
        result_intent.get(field_name) == expected_value
        for field_name, expected_value in expected_values.items()
    )


def _require_recovery_cursor_observation_matches(
    *,
    recovery: Mapping[str, Any],
    observation: _ExactPairedRuntimeAttemptObservation,
    action: str,
    allow_committed_journal_successor: bool,
    allow_retired_legacy_temp: bool,
) -> None:
    retained = observation.retention
    retention_triplet = (
        str(retained.path) if retained is not None else None,
        retained.identity if retained is not None else None,
        retained.raw_sha256 if retained is not None else None,
    )
    retention_prefix = (
        "successor_attempt_record"
        if recovery.get("successor_attempt_record_path") is not None
        else "predecessor_attempt_record"
    )
    expected_retention_triplet = (
        recovery.get(f"{retention_prefix}_path"),
        (
            tuple(recovery[f"{retention_prefix}_identity"])
            if isinstance(
                recovery.get(f"{retention_prefix}_identity"),
                (list, tuple),
            )
            else None
        ),
        recovery.get(f"{retention_prefix}_sha256"),
    )
    if retention_triplet != expected_retention_triplet and not (
        _is_exact_retention_commit_action_before_cas(
            recovery=recovery,
            observation=observation,
            action=action,
        )
    ):
        raise ValueError("runtime_apply_recovery_attempt_record_changed")
    transaction = observation.transaction
    observed_journal = (
        str(transaction.journal_path)
        if transaction.journal is not None
        else None,
        transaction.journal_identity,
        transaction.journal_sha256,
    )
    journal_prefix = (
        "successor_journal"
        if recovery.get("successor_journal_path") is not None
        else "predecessor_journal"
    )
    expected_journal = (
        recovery.get(f"{journal_prefix}_path"),
        (
            tuple(recovery[f"{journal_prefix}_identity"])
            if isinstance(
                recovery.get(f"{journal_prefix}_identity"),
                (list, tuple),
            )
            else None
        ),
        recovery.get(f"{journal_prefix}_sha256"),
    )
    if not allow_committed_journal_successor and (
        observed_journal != expected_journal
    ):
        raise ValueError("runtime_apply_recovery_journal_changed")
    observed_temp = _legacy_uuid_temp_evidence(
        observation=transaction,
        family="nonterminal_apply",
    )
    if not allow_retired_legacy_temp and any(
        recovery.get(key) != value
        for key, value in observed_temp.items()
    ):
        raise ValueError("runtime_apply_recovery_legacy_temp_changed")


def _is_exact_retention_commit_action_before_cas(
    *,
    recovery: Mapping[str, Any],
    observation: _ExactPairedRuntimeAttemptObservation,
    action: str,
) -> bool:
    expected_state = {
        "commit_bound_initial_attempt_record": "ACTIVE",
        "commit_bound_candidate_planned_attempt_record": "CANDIDATE_PLANNED",
        "commit_bound_prior_owner_planned_attempt_record": (
            "PRIOR_OWNER_PLANNED"
        ),
        "commit_bound_prior_owner_attempt_record": "PRIOR_OWNER_BOUND",
        "bind_candidate_fence": "CANDIDATE_BOUND",
        "finalize_attempt_record": "FINALIZED",
    }.get(action)
    external = recovery.get("external_file_action")
    retained = observation.retention
    if (
        expected_state is None
        or not isinstance(external, Mapping)
        or external.get("stage") != "STAGING_BOUND"
        or external.get("action_kind") != action
        or retained is None
    ):
        return False
    final_path = Path(str(external.get("final_path")))
    staging_path = Path(str(external.get("staging_path")))
    inner_temp_path = Path(str(external.get("inner_temp_path")))
    staging_identity = external.get("staging_identity")
    record = retained.record
    exact = (
        retained.path == final_path
        and retained.identity == tuple(staging_identity or ())
        and retained.raw_sha256 == external.get("planned_successor_sha256")
        and external.get("staging_size")
        == external.get("planned_successor_size")
        and external.get("staging_sha256")
        == external.get("planned_successor_sha256")
        and not path_lexists(staging_path)
        and not path_lexists(inner_temp_path)
        and record.state == expected_state
        and record.apply_attempt_id == recovery.get("apply_attempt_id")
        and record.retention_owner_run_id == recovery.get("run_id")
        and (
            record.package_root_sha256 is None
            if expected_state == "ACTIVE"
            else record.package_root_sha256
            == "sha256:"
            + Path(str(recovery["renamed_target_path"])).name.rsplit(
                "--sha256-", 1
            )[1]
        )
    )
    if not exact:
        return False
    if expected_state == "FINALIZED":
        expected_journal_path = Path(str(recovery["successor_journal_path"]))
        expected_journal_identity = tuple(
            recovery["successor_journal_identity"]
        )
        expected_journal_sha256 = str(recovery["successor_journal_sha256"])
        return (
            record.journal_path == expected_journal_path
            and record.journal_identity == expected_journal_identity
            and record.journal_sha256 == expected_journal_sha256
            and record.planned_journal_path == expected_journal_path
            and record.planned_journal_size == expected_journal_path.stat().st_size
            and record.planned_journal_sha256 == expected_journal_sha256
            and record.target_path
            == Path(str(recovery["renamed_target_path"]))
            and record.target_identity
            == tuple(recovery["successor_renamed_target_identity"])
            and record.owns_target is True
            and record.target_owner_journal_path == expected_journal_path
            and record.target_owner_journal_identity
            == expected_journal_identity
            and record.target_owner_journal_sha256
            == expected_journal_sha256
            and record.candidate_path is None
            and record.candidate_parent_identity is None
            and record.candidate_identity is None
        )
    if expected_state != "CANDIDATE_BOUND":
        return True
    expected_journal_path = Path(str(recovery["successor_journal_path"]))
    expected_journal_identity = tuple(recovery["successor_journal_identity"])
    expected_journal_sha256 = str(recovery["successor_journal_sha256"])
    expected_candidate_path = Path(str(recovery["candidate_path"]))
    return (
        record.journal_path == expected_journal_path
        and record.journal_identity == expected_journal_identity
        and record.journal_sha256 == expected_journal_sha256
        and record.planned_journal_path == expected_journal_path
        and record.planned_journal_size
        == expected_journal_path.stat().st_size
        and record.planned_journal_sha256 == expected_journal_sha256
        and record.candidate_path == expected_candidate_path
        and record.candidate_parent_identity
        == tuple(recovery["candidate_parent_identity"])
        and record.candidate_identity
        == tuple(recovery["successor_candidate_identity"])
        and record.target_path is None
        and record.target_identity is None
        and record.owns_target is False
    )


def _retire_unbound_recovery_external_file_action(
    *,
    recovery: Mapping[str, Any],
    terminal_retirement: Mapping[str, Any] | None = None,
) -> (
    RuntimeApplyRecoveryPhysicalPostcondition
    | TerminalResolutionPhysicalPostcondition
):
    external = recovery.get("external_file_action")
    if (
        not isinstance(external, Mapping)
        or external.get("stage") != "PLANNED"
    ):
        raise ValueError("runtime_recovery_external_action_invalid")
    final_path = Path(str(external.get("final_path")))
    staging_path = Path(str(external.get("staging_path")))
    inner_temp_path = Path(str(external.get("inner_temp_path")))
    parent_identity = tuple(external.get("parent_identity", ()))
    planned_size = external.get("planned_successor_size")
    planned_sha256 = external.get("planned_successor_sha256")
    if (
        not all(
            path.is_absolute()
            for path in (final_path, staging_path, inner_temp_path)
        )
        or staging_path != final_path.with_name(f"{final_path.name}.staged")
        or inner_temp_path
        != staging_path.with_name(
            f".{staging_path.name}.live-start-atomic.tmp"
        )
        or len(parent_identity) != 3
        or path_identity(final_path.parent) != parent_identity
        or type(planned_size) is not int
        or not 0 < planned_size <= _RUNTIME_EXTERNAL_FILE_ACTION_MAX_BYTES
        or not isinstance(planned_sha256, str)
        or _PREFIXED_SHA256.fullmatch(planned_sha256) is None
    ):
        raise ValueError("runtime_recovery_external_action_invalid")
    predecessor_state = external.get("predecessor_state")
    if predecessor_state == "absent":
        if path_lexists(final_path):
            raise ValueError("runtime_recovery_external_final_changed")
    elif predecessor_state == "exact":
        final_raw, final_identity = _read_exact_runtime_external_file(
            final_path,
            expected_parent_identity=parent_identity,
            maximum_size=_RUNTIME_EXTERNAL_FILE_ACTION_MAX_BYTES,
        )
        if (
            tuple(external.get("predecessor_identity", ()))
            != final_identity
            or external.get("predecessor_size") != len(final_raw)
            or external.get("predecessor_sha256")
            != "sha256:" + hashlib.sha256(final_raw).hexdigest()
        ):
            raise ValueError("runtime_recovery_external_final_changed")
    else:
        raise ValueError("runtime_recovery_external_action_invalid")
    _retire_unbound_runtime_external_file(
        inner_temp_path,
        expected_parent_identity=parent_identity,
        maximum_size=max(planned_size, 1),
    )
    _retire_unbound_runtime_external_file(
        staging_path,
        expected_parent_identity=parent_identity,
        maximum_size=max(planned_size, 1),
        expected_size=planned_size,
        expected_sha256=planned_sha256,
    )
    if path_lexists(staging_path) or path_lexists(inner_temp_path):
        raise ValueError("runtime_recovery_external_residue_present")
    next_external = _plain_json_value(external)
    if not isinstance(next_external, dict):
        raise ValueError("runtime_recovery_external_action_invalid")
    next_external.pop("content_sha256", None)
    next_external["action_index"] = int(external.get("action_index")) + 1
    sealed_external = seal_embedded_document(
        "external_file_action",
        next_external,
    )
    if terminal_retirement is not None:
        owner = recovery.get("owner_retirement")
        if not isinstance(owner, Mapping):
            raise ValueError(
                "runtime_owner_retirement_cursor_invalid"
            )
        return _owner_retirement_owner_external_postcondition(
            recovery=recovery,
            action="retire_unbound_file_action_staging",
            owner=owner,
            next_owner=_seal_owner_retirement_document(owner),
            next_action="materialize_file_action_staging",
            next_external=sealed_external,
            terminal_retirement=terminal_retirement,
        )
    successor = _seal_apply_recovery_successor(
        recovery,
        changes={
            "action_index": int(recovery.get("action_index")) + 1,
            "expected_action": "materialize_file_action_staging",
            "external_file_action": sealed_external,
        },
    )
    return RuntimeApplyRecoveryPhysicalPostcondition(
        action="retire_unbound_file_action_staging",
        evidence={"apply_recovery": successor},
    )


def _retention_bytes_for_recovery_action(
    recovery: Mapping[str, Any],
    *,
    state: str,
) -> bytes:
    runtime_root = Path(str(recovery["runtime_root"]))
    attempt_id = str(recovery["apply_attempt_id"])
    if state == "ACTIVE":
        planned_journal_path = None
        planned_journal_size = None
        planned_journal_sha256 = None
        candidate_path = None
        candidate_parent_identity = None
    elif state in {"CANDIDATE_PLANNED", "CANDIDATE_BOUND"}:
        if state == "CANDIDATE_BOUND":
            planned_journal_path = Path(str(recovery["successor_journal_path"]))
            journal_status = plain_file_status(planned_journal_path)
            planned_journal_size = journal_status.st_size
            planned_journal_sha256 = str(recovery["successor_journal_sha256"])
        else:
            planned_journal_path = Path(
                str(recovery["planned_journal_successor_path"])
            )
            planned_journal_size = int(
                recovery["planned_journal_successor_size"]
            )
            planned_journal_sha256 = str(
                recovery["planned_journal_successor_sha256"]
            )
        candidate_path = Path(str(recovery["candidate_path"]))
        candidate_parent_identity = tuple(
            recovery["candidate_parent_identity"]
        )
    elif state == "FINALIZED":
        planned_journal_path = Path(str(recovery["successor_journal_path"]))
        journal_status = plain_file_status(planned_journal_path)
        planned_journal_size = journal_status.st_size
        planned_journal_sha256 = str(recovery["successor_journal_sha256"])
        candidate_path = None
        candidate_parent_identity = None
    elif state in {"PRIOR_OWNER_PLANNED", "PRIOR_OWNER_BOUND"}:
        planned_journal_path = Path(
            str(
                recovery[
                    "successor_journal_path"
                    if state == "PRIOR_OWNER_BOUND"
                    else "planned_journal_successor_path"
                ]
            )
        )
        if state == "PRIOR_OWNER_BOUND":
            planned_journal_size = plain_file_status(planned_journal_path).st_size
            planned_journal_sha256 = str(recovery["successor_journal_sha256"])
        else:
            planned_journal_size = int(recovery["planned_journal_successor_size"])
            planned_journal_sha256 = str(
                recovery["planned_journal_successor_sha256"]
            )
        candidate_path = None
        candidate_parent_identity = None
    else:
        raise ValueError("runtime_initial_retention_state_invalid")
    return build_runtime_attempt_retention_bytes(
        runtime_root=runtime_root,
        state=state,
        apply_attempt_id=attempt_id,
        retention_owner_run_id=str(recovery["run_id"]),
        journal_path=(
            Path(str(recovery["successor_journal_path"]))
            if state in {"CANDIDATE_BOUND", "PRIOR_OWNER_BOUND", "FINALIZED"}
            else None
        ),
        journal_identity=(
            tuple(recovery["successor_journal_identity"])
            if state in {"CANDIDATE_BOUND", "PRIOR_OWNER_BOUND", "FINALIZED"}
            else None
        ),
        journal_sha256=(
            str(recovery["successor_journal_sha256"])
            if state in {"CANDIDATE_BOUND", "PRIOR_OWNER_BOUND", "FINALIZED"}
            else None
        ),
        package_root_sha256=(
            None
            if state == "ACTIVE"
            else "sha256:"
            + Path(str(recovery["renamed_target_path"])).name.rsplit(
                "--sha256-", 1
            )[1]
        ),
        target_path=(
            Path(str(recovery["renamed_target_path"]))
            if state in {"PRIOR_OWNER_PLANNED", "PRIOR_OWNER_BOUND", "FINALIZED"}
            else None
        ),
        target_identity=(
            tuple(recovery["successor_renamed_target_identity"])
            if state in {"PRIOR_OWNER_PLANNED", "PRIOR_OWNER_BOUND", "FINALIZED"}
            else None
        ),
        owns_target=(
            (
                recovery.get("install_route") != "prior_owner"
                if state == "FINALIZED"
                else None
                if state == "ACTIVE"
                else False
            )
        ),
        target_owner_journal_path=(
            Path(str(recovery["predecessor_target_owner_journal_path"]))
            if state in {"PRIOR_OWNER_PLANNED", "PRIOR_OWNER_BOUND"}
            else Path(
                str(
                    recovery[
                        "predecessor_target_owner_journal_path"
                        if recovery.get("install_route") == "prior_owner"
                        else "successor_journal_path"
                    ]
                )
            )
            if state == "FINALIZED"
            else None
        ),
        target_owner_journal_identity=(
            tuple(recovery["predecessor_target_owner_journal_identity"])
            if state in {"PRIOR_OWNER_PLANNED", "PRIOR_OWNER_BOUND"}
            else tuple(
                recovery[
                    "predecessor_target_owner_journal_identity"
                    if recovery.get("install_route") == "prior_owner"
                    else "successor_journal_identity"
                ]
            )
            if state == "FINALIZED"
            else None
        ),
        target_owner_journal_sha256=(
            str(recovery["predecessor_target_owner_journal_sha256"])
            if state in {"PRIOR_OWNER_PLANNED", "PRIOR_OWNER_BOUND"}
            else str(
                recovery[
                    "predecessor_target_owner_journal_sha256"
                    if recovery.get("install_route") == "prior_owner"
                    else "successor_journal_sha256"
                ]
            )
            if state == "FINALIZED"
            else None
        ),
        planned_journal_path=planned_journal_path,
        planned_journal_size=planned_journal_size,
        planned_journal_sha256=planned_journal_sha256,
        candidate_path=candidate_path,
        candidate_parent_identity=candidate_parent_identity,
        candidate_identity=(
            tuple(recovery["successor_candidate_identity"])
            if state == "CANDIDATE_BOUND"
            else None
        ),
    )


def _prepared_journal_bytes_from_recovery(
    *,
    recovery: Mapping[str, Any],
    package_lease: PackageInputLease,
    deck_name: str,
    state_key: str,
) -> bytes:
    binding = _require_active_package_input_lease(package_lease)
    if binding.lease.snapshot is None or binding.lease.content_root_sha256 is None:
        raise ValueError("runtime_candidate_package_lease_invalid")
    spec = _runtime_package_spec(verify_tree_manifest(binding.lease.snapshot))
    if spec.deck_name != deck_name:
        raise ValueError("runtime_candidate_package_changed")
    runtime_root = Path(str(recovery["runtime_root"]))
    candidate = (
        Path(str(recovery["candidate_path"]))
        if recovery.get("candidate_path") is not None
        else runtime_root
        / ".hsconfig"
        / "staging"
        / str(recovery["apply_attempt_id"])
    )
    target = Path(str(recovery["renamed_target_path"]))
    current_ini = read_deck_config(
        runtime_root / "CustomConfig" / "deck_config.ini",
        deck_name=deck_name,
    )
    next_ini = render_deck_config(
        current_ini,
        deck_name=deck_name,
        config_dir=target.name,
    )
    journal = RuntimeTransactionJournal(
        schema_version=1,
        transaction_id=str(recovery["apply_attempt_id"]),
        deck_name=deck_name,
        source_manifest_sha256=binding.lease.content_root_sha256,
        state_key=state_key,
        logical_config_dir=spec.logical_config_dir,
        package_root_sha256=spec.package_root_sha256,
        candidate_path=candidate.relative_to(runtime_root).as_posix(),
        target_path=target.relative_to(runtime_root).as_posix(),
        candidate_identity=None,
        target_identity=None,
        owns_target=False,
        previous_config_dir=current_ini.selected_config_dir,
        next_config_dir=target.name,
        previous_ini_sha256=current_ini.sha256,
        next_ini_sha256=hashlib.sha256(next_ini).hexdigest(),
        phase=RuntimeTransactionPhase.PREPARED,
    )
    raw = runtime_transaction_journal_bytes(journal)
    if (
        len(raw) != recovery.get("planned_journal_successor_size")
        or "sha256:" + hashlib.sha256(raw).hexdigest()
        != recovery.get("planned_journal_successor_sha256")
    ):
        raise ValueError("runtime_candidate_planned_journal_changed")
    return raw


def _planned_journal_bytes_from_recovery(
    *,
    recovery: Mapping[str, Any],
    package_lease: PackageInputLease,
    deck_name: str,
    state_key: str,
) -> bytes:
    phase_name = recovery.get("planned_journal_successor_phase")
    if phase_name == RuntimeTransactionPhase.PREPARED.name:
        return _prepared_journal_bytes_from_recovery(
            recovery=recovery,
            package_lease=package_lease,
            deck_name=deck_name,
            state_key=state_key,
        )
    try:
        phase = RuntimeTransactionPhase[str(phase_name)]
    except KeyError as error:
        raise ValueError("runtime_candidate_journal_phase_invalid") from error
    target_identity = (
        tuple(recovery["successor_renamed_target_identity"])
        if recovery.get("successor_renamed_target_identity") is not None
        else None
    )
    raw = _journal_successor_bytes(
        recovery=recovery,
        phase=phase,
        target_identity=target_identity,
        owns_target=(
            target_identity is not None
            and recovery.get("install_route") != "prior_owner"
        ),
    )
    if (
        len(raw) != recovery.get("planned_journal_successor_size")
        or "sha256:" + hashlib.sha256(raw).hexdigest()
        != recovery.get("planned_journal_successor_sha256")
    ):
        raise ValueError("runtime_candidate_journal_changed")
    return raw


def _materialize_initial_retention_staging(
    *,
    recovery: Mapping[str, Any],
    payload: bytes | None = None,
    commit_action: str | None = None,
) -> RuntimeApplyRecoveryPhysicalPostcondition:
    external = recovery.get("external_file_action")
    if not isinstance(external, Mapping) or external.get("stage") != "PLANNED":
        raise ValueError("runtime_initial_retention_action_invalid")
    if recovery.get("install_route") == "new_target":
        _require_new_target_prefix_absent(
            recovery,
            allow_bound_candidate=(
                commit_action == "bind_candidate_fence"
                or recovery.get("successor_candidate_identity") is not None
            ),
            allow_bound_target=(
                recovery.get("successor_renamed_target_identity") is not None
            ),
        )
    predecessor_state = external.get("predecessor_state")
    state = (
        "ACTIVE"
        if predecessor_state == "absent"
        else "PRIOR_OWNER_PLANNED"
        if recovery.get("install_route") == "prior_owner"
        else "CANDIDATE_PLANNED"
    )
    content = (
        _retention_bytes_for_recovery_action(recovery, state=state)
        if payload is None
        else payload
    )
    planned_sha256 = "sha256:" + hashlib.sha256(content).hexdigest()
    if (
        len(content) != external.get("planned_successor_size")
        or planned_sha256 != external.get("planned_successor_sha256")
    ):
        raise ValueError("runtime_initial_retention_payload_changed")
    final_path = Path(str(external["final_path"]))
    staging_path = Path(str(external["staging_path"]))
    inner_temp_path = Path(str(external["inner_temp_path"]))
    parent_identity = tuple(external["parent_identity"])
    if predecessor_state == "absent" and path_lexists(final_path):
        raise ValueError("runtime_initial_retention_final_changed")
    if predecessor_state == "exact":
        raw, identity = _read_exact_runtime_external_file(
            final_path,
            expected_parent_identity=parent_identity,
            maximum_size=RUNTIME_ATTEMPT_RETENTION_MAX_BYTES,
        )
        if (
            identity != tuple(external["predecessor_identity"])
            or len(raw) != external["predecessor_size"]
            or "sha256:" + hashlib.sha256(raw).hexdigest()
            != external["predecessor_sha256"]
        ):
            raise ValueError("runtime_initial_retention_final_changed")
    materialized = atomic_materialize_staging_bytes(
        staging_path=staging_path,
        inner_temp_path=inner_temp_path,
        payload=content,
        expected_parent_identity=parent_identity,
        maximum_size=RUNTIME_ATTEMPT_RETENTION_MAX_BYTES,
    )
    next_external = _plain_json_value(external)
    assert isinstance(next_external, dict)
    next_external.pop("content_sha256", None)
    next_external.update(
        {
            "action_index": int(external["action_index"]) + 1,
            "stage": "STAGING_BOUND",
            "action_kind": commit_action
            or (
                "commit_bound_initial_attempt_record"
                if state == "ACTIVE"
                else "commit_bound_prior_owner_planned_attempt_record"
                if state == "PRIOR_OWNER_PLANNED"
                else "commit_bound_candidate_planned_attempt_record"
            ),
            "staging_identity": materialized.identity,
            "staging_size": materialized.size,
            "staging_sha256": materialized.sha256,
        }
    )
    commit_action = str(next_external["action_kind"])
    successor = _seal_apply_recovery_successor(
        recovery,
        changes={
            "action_index": int(recovery["action_index"]) + 1,
            "expected_action": commit_action,
            "external_file_action": seal_embedded_document(
                "external_file_action", next_external
            ),
        },
    )
    return RuntimeApplyRecoveryPhysicalPostcondition(
        action="materialize_file_action_staging",
        evidence={"apply_recovery": successor},
    )


def _commit_initial_retention_staging(
    *,
    recovery: Mapping[str, Any],
    action: str,
    custom_config_parent_identity: PathIdentity | None = None,
    transactions_parent_identity: PathIdentity | None = None,
) -> RuntimeApplyRecoveryPhysicalPostcondition:
    external = recovery.get("external_file_action")
    if not isinstance(external, Mapping) or external.get("stage") != "STAGING_BOUND":
        raise ValueError("runtime_initial_retention_commit_invalid")
    if recovery.get("install_route") == "new_target":
        _require_new_target_prefix_absent(recovery)
    final_path = Path(str(external["final_path"]))
    staging_path = Path(str(external["staging_path"]))
    inner_temp_path = Path(str(external["inner_temp_path"]))
    parent_identity = tuple(external["parent_identity"])
    staging_identity = tuple(external["staging_identity"])
    expected_state = {
        "commit_bound_initial_attempt_record": "ACTIVE",
        "commit_bound_candidate_planned_attempt_record": "CANDIDATE_PLANNED",
        "commit_bound_prior_owner_planned_attempt_record": "PRIOR_OWNER_PLANNED",
        "commit_bound_prior_owner_attempt_record": "PRIOR_OWNER_BOUND",
    }.get(action)
    if expected_state is None:
        raise ValueError("runtime_initial_retention_commit_invalid")
    payload = _retention_bytes_for_recovery_action(
        recovery,
        state=expected_state,
    )
    if path_lexists(final_path) and not path_lexists(staging_path):
        raw, final_identity = _read_exact_runtime_external_file(
            final_path,
            expected_parent_identity=parent_identity,
            maximum_size=RUNTIME_ATTEMPT_RETENTION_MAX_BYTES,
        )
    else:
        if external.get("commit_mode") == "create_no_replace":
            committed = atomic_commit_bound_staging_no_replace(
                path=final_path,
                staging_path=staging_path,
                expected_staging_identity=staging_identity,
                expected_size=int(external["staging_size"]),
                expected_sha256=str(external["staging_sha256"]),
                expected_parent_identity=parent_identity,
            )
        else:
            committed = atomic_commit_bound_staging_replace(
                path=final_path,
                staging_path=staging_path,
                expected_predecessor_identity=tuple(external["predecessor_identity"]),
                expected_staging_identity=staging_identity,
                expected_size=int(external["staging_size"]),
                expected_sha256=str(external["staging_sha256"]),
                expected_parent_identity=parent_identity,
            )
        final_identity = committed.identity
        raw, observed_identity = _read_exact_runtime_external_file(
            final_path,
            expected_parent_identity=parent_identity,
            maximum_size=RUNTIME_ATTEMPT_RETENTION_MAX_BYTES,
        )
        if observed_identity != final_identity:
            raise ValueError("runtime_initial_retention_commit_changed")
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    if (
        final_identity != staging_identity
        or raw != payload
        or path_lexists(staging_path)
        or path_lexists(inner_temp_path)
    ):
        raise ValueError("runtime_initial_retention_commit_changed")

    if expected_state == "ACTIVE":
        next_state = (
            "PRIOR_OWNER_PLANNED"
            if recovery.get("install_route") == "prior_owner"
            else "CANDIDATE_PLANNED"
        )
        candidate_raw = _retention_bytes_for_recovery_action(
            recovery,
            state=next_state,
        )
        next_external = _build_external_file_action(
            action_kind="materialize_file_action_staging",
            action_index=int(external["action_index"]) + 1,
            final_path=final_path,
            staging_path=staging_path,
            inner_temp_path=inner_temp_path,
            parent_identity=parent_identity,
            predecessor_identity=final_identity,
            predecessor_size=len(raw),
            predecessor_sha256=digest,
            planned_successor_size=len(candidate_raw),
            planned_successor_sha256=(
                "sha256:" + hashlib.sha256(candidate_raw).hexdigest()
            ),
            commit_mode="replace_exact",
        )
    elif expected_state in {"CANDIDATE_PLANNED", "PRIOR_OWNER_PLANNED"}:
        journal_path = Path(str(recovery["planned_journal_successor_path"]))
        next_external = _build_external_file_action(
            action_kind="materialize_file_action_staging",
            action_index=int(external["action_index"]) + 1,
            final_path=journal_path,
            staging_path=journal_path.with_name(f"{journal_path.name}.staged"),
            inner_temp_path=journal_path.with_name(
                f".{journal_path.name}.staged.live-start-atomic.tmp"
            ),
            parent_identity=tuple(recovery["planned_journal_successor_parent_identity"]),
            predecessor_identity=None,
            predecessor_size=None,
            predecessor_sha256=None,
            planned_successor_size=int(recovery["planned_journal_successor_size"]),
            planned_successor_sha256=str(recovery["planned_journal_successor_sha256"]),
            commit_mode="create_no_replace",
        )
    else:
        if (
            custom_config_parent_identity is None
            or transactions_parent_identity is None
        ):
            raise ValueError("runtime_prior_owner_ini_parent_missing")
        interim = _seal_apply_recovery_successor(
            recovery,
            changes={
                "action_index": int(recovery["action_index"]) + 1,
                "external_file_action": None,
                "successor_attempt_record_path": str(final_path),
                "successor_attempt_record_identity": final_identity,
                "successor_attempt_record_sha256": digest,
            },
        )
        ini_path = Path(str(recovery["runtime_root"])) / "CustomConfig" / "deck_config.ini"
        journal = _bound_recovery_journal(interim)
        current_ini = read_deck_config(ini_path, deck_name=journal.deck_name)
        if (
            current_ini.existed != (journal.previous_ini_sha256 is not None)
            or current_ini.sha256 != journal.previous_ini_sha256
            or current_ini.selected_config_dir != journal.previous_config_dir
        ):
            raise ValueError("runtime_suffix_predecessor_changed")
        ini_payload = render_deck_config(
            current_ini,
            deck_name=journal.deck_name,
            config_dir=journal.next_config_dir,
        )
        next_external = _plan_suffix_external(
            interim,
            final_path=ini_path,
            payload=ini_payload,
            expected_parent_identity=custom_config_parent_identity,
            expected_predecessor_snapshot=current_ini,
        )
        ini_journal_payload = runtime_transaction_journal_bytes(
            replace(
                journal,
                phase=RuntimeTransactionPhase.INI_COMMITTED,
                target_identity=tuple(
                    recovery["successor_renamed_target_identity"]
                ),
                owns_target=False,
            )
        )
    successor = _seal_apply_recovery_successor(
        recovery,
        changes={
            "action_index": int(recovery["action_index"]) + 1,
            "expected_action": (
                "materialize_file_action_staging"
                if expected_state == "PRIOR_OWNER_BOUND"
                else "materialize_file_action_staging"
            ),
            "external_file_action": next_external,
            "successor_attempt_record_path": str(final_path),
            "successor_attempt_record_identity": final_identity,
            "successor_attempt_record_sha256": digest,
            **(
                {
                    "planned_journal_successor_path": str(
                        recovery["successor_journal_path"]
                    ),
                    "planned_journal_successor_parent_identity": (
                        transactions_parent_identity
                    ),
                    "planned_journal_successor_phase": (
                        RuntimeTransactionPhase.INI_COMMITTED.name
                    ),
                    "planned_journal_successor_size": len(ini_journal_payload),
                    "planned_journal_successor_sha256": (
                        "sha256:"
                        + hashlib.sha256(ini_journal_payload).hexdigest()
                    ),
                }
                if expected_state == "PRIOR_OWNER_BOUND"
                else {}
            ),
        },
    )
    return RuntimeApplyRecoveryPhysicalPostcondition(
        action=action,
        evidence={"apply_recovery": successor},
    )


def _require_new_target_prefix_absent(
    recovery: Mapping[str, Any],
    *,
    allow_bound_candidate: bool = False,
    allow_bound_target: bool = False,
) -> None:
    if recovery.get("install_route") != "new_target":
        raise ValueError("runtime_initial_retention_route_invalid")
    candidate = recovery.get("candidate_path")
    target = recovery.get("renamed_target_path")
    if (
        not isinstance(candidate, str)
        or not isinstance(target, str)
        or (
            path_lexists(Path(candidate))
            and not allow_bound_candidate
        )
        or (path_lexists(Path(target)) and not allow_bound_target)
    ):
        raise ValueError("runtime_initial_new_target_surface_changed")
    if allow_bound_candidate:
        _require_runtime_layout_directory(
            Path(candidate),
            expected_parent_identity=tuple(
                recovery["candidate_parent_identity"]
            ),
            expected_identity=tuple(
                recovery["successor_candidate_identity"]
            ),
            require_empty=(
                recovery.get("candidate_tree_cursor") in {None, 0}
            ),
        )


def _execute_created_candidate_action(
    *,
    recovery: Mapping[str, Any],
) -> RuntimeApplyRecoveryPhysicalPostcondition:
    candidate = Path(str(recovery.get("candidate_path")))
    parent_identity = tuple(recovery.get("candidate_parent_identity", ()))
    if (
        recovery.get("install_route") != "new_target"
        or recovery.get("expected_action") != "bind_created_candidate"
        or recovery.get("external_file_action") is not None
        or recovery.get("predecessor_candidate_identity") is not None
        or recovery.get("successor_candidate_identity") is not None
        or not candidate.is_absolute()
        or len(parent_identity) != 3
        or path_identity(candidate.parent) != parent_identity
    ):
        raise ValueError("runtime_candidate_create_cursor_invalid")
    if path_lexists(candidate):
        identity = _require_runtime_layout_directory(
            candidate,
            expected_parent_identity=parent_identity,
            expected_identity=None,
            require_empty=True,
        )
    else:
        identity = secure_create_directory(
            candidate,
            expected_parent_identity=parent_identity,
        )
        _require_runtime_layout_directory(
            candidate,
            expected_parent_identity=parent_identity,
            expected_identity=identity,
            require_empty=True,
        )
    bound_raw = _retention_bytes_for_recovery_action(
        {
            **dict(recovery),
            "successor_candidate_identity": identity,
        },
        state="CANDIDATE_BOUND",
    )
    retention_path = Path(str(recovery["successor_attempt_record_path"]))
    external = _build_external_file_action(
        action_kind="materialize_file_action_staging",
        action_index=int(recovery["action_index"]) + 1,
        final_path=retention_path,
        staging_path=retention_path.with_name(f"{retention_path.name}.staged"),
        inner_temp_path=retention_path.with_name(
            f".{retention_path.name}.staged.live-start-atomic.tmp"
        ),
        parent_identity=path_identity(retention_path.parent),
        predecessor_identity=tuple(recovery["successor_attempt_record_identity"]),
        predecessor_size=retention_path.stat().st_size,
        predecessor_sha256=str(recovery["successor_attempt_record_sha256"]),
        planned_successor_size=len(bound_raw),
        planned_successor_sha256=(
            "sha256:" + hashlib.sha256(bound_raw).hexdigest()
        ),
        commit_mode="replace_exact",
    )
    successor = _seal_apply_recovery_successor(
        recovery,
        changes={
            "action_index": int(recovery["action_index"]) + 1,
            "expected_action": "materialize_file_action_staging",
            "successor_candidate_identity": identity,
            "external_file_action": external,
        },
    )
    return RuntimeApplyRecoveryPhysicalPostcondition(
        action="bind_created_candidate",
        evidence={"apply_recovery": successor},
    )


def _candidate_manifest_from_pair(
    *,
    package_lease: PackageInputLease,
    deck_name: str,
) -> tuple[Mapping[str, Any], str]:
    binding = _require_active_package_input_lease(package_lease)
    if binding.snapshot is None:
        raise ValueError("runtime_candidate_package_lease_invalid")
    spec = _runtime_package_spec(verify_tree_manifest(binding.snapshot))
    if spec.deck_name != deck_name:
        raise ValueError("runtime_candidate_package_changed")
    source_root = binding.package_root / "CustomConfig" / spec.logical_config_dir
    source_root_identity = _require_runtime_layout_directory(
        source_root,
        expected_parent_identity=path_identity(source_root.parent),
        expected_identity=None,
        require_empty=False,
    )
    file_by_path = {row.relative_path: row for row in spec.files}
    paths = set(file_by_path)
    for relative in tuple(paths):
        parent = Path(relative).parent
        while parent != Path("."):
            paths.add(parent.as_posix())
            parent = parent.parent
    actual_paths: set[str] = set()
    pending = [(source_root, source_root_identity, Path("."))]
    maximum_entries = len(paths)
    while pending:
        directory, directory_identity, relative_parent = pending.pop()
        if path_identity(directory) != directory_identity:
            raise ValueError("runtime_candidate_package_changed")
        with os.scandir(directory) as iterator:
            for row in iterator:
                relative_path = (
                    Path(row.name)
                    if relative_parent == Path(".")
                    else relative_parent / row.name
                )
                relative = relative_path.as_posix()
                if relative in actual_paths:
                    raise ValueError(
                        "runtime_candidate_package_membership_changed"
                    )
                actual_paths.add(relative)
                if len(actual_paths) > maximum_entries:
                    raise ValueError(
                        "runtime_candidate_package_membership_changed"
                    )
                status = row.stat(follow_symlinks=False)
                if status_is_reparse(status):
                    raise ValueError("runtime_candidate_package_changed")
                if stat.S_ISDIR(status.st_mode):
                    child = Path(row.path)
                    child_identity = path_identity_from_status(status)
                    _require_runtime_layout_directory(
                        child,
                        expected_parent_identity=directory_identity,
                        expected_identity=child_identity,
                        require_empty=False,
                    )
                    pending.append((child, child_identity, relative_path))
                elif not stat.S_ISREG(status.st_mode):
                    raise ValueError("runtime_candidate_package_changed")
        if path_identity(directory) != directory_identity:
            raise ValueError("runtime_candidate_package_changed")
    if actual_paths != paths:
        raise ValueError("runtime_candidate_package_membership_changed")
    entries: list[dict[str, Any]] = []
    for relative in sorted(paths):
        source = source_root / Path(relative)
        if relative in file_by_path:
            expected = file_by_path[relative]
            status = plain_file_status(source)
            identity = path_identity_from_status(status)
            require_no_alternate_data_streams(
                source,
                expected_identity=identity,
                expected_parent_identity=path_identity(source.parent),
                directory=False,
                expected_size=status.st_size,
            )
            raw = read_file_no_follow(
                source,
                expected_status=status,
                maximum_size=max(expected.size, 1),
            )
            digest = "sha256:" + hashlib.sha256(raw).hexdigest()
            if len(raw) != expected.size or digest != "sha256:" + expected.sha256:
                raise ValueError("runtime_candidate_package_changed")
            kind = "file"
            size = len(raw)
        else:
            identity = _require_runtime_layout_directory(
                source,
                expected_parent_identity=path_identity(source.parent),
                expected_identity=None,
                require_empty=False,
            )
            kind = "directory"
            size = 0
            digest = "sha256:" + hashlib.sha256(b"").hexdigest()
        entries.append(
            {
                "relative_path": relative,
                "kind": kind,
                "source_identity": list(identity),
                "size": size,
                "sha256": digest,
            }
        )
    manifest = {
        "schema_version": 1,
        "manifest_kind": "hsconfig_candidate_tree",
        "entries": entries,
    }
    raw_manifest = json.dumps(
        manifest,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return MappingProxyType(manifest), (
        "sha256:" + hashlib.sha256(raw_manifest).hexdigest()
    )


def _verify_candidate_tree_prefix(
    *,
    root: Path,
    root_identity: PathIdentity,
    expected_parent_identity: PathIdentity,
    entries: tuple[Mapping[str, Any], ...],
    cursor: int,
) -> None:
    if (
        path_identity(root.parent) != expected_parent_identity
        or path_identity(root) != root_identity
        or not 0 <= cursor <= len(entries)
    ):
        raise ValueError("runtime_candidate_tree_prefix_changed")
    expected_files = tuple(
        str(row["relative_path"])
        for row in entries[:cursor]
        if row["kind"] == "file"
    )
    expected_directories = tuple(
        str(row["relative_path"])
        for row in entries[:cursor]
        if row["kind"] == "directory"
    )
    snapshot = snapshot_bounded_filesystem_package(root)
    if (
        snapshot.file_names() != expected_files
        or snapshot.directory_names != expected_directories
    ):
        raise ValueError("runtime_candidate_tree_prefix_changed")
    for row in entries[:cursor]:
        path = root / Path(str(row["relative_path"]))
        if row["kind"] == "directory":
            _require_runtime_layout_directory(
                path,
                expected_parent_identity=path_identity(path.parent),
                expected_identity=None,
                require_empty=False,
            )
            continue
        status = plain_file_status(path)
        identity = path_identity_from_status(status)
        require_no_alternate_data_streams(
            path,
            expected_identity=identity,
            expected_parent_identity=path_identity(path.parent),
            directory=False,
            expected_size=int(row["size"]),
        )
        raw = read_file_no_follow(
            path,
            expected_status=status,
            maximum_size=max(int(row["size"]), 1),
        )
        if (
            len(raw) != row["size"]
            or "sha256:" + hashlib.sha256(raw).hexdigest() != row["sha256"]
        ):
            raise ValueError("runtime_candidate_tree_prefix_changed")
    if (
        path_identity(root.parent) != expected_parent_identity
        or path_identity(root) != root_identity
    ):
        raise ValueError("runtime_candidate_tree_prefix_changed")


def _journal_successor_bytes(
    *,
    recovery: Mapping[str, Any],
    phase: RuntimeTransactionPhase,
    target_identity: PathIdentity | None = None,
    owns_target: bool = False,
) -> bytes:
    journal_path = Path(str(recovery["successor_journal_path"]))
    raw, identity = _read_exact_runtime_external_file(
        journal_path,
        expected_parent_identity=path_identity(journal_path.parent),
        maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
    )
    if (
        identity != tuple(recovery["successor_journal_identity"])
        or "sha256:" + hashlib.sha256(raw).hexdigest()
        != recovery["successor_journal_sha256"]
    ):
        raise ValueError("runtime_candidate_journal_changed")
    journal = parse_runtime_transaction_journal_bytes(
        raw,
        expected_transaction_id=str(recovery["apply_attempt_id"]),
    )
    successor = replace(
        journal,
        phase=phase,
        candidate_identity=(
            tuple(recovery["successor_candidate_identity"])
            if recovery.get("successor_candidate_identity") is not None
            else journal.candidate_identity
        ),
        target_identity=target_identity,
        owns_target=owns_target,
    )
    return runtime_transaction_journal_bytes(successor)


def _plan_journal_successor(
    recovery: Mapping[str, Any],
    *,
    payload: bytes,
    phase: RuntimeTransactionPhase,
    transactions_parent_identity: PathIdentity,
    next_action: str = "materialize_file_action_staging",
    changes: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    journal_path = Path(str(recovery["successor_journal_path"]))
    if path_identity(journal_path.parent) != transactions_parent_identity:
        raise ValueError("runtime_suffix_journal_parent_changed")
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    external = _build_external_file_action(
        action_kind="materialize_file_action_staging",
        action_index=int(recovery["action_index"]) + 1,
        final_path=journal_path,
        staging_path=journal_path.with_name(f"{journal_path.name}.staged"),
        inner_temp_path=journal_path.with_name(
            f".{journal_path.name}.staged.live-start-atomic.tmp"
        ),
        parent_identity=transactions_parent_identity,
        predecessor_identity=tuple(recovery["successor_journal_identity"]),
        predecessor_size=journal_path.stat().st_size,
        predecessor_sha256=str(recovery["successor_journal_sha256"]),
        planned_successor_size=len(payload),
        planned_successor_sha256=digest,
        commit_mode="replace_exact",
    )
    return _seal_apply_recovery_successor(
        recovery,
        changes={
            **dict(changes or {}),
            "action_index": int(recovery["action_index"]) + 1,
            "expected_action": next_action,
            "external_file_action": external,
            "planned_journal_successor_path": str(journal_path),
            "planned_journal_successor_parent_identity": (
                transactions_parent_identity
            ),
            "planned_journal_successor_phase": phase.name,
            "planned_journal_successor_size": len(payload),
            "planned_journal_successor_sha256": digest,
        },
    )


def _materialize_candidate_tree_entry(
    *,
    recovery: Mapping[str, Any],
    package_lease: PackageInputLease,
    deck_name: str,
    transactions_parent_identity: PathIdentity,
) -> RuntimeApplyRecoveryPhysicalPostcondition:
    manifest, manifest_sha256 = _candidate_manifest_from_pair(
        package_lease=package_lease,
        deck_name=deck_name,
    )
    entries = tuple(manifest["entries"])
    cursor = int(recovery.get("candidate_tree_cursor", -1))
    if (
        recovery.get("expected_action") != "materialize_candidate_tree_entry"
        or recovery.get("candidate_tree_manifest_sha256") != manifest_sha256
        or recovery.get("candidate_tree_entry_count") != len(entries)
        or not 0 <= cursor < len(entries)
    ):
        raise ValueError("runtime_candidate_tree_cursor_invalid")
    row = entries[cursor]
    for field, key in (
        ("relative_path", "candidate_tree_next_relative_path"),
        ("kind", "candidate_tree_next_kind"),
        ("source_identity", "candidate_tree_next_source_identity"),
        ("size", "candidate_tree_next_size"),
        ("sha256", "candidate_tree_next_sha256"),
    ):
        observed = recovery.get(key)
        expected = row[field]
        if field == "source_identity":
            observed = tuple(observed or ())
            expected = tuple(expected)
        if observed != expected:
            raise ValueError("runtime_candidate_tree_cursor_invalid")
    candidate = Path(str(recovery["candidate_path"]))
    candidate_identity = tuple(recovery["successor_candidate_identity"])
    destination = candidate / Path(str(row["relative_path"]))
    _verify_candidate_tree_prefix(
        root=candidate,
        root_identity=candidate_identity,
        expected_parent_identity=tuple(recovery["candidate_parent_identity"]),
        entries=entries,
        cursor=(cursor + 1 if path_lexists(destination) else cursor),
    )
    if path_identity(destination.parent) != tuple(
        recovery["candidate_tree_next_parent_identity"]
    ):
        raise ValueError("runtime_candidate_tree_parent_changed")
    if row["kind"] == "directory":
        if path_lexists(destination):
            successor_identity = _require_runtime_layout_directory(
                destination,
                expected_parent_identity=path_identity(destination.parent),
                expected_identity=None,
                require_empty=True,
            )
        else:
            successor_identity = secure_create_directory(
                destination,
                expected_parent_identity=path_identity(destination.parent),
            )
    else:
        source_root = package_lease.package_root / "CustomConfig" / deck_name
        source = package_lease.package_root / "CustomConfig" / Path(
            str(row["relative_path"])
        ).parent
        del source_root, source
        binding = _require_active_package_input_lease(package_lease)
        spec = _runtime_package_spec(verify_tree_manifest(binding.snapshot))
        source_path = (
            binding.package_root
            / "CustomConfig"
            / spec.logical_config_dir
            / Path(str(row["relative_path"]))
        )
        source_status = plain_file_status(source_path)
        if path_identity_from_status(source_status) != tuple(row["source_identity"]):
            raise ValueError("runtime_candidate_source_changed")
        raw = read_file_no_follow(
            source_path,
            expected_status=source_status,
            maximum_size=max(int(row["size"]), 1),
        )
        if path_lexists(destination):
            status = plain_file_status(destination)
            existing = read_file_no_follow(
                destination,
                expected_status=status,
                maximum_size=max(int(row["size"]), 1),
            )
            if existing != raw:
                raise ValueError("runtime_candidate_leaf_changed")
            successor_identity = path_identity_from_status(status)
        else:
            descriptor = secure_open_file_descriptor(
                destination,
                create=True,
                write=True,
                expected_parent_identity=path_identity(destination.parent),
            )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
                successor_identity = path_identity_from_status(
                    os.fstat(handle.fileno())
                )
    next_cursor = cursor + 1
    _verify_candidate_tree_prefix(
        root=candidate,
        root_identity=candidate_identity,
        expected_parent_identity=tuple(recovery["candidate_parent_identity"]),
        entries=entries,
        cursor=next_cursor,
    )
    changes: dict[str, Any] = {
        "action_index": int(recovery["action_index"]) + 1,
        "candidate_tree_cursor": next_cursor,
        "candidate_tree_next_successor_identity": successor_identity,
    }
    if next_cursor < len(entries):
        next_row = entries[next_cursor]
        next_path = candidate / Path(str(next_row["relative_path"]))
        changes.update(
            {
                "expected_action": "materialize_candidate_tree_entry",
                "candidate_tree_next_relative_path": next_row["relative_path"],
                "candidate_tree_next_kind": next_row["kind"],
                "candidate_tree_next_source_identity": next_row["source_identity"],
                "candidate_tree_next_size": next_row["size"],
                "candidate_tree_next_sha256": next_row["sha256"],
                "candidate_tree_next_parent_identity": path_identity(
                    next_path.parent
                ),
                "candidate_tree_next_successor_identity": None,
            }
        )
        successor = _seal_apply_recovery_successor(recovery, changes=changes)
    else:
        payload = _journal_successor_bytes(
            recovery=recovery,
            phase=RuntimeTransactionPhase.RUNTIME_STAGED,
        )
        successor = _plan_journal_successor(
            recovery,
            payload=payload,
            phase=RuntimeTransactionPhase.RUNTIME_STAGED,
            transactions_parent_identity=transactions_parent_identity,
            changes={
                **changes,
                "candidate_tree_next_relative_path": None,
                "candidate_tree_next_kind": None,
                "candidate_tree_next_source_identity": None,
                "candidate_tree_next_size": None,
                "candidate_tree_next_sha256": None,
                "candidate_tree_next_parent_identity": None,
                "candidate_tree_next_successor_identity": None,
            },
        )
    return RuntimeApplyRecoveryPhysicalPostcondition(
        action="materialize_candidate_tree_entry",
        evidence={"apply_recovery": successor},
    )


def _verify_candidate_tree_action(
    *,
    recovery: Mapping[str, Any],
    package_lease: PackageInputLease,
    deck_name: str,
    transactions_parent_identity: PathIdentity,
) -> RuntimeApplyRecoveryPhysicalPostcondition:
    manifest, digest = _candidate_manifest_from_pair(
        package_lease=package_lease, deck_name=deck_name
    )
    entries = tuple(manifest["entries"])
    if (
        recovery.get("candidate_tree_manifest_sha256") != digest
        or recovery.get("candidate_tree_cursor") != len(entries)
        or recovery.get("candidate_tree_entry_count") != len(entries)
    ):
        raise ValueError("runtime_candidate_tree_verification_invalid")
    _verify_candidate_tree_prefix(
        root=Path(str(recovery["candidate_path"])),
        root_identity=tuple(recovery["successor_candidate_identity"]),
        expected_parent_identity=tuple(recovery["candidate_parent_identity"]),
        entries=entries,
        cursor=len(entries),
    )
    payload = _journal_successor_bytes(
        recovery=recovery, phase=RuntimeTransactionPhase.RUNTIME_VERIFIED
    )
    successor = _plan_journal_successor(
        recovery,
        payload=payload,
        phase=RuntimeTransactionPhase.RUNTIME_VERIFIED,
        transactions_parent_identity=transactions_parent_identity,
        changes={"candidate_tree_verified_sha256": digest},
    )
    return RuntimeApplyRecoveryPhysicalPostcondition(
        action="verify_candidate_tree", evidence={"apply_recovery": successor}
    )


def _rename_candidate_to_target(
    *,
    recovery: Mapping[str, Any],
    package_lease: PackageInputLease,
    deck_name: str,
    custom_config_parent_identity: PathIdentity,
    transactions_parent_identity: PathIdentity,
) -> RuntimeApplyRecoveryPhysicalPostcondition:
    manifest, digest = _candidate_manifest_from_pair(
        package_lease=package_lease, deck_name=deck_name
    )
    entries = tuple(manifest["entries"])
    if recovery.get("candidate_tree_verified_sha256") != digest:
        raise ValueError("runtime_candidate_tree_not_verified")
    candidate = Path(str(recovery["candidate_path"]))
    target = Path(str(recovery["renamed_target_path"]))
    candidate_identity = tuple(recovery["successor_candidate_identity"])
    candidate_parent_identity = tuple(recovery["candidate_parent_identity"])
    if path_identity(candidate.parent) != candidate_parent_identity:
        raise ValueError("runtime_candidate_parent_changed")
    if path_lexists(candidate):
        _verify_candidate_tree_prefix(
            root=candidate,
        root_identity=candidate_identity,
        expected_parent_identity=candidate_parent_identity,
            entries=entries,
            cursor=len(entries),
        )
        if path_lexists(target):
            raise ValueError("runtime_candidate_target_changed")
        secure_replace(
            candidate,
            target,
            expected_source_identity=candidate_identity,
            expected_source_parent_identity=candidate_parent_identity,
            expected_target_parent_identity=custom_config_parent_identity,
            expected_target_absent=True,
        )
    target_identity = _require_runtime_layout_directory(
        target,
        expected_parent_identity=custom_config_parent_identity,
        expected_identity=candidate_identity,
        require_empty=False,
    )
    _verify_candidate_tree_prefix(
        root=target,
        root_identity=target_identity,
        expected_parent_identity=custom_config_parent_identity,
        entries=entries,
        cursor=len(entries),
    )
    if path_lexists(candidate):
        raise ValueError("runtime_candidate_rename_changed")
    if path_identity(candidate.parent) != candidate_parent_identity:
        raise ValueError("runtime_candidate_parent_changed")
    payload = _journal_successor_bytes(
        recovery=recovery,
        phase=RuntimeTransactionPhase.RUNTIME_VERIFIED,
        target_identity=target_identity,
        owns_target=True,
    )
    successor = _plan_journal_successor(
        recovery,
        payload=payload,
        phase=RuntimeTransactionPhase.RUNTIME_VERIFIED,
        transactions_parent_identity=transactions_parent_identity,
        changes={
            "predecessor_candidate_identity": candidate_identity,
            "successor_candidate_identity": None,
            "predecessor_renamed_target_identity": None,
            "successor_renamed_target_identity": target_identity,
        },
    )
    return RuntimeApplyRecoveryPhysicalPostcondition(
        action="rename_candidate_to_target", evidence={"apply_recovery": successor}
    )


def _bind_renamed_target(
    *,
    recovery: Mapping[str, Any],
    package_lease: PackageInputLease,
    deck_name: str,
    transaction_id: str,
    custom_config_parent_identity: PathIdentity,
) -> RuntimeApplyRecoveryPhysicalPostcondition:
    manifest, digest = _candidate_manifest_from_pair(
        package_lease=package_lease, deck_name=deck_name
    )
    entries = tuple(manifest["entries"])
    if (
        digest != recovery.get("candidate_tree_manifest_sha256")
        or digest != recovery.get("candidate_tree_verified_sha256")
        or len(entries) != recovery.get("candidate_tree_entry_count")
        or path_lexists(Path(str(recovery["candidate_path"])))
        or path_identity(Path(str(recovery["candidate_path"])).parent)
        != tuple(recovery["candidate_parent_identity"])
    ):
        raise ValueError("runtime_target_owner_manifest_changed")
    target = Path(str(recovery["renamed_target_path"]))
    target_identity = tuple(recovery["successor_renamed_target_identity"])
    _verify_candidate_tree_prefix(
        root=target,
        root_identity=target_identity,
        expected_parent_identity=custom_config_parent_identity,
        entries=entries,
        cursor=len(entries),
    )
    external = recovery.get("external_file_action")
    if not isinstance(external, Mapping):
        raise ValueError("runtime_target_owner_cursor_invalid")
    commit_manifest, commit_digest = _candidate_manifest_from_pair(
        package_lease=package_lease, deck_name=deck_name
    )
    commit_entries = tuple(commit_manifest["entries"])
    if (
        commit_digest != digest
        or commit_entries != entries
        or path_lexists(Path(str(recovery["candidate_path"])))
        or path_identity(Path(str(recovery["candidate_path"])).parent)
        != tuple(recovery["candidate_parent_identity"])
    ):
        raise ValueError("runtime_target_owner_manifest_changed")
    _verify_candidate_tree_prefix(
        root=target,
        root_identity=target_identity,
        expected_parent_identity=custom_config_parent_identity,
        entries=commit_entries,
        cursor=len(commit_entries),
    )
    runtime_root = Path(str(recovery["runtime_root"]))
    ini_path = runtime_root / "CustomConfig" / "deck_config.ini"
    if path_identity(ini_path.parent) != custom_config_parent_identity:
        raise ValueError("runtime_ini_parent_changed")
    committed = _execute_bound_controller_journal_action(
        external_file_action=external, transaction_id=transaction_id
    )
    journal = committed.journal
    if (
        journal is None
        or journal.phase != RuntimeTransactionPhase.RUNTIME_VERIFIED
        or journal.target_identity != target_identity
        or journal.owns_target
        is not (recovery.get("install_route") != "prior_owner")
    ):
        raise ValueError("runtime_target_owner_journal_invalid")
    current_ini = read_deck_config(ini_path, deck_name=deck_name)
    next_ini = render_deck_config(
        current_ini,
        deck_name=deck_name,
        config_dir=target.name,
    )
    ini_digest = "sha256:" + hashlib.sha256(next_ini).hexdigest()
    ini_journal_payload = runtime_transaction_journal_bytes(
        replace(
            journal,
            phase=RuntimeTransactionPhase.INI_COMMITTED,
            target_identity=target_identity,
            owns_target=True,
        )
    )
    ini_journal_digest = (
        "sha256:" + hashlib.sha256(ini_journal_payload).hexdigest()
    )
    ini_exists = path_lexists(ini_path)
    next_external = _build_external_file_action(
        action_kind="materialize_file_action_staging",
        action_index=int(recovery["action_index"]) + 1,
        final_path=ini_path,
        staging_path=ini_path.with_name(f"{ini_path.name}.staged"),
        inner_temp_path=ini_path.with_name(
            f".{ini_path.name}.staged.live-start-atomic.tmp"
        ),
        parent_identity=custom_config_parent_identity,
        predecessor_identity=(path_identity(ini_path) if ini_exists else None),
        predecessor_size=(ini_path.stat().st_size if ini_exists else None),
        predecessor_sha256=(
            "sha256:" + current_ini.sha256 if ini_exists else None
        ),
        planned_successor_size=len(next_ini),
        planned_successor_sha256=ini_digest,
        commit_mode=("replace_exact" if ini_exists else "create_no_replace"),
    )
    successor = _seal_apply_recovery_successor(
        recovery,
        changes={
            "action_index": int(recovery["action_index"]) + 1,
            "expected_action": "materialize_file_action_staging",
            "external_file_action": next_external,
            "predecessor_renamed_target_identity": target_identity,
            "successor_journal_path": str(committed.journal_path),
            "successor_journal_identity": committed.journal_identity,
            "successor_journal_sha256": committed.journal_sha256,
            "planned_journal_successor_path": str(committed.journal_path),
            "planned_journal_successor_parent_identity": (
                tuple(external["parent_identity"])
            ),
            "planned_journal_successor_phase": (
                RuntimeTransactionPhase.INI_COMMITTED.name
            ),
            "planned_journal_successor_size": len(ini_journal_payload),
            "planned_journal_successor_sha256": ini_journal_digest,
        },
    )
    return RuntimeApplyRecoveryPhysicalPostcondition(
        action="bind_renamed_target", evidence={"apply_recovery": successor}
    )


def _bound_recovery_journal(
    recovery: Mapping[str, Any],
) -> RuntimeTransactionJournal:
    path = Path(str(recovery["successor_journal_path"]))
    raw, identity = _read_exact_runtime_external_file(
        path,
        expected_parent_identity=path_identity(path.parent),
        maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
    )
    if (
        identity != tuple(recovery["successor_journal_identity"])
        or "sha256:" + hashlib.sha256(raw).hexdigest()
        != recovery["successor_journal_sha256"]
    ):
        raise ValueError("runtime_suffix_journal_changed")
    return parse_runtime_transaction_journal_bytes(
        raw,
        expected_transaction_id=str(recovery["apply_attempt_id"]),
    )


def _runtime_state_successor_bytes(
    recovery: Mapping[str, Any],
) -> bytes:
    journal = _bound_recovery_journal(recovery)
    current = read_runtime_state(Path(str(recovery["runtime_root"])))
    decks = [] if current is None else list(current.decks)
    decks = [
        deck
        for deck in decks
        if deck.state_key.casefold() != journal.state_key.casefold()
        and deck.deck_name.casefold() != journal.deck_name.casefold()
    ]
    decks.append(
        RuntimeDeckState(
            state_key=journal.state_key,
            deck_name=journal.deck_name,
            config_dir=journal.next_config_dir,
            package_root_sha256=journal.package_root_sha256,
            ini_sha256=str(recovery["deck_config_ini_sha256"]).removeprefix(
                "sha256:"
            ),
        )
    )
    return serialize_runtime_state(RuntimeState(1, tuple(decks)))


def _suffix_payload_and_commit_action(
    recovery: Mapping[str, Any],
) -> tuple[bytes, str]:
    external = recovery.get("external_file_action")
    if not isinstance(external, Mapping):
        raise ValueError("runtime_suffix_external_action_invalid")
    final_path = Path(str(external["final_path"]))
    runtime_root = Path(str(recovery["runtime_root"]))
    if final_path == runtime_root / "CustomConfig" / "deck_config.ini":
        journal = _bound_recovery_journal(recovery)
        current = read_deck_config(
            final_path, deck_name=journal.deck_name
        )
        return (
            render_deck_config(
                current,
                deck_name=journal.deck_name,
                config_dir=Path(str(recovery["renamed_target_path"])).name,
            ),
            "write_deck_config_ini",
        )
    journal_path = Path(str(recovery["successor_journal_path"]))
    if final_path == journal_path:
        phase = str(recovery["planned_journal_successor_phase"])
        phase_value = {
            RuntimeTransactionPhase.INI_COMMITTED.name: (
                RuntimeTransactionPhase.INI_COMMITTED,
                "commit_ini_journal",
            ),
            RuntimeTransactionPhase.STATE_COMMITTED.name: (
                RuntimeTransactionPhase.STATE_COMMITTED,
                "commit_state_journal",
            ),
            RuntimeTransactionPhase.FINALIZED.name: (
                RuntimeTransactionPhase.FINALIZED,
                "finalize_journal",
            ),
        }.get(phase)
        if phase_value is None:
            raise ValueError("runtime_suffix_journal_phase_invalid")
        journal_phase, action = phase_value
        return (
            _journal_successor_bytes(
                recovery=recovery,
                phase=journal_phase,
                target_identity=tuple(
                    recovery["successor_renamed_target_identity"]
                ),
                owns_target=recovery.get("install_route") != "prior_owner",
            ),
            action,
        )
    state_path = runtime_root / ".hsconfig" / "state.json"
    if final_path == state_path:
        return _runtime_state_successor_bytes(recovery), "write_runtime_state"
    journal = _bound_recovery_journal(recovery)
    receipt_path = _receipt_path(runtime_root, journal.state_key)
    if final_path == receipt_path:
        ini_sha256 = str(recovery["deck_config_ini_sha256"]).removeprefix(
            "sha256:"
        )
        return (
            _receipt_bytes(_receipt_payload(journal, ini_sha256)),
            "write_last_apply_receipt",
        )
    retention_path = Path(str(recovery["successor_attempt_record_path"]))
    if final_path == retention_path:
        return (
            _retention_bytes_for_recovery_action(recovery, state="FINALIZED"),
            "finalize_attempt_record",
        )
    raise ValueError("runtime_suffix_external_path_invalid")


def _plan_suffix_external(
    recovery: Mapping[str, Any],
    *,
    final_path: Path,
    payload: bytes,
    expected_parent_identity: PathIdentity,
    expected_predecessor_snapshot: DeckConfigSnapshot | None = None,
) -> Mapping[str, Any]:
    parent_identity = tuple(expected_parent_identity)
    if path_identity(final_path.parent) != parent_identity:
        raise ValueError("runtime_suffix_parent_changed")
    if path_lexists(final_path):
        raw, identity = _read_exact_runtime_external_file(
            final_path,
            expected_parent_identity=parent_identity,
            maximum_size=_RUNTIME_EXTERNAL_FILE_ACTION_MAX_BYTES,
        )
        predecessor_size: int | None = len(raw)
        predecessor_sha256: str | None = (
            "sha256:" + hashlib.sha256(raw).hexdigest()
        )
    else:
        identity = None
        raw = None
        predecessor_size = None
        predecessor_sha256 = None
    if expected_predecessor_snapshot is not None:
        snapshot = expected_predecessor_snapshot
        if (
            snapshot.path != final_path
            or snapshot.existed != (identity is not None)
            or snapshot.content != raw
            or (
                snapshot.sha256
                != (
                    hashlib.sha256(raw).hexdigest()
                    if raw is not None
                    else None
                )
            )
            or (
                not snapshot.existed
                and snapshot.selected_config_dir is not None
            )
        ):
            raise ValueError("runtime_suffix_predecessor_changed")
    return _build_external_file_action(
        action_kind="materialize_file_action_staging",
        action_index=int(recovery["action_index"]),
        final_path=final_path,
        staging_path=final_path.with_name(f"{final_path.name}.staged"),
        inner_temp_path=final_path.with_name(
            f".{final_path.name}.staged.live-start-atomic.tmp"
        ),
        parent_identity=parent_identity,
        predecessor_identity=identity,
        predecessor_size=predecessor_size,
        predecessor_sha256=predecessor_sha256,
        planned_successor_size=len(payload),
        planned_successor_sha256=(
            "sha256:" + hashlib.sha256(payload).hexdigest()
        ),
        commit_mode=("replace_exact" if identity is not None else "create_no_replace"),
    )


def _commit_or_confirm_suffix_file(
    recovery: Mapping[str, Any],
    *,
    action: str,
) -> tuple[PathIdentity, bytes, str]:
    external = recovery.get("external_file_action")
    if (
        not isinstance(external, Mapping)
        or external.get("stage") != "STAGING_BOUND"
        or external.get("action_kind") != action
    ):
        raise ValueError("runtime_suffix_commit_cursor_invalid")
    payload, expected_action = _suffix_payload_and_commit_action(recovery)
    if expected_action != action:
        raise ValueError("runtime_suffix_commit_action_invalid")
    final_path = Path(str(external["final_path"]))
    staging_path = Path(str(external["staging_path"]))
    inner_temp_path = Path(str(external["inner_temp_path"]))
    parent_identity = tuple(external["parent_identity"])
    staging_identity = tuple(external["staging_identity"])
    no_op = (
        external.get("predecessor_state") == "exact"
        and external.get("predecessor_size") == len(payload)
        and external.get("predecessor_sha256")
        == "sha256:" + hashlib.sha256(payload).hexdigest()
    )
    if no_op:
        raw, identity = _read_exact_runtime_external_file(
            final_path,
            expected_parent_identity=parent_identity,
            maximum_size=_RUNTIME_EXTERNAL_FILE_ACTION_MAX_BYTES,
        )
        if identity != tuple(external["predecessor_identity"]):
            raise ValueError("runtime_suffix_noop_predecessor_changed")
        if path_lexists(staging_path):
            _retire_unbound_runtime_external_file(
                staging_path,
                expected_parent_identity=parent_identity,
                maximum_size=max(len(payload), 1),
                expected_size=len(payload),
                expected_sha256=(
                    "sha256:" + hashlib.sha256(payload).hexdigest()
                ),
                expected_identity=staging_identity,
            )
    elif path_lexists(final_path) and not path_lexists(staging_path):
        raw, identity = _read_exact_runtime_external_file(
            final_path,
            expected_parent_identity=parent_identity,
            maximum_size=_RUNTIME_EXTERNAL_FILE_ACTION_MAX_BYTES,
        )
        if identity != staging_identity:
            raise ValueError("runtime_suffix_committed_identity_changed")
    else:
        if external.get("commit_mode") == "create_no_replace":
            committed = atomic_commit_bound_staging_no_replace(
                path=final_path,
                staging_path=staging_path,
                expected_staging_identity=staging_identity,
                expected_size=len(payload),
                expected_sha256="sha256:" + hashlib.sha256(payload).hexdigest(),
                expected_parent_identity=parent_identity,
            )
        else:
            committed = atomic_commit_bound_staging_replace(
                path=final_path,
                staging_path=staging_path,
                expected_predecessor_identity=tuple(external["predecessor_identity"]),
                expected_staging_identity=staging_identity,
                expected_size=len(payload),
                expected_sha256="sha256:" + hashlib.sha256(payload).hexdigest(),
                expected_parent_identity=parent_identity,
            )
        identity = committed.identity
        raw, observed_identity = _read_exact_runtime_external_file(
            final_path,
            expected_parent_identity=parent_identity,
            maximum_size=_RUNTIME_EXTERNAL_FILE_ACTION_MAX_BYTES,
        )
        if observed_identity != identity:
            raise ValueError("runtime_suffix_commit_changed")
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    if raw != payload or path_lexists(staging_path) or path_lexists(inner_temp_path):
        raise ValueError("runtime_suffix_commit_changed")
    return identity, raw, digest


def _write_suffix_artifact(
    recovery: Mapping[str, Any],
    *,
    action: str,
    transactions_parent_identity: PathIdentity,
    layout_identities: Mapping[str, PathIdentity] | None = None,
) -> RuntimeApplyRecoveryPhysicalPostcondition:
    identity, raw, digest = _commit_or_confirm_suffix_file(
        recovery, action=action
    )
    if action == "write_deck_config_ini":
        journal_payload = _journal_successor_bytes(
            recovery=recovery,
            phase=RuntimeTransactionPhase.INI_COMMITTED,
            target_identity=tuple(recovery["successor_renamed_target_identity"]),
            owns_target=recovery.get("install_route") != "prior_owner",
        )
        successor = _plan_journal_successor(
            recovery,
            payload=journal_payload,
            phase=RuntimeTransactionPhase.INI_COMMITTED,
            transactions_parent_identity=transactions_parent_identity,
            changes={"deck_config_ini_sha256": digest},
        )
    elif action == "write_runtime_state":
        journal_payload = _journal_successor_bytes(
            recovery=recovery,
            phase=RuntimeTransactionPhase.STATE_COMMITTED,
            target_identity=tuple(recovery["successor_renamed_target_identity"]),
            owns_target=recovery.get("install_route") != "prior_owner",
        )
        successor = _plan_journal_successor(
            recovery,
            payload=journal_payload,
            phase=RuntimeTransactionPhase.STATE_COMMITTED,
            transactions_parent_identity=transactions_parent_identity,
            changes={"runtime_state_sha256": digest},
        )
    elif action == "write_last_apply_receipt":
        journal_payload = _journal_successor_bytes(
            recovery=recovery,
            phase=RuntimeTransactionPhase.FINALIZED,
            target_identity=tuple(recovery["successor_renamed_target_identity"]),
            owns_target=recovery.get("install_route") != "prior_owner",
        )
        successor = _plan_journal_successor(
            recovery,
            payload=journal_payload,
            phase=RuntimeTransactionPhase.FINALIZED,
            transactions_parent_identity=transactions_parent_identity,
            changes={"last_apply_receipt_sha256": digest},
        )
    elif action == "finalize_attempt_record":
        del raw
        if layout_identities is None:
            raise ValueError("runtime_owner_retirement_layout_missing")
        owner_cursor = _initial_owner_retirement_cursor(
            recovery=recovery,
            runtime_root=Path(str(recovery["runtime_root"])),
            layout_identities=layout_identities,
        )
        changes: dict[str, object] = {
            "action_index": int(recovery["action_index"]) + 1,
            "expected_action": "observe_committed",
            "external_file_action": None,
            "successor_attempt_record_identity": identity,
            "successor_attempt_record_sha256": digest,
        }
        if owner_cursor is not None:
            owner, owner_external = owner_cursor
            changes.update(
                {
                    "expected_action": "materialize_file_action_staging",
                    "owner_retirement": owner,
                    "external_file_action": owner_external,
                }
            )
        successor = _seal_apply_recovery_successor(
            recovery,
            changes=changes,
        )
    else:
        raise ValueError("runtime_suffix_artifact_action_invalid")
    return RuntimeApplyRecoveryPhysicalPostcondition(
        action=action, evidence={"apply_recovery": successor}
    )


def _commit_suffix_journal(
    recovery: Mapping[str, Any],
    *,
    action: str,
    transaction_id: str,
    layout_identities: Mapping[str, PathIdentity],
    runtime_internal_identity: PathIdentity,
    state_key: str,
) -> RuntimeApplyRecoveryPhysicalPostcondition:
    external = recovery.get("external_file_action")
    if not isinstance(external, Mapping):
        raise ValueError("runtime_suffix_journal_action_invalid")
    transactions_parent_identity = layout_identities["transactions"]
    journal_parent = Path(str(external["final_path"])).parent
    if (
        tuple(external["parent_identity"]) != transactions_parent_identity
        or tuple(recovery["planned_journal_successor_parent_identity"])
        != transactions_parent_identity
        or path_identity(journal_parent) != transactions_parent_identity
    ):
        raise ValueError("runtime_suffix_journal_parent_changed")
    expected_next_parent_identity = {
        "commit_ini_journal": runtime_internal_identity,
        "commit_state_journal": layout_identities["state_receipts"],
        "finalize_journal": layout_identities["attempt_retention"],
    }.get(action)
    if expected_next_parent_identity is None:
        raise ValueError("runtime_suffix_journal_action_invalid")
    if action == "commit_ini_journal":
        next_parent = Path(str(recovery["runtime_root"])) / ".hsconfig"
    elif action == "commit_state_journal":
        next_parent = _receipt_path(
            Path(str(recovery["runtime_root"])), state_key
        ).parent
    else:
        next_parent = Path(str(recovery["successor_attempt_record_path"])).parent
    if path_identity(next_parent) != expected_next_parent_identity:
        raise ValueError("runtime_suffix_parent_changed")
    committed = _execute_bound_controller_journal_action(
        external_file_action=external,
        transaction_id=transaction_id,
    )
    if path_identity(journal_parent) != transactions_parent_identity:
        raise ValueError("runtime_suffix_journal_parent_changed")
    journal = committed.journal
    expected_phase = {
        "commit_ini_journal": RuntimeTransactionPhase.INI_COMMITTED,
        "commit_state_journal": RuntimeTransactionPhase.STATE_COMMITTED,
        "finalize_journal": RuntimeTransactionPhase.FINALIZED,
    }.get(action)
    if journal is None or journal.phase != expected_phase:
        raise ValueError("runtime_suffix_journal_phase_invalid")
    next_journal_phase = {
        "commit_ini_journal": RuntimeTransactionPhase.STATE_COMMITTED,
        "commit_state_journal": RuntimeTransactionPhase.FINALIZED,
    }.get(action)
    next_journal_payload = (
        runtime_transaction_journal_bytes(
            replace(
                journal,
                phase=next_journal_phase,
                target_identity=tuple(
                    recovery["successor_renamed_target_identity"]
                ),
                owns_target=recovery.get("install_route") != "prior_owner",
            )
        )
        if next_journal_phase is not None
        else None
    )
    base_changes = {
        "action_index": int(recovery["action_index"]) + 1,
        "expected_action": "materialize_file_action_staging",
        "successor_journal_path": str(committed.journal_path),
        "successor_journal_identity": committed.journal_identity,
        "successor_journal_sha256": committed.journal_sha256,
        "planned_journal_successor_path": (
            str(committed.journal_path)
            if next_journal_payload is not None
            else None
        ),
        "planned_journal_successor_parent_identity": (
            transactions_parent_identity
            if next_journal_payload is not None
            else None
        ),
        "planned_journal_successor_phase": (
            next_journal_phase.name
            if next_journal_phase is not None
            else None
        ),
        "planned_journal_successor_size": (
            len(next_journal_payload)
            if next_journal_payload is not None
            else None
        ),
        "planned_journal_successor_sha256": (
            "sha256:" + hashlib.sha256(next_journal_payload).hexdigest()
            if next_journal_payload is not None
            else None
        ),
    }
    if (
        action == "finalize_journal"
        and recovery.get("install_route") == "new_target"
        and journal.owns_target is True
    ):
        base_changes.update(
            {
                "successor_target_owner_journal_path": str(
                    committed.journal_path
                ),
                "successor_target_owner_journal_identity": (
                    committed.journal_identity
                ),
                "successor_target_owner_journal_sha256": (
                    committed.journal_sha256
                ),
            }
        )
    interim = _seal_apply_recovery_successor(
        recovery,
        changes={**base_changes, "external_file_action": None},
    )
    if action == "commit_ini_journal":
        final_path = Path(str(recovery["runtime_root"])) / ".hsconfig" / "state.json"
        payload = _runtime_state_successor_bytes(interim)
        expected_parent_identity = expected_next_parent_identity
    elif action == "commit_state_journal":
        final_path = _receipt_path(
            Path(str(recovery["runtime_root"])), journal.state_key
        )
        ini_sha256 = str(recovery["deck_config_ini_sha256"]).removeprefix(
            "sha256:"
        )
        payload = _receipt_bytes(_receipt_payload(journal, ini_sha256))
        expected_parent_identity = expected_next_parent_identity
    else:
        final_path = Path(str(recovery["successor_attempt_record_path"]))
        payload = _retention_bytes_for_recovery_action(
            interim, state="FINALIZED"
        )
        expected_parent_identity = expected_next_parent_identity
    successor = _seal_apply_recovery_successor(
        recovery,
        changes={
            **base_changes,
            "external_file_action": _plan_suffix_external(
                interim,
                final_path=final_path,
                payload=payload,
                expected_parent_identity=expected_parent_identity,
            ),
        },
    )
    return RuntimeApplyRecoveryPhysicalPostcondition(
        action=action, evidence={"apply_recovery": successor}
    )


def _commit_bound_candidate_fence(
    *,
    recovery: Mapping[str, Any],
    package_lease: PackageInputLease,
    deck_name: str,
) -> RuntimeApplyRecoveryPhysicalPostcondition:
    external = recovery.get("external_file_action")
    if (
        not isinstance(external, Mapping)
        or external.get("stage") != "STAGING_BOUND"
        or external.get("action_kind") != "bind_candidate_fence"
        or recovery.get("successor_candidate_identity") is None
    ):
        raise ValueError("runtime_candidate_fence_cursor_invalid")
    _require_new_target_prefix_absent(
        recovery,
        allow_bound_candidate=True,
    )
    manifest, manifest_sha256 = _candidate_manifest_from_pair(
        package_lease=package_lease,
        deck_name=deck_name,
    )
    final_path = Path(str(external["final_path"]))
    staging_path = Path(str(external["staging_path"]))
    parent_identity = tuple(external["parent_identity"])
    staging_identity = tuple(external["staging_identity"])
    if path_lexists(final_path) and not path_lexists(staging_path):
        raw, identity = _read_exact_runtime_external_file(
            final_path,
            expected_parent_identity=parent_identity,
            maximum_size=RUNTIME_ATTEMPT_RETENTION_MAX_BYTES,
        )
        if (
            identity != staging_identity
            or len(raw) != external.get("planned_successor_size")
            or "sha256:" + hashlib.sha256(raw).hexdigest()
            != external.get("planned_successor_sha256")
        ):
            raise ValueError("runtime_candidate_fence_commit_changed")
    else:
        committed = atomic_commit_bound_staging_replace(
            path=final_path,
            staging_path=staging_path,
            expected_predecessor_identity=tuple(external["predecessor_identity"]),
            expected_staging_identity=staging_identity,
            expected_size=int(external["staging_size"]),
            expected_sha256=str(external["staging_sha256"]),
            expected_parent_identity=parent_identity,
        )
        raw, identity = _read_exact_runtime_external_file(
            final_path,
            expected_parent_identity=parent_identity,
            maximum_size=RUNTIME_ATTEMPT_RETENTION_MAX_BYTES,
        )
        if identity != committed.identity:
            raise ValueError("runtime_candidate_fence_commit_changed")
    record = _runtime_attempt_retention_from_raw(
        raw,
        runtime_root=Path(str(recovery["runtime_root"])),
    )
    if identity != staging_identity or record.state != "CANDIDATE_BOUND":
        raise ValueError("runtime_candidate_fence_commit_changed")
    entries = manifest["entries"]
    first = entries[0]
    candidate_identity = tuple(recovery["successor_candidate_identity"])
    successor = _seal_apply_recovery_successor(
        recovery,
        changes={
            "action_index": int(recovery["action_index"]) + 1,
            "expected_action": "materialize_candidate_tree_entry",
            "external_file_action": None,
            "successor_attempt_record_identity": identity,
            "successor_attempt_record_sha256": (
                "sha256:" + hashlib.sha256(raw).hexdigest()
            ),
            "candidate_tree_manifest_sha256": manifest_sha256,
            "candidate_tree_entry_count": len(entries),
            "candidate_tree_cursor": 0,
            "candidate_tree_next_relative_path": first["relative_path"],
            "candidate_tree_next_kind": first["kind"],
            "candidate_tree_next_source_identity": first["source_identity"],
            "candidate_tree_next_size": first["size"],
            "candidate_tree_next_sha256": first["sha256"],
            "candidate_tree_next_parent_identity": candidate_identity,
            "candidate_tree_next_successor_identity": None,
        },
    )
    return RuntimeApplyRecoveryPhysicalPostcondition(
        action="bind_candidate_fence",
        evidence={"apply_recovery": successor},
    )


def _controller_journal_recovery_postcondition(
    *,
    recovery: Mapping[str, Any],
    transaction_id: str,
    attempt_retention_parent_identity: PathIdentity,
) -> RuntimeApplyRecoveryPhysicalPostcondition:
    external = recovery.get("external_file_action")
    if not isinstance(external, Mapping):
        raise ValueError("runtime_controller_journal_action_invalid")
    committed = _execute_bound_controller_journal_action(
        external_file_action=external,
        transaction_id=transaction_id,
    )
    journal = committed.journal
    if journal is None:
        raise ValueError("runtime_controller_journal_commit_missing")
    prior_owner_prepared = (
        journal.phase == RuntimeTransactionPhase.PREPARED
        and recovery.get("install_route") == "prior_owner"
    )
    next_action = {
        RuntimeTransactionPhase.PREPARED: "bind_created_candidate",
        RuntimeTransactionPhase.RUNTIME_STAGED: "verify_candidate_tree",
        RuntimeTransactionPhase.RUNTIME_VERIFIED: "rename_candidate_to_target",
    }.get(journal.phase)
    if next_action is None or (
        journal.phase == RuntimeTransactionPhase.PREPARED
        and recovery.get("install_route") not in {"new_target", "prior_owner"}
    ):
        raise ValueError("runtime_controller_journal_successor_unsupported")
    changes: dict[str, Any] = {
        "action_index": int(recovery.get("action_index")) + 1,
        "expected_action": next_action,
        "external_file_action": None,
        "successor_journal_path": str(committed.journal_path),
        "successor_journal_identity": committed.journal_identity,
        "successor_journal_sha256": committed.journal_sha256,
        "planned_journal_successor_path": None,
        "planned_journal_successor_parent_identity": None,
        "planned_journal_successor_phase": None,
        "planned_journal_successor_size": None,
        "planned_journal_successor_sha256": None,
    }
    if prior_owner_prepared:
        bound_recovery = {
            **dict(recovery),
            "successor_journal_path": str(committed.journal_path),
            "successor_journal_identity": committed.journal_identity,
            "successor_journal_sha256": committed.journal_sha256,
        }
        bound_raw = _retention_bytes_for_recovery_action(
            bound_recovery,
            state="PRIOR_OWNER_BOUND",
        )
        retention_path = Path(str(recovery["successor_attempt_record_path"]))
        changes.update(
            {
                "expected_action": "materialize_file_action_staging",
                "external_file_action": _build_external_file_action(
                    action_kind="materialize_file_action_staging",
                    action_index=int(recovery["action_index"]) + 1,
                    final_path=retention_path,
                    staging_path=retention_path.with_name(
                        f"{retention_path.name}.staged"
                    ),
                    inner_temp_path=retention_path.with_name(
                        f".{retention_path.name}.staged.live-start-atomic.tmp"
                    ),
                    parent_identity=attempt_retention_parent_identity,
                    predecessor_identity=tuple(
                        recovery["successor_attempt_record_identity"]
                    ),
                    predecessor_size=retention_path.stat().st_size,
                    predecessor_sha256=str(
                        recovery["successor_attempt_record_sha256"]
                    ),
                    planned_successor_size=len(bound_raw),
                    planned_successor_sha256=(
                        "sha256:" + hashlib.sha256(bound_raw).hexdigest()
                    ),
                    commit_mode="replace_exact",
                ),
            }
        )
    for field_name in (
        "path",
        "parent_identity",
        "identity",
        "size",
        "sha256",
        "classification",
        "origin",
    ):
        changes[f"successor_transaction_temp_{field_name}"] = None
    successor = _seal_apply_recovery_successor(
        recovery,
        changes=changes,
    )
    return RuntimeApplyRecoveryPhysicalPostcondition(
        action="advance_controller_transaction_journal_write",
        evidence={"apply_recovery": successor},
    )


def _runtime_observation_recovery_postcondition(
    *,
    recovery: Mapping[str, Any],
    action: str,
    observation: _ExactPairedRuntimeAttemptObservation,
    package_lease: PackageInputLease,
    persisted: LiveStartSession,
    profile_lease: OperatorProfileLease,
    session_root: Path,
    lease_pair: ControllerApplyLeasePair,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
) -> RuntimeApplyRecoveryPhysicalPostcondition:
    journal = observation.transaction.journal
    clear_external_file_action = False
    if action == "observe_not_committed":
        if observation.transaction.legacy_temp_path is not None:
            raise ValueError("runtime_not_committed_observation_invalid")
        exact_new_target = recovery.get("install_route") == "new_target"
        if exact_new_target:
            if _prove_exact_new_target_precommit_no_commit(
                recovery=recovery,
                observation=observation,
                package_lease=package_lease,
                persisted=persisted,
                profile_lease=profile_lease,
                session_root=session_root,
                lease_pair=lease_pair,
                runtime_admission=runtime_admission,
            ) != "not_committed":
                raise ValueError("runtime_not_committed_observation_invalid")
            clear_external_file_action = (
                recovery.get("external_file_action") is not None
            )
        elif recovery.get("install_route") == "prior_owner":
            layout = persisted.runtime_layout_bootstrap
            if not isinstance(layout, Mapping):
                raise ValueError("runtime_not_committed_observation_invalid")
            layout_identities = _validated_complete_layout_successor_identities(
                layout=layout,
                runtime_root=runtime_admission.runtime_root,
            )
            _require_retained_child_absent(
                runtime_admission.runtime_root
                / ".hsconfig"
                / "staging"
                / str(recovery["apply_attempt_id"]),
                expected_parent_identity=layout_identities["staging"],
            )
            prior_owner_bound_status = (
                _prove_exact_prior_owner_bound_pre_ini_no_commit(
                    recovery=recovery,
                    observation=observation,
                    persisted=persisted,
                    lease_pair=lease_pair,
                    runtime_admission=runtime_admission,
                )
            )
            if prior_owner_bound_status == "not_committed":
                clear_external_file_action = True
            elif prior_owner_bound_status is not None or (
                not _exact_abandonable_prior_owner_journal_intent(recovery)
                or not _journal_less_same_attempt_pre_apply_snapshot_is_exact(
                    recovery=recovery,
                    lease_pair=lease_pair,
                    runtime_admission=runtime_admission,
                )
            ):
                raise ValueError("runtime_not_committed_observation_invalid")
            else:
                clear_external_file_action = True
        elif journal is not None:
            raise ValueError("runtime_not_committed_observation_invalid")
        disposition = "NOT_COMMITTED"
    elif action == "observe_committed":
        if journal is None or journal.phase != RuntimeTransactionPhase.FINALIZED:
            raise ValueError("runtime_committed_observation_invalid")
        disposition = "COMMITTED"
    elif action == "observe_pending":
        if recovery.get("external_file_action") is not None:
            raise ValueError("runtime_pending_observation_external_action_invalid")
        if journal is None and observation.transaction.legacy_temp_path is None:
            raise ValueError("runtime_pending_observation_invalid")
        disposition = "COMMITTED_RECOVERY_PENDING"
    elif action == "observe_unknown":
        marker = observation.authority_contradiction
        if recovery.get("install_route") == "new_target":
            external = recovery.get("external_file_action")
            ini_external_final = _classify_new_target_ini_external_final(
                recovery=recovery,
                runtime_root=runtime_admission.runtime_root,
                deck_name=persisted.deck_name,
            )
            if marker is not None and marker.surface != "candidate_root":
                raise ValueError("runtime_unknown_observation_invalid")
            if marker is not None and ini_external_final is not None:
                raise ValueError("runtime_unknown_observation_invalid")
            if marker is None and ini_external_final == "exact":
                raise ValueError("runtime_unknown_observation_invalid")
            if marker is not None:
                unknown_status = _prove_exact_new_target_precommit_no_commit(
                    recovery=recovery,
                    observation=observation,
                    package_lease=package_lease,
                    persisted=persisted,
                    profile_lease=profile_lease,
                    session_root=session_root,
                    lease_pair=lease_pair,
                    runtime_admission=runtime_admission,
                )
                if unknown_status != "unknown":
                    raise ValueError("runtime_unknown_observation_invalid")
                clear_external_file_action = (
                    recovery.get("external_file_action") is not None
                )
            elif ini_external_final == "contradictory":
                _require_new_target_ini_external_residue(
                    recovery=recovery,
                    runtime_root=runtime_admission.runtime_root,
                )
                clear_external_file_action = True
            else:
                if isinstance(external, Mapping) and (
                    path_lexists(Path(str(external.get("staging_path"))))
                    or path_lexists(Path(str(external.get("inner_temp_path"))))
                ):
                    raise ValueError(
                        "runtime_unknown_observation_file_action_recovery_required"
                    )
                unknown_status = _prove_exact_new_target_precommit_no_commit(
                    recovery=recovery,
                    observation=observation,
                    package_lease=package_lease,
                    persisted=persisted,
                    profile_lease=profile_lease,
                    session_root=session_root,
                    lease_pair=lease_pair,
                    runtime_admission=runtime_admission,
                )
                if unknown_status != "unknown":
                    raise ValueError("runtime_unknown_observation_invalid")
                clear_external_file_action = (
                    recovery.get("external_file_action") is not None
                )
        elif recovery.get("install_route") == "prior_owner":
            layout = persisted.runtime_layout_bootstrap
            if not isinstance(layout, Mapping):
                raise ValueError("runtime_unknown_observation_invalid")
            layout_identities = _validated_complete_layout_successor_identities(
                layout=layout,
                runtime_root=runtime_admission.runtime_root,
            )
            _require_retained_child_absent(
                runtime_admission.runtime_root
                / ".hsconfig"
                / "staging"
                / str(recovery["apply_attempt_id"]),
                expected_parent_identity=layout_identities["staging"],
            )
            if marker is not None:
                if marker.surface not in {
                    "prior_owner_target",
                    "prior_owner_journal",
                }:
                    raise ValueError("runtime_unknown_observation_invalid")
                external = recovery.get("external_file_action")
                if isinstance(external, Mapping) and any(
                    path_lexists(Path(str(external.get(field_name))))
                    for field_name in ("staging_path", "inner_temp_path")
                ):
                    raise ValueError(
                        "runtime_unknown_observation_file_action_recovery_required"
                    )
                if (
                    recovery.get("successor_journal_identity") is None
                    and not _exact_abandonable_prior_owner_journal_intent(
                        recovery
                    )
                ):
                    raise ValueError("runtime_unknown_observation_invalid")
                _require_bounded_authority_marker_content_exact(
                    marker=marker,
                    recovery=recovery,
                    package_lease=package_lease,
                    deck_name=persisted.deck_name,
                    layout_identities=layout_identities,
                )
            elif (
                recovery.get("successor_journal_identity") is not None
                or not _exact_abandonable_prior_owner_journal_intent(recovery)
                or _journal_less_same_attempt_pre_apply_snapshot_is_exact(
                    recovery=recovery,
                    lease_pair=lease_pair,
                    runtime_admission=runtime_admission,
                )
            ):
                raise ValueError("runtime_unknown_observation_invalid")
            clear_external_file_action = True
        else:
            raise ValueError("runtime_unknown_observation_invalid")
        disposition = "UNKNOWN_REQUIRES_RECOVERY"
    else:
        raise ValueError("runtime_recovery_observation_action_invalid")
    changes: dict[str, Any] = {
        field_name: None
        for field_name in _APPLY_RECOVERY_FIELDS
        if field_name.startswith("successor_")
    }
    no_tree_terminal_observation = (
        action in {"observe_not_committed", "observe_unknown"}
        and recovery.get("predecessor_candidate_identity") is None
        and recovery.get("successor_candidate_identity") is None
    )
    if action in {"observe_not_committed", "observe_unknown"} and (
        clear_external_file_action or no_tree_terminal_observation
    ):
        changes["external_file_action"] = None
        changes.update(
            {
                "planned_journal_successor_path": None,
                "planned_journal_successor_parent_identity": None,
                "planned_journal_successor_phase": None,
                "planned_journal_successor_size": None,
                "planned_journal_successor_sha256": None,
            }
        )
    if no_tree_terminal_observation:
        changes.update(
            {
                "candidate_path": None,
                "candidate_parent_identity": None,
            }
        )
    for predecessor_prefix, successor_prefix, suffixes in (
        ("predecessor_attempt_record", "successor_attempt_record", ("path", "identity", "sha256")),
        ("predecessor_journal", "successor_journal", ("path", "identity", "sha256")),
        (
            "predecessor_transaction_temp",
            "successor_transaction_temp",
            (
                "path",
                "parent_identity",
                "identity",
                "size",
                "sha256",
                "classification",
                "origin",
            ),
        ),
        (
            "predecessor_target_owner_journal",
            "successor_target_owner_journal",
            ("path", "identity", "sha256"),
        ),
    ):
        if recovery.get(f"{successor_prefix}_{suffixes[0]}") is not None:
            for suffix in suffixes:
                changes[f"{predecessor_prefix}_{suffix}"] = recovery.get(
                    f"{successor_prefix}_{suffix}"
                )
    if recovery.get("successor_candidate_identity") is not None:
        changes["predecessor_candidate_identity"] = recovery.get(
            "successor_candidate_identity"
        )
    if recovery.get("successor_renamed_target_identity") is not None:
        changes["predecessor_renamed_target_identity"] = recovery.get(
            "successor_renamed_target_identity"
        )
    changes.update(
        {
            "action_index": int(recovery.get("action_index")) + 1,
            "expected_action": None,
            "stable_physical_disposition": disposition,
        }
    )
    if action == "observe_committed":
        changes.update(
            {
                "runtime_match_status": "unknown",
                "runtime_match_sha256": None,
            }
        )
    successor = _seal_apply_recovery_successor(
        recovery,
        changes=changes,
    )
    return RuntimeApplyRecoveryPhysicalPostcondition(
        action=action,
        evidence={"apply_recovery": successor},
    )


def _require_committed_new_target_parity(
    *,
    recovery: Mapping[str, Any],
    observation: _ExactPairedRuntimeAttemptObservation,
    package_lease: PackageInputLease,
    deck_name: str,
    layout_identities: Mapping[str, PathIdentity],
    metadata_root_identity: PathIdentity,
) -> None:
    journal = observation.transaction.journal
    if journal is None or journal.phase != RuntimeTransactionPhase.FINALIZED:
        raise ValueError("runtime_committed_journal_invalid")
    manifest, manifest_sha256 = _candidate_manifest_from_pair(
        package_lease=package_lease,
        deck_name=deck_name,
    )
    entries = tuple(manifest["entries"])
    target = Path(str(recovery["renamed_target_path"]))
    target_identity = tuple(recovery["successor_renamed_target_identity"])
    prior_owner = recovery.get("install_route") == "prior_owner"
    if prior_owner:
        if (
            any(
                recovery.get(field) is not None
                for field in (
                    "candidate_path",
                    "candidate_parent_identity",
                    "successor_candidate_identity",
                    "candidate_tree_manifest_sha256",
                    "candidate_tree_verified_sha256",
                    "candidate_tree_entry_count",
                )
            )
            or journal.target_identity != target_identity
            or journal.owns_target is not False
        ):
            raise ValueError("runtime_committed_manifest_changed")
        owner_path = Path(
            str(recovery["predecessor_target_owner_journal_path"])
        )
        owner_raw, owner_identity = _read_exact_runtime_external_file(
            owner_path,
            expected_parent_identity=layout_identities["transactions"],
            maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
        )
        owner = parse_runtime_transaction_journal_bytes(
            owner_raw, expected_transaction_id=owner_path.stem
        )
        if (
            owner_identity
            != tuple(recovery["predecessor_target_owner_journal_identity"])
            or "sha256:" + hashlib.sha256(owner_raw).hexdigest()
            != recovery["predecessor_target_owner_journal_sha256"]
            or owner.phase != RuntimeTransactionPhase.FINALIZED
            or owner.owns_target is not True
            or owner.target_identity != target_identity
        ):
            raise ValueError("runtime_committed_owner_changed")
    else:
        candidate = Path(str(recovery["candidate_path"]))
        if (
            manifest_sha256 != recovery.get("candidate_tree_manifest_sha256")
            or manifest_sha256 != recovery.get("candidate_tree_verified_sha256")
            or len(entries) != recovery.get("candidate_tree_entry_count")
            or path_lexists(candidate)
            or path_identity(candidate.parent)
            != tuple(recovery["candidate_parent_identity"])
            or journal.target_identity != target_identity
            or journal.owns_target is not True
        ):
            raise ValueError("runtime_committed_manifest_changed")
    _verify_candidate_tree_prefix(
        root=target,
        root_identity=target_identity,
        expected_parent_identity=layout_identities["custom_config"],
        entries=entries,
        cursor=len(entries),
    )
    runtime_root = Path(str(recovery["runtime_root"]))
    ini_path = runtime_root / "CustomConfig" / "deck_config.ini"
    ini_raw, _ = _read_exact_runtime_external_file(
        ini_path,
        expected_parent_identity=layout_identities["custom_config"],
        maximum_size=_RUNTIME_EXTERNAL_FILE_ACTION_MAX_BYTES,
    )
    ini_digest = "sha256:" + hashlib.sha256(ini_raw).hexdigest()
    ini = read_deck_config(ini_path, deck_name=deck_name)
    if (
        ini_digest != recovery.get("deck_config_ini_sha256")
        or ini.selected_config_dir != target.name
        or ini.sha256 != journal.next_ini_sha256
    ):
        raise ValueError("runtime_committed_ini_changed")
    state_path = runtime_root / ".hsconfig" / "state.json"
    state_raw, _ = _read_exact_runtime_external_file(
        state_path,
        expected_parent_identity=metadata_root_identity,
        maximum_size=_RUNTIME_EXTERNAL_FILE_ACTION_MAX_BYTES,
    )
    state = read_runtime_state(runtime_root)
    selected = None if state is None else next(
        (item for item in state.decks if item.state_key == journal.state_key),
        None,
    )
    if (
        "sha256:" + hashlib.sha256(state_raw).hexdigest()
        != recovery.get("runtime_state_sha256")
        or selected is None
        or selected.config_dir != target.name
        or selected.package_root_sha256 != journal.package_root_sha256
        or selected.ini_sha256 != ini.sha256
    ):
        raise ValueError("runtime_committed_state_changed")
    receipt_path = _receipt_path(runtime_root, journal.state_key)
    receipt_raw, _ = _read_exact_runtime_external_file(
        receipt_path,
        expected_parent_identity=layout_identities["state_receipts"],
        maximum_size=_RUNTIME_EXTERNAL_FILE_ACTION_MAX_BYTES,
    )
    if (
        "sha256:" + hashlib.sha256(receipt_raw).hexdigest()
        != recovery.get("last_apply_receipt_sha256")
        or receipt_raw != _receipt_bytes(_receipt_payload(journal, ini.sha256))
    ):
        raise ValueError("runtime_committed_receipt_changed")


@contextmanager
def _lease_runtime_apply_after_gates(
    *,
    runtime_root: Path,
    expected_root_identity: PathIdentity,
    require_gates: Callable[[], None],
) -> Iterator[RuntimeApplyLease]:
    """Bootstrap only Runtime lock metadata after all caller-specific gates."""

    root = _require_exact_runtime_root(
        runtime_root,
        expected_root_identity=expected_root_identity,
    )
    require_gates()
    _require_exact_runtime_root(
        root,
        expected_root_identity=expected_root_identity,
    )
    metadata_root, metadata_root_identity = _create_or_confirm_runtime_metadata(
        root,
        runtime_root_identity=expected_root_identity,
    )
    apply_lock_path = metadata_root / "apply.lock"
    if path_lexists(apply_lock_path):
        _require_exact_empty_apply_lock(
            apply_lock_path,
            expected_parent_identity=metadata_root_identity,
        )
    path_guard = capture_plain_ancestor_guard(apply_lock_path)
    with ExclusiveFileLock(
        apply_lock_path,
        expected_parent_identity=metadata_root_identity,
        path_guard=path_guard,
    ):
        apply_lock_identity = _require_exact_empty_apply_lock(
            apply_lock_path,
            expected_parent_identity=metadata_root_identity,
        )
        _revalidate_runtime_apply_filesystem(
            runtime_root=root,
            runtime_root_identity=expected_root_identity,
            metadata_root=metadata_root,
            metadata_root_identity=metadata_root_identity,
            apply_lock_path=apply_lock_path,
            apply_lock_identity=apply_lock_identity,
            path_guard=path_guard,
        )
        require_gates()
        _revalidate_runtime_apply_filesystem(
            runtime_root=root,
            runtime_root_identity=expected_root_identity,
            metadata_root=metadata_root,
            metadata_root_identity=metadata_root_identity,
            apply_lock_path=apply_lock_path,
            apply_lock_identity=apply_lock_identity,
            path_guard=path_guard,
        )
        token = RuntimeApplyLockToken(_RUNTIME_APPLY_TOKEN_AUTHORITY)
        lease = RuntimeApplyLease(
            runtime_root=root,
            runtime_root_identity=expected_root_identity,
            apply_lock_path=apply_lock_path,
            apply_lock_identity=apply_lock_identity,
            lock_token=token,
        )
        binding = _RuntimeApplyLeaseBinding(
            token=token,
            lease=lease,
            thread_id=get_ident(),
            runtime_root=root,
            runtime_root_identity=expected_root_identity,
            metadata_root=metadata_root,
            metadata_root_identity=metadata_root_identity,
            apply_lock_path=apply_lock_path,
            apply_lock_identity=apply_lock_identity,
            path_guard=path_guard,
        )
        _register_runtime_apply_lease(binding)
        try:
            yield lease
        finally:
            # The bearer expires while the physical lock is still held.
            _retire_runtime_apply_lease(token, lease)


def _require_active_runtime_apply_lease(
    lease: RuntimeApplyLease,
    *,
    runtime_root: Path | None = None,
    expected_root_identity: PathIdentity | None = None,
) -> _RuntimeApplyLeaseBinding:
    """Authenticate one exact active same-thread Runtime lease."""

    if not isinstance(lease, RuntimeApplyLease):
        raise ValueError("runtime_apply_lease_invalid")
    token = lease.lock_token
    if not isinstance(token, RuntimeApplyLockToken):
        raise ValueError("runtime_apply_lease_invalid")
    with _active_runtime_apply_leases_lock:
        binding = _active_runtime_apply_leases.get(id(token))
    if binding is None:
        raise ValueError("runtime_apply_lease_inactive")
    if binding.token is not token or binding.lease is not lease:
        raise ValueError("runtime_apply_lease_invalid")
    if (
        getattr(token, "_thread_id", None) != binding.thread_id
        or binding.thread_id != get_ident()
    ):
        raise ValueError("runtime_apply_lease_wrong_thread")
    if (
        lease.runtime_root != binding.runtime_root
        or lease.runtime_root_identity != binding.runtime_root_identity
        or lease.apply_lock_path != binding.apply_lock_path
        or lease.apply_lock_identity != binding.apply_lock_identity
        or lease.lock_token is not binding.token
    ):
        raise ValueError("runtime_apply_lease_invalid")
    if runtime_root is not None and Path(runtime_root) != binding.runtime_root:
        raise ValueError("runtime_apply_lease_runtime_root_mismatch")
    if (
        expected_root_identity is not None
        and expected_root_identity != binding.runtime_root_identity
    ):
        raise ValueError("runtime_apply_lease_runtime_root_identity_mismatch")
    _revalidate_runtime_apply_filesystem(
        runtime_root=binding.runtime_root,
        runtime_root_identity=binding.runtime_root_identity,
        metadata_root=binding.metadata_root,
        metadata_root_identity=binding.metadata_root_identity,
        apply_lock_path=binding.apply_lock_path,
        apply_lock_identity=binding.apply_lock_identity,
        path_guard=binding.path_guard,
    )
    return binding


def _register_runtime_apply_lease(binding: _RuntimeApplyLeaseBinding) -> None:
    with _active_runtime_apply_leases_lock:
        if id(binding.token) in _active_runtime_apply_leases:
            raise ValueError("runtime_apply_lease_token_collision")
        _active_runtime_apply_leases[id(binding.token)] = binding


def _retire_runtime_apply_lease(
    token: RuntimeApplyLockToken,
    lease: RuntimeApplyLease,
) -> None:
    with _active_runtime_apply_leases_lock:
        active = _active_runtime_apply_leases.get(id(token))
        if active is not None and active.token is token and active.lease is lease:
            _active_runtime_apply_leases.pop(id(token), None)


def _create_or_confirm_runtime_metadata(
    runtime_root: Path,
    *,
    runtime_root_identity: PathIdentity,
) -> tuple[Path, PathIdentity]:
    _require_exact_runtime_root(
        runtime_root,
        expected_root_identity=runtime_root_identity,
    )
    metadata_root = runtime_root / ".hsconfig"
    if not path_lexists(metadata_root):
        try:
            secure_create_directory(
                metadata_root,
                expected_parent_identity=runtime_root_identity,
            )
        except FileExistsError:
            pass
    metadata_root_identity = _require_exact_plain_directory(
        metadata_root,
        expected_parent_identity=runtime_root_identity,
        expected_identity=None,
        error="runtime_apply_metadata_invalid",
    )
    _require_exact_runtime_root(
        runtime_root,
        expected_root_identity=runtime_root_identity,
    )
    return metadata_root, metadata_root_identity


def _require_exact_runtime_root(
    runtime_root: Path,
    *,
    expected_root_identity: PathIdentity,
) -> Path:
    root = Path(runtime_root)
    if not _valid_path_identity(expected_root_identity):
        raise ValueError("runtime_apply_runtime_root_identity_invalid")
    if not root.is_absolute():
        raise ValueError("runtime_apply_runtime_root_not_absolute")
    identity = _require_exact_plain_directory(
        root,
        expected_parent_identity=path_identity(root.parent),
        expected_identity=expected_root_identity,
        error="runtime_apply_runtime_root_invalid",
    )
    if identity != expected_root_identity:
        raise ValueError("runtime_apply_runtime_root_identity_changed")
    return root


def _require_exact_plain_directory(
    path: Path,
    *,
    expected_parent_identity: PathIdentity,
    expected_identity: PathIdentity | None,
    error: str,
) -> PathIdentity:
    candidate = Path(path)
    try:
        require_plain_directory(candidate)
        status = candidate.lstat()
        identity = path_identity_from_status(status)
        if expected_identity is not None and identity != expected_identity:
            raise ValueError("filesystem_path_identity_changed")
        if path_identity(candidate.parent) != expected_parent_identity:
            raise ValueError("filesystem_path_identity_changed")
        require_same_identity_resolution(candidate, expected_status=status)
        if candidate.resolve(strict=True) != candidate:
            raise ValueError("filesystem_path_not_canonical")
        require_no_alternate_data_streams(
            candidate,
            expected_identity=identity,
            expected_parent_identity=expected_parent_identity,
            directory=True,
        )
        if path_identity(candidate) != identity:
            raise ValueError("filesystem_path_identity_changed")
        return identity
    except (OSError, ValueError) as cause:
        if isinstance(cause, ValueError) and cause.args == (
            "filesystem_path_identity_changed",
        ):
            raise ValueError(f"{error}_identity_changed") from cause
        raise ValueError(error) from cause


def _require_exact_empty_apply_lock(
    path: Path,
    *,
    expected_parent_identity: PathIdentity,
    expected_identity: PathIdentity | None = None,
) -> PathIdentity:
    lock_path = Path(path)
    try:
        status = plain_file_status(lock_path)
        identity = path_identity_from_status(status)
        if (
            status.st_size != 0
            or (expected_identity is not None and identity != expected_identity)
            or path_identity(lock_path.parent) != expected_parent_identity
        ):
            raise ValueError("runtime_apply_lock_changed")
        require_same_identity_resolution(lock_path, expected_status=status)
        if lock_path.resolve(strict=True) != lock_path:
            raise ValueError("runtime_apply_lock_not_canonical")
        require_no_alternate_data_streams(
            lock_path,
            expected_identity=identity,
            expected_parent_identity=expected_parent_identity,
            directory=False,
            expected_size=0,
        )
        if path_identity(lock_path) != identity:
            raise ValueError("runtime_apply_lock_changed")
        return identity
    except (OSError, ValueError) as cause:
        raise ValueError("runtime_apply_lock_invalid") from cause


def _revalidate_runtime_apply_filesystem(
    *,
    runtime_root: Path,
    runtime_root_identity: PathIdentity,
    metadata_root: Path,
    metadata_root_identity: PathIdentity,
    apply_lock_path: Path,
    apply_lock_identity: PathIdentity,
    path_guard: FilesystemPathGuard,
) -> None:
    path_guard.validate()
    _require_exact_runtime_root(
        runtime_root,
        expected_root_identity=runtime_root_identity,
    )
    _require_exact_plain_directory(
        metadata_root,
        expected_parent_identity=runtime_root_identity,
        expected_identity=metadata_root_identity,
        error="runtime_apply_metadata_invalid",
    )
    _require_exact_empty_apply_lock(
        apply_lock_path,
        expected_parent_identity=metadata_root_identity,
        expected_identity=apply_lock_identity,
    )
    path_guard.validate()


def _valid_path_identity(value: object) -> bool:
    return (
        type(value) is tuple
        and len(value) == 3
        and all(type(part) is int and part >= 0 for part in value)
    )


def _runtime_attempt_retention_path(
    runtime_root: Path,
    apply_attempt_id: str,
) -> Path:
    if (
        not isinstance(apply_attempt_id, str)
        or _ATTEMPT_ID.fullmatch(apply_attempt_id) is None
    ):
        raise ValueError("runtime_attempt_retention_id_invalid")
    return (
        Path(runtime_root)
        / ".hsconfig"
        / "attempt-retention"
        / f"{apply_attempt_id}.json"
    )


def _observe_runtime_attempt_retention(
    runtime_root: Path,
    *,
    apply_attempt_id: str,
) -> _ObservedRuntimeAttemptRetention | None:
    path = _runtime_attempt_retention_path(runtime_root, apply_attempt_id)
    if not path_lexists(path):
        return None
    try:
        parent_identity = path_identity(path.parent)
        status = plain_file_status(path)
        identity = path_identity_from_status(status)
        require_no_alternate_data_streams(
            path,
            expected_identity=identity,
            expected_parent_identity=parent_identity,
            directory=False,
            expected_size=status.st_size,
        )
        raw = read_file_no_follow(
            path,
            expected_status=status,
            maximum_size=RUNTIME_ATTEMPT_RETENTION_MAX_BYTES,
        )
        record = _runtime_attempt_retention_from_raw(
            raw,
            runtime_root=Path(runtime_root),
        )
        if record.apply_attempt_id != apply_attempt_id:
            raise ValueError("attempt")
        return _ObservedRuntimeAttemptRetention(
            record=record,
            path=path,
            identity=identity,
            raw_sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
        )
    except Exception as error:
        raise ValueError("runtime_attempt_retention_invalid") from error


def _observe_retained_transaction(
    path: Path,
    *,
    expected_transaction_id: str,
    expected_identity: PathIdentity | None,
    expected_size: int | None,
    expected_sha256: str | None,
) -> tuple[RuntimeTransactionJournal, PathIdentity, str]:
    try:
        path_guard = capture_plain_ancestor_guard(path)
        status = plain_file_status(path)
        identity = path_identity_from_status(status)
        parent_identity = path_identity(path.parent)
        require_same_identity_resolution(path, expected_status=status)
        require_no_alternate_data_streams(
            path,
            expected_identity=identity,
            expected_parent_identity=parent_identity,
            directory=False,
            expected_size=status.st_size,
        )
        raw = read_file_no_follow(
            path,
            expected_status=status,
            maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
        )
        digest = "sha256:" + hashlib.sha256(raw).hexdigest()
        if (
            (expected_identity is not None and identity != expected_identity)
            or (expected_size is not None and len(raw) != expected_size)
            or (expected_sha256 is not None and digest != expected_sha256)
        ):
            raise ValueError("binding")
        journal = parse_runtime_transaction_journal_bytes(
            raw,
            expected_transaction_id=expected_transaction_id,
        )
        path_guard.validate()
        return journal, identity, digest
    except Exception as error:
        raise ValueError("runtime_attempt_retained_journal_invalid") from error


def _observe_retained_directory(
    path: Path,
    *,
    expected_identity: PathIdentity,
    expected_parent_identity: PathIdentity | None,
) -> PathIdentity:
    path_guard = capture_plain_ancestor_guard(path)
    require_plain_directory(path)
    status = path.lstat()
    identity = path_identity_from_status(status)
    parent_identity = path_identity(path.parent)
    require_same_identity_resolution(path, expected_status=status)
    if (
        identity != expected_identity
        or (
            expected_parent_identity is not None
            and parent_identity != expected_parent_identity
        )
    ):
        raise ValueError("runtime_attempt_retained_directory_changed")
    require_no_alternate_data_streams(
        path,
        expected_identity=identity,
        expected_parent_identity=parent_identity,
        directory=True,
    )
    path_guard.validate()
    return identity


def _require_retained_child_absent(
    path: Path,
    *,
    expected_parent_identity: PathIdentity,
) -> None:
    path_guard = capture_plain_ancestor_guard(path)
    require_plain_directory(path.parent)
    parent_status = path.parent.lstat()
    require_same_identity_resolution(path.parent, expected_status=parent_status)
    if (
        path_identity_from_status(parent_status) != expected_parent_identity
        or path_lexists(path)
    ):
        raise ValueError("runtime_attempt_retention_candidate_changed")
    path_guard.validate()


def _completed_owner_retirement_fallback_is_exact(
    runtime_root: Path,
    *,
    record: RuntimeAttemptRetentionRecord,
) -> bool:
    """Accept a retired old owner only through its immutable completion proof."""

    owner_path = record.target_owner_journal_path
    owner_identity = record.target_owner_journal_identity
    owner_sha256 = record.target_owner_journal_sha256
    target = record.target_path
    target_identity = record.target_identity
    if (
        owner_path is None
        or owner_identity is None
        or owner_sha256 is None
        or target is None
        or target_identity is None
    ):
        return False
    root = Path(runtime_root)
    if (
        owner_path != runtime_transaction_journal_path(root, owner_path.stem)
        or target.parent != root / "CustomConfig"
    ):
        raise ValueError("runtime_owner_retirement_fallback_invalid")
    tombstone_path = (
        root / ".hsconfig" / "owner-retirements" / f"{owner_path.stem}.json"
    )
    if not path_lexists(tombstone_path):
        return False
    retirements_parent = tombstone_path.parent
    raw, _identity = _read_exact_runtime_external_file(
        tombstone_path,
        expected_parent_identity=path_identity(retirements_parent),
        maximum_size=RUNTIME_OWNER_RETIREMENT_MAX_BYTES,
    )
    tombstone = _parse_owner_retirement_tombstone_bytes(raw, runtime_root=root)
    if (
        tombstone.get("state") != "COMPLETED"
        or tombstone.get("retired_owner_transaction_id") != owner_path.stem
        or Path(str(tombstone.get("initial_owner_journal_path"))) != owner_path
        or tuple(tombstone.get("initial_owner_journal_identity") or ())
        != owner_identity
        or tombstone.get("initial_owner_journal_sha256") != owner_sha256
        or Path(str(tombstone.get("retired_target_path"))) != target
        or tuple(tombstone.get("retired_target_identity") or ())
        != target_identity
        or tombstone.get("completed_owner_journal_identity") is None
        or tombstone.get("completed_owner_journal_sha256") is None
    ):
        raise ValueError("runtime_owner_retirement_fallback_invalid")
    successor_path = Path(str(tombstone["successor_owner_journal_path"]))
    successor_raw, successor_identity = _read_exact_runtime_external_file(
        successor_path,
        expected_parent_identity=path_identity(successor_path.parent),
        maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
    )
    successor = parse_runtime_transaction_journal_bytes(
        successor_raw,
        expected_transaction_id=str(tombstone["successor_transaction_id"]),
    )
    if (
        successor_identity
        != tuple(tombstone["successor_owner_journal_identity"])
        or _owner_retirement_digest(successor_raw)
        != tombstone["successor_owner_journal_sha256"]
        or successor.phase != RuntimeTransactionPhase.FINALIZED
        or successor.owns_target is not True
        or successor.package_root_sha256
        != str(tombstone["successor_package_root_sha256"]).removeprefix(
            "sha256:"
        )
    ):
        raise ValueError("runtime_owner_retirement_fallback_invalid")
    return True


def _validate_runtime_attempt_retention_projection(
    runtime_root: Path,
    observed: _ObservedRuntimeAttemptRetention,
) -> tuple[RuntimeTransactionJournal | None, RuntimeTransactionJournal | None]:
    record = observed.record
    root = Path(runtime_root)
    expected_attempt_journal = runtime_transaction_journal_path(
        root,
        record.apply_attempt_id,
    )
    attempt_journal: RuntimeTransactionJournal | None = None
    owner_journal: RuntimeTransactionJournal | None = None
    completed_owner_fallback = _completed_owner_retirement_fallback_is_exact(
        root,
        record=record,
    )

    if record.state == "ACTIVE":
        if path_lexists(expected_attempt_journal) or path_lexists(
            root / ".hsconfig" / "staging" / record.apply_attempt_id
        ):
            raise ValueError("runtime_attempt_retention_active_projection_invalid")
        return None, None

    if completed_owner_fallback:
        if (
            path_lexists(expected_attempt_journal)
            or (
                record.planned_journal_path is not None
                and path_lexists(record.planned_journal_path)
            )
        ):
            raise ValueError("runtime_owner_retirement_fallback_invalid")
    elif record.planned_journal_path is None:
        raise ValueError("runtime_attempt_retention_planned_journal_missing")
    elif path_lexists(record.planned_journal_path):
        planned, planned_identity, planned_digest = _observe_retained_transaction(
            record.planned_journal_path,
            expected_transaction_id=record.apply_attempt_id,
            expected_identity=(
                record.journal_identity
                if record.journal_path is not None
                else None
            ),
            expected_size=record.planned_journal_size,
            expected_sha256=record.planned_journal_sha256,
        )
        if (
            record.package_root_sha256
            != "sha256:" + planned.package_root_sha256
        ):
            raise ValueError("runtime_attempt_retention_package_mismatch")
        if record.journal_path is not None:
            if (
                record.journal_path != record.planned_journal_path
                or record.journal_identity != planned_identity
                or record.journal_sha256 != planned_digest
            ):
                raise ValueError("runtime_attempt_retention_journal_mismatch")
            attempt_journal = planned
    elif record.journal_path is not None:
        raise ValueError("runtime_attempt_retention_journal_missing")

    if record.candidate_path is not None:
        if record.candidate_identity is None:
            if record.candidate_parent_identity is None:
                raise ValueError("runtime_attempt_retention_candidate_parent_missing")
            _require_retained_child_absent(
                record.candidate_path,
                expected_parent_identity=record.candidate_parent_identity,
            )
        else:
            if record.candidate_parent_identity is None:
                raise ValueError("runtime_attempt_retention_candidate_parent_missing")
            _observe_retained_directory(
                record.candidate_path,
                expected_identity=record.candidate_identity,
                expected_parent_identity=record.candidate_parent_identity,
            )

    if record.target_path is not None:
        if record.target_identity is None:
            raise ValueError("runtime_attempt_retention_target_identity_missing")
        if completed_owner_fallback:
            if path_lexists(record.target_path):
                raise ValueError("runtime_owner_retirement_fallback_invalid")
        else:
            _observe_retained_directory(
                record.target_path,
                expected_identity=record.target_identity,
                expected_parent_identity=None,
            )

    if record.target_owner_journal_path is not None:
        if completed_owner_fallback:
            if path_lexists(record.target_owner_journal_path):
                raise ValueError("runtime_owner_retirement_fallback_invalid")
            return attempt_journal, owner_journal
        owner_id = record.target_owner_journal_path.stem
        owner_journal, owner_identity, owner_digest = _observe_retained_transaction(
            record.target_owner_journal_path,
            expected_transaction_id=owner_id,
            expected_identity=record.target_owner_journal_identity,
            expected_size=None,
            expected_sha256=record.target_owner_journal_sha256,
        )
        if (
            owner_identity != record.target_owner_journal_identity
            or owner_digest != record.target_owner_journal_sha256
            or owner_journal.phase != RuntimeTransactionPhase.FINALIZED
            or not owner_journal.owns_target
            or record.target_path is None
            or owner_journal.target_path
            != record.target_path.relative_to(root).as_posix()
            or owner_journal.target_identity != record.target_identity
        ):
            raise ValueError("runtime_attempt_retention_owner_mismatch")
    return attempt_journal, owner_journal


def _reconcile_one_attempt_retention_reserved_temp(
    path: Path,
    *,
    expected_parent_identity: PathIdentity,
) -> None:
    try:
        status = plain_file_status(path)
        identity = path_identity_from_status(status)
        if status.st_size > RUNTIME_ATTEMPT_RETENTION_MAX_BYTES:
            raise ValueError("bounds")
        require_no_alternate_data_streams(
            path,
            expected_identity=identity,
            expected_parent_identity=expected_parent_identity,
            directory=False,
            expected_size=status.st_size,
        )
        secure_unlink(
            path,
            expected_identity=identity,
            expected_parent_identity=expected_parent_identity,
        )
        if path_lexists(path):
            raise ValueError("not retired")
    except Exception as error:
        raise ValueError("runtime_attempt_retention_reserved_temp_invalid") from error


def _reconcile_exact_attempt_retention_reserved_temp(
    runtime_root: Path,
    *,
    apply_attempt_id: str,
) -> None:
    final = _runtime_attempt_retention_path(runtime_root, apply_attempt_id)
    directory = final.parent
    if not path_lexists(directory):
        return
    require_plain_directory(directory)
    staging = final.with_name(f"{final.name}.staged")
    reserved = staging.with_name(f".{staging.name}.live-start-atomic.tmp")
    if path_lexists(reserved):
        _reconcile_one_attempt_retention_reserved_temp(
            reserved,
            expected_parent_identity=path_identity(directory),
        )


def _reconcile_attempt_retention_reserved_temps(runtime_root: Path) -> None:
    directory = Path(runtime_root) / ".hsconfig" / "attempt-retention"
    if not path_lexists(directory):
        return
    try:
        require_plain_directory(directory)
        parent_identity = path_identity(directory)
        reserved: list[Path] = []
        count = 0
        with os.scandir(directory) as iterator:
            for entry in iterator:
                count += 1
                if count > 1024:
                    raise ValueError("bounds")
                if _ATTEMPT_RETENTION_RESERVED_TEMP.fullmatch(entry.name):
                    reserved.append(Path(entry.path))
        for path in sorted(reserved, key=lambda value: value.name):
            _reconcile_one_attempt_retention_reserved_temp(
                path,
                expected_parent_identity=parent_identity,
            )
    except Exception as error:
        raise ValueError("runtime_attempt_retention_store_invalid") from error


def _load_runtime_attempt_retentions(
    runtime_root: Path,
) -> tuple[_ObservedRuntimeAttemptRetention, ...]:
    directory = Path(runtime_root) / ".hsconfig" / "attempt-retention"
    if not path_lexists(directory):
        return ()
    try:
        require_plain_directory(directory)
        attempt_ids: list[str] = []
        count = 0
        with os.scandir(directory) as iterator:
            for entry in iterator:
                count += 1
                if count > 1024:
                    raise ValueError("bounds")
                match = _ATTEMPT_RETENTION_ENTRY.fullmatch(entry.name)
                if match is None:
                    raise ValueError("entry")
                attempt_ids.append(match.group("attempt"))
        if len(set(attempt_ids)) != len(attempt_ids):
            raise ValueError("duplicate")
        observed: list[_ObservedRuntimeAttemptRetention] = []
        for attempt_id in sorted(attempt_ids):
            row = _observe_runtime_attempt_retention(
                runtime_root,
                apply_attempt_id=attempt_id,
            )
            if row is None:
                raise ValueError("missing")
            _validate_runtime_attempt_retention_projection(runtime_root, row)
            observed.append(row)
        return tuple(observed)
    except Exception as error:
        raise ValueError("runtime_attempt_retention_store_invalid") from error


def _runtime_attempt_preservation_index(
    runtime_root: Path,
    rows: tuple[_ObservedRuntimeAttemptRetention, ...],
) -> _RuntimeAttemptPreservationIndex:
    transaction_ids: set[str] = set()
    candidates: dict[str, PathIdentity] = {}
    targets: dict[str, PathIdentity] = {}
    root = Path(runtime_root)
    for observed in rows:
        record = observed.record
        transaction_ids.add(record.apply_attempt_id)
        if _completed_owner_retirement_fallback_is_exact(
            root,
            record=record,
        ):
            continue
        if record.target_owner_journal_path is not None:
            transaction_ids.add(record.target_owner_journal_path.stem)
        if record.candidate_path is not None and record.candidate_identity is not None:
            candidates[record.apply_attempt_id] = record.candidate_identity
        if record.target_path is not None and record.target_identity is not None:
            key = record.target_path.relative_to(root).as_posix().casefold()
            previous = targets.setdefault(key, record.target_identity)
            if previous != record.target_identity:
                raise ValueError("runtime_attempt_retention_target_conflict")
    return _RuntimeAttemptPreservationIndex(
        transaction_ids=frozenset(transaction_ids),
        candidate_identities=candidates,
        target_identities=targets,
    )


def _refresh_runtime_attempt_preservation_index(
    runtime_root: Path,
) -> _RuntimeAttemptPreservationIndex:
    _reconcile_attempt_retention_reserved_temps(runtime_root)
    retained_attempts = _load_runtime_attempt_retentions(runtime_root)
    return _runtime_attempt_preservation_index(runtime_root, retained_attempts)


def _reject_unprotected_journal_target_collisions(
    journals: tuple[RuntimeTransactionJournal, ...],
    preservation_index: _RuntimeAttemptPreservationIndex,
) -> None:
    protected_identities = frozenset(
        preservation_index.target_identities.values()
    )
    for journal in journals:
        if (
            journal.target_path.casefold()
            in preservation_index.target_identities
            or (
                journal.target_identity is not None
                and journal.target_identity in protected_identities
            )
        ):
            raise RuntimeError("runtime_recovery_ownership_ambiguous")


def plan_runtime_install(
    *,
    published_output: PublishedOutput,
    runtime_root: Path,
) -> RuntimeInstallPlan:
    if not isinstance(published_output, PublishedOutput):
        raise TypeError("published_output_required")
    root = Path(runtime_root)
    require_plain_directory(root)
    if (
        published_output.package_root != published_output.revision_root / "04_package"
        or published_output.revision_root.parent.parent != published_output.output_root
    ):
        raise ValueError("published_output_invalid")
    verified = snapshot_and_verify_revision(published_output.revision_root)
    if verified.manifest.content_root_sha256 != published_output.content_root_sha256:
        raise ValueError("published_output_invalid")
    spec = _runtime_package_spec(verified.manifest)
    versioned = f"{spec.logical_config_dir}--sha256-{spec.package_root_sha256}"
    if len(versioned) > _SAFE_COMPONENT_LIMIT:
        raise ValueError("runtime_config_component_too_long")
    ini_path = root / "CustomConfig" / "deck_config.ini"
    if path_lexists(ini_path.parent):
        require_plain_directory(ini_path.parent)
        ini_snapshot = read_deck_config(ini_path, deck_name=spec.deck_name)
    else:
        ini_snapshot = DeckConfigSnapshot(
            path=ini_path,
            existed=False,
            content=None,
            sha256=None,
            selected_config_dir=None,
        )
    return RuntimeInstallPlan(
        deck_name=spec.deck_name,
        logical_config_dir=spec.logical_config_dir,
        versioned_config_dir=versioned,
        package_root_sha256=spec.package_root_sha256,
        source_revision_root=published_output.revision_root,
        source_package_root=published_output.package_root,
        runtime_root=root,
        ini_snapshot=ini_snapshot,
    )


def install_runtime_package(
    plan: RuntimeInstallPlan,
    *,
    fault_hook: FaultHook = no_fault,
    transaction_id: str | None = None,
) -> RuntimeInstallResult:
    if not isinstance(plan, RuntimeInstallPlan):
        raise TypeError("runtime_install_plan_required")
    _bootstrap_neutral_output_locks()
    with lease_output_operation_admission() as operation_lease:
        require_output_operation_allows_runtime_mutation(lease=operation_lease)
        return _install_runtime_package_under_output_operation(
            plan,
            operation_lease=operation_lease,
            fault_hook=fault_hook,
            transaction_id=transaction_id,
        )


def _install_runtime_package_under_output_operation(
    plan: RuntimeInstallPlan,
    *,
    operation_lease: OutputOperationAdmissionLease,
    fault_hook: FaultHook = no_fault,
    transaction_id: str | None = None,
) -> RuntimeInstallResult:
    if not isinstance(plan, RuntimeInstallPlan):
        raise TypeError("runtime_install_plan_required")
    caller_owned_transaction = transaction_id is not None
    selected_transaction_id = (
        transaction_id if transaction_id is not None else uuid.uuid4().hex
    )
    runtime_transaction_journal_path(Path(), selected_transaction_id)
    output_root = plan.source_revision_root.parent.parent
    with lease_package_input(output_root) as lease:
        spec = _validate_leased_source(plan, lease)
        with _lease_runtime_apply_under_output_operation(
            output_operation_lease=operation_lease,
            runtime_root=plan.runtime_root,
            expected_root_identity=path_identity(plan.runtime_root),
        ):
            selected_journal_path = runtime_transaction_journal_path(
                plan.runtime_root,
                selected_transaction_id,
            )
            if path_lexists(selected_journal_path):
                raise RuntimeInstallRecoveryRequiredError(
                    "runtime_transaction_recovery_required"
                )
            try:
                _ensure_runtime_layout(plan.runtime_root)
                fault_hook("after_lock")
                recovery = _recover_locked(plan.runtime_root)
                current_ini = _read_actual_ini(plan)
                if _same_config_dir(
                    current_ini.selected_config_dir,
                    plan.versioned_config_dir,
                ):
                    target = (
                        plan.runtime_root / "CustomConfig" / plan.versioned_config_dir
                    )
                    _verify_runtime_tree_against_spec(target, spec, lease.snapshot)
                    owner = _require_unambiguous_owner(
                        plan.runtime_root,
                        target,
                        plan.package_root_sha256,
                    )
                    state = _repair_selected_state_without_journal(
                        plan,
                        current_ini,
                    )
                    receipt = _receipt_path(
                        plan.runtime_root,
                        _state_key(plan.deck_name),
                    )
                    if not receipt.is_file():
                        _write_receipt(
                            plan.runtime_root,
                            _receipt_payload_for_plan(
                                plan,
                                current_ini.sha256,
                                _state_key(plan.deck_name),
                            ),
                        )
                    if caller_owned_transaction:
                        _write_journal(
                            selected_journal_path,
                            _finalized_noop_journal(
                                plan=plan,
                                current_ini=current_ini,
                                transaction_id=selected_transaction_id,
                                target_identity=owner.target_identity,
                            ),
                        )
                    del state
                    return RuntimeInstallResult(
                        status=(
                            "recovered" if recovery.repaired else "already_current"
                        ),
                        config_dir=plan.versioned_config_dir,
                        package_root_sha256=plan.package_root_sha256,
                        previous_config_dir=current_ini.selected_config_dir,
                        receipt_path=receipt,
                    )
                return _install_locked(
                    plan,
                    spec,
                    lease.snapshot,
                    current_ini,
                    fault_hook,
                    selected_transaction_id,
                    retain_finalized_nonowner_journal=caller_owned_transaction,
                )
            except BaseException as primary:
                try:
                    require_output_operation_allows_runtime_mutation(
                        lease=operation_lease
                    )
                    require_live_admission_allows_runtime_mutation(
                        runtime_root=plan.runtime_root,
                        runtime_root_identity=path_identity(plan.runtime_root),
                    )
                    _recover_locked(plan.runtime_root)
                except BaseException as recovery_error:
                    _add_note(
                        primary,
                        "best-effort runtime recovery failed",
                        recovery_error,
                    )
                raise


def recover_runtime_state(runtime_root: Path) -> RuntimeState | None:
    root = Path(runtime_root)
    _bootstrap_neutral_output_locks()
    with lease_output_operation_admission() as operation_lease:
        require_plain_directory(root)
        with _lease_runtime_apply_under_output_operation(
            output_operation_lease=operation_lease,
            runtime_root=root,
            expected_root_identity=path_identity(root),
        ):
            _ensure_runtime_layout(root)
            return _recover_locked(root).state


def recover_runtime_attempt(
    runtime_root: Path,
    *,
    transaction_id: str,
    expected_retention_owner_run_id: str,
    expected_package_root_sha256: str,
    expected_deck_name: str,
) -> RuntimeAttemptRecovery:
    """Observe one exact retained attempt without broad recovery side effects."""

    root = Path(runtime_root)
    runtime_transaction_journal_path(root, transaction_id)
    if (
        not isinstance(expected_retention_owner_run_id, str)
        or _ATTEMPT_ID.fullmatch(expected_retention_owner_run_id) is None
        or not isinstance(expected_package_root_sha256, str)
        or _PREFIXED_SHA256.fullmatch(expected_package_root_sha256) is None
        or not _valid_deck_name(expected_deck_name)
    ):
        raise ValueError("runtime_attempt_recovery_expectation_invalid")
    require_plain_directory(root)
    root_identity = path_identity(root)
    with _lease_runtime_apply_after_gates(
        runtime_root=root,
        expected_root_identity=root_identity,
        require_gates=lambda: None,
    ) as runtime_lease:
        _require_active_runtime_apply_lease(
            runtime_lease,
            runtime_root=root,
            expected_root_identity=root_identity,
        )
        _reconcile_exact_attempt_retention_reserved_temp(
            root,
            apply_attempt_id=transaction_id,
        )
        retention_path = _runtime_attempt_retention_path(root, transaction_id)
        retention_staging = retention_path.with_name(
            f"{retention_path.name}.staged"
        )
        if path_lexists(retention_staging):
            raise ValueError("runtime_attempt_retention_store_invalid")
        observed = _observe_runtime_attempt_retention(
            root,
            apply_attempt_id=transaction_id,
        )
        completed_owner_fallback = False
        if observed is not None:
            record = observed.record
            if (
                record.retention_owner_run_id
                != expected_retention_owner_run_id
                or (
                    record.package_root_sha256 is not None
                    and record.package_root_sha256
                    != expected_package_root_sha256
                )
            ):
                raise ValueError("runtime_attempt_recovery_retention_mismatch")
            _validate_runtime_attempt_retention_projection(root, observed)
            completed_owner_fallback = (
                _completed_owner_retirement_fallback_is_exact(
                    root,
                    record=record,
                )
            )

        journal_path = runtime_transaction_journal_path(root, transaction_id)
        journal: RuntimeTransactionJournal | None = None
        journal_identity: PathIdentity | None = None
        journal_sha256: str | None = None
        if path_lexists(journal_path):
            record = observed.record if observed is not None else None
            journal, journal_identity, journal_sha256 = _observe_retained_transaction(
                journal_path,
                expected_transaction_id=transaction_id,
                expected_identity=(
                    record.journal_identity
                    if record is not None and record.journal_path is not None
                    else None
                ),
                expected_size=(
                    record.planned_journal_size if record is not None else None
                ),
                expected_sha256=(
                    record.planned_journal_sha256 if record is not None else None
                ),
            )
            if (
                journal.deck_name != expected_deck_name
                or "sha256:" + journal.package_root_sha256
                != expected_package_root_sha256
            ):
                raise ValueError("runtime_attempt_recovery_journal_mismatch")

        receipt_path: Path | None = None
        status: Literal[
            "not_committed",
            "committed",
            "recovered",
            "committed_receipt_pending",
            "unknown",
        ]
        if journal is None and completed_owner_fallback:
            candidate_receipt = _receipt_path(root, _state_key(expected_deck_name))
            if path_lexists(candidate_receipt):
                plain_file_status(candidate_receipt)
                receipt_path = candidate_receipt
                status = "committed"
            else:
                status = "committed_receipt_pending"
        elif journal is None:
            status = "not_committed"
        elif journal.phase == RuntimeTransactionPhase.FINALIZED:
            candidate_receipt = _receipt_path(root, journal.state_key)
            if path_lexists(candidate_receipt):
                plain_file_status(candidate_receipt)
                receipt_path = candidate_receipt
                status = "committed"
            else:
                status = "committed_receipt_pending"
        elif journal.phase in {
            RuntimeTransactionPhase.INI_COMMITTED,
            RuntimeTransactionPhase.STATE_COMMITTED,
        }:
            status = "committed_receipt_pending"
        else:
            status = "unknown"

        record = observed.record if observed is not None else None
        return RuntimeAttemptRecovery(
            transaction_id=transaction_id,
            status=status,
            package_root_sha256=(
                record.package_root_sha256
                if record is not None
                else (
                    "sha256:" + journal.package_root_sha256
                    if journal is not None
                    else None
                )
            ),
            receipt_path=receipt_path,
            retained_attempt_record_path=(
                observed.path if observed is not None else None
            ),
            retained_attempt_record_identity=(
                observed.identity if observed is not None else None
            ),
            retained_attempt_record_sha256=(
                observed.raw_sha256 if observed is not None else None
            ),
            retained_journal_path=(journal_path if journal is not None else None),
            retained_journal_identity=journal_identity,
            retained_journal_sha256=journal_sha256,
            target_owner_journal_path=(
                record.target_owner_journal_path if record is not None else None
            ),
            target_owner_journal_identity=(
                record.target_owner_journal_identity
                if record is not None
                else None
            ),
            target_owner_journal_sha256=(
                record.target_owner_journal_sha256
                if record is not None
                else None
            ),
            runtime_admission=None,
            observation_family=None,
            initial_apply_recovery_evidence=None,
            initial_terminal_resolution_evidence=None,
            runtime_observation_receipt=None,
            apply_recovery_step_receipt=None,
            terminal_resolution_step_receipt=None,
        )


def _paired_runtime_attempt_result(
    *,
    observation: _ExactPairedRuntimeAttemptObservation,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    observation_family: RuntimeRecoveryObservationFamily | None,
    runtime_observation_receipt: RuntimeObservationReceipt | None,
    apply_recovery_step_receipt: ApplyRecoveryStepReceipt | None,
    terminal_resolution_step_receipt: TerminalResolutionStepReceipt | None,
    terminal_cleanup_inventory: TerminalResolutionCleanupInventory | None = None,
    status_override: Literal[
        "not_committed",
        "committed",
        "recovered",
        "committed_receipt_pending",
        "unknown",
    ] | None = None,
) -> RuntimeAttemptRecovery:
    retained = observation.retention
    record = retained.record if retained is not None else None
    transaction = observation.transaction
    return RuntimeAttemptRecovery(
        transaction_id=runtime_admission.apply_attempt_id,
        status=status_override or observation.status,
        package_root_sha256=runtime_admission.package_root_sha256,
        receipt_path=observation.receipt_path,
        retained_attempt_record_path=(
            retained.path if retained is not None else None
        ),
        retained_attempt_record_identity=(
            retained.identity if retained is not None else None
        ),
        retained_attempt_record_sha256=(
            retained.raw_sha256 if retained is not None else None
        ),
        retained_journal_path=(
            transaction.journal_path
            if transaction.journal is not None
            else None
        ),
        retained_journal_identity=transaction.journal_identity,
        retained_journal_sha256=transaction.journal_sha256,
        target_owner_journal_path=(
            record.target_owner_journal_path
            if record is not None
            else None
        ),
        target_owner_journal_identity=(
            record.target_owner_journal_identity
            if record is not None
            else None
        ),
        target_owner_journal_sha256=(
            record.target_owner_journal_sha256
            if record is not None
            else None
        ),
        runtime_admission=runtime_admission,
        observation_family=observation_family,
        initial_apply_recovery_evidence=None,
        initial_terminal_resolution_evidence=None,
        runtime_observation_receipt=runtime_observation_receipt,
        apply_recovery_step_receipt=apply_recovery_step_receipt,
        terminal_resolution_step_receipt=(
            terminal_resolution_step_receipt
        ),
        terminal_cleanup_inventory=terminal_cleanup_inventory,
    )


def _classify_new_target_ini_external_final(
    *,
    recovery: Mapping[str, Any],
    runtime_root: Path,
    deck_name: str,
) -> Literal["exact", "contradictory"] | None:
    """Classify the narrowly-bound deck INI final without mutating it.

    ``None`` deliberately leaves unrelated external-file actions to the
    ordinary recovery classifier.  Filesystem authority failures are not
    converted into an observation: callers must fail closed on those errors.
    """

    external = recovery.get("external_file_action")
    action = recovery.get("expected_action")
    if not isinstance(external, Mapping):
        return None
    final_path = Path(str(external.get("final_path")))
    expected_final_path = runtime_root / "CustomConfig" / "deck_config.ini"
    if final_path != expected_final_path:
        return None
    external_stage = external.get("stage")
    external_action = external.get("action_kind")
    selected_unknown = action == "observe_unknown"
    if selected_unknown:
        expected_index = int(recovery["action_index"]) - 1
        valid_action_stage = (external_stage, external_action) in {
            ("PLANNED", "materialize_file_action_staging"),
            ("STAGING_BOUND", "write_deck_config_ini"),
        }
    else:
        expected_index = recovery.get("action_index")
        valid_action_stage = (action, external_stage, external_action) in {
            (
                "materialize_file_action_staging",
                "PLANNED",
                "materialize_file_action_staging",
            ),
            (
                "write_deck_config_ini",
                "STAGING_BOUND",
                "write_deck_config_ini",
            ),
        }
    if not valid_action_stage:
        return None
    if external.get("action_index") != expected_index:
        raise ValueError("runtime_failure_selection_ini_external_invalid")
    parent_identity = tuple(external.get("parent_identity", ()))
    planned_size = external.get("planned_successor_size")
    planned_sha256 = external.get("planned_successor_sha256")
    if (
        len(parent_identity) != 3
        or type(planned_size) is not int
        or not 0 <= planned_size <= MAX_DECK_CONFIG_BYTES
        or not isinstance(planned_sha256, str)
        or _PREFIXED_SHA256.fullmatch(planned_sha256) is None
    ):
        raise ValueError("runtime_failure_selection_ini_external_invalid")
    require_plain_directory(final_path.parent)
    if path_identity(final_path.parent) != parent_identity:
        raise ValueError("runtime_external_file_action_parent_changed")

    predecessor_state = external.get("predecessor_state")
    if predecessor_state == "absent":
        if (
            external.get("predecessor_identity") is not None
            or external.get("predecessor_size") is not None
            or external.get("predecessor_sha256") is not None
        ):
            raise ValueError("runtime_failure_selection_ini_external_invalid")
        if not path_lexists(final_path):
            return "exact"
    elif predecessor_state == "exact":
        predecessor_identity = tuple(
            external.get("predecessor_identity", ())
        )
        predecessor_size = external.get("predecessor_size")
        predecessor_sha256 = external.get("predecessor_sha256")
        if (
            len(predecessor_identity) != 3
            or type(predecessor_size) is not int
            or predecessor_size < 0
            or not isinstance(predecessor_sha256, str)
            or _PREFIXED_SHA256.fullmatch(predecessor_sha256) is None
        ):
            raise ValueError("runtime_failure_selection_ini_external_invalid")
        if not path_lexists(final_path):
            return "contradictory"
    else:
        raise ValueError("runtime_failure_selection_ini_external_invalid")

    status = plain_file_status(final_path)
    final_identity = path_identity_from_status(status)
    require_no_alternate_data_streams(
        final_path,
        expected_identity=final_identity,
        expected_parent_identity=parent_identity,
        directory=False,
        expected_size=status.st_size,
    )
    if status.st_size > MAX_DECK_CONFIG_BYTES:
        return "contradictory"
    final_raw = read_file_no_follow(
        final_path,
        expected_status=status,
        maximum_size=MAX_DECK_CONFIG_BYTES,
    )
    try:
        read_deck_config(final_path, deck_name=deck_name)
    except ValueError as exc:
        if str(exc) not in {
            "deck_config_ini_invalid_encoding",
            "deck_config_ini_ambiguous_mapping",
            "deck_config_ini_unsafe_config_dir",
        }:
            raise
        return "contradictory"
    final_sha256 = "sha256:" + hashlib.sha256(final_raw).hexdigest()
    predecessor_matches = (
        predecessor_state == "exact"
        and final_identity == predecessor_identity
        and len(final_raw) == predecessor_size
        and final_sha256 == predecessor_sha256
    )
    successor_matches = (
        len(final_raw) == planned_size and final_sha256 == planned_sha256
    )
    return "exact" if predecessor_matches or successor_matches else "contradictory"


def _require_new_target_ini_external_residue(
    *,
    recovery: Mapping[str, Any],
    runtime_root: Path,
) -> None:
    """Require the exact non-mutating residue for a selected INI unknown."""

    external = recovery.get("external_file_action")
    if not isinstance(external, Mapping):
        raise ValueError("runtime_unknown_observation_ini_external_residue_invalid")
    final_path = Path(str(external.get("final_path")))
    expected_final_path = runtime_root / "CustomConfig" / "deck_config.ini"
    staging_path = Path(str(external.get("staging_path")))
    inner_temp_path = Path(str(external.get("inner_temp_path")))
    parent_identity = tuple(external.get("parent_identity", ()))
    if (
        final_path != expected_final_path
        or staging_path != final_path.with_name(f"{final_path.name}.staged")
        or inner_temp_path
        != staging_path.with_name(
            f".{staging_path.name}.live-start-atomic.tmp"
        )
        or len(parent_identity) != 3
        or staging_path.parent != final_path.parent
    ):
        raise ValueError("runtime_unknown_observation_ini_external_residue_invalid")
    require_plain_directory(staging_path.parent)
    if path_identity(staging_path.parent) != parent_identity:
        raise ValueError("runtime_external_file_action_parent_changed")
    stage = external.get("stage")
    if stage == "PLANNED":
        if path_lexists(staging_path) or path_lexists(inner_temp_path):
            raise ValueError(
                "runtime_unknown_observation_ini_external_residue_invalid"
            )
        return
    if stage != "STAGING_BOUND" or path_lexists(inner_temp_path):
        raise ValueError("runtime_unknown_observation_ini_external_residue_invalid")
    if not path_lexists(staging_path):
        raise ValueError("runtime_unknown_observation_ini_external_residue_invalid")
    staging_identity_value = external.get("staging_identity")
    staging_size = external.get("staging_size")
    staging_sha256 = external.get("staging_sha256")
    planned_size = external.get("planned_successor_size")
    planned_sha256 = external.get("planned_successor_sha256")
    if (
        not isinstance(staging_identity_value, (list, tuple))
        or len(staging_identity_value) != 3
        or type(staging_size) is not int
        or not 0 <= staging_size <= MAX_DECK_CONFIG_BYTES
        or not isinstance(staging_sha256, str)
        or _PREFIXED_SHA256.fullmatch(staging_sha256) is None
        or staging_size != planned_size
        or staging_sha256 != planned_sha256
    ):
        raise ValueError("runtime_unknown_observation_ini_external_residue_invalid")
    expected_staging_identity = tuple(staging_identity_value)
    status = plain_file_status(staging_path)
    staging_identity = path_identity_from_status(status)
    require_no_alternate_data_streams(
        staging_path,
        expected_identity=staging_identity,
        expected_parent_identity=parent_identity,
        directory=False,
        expected_size=status.st_size,
    )
    staging_raw = read_file_no_follow(
        staging_path,
        expected_status=status,
        maximum_size=MAX_DECK_CONFIG_BYTES,
    )
    if (
        staging_identity != expected_staging_identity
        or len(staging_raw) != staging_size
        or "sha256:" + hashlib.sha256(staging_raw).hexdigest()
        != staging_sha256
    ):
        raise ValueError("runtime_unknown_observation_ini_external_residue_invalid")


def classify_runtime_failure_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    transaction_id: str,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    expected_recovery: RuntimeApplyRecoveryEvidence,
) -> RuntimeFailureSelection:
    """Boundedly classify one persisted failed action without mutation."""

    if (
        type(runtime_admission) is not RuntimeLiveAttemptAdmissionEvidence
        or type(expected_recovery) is not RuntimeApplyRecoveryEvidence
        or transaction_id != runtime_admission.apply_attempt_id
    ):
        raise ValueError("runtime_failure_selection_arguments_invalid")
    binding = _require_active_controller_apply_pair(lease_pair)
    persisted = load_live_start_session_under_lock(
        session_lease=binding.session_lease
    )
    _validate_controller_pair_session_provenance(
        binding=binding,
        persisted=persisted,
    )
    recovery = persisted.apply_recovery
    expected = expected_recovery.value
    if (
        binding.runtime_admission is not runtime_admission
        or runtime_admission.runtime_root
        != lease_pair.runtime_lease.runtime_root
        or runtime_admission.runtime_root_identity
        != lease_pair.runtime_lease.runtime_root_identity
        or persisted.run_id != runtime_admission.run_id
        or not isinstance(recovery, Mapping)
        or dict(recovery) != dict(expected)
        or recovery.get("apply_attempt_id") != transaction_id
        or recovery.get("runtime_admission_path")
        != str(runtime_admission.admission_path)
        or tuple(recovery.get("runtime_admission_identity", ()))
        != runtime_admission.admission_identity
        or recovery.get("runtime_admission_sha256")
        != runtime_admission.admission_sha256
        or recovery.get("runtime_root") != str(runtime_admission.runtime_root)
        or tuple(recovery.get("runtime_root_identity", ()))
        != runtime_admission.runtime_root_identity
    ):
        raise ValueError("runtime_failure_selection_pair_or_cursor_changed")
    action = recovery.get("expected_action")
    if (
        action not in RUNTIME_APPLY_RECOVERY_ACTIONS
        or action in RUNTIME_TERMINAL_OBSERVATION_ACTIONS
    ):
        raise ValueError("runtime_failure_selection_action_invalid")
    layout = persisted.runtime_layout_bootstrap
    if not isinstance(layout, Mapping):
        raise ValueError("runtime_failure_selection_layout_changed")
    layout_identities = _validated_complete_layout_successor_identities(
        layout=layout,
        runtime_root=runtime_admission.runtime_root,
    )
    observed = _observe_exact_paired_runtime_attempt(
        runtime_admission.runtime_root,
        transaction_id=transaction_id,
        expected_retention_owner_run_id=(
            runtime_admission.retention_owner_run_id
        ),
        expected_package_root_sha256=str(recovery["package_root_sha256"]),
        expected_deck_name=persisted.deck_name,
        recovery_cursor=recovery,
        tolerate_bounded_authority_contradiction=True,
        layout_identities=layout_identities,
    )
    _require_recovery_cursor_observation_matches(
        recovery=recovery,
        observation=observed,
        action=str(action),
        allow_committed_journal_successor=action == "bind_renamed_target",
        allow_retired_legacy_temp=False,
    )
    if recovery.get("install_route") == "prior_owner":
        _require_retained_child_absent(
            runtime_admission.runtime_root
            / ".hsconfig"
            / "staging"
            / transaction_id,
            expected_parent_identity=layout_identities["staging"],
        )
    external = recovery.get("external_file_action")
    owner_retirement = recovery.get("owner_retirement")
    unfinished_owner_cleanup = (
        isinstance(owner_retirement, Mapping)
        and owner_retirement.get("stage") in {"CLEANING", "COMPLETED"}
        and external is None
        and action
        in {
            "delete_owner_cleanup_entry",
            "retire_owner_target_root",
            "retire_old_owner_journal",
        }
    )
    visible_intended_ini = recovery.get("deck_config_ini_sha256") is not None
    ini_external_final = _classify_new_target_ini_external_final(
        recovery=recovery,
        runtime_root=runtime_admission.runtime_root,
        deck_name=persisted.deck_name,
    )
    marker = observed.authority_contradiction
    if marker is not None and ini_external_final is not None:
        raise ValueError("runtime_bounded_authority_contradiction_ambiguous")
    if marker is not None and recovery.get("install_route") == "prior_owner":
        if marker.surface not in {
            "prior_owner_target",
            "prior_owner_journal",
        }:
            raise ValueError("runtime_bounded_authority_contradiction_invalid")
        if visible_intended_ini:
            raise ValueError("runtime_bounded_authority_contradiction_ambiguous")
        if isinstance(external, Mapping) and any(
            path_lexists(Path(str(external.get(field_name))))
            for field_name in ("staging_path", "inner_temp_path")
        ):
            raise ValueError(
                "runtime_unknown_observation_file_action_recovery_required"
            )
        if (
            recovery.get("successor_journal_identity") is None
            and not _exact_abandonable_prior_owner_journal_intent(recovery)
        ):
            raise ValueError("runtime_bounded_authority_contradiction_invalid")
        _require_bounded_authority_marker_content_exact(
            marker=marker,
            recovery=recovery,
            package_lease=lease_pair.package_lease,
            deck_name=persisted.deck_name,
            layout_identities=layout_identities,
        )
        return RuntimeFailureSelection(
            disposition="select_terminal_observation",
            expected_recovery_sha256=str(recovery["content_sha256"]),
            expected_action_index=int(recovery["action_index"]),
            expected_action=str(action),
            selected_observation="observe_unknown",
        )
    if marker is not None and recovery.get("install_route") != "new_target":
        raise ValueError("runtime_bounded_authority_contradiction_invalid")
    prior_owner_bound_status = (
        _prove_exact_prior_owner_bound_pre_ini_no_commit(
            recovery=recovery,
            observation=observed,
            persisted=persisted,
            lease_pair=lease_pair,
            runtime_admission=runtime_admission,
        )
    )
    if prior_owner_bound_status == "resume":
        return RuntimeFailureSelection(
            disposition="resume_current_action",
            expected_recovery_sha256=str(recovery["content_sha256"]),
            expected_action_index=int(recovery["action_index"]),
            expected_action=str(action),
            selected_observation=None,
        )
    prior_owner_no_commit = (
        recovery.get("install_route") == "prior_owner"
        and recovery.get("successor_journal_identity") is None
        and not visible_intended_ini
        and recovery.get("deck_config_ini_sha256") is None
        and _exact_abandonable_prior_owner_journal_intent(recovery)
    )
    if prior_owner_no_commit and not (
        _journal_less_same_attempt_pre_apply_snapshot_is_exact(
            recovery=recovery,
            lease_pair=lease_pair,
            runtime_admission=runtime_admission,
        )
    ):
        return RuntimeFailureSelection(
            disposition="select_terminal_observation",
            expected_recovery_sha256=str(recovery["content_sha256"]),
            expected_action_index=int(recovery["action_index"]),
            expected_action=str(action),
            selected_observation="observe_unknown",
        )
    if marker is None and ini_external_final == "contradictory":
        return RuntimeFailureSelection(
            disposition="select_terminal_observation",
            expected_recovery_sha256=str(recovery["content_sha256"]),
            expected_action_index=int(recovery["action_index"]),
            expected_action=str(action),
            selected_observation="observe_unknown",
        )
    if (
        marker is None
        and ini_external_final == "exact"
        and prior_owner_bound_status != "not_committed"
    ):
        return RuntimeFailureSelection(
            disposition="resume_current_action",
            expected_recovery_sha256=str(recovery["content_sha256"]),
            expected_action_index=int(recovery["action_index"]),
            expected_action=str(action),
            selected_observation=None,
        )
    no_commit = (
        prior_owner_no_commit
        or prior_owner_bound_status == "not_committed"
    )
    new_target_precommit_status = _prove_exact_new_target_precommit_no_commit(
        recovery=recovery,
        observation=observed,
        package_lease=lease_pair.package_lease,
        persisted=persisted,
        profile_lease=binding.profile_lease,
        session_root=binding.session_root,
        lease_pair=lease_pair,
        runtime_admission=runtime_admission,
    )
    if new_target_precommit_status == "resume":
        return RuntimeFailureSelection(
            disposition="resume_current_action",
            expected_recovery_sha256=str(recovery["content_sha256"]),
            expected_action_index=int(recovery["action_index"]),
            expected_action=str(action),
            selected_observation=None,
        )
    if new_target_precommit_status == "unknown":
        return RuntimeFailureSelection(
            disposition="select_terminal_observation",
            expected_recovery_sha256=str(recovery["content_sha256"]),
            expected_action_index=int(recovery["action_index"]),
            expected_action=str(action),
            selected_observation="observe_unknown",
        )
    exact_new_target_no_commit = new_target_precommit_status == "not_committed"
    no_commit = no_commit or exact_new_target_no_commit
    if exact_new_target_no_commit:
        visible_intended_ini = False
    if visible_intended_ini and not unfinished_owner_cleanup:
        return RuntimeFailureSelection(
            disposition="resume_current_action",
            expected_recovery_sha256=str(recovery["content_sha256"]),
            expected_action_index=int(recovery["action_index"]),
            expected_action=str(action),
            selected_observation=None,
        )
    if no_commit:
        selected = "observe_not_committed"
    elif isinstance(external, Mapping):
        return RuntimeFailureSelection(
            disposition="resume_current_action",
            expected_recovery_sha256=str(recovery["content_sha256"]),
            expected_action_index=int(recovery["action_index"]),
            expected_action=str(action),
            selected_observation=None,
        )
    else:
        selected = "observe_pending"
    return RuntimeFailureSelection(
        disposition="select_terminal_observation",
        expected_recovery_sha256=str(recovery["content_sha256"]),
        expected_action_index=int(recovery["action_index"]),
        expected_action=str(action),
        selected_observation=selected,
    )


def _load_bound_same_attempt_snapshots(
    *,
    lease_pair: ControllerApplyLeasePair,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    apply_attempt_id: str,
) -> tuple[
    LiveStartSession,
    apply_invocation_module.PreApplyRuntimeSnapshot,
    apply_invocation_module.PreApplyRuntimeSnapshot,
]:
    binding = _require_active_controller_apply_pair(lease_pair)
    persisted = load_live_start_session_under_lock(
        session_lease=binding.session_lease
    )
    _validate_controller_pair_session_provenance(
        binding=binding, persisted=persisted
    )
    invocation = apply_invocation_module.load_apply_invocation(
        binding.session_root / "receipts" / "apply_invocation.json"
    )
    raw_sha256 = "sha256:" + hashlib.sha256(
        invocation.canonical_json
    ).hexdigest()
    if (
        binding.runtime_admission is not runtime_admission
        or invocation.apply_attempt_id != apply_attempt_id
        or invocation.run_id != runtime_admission.run_id
        or invocation.runtime_root != runtime_admission.runtime_root
        or invocation.runtime_root_identity
        != runtime_admission.runtime_root_identity
        or invocation.operator_profile_sha256
        != runtime_admission.operator_profile_sha256
        or invocation.pre_apply_runtime_snapshot.deck_name
        != persisted.deck_name
        or invocation.content_sha256 != persisted.apply_invocation_sha256
        or invocation.content_sha256
        != runtime_admission.apply_invocation_sha256
        or invocation.pre_apply_runtime_snapshot.content_sha256
        != runtime_admission.pre_apply_runtime_snapshot_sha256
        or persisted.artifact_bindings.get(
            "receipts/apply_invocation.json"
        )
        != raw_sha256
    ):
        raise ValueError("same_attempt_invocation_binding_changed")
    current = apply_invocation_module.capture_pre_apply_runtime_snapshot(
        runtime_root=runtime_admission.runtime_root,
        expected_runtime_root_identity=runtime_admission.runtime_root_identity,
        deck_name=persisted.deck_name,
        state_key=_state_key(persisted.deck_name),
        profile_lease=binding.profile_lease,
    )
    return persisted, invocation.pre_apply_runtime_snapshot, current


def _validate_same_attempt_journal_delta_with_snapshot(
    *,
    lease_pair: ControllerApplyLeasePair,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    apply_attempt_id: str,
    expected_attempt_record_path: Path,
    expected_attempt_record_identity: PathIdentity,
    expected_attempt_record_sha256: str,
    expected_journal_path: Path,
    expected_journal_identity: PathIdentity,
    expected_journal_sha256: str,
    expected_journal_phase: str,
    recovery_cursor: Mapping[str, Any] | None = None,
) -> tuple[
    apply_invocation_module.ValidatedSameAttemptJournalDelta,
    apply_invocation_module.PreApplyRuntimeSnapshot,
    apply_invocation_module.PreApplyRuntimeSnapshot,
]:
    binding = _require_active_controller_apply_pair(lease_pair)
    persisted = load_live_start_session_under_lock(
        session_lease=binding.session_lease
    )
    _validate_controller_pair_session_provenance(
        binding=binding, persisted=persisted
    )
    recovery = (
        persisted.apply_recovery
        if recovery_cursor is None
        else recovery_cursor
    )
    if (
        type(runtime_admission) is not RuntimeLiveAttemptAdmissionEvidence
        or binding.runtime_admission is not runtime_admission
        or apply_attempt_id != runtime_admission.apply_attempt_id
        or not isinstance(recovery, Mapping)
        or recovery.get("apply_attempt_id") != apply_attempt_id
        or expected_journal_phase
        not in {"PREPARED", "RUNTIME_STAGED", "RUNTIME_VERIFIED"}
    ):
        raise ValueError("same_attempt_journal_delta_pair_changed")
    expected_attempt_triplet = (
        str(expected_attempt_record_path),
        tuple(expected_attempt_record_identity),
        expected_attempt_record_sha256,
    )
    expected_journal_triplet = (
        str(expected_journal_path),
        tuple(expected_journal_identity),
        expected_journal_sha256,
    )
    attempt_prefix = (
        "successor"
        if recovery.get("successor_attempt_record_path") is not None
        else "predecessor"
    )
    journal_prefix = (
        "successor"
        if recovery.get("successor_journal_path") is not None
        else "predecessor"
    )
    persisted_attempt_triplet = (
        recovery.get(f"{attempt_prefix}_attempt_record_path"),
        tuple(recovery[f"{attempt_prefix}_attempt_record_identity"]),
        recovery.get(f"{attempt_prefix}_attempt_record_sha256"),
    )
    persisted_journal_triplet = (
        recovery.get(f"{journal_prefix}_journal_path"),
        tuple(recovery[f"{journal_prefix}_journal_identity"]),
        recovery.get(f"{journal_prefix}_journal_sha256"),
    )
    if (
        expected_attempt_triplet != persisted_attempt_triplet
        or expected_journal_triplet != persisted_journal_triplet
    ):
        raise ValueError("same_attempt_journal_delta_cursor_changed")
    if (
        expected_attempt_record_path
        != _runtime_attempt_retention_path(
            runtime_admission.runtime_root, apply_attempt_id
        )
        or expected_journal_path
        != runtime_transaction_journal_path(
            runtime_admission.runtime_root, apply_attempt_id
        )
    ):
        raise ValueError("same_attempt_journal_delta_path_changed")
    layout = persisted.runtime_layout_bootstrap
    if not isinstance(layout, Mapping):
        raise ValueError("same_attempt_journal_delta_layout_changed")
    identities = _validated_complete_layout_successor_identities(
        layout=layout, runtime_root=runtime_admission.runtime_root
    )
    attempt_raw, attempt_identity = _read_exact_runtime_external_file(
        expected_attempt_record_path,
        expected_parent_identity=identities["attempt_retention"],
        maximum_size=RUNTIME_ATTEMPT_RETENTION_MAX_BYTES,
    )
    journal_raw, journal_identity = _read_exact_runtime_external_file(
        expected_journal_path,
        expected_parent_identity=identities["transactions"],
        maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
    )
    attempt_sha256 = "sha256:" + hashlib.sha256(attempt_raw).hexdigest()
    journal_sha256 = "sha256:" + hashlib.sha256(journal_raw).hexdigest()
    record = _runtime_attempt_retention_from_raw(
        attempt_raw, runtime_root=runtime_admission.runtime_root
    )
    journal = parse_runtime_transaction_journal_bytes(
        journal_raw, expected_transaction_id=apply_attempt_id
    )
    planned_record = record.state in {
        "CANDIDATE_PLANNED",
        "PRIOR_OWNER_PLANNED",
    }
    bound_record = record.state in {
        "CANDIDATE_BOUND",
        "PRIOR_OWNER_BOUND",
    }
    evidence_checks = {
        "attempt_identity": attempt_identity
        == tuple(expected_attempt_record_identity),
        "attempt_sha256": attempt_sha256 == expected_attempt_record_sha256,
        "journal_identity": journal_identity == tuple(expected_journal_identity),
        "journal_sha256": journal_sha256 == expected_journal_sha256,
        "attempt_id": record.apply_attempt_id == apply_attempt_id,
        "owner_run": record.retention_owner_run_id
        == runtime_admission.retention_owner_run_id,
        "package": record.package_root_sha256
        == "sha256:" + journal.package_root_sha256,
        "deck": journal.deck_name == persisted.deck_name,
        "phase": journal.phase.name == expected_journal_phase,
        "record_state": planned_record or bound_record,
        "record_journal_projection": (
            planned_record
            and expected_journal_phase == "PREPARED"
            and record.journal_path is None
            and record.journal_identity is None
            and record.journal_sha256 is None
        )
        or (bound_record and record.journal_path == expected_journal_path),
        "record_planned_journal_path": record.planned_journal_path
        == expected_journal_path,
        "record_planned_journal_size": (
            record.planned_journal_size == len(journal_raw)
            if planned_record
            else type(record.planned_journal_size) is int
            and record.planned_journal_size > 0
        ),
        "record_planned_journal_sha256": (
            record.planned_journal_sha256 == journal_sha256
            if planned_record
            else isinstance(record.planned_journal_sha256, str)
            and record.planned_journal_sha256.startswith("sha256:")
            and len(record.planned_journal_sha256) == 71
        ),
    }
    failed_evidence = tuple(
        name for name, matches in evidence_checks.items() if not matches
    )
    if failed_evidence:
        raise ValueError(
            "same_attempt_journal_delta_evidence_changed:"
            + ",".join(failed_evidence)
        )
    _, sealed, current = _load_bound_same_attempt_snapshots(
        lease_pair=lease_pair,
        runtime_admission=runtime_admission,
        apply_attempt_id=apply_attempt_id,
    )

    def validate_lifetime() -> None:
        active = _require_active_controller_apply_pair(lease_pair)
        if active.runtime_admission is not runtime_admission:
            raise ValueError("same_attempt_journal_delta_pair_changed")

    return (
        apply_invocation_module._mint_validated_same_attempt_journal_delta(
            pair_authority=lease_pair.pair_token,
            runtime_admission=runtime_admission,
            pair_lifetime_validator=validate_lifetime,
            sealed=sealed,
            current=current,
            apply_attempt_id=apply_attempt_id,
        ),
        sealed,
        current,
    )


def validate_same_attempt_journal_delta_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    apply_attempt_id: str,
    expected_attempt_record_path: Path,
    expected_attempt_record_identity: PathIdentity,
    expected_attempt_record_sha256: str,
    expected_journal_path: Path,
    expected_journal_identity: PathIdentity,
    expected_journal_sha256: str,
    expected_journal_phase: str,
) -> apply_invocation_module.ValidatedSameAttemptJournalDelta:
    delta, _, _ = _validate_same_attempt_journal_delta_with_snapshot(
        lease_pair=lease_pair,
        runtime_admission=runtime_admission,
        apply_attempt_id=apply_attempt_id,
        expected_attempt_record_path=expected_attempt_record_path,
        expected_attempt_record_identity=expected_attempt_record_identity,
        expected_attempt_record_sha256=expected_attempt_record_sha256,
        expected_journal_path=expected_journal_path,
        expected_journal_identity=expected_journal_identity,
        expected_journal_sha256=expected_journal_sha256,
        expected_journal_phase=expected_journal_phase,
    )
    return delta


def _same_attempt_pre_apply_snapshot_is_exact(
    *,
    recovery: Mapping[str, Any],
    lease_pair: ControllerApplyLeasePair,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    expected_journal_phase: str = "RUNTIME_VERIFIED",
) -> bool:
    attempt_prefix = (
        "successor_attempt_record"
        if recovery.get("successor_attempt_record_path") is not None
        else "predecessor_attempt_record"
    )
    journal_prefix = (
        "successor_journal"
        if recovery.get("successor_journal_path") is not None
        else "predecessor_journal"
    )
    delta: apply_invocation_module.ValidatedSameAttemptJournalDelta | None = None
    delta, sealed, current = _validate_same_attempt_journal_delta_with_snapshot(
        lease_pair=lease_pair,
        runtime_admission=runtime_admission,
        apply_attempt_id=str(recovery["apply_attempt_id"]),
        expected_attempt_record_path=Path(str(recovery[f"{attempt_prefix}_path"])),
        expected_attempt_record_identity=tuple(recovery[f"{attempt_prefix}_identity"]),
        expected_attempt_record_sha256=str(recovery[f"{attempt_prefix}_sha256"]),
        expected_journal_path=Path(str(recovery[f"{journal_prefix}_path"])),
        expected_journal_identity=tuple(recovery[f"{journal_prefix}_identity"]),
        expected_journal_sha256=str(recovery[f"{journal_prefix}_sha256"]),
        expected_journal_phase=expected_journal_phase,
        recovery_cursor=recovery,
    )
    try:
        apply_invocation_module.require_same_attempt_pre_apply_snapshot(
            sealed=sealed,
            current=current,
            apply_attempt_id=str(recovery["apply_attempt_id"]),
            validated_delta=delta,
        )
    finally:
        if delta is not None:
            apply_invocation_module._retire_validated_same_attempt_journal_delta(
                validated_delta=delta,
                pair_authority=lease_pair.pair_token,
                runtime_admission=runtime_admission,
            )
    active = _require_active_controller_apply_pair(lease_pair)
    if active.runtime_admission is not runtime_admission:
        raise ValueError("runtime_snapshot_pair_changed")
    return True


def _journal_less_same_attempt_pre_apply_snapshot_is_exact(
    *,
    recovery: Mapping[str, Any],
    lease_pair: ControllerApplyLeasePair,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
) -> bool:
    _, sealed, current = _load_bound_same_attempt_snapshots(
        lease_pair=lease_pair,
        runtime_admission=runtime_admission,
        apply_attempt_id=str(recovery["apply_attempt_id"]),
    )
    apply_attempt_id = str(recovery["apply_attempt_id"])
    if apply_attempt_id in sealed.transaction_ids:
        raise ValueError("pre_apply_snapshot_attempt_preexisting")
    exact = current.canonical_json == sealed.canonical_json
    if exact:
        apply_invocation_module.require_same_attempt_pre_apply_snapshot(
            sealed=sealed,
            current=current,
            apply_attempt_id=apply_attempt_id,
            validated_delta=None,
        )
    active = _require_active_controller_apply_pair(lease_pair)
    if active.runtime_admission is not runtime_admission:
        raise ValueError("runtime_snapshot_pair_changed")
    return exact


def _exact_abandonable_prior_owner_journal_intent(
    recovery: Mapping[str, Any],
) -> bool:
    external = recovery.get("external_file_action")
    if not isinstance(external, Mapping):
        return False
    final = Path(str(external.get("final_path")))
    staging = Path(str(external.get("staging_path")))
    inner = Path(str(external.get("inner_temp_path")))
    selected = recovery.get("expected_action") in {
        "observe_not_committed",
        "observe_unknown",
    }
    expected_index = int(recovery["action_index"]) - (1 if selected else 0)
    planned_fields_match = all(
        external.get(external_field) == recovery.get(planned_field)
        for external_field, planned_field in (
            ("final_path", "planned_journal_successor_path"),
            ("parent_identity", "planned_journal_successor_parent_identity"),
            ("planned_successor_size", "planned_journal_successor_size"),
            ("planned_successor_sha256", "planned_journal_successor_sha256"),
        )
    )
    return (
        recovery.get("install_route") == "prior_owner"
        and recovery.get("planned_journal_successor_phase") == "PREPARED"
        and external.get("action_kind") == "materialize_file_action_staging"
        and external.get("stage") == "PLANNED"
        and external.get("action_index") == expected_index
        and external.get("commit_mode") == "create_no_replace"
        and external.get("predecessor_state") == "absent"
        and external.get("predecessor_identity") is None
        and external.get("predecessor_size") is None
        and external.get("predecessor_sha256") is None
        and planned_fields_match
        and path_identity(final.parent)
        == tuple(recovery["planned_journal_successor_parent_identity"])
        and not path_lexists(final)
        and not path_lexists(staging)
        and not path_lexists(inner)
    )


def _prove_exact_prior_owner_bound_pre_ini_no_commit(
    *,
    recovery: Mapping[str, Any],
    observation: _ExactPairedRuntimeAttemptObservation,
    persisted: LiveStartSession,
    lease_pair: ControllerApplyLeasePair,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
) -> Literal["not_committed", "resume"] | None:
    """Prove the exact non-owning PREPARED predecessor before its INI step."""

    action = recovery.get("expected_action")
    retained = observation.retention
    journal = observation.transaction.journal
    record = retained.record if retained is not None else None
    if (
        recovery.get("install_route") != "prior_owner"
        or action
        not in {"materialize_file_action_staging", "observe_not_committed"}
        or record is None
        or record.state != "PRIOR_OWNER_BOUND"
        or journal is None
        or journal.phase != RuntimeTransactionPhase.PREPARED
    ):
        return None
    if recovery.get("deck_config_ini_sha256") is not None:
        return None

    invalid = "runtime_prior_owner_bound_precommit_authority_invalid"
    layout = persisted.runtime_layout_bootstrap
    if not isinstance(layout, Mapping):
        raise ValueError(invalid)
    runtime_root = runtime_admission.runtime_root
    layout_identities = _validated_complete_layout_successor_identities(
        layout=layout,
        runtime_root=runtime_root,
    )
    attempt_id = str(recovery["apply_attempt_id"])
    attempt_path = _runtime_attempt_retention_path(runtime_root, attempt_id)
    journal_path = runtime_transaction_journal_path(runtime_root, attempt_id)
    target = Path(str(recovery.get("renamed_target_path")))
    target_identity = tuple(
        recovery.get("successor_renamed_target_identity", ())
    )
    target_package_sha256 = (
        "sha256:" + target.name.rsplit("--sha256-", 1)[1]
        if "--sha256-" in target.name
        else None
    )
    owner_path = Path(
        str(recovery.get("predecessor_target_owner_journal_path"))
    )
    external = recovery.get("external_file_action")
    expected_external_index = int(recovery["action_index"]) - (
        1 if action == "observe_not_committed" else 0
    )
    expected_fence_raw = _retention_bytes_for_recovery_action(
        recovery,
        state="PRIOR_OWNER_BOUND",
    )
    expected_fence_sha256 = (
        "sha256:" + hashlib.sha256(expected_fence_raw).hexdigest()
    )
    candidate = runtime_root / ".hsconfig" / "staging" / attempt_id
    if (
        recovery.get("stable_physical_disposition") is not None
        or recovery.get("deck_config_ini_sha256") is not None
        or recovery.get("owner_retirement") is not None
        or observation.authority_contradiction is not None
        or observation.transaction.controller_staging_path is not None
        or observation.transaction.legacy_temp_path is not None
        or retained is None
        or retained.path != attempt_path
        or retained.identity
        != tuple(recovery.get("successor_attempt_record_identity", ()))
        or retained.raw_sha256
        != recovery.get("successor_attempt_record_sha256")
        or retained.raw_sha256 != expected_fence_sha256
        or any(
            recovery.get(f"predecessor_attempt_record_{suffix}") is not None
            for suffix in ("path", "identity", "sha256")
        )
        or record.schema_version != RUNTIME_ATTEMPT_RETENTION_SCHEMA_VERSION
        or record.apply_attempt_id != attempt_id
        or record.retention_owner_run_id != recovery.get("run_id")
        or record.package_root_sha256 != target_package_sha256
        or record.journal_path != journal_path
        or record.journal_identity
        != tuple(recovery.get("successor_journal_identity", ()))
        or record.journal_sha256 != recovery.get("successor_journal_sha256")
        or record.planned_journal_path != journal_path
        or record.planned_journal_size != observation.transaction.journal_size
        or record.planned_journal_sha256
        != observation.transaction.journal_sha256
        or record.target_path != target
        or record.target_identity != target_identity
        or record.owns_target is not False
        or record.target_owner_journal_path != owner_path
        or record.target_owner_journal_identity
        != tuple(
            recovery.get("predecessor_target_owner_journal_identity", ())
        )
        or record.target_owner_journal_sha256
        != recovery.get("predecessor_target_owner_journal_sha256")
        or any(
            recovery.get(f"predecessor_journal_{suffix}") is not None
            for suffix in ("path", "identity", "sha256")
        )
        or observation.transaction.journal_path != journal_path
        or observation.transaction.journal_identity
        != tuple(recovery.get("successor_journal_identity", ()))
        or observation.transaction.journal_sha256
        != recovery.get("successor_journal_sha256")
        or journal.schema_version != 1
        or journal.transaction_id != attempt_id
        or journal.deck_name != persisted.deck_name
        or "sha256:" + journal.package_root_sha256
        != target_package_sha256
        or journal.candidate_identity is not None
        or journal.target_identity is not None
        or journal.owns_target is not False
        or runtime_root / journal.candidate_path != candidate
        or runtime_root / journal.target_path != target
        or recovery.get("predecessor_renamed_target_identity")
        != recovery.get("successor_renamed_target_identity")
        or record.candidate_path is not None
        or record.candidate_parent_identity is not None
        or record.candidate_identity is not None
        or any(
            recovery.get(field_name) is not None
            for field_name in (
                "candidate_path",
                "candidate_parent_identity",
                "predecessor_candidate_identity",
                "successor_candidate_identity",
            )
        )
        or any(
            recovery.get(field_name) is not None
            for field_name in _APPLY_RECOVERY_FIELDS
            if field_name.startswith("candidate_tree_")
        )
        or any(
            recovery.get(f"successor_target_owner_journal_{suffix}")
            is not None
            for suffix in ("path", "identity", "sha256")
        )
        or not isinstance(external, Mapping)
        or external.get("stage") != "PLANNED"
        or external.get("action_kind") != "materialize_file_action_staging"
        or external.get("action_index") != expected_external_index
    ):
        raise ValueError(invalid)

    _require_retained_child_absent(
        candidate,
        expected_parent_identity=layout_identities["staging"],
    )
    _observe_retained_directory(
        target,
        expected_identity=target_identity,
        expected_parent_identity=layout_identities["custom_config"],
    )
    owner_raw, owner_identity = _read_exact_runtime_external_file(
        owner_path,
        expected_parent_identity=layout_identities["transactions"],
        maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
    )
    owner = parse_runtime_transaction_journal_bytes(
        owner_raw,
        expected_transaction_id=owner_path.stem,
    )
    if (
        owner_path == journal_path
        or owner_identity
        != tuple(
            recovery.get("predecessor_target_owner_journal_identity", ())
        )
        or "sha256:" + hashlib.sha256(owner_raw).hexdigest()
        != recovery.get("predecessor_target_owner_journal_sha256")
        or owner.phase != RuntimeTransactionPhase.FINALIZED
        or owner.owns_target is not True
        or owner.target_identity != target_identity
        or runtime_root / owner.target_path != target
    ):
        raise ValueError(invalid)

    ini_path = runtime_root / "CustomConfig" / "deck_config.ini"
    staging_path = ini_path.with_name(f"{ini_path.name}.staged")
    inner_temp_path = staging_path.with_name(
        f".{staging_path.name}.live-start-atomic.tmp"
    )
    planned_journal_raw = runtime_transaction_journal_bytes(
        replace(
            journal,
            phase=RuntimeTransactionPhase.INI_COMMITTED,
            target_identity=target_identity,
            owns_target=False,
        )
    )
    if (
        Path(str(external.get("final_path"))) != ini_path
        or Path(str(external.get("staging_path"))) != staging_path
        or Path(str(external.get("inner_temp_path"))) != inner_temp_path
        or tuple(external.get("parent_identity", ()))
        != layout_identities["custom_config"]
        or path_identity(ini_path.parent)
        != layout_identities["custom_config"]
        or external.get("planned_successor_sha256")
        != "sha256:" + journal.next_ini_sha256
        or recovery.get("planned_journal_successor_path")
        != str(journal_path)
        or tuple(
            recovery.get("planned_journal_successor_parent_identity", ())
        )
        != layout_identities["transactions"]
        or recovery.get("planned_journal_successor_phase")
        != RuntimeTransactionPhase.INI_COMMITTED.name
        or recovery.get("planned_journal_successor_size")
        != len(planned_journal_raw)
        or recovery.get("planned_journal_successor_sha256")
        != "sha256:" + hashlib.sha256(planned_journal_raw).hexdigest()
    ):
        raise ValueError(invalid)
    if path_lexists(staging_path) or path_lexists(inner_temp_path):
        return "resume"

    predecessor_state = external.get("predecessor_state")
    if predecessor_state == "absent":
        if (
            external.get("commit_mode") != "create_no_replace"
            or external.get("predecessor_identity") is not None
            or external.get("predecessor_size") is not None
            or external.get("predecessor_sha256") is not None
            or journal.previous_ini_sha256 is not None
        ):
            raise ValueError(invalid)
        if path_lexists(ini_path):
            final_raw, _ = _read_exact_runtime_external_file(
                ini_path,
                expected_parent_identity=layout_identities["custom_config"],
                maximum_size=MAX_DECK_CONFIG_BYTES,
            )
            final_sha256 = "sha256:" + hashlib.sha256(final_raw).hexdigest()
            if (
                len(final_raw) == external.get("planned_successor_size")
                and final_sha256 == external.get("planned_successor_sha256")
            ):
                return "resume"
            raise ValueError(invalid)
        current_ini = read_deck_config(ini_path, deck_name=persisted.deck_name)
        if current_ini.existed or current_ini.sha256 is not None:
            raise ValueError(invalid)
    elif predecessor_state == "exact":
        predecessor_identity = tuple(
            external.get("predecessor_identity", ())
        )
        predecessor_size = external.get("predecessor_size")
        predecessor_sha256 = external.get("predecessor_sha256")
        if (
            external.get("commit_mode") != "replace_exact"
            or len(predecessor_identity) != 3
            or type(predecessor_size) is not int
            or not isinstance(predecessor_sha256, str)
            or journal.previous_ini_sha256 is None
            or predecessor_sha256
            != "sha256:" + journal.previous_ini_sha256
            or not path_lexists(ini_path)
        ):
            raise ValueError(invalid)
        final_raw, final_identity = _read_exact_runtime_external_file(
            ini_path,
            expected_parent_identity=layout_identities["custom_config"],
            maximum_size=MAX_DECK_CONFIG_BYTES,
        )
        final_sha256 = "sha256:" + hashlib.sha256(final_raw).hexdigest()
        if (
            final_identity != predecessor_identity
            or len(final_raw) != predecessor_size
            or final_sha256 != predecessor_sha256
        ):
            if (
                len(final_raw) == external.get("planned_successor_size")
                and final_sha256 == external.get("planned_successor_sha256")
            ):
                return "resume"
            raise ValueError(invalid)
        current_ini = read_deck_config(ini_path, deck_name=persisted.deck_name)
        if current_ini.sha256 != journal.previous_ini_sha256:
            raise ValueError(invalid)
    else:
        raise ValueError(invalid)

    planned_ini_raw = render_deck_config(
        current_ini,
        deck_name=persisted.deck_name,
        config_dir=journal.next_config_dir,
    )
    if (
        len(planned_ini_raw) != external.get("planned_successor_size")
        or "sha256:" + hashlib.sha256(planned_ini_raw).hexdigest()
        != external.get("planned_successor_sha256")
    ):
        raise ValueError(invalid)
    if not _same_attempt_pre_apply_snapshot_is_exact(
        recovery=recovery,
        lease_pair=lease_pair,
        runtime_admission=runtime_admission,
        expected_journal_phase="PREPARED",
    ):
        raise ValueError(invalid)
    final_layout_identities = _validated_complete_layout_successor_identities(
        layout=layout,
        runtime_root=runtime_root,
    )
    if dict(final_layout_identities) != dict(layout_identities):
        raise ValueError(invalid)
    final_observation = _observe_exact_paired_runtime_attempt(
        runtime_root,
        transaction_id=attempt_id,
        expected_retention_owner_run_id=(
            runtime_admission.retention_owner_run_id
        ),
        expected_package_root_sha256=str(recovery["package_root_sha256"]),
        expected_deck_name=persisted.deck_name,
        recovery_cursor=recovery,
        tolerate_bounded_authority_contradiction=False,
        layout_identities=final_layout_identities,
    )
    _require_recovery_cursor_observation_matches(
        recovery=recovery,
        observation=final_observation,
        action=str(action),
        allow_committed_journal_successor=False,
        allow_retired_legacy_temp=False,
    )
    if (
        final_observation.authority_contradiction is not None
        or final_observation.transaction.controller_staging_path is not None
        or final_observation.transaction.legacy_temp_path is not None
        or path_lexists(staging_path)
        or path_lexists(inner_temp_path)
    ):
        raise ValueError(invalid)
    _require_retained_child_absent(
        candidate,
        expected_parent_identity=final_layout_identities["staging"],
    )
    if predecessor_state == "absent":
        _require_retained_child_absent(
            ini_path,
            expected_parent_identity=final_layout_identities["custom_config"],
        )
    else:
        final_raw, final_identity = _read_exact_runtime_external_file(
            ini_path,
            expected_parent_identity=final_layout_identities["custom_config"],
            maximum_size=MAX_DECK_CONFIG_BYTES,
        )
        if (
            final_identity != predecessor_identity
            or len(final_raw) != predecessor_size
            or "sha256:" + hashlib.sha256(final_raw).hexdigest()
            != predecessor_sha256
        ):
            raise ValueError(invalid)
    active = _require_active_controller_apply_pair(lease_pair)
    if active.runtime_admission is not runtime_admission:
        raise ValueError(invalid)
    return "not_committed"


def _prove_exact_new_target_precommit_no_commit(
    *,
    recovery: Mapping[str, Any],
    observation: _ExactPairedRuntimeAttemptObservation,
    package_lease: PackageInputLease,
    persisted: LiveStartSession,
    profile_lease: OperatorProfileLease,
    session_root: Path,
    lease_pair: ControllerApplyLeasePair,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
) -> Literal["not_committed", "resume", "unknown"] | None:
    action = recovery.get("expected_action")
    journal = observation.transaction.journal
    planned_create_observation = action in {
        "materialize_file_action_staging",
        "observe_not_committed",
    }
    active_create_observation = action in {
        "materialize_file_action_staging",
        "observe_not_committed",
        "observe_unknown",
    }
    prebind_no_tree_observation = action in {
        "bind_created_candidate",
        "observe_not_committed",
        "observe_unknown",
    }
    record = (
        observation.retention.record
        if observation.retention is not None
        else None
    )
    if (
        recovery.get("install_route") == "new_target"
        and active_create_observation
        and journal is None
        and record is not None
        and record.state == "ACTIVE"
    ):
        layout = persisted.runtime_layout_bootstrap
        external = recovery.get("external_file_action")
        retained = observation.retention
        if not isinstance(layout, Mapping) or not isinstance(
            external, Mapping
        ):
            raise ValueError("runtime_failure_selection_layout_changed")
        layout_identities = _validated_complete_layout_successor_identities(
            layout=layout,
            runtime_root=Path(str(recovery["runtime_root"])),
        )
        attempt_path = _runtime_attempt_retention_path(
            runtime_admission.runtime_root,
            str(recovery["apply_attempt_id"]),
        )
        candidate = Path(str(recovery["candidate_path"]))
        target = Path(str(recovery["renamed_target_path"]))
        journal_path = runtime_transaction_journal_path(
            runtime_admission.runtime_root,
            str(recovery["apply_attempt_id"]),
        )
        staging = Path(str(external.get("staging_path")))
        inner = Path(str(external.get("inner_temp_path")))
        journal_staging = journal_path.with_name(f"{journal_path.name}.staged")
        journal_inner = journal_path.with_name(
            f".{journal_path.name}.staged.live-start-atomic.tmp"
        )
        expected_external_index = int(recovery["action_index"]) - (
            1 if action in {"observe_not_committed", "observe_unknown"} else 0
        )
        active_raw = _retention_bytes_for_recovery_action(
            recovery,
            state="ACTIVE",
        )
        planned_raw = _retention_bytes_for_recovery_action(
            recovery,
            state="CANDIDATE_PLANNED",
        )
        active_sha256 = "sha256:" + hashlib.sha256(active_raw).hexdigest()
        planned_sha256 = "sha256:" + hashlib.sha256(planned_raw).hexdigest()
        if (
            retained is None
            or retained.path != attempt_path
            or retained.raw_sha256 != active_sha256
            or recovery.get("successor_attempt_record_path")
            != str(attempt_path)
            or tuple(recovery.get("successor_attempt_record_identity", ()))
            != retained.identity
            or recovery.get("successor_attempt_record_sha256")
            != active_sha256
            or recovery.get("predecessor_attempt_record_path") is not None
            or recovery.get("predecessor_journal_path") is not None
            or recovery.get("successor_journal_identity") is not None
            or recovery.get("predecessor_candidate_identity") is not None
            or recovery.get("successor_candidate_identity") is not None
            or recovery.get("predecessor_renamed_target_identity") is not None
            or recovery.get("successor_renamed_target_identity") is not None
            or recovery.get("candidate_tree_manifest_sha256") is not None
            or recovery.get("candidate_tree_verified_sha256") is not None
            or recovery.get("candidate_tree_entry_count") is not None
            or recovery.get("candidate_tree_cursor") is not None
            or recovery.get("candidate_tree_next_relative_path") is not None
            or recovery.get("deck_config_ini_sha256") is not None
            or external.get("action_kind")
            != "materialize_file_action_staging"
            or external.get("stage") != "PLANNED"
            or external.get("action_index") != expected_external_index
            or external.get("commit_mode") != "replace_exact"
            or Path(str(external.get("final_path"))) != attempt_path
            or tuple(external.get("parent_identity", ()))
            != layout_identities["attempt_retention"]
            or tuple(external.get("predecessor_identity", ()))
            != retained.identity
            or external.get("predecessor_size") != len(active_raw)
            or external.get("predecessor_sha256") != active_sha256
            or external.get("planned_successor_size") != len(planned_raw)
            or external.get("planned_successor_sha256") != planned_sha256
            or path_lexists(staging)
            or path_lexists(inner)
            or candidate
            != runtime_admission.runtime_root
            / ".hsconfig"
            / "staging"
            / str(recovery["apply_attempt_id"])
            or path_identity(candidate.parent) != layout_identities["staging"]
            or path_lexists(candidate)
            or path_identity(target.parent)
            != layout_identities["custom_config"]
            or path_lexists(target)
            or recovery.get("planned_journal_successor_path")
            != str(journal_path)
            or tuple(
                recovery.get("planned_journal_successor_parent_identity", ())
            )
            != layout_identities["transactions"]
            or recovery.get("planned_journal_successor_phase") != "PREPARED"
            or path_lexists(journal_path)
            or path_lexists(journal_staging)
            or path_lexists(journal_inner)
            or path_identity(journal_path.parent)
            != layout_identities["transactions"]
        ):
            raise ValueError("runtime_new_target_precommit_authority_invalid")
        if not _journal_less_same_attempt_pre_apply_snapshot_is_exact(
            recovery=recovery,
            lease_pair=lease_pair,
            runtime_admission=runtime_admission,
        ):
            return "unknown"
        return "not_committed"
    if (
        recovery.get("install_route") == "new_target"
        and prebind_no_tree_observation
        and journal is not None
        and journal.phase == RuntimeTransactionPhase.PREPARED
        and record is not None
        and record.state == "CANDIDATE_PLANNED"
        and recovery.get("external_file_action") is None
        and recovery.get("predecessor_candidate_identity") is None
        and recovery.get("successor_candidate_identity") is None
    ):
        layout = persisted.runtime_layout_bootstrap
        retained = observation.retention
        if not isinstance(layout, Mapping) or retained is None:
            raise ValueError("runtime_failure_selection_layout_changed")
        runtime_root = runtime_admission.runtime_root
        layout_identities = _validated_complete_layout_successor_identities(
            layout=layout,
            runtime_root=runtime_root,
        )
        attempt_id = str(recovery["apply_attempt_id"])
        attempt_path = _runtime_attempt_retention_path(
            runtime_root,
            attempt_id,
        )
        journal_path = runtime_transaction_journal_path(
            runtime_root,
            attempt_id,
        )
        candidate = runtime_root / ".hsconfig" / "staging" / attempt_id
        target = Path(str(recovery["renamed_target_path"]))
        retention_staging = attempt_path.with_name(
            f"{attempt_path.name}.staged"
        )
        retention_inner = attempt_path.with_name(
            f".{attempt_path.name}.staged.live-start-atomic.tmp"
        )
        if (
            recovery.get("external_file_action") is not None
            or retained.path != attempt_path
            or recovery.get("successor_attempt_record_path")
            != str(attempt_path)
            or tuple(recovery.get("successor_attempt_record_identity", ()))
            != retained.identity
            or recovery.get("successor_attempt_record_sha256")
            != retained.raw_sha256
            or any(
                recovery.get(f"predecessor_attempt_record_{suffix}")
                is not None
                for suffix in ("path", "identity", "sha256")
            )
            or recovery.get("successor_journal_path") != str(journal_path)
            or tuple(recovery.get("successor_journal_identity", ()))
            != observation.transaction.journal_identity
            or recovery.get("successor_journal_sha256")
            != observation.transaction.journal_sha256
            or any(
                recovery.get(f"predecessor_journal_{suffix}") is not None
                for suffix in ("path", "identity", "sha256")
            )
            or any(
                recovery.get(f"{prefix}_{suffix}") is not None
                for prefix, suffixes in (
                    (
                        "predecessor_target_owner_journal",
                        ("path", "identity", "sha256"),
                    ),
                    (
                        "successor_target_owner_journal",
                        ("path", "identity", "sha256"),
                    ),
                    (
                        "predecessor_transaction_temp",
                        (
                            "path",
                            "parent_identity",
                            "identity",
                            "size",
                            "sha256",
                            "classification",
                            "origin",
                        ),
                    ),
                    (
                        "successor_transaction_temp",
                        (
                            "path",
                            "parent_identity",
                            "identity",
                            "size",
                            "sha256",
                            "classification",
                            "origin",
                        ),
                    ),
                )
                for suffix in suffixes
            )
            or recovery.get("owner_retirement") is not None
            or record.journal_path is not None
            or record.journal_identity is not None
            or record.journal_sha256 is not None
            or record.planned_journal_path != journal_path
            or record.planned_journal_size
            != observation.transaction.journal_size
            or record.planned_journal_sha256
            != observation.transaction.journal_sha256
            or record.package_root_sha256
            != "sha256:" + journal.package_root_sha256
            or recovery.get("planned_journal_successor_path") is not None
            or recovery.get("planned_journal_successor_parent_identity")
            is not None
            or recovery.get("planned_journal_successor_phase") is not None
            or recovery.get("planned_journal_successor_size") is not None
            or recovery.get("planned_journal_successor_sha256") is not None
            or Path(str(recovery.get("candidate_path"))) != candidate
            or tuple(recovery.get("candidate_parent_identity", ()))
            != layout_identities["staging"]
            or recovery.get("predecessor_candidate_identity") is not None
            or recovery.get("successor_candidate_identity") is not None
            or any(
                recovery.get(field_name) is not None
                for field_name in _APPLY_RECOVERY_FIELDS
                if field_name.startswith("candidate_tree_")
            )
            or record.candidate_path != candidate
            or record.candidate_parent_identity
            != layout_identities["staging"]
            or record.candidate_identity is not None
            or record.target_path is not None
            or record.target_identity is not None
            or record.owns_target is not False
            or record.target_owner_journal_path is not None
            or runtime_root / journal.candidate_path != candidate
            or runtime_root / journal.target_path != target
            or journal.candidate_identity is not None
            or journal.target_identity is not None
            or journal.owns_target
            or observation.transaction.controller_staging_path is not None
            or observation.transaction.legacy_temp_path is not None
            or path_lexists(retention_staging)
            or path_lexists(retention_inner)
            or path_identity(attempt_path.parent)
            != layout_identities["attempt_retention"]
            or path_lexists(candidate)
            or path_identity(candidate.parent) != layout_identities["staging"]
            or path_lexists(target)
            or path_identity(target.parent)
            != layout_identities["custom_config"]
            or path_identity(journal_path.parent)
            != layout_identities["transactions"]
        ):
            raise ValueError("runtime_new_target_precommit_authority_invalid")
        ini = read_deck_config(
            runtime_root / "CustomConfig" / "deck_config.ini",
            deck_name=journal.deck_name,
        )
        if ini.sha256 != journal.previous_ini_sha256:
            raise ValueError("runtime_new_target_precommit_authority_invalid")
        if not _same_attempt_pre_apply_snapshot_is_exact(
            recovery=recovery,
            lease_pair=lease_pair,
            runtime_admission=runtime_admission,
            expected_journal_phase="PREPARED",
        ):
            raise ValueError("runtime_new_target_precommit_authority_invalid")
        return "not_committed"
    if (
        recovery.get("install_route") == "new_target"
        and planned_create_observation
        and journal is not None
        and journal.phase == RuntimeTransactionPhase.PREPARED
        and record is not None
        and record.state == "CANDIDATE_PLANNED"
    ):
        layout = persisted.runtime_layout_bootstrap
        if not isinstance(layout, Mapping):
            raise ValueError("runtime_failure_selection_layout_changed")
        layout_identities = _validated_complete_layout_successor_identities(
            layout=layout,
            runtime_root=Path(str(recovery["runtime_root"])),
        )
        candidate = Path(str(recovery["candidate_path"]))
        target = Path(str(recovery["renamed_target_path"]))
        external = recovery.get("external_file_action")
        candidate_identity = recovery.get("successor_candidate_identity")
        expected_external_index = int(recovery["action_index"]) - (
            1 if action == "observe_not_committed" else 0
        )
        if (
            not isinstance(external, Mapping)
            or not isinstance(candidate_identity, (list, tuple))
            or recovery.get("predecessor_candidate_identity") is not None
            or recovery.get("candidate_tree_manifest_sha256") is not None
            or recovery.get("candidate_tree_verified_sha256") is not None
            or record.candidate_path != candidate
            or record.candidate_identity is not None
            or record.candidate_parent_identity
            != layout_identities["staging"]
            or tuple(recovery.get("candidate_parent_identity", ()))
            != layout_identities["staging"]
            or journal.candidate_identity is not None
            or journal.owns_target
            or external.get("action_kind")
            != "materialize_file_action_staging"
            or external.get("stage") != "PLANNED"
            or external.get("action_index") != expected_external_index
            or external.get("commit_mode") != "replace_exact"
            or Path(str(external.get("final_path")))
            != Path(str(recovery["successor_attempt_record_path"]))
            or tuple(external.get("parent_identity", ()))
            != layout_identities["attempt_retention"]
            or tuple(external.get("predecessor_identity", ()))
            != tuple(recovery["successor_attempt_record_identity"])
            or external.get("predecessor_sha256")
            != recovery["successor_attempt_record_sha256"]
            or path_lexists(Path(str(external.get("staging_path"))))
            or path_lexists(Path(str(external.get("inner_temp_path"))))
            or Path(str(recovery["runtime_root"])) / journal.candidate_path
            != candidate
            or Path(str(recovery["runtime_root"])) / journal.target_path
            != target
            or path_identity(candidate.parent) != layout_identities["staging"]
            or path_identity(target.parent)
            != layout_identities["custom_config"]
            or path_lexists(target)
        ):
            raise ValueError("runtime_new_target_precommit_authority_invalid")
        try:
            _require_runtime_layout_directory(
                candidate,
                expected_parent_identity=layout_identities["staging"],
                expected_identity=tuple(candidate_identity),
                require_empty=True,
            )
        except ValueError as error:
            raise ValueError(
                "runtime_new_target_precommit_authority_invalid"
            ) from error
        ini_path = (
            Path(str(recovery["runtime_root"]))
            / "CustomConfig"
            / "deck_config.ini"
        )
        ini = read_deck_config(ini_path, deck_name=journal.deck_name)
        if ini.sha256 == journal.next_ini_sha256:
            return "resume"
        if ini.sha256 != journal.previous_ini_sha256:
            raise ValueError("runtime_new_target_precommit_authority_invalid")
        snapshot_exact = _same_attempt_pre_apply_snapshot_is_exact(
            recovery=recovery,
            lease_pair=lease_pair,
            runtime_admission=runtime_admission,
            expected_journal_phase="PREPARED",
        )
        if not snapshot_exact:
            raise ValueError("runtime_new_target_precommit_authority_invalid")
        return "not_committed"
    if (
        recovery.get("install_route") != "new_target"
        or action not in {
            "rename_candidate_to_target",
            "materialize_file_action_staging",
            "bind_renamed_target",
            "observe_not_committed",
            "observe_unknown",
        }
        or recovery.get("deck_config_ini_sha256") is not None
        or journal is None
        or journal.phase != RuntimeTransactionPhase.RUNTIME_VERIFIED
        or journal.transaction_id != recovery.get("apply_attempt_id")
        or (
            journal.owns_target is not False
            and not (
                action == "bind_renamed_target"
                and journal.owns_target is True
            )
        )
    ):
        return None
    layout = persisted.runtime_layout_bootstrap
    if not isinstance(layout, Mapping):
        raise ValueError("runtime_failure_selection_layout_changed")
    layout_identities = _validated_complete_layout_successor_identities(
        layout=layout,
        runtime_root=Path(str(recovery["runtime_root"])),
    )
    manifest, manifest_sha256 = _candidate_manifest_from_pair(
        package_lease=package_lease,
        deck_name=persisted.deck_name,
    )
    entries = tuple(manifest["entries"])
    if (
        recovery.get("candidate_tree_manifest_sha256") != manifest_sha256
        or recovery.get("candidate_tree_verified_sha256") != manifest_sha256
        or recovery.get("candidate_tree_entry_count") != len(entries)
        or recovery.get("candidate_tree_cursor") != len(entries)
    ):
        raise ValueError("runtime_failure_selection_manifest_changed")
    candidate = Path(str(recovery["candidate_path"]))
    target = Path(str(recovery["renamed_target_path"]))
    external = recovery.get("external_file_action")
    observation_candidate = (
        action in {"observe_not_committed", "observe_unknown"}
        and external is None
    )
    if action == "rename_candidate_to_target" or observation_candidate:
        candidate_parent_identity = tuple(recovery["candidate_parent_identity"])
        if path_identity(candidate.parent) != candidate_parent_identity:
            raise ValueError("runtime_failure_selection_tree_parent_changed")
        if path_lexists(candidate):
            root = candidate
            root_identity = recovery.get("predecessor_candidate_identity")
            if root_identity is None:
                root_identity = recovery.get("successor_candidate_identity")
            parent_identity = candidate_parent_identity
            opposite = target
            opposite_parent_identity = layout_identities["custom_config"]
            physical_action_complete = False
            resume_after_validation = False
        else:
            root = target
            root_identity = recovery.get("successor_candidate_identity")
            parent_identity = layout_identities["custom_config"]
            opposite = candidate
            opposite_parent_identity = candidate_parent_identity
            physical_action_complete = True
            resume_after_validation = True
    else:
        if not isinstance(external, Mapping):
            raise ValueError("runtime_new_target_precommit_authority_invalid")
        if action == "bind_renamed_target":
            if external.get("stage") != "STAGING_BOUND":
                raise ValueError("runtime_new_target_precommit_authority_invalid")
            staging_path = Path(str(external.get("staging_path")))
            external_action_complete = not path_lexists(staging_path)
            resume_after_validation = True
        else:
            external_action_complete = False
            resume_after_validation = path_lexists(
                Path(str(external.get("staging_path")))
            ) or path_lexists(Path(str(external.get("inner_temp_path"))))
        if (
            external.get("stage")
            != (
                "STAGING_BOUND"
                if action == "bind_renamed_target"
                else "PLANNED"
            )
            or external.get("action_kind")
            != (
                "bind_renamed_target"
                if action == "bind_renamed_target"
                else "materialize_file_action_staging"
            )
            or external.get("action_index")
            != (
                int(recovery["action_index"]) - 1
                if action in {"observe_not_committed", "observe_unknown"}
                else recovery.get("action_index")
            )
            or external.get("commit_mode") != "replace_exact"
            or Path(str(external.get("final_path")))
            != Path(str(recovery.get("successor_journal_path")))
            or tuple(external.get("parent_identity", ()))
            != layout_identities["transactions"]
            or tuple(external.get("predecessor_identity", ()))
            != tuple(recovery.get("successor_journal_identity", ()))
            or external.get("predecessor_sha256")
            != recovery.get("successor_journal_sha256")
            or external.get("planned_successor_size")
            != recovery.get("planned_journal_successor_size")
            or external.get("planned_successor_sha256")
            != recovery.get("planned_journal_successor_sha256")
            or (
                action == "bind_renamed_target"
                and path_lexists(Path(str(external.get("inner_temp_path"))))
            )
        ):
            raise ValueError("runtime_new_target_precommit_authority_invalid")
        final_raw, final_identity = _read_exact_runtime_external_file(
            Path(str(external["final_path"])),
            expected_parent_identity=layout_identities["transactions"],
            maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
        )
        final_digest = "sha256:" + hashlib.sha256(final_raw).hexdigest()
        if external_action_complete:
            if (
                final_identity != tuple(external.get("staging_identity", ()))
                or len(final_raw) != external.get("planned_successor_size")
                or final_digest != external.get("planned_successor_sha256")
                or path_lexists(Path(str(external["staging_path"])))
            ):
                raise ValueError("runtime_new_target_precommit_authority_invalid")
        elif (
            final_identity != tuple(external["predecessor_identity"])
            or len(final_raw) != external.get("predecessor_size")
            or final_digest != external.get("predecessor_sha256")
        ):
            raise ValueError("runtime_new_target_precommit_authority_invalid")
        root = target
        root_identity = recovery.get("predecessor_renamed_target_identity")
        if root_identity is None:
            root_identity = recovery.get("successor_renamed_target_identity")
        parent_identity = layout_identities["custom_config"]
        opposite = candidate
        opposite_parent_identity = tuple(recovery["candidate_parent_identity"])
        physical_action_complete = False
    if not isinstance(root_identity, (list, tuple)):
        raise ValueError("runtime_failure_selection_tree_changed")
    if observation.authority_contradiction is not None:
        if observation.authority_contradiction.surface != "candidate_root":
            raise ValueError("runtime_new_target_precommit_authority_invalid")
        if not (action == "rename_candidate_to_target" or observation_candidate):
            raise ValueError("runtime_new_target_precommit_authority_invalid")
        try:
            marker_prerequisites_invalid = (
                path_identity(candidate.parent) != candidate_parent_identity
                or path_identity(target.parent)
                != layout_identities["custom_config"]
                or path_lexists(target)
            )
        except (FileNotFoundError, OSError, ValueError) as error:
            raise ValueError(
                "runtime_new_target_precommit_authority_invalid"
            ) from error
        if marker_prerequisites_invalid:
            raise ValueError("runtime_new_target_precommit_authority_invalid")
        ini_path = (
            Path(str(recovery["runtime_root"]))
            / "CustomConfig"
            / "deck_config.ini"
        )
        if path_identity(ini_path.parent) != layout_identities["custom_config"]:
            raise ValueError("runtime_failure_selection_ini_parent_changed")
        ini = read_deck_config(ini_path, deck_name=journal.deck_name)
        if ini.sha256 not in {
            journal.previous_ini_sha256,
            journal.next_ini_sha256,
        }:
            raise ValueError("runtime_new_target_precommit_authority_invalid")
        _require_bounded_authority_marker_content_exact(
            marker=observation.authority_contradiction,
            recovery=recovery,
            package_lease=package_lease,
            deck_name=persisted.deck_name,
            layout_identities=layout_identities,
        )
        if not _same_attempt_pre_apply_snapshot_is_exact(
            recovery=recovery,
            lease_pair=lease_pair,
            runtime_admission=runtime_admission,
        ):
            raise ValueError("runtime_new_target_precommit_authority_invalid")
        return "unknown"
    try:
        root_authority_changed = (
            path_identity(root.parent) != parent_identity
            or path_identity(root) != tuple(root_identity)
        )
    except (FileNotFoundError, OSError, ValueError) as error:
        raise ValueError(
            "runtime_new_target_precommit_authority_invalid"
        ) from error
    if root_authority_changed:
        raise ValueError("runtime_new_target_precommit_authority_invalid")
    try:
        _verify_candidate_tree_prefix(
            root=root,
            root_identity=tuple(root_identity),
            expected_parent_identity=parent_identity,
            entries=entries,
            cursor=len(entries),
        )
    except ValueError as error:
        raise ValueError(
            "runtime_new_target_precommit_authority_invalid"
        ) from error
    try:
        opposite_changed = (
            path_identity(opposite.parent) != opposite_parent_identity
            or path_lexists(opposite)
        )
    except (FileNotFoundError, OSError, ValueError) as error:
        raise ValueError(
            "runtime_new_target_precommit_authority_invalid"
        ) from error
    if opposite_changed:
        raise ValueError("runtime_new_target_precommit_authority_invalid")
    if physical_action_complete or resume_after_validation:
        return "resume"
    ini_path = Path(str(recovery["runtime_root"])) / "CustomConfig" / "deck_config.ini"
    if path_identity(ini_path.parent) != layout_identities["custom_config"]:
        raise ValueError("runtime_failure_selection_ini_parent_changed")
    ini = read_deck_config(ini_path, deck_name=journal.deck_name)
    if path_identity(ini_path.parent) != layout_identities["custom_config"]:
        raise ValueError("runtime_failure_selection_ini_parent_changed")
    if ini.sha256 == journal.next_ini_sha256:
        return "resume"
    if ini.sha256 != journal.previous_ini_sha256:
        raise ValueError("runtime_new_target_precommit_authority_invalid")
    if isinstance(external, Mapping) and Path(str(external.get("final_path"))) == ini_path:
        return "resume"
    if not _same_attempt_pre_apply_snapshot_is_exact(
        recovery=recovery,
        lease_pair=lease_pair,
        runtime_admission=runtime_admission,
    ):
        raise ValueError("runtime_new_target_precommit_authority_invalid")
    return "not_committed"


def observe_runtime_failure_selection_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    transaction_id: str,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    expected_recovery: RuntimeApplyRecoveryEvidence,
    observation_authorization: RuntimeObservationAuthorization,
) -> RuntimeObservationReceipt:
    """Mint the sole terminal-classification receipt for an exact cursor."""

    if type(observation_authorization) is not RuntimeObservationAuthorization:
        raise ValueError("runtime_failure_selection_authorization_invalid")
    selection: RuntimeFailureSelection | None = None

    def observe() -> RuntimeObservationPostcondition:
        nonlocal selection
        selection = classify_runtime_failure_from_pair(
            lease_pair=lease_pair,
            transaction_id=transaction_id,
            runtime_admission=runtime_admission,
            expected_recovery=expected_recovery,
        )
        if (
            selection.disposition != "select_terminal_observation"
            or selection.selected_observation is None
        ):
            raise ValueError("runtime_failure_selection_not_terminal")
        successor = _seal_apply_recovery_successor(
            expected_recovery.value,
            changes={
                "action_index": selection.expected_action_index + 1,
                "expected_action": selection.selected_observation,
            },
        )
        return RuntimeObservationPostcondition(
            action=transaction_id,
            observation_family="terminal_classification",
            evidence={"apply_recovery": successor},
        )

    return _execute_runtime_observation(
        observation_authorization=observation_authorization,
        observation_family="terminal_classification",
        read_only_observation=observe,
    )


def _terminal_cleanup_manifest_sha256(entries: object) -> str:
    value = _plain_json_value(entries)
    if not isinstance(value, list):
        raise ValueError("runtime_no_commit_cleanup_entries_invalid")
    raw = (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _validate_no_commit_cleanup_projection(
    *,
    inventory: TerminalResolutionCleanupInventory,
    cursor: int,
    allow_current_absent: bool,
) -> tuple[Path, Mapping[str, Any], bool, bool]:
    entries_value = inventory.value.get("entries")
    roots_value = inventory.value.get("cleanup_roots")
    if not isinstance(entries_value, tuple) or not isinstance(roots_value, tuple):
        raise ValueError("runtime_no_commit_cleanup_inventory_invalid")
    entries = tuple(entries_value)
    roots = tuple(roots_value)
    if (
        inventory.value.get("cleanup_entry_count") != len(entries)
        or not 0 <= cursor < len(entries)
        or inventory.value.get("cleanup_manifest_sha256")
        != _terminal_cleanup_manifest_sha256(entries)
    ):
        raise ValueError("runtime_no_commit_cleanup_manifest_invalid")
    root_by_role: dict[str, Mapping[str, Any]] = {}
    for root in roots:
        if not isinstance(root, Mapping):
            raise ValueError("runtime_no_commit_cleanup_roots_invalid")
        role = str(root.get("root_role"))
        if role in root_by_role:
            raise ValueError("runtime_no_commit_cleanup_roots_invalid")
        root_by_role[role] = root
    root_rows = {
        str(row.get("root_role")): row
        for row in entries
        if isinstance(row, Mapping) and row.get("relative_path") == "."
    }
    if set(root_rows) != set(root_by_role) or sum(
        isinstance(row, Mapping) and row.get("relative_path") == "."
        for row in entries
    ) != len(root_by_role):
        raise ValueError("runtime_no_commit_cleanup_root_rows_invalid")
    row_by_key = {
        (str(row["root_role"]), str(row["relative_path"])): row
        for row in entries
    }
    for role, root in root_by_role.items():
        root_row = root_rows[role]
        if (
            root_row.get("entry_kind") != "directory"
            or tuple(root_row["identity"]) != tuple(root["source_identity"])
            or tuple(root_row["expected_parent_identity"])
            != tuple(root["expected_parent_identity"])
        ):
            raise ValueError("runtime_no_commit_cleanup_root_rows_invalid")
    for row in entries:
        relative = str(row["relative_path"])
        if relative == ".":
            continue
        parent_relative = (
            relative.rsplit("/", 1)[0] if "/" in relative else "."
        )
        parent_row = row_by_key.get(
            (str(row["root_role"]), parent_relative)
        )
        if (
            not isinstance(parent_row, Mapping)
            or parent_row.get("entry_kind") != "directory"
            or tuple(row["expected_parent_identity"])
            != tuple(parent_row["identity"])
        ):
            raise ValueError("runtime_no_commit_cleanup_parent_graph_invalid")

    current = entries[cursor]
    if not isinstance(current, Mapping):
        raise ValueError("runtime_no_commit_cleanup_entry_invalid")
    current_role = str(current["root_role"])
    root = root_by_role.get(current_role)
    if root is None:
        raise ValueError("runtime_no_commit_cleanup_entry_root_invalid")
    root_path = Path(str(root["source_path"]))
    current_path = (
        root_path
        if current["relative_path"] == "."
        else root_path / str(current["relative_path"])
    )

    expected_present: dict[Path, Mapping[str, Any]] = {}
    for index, row in enumerate(entries):
        if not isinstance(row, Mapping):
            raise ValueError("runtime_no_commit_cleanup_entry_invalid")
        row_root = root_by_role[str(row["root_role"])]
        base = Path(str(row_root["source_path"]))
        path = base if row["relative_path"] == "." else base / str(row["relative_path"])
        if index >= cursor:
            expected_present[path] = row
        elif path_lexists(path):
            raise ValueError("runtime_no_commit_cleanup_prior_entry_present")

    actual: set[Path] = set()
    bound = len(entries) + len(roots)
    for root_value in roots:
        base = Path(str(root_value["source_path"]))
        if not path_lexists(base):
            continue
        pending = [base]
        while pending:
            directory = pending.pop()
            actual.add(directory)
            if len(actual) > bound:
                raise ValueError("runtime_no_commit_cleanup_surface_invalid")
            with os.scandir(directory) as iterator:
                for entry in iterator:
                    path = Path(entry.path)
                    actual.add(path)
                    if len(actual) > bound:
                        raise ValueError("runtime_no_commit_cleanup_surface_invalid")
                    status = path.lstat()
                    if status_is_reparse(status):
                        raise ValueError("runtime_no_commit_cleanup_surface_invalid")
                    if stat.S_ISDIR(status.st_mode):
                        pending.append(path)
                    elif not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
                        raise ValueError("runtime_no_commit_cleanup_surface_invalid")
    current_absent = not path_lexists(current_path)
    allowed = set(expected_present)
    if allow_current_absent and current_absent:
        allowed.discard(current_path)
    if actual != allowed:
        raise ValueError("runtime_no_commit_cleanup_surface_invalid")

    for path, row in expected_present.items():
        if path == current_path and current_absent:
            continue
        status = path.lstat()
        identity = path_identity_from_status(status)
        if (
            identity != tuple(row["identity"])
            or path_identity(path.parent)
            != tuple(row["expected_parent_identity"])
        ):
            raise ValueError("runtime_no_commit_cleanup_entry_changed")
        if row["entry_kind"] == "file":
            raw, read_identity = _read_exact_runtime_external_file(
                path,
                expected_parent_identity=tuple(row["expected_parent_identity"]),
                maximum_size=int(row["size"]),
            )
            if (
                read_identity != identity
                or len(raw) != row["size"]
                or "sha256:" + hashlib.sha256(raw).hexdigest() != row["sha256"]
            ):
                raise ValueError("runtime_no_commit_cleanup_entry_changed")
        else:
            require_plain_directory(path)
            if os.name == "nt":
                require_no_alternate_data_streams(
                    path,
                    expected_identity=identity,
                    expected_parent_identity=tuple(row["expected_parent_identity"]),
                    directory=True,
                )
    roots_absent = all(
        not path_lexists(Path(str(root["source_path"]))) for root in roots
    )
    return current_path, current, current_absent, roots_absent


def _validate_no_commit_cleanup_physical_surface(
    *,
    persisted: LiveStartSession,
    lease_pair: ControllerApplyLeasePair,
    resolution: Mapping[str, Any],
    inventory: TerminalResolutionCleanupInventory,
    cursor: int,
    require_current_absent: bool,
) -> tuple[Path, Mapping[str, Any], bool, bool]:
    for family in (
        "attempt_record",
        "journal",
        "target_owner_journal",
    ):
        if any(
            resolution.get(f"successor_{family}_{suffix}") is not None
            for suffix in ("path", "identity", "sha256")
        ):
            raise ValueError("runtime_no_commit_cleanup_successor_invalid")

    def predecessor_triplet(
        family: str,
        *,
        required: bool,
    ) -> tuple[Path, PathIdentity, str] | None:
        values = (
            resolution.get(f"predecessor_{family}_path"),
            resolution.get(f"predecessor_{family}_identity"),
            resolution.get(f"predecessor_{family}_sha256"),
        )
        if all(value is None for value in values) and not required:
            return None
        if any(value is None for value in values):
            raise ValueError("runtime_no_commit_cleanup_triplet_invalid")
        return Path(str(values[0])), tuple(values[1]), str(values[2])

    attempt_triplet = predecessor_triplet("attempt_record", required=True)
    journal_triplet = predecessor_triplet("journal", required=True)
    owner_triplet = predecessor_triplet(
        "target_owner_journal", required=False
    )
    assert attempt_triplet is not None and journal_triplet is not None
    attempt_path, expected_attempt_identity, expected_attempt_sha256 = (
        attempt_triplet
    )
    journal_path, expected_journal_identity, expected_journal_sha256 = (
        journal_triplet
    )
    inventory_path = Path(str(resolution["cleanup_inventory_path"]))
    inventory_parent_identity = tuple(
        resolution["cleanup_inventory_parent_identity"]
    )
    raw, inventory_identity = _read_exact_runtime_external_file(
        inventory_path,
        expected_parent_identity=inventory_parent_identity,
        maximum_size=int(resolution["cleanup_inventory_size"]),
    )
    staging_path = inventory_path.with_name(f"{inventory_path.name}.staged")
    inner_path = staging_path.with_name(
        f".{staging_path.name}.live-start-atomic.tmp"
    )
    binding = _authenticate_controller_apply_pair_binding(lease_pair)
    if (
        inventory_path
        != binding.session_root / "terminal-resolution-cleanup.json"
        or inventory_parent_identity != binding.session_root_identity
        or type(binding.runtime_admission)
        is not RuntimeLiveAttemptAdmissionEvidence
    ):
        raise ValueError("runtime_no_commit_cleanup_sidecar_path_changed")
    assert isinstance(
        binding.runtime_admission, RuntimeLiveAttemptAdmissionEvidence
    )
    if (
        inventory_identity != tuple(resolution["cleanup_inventory_identity"])
        or raw != inventory.canonical_json
        or len(raw) != resolution["cleanup_inventory_size"]
        or "sha256:" + hashlib.sha256(raw).hexdigest()
        != resolution["cleanup_inventory_sha256"]
        or path_lexists(staging_path)
        or path_lexists(inner_path)
    ):
        raise ValueError("runtime_no_commit_cleanup_sidecar_changed")
    layout_identities = _validated_complete_layout_successor_identities(
        layout=persisted.runtime_layout_bootstrap,
        runtime_root=lease_pair.runtime_lease.runtime_root,
    )
    attempt_raw, attempt_identity = _read_exact_runtime_external_file(
        attempt_path,
        expected_parent_identity=layout_identities["attempt_retention"],
        maximum_size=RUNTIME_ATTEMPT_RETENTION_MAX_BYTES,
    )
    if (
        attempt_identity != expected_attempt_identity
        or "sha256:" + hashlib.sha256(attempt_raw).hexdigest()
        != expected_attempt_sha256
    ):
        raise ValueError("runtime_no_commit_cleanup_fence_changed")
    record = _runtime_attempt_retention_from_raw(
        attempt_raw,
        runtime_root=lease_pair.runtime_lease.runtime_root,
    )
    journal_raw, journal_identity = _read_exact_runtime_external_file(
        journal_path,
        expected_parent_identity=layout_identities["transactions"],
        maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
    )
    if (
        journal_identity != expected_journal_identity
        or "sha256:" + hashlib.sha256(journal_raw).hexdigest()
        != expected_journal_sha256
    ):
        raise ValueError("runtime_no_commit_cleanup_journal_changed")
    journal = parse_runtime_transaction_journal_bytes(
        journal_raw,
        expected_transaction_id=str(resolution["apply_attempt_id"]),
    )
    ini_path = lease_pair.runtime_lease.runtime_root / "CustomConfig" / "deck_config.ini"
    if path_identity(ini_path.parent) != layout_identities["custom_config"]:
        raise ValueError("runtime_no_commit_cleanup_ini_parent_changed")
    ini = read_deck_config(ini_path, deck_name=journal.deck_name)
    if ini.sha256 != journal.previous_ini_sha256:
        raise ValueError("runtime_no_commit_cleanup_ini_changed")

    delta: apply_invocation_module.ValidatedSameAttemptJournalDelta | None = None
    try:
        delta, sealed_snapshot, current_snapshot = (
            _validate_same_attempt_journal_delta_with_snapshot(
                lease_pair=lease_pair,
                runtime_admission=binding.runtime_admission,
                apply_attempt_id=str(resolution["apply_attempt_id"]),
                expected_attempt_record_path=attempt_path,
                expected_attempt_record_identity=expected_attempt_identity,
                expected_attempt_record_sha256=expected_attempt_sha256,
                expected_journal_path=journal_path,
                expected_journal_identity=expected_journal_identity,
                expected_journal_sha256=expected_journal_sha256,
                expected_journal_phase=journal.phase.name,
                recovery_cursor=resolution,
            )
        )
        apply_invocation_module.require_same_attempt_pre_apply_snapshot(
            sealed=sealed_snapshot,
            current=current_snapshot,
            apply_attempt_id=str(resolution["apply_attempt_id"]),
            validated_delta=delta,
        )
    finally:
        if delta is not None:
            apply_invocation_module._retire_validated_same_attempt_journal_delta(
                validated_delta=delta,
                pair_authority=lease_pair.pair_token,
                runtime_admission=binding.runtime_admission,
            )

    deterministic_candidate = (
        lease_pair.runtime_lease.runtime_root
        / ".hsconfig"
        / "staging"
        / str(resolution["apply_attempt_id"])
    )
    deterministic_journal = runtime_transaction_journal_path(
        lease_pair.runtime_lease.runtime_root,
        str(resolution["apply_attempt_id"]),
    )
    retirement = persisted.terminal_retirement
    result_intent = persisted.result_intent
    if not isinstance(retirement, Mapping) or not isinstance(
        result_intent, Mapping
    ):
        raise ValueError("runtime_no_commit_cleanup_session_evidence_invalid")
    for evidence in (retirement, result_intent):
        retained_owner = (
            evidence.get("retained_target_owner_journal_path"),
            evidence.get("retained_target_owner_journal_identity"),
            evidence.get("retained_target_owner_journal_sha256"),
        )
        expected_owner = (
            (None, None, None)
            if owner_triplet is None
            else (
                str(owner_triplet[0]),
                owner_triplet[1],
                owner_triplet[2],
            )
        )
        if (
            evidence.get("retained_attempt_record_path") != str(attempt_path)
            or tuple(evidence.get("retained_attempt_record_identity", ()))
            != expected_attempt_identity
            or evidence.get("retained_attempt_record_sha256")
            != expected_attempt_sha256
            or evidence.get("retained_journal_path") != str(journal_path)
            or tuple(evidence.get("retained_journal_identity", ()))
            != expected_journal_identity
            or evidence.get("retained_journal_sha256")
            != expected_journal_sha256
            or retained_owner[0] != expected_owner[0]
            or (
                tuple(retained_owner[1])
                if retained_owner[1] is not None
                else None
            )
            != expected_owner[1]
            or retained_owner[2] != expected_owner[2]
        ):
            raise ValueError(
                "runtime_no_commit_cleanup_session_evidence_changed"
            )
    planned_record = record.state == "CANDIDATE_PLANNED"
    bound_record = record.state == "CANDIDATE_BOUND"
    record_journal_projection_valid = (
        planned_record
        and journal.phase == RuntimeTransactionPhase.PREPARED
        and record.journal_path is None
        and record.journal_identity is None
        and record.journal_sha256 is None
        and record.planned_journal_path == deterministic_journal
        and record.planned_journal_size == len(journal_raw)
        and record.planned_journal_sha256 == expected_journal_sha256
    ) or (bound_record and record.journal_path == deterministic_journal)
    if (
        not (planned_record or bound_record)
        or record.apply_attempt_id != resolution.get("apply_attempt_id")
        or record.retention_owner_run_id != resolution.get("run_id")
        or record.package_root_sha256
        != "sha256:" + journal.package_root_sha256
        or binding.runtime_admission.package_root_sha256
        != resolution.get("package_root_sha256")
        or journal.deck_name != persisted.deck_name
        or not record_journal_projection_valid
        or journal_path != deterministic_journal
        or record.candidate_path != deterministic_candidate
        or resolution.get("candidate_path") != str(deterministic_candidate)
        or tuple(resolution.get("candidate_parent_identity", ()))
        != layout_identities["staging"]
        or lease_pair.runtime_lease.runtime_root / journal.candidate_path
        != deterministic_candidate
        or record.candidate_parent_identity != layout_identities["staging"]
        or record.target_owner_journal_path is not None
        or resolution.get("predecessor_target_owner_journal_path") is not None
        or journal.owns_target
        or (
            journal.phase == RuntimeTransactionPhase.PREPARED
            and journal.candidate_identity is not None
        )
        or (
            journal.phase
            in {
                RuntimeTransactionPhase.RUNTIME_STAGED,
                RuntimeTransactionPhase.RUNTIME_VERIFIED,
            }
            and journal.candidate_identity != record.candidate_identity
        )
        or journal.phase
        not in {
            RuntimeTransactionPhase.PREPARED,
            RuntimeTransactionPhase.RUNTIME_STAGED,
            RuntimeTransactionPhase.RUNTIME_VERIFIED,
        }
    ):
        raise ValueError("runtime_no_commit_cleanup_authority_changed")
    if (
        bound_record
        and resolution.get("predecessor_candidate_identity")
        != record.candidate_identity
    ):
        raise ValueError("runtime_no_commit_cleanup_candidate_changed")

    current_path, current, was_absent, roots_absent = (
        _validate_no_commit_cleanup_projection(
            inventory=inventory,
            cursor=cursor,
            allow_current_absent=True,
        )
    )
    if require_current_absent and not was_absent:
        raise ValueError("runtime_no_commit_cleanup_delete_failed")
    roots = inventory.value["cleanup_roots"]
    for root in roots:
        role = root["root_role"]
        expected_path = (
            record.candidate_path
            if role == "candidate"
            else lease_pair.runtime_lease.runtime_root / journal.target_path
        )
        expected_identity = (
            tuple(root["source_identity"])
            if role == "candidate" and planned_record
            else tuple(resolution["predecessor_candidate_identity"])
            if role == "candidate"
            else tuple(root["source_identity"])
        )
        expected_parent_identity = (
            record.candidate_parent_identity
            if role == "candidate"
            else layout_identities["custom_config"]
        )
        opposite_path = (
            lease_pair.runtime_lease.runtime_root / journal.target_path
            if role == "candidate"
            else deterministic_candidate
        )
        if (
            expected_path != Path(str(root["source_path"]))
            or expected_identity != tuple(root["source_identity"])
            or (
                role == "candidate"
                and planned_record
                and resolution.get("predecessor_candidate_identity")
                != expected_identity
            )
            or expected_parent_identity
            != tuple(root["expected_parent_identity"])
            or (
                role == "target"
                and (
                    not bound_record
                    or journal.phase
                    != RuntimeTransactionPhase.RUNTIME_VERIFIED
                    or record.candidate_identity != expected_identity
                    or journal.candidate_identity != expected_identity
                    or resolution.get("predecessor_candidate_identity")
                    != expected_identity
                )
            )
            or path_lexists(opposite_path)
        ):
            raise ValueError("runtime_no_commit_cleanup_root_changed")
    return current_path, current, was_absent, roots_absent


def delete_runtime_no_commit_entry_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    terminal_authorization: TerminalRetirementAuthorization,
    inventory: TerminalResolutionCleanupInventory,
    expected_cursor: int,
) -> RuntimeNoCommitCleanupStep:
    """Delete or confirm exactly one sealed no-commit inventory row."""

    if (
        type(inventory) is not TerminalResolutionCleanupInventory
        or type(expected_cursor) is not int
        or expected_cursor < 0
        or type(terminal_authorization) is not TerminalRetirementAuthorization
    ):
        raise ValueError("runtime_no_commit_cleanup_arguments_invalid")
    binding = _authenticate_controller_apply_pair_binding(lease_pair)
    expected_session = binding.expected_session
    _require_terminal_physical_authorization_context(
        session_lease=binding.session_lease,
        expected_session=expected_session,
        terminal_authorization=terminal_authorization,
        action="delete_cleanup_entry",
    )
    roots_absent = False
    was_absent = False

    def perform() -> TerminalResolutionPhysicalPostcondition:
        nonlocal roots_absent, was_absent
        active = _require_active_controller_apply_pair(lease_pair)
        persisted = load_live_start_session_under_lock(
            session_lease=active.session_lease
        )
        if (
            persisted != expected_session
            or persisted.canonical_json != expected_session.canonical_json
            or persisted.session_identity != expected_session.session_identity
        ):
            raise ValueError("runtime_no_commit_cleanup_session_changed")
        retirement = persisted.terminal_retirement
        if (
            not isinstance(retirement, Mapping)
            or retirement.get("operation") != "release_resolved_terminal"
            or retirement.get("stage") != "RECOVERY_CLEANING"
        ):
            raise ValueError("runtime_no_commit_cleanup_cursor_invalid")
        resolution = retirement.get("terminal_resolution_evidence")
        commitment_checks = {
            "resolution": isinstance(resolution, Mapping),
            "stage": isinstance(resolution, Mapping)
            and resolution.get("cleanup_stage") == "CLEANING",
            "disposition": isinstance(resolution, Mapping)
            and resolution.get("resolved_physical_disposition")
            == "NOT_COMMITTED",
            "external": isinstance(resolution, Mapping)
            and resolution.get("external_file_action") is None,
            "cursor": isinstance(resolution, Mapping)
            and resolution.get("cleanup_cursor") == expected_cursor,
            "count": isinstance(resolution, Mapping)
            and resolution.get("cleanup_entry_count")
            == inventory.value.get("cleanup_entry_count"),
            "manifest": isinstance(resolution, Mapping)
            and resolution.get("cleanup_manifest_sha256")
            == inventory.value.get("cleanup_manifest_sha256"),
            "roots": isinstance(resolution, Mapping)
            and _plain_json_value(resolution.get("cleanup_roots"))
            == _plain_json_value(inventory.value.get("cleanup_roots")),
            "run": isinstance(resolution, Mapping)
            and inventory.value.get("run_id") == resolution.get("run_id"),
            "attempt": isinstance(resolution, Mapping)
            and inventory.value.get("apply_attempt_id")
            == resolution.get("apply_attempt_id"),
            "root_path": inventory.value.get("runtime_root_path")
            == str(lease_pair.runtime_lease.runtime_root),
            "root_identity": tuple(
                inventory.value.get("runtime_root_identity", ())
            )
            == lease_pair.runtime_lease.runtime_root_identity,
        }
        if not all(commitment_checks.values()):
            failed = ",".join(
                key for key, valid in commitment_checks.items() if not valid
            )
            raise ValueError(
                f"runtime_no_commit_cleanup_commitment_mismatch:{failed}"
            )
        assert isinstance(resolution, Mapping)
        current_path, current, was_absent, _ = (
            _validate_no_commit_cleanup_physical_surface(
                persisted=persisted,
                lease_pair=lease_pair,
                resolution=resolution,
                inventory=inventory,
                cursor=expected_cursor,
                require_current_absent=False,
            )
        )
        if not was_absent:
            try:
                if current["entry_kind"] == "file":
                    secure_unlink_verified(
                        current_path,
                        expected_identity=tuple(current["identity"]),
                        expected_parent_identity=tuple(
                            current["expected_parent_identity"]
                        ),
                        expected_size=int(current["size"]),
                        expected_sha256=str(current["sha256"])[7:],
                    )
                else:
                    secure_rmdir_verified(
                        current_path,
                        expected_identity=tuple(current["identity"]),
                        expected_parent_identity=tuple(
                            current["expected_parent_identity"]
                        ),
                    )
            except ValueError as error:
                raise ValueError("runtime_no_commit_cleanup_entry_changed") from error
        _, _, _, roots_absent = _validate_no_commit_cleanup_physical_surface(
            persisted=persisted,
            lease_pair=lease_pair,
            resolution=resolution,
            inventory=inventory,
            cursor=expected_cursor,
            require_current_absent=True,
        )
        post_active = _require_active_controller_apply_pair(lease_pair)
        post_persisted = load_live_start_session_under_lock(
            session_lease=post_active.session_lease
        )
        if (
            post_persisted != persisted
            or post_persisted.canonical_json != persisted.canonical_json
            or post_persisted.session_identity != persisted.session_identity
        ):
            raise ValueError("runtime_no_commit_cleanup_session_changed")
        successor_resolution = _plain_json_value(resolution)
        successor_retirement = _plain_json_value(retirement)
        successor_resolution.pop("content_sha256", None)
        successor_retirement.pop("content_sha256", None)
        successor_resolution["cleanup_cursor"] = expected_cursor + 1
        successor_retirement["terminal_resolution_evidence"] = _plain_json_value(
            TerminalResolutionEvidence(
                _seal_terminal_resolution(successor_resolution)
            ).value
        )
        successor = seal_embedded_document(
            "terminal_retirement", successor_retirement
        )
        return TerminalResolutionPhysicalPostcondition(
            action="delete_cleanup_entry",
            evidence={"terminal_retirement": successor},
        )

    receipt = _execute_terminal_resolution_physical_step(
        terminal_authorization=terminal_authorization,
        action="delete_cleanup_entry",
        physical_action=perform,
    )
    return RuntimeNoCommitCleanupStep(
        next_cursor=expected_cursor + 1,
        current_entry_was_already_absent=was_absent,
        cleanup_roots_absent=roots_absent,
        step_receipt=receipt,
    )


def _no_commit_metadata_triplet(
    resolution: Mapping[str, Any],
    prefix: str,
    *,
    required: bool,
) -> tuple[Path, PathIdentity, str] | None:
    values = (
        resolution.get(f"{prefix}_path"),
        resolution.get(f"{prefix}_identity"),
        resolution.get(f"{prefix}_sha256"),
    )
    if all(value is None for value in values) and not required:
        return None
    if (
        any(value is None for value in values)
        or not isinstance(values[2], str)
        or _PREFIXED_SHA256.fullmatch(values[2]) is None
    ):
        raise ValueError("runtime_no_commit_metadata_commitment_invalid")
    return Path(str(values[0])), tuple(values[1]), str(values[2])


def _validate_no_commit_metadata_surface(
    *,
    lease_pair: ControllerApplyLeasePair,
    persisted: LiveStartSession,
    retirement: Mapping[str, Any],
    resolution: Mapping[str, Any],
    action: Literal["journal", "fence"],
    require_action_complete: bool,
    baseline: _RuntimeNoCommitMetadataSurface | None,
) -> _RuntimeNoCommitMetadataSurface:
    """Validate every immutable no-commit authority around one metadata row."""

    binding = _authenticate_controller_apply_pair_binding(lease_pair)
    runtime_admission = binding.runtime_admission
    result_intent = persisted.result_intent
    if (
        type(runtime_admission) is not RuntimeLiveAttemptAdmissionEvidence
        or not isinstance(result_intent, Mapping)
        or retirement.get("terminal_resolution_evidence") != resolution
        or resolution.get("run_id") != runtime_admission.run_id
        or resolution.get("apply_attempt_id")
        != runtime_admission.apply_attempt_id
        or resolution.get("package_root_sha256")
        != runtime_admission.package_root_sha256
        or resolution.get("resolved_physical_disposition") != "NOT_COMMITTED"
        or resolution.get("external_file_action") is not None
        or resolution.get("owner_retirement") is not None
    ):
        raise ValueError("runtime_no_commit_metadata_authority_changed")

    for resolution_prefix, retained_prefix in (
        ("predecessor_attempt_record", "retained_attempt_record"),
        ("predecessor_journal", "retained_journal"),
        (
            "predecessor_target_owner_journal",
            "retained_target_owner_journal",
        ),
    ):
        for suffix in ("path", "identity", "sha256"):
            expected = resolution.get(f"{resolution_prefix}_{suffix}")
            if (
                retirement.get(f"{retained_prefix}_{suffix}") != expected
                or result_intent.get(f"{retained_prefix}_{suffix}")
                != expected
            ):
                raise ValueError(
                    "runtime_no_commit_metadata_session_evidence_changed"
                )

    prohibited_fields = {
        "allowed_attempt_record_successor_state",
        "allowed_journal_successor_phase",
        "external_file_action",
        "owner_retirement",
        "successor_candidate_identity",
        "planned_journal_successor_path",
        "planned_journal_successor_parent_identity",
        "planned_journal_successor_phase",
        "planned_journal_successor_size",
        "planned_journal_successor_sha256",
    }
    for prefix in (
        "successor_attempt_record",
        "successor_journal",
        "successor_target_owner_journal",
    ):
        prohibited_fields.update(
            f"{prefix}_{suffix}" for suffix in ("path", "identity", "sha256")
        )
    for prefix in ("predecessor_transaction_temp", "successor_transaction_temp"):
        prohibited_fields.update(
            f"{prefix}_{suffix}"
            for suffix in (
                "path",
                "parent_identity",
                "identity",
                "size",
                "sha256",
                "classification",
                "origin",
            )
        )
    if any(resolution.get(field_name) is not None for field_name in prohibited_fields):
        raise ValueError("runtime_no_commit_metadata_successor_invalid")

    layout_identities = _validated_complete_layout_successor_identities(
        layout=persisted.runtime_layout_bootstrap,
        runtime_root=lease_pair.runtime_lease.runtime_root,
    )
    runtime_root = lease_pair.runtime_lease.runtime_root
    attempt_id = str(resolution["apply_attempt_id"])
    attempt_triplet = _no_commit_metadata_triplet(
        resolution,
        "predecessor_attempt_record",
        required=True,
    )
    journal_triplet = _no_commit_metadata_triplet(
        resolution,
        "predecessor_journal",
        required=False,
    )
    owner_triplet = _no_commit_metadata_triplet(
        resolution,
        "predecessor_target_owner_journal",
        required=False,
    )
    assert attempt_triplet is not None
    attempt_path, expected_attempt_identity, expected_attempt_sha256 = (
        attempt_triplet
    )
    deterministic_attempt = _runtime_attempt_retention_path(
        runtime_root,
        attempt_id,
    )
    deterministic_journal = runtime_transaction_journal_path(
        runtime_root,
        attempt_id,
    )
    if attempt_path != deterministic_attempt:
        raise ValueError("runtime_no_commit_metadata_commitment_invalid")

    attempt_raw: bytes | None = None
    attempt_identity: PathIdentity | None = None
    record: RuntimeAttemptRetentionRecord | None = None
    attempt_exists = path_lexists(attempt_path)
    if action == "journal" and not attempt_exists:
        raise ValueError("runtime_no_commit_metadata_fence_changed")
    if require_action_complete and action == "fence" and attempt_exists:
        raise ValueError("runtime_no_commit_metadata_delete_failed")
    if attempt_exists:
        attempt_raw, attempt_identity = _read_exact_runtime_external_file(
            attempt_path,
            expected_parent_identity=layout_identities["attempt_retention"],
            maximum_size=RUNTIME_ATTEMPT_RETENTION_MAX_BYTES,
        )
        if (
            attempt_identity != expected_attempt_identity
            or "sha256:" + hashlib.sha256(attempt_raw).hexdigest()
            != expected_attempt_sha256
        ):
            raise ValueError("runtime_no_commit_metadata_fence_changed")
        record = _runtime_attempt_retention_from_raw(
            attempt_raw,
            runtime_root=runtime_root,
        )
    elif path_identity(attempt_path.parent) != layout_identities["attempt_retention"]:
        raise ValueError("runtime_no_commit_metadata_parent_changed")

    journal_path = (
        journal_triplet[0] if journal_triplet is not None else deterministic_journal
    )
    if journal_path != deterministic_journal:
        raise ValueError("runtime_no_commit_metadata_commitment_invalid")
    journal_raw: bytes | None = None
    journal_identity: PathIdentity | None = None
    journal: RuntimeTransactionJournal | None = None
    journal_exists = path_lexists(journal_path)
    if action == "fence" and journal_exists:
        raise ValueError("runtime_no_commit_metadata_order_invalid")
    if require_action_complete and action == "journal" and journal_exists:
        raise ValueError("runtime_no_commit_metadata_delete_failed")
    if journal_exists:
        if journal_triplet is None:
            raise ValueError("runtime_no_commit_metadata_journal_changed")
        journal_raw, journal_identity = _read_exact_runtime_external_file(
            journal_path,
            expected_parent_identity=layout_identities["transactions"],
            maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
        )
        if (
            journal_identity != journal_triplet[1]
            or "sha256:" + hashlib.sha256(journal_raw).hexdigest()
            != journal_triplet[2]
        ):
            raise ValueError("runtime_no_commit_metadata_journal_changed")
        journal = parse_runtime_transaction_journal_bytes(
            journal_raw,
            expected_transaction_id=attempt_id,
        )
    elif path_identity(journal_path.parent) != layout_identities["transactions"]:
        raise ValueError("runtime_no_commit_metadata_parent_changed")

    tree_bearing = resolution.get("cleanup_stage") is not None
    inventory_path: Path | None = None
    inventory_identity: PathIdentity | None = None
    inventory_raw: bytes | None = None
    if tree_bearing:
        count = resolution.get("cleanup_entry_count")
        roots = resolution.get("cleanup_roots")
        inventory_path = Path(str(resolution.get("cleanup_inventory_path")))
        inventory_parent_identity = tuple(
            resolution.get("cleanup_inventory_parent_identity", ())
        )
        if (
            type(count) is not int
            or count < 1
            or resolution.get("cleanup_cursor") != count
            or not isinstance(roots, (list, tuple))
            or inventory_path
            != binding.session_root / "terminal-resolution-cleanup.json"
            or inventory_parent_identity != binding.session_root_identity
        ):
            raise ValueError("runtime_no_commit_metadata_sidecar_changed")
        inventory_size = resolution.get("cleanup_inventory_size")
        inventory_sha256 = resolution.get("cleanup_inventory_sha256")
        if type(inventory_size) is not int or inventory_size < 1:
            raise ValueError("runtime_no_commit_metadata_sidecar_changed")
        inventory_raw, inventory_identity = _read_exact_runtime_external_file(
            inventory_path,
            expected_parent_identity=inventory_parent_identity,
            maximum_size=inventory_size,
        )
        try:
            inventory_value = json.loads(
                inventory_raw.decode("utf-8"),
                object_pairs_hook=_runtime_attempt_unique_object,
                parse_constant=_reject_runtime_attempt_constant,
            )
            inventory = TerminalResolutionCleanupInventory(inventory_value)
        except Exception as error:
            raise ValueError(
                "runtime_no_commit_metadata_sidecar_changed"
            ) from error
        staging_path = inventory_path.with_name(f"{inventory_path.name}.staged")
        inner_path = staging_path.with_name(
            f".{staging_path.name}.live-start-atomic.tmp"
        )
        if (
            inventory_identity
            != tuple(resolution.get("cleanup_inventory_identity", ()))
            or len(inventory_raw) != inventory_size
            or inventory_raw != inventory.canonical_json
            or "sha256:" + hashlib.sha256(inventory_raw).hexdigest()
            != inventory_sha256
            or inventory.value.get("cleanup_entry_count") != count
            or inventory.value.get("cleanup_manifest_sha256")
            != resolution.get("cleanup_manifest_sha256")
            or _plain_json_value(inventory.value.get("cleanup_roots"))
            != _plain_json_value(roots)
            or path_lexists(staging_path)
            or path_lexists(inner_path)
            or path_identity(staging_path.parent) != binding.session_root_identity
        ):
            raise ValueError("runtime_no_commit_metadata_sidecar_changed")
        for root in roots:
            if (
                not isinstance(root, Mapping)
                or path_lexists(Path(str(root.get("source_path"))))
                or path_identity(Path(str(root.get("source_path"))).parent)
                != tuple(root.get("expected_parent_identity", ()))
            ):
                raise ValueError("runtime_no_commit_metadata_cleanup_root_changed")
    else:
        cleanup_fields = (
            "cleanup_inventory_path",
            "cleanup_inventory_parent_identity",
            "cleanup_inventory_identity",
            "cleanup_inventory_size",
            "cleanup_inventory_sha256",
            "cleanup_manifest_sha256",
            "cleanup_entry_count",
            "cleanup_cursor",
            "cleanup_roots",
        )
        if any(resolution.get(name) is not None for name in cleanup_fields):
            raise ValueError("runtime_no_commit_metadata_cleanup_invalid")
        inventory_path = binding.session_root / "terminal-resolution-cleanup.json"
        staging_path = inventory_path.with_name(f"{inventory_path.name}.staged")
        inner_path = staging_path.with_name(
            f".{staging_path.name}.live-start-atomic.tmp"
        )
        if (
            path_lexists(inventory_path)
            or path_lexists(staging_path)
            or path_lexists(inner_path)
            or path_identity(inventory_path.parent) != binding.session_root_identity
        ):
            raise ValueError("runtime_no_commit_metadata_sidecar_changed")
        inventory_path = None

    if record is not None:
        if record.state == "ACTIVE":
            active_metadata = (
                record.journal_path,
                record.journal_identity,
                record.journal_sha256,
                record.package_root_sha256,
                record.target_path,
                record.target_identity,
                record.owns_target,
                record.target_owner_journal_path,
                record.target_owner_journal_identity,
                record.target_owner_journal_sha256,
                record.planned_journal_path,
                record.planned_journal_size,
                record.planned_journal_sha256,
                record.candidate_path,
                record.candidate_parent_identity,
                record.candidate_identity,
            )
            if (
                tree_bearing
                or record.apply_attempt_id != attempt_id
                or record.retention_owner_run_id != resolution.get("run_id")
                or any(value is not None for value in active_metadata)
                or journal_triplet is not None
                or owner_triplet is not None
                or resolution.get("candidate_path") is not None
                or resolution.get("candidate_parent_identity") is not None
                or resolution.get("predecessor_candidate_identity") is not None
            ):
                raise ValueError(
                    "runtime_no_commit_metadata_authority_changed"
                )
        else:
            planned = (
                record.planned_journal_path,
                record.planned_journal_size,
                record.planned_journal_sha256,
            )
            allowed_states = (
                {"CANDIDATE_PLANNED", "CANDIDATE_BOUND"}
                if tree_bearing
                else {
                    "CANDIDATE_PLANNED",
                    "PRIOR_OWNER_PLANNED",
                    "PRIOR_OWNER_BOUND",
                }
            )
            if (
                record.state not in allowed_states
                or record.apply_attempt_id != attempt_id
                or record.retention_owner_run_id != resolution.get("run_id")
                or record.owns_target is not False
                or planned[0] != deterministic_journal
                or type(planned[1]) is not int
                or planned[1] < 1
                or not isinstance(planned[2], str)
                or _PREFIXED_SHA256.fullmatch(planned[2]) is None
            ):
                raise ValueError(
                    "runtime_no_commit_metadata_authority_changed"
                )
            if journal is not None:
                planned_state = record.state.endswith("_PLANNED")
                if (
                    record.package_root_sha256
                    != "sha256:" + journal.package_root_sha256
                    or journal.deck_name != persisted.deck_name
                    or journal.owns_target
                    or (
                        planned_state
                        and (
                            journal.phase != RuntimeTransactionPhase.PREPARED
                            or record.journal_path is not None
                            or record.journal_identity is not None
                            or record.journal_sha256 is not None
                            or planned[1] != len(journal_raw or b"")
                            or planned[2] != journal_triplet[2]
                        )
                    )
                    or (
                        not planned_state
                        and record.journal_path != deterministic_journal
                    )
                ):
                    raise ValueError(
                        "runtime_no_commit_metadata_authority_changed"
                    )

    candidate_path_value = resolution.get("candidate_path")
    candidate_parent_value = resolution.get("candidate_parent_identity")
    if not tree_bearing and candidate_path_value is not None:
        candidate_path = Path(str(candidate_path_value))
        if (
            candidate_path
            != runtime_root / ".hsconfig" / "staging" / attempt_id
            or tuple(candidate_parent_value or ()) != layout_identities["staging"]
            or resolution.get("predecessor_candidate_identity") is not None
            or path_lexists(candidate_path)
            or path_identity(candidate_path.parent) != layout_identities["staging"]
            or (
                record is not None
                and (
                    record.state != "CANDIDATE_PLANNED"
                    or record.candidate_path != candidate_path
                    or record.candidate_parent_identity
                    != layout_identities["staging"]
                    or record.candidate_identity is not None
                )
            )
        ):
            raise ValueError("runtime_no_commit_metadata_candidate_changed")
    elif not tree_bearing and record is not None and record.candidate_path is not None:
        raise ValueError("runtime_no_commit_metadata_candidate_changed")

    owner_path: Path | None = None
    owner_identity: PathIdentity | None = None
    owner_raw: bytes | None = None
    target_path: Path | None = None
    target_identity: PathIdentity | None = None
    if owner_triplet is not None:
        owner_path, expected_owner_identity, expected_owner_sha256 = owner_triplet
        if owner_path != runtime_transaction_journal_path(
            runtime_root,
            owner_path.stem,
        ):
            raise ValueError("runtime_no_commit_metadata_owner_changed")
        owner_raw, owner_identity = _read_exact_runtime_external_file(
            owner_path,
            expected_parent_identity=layout_identities["transactions"],
            maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
        )
        owner = parse_runtime_transaction_journal_bytes(
            owner_raw,
            expected_transaction_id=owner_path.stem,
        )
        target_path = runtime_root / owner.target_path
        target_identity = owner.target_identity
        if (
            owner_identity != expected_owner_identity
            or "sha256:" + hashlib.sha256(owner_raw).hexdigest()
            != expected_owner_sha256
            or owner.phase != RuntimeTransactionPhase.FINALIZED
            or not owner.owns_target
            or target_identity is None
            or path_identity(target_path.parent)
            != layout_identities["custom_config"]
        ):
            raise ValueError("runtime_no_commit_metadata_owner_changed")
        _observe_retained_directory(
            target_path,
            expected_identity=target_identity,
            expected_parent_identity=layout_identities["custom_config"],
        )
        if record is not None and (
            record.target_path != target_path
            or record.target_identity != target_identity
            or record.target_owner_journal_path != owner_path
            or record.target_owner_journal_identity != owner_identity
            or record.target_owner_journal_sha256 != expected_owner_sha256
        ):
            raise ValueError("runtime_no_commit_metadata_owner_changed")
    elif record is not None and record.target_owner_journal_path is not None:
        raise ValueError("runtime_no_commit_metadata_owner_changed")
    elif journal is not None:
        target_path = runtime_root / journal.target_path
        if (
            path_lexists(target_path)
            or path_identity(target_path.parent)
            != layout_identities["custom_config"]
        ):
            raise ValueError("runtime_no_commit_metadata_target_changed")
    elif baseline is not None and baseline.target_path is not None:
        target_path = baseline.target_path
        target_identity = baseline.target_identity
        if target_identity is None:
            if (
                path_lexists(target_path)
                or path_identity(target_path.parent)
                != layout_identities["custom_config"]
            ):
                raise ValueError("runtime_no_commit_metadata_target_changed")
        else:
            _observe_retained_directory(
                target_path,
                expected_identity=target_identity,
                expected_parent_identity=layout_identities["custom_config"],
            )

    snapshot_exact = (
        _same_attempt_pre_apply_snapshot_is_exact(
            recovery=resolution,
            lease_pair=lease_pair,
            runtime_admission=runtime_admission,
            expected_journal_phase=journal.phase.name,
        )
        if journal is not None
        else _journal_less_same_attempt_pre_apply_snapshot_is_exact(
            recovery=resolution,
            lease_pair=lease_pair,
            runtime_admission=runtime_admission,
        )
    )
    if not snapshot_exact:
        raise ValueError("runtime_no_commit_metadata_snapshot_changed")

    surface = _RuntimeNoCommitMetadataSurface(
        attempt_path=attempt_path,
        attempt_identity=attempt_identity,
        attempt_raw=attempt_raw,
        record=record,
        journal_path=journal_path,
        journal_identity=journal_identity,
        journal_raw=journal_raw,
        journal=journal,
        owner_path=owner_path,
        owner_identity=owner_identity,
        owner_raw=owner_raw,
        target_path=target_path,
        target_identity=target_identity,
        inventory_path=inventory_path,
        inventory_identity=inventory_identity,
        inventory_raw=inventory_raw,
    )
    if baseline is not None:
        stable_fields = (
            "owner_path",
            "owner_identity",
            "owner_raw",
            "target_path",
            "target_identity",
            "inventory_path",
            "inventory_identity",
            "inventory_raw",
        )
        if any(
            getattr(surface, name) != getattr(baseline, name)
            for name in stable_fields
        ):
            raise ValueError("runtime_no_commit_metadata_sibling_changed")
        if action == "journal" and (
            surface.attempt_identity != baseline.attempt_identity
            or surface.attempt_raw != baseline.attempt_raw
        ):
            raise ValueError("runtime_no_commit_metadata_fence_changed")
    return surface


def retire_runtime_no_commit_metadata_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    terminal_authorization: TerminalRetirementAuthorization,
    action: Literal["journal", "fence"],
) -> RuntimeNoCommitMetadataStep:
    """Retire exactly one retained no-commit journal or fence entry."""

    if type(terminal_authorization) is not TerminalRetirementAuthorization:
        raise ValueError("runtime_no_commit_metadata_arguments_invalid")
    binding = _authenticate_controller_apply_pair_binding(lease_pair)
    expected_session = binding.expected_session
    if action not in {"journal", "fence"}:
        raise ValueError("runtime_no_commit_metadata_action_invalid")
    physical_action = f"retire_cleanup_{action}"
    if terminal_authorization._opaque.action != physical_action:
        raise ValueError("runtime_no_commit_metadata_action_invalid")
    _require_terminal_physical_authorization_context(
        session_lease=binding.session_lease,
        expected_session=expected_session,
        terminal_authorization=terminal_authorization,
        action=physical_action,
    )
    was_absent = False

    def perform() -> TerminalResolutionPhysicalPostcondition:
        nonlocal was_absent
        active = _require_active_controller_apply_pair(lease_pair)
        persisted = load_live_start_session_under_lock(
            session_lease=active.session_lease
        )
        if (
            persisted != expected_session
            or persisted.canonical_json != expected_session.canonical_json
            or persisted.session_identity != expected_session.session_identity
        ):
            raise ValueError("runtime_no_commit_metadata_session_changed")
        retirement = persisted.terminal_retirement
        if (
            not isinstance(retirement, Mapping)
            or retirement.get("operation") != "release_resolved_terminal"
        ):
            raise ValueError("runtime_no_commit_metadata_cursor_invalid")
        resolution = retirement.get("terminal_resolution_evidence")
        if (
            not isinstance(resolution, Mapping)
            or resolution.get("resolved_physical_disposition")
            != "NOT_COMMITTED"
        ):
            raise ValueError("runtime_no_commit_metadata_cursor_invalid")
        outer_stage = retirement.get("stage")
        cleanup_stage = resolution.get("cleanup_stage")
        cleanup_count = resolution.get("cleanup_entry_count")
        cleanup_cursor = resolution.get("cleanup_cursor")
        tree_bearing = cleanup_stage is not None
        if tree_bearing:
            if action == "journal":
                ordered = (
                    outer_stage == "RECOVERY_CLEANING"
                    and cleanup_stage == "CLEANING"
                    and type(cleanup_count) is int
                    and cleanup_count > 0
                    and cleanup_cursor == cleanup_count
                )
            else:
                ordered = (
                    outer_stage == "RECOVERY_JOURNAL_RETIRED"
                    and cleanup_stage == "JOURNAL_RETIRED"
                    and type(cleanup_count) is int
                    and cleanup_cursor == cleanup_count
                )
        else:
            cleanup_fields = (
                "cleanup_inventory_path",
                "cleanup_inventory_parent_identity",
                "cleanup_inventory_identity",
                "cleanup_inventory_size",
                "cleanup_inventory_sha256",
                "cleanup_manifest_sha256",
                "cleanup_entry_count",
                "cleanup_cursor",
                "cleanup_roots",
                "external_file_action",
            )
            cleanup_is_null = all(
                resolution.get(name) is None for name in cleanup_fields
            )
            if action == "journal":
                ordered = (
                    outer_stage == "RECOVERY_PREPARED"
                    and cleanup_is_null
                    and resolution.get("predecessor_journal_path")
                    is not None
                )
            else:
                journal_retained = resolution.get(
                    "predecessor_journal_path"
                ) is not None
                ordered = cleanup_is_null and (
                    (
                        outer_stage == "RECOVERY_PREPARED"
                        and not journal_retained
                    )
                    or (
                        outer_stage == "RECOVERY_JOURNAL_RETIRED"
                        and journal_retained
                    )
                )
        if not ordered:
            raise ValueError("runtime_no_commit_metadata_order_invalid")
        surface = _validate_no_commit_metadata_surface(
            lease_pair=lease_pair,
            persisted=persisted,
            retirement=retirement,
            resolution=resolution,
            action=action,
            require_action_complete=False,
            baseline=None,
        )
        layout_identities = _validated_complete_layout_successor_identities(
            layout=persisted.runtime_layout_bootstrap,
            runtime_root=lease_pair.runtime_lease.runtime_root,
        )
        path = surface.journal_path if action == "journal" else surface.attempt_path
        identity = (
            surface.journal_identity
            if action == "journal"
            else surface.attempt_identity
        )
        raw = surface.journal_raw if action == "journal" else surface.attempt_raw
        parent_identity = layout_identities[
            "transactions" if action == "journal" else "attempt_retention"
        ]
        deterministic_candidate = (
            lease_pair.runtime_lease.runtime_root
            / ".hsconfig"
            / "staging"
            / str(resolution["apply_attempt_id"])
        )
        if not tree_bearing and action == "fence":
            _require_retained_child_absent(
                deterministic_candidate,
                expected_parent_identity=layout_identities["staging"],
            )
        was_absent = raw is None
        if not was_absent:
            assert raw is not None and identity is not None
            secure_unlink_verified(
                path,
                expected_identity=identity,
                expected_parent_identity=parent_identity,
                expected_size=len(raw),
                expected_sha256=hashlib.sha256(raw).hexdigest(),
            )
        if not tree_bearing and action == "fence":
            _require_retained_child_absent(
                deterministic_candidate,
                expected_parent_identity=layout_identities["staging"],
            )
        _validate_no_commit_metadata_surface(
            lease_pair=lease_pair,
            persisted=persisted,
            retirement=retirement,
            resolution=resolution,
            action=action,
            require_action_complete=True,
            baseline=surface,
        )
        post_persisted = load_live_start_session_under_lock(
            session_lease=active.session_lease
        )
        if (
            post_persisted != persisted
            or post_persisted.canonical_json != persisted.canonical_json
            or post_persisted.session_identity != persisted.session_identity
        ):
            raise ValueError("runtime_no_commit_metadata_session_changed")
        successor = _plain_json_value(retirement)
        successor.pop("content_sha256", None)
        successor_resolution = _plain_json_value(resolution)
        successor_resolution.pop("content_sha256", None)
        if tree_bearing:
            successor_resolution["cleanup_stage"] = (
                "JOURNAL_RETIRED"
                if action == "journal"
                else "FENCE_RETIRED"
            )
            successor["terminal_resolution_evidence"] = (
                _seal_terminal_resolution(successor_resolution)
            )
        successor["stage"] = (
            "RECOVERY_JOURNAL_RETIRED"
            if action == "journal"
            else "RECOVERY_FENCE_RETIRED"
        )
        return TerminalResolutionPhysicalPostcondition(
            action=physical_action,
            evidence={
                "terminal_retirement": seal_embedded_document(
                    "terminal_retirement", successor
                )
            },
        )

    receipt = _execute_terminal_resolution_physical_step(
        terminal_authorization=terminal_authorization,
        action=physical_action,
        physical_action=perform,
    )
    return RuntimeNoCommitMetadataStep(
        action=action,
        object_was_already_absent=was_absent,
        step_receipt=receipt,
    )


def _retire_success_attempt_evidence_step_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    session_lease: LiveStartSessionLease,
    expected_retirement_session: LiveStartSession,
    terminal_authorization: TerminalRetirementAuthorization,
    transaction_id: str,
    expected_retention_owner_run_id: str,
    expected_package_root_sha256: str,
    expected_retention_fence_path: Path,
    expected_retention_fence_identity: PathIdentity,
    expected_retention_fence_sha256: str,
    expected_journal_path: Path,
    expected_journal_identity: PathIdentity,
    expected_journal_sha256: str,
    expected_target_owner_journal_path: Path,
    expected_target_owner_journal_identity: PathIdentity,
    expected_target_owner_journal_sha256: str,
    expected_target_path: Path,
    expected_target_identity: PathIdentity,
    expected_runtime_admission_path: Path,
    expected_runtime_admission_parent_identity: PathIdentity,
    expected_runtime_admission_identity: PathIdentity,
    expected_runtime_admission_sha256: str,
    action: Literal["journal", "fence"],
) -> RuntimeAttemptEvidenceRetirementStep:
    """Retire one exact successful-attempt row under a held controller pair."""

    physical_action = {
        "journal": "retire_ack_journal",
        "fence": "retire_ack_fence",
    }.get(action)
    if physical_action is None:
        raise ValueError("runtime_success_ack_action_unimplemented")
    if type(terminal_authorization) is not TerminalRetirementAuthorization:
        raise ValueError("runtime_success_ack_authorization_invalid")
    if (
        not isinstance(transaction_id, str)
        or _ATTEMPT_ID.fullmatch(transaction_id) is None
        or not isinstance(expected_retention_owner_run_id, str)
        or _ATTEMPT_ID.fullmatch(expected_retention_owner_run_id) is None
        or not isinstance(expected_package_root_sha256, str)
        or _PREFIXED_SHA256.fullmatch(expected_package_root_sha256) is None
        or any(
            not isinstance(path, Path) or not path.is_absolute()
            for path in (
                expected_retention_fence_path,
                expected_journal_path,
                expected_target_owner_journal_path,
                expected_target_path,
                expected_runtime_admission_path,
            )
        )
        or any(
            not _valid_path_identity(identity)
            for identity in (
                expected_retention_fence_identity,
                expected_journal_identity,
                expected_target_owner_journal_identity,
                expected_target_identity,
                expected_runtime_admission_parent_identity,
                expected_runtime_admission_identity,
            )
        )
        or any(
            not isinstance(digest, str)
            or _PREFIXED_SHA256.fullmatch(digest) is None
            for digest in (
                expected_retention_fence_sha256,
                expected_journal_sha256,
                expected_target_owner_journal_sha256,
                expected_runtime_admission_sha256,
            )
        )
    ):
        raise ValueError("runtime_success_ack_arguments_invalid")
    binding = _require_controller_pair_session_cursor(
        lease_pair=lease_pair,
        session_lease=session_lease,
        expected_session=expected_retirement_session,
    )
    if terminal_authorization._opaque.action != physical_action:
        raise ValueError("runtime_success_ack_action_invalid")
    _require_terminal_physical_authorization_context(
        session_lease=session_lease,
        expected_session=expected_retirement_session,
        terminal_authorization=terminal_authorization,
        action=physical_action,
    )
    was_absent = False

    def require_exact_file(
        path: Path,
        *,
        parent_identity: PathIdentity,
        expected_identity: PathIdentity,
        expected_sha256: str,
        maximum_size: int,
    ) -> tuple[bytes, PathIdentity]:
        raw, identity = _read_exact_runtime_external_file(
            path,
            expected_parent_identity=parent_identity,
            maximum_size=maximum_size,
        )
        if (
            identity != expected_identity
            or "sha256:" + hashlib.sha256(raw).hexdigest()
            != expected_sha256
        ):
            raise ValueError("runtime_success_ack_evidence_changed")
        return raw, identity

    def require_current_success_runtime_parity(
        *,
        owner: RuntimeTransactionJournal,
        layout_identities: Mapping[str, PathIdentity],
        result_intent: Mapping[str, Any],
        current_session: LiveStartSession,
        runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    ) -> None:
        """Require current owning-runtime facts before retiring its fence."""

        try:
            package_binding = _require_active_package_input_lease(
                lease_pair.package_lease
            )
            if (
                package_binding.lease.snapshot is None
                or package_binding.lease.content_root_sha256
                != expected_package_root_sha256.removeprefix("sha256:")
            ):
                raise ValueError("package")
            spec = _runtime_package_spec(
                verify_tree_manifest(package_binding.lease.snapshot)
            )
            manifest, _ = _candidate_manifest_from_pair(
                package_lease=lease_pair.package_lease,
                deck_name=current_session.deck_name,
            )
            entries = tuple(manifest["entries"])
            if (
                owner.deck_name != current_session.deck_name
                or owner.logical_config_dir != spec.logical_config_dir
                or owner.package_root_sha256 != spec.package_root_sha256
                or owner.source_manifest_sha256
                != expected_package_root_sha256.removeprefix("sha256:")
                or owner.target_path
                != expected_target_path.relative_to(
                    runtime_admission.runtime_root
                ).as_posix()
                or owner.target_identity != expected_target_identity
                or owner.next_config_dir != expected_target_path.name
            ):
                raise ValueError("owner")
            _verify_candidate_tree_prefix(
                root=expected_target_path,
                root_identity=expected_target_identity,
                expected_parent_identity=layout_identities["custom_config"],
                entries=entries,
                cursor=len(entries),
            )
            ini_path = (
                runtime_admission.runtime_root / "CustomConfig" / "deck_config.ini"
            )
            ini_raw, _ = _read_exact_runtime_external_file(
                ini_path,
                expected_parent_identity=layout_identities["custom_config"],
                maximum_size=_RUNTIME_EXTERNAL_FILE_ACTION_MAX_BYTES,
            )
            ini = read_deck_config(ini_path, deck_name=current_session.deck_name)
            if (
                "sha256:" + hashlib.sha256(ini_raw).hexdigest()
                != result_intent.get("deck_config_ini_sha256")
                or ini.selected_config_dir != expected_target_path.name
                or ini.sha256 != owner.next_ini_sha256
                or ini_raw != render_deck_config(
                    ini,
                    deck_name=current_session.deck_name,
                    config_dir=expected_target_path.name,
                )
            ):
                raise ValueError("ini")
            runtime_binding = _require_active_runtime_apply_lease(
                lease_pair.runtime_lease
            )
            state_path = runtime_admission.runtime_root / ".hsconfig" / "state.json"
            state_raw, _ = _read_exact_runtime_external_file(
                state_path,
                expected_parent_identity=runtime_binding.metadata_root_identity,
                maximum_size=_RUNTIME_EXTERNAL_FILE_ACTION_MAX_BYTES,
            )
            state = read_runtime_state(runtime_admission.runtime_root)
            selected = None if state is None else next(
                (row for row in state.decks if row.state_key == owner.state_key),
                None,
            )
            if (
                state is None
                or serialize_runtime_state(state) != state_raw
                or "sha256:" + hashlib.sha256(state_raw).hexdigest()
                != result_intent.get("runtime_state_sha256")
                or selected is None
                or selected.deck_name != owner.deck_name
                or selected.config_dir != expected_target_path.name
                or selected.package_root_sha256 != owner.package_root_sha256
                or selected.ini_sha256 != ini.sha256
            ):
                raise ValueError("state")
            receipt_path = _receipt_path(
                runtime_admission.runtime_root, owner.state_key
            )
            receipt_raw, _ = _read_exact_runtime_external_file(
                receipt_path,
                expected_parent_identity=layout_identities["state_receipts"],
                maximum_size=_RUNTIME_EXTERNAL_FILE_ACTION_MAX_BYTES,
            )
            if (
                "sha256:" + hashlib.sha256(receipt_raw).hexdigest()
                != result_intent.get("last_apply_receipt_sha256")
                or receipt_raw != _receipt_bytes(_receipt_payload(owner, ini.sha256))
            ):
                raise ValueError("receipt")
        except Exception as error:
            raise ValueError(
                "runtime_success_ack_current_runtime_facts_changed"
            ) from error

    def require_selected_success_ack_row_absent(
        path: Path,
        *,
        parent_identity: PathIdentity,
    ) -> None:
        try:
            _require_retained_child_absent(
                path,
                expected_parent_identity=parent_identity,
            )
        except Exception as error:
            raise ValueError("runtime_success_ack_evidence_changed") from error

    def perform() -> SuccessAckStepEvidence:
        nonlocal was_absent
        active = _require_active_controller_apply_pair(lease_pair)
        if active is not binding:
            raise ValueError("runtime_success_ack_pair_changed")
        _require_controller_pair_session_cursor(
            lease_pair=lease_pair,
            session_lease=session_lease,
            expected_session=expected_retirement_session,
        )
        persisted = load_live_start_session_under_lock(
            session_lease=session_lease
        )
        if (
            persisted.canonical_json != expected_retirement_session.canonical_json
            or persisted.session_identity
            != expected_retirement_session.session_identity
        ):
            raise ValueError("runtime_success_ack_session_changed")
        retirement = persisted.terminal_retirement
        acknowledgement = persisted.attempt_acknowledgement
        intent = persisted.result_intent
        admission = active.runtime_admission
        if (
            type(admission) is not RuntimeLiveAttemptAdmissionEvidence
            or admission.apply_attempt_id != transaction_id
            or admission.retention_owner_run_id != expected_retention_owner_run_id
            or admission.package_root_sha256 != expected_package_root_sha256
            or admission.runtime_root != lease_pair.runtime_lease.runtime_root
            or admission.runtime_root_identity
            != lease_pair.runtime_lease.runtime_root_identity
            or admission.admission_path != expected_runtime_admission_path
            or admission.admission_parent_identity
            != expected_runtime_admission_parent_identity
            or admission.admission_identity != expected_runtime_admission_identity
            or admission.admission_sha256 != expected_runtime_admission_sha256
            or not isinstance(retirement, Mapping)
            or retirement.get("operation") != "ack_success"
            or retirement.get("apply_attempt_id") != transaction_id
            or retirement.get("run_id") != expected_retention_owner_run_id
            or not isinstance(acknowledgement, Mapping)
            or not isinstance(intent, Mapping)
            or persisted.terminal_status not in {"LIVE_AND_MATCHED", "ALREADY_LIVE"}
            or intent.get("terminal_status") != persisted.terminal_status
            or (
                persisted.terminal_status == "LIVE_AND_MATCHED"
                and intent.get("raw_apply_status") not in {"applied", "recovered"}
            )
            or (
                persisted.terminal_status == "ALREADY_LIVE"
                and intent.get("raw_apply_status") != "already_current"
            )
            or intent.get("physical_disposition") != "COMMITTED"
            or intent.get("runtime_match_status") != "matched"
            or persisted.closed_apply_recovery_commitment is not None
        ):
            raise ValueError("runtime_success_ack_cursor_invalid")
        stage = retirement.get("stage")
        journal_owns_target = acknowledgement.get("journal_owns_target")
        acknowledgement_action = acknowledgement.get("acknowledgement_action")
        if (
            action == "journal"
            and stage == "PREPARED"
            and journal_owns_target is False
            and acknowledgement_action == "delete_nonowning_attempt_and_fence"
        ):
            pass
        elif (
            action == "fence"
            and stage == "PREPARED"
            and journal_owns_target is True
            and acknowledgement_action == "retain_target_owner_delete_fence"
        ):
            pass
        elif (
            action == "fence"
            and stage == "ACK_JOURNAL_RETIRED"
            and journal_owns_target is False
            and acknowledgement_action == "delete_nonowning_attempt_and_fence"
        ):
            pass
        else:
            raise ValueError("runtime_success_ack_cursor_invalid")
        expected_fields = {
            "retention_fence_path": str(expected_retention_fence_path),
            "retention_fence_identity": expected_retention_fence_identity,
            "retention_fence_sha256": expected_retention_fence_sha256,
            "journal_path": str(expected_journal_path),
            "journal_identity": expected_journal_identity,
            "journal_sha256": expected_journal_sha256,
            "target_owner_journal_path": str(expected_target_owner_journal_path),
            "target_owner_journal_identity": expected_target_owner_journal_identity,
            "target_owner_journal_sha256": expected_target_owner_journal_sha256,
            "target_path": str(expected_target_path),
            "target_identity": expected_target_identity,
            "runtime_admission_path": str(expected_runtime_admission_path),
            "runtime_admission_parent_identity": expected_runtime_admission_parent_identity,
            "runtime_admission_identity": expected_runtime_admission_identity,
            "runtime_admission_sha256": expected_runtime_admission_sha256,
            "package_root_sha256": expected_package_root_sha256,
        }
        if any(
            acknowledgement.get(name) != value
            for name, value in expected_fields.items()
        ) or any(
            retirement.get(name) != value
            for name, value in expected_fields.items()
            if name.startswith("runtime_admission_")
        ):
            raise ValueError("runtime_success_ack_binding_changed")
        intent_fields = {
            "run_id": expected_retention_owner_run_id,
            "apply_attempt_id": transaction_id,
            "package_root_sha256": expected_package_root_sha256,
            "physical_disposition": "COMMITTED",
            "runtime_match_status": "matched",
            "retained_attempt_record_path": str(expected_retention_fence_path),
            "retained_attempt_record_identity": expected_retention_fence_identity,
            "retained_attempt_record_sha256": expected_retention_fence_sha256,
            "retained_journal_path": str(expected_journal_path),
            "retained_journal_identity": expected_journal_identity,
            "retained_journal_sha256": expected_journal_sha256,
            "retained_target_owner_journal_path": str(
                expected_target_owner_journal_path
            ),
            "retained_target_owner_journal_identity": (
                expected_target_owner_journal_identity
            ),
            "retained_target_owner_journal_sha256": (
                expected_target_owner_journal_sha256
            ),
            "runtime_admission_path": str(expected_runtime_admission_path),
            "runtime_admission_parent_identity": (
                expected_runtime_admission_parent_identity
            ),
            "runtime_admission_identity": expected_runtime_admission_identity,
            "runtime_admission_sha256": expected_runtime_admission_sha256,
        }
        if (
            any(intent.get(name) != value for name, value in intent_fields.items())
            or retirement.get("result_intent_sha256")
            != intent.get("content_sha256")
        ):
            raise ValueError("runtime_success_ack_result_binding_changed")
        layout = persisted.runtime_layout_bootstrap
        if not isinstance(layout, Mapping):
            raise ValueError("runtime_success_ack_layout_missing")
        identities = _validated_complete_layout_successor_identities(
            layout=layout,
            runtime_root=admission.runtime_root,
        )
        if (
            expected_retention_fence_path
            != _runtime_attempt_retention_path(admission.runtime_root, transaction_id)
            or expected_journal_path
            != runtime_transaction_journal_path(admission.runtime_root, transaction_id)
            or expected_retention_fence_path.parent
            != admission.runtime_root / ".hsconfig" / "attempt-retention"
            or expected_journal_path.parent
            != admission.runtime_root / ".hsconfig" / "transactions"
            or expected_target_owner_journal_path.parent
            != admission.runtime_root / ".hsconfig" / "transactions"
            or expected_target_path.parent
            != admission.runtime_root / "CustomConfig"
            or path_identity(expected_runtime_admission_path.parent)
            != expected_runtime_admission_parent_identity
        ):
            raise ValueError("runtime_success_ack_path_invalid")
        require_exact_file(
            expected_runtime_admission_path,
            parent_identity=expected_runtime_admission_parent_identity,
            expected_identity=expected_runtime_admission_identity,
            expected_sha256=expected_runtime_admission_sha256,
            maximum_size=RUNTIME_LIVE_ATTEMPT_ADMISSION_MAX_BYTES,
        )
        owner_raw, owner_identity = require_exact_file(
            expected_target_owner_journal_path,
            parent_identity=identities["transactions"],
            expected_identity=expected_target_owner_journal_identity,
            expected_sha256=expected_target_owner_journal_sha256,
            maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
        )
        owner = parse_runtime_transaction_journal_bytes(
            owner_raw,
            expected_transaction_id=expected_target_owner_journal_path.stem,
        )
        if (
            owner_identity != expected_target_owner_journal_identity
            or owner.phase is not RuntimeTransactionPhase.FINALIZED
            or not owner.owns_target
            or owner.source_manifest_sha256
            != expected_package_root_sha256.removeprefix("sha256:")
            or owner.target_identity != expected_target_identity
            or owner.target_path
            != expected_target_path.relative_to(admission.runtime_root).as_posix()
        ):
            raise ValueError("runtime_success_ack_owner_changed")
        journal_raw: bytes | None = None
        journal_identity: PathIdentity | None = None
        journal: RuntimeTransactionJournal | None = None
        journal_must_survive = journal_owns_target is True
        if action == "journal" or journal_must_survive:
            if action == "journal" and not path_lexists(expected_journal_path):
                if path_identity(expected_journal_path.parent) != identities[
                    "transactions"
                ]:
                    raise ValueError("runtime_success_ack_owner_changed")
            else:
                journal_raw, journal_identity = require_exact_file(
                    expected_journal_path,
                    parent_identity=identities["transactions"],
                    expected_identity=expected_journal_identity,
                    expected_sha256=expected_journal_sha256,
                    maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
                )
                journal = parse_runtime_transaction_journal_bytes(
                    journal_raw,
                    expected_transaction_id=transaction_id,
                )
                if (
                    journal_identity != expected_journal_identity
                    or journal.phase is not RuntimeTransactionPhase.FINALIZED
                    or journal.owns_target != journal_must_survive
                    or journal.source_manifest_sha256
                    != expected_package_root_sha256.removeprefix("sha256:")
                    or journal.target_identity != expected_target_identity
                    or journal.target_path != owner.target_path
                    or journal.next_config_dir != owner.next_config_dir
                    or journal.package_root_sha256 != owner.package_root_sha256
                ):
                    raise ValueError("runtime_success_ack_owner_changed")
                if journal_must_survive:
                    if (
                        expected_journal_path != expected_target_owner_journal_path
                        or expected_journal_identity
                        != expected_target_owner_journal_identity
                        or expected_journal_sha256
                        != expected_target_owner_journal_sha256
                    ):
                        raise ValueError("runtime_success_ack_owner_changed")
                elif expected_journal_path == expected_target_owner_journal_path:
                    raise ValueError("runtime_success_ack_owner_changed")
        elif (
            path_lexists(expected_journal_path)
            or path_identity(expected_journal_path.parent)
            != identities["transactions"]
        ):
            raise ValueError("runtime_success_ack_owner_changed")
        require_current_success_runtime_parity(
            owner=owner,
            layout_identities=identities,
            result_intent=intent,
            current_session=persisted,
            runtime_admission=admission,
        )
        _observe_retained_directory(
            expected_target_path,
            expected_identity=expected_target_identity,
            expected_parent_identity=identities["custom_config"],
        )
        fence_raw: bytes | None = None
        if path_lexists(expected_retention_fence_path):
            fence_raw, fence_identity = require_exact_file(
                expected_retention_fence_path,
                parent_identity=identities["attempt_retention"],
                expected_identity=expected_retention_fence_identity,
                expected_sha256=expected_retention_fence_sha256,
                maximum_size=RUNTIME_ATTEMPT_RETENTION_MAX_BYTES,
            )
            record = _runtime_attempt_retention_from_raw(
                fence_raw,
                runtime_root=admission.runtime_root,
            )
            if (
                fence_identity != expected_retention_fence_identity
                or record.schema_version != RUNTIME_ATTEMPT_RETENTION_SCHEMA_VERSION
                or record.state != "FINALIZED"
                or record.apply_attempt_id != transaction_id
                or record.retention_owner_run_id != expected_retention_owner_run_id
                or record.journal_path != expected_journal_path
                or record.journal_identity != expected_journal_identity
                or record.journal_sha256 != expected_journal_sha256
                or record.package_root_sha256
                != "sha256:" + owner.package_root_sha256
                or record.target_path != expected_target_path
                or record.target_identity != expected_target_identity
                or record.owns_target is not journal_must_survive
                or record.target_owner_journal_path
                != expected_target_owner_journal_path
                or record.target_owner_journal_identity
                != expected_target_owner_journal_identity
                or record.target_owner_journal_sha256
                != expected_target_owner_journal_sha256
            ):
                raise ValueError("runtime_success_ack_fence_changed")
        else:
            if path_identity(expected_retention_fence_path.parent) != identities[
                "attempt_retention"
            ]:
                raise ValueError("runtime_success_ack_fence_parent_changed")
            if action == "journal":
                raise ValueError("runtime_success_ack_fence_changed")
        if action == "journal":
            was_absent = journal_raw is None
            if journal_raw is not None:
                assert journal_identity is not None
                secure_unlink_verified(
                    expected_journal_path,
                    expected_identity=journal_identity,
                    expected_parent_identity=identities["transactions"],
                    expected_size=len(journal_raw),
                    expected_sha256=hashlib.sha256(journal_raw).hexdigest(),
                )
            require_selected_success_ack_row_absent(
                expected_journal_path,
                parent_identity=identities["transactions"],
            )
            require_exact_file(
                expected_retention_fence_path,
                parent_identity=identities["attempt_retention"],
                expected_identity=expected_retention_fence_identity,
                expected_sha256=expected_retention_fence_sha256,
                maximum_size=RUNTIME_ATTEMPT_RETENTION_MAX_BYTES,
            )
        else:
            was_absent = fence_raw is None
            if fence_raw is not None:
                secure_unlink_verified(
                    expected_retention_fence_path,
                    expected_identity=expected_retention_fence_identity,
                    expected_parent_identity=identities["attempt_retention"],
                    expected_size=len(fence_raw),
                    expected_sha256=hashlib.sha256(fence_raw).hexdigest(),
                )
            require_selected_success_ack_row_absent(
                expected_retention_fence_path,
                parent_identity=identities["attempt_retention"],
            )
            if journal_must_survive:
                require_exact_file(
                    expected_journal_path,
                    parent_identity=identities["transactions"],
                    expected_identity=expected_journal_identity,
                    expected_sha256=expected_journal_sha256,
                    maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
                )
            elif (
                path_lexists(expected_journal_path)
                or path_identity(expected_journal_path.parent)
                != identities["transactions"]
            ):
                raise ValueError("runtime_success_ack_owner_changed")
        require_exact_file(
            expected_target_owner_journal_path,
            parent_identity=identities["transactions"],
            expected_identity=expected_target_owner_journal_identity,
            expected_sha256=expected_target_owner_journal_sha256,
            maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
        )
        _observe_retained_directory(
            expected_target_path,
            expected_identity=expected_target_identity,
            expected_parent_identity=identities["custom_config"],
        )
        require_exact_file(
            expected_runtime_admission_path,
            parent_identity=expected_runtime_admission_parent_identity,
            expected_identity=expected_runtime_admission_identity,
            expected_sha256=expected_runtime_admission_sha256,
            maximum_size=RUNTIME_LIVE_ATTEMPT_ADMISSION_MAX_BYTES,
        )
        require_current_success_runtime_parity(
            owner=owner,
            layout_identities=identities,
            result_intent=intent,
            current_session=persisted,
            runtime_admission=admission,
        )
        current = load_live_start_session_under_lock(session_lease=session_lease)
        if (
            current.canonical_json != persisted.canonical_json
            or current.session_identity != persisted.session_identity
        ):
            raise ValueError("runtime_success_ack_session_changed")
        require_selected_success_ack_row_absent(
            expected_journal_path
            if action == "journal"
            else expected_retention_fence_path,
            parent_identity=(
                identities["transactions"]
                if action == "journal"
                else identities["attempt_retention"]
            ),
        )
        successor = _plain_json_value(retirement)
        successor.pop("content_sha256", None)
        successor["stage"] = (
            "ACK_JOURNAL_RETIRED" if action == "journal" else "EVIDENCE_RETIRED"
        )
        return SuccessAckStepEvidence(
            action=physical_action,
            evidence={
                "terminal_retirement": seal_embedded_document(
                    "terminal_retirement", successor
                )
            },
        )

    receipt = _execute_terminal_resolution_physical_step(
        terminal_authorization=terminal_authorization,
        action=physical_action,
        physical_action=perform,
    )
    return RuntimeAttemptEvidenceRetirementStep(
        action=action,
        object_was_already_absent=was_absent,
        step_receipt=receipt,
    )


def _snapshot_terminal_cleanup_root(
    *,
    root_role: Literal["candidate", "target"],
    root_path: Path,
    root_identity: PathIdentity,
    root_parent_identity: PathIdentity,
) -> tuple[dict[str, Any], ...]:
    if (
        path_identity(root_path.parent) != root_parent_identity
        or path_identity(root_path) != root_identity
    ):
        raise ValueError("runtime_terminal_cleanup_root_changed")
    rows: list[dict[str, Any]] = []
    total_file_bytes = 0
    discovered_nodes = 1
    metadata_bytes = 0

    def append_row(row: dict[str, Any]) -> None:
        nonlocal metadata_bytes
        row_bytes = len(
            json.dumps(
                row,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        )
        metadata_bytes += row_bytes + 1
        if (
            len(rows) + 1
            > LIVE_START_TERMINAL_CLEANUP_INVENTORY_MAX_ENTRIES
            or metadata_bytes
            > LIVE_START_TERMINAL_CLEANUP_INVENTORY_MAX_BYTES
        ):
            raise ValueError("runtime_terminal_cleanup_inventory_too_large")
        rows.append(row)
    pending: list[tuple[Path, str, PathIdentity, PathIdentity]] = [
        (root_path, ".", root_identity, root_parent_identity)
    ]
    while pending:
        (
            directory,
            relative,
            expected_identity,
            expected_parent_identity,
        ) = pending.pop()
        status = directory.lstat()
        identity = path_identity_from_status(status)
        if (
            not stat.S_ISDIR(status.st_mode)
            or status_is_reparse(status)
            or identity != expected_identity
            or path_identity(directory.parent) != expected_parent_identity
        ):
            raise ValueError("runtime_terminal_cleanup_entry_changed")
        require_no_alternate_data_streams(
            directory,
            expected_identity=identity,
            expected_parent_identity=expected_parent_identity,
            directory=True,
        )
        depth = 0 if relative == "." else relative.count("/") + 1
        if depth > MAX_FILESYSTEM_DEPTH:
            raise ValueError("runtime_terminal_cleanup_inventory_too_deep")
        append_row(
            {
                "root_role": root_role,
                "relative_path": relative,
                "entry_kind": "directory",
                "identity": identity,
                "expected_parent_identity": expected_parent_identity,
                "size": None,
                "sha256": None,
            }
        )
        children: list[
            tuple[Path, str, PathIdentity, PathIdentity]
        ] = []
        directory_entry_count = 0
        with os.scandir(directory) as iterator:
            for entry in iterator:
                directory_entry_count += 1
                if (
                    directory_entry_count
                    > MAX_FILESYSTEM_ENTRIES_PER_DIRECTORY
                ):
                    raise ValueError(
                        "runtime_terminal_cleanup_inventory_too_wide"
                    )
                discovered_nodes += 1
                if (
                    discovered_nodes
                    > LIVE_START_TERMINAL_CLEANUP_INVENTORY_MAX_ENTRIES
                ):
                    raise ValueError(
                        "runtime_terminal_cleanup_inventory_too_large"
                    )
                child = Path(entry.path)
                child_relative = (
                    entry.name
                    if relative == "."
                    else f"{relative}/{entry.name}"
                )
                child_status = child.lstat()
                child_identity = path_identity_from_status(child_status)
                if status_is_reparse(child_status):
                    raise ValueError("runtime_terminal_cleanup_entry_changed")
                if stat.S_ISDIR(child_status.st_mode):
                    children.append(
                        (child, child_relative, child_identity, identity)
                    )
                    continue
                if (
                    not stat.S_ISREG(child_status.st_mode)
                    or child_status.st_nlink != 1
                    or child_status.st_size
                    > LIVE_START_TERMINAL_CLEANUP_INVENTORY_MAX_BYTES
                    - total_file_bytes
                ):
                    raise ValueError("runtime_terminal_cleanup_entry_changed")
                require_no_alternate_data_streams(
                    child,
                    expected_identity=child_identity,
                    expected_parent_identity=identity,
                    directory=False,
                    expected_size=child_status.st_size,
                )
                raw = read_file_no_follow(
                    child,
                    expected_status=child_status,
                    maximum_size=max(child_status.st_size, 1),
                )
                total_file_bytes += len(raw)
                if (
                    len(rows) + 1
                    > LIVE_START_TERMINAL_CLEANUP_INVENTORY_MAX_ENTRIES
                    or total_file_bytes
                    > LIVE_START_TERMINAL_CLEANUP_INVENTORY_MAX_BYTES
                ):
                    raise ValueError(
                        "runtime_terminal_cleanup_inventory_too_large"
                    )
                append_row(
                    {
                        "root_role": root_role,
                        "relative_path": child_relative,
                        "entry_kind": "file",
                        "identity": child_identity,
                        "expected_parent_identity": identity,
                        "size": len(raw),
                        "sha256": "sha256:"
                        + hashlib.sha256(raw).hexdigest(),
                    }
                )
        pending.extend(reversed(sorted(children, key=lambda row: row[1])))
    if (
        path_identity(root_path.parent) != root_parent_identity
        or path_identity(root_path) != root_identity
    ):
        raise ValueError("runtime_terminal_cleanup_root_changed")
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                ("candidate", "target").index(str(row["root_role"])),
                -(
                    0
                    if row["relative_path"] == "."
                    else str(row["relative_path"]).count("/") + 1
                ),
                str(row["relative_path"]).encode(),
            ),
        )
    )


def _reconstruct_runtime_no_commit_inventory_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    transaction_id: str,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    observed: _ExactPairedRuntimeAttemptObservation | None,
) -> TerminalResolutionCleanupInventory:
    """Reconstruct the exact sealed no-commit tree inventory read-only."""

    binding = _require_active_controller_apply_pair(lease_pair)
    persisted = load_live_start_session_under_lock(
        session_lease=binding.session_lease
    )
    _validate_controller_pair_session_provenance(
        binding=binding, persisted=persisted
    )
    result_intent = persisted.result_intent
    if (
        binding.runtime_admission != runtime_admission
        or runtime_admission.apply_attempt_id != transaction_id
        or not isinstance(result_intent, Mapping)
        or result_intent.get("physical_disposition") != "NOT_COMMITTED"
        or result_intent.get("retained_candidate_identity") is None
        or result_intent.get("retained_journal_path") is None
        or result_intent.get("retained_journal_identity") is None
        or result_intent.get("retained_journal_sha256") is None
    ):
        raise ValueError("runtime_terminal_cleanup_provenance_invalid")
    layout_identities = _validated_complete_layout_successor_identities(
        layout=persisted.runtime_layout_bootstrap,
        runtime_root=lease_pair.runtime_lease.runtime_root,
    )
    retained_journal_path = Path(str(result_intent["retained_journal_path"]))
    retained_journal_raw, retained_journal_identity = (
        _read_exact_runtime_external_file(
            retained_journal_path,
            expected_parent_identity=layout_identities["transactions"],
            maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
        )
    )
    if (
        retained_journal_identity
        != tuple(result_intent["retained_journal_identity"])
        or "sha256:" + hashlib.sha256(retained_journal_raw).hexdigest()
        != result_intent["retained_journal_sha256"]
    ):
        raise ValueError("runtime_terminal_cleanup_provenance_invalid")
    retained_journal = parse_runtime_transaction_journal_bytes(
        retained_journal_raw,
        expected_transaction_id=transaction_id,
    )
    retained_target_path = (
        lease_pair.runtime_lease.runtime_root / retained_journal.target_path
    )
    bound_target = (
        (retained_target_path, tuple(result_intent["retained_candidate_identity"]))
        if not path_lexists(
            lease_pair.runtime_lease.runtime_root
            / ".hsconfig"
            / "staging"
            / transaction_id
        )
        and path_lexists(retained_target_path)
        else None
    )
    if observed is None:
        observed = _observe_exact_paired_runtime_attempt(
            lease_pair.runtime_lease.runtime_root,
            transaction_id=transaction_id,
            expected_retention_owner_run_id=(
                runtime_admission.retention_owner_run_id
            ),
            expected_package_root_sha256=(
                "sha256:" + retained_journal.package_root_sha256
            ),
            expected_deck_name=persisted.deck_name,
            recovery_cursor=None,
            action_bound_candidate_identity=tuple(
                result_intent["retained_candidate_identity"]
            ),
            action_bound_journal_triplet=(
                str(retained_journal_path),
                retained_journal_identity,
                str(result_intent["retained_journal_sha256"]),
            ),
            action_bound_target=bound_target,
        )
    retained = observed.retention
    transaction = observed.transaction
    if retained is None or transaction.journal is None:
        raise ValueError("runtime_terminal_cleanup_provenance_invalid")
    record = retained.record
    journal = transaction.journal
    expected_owner_triplet = (
        result_intent.get("retained_target_owner_journal_path"),
        result_intent.get("retained_target_owner_journal_identity"),
        result_intent.get("retained_target_owner_journal_sha256"),
    )
    observed_owner_triplet = (
        (
            str(record.target_owner_journal_path)
            if record.target_owner_journal_path is not None
            else None
        ),
        record.target_owner_journal_identity,
        record.target_owner_journal_sha256,
    )
    if (
        str(retained.path) != result_intent["retained_attempt_record_path"]
        or retained.identity
        != tuple(result_intent["retained_attempt_record_identity"])
        or retained.raw_sha256
        != result_intent["retained_attempt_record_sha256"]
        or str(transaction.journal_path)
        != result_intent["retained_journal_path"]
        or transaction.journal_identity
        != tuple(result_intent["retained_journal_identity"])
        or transaction.journal_sha256
        != result_intent["retained_journal_sha256"]
        or observed_owner_triplet[0] != expected_owner_triplet[0]
        or (
            tuple(observed_owner_triplet[1])
            if observed_owner_triplet[1] is not None
            else None
        )
        != (
            tuple(expected_owner_triplet[1])
            if expected_owner_triplet[1] is not None
            else None
        )
        or observed_owner_triplet[2] != expected_owner_triplet[2]
    ):
        raise ValueError("runtime_terminal_cleanup_provenance_changed")
    owner_raw: bytes | None = None
    owner_identity: PathIdentity | None = None
    if expected_owner_triplet[0] is not None:
        owner_raw, owner_identity = _read_exact_runtime_external_file(
            Path(str(expected_owner_triplet[0])),
            expected_parent_identity=layout_identities["transactions"],
            maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
        )
        if (
            owner_identity != tuple(expected_owner_triplet[1])
            or "sha256:" + hashlib.sha256(owner_raw).hexdigest()
            != expected_owner_triplet[2]
        ):
            raise ValueError("runtime_terminal_cleanup_provenance_changed")
    candidate = Path(str(record.candidate_path))
    target = lease_pair.runtime_lease.runtime_root / journal.target_path
    retained_identity = tuple(result_intent["retained_candidate_identity"])
    candidate_exists = path_lexists(candidate)
    target_exists = path_lexists(target)
    if candidate_exists == target_exists:
        raise ValueError("runtime_terminal_cleanup_root_projection_invalid")
    if candidate_exists:
        role: Literal["candidate", "target"] = "candidate"
        root = candidate
        parent_identity = layout_identities["staging"]
        planned_candidate = (
            record.state == "CANDIDATE_PLANNED"
            and journal.phase == RuntimeTransactionPhase.PREPARED
            and record.candidate_identity is None
            and journal.candidate_identity is None
            and record.planned_journal_path == retained_journal_path
            and record.planned_journal_size == len(retained_journal_raw)
            and record.planned_journal_sha256
            == result_intent["retained_journal_sha256"]
        )
        bound_candidate = (
            record.state == "CANDIDATE_BOUND"
            and journal.phase
            in {
                RuntimeTransactionPhase.PREPARED,
                RuntimeTransactionPhase.RUNTIME_STAGED,
                RuntimeTransactionPhase.RUNTIME_VERIFIED,
            }
            and record.candidate_identity == retained_identity
            and (
                journal.candidate_identity is None
                if journal.phase == RuntimeTransactionPhase.PREPARED
                else journal.candidate_identity == retained_identity
            )
        )
        if (
            target_exists
            or record.candidate_parent_identity != parent_identity
            or not (planned_candidate or bound_candidate)
            or journal.owns_target
        ):
            raise ValueError("runtime_terminal_cleanup_root_projection_invalid")
    else:
        role = "target"
        root = target
        parent_identity = layout_identities["custom_config"]
        if (
            record.state != "CANDIDATE_BOUND"
            or journal.phase != RuntimeTransactionPhase.RUNTIME_VERIFIED
            or record.candidate_identity != retained_identity
            or journal.candidate_identity != retained_identity
            or journal.owns_target
        ):
            raise ValueError("runtime_terminal_cleanup_root_projection_invalid")
    if (
        path_identity(root.parent) != parent_identity
        or path_identity(root) != retained_identity
    ):
        raise ValueError("runtime_terminal_cleanup_root_changed")
    first = _snapshot_terminal_cleanup_root(
        root_role=role,
        root_path=root,
        root_identity=retained_identity,
        root_parent_identity=parent_identity,
    )
    second = _snapshot_terminal_cleanup_root(
        root_role=role,
        root_path=root,
        root_identity=retained_identity,
        root_parent_identity=parent_identity,
    )
    if first != second:
        raise ValueError("runtime_terminal_cleanup_surface_changed")
    roots = [
        {
            "root_role": role,
            "source_path": str(root),
            "source_identity": retained_identity,
            "expected_parent_identity": parent_identity,
        }
    ]
    value = {
        "schema_version": 1,
        "inventory_kind": "live_start_terminal_resolution_cleanup_inventory",
        "run_id": persisted.run_id,
        "apply_attempt_id": transaction_id,
        "runtime_root_path": str(runtime_admission.runtime_root),
        "runtime_root_identity": runtime_admission.runtime_root_identity,
        "cleanup_roots": roots,
        "cleanup_manifest_sha256": _terminal_cleanup_manifest_sha256(first),
        "cleanup_entry_count": len(first),
        "entries": list(first),
    }
    inventory_unsigned = _plain_json_value(value)
    inventory_raw = (
        json.dumps(
            inventory_unsigned,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    inventory = TerminalResolutionCleanupInventory(
        {
            **inventory_unsigned,
            "content_sha256": "sha256:"
            + hashlib.sha256(inventory_raw).hexdigest(),
        }
    )
    retirement = persisted.terminal_retirement
    if retirement is not None:
        resolution = retirement.get("terminal_resolution_evidence")
        external = (
            resolution.get("external_file_action")
            if isinstance(resolution, Mapping)
            else None
        )
        inventory_path = binding.session_root / "terminal-resolution-cleanup.json"
        staging_path = inventory_path.with_name(f"{inventory_path.name}.staged")
        inner_path = staging_path.with_name(
            f".{staging_path.name}.live-start-atomic.tmp"
        )
        if (
            retirement.get("operation") != "release_resolved_terminal"
            or retirement.get("stage") != "RECOVERY_PREPARED"
            or not isinstance(resolution, Mapping)
            or resolution.get("cleanup_stage") != "PREPARED"
            or resolution.get("cleanup_inventory_path") != str(inventory_path)
            or tuple(resolution.get("cleanup_inventory_parent_identity", ()))
            != binding.session_root_identity
            or resolution.get("cleanup_inventory_identity") is not None
            or resolution.get("cleanup_inventory_size") != inventory.size
            or resolution.get("cleanup_inventory_sha256") != inventory.sha256
            or resolution.get("cleanup_manifest_sha256")
            != inventory.value["cleanup_manifest_sha256"]
            or resolution.get("cleanup_entry_count") != len(first)
            or resolution.get("cleanup_cursor") != 0
            or _plain_json_value(resolution.get("cleanup_roots"))
            != _plain_json_value(roots)
            or not isinstance(external, Mapping)
            or external.get("action_kind")
            != "commit_bound_terminal_cleanup_inventory"
            or external.get("final_path") != str(inventory_path)
            or external.get("staging_path") != str(staging_path)
            or external.get("inner_temp_path") != str(inner_path)
            or tuple(external.get("parent_identity", ()))
            != binding.session_root_identity
            or external.get("planned_successor_size") != inventory.size
            or external.get("planned_successor_sha256") != inventory.sha256
            or path_lexists(inner_path)
        ):
            raise ValueError(
                "runtime_terminal_cleanup_replay_commitment_changed"
            )
        external_stage = external.get("stage")
        if external_stage == "PLANNED":
            physical_valid = not path_lexists(inventory_path) and not path_lexists(
                staging_path
            )
        elif external_stage == "STAGING_BOUND":
            expected_staging_identity = tuple(
                external.get("staging_identity", ())
            )
            if path_lexists(staging_path) and not path_lexists(inventory_path):
                staging_raw, staging_identity = _read_exact_runtime_external_file(
                    staging_path,
                    expected_parent_identity=binding.session_root_identity,
                    maximum_size=inventory.size,
                )
                physical_valid = (
                    staging_identity == expected_staging_identity
                    and staging_raw == inventory.canonical_json
                )
            elif path_lexists(inventory_path) and not path_lexists(staging_path):
                final_raw, final_identity = _read_exact_runtime_external_file(
                    inventory_path,
                    expected_parent_identity=binding.session_root_identity,
                    maximum_size=inventory.size,
                )
                physical_valid = (
                    final_identity == expected_staging_identity
                    and final_raw == inventory.canonical_json
                )
            elif (
                os.name != "nt"
                and path_lexists(inventory_path)
                and path_lexists(staging_path)
            ):
                def read_two_link(path: Path) -> tuple[bytes, PathIdentity]:
                    status = path.lstat()
                    identity = path_identity_from_status(status)
                    if (
                        not stat.S_ISREG(status.st_mode)
                        or status_is_reparse(status)
                        or status.st_nlink != 2
                        or identity != expected_staging_identity
                        or path_identity(path.parent)
                        != binding.session_root_identity
                        or status.st_size != inventory.size
                    ):
                        raise ValueError(
                            "runtime_terminal_cleanup_replay_commitment_changed"
                        )
                    require_no_alternate_data_streams(
                        path,
                        expected_identity=identity,
                        expected_parent_identity=binding.session_root_identity,
                        directory=False,
                        expected_size=status.st_size,
                    )
                    descriptor = os.open(
                        path,
                        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                    )
                    try:
                        opened = os.fstat(descriptor)
                        if (
                            path_identity_from_status(opened) != identity
                            or opened.st_nlink != 2
                            or opened.st_size != inventory.size
                        ):
                            raise ValueError(
                                "runtime_terminal_cleanup_replay_commitment_changed"
                            )
                        chunks: list[bytes] = []
                        remaining = inventory.size
                        while remaining:
                            chunk = os.read(descriptor, min(remaining, 64 * 1024))
                            if not chunk:
                                raise ValueError(
                                    "runtime_terminal_cleanup_replay_commitment_changed"
                                )
                            chunks.append(chunk)
                            remaining -= len(chunk)
                        if os.read(descriptor, 1):
                            raise ValueError(
                                "runtime_terminal_cleanup_replay_commitment_changed"
                            )
                        after = os.fstat(descriptor)
                        if (
                            path_identity_from_status(after) != identity
                            or after.st_nlink != 2
                            or after.st_size != inventory.size
                            or path_identity(path) != identity
                            or path_identity(path.parent)
                            != binding.session_root_identity
                        ):
                            raise ValueError(
                                "runtime_terminal_cleanup_replay_commitment_changed"
                            )
                        return b"".join(chunks), identity
                    finally:
                        os.close(descriptor)

                staging_raw, staging_identity = read_two_link(staging_path)
                final_raw, final_identity = read_two_link(inventory_path)
                staging_status = staging_path.lstat()
                final_status = inventory_path.lstat()
                physical_valid = (
                    staging_identity == expected_staging_identity
                    and final_identity == expected_staging_identity
                    and path_identity_from_status(staging_status)
                    == expected_staging_identity
                    and path_identity_from_status(final_status)
                    == expected_staging_identity
                    and staging_status.st_nlink == 2
                    and final_status.st_nlink == 2
                    and staging_raw == inventory.canonical_json
                    and final_raw == inventory.canonical_json
                )
            else:
                physical_valid = False
        else:
            physical_valid = False
        if not physical_valid:
            raise ValueError(
                "runtime_terminal_cleanup_replay_commitment_changed"
            )
    if _snapshot_terminal_cleanup_root(
        root_role=role,
        root_path=root,
        root_identity=retained_identity,
        root_parent_identity=parent_identity,
    ) != first:
        raise ValueError("runtime_terminal_cleanup_surface_changed")
    post_journal_raw, post_journal_identity = _read_exact_runtime_external_file(
        retained_journal_path,
        expected_parent_identity=layout_identities["transactions"],
        maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
    )
    retained_attempt_path = Path(
        str(result_intent["retained_attempt_record_path"])
    )
    post_attempt_raw, post_attempt_identity = _read_exact_runtime_external_file(
        retained_attempt_path,
        expected_parent_identity=layout_identities["attempt_retention"],
        maximum_size=RUNTIME_ATTEMPT_RETENTION_MAX_BYTES,
    )
    if (
        post_journal_raw != retained_journal_raw
        or post_journal_identity != retained_journal_identity
        or post_attempt_identity
        != tuple(result_intent["retained_attempt_record_identity"])
        or "sha256:" + hashlib.sha256(post_attempt_raw).hexdigest()
        != result_intent["retained_attempt_record_sha256"]
    ):
        raise ValueError("runtime_terminal_cleanup_provenance_changed")
    if expected_owner_triplet[0] is not None:
        post_owner_raw, post_owner_identity = _read_exact_runtime_external_file(
            Path(str(expected_owner_triplet[0])),
            expected_parent_identity=layout_identities["transactions"],
            maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
        )
        if post_owner_raw != owner_raw or post_owner_identity != owner_identity:
            raise ValueError("runtime_terminal_cleanup_provenance_changed")
    if (
        path_lexists(candidate) != candidate_exists
        or path_lexists(target) != target_exists
        or path_identity(root.parent) != parent_identity
        or path_identity(root) != retained_identity
    ):
        raise ValueError("runtime_terminal_cleanup_surface_changed")
    post = load_live_start_session_under_lock(
        session_lease=binding.session_lease
    )
    if post != persisted or post.canonical_json != persisted.canonical_json:
        raise ValueError("runtime_terminal_cleanup_session_changed")
    return inventory


def reconstruct_runtime_no_commit_inventory_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    transaction_id: str,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
) -> TerminalResolutionCleanupInventory:
    """Reconstruct the exact sealed no-commit tree inventory read-only."""

    return _reconstruct_runtime_no_commit_inventory_from_pair(
        lease_pair=lease_pair,
        transaction_id=transaction_id,
        runtime_admission=runtime_admission,
        observed=None,
    )


def recover_runtime_attempt_from_pair(
    *,
    lease_pair: ControllerApplyLeasePair,
    transaction_id: str,
    expected_retention_owner_run_id: str,
    expected_package_root_sha256: str,
    expected_deck_name: str,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
    observation_family: RuntimeRecoveryObservationFamily | None = None,
    runtime_observation_authorization: (
        RuntimeObservationAuthorization | None
    ) = None,
    nonterminal_recovery_authorization: (
        RuntimeAttemptRecoveryAuthorization | None
    ) = None,
    terminal_authorization: TerminalRetirementAuthorization | None = None,
) -> RuntimeAttemptRecovery:
    """Observe or advance one exact attempt under an active controller pair."""

    observation_mode = (
        observation_family is not None
        or runtime_observation_authorization is not None
    )
    physical_count = sum(
        authority is not None
        for authority in (
            nonterminal_recovery_authorization,
            terminal_authorization,
        )
    )
    if (
        not isinstance(transaction_id, str)
        or _ATTEMPT_ID.fullmatch(transaction_id) is None
        or not isinstance(expected_retention_owner_run_id, str)
        or _ATTEMPT_ID.fullmatch(expected_retention_owner_run_id) is None
        or not isinstance(expected_package_root_sha256, str)
        or _PREFIXED_SHA256.fullmatch(expected_package_root_sha256) is None
        or not _valid_deck_name(expected_deck_name)
        or type(runtime_admission)
        is not RuntimeLiveAttemptAdmissionEvidence
        or (
            runtime_observation_authorization is not None
            and type(runtime_observation_authorization)
            is not RuntimeObservationAuthorization
        )
        or (
            nonterminal_recovery_authorization is not None
            and type(nonterminal_recovery_authorization)
            is not RuntimeAttemptRecoveryAuthorization
        )
        or (
            terminal_authorization is not None
            and type(terminal_authorization)
            is not TerminalRetirementAuthorization
        )
        or (
            observation_mode
            and (
                observation_family
                not in {"nonterminal_apply", "terminal_resolution"}
                or runtime_observation_authorization is None
                or physical_count != 0
            )
        )
        or (not observation_mode and physical_count != 1)
    ):
        raise ValueError("runtime_attempt_recovery_carrier_matrix_invalid")

    binding = _require_active_controller_apply_pair(lease_pair)
    persisted = load_live_start_session_under_lock(
        session_lease=binding.session_lease
    )
    _validate_controller_pair_session_provenance(
        binding=binding,
        persisted=persisted,
    )
    if (
        binding.runtime_admission != runtime_admission
        or runtime_admission.apply_attempt_id != transaction_id
        or runtime_admission.retention_owner_run_id
        != expected_retention_owner_run_id
        or runtime_admission.package_root_sha256
        != expected_package_root_sha256
        or runtime_admission.runtime_root
        != lease_pair.runtime_lease.runtime_root
        or runtime_admission.runtime_root_identity
        != lease_pair.runtime_lease.runtime_root_identity
        or persisted.run_id != runtime_admission.run_id
        or persisted.deck_name != expected_deck_name
    ):
        raise ValueError("runtime_attempt_recovery_pair_mismatch")
    runtime_root = lease_pair.runtime_lease.runtime_root
    terminal_closed_recovery: Mapping[str, Any] | None = None
    if observation_family == "terminal_resolution":
        terminal_closed_recovery = persisted.closed_apply_recovery_commitment
        terminal_intent = persisted.result_intent
        if (
            persisted.apply_recovery is not None
            or persisted.terminal_retirement is not None
            or not isinstance(terminal_closed_recovery, Mapping)
            or terminal_closed_recovery.get("recovery_stage") != "CLOSED"
            or terminal_closed_recovery.get("run_id") != runtime_admission.run_id
            or terminal_closed_recovery.get("apply_attempt_id")
            != transaction_id
            or terminal_closed_recovery.get("runtime_admission_path")
            != str(runtime_admission.admission_path)
            or tuple(
                terminal_closed_recovery.get("runtime_admission_identity", ())
            )
            != runtime_admission.admission_identity
            or terminal_closed_recovery.get("runtime_admission_sha256")
            != runtime_admission.admission_sha256
            or terminal_closed_recovery.get("package_root_sha256")
            != expected_package_root_sha256
            or terminal_closed_recovery.get("runtime_root") != str(runtime_root)
            or tuple(terminal_closed_recovery.get("runtime_root_identity", ()))
            != runtime_admission.runtime_root_identity
            or not isinstance(terminal_intent, Mapping)
            or persisted.terminal_status != terminal_intent.get("terminal_status")
            or terminal_intent.get("run_id") != runtime_admission.run_id
            or terminal_intent.get("apply_attempt_id") != transaction_id
            or terminal_intent.get("package_root_sha256")
            != terminal_closed_recovery.get("package_root_sha256")
            or terminal_intent.get("physical_disposition")
            != terminal_closed_recovery.get("stable_physical_disposition")
            or terminal_intent.get("runtime_admission_path")
            != terminal_closed_recovery.get("runtime_admission_path")
            or tuple(terminal_intent.get("runtime_admission_identity", ()))
            != tuple(terminal_closed_recovery.get("runtime_admission_identity", ()))
            or terminal_intent.get("runtime_admission_sha256")
            != terminal_closed_recovery.get("runtime_admission_sha256")
            or not _closed_recovery_result_intent_binding_is_exact(
                closed_recovery=terminal_closed_recovery,
                result_intent=terminal_intent,
            )
        ):
            raise ValueError("runtime_attempt_recovery_terminal_session_invalid")
    layout = persisted.runtime_layout_bootstrap
    if not isinstance(layout, Mapping):
        raise ValueError("runtime_attempt_recovery_layout_missing")
    layout_identities = _validated_complete_layout_successor_identities(
        layout=layout,
        runtime_root=runtime_root,
    )
    runtime_lease_binding = _require_active_runtime_apply_lease(
        lease_pair.runtime_lease
    )

    if observation_mode:
        assert observation_family is not None
        assert runtime_observation_authorization is not None
        bearer = _require_opaque_carrier(
            runtime_observation_authorization,
            carrier_type=RuntimeObservationAuthorization,
            family=f"runtime_observation:{observation_family}",
            action=transaction_id,
            consume=False,
        )
        if (
            bearer.session_bearer
            is not binding.session_token._bearer
            or bearer.cursor_sha256 != persisted.content_sha256
        ):
            raise ValueError(
                "runtime_attempt_recovery_observation_capability_changed"
            )
        observed: _ExactPairedRuntimeAttemptObservation | None = None
        terminal_inventory: TerminalResolutionCleanupInventory | None = None

        def observe() -> RuntimeObservationPostcondition:
            nonlocal observed, terminal_inventory
            observation_package_sha256 = expected_package_root_sha256
            terminal_unknown_projection = (
                observation_family == "terminal_resolution"
                and terminal_closed_recovery is not None
                and terminal_closed_recovery.get("stable_physical_disposition")
                == "UNKNOWN_REQUIRES_RECOVERY"
            )
            observation_journal_triplet: tuple[
                str, PathIdentity, str
            ] | None = None
            observation_bound_target: tuple[Path, PathIdentity] | None = None
            if (
                observation_family == "terminal_resolution"
                and terminal_closed_recovery is not None
                and terminal_closed_recovery.get("predecessor_journal_path")
                is not None
            ):
                retained_path = Path(
                    str(terminal_closed_recovery["predecessor_journal_path"])
                )
                retained_raw, retained_identity = _read_exact_runtime_external_file(
                    retained_path,
                    expected_parent_identity=layout_identities["transactions"],
                    maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
                )
                if (
                    retained_identity
                    != tuple(
                        terminal_closed_recovery[
                            "predecessor_journal_identity"
                        ]
                    )
                    or "sha256:" + hashlib.sha256(retained_raw).hexdigest()
                    != terminal_closed_recovery["predecessor_journal_sha256"]
                ):
                    raise ValueError("runtime_attempt_recovery_retention_mismatch")
                retained_transaction = parse_runtime_transaction_journal_bytes(
                    retained_raw,
                    expected_transaction_id=transaction_id,
                )
                observation_package_sha256 = (
                    "sha256:" + retained_transaction.package_root_sha256
                )
                observation_journal_triplet = (
                    str(retained_path),
                    retained_identity,
                    str(terminal_closed_recovery["predecessor_journal_sha256"]),
                )
                candidate_path = (
                    runtime_root / ".hsconfig" / "staging" / transaction_id
                )
                target_path = runtime_root / retained_transaction.target_path
                if (
                    terminal_closed_recovery.get(
                        "predecessor_candidate_identity"
                    )
                    is not None
                    and not path_lexists(candidate_path)
                    and path_lexists(target_path)
                ):
                    observation_bound_target = (
                        target_path,
                        tuple(
                            terminal_closed_recovery[
                                "predecessor_candidate_identity"
                            ]
                        ),
                    )
            elif (
                observation_family == "terminal_resolution"
                and terminal_closed_recovery is not None
                and terminal_closed_recovery.get(
                    "predecessor_attempt_record_path"
                )
                is not None
            ):
                attempt_path = Path(
                    str(
                        terminal_closed_recovery[
                            "predecessor_attempt_record_path"
                        ]
                    )
                )
                attempt_raw, attempt_identity = _read_exact_runtime_external_file(
                    attempt_path,
                    expected_parent_identity=layout_identities[
                        "attempt_retention"
                    ],
                    maximum_size=RUNTIME_ATTEMPT_RETENTION_MAX_BYTES,
                )
                if (
                    attempt_identity
                    != tuple(
                        terminal_closed_recovery[
                            "predecessor_attempt_record_identity"
                        ]
                    )
                    or "sha256:" + hashlib.sha256(attempt_raw).hexdigest()
                    != terminal_closed_recovery[
                        "predecessor_attempt_record_sha256"
                    ]
                ):
                    raise ValueError("runtime_attempt_recovery_retention_mismatch")
                attempt_record = _runtime_attempt_retention_from_raw(
                    attempt_raw, runtime_root=runtime_root
                )
                if attempt_record.package_root_sha256 is not None:
                    observation_package_sha256 = (
                        attempt_record.package_root_sha256
                    )
            observed = _observe_exact_paired_runtime_attempt(
                runtime_root,
                transaction_id=transaction_id,
                expected_retention_owner_run_id=(
                    expected_retention_owner_run_id
                ),
                expected_package_root_sha256=observation_package_sha256,
                expected_deck_name=expected_deck_name,
                recovery_cursor=(
                    terminal_closed_recovery
                    if observation_family == "terminal_resolution"
                    else None
                ),
                action_bound_candidate_identity=(
                    tuple(
                        terminal_closed_recovery[
                            "predecessor_candidate_identity"
                        ]
                    )
                    if observation_family == "terminal_resolution"
                    and terminal_closed_recovery is not None
                    and terminal_closed_recovery.get(
                        "predecessor_candidate_identity"
                    )
                    is not None
                    else None
                ),
                action_bound_journal_triplet=observation_journal_triplet,
                action_bound_target=observation_bound_target,
                tolerate_bounded_authority_contradiction=(
                    terminal_unknown_projection
                ),
                layout_identities=layout_identities,
            )
            if observation_family == "nonterminal_apply":
                evidence: Mapping[str, Any] = {
                    "apply_recovery": (
                        _initial_apply_recovery_from_observation(
                            observation=observed,
                            runtime_admission=runtime_admission,
                        ).value
                    )
                }
            else:
                terminal_evidence = _initial_terminal_resolution_from_observation(
                    observation=observed,
                    runtime_admission=runtime_admission,
                    closed_recovery=terminal_closed_recovery,
                )
                if (
                    terminal_closed_recovery is not None
                    and terminal_closed_recovery.get(
                        "stable_physical_disposition"
                    )
                    == "NOT_COMMITTED"
                    and terminal_closed_recovery.get("owner_retirement") is None
                    and terminal_closed_recovery.get(
                        "predecessor_candidate_identity"
                    )
                    is not None
                ):
                    terminal_inventory = _reconstruct_runtime_no_commit_inventory_from_pair(
                        lease_pair=lease_pair,
                        transaction_id=transaction_id,
                        runtime_admission=runtime_admission,
                        observed=observed,
                    )
                    terminal_value = _plain_json_value(terminal_evidence.value)
                    terminal_value.pop("content_sha256", None)
                    inventory_path = (
                        binding.session_root
                        / "terminal-resolution-cleanup.json"
                    )
                    staging_path = inventory_path.with_name(
                        f"{inventory_path.name}.staged"
                    )
                    inner_path = staging_path.with_name(
                        f".{staging_path.name}.live-start-atomic.tmp"
                    )
                    terminal_value.update(
                        {
                            "external_file_action": seal_embedded_document(
                                "external_file_action",
                                {
                                    "schema_version": 1,
                                    "action_kind": "commit_bound_terminal_cleanup_inventory",
                                    "action_index": 0,
                                    "stage": "PLANNED",
                                    "final_path": str(inventory_path),
                                    "staging_path": str(staging_path),
                                    "inner_temp_path": str(inner_path),
                                    "parent_identity": binding.session_root_identity,
                                    "predecessor_state": "absent",
                                    "predecessor_identity": None,
                                    "predecessor_size": None,
                                    "predecessor_sha256": None,
                                    "planned_successor_size": terminal_inventory.size,
                                    "planned_successor_sha256": terminal_inventory.sha256,
                                    "staging_identity": None,
                                    "staging_size": None,
                                    "staging_sha256": None,
                                    "commit_mode": "create_no_replace",
                                },
                            ),
                            "cleanup_stage": "PREPARED",
                            "cleanup_inventory_path": str(inventory_path),
                            "cleanup_inventory_parent_identity": binding.session_root_identity,
                            "cleanup_inventory_identity": None,
                            "cleanup_inventory_size": terminal_inventory.size,
                            "cleanup_inventory_sha256": terminal_inventory.sha256,
                            "cleanup_manifest_sha256": terminal_inventory.value[
                                "cleanup_manifest_sha256"
                            ],
                            "cleanup_entry_count": terminal_inventory.value[
                                "cleanup_entry_count"
                            ],
                            "cleanup_cursor": 0,
                            "cleanup_roots": _plain_json_value(
                                terminal_inventory.value["cleanup_roots"]
                            ),
                        }
                    )
                    terminal_evidence = TerminalResolutionEvidence(
                        _seal_terminal_resolution(terminal_value)
                    )
                evidence = {
                    "terminal_resolution_evidence": terminal_evidence.value
                }
            return RuntimeObservationPostcondition(
                action=transaction_id,
                observation_family=observation_family,
                evidence=evidence,
            )

        receipt = _execute_runtime_observation(
            observation_authorization=(
                runtime_observation_authorization
            ),
            observation_family=observation_family,
            read_only_observation=observe,
        )
        if observed is None:
            raise RuntimeError("runtime_attempt_recovery_observation_missing")
        return _paired_runtime_attempt_result(
            observation=observed,
            runtime_admission=runtime_admission,
            observation_family=observation_family,
            runtime_observation_receipt=receipt,
            apply_recovery_step_receipt=None,
            terminal_resolution_step_receipt=None,
            terminal_cleanup_inventory=terminal_inventory,
            status_override=(
                "not_committed"
                if observation_family == "terminal_resolution"
                and terminal_closed_recovery is not None
                and terminal_closed_recovery.get("stable_physical_disposition")
                == "NOT_COMMITTED"
                else None
            ),
        )

    if nonterminal_recovery_authorization is not None:
        recovery = persisted.apply_recovery
        if (
            not isinstance(recovery, Mapping)
            or recovery.get("recovery_stage") != "ACTIVE"
            or recovery.get("run_id") != runtime_admission.run_id
            or recovery.get("apply_attempt_id") != transaction_id
            or recovery.get("apply_invocation_sha256")
            != runtime_admission.apply_invocation_sha256
            or recovery.get("runtime_admission_path")
            != str(runtime_admission.admission_path)
            or tuple(recovery.get("runtime_admission_identity", ()))
            != runtime_admission.admission_identity
            or recovery.get("runtime_admission_sha256")
            != runtime_admission.admission_sha256
            or recovery.get("package_root_sha256")
            != runtime_admission.package_root_sha256
            or recovery.get("runtime_root") != str(runtime_root)
            or tuple(recovery.get("runtime_root_identity", ()))
            != runtime_admission.runtime_root_identity
        ):
            raise ValueError("runtime_attempt_recovery_cursor_mismatch")
        action = getattr(
            getattr(nonterminal_recovery_authorization, "_opaque", None),
            "action",
            "",
        )
        bearer = _require_opaque_carrier(
            nonterminal_recovery_authorization,
            carrier_type=RuntimeAttemptRecoveryAuthorization,
            family="nonterminal_apply_recovery",
            action=action,
            consume=False,
        )
        alternate = _is_unbound_file_action_retirement_alternate(
            recovery=recovery,
            action=action,
        )
        if (
            action not in RUNTIME_APPLY_RECOVERY_ACTIONS
            or (
                recovery.get("expected_action") != action
                and not alternate
            )
            or bearer.session_bearer
            is not binding.session_token._bearer
            or bearer.cursor_sha256 != persisted.content_sha256
        ):
            raise ValueError(
                "runtime_attempt_recovery_nonterminal_capability_changed"
            )
        observed = None

        def advance() -> RuntimeApplyRecoveryPhysicalPostcondition:
            nonlocal observed
            observed = _observe_exact_paired_runtime_attempt(
                runtime_root,
                transaction_id=transaction_id,
                expected_retention_owner_run_id=(
                    expected_retention_owner_run_id
                ),
                expected_package_root_sha256=(
                    expected_package_root_sha256
                ),
                expected_deck_name=expected_deck_name,
                recovery_cursor=recovery,
                tolerate_bounded_authority_contradiction=(
                    action == "observe_unknown"
                ),
                layout_identities=layout_identities,
            )
            legacy_action = action in {
                "promote_legacy_uuid_transaction_temp",
                "retire_legacy_uuid_transaction_temp",
            }
            controller_action = (
                action
                in {
                    "advance_controller_transaction_journal_write",
                    "bind_renamed_target",
                    "commit_ini_journal",
                    "commit_state_journal",
                    "finalize_journal",
                }
            )
            _require_recovery_cursor_observation_matches(
                recovery=recovery,
                observation=observed,
                action=action,
                allow_committed_journal_successor=(
                    controller_action
                    or action == "promote_legacy_uuid_transaction_temp"
                ),
                allow_retired_legacy_temp=legacy_action
                and observed.transaction.legacy_temp_path is None,
            )
            if legacy_action:
                return _execute_bound_legacy_uuid_temp_action(
                    recovery=recovery,
                    action=action,
                )
            if action == "advance_controller_transaction_journal_write":
                return _controller_journal_recovery_postcondition(
                    recovery=recovery,
                    transaction_id=transaction_id,
                    attempt_retention_parent_identity=layout_identities[
                        "attempt_retention"
                    ],
                )
            if action == "retire_unbound_file_action_staging":
                return _retire_unbound_recovery_external_file_action(
                    recovery=recovery,
                )
            if action == "materialize_file_action_staging":
                external = recovery.get("external_file_action")
                if not isinstance(external, Mapping):
                    raise ValueError("runtime_recovery_external_action_invalid")
                if recovery.get("owner_retirement") is not None:
                    return _owner_retirement_materialize_action(
                        recovery=recovery,
                        runtime_root=runtime_root,
                        layout_identities=layout_identities,
                    )
                final_path = Path(str(external.get("final_path")))
                if (
                    recovery.get("install_route") == "prior_owner"
                    and final_path
                    == _runtime_attempt_retention_path(
                        Path(str(recovery["runtime_root"])),
                        str(recovery["apply_attempt_id"]),
                    )
                    and recovery.get("last_apply_receipt_sha256") is None
                ):
                    predecessor_state = external.get("predecessor_state")
                    prior_state = (
                        "ACTIVE"
                        if predecessor_state == "absent"
                        else "PRIOR_OWNER_BOUND"
                        if recovery.get("successor_journal_identity") is not None
                        else "PRIOR_OWNER_PLANNED"
                    )
                    return _materialize_initial_retention_staging(
                        recovery=recovery,
                        payload=_retention_bytes_for_recovery_action(
                            recovery, state=prior_state
                        ),
                        commit_action=(
                            "commit_bound_initial_attempt_record"
                            if prior_state == "ACTIVE"
                            else "commit_bound_prior_owner_attempt_record"
                            if prior_state == "PRIOR_OWNER_BOUND"
                            else "commit_bound_prior_owner_planned_attempt_record"
                        ),
                    )
                if (
                    recovery.get("successor_renamed_target_identity") is not None
                    and (
                        recovery.get("install_route") == "new_target"
                        or final_path
                        != Path(
                            str(recovery.get("planned_journal_successor_path"))
                        )
                    )
                    and (
                        final_path
                        != Path(
                            str(recovery.get("planned_journal_successor_path"))
                        )
                        or recovery.get("planned_journal_successor_phase")
                        in {
                            RuntimeTransactionPhase.INI_COMMITTED.name,
                            RuntimeTransactionPhase.STATE_COMMITTED.name,
                            RuntimeTransactionPhase.FINALIZED.name,
                        }
                    )
                ):
                    payload, commit_action = _suffix_payload_and_commit_action(
                        recovery
                    )
                    return _materialize_initial_retention_staging(
                        recovery=recovery,
                        payload=payload,
                        commit_action=commit_action,
                    )
                if final_path == Path(
                    str(recovery.get("planned_journal_successor_path"))
                ):
                    payload = _planned_journal_bytes_from_recovery(
                        recovery=recovery,
                        package_lease=lease_pair.package_lease,
                        deck_name=expected_deck_name,
                        state_key=Path(
                            str(layout["directories"][4]["path"])
                        ).name,
                    )
                    commit_action = (
                        "bind_renamed_target"
                        if recovery.get("install_route") == "new_target"
                        and recovery.get("successor_renamed_target_identity")
                        is not None
                        else {
                            RuntimeTransactionPhase.INI_COMMITTED.name: (
                                "commit_ini_journal"
                            ),
                            RuntimeTransactionPhase.STATE_COMMITTED.name: (
                                "commit_state_journal"
                            ),
                            RuntimeTransactionPhase.FINALIZED.name: (
                                "finalize_journal"
                            ),
                        }.get(
                            str(
                                recovery.get(
                                    "planned_journal_successor_phase"
                                )
                            ),
                            "advance_controller_transaction_journal_write",
                        )
                    )
                    return _materialize_initial_retention_staging(
                        recovery=recovery,
                        payload=payload,
                        commit_action=commit_action,
                    )
                if (
                    recovery.get("successor_candidate_identity") is not None
                    and recovery.get("successor_journal_identity") is not None
                ):
                    _candidate_manifest_from_pair(
                        package_lease=lease_pair.package_lease,
                        deck_name=expected_deck_name,
                    )
                    payload = _retention_bytes_for_recovery_action(
                        recovery,
                        state="CANDIDATE_BOUND",
                    )
                    return _materialize_initial_retention_staging(
                        recovery=recovery,
                        payload=payload,
                        commit_action="bind_candidate_fence",
                    )
                return _materialize_initial_retention_staging(
                    recovery=recovery,
                )
            if action in {
                "commit_bound_initial_attempt_record",
                "commit_bound_candidate_planned_attempt_record",
                "commit_bound_prior_owner_planned_attempt_record",
                "commit_bound_prior_owner_attempt_record",
            }:
                return _commit_initial_retention_staging(
                    recovery=recovery,
                    action=action,
                    custom_config_parent_identity=layout_identities[
                        "custom_config"
                    ],
                    transactions_parent_identity=layout_identities[
                        "transactions"
                    ],
                )
            if action == "commit_owner_retirement_prepared":
                return _owner_retirement_commit_prepared_action(
                    recovery=recovery,
                    runtime_root=runtime_root,
                    layout_identities=layout_identities,
                )
            if action == "initialize_owner_cleanup_journal":
                return _owner_retirement_initialize_journal_action(
                    recovery=recovery,
                    runtime_root=runtime_root,
                    layout_identities=layout_identities,
                )
            if action == "delete_owner_cleanup_entry":
                return _owner_retirement_delete_entry_action(
                    recovery=recovery,
                    runtime_root=runtime_root,
                    layout_identities=layout_identities,
                )
            if action == "advance_owner_cleanup_journal":
                return _owner_retirement_advance_journal_action(
                    recovery=recovery,
                    runtime_root=runtime_root,
                    layout_identities=layout_identities,
                )
            if action == "retire_owner_target_root":
                return _owner_retirement_retire_root_action(
                    recovery=recovery,
                    runtime_root=runtime_root,
                    layout_identities=layout_identities,
                )
            if action == "commit_owner_retirement_completed":
                return _owner_retirement_commit_completed_action(
                    recovery=recovery,
                    runtime_root=runtime_root,
                    layout_identities=layout_identities,
                )
            if action == "retire_old_owner_journal":
                return _owner_retirement_retire_old_journal_action(
                    recovery=recovery,
                    runtime_root=runtime_root,
                    layout_identities=layout_identities,
                )
            if action == "observe_owner_retirement_completed":
                return _owner_retirement_observe_completed_action(
                    recovery=recovery,
                    runtime_root=runtime_root,
                    layout_identities=layout_identities,
                )
            if action == "bind_created_candidate":
                return _execute_created_candidate_action(
                    recovery=recovery,
                )
            if action == "bind_candidate_fence":
                return _commit_bound_candidate_fence(
                    recovery=recovery,
                    package_lease=lease_pair.package_lease,
                    deck_name=expected_deck_name,
                )
            if action == "materialize_candidate_tree_entry":
                return _materialize_candidate_tree_entry(
                    recovery=recovery,
                    package_lease=lease_pair.package_lease,
                    deck_name=expected_deck_name,
                    transactions_parent_identity=layout_identities[
                        "transactions"
                    ],
                )
            if action == "verify_candidate_tree":
                return _verify_candidate_tree_action(
                    recovery=recovery,
                    package_lease=lease_pair.package_lease,
                    deck_name=expected_deck_name,
                    transactions_parent_identity=layout_identities[
                        "transactions"
                    ],
                )
            if action == "rename_candidate_to_target":
                return _rename_candidate_to_target(
                    recovery=recovery,
                    package_lease=lease_pair.package_lease,
                    deck_name=expected_deck_name,
                    custom_config_parent_identity=layout_identities[
                        "custom_config"
                    ],
                    transactions_parent_identity=layout_identities[
                        "transactions"
                    ],
                )
            if action == "bind_renamed_target":
                return _bind_renamed_target(
                    recovery=recovery,
                    package_lease=lease_pair.package_lease,
                    deck_name=expected_deck_name,
                    transaction_id=transaction_id,
                    custom_config_parent_identity=layout_identities[
                        "custom_config"
                    ],
                )
            if action in {
                "write_deck_config_ini",
                "write_runtime_state",
                "write_last_apply_receipt",
                "finalize_attempt_record",
            }:
                return _write_suffix_artifact(
                    recovery,
                    action=action,
                    transactions_parent_identity=layout_identities[
                        "transactions"
                    ],
                    layout_identities=layout_identities,
                )
            if action in {
                "commit_ini_journal",
                "commit_state_journal",
                "finalize_journal",
            }:
                return _commit_suffix_journal(
                    recovery,
                    action=action,
                    transaction_id=transaction_id,
                    layout_identities=layout_identities,
                    runtime_internal_identity=(
                        runtime_lease_binding.metadata_root_identity
                    ),
                    state_key=_state_key(expected_deck_name),
                )
            if action in {
                "observe_not_committed",
                "observe_committed",
                "observe_pending",
                "observe_unknown",
            }:
                if action == "observe_committed":
                    _require_committed_new_target_parity(
                        recovery=recovery,
                        observation=observed,
                        package_lease=lease_pair.package_lease,
                        deck_name=expected_deck_name,
                        layout_identities=layout_identities,
                        metadata_root_identity=(
                            runtime_lease_binding.metadata_root_identity
                        ),
                    )
                return _runtime_observation_recovery_postcondition(
                    recovery=recovery,
                    action=action,
                    observation=observed,
                    package_lease=lease_pair.package_lease,
                    persisted=persisted,
                    profile_lease=binding.profile_lease,
                    session_root=binding.session_root,
                    lease_pair=lease_pair,
                    runtime_admission=runtime_admission,
                )
            raise ValueError(
                "runtime_paired_recovery_action_not_implemented"
            )

        receipt = _execute_apply_recovery_physical_step(
            recovery_authorization=nonterminal_recovery_authorization,
            action=action,
            physical_action=advance,
        )
        if observed is None:
            raise RuntimeError("runtime_attempt_recovery_observation_missing")
        return _paired_runtime_attempt_result(
            observation=observed,
            runtime_admission=runtime_admission,
            observation_family=None,
            runtime_observation_receipt=None,
            apply_recovery_step_receipt=receipt,
            terminal_resolution_step_receipt=None,
        )

    assert terminal_authorization is not None
    retirement = persisted.terminal_retirement
    if (
        not isinstance(retirement, Mapping)
        or retirement.get("operation") != "release_resolved_terminal"
        or retirement.get("run_id") != runtime_admission.run_id
        or retirement.get("apply_attempt_id") != transaction_id
        or retirement.get("runtime_admission_path")
        != str(runtime_admission.admission_path)
        or tuple(retirement.get("runtime_admission_identity", ()))
        != runtime_admission.admission_identity
        or retirement.get("runtime_admission_sha256")
        != runtime_admission.admission_sha256
        or not isinstance(
            retirement.get("terminal_resolution_evidence"),
            Mapping,
        )
    ):
        raise ValueError("runtime_attempt_terminal_cursor_mismatch")
    terminal_resolution = retirement["terminal_resolution_evidence"]
    terminal_action = getattr(
        getattr(terminal_authorization, "_opaque", None),
        "action",
        "",
    )
    terminal_bearer = _require_opaque_carrier(
        terminal_authorization,
        carrier_type=TerminalRetirementAuthorization,
        family="terminal_retirement",
        action=terminal_action,
        consume=False,
    )
    if (
        terminal_action != "physical_recovery_advanced"
        or terminal_bearer.session_bearer
        is not binding.session_token._bearer
        or terminal_bearer.cursor_sha256 != persisted.content_sha256
    ):
        raise ValueError(
            "runtime_attempt_recovery_terminal_capability_changed"
        )
    registered_terminal_owner_context = (
        _terminal_owner_context_for_authorization(
            terminal_authorization
        )
    )
    observed = None

    def advance_terminal() -> TerminalResolutionPhysicalPostcondition:
        nonlocal observed
        terminal_package_sha256 = expected_package_root_sha256
        terminal_journal_triplet = None
        predecessor_journal_path = terminal_resolution.get(
            "predecessor_journal_path"
        )
        if predecessor_journal_path is not None:
            journal_path = Path(str(predecessor_journal_path))
            journal_raw, journal_identity = _read_exact_runtime_external_file(
                journal_path,
                expected_parent_identity=layout_identities["transactions"],
                maximum_size=MAX_RUNTIME_TRANSACTION_BYTES,
            )
            journal_sha256 = "sha256:" + hashlib.sha256(journal_raw).hexdigest()
            if (
                journal_identity
                != tuple(terminal_resolution["predecessor_journal_identity"])
                or journal_sha256
                != terminal_resolution["predecessor_journal_sha256"]
            ):
                raise ValueError("runtime_attempt_terminal_cursor_mismatch")
            terminal_journal = parse_runtime_transaction_journal_bytes(
                journal_raw,
                expected_transaction_id=transaction_id,
            )
            terminal_package_sha256 = (
                "sha256:" + terminal_journal.package_root_sha256
            )
            terminal_journal_triplet = (
                str(journal_path),
                journal_identity,
                journal_sha256,
            )
        else:
            attempt_path = terminal_resolution.get(
                "predecessor_attempt_record_path"
            )
            if attempt_path is not None:
                attempt_raw, attempt_identity = _read_exact_runtime_external_file(
                    Path(str(attempt_path)),
                    expected_parent_identity=layout_identities[
                        "attempt_retention"
                    ],
                    maximum_size=RUNTIME_ATTEMPT_RETENTION_MAX_BYTES,
                )
                if (
                    attempt_identity
                    != tuple(
                        terminal_resolution[
                            "predecessor_attempt_record_identity"
                        ]
                    )
                    or "sha256:" + hashlib.sha256(attempt_raw).hexdigest()
                    != terminal_resolution[
                        "predecessor_attempt_record_sha256"
                    ]
                ):
                    raise ValueError("runtime_attempt_terminal_cursor_mismatch")
                attempt_record = _runtime_attempt_retention_from_raw(
                    attempt_raw, runtime_root=runtime_root
                )
                if attempt_record.package_root_sha256 is not None:
                    terminal_package_sha256 = (
                        attempt_record.package_root_sha256
                    )
        observed = _observe_exact_paired_runtime_attempt(
            runtime_root,
            transaction_id=transaction_id,
            expected_retention_owner_run_id=(
                expected_retention_owner_run_id
            ),
            expected_package_root_sha256=terminal_package_sha256,
            expected_deck_name=expected_deck_name,
            recovery_cursor=terminal_resolution,
            action_bound_journal_triplet=terminal_journal_triplet,
        )
        terminal_owner = terminal_resolution.get("owner_retirement")
        if isinstance(terminal_owner, Mapping):
            if terminal_resolution.get(
                "predecessor_transaction_temp_path"
            ) is not None:
                raise ValueError(
                    "runtime_terminal_paired_recovery_action_not_implemented"
                )
            terminal_external_raw = terminal_resolution.get(
                "external_file_action"
            )
            terminal_external = (
                terminal_external_raw
                if isinstance(terminal_external_raw, Mapping)
                else None
            )
            nominal_owner_action = _owner_action_for_cursor(
                owner=terminal_owner,
                external=terminal_external,
            )
            owner_recovery = dict(terminal_resolution)
            owner_recovery.update(
                {
                    "runtime_root": str(runtime_root),
                    "runtime_root_identity": (
                        runtime_admission.runtime_root_identity
                    ),
                    "expected_action": nominal_owner_action,
                }
            )
            terminal_owner_context = registered_terminal_owner_context
            bound_owner_action = (
                terminal_owner_context.get("owner_action")
                if isinstance(terminal_owner_context, Mapping)
                else None
            )
            alternate = (
                nominal_owner_action
                == "materialize_file_action_staging"
                and isinstance(bound_owner_action, str)
                and _is_unbound_file_action_retirement_alternate(
                    recovery=owner_recovery,
                    action=bound_owner_action,
                )
                and terminal_external is not None
                and (
                    path_lexists(
                        Path(str(terminal_external["staging_path"]))
                    )
                    or path_lexists(
                        Path(str(terminal_external["inner_temp_path"]))
                    )
                )
            )
            if (
                not isinstance(bound_owner_action, str)
                or (
                    bound_owner_action != nominal_owner_action
                    and not alternate
                )
            ):
                raise ValueError(
                    "runtime_attempt_terminal_owner_capability_changed"
                )
            owner_action = bound_owner_action
            _require_recovery_cursor_observation_matches(
                recovery=owner_recovery,
                observation=observed,
                action=owner_action,
                allow_committed_journal_successor=False,
                allow_retired_legacy_temp=False,
            )
            return _execute_terminal_owner_retirement_action(
                action=owner_action,
                recovery=owner_recovery,
                terminal_retirement=retirement,
                runtime_root=runtime_root,
                layout_identities=layout_identities,
                observation_status=observed.status,
            )
        if (
            terminal_resolution.get("external_file_action") is not None
            or terminal_resolution.get(
                "predecessor_transaction_temp_path"
            )
            is not None
        ):
            raise ValueError(
                "runtime_terminal_paired_recovery_action_not_implemented"
            )
        next_disposition = {
            "not_committed": "NOT_COMMITTED",
            "committed": "COMMITTED",
            "committed_receipt_pending": (
                "COMMITTED_RECOVERY_PENDING"
            ),
            "unknown": "UNKNOWN_REQUIRES_RECOVERY",
        }[observed.status]
        if (
            terminal_resolution.get("resolved_physical_disposition")
            == "NOT_COMMITTED"
        ):
            next_disposition = "NOT_COMMITTED"
        if (
            terminal_resolution.get("resolved_physical_disposition")
            == next_disposition
        ):
            raise ValueError("runtime_terminal_observation_not_advanced")
        next_resolution = _plain_json_value(terminal_resolution)
        next_retirement = _plain_json_value(retirement)
        if not isinstance(next_resolution, dict) or not isinstance(
            next_retirement,
            dict,
        ):
            raise ValueError("runtime_attempt_terminal_cursor_mismatch")
        next_resolution["resolved_physical_disposition"] = (
            next_disposition
        )
        next_retirement.pop("content_sha256", None)
        next_retirement["terminal_resolution_evidence"] = (
            _plain_json_value(_seal_terminal_resolution(next_resolution))
        )
        successor = seal_embedded_document(
            "terminal_retirement",
            next_retirement,
        )
        return TerminalResolutionPhysicalPostcondition(
            action=terminal_action,
            evidence={"terminal_retirement": successor},
        )

    terminal_receipt = _execute_terminal_resolution_physical_step(
        terminal_authorization=terminal_authorization,
        action=terminal_action,
        physical_action=advance_terminal,
    )
    if observed is None:
        raise RuntimeError("runtime_attempt_recovery_observation_missing")
    return _paired_runtime_attempt_result(
        observation=observed,
        runtime_admission=runtime_admission,
        observation_family=None,
        runtime_observation_receipt=None,
        apply_recovery_step_receipt=None,
        terminal_resolution_step_receipt=terminal_receipt,
    )


def _install_locked(
    plan: RuntimeInstallPlan,
    spec: _RuntimePackageSpec,
    source_snapshot: BoundedFilesystemPackageView | None,
    current_ini: DeckConfigSnapshot,
    fault_hook: FaultHook,
    transaction_id: str,
    *,
    retain_finalized_nonowner_journal: bool = False,
) -> RuntimeInstallResult:
    if source_snapshot is None:
        raise ValueError("runtime_install_source_not_current")
    runtime_transaction_journal_path(plan.runtime_root, transaction_id)
    next_ini = render_deck_config(
        current_ini,
        deck_name=plan.deck_name,
        config_dir=plan.versioned_config_dir,
    )
    next_ini_sha256 = hashlib.sha256(next_ini).hexdigest()
    state_key = _state_key(plan.deck_name)
    journal = RuntimeTransactionJournal(
        schema_version=1,
        transaction_id=transaction_id,
        deck_name=plan.deck_name,
        source_manifest_sha256=_source_manifest_sha256(plan),
        state_key=state_key,
        logical_config_dir=plan.logical_config_dir,
        package_root_sha256=plan.package_root_sha256,
        candidate_path=f".hsconfig/staging/{transaction_id}",
        target_path=f"CustomConfig/{plan.versioned_config_dir}",
        candidate_identity=None,
        target_identity=None,
        owns_target=False,
        previous_config_dir=current_ini.selected_config_dir,
        next_config_dir=plan.versioned_config_dir,
        previous_ini_sha256=current_ini.sha256,
        next_ini_sha256=next_ini_sha256,
        phase=RuntimeTransactionPhase.PREPARED,
    )
    journal_path = runtime_transaction_journal_path(
        plan.runtime_root,
        transaction_id,
    )
    _write_journal(journal_path, journal)
    candidate = plan.runtime_root / journal.candidate_path
    candidate_identity = secure_create_directory(
        candidate,
        expected_parent_identity=path_identity(candidate.parent),
    )
    journal = replace(journal, candidate_identity=candidate_identity)
    _write_journal(journal_path, journal)

    _copy_runtime_files(candidate, spec, source_snapshot)
    journal = replace(
        journal,
        phase=RuntimeTransactionPhase.RUNTIME_STAGED,
    )
    _write_journal(journal_path, journal)
    fault_hook("after_runtime_staging_copy")

    _verify_runtime_tree_against_spec(candidate, spec, source_snapshot)
    journal = replace(
        journal,
        phase=RuntimeTransactionPhase.RUNTIME_VERIFIED,
    )
    _write_journal(journal_path, journal)
    fault_hook("after_runtime_staging_verify")

    target = plan.runtime_root / journal.target_path
    if path_lexists(target):
        target_identity = _plain_directory_identity(target)
        try:
            _verify_runtime_tree_against_spec(target, spec, source_snapshot)
            _require_unambiguous_owner(
                plan.runtime_root,
                target,
                plan.package_root_sha256,
            )
        except Exception as error:
            raise RuntimeError("runtime_digest_target_conflict") from error
        _remove_owned_tree(candidate, candidate_identity)
        journal = replace(
            journal,
            target_identity=target_identity,
            owns_target=False,
        )
        _write_journal(journal_path, journal)
    else:
        secure_replace(
            candidate,
            target,
            expected_source_identity=candidate_identity,
            expected_source_parent_identity=path_identity(candidate.parent),
            expected_target_parent_identity=path_identity(target.parent),
            expected_target_absent=True,
        )
        fault_hook("after_runtime_revision_rename")
        target_identity = _plain_directory_identity(target)
        if target_identity != candidate_identity:
            raise RuntimeError("runtime_target_identity_changed")
        journal = replace(
            journal,
            target_identity=target_identity,
            owns_target=True,
        )
        _write_journal(journal_path, journal)

    _verify_runtime_tree_against_spec(target, spec, source_snapshot)
    fault_hook("before_ini_compare_and_swap")
    committed_ini_sha256 = replace_deck_config_if_unchanged(
        current_ini,
        next_ini,
    )
    fault_hook("after_ini_compare_and_swap")
    committed_ini = _read_actual_ini(plan)
    if (
        committed_ini.selected_config_dir != plan.versioned_config_dir
        or committed_ini.sha256 != committed_ini_sha256
        or committed_ini_sha256 != next_ini_sha256
    ):
        raise RuntimeError("runtime_ini_commit_verification_failed")
    _verify_runtime_tree_against_spec(target, spec, source_snapshot)
    journal = replace(
        journal,
        target_identity=_plain_directory_identity(target),
        phase=RuntimeTransactionPhase.INI_COMMITTED,
    )
    _write_journal(journal_path, journal)

    fault_hook("before_state_write")
    _write_selected_state(
        plan.runtime_root,
        journal,
        committed_ini_sha256,
    )
    fault_hook("after_state_write")
    journal = replace(
        journal,
        phase=RuntimeTransactionPhase.STATE_COMMITTED,
    )
    _write_journal(journal_path, journal)

    receipt_path = _receipt_path(plan.runtime_root, state_key)
    try:
        fault_hook("before_receipt_write")
        _write_receipt(
            plan.runtime_root,
            _receipt_payload(journal, committed_ini_sha256),
            fault_hook=fault_hook,
        )
    except Exception:
        return RuntimeInstallResult(
            status="committed_receipt_pending",
            config_dir=plan.versioned_config_dir,
            package_root_sha256=plan.package_root_sha256,
            previous_config_dir=current_ini.selected_config_dir,
            receipt_path=None,
        )

    journal = replace(journal, phase=RuntimeTransactionPhase.FINALIZED)
    _write_journal(journal_path, journal)
    fault_hook("before_old_revision_cleanup")
    _cleanup_old_revision(
        plan.runtime_root,
        journal,
        fault_hook=fault_hook,
        preservation_index=_refresh_runtime_attempt_preservation_index(
            plan.runtime_root
        ),
    )
    if not journal.owns_target and not retain_finalized_nonowner_journal:
        _delete_journal(journal_path)
    return RuntimeInstallResult(
        status="applied",
        config_dir=plan.versioned_config_dir,
        package_root_sha256=plan.package_root_sha256,
        previous_config_dir=current_ini.selected_config_dir,
        receipt_path=receipt_path,
    )


def _finalized_noop_journal(
    *,
    plan: RuntimeInstallPlan,
    current_ini: DeckConfigSnapshot,
    transaction_id: str,
    target_identity: tuple[int, int, int] | None,
) -> RuntimeTransactionJournal:
    if (
        current_ini.selected_config_dir != plan.versioned_config_dir
        or current_ini.sha256 is None
        or target_identity is None
    ):
        raise RuntimeError("runtime_already_current_journal_invalid")
    return RuntimeTransactionJournal(
        schema_version=1,
        transaction_id=transaction_id,
        deck_name=plan.deck_name,
        source_manifest_sha256=_source_manifest_sha256(plan),
        state_key=_state_key(plan.deck_name),
        logical_config_dir=plan.logical_config_dir,
        package_root_sha256=plan.package_root_sha256,
        candidate_path=f".hsconfig/staging/{transaction_id}",
        target_path=f"CustomConfig/{plan.versioned_config_dir}",
        candidate_identity=None,
        target_identity=target_identity,
        owns_target=False,
        previous_config_dir=current_ini.selected_config_dir,
        next_config_dir=plan.versioned_config_dir,
        previous_ini_sha256=current_ini.sha256,
        next_ini_sha256=current_ini.sha256,
        phase=RuntimeTransactionPhase.FINALIZED,
    )


def _validate_leased_source(
    plan: RuntimeInstallPlan,
    lease: PackageInputLease,
) -> _RuntimePackageSpec:
    if (
        lease.publication is None
        or lease.snapshot is None
        or lease.content_root_sha256 != _source_manifest_sha256(plan)
        or lease.package_root != plan.source_package_root
        or lease.package_root.parent != plan.source_revision_root
    ):
        raise ValueError("runtime_install_source_not_current")
    manifest = verify_tree_manifest(lease.snapshot)
    spec = _runtime_package_spec(manifest)
    if (
        manifest.content_root_sha256 != _source_manifest_sha256(plan)
        or spec.deck_name != plan.deck_name
        or spec.logical_config_dir != plan.logical_config_dir
        or spec.package_root_sha256 != plan.package_root_sha256
        or plan.versioned_config_dir
        != f"{spec.logical_config_dir}--sha256-{spec.package_root_sha256}"
    ):
        raise ValueError("runtime_install_source_not_current")
    return spec


def _source_manifest_sha256(plan: RuntimeInstallPlan) -> str:
    name = plan.source_revision_root.name
    prefix = "sha256-"
    if not name.startswith(prefix) or not _SHA256.fullmatch(name[len(prefix) :]):
        raise ValueError("runtime_install_plan_invalid")
    return name[len(prefix) :]


def _runtime_package_spec(
    manifest: TreeManifest | None,
) -> _RuntimePackageSpec:
    if manifest is None:
        raise ValueError("runtime_install_source_not_current")
    prefix = "04_package/CustomConfig/"
    selected: list[tuple[ManifestEntry, str, str]] = []
    logical_names: set[str] = set()
    for entry in manifest.entries:
        if not entry.relative_path.startswith(prefix):
            continue
        suffix = entry.relative_path[len(prefix) :]
        if "/" not in suffix:
            raise ValueError("runtime_package_manifest_invalid")
        logical, relative = suffix.split("/", 1)
        if not logical or not relative:
            raise ValueError("runtime_package_manifest_invalid")
        logical_names.add(logical)
        selected.append((entry, logical, relative))
    if len(logical_names) != 1 or not selected:
        raise ValueError("runtime_package_manifest_invalid")
    logical = next(iter(logical_names))
    if not _valid_component(logical):
        raise ValueError("runtime_package_manifest_invalid")
    files = tuple(
        _RuntimeFile(
            relative_path=relative,
            size=entry.size,
            sha256=entry.sha256,
            source_path=entry.relative_path,
        )
        for entry, row_logical, relative in selected
        if row_logical == logical
    )
    paths = tuple(row.relative_path for row in files)
    if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
        raise ValueError("runtime_package_manifest_invalid")
    records = b"".join(
        (f"{row.relative_path}\0{row.size}\0{row.sha256}\n").encode("utf-8")
        for row in files
    )
    return _RuntimePackageSpec(
        deck_name=manifest.deck_name,
        logical_config_dir=logical,
        package_root_sha256=hashlib.sha256(records).hexdigest(),
        files=files,
    )


def _ensure_runtime_layout(runtime_root: Path) -> None:
    require_plain_directory(runtime_root)
    _ensure_directory(runtime_root / "CustomConfig")
    hsconfig = runtime_root / ".hsconfig"
    _ensure_directory(hsconfig)
    _ensure_directory(hsconfig / "transactions")
    _ensure_directory(hsconfig / "staging")
    _ensure_directory(hsconfig / "receipts")


def _ensure_directory(path: Path) -> None:
    target = Path(path)
    if path_lexists(target):
        require_plain_directory(target)
        return
    require_plain_directory(target.parent)
    try:
        secure_create_directory(
            target,
            expected_parent_identity=path_identity(target.parent),
        )
    except FileExistsError:
        require_plain_directory(target)


def _copy_runtime_files(
    candidate: Path,
    spec: _RuntimePackageSpec,
    source_snapshot: BoundedFilesystemPackageView,
) -> None:
    directories = sorted(
        {
            "/".join(row.relative_path.split("/")[:index])
            for row in spec.files
            for index in range(1, len(row.relative_path.split("/")))
        },
        key=lambda value: (value.count("/"), value),
    )
    for relative in directories:
        _ensure_directory(candidate / Path(relative))
    for row in spec.files:
        content = source_snapshot.read_bytes(row.source_path)
        if (
            len(content) != row.size
            or hashlib.sha256(content).hexdigest() != row.sha256
        ):
            raise ValueError("runtime_install_source_not_current")
        target = candidate / Path(row.relative_path)
        descriptor = secure_open_file_descriptor(
            target,
            create=True,
            write=True,
            expected_parent_identity=path_identity(target.parent),
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = -1
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
                status = os.fstat(handle.fileno())
                if (
                    not stat.S_ISREG(status.st_mode)
                    or status_is_reparse(status)
                    or status.st_nlink != 1
                    or status.st_size != row.size
                ):
                    raise RuntimeError("runtime_staging_write_failed")
        finally:
            if descriptor >= 0:
                os.close(descriptor)


def _verify_runtime_tree_against_spec(
    root: Path,
    spec: _RuntimePackageSpec,
    source_snapshot: BoundedFilesystemPackageView | None,
) -> None:
    try:
        snapshot = snapshot_bounded_filesystem_package(root)
        expected_names = tuple(row.relative_path for row in spec.files)
        if snapshot.file_names() != expected_names:
            raise ValueError("membership")
        expected_directories = sorted(
            {
                "/".join(path.split("/")[:index])
                for path in expected_names
                for index in range(1, len(path.split("/")))
            }
        )
        if snapshot.directory_names != tuple(expected_directories):
            raise ValueError("directories")
        for row in spec.files:
            content = snapshot.read_bytes(row.relative_path)
            if (
                len(content) != row.size
                or hashlib.sha256(content).hexdigest() != row.sha256
                or (
                    source_snapshot is not None
                    and content != source_snapshot.read_bytes(row.source_path)
                )
            ):
                raise ValueError("content")
    except Exception as error:
        raise RuntimeError("runtime_package_verification_failed") from error


def _verify_runtime_tree_digest(root: Path, expected_digest: str) -> None:
    try:
        snapshot = snapshot_bounded_filesystem_package(root)
        records = b"".join(
            (f"{name}\0{len(content)}\0{hashlib.sha256(content).hexdigest()}\n").encode(
                "utf-8"
            )
            for name in snapshot.file_names()
            for content in (snapshot.read_bytes(name),)
        )
        if hashlib.sha256(records).hexdigest() != expected_digest:
            raise ValueError("digest")
    except Exception as error:
        raise RuntimeError("runtime_package_verification_failed") from error


def _read_actual_ini(plan: RuntimeInstallPlan) -> DeckConfigSnapshot:
    return read_deck_config(
        plan.runtime_root / "CustomConfig" / "deck_config.ini",
        deck_name=plan.deck_name,
    )


def _write_journal(
    path: Path,
    journal: RuntimeTransactionJournal,
) -> None:
    write_runtime_transaction_journal(path, journal)
    if read_runtime_transaction_journal(path) != journal:
        raise RuntimeError("runtime_transaction_journal_commit_failed")


def _recover_locked(runtime_root: Path) -> _RecoveryOutcome:
    repaired = False
    preservation_index = _refresh_runtime_attempt_preservation_index(runtime_root)
    journals = (
        load_runtime_transaction_journals(
            runtime_root,
            protected_transaction_ids=preservation_index.transaction_ids,
        )
        if preservation_index.transaction_ids
        else load_runtime_transaction_journals(runtime_root)
    )
    _reject_unprotected_journal_target_collisions(
        journals,
        preservation_index,
    )
    if preservation_index.candidate_identities:
        _validate_recovery_ownership(
            runtime_root,
            journals,
            protected_candidates=preservation_index.candidate_identities,
        )
    else:
        _validate_recovery_ownership(runtime_root, journals)
    for original in journals:
        journal = original
        journal_path = runtime_transaction_journal_path(
            runtime_root,
            journal.transaction_id,
        )
        candidate = runtime_root / journal.candidate_path
        target = runtime_root / journal.target_path
        candidate_identity = _directory_identity_or_none(candidate)
        target_identity = _directory_identity_or_none(target)
        if (
            candidate_identity is not None
            and journal.candidate_identity != candidate_identity
        ):
            raise RuntimeError("runtime_recovery_ownership_ambiguous")
        if journal.cleanup_started:
            if _resume_owned_cleanup(runtime_root, journal):
                repaired = True
            continue
        rename_window = (
            target_identity is not None
            and journal.target_identity is None
            and journal.candidate_identity == target_identity
        )
        if (
            journal.target_identity is not None
            and target_identity != journal.target_identity
        ):
            raise RuntimeError("runtime_recovery_ownership_ambiguous")
        if rename_window:
            journal = replace(
                journal,
                target_identity=target_identity,
                owns_target=True,
            )
            _write_journal(journal_path, journal)
            repaired = True

        ini = read_deck_config(
            runtime_root / "CustomConfig" / "deck_config.ini",
            deck_name=journal.deck_name,
        )
        selected = _same_config_dir(
            ini.selected_config_dir,
            journal.next_config_dir,
        )
        if selected:
            if target_identity is None or ini.sha256 != journal.next_ini_sha256:
                raise RuntimeError("runtime_recovery_committed_target_invalid")
            _verify_runtime_tree_digest(target, journal.package_root_sha256)
            if journal.phase in {
                RuntimeTransactionPhase.PREPARED,
                RuntimeTransactionPhase.RUNTIME_STAGED,
                RuntimeTransactionPhase.RUNTIME_VERIFIED,
            }:
                journal = replace(
                    journal,
                    target_identity=target_identity,
                    owns_target=(
                        journal.owns_target
                        or journal.candidate_identity == target_identity
                    ),
                    phase=RuntimeTransactionPhase.INI_COMMITTED,
                )
                _write_journal(journal_path, journal)
                repaired = True
            if candidate_identity is not None:
                _remove_owned_tree(candidate, candidate_identity)
                repaired = True
            state_before = read_runtime_state(runtime_root)
            expected_state = _write_selected_state(
                runtime_root,
                journal,
                ini.sha256,
            )
            if state_before != expected_state:
                repaired = True
            if journal.phase == RuntimeTransactionPhase.INI_COMMITTED:
                journal = replace(
                    journal,
                    phase=RuntimeTransactionPhase.STATE_COMMITTED,
                )
                _write_journal(journal_path, journal)
                repaired = True
            receipt = _receipt_path(runtime_root, journal.state_key)
            expected_receipt = _receipt_bytes(_receipt_payload(journal, ini.sha256))
            if _plain_file_bytes_or_none(receipt) != expected_receipt:
                _write_receipt(
                    runtime_root,
                    _receipt_payload(journal, ini.sha256),
                )
                repaired = True
            if journal.phase == RuntimeTransactionPhase.STATE_COMMITTED:
                journal = replace(
                    journal,
                    phase=RuntimeTransactionPhase.FINALIZED,
                )
                _write_journal(journal_path, journal)
                repaired = True
            _cleanup_old_revision(
                runtime_root,
                journal,
                preservation_index=preservation_index,
            )
            if not journal.owns_target:
                _delete_journal(journal_path)
                repaired = True
            del expected_state
            continue

        if journal.phase in {
            RuntimeTransactionPhase.INI_COMMITTED,
            RuntimeTransactionPhase.STATE_COMMITTED,
        }:
            raise RuntimeError("runtime_recovery_ini_conflict")
        if candidate_identity is not None:
            _remove_owned_tree(candidate, candidate_identity)
            repaired = True
        active = _active_config_dirs(runtime_root)
        if (
            target_identity is not None
            and (journal.owns_target or rename_window)
            and active is not None
            and journal.next_config_dir.casefold() not in active
        ):
            _verify_runtime_tree_digest(target, journal.package_root_sha256)
            _remove_owned_tree(target, target_identity)
            repaired = True
        if journal.phase != RuntimeTransactionPhase.FINALIZED:
            _delete_journal(journal_path)
            repaired = True

    state = read_runtime_state(runtime_root)
    _verify_active_state_targets(runtime_root, state)
    return _RecoveryOutcome(state=state, repaired=repaired)


def _validate_recovery_ownership(
    runtime_root: Path,
    journals: tuple[RuntimeTransactionJournal, ...],
    *,
    protected_candidates: Mapping[str, PathIdentity] | None = None,
) -> None:
    retained_candidates = (
        {} if protected_candidates is None else dict(protected_candidates)
    )
    owned_targets: dict[str, list[RuntimeTransactionJournal]] = {}
    by_transaction_id = {journal.transaction_id: journal for journal in journals}
    for journal in journals:
        if journal.owns_target:
            owned_targets.setdefault(
                journal.target_path.casefold(),
                [],
            ).append(journal)
    if any(len(owners) != 1 for owners in owned_targets.values()):
        raise RuntimeError("runtime_recovery_ownership_ambiguous")

    staging = runtime_root / ".hsconfig" / "staging"
    count = 0
    with os.scandir(staging) as iterator:
        for entry in iterator:
            count += 1
            if count > 1024:
                raise RuntimeError("runtime_recovery_ownership_ambiguous")
            path = Path(entry.path)
            status = path.lstat()
            journal = by_transaction_id.get(entry.name)
            retained_identity = retained_candidates.get(entry.name)
            if (
                journal is None
                and retained_identity is not None
                and not status_is_reparse(status)
                and stat.S_ISDIR(status.st_mode)
                and path_identity_from_status(status) == retained_identity
            ):
                continue
            if (
                journal is None
                or journal.candidate_path != f".hsconfig/staging/{entry.name}"
                or journal.candidate_identity is None
                or status_is_reparse(status)
                or not stat.S_ISDIR(status.st_mode)
                or path_identity_from_status(status) != journal.candidate_identity
            ):
                raise RuntimeError("runtime_recovery_ownership_ambiguous")


def _write_selected_state(
    runtime_root: Path,
    journal: RuntimeTransactionJournal,
    ini_sha256: str | None,
) -> RuntimeState:
    if ini_sha256 is None:
        raise RuntimeError("runtime_ini_commit_verification_failed")
    current = read_runtime_state(runtime_root)
    decks = [] if current is None else list(current.decks)
    next_deck = RuntimeDeckState(
        state_key=journal.state_key,
        deck_name=journal.deck_name,
        config_dir=journal.next_config_dir,
        package_root_sha256=journal.package_root_sha256,
        ini_sha256=ini_sha256,
    )
    decks = [
        deck
        for deck in decks
        if deck.state_key.casefold() != journal.state_key.casefold()
        and deck.deck_name.casefold() != journal.deck_name.casefold()
    ]
    decks.append(next_deck)
    state = RuntimeState(1, tuple(decks))
    content = serialize_runtime_state(state)
    state_path = runtime_root / ".hsconfig" / "state.json"
    if _plain_file_bytes_or_none(state_path) != content:
        atomic_write_bytes(state_path, content)
    if read_runtime_state(runtime_root) != state:
        raise RuntimeError("runtime_state_commit_verification_failed")
    return state


def _repair_selected_state_without_journal(
    plan: RuntimeInstallPlan,
    ini: DeckConfigSnapshot,
) -> RuntimeState:
    owner = _require_unambiguous_owner(
        plan.runtime_root,
        plan.runtime_root / "CustomConfig" / plan.versioned_config_dir,
        plan.package_root_sha256,
    )
    return _write_selected_state(plan.runtime_root, owner, ini.sha256)


def _receipt_payload(
    journal: RuntimeTransactionJournal,
    ini_sha256: str,
) -> dict[str, object]:
    return {
        "schema_version": _RECEIPT_SCHEMA_VERSION,
        "state_key": journal.state_key,
        "deck_name": journal.deck_name,
        "logical_config_dir": journal.logical_config_dir,
        "config_dir": journal.next_config_dir,
        "package_root_sha256": journal.package_root_sha256,
        "source_manifest_sha256": journal.source_manifest_sha256,
        "ini_sha256": ini_sha256,
    }


def _receipt_payload_for_plan(
    plan: RuntimeInstallPlan,
    ini_sha256: str | None,
    state_key: str,
) -> dict[str, object]:
    if ini_sha256 is None:
        raise RuntimeError("runtime_ini_commit_verification_failed")
    return {
        "schema_version": _RECEIPT_SCHEMA_VERSION,
        "state_key": state_key,
        "deck_name": plan.deck_name,
        "logical_config_dir": plan.logical_config_dir,
        "config_dir": plan.versioned_config_dir,
        "package_root_sha256": plan.package_root_sha256,
        "source_manifest_sha256": _source_manifest_sha256(plan),
        "ini_sha256": ini_sha256,
    }


def _receipt_bytes(payload: dict[str, object]) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _write_receipt(
    runtime_root: Path,
    payload: dict[str, object],
    *,
    fault_hook: FaultHook = no_fault,
) -> Path:
    state_key = payload["state_key"]
    if not isinstance(state_key, str) or not _valid_component(state_key):
        raise ValueError("runtime_receipt_invalid")
    directory = runtime_root / ".hsconfig" / "receipts" / state_key
    _ensure_directory(directory)
    path = directory / "last_apply_receipt.json"
    content = _receipt_bytes(payload)

    def receipt_atomic_fault(stage: str) -> None:
        if stage == "after_replace":
            fault_hook("during_receipt_write")

    atomic_write_bytes(path, content, fault_hook=receipt_atomic_fault)
    if _plain_file_bytes_or_none(path) != content:
        raise RuntimeError("runtime_receipt_commit_verification_failed")
    return path


def _receipt_path(runtime_root: Path, state_key: str) -> Path:
    return (
        runtime_root / ".hsconfig" / "receipts" / state_key / "last_apply_receipt.json"
    )


def _cleanup_old_revision(
    runtime_root: Path,
    journal: RuntimeTransactionJournal,
    *,
    fault_hook: FaultHook = no_fault,
    preservation_index: _RuntimeAttemptPreservationIndex | None = None,
) -> None:
    hook_called = False

    def cleanup_fault(stage: str) -> None:
        nonlocal hook_called
        hook_called = True
        fault_hook(stage)

    try:
        old_name = journal.previous_config_dir
        if old_name is None or _same_config_dir(
            old_name,
            journal.next_config_dir,
        ):
            return
        active = _active_config_dirs(runtime_root)
        if active is None or old_name.casefold() in active:
            return
        old_relative = f"CustomConfig/{old_name}"
        if preservation_index is not None:
            protected_identity = preservation_index.target_identities.get(
                old_relative.casefold()
            )
            if protected_identity is not None:
                try:
                    _observe_retained_directory(
                        runtime_root / old_relative,
                        expected_identity=protected_identity,
                        expected_parent_identity=None,
                    )
                except ValueError as error:
                    raise RuntimeError(
                        "runtime_recovery_ownership_ambiguous"
                    ) from error
                return
        owners = [
            candidate
            for candidate in (
                load_runtime_transaction_journals(
                    runtime_root,
                    protected_transaction_ids=preservation_index.transaction_ids,
                )
                if preservation_index is not None
                and preservation_index.transaction_ids
                else load_runtime_transaction_journals(runtime_root)
            )
            if candidate.phase == RuntimeTransactionPhase.FINALIZED
            and candidate.owns_target
            and candidate.target_path.casefold()
            == f"CustomConfig/{old_name}".casefold()
        ]
        if len(owners) != 1:
            return
        owner = owners[0]
        old_path = runtime_root / owner.target_path
        if not path_lexists(old_path):
            _delete_journal(
                runtime_transaction_journal_path(
                    runtime_root,
                    owner.transaction_id,
                )
            )
            return
        old_identity = _plain_directory_identity(old_path)
        if owner.target_identity != old_identity:
            raise RuntimeError("runtime_recovery_ownership_ambiguous")
        if owner.cleanup_started:
            owner_tombstone = (
                runtime_root
                / ".hsconfig"
                / "owner-retirements"
                / f"{owner.transaction_id}.json"
            )
            if path_lexists(owner_tombstone):
                raise RuntimeError("runtime_owner_retirement_recovery_required")
            _resume_owned_cleanup(
                runtime_root,
                owner,
                fault_hook=cleanup_fault,
            )
            return
        _verify_runtime_tree_digest(old_path, owner.package_root_sha256)
        cleanup = _prepare_cleanup_journal(runtime_root, owner, old_path)
        if cleanup is None:
            return
        _resume_owned_cleanup(
            runtime_root,
            cleanup,
            fault_hook=cleanup_fault,
        )
    finally:
        if not hook_called:
            fault_hook("during_old_revision_cleanup")


def _prepare_cleanup_journal(
    runtime_root: Path,
    owner: RuntimeTransactionJournal,
    target: Path,
) -> RuntimeTransactionJournal | None:
    snapshot = snapshot_bounded_filesystem_package(target)
    file_names = sorted(
        snapshot.file_names(),
        key=lambda value: (value.count("/"), value),
        reverse=True,
    )
    directory_names = sorted(
        snapshot.directory_names,
        key=lambda value: (value.count("/"), value),
        reverse=True,
    )
    entries = tuple(
        RuntimeCleanupEntry(
            kind=kind,
            relative_path=name,
            identity=path_identity(target / Path(name)),
        )
        for kind, names in (
            ("file", file_names),
            ("directory", directory_names),
        )
        for name in names
    )
    cleanup = replace(
        owner,
        cleanup_started=True,
        cleanup_entries=entries,
        cleanup_cursor=0,
    )
    try:
        runtime_transaction_journal_bytes(cleanup)
    except ValueError:
        return None
    _write_journal(
        runtime_transaction_journal_path(
            runtime_root,
            cleanup.transaction_id,
        ),
        cleanup,
    )
    return cleanup


def _resume_owned_cleanup(
    runtime_root: Path,
    journal: RuntimeTransactionJournal,
    *,
    fault_hook: FaultHook = no_fault,
) -> bool:
    if not journal.cleanup_started or journal.target_identity is None:
        raise RuntimeError("runtime_recovery_ownership_ambiguous")
    owner_tombstone = (
        runtime_root
        / ".hsconfig"
        / "owner-retirements"
        / f"{journal.transaction_id}.json"
    )
    if path_lexists(owner_tombstone):
        raise RuntimeError("runtime_owner_retirement_recovery_required")
    journal_path = runtime_transaction_journal_path(
        runtime_root,
        journal.transaction_id,
    )
    target = runtime_root / journal.target_path
    active = _active_config_dirs(runtime_root)
    if active is None or journal.next_config_dir.casefold() in active:
        return False
    if not path_lexists(target):
        _delete_journal(journal_path)
        return True
    if _plain_directory_identity(target) != journal.target_identity:
        raise RuntimeError("runtime_recovery_ownership_ambiguous")
    _validate_remaining_cleanup_inventory(target, journal)
    current = journal
    for index in range(journal.cleanup_cursor, len(journal.cleanup_entries)):
        entry = journal.cleanup_entries[index]
        path = target / Path(entry.relative_path)
        if path_lexists(path):
            status = path.lstat()
            if (
                status_is_reparse(status)
                or path_identity_from_status(status) != entry.identity
                or (
                    entry.kind == "file"
                    and (not stat.S_ISREG(status.st_mode) or status.st_nlink != 1)
                )
                or (entry.kind == "directory" and not stat.S_ISDIR(status.st_mode))
            ):
                raise RuntimeError("runtime_recovery_ownership_ambiguous")
            if entry.kind == "file":
                secure_unlink(
                    path,
                    expected_identity=entry.identity,
                    expected_parent_identity=path_identity(path.parent),
                )
            else:
                secure_rmdir(
                    path,
                    expected_identity=entry.identity,
                    expected_parent_identity=path_identity(path.parent),
                )
            fault_hook("during_old_revision_cleanup")
        current = replace(current, cleanup_cursor=index + 1)
        _write_journal(journal_path, current)

    with os.scandir(target) as iterator:
        if any(iterator):
            raise RuntimeError("runtime_recovery_ownership_ambiguous")
    secure_rmdir(
        target,
        expected_identity=journal.target_identity,
        expected_parent_identity=path_identity(target.parent),
    )
    fault_hook("during_old_revision_cleanup")
    _delete_journal(journal_path)
    return True


def _validate_remaining_cleanup_inventory(
    target: Path,
    journal: RuntimeTransactionJournal,
) -> None:
    snapshot = snapshot_bounded_filesystem_package(target)
    expected = {
        (entry.kind, entry.relative_path): (index, entry)
        for index, entry in enumerate(journal.cleanup_entries)
    }
    actual = [
        *(("file", name) for name in snapshot.file_names()),
        *(("directory", name) for name in snapshot.directory_names),
    ]
    for key in actual:
        row = expected.get(key)
        if row is None or row[0] < journal.cleanup_cursor:
            raise RuntimeError("runtime_recovery_ownership_ambiguous")
        path = target / Path(key[1])
        if path_identity(path) != row[1].identity:
            raise RuntimeError("runtime_recovery_ownership_ambiguous")


def _require_unambiguous_owner(
    runtime_root: Path,
    target: Path,
    package_root_sha256: str,
) -> RuntimeTransactionJournal:
    identity = _plain_directory_identity(target)
    relative = target.relative_to(runtime_root).as_posix()
    owners = [
        journal
        for journal in load_runtime_transaction_journals(runtime_root)
        if journal.phase == RuntimeTransactionPhase.FINALIZED
        and journal.owns_target
        and journal.target_path == relative
        and journal.package_root_sha256 == package_root_sha256
        and journal.target_identity == identity
    ]
    if len(owners) != 1:
        raise RuntimeError("runtime_digest_target_conflict")
    return owners[0]


def _active_config_dirs(runtime_root: Path) -> set[str] | None:
    path = runtime_root / "CustomConfig" / "deck_config.ini"
    content = _plain_file_bytes_or_none(path)
    if content is None:
        return set()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None
    in_configs = False
    seen_decks: set[str] = set()
    configs: set[str] = set()
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_configs = stripped.casefold() == "[configs]"
            continue
        if (
            not in_configs
            or not stripped
            or stripped.startswith(("#", ";"))
            or "=" not in raw
        ):
            continue
        key, value = raw.split("=", 1)
        deck = key.strip().casefold()
        config = value.strip()
        if not deck or deck in seen_decks or not _valid_component(config):
            return None
        seen_decks.add(deck)
        configs.add(config.casefold())
    return configs


def _verify_active_state_targets(
    runtime_root: Path,
    state: RuntimeState | None,
) -> None:
    if state is None:
        return
    active = _active_config_dirs(runtime_root)
    if active is None:
        return
    for deck in state.decks:
        if deck.config_dir.casefold() not in active:
            continue
        target = runtime_root / "CustomConfig" / deck.config_dir
        _verify_runtime_tree_digest(target, deck.package_root_sha256)


def _remove_owned_tree(
    root: Path,
    expected_identity: tuple[int, int, int],
) -> None:
    if _plain_directory_identity(root) != expected_identity:
        raise RuntimeError("runtime_recovery_ownership_ambiguous")
    snapshot = snapshot_bounded_filesystem_package(root)
    for name in sorted(
        snapshot.file_names(),
        key=lambda value: (value.count("/"), value),
        reverse=True,
    ):
        path = root / Path(name)
        status = plain_file_status(path)
        secure_unlink(
            path,
            expected_identity=path_identity_from_status(status),
            expected_parent_identity=path_identity(path.parent),
        )
    for name in sorted(
        snapshot.directory_names,
        key=lambda value: (value.count("/"), value),
        reverse=True,
    ):
        path = root / Path(name)
        secure_rmdir(
            path,
            expected_identity=path_identity(path),
            expected_parent_identity=path_identity(path.parent),
        )
    secure_rmdir(
        root,
        expected_identity=expected_identity,
        expected_parent_identity=path_identity(root.parent),
    )


def _delete_journal(path: Path) -> None:
    if not path_lexists(path):
        return
    status = plain_file_status(path)
    secure_unlink(
        path,
        expected_identity=path_identity_from_status(status),
        expected_parent_identity=path_identity(path.parent),
    )


def _plain_file_bytes_or_none(path: Path) -> bytes | None:
    if not path_lexists(path):
        return None
    status = plain_file_status(path)
    return read_file_no_follow(
        path,
        expected_status=status,
        maximum_size=1024 * 1024,
    )


def _plain_directory_identity(path: Path) -> tuple[int, int, int]:
    require_plain_directory(path)
    return path_identity(path)


def _directory_identity_or_none(
    path: Path,
) -> tuple[int, int, int] | None:
    if not path_lexists(path):
        return None
    return _plain_directory_identity(path)


def _state_key(deck_name: str) -> str:
    digest = hashlib.sha256(
        _STATE_IDENTITY_DOMAIN + deck_name.casefold().encode("utf-8")
    ).hexdigest()
    normalized = unicodedata.normalize("NFKD", deck_name.casefold())
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-") or "deck"
    slug = slug[:_STATE_SLUG_LIMIT].rstrip("-") or "deck"
    return f"{slug}--sha256-{digest}"


def _same_config_dir(left: str | None, right: str | None) -> bool:
    return (
        left is not None and right is not None and left.casefold() == right.casefold()
    )


def _valid_deck_name(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and len(value) <= _SAFE_COMPONENT_LIMIT
        and not value.startswith((";", "#"))
        and not any(character in value for character in "\r\n=\0")
        and not any(ord(character) < 32 for character in value)
    )


def _valid_component(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and len(value) <= _SAFE_COMPONENT_LIMIT
        and value not in {".", ".."}
        and Path(value).name == value
        and not any(character in value for character in '<>:"/\\|?*\0')
        and not any(ord(character) < 32 for character in value)
        and not value.endswith((".", " "))
    )


def _add_note(
    primary: BaseException,
    operation: str,
    error: BaseException,
) -> None:
    try:
        primary.add_note(f"{operation}: {type(error).__name__}: {error}")
    except BaseException:
        pass


__all__ = (
    "RUNTIME_ATTEMPT_RETENTION_FIELDS",
    "RUNTIME_ATTEMPT_RETENTION_KIND",
    "RUNTIME_ATTEMPT_RETENTION_MAX_BYTES",
    "RUNTIME_ATTEMPT_RETENTION_SCHEMA_VERSION",
    "RuntimeApplyLease",
    "RuntimeApplyLockToken",
    "RuntimeAttemptEvidenceRetirementStep",
    "RuntimeAttemptRecovery",
    "RuntimeAttemptRetentionRecord",
    "RuntimeInstallPlan",
    "RuntimeInstallResult",
    "RuntimeNoCommitCleanupStep",
    "RuntimeNoCommitMetadataStep",
    "build_runtime_attempt_retention_bytes",
    "bootstrap_runtime_layout_directory_from_pair",
    "install_runtime_package",
    "lease_runtime_apply",
    "plan_runtime_install",
    "observe_runtime_layout_bootstrap_from_pair",
    "recover_runtime_attempt",
    "recover_runtime_attempt_from_pair",
    "reconstruct_runtime_no_commit_inventory_from_pair",
    "delete_runtime_no_commit_entry_from_pair",
    "retire_runtime_no_commit_metadata_from_pair",
    "recover_runtime_state",
)
