"""Neutral fixed output-operation admission observation and lock gates."""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import Lock, get_ident
from typing import Any, Literal

from hsconfig.atomic_io import ExclusiveFileLock
from hsconfig.package_io import (
    PathIdentity,
    capture_plain_ancestor_guard,
    path_identity,
    path_identity_from_status,
    path_lexists,
    plain_file_status,
    read_file_no_follow,
    require_no_alternate_data_streams,
    require_plain_directory,
    require_same_identity_resolution,
)


OUTPUT_OPERATION_ADMISSION_SCHEMA_VERSION = 1
OUTPUT_OPERATION_ADMISSION_MAX_BYTES = 64 * 1024
OUTPUT_OPERATION_ADMISSION_KIND = "live_start_output_operation_admission"
OUTPUT_OPERATION_ADMISSION_NAME = "output-operation-admission.json"
OUTPUT_OPERATION_ADMISSION_STAGING_NAME = "output-operation-admission.staged"
OUTPUT_OPERATION_ADMISSION_RESERVED_TEMP_NAME = (
    ".output-operation-admission.staged.live-start-atomic.tmp"
)
OUTPUT_OPERATION_LOCK_NAME = "output-operation.lock"
OUTPUT_OPERATION_ADMISSION_FIELDS = frozenset(
    {
        "schema_version",
        "record_kind",
        "state",
        "run_id",
        "session_root",
        "session_root_identity",
        "expected_session_sha256",
        "operator_profile_path",
        "operator_profile_parent_identity",
        "operator_profile_identity",
        "operator_profile_sha256",
        "state_root_identity",
        "output_base_root",
        "output_base_root_identity",
        "output_child_path",
        "output_child_predecessor_state",
        "output_child_predecessor_identity",
        "output_bootstrap_lock_path",
        "output_bootstrap_lock_identity",
        "output_claim_path",
        "content_sha256",
    }
)


