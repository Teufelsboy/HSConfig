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
from typing import Any, Literal, TypeVar

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
from hsconfig.input_snapshot_manifest import FrozenCompilerInputs
from hsconfig.package_io import (
    MAX_FILESYSTEM_NODES,
    PathIdentity,
    path_identity,
    path_identity_from_status,
    require_no_alternate_data_streams,
    secure_create_directory,
    secure_open_file_descriptor,
    secure_unlink,
    status_is_reparse,
)
from hsconfig.package_request import FrozenJsonDocument


LIVE_START_SESSION_SCHEMA_VERSION = 1
LIVE_START_SESSION_MAX_BYTES = 256 * 1024
LIVE_START_RESULT_INTENT_SCHEMA_VERSION = 1
LIVE_START_RESULT_INTENT_MAX_BYTES = 64 * 1024
LIVE_START_RESULT_INTENT_KIND = "live_start_result_intent"
LIVE_START_ATTEMPT_ACKNOWLEDGEMENT_SCHEMA_VERSION = 1
LIVE_START_ATTEMPT_ACKNOWLEDGEMENT_MAX_BYTES = 32 * 1024
LIVE_START_ATTEMPT_ACKNOWLEDGEMENT_KIND = (
    "live_start_attempt_acknowledgement"
)
LIVE_START_TERMINAL_RETIREMENT_SCHEMA_VERSION = 1
LIVE_START_TERMINAL_RETIREMENT_MAX_BYTES = 64 * 1024
LIVE_START_TERMINAL_RETIREMENT_KIND = "live_start_terminal_retirement"
LIVE_START_TERMINAL_RESOLUTION_EVIDENCE_SCHEMA_VERSION = 1
LIVE_START_TERMINAL_RESOLUTION_EVIDENCE_MAX_BYTES = 64 * 1024
LIVE_START_TERMINAL_RESOLUTION_EVIDENCE_KIND = (
    "live_start_terminal_resolution_evidence"
)
LIVE_START_RUNTIME_APPLY_RECOVERY_EVIDENCE_SCHEMA_VERSION = 1
LIVE_START_RUNTIME_APPLY_RECOVERY_EVIDENCE_MAX_BYTES = 64 * 1024
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
        "package_validated": "install_package_validation",
        "prepublication_passed": "install_prepublication_validation",
        "publication_committed": "cleanup_prepublication",
        "apply_started": "install_apply_invocation",
    }
)

