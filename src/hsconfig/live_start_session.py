"""Closed, resumable authority cursor for Codex-first live-start runs.

The session is deliberately workflow state, never apply authority.  Every
mutation is a byte-, digest-, identity-, lock-, thread-, and predecessor-bound
compare-and-set.  Physical mutations are mediated by short-lived opaque
capabilities and their single-use receipts.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from copy import copy
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import secrets
import stat
import threading
from types import MappingProxyType
from typing import Any, BinaryIO, Literal, TypeVar

from hsconfig import input_snapshot_manifest as _task2_inputs
from hsconfig.atomic_io import (
    AtomicWriteConflictError,
    ExclusiveFileLock,
    MaterializedStagingBytes,
    PublishedNoReplaceBytes,
    atomic_commit_bound_staging_no_replace,
    atomic_materialize_staging_bytes,
    atomic_write_reserved_bytes,
)
from hsconfig.apply_invocation import (
    APPLY_INVOCATION_MAX_BYTES,
    ApplyInvocation,
    parse_apply_invocation as _parse_apply_invocation,
    require_apply_invocation_admission_capacity as _require_apply_invocation_admission_capacity,
)
from hsconfig.input_snapshot_manifest import FrozenCompilerInputs
from hsconfig.output_operation_admission import (
    OUTPUT_OPERATION_ADMISSION_NAME,
    OUTPUT_OPERATION_ADMISSION_RESERVED_TEMP_NAME,
    OUTPUT_OPERATION_ADMISSION_STAGING_NAME,
    _require_windows_safe_absolute_path,
)
from hsconfig.package_io import (
    MAX_FILESYSTEM_NODES,
    PathIdentity,
    path_identity,
    path_identity_from_status,
    require_no_alternate_data_streams,
    require_plain_directory,
    require_same_identity_resolution,
    secure_create_directory,
    secure_open_file_descriptor,
    secure_unlink,
    status_is_reparse,
)
from hsconfig.package_request import FrozenJsonDocument
from hsconfig.runtime_live_admission import (
    RUNTIME_LIVE_ATTEMPT_ADMISSION_MAX_BYTES,
    RUNTIME_LIVE_ATTEMPT_ADMISSION_NAME,
    RuntimeLiveAttemptAdmissionEvidence,
)
from hsconfig.runtime_transaction_journal import (
    RuntimeTransactionPhase,
    parse_runtime_transaction_journal_bytes,
)


LIVE_START_SESSION_SCHEMA_VERSION = 1
LIVE_START_SESSION_MAX_BYTES = 320 * 1024
LIVE_START_RESULT_INTENT_SCHEMA_VERSION = 1
LIVE_START_RESULT_INTENT_MAX_BYTES = 64 * 1024
LIVE_START_RESULT_INTENT_KIND = "live_start_result_intent"
LIVE_START_RESULT_SUMMARY_MAX_BYTES = 64 * 1024
LIVE_START_RESULT_SUMMARY_KIND = "live_start_result"
LIVE_START_ATTEMPT_ACKNOWLEDGEMENT_SCHEMA_VERSION = 1
LIVE_START_ATTEMPT_ACKNOWLEDGEMENT_MAX_BYTES = 32 * 1024
LIVE_START_ATTEMPT_ACKNOWLEDGEMENT_KIND = (
    "live_start_attempt_acknowledgement"
)
LIVE_START_TERMINAL_RETIREMENT_SCHEMA_VERSION = 1
LIVE_START_TERMINAL_RETIREMENT_MAX_BYTES = 192 * 1024
LIVE_START_TERMINAL_RETIREMENT_KIND = "live_start_terminal_retirement"
LIVE_START_TERMINAL_RESOLUTION_EVIDENCE_SCHEMA_VERSION = 1
LIVE_START_TERMINAL_RESOLUTION_EVIDENCE_MAX_BYTES = 128 * 1024
LIVE_START_TERMINAL_RESOLUTION_EVIDENCE_KIND = (
    "live_start_terminal_resolution_evidence"
)
LIVE_START_RUNTIME_APPLY_RECOVERY_EVIDENCE_SCHEMA_VERSION = 1
LIVE_START_RUNTIME_APPLY_RECOVERY_EVIDENCE_MAX_BYTES = 128 * 1024
LIVE_START_RUNTIME_APPLY_RECOVERY_EVIDENCE_KIND = (
    "live_start_runtime_apply_recovery_evidence"
)
LIVE_START_RUNTIME_LAYOUT_BOOTSTRAP_SCHEMA_VERSION = 1
LIVE_START_RUNTIME_LAYOUT_BOOTSTRAP_MAX_BYTES = 32 * 1024
LIVE_START_RUNTIME_LAYOUT_BOOTSTRAP_KIND = (
    "live_start_runtime_layout_bootstrap"
)
LIVE_START_OWNER_RETIREMENT_EVIDENCE_SCHEMA_VERSION = 1
LIVE_START_OWNER_RETIREMENT_EVIDENCE_MAX_BYTES = 64 * 1024
LIVE_START_OWNER_RETIREMENT_TOMBSTONE_MAX_BYTES = 4 * 1024 * 1024
LIVE_START_OWNER_RETIREMENT_EVIDENCE_KIND = (
    "live_start_owner_retirement_evidence"
)
LIVE_START_EXTERNAL_FILE_ACTION_SCHEMA_VERSION = 1
LIVE_START_EXTERNAL_FILE_ACTION_MAX_BYTES = 32 * 1024
LIVE_START_EXTERNAL_FILE_ACTION_KIND = "live_start_external_file_action"
LIVE_START_PENDING_TRANSITION_SCHEMA_VERSION = 1
LIVE_START_PENDING_TRANSITION_MAX_BYTES = 64 * 1024
LIVE_START_PENDING_TRANSITION_KIND = "live_start_pending_transition"
LIVE_START_OUTPUT_CHILD_BINDING_SCHEMA_VERSION = 1
LIVE_START_OUTPUT_CHILD_BINDING_MAX_BYTES = 32 * 1024
LIVE_START_OUTPUT_CHILD_BINDING_KIND = "live_start_output_child_binding"
LIVE_START_OUTPUT_CHILD_CLAIM_SCHEMA_VERSION = 1
LIVE_START_OUTPUT_CHILD_CLAIM_MAX_BYTES = 16 * 1024
LIVE_START_OUTPUT_CHILD_CLAIM_KIND = "live_start_output_child_claim"
LIVE_START_OUTPUT_OPERATION_ADMISSION_BINDING_SCHEMA_VERSION = 1
LIVE_START_OUTPUT_OPERATION_ADMISSION_BINDING_MAX_BYTES = 32 * 1024
LIVE_START_OUTPUT_OPERATION_ADMISSION_BINDING_KIND = (
    "live_start_output_operation_admission_binding"
)
LIVE_START_CLEANUP_IDENTITY_INVENTORY_SCHEMA_VERSION = 1
LIVE_START_CLEANUP_IDENTITY_INVENTORY_MAX_BYTES = 64 * 1024 * 1024
LIVE_START_CLEANUP_IDENTITY_INVENTORY_MAX_ENTRIES = MAX_FILESYSTEM_NODES
LIVE_START_CLEANUP_IDENTITY_INVENTORY_KIND = (
    "live_start_prepublication_cleanup_identity_inventory"
)
LIVE_START_TERMINAL_CLEANUP_INVENTORY_SCHEMA_VERSION = 1
LIVE_START_TERMINAL_CLEANUP_INVENTORY_MAX_BYTES = 64 * 1024 * 1024
LIVE_START_TERMINAL_CLEANUP_INVENTORY_MAX_ENTRIES = MAX_FILESYSTEM_NODES
LIVE_START_TERMINAL_CLEANUP_INVENTORY_KIND = (
    "live_start_terminal_resolution_cleanup_inventory"
)
LIVE_START_FROZEN_INPUT_FILES = (
    "inputs/input_snapshot_manifest.json",
    "inputs/deck.json",
    "inputs/cards.json",
    "inputs/sources.json",
)
_PHYSICAL_IDENTITY_MAX_MISSING_COMPONENTS = 256
_PHYSICAL_IDENTITY_MAX_ANCESTOR_ROWS = 256
LIVE_START_FROZEN_INPUT_MAXIMUM_BYTES = MappingProxyType(
    {
        "inputs/input_snapshot_manifest.json": 256 * 1024,
        "inputs/deck.json": 134_217_728 + 1_048_576,
        "inputs/cards.json": 3 * 134_217_728 + 1_048_576,
        "inputs/sources.json": 2 * 134_217_728 + 1_048_576,
    }
)


def _no_creation_fault(_point: str) -> None:
    """Default live-start creation hook."""


class LiveStartPhase(StrEnum):
    INPUT_FROZEN = "INPUT_FROZEN"
    CANDIDATE_DRAFTED = "CANDIDATE_DRAFTED"
    CANDIDATE_VALIDATED = "CANDIDATE_VALIDATED"
    REVIEW_APPROVED = "REVIEW_APPROVED"
    PACKAGE_VALIDATED = "PACKAGE_VALIDATED"
    PREPUBLICATION_CHECK_PASSED = "PREPUBLICATION_CHECK_PASSED"
    PUBLICATION_COMMITTED = "PUBLICATION_COMMITTED"
    APPLY_STARTED = "APPLY_STARTED"
    APPLY_COMMITTED = "APPLY_COMMITTED"
    RUNTIME_MATCHED = "RUNTIME_MATCHED"


LiveStartTerminalStatus = Literal[
    "LIVE_AND_MATCHED",
    "ALREADY_LIVE",
    "PREVIEW_READY",
    "PROFILE_REQUIRED",
    "FAILED_PRESERVED",
    "APPLIED_BUT_NOT_VERIFIED",
]


class SessionConflictError(RuntimeError):
    """The persisted session is not the exact expected predecessor."""


class SessionCapabilityError(RuntimeError):
    """A session or physical capability is forged, stale, or out of context."""


class SessionValidationError(ValueError):
    """A closed session or embedded document is invalid."""


class SessionLayoutError(SessionValidationError):
    """The physical run layout contains an undeclared or unsafe surface."""


_RUN_ID = re.compile(r"[0-9a-f]{32}\Z")
_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_SESSION_FIELDS = frozenset(
    {
        "schema_version",
        "run_id",
        "deck_name",
        "deck_code_sha256",
        "preview_requested",
        "phase",
        "candidate_revision",
        "revisions_used",
        "input_snapshot_manifest_sha256",
        "artifact_bindings",
        "pending_transition",
        "prepublication_work_binding",
        "output_operation_admission_binding",
        "output_child_binding",
        "publication_binding",
        "apply_invocation_sha256",
        "runtime_admission_binding",
        "runtime_layout_bootstrap",
        "apply_recovery",
        "closed_apply_recovery_commitment",
        "result_intent",
        "attempt_acknowledgement",
        "terminal_retirement",
        "terminal_status",
        "content_sha256",
    }
)
RUN_LOGICAL_FILES = frozenset(
    {
        "session.json",
        "inputs/input_snapshot_manifest.json",
        "inputs/deck.json",
        "inputs/cards.json",
        "inputs/sources.json",
        "starter/starter_context.json",
        "starter/starter_config_candidate.json",
        "starter/starter_config_review.json",
        "receipts/candidate_validation.json",
        "receipts/review_validation.json",
        "receipts/package_validation.json",
        "receipts/prepublication_apply_check.json",
        "receipts/apply_invocation.json",
        "terminal-resolution-cleanup.json",
        "result/summary.json",
        "result/summary.md",
    }
)
RUN_LOGICAL_DIRECTORIES = frozenset({"inputs", "starter", "receipts", "result"})

_FROZEN_INPUT_ARTIFACTS = frozenset(LIVE_START_FROZEN_INPUT_FILES)
_PHASE_MANDATORY_ARTIFACTS = MappingProxyType(
    {
        LiveStartPhase.INPUT_FROZEN: _FROZEN_INPUT_ARTIFACTS,
        LiveStartPhase.CANDIDATE_DRAFTED: _FROZEN_INPUT_ARTIFACTS
        | {
            "starter/starter_context.json",
            "starter/starter_config_candidate.json",
        },
        LiveStartPhase.CANDIDATE_VALIDATED: _FROZEN_INPUT_ARTIFACTS
        | {
            "starter/starter_context.json",
            "starter/starter_config_candidate.json",
            "receipts/candidate_validation.json",
        },
        LiveStartPhase.REVIEW_APPROVED: _FROZEN_INPUT_ARTIFACTS
        | {
            "starter/starter_context.json",
            "starter/starter_config_candidate.json",
            "receipts/candidate_validation.json",
            "starter/starter_config_review.json",
            "receipts/review_validation.json",
        },
        LiveStartPhase.PACKAGE_VALIDATED: _FROZEN_INPUT_ARTIFACTS
        | {
            "starter/starter_context.json",
            "starter/starter_config_candidate.json",
            "receipts/candidate_validation.json",
            "starter/starter_config_review.json",
            "receipts/review_validation.json",
            "receipts/package_validation.json",
        },
        LiveStartPhase.PREPUBLICATION_CHECK_PASSED: _FROZEN_INPUT_ARTIFACTS
        | {
            "starter/starter_context.json",
            "starter/starter_config_candidate.json",
            "receipts/candidate_validation.json",
            "starter/starter_config_review.json",
            "receipts/review_validation.json",
            "receipts/package_validation.json",
            "receipts/prepublication_apply_check.json",
        },
        LiveStartPhase.PUBLICATION_COMMITTED: _FROZEN_INPUT_ARTIFACTS
        | {
            "starter/starter_context.json",
            "starter/starter_config_candidate.json",
            "receipts/candidate_validation.json",
            "starter/starter_config_review.json",
            "receipts/review_validation.json",
            "receipts/package_validation.json",
            "receipts/prepublication_apply_check.json",
        },
        LiveStartPhase.APPLY_STARTED: _FROZEN_INPUT_ARTIFACTS
        | {
            "starter/starter_context.json",
            "starter/starter_config_candidate.json",
            "receipts/candidate_validation.json",
            "starter/starter_config_review.json",
            "receipts/review_validation.json",
            "receipts/package_validation.json",
            "receipts/prepublication_apply_check.json",
            "receipts/apply_invocation.json",
        },
        LiveStartPhase.APPLY_COMMITTED: _FROZEN_INPUT_ARTIFACTS
        | {
            "starter/starter_context.json",
            "starter/starter_config_candidate.json",
            "receipts/candidate_validation.json",
            "starter/starter_config_review.json",
            "receipts/review_validation.json",
            "receipts/package_validation.json",
            "receipts/prepublication_apply_check.json",
            "receipts/apply_invocation.json",
        },
        LiveStartPhase.RUNTIME_MATCHED: _FROZEN_INPUT_ARTIFACTS
        | {
            "starter/starter_context.json",
            "starter/starter_config_candidate.json",
            "receipts/candidate_validation.json",
            "starter/starter_config_review.json",
            "receipts/review_validation.json",
            "receipts/package_validation.json",
            "receipts/prepublication_apply_check.json",
            "receipts/apply_invocation.json",
        },
    }
)

PHASE_TRANSITIONS = MappingProxyType(
    {
        LiveStartPhase.INPUT_FROZEN: frozenset(
            {LiveStartPhase.CANDIDATE_DRAFTED}
        ),
        LiveStartPhase.CANDIDATE_DRAFTED: frozenset(
            {
                LiveStartPhase.CANDIDATE_DRAFTED,
                LiveStartPhase.CANDIDATE_VALIDATED,
            }
        ),
        LiveStartPhase.CANDIDATE_VALIDATED: frozenset(
            {
                LiveStartPhase.CANDIDATE_DRAFTED,
                LiveStartPhase.REVIEW_APPROVED,
            }
        ),
        LiveStartPhase.REVIEW_APPROVED: frozenset(
            {LiveStartPhase.PACKAGE_VALIDATED}
        ),
        LiveStartPhase.PACKAGE_VALIDATED: frozenset(
            {LiveStartPhase.PREPUBLICATION_CHECK_PASSED}
        ),
        LiveStartPhase.PREPUBLICATION_CHECK_PASSED: frozenset(
            {LiveStartPhase.PUBLICATION_COMMITTED}
        ),
        LiveStartPhase.PUBLICATION_COMMITTED: frozenset(
            {LiveStartPhase.APPLY_STARTED}
        ),
        LiveStartPhase.APPLY_STARTED: frozenset(
            {LiveStartPhase.APPLY_STARTED, LiveStartPhase.APPLY_COMMITTED}
        ),
        LiveStartPhase.APPLY_COMMITTED: frozenset(
            {LiveStartPhase.APPLY_COMMITTED, LiveStartPhase.RUNTIME_MATCHED}
        ),
        LiveStartPhase.RUNTIME_MATCHED: frozenset(
            {LiveStartPhase.RUNTIME_MATCHED}
        ),
    }
)

_EVENT_TRANSITIONS = MappingProxyType(
    {
        "initial_draft": (
            LiveStartPhase.INPUT_FROZEN,
            LiveStartPhase.CANDIDATE_DRAFTED,
        ),
        "candidate_valid": (
            LiveStartPhase.CANDIDATE_DRAFTED,
            LiveStartPhase.CANDIDATE_VALIDATED,
        ),
        "technical_failure": (
            LiveStartPhase.CANDIDATE_DRAFTED,
            LiveStartPhase.CANDIDATE_DRAFTED,
        ),
        "replacement_draft": (
            LiveStartPhase.CANDIDATE_DRAFTED,
            LiveStartPhase.CANDIDATE_DRAFTED,
        ),
        "review_approved": (
            LiveStartPhase.CANDIDATE_VALIDATED,
            LiveStartPhase.REVIEW_APPROVED,
        ),
        "review_revision": (
            LiveStartPhase.CANDIDATE_VALIDATED,
            LiveStartPhase.CANDIDATE_DRAFTED,
        ),
        "package_validated": (
            LiveStartPhase.REVIEW_APPROVED,
            LiveStartPhase.PACKAGE_VALIDATED,
        ),
        "prepublication_passed": (
            LiveStartPhase.PACKAGE_VALIDATED,
            LiveStartPhase.PREPUBLICATION_CHECK_PASSED,
        ),
        "publication_committed": (
            LiveStartPhase.PREPUBLICATION_CHECK_PASSED,
            LiveStartPhase.PUBLICATION_COMMITTED,
        ),
        "apply_started": (
            LiveStartPhase.PUBLICATION_COMMITTED,
            LiveStartPhase.APPLY_STARTED,
        ),
        "apply_committed": (
            LiveStartPhase.APPLY_STARTED,
            LiveStartPhase.APPLY_COMMITTED,
        ),
        "runtime_matched": (
            LiveStartPhase.APPLY_COMMITTED,
            LiveStartPhase.RUNTIME_MATCHED,
        ),
    }
)

_PHASE_FINAL_PENDING_OPERATIONS = MappingProxyType(
    {
        "initial_draft": "install_candidate",
        "replacement_draft": "install_candidate",
        "candidate_valid": "install_candidate_validation",
        "review_approved": "install_review_validation",
        "review_revision": "review_revision",
        "package_validated": "install_package_validation",
        "prepublication_passed": "install_prepublication_validation",
        "apply_started": "install_apply_invocation",
    }
)

_INTERNAL_TRANSITION_AUTHORITY = object()
_PUBLIC_SENSITIVE_UPDATE_FIELDS = frozenset(
    {
        "artifact_bindings",
        "prepublication_work_binding",
        "output_operation_admission_binding",
        "output_child_binding",
        "publication_binding",
        "apply_invocation_sha256",
        "runtime_admission_binding",
        "runtime_layout_bootstrap",
        "apply_recovery",
        "closed_apply_recovery_commitment",
        "result_intent",
        "attempt_acknowledgement",
        "terminal_retirement",
        "terminal_status",
    }
)
_INTERNAL_EVENT_FIELD_ALLOWLIST = MappingProxyType(
    {
        "same_phase_cas": frozenset(
            {
                "artifact_bindings",
                "pending_transition",
                "prepublication_work_binding",
                "output_operation_admission_binding",
                "output_child_binding",
                "publication_binding",
                "apply_invocation_sha256",
                "runtime_admission_binding",
                "runtime_layout_bootstrap",
                "apply_recovery",
                "closed_apply_recovery_commitment",
                "result_intent",
                "attempt_acknowledgement",
                "terminal_retirement",
            }
        ),
        "apply_committed": frozenset({"apply_recovery"}),
        "runtime_matched": frozenset({"apply_recovery"}),
        "apply_started": frozenset(
            {
                "artifact_bindings",
                "pending_transition",
                "output_operation_admission_binding",
                "apply_invocation_sha256",
                "runtime_admission_binding",
            }
        ),
        "package_validated": frozenset(
            {
                "artifact_bindings",
                "pending_transition",
                "prepublication_work_binding",
            }
        ),
        "prepublication_passed": frozenset(
            {"artifact_bindings", "pending_transition"}
        ),
        "publication_committed": frozenset(
            {"publication_binding"}
        ),
        "bind_terminal": frozenset({"artifact_bindings", "terminal_status"}),
        "replacement_draft": frozenset(
            {"artifact_bindings", "pending_transition"}
        ),
        "review_revision": frozenset(
            {"artifact_bindings", "pending_transition"}
        ),
    }
)

_DOWNSTREAM_REVISION_ARTIFACTS = frozenset(
    {
        "receipts/candidate_validation.json",
        "starter/starter_config_review.json",
        "receipts/review_validation.json",
        "receipts/package_validation.json",
        "receipts/prepublication_apply_check.json",
        "receipts/apply_invocation.json",
        "result/summary.json",
        "result/summary.md",
    }
)


@dataclass(frozen=True, slots=True)
class LiveStartSession:
    schema_version: int
    run_id: str
    deck_name: str
    deck_code_sha256: str
    preview_requested: bool
    phase: LiveStartPhase
    candidate_revision: int
    revisions_used: int
    input_snapshot_manifest_sha256: str
    artifact_bindings: Mapping[str, str]
    pending_transition: Mapping[str, Any] | None
    prepublication_work_binding: Mapping[str, Any] | None
    output_operation_admission_binding: Mapping[str, Any] | None
    output_child_binding: Mapping[str, Any] | None
    publication_binding: Mapping[str, Any] | None
    apply_invocation_sha256: str | None
    runtime_admission_binding: Mapping[str, Any] | None
    runtime_layout_bootstrap: Mapping[str, Any] | None
    apply_recovery: Mapping[str, Any] | None
    closed_apply_recovery_commitment: Mapping[str, Any] | None
    result_intent: Mapping[str, Any] | None
    attempt_acknowledgement: Mapping[str, Any] | None
    terminal_retirement: Mapping[str, Any] | None
    terminal_status: str | None
    content_sha256: str
    canonical_json: bytes = field(repr=False)
    session_identity: PathIdentity | None = field(repr=False, compare=False)

    def to_value(self) -> dict[str, Any]:
        return _decode_canonical_json(self.canonical_json)


@dataclass(frozen=True, slots=True)
class LiveStartSessionUpdate:
    event: str
    changes: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.event, str) or not self.event:
            raise ValueError("live_start_session_update_event_invalid")
        object.__setattr__(self, "changes", _freeze_mapping(self.changes))


class _SessionBearer:
    __slots__ = (
        "active",
        "thread_id",
        "nonce",
        "session_root",
        "session_root_identity",
        "session_lock_path",
        "session_lock_identity",
        "session_lock",
    )

    def __init__(
        self,
        *,
        session_root: Path,
        session_root_identity: PathIdentity,
        session_lock_path: Path,
        session_lock_identity: PathIdentity,
        session_lock: ExclusiveFileLock | None = None,
    ) -> None:
        self.active = True
        self.thread_id = threading.get_ident()
        self.nonce = secrets.token_hex(32)
        self.session_root = session_root
        self.session_root_identity = session_root_identity
        self.session_lock_path = session_lock_path
        self.session_lock_identity = session_lock_identity
        self.session_lock = session_lock


@dataclass(frozen=True, slots=True, init=False)
class SessionLockToken:
    _bearer: _SessionBearer = field(repr=False, compare=False)

    def __new__(cls, _mint: object | None = None) -> SessionLockToken:
        if _mint is not _OPAQUE_MINT:
            raise TypeError("session_lock_token_nonconstructible")
        return object.__new__(cls)

    @classmethod
    def _mint(cls, bearer: _SessionBearer) -> SessionLockToken:
        token = object.__new__(cls)
        object.__setattr__(token, "_bearer", bearer)
        return token

    def __copy__(self) -> SessionLockToken:
        return self

    def __deepcopy__(self, _memo: dict[int, Any]) -> SessionLockToken:
        return self

    def __reduce__(self) -> None:
        raise TypeError("session_lock_token_nonserializable")


@dataclass(frozen=True, slots=True)
class LiveStartSessionLease:
    session_root: Path
    session_root_identity: PathIdentity
    session_lock_path: Path
    session_lock_identity: PathIdentity
    lock_token: SessionLockToken


@dataclass(frozen=True, slots=True)
class _SessionContextRegistration:
    bearer: _SessionBearer
    token: SessionLockToken
    thread_id: int
    nonce: str
    session_root: Path
    session_root_identity: PathIdentity
    session_lock_path: Path
    session_lock_identity: PathIdentity
    session_lock: ExclusiveFileLock
    session_lock_object_path: Path
    session_lock_handle: BinaryIO
    session_lock_handle_identity: PathIdentity


_AUTHORITY_REGISTRY_LOCK = threading.RLock()
_ACTIVE_SESSION_CONTEXTS: dict[int, _SessionContextRegistration] = {}


def _register_session_context(
    *,
    bearer: _SessionBearer,
    token: SessionLockToken,
) -> None:
    with _AUTHORITY_REGISTRY_LOCK:
        if id(bearer) in _ACTIVE_SESSION_CONTEXTS:
            raise SessionCapabilityError(
                "live_start_session_capability_registry_conflict"
            )
        session_lock = bearer.session_lock
        session_lock_handle = getattr(session_lock, "_handle", None)
        try:
            session_lock_handle_identity = path_identity_from_status(
                os.fstat(session_lock_handle.fileno())
            )
        except (AttributeError, OSError, RuntimeError, ValueError) as error:
            raise SessionCapabilityError(
                "live_start_session_capability_registry_invalid"
            ) from error
        if (
            not bearer.active
            or not bearer.nonce
            or token._bearer is not bearer
            or not isinstance(session_lock, ExclusiveFileLock)
            or session_lock.path != bearer.session_lock_path
            or session_lock_handle_identity != bearer.session_lock_identity
        ):
            raise SessionCapabilityError(
                "live_start_session_capability_registry_invalid"
            )
        _ACTIVE_SESSION_CONTEXTS[id(bearer)] = (
            _SessionContextRegistration(
                bearer=bearer,
                token=token,
                thread_id=bearer.thread_id,
                nonce=bearer.nonce,
                session_root=bearer.session_root,
                session_root_identity=bearer.session_root_identity,
                session_lock_path=bearer.session_lock_path,
                session_lock_identity=bearer.session_lock_identity,
                session_lock=session_lock,
                session_lock_object_path=session_lock.path,
                session_lock_handle=session_lock_handle,
                session_lock_handle_identity=session_lock_handle_identity,
            )
        )


def _session_context_registration(
    *,
    bearer: _SessionBearer,
    token: SessionLockToken | None = None,
) -> _SessionContextRegistration | None:
    with _AUTHORITY_REGISTRY_LOCK:
        registered = _ACTIVE_SESSION_CONTEXTS.get(id(bearer))
        if (
            registered is None
            or registered.bearer is not bearer
            or (token is not None and registered.token is not token)
        ):
            return None
        return registered


def _session_context_registration_matches(
    registration: _SessionContextRegistration,
    *,
    bearer: _SessionBearer,
    token: SessionLockToken | None = None,
) -> bool:
    return (
        registration.bearer is bearer
        and (token is None or registration.token is token)
        and getattr(registration.token, "_bearer", None) is bearer
        and bearer.active
        and bearer.thread_id == registration.thread_id
        and bearer.nonce == registration.nonce
        and bearer.session_root == registration.session_root
        and bearer.session_root_identity
        == registration.session_root_identity
        and bearer.session_lock_path == registration.session_lock_path
        and bearer.session_lock_identity
        == registration.session_lock_identity
        and bearer.session_lock is registration.session_lock
        and getattr(registration.session_lock, "path", None)
        == registration.session_lock_object_path
        and _registered_session_lock_handle_matches(registration)
    )


def _registered_session_lock_handle_matches(
    registration: _SessionContextRegistration,
) -> bool:
    handle = getattr(registration.session_lock, "_handle", None)
    if handle is not registration.session_lock_handle:
        return False
    try:
        return (
            not handle.closed
            and path_identity_from_status(os.fstat(handle.fileno()))
            == registration.session_lock_handle_identity
        )
    except (AttributeError, OSError, RuntimeError, ValueError):
        return False


def _session_context_is_registered(
    *,
    bearer: _SessionBearer,
    token: SessionLockToken | None = None,
) -> bool:
    with _AUTHORITY_REGISTRY_LOCK:
        registered = _ACTIVE_SESSION_CONTEXTS.get(id(bearer))
        return (
            registered is not None
            and _session_context_registration_matches(
                registered,
                bearer=bearer,
                token=token,
            )
        )


def _deregister_session_context(*, bearer: _SessionBearer) -> None:
    with _AUTHORITY_REGISTRY_LOCK:
        registered = _ACTIVE_SESSION_CONTEXTS.get(id(bearer))
        if registered is not None and registered.bearer is bearer:
            del _ACTIVE_SESSION_CONTEXTS[id(bearer)]


def _validate_frozen_compiler_inputs(
    value: FrozenCompilerInputs,
    *,
    deck_name: str,
    deck_code_sha256: str,
    runtime_root: Path,
    output_base_root: Path,
    output_deck_root: Path,
) -> tuple[Mapping[str, bytes], str]:
    """Revalidate one genuine Task-2 carrier and derive its four envelopes."""

    if not isinstance(value, FrozenCompilerInputs):
        raise SessionValidationError(
            "live_start_task2_frozen_inputs_required"
        )
    try:
        validated_manifest = (
            _task2_inputs.validate_input_snapshot_manifest_document(
                value.manifest.document.document
            )
        )
        validated = FrozenCompilerInputs(
            manifest=validated_manifest,
            deck=value.deck,
            full_cards=value.full_cards,
            collectible_cards=value.collectible_cards,
            source_acquisition=value.source_acquisition,
            source_documents=value.source_documents,
            globalvalues_baseline=value.globalvalues_baseline,
        )
        _task2_inputs._require_manifest_blob_match(validated)
        _task2_inputs._validate_loaded_compiler_binding(validated)

        compiler = validated.manifest.compiler_inputs.to_value()
        operator = validated.manifest.operator_bindings.to_value()
        deck = validated.deck.to_value()
        deck_identity = deck.get("deck_identity")
        expected_runtime_root = Path(runtime_root).absolute()
        expected_output_base = Path(output_base_root).absolute()
        expected_output_deck = Path(output_deck_root).absolute()
        if (
            compiler.get("deck_code_sha256") != deck_code_sha256
            or not isinstance(deck_identity, dict)
            or deck_identity.get("deck_name") != deck_name
            or operator.get("runtime_root") != str(expected_runtime_root)
            or operator.get("output_base_root") != str(expected_output_base)
            or operator.get("deck_output_name") != expected_output_deck.name
            or expected_output_deck.parent != expected_output_base
            or tuple(operator.get("runtime_root_identity", ()))
            != path_identity(expected_runtime_root)
            or tuple(operator.get("output_base_root_identity", ()))
            != path_identity(expected_output_base)
        ):
            raise ValueError("input_snapshot_creation_binding_mismatch")

        cards_envelope = FrozenJsonDocument.from_value(
            {
                "full_cards": validated.full_cards.to_value(),
                "collectible_cards": validated.collectible_cards.to_value(),
                "globalvalues_baseline": (
                    validated.globalvalues_baseline.to_value()
                ),
            }
        )
        sources_envelope = FrozenJsonDocument.from_value(
            {
                "source_acquisition": validated.source_acquisition.to_value(),
                "source_documents": validated.source_documents.to_value(),
            }
        )
        frozen = {
            "inputs/input_snapshot_manifest.json": (
                validated.manifest.document.canonical_json
            ),
            "inputs/deck.json": validated.deck.canonical_json,
            "inputs/cards.json": cards_envelope.canonical_json,
            "inputs/sources.json": sources_envelope.canonical_json,
        }
        for logical, raw in frozen.items():
            if (
                not raw
                or len(raw) > LIVE_START_FROZEN_INPUT_MAXIMUM_BYTES[logical]
                or _canonical_frozen_input_json(
                    _decode_frozen_input_json(raw)
                )
                != raw
            ):
                raise ValueError("input_snapshot_physical_envelope_invalid")
    except (OSError, TypeError, ValueError) as error:
        raise SessionValidationError(
            "live_start_task2_frozen_inputs_invalid"
        ) from error
    return (
        MappingProxyType(frozen),
        validated.manifest.document.content_sha256,
    )


def _canonical_frozen_input_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise SessionValidationError(
            "live_start_frozen_input_json_invalid"
        ) from error


def _decode_frozen_input_json(raw: bytes) -> dict[str, Any]:
    if (
        raw.startswith(b"\xef\xbb\xbf")
        or b"\x00" in raw
        or b"\r" in raw
    ):
        raise SessionValidationError(
            "live_start_frozen_input_json_encoding_invalid"
        )

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise SessionValidationError(
                    "live_start_frozen_input_json_duplicate_key"
                )
            result[key] = item
        return result

    def reject_constant(_value: str) -> None:
        raise SessionValidationError(
            "live_start_frozen_input_json_non_finite"
        )

    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SessionValidationError(
            "live_start_frozen_input_json_invalid"
        ) from error
    if not isinstance(value, dict):
        raise SessionValidationError(
            "live_start_frozen_input_json_not_object"
        )
    if _canonical_frozen_input_json(value) != raw:
        raise SessionValidationError(
            "live_start_frozen_input_json_not_canonical"
        )
    return value


def _canonical_absolute_root(
    path: os.PathLike[str] | str,
    *,
    field: str,
) -> Path:
    original_is_string = isinstance(path, str)
    try:
        text = os.fspath(path)
    except TypeError as error:
        raise SessionValidationError(
            f"live_start_{field}_not_canonical"
        ) from error
    if (
        type(text) is not str
        or not text
        or "\x00" in text
        or os.path.normpath(text) != text
    ):
        raise SessionValidationError(f"live_start_{field}_not_canonical")
    candidate = Path(text)
    serialized = str(candidate)
    bare_unc_share_serialization = (
        text == candidate.drive
        and candidate.root == "\\"
        and candidate.anchor == text + "\\"
        and serialized == text + "\\"
    )
    explicit_unc_share_root_separator = (
        original_is_string
        and candidate.drive.startswith("\\\\")
        and candidate.root == "\\"
        and text == candidate.anchor
        and serialized == text
    )
    if (
        not candidate.is_absolute()
        or explicit_unc_share_root_separator
        or (serialized != text and not bare_unc_share_serialization)
    ):
        raise SessionValidationError(f"live_start_{field}_not_canonical")
    try:
        return _require_windows_safe_absolute_path(
            candidate,
            error=f"live_start_{field}_windows_namespace_invalid",
        )
    except ValueError as error:
        raise SessionValidationError(str(error)) from error


def _resolve_local_app_data_root(
    configured: os.PathLike[str] | str | None,
) -> Path:
    if configured is None:
        environment_value = os.environ.get("LOCALAPPDATA")
        if not environment_value:
            raise SessionValidationError(
                "live_start_local_app_data_missing"
            )
        configured = environment_value
    return _canonical_absolute_root(
        configured,
        field="local_app_data_root",
    )


def create_live_start_session(
    *,
    session_root: Path,
    local_app_data_root: Path | None = None,
    repository_root: Path,
    runtime_root: Path,
    output_base_root: Path,
    output_deck_root: Path,
    installed_skill_root: Path,
    deck_name: str,
    deck_code_sha256: str,
    preview_requested: bool,
    frozen_compiler_inputs: FrozenCompilerInputs | None = None,
    input_snapshot_manifest_sha256: str | None = None,
    frozen_input_bytes: Mapping[str, bytes] | None = None,
    _fault_hook: Callable[[str], None] = _no_creation_fault,
) -> LiveStartSession:
    """Create one run, its external persistent lock, and initial cursor."""

    root = _canonical_absolute_root(session_root, field="session_root")
    local_root = _resolve_local_app_data_root(local_app_data_root)
    canonical_repository_root = _canonical_absolute_root(
        repository_root,
        field="repository_root",
    )
    canonical_runtime_root = _canonical_absolute_root(
        runtime_root,
        field="runtime_root",
    )
    canonical_output_base_root = _canonical_absolute_root(
        output_base_root,
        field="output_base_root",
    )
    canonical_output_deck_root = _canonical_absolute_root(
        output_deck_root,
        field="output_deck_root",
    )
    canonical_installed_skill_root = _canonical_absolute_root(
        installed_skill_root,
        field="installed_skill_root",
    )
    forbidden_roots = (
        canonical_repository_root,
        canonical_runtime_root,
        canonical_output_base_root,
        canonical_output_deck_root,
        canonical_installed_skill_root,
    )
    run_id = root.name
    _require_run_id(run_id)
    _require_deck_name(deck_name)
    _require_sha256(deck_code_sha256, "deck_code_sha256")
    frozen_inputs, derived_manifest_sha256 = (
        _validate_frozen_compiler_inputs(
            frozen_compiler_inputs,  # type: ignore[arg-type]
            deck_name=deck_name,
            deck_code_sha256=deck_code_sha256,
            runtime_root=canonical_runtime_root,
            output_base_root=canonical_output_base_root,
            output_deck_root=canonical_output_deck_root,
        )
    )
    if (
        input_snapshot_manifest_sha256 is not None
        and input_snapshot_manifest_sha256 != derived_manifest_sha256
    ) or (
        frozen_input_bytes is not None
        and dict(frozen_input_bytes) != dict(frozen_inputs)
    ):
        raise SessionValidationError(
            "live_start_task2_frozen_inputs_projection_mismatch"
        )
    input_snapshot_manifest_sha256 = derived_manifest_sha256
    if not callable(_fault_hook):
        raise TypeError("live_start_creation_fault_hook_invalid")
    if type(preview_requested) is not bool:
        raise SessionValidationError("live_start_preview_requested_invalid")
    state_root = local_root / "HSConfig"
    expected_root = state_root / "runs" / run_id
    if root != expected_root:
        raise SessionValidationError(
            "live_start_session_root_not_canonical"
        )
    runs_root = state_root / "runs"
    locks_root = state_root / "locks"
    _validate_existing_creation_authority_roots_no_ads(
        local_root,
        state_root,
        runs_root,
        locks_root,
        root,
    )
    _validate_existing_plain_ancestor_chain(local_root)
    if any(
        _paths_overlap(state_root, forbidden_root)
        for forbidden_root in forbidden_roots
    ):
        raise SessionValidationError(
            "live_start_session_forbidden_root_overlap"
        )
    _require_or_create_plain_directory(state_root)
    _validate_existing_creation_authority_roots_no_ads(state_root)
    _require_or_create_plain_directory(runs_root)
    _validate_existing_creation_authority_roots_no_ads(runs_root)
    _require_or_create_plain_directory(locks_root)
    _validate_existing_creation_authority_roots_no_ads(locks_root)
    lock_path = locks_root / f"live-start-{run_id}.lock"
    if os.path.lexists(root) or os.path.lexists(lock_path):
        raise FileExistsError("live_start_session_already_exists")

    with ExclusiveFileLock(
        lock_path,
        expected_parent_identity=path_identity(locks_root),
        create_if_missing=True,
    ) as session_lock:
        lock_identity = path_identity(lock_path)
        try:
            session_lock.validate_no_alternate_data_streams(
                expected_size=0
            )
        except (OSError, ValueError) as error:
            raise SessionLayoutError(
                "live_start_layout_alternate_stream_forbidden"
            ) from error
        root_identity = secure_create_directory(
            root,
            expected_parent_identity=path_identity(root.parent),
        )
        _validate_existing_creation_authority_roots_no_ads(root)
        inputs_root = root / "inputs"
        inputs_identity = secure_create_directory(
            inputs_root,
            expected_parent_identity=root_identity,
        )
        _validate_existing_creation_authority_roots_no_ads(inputs_root)
        input_bindings: dict[str, str] = {}
        for logical in LIVE_START_FROZEN_INPUT_FILES:
            payload = frozen_inputs[logical]
            maximum_size = LIVE_START_FROZEN_INPUT_MAXIMUM_BYTES[logical]
            published_input = atomic_write_reserved_bytes(
                path=root / logical,
                payload=payload,
                expected_parent_identity=inputs_identity,
                expected_predecessor_identity=None,
                expected_predecessor_sha256=None,
                maximum_size=maximum_size,
            )
            rebound_raw, rebound_identity = _read_bound_file(
                root / logical,
                expected_parent_identity=inputs_identity,
                maximum_size=maximum_size,
            )
            if (
                rebound_raw != payload
                or rebound_identity != published_input.identity
                or _bytes_sha256(rebound_raw) != published_input.sha256
            ):
                raise SessionConflictError(
                    "live_start_frozen_input_install_mismatch"
                )
            input_bindings[logical] = published_input.sha256
        value: dict[str, Any] = {
            "schema_version": LIVE_START_SESSION_SCHEMA_VERSION,
            "run_id": run_id,
            "deck_name": deck_name,
            "deck_code_sha256": deck_code_sha256,
            "preview_requested": preview_requested,
            "phase": LiveStartPhase.INPUT_FROZEN.value,
            "candidate_revision": 1,
            "revisions_used": 0,
            "input_snapshot_manifest_sha256": (
                input_snapshot_manifest_sha256
            ),
            "artifact_bindings": input_bindings,
            "pending_transition": None,
            "prepublication_work_binding": None,
            "output_operation_admission_binding": None,
            "output_child_binding": None,
            "publication_binding": None,
            "apply_invocation_sha256": None,
            "runtime_admission_binding": None,
            "runtime_layout_bootstrap": None,
            "apply_recovery": None,
            "closed_apply_recovery_commitment": None,
            "result_intent": None,
            "attempt_acknowledgement": None,
            "terminal_retirement": None,
            "terminal_status": None,
        }
        sealed = _seal_session_value(value, session_identity=None)
        _fault_hook("before_session_commit_marker")
        published = atomic_write_reserved_bytes(
            path=root / "session.json",
            payload=sealed.canonical_json,
            expected_parent_identity=root_identity,
            expected_predecessor_identity=None,
            expected_predecessor_sha256=None,
            maximum_size=LIVE_START_SESSION_MAX_BYTES,
        )
        _fault_hook("after_session_commit_marker")
        if path_identity(lock_path) != lock_identity:
            raise SessionConflictError("live_start_session_lock_changed")
        return _load_session_bytes(
            sealed.canonical_json,
            session_identity=published.identity,
        )


@contextmanager
def lease_live_start_session(
    session_root: Path,
    *,
    local_app_data_root: Path | None = None,
) -> Iterator[LiveStartSessionLease]:
    root = _canonical_absolute_root(session_root, field="session_root")
    local_root = _resolve_local_app_data_root(local_app_data_root)
    run_id = root.name
    _require_run_id(run_id)
    expected_root = local_root / "HSConfig" / "runs" / run_id
    if root != expected_root:
        raise SessionValidationError(
            "live_start_session_root_not_canonical"
        )
    _validate_existing_plain_ancestor_chain(local_root)
    lock_path = _session_lock_path(root)
    if not os.path.lexists(root) or not os.path.lexists(lock_path):
        raise FileNotFoundError("live_start_session_authority_missing")
    _require_existing_live_start_root_ancestry(
        local_root=local_root,
        session_root=root,
    )
    root_identity = path_identity(root)
    lock_parent_identity = path_identity(lock_path.parent)
    with ExclusiveFileLock(
        lock_path,
        expected_parent_identity=lock_parent_identity,
        create_if_missing=False,
    ) as session_lock:
        lock_identity = path_identity(lock_path)
        lock_status = lock_path.lstat()
        if lock_status.st_size != 0:
            raise SessionLayoutError("live_start_session_lock_not_empty")
        try:
            session_lock.validate_no_alternate_data_streams(
                expected_size=0
            )
        except (OSError, ValueError) as error:
            raise SessionLayoutError(
                "live_start_layout_alternate_stream_forbidden"
            ) from error
        if path_identity(root) != root_identity:
            raise SessionConflictError("live_start_session_root_changed")
        _validate_authority_root_paths_no_ads(
            root=root,
            lock_path=lock_path,
        )
        bearer = _SessionBearer(
            session_root=root,
            session_root_identity=root_identity,
            session_lock_path=lock_path,
            session_lock_identity=lock_identity,
            session_lock=session_lock,
        )
        token = SessionLockToken._mint(bearer)
        _register_session_context(bearer=bearer, token=token)
        lease = LiveStartSessionLease(
            session_root=root,
            session_root_identity=root_identity,
            session_lock_path=lock_path,
            session_lock_identity=lock_identity,
            lock_token=token,
        )
        try:
            _require_session_lease(lease)
            yield lease
        finally:
            # Invalidate authority before the OS lock is released.
            _deactivate_opaque_bearers_for_session(bearer)
            _deregister_session_context(bearer=bearer)
            bearer.active = False
            bearer.nonce = ""


def load_live_start_session(
    session_root: Path,
    *,
    local_app_data_root: Path | None = None,
) -> LiveStartSession:
    with lease_live_start_session(
        session_root,
        local_app_data_root=local_app_data_root,
    ) as lease:
        return load_live_start_session_under_lock(session_lease=lease)


def load_live_start_session_under_lock(
    *,
    session_lease: LiveStartSessionLease,
) -> LiveStartSession:
    _require_session_lease(session_lease)
    _reconcile_session_temp_under_lock(session_lease=session_lease)
    path = session_lease.session_root / "session.json"
    raw, identity = _read_bound_file(
        path,
        expected_parent_identity=session_lease.session_root_identity,
        maximum_size=LIVE_START_SESSION_MAX_BYTES,
    )
    session = _load_session_bytes(raw, session_identity=identity)
    if session.run_id != session_lease.session_root.name:
        raise SessionValidationError("live_start_session_run_id_mismatch")
    _validate_run_layout_under_lock(
        session_lease=session_lease,
        session=session,
    )
    _validate_bound_artifacts_under_lock(
        session_lease=session_lease,
        session=session,
    )
    return session


def update_session_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    update: LiveStartSessionUpdate,
) -> LiveStartSession:
    return _update_session_under_lock(
        session_lease=session_lease,
        expected_session=expected_session,
        update=update,
        transition_authority=None,
    )


def _update_session_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    update: LiveStartSessionUpdate,
    transition_authority: object | None,
) -> LiveStartSession:
    _require_session_lease(session_lease)
    if not isinstance(expected_session, LiveStartSession):
        raise TypeError("live_start_expected_session_invalid")
    if not isinstance(update, LiveStartSessionUpdate):
        raise TypeError("live_start_session_update_invalid")
    _reconcile_session_temp_under_lock(
        session_lease=session_lease,
        expected_session=expected_session,
    )
    current = _load_expected_predecessor_under_lock(
        session_lease=session_lease,
        expected_session=expected_session,
    )
    _validate_run_layout_under_lock(
        session_lease=session_lease,
        session=current,
    )
    successor = _build_session_successor(
        current=current,
        update=update,
        transition_authority=transition_authority,
    )
    return _publish_session_successor_under_lock(
        session_lease=session_lease,
        current=current,
        successor=successor,
    )


def _build_session_successor(
    *,
    current: LiveStartSession,
    update: LiveStartSessionUpdate,
    transition_authority: object | None,
) -> LiveStartSession:
    successor_value = _apply_session_update(
        current,
        update,
        transition_authority=transition_authority,
    )
    return _seal_session_value(successor_value, session_identity=None)


def _publish_session_successor_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    current: LiveStartSession,
    successor: LiveStartSession,
) -> LiveStartSession:
    try:
        published = atomic_write_reserved_bytes(
            path=session_lease.session_root / "session.json",
            payload=successor.canonical_json,
            expected_parent_identity=session_lease.session_root_identity,
            expected_predecessor_identity=current.session_identity,
            expected_predecessor_sha256=_bytes_sha256(current.canonical_json),
            maximum_size=LIVE_START_SESSION_MAX_BYTES,
        )
    except AtomicWriteConflictError as error:
        raise SessionConflictError("live_start_session_cas_conflict") from error
    return _load_session_bytes(
        successor.canonical_json,
        session_identity=published.identity,
    )


def transition_live_start_session_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    event: str,
    changes: Mapping[str, Any] | None = None,
) -> LiveStartSession:
    return update_session_under_lock(
        session_lease=session_lease,
        expected_session=expected_session,
        update=LiveStartSessionUpdate(event=event, changes=changes or {}),
    )


def _transition_receipt_authorized_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    event: str,
    changes: Mapping[str, Any] | None = None,
) -> LiveStartSession:
    return _update_session_under_lock(
        session_lease=session_lease,
        expected_session=expected_session,
        update=LiveStartSessionUpdate(event=event, changes=changes or {}),
        transition_authority=_INTERNAL_TRANSITION_AUTHORITY,
    )


def _transition_validated_apply_started_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    changes: Mapping[str, Any],
) -> LiveStartSession:
    """Publish the prevalidated receipt-committed cursor without layout I/O."""

    _require_session_lease(session_lease)
    if not isinstance(expected_session, LiveStartSession):
        raise TypeError("live_start_expected_session_invalid")
    _reconcile_session_temp_under_lock(
        session_lease=session_lease,
        expected_session=expected_session,
    )
    current = _load_expected_predecessor_under_lock(
        session_lease=session_lease,
        expected_session=expected_session,
    )
    successor = _build_session_successor(
        current=current,
        update=LiveStartSessionUpdate(
            event="apply_started",
            changes=changes,
        ),
        transition_authority=_INTERNAL_TRANSITION_AUTHORITY,
    )
    return _publish_session_successor_under_lock(
        session_lease=session_lease,
        current=current,
        successor=successor,
    )


def validate_resume_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_deck_code_sha256: str,
    expected_input_snapshot_manifest_sha256: str,
    expected_runtime_grammar_version: str | None = None,
    expected_compiler_contract_id: str | None = None,
) -> LiveStartSession:
    """Reread every bound completed artifact and reject frozen-input drift."""

    session = load_live_start_session_under_lock(session_lease=session_lease)
    if (
        session.deck_code_sha256 != expected_deck_code_sha256
        or session.input_snapshot_manifest_sha256
        != expected_input_snapshot_manifest_sha256
    ):
        raise SessionConflictError("live_start_resume_frozen_input_drift")
    if (
        expected_runtime_grammar_version is not None
        or expected_compiler_contract_id is not None
    ):
        manifest_path = (
            session_lease.session_root / "inputs/input_snapshot_manifest.json"
        )
        raw, _identity = _read_bound_file(
            manifest_path,
            expected_parent_identity=path_identity(manifest_path.parent),
            maximum_size=256 * 1024,
        )
        value = _decode_frozen_input_json(raw)
        compiler_inputs = value.get("compiler_inputs")
        if not isinstance(compiler_inputs, dict):
            raise SessionValidationError("live_start_snapshot_manifest_invalid")
        if (
            expected_runtime_grammar_version is not None
            and compiler_inputs.get("runtime_grammar_version")
            != expected_runtime_grammar_version
        ) or (
            expected_compiler_contract_id is not None
            and compiler_inputs.get("compiler_contract_id")
            != expected_compiler_contract_id
        ):
            raise SessionConflictError("live_start_resume_compiler_drift")
    _validate_completed_phase_receipts(session_lease=session_lease, session=session)
    return session


def _validate_bound_artifacts_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    session: LiveStartSession,
) -> None:
    for logical_path, digest in session.artifact_bindings.items():
        artifact_path = session_lease.session_root / logical_path
        if not os.path.lexists(artifact_path):
            if _review_revision_candidate_receipt_cleanup_pending(
                session=session,
                logical_path=logical_path,
                artifact_path=artifact_path,
            ):
                continue
            raise SessionConflictError(
                "live_start_resume_artifact_missing"
            )
        maximum_size = LIVE_START_FROZEN_INPUT_MAXIMUM_BYTES.get(
            logical_path,
            64 * 1024 * 1024,
        )
        raw, _identity = _read_bound_file(
            artifact_path,
            expected_parent_identity=path_identity(artifact_path.parent),
            maximum_size=maximum_size,
        )
        if _bytes_sha256(raw) != digest:
            raise SessionConflictError("live_start_resume_artifact_drift")


def _review_revision_candidate_receipt_cleanup_pending(
    *,
    session: LiveStartSession,
    logical_path: str,
    artifact_path: Path,
) -> bool:
    if logical_path != "receipts/candidate_validation.json":
        return False
    pending = session.pending_transition
    if (
        not isinstance(pending, Mapping)
        or pending.get("operation") != "review_revision"
        or pending.get("stage") != "PRIMARY_APPLIED"
        or pending.get("external_file_action") is not None
    ):
        return False
    actions = pending.get("actions")
    if not isinstance(actions, (list, tuple)) or len(actions) != 1:
        return False
    row = actions[0]
    successor_bindings = pending.get("successor_artifact_bindings")
    return (
        isinstance(row, Mapping)
        and isinstance(successor_bindings, Mapping)
        and Path(str(row.get("path"))) == artifact_path.absolute()
        and row.get("historical_sha256")
        == session.artifact_bindings.get(logical_path)
        and logical_path not in successor_bindings
    )


def _apply_session_update(
    session: LiveStartSession,
    update: LiveStartSessionUpdate,
    *,
    transition_authority: object | None = None,
) -> dict[str, Any]:
    value = session.to_value()
    value.pop("content_sha256")
    event = update.event
    changes = _thaw(update.changes)
    _validate_update_authority(
        session=session,
        event=event,
        changes=changes,
        transition_authority=transition_authority,
    )
    if event in _EVENT_TRANSITIONS:
        expected_source, target = _EVENT_TRANSITIONS[event]
        if session.phase is not expected_source:
            raise SessionConflictError("live_start_phase_transition_invalid")
        if target not in PHASE_TRANSITIONS[session.phase]:
            raise SessionValidationError("live_start_phase_table_invalid")
        value["phase"] = target.value
    elif event == "same_phase_cas":
        target = session.phase
    elif event == "bind_terminal":
        target = session.phase
        if session.pending_transition is not None or session.apply_recovery is not None:
            raise SessionConflictError("live_start_terminal_cursor_not_closed")
    else:
        raise SessionValidationError("live_start_session_event_invalid")

    permitted_changes = {
        "artifact_bindings",
        "pending_transition",
        "prepublication_work_binding",
        "output_operation_admission_binding",
        "output_child_binding",
        "publication_binding",
        "apply_invocation_sha256",
        "runtime_admission_binding",
        "runtime_layout_bootstrap",
        "apply_recovery",
        "closed_apply_recovery_commitment",
        "result_intent",
        "attempt_acknowledgement",
        "terminal_retirement",
        "terminal_status",
    }
    if set(changes) - permitted_changes:
        raise SessionValidationError("live_start_session_update_fields_invalid")
    for key, item in changes.items():
        value[key] = item

    if event in {"technical_failure", "review_revision"}:
        if (
            session.revisions_used >= 2
            or session.candidate_revision >= 3
            or session.revisions_used != session.candidate_revision - 1
        ):
            raise SessionConflictError("live_start_candidate_revision_budget_exhausted")
        value["revisions_used"] = session.revisions_used + 1
        if event == "technical_failure":
            bindings = dict(value["artifact_bindings"])
            for logical in _DOWNSTREAM_REVISION_ARTIFACTS:
                bindings.pop(logical, None)
            value["artifact_bindings"] = bindings
    elif event == "replacement_draft":
        expected_revision = session.candidate_revision + 1
        previous_candidate = session.artifact_bindings.get(
            "starter/starter_config_candidate.json"
        )
        replacement_candidate = value["artifact_bindings"].get(
            "starter/starter_config_candidate.json"
        )
        if (
            session.revisions_used != expected_revision - 1
            or expected_revision > 3
            or previous_candidate is None
            or replacement_candidate == previous_candidate
        ):
            raise SessionConflictError(
                "live_start_candidate_revision_or_candidate_invalid"
            )
        value["candidate_revision"] = expected_revision
        bindings = dict(value["artifact_bindings"])
        for logical in _DOWNSTREAM_REVISION_ARTIFACTS:
            bindings.pop(logical, None)
        value["artifact_bindings"] = bindings
    elif event not in {"same_phase_cas", "bind_terminal"}:
        if (
            value["candidate_revision"] != session.candidate_revision
            or value["revisions_used"] != session.revisions_used
        ):
            raise SessionValidationError("live_start_revision_state_changed")

    if value["preview_requested"] is not session.preview_requested:
        raise SessionValidationError("live_start_preview_requested_immutable")
    if value["deck_code_sha256"] != session.deck_code_sha256:
        raise SessionValidationError("live_start_deck_identity_immutable")
    if (
        value["input_snapshot_manifest_sha256"]
        != session.input_snapshot_manifest_sha256
    ):
        raise SessionValidationError("live_start_frozen_input_immutable")
    return value


def _validate_update_authority(
    *,
    session: LiveStartSession,
    event: str,
    changes: Mapping[str, Any],
    transition_authority: object | None,
) -> None:
    internally_authorized = (
        transition_authority is _INTERNAL_TRANSITION_AUTHORITY
    )
    if transition_authority is not None and not internally_authorized:
        raise SessionCapabilityError(
            "live_start_transition_authority_forged"
        )
    if internally_authorized:
        allowed_fields = _INTERNAL_EVENT_FIELD_ALLOWLIST.get(event)
        if allowed_fields is None or set(changes) - allowed_fields:
            raise SessionCapabilityError(
                "live_start_internal_transition_authority_scope_invalid"
            )
    else:
        _validate_public_update_scope(event=event, changes=changes)
        if session.pending_transition is not None and (
            event in _PHASE_FINAL_PENDING_OPERATIONS
            or "pending_transition" in changes
        ):
            raise SessionCapabilityError(
                "live_start_pending_completion_authority_required"
            )
    expected_operation = _PHASE_FINAL_PENDING_OPERATIONS.get(event)
    if expected_operation is not None:
        pending = session.pending_transition
        if (
            not isinstance(pending, Mapping)
            or pending.get("operation") != expected_operation
            or pending.get("stage")
            not in {"PRIMARY_APPLIED", "CLEANUP_DELETING"}
            or changes.get("pending_transition", object()) is not None
        ):
            raise SessionConflictError(
                "live_start_phase_transition_intent_missing_or_invalid"
            )
        target_phase = _EVENT_TRANSITIONS[event][1].value
        if (
            pending.get("source_phase") != session.phase.value
            or pending.get("target_phase") != target_phase
            or changes.get("artifact_bindings")
            != pending.get("successor_artifact_bindings")
        ):
            raise SessionConflictError(
                "live_start_phase_transition_intent_mismatch"
            )

    if event != "same_phase_cas":
        return
    if (
        session.pending_transition is not None
        and "pending_transition" in changes
        and not internally_authorized
    ):
        raise SessionCapabilityError(
            "live_start_pending_transition_receipt_required"
        )
    predecessor_pending = session.pending_transition
    successor_pending_value = changes.get("pending_transition")
    if (
        isinstance(predecessor_pending, Mapping)
        and predecessor_pending.get("operation") == "cleanup_prepublication"
        and successor_pending_value is None
        and (
            predecessor_pending.get("stage") != "CLEANUP_DELETING"
            or predecessor_pending.get("cleanup_cursor")
            != predecessor_pending.get("cleanup_entry_count")
        )
    ):
        raise SessionCapabilityError(
            "live_start_prepublication_cleanup_incomplete"
        )
    if (
        isinstance(predecessor_pending, Mapping)
        and predecessor_pending.get("operation") == "cleanup_prepublication"
        and isinstance(successor_pending_value, Mapping)
        and successor_pending_value.get("operation")
        == "cleanup_prepublication"
    ):
        _validate_prepublication_cleanup_pending_successor(
            predecessor=predecessor_pending,
            successor=successor_pending_value,
        )
    if (
        isinstance(predecessor_pending, Mapping)
        and predecessor_pending.get("operation")
        == "materialize_prepublication_work"
    ):
        _validate_prepublication_materialization_successor(
            predecessor=predecessor_pending,
            successor=successor_pending_value,
            successor_work_binding=changes.get(
                "prepublication_work_binding"
            ),
        )
    if (
        isinstance(predecessor_pending, Mapping)
        and predecessor_pending.get("operation")
        == "install_apply_invocation"
        and "pending_transition" in changes
    ):
        _validate_apply_invocation_pending_successor(
            predecessor=predecessor_pending,
            successor=successor_pending_value,
        )
    for field_name, successor in changes.items():
        predecessor = getattr(session, field_name)
        if successor == predecessor:
            if successor is None:
                raise SessionValidationError(
                    "live_start_same_phase_null_authority_invalid"
                )
            raise SessionValidationError(
                "live_start_same_phase_noop_invalid"
            )
    successor_pending = changes.get("pending_transition", object())
    if (
        session.pending_transition is None
        and isinstance(successor_pending, Mapping)
        and successor_pending.get("stage") != "PREPARED"
    ):
        raise SessionValidationError(
            "live_start_pending_initial_stage_invalid"
        )


def _validate_apply_invocation_pending_successor(
    *,
    predecessor: Mapping[str, Any],
    successor: Any,
) -> None:
    current = validate_embedded_document(
        "pending_transition",
        predecessor,
    )
    if successor is None:
        if (
            current.get("stage") != "PREPARED"
            or not isinstance(current.get("external_file_action"), Mapping)
            or current["external_file_action"].get("stage") != "PLANNED"
            or any(
                current.get(field_name) is not None
                for field_name in (
                    "runtime_admission_staging_identity",
                    "runtime_admission_staging_size",
                    "runtime_admission_staging_sha256",
                    "runtime_admission_identity",
                    "runtime_admission_sha256",
                )
            )
        ):
            raise SessionCapabilityError(
                "live_start_apply_invocation_rollback_invalid"
            )
        return
    if not isinstance(successor, Mapping):
        raise SessionCapabilityError(
            "live_start_apply_invocation_successor_invalid"
        )
    next_value = validate_embedded_document(
        "pending_transition",
        successor,
    )
    mutable = {
        "stage",
        "next_action_index",
        "external_file_action",
        "runtime_admission_staging_identity",
        "runtime_admission_staging_size",
        "runtime_admission_staging_sha256",
        "runtime_admission_identity",
        "runtime_admission_sha256",
        "content_sha256",
    }
    for field_name in _PENDING_TRANSITION_FIELDS - mutable:
        if current.get(field_name) != next_value.get(field_name):
            raise SessionCapabilityError(
                "live_start_apply_invocation_successor_changed"
            )

    current_stage = current.get("stage")
    next_stage = next_value.get("stage")
    current_external = current.get("external_file_action")
    next_external = next_value.get("external_file_action")
    unchanged_runtime_fields = all(
        current.get(field_name) == next_value.get(field_name)
        for field_name in (
            "runtime_admission_staging_identity",
            "runtime_admission_staging_size",
            "runtime_admission_staging_sha256",
            "runtime_admission_identity",
            "runtime_admission_sha256",
        )
    )

    prepared_cleanup = (
        current_stage == next_stage == "PREPARED"
        and isinstance(current_external, Mapping)
        and isinstance(next_external, Mapping)
        and current_external.get("stage")
        == next_external.get("stage")
        == "PLANNED"
        and current_external.get("action_kind")
        == next_external.get("action_kind")
        == "materialize_runtime_admission_staging"
        and next_external.get("action_index")
        == current_external.get("action_index") + 1
        and _external_action_unchanged_except(
            predecessor=current_external,
            successor=next_external,
            mutable={"action_index", "content_sha256"},
        )
        and unchanged_runtime_fields
        and current.get("next_action_index")
        == next_value.get("next_action_index")
    )
    admission_staging_bound = (
        current_stage == "PREPARED"
        and next_stage == "STAGING_BOUND"
        and isinstance(current_external, Mapping)
        and isinstance(next_external, Mapping)
        and current_external.get("action_kind")
        == "materialize_runtime_admission_staging"
        and current_external.get("stage") == "PLANNED"
        and next_external.get("action_kind")
        == "commit_bound_runtime_admission"
        and next_external.get("stage") == "STAGING_BOUND"
        and _external_action_unchanged_except(
            predecessor=current_external,
            successor=next_external,
            mutable={
                "action_kind",
                "stage",
                "staging_identity",
                "staging_size",
                "staging_sha256",
                "content_sha256",
            },
        )
        and current.get("runtime_admission_staging_identity") is None
        and next_value.get("runtime_admission_staging_identity") is not None
        and current.get("runtime_admission_identity") is None
        and next_value.get("runtime_admission_identity") is None
        and current.get("next_action_index")
        == next_value.get("next_action_index")
    )
    admission_committed = (
        current_stage == "STAGING_BOUND"
        and next_stage == "PRIMARY_APPLIED"
        and isinstance(current_external, Mapping)
        and current_external.get("action_kind")
        == "commit_bound_runtime_admission"
        and current_external.get("stage") == "STAGING_BOUND"
        and next_external is None
        and current.get("runtime_admission_identity") is None
        and next_value.get("runtime_admission_identity")
        == current.get("runtime_admission_staging_identity")
        and next_value.get("runtime_admission_sha256")
        == current.get("runtime_admission_staging_sha256")
        and current.get("next_action_index")
        == next_value.get("next_action_index")
    )
    receipt_intent_installed = (
        current_stage == next_stage == "PRIMARY_APPLIED"
        and current_external is None
        and isinstance(next_external, Mapping)
        and next_external.get("action_kind")
        == "materialize_invocation_receipt_staging"
        and next_external.get("stage") == "PLANNED"
        and unchanged_runtime_fields
        and current.get("next_action_index")
        == next_value.get("next_action_index")
        == 0
    )
    receipt_cleanup = (
        current_stage == next_stage == "PRIMARY_APPLIED"
        and isinstance(current_external, Mapping)
        and isinstance(next_external, Mapping)
        and current_external.get("action_kind")
        == next_external.get("action_kind")
        == "materialize_invocation_receipt_staging"
        and current_external.get("stage")
        == next_external.get("stage")
        == "PLANNED"
        and next_external.get("action_index")
        == current_external.get("action_index") + 1
        and _external_action_unchanged_except(
            predecessor=current_external,
            successor=next_external,
            mutable={"action_index", "content_sha256"},
        )
        and unchanged_runtime_fields
        and current.get("next_action_index")
        == next_value.get("next_action_index")
    )
    receipt_staging_bound = (
        current_stage == next_stage == "PRIMARY_APPLIED"
        and isinstance(current_external, Mapping)
        and isinstance(next_external, Mapping)
        and current_external.get("action_kind")
        == "materialize_invocation_receipt_staging"
        and current_external.get("stage") == "PLANNED"
        and next_external.get("action_kind")
        == "commit_bound_invocation_receipt"
        and next_external.get("stage") == "STAGING_BOUND"
        and _external_action_unchanged_except(
            predecessor=current_external,
            successor=next_external,
            mutable={
                "action_kind",
                "stage",
                "staging_identity",
                "staging_size",
                "staging_sha256",
                "content_sha256",
            },
        )
        and unchanged_runtime_fields
        and current.get("next_action_index")
        == next_value.get("next_action_index")
    )
    receipt_committed = (
        current_stage == next_stage == "PRIMARY_APPLIED"
        and isinstance(current_external, Mapping)
        and current_external.get("action_kind")
        == "commit_bound_invocation_receipt"
        and current_external.get("stage") == "STAGING_BOUND"
        and next_external is None
        and unchanged_runtime_fields
        and next_value.get("next_action_index")
        == current.get("next_action_index") + 1
    )
    if not any(
        (
            prepared_cleanup,
            admission_staging_bound,
            admission_committed,
            receipt_intent_installed,
            receipt_cleanup,
            receipt_staging_bound,
            receipt_committed,
        )
    ):
        raise SessionCapabilityError(
            "live_start_apply_invocation_successor_invalid"
        )


def _external_action_unchanged_except(
    *,
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    mutable: set[str],
) -> bool:
    return all(
        predecessor.get(field_name) == successor.get(field_name)
        for field_name in _EXTERNAL_FILE_ACTION_FIELDS - mutable
    )


def _validate_prepublication_materialization_successor(
    *,
    predecessor: Mapping[str, Any],
    successor: Any,
    successor_work_binding: Any,
) -> None:
    current = validate_embedded_document(
        "pending_transition",
        predecessor,
    )
    current_stage = current.get("stage")
    if successor is None:
        actions = current.get("actions")
        normalized_work_binding = _normalize_json(successor_work_binding)
        if isinstance(normalized_work_binding, dict):
            _validate_prepublication_work_binding(normalized_work_binding)
        if (
            current_stage != "PRIMARY_APPLIED"
            or not isinstance(actions, tuple)
            or current.get("next_action_index") != len(actions)
            or not isinstance(normalized_work_binding, dict)
            or set(normalized_work_binding)
            != _PREPUBLICATION_WORK_BINDING_FIELDS
            or normalized_work_binding.get("work_parent_path")
            != current.get("work_parent_path")
            or tuple(normalized_work_binding.get("work_parent_identity", ()))
            != tuple(current.get("work_parent_identity", ()))
            or normalized_work_binding.get("work_root")
            != current.get("work_root")
            or tuple(normalized_work_binding.get("work_root_identity", ()))
            != tuple(current.get("work_root_identity", ()))
        ):
            raise SessionCapabilityError(
                "live_start_prepublication_materialization_completion_invalid"
            )
        return
    if not isinstance(successor, Mapping):
        raise SessionCapabilityError(
            "live_start_prepublication_materialization_successor_invalid"
        )
    next_value = validate_embedded_document(
        "pending_transition",
        successor,
    )
    mutable = {"stage", "work_root_identity", "next_action_index", "content_sha256"}
    for field_name in _PENDING_TRANSITION_FIELDS - mutable:
        if current.get(field_name) != next_value.get(field_name):
            raise SessionCapabilityError(
                "live_start_prepublication_materialization_successor_changed"
            )
    if successor_work_binding is not None:
        raise SessionCapabilityError(
            "live_start_prepublication_materialization_successor_invalid"
        )
    if current_stage == "PREPARED":
        valid = (
            next_value.get("stage") == "PRIMARY_APPLIED"
            and current.get("work_root_identity") is None
            and next_value.get("work_root_identity") is not None
            and current.get("next_action_index") == 0
            and next_value.get("next_action_index") == 0
        )
    else:
        valid = (
            current_stage == next_value.get("stage") == "PRIMARY_APPLIED"
            and current.get("work_root_identity")
            == next_value.get("work_root_identity")
            and next_value.get("next_action_index")
            == current.get("next_action_index") + 1
        )
    if not valid:
        raise SessionCapabilityError(
            "live_start_prepublication_materialization_successor_invalid"
        )


def _validate_public_update_scope(
    *,
    event: str,
    changes: Mapping[str, Any],
) -> None:
    if event == "review_revision":
        raise SessionCapabilityError(
            "live_start_review_revision_specialized_authority_required"
        )
    if event in {"apply_committed", "runtime_matched", "bind_terminal"}:
        raise SessionCapabilityError(
            "live_start_specialized_transition_authority_required"
        )
    pending = changes.get("pending_transition")
    if (
        isinstance(pending, Mapping)
        and pending.get("operation") == "review_revision"
    ):
        raise SessionCapabilityError(
            "live_start_review_revision_specialized_authority_required"
        )
    if set(changes) & _PUBLIC_SENSITIVE_UPDATE_FIELDS:
        raise SessionCapabilityError(
            "live_start_specialized_field_authority_required"
        )


def _validate_prepublication_cleanup_pending_successor(
    *,
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
) -> None:
    current = validate_embedded_document(
        "pending_transition",
        predecessor,
    )
    next_value = validate_embedded_document(
        "pending_transition",
        successor,
    )
    mutable = {
        "stage",
        "external_file_action",
        "cleanup_inventory_identity",
        "quarantine_identity",
        "cleanup_cursor",
        "content_sha256",
    }
    for field_name in _PENDING_TRANSITION_FIELDS - mutable:
        if current.get(field_name) != next_value.get(field_name):
            raise SessionCapabilityError(
                "live_start_prepublication_cleanup_successor_changed"
            )
    source_stage = current.get("stage")
    target_stage = next_value.get("stage")
    current_external = current.get("external_file_action")
    next_external = next_value.get("external_file_action")
    if source_stage == "PREPARED" and target_stage == "PREPARED":
        if not isinstance(current_external, Mapping) or not isinstance(
            next_external,
            Mapping,
        ):
            raise SessionCapabilityError(
                "live_start_prepublication_cleanup_successor_invalid"
            )
        for field_name in _EXTERNAL_FILE_ACTION_FIELDS - {
            "action_index",
            "content_sha256",
        }:
            if current_external.get(field_name) != next_external.get(
                field_name
            ):
                raise SessionCapabilityError(
                    "live_start_prepublication_cleanup_successor_changed"
                )
        if next_external.get("action_index") != (
            current_external.get("action_index") + 1
        ):
            raise SessionCapabilityError(
                "live_start_prepublication_cleanup_successor_invalid"
            )
        return
    if source_stage == "PREPARED" and target_stage == "STAGING_BOUND":
        if (
            not isinstance(current_external, Mapping)
            or not isinstance(next_external, Mapping)
            or current_external.get("action_kind")
            != "materialize_prepublication_cleanup_inventory_staging"
            or next_external.get("action_kind")
            != "commit_bound_prepublication_cleanup_inventory"
            or current_external.get("stage") != "PLANNED"
            or next_external.get("stage") != "STAGING_BOUND"
            or current_external.get("action_index")
            != next_external.get("action_index")
        ):
            raise SessionCapabilityError(
                "live_start_prepublication_cleanup_successor_invalid"
            )
        for field_name in _EXTERNAL_FILE_ACTION_FIELDS - {
            "action_kind",
            "stage",
            "staging_identity",
            "staging_size",
            "staging_sha256",
            "content_sha256",
        }:
            if current_external.get(field_name) != next_external.get(
                field_name
            ):
                raise SessionCapabilityError(
                    "live_start_prepublication_cleanup_successor_changed"
                )
        return
    if source_stage == "STAGING_BOUND" and target_stage == "PRIMARY_APPLIED":
        if (
            not isinstance(current_external, Mapping)
            or next_external is not None
            or next_value.get("cleanup_inventory_identity")
            != current_external.get("staging_identity")
            or next_value.get("quarantine_identity") is not None
            or next_value.get("cleanup_cursor") != 0
        ):
            raise SessionCapabilityError(
                "live_start_prepublication_cleanup_successor_invalid"
            )
        return
    if source_stage == "PRIMARY_APPLIED" and target_stage == "CLEANUP_DELETING":
        if (
            current_external is not None
            or next_external is not None
            or current.get("cleanup_inventory_identity")
            != next_value.get("cleanup_inventory_identity")
            or current.get("quarantine_identity") is not None
            or next_value.get("quarantine_identity")
            != current.get("work_root_identity")
            or current.get("cleanup_cursor") != 0
            or next_value.get("cleanup_cursor") != 0
        ):
            raise SessionCapabilityError(
                "live_start_prepublication_cleanup_successor_invalid"
            )
        return
    if source_stage == target_stage == "CLEANUP_DELETING":
        if (
            current_external is not None
            or next_external is not None
            or current.get("cleanup_inventory_identity")
            != next_value.get("cleanup_inventory_identity")
            or current.get("quarantine_identity")
            != next_value.get("quarantine_identity")
            or next_value.get("cleanup_cursor")
            != current.get("cleanup_cursor") + 1
        ):
            raise SessionCapabilityError(
                "live_start_prepublication_cleanup_successor_invalid"
            )
        return
    raise SessionCapabilityError(
        "live_start_prepublication_cleanup_successor_invalid"
    )


def _seal_session_value(
    value: Mapping[str, Any],
    *,
    session_identity: PathIdentity | None,
) -> LiveStartSession:
    unsigned = _normalize_json(value)
    if not isinstance(unsigned, dict):
        raise SessionValidationError("live_start_session_not_object")
    unsigned.pop("content_sha256", None)
    if set(unsigned) != _SESSION_FIELDS - {"content_sha256"}:
        raise SessionValidationError("live_start_session_fields_invalid")
    content_sha256 = _self_digest(unsigned)
    sealed = {**unsigned, "content_sha256": content_sha256}
    canonical = _canonical_json(sealed)
    return _load_session_bytes(canonical, session_identity=session_identity)


def _load_session_bytes(
    raw: bytes,
    *,
    session_identity: PathIdentity | None,
) -> LiveStartSession:
    if not isinstance(raw, bytes) or len(raw) > LIVE_START_SESSION_MAX_BYTES:
        raise SessionValidationError("live_start_session_size_invalid")
    value = _decode_json_document(raw)
    if _canonical_json(value) != raw:
        raise SessionValidationError("live_start_session_not_canonical")
    if set(value) != _SESSION_FIELDS:
        raise SessionValidationError("live_start_session_fields_invalid")
    content_sha256 = value.get("content_sha256")
    unsigned = dict(value)
    unsigned.pop("content_sha256")
    if content_sha256 != _self_digest(unsigned):
        raise SessionValidationError("live_start_session_content_sha256_invalid")
    if value.get("schema_version") != LIVE_START_SESSION_SCHEMA_VERSION:
        raise SessionValidationError("live_start_session_schema_invalid")
    _require_run_id(value.get("run_id"))
    _require_deck_name(value.get("deck_name"))
    _require_sha256(value.get("deck_code_sha256"), "deck_code_sha256")
    _require_sha256(
        value.get("input_snapshot_manifest_sha256"),
        "input_snapshot_manifest_sha256",
    )
    if type(value.get("preview_requested")) is not bool:
        raise SessionValidationError("live_start_preview_requested_invalid")
    try:
        phase = LiveStartPhase(value.get("phase"))
    except (TypeError, ValueError) as error:
        raise SessionValidationError("live_start_session_phase_invalid") from error
    candidate_revision = _bounded_integer(
        value.get("candidate_revision"), 1, 3, "candidate_revision"
    )
    revisions_used = _bounded_integer(
        value.get("revisions_used"), 0, 2, "revisions_used"
    )
    if candidate_revision > revisions_used + 1:
        raise SessionValidationError("live_start_candidate_revision_state_invalid")
    artifact_bindings = _validate_artifact_bindings(value.get("artifact_bindings"))
    _validate_session_nested_documents(value=value, phase=phase)
    _validate_phase_artifact_bindings(
        value=value,
        phase=phase,
        artifact_bindings=artifact_bindings,
    )
    terminal_status = value.get("terminal_status")
    if terminal_status is not None and terminal_status not in {
        "LIVE_AND_MATCHED",
        "ALREADY_LIVE",
        "PREVIEW_READY",
        "FAILED_PRESERVED",
        "APPLIED_BUT_NOT_VERIFIED",
    }:
        # PROFILE_REQUIRED is pre-session only.
        raise SessionValidationError("live_start_terminal_status_invalid")
    return LiveStartSession(
        schema_version=LIVE_START_SESSION_SCHEMA_VERSION,
        run_id=value["run_id"],
        deck_name=value["deck_name"],
        deck_code_sha256=value["deck_code_sha256"],
        preview_requested=value["preview_requested"],
        phase=phase,
        candidate_revision=candidate_revision,
        revisions_used=revisions_used,
        input_snapshot_manifest_sha256=value[
            "input_snapshot_manifest_sha256"
        ],
        artifact_bindings=artifact_bindings,
        pending_transition=_freeze_optional_mapping(value["pending_transition"]),
        prepublication_work_binding=_freeze_optional_mapping(
            value["prepublication_work_binding"]
        ),
        output_operation_admission_binding=_freeze_optional_mapping(
            value["output_operation_admission_binding"]
        ),
        output_child_binding=_freeze_optional_mapping(value["output_child_binding"]),
        publication_binding=_freeze_optional_mapping(value["publication_binding"]),
        apply_invocation_sha256=value["apply_invocation_sha256"],
        runtime_admission_binding=_freeze_optional_mapping(
            value["runtime_admission_binding"]
        ),
        runtime_layout_bootstrap=_freeze_optional_mapping(
            value["runtime_layout_bootstrap"]
        ),
        apply_recovery=_freeze_optional_mapping(value["apply_recovery"]),
        closed_apply_recovery_commitment=_freeze_optional_mapping(
            value["closed_apply_recovery_commitment"]
        ),
        result_intent=_freeze_optional_mapping(value["result_intent"]),
        attempt_acknowledgement=_freeze_optional_mapping(
            value["attempt_acknowledgement"]
        ),
        terminal_retirement=_freeze_optional_mapping(value["terminal_retirement"]),
        terminal_status=terminal_status,
        content_sha256=content_sha256,
        canonical_json=raw,
        session_identity=session_identity,
    )


def _load_expected_predecessor_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
) -> LiveStartSession:
    path = session_lease.session_root / "session.json"
    raw, identity = _read_bound_file(
        path,
        expected_parent_identity=session_lease.session_root_identity,
        maximum_size=LIVE_START_SESSION_MAX_BYTES,
    )
    if (
        expected_session.session_identity is None
        or identity != expected_session.session_identity
        or raw != expected_session.canonical_json
    ):
        raise SessionConflictError("live_start_session_cas_stale_predecessor")
    loaded = _load_session_bytes(raw, session_identity=identity)
    if loaded.content_sha256 != expected_session.content_sha256:
        raise SessionConflictError("live_start_session_cas_stale_digest")
    return loaded


def _require_session_lease(lease: LiveStartSessionLease) -> _SessionBearer:
    if not isinstance(lease, LiveStartSessionLease):
        raise SessionCapabilityError("live_start_session_capability_forged")
    token = lease.lock_token
    if not isinstance(token, SessionLockToken) or not hasattr(token, "_bearer"):
        raise SessionCapabilityError("live_start_session_capability_forged")
    bearer = token._bearer
    if not isinstance(bearer, _SessionBearer):
        raise SessionCapabilityError("live_start_session_capability_forged")
    if not bearer.active or not bearer.nonce:
        raise SessionCapabilityError("live_start_session_capability_expired")
    registration = _session_context_registration(
        bearer=bearer,
        token=token,
    )
    if registration is None:
        raise SessionCapabilityError("live_start_session_capability_forged")
    if registration.thread_id != threading.get_ident():
        raise SessionCapabilityError("live_start_session_capability_wrong_thread")
    if (
        not _session_context_registration_matches(
            registration,
            bearer=bearer,
            token=token,
        )
        or lease.session_root != registration.session_root
        or lease.session_root_identity != registration.session_root_identity
        or lease.session_lock_path != registration.session_lock_path
        or lease.session_lock_identity != registration.session_lock_identity
        or path_identity(registration.session_root)
        != registration.session_root_identity
        or path_identity(registration.session_lock_path)
        != registration.session_lock_identity
    ):
        raise SessionCapabilityError("live_start_session_capability_context_mismatch")
    lock_status = registration.session_lock_path.lstat()
    if lock_status.st_size != 0:
        raise SessionCapabilityError(
            "live_start_session_capability_lock_invalid"
        )
    try:
        registration.session_lock.validate_no_alternate_data_streams(
            expected_size=0
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise SessionCapabilityError(
            "live_start_session_capability_lock_invalid"
        ) from error
    if not _session_context_is_registered(bearer=bearer, token=token):
        raise SessionCapabilityError(
            "live_start_session_capability_context_mismatch"
        )
    return bearer


def _session_lock_path(session_root: Path) -> Path:
    return (
        session_root.parent.parent
        / "locks"
        / f"live-start-{session_root.name}.lock"
    )


def _paths_overlap(left: Path, right: Path) -> bool:
    left_mapping = _physical_identity_mapping(left)
    right_mapping = _physical_identity_mapping(right)
    return _identity_mappings_overlap(
        left_identities=left_mapping[0],
        left_remaining=left_mapping[1],
        right_identities=right_mapping[0],
        right_remaining=right_mapping[1],
    )


def _physical_identity_mapping(
    path: Path,
) -> tuple[tuple[PathIdentity, ...], tuple[str, ...]]:
    nearest_existing = Path(path)
    remaining: list[str] = []
    while not os.path.lexists(nearest_existing):
        if len(remaining) >= _PHYSICAL_IDENTITY_MAX_MISSING_COMPONENTS:
            raise SessionValidationError(
                "live_start_physical_identity_mapping_missing_bound_exceeded"
            )
        parent = nearest_existing.parent
        if parent == nearest_existing:
            raise FileNotFoundError(nearest_existing)
        remaining.append(nearest_existing.name)
        nearest_existing = parent

    identities: list[PathIdentity] = []
    current = nearest_existing
    while True:
        if len(identities) >= _PHYSICAL_IDENTITY_MAX_ANCESTOR_ROWS:
            raise SessionValidationError(
                "live_start_physical_identity_mapping_ancestor_bound_exceeded"
            )
        try:
            require_plain_directory(current)
            require_same_identity_resolution(current)
            identity = path_identity(current)
        except (OSError, ValueError) as error:
            raise SessionLayoutError(
                "live_start_physical_identity_mapping_ancestor_invalid"
            ) from error
        identities.append(identity)
        parent = current.parent
        if parent == current:
            break
        current = parent
    return tuple(identities), tuple(reversed(remaining))


def _identity_mappings_overlap(
    *,
    left_identities: tuple[PathIdentity, ...],
    left_remaining: tuple[str, ...],
    right_identities: tuple[PathIdentity, ...],
    right_remaining: tuple[str, ...],
) -> bool:
    if not left_identities or not right_identities:
        raise SessionValidationError(
            "live_start_physical_identity_mapping_empty"
        )
    if not left_remaining and not right_remaining:
        return (
            left_identities[0] in right_identities
            or right_identities[0] in left_identities
        )
    if not left_remaining:
        return left_identities[0] in right_identities
    if not right_remaining:
        return right_identities[0] in left_identities
    if left_identities[0] != right_identities[0]:
        return False
    left_suffix = tuple(os.path.normcase(part) for part in left_remaining)
    right_suffix = tuple(os.path.normcase(part) for part in right_remaining)
    shortest = min(len(left_suffix), len(right_suffix))
    return left_suffix[:shortest] == right_suffix[:shortest]


def _require_existing_live_start_root_ancestry(
    *,
    local_root: Path,
    session_root: Path,
) -> None:
    state_root = local_root / "HSConfig"
    runs_root = state_root / "runs"
    local_mapping = _physical_identity_mapping(local_root)
    state_mapping = _physical_identity_mapping(state_root)
    runs_mapping = _physical_identity_mapping(runs_root)
    session_mapping = _physical_identity_mapping(session_root)
    if any(
        remaining
        for _identities, remaining in (
            local_mapping,
            state_mapping,
            runs_mapping,
            session_mapping,
        )
    ):
        raise SessionValidationError(
            "live_start_session_physical_ancestry_missing"
        )
    if (
        state_mapping[0][1:] != local_mapping[0]
        or runs_mapping[0][1:] != state_mapping[0]
        or session_mapping[0][1:] != runs_mapping[0]
    ):
        raise SessionValidationError(
            "live_start_session_physical_ancestry_invalid"
        )


def _validate_existing_plain_ancestor_chain(path: Path) -> None:
    _physical_identity_mapping(path)


def _validate_existing_creation_authority_roots_no_ads(
    *paths: Path,
) -> None:
    if os.name != "nt":
        return
    for path in paths:
        candidate = Path(path).absolute()
        if not os.path.lexists(candidate):
            continue
        status = candidate.lstat()
        if not stat.S_ISDIR(status.st_mode) or status_is_reparse(status):
            raise SessionLayoutError("live_start_directory_invalid")
        _validate_path_no_ads(
            candidate,
            status=status,
            directory=True,
        )


def _require_or_create_plain_directory(path: Path) -> PathIdentity:
    directory = Path(path).absolute()
    if not os.path.lexists(directory):
        parent = directory.parent
        if not os.path.lexists(parent):
            _require_or_create_plain_directory(parent)
        return secure_create_directory(
            directory,
            expected_parent_identity=path_identity(parent),
        )
    status = directory.lstat()
    if not stat.S_ISDIR(status.st_mode) or status_is_reparse(status):
        raise SessionLayoutError("live_start_directory_invalid")
    return path_identity_from_status(status)


def _read_bound_file(
    path: Path,
    *,
    expected_parent_identity: PathIdentity,
    maximum_size: int,
) -> tuple[bytes, PathIdentity]:
    return _read_bound_file_with_links(
        path,
        expected_parent_identity=expected_parent_identity,
        maximum_size=maximum_size,
        allowed_links=frozenset({1}),
    )


def _read_bound_file_with_links(
    path: Path,
    *,
    expected_parent_identity: PathIdentity,
    maximum_size: int,
    allowed_links: frozenset[int],
) -> tuple[bytes, PathIdentity]:
    if not allowed_links or any(
        type(link_count) is not int or link_count < 1
        for link_count in allowed_links
    ):
        raise ValueError("live_start_allowed_link_count_invalid")
    status = Path(path).lstat()
    identity = path_identity_from_status(status)
    if (
        not stat.S_ISREG(status.st_mode)
        or status_is_reparse(status)
        or status.st_nlink not in allowed_links
        or status.st_size > maximum_size
        or path_identity(path.parent) != expected_parent_identity
    ):
        raise SessionLayoutError("live_start_file_invalid")
    if os.name == "nt":
        require_no_alternate_data_streams(
            path,
            expected_identity=identity,
            expected_parent_identity=expected_parent_identity,
            directory=False,
            expected_size=status.st_size,
        )
    descriptor = secure_open_file_descriptor(
        path,
        create=False,
        write=False,
        expected_parent_identity=expected_parent_identity,
    )
    try:
        opened = os.fstat(descriptor)
        if path_identity_from_status(opened) != identity:
            raise SessionConflictError("live_start_file_identity_changed")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            raw = handle.read(maximum_size + 1)
        after = os.fstat(descriptor)
        if (
            path_identity_from_status(after) != identity
            or after.st_size != len(raw)
            or after.st_nlink not in allowed_links
        ):
            raise SessionConflictError("live_start_file_changed")
    finally:
        os.close(descriptor)
    return raw, identity


_PENDING_TRANSITION_FIELDS = frozenset(
    """schema_version transition_kind run_id operation stage
    expected_session_sha256 source_phase target_phase source_candidate_revision
    target_candidate_revision source_revisions_used target_revisions_used
    successor_artifact_bindings actions next_action_index external_file_action
    rendered_model_sha256 work_parent_path work_parent_identity work_root
    work_root_identity work_tree_sha256 cleanup_manifest_sha256
    cleanup_entry_count receipt_parent_path receipt_parent_identity
    cleanup_inventory_path cleanup_inventory_identity
    cleanup_inventory_size cleanup_inventory_sha256 quarantine_path
    cleanup_parent_identity quarantine_identity cleanup_cursor apply_attempt_id
    apply_invocation_sha256 apply_invocation_document_size
    runtime_admission_document_size
    runtime_admission_document_sha256 runtime_admission_path
    runtime_admission_staging_path runtime_admission_staging_inner_temp_path
    runtime_admission_staging_identity runtime_admission_staging_size
    runtime_admission_staging_sha256 runtime_admission_parent_identity
    runtime_admission_identity runtime_admission_sha256 output_base_path
    output_base_identity output_operation_admission_path
    output_operation_admission_staging_path
    output_operation_admission_staging_inner_temp_path
    output_operation_admission_staging_identity
    output_operation_admission_staging_size
    output_operation_admission_staging_sha256
    output_operation_admission_parent_identity
    output_operation_admission_planned_size
    output_operation_admission_planned_sha256
    output_operation_admission_identity output_operation_admission_sha256
    output_child_path output_child_predecessor_state
    output_child_predecessor_identity planned_output_claim_size
    planned_output_claim_sha256 output_claim_path output_claim_staging_path
    output_claim_staging_inner_temp_path output_claim_parent_identity
    output_claim_staging_identity output_claim_staging_size
    output_claim_staging_sha256 output_claim_identity output_claim_sha256
    created_or_confirmed_output_child_identity output_bootstrap_lock_path
    output_bootstrap_lock_identity content_sha256""".split()
)
_APPLY_INVOCATION_PENDING_FIELDS = frozenset(
    {
        "apply_attempt_id",
        "apply_invocation_sha256",
        "apply_invocation_document_size",
        "runtime_admission_document_size",
        "runtime_admission_document_sha256",
        "runtime_admission_path",
        "runtime_admission_staging_path",
        "runtime_admission_staging_inner_temp_path",
        "runtime_admission_staging_identity",
        "runtime_admission_staging_size",
        "runtime_admission_staging_sha256",
        "runtime_admission_parent_identity",
        "runtime_admission_identity",
        "runtime_admission_sha256",
    }
)
_APPLY_INVOCATION_PENDING_ALLOWED_FIELDS = frozenset(
    {
        "schema_version",
        "transition_kind",
        "run_id",
        "operation",
        "stage",
        "expected_session_sha256",
        "source_phase",
        "target_phase",
        "source_candidate_revision",
        "target_candidate_revision",
        "source_revisions_used",
        "target_revisions_used",
        "successor_artifact_bindings",
        "actions",
        "next_action_index",
        "external_file_action",
        "content_sha256",
    }
    | _APPLY_INVOCATION_PENDING_FIELDS
)
_REVIEW_REVISION_PENDING_ALLOWED_FIELDS = frozenset(
    {
        "schema_version",
        "transition_kind",
        "run_id",
        "operation",
        "stage",
        "expected_session_sha256",
        "source_phase",
        "target_phase",
        "source_candidate_revision",
        "target_candidate_revision",
        "source_revisions_used",
        "target_revisions_used",
        "successor_artifact_bindings",
        "actions",
        "next_action_index",
        "external_file_action",
        "content_sha256",
    }
)
_REVIEW_REVISION_RETIREMENT_ACTION_FIELDS = frozenset(
    {
        "action",
        "materialization_source",
        "path",
        "parent_identity",
        "historical_identity",
        "historical_size",
        "historical_sha256",
        "directory_path",
        "directory_parent_identity",
        "directory_identity",
        "review_path",
        "review_parent_identity",
        "review_identity",
        "review_size",
        "review_sha256",
    }
)
_REVIEW_REVISION_MATERIALIZATION_SOURCE_FIELDS = frozenset(
    {"path", "parent_identity", "identity", "size", "sha256"}
)
_EXTERNAL_FILE_ACTION_FIELDS = frozenset(
    """schema_version action_kind action_index stage final_path staging_path
    inner_temp_path parent_identity predecessor_state predecessor_identity
    predecessor_size predecessor_sha256 planned_successor_size
    planned_successor_sha256 staging_identity staging_size staging_sha256
    commit_mode content_sha256""".split()
)
_OUTPUT_CHILD_BINDING_FIELDS = frozenset(
    """schema_version binding_kind run_id output_base_path output_base_identity
    output_child_path output_child_identity predecessor_state
    predecessor_output_child_identity claim_path claim_parent_identity
    claim_identity claim_sha256 claim_state content_sha256""".split()
)
_OUTPUT_OPERATION_BINDING_FIELDS = frozenset(
    """schema_version binding_kind state release_handoff_kind admission_path
    admission_parent_identity admission_identity admission_size admission_sha256
    run_id session_root session_root_identity expected_session_sha256
    operator_profile_path operator_profile_parent_identity
    operator_profile_identity operator_profile_sha256 state_root_identity
    output_base_root output_base_root_identity output_child_path
    output_child_predecessor_state output_child_predecessor_identity
    output_bootstrap_lock_path output_bootstrap_lock_identity output_claim_path
    handoff_runtime_admission_path handoff_runtime_admission_parent_identity
    handoff_runtime_admission_identity handoff_runtime_admission_sha256
    content_sha256""".split()
)
_RUNTIME_ADMISSION_BINDING_FIELDS = frozenset(
    """admission_path admission_parent_identity admission_identity
    admission_sha256 output_operation_admission_path
    output_operation_admission_identity output_operation_admission_sha256
    output_child_binding_sha256 output_child_path output_child_identity
    publication_revision publication_content_root_sha256""".split()
)
_PUBLICATION_BINDING_FIELDS = frozenset(
    {
        "output_child_path",
        "output_child_identity",
        "output_child_binding_sha256",
        "revision",
        "content_root_sha256",
        "prior_current_identity",
    }
)
_PREPUBLICATION_WORK_BINDING_FIELDS = frozenset(
    """work_parent_path work_parent_identity work_root work_root_identity
    work_tree_sha256 cleanup_manifest_sha256 cleanup_entry_count""".split()
)
_PREPUBLICATION_MATERIALIZATION_ACTION_FIELDS = frozenset(
    {"relative_path", "size", "sha256"}
)
_RUNTIME_LAYOUT_FIELDS = frozenset(
    """schema_version binding_kind run_id apply_attempt_id runtime_root
    runtime_root_identity stage next_directory_index directory_count directories
    content_sha256""".split()
)
_RUNTIME_LAYOUT_DIRECTORY_FIELDS = frozenset(
    """role path expected_parent_identity predecessor_state
    predecessor_identity successor_identity""".split()
)
_APPLY_RECOVERY_FIELDS = frozenset(
    """schema_version recovery_kind recovery_stage run_id apply_attempt_id
    apply_invocation_sha256 runtime_admission_path
    runtime_admission_parent_identity runtime_admission_identity
    runtime_admission_sha256 package_root_sha256 runtime_root
    runtime_root_identity install_route action_index expected_action
    predecessor_attempt_record_path predecessor_attempt_record_identity
    predecessor_attempt_record_sha256 predecessor_journal_path
    predecessor_journal_identity predecessor_journal_sha256
    predecessor_transaction_temp_path
    predecessor_transaction_temp_parent_identity
    predecessor_transaction_temp_identity predecessor_transaction_temp_size
    predecessor_transaction_temp_sha256
    predecessor_transaction_temp_classification
    predecessor_transaction_temp_origin external_file_action
    predecessor_target_owner_journal_path
    predecessor_target_owner_journal_identity
    predecessor_target_owner_journal_sha256 successor_attempt_record_path
    successor_attempt_record_identity successor_attempt_record_sha256
    successor_journal_path successor_journal_identity successor_journal_sha256
    successor_transaction_temp_path successor_transaction_temp_parent_identity
    successor_transaction_temp_identity successor_transaction_temp_size
    successor_transaction_temp_sha256 successor_transaction_temp_classification
    successor_transaction_temp_origin planned_journal_successor_path
    planned_journal_successor_parent_identity planned_journal_successor_phase
    planned_journal_successor_size planned_journal_successor_sha256
    successor_target_owner_journal_path successor_target_owner_journal_identity
    successor_target_owner_journal_sha256 candidate_path
    candidate_parent_identity predecessor_candidate_identity
    successor_candidate_identity candidate_tree_manifest_sha256
    candidate_tree_entry_count candidate_tree_cursor
    candidate_tree_next_relative_path candidate_tree_next_kind
    candidate_tree_next_source_identity candidate_tree_next_size
    candidate_tree_next_sha256 candidate_tree_next_parent_identity
    candidate_tree_next_successor_identity candidate_tree_verified_sha256
    renamed_target_path predecessor_renamed_target_identity
    successor_renamed_target_identity owner_retirement
    last_apply_receipt_sha256 runtime_state_sha256 deck_config_ini_sha256
    runtime_match_status runtime_match_sha256 stable_physical_disposition
    content_sha256""".split()
)
RUNTIME_LAYOUT_DIRECTORY_ROLES = (
    "custom_config",
    "transactions",
    "staging",
    "receipts",
    "state_receipts",
    "attempt_retention",
    "owner_retirements",
)
_RESULT_INTENT_FIELDS = frozenset(
    """schema_version intent_kind run_id terminal_status deck_name
    candidate_revision unique_main_deck_cards configured_cards
    deliberately_unconfigured_cards review_confidence visible_limitations
    apply_attempt_id publication_revision publication_content_root_sha256
    raw_apply_status physical_disposition runtime_match_status
    runtime_match_sha256 package_root_sha256 last_apply_receipt_sha256
    runtime_state_sha256 deck_config_ini_sha256 retained_attempt_record_path
    retained_attempt_record_identity retained_attempt_record_sha256
    retained_journal_path retained_journal_identity retained_journal_sha256
    retained_target_owner_journal_path retained_target_owner_journal_identity
    retained_target_owner_journal_sha256 retained_candidate_identity
    runtime_admission_path
    runtime_admission_parent_identity runtime_admission_identity
    runtime_admission_sha256 error_code retained_safe_state content_sha256""".split()
)
_ATTEMPT_ACK_FIELDS = frozenset(
    """schema_version acknowledgement_kind run_id apply_attempt_id
    retention_owner_run_id retention_fence_path retention_fence_identity
    retention_fence_sha256 journal_path journal_identity journal_sha256
    target_owner_journal_path target_owner_journal_identity
    target_owner_journal_sha256 target_path target_identity
    package_root_sha256 runtime_admission_path runtime_admission_parent_identity
    runtime_admission_identity runtime_admission_sha256 journal_owns_target
    acknowledgement_action content_sha256""".split()
)
_TERMINAL_RETIREMENT_FIELDS = frozenset(
    """schema_version retirement_kind run_id apply_attempt_id operation stage
    source_terminal_session_sha256 result_intent_sha256
    terminal_resolution_evidence runtime_admission_path
    runtime_admission_parent_identity runtime_admission_identity
    runtime_admission_sha256 retained_attempt_record_path
    retained_attempt_record_identity retained_attempt_record_sha256
    retained_journal_path retained_journal_identity retained_journal_sha256
    retained_target_owner_journal_path retained_target_owner_journal_identity
    retained_target_owner_journal_sha256 retained_candidate_identity
    content_sha256""".split()
)
_TERMINAL_RESOLUTION_FIELDS = frozenset(
    """schema_version resolution_kind run_id apply_attempt_id
    action_index
    predecessor_attempt_record_path predecessor_attempt_record_identity
    predecessor_attempt_record_sha256 predecessor_journal_path
    predecessor_journal_identity predecessor_journal_sha256
    predecessor_transaction_temp_path
    predecessor_transaction_temp_parent_identity
    predecessor_transaction_temp_identity predecessor_transaction_temp_size
    predecessor_transaction_temp_sha256
    predecessor_transaction_temp_classification
    predecessor_transaction_temp_origin external_file_action owner_retirement
    predecessor_target_owner_journal_path
    predecessor_target_owner_journal_identity
    predecessor_target_owner_journal_sha256
    allowed_attempt_record_successor_state allowed_journal_successor_phase
    successor_attempt_record_path successor_attempt_record_identity
    successor_attempt_record_sha256 successor_journal_path
    successor_journal_identity successor_journal_sha256
    successor_transaction_temp_path successor_transaction_temp_parent_identity
    successor_transaction_temp_identity successor_transaction_temp_size
    successor_transaction_temp_sha256 successor_transaction_temp_classification
    successor_transaction_temp_origin planned_journal_successor_path
    planned_journal_successor_parent_identity planned_journal_successor_phase
    planned_journal_successor_size planned_journal_successor_sha256
    successor_target_owner_journal_path
    successor_target_owner_journal_identity
    successor_target_owner_journal_sha256 candidate_path
    candidate_parent_identity predecessor_candidate_identity
    successor_candidate_identity resolved_physical_disposition cleanup_stage
    cleanup_inventory_path cleanup_inventory_parent_identity
    cleanup_inventory_identity cleanup_inventory_size cleanup_inventory_sha256
    cleanup_manifest_sha256 cleanup_entry_count cleanup_cursor cleanup_roots
    package_root_sha256 last_apply_receipt_sha256 runtime_state_sha256
    deck_config_ini_sha256 runtime_match_status runtime_match_sha256
    content_sha256""".split()
)
_OWNER_RETIREMENT_FIELDS = frozenset(
    """schema_version evidence_kind stage tombstone_path
    tombstone_parent_identity tombstone_identity tombstone_sha256
    retired_owner_transaction_id initial_owner_journal_path
    initial_owner_journal_identity initial_owner_journal_sha256
    current_owner_journal_identity current_owner_journal_sha256
    retired_target_path retired_target_parent_identity retired_target_identity
    retired_target_tree_sha256 successor_transaction_id
    successor_package_root_sha256 successor_owner_journal_path
    successor_owner_journal_identity successor_owner_journal_sha256
    cleanup_manifest_sha256 cleanup_entry_count cleanup_cursor
    planned_completed_tombstone_size planned_completed_tombstone_sha256
    next_entry_relative_path next_entry_kind next_entry_identity
    next_entry_parent_identity next_entry_size next_entry_sha256
    old_owner_journal_retired content_sha256""".split()
)
_OWNER_TOMBSTONE_FIELDS = frozenset(
    """schema_version record_kind state retired_owner_transaction_id
    initial_owner_journal_path initial_owner_journal_identity
    initial_owner_journal_sha256 retired_target_path
    retired_target_parent_identity retired_target_identity
    retired_target_tree_sha256 successor_transaction_id
    successor_package_root_sha256 successor_owner_journal_path
    successor_owner_journal_identity successor_owner_journal_sha256
    cleanup_manifest_sha256 cleanup_entry_count cleanup_entries
    completed_cleanup_cursor completed_owner_journal_identity
    completed_owner_journal_sha256 content_sha256""".split()
)
_OWNER_TOMBSTONE_ENTRY_FIELDS = frozenset(
    """relative_path entry_kind identity expected_parent_identity size
    sha256""".split()
)
_OWNER_ROOT_POSTCONDITION_FIELDS = frozenset(
    """target_path historical_target_identity target_parent_identity
    prepared_tombstone_path prepared_tombstone_identity
    prepared_tombstone_sha256 final_owner_journal_path
    final_owner_journal_identity final_owner_journal_sha256
    cleanup_manifest_sha256 cleanup_entry_count
    planned_completed_tombstone_size
    planned_completed_tombstone_sha256 disposition""".split()
)
_OWNER_DELETE_POSTCONDITION_FIELDS = frozenset(
    """target_path historical_target_identity target_parent_identity
    entry_relative_path entry_kind entry_identity entry_parent_identity
    entry_size entry_sha256 prepared_tombstone_path
    prepared_tombstone_identity prepared_tombstone_sha256
    current_owner_journal_path current_owner_journal_identity
    current_owner_journal_sha256 cleanup_manifest_sha256
    cleanup_entry_count cleanup_cursor disposition""".split()
)
_OWNER_OLD_JOURNAL_POSTCONDITION_FIELDS = frozenset(
    """journal_path historical_journal_identity historical_journal_sha256
    completed_tombstone_path completed_tombstone_identity
    completed_tombstone_sha256 successor_owner_journal_path
    successor_owner_journal_identity successor_owner_journal_sha256
    disposition""".split()
)
_TERMINAL_CLEANUP_INVENTORY_FIELDS = frozenset(
    """schema_version inventory_kind run_id apply_attempt_id runtime_root_path
    runtime_root_identity cleanup_roots cleanup_manifest_sha256
    cleanup_entry_count entries content_sha256""".split()
)
_TERMINAL_CLEANUP_ROOT_FIELDS = frozenset(
    {"root_role", "source_path", "source_identity", "expected_parent_identity"}
)
_TERMINAL_CLEANUP_ENTRY_FIELDS = frozenset(
    {
        "root_role",
        "relative_path",
        "entry_kind",
        "identity",
        "expected_parent_identity",
        "size",
        "sha256",
    }
)
_EXTERNAL_DOCUMENT_SPECS = MappingProxyType(
    {
        "pending_transition": (
            _PENDING_TRANSITION_FIELDS,
            LIVE_START_PENDING_TRANSITION_MAX_BYTES,
            "transition_kind",
            LIVE_START_PENDING_TRANSITION_KIND,
        ),
        "external_file_action": (
            _EXTERNAL_FILE_ACTION_FIELDS,
            LIVE_START_EXTERNAL_FILE_ACTION_MAX_BYTES,
            None,
            None,
        ),
        "output_child_binding": (
            _OUTPUT_CHILD_BINDING_FIELDS,
            LIVE_START_OUTPUT_CHILD_BINDING_MAX_BYTES,
            "binding_kind",
            LIVE_START_OUTPUT_CHILD_BINDING_KIND,
        ),
        "output_operation_admission_binding": (
            _OUTPUT_OPERATION_BINDING_FIELDS,
            LIVE_START_OUTPUT_OPERATION_ADMISSION_BINDING_MAX_BYTES,
            "binding_kind",
            LIVE_START_OUTPUT_OPERATION_ADMISSION_BINDING_KIND,
        ),
        "runtime_layout_bootstrap": (
            _RUNTIME_LAYOUT_FIELDS,
            LIVE_START_RUNTIME_LAYOUT_BOOTSTRAP_MAX_BYTES,
            "binding_kind",
            LIVE_START_RUNTIME_LAYOUT_BOOTSTRAP_KIND,
        ),
        "result_intent": (
            _RESULT_INTENT_FIELDS,
            LIVE_START_RESULT_INTENT_MAX_BYTES,
            "intent_kind",
            LIVE_START_RESULT_INTENT_KIND,
        ),
        "attempt_acknowledgement": (
            _ATTEMPT_ACK_FIELDS,
            LIVE_START_ATTEMPT_ACKNOWLEDGEMENT_MAX_BYTES,
            "acknowledgement_kind",
            LIVE_START_ATTEMPT_ACKNOWLEDGEMENT_KIND,
        ),
        "terminal_retirement": (
            _TERMINAL_RETIREMENT_FIELDS,
            LIVE_START_TERMINAL_RETIREMENT_MAX_BYTES,
            "retirement_kind",
            LIVE_START_TERMINAL_RETIREMENT_KIND,
        ),
    }
)

PENDING_TRANSITION_OPERATIONS = frozenset(
    {
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
        "review_revision",
    }
)
PENDING_TRANSITION_STAGES = frozenset(
    {"PREPARED", "STAGING_BOUND", "PRIMARY_APPLIED", "CLEANUP_DELETING"}
)
OUTPUT_OPERATION_ADMISSION_STATES = frozenset(
    {
        "ACTIVE",
        "RUNTIME_HANDOFF_RELEASE_AUTHORIZED",
        "TERMINAL_RELEASE_AUTHORIZED",
    }
)
OUTPUT_CHILD_CLAIM_STATES = frozenset({"ACTIVE", "RETIRED"})
TERMINAL_RETIREMENT_STAGES = MappingProxyType(
    {
        "ack_success": frozenset(
            {
                "PREPARED",
                "ACK_JOURNAL_RETIRED",
                "EVIDENCE_RETIRED",
                "ADMISSION_RELEASE_AUTHORIZED",
            }
        ),
        "release_not_committed": frozenset(
            {"PREPARED", "EVIDENCE_RETIRED", "ADMISSION_RELEASE_AUTHORIZED"}
        ),
        "release_committed_mismatch": frozenset(
            {"PREPARED", "EVIDENCE_RETIRED", "ADMISSION_RELEASE_AUTHORIZED"}
        ),
        "release_resolved_terminal": frozenset(
            {
                "RECOVERY_PREPARED",
                "RECOVERY_INVENTORY_BOUND",
                "RECOVERY_CLEANING",
                "RECOVERY_JOURNAL_RETIRED",
                "RECOVERY_FENCE_RETIRED",
                "RECOVERY_INVENTORY_RETIRED",
                "RECOVERY_STABILIZED",
                "EVIDENCE_RETIRED",
                "ADMISSION_RELEASE_AUTHORIZED",
            }
        ),
    }
)
RECOVERY_STAGES = frozenset({"ACTIVE", "CLOSED"})


def validate_embedded_document(
    document_kind: str,
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Validate one closed, canonical, self-digested nested document."""

    try:
        fields, maximum_size, kind_field, kind_value = _EXTERNAL_DOCUMENT_SPECS[
            document_kind
        ]
    except KeyError as error:
        raise SessionValidationError("live_start_document_kind_invalid") from error
    normalized = _normalize_json(value)
    if not isinstance(normalized, dict) or set(normalized) != fields:
        raise SessionValidationError(f"live_start_{document_kind}_fields_invalid")
    if len(_canonical_json(normalized)) > maximum_size:
        raise SessionValidationError(f"live_start_{document_kind}_size_invalid")
    if normalized.get("schema_version") != 1:
        raise SessionValidationError(f"live_start_{document_kind}_schema_invalid")
    if kind_field is not None and normalized.get(kind_field) != kind_value:
        raise SessionValidationError(f"live_start_{document_kind}_kind_invalid")
    claimed = normalized.get("content_sha256")
    unsigned = dict(normalized)
    unsigned.pop("content_sha256")
    if claimed != _self_digest(unsigned):
        raise SessionValidationError(
            f"live_start_{document_kind}_content_sha256_invalid"
        )
    if document_kind == "external_file_action":
        _validate_external_file_action(normalized)
    elif document_kind == "pending_transition":
        _validate_pending_transition(normalized)
    elif document_kind == "output_child_binding":
        _validate_output_child_binding(normalized)
    elif document_kind == "output_operation_admission_binding":
        _validate_output_operation_binding(normalized)
    elif document_kind == "runtime_layout_bootstrap":
        _validate_runtime_layout(normalized)
    elif document_kind == "result_intent":
        _validate_result_intent(normalized)
    elif document_kind == "attempt_acknowledgement":
        _validate_attempt_acknowledgement(normalized)
    elif document_kind == "terminal_retirement":
        _validate_terminal_retirement(normalized)
    return _freeze_mapping(normalized)


def seal_embedded_document(
    document_kind: str,
    unsigned_value: Mapping[str, Any],
) -> Mapping[str, Any]:
    normalized = _normalize_json(unsigned_value)
    if not isinstance(normalized, dict):
        raise SessionValidationError("live_start_document_not_object")
    normalized.pop("content_sha256", None)
    sealed = {**normalized, "content_sha256": _self_digest(normalized)}
    return validate_embedded_document(document_kind, sealed)


def _validate_session_nested_documents(
    *,
    value: Mapping[str, Any],
    phase: LiveStartPhase,
) -> None:
    for name in (
        "pending_transition",
        "output_operation_admission_binding",
        "output_child_binding",
        "runtime_layout_bootstrap",
        "result_intent",
        "attempt_acknowledgement",
        "terminal_retirement",
    ):
        nested = value.get(name)
        if nested is not None:
            validate_embedded_document(name, nested)
    for name, fields in (
        ("prepublication_work_binding", _PREPUBLICATION_WORK_BINDING_FIELDS),
        ("runtime_admission_binding", _RUNTIME_ADMISSION_BINDING_FIELDS),
        ("publication_binding", _PUBLICATION_BINDING_FIELDS),
    ):
        nested = value.get(name)
        if nested is not None:
            if not isinstance(nested, dict) or set(nested) != fields:
                raise SessionValidationError(f"live_start_{name}_fields_invalid")
            if name == "prepublication_work_binding":
                _validate_prepublication_work_binding(nested)
            elif name == "runtime_admission_binding":
                _validate_runtime_admission_binding(nested)
            else:
                _validate_publication_binding(nested)
    apply_invocation = value.get("apply_invocation_sha256")
    if apply_invocation is not None:
        _require_sha256(apply_invocation, "apply_invocation_sha256")
    apply_recovery = value.get("apply_recovery")
    if apply_recovery is not None:
        _validate_apply_recovery_document(apply_recovery)
    closed_recovery = value.get("closed_apply_recovery_commitment")
    if closed_recovery is not None:
        validated_closed = _validate_apply_recovery_document(closed_recovery)
        if validated_closed.get("recovery_stage") != "CLOSED":
            raise SessionValidationError(
                "live_start_closed_recovery_commitment_stage_invalid"
            )
    _validate_session_binding_matrix(value=value, phase=phase)


def _validate_prepublication_work_binding(
    value: Mapping[str, Any],
) -> None:
    for key in ("work_parent_path", "work_root"):
        _require_absolute_path(value.get(key), key)
    for key in ("work_parent_identity", "work_root_identity"):
        _require_identity(value.get(key), key)
    for key in ("work_tree_sha256", "cleanup_manifest_sha256"):
        _require_sha256(value.get(key), key)
    _bounded_integer(
        value.get("cleanup_entry_count"),
        0,
        MAX_FILESYSTEM_NODES,
        "cleanup_entry_count",
    )
    if Path(value["work_root"]).parent != Path(value["work_parent_path"]):
        raise SessionValidationError(
            "live_start_prepublication_work_path_invalid"
        )


def _validate_runtime_admission_binding(
    value: Mapping[str, Any],
) -> None:
    if set(value) != _RUNTIME_ADMISSION_BINDING_FIELDS:
        raise SessionValidationError(
            "live_start_runtime_admission_binding_fields_invalid"
        )
    for key in (
        "admission_path",
        "output_operation_admission_path",
        "output_child_path",
    ):
        _require_absolute_path(value.get(key), key)
    for key in (
        "admission_parent_identity",
        "admission_identity",
        "output_operation_admission_identity",
        "output_child_identity",
    ):
        _require_identity(value.get(key), key)
    for key in (
        "admission_sha256",
        "output_operation_admission_sha256",
        "output_child_binding_sha256",
        "publication_content_root_sha256",
    ):
        _require_sha256(value.get(key), key)
    revision = value.get("publication_revision")
    if (
        not isinstance(revision, str)
        or re.fullmatch(r"revisions/sha256-[0-9a-f]{64}", revision)
        is None
    ):
        raise SessionValidationError(
            "live_start_runtime_admission_publication_revision_invalid"
        )


def _validate_publication_binding(value: Mapping[str, Any]) -> None:
    if set(value) != _PUBLICATION_BINDING_FIELDS:
        raise SessionValidationError(
            "live_start_publication_binding_fields_invalid"
        )
    _require_absolute_path(
        value.get("output_child_path"),
        "publication_output_child_path",
    )
    _require_identity(
        value.get("output_child_identity"),
        "publication_output_child_identity",
    )
    _require_sha256(
        value.get("output_child_binding_sha256"),
        "publication_output_child_binding_sha256",
    )
    prior_current_identity = value.get("prior_current_identity")
    if prior_current_identity is not None:
        _require_identity(
            prior_current_identity,
            "publication_prior_current_identity",
        )
    revision = value.get("revision")
    if (
        not isinstance(revision, str)
        or re.fullmatch(r"revisions/sha256-[0-9a-f]{64}", revision)
        is None
    ):
        raise SessionValidationError(
            "live_start_publication_revision_invalid"
        )
    _require_sha256(
        value.get("content_root_sha256"),
        "publication_content_root_sha256",
    )


def _validate_session_binding_matrix(
    *,
    value: Mapping[str, Any],
    phase: LiveStartPhase,
) -> None:
    _validate_top_level_phase_field_matrix(value=value, phase=phase)
    admission = value.get("runtime_admission_binding")
    layout = value.get("runtime_layout_bootstrap")
    invocation = value.get("apply_invocation_sha256")
    ordinal = list(LiveStartPhase).index(phase)
    publication_ordinal = list(LiveStartPhase).index(
        LiveStartPhase.PUBLICATION_COMMITTED
    )
    apply_ordinal = list(LiveStartPhase).index(LiveStartPhase.APPLY_STARTED)
    if ordinal >= publication_ordinal and value.get(
        "publication_binding"
    ) is None:
        raise SessionValidationError(
            "live_start_publication_binding_missing"
        )
    if ordinal >= apply_ordinal:
        if admission is None or layout is None or invocation is None:
            raise SessionValidationError("live_start_runtime_admission_binding_missing")
        if layout.get("stage") != "COMPLETE":
            raise SessionValidationError("live_start_runtime_layout_incomplete")
    elif admission is not None and value.get("pending_transition") is None:
        raise SessionValidationError("live_start_runtime_admission_phase_invalid")
    if value.get("attempt_acknowledgement") is not None:
        intent = value.get("result_intent")
        if (
            not isinstance(intent, dict)
            or intent.get("terminal_status")
            not in {"LIVE_AND_MATCHED", "ALREADY_LIVE"}
        ):
            raise SessionValidationError("live_start_acknowledgement_status_invalid")
    if value.get("terminal_status") is not None and value.get("result_intent") is None:
        raise SessionValidationError("live_start_terminal_result_intent_missing")
    if value.get("terminal_status") is not None and value.get("pending_transition") is not None:
        raise SessionValidationError("live_start_terminal_pending_transition_invalid")
    if value.get("result_intent") is not None:
        _validate_terminal_status_matrix(value=value, phase=phase)


def _validate_top_level_phase_field_matrix(
    *,
    value: Mapping[str, Any],
    phase: LiveStartPhase,
) -> None:
    run_id = value.get("run_id")
    pending = value.get("pending_transition")
    prepublication = value.get("prepublication_work_binding")
    operation_binding = value.get("output_operation_admission_binding")
    child_binding = value.get("output_child_binding")
    publication = value.get("publication_binding")
    invocation = value.get("apply_invocation_sha256")
    admission = value.get("runtime_admission_binding")
    layout = value.get("runtime_layout_bootstrap")
    recovery = value.get("apply_recovery")
    closed_recovery = value.get("closed_apply_recovery_commitment")
    intent = value.get("result_intent")
    acknowledgement = value.get("attempt_acknowledgement")
    retirement = value.get("terminal_retirement")
    terminal_status = value.get("terminal_status")

    phase_index = list(LiveStartPhase).index(phase)
    package_index = list(LiveStartPhase).index(
        LiveStartPhase.PACKAGE_VALIDATED
    )
    prepublication_index = list(LiveStartPhase).index(
        LiveStartPhase.PREPUBLICATION_CHECK_PASSED
    )
    publication_index = list(LiveStartPhase).index(
        LiveStartPhase.PUBLICATION_COMMITTED
    )
    apply_index = list(LiveStartPhase).index(LiveStartPhase.APPLY_STARTED)

    if pending is not None:
        if (
            pending.get("run_id") != run_id
            or pending.get("source_phase") != phase.value
            or pending.get("source_candidate_revision")
            != value.get("candidate_revision")
            or pending.get("source_revisions_used")
            != value.get("revisions_used")
        ):
            raise SessionValidationError(
                "live_start_pending_outer_binding_invalid"
            )
        if pending.get("operation") == "cleanup_prepublication":
            if not isinstance(prepublication, Mapping) or any(
                pending.get(field_name) != prepublication.get(field_name)
                for field_name in _PREPUBLICATION_WORK_BINDING_FIELDS
            ):
                raise SessionValidationError(
                    "live_start_prepublication_cleanup_work_binding_invalid"
                )
        if pending.get("operation") == "install_apply_invocation":
            _validate_apply_invocation_outer_matrix(
                value=value,
                pending=pending,
            )

    if (
        phase_index < package_index
        and phase is not LiveStartPhase.REVIEW_APPROVED
        and prepublication is not None
    ):
        raise SessionValidationError(
            "live_start_prepublication_work_phase_invalid"
        )
    if phase_index >= package_index and prepublication is None:
        raise SessionValidationError(
            "live_start_prepublication_work_binding_missing"
        )
    if (
        phase is LiveStartPhase.REVIEW_APPROVED
        and prepublication is not None
        and pending is not None
        and pending.get("operation") != "install_package_validation"
    ):
        raise SessionValidationError(
            "live_start_prepublication_work_phase_invalid"
        )
    if phase_index < prepublication_index and any(
        item is not None for item in (operation_binding, child_binding)
    ):
        raise SessionValidationError(
            "live_start_output_binding_phase_invalid"
        )
    if phase_index < publication_index and publication is not None:
        raise SessionValidationError(
            "live_start_publication_binding_phase_invalid"
        )
    if phase_index >= publication_index and (
        publication is None
        or operation_binding is None
        or child_binding is None
    ):
        raise SessionValidationError(
            "live_start_output_binding_missing"
        )
    if phase_index < apply_index:
        apply_pending = (
            phase is LiveStartPhase.PUBLICATION_COMMITTED
            and isinstance(pending, Mapping)
            and pending.get("operation") == "install_apply_invocation"
        )
        if not apply_pending and any(
            item is not None for item in (invocation, admission, layout)
        ):
            raise SessionValidationError(
                "live_start_runtime_binding_phase_invalid"
            )
        if recovery is not None or closed_recovery is not None:
            raise SessionValidationError(
                "live_start_apply_recovery_phase_invalid"
            )
    if phase_index >= apply_index and any(
        item is None for item in (invocation, admission, layout)
    ):
        raise SessionValidationError(
            "live_start_runtime_admission_binding_missing"
        )

    if isinstance(operation_binding, Mapping):
        if operation_binding.get("run_id") != run_id:
            raise SessionValidationError(
                "live_start_output_operation_outer_binding_invalid"
            )
    if isinstance(child_binding, Mapping):
        if child_binding.get("run_id") != run_id:
            raise SessionValidationError(
                "live_start_output_child_outer_binding_invalid"
            )
    if isinstance(publication, Mapping) and isinstance(
        child_binding, Mapping
    ):
        if (
            publication.get("output_child_path")
            != child_binding.get("output_child_path")
            or publication.get("output_child_identity")
            != child_binding.get("output_child_identity")
            or publication.get("output_child_binding_sha256")
            != child_binding.get("content_sha256")
        ):
            raise SessionValidationError(
                "live_start_publication_output_child_binding_invalid"
            )
    if isinstance(admission, Mapping):
        if not isinstance(operation_binding, Mapping) or not isinstance(
            child_binding, Mapping
        ) or not isinstance(publication, Mapping):
            raise SessionValidationError(
                "live_start_runtime_outer_binding_invalid"
            )
        if (
            admission.get("output_operation_admission_path")
            != operation_binding.get("admission_path")
            or admission.get("output_operation_admission_identity")
            != operation_binding.get("admission_identity")
            or admission.get("output_operation_admission_sha256")
            != operation_binding.get("admission_sha256")
            or admission.get("output_child_binding_sha256")
            != child_binding.get("content_sha256")
            or admission.get("output_child_path")
            != child_binding.get("output_child_path")
            or admission.get("output_child_identity")
            != child_binding.get("output_child_identity")
            or admission.get("publication_revision")
            != publication.get("revision")
            or admission.get("publication_content_root_sha256")
            != publication.get("content_root_sha256")
        ):
            raise SessionValidationError(
                "live_start_runtime_outer_binding_invalid"
            )
    if isinstance(layout, Mapping):
        if layout.get("run_id") != run_id:
            raise SessionValidationError(
                "live_start_runtime_layout_outer_binding_invalid"
            )
    if isinstance(recovery, Mapping):
        if (
            recovery.get("run_id") != run_id
            or recovery.get("apply_invocation_sha256") != invocation
            or not isinstance(admission, Mapping)
            or recovery.get("runtime_admission_path")
            != admission.get("admission_path")
            or recovery.get("runtime_admission_parent_identity")
            != admission.get("admission_parent_identity")
            or recovery.get("runtime_admission_identity")
            != admission.get("admission_identity")
            or recovery.get("runtime_admission_sha256")
            != admission.get("admission_sha256")
            or not isinstance(layout, Mapping)
            or recovery.get("apply_attempt_id")
            != layout.get("apply_attempt_id")
            or recovery.get("runtime_root") != layout.get("runtime_root")
            or recovery.get("runtime_root_identity")
            != layout.get("runtime_root_identity")
        ):
            raise SessionValidationError(
                "live_start_apply_recovery_outer_binding_invalid"
            )
    if closed_recovery is not None:
        if (
            not isinstance(closed_recovery, Mapping)
            or recovery is not None
            or not isinstance(intent, Mapping)
            or retirement is not None
            or closed_recovery.get("recovery_stage") != "CLOSED"
            or closed_recovery.get("run_id") != run_id
            or closed_recovery.get("apply_invocation_sha256") != invocation
            or not isinstance(admission, Mapping)
            or closed_recovery.get("runtime_admission_path")
            != admission.get("admission_path")
            or closed_recovery.get("runtime_admission_parent_identity")
            != admission.get("admission_parent_identity")
            or closed_recovery.get("runtime_admission_identity")
            != admission.get("admission_identity")
            or closed_recovery.get("runtime_admission_sha256")
            != admission.get("admission_sha256")
            or not isinstance(layout, Mapping)
            or closed_recovery.get("apply_attempt_id")
            != layout.get("apply_attempt_id")
            or closed_recovery.get("runtime_root")
            != layout.get("runtime_root")
            or closed_recovery.get("runtime_root_identity")
            != layout.get("runtime_root_identity")
        ):
            raise SessionValidationError(
                "live_start_closed_recovery_commitment_outer_binding_invalid"
            )
        expected_intent_values = {
            "apply_attempt_id": closed_recovery.get("apply_attempt_id"),
            "package_root_sha256": closed_recovery.get(
                "package_root_sha256"
            ),
            "last_apply_receipt_sha256": closed_recovery.get(
                "last_apply_receipt_sha256"
            ),
            "runtime_state_sha256": closed_recovery.get(
                "runtime_state_sha256"
            ),
            "deck_config_ini_sha256": closed_recovery.get(
                "deck_config_ini_sha256"
            ),
            "runtime_match_status": closed_recovery.get(
                "runtime_match_status"
            ),
            "runtime_match_sha256": closed_recovery.get(
                "runtime_match_sha256"
            ),
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
                expected_intent_values[f"{intent_prefix}_{suffix}"] = (
                    closed_recovery.get(f"{recovery_prefix}_{suffix}")
                )
        if any(
            intent.get(field_name) != expected_value
            for field_name, expected_value in expected_intent_values.items()
        ):
            raise SessionValidationError(
                "live_start_closed_recovery_result_binding_invalid"
            )
    elif recovery is not None and intent is not None:
        raise SessionValidationError(
            "live_start_apply_recovery_result_coexistence_invalid"
        )
    elif (
        isinstance(intent, Mapping)
        and intent.get("apply_attempt_id") is not None
        and retirement is None
    ):
        raise SessionValidationError(
            "live_start_closed_recovery_commitment_missing"
        )
    if isinstance(intent, Mapping):
        attempt_id = intent.get("apply_attempt_id")
        if attempt_id is not None and (
            not isinstance(layout, Mapping)
            or attempt_id != layout.get("apply_attempt_id")
        ):
            raise SessionValidationError(
                "live_start_result_attempt_binding_invalid"
            )
    if isinstance(acknowledgement, Mapping):
        if (
            acknowledgement.get("run_id") != run_id
            or not isinstance(intent, Mapping)
            or acknowledgement.get("apply_attempt_id")
            != intent.get("apply_attempt_id")
        ):
            raise SessionValidationError(
                "live_start_acknowledgement_outer_binding_invalid"
            )
    if isinstance(retirement, Mapping):
        if not _terminal_operation_matches_authority(
            operation=retirement.get("operation"),
            terminal_status=terminal_status,
            result_intent=intent,
            attempt_acknowledgement=acknowledgement,
            has_resolution=(
                retirement.get("terminal_resolution_evidence") is not None
            ),
        ):
            raise SessionValidationError(
                "live_start_terminal_retirement_operation_binding_invalid"
            )
        if (
            retirement.get("run_id") != run_id
            or not isinstance(intent, Mapping)
            or retirement.get("result_intent_sha256")
            != intent.get("content_sha256")
            or retirement.get("apply_attempt_id")
            != intent.get("apply_attempt_id")
        ):
            raise SessionValidationError(
                "live_start_terminal_retirement_outer_binding_invalid"
            )
        for retirement_name, intent_name in (
            ("runtime_admission_path", "runtime_admission_path"),
            (
                "runtime_admission_parent_identity",
                "runtime_admission_parent_identity",
            ),
            ("runtime_admission_identity", "runtime_admission_identity"),
            ("runtime_admission_sha256", "runtime_admission_sha256"),
            (
                "retained_attempt_record_path",
                "retained_attempt_record_path",
            ),
            (
                "retained_attempt_record_identity",
                "retained_attempt_record_identity",
            ),
            (
                "retained_attempt_record_sha256",
                "retained_attempt_record_sha256",
            ),
            ("retained_journal_path", "retained_journal_path"),
            ("retained_journal_identity", "retained_journal_identity"),
            ("retained_journal_sha256", "retained_journal_sha256"),
            (
                "retained_target_owner_journal_path",
                "retained_target_owner_journal_path",
            ),
            (
                "retained_target_owner_journal_identity",
                "retained_target_owner_journal_identity",
            ),
            (
                "retained_target_owner_journal_sha256",
                "retained_target_owner_journal_sha256",
            ),
            (
                "retained_candidate_identity",
                "retained_candidate_identity",
            ),
        ):
            if retirement.get(retirement_name) != intent.get(intent_name):
                raise SessionValidationError(
                    "live_start_terminal_retirement_outer_binding_invalid"
                )
        resolution = retirement.get("terminal_resolution_evidence")
        if isinstance(resolution, Mapping):
            resolution_outer_invalid = (
                resolution.get("run_id") != run_id
                or resolution.get("apply_attempt_id")
                != retirement.get("apply_attempt_id")
                or resolution.get("package_root_sha256")
                != intent.get("package_root_sha256")
                or (
                    resolution.get("resolved_physical_disposition")
                    == "NOT_COMMITTED"
                    and resolution.get("predecessor_candidate_identity")
                    != retirement.get("retained_candidate_identity")
                )
            )
            for resolution_prefix, retirement_prefix in (
                ("predecessor_attempt_record", "retained_attempt_record"),
                ("predecessor_journal", "retained_journal"),
                (
                    "predecessor_target_owner_journal",
                    "retained_target_owner_journal",
                ),
            ):
                for suffix in ("path", "identity", "sha256"):
                    resolution_outer_invalid = (
                        resolution_outer_invalid
                        or resolution.get(f"{resolution_prefix}_{suffix}")
                        != retirement.get(f"{retirement_prefix}_{suffix}")
                    )
            if resolution_outer_invalid:
                raise SessionValidationError(
                    "live_start_terminal_resolution_outer_binding_invalid"
                )
    if retirement is not None and terminal_status is None:
        raise SessionValidationError(
            "live_start_terminal_retirement_status_missing"
        )


def _validate_apply_invocation_outer_matrix(
    *,
    value: Mapping[str, Any],
    pending: Mapping[str, Any],
) -> None:
    if (
        value.get("apply_invocation_sha256") is not None
        or value.get("runtime_admission_binding") is not None
    ):
        raise SessionValidationError(
            "live_start_apply_invocation_outer_binding_invalid"
        )
    layout = value.get("runtime_layout_bootstrap")
    stage = pending.get("stage")
    external = pending.get("external_file_action")
    if stage in {"PREPARED", "STAGING_BOUND"}:
        if layout is not None:
            raise SessionValidationError(
                "live_start_runtime_layout_phase_invalid"
            )
        return
    if stage != "PRIMARY_APPLIED":
        raise SessionValidationError(
            "live_start_apply_invocation_outer_binding_invalid"
        )
    if layout is None:
        if external is not None or pending.get("next_action_index") != 0:
            raise SessionValidationError(
                "live_start_invocation_receipt_before_layout_invalid"
            )
        return
    if (
        layout.get("run_id") != value.get("run_id")
        or layout.get("apply_attempt_id")
        != pending.get("apply_attempt_id")
    ):
        raise SessionValidationError(
            "live_start_runtime_layout_outer_binding_invalid"
        )
    if layout.get("stage") == "INCOMPLETE":
        if external is not None or pending.get("next_action_index") != 0:
            raise SessionValidationError(
                "live_start_invocation_receipt_before_layout_invalid"
            )
        return
    if layout.get("stage") != "COMPLETE":
        raise SessionValidationError(
            "live_start_runtime_layout_completion_invalid"
        )
    if external is None:
        if pending.get("next_action_index") != 1:
            raise SessionValidationError(
                "live_start_invocation_receipt_commit_invalid"
            )
    elif pending.get("next_action_index") != 0:
        raise SessionValidationError(
            "live_start_invocation_receipt_cursor_invalid"
        )


def _validate_phase_artifact_bindings(
    *,
    value: Mapping[str, Any],
    phase: LiveStartPhase,
    artifact_bindings: Mapping[str, str],
) -> None:
    mandatory = _PHASE_MANDATORY_ARTIFACTS[phase]
    result_paths = frozenset(
        {"result/summary.json", "result/summary.md"}
    )
    actual = frozenset(artifact_bindings)
    if not mandatory <= actual:
        raise SessionValidationError(
            "live_start_phase_artifact_binding_missing"
        )
    extras = actual - mandatory
    revision_request_path = "starter/starter_config_review.json"
    revision_request_variant = (
        phase is LiveStartPhase.CANDIDATE_DRAFTED
        and extras == {revision_request_path}
        and value.get("revisions_used") == value.get("candidate_revision")
        and value.get("pending_transition") is None
    )
    if extras - result_paths and not revision_request_variant:
        raise SessionValidationError(
            "live_start_phase_artifact_binding_forbidden"
        )
    intent = value.get("result_intent")
    if intent is None and extras and not revision_request_variant:
        raise SessionValidationError(
            "live_start_result_artifact_binding_phase_invalid"
        )
    if value.get("terminal_status") is not None and extras != result_paths:
        raise SessionValidationError(
            "live_start_terminal_result_artifact_binding_missing"
        )


def _validate_terminal_status_matrix(
    *,
    value: Mapping[str, Any],
    phase: LiveStartPhase,
) -> None:
    intent = value.get("result_intent")
    if not isinstance(intent, Mapping):
        raise SessionValidationError("live_start_terminal_intent_invalid")
    if (
        intent.get("run_id") != value.get("run_id")
        or intent.get("deck_name") != value.get("deck_name")
        or intent.get("candidate_revision")
        != value.get("candidate_revision")
    ):
        raise SessionValidationError("live_start_terminal_intent_binding_invalid")
    status = intent.get("terminal_status")
    terminal_status = value.get("terminal_status")
    if terminal_status is not None and terminal_status != status:
        raise SessionValidationError("live_start_terminal_status_mismatch")
    acknowledgement = value.get("attempt_acknowledgement")
    publication = value.get("publication_binding")
    invocation = value.get("apply_invocation_sha256")
    admission = value.get("runtime_admission_binding")
    recovery = value.get("apply_recovery")
    raw_status = intent.get("raw_apply_status")
    disposition = intent.get("physical_disposition")
    match_status = intent.get("runtime_match_status")
    safe_state = intent.get("retained_safe_state")
    if recovery is not None:
        raise SessionValidationError(
            "live_start_terminal_recovery_not_consumed"
        )

    intent_publication = (
        intent.get("publication_revision"),
        intent.get("publication_content_root_sha256"),
    )
    if publication is None:
        if any(item is not None for item in intent_publication):
            raise SessionValidationError(
                "live_start_terminal_publication_binding_invalid"
            )
    elif (
        intent_publication[0] != publication.get("revision")
        or intent_publication[1]
        != publication.get("content_root_sha256")
    ):
        raise SessionValidationError(
            "live_start_terminal_publication_binding_invalid"
        )

    intent_admission = (
        intent.get("runtime_admission_path"),
        intent.get("runtime_admission_parent_identity"),
        intent.get("runtime_admission_identity"),
        intent.get("runtime_admission_sha256"),
    )
    if admission is None:
        if any(item is not None for item in intent_admission):
            raise SessionValidationError(
                "live_start_terminal_admission_binding_invalid"
            )
    else:
        session_admission = (
            admission.get("admission_path"),
            admission.get("admission_parent_identity"),
            admission.get("admission_identity"),
            admission.get("admission_sha256"),
        )
        if intent_admission != session_admission:
            raise SessionValidationError(
                "live_start_terminal_admission_binding_invalid"
            )

    apply_attempt_id = intent.get("apply_attempt_id")
    if (invocation is None) != (apply_attempt_id is None):
        raise SessionValidationError(
            "live_start_terminal_attempt_binding_invalid"
        )
    phase_index = list(LiveStartPhase).index(phase)
    review_index = list(LiveStartPhase).index(
        LiveStartPhase.REVIEW_APPROVED
    )
    if phase_index >= review_index and (
        intent.get("review_confidence") not in {"high", "limited"}
        or intent.get("configured_cards") is None
        or intent.get("deliberately_unconfigured_cards") is None
    ):
        raise SessionValidationError(
            "live_start_terminal_review_or_coverage_invalid"
        )

    if status == "PREVIEW_READY":
        if (
            phase is not LiveStartPhase.PUBLICATION_COMMITTED
            or value.get("preview_requested") is not True
            or publication is None
            or invocation is not None
            or admission is not None
            or value.get("runtime_layout_bootstrap") is not None
            or raw_status is not None
            or disposition is not None
            or match_status != "not_run"
            or intent.get("runtime_match_sha256") is not None
            or acknowledgement is not None
            or safe_state != "PUBLISHED_PREVIEW_RUNTIME_UNCHANGED"
            or intent.get("review_confidence") not in {"high", "limited"}
        ):
            raise SessionValidationError(
                "live_start_preview_terminal_matrix_invalid"
            )
        return

    if status in {"LIVE_AND_MATCHED", "ALREADY_LIVE"}:
        expected_raw = (
            {"applied", "recovered"}
            if status == "LIVE_AND_MATCHED"
            else {"already_current"}
        )
        if (
            phase is not LiveStartPhase.RUNTIME_MATCHED
            or raw_status not in expected_raw
            or disposition != "COMMITTED"
            or match_status != "matched"
            or safe_state != "ACTIVE_RUNTIME_MATCHED"
            or acknowledgement is None
            or invocation is None
            or admission is None
            or publication is None
        ):
            raise SessionValidationError(
                "live_start_success_terminal_matrix_invalid"
            )
        for key in (
            "runtime_match_sha256",
            "package_root_sha256",
            "last_apply_receipt_sha256",
            "runtime_state_sha256",
            "deck_config_ini_sha256",
        ):
            _require_sha256(intent.get(key), key)
        return

    if acknowledgement is not None:
        raise SessionValidationError(
            "live_start_failure_acknowledgement_forbidden"
        )
    if status == "FAILED_PRESERVED":
        prepublication_index = list(LiveStartPhase).index(
            LiveStartPhase.PREPUBLICATION_CHECK_PASSED
        )
        if phase_index <= prepublication_index:
            valid = (
                invocation is None
                and admission is None
                and publication is None
                and raw_status is None
                and disposition is None
                and match_status == "not_run"
                and safe_state == "NO_PUBLICATION_OR_RUNTIME_WRITE"
            )
        elif phase is LiveStartPhase.PUBLICATION_COMMITTED:
            valid = (
                publication is not None
                and invocation is None
                and admission is None
                and raw_status is None
                and disposition is None
                and match_status == "not_run"
                and safe_state
                == "PUBLICATION_RETAINED_RUNTIME_UNCHANGED"
            )
        else:
            valid = (
                phase is LiveStartPhase.APPLY_STARTED
                and invocation is not None
                and admission is not None
                and disposition == "NOT_COMMITTED"
                and match_status == "not_run"
                and safe_state == "PREVIOUS_RUNTIME_UNCHANGED"
            )
        if not valid:
            raise SessionValidationError(
                "live_start_failure_terminal_matrix_invalid"
            )
        return

    if status == "APPLIED_BUT_NOT_VERIFIED":
        committed_mismatch = (
            phase is LiveStartPhase.APPLY_COMMITTED
            and raw_status in {"applied", "already_current", "recovered"}
            and disposition == "COMMITTED"
            and match_status in {"mismatch", "unknown"}
        )
        pending_or_unknown = (
            phase in {
                LiveStartPhase.APPLY_STARTED,
                LiveStartPhase.APPLY_COMMITTED,
            }
            and raw_status in {None, "committed_receipt_pending"}
            and disposition
            in {
                "COMMITTED_RECOVERY_PENDING",
                "UNKNOWN_REQUIRES_RECOVERY",
            }
        )
        if (
            not (committed_mismatch or pending_or_unknown)
            or invocation is None
            or admission is None
            or safe_state != "ATTEMPT_EVIDENCE_RETAINED"
        ):
            raise SessionValidationError(
                "live_start_unverified_terminal_matrix_invalid"
            )
        return

    raise SessionValidationError("live_start_terminal_status_matrix_invalid")


def _validate_external_file_action(value: Mapping[str, Any]) -> None:
    if value.get("stage") not in {"PLANNED", "STAGING_BOUND"}:
        raise SessionValidationError("live_start_external_file_action_stage_invalid")
    if value.get("commit_mode") not in {"create_no_replace", "replace_exact"}:
        raise SessionValidationError("live_start_external_file_action_mode_invalid")
    action_kind = value.get("action_kind")
    if (
        not isinstance(action_kind, str)
        or _SAFE_TOKEN.fullmatch(action_kind) is None
    ):
        raise SessionValidationError(
            "live_start_external_file_action_kind_invalid"
        )
    _bounded_integer(value.get("action_index"), 0, 1_000_000, "action_index")
    for key in ("final_path", "staging_path", "inner_temp_path"):
        _require_absolute_path(value.get(key), key)
    final_path = Path(value["final_path"])
    staging_path = Path(value["staging_path"])
    inner_path = Path(value["inner_temp_path"])
    standard_staging_paths = (
        staging_path == final_path.with_name(f"{final_path.name}.staged")
        and inner_path
        == staging_path.with_name(
            f".{staging_path.name}.live-start-atomic.tmp"
        )
    )
    fixed_output_operation_paths = (
        final_path.name == OUTPUT_OPERATION_ADMISSION_NAME
        and staging_path
        == final_path.with_name(OUTPUT_OPERATION_ADMISSION_STAGING_NAME)
        and inner_path
        == final_path.with_name(
            OUTPUT_OPERATION_ADMISSION_RESERVED_TEMP_NAME
        )
    )
    fixed_runtime_admission_paths = (
        final_path.name == RUNTIME_LIVE_ATTEMPT_ADMISSION_NAME
        and action_kind
        in {
            "materialize_runtime_admission_staging",
            "commit_bound_runtime_admission",
            "retire_unbound_runtime_admission_staging",
        }
        and re.fullmatch(
            r"\.live-start-active-attempt\.[0-9a-f]{32}\."
            r"[0-9a-f]{32}\.staged",
            staging_path.name,
        )
        is not None
        and staging_path.parent == final_path.parent
        and inner_path
        == staging_path.with_name(
            f".{staging_path.name}.live-start-atomic.tmp"
        )
    )
    if (
        not (
            standard_staging_paths
            or fixed_output_operation_paths
            or fixed_runtime_admission_paths
        )
        or len({final_path, staging_path, inner_path}) != 3
    ):
        raise SessionValidationError("live_start_external_file_action_paths_invalid")
    _require_identity(value.get("parent_identity"), "parent_identity")
    predecessor = value.get("predecessor_state")
    if predecessor not in {"absent", "exact"}:
        raise SessionValidationError("live_start_external_file_action_predecessor_invalid")
    if (value["commit_mode"] == "create_no_replace") != (
        predecessor == "absent"
    ):
        raise SessionValidationError("live_start_external_file_action_mode_invalid")
    predecessor_values = (
        value.get("predecessor_identity"),
        value.get("predecessor_size"),
        value.get("predecessor_sha256"),
    )
    if predecessor == "absent" and any(item is not None for item in predecessor_values):
        raise SessionValidationError("live_start_external_file_action_predecessor_invalid")
    if predecessor == "exact":
        _require_identity(predecessor_values[0], "predecessor_identity")
        _bounded_integer(predecessor_values[1], 0, 64 * 1024 * 1024, "predecessor_size")
        _require_sha256(predecessor_values[2], "predecessor_sha256")
    planned_size = _bounded_integer(
        value.get("planned_successor_size"),
        0,
        64 * 1024 * 1024,
        "planned_successor_size",
    )
    _require_sha256(value.get("planned_successor_sha256"), "planned_successor_sha256")
    staging_values = (
        value.get("staging_identity"),
        value.get("staging_size"),
        value.get("staging_sha256"),
    )
    if value["stage"] == "PLANNED":
        if any(item is not None for item in staging_values):
            raise SessionValidationError("live_start_external_file_action_staging_invalid")
    else:
        _require_identity(staging_values[0], "staging_identity")
        if staging_values[1] != planned_size or staging_values[2] != value[
            "planned_successor_sha256"
        ]:
            raise SessionValidationError("live_start_external_file_action_staging_invalid")


def _validate_pending_transition(value: Mapping[str, Any]) -> None:
    if value.get("operation") not in PENDING_TRANSITION_OPERATIONS:
        raise SessionValidationError("live_start_pending_operation_invalid")
    if value.get("stage") not in PENDING_TRANSITION_STAGES:
        raise SessionValidationError("live_start_pending_stage_invalid")
    _require_run_id(value.get("run_id"))
    _require_sha256(value.get("expected_session_sha256"), "expected_session_sha256")
    _bounded_integer(value.get("next_action_index"), 0, MAX_FILESYSTEM_NODES, "next_action_index")
    actions = value.get("actions")
    if not isinstance(actions, list) or len(actions) > MAX_FILESYSTEM_NODES:
        raise SessionValidationError("live_start_pending_actions_invalid")
    external = value.get("external_file_action")
    if external is not None:
        validate_embedded_document("external_file_action", external)
    if value["stage"] == "STAGING_BOUND":
        if not isinstance(external, dict) or external.get("stage") != "STAGING_BOUND":
            raise SessionValidationError("live_start_pending_staging_invalid")
    operation = value["operation"]
    stage = value["stage"]
    allowed_stages = {
        "install_output_operation_admission": {"PREPARED", "STAGING_BOUND"},
        "bootstrap_output_child": {
            "PREPARED",
            "STAGING_BOUND",
            "PRIMARY_APPLIED",
        },
        "retire_output_child_claim": {"PREPARED", "PRIMARY_APPLIED"},
        "install_apply_invocation": {
            "PREPARED",
            "STAGING_BOUND",
            "PRIMARY_APPLIED",
        },
        "cleanup_prepublication": {
            "PREPARED",
            "STAGING_BOUND",
            "PRIMARY_APPLIED",
            "CLEANUP_DELETING",
        },
        "review_revision": {
            "PREPARED",
            "STAGING_BOUND",
            "PRIMARY_APPLIED",
        },
    }
    if stage not in allowed_stages.get(
        operation,
        {"PREPARED", "STAGING_BOUND", "PRIMARY_APPLIED"},
    ):
        raise SessionValidationError(
            "live_start_pending_operation_stage_invalid"
        )
    if operation in {
        "install_output_operation_admission",
        "bootstrap_output_child",
        "retire_output_child_claim",
        "cleanup_prepublication",
    } and actions:
        raise SessionValidationError(
            "live_start_pending_operation_actions_invalid"
        )
    if stage == "PREPARED" and value.get("next_action_index") != 0:
        raise SessionValidationError(
            "live_start_pending_initial_action_index_invalid"
        )
    if operation == "install_output_operation_admission" and (
        not isinstance(external, Mapping)
        or external.get("action_kind")
        not in {
            "materialize_output_operation_admission_staging",
            "retire_unbound_output_operation_admission_staging",
            "commit_bound_output_operation_admission",
        }
    ):
        raise SessionValidationError(
            "live_start_output_operation_external_action_invalid"
        )
    if operation == "bootstrap_output_child" and stage in {
        "PREPARED",
        "STAGING_BOUND",
    } and not isinstance(external, Mapping):
        raise SessionValidationError(
            "live_start_output_child_external_action_missing"
        )
    if operation == "retire_output_child_claim" and external is not None:
        raise SessionValidationError(
            "live_start_pending_external_action_forbidden"
        )
    if operation == "install_output_operation_admission":
        _validate_output_operation_pending_matrix(
            value=value,
            stage=stage,
            external=external,
        )
    if operation in {
        "bootstrap_output_child",
        "retire_output_child_claim",
    }:
        _validate_output_child_pending_matrix(
            value=value,
            operation=operation,
            stage=stage,
            external=external,
        )
    if operation == "review_revision":
        _validate_review_revision_pending_matrix(
            value=value,
            stage=stage,
            external=external,
        )
    if operation == "install_apply_invocation":
        _validate_apply_invocation_pending_matrix(
            value=value,
            stage=stage,
            external=external,
        )
    elif any(
        value.get(field_name) is not None
        for field_name in _APPLY_INVOCATION_PENDING_FIELDS
    ):
        raise SessionValidationError(
            "live_start_apply_invocation_authority_forbidden"
        )
    if operation == "materialize_prepublication_work":
        _validate_prepublication_materialization_pending_matrix(
            value=value,
            stage=stage,
            external=external,
        )
    elif value.get("rendered_model_sha256") is not None:
        raise SessionValidationError(
            "live_start_prepublication_materialization_authority_forbidden"
        )
    receipt_parent_fields = (
        value.get("receipt_parent_path"),
        value.get("receipt_parent_identity"),
    )
    if operation in {
        "install_package_validation",
        "install_prepublication_validation",
    }:
        receipt_parent = _require_absolute_path(
            receipt_parent_fields[0],
            "receipt_parent_path",
        )
        _require_identity(
            receipt_parent_fields[1],
            "receipt_parent_identity",
        )
        if receipt_parent.name != "receipts":
            raise SessionValidationError(
                "live_start_receipt_parent_path_invalid"
            )
    elif any(item is not None for item in receipt_parent_fields):
        raise SessionValidationError(
            "live_start_receipt_parent_authority_forbidden"
        )
    cleanup_authority_fields = (
        "cleanup_inventory_path",
        "cleanup_inventory_identity",
        "cleanup_inventory_size",
        "cleanup_inventory_sha256",
        "quarantine_path",
        "cleanup_parent_identity",
        "quarantine_identity",
        "cleanup_cursor",
    )
    if operation == "cleanup_prepublication":
        _validate_prepublication_cleanup_pending_matrix(
            value=value,
            stage=stage,
            external=external,
        )
    elif any(value.get(field_name) is not None for field_name in cleanup_authority_fields):
        raise SessionValidationError(
            "live_start_pending_cleanup_authority_forbidden"
        )


def _validate_apply_invocation_pending_matrix(
    *,
    value: Mapping[str, Any],
    stage: Any,
    external: Any,
) -> None:
    if any(
        value.get(field_name) is not None
        for field_name in (
            _PENDING_TRANSITION_FIELDS
            - _APPLY_INVOCATION_PENDING_ALLOWED_FIELDS
        )
    ):
        raise SessionValidationError(
            "live_start_apply_invocation_pending_field_forbidden"
        )
    apply_attempt_id = value.get("apply_attempt_id")
    _require_run_id(apply_attempt_id)
    _require_sha256(
        value.get("apply_invocation_sha256"),
        "apply_invocation_sha256",
    )
    invocation_document_size = _bounded_integer(
        value.get("apply_invocation_document_size"),
        1,
        APPLY_INVOCATION_MAX_BYTES,
        "apply_invocation_document_size",
    )
    planned_size = _bounded_integer(
        value.get("runtime_admission_document_size"),
        1,
        RUNTIME_LIVE_ATTEMPT_ADMISSION_MAX_BYTES,
        "runtime_admission_document_size",
    )
    planned_sha256 = _require_sha256(
        value.get("runtime_admission_document_sha256"),
        "runtime_admission_document_sha256",
    )
    admission_path = _require_absolute_path(
        value.get("runtime_admission_path"),
        "runtime_admission_path",
    )
    staging_path = _require_absolute_path(
        value.get("runtime_admission_staging_path"),
        "runtime_admission_staging_path",
    )
    inner_temp_path = _require_absolute_path(
        value.get("runtime_admission_staging_inner_temp_path"),
        "runtime_admission_staging_inner_temp_path",
    )
    parent_identity = _require_identity(
        value.get("runtime_admission_parent_identity"),
        "runtime_admission_parent_identity",
    )
    expected_staging_path = admission_path.with_name(
        ".live-start-active-attempt."
        f"{value.get('run_id')}.{apply_attempt_id}.staged"
    )
    expected_inner_temp_path = expected_staging_path.with_name(
        f".{expected_staging_path.name}.live-start-atomic.tmp"
    )
    if (
        admission_path.name != RUNTIME_LIVE_ATTEMPT_ADMISSION_NAME
        or staging_path != expected_staging_path
        or inner_temp_path != expected_inner_temp_path
        or admission_path.parent != staging_path.parent
    ):
        raise SessionValidationError(
            "live_start_runtime_admission_paths_invalid"
        )
    if value.get("actions") != []:
        raise SessionValidationError(
            "live_start_apply_invocation_actions_invalid"
        )
    successor_bindings = _validate_artifact_bindings(
        value.get("successor_artifact_bindings")
    )
    invocation_receipt_sha256 = successor_bindings.get(
        "receipts/apply_invocation.json"
    )
    if (
        frozenset(successor_bindings)
        != _PHASE_MANDATORY_ARTIFACTS[LiveStartPhase.APPLY_STARTED]
        or invocation_receipt_sha256 is None
    ):
        raise SessionValidationError(
            "live_start_apply_invocation_successor_artifacts_invalid"
        )
    _require_sha256(
        invocation_receipt_sha256,
        "apply_invocation_receipt_sha256",
    )
    if (
        value.get("source_phase")
        != LiveStartPhase.PUBLICATION_COMMITTED.value
        or value.get("target_phase") != LiveStartPhase.APPLY_STARTED.value
        or value.get("source_candidate_revision")
        != value.get("target_candidate_revision")
        or value.get("source_revisions_used")
        != value.get("target_revisions_used")
    ):
        raise SessionValidationError(
            "live_start_apply_invocation_cursor_invalid"
        )

    staging_identity = value.get("runtime_admission_staging_identity")
    staging_size = value.get("runtime_admission_staging_size")
    staging_sha256 = value.get("runtime_admission_staging_sha256")
    admission_identity = value.get("runtime_admission_identity")
    admission_sha256 = value.get("runtime_admission_sha256")
    if stage == "PREPARED":
        if any(
            item is not None
            for item in (
                staging_identity,
                staging_size,
                staging_sha256,
                admission_identity,
                admission_sha256,
            )
        ):
            raise SessionValidationError(
                "live_start_runtime_admission_prepared_matrix_invalid"
            )
        expected_actions = {"materialize_runtime_admission_staging"}
        expected_external_stage = "PLANNED"
    elif stage == "STAGING_BOUND":
        bound_identity = _require_identity(
            staging_identity,
            "runtime_admission_staging_identity",
        )
        if (
            staging_size != planned_size
            or staging_sha256 != planned_sha256
            or admission_identity is not None
            or admission_sha256 is not None
        ):
            raise SessionValidationError(
                "live_start_runtime_admission_staging_matrix_invalid"
            )
        expected_actions = {"commit_bound_runtime_admission"}
        expected_external_stage = "STAGING_BOUND"
        if not bound_identity:
            raise SessionValidationError(
                "live_start_runtime_admission_staging_matrix_invalid"
            )
    else:
        bound_identity = _require_identity(
            staging_identity,
            "runtime_admission_staging_identity",
        )
        final_identity = _require_identity(
            admission_identity,
            "runtime_admission_identity",
        )
        if (
            final_identity != bound_identity
            or staging_size != planned_size
            or staging_sha256 != planned_sha256
            or admission_sha256 != planned_sha256
        ):
            raise SessionValidationError(
                "live_start_runtime_admission_primary_matrix_invalid"
            )
        if external is None:
            if value.get("next_action_index") not in {0, 1}:
                raise SessionValidationError(
                    "live_start_apply_invocation_action_index_invalid"
                )
            return
        expected_actions = {
            "materialize_invocation_receipt_staging",
            "commit_bound_invocation_receipt",
        }
        expected_external_stage = (
            "STAGING_BOUND"
            if external.get("action_kind")
            == "commit_bound_invocation_receipt"
            else "PLANNED"
        )

    if not isinstance(external, Mapping):
        raise SessionValidationError(
            "live_start_apply_invocation_external_action_missing"
        )
    if (
        external.get("action_kind") not in expected_actions
        or external.get("stage") != expected_external_stage
        or external.get("commit_mode") != "create_no_replace"
        or external.get("predecessor_state") != "absent"
        or (
            stage in {"PREPARED", "STAGING_BOUND"}
            and _require_identity(
                external.get("parent_identity"),
                "parent_identity",
            )
            != parent_identity
        )
        or external.get("planned_successor_size")
        != (
            planned_size
            if stage in {"PREPARED", "STAGING_BOUND"}
            else external.get("planned_successor_size")
        )
        or external.get("planned_successor_sha256")
        != (
            planned_sha256
            if stage in {"PREPARED", "STAGING_BOUND"}
            else external.get("planned_successor_sha256")
        )
    ):
        raise SessionValidationError(
            "live_start_apply_invocation_external_action_invalid"
        )
    if stage in {"PREPARED", "STAGING_BOUND"} and (
        external.get("final_path") != str(admission_path)
        or external.get("staging_path") != str(staging_path)
        or external.get("inner_temp_path") != str(inner_temp_path)
    ):
        raise SessionValidationError(
            "live_start_apply_invocation_external_action_invalid"
        )
    if stage == "STAGING_BOUND" and (
        _require_identity(external.get("staging_identity"), "staging_identity")
        != _require_identity(staging_identity, "runtime_admission_staging_identity")
        or external.get("staging_size") != staging_size
        or external.get("staging_sha256") != staging_sha256
    ):
        raise SessionValidationError(
            "live_start_apply_invocation_external_action_invalid"
        )
    if stage == "PRIMARY_APPLIED":
        receipt_path = Path(str(external.get("final_path")))
        if (
            receipt_path.name != "apply_invocation.json"
            or receipt_path.parent.name != "receipts"
            or value.get("next_action_index") != 0
            or external.get("planned_successor_size")
            != invocation_document_size
            or external.get("planned_successor_sha256")
            != invocation_receipt_sha256
        ):
            raise SessionValidationError(
                "live_start_invocation_receipt_action_invalid"
            )


def _validate_prepublication_materialization_pending_matrix(
    *,
    value: Mapping[str, Any],
    stage: Any,
    external: Any,
) -> None:
    actions = value.get("actions")
    if (
        stage not in {"PREPARED", "PRIMARY_APPLIED"}
        or external is not None
        or not isinstance(actions, list)
        or not actions
    ):
        raise SessionValidationError(
            "live_start_prepublication_materialization_matrix_invalid"
        )
    expected_paths: list[str] = []
    for action in actions:
        if (
            not isinstance(action, dict)
            or set(action)
            != _PREPUBLICATION_MATERIALIZATION_ACTION_FIELDS
        ):
            raise SessionValidationError(
                "live_start_prepublication_materialization_action_invalid"
            )
        expected_paths.append(
            _require_safe_relative_path(
                action.get("relative_path"),
                "prepublication_materialization_relative_path",
            )
        )
        _bounded_integer(
            action.get("size"),
            0,
            64 * 1024 * 1024,
            "prepublication_materialization_size",
        )
        _require_sha256(
            action.get("sha256"),
            "prepublication_materialization_sha256",
        )
    if expected_paths != sorted(expected_paths) or len(set(expected_paths)) != len(
        expected_paths
    ):
        raise SessionValidationError(
            "live_start_prepublication_materialization_actions_invalid"
        )
    _require_sha256(
        value.get("rendered_model_sha256"),
        "rendered_model_sha256",
    )
    work_parent = _require_absolute_path(
        value.get("work_parent_path"),
        "work_parent_path",
    )
    work_root = _require_absolute_path(value.get("work_root"), "work_root")
    _require_identity(value.get("work_parent_identity"), "work_parent_identity")
    if work_root.parent != work_parent:
        raise SessionValidationError(
            "live_start_prepublication_materialization_path_invalid"
        )
    cursor = value.get("next_action_index")
    if stage == "PREPARED":
        if cursor != 0 or value.get("work_root_identity") is not None:
            raise SessionValidationError(
                "live_start_prepublication_materialization_cursor_invalid"
            )
    else:
        _require_identity(value.get("work_root_identity"), "work_root_identity")
        if type(cursor) is not int or cursor < 0 or cursor > len(actions):
            raise SessionValidationError(
                "live_start_prepublication_materialization_cursor_invalid"
            )
    if any(
        value.get(field_name) is not None
        for field_name in (
            "work_tree_sha256",
            "cleanup_manifest_sha256",
            "cleanup_entry_count",
        )
    ):
        raise SessionValidationError(
            "live_start_prepublication_materialization_result_invalid"
        )


def _validate_review_revision_materialization_source(
    *,
    source: Any,
    external: Any,
) -> None:
    if (
        not isinstance(source, dict)
        or set(source) != _REVIEW_REVISION_MATERIALIZATION_SOURCE_FIELDS
    ):
        raise SessionValidationError(
            "live_start_review_revision_materialization_source_invalid"
        )
    _require_absolute_path(
        source.get("path"),
        "review_revision_materialization_source_path",
    )
    _require_identity(
        source.get("parent_identity"),
        "review_revision_materialization_source_parent_identity",
    )
    _require_identity(
        source.get("identity"),
        "review_revision_materialization_source_identity",
    )
    source_size = _bounded_integer(
        source.get("size"),
        1,
        256 * 1024,
        "review_revision_materialization_source_size",
    )
    source_sha256 = _require_sha256(
        source.get("sha256"),
        "review_revision_materialization_source_sha256",
    )
    if not isinstance(external, Mapping) or (
        source_size != external.get("planned_successor_size")
        or source_sha256 != external.get("planned_successor_sha256")
    ):
        raise SessionValidationError(
            "live_start_review_revision_materialization_source_binding_invalid"
        )


def _validate_review_revision_pending_matrix(
    *,
    value: Mapping[str, Any],
    stage: Any,
    external: Any,
) -> None:
    if any(
        value.get(field_name) is not None
        for field_name in (
            _PENDING_TRANSITION_FIELDS
            - _REVIEW_REVISION_PENDING_ALLOWED_FIELDS
        )
    ):
        raise SessionValidationError(
            "live_start_review_revision_pending_field_forbidden"
        )
    source_revision = _bounded_integer(
        value.get("source_candidate_revision"),
        1,
        2,
        "source_candidate_revision",
    )
    source_revisions_used = _bounded_integer(
        value.get("source_revisions_used"),
        0,
        1,
        "source_revisions_used",
    )
    if (
        value.get("source_phase") != LiveStartPhase.CANDIDATE_VALIDATED.value
        or value.get("target_phase")
        != LiveStartPhase.CANDIDATE_DRAFTED.value
        or value.get("target_candidate_revision")
        != source_revision
        or value.get("target_revisions_used")
        != source_revisions_used + 1
        or value.get("target_revisions_used")
        != source_revision
        or value.get("next_action_index") != 0
    ):
        raise SessionValidationError(
            "live_start_review_revision_cursor_invalid"
        )
    successor_bindings = _validate_artifact_bindings(
        value.get("successor_artifact_bindings")
    )
    review_logical = "starter/starter_config_review.json"
    review_sha256 = successor_bindings.get(review_logical)
    if review_sha256 is None or (
        frozenset(successor_bindings) & _DOWNSTREAM_REVISION_ARTIFACTS
    ) != {review_logical}:
        raise SessionValidationError(
            "live_start_review_revision_successor_invalid"
        )
    actions = value.get("actions")
    if not isinstance(actions, list) or len(actions) != 1:
        raise SessionValidationError(
            "live_start_review_revision_cleanup_action_invalid"
        )
    cleanup = actions[0]
    if (
        not isinstance(cleanup, dict)
        or set(cleanup) != _REVIEW_REVISION_RETIREMENT_ACTION_FIELDS
        or cleanup.get("action")
        != "retire_candidate_validation_receipt"
    ):
        raise SessionValidationError(
            "live_start_review_revision_cleanup_action_invalid"
        )
    _validate_review_revision_materialization_source(
        source=cleanup.get("materialization_source"),
        external=(
            external
            if isinstance(external, Mapping)
            else {
                "planned_successor_size": cleanup.get("review_size"),
                "planned_successor_sha256": cleanup.get("review_sha256"),
            }
        ),
    )
    cleanup_path = _require_absolute_path(
        cleanup.get("path"),
        "review_revision_cleanup_path",
    )
    _require_identity(
        cleanup.get("parent_identity"),
        "review_revision_cleanup_parent_identity",
    )
    _require_identity(
        cleanup.get("historical_identity"),
        "review_revision_cleanup_identity",
    )
    _bounded_integer(
        cleanup.get("historical_size"),
        1,
        256 * 1024,
        "review_revision_cleanup_size",
    )
    _require_sha256(
        cleanup.get("historical_sha256"),
        "review_revision_cleanup_sha256",
    )
    directory_path = _require_absolute_path(
        cleanup.get("directory_path"),
        "review_revision_cleanup_directory_path",
    )
    _require_identity(
        cleanup.get("directory_parent_identity"),
        "review_revision_cleanup_directory_parent_identity",
    )
    _require_identity(
        cleanup.get("directory_identity"),
        "review_revision_cleanup_directory_identity",
    )
    if (
        cleanup_path.name != "candidate_validation.json"
        or cleanup_path.parent != directory_path
        or directory_path.name != "receipts"
    ):
        raise SessionValidationError(
            "live_start_review_revision_cleanup_path_invalid"
        )
    review_binding_values = (
        cleanup.get("review_path"),
        cleanup.get("review_parent_identity"),
        cleanup.get("review_identity"),
        cleanup.get("review_size"),
        cleanup.get("review_sha256"),
    )
    if stage in {"PREPARED", "STAGING_BOUND"}:
        if any(item is not None for item in review_binding_values):
            raise SessionValidationError(
                "live_start_review_revision_final_binding_invalid"
            )
        if (
            not isinstance(external, Mapping)
            or external.get("action_kind")
            != "materialize_review_revision_staging"
            or external.get("stage")
            != ("PLANNED" if stage == "PREPARED" else "STAGING_BOUND")
            or external.get("planned_successor_sha256") != review_sha256
            or Path(str(external.get("final_path"))).name
            != "starter_config_review.json"
        ):
            raise SessionValidationError(
                "live_start_review_revision_external_action_invalid"
            )
    else:
        if external is not None:
            raise SessionValidationError(
                "live_start_review_revision_external_action_invalid"
            )
        review_path = _require_absolute_path(
            review_binding_values[0],
            "review_revision_final_path",
        )
        _require_identity(
            review_binding_values[1],
            "review_revision_final_parent_identity",
        )
        _require_identity(
            review_binding_values[2],
            "review_revision_final_identity",
        )
        _bounded_integer(
            review_binding_values[3],
            1,
            256 * 1024,
            "review_revision_final_size",
        )
        review_digest = _require_sha256(
            review_binding_values[4],
            "review_revision_final_sha256",
        )
        if (
            review_path.name != "starter_config_review.json"
            or review_digest != review_sha256
        ):
            raise SessionValidationError(
                "live_start_review_revision_final_binding_invalid"
            )


def _validate_prepublication_cleanup_pending_matrix(
    *,
    value: Mapping[str, Any],
    stage: Any,
    external: Any,
) -> None:
    work_parent = _require_absolute_path(
        value.get("work_parent_path"),
        "work_parent_path",
    )
    work_root = _require_absolute_path(value.get("work_root"), "work_root")
    inventory_path = _require_absolute_path(
        value.get("cleanup_inventory_path"),
        "cleanup_inventory_path",
    )
    quarantine_path = _require_absolute_path(
        value.get("quarantine_path"),
        "quarantine_path",
    )
    _require_identity(
        value.get("work_parent_identity"),
        "work_parent_identity",
    )
    work_root_identity = _require_identity(
        value.get("work_root_identity"),
        "work_root_identity",
    )
    cleanup_parent_identity = _require_identity(
        value.get("cleanup_parent_identity"),
        "cleanup_parent_identity",
    )
    _require_sha256(value.get("work_tree_sha256"), "work_tree_sha256")
    _require_sha256(
        value.get("cleanup_manifest_sha256"),
        "cleanup_manifest_sha256",
    )
    cleanup_count = _bounded_integer(
        value.get("cleanup_entry_count"),
        0,
        MAX_FILESYSTEM_NODES,
        "cleanup_entry_count",
    )
    inventory_size = _bounded_integer(
        value.get("cleanup_inventory_size"),
        1,
        64 * 1024 * 1024,
        "cleanup_inventory_size",
    )
    inventory_sha256 = _require_sha256(
        value.get("cleanup_inventory_sha256"),
        "cleanup_inventory_sha256",
    )
    cleanup_cursor = _bounded_integer(
        value.get("cleanup_cursor"),
        0,
        cleanup_count,
        "cleanup_cursor",
    )
    if (
        work_root.parent != work_parent
        or inventory_path.parent != quarantine_path.parent
        or inventory_path == quarantine_path
        or value.get("actions") != []
        or value.get("next_action_index") != 0
    ):
        raise SessionValidationError(
            "live_start_prepublication_cleanup_binding_invalid"
        )
    inventory_identity = value.get("cleanup_inventory_identity")
    quarantine_identity = value.get("quarantine_identity")
    if stage in {"PREPARED", "STAGING_BOUND"}:
        if (
            not isinstance(external, Mapping)
            or external.get("stage")
            != ("PLANNED" if stage == "PREPARED" else "STAGING_BOUND")
            or external.get("action_kind")
            not in (
                {
                    "retire_unbound_prepublication_cleanup_inventory_staging",
                    "materialize_prepublication_cleanup_inventory_staging",
                }
                if stage == "PREPARED"
                else {"commit_bound_prepublication_cleanup_inventory"}
            )
            or Path(external.get("final_path", "")) != inventory_path
            or _require_identity(
                external.get("parent_identity"),
                "external_parent_identity",
            )
            != cleanup_parent_identity
            or external.get("planned_successor_size") != inventory_size
            or external.get("planned_successor_sha256") != inventory_sha256
            or inventory_identity is not None
            or quarantine_identity is not None
            or cleanup_cursor != 0
        ):
            raise SessionValidationError(
                "live_start_prepublication_cleanup_inventory_intent_invalid"
            )
        return
    if external is not None:
        raise SessionValidationError(
            "live_start_prepublication_cleanup_external_action_invalid"
        )
    _require_identity(
        inventory_identity,
        "cleanup_inventory_identity",
    )
    if stage == "PRIMARY_APPLIED":
        if quarantine_identity is not None or cleanup_cursor != 0:
            raise SessionValidationError(
                "live_start_prepublication_cleanup_primary_invalid"
            )
        return
    if stage == "CLEANUP_DELETING" and (
        _require_identity(
            quarantine_identity,
            "quarantine_identity",
        )
        != work_root_identity
    ):
        raise SessionValidationError(
            "live_start_prepublication_cleanup_quarantine_invalid"
        )


def _validate_output_operation_pending_matrix(
    *,
    value: Mapping[str, Any],
    stage: Any,
    external: Any,
) -> None:
    for key in (
        "output_base_path",
        "output_operation_admission_path",
        "output_operation_admission_staging_path",
        "output_operation_admission_staging_inner_temp_path",
        "output_child_path",
        "output_bootstrap_lock_path",
    ):
        _require_absolute_path(value.get(key), key)
    for key in (
        "output_base_identity",
        "output_operation_admission_parent_identity",
        "output_bootstrap_lock_identity",
    ):
        _require_identity(value.get(key), key)
    planned_size = _bounded_integer(
        value.get("output_operation_admission_planned_size"),
        1,
        LIVE_START_OUTPUT_OPERATION_ADMISSION_BINDING_MAX_BYTES,
        "output_operation_admission_planned_size",
    )
    planned_sha256 = _require_sha256(
        value.get("output_operation_admission_planned_sha256"),
        "output_operation_admission_planned_sha256",
    )
    staging = (
        value.get("output_operation_admission_staging_identity"),
        value.get("output_operation_admission_staging_size"),
        value.get("output_operation_admission_staging_sha256"),
    )
    final = (
        value.get("output_operation_admission_identity"),
        value.get("output_operation_admission_sha256"),
    )
    if any(item is not None for item in final):
        raise SessionValidationError(
            "live_start_output_operation_pending_final_invalid"
        )
    if stage == "PREPARED":
        if (
            any(item is not None for item in staging)
            or not isinstance(external, Mapping)
            or external.get("stage") != "PLANNED"
        ):
            raise SessionValidationError(
                "live_start_output_operation_pending_staging_invalid"
            )
    elif stage == "STAGING_BOUND":
        if (
            not isinstance(external, Mapping)
            or external.get("stage") != "STAGING_BOUND"
            or _require_identity(
                staging[0],
                "output_operation_admission_staging_identity",
            )
            != _require_identity(
                external.get("staging_identity"),
                "external_staging_identity",
            )
            or staging[1] != planned_size
            or staging[2] != planned_sha256
            or staging[1] != external.get("staging_size")
            or staging[2] != external.get("staging_sha256")
        ):
            raise SessionValidationError(
                "live_start_output_operation_pending_staging_invalid"
            )
    else:
        raise SessionValidationError(
            "live_start_output_operation_pending_stage_invalid"
        )


def _validate_output_child_pending_matrix(
    *,
    value: Mapping[str, Any],
    operation: str,
    stage: Any,
    external: Any,
) -> None:
    for key in (
        "output_base_path",
        "output_child_path",
        "output_claim_path",
        "output_bootstrap_lock_path",
    ):
        _require_absolute_path(value.get(key), key)
    for key in (
        "output_base_identity",
        "output_claim_parent_identity",
        "output_bootstrap_lock_identity",
    ):
        _require_identity(value.get(key), key)
    predecessor_state = value.get("output_child_predecessor_state")
    predecessor_identity = value.get("output_child_predecessor_identity")
    if predecessor_state == "absent":
        if predecessor_identity is not None:
            raise SessionValidationError(
                "live_start_output_child_pending_predecessor_invalid"
            )
    elif predecessor_state == "existing":
        _require_identity(
            predecessor_identity,
            "output_child_predecessor_identity",
        )
    else:
        raise SessionValidationError(
            "live_start_output_child_pending_predecessor_invalid"
        )
    staging = (
        value.get("output_claim_staging_identity"),
        value.get("output_claim_staging_size"),
        value.get("output_claim_staging_sha256"),
    )
    claim = (
        value.get("output_claim_identity"),
        value.get("output_claim_sha256"),
    )
    if operation == "retire_output_child_claim":
        if (
            stage not in {"PREPARED", "PRIMARY_APPLIED"}
            or external is not None
            or any(item is not None for item in staging)
        ):
            raise SessionValidationError(
                "live_start_output_child_retirement_pending_invalid"
            )
        _require_identity(claim[0], "output_claim_identity")
        _require_sha256(claim[1], "output_claim_sha256")
        _require_identity(
            value.get("created_or_confirmed_output_child_identity"),
            "created_or_confirmed_output_child_identity",
        )
        return
    planned_size = _bounded_integer(
        value.get("planned_output_claim_size"),
        1,
        LIVE_START_OUTPUT_CHILD_CLAIM_MAX_BYTES,
        "planned_output_claim_size",
    )
    planned_sha256 = _require_sha256(
        value.get("planned_output_claim_sha256"),
        "planned_output_claim_sha256",
    )
    for key in (
        "output_claim_staging_path",
        "output_claim_staging_inner_temp_path",
    ):
        _require_absolute_path(value.get(key), key)
    if stage == "PREPARED":
        if (
            any(item is not None for item in (*staging, *claim))
            or value.get("created_or_confirmed_output_child_identity")
            is not None
            or not isinstance(external, Mapping)
            or external.get("stage") != "PLANNED"
        ):
            raise SessionValidationError(
                "live_start_output_child_pending_staging_invalid"
            )
        return
    if stage == "STAGING_BOUND":
        if (
            not isinstance(external, Mapping)
            or external.get("stage") != "STAGING_BOUND"
            or _require_identity(
                staging[0], "output_claim_staging_identity"
            )
            != _require_identity(
                external.get("staging_identity"),
                "external_staging_identity",
            )
            or staging[1] != planned_size
            or staging[2] != planned_sha256
            or staging[1] != external.get("staging_size")
            or staging[2] != external.get("staging_sha256")
            or any(item is not None for item in claim)
            or value.get("created_or_confirmed_output_child_identity")
            is not None
        ):
            raise SessionValidationError(
                "live_start_output_child_pending_staging_invalid"
            )
        return
    if stage == "PRIMARY_APPLIED":
        if (
            external is not None
            or _require_identity(
                staging[0], "output_claim_staging_identity"
            )
            is None
            or staging[1] != planned_size
            or staging[2] != planned_sha256
        ):
            raise SessionValidationError(
                "live_start_output_child_pending_primary_invalid"
            )
        _require_identity(claim[0], "output_claim_identity")
        _require_sha256(claim[1], "output_claim_sha256")
        return
    raise SessionValidationError(
        "live_start_output_child_pending_stage_invalid"
    )


def _validate_output_child_binding(value: Mapping[str, Any]) -> None:
    _require_run_id(value.get("run_id"))
    for key in (
        "output_base_path",
        "output_child_path",
        "claim_path",
    ):
        _require_absolute_path(value.get(key), key)
    for key in (
        "output_base_identity",
        "output_child_identity",
        "claim_parent_identity",
    ):
        _require_identity(value.get(key), key)
    if (
        Path(value["output_child_path"]).parent
        != Path(value["output_base_path"])
        or Path(value["claim_path"]).parent
        != Path(value["output_base_path"])
    ):
        raise SessionValidationError(
            "live_start_output_child_path_invalid"
        )
    if value.get("predecessor_state") not in {"absent", "existing"}:
        raise SessionValidationError("live_start_output_child_predecessor_invalid")
    if value.get("claim_state") not in OUTPUT_CHILD_CLAIM_STATES:
        raise SessionValidationError("live_start_output_child_claim_state_invalid")
    predecessor = value.get("predecessor_output_child_identity")
    if value["predecessor_state"] == "absent" and predecessor is not None:
        raise SessionValidationError("live_start_output_child_predecessor_invalid")
    if value["predecessor_state"] == "existing":
        _require_identity(predecessor, "predecessor_output_child_identity")
    claim_triplet = (value.get("claim_identity"), value.get("claim_sha256"))
    if value["claim_state"] == "ACTIVE":
        _require_identity(claim_triplet[0], "claim_identity")
        _require_sha256(claim_triplet[1], "claim_sha256")
    elif any(item is not None for item in claim_triplet):
        raise SessionValidationError("live_start_output_child_retired_claim_invalid")


def _validate_output_operation_binding(value: Mapping[str, Any]) -> None:
    state = value.get("state")
    if state not in OUTPUT_OPERATION_ADMISSION_STATES:
        raise SessionValidationError("live_start_output_operation_state_invalid")
    _require_run_id(value.get("run_id"))
    for key in (
        "admission_path",
        "session_root",
        "operator_profile_path",
        "output_base_root",
        "output_child_path",
        "output_bootstrap_lock_path",
        "output_claim_path",
    ):
        _require_absolute_path(value.get(key), key)
    for key in (
        "admission_parent_identity",
        "admission_identity",
        "session_root_identity",
        "operator_profile_parent_identity",
        "operator_profile_identity",
        "state_root_identity",
        "output_base_root_identity",
        "output_bootstrap_lock_identity",
    ):
        _require_identity(value.get(key), key)
    _bounded_integer(
        value.get("admission_size"),
        1,
        LIVE_START_OUTPUT_OPERATION_ADMISSION_BINDING_MAX_BYTES,
        "output_operation_admission_size",
    )
    for key in (
        "admission_sha256",
        "expected_session_sha256",
        "operator_profile_sha256",
    ):
        _require_sha256(value.get(key), key)
    predecessor_state = value.get("output_child_predecessor_state")
    predecessor_identity = value.get(
        "output_child_predecessor_identity"
    )
    if predecessor_state == "absent":
        if predecessor_identity is not None:
            raise SessionValidationError(
                "live_start_output_operation_predecessor_invalid"
            )
    elif predecessor_state == "existing":
        _require_identity(
            predecessor_identity,
            "output_child_predecessor_identity",
        )
    else:
        raise SessionValidationError(
            "live_start_output_operation_predecessor_invalid"
        )
    handoff_fields = (
        value.get("handoff_runtime_admission_path"),
        value.get("handoff_runtime_admission_parent_identity"),
        value.get("handoff_runtime_admission_identity"),
        value.get("handoff_runtime_admission_sha256"),
    )
    if state == "ACTIVE":
        if value.get("release_handoff_kind") is not None or any(
            item is not None for item in handoff_fields
        ):
            raise SessionValidationError("live_start_output_operation_handoff_invalid")
    elif state == "RUNTIME_HANDOFF_RELEASE_AUTHORIZED":
        if value.get("release_handoff_kind") != "runtime_admission":
            raise SessionValidationError("live_start_output_operation_handoff_invalid")
        _require_absolute_path(handoff_fields[0], "handoff_runtime_admission_path")
        _require_identity(handoff_fields[1], "handoff_runtime_admission_parent_identity")
        _require_identity(handoff_fields[2], "handoff_runtime_admission_identity")
        _require_sha256(handoff_fields[3], "handoff_runtime_admission_sha256")
    elif value.get("release_handoff_kind") != "terminal_no_runtime" or any(
        item is not None for item in handoff_fields
    ):
        raise SessionValidationError("live_start_output_operation_handoff_invalid")


def _validate_runtime_layout(value: Mapping[str, Any]) -> None:
    if value.get("stage") not in {"INCOMPLETE", "COMPLETE"}:
        raise SessionValidationError("live_start_runtime_layout_stage_invalid")
    _require_run_id(value.get("run_id"))
    _require_run_id(value.get("apply_attempt_id"))
    runtime_root = _require_absolute_path(
        value.get("runtime_root"), "runtime_root"
    )
    _require_identity(value.get("runtime_root_identity"), "runtime_root_identity")
    rows = value.get("directories")
    if not isinstance(rows, list) or len(rows) != len(RUNTIME_LAYOUT_DIRECTORY_ROLES):
        raise SessionValidationError("live_start_runtime_layout_directories_invalid")
    if tuple(row.get("role") for row in rows if isinstance(row, dict)) != RUNTIME_LAYOUT_DIRECTORY_ROLES:
        raise SessionValidationError("live_start_runtime_layout_order_invalid")
    observed_paths: list[Path] = []
    expected_paths = {
        "custom_config": runtime_root / "CustomConfig",
        "transactions": runtime_root / ".hsconfig" / "transactions",
        "staging": runtime_root / ".hsconfig" / "staging",
        "receipts": runtime_root / ".hsconfig" / "receipts",
        "attempt_retention": runtime_root
        / ".hsconfig"
        / "attempt-retention",
        "owner_retirements": runtime_root
        / ".hsconfig"
        / "owner-retirements",
    }
    for row in rows:
        if not isinstance(row, dict) or set(row) != _RUNTIME_LAYOUT_DIRECTORY_FIELDS:
            raise SessionValidationError("live_start_runtime_layout_directory_fields_invalid")
        directory_path = _require_absolute_path(
            row.get("path"), "runtime_layout_directory_path"
        )
        role = row["role"]
        if role == "state_receipts":
            receipts_root = runtime_root / ".hsconfig" / "receipts"
            if (
                directory_path.parent != receipts_root
                or _SAFE_TOKEN.fullmatch(directory_path.name) is None
            ):
                raise SessionValidationError(
                    "live_start_runtime_layout_directory_path_invalid"
                )
        elif directory_path != expected_paths[role]:
            raise SessionValidationError(
                "live_start_runtime_layout_directory_path_invalid"
            )
        observed_paths.append(directory_path)
        expected_parent_identity = row.get("expected_parent_identity")
        if role == "state_receipts" and expected_parent_identity is None:
            if (
                row.get("predecessor_state") != "absent"
                or row.get("predecessor_identity") is not None
                or row.get("successor_identity") is not None
            ):
                raise SessionValidationError(
                    "live_start_runtime_layout_parent_binding_invalid"
                )
        else:
            _require_identity(
                expected_parent_identity,
                "expected_parent_identity",
            )
        if row.get("predecessor_state") not in {"absent", "existing"}:
            raise SessionValidationError("live_start_runtime_layout_predecessor_invalid")
        if row["predecessor_state"] == "absent" and row.get("predecessor_identity") is not None:
            raise SessionValidationError("live_start_runtime_layout_predecessor_invalid")
        if row["predecessor_state"] == "existing":
            _require_identity(row.get("predecessor_identity"), "predecessor_identity")
        if row.get("successor_identity") is not None:
            _require_identity(row["successor_identity"], "successor_identity")
    if len(set(observed_paths)) != len(observed_paths):
        raise SessionValidationError(
            "live_start_runtime_layout_directory_path_duplicate"
        )
    count = _bounded_integer(value.get("directory_count"), 0, 7, "directory_count")
    cursor = _bounded_integer(value.get("next_directory_index"), 0, count, "next_directory_index")
    expected_cursor = next(
        (index for index, row in enumerate(rows) if row["successor_identity"] is None),
        count,
    )
    if count != 7 or cursor != expected_cursor:
        raise SessionValidationError("live_start_runtime_layout_cursor_invalid")
    if (value["stage"] == "COMPLETE") != (cursor == count):
        raise SessionValidationError("live_start_runtime_layout_completion_invalid")


def _validate_apply_recovery_document(value: Any) -> Mapping[str, Any]:
    normalized = _normalize_json(value)
    if not isinstance(normalized, dict) or set(normalized) != _APPLY_RECOVERY_FIELDS:
        raise SessionValidationError("live_start_apply_recovery_fields_invalid")
    if len(_canonical_json(normalized)) > LIVE_START_RUNTIME_APPLY_RECOVERY_EVIDENCE_MAX_BYTES:
        raise SessionValidationError("live_start_apply_recovery_size_invalid")
    if normalized.get("schema_version") != LIVE_START_RUNTIME_APPLY_RECOVERY_EVIDENCE_SCHEMA_VERSION:
        raise SessionValidationError("live_start_apply_recovery_schema_invalid")
    if normalized.get("recovery_kind") != LIVE_START_RUNTIME_APPLY_RECOVERY_EVIDENCE_KIND:
        raise SessionValidationError("live_start_apply_recovery_kind_invalid")
    stage = normalized.get("recovery_stage")
    if stage not in RECOVERY_STAGES:
        raise SessionValidationError("live_start_apply_recovery_stage_invalid")
    _require_run_id(normalized.get("run_id"))
    _require_run_id(normalized.get("apply_attempt_id"))
    _bounded_integer(normalized.get("action_index"), 0, MAX_FILESYSTEM_NODES, "action_index")
    action = normalized.get("expected_action")
    if action is not None and action not in RUNTIME_APPLY_RECOVERY_ACTIONS:
        raise SessionValidationError("live_start_apply_recovery_action_invalid")
    if stage == "CLOSED" and action is not None:
        raise SessionValidationError("live_start_apply_recovery_closed_action_invalid")
    if normalized.get("install_route") not in {"new_target", "prior_owner"}:
        raise SessionValidationError("live_start_apply_recovery_route_invalid")
    _require_sha256(
        normalized.get("apply_invocation_sha256"),
        "apply_invocation_sha256",
    )
    _require_absolute_path(
        normalized.get("runtime_admission_path"),
        "runtime_admission_path",
    )
    _require_identity(
        normalized.get("runtime_admission_parent_identity"),
        "runtime_admission_parent_identity",
    )
    _require_identity(
        normalized.get("runtime_admission_identity"),
        "runtime_admission_identity",
    )
    _require_sha256(
        normalized.get("runtime_admission_sha256"),
        "runtime_admission_sha256",
    )
    _require_sha256(
        normalized.get("package_root_sha256"), "package_root_sha256"
    )
    _require_absolute_path(normalized.get("runtime_root"), "runtime_root")
    _require_identity(
        normalized.get("runtime_root_identity"), "runtime_root_identity"
    )
    for prefix in (
        "predecessor_attempt_record",
        "predecessor_journal",
        "predecessor_target_owner_journal",
        "successor_attempt_record",
        "successor_journal",
        "successor_target_owner_journal",
    ):
        _validate_nullable_path_identity_digest(normalized, prefix)
    for prefix in (
        "predecessor_transaction_temp",
        "successor_transaction_temp",
    ):
        _validate_nullable_transaction_temp(normalized, prefix)
    candidate_fields = (
        normalized.get("candidate_path"),
        normalized.get("candidate_parent_identity"),
        normalized.get("predecessor_candidate_identity"),
        normalized.get("successor_candidate_identity"),
    )
    if any(item is not None for item in candidate_fields):
        if (
            candidate_fields[0] is None
            or candidate_fields[1] is None
            or (
                candidate_fields[2] is None
                and candidate_fields[3] is None
                and normalized.get("expected_action")
                not in {
                    "materialize_file_action_staging",
                    "commit_bound_initial_attempt_record",
                    "commit_bound_candidate_planned_attempt_record",
                    "advance_controller_transaction_journal_write",
                    "bind_created_candidate",
                    "observe_not_committed",
                    "observe_unknown",
                }
            )
        ):
            raise SessionValidationError(
                "live_start_apply_recovery_candidate_nullability_invalid"
            )
        _require_absolute_path(candidate_fields[0], "candidate_path")
        _require_identity(
            candidate_fields[1], "candidate_parent_identity"
        )
        for field_name, item in (
            ("predecessor_candidate_identity", candidate_fields[2]),
            ("successor_candidate_identity", candidate_fields[3]),
        ):
            if item is not None:
                _require_identity(item, field_name)
    candidate_tree_fields = (
        normalized.get("candidate_tree_manifest_sha256"),
        normalized.get("candidate_tree_entry_count"),
        normalized.get("candidate_tree_cursor"),
    )
    candidate_tree_next_fields = (
        normalized.get("candidate_tree_next_relative_path"),
        normalized.get("candidate_tree_next_kind"),
        normalized.get("candidate_tree_next_source_identity"),
        normalized.get("candidate_tree_next_size"),
        normalized.get("candidate_tree_next_sha256"),
        normalized.get("candidate_tree_next_parent_identity"),
        normalized.get("candidate_tree_next_successor_identity"),
    )
    if any(item is not None for item in candidate_tree_fields) or any(
        item is not None for item in candidate_tree_next_fields
    ):
        _require_sha256(
            candidate_tree_fields[0],
            "candidate_tree_manifest_sha256",
        )
        entry_count = _bounded_integer(
            candidate_tree_fields[1],
            0,
            MAX_FILESYSTEM_NODES,
            "candidate_tree_entry_count",
        )
        cursor = _bounded_integer(
            candidate_tree_fields[2],
            0,
            entry_count,
            "candidate_tree_cursor",
        )
        if cursor < entry_count:
            relative = candidate_tree_next_fields[0]
            if (
                not isinstance(relative, str)
                or not relative
                or Path(relative).is_absolute()
                or ".." in Path(relative).parts
                or Path(relative).as_posix() != relative
            ):
                raise SessionValidationError(
                    "live_start_candidate_tree_relative_path_invalid"
                )
            if candidate_tree_next_fields[1] not in {"file", "directory"}:
                raise SessionValidationError(
                    "live_start_candidate_tree_kind_invalid"
                )
            _require_identity(
                candidate_tree_next_fields[2],
                "candidate_tree_next_source_identity",
            )
            _bounded_integer(
                candidate_tree_next_fields[3],
                0,
                64 * 1024 * 1024,
                "candidate_tree_next_size",
            )
            _require_sha256(
                candidate_tree_next_fields[4],
                "candidate_tree_next_sha256",
            )
            _require_identity(
                candidate_tree_next_fields[5],
                "candidate_tree_next_parent_identity",
            )
            successor_identity = candidate_tree_next_fields[6]
            if successor_identity is not None:
                _require_identity(
                    successor_identity,
                    "candidate_tree_next_successor_identity",
                )
        elif any(item is not None for item in candidate_tree_next_fields):
            raise SessionValidationError(
                "live_start_candidate_tree_completed_cursor_invalid"
            )
        if (
            normalized.get("candidate_tree_verified_sha256") is not None
            and cursor != entry_count
        ):
            raise SessionValidationError(
                "live_start_candidate_tree_verified_cursor_invalid"
            )
    elif normalized.get("candidate_tree_verified_sha256") is not None:
        raise SessionValidationError(
            "live_start_candidate_tree_verified_without_manifest"
        )
    planned_journal = (
        normalized.get("planned_journal_successor_path"),
        normalized.get("planned_journal_successor_parent_identity"),
        normalized.get("planned_journal_successor_phase"),
        normalized.get("planned_journal_successor_size"),
        normalized.get("planned_journal_successor_sha256"),
    )
    if any(item is not None for item in planned_journal):
        if any(item is None for item in planned_journal):
            raise SessionValidationError(
                "live_start_apply_recovery_planned_journal_invalid"
            )
        _require_absolute_path(
            planned_journal[0], "planned_journal_successor_path"
        )
        _require_identity(
            planned_journal[1],
            "planned_journal_successor_parent_identity",
        )
        if (
            not isinstance(planned_journal[2], str)
            or _SAFE_TOKEN.fullmatch(planned_journal[2]) is None
        ):
            raise SessionValidationError(
                "live_start_apply_recovery_planned_journal_phase_invalid"
            )
        _bounded_integer(
            planned_journal[3],
            0,
            64 * 1024 * 1024,
            "planned_journal_successor_size",
        )
        _require_sha256(
            planned_journal[4], "planned_journal_successor_sha256"
        )
    for key in (
        "last_apply_receipt_sha256",
        "runtime_state_sha256",
        "deck_config_ini_sha256",
        "candidate_tree_manifest_sha256",
        "candidate_tree_verified_sha256",
    ):
        digest = normalized.get(key)
        if digest is not None:
            _require_sha256(digest, key)
    match_status = normalized.get("runtime_match_status")
    if match_status not in {"not_run", "matched", "mismatch", "unknown"}:
        raise SessionValidationError(
            "live_start_apply_recovery_runtime_match_status_invalid"
        )
    match_sha256 = normalized.get("runtime_match_sha256")
    if match_status in {"matched", "mismatch"}:
        _require_sha256(match_sha256, "runtime_match_sha256")
    elif match_sha256 is not None:
        raise SessionValidationError(
            "live_start_apply_recovery_runtime_match_digest_invalid"
        )
    disposition = normalized.get("stable_physical_disposition")
    if disposition not in {
        None,
        "NOT_COMMITTED",
        "COMMITTED",
        "COMMITTED_RECOVERY_PENDING",
        "UNKNOWN_REQUIRES_RECOVERY",
    }:
        raise SessionValidationError(
            "live_start_apply_recovery_disposition_invalid"
        )
    external = normalized.get("external_file_action")
    if external is not None:
        validate_embedded_document("external_file_action", external)
        external_paths = {
            external.get("final_path"),
            external.get("staging_path"),
            external.get("inner_temp_path"),
        }
        if any(
            normalized.get(f"{prefix}_path") in external_paths
            for prefix in (
                "predecessor_transaction_temp",
                "successor_transaction_temp",
            )
            if normalized.get(f"{prefix}_path") is not None
        ):
            raise SessionValidationError(
                "live_start_legacy_transaction_temp_external_alias_invalid"
            )
    owner_retirement = normalized.get("owner_retirement")
    if owner_retirement is not None:
        _validate_owner_retirement_document(owner_retirement)
        _validate_owner_cursor_action_binding(
            recovery=normalized,
            conflict=False,
        )
    if stage == "ACTIVE" and (
        (disposition is None) != (action is not None)
        or (
            disposition is not None
            and (
                external is not None
                or any(
                    normalized.get(field_name) is not None
                    for field_name in _APPLY_RECOVERY_FIELDS
                    if field_name.startswith("successor_")
                )
            )
        )
    ):
        raise SessionValidationError(
            "live_start_apply_recovery_active_matrix_invalid"
        )
    if stage == "CLOSED" and (
        action is not None
        or disposition is None
        or external is not None
        or any(
            normalized.get(field_name) is not None
            for field_name in _APPLY_RECOVERY_FIELDS
            if field_name.startswith("successor_")
        )
    ):
        raise SessionValidationError(
            "live_start_apply_recovery_closed_matrix_invalid"
        )
    claimed = normalized.get("content_sha256")
    unsigned = dict(normalized)
    unsigned.pop("content_sha256")
    if claimed != _self_digest(unsigned):
        raise SessionValidationError("live_start_apply_recovery_digest_invalid")
    return _freeze_mapping(normalized)


_APPLY_RECOVERY_IMMUTABLE_FIELDS = frozenset(
    {
        "schema_version",
        "recovery_kind",
        "run_id",
        "apply_attempt_id",
        "apply_invocation_sha256",
        "runtime_admission_path",
        "runtime_admission_parent_identity",
        "runtime_admission_identity",
        "runtime_admission_sha256",
        "package_root_sha256",
        "runtime_root",
        "runtime_root_identity",
        "install_route",
    }
)

_APPLY_RECOVERY_CURSOR_FIELDS = frozenset(
    {"action_index", "expected_action", "content_sha256"}
)
_APPLY_RECOVERY_TERMINAL_OBSERVATION_PROMOTION_FIELDS = frozenset(
    {
        "predecessor_candidate_identity",
        "successor_candidate_identity",
        "predecessor_renamed_target_identity",
        "successor_renamed_target_identity",
    }
) | frozenset(
    f"{prefix}_{suffix}"
    for prefix, suffixes in (
        ("predecessor_attempt_record", ("path", "identity", "sha256")),
        ("successor_attempt_record", ("path", "identity", "sha256")),
        ("predecessor_journal", ("path", "identity", "sha256")),
        ("successor_journal", ("path", "identity", "sha256")),
        (
            "predecessor_transaction_temp",
            ("path", "parent_identity", "identity", "size", "sha256", "classification", "origin"),
        ),
        (
            "successor_transaction_temp",
            ("path", "parent_identity", "identity", "size", "sha256", "classification", "origin"),
        ),
        (
            "predecessor_target_owner_journal",
            ("path", "identity", "sha256"),
        ),
        (
            "successor_target_owner_journal",
            ("path", "identity", "sha256"),
        ),
    )
    for suffix in suffixes
)
_APPLY_RECOVERY_ACTION_MUTABLE_FIELDS = MappingProxyType(
    {
        "observe_not_committed": frozenset(
            {
                "stable_physical_disposition",
                "external_file_action",
                "candidate_path",
                "candidate_parent_identity",
                "planned_journal_successor_path",
                "planned_journal_successor_parent_identity",
                "planned_journal_successor_phase",
                "planned_journal_successor_size",
                "planned_journal_successor_sha256",
            }
        )
        | _APPLY_RECOVERY_TERMINAL_OBSERVATION_PROMOTION_FIELDS,
        "materialize_file_action_staging": frozenset(
            {"external_file_action"}
        ),
        "retire_unbound_file_action_staging": frozenset(
            {"external_file_action"}
        ),
        "commit_bound_initial_attempt_record": frozenset(
            {
                "external_file_action",
                "successor_attempt_record_path",
                "successor_attempt_record_identity",
                "successor_attempt_record_sha256",
            }
        ),
        "commit_bound_candidate_planned_attempt_record": frozenset(
            {
                "external_file_action",
                "successor_attempt_record_path",
                "successor_attempt_record_identity",
                "successor_attempt_record_sha256",
            }
        ),
        "commit_bound_prior_owner_planned_attempt_record": frozenset(
            {
                "external_file_action",
                "successor_attempt_record_path",
                "successor_attempt_record_identity",
                "successor_attempt_record_sha256",
            }
        ),
        "advance_controller_transaction_journal_write": frozenset(
            {
                "external_file_action",
                "successor_journal_path",
                "successor_journal_identity",
                "successor_journal_sha256",
                "successor_transaction_temp_path",
                "successor_transaction_temp_parent_identity",
                "successor_transaction_temp_identity",
                "successor_transaction_temp_size",
                "successor_transaction_temp_sha256",
                "successor_transaction_temp_classification",
                "successor_transaction_temp_origin",
                "planned_journal_successor_path",
                "planned_journal_successor_parent_identity",
                "planned_journal_successor_phase",
                "planned_journal_successor_size",
                "planned_journal_successor_sha256",
            }
        ),
        "promote_legacy_uuid_transaction_temp": frozenset(
            {
                "external_file_action",
                "successor_journal_path",
                "successor_journal_identity",
                "successor_journal_sha256",
                "successor_transaction_temp_path",
                "successor_transaction_temp_parent_identity",
                "successor_transaction_temp_identity",
                "successor_transaction_temp_size",
                "successor_transaction_temp_sha256",
                "successor_transaction_temp_classification",
                "successor_transaction_temp_origin",
            }
        ),
        "retire_legacy_uuid_transaction_temp": frozenset(
            {
                "successor_transaction_temp_path",
                "successor_transaction_temp_parent_identity",
                "successor_transaction_temp_identity",
                "successor_transaction_temp_size",
                "successor_transaction_temp_sha256",
                "successor_transaction_temp_classification",
                "successor_transaction_temp_origin",
            }
        ),
        "bind_created_candidate": frozenset(
            {
                "external_file_action",
                "candidate_path",
                "candidate_parent_identity",
                "predecessor_candidate_identity",
                "successor_candidate_identity",
            }
        ),
        "bind_candidate_fence": frozenset(
            {
                "external_file_action",
                "successor_attempt_record_path",
                "successor_attempt_record_identity",
                "successor_attempt_record_sha256",
                "candidate_tree_manifest_sha256",
                "candidate_tree_entry_count",
                "candidate_tree_cursor",
                "candidate_tree_next_relative_path",
                "candidate_tree_next_kind",
                "candidate_tree_next_source_identity",
                "candidate_tree_next_size",
                "candidate_tree_next_sha256",
                "candidate_tree_next_parent_identity",
                "candidate_tree_next_successor_identity",
            }
        ),
        "commit_bound_prior_owner_attempt_record": frozenset(
            {
                "external_file_action",
                "successor_attempt_record_path",
                "successor_attempt_record_identity",
                "successor_attempt_record_sha256",
                "planned_journal_successor_path",
                "planned_journal_successor_parent_identity",
                "planned_journal_successor_phase",
                "planned_journal_successor_size",
                "planned_journal_successor_sha256",
            }
        ),
        "materialize_candidate_tree_entry": frozenset(
            {
                "external_file_action",
                "planned_journal_successor_path",
                "planned_journal_successor_parent_identity",
                "planned_journal_successor_phase",
                "planned_journal_successor_size",
                "planned_journal_successor_sha256",
                "candidate_tree_cursor",
                "candidate_tree_next_relative_path",
                "candidate_tree_next_kind",
                "candidate_tree_next_source_identity",
                "candidate_tree_next_size",
                "candidate_tree_next_sha256",
                "candidate_tree_next_parent_identity",
                "candidate_tree_next_successor_identity",
            }
        ),
        "verify_candidate_tree": frozenset(
            {
                "external_file_action",
                "candidate_tree_verified_sha256",
                "planned_journal_successor_path",
                "planned_journal_successor_parent_identity",
                "planned_journal_successor_phase",
                "planned_journal_successor_size",
                "planned_journal_successor_sha256",
            }
        ),
        "rename_candidate_to_target": frozenset(
            {
                "external_file_action",
                "candidate_path",
                "predecessor_candidate_identity",
                "successor_candidate_identity",
                "renamed_target_path",
                "predecessor_renamed_target_identity",
                "successor_renamed_target_identity",
                "planned_journal_successor_path",
                "planned_journal_successor_parent_identity",
                "planned_journal_successor_phase",
                "planned_journal_successor_size",
                "planned_journal_successor_sha256",
            }
        ),
        "bind_renamed_target": frozenset(
            {
                "external_file_action",
                "predecessor_renamed_target_identity",
                "successor_renamed_target_identity",
                "successor_journal_path",
                "successor_journal_identity",
                "successor_journal_sha256",
                "planned_journal_successor_path",
                "planned_journal_successor_parent_identity",
                "planned_journal_successor_phase",
                "planned_journal_successor_size",
                "planned_journal_successor_sha256",
            }
        ),
        "write_deck_config_ini": frozenset(
            {"external_file_action", "deck_config_ini_sha256"}
        ),
        "commit_ini_journal": frozenset(
            {
                "external_file_action",
                "successor_journal_path",
                "successor_journal_identity",
                "successor_journal_sha256",
                "planned_journal_successor_path",
                "planned_journal_successor_parent_identity",
                "planned_journal_successor_phase",
                "planned_journal_successor_size",
                "planned_journal_successor_sha256",
            }
        ),
        "write_runtime_state": frozenset(
            {"external_file_action", "runtime_state_sha256"}
        ),
        "commit_state_journal": frozenset(
            {
                "external_file_action",
                "successor_journal_path",
                "successor_journal_identity",
                "successor_journal_sha256",
                "planned_journal_successor_path",
                "planned_journal_successor_parent_identity",
                "planned_journal_successor_phase",
                "planned_journal_successor_size",
                "planned_journal_successor_sha256",
            }
        ),
        "write_last_apply_receipt": frozenset(
            {"external_file_action", "last_apply_receipt_sha256"}
        ),
        "finalize_journal": frozenset(
            {
                "external_file_action",
                "successor_journal_path",
                "successor_journal_identity",
                "successor_journal_sha256",
                "successor_target_owner_journal_path",
                "successor_target_owner_journal_identity",
                "successor_target_owner_journal_sha256",
                "planned_journal_successor_path",
                "planned_journal_successor_parent_identity",
                "planned_journal_successor_phase",
                "planned_journal_successor_size",
                "planned_journal_successor_sha256",
            }
        ),
        "finalize_attempt_record": frozenset(
            {
                "external_file_action",
                "owner_retirement",
                "successor_attempt_record_path",
                "successor_attempt_record_identity",
                "successor_attempt_record_sha256",
            }
        ),
        "commit_owner_retirement_prepared": frozenset(
            {"external_file_action", "owner_retirement"}
        ),
        "initialize_owner_cleanup_journal": frozenset(
            {"external_file_action", "owner_retirement"}
        ),
        "delete_owner_cleanup_entry": frozenset(
            {"external_file_action", "owner_retirement"}
        ),
        "advance_owner_cleanup_journal": frozenset(
            {"external_file_action", "owner_retirement"}
        ),
        "retire_owner_target_root": frozenset(
            {"external_file_action", "owner_retirement"}
        ),
        "commit_owner_retirement_completed": frozenset(
            {"external_file_action", "owner_retirement"}
        ),
        "retire_old_owner_journal": frozenset({"owner_retirement"}),
        "observe_owner_retirement_completed": frozenset(
            {"owner_retirement"}
        ),
        "observe_committed": frozenset(
            {
                "last_apply_receipt_sha256",
                "runtime_state_sha256",
                "deck_config_ini_sha256",
                "runtime_match_status",
                "runtime_match_sha256",
                "stable_physical_disposition",
            }
        )
        | frozenset(
            field_name
            for field_name in _APPLY_RECOVERY_FIELDS
            if field_name.startswith("successor_")
        )
        | _APPLY_RECOVERY_TERMINAL_OBSERVATION_PROMOTION_FIELDS,
        "observe_pending": frozenset(
            {"runtime_match_status", "stable_physical_disposition"}
        )
        | _APPLY_RECOVERY_TERMINAL_OBSERVATION_PROMOTION_FIELDS,
        "observe_unknown": frozenset(
            {
                "runtime_match_status",
                "stable_physical_disposition",
                "external_file_action",
                "candidate_path",
                "candidate_parent_identity",
                "planned_journal_successor_path",
                "planned_journal_successor_parent_identity",
                "planned_journal_successor_phase",
                "planned_journal_successor_size",
                "planned_journal_successor_sha256",
            }
        )
        | _APPLY_RECOVERY_TERMINAL_OBSERVATION_PROMOTION_FIELDS,
    }
)

_APPLY_RECOVERY_ACTION_NEXT = MappingProxyType(
    {
        "observe_not_committed": frozenset({None}),
        "materialize_file_action_staging": frozenset(
            {
                "commit_bound_initial_attempt_record",
                "commit_bound_candidate_planned_attempt_record",
                "commit_bound_prior_owner_planned_attempt_record",
                "advance_controller_transaction_journal_write",
                "bind_candidate_fence",
                "bind_renamed_target",
                "commit_bound_prior_owner_attempt_record",
                "write_deck_config_ini",
                "commit_ini_journal",
                "write_runtime_state",
                "commit_state_journal",
                "write_last_apply_receipt",
                "finalize_journal",
                "finalize_attempt_record",
                "commit_owner_retirement_prepared",
                "initialize_owner_cleanup_journal",
                "advance_owner_cleanup_journal",
                "commit_owner_retirement_completed",
            }
        ),
        "retire_unbound_file_action_staging": frozenset(
            {"materialize_file_action_staging"}
        ),
        "commit_bound_initial_attempt_record": frozenset(
            {"materialize_file_action_staging"}
        ),
        "commit_bound_candidate_planned_attempt_record": frozenset(
            {"materialize_file_action_staging"}
        ),
        "commit_bound_prior_owner_planned_attempt_record": frozenset(
            {"materialize_file_action_staging"}
        ),
        "advance_controller_transaction_journal_write": frozenset(
            {
                "bind_created_candidate",
                "verify_candidate_tree",
                "rename_candidate_to_target",
                "materialize_file_action_staging",
            }
        ),
        "promote_legacy_uuid_transaction_temp": frozenset(
            {
                "bind_created_candidate",
                "write_deck_config_ini",
                "observe_committed",
            }
        ),
        "retire_legacy_uuid_transaction_temp": frozenset(
            {
                "bind_created_candidate",
                "write_deck_config_ini",
                "observe_committed",
            }
        ),
        "bind_created_candidate": frozenset(
            {"materialize_file_action_staging"}
        ),
        "bind_candidate_fence": frozenset(
            {"materialize_candidate_tree_entry"}
        ),
        "commit_bound_prior_owner_attempt_record": frozenset(
            {"materialize_file_action_staging"}
        ),
        "materialize_candidate_tree_entry": frozenset(
            {
                "materialize_candidate_tree_entry",
                "materialize_file_action_staging",
            }
        ),
        "verify_candidate_tree": frozenset(
            {"materialize_file_action_staging"}
        ),
        "rename_candidate_to_target": frozenset(
            {"materialize_file_action_staging"}
        ),
        "bind_renamed_target": frozenset(
            {"materialize_file_action_staging"}
        ),
        "write_deck_config_ini": frozenset(
            {"materialize_file_action_staging"}
        ),
        "commit_ini_journal": frozenset(
            {"materialize_file_action_staging"}
        ),
        "write_runtime_state": frozenset(
            {"materialize_file_action_staging"}
        ),
        "commit_state_journal": frozenset(
            {"materialize_file_action_staging"}
        ),
        "write_last_apply_receipt": frozenset(
            {"materialize_file_action_staging"}
        ),
        "finalize_journal": frozenset(
            {"materialize_file_action_staging"}
        ),
        "finalize_attempt_record": frozenset(
            {"materialize_file_action_staging", "observe_committed"}
        ),
        "commit_owner_retirement_prepared": frozenset(
            {"materialize_file_action_staging"}
        ),
        "initialize_owner_cleanup_journal": frozenset(
            {"delete_owner_cleanup_entry", "retire_owner_target_root"}
        ),
        "delete_owner_cleanup_entry": frozenset(
            {"materialize_file_action_staging"}
        ),
        "advance_owner_cleanup_journal": frozenset(
            {"delete_owner_cleanup_entry", "retire_owner_target_root"}
        ),
        "retire_owner_target_root": frozenset(
            {"materialize_file_action_staging"}
        ),
        "commit_owner_retirement_completed": frozenset(
            {"retire_old_owner_journal"}
        ),
        "retire_old_owner_journal": frozenset(
            {"observe_owner_retirement_completed"}
        ),
        "observe_owner_retirement_completed": frozenset(
            {"observe_committed"}
        ),
        "observe_committed": frozenset({None}),
        "observe_pending": frozenset({None}),
        "observe_unknown": frozenset({None}),
    }
)


_OWNER_RETIREMENT_PHYSICAL_ACTIONS = frozenset(
    {
        "commit_owner_retirement_prepared",
        "initialize_owner_cleanup_journal",
        "delete_owner_cleanup_entry",
        "advance_owner_cleanup_journal",
        "retire_owner_target_root",
        "commit_owner_retirement_completed",
        "retire_old_owner_journal",
        "observe_owner_retirement_completed",
    }
)


def _owner_action_for_cursor(
    *,
    owner: Mapping[str, Any],
    external: Mapping[str, Any] | None,
) -> str:
    stage = owner.get("stage")
    expected_external_action = {
        "PREPARED_PLANNED": "commit_owner_retirement_prepared",
        "PREPARED": "initialize_owner_cleanup_journal",
        "CLEANING": "advance_owner_cleanup_journal",
        "TARGET_RETIRED": "commit_owner_retirement_completed",
    }.get(stage)
    if external is not None:
        if (
            expected_external_action is None
            or external.get("action_kind") != expected_external_action
        ):
            raise SessionConflictError(
                "live_start_owner_external_action_invalid"
            )
        return (
            "materialize_file_action_staging"
            if external.get("stage") == "PLANNED"
            else str(external.get("action_kind"))
        )
    if stage == "CLEANING":
        return (
            "delete_owner_cleanup_entry"
            if owner.get("cleanup_cursor")
            < owner.get("cleanup_entry_count")
            else "retire_owner_target_root"
        )
    if stage == "COMPLETED":
        return "retire_old_owner_journal"
    if stage == "OWNER_RETIRED":
        return "observe_owner_retirement_completed"
    raise SessionConflictError(
        "live_start_owner_action_precondition_invalid"
    )


def _validate_owner_cursor_action_binding(
    *,
    recovery: Mapping[str, Any],
    conflict: bool,
) -> None:
    owner_raw = recovery.get("owner_retirement")
    if not isinstance(owner_raw, Mapping):
        return
    owner = _validate_owner_retirement_document(owner_raw)
    external_raw = recovery.get("external_file_action")
    external = (
        validate_embedded_document("external_file_action", external_raw)
        if isinstance(external_raw, Mapping)
        else None
    )
    error_type = SessionConflictError if conflict else SessionValidationError
    expected_recovery_action = recovery.get("expected_action")
    stable_disposition = recovery.get("stable_physical_disposition")
    if external is None and stable_disposition is None and (
        expected_recovery_action in {"observe_pending", "observe_unknown"}
        or (
            expected_recovery_action == "observe_committed"
            and owner.get("stage") == "OWNER_RETIRED"
        )
    ):
        return
    if external is None and expected_recovery_action is None:
        if stable_disposition in {
            "COMMITTED_RECOVERY_PENDING",
            "UNKNOWN_REQUIRES_RECOVERY",
        }:
            return
        if (
            stable_disposition == "COMMITTED"
            and owner.get("stage") == "OWNER_RETIRED"
        ):
            return
    if (
        owner.get("stage") == "OWNER_RETIRED"
        and external is None
        and expected_recovery_action == "observe_committed"
    ):
        return
    try:
        expected_action = _owner_action_for_cursor(
            owner=owner,
            external=external,
        )
    except (SessionConflictError, SessionValidationError) as error:
        raise error_type(
            "live_start_owner_action_precondition_invalid"
        ) from error
    if recovery.get("expected_action") != expected_action:
        raise error_type(
            "live_start_owner_action_precondition_invalid"
        )
    if external is None:
        return
    action_index = recovery.get("action_index")
    if type(action_index) is not int:
        raise error_type("live_start_owner_action_index_invalid")
    expected_external_index = (
        action_index
        if external.get("stage") == "PLANNED"
        else action_index - 1
    )
    if external.get("action_index") != expected_external_index:
        raise error_type("live_start_owner_action_index_invalid")


def _owner_successor_action(
    *,
    action: str,
    current_external: Mapping[str, Any] | None,
    successor_owner: Mapping[str, Any],
) -> str:
    if action == "materialize_file_action_staging":
        if current_external is None:
            raise SessionCapabilityError(
                "live_start_owner_external_action_missing"
            )
        return str(current_external["action_kind"])
    if action in {
        "commit_owner_retirement_prepared",
        "delete_owner_cleanup_entry",
        "retire_owner_target_root",
    }:
        return "materialize_file_action_staging"
    if action in {
        "initialize_owner_cleanup_journal",
        "advance_owner_cleanup_journal",
    }:
        return (
            "retire_owner_target_root"
            if successor_owner["cleanup_cursor"]
            == successor_owner["cleanup_entry_count"]
            else "delete_owner_cleanup_entry"
        )
    if action == "commit_owner_retirement_completed":
        return "retire_old_owner_journal"
    if action == "retire_old_owner_journal":
        return "observe_owner_retirement_completed"
    if action == "observe_owner_retirement_completed":
        return "observe_committed"
    raise SessionCapabilityError(
        "live_start_owner_successor_action_invalid"
    )


def _require_owner_external_action(
    external: Any,
    *,
    action_kind: str,
    stage: str,
    final_path: Any,
    predecessor_state: str,
    predecessor_identity: Any,
    predecessor_sha256: Any,
    planned_successor_size: Any | None = None,
    planned_successor_sha256: Any | None = None,
    expected_action_index: int | None = None,
    expected_parent_identity: Any | None = None,
) -> Mapping[str, Any]:
    if not isinstance(external, Mapping):
        raise SessionCapabilityError(
            "live_start_owner_external_action_missing"
        )
    value = validate_embedded_document("external_file_action", external)
    if (
        value.get("action_kind") != action_kind
        or value.get("stage") != stage
        or value.get("final_path") != final_path
        or value.get("predecessor_state") != predecessor_state
        or value.get("predecessor_identity") != predecessor_identity
        or value.get("predecessor_sha256") != predecessor_sha256
        or (
            expected_action_index is not None
            and value.get("action_index") != expected_action_index
        )
        or (
            expected_parent_identity is not None
            and value.get("parent_identity") != expected_parent_identity
        )
        or (
            planned_successor_size is not None
            and value.get("planned_successor_size")
            != planned_successor_size
        )
        or (
            planned_successor_sha256 is not None
            and value.get("planned_successor_sha256")
            != planned_successor_sha256
        )
    ):
        raise SessionCapabilityError(
            "live_start_owner_external_action_invalid"
        )
    return value


def _validate_owner_retirement_successor(
    *,
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    action: str,
) -> None:
    current_owner_raw = predecessor.get("owner_retirement")
    next_owner_raw = successor.get("owner_retirement")
    owner_action = action in _OWNER_RETIREMENT_PHYSICAL_ACTIONS
    if action in {"observe_committed", "observe_pending", "observe_unknown"}:
        if current_owner_raw is None and next_owner_raw is None:
            return
        if not isinstance(current_owner_raw, Mapping) or not isinstance(
            next_owner_raw,
            Mapping,
        ):
            raise SessionCapabilityError(
                "live_start_owner_retirement_cursor_missing"
            )
        current_owner = _validate_owner_retirement_document(
            current_owner_raw
        )
        next_owner = _validate_owner_retirement_document(next_owner_raw)
        expected_disposition = {
            "observe_committed": "COMMITTED",
            "observe_pending": "COMMITTED_RECOVERY_PENDING",
            "observe_unknown": "UNKNOWN_REQUIRES_RECOVERY",
        }[action]
        if (
            current_owner != next_owner
            or predecessor.get("external_file_action") is not None
            or successor.get("external_file_action") is not None
            or successor.get("expected_action") is not None
            or successor.get("stable_physical_disposition")
            != expected_disposition
            or (
                action == "observe_committed"
                and current_owner.get("stage") != "OWNER_RETIRED"
            )
        ):
            raise SessionCapabilityError(
                "live_start_owner_retirement_observation_invalid"
            )
        return
    if action == "finalize_attempt_record" and current_owner_raw is None:
        if not isinstance(next_owner_raw, Mapping):
            return
        next_owner = _validate_owner_retirement_document(next_owner_raw)
        current_external = validate_embedded_document(
            "external_file_action",
            predecessor.get("external_file_action"),
        )
        next_external = _require_owner_external_action(
            successor.get("external_file_action"),
            action_kind="commit_owner_retirement_prepared",
            stage="PLANNED",
            final_path=next_owner["tombstone_path"],
            predecessor_state="absent",
            predecessor_identity=None,
            predecessor_sha256=None,
            planned_successor_sha256=next_owner["tombstone_sha256"],
            expected_action_index=int(successor["action_index"]),
            expected_parent_identity=next_owner[
                "tombstone_parent_identity"
            ],
        )
        runtime_root = Path(str(successor["runtime_root"]))
        transactions_root = runtime_root / ".hsconfig" / "transactions"
        owner_retirements_root = (
            runtime_root / ".hsconfig" / "owner-retirements"
        )
        retired_owner_id = next_owner["retired_owner_transaction_id"]
        successor_owner_id = next_owner["successor_transaction_id"]
        valid = (
            next_owner["stage"] == "PREPARED_PLANNED"
            and successor.get("install_route") == "new_target"
            and current_external.get("action_kind")
            == "finalize_attempt_record"
            and current_external.get("stage") == "STAGING_BOUND"
            and current_external.get("action_index")
            == int(predecessor["action_index"])
            and current_external.get("final_path")
            == successor.get("successor_attempt_record_path")
            and current_external.get("staging_identity")
            == successor.get("successor_attempt_record_identity")
            and current_external.get("staging_sha256")
            == successor.get("successor_attempt_record_sha256")
            and successor.get("expected_action")
            == "materialize_file_action_staging"
            and next_external.get("parent_identity")
            == next_owner["tombstone_parent_identity"]
            and Path(str(next_owner["tombstone_path"]))
            == owner_retirements_root / f"{retired_owner_id}.json"
            and Path(str(next_owner["initial_owner_journal_path"]))
            == transactions_root / f"{retired_owner_id}.json"
            and Path(str(next_owner["successor_owner_journal_path"]))
            == transactions_root / f"{successor_owner_id}.json"
            and Path(str(next_owner["retired_target_path"])).parent
            == runtime_root / "CustomConfig"
            and next_owner["retired_target_path"]
            != successor.get("renamed_target_path")
            and retired_owner_id != successor_owner_id
            and next_owner["current_owner_journal_identity"]
            == next_owner["initial_owner_journal_identity"]
            and next_owner["current_owner_journal_sha256"]
            == next_owner["initial_owner_journal_sha256"]
            and next_owner["successor_transaction_id"]
            == successor["apply_attempt_id"]
            and next_owner["successor_owner_journal_path"]
            == successor.get("successor_target_owner_journal_path")
            == successor.get("successor_journal_path")
            and next_owner["successor_owner_journal_identity"]
            == successor.get("successor_target_owner_journal_identity")
            == successor.get("successor_journal_identity")
            and next_owner["successor_owner_journal_sha256"]
            == successor.get("successor_target_owner_journal_sha256")
            == successor.get("successor_journal_sha256")
        )
        if not valid:
            raise SessionCapabilityError(
                "live_start_owner_retirement_initial_successor_invalid"
            )
        return
    if action == "retire_unbound_file_action_staging" and (
        current_owner_raw is not None or next_owner_raw is not None
    ):
        if not isinstance(current_owner_raw, Mapping) or not isinstance(
            next_owner_raw,
            Mapping,
        ):
            raise SessionCapabilityError(
                "live_start_owner_retirement_cursor_missing"
            )
        current_owner = _validate_owner_retirement_document(
            current_owner_raw
        )
        next_owner = _validate_owner_retirement_document(next_owner_raw)
        current_external = validate_embedded_document(
            "external_file_action",
            predecessor.get("external_file_action"),
        )
        next_external = validate_embedded_document(
            "external_file_action",
            successor.get("external_file_action"),
        )
        immutable_external_fields = _EXTERNAL_FILE_ACTION_FIELDS - {
            "action_index",
            "content_sha256",
        }
        if (
            not _is_unbound_file_action_retirement_alternate(
                recovery=predecessor,
                action=action,
            )
            or current_owner != next_owner
            or current_external.get("stage") != "PLANNED"
            or next_external.get("stage") != "PLANNED"
            or next_external.get("action_index")
            != current_external.get("action_index") + 1
            or any(
                current_external.get(field_name)
                != next_external.get(field_name)
                for field_name in immutable_external_fields
            )
            or successor.get("expected_action")
            != "materialize_file_action_staging"
        ):
            raise SessionCapabilityError(
                "live_start_owner_retirement_successor_invalid"
            )
        return
    if action == "materialize_file_action_staging":
        if current_owner_raw is None and next_owner_raw is None:
            return
    elif not owner_action:
        if current_owner_raw is not None or next_owner_raw is not None:
            raise SessionCapabilityError(
                "live_start_owner_retirement_action_invalid"
            )
        return
    if not isinstance(current_owner_raw, Mapping) or not isinstance(
        next_owner_raw,
        Mapping,
    ):
        raise SessionCapabilityError(
            "live_start_owner_retirement_cursor_missing"
        )
    current = _validate_owner_retirement_document(current_owner_raw)
    next_value = _validate_owner_retirement_document(next_owner_raw)
    current_action_index = predecessor.get("action_index")
    successor_action_index = successor.get("action_index")
    if current_action_index is None and successor_action_index is None:
        current_planned_action_index = None
        current_bound_action_index = None
        successor_planned_action_index = None
    elif (
        type(current_action_index) is int
        and type(successor_action_index) is int
        and successor_action_index == current_action_index + 1
    ):
        current_planned_action_index = current_action_index
        current_bound_action_index = current_action_index - 1
        successor_planned_action_index = successor_action_index
    else:
        raise SessionCapabilityError(
            "live_start_owner_retirement_action_index_invalid"
        )
    mutable_by_action = {
        "materialize_file_action_staging": frozenset(),
        "commit_owner_retirement_prepared": frozenset(
            {"stage", "tombstone_identity"}
        ),
        "initialize_owner_cleanup_journal": frozenset(
            {
                "stage",
                "current_owner_journal_identity",
                "current_owner_journal_sha256",
                "planned_completed_tombstone_size",
                "planned_completed_tombstone_sha256",
            }
        ),
        "delete_owner_cleanup_entry": frozenset(),
        "advance_owner_cleanup_journal": frozenset(
            {
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
            }
        ),
        "retire_owner_target_root": frozenset({"stage"}),
        "commit_owner_retirement_completed": frozenset(
            {"stage", "tombstone_identity", "tombstone_sha256"}
        ),
        "retire_old_owner_journal": frozenset(
            {"stage", "old_owner_journal_retired"}
        ),
        "observe_owner_retirement_completed": frozenset(),
    }
    mutable = mutable_by_action[action] | {"content_sha256"}
    for field_name in _OWNER_RETIREMENT_FIELDS - mutable:
        if current.get(field_name) != next_value.get(field_name):
            raise SessionCapabilityError(
                "live_start_owner_retirement_history_changed"
            )

    if action in {
        "initialize_owner_cleanup_journal",
        "advance_owner_cleanup_journal",
    }:
        try:
            prepared_raw = _read_exact_owner_file(
                path=Path(current["tombstone_path"]),
                expected_parent_identity=_require_identity(
                    current["tombstone_parent_identity"],
                    "owner_tombstone_parent_identity",
                ),
                expected_identity=current["tombstone_identity"],
                expected_sha256=current["tombstone_sha256"],
            )
            _validate_owner_tombstone_binding(
                owner=next_value,
                raw=prepared_raw,
                expected_state="PREPARED",
                expected_raw_sha256=current["tombstone_sha256"],
            )
        except (SessionConflictError, SessionValidationError) as error:
            raise SessionCapabilityError(
                "live_start_owner_retirement_successor_authority_changed"
            ) from error

    current_external = predecessor.get("external_file_action")
    next_external = successor.get("external_file_action")
    if action == "materialize_file_action_staging":
        materialization_by_stage = {
            "PREPARED_PLANNED": (
                "commit_owner_retirement_prepared",
                current["tombstone_path"],
                "absent",
                None,
                None,
                None,
                current["tombstone_sha256"],
            ),
            "PREPARED": (
                "initialize_owner_cleanup_journal",
                current["initial_owner_journal_path"],
                "exact",
                current["current_owner_journal_identity"],
                current["current_owner_journal_sha256"],
                None,
                None,
            ),
            "CLEANING": (
                "advance_owner_cleanup_journal",
                current["initial_owner_journal_path"],
                "exact",
                current["current_owner_journal_identity"],
                current["current_owner_journal_sha256"],
                None,
                None,
            ),
            "TARGET_RETIRED": (
                "commit_owner_retirement_completed",
                current["tombstone_path"],
                "exact",
                current["tombstone_identity"],
                current["tombstone_sha256"],
                current["planned_completed_tombstone_size"],
                current["planned_completed_tombstone_sha256"],
            ),
        }
        materialization = materialization_by_stage.get(current["stage"])
        if materialization is None:
            raise SessionCapabilityError(
                "live_start_owner_materialization_stage_invalid"
            )
        (
            materialized_action,
            final_path,
            predecessor_state,
            predecessor_identity,
            predecessor_sha256,
            planned_successor_size,
            planned_successor_sha256,
        ) = materialization
        planned = _require_owner_external_action(
            current_external,
            action_kind=materialized_action,
            stage="PLANNED",
            final_path=final_path,
            predecessor_state=predecessor_state,
            predecessor_identity=predecessor_identity,
            predecessor_sha256=predecessor_sha256,
            planned_successor_size=planned_successor_size,
            planned_successor_sha256=planned_successor_sha256,
            expected_action_index=current_planned_action_index,
            expected_parent_identity=(
                current["tombstone_parent_identity"]
                if current["stage"] in {"PREPARED_PLANNED", "TARGET_RETIRED"}
                else None
            ),
        )
        bound = _require_owner_external_action(
            next_external,
            action_kind=planned["action_kind"],
            stage="STAGING_BOUND",
            final_path=planned["final_path"],
            predecessor_state=planned["predecessor_state"],
            predecessor_identity=planned["predecessor_identity"],
            predecessor_sha256=planned["predecessor_sha256"],
            planned_successor_size=planned["planned_successor_size"],
            planned_successor_sha256=planned["planned_successor_sha256"],
            expected_action_index=current_planned_action_index,
            expected_parent_identity=(
                current["tombstone_parent_identity"]
                if current["stage"] in {"PREPARED_PLANNED", "TARGET_RETIRED"}
                else None
            ),
        )
        for field_name in _EXTERNAL_FILE_ACTION_FIELDS - {
            "stage",
            "staging_identity",
            "staging_size",
            "staging_sha256",
            "content_sha256",
        }:
            if planned.get(field_name) != bound.get(field_name):
                raise SessionCapabilityError(
                    "live_start_owner_materialization_changed"
                )
        if successor.get("expected_action") != planned["action_kind"]:
            raise SessionCapabilityError(
                "live_start_owner_materialization_action_invalid"
            )
        return

    if action == "commit_owner_retirement_prepared":
        external = _require_owner_external_action(
            current_external,
            action_kind=action,
            stage="STAGING_BOUND",
            final_path=current["tombstone_path"],
            predecessor_state="absent",
            predecessor_identity=None,
            predecessor_sha256=None,
            planned_successor_sha256=current["tombstone_sha256"],
            expected_action_index=current_bound_action_index,
            expected_parent_identity=current["tombstone_parent_identity"],
        )
        _require_owner_external_action(
            next_external,
            action_kind="initialize_owner_cleanup_journal",
            stage="PLANNED",
            final_path=current["initial_owner_journal_path"],
            predecessor_state="exact",
            predecessor_identity=current["initial_owner_journal_identity"],
            predecessor_sha256=current["initial_owner_journal_sha256"],
            expected_action_index=successor_planned_action_index,
        )
        valid = (
            current["stage"] == "PREPARED_PLANNED"
            and next_value["stage"] == "PREPARED"
            and next_value["tombstone_identity"]
            == external["staging_identity"]
            and successor.get("expected_action")
            == "materialize_file_action_staging"
        )
    elif action == "initialize_owner_cleanup_journal":
        external = _require_owner_external_action(
            current_external,
            action_kind=action,
            stage="STAGING_BOUND",
            final_path=current["initial_owner_journal_path"],
            predecessor_state="exact",
            predecessor_identity=current["current_owner_journal_identity"],
            predecessor_sha256=current["current_owner_journal_sha256"],
            expected_action_index=current_bound_action_index,
        )
        at_end = next_value["cleanup_entry_count"] == 0
        valid = (
            current["stage"] == "PREPARED"
            and current["cleanup_cursor"] == 0
            and next_value["stage"] == "CLEANING"
            and next_value["cleanup_cursor"] == 0
            and next_value["current_owner_journal_identity"]
            == external["staging_identity"]
            and next_value["current_owner_journal_sha256"]
            == external["staging_sha256"]
            and next_external is None
            and successor.get("expected_action")
            == (
                "retire_owner_target_root"
                if at_end
                else "delete_owner_cleanup_entry"
            )
        )
    elif action == "delete_owner_cleanup_entry":
        _require_owner_external_action(
            next_external,
            action_kind="advance_owner_cleanup_journal",
            stage="PLANNED",
            final_path=current["initial_owner_journal_path"],
            predecessor_state="exact",
            predecessor_identity=current["current_owner_journal_identity"],
            predecessor_sha256=current["current_owner_journal_sha256"],
            expected_action_index=successor_planned_action_index,
        )
        valid = (
            current["stage"] == "CLEANING"
            and current["cleanup_cursor"] < current["cleanup_entry_count"]
            and next_value == current
            and current_external is None
            and successor.get("expected_action")
            == "materialize_file_action_staging"
        )
    elif action == "advance_owner_cleanup_journal":
        external = _require_owner_external_action(
            current_external,
            action_kind=action,
            stage="STAGING_BOUND",
            final_path=current["initial_owner_journal_path"],
            predecessor_state="exact",
            predecessor_identity=current["current_owner_journal_identity"],
            predecessor_sha256=current["current_owner_journal_sha256"],
            expected_action_index=current_bound_action_index,
        )
        next_cursor = current["cleanup_cursor"] + 1
        at_end = next_cursor == current["cleanup_entry_count"]
        valid = (
            current["stage"] == next_value["stage"] == "CLEANING"
            and next_value["cleanup_cursor"] == next_cursor
            and next_value["current_owner_journal_identity"]
            == external["staging_identity"]
            and next_value["current_owner_journal_sha256"]
            == external["staging_sha256"]
            and next_external is None
            and successor.get("expected_action")
            == (
                "retire_owner_target_root"
                if at_end
                else "delete_owner_cleanup_entry"
            )
        )
    elif action == "retire_owner_target_root":
        _require_owner_external_action(
            next_external,
            action_kind="commit_owner_retirement_completed",
            stage="PLANNED",
            final_path=current["tombstone_path"],
            predecessor_state="exact",
            predecessor_identity=current["tombstone_identity"],
            predecessor_sha256=current["tombstone_sha256"],
            planned_successor_size=current[
                "planned_completed_tombstone_size"
            ],
            planned_successor_sha256=current[
                "planned_completed_tombstone_sha256"
            ],
            expected_action_index=successor_planned_action_index,
            expected_parent_identity=current["tombstone_parent_identity"],
        )
        valid = (
            current["stage"] == "CLEANING"
            and current["cleanup_cursor"] == current["cleanup_entry_count"]
            and next_value["stage"] == "TARGET_RETIRED"
            and current_external is None
            and successor.get("expected_action")
            == "materialize_file_action_staging"
        )
    elif action == "commit_owner_retirement_completed":
        external = _require_owner_external_action(
            current_external,
            action_kind=action,
            stage="STAGING_BOUND",
            final_path=current["tombstone_path"],
            predecessor_state="exact",
            predecessor_identity=current["tombstone_identity"],
            predecessor_sha256=current["tombstone_sha256"],
            planned_successor_size=current[
                "planned_completed_tombstone_size"
            ],
            planned_successor_sha256=current[
                "planned_completed_tombstone_sha256"
            ],
            expected_action_index=current_bound_action_index,
            expected_parent_identity=current["tombstone_parent_identity"],
        )
        valid = (
            current["stage"] == "TARGET_RETIRED"
            and next_value["stage"] == "COMPLETED"
            and next_value["tombstone_identity"]
            == external["staging_identity"]
            and next_value["tombstone_sha256"]
            == external["staging_sha256"]
            and next_external is None
            and successor.get("expected_action")
            == "retire_old_owner_journal"
        )
    elif action == "retire_old_owner_journal":
        valid = (
            current["stage"] == "COMPLETED"
            and next_value["stage"] == "OWNER_RETIRED"
            and next_value["old_owner_journal_retired"] is True
            and current_external is None
            and next_external is None
            and successor.get("expected_action")
            == "observe_owner_retirement_completed"
        )
    else:
        valid = (
            current["stage"] == next_value["stage"] == "OWNER_RETIRED"
            and next_value == current
            and current_external is None
            and next_external is None
            and successor.get("expected_action") == "observe_committed"
        )
    if not valid:
        raise SessionCapabilityError(
            "live_start_owner_retirement_successor_invalid"
        )


def _is_unbound_file_action_retirement_alternate(
    *,
    recovery: Mapping[str, Any],
    action: str,
) -> bool:
    external = recovery.get("external_file_action")
    owner = recovery.get("owner_retirement")
    expected_action = recovery.get("expected_action")
    return (
        action == "retire_unbound_file_action_staging"
        and isinstance(external, Mapping)
        and external.get("stage") == "PLANNED"
        and (
            (
                owner is None
                and expected_action
                in {
                    "materialize_file_action_staging",
                    "observe_not_committed",
                    "observe_unknown",
                }
            )
            or (
                isinstance(owner, Mapping)
                and expected_action == "materialize_file_action_staging"
            )
        )
    )


def _validate_terminal_observation_promotion(
    *,
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    action: str,
) -> None:
    if action not in {
        "observe_not_committed",
        "observe_committed",
        "observe_pending",
        "observe_unknown",
    }:
        return
    for predecessor_prefix, successor_prefix, suffixes in (
        ("predecessor_attempt_record", "successor_attempt_record", ("path", "identity", "sha256")),
        ("predecessor_journal", "successor_journal", ("path", "identity", "sha256")),
        (
            "predecessor_transaction_temp",
            "successor_transaction_temp",
            ("path", "parent_identity", "identity", "size", "sha256", "classification", "origin"),
        ),
        (
            "predecessor_target_owner_journal",
            "successor_target_owner_journal",
            ("path", "identity", "sha256"),
        ),
    ):
        current_successor = tuple(
            predecessor.get(f"{successor_prefix}_{suffix}")
            for suffix in suffixes
        )
        expected_predecessor = (
            current_successor
            if any(item is not None for item in current_successor)
            else tuple(
                predecessor.get(f"{predecessor_prefix}_{suffix}")
                for suffix in suffixes
            )
        )
        if tuple(
            successor.get(f"{predecessor_prefix}_{suffix}")
            for suffix in suffixes
        ) != expected_predecessor or any(
            successor.get(f"{successor_prefix}_{suffix}") is not None
            for suffix in suffixes
        ):
            raise SessionCapabilityError(
                "live_start_terminal_observation_promotion_invalid"
            )
    for predecessor_field, successor_field in (
        ("predecessor_candidate_identity", "successor_candidate_identity"),
        (
            "predecessor_renamed_target_identity",
            "successor_renamed_target_identity",
        ),
    ):
        expected = (
            predecessor.get(successor_field)
            if predecessor.get(successor_field) is not None
            else predecessor.get(predecessor_field)
        )
        if (
            successor.get(predecessor_field) != expected
            or successor.get(successor_field) is not None
        ):
            raise SessionCapabilityError(
                "live_start_terminal_observation_promotion_invalid"
            )


def _validate_apply_recovery_physical_successor(
    *,
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    action: str,
) -> None:
    current = _validate_apply_recovery_document(predecessor)
    next_value = _validate_apply_recovery_document(successor)
    if (
        action not in RUNTIME_APPLY_RECOVERY_ACTIONS
        or current.get("recovery_stage") != "ACTIVE"
        or (
            current.get("expected_action") != action
            and not _is_unbound_file_action_retirement_alternate(
                recovery=current,
                action=action,
            )
        )
        or next_value.get("recovery_stage") != "ACTIVE"
        or next_value.get("action_index") != current.get("action_index") + 1
    ):
        raise SessionCapabilityError(
            "live_start_apply_recovery_successor_invalid"
        )
    for field_name in _APPLY_RECOVERY_IMMUTABLE_FIELDS:
        if current.get(field_name) != next_value.get(field_name):
            raise SessionCapabilityError(
                "live_start_apply_recovery_successor_history_changed"
            )
    mutable = _APPLY_RECOVERY_CURSOR_FIELDS | (
        _APPLY_RECOVERY_ACTION_MUTABLE_FIELDS[action]
    )
    for field_name in _APPLY_RECOVERY_FIELDS - mutable:
        if current.get(field_name) != next_value.get(field_name):
            raise SessionCapabilityError(
                "live_start_apply_recovery_successor_history_changed"
            )
    _validate_terminal_observation_promotion(
        predecessor=current,
        successor=next_value,
        action=action,
    )
    if next_value.get("expected_action") not in (
        _APPLY_RECOVERY_ACTION_NEXT[action]
    ):
        raise SessionCapabilityError(
            "live_start_apply_recovery_next_action_invalid"
        )
    _validate_owner_retirement_successor(
        predecessor=current,
        successor=next_value,
        action=action,
    )
    if action == "materialize_file_action_staging":
        external = next_value.get("external_file_action")
        allowed_commit_actions = {
            "commit_bound_initial_attempt_record",
            "commit_bound_candidate_planned_attempt_record",
            "commit_bound_prior_owner_planned_attempt_record",
            "advance_controller_transaction_journal_write",
            "bind_candidate_fence",
            "bind_renamed_target",
            "commit_bound_prior_owner_attempt_record",
            "write_deck_config_ini",
            "commit_ini_journal",
            "write_runtime_state",
            "commit_state_journal",
            "write_last_apply_receipt",
            "finalize_journal",
            "finalize_attempt_record",
            "commit_owner_retirement_prepared",
            "initialize_owner_cleanup_journal",
            "advance_owner_cleanup_journal",
            "commit_owner_retirement_completed",
        }
        if (
            not isinstance(external, Mapping)
            or external.get("stage") != "STAGING_BOUND"
            or next_value.get("expected_action")
            not in allowed_commit_actions
        ):
            raise SessionCapabilityError(
                "live_start_apply_recovery_successor_invalid"
            )
    if action == "commit_bound_initial_attempt_record":
        current_external = current.get("external_file_action")
        next_external = next_value.get("external_file_action")
        if (
            not isinstance(current_external, Mapping)
            or current_external.get("stage") != "STAGING_BOUND"
            or current_external.get("action_kind") != action
            or current_external.get("predecessor_state") != "absent"
            or current.get("successor_attempt_record_path") is not None
            or not isinstance(next_external, Mapping)
            or next_external.get("stage") != "PLANNED"
            or next_external.get("action_kind")
            != "materialize_file_action_staging"
            or next_external.get("predecessor_state") != "exact"
            or next_external.get("predecessor_identity")
            != next_value.get("successor_attempt_record_identity")
            or next_external.get("predecessor_sha256")
            != next_value.get("successor_attempt_record_sha256")
            or next_value.get("expected_action")
            != "materialize_file_action_staging"
        ):
            raise SessionCapabilityError(
                "live_start_initial_attempt_record_successor_invalid"
            )
    if action == "commit_bound_candidate_planned_attempt_record":
        current_external = current.get("external_file_action")
        next_external = next_value.get("external_file_action")
        candidate_tree_fields = (
            field_name
            for field_name in _APPLY_RECOVERY_FIELDS
            if field_name.startswith("candidate_tree_")
        )
        if (
            not isinstance(current_external, Mapping)
            or current_external.get("stage") != "STAGING_BOUND"
            or current_external.get("action_kind") != action
            or current_external.get("predecessor_state") != "exact"
            or current_external.get("predecessor_identity")
            != current.get("successor_attempt_record_identity")
            or current_external.get("predecessor_sha256")
            != current.get("successor_attempt_record_sha256")
            or current.get("candidate_path") is None
            or current.get("candidate_parent_identity") is None
            or current.get("predecessor_candidate_identity") is not None
            or current.get("planned_journal_successor_path") is None
            or current.get("planned_journal_successor_size") is None
            or current.get("planned_journal_successor_sha256") is None
            or any(current.get(field_name) is not None for field_name in candidate_tree_fields)
            or not isinstance(next_external, Mapping)
            or next_external.get("stage") != "PLANNED"
            or next_external.get("action_kind")
            != "materialize_file_action_staging"
            or next_external.get("predecessor_state") != "absent"
            or next_external.get("final_path")
            != next_value.get("planned_journal_successor_path")
            or next_external.get("planned_successor_size")
            != next_value.get("planned_journal_successor_size")
            or next_external.get("planned_successor_sha256")
            != next_value.get("planned_journal_successor_sha256")
            or next_value.get("expected_action")
            != "materialize_file_action_staging"
        ):
            raise SessionCapabilityError(
                "live_start_candidate_planned_record_successor_invalid"
            )
    if action == "retire_unbound_file_action_staging" and (
        next_value.get("expected_action")
        != "materialize_file_action_staging"
    ):
        raise SessionCapabilityError(
            "live_start_apply_recovery_successor_invalid"
        )
    if action == "materialize_candidate_tree_entry":
        current_count = current.get("candidate_tree_entry_count")
        current_cursor = current.get("candidate_tree_cursor")
        next_cursor = next_value.get("candidate_tree_cursor")
        if (
            not isinstance(current_count, int)
            or isinstance(current_count, bool)
            or not isinstance(current_cursor, int)
            or isinstance(current_cursor, bool)
            or current_cursor >= current_count
            or next_cursor != current_cursor + 1
            or current.get("candidate_tree_next_relative_path") is None
        ):
            raise SessionCapabilityError(
                "live_start_candidate_tree_materialization_successor_invalid"
            )
        expected_next = (
            "materialize_candidate_tree_entry"
            if next_cursor < current_count
            else "materialize_file_action_staging"
        )
        if next_value.get("expected_action") != expected_next:
            raise SessionCapabilityError(
                "live_start_candidate_tree_materialization_successor_invalid"
            )
    if action == "bind_created_candidate" and (
        current.get("candidate_path") is None
        or current.get("successor_candidate_identity") is not None
        or next_value.get("successor_candidate_identity") is None
        or next_value.get("expected_action")
        != "materialize_file_action_staging"
    ):
        raise SessionCapabilityError(
            "live_start_created_candidate_successor_invalid"
        )
    if action == "bind_candidate_fence" and (
        current.get("successor_candidate_identity") is None
        or current.get("candidate_tree_manifest_sha256") is not None
        or next_value.get("candidate_tree_manifest_sha256") is None
        or type(next_value.get("candidate_tree_entry_count")) is not int
        or next_value.get("candidate_tree_entry_count") <= 0
        or next_value.get("candidate_tree_cursor") != 0
        or next_value.get("candidate_tree_next_relative_path") is None
        or next_value.get("candidate_tree_next_parent_identity")
        != current.get("successor_candidate_identity")
        or next_value.get("external_file_action") is not None
        or next_value.get("expected_action")
        != "materialize_candidate_tree_entry"
    ):
        raise SessionCapabilityError(
            "live_start_candidate_fence_successor_invalid"
        )
    if action == "verify_candidate_tree" and (
        current.get("candidate_tree_entry_count")
        != current.get("candidate_tree_cursor")
        or current.get("candidate_tree_verified_sha256") is not None
        or next_value.get("candidate_tree_verified_sha256") is None
        or next_value.get("expected_action")
        != "materialize_file_action_staging"
    ):
        raise SessionCapabilityError(
            "live_start_candidate_tree_verification_successor_invalid"
        )
    if action == "rename_candidate_to_target" and (
        current.get("candidate_tree_verified_sha256") is None
        or current.get("successor_candidate_identity") is None
        or current.get("successor_renamed_target_identity") is not None
        or next_value.get("predecessor_candidate_identity")
        != current.get("successor_candidate_identity")
        or next_value.get("successor_candidate_identity") is not None
        or next_value.get("successor_renamed_target_identity")
        != current.get("successor_candidate_identity")
        or next_value.get("expected_action")
        != "materialize_file_action_staging"
    ):
        raise SessionCapabilityError(
            "live_start_candidate_tree_rename_successor_invalid"
        )
    if action == "advance_controller_transaction_journal_write" and (
        next_value.get("successor_journal_path") is None
        or next_value.get("successor_journal_identity") is None
        or next_value.get("successor_journal_sha256") is None
        or next_value.get("planned_journal_successor_path") is not None
        or (
            next_value.get("external_file_action") is not None
            and not (
                current.get("install_route") == "prior_owner"
                and current.get("planned_journal_successor_phase")
                == "PREPARED"
                and next_value.get("expected_action")
                == "materialize_file_action_staging"
                and isinstance(
                    next_value.get("external_file_action"), Mapping
                )
                and next_value["external_file_action"].get("stage")
                == "PLANNED"
                and next_value["external_file_action"].get("action_kind")
                == "materialize_file_action_staging"
            )
        )
    ):
        raise SessionCapabilityError(
            "live_start_controller_journal_successor_invalid"
        )
    observation_dispositions = {
        "observe_not_committed": "NOT_COMMITTED",
        "observe_committed": "COMMITTED",
        "observe_pending": "COMMITTED_RECOVERY_PENDING",
        "observe_unknown": "UNKNOWN_REQUIRES_RECOVERY",
    }
    if action in observation_dispositions and (
        current.get("stable_physical_disposition") is not None
        or next_value.get("expected_action") is not None
        or next_value.get("stable_physical_disposition")
        != observation_dispositions[action]
    ):
        raise SessionCapabilityError(
            "live_start_apply_recovery_observation_successor_invalid"
        )
    if action in {"observe_not_committed", "observe_unknown"}:
        current_external = current.get("external_file_action")
        candidate_planned_external = (
            isinstance(current_external, Mapping)
            and current.get("install_route") == "new_target"
            and all(
                current.get(field_name) is None
                for field_name in (
                    "planned_journal_successor_path",
                    "planned_journal_successor_parent_identity",
                    "planned_journal_successor_phase",
                    "planned_journal_successor_size",
                    "planned_journal_successor_sha256",
                )
            )
            and current.get("successor_journal_path") is not None
            and current.get("successor_journal_identity") is not None
            and current.get("successor_journal_sha256") is not None
            and current.get("successor_candidate_identity") is not None
            and current.get("predecessor_candidate_identity") is None
            and current.get("candidate_tree_manifest_sha256") is None
            and current.get("candidate_tree_verified_sha256") is None
            and current_external.get("stage") == "PLANNED"
            and current_external.get("action_kind")
            == "materialize_file_action_staging"
            and current_external.get("action_index")
            == current.get("action_index") - 1
            and current_external.get("final_path")
            == current.get("successor_attempt_record_path")
            and current_external.get("predecessor_identity")
            == current.get("successor_attempt_record_identity")
            and current_external.get("predecessor_sha256")
            == current.get("successor_attempt_record_sha256")
        )
        active_fence_external = (
            isinstance(current_external, Mapping)
            and current.get("install_route") == "new_target"
            and current.get("candidate_path") is not None
            and current.get("candidate_parent_identity") is not None
            and current.get("predecessor_candidate_identity") is None
            and current.get("successor_candidate_identity") is None
            and all(
                current.get(field_name) is None
                for field_name in (
                    "predecessor_attempt_record_path",
                    "predecessor_attempt_record_identity",
                    "predecessor_attempt_record_sha256",
                    "predecessor_journal_path",
                    "predecessor_journal_identity",
                    "predecessor_journal_sha256",
                    "successor_journal_path",
                    "successor_journal_identity",
                    "successor_journal_sha256",
                    "predecessor_renamed_target_identity",
                    "successor_renamed_target_identity",
                    "candidate_tree_manifest_sha256",
                    "candidate_tree_verified_sha256",
                    "candidate_tree_entry_count",
                    "candidate_tree_cursor",
                    "candidate_tree_next_relative_path",
                )
            )
            and current.get("successor_attempt_record_path") is not None
            and current.get("successor_attempt_record_identity") is not None
            and current.get("successor_attempt_record_sha256") is not None
            and current.get("planned_journal_successor_path") is not None
            and current.get("planned_journal_successor_parent_identity")
            is not None
            and current.get("planned_journal_successor_phase") == "PREPARED"
            and current.get("planned_journal_successor_size") is not None
            and current.get("planned_journal_successor_sha256") is not None
            and current_external.get("stage") == "PLANNED"
            and current_external.get("action_kind")
            == "materialize_file_action_staging"
            and current_external.get("action_index")
            == current.get("action_index") - 1
            and current_external.get("commit_mode") == "replace_exact"
            and current_external.get("predecessor_state") == "exact"
            and current_external.get("final_path")
            == current.get("successor_attempt_record_path")
            and current_external.get("predecessor_identity")
            == current.get("successor_attempt_record_identity")
            and current_external.get("predecessor_sha256")
            == current.get("successor_attempt_record_sha256")
            and type(current_external.get("predecessor_size")) is int
            and current_external.get("predecessor_size") > 0
            and type(current_external.get("planned_successor_size")) is int
            and current_external.get("planned_successor_size") > 0
            and current_external.get("planned_successor_sha256")
            != current_external.get("predecessor_sha256")
        )
        new_target_ini_external_unknown = (
            action == "observe_unknown"
            and current.get("expected_action") == "observe_unknown"
            and isinstance(current_external, Mapping)
            and current.get("install_route") == "new_target"
            and current.get("deck_config_ini_sha256") is None
            and current_external.get("action_index")
            == current.get("action_index") - 1
            and current_external.get("final_path")
            == str(
                Path(str(current["runtime_root"]))
                / "CustomConfig"
                / "deck_config.ini"
            )
            and (
                (
                    current_external.get("stage") == "PLANNED"
                    and current_external.get("action_kind")
                    == "materialize_file_action_staging"
                )
                or (
                    current_external.get("stage") == "STAGING_BOUND"
                    and current_external.get("action_kind")
                    == "write_deck_config_ini"
                )
            )
            and current.get("successor_journal_path") is not None
            and current.get("successor_journal_identity") is not None
            and current.get("successor_journal_sha256") is not None
            and current.get("planned_journal_successor_path") is not None
            and current.get("planned_journal_successor_parent_identity")
            is not None
            and current.get("planned_journal_successor_phase")
            == "INI_COMMITTED"
            and current.get("planned_journal_successor_size") is not None
            and current.get("planned_journal_successor_sha256") is not None
            and current.get("predecessor_renamed_target_identity") is not None
            and current.get("successor_renamed_target_identity")
            == current.get("predecessor_renamed_target_identity")
            and current.get("candidate_path") is not None
            and current.get("candidate_parent_identity") is not None
            and current.get("predecessor_candidate_identity") is not None
            and current.get("successor_candidate_identity") is None
            and current.get("candidate_tree_manifest_sha256") is not None
            and current.get("candidate_tree_verified_sha256") is not None
            and type(current.get("candidate_tree_entry_count")) is int
            and current.get("candidate_tree_entry_count") > 0
            and current.get("candidate_tree_cursor")
            == current.get("candidate_tree_entry_count")
            and all(
                current.get(field_name) is None
                for field_name in (
                    "candidate_tree_next_relative_path",
                    "candidate_tree_next_kind",
                    "candidate_tree_next_source_identity",
                    "candidate_tree_next_size",
                    "candidate_tree_next_sha256",
                    "candidate_tree_next_parent_identity",
                    "candidate_tree_next_successor_identity",
                )
            )
        )
        prior_owner_bound_ini_external_not_committed = (
            action == "observe_not_committed"
            and current.get("expected_action") == "observe_not_committed"
            and isinstance(current_external, Mapping)
            and current.get("install_route") == "prior_owner"
            and current.get("deck_config_ini_sha256") is None
            and current.get("owner_retirement") is None
            and current.get("successor_attempt_record_path") is not None
            and current.get("successor_attempt_record_identity") is not None
            and current.get("successor_attempt_record_sha256") is not None
            and current.get("successor_journal_path") is not None
            and current.get("successor_journal_identity") is not None
            and current.get("successor_journal_sha256") is not None
            and current.get("planned_journal_successor_path")
            == current.get("successor_journal_path")
            and current.get("planned_journal_successor_parent_identity")
            is not None
            and current.get("planned_journal_successor_phase")
            == "INI_COMMITTED"
            and current.get("planned_journal_successor_size") is not None
            and current.get("planned_journal_successor_sha256") is not None
            and current.get("predecessor_renamed_target_identity")
            == current.get("successor_renamed_target_identity")
            and current.get("successor_renamed_target_identity") is not None
            and current.get("predecessor_target_owner_journal_path")
            is not None
            and current.get("predecessor_target_owner_journal_identity")
            is not None
            and current.get("predecessor_target_owner_journal_sha256")
            is not None
            and all(
                current.get(field_name) is None
                for field_name in (
                    "candidate_path",
                    "candidate_parent_identity",
                    "predecessor_candidate_identity",
                    "successor_candidate_identity",
                )
            )
            and all(
                current.get(field_name) is None
                for field_name in _APPLY_RECOVERY_FIELDS
                if field_name.startswith("candidate_tree_")
            )
            and current_external.get("stage") == "PLANNED"
            and current_external.get("action_kind")
            == "materialize_file_action_staging"
            and current_external.get("action_index")
            == current.get("action_index") - 1
            and Path(str(current_external.get("final_path")))
            == Path(str(current["runtime_root"]))
            / "CustomConfig"
            / "deck_config.ini"
        )
        if (
            next_value.get("external_file_action") is not None
            or (
                current_external is not None
                and not candidate_planned_external
                and not active_fence_external
                and not new_target_ini_external_unknown
                and not prior_owner_bound_ini_external_not_committed
                and (
                    current.get("install_route")
                    not in {"new_target", "prior_owner"}
                    or current.get("planned_journal_successor_phase")
                    != (
                        "RUNTIME_VERIFIED"
                        if current.get("install_route") == "new_target"
                        else "PREPARED"
                    )
                    or
                    current_external.get("stage") != "PLANNED"
                    or current_external.get("action_kind")
                    != "materialize_file_action_staging"
                    or current_external.get("final_path")
                    != (
                        current.get("successor_journal_path")
                        if current.get("install_route") == "new_target"
                        else current.get("planned_journal_successor_path")
                    )
                    or current_external.get("action_index")
                    != current.get("action_index") - 1
                    or any(
                        current_external.get(external_field)
                        != current.get(planned_field)
                        for external_field, planned_field in (
                            ("final_path", "planned_journal_successor_path"),
                            ("parent_identity", "planned_journal_successor_parent_identity"),
                            ("planned_successor_size", "planned_journal_successor_size"),
                            ("planned_successor_sha256", "planned_journal_successor_sha256"),
                        )
                    )
                )
            )
        ):
            raise SessionCapabilityError(
                "live_start_apply_recovery_observation_successor_invalid"
            )
        if current_external is not None and any(
            next_value.get(field_name) is not None
            for field_name in (
                "planned_journal_successor_path",
                "planned_journal_successor_parent_identity",
                "planned_journal_successor_phase",
                "planned_journal_successor_size",
                "planned_journal_successor_sha256",
            )
        ):
            raise SessionCapabilityError(
                "live_start_apply_recovery_observation_successor_invalid"
            )
        if current_external is None and any(
            next_value.get(field_name) != current.get(field_name)
            for field_name in (
                "planned_journal_successor_path",
                "planned_journal_successor_parent_identity",
                "planned_journal_successor_phase",
                "planned_journal_successor_size",
                "planned_journal_successor_sha256",
            )
        ):
            raise SessionCapabilityError(
                "live_start_apply_recovery_observation_successor_invalid"
            )


def _validate_apply_recovery_closure_successor(
    *,
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
) -> None:
    current = _validate_apply_recovery_document(predecessor)
    next_value = _validate_apply_recovery_document(successor)
    if (
        current.get("recovery_stage") != "ACTIVE"
        or current.get("expected_action") is not None
        or current.get("stable_physical_disposition") is None
        or current.get("external_file_action") is not None
        or next_value.get("recovery_stage") != "CLOSED"
    ):
        raise SessionCapabilityError(
            "live_start_apply_recovery_closure_invalid"
        )
    bind_committed_mismatch = (
        current.get("stable_physical_disposition") == "COMMITTED"
        and current.get("runtime_match_status") == "unknown"
        and current.get("runtime_match_sha256") is None
        and next_value.get("runtime_match_status") == "mismatch"
        and isinstance(next_value.get("runtime_match_sha256"), str)
    )
    mutable_fields = {"recovery_stage", "content_sha256"}
    if bind_committed_mismatch:
        mutable_fields.update(
            {"runtime_match_status", "runtime_match_sha256"}
        )
    for field_name in _APPLY_RECOVERY_FIELDS - mutable_fields:
        if current.get(field_name) != next_value.get(field_name):
            raise SessionCapabilityError(
                "live_start_apply_recovery_closure_changed"
            )


def _validate_apply_recovery_pure_phase_successor(
    *,
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    transition: Literal["apply_committed", "runtime_matched"],
) -> None:
    current = _validate_apply_recovery_document(predecessor)
    next_value = _validate_apply_recovery_document(successor)
    runtime_match_bound = (
        transition == "runtime_matched"
        and current.get("stable_physical_disposition") == "COMMITTED"
        and current.get("runtime_match_status") == "unknown"
        and current.get("runtime_match_sha256") is None
        and next_value.get("runtime_match_status") == "matched"
        and isinstance(next_value.get("runtime_match_sha256"), str)
        and all(
            current.get(field_name) == next_value.get(field_name)
            for field_name in _APPLY_RECOVERY_FIELDS
            - {
                "content_sha256",
                "runtime_match_status",
                "runtime_match_sha256",
            }
        )
    )
    if current != next_value and not runtime_match_bound:
        raise SessionCapabilityError(
            f"live_start_{transition}_successor_invalid"
        )


def _validate_apply_recovery_classification_successor(
    *,
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
) -> None:
    current = _validate_apply_recovery_document(predecessor)
    next_value = _validate_apply_recovery_document(successor)
    selected = next_value.get("expected_action")
    if (
        current.get("recovery_stage") != "ACTIVE"
        or current.get("expected_action") is None
        or current.get("stable_physical_disposition") is not None
        or next_value.get("recovery_stage") != "ACTIVE"
        or next_value.get("action_index")
        != current.get("action_index") + 1
        or selected not in RUNTIME_TERMINAL_OBSERVATION_ACTIONS
        or current.get("expected_action")
        in RUNTIME_TERMINAL_OBSERVATION_ACTIONS
        or (
            selected == "observe_pending"
            and current.get("external_file_action") is not None
        )
    ):
        raise SessionCapabilityError(
            "live_start_terminal_classification_successor_invalid"
        )
    mutable = {"action_index", "expected_action", "content_sha256"}
    for field_name in _APPLY_RECOVERY_FIELDS - mutable:
        if current.get(field_name) != next_value.get(field_name):
            raise SessionCapabilityError(
                "live_start_terminal_classification_history_changed"
            )


_TERMINAL_RETIREMENT_SUCCESSOR_STAGES = MappingProxyType(
    {
        "ack_success": frozenset(
            {
                ("PREPARED", "ack_journal_retired", "ACK_JOURNAL_RETIRED"),
                ("PREPARED", "evidence_retired", "EVIDENCE_RETIRED"),
                (
                    "ACK_JOURNAL_RETIRED",
                    "evidence_retired",
                    "EVIDENCE_RETIRED",
                ),
                (
                    "EVIDENCE_RETIRED",
                    "admission_release_authorized",
                    "ADMISSION_RELEASE_AUTHORIZED",
                ),
            }
        ),
        "release_not_committed": frozenset(
            {
                ("PREPARED", "evidence_retired", "EVIDENCE_RETIRED"),
                (
                    "EVIDENCE_RETIRED",
                    "admission_release_authorized",
                    "ADMISSION_RELEASE_AUTHORIZED",
                ),
            }
        ),
        "release_committed_mismatch": frozenset(
            {
                ("PREPARED", "evidence_retired", "EVIDENCE_RETIRED"),
                (
                    "EVIDENCE_RETIRED",
                    "admission_release_authorized",
                    "ADMISSION_RELEASE_AUTHORIZED",
                ),
            }
        ),
        "release_resolved_terminal": frozenset(
            {
                (
                    "RECOVERY_STABILIZED",
                    "evidence_retired",
                    "EVIDENCE_RETIRED",
                ),
                (
                    "EVIDENCE_RETIRED",
                    "admission_release_authorized",
                    "ADMISSION_RELEASE_AUTHORIZED",
                ),
            }
        ),
    }
)


def _validate_terminal_retirement_successor(
    *,
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    transition: str,
) -> None:
    current = validate_embedded_document(
        "terminal_retirement", predecessor
    )
    next_value = validate_embedded_document(
        "terminal_retirement", successor
    )
    operation = current["operation"]
    edge = (current["stage"], transition, next_value["stage"])
    if (
        next_value["operation"] != operation
        or edge not in _TERMINAL_RETIREMENT_SUCCESSOR_STAGES[operation]
    ):
        raise SessionCapabilityError(
            "live_start_terminal_retirement_successor_invalid"
        )
    for field_name in _TERMINAL_RETIREMENT_FIELDS - {
        "stage",
        "content_sha256",
    }:
        if current.get(field_name) != next_value.get(field_name):
            raise SessionCapabilityError(
                "live_start_terminal_retirement_successor_changed"
            )


_TERMINAL_RESOLUTION_OUTER_EDGES = MappingProxyType(
    {
        "cleanup_inventory_unbound_staging_retired": frozenset(
            {("RECOVERY_PREPARED", "RECOVERY_PREPARED")}
        ),
        "cleanup_inventory_staging_bound": frozenset(
            {("RECOVERY_PREPARED", "RECOVERY_PREPARED")}
        ),
        "inventory_bound": frozenset(
            {("RECOVERY_PREPARED", "RECOVERY_INVENTORY_BOUND")}
        ),
        "cleaning_started": frozenset(
            {("RECOVERY_INVENTORY_BOUND", "RECOVERY_CLEANING")}
        ),
        "cleanup_cursor_advanced": frozenset(
            {("RECOVERY_CLEANING", "RECOVERY_CLEANING")}
        ),
        "journal_retired": frozenset(
            {
                ("RECOVERY_PREPARED", "RECOVERY_JOURNAL_RETIRED"),
                ("RECOVERY_CLEANING", "RECOVERY_JOURNAL_RETIRED"),
            }
        ),
        "fence_retired": frozenset(
            {
                ("RECOVERY_PREPARED", "RECOVERY_FENCE_RETIRED"),
                (
                    "RECOVERY_JOURNAL_RETIRED",
                    "RECOVERY_FENCE_RETIRED",
                ),
            }
        ),
        "inventory_retired": frozenset(
            {
                (
                    "RECOVERY_FENCE_RETIRED",
                    "RECOVERY_INVENTORY_RETIRED",
                )
            }
        ),
        "physical_recovery_advanced": frozenset(
            {("RECOVERY_PREPARED", "RECOVERY_PREPARED")}
        ),
        "stabilized": frozenset(
            {
                ("RECOVERY_PREPARED", "RECOVERY_STABILIZED"),
                ("RECOVERY_FENCE_RETIRED", "RECOVERY_STABILIZED"),
                ("RECOVERY_INVENTORY_RETIRED", "RECOVERY_STABILIZED"),
            }
        ),
    }
)

_TERMINAL_RESOLUTION_MUTABLE_FIELDS = MappingProxyType(
    {
        "cleanup_inventory_unbound_staging_retired": frozenset(
            {"external_file_action"}
        ),
        "cleanup_inventory_staging_bound": frozenset(
            {"external_file_action"}
        ),
        "inventory_bound": frozenset(
            {
                "external_file_action",
                "cleanup_stage",
                "cleanup_inventory_identity",
            }
        ),
        "cleaning_started": frozenset({"cleanup_stage"}),
        "cleanup_cursor_advanced": frozenset({"cleanup_cursor"}),
        "journal_retired": frozenset(
            {
                "cleanup_stage",
                "successor_journal_path",
                "successor_journal_identity",
                "successor_journal_sha256",
            }
        ),
        "fence_retired": frozenset(
            {
                "cleanup_stage",
                "successor_attempt_record_path",
                "successor_attempt_record_identity",
                "successor_attempt_record_sha256",
            }
        ),
        "inventory_retired": frozenset({"cleanup_stage"}),
        "physical_recovery_advanced": frozenset(
            {
                "action_index",
                "allowed_attempt_record_successor_state",
                "allowed_journal_successor_phase",
                "successor_attempt_record_path",
                "successor_attempt_record_identity",
                "successor_attempt_record_sha256",
                "successor_journal_path",
                "successor_journal_identity",
                "successor_journal_sha256",
                "successor_transaction_temp_path",
                "successor_transaction_temp_parent_identity",
                "successor_transaction_temp_identity",
                "successor_transaction_temp_size",
                "successor_transaction_temp_sha256",
                "successor_transaction_temp_classification",
                "successor_transaction_temp_origin",
                "planned_journal_successor_path",
                "planned_journal_successor_parent_identity",
                "planned_journal_successor_phase",
                "planned_journal_successor_size",
                "planned_journal_successor_sha256",
                "successor_target_owner_journal_path",
                "successor_target_owner_journal_identity",
                "successor_target_owner_journal_sha256",
                "candidate_path",
                "candidate_parent_identity",
                "predecessor_candidate_identity",
                "successor_candidate_identity",
                "external_file_action",
                "owner_retirement",
                "resolved_physical_disposition",
                "last_apply_receipt_sha256",
                "runtime_state_sha256",
                "deck_config_ini_sha256",
                "runtime_match_status",
                "runtime_match_sha256",
            }
        )
        | (
            _APPLY_RECOVERY_TERMINAL_OBSERVATION_PROMOTION_FIELDS
            & _TERMINAL_RESOLUTION_FIELDS
        ),
        "stabilized": frozenset(
            {
                "cleanup_stage",
                "successor_attempt_record_path",
                "successor_attempt_record_identity",
                "successor_attempt_record_sha256",
                "successor_journal_path",
                "successor_journal_identity",
                "successor_journal_sha256",
                "successor_target_owner_journal_path",
                "successor_target_owner_journal_identity",
                "successor_target_owner_journal_sha256",
                "external_file_action",
                "owner_retirement",
                "resolved_physical_disposition",
                "last_apply_receipt_sha256",
                "runtime_state_sha256",
                "deck_config_ini_sha256",
                "runtime_match_status",
                "runtime_match_sha256",
            }
        ),
    }
)


def _terminal_resolution_effective_triplet(
    resolution: Mapping[str, Any],
    *,
    authority: str,
) -> tuple[str, PathIdentity, str]:
    if authority not in {"attempt_record", "journal"}:
        raise SessionCapabilityError(
            "live_start_terminal_authority_family_invalid"
        )
    prefix = (
        f"successor_{authority}"
        if resolution.get(f"successor_{authority}_path") is not None
        else f"predecessor_{authority}"
    )
    path = resolution.get(f"{prefix}_path")
    identity = resolution.get(f"{prefix}_identity")
    digest = resolution.get(f"{prefix}_sha256")
    if (
        not isinstance(path, str)
        or not isinstance(identity, (list, tuple))
        or not isinstance(digest, str)
    ):
        raise SessionCapabilityError(
            "live_start_terminal_authority_triplet_invalid"
        )
    return path, tuple(identity), digest


def _validate_terminal_ownerless_commit_ini_successor(
    *,
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    authorized_owner_action: str | None,
) -> None:
    current_external_raw = predecessor.get("external_file_action")
    next_external_raw = successor.get("external_file_action")
    if (
        authorized_owner_action is not None
        or not isinstance(current_external_raw, Mapping)
        or not isinstance(next_external_raw, Mapping)
    ):
        raise SessionCapabilityError(
            "live_start_terminal_ownerless_commit_ini_invalid"
        )
    current_external = validate_embedded_document(
        "external_file_action",
        current_external_raw,
    )
    next_external = validate_embedded_document(
        "external_file_action",
        next_external_raw,
    )
    current_journal = _terminal_resolution_effective_triplet(
        predecessor,
        authority="journal",
    )
    next_journal = _terminal_resolution_effective_triplet(
        successor,
        authority="journal",
    )
    current_action_index = predecessor.get("action_index")
    next_action_index = successor.get("action_index")
    state_path = Path(current_journal[0]).parent.parent / "state.json"
    candidate_fields = (
        predecessor.get("candidate_path"),
        predecessor.get("candidate_parent_identity"),
        predecessor.get("predecessor_candidate_identity"),
        predecessor.get("successor_candidate_identity"),
    )
    owner_triplet = tuple(
        predecessor.get(f"predecessor_target_owner_journal_{suffix}")
        for suffix in ("path", "identity", "sha256")
    )
    if (
        type(current_action_index) is not int
        or next_action_index != current_action_index + 1
        or predecessor.get("cleanup_stage") is not None
        or predecessor.get("predecessor_transaction_temp_path") is not None
        or predecessor.get("deck_config_ini_sha256") is None
        or predecessor.get("resolved_physical_disposition")
        not in {
            "COMMITTED_RECOVERY_PENDING",
            "UNKNOWN_REQUIRES_RECOVERY",
        }
        or any(value is not None for value in candidate_fields)
        or any(value is None for value in owner_triplet)
        or predecessor.get("allowed_journal_successor_phase")
        != "INI_COMMITTED"
        or predecessor.get("planned_journal_successor_phase")
        != "INI_COMMITTED"
        or predecessor.get("planned_journal_successor_path")
        != current_journal[0]
        or predecessor.get("planned_journal_successor_parent_identity")
        != current_external.get("parent_identity")
        or predecessor.get("planned_journal_successor_size")
        != current_external.get("planned_successor_size")
        or predecessor.get("planned_journal_successor_sha256")
        != current_external.get("planned_successor_sha256")
        or current_external.get("stage") != "STAGING_BOUND"
        or current_external.get("action_kind") != "commit_ini_journal"
        or current_external.get("action_index") != current_action_index
        or current_external.get("final_path") != current_journal[0]
        or current_external.get("predecessor_state") != "exact"
        or current_external.get("predecessor_identity")
        != current_journal[1]
        or current_external.get("predecessor_sha256")
        != current_journal[2]
        or current_external.get("staging_size")
        != current_external.get("planned_successor_size")
        or current_external.get("staging_sha256")
        != current_external.get("planned_successor_sha256")
        or successor.get("allowed_journal_successor_phase")
        != "STATE_COMMITTED"
        or successor.get("planned_journal_successor_phase")
        != "STATE_COMMITTED"
        or successor.get("planned_journal_successor_path")
        != next_journal[0]
        or successor.get("planned_journal_successor_parent_identity")
        != current_external.get("parent_identity")
        or next_journal[0] != current_journal[0]
        or next_journal[1] != current_external.get("staging_identity")
        or next_journal[2] != current_external.get("staging_sha256")
        or next_external.get("stage") != "PLANNED"
        or next_external.get("action_kind")
        != "materialize_file_action_staging"
        or next_external.get("action_index") != next_action_index
        or Path(str(next_external.get("final_path"))) != state_path
        or next_external.get("staging_identity") is not None
        or next_external.get("staging_size") is not None
        or next_external.get("staging_sha256") is not None
    ):
        raise SessionCapabilityError(
            "live_start_terminal_ownerless_commit_ini_invalid"
        )
    mutable_fields = {
        "action_index",
        "allowed_journal_successor_phase",
        "successor_journal_path",
        "successor_journal_identity",
        "successor_journal_sha256",
        "planned_journal_successor_path",
        "planned_journal_successor_parent_identity",
        "planned_journal_successor_phase",
        "planned_journal_successor_size",
        "planned_journal_successor_sha256",
        "external_file_action",
        "content_sha256",
    }
    for field_name in _TERMINAL_RESOLUTION_FIELDS - mutable_fields:
        if predecessor.get(field_name) != successor.get(field_name):
            raise SessionCapabilityError(
                "live_start_terminal_ownerless_commit_ini_history_changed"
            )


def _validate_terminal_ownerless_commit_state_successor(
    *,
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    authorized_owner_action: str | None,
) -> None:
    current_external_raw = predecessor.get("external_file_action")
    next_external_raw = successor.get("external_file_action")
    if (
        authorized_owner_action is not None
        or not isinstance(current_external_raw, Mapping)
        or not isinstance(next_external_raw, Mapping)
    ):
        raise SessionCapabilityError(
            "live_start_terminal_ownerless_commit_state_invalid"
        )
    current_external = validate_embedded_document(
        "external_file_action",
        current_external_raw,
    )
    next_external = validate_embedded_document(
        "external_file_action",
        next_external_raw,
    )
    current_journal = _terminal_resolution_effective_triplet(
        predecessor,
        authority="journal",
    )
    next_journal = _terminal_resolution_effective_triplet(
        successor,
        authority="journal",
    )
    current_action_index = predecessor.get("action_index")
    next_action_index = successor.get("action_index")
    journal_path = Path(current_journal[0])
    metadata_root = journal_path.parent.parent
    receipt_path = Path(str(next_external.get("final_path")))
    candidate_fields = (
        predecessor.get("candidate_path"),
        predecessor.get("candidate_parent_identity"),
        predecessor.get("predecessor_candidate_identity"),
        predecessor.get("successor_candidate_identity"),
    )
    owner_triplet = tuple(
        predecessor.get(f"predecessor_target_owner_journal_{suffix}")
        for suffix in ("path", "identity", "sha256")
    )
    if (
        type(current_action_index) is not int
        or next_action_index != current_action_index + 1
        or predecessor.get("cleanup_stage") is not None
        or predecessor.get("predecessor_transaction_temp_path") is not None
        or predecessor.get("deck_config_ini_sha256") is None
        or predecessor.get("runtime_state_sha256") is None
        or predecessor.get("last_apply_receipt_sha256") is not None
        or predecessor.get("resolved_physical_disposition")
        not in {
            "COMMITTED_RECOVERY_PENDING",
            "UNKNOWN_REQUIRES_RECOVERY",
        }
        or any(value is not None for value in candidate_fields)
        or any(value is None for value in owner_triplet)
        or predecessor.get("allowed_journal_successor_phase")
        != "STATE_COMMITTED"
        or predecessor.get("planned_journal_successor_phase")
        != "STATE_COMMITTED"
        or predecessor.get("planned_journal_successor_path")
        != current_journal[0]
        or predecessor.get("planned_journal_successor_parent_identity")
        != current_external.get("parent_identity")
        or predecessor.get("planned_journal_successor_size")
        != current_external.get("planned_successor_size")
        or predecessor.get("planned_journal_successor_sha256")
        != current_external.get("planned_successor_sha256")
        or current_external.get("stage") != "STAGING_BOUND"
        or current_external.get("action_kind") != "commit_state_journal"
        or current_external.get("action_index") != current_action_index
        or current_external.get("final_path") != current_journal[0]
        or current_external.get("predecessor_state") != "exact"
        or current_external.get("predecessor_identity")
        != current_journal[1]
        or current_external.get("predecessor_sha256")
        != current_journal[2]
        or current_external.get("staging_size")
        != current_external.get("planned_successor_size")
        or current_external.get("staging_sha256")
        != current_external.get("planned_successor_sha256")
        or successor.get("allowed_journal_successor_phase")
        != "FINALIZED"
        or successor.get("planned_journal_successor_phase")
        != "FINALIZED"
        or successor.get("planned_journal_successor_path")
        != next_journal[0]
        or successor.get("planned_journal_successor_parent_identity")
        != current_external.get("parent_identity")
        or next_journal[0] != current_journal[0]
        or next_journal[1] != current_external.get("staging_identity")
        or next_journal[2] != current_external.get("staging_sha256")
        or next_external.get("stage") != "PLANNED"
        or next_external.get("action_kind")
        != "materialize_file_action_staging"
        or next_external.get("action_index") != next_action_index
        or receipt_path.name != "last_apply_receipt.json"
        or receipt_path.parent.parent != metadata_root / "receipts"
        or not receipt_path.parent.name
        or Path(str(next_external.get("staging_path")))
        != receipt_path.with_name(f"{receipt_path.name}.staged")
        or Path(str(next_external.get("inner_temp_path")))
        != receipt_path.with_name(
            f".{receipt_path.name}.staged.live-start-atomic.tmp"
        )
        or next_external.get("staging_identity") is not None
        or next_external.get("staging_size") is not None
        or next_external.get("staging_sha256") is not None
    ):
        raise SessionCapabilityError(
            "live_start_terminal_ownerless_commit_state_invalid"
        )
    mutable_fields = {
        "action_index",
        "allowed_journal_successor_phase",
        "successor_journal_path",
        "successor_journal_identity",
        "successor_journal_sha256",
        "planned_journal_successor_path",
        "planned_journal_successor_parent_identity",
        "planned_journal_successor_phase",
        "planned_journal_successor_size",
        "planned_journal_successor_sha256",
        "external_file_action",
        "content_sha256",
    }
    for field_name in _TERMINAL_RESOLUTION_FIELDS - mutable_fields:
        if predecessor.get(field_name) != successor.get(field_name):
            raise SessionCapabilityError(
                "live_start_terminal_ownerless_commit_state_history_changed"
            )


def _validate_terminal_ownerless_finalize_journal_successor(
    *,
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    authorized_owner_action: str | None,
) -> None:
    current_external_raw = predecessor.get("external_file_action")
    next_external_raw = successor.get("external_file_action")
    if (
        authorized_owner_action is not None
        or not isinstance(current_external_raw, Mapping)
        or not isinstance(next_external_raw, Mapping)
    ):
        raise SessionCapabilityError(
            "live_start_terminal_ownerless_finalize_journal_invalid"
        )
    current_external = validate_embedded_document(
        "external_file_action",
        current_external_raw,
    )
    next_external = validate_embedded_document(
        "external_file_action",
        next_external_raw,
    )
    current_journal = _terminal_resolution_effective_triplet(
        predecessor,
        authority="journal",
    )
    next_journal = _terminal_resolution_effective_triplet(
        successor,
        authority="journal",
    )
    current_attempt = _terminal_resolution_effective_triplet(
        predecessor,
        authority="attempt_record",
    )
    next_attempt = _terminal_resolution_effective_triplet(
        successor,
        authority="attempt_record",
    )
    current_action_index = predecessor.get("action_index")
    next_action_index = successor.get("action_index")
    candidate_fields = (
        predecessor.get("candidate_path"),
        predecessor.get("candidate_parent_identity"),
        predecessor.get("predecessor_candidate_identity"),
        predecessor.get("successor_candidate_identity"),
    )
    owner_triplet = tuple(
        predecessor.get(f"predecessor_target_owner_journal_{suffix}")
        for suffix in ("path", "identity", "sha256")
    )
    planned_fields = tuple(
        successor.get(f"planned_journal_successor_{suffix}")
        for suffix in ("path", "parent_identity", "phase", "size", "sha256")
    )
    if (
        type(current_action_index) is not int
        or next_action_index != current_action_index + 1
        or predecessor.get("cleanup_stage") is not None
        or predecessor.get("predecessor_transaction_temp_path") is not None
        or predecessor.get("deck_config_ini_sha256") is None
        or predecessor.get("runtime_state_sha256") is None
        or predecessor.get("last_apply_receipt_sha256") is None
        or predecessor.get("resolved_physical_disposition")
        not in {
            "COMMITTED_RECOVERY_PENDING",
            "UNKNOWN_REQUIRES_RECOVERY",
        }
        or any(value is not None for value in candidate_fields)
        or any(value is None for value in owner_triplet)
        or predecessor.get("allowed_attempt_record_successor_state")
        is not None
        or predecessor.get("allowed_journal_successor_phase")
        != "FINALIZED"
        or predecessor.get("planned_journal_successor_phase")
        != "FINALIZED"
        or predecessor.get("planned_journal_successor_path")
        != current_journal[0]
        or predecessor.get("planned_journal_successor_parent_identity")
        != current_external.get("parent_identity")
        or predecessor.get("planned_journal_successor_size")
        != current_external.get("planned_successor_size")
        or predecessor.get("planned_journal_successor_sha256")
        != current_external.get("planned_successor_sha256")
        or current_external.get("stage") != "STAGING_BOUND"
        or current_external.get("action_kind") != "finalize_journal"
        or current_external.get("action_index") != current_action_index
        or current_external.get("final_path") != current_journal[0]
        or current_external.get("predecessor_state") != "exact"
        or current_external.get("predecessor_identity")
        != current_journal[1]
        or current_external.get("predecessor_sha256")
        != current_journal[2]
        or current_external.get("staging_size")
        != current_external.get("planned_successor_size")
        or current_external.get("staging_sha256")
        != current_external.get("planned_successor_sha256")
        or successor.get("allowed_journal_successor_phase") is not None
        or successor.get("allowed_attempt_record_successor_state")
        != "FINALIZED"
        or any(value is not None for value in planned_fields)
        or next_journal[0] != current_journal[0]
        or next_journal[1] != current_external.get("staging_identity")
        or next_journal[2] != current_external.get("staging_sha256")
        or next_attempt != current_attempt
        or next_external.get("stage") != "PLANNED"
        or next_external.get("action_kind")
        != "materialize_file_action_staging"
        or next_external.get("action_index") != next_action_index
        or next_external.get("final_path") != current_attempt[0]
        or next_external.get("predecessor_state") != "exact"
        or next_external.get("predecessor_identity") != current_attempt[1]
        or next_external.get("predecessor_sha256") != current_attempt[2]
        or next_external.get("staging_identity") is not None
        or next_external.get("staging_size") is not None
        or next_external.get("staging_sha256") is not None
    ):
        raise SessionCapabilityError(
            "live_start_terminal_ownerless_finalize_journal_invalid"
        )
    mutable_fields = {
        "action_index",
        "allowed_attempt_record_successor_state",
        "allowed_journal_successor_phase",
        "successor_journal_path",
        "successor_journal_identity",
        "successor_journal_sha256",
        "planned_journal_successor_path",
        "planned_journal_successor_parent_identity",
        "planned_journal_successor_phase",
        "planned_journal_successor_size",
        "planned_journal_successor_sha256",
        "external_file_action",
        "content_sha256",
    }
    for field_name in _TERMINAL_RESOLUTION_FIELDS - mutable_fields:
        if predecessor.get(field_name) != successor.get(field_name):
            raise SessionCapabilityError(
                "live_start_terminal_ownerless_finalize_journal_history_changed"
            )


def _validate_terminal_ownerless_materialize_successor(
    *,
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    authorized_owner_action: str | None,
) -> None:
    current_external_raw = predecessor.get("external_file_action")
    next_external_raw = successor.get("external_file_action")
    if (
        authorized_owner_action
        not in {None, "retire_unbound_file_action_staging"}
        or not isinstance(current_external_raw, Mapping)
        or not isinstance(next_external_raw, Mapping)
    ):
        raise SessionCapabilityError(
            "live_start_terminal_ownerless_state_materialize_invalid"
        )
    current_external = validate_embedded_document(
        "external_file_action",
        current_external_raw,
    )
    next_external = validate_embedded_document(
        "external_file_action",
        next_external_raw,
    )
    current_journal = _terminal_resolution_effective_triplet(
        predecessor,
        authority="journal",
    )
    next_journal = _terminal_resolution_effective_triplet(
        successor,
        authority="journal",
    )
    current_attempt = _terminal_resolution_effective_triplet(
        predecessor,
        authority="attempt_record",
    )
    next_attempt = _terminal_resolution_effective_triplet(
        successor,
        authority="attempt_record",
    )
    current_action_index = predecessor.get("action_index")
    next_action_index = successor.get("action_index")
    retiring_unbound = (
        authorized_owner_action == "retire_unbound_file_action_staging"
    )
    state_path = Path(current_journal[0]).parent.parent / "state.json"
    metadata_root = Path(current_journal[0]).parent.parent
    candidate_fields = (
        predecessor.get("candidate_path"),
        predecessor.get("candidate_parent_identity"),
        predecessor.get("predecessor_candidate_identity"),
        predecessor.get("successor_candidate_identity"),
    )
    owner_triplet = tuple(
        predecessor.get(f"predecessor_target_owner_journal_{suffix}")
        for suffix in ("path", "identity", "sha256")
    )
    current_final_path = Path(str(current_external.get("final_path")))
    materialize_kind = (
        "state"
        if (
            current_final_path == state_path
            and predecessor.get("runtime_state_sha256") is None
        )
        else "journal"
        if (
            current_final_path == Path(current_journal[0])
            and predecessor.get("runtime_state_sha256") is not None
            and current_external.get("predecessor_state") == "exact"
            and current_external.get("predecessor_identity")
            == current_journal[1]
            and current_external.get("predecessor_sha256")
            == current_journal[2]
            and current_external.get("planned_successor_size")
            == predecessor.get("planned_journal_successor_size")
            and current_external.get("planned_successor_sha256")
            == predecessor.get("planned_journal_successor_sha256")
            and (
                (
                    predecessor.get("planned_journal_successor_phase")
                    == "STATE_COMMITTED"
                    and predecessor.get("last_apply_receipt_sha256") is None
                )
                or (
                    predecessor.get("planned_journal_successor_phase")
                    == "FINALIZED"
                    and predecessor.get("last_apply_receipt_sha256")
                    is not None
                )
            )
        )
        else "receipt"
        if (
            current_final_path.name == "last_apply_receipt.json"
            and current_final_path.parent.parent
            == metadata_root / "receipts"
            and bool(current_final_path.parent.name)
            and predecessor.get("runtime_state_sha256") is not None
            and predecessor.get("last_apply_receipt_sha256") is None
        )
        else "attempt"
        if (
            current_final_path == Path(current_attempt[0])
            and current_external.get("predecessor_state") == "exact"
            and current_external.get("predecessor_identity")
            == current_attempt[1]
            and current_external.get("predecessor_sha256")
            == current_attempt[2]
            and predecessor.get("runtime_state_sha256") is not None
            and predecessor.get("last_apply_receipt_sha256") is not None
            and predecessor.get("allowed_journal_successor_phase") is None
            and predecessor.get("allowed_attempt_record_successor_state")
            == "FINALIZED"
            and all(
                predecessor.get(field_name) is None
                for field_name in (
                    "planned_journal_successor_path",
                    "planned_journal_successor_parent_identity",
                    "planned_journal_successor_phase",
                    "planned_journal_successor_size",
                    "planned_journal_successor_sha256",
                )
            )
        )
        else None
    )
    expected_planned_journal_phase = {
        "state": "STATE_COMMITTED",
        "receipt": "FINALIZED",
    }.get(materialize_kind) or (
        predecessor.get("planned_journal_successor_phase")
        if materialize_kind == "journal"
        else None
    )
    if (
        type(current_action_index) is not int
        or next_action_index != current_action_index + 1
        or predecessor.get("cleanup_stage") is not None
        or predecessor.get("predecessor_transaction_temp_path") is not None
        or predecessor.get("deck_config_ini_sha256") is None
        or predecessor.get("resolved_physical_disposition")
        not in {
            "COMMITTED_RECOVERY_PENDING",
            "UNKNOWN_REQUIRES_RECOVERY",
        }
        or any(value is not None for value in candidate_fields)
        or any(value is None for value in owner_triplet)
        or predecessor.get("allowed_journal_successor_phase")
        != expected_planned_journal_phase
        or predecessor.get("planned_journal_successor_phase")
        != expected_planned_journal_phase
        or (
            materialize_kind != "attempt"
            and predecessor.get("planned_journal_successor_path")
            != current_journal[0]
        )
        or (
            materialize_kind == "attempt"
            and predecessor.get("allowed_attempt_record_successor_state")
            != "FINALIZED"
        )
        or current_external.get("stage") != "PLANNED"
        or current_external.get("action_kind")
        != "materialize_file_action_staging"
        or current_external.get("action_index") != current_action_index
        or materialize_kind is None
        or current_external.get("staging_identity") is not None
        or current_external.get("staging_size") is not None
        or current_external.get("staging_sha256") is not None
        or next_journal != current_journal
        or next_attempt != current_attempt
        or next_external.get("action_index") != next_action_index
    ):
        raise SessionCapabilityError(
            "live_start_terminal_ownerless_materialize_invalid"
        )
    mutable_external_fields = (
        {"action_index", "content_sha256"}
        if retiring_unbound
        else {
            "action_index",
            "action_kind",
            "stage",
            "staging_identity",
            "staging_size",
            "staging_sha256",
            "content_sha256",
        }
    )
    transition_invalid = (
        (
            next_external.get("stage") != "PLANNED"
            or next_external.get("action_kind")
            != "materialize_file_action_staging"
            or next_external.get("staging_identity") is not None
            or next_external.get("staging_size") is not None
            or next_external.get("staging_sha256") is not None
        )
        if retiring_unbound
        else (
            next_external.get("stage") != "STAGING_BOUND"
            or next_external.get("action_kind")
            != (
                "write_runtime_state"
                if materialize_kind == "state"
                else (
                    "write_last_apply_receipt"
                    if materialize_kind == "receipt"
                    else (
                        "finalize_attempt_record"
                        if materialize_kind == "attempt"
                        else (
                            "finalize_journal"
                            if expected_planned_journal_phase == "FINALIZED"
                            else "commit_state_journal"
                        )
                    )
                )
            )
            or next_external.get("staging_size")
            != current_external.get("planned_successor_size")
            or next_external.get("staging_sha256")
            != current_external.get("planned_successor_sha256")
        )
    )
    if transition_invalid or any(
        current_external.get(field_name)
        != next_external.get(field_name)
        for field_name in (
            _EXTERNAL_FILE_ACTION_FIELDS - mutable_external_fields
        )
    ):
        raise SessionCapabilityError(
            "live_start_terminal_ownerless_materialize_invalid"
        )
    mutable_resolution_fields = {
        "action_index",
        "external_file_action",
        "content_sha256",
    }
    for field_name in (
        _TERMINAL_RESOLUTION_FIELDS - mutable_resolution_fields
    ):
        if predecessor.get(field_name) != successor.get(field_name):
            raise SessionCapabilityError(
                "live_start_terminal_ownerless_materialize_history_changed"
            )


def _validate_terminal_ownerless_state_write_successor(
    *,
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    authorized_owner_action: str | None,
) -> None:
    current_external_raw = predecessor.get("external_file_action")
    next_external_raw = successor.get("external_file_action")
    if (
        authorized_owner_action is not None
        or not isinstance(current_external_raw, Mapping)
        or not isinstance(next_external_raw, Mapping)
    ):
        raise SessionCapabilityError(
            "live_start_terminal_ownerless_state_write_invalid"
        )
    current_external = validate_embedded_document(
        "external_file_action",
        current_external_raw,
    )
    next_external = validate_embedded_document(
        "external_file_action",
        next_external_raw,
    )
    current_journal = _terminal_resolution_effective_triplet(
        predecessor,
        authority="journal",
    )
    next_journal = _terminal_resolution_effective_triplet(
        successor,
        authority="journal",
    )
    current_action_index = predecessor.get("action_index")
    next_action_index = successor.get("action_index")
    journal_path = Path(current_journal[0])
    state_path = journal_path.parent.parent / "state.json"
    candidate_fields = (
        predecessor.get("candidate_path"),
        predecessor.get("candidate_parent_identity"),
        predecessor.get("predecessor_candidate_identity"),
        predecessor.get("successor_candidate_identity"),
    )
    owner_triplet = tuple(
        predecessor.get(f"predecessor_target_owner_journal_{suffix}")
        for suffix in ("path", "identity", "sha256")
    )
    if (
        type(current_action_index) is not int
        or next_action_index != current_action_index + 1
        or predecessor.get("cleanup_stage") is not None
        or predecessor.get("predecessor_transaction_temp_path") is not None
        or predecessor.get("deck_config_ini_sha256") is None
        or predecessor.get("runtime_state_sha256") is not None
        or predecessor.get("resolved_physical_disposition")
        not in {
            "COMMITTED_RECOVERY_PENDING",
            "UNKNOWN_REQUIRES_RECOVERY",
        }
        or any(value is not None for value in candidate_fields)
        or any(value is None for value in owner_triplet)
        or predecessor.get("allowed_journal_successor_phase")
        != "STATE_COMMITTED"
        or predecessor.get("planned_journal_successor_phase")
        != "STATE_COMMITTED"
        or predecessor.get("planned_journal_successor_path")
        != current_journal[0]
        or current_external.get("stage") != "STAGING_BOUND"
        or current_external.get("action_kind") != "write_runtime_state"
        or current_external.get("action_index") != current_action_index
        or Path(str(current_external.get("final_path"))) != state_path
        or current_external.get("staging_size")
        != current_external.get("planned_successor_size")
        or current_external.get("staging_sha256")
        != current_external.get("planned_successor_sha256")
        or next_journal != current_journal
        or successor.get("runtime_state_sha256")
        != current_external.get("planned_successor_sha256")
        or next_external.get("stage") != "PLANNED"
        or next_external.get("action_kind")
        != "materialize_file_action_staging"
        or next_external.get("action_index") != next_action_index
        or Path(str(next_external.get("final_path"))) != journal_path
        or next_external.get("predecessor_state") != "exact"
        or next_external.get("predecessor_identity")
        != current_journal[1]
        or next_external.get("predecessor_sha256")
        != current_journal[2]
        or next_external.get("planned_successor_size")
        != successor.get("planned_journal_successor_size")
        or next_external.get("planned_successor_sha256")
        != successor.get("planned_journal_successor_sha256")
        or next_external.get("staging_identity") is not None
        or next_external.get("staging_size") is not None
        or next_external.get("staging_sha256") is not None
    ):
        raise SessionCapabilityError(
            "live_start_terminal_ownerless_state_write_invalid"
        )
    mutable_resolution_fields = {
        "action_index",
        "runtime_state_sha256",
        "external_file_action",
        "content_sha256",
    }
    for field_name in (
        _TERMINAL_RESOLUTION_FIELDS - mutable_resolution_fields
    ):
        if predecessor.get(field_name) != successor.get(field_name):
            raise SessionCapabilityError(
                "live_start_terminal_ownerless_state_write_history_changed"
            )


def _validate_terminal_ownerless_receipt_write_successor(
    *,
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    authorized_owner_action: str | None,
) -> None:
    current_external_raw = predecessor.get("external_file_action")
    next_external_raw = successor.get("external_file_action")
    if (
        authorized_owner_action is not None
        or not isinstance(current_external_raw, Mapping)
        or not isinstance(next_external_raw, Mapping)
    ):
        raise SessionCapabilityError(
            "live_start_terminal_ownerless_receipt_write_invalid"
        )
    current_external = validate_embedded_document(
        "external_file_action",
        current_external_raw,
    )
    next_external = validate_embedded_document(
        "external_file_action",
        next_external_raw,
    )
    current_journal = _terminal_resolution_effective_triplet(
        predecessor,
        authority="journal",
    )
    next_journal = _terminal_resolution_effective_triplet(
        successor,
        authority="journal",
    )
    current_action_index = predecessor.get("action_index")
    next_action_index = successor.get("action_index")
    journal_path = Path(current_journal[0])
    metadata_root = journal_path.parent.parent
    receipt_path = Path(str(current_external.get("final_path")))
    candidate_fields = (
        predecessor.get("candidate_path"),
        predecessor.get("candidate_parent_identity"),
        predecessor.get("predecessor_candidate_identity"),
        predecessor.get("successor_candidate_identity"),
    )
    owner_triplet = tuple(
        predecessor.get(f"predecessor_target_owner_journal_{suffix}")
        for suffix in ("path", "identity", "sha256")
    )
    if (
        type(current_action_index) is not int
        or next_action_index != current_action_index + 1
        or predecessor.get("cleanup_stage") is not None
        or predecessor.get("predecessor_transaction_temp_path") is not None
        or predecessor.get("deck_config_ini_sha256") is None
        or predecessor.get("runtime_state_sha256") is None
        or predecessor.get("last_apply_receipt_sha256") is not None
        or predecessor.get("resolved_physical_disposition")
        not in {
            "COMMITTED_RECOVERY_PENDING",
            "UNKNOWN_REQUIRES_RECOVERY",
        }
        or any(value is not None for value in candidate_fields)
        or any(value is None for value in owner_triplet)
        or predecessor.get("allowed_journal_successor_phase")
        != "FINALIZED"
        or predecessor.get("planned_journal_successor_phase")
        != "FINALIZED"
        or predecessor.get("planned_journal_successor_path")
        != current_journal[0]
        or current_external.get("stage") != "STAGING_BOUND"
        or current_external.get("action_kind")
        != "write_last_apply_receipt"
        or current_external.get("action_index") != current_action_index
        or receipt_path.name != "last_apply_receipt.json"
        or receipt_path.parent.parent != metadata_root / "receipts"
        or not receipt_path.parent.name
        or current_external.get("staging_size")
        != current_external.get("planned_successor_size")
        or current_external.get("staging_sha256")
        != current_external.get("planned_successor_sha256")
        or next_journal != current_journal
        or successor.get("last_apply_receipt_sha256")
        != current_external.get("planned_successor_sha256")
        or next_external.get("stage") != "PLANNED"
        or next_external.get("action_kind")
        != "materialize_file_action_staging"
        or next_external.get("action_index") != next_action_index
        or Path(str(next_external.get("final_path"))) != journal_path
        or next_external.get("parent_identity")
        != predecessor.get("planned_journal_successor_parent_identity")
        or next_external.get("predecessor_state") != "exact"
        or next_external.get("predecessor_identity")
        != current_journal[1]
        or next_external.get("predecessor_sha256")
        != current_journal[2]
        or next_external.get("planned_successor_size")
        != successor.get("planned_journal_successor_size")
        or next_external.get("planned_successor_sha256")
        != successor.get("planned_journal_successor_sha256")
        or next_external.get("staging_identity") is not None
        or next_external.get("staging_size") is not None
        or next_external.get("staging_sha256") is not None
    ):
        raise SessionCapabilityError(
            "live_start_terminal_ownerless_receipt_write_invalid"
        )
    mutable_resolution_fields = {
        "action_index",
        "last_apply_receipt_sha256",
        "external_file_action",
        "content_sha256",
    }
    for field_name in (
        _TERMINAL_RESOLUTION_FIELDS - mutable_resolution_fields
    ):
        if predecessor.get(field_name) != successor.get(field_name):
            raise SessionCapabilityError(
                "live_start_terminal_ownerless_receipt_write_history_changed"
            )


def _validate_terminal_ownerless_finalize_attempt_successor(
    *,
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    authorized_owner_action: str | None,
) -> None:
    current_external_raw = predecessor.get("external_file_action")
    if (
        authorized_owner_action is not None
        or not isinstance(current_external_raw, Mapping)
        or successor.get("external_file_action") is not None
    ):
        raise SessionCapabilityError(
            "live_start_terminal_ownerless_finalize_attempt_invalid"
        )
    current_external = validate_embedded_document(
        "external_file_action",
        current_external_raw,
    )
    current_journal = _terminal_resolution_effective_triplet(
        predecessor,
        authority="journal",
    )
    next_journal = _terminal_resolution_effective_triplet(
        successor,
        authority="journal",
    )
    current_attempt = _terminal_resolution_effective_triplet(
        predecessor,
        authority="attempt_record",
    )
    next_attempt = _terminal_resolution_effective_triplet(
        successor,
        authority="attempt_record",
    )
    current_action_index = predecessor.get("action_index")
    next_action_index = successor.get("action_index")
    candidate_fields = (
        predecessor.get("candidate_path"),
        predecessor.get("candidate_parent_identity"),
        predecessor.get("predecessor_candidate_identity"),
        predecessor.get("successor_candidate_identity"),
    )
    owner_triplet = tuple(
        predecessor.get(f"predecessor_target_owner_journal_{suffix}")
        for suffix in ("path", "identity", "sha256")
    )
    current_planned_journal = tuple(
        predecessor.get(field_name)
        for field_name in (
            "planned_journal_successor_path",
            "planned_journal_successor_parent_identity",
            "planned_journal_successor_phase",
            "planned_journal_successor_size",
            "planned_journal_successor_sha256",
        )
    )
    next_planned_journal = tuple(
        successor.get(field_name)
        for field_name in (
            "planned_journal_successor_path",
            "planned_journal_successor_parent_identity",
            "planned_journal_successor_phase",
            "planned_journal_successor_size",
            "planned_journal_successor_sha256",
        )
    )
    staging_identity = current_external.get("staging_identity")
    expected_next_attempt = (
        current_attempt[0],
        (
            tuple(staging_identity)
            if isinstance(staging_identity, (list, tuple))
            else None
        ),
        current_external.get("staging_sha256"),
    )
    if (
        type(current_action_index) is not int
        or next_action_index != current_action_index + 1
        or predecessor.get("cleanup_stage") is not None
        or predecessor.get("predecessor_transaction_temp_path") is not None
        or predecessor.get("deck_config_ini_sha256") is None
        or predecessor.get("runtime_state_sha256") is None
        or predecessor.get("last_apply_receipt_sha256") is None
        or predecessor.get("resolved_physical_disposition")
        not in {
            "COMMITTED_RECOVERY_PENDING",
            "UNKNOWN_REQUIRES_RECOVERY",
        }
        or any(value is not None for value in candidate_fields)
        or any(value is None for value in owner_triplet)
        or predecessor.get("owner_retirement") is not None
        or successor.get("owner_retirement") is not None
        or predecessor.get("allowed_journal_successor_phase") is not None
        or predecessor.get("allowed_attempt_record_successor_state")
        != "FINALIZED"
        or successor.get("allowed_journal_successor_phase") is not None
        or successor.get("allowed_attempt_record_successor_state") is not None
        or any(value is not None for value in current_planned_journal)
        or any(value is not None for value in next_planned_journal)
        or current_external.get("stage") != "STAGING_BOUND"
        or current_external.get("action_kind")
        != "finalize_attempt_record"
        or current_external.get("action_index") != current_action_index
        or current_external.get("final_path") != current_attempt[0]
        or current_external.get("predecessor_state") != "exact"
        or current_external.get("predecessor_identity") != current_attempt[1]
        or current_external.get("predecessor_sha256") != current_attempt[2]
        or current_external.get("staging_size")
        != current_external.get("planned_successor_size")
        or current_external.get("staging_sha256")
        != current_external.get("planned_successor_sha256")
        or next_journal != current_journal
        or next_attempt != expected_next_attempt
    ):
        raise SessionCapabilityError(
            "live_start_terminal_ownerless_finalize_attempt_invalid"
        )
    mutable_resolution_fields = {
        "action_index",
        "allowed_attempt_record_successor_state",
        "successor_attempt_record_path",
        "successor_attempt_record_identity",
        "successor_attempt_record_sha256",
        "external_file_action",
        "content_sha256",
    }
    for field_name in (
        _TERMINAL_RESOLUTION_FIELDS - mutable_resolution_fields
    ):
        if predecessor.get(field_name) != successor.get(field_name):
            raise SessionCapabilityError(
                "live_start_terminal_ownerless_finalize_attempt_history_changed"
            )


def _validate_terminal_ownerless_classification_successor(
    *,
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    authorized_owner_action: str | None,
) -> None:
    current_disposition = predecessor.get("resolved_physical_disposition")
    next_disposition = successor.get("resolved_physical_disposition")
    if (
        authorized_owner_action is not None
        or predecessor.get("owner_retirement") is not None
        or successor.get("owner_retirement") is not None
        or predecessor.get("external_file_action") is not None
        or successor.get("external_file_action") is not None
        or predecessor.get("cleanup_stage") is not None
        or successor.get("cleanup_stage") is not None
        or predecessor.get("predecessor_transaction_temp_path") is not None
        or successor.get("predecessor_transaction_temp_path") is not None
        or current_disposition
        not in {
            "COMMITTED_RECOVERY_PENDING",
            "UNKNOWN_REQUIRES_RECOVERY",
        }
        or next_disposition
        not in {
            "NOT_COMMITTED",
            "COMMITTED_RECOVERY_PENDING",
            "UNKNOWN_REQUIRES_RECOVERY",
        }
        or next_disposition == current_disposition
    ):
        raise SessionCapabilityError(
            "live_start_terminal_ownerless_classification_invalid"
        )
    mutable_fields = {
        "action_index",
        "resolved_physical_disposition",
        "content_sha256",
    }
    for field_name in _TERMINAL_RESOLUTION_FIELDS - mutable_fields:
        if predecessor.get(field_name) != successor.get(field_name):
            raise SessionCapabilityError(
                "live_start_terminal_ownerless_classification_history_changed"
            )


def _validate_terminal_ownerless_observe_committed_successor(
    *,
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    authorized_owner_action: str | None,
) -> None:
    current_successor_attempt = tuple(
        predecessor.get(f"successor_attempt_record_{suffix}")
        for suffix in ("path", "identity", "sha256")
    )
    current_successor_journal = tuple(
        predecessor.get(f"successor_journal_{suffix}")
        for suffix in ("path", "identity", "sha256")
    )
    current_owner = tuple(
        predecessor.get(f"predecessor_target_owner_journal_{suffix}")
        for suffix in ("path", "identity", "sha256")
    )
    current_candidate = tuple(
        predecessor.get(field_name)
        for field_name in (
            "candidate_path",
            "candidate_parent_identity",
            "predecessor_candidate_identity",
            "successor_candidate_identity",
        )
    )
    next_candidate = tuple(
        successor.get(field_name)
        for field_name in (
            "candidate_path",
            "candidate_parent_identity",
            "predecessor_candidate_identity",
            "successor_candidate_identity",
        )
    )
    current_planned = tuple(
        predecessor.get(field_name)
        for field_name in (
            "planned_journal_successor_path",
            "planned_journal_successor_parent_identity",
            "planned_journal_successor_phase",
            "planned_journal_successor_size",
            "planned_journal_successor_sha256",
        )
    )
    next_planned = tuple(
        successor.get(field_name)
        for field_name in (
            "planned_journal_successor_path",
            "planned_journal_successor_parent_identity",
            "planned_journal_successor_phase",
            "planned_journal_successor_size",
            "planned_journal_successor_sha256",
        )
    )
    current_action_index = predecessor.get("action_index")
    if (
        authorized_owner_action is not None
        or type(current_action_index) is not int
        or successor.get("action_index") != current_action_index + 1
        or predecessor.get("owner_retirement") is not None
        or successor.get("owner_retirement") is not None
        or predecessor.get("external_file_action") is not None
        or successor.get("external_file_action") is not None
        or predecessor.get("cleanup_stage") is not None
        or successor.get("cleanup_stage") is not None
        or predecessor.get("predecessor_transaction_temp_path") is not None
        or predecessor.get("resolved_physical_disposition")
        not in {
            "COMMITTED_RECOVERY_PENDING",
            "UNKNOWN_REQUIRES_RECOVERY",
        }
        or successor.get("resolved_physical_disposition") != "COMMITTED"
        or predecessor.get("allowed_journal_successor_phase") is not None
        or successor.get("allowed_journal_successor_phase") is not None
        or predecessor.get("allowed_attempt_record_successor_state") is not None
        or successor.get("allowed_attempt_record_successor_state") is not None
        or any(value is not None for value in current_planned)
        or any(value is not None for value in next_planned)
        or any(value is None for value in current_successor_attempt)
        or any(value is None for value in current_successor_journal)
        or any(value is None for value in current_owner)
        or any(value is not None for value in current_candidate)
        or any(value is not None for value in next_candidate)
        or predecessor.get("deck_config_ini_sha256") is None
        or predecessor.get("runtime_state_sha256") is None
        or predecessor.get("last_apply_receipt_sha256") is None
        or predecessor.get("runtime_match_status")
        not in {"not_run", "unknown"}
        or predecessor.get("runtime_match_sha256") is not None
        or successor.get("runtime_match_status") != "unknown"
        or successor.get("runtime_match_sha256") is not None
    ):
        raise SessionCapabilityError(
            "live_start_terminal_ownerless_observe_committed_invalid"
        )
    mutable_resolution_fields = {
        "action_index",
        "resolved_physical_disposition",
        "runtime_match_status",
        "runtime_match_sha256",
        "content_sha256",
    }
    for field_name in (
        _TERMINAL_RESOLUTION_FIELDS - mutable_resolution_fields
    ):
        if predecessor.get(field_name) != successor.get(field_name):
            raise SessionCapabilityError(
                "live_start_terminal_ownerless_observe_committed_history_changed"
            )


def _validate_terminal_owner_successor(
    *,
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    authorized_owner_action: str | None = None,
) -> str | None:
    current_owner_raw = predecessor.get("owner_retirement")
    next_owner_raw = successor.get("owner_retirement")
    if current_owner_raw is None and next_owner_raw is None:
        current_action_index = predecessor.get("action_index")
        if (
            type(current_action_index) is not int
            or successor.get("action_index") != current_action_index + 1
        ):
            raise SessionCapabilityError(
                "live_start_terminal_owner_action_index_invalid"
            )
        current_external = predecessor.get("external_file_action")
        if (
            current_external is None
            and successor.get("external_file_action") is None
        ):
            if (
                successor.get("resolved_physical_disposition")
                == "COMMITTED"
            ):
                _validate_terminal_ownerless_observe_committed_successor(
                    predecessor=predecessor,
                    successor=successor,
                    authorized_owner_action=authorized_owner_action,
                )
            else:
                _validate_terminal_ownerless_classification_successor(
                    predecessor=predecessor,
                    successor=successor,
                    authorized_owner_action=authorized_owner_action,
                )
        elif (
            isinstance(current_external, Mapping)
            and current_external.get("stage") == "PLANNED"
            and current_external.get("action_kind")
            == "materialize_file_action_staging"
        ):
            _validate_terminal_ownerless_materialize_successor(
                predecessor=predecessor,
                successor=successor,
                authorized_owner_action=authorized_owner_action,
            )
        elif (
            isinstance(current_external, Mapping)
            and current_external.get("stage") == "STAGING_BOUND"
            and current_external.get("action_kind")
            == "finalize_attempt_record"
        ):
            _validate_terminal_ownerless_finalize_attempt_successor(
                predecessor=predecessor,
                successor=successor,
                authorized_owner_action=authorized_owner_action,
            )
        elif (
            isinstance(current_external, Mapping)
            and current_external.get("stage") == "STAGING_BOUND"
            and current_external.get("action_kind")
            == "finalize_journal"
        ):
            _validate_terminal_ownerless_finalize_journal_successor(
                predecessor=predecessor,
                successor=successor,
                authorized_owner_action=authorized_owner_action,
            )
        elif (
            isinstance(current_external, Mapping)
            and current_external.get("stage") == "STAGING_BOUND"
            and current_external.get("action_kind")
            == "commit_state_journal"
        ):
            _validate_terminal_ownerless_commit_state_successor(
                predecessor=predecessor,
                successor=successor,
                authorized_owner_action=authorized_owner_action,
            )
        elif (
            isinstance(current_external, Mapping)
            and current_external.get("stage") == "STAGING_BOUND"
            and current_external.get("action_kind")
            == "write_last_apply_receipt"
        ):
            _validate_terminal_ownerless_receipt_write_successor(
                predecessor=predecessor,
                successor=successor,
                authorized_owner_action=authorized_owner_action,
            )
        elif (
            isinstance(current_external, Mapping)
            and current_external.get("stage") == "STAGING_BOUND"
            and current_external.get("action_kind")
            == "write_runtime_state"
        ):
            _validate_terminal_ownerless_state_write_successor(
                predecessor=predecessor,
                successor=successor,
                authorized_owner_action=authorized_owner_action,
            )
        else:
            _validate_terminal_ownerless_commit_ini_successor(
                predecessor=predecessor,
                successor=successor,
                authorized_owner_action=authorized_owner_action,
            )
        return authorized_owner_action
    if not isinstance(current_owner_raw, Mapping) or not isinstance(
        next_owner_raw,
        Mapping,
    ):
        raise SessionCapabilityError(
            "live_start_terminal_owner_cursor_changed"
        )
    current_owner = _validate_owner_retirement_document(
        current_owner_raw
    )
    next_owner = _validate_owner_retirement_document(next_owner_raw)
    current_external_raw = predecessor.get("external_file_action")
    next_external_raw = successor.get("external_file_action")
    current_external = (
        validate_embedded_document(
            "external_file_action",
            current_external_raw,
        )
        if isinstance(current_external_raw, Mapping)
        else None
    )
    nominal_action = _owner_action_for_cursor(
        owner=current_owner,
        external=current_external,
    )
    current_cursor = {
        "owner_retirement": current_owner,
        "external_file_action": current_external,
        "action_index": predecessor.get("action_index"),
        "expected_action": nominal_action,
    }
    action = nominal_action
    if authorized_owner_action is not None:
        alternate = (
            nominal_action == "materialize_file_action_staging"
            and _is_unbound_file_action_retirement_alternate(
                recovery=current_cursor,
                action=authorized_owner_action,
            )
        )
        if authorized_owner_action != nominal_action and not alternate:
            raise SessionCapabilityError(
                "live_start_terminal_owner_action_changed"
            )
        action = authorized_owner_action
    successor_action = (
        "materialize_file_action_staging"
        if action == "retire_unbound_file_action_staging"
        else _owner_successor_action(
            action=action,
            current_external=current_external,
            successor_owner=next_owner,
        )
    )
    successor_cursor = {
        "owner_retirement": next_owner,
        "external_file_action": next_external_raw,
        "action_index": successor.get("action_index"),
        "expected_action": successor_action,
    }
    _validate_owner_retirement_successor(
        predecessor=current_cursor,
        successor=successor_cursor,
        action=action,
    )
    current_disposition = predecessor.get(
        "resolved_physical_disposition"
    )
    next_disposition = successor.get("resolved_physical_disposition")
    if action == "observe_owner_retirement_completed":
        if (
            current_disposition
            not in {
                "COMMITTED_RECOVERY_PENDING",
                "UNKNOWN_REQUIRES_RECOVERY",
            }
            or next_disposition != "COMMITTED"
        ):
            raise SessionCapabilityError(
                "live_start_terminal_owner_disposition_invalid"
            )
    elif current_disposition != next_disposition:
        raise SessionCapabilityError(
            "live_start_terminal_owner_disposition_changed"
        )
    mutable_resolution_fields = {
        "action_index",
        "owner_retirement",
        "external_file_action",
        "content_sha256",
    }
    if action == "observe_owner_retirement_completed":
        mutable_resolution_fields.add(
            "resolved_physical_disposition"
        )
    for field_name in (
        _TERMINAL_RESOLUTION_FIELDS - mutable_resolution_fields
    ):
        if predecessor.get(field_name) != successor.get(field_name):
            raise SessionCapabilityError(
                "live_start_terminal_owner_history_changed"
            )
    if isinstance(next_external_raw, Mapping):
        try:
            _validate_owner_external_physical(next_external_raw)
        except (SessionConflictError, SessionValidationError) as error:
            raise SessionCapabilityError(
                "live_start_terminal_owner_physical_changed"
            ) from error
    return action


def _validate_terminal_resolution_successor(
    *,
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    transition: str,
    authorized_owner_action: str | None = None,
    ownerless_issuer_context: Mapping[str, Any] | None = None,
) -> str | None:
    current = validate_embedded_document(
        "terminal_retirement", predecessor
    )
    next_value = validate_embedded_document(
        "terminal_retirement", successor
    )
    if (
        current.get("operation") != "release_resolved_terminal"
        or next_value.get("operation") != "release_resolved_terminal"
        or transition not in _TERMINAL_RESOLUTION_OUTER_EDGES
        or (current["stage"], next_value["stage"])
        not in _TERMINAL_RESOLUTION_OUTER_EDGES[transition]
    ):
        raise SessionCapabilityError(
            "live_start_terminal_resolution_successor_invalid"
        )
    for field_name in _TERMINAL_RETIREMENT_FIELDS - {
        "stage",
        "terminal_resolution_evidence",
        "content_sha256",
    }:
        if current.get(field_name) != next_value.get(field_name):
            raise SessionCapabilityError(
                "live_start_terminal_resolution_successor_changed"
            )
    current_resolution = _validate_terminal_resolution_document(
        current["terminal_resolution_evidence"]
    )
    next_resolution = _validate_terminal_resolution_document(
        next_value["terminal_resolution_evidence"]
    )
    changed = {
        field_name
        for field_name in _TERMINAL_RESOLUTION_FIELDS - {"content_sha256"}
        if current_resolution.get(field_name)
        != next_resolution.get(field_name)
    }
    outer_only_metadata = (
        transition in {"journal_retired", "fence_retired"}
        and current_resolution.get("cleanup_stage") is None
        and next_resolution.get("cleanup_stage") is None
        and current_resolution == next_resolution
    )
    current_owner = current_resolution.get("owner_retirement")
    owner_stabilized_outer_only = (
        transition == "stabilized"
        and current_resolution == next_resolution
        and isinstance(current_owner, Mapping)
        and current_owner.get("stage") == "OWNER_RETIRED"
        and current_resolution.get("external_file_action") is None
        and current_resolution.get("cleanup_stage") is None
        and current_resolution.get("resolved_physical_disposition")
        == "COMMITTED"
    )
    evidence_free_stabilized_outer_only = (
        transition == "stabilized"
        and current_resolution == next_resolution
        and current_owner is None
        and current_resolution.get("external_file_action") is None
        and current_resolution.get("cleanup_stage") is None
        and current_resolution.get("resolved_physical_disposition")
        in {"NOT_COMMITTED", "COMMITTED"}
    )
    if (
        not (
            outer_only_metadata
            or owner_stabilized_outer_only
            or evidence_free_stabilized_outer_only
        )
        and (
            not changed
            or not changed
            <= _TERMINAL_RESOLUTION_MUTABLE_FIELDS[transition]
        )
    ):
        raise SessionCapabilityError(
            "live_start_terminal_resolution_successor_changed"
        )
    owner_action: str | None = None
    if transition == "physical_recovery_advanced":
        current_external = current_resolution.get("external_file_action")
        if current_owner is None:
            if (
                not isinstance(ownerless_issuer_context, Mapping)
                or set(ownerless_issuer_context)
                != {
                    "apply_attempt_id",
                    "action_index",
                    "predecessor_resolution_sha256",
                    "predecessor_external_sha256",
                    "successor_retirement_sha256",
                    "successor_resolution_sha256",
                }
                or ownerless_issuer_context.get("apply_attempt_id")
                != current_resolution.get("apply_attempt_id")
                or ownerless_issuer_context.get("action_index")
                != current_resolution.get("action_index")
                or ownerless_issuer_context.get(
                    "predecessor_resolution_sha256"
                )
                != current_resolution.get("content_sha256")
                or ownerless_issuer_context.get(
                    "predecessor_external_sha256"
                )
                != (
                    current_external.get("content_sha256")
                    if isinstance(current_external, Mapping)
                    else None
                )
                or ownerless_issuer_context.get(
                    "successor_retirement_sha256"
                )
                != next_value.get("content_sha256")
                or ownerless_issuer_context.get(
                    "successor_resolution_sha256"
                )
                != next_resolution.get("content_sha256")
            ):
                raise SessionCapabilityError(
                    "live_start_terminal_ownerless_issuer_invalid"
                )
        elif ownerless_issuer_context is not None:
            raise SessionCapabilityError(
                "live_start_terminal_ownerless_issuer_unexpected"
            )
        owner_action = _validate_terminal_owner_successor(
            predecessor=current_resolution,
            successor=next_resolution,
            authorized_owner_action=authorized_owner_action,
        )
    if transition == "cleanup_inventory_unbound_staging_retired":
        _validate_terminal_external_action_successor(
            predecessor=current_resolution.get("external_file_action"),
            successor=next_resolution.get("external_file_action"),
            transition="unbound_retired",
        )
    elif transition == "cleanup_inventory_staging_bound":
        _validate_terminal_external_action_successor(
            predecessor=current_resolution.get("external_file_action"),
            successor=next_resolution.get("external_file_action"),
            transition="staging_bound",
        )
    elif transition == "inventory_bound":
        current_external = current_resolution.get("external_file_action")
        if (
            current_resolution.get("cleanup_stage") != "PREPARED"
            or next_resolution.get("cleanup_stage") != "INVENTORY_BOUND"
            or not isinstance(current_external, Mapping)
            or next_resolution.get("external_file_action") is not None
            or current_resolution.get("cleanup_inventory_identity") is not None
            or next_resolution.get("cleanup_inventory_identity")
            != current_external.get("staging_identity")
            or next_resolution.get("cleanup_inventory_size")
            != current_external.get("staging_size")
            or next_resolution.get("cleanup_inventory_sha256")
            != current_external.get("staging_sha256")
        ):
            raise SessionCapabilityError(
                "live_start_terminal_resolution_successor_invalid"
            )
    elif transition == "cleaning_started":
        _require_terminal_cleanup_stage_edge(
            current_resolution,
            next_resolution,
            source="INVENTORY_BOUND",
            target="CLEANING",
        )
    elif transition == "cleanup_cursor_advanced":
        if (
            current_resolution.get("cleanup_stage") != "CLEANING"
            or next_resolution.get("cleanup_stage") != "CLEANING"
            or next_resolution.get("cleanup_cursor")
            != current_resolution.get("cleanup_cursor") + 1
        ):
            raise SessionCapabilityError(
                "live_start_terminal_resolution_successor_invalid"
            )
    elif transition == "journal_retired":
        current_cleanup = current_resolution.get("cleanup_stage")
        next_cleanup = next_resolution.get("cleanup_stage")
        if (current_cleanup, next_cleanup) not in {
            (None, None),
            ("CLEANING", "JOURNAL_RETIRED"),
        }:
            raise SessionCapabilityError(
                "live_start_terminal_resolution_successor_invalid"
            )
    elif transition == "fence_retired":
        current_cleanup = current_resolution.get("cleanup_stage")
        next_cleanup = next_resolution.get("cleanup_stage")
        if (current_cleanup, next_cleanup) not in {
            (None, None),
            ("JOURNAL_RETIRED", "FENCE_RETIRED"),
        }:
            raise SessionCapabilityError(
                "live_start_terminal_resolution_successor_invalid"
            )
    elif transition == "inventory_retired":
        _require_terminal_cleanup_stage_edge(
            current_resolution,
            next_resolution,
            source="FENCE_RETIRED",
            target="INVENTORY_RETIRED",
        )
    elif transition == "stabilized" and (
        next_resolution.get("cleanup_stage")
        not in {None, "COMPLETE"}
    ):
        raise SessionCapabilityError(
            "live_start_terminal_resolution_successor_invalid"
        )
    return owner_action


def _validate_terminal_external_action_successor(
    *,
    predecessor: Any,
    successor: Any,
    transition: str,
) -> None:
    if not isinstance(predecessor, Mapping) or not isinstance(
        successor, Mapping
    ):
        raise SessionCapabilityError(
            "live_start_terminal_resolution_file_action_invalid"
        )
    current = validate_embedded_document(
        "external_file_action", predecessor
    )
    next_value = validate_embedded_document(
        "external_file_action", successor
    )
    if transition == "unbound_retired":
        mutable = {"action_index", "content_sha256"}
        if (
            current["stage"] != "PLANNED"
            or next_value["stage"] != "PLANNED"
            or next_value["action_index"] != current["action_index"] + 1
        ):
            raise SessionCapabilityError(
                "live_start_terminal_resolution_file_action_invalid"
            )
    else:
        mutable = {
            "stage",
            "staging_identity",
            "staging_size",
            "staging_sha256",
            "content_sha256",
        }
        if (
            current["stage"] != "PLANNED"
            or next_value["stage"] != "STAGING_BOUND"
        ):
            raise SessionCapabilityError(
                "live_start_terminal_resolution_file_action_invalid"
            )
    for field_name in _EXTERNAL_FILE_ACTION_FIELDS - mutable:
        if current.get(field_name) != next_value.get(field_name):
            raise SessionCapabilityError(
                "live_start_terminal_resolution_file_action_changed"
            )


def _require_terminal_cleanup_stage_edge(
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
    *,
    source: str,
    target: str,
) -> None:
    if (
        predecessor.get("cleanup_stage") != source
        or successor.get("cleanup_stage") != target
    ):
        raise SessionCapabilityError(
            "live_start_terminal_resolution_successor_invalid"
        )


def _validate_result_intent(value: Mapping[str, Any]) -> None:
    _require_run_id(value.get("run_id"))
    status = value.get("terminal_status")
    if status not in {
        "LIVE_AND_MATCHED",
        "ALREADY_LIVE",
        "PREVIEW_READY",
        "FAILED_PRESERVED",
        "APPLIED_BUT_NOT_VERIFIED",
    }:
        raise SessionValidationError("live_start_result_status_invalid")
    _require_deck_name(value.get("deck_name"))
    _bounded_integer(value.get("candidate_revision"), 1, 3, "candidate_revision")
    confidence = value.get("review_confidence")
    if confidence is not None and confidence not in {"high", "limited"}:
        raise SessionValidationError(
            "live_start_result_review_confidence_invalid"
        )
    limitations = value.get("visible_limitations")
    if (
        not isinstance(limitations, list)
        or len(limitations) > 32
        or limitations != sorted(set(limitations))
        or any(
            not isinstance(item, str)
            or not item
            or len(item) > 256
            or any(ord(character) < 32 for character in item)
            for item in limitations
        )
    ):
        raise SessionValidationError(
            "live_start_result_limitations_invalid"
        )
    unique = _bounded_integer(
        value.get("unique_main_deck_cards"),
        0,
        MAX_FILESYSTEM_NODES,
        "unique_main_deck_cards",
    )
    configured = value.get("configured_cards")
    unconfigured = value.get("deliberately_unconfigured_cards")
    if (configured is None) != (unconfigured is None):
        raise SessionValidationError("live_start_result_coverage_nullability_invalid")
    if configured is not None:
        configured_count = _bounded_integer(
            configured, 0, unique, "configured_cards"
        )
        unconfigured_count = _bounded_integer(
            unconfigured, 0, unique, "deliberately_unconfigured_cards"
        )
        if configured_count + unconfigured_count != unique:
            raise SessionValidationError("live_start_result_coverage_invalid")
    if status in {"LIVE_AND_MATCHED", "ALREADY_LIVE", "PREVIEW_READY"} and configured is None:
        raise SessionValidationError("live_start_result_coverage_required")
    runtime_admission = (
        value.get("runtime_admission_path"),
        value.get("runtime_admission_parent_identity"),
        value.get("runtime_admission_identity"),
        value.get("runtime_admission_sha256"),
    )
    if any(item is None for item in runtime_admission) and not all(
        item is None for item in runtime_admission
    ):
        raise SessionValidationError("live_start_result_runtime_admission_invalid")
    if runtime_admission[0] is not None:
        _require_absolute_path(runtime_admission[0], "runtime_admission_path")
        _require_identity(runtime_admission[1], "runtime_admission_parent_identity")
        _require_identity(runtime_admission[2], "runtime_admission_identity")
        _require_sha256(runtime_admission[3], "runtime_admission_sha256")
    if status == "PREVIEW_READY" and any(item is not None for item in runtime_admission):
        raise SessionValidationError("live_start_preview_runtime_admission_forbidden")
    apply_attempt_id = value.get("apply_attempt_id")
    if apply_attempt_id is not None:
        _require_run_id(apply_attempt_id)
    publication = (
        value.get("publication_revision"),
        value.get("publication_content_root_sha256"),
    )
    if (publication[0] is None) != (publication[1] is None):
        raise SessionValidationError(
            "live_start_result_publication_nullability_invalid"
        )
    if publication[0] is not None:
        if (
            not isinstance(publication[0], str)
            or re.fullmatch(r"revisions/sha256-[0-9a-f]{64}", publication[0])
            is None
        ):
            raise SessionValidationError(
                "live_start_result_publication_revision_invalid"
            )
        _require_sha256(
            publication[1], "publication_content_root_sha256"
        )
    raw_apply_status = value.get("raw_apply_status")
    if raw_apply_status not in {
        None,
        "applied",
        "already_current",
        "recovered",
        "committed_receipt_pending",
    }:
        raise SessionValidationError("live_start_raw_apply_status_invalid")
    if value.get("physical_disposition") not in {
        None,
        "NOT_COMMITTED",
        "COMMITTED",
        "COMMITTED_RECOVERY_PENDING",
        "UNKNOWN_REQUIRES_RECOVERY",
    }:
        raise SessionValidationError(
            "live_start_physical_disposition_invalid"
        )
    if value.get("runtime_match_status") not in {
        "not_run",
        "matched",
        "mismatch",
        "unknown",
    }:
        raise SessionValidationError("live_start_runtime_match_status_invalid")
    runtime_match_sha256 = value.get("runtime_match_sha256")
    if value["runtime_match_status"] in {"matched", "mismatch"}:
        _require_sha256(runtime_match_sha256, "runtime_match_sha256")
    elif runtime_match_sha256 is not None:
        raise SessionValidationError(
            "live_start_runtime_match_digest_invalid"
        )
    for key in (
        "package_root_sha256",
        "last_apply_receipt_sha256",
        "runtime_state_sha256",
        "deck_config_ini_sha256",
    ):
        digest = value.get(key)
        if digest is not None:
            _require_sha256(digest, key)
    for prefix in (
        "retained_attempt_record",
        "retained_journal",
        "retained_target_owner_journal",
    ):
        _validate_nullable_path_identity_digest(value, prefix)
    retained_candidate_identity = value.get("retained_candidate_identity")
    if retained_candidate_identity is not None:
        _require_identity(
            retained_candidate_identity,
            "retained_candidate_identity",
        )
        if value.get("physical_disposition") != "NOT_COMMITTED":
            raise SessionValidationError(
                "live_start_result_candidate_identity_invalid"
            )
    safe_states = {
        "NO_PUBLICATION_OR_RUNTIME_WRITE",
        "PUBLICATION_RETAINED_RUNTIME_UNCHANGED",
        "PUBLISHED_PREVIEW_RUNTIME_UNCHANGED",
        "PREVIOUS_RUNTIME_UNCHANGED",
        "ATTEMPT_EVIDENCE_RETAINED",
        "ACTIVE_RUNTIME_MATCHED",
    }
    if value.get("retained_safe_state") not in safe_states:
        raise SessionValidationError("live_start_result_safe_state_invalid")
    if status in {"LIVE_AND_MATCHED", "ALREADY_LIVE", "PREVIEW_READY"}:
        if value.get("error_code") is not None:
            raise SessionValidationError(
                "live_start_result_success_error_invalid"
            )
    else:
        error_code = value.get("error_code")
        if (
            not isinstance(error_code, str)
            or _SAFE_TOKEN.fullmatch(error_code) is None
        ):
            raise SessionValidationError(
                "live_start_result_error_code_invalid"
            )


def _validate_result_intent_recovery_binding(
    *,
    session_lease: LiveStartSessionLease,
    session_value: LiveStartSession,
    recovery: Mapping[str, Any],
    intent: Mapping[str, Any],
    acknowledgement: Mapping[str, Any] | None,
) -> None:
    admission = session_value.runtime_admission_binding
    publication = session_value.publication_binding
    expected = {
        "run_id": session_value.run_id,
        "deck_name": session_value.deck_name,
        "candidate_revision": session_value.candidate_revision,
        "apply_attempt_id": recovery.get("apply_attempt_id"),
        "package_root_sha256": recovery.get("package_root_sha256"),
        "last_apply_receipt_sha256": recovery.get(
            "last_apply_receipt_sha256"
        ),
        "runtime_state_sha256": recovery.get("runtime_state_sha256"),
        "deck_config_ini_sha256": recovery.get(
            "deck_config_ini_sha256"
        ),
        "runtime_match_status": recovery.get("runtime_match_status"),
        "runtime_match_sha256": recovery.get("runtime_match_sha256"),
        "physical_disposition": recovery.get(
            "stable_physical_disposition"
        ),
        "retained_candidate_identity": (
            recovery.get("predecessor_candidate_identity")
            if recovery.get("stable_physical_disposition")
            == "NOT_COMMITTED"
            else None
        ),
        "publication_revision": (
            publication.get("revision")
            if isinstance(publication, Mapping)
            else None
        ),
        "publication_content_root_sha256": (
            publication.get("content_root_sha256")
            if isinstance(publication, Mapping)
            else None
        ),
    }
    for field_name, expected_value in expected.items():
        if intent.get(field_name) != expected_value:
            raise SessionValidationError(
                "live_start_result_recovery_binding_invalid"
            )
    if isinstance(admission, Mapping):
        for intent_name, admission_name in (
            ("runtime_admission_path", "admission_path"),
            (
                "runtime_admission_parent_identity",
                "admission_parent_identity",
            ),
            ("runtime_admission_identity", "admission_identity"),
            ("runtime_admission_sha256", "admission_sha256"),
        ):
            if intent.get(intent_name) != admission.get(admission_name):
                raise SessionValidationError(
                    "live_start_result_recovery_binding_invalid"
                )
    for intent_prefix, recovery_prefix in (
        ("retained_attempt_record", "predecessor_attempt_record"),
        ("retained_journal", "predecessor_journal"),
        (
            "retained_target_owner_journal",
            "predecessor_target_owner_journal",
        ),
    ):
        for suffix in ("path", "identity", "sha256"):
            if intent.get(f"{intent_prefix}_{suffix}") != recovery.get(
                f"{recovery_prefix}_{suffix}"
            ):
                raise SessionValidationError(
                    "live_start_result_recovery_binding_invalid"
                )
    if acknowledgement is not None:
        journal_owns_target = recovery.get("install_route") == "new_target"
        acknowledgement_expected = {
            "run_id": session_value.run_id,
            "apply_attempt_id": recovery.get("apply_attempt_id"),
            "retention_owner_run_id": session_value.run_id,
            "retention_fence_path": recovery.get(
                "predecessor_attempt_record_path"
            ),
            "retention_fence_identity": recovery.get(
                "predecessor_attempt_record_identity"
            ),
            "retention_fence_sha256": recovery.get(
                "predecessor_attempt_record_sha256"
            ),
            "journal_path": recovery.get("predecessor_journal_path"),
            "journal_identity": recovery.get(
                "predecessor_journal_identity"
            ),
            "journal_sha256": recovery.get("predecessor_journal_sha256"),
            "target_owner_journal_path": recovery.get(
                "predecessor_target_owner_journal_path"
            ),
            "target_owner_journal_identity": recovery.get(
                "predecessor_target_owner_journal_identity"
            ),
            "target_owner_journal_sha256": recovery.get(
                "predecessor_target_owner_journal_sha256"
            ),
            "target_path": recovery.get("renamed_target_path"),
            "target_identity": recovery.get(
                "predecessor_renamed_target_identity"
            ),
            "package_root_sha256": recovery.get("package_root_sha256"),
            "runtime_admission_path": intent.get(
                "runtime_admission_path"
            ),
            "runtime_admission_parent_identity": intent.get(
                "runtime_admission_parent_identity"
            ),
            "runtime_admission_identity": intent.get(
                "runtime_admission_identity"
            ),
            "runtime_admission_sha256": intent.get(
                "runtime_admission_sha256"
            ),
            "journal_owns_target": journal_owns_target,
            "acknowledgement_action": (
                "retain_target_owner_delete_fence"
                if journal_owns_target
                else "delete_nonowning_attempt_and_fence"
            ),
        }
        for field_name, expected_value in acknowledgement_expected.items():
            if acknowledgement.get(field_name) != expected_value:
                raise SessionValidationError(
                    "live_start_acknowledgement_recovery_binding_invalid"
                )
    if intent.get("unique_main_deck_cards") != (
        _frozen_main_roster_count_under_lock(
            session_lease=session_lease,
            session_value=session_value,
        )
    ):
        raise SessionValidationError(
            "live_start_result_frozen_roster_binding_invalid"
        )


def _frozen_main_roster_count_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    session_value: LiveStartSession,
) -> int:
    _require_session_lease(session_lease)
    inputs_root = session_lease.session_root / "inputs"
    inputs_identity = path_identity(inputs_root)
    documents: dict[str, dict[str, Any]] = {}
    for logical_path in ("inputs/deck.json", "inputs/cards.json"):
        raw, _identity = _read_bound_file(
            session_lease.session_root / logical_path,
            expected_parent_identity=inputs_identity,
            maximum_size=LIVE_START_FROZEN_INPUT_MAXIMUM_BYTES[
                logical_path
            ],
        )
        if _bytes_sha256(raw) != session_value.artifact_bindings.get(
            logical_path
        ):
            raise SessionConflictError(
                "live_start_result_frozen_roster_artifact_drift"
            )
        documents[logical_path] = _decode_frozen_input_json(raw)
    deck = documents["inputs/deck.json"]
    cards = documents["inputs/cards.json"]
    try:
        _task2_inputs._validate_deck_and_card_closure(
            deck,
            full_cards=cards["full_cards"],
            collectible_cards=cards["collectible_cards"],
        )
        deck_identity = deck["deck_identity"]
        main_deck = _task2_inputs._deck_card_rows(
            deck_identity["main_deck"],
            "main_deck",
        )
    except (KeyError, TypeError, ValueError) as error:
        raise SessionValidationError(
            "live_start_result_frozen_roster_authority_invalid"
        ) from error
    return len(main_deck)


def _validate_attempt_acknowledgement(value: Mapping[str, Any]) -> None:
    for key in ("run_id", "apply_attempt_id", "retention_owner_run_id"):
        _require_run_id(value.get(key))
    if type(value.get("journal_owns_target")) is not bool:
        raise SessionValidationError("live_start_acknowledgement_owner_invalid")
    action = value.get("acknowledgement_action")
    if action not in {
        "retain_target_owner_delete_fence",
        "delete_nonowning_attempt_and_fence",
    }:
        raise SessionValidationError("live_start_acknowledgement_action_invalid")
    if (action == "retain_target_owner_delete_fence") != value[
        "journal_owns_target"
    ]:
        raise SessionValidationError("live_start_acknowledgement_owner_action_invalid")
    for prefix in (
        "retention_fence",
        "journal",
        "target_owner_journal",
        "runtime_admission",
    ):
        _require_absolute_path(value.get(f"{prefix}_path"), f"{prefix}_path")
        _require_identity(value.get(f"{prefix}_identity"), f"{prefix}_identity")
        _require_sha256(value.get(f"{prefix}_sha256"), f"{prefix}_sha256")
    _require_identity(
        value.get("runtime_admission_parent_identity"),
        "runtime_admission_parent_identity",
    )
    _require_absolute_path(value.get("target_path"), "target_path")
    _require_identity(value.get("target_identity"), "target_identity")
    _require_sha256(value.get("package_root_sha256"), "package_root_sha256")


def _terminal_operation_matches_authority(
    *,
    operation: Any,
    terminal_status: Any,
    result_intent: Any,
    attempt_acknowledgement: Any,
    has_resolution: bool,
) -> bool:
    if (
        not isinstance(result_intent, Mapping)
        or terminal_status != result_intent.get("terminal_status")
        or operation not in TERMINAL_RETIREMENT_STAGES
    ):
        return False
    admission = (
        result_intent.get("runtime_admission_path"),
        result_intent.get("runtime_admission_parent_identity"),
        result_intent.get("runtime_admission_identity"),
        result_intent.get("runtime_admission_sha256"),
    )
    if any(item is None for item in admission):
        return False
    disposition = result_intent.get("physical_disposition")
    runtime_match_status = result_intent.get("runtime_match_status")
    if terminal_status in {"LIVE_AND_MATCHED", "ALREADY_LIVE"}:
        return (
            operation == "ack_success"
            and disposition == "COMMITTED"
            and runtime_match_status == "matched"
            and isinstance(attempt_acknowledgement, Mapping)
            and not has_resolution
        )
    if (
        terminal_status == "FAILED_PRESERVED"
        and disposition == "NOT_COMMITTED"
        and attempt_acknowledgement is None
    ):
        retained_metadata_absent = (
            result_intent.get("retained_candidate_identity") is None
            and all(
                result_intent.get(f"{prefix}_{suffix}") is None
                for prefix in (
                    "retained_attempt_record",
                    "retained_journal",
                    "retained_target_owner_journal",
                )
                for suffix in ("path", "identity", "sha256")
            )
        )
        return (
            operation == "release_not_committed"
            and retained_metadata_absent
            and not has_resolution
        ) or (
            operation == "release_resolved_terminal" and has_resolution
        )
    if (
        terminal_status == "APPLIED_BUT_NOT_VERIFIED"
        and disposition == "COMMITTED"
        and runtime_match_status == "mismatch"
        and attempt_acknowledgement is None
    ):
        return operation == "release_committed_mismatch" and not has_resolution
    if (
        terminal_status == "APPLIED_BUT_NOT_VERIFIED"
        and disposition
        in {
            "COMMITTED_RECOVERY_PENDING",
            "UNKNOWN_REQUIRES_RECOVERY",
        }
        and runtime_match_status in {"not_run", "unknown"}
        and attempt_acknowledgement is None
    ):
        return operation == "release_resolved_terminal" and has_resolution
    return False


def _validate_terminal_retirement(value: Mapping[str, Any]) -> None:
    _require_run_id(value.get("run_id"))
    _require_run_id(value.get("apply_attempt_id"))
    operation = value.get("operation")
    if operation not in TERMINAL_RETIREMENT_STAGES:
        raise SessionValidationError("live_start_terminal_retirement_operation_invalid")
    if value.get("stage") not in TERMINAL_RETIREMENT_STAGES[operation]:
        raise SessionValidationError("live_start_terminal_retirement_stage_invalid")
    _require_sha256(value.get("source_terminal_session_sha256"), "source_terminal_session_sha256")
    _require_sha256(value.get("result_intent_sha256"), "result_intent_sha256")
    resolution = value.get("terminal_resolution_evidence")
    if operation == "release_resolved_terminal":
        if not isinstance(resolution, dict):
            raise SessionValidationError("live_start_terminal_resolution_evidence_missing")
        _validate_terminal_resolution_document(resolution)
        _validate_terminal_cleanup_outer_binding(value)
    elif resolution is not None:
        raise SessionValidationError("live_start_terminal_resolution_evidence_forbidden")
    admission = (
        value.get("runtime_admission_path"),
        value.get("runtime_admission_parent_identity"),
        value.get("runtime_admission_identity"),
        value.get("runtime_admission_sha256"),
    )
    _require_absolute_path(admission[0], "runtime_admission_path")
    _require_identity(admission[1], "runtime_admission_parent_identity")
    _require_identity(admission[2], "runtime_admission_identity")
    _require_sha256(admission[3], "runtime_admission_sha256")
    for prefix in (
        "retained_attempt_record",
        "retained_journal",
        "retained_target_owner_journal",
    ):
        _validate_nullable_path_identity_digest(value, prefix)


def _validate_terminal_resolution_document(value: Any) -> Mapping[str, Any]:
    normalized = _normalize_json(value)
    if (
        not isinstance(normalized, dict)
        or set(normalized) != _TERMINAL_RESOLUTION_FIELDS
    ):
        raise SessionValidationError(
            "live_start_terminal_resolution_fields_invalid"
        )
    if (
        len(_canonical_json(normalized))
        > LIVE_START_TERMINAL_RESOLUTION_EVIDENCE_MAX_BYTES
    ):
        raise SessionValidationError(
            "live_start_terminal_resolution_size_invalid"
        )
    if (
        normalized.get("schema_version")
        != LIVE_START_TERMINAL_RESOLUTION_EVIDENCE_SCHEMA_VERSION
        or normalized.get("resolution_kind")
        != LIVE_START_TERMINAL_RESOLUTION_EVIDENCE_KIND
    ):
        raise SessionValidationError(
            "live_start_terminal_resolution_kind_invalid"
        )
    _require_run_id(normalized.get("run_id"))
    _require_run_id(normalized.get("apply_attempt_id"))
    _bounded_integer(
        normalized.get("action_index"),
        0,
        MAX_FILESYSTEM_NODES,
        "action_index",
    )
    _validate_self_digest(
        normalized,
        error_code="live_start_terminal_resolution_content_sha256_invalid",
    )

    for prefix in (
        "predecessor_attempt_record",
        "predecessor_journal",
        "predecessor_target_owner_journal",
        "successor_attempt_record",
        "successor_journal",
        "successor_target_owner_journal",
    ):
        _validate_nullable_path_identity_digest(normalized, prefix)
    for prefix in (
        "predecessor_transaction_temp",
        "successor_transaction_temp",
    ):
        _validate_nullable_transaction_temp(normalized, prefix)

    planned_journal = (
        normalized.get("planned_journal_successor_path"),
        normalized.get("planned_journal_successor_parent_identity"),
        normalized.get("planned_journal_successor_phase"),
        normalized.get("planned_journal_successor_size"),
        normalized.get("planned_journal_successor_sha256"),
    )
    if not all(item is None for item in planned_journal):
        if any(item is None for item in planned_journal):
            raise SessionValidationError(
                "live_start_terminal_resolution_planned_journal_invalid"
            )
        _require_absolute_path(
            planned_journal[0], "planned_journal_successor_path"
        )
        _require_identity(
            planned_journal[1], "planned_journal_successor_parent_identity"
        )
        if (
            not isinstance(planned_journal[2], str)
            or _SAFE_TOKEN.fullmatch(planned_journal[2]) is None
        ):
            raise SessionValidationError(
                "live_start_planned_journal_successor_phase_invalid"
            )
        _bounded_integer(
            planned_journal[3],
            0,
            64 * 1024 * 1024,
            "planned_journal_successor_size",
        )
        _require_sha256(
            planned_journal[4], "planned_journal_successor_sha256"
        )

    candidate = (
        normalized.get("candidate_path"),
        normalized.get("candidate_parent_identity"),
        normalized.get("predecessor_candidate_identity"),
        normalized.get("successor_candidate_identity"),
    )
    if not all(item is None for item in candidate):
        if candidate[0] is None or candidate[1] is None:
            raise SessionValidationError(
                "live_start_terminal_resolution_candidate_invalid"
            )
        _require_absolute_path(candidate[0], "candidate_path")
        _require_identity(candidate[1], "candidate_parent_identity")
        for name, identity in zip(
            (
                "predecessor_candidate_identity",
                "successor_candidate_identity",
            ),
            candidate[2:],
            strict=True,
        ):
            if identity is not None:
                _require_identity(identity, name)

    disposition = normalized.get("resolved_physical_disposition")
    if disposition not in {
        "NOT_COMMITTED",
        "COMMITTED",
        "COMMITTED_RECOVERY_PENDING",
        "UNKNOWN_REQUIRES_RECOVERY",
    }:
        raise SessionValidationError(
            "live_start_terminal_resolution_disposition_invalid"
        )
    for key in (
        "allowed_attempt_record_successor_state",
        "allowed_journal_successor_phase",
    ):
        token = normalized.get(key)
        if token is not None and (
            not isinstance(token, str) or _SAFE_TOKEN.fullmatch(token) is None
        ):
            raise SessionValidationError(f"live_start_{key}_invalid")

    external = normalized.get("external_file_action")
    if external is not None:
        validate_embedded_document("external_file_action", external)
    owner = normalized.get("owner_retirement")
    if owner is not None:
        _validate_owner_retirement_document(owner)
    _validate_terminal_cleanup_binding(normalized)

    _require_sha256(normalized.get("package_root_sha256"), "package_root_sha256")
    for key in (
        "last_apply_receipt_sha256",
        "runtime_state_sha256",
        "deck_config_ini_sha256",
    ):
        digest = normalized.get(key)
        if digest is not None:
            _require_sha256(digest, key)
    match_status = normalized.get("runtime_match_status")
    if match_status not in {"not_run", "matched", "mismatch", "unknown"}:
        raise SessionValidationError(
            "live_start_terminal_resolution_runtime_match_status_invalid"
        )
    match_digest = normalized.get("runtime_match_sha256")
    if match_status in {"matched", "mismatch"}:
        _require_sha256(match_digest, "runtime_match_sha256")
    elif match_digest is not None:
        raise SessionValidationError(
            "live_start_terminal_resolution_runtime_match_digest_invalid"
        )
    return _freeze_mapping(normalized)


def _validate_owner_retirement_document(value: Any) -> Mapping[str, Any]:
    normalized = _normalize_json(value)
    if not isinstance(normalized, dict) or set(normalized) != _OWNER_RETIREMENT_FIELDS:
        raise SessionValidationError("live_start_owner_retirement_fields_invalid")
    if (
        len(_canonical_json(normalized))
        > LIVE_START_OWNER_RETIREMENT_EVIDENCE_MAX_BYTES
    ):
        raise SessionValidationError("live_start_owner_retirement_size_invalid")
    if (
        normalized.get("schema_version")
        != LIVE_START_OWNER_RETIREMENT_EVIDENCE_SCHEMA_VERSION
        or normalized.get("evidence_kind")
        != LIVE_START_OWNER_RETIREMENT_EVIDENCE_KIND
    ):
        raise SessionValidationError("live_start_owner_retirement_kind_invalid")
    if normalized.get("stage") not in OWNER_RETIREMENT_STAGES:
        raise SessionValidationError("live_start_owner_retirement_stage_invalid")
    _validate_self_digest(
        normalized,
        error_code="live_start_owner_retirement_content_sha256_invalid",
    )
    for key in ("retired_owner_transaction_id", "successor_transaction_id"):
        _require_run_id(normalized.get(key))
    for key in (
        "tombstone_path",
        "initial_owner_journal_path",
        "retired_target_path",
        "successor_owner_journal_path",
    ):
        _require_absolute_path(normalized.get(key), key)
    for key in (
        "tombstone_parent_identity",
        "initial_owner_journal_identity",
        "current_owner_journal_identity",
        "retired_target_parent_identity",
        "retired_target_identity",
        "successor_owner_journal_identity",
    ):
        _require_identity(normalized.get(key), key)
    for key in (
        "tombstone_sha256",
        "initial_owner_journal_sha256",
        "current_owner_journal_sha256",
        "retired_target_tree_sha256",
        "successor_package_root_sha256",
        "successor_owner_journal_sha256",
        "cleanup_manifest_sha256",
    ):
        _require_sha256(normalized.get(key), key)
    tombstone_identity = normalized.get("tombstone_identity")
    if normalized["stage"] == "PREPARED_PLANNED":
        if tombstone_identity is not None:
            raise SessionValidationError(
                "live_start_owner_retirement_tombstone_identity_invalid"
            )
    else:
        _require_identity(tombstone_identity, "tombstone_identity")
    count = _bounded_integer(
        normalized.get("cleanup_entry_count"),
        0,
        MAX_FILESYSTEM_NODES,
        "owner_cleanup_entry_count",
    )
    cursor = _bounded_integer(
        normalized.get("cleanup_cursor"),
        0,
        count,
        "owner_cleanup_cursor",
    )
    planned = (
        normalized.get("planned_completed_tombstone_size"),
        normalized.get("planned_completed_tombstone_sha256"),
    )
    if (planned[0] is None) != (planned[1] is None):
        raise SessionValidationError(
            "live_start_owner_retirement_planned_tombstone_invalid"
        )
    if planned[0] is not None:
        _bounded_integer(
            planned[0],
            1,
            LIVE_START_OWNER_RETIREMENT_TOMBSTONE_MAX_BYTES,
            "planned_completed_tombstone_size",
        )
        _require_sha256(planned[1], "planned_completed_tombstone_sha256")
    if normalized["stage"] in {
        "TARGET_RETIRED",
        "COMPLETED",
        "OWNER_RETIRED",
    } and planned[0] is None:
        raise SessionValidationError(
            "live_start_owner_retirement_planned_tombstone_missing"
        )
    next_entry = tuple(
        normalized.get(key)
        for key in (
            "next_entry_relative_path",
            "next_entry_kind",
            "next_entry_identity",
            "next_entry_parent_identity",
            "next_entry_size",
            "next_entry_sha256",
        )
    )
    if not all(item is None for item in next_entry):
        if next_entry[0] is None or next_entry[1] not in {"file", "directory"}:
            raise SessionValidationError(
                "live_start_owner_retirement_next_entry_invalid"
            )
        _require_safe_relative_path(next_entry[0], "owner_next_entry_relative_path")
        _require_identity(next_entry[2], "next_entry_identity")
        _require_identity(next_entry[3], "next_entry_parent_identity")
        if next_entry[1] == "file":
            _bounded_integer(
                next_entry[4],
                0,
                64 * 1024 * 1024,
                "next_entry_size",
            )
            _require_sha256(next_entry[5], "next_entry_sha256")
        elif next_entry[4] is not None or next_entry[5] is not None:
            raise SessionValidationError(
                "live_start_owner_retirement_next_entry_invalid"
            )
    if type(normalized.get("old_owner_journal_retired")) is not bool:
        raise SessionValidationError(
            "live_start_owner_retirement_old_owner_invalid"
        )
    if normalized["stage"] == "OWNER_RETIRED":
        if not normalized["old_owner_journal_retired"]:
            raise SessionValidationError(
                "live_start_owner_retirement_old_owner_invalid"
            )
    elif normalized["old_owner_journal_retired"]:
        raise SessionValidationError(
            "live_start_owner_retirement_old_owner_invalid"
        )
    if cursor == count and any(item is not None for item in next_entry):
        raise SessionValidationError(
            "live_start_owner_retirement_next_entry_invalid"
        )
    stage = normalized["stage"]
    planned_complete = planned[0] is not None
    has_next_entry = any(item is not None for item in next_entry)
    if stage in {"PREPARED_PLANNED", "PREPARED"}:
        if (
            cursor != 0
            or planned_complete
            or has_next_entry != (count > 0)
        ):
            raise SessionValidationError(
                "live_start_owner_retirement_prepared_matrix_invalid"
            )
    elif stage == "CLEANING":
        at_end = cursor == count
        if has_next_entry != (not at_end) or planned_complete != at_end:
            raise SessionValidationError(
                "live_start_owner_retirement_cleaning_matrix_invalid"
            )
    elif (
        cursor != count
        or has_next_entry
        or not planned_complete
    ):
        raise SessionValidationError(
            "live_start_owner_retirement_terminal_matrix_invalid"
        )
    return _freeze_mapping(normalized)


def _validate_owner_tombstone_document(
    value: Any,
) -> Mapping[str, Any]:
    normalized = _normalize_json(value)
    if (
        not isinstance(normalized, dict)
        or set(normalized) != _OWNER_TOMBSTONE_FIELDS
    ):
        raise SessionValidationError(
            "live_start_owner_tombstone_fields_invalid"
        )
    if (
        len(_canonical_json(normalized))
        > LIVE_START_OWNER_RETIREMENT_TOMBSTONE_MAX_BYTES
    ):
        raise SessionValidationError(
            "live_start_owner_tombstone_size_invalid"
        )
    if (
        normalized.get("schema_version") != 1
        or normalized.get("record_kind")
        != "runtime_owner_retirement"
        or normalized.get("state") not in {"PREPARED", "COMPLETED"}
    ):
        raise SessionValidationError(
            "live_start_owner_tombstone_kind_invalid"
        )
    _validate_self_digest(
        normalized,
        error_code="live_start_owner_tombstone_content_sha256_invalid",
    )
    for key in (
        "retired_owner_transaction_id",
        "successor_transaction_id",
    ):
        _require_run_id(normalized.get(key))
    retired_owner_id = normalized["retired_owner_transaction_id"]
    successor_id = normalized["successor_transaction_id"]
    if retired_owner_id == successor_id:
        raise SessionValidationError(
            "live_start_owner_tombstone_transaction_invalid"
        )
    for key in (
        "initial_owner_journal_path",
        "retired_target_path",
        "successor_owner_journal_path",
    ):
        _require_absolute_path(normalized.get(key), key)
    initial_owner_path = Path(normalized["initial_owner_journal_path"])
    successor_owner_path = Path(normalized["successor_owner_journal_path"])
    if (
        initial_owner_path.parent != successor_owner_path.parent
        or initial_owner_path.name != f"{retired_owner_id}.json"
        or successor_owner_path.name != f"{successor_id}.json"
    ):
        raise SessionValidationError(
            "live_start_owner_tombstone_journal_path_invalid"
        )
    for key in (
        "initial_owner_journal_identity",
        "retired_target_parent_identity",
        "retired_target_identity",
        "successor_owner_journal_identity",
    ):
        _require_identity(normalized.get(key), key)
    for key in (
        "initial_owner_journal_sha256",
        "retired_target_tree_sha256",
        "successor_package_root_sha256",
        "successor_owner_journal_sha256",
        "cleanup_manifest_sha256",
    ):
        _require_sha256(normalized.get(key), key)
    entries = normalized.get("cleanup_entries")
    if not isinstance(entries, list):
        raise SessionValidationError(
            "live_start_owner_tombstone_entries_invalid"
        )
    count = _bounded_integer(
        normalized.get("cleanup_entry_count"),
        0,
        MAX_FILESYSTEM_NODES,
        "owner_tombstone_cleanup_entry_count",
    )
    if len(entries) != count:
        raise SessionValidationError(
            "live_start_owner_tombstone_entry_count_invalid"
        )
    relative_paths: set[str] = set()
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or set(entry) != _OWNER_TOMBSTONE_ENTRY_FIELDS
        ):
            raise SessionValidationError(
                "live_start_owner_tombstone_entry_invalid"
            )
        relative_path = entry.get("relative_path")
        _require_safe_relative_path(
            relative_path,
            "owner_tombstone_relative_path",
        )
        if relative_path in relative_paths:
            raise SessionValidationError(
                "live_start_owner_tombstone_entry_duplicate"
            )
        relative_paths.add(relative_path)
        if entry.get("entry_kind") not in {"file", "directory"}:
            raise SessionValidationError(
                "live_start_owner_tombstone_entry_kind_invalid"
            )
        _require_identity(entry.get("identity"), "owner_tombstone_identity")
        _require_identity(
            entry.get("expected_parent_identity"),
            "owner_tombstone_parent_identity",
        )
        if entry["entry_kind"] == "file":
            _bounded_integer(
                entry.get("size"),
                0,
                64 * 1024 * 1024,
                "owner_tombstone_entry_size",
            )
            _require_sha256(
                entry.get("sha256"),
                "owner_tombstone_entry_sha256",
            )
        elif entry.get("size") is not None or entry.get("sha256") is not None:
            raise SessionValidationError(
                "live_start_owner_tombstone_directory_invalid"
            )
    files = [entry for entry in entries if entry["entry_kind"] == "file"]
    directories = [
        entry for entry in entries if entry["entry_kind"] == "directory"
    ]
    canonical_entries = sorted(
        files,
        key=lambda entry: (
            str(entry["relative_path"]).count("/"),
            str(entry["relative_path"]),
        ),
        reverse=True,
    ) + sorted(
        directories,
        key=lambda entry: (
            str(entry["relative_path"]).count("/"),
            str(entry["relative_path"]),
        ),
        reverse=True,
    )
    if entries != canonical_entries:
        raise SessionValidationError(
            "live_start_owner_tombstone_entry_order_invalid"
        )
    directory_identities = {
        str(entry["relative_path"]): entry["identity"]
        for entry in directories
    }
    target_identity = normalized["retired_target_identity"]
    for entry in entries:
        relative_path = str(entry["relative_path"])
        parent_relative = relative_path.rpartition("/")[0]
        expected_parent = (
            target_identity
            if not parent_relative
            else directory_identities.get(parent_relative)
        )
        if (
            expected_parent is None
            or entry["expected_parent_identity"] != expected_parent
        ):
            raise SessionValidationError(
                "live_start_owner_tombstone_entry_topology_invalid"
            )
    manifest_sha256 = (
        f"sha256:{sha256(_canonical_json(entries)).hexdigest()}"
    )
    if normalized.get("cleanup_manifest_sha256") != manifest_sha256:
        raise SessionValidationError(
            "live_start_owner_tombstone_manifest_invalid"
        )
    completed = (
        normalized.get("completed_cleanup_cursor"),
        normalized.get("completed_owner_journal_identity"),
        normalized.get("completed_owner_journal_sha256"),
    )
    if normalized["state"] == "PREPARED":
        if any(item is not None for item in completed):
            raise SessionValidationError(
                "live_start_owner_tombstone_prepared_invalid"
            )
    else:
        if completed[0] != count:
            raise SessionValidationError(
                "live_start_owner_tombstone_completed_cursor_invalid"
            )
        _require_identity(
            completed[1],
            "completed_owner_journal_identity",
        )
        _require_sha256(
            completed[2],
            "completed_owner_journal_sha256",
        )
    return _freeze_mapping(normalized)


def _validate_terminal_cleanup_inventory_document(
    value: Any,
) -> tuple[Mapping[str, Any], bytes]:
    normalized = _normalize_json(value)
    if (
        not isinstance(normalized, dict)
        or set(normalized) != _TERMINAL_CLEANUP_INVENTORY_FIELDS
    ):
        raise SessionValidationError(
            "live_start_terminal_cleanup_inventory_fields_invalid"
        )
    raw = _canonical_json(normalized)
    if len(raw) > LIVE_START_TERMINAL_CLEANUP_INVENTORY_MAX_BYTES:
        raise SessionValidationError(
            "live_start_terminal_cleanup_inventory_size_invalid"
        )
    if (
        normalized.get("schema_version")
        != LIVE_START_TERMINAL_CLEANUP_INVENTORY_SCHEMA_VERSION
        or normalized.get("inventory_kind")
        != LIVE_START_TERMINAL_CLEANUP_INVENTORY_KIND
    ):
        raise SessionValidationError(
            "live_start_terminal_cleanup_inventory_kind_invalid"
        )
    _validate_self_digest(
        normalized,
        error_code=(
            "live_start_terminal_cleanup_inventory_content_sha256_invalid"
        ),
    )
    _require_run_id(normalized.get("run_id"))
    _require_run_id(normalized.get("apply_attempt_id"))
    _require_absolute_path(
        normalized.get("runtime_root_path"), "runtime_root_path"
    )
    _require_identity(
        normalized.get("runtime_root_identity"), "runtime_root_identity"
    )
    _require_sha256(
        normalized.get("cleanup_manifest_sha256"), "cleanup_manifest_sha256"
    )
    roots = normalized.get("cleanup_roots")
    if not isinstance(roots, list) or len(roots) > 2:
        raise SessionValidationError(
            "live_start_terminal_cleanup_inventory_roots_invalid"
        )
    root_roles: list[str] = []
    for root in roots:
        if not isinstance(root, dict) or set(root) != _TERMINAL_CLEANUP_ROOT_FIELDS:
            raise SessionValidationError(
                "live_start_terminal_cleanup_inventory_root_fields_invalid"
            )
        role = root.get("root_role")
        if role not in {"candidate", "target"} or role in root_roles:
            raise SessionValidationError(
                "live_start_terminal_cleanup_inventory_roots_invalid"
            )
        root_roles.append(role)
        _require_absolute_path(root.get("source_path"), "cleanup_root_path")
        _require_identity(root.get("source_identity"), "cleanup_root_identity")
        _require_identity(
            root.get("expected_parent_identity"),
            "cleanup_root_parent_identity",
        )
    if root_roles != sorted(root_roles, key=("candidate", "target").index):
        raise SessionValidationError(
            "live_start_terminal_cleanup_inventory_roots_order_invalid"
        )
    entries = normalized.get("entries")
    if (
        not isinstance(entries, list)
        or len(entries) > LIVE_START_TERMINAL_CLEANUP_INVENTORY_MAX_ENTRIES
    ):
        raise SessionValidationError(
            "live_start_terminal_cleanup_inventory_entries_invalid"
        )
    seen: set[tuple[str, str]] = set()
    ordering: list[tuple[int, int, bytes]] = []
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or set(entry) != _TERMINAL_CLEANUP_ENTRY_FIELDS
        ):
            raise SessionValidationError(
                "live_start_terminal_cleanup_inventory_entry_fields_invalid"
            )
        role = entry.get("root_role")
        if role not in root_roles:
            raise SessionValidationError(
                "live_start_terminal_cleanup_inventory_entry_root_invalid"
            )
        relative = _require_safe_relative_path(
            entry.get("relative_path"), "cleanup_entry_relative_path"
        )
        key = (role, relative)
        if key in seen:
            raise SessionValidationError(
                "live_start_terminal_cleanup_inventory_entry_duplicate"
            )
        seen.add(key)
        kind = entry.get("entry_kind")
        if kind not in {"file", "directory"}:
            raise SessionValidationError(
                "live_start_terminal_cleanup_inventory_entry_kind_invalid"
            )
        _require_identity(entry.get("identity"), "cleanup_entry_identity")
        _require_identity(
            entry.get("expected_parent_identity"),
            "cleanup_entry_parent_identity",
        )
        if kind == "file":
            _bounded_integer(
                entry.get("size"),
                0,
                64 * 1024 * 1024,
                "cleanup_entry_size",
            )
            _require_sha256(entry.get("sha256"), "cleanup_entry_sha256")
        elif entry.get("size") is not None or entry.get("sha256") is not None:
            raise SessionValidationError(
                "live_start_terminal_cleanup_inventory_entry_nullability_invalid"
            )
        depth = 0 if relative == "." else relative.count("/") + 1
        ordering.append(
            (("candidate", "target").index(role), -depth, relative.encode())
        )
    if ordering != sorted(ordering):
        raise SessionValidationError(
            "live_start_terminal_cleanup_inventory_entries_order_invalid"
        )
    count = _bounded_integer(
        normalized.get("cleanup_entry_count"),
        0,
        LIVE_START_TERMINAL_CLEANUP_INVENTORY_MAX_ENTRIES,
        "terminal_cleanup_inventory_count",
    )
    if count != len(entries):
        raise SessionValidationError(
            "live_start_terminal_cleanup_inventory_count_invalid"
        )
    return _freeze_mapping(normalized), raw


def _validate_self_digest(value: Mapping[str, Any], *, error_code: str) -> None:
    claimed = value.get("content_sha256")
    unsigned = dict(value)
    unsigned.pop("content_sha256", None)
    if claimed != _self_digest(unsigned):
        raise SessionValidationError(error_code)


def _validate_nullable_path_identity_digest(
    value: Mapping[str, Any],
    prefix: str,
) -> None:
    triplet = (
        value.get(f"{prefix}_path"),
        value.get(f"{prefix}_identity"),
        value.get(f"{prefix}_sha256"),
    )
    if all(item is None for item in triplet):
        return
    if any(item is None for item in triplet):
        raise SessionValidationError(f"live_start_{prefix}_triplet_invalid")
    _require_absolute_path(triplet[0], f"{prefix}_path")
    _require_identity(triplet[1], f"{prefix}_identity")
    _require_sha256(triplet[2], f"{prefix}_sha256")


def _validate_nullable_transaction_temp(
    value: Mapping[str, Any],
    prefix: str,
) -> None:
    names = (
        "path",
        "parent_identity",
        "identity",
        "size",
        "sha256",
        "classification",
        "origin",
    )
    items = tuple(value.get(f"{prefix}_{name}") for name in names)
    if all(item is None for item in items):
        return
    if any(item is None for item in items):
        raise SessionValidationError(f"live_start_{prefix}_nullability_invalid")
    _require_absolute_path(items[0], f"{prefix}_path")
    _require_identity(items[1], f"{prefix}_parent_identity")
    _require_identity(items[2], f"{prefix}_identity")
    _bounded_integer(
        items[3], 0, 64 * 1024 * 1024, f"{prefix}_size"
    )
    _require_sha256(items[4], f"{prefix}_sha256")
    if items[5] not in {
        "legacy_complete_valid",
        "legacy_redundant_equal",
        "legacy_monotone_successor",
        "legacy_partial_invalid",
    }:
        raise SessionValidationError(
            f"live_start_{prefix}_classification_invalid"
        )
    if items[6] != "legacy_uuid":
        raise SessionValidationError(f"live_start_{prefix}_origin_invalid")


def _validate_terminal_cleanup_binding(value: Mapping[str, Any]) -> None:
    stage = value.get("cleanup_stage")
    fields = (
        value.get("cleanup_inventory_path"),
        value.get("cleanup_inventory_parent_identity"),
        value.get("cleanup_inventory_identity"),
        value.get("cleanup_inventory_size"),
        value.get("cleanup_inventory_sha256"),
        value.get("cleanup_manifest_sha256"),
        value.get("cleanup_entry_count"),
        value.get("cleanup_cursor"),
        value.get("cleanup_roots"),
    )
    if stage is None:
        if any(item is not None for item in fields):
            raise SessionValidationError(
                "live_start_terminal_resolution_cleanup_nullability_invalid"
            )
        return
    if stage not in {
        "PREPARED",
        "INVENTORY_BOUND",
        "CLEANING",
        "JOURNAL_RETIRED",
        "FENCE_RETIRED",
        "INVENTORY_RETIRED",
        "COMPLETE",
    }:
        raise SessionValidationError(
            "live_start_terminal_resolution_cleanup_stage_invalid"
        )
    required = (
        fields[0],
        fields[1],
        fields[3],
        fields[4],
        fields[5],
        fields[6],
        fields[7],
        fields[8],
    )
    if any(item is None for item in required):
        raise SessionValidationError(
            "live_start_terminal_resolution_cleanup_nullability_invalid"
        )
    _require_absolute_path(fields[0], "cleanup_inventory_path")
    _require_identity(fields[1], "cleanup_inventory_parent_identity")
    if stage == "PREPARED":
        if fields[2] is not None:
            raise SessionValidationError(
                "live_start_terminal_resolution_cleanup_identity_invalid"
            )
    else:
        _require_identity(fields[2], "cleanup_inventory_identity")
    _bounded_integer(
        fields[3],
        1,
        LIVE_START_TERMINAL_CLEANUP_INVENTORY_MAX_BYTES,
        "cleanup_inventory_size",
    )
    _require_sha256(fields[4], "cleanup_inventory_sha256")
    _require_sha256(fields[5], "cleanup_manifest_sha256")
    count = _bounded_integer(
        fields[6],
        0,
        LIVE_START_TERMINAL_CLEANUP_INVENTORY_MAX_ENTRIES,
        "cleanup_entry_count",
    )
    cursor = _bounded_integer(fields[7], 0, count, "cleanup_cursor")
    if not isinstance(fields[8], list) or len(fields[8]) > 2:
        raise SessionValidationError("live_start_cleanup_roots_invalid")
    external = value.get("external_file_action")
    if stage == "PREPARED":
        if (
            cursor != 0
            or not isinstance(external, Mapping)
            or external.get("action_kind")
            != "commit_bound_terminal_cleanup_inventory"
            or external.get("stage") not in {"PLANNED", "STAGING_BOUND"}
            or external.get("commit_mode") != "create_no_replace"
            or external.get("predecessor_state") != "absent"
            or Path(external.get("final_path", "")) != Path(fields[0])
            or tuple(external.get("parent_identity", ()))
            != tuple(fields[1])
            or external.get("planned_successor_size") != fields[3]
            or external.get("planned_successor_sha256") != fields[4]
        ):
            raise SessionValidationError(
                "live_start_terminal_resolution_cleanup_prepared_invalid"
            )
    elif external is not None:
        raise SessionValidationError(
            "live_start_terminal_resolution_cleanup_external_invalid"
        )
    if stage == "INVENTORY_BOUND" and cursor != 0:
        raise SessionValidationError(
            "live_start_terminal_resolution_cleanup_cursor_invalid"
        )
    if stage in {
        "JOURNAL_RETIRED",
        "FENCE_RETIRED",
        "INVENTORY_RETIRED",
        "COMPLETE",
    } and cursor != count:
        raise SessionValidationError(
            "live_start_terminal_resolution_cleanup_cursor_invalid"
        )


def _validate_terminal_cleanup_outer_binding(
    retirement: Mapping[str, Any],
) -> None:
    if retirement.get("operation") != "release_resolved_terminal":
        return
    resolution = retirement.get("terminal_resolution_evidence")
    if not isinstance(resolution, Mapping):
        raise SessionValidationError(
            "live_start_terminal_resolution_cleanup_outer_invalid"
        )
    outer_stage = retirement.get("stage")
    cleanup_stage = resolution.get("cleanup_stage")
    if cleanup_stage is None:
        if outer_stage in {
            "RECOVERY_INVENTORY_BOUND",
            "RECOVERY_CLEANING",
            "RECOVERY_INVENTORY_RETIRED",
        }:
            raise SessionValidationError(
                "live_start_terminal_resolution_cleanup_outer_invalid"
            )
        return
    expected_cleanup_stage = {
        "RECOVERY_PREPARED": "PREPARED",
        "RECOVERY_INVENTORY_BOUND": "INVENTORY_BOUND",
        "RECOVERY_CLEANING": "CLEANING",
        "RECOVERY_JOURNAL_RETIRED": "JOURNAL_RETIRED",
        "RECOVERY_FENCE_RETIRED": "FENCE_RETIRED",
        "RECOVERY_INVENTORY_RETIRED": "INVENTORY_RETIRED",
        "RECOVERY_STABILIZED": "COMPLETE",
        "EVIDENCE_RETIRED": "COMPLETE",
        "ADMISSION_RELEASE_AUTHORIZED": "COMPLETE",
    }.get(outer_stage)
    if cleanup_stage != expected_cleanup_stage:
        raise SessionValidationError(
            "live_start_terminal_resolution_cleanup_outer_invalid"
        )


def _require_safe_relative_path(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise SessionValidationError(f"live_start_{name}_invalid")
    if value == ".":
        return value
    if (
        "\\" in value
        or value.startswith("/")
        or value.endswith("/")
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise SessionValidationError(f"live_start_{name}_invalid")
    return value


def _validate_artifact_bindings(value: Any) -> Mapping[str, str]:
    if not isinstance(value, dict) or len(value) > len(RUN_LOGICAL_FILES):
        raise SessionValidationError("live_start_artifact_bindings_invalid")
    result: dict[str, str] = {}
    for logical, digest in value.items():
        if logical not in RUN_LOGICAL_FILES or logical == "session.json":
            raise SessionValidationError("live_start_artifact_path_invalid")
        _require_sha256(digest, "artifact_sha256")
        result[logical] = digest
    manifest_digest = result.get("inputs/input_snapshot_manifest.json")
    if manifest_digest is None:
        raise SessionValidationError("live_start_snapshot_binding_missing")
    return MappingProxyType(dict(sorted(result.items())))


_RECEIPT_FIELDS = MappingProxyType(
    {
        "candidate_validation": frozenset(
            """schema_version receipt_kind run_id candidate_revision
            starter_context_sha256 candidate_sha256 status findings
            content_sha256""".split()
        ),
        "review_validation": frozenset(
            """schema_version receipt_kind run_id candidate_revision
            starter_context_sha256 candidate_sha256 review_sha256 review_status
            confidence content_sha256""".split()
        ),
        "package_validation": frozenset(
            """schema_version receipt_kind run_id input_snapshot_manifest_sha256
            starter_context_sha256 candidate_sha256 candidate_revision
            review_sha256 package_root_sha256 derivation_receipt_sha256
            operator_summary_sha256 apply_gate_allowed prepublication_work_root
            prepublication_work_parent_path prepublication_work_parent_identity
            prepublication_work_root_identity prepublication_work_tree_sha256
            cleanup_manifest_sha256 cleanup_entry_count content_sha256""".split()
        ),
    }
)


def seal_validation_receipt(
    *,
    receipt_kind: Literal[
        "candidate_validation", "review_validation", "package_validation"
    ],
    unsigned_value: Mapping[str, Any],
) -> Mapping[str, Any]:
    value = _normalize_json(unsigned_value)
    if not isinstance(value, dict):
        raise SessionValidationError("live_start_receipt_not_object")
    value.pop("content_sha256", None)
    value["schema_version"] = 1
    value["receipt_kind"] = receipt_kind
    value["content_sha256"] = _self_digest(value)
    return validate_validation_receipt(receipt_kind=receipt_kind, value=value)


def validate_validation_receipt(
    *,
    receipt_kind: Literal[
        "candidate_validation", "review_validation", "package_validation"
    ],
    value: Mapping[str, Any],
    run_id: str | None = None,
    candidate_revision: int | None = None,
) -> Mapping[str, Any]:
    normalized = _normalize_json(value)
    if not isinstance(normalized, dict) or set(normalized) != _RECEIPT_FIELDS[receipt_kind]:
        raise SessionValidationError("live_start_validation_receipt_fields_invalid")
    if normalized.get("schema_version") != 1 or normalized.get("receipt_kind") != receipt_kind:
        raise SessionValidationError("live_start_validation_receipt_kind_invalid")
    claimed = normalized["content_sha256"]
    unsigned = dict(normalized)
    unsigned.pop("content_sha256")
    if claimed != _self_digest(unsigned):
        raise SessionValidationError("live_start_validation_receipt_digest_invalid")
    _require_run_id(normalized.get("run_id"))
    revision = _bounded_integer(normalized.get("candidate_revision"), 1, 3, "candidate_revision")
    if run_id is not None and normalized["run_id"] != run_id:
        raise SessionConflictError("live_start_validation_receipt_run_mismatch")
    if candidate_revision is not None and revision != candidate_revision:
        raise SessionConflictError("live_start_validation_receipt_revision_mismatch")
    if receipt_kind == "candidate_validation":
        _require_validation_receipt_digests(
            normalized,
            "starter_context_sha256",
            "candidate_sha256",
        )
        if normalized.get("status") != "valid" or normalized.get("findings") != []:
            raise SessionValidationError("live_start_candidate_receipt_not_valid")
    elif receipt_kind == "review_validation":
        _require_validation_receipt_digests(
            normalized,
            "starter_context_sha256",
            "candidate_sha256",
            "review_sha256",
        )
        if normalized.get("review_status") != "approved" or normalized.get("confidence") not in {"high", "limited"}:
            raise SessionValidationError("live_start_review_receipt_not_approved")
    else:
        _require_validation_receipt_digests(
            normalized,
            "input_snapshot_manifest_sha256",
            "starter_context_sha256",
            "candidate_sha256",
            "review_sha256",
            "package_root_sha256",
            "derivation_receipt_sha256",
            "operator_summary_sha256",
            "prepublication_work_tree_sha256",
            "cleanup_manifest_sha256",
        )
        if (
            type(normalized.get("apply_gate_allowed")) is not bool
            or not normalized["apply_gate_allowed"]
        ):
            raise SessionValidationError(
                "live_start_package_receipt_gate_invalid"
            )
        for key in (
            "prepublication_work_root",
            "prepublication_work_parent_path",
        ):
            _require_absolute_path(normalized.get(key), key)
        for key in (
            "prepublication_work_parent_identity",
            "prepublication_work_root_identity",
        ):
            _require_identity(normalized.get(key), key)
        _bounded_integer(
            normalized.get("cleanup_entry_count"),
            0,
            MAX_FILESYSTEM_NODES,
            "cleanup_entry_count",
        )
    return _freeze_mapping(normalized)


def _require_validation_receipt_digests(
    value: Mapping[str, Any],
    *field_names: str,
) -> None:
    try:
        for field_name in field_names:
            _require_sha256(value.get(field_name), field_name)
    except SessionValidationError as error:
        raise SessionValidationError(
            "live_start_validation_receipt_digest_invalid"
        ) from error


def _validate_completed_phase_receipts(
    *,
    session_lease: LiveStartSessionLease,
    session: LiveStartSession,
) -> None:
    phase_index = list(LiveStartPhase).index(session.phase)
    requirements = (
        (
            LiveStartPhase.CANDIDATE_VALIDATED,
            "receipts/candidate_validation.json",
            "candidate_validation",
        ),
        (
            LiveStartPhase.REVIEW_APPROVED,
            "receipts/review_validation.json",
            "review_validation",
        ),
        (
            LiveStartPhase.PACKAGE_VALIDATED,
            "receipts/package_validation.json",
            "package_validation",
        ),
    )
    for required_phase, logical, kind in requirements:
        if phase_index < list(LiveStartPhase).index(required_phase):
            continue
        receipt_path = session_lease.session_root / logical
        if (
            not os.path.lexists(receipt_path)
            and _review_revision_candidate_receipt_cleanup_pending(
                session=session,
                logical_path=logical,
                artifact_path=receipt_path,
            )
        ):
            continue
        raw, _identity = _read_bound_file(
            receipt_path,
            expected_parent_identity=path_identity(
                receipt_path.parent
            ),
            maximum_size=256 * 1024,
        )
        if kind == "package_validation" and not raw.endswith(b"\n"):
            try:
                from hsconfig.package_request import FrozenJsonDocument

                receipt_value = FrozenJsonDocument.from_json_bytes(
                    raw
                ).to_value()
            except (TypeError, UnicodeError, ValueError) as error:
                raise SessionValidationError(
                    "live_start_json_not_canonical"
                ) from error
            if not isinstance(receipt_value, dict):
                raise SessionValidationError("live_start_json_not_object")
            receipt = receipt_value
        else:
            receipt = _decode_json_document(raw)
        receipt = validate_validation_receipt(
            receipt_kind=kind,  # type: ignore[arg-type]
            value=receipt,
            run_id=session.run_id,
            candidate_revision=session.candidate_revision,
        )
        _require_completed_receipt_binding(
            session=session,
            receipt_kind=kind,
            receipt=receipt,
            receipt_bytes_sha256=_bytes_sha256(raw),
            receipt_logical_path=logical,
        )


def _require_completed_receipt_binding(
    *,
    session: LiveStartSession,
    receipt_kind: str,
    receipt: Mapping[str, Any],
    receipt_bytes_sha256: str,
    receipt_logical_path: str,
) -> None:
    bindings = session.artifact_bindings
    expected: dict[str, Any] = {
        "starter_context_sha256": bindings.get(
            "starter/starter_context.json"
        ),
        "candidate_sha256": bindings.get(
            "starter/starter_config_candidate.json"
        ),
    }
    if receipt_kind in {"review_validation", "package_validation"}:
        expected["review_sha256"] = bindings.get(
            "starter/starter_config_review.json"
        )
    if receipt_kind == "package_validation":
        expected["input_snapshot_manifest_sha256"] = (
            session.input_snapshot_manifest_sha256
        )
        work = session.prepublication_work_binding
        if not isinstance(work, Mapping):
            raise SessionConflictError(
                "live_start_validation_receipt_work_binding_missing"
            )
        expected.update(
            {
                "prepublication_work_root": work.get("work_root"),
                "prepublication_work_parent_path": work.get(
                    "work_parent_path"
                ),
                "prepublication_work_parent_identity": work.get(
                    "work_parent_identity"
                ),
                "prepublication_work_root_identity": work.get(
                    "work_root_identity"
                ),
                "prepublication_work_tree_sha256": work.get(
                    "work_tree_sha256"
                ),
                "cleanup_manifest_sha256": work.get(
                    "cleanup_manifest_sha256"
                ),
                "cleanup_entry_count": work.get("cleanup_entry_count"),
            }
        )
    if (
        bindings.get(receipt_logical_path) != receipt_bytes_sha256
        or any(receipt.get(key) != item for key, item in expected.items())
    ):
        raise SessionConflictError(
            "live_start_validation_receipt_artifact_binding_mismatch"
        )


def _validate_run_layout_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    session: LiveStartSession,
) -> None:
    _require_session_lease(session_lease)
    root = session_lease.session_root
    pending = session.pending_transition
    if (
        isinstance(pending, Mapping)
        and pending.get("operation") == "review_revision"
    ):
        _require_exact_review_revision_run_locations(
            session_lease=session_lease,
            revision_session=session,
        )
    allowed_reserved = _allowed_reserved_run_paths(root=root, session=session)
    allowed_files = _allowed_logical_run_files(root=root, session=session)
    allowed_posix_two_link_files = (
        _review_revision_posix_two_link_layout_paths(
            root=root,
            session=session,
        )
    )
    allowed_directories = {
        prefix
        for logical in allowed_files | set(allowed_reserved)
        for prefix in _logical_parent_prefixes(logical)
    }
    _validate_authority_roots_no_ads(session_lease=session_lease)
    result_reserved_seen = 0
    seen = 0
    pending = [(root, "")]
    while pending:
        directory, prefix = pending.pop()
        with os.scandir(directory) as iterator:
            entries = sorted(iterator, key=lambda item: item.name)
        for entry in entries:
            seen += 1
            if seen > MAX_FILESYSTEM_NODES:
                raise SessionLayoutError("live_start_layout_node_limit")
            child = Path(entry.path)
            status = child.lstat()
            if status_is_reparse(status) or entry.is_symlink():
                raise SessionLayoutError("live_start_layout_reparse_forbidden")
            logical = f"{prefix}{entry.name}"
            if stat.S_ISDIR(status.st_mode):
                if logical not in allowed_directories:
                    raise SessionLayoutError(
                        "live_start_layout_directory_unbound"
                    )
                _validate_path_no_ads(
                    child,
                    status=status,
                    directory=True,
                )
                pending.append((child, f"{logical}/"))
                continue
            if logical in {
                "result/.summary.json.live-start-atomic.tmp",
                "result/.summary.md.live-start-atomic.tmp",
            } and logical not in allowed_reserved:
                raise SessionLayoutError(
                    "live_start_result_reserved_temp_unexpected"
                )
            if (
                not stat.S_ISREG(status.st_mode)
                or (
                    status.st_nlink != 1
                    and logical not in allowed_posix_two_link_files
                )
                or (
                    logical not in allowed_files
                    and logical not in allowed_reserved
                )
            ):
                raise SessionLayoutError("live_start_layout_file_unbound")
            _validate_path_no_ads(
                child,
                status=status,
                directory=False,
            )
            pending_cursor = session.pending_transition
            if (
                logical == "receipts/apply_invocation.json"
                and isinstance(pending_cursor, Mapping)
                and _pending_apply_invocation_receipt_is_layout_bound(
                    pending_cursor
                )
            ):
                successor_bindings = pending_cursor[
                    "successor_artifact_bindings"
                ]
                raw, _identity = _read_bound_file(
                    child,
                    expected_parent_identity=path_identity(child.parent),
                    maximum_size=APPLY_INVOCATION_MAX_BYTES,
                )
                if _bytes_sha256(raw) != successor_bindings[
                    "receipts/apply_invocation.json"
                ]:
                    raise SessionLayoutError(
                        "live_start_apply_invocation_receipt_unbound"
                    )
            if logical.startswith("result/.") and logical in allowed_reserved:
                result_reserved_seen += 1
                if result_reserved_seen > 1:
                    raise SessionLayoutError(
                        "live_start_result_reserved_temp_ambiguous"
                    )
            if (
                logical == "terminal-resolution-cleanup.json"
                and not _terminal_cleanup_final_permitted(session)
            ):
                raise SessionLayoutError(
                    "live_start_terminal_cleanup_inventory_unexpected"
                )


def _allowed_logical_run_files(
    *,
    root: Path,
    session: LiveStartSession,
) -> set[str]:
    allowed = {"session.json", *session.artifact_bindings.keys()}
    pending = session.pending_transition
    receipt_write_pending = (
        isinstance(pending, Mapping)
        and pending.get("operation")
        in {
            "install_package_validation",
            "install_prepublication_validation",
        }
    )
    if isinstance(pending, Mapping) and (
        pending.get("stage") in {"PRIMARY_APPLIED", "CLEANUP_DELETING"}
        or receipt_write_pending
    ):
        successor_bindings = pending.get("successor_artifact_bindings")
        if isinstance(successor_bindings, Mapping):
            if pending.get("operation") == "install_apply_invocation":
                if _pending_apply_invocation_receipt_is_layout_bound(
                    pending
                ):
                    allowed.add("receipts/apply_invocation.json")
            else:
                allowed.update(successor_bindings.keys())
    if session.result_intent is not None:
        allowed.update({"result/summary.json", "result/summary.md"})
    if _terminal_cleanup_final_permitted(session):
        allowed.add("terminal-resolution-cleanup.json")
    for external in _session_external_file_actions(session):
        if external.get("stage") != "STAGING_BOUND":
            continue
        final_path = external.get("final_path")
        if not isinstance(final_path, str):
            continue
        try:
            allowed.add(Path(final_path).relative_to(root).as_posix())
        except ValueError:
            pass
    return allowed


def _pending_apply_invocation_receipt_is_layout_bound(
    pending: Mapping[str, Any],
) -> bool:
    successor_bindings = pending.get("successor_artifact_bindings")
    return (
        pending.get("operation") == "install_apply_invocation"
        and pending.get("stage") == "PRIMARY_APPLIED"
        and pending.get("external_file_action") is None
        and pending.get("next_action_index") == 1
        and isinstance(successor_bindings, Mapping)
        and frozenset(successor_bindings)
        == _PHASE_MANDATORY_ARTIFACTS[LiveStartPhase.APPLY_STARTED]
        and isinstance(
            successor_bindings.get("receipts/apply_invocation.json"),
            str,
        )
        and _SHA256.fullmatch(
            successor_bindings["receipts/apply_invocation.json"]
        )
        is not None
    )


def _logical_parent_prefixes(logical: str) -> tuple[str, ...]:
    parts = logical.split("/")[:-1]
    return tuple("/".join(parts[:index]) for index in range(1, len(parts) + 1))


def _validate_authority_roots_no_ads(
    *,
    session_lease: LiveStartSessionLease,
) -> None:
    _validate_authority_root_paths_no_ads(
        root=session_lease.session_root,
        lock_path=session_lease.session_lock_path,
    )


def _validate_authority_root_paths_no_ads(
    *,
    root: Path,
    lock_path: Path,
) -> None:
    if os.name != "nt":
        return
    for path in (
        root.parent.parent,
        root.parent,
        lock_path.parent,
        root,
    ):
        status = path.lstat()
        _validate_path_no_ads(
            path,
            status=status,
            directory=stat.S_ISDIR(status.st_mode),
        )


def _validate_path_no_ads(
    path: Path,
    *,
    status: os.stat_result,
    directory: bool,
) -> None:
    if os.name != "nt":
        return
    try:
        require_no_alternate_data_streams(
            path,
            expected_identity=path_identity_from_status(status),
            expected_parent_identity=path_identity(path.parent),
            directory=directory,
            expected_size=None if directory else status.st_size,
        )
    except (OSError, ValueError) as error:
        raise SessionLayoutError(
            "live_start_layout_alternate_stream_forbidden"
        ) from error


def _allowed_reserved_run_paths(
    *,
    root: Path,
    session: LiveStartSession,
) -> frozenset[str]:
    allowed: set[str] = set()
    if (
        session.result_intent is not None
        and session.terminal_status is None
    ):
        allowed.update(
            {
                "result/.summary.json.live-start-atomic.tmp",
                "result/.summary.md.live-start-atomic.tmp",
            }
        )
    for external in _session_external_file_actions(session):
        stage = external.get("stage")
        names = [external.get("staging_path")]
        if stage == "PLANNED":
            names.append(external.get("inner_temp_path"))
        for name in names:
            if not isinstance(name, str):
                continue
            path = Path(name)
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                continue
            allowed.add(relative)
    return frozenset(allowed)


def _session_external_file_actions(
    session: LiveStartSession,
) -> tuple[Mapping[str, Any], ...]:
    actions: list[Mapping[str, Any]] = []
    for container in (
        session.pending_transition,
        session.apply_recovery,
    ):
        if isinstance(container, Mapping):
            external = container.get("external_file_action")
            if isinstance(external, Mapping):
                actions.append(external)
    retirement = session.terminal_retirement
    if isinstance(retirement, Mapping):
        resolution = retirement.get("terminal_resolution_evidence")
        if isinstance(resolution, Mapping):
            external = resolution.get("external_file_action")
            if isinstance(external, Mapping):
                actions.append(external)
    return tuple(actions)


def _terminal_cleanup_final_permitted(session: LiveStartSession) -> bool:
    retirement = session.terminal_retirement
    if not isinstance(retirement, Mapping):
        return False
    resolution = retirement.get("terminal_resolution_evidence")
    if not isinstance(resolution, Mapping):
        return False
    if resolution.get("cleanup_stage") in {
        "INVENTORY_BOUND",
        "CLEANING",
        "JOURNAL_RETIRED",
        "FENCE_RETIRED",
    }:
        return True
    external = resolution.get("external_file_action")
    return (
        resolution.get("cleanup_stage") == "PREPARED"
        and isinstance(external, Mapping)
        and external.get("stage") == "STAGING_BOUND"
    )


def _reconcile_session_temp_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession | None = None,
) -> None:
    _require_session_lease(session_lease)
    temp = session_lease.session_root / ".session.json.live-start-atomic.tmp"
    if not os.path.lexists(temp):
        return
    status = temp.lstat()
    identity = path_identity_from_status(status)
    if (
        not stat.S_ISREG(status.st_mode)
        or status_is_reparse(status)
        or status.st_nlink != 1
        or status.st_size > LIVE_START_SESSION_MAX_BYTES
    ):
        raise SessionLayoutError("live_start_session_reserved_temp_invalid")
    if os.name == "nt":
        require_no_alternate_data_streams(
            temp,
            expected_identity=identity,
            expected_parent_identity=session_lease.session_root_identity,
            directory=False,
            expected_size=status.st_size,
        )
    session_path = session_lease.session_root / "session.json"
    raw, current_identity = _read_bound_file(
        session_path,
        expected_parent_identity=session_lease.session_root_identity,
        maximum_size=LIVE_START_SESSION_MAX_BYTES,
    )
    _load_session_bytes(raw, session_identity=current_identity)
    if expected_session is not None and (
        raw != expected_session.canonical_json
        or current_identity != expected_session.session_identity
    ):
        # A successful reserved replace consumes the temp name.  Therefore a
        # remaining temp beside any non-predecessor session is unknown state,
        # never rollback authority.
        raise SessionConflictError("live_start_session_temp_state_invalid")
    secure_unlink(
        temp,
        expected_identity=identity,
        expected_parent_identity=session_lease.session_root_identity,
    )


def _canonical_json(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise SessionValidationError("live_start_json_invalid") from error


def _decode_json_document(raw: bytes) -> dict[str, Any]:
    if raw.startswith(b"\xef\xbb\xbf") or not raw.endswith(b"\n"):
        raise SessionValidationError("live_start_json_encoding_invalid")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SessionValidationError("live_start_json_duplicate_key")
            result[key] = value
        return result

    def reject_constant(_value: str) -> None:
        raise SessionValidationError("live_start_json_non_finite")

    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except SessionValidationError:
        raise
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ) as error:
        raise SessionValidationError("live_start_json_invalid") from error
    if not isinstance(value, dict):
        raise SessionValidationError("live_start_json_not_object")
    return value


def _decode_canonical_json(raw: bytes) -> dict[str, Any]:
    value = _decode_json_document(raw)
    if _canonical_json(value) != raw:
        raise SessionValidationError("live_start_json_not_canonical")
    return value


def _normalize_json(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise SessionValidationError("live_start_json_key_invalid")
            result[key] = _normalize_json(item)
        return result
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return [_normalize_json(item) for item in value]
    if value is None or type(value) in {str, int, float, bool}:
        if isinstance(value, float) and not __import__("math").isfinite(value):
            raise SessionValidationError("live_start_json_non_finite")
        return value
    raise SessionValidationError("live_start_json_value_invalid")


def _self_digest(unsigned: Mapping[str, Any]) -> str:
    return _bytes_sha256(_canonical_json(unsigned))


def _bytes_sha256(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(
        {
            key: _freeze_json(item)
            for key, item in sorted(value.items())
        }
    )


def _freeze_optional_mapping(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise SessionValidationError("live_start_nested_object_invalid")
    return _freeze_mapping(value)


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return tuple(_freeze_json(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _require_run_id(value: Any) -> str:
    if not isinstance(value, str) or _RUN_ID.fullmatch(value) is None:
        raise SessionValidationError("live_start_run_id_invalid")
    return value


def _require_sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise SessionValidationError(f"live_start_{name}_invalid")
    return value


def _require_deck_name(value: Any) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 128
        or any(ord(character) < 0x20 for character in value)
    ):
        raise SessionValidationError("live_start_deck_name_invalid")
    return value


def _bounded_integer(value: Any, minimum: int, maximum: int, name: str) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise SessionValidationError(f"live_start_{name}_invalid")
    return value


def _require_identity(value: Any, name: str) -> PathIdentity:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 3
        or any(type(item) is not int or item < 0 for item in value)
    ):
        raise SessionValidationError(f"live_start_{name}_invalid")
    return value[0], value[1], value[2]


def _require_absolute_path(value: Any, name: str) -> Path:
    if not isinstance(value, str):
        raise SessionValidationError(f"live_start_{name}_invalid")
    path = Path(value)
    if not path.is_absolute() or str(path.absolute()) != value:
        raise SessionValidationError(f"live_start_{name}_invalid")
    return path


RuntimeApplyRecoveryAction = Literal[
    "observe_not_committed",
    "materialize_file_action_staging",
    "retire_unbound_file_action_staging",
    "commit_bound_initial_attempt_record",
    "commit_bound_candidate_planned_attempt_record",
    "commit_bound_prior_owner_planned_attempt_record",
    "advance_controller_transaction_journal_write",
    "promote_legacy_uuid_transaction_temp",
    "retire_legacy_uuid_transaction_temp",
    "bind_created_candidate",
    "bind_candidate_fence",
    "commit_bound_prior_owner_attempt_record",
    "materialize_candidate_tree_entry",
    "verify_candidate_tree",
    "rename_candidate_to_target",
    "bind_renamed_target",
    "write_deck_config_ini",
    "commit_ini_journal",
    "write_runtime_state",
    "commit_state_journal",
    "write_last_apply_receipt",
    "finalize_journal",
    "finalize_attempt_record",
    "commit_owner_retirement_prepared",
    "initialize_owner_cleanup_journal",
    "delete_owner_cleanup_entry",
    "advance_owner_cleanup_journal",
    "retire_owner_target_root",
    "commit_owner_retirement_completed",
    "retire_old_owner_journal",
    "observe_owner_retirement_completed",
    "observe_committed",
    "observe_pending",
    "observe_unknown",
]
RUNTIME_APPLY_RECOVERY_ACTIONS = (
    "observe_not_committed",
    "materialize_file_action_staging",
    "retire_unbound_file_action_staging",
    "commit_bound_initial_attempt_record",
    "commit_bound_candidate_planned_attempt_record",
    "commit_bound_prior_owner_planned_attempt_record",
    "advance_controller_transaction_journal_write",
    "promote_legacy_uuid_transaction_temp",
    "retire_legacy_uuid_transaction_temp",
    "bind_created_candidate",
    "bind_candidate_fence",
    "commit_bound_prior_owner_attempt_record",
    "materialize_candidate_tree_entry",
    "verify_candidate_tree",
    "rename_candidate_to_target",
    "bind_renamed_target",
    "write_deck_config_ini",
    "commit_ini_journal",
    "write_runtime_state",
    "commit_state_journal",
    "write_last_apply_receipt",
    "finalize_journal",
    "finalize_attempt_record",
    "commit_owner_retirement_prepared",
    "initialize_owner_cleanup_journal",
    "delete_owner_cleanup_entry",
    "advance_owner_cleanup_journal",
    "retire_owner_target_root",
    "commit_owner_retirement_completed",
    "retire_old_owner_journal",
    "observe_owner_retirement_completed",
    "observe_committed",
    "observe_pending",
    "observe_unknown",
)
RUNTIME_TERMINAL_OBSERVATION_ACTIONS = frozenset(
    {"observe_not_committed", "observe_pending", "observe_unknown"}
)
NONTERMINAL_PURE_TRANSITIONS = frozenset(
    {
        "select_terminal_classification",
        "apply_committed",
        "runtime_matched",
        "recovery_closed",
    }
)
RUNTIME_LAYOUT_BOOTSTRAP_ACTIONS = frozenset(
    {"create_or_confirm_runtime_layout_directory"}
)
OUTPUT_OPERATION_ADMISSION_ACTIONS = frozenset(
    {
        "materialize_output_operation_admission_staging",
        "commit_bound_output_operation_admission",
        "retire_unbound_output_operation_admission_staging",
    }
)
RUNTIME_ADMISSION_ACTIONS = frozenset(
    {
        "materialize_runtime_admission_staging",
        "commit_bound_runtime_admission",
        "retire_unbound_runtime_admission_staging",
        "materialize_invocation_receipt_staging",
        "commit_bound_invocation_receipt",
        "retire_unbound_invocation_receipt_staging",
    }
)
OUTPUT_CHILD_BOOTSTRAP_ACTIONS = frozenset(
    {
        "materialize_claim_staging",
        "commit_bound_claim",
        "retire_unbound_claim_staging",
        "bind_existing_child",
        "create_output_child",
        "retire_claim",
        "confirm_claim_absent_and_current_exact",
    }
)
CANDIDATE_REVIEW_REVISION_ACTIONS = frozenset(
    {
        "retire_unbound_review_revision_staging",
        "materialize_review_revision_staging",
        "restore_review_revision_predecessor",
        "commit_bound_review_revision_request",
        "retire_candidate_validation_receipt",
    }
)
TERMINAL_RESOLUTION_PHYSICAL_ACTIONS = frozenset(RUNTIME_APPLY_RECOVERY_ACTIONS) | {
    "physical_recovery_advanced",
    "retire_unbound_terminal_cleanup_inventory_staging",
    "materialize_terminal_cleanup_inventory_staging",
    "commit_bound_terminal_cleanup_inventory",
    "delete_cleanup_entry",
    "retire_cleanup_journal",
    "retire_cleanup_fence",
    "retire_cleanup_inventory",
    "retire_ack_journal",
    "retire_ack_fence",
}
NEW_TARGET_ACTION_ORDER = (
    "commit_bound_initial_attempt_record",
    "commit_bound_candidate_planned_attempt_record",
    "advance_controller_transaction_journal_write",
    "bind_created_candidate",
    "bind_candidate_fence",
    "materialize_candidate_tree_entry",
    "verify_candidate_tree",
    "rename_candidate_to_target",
    "bind_renamed_target",
    "write_deck_config_ini",
    "commit_ini_journal",
    "write_runtime_state",
    "commit_state_journal",
    "write_last_apply_receipt",
    "finalize_journal",
    "finalize_attempt_record",
)
OWNER_RETIREMENT_ACTION_ORDER = (
    "commit_owner_retirement_prepared",
    "initialize_owner_cleanup_journal",
    "delete_owner_cleanup_entry",
    "advance_owner_cleanup_journal",
    "retire_owner_target_root",
    "commit_owner_retirement_completed",
    "retire_old_owner_journal",
    "observe_owner_retirement_completed",
)
OWNER_RETIREMENT_STAGES = (
    "PREPARED_PLANNED",
    "PREPARED",
    "CLEANING",
    "TARGET_RETIRED",
    "COMPLETED",
    "OWNER_RETIRED",
)

RuntimeObservationFamily = Literal[
    "first_install",
    "nonterminal_apply",
    "terminal_resolution",
    "terminal_classification",
    "terminal_release",
]
RUNTIME_OBSERVATION_FAMILIES = frozenset(
    {
        "first_install",
        "nonterminal_apply",
        "terminal_resolution",
        "terminal_classification",
        "terminal_release",
    }
)


@dataclass(frozen=True, slots=True)
class RuntimeApplyRecoveryEvidence:
    value: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "value",
            _validate_apply_recovery_document(self.value),
        )

    @property
    def content_sha256(self) -> str:
        value = _thaw(self.value)
        claimed = value.get("content_sha256")
        if isinstance(claimed, str) and _SHA256.fullmatch(claimed):
            return claimed
        return _bytes_sha256(_canonical_json(value))


@dataclass(frozen=True, slots=True)
class TerminalResolutionEvidence:
    value: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "value",
            _validate_terminal_resolution_document(self.value),
        )


@dataclass(frozen=True, slots=True)
class RuntimeLayoutBootstrapEvidence:
    value: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "value",
            validate_embedded_document(
                "runtime_layout_bootstrap",
                self.value,
            ),
        )


@dataclass(frozen=True, slots=True)
class OwnerRetirementEvidence:
    value: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "value",
            _validate_owner_retirement_document(self.value),
        )


@dataclass(frozen=True, slots=True)
class TerminalResolutionCleanupInventory:
    value: Mapping[str, Any]
    canonical_json: bytes = field(init=False, repr=False)

    def __post_init__(self) -> None:
        normalized, canonical_json = _validate_terminal_cleanup_inventory_document(
            self.value
        )
        object.__setattr__(self, "value", normalized)
        object.__setattr__(self, "canonical_json", canonical_json)

    @property
    def size(self) -> int:
        return len(self.canonical_json)

    @property
    def sha256(self) -> str:
        return _bytes_sha256(self.canonical_json)


@dataclass(frozen=True, slots=True)
class TerminalCleanupInventoryPublishStep:
    action: Literal["materialize", "commit"]
    staging: MaterializedStagingBytes | None
    published: PublishedNoReplaceBytes | None
    step_receipt: TerminalResolutionStepReceipt

    def __post_init__(self) -> None:
        if self.action == "materialize":
            valid_result = self.staging is not None and self.published is None
        elif self.action == "commit":
            valid_result = self.staging is None and self.published is not None
        else:
            valid_result = False
        if not valid_result:
            raise SessionValidationError(
                "live_start_terminal_cleanup_publish_result_invalid"
            )
        if not isinstance(self.step_receipt, TerminalResolutionStepReceipt):
            raise SessionValidationError(
                "live_start_terminal_cleanup_publish_receipt_invalid"
            )


@dataclass(frozen=True, slots=True)
class TerminalCleanupInventoryRetireStep:
    action: Literal["unbound_staging", "final_sidecar"]
    object_was_already_absent: bool
    step_receipt: TerminalResolutionStepReceipt

    def __post_init__(self) -> None:
        if self.action not in {"unbound_staging", "final_sidecar"}:
            raise SessionValidationError(
                "live_start_terminal_cleanup_retire_action_invalid"
            )
        if type(self.object_was_already_absent) is not bool:
            raise SessionValidationError(
                "live_start_terminal_cleanup_retire_absence_invalid"
            )
        if not isinstance(self.step_receipt, TerminalResolutionStepReceipt):
            raise SessionValidationError(
                "live_start_terminal_cleanup_retire_receipt_invalid"
            )


@dataclass(frozen=True, slots=True)
class _PhysicalPostcondition:
    action: str
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.action, str) or not self.action:
            raise SessionValidationError("live_start_physical_postcondition_action_invalid")
        object.__setattr__(self, "evidence", _freeze_mapping(self.evidence))


@dataclass(frozen=True, slots=True)
class RuntimeApplyRecoveryPhysicalPostcondition(_PhysicalPostcondition):
    pass


@dataclass(frozen=True, slots=True)
class TerminalResolutionPhysicalPostcondition(_PhysicalPostcondition):
    pass


@dataclass(frozen=True, slots=True)
class SuccessAckStepEvidence(_PhysicalPostcondition):
    pass


@dataclass(frozen=True, slots=True)
class RuntimeObservationPostcondition(_PhysicalPostcondition):
    observation_family: str = ""

    def __post_init__(self) -> None:
        super(RuntimeObservationPostcondition, self).__post_init__()
        if self.observation_family not in RUNTIME_OBSERVATION_FAMILIES:
            raise SessionValidationError("live_start_runtime_observation_family_invalid")


@dataclass(frozen=True, slots=True)
class RuntimeLayoutBootstrapPhysicalPostcondition(_PhysicalPostcondition):
    pass


@dataclass(frozen=True, slots=True)
class RuntimeAdmissionPhysicalPostcondition(_PhysicalPostcondition):
    pass


@dataclass(frozen=True, slots=True)
class OutputOperationAdmissionPhysicalPostcondition(_PhysicalPostcondition):
    pass


@dataclass(frozen=True, slots=True)
class OutputChildBootstrapPhysicalPostcondition(_PhysicalPostcondition):
    pass


@dataclass(frozen=True, slots=True)
class CandidateReviewRevisionPhysicalPostcondition(_PhysicalPostcondition):
    pass


def _physical_postcondition_value_sha256(value: Any) -> str | None:
    try:
        if isinstance(value, _PhysicalPostcondition):
            observation_family = (
                value.observation_family
                if isinstance(value, RuntimeObservationPostcondition)
                else None
            )
            canonical_value = {
                "type_module": type(value).__module__,
                "type_qualname": type(value).__qualname__,
                "action": value.action,
                "observation_family": observation_family,
                "evidence": _normalize_json(value.evidence),
            }
        elif type(value) is _RuntimeAdmissionReleasePrecondition:
            canonical_value = {
                "type_module": type(value).__module__,
                "type_qualname": type(value).__qualname__,
                "admission_path": str(value.admission_path),
                "admission_parent_identity": list(
                    value.admission_parent_identity
                ),
                "historical_admission_identity": list(
                    value.historical_admission_identity
                ),
                "historical_admission_sha256": (
                    value.historical_admission_sha256
                ),
            }
        else:
            return None
        return _bytes_sha256(_canonical_json(canonical_value))
    except (
        AttributeError,
        RecursionError,
        SessionValidationError,
        TypeError,
        ValueError,
    ):
        return None


RuntimeAdmissionReleaseDisposition = Literal[
    "old_unlinked", "already_absent", "valid_foreign_successor"
]


@dataclass(frozen=True, slots=True)
class RuntimeAdmissionReleasePostcondition:
    admission_path: Path
    admission_parent_identity: PathIdentity
    historical_admission_identity: PathIdentity
    historical_admission_sha256: str
    disposition: RuntimeAdmissionReleaseDisposition
    foreign_successor_identity: PathIdentity | None
    foreign_successor_sha256: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.admission_path, Path) or not self.admission_path.is_absolute():
            raise SessionValidationError(
                "live_start_runtime_admission_release_path_invalid"
            )
        _require_identity(
            self.admission_parent_identity,
            "runtime_admission_release_parent_identity",
        )
        _require_identity(
            self.historical_admission_identity,
            "historical_admission_identity",
        )
        _require_sha256(
            self.historical_admission_sha256,
            "historical_admission_sha256",
        )
        if self.disposition not in {
            "old_unlinked",
            "already_absent",
            "valid_foreign_successor",
        }:
            raise SessionValidationError("live_start_runtime_admission_release_invalid")
        if self.disposition == "valid_foreign_successor":
            _require_identity(self.foreign_successor_identity, "foreign_successor_identity")
            _require_sha256(self.foreign_successor_sha256, "foreign_successor_sha256")
            if self.foreign_successor_identity == self.historical_admission_identity:
                raise SessionValidationError("live_start_runtime_admission_foreign_identity_invalid")
        elif self.foreign_successor_identity is not None or self.foreign_successor_sha256 is not None:
            raise SessionValidationError("live_start_runtime_admission_release_nullability_invalid")


@dataclass(frozen=True, slots=True)
class _RuntimeAdmissionReleasePrecondition:
    admission_path: Path
    admission_parent_identity: PathIdentity
    historical_admission_identity: PathIdentity
    historical_admission_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.admission_path, Path)
            or not self.admission_path.is_absolute()
        ):
            raise SessionValidationError(
                "live_start_runtime_admission_release_path_invalid"
            )
        _require_identity(
            self.admission_parent_identity,
            "runtime_admission_release_parent_identity",
        )
        _require_identity(
            self.historical_admission_identity,
            "historical_admission_identity",
        )
        _require_sha256(
            self.historical_admission_sha256,
            "historical_admission_sha256",
        )


def _detached_registered_postcondition(
    value: Any,
) -> _PhysicalPostcondition | _RuntimeAdmissionReleasePrecondition | None:
    if isinstance(value, RuntimeObservationPostcondition):
        return type(value)(
            action=value.action,
            evidence=_thaw(value.evidence),
            observation_family=value.observation_family,
        )
    if isinstance(value, _PhysicalPostcondition):
        return type(value)(
            action=value.action,
            evidence=_thaw(value.evidence),
        )
    if type(value) is _RuntimeAdmissionReleasePrecondition:
        return _RuntimeAdmissionReleasePrecondition(
            admission_path=Path(str(value.admission_path)),
            admission_parent_identity=tuple(value.admission_parent_identity),
            historical_admission_identity=tuple(
                value.historical_admission_identity
            ),
            historical_admission_sha256=str(
                value.historical_admission_sha256
            ),
        )
    return None


class _OpaqueBearer:
    __slots__ = (
        "active",
        "action",
        "cursor_sha256",
        "family",
        "nonce",
        "physical_slot_family",
        "physical_precondition",
        "session_bearer",
        "terminal_owner_context",
        "thread_id",
        "successor",
    )

    def __init__(
        self,
        *,
        session_bearer: _SessionBearer,
        family: str,
        cursor_sha256: str,
        action: str,
    ) -> None:
        self.active = True
        self.action = action
        self.cursor_sha256 = cursor_sha256
        self.family = family
        self.nonce = secrets.token_hex(32)
        self.physical_slot_family: str | None = None
        self.physical_precondition: Mapping[str, Any] | None = None
        self.session_bearer = session_bearer
        self.terminal_owner_context: Mapping[str, Any] | None = None
        self.thread_id = threading.get_ident()
        self.successor: Any = None


@dataclass(frozen=True, slots=True)
class _OpaqueBearerRegistration:
    bearer: _OpaqueBearer
    session_bearer: _SessionBearer
    family: str
    cursor_sha256: str
    action: str
    thread_id: int
    nonce: str
    physical_slot_family: str | None
    registered_successor: Any
    registered_successor_snapshot: Any
    registered_successor_postcondition_sha256: str | None
    registered_physical_precondition: Mapping[str, Any] | None
    registered_terminal_owner_context: Mapping[str, Any] | None
    parent_terminal_bearer: _OpaqueBearer | None
    parent_registration: _OpaqueBearerRegistration | None


@dataclass(frozen=True, slots=True)
class _OpaqueBearerConsumption:
    bearer: _OpaqueBearer
    registration: _OpaqueBearerRegistration
    session_bearer: _SessionBearer
    family: str
    cursor_sha256: str
    action: str
    thread_id: int
    successor: Any
    successor_postcondition_sha256: str | None
    successor_was_registry_bound: bool
    physical_precondition: Mapping[str, Any] | None
    terminal_owner_context: Mapping[str, Any] | None
    parent_terminal_bearer: _OpaqueBearer | None
    parent_registration: _OpaqueBearerRegistration | None


@dataclass(frozen=True, slots=True)
class _TerminalOwnerlessIssuerBinding:
    issuer_bearer: _OpaqueBearer
    physical_action: Callable[..., Any]
    physical_precondition: Mapping[str, Any]
    parent_terminal_bearer: _OpaqueBearer
    parent_registration: _OpaqueBearerRegistration


@dataclass(frozen=True, slots=True)
class _TerminalOwnerContextBinding:
    bearer: _OpaqueBearer
    registration: _OpaqueBearerRegistration
    context: Mapping[str, Any] | None


_OPAQUE_MINT = object()


@dataclass(frozen=True, slots=True, init=False)
class _OpaqueCarrier:
    _opaque: _OpaqueBearer = field(repr=False, compare=False)

    def __new__(cls, _mint: object | None = None):
        if _mint is not _OPAQUE_MINT:
            raise TypeError("live_start_capability_nonconstructible")
        return object.__new__(cls)

    @classmethod
    def _mint(cls, bearer: _OpaqueBearer):
        carrier = object.__new__(cls)
        object.__setattr__(carrier, "_opaque", bearer)
        return carrier

    def __copy__(self):
        copied = object.__new__(type(self))
        object.__setattr__(copied, "_opaque", self._opaque)
        _register_opaque_carrier_copy(source=self, copied=copied)
        return copied

    def __deepcopy__(self, _memo: dict[int, Any]):
        return copy(self)

    def __reduce__(self) -> None:
        raise TypeError("live_start_capability_nonserializable")


@dataclass(frozen=True, slots=True, init=False)
class TerminalRetirementAuthorization(_OpaqueCarrier):
    pass


@dataclass(frozen=True, slots=True, init=False)
class TerminalOwnerlessSuccessorIssuer(_OpaqueCarrier):
    pass


@dataclass(frozen=True, slots=True, init=False)
class RuntimeAttemptRecoveryAuthorization(_OpaqueCarrier):
    pass


@dataclass(frozen=True, slots=True, init=False)
class RuntimeObservationAuthorization(_OpaqueCarrier):
    pass


@dataclass(frozen=True, slots=True, init=False)
class RuntimeLayoutBootstrapAuthorization(_OpaqueCarrier):
    pass


@dataclass(frozen=True, slots=True, init=False)
class RuntimeAdmissionAuthorization(_OpaqueCarrier):
    pass


@dataclass(frozen=True, slots=True, init=False)
class OutputOperationAdmissionAuthorization(_OpaqueCarrier):
    pass


@dataclass(frozen=True, slots=True, init=False)
class OutputOperationAdmissionReleaseAuthorization(_OpaqueCarrier):
    pass


@dataclass(frozen=True, slots=True, init=False)
class OutputChildBootstrapAuthorization(_OpaqueCarrier):
    pass


@dataclass(frozen=True, slots=True, init=False)
class CandidateReviewRevisionAuthorization(_OpaqueCarrier):
    pass


@dataclass(frozen=True, slots=True, init=False)
class TerminalResolutionStepReceipt(_OpaqueCarrier):
    pass


@dataclass(frozen=True, slots=True, init=False)
class ApplyRecoveryStepReceipt(_OpaqueCarrier):
    pass


@dataclass(frozen=True, slots=True, init=False)
class RuntimeObservationReceipt(_OpaqueCarrier):
    pass


@dataclass(frozen=True, slots=True, init=False)
class RuntimeLayoutBootstrapStepReceipt(_OpaqueCarrier):
    pass


@dataclass(frozen=True, slots=True, init=False)
class RuntimeAdmissionStepReceipt(_OpaqueCarrier):
    pass


@dataclass(frozen=True, slots=True, init=False)
class OutputOperationAdmissionStepReceipt(_OpaqueCarrier):
    pass


@dataclass(frozen=True, slots=True, init=False)
class OutputChildBootstrapStepReceipt(_OpaqueCarrier):
    pass


@dataclass(frozen=True, slots=True, init=False)
class CandidateReviewRevisionStepReceipt(_OpaqueCarrier):
    pass


_ACTIVE_OPAQUE_BEARERS: dict[int, _OpaqueBearer] = {}
_OPAQUE_BEARER_REGISTRATIONS: dict[
    int,
    _OpaqueBearerRegistration,
] = {}
_ACTIVE_OPAQUE_CARRIERS: dict[
    int,
    tuple[_OpaqueCarrier, _OpaqueBearer],
] = {}
_BOUND_PHYSICAL_POSTCONDITIONS: dict[
    int,
    _PhysicalPostcondition | _RuntimeAdmissionReleasePrecondition,
] = {}
_BOUND_TERMINAL_OWNERLESS_ISSUERS: dict[
    int,
    _TerminalOwnerlessIssuerBinding,
] = {}
_ACTIVE_TERMINAL_OWNERLESS_ISSUER_BY_PARENT: dict[
    int,
    _OpaqueBearer,
] = {}
_BOUND_TERMINAL_OWNER_CONTEXTS: dict[
    int,
    _TerminalOwnerContextBinding,
] = {}
_ACTIVE_TERMINAL_PHYSICAL_SLOTS: dict[
    tuple[int, str, str, str],
    _OpaqueBearer,
] = {}
_TERMINAL_PHYSICAL_SLOT_BY_BEARER: dict[
    int,
    tuple[int, str, str, str],
] = {}
_ACTIVE_NONTERMINAL_PHYSICAL_SLOTS: dict[
    tuple[int, str, str, str],
    _OpaqueBearer,
] = {}
_NONTERMINAL_PHYSICAL_SLOT_BY_BEARER: dict[
    int,
    tuple[int, str, str, str],
] = {}


def _terminal_physical_slot_key(
    bearer: _OpaqueBearer,
) -> tuple[int, str, str, str]:
    return (
        id(bearer.session_bearer),
        "terminal_retirement",
        bearer.cursor_sha256,
        bearer.action,
    )


def _terminal_physical_cursor_slot_is_claimed(
    *,
    session_bearer: _SessionBearer,
    cursor_sha256: str,
) -> bool:
    with _AUTHORITY_REGISTRY_LOCK:
        return any(
            key[0] == id(session_bearer)
            and key[1] == "terminal_retirement"
            and key[2] == cursor_sha256
            for key in _ACTIVE_TERMINAL_PHYSICAL_SLOTS
        )


def _require_terminal_physical_cursor_slot_available(
    *,
    session_bearer: _SessionBearer,
    cursor_sha256: str,
) -> None:
    if _terminal_physical_cursor_slot_is_claimed(
        session_bearer=session_bearer,
        cursor_sha256=cursor_sha256,
    ):
        raise SessionCapabilityError(
            "live_start_terminal_physical_authorization_outstanding"
        )


def _terminal_physical_slot_is_consistent(
    *, bearer: _OpaqueBearer
) -> bool:
    if (
        bearer.action not in TERMINAL_RESOLUTION_PHYSICAL_ACTIONS
        or bearer.family
        not in {"terminal_retirement", "terminal_retirement_receipt"}
    ):
        return True
    key = _TERMINAL_PHYSICAL_SLOT_BY_BEARER.get(id(bearer))
    return (
        key == _terminal_physical_slot_key(bearer)
        and _ACTIVE_TERMINAL_PHYSICAL_SLOTS.get(key) is bearer
    )


def _release_terminal_physical_slot(*, bearer: _OpaqueBearer) -> None:
    with _AUTHORITY_REGISTRY_LOCK:
        key = _TERMINAL_PHYSICAL_SLOT_BY_BEARER.pop(id(bearer), None)
        if key is None:
            candidate_key = _terminal_physical_slot_key(bearer)
            if (
                _ACTIVE_TERMINAL_PHYSICAL_SLOTS.get(candidate_key)
                is bearer
            ):
                key = candidate_key
        if (
            key is not None
            and _ACTIVE_TERMINAL_PHYSICAL_SLOTS.get(key) is bearer
        ):
            del _ACTIVE_TERMINAL_PHYSICAL_SLOTS[key]


def _nonterminal_physical_slot_key(
    bearer: _OpaqueBearer,
) -> tuple[int, str, str, str]:
    return (
        id(bearer.session_bearer),
        "nonterminal_apply_recovery",
        bearer.cursor_sha256,
        bearer.action,
    )


def _nonterminal_physical_cursor_slot_is_claimed(
    *,
    session_bearer: _SessionBearer,
    cursor_sha256: str,
) -> bool:
    with _AUTHORITY_REGISTRY_LOCK:
        return any(
            key[0] == id(session_bearer)
            and key[1] == "nonterminal_apply_recovery"
            and key[2] == cursor_sha256
            for key in _ACTIVE_NONTERMINAL_PHYSICAL_SLOTS
        )


def _require_nonterminal_physical_cursor_slot_available(
    *,
    session_bearer: _SessionBearer,
    cursor_sha256: str,
) -> None:
    if _nonterminal_physical_cursor_slot_is_claimed(
        session_bearer=session_bearer,
        cursor_sha256=cursor_sha256,
    ):
        raise SessionConflictError(
            "live_start_nonterminal_physical_authorization_outstanding"
        )


def _nonterminal_physical_slot_is_consistent(
    *, bearer: _OpaqueBearer
) -> bool:
    if bearer.physical_slot_family != "nonterminal":
        return True
    if (
        bearer.action not in RUNTIME_APPLY_RECOVERY_ACTIONS
        or bearer.family
        not in {
            "nonterminal_apply_recovery",
            "nonterminal_apply_recovery_receipt",
        }
    ):
        return False
    key = _NONTERMINAL_PHYSICAL_SLOT_BY_BEARER.get(id(bearer))
    return (
        key == _nonterminal_physical_slot_key(bearer)
        and _ACTIVE_NONTERMINAL_PHYSICAL_SLOTS.get(key) is bearer
    )


def _release_nonterminal_physical_slot(*, bearer: _OpaqueBearer) -> None:
    with _AUTHORITY_REGISTRY_LOCK:
        key = _NONTERMINAL_PHYSICAL_SLOT_BY_BEARER.pop(
            id(bearer), None
        )
        if key is None:
            candidate_key = _nonterminal_physical_slot_key(bearer)
            if (
                _ACTIVE_NONTERMINAL_PHYSICAL_SLOTS.get(candidate_key)
                is bearer
            ):
                key = candidate_key
        if (
            key is not None
            and _ACTIVE_NONTERMINAL_PHYSICAL_SLOTS.get(key) is bearer
        ):
            del _ACTIVE_NONTERMINAL_PHYSICAL_SLOTS[key]


def _freeze_terminal_owner_context_for_registration(
    *,
    bearer: _OpaqueBearer,
    context: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    if context is None:
        return None
    if (
        bearer.family != "terminal_retirement"
        or bearer.action != "physical_recovery_advanced"
    ):
        raise SessionCapabilityError(
            "live_start_terminal_owner_capability_invalid"
        )
    frozen = _freeze_mapping(context)
    owner_action = frozen.get("owner_action")
    ownerless = frozen.get("ownerless")
    object_preexisting = frozen.get("owner_object_preexisting")
    if (
        not isinstance(owner_action, str)
        or set(frozen)
        not in (
            {"owner_action"},
            {"owner_action", "owner_object_preexisting"},
            {"ownerless", "owner_action"},
        )
        or (
            "owner_object_preexisting" in frozen
            and type(object_preexisting) is not bool
        )
        or ("ownerless" in frozen and ownerless is not True)
    ):
        raise SessionCapabilityError(
            "live_start_terminal_owner_capability_invalid"
        )
    return frozen


def _mint_registered_opaque_carrier(
    *,
    carrier_type: type[_AuthorizationT],
    bearer: _OpaqueBearer,
    claim_terminal_slot: bool = False,
    terminal_slot_source: _OpaqueBearer | None = None,
    claim_nonterminal_slot: bool = False,
    nonterminal_slot_source: _OpaqueBearer | None = None,
    ownerless_parent_terminal_bearer: _OpaqueBearer | None = None,
    terminal_owner_context: Mapping[str, Any] | None = None,
) -> _AuthorizationT:
    if not _session_context_is_registered(bearer=bearer.session_bearer):
        raise SessionCapabilityError(
            "live_start_physical_capability_session_forged"
        )
    registered_terminal_owner_context = (
        _freeze_terminal_owner_context_for_registration(
            bearer=bearer,
            context=terminal_owner_context,
        )
    )
    bearer.terminal_owner_context = registered_terminal_owner_context
    carrier = carrier_type._mint(bearer)
    with _AUTHORITY_REGISTRY_LOCK:
        if id(bearer) in _ACTIVE_OPAQUE_BEARERS:
            raise SessionCapabilityError(
                "live_start_physical_capability_registry_conflict"
            )
        terminal_slot_key: tuple[int, str, str, str] | None = None
        if claim_terminal_slot:
            terminal_slot_key = _terminal_physical_slot_key(bearer)
            _require_terminal_physical_cursor_slot_available(
                session_bearer=bearer.session_bearer,
                cursor_sha256=bearer.cursor_sha256,
            )
        elif terminal_slot_source is not None:
            terminal_slot_key = _TERMINAL_PHYSICAL_SLOT_BY_BEARER.get(
                id(terminal_slot_source)
            )
            if (
                terminal_slot_key is None
                or terminal_slot_key != _terminal_physical_slot_key(bearer)
                or _ACTIVE_TERMINAL_PHYSICAL_SLOTS.get(terminal_slot_key)
                is not terminal_slot_source
            ):
                raise SessionCapabilityError(
                    "live_start_terminal_physical_authorization_invalid"
                )
        nonterminal_slot_key: tuple[int, str, str, str] | None = None
        if claim_nonterminal_slot:
            nonterminal_slot_key = _nonterminal_physical_slot_key(bearer)
            _require_nonterminal_physical_cursor_slot_available(
                session_bearer=bearer.session_bearer,
                cursor_sha256=bearer.cursor_sha256,
            )
        elif nonterminal_slot_source is not None:
            nonterminal_slot_key = (
                _NONTERMINAL_PHYSICAL_SLOT_BY_BEARER.get(
                    id(nonterminal_slot_source)
                )
            )
            if (
                nonterminal_slot_key is None
                or nonterminal_slot_key
                != _nonterminal_physical_slot_key(bearer)
                or _ACTIVE_NONTERMINAL_PHYSICAL_SLOTS.get(
                    nonterminal_slot_key
                )
                is not nonterminal_slot_source
            ):
                raise SessionCapabilityError(
                    "live_start_nonterminal_physical_authorization_invalid"
                )
        ownerless_issuer = (
            bearer.family == "terminal_ownerless_successor_issuer"
        )
        parent_registration: _OpaqueBearerRegistration | None = None
        if ownerless_issuer:
            parent = ownerless_parent_terminal_bearer
            if (
                parent is None
                or not callable(bearer.successor)
                or not isinstance(bearer.physical_precondition, Mapping)
            ):
                raise SessionCapabilityError(
                    "live_start_terminal_ownerless_issuer_invalid"
                )
            parent_registration = _OPAQUE_BEARER_REGISTRATIONS.get(
                id(parent)
            )
            if (
                _ACTIVE_OPAQUE_BEARERS.get(id(parent)) is not parent
                or parent_registration is None
                or parent_registration.bearer is not parent
                or not _opaque_bearer_registration_matches(parent)
                or not _terminal_physical_slot_is_consistent(bearer=parent)
                or id(parent)
                in _ACTIVE_TERMINAL_OWNERLESS_ISSUER_BY_PARENT
            ):
                raise SessionCapabilityError(
                    "live_start_terminal_ownerless_issuer_invalid"
                )
        elif ownerless_parent_terminal_bearer is not None:
            raise SessionCapabilityError(
                "live_start_terminal_ownerless_issuer_invalid"
            )
        if nonterminal_slot_key is not None:
            bearer.physical_slot_family = "nonterminal"
        registered_successor_snapshot = _detached_registered_postcondition(
            bearer.successor
        )
        registered_successor_postcondition_sha256 = (
            _physical_postcondition_value_sha256(bearer.successor)
        )
        if (
            isinstance(
                bearer.successor,
                (_PhysicalPostcondition, _RuntimeAdmissionReleasePrecondition),
            )
            and (
                registered_successor_postcondition_sha256 is None
                or registered_successor_snapshot is None
                or _physical_postcondition_value_sha256(
                    registered_successor_snapshot
                )
                != registered_successor_postcondition_sha256
            )
        ):
            raise SessionCapabilityError(
                "live_start_physical_postcondition_invalid"
            )
        registration = _OpaqueBearerRegistration(
            bearer=bearer,
            session_bearer=bearer.session_bearer,
            family=bearer.family,
            cursor_sha256=bearer.cursor_sha256,
            action=bearer.action,
            thread_id=bearer.thread_id,
            nonce=bearer.nonce,
            physical_slot_family=bearer.physical_slot_family,
            registered_successor=bearer.successor,
            registered_successor_snapshot=registered_successor_snapshot,
            registered_successor_postcondition_sha256=(
                registered_successor_postcondition_sha256
            ),
            registered_physical_precondition=bearer.physical_precondition,
            registered_terminal_owner_context=(
                registered_terminal_owner_context
            ),
            parent_terminal_bearer=ownerless_parent_terminal_bearer,
            parent_registration=parent_registration,
        )
        _ACTIVE_OPAQUE_BEARERS[id(bearer)] = bearer
        _OPAQUE_BEARER_REGISTRATIONS[id(bearer)] = registration
        _ACTIVE_OPAQUE_CARRIERS[id(carrier)] = (carrier, bearer)
        if (
            bearer.family == "terminal_retirement"
            and bearer.action == "physical_recovery_advanced"
        ):
            _BOUND_TERMINAL_OWNER_CONTEXTS[id(bearer)] = (
                _TerminalOwnerContextBinding(
                    bearer=bearer,
                    registration=registration,
                    context=registered_terminal_owner_context,
                )
            )
        if isinstance(
            bearer.successor,
            (_PhysicalPostcondition, _RuntimeAdmissionReleasePrecondition),
        ):
            _BOUND_PHYSICAL_POSTCONDITIONS[id(bearer)] = (
                bearer.successor
            )
        if ownerless_issuer:
            assert ownerless_parent_terminal_bearer is not None
            assert parent_registration is not None
            assert bearer.physical_precondition is not None
            _BOUND_TERMINAL_OWNERLESS_ISSUERS[id(bearer)] = (
                _TerminalOwnerlessIssuerBinding(
                    issuer_bearer=bearer,
                    physical_action=bearer.successor,
                    physical_precondition=bearer.physical_precondition,
                    parent_terminal_bearer=(
                        ownerless_parent_terminal_bearer
                    ),
                    parent_registration=parent_registration,
                )
            )
            _ACTIVE_TERMINAL_OWNERLESS_ISSUER_BY_PARENT[
                id(ownerless_parent_terminal_bearer)
            ] = bearer
        if terminal_slot_key is not None:
            if terminal_slot_source is not None:
                _TERMINAL_PHYSICAL_SLOT_BY_BEARER.pop(
                    id(terminal_slot_source), None
                )
            _ACTIVE_TERMINAL_PHYSICAL_SLOTS[terminal_slot_key] = bearer
            _TERMINAL_PHYSICAL_SLOT_BY_BEARER[id(bearer)] = (
                terminal_slot_key
            )
        if nonterminal_slot_key is not None:
            if nonterminal_slot_source is not None:
                _NONTERMINAL_PHYSICAL_SLOT_BY_BEARER.pop(
                    id(nonterminal_slot_source), None
                )
            _ACTIVE_NONTERMINAL_PHYSICAL_SLOTS[
                nonterminal_slot_key
            ] = bearer
            _NONTERMINAL_PHYSICAL_SLOT_BY_BEARER[id(bearer)] = (
                nonterminal_slot_key
            )
    return carrier


def _register_opaque_carrier_copy(
    *,
    source: _OpaqueCarrier,
    copied: _OpaqueCarrier,
) -> None:
    with _AUTHORITY_REGISTRY_LOCK:
        registered = _ACTIVE_OPAQUE_CARRIERS.get(id(source))
        if (
            registered is not None
            and registered[0] is source
            and registered[1].active
            and _ACTIVE_OPAQUE_BEARERS.get(id(registered[1]))
            is registered[1]
            and _opaque_bearer_registration_matches(registered[1])
            and _terminal_physical_slot_is_consistent(
                bearer=registered[1]
            )
            and _nonterminal_physical_slot_is_consistent(
                bearer=registered[1]
            )
        ):
            _ACTIVE_OPAQUE_CARRIERS[id(copied)] = (
                copied,
                registered[1],
            )


def _opaque_bearer_registration_matches(bearer: _OpaqueBearer) -> bool:
    registration = _OPAQUE_BEARER_REGISTRATIONS.get(id(bearer))
    owner_context_binding = _BOUND_TERMINAL_OWNER_CONTEXTS.get(id(bearer))
    terminal_owner_context_required = (
        bearer.family == "terminal_retirement"
        and bearer.action == "physical_recovery_advanced"
    )
    return (
        registration is not None
        and registration.bearer is bearer
        and registration.session_bearer is bearer.session_bearer
        and registration.family == bearer.family
        and registration.cursor_sha256 == bearer.cursor_sha256
        and registration.action == bearer.action
        and registration.thread_id == bearer.thread_id
        and registration.nonce == bearer.nonce
        and registration.physical_slot_family
        == bearer.physical_slot_family
        and registration.registered_successor is bearer.successor
        and registration.registered_successor_postcondition_sha256
        == _physical_postcondition_value_sha256(bearer.successor)
        and (
            (
                isinstance(
                    registration.registered_successor,
                    (
                        _PhysicalPostcondition,
                        _RuntimeAdmissionReleasePrecondition,
                    ),
                )
                and registration.registered_successor_snapshot is not None
                and _physical_postcondition_value_sha256(
                    registration.registered_successor_snapshot
                )
                == registration.registered_successor_postcondition_sha256
            )
            or (
                not isinstance(
                    registration.registered_successor,
                    (
                        _PhysicalPostcondition,
                        _RuntimeAdmissionReleasePrecondition,
                    ),
                )
                and registration.registered_successor_snapshot is None
            )
        )
        and registration.registered_physical_precondition
        is bearer.physical_precondition
        and registration.registered_terminal_owner_context
        is bearer.terminal_owner_context
        and (
            (
                terminal_owner_context_required
                and owner_context_binding is not None
                and owner_context_binding.bearer is bearer
                and owner_context_binding.registration is registration
                and owner_context_binding.context
                is registration.registered_terminal_owner_context
            )
            or (
                not terminal_owner_context_required
                and owner_context_binding is None
                and registration.registered_terminal_owner_context is None
            )
        )
    )


def _opaque_carrier_is_registered(
    *,
    carrier: _OpaqueCarrier,
    bearer: _OpaqueBearer,
) -> bool:
    with _AUTHORITY_REGISTRY_LOCK:
        bearer_registered = _ACTIVE_OPAQUE_BEARERS.get(id(bearer))
        carrier_registered = _ACTIVE_OPAQUE_CARRIERS.get(id(carrier))
        bound_postcondition = _BOUND_PHYSICAL_POSTCONDITIONS.get(
            id(bearer)
        )
        bound_ownerless_issuer = _BOUND_TERMINAL_OWNERLESS_ISSUERS.get(
            id(bearer)
        )
        registration = _OPAQUE_BEARER_REGISTRATIONS.get(id(bearer))
        runtime_release_precondition_required = (
            bearer.family == "terminal_retirement"
            and bearer.action == "release_runtime_admission"
        )
        immutable_postcondition_required = (
            runtime_release_precondition_required
            or registration is not None
            and isinstance(
                registration.registered_successor,
                _PhysicalPostcondition,
            )
        )
        return (
            bearer_registered is bearer
            and _opaque_bearer_registration_matches(bearer)
            and carrier_registered is not None
            and carrier_registered[0] is carrier
            and carrier_registered[1] is bearer
            and (
                (
                    immutable_postcondition_required
                    and registration is not None
                    and (
                        not runtime_release_precondition_required
                        or type(registration.registered_successor)
                        is _RuntimeAdmissionReleasePrecondition
                    )
                    and bearer.successor
                    is registration.registered_successor
                    and bound_postcondition
                    is registration.registered_successor
                )
                or (
                    not immutable_postcondition_required
                    and (
                        bound_postcondition is None
                        or bearer.successor is bound_postcondition
                    )
                )
            )
            and (
                (
                    bearer.family
                    == "terminal_ownerless_successor_issuer"
                    and registration is not None
                    and bound_ownerless_issuer is not None
                    and bound_ownerless_issuer.issuer_bearer is bearer
                    and bearer.successor
                    is bound_ownerless_issuer.physical_action
                    and bearer.successor
                    is registration.registered_successor
                    and bearer.physical_precondition
                    is bound_ownerless_issuer.physical_precondition
                    and bearer.physical_precondition
                    is registration.registered_physical_precondition
                    and bound_ownerless_issuer.parent_terminal_bearer
                    is registration.parent_terminal_bearer
                    and bound_ownerless_issuer.parent_registration
                    is registration.parent_registration
                    and _ACTIVE_TERMINAL_OWNERLESS_ISSUER_BY_PARENT.get(
                        id(bound_ownerless_issuer.parent_terminal_bearer)
                    )
                    is bearer
                )
                or (
                    bearer.family
                    != "terminal_ownerless_successor_issuer"
                    and bound_ownerless_issuer is None
                )
            )
            and _terminal_physical_slot_is_consistent(bearer=bearer)
            and _nonterminal_physical_slot_is_consistent(bearer=bearer)
        )


def _deregister_opaque_bearer(
    *,
    bearer: _OpaqueBearer,
    release_terminal_slot: bool = True,
    release_nonterminal_slot: bool = True,
) -> None:
    with _AUTHORITY_REGISTRY_LOCK:
        _BOUND_PHYSICAL_POSTCONDITIONS.pop(id(bearer), None)
        _BOUND_TERMINAL_OWNER_CONTEXTS.pop(id(bearer), None)
        ownerless_binding = _BOUND_TERMINAL_OWNERLESS_ISSUERS.pop(
            id(bearer),
            None,
        )
        if (
            ownerless_binding is not None
            and _ACTIVE_TERMINAL_OWNERLESS_ISSUER_BY_PARENT.get(
                id(ownerless_binding.parent_terminal_bearer)
            )
            is bearer
        ):
            del _ACTIVE_TERMINAL_OWNERLESS_ISSUER_BY_PARENT[
                id(ownerless_binding.parent_terminal_bearer)
            ]
        for parent_id, active_issuer in tuple(
            _ACTIVE_TERMINAL_OWNERLESS_ISSUER_BY_PARENT.items()
        ):
            if active_issuer is bearer:
                del _ACTIVE_TERMINAL_OWNERLESS_ISSUER_BY_PARENT[parent_id]
        _OPAQUE_BEARER_REGISTRATIONS.pop(id(bearer), None)
        if _ACTIVE_OPAQUE_BEARERS.get(id(bearer)) is bearer:
            del _ACTIVE_OPAQUE_BEARERS[id(bearer)]
        for carrier_id, (_carrier, registered_bearer) in tuple(
            _ACTIVE_OPAQUE_CARRIERS.items()
        ):
            if registered_bearer is bearer:
                del _ACTIVE_OPAQUE_CARRIERS[carrier_id]
        if release_terminal_slot:
            _release_terminal_physical_slot(bearer=bearer)
        if release_nonterminal_slot:
            _release_nonterminal_physical_slot(bearer=bearer)


def _register_terminal_owner_context(
    *,
    authorization: TerminalRetirementAuthorization,
    context: Mapping[str, Any],
) -> None:
    if not isinstance(authorization, TerminalRetirementAuthorization):
        raise SessionCapabilityError(
            "live_start_terminal_owner_capability_forged"
        )
    bearer = _require_opaque_carrier(
        authorization,
        carrier_type=TerminalRetirementAuthorization,
        family="terminal_retirement",
        action=authorization._opaque.action,
        consume=False,
    )
    frozen = _freeze_terminal_owner_context_for_registration(
        bearer=bearer,
        context=context,
    )
    with _AUTHORITY_REGISTRY_LOCK:
        registration = _OPAQUE_BEARER_REGISTRATIONS.get(id(bearer))
        if (
            registration is None
            or registration.bearer is not bearer
            or registration.registered_terminal_owner_context != frozen
        ):
            raise SessionCapabilityError(
                "live_start_terminal_owner_capability_invalid"
            )


def _terminal_owner_context_for_authorization(
    authorization: TerminalRetirementAuthorization,
) -> Mapping[str, Any] | None:
    if not isinstance(authorization, TerminalRetirementAuthorization):
        raise SessionCapabilityError(
            "live_start_terminal_owner_capability_forged"
        )
    bearer = _require_opaque_carrier(
        authorization,
        carrier_type=TerminalRetirementAuthorization,
        family="terminal_retirement",
        action=authorization._opaque.action,
        consume=False,
    )
    with _AUTHORITY_REGISTRY_LOCK:
        registration = _OPAQUE_BEARER_REGISTRATIONS.get(id(bearer))
        if (
            registration is None
            or registration.bearer is not bearer
            or not _opaque_bearer_registration_matches(bearer)
        ):
            raise SessionCapabilityError(
                "live_start_terminal_owner_capability_invalid"
            )
        return registration.registered_terminal_owner_context


def _deactivate_opaque_bearers_for_session(
    session_bearer: _SessionBearer,
) -> None:
    with _AUTHORITY_REGISTRY_LOCK:
        bearers = tuple(
            {
                id(bearer): bearer
                for bearer in (
                    *_ACTIVE_OPAQUE_BEARERS.values(),
                    *_ACTIVE_TERMINAL_PHYSICAL_SLOTS.values(),
                    *_ACTIVE_NONTERMINAL_PHYSICAL_SLOTS.values(),
                )
            }.values()
        )
    for opaque_bearer in bearers:
        if opaque_bearer.session_bearer is session_bearer:
            _deregister_opaque_bearer(bearer=opaque_bearer)
            opaque_bearer.active = False
            opaque_bearer.nonce = ""


_AuthorizationT = TypeVar("_AuthorizationT", bound=_OpaqueCarrier)
_ReceiptT = TypeVar("_ReceiptT", bound=_OpaqueCarrier)
_PostconditionT = TypeVar("_PostconditionT", bound=_PhysicalPostcondition)
_PhysicalResultT = TypeVar("_PhysicalResultT")


def _mint_authorization_under_lock(
    *,
    authorization_type: type[_AuthorizationT],
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    family: str,
    action: str,
) -> _AuthorizationT:
    session_bearer, current = (
        _authenticate_authorization_cursor_under_lock(
            session_lease=session_lease,
            expected_session=expected_session,
        )
    )
    return _mint_authorization_for_authenticated_cursor(
        authorization_type=authorization_type,
        session_bearer=session_bearer,
        current=current,
        family=family,
        action=action,
    )


def _authenticate_authorization_cursor_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
) -> tuple[_SessionBearer, LiveStartSession]:
    session_bearer = _require_session_lease(session_lease)
    current = _load_expected_predecessor_under_lock(
        session_lease=session_lease,
        expected_session=expected_session,
    )
    _validate_run_layout_under_lock(
        session_lease=session_lease,
        session=current,
    )
    return session_bearer, current


def _mint_authorization_for_authenticated_cursor(
    *,
    authorization_type: type[_AuthorizationT],
    session_bearer: _SessionBearer,
    current: LiveStartSession,
    family: str,
    action: str,
    claim_nonterminal_slot: bool = False,
    registered_successor: Any = None,
    registered_physical_precondition: Mapping[str, Any] | None = None,
) -> _AuthorizationT:
    bearer = _OpaqueBearer(
        session_bearer=session_bearer,
        family=family,
        cursor_sha256=current.content_sha256,
        action=action,
    )
    bearer.successor = registered_successor
    bearer.physical_precondition = registered_physical_precondition
    return _mint_registered_opaque_carrier(
        carrier_type=authorization_type,
        bearer=bearer,
        claim_nonterminal_slot=claim_nonterminal_slot,
    )


def _require_opaque_carrier(
    carrier: _OpaqueCarrier,
    *,
    carrier_type: type[_AuthorizationT],
    family: str,
    action: str,
    consume: bool,
    preserve_terminal_slot: bool = False,
    preserve_nonterminal_slot: bool = False,
    capture_registered_state: bool = False,
) -> _OpaqueBearer | _OpaqueBearerConsumption:
    if not isinstance(carrier, carrier_type) or not hasattr(carrier, "_opaque"):
        raise SessionCapabilityError("live_start_physical_capability_forged")
    bearer = carrier._opaque
    if not isinstance(bearer, _OpaqueBearer) or not _opaque_carrier_is_registered(
        carrier=carrier,
        bearer=bearer,
    ):
        raise SessionCapabilityError("live_start_physical_capability_forged")
    if (
        not bearer.active
        or not bearer.nonce
        or bearer.thread_id != threading.get_ident()
        or bearer.family != family
        or bearer.action != action
        or not bearer.session_bearer.active
        or not _session_context_is_registered(
            bearer=bearer.session_bearer
        )
        or bearer.session_bearer.thread_id != threading.get_ident()
    ):
        raise SessionCapabilityError("live_start_physical_capability_invalid")
    _require_opaque_cursor_current(bearer)
    consumption: _OpaqueBearerConsumption | None = None
    if consume:
        with _AUTHORITY_REGISTRY_LOCK:
            registration = _OPAQUE_BEARER_REGISTRATIONS.get(id(bearer))
            if (
                registration is None
                or not _opaque_carrier_is_registered(
                    carrier=carrier,
                    bearer=bearer,
                )
                or _OPAQUE_BEARER_REGISTRATIONS.get(id(bearer))
                is not registration
            ):
                raise SessionCapabilityError(
                    "live_start_physical_capability_forged"
                )
            if isinstance(
                registration.registered_successor,
                (_PhysicalPostcondition, _RuntimeAdmissionReleasePrecondition),
            ) and (
                bearer.successor is not registration.registered_successor
                or _BOUND_PHYSICAL_POSTCONDITIONS.get(id(bearer))
                is not registration.registered_successor
            ):
                raise SessionCapabilityError(
                    "live_start_physical_capability_forged"
                )
            successor_postcondition_sha256 = (
                _physical_postcondition_value_sha256(
                    registration.registered_successor
                )
            )
            if (
                successor_postcondition_sha256
                != registration.registered_successor_postcondition_sha256
            ):
                raise SessionCapabilityError(
                    "live_start_physical_capability_forged"
                )
            consumed_successor = registration.registered_successor
            if registration.registered_successor_snapshot is not None:
                consumed_successor = _detached_registered_postcondition(
                    registration.registered_successor_snapshot
                )
                if (
                    consumed_successor is None
                    or _physical_postcondition_value_sha256(
                        consumed_successor
                    )
                    != registration.registered_successor_postcondition_sha256
                ):
                    raise SessionCapabilityError(
                        "live_start_physical_capability_forged"
                    )
            if capture_registered_state:
                consumption = _OpaqueBearerConsumption(
                    bearer=bearer,
                    registration=registration,
                    session_bearer=registration.session_bearer,
                    family=registration.family,
                    cursor_sha256=registration.cursor_sha256,
                    action=registration.action,
                    thread_id=registration.thread_id,
                    successor=consumed_successor,
                    successor_postcondition_sha256=(
                        registration.registered_successor_postcondition_sha256
                    ),
                    successor_was_registry_bound=True,
                    physical_precondition=(
                        registration.registered_physical_precondition
                    ),
                    terminal_owner_context=(
                        registration.registered_terminal_owner_context
                    ),
                    parent_terminal_bearer=(
                        registration.parent_terminal_bearer
                    ),
                    parent_registration=registration.parent_registration,
                )
            _deregister_opaque_bearer(
                bearer=bearer,
                release_terminal_slot=not preserve_terminal_slot,
                release_nonterminal_slot=not preserve_nonterminal_slot,
            )
        bearer.active = False
        bearer.nonce = ""
    if consumption is not None:
        if (
            _physical_postcondition_value_sha256(consumption.successor)
            != consumption.successor_postcondition_sha256
        ):
            raise SessionCapabilityError(
                "live_start_physical_capability_forged"
            )
        return consumption
    return bearer


def _require_candidate_review_revision_receipt_authority_without_observation(
    *,
    receipt: CandidateReviewRevisionStepReceipt,
    session_lease: LiveStartSessionLease,
    expected_revision_session: LiveStartSession,
    allowed_actions: frozenset[str],
) -> str:
    if not isinstance(session_lease, LiveStartSessionLease):
        raise SessionCapabilityError(
            "live_start_review_revision_receipt_invalid"
        )
    token = session_lease.lock_token
    if not isinstance(token, SessionLockToken) or not hasattr(token, "_bearer"):
        raise SessionCapabilityError(
            "live_start_review_revision_receipt_invalid"
        )
    session_bearer = token._bearer
    if (
        not isinstance(session_bearer, _SessionBearer)
        or not session_bearer.active
        or not session_bearer.nonce
        or session_bearer.thread_id != threading.get_ident()
        or not _session_context_is_registered(
            bearer=session_bearer,
            token=token,
        )
        or session_lease.session_root != session_bearer.session_root
        or session_lease.session_root_identity
        != session_bearer.session_root_identity
        or session_lease.session_lock_path != session_bearer.session_lock_path
        or session_lease.session_lock_identity
        != session_bearer.session_lock_identity
    ):
        raise SessionCapabilityError(
            "live_start_review_revision_receipt_invalid"
        )
    if (
        not isinstance(expected_revision_session, LiveStartSession)
        or type(receipt) is not CandidateReviewRevisionStepReceipt
        or not hasattr(receipt, "_opaque")
    ):
        raise SessionCapabilityError(
            "live_start_review_revision_receipt_invalid"
        )
    bearer = receipt._opaque
    if (
        not isinstance(bearer, _OpaqueBearer)
        or not _opaque_carrier_is_registered(
            carrier=receipt,
            bearer=bearer,
        )
        or not bearer.active
        or not bearer.nonce
        or bearer.family != "candidate_review_revision_receipt"
        or bearer.session_bearer is not session_bearer
        or bearer.cursor_sha256
        != expected_revision_session.content_sha256
        or bearer.thread_id != threading.get_ident()
    ):
        raise SessionCapabilityError(
            "live_start_review_revision_receipt_invalid"
        )
    action = bearer.action
    if type(action) is not str or action not in allowed_actions:
        raise SessionCapabilityError(
            "live_start_review_revision_receipt_invalid"
        )
    physical_precondition = bearer.physical_precondition
    if (
        not isinstance(physical_precondition, Mapping)
        or physical_precondition.get("action") != action
        or not isinstance(
            bearer.successor,
            CandidateReviewRevisionPhysicalPostcondition,
        )
        or bearer.successor.action != action
    ):
        raise SessionCapabilityError(
            "live_start_review_revision_receipt_invalid"
        )
    return action


def _require_opaque_cursor_current(bearer: _OpaqueBearer) -> None:
    session_bearer = bearer.session_bearer
    try:
        if (
            session_bearer.session_lock is None
            or path_identity(session_bearer.session_root)
            != session_bearer.session_root_identity
            or path_identity(session_bearer.session_lock_path)
            != session_bearer.session_lock_identity
        ):
            raise SessionCapabilityError(
                "live_start_physical_capability_context_changed"
            )
        session_bearer.session_lock.validate_no_alternate_data_streams(
            expected_size=0
        )
        raw, identity = _read_bound_file(
            session_bearer.session_root / "session.json",
            expected_parent_identity=session_bearer.session_root_identity,
            maximum_size=LIVE_START_SESSION_MAX_BYTES,
        )
        current = _load_session_bytes(raw, session_identity=identity)
    except SessionCapabilityError:
        raise
    except (OSError, RuntimeError, ValueError) as error:
        raise SessionCapabilityError(
            "live_start_physical_capability_context_changed"
        ) from error
    if current.content_sha256 != bearer.cursor_sha256:
        _deregister_opaque_bearer(bearer=bearer)
        bearer.active = False
        bearer.nonce = ""
        raise SessionCapabilityError(
            "live_start_physical_capability_cursor_stale"
        )


def _execute_physical_step(
    *,
    authorization: _OpaqueCarrier,
    authorization_type: type[_AuthorizationT],
    receipt_type: type[_ReceiptT],
    postcondition_type: type[_PostconditionT],
    family: str,
    action: str,
    physical_action: Callable[[], _PostconditionT],
    before_authorization_consume: Callable[[], None] | None = None,
    before_physical_action: Callable[[], None] | None = None,
    receipt_physical_precondition: (
        Callable[[], Mapping[str, Any] | None] | None
    ) = None,
) -> _ReceiptT:
    if before_authorization_consume is not None:
        _require_opaque_carrier(
            authorization,
            carrier_type=authorization_type,
            family=family,
            action=action,
            consume=False,
        )
        before_authorization_consume()
    consumed = _require_opaque_carrier(
        authorization,
        carrier_type=authorization_type,
        family=family,
        action=action,
        consume=True,
        capture_registered_state=True,
    )
    if not isinstance(consumed, _OpaqueBearerConsumption):
        raise SessionCapabilityError("live_start_physical_capability_invalid")
    if before_physical_action is not None:
        before_physical_action()
    result = physical_action()
    if not isinstance(result, postcondition_type) or result.action != action:
        raise SessionCapabilityError("live_start_physical_postcondition_invalid")
    receipt_bearer = _OpaqueBearer(
        session_bearer=consumed.session_bearer,
        family=f"{family}_receipt",
        cursor_sha256=consumed.cursor_sha256,
        action=action,
    )
    receipt_bearer.successor = result
    if receipt_physical_precondition is not None:
        receipt_bearer.physical_precondition = (
            receipt_physical_precondition()
        )
    return _mint_registered_opaque_carrier(
        carrier_type=receipt_type,
        bearer=receipt_bearer,
    )


def _read_exact_owner_file(
    *,
    path: Path,
    expected_parent_identity: PathIdentity,
    expected_identity: Any,
    expected_sha256: Any,
    expected_size: Any | None = None,
) -> bytes:
    identity = _require_identity(expected_identity, "owner_file_identity")
    digest = _require_sha256(expected_sha256, "owner_file_sha256")
    try:
        raw, observed_identity = _read_bound_file(
            path,
            expected_parent_identity=expected_parent_identity,
            maximum_size=64 * 1024 * 1024,
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise SessionConflictError(
            "live_start_owner_file_changed"
        ) from error
    if (
        observed_identity != identity
        or f"sha256:{sha256(raw).hexdigest()}" != digest
        or (expected_size is not None and len(raw) != expected_size)
    ):
        raise SessionConflictError("live_start_owner_file_changed")
    return raw


def _validate_owner_tombstone_binding(
    *,
    owner: Mapping[str, Any],
    raw: bytes,
    expected_state: str,
    expected_raw_sha256: str,
) -> tuple[Mapping[str, Any], bytes]:
    if f"sha256:{sha256(raw).hexdigest()}" != expected_raw_sha256:
        raise SessionConflictError(
            "live_start_owner_tombstone_digest_changed"
        )
    try:
        document = _validate_owner_tombstone_document(
            _decode_canonical_json(raw)
        )
    except SessionValidationError as error:
        raise SessionConflictError(
            "live_start_owner_tombstone_invalid"
        ) from error
    direct_bindings = {
        "retired_owner_transaction_id": "retired_owner_transaction_id",
        "initial_owner_journal_path": "initial_owner_journal_path",
        "initial_owner_journal_identity": (
            "initial_owner_journal_identity"
        ),
        "initial_owner_journal_sha256": "initial_owner_journal_sha256",
        "retired_target_path": "retired_target_path",
        "retired_target_parent_identity": (
            "retired_target_parent_identity"
        ),
        "retired_target_identity": "retired_target_identity",
        "retired_target_tree_sha256": "retired_target_tree_sha256",
        "successor_transaction_id": "successor_transaction_id",
        "successor_package_root_sha256": (
            "successor_package_root_sha256"
        ),
        "successor_owner_journal_path": "successor_owner_journal_path",
        "successor_owner_journal_identity": (
            "successor_owner_journal_identity"
        ),
        "successor_owner_journal_sha256": (
            "successor_owner_journal_sha256"
        ),
        "cleanup_manifest_sha256": "cleanup_manifest_sha256",
        "cleanup_entry_count": "cleanup_entry_count",
    }
    if document.get("state") != expected_state or any(
        document.get(document_field) != owner.get(owner_field)
        for document_field, owner_field in direct_bindings.items()
    ):
        raise SessionConflictError(
            "live_start_owner_tombstone_authority_changed"
        )
    count = owner["cleanup_entry_count"]
    cursor = owner["cleanup_cursor"]
    entries = document["cleanup_entries"]
    if cursor < count:
        row = entries[cursor]
        row_bindings = {
            "relative_path": "next_entry_relative_path",
            "entry_kind": "next_entry_kind",
            "identity": "next_entry_identity",
            "expected_parent_identity": "next_entry_parent_identity",
            "size": "next_entry_size",
            "sha256": "next_entry_sha256",
        }
        if any(
            row.get(row_field) != owner.get(owner_field)
            for row_field, owner_field in row_bindings.items()
        ):
            raise SessionConflictError(
                "live_start_owner_cleanup_entry_authority_changed"
            )
    completed_unsigned = _thaw(document)
    completed_unsigned.pop("content_sha256")
    completed_unsigned.update(
        {
            "state": "COMPLETED",
            "completed_cleanup_cursor": count,
            "completed_owner_journal_identity": owner[
                "current_owner_journal_identity"
            ],
            "completed_owner_journal_sha256": owner[
                "current_owner_journal_sha256"
            ],
        }
    )
    completed = {
        **completed_unsigned,
        "content_sha256": _self_digest(completed_unsigned),
    }
    completed_raw = _canonical_json(completed)
    if expected_state == "COMPLETED" and (
        document.get("completed_cleanup_cursor") != count
        or document.get("completed_owner_journal_identity")
        != owner.get("current_owner_journal_identity")
        or document.get("completed_owner_journal_sha256")
        != owner.get("current_owner_journal_sha256")
    ):
        raise SessionConflictError(
            "live_start_owner_completed_tombstone_changed"
        )
    planned_size = owner.get("planned_completed_tombstone_size")
    planned_sha256 = owner.get("planned_completed_tombstone_sha256")
    if planned_size is not None and (
        planned_size != len(completed_raw)
        or planned_sha256
        != f"sha256:{sha256(completed_raw).hexdigest()}"
    ):
        raise SessionConflictError(
            "live_start_owner_completed_tombstone_intent_changed"
        )
    return document, completed_raw


def _validate_owner_external_physical(
    external: Mapping[str, Any],
    *,
    allow_visible_bound_commit: str | None = None,
    allow_unbound_staging_residue: bool = False,
) -> bytes | None:
    value = validate_embedded_document("external_file_action", external)
    parent_identity = _require_identity(
        value["parent_identity"],
        "owner_external_parent_identity",
    )
    final_path = Path(value["final_path"])
    staging_path = Path(value["staging_path"])
    inner_temp_path = Path(value["inner_temp_path"])
    try:
        if path_identity(final_path.parent) != parent_identity:
            raise SessionConflictError(
                "live_start_owner_external_parent_changed"
            )
    except (OSError, ValueError) as error:
        raise SessionConflictError(
            "live_start_owner_external_parent_changed"
        ) from error
    if (
        allow_visible_bound_commit is not None
        and value["stage"] == "STAGING_BOUND"
        and value["action_kind"] == allow_visible_bound_commit
        and os.path.lexists(final_path)
        and not os.path.lexists(staging_path)
    ):
        if os.path.lexists(inner_temp_path):
            raise SessionConflictError(
                "live_start_owner_external_inner_temp_present"
            )
        if (
            value["staging_size"] != value["planned_successor_size"]
            or value["staging_sha256"]
            != value["planned_successor_sha256"]
        ):
            raise SessionConflictError(
                "live_start_owner_visible_commit_changed"
            )
        return _read_exact_owner_file(
            path=final_path,
            expected_parent_identity=parent_identity,
            expected_identity=value["staging_identity"],
            expected_sha256=value["staging_sha256"],
            expected_size=value["staging_size"],
        )
    if value["predecessor_state"] == "absent":
        if os.path.lexists(final_path):
            raise SessionConflictError(
                "live_start_owner_external_predecessor_changed"
            )
    else:
        _read_exact_owner_file(
            path=final_path,
            expected_parent_identity=parent_identity,
            expected_identity=value["predecessor_identity"],
            expected_sha256=value["predecessor_sha256"],
            expected_size=value["predecessor_size"],
        )
    if value["stage"] == "PLANNED":
        residue_present = os.path.lexists(
            staging_path
        ) or os.path.lexists(inner_temp_path)
        if residue_present and not allow_unbound_staging_residue:
            raise SessionConflictError(
                "live_start_owner_external_unbound_staging_present"
            )
        if allow_unbound_staging_residue and not residue_present:
            raise SessionConflictError(
                "live_start_owner_external_unbound_staging_missing"
            )
        return None
    _read_exact_owner_file(
        path=staging_path,
        expected_parent_identity=parent_identity,
        expected_identity=value["staging_identity"],
        expected_sha256=value["staging_sha256"],
        expected_size=value["staging_size"],
    )
    if os.path.lexists(inner_temp_path):
        raise SessionConflictError(
            "live_start_owner_external_inner_temp_present"
        )
    return None


def _validate_visible_owner_journal_commit(
    *,
    owner: Mapping[str, Any],
    prepared_tombstone: Mapping[str, Any],
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
    except ValueError as error:
        raise SessionConflictError(
            "live_start_owner_visible_journal_invalid"
        ) from error
    expected_entries = tuple(
        (
            entry["entry_kind"],
            entry["relative_path"],
            tuple(entry["identity"]),
        )
        for entry in prepared_tombstone["cleanup_entries"]
    )
    observed_entries = tuple(
        (entry.kind, entry.relative_path, entry.identity)
        for entry in journal.cleanup_entries
    )
    if (
        journal.phase != RuntimeTransactionPhase.FINALIZED
        or not journal.owns_target
        or not journal.cleanup_started
        or journal.cleanup_cursor != expected_cursor
        or journal.target_identity
        != tuple(owner["retired_target_identity"])
        or runtime_root / journal.target_path
        != Path(owner["retired_target_path"])
        or observed_entries != expected_entries
    ):
        raise SessionConflictError(
            "live_start_owner_visible_journal_invalid"
        )


def _validate_owner_commit_external_binding(
    *,
    owner: Mapping[str, Any],
    external: Mapping[str, Any] | None,
    action: str,
) -> None:
    if action not in {
        "commit_owner_retirement_prepared",
        "initialize_owner_cleanup_journal",
        "advance_owner_cleanup_journal",
        "commit_owner_retirement_completed",
    }:
        return
    if not isinstance(external, Mapping):
        raise SessionConflictError(
            "live_start_owner_external_action_missing"
        )
    if action == "commit_owner_retirement_prepared":
        expected = {
            "final_path": owner["tombstone_path"],
            "commit_mode": "create_no_replace",
            "predecessor_state": "absent",
            "predecessor_identity": None,
            "predecessor_sha256": None,
            "planned_successor_sha256": owner["tombstone_sha256"],
        }
    elif action in {
        "initialize_owner_cleanup_journal",
        "advance_owner_cleanup_journal",
    }:
        expected = {
            "final_path": owner["initial_owner_journal_path"],
            "commit_mode": "replace_exact",
            "predecessor_state": "exact",
            "predecessor_identity": owner[
                "current_owner_journal_identity"
            ],
            "predecessor_sha256": owner[
                "current_owner_journal_sha256"
            ],
        }
    else:
        expected = {
            "final_path": owner["tombstone_path"],
            "commit_mode": "replace_exact",
            "predecessor_state": "exact",
            "predecessor_identity": owner["tombstone_identity"],
            "predecessor_sha256": owner["tombstone_sha256"],
            "planned_successor_size": owner[
                "planned_completed_tombstone_size"
            ],
            "planned_successor_sha256": owner[
                "planned_completed_tombstone_sha256"
            ],
        }
    if (
        external.get("stage") != "STAGING_BOUND"
        or external.get("action_kind") != action
        or any(external.get(key) != value for key, value in expected.items())
    ):
        raise SessionConflictError(
            "live_start_owner_external_action_invalid"
        )


def _require_owner_directory(
    *,
    path: Path,
    expected_parent_identity: Any,
    expected_identity: Any,
    empty: bool,
) -> None:
    parent_identity = _require_identity(
        expected_parent_identity,
        "owner_directory_parent_identity",
    )
    identity = _require_identity(
        expected_identity,
        "owner_directory_identity",
    )
    try:
        status = path.lstat()
        if (
            not stat.S_ISDIR(status.st_mode)
            or status_is_reparse(status)
            or path_identity_from_status(status) != identity
            or path_identity(path.parent) != parent_identity
            or (empty and any(path.iterdir()))
        ):
            raise SessionConflictError(
                "live_start_owner_target_changed"
            )
        if os.name == "nt":
            require_no_alternate_data_streams(
                path,
                expected_identity=identity,
                expected_parent_identity=parent_identity,
                directory=True,
                expected_size=None,
            )
    except SessionConflictError:
        raise
    except (OSError, RuntimeError, ValueError) as error:
        raise SessionConflictError(
            "live_start_owner_target_changed"
        ) from error


def _validate_owner_layout_binding_under_lock(
    *,
    owner: Mapping[str, Any],
    external: Mapping[str, Any] | None,
    runtime_layout: Mapping[str, Any],
) -> Mapping[str, PathIdentity]:
    if runtime_layout.get("stage") != "COMPLETE":
        raise SessionConflictError(
            "live_start_owner_layout_binding_invalid"
        )
    rows = runtime_layout.get("directories")
    if not isinstance(rows, Sequence):
        raise SessionConflictError(
            "live_start_owner_layout_binding_invalid"
        )
    by_role = {
        row.get("role"): row
        for row in rows
        if isinstance(row, Mapping)
    }
    authorities: dict[str, tuple[Path, PathIdentity]] = {}
    try:
        for role in ("custom_config", "transactions", "owner_retirements"):
            row = by_role.get(role)
            if not isinstance(row, Mapping):
                raise SessionConflictError(
                    "live_start_owner_layout_binding_invalid"
                )
            path = Path(str(row.get("path")))
            identity = _require_identity(
                row.get("successor_identity"),
                f"owner_layout_{role}_identity",
            )
            if path_identity(path) != identity:
                raise SessionConflictError(
                    "live_start_owner_layout_binding_invalid"
                )
            authorities[role] = (path, identity)
    except SessionConflictError:
        raise
    except (OSError, ValueError) as error:
        raise SessionConflictError(
            "live_start_owner_layout_binding_invalid"
        ) from error

    custom_path, custom_identity = authorities["custom_config"]
    transactions_path, transactions_identity = authorities["transactions"]
    retirements_path, retirements_identity = authorities[
        "owner_retirements"
    ]
    tombstone_path = Path(str(owner["tombstone_path"]))
    initial_owner_path = Path(str(owner["initial_owner_journal_path"]))
    successor_owner_path = Path(str(owner["successor_owner_journal_path"]))
    retired_target_path = Path(str(owner["retired_target_path"]))
    if (
        tombstone_path.parent != retirements_path
        or _require_identity(
            owner["tombstone_parent_identity"],
            "owner_tombstone_parent_identity",
        )
        != retirements_identity
        or initial_owner_path.parent != transactions_path
        or successor_owner_path.parent != transactions_path
        or retired_target_path.parent != custom_path
        or _require_identity(
            owner["retired_target_parent_identity"],
            "owner_target_parent_identity",
        )
        != custom_identity
    ):
        raise SessionConflictError(
            "live_start_owner_layout_binding_invalid"
        )
    if external is not None:
        external_final = Path(str(external["final_path"]))
        if external_final == tombstone_path:
            expected_external_parent = retirements_identity
        elif external_final == initial_owner_path:
            expected_external_parent = transactions_identity
        else:
            raise SessionConflictError(
                "live_start_owner_layout_binding_invalid"
            )
        if _require_identity(
            external["parent_identity"],
            "owner_external_parent_identity",
        ) != expected_external_parent:
            raise SessionConflictError(
                "live_start_owner_layout_binding_invalid"
            )
    return MappingProxyType(
        {
            "custom_config": custom_identity,
            "transactions": transactions_identity,
            "owner_retirements": retirements_identity,
        }
    )


def _validate_owner_action_precondition_under_lock(
    *,
    recovery: Mapping[str, Any],
    action: str,
    enforce_cursor_binding: bool = True,
    runtime_layout: Mapping[str, Any] | None = None,
    allow_unbound_staging_residue: bool = False,
) -> None:
    owner_raw = recovery.get("owner_retirement")
    owner_action = action in _OWNER_RETIREMENT_PHYSICAL_ACTIONS
    if action == "materialize_file_action_staging":
        if owner_raw is None:
            return
    elif not owner_action:
        return
    if not isinstance(owner_raw, Mapping):
        raise SessionConflictError(
            "live_start_owner_retirement_cursor_missing"
        )
    owner = _validate_owner_retirement_document(owner_raw)
    external_raw = recovery.get("external_file_action")
    external = (
        validate_embedded_document("external_file_action", external_raw)
        if isinstance(external_raw, Mapping)
        else None
    )
    if enforce_cursor_binding:
        _validate_owner_cursor_action_binding(
            recovery=recovery,
            conflict=True,
        )
    layout_identities = (
        _validate_owner_layout_binding_under_lock(
            owner=owner,
            external=external,
            runtime_layout=runtime_layout,
        )
        if isinstance(runtime_layout, Mapping)
        else None
    )
    stage = owner["stage"]
    expected = _owner_action_for_cursor(owner=owner, external=external)
    if expected != action:
        raise SessionConflictError(
            "live_start_owner_action_precondition_invalid"
        )
    if allow_unbound_staging_residue and (
        action != "materialize_file_action_staging"
        or external is None
        or external.get("stage") != "PLANNED"
    ):
        raise SessionConflictError(
            "live_start_owner_unbound_staging_authority_invalid"
        )
    _validate_owner_commit_external_binding(
        owner=owner,
        external=external,
        action=action,
    )
    visible_bound_commit_raw = (
        _validate_owner_external_physical(
            external,
            allow_visible_bound_commit=action,
            allow_unbound_staging_residue=(
                allow_unbound_staging_residue
            ),
        )
        if external is not None
        else None
    )

    tombstone_path = Path(owner["tombstone_path"])
    tombstone_parent = _require_identity(
        (
            layout_identities["owner_retirements"]
            if layout_identities is not None
            else owner["tombstone_parent_identity"]
        ),
        "owner_tombstone_parent_identity",
    )
    target = Path(owner["retired_target_path"])
    target_parent = _require_identity(
        (
            layout_identities["custom_config"]
            if layout_identities is not None
            else owner["retired_target_parent_identity"]
        ),
        "owner_target_parent_identity",
    )
    try:
        if (
            path_identity(tombstone_path.parent) != tombstone_parent
            or path_identity(target.parent) != target_parent
        ):
            raise SessionConflictError(
                "live_start_owner_parent_changed"
            )
    except SessionConflictError:
        raise
    except (OSError, ValueError) as error:
        raise SessionConflictError(
            "live_start_owner_parent_changed"
        ) from error

    successor_path = Path(owner["successor_owner_journal_path"])
    _read_exact_owner_file(
        path=successor_path,
        expected_parent_identity=(
            layout_identities["transactions"]
            if layout_identities is not None
            else path_identity(successor_path.parent)
        ),
        expected_identity=owner["successor_owner_journal_identity"],
        expected_sha256=owner["successor_owner_journal_sha256"],
    )

    prepared_document: Mapping[str, Any] | None = None
    completed_raw: bytes | None = None
    if stage == "PREPARED_PLANNED":
        if visible_bound_commit_raw is not None:
            prepared_document, completed_raw = (
                _validate_owner_tombstone_binding(
                    owner=owner,
                    raw=visible_bound_commit_raw,
                    expected_state="PREPARED",
                    expected_raw_sha256=owner["tombstone_sha256"],
                )
            )
        elif os.path.lexists(tombstone_path):
            raise SessionConflictError(
                "live_start_owner_tombstone_created_early"
            )
    else:
        visible_completed_commit = (
            action == "commit_owner_retirement_completed"
            and visible_bound_commit_raw is not None
        )
        expected_tombstone_state = (
            "COMPLETED"
            if visible_completed_commit
            or stage in {"COMPLETED", "OWNER_RETIRED"}
            else "PREPARED"
        )
        raw = (
            visible_bound_commit_raw
            if visible_completed_commit
            else _read_exact_owner_file(
                path=tombstone_path,
                expected_parent_identity=tombstone_parent,
                expected_identity=owner["tombstone_identity"],
                expected_sha256=owner["tombstone_sha256"],
            )
        )
        assert raw is not None
        prepared_document, completed_raw = (
            _validate_owner_tombstone_binding(
                owner=owner,
                raw=raw,
                expected_state=expected_tombstone_state,
                expected_raw_sha256=(
                    owner["planned_completed_tombstone_sha256"]
                    if visible_completed_commit
                    else owner["tombstone_sha256"]
                ),
            )
        )

    target_retired = stage in {
        "TARGET_RETIRED",
        "COMPLETED",
        "OWNER_RETIRED",
    }
    if target_retired:
        if os.path.lexists(target):
            raise SessionConflictError(
                "live_start_owner_target_not_retired"
            )
    elif (
        action == "retire_owner_target_root"
        and not os.path.lexists(target)
    ):
        pass
    else:
        _require_owner_directory(
            path=target,
            expected_parent_identity=target_parent,
            expected_identity=owner["retired_target_identity"],
            empty=action == "retire_owner_target_root",
        )

    old_journal = Path(owner["initial_owner_journal_path"])
    old_journal_parent = (
        layout_identities["transactions"]
        if layout_identities is not None
        else path_identity(old_journal.parent)
    )
    if stage == "OWNER_RETIRED":
        if os.path.lexists(old_journal):
            raise SessionConflictError(
                "live_start_owner_journal_not_retired"
            )
    elif (
        action == "retire_old_owner_journal"
        and not os.path.lexists(old_journal)
    ):
        pass
    elif (
        action
        in {
            "initialize_owner_cleanup_journal",
            "advance_owner_cleanup_journal",
        }
        and visible_bound_commit_raw is not None
    ):
        if prepared_document is None:
            raise SessionConflictError(
                "live_start_owner_tombstone_missing"
            )
        _validate_visible_owner_journal_commit(
            owner=owner,
            prepared_tombstone=prepared_document,
            raw=visible_bound_commit_raw,
            runtime_root=Path(recovery["runtime_root"]),
            expected_cursor=(
                0
                if action == "initialize_owner_cleanup_journal"
                else int(owner["cleanup_cursor"]) + 1
            ),
        )
    else:
        _read_exact_owner_file(
            path=old_journal,
            expected_parent_identity=old_journal_parent,
            expected_identity=owner["current_owner_journal_identity"],
            expected_sha256=owner["current_owner_journal_sha256"],
        )

    if action == "commit_owner_retirement_prepared":
        assert external is not None
        raw = (
            visible_bound_commit_raw
            if visible_bound_commit_raw is not None
            else _read_exact_owner_file(
                path=Path(external["staging_path"]),
                expected_parent_identity=tombstone_parent,
                expected_identity=external["staging_identity"],
                expected_sha256=external["staging_sha256"],
                expected_size=external["staging_size"],
            )
        )
        _validate_owner_tombstone_binding(
            owner=owner,
            raw=raw,
            expected_state="PREPARED",
            expected_raw_sha256=owner["tombstone_sha256"],
        )
    elif action == "commit_owner_retirement_completed":
        assert external is not None
        assert completed_raw is not None
        staged = (
            visible_bound_commit_raw
            if visible_bound_commit_raw is not None
            else _read_exact_owner_file(
                path=Path(external["staging_path"]),
                expected_parent_identity=tombstone_parent,
                expected_identity=external["staging_identity"],
                expected_sha256=external["staging_sha256"],
                expected_size=external["staging_size"],
            )
        )
        if staged != completed_raw:
            raise SessionConflictError(
                "live_start_owner_completed_tombstone_substituted"
            )
    elif action == "delete_owner_cleanup_entry":
        if prepared_document is None:
            raise SessionConflictError(
                "live_start_owner_tombstone_missing"
            )
        entry_path = target / owner["next_entry_relative_path"]
        entry_parent_identity = _require_identity(
            owner["next_entry_parent_identity"],
            "owner_next_entry_parent_identity",
        )
        try:
            if path_identity(entry_path.parent) != entry_parent_identity:
                raise SessionConflictError(
                    "live_start_owner_cleanup_entry_parent_changed"
                )
        except SessionConflictError:
            raise
        except (OSError, ValueError) as error:
            raise SessionConflictError(
                "live_start_owner_cleanup_entry_parent_changed"
            ) from error
        if not os.path.lexists(entry_path):
            pass
        elif owner["next_entry_kind"] == "file":
            _read_exact_owner_file(
                path=entry_path,
                expected_parent_identity=entry_parent_identity,
                expected_identity=owner["next_entry_identity"],
                expected_sha256=owner["next_entry_sha256"],
                expected_size=owner["next_entry_size"],
            )
        else:
            _require_owner_directory(
                path=entry_path,
                expected_parent_identity=owner[
                    "next_entry_parent_identity"
                ],
                expected_identity=owner["next_entry_identity"],
                empty=True,
            )
    elif stage == "CLEANING" and external is not None:
        entry_path = target / owner["next_entry_relative_path"]
        if os.path.lexists(entry_path):
            raise SessionConflictError(
                "live_start_owner_cleanup_entry_not_retired"
            )
    elif action == "observe_owner_retirement_completed":
        if prepared_document is None or prepared_document["state"] != "COMPLETED":
            raise SessionConflictError(
                "live_start_owner_completion_not_observed"
            )


def _validate_owner_root_postcondition(
    *,
    predecessor: Mapping[str, Any],
    evidence: Mapping[str, Any],
    runtime_layout: Mapping[str, Any],
) -> None:
    owner_raw = predecessor.get("owner_retirement")
    root_raw = evidence.get("owner_root_postcondition")
    if not isinstance(owner_raw, Mapping) or not isinstance(root_raw, Mapping):
        raise SessionCapabilityError(
            "live_start_owner_root_postcondition_missing"
        )
    owner = _validate_owner_retirement_document(owner_raw)
    root = _normalize_json(root_raw)
    if (
        not isinstance(root, dict)
        or set(root) != _OWNER_ROOT_POSTCONDITION_FIELDS
        or root.get("disposition") not in {"removed", "already_absent"}
    ):
        raise SessionCapabilityError(
            "live_start_owner_root_postcondition_invalid"
        )
    preexisting = evidence.get("_owner_object_preexisting")
    if type(preexisting) is not bool or root["disposition"] != (
        "removed" if preexisting else "already_absent"
    ):
        raise SessionCapabilityError(
            "live_start_owner_root_postcondition_disposition_invalid"
        )
    expected = {
        "target_path": owner["retired_target_path"],
        "historical_target_identity": owner["retired_target_identity"],
        "target_parent_identity": owner[
            "retired_target_parent_identity"
        ],
        "prepared_tombstone_path": owner["tombstone_path"],
        "prepared_tombstone_identity": owner["tombstone_identity"],
        "prepared_tombstone_sha256": owner["tombstone_sha256"],
        "final_owner_journal_path": owner[
            "initial_owner_journal_path"
        ],
        "final_owner_journal_identity": owner[
            "current_owner_journal_identity"
        ],
        "final_owner_journal_sha256": owner[
            "current_owner_journal_sha256"
        ],
        "cleanup_manifest_sha256": owner["cleanup_manifest_sha256"],
        "cleanup_entry_count": owner["cleanup_entry_count"],
        "planned_completed_tombstone_size": owner[
            "planned_completed_tombstone_size"
        ],
        "planned_completed_tombstone_sha256": owner[
            "planned_completed_tombstone_sha256"
        ],
    }
    if any(root.get(key) != _normalize_json(value) for key, value in expected.items()):
        raise SessionCapabilityError(
            "live_start_owner_root_postcondition_changed"
        )
    if os.path.lexists(Path(owner["retired_target_path"])):
        raise SessionCapabilityError(
            "live_start_owner_root_postcondition_target_present"
        )
    try:
        _validate_owner_action_precondition_under_lock(
            recovery=predecessor,
            action="retire_owner_target_root",
            enforce_cursor_binding=("expected_action" in predecessor),
            runtime_layout=runtime_layout,
        )
    except (SessionConflictError, SessionValidationError) as error:
        raise SessionCapabilityError(
            "live_start_owner_root_postcondition_physical_changed"
        ) from error


def _require_owner_postcondition_mapping(
    *,
    value: Any,
    fields: frozenset[str],
    expected: Mapping[str, Any],
    error_code: str,
) -> Mapping[str, Any]:
    normalized = _normalize_json(value)
    if (
        not isinstance(normalized, dict)
        or set(normalized) != fields
        or normalized.get("disposition")
        not in {"removed", "already_absent"}
        or any(
            normalized.get(key) != _normalize_json(item)
            for key, item in expected.items()
        )
    ):
        raise SessionCapabilityError(error_code)
    return _freeze_mapping(normalized)


def _validate_owner_delete_postcondition(
    *,
    predecessor: Mapping[str, Any],
    evidence: Mapping[str, Any],
    runtime_layout: Mapping[str, Any],
) -> None:
    owner_raw = predecessor.get("owner_retirement")
    if not isinstance(owner_raw, Mapping):
        raise SessionCapabilityError(
            "live_start_owner_delete_postcondition_missing"
        )
    owner = _validate_owner_retirement_document(owner_raw)
    postcondition = _require_owner_postcondition_mapping(
        value=evidence.get("owner_delete_postcondition"),
        fields=_OWNER_DELETE_POSTCONDITION_FIELDS,
        expected={
            "target_path": owner["retired_target_path"],
            "historical_target_identity": owner[
                "retired_target_identity"
            ],
            "target_parent_identity": owner[
                "retired_target_parent_identity"
            ],
            "entry_relative_path": owner["next_entry_relative_path"],
            "entry_kind": owner["next_entry_kind"],
            "entry_identity": owner["next_entry_identity"],
            "entry_parent_identity": owner[
                "next_entry_parent_identity"
            ],
            "entry_size": owner["next_entry_size"],
            "entry_sha256": owner["next_entry_sha256"],
            "prepared_tombstone_path": owner["tombstone_path"],
            "prepared_tombstone_identity": owner[
                "tombstone_identity"
            ],
            "prepared_tombstone_sha256": owner["tombstone_sha256"],
            "current_owner_journal_path": owner[
                "initial_owner_journal_path"
            ],
            "current_owner_journal_identity": owner[
                "current_owner_journal_identity"
            ],
            "current_owner_journal_sha256": owner[
                "current_owner_journal_sha256"
            ],
            "cleanup_manifest_sha256": owner[
                "cleanup_manifest_sha256"
            ],
            "cleanup_entry_count": owner["cleanup_entry_count"],
            "cleanup_cursor": owner["cleanup_cursor"],
        },
        error_code="live_start_owner_delete_postcondition_invalid",
    )
    preexisting = evidence.get("_owner_object_preexisting")
    if type(preexisting) is not bool or postcondition["disposition"] != (
        "removed" if preexisting else "already_absent"
    ):
        raise SessionCapabilityError(
            "live_start_owner_delete_postcondition_disposition_invalid"
        )
    entry_path = (
        Path(owner["retired_target_path"])
        / owner["next_entry_relative_path"]
    )
    if os.path.lexists(entry_path):
        raise SessionCapabilityError(
            "live_start_owner_delete_postcondition_entry_present"
        )
    try:
        _validate_owner_action_precondition_under_lock(
            recovery=predecessor,
            action="delete_owner_cleanup_entry",
            enforce_cursor_binding=("expected_action" in predecessor),
            runtime_layout=runtime_layout,
        )
    except (SessionConflictError, SessionValidationError) as error:
        raise SessionCapabilityError(
            "live_start_owner_delete_postcondition_physical_changed"
        ) from error


def _validate_owner_old_journal_postcondition(
    *,
    predecessor: Mapping[str, Any],
    evidence: Mapping[str, Any],
    runtime_layout: Mapping[str, Any],
) -> None:
    owner_raw = predecessor.get("owner_retirement")
    if not isinstance(owner_raw, Mapping):
        raise SessionCapabilityError(
            "live_start_owner_old_journal_postcondition_missing"
        )
    owner = _validate_owner_retirement_document(owner_raw)
    postcondition = _require_owner_postcondition_mapping(
        value=evidence.get("owner_old_journal_postcondition"),
        fields=_OWNER_OLD_JOURNAL_POSTCONDITION_FIELDS,
        expected={
            "journal_path": owner["initial_owner_journal_path"],
            "historical_journal_identity": owner[
                "current_owner_journal_identity"
            ],
            "historical_journal_sha256": owner[
                "current_owner_journal_sha256"
            ],
            "completed_tombstone_path": owner["tombstone_path"],
            "completed_tombstone_identity": owner[
                "tombstone_identity"
            ],
            "completed_tombstone_sha256": owner[
                "tombstone_sha256"
            ],
            "successor_owner_journal_path": owner[
                "successor_owner_journal_path"
            ],
            "successor_owner_journal_identity": owner[
                "successor_owner_journal_identity"
            ],
            "successor_owner_journal_sha256": owner[
                "successor_owner_journal_sha256"
            ],
        },
        error_code="live_start_owner_old_journal_postcondition_invalid",
    )
    preexisting = evidence.get("_owner_object_preexisting")
    if type(preexisting) is not bool or postcondition["disposition"] != (
        "removed" if preexisting else "already_absent"
    ):
        raise SessionCapabilityError(
            "live_start_owner_old_journal_postcondition_disposition_invalid"
        )
    if os.path.lexists(Path(owner["initial_owner_journal_path"])):
        raise SessionCapabilityError(
            "live_start_owner_old_journal_postcondition_present"
        )
    try:
        _validate_owner_action_precondition_under_lock(
            recovery=predecessor,
            action="retire_old_owner_journal",
            enforce_cursor_binding=("expected_action" in predecessor),
            runtime_layout=runtime_layout,
        )
    except (SessionConflictError, SessionValidationError) as error:
        raise SessionCapabilityError(
            "live_start_owner_old_journal_postcondition_physical_changed"
        ) from error


def _validate_owner_physical_postcondition(
    *,
    predecessor: Mapping[str, Any],
    action: str,
    evidence: Mapping[str, Any],
    runtime_layout: Mapping[str, Any] | None,
) -> None:
    if action == "observe_owner_retirement_completed":
        if not isinstance(runtime_layout, Mapping):
            raise SessionCapabilityError(
                "live_start_owner_layout_binding_missing"
            )
        try:
            _validate_owner_action_precondition_under_lock(
                recovery=predecessor,
                action=action,
                enforce_cursor_binding=(
                    "expected_action" in predecessor
                ),
                runtime_layout=runtime_layout,
            )
        except (SessionConflictError, SessionValidationError) as error:
            raise SessionCapabilityError(
                "live_start_owner_observation_postcondition_changed"
            ) from error
        return
    validators = {
        "delete_owner_cleanup_entry": _validate_owner_delete_postcondition,
        "retire_owner_target_root": _validate_owner_root_postcondition,
        "retire_old_owner_journal": (
            _validate_owner_old_journal_postcondition
        ),
    }
    validator = validators.get(action)
    if validator is not None:
        if not isinstance(runtime_layout, Mapping):
            raise SessionCapabilityError(
                "live_start_owner_layout_binding_missing"
            )
        validator(
            predecessor=predecessor,
            evidence=evidence,
            runtime_layout=runtime_layout,
        )


def _consume_receipt_registration_under_lock(
    *,
    receipt: _OpaqueCarrier,
    receipt_type: type[_ReceiptT],
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    family: str,
    action: str,
) -> _OpaqueBearerConsumption:
    session_bearer = _require_session_lease(session_lease)
    bearer = _require_opaque_carrier(
        receipt,
        carrier_type=receipt_type,
        family=f"{family}_receipt",
        action=action,
        consume=False,
    )
    if bearer.session_bearer is not session_bearer:
        raise SessionCapabilityError("live_start_physical_receipt_stale")
    current = _load_expected_predecessor_under_lock(
        session_lease=session_lease,
        expected_session=expected_session,
    )
    consumed = _require_opaque_carrier(
        receipt,
        carrier_type=receipt_type,
        family=f"{family}_receipt",
        action=action,
        consume=True,
        capture_registered_state=True,
    )
    if (
        not isinstance(consumed, _OpaqueBearerConsumption)
        or consumed.session_bearer is not session_bearer
        or consumed.family != f"{family}_receipt"
        or consumed.action != action
        or consumed.cursor_sha256 != current.content_sha256
        or not consumed.successor_was_registry_bound
        or not isinstance(consumed.successor, _PhysicalPostcondition)
    ):
        raise SessionCapabilityError("live_start_physical_receipt_stale")
    return consumed


def _consume_receipt_under_lock(
    *,
    receipt: _OpaqueCarrier,
    receipt_type: type[_ReceiptT],
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    family: str,
    action: str,
) -> _PhysicalPostcondition:
    consumed = _consume_receipt_registration_under_lock(
        receipt=receipt,
        receipt_type=receipt_type,
        session_lease=session_lease,
        expected_session=expected_session,
        family=family,
        action=action,
    )
    assert isinstance(consumed.successor, _PhysicalPostcondition)
    return consumed.successor


def _validate_apply_recovery_action_precondition_under_lock(
    *,
    recovery: Mapping[str, Any],
    action: str,
    runtime_layout: Mapping[str, Any] | None = None,
) -> None:
    _validate_owner_action_precondition_under_lock(
        recovery=recovery,
        action=action,
        runtime_layout=runtime_layout,
    )
    if action != "write_deck_config_ini":
        return
    external = recovery.get("external_file_action")
    if (
        not isinstance(external, Mapping)
        or external.get("action_kind") != "write_deck_config_ini"
        or external.get("stage") != "STAGING_BOUND"
    ):
        raise SessionConflictError(
            "live_start_deck_config_ini_staging_not_bound"
        )
    target_path = recovery.get("renamed_target_path")
    predecessor_target_identity = recovery.get(
        "predecessor_renamed_target_identity"
    )
    successor_target_identity = recovery.get(
        "successor_renamed_target_identity"
    )
    if (
        not isinstance(target_path, str)
        or predecessor_target_identity is None
        or successor_target_identity is None
        or predecessor_target_identity != successor_target_identity
    ):
        raise SessionConflictError(
            "live_start_deck_config_ini_target_owner_not_bound"
        )
    expected_target_identity = _require_identity(
        predecessor_target_identity,
        "predecessor_renamed_target_identity",
    )
    try:
        if path_identity(Path(target_path)) != expected_target_identity:
            raise SessionConflictError(
                "live_start_deck_config_ini_target_owner_changed"
            )
    except SessionConflictError:
        raise
    except (OSError, ValueError) as error:
        raise SessionConflictError(
            "live_start_deck_config_ini_target_owner_changed"
        ) from error

    route = recovery.get("install_route")
    journal_prefix = (
        "successor_journal"
        if route == "new_target"
        else "predecessor_target_owner_journal"
    )
    journal_path_value = recovery.get(f"{journal_prefix}_path")
    journal_identity_value = recovery.get(f"{journal_prefix}_identity")
    journal_sha256 = recovery.get(f"{journal_prefix}_sha256")
    if (
        route not in {"new_target", "prior_owner"}
        or not isinstance(journal_path_value, str)
        or journal_identity_value is None
        or not isinstance(journal_sha256, str)
    ):
        raise SessionConflictError(
            "live_start_deck_config_ini_owner_journal_not_bound"
        )
    journal_path = Path(journal_path_value)
    expected_journal_identity = _require_identity(
        journal_identity_value,
        f"{journal_prefix}_identity",
    )
    try:
        raw, observed_identity = _read_bound_file(
            journal_path,
            expected_parent_identity=path_identity(journal_path.parent),
            maximum_size=64 * 1024 * 1024,
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise SessionConflictError(
            "live_start_deck_config_ini_owner_journal_changed"
        ) from error
    if (
        observed_identity != expected_journal_identity
        or f"sha256:{sha256(raw).hexdigest()}" != journal_sha256
    ):
        raise SessionConflictError(
            "live_start_deck_config_ini_owner_journal_changed"
        )


def _authorize_nonterminal_apply_recovery_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_recovery_session: LiveStartSession,
    expected_action: str,
) -> RuntimeAttemptRecoveryAuthorization:
    if expected_action not in frozenset(RUNTIME_APPLY_RECOVERY_ACTIONS) | (
        NONTERMINAL_PURE_TRANSITIONS - {"select_terminal_classification"}
    ):
        raise SessionValidationError("live_start_apply_recovery_action_invalid")
    session_bearer, current = (
        _authenticate_authorization_cursor_under_lock(
            session_lease=session_lease,
            expected_session=expected_recovery_session,
        )
    )
    recovery = current.apply_recovery
    if not isinstance(recovery, Mapping) or recovery.get("recovery_stage") != "ACTIVE":
        raise SessionConflictError("live_start_apply_recovery_cursor_invalid")
    physical_action = expected_action in RUNTIME_APPLY_RECOVERY_ACTIONS
    if physical_action:
        _require_nonterminal_physical_cursor_slot_available(
            session_bearer=session_bearer,
            cursor_sha256=current.content_sha256,
        )
    if (
        expected_action in RUNTIME_APPLY_RECOVERY_ACTIONS
        and recovery.get("expected_action") != expected_action
        and not _is_unbound_file_action_retirement_alternate(
            recovery=recovery,
            action=expected_action,
        )
    ):
        raise SessionConflictError("live_start_apply_recovery_action_mismatch")
    _validate_apply_recovery_action_precondition_under_lock(
        recovery=recovery,
        action=expected_action,
        runtime_layout=current.runtime_layout_bootstrap,
    )
    owner_context: dict[str, Any] | None = None
    if expected_action in {
        "delete_owner_cleanup_entry",
        "retire_owner_target_root",
        "retire_old_owner_journal",
    }:
        owner = recovery.get("owner_retirement")
        if not isinstance(owner, Mapping):
            raise SessionConflictError(
                "live_start_owner_retirement_cursor_missing"
            )
        if expected_action == "delete_owner_cleanup_entry":
            path = (
                Path(owner["retired_target_path"])
                / owner["next_entry_relative_path"]
            )
        elif expected_action == "retire_owner_target_root":
            path = Path(owner["retired_target_path"])
        else:
            path = Path(owner["initial_owner_journal_path"])
        owner_context = {
            "owner_object_preexisting": os.path.lexists(path)
        }
    authorization = _mint_authorization_for_authenticated_cursor(
        authorization_type=RuntimeAttemptRecoveryAuthorization,
        session_bearer=session_bearer,
        current=current,
        family="nonterminal_apply_recovery",
        action=expected_action,
        claim_nonterminal_slot=physical_action,
        registered_successor=(
            _freeze_mapping(owner_context)
            if owner_context is not None
            else None
        ),
    )
    return authorization


def _discard_unused_nonterminal_apply_recovery_authorization(
    authorization: RuntimeAttemptRecoveryAuthorization,
    *,
    expected_action: str,
) -> bool:
    """Retire an unconsumed physical slot without re-reading a stale cursor."""

    if (
        type(authorization) is not RuntimeAttemptRecoveryAuthorization
        or not hasattr(authorization, "_opaque")
        or expected_action not in RUNTIME_APPLY_RECOVERY_ACTIONS
    ):
        raise SessionCapabilityError(
            "live_start_unused_apply_recovery_authorization_invalid"
        )
    bearer = authorization._opaque
    if not isinstance(bearer, _OpaqueBearer):
        raise SessionCapabilityError(
            "live_start_unused_apply_recovery_authorization_invalid"
        )
    with _AUTHORITY_REGISTRY_LOCK:
        bearer_registration = _OPAQUE_BEARER_REGISTRATIONS.get(id(bearer))
        carrier_registration = _ACTIVE_OPAQUE_CARRIERS.get(id(authorization))
        reverse_slot = _NONTERMINAL_PHYSICAL_SLOT_BY_BEARER.get(id(bearer))
        slot_contains_bearer = any(
            active_bearer is bearer
            for active_bearer in _ACTIVE_NONTERMINAL_PHYSICAL_SLOTS.values()
        )
        fully_inactive = (
            not bearer.active
            and not bearer.nonce
            and _ACTIVE_OPAQUE_BEARERS.get(id(bearer)) is None
            and bearer_registration is None
            and carrier_registration is None
            and reverse_slot is None
            and not slot_contains_bearer
            and _BOUND_PHYSICAL_POSTCONDITIONS.get(id(bearer)) is None
            and _BOUND_TERMINAL_OWNERLESS_ISSUERS.get(id(bearer)) is None
        )
        if fully_inactive:
            return False
        if (
            not bearer.active
            or not bearer.nonce
            or bearer.family != "nonterminal_apply_recovery"
            or bearer.action != expected_action
            or bearer.thread_id != threading.get_ident()
            or bearer.physical_slot_family != "nonterminal"
            or not bearer.session_bearer.active
            or bearer.session_bearer.thread_id != threading.get_ident()
            or not _session_context_is_registered(
                bearer=bearer.session_bearer
            )
            or _ACTIVE_OPAQUE_BEARERS.get(id(bearer)) is not bearer
            or bearer_registration is None
            or bearer_registration.bearer is not bearer
            or carrier_registration is None
            or carrier_registration[0] is not authorization
            or carrier_registration[1] is not bearer
            or not _opaque_bearer_registration_matches(bearer)
            or not _opaque_carrier_is_registered(
                carrier=authorization,
                bearer=bearer,
            )
            or not _nonterminal_physical_slot_is_consistent(bearer=bearer)
        ):
            raise SessionCapabilityError(
                "live_start_unused_apply_recovery_authorization_invalid"
            )
        _deregister_opaque_bearer(bearer=bearer)
        bearer.active = False
        bearer.nonce = ""
        return True


def _execute_apply_recovery_physical_step(
    *,
    recovery_authorization: RuntimeAttemptRecoveryAuthorization,
    action: RuntimeApplyRecoveryAction,
    physical_action: Callable[[], RuntimeApplyRecoveryPhysicalPostcondition],
) -> ApplyRecoveryStepReceipt:
    if action not in RUNTIME_APPLY_RECOVERY_ACTIONS:
        raise SessionValidationError("live_start_apply_recovery_action_invalid")
    consumed = _require_opaque_carrier(
        recovery_authorization,
        carrier_type=RuntimeAttemptRecoveryAuthorization,
        family="nonterminal_apply_recovery",
        action=action,
        consume=True,
        preserve_nonterminal_slot=True,
        capture_registered_state=True,
    )
    bearer = (
        consumed.bearer
        if isinstance(consumed, _OpaqueBearerConsumption)
        else recovery_authorization._opaque
    )
    slot_owner = bearer
    receipt_bearer: _OpaqueBearer | None = None
    try:
        if not isinstance(consumed, _OpaqueBearerConsumption):
            raise SessionCapabilityError(
                "live_start_apply_recovery_authorization_invalid"
            )
        owner_context: Mapping[str, Any] | None = None
        if action in {
            "delete_owner_cleanup_entry",
            "retire_owner_target_root",
            "retire_old_owner_journal",
        }:
            if not isinstance(consumed.successor, Mapping):
                raise SessionCapabilityError(
                    "live_start_owner_authorization_context_missing"
                )
            owner_context = consumed.successor
        elif consumed.successor is not None:
            raise SessionCapabilityError(
                "live_start_apply_recovery_authorization_invalid"
            )
        postcondition = physical_action()
        if (
            not isinstance(
                postcondition,
                RuntimeApplyRecoveryPhysicalPostcondition,
            )
            or postcondition.action != action
        ):
            raise SessionCapabilityError(
                "live_start_physical_postcondition_invalid"
            )
        if owner_context is not None:
            evidence = dict(postcondition.evidence)
            evidence["_owner_object_preexisting"] = owner_context.get(
                "owner_object_preexisting"
            )
            postcondition = RuntimeApplyRecoveryPhysicalPostcondition(
                action=action,
                evidence=evidence,
            )
        receipt_bearer = _OpaqueBearer(
            session_bearer=consumed.session_bearer,
            family="nonterminal_apply_recovery_receipt",
            cursor_sha256=consumed.cursor_sha256,
            action=action,
        )
        receipt_bearer.successor = postcondition
        receipt = _mint_registered_opaque_carrier(
            carrier_type=ApplyRecoveryStepReceipt,
            bearer=receipt_bearer,
            nonterminal_slot_source=bearer,
        )
        slot_owner = receipt_bearer
        return receipt
    except BaseException:
        if receipt_bearer is not None:
            _deregister_opaque_bearer(bearer=receipt_bearer)
        _release_nonterminal_physical_slot(bearer=slot_owner)
        _release_nonterminal_physical_slot(bearer=bearer)
        raise


def authorize_terminal_retirement_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_retirement_session: LiveStartSession,
    runtime_observation_receipt: RuntimeObservationReceipt | None = None,
) -> TerminalRetirementAuthorization:
    session_bearer, current = (
        _authenticate_authorization_cursor_under_lock(
            session_lease=session_lease,
            expected_session=expected_retirement_session,
        )
    )
    retirement = current.terminal_retirement
    if not isinstance(retirement, Mapping):
        raise SessionConflictError("live_start_terminal_retirement_missing")
    action = _terminal_action_for_retirement(
        retirement,
        attempt_acknowledgement=(
            current.attempt_acknowledgement
        ),
    )
    if action == "admission_release_authorized":
        if runtime_observation_receipt is None:
            raise SessionCapabilityError(
                "live_start_terminal_release_observation_missing"
            )
        postcondition = _consume_runtime_observation_receipt_under_lock(
            receipt=runtime_observation_receipt,
            session_lease=session_lease,
            expected_session=current,
            observation_family="terminal_release",
            apply_attempt_id=_session_apply_attempt_id(current),
        )
        if postcondition.evidence.get(
            "terminal_retirement_sha256"
        ) != retirement.get("content_sha256"):
            raise SessionCapabilityError(
                "live_start_terminal_release_observation_invalid"
            )
    elif runtime_observation_receipt is not None:
        raise SessionCapabilityError(
            "live_start_terminal_release_observation_unexpected"
        )
    if action in TERMINAL_RESOLUTION_PHYSICAL_ACTIONS:
        _require_terminal_physical_cursor_slot_available(
            session_bearer=session_bearer,
            cursor_sha256=current.content_sha256,
        )
    owner_context: dict[str, Any] | None = None
    if action == "physical_recovery_advanced":
        resolution = retirement.get("terminal_resolution_evidence")
        if isinstance(resolution, Mapping) and isinstance(
            resolution.get("owner_retirement"),
            Mapping,
        ):
            current_owner = _validate_owner_retirement_document(
                resolution["owner_retirement"]
            )
            current_external_raw = resolution.get("external_file_action")
            current_external = (
                validate_embedded_document(
                    "external_file_action",
                    current_external_raw,
                )
                if isinstance(current_external_raw, Mapping)
                else None
            )
            owner_action = _owner_action_for_cursor(
                owner=current_owner,
                external=current_external,
            )
            unbound_staging_residue = (
                owner_action == "materialize_file_action_staging"
                and current_external is not None
                and current_external.get("stage") == "PLANNED"
                and (
                    os.path.lexists(
                        Path(str(current_external["staging_path"]))
                    )
                    or os.path.lexists(
                        Path(str(current_external["inner_temp_path"]))
                    )
                )
            )
            _validate_owner_action_precondition_under_lock(
                recovery={
                    "owner_retirement": current_owner,
                    "external_file_action": current_external,
                },
                action=owner_action,
                enforce_cursor_binding=False,
                runtime_layout=current.runtime_layout_bootstrap,
                allow_unbound_staging_residue=(
                    unbound_staging_residue
                ),
            )
            effective_owner_action = (
                "retire_unbound_file_action_staging"
                if unbound_staging_residue
                else owner_action
            )
            owner_context = {"owner_action": effective_owner_action}
            if owner_action in {
                "delete_owner_cleanup_entry",
                "retire_owner_target_root",
                "retire_old_owner_journal",
            }:
                if owner_action == "delete_owner_cleanup_entry":
                    owner_path = (
                        Path(current_owner["retired_target_path"])
                        / current_owner["next_entry_relative_path"]
                    )
                elif owner_action == "retire_owner_target_root":
                    owner_path = Path(
                        current_owner["retired_target_path"]
                    )
                else:
                    owner_path = Path(
                        current_owner["initial_owner_journal_path"]
                    )
                owner_context["owner_object_preexisting"] = (
                    os.path.lexists(owner_path)
                )
        elif isinstance(resolution, Mapping):
            ownerless_external_raw = resolution.get(
                "external_file_action"
            )
            ownerless_external = (
                validate_embedded_document(
                    "external_file_action",
                    ownerless_external_raw,
                )
                if isinstance(ownerless_external_raw, Mapping)
                else None
            )
            if (
                ownerless_external is not None
                and ownerless_external.get("stage") == "PLANNED"
                and ownerless_external.get("action_kind")
                == "materialize_file_action_staging"
                and (
                    os.path.lexists(
                        Path(str(ownerless_external["staging_path"]))
                    )
                    or os.path.lexists(
                        Path(str(ownerless_external["inner_temp_path"]))
                    )
                )
            ):
                owner_context = {
                    "ownerless": True,
                    "owner_action": (
                        "retire_unbound_file_action_staging"
                    )
                }
    elif action == "stabilized":
        resolution = retirement.get("terminal_resolution_evidence")
        owner_raw = (
            resolution.get("owner_retirement")
            if isinstance(resolution, Mapping)
            else None
        )
        if isinstance(owner_raw, Mapping):
            if (
                owner_raw.get("stage") != "OWNER_RETIRED"
                or resolution.get("external_file_action") is not None
                or resolution.get("cleanup_stage") is not None
                or resolution.get("resolved_physical_disposition")
                != "COMMITTED"
            ):
                raise SessionConflictError(
                    "live_start_terminal_owner_stabilization_invalid"
                )
            _validate_owner_action_precondition_under_lock(
                recovery={
                    "owner_retirement": owner_raw,
                    "external_file_action": None,
                },
                action="observe_owner_retirement_completed",
                enforce_cursor_binding=False,
                runtime_layout=current.runtime_layout_bootstrap,
            )
    if action == "materialize_terminal_cleanup_inventory_staging":
        resolution = retirement["terminal_resolution_evidence"]
        external = resolution["external_file_action"]
        if os.path.lexists(Path(external["staging_path"])) or os.path.lexists(
            Path(external["inner_temp_path"])
        ):
            action = "retire_unbound_terminal_cleanup_inventory_staging"
    authorization_bearer = _OpaqueBearer(
        session_bearer=session_bearer,
        family="terminal_retirement",
        cursor_sha256=current.content_sha256,
        action=action,
    )
    if action == "release_runtime_admission":
        authorization_bearer.successor = (
            _RuntimeAdmissionReleasePrecondition(
                admission_path=Path(
                    retirement["runtime_admission_path"]
                ),
                admission_parent_identity=_require_identity(
                    retirement["runtime_admission_parent_identity"],
                    "runtime_admission_parent_identity",
                ),
                historical_admission_identity=_require_identity(
                    retirement["runtime_admission_identity"],
                    "runtime_admission_identity",
                ),
                historical_admission_sha256=retirement[
                    "runtime_admission_sha256"
                ],
            )
        )
    authorization = _mint_registered_opaque_carrier(
        carrier_type=TerminalRetirementAuthorization,
        bearer=authorization_bearer,
        claim_terminal_slot=(
            action in TERMINAL_RESOLUTION_PHYSICAL_ACTIONS
        ),
        terminal_owner_context=owner_context,
    )
    return authorization


def _terminal_action_for_cursor(*, operation: Any, stage: Any) -> str:
    if operation == "ack_success":
        raise SessionConflictError(
            "live_start_acknowledgement_context_missing"
        )
    if stage == "EVIDENCE_RETIRED":
        return "admission_release_authorized"
    if stage == "ADMISSION_RELEASE_AUTHORIZED":
        return "release_runtime_admission"
    if operation == "release_resolved_terminal":
        resolution_actions = {
            "RECOVERY_PREPARED": "physical_recovery_advanced",
            "RECOVERY_INVENTORY_BOUND": "cleaning_started",
            "RECOVERY_CLEANING": "delete_cleanup_entry",
            "RECOVERY_JOURNAL_RETIRED": "retire_cleanup_fence",
            "RECOVERY_FENCE_RETIRED": "retire_cleanup_inventory",
            "RECOVERY_INVENTORY_RETIRED": "stabilized",
            "RECOVERY_STABILIZED": "evidence_retired",
        }
        try:
            return resolution_actions[stage]
        except KeyError as error:
            raise SessionConflictError("live_start_terminal_cursor_invalid") from error
    if stage == "PREPARED":
        return "evidence_retired"
    raise SessionConflictError("live_start_terminal_cursor_invalid")


def _terminal_action_for_retirement(
    retirement: Mapping[str, Any],
    *,
    attempt_acknowledgement: Mapping[str, Any] | None = None,
) -> str:
    operation = retirement.get("operation")
    stage = retirement.get("stage")
    if operation == "ack_success":
        if stage == "EVIDENCE_RETIRED":
            return "admission_release_authorized"
        if stage == "ADMISSION_RELEASE_AUTHORIZED":
            return "release_runtime_admission"
        if not isinstance(attempt_acknowledgement, Mapping):
            raise SessionConflictError(
                "live_start_acknowledgement_context_missing"
            )
        acknowledgement_action = attempt_acknowledgement.get(
            "acknowledgement_action"
        )
        if stage == "PREPARED":
            if acknowledgement_action == "retain_target_owner_delete_fence":
                return "retire_ack_fence"
            if acknowledgement_action == "delete_nonowning_attempt_and_fence":
                return "retire_ack_journal"
        elif (
            stage == "ACK_JOURNAL_RETIRED"
            and acknowledgement_action
            == "delete_nonowning_attempt_and_fence"
        ):
            return "retire_ack_fence"
        raise SessionConflictError(
            "live_start_acknowledgement_cursor_invalid"
        )
    if operation != "release_resolved_terminal":
        return _terminal_action_for_cursor(operation=operation, stage=stage)
    resolution = retirement.get("terminal_resolution_evidence")
    if not isinstance(resolution, Mapping):
        raise SessionConflictError("live_start_terminal_resolution_missing")
    cleanup_stage = resolution.get("cleanup_stage")
    external = resolution.get("external_file_action")
    if stage == "RECOVERY_PREPARED":
        owner = resolution.get("owner_retirement")
        if (
            owner is None
            and external is None
            and cleanup_stage is None
            and resolution.get("resolved_physical_disposition")
            == "COMMITTED"
        ):
            return "stabilized"
        if isinstance(owner, Mapping):
            if (
                owner.get("stage") == "OWNER_RETIRED"
                and external is None
                and cleanup_stage is None
                and resolution.get("resolved_physical_disposition")
                == "COMMITTED"
            ):
                return "stabilized"
            return "physical_recovery_advanced"
        if cleanup_stage == "PREPARED" and isinstance(external, Mapping):
            if external.get("stage") == "PLANNED":
                return "materialize_terminal_cleanup_inventory_staging"
            if external.get("stage") == "STAGING_BOUND":
                return "commit_bound_terminal_cleanup_inventory"
            raise SessionConflictError(
                "live_start_terminal_cleanup_external_stage_invalid"
            )
        if (
            cleanup_stage is None
            and external is None
            and resolution.get("resolved_physical_disposition")
            == "NOT_COMMITTED"
        ):
            return (
                "retire_cleanup_journal"
                if resolution.get("predecessor_journal_path") is not None
                else "retire_cleanup_fence"
            )
        return "physical_recovery_advanced"
    if stage == "RECOVERY_INVENTORY_BOUND":
        return "cleaning_started"
    if stage == "RECOVERY_CLEANING":
        count = resolution.get("cleanup_entry_count")
        cursor = resolution.get("cleanup_cursor")
        if type(count) is not int or type(cursor) is not int or not 0 <= cursor <= count:
            raise SessionConflictError(
                "live_start_terminal_cleanup_cursor_invalid"
            )
        return "delete_cleanup_entry" if cursor < count else "retire_cleanup_journal"
    if stage == "RECOVERY_JOURNAL_RETIRED":
        return "retire_cleanup_fence"
    if stage == "RECOVERY_FENCE_RETIRED":
        if cleanup_stage == "FENCE_RETIRED":
            return "retire_cleanup_inventory"
        return "stabilized"
    if stage == "RECOVERY_INVENTORY_RETIRED":
        return "stabilized"
    if stage == "RECOVERY_STABILIZED":
        return "evidence_retired"
    if stage == "EVIDENCE_RETIRED":
        return "admission_release_authorized"
    if stage == "ADMISSION_RELEASE_AUTHORIZED":
        return "release_runtime_admission"
    raise SessionConflictError("live_start_terminal_cursor_invalid")


def _mint_terminal_ownerless_successor_issuer(
    *,
    terminal_authorization: TerminalRetirementAuthorization,
    physical_action: Callable[
        [], TerminalResolutionPhysicalPostcondition
    ],
    predecessor_resolution: Mapping[str, Any],
) -> TerminalOwnerlessSuccessorIssuer:
    """Bind the vetted Runtime projector to one exact ownerless cursor."""

    terminal_bearer = _require_opaque_carrier(
        terminal_authorization,
        carrier_type=TerminalRetirementAuthorization,
        family="terminal_retirement",
        action="physical_recovery_advanced",
        consume=False,
    )
    if not callable(physical_action):
        raise SessionCapabilityError(
            "live_start_terminal_ownerless_issuer_invalid"
        )
    predecessor = _validate_terminal_resolution_document(
        predecessor_resolution
    )
    external = predecessor.get("external_file_action")
    if predecessor.get("owner_retirement") is not None or (
        external is not None and not isinstance(external, Mapping)
    ):
        raise SessionCapabilityError(
            "live_start_terminal_ownerless_issuer_invalid"
        )
    try:
        raw, identity = _read_bound_file(
            terminal_bearer.session_bearer.session_root / "session.json",
            expected_parent_identity=(
                terminal_bearer.session_bearer.session_root_identity
            ),
            maximum_size=LIVE_START_SESSION_MAX_BYTES,
        )
        current = _load_session_bytes(raw, session_identity=identity)
        retirement = current.terminal_retirement
        current_resolution = (
            retirement.get("terminal_resolution_evidence")
            if isinstance(retirement, Mapping)
            else None
        )
        if (
            current.content_sha256 != terminal_bearer.cursor_sha256
            or not isinstance(current_resolution, Mapping)
            or current_resolution.get("content_sha256")
            != predecessor.get("content_sha256")
            or current_resolution != predecessor
        ):
            raise SessionCapabilityError(
                "live_start_terminal_ownerless_issuer_invalid"
            )
    except SessionCapabilityError:
        raise
    except (OSError, RuntimeError, ValueError) as error:
        raise SessionCapabilityError(
            "live_start_terminal_ownerless_issuer_invalid"
        ) from error
    issuer_bearer = _OpaqueBearer(
        session_bearer=terminal_bearer.session_bearer,
        family="terminal_ownerless_successor_issuer",
        cursor_sha256=terminal_bearer.cursor_sha256,
        action="physical_recovery_advanced",
    )
    issuer_bearer.successor = physical_action
    issuer_bearer.physical_precondition = _freeze_mapping(
        {
            "apply_attempt_id": predecessor.get("apply_attempt_id"),
            "action_index": predecessor.get("action_index"),
            "predecessor_resolution_sha256": predecessor.get(
                "content_sha256"
            ),
            "predecessor_external_sha256": (
                external.get("content_sha256")
                if isinstance(external, Mapping)
                else None
            ),
        }
    )
    return _mint_registered_opaque_carrier(
        carrier_type=TerminalOwnerlessSuccessorIssuer,
        bearer=issuer_bearer,
        ownerless_parent_terminal_bearer=terminal_bearer,
    )


def _execute_terminal_resolution_physical_step(
    *,
    terminal_authorization: TerminalRetirementAuthorization,
    action: str,
    physical_action: Callable[[], TerminalResolutionPhysicalPostcondition | SuccessAckStepEvidence],
    ownerless_successor_issuer: TerminalOwnerlessSuccessorIssuer | None = None,
) -> TerminalResolutionStepReceipt:
    if action not in TERMINAL_RESOLUTION_PHYSICAL_ACTIONS:
        raise SessionValidationError("live_start_terminal_resolution_action_invalid")
    terminal_bearer = _require_opaque_carrier(
        terminal_authorization,
        carrier_type=TerminalRetirementAuthorization,
        family="terminal_retirement",
        action=action,
        consume=False,
    )
    with _AUTHORITY_REGISTRY_LOCK:
        terminal_registration = _OPAQUE_BEARER_REGISTRATIONS.get(
            id(terminal_bearer)
        )
        if (
            terminal_registration is None
            or terminal_registration.bearer is not terminal_bearer
            or not _opaque_bearer_registration_matches(terminal_bearer)
        ):
            raise SessionCapabilityError(
                "live_start_terminal_resolution_authorization_invalid"
            )
    owner_context = (
        terminal_registration.registered_terminal_owner_context
        if action == "physical_recovery_advanced"
        else None
    )
    ownerless_physical_recovery = (
        action == "physical_recovery_advanced"
        and (
            owner_context is None
            or owner_context.get("ownerless") is True
        )
    )
    issuer_bearer: _OpaqueBearer | None = None
    issuer_context: Mapping[str, Any] | None = None
    issuer_parent_registration: _OpaqueBearerRegistration | None = None
    if ownerless_physical_recovery:
        if ownerless_successor_issuer is None:
            raise SessionCapabilityError(
                "live_start_terminal_ownerless_issuer_missing"
            )
        issuer_bearer = _require_opaque_carrier(
            ownerless_successor_issuer,
            carrier_type=TerminalOwnerlessSuccessorIssuer,
            family="terminal_ownerless_successor_issuer",
            action=action,
            consume=False,
        )
        issuer_context = issuer_bearer.physical_precondition
        with _AUTHORITY_REGISTRY_LOCK:
            issuer_binding = _BOUND_TERMINAL_OWNERLESS_ISSUERS.get(
                id(issuer_bearer)
            )
            issuer_parent_registration = _OPAQUE_BEARER_REGISTRATIONS.get(
                id(terminal_bearer)
            )
        if (
            issuer_bearer.session_bearer is not terminal_bearer.session_bearer
            or issuer_bearer.cursor_sha256 != terminal_bearer.cursor_sha256
            or issuer_bearer.successor is not physical_action
            or not isinstance(issuer_context, Mapping)
            or issuer_binding is None
            or issuer_binding.issuer_bearer is not issuer_bearer
            or issuer_binding.parent_terminal_bearer is not terminal_bearer
            or issuer_binding.parent_registration
            is not issuer_parent_registration
            or issuer_binding.physical_action is not physical_action
            or issuer_binding.physical_precondition is not issuer_context
            or _ACTIVE_TERMINAL_OWNERLESS_ISSUER_BY_PARENT.get(
                id(terminal_bearer)
            )
            is not issuer_bearer
            or set(issuer_context)
            != {
                "apply_attempt_id",
                "action_index",
                "predecessor_resolution_sha256",
                "predecessor_external_sha256",
            }
        ):
            raise SessionCapabilityError(
                "live_start_terminal_ownerless_issuer_invalid"
            )
    elif ownerless_successor_issuer is not None:
        raise SessionCapabilityError(
            "live_start_terminal_ownerless_issuer_unexpected"
        )
    try:
        terminal_consumed = _require_opaque_carrier(
            terminal_authorization,
            carrier_type=TerminalRetirementAuthorization,
            family="terminal_retirement",
            action=action,
            consume=True,
            preserve_terminal_slot=True,
            capture_registered_state=True,
        )
        if not isinstance(terminal_consumed, _OpaqueBearerConsumption):
            raise SessionCapabilityError(
                "live_start_terminal_resolution_authorization_invalid"
            )
    except BaseException:
        if issuer_bearer is not None:
            _deregister_opaque_bearer(bearer=issuer_bearer)
            issuer_bearer.active = False
            issuer_bearer.nonce = ""
        _deregister_opaque_bearer(bearer=terminal_bearer)
        terminal_bearer.active = False
        terminal_bearer.nonce = ""
        _release_terminal_physical_slot(bearer=terminal_bearer)
        raise
    bearer = terminal_consumed.bearer
    issued_physical_action = physical_action
    try:
        if (
            terminal_consumed.registration is not terminal_registration
            or terminal_consumed.terminal_owner_context is not owner_context
        ):
            raise SessionCapabilityError(
                "live_start_terminal_resolution_authorization_invalid"
            )
        owner_context = terminal_consumed.terminal_owner_context
        if issuer_bearer is not None:
            consumed_issuer = _require_opaque_carrier(
                ownerless_successor_issuer,
                carrier_type=TerminalOwnerlessSuccessorIssuer,
                family="terminal_ownerless_successor_issuer",
                action=action,
                consume=True,
                capture_registered_state=True,
            )
            if (
                not isinstance(consumed_issuer, _OpaqueBearerConsumption)
                or consumed_issuer.family
                != "terminal_ownerless_successor_issuer"
                or consumed_issuer.action != action
                or consumed_issuer.thread_id != threading.get_ident()
                or consumed_issuer.session_bearer
                is not terminal_consumed.session_bearer
                or consumed_issuer.cursor_sha256
                != terminal_consumed.cursor_sha256
                or not consumed_issuer.successor_was_registry_bound
                or consumed_issuer.successor is not physical_action
                or not isinstance(
                    consumed_issuer.physical_precondition,
                    Mapping,
                )
                or consumed_issuer.physical_precondition is not issuer_context
                or consumed_issuer.parent_terminal_bearer is not bearer
                or consumed_issuer.parent_registration
                is not terminal_consumed.registration
                or issuer_parent_registration
                is not terminal_consumed.registration
            ):
                raise SessionCapabilityError(
                    "live_start_terminal_ownerless_issuer_invalid"
                )
            issued_physical_action = consumed_issuer.successor
            issuer_context = consumed_issuer.physical_precondition
    except BaseException:
        if issuer_bearer is not None:
            _deregister_opaque_bearer(bearer=issuer_bearer)
            issuer_bearer.active = False
            issuer_bearer.nonce = ""
        _release_terminal_physical_slot(bearer=bearer)
        raise
    slot_owner = bearer
    receipt_bearer: _OpaqueBearer | None = None
    try:
        result = issued_physical_action()
        expected_postcondition_type: type[
            TerminalResolutionPhysicalPostcondition | SuccessAckStepEvidence
        ] = (
            SuccessAckStepEvidence
            if action in {"retire_ack_journal", "retire_ack_fence"}
            else TerminalResolutionPhysicalPostcondition
        )
        if not isinstance(result, expected_postcondition_type):
            raise SessionCapabilityError(
                "live_start_terminal_resolution_postcondition_family_invalid"
            )
        if result.action != action:
            raise SessionCapabilityError(
                "live_start_terminal_resolution_postcondition_invalid"
            )
        if ownerless_physical_recovery:
            evidence = dict(result.evidence)
            successor_retirement = evidence.get("terminal_retirement")
            if not isinstance(successor_retirement, Mapping):
                raise SessionCapabilityError(
                    "live_start_terminal_ownerless_successor_missing"
                )
            successor_retirement = validate_embedded_document(
                "terminal_retirement",
                successor_retirement,
            )
            successor_resolution = successor_retirement.get(
                "terminal_resolution_evidence"
            )
            if not isinstance(successor_resolution, Mapping):
                raise SessionCapabilityError(
                    "live_start_terminal_ownerless_successor_missing"
                )
            assert issuer_context is not None
            evidence["_terminal_ownerless_issuer_context"] = {
                **dict(issuer_context),
                "successor_retirement_sha256": successor_retirement.get(
                    "content_sha256"
                ),
                "successor_resolution_sha256": successor_resolution.get(
                    "content_sha256"
                ),
            }
            result = TerminalResolutionPhysicalPostcondition(
                action=result.action,
                evidence=evidence,
            )
        if action == "physical_recovery_advanced" and isinstance(
            owner_context,
            Mapping,
        ):
            owner_action = owner_context.get("owner_action")
            if not isinstance(owner_action, str):
                raise SessionCapabilityError(
                    "live_start_terminal_owner_action_missing"
                )
            evidence = dict(result.evidence)
            evidence["_owner_object_preexisting"] = owner_context.get(
                "owner_object_preexisting"
            )
            evidence["_terminal_owner_action"] = owner_action
            result = TerminalResolutionPhysicalPostcondition(
                action=result.action,
                evidence=evidence,
            )
        receipt_bearer = _OpaqueBearer(
            session_bearer=terminal_consumed.session_bearer,
            family="terminal_retirement_receipt",
            cursor_sha256=terminal_consumed.cursor_sha256,
            action=action,
        )
        receipt_bearer.successor = result
        receipt = _mint_registered_opaque_carrier(
            carrier_type=TerminalResolutionStepReceipt,
            bearer=receipt_bearer,
            terminal_slot_source=bearer,
        )
        slot_owner = receipt_bearer
        return receipt
    except BaseException:
        if receipt_bearer is not None:
            _deregister_opaque_bearer(bearer=receipt_bearer)
        _release_terminal_physical_slot(bearer=slot_owner)
        _release_terminal_physical_slot(bearer=bearer)
        raise


def _authorize_runtime_observation_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    observation_family: RuntimeObservationFamily,
    apply_attempt_id: str,
) -> RuntimeObservationAuthorization:
    if observation_family not in RUNTIME_OBSERVATION_FAMILIES:
        raise SessionValidationError("live_start_runtime_observation_family_invalid")
    _require_run_id(apply_attempt_id)
    return _mint_authorization_under_lock(
        authorization_type=RuntimeObservationAuthorization,
        session_lease=session_lease,
        expected_session=expected_session,
        family=f"runtime_observation:{observation_family}",
        action=apply_attempt_id,
    )


def _execute_runtime_observation(
    *,
    observation_authorization: RuntimeObservationAuthorization,
    observation_family: RuntimeObservationFamily,
    read_only_observation: Callable[[], RuntimeObservationPostcondition],
) -> RuntimeObservationReceipt:
    if observation_family not in RUNTIME_OBSERVATION_FAMILIES:
        raise SessionValidationError("live_start_runtime_observation_family_invalid")
    if not isinstance(observation_authorization, RuntimeObservationAuthorization):
        raise SessionCapabilityError("live_start_runtime_observation_capability_forged")
    bearer = observation_authorization._opaque
    if bearer.family != f"runtime_observation:{observation_family}":
        raise SessionCapabilityError("live_start_runtime_observation_family_mismatch")
    consumed = _require_opaque_carrier(
        observation_authorization,
        carrier_type=RuntimeObservationAuthorization,
        family=bearer.family,
        action=bearer.action,
        consume=True,
        capture_registered_state=True,
    )
    if not isinstance(consumed, _OpaqueBearerConsumption):
        raise SessionCapabilityError(
            "live_start_runtime_observation_capability_invalid"
        )
    result = read_only_observation()
    if not isinstance(result, RuntimeObservationPostcondition) or result.observation_family != observation_family:
        raise SessionCapabilityError("live_start_runtime_observation_postcondition_invalid")
    receipt_bearer = _OpaqueBearer(
        session_bearer=consumed.session_bearer,
        family=f"runtime_observation_receipt:{observation_family}",
        cursor_sha256=consumed.cursor_sha256,
        action=consumed.action,
    )
    receipt_bearer.successor = result
    return _mint_registered_opaque_carrier(
        carrier_type=RuntimeObservationReceipt,
        bearer=receipt_bearer,
    )


def _consume_runtime_observation_receipt_under_lock(
    *,
    receipt: RuntimeObservationReceipt,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    observation_family: RuntimeObservationFamily,
    apply_attempt_id: str,
) -> RuntimeObservationPostcondition:
    _require_session_lease(session_lease)
    _require_run_id(apply_attempt_id)
    current = _load_expected_predecessor_under_lock(
        session_lease=session_lease,
        expected_session=expected_session,
    )
    if (
        not isinstance(receipt, RuntimeObservationReceipt)
        or not hasattr(receipt, "_opaque")
        or not isinstance(receipt._opaque, _OpaqueBearer)
    ):
        raise SessionCapabilityError(
            "live_start_runtime_observation_receipt_forged"
        )
    bearer = receipt._opaque
    if not _opaque_carrier_is_registered(carrier=receipt, bearer=bearer):
        raise SessionCapabilityError(
            "live_start_runtime_observation_receipt_forged"
        )
    if (
        bearer.session_bearer is not session_lease.lock_token._bearer
        or bearer.cursor_sha256 != current.content_sha256
    ):
        raise SessionCapabilityError(
            "live_start_runtime_observation_receipt_session_or_cursor_mismatch"
        )
    consumed = _require_opaque_carrier(
        receipt,
        carrier_type=RuntimeObservationReceipt,
        family=f"runtime_observation_receipt:{observation_family}",
        action=apply_attempt_id,
        consume=True,
        capture_registered_state=True,
    )
    if (
        not isinstance(consumed, _OpaqueBearerConsumption)
        or consumed.session_bearer is not session_lease.lock_token._bearer
        or consumed.family
        != f"runtime_observation_receipt:{observation_family}"
        or consumed.action != apply_attempt_id
        or consumed.cursor_sha256 != current.content_sha256
        or not consumed.successor_was_registry_bound
    ):
        raise SessionCapabilityError(
            "live_start_runtime_observation_receipt_postcondition_invalid"
        )
    postcondition = consumed.successor
    if (
        not isinstance(postcondition, RuntimeObservationPostcondition)
        or postcondition.observation_family != observation_family
        or postcondition.action != apply_attempt_id
    ):
        raise SessionCapabilityError(
            "live_start_runtime_observation_receipt_postcondition_invalid"
        )
    return postcondition


def _session_apply_attempt_id(session: LiveStartSession) -> str:
    for container in (
        session.apply_recovery,
        session.closed_apply_recovery_commitment,
        session.runtime_layout_bootstrap,
        session.result_intent,
        session.terminal_retirement,
        session.pending_transition,
    ):
        if isinstance(container, Mapping):
            attempt_id = container.get("apply_attempt_id")
            if attempt_id is not None:
                _require_run_id(attempt_id)
                return attempt_id
    raise SessionConflictError("live_start_apply_attempt_id_missing")


def _execute_output_operation_admission_physical_step(
    *,
    admission_authorization: OutputOperationAdmissionAuthorization,
    action: str,
    physical_action: Callable[[], OutputOperationAdmissionPhysicalPostcondition],
) -> OutputOperationAdmissionStepReceipt:
    if action not in OUTPUT_OPERATION_ADMISSION_ACTIONS:
        raise SessionValidationError("live_start_output_operation_action_invalid")
    return _execute_physical_step(
        authorization=admission_authorization,
        authorization_type=OutputOperationAdmissionAuthorization,
        receipt_type=OutputOperationAdmissionStepReceipt,
        postcondition_type=OutputOperationAdmissionPhysicalPostcondition,
        family="output_operation_admission",
        action=action,
        physical_action=physical_action,
    )


def _execute_output_child_bootstrap_physical_step(
    *,
    bootstrap_authorization: OutputChildBootstrapAuthorization,
    action: str,
    physical_action: Callable[[], OutputChildBootstrapPhysicalPostcondition],
) -> OutputChildBootstrapStepReceipt:
    if action not in OUTPUT_CHILD_BOOTSTRAP_ACTIONS:
        raise SessionValidationError("live_start_output_bootstrap_action_invalid")
    return _execute_physical_step(
        authorization=bootstrap_authorization,
        authorization_type=OutputChildBootstrapAuthorization,
        receipt_type=OutputChildBootstrapStepReceipt,
        postcondition_type=OutputChildBootstrapPhysicalPostcondition,
        family="output_child_bootstrap",
        action=action,
        physical_action=physical_action,
    )


def _execute_runtime_admission_physical_step(
    *,
    admission_authorization: RuntimeAdmissionAuthorization,
    action: str,
    physical_action: Callable[[], RuntimeAdmissionPhysicalPostcondition],
) -> RuntimeAdmissionStepReceipt:
    if action not in RUNTIME_ADMISSION_ACTIONS:
        raise SessionValidationError("live_start_runtime_admission_action_invalid")
    return _execute_physical_step(
        authorization=admission_authorization,
        authorization_type=RuntimeAdmissionAuthorization,
        receipt_type=RuntimeAdmissionStepReceipt,
        postcondition_type=RuntimeAdmissionPhysicalPostcondition,
        family="runtime_admission",
        action=action,
        physical_action=physical_action,
    )


def _execute_runtime_layout_bootstrap_physical_step(
    *,
    layout_authorization: RuntimeLayoutBootstrapAuthorization,
    action: str,
    physical_action: Callable[[], RuntimeLayoutBootstrapPhysicalPostcondition],
) -> RuntimeLayoutBootstrapStepReceipt:
    if action not in RUNTIME_LAYOUT_BOOTSTRAP_ACTIONS:
        raise SessionValidationError("live_start_runtime_layout_action_invalid")
    return _execute_physical_step(
        authorization=layout_authorization,
        authorization_type=RuntimeLayoutBootstrapAuthorization,
        receipt_type=RuntimeLayoutBootstrapStepReceipt,
        postcondition_type=RuntimeLayoutBootstrapPhysicalPostcondition,
        family="runtime_layout_bootstrap",
        action=action,
        physical_action=physical_action,
    )


def _execute_output_operation_release(
    *,
    release_authorization: OutputOperationAdmissionReleaseAuthorization,
    physical_action: Callable[[], _PhysicalResultT],
) -> _PhysicalResultT:
    _require_opaque_carrier(
        release_authorization,
        carrier_type=OutputOperationAdmissionReleaseAuthorization,
        family="output_operation_release",
        action="release_output_operation_admission",
        consume=True,
    )
    return physical_action()


def _execute_runtime_admission_release(
    *,
    terminal_authorization: TerminalRetirementAuthorization,
    action: Literal["release_runtime_admission"],
    physical_action: Callable[[], RuntimeAdmissionReleasePostcondition],
) -> RuntimeAdmissionReleasePostcondition:
    if action != "release_runtime_admission":
        raise SessionValidationError("live_start_runtime_admission_release_action_invalid")
    consumed = _require_opaque_carrier(
        terminal_authorization,
        carrier_type=TerminalRetirementAuthorization,
        family="terminal_retirement",
        action=action,
        consume=True,
        capture_registered_state=True,
    )
    if (
        not isinstance(consumed, _OpaqueBearerConsumption)
        or consumed.family != "terminal_retirement"
        or consumed.action != action
        or consumed.thread_id != threading.get_ident()
        or not consumed.session_bearer.active
        or not _session_context_is_registered(
            bearer=consumed.session_bearer
        )
        or not consumed.successor_was_registry_bound
    ):
        raise SessionCapabilityError(
            "live_start_runtime_admission_release_binding_invalid"
        )
    expected = consumed.successor
    if type(expected) is not _RuntimeAdmissionReleasePrecondition:
        raise SessionCapabilityError(
            "live_start_runtime_admission_release_binding_invalid"
        )
    result = physical_action()
    if not isinstance(result, RuntimeAdmissionReleasePostcondition):
        raise SessionCapabilityError("live_start_runtime_admission_release_postcondition_invalid")
    if any(
        actual != getattr(expected, field_name)
        for field_name, actual in (
            ("admission_path", result.admission_path),
            ("admission_parent_identity", result.admission_parent_identity),
            (
                "historical_admission_identity",
                result.historical_admission_identity,
            ),
            (
                "historical_admission_sha256",
                result.historical_admission_sha256,
            ),
        )
    ):
        raise SessionCapabilityError(
            "live_start_runtime_admission_release_binding_invalid"
        )
    return result


def _build_external_file_action(
    *,
    action_kind: str,
    action_index: int,
    final_path: Path,
    staging_path: Path,
    inner_temp_path: Path,
    parent_identity: PathIdentity,
    predecessor_identity: PathIdentity | None,
    predecessor_size: int | None,
    predecessor_sha256: str | None,
    planned_successor_size: int,
    planned_successor_sha256: str,
    commit_mode: Literal["create_no_replace", "replace_exact"],
) -> Mapping[str, Any]:
    predecessor_state = "absent" if predecessor_identity is None else "exact"
    return seal_embedded_document(
        "external_file_action",
        {
            "schema_version": LIVE_START_EXTERNAL_FILE_ACTION_SCHEMA_VERSION,
            "action_kind": action_kind,
            "action_index": action_index,
            "stage": "PLANNED",
            "final_path": str(Path(final_path).absolute()),
            "staging_path": str(Path(staging_path).absolute()),
            "inner_temp_path": str(Path(inner_temp_path).absolute()),
            "parent_identity": parent_identity,
            "predecessor_state": predecessor_state,
            "predecessor_identity": predecessor_identity,
            "predecessor_size": predecessor_size,
            "predecessor_sha256": predecessor_sha256,
            "planned_successor_size": planned_successor_size,
            "planned_successor_sha256": planned_successor_sha256,
            "staging_identity": None,
            "staging_size": None,
            "staging_sha256": None,
            "commit_mode": commit_mode,
        },
    )


def _empty_pending_transition(
    *,
    session: LiveStartSession,
    operation: str,
    external_file_action: Mapping[str, Any] | None,
) -> dict[str, Any]:
    value = {field_name: None for field_name in _PENDING_TRANSITION_FIELDS}
    value.update(
        {
            "schema_version": LIVE_START_PENDING_TRANSITION_SCHEMA_VERSION,
            "transition_kind": LIVE_START_PENDING_TRANSITION_KIND,
            "run_id": session.run_id,
            "operation": operation,
            "stage": "PREPARED",
            "expected_session_sha256": session.content_sha256,
            "source_phase": session.phase.value,
            "target_phase": session.phase.value,
            "source_candidate_revision": session.candidate_revision,
            "target_candidate_revision": session.candidate_revision,
            "source_revisions_used": session.revisions_used,
            "target_revisions_used": session.revisions_used,
            "successor_artifact_bindings": dict(session.artifact_bindings),
            "actions": [],
            "next_action_index": 0,
            "external_file_action": (
                None
                if external_file_action is None
                else _thaw(external_file_action)
            ),
        }
    )
    return value


def _seal_pending(value: Mapping[str, Any]) -> Mapping[str, Any]:
    unsigned = _normalize_json(value)
    if not isinstance(unsigned, dict):
        raise SessionValidationError("live_start_pending_transition_invalid")
    unsigned.pop("content_sha256", None)
    return seal_embedded_document("pending_transition", unsigned)


def _receipt_evidence(
    postcondition: _PhysicalPostcondition,
) -> dict[str, Any]:
    return _thaw(postcondition.evidence)


def _bind_external_staging_from_receipt(
    *,
    external: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> Mapping[str, Any]:
    value = _thaw(external)
    value.pop("content_sha256", None)
    identity = _require_identity(evidence.get("staging_identity"), "staging_identity")
    size = _bounded_integer(
        evidence.get("staging_size"),
        0,
        64 * 1024 * 1024,
        "staging_size",
    )
    digest = _require_sha256(evidence.get("staging_sha256"), "staging_sha256")
    if size != value["planned_successor_size"] or digest != value["planned_successor_sha256"]:
        raise SessionCapabilityError("live_start_staging_receipt_content_mismatch")
    value.update(
        {
            "stage": "STAGING_BOUND",
            "staging_identity": identity,
            "staging_size": size,
            "staging_sha256": digest,
        }
    )
    return seal_embedded_document("external_file_action", value)


def _review_revision_run_paths(
    session_lease: LiveStartSessionLease,
) -> tuple[Path, Path, Path, Path, Path]:
    root = session_lease.session_root
    final_path = root / "starter/starter_config_review.json"
    staging_path = final_path.with_name(f"{final_path.name}.staged")
    inner_temp_path = staging_path.with_name(
        f".{staging_path.name}.live-start-atomic.tmp"
    )
    cleanup_directory = root / "receipts"
    cleanup_path = cleanup_directory / "candidate_validation.json"
    return (
        final_path,
        staging_path,
        inner_temp_path,
        cleanup_path,
        cleanup_directory,
    )


def _require_exact_review_revision_run_locations(
    *,
    session_lease: LiveStartSessionLease,
    revision_session: LiveStartSession,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    pending = revision_session.pending_transition
    if (
        not isinstance(pending, Mapping)
        or pending.get("operation") != "review_revision"
    ):
        raise SessionConflictError(
            "live_start_review_revision_pending_missing"
        )
    actions = pending.get("actions")
    if not isinstance(actions, (list, tuple)) or len(actions) != 1:
        raise SessionConflictError(
            "live_start_review_revision_cleanup_missing"
        )
    cleanup = actions[0]
    if not isinstance(cleanup, Mapping):
        raise SessionConflictError(
            "live_start_review_revision_cleanup_missing"
        )
    (
        final_path,
        staging_path,
        inner_temp_path,
        cleanup_path,
        cleanup_directory,
    ) = _review_revision_run_paths(session_lease)
    validation_binding = revision_session.artifact_bindings.get(
        "receipts/candidate_validation.json"
    )
    if (
        cleanup.get("path") != str(cleanup_path)
        or cleanup.get("directory_path") != str(cleanup_directory)
        or cleanup.get("historical_sha256") != validation_binding
        or _require_identity(
            cleanup.get("parent_identity"),
            "review_revision_cleanup_parent_identity",
        )
        != _require_identity(
            cleanup.get("directory_identity"),
            "review_revision_cleanup_directory_identity",
        )
        or _require_identity(
            cleanup.get("directory_parent_identity"),
            "review_revision_cleanup_directory_parent_identity",
        )
        != session_lease.session_root_identity
    ):
        raise SessionConflictError(
            "live_start_review_revision_run_location_changed"
        )
    stage = pending.get("stage")
    external = pending.get("external_file_action")
    if stage in {"PREPARED", "STAGING_BOUND"}:
        if not isinstance(external, Mapping) or (
            external.get("final_path") != str(final_path)
            or external.get("staging_path") != str(staging_path)
            or external.get("inner_temp_path") != str(inner_temp_path)
        ):
            raise SessionConflictError(
                "live_start_review_revision_run_location_changed"
            )
    elif stage == "PRIMARY_APPLIED":
        if external is not None or cleanup.get("review_path") != str(
            final_path
        ):
            raise SessionConflictError(
                "live_start_review_revision_run_location_changed"
            )
    else:
        raise SessionConflictError(
            "live_start_review_revision_stage_invalid"
        )
    return pending, cleanup


def _require_review_revision_source_ancestry_external(
    *,
    source_path: Path,
    session_lease: LiveStartSessionLease,
    expected_parent_identity: PathIdentity | None = None,
) -> PathIdentity:
    snapshots: list[tuple[Path, PathIdentity]] = []
    ancestor = source_path.parent
    for _index in range(MAX_FILESYSTEM_NODES):
        try:
            status = ancestor.lstat()
        except OSError as error:
            raise SessionConflictError(
                "live_start_review_revision_source_parent_missing"
            ) from error
        if not stat.S_ISDIR(status.st_mode) or status_is_reparse(status):
            raise SessionLayoutError(
                "live_start_review_revision_source_parent_invalid"
            )
        identity = path_identity_from_status(status)
        if identity == session_lease.session_root_identity:
            raise SessionValidationError(
                "live_start_review_revision_source_must_be_external"
            )
        if not snapshots:
            _validate_path_no_ads(
                ancestor,
                status=status,
                directory=True,
            )
        snapshots.append((ancestor, identity))
        parent = ancestor.parent
        if parent == ancestor:
            break
        ancestor = parent
    else:
        raise SessionLayoutError(
            "live_start_review_revision_source_ancestry_invalid"
        )
    for index, (path, identity) in enumerate(snapshots):
        try:
            status = path.lstat()
        except OSError as error:
            raise SessionConflictError(
                "live_start_review_revision_source_parent_changed"
            ) from error
        if (
            not stat.S_ISDIR(status.st_mode)
            or status_is_reparse(status)
            or path_identity_from_status(status) != identity
        ):
            raise SessionConflictError(
                "live_start_review_revision_source_parent_changed"
            )
        if index == 0:
            _validate_path_no_ads(
                path,
                status=status,
                directory=True,
            )
    parent_identity = snapshots[0][1]
    if (
        expected_parent_identity is not None
        and parent_identity != expected_parent_identity
    ):
        raise SessionConflictError(
            "live_start_review_revision_source_parent_changed"
        )
    return parent_identity


def _require_canonical_local_review_revision_source_namespace(
    source_path: Path,
) -> None:
    if not isinstance(source_path, Path) or not source_path.is_absolute():
        raise SessionValidationError(
            "live_start_review_revision_source_path_invalid"
        )
    if os.name == "nt" and (
        re.fullmatch(r"[A-Za-z]:", source_path.drive) is None
        or str(source_path).startswith(("\\\\", "//"))
    ):
        raise SessionValidationError(
            "live_start_review_revision_source_path_invalid"
        )


def _require_external_review_revision_source_path(
    *,
    source_path: Path,
    session_root: Path,
    forbidden_paths: Sequence[Path],
) -> Path:
    _require_canonical_local_review_revision_source_namespace(source_path)
    try:
        canonical_source = source_path.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise SessionValidationError(
            "live_start_review_revision_source_path_invalid"
        ) from error
    if (
        str(canonical_source) != str(source_path)
    ):
        raise SessionValidationError(
            "live_start_review_revision_source_path_invalid"
        )
    source = canonical_source
    try:
        source.relative_to(session_root)
    except ValueError:
        pass
    else:
        raise SessionValidationError(
            "live_start_review_revision_source_must_be_external"
        )
    if source in {Path(path) for path in forbidden_paths}:
        raise SessionValidationError(
            "live_start_review_revision_source_alias_invalid"
        )
    return source


def _review_revision_materialization_source(
    pending: Mapping[str, Any],
) -> Mapping[str, Any]:
    actions = pending.get("actions")
    if not isinstance(actions, (list, tuple)) or len(actions) != 1:
        raise SessionConflictError(
            "live_start_review_revision_materialization_source_missing"
        )
    row = actions[0]
    if not isinstance(row, Mapping):
        raise SessionConflictError(
            "live_start_review_revision_materialization_source_missing"
        )
    source = row.get("materialization_source")
    if not isinstance(source, Mapping):
        raise SessionConflictError(
            "live_start_review_revision_materialization_source_missing"
        )
    return source


def _observe_review_revision_materialization_source(
    *,
    session_lease: LiveStartSessionLease,
    pending: Mapping[str, Any],
) -> bytes | None:
    external = pending.get("external_file_action")
    if not isinstance(external, Mapping):
        raise SessionConflictError(
            "live_start_review_revision_external_missing"
        )
    source = _review_revision_materialization_source(pending)
    source_path = _require_external_review_revision_source_path(
        source_path=Path(source["path"]),
        session_root=session_lease.session_root,
        forbidden_paths=(
            Path(external["final_path"]),
            Path(external["staging_path"]),
            Path(external["inner_temp_path"]),
        ),
    )
    expected_parent_identity = _require_identity(
        source.get("parent_identity"),
        "review_revision_materialization_source_parent_identity",
    )
    _require_review_revision_source_ancestry_external(
        source_path=source_path,
        session_lease=session_lease,
        expected_parent_identity=expected_parent_identity,
    )
    if not os.path.lexists(source_path):
        return None
    try:
        raw, identity = _read_bound_file(
            source_path,
            expected_parent_identity=expected_parent_identity,
            maximum_size=256 * 1024,
        )
    except SessionValidationError:
        raise
    except (OSError, RuntimeError, ValueError) as error:
        raise SessionConflictError(
            "live_start_review_revision_source_changed"
        ) from error
    if (
        identity
        != _require_identity(
            source.get("identity"),
            "review_revision_materialization_source_identity",
        )
        or len(raw) != source.get("size")
        or _bytes_sha256(raw) != source.get("sha256")
        or len(raw) != external.get("planned_successor_size")
        or _bytes_sha256(raw) != external.get("planned_successor_sha256")
    ):
        raise SessionConflictError(
            "live_start_review_revision_source_changed"
        )
    _validate_request_review_bytes(raw=raw)
    return raw


def _validate_request_review_bytes(
    *,
    raw: bytes,
) -> Mapping[str, Any]:
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= 256 * 1024:
        raise SessionValidationError(
            "live_start_review_revision_request_size_invalid"
        )
    value = _decode_canonical_json(raw)
    if not value:
        raise SessionValidationError(
            "live_start_review_revision_request_empty"
        )
    try:
        return _freeze_mapping(value)
    except RecursionError as error:
        raise SessionValidationError("live_start_json_invalid") from error


def _require_review_revision_expected_cursor_integrity(
    expected_session: LiveStartSession,
) -> None:
    error_code = "live_start_review_revision_expected_cursor_mutated"
    try:
        if type(expected_session) is not LiveStartSession:
            raise SessionCapabilityError(error_code)
        canonical_session = _load_session_bytes(
            expected_session.canonical_json,
            session_identity=expected_session.session_identity,
        )
        if expected_session != canonical_session:
            raise SessionCapabilityError(error_code)
    except SessionCapabilityError:
        raise
    except (
        SessionConflictError,
        SessionLayoutError,
        SessionValidationError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise SessionCapabilityError(error_code) from error


def prepare_candidate_review_revision_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_validated_session: LiveStartSession,
    request_review_source_path: Path,
) -> LiveStartSession:
    _require_review_revision_expected_cursor_integrity(
        expected_validated_session
    )
    _session_bearer, current = (
        _authenticate_authorization_cursor_under_lock(
            session_lease=session_lease,
            expected_session=expected_validated_session,
        )
    )
    if (
        current.phase is not LiveStartPhase.CANDIDATE_VALIDATED
        or current.pending_transition is not None
        or current.revisions_used >= 2
        or current.candidate_revision >= 3
        or current.revisions_used != current.candidate_revision - 1
    ):
        raise SessionConflictError(
            "live_start_review_revision_cursor_invalid"
        )
    review_path = (
        session_lease.session_root / "starter/starter_config_review.json"
    )
    validation_path = (
        session_lease.session_root / "receipts/candidate_validation.json"
    )
    staging_path = review_path.with_name(f"{review_path.name}.staged")
    inner_temp_path = staging_path.with_name(
        f".{staging_path.name}.live-start-atomic.tmp"
    )
    source_path = _require_external_review_revision_source_path(
        source_path=request_review_source_path,
        session_root=session_lease.session_root,
        forbidden_paths=(review_path, staging_path, inner_temp_path),
    )
    source_parent_identity = (
        _require_review_revision_source_ancestry_external(
            source_path=source_path,
            session_lease=session_lease,
        )
    )
    try:
        request_review_bytes, source_identity = _read_bound_file(
            source_path,
            expected_parent_identity=source_parent_identity,
            maximum_size=256 * 1024,
        )
    except SessionValidationError:
        raise
    except (OSError, RuntimeError, ValueError) as error:
        raise SessionLayoutError(
            "live_start_review_revision_source_invalid"
        ) from error
    _validate_request_review_bytes(raw=request_review_bytes)
    review_parent_identity = path_identity(review_path.parent)
    validation_parent_identity = path_identity(validation_path.parent)
    validation_raw, validation_identity = _read_bound_file(
        validation_path,
        expected_parent_identity=validation_parent_identity,
        maximum_size=256 * 1024,
    )
    validation_sha256 = _bytes_sha256(validation_raw)
    validation_receipt = validate_validation_receipt(
        receipt_kind="candidate_validation",
        value=_decode_canonical_json(validation_raw),
        run_id=current.run_id,
        candidate_revision=current.candidate_revision,
    )
    _require_completed_receipt_binding(
        session=current,
        receipt_kind="candidate_validation",
        receipt=validation_receipt,
        receipt_bytes_sha256=validation_sha256,
        receipt_logical_path="receipts/candidate_validation.json",
    )
    if any(
        os.path.lexists(path)
        for path in (review_path, staging_path, inner_temp_path)
    ):
        raise SessionConflictError(
            "live_start_review_revision_target_not_absent"
        )
    request_sha256 = _bytes_sha256(request_review_bytes)
    external = _build_external_file_action(
        action_kind="materialize_review_revision_staging",
        action_index=0,
        final_path=review_path,
        staging_path=staging_path,
        inner_temp_path=inner_temp_path,
        parent_identity=review_parent_identity,
        predecessor_identity=None,
        predecessor_size=None,
        predecessor_sha256=None,
        planned_successor_size=len(request_review_bytes),
        planned_successor_sha256=request_sha256,
        commit_mode="create_no_replace",
    )
    successor_bindings = dict(current.artifact_bindings)
    for logical in _DOWNSTREAM_REVISION_ARTIFACTS:
        successor_bindings.pop(logical, None)
    successor_bindings["starter/starter_config_review.json"] = (
        request_sha256
    )
    pending = _empty_pending_transition(
        session=current,
        operation="review_revision",
        external_file_action=external,
    )
    pending.update(
        {
            "target_phase": LiveStartPhase.CANDIDATE_DRAFTED.value,
            "target_revisions_used": current.revisions_used + 1,
            "successor_artifact_bindings": successor_bindings,
            "actions": [
                {
                    "action": "retire_candidate_validation_receipt",
                    "materialization_source": {
                        "path": str(source_path),
                        "parent_identity": list(source_parent_identity),
                        "identity": list(source_identity),
                        "size": len(request_review_bytes),
                        "sha256": request_sha256,
                    },
                    "path": str(validation_path.absolute()),
                    "parent_identity": list(validation_parent_identity),
                    "historical_identity": list(validation_identity),
                    "historical_size": len(validation_raw),
                    "historical_sha256": validation_sha256,
                    "directory_path": str(
                        validation_path.parent.absolute()
                    ),
                    "directory_parent_identity": list(
                        path_identity(validation_path.parent.parent)
                    ),
                    "directory_identity": list(
                        validation_parent_identity
                    ),
                    "review_path": None,
                    "review_parent_identity": None,
                    "review_identity": None,
                    "review_size": None,
                    "review_sha256": None,
                }
            ],
        }
    )
    return _transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=current,
        event="same_phase_cas",
        changes={"pending_transition": _seal_pending(pending)},
    )


def _candidate_review_revision_action(
    pending: Mapping[str, Any],
) -> str:
    if pending.get("operation") != "review_revision":
        raise SessionConflictError(
            "live_start_review_revision_pending_missing"
        )
    stage = pending.get("stage")
    if stage == "PREPARED":
        return "materialize_review_revision_staging"
    if stage == "STAGING_BOUND":
        return "commit_bound_review_revision_request"
    if stage == "PRIMARY_APPLIED":
        return "retire_candidate_validation_receipt"
    raise SessionConflictError("live_start_review_revision_stage_invalid")


def _candidate_review_revision_allowed_actions(
    pending: Mapping[str, Any],
) -> frozenset[str]:
    if pending.get("operation") != "review_revision":
        return frozenset()
    return {
        "PREPARED": frozenset(
            {
                "retire_unbound_review_revision_staging",
                "materialize_review_revision_staging",
                "restore_review_revision_predecessor",
            }
        ),
        "STAGING_BOUND": frozenset(
            {"commit_bound_review_revision_request"}
        ),
        "PRIMARY_APPLIED": frozenset(
            {"retire_candidate_validation_receipt"}
        ),
    }.get(pending.get("stage"), frozenset())


def _require_review_revision_final_binding(
    *,
    cleanup_row: Mapping[str, Any],
    expected_sha256: str,
) -> tuple[bytes, PathIdentity]:
    final_path = Path(cleanup_row["review_path"])
    expected_parent_identity = _require_identity(
        cleanup_row["review_parent_identity"],
        "review_revision_final_parent_identity",
    )
    try:
        raw, identity = _read_bound_file(
            final_path,
            expected_parent_identity=expected_parent_identity,
            maximum_size=256 * 1024,
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise SessionConflictError(
            "live_start_review_revision_final_binding_changed"
        ) from error
    if (
        identity
        != _require_identity(
            cleanup_row["review_identity"],
            "review_revision_final_identity",
        )
        or len(raw) != cleanup_row["review_size"]
        or _bytes_sha256(raw) != cleanup_row["review_sha256"]
        or cleanup_row["review_sha256"] != expected_sha256
    ):
        raise SessionConflictError(
            "live_start_review_revision_final_binding_changed"
        )
    return raw, identity


def _require_review_revision_run_physical_bindings(
    *,
    session_lease: LiveStartSessionLease,
    revision_session: LiveStartSession,
) -> None:
    pending, cleanup = _require_exact_review_revision_run_locations(
        session_lease=session_lease,
        revision_session=revision_session,
    )
    (
        _final_path,
        _staging_path,
        _inner_temp_path,
        cleanup_path,
        cleanup_directory,
    ) = _review_revision_run_paths(session_lease)
    expected_directory_parent_identity = _require_identity(
        cleanup["directory_parent_identity"],
        "review_revision_cleanup_directory_parent_identity",
    )
    expected_directory_identity = _require_identity(
        cleanup["directory_identity"],
        "review_revision_cleanup_directory_identity",
    )
    expected_cleanup_identity = _require_identity(
        cleanup["historical_identity"],
        "review_revision_cleanup_identity",
    )
    allow_absent = pending.get("stage") == "PRIMARY_APPLIED"
    try:
        if (
            path_identity(cleanup_directory.parent)
            != expected_directory_parent_identity
        ):
            raise SessionConflictError(
                "live_start_review_revision_cleanup_directory_changed"
            )
        directory_present = os.path.lexists(cleanup_directory)
        if directory_present:
            directory_status = cleanup_directory.lstat()
            if (
                not stat.S_ISDIR(directory_status.st_mode)
                or status_is_reparse(directory_status)
                or path_identity_from_status(directory_status)
                != expected_directory_identity
            ):
                raise SessionConflictError(
                    "live_start_review_revision_cleanup_directory_changed"
                )
            _validate_path_no_ads(
                cleanup_directory,
                status=directory_status,
                directory=True,
            )
            if os.path.lexists(cleanup_path):
                cleanup_raw, cleanup_identity = _read_bound_file(
                    cleanup_path,
                    expected_parent_identity=expected_directory_identity,
                    maximum_size=256 * 1024,
                )
                if (
                    cleanup_identity != expected_cleanup_identity
                    or len(cleanup_raw) != cleanup["historical_size"]
                    or _bytes_sha256(cleanup_raw)
                    != cleanup["historical_sha256"]
                ):
                    raise SessionConflictError(
                        "live_start_review_revision_cleanup_changed"
                    )
            else:
                if not allow_absent:
                    raise SessionConflictError(
                        "live_start_review_revision_cleanup_missing"
                    )
                with os.scandir(cleanup_directory) as iterator:
                    if next(iterator, None) is not None:
                        raise SessionConflictError(
                            "live_start_review_revision_cleanup_directory_changed"
                        )
                if path_identity(cleanup_directory) != expected_directory_identity:
                    raise SessionConflictError(
                        "live_start_review_revision_cleanup_directory_changed"
                    )
        elif not allow_absent or os.path.lexists(cleanup_path):
            raise SessionConflictError(
                "live_start_review_revision_cleanup_directory_missing"
            )
        elif (
            path_identity(cleanup_directory.parent)
            != expected_directory_parent_identity
        ):
            raise SessionConflictError(
                "live_start_review_revision_cleanup_directory_changed"
            )
    except SessionConflictError:
        raise
    except (OSError, RuntimeError, ValueError) as error:
        raise SessionConflictError(
            "live_start_review_revision_cleanup_changed"
        ) from error
    if pending.get("stage") == "PRIMARY_APPLIED":
        successor = pending.get("successor_artifact_bindings")
        if not isinstance(successor, Mapping):
            raise SessionConflictError(
                "live_start_review_revision_successor_missing"
            )
        _require_review_revision_final_binding(
            cleanup_row=cleanup,
            expected_sha256=successor[
                "starter/starter_config_review.json"
            ],
        )


def _require_exact_review_revision_posix_two_link_state(
    external: Mapping[str, Any],
) -> tuple[bytes, PathIdentity]:
    if os.name == "nt":
        raise SessionConflictError(
            "live_start_review_revision_posix_two_link_forbidden"
        )
    final_path = Path(external["final_path"])
    staging_path = Path(external["staging_path"])
    inner_path = Path(external["inner_temp_path"])
    expected_parent_identity = _require_identity(
        external["parent_identity"],
        "review_revision_parent_identity",
    )
    if (
        final_path.parent != staging_path.parent
        or path_identity(final_path.parent) != expected_parent_identity
        or os.path.lexists(inner_path)
        or not os.path.lexists(final_path)
        or not os.path.lexists(staging_path)
    ):
        raise SessionConflictError(
            "live_start_review_revision_posix_two_link_invalid"
        )
    try:
        final_raw, final_identity = _read_bound_file_with_links(
            final_path,
            expected_parent_identity=expected_parent_identity,
            maximum_size=256 * 1024,
            allowed_links=frozenset({2}),
        )
        staging_raw, staging_identity = _read_bound_file_with_links(
            staging_path,
            expected_parent_identity=expected_parent_identity,
            maximum_size=256 * 1024,
            allowed_links=frozenset({2}),
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise SessionConflictError(
            "live_start_review_revision_posix_two_link_invalid"
        ) from error
    expected_identity = _require_identity(
        external["staging_identity"],
        "review_revision_staging_identity",
    )
    expected_size = external["staging_size"]
    expected_sha256 = external["staging_sha256"]
    if (
        final_identity != expected_identity
        or staging_identity != expected_identity
        or final_raw != staging_raw
        or len(final_raw) != expected_size
        or _bytes_sha256(final_raw) != expected_sha256
        or expected_size != external["planned_successor_size"]
        or expected_sha256 != external["planned_successor_sha256"]
    ):
        raise SessionConflictError(
            "live_start_review_revision_posix_two_link_changed"
        )
    return final_raw, final_identity


def _observe_review_revision_staging_bound(
    external: Mapping[str, Any],
) -> tuple[bytes, PathIdentity]:
    final_path = Path(external["final_path"])
    staging_path = Path(external["staging_path"])
    inner_path = Path(external["inner_temp_path"])
    expected_parent_identity = _require_identity(
        external["parent_identity"],
        "review_revision_parent_identity",
    )
    if path_identity(final_path.parent) != expected_parent_identity:
        raise SessionConflictError(
            "live_start_review_revision_parent_changed"
        )
    if os.path.lexists(inner_path):
        raise SessionConflictError(
            "live_start_review_revision_bound_state_invalid"
        )
    staging_present = os.path.lexists(staging_path)
    final_present = os.path.lexists(final_path)
    if staging_present and final_present:
        return _require_exact_review_revision_posix_two_link_state(external)
    if not staging_present and not final_present:
        raise SessionConflictError(
            "live_start_review_revision_bound_state_invalid"
        )
    bound_path = staging_path if staging_present else final_path
    bound_raw, bound_identity = _read_bound_file(
        bound_path,
        expected_parent_identity=expected_parent_identity,
        maximum_size=256 * 1024,
    )
    if (
        bound_identity
        != _require_identity(
            external["staging_identity"],
            "review_revision_staging_identity",
        )
        or len(bound_raw) != external["staging_size"]
        or _bytes_sha256(bound_raw) != external["staging_sha256"]
    ):
        raise SessionConflictError(
            "live_start_review_revision_staging_changed"
        )
    return bound_raw, bound_identity


def _review_revision_posix_two_link_layout_paths(
    *,
    root: Path,
    session: LiveStartSession,
) -> frozenset[str]:
    if os.name == "nt":
        return frozenset()
    pending = session.pending_transition
    if (
        not isinstance(pending, Mapping)
        or pending.get("operation") != "review_revision"
        or pending.get("stage") != "STAGING_BOUND"
    ):
        return frozenset()
    external = pending.get("external_file_action")
    if not isinstance(external, Mapping):
        return frozenset()
    expected_final = root / "starter/starter_config_review.json"
    expected_staging = expected_final.with_name(
        f"{expected_final.name}.staged"
    )
    expected_inner = expected_staging.with_name(
        f".{expected_staging.name}.live-start-atomic.tmp"
    )
    if (
        external.get("final_path") != str(expected_final)
        or external.get("staging_path") != str(expected_staging)
        or external.get("inner_temp_path") != str(expected_inner)
    ):
        return frozenset()
    try:
        _require_exact_review_revision_posix_two_link_state(external)
        final_logical = Path(external["final_path"]).relative_to(root).as_posix()
        staging_logical = (
            Path(external["staging_path"]).relative_to(root).as_posix()
        )
    except (OSError, RuntimeError, ValueError):
        return frozenset()
    if final_logical == staging_logical:
        return frozenset()
    return frozenset({final_logical, staging_logical})


def authorize_candidate_review_revision_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_revision_session: LiveStartSession,
) -> CandidateReviewRevisionAuthorization:
    _require_review_revision_expected_cursor_integrity(
        expected_revision_session
    )
    session_bearer, current = (
        _authenticate_authorization_cursor_under_lock(
            session_lease=session_lease,
            expected_session=expected_revision_session,
        )
    )
    pending = current.pending_transition
    if not isinstance(pending, Mapping):
        raise SessionConflictError(
            "live_start_review_revision_pending_missing"
        )
    action = _candidate_review_revision_action(pending)
    _require_review_revision_run_physical_bindings(
        session_lease=session_lease,
        revision_session=current,
    )
    external = pending.get("external_file_action")
    if action in {
        "materialize_review_revision_staging",
        "commit_bound_review_revision_request",
    }:
        if not isinstance(external, Mapping):
            raise SessionConflictError(
                "live_start_review_revision_external_missing"
            )
        final_path = Path(external["final_path"])
        staging_path = Path(external["staging_path"])
        inner_path = Path(external["inner_temp_path"])
        if path_identity(final_path.parent) != _require_identity(
            external["parent_identity"],
            "review_revision_parent_identity",
        ):
            raise SessionConflictError(
                "live_start_review_revision_parent_changed"
            )
        if pending.get("stage") == "PREPARED":
            source_raw = _observe_review_revision_materialization_source(
                session_lease=session_lease,
                pending=pending,
            )
            if os.path.lexists(final_path):
                raise SessionConflictError(
                    "live_start_review_revision_direct_final_invalid"
                )
            if os.path.lexists(staging_path) or os.path.lexists(inner_path):
                action = "retire_unbound_review_revision_staging"
            elif source_raw is None:
                action = "restore_review_revision_predecessor"
            else:
                action = "materialize_review_revision_staging"
        else:
            _observe_review_revision_staging_bound(external)
    return _mint_authorization_for_authenticated_cursor(
        authorization_type=CandidateReviewRevisionAuthorization,
        session_bearer=session_bearer,
        current=current,
        family="candidate_review_revision",
        action=action,
    )


def _require_candidate_review_revision_execution_context(
    *,
    session_lease: LiveStartSessionLease,
    expected_revision_session: LiveStartSession,
    revision_authorization: CandidateReviewRevisionAuthorization,
    action: str,
) -> None:
    session_bearer = _require_session_lease(session_lease)
    if (
        not isinstance(
            revision_authorization,
            CandidateReviewRevisionAuthorization,
        )
        or not hasattr(revision_authorization, "_opaque")
        or not isinstance(revision_authorization._opaque, _OpaqueBearer)
        or revision_authorization._opaque.session_bearer
        is not session_bearer
        or revision_authorization._opaque.cursor_sha256
        != expected_revision_session.content_sha256
    ):
        raise SessionCapabilityError(
            "live_start_review_revision_execution_context_invalid"
        )
    _require_review_revision_expected_cursor_integrity(
        expected_revision_session
    )
    pending = expected_revision_session.pending_transition
    if (
        not isinstance(pending, Mapping)
        or action not in _candidate_review_revision_allowed_actions(pending)
    ):
        raise SessionCapabilityError(
            "live_start_review_revision_execution_stage_invalid"
        )


def _execute_candidate_review_revision_physical_step(
    *,
    session_lease: LiveStartSessionLease,
    expected_revision_session: LiveStartSession,
    revision_authorization: CandidateReviewRevisionAuthorization,
    action: str,
    physical_action: Callable[
        [], CandidateReviewRevisionPhysicalPostcondition
    ],
) -> CandidateReviewRevisionStepReceipt:
    if action not in CANDIDATE_REVIEW_REVISION_ACTIONS:
        raise SessionValidationError(
            "live_start_review_revision_action_invalid"
        )
    _require_candidate_review_revision_execution_context(
        session_lease=session_lease,
        expected_revision_session=expected_revision_session,
        revision_authorization=revision_authorization,
        action=action,
    )
    physical_precondition: Mapping[str, Any] | None = None

    def require_physical_precondition() -> None:
        nonlocal physical_precondition
        try:
            _session_bearer, current = (
                _authenticate_authorization_cursor_under_lock(
                    session_lease=session_lease,
                    expected_session=expected_revision_session,
                )
            )
            pending = current.pending_transition
            if (
                not isinstance(pending, Mapping)
                or action
                not in _candidate_review_revision_allowed_actions(pending)
            ):
                raise SessionConflictError(
                    "live_start_review_revision_execution_stage_invalid"
                )
            _require_review_revision_run_physical_bindings(
                session_lease=session_lease,
                revision_session=current,
            )
            external = pending.get("external_file_action")
            observed_precondition: dict[str, Any] = {"action": action}
            if action in {
                "materialize_review_revision_staging",
                "restore_review_revision_predecessor",
            }:
                source_raw = _observe_review_revision_materialization_source(
                    session_lease=session_lease,
                    pending=pending,
                )
                if not isinstance(external, Mapping):
                    raise SessionConflictError(
                        "live_start_review_revision_external_missing"
                    )
                target_present = any(
                    os.path.lexists(Path(external[field_name]))
                    for field_name in (
                        "final_path",
                        "staging_path",
                        "inner_temp_path",
                    )
                )
                if (
                    action == "materialize_review_revision_staging"
                    and (source_raw is None or target_present)
                ) or (
                    action == "restore_review_revision_predecessor"
                    and (source_raw is not None or target_present)
                ):
                    raise SessionConflictError(
                        "live_start_review_revision_source_precondition_changed"
                    )
            elif action == "commit_bound_review_revision_request":
                if not isinstance(external, Mapping):
                    raise SessionConflictError(
                        "live_start_review_revision_external_missing"
                    )
                _observe_review_revision_staging_bound(external)
            elif action == "retire_candidate_validation_receipt":
                cleanup = pending.get("actions")
                if not isinstance(cleanup, (list, tuple)) or len(cleanup) != 1:
                    raise SessionConflictError(
                        "live_start_review_revision_cleanup_missing"
                    )
                successor = pending.get("successor_artifact_bindings")
                if not isinstance(successor, Mapping):
                    raise SessionConflictError(
                        "live_start_review_revision_successor_missing"
                    )
                _require_review_revision_final_binding(
                    cleanup_row=cleanup[0],
                    expected_sha256=successor[
                        "starter/starter_config_review.json"
                    ],
                )
                observed_precondition.update(
                    {
                        "receipt_present": os.path.lexists(
                            Path(cleanup[0]["path"])
                        ),
                        "directory_present": os.path.lexists(
                            Path(cleanup[0]["directory_path"])
                        ),
                    }
                )
            physical_precondition = _freeze_mapping(
                observed_precondition
            )
        except (
            SessionCapabilityError,
            SessionConflictError,
            SessionLayoutError,
            SessionValidationError,
            OSError,
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            IndexError,
        ) as error:
            raise SessionCapabilityError(
                "live_start_review_revision_physical_precondition_changed"
            ) from error

    receipt = _execute_physical_step(
        authorization=revision_authorization,
        authorization_type=CandidateReviewRevisionAuthorization,
        receipt_type=CandidateReviewRevisionStepReceipt,
        postcondition_type=CandidateReviewRevisionPhysicalPostcondition,
        family="candidate_review_revision",
        action=action,
        physical_action=physical_action,
        before_authorization_consume=require_physical_precondition,
        receipt_physical_precondition=lambda: physical_precondition,
    )
    if physical_precondition is None:
        raise SessionCapabilityError(
            "live_start_review_revision_physical_precondition_missing"
        )
    return receipt


def _require_exact_revision_step_evidence(
    *,
    evidence: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> None:
    if _normalize_json(evidence) != _normalize_json(expected):
        raise SessionCapabilityError(
            "live_start_review_revision_postcondition_invalid"
        )


def _validate_candidate_review_revision_receipt_postcondition_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    current: LiveStartSession,
    postcondition: CandidateReviewRevisionPhysicalPostcondition,
    physical_precondition: Mapping[str, Any],
    action: str,
) -> None:
    error_code = "live_start_review_revision_receipt_postcondition_invalid"
    try:
        pending = current.pending_transition
        if not isinstance(pending, Mapping):
            raise SessionCapabilityError(error_code)
        if (
            not isinstance(
                postcondition,
                CandidateReviewRevisionPhysicalPostcondition,
            )
            or postcondition.action != action
            or not isinstance(physical_precondition, Mapping)
            or physical_precondition.get("action") != action
        ):
            raise SessionCapabilityError(error_code)
        expected_precondition_fields = {"action"}
        if action == "retire_candidate_validation_receipt":
            expected_precondition_fields.update(
                {"receipt_present", "directory_present"}
            )
        if set(physical_precondition) != expected_precondition_fields:
            raise SessionCapabilityError(error_code)

        evidence = postcondition.evidence
        external = pending.get("external_file_action")
        if action == "restore_review_revision_predecessor":
            if not isinstance(external, Mapping):
                raise SessionCapabilityError(error_code)
            source = _review_revision_materialization_source(pending)
            final_path = Path(external["final_path"])
            staging_path = Path(external["staging_path"])
            inner_path = Path(external["inner_temp_path"])
            expected_evidence = {
                "source_path": source["path"],
                "source_parent_identity": source["parent_identity"],
                "historical_source_identity": source["identity"],
                "historical_source_size": source["size"],
                "historical_source_sha256": source["sha256"],
                "final_path": str(final_path),
                "staging_path": str(staging_path),
                "inner_temp_path": str(inner_path),
                "target_parent_identity": external["parent_identity"],
                "source_absent": True,
                "final_absent": True,
                "staging_absent": True,
                "inner_temp_absent": True,
            }
            _require_exact_revision_step_evidence(
                evidence=evidence,
                expected=expected_evidence,
            )
            if (
                _observe_review_revision_materialization_source(
                    session_lease=session_lease,
                    pending=pending,
                )
                is not None
                or path_identity(final_path.parent)
                != _require_identity(
                    external["parent_identity"],
                    "review_revision_parent_identity",
                )
                or any(
                    os.path.lexists(path)
                    for path in (final_path, staging_path, inner_path)
                )
            ):
                raise SessionCapabilityError(error_code)
            predecessor_value = current.to_value()
            predecessor_value.pop("content_sha256")
            predecessor_value["pending_transition"] = None
            predecessor = _seal_session_value(
                predecessor_value,
                session_identity=None,
            )
            if predecessor.content_sha256 != pending.get(
                "expected_session_sha256"
            ):
                raise SessionCapabilityError(error_code)
            return

        if action == "retire_unbound_review_revision_staging":
            if not isinstance(external, Mapping):
                raise SessionCapabilityError(error_code)
            final_path = Path(external["final_path"])
            staging_path = Path(external["staging_path"])
            inner_path = Path(external["inner_temp_path"])
            _require_exact_revision_step_evidence(
                evidence=evidence,
                expected={
                    "final_path": str(final_path),
                    "staging_path": str(staging_path),
                    "inner_temp_path": str(inner_path),
                    "parent_identity": external["parent_identity"],
                    "final_absent": True,
                    "staging_absent": True,
                    "inner_temp_absent": True,
                },
            )
            if (
                path_identity(final_path.parent)
                != _require_identity(
                    external["parent_identity"],
                    "review_revision_parent_identity",
                )
                or any(
                    os.path.lexists(path)
                    for path in (final_path, staging_path, inner_path)
                )
            ):
                raise SessionCapabilityError(error_code)
            return

        if action == "materialize_review_revision_staging":
            if not isinstance(external, Mapping):
                raise SessionCapabilityError(error_code)
            final_path = Path(external["final_path"])
            staging_path = Path(external["staging_path"])
            inner_path = Path(external["inner_temp_path"])
            _require_exact_revision_step_evidence(
                evidence=evidence,
                expected={
                    "staging_path": str(staging_path),
                    "staging_parent_identity": external["parent_identity"],
                    "staging_identity": evidence.get("staging_identity"),
                    "staging_size": external["planned_successor_size"],
                    "staging_sha256": external["planned_successor_sha256"],
                },
            )
            expected_parent_identity = _require_identity(
                external["parent_identity"],
                "review_revision_parent_identity",
            )
            staging_raw, staging_identity = _read_bound_file(
                staging_path,
                expected_parent_identity=expected_parent_identity,
                maximum_size=256 * 1024,
            )
            if (
                path_identity(final_path.parent) != expected_parent_identity
                or os.path.lexists(final_path)
                or os.path.lexists(inner_path)
                or staging_identity
                != _require_identity(
                    evidence.get("staging_identity"),
                    "review_revision_staging_identity",
                )
                or len(staging_raw) != external["planned_successor_size"]
                or _bytes_sha256(staging_raw)
                != external["planned_successor_sha256"]
            ):
                raise SessionCapabilityError(error_code)
            return

        if action == "commit_bound_review_revision_request":
            if not isinstance(external, Mapping):
                raise SessionCapabilityError(error_code)
            final_path = Path(external["final_path"])
            staging_path = Path(external["staging_path"])
            inner_path = Path(external["inner_temp_path"])
            _require_exact_revision_step_evidence(
                evidence=evidence,
                expected={
                    "final_path": str(final_path),
                    "final_parent_identity": external["parent_identity"],
                    "final_identity": external["staging_identity"],
                    "final_size": external["planned_successor_size"],
                    "final_sha256": external["planned_successor_sha256"],
                    "staging_absent": True,
                },
            )
            expected_parent_identity = _require_identity(
                external["parent_identity"],
                "review_revision_parent_identity",
            )
            final_raw, final_identity = _read_bound_file(
                final_path,
                expected_parent_identity=expected_parent_identity,
                maximum_size=256 * 1024,
            )
            if (
                path_identity(final_path.parent) != expected_parent_identity
                or final_identity
                != _require_identity(
                    external["staging_identity"],
                    "review_revision_final_identity",
                )
                or len(final_raw) != external["planned_successor_size"]
                or _bytes_sha256(final_raw)
                != external["planned_successor_sha256"]
                or os.path.lexists(staging_path)
                or os.path.lexists(inner_path)
            ):
                raise SessionCapabilityError(error_code)
            return

        if action != "retire_candidate_validation_receipt":
            raise SessionCapabilityError(error_code)
        cleanup = pending.get("actions")
        successor = pending.get("successor_artifact_bindings")
        if (
            not isinstance(cleanup, (list, tuple))
            or len(cleanup) != 1
            or not isinstance(successor, Mapping)
        ):
            raise SessionCapabilityError(error_code)
        row = cleanup[0]
        receipt_present = physical_precondition.get("receipt_present")
        directory_present = physical_precondition.get("directory_present")
        if type(receipt_present) is not bool or type(directory_present) is not bool:
            raise SessionCapabilityError(error_code)
        expected_disposition = "removed" if receipt_present else "already_absent"
        expected_directory_disposition = (
            "removed" if directory_present else "already_absent"
        )
        _require_exact_revision_step_evidence(
            evidence=evidence,
            expected={
                "path": row["path"],
                "parent_identity": row["parent_identity"],
                "historical_identity": row["historical_identity"],
                "historical_size": row["historical_size"],
                "historical_sha256": row["historical_sha256"],
                "directory_path": row["directory_path"],
                "directory_parent_identity": row[
                    "directory_parent_identity"
                ],
                "directory_identity": row["directory_identity"],
                "disposition": expected_disposition,
                "directory_disposition": expected_directory_disposition,
            },
        )
        if os.path.lexists(Path(row["path"])) or os.path.lexists(
            Path(row["directory_path"])
        ):
            raise SessionCapabilityError(error_code)
        _require_review_revision_final_binding(
            cleanup_row=row,
            expected_sha256=successor[
                "starter/starter_config_review.json"
            ],
        )
    except (
        SessionCapabilityError,
        SessionConflictError,
        SessionLayoutError,
        SessionValidationError,
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        IndexError,
    ) as error:
        raise SessionCapabilityError(error_code) from error


def _build_candidate_review_revision_update(
    *,
    current: LiveStartSession,
    postcondition: CandidateReviewRevisionPhysicalPostcondition,
    action: str,
) -> LiveStartSessionUpdate:
    pending = current.pending_transition
    assert isinstance(pending, Mapping)
    external = pending.get("external_file_action")
    evidence = postcondition.evidence
    pending_value = _thaw(pending)
    pending_value.pop("content_sha256")
    if action == "restore_review_revision_predecessor":
        return LiveStartSessionUpdate(
            event="same_phase_cas",
            changes={"pending_transition": None},
        )
    if action == "retire_unbound_review_revision_staging":
        assert isinstance(external, Mapping)
        pending_value["external_file_action"] = _thaw(
            _retire_unbound_external_from_receipt(
                external=external,
                next_action_kind="materialize_review_revision_staging",
            )
        )
    elif action == "materialize_review_revision_staging":
        assert isinstance(external, Mapping)
        pending_value.update(
            {
                "stage": "STAGING_BOUND",
                "external_file_action": _bind_external_staging_from_receipt(
                    external=external,
                    evidence=evidence,
                ),
            }
        )
    elif action == "commit_bound_review_revision_request":
        assert isinstance(external, Mapping)
        final_path = Path(external["final_path"])
        pending_value.update(
            {
                "stage": "PRIMARY_APPLIED",
                "external_file_action": None,
            }
        )
        actions = pending_value["actions"]
        actions[0].update(
            {
                "review_path": str(final_path),
                "review_parent_identity": external["parent_identity"],
                "review_identity": external["staging_identity"],
                "review_size": external["planned_successor_size"],
                "review_sha256": external["planned_successor_sha256"],
            }
        )
    else:
        assert action == "retire_candidate_validation_receipt"
        return LiveStartSessionUpdate(
            event="review_revision",
            changes={
                "artifact_bindings": pending[
                    "successor_artifact_bindings"
                ],
                "pending_transition": None,
            },
        )
    return LiveStartSessionUpdate(
        event="same_phase_cas",
        changes={"pending_transition": _seal_pending(pending_value)},
    )


def advance_candidate_review_revision_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_revision_session: LiveStartSession,
    revision_step_receipt: CandidateReviewRevisionStepReceipt,
) -> LiveStartSession:
    action = (
        _require_candidate_review_revision_receipt_authority_without_observation(
            receipt=revision_step_receipt,
            session_lease=session_lease,
            expected_revision_session=expected_revision_session,
            allowed_actions=CANDIDATE_REVIEW_REVISION_ACTIONS,
        )
    )
    _require_review_revision_expected_cursor_integrity(
        expected_revision_session
    )
    expected_pending = expected_revision_session.pending_transition
    if (
        not isinstance(expected_pending, Mapping)
        or action
        not in _candidate_review_revision_allowed_actions(expected_pending)
    ):
        raise SessionCapabilityError(
            "live_start_review_revision_receipt_invalid"
        )
    try:
        current = _load_expected_predecessor_under_lock(
            session_lease=session_lease,
            expected_session=expected_revision_session,
        )
    except (
        SessionConflictError,
        SessionLayoutError,
        SessionValidationError,
        OSError,
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        IndexError,
    ) as error:
        raise SessionCapabilityError(
            "live_start_review_revision_receipt_cursor_stale"
        ) from error
    current_pending = current.pending_transition
    if (
        not isinstance(current_pending, Mapping)
        or action
        not in _candidate_review_revision_allowed_actions(current_pending)
    ):
        raise SessionCapabilityError(
            "live_start_review_revision_receipt_cursor_stale"
        )
    try:
        _reconcile_session_temp_under_lock(
            session_lease=session_lease,
            expected_session=current,
        )
        _session_bearer, current = (
            _authenticate_authorization_cursor_under_lock(
                session_lease=session_lease,
                expected_session=current,
            )
        )
        _require_review_revision_run_physical_bindings(
            session_lease=session_lease,
            revision_session=current,
        )
    except SessionCapabilityError:
        raise
    except (
        SessionConflictError,
        SessionLayoutError,
        SessionValidationError,
        OSError,
        RuntimeError,
        ValueError,
    ) as error:
        raise SessionCapabilityError(
            "live_start_review_revision_physical_postcondition_changed"
        ) from error
    consumed = _consume_receipt_registration_under_lock(
        receipt=revision_step_receipt,
        receipt_type=CandidateReviewRevisionStepReceipt,
        session_lease=session_lease,
        expected_session=expected_revision_session,
        family="candidate_review_revision",
        action=action,
    )
    postcondition = consumed.successor
    physical_precondition = consumed.physical_precondition
    if (
        not isinstance(
            postcondition,
            CandidateReviewRevisionPhysicalPostcondition,
        )
        or not isinstance(physical_precondition, Mapping)
    ):
        raise SessionCapabilityError(
            "live_start_review_revision_receipt_postcondition_invalid"
        )
    _validate_candidate_review_revision_receipt_postcondition_under_lock(
        session_lease=session_lease,
        current=current,
        postcondition=postcondition,
        physical_precondition=physical_precondition,
        action=action,
    )
    update = _build_candidate_review_revision_update(
        current=current,
        postcondition=postcondition,
        action=action,
    )
    successor = _build_session_successor(
        current=current,
        update=update,
        transition_authority=_INTERNAL_TRANSITION_AUTHORITY,
    )
    return _publish_session_successor_under_lock(
        session_lease=session_lease,
        current=current,
        successor=successor,
    )


def _validate_output_operation_binding_from_pending(
    *,
    session_lease: LiveStartSessionLease,
    predecessor: LiveStartSession,
    pending: Mapping[str, Any],
    binding: Mapping[str, Any],
) -> None:
    expected = {
        "state": "ACTIVE",
        "release_handoff_kind": None,
        "admission_path": pending.get("output_operation_admission_path"),
        "admission_parent_identity": _require_identity(
            pending.get("output_operation_admission_parent_identity"),
            "output_operation_admission_parent_identity",
        ),
        "admission_identity": _require_identity(
            pending.get("output_operation_admission_staging_identity"),
            "output_operation_admission_staging_identity",
        ),
        "admission_size": pending.get(
            "output_operation_admission_planned_size"
        ),
        "admission_sha256": pending.get(
            "output_operation_admission_planned_sha256"
        ),
        "run_id": predecessor.run_id,
        "session_root": str(session_lease.session_root),
        "session_root_identity": session_lease.session_root_identity,
        "expected_session_sha256": pending.get(
            "expected_session_sha256"
        ),
        "output_base_root": pending.get("output_base_path"),
        "output_base_root_identity": _require_identity(
            pending.get("output_base_identity"),
            "output_base_identity",
        ),
        "output_child_path": pending.get("output_child_path"),
        "output_child_predecessor_state": pending.get(
            "output_child_predecessor_state"
        ),
        "output_child_predecessor_identity": (
            None
            if pending.get("output_child_predecessor_identity") is None
            else _require_identity(
                pending.get("output_child_predecessor_identity"),
                "output_child_predecessor_identity",
            )
        ),
        "output_bootstrap_lock_path": pending.get(
            "output_bootstrap_lock_path"
        ),
        "output_bootstrap_lock_identity": _require_identity(
            pending.get("output_bootstrap_lock_identity"),
            "output_bootstrap_lock_identity",
        ),
    }
    for field_name, expected_value in expected.items():
        if binding.get(field_name) != expected_value:
            raise SessionCapabilityError(
                "live_start_output_operation_binding_successor_invalid"
            )
    if any(
        binding.get(field_name) is not None
        for field_name in (
            "handoff_runtime_admission_path",
            "handoff_runtime_admission_parent_identity",
            "handoff_runtime_admission_identity",
            "handoff_runtime_admission_sha256",
        )
    ):
        raise SessionCapabilityError(
            "live_start_output_operation_binding_successor_invalid"
        )


def _validate_output_child_binding_from_pending(
    *,
    predecessor: LiveStartSession,
    pending: Mapping[str, Any],
    binding: Mapping[str, Any],
) -> None:
    expected = {
        "run_id": predecessor.run_id,
        "output_base_path": pending.get("output_base_path"),
        "output_base_identity": _require_identity(
            pending.get("output_base_identity"),
            "output_base_identity",
        ),
        "output_child_path": pending.get("output_child_path"),
        "predecessor_state": pending.get("output_child_predecessor_state"),
        "predecessor_output_child_identity": (
            None
            if pending.get("output_child_predecessor_identity") is None
            else _require_identity(
                pending.get("output_child_predecessor_identity"),
                "output_child_predecessor_identity",
            )
        ),
        "claim_path": pending.get("output_claim_path"),
        "claim_parent_identity": _require_identity(
            pending.get("output_claim_parent_identity"),
            "output_claim_parent_identity",
        ),
        "claim_identity": _require_identity(
            pending.get("output_claim_identity"),
            "output_claim_identity",
        ),
        "claim_sha256": pending.get("output_claim_sha256"),
        "claim_state": "ACTIVE",
    }
    for field_name, expected_value in expected.items():
        if binding.get(field_name) != expected_value:
            raise SessionCapabilityError(
                "live_start_output_child_binding_successor_invalid"
            )
    resulting_identity = pending.get(
        "created_or_confirmed_output_child_identity"
    )
    if resulting_identity is not None and (
        binding.get("output_child_identity") != resulting_identity
    ):
        raise SessionCapabilityError(
            "live_start_output_child_binding_successor_invalid"
        )


def _validate_output_child_retirement_successor(
    *,
    predecessor: LiveStartSession,
    retired_binding: Mapping[str, Any],
    publication_binding: Mapping[str, Any],
) -> None:
    current_child = predecessor.output_child_binding
    current_publication = predecessor.publication_binding
    if not isinstance(current_child, Mapping) or not isinstance(
        current_publication, Mapping
    ):
        raise SessionConflictError(
            "live_start_output_child_retirement_cursor_invalid"
        )
    mutable_child = {
        "claim_state",
        "claim_identity",
        "claim_sha256",
        "content_sha256",
    }
    for field_name in _OUTPUT_CHILD_BINDING_FIELDS - mutable_child:
        if retired_binding.get(field_name) != current_child.get(field_name):
            raise SessionCapabilityError(
                "live_start_output_child_retirement_successor_invalid"
            )
    if (
        current_child.get("claim_state") != "ACTIVE"
        or retired_binding.get("claim_state") != "RETIRED"
        or retired_binding.get("claim_identity") is not None
        or retired_binding.get("claim_sha256") is not None
    ):
        raise SessionCapabilityError(
            "live_start_output_child_retirement_successor_invalid"
        )
    for field_name in _PUBLICATION_BINDING_FIELDS - {
        "output_child_binding_sha256"
    }:
        successor_value = publication_binding.get(field_name)
        current_value = current_publication.get(field_name)
        if field_name in {
            "output_child_identity",
            "prior_current_identity",
        } and successor_value is not None:
            successor_value = _require_identity(
                successor_value,
                field_name,
            )
            if current_value is not None:
                current_value = _require_identity(
                    current_value,
                    field_name,
                )
        if successor_value != current_value:
            raise SessionCapabilityError(
                "live_start_publication_rebinding_invalid"
            )
    if publication_binding.get(
        "output_child_binding_sha256"
    ) != retired_binding.get("content_sha256"):
        raise SessionCapabilityError(
            "live_start_publication_rebinding_invalid"
        )


def _validate_runtime_layout_successor(
    *,
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
) -> None:
    current = validate_embedded_document(
        "runtime_layout_bootstrap", predecessor
    )
    next_value = validate_embedded_document(
        "runtime_layout_bootstrap", successor
    )
    current_index = current["next_directory_index"]
    if (
        current["stage"] != "INCOMPLETE"
        or current_index >= current["directory_count"]
        or next_value["next_directory_index"] != current_index + 1
    ):
        raise SessionCapabilityError(
            "live_start_runtime_layout_successor_invalid"
        )
    for field_name in _RUNTIME_LAYOUT_FIELDS - {
        "stage",
        "next_directory_index",
        "directories",
        "content_sha256",
    }:
        if current.get(field_name) != next_value.get(field_name):
            raise SessionCapabilityError(
                "live_start_runtime_layout_successor_changed"
            )
    current_rows = current["directories"]
    next_rows = next_value["directories"]
    for index, (current_row, next_row) in enumerate(
        zip(current_rows, next_rows, strict=True)
    ):
        mutable_row_fields = {"successor_identity"}
        if (
            index == current_index
            and current_row.get("role") == "state_receipts"
            and current_row.get("expected_parent_identity") is None
        ):
            mutable_row_fields.add("expected_parent_identity")
        for field_name in (
            _RUNTIME_LAYOUT_DIRECTORY_FIELDS - mutable_row_fields
        ):
            if current_row.get(field_name) != next_row.get(field_name):
                raise SessionCapabilityError(
                    "live_start_runtime_layout_successor_changed"
                )
        if index == current_index:
            if (
                current_row.get("successor_identity") is not None
                or next_row.get("successor_identity") is None
            ):
                raise SessionCapabilityError(
                    "live_start_runtime_layout_successor_invalid"
                )
            if current_row.get("role") == "state_receipts":
                receipts_row = next_rows[index - 1]
                expected_parent = receipts_row.get("successor_identity")
                if (
                    expected_parent is None
                    or next_row.get("expected_parent_identity")
                    != expected_parent
                ):
                    raise SessionCapabilityError(
                        "live_start_runtime_layout_parent_binding_invalid"
                    )
        elif current_row.get("successor_identity") != next_row.get(
            "successor_identity"
        ):
            raise SessionCapabilityError(
                "live_start_runtime_layout_successor_changed"
            )
    expected_stage = (
        "COMPLETE"
        if next_value["next_directory_index"]
        == next_value["directory_count"]
        else "INCOMPLETE"
    )
    if next_value["stage"] != expected_stage:
        raise SessionCapabilityError(
            "live_start_runtime_layout_successor_invalid"
        )


def _retire_unbound_external_from_receipt(
    *,
    external: Mapping[str, Any],
    next_action_kind: str,
) -> Mapping[str, Any]:
    value = _thaw(external)
    value.pop("content_sha256", None)
    if value.get("stage") != "PLANNED":
        raise SessionConflictError("live_start_unbound_staging_retirement_invalid")
    value["action_index"] += 1
    value["action_kind"] = next_action_kind
    return seal_embedded_document("external_file_action", value)


def prepare_output_operation_admission_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_prepublication_session: LiveStartSession,
    admission_path: Path,
    admission_staging_path: Path,
    admission_staging_inner_temp_path: Path,
    admission_parent_identity: PathIdentity,
    planned_admission_size: int,
    planned_admission_sha256: str,
    output_base_path: Path,
    output_base_identity: PathIdentity,
    output_child_path: Path,
    predecessor_output_child_identity: PathIdentity | None,
    output_bootstrap_lock_path: Path,
    output_bootstrap_lock_identity: PathIdentity,
) -> LiveStartSession:
    if (
        expected_prepublication_session.phase
        is not LiveStartPhase.PREPUBLICATION_CHECK_PASSED
        or expected_prepublication_session.pending_transition is not None
        or expected_prepublication_session.output_operation_admission_binding
        is not None
    ):
        raise SessionConflictError("live_start_output_operation_prepare_invalid")
    external = _build_external_file_action(
        action_kind="materialize_output_operation_admission_staging",
        action_index=0,
        final_path=admission_path,
        staging_path=admission_staging_path,
        inner_temp_path=admission_staging_inner_temp_path,
        parent_identity=admission_parent_identity,
        predecessor_identity=None,
        predecessor_size=None,
        predecessor_sha256=None,
        planned_successor_size=planned_admission_size,
        planned_successor_sha256=planned_admission_sha256,
        commit_mode="create_no_replace",
    )
    pending = _empty_pending_transition(
        session=expected_prepublication_session,
        operation="install_output_operation_admission",
        external_file_action=external,
    )
    pending.update(
        {
            "output_base_path": str(Path(output_base_path).absolute()),
            "output_base_identity": output_base_identity,
            "output_operation_admission_path": str(Path(admission_path).absolute()),
            "output_operation_admission_staging_path": str(
                Path(admission_staging_path).absolute()
            ),
            "output_operation_admission_staging_inner_temp_path": str(
                Path(admission_staging_inner_temp_path).absolute()
            ),
            "output_operation_admission_parent_identity": admission_parent_identity,
            "output_operation_admission_planned_size": planned_admission_size,
            "output_operation_admission_planned_sha256": planned_admission_sha256,
            "output_child_path": str(Path(output_child_path).absolute()),
            "output_child_predecessor_state": (
                "absent"
                if predecessor_output_child_identity is None
                else "existing"
            ),
            "output_child_predecessor_identity": predecessor_output_child_identity,
            "output_bootstrap_lock_path": str(
                Path(output_bootstrap_lock_path).absolute()
            ),
            "output_bootstrap_lock_identity": output_bootstrap_lock_identity,
        }
    )
    return _transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=expected_prepublication_session,
        event="same_phase_cas",
        changes={"pending_transition": _seal_pending(pending)},
    )


def authorize_output_operation_admission_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_operation_session: LiveStartSession,
    action: str,
) -> OutputOperationAdmissionAuthorization:
    if action not in OUTPUT_OPERATION_ADMISSION_ACTIONS:
        raise SessionValidationError("live_start_output_operation_action_invalid")
    pending = expected_operation_session.pending_transition
    if not isinstance(pending, Mapping) or pending.get("operation") != "install_output_operation_admission":
        raise SessionConflictError("live_start_output_operation_cursor_invalid")
    external = pending.get("external_file_action")
    if not isinstance(external, Mapping):
        raise SessionConflictError("live_start_output_operation_file_action_missing")
    allowed = {
        "PREPARED": {
            "materialize_output_operation_admission_staging",
            "retire_unbound_output_operation_admission_staging",
        },
        "STAGING_BOUND": {"commit_bound_output_operation_admission"},
    }
    if action not in allowed.get(pending.get("stage"), set()):
        raise SessionConflictError("live_start_output_operation_action_stage_invalid")
    return _mint_authorization_under_lock(
        authorization_type=OutputOperationAdmissionAuthorization,
        session_lease=session_lease,
        expected_session=expected_operation_session,
        family="output_operation_admission",
        action=action,
    )


def advance_output_operation_admission_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_operation_session: LiveStartSession,
    transition: str,
    physical_step_receipt: OutputOperationAdmissionStepReceipt,
) -> LiveStartSession:
    actions = {
        "unbound_staging_retired": (
            "retire_unbound_output_operation_admission_staging"
        ),
        "staging_bound": "materialize_output_operation_admission_staging",
        "admission_active": "commit_bound_output_operation_admission",
    }
    try:
        action = actions[transition]
    except KeyError as error:
        raise SessionValidationError("live_start_output_operation_advance_invalid") from error
    postcondition = _consume_receipt_under_lock(
        receipt=physical_step_receipt,
        receipt_type=OutputOperationAdmissionStepReceipt,
        session_lease=session_lease,
        expected_session=expected_operation_session,
        family="output_operation_admission",
        action=action,
    )
    pending = _thaw(expected_operation_session.pending_transition)
    external = pending["external_file_action"]
    evidence = _receipt_evidence(postcondition)
    if transition == "unbound_staging_retired":
        pending["external_file_action"] = _retire_unbound_external_from_receipt(
            external=external,
            next_action_kind="materialize_output_operation_admission_staging",
        )
    elif transition == "staging_bound":
        pending["external_file_action"] = _bind_external_staging_from_receipt(
            external=external,
            evidence=evidence,
        )
        pending["stage"] = "STAGING_BOUND"
        pending["output_operation_admission_staging_identity"] = evidence[
            "staging_identity"
        ]
        pending["output_operation_admission_staging_size"] = evidence[
            "staging_size"
        ]
        pending["output_operation_admission_staging_sha256"] = evidence[
            "staging_sha256"
        ]
    else:
        binding = evidence.get("binding")
        if not isinstance(binding, Mapping):
            raise SessionCapabilityError("live_start_output_operation_binding_receipt_invalid")
        validated = validate_embedded_document(
            "output_operation_admission_binding",
            binding,
        )
        _validate_output_operation_binding_from_pending(
            session_lease=session_lease,
            predecessor=expected_operation_session,
            pending=pending,
            binding=validated,
        )
        return _transition_receipt_authorized_under_lock(
            session_lease=session_lease,
            expected_session=expected_operation_session,
            event="same_phase_cas",
            changes={
                "pending_transition": None,
                "output_operation_admission_binding": validated,
            },
        )
    return _transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=expected_operation_session,
        event="same_phase_cas",
        changes={"pending_transition": _seal_pending(pending)},
    )


def _authorize_output_operation_admission_release_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_release_authorized_session: LiveStartSession,
) -> OutputOperationAdmissionReleaseAuthorization:
    binding = expected_release_authorized_session.output_operation_admission_binding
    if not isinstance(binding, Mapping) or binding.get("state") not in {
        "RUNTIME_HANDOFF_RELEASE_AUTHORIZED",
        "TERMINAL_RELEASE_AUTHORIZED",
    }:
        raise SessionConflictError("live_start_output_operation_release_not_authorized")
    return _mint_authorization_under_lock(
        authorization_type=OutputOperationAdmissionReleaseAuthorization,
        session_lease=session_lease,
        expected_session=expected_release_authorized_session,
        family="output_operation_release",
        action="release_output_operation_admission",
    )


def prepare_output_child_bootstrap_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_prepublication_session: LiveStartSession,
    output_base_path: Path,
    output_base_identity: PathIdentity,
    output_child_path: Path,
    predecessor_output_child_identity: PathIdentity | None,
    planned_claim_size: int,
    planned_claim_sha256: str,
    planned_claim_staging_path: Path,
    planned_claim_staging_inner_temp_path: Path,
    output_bootstrap_lock_path: Path,
    output_bootstrap_lock_identity: PathIdentity,
) -> LiveStartSession:
    binding = expected_prepublication_session.output_operation_admission_binding
    if (
        expected_prepublication_session.phase
        is not LiveStartPhase.PREPUBLICATION_CHECK_PASSED
        or expected_prepublication_session.pending_transition is not None
        or expected_prepublication_session.output_child_binding is not None
        or not isinstance(binding, Mapping)
        or binding.get("state") != "ACTIVE"
    ):
        raise SessionConflictError("live_start_output_child_bootstrap_prepare_invalid")
    claim_path = Path(planned_claim_staging_path).with_name(
        Path(planned_claim_staging_path).name.removesuffix(".staged")
    )
    external = _build_external_file_action(
        action_kind="materialize_claim_staging",
        action_index=0,
        final_path=claim_path,
        staging_path=planned_claim_staging_path,
        inner_temp_path=planned_claim_staging_inner_temp_path,
        parent_identity=output_base_identity,
        predecessor_identity=None,
        predecessor_size=None,
        predecessor_sha256=None,
        planned_successor_size=planned_claim_size,
        planned_successor_sha256=planned_claim_sha256,
        commit_mode="create_no_replace",
    )
    pending = _empty_pending_transition(
        session=expected_prepublication_session,
        operation="bootstrap_output_child",
        external_file_action=external,
    )
    pending.update(
        {
            "output_base_path": str(Path(output_base_path).absolute()),
            "output_base_identity": output_base_identity,
            "output_child_path": str(Path(output_child_path).absolute()),
            "output_child_predecessor_state": (
                "absent"
                if predecessor_output_child_identity is None
                else "existing"
            ),
            "output_child_predecessor_identity": predecessor_output_child_identity,
            "planned_output_claim_size": planned_claim_size,
            "planned_output_claim_sha256": planned_claim_sha256,
            "output_claim_path": str(claim_path.absolute()),
            "output_claim_staging_path": str(
                Path(planned_claim_staging_path).absolute()
            ),
            "output_claim_staging_inner_temp_path": str(
                Path(planned_claim_staging_inner_temp_path).absolute()
            ),
            "output_claim_parent_identity": output_base_identity,
            "output_bootstrap_lock_path": str(
                Path(output_bootstrap_lock_path).absolute()
            ),
            "output_bootstrap_lock_identity": output_bootstrap_lock_identity,
        }
    )
    return _transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=expected_prepublication_session,
        event="same_phase_cas",
        changes={"pending_transition": _seal_pending(pending)},
    )


def prepare_output_child_claim_retirement_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_publication_session: LiveStartSession,
) -> LiveStartSession:
    child = expected_publication_session.output_child_binding
    publication = expected_publication_session.publication_binding
    operation = expected_publication_session.output_operation_admission_binding
    if (
        expected_publication_session.phase
        is not LiveStartPhase.PUBLICATION_COMMITTED
        or expected_publication_session.pending_transition is not None
        or not isinstance(child, Mapping)
        or child.get("claim_state") != "ACTIVE"
        or not isinstance(publication, Mapping)
        or not isinstance(operation, Mapping)
        or operation.get("state") != "ACTIVE"
    ):
        raise SessionConflictError(
            "live_start_output_claim_retirement_prepare_invalid"
        )
    pending = _empty_pending_transition(
        session=expected_publication_session,
        operation="retire_output_child_claim",
        external_file_action=None,
    )
    pending.update(
        {
            "output_base_path": child["output_base_path"],
            "output_base_identity": child["output_base_identity"],
            "output_child_path": child["output_child_path"],
            "output_child_predecessor_state": child[
                "predecessor_state"
            ],
            "output_child_predecessor_identity": child[
                "predecessor_output_child_identity"
            ],
            "output_claim_path": child["claim_path"],
            "output_claim_parent_identity": child[
                "claim_parent_identity"
            ],
            "output_claim_identity": child["claim_identity"],
            "output_claim_sha256": child["claim_sha256"],
            "created_or_confirmed_output_child_identity": child[
                "output_child_identity"
            ],
            "output_bootstrap_lock_path": operation[
                "output_bootstrap_lock_path"
            ],
            "output_bootstrap_lock_identity": operation[
                "output_bootstrap_lock_identity"
            ],
        }
    )
    return _transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=expected_publication_session,
        event="same_phase_cas",
        changes={"pending_transition": _seal_pending(pending)},
    )


def authorize_output_child_bootstrap_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_bootstrap_session: LiveStartSession,
    action: str,
) -> OutputChildBootstrapAuthorization:
    if action not in OUTPUT_CHILD_BOOTSTRAP_ACTIONS:
        raise SessionValidationError("live_start_output_bootstrap_action_invalid")
    pending = expected_bootstrap_session.pending_transition
    if not isinstance(pending, Mapping) or pending.get("operation") not in {
        "bootstrap_output_child",
        "retire_output_child_claim",
    }:
        raise SessionConflictError("live_start_output_bootstrap_cursor_invalid")
    operation = pending["operation"]
    stage = pending["stage"]
    matrix = {
        ("bootstrap_output_child", "PREPARED"): {
            "materialize_claim_staging",
            "retire_unbound_claim_staging",
        },
        ("bootstrap_output_child", "STAGING_BOUND"): {"commit_bound_claim"},
        ("bootstrap_output_child", "PRIMARY_APPLIED"): {
            "bind_existing_child",
            "create_output_child",
        },
        ("retire_output_child_claim", "PREPARED"): {"retire_claim"},
        ("retire_output_child_claim", "PRIMARY_APPLIED"): {
            "confirm_claim_absent_and_current_exact"
        },
    }
    if action not in matrix.get((operation, stage), set()):
        raise SessionConflictError("live_start_output_bootstrap_action_stage_invalid")
    return _mint_authorization_under_lock(
        authorization_type=OutputChildBootstrapAuthorization,
        session_lease=session_lease,
        expected_session=expected_bootstrap_session,
        family="output_child_bootstrap",
        action=action,
    )


def advance_output_child_bootstrap_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_bootstrap_session: LiveStartSession,
    transition: str,
    bootstrap_authorization: OutputChildBootstrapAuthorization | None,
    physical_step_receipt: OutputChildBootstrapStepReceipt | None,
) -> LiveStartSession:
    if bootstrap_authorization is not None:
        raise SessionCapabilityError(
            "live_start_output_bootstrap_carrier_matrix_invalid"
        )
    action_by_transition = {
        "unbound_claim_staging_retired": "retire_unbound_claim_staging",
        "claim_staging_bound": "materialize_claim_staging",
        "claim_bound": "commit_bound_claim",
        "child_bound": None,
        "claim_unlinked": "retire_claim",
        "claim_retired": "confirm_claim_absent_and_current_exact",
    }
    if transition not in action_by_transition or physical_step_receipt is None:
        raise SessionValidationError("live_start_output_bootstrap_advance_invalid")
    expected_action = action_by_transition[transition]
    if transition == "child_bound":
        receipt_action = physical_step_receipt._opaque.action
        if receipt_action not in {"bind_existing_child", "create_output_child"}:
            raise SessionCapabilityError("live_start_output_bootstrap_receipt_action_invalid")
        expected_action = receipt_action
    assert expected_action is not None
    postcondition = _consume_receipt_under_lock(
        receipt=physical_step_receipt,
        receipt_type=OutputChildBootstrapStepReceipt,
        session_lease=session_lease,
        expected_session=expected_bootstrap_session,
        family="output_child_bootstrap",
        action=expected_action,
    )
    pending = _thaw(expected_bootstrap_session.pending_transition)
    evidence = _receipt_evidence(postcondition)
    if transition == "unbound_claim_staging_retired":
        pending["external_file_action"] = _retire_unbound_external_from_receipt(
            external=pending["external_file_action"],
            next_action_kind="materialize_claim_staging",
        )
    elif transition == "claim_staging_bound":
        pending["external_file_action"] = _bind_external_staging_from_receipt(
            external=pending["external_file_action"],
            evidence=evidence,
        )
        pending["stage"] = "STAGING_BOUND"
        pending["output_claim_staging_identity"] = evidence["staging_identity"]
        pending["output_claim_staging_size"] = evidence["staging_size"]
        pending["output_claim_staging_sha256"] = evidence["staging_sha256"]
    elif transition == "claim_bound":
        pending["stage"] = "PRIMARY_APPLIED"
        pending["external_file_action"] = None
        pending["output_claim_identity"] = _require_identity(
            evidence.get("claim_identity"), "claim_identity"
        )
        pending["output_claim_sha256"] = _require_sha256(
            evidence.get("claim_sha256"), "claim_sha256"
        )
    elif transition == "child_bound":
        binding = evidence.get("binding")
        if not isinstance(binding, Mapping):
            raise SessionCapabilityError("live_start_output_child_binding_receipt_invalid")
        validated = validate_embedded_document("output_child_binding", binding)
        _validate_output_child_binding_from_pending(
            predecessor=expected_bootstrap_session,
            pending=pending,
            binding=validated,
        )
        return _transition_receipt_authorized_under_lock(
            session_lease=session_lease,
            expected_session=expected_bootstrap_session,
            event="same_phase_cas",
            changes={
                "pending_transition": None,
                "output_child_binding": validated,
            },
        )
    elif transition == "claim_unlinked":
        child = expected_bootstrap_session.output_child_binding
        publication = expected_bootstrap_session.publication_binding
        expected_evidence = {
            "claim_path": pending.get("output_claim_path"),
            "claim_parent_identity": pending.get(
                "output_claim_parent_identity"
            ),
            "historical_claim_identity": pending.get(
                "output_claim_identity"
            ),
            "historical_claim_sha256": pending.get(
                "output_claim_sha256"
            ),
            "claim_disposition": "absent",
            "output_child_identity": (
                child.get("output_child_identity")
                if isinstance(child, Mapping)
                else None
            ),
            "publication_revision": (
                publication.get("revision")
                if isinstance(publication, Mapping)
                else None
            ),
            "publication_content_root_sha256": (
                publication.get("content_root_sha256")
                if isinstance(publication, Mapping)
                else None
            ),
        }
        for field_name, expected_value in expected_evidence.items():
            actual = evidence.get(field_name)
            if field_name.endswith("identity") and actual is not None:
                actual = _require_identity(actual, field_name)
                if expected_value is not None:
                    expected_value = _require_identity(
                        expected_value,
                        field_name,
                    )
            if actual != expected_value:
                raise SessionCapabilityError(
                    "live_start_output_claim_unlink_receipt_invalid"
                )
        pending["stage"] = "PRIMARY_APPLIED"
    else:
        retired_binding = evidence.get("output_child_binding")
        publication_binding = evidence.get("publication_binding")
        if not isinstance(retired_binding, Mapping) or not isinstance(publication_binding, Mapping):
            raise SessionCapabilityError("live_start_output_claim_retirement_receipt_invalid")
        validated = validate_embedded_document(
            "output_child_binding",
            retired_binding,
        )
        if set(publication_binding) != _PUBLICATION_BINDING_FIELDS:
            raise SessionCapabilityError("live_start_publication_rebinding_invalid")
        _validate_output_child_retirement_successor(
            predecessor=expected_bootstrap_session,
            retired_binding=validated,
            publication_binding=publication_binding,
        )
        return _transition_receipt_authorized_under_lock(
            session_lease=session_lease,
            expected_session=expected_bootstrap_session,
            event="same_phase_cas",
            changes={
                "pending_transition": None,
                "output_child_binding": validated,
                "publication_binding": publication_binding,
            },
        )
    return _transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=expected_bootstrap_session,
        event="same_phase_cas",
        changes={"pending_transition": _seal_pending(pending)},
    )


def _require_exact_apply_invocation(invocation: Any) -> ApplyInvocation:
    if type(invocation) is not ApplyInvocation:
        raise TypeError("apply_invocation_required")
    try:
        parsed = _parse_apply_invocation(invocation.canonical_json)
    except (TypeError, ValueError) as error:
        raise SessionCapabilityError(
            "live_start_apply_invocation_seal_invalid"
        ) from error
    if parsed != invocation:
        raise SessionCapabilityError(
            "live_start_apply_invocation_seal_invalid"
        )
    return invocation


def prepare_apply_attempt_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    invocation: ApplyInvocation,
    planned_admission_path: Path,
    planned_admission_staging_path: Path,
    planned_admission_staging_inner_temp_path: Path,
    planned_admission_parent_identity: PathIdentity,
    planned_admission_document_size: int,
    planned_admission_document_sha256: str,
) -> LiveStartSession:
    """Persist one apply/admission intent without touching its file surfaces."""

    _require_exact_apply_invocation(invocation)
    _require_apply_invocation_admission_capacity(invocation)
    if (
        expected_session.phase is not LiveStartPhase.PUBLICATION_COMMITTED
        or expected_session.pending_transition is not None
        or expected_session.apply_invocation_sha256 is not None
        or expected_session.runtime_admission_binding is not None
        or expected_session.runtime_layout_bootstrap is not None
    ):
        raise SessionConflictError(
            "live_start_apply_invocation_prepare_invalid"
        )
    operation = expected_session.output_operation_admission_binding
    child = expected_session.output_child_binding
    publication = expected_session.publication_binding
    if (
        not isinstance(operation, Mapping)
        or operation.get("state") != "ACTIVE"
        or not isinstance(child, Mapping)
        or child.get("claim_state") != "RETIRED"
        or not isinstance(publication, Mapping)
    ):
        raise SessionConflictError(
            "live_start_apply_invocation_authority_invalid"
        )
    if (
        invocation.run_id != expected_session.run_id
        or invocation.output_operation_admission_path
        != Path(str(operation.get("admission_path")))
        or invocation.output_operation_admission_identity
        != _require_identity(
            operation.get("admission_identity"),
            "output_operation_admission_identity",
        )
        or invocation.output_operation_admission_sha256
        != operation.get("admission_sha256")
        or invocation.output_child_binding_sha256
        != child.get("content_sha256")
        or invocation.output_child_path
        != Path(str(child.get("output_child_path")))
        or invocation.output_child_identity
        != _require_identity(
            child.get("output_child_identity"),
            "output_child_identity",
        )
        or invocation.operator_profile_sha256
        != operation.get("operator_profile_sha256")
        or invocation.publication_revision
        != publication.get("revision")
        or invocation.publication_content_root_sha256
        != publication.get("content_root_sha256")
    ):
        raise SessionCapabilityError(
            "live_start_apply_invocation_binding_invalid"
        )
    if (
        child.get("output_child_path")
        != publication.get("output_child_path")
        or child.get("output_child_identity")
        != publication.get("output_child_identity")
        or child.get("content_sha256")
        != publication.get("output_child_binding_sha256")
    ):
        raise SessionCapabilityError(
            "live_start_apply_invocation_publication_binding_invalid"
        )

    admission_path = Path(planned_admission_path)
    staging_path = Path(planned_admission_staging_path)
    inner_temp_path = Path(planned_admission_staging_inner_temp_path)
    if any(
        not path.is_absolute() or path != path.absolute()
        for path in (admission_path, staging_path, inner_temp_path)
    ):
        raise SessionValidationError(
            "live_start_runtime_admission_paths_invalid"
        )
    expected_staging_path = admission_path.with_name(
        ".live-start-active-attempt."
        f"{expected_session.run_id}.{invocation.apply_attempt_id}.staged"
    )
    expected_inner_temp_path = expected_staging_path.with_name(
        f".{expected_staging_path.name}.live-start-atomic.tmp"
    )
    parent_identity = _require_identity(
        planned_admission_parent_identity,
        "runtime_admission_parent_identity",
    )
    if (
        admission_path.name != RUNTIME_LIVE_ATTEMPT_ADMISSION_NAME
        or admission_path.parent
        != Path(str(operation.get("admission_path"))).parent
        or staging_path != expected_staging_path
        or inner_temp_path != expected_inner_temp_path
        or parent_identity
        != _require_identity(
            operation.get("state_root_identity"),
            "state_root_identity",
        )
    ):
        raise SessionCapabilityError(
            "live_start_runtime_admission_planned_binding_invalid"
        )
    planned_size = _bounded_integer(
        planned_admission_document_size,
        1,
        RUNTIME_LIVE_ATTEMPT_ADMISSION_MAX_BYTES,
        "runtime_admission_document_size",
    )
    planned_sha256 = _require_sha256(
        planned_admission_document_sha256,
        "runtime_admission_document_sha256",
    )
    external = _build_external_file_action(
        action_kind="materialize_runtime_admission_staging",
        action_index=0,
        final_path=admission_path,
        staging_path=staging_path,
        inner_temp_path=inner_temp_path,
        parent_identity=parent_identity,
        predecessor_identity=None,
        predecessor_size=None,
        predecessor_sha256=None,
        planned_successor_size=planned_size,
        planned_successor_sha256=planned_sha256,
        commit_mode="create_no_replace",
    )
    pending = _empty_pending_transition(
        session=expected_session,
        operation="install_apply_invocation",
        external_file_action=external,
    )
    pending.update(
        {
            "target_phase": LiveStartPhase.APPLY_STARTED.value,
            "successor_artifact_bindings": {
                **dict(expected_session.artifact_bindings),
                "receipts/apply_invocation.json": _bytes_sha256(
                    invocation.canonical_json
                ),
            },
            "apply_attempt_id": invocation.apply_attempt_id,
            "apply_invocation_sha256": invocation.content_sha256,
            "apply_invocation_document_size": len(
                invocation.canonical_json
            ),
            "runtime_admission_document_size": planned_size,
            "runtime_admission_document_sha256": planned_sha256,
            "runtime_admission_path": str(admission_path),
            "runtime_admission_staging_path": str(staging_path),
            "runtime_admission_staging_inner_temp_path": str(inner_temp_path),
            "runtime_admission_parent_identity": parent_identity,
        }
    )
    return _transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=expected_session,
        event="same_phase_cas",
        changes={"pending_transition": _seal_pending(pending)},
    )


def prepare_runtime_layout_bootstrap_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_admission_committed_session: LiveStartSession,
    layout_evidence: RuntimeLayoutBootstrapEvidence,
) -> LiveStartSession:
    pending = expected_admission_committed_session.pending_transition
    if (
        not isinstance(pending, Mapping)
        or pending.get("operation") != "install_apply_invocation"
        or pending.get("stage") != "PRIMARY_APPLIED"
        or pending.get("external_file_action") is not None
        or pending.get("next_action_index") != 0
        or pending.get("runtime_admission_identity") is None
        or pending.get("runtime_admission_sha256")
        != pending.get("runtime_admission_document_sha256")
        or expected_admission_committed_session.runtime_layout_bootstrap is not None
    ):
        raise SessionConflictError("live_start_runtime_layout_prepare_invalid")
    if not isinstance(layout_evidence, RuntimeLayoutBootstrapEvidence):
        raise TypeError("live_start_runtime_layout_evidence_invalid")
    validated = validate_embedded_document(
        "runtime_layout_bootstrap",
        layout_evidence.value,
    )
    if (
        validated.get("stage") != "INCOMPLETE"
        or validated.get("next_directory_index") != 0
        or validated.get("run_id")
        != expected_admission_committed_session.run_id
        or validated.get("apply_attempt_id")
        != pending.get("apply_attempt_id")
    ):
        raise SessionValidationError("live_start_runtime_layout_initial_stage_invalid")
    return _transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=expected_admission_committed_session,
        event="same_phase_cas",
        changes={"runtime_layout_bootstrap": validated},
    )


def _authorize_runtime_layout_bootstrap_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_layout_session: LiveStartSession,
    action: str,
) -> RuntimeLayoutBootstrapAuthorization:
    if action not in RUNTIME_LAYOUT_BOOTSTRAP_ACTIONS:
        raise SessionValidationError("live_start_runtime_layout_action_invalid")
    layout = expected_layout_session.runtime_layout_bootstrap
    if not isinstance(layout, Mapping) or layout.get("stage") != "INCOMPLETE":
        raise SessionConflictError("live_start_runtime_layout_cursor_invalid")
    return _mint_authorization_under_lock(
        authorization_type=RuntimeLayoutBootstrapAuthorization,
        session_lease=session_lease,
        expected_session=expected_layout_session,
        family="runtime_layout_bootstrap",
        action=action,
    )


def advance_runtime_layout_bootstrap_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_layout_session: LiveStartSession,
    transition: str,
    physical_step_receipt: RuntimeLayoutBootstrapStepReceipt,
) -> LiveStartSession:
    if transition != "directory_bound":
        raise SessionValidationError("live_start_runtime_layout_advance_invalid")
    postcondition = _consume_receipt_under_lock(
        receipt=physical_step_receipt,
        receipt_type=RuntimeLayoutBootstrapStepReceipt,
        session_lease=session_lease,
        expected_session=expected_layout_session,
        family="runtime_layout_bootstrap",
        action="create_or_confirm_runtime_layout_directory",
    )
    evidence = _receipt_evidence(postcondition)
    layout = evidence.get("runtime_layout_bootstrap")
    if not isinstance(layout, Mapping):
        raise SessionCapabilityError("live_start_runtime_layout_receipt_invalid")
    validated = validate_embedded_document("runtime_layout_bootstrap", layout)
    current = expected_layout_session.runtime_layout_bootstrap
    if not isinstance(current, Mapping):
        raise SessionConflictError("live_start_runtime_layout_cursor_missing")
    _validate_runtime_layout_successor(
        predecessor=current,
        successor=validated,
    )
    current_index = current.get("next_directory_index")
    current_rows = current.get("directories")
    next_rows = validated.get("directories")
    if (
        type(current_index) is not int
        or not isinstance(current_rows, Sequence)
        or not isinstance(next_rows, Sequence)
        or current_index >= len(current_rows)
    ):
        raise SessionCapabilityError(
            "live_start_runtime_layout_receipt_invalid"
        )
    current_row = current_rows[current_index]
    next_row = next_rows[current_index]
    expected_evidence_fields = {
        "runtime_layout_bootstrap",
        "directory_path",
        "directory_parent_identity",
        "directory_identity",
    }
    if validated["stage"] == "COMPLETE":
        expected_evidence_fields.add("invocation_receipt_file_action")
    if (
        set(evidence) != expected_evidence_fields
        or evidence.get("directory_path") != current_row.get("path")
        or _require_identity(
            evidence.get("directory_parent_identity"),
            "directory_parent_identity",
        )
        != _require_identity(
            next_row.get("expected_parent_identity"),
            "expected_parent_identity",
        )
        or _require_identity(
            evidence.get("directory_identity"),
            "directory_identity",
        )
        != _require_identity(
            next_row.get("successor_identity"),
            "successor_identity",
        )
    ):
        raise SessionCapabilityError(
            "live_start_runtime_layout_receipt_invalid"
        )
    changes: dict[str, Any] = {"runtime_layout_bootstrap": validated}
    if validated["stage"] == "COMPLETE":
        pending = _thaw(expected_layout_session.pending_transition)
        invocation_action = evidence.get("invocation_receipt_file_action")
        if not isinstance(invocation_action, Mapping):
            raise SessionCapabilityError("live_start_invocation_receipt_intent_missing")
        validated_action = validate_embedded_document(
            "external_file_action",
            invocation_action,
        )
        expected_receipt_path = (
            session_lease.session_root
            / "receipts"
            / "apply_invocation.json"
        )
        successor_bindings = pending.get("successor_artifact_bindings")
        expected_receipt_sha256 = (
            successor_bindings.get("receipts/apply_invocation.json")
            if isinstance(successor_bindings, Mapping)
            else None
        )
        expected_receipt_size = _bounded_integer(
            pending.get("apply_invocation_document_size"),
            1,
            APPLY_INVOCATION_MAX_BYTES,
            "apply_invocation_document_size",
        )
        expected_receipt_staging_path = expected_receipt_path.with_name(
            f"{expected_receipt_path.name}.staged"
        )
        expected_receipt_inner_temp_path = (
            expected_receipt_staging_path.with_name(
                "."
                f"{expected_receipt_staging_path.name}"
                ".live-start-atomic.tmp"
            )
        )
        if (
            validated_action.get("action_kind")
            != "materialize_invocation_receipt_staging"
            or validated_action.get("action_index") != 0
            or validated_action.get("stage") != "PLANNED"
            or validated_action.get("final_path")
            != str(expected_receipt_path)
            or validated_action.get("staging_path")
            != str(expected_receipt_staging_path)
            or validated_action.get("inner_temp_path")
            != str(expected_receipt_inner_temp_path)
            or validated_action.get("commit_mode") != "create_no_replace"
            or validated_action.get("predecessor_state") != "absent"
            or validated_action.get("planned_successor_size")
            != expected_receipt_size
            or validated_action.get("planned_successor_sha256")
            != expected_receipt_sha256
        ):
            raise SessionCapabilityError(
                "live_start_invocation_receipt_intent_invalid"
            )
        pending["external_file_action"] = validated_action
        changes["pending_transition"] = _seal_pending(pending)
    return _transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=expected_layout_session,
        event="same_phase_cas",
        changes=changes,
    )


def _authorize_runtime_admission_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_admission_session: LiveStartSession,
    action: str,
) -> RuntimeAdmissionAuthorization:
    if action not in RUNTIME_ADMISSION_ACTIONS:
        raise SessionValidationError("live_start_runtime_admission_action_invalid")
    pending = expected_admission_session.pending_transition
    if (
        not isinstance(pending, Mapping)
        or pending.get("operation") != "install_apply_invocation"
    ):
        raise SessionConflictError("live_start_runtime_admission_cursor_invalid")
    external = pending.get("external_file_action")
    if not isinstance(external, Mapping):
        raise SessionConflictError(
            "live_start_runtime_admission_file_action_missing"
        )
    stage = pending.get("stage")
    external_stage = external.get("stage")
    external_action = external.get("action_kind")
    if action in {
        "materialize_runtime_admission_staging",
        "retire_unbound_runtime_admission_staging",
    }:
        allowed = (
            stage == "PREPARED"
            and external_stage == "PLANNED"
            and external_action == "materialize_runtime_admission_staging"
        )
    elif action == "commit_bound_runtime_admission":
        allowed = (
            stage == "STAGING_BOUND"
            and external_stage == "STAGING_BOUND"
            and external_action == action
        )
    elif action in {
        "materialize_invocation_receipt_staging",
        "retire_unbound_invocation_receipt_staging",
    }:
        layout = expected_admission_session.runtime_layout_bootstrap
        allowed = (
            stage == "PRIMARY_APPLIED"
            and isinstance(layout, Mapping)
            and layout.get("stage") == "COMPLETE"
            and external_stage == "PLANNED"
            and external_action
            == "materialize_invocation_receipt_staging"
        )
    else:
        layout = expected_admission_session.runtime_layout_bootstrap
        allowed = (
            stage == "PRIMARY_APPLIED"
            and isinstance(layout, Mapping)
            and layout.get("stage") == "COMPLETE"
            and external_stage == "STAGING_BOUND"
            and external_action == "commit_bound_invocation_receipt"
        )
    if not allowed:
        raise SessionConflictError(
            "live_start_runtime_admission_action_mismatch"
        )
    if stage == "PRIMARY_APPLIED":
        session_bearer, current = (
            _authenticate_authorization_cursor_under_lock(
                session_lease=session_lease,
                expected_session=expected_admission_session,
            )
        )
        _require_exact_invocation_receipt_run_location_under_lock(
            session_lease=session_lease,
            session=current,
        )
        return _mint_authorization_for_authenticated_cursor(
            authorization_type=RuntimeAdmissionAuthorization,
            session_bearer=session_bearer,
            current=current,
            family="runtime_admission",
            action=action,
        )
    return _mint_authorization_under_lock(
        authorization_type=RuntimeAdmissionAuthorization,
        session_lease=session_lease,
        expected_session=expected_admission_session,
        family="runtime_admission",
        action=action,
    )


def _require_exact_invocation_receipt_run_location_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    session: LiveStartSession,
) -> None:
    pending = session.pending_transition
    operation = session.output_operation_admission_binding
    if not isinstance(pending, Mapping) or not isinstance(operation, Mapping):
        raise SessionConflictError(
            "live_start_invocation_receipt_run_location_changed"
        )
    external = pending.get("external_file_action")
    successor_bindings = pending.get("successor_artifact_bindings")
    expected_final = (
        session_lease.session_root / "receipts" / "apply_invocation.json"
    )
    expected_staging = expected_final.with_name(
        f"{expected_final.name}.staged"
    )
    expected_inner_temp = expected_staging.with_name(
        f".{expected_staging.name}.live-start-atomic.tmp"
    )
    try:
        receipts_parent_identity = path_identity(expected_final.parent)
    except (OSError, ValueError) as error:
        raise SessionConflictError(
            "live_start_invocation_receipt_run_location_changed"
        ) from error
    receipt_sha256 = (
        successor_bindings.get("receipts/apply_invocation.json")
        if isinstance(successor_bindings, Mapping)
        else None
    )
    if (
        pending.get("operation") != "install_apply_invocation"
        or pending.get("stage") != "PRIMARY_APPLIED"
        or not isinstance(external, Mapping)
        or external.get("final_path") != str(expected_final)
        or external.get("staging_path") != str(expected_staging)
        or external.get("inner_temp_path") != str(expected_inner_temp)
        or _require_identity(
            external.get("parent_identity"),
            "invocation_receipt_parent_identity",
        )
        != receipts_parent_identity
        or operation.get("session_root") != str(session_lease.session_root)
        or _require_identity(
            operation.get("session_root_identity"),
            "output_operation_session_root_identity",
        )
        != session_lease.session_root_identity
        or external.get("planned_successor_sha256") != receipt_sha256
    ):
        raise SessionConflictError(
            "live_start_invocation_receipt_run_location_changed"
        )


def advance_runtime_admission_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_admission_session: LiveStartSession,
    transition: str,
    physical_step_receipt: RuntimeAdmissionStepReceipt,
) -> LiveStartSession:
    action_by_transition = {
        "unbound_staging_retired": "retire_unbound_runtime_admission_staging",
        "staging_bound": "materialize_runtime_admission_staging",
        "admission_primary_applied": "commit_bound_runtime_admission",
        "invocation_receipt_unbound_staging_retired": (
            "retire_unbound_invocation_receipt_staging"
        ),
        "invocation_receipt_staging_bound": (
            "materialize_invocation_receipt_staging"
        ),
        "invocation_receipt_committed": "commit_bound_invocation_receipt",
    }
    try:
        action = action_by_transition[transition]
    except KeyError as error:
        raise SessionValidationError("live_start_runtime_admission_advance_invalid") from error
    pending_value = expected_admission_session.pending_transition
    if (
        not isinstance(pending_value, Mapping)
        or pending_value.get("operation") != "install_apply_invocation"
        or not isinstance(
            pending_value.get("external_file_action"),
            Mapping,
        )
    ):
        raise SessionConflictError(
            "live_start_runtime_admission_cursor_invalid"
        )
    _validate_runtime_admission_transition_cursor(
        expected_session=expected_admission_session,
        transition=transition,
    )
    postcondition = _consume_receipt_under_lock(
        receipt=physical_step_receipt,
        receipt_type=RuntimeAdmissionStepReceipt,
        session_lease=session_lease,
        expected_session=expected_admission_session,
        family="runtime_admission",
        action=action,
    )
    pending = _thaw(expected_admission_session.pending_transition)
    external = pending["external_file_action"]
    evidence = _receipt_evidence(postcondition)
    _validate_runtime_admission_step_evidence(
        expected_session=expected_admission_session,
        transition=transition,
        external=external,
        evidence=evidence,
    )
    if transition.endswith("unbound_staging_retired"):
        next_action = (
            "materialize_invocation_receipt_staging"
            if transition.startswith("invocation")
            else "materialize_runtime_admission_staging"
        )
        pending["external_file_action"] = _retire_unbound_external_from_receipt(
            external=external,
            next_action_kind=next_action,
        )
    elif transition.endswith("staging_bound"):
        bound_external = _bind_external_staging_from_receipt(
            external=external,
            evidence=evidence,
        )
        bound_value = _thaw(bound_external)
        bound_value.pop("content_sha256", None)
        bound_value["action_kind"] = (
            "commit_bound_invocation_receipt"
            if transition.startswith("invocation")
            else "commit_bound_runtime_admission"
        )
        pending["external_file_action"] = seal_embedded_document(
            "external_file_action",
            bound_value,
        )
        if transition == "staging_bound":
            pending["stage"] = "STAGING_BOUND"
            pending["runtime_admission_staging_identity"] = _require_identity(
                evidence["staging_identity"],
                "runtime_admission_staging_identity",
            )
            pending["runtime_admission_staging_size"] = evidence["staging_size"]
            pending["runtime_admission_staging_sha256"] = evidence["staging_sha256"]
    elif transition == "admission_primary_applied":
        pending["stage"] = "PRIMARY_APPLIED"
        pending["runtime_admission_identity"] = _require_identity(
            evidence.get("admission_identity"), "admission_identity"
        )
        pending["runtime_admission_sha256"] = _require_sha256(
            evidence.get("admission_sha256"), "admission_sha256"
        )
        pending["external_file_action"] = None
    else:
        pending["external_file_action"] = None
        pending["next_action_index"] += 1
    return _transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=expected_admission_session,
        event="same_phase_cas",
        changes={"pending_transition": _seal_pending(pending)},
    )


def _validate_runtime_admission_transition_cursor(
    *,
    expected_session: LiveStartSession,
    transition: str,
) -> None:
    pending = expected_session.pending_transition
    if not isinstance(pending, Mapping):
        raise SessionConflictError(
            "live_start_runtime_admission_cursor_invalid"
        )
    external = pending.get("external_file_action")
    if not isinstance(external, Mapping):
        raise SessionConflictError(
            "live_start_runtime_admission_cursor_invalid"
        )
    expected_rows = {
        "unbound_staging_retired": (
            "PREPARED",
            "PLANNED",
            "materialize_runtime_admission_staging",
        ),
        "staging_bound": (
            "PREPARED",
            "PLANNED",
            "materialize_runtime_admission_staging",
        ),
        "admission_primary_applied": (
            "STAGING_BOUND",
            "STAGING_BOUND",
            "commit_bound_runtime_admission",
        ),
        "invocation_receipt_unbound_staging_retired": (
            "PRIMARY_APPLIED",
            "PLANNED",
            "materialize_invocation_receipt_staging",
        ),
        "invocation_receipt_staging_bound": (
            "PRIMARY_APPLIED",
            "PLANNED",
            "materialize_invocation_receipt_staging",
        ),
        "invocation_receipt_committed": (
            "PRIMARY_APPLIED",
            "STAGING_BOUND",
            "commit_bound_invocation_receipt",
        ),
    }
    row = expected_rows[transition]
    if (
        pending.get("stage") != row[0]
        or external.get("stage") != row[1]
        or external.get("action_kind") != row[2]
    ):
        raise SessionConflictError(
            "live_start_runtime_admission_transition_cursor_invalid"
        )
    if transition.startswith("invocation"):
        layout = expected_session.runtime_layout_bootstrap
        if not isinstance(layout, Mapping) or layout.get("stage") != "COMPLETE":
            raise SessionConflictError(
                "live_start_invocation_receipt_before_layout_complete"
            )


def _validate_runtime_admission_step_evidence(
    *,
    expected_session: LiveStartSession,
    transition: str,
    external: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> None:
    pending = expected_session.pending_transition
    if not isinstance(pending, Mapping):
        raise SessionConflictError(
            "live_start_runtime_admission_cursor_invalid"
        )
    if transition in {
        "staging_bound",
        "invocation_receipt_staging_bound",
    }:
        expected_fields = frozenset(
            {
                "staging_path",
                "staging_parent_identity",
                "staging_identity",
                "staging_size",
                "staging_sha256",
                "final_absent",
                "inner_temp_absent",
            }
        )
        if set(evidence) != expected_fields:
            raise SessionCapabilityError(
                "live_start_runtime_admission_staging_receipt_invalid"
            )
        if (
            evidence.get("staging_path") != external.get("staging_path")
            or _require_identity(
                evidence.get("staging_parent_identity"),
                "staging_parent_identity",
            )
            != _require_identity(
                external.get("parent_identity"),
                "parent_identity",
            )
            or evidence.get("staging_size")
            != external.get("planned_successor_size")
            or evidence.get("staging_sha256")
            != external.get("planned_successor_sha256")
            or evidence.get("final_absent") is not True
            or evidence.get("inner_temp_absent") is not True
        ):
            raise SessionCapabilityError(
                "live_start_runtime_admission_staging_receipt_invalid"
            )
        _require_identity(evidence.get("staging_identity"), "staging_identity")
        return
    if transition == "admission_primary_applied":
        expected_fields = frozenset(
            {
                "admission_path",
                "admission_parent_identity",
                "admission_identity",
                "admission_size",
                "admission_sha256",
                "staging_path",
                "staging_absent",
                "inner_temp_path",
                "inner_temp_absent",
            }
        )
        if set(evidence) != expected_fields:
            raise SessionCapabilityError(
                "live_start_runtime_admission_commit_receipt_invalid"
            )
        final_identity = _require_identity(
            evidence.get("admission_identity"),
            "admission_identity",
        )
        if (
            evidence.get("admission_path") != external.get("final_path")
            or _require_identity(
                evidence.get("admission_parent_identity"),
                "admission_parent_identity",
            )
            != _require_identity(
                external.get("parent_identity"),
                "parent_identity",
            )
            or final_identity
            != _require_identity(
                external.get("staging_identity"),
                "staging_identity",
            )
            or evidence.get("admission_size")
            != external.get("planned_successor_size")
            or evidence.get("admission_sha256")
            != external.get("planned_successor_sha256")
            or evidence.get("staging_path") != external.get("staging_path")
            or evidence.get("inner_temp_path")
            != external.get("inner_temp_path")
            or evidence.get("staging_absent") is not True
            or evidence.get("inner_temp_absent") is not True
        ):
            raise SessionCapabilityError(
                "live_start_runtime_admission_commit_receipt_invalid"
            )
        return
    if transition == "invocation_receipt_committed":
        expected_fields = frozenset(
            {
                "invocation_receipt_path",
                "invocation_receipt_parent_identity",
                "invocation_receipt_identity",
                "invocation_receipt_size",
                "invocation_receipt_sha256",
                "apply_invocation_sha256",
                "staging_absent",
                "inner_temp_absent",
            }
        )
        if set(evidence) != expected_fields:
            raise SessionCapabilityError(
                "live_start_invocation_receipt_commit_invalid"
            )
        receipt_identity = _require_identity(
            evidence.get("invocation_receipt_identity"),
            "invocation_receipt_identity",
        )
        if (
            evidence.get("invocation_receipt_path")
            != external.get("final_path")
            or _require_identity(
                evidence.get("invocation_receipt_parent_identity"),
                "invocation_receipt_parent_identity",
            )
            != _require_identity(
                external.get("parent_identity"),
                "parent_identity",
            )
            or receipt_identity
            != _require_identity(
                external.get("staging_identity"),
                "staging_identity",
            )
            or evidence.get("invocation_receipt_size")
            != external.get("planned_successor_size")
            or evidence.get("invocation_receipt_sha256")
            != external.get("planned_successor_sha256")
            or evidence.get("apply_invocation_sha256")
            != pending.get("apply_invocation_sha256")
            or evidence.get("staging_absent") is not True
            or evidence.get("inner_temp_absent") is not True
        ):
            raise SessionCapabilityError(
                "live_start_invocation_receipt_commit_invalid"
            )
        return
    _validate_runtime_admission_cleanup_evidence(
        transition=transition,
        pending=pending,
        external=external,
        evidence=evidence,
    )


def _validate_runtime_admission_cleanup_evidence(
    *,
    transition: str,
    pending: Mapping[str, Any],
    external: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> None:
    if transition == "unbound_staging_retired":
        expected_fields = frozenset(
            {
                "admission_path",
                "admission_absent",
                "staging_path",
                "historical_staging_identity",
                "historical_staging_size",
                "historical_staging_sha256",
                "staging_absent",
                "inner_temp_path",
                "inner_temp_absent",
                "invocation_receipt_path",
                "invocation_receipt_absent",
            }
        )
        historical = (
            evidence.get("historical_staging_identity"),
            evidence.get("historical_staging_size"),
            evidence.get("historical_staging_sha256"),
        )
        if set(evidence) != expected_fields or (
            not all(item is None for item in historical)
            and (
                historical[0] is None
                or _require_identity(
                    historical[0],
                    "historical_staging_identity",
                )
                is None
                or historical[1] != external.get("planned_successor_size")
                or historical[2]
                != external.get("planned_successor_sha256")
            )
        ):
            raise SessionCapabilityError(
                "live_start_runtime_admission_cleanup_receipt_invalid"
            )
        receipt_path = _require_absolute_path(
            evidence.get("invocation_receipt_path"),
            "invocation_receipt_path",
        )
        if (
            evidence.get("admission_path") != external.get("final_path")
            or evidence.get("staging_path") != external.get("staging_path")
            or evidence.get("inner_temp_path")
            != external.get("inner_temp_path")
            or receipt_path.name != "apply_invocation.json"
            or receipt_path.parent.name != "receipts"
            or evidence.get("admission_absent") is not True
            or evidence.get("staging_absent") is not True
            or evidence.get("inner_temp_absent") is not True
            or evidence.get("invocation_receipt_absent") is not True
        ):
            raise SessionCapabilityError(
                "live_start_runtime_admission_cleanup_receipt_invalid"
            )
        return
    expected_fields = frozenset(
        {
            "invocation_receipt_path",
            "invocation_receipt_absent",
            "staging_path",
            "historical_staging_identity",
            "historical_staging_size",
            "historical_staging_sha256",
            "staging_absent",
            "inner_temp_path",
            "inner_temp_absent",
            "admission_path",
            "admission_identity",
            "admission_sha256",
        }
    )
    historical = (
        evidence.get("historical_staging_identity"),
        evidence.get("historical_staging_size"),
        evidence.get("historical_staging_sha256"),
    )
    if (
        set(evidence) != expected_fields
        or (
            not all(item is None for item in historical)
            and (
                historical[0] is None
                or _require_identity(
                    historical[0],
                    "historical_staging_identity",
                )
                is None
                or historical[1] != external.get("planned_successor_size")
                or historical[2]
                != external.get("planned_successor_sha256")
            )
        )
        or evidence.get("invocation_receipt_path")
        != external.get("final_path")
        or evidence.get("staging_path") != external.get("staging_path")
        or evidence.get("inner_temp_path") != external.get("inner_temp_path")
        or evidence.get("admission_path")
        != pending.get("runtime_admission_path")
        or _require_identity(
            evidence.get("admission_identity"),
            "admission_identity",
        )
        != _require_identity(
            pending.get("runtime_admission_identity"),
            "runtime_admission_identity",
        )
        or evidence.get("admission_sha256")
        != pending.get("runtime_admission_sha256")
        or evidence.get("invocation_receipt_absent") is not True
        or evidence.get("staging_absent") is not True
        or evidence.get("inner_temp_absent") is not True
    ):
        raise SessionCapabilityError(
            "live_start_invocation_receipt_cleanup_receipt_invalid"
        )


def _complete_apply_started_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_receipt_committed_session: LiveStartSession,
    invocation: ApplyInvocation,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
) -> LiveStartSession:
    """Perform the sole I/O-free receipt-committed APPLY_STARTED CAS."""

    pending = expected_receipt_committed_session.pending_transition
    layout = expected_receipt_committed_session.runtime_layout_bootstrap
    operation = (
        expected_receipt_committed_session.output_operation_admission_binding
    )
    child = expected_receipt_committed_session.output_child_binding
    publication = expected_receipt_committed_session.publication_binding
    if (
        expected_receipt_committed_session.phase
        is not LiveStartPhase.PUBLICATION_COMMITTED
        or not isinstance(pending, Mapping)
        or pending.get("operation") != "install_apply_invocation"
        or pending.get("stage") != "PRIMARY_APPLIED"
        or pending.get("source_phase") != "PUBLICATION_COMMITTED"
        or pending.get("target_phase") != "APPLY_STARTED"
        or pending.get("external_file_action") is not None
        or pending.get("next_action_index") != 1
        or not isinstance(layout, Mapping)
        or layout.get("stage") != "COMPLETE"
        or pending.get("apply_attempt_id")
        != layout.get("apply_attempt_id")
        or not isinstance(operation, Mapping)
        or operation.get("state") != "ACTIVE"
        or not isinstance(child, Mapping)
        or child.get("claim_state") != "RETIRED"
        or not isinstance(publication, Mapping)
    ):
        raise SessionConflictError(
            "live_start_apply_started_receipt_cursor_invalid"
        )

    _require_exact_apply_invocation(invocation)
    if invocation.content_sha256 != pending.get("apply_invocation_sha256"):
        raise SessionCapabilityError(
            "live_start_apply_started_invocation_binding_invalid"
        )
    if type(runtime_admission) is not RuntimeLiveAttemptAdmissionEvidence:
        raise SessionCapabilityError(
            "runtime_admission_missing_or_invalid: evidence required"
        )
    _validate_apply_started_authority_bindings(
        session_lease=session_lease,
        session=expected_receipt_committed_session,
        pending=pending,
        layout=layout,
        operation=operation,
        child=child,
        publication=publication,
        invocation=invocation,
        runtime_admission=runtime_admission,
    )
    admission = _normalize_json({
        "admission_path": pending.get("runtime_admission_path"),
        "admission_parent_identity": pending.get(
            "runtime_admission_parent_identity"
        ),
        "admission_identity": pending.get("runtime_admission_identity"),
        "admission_sha256": pending.get("runtime_admission_sha256"),
        "output_operation_admission_path": operation.get("admission_path"),
        "output_operation_admission_identity": operation.get(
            "admission_identity"
        ),
        "output_operation_admission_sha256": operation.get(
            "admission_sha256"
        ),
        "output_child_binding_sha256": child.get("content_sha256"),
        "output_child_path": child.get("output_child_path"),
        "output_child_identity": child.get("output_child_identity"),
        "publication_revision": publication.get("revision"),
        "publication_content_root_sha256": publication.get(
            "content_root_sha256"
        ),
    })
    if not isinstance(admission, dict):
        raise SessionCapabilityError(
            "runtime_admission_missing_or_invalid"
        )
    _validate_runtime_admission_binding(admission)

    handoff = _thaw(operation)
    handoff.pop("content_sha256", None)
    handoff.update(
        {
            "state": "RUNTIME_HANDOFF_RELEASE_AUTHORIZED",
            "release_handoff_kind": "runtime_admission",
            "handoff_runtime_admission_path": admission[
                "admission_path"
            ],
            "handoff_runtime_admission_parent_identity": admission[
                "admission_parent_identity"
            ],
            "handoff_runtime_admission_identity": admission[
                "admission_identity"
            ],
            "handoff_runtime_admission_sha256": admission[
                "admission_sha256"
            ],
        }
    )
    sealed_handoff = seal_embedded_document(
        "output_operation_admission_binding",
        handoff,
    )
    successor_bindings = pending.get("successor_artifact_bindings")
    if not isinstance(successor_bindings, Mapping):
        raise SessionConflictError(
            "live_start_apply_started_artifact_binding_invalid"
        )
    return _transition_validated_apply_started_under_lock(
        session_lease=session_lease,
        expected_session=expected_receipt_committed_session,
        changes={
            "artifact_bindings": successor_bindings,
            "pending_transition": None,
            "output_operation_admission_binding": sealed_handoff,
            "apply_invocation_sha256": invocation.content_sha256,
            "runtime_admission_binding": admission,
        },
    )


def _validate_apply_started_authority_bindings(
    *,
    session_lease: LiveStartSessionLease,
    session: LiveStartSession,
    pending: Mapping[str, Any],
    layout: Mapping[str, Any],
    operation: Mapping[str, Any],
    child: Mapping[str, Any],
    publication: Mapping[str, Any],
    invocation: ApplyInvocation,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence,
) -> None:
    try:
        admission_parent_identity = _require_identity(
            pending.get("runtime_admission_parent_identity"),
            "runtime_admission_parent_identity",
        )
        admission_identity = _require_identity(
            pending.get("runtime_admission_identity"),
            "runtime_admission_identity",
        )
        runtime_root_identity = _require_identity(
            layout.get("runtime_root_identity"),
            "runtime_root_identity",
        )
        operation_identity = _require_identity(
            operation.get("admission_identity"),
            "output_operation_admission_identity",
        )
        child_identity = _require_identity(
            child.get("output_child_identity"),
            "output_child_identity",
        )
        output_base_identity = _require_identity(
            child.get("output_base_identity"),
            "output_base_identity",
        )
        operation_output_base_identity = _require_identity(
            operation.get("output_base_root_identity"),
            "output_base_root_identity",
        )
        state_root_identity = _require_identity(
            operation.get("state_root_identity"),
            "state_root_identity",
        )
    except SessionValidationError as error:
        raise SessionCapabilityError(
            "runtime_admission_missing_or_invalid"
        ) from error
    expected_retention_path = (
        invocation.runtime_root
        / ".hsconfig"
        / "attempt-retention"
        / f"{invocation.apply_attempt_id}.json"
    )
    evidence_bindings = (
        runtime_admission.admission_path
        == Path(str(pending.get("runtime_admission_path"))),
        runtime_admission.admission_parent_identity
        == admission_parent_identity,
        runtime_admission.admission_identity == admission_identity,
        runtime_admission.admission_sha256
        == pending.get("runtime_admission_sha256")
        == pending.get("runtime_admission_document_sha256"),
        runtime_admission.run_id == session.run_id == invocation.run_id,
        runtime_admission.apply_attempt_id
        == pending.get("apply_attempt_id")
        == invocation.apply_attempt_id,
        runtime_admission.retention_owner_run_id == session.run_id,
        runtime_admission.session_root == session_lease.session_root,
        runtime_admission.session_root_identity
        == session_lease.session_root_identity,
        operation.get("session_root") == str(session_lease.session_root),
        operation.get("session_root_identity")
        == session_lease.session_root_identity,
        runtime_admission.operator_profile_sha256
        == operation.get("operator_profile_sha256")
        == invocation.operator_profile_sha256,
        runtime_admission.state_root_identity
        == state_root_identity
        == admission_parent_identity,
        runtime_admission.runtime_root
        == Path(str(layout.get("runtime_root")))
        == invocation.runtime_root,
        runtime_admission.runtime_root_identity
        == runtime_root_identity
        == invocation.runtime_root_identity,
        runtime_admission.output_base_root
        == Path(str(child.get("output_base_path")))
        == Path(str(operation.get("output_base_root"))),
        runtime_admission.output_base_root_identity
        == output_base_identity
        == operation_output_base_identity,
        runtime_admission.output_root
        == Path(str(child.get("output_child_path")))
        == Path(str(operation.get("output_child_path")))
        == invocation.output_child_path,
        runtime_admission.output_root_identity
        == child_identity
        == invocation.output_child_identity,
        runtime_admission.output_operation_admission_path
        == Path(str(operation.get("admission_path")))
        == invocation.output_operation_admission_path,
        runtime_admission.output_operation_admission_identity
        == operation_identity
        == invocation.output_operation_admission_identity,
        runtime_admission.output_operation_admission_sha256
        == operation.get("admission_sha256")
        == invocation.output_operation_admission_sha256,
        runtime_admission.output_child_binding_sha256
        == child.get("content_sha256")
        == invocation.output_child_binding_sha256,
        runtime_admission.publication_revision
        == publication.get("revision")
        == invocation.publication_revision,
        runtime_admission.publication_content_root_sha256
        == publication.get("content_root_sha256")
        == invocation.publication_content_root_sha256,
        runtime_admission.pre_apply_runtime_snapshot_sha256
        == invocation.pre_apply_runtime_snapshot.content_sha256,
        runtime_admission.apply_invocation_sha256
        == invocation.content_sha256,
        runtime_admission.retention_fence_path == expected_retention_path,
    )
    try:
        _require_sha256(
            runtime_admission.package_root_sha256,
            "package_root_sha256",
        )
    except SessionValidationError as error:
        raise SessionCapabilityError(
            "runtime_admission_missing_or_invalid"
        ) from error
    if not all(evidence_bindings):
        raise SessionCapabilityError(
            "runtime_admission_missing_or_invalid"
        )


def resume_pending_apply_invocation_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    invocation: ApplyInvocation,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence | None,
    transition: str,
    physical_step_receipt: RuntimeAdmissionStepReceipt | None,
) -> LiveStartSession:
    """Resume only receipt-CAS, rollback, validation, or final-CAS edges."""

    if transition not in {
        "rollback_prepared",
        "validate_primary",
        "commit_invocation_receipt",
        "complete_apply_started",
    }:
        raise SessionValidationError(
            "live_start_apply_invocation_resume_transition_invalid"
        )
    _require_exact_apply_invocation(invocation)
    _require_session_lease(session_lease)
    current = _load_expected_predecessor_under_lock(
        session_lease=session_lease,
        expected_session=expected_session,
    )
    pending = current.pending_transition
    if (
        not isinstance(pending, Mapping)
        or pending.get("operation") != "install_apply_invocation"
        or pending.get("apply_invocation_sha256")
        != invocation.content_sha256
        or pending.get("apply_invocation_document_size")
        != len(invocation.canonical_json)
        or pending.get("apply_attempt_id") != invocation.apply_attempt_id
        or invocation.run_id != current.run_id
    ):
        raise SessionCapabilityError(
            "live_start_apply_invocation_required_or_mismatched"
        )
    successor_bindings = pending.get("successor_artifact_bindings")
    if (
        not isinstance(successor_bindings, Mapping)
        or successor_bindings.get("receipts/apply_invocation.json")
        != _bytes_sha256(invocation.canonical_json)
    ):
        raise SessionCapabilityError(
            "live_start_apply_invocation_receipt_binding_invalid"
        )

    if transition == "rollback_prepared":
        if runtime_admission is not None:
            raise SessionCapabilityError(
                "runtime_admission_missing_or_invalid"
            )
        if pending.get("stage") != "PREPARED":
            raise SessionConflictError(
                "live_start_apply_invocation_rollback_invalid"
            )
        rollback_cursor = current
        if physical_step_receipt is not None:
            rollback_cursor = advance_runtime_admission_under_lock(
                session_lease=session_lease,
                expected_admission_session=current,
                transition="unbound_staging_retired",
                physical_step_receipt=physical_step_receipt,
            )
        return _transition_receipt_authorized_under_lock(
            session_lease=session_lease,
            expected_session=rollback_cursor,
            event="same_phase_cas",
            changes={"pending_transition": None},
        )

    _validate_pending_runtime_admission_evidence(
        session_lease=session_lease,
        session=current,
        invocation=invocation,
        runtime_admission=runtime_admission,
    )
    if transition == "validate_primary":
        if physical_step_receipt is not None or (
            pending.get("stage") != "PRIMARY_APPLIED"
            or pending.get("external_file_action") is not None
            or pending.get("next_action_index") != 0
        ):
            raise SessionConflictError(
                "live_start_apply_invocation_primary_cursor_invalid"
            )
        return current
    if transition == "commit_invocation_receipt":
        if physical_step_receipt is None:
            raise SessionCapabilityError(
                "live_start_invocation_receipt_required"
            )
        return advance_runtime_admission_under_lock(
            session_lease=session_lease,
            expected_admission_session=current,
            transition="invocation_receipt_committed",
            physical_step_receipt=physical_step_receipt,
        )
    if physical_step_receipt is not None:
        raise SessionCapabilityError(
            "live_start_apply_started_physical_receipt_forbidden"
        )
    return _complete_apply_started_under_lock(
        session_lease=session_lease,
        expected_receipt_committed_session=current,
        invocation=invocation,
        runtime_admission=runtime_admission,
    )


def _validate_pending_runtime_admission_evidence(
    *,
    session_lease: LiveStartSessionLease,
    session: LiveStartSession,
    invocation: ApplyInvocation,
    runtime_admission: RuntimeLiveAttemptAdmissionEvidence | None,
) -> None:
    if type(runtime_admission) is not RuntimeLiveAttemptAdmissionEvidence:
        raise SessionCapabilityError(
            "runtime_admission_missing_or_invalid: evidence required"
        )
    pending = session.pending_transition
    operation = session.output_operation_admission_binding
    child = session.output_child_binding
    publication = session.publication_binding
    if (
        not isinstance(pending, Mapping)
        or not isinstance(operation, Mapping)
        or operation.get("state") != "ACTIVE"
        or not isinstance(child, Mapping)
        or child.get("claim_state") != "RETIRED"
        or not isinstance(publication, Mapping)
    ):
        raise SessionCapabilityError(
            "runtime_admission_missing_or_invalid"
        )
    try:
        pending_parent_identity = _require_identity(
            pending.get("runtime_admission_parent_identity"),
            "runtime_admission_parent_identity",
        )
        pending_identity = _require_identity(
            pending.get("runtime_admission_identity"),
            "runtime_admission_identity",
        )
        operation_identity = _require_identity(
            operation.get("admission_identity"),
            "output_operation_admission_identity",
        )
        state_root_identity = _require_identity(
            operation.get("state_root_identity"),
            "state_root_identity",
        )
        output_base_identity = _require_identity(
            child.get("output_base_identity"),
            "output_base_identity",
        )
        operation_output_base_identity = _require_identity(
            operation.get("output_base_root_identity"),
            "output_base_root_identity",
        )
        child_identity = _require_identity(
            child.get("output_child_identity"),
            "output_child_identity",
        )
        _require_sha256(
            runtime_admission.package_root_sha256,
            "package_root_sha256",
        )
    except SessionValidationError as error:
        raise SessionCapabilityError(
            "runtime_admission_missing_or_invalid"
        ) from error
    expected_retention_path = (
        invocation.runtime_root
        / ".hsconfig"
        / "attempt-retention"
        / f"{invocation.apply_attempt_id}.json"
    )
    if not all(
        (
            runtime_admission.admission_path
            == Path(str(pending.get("runtime_admission_path"))),
            runtime_admission.admission_parent_identity
            == pending_parent_identity,
            runtime_admission.admission_identity == pending_identity,
            runtime_admission.admission_sha256
            == pending.get("runtime_admission_sha256")
            == pending.get("runtime_admission_document_sha256"),
            runtime_admission.run_id == session.run_id == invocation.run_id,
            runtime_admission.apply_attempt_id
            == pending.get("apply_attempt_id")
            == invocation.apply_attempt_id,
            runtime_admission.retention_owner_run_id == session.run_id,
            runtime_admission.session_root == session_lease.session_root,
            runtime_admission.session_root_identity
            == session_lease.session_root_identity,
            operation.get("session_root") == str(session_lease.session_root),
            operation.get("session_root_identity")
            == session_lease.session_root_identity,
            runtime_admission.operator_profile_sha256
            == operation.get("operator_profile_sha256")
            == invocation.operator_profile_sha256,
            runtime_admission.state_root_identity
            == state_root_identity
            == pending_parent_identity,
            runtime_admission.runtime_root == invocation.runtime_root,
            runtime_admission.runtime_root_identity
            == invocation.runtime_root_identity,
            runtime_admission.output_base_root
            == Path(str(child.get("output_base_path")))
            == Path(str(operation.get("output_base_root"))),
            runtime_admission.output_base_root_identity
            == output_base_identity
            == operation_output_base_identity,
            runtime_admission.output_root
            == Path(str(child.get("output_child_path")))
            == Path(str(operation.get("output_child_path")))
            == invocation.output_child_path,
            runtime_admission.output_root_identity
            == child_identity
            == invocation.output_child_identity,
            runtime_admission.output_operation_admission_path
            == Path(str(operation.get("admission_path")))
            == invocation.output_operation_admission_path,
            runtime_admission.output_operation_admission_identity
            == operation_identity
            == invocation.output_operation_admission_identity,
            runtime_admission.output_operation_admission_sha256
            == operation.get("admission_sha256")
            == invocation.output_operation_admission_sha256,
            runtime_admission.output_child_binding_sha256
            == child.get("content_sha256")
            == invocation.output_child_binding_sha256,
            runtime_admission.publication_revision
            == publication.get("revision")
            == invocation.publication_revision,
            runtime_admission.publication_content_root_sha256
            == publication.get("content_root_sha256")
            == invocation.publication_content_root_sha256,
            runtime_admission.pre_apply_runtime_snapshot_sha256
            == invocation.pre_apply_runtime_snapshot.content_sha256,
            runtime_admission.apply_invocation_sha256
            == invocation.content_sha256,
            runtime_admission.retention_fence_path
            == expected_retention_path,
        )
    ):
        raise SessionCapabilityError(
            "runtime_admission_missing_or_invalid"
        )


def prepare_first_runtime_install_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_apply_started_session: LiveStartSession,
    runtime_observation_receipt: RuntimeObservationReceipt,
) -> LiveStartSession:
    return _prepare_apply_recovery_from_observation_under_lock(
        session_lease=session_lease,
        expected_session=expected_apply_started_session,
        runtime_observation_receipt=runtime_observation_receipt,
        observation_family="first_install",
    )


def prepare_nonterminal_apply_recovery_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_nonterminal_session: LiveStartSession,
    runtime_observation_receipt: RuntimeObservationReceipt,
) -> LiveStartSession:
    return _prepare_apply_recovery_from_observation_under_lock(
        session_lease=session_lease,
        expected_session=expected_nonterminal_session,
        runtime_observation_receipt=runtime_observation_receipt,
        observation_family="nonterminal_apply",
    )


def _prepare_apply_recovery_from_observation_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    runtime_observation_receipt: RuntimeObservationReceipt,
    observation_family: str,
) -> LiveStartSession:
    if expected_session.phase not in {
        LiveStartPhase.APPLY_STARTED,
        LiveStartPhase.APPLY_COMMITTED,
    } or expected_session.apply_recovery is not None:
        raise SessionConflictError("live_start_apply_recovery_prepare_invalid")
    postcondition = _consume_runtime_observation_receipt_under_lock(
        receipt=runtime_observation_receipt,
        session_lease=session_lease,
        expected_session=expected_session,
        observation_family=observation_family,  # type: ignore[arg-type]
        apply_attempt_id=_session_apply_attempt_id(expected_session),
    )
    recovery = postcondition.evidence.get("apply_recovery")
    if not isinstance(recovery, Mapping):
        raise SessionCapabilityError("live_start_runtime_observation_recovery_missing")
    validated = _validate_apply_recovery_document(recovery)
    if validated.get("recovery_stage") != "ACTIVE":
        raise SessionCapabilityError("live_start_initial_recovery_not_active")
    return _transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=expected_session,
        event="same_phase_cas",
        changes={"apply_recovery": validated},
    )


def advance_nonterminal_apply_recovery_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_recovery_session: LiveStartSession,
    transition: str,
    recovery_evidence: RuntimeApplyRecoveryEvidence | None,
    recovery_authorization: RuntimeAttemptRecoveryAuthorization | None,
    physical_step_receipt: ApplyRecoveryStepReceipt | None,
    runtime_observation_receipt: RuntimeObservationReceipt | None,
) -> LiveStartSession:
    if transition == "physical_recovery_advanced":
        if physical_step_receipt is None or any(
            item is not None
            for item in (
                recovery_evidence,
                recovery_authorization,
                runtime_observation_receipt,
            )
        ):
            raise SessionCapabilityError("live_start_apply_recovery_carrier_matrix_invalid")
        action = physical_step_receipt._opaque.action
        postcondition = _consume_receipt_under_lock(
            receipt=physical_step_receipt,
            receipt_type=ApplyRecoveryStepReceipt,
            session_lease=session_lease,
            expected_session=expected_recovery_session,
            family="nonterminal_apply_recovery",
            action=action,
        )
        successor = postcondition.evidence.get("apply_recovery")
        if not isinstance(successor, Mapping):
            raise SessionCapabilityError("live_start_apply_recovery_successor_missing")
        validated = _validate_apply_recovery_document(successor)
        current = expected_recovery_session.apply_recovery
        if not isinstance(current, Mapping):
            raise SessionConflictError(
                "live_start_apply_recovery_cursor_missing"
            )
        _validate_owner_physical_postcondition(
            predecessor=current,
            action=action,
            evidence=postcondition.evidence,
            runtime_layout=(
                expected_recovery_session.runtime_layout_bootstrap
            ),
        )
        _validate_apply_recovery_physical_successor(
            predecessor=current,
            successor=validated,
            action=action,
        )
    elif transition == "select_terminal_classification":
        if runtime_observation_receipt is None or any(
            item is not None
            for item in (
                recovery_evidence,
                recovery_authorization,
                physical_step_receipt,
            )
        ):
            raise SessionCapabilityError("live_start_classification_carrier_matrix_invalid")
        postcondition = _consume_runtime_observation_receipt_under_lock(
            receipt=runtime_observation_receipt,
            session_lease=session_lease,
            expected_session=expected_recovery_session,
            observation_family="terminal_classification",
            apply_attempt_id=_session_apply_attempt_id(
                expected_recovery_session
            ),
        )
        successor = postcondition.evidence.get("apply_recovery")
        if not isinstance(successor, Mapping):
            raise SessionCapabilityError("live_start_classification_successor_missing")
        validated = _validate_apply_recovery_document(successor)
        current = expected_recovery_session.apply_recovery
        if not isinstance(current, Mapping):
            raise SessionConflictError(
                "live_start_apply_recovery_cursor_missing"
            )
        _validate_apply_recovery_classification_successor(
            predecessor=current,
            successor=validated,
        )
    else:
        if transition not in {"apply_committed", "runtime_matched", "recovery_closed"}:
            raise SessionValidationError("live_start_apply_recovery_advance_invalid")
        if (
            recovery_evidence is None
            or recovery_authorization is None
            or physical_step_receipt is not None
            or runtime_observation_receipt is not None
        ):
            raise SessionCapabilityError("live_start_apply_recovery_pure_carrier_invalid")
        _require_opaque_carrier(
            recovery_authorization,
            carrier_type=RuntimeAttemptRecoveryAuthorization,
            family="nonterminal_apply_recovery",
            action=transition,
            consume=True,
        )
        validated = _validate_apply_recovery_document(recovery_evidence.value)
        current = expected_recovery_session.apply_recovery
        if not isinstance(current, Mapping):
            raise SessionConflictError("live_start_apply_recovery_cursor_missing")
        if transition == "recovery_closed":
            _validate_apply_recovery_closure_successor(
                predecessor=current,
                successor=validated,
            )
        else:
            _validate_apply_recovery_pure_phase_successor(
                predecessor=current,
                successor=validated,
                transition=transition,
            )
    changes: dict[str, Any] = {"apply_recovery": validated}
    event = "same_phase_cas"
    if transition == "apply_committed":
        if expected_recovery_session.phase is not LiveStartPhase.APPLY_STARTED:
            raise SessionConflictError("live_start_apply_committed_phase_invalid")
        event = "apply_committed"
    elif transition == "runtime_matched":
        if expected_recovery_session.phase is not LiveStartPhase.APPLY_COMMITTED:
            raise SessionConflictError("live_start_runtime_matched_phase_invalid")
        event = "runtime_matched"
    return _transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=expected_recovery_session,
        event=event,
        changes=changes,
    )


def bind_result_intent_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    result_intent: Mapping[str, Any],
    attempt_acknowledgement: Mapping[str, Any] | None = None,
) -> LiveStartSession:
    recovery = expected_session.apply_recovery
    if (
        expected_session.pending_transition is not None
        or not isinstance(recovery, Mapping)
        or recovery.get("recovery_stage") != "CLOSED"
        or expected_session.result_intent is not None
    ):
        raise SessionConflictError("live_start_result_intent_cursor_invalid")
    validated_intent = validate_embedded_document("result_intent", result_intent)
    status = validated_intent["terminal_status"]
    if status in {"LIVE_AND_MATCHED", "ALREADY_LIVE"}:
        if attempt_acknowledgement is None:
            raise SessionValidationError("live_start_success_acknowledgement_missing")
        validated_ack = validate_embedded_document(
            "attempt_acknowledgement",
            attempt_acknowledgement,
        )
    elif attempt_acknowledgement is not None:
        raise SessionValidationError("live_start_failure_acknowledgement_forbidden")
    else:
        validated_ack = None
    _validate_result_intent_recovery_binding(
        session_lease=session_lease,
        session_value=expected_session,
        recovery=recovery,
        intent=validated_intent,
        acknowledgement=validated_ack,
    )
    changes: dict[str, Any] = {
        "apply_recovery": None,
        "closed_apply_recovery_commitment": recovery,
        "result_intent": validated_intent,
    }
    if validated_ack is not None:
        changes["attempt_acknowledgement"] = validated_ack
    published = _transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=expected_session,
        event="same_phase_cas",
        changes=changes,
    )
    persisted = load_live_start_session_under_lock(
        session_lease=session_lease
    )
    if (
        persisted.canonical_json != published.canonical_json
        or persisted.content_sha256 != published.content_sha256
    ):
        raise SessionConflictError(
            "live_start_result_intent_persistence_mismatch"
        )
    return persisted


def _live_start_result_payloads(
    result_intent: Mapping[str, Any],
) -> tuple[bytes, bytes]:
    intent = validate_embedded_document("result_intent", result_intent)
    summary = FrozenJsonDocument.from_value(
        {
            "schema_version": 1,
            "summary_kind": LIVE_START_RESULT_SUMMARY_KIND,
            "run_id": intent["run_id"],
            "status": intent["terminal_status"],
            "deck_name": intent["deck_name"],
            "candidate_revision": intent["candidate_revision"],
            "unique_main_deck_cards": intent["unique_main_deck_cards"],
            "configured_cards": intent["configured_cards"],
            "deliberately_unconfigured_cards": intent[
                "deliberately_unconfigured_cards"
            ],
            "review_confidence": intent["review_confidence"],
            "visible_limitations": intent["visible_limitations"],
            "raw_apply_status": intent["raw_apply_status"],
            "physical_disposition": intent["physical_disposition"],
            "runtime_match_status": intent["runtime_match_status"],
            "error_code": intent["error_code"],
            "retained_safe_state": intent["retained_safe_state"],
        }
    ).canonical_json
    if len(summary) > LIVE_START_RESULT_SUMMARY_MAX_BYTES:
        raise SessionValidationError("live_start_result_summary_too_large")

    def markdown_text(value: Any) -> str:
        rendered = "unavailable" if value is None else str(value)
        rendered = rendered.replace("\r", " ").replace("\n", " ")
        rendered = rendered.replace("&", "&amp;")
        rendered = rendered.replace("<", "&lt;").replace(">", "&gt;")
        return re.sub(r"([\\`*_{}\[\]()#+\-.!|])", r"\\\1", rendered)

    limitations = tuple(intent["visible_limitations"])
    lines = [
        "# Live start result",
        "",
        f"- Status: {markdown_text(intent['terminal_status'])}",
        f"- Deck: {markdown_text(intent['deck_name'])}",
        f"- Candidate revision: {intent['candidate_revision']}",
        (
            "- Card coverage: "
            f"{markdown_text(intent['configured_cards'])} configured, "
            f"{markdown_text(intent['deliberately_unconfigured_cards'])} "
            "deliberately unconfigured, "
            f"{intent['unique_main_deck_cards']} unique main-deck cards"
        ),
        f"- Review confidence: {markdown_text(intent['review_confidence'])}",
        f"- Apply status: {markdown_text(intent['raw_apply_status'])}",
        (
            "- Physical disposition: "
            f"{markdown_text(intent['physical_disposition'])}"
        ),
        (
            "- Runtime match: "
            f"{markdown_text(intent['runtime_match_status'])}"
        ),
        f"- Safe state: {markdown_text(intent['retained_safe_state'])}",
    ]
    if intent["error_code"] is not None:
        lines.append(f"- Error: {markdown_text(intent['error_code'])}")
    if limitations:
        lines.extend(("", "## Visible limitations", ""))
        lines.extend(f"- {markdown_text(item)}" for item in limitations)
    markdown = ("\n".join(lines) + "\n").encode("utf-8")
    if len(markdown) > LIVE_START_RESULT_SUMMARY_MAX_BYTES:
        raise SessionValidationError("live_start_result_summary_too_large")
    return summary, markdown


def _require_or_create_result_directory_under_lock(
    *,
    session_lease: LiveStartSessionLease,
) -> tuple[Path, PathIdentity]:
    _require_session_lease(session_lease)
    root = session_lease.session_root
    if path_identity(root) != session_lease.session_root_identity:
        raise SessionConflictError("live_start_result_parent_changed")
    result_root = root / "result"
    try:
        status = result_root.lstat()
    except FileNotFoundError:
        try:
            identity = secure_create_directory(
                result_root,
                expected_parent_identity=session_lease.session_root_identity,
            )
        except FileExistsError:
            status = result_root.lstat()
        else:
            status = result_root.lstat()
            if path_identity_from_status(status) != identity:
                raise SessionConflictError("live_start_result_parent_changed")
    if (
        not stat.S_ISDIR(status.st_mode)
        or status_is_reparse(status)
        or path_identity(root) != session_lease.session_root_identity
    ):
        raise SessionLayoutError("live_start_result_parent_invalid")
    identity = path_identity_from_status(status)
    require_same_identity_resolution(result_root, expected_status=status)
    _validate_path_no_ads(result_root, status=status, directory=True)
    return result_root, identity


def _read_exact_result_file_or_absent(
    *,
    path: Path,
    payload: bytes,
    parent_identity: PathIdentity,
) -> bool:
    try:
        raw, _identity = _read_bound_file(
            path,
            expected_parent_identity=parent_identity,
            maximum_size=LIVE_START_RESULT_SUMMARY_MAX_BYTES,
        )
    except FileNotFoundError:
        return False
    if raw != payload:
        raise SessionConflictError("live_start_result_final_bytes_changed")
    return True


def _retire_reserved_result_temp(
    *,
    path: Path,
    parent_identity: PathIdentity,
) -> None:
    try:
        status = path.lstat()
    except FileNotFoundError:
        return
    identity = path_identity_from_status(status)
    if (
        not stat.S_ISREG(status.st_mode)
        or status_is_reparse(status)
        or status.st_nlink != 1
        or status.st_size > LIVE_START_RESULT_SUMMARY_MAX_BYTES
        or path_identity(path.parent) != parent_identity
    ):
        raise SessionLayoutError("live_start_result_reserved_temp_invalid")
    _validate_path_no_ads(path, status=status, directory=False)
    secure_unlink(
        path,
        expected_identity=identity,
        expected_parent_identity=parent_identity,
        missing_ok=False,
    )
    if os.path.lexists(path) or path_identity(path.parent) != parent_identity:
        raise SessionConflictError("live_start_result_reserved_temp_changed")


def _materialize_exact_result_file(
    *,
    path: Path,
    payload: bytes,
    parent_identity: PathIdentity,
) -> None:
    if _read_exact_result_file_or_absent(
        path=path,
        payload=payload,
        parent_identity=parent_identity,
    ):
        return
    published = atomic_write_reserved_bytes(
        path=path,
        payload=payload,
        expected_parent_identity=parent_identity,
        expected_predecessor_identity=None,
        expected_predecessor_sha256=None,
        maximum_size=LIVE_START_RESULT_SUMMARY_MAX_BYTES,
    )
    if published.sha256 != _bytes_sha256(payload):
        raise SessionConflictError("live_start_result_persistence_mismatch")


def complete_live_start_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_result_session: LiveStartSession,
) -> LiveStartSession:
    """Persist one intent-derived result pair and terminalize in one CAS."""

    _require_session_lease(session_lease)
    persisted = load_live_start_session_under_lock(session_lease=session_lease)
    if (
        persisted != expected_result_session
        or persisted.canonical_json != expected_result_session.canonical_json
        or persisted.content_sha256 != expected_result_session.content_sha256
        or persisted.session_identity != expected_result_session.session_identity
        or persisted.terminal_status is not None
        or not isinstance(persisted.result_intent, Mapping)
        or persisted.apply_recovery is not None
        or persisted.pending_transition is not None
        or any(
            logical_path in persisted.artifact_bindings
            for logical_path in ("result/summary.json", "result/summary.md")
        )
    ):
        raise SessionConflictError("live_start_result_completion_cursor_invalid")
    summary_json, summary_markdown = _live_start_result_payloads(
        persisted.result_intent
    )
    result_root, result_parent_identity = (
        _require_or_create_result_directory_under_lock(
            session_lease=session_lease
        )
    )
    json_path = result_root / "summary.json"
    markdown_path = result_root / "summary.md"
    json_temp = result_root / ".summary.json.live-start-atomic.tmp"
    markdown_temp = result_root / ".summary.md.live-start-atomic.tmp"
    json_present = _read_exact_result_file_or_absent(
        path=json_path,
        payload=summary_json,
        parent_identity=result_parent_identity,
    )
    markdown_present = _read_exact_result_file_or_absent(
        path=markdown_path,
        payload=summary_markdown,
        parent_identity=result_parent_identity,
    )
    json_temp_present = os.path.lexists(json_temp)
    markdown_temp_present = os.path.lexists(markdown_temp)
    if (
        json_temp_present
        and json_present
        or markdown_temp_present
        and (not json_present or markdown_present)
        or markdown_present
        and not json_present
    ):
        raise SessionConflictError("live_start_result_physical_state_invalid")
    if json_temp_present:
        _retire_reserved_result_temp(
            path=json_temp,
            parent_identity=result_parent_identity,
        )
    _materialize_exact_result_file(
        path=json_path,
        payload=summary_json,
        parent_identity=result_parent_identity,
    )
    if markdown_temp_present:
        _retire_reserved_result_temp(
            path=markdown_temp,
            parent_identity=result_parent_identity,
        )
    _materialize_exact_result_file(
        path=markdown_path,
        payload=summary_markdown,
        parent_identity=result_parent_identity,
    )
    for path, payload in (
        (json_path, summary_json),
        (markdown_path, summary_markdown),
    ):
        if not _read_exact_result_file_or_absent(
            path=path,
            payload=payload,
            parent_identity=result_parent_identity,
        ):
            raise SessionConflictError("live_start_result_persistence_mismatch")
    if (
        os.path.lexists(json_temp)
        or os.path.lexists(markdown_temp)
        or path_identity(result_root) != result_parent_identity
    ):
        raise SessionConflictError("live_start_result_persistence_mismatch")
    current = load_live_start_session_under_lock(session_lease=session_lease)
    if (
        current != persisted
        or current.canonical_json != persisted.canonical_json
        or current.content_sha256 != persisted.content_sha256
        or current.session_identity != persisted.session_identity
    ):
        raise SessionConflictError("live_start_result_completion_cursor_changed")
    artifact_bindings = dict(persisted.artifact_bindings)
    artifact_bindings.update(
        {
            "result/summary.json": _bytes_sha256(summary_json),
            "result/summary.md": _bytes_sha256(summary_markdown),
        }
    )
    terminal = _transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=persisted,
        event="bind_terminal",
        changes={
            "artifact_bindings": artifact_bindings,
            "terminal_status": persisted.result_intent["terminal_status"],
        },
    )
    return terminal


def record_terminal_status_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_result_session: LiveStartSession,
) -> LiveStartSession:
    """Compatibility entry point for the single intent-derived completion CAS."""

    return complete_live_start_under_lock(
        session_lease=session_lease,
        expected_result_session=expected_result_session,
    )


def prepare_terminal_retirement_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_terminal_session: LiveStartSession,
    operation: Literal[
        "ack_success",
        "release_not_committed",
        "release_committed_mismatch",
        "release_resolved_terminal",
    ],
    runtime_observation_receipt: RuntimeObservationReceipt | None,
) -> LiveStartSession:
    if (
        expected_terminal_session.terminal_status is None
        or expected_terminal_session.result_intent is None
        or expected_terminal_session.terminal_retirement is not None
        or expected_terminal_session.pending_transition is not None
        or expected_terminal_session.apply_recovery is not None
    ):
        raise SessionConflictError("live_start_terminal_retirement_prepare_invalid")
    if operation not in TERMINAL_RETIREMENT_STAGES:
        raise SessionValidationError("live_start_terminal_retirement_operation_invalid")
    intent = expected_terminal_session.result_intent
    closed_recovery = (
        expected_terminal_session.closed_apply_recovery_commitment
    )
    if intent.get("apply_attempt_id") is not None and not isinstance(
        closed_recovery,
        Mapping,
    ):
        raise SessionConflictError(
            "live_start_closed_recovery_commitment_missing"
        )
    if not _terminal_operation_matches_authority(
        operation=operation,
        terminal_status=expected_terminal_session.terminal_status,
        result_intent=intent,
        attempt_acknowledgement=(
            expected_terminal_session.attempt_acknowledgement
        ),
        has_resolution=(runtime_observation_receipt is not None),
    ):
        raise SessionConflictError(
            "live_start_terminal_retirement_operation_binding_invalid"
        )
    resolved_evidence: Mapping[str, Any] | None = None
    if operation == "release_resolved_terminal":
        if runtime_observation_receipt is None:
            raise SessionCapabilityError("live_start_terminal_resolution_observation_missing")
        postcondition = _consume_runtime_observation_receipt_under_lock(
            receipt=runtime_observation_receipt,
            session_lease=session_lease,
            expected_session=expected_terminal_session,
            observation_family="terminal_resolution",
            apply_attempt_id=_session_apply_attempt_id(
                expected_terminal_session
            ),
        )
        resolved = postcondition.evidence.get(
            "terminal_resolution_evidence"
        )
        if not isinstance(resolved, Mapping):
            raise SessionCapabilityError("live_start_terminal_resolution_evidence_missing")
        if isinstance(closed_recovery, Mapping):
            if resolved.get("action_index") != closed_recovery.get(
                "action_index"
            ):
                raise SessionCapabilityError(
                    "live_start_terminal_resolution_action_index_changed"
                )
            source_owner = closed_recovery.get("owner_retirement")
            if isinstance(source_owner, Mapping) and (
                resolved.get("owner_retirement") != source_owner
                or resolved.get("external_file_action")
                != closed_recovery.get("external_file_action")
                or resolved.get("cleanup_stage") is not None
            ):
                raise SessionCapabilityError(
                    "live_start_terminal_owner_handoff_invalid"
                )
        resolved_evidence = _freeze_mapping(resolved)
        stage = "RECOVERY_PREPARED"
    else:
        if runtime_observation_receipt is not None:
            raise SessionCapabilityError("live_start_terminal_observation_forbidden")
        if isinstance(closed_recovery, Mapping):
            source_owner = closed_recovery.get("owner_retirement")
            if isinstance(source_owner, Mapping) and (
                closed_recovery.get("stable_physical_disposition")
                != "COMMITTED"
                or source_owner.get("stage") != "OWNER_RETIRED"
            ):
                raise SessionConflictError(
                    "live_start_terminal_owner_resolution_required"
                )
        stage = "PREPARED"
    value = {
        "schema_version": LIVE_START_TERMINAL_RETIREMENT_SCHEMA_VERSION,
        "retirement_kind": LIVE_START_TERMINAL_RETIREMENT_KIND,
        "run_id": expected_terminal_session.run_id,
        "apply_attempt_id": intent.get("apply_attempt_id"),
        "operation": operation,
        "stage": stage,
        "source_terminal_session_sha256": expected_terminal_session.content_sha256,
        "result_intent_sha256": intent.get("content_sha256"),
        "terminal_resolution_evidence": resolved_evidence,
        "runtime_admission_path": intent.get("runtime_admission_path"),
        "runtime_admission_parent_identity": intent.get(
            "runtime_admission_parent_identity"
        ),
        "runtime_admission_identity": intent.get("runtime_admission_identity"),
        "runtime_admission_sha256": intent.get("runtime_admission_sha256"),
        "retained_attempt_record_path": intent.get(
            "retained_attempt_record_path"
        ),
        "retained_attempt_record_identity": intent.get(
            "retained_attempt_record_identity"
        ),
        "retained_attempt_record_sha256": intent.get(
            "retained_attempt_record_sha256"
        ),
        "retained_journal_path": intent.get("retained_journal_path"),
        "retained_journal_identity": intent.get("retained_journal_identity"),
        "retained_journal_sha256": intent.get("retained_journal_sha256"),
        "retained_target_owner_journal_path": intent.get(
            "retained_target_owner_journal_path"
        ),
        "retained_target_owner_journal_identity": intent.get(
            "retained_target_owner_journal_identity"
        ),
        "retained_target_owner_journal_sha256": intent.get(
            "retained_target_owner_journal_sha256"
        ),
        "retained_candidate_identity": intent.get(
            "retained_candidate_identity"
        ),
    }
    retirement = seal_embedded_document("terminal_retirement", value)
    return _transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=expected_terminal_session,
        event="same_phase_cas",
        changes={
            "closed_apply_recovery_commitment": None,
            "terminal_retirement": retirement,
        },
    )


def advance_terminal_retirement_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_retirement_session: LiveStartSession,
    transition: str,
    terminal_authorization: TerminalRetirementAuthorization | None,
    physical_step_receipt: TerminalResolutionStepReceipt | None,
) -> LiveStartSession:
    if transition not in {
        "ack_journal_retired",
        "evidence_retired",
        "admission_release_authorized",
    }:
        raise SessionValidationError("live_start_terminal_retirement_advance_invalid")
    current = expected_retirement_session.terminal_retirement
    if not isinstance(current, Mapping):
        raise SessionConflictError("live_start_terminal_retirement_cursor_missing")
    if physical_step_receipt is not None:
        if terminal_authorization is not None:
            raise SessionCapabilityError("live_start_terminal_retirement_carrier_matrix_invalid")
        if not isinstance(
            physical_step_receipt,
            TerminalResolutionStepReceipt,
        ) or not hasattr(physical_step_receipt, "_opaque"):
            raise SessionCapabilityError(
                "live_start_terminal_retirement_receipt_forged"
            )
        action = physical_step_receipt._opaque.action
        expected_physical_action = {
            "ack_journal_retired": "retire_ack_journal",
            "evidence_retired": "retire_ack_fence",
        }.get(transition)
        if (
            current.get("operation") != "ack_success"
            or action != expected_physical_action
        ):
            raise SessionCapabilityError(
                "live_start_terminal_retirement_receipt_action_mismatch"
            )
        postcondition = _consume_receipt_under_lock(
            receipt=physical_step_receipt,
            receipt_type=TerminalResolutionStepReceipt,
            session_lease=session_lease,
            expected_session=expected_retirement_session,
            family="terminal_retirement",
            action=action,
        )
        successor = postcondition.evidence.get("terminal_retirement")
        if not isinstance(successor, Mapping):
            raise SessionCapabilityError("live_start_terminal_retirement_successor_missing")
        validated = validate_embedded_document("terminal_retirement", successor)
        expected_stage = {
            "ack_journal_retired": "ACK_JOURNAL_RETIRED",
            "evidence_retired": "EVIDENCE_RETIRED",
            "admission_release_authorized": "ADMISSION_RELEASE_AUTHORIZED",
        }[transition]
        if validated.get("stage") != expected_stage:
            raise SessionCapabilityError(
                "live_start_terminal_retirement_receipt_transition_mismatch"
            )
        _validate_terminal_retirement_successor(
            predecessor=current,
            successor=validated,
            transition=transition,
        )
    else:
        if terminal_authorization is None:
            raise SessionCapabilityError("live_start_terminal_retirement_authorization_missing")
        expected_action = {
            "evidence_retired": "evidence_retired",
            "admission_release_authorized": "admission_release_authorized",
        }.get(transition)
        if expected_action is None:
            raise SessionCapabilityError("live_start_terminal_retirement_receipt_required")
        _require_opaque_carrier(
            terminal_authorization,
            carrier_type=TerminalRetirementAuthorization,
            family="terminal_retirement",
            action=expected_action,
            consume=True,
        )
        value = _thaw(current)
        value.pop("content_sha256", None)
        value["stage"] = (
            "EVIDENCE_RETIRED"
            if transition == "evidence_retired"
            else "ADMISSION_RELEASE_AUTHORIZED"
        )
        validated = seal_embedded_document("terminal_retirement", value)
        _validate_terminal_retirement_successor(
            predecessor=current,
            successor=validated,
            transition=transition,
        )
    return _transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=expected_retirement_session,
        event="same_phase_cas",
        changes={"terminal_retirement": validated},
    )


def advance_terminal_resolution_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_resolution_session: LiveStartSession,
    transition: str,
    resolved_evidence: TerminalResolutionEvidence | None,
    terminal_authorization: TerminalRetirementAuthorization | None,
    physical_step_receipt: TerminalResolutionStepReceipt | None,
) -> LiveStartSession:
    allowed = {
        "cleanup_inventory_unbound_staging_retired",
        "cleanup_inventory_staging_bound",
        "inventory_bound",
        "cleaning_started",
        "cleanup_cursor_advanced",
        "journal_retired",
        "fence_retired",
        "inventory_retired",
        "physical_recovery_advanced",
        "stabilized",
    }
    if transition not in allowed:
        raise SessionValidationError("live_start_terminal_resolution_advance_invalid")
    current = expected_resolution_session.terminal_retirement
    if not isinstance(current, Mapping) or current.get("operation") != "release_resolved_terminal":
        raise SessionConflictError("live_start_terminal_resolution_cursor_invalid")
    if physical_step_receipt is not None:
        if terminal_authorization is not None or resolved_evidence is not None:
            raise SessionCapabilityError("live_start_terminal_resolution_carrier_matrix_invalid")
        if not isinstance(
            physical_step_receipt,
            TerminalResolutionStepReceipt,
        ) or not hasattr(physical_step_receipt, "_opaque"):
            raise SessionCapabilityError(
                "live_start_terminal_resolution_receipt_forged"
            )
        action = physical_step_receipt._opaque.action
        expected_action = {
            "cleanup_inventory_unbound_staging_retired": (
                "retire_unbound_terminal_cleanup_inventory_staging"
            ),
            "cleanup_inventory_staging_bound": (
                "materialize_terminal_cleanup_inventory_staging"
            ),
            "inventory_bound": "commit_bound_terminal_cleanup_inventory",
            "cleanup_cursor_advanced": "delete_cleanup_entry",
            "journal_retired": "retire_cleanup_journal",
            "fence_retired": "retire_cleanup_fence",
            "inventory_retired": "retire_cleanup_inventory",
        }.get(transition)
        if transition == "physical_recovery_advanced":
            expected_action = _terminal_action_for_retirement(current)
        if action != expected_action:
            raise SessionCapabilityError(
                "live_start_terminal_resolution_receipt_action_mismatch"
            )
        postcondition = _consume_receipt_under_lock(
            receipt=physical_step_receipt,
            receipt_type=TerminalResolutionStepReceipt,
            session_lease=session_lease,
            expected_session=expected_resolution_session,
            family="terminal_retirement",
            action=action,
        )
        successor = postcondition.evidence.get("terminal_retirement")
        if not isinstance(successor, Mapping):
            raise SessionCapabilityError("live_start_terminal_resolution_successor_missing")
        if transition in {
            "cleanup_inventory_unbound_staging_retired",
            "cleanup_inventory_staging_bound",
        }:
            current_resolution = current.get(
                "terminal_resolution_evidence"
            )
            successor_resolution = successor.get(
                "terminal_resolution_evidence"
            )
            _validate_terminal_external_action_successor(
                predecessor=(
                    current_resolution.get("external_file_action")
                    if isinstance(current_resolution, Mapping)
                    else None
                ),
                successor=(
                    successor_resolution.get("external_file_action")
                    if isinstance(successor_resolution, Mapping)
                    else None
                ),
                transition=(
                    "unbound_retired"
                    if transition
                    == "cleanup_inventory_unbound_staging_retired"
                    else "staging_bound"
                ),
            )
        validated = validate_embedded_document("terminal_retirement", successor)
        expected_outer_stage = {
            "cleanup_inventory_unbound_staging_retired": "RECOVERY_PREPARED",
            "cleanup_inventory_staging_bound": "RECOVERY_PREPARED",
            "inventory_bound": "RECOVERY_INVENTORY_BOUND",
            "cleanup_cursor_advanced": "RECOVERY_CLEANING",
            "journal_retired": "RECOVERY_JOURNAL_RETIRED",
            "fence_retired": "RECOVERY_FENCE_RETIRED",
            "inventory_retired": "RECOVERY_INVENTORY_RETIRED",
            "physical_recovery_advanced": "RECOVERY_PREPARED",
        }.get(transition)
        if (
            expected_outer_stage is None
            or validated.get("stage") != expected_outer_stage
        ):
            raise SessionCapabilityError(
                "live_start_terminal_resolution_receipt_transition_mismatch"
            )
        owner_action = _validate_terminal_resolution_successor(
            predecessor=current,
            successor=validated,
            transition=transition,
            authorized_owner_action=(
                postcondition.evidence.get("_terminal_owner_action")
                if transition == "physical_recovery_advanced"
                else None
            ),
            ownerless_issuer_context=(
                postcondition.evidence.get(
                    "_terminal_ownerless_issuer_context"
                )
                if transition == "physical_recovery_advanced"
                else None
            ),
        )
        if transition == "physical_recovery_advanced":
            current_resolution = current.get(
                "terminal_resolution_evidence"
            )
            if not isinstance(current_resolution, Mapping):
                raise SessionCapabilityError(
                    "live_start_terminal_resolution_evidence_missing"
                )
            if owner_action is not None:
                _validate_owner_physical_postcondition(
                    predecessor=current_resolution,
                    action=owner_action,
                    evidence=postcondition.evidence,
                    runtime_layout=(
                        expected_resolution_session.runtime_layout_bootstrap
                    ),
                )
    else:
        if (
            transition not in {"cleaning_started", "stabilized"}
            or terminal_authorization is None
            or resolved_evidence is None
        ):
            raise SessionCapabilityError("live_start_terminal_resolution_pure_carrier_invalid")
        action = transition
        _require_opaque_carrier(
            terminal_authorization,
            carrier_type=TerminalRetirementAuthorization,
            family="terminal_retirement",
            action=action,
            consume=True,
        )
        value = _thaw(current)
        value.pop("content_sha256", None)
        value["terminal_resolution_evidence"] = _thaw(resolved_evidence.value)
        value["stage"] = (
            "RECOVERY_CLEANING"
            if transition == "cleaning_started"
            else "RECOVERY_STABILIZED"
        )
        validated = seal_embedded_document("terminal_retirement", value)
        _validate_terminal_resolution_successor(
            predecessor=current,
            successor=validated,
            transition=transition,
        )
    return _transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=expected_resolution_session,
        event="same_phase_cas",
        changes={"terminal_retirement": validated},
    )


def publish_terminal_cleanup_inventory_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_recovery_prepared_session: LiveStartSession,
    terminal_authorization: TerminalRetirementAuthorization,
    inventory: TerminalResolutionCleanupInventory,
    action: Literal["materialize", "commit"],
) -> TerminalCleanupInventoryPublishStep:
    """Perform one bound cleanup-inventory publish row and return its receipt."""

    if action not in {"materialize", "commit"}:
        raise SessionValidationError(
            "live_start_terminal_cleanup_publish_action_invalid"
        )
    if not isinstance(inventory, TerminalResolutionCleanupInventory):
        raise TypeError("live_start_terminal_cleanup_inventory_invalid")
    retirement, resolution, external = _terminal_cleanup_publish_cursor(
        expected_recovery_prepared_session=expected_recovery_prepared_session,
        inventory=inventory,
        action=action,
    )
    physical_action_name = (
        "materialize_terminal_cleanup_inventory_staging"
        if action == "materialize"
        else "commit_bound_terminal_cleanup_inventory"
    )
    _require_terminal_physical_authorization_context(
        session_lease=session_lease,
        expected_session=expected_recovery_prepared_session,
        terminal_authorization=terminal_authorization,
        action=physical_action_name,
    )
    result: MaterializedStagingBytes | PublishedNoReplaceBytes | None = None

    def perform() -> TerminalResolutionPhysicalPostcondition:
        nonlocal result
        final_path = Path(external["final_path"])
        staging_path = Path(external["staging_path"])
        parent_identity = _require_identity(
            external["parent_identity"], "cleanup_inventory_parent_identity"
        )
        successor_resolution = _thaw(resolution)
        successor_retirement = _thaw(retirement)
        successor_retirement.pop("content_sha256", None)
        if action == "materialize":
            if os.path.lexists(final_path):
                raise SessionConflictError(
                    "live_start_terminal_cleanup_final_created_from_planned"
                )
            materialized = atomic_materialize_staging_bytes(
                staging_path=staging_path,
                inner_temp_path=Path(external["inner_temp_path"]),
                payload=inventory.canonical_json,
                expected_parent_identity=parent_identity,
                maximum_size=LIVE_START_TERMINAL_CLEANUP_INVENTORY_MAX_BYTES,
            )
            result = materialized
            successor_external = _thaw(external)
            successor_external.pop("content_sha256", None)
            successor_external.update(
                {
                    "stage": "STAGING_BOUND",
                    "staging_identity": list(materialized.identity),
                    "staging_size": materialized.size,
                    "staging_sha256": materialized.sha256,
                }
            )
            successor_resolution["external_file_action"] = _thaw(
                seal_embedded_document(
                    "external_file_action", successor_external
                )
            )
        else:
            staging_identity = _require_identity(
                external["staging_identity"],
                "cleanup_inventory_staging_identity",
            )
            published = atomic_commit_bound_staging_no_replace(
                path=final_path,
                staging_path=staging_path,
                expected_staging_identity=staging_identity,
                expected_size=inventory.size,
                expected_sha256=inventory.sha256,
                expected_parent_identity=parent_identity,
            )
            result = published
            successor_resolution.update(
                {
                    "external_file_action": None,
                    "cleanup_stage": "INVENTORY_BOUND",
                    "cleanup_inventory_identity": list(published.identity),
                    "cleanup_inventory_size": published.size,
                    "cleanup_inventory_sha256": published.sha256,
                }
            )
            successor_retirement["stage"] = "RECOVERY_INVENTORY_BOUND"
        successor_resolution.pop("content_sha256", None)
        validated_resolution = TerminalResolutionEvidence(
            _seal_terminal_resolution(successor_resolution)
        )
        successor_retirement["terminal_resolution_evidence"] = _thaw(
            validated_resolution.value
        )
        validated_retirement = seal_embedded_document(
            "terminal_retirement", successor_retirement
        )
        return TerminalResolutionPhysicalPostcondition(
            action=physical_action_name,
            evidence={"terminal_retirement": validated_retirement},
        )

    try:
        receipt = _execute_terminal_resolution_physical_step(
            terminal_authorization=terminal_authorization,
            action=physical_action_name,
            physical_action=perform,
        )
    except AtomicWriteConflictError as error:
        raise SessionConflictError(
            "live_start_terminal_cleanup_physical_conflict"
        ) from error
    if action == "materialize":
        if not isinstance(result, MaterializedStagingBytes):
            raise SessionCapabilityError(
                "live_start_terminal_cleanup_materialize_result_invalid"
            )
        return TerminalCleanupInventoryPublishStep(
            action="materialize",
            staging=result,
            published=None,
            step_receipt=receipt,
        )
    if not isinstance(result, PublishedNoReplaceBytes):
        raise SessionCapabilityError(
            "live_start_terminal_cleanup_commit_result_invalid"
        )
    return TerminalCleanupInventoryPublishStep(
        action="commit",
        staging=None,
        published=result,
        step_receipt=receipt,
    )


def retire_terminal_cleanup_inventory_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_resolution_session: LiveStartSession,
    terminal_authorization: TerminalRetirementAuthorization,
    action: Literal["unbound_staging", "final_sidecar"],
) -> TerminalCleanupInventoryRetireStep:
    """Retire exactly one permitted cleanup-inventory name without adoption."""

    if action not in {"unbound_staging", "final_sidecar"}:
        raise SessionValidationError(
            "live_start_terminal_cleanup_retire_action_invalid"
        )
    retirement = expected_resolution_session.terminal_retirement
    if (
        not isinstance(retirement, Mapping)
        or retirement.get("operation") != "release_resolved_terminal"
    ):
        raise SessionConflictError(
            "live_start_terminal_cleanup_retire_cursor_invalid"
        )
    resolution_value = retirement.get("terminal_resolution_evidence")
    if not isinstance(resolution_value, Mapping):
        raise SessionConflictError(
            "live_start_terminal_cleanup_resolution_missing"
        )
    resolution = _validate_terminal_resolution_document(resolution_value)
    if action == "unbound_staging":
        if (
            retirement.get("stage") != "RECOVERY_PREPARED"
            or resolution.get("cleanup_stage") != "PREPARED"
        ):
            raise SessionConflictError(
                "live_start_terminal_cleanup_unbound_stage_invalid"
            )
        external = resolution.get("external_file_action")
        if not isinstance(external, Mapping):
            raise SessionConflictError(
                "live_start_terminal_cleanup_external_action_missing"
            )
        external = validate_embedded_document("external_file_action", external)
        if (
            external.get("stage") != "PLANNED"
            or external.get("action_kind")
            != "commit_bound_terminal_cleanup_inventory"
        ):
            raise SessionConflictError(
                "live_start_terminal_cleanup_unbound_action_invalid"
            )
        path = Path(external["staging_path"])
        inner_temp_path = Path(external["inner_temp_path"])
        parent_identity = _require_identity(
            external["parent_identity"], "cleanup_inventory_parent_identity"
        )
        expected_identity = None
        physical_action_name = (
            "retire_unbound_terminal_cleanup_inventory_staging"
        )
    else:
        if (
            retirement.get("stage") != "RECOVERY_FENCE_RETIRED"
            or resolution.get("cleanup_stage") != "FENCE_RETIRED"
            or resolution.get("external_file_action") is not None
        ):
            raise SessionConflictError(
                "live_start_terminal_cleanup_final_stage_invalid"
            )
        path = Path(resolution["cleanup_inventory_path"])
        parent_identity = _require_identity(
            resolution["cleanup_inventory_parent_identity"],
            "cleanup_inventory_parent_identity",
        )
        expected_identity = _require_identity(
            resolution["cleanup_inventory_identity"],
            "cleanup_inventory_identity",
        )
        physical_action_name = "retire_cleanup_inventory"
    _require_terminal_physical_authorization_context(
        session_lease=session_lease,
        expected_session=expected_resolution_session,
        terminal_authorization=terminal_authorization,
        action=physical_action_name,
    )
    was_absent: bool | None = None

    def perform() -> TerminalResolutionPhysicalPostcondition:
        nonlocal was_absent
        if action == "unbound_staging" and os.path.lexists(
            Path(external["final_path"])
        ):
            raise SessionConflictError(
                "live_start_terminal_cleanup_direct_final_invalid"
            )
        retire_path = path
        if action == "unbound_staging" and os.path.lexists(inner_temp_path):
            retire_path = inner_temp_path
        was_absent = _retire_plain_file_or_confirm_absent(
            path=retire_path,
            expected_parent_identity=parent_identity,
            expected_identity=expected_identity,
        )
        successor_resolution = _thaw(resolution)
        successor_retirement = _thaw(retirement)
        successor_retirement.pop("content_sha256", None)
        if action == "unbound_staging":
            successor_external = _thaw(external)
            successor_external.pop("content_sha256", None)
            successor_external["action_index"] += 1
            successor_resolution["external_file_action"] = _thaw(
                seal_embedded_document(
                    "external_file_action", successor_external
                )
            )
        else:
            successor_resolution["cleanup_stage"] = "INVENTORY_RETIRED"
            successor_retirement["stage"] = "RECOVERY_INVENTORY_RETIRED"
        successor_resolution.pop("content_sha256", None)
        validated_resolution = TerminalResolutionEvidence(
            _seal_terminal_resolution(successor_resolution)
        )
        successor_retirement["terminal_resolution_evidence"] = _thaw(
            validated_resolution.value
        )
        validated_retirement = seal_embedded_document(
            "terminal_retirement", successor_retirement
        )
        return TerminalResolutionPhysicalPostcondition(
            action=physical_action_name,
            evidence={"terminal_retirement": validated_retirement},
        )

    receipt = _execute_terminal_resolution_physical_step(
        terminal_authorization=terminal_authorization,
        action=physical_action_name,
        physical_action=perform,
    )
    if type(was_absent) is not bool:
        raise SessionCapabilityError(
            "live_start_terminal_cleanup_retire_result_invalid"
        )
    return TerminalCleanupInventoryRetireStep(
        action=action,
        object_was_already_absent=was_absent,
        step_receipt=receipt,
    )


def _retire_plain_file_or_confirm_absent(
    *,
    path: Path,
    expected_parent_identity: PathIdentity,
    expected_identity: PathIdentity | None,
) -> bool:
    if path_identity(path.parent) != expected_parent_identity:
        raise SessionConflictError(
            "live_start_terminal_cleanup_parent_changed"
        )
    try:
        status = path.lstat()
    except FileNotFoundError:
        return True
    identity = path_identity_from_status(status)
    if (
        not stat.S_ISREG(status.st_mode)
        or status_is_reparse(status)
        or status.st_nlink != 1
        or (
            expected_identity is not None
            and identity != expected_identity
        )
    ):
        raise SessionConflictError(
            "live_start_terminal_cleanup_retire_identity_invalid"
        )
    if os.name == "nt":
        require_no_alternate_data_streams(
            path,
            expected_identity=identity,
            expected_parent_identity=expected_parent_identity,
            directory=False,
            expected_size=status.st_size,
        )
    secure_unlink(path, expected_identity=identity, missing_ok=False)
    if path_identity(path.parent) != expected_parent_identity:
        raise SessionConflictError(
            "live_start_terminal_cleanup_parent_changed"
        )
    return False


def _terminal_cleanup_publish_cursor(
    *,
    expected_recovery_prepared_session: LiveStartSession,
    inventory: TerminalResolutionCleanupInventory,
    action: Literal["materialize", "commit"],
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    retirement = expected_recovery_prepared_session.terminal_retirement
    if (
        not isinstance(retirement, Mapping)
        or retirement.get("operation") != "release_resolved_terminal"
        or retirement.get("stage") != "RECOVERY_PREPARED"
    ):
        raise SessionConflictError(
            "live_start_terminal_cleanup_publish_cursor_invalid"
        )
    resolution = retirement.get("terminal_resolution_evidence")
    if not isinstance(resolution, Mapping):
        raise SessionConflictError(
            "live_start_terminal_cleanup_resolution_missing"
        )
    resolution = _validate_terminal_resolution_document(resolution)
    if resolution.get("cleanup_stage") != "PREPARED":
        raise SessionConflictError(
            "live_start_terminal_cleanup_publish_stage_invalid"
        )
    external = resolution.get("external_file_action")
    if not isinstance(external, Mapping):
        raise SessionConflictError(
            "live_start_terminal_cleanup_external_action_missing"
        )
    external = validate_embedded_document("external_file_action", external)
    expected_stage = "PLANNED" if action == "materialize" else "STAGING_BOUND"
    if (
        external.get("stage") != expected_stage
        or external.get("action_kind")
        != "commit_bound_terminal_cleanup_inventory"
        or external.get("commit_mode") != "create_no_replace"
        or external.get("predecessor_state") != "absent"
    ):
        raise SessionConflictError(
            "live_start_terminal_cleanup_external_action_invalid"
        )
    if (
        inventory.value.get("run_id") != resolution.get("run_id")
        or inventory.value.get("apply_attempt_id")
        != resolution.get("apply_attempt_id")
        or Path(external["final_path"])
        != Path(resolution["cleanup_inventory_path"])
        or tuple(external["parent_identity"])
        != tuple(resolution["cleanup_inventory_parent_identity"])
        or external.get("planned_successor_size") != inventory.size
        or external.get("planned_successor_sha256") != inventory.sha256
        or resolution.get("cleanup_inventory_size") != inventory.size
        or resolution.get("cleanup_inventory_sha256") != inventory.sha256
        or resolution.get("cleanup_manifest_sha256")
        != inventory.value.get("cleanup_manifest_sha256")
        or resolution.get("cleanup_entry_count")
        != inventory.value.get("cleanup_entry_count")
        or _normalize_json(resolution.get("cleanup_roots"))
        != _normalize_json(inventory.value.get("cleanup_roots"))
    ):
        raise SessionConflictError(
            "live_start_terminal_cleanup_inventory_commitment_mismatch"
        )
    if action == "materialize":
        if any(
            external.get(key) is not None
            for key in (
                "staging_identity",
                "staging_size",
                "staging_sha256",
            )
        ):
            raise SessionConflictError(
                "live_start_terminal_cleanup_planned_staging_invalid"
            )
    else:
        _require_identity(
            external.get("staging_identity"),
            "cleanup_inventory_staging_identity",
        )
        if (
            external.get("staging_size") != inventory.size
            or external.get("staging_sha256") != inventory.sha256
        ):
            raise SessionConflictError(
                "live_start_terminal_cleanup_bound_staging_invalid"
            )
    return retirement, resolution, external


def _require_terminal_physical_authorization_context(
    *,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    terminal_authorization: TerminalRetirementAuthorization,
    action: str,
) -> None:
    session_bearer = _require_session_lease(session_lease)
    if not isinstance(expected_session, LiveStartSession):
        raise TypeError("live_start_expected_session_invalid")
    bearer = _require_opaque_carrier(
        terminal_authorization,
        carrier_type=TerminalRetirementAuthorization,
        family="terminal_retirement",
        action=action,
        consume=False,
    )
    if (
        bearer.session_bearer is not session_bearer
        or bearer.cursor_sha256 != expected_session.content_sha256
    ):
        raise SessionCapabilityError(
            "live_start_terminal_physical_authorization_stale"
        )


def _seal_terminal_resolution(value: Mapping[str, Any]) -> Mapping[str, Any]:
    normalized = _normalize_json(value)
    if not isinstance(normalized, dict):
        raise SessionValidationError(
            "live_start_terminal_resolution_not_object"
        )
    normalized.pop("content_sha256", None)
    return _freeze_mapping(
        {**normalized, "content_sha256": _self_digest(normalized)}
    )