_STANDARD_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_RUN_ID = re.compile(r"[0-9a-f]{32}\Z")
_TOKEN_AUTHORITY = object()
_WINDOWS_RESERVED_NAMES = frozenset(
    {"con", "prn", "aux", "nul", "conin$", "conout$"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
    | {
        f"{prefix}{suffix}"
        for prefix in ("com", "lpt")
        for suffix in ("¹", "²", "³")
    }
)
_WINDOWS_INVALID_COMPONENT_CHARACTERS = frozenset('<>"/\\|?*:')
_WINDOWS_UNC_IPC_SHARES = frozenset({"pipe", "mailslot", "ipc$"})
_LOCK_STREAM_VALIDATION_TIMEOUT_SECONDS = 30.0
_STATE_ROOT_MAX_IDENTITY_ROWS = 256


@dataclass(frozen=True, slots=True, init=False)
class OutputOperationAdmissionLockToken:
    """Opaque process-local capability for one held operation lock."""

    _nonce: object
    _thread_id: int

    def __init__(self, authority: object | None = None) -> None:
        if authority is not _TOKEN_AUTHORITY:
            raise TypeError("output_operation_admission_token_not_constructible")
        object.__setattr__(self, "_nonce", object())
        object.__setattr__(self, "_thread_id", get_ident())

    def __copy__(self) -> OutputOperationAdmissionLockToken:
        raise TypeError("output_operation_admission_token_not_copyable")

    def __deepcopy__(self, memo: dict[int, object]) -> OutputOperationAdmissionLockToken:
        raise TypeError("output_operation_admission_token_not_copyable")

    def __reduce__(self) -> object:
        raise TypeError("output_operation_admission_token_not_serializable")


@dataclass(frozen=True, slots=True)
class OutputOperationAdmissionLease:
    state_root: Path
    state_root_identity: PathIdentity
    locks_root_identity: PathIdentity
    lock_path: Path
    lock_identity: PathIdentity
    lock_token: OutputOperationAdmissionLockToken


@dataclass(frozen=True, slots=True)
class OutputOperationAdmissionEvidence:
    admission_path: Path
    admission_parent_identity: PathIdentity
    admission_identity: PathIdentity
    admission_size: int
    admission_sha256: str
    state: Literal["ACTIVE"]
    run_id: str
    session_root: Path
    session_root_identity: PathIdentity
    expected_session_sha256: str
    operator_profile_path: Path
    operator_profile_parent_identity: PathIdentity
    operator_profile_identity: PathIdentity
    operator_profile_sha256: str
    state_root_identity: PathIdentity
    output_base_root: Path
    output_base_root_identity: PathIdentity
    output_child_path: Path
    output_child_predecessor_state: Literal["absent", "existing"]
    output_child_predecessor_identity: PathIdentity | None
    output_bootstrap_lock_path: Path
    output_bootstrap_lock_identity: PathIdentity
    output_claim_path: Path


_active_leases: dict[
    int,
    tuple[
        OutputOperationAdmissionLockToken,
        OutputOperationAdmissionLease,
        int,
    ],
] = {}
_active_leases_lock = Lock()


def output_operation_state_root(
    environ: Mapping[str, str] | None = None,
) -> Path:
    environment = os.environ if environ is None else environ
    raw = environment.get("LOCALAPPDATA")
    if not isinstance(raw, str) or not raw:
        raise ValueError("localappdata_missing")
    root = Path(raw)
    if not root.is_absolute():
        raise ValueError("localappdata_not_absolute")
    _require_windows_safe_absolute_path(
        root,
        error="localappdata_windows_namespace_invalid",
    )
    return root / "HSConfig"


def output_operation_admission_path(
    environ: Mapping[str, str] | None = None,
) -> Path:
    return output_operation_state_root(environ) / OUTPUT_OPERATION_ADMISSION_NAME


def output_operation_admission_staging_path(
    environ: Mapping[str, str] | None = None,
) -> Path:
    return output_operation_state_root(environ) / OUTPUT_OPERATION_ADMISSION_STAGING_NAME


def output_operation_admission_reserved_temp_path(
    environ: Mapping[str, str] | None = None,
) -> Path:
    return (
        output_operation_state_root(environ)
        / OUTPUT_OPERATION_ADMISSION_RESERVED_TEMP_NAME
    )


def output_operation_lock_path(
    environ: Mapping[str, str] | None = None,
) -> Path:
    return output_operation_state_root(environ) / "locks" / OUTPUT_OPERATION_LOCK_NAME


@contextmanager
def lease_output_operation_admission() -> Iterator[OutputOperationAdmissionLease]:
    """Hold the pre-existing neutral lock without creating directory state."""

    state_root = output_operation_state_root()
    _require_state_root_identity_row_bound(state_root)
    _require_canonical_plain_directory(state_root)
    state_root_identity = path_identity(state_root)
    with _lease_output_operation_admission_for_state_root(
        state_root=state_root,
        state_root_identity=state_root_identity,
    ) as lease:
        yield lease


@contextmanager
def _lease_output_operation_admission_for_state_root(
    *,
    state_root: Path,
    state_root_identity: PathIdentity,
) -> Iterator[OutputOperationAdmissionLease]:
    """Hold the neutral lock under one already bound state-root authority."""

    state_root = Path(state_root)
    _require_state_root_identity_row_bound(state_root)
    _require_canonical_plain_directory(state_root)
    if path_identity(state_root) != state_root_identity:
        raise ValueError("output_operation_state_root_identity_changed")
    locks_root = state_root / "locks"
    _require_canonical_plain_directory(locks_root)
    locks_root_identity = path_identity(locks_root)
    lock_path = locks_root / OUTPUT_OPERATION_LOCK_NAME
    if path_lexists(lock_path):
        lock_identity = _require_empty_plain_lock(
            lock_path,
            expected_parent_identity=locks_root_identity,
        )
    else:
        raise FileNotFoundError(lock_path)
    path_guard = capture_plain_ancestor_guard(lock_path)
    with ExclusiveFileLock(
        lock_path,
        expected_parent_identity=locks_root_identity,
        path_guard=path_guard,
        create_if_missing=False,
    ):
        _require_empty_plain_lock_under_lock(
            lock_path,
            expected_identity=lock_identity,
        )
        if path_identity(state_root) != state_root_identity:
            raise ValueError("output_operation_state_root_identity_changed")
        token = OutputOperationAdmissionLockToken(_TOKEN_AUTHORITY)
        lease = OutputOperationAdmissionLease(
            state_root=state_root,
            state_root_identity=state_root_identity,
            locks_root_identity=locks_root_identity,
            lock_path=lock_path,
            lock_identity=lock_identity,
            lock_token=token,
        )
        with _active_leases_lock:
            _active_leases[id(token)] = (token, lease, get_ident())
        try:
            yield lease
        finally:
            with _active_leases_lock:
                _active_leases.pop(id(token), None)


def observe_output_operation_admission_under_lease(
    lease: OutputOperationAdmissionLease,
) -> OutputOperationAdmissionEvidence | None:
    """Boundedly observe exactly the final, staging, and reserved-temp paths."""

    _require_active_lease(lease)
    _revalidate_lease_filesystem(lease)
    staging_path = lease.state_root / OUTPUT_OPERATION_ADMISSION_STAGING_NAME
    reserved_temp_path = (
        lease.state_root / OUTPUT_OPERATION_ADMISSION_RESERVED_TEMP_NAME
    )
    for residue_path in (staging_path, reserved_temp_path):
        if path_lexists(residue_path):
            _require_plain_file_without_streams(
                residue_path,
                expected_parent_identity=lease.state_root_identity,
            )
            raise ValueError("output_operation_admission_residue_present")
    admission_path = lease.state_root / OUTPUT_OPERATION_ADMISSION_NAME
    if not path_lexists(admission_path):
        return None
    status = plain_file_status(admission_path)
    raw = read_file_no_follow(
        admission_path,
        expected_status=status,
        maximum_size=OUTPUT_OPERATION_ADMISSION_MAX_BYTES,
    )
    require_no_alternate_data_streams(
        admission_path,
        expected_identity=path_identity_from_status(status),
        expected_parent_identity=lease.state_root_identity,
        directory=False,
        expected_size=len(raw),
    )
    document = _load_canonical_document(raw)
    evidence = _parse_admission_document(
        document,
        admission_path=admission_path,
        admission_status=status,
        admission_size=len(raw),
        lease=lease,
    )
    if path_identity(admission_path) != evidence.admission_identity:
        raise ValueError("output_operation_admission_identity_changed")
    _revalidate_lease_filesystem(lease)
    return evidence


def require_output_operation_allows_profile_mutation(
    lease: OutputOperationAdmissionLease,
) -> None:
    if observe_output_operation_admission_under_lease(lease) is not None:
        raise ValueError("output_operation_admission_blocks_profile_mutation")


def require_output_operation_allows_publication(
    *,
    lease: OutputOperationAdmissionLease,
    output_root: Path,
    output_root_identity: PathIdentity | None,
    allowed_exact: OutputOperationAdmissionEvidence | None = None,
) -> None:
    observed = observe_output_operation_admission_under_lease(lease)
    if observed is None:
        if allowed_exact is not None:
            raise ValueError("output_operation_admission_expected_active")
        return
    if allowed_exact is None or observed != allowed_exact:
        raise ValueError("output_operation_admission_blocks_publication")
    if Path(output_root) != observed.output_child_path:
        raise ValueError("output_operation_admission_output_root_mismatch")
    expected_identity = (
        observed.output_child_predecessor_identity
        if observed.output_child_predecessor_state == "existing"
        else None
    )
    if output_root_identity != expected_identity:
        raise ValueError("output_operation_admission_output_identity_mismatch")


def require_output_operation_allows_runtime_mutation(
    *, lease: OutputOperationAdmissionLease
) -> None:
    if observe_output_operation_admission_under_lease(lease) is not None:
        raise ValueError("output_operation_admission_blocks_runtime_mutation")


def _require_active_lease(lease: OutputOperationAdmissionLease) -> None:
    if not isinstance(lease, OutputOperationAdmissionLease):
        raise ValueError("output_operation_admission_lease_invalid")
    token = lease.lock_token
    if not isinstance(token, OutputOperationAdmissionLockToken):
        raise ValueError("output_operation_admission_lease_invalid")
    with _active_leases_lock:
        active = _active_leases.get(id(token))
    if active is None:
        raise ValueError("output_operation_admission_lease_inactive")
    active_token, active_lease, thread_id = active
    if active_token is not token or active_lease is not lease:
        raise ValueError("output_operation_admission_lease_invalid")
    if token._thread_id != thread_id or thread_id != get_ident():
        raise ValueError("output_operation_admission_lease_wrong_thread")


def _revalidate_lease_filesystem(lease: OutputOperationAdmissionLease) -> None:
    _require_canonical_plain_directory(lease.state_root)
    if path_identity(lease.state_root) != lease.state_root_identity:
        raise ValueError("output_operation_state_root_identity_changed")
    locks_root = lease.state_root / "locks"
    _require_canonical_plain_directory(locks_root)
    if path_identity(locks_root) != lease.locks_root_identity:
        raise ValueError("output_operation_locks_root_identity_changed")
    _require_empty_plain_lock_under_lock(
        lease.lock_path,
        expected_identity=lease.lock_identity,
    )


def _require_state_root_identity_row_bound(path: Path) -> None:
    if len(Path(path).parts) > _STATE_ROOT_MAX_IDENTITY_ROWS:
        raise ValueError("filesystem_identity_mapping_ancestor_bound_exceeded")


def _require_canonical_plain_directory(path: Path) -> None:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValueError("filesystem_path_not_absolute")
    _require_windows_safe_absolute_path(
        candidate,
        error="filesystem_windows_namespace_invalid",
    )
    require_plain_directory(candidate)
    require_same_identity_resolution(candidate)
    if candidate.resolve(strict=True) != candidate:
        raise ValueError("filesystem_path_not_canonical")
    identity = path_identity(candidate)
    require_no_alternate_data_streams(
        candidate,
        expected_identity=identity,
        expected_parent_identity=path_identity(candidate.parent),
        directory=True,
    )
    if path_identity(candidate) != identity:
        raise ValueError("filesystem_path_identity_changed")


def _require_empty_plain_lock(
    path: Path,
    *,
    expected_parent_identity: PathIdentity,
) -> PathIdentity:
    status = plain_file_status(path)
    if status.st_size != 0:
        raise ValueError("output_operation_lock_not_empty")
    identity = path_identity_from_status(status)
    _require_lock_without_alternate_data_streams(
        path,
        expected_identity=identity,
        expected_parent_identity=expected_parent_identity,
    )
    return identity


def _require_empty_plain_lock_under_lock(
    path: Path,
    *,
    expected_identity: PathIdentity,
) -> None:
    status = plain_file_status(path)
    if status.st_size != 0:
        raise ValueError("output_operation_lock_not_empty")
    if path_identity_from_status(status) != expected_identity:
        raise ValueError("output_operation_lock_identity_changed")


def _require_plain_file_without_streams(
    path: Path,
    *,
    expected_parent_identity: PathIdentity,
) -> os.stat_result:
    status = plain_file_status(path)
    require_no_alternate_data_streams(
        path,
        expected_identity=path_identity_from_status(status),
        expected_parent_identity=expected_parent_identity,
        directory=False,
        expected_size=status.st_size,
    )
    return status


def _require_lock_without_alternate_data_streams(
    path: Path,
    *,
    expected_identity: PathIdentity,
    expected_parent_identity: PathIdentity,
) -> None:
    deadline = time.monotonic() + _LOCK_STREAM_VALIDATION_TIMEOUT_SECONDS
    while True:
        try:
            require_no_alternate_data_streams(
                path,
                expected_identity=expected_identity,
                expected_parent_identity=expected_parent_identity,
                directory=False,
                expected_size=0,
            )
            return
        except OSError as error:
            remaining = deadline - time.monotonic()
            if (
                os.name != "nt"
                or error.errno not in {32, 33}
                or remaining <= 0
            ):
                raise
            time.sleep(min(0.05, remaining))


def _load_canonical_document(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > OUTPUT_OPERATION_ADMISSION_MAX_BYTES:
        raise ValueError("output_operation_admission_size_invalid")
    if raw.startswith(b"\xef\xbb\xbf") or b"\x00" in raw:
        raise ValueError("output_operation_admission_bytes_invalid")

    def reject_constant(value: str) -> None:
        raise ValueError(f"output_operation_admission_non_finite:{value}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("output_operation_admission_duplicate_key")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("output_operation_admission_json_invalid") from error
    if not isinstance(value, dict):
        raise ValueError("output_operation_admission_root_invalid")
    if _canonical_json(value) != raw:
        raise ValueError("output_operation_admission_not_canonical")
    return value


def _parse_admission_document(
    document: dict[str, Any],
    *,
    admission_path: Path,
    admission_status: os.stat_result,
    admission_size: int,
    lease: OutputOperationAdmissionLease,
) -> OutputOperationAdmissionEvidence:
    if set(document) != OUTPUT_OPERATION_ADMISSION_FIELDS:
        raise ValueError("output_operation_admission_fields_invalid")
    if type(document["schema_version"]) is not int or document[
        "schema_version"
    ] != OUTPUT_OPERATION_ADMISSION_SCHEMA_VERSION:
        raise ValueError("output_operation_admission_schema_invalid")
    if document["record_kind"] != OUTPUT_OPERATION_ADMISSION_KIND:
        raise ValueError("output_operation_admission_kind_invalid")
    if document["state"] != "ACTIVE":
        raise ValueError("output_operation_admission_state_invalid")
    run_id = _require_text_pattern(document["run_id"], _RUN_ID, "run_id")
    expected_session_sha256 = _require_digest(
        document["expected_session_sha256"], "expected_session_sha256"
    )
    operator_profile_sha256 = _require_digest(
        document["operator_profile_sha256"], "operator_profile_sha256"
    )
    content_sha256 = _require_digest(document["content_sha256"], "content_sha256")
    unsigned = dict(document)
    del unsigned["content_sha256"]
    if content_sha256 != "sha256:" + sha256(_canonical_json(unsigned)).hexdigest():
        raise ValueError("output_operation_admission_content_sha256_invalid")

    session_root = _canonical_absolute_path(document["session_root"], "session_root")
    operator_profile_path = _canonical_absolute_path(
        document["operator_profile_path"], "operator_profile_path"
    )
    output_base_root = _canonical_absolute_path(
        document["output_base_root"], "output_base_root"
    )
    output_child_path = _canonical_absolute_path(
        document["output_child_path"], "output_child_path"
    )
    output_bootstrap_lock_path = _canonical_absolute_path(
        document["output_bootstrap_lock_path"], "output_bootstrap_lock_path"
    )
    output_claim_path = _canonical_absolute_path(
        document["output_claim_path"], "output_claim_path"
    )
    if operator_profile_path != lease.state_root / "operator-profile.json":
        raise ValueError("output_operation_admission_profile_path_invalid")
    if output_child_path.parent != output_base_root or not output_child_path.name:
        raise ValueError("output_operation_admission_output_child_invalid")
    if output_claim_path.parent != output_base_root:
        raise ValueError("output_operation_admission_output_claim_invalid")

    predecessor_state = document["output_child_predecessor_state"]
    predecessor_identity_value = document["output_child_predecessor_identity"]
    if predecessor_state == "absent":
        if predecessor_identity_value is not None:
            raise ValueError("output_operation_admission_predecessor_invalid")
        predecessor_identity = None
    elif predecessor_state == "existing":
        predecessor_identity = _identity(predecessor_identity_value, "predecessor")
    else:
        raise ValueError("output_operation_admission_predecessor_invalid")

    state_root_identity = _identity(document["state_root_identity"], "state_root")
    if state_root_identity != lease.state_root_identity:
        raise ValueError("output_operation_admission_state_root_identity_invalid")
    return OutputOperationAdmissionEvidence(
        admission_path=admission_path,
        admission_parent_identity=lease.state_root_identity,
        admission_identity=path_identity_from_status(admission_status),
        admission_size=admission_size,
        admission_sha256=content_sha256,
        state="ACTIVE",
        run_id=run_id,
        session_root=session_root,
        session_root_identity=_identity(
            document["session_root_identity"], "session_root"
        ),
        expected_session_sha256=expected_session_sha256,
        operator_profile_path=operator_profile_path,
        operator_profile_parent_identity=_identity(
            document["operator_profile_parent_identity"], "operator_profile_parent"
        ),
        operator_profile_identity=_identity(
            document["operator_profile_identity"], "operator_profile"
        ),
        operator_profile_sha256=operator_profile_sha256,
        state_root_identity=state_root_identity,
        output_base_root=output_base_root,
        output_base_root_identity=_identity(
            document["output_base_root_identity"], "output_base_root"
        ),
        output_child_path=output_child_path,
        output_child_predecessor_state=predecessor_state,
        output_child_predecessor_identity=predecessor_identity,
        output_bootstrap_lock_path=output_bootstrap_lock_path,
        output_bootstrap_lock_identity=_identity(
            document["output_bootstrap_lock_identity"], "output_bootstrap_lock"
        ),
        output_claim_path=output_claim_path,
    )


def _identity(value: object, field: str) -> PathIdentity:
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(type(item) is not int for item in value)
    ):
        raise ValueError(f"output_operation_admission_{field}_identity_invalid")
    return value[0], value[1], value[2]


def _require_digest(value: object, field: str) -> str:
    return _require_text_pattern(value, _STANDARD_SHA256, field)


def _require_text_pattern(value: object, pattern: re.Pattern[str], field: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ValueError(f"output_operation_admission_{field}_invalid")
    return value


def _canonical_absolute_path(value: object, field: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(f"output_operation_admission_{field}_invalid")
    path = Path(value)
    if (
        not path.is_absolute()
        or os.path.normpath(value) != value
        or str(path) != value
    ):
        raise ValueError(f"output_operation_admission_{field}_invalid")
    return _require_windows_safe_absolute_path(
        path,
        error=f"output_operation_admission_{field}_windows_namespace_invalid",
    )


def _require_windows_safe_absolute_path(path: Path, *, error: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValueError(error)
    if os.name != "nt":
        return candidate
    text = str(candidate)
    lowered = text.casefold()
    if lowered.startswith(("\\\\?\\", "\\\\.\\", "\\??\\")):
        raise ValueError(error)
    drive = candidate.drive
    if drive.startswith("\\\\"):
        authority_components = drive[2:].split("\\")
        if len(authority_components) != 2:
            raise ValueError(error)
        server, share = authority_components
        _require_windows_safe_component(
            server,
            error=error,
            reject_device_name=False,
        )
        _require_windows_safe_component(
            share,
            error=error,
            reject_device_name=False,
        )
        if share.casefold() in _WINDOWS_UNC_IPC_SHARES:
            raise ValueError(error)
    elif re.fullmatch(r"[A-Za-z]:", drive):
        pass
    else:
        raise ValueError(error)
    for component in candidate.parts[1:]:
        _require_windows_safe_component(
            component,
            error=error,
            reject_device_name=True,
        )
    return candidate


def _require_windows_safe_component(
    component: str,
    *,
    error: str,
    reject_device_name: bool,
) -> None:
    if (
        not component
        or component in {".", ".."}
        or component.endswith((".", " "))
        or any(ord(character) < 32 for character in component)
        or any(
            character in _WINDOWS_INVALID_COMPONENT_CHARACTERS
            for character in component
        )
    ):
        raise ValueError(error)
    if reject_device_name:
        device_stem = component.split(".", 1)[0].rstrip(" .").casefold()
        if device_stem in _WINDOWS_RESERVED_NAMES:
            raise ValueError(error)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


__all__ = (
    "OUTPUT_OPERATION_ADMISSION_FIELDS",
    "OUTPUT_OPERATION_ADMISSION_KIND",
    "OUTPUT_OPERATION_ADMISSION_MAX_BYTES",
    "OUTPUT_OPERATION_ADMISSION_NAME",
    "OUTPUT_OPERATION_ADMISSION_RESERVED_TEMP_NAME",
    "OUTPUT_OPERATION_ADMISSION_SCHEMA_VERSION",
    "OUTPUT_OPERATION_ADMISSION_STAGING_NAME",
    "OutputOperationAdmissionEvidence",
    "OutputOperationAdmissionLease",
    "OutputOperationAdmissionLockToken",
    "lease_output_operation_admission",
    "observe_output_operation_admission_under_lease",
    "output_operation_admission_path",
    "output_operation_admission_reserved_temp_path",
    "output_operation_admission_staging_path",
    "output_operation_lock_path",
    "output_operation_state_root",
    "require_output_operation_allows_profile_mutation",
    "require_output_operation_allows_publication",
    "require_output_operation_allows_runtime_mutation",
)