_INTERNAL_TRANSITION_AUTHORITY = object()
_PUBLIC_SENSITIVE_UPDATE_FIELDS = frozenset(
    {
        "prepublication_work_binding",
        "output_operation_admission_binding",
        "output_child_binding",
        "publication_binding",
        "apply_invocation_sha256",
        "runtime_admission_binding",
        "runtime_layout_bootstrap",
        "apply_recovery",
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
        "bind_terminal": frozenset({"terminal_status"}),
        "replacement_draft": frozenset(
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


_AUTHORITY_REGISTRY_LOCK = threading.RLock()
_ACTIVE_SESSION_CONTEXTS: dict[
    int,
    tuple[_SessionBearer, SessionLockToken],
] = {}


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
        _ACTIVE_SESSION_CONTEXTS[id(bearer)] = (bearer, token)


def _session_context_is_registered(
    *,
    bearer: _SessionBearer,
    token: SessionLockToken | None = None,
) -> bool:
    with _AUTHORITY_REGISTRY_LOCK:
        registered = _ACTIVE_SESSION_CONTEXTS.get(id(bearer))
        return (
            registered is not None
            and registered[0] is bearer
            and (token is None or registered[1] is token)
        )


def _deregister_session_context(*, bearer: _SessionBearer) -> None:
    with _AUTHORITY_REGISTRY_LOCK:
        registered = _ACTIVE_SESSION_CONTEXTS.get(id(bearer))
        if registered is not None and registered[0] is bearer:
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


def _resolve_local_app_data_root(configured: Path | None) -> Path:
    if configured is None:
        environment_value = os.environ.get("LOCALAPPDATA")
        if not environment_value:
            raise SessionValidationError(
                "live_start_local_app_data_missing"
            )
        configured = Path(environment_value)
    return Path(configured).absolute()


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

    root = Path(session_root).absolute()
    run_id = root.name
    _require_run_id(run_id)
    _require_deck_name(deck_name)
    _require_sha256(deck_code_sha256, "deck_code_sha256")
    frozen_inputs, derived_manifest_sha256 = (
        _validate_frozen_compiler_inputs(
            frozen_compiler_inputs,  # type: ignore[arg-type]
            deck_name=deck_name,
            deck_code_sha256=deck_code_sha256,
            runtime_root=runtime_root,
            output_base_root=output_base_root,
            output_deck_root=output_deck_root,
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
    local_root = _resolve_local_app_data_root(local_app_data_root)
    state_root = local_root / "HSConfig"
    expected_root = state_root / "runs" / run_id
    if root != expected_root:
        raise SessionValidationError(
            "live_start_session_root_not_canonical"
        )
    forbidden_roots = tuple(
        Path(path).absolute()
        for path in (
            repository_root,
            runtime_root,
            output_base_root,
            output_deck_root,
            installed_skill_root,
        )
    )
    if any(
        _paths_overlap(state_root, forbidden_root)
        for forbidden_root in forbidden_roots
    ):
        raise SessionValidationError(
            "live_start_session_forbidden_root_overlap"
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
    root = Path(session_root).absolute()
    run_id = root.name
    _require_run_id(run_id)
    local_root = _resolve_local_app_data_root(local_app_data_root)
    expected_root = local_root / "HSConfig" / "runs" / run_id
    if root != expected_root:
        raise SessionValidationError(
            "live_start_session_root_not_canonical"
        )
    _validate_existing_plain_ancestor_chain(local_root)
    lock_path = _session_lock_path(root)
    if not os.path.lexists(root) or not os.path.lexists(lock_path):
        raise FileNotFoundError("live_start_session_authority_missing")
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
    successor_value = _apply_session_update(
        current,
        update,
        transition_authority=transition_authority,
    )
    successor = _seal_session_value(successor_value, session_identity=None)
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
        if event in {"apply_committed", "runtime_matched", "bind_terminal"}:
            raise SessionCapabilityError(
                "live_start_specialized_transition_authority_required"
            )
        if set(changes) & _PUBLIC_SENSITIVE_UPDATE_FIELDS:
            raise SessionCapabilityError(
                "live_start_specialized_field_authority_required"
            )
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
        and isinstance(successor_pending_value, Mapping)
        and successor_pending_value.get("operation")
        == "cleanup_prepublication"
    ):
        _validate_prepublication_cleanup_pending_successor(
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
    if not bearer.active or not bearer.nonce:
        raise SessionCapabilityError("live_start_session_capability_expired")
    if not _session_context_is_registered(bearer=bearer, token=token):
        raise SessionCapabilityError("live_start_session_capability_forged")
    if bearer.thread_id != threading.get_ident():
        raise SessionCapabilityError("live_start_session_capability_wrong_thread")
    if (
        lease.session_root != bearer.session_root
        or lease.session_root_identity != bearer.session_root_identity
        or lease.session_lock_path != bearer.session_lock_path
        or lease.session_lock_identity != bearer.session_lock_identity
        or path_identity(lease.session_root) != bearer.session_root_identity
        or path_identity(lease.session_lock_path) != bearer.session_lock_identity
    ):
        raise SessionCapabilityError("live_start_session_capability_context_mismatch")
    lock_status = lease.session_lock_path.lstat()
    if lock_status.st_size != 0 or bearer.session_lock is None:
        raise SessionCapabilityError(
            "live_start_session_capability_lock_invalid"
        )
    try:
        bearer.session_lock.validate_no_alternate_data_streams(
            expected_size=0
        )
    except (OSError, RuntimeError, ValueError) as error:
        raise SessionCapabilityError(
            "live_start_session_capability_lock_invalid"
        ) from error
    return bearer


def _session_lock_path(session_root: Path) -> Path:
    return (
        session_root.parent.parent
        / "locks"
        / f"live-start-{session_root.name}.lock"
    )


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _validate_existing_plain_ancestor_chain(path: Path) -> None:
    current = Path(path).absolute()
    existing: list[Path] = []
    while True:
        if os.path.lexists(current):
            existing.append(current)
        if current.parent == current:
            break
        current = current.parent
    for ancestor in reversed(existing):
        status = ancestor.lstat()
        if not stat.S_ISDIR(status.st_mode) or status_is_reparse(status):
            raise SessionLayoutError(
                "live_start_state_ancestor_invalid"
            )


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
    status = Path(path).lstat()
    identity = path_identity_from_status(status)
    if (
        not stat.S_ISREG(status.st_mode)
        or status_is_reparse(status)
        or status.st_nlink != 1
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
            or after.st_nlink != 1
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
    cleanup_entry_count cleanup_inventory_path cleanup_inventory_identity
    cleanup_inventory_size cleanup_inventory_sha256 quarantine_path
    cleanup_parent_identity quarantine_identity cleanup_cursor apply_attempt_id
    apply_invocation_sha256 runtime_admission_document_size
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
    retained_target_owner_journal_sha256 runtime_admission_path
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
    retained_target_owner_journal_sha256 content_sha256""".split()
)
_TERMINAL_RESOLUTION_FIELDS = frozenset(
    """schema_version resolution_kind run_id apply_attempt_id
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

    if phase_index < package_index and prepublication is not None:
        raise SessionValidationError(
            "live_start_prepublication_work_phase_invalid"
        )
    if phase in {
        LiveStartPhase.PACKAGE_VALIDATED,
        LiveStartPhase.PREPUBLICATION_CHECK_PASSED,
    } and prepublication is None:
        raise SessionValidationError(
            "live_start_prepublication_work_binding_missing"
        )
    if phase_index >= publication_index and prepublication is not None:
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
        if recovery is not None:
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
        ):
            if retirement.get(retirement_name) != intent.get(intent_name):
                raise SessionValidationError(
                    "live_start_terminal_retirement_outer_binding_invalid"
                )
        resolution = retirement.get("terminal_resolution_evidence")
        if isinstance(resolution, Mapping) and (
            resolution.get("run_id") != run_id
            or resolution.get("apply_attempt_id")
            != retirement.get("apply_attempt_id")
            or resolution.get("package_root_sha256")
            != intent.get("package_root_sha256")
        ):
            raise SessionValidationError(
                "live_start_terminal_resolution_outer_binding_invalid"
            )
    if retirement is not None and terminal_status is None:
        raise SessionValidationError(
            "live_start_terminal_retirement_status_missing"
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
    if extras - result_paths:
        raise SessionValidationError(
            "live_start_phase_artifact_binding_forbidden"
        )
    intent = value.get("result_intent")
    if intent is None and extras:
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
    if (
        staging_path != final_path.with_name(f"{final_path.name}.staged")
        or inner_path
        != staging_path.with_name(f".{staging_path.name}.live-start-atomic.tmp")
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
        _require_identity(row.get("expected_parent_identity"), "expected_parent_identity")
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
                != "bind_created_candidate"
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
_APPLY_RECOVERY_ACTION_MUTABLE_FIELDS = MappingProxyType(
    {
        "observe_not_committed": frozenset(
            {
                "stable_physical_disposition",
            }
        ),
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
            }
        ),
        "commit_bound_prior_owner_attempt_record": frozenset(
            {
                "external_file_action",
                "successor_attempt_record_path",
                "successor_attempt_record_identity",
                "successor_attempt_record_sha256",
            }
        ),
        "materialize_candidate_tree_entry": frozenset(
            {
                "external_file_action",
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
            {"external_file_action", "candidate_tree_verified_sha256"}
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
        ),
        "observe_pending": frozenset(
            {"runtime_match_status", "stable_physical_disposition"}
        ),
        "observe_unknown": frozenset(
            {"runtime_match_status", "stable_physical_disposition"}
        ),
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
            {"commit_owner_retirement_prepared", "observe_committed"}
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
        )
        _require_owner_external_action(
            next_external,
            action_kind="initialize_owner_cleanup_journal",
            stage="PLANNED",
            final_path=current["initial_owner_journal_path"],
            predecessor_state="exact",
            predecessor_identity=current["initial_owner_journal_identity"],
            predecessor_sha256=current["initial_owner_journal_sha256"],
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
        or current.get("expected_action") != action
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
        or next_value.get("external_file_action") is not None
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
    for field_name in _APPLY_RECOVERY_FIELDS - {
        "recovery_stage",
        "content_sha256",
    }:
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
    if current != next_value:
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


def _validate_terminal_owner_successor(
    *,
    predecessor: Mapping[str, Any],
    successor: Mapping[str, Any],
) -> str | None:
    current_owner_raw = predecessor.get("owner_retirement")
    next_owner_raw = successor.get("owner_retirement")
    if current_owner_raw is None and next_owner_raw is None:
        return None
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
    action = _owner_action_for_cursor(
        owner=current_owner,
        external=current_external,
    )
    successor_action = _owner_successor_action(
        action=action,
        current_external=current_external,
        successor_owner=next_owner,
    )
    current_cursor = {
        "owner_retirement": current_owner,
        "external_file_action": current_external,
        "expected_action": action,
    }
    successor_cursor = {
        "owner_retirement": next_owner,
        "external_file_action": next_external_raw,
        "expected_action": successor_action,
    }
    _validate_owner_retirement_successor(
        predecessor=current_cursor,
        successor=successor_cursor,
        action=action,
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
    if (
        not changed
        or not changed
        <= _TERMINAL_RESOLUTION_MUTABLE_FIELDS[transition]
    ):
        raise SessionCapabilityError(
            "live_start_terminal_resolution_successor_changed"
        )
    owner_action: str | None = None
    if transition == "physical_recovery_advanced":
        owner_action = _validate_terminal_owner_successor(
            predecessor=current_resolution,
            successor=next_resolution,
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
    elif transition == "journal_retired" and (
        next_resolution.get("cleanup_stage")
        not in {None, "JOURNAL_RETIRED"}
    ):
        raise SessionCapabilityError(
            "live_start_terminal_resolution_successor_invalid"
        )
    elif transition == "fence_retired" and (
        next_resolution.get("cleanup_stage")
        not in {None, "FENCE_RETIRED"}
    ):
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
            "journal_owns_target": True,
            "acknowledgement_action": (
                "retain_target_owner_delete_fence"
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
        return (
            operation == "release_not_committed" and not has_resolution
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
            0,
            LIVE_START_OWNER_RETIREMENT_EVIDENCE_MAX_BYTES,
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
        > LIVE_START_OWNER_RETIREMENT_EVIDENCE_MAX_BYTES
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
    for key in (
        "initial_owner_journal_path",
        "retired_target_path",
        "successor_owner_journal_path",
    ):
        _require_absolute_path(normalized.get(key), key)
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
        raw, _identity = _read_bound_file(
            session_lease.session_root / logical,
            expected_parent_identity=path_identity(
                (session_lease.session_root / logical).parent
            ),
            maximum_size=256 * 1024,
        )
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
    allowed_reserved = _allowed_reserved_run_paths(root=root, session=session)
    allowed_files = _allowed_logical_run_files(root=root, session=session)
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
                or status.st_nlink != 1
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
    if isinstance(pending, Mapping) and pending.get("stage") in {
        "PRIMARY_APPLIED",
        "CLEANUP_DELETING",
    }:
        successor_bindings = pending.get("successor_artifact_bindings")
        if isinstance(successor_bindings, Mapping):
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
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
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
    if isinstance(value, list):
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
]
RUNTIME_OBSERVATION_FAMILIES = frozenset(
    {
        "first_install",
        "nonterminal_apply",
        "terminal_resolution",
        "terminal_classification",
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


class _OpaqueBearer:
    __slots__ = (
        "active",
        "action",
        "cursor_sha256",
        "family",
        "nonce",
        "session_bearer",
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
        self.session_bearer = session_bearer
        self.thread_id = threading.get_ident()
        self.successor: Any = None


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


_ACTIVE_OPAQUE_BEARERS: dict[int, _OpaqueBearer] = {}
_ACTIVE_OPAQUE_CARRIERS: dict[
    int,
    tuple[_OpaqueCarrier, _OpaqueBearer],
] = {}


def _mint_registered_opaque_carrier(
    *,
    carrier_type: type[_AuthorizationT],
    bearer: _OpaqueBearer,
) -> _AuthorizationT:
    if not _session_context_is_registered(bearer=bearer.session_bearer):
        raise SessionCapabilityError(
            "live_start_physical_capability_session_forged"
        )
    carrier = carrier_type._mint(bearer)
    with _AUTHORITY_REGISTRY_LOCK:
        if id(bearer) in _ACTIVE_OPAQUE_BEARERS:
            raise SessionCapabilityError(
                "live_start_physical_capability_registry_conflict"
            )
        _ACTIVE_OPAQUE_BEARERS[id(bearer)] = bearer
        _ACTIVE_OPAQUE_CARRIERS[id(carrier)] = (carrier, bearer)
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
        ):
            _ACTIVE_OPAQUE_CARRIERS[id(copied)] = (
                copied,
                registered[1],
            )


def _opaque_carrier_is_registered(
    *,
    carrier: _OpaqueCarrier,
    bearer: _OpaqueBearer,
) -> bool:
    with _AUTHORITY_REGISTRY_LOCK:
        bearer_registered = _ACTIVE_OPAQUE_BEARERS.get(id(bearer))
        carrier_registered = _ACTIVE_OPAQUE_CARRIERS.get(id(carrier))
        return (
            bearer_registered is bearer
            and carrier_registered is not None
            and carrier_registered[0] is carrier
            and carrier_registered[1] is bearer
        )


def _deregister_opaque_bearer(*, bearer: _OpaqueBearer) -> None:
    with _AUTHORITY_REGISTRY_LOCK:
        if _ACTIVE_OPAQUE_BEARERS.get(id(bearer)) is bearer:
            del _ACTIVE_OPAQUE_BEARERS[id(bearer)]
        for carrier_id, (_carrier, registered_bearer) in tuple(
            _ACTIVE_OPAQUE_CARRIERS.items()
        ):
            if registered_bearer is bearer:
                del _ACTIVE_OPAQUE_CARRIERS[carrier_id]


def _deactivate_opaque_bearers_for_session(
    session_bearer: _SessionBearer,
) -> None:
    with _AUTHORITY_REGISTRY_LOCK:
        bearers = tuple(_ACTIVE_OPAQUE_BEARERS.values())
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
    session_bearer = _require_session_lease(session_lease)
    current = _load_expected_predecessor_under_lock(
        session_lease=session_lease,
        expected_session=expected_session,
    )
    _validate_run_layout_under_lock(
        session_lease=session_lease,
        session=current,
    )
    bearer = _OpaqueBearer(
        session_bearer=session_bearer,
        family=family,
        cursor_sha256=current.content_sha256,
        action=action,
    )
    return _mint_registered_opaque_carrier(
        carrier_type=authorization_type,
        bearer=bearer,
    )


def _require_opaque_carrier(
    carrier: _OpaqueCarrier,
    *,
    carrier_type: type[_AuthorizationT],
    family: str,
    action: str,
    consume: bool,
) -> _OpaqueBearer:
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
    if consume:
        _deregister_opaque_bearer(bearer=bearer)
        bearer.active = False
        bearer.nonce = ""
    return bearer


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
) -> _ReceiptT:
    bearer = _require_opaque_carrier(
        authorization,
        carrier_type=authorization_type,
        family=family,
        action=action,
        consume=True,
    )
    result = physical_action()
    if not isinstance(result, postcondition_type) or result.action != action:
        raise SessionCapabilityError("live_start_physical_postcondition_invalid")
    receipt_bearer = _OpaqueBearer(
        session_bearer=bearer.session_bearer,
        family=f"{family}_receipt",
        cursor_sha256=bearer.cursor_sha256,
        action=action,
    )
    receipt_bearer.successor = result
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
) -> None:
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
        if os.path.lexists(staging_path) or os.path.lexists(inner_temp_path):
            raise SessionConflictError(
                "live_start_owner_external_unbound_staging_present"
            )
        return
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


def _validate_owner_action_precondition_under_lock(
    *,
    recovery: Mapping[str, Any],
    action: str,
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
    stage = owner["stage"]
    expected = _owner_action_for_cursor(owner=owner, external=external)
    if expected != action:
        raise SessionConflictError(
            "live_start_owner_action_precondition_invalid"
        )

    tombstone_path = Path(owner["tombstone_path"])
    tombstone_parent = _require_identity(
        owner["tombstone_parent_identity"],
        "owner_tombstone_parent_identity",
    )
    target = Path(owner["retired_target_path"])
    target_parent = _require_identity(
        owner["retired_target_parent_identity"],
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
        expected_parent_identity=path_identity(successor_path.parent),
        expected_identity=owner["successor_owner_journal_identity"],
        expected_sha256=owner["successor_owner_journal_sha256"],
    )

    prepared_document: Mapping[str, Any] | None = None
    completed_raw: bytes | None = None
    if stage == "PREPARED_PLANNED":
        if os.path.lexists(tombstone_path):
            raise SessionConflictError(
                "live_start_owner_tombstone_created_early"
            )
    else:
        expected_tombstone_state = (
            "COMPLETED"
            if stage in {"COMPLETED", "OWNER_RETIRED"}
            else "PREPARED"
        )
        raw = _read_exact_owner_file(
            path=tombstone_path,
            expected_parent_identity=tombstone_parent,
            expected_identity=owner["tombstone_identity"],
            expected_sha256=owner["tombstone_sha256"],
        )
        prepared_document, completed_raw = (
            _validate_owner_tombstone_binding(
                owner=owner,
                raw=raw,
                expected_state=expected_tombstone_state,
                expected_raw_sha256=owner["tombstone_sha256"],
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
    old_journal_parent = path_identity(old_journal.parent)
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
    else:
        _read_exact_owner_file(
            path=old_journal,
            expected_parent_identity=old_journal_parent,
            expected_identity=owner["current_owner_journal_identity"],
            expected_sha256=owner["current_owner_journal_sha256"],
        )

    if external is not None:
        _validate_owner_external_physical(external)
    if action == "commit_owner_retirement_prepared":
        assert external is not None
        raw = _read_exact_owner_file(
            path=Path(external["staging_path"]),
            expected_parent_identity=tombstone_parent,
            expected_identity=external["staging_identity"],
            expected_sha256=external["staging_sha256"],
            expected_size=external["staging_size"],
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
        staged = _read_exact_owner_file(
            path=Path(external["staging_path"]),
            expected_parent_identity=tombstone_parent,
            expected_identity=external["staging_identity"],
            expected_sha256=external["staging_sha256"],
            expected_size=external["staging_size"],
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
        if not os.path.lexists(entry_path):
            pass
        elif owner["next_entry_kind"] == "file":
            _read_exact_owner_file(
                path=entry_path,
                expected_parent_identity=_require_identity(
                    owner["next_entry_parent_identity"],
                    "owner_next_entry_parent_identity",
                ),
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
        )
    except (SessionConflictError, SessionValidationError) as error:
        raise SessionCapabilityError(
            "live_start_owner_delete_postcondition_physical_changed"
        ) from error


def _validate_owner_old_journal_postcondition(
    *,
    predecessor: Mapping[str, Any],
    evidence: Mapping[str, Any],
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
) -> None:
    validators = {
        "delete_owner_cleanup_entry": _validate_owner_delete_postcondition,
        "retire_owner_target_root": _validate_owner_root_postcondition,
        "retire_old_owner_journal": (
            _validate_owner_old_journal_postcondition
        ),
    }
    validator = validators.get(action)
    if validator is not None:
        validator(predecessor=predecessor, evidence=evidence)


def _consume_receipt_under_lock(
    *,
    receipt: _OpaqueCarrier,
    receipt_type: type[_ReceiptT],
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    family: str,
    action: str,
) -> _PhysicalPostcondition:
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
    bearer = _require_opaque_carrier(
        receipt,
        carrier_type=receipt_type,
        family=f"{family}_receipt",
        action=action,
        consume=True,
    )
    if (
        bearer.cursor_sha256 != current.content_sha256
        or not isinstance(bearer.successor, _PhysicalPostcondition)
    ):
        raise SessionCapabilityError("live_start_physical_receipt_stale")
    return bearer.successor


def _validate_apply_recovery_action_precondition_under_lock(
    *,
    recovery: Mapping[str, Any],
    action: str,
) -> None:
    _validate_owner_action_precondition_under_lock(
        recovery=recovery,
        action=action,
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
    recovery = expected_recovery_session.apply_recovery
    if not isinstance(recovery, Mapping) or recovery.get("recovery_stage") != "ACTIVE":
        raise SessionConflictError("live_start_apply_recovery_cursor_invalid")
    if expected_action in RUNTIME_APPLY_RECOVERY_ACTIONS and recovery.get("expected_action") != expected_action:
        raise SessionConflictError("live_start_apply_recovery_action_mismatch")
    _validate_apply_recovery_action_precondition_under_lock(
        recovery=recovery,
        action=expected_action,
    )
    authorization = _mint_authorization_under_lock(
        authorization_type=RuntimeAttemptRecoveryAuthorization,
        session_lease=session_lease,
        expected_session=expected_recovery_session,
        family="nonterminal_apply_recovery",
        action=expected_action,
    )
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
        authorization._opaque.successor = {
            "owner_object_preexisting": os.path.lexists(path)
        }
    return authorization


def _execute_apply_recovery_physical_step(
    *,
    recovery_authorization: RuntimeAttemptRecoveryAuthorization,
    action: RuntimeApplyRecoveryAction,
    physical_action: Callable[[], RuntimeApplyRecoveryPhysicalPostcondition],
) -> ApplyRecoveryStepReceipt:
    if action not in RUNTIME_APPLY_RECOVERY_ACTIONS:
        raise SessionValidationError("live_start_apply_recovery_action_invalid")
    owner_context: Mapping[str, Any] | None = None
    if action in {
        "delete_owner_cleanup_entry",
        "retire_owner_target_root",
        "retire_old_owner_journal",
    }:
        bearer = _require_opaque_carrier(
            recovery_authorization,
            carrier_type=RuntimeAttemptRecoveryAuthorization,
            family="nonterminal_apply_recovery",
            action=action,
            consume=False,
        )
        if not isinstance(bearer.successor, Mapping):
            raise SessionCapabilityError(
                "live_start_owner_authorization_context_missing"
            )
        owner_context = bearer.successor
    receipt = _execute_physical_step(
        authorization=recovery_authorization,
        authorization_type=RuntimeAttemptRecoveryAuthorization,
        receipt_type=ApplyRecoveryStepReceipt,
        postcondition_type=RuntimeApplyRecoveryPhysicalPostcondition,
        family="nonterminal_apply_recovery",
        action=action,
        physical_action=physical_action,
    )
    if owner_context is not None:
        postcondition = receipt._opaque.successor
        if not isinstance(
            postcondition,
            RuntimeApplyRecoveryPhysicalPostcondition,
        ):
            raise SessionCapabilityError(
                "live_start_owner_postcondition_family_invalid"
            )
        evidence = dict(postcondition.evidence)
        evidence["_owner_object_preexisting"] = owner_context.get(
            "owner_object_preexisting"
        )
        receipt._opaque.successor = (
            RuntimeApplyRecoveryPhysicalPostcondition(
                action=action,
                evidence=evidence,
            )
        )
    return receipt


def authorize_terminal_retirement_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_retirement_session: LiveStartSession,
) -> TerminalRetirementAuthorization:
    retirement = expected_retirement_session.terminal_retirement
    if not isinstance(retirement, Mapping):
        raise SessionConflictError("live_start_terminal_retirement_missing")
    action = _terminal_action_for_retirement(
        retirement,
        attempt_acknowledgement=(
            expected_retirement_session.attempt_acknowledgement
        ),
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
            _validate_owner_action_precondition_under_lock(
                recovery={
                    "owner_retirement": current_owner,
                    "external_file_action": current_external,
                },
                action=owner_action,
            )
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
                owner_context = {
                    "owner_object_preexisting": os.path.lexists(owner_path)
                }
    if action == "materialize_terminal_cleanup_inventory_staging":
        resolution = retirement["terminal_resolution_evidence"]
        external = resolution["external_file_action"]
        if os.path.lexists(Path(external["staging_path"])) or os.path.lexists(
            Path(external["inner_temp_path"])
        ):
            action = "retire_unbound_terminal_cleanup_inventory_staging"
    authorization = _mint_authorization_under_lock(
        authorization_type=TerminalRetirementAuthorization,
        session_lease=session_lease,
        expected_session=expected_retirement_session,
        family="terminal_retirement",
        action=action,
    )
    if owner_context is not None:
        authorization._opaque.successor = owner_context
    elif action == "release_runtime_admission":
        authorization._opaque.successor = {
            "admission_path": Path(retirement["runtime_admission_path"]),
            "admission_parent_identity": _require_identity(
                retirement["runtime_admission_parent_identity"],
                "runtime_admission_parent_identity",
            ),
            "historical_admission_identity": _require_identity(
                retirement["runtime_admission_identity"],
                "runtime_admission_identity",
            ),
            "historical_admission_sha256": retirement[
                "runtime_admission_sha256"
            ],
        }
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
        if cleanup_stage == "PREPARED" and isinstance(external, Mapping):
            if external.get("stage") == "PLANNED":
                return "materialize_terminal_cleanup_inventory_staging"
            if external.get("stage") == "STAGING_BOUND":
                return "commit_bound_terminal_cleanup_inventory"
            raise SessionConflictError(
                "live_start_terminal_cleanup_external_stage_invalid"
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


def _execute_terminal_resolution_physical_step(
    *,
    terminal_authorization: TerminalRetirementAuthorization,
    action: str,
    physical_action: Callable[[], TerminalResolutionPhysicalPostcondition | SuccessAckStepEvidence],
) -> TerminalResolutionStepReceipt:
    if action not in TERMINAL_RESOLUTION_PHYSICAL_ACTIONS:
        raise SessionValidationError("live_start_terminal_resolution_action_invalid")
    bearer = _require_opaque_carrier(
        terminal_authorization,
        carrier_type=TerminalRetirementAuthorization,
        family="terminal_retirement",
        action=action,
        consume=True,
    )
    result = physical_action()
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
        raise SessionCapabilityError("live_start_terminal_resolution_postcondition_invalid")
    if action == "physical_recovery_advanced" and isinstance(
        bearer.successor,
        Mapping,
    ):
        evidence = dict(result.evidence)
        evidence["_owner_object_preexisting"] = bearer.successor.get(
            "owner_object_preexisting"
        )
        result = TerminalResolutionPhysicalPostcondition(
            action=result.action,
            evidence=evidence,
        )
    receipt_bearer = _OpaqueBearer(
        session_bearer=bearer.session_bearer,
        family="terminal_retirement_receipt",
        cursor_sha256=bearer.cursor_sha256,
        action=action,
    )
    receipt_bearer.successor = result
    return _mint_registered_opaque_carrier(
        carrier_type=TerminalResolutionStepReceipt,
        bearer=receipt_bearer,
    )


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
    _require_opaque_carrier(
        observation_authorization,
        carrier_type=RuntimeObservationAuthorization,
        family=bearer.family,
        action=bearer.action,
        consume=True,
    )
    result = read_only_observation()
    if not isinstance(result, RuntimeObservationPostcondition) or result.observation_family != observation_family:
        raise SessionCapabilityError("live_start_runtime_observation_postcondition_invalid")
    receipt_bearer = _OpaqueBearer(
        session_bearer=bearer.session_bearer,
        family=f"runtime_observation_receipt:{observation_family}",
        cursor_sha256=bearer.cursor_sha256,
        action=bearer.action,
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
    bearer = _require_opaque_carrier(
        terminal_authorization,
        carrier_type=TerminalRetirementAuthorization,
        family="terminal_retirement",
        action=action,
        consume=True,
    )
    result = physical_action()
    if not isinstance(result, RuntimeAdmissionReleasePostcondition):
        raise SessionCapabilityError("live_start_runtime_admission_release_postcondition_invalid")
    expected = bearer.successor
    if not isinstance(expected, Mapping) or any(
        actual != expected.get(key)
        for key, actual in (
            ("admission_path", result.admission_path),
            (
                "admission_parent_identity",
                result.admission_parent_identity,
            ),
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
        "output_base_identity": pending.get("output_base_identity"),
        "output_child_path": pending.get("output_child_path"),
        "predecessor_state": pending.get("output_child_predecessor_state"),
        "predecessor_output_child_identity": pending.get(
            "output_child_predecessor_identity"
        ),
        "claim_path": pending.get("output_claim_path"),
        "claim_parent_identity": pending.get("output_claim_parent_identity"),
        "claim_identity": pending.get("output_claim_identity"),
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
        for field_name in _RUNTIME_LAYOUT_DIRECTORY_FIELDS - {
            "successor_identity"
        }:
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
        or expected_admission_committed_session.runtime_layout_bootstrap is not None
    ):
        raise SessionConflictError("live_start_runtime_layout_prepare_invalid")
    if not isinstance(layout_evidence, RuntimeLayoutBootstrapEvidence):
        raise TypeError("live_start_runtime_layout_evidence_invalid")
    validated = validate_embedded_document(
        "runtime_layout_bootstrap",
        layout_evidence.value,
    )
    if validated.get("stage") != "INCOMPLETE":
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
    changes: dict[str, Any] = {"runtime_layout_bootstrap": validated}
    if validated["stage"] == "COMPLETE":
        pending = _thaw(expected_layout_session.pending_transition)
        invocation_action = evidence.get("invocation_receipt_file_action")
        if not isinstance(invocation_action, Mapping):
            raise SessionCapabilityError("live_start_invocation_receipt_intent_missing")
        validate_embedded_document("external_file_action", invocation_action)
        pending["external_file_action"] = invocation_action
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
    if not isinstance(pending, Mapping) or pending.get("operation") != "install_apply_invocation":
        raise SessionConflictError("live_start_runtime_admission_cursor_invalid")
    external = pending.get("external_file_action")
    if not isinstance(external, Mapping) or external.get("action_kind") != action:
        raise SessionConflictError("live_start_runtime_admission_action_mismatch")
    return _mint_authorization_under_lock(
        authorization_type=RuntimeAdmissionAuthorization,
        session_lease=session_lease,
        expected_session=expected_admission_session,
        family="runtime_admission",
        action=action,
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
        pending["external_file_action"] = _bind_external_staging_from_receipt(
            external=external,
            evidence=evidence,
        )
        if transition == "staging_bound":
            pending["stage"] = "STAGING_BOUND"
            pending["runtime_admission_staging_identity"] = evidence["staging_identity"]
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


def _complete_apply_started_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_receipt_committed_session: LiveStartSession,
    invocation: Any,
    runtime_admission: Any,
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

    invocation_value = getattr(invocation, "value", invocation)
    if isinstance(invocation_value, Mapping):
        invocation_sha256 = invocation_value.get("content_sha256")
    else:
        invocation_sha256 = getattr(invocation, "content_sha256", None)
    invocation_sha256 = _require_sha256(
        invocation_sha256,
        "apply_invocation_sha256",
    )
    if invocation_sha256 != pending.get("apply_invocation_sha256"):
        raise SessionCapabilityError(
            "live_start_apply_started_invocation_binding_invalid"
        )

    admission_value = getattr(runtime_admission, "value", runtime_admission)
    if isinstance(admission_value, Mapping):
        admission = _normalize_json(admission_value)
    else:
        admission = {
            field_name: getattr(runtime_admission, field_name, None)
            for field_name in _RUNTIME_ADMISSION_BINDING_FIELDS
        }
    if not isinstance(admission, dict):
        raise SessionCapabilityError(
            "live_start_apply_started_admission_binding_invalid"
        )
    _validate_runtime_admission_binding(admission)
    expected_admission = _normalize_json({
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
    if admission != expected_admission or (
        pending.get("runtime_admission_document_sha256")
        != admission.get("admission_sha256")
        or pending.get("runtime_admission_sha256")
        != admission.get("admission_sha256")
    ):
        raise SessionCapabilityError(
            "live_start_apply_started_admission_binding_invalid"
        )

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
    return _transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=expected_receipt_committed_session,
        event="apply_started",
        changes={
            "artifact_bindings": successor_bindings,
            "pending_transition": None,
            "output_operation_admission_binding": sealed_handoff,
            "apply_invocation_sha256": invocation_sha256,
            "runtime_admission_binding": admission,
        },
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


def record_terminal_status_under_lock(
    *,
    session_lease: LiveStartSessionLease,
    expected_result_session: LiveStartSession,
) -> LiveStartSession:
    intent = expected_result_session.result_intent
    if (
        not isinstance(intent, Mapping)
        or expected_result_session.terminal_status is not None
        or expected_result_session.apply_recovery is not None
        or expected_result_session.pending_transition is not None
    ):
        raise SessionConflictError("live_start_terminal_status_cursor_invalid")
    return _transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=expected_result_session,
        event="bind_terminal",
        changes={"terminal_status": intent["terminal_status"]},
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
        resolved_evidence = _freeze_mapping(resolved)
        stage = "RECOVERY_PREPARED"
    else:
        if runtime_observation_receipt is not None:
            raise SessionCapabilityError("live_start_terminal_observation_forbidden")
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
    }
    retirement = seal_embedded_document("terminal_retirement", value)
    return _transition_receipt_authorized_under_lock(
        session_lease=session_lease,
        expected_session=expected_terminal_session,
        event="same_phase_cas",
        changes={"terminal_retirement": retirement},
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
