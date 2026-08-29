"""Crash-recoverable publication of one immutable configure-run revision."""

from __future__ import annotations

import json
import os
import re
import stat
import uuid
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from threading import Lock, get_ident
from typing import Any, Literal

from hsconfig import live_start_session as live_session
from hsconfig import operator_profile as operator_profile_state
from hsconfig import output_operation_admission as output_admission
from hsconfig.atomic_io import (
    AtomicWriteConflictError,
    ExclusiveFileLock,
    FaultHook,
    MaterializedStagingBytes,
    atomic_commit_bound_staging_no_replace,
    atomic_materialize_staging_bytes,
    no_fault,
)
from hsconfig.configure_run_model import (
    RenderedConfigureRun,
)
from hsconfig.current_output import (
    CURRENT_PATH,
    CURRENT_SCHEMA_VERSION,
    OutputPublication,
    output_publication_bytes,
    parse_output_publication,
    resolve_current_publication_unlocked,
    snapshot_and_verify_revision,
)
from hsconfig.live_start_faults import (
    LiveStartFaultHook,
    LiveStartFaultPoint,
    invoke_live_start_fault,
    no_live_start_fault,
)
from hsconfig.live_start_session import (
    LiveStartSession,
    LiveStartSessionLease,
    OutputChildBootstrapAuthorization,
    OutputChildBootstrapPhysicalPostcondition,
    OutputChildBootstrapStepReceipt,
    OutputOperationAdmissionAuthorization,
    OutputOperationAdmissionPhysicalPostcondition,
    OutputOperationAdmissionStepReceipt,
)
from hsconfig.operator_profile import OperatorProfileLease
from hsconfig.package_io import (
    MAX_FILESYSTEM_DIRECTORIES,
    MAX_FILESYSTEM_DEPTH,
    MAX_FILESYSTEM_ENTRIES_PER_DIRECTORY,
    MAX_FILESYSTEM_NODES,
    MAX_RUN_PATH_BYTES,
    FilesystemPathGuard,
    PlainDirectoryMutationGuard,
    bootstrap_plain_child_directory_under_guard,
    capture_plain_ancestor_guard,
    hold_plain_directory,
    path_identity,
    path_identity_from_status,
    path_lexists,
    plain_file_status,
    read_file_no_follow,
    require_no_alternate_data_streams,
    require_plain_directory,
    secure_create_directory,
    secure_open_file_descriptor,
    secure_replace,
    secure_rmdir,
    secure_unlink,
    status_is_reparse,
)
from hsconfig.output_operation_admission import (
    OutputOperationAdmissionEvidence,
    OutputOperationAdmissionLease,
    build_output_operation_admission_bytes,
    lease_output_operation_admission,
    observe_output_operation_admission_under_lease,
    output_operation_admission_path,
    output_operation_admission_reserved_temp_path,
    output_operation_admission_staging_path,
    output_operation_lock_path,
    output_operation_state_root,
    require_output_operation_allows_publication,
)
from hsconfig.package_domain import canonical_relative_path


_TRANSACTION_SCHEMA_VERSION = 1
_LIVE_START_TRANSACTION_SCHEMA_VERSION = 2
_LIVE_START_COMMIT_RECEIPT_SCHEMA_VERSION = 1
_LIVE_START_COMMIT_RECEIPT_KIND = "live_start_current_pointer_commit"
_MAX_TRANSACTION_FILES = 256
_MAX_TRANSACTION_BYTES = 16 * 1024 * 1024
_MAX_TRANSACTION_FILE_BYTES = 1024 * 1024
_TRANSACTION_ID = re.compile(r"^[0-9a-f]{32}$")
_REVISION_NAME = re.compile(r"^sha256-[0-9a-f]{64}$")
_STAGING_NAME = re.compile(r"^\.staging-[0-9a-f]{32}$")
_PHASES = frozenset(
    {
        "prepared",
        "staging_owned",
        "staging_verified",
        "revision_ready",
        "pointer_staging_bound",
        "pointer_committed",
        "cleanup_started",
        "finalized",
    }
)
_JOURNAL_V1_KEYS = frozenset(
    {
        "schema_version",
        "transaction_id",
        "deck_name",
        "deck_fingerprint",
        "content_root_sha256",
        "staging",
        "revision",
        "previous_revision",
        "previous_revision_identity",
        "previous_owner_transaction_id",
        "staging_identity",
        "revision_identity",
        "owns_revision",
        "phase",
    }
)
_JOURNAL_V2_KEYS = _JOURNAL_V1_KEYS | {"live_start_commit_receipt"}
_LIVE_START_COMMIT_RECEIPT_KEYS = frozenset(
    {
        "schema_version",
        "receipt_kind",
        "disposition",
        "expected_session_sha256",
        "operation_admission_identity",
        "operation_admission_sha256",
        "claim_identity",
        "claim_sha256",
        "output_child_identity",
        "pointer_predecessor_identity",
        "pointer_predecessor_size",
        "pointer_predecessor_sha256",
        "pointer_staging_identity",
        "planned_pointer_size",
        "planned_pointer_sha256",
        "owner_journal_predecessor_identity",
        "owner_journal_identity",
        "content_sha256",
    }
)


@dataclass(frozen=True, slots=True)
class PublishedOutput:
    output_root: Path
    revision_root: Path
    package_root: Path
    content_root_sha256: str
    reused_existing_revision: bool


@dataclass(frozen=True, slots=True)
class _PointerSnapshot:
    existed: bool
    content: bytes | None
    identity: tuple[int, int, int, int, int, int] | None


@dataclass(frozen=True, slots=True)
class _LiveStartCommitReceipt:
    schema_version: int
    receipt_kind: str
    disposition: Literal["pointer_staged", "reused_existing"]
    expected_session_sha256: str
    operation_admission_identity: tuple[int, int, int]
    operation_admission_sha256: str
    claim_identity: tuple[int, int, int]
    claim_sha256: str
    output_child_identity: tuple[int, int, int]
    pointer_predecessor_identity: tuple[int, int, int] | None
    pointer_predecessor_size: int | None
    pointer_predecessor_sha256: str | None
    pointer_staging_identity: tuple[int, int, int]
    planned_pointer_size: int
    planned_pointer_sha256: str
    owner_journal_predecessor_identity: tuple[int, int, int] | None
    owner_journal_identity: tuple[int, int, int] | None
    content_sha256: str

    def __post_init__(self) -> None:
        _validate_live_start_commit_receipt(self)


@dataclass(frozen=True, slots=True)
class _LiveStartTempRecoveryAuthority:
    expected_session_sha256: str
    operation_admission_identity: tuple[int, int, int]
    operation_admission_sha256: str
    claim_identity: tuple[int, int, int]
    claim_sha256: str
    output_child_identity: tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class _Transaction:
    schema_version: int
    transaction_id: str
    deck_name: str
    deck_fingerprint: str
    content_root_sha256: str
    staging: str
    revision: str
    previous_revision: str | None
    previous_revision_identity: tuple[int, int, int] | None
    previous_owner_transaction_id: str | None
    staging_identity: tuple[int, int, int] | None
    revision_identity: tuple[int, int, int] | None
    owns_revision: bool
    phase: str
    live_start_commit_receipt: _LiveStartCommitReceipt | None = None

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version
            not in {
                _TRANSACTION_SCHEMA_VERSION,
                _LIVE_START_TRANSACTION_SCHEMA_VERSION,
            }
            or not _TRANSACTION_ID.fullmatch(self.transaction_id)
            or not self.deck_name
            or self.deck_name != self.deck_name.strip()
            or not _is_sha256(self.deck_fingerprint)
            or not _is_sha256(self.content_root_sha256)
            or self.staging
            != f"revisions/.staging-{self.transaction_id}"
            or self.revision
            != f"revisions/sha256-{self.content_root_sha256}"
            or (
                self.previous_revision is not None
                and not _canonical_revision(self.previous_revision)
            )
            or not _identity_or_none(self.previous_revision_identity)
            or (
                self.previous_owner_transaction_id is not None
                and not _TRANSACTION_ID.fullmatch(
                    self.previous_owner_transaction_id
                )
            )
            or not _identity_or_none(self.staging_identity)
            or not _identity_or_none(self.revision_identity)
            or type(self.owns_revision) is not bool
            or self.phase not in _PHASES
            or (
                self.schema_version == _TRANSACTION_SCHEMA_VERSION
                and self.live_start_commit_receipt is not None
            )
            or not _valid_phase_state(self)
        ):
            raise ValueError("publisher_transaction_invalid")


class _LoadedTransactions(list[tuple[Path, _Transaction]]):
    def __init__(self) -> None:
        super().__init__()
        self.identities: dict[Path, tuple[int, int, int]] = {}


_OUTPUT_BOOTSTRAP_TOKEN_AUTHORITY = object()
_OUTPUT_PUBLICATION_AUTHORITY = object()
_OUTPUT_PUBLICATION_PERMIT_AUTHORITY = object()
_OUTPUT_CHILD_CLAIM_MAX_BYTES = 16 * 1024
_active_output_bootstrap_leases: dict[
    int,
    tuple[object, "OutputChildBootstrapLease", int],
] = {}
_active_output_bootstrap_leases_lock = Lock()
_consumed_output_publication_tokens: set[object] = set()
_consumed_output_publication_tokens_lock = Lock()


class _OutputChildBootstrapToken:
    __slots__ = ("nonce", "thread_id")

    def __init__(self, authority: object | None = None) -> None:
        if authority is not _OUTPUT_BOOTSTRAP_TOKEN_AUTHORITY:
            raise TypeError("output_child_bootstrap_token_not_constructible")
        self.nonce = object()
        self.thread_id = get_ident()


@dataclass(frozen=True, slots=True, init=False)
class OutputChildBootstrapLease:
    output_root: Path
    state_root: Path
    state_root_identity: tuple[int, int, int]
    locks_root_identity: tuple[int, int, int]
    lock_path: Path
    lock_identity: tuple[int, int, int]
    lock_token: _OutputChildBootstrapToken

    def __init__(
        self,
        *,
        output_root: Path,
        state_root: Path,
        state_root_identity: tuple[int, int, int],
        locks_root_identity: tuple[int, int, int],
        lock_path: Path,
        lock_identity: tuple[int, int, int],
        lock_token: _OutputChildBootstrapToken,
        authority: object | None = None,
    ) -> None:
        if authority is not _OUTPUT_BOOTSTRAP_TOKEN_AUTHORITY:
            raise TypeError("output_child_bootstrap_lease_not_constructible")
        object.__setattr__(self, "output_root", output_root)
        object.__setattr__(self, "state_root", state_root)
        object.__setattr__(self, "state_root_identity", state_root_identity)
        object.__setattr__(self, "locks_root_identity", locks_root_identity)
        object.__setattr__(self, "lock_path", lock_path)
        object.__setattr__(self, "lock_identity", lock_identity)
        object.__setattr__(self, "lock_token", lock_token)


class OutputPublicationAuthorization:
    __slots__ = (
        "bootstrap_lease",
        "claim_identity",
        "claim_sha256",
        "guard",
        "kind",
        "operation_admission",
        "operation_lease",
        "profile_lease",
        "session_lease",
        "session_sha256",
        "thread_id",
        "_token",
    )

    def __init__(
        self,
        *,
        bootstrap_lease: OutputChildBootstrapLease,
        claim_identity: tuple[int, int, int] | None,
        claim_sha256: str | None,
        guard: PlainDirectoryMutationGuard,
        kind: str,
        operation_admission: OutputOperationAdmissionEvidence | None,
        operation_lease: OutputOperationAdmissionLease,
        profile_lease: object | None,
        session_lease: object | None,
        session_sha256: str | None,
        authority: object | None = None,
    ) -> None:
        if authority is not _OUTPUT_PUBLICATION_AUTHORITY:
            raise TypeError("output_publication_authorization_not_constructible")
        self.bootstrap_lease = bootstrap_lease
        self.claim_identity = claim_identity
        self.claim_sha256 = claim_sha256
        self.guard = guard
        self.kind = kind
        self.operation_admission = operation_admission
        self.operation_lease = operation_lease
        self.profile_lease = profile_lease
        self.session_lease = session_lease
        self.session_sha256 = session_sha256
        self.thread_id = get_ident()
        self._token = object()

    @property
    def used(self) -> bool:
        with _consumed_output_publication_tokens_lock:
            return self._token in _consumed_output_publication_tokens


def _consume_output_publication_authorization(
    authorization: OutputPublicationAuthorization,
) -> None:
    with _consumed_output_publication_tokens_lock:
        if authorization._token in _consumed_output_publication_tokens:
            raise ValueError("output_publication_authorization_reused")
        _consumed_output_publication_tokens.add(authorization._token)


class OutputPublicationPermit:
    __slots__ = ("authorization", "active", "published")

    def __init__(
        self,
        authorization: OutputPublicationAuthorization,
        authority: object | None = None,
    ) -> None:
        if authority is not _OUTPUT_PUBLICATION_PERMIT_AUTHORITY:
            raise TypeError("output_publication_permit_not_constructible")
        self.authorization = authorization
        self.active = True
        self.published: PublishedOutput | None = None


@dataclass(frozen=True, slots=True)
class OutputOperationAdmissionPhysicalStep:
    staging: MaterializedStagingBytes | None
    evidence: OutputOperationAdmissionEvidence | None
    step_receipt: OutputOperationAdmissionStepReceipt


OutputOperationAdmissionReleaseDisposition = Literal[
    "old_unlinked",
    "already_absent",
    "valid_foreign_successor",
]


@dataclass(frozen=True, slots=True)
class OutputChildBootstrapPhysicalStep:
    claim_staging: MaterializedStagingBytes | None
    claim_identity: tuple[int, int, int] | None
    output_child_identity: tuple[int, int, int] | None
    object_was_already_in_exact_postcondition: bool
    step_receipt: OutputChildBootstrapStepReceipt


def output_child_claim_path(output_root: Path) -> Path:
    root = _canonical_output_root(output_root)
    component_digest = sha256(root.name.encode("utf-8")).hexdigest()
    return root.parent / (
        f".hsconfig-live-start-output-child-{component_digest}.claim.json"
    )


def output_child_claim_staging_path(output_root: Path) -> Path:
    claim = output_child_claim_path(output_root)
    return claim.with_name(f"{claim.name}.staged")


def output_child_claim_staging_inner_temp_path(output_root: Path) -> Path:
    staging = output_child_claim_staging_path(output_root)
    return staging.with_name(f".{staging.name}.live-start-atomic.tmp")


def build_output_child_claim_bytes(
    *,
    run_id: str,
    session_root: Path,
    session_root_identity: tuple[int, int, int],
    expected_session_sha256: str,
    output_base_path: Path,
    output_base_identity: tuple[int, int, int],
    output_child_path: Path,
    predecessor_state: Literal["absent", "existing"],
    predecessor_output_child_identity: tuple[int, int, int] | None,
) -> bytes:
    if predecessor_state == "absent":
        if predecessor_output_child_identity is not None:
            raise ValueError("output_child_claim_predecessor_invalid")
    elif predecessor_state == "existing":
        if predecessor_output_child_identity is None:
            raise ValueError("output_child_claim_predecessor_invalid")
    else:
        raise ValueError("output_child_claim_predecessor_invalid")
    unsigned: dict[str, Any] = {
        "schema_version": live_session.LIVE_START_OUTPUT_CHILD_CLAIM_SCHEMA_VERSION,
        "claim_kind": live_session.LIVE_START_OUTPUT_CHILD_CLAIM_KIND,
        "run_id": run_id,
        "session_root": str(Path(session_root).absolute()),
        "session_root_identity": list(session_root_identity),
        "expected_session_sha256": expected_session_sha256,
        "output_base_path": str(Path(output_base_path).absolute()),
        "output_base_identity": list(output_base_identity),
        "output_child_path": str(Path(output_child_path).absolute()),
        "predecessor_state": predecessor_state,
        "predecessor_output_child_identity": (
            None
            if predecessor_output_child_identity is None
            else list(predecessor_output_child_identity)
        ),
    }
    unsigned_raw = _canonical_json_bytes(unsigned)
    document = {
        **unsigned,
        "content_sha256": "sha256:" + sha256(unsigned_raw).hexdigest(),
    }
    raw = _canonical_json_bytes(document)
    if len(raw) > live_session.LIVE_START_OUTPUT_CHILD_CLAIM_MAX_BYTES:
        raise ValueError("output_child_claim_size_invalid")
    return raw


def _load_output_child_claim_bytes(raw: bytes) -> dict[str, Any]:
    if (
        not isinstance(raw, bytes)
        or not raw
        or len(raw) > live_session.LIVE_START_OUTPUT_CHILD_CLAIM_MAX_BYTES
    ):
        raise ValueError("output_child_claim_bytes_invalid")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("output_child_claim_json_invalid") from error
    if not isinstance(value, dict) or _canonical_json_bytes(value) != raw:
        raise ValueError("output_child_claim_not_canonical")
    expected_fields = {
        "schema_version",
        "claim_kind",
        "run_id",
        "session_root",
        "session_root_identity",
        "expected_session_sha256",
        "output_base_path",
        "output_base_identity",
        "output_child_path",
        "predecessor_state",
        "predecessor_output_child_identity",
        "content_sha256",
    }
    if set(value) != expected_fields:
        raise ValueError("output_child_claim_fields_invalid")
    claimed = value["content_sha256"]
    unsigned = dict(value)
    unsigned.pop("content_sha256")
    if (
        claimed
        != "sha256:" + sha256(_canonical_json_bytes(unsigned)).hexdigest()
        or build_output_child_claim_bytes(
            run_id=value["run_id"],
            session_root=Path(value["session_root"]),
            session_root_identity=tuple(value["session_root_identity"]),
            expected_session_sha256=value["expected_session_sha256"],
            output_base_path=Path(value["output_base_path"]),
            output_base_identity=tuple(value["output_base_identity"]),
            output_child_path=Path(value["output_child_path"]),
            predecessor_state=value["predecessor_state"],
            predecessor_output_child_identity=(
                None
                if value["predecessor_output_child_identity"] is None
                else tuple(value["predecessor_output_child_identity"])
            ),
        )
        != raw
    ):
        raise ValueError("output_child_claim_content_sha256_invalid")
    return value


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def output_child_bootstrap_lock_path(output_root: Path) -> Path:
    canonical = str(_canonical_output_root(output_root)).encode("utf-8")
    digest = sha256(canonical).hexdigest()
    return output_operation_state_root() / "locks" / f"output-child-{digest}.lock"


def _canonical_output_root(output_root: Path) -> Path:
    root = Path(output_root)
    if not root.is_absolute():
        root = root.absolute()
    return root


def _bootstrap_neutral_output_locks(*, output_root: Path | None = None) -> None:
    local_app_data = output_operation_state_root().parent
    require_plain_directory(local_app_data)
    with hold_plain_directory(local_app_data) as local_guard:
        state_identity = bootstrap_plain_child_directory_under_guard(
            parent_guard=local_guard,
            child_name="HSConfig",
        )
    state_root = output_operation_state_root()
    with hold_plain_directory(
        state_root,
        expected_identity=state_identity,
    ) as state_guard:
        locks_identity = bootstrap_plain_child_directory_under_guard(
            parent_guard=state_guard,
            child_name="locks",
        )
    with hold_plain_directory(
        state_root / "locks",
        expected_identity=locks_identity,
    ) as locks_guard:
        _create_or_require_empty_lock(
            locks_guard,
            output_operation_lock_path().name,
        )
        if output_root is not None:
            _create_or_require_empty_lock(
                locks_guard,
                output_child_bootstrap_lock_path(output_root).name,
            )


def _create_or_require_empty_lock(
    parent: PlainDirectoryMutationGuard,
    name: str,
) -> tuple[int, int, int]:
    try:
        descriptor = parent.open_file(name, create=True, write=True)
    except FileExistsError:
        descriptor = parent.open_file(name, create=False, write=False)
    try:
        status = os.fstat(descriptor)
        if status.st_size != 0 or status.st_nlink != 1:
            raise ValueError("output_publication_lock_invalid")
        identity = path_identity_from_status(status)
    finally:
        os.close(descriptor)
    parent.validate()
    return identity


@contextmanager
def lease_output_child_bootstrap(
    *, output_root: Path
) -> Iterator[OutputChildBootstrapLease]:
    root = _canonical_output_root(output_root)
    lock_path = output_child_bootstrap_lock_path(root)
    locks_root = lock_path.parent
    locks_identity = path_identity(locks_root)
    lock_status = plain_file_status(lock_path)
    if lock_status.st_size != 0:
        raise ValueError("output_child_bootstrap_lock_not_empty")
    lock_identity = path_identity_from_status(lock_status)
    with ExclusiveFileLock(
        lock_path,
        expected_parent_identity=locks_identity,
        create_if_missing=False,
    ):
        if path_identity(lock_path) != lock_identity:
            raise ValueError("output_child_bootstrap_lock_identity_changed")
        token = _OutputChildBootstrapToken(_OUTPUT_BOOTSTRAP_TOKEN_AUTHORITY)
        lease = OutputChildBootstrapLease(
            output_root=root,
            state_root=output_operation_state_root(),
            state_root_identity=path_identity(output_operation_state_root()),
            locks_root_identity=locks_identity,
            lock_path=lock_path,
            lock_identity=lock_identity,
            lock_token=token,
            authority=_OUTPUT_BOOTSTRAP_TOKEN_AUTHORITY,
        )
        with _active_output_bootstrap_leases_lock:
            _active_output_bootstrap_leases[id(token)] = (
                token.nonce,
                lease,
                get_ident(),
            )
        try:
            yield lease
        finally:
            with _active_output_bootstrap_leases_lock:
                _active_output_bootstrap_leases.pop(id(token), None)


def _require_active_output_bootstrap_lease(
    lease: OutputChildBootstrapLease,
) -> None:
    if not isinstance(lease, OutputChildBootstrapLease):
        raise ValueError("output_publication_bootstrap_lease_invalid")
    token = lease.lock_token
    with _active_output_bootstrap_leases_lock:
        active = _active_output_bootstrap_leases.get(id(token))
    if active is None:
        raise ValueError("output_publication_bootstrap_lease_inactive")
    if active[0] is not token.nonce or active[1] is not lease:
        raise ValueError("output_publication_bootstrap_lease_invalid")
    if active[2] != get_ident():
        raise ValueError("output_publication_bootstrap_lease_cross_thread")
    if (
        path_identity(lease.state_root) != lease.state_root_identity
        or path_identity(lease.lock_path.parent) != lease.locks_root_identity
        or path_identity(lease.lock_path) != lease.lock_identity
        or lease.lock_path != output_child_bootstrap_lock_path(lease.output_root)
    ):
        raise ValueError("output_publication_bootstrap_lease_changed")


def _require_plain_file_no_ads(
    path: Path,
    status: os.stat_result,
) -> None:
    require_no_alternate_data_streams(
        path,
        expected_identity=path_identity_from_status(status),
        expected_parent_identity=path_identity(path.parent),
        directory=False,
        expected_size=status.st_size,
    )


def _claim_fingerprint(
    output_root: Path,
) -> tuple[tuple[int, int, int], str] | None:
    claim = output_child_claim_path(output_root)
    if not path_lexists(claim):
        return None
    status = plain_file_status(claim)
    _require_plain_file_no_ads(claim, status)
    raw = read_file_no_follow(
        claim,
        expected_status=status,
        maximum_size=_OUTPUT_CHILD_CLAIM_MAX_BYTES,
    )
    return path_identity_from_status(status), "sha256:" + sha256(raw).hexdigest()


def _admission_raw_sha256(
    evidence: OutputOperationAdmissionEvidence,
) -> str:
    status = plain_file_status(evidence.admission_path)
    _require_plain_file_no_ads(evidence.admission_path, status)
    if path_identity_from_status(status) != evidence.admission_identity:
        raise ValueError("output_operation_admission_identity_changed")
    raw = read_file_no_follow(
        evidence.admission_path,
        expected_status=status,
        maximum_size=output_admission.OUTPUT_OPERATION_ADMISSION_MAX_BYTES,
    )
    if len(raw) != evidence.admission_size:
        raise ValueError("output_operation_admission_size_changed")
    return "sha256:" + sha256(raw).hexdigest()


def _require_active_operation_context(
    operation_lease: OutputOperationAdmissionLease,
) -> None:
    output_admission._require_active_lease(operation_lease)
    output_admission._revalidate_lease_filesystem(operation_lease)


def _remove_unbound_plain_file(
    path: Path,
    *,
    expected_parent_identity: tuple[int, int, int],
    maximum_size: int,
) -> None:
    if not path_lexists(path):
        return
    status = plain_file_status(path)
    _require_plain_file_no_ads(path, status)
    read_file_no_follow(
        path,
        expected_status=status,
        maximum_size=maximum_size,
    )
    secure_unlink(
        path,
        expected_identity=path_identity_from_status(status),
        expected_parent_identity=expected_parent_identity,
        missing_ok=False,
    )


def _operation_admission_payload(
    *,
    pending: Mapping[str, Any],
    session_lease: LiveStartSessionLease,
    profile_lease: OperatorProfileLease,
) -> bytes:
    operator_profile_state._require_active_lease(profile_lease)
    profile = profile_lease.profile
    return build_output_operation_admission_bytes(
        run_id=str(pending["run_id"]),
        session_root=session_lease.session_root,
        session_root_identity=session_lease.session_root_identity,
        expected_session_sha256=str(pending["expected_session_sha256"]),
        operator_profile=profile,
        operator_profile_path=profile_lease.profile_path,
        operator_profile_parent_identity=profile_lease.profile_parent_identity,
        operator_profile_identity=profile_lease.profile_identity,
        state_root_identity=tuple(
            pending["output_operation_admission_parent_identity"]
        ),
        output_base_root=Path(str(pending["output_base_path"])),
        output_base_root_identity=tuple(pending["output_base_identity"]),
        output_child_path=Path(str(pending["output_child_path"])),
        output_child_predecessor_state=str(
            pending["output_child_predecessor_state"]
        ),
        output_child_predecessor_identity=(
            None
            if pending["output_child_predecessor_identity"] is None
            else tuple(pending["output_child_predecessor_identity"])
        ),
        output_bootstrap_lock_path=Path(
            str(pending["output_bootstrap_lock_path"])
        ),
        output_bootstrap_lock_identity=tuple(
            pending["output_bootstrap_lock_identity"]
        ),
        output_claim_path=output_child_claim_path(
            Path(str(pending["output_child_path"]))
        ),
    )


def _output_operation_binding(
    evidence: OutputOperationAdmissionEvidence,
    *,
    raw_sha256: str,
) -> Mapping[str, Any]:
    return live_session.seal_embedded_document(
        "output_operation_admission_binding",
        {
            "schema_version": (
                live_session.LIVE_START_OUTPUT_OPERATION_ADMISSION_BINDING_SCHEMA_VERSION
            ),
            "binding_kind": (
                live_session.LIVE_START_OUTPUT_OPERATION_ADMISSION_BINDING_KIND
            ),
            "state": "ACTIVE",
            "release_handoff_kind": None,
            "admission_path": str(evidence.admission_path),
            "admission_parent_identity": evidence.admission_parent_identity,
            "admission_identity": evidence.admission_identity,
            "admission_size": evidence.admission_size,
            "admission_sha256": raw_sha256,
            "run_id": evidence.run_id,
            "session_root": str(evidence.session_root),
            "session_root_identity": evidence.session_root_identity,
            "expected_session_sha256": evidence.expected_session_sha256,
            "operator_profile_path": str(evidence.operator_profile_path),
            "operator_profile_parent_identity": (
                evidence.operator_profile_parent_identity
            ),
            "operator_profile_identity": evidence.operator_profile_identity,
            "operator_profile_sha256": evidence.operator_profile_sha256,
            "state_root_identity": evidence.state_root_identity,
            "output_base_root": str(evidence.output_base_root),
            "output_base_root_identity": evidence.output_base_root_identity,
            "output_child_path": str(evidence.output_child_path),
            "output_child_predecessor_state": (
                evidence.output_child_predecessor_state
            ),
            "output_child_predecessor_identity": (
                evidence.output_child_predecessor_identity
            ),
            "output_bootstrap_lock_path": str(
                evidence.output_bootstrap_lock_path
            ),
            "output_bootstrap_lock_identity": (
                evidence.output_bootstrap_lock_identity
            ),
            "output_claim_path": str(evidence.output_claim_path),
            "handoff_runtime_admission_path": None,
            "handoff_runtime_admission_parent_identity": None,
            "handoff_runtime_admission_identity": None,
            "handoff_runtime_admission_sha256": None,
        },
    )


def publish_output_operation_admission_under_lease(
    *,
    operation_lease: OutputOperationAdmissionLease,
    bootstrap_lease: OutputChildBootstrapLease,
    output_base_guard: PlainDirectoryMutationGuard,
    session_lease: LiveStartSessionLease,
    expected_operation_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    admission_authorization: OutputOperationAdmissionAuthorization,
    fault_hook: LiveStartFaultHook = no_live_start_fault,
) -> OutputOperationAdmissionPhysicalStep:
    action = admission_authorization._opaque.action
    staging_result: MaterializedStagingBytes | None = None
    observed_evidence: OutputOperationAdmissionEvidence | None = None

    def perform() -> OutputOperationAdmissionPhysicalPostcondition:
        nonlocal staging_result, observed_evidence
        _require_active_operation_context(operation_lease)
        _require_active_output_bootstrap_lease(bootstrap_lease)
        output_base_guard.validate()
        current = live_session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        if current.content_sha256 != expected_operation_session.content_sha256:
            raise live_session.SessionConflictError(
                "live_start_output_operation_cursor_stale"
            )
        pending = current.pending_transition
        if not isinstance(pending, Mapping):
            raise live_session.SessionConflictError(
                "live_start_output_operation_cursor_invalid"
            )
        if (
            output_base_guard.path != Path(str(pending["output_base_path"]))
            or output_base_guard.identity
            != tuple(pending["output_base_identity"])
            or bootstrap_lease.lock_path
            != Path(str(pending["output_bootstrap_lock_path"]))
            or bootstrap_lease.lock_identity
            != tuple(pending["output_bootstrap_lock_identity"])
        ):
            raise ValueError("live_start_output_operation_capability_changed")
        payload = _operation_admission_payload(
            pending=pending,
            session_lease=session_lease,
            profile_lease=profile_lease,
        )
        external = pending["external_file_action"]
        final_path = Path(str(external["final_path"]))
        staging_path = Path(str(external["staging_path"]))
        inner_path = Path(str(external["inner_temp_path"]))
        parent_identity = tuple(external["parent_identity"])
        if (
            len(payload) != external["planned_successor_size"]
            or "sha256:" + sha256(payload).hexdigest()
            != external["planned_successor_sha256"]
            or final_path != output_operation_admission_path()
            or staging_path != output_operation_admission_staging_path()
            or inner_path != output_operation_admission_reserved_temp_path()
            or parent_identity != operation_lease.state_root_identity
        ):
            raise ValueError("live_start_output_operation_plan_changed")
        if action == "retire_unbound_output_operation_admission_staging":
            if path_lexists(final_path):
                raise ValueError("live_start_output_operation_direct_final_invalid")
            _remove_unbound_plain_file(
                inner_path,
                expected_parent_identity=parent_identity,
                maximum_size=output_admission.OUTPUT_OPERATION_ADMISSION_MAX_BYTES,
            )
            _remove_unbound_plain_file(
                staging_path,
                expected_parent_identity=parent_identity,
                maximum_size=output_admission.OUTPUT_OPERATION_ADMISSION_MAX_BYTES,
            )
            evidence: dict[str, Any] = {
                "final_absent": True,
                "staging_absent": True,
                "inner_temp_absent": True,
            }
        elif action == "materialize_output_operation_admission_staging":
            if path_lexists(final_path):
                raise ValueError("live_start_output_operation_direct_final_invalid")

            def materialized_fault(point: str) -> None:
                if point != "after_staging_flush_before_identity_return":
                    raise AtomicWriteConflictError(
                        "live_start_output_operation_fault_invalid"
                    )
                invoke_live_start_fault(
                    fault_hook,
                    LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS,
                )

            staging_result = atomic_materialize_staging_bytes(
                staging_path=staging_path,
                inner_temp_path=inner_path,
                payload=payload,
                expected_parent_identity=parent_identity,
                maximum_size=output_admission.OUTPUT_OPERATION_ADMISSION_MAX_BYTES,
                fault_hook=materialized_fault,
            )
            evidence = {
                "staging_identity": staging_result.identity,
                "staging_size": staging_result.size,
                "staging_sha256": staging_result.sha256,
            }
        elif action == "commit_bound_output_operation_admission":
            expected_identity = tuple(external["staging_identity"])

            def committed_fault(point: str) -> None:
                if point == "after_bound_staging_posix_link_before_unlink":
                    invoke_live_start_fault(
                        fault_hook,
                        LiveStartFaultPoint.AFTER_BOUND_STAGING_POSIX_LINK_BEFORE_UNLINK,
                    )
                elif point == "after_bound_staging_commit_before_return":
                    invoke_live_start_fault(
                        fault_hook,
                        LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_BOUND_COMMIT_BEFORE_CAS,
                    )
                else:
                    raise AtomicWriteConflictError(
                        "live_start_output_operation_fault_invalid"
                    )

            committed = atomic_commit_bound_staging_no_replace(
                path=final_path,
                staging_path=staging_path,
                expected_staging_identity=expected_identity,
                expected_size=int(external["staging_size"]),
                expected_sha256=str(external["staging_sha256"]),
                expected_parent_identity=parent_identity,
                fault_hook=committed_fault,
            )
            final_status = plain_file_status(final_path)
            _require_plain_file_no_ads(final_path, final_status)
            raw = read_file_no_follow(
                final_path,
                expected_status=final_status,
                maximum_size=output_admission.OUTPUT_OPERATION_ADMISSION_MAX_BYTES,
            )
            if committed.identity != expected_identity or raw != payload:
                raise ValueError("live_start_output_operation_commit_changed")
            observed_evidence = observe_output_operation_admission_under_lease(
                operation_lease
            )
            if observed_evidence is None:
                raise ValueError("live_start_output_operation_missing")
            evidence = {
                "binding": _output_operation_binding(
                    observed_evidence,
                    raw_sha256="sha256:" + sha256(raw).hexdigest(),
                )
            }
        else:
            raise ValueError("live_start_output_operation_action_invalid")
        return OutputOperationAdmissionPhysicalPostcondition(
            action=action,
            evidence=evidence,
        )

    receipt = live_session._execute_output_operation_admission_physical_step(
        admission_authorization=admission_authorization,
        action=action,
        physical_action=perform,
    )
    return OutputOperationAdmissionPhysicalStep(
        staging=staging_result,
        evidence=observed_evidence,
        step_receipt=receipt,
    )


_CONTROLLED_OUTPUT_CHILD_MTIME_NS = 946_684_800_000_000_000


def _claim_payload_from_pending(
    *,
    pending: Mapping[str, Any],
    session_lease: LiveStartSessionLease,
) -> bytes:
    return build_output_child_claim_bytes(
        run_id=str(pending["run_id"]),
        session_root=session_lease.session_root,
        session_root_identity=session_lease.session_root_identity,
        expected_session_sha256=str(pending["expected_session_sha256"]),
        output_base_path=Path(str(pending["output_base_path"])),
        output_base_identity=tuple(pending["output_base_identity"]),
        output_child_path=Path(str(pending["output_child_path"])),
        predecessor_state=str(pending["output_child_predecessor_state"]),
        predecessor_output_child_identity=(
            None
            if pending["output_child_predecessor_identity"] is None
            else tuple(pending["output_child_predecessor_identity"])
        ),
    )


def _read_exact_claim(
    path: Path,
    *,
    expected_parent_identity: tuple[int, int, int],
    expected_identity: tuple[int, int, int] | None = None,
    expected_sha256: str | None = None,
) -> tuple[bytes, tuple[int, int, int], dict[str, Any]]:
    if path_identity(path.parent) != expected_parent_identity:
        raise ValueError("live_start_output_claim_parent_identity_changed")
    status = plain_file_status(path)
    _require_plain_file_no_ads(path, status)
    identity = path_identity_from_status(status)
    raw = read_file_no_follow(
        path,
        expected_status=status,
        maximum_size=live_session.LIVE_START_OUTPUT_CHILD_CLAIM_MAX_BYTES,
    )
    digest = "sha256:" + sha256(raw).hexdigest()
    if (
        expected_identity is not None
        and identity != expected_identity
        or expected_sha256 is not None
        and digest != expected_sha256
    ):
        raise ValueError("live_start_output_claim_identity_changed")
    return raw, identity, _load_output_child_claim_bytes(raw)


def _output_child_binding(
    *,
    current: LiveStartSession,
    pending: Mapping[str, Any],
    output_child_identity: tuple[int, int, int],
) -> Mapping[str, Any]:
    return live_session.seal_embedded_document(
        "output_child_binding",
        {
            "schema_version": live_session.LIVE_START_OUTPUT_CHILD_BINDING_SCHEMA_VERSION,
            "binding_kind": live_session.LIVE_START_OUTPUT_CHILD_BINDING_KIND,
            "run_id": current.run_id,
            "output_base_path": pending["output_base_path"],
            "output_base_identity": pending["output_base_identity"],
            "output_child_path": pending["output_child_path"],
            "output_child_identity": output_child_identity,
            "predecessor_state": pending["output_child_predecessor_state"],
            "predecessor_output_child_identity": pending[
                "output_child_predecessor_identity"
            ],
            "claim_path": pending["output_claim_path"],
            "claim_parent_identity": pending["output_claim_parent_identity"],
            "claim_identity": pending["output_claim_identity"],
            "claim_sha256": pending["output_claim_sha256"],
            "claim_state": "ACTIVE",
        },
    )


def perform_output_child_bootstrap_step_under_guards(
    *,
    session_lease: LiveStartSessionLease,
    expected_bootstrap_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
    bootstrap_lease: OutputChildBootstrapLease,
    output_base_guard: PlainDirectoryMutationGuard,
    bootstrap_authorization: OutputChildBootstrapAuthorization,
    fault_hook: LiveStartFaultHook = no_live_start_fault,
) -> OutputChildBootstrapPhysicalStep:
    action = bootstrap_authorization._opaque.action
    claim_staging: MaterializedStagingBytes | None = None
    claim_identity: tuple[int, int, int] | None = None
    child_identity: tuple[int, int, int] | None = None
    already_exact = False

    def perform() -> OutputChildBootstrapPhysicalPostcondition:
        nonlocal claim_staging, claim_identity, child_identity, already_exact
        operator_profile_state._require_active_lease(profile_lease)
        _require_active_output_bootstrap_lease(bootstrap_lease)
        output_base_guard.validate()
        current = live_session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
        if current.content_sha256 != expected_bootstrap_session.content_sha256:
            raise live_session.SessionConflictError(
                "live_start_output_bootstrap_cursor_stale"
            )
        pending = current.pending_transition
        if not isinstance(pending, Mapping):
            raise live_session.SessionConflictError(
                "live_start_output_bootstrap_cursor_invalid"
            )
        if (
            output_base_guard.path != Path(str(pending["output_base_path"]))
            or output_base_guard.identity
            != tuple(pending["output_base_identity"])
            or bootstrap_lease.output_root
            != Path(str(pending["output_child_path"]))
        ):
            raise ValueError("live_start_output_bootstrap_capability_changed")
        operation = current.output_operation_admission_binding
        if (
            not isinstance(operation, Mapping)
            or operation.get("state") != "ACTIVE"
            or operation.get("output_bootstrap_lock_path")
            != str(bootstrap_lease.lock_path)
            or tuple(operation.get("output_bootstrap_lock_identity", ()))
            != bootstrap_lease.lock_identity
        ):
            raise ValueError("live_start_output_operation_binding_changed")
        output_child = Path(str(pending["output_child_path"]))
        claim_path = Path(str(pending["output_claim_path"]))
        claim_parent_identity = tuple(pending["output_claim_parent_identity"])

        if pending["operation"] == "bootstrap_output_child":
            payload = _claim_payload_from_pending(
                pending=pending,
                session_lease=session_lease,
            )
        else:
            payload = b""
        if action in {
            "retire_unbound_claim_staging",
            "materialize_claim_staging",
            "commit_bound_claim",
        }:
            external = pending["external_file_action"]
            final_path = Path(str(external["final_path"]))
            staging_path = Path(str(external["staging_path"]))
            inner_path = Path(str(external["inner_temp_path"]))
            parent_identity = tuple(external["parent_identity"])
            if (
                final_path != claim_path
                or staging_path != output_child_claim_staging_path(output_child)
                or inner_path
                != output_child_claim_staging_inner_temp_path(output_child)
                or parent_identity != claim_parent_identity
                or len(payload) != external["planned_successor_size"]
                or "sha256:" + sha256(payload).hexdigest()
                != external["planned_successor_sha256"]
            ):
                raise ValueError("live_start_output_claim_plan_changed")
        if action == "retire_unbound_claim_staging":
            if path_lexists(claim_path):
                raise ValueError("live_start_output_claim_direct_final_invalid")
            _remove_unbound_plain_file(
                inner_path,
                expected_parent_identity=parent_identity,
                maximum_size=live_session.LIVE_START_OUTPUT_CHILD_CLAIM_MAX_BYTES,
            )
            _remove_unbound_plain_file(
                staging_path,
                expected_parent_identity=parent_identity,
                maximum_size=live_session.LIVE_START_OUTPUT_CHILD_CLAIM_MAX_BYTES,
            )
            evidence: dict[str, Any] = {
                "final_absent": True,
                "staging_absent": True,
                "inner_temp_absent": True,
            }
        elif action == "materialize_claim_staging":
            if path_lexists(claim_path):
                raise ValueError("live_start_output_claim_direct_final_invalid")

            def materialized_fault(point: str) -> None:
                if point != "after_staging_flush_before_identity_return":
                    raise AtomicWriteConflictError(
                        "live_start_output_claim_fault_invalid"
                    )
                invoke_live_start_fault(
                    fault_hook,
                    LiveStartFaultPoint.AFTER_OUTPUT_CHILD_CLAIM_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS,
                )

            claim_staging = atomic_materialize_staging_bytes(
                staging_path=staging_path,
                inner_temp_path=inner_path,
                payload=payload,
                expected_parent_identity=parent_identity,
                maximum_size=live_session.LIVE_START_OUTPUT_CHILD_CLAIM_MAX_BYTES,
                fault_hook=materialized_fault,
            )
            evidence = {
                "staging_identity": claim_staging.identity,
                "staging_size": claim_staging.size,
                "staging_sha256": claim_staging.sha256,
            }
        elif action == "commit_bound_claim":
            expected_identity = tuple(external["staging_identity"])

            def committed_fault(point: str) -> None:
                if point == "after_bound_staging_posix_link_before_unlink":
                    invoke_live_start_fault(
                        fault_hook,
                        LiveStartFaultPoint.AFTER_BOUND_STAGING_POSIX_LINK_BEFORE_UNLINK,
                    )
                elif point == "after_bound_staging_commit_before_return":
                    invoke_live_start_fault(
                        fault_hook,
                        LiveStartFaultPoint.AFTER_OUTPUT_CHILD_CLAIM_BOUND_COMMIT_BEFORE_CAS,
                    )
                else:
                    raise AtomicWriteConflictError(
                        "live_start_output_claim_fault_invalid"
                    )

            committed = atomic_commit_bound_staging_no_replace(
                path=claim_path,
                staging_path=staging_path,
                expected_staging_identity=expected_identity,
                expected_size=int(external["staging_size"]),
                expected_sha256=str(external["staging_sha256"]),
                expected_parent_identity=parent_identity,
                fault_hook=committed_fault,
            )
            raw, claim_identity, _document = _read_exact_claim(
                claim_path,
                expected_parent_identity=parent_identity,
                expected_identity=expected_identity,
                expected_sha256=str(external["staging_sha256"]),
            )
            if committed.identity != claim_identity or raw != payload:
                raise ValueError("live_start_output_claim_commit_changed")
            evidence = {
                "claim_identity": claim_identity,
                "claim_sha256": "sha256:" + sha256(raw).hexdigest(),
            }
        elif action in {"bind_existing_child", "create_output_child"}:
            raw, claim_identity, claim_document = _read_exact_claim(
                claim_path,
                expected_parent_identity=claim_parent_identity,
                expected_identity=tuple(pending["output_claim_identity"]),
                expected_sha256=str(pending["output_claim_sha256"]),
            )
            if raw != _claim_payload_from_pending(
                pending=pending,
                session_lease=session_lease,
            ) or claim_document["output_child_path"] != str(output_child):
                raise ValueError("live_start_output_claim_binding_changed")
            predecessor = pending["output_child_predecessor_identity"]
            if action == "bind_existing_child":
                if predecessor is None or not path_lexists(output_child):
                    raise ValueError("live_start_output_child_precondition_changed")
                child_identity = path_identity(output_child)
                if child_identity != tuple(predecessor):
                    raise ValueError("live_start_output_child_identity_changed")
                require_plain_directory(output_child)
                already_exact = True
            else:
                if predecessor is not None:
                    raise ValueError("live_start_output_child_precondition_changed")
                if not path_lexists(output_child):
                    child_identity = output_base_guard.create_directory(
                        output_child.name
                    )
                    controlled_times = (
                        _CONTROLLED_OUTPUT_CHILD_MTIME_NS,
                        _CONTROLLED_OUTPUT_CHILD_MTIME_NS,
                    )
                    try:
                        os.utime(
                            output_child,
                            ns=controlled_times,
                            follow_symlinks=False,
                        )
                    except NotImplementedError:
                        os.utime(output_child, ns=controlled_times)
                else:
                    require_plain_directory(output_child)
                    status = output_child.lstat()
                    if (
                        status.st_mtime_ns
                        != _CONTROLLED_OUTPUT_CHILD_MTIME_NS
                        or any(output_child.iterdir())
                    ):
                        raise ValueError(
                            "live_start_output_child_create_postcondition_changed"
                        )
                    child_identity = path_identity_from_status(status)
                    already_exact = True
                require_plain_directory(output_child)
                status = output_child.lstat()
                if (
                    path_identity_from_status(status) != child_identity
                    or status.st_mtime_ns != _CONTROLLED_OUTPUT_CHILD_MTIME_NS
                    or any(output_child.iterdir())
                ):
                    raise ValueError(
                        "live_start_output_child_create_postcondition_changed"
                    )
            assert child_identity is not None
            invoke_live_start_fault(
                fault_hook,
                LiveStartFaultPoint.AFTER_OUTPUT_CHILD_CREATE_BEFORE_CAS,
            )
            evidence = {
                "binding": _output_child_binding(
                    current=current,
                    pending=pending,
                    output_child_identity=child_identity,
                )
            }
        elif action == "retire_claim":
            child = current.output_child_binding
            publication = current.publication_binding
            if not isinstance(child, Mapping) or not isinstance(
                publication, Mapping
            ):
                raise ValueError("live_start_output_claim_retirement_invalid")
            if (
                path_identity(output_child)
                != tuple(child["output_child_identity"])
            ):
                raise ValueError("live_start_output_child_identity_changed")
            selected, _verified = _resolve_current_publication_without_ads(
                output_child
            )
            if (
                selected is None
                or selected.revision != publication["revision"]
                or "sha256:" + selected.content_root_sha256
                != publication["content_root_sha256"]
            ):
                raise ValueError("live_start_publication_current_changed")
            if path_lexists(claim_path):
                _read_exact_claim(
                    claim_path,
                    expected_parent_identity=claim_parent_identity,
                    expected_identity=tuple(pending["output_claim_identity"]),
                    expected_sha256=str(pending["output_claim_sha256"]),
                )
                secure_unlink(
                    claim_path,
                    expected_identity=tuple(pending["output_claim_identity"]),
                    expected_parent_identity=claim_parent_identity,
                    missing_ok=False,
                )
            else:
                already_exact = True
            invoke_live_start_fault(
                fault_hook,
                LiveStartFaultPoint.AFTER_OUTPUT_CHILD_CLAIM_UNLINK_BEFORE_CAS,
            )
            evidence = {
                "claim_path": str(claim_path),
                "claim_parent_identity": claim_parent_identity,
                "historical_claim_identity": pending["output_claim_identity"],
                "historical_claim_sha256": pending["output_claim_sha256"],
                "claim_disposition": "absent",
                "output_child_identity": child["output_child_identity"],
                "publication_revision": publication["revision"],
                "publication_content_root_sha256": publication[
                    "content_root_sha256"
                ],
            }
        elif action == "confirm_claim_absent_and_current_exact":
            child = current.output_child_binding
            publication = current.publication_binding
            if (
                path_lexists(claim_path)
                or not isinstance(child, Mapping)
                or not isinstance(publication, Mapping)
                or path_identity(output_child)
                != tuple(child["output_child_identity"])
            ):
                raise ValueError("live_start_output_claim_absence_invalid")
            selected, _verified = _resolve_current_publication_without_ads(
                output_child
            )
            if (
                selected is None
                or selected.revision != publication["revision"]
                or "sha256:" + selected.content_root_sha256
                != publication["content_root_sha256"]
            ):
                raise ValueError("live_start_publication_current_changed")
            retired_unsigned = dict(child)
            retired_unsigned.pop("content_sha256", None)
            retired_unsigned.update(
                {
                    "claim_identity": None,
                    "claim_sha256": None,
                    "claim_state": "RETIRED",
                }
            )
            retired = live_session.seal_embedded_document(
                "output_child_binding",
                retired_unsigned,
            )
            rebound_publication = dict(publication)
            rebound_publication["output_child_binding_sha256"] = retired[
                "content_sha256"
            ]
            evidence = {
                "output_child_binding": retired,
                "publication_binding": rebound_publication,
            }
            invoke_live_start_fault(
                fault_hook,
                LiveStartFaultPoint.AFTER_OUTPUT_CHILD_CLAIM_CONFIRMATION_BEFORE_RETIRED_CAS,
            )
        else:
            raise ValueError("live_start_output_bootstrap_action_invalid")
        return OutputChildBootstrapPhysicalPostcondition(
            action=action,
            evidence=evidence,
        )

    receipt = live_session._execute_output_child_bootstrap_physical_step(
        bootstrap_authorization=bootstrap_authorization,
        action=action,
        physical_action=perform,
    )
    return OutputChildBootstrapPhysicalStep(
        claim_staging=claim_staging,
        claim_identity=claim_identity,
        output_child_identity=child_identity,
        object_was_already_in_exact_postcondition=already_exact,
        step_receipt=receipt,
    )


def _validate_output_publication_guard(
    guard: object,
    *,
    lease: OutputChildBootstrapLease,
) -> PlainDirectoryMutationGuard:
    if not isinstance(guard, PlainDirectoryMutationGuard):
        raise ValueError("output_publication_guard_invalid")
    try:
        guard.validate()
    except ValueError as error:
        if str(error) == "filesystem_directory_guard_inactive":
            raise ValueError("output_publication_guard_inactive") from error
        raise
    if guard.path != lease.output_root:
        raise ValueError("output_publication_guard_path_invalid")
    return guard


def _load_exact_owning_session(
    *,
    session_lease: object,
    expected_session_sha256: str,
) -> object:
    from hsconfig import live_start_session as live_session

    try:
        current = live_session.load_live_start_session_under_lock(
            session_lease=session_lease
        )
    except (
        live_session.SessionCapabilityError,
        live_session.SessionConflictError,
        live_session.SessionLayoutError,
        live_session.SessionValidationError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        detail = str(error)
        if "cross_thread" in detail or "wrong_thread" in detail:
            reason = "output_publication_session_lease_cross_thread"
        elif "inactive" in detail or "expired" in detail:
            reason = "output_publication_session_lease_inactive"
        else:
            reason = "output_publication_session_lease_invalid"
        raise ValueError(reason) from error
    if current.content_sha256 != expected_session_sha256:
        raise ValueError("output_publication_session_cursor_stale")
    return current


def authorize_output_publication_under_bootstrap_lease(
    *,
    operation_lease: OutputOperationAdmissionLease,
    bootstrap_lease: OutputChildBootstrapLease,
    output_guard: PlainDirectoryMutationGuard,
    operation_admission: OutputOperationAdmissionEvidence | None,
    session_lease: object | None,
    expected_session: object | None,
    profile_lease: object | None,
) -> OutputPublicationAuthorization:
    _require_active_output_bootstrap_lease(bootstrap_lease)
    guard = _validate_output_publication_guard(
        output_guard,
        lease=bootstrap_lease,
    )
    observed = observe_output_operation_admission_under_lease(operation_lease)
    claim = _claim_fingerprint(bootstrap_lease.output_root)
    if operation_admission is None:
        if any(
            value is not None
            for value in (session_lease, expected_session, profile_lease)
        ):
            raise ValueError("output_publication_authorization_kind_invalid")
        if observed is not None:
            raise ValueError("output_operation_admission_blocks_publication")
        if claim is not None:
            raise ValueError("output_child_claim_present")
        kind = "ORDINARY_CLAIM_ABSENT"
        session_sha256 = None
    else:
        if any(
            value is None
            for value in (session_lease, expected_session, profile_lease)
        ):
            raise ValueError("output_publication_authorization_kind_invalid")
        if (
            observed != operation_admission
            or operation_admission.output_child_path
            != bootstrap_lease.output_root
        ):
            raise ValueError("output_operation_admission_blocks_publication")
        from hsconfig import live_start_session as live_session

        if not isinstance(expected_session, live_session.LiveStartSession):
            raise ValueError("output_publication_session_cursor_stale")
        current = _load_exact_owning_session(
            session_lease=session_lease,
            expected_session_sha256=expected_session.content_sha256,
        )
        try:
            operator_profile_state._require_active_lease(profile_lease)
            profile = profile_lease.profile
        except (TypeError, ValueError) as error:
            raise ValueError("output_publication_profile_binding_changed") from error
        if (
            profile.content_sha256 != operation_admission.operator_profile_sha256
            or Path(profile_lease.profile_path)
            != operation_admission.operator_profile_path
            or profile_lease.profile_identity
            != operation_admission.operator_profile_identity
        ):
            raise ValueError("output_publication_profile_binding_changed")
        binding = current.output_operation_admission_binding
        child = current.output_child_binding
        if (
            not isinstance(binding, Mapping)
            or binding.get("admission_identity")
            != operation_admission.admission_identity
            or binding.get("admission_sha256")
            != _admission_raw_sha256(operation_admission)
            or not isinstance(child, Mapping)
            or child.get("claim_state") != "ACTIVE"
            or child.get("output_child_identity") != guard.identity
            or child.get("output_child_path") != str(guard.path)
        ):
            raise ValueError("output_publication_authorization_kind_invalid")
        expected_claim = (
            tuple(child["claim_identity"]),
            str(child["claim_sha256"]),
        )
        if claim != expected_claim:
            raise ValueError("output_publication_claim_identity_changed")
        kind = "OWNING_ACTIVE_CLAIM"
        session_sha256 = current.content_sha256
    return OutputPublicationAuthorization(
        bootstrap_lease=bootstrap_lease,
        claim_identity=None if claim is None else claim[0],
        claim_sha256=None if claim is None else claim[1],
        guard=guard,
        kind=kind,
        operation_admission=operation_admission,
        operation_lease=operation_lease,
        profile_lease=profile_lease,
        session_lease=session_lease,
        session_sha256=session_sha256,
        authority=_OUTPUT_PUBLICATION_AUTHORITY,
    )


@contextmanager
def _begin_output_publication(
    *,
    publication_authorization: OutputPublicationAuthorization,
    operation_lease: OutputOperationAdmissionLease,
    bootstrap_lease: OutputChildBootstrapLease,
    output_guard: PlainDirectoryMutationGuard,
) -> Iterator[OutputPublicationPermit]:
    if not isinstance(publication_authorization, OutputPublicationAuthorization):
        raise ValueError("output_publication_authorization_invalid")
    authorization = publication_authorization
    _consume_output_publication_authorization(authorization)
    if authorization.thread_id != get_ident():
        raise ValueError("output_publication_authorization_cross_thread")
    try:
        _require_active_output_bootstrap_lease(authorization.bootstrap_lease)
    except ValueError as error:
        raise ValueError("output_publication_authorization_expired") from error
    if authorization.bootstrap_lease is not bootstrap_lease:
        raise ValueError("output_publication_authorization_expired")
    guard = _validate_output_publication_guard(output_guard, lease=bootstrap_lease)
    if (
        authorization.operation_lease is not operation_lease
        or authorization.guard is not output_guard
    ):
        raise ValueError("output_publication_authorization_binding_invalid")
    _require_active_output_bootstrap_lease(bootstrap_lease)
    observed = observe_output_operation_admission_under_lease(operation_lease)
    claim = _claim_fingerprint(bootstrap_lease.output_root)
    if authorization.kind == "ORDINARY_CLAIM_ABSENT":
        if observed is not None or claim is not None:
            raise ValueError("output_publication_authorization_kind_invalid")
    elif authorization.kind == "OWNING_ACTIVE_CLAIM":
        if observed != authorization.operation_admission:
            raise ValueError("output_publication_authorization_expired")
        expected_claim = (
            authorization.claim_identity,
            authorization.claim_sha256,
        )
        if claim != expected_claim:
            raise ValueError("output_publication_claim_identity_changed")
        current = _load_exact_owning_session(
            session_lease=authorization.session_lease,
            expected_session_sha256=authorization.session_sha256,
        )
        child = current.output_child_binding
        if (
            not isinstance(child, Mapping)
            or child.get("claim_state") != "ACTIVE"
            or child.get("output_child_identity") != guard.identity
        ):
            raise ValueError("output_publication_authorization_expired")
        try:
            operator_profile_state._require_active_lease(
                authorization.profile_lease
            )
        except (TypeError, ValueError) as error:
            raise ValueError(
                "output_publication_profile_binding_changed"
            ) from error
    else:
        raise ValueError("output_publication_authorization_kind_invalid")
    guard.validate()
    permit = OutputPublicationPermit(
        authorization,
        _OUTPUT_PUBLICATION_PERMIT_AUTHORITY,
    )
    try:
        yield permit
    finally:
        if permit.active:
            permit.active = False


def _finish_output_publication(
    *,
    permit: OutputPublicationPermit,
    published_output: PublishedOutput,
) -> None:
    if (
        not isinstance(permit, OutputPublicationPermit)
        or not permit.active
        or permit.published is not None
        or not isinstance(published_output, PublishedOutput)
    ):
        raise ValueError("output_publication_permit_invalid")
    if published_output.output_root != permit.authorization.bootstrap_lease.output_root:
        raise ValueError("output_publication_result_root_invalid")
    permit.published = published_output
    permit.active = False


def _build_live_start_commit_receipt(
    *,
    authorization: OutputPublicationAuthorization,
    pointer_snapshot: _PointerSnapshot,
    pointer_result_identity: tuple[int, int, int],
    pointer_content: bytes,
    disposition: Literal["pointer_staged", "reused_existing"],
    owner_journal_predecessor_identity: tuple[int, int, int] | None,
) -> _LiveStartCommitReceipt:
    operation = authorization.operation_admission
    if (
        authorization.kind != "OWNING_ACTIVE_CLAIM"
        or authorization.session_sha256 is None
        or authorization.claim_identity is None
        or authorization.claim_sha256 is None
        or operation is None
    ):
        raise ValueError("output_publication_authorization_kind_invalid")
    predecessor_identity = (
        None
        if pointer_snapshot.identity is None
        else pointer_snapshot.identity[:3]
    )
    predecessor_size = (
        None
        if pointer_snapshot.content is None
        else len(pointer_snapshot.content)
    )
    predecessor_sha256 = (
        None
        if pointer_snapshot.content is None
        else "sha256:" + sha256(pointer_snapshot.content).hexdigest()
    )
    unsigned = {
        "schema_version": _LIVE_START_COMMIT_RECEIPT_SCHEMA_VERSION,
        "receipt_kind": _LIVE_START_COMMIT_RECEIPT_KIND,
        "disposition": disposition,
        "expected_session_sha256": authorization.session_sha256,
        "operation_admission_identity": list(operation.admission_identity),
        "operation_admission_sha256": _admission_raw_sha256(operation),
        "claim_identity": list(authorization.claim_identity),
        "claim_sha256": authorization.claim_sha256,
        "output_child_identity": list(authorization.guard.identity),
        "pointer_predecessor_identity": (
            None
            if predecessor_identity is None
            else list(predecessor_identity)
        ),
        "pointer_predecessor_size": predecessor_size,
        "pointer_predecessor_sha256": predecessor_sha256,
        "pointer_staging_identity": list(pointer_result_identity),
        "planned_pointer_size": len(pointer_content),
        "planned_pointer_sha256": (
            "sha256:" + sha256(pointer_content).hexdigest()
        ),
        "owner_journal_predecessor_identity": (
            None
            if owner_journal_predecessor_identity is None
            else list(owner_journal_predecessor_identity)
        ),
        "owner_journal_identity": None,
    }
    return _LiveStartCommitReceipt(
        schema_version=_LIVE_START_COMMIT_RECEIPT_SCHEMA_VERSION,
        receipt_kind=_LIVE_START_COMMIT_RECEIPT_KIND,
        disposition=disposition,
        expected_session_sha256=authorization.session_sha256,
        operation_admission_identity=operation.admission_identity,
        operation_admission_sha256=str(
            unsigned["operation_admission_sha256"]
        ),
        claim_identity=authorization.claim_identity,
        claim_sha256=authorization.claim_sha256,
        output_child_identity=authorization.guard.identity,
        pointer_predecessor_identity=predecessor_identity,
        pointer_predecessor_size=predecessor_size,
        pointer_predecessor_sha256=predecessor_sha256,
        pointer_staging_identity=pointer_result_identity,
        planned_pointer_size=len(pointer_content),
        planned_pointer_sha256=str(unsigned["planned_pointer_sha256"]),
        owner_journal_predecessor_identity=(
            owner_journal_predecessor_identity
        ),
        owner_journal_identity=None,
        content_sha256=(
            "sha256:" + sha256(_canonical_json_bytes(unsigned)).hexdigest()
        ),
    )


def _require_live_start_receipt_authorization(
    *,
    receipt: _LiveStartCommitReceipt,
    authorization: OutputPublicationAuthorization,
) -> None:
    authority = _live_start_temp_recovery_authority_from_authorization(
        authorization
    )
    _require_live_start_temp_receipt_authority(
        receipt=receipt,
        authority=authority,
    )


def _live_start_temp_recovery_authority_from_authorization(
    authorization: OutputPublicationAuthorization,
) -> _LiveStartTempRecoveryAuthority:
    operation = authorization.operation_admission
    claim = _claim_fingerprint(authorization.guard.path)
    if (
        authorization.kind != "OWNING_ACTIVE_CLAIM"
        or authorization.session_sha256 is None
        or operation is None
        or authorization.claim_identity is None
        or authorization.claim_sha256 is None
        or claim
        != (authorization.claim_identity, authorization.claim_sha256)
    ):
        raise ValueError("output_publication_authorization_expired")
    authorization.guard.validate()
    return _LiveStartTempRecoveryAuthority(
        expected_session_sha256=authorization.session_sha256,
        operation_admission_identity=operation.admission_identity,
        operation_admission_sha256=_admission_raw_sha256(operation),
        claim_identity=authorization.claim_identity,
        claim_sha256=authorization.claim_sha256,
        output_child_identity=authorization.guard.identity,
    )


def _require_live_start_temp_receipt_authority(
    *,
    receipt: _LiveStartCommitReceipt,
    authority: _LiveStartTempRecoveryAuthority,
) -> None:
    if (
        receipt.expected_session_sha256
        != authority.expected_session_sha256
        or receipt.operation_admission_identity
        != authority.operation_admission_identity
        or receipt.operation_admission_sha256
        != authority.operation_admission_sha256
        or receipt.claim_identity != authority.claim_identity
        or receipt.claim_sha256 != authority.claim_sha256
        or receipt.output_child_identity != authority.output_child_identity
    ):
        raise ValueError("output_publication_authorization_expired")


def _require_current_pointer_receipt_exact(
    output_root: Path,
    receipt: _LiveStartCommitReceipt,
    expected_content: bytes,
) -> None:
    pointer_path = output_root / CURRENT_PATH
    try:
        status = plain_file_status(pointer_path)
    except (FileNotFoundError, ValueError) as error:
        raise ValueError(
            "live_start_publication_current_identity_changed"
        ) from error
    if path_identity_from_status(status) != receipt.pointer_staging_identity:
        raise ValueError("live_start_publication_current_identity_changed")
    _require_plain_file_no_ads(pointer_path, status)
    raw = read_file_no_follow(
        pointer_path,
        expected_status=status,
        maximum_size=max(len(expected_content), 1),
    )
    if (
        len(raw) != receipt.planned_pointer_size
        or "sha256:" + sha256(raw).hexdigest()
        != receipt.planned_pointer_sha256
        or raw != expected_content
    ):
        raise ValueError("live_start_publication_current_bytes_changed")


def _require_pointer_predecessor_exact(
    output_root: Path,
    receipt: _LiveStartCommitReceipt,
) -> None:
    pointer_path = output_root / CURRENT_PATH
    if receipt.pointer_predecessor_identity is None:
        if path_lexists(pointer_path):
            raise ValueError("live_start_publication_current_identity_changed")
        return
    try:
        status = plain_file_status(pointer_path)
    except (FileNotFoundError, ValueError) as error:
        raise ValueError(
            "live_start_publication_current_identity_changed"
        ) from error
    if path_identity_from_status(status) != receipt.pointer_predecessor_identity:
        raise ValueError("live_start_publication_current_identity_changed")
    _require_plain_file_no_ads(pointer_path, status)
    raw = read_file_no_follow(
        pointer_path,
        expected_status=status,
        maximum_size=max(receipt.pointer_predecessor_size or 0, 1),
    )
    if (
        len(raw) != receipt.pointer_predecessor_size
        or "sha256:" + sha256(raw).hexdigest()
        != receipt.pointer_predecessor_sha256
    ):
        raise ValueError("live_start_publication_current_bytes_changed")


def _live_start_publication_prior_current_identity(
    published: PublishedOutput,
) -> tuple[int, int, int] | None:
    if not isinstance(published, PublishedOutput):
        raise TypeError("published_output_required")
    revision = published.revision_root.relative_to(
        published.output_root
    ).as_posix()
    owners = [
        transaction
        for _path, transaction in _load_valid_transactions(
            published.output_root
        )
        if transaction.owns_revision
        and transaction.revision == revision
        and transaction.content_root_sha256 == published.content_root_sha256
        and transaction.live_start_commit_receipt is not None
    ]
    if len(owners) != 1:
        raise ValueError("live_start_publication_commit_receipt_invalid")
    receipt = owners[0].live_start_commit_receipt
    if receipt is None:
        raise ValueError("live_start_publication_commit_receipt_invalid")
    _require_current_pointer_receipt_exact(
        published.output_root,
        receipt,
        output_publication_bytes(
            OutputPublication(
                schema_version=CURRENT_SCHEMA_VERSION,
                deck_name=owners[0].deck_name,
                deck_fingerprint=owners[0].deck_fingerprint,
                revision=owners[0].revision,
                content_root_sha256=owners[0].content_root_sha256,
            )
        ),
    )
    return receipt.pointer_predecessor_identity


def _owner_for_revision_locked(
    output_root: Path,
    revision: str,
) -> tuple[Path, _Transaction, tuple[int, int, int]]:
    journals = _load_valid_transactions(output_root)
    owners = [
        (path, transaction)
        for path, transaction in journals
        if transaction.owns_revision and transaction.revision == revision
    ]
    if len(owners) != 1:
        raise ValueError("publisher_current_owner_invalid")
    path, transaction = owners[0]
    identity = getattr(journals, "identities", {}).get(path)
    if identity is None:
        raise ValueError("publisher_current_owner_invalid")
    return path, transaction, identity


def _bind_reused_live_start_publication_locked(
    *,
    rendered: RenderedConfigureRun,
    output_root: Path,
    current: PublishedOutput,
    authorization: OutputPublicationAuthorization,
) -> tuple[Path, _Transaction]:
    revision = current.revision_root.relative_to(output_root).as_posix()
    journal_path, owner, journal_identity = _owner_for_revision_locked(
        output_root,
        revision,
    )
    if (
        owner.phase != "finalized"
        or owner.revision_identity != path_identity(current.revision_root)
        or owner.deck_name != rendered.model.deck_name
        or owner.deck_fingerprint != rendered.model.deck_fingerprint
        or owner.content_root_sha256 != rendered.content_root_sha256
    ):
        raise ValueError("publisher_current_owner_invalid")
    pointer_snapshot = _snapshot_pointer(output_root)
    if pointer_snapshot.content is None or pointer_snapshot.identity is None:
        raise ValueError("live_start_publication_current_identity_changed")
    receipt = _build_live_start_commit_receipt(
        authorization=authorization,
        pointer_snapshot=pointer_snapshot,
        pointer_result_identity=pointer_snapshot.identity[:3],
        pointer_content=pointer_snapshot.content,
        disposition="reused_existing",
        owner_journal_predecessor_identity=journal_identity,
    )
    upgraded = replace(
        owner,
        schema_version=_LIVE_START_TRANSACTION_SCHEMA_VERSION,
        live_start_commit_receipt=receipt,
    )
    upgraded = _write_transaction(
        journal_path,
        upgraded,
        expected_target_identity=journal_identity,
        expected_target_content=_transaction_bytes(owner),
    )
    return journal_path, upgraded


def _adopt_existing_revision_owner_for_live_start_locked(
    *,
    output_root: Path,
    coordinator_path: Path,
    coordinator: _Transaction,
    revision_root: Path,
) -> tuple[Path, _Transaction]:
    journals = _load_valid_transactions(output_root)
    owners = [
        (path, transaction)
        for path, transaction in journals
        if path != coordinator_path
        and transaction.owns_revision
        and transaction.revision == coordinator.revision
    ]
    if len(owners) != 1:
        raise ValueError("publisher_current_owner_invalid")
    owner_path, owner = owners[0]
    identities = getattr(journals, "identities", {})
    owner_identity = identities.get(owner_path)
    coordinator_identity = identities.get(coordinator_path)
    if (
        owner_identity is None
        or coordinator_identity is None
        or owner.phase != "finalized"
        or owner.revision_identity != path_identity(revision_root)
        or owner.deck_name != coordinator.deck_name
        or owner.deck_fingerprint != coordinator.deck_fingerprint
        or owner.content_root_sha256 != coordinator.content_root_sha256
    ):
        raise ValueError("publisher_current_owner_invalid")
    secure_unlink(
        coordinator_path,
        expected_identity=coordinator_identity,
        expected_parent_identity=path_identity(coordinator_path.parent),
    )
    adopted = replace(
        owner,
        schema_version=_LIVE_START_TRANSACTION_SCHEMA_VERSION,
        previous_revision=coordinator.previous_revision,
        previous_revision_identity=None,
        previous_owner_transaction_id=None,
        staging_identity=None,
        phase="revision_ready",
        live_start_commit_receipt=None,
    )
    _write_transaction(
        owner_path,
        adopted,
        expected_target_identity=owner_identity,
        expected_target_content=_transaction_bytes(owner),
    )
    return owner_path, adopted


def _commit_live_start_pointer_locked(
    *,
    output_root: Path,
    pointer_snapshot: _PointerSnapshot,
    publication: OutputPublication,
    transaction: _Transaction,
    journal_path: Path,
    authorization: OutputPublicationAuthorization,
    fault_hook: FaultHook,
) -> _Transaction:
    if (
        transaction.schema_version != _LIVE_START_TRANSACTION_SCHEMA_VERSION
        or transaction.phase != "revision_ready"
        or not transaction.owns_revision
    ):
        raise ValueError("publisher_live_start_transaction_invalid")
    pointer_content = output_publication_bytes(publication)
    staging_path = (
        output_root
        / ".publisher"
        / "transactions"
        / f".{transaction.transaction_id}.current.tmp"
    )
    inner_temp_path = staging_path.with_name(
        f".{staging_path.name}.live-start-atomic.tmp"
    )

    def staging_fault(_stage: str) -> None:
        fault_hook("after_pointer_temp_write")

    staged = atomic_materialize_staging_bytes(
        staging_path=staging_path,
        inner_temp_path=inner_temp_path,
        payload=pointer_content,
        expected_parent_identity=path_identity(staging_path.parent),
        maximum_size=1024 * 1024,
        fault_hook=staging_fault,
    )
    receipt = _build_live_start_commit_receipt(
        authorization=authorization,
        pointer_snapshot=pointer_snapshot,
        pointer_result_identity=staged.identity,
        pointer_content=pointer_content,
        disposition="pointer_staged",
        owner_journal_predecessor_identity=None,
    )
    journal_status = plain_file_status(journal_path)
    _require_plain_file_no_ads(journal_path, journal_status)
    journal_content = read_file_no_follow(
        journal_path,
        expected_status=journal_status,
        maximum_size=_MAX_TRANSACTION_FILE_BYTES,
    )
    transaction = replace(
        transaction,
        phase="pointer_staging_bound",
        live_start_commit_receipt=receipt,
    )
    transaction = _write_transaction(
        journal_path,
        transaction,
        expected_target_identity=path_identity_from_status(journal_status),
        expected_target_content=journal_content,
        fault_hook=fault_hook,
    )
    if _snapshot_pointer(output_root) != pointer_snapshot:
        raise ValueError("current_output_concurrent_change")
    parent_identity = path_identity(staging_path.parent)
    secure_replace(
        staging_path,
        output_root / CURRENT_PATH,
        expected_source_identity=staged.identity,
        expected_source_parent_identity=parent_identity,
        expected_target_parent_identity=path_identity(output_root),
        expected_target_identity=(
            None
            if pointer_snapshot.identity is None
            else pointer_snapshot.identity[:3]
        ),
        expected_target_absent=not pointer_snapshot.existed,
    )
    _require_current_pointer_receipt_exact(
        output_root,
        receipt,
        pointer_content,
    )
    fault_hook("after_pointer_replace")
    previous = transaction
    transaction = replace(transaction, phase="pointer_committed")
    journal_status = plain_file_status(journal_path)
    transaction = _write_transaction(
        journal_path,
        transaction,
        expected_target_identity=path_identity_from_status(journal_status),
        expected_target_content=_transaction_bytes(previous),
        fault_hook=fault_hook,
    )
    return transaction


def _resume_live_start_publication_locked(
    *,
    rendered: RenderedConfigureRun,
    output_root: Path,
    authorization: OutputPublicationAuthorization,
    fault_hook: FaultHook,
) -> tuple[PublishedOutput, Path, _Transaction] | None:
    recovery_authority = (
        _live_start_temp_recovery_authority_from_authorization(
            authorization
        )
    )
    pointer_path = output_root / CURRENT_PATH
    current = (
        _resolve_current_publication_without_ads(output_root)
        if path_lexists(pointer_path)
        else None
    )
    preserved_pointer_temps = _recover_owned_atomic_temps(
        output_root,
        current_revision=current[0].revision if current is not None else None,
        current=current,
        preserve_bound_live_pointer_temps=True,
        live_start_authority=recovery_authority,
    )
    journals = _load_valid_transactions(
        output_root,
        allowed_live_pointer_temp_ids=preserved_pointer_temps,
    )
    candidates = [
        (path, transaction)
        for path, transaction in journals
        if transaction.live_start_commit_receipt is not None
        and transaction.live_start_commit_receipt.expected_session_sha256
        == authorization.session_sha256
        and transaction.deck_name == rendered.model.deck_name
        and transaction.deck_fingerprint == rendered.model.deck_fingerprint
        and transaction.content_root_sha256 == rendered.content_root_sha256
    ]
    if not candidates:
        active_foreign = [
            transaction
            for _path, transaction in journals
            if transaction.live_start_commit_receipt is not None
            and transaction.phase in {
                "pointer_staging_bound",
                "pointer_committed",
            }
        ]
        if active_foreign:
            raise ValueError("output_publication_authorization_expired")
        return None
    if len(candidates) != 1:
        raise ValueError("publisher_live_start_commit_receipt_ambiguous")
    journal_path, transaction = candidates[0]
    receipt = transaction.live_start_commit_receipt
    if receipt is None:
        raise ValueError("publisher_live_start_commit_receipt_invalid")
    _require_live_start_receipt_authorization(
        receipt=receipt,
        authorization=authorization,
    )
    publication = OutputPublication(
        schema_version=CURRENT_SCHEMA_VERSION,
        deck_name=transaction.deck_name,
        deck_fingerprint=transaction.deck_fingerprint,
        revision=transaction.revision,
        content_root_sha256=transaction.content_root_sha256,
    )
    pointer_content = output_publication_bytes(publication)
    if receipt.disposition == "pointer_staged":
        if transaction.phase == "pointer_staging_bound":
            staging_path = (
                output_root
                / ".publisher"
                / "transactions"
                / f".{transaction.transaction_id}.current.tmp"
            )
            if path_lexists(staging_path):
                status = plain_file_status(staging_path)
                _require_plain_file_no_ads(staging_path, status)
                raw = read_file_no_follow(
                    staging_path,
                    expected_status=status,
                    maximum_size=max(receipt.planned_pointer_size, 1),
                )
                if (
                    path_identity_from_status(status)
                    != receipt.pointer_staging_identity
                    or raw != pointer_content
                ):
                    raise ValueError(
                        "live_start_publication_current_identity_changed"
                    )
                _require_pointer_predecessor_exact(output_root, receipt)
                secure_replace(
                    staging_path,
                    output_root / CURRENT_PATH,
                    expected_source_identity=receipt.pointer_staging_identity,
                    expected_source_parent_identity=path_identity(
                        staging_path.parent
                    ),
                    expected_target_parent_identity=path_identity(output_root),
                    expected_target_identity=(
                        receipt.pointer_predecessor_identity
                    ),
                    expected_target_absent=(
                        receipt.pointer_predecessor_identity is None
                    ),
                )
            _require_current_pointer_receipt_exact(
                output_root,
                receipt,
                pointer_content,
            )
            previous = transaction
            transaction = replace(transaction, phase="pointer_committed")
            status = plain_file_status(journal_path)
            transaction = _write_transaction(
                journal_path,
                transaction,
                expected_target_identity=path_identity_from_status(status),
                expected_target_content=_transaction_bytes(previous),
                fault_hook=fault_hook,
            )
        elif transaction.phase in {"pointer_committed", "finalized"}:
            _require_current_pointer_receipt_exact(
                output_root,
                receipt,
                pointer_content,
            )
        else:
            raise ValueError("publisher_live_start_commit_phase_invalid")
    elif receipt.disposition == "reused_existing" and transaction.phase == "finalized":
        _require_current_pointer_receipt_exact(
            output_root,
            receipt,
            pointer_content,
        )
    else:
        raise ValueError("publisher_live_start_commit_phase_invalid")
    revision_root = output_root / transaction.revision
    if (
        not transaction.owns_revision
        or transaction.revision_identity != path_identity(revision_root)
    ):
        raise ValueError("publisher_current_owner_invalid")
    verified = snapshot_and_verify_revision(revision_root)
    if (
        verified.manifest.deck_name != transaction.deck_name
        or verified.manifest.deck_fingerprint != transaction.deck_fingerprint
        or verified.manifest.content_root_sha256
        != transaction.content_root_sha256
    ):
        raise ValueError("publisher_current_owner_invalid")
    return (
        PublishedOutput(
            output_root=output_root,
            revision_root=revision_root,
            package_root=revision_root / "04_package",
            content_root_sha256=transaction.content_root_sha256,
            reused_existing_revision=True,
        ),
        journal_path,
        transaction,
    )


def _finish_live_start_publication_locked(
    *,
    authorization: OutputPublicationAuthorization,
    published: PublishedOutput,
    journal_path: Path,
    transaction: _Transaction,
    fault_hook: FaultHook,
) -> None:
    receipt = transaction.live_start_commit_receipt
    if receipt is None:
        raise ValueError("publisher_live_start_commit_receipt_invalid")
    _require_live_start_receipt_authorization(
        receipt=receipt,
        authorization=authorization,
    )
    _require_current_pointer_receipt_exact(
        published.output_root,
        receipt,
        output_publication_bytes(
            OutputPublication(
                schema_version=CURRENT_SCHEMA_VERSION,
                deck_name=transaction.deck_name,
                deck_fingerprint=transaction.deck_fingerprint,
                revision=transaction.revision,
                content_root_sha256=transaction.content_root_sha256,
            )
        ),
    )
    current = live_session.load_live_start_session_under_lock(
        session_lease=authorization.session_lease
    )
    if current.content_sha256 == authorization.session_sha256:
        return
    child = current.output_child_binding
    binding = current.publication_binding
    if (
        current.phase is not live_session.LiveStartPhase.PUBLICATION_COMMITTED
        or not isinstance(child, Mapping)
        or not isinstance(binding, Mapping)
        or binding.get("output_child_path") != str(published.output_root)
        or binding.get("output_child_identity")
        != authorization.guard.identity
        or binding.get("output_child_binding_sha256")
        != child.get("content_sha256")
        or binding.get("revision") != transaction.revision
        or binding.get("content_root_sha256")
        != "sha256:" + transaction.content_root_sha256
        or binding.get("prior_current_identity")
        != receipt.pointer_predecessor_identity
    ):
        raise ValueError("live_start_publication_session_cursor_stale")
    if receipt.disposition == "pointer_staged":
        _cleanup_after_commit(
            published.output_root,
            transaction,
            journal_path,
            fault_hook=fault_hook,
        )


def _finalize_committed_live_start_publication_under_guard(
    *,
    output_guard: PlainDirectoryMutationGuard,
    operation_lease: OutputOperationAdmissionLease,
    bootstrap_lease: OutputChildBootstrapLease,
    operation_admission: OutputOperationAdmissionEvidence,
    session_lease: LiveStartSessionLease,
    expected_session: LiveStartSession,
    profile_lease: OperatorProfileLease,
) -> None:
    """Finish the exact receipt-bound owner after the session commit CAS."""

    _require_active_output_bootstrap_lease(bootstrap_lease)
    guard = _validate_output_publication_guard(
        output_guard,
        lease=bootstrap_lease,
    )
    observed = observe_output_operation_admission_under_lease(operation_lease)
    current = _load_exact_owning_session(
        session_lease=session_lease,
        expected_session_sha256=expected_session.content_sha256,
    )
    operator_profile_state._require_active_lease(profile_lease)
    child = current.output_child_binding
    publication = current.publication_binding
    operation = current.output_operation_admission_binding
    if (
        current.phase is not live_session.LiveStartPhase.PUBLICATION_COMMITTED
        or observed != operation_admission
        or not isinstance(child, Mapping)
        or child.get("claim_state") != "ACTIVE"
        or not isinstance(publication, Mapping)
        or not isinstance(operation, Mapping)
        or operation.get("admission_identity")
        != operation_admission.admission_identity
        or operation.get("admission_sha256")
        != _admission_raw_sha256(operation_admission)
        or child.get("output_child_path") != str(guard.path)
        or child.get("output_child_identity") != guard.identity
        or publication.get("output_child_path") != str(guard.path)
        or publication.get("output_child_identity") != guard.identity
        or publication.get("output_child_binding_sha256")
        != child.get("content_sha256")
    ):
        raise ValueError("live_start_publication_session_cursor_stale")
    profile = profile_lease.profile
    if (
        profile.content_sha256 != operation_admission.operator_profile_sha256
        or Path(profile_lease.profile_path)
        != operation_admission.operator_profile_path
        or profile_lease.profile_identity
        != operation_admission.operator_profile_identity
    ):
        raise ValueError("output_publication_profile_binding_changed")
    expected_claim = (
        tuple(child["claim_identity"]),
        str(child["claim_sha256"]),
    )
    pending = current.pending_transition
    claim_may_be_absent = (
        isinstance(pending, Mapping)
        and pending.get("operation") == "retire_output_child_claim"
        and pending.get("stage") in {"PREPARED", "PRIMARY_APPLIED"}
    )
    physical_claim = _claim_fingerprint(guard.path)
    if physical_claim != expected_claim and not (
        physical_claim is None and claim_may_be_absent
    ):
        raise ValueError("output_publication_claim_identity_changed")
    predecessor_value = current.to_value()
    predecessor_value["phase"] = (
        live_session.LiveStartPhase.PREPUBLICATION_CHECK_PASSED.value
    )
    predecessor_value["pending_transition"] = None
    predecessor_value["publication_binding"] = None
    predecessor_sha256 = live_session._seal_session_value(
        predecessor_value,
        session_identity=None,
    ).content_sha256
    recovery_authority = _LiveStartTempRecoveryAuthority(
        expected_session_sha256=predecessor_sha256,
        operation_admission_identity=operation_admission.admission_identity,
        operation_admission_sha256=_admission_raw_sha256(
            operation_admission
        ),
        claim_identity=expected_claim[0],
        claim_sha256=expected_claim[1],
        output_child_identity=guard.identity,
    )

    root = guard.path
    ancestor_guard = capture_plain_ancestor_guard(root / ".publish.lock")
    _validate_existing_layout(root, output_guard=guard)
    with ExclusiveFileLock(
        root / ".publish.lock",
        expected_parent_identity=guard.identity,
        path_guard=guard,
    ):
        guard.validate()
        ancestor_guard.validate()
        pointer = _resolve_current_publication_without_ads(root)
        _recover_owned_atomic_temps(
            root,
            current_revision=pointer[0].revision,
            current=pointer,
            live_start_authority=recovery_authority,
        )
        journals = _load_valid_transactions(root)
        candidates = [
            (path, transaction)
            for path, transaction in journals
            if transaction.owns_revision
            and transaction.revision == publication.get("revision")
            and transaction.live_start_commit_receipt is not None
        ]
        if len(candidates) != 1:
            raise ValueError("publisher_live_start_commit_receipt_ambiguous")
        journal_path, transaction = candidates[0]
        receipt = transaction.live_start_commit_receipt
        assert receipt is not None
        if (
            transaction.phase
            not in {"pointer_committed", "cleanup_started", "finalized"}
            or receipt.expected_session_sha256 != predecessor_sha256
            or receipt.operation_admission_identity
            != operation_admission.admission_identity
            or receipt.operation_admission_sha256
            != operation.get("admission_sha256")
            or receipt.claim_identity != expected_claim[0]
            or receipt.claim_sha256 != expected_claim[1]
            or receipt.output_child_identity != guard.identity
            or receipt.pointer_predecessor_identity
            != publication.get("prior_current_identity")
            or publication.get("content_root_sha256")
            != "sha256:" + transaction.content_root_sha256
        ):
            raise ValueError("publisher_live_start_commit_receipt_invalid")
        pointer_content = output_publication_bytes(pointer[0])
        _require_current_pointer_receipt_exact(
            root,
            receipt,
            pointer_content,
        )
        if transaction.phase != "finalized":
            _cleanup_after_commit(
                root,
                transaction,
                journal_path,
                fault_hook=no_fault,
            )
        finalized = _load_valid_transactions(root)
        finalized_owner = [
            candidate
            for _path, candidate in finalized
            if candidate.transaction_id == transaction.transaction_id
            and candidate.owns_revision
        ]
        if len(finalized_owner) != 1 or finalized_owner[0].phase != "finalized":
            raise ValueError("publisher_finalized_authority_invalid")
        guard.validate()


@contextmanager
def publish_configure_run_under_guard(
    rendered: RenderedConfigureRun,
    *,
    output_guard: PlainDirectoryMutationGuard,
    operation_lease: OutputOperationAdmissionLease,
    bootstrap_lease: OutputChildBootstrapLease,
    publication_authorization: OutputPublicationAuthorization,
    fault_hook: FaultHook = no_fault,
) -> Iterator[PublishedOutput]:
    with _begin_output_publication(
        publication_authorization=publication_authorization,
        operation_lease=operation_lease,
        bootstrap_lease=bootstrap_lease,
        output_guard=output_guard,
    ) as permit:
        output_guard.validate()
        with _publish_configure_run_context(
            rendered,
            output_guard.path,
            publication_authorization=permit.authorization,
            output_guard=output_guard,
            fault_hook=fault_hook,
        ) as published:
            output_guard.validate()
            try:
                yield published
            finally:
                output_guard.validate()
                _finish_output_publication(
                    permit=permit,
                    published_output=published,
                )


def publish_configure_run(
    rendered: RenderedConfigureRun,
    output_root: Path,
    *,
    fault_hook: FaultHook = no_fault,
) -> PublishedOutput:
    if not isinstance(rendered, RenderedConfigureRun):
        raise TypeError("rendered_configure_run_required")
    root = _canonical_output_root(output_root)
    _bootstrap_neutral_output_locks(output_root=root)
    with lease_output_operation_admission() as operation_lease:
        root_identity = path_identity(root) if path_lexists(root) else None
        require_output_operation_allows_publication(
            lease=operation_lease,
            output_root=root,
            output_root_identity=root_identity,
        )
        with lease_output_child_bootstrap(output_root=root) as bootstrap_lease:
            if _claim_fingerprint(root) is not None:
                raise ValueError("output_child_claim_present")
            _secure_create_directory_chain(root.parent)
            with hold_plain_directory(root.parent) as parent_guard:
                bootstrap_plain_child_directory_under_guard(
                    parent_guard=parent_guard,
                    child_name=root.name,
                )
            with hold_plain_directory(root) as output_guard:
                authorization = authorize_output_publication_under_bootstrap_lease(
                    operation_lease=operation_lease,
                    bootstrap_lease=bootstrap_lease,
                    output_guard=output_guard,
                    operation_admission=None,
                    session_lease=None,
                    expected_session=None,
                    profile_lease=None,
                )
                with publish_configure_run_under_guard(
                    rendered,
                    output_guard=output_guard,
                    operation_lease=operation_lease,
                    bootstrap_lease=bootstrap_lease,
                    publication_authorization=authorization,
                    fault_hook=fault_hook,
                ) as published:
                    return published


@contextmanager
def _publish_configure_run_context(
    rendered: RenderedConfigureRun,
    output_root: Path,
    *,
    publication_authorization: OutputPublicationAuthorization | None,
    output_guard: PlainDirectoryMutationGuard | None = None,
    fault_hook: FaultHook = no_fault,
) -> Iterator[PublishedOutput]:
    """Publish a validated immutable run and atomically select it as current."""

    if not isinstance(rendered, RenderedConfigureRun):
        raise TypeError("rendered_configure_run_required")
    root = Path(output_root)
    if output_guard is not None:
        _validate_output_root_guard(root, output_guard)
    ancestor_guard = capture_plain_ancestor_guard(root)
    if path_lexists(root):
        require_plain_directory(root)
        lock_candidate = root / ".publish.lock"
        if path_lexists(lock_candidate):
            plain_file_status(lock_candidate)
    _ensure_layout(root, output_guard=output_guard)
    layout_guards = _capture_layout_guards(root)
    with ExclusiveFileLock(
        root / ".publish.lock",
        expected_parent_identity=(
            output_guard.identity if output_guard is not None else None
        ),
        path_guard=output_guard,
    ):
        if output_guard is not None:
            _validate_output_root_guard(root, output_guard)
        layout_guards = _capture_layout_guards(root)
        ancestor_guard.validate()
        _validate_layout_guards(layout_guards)
        fault_hook("after_lock")
        _validate_layout_guards(layout_guards)
        owning = (
            publication_authorization is not None
            and publication_authorization.kind == "OWNING_ACTIVE_CLAIM"
        )
        if owning:
            resumed = _resume_live_start_publication_locked(
                rendered=rendered,
                output_root=root,
                authorization=publication_authorization,
                fault_hook=fault_hook,
            )
            if resumed is not None:
                published, journal_path, transaction = resumed
                try:
                    yield published
                finally:
                    _finish_live_start_publication_locked(
                        authorization=publication_authorization,
                        published=published,
                        journal_path=journal_path,
                        transaction=transaction,
                        fault_hook=fault_hook,
                    )
                return
        current = _reconcile_locked(root)
        if (
            current is not None
            and current.content_root_sha256
            == rendered.content_root_sha256
            and current.revision_root.name
            == f"sha256-{rendered.content_root_sha256}"
        ):
            _validate_layout_guards(layout_guards)
            published = replace(current, reused_existing_revision=True)
            if owning:
                journal_path, transaction = _bind_reused_live_start_publication_locked(
                    rendered=rendered,
                    output_root=root,
                    current=published,
                    authorization=publication_authorization,
                )
                try:
                    yield published
                finally:
                    _finish_live_start_publication_locked(
                        authorization=publication_authorization,
                        published=published,
                        journal_path=journal_path,
                        transaction=transaction,
                        fault_hook=fault_hook,
                    )
            else:
                yield published
            return
        pointer_snapshot = _snapshot_pointer(root)
        transaction = _new_transaction(
            rendered,
            current,
            schema_version=(
                _LIVE_START_TRANSACTION_SCHEMA_VERSION
                if owning
                else _TRANSACTION_SCHEMA_VERSION
            ),
        )
        journal_path = _journal_path(root, transaction.transaction_id)
        _write_transaction(
            journal_path,
            transaction,
            fault_hook=fault_hook,
        )

        staging_root = root / transaction.staging
        staging_identity = secure_create_directory(
            staging_root,
            expected_parent_identity=path_identity(staging_root.parent),
        )
        _validate_layout_guards(layout_guards)
        if path_identity(staging_root) != staging_identity:
            raise ValueError("publication_staging_identity_mismatch")
        transaction = replace(
            transaction,
            staging_identity=staging_identity,
            phase="staging_owned",
        )
        _write_transaction(
            journal_path,
            transaction,
            fault_hook=fault_hook,
        )
        _write_rendered_run(rendered, staging_root)
        _validate_layout_guards(layout_guards)
        fault_hook("after_staging_render")
        _validate_layout_guards(layout_guards)
        staged = snapshot_and_verify_revision(staging_root)
        if (
            staged.manifest.content_root_sha256
            != rendered.content_root_sha256
            or staged.manifest.deck_name != rendered.model.deck_name
            or staged.manifest.deck_fingerprint
            != rendered.model.deck_fingerprint
        ):
            raise ValueError("staged_revision_identity_mismatch")
        transaction = replace(transaction, phase="staging_verified")
        _write_transaction(
            journal_path,
            transaction,
            fault_hook=fault_hook,
        )
        fault_hook("after_staging_verify")
        _validate_layout_guards(layout_guards)

        revision_root = root / transaction.revision
        reused = path_lexists(revision_root)
        if reused:
            require_plain_directory(revision_root)
            existing = snapshot_and_verify_revision(revision_root)
            if (
                existing.manifest.content_root_sha256
                != rendered.content_root_sha256
                or existing.manifest.deck_name != rendered.model.deck_name
                or existing.manifest.deck_fingerprint
                != rendered.model.deck_fingerprint
            ):
                raise ValueError("publication_digest_target_conflict")
            _remove_owned_tree(
                staging_root,
                expected_identity=staging_identity,
            )
            if owning:
                journal_path, transaction = (
                    _adopt_existing_revision_owner_for_live_start_locked(
                        output_root=root,
                        coordinator_path=journal_path,
                        coordinator=transaction,
                        revision_root=revision_root,
                    )
                )
            else:
                transaction = replace(
                    transaction,
                    staging_identity=None,
                    revision_identity=path_identity(revision_root),
                    owns_revision=False,
                    phase="revision_ready",
                )
        else:
            _validate_layout_guards(layout_guards)
            revisions_identity = path_identity(staging_root.parent)
            secure_replace(
                staging_root,
                revision_root,
                expected_source_identity=staging_identity,
                expected_source_parent_identity=revisions_identity,
                expected_target_parent_identity=revisions_identity,
                expected_target_absent=True,
            )
            _validate_layout_guards(layout_guards)
            revision_identity = path_identity(revision_root)
            if revision_identity != staging_identity:
                raise ValueError("publication_revision_identity_mismatch")
            transaction = replace(
                transaction,
                staging_identity=None,
                revision_identity=revision_identity,
                owns_revision=True,
                phase="revision_ready",
            )
        _write_transaction(
            journal_path,
            transaction,
            fault_hook=fault_hook,
        )
        fault_hook("after_revision_rename")
        _validate_layout_guards(layout_guards)

        publication = OutputPublication(
            schema_version=CURRENT_SCHEMA_VERSION,
            deck_name=rendered.model.deck_name,
            deck_fingerprint=rendered.model.deck_fingerprint,
            revision=transaction.revision,
            content_root_sha256=rendered.content_root_sha256,
        )
        fault_hook("before_pointer_replace")
        _validate_layout_guards(layout_guards)
        if owning:
            transaction = _commit_live_start_pointer_locked(
                output_root=root,
                pointer_snapshot=pointer_snapshot,
                publication=publication,
                transaction=transaction,
                journal_path=journal_path,
                authorization=publication_authorization,
                fault_hook=fault_hook,
            )
        else:
            _replace_pointer_if_unchanged(
                root,
                pointer_snapshot,
                output_publication_bytes(publication),
                transaction_id=transaction.transaction_id,
                fault_hook=fault_hook,
            )
            _validate_layout_guards(layout_guards)
            fault_hook("after_pointer_replace")
            _validate_layout_guards(layout_guards)
            transaction = replace(transaction, phase="pointer_committed")
            _write_transaction(
                journal_path,
                transaction,
                fault_hook=fault_hook,
            )

        selected, _verified = _resolve_current_publication_without_ads(root)
        if selected != publication:
            raise ValueError("publication_pointer_verification_failed")
        fault_hook("before_old_revision_cleanup")
        _validate_layout_guards(layout_guards)
        published = PublishedOutput(
            output_root=root,
            revision_root=revision_root,
            package_root=revision_root / "04_package",
            content_root_sha256=rendered.content_root_sha256,
            reused_existing_revision=reused,
        )
        if owning:
            try:
                yield published
            finally:
                _finish_live_start_publication_locked(
                    authorization=publication_authorization,
                    published=published,
                    journal_path=journal_path,
                    transaction=transaction,
                    fault_hook=fault_hook,
                )
        else:
            _cleanup_after_commit(
                root,
                transaction,
                journal_path,
                fault_hook=fault_hook,
            )
            _validate_layout_guards(layout_guards)
            yield published


def _publish_configure_run_unwrapped(
    rendered: RenderedConfigureRun,
    output_root: Path,
    *,
    fault_hook: FaultHook = no_fault,
) -> PublishedOutput:
    with _publish_configure_run_context(
        rendered,
        output_root,
        publication_authorization=None,
        fault_hook=fault_hook,
    ) as published:
        return published


def reconcile_output(output_root: Path) -> PublishedOutput | None:
    """Recover publisher-owned interrupted state and return verified current."""

    root = _canonical_output_root(output_root)
    if not path_lexists(root):
        return None
    _bootstrap_neutral_output_locks(output_root=root)
    with lease_output_operation_admission() as operation_lease:
        root_identity = path_identity(root)
        try:
            require_output_operation_allows_publication(
                lease=operation_lease,
                output_root=root,
                output_root_identity=root_identity,
            )
        except ValueError as error:
            if str(error) == "output_operation_admission_blocks_publication":
                raise ValueError(
                    "publisher_live_start_authority_active"
                ) from error
            raise
        with lease_output_child_bootstrap(output_root=root):
            if _claim_fingerprint(root) is not None:
                raise ValueError("publisher_live_start_authority_active")
            with hold_plain_directory(
                root,
                expected_identity=root_identity,
            ) as output_guard:
                return _reconcile_output_under_guard(
                    root,
                    output_guard=output_guard,
                )


def _reconcile_output_under_guard(
    root: Path,
    *,
    output_guard: PlainDirectoryMutationGuard,
) -> PublishedOutput | None:
    _validate_output_root_guard(root, output_guard)
    ancestor_guard = capture_plain_ancestor_guard(root / ".publish.lock")
    _validate_existing_layout(root, output_guard=output_guard)
    layout_guards = _capture_layout_guards(root)
    with ExclusiveFileLock(
        root / ".publish.lock",
        expected_parent_identity=output_guard.identity,
        path_guard=output_guard,
    ):
        output_guard.validate()
        layout_guards = _capture_layout_guards(root)
        ancestor_guard.validate()
        _validate_layout_guards(layout_guards)
        _reject_active_live_start_publication_locked(root)
        result = _reconcile_locked(root)
        _validate_layout_guards(layout_guards)
        output_guard.validate()
        return result


def _reject_active_live_start_publication_locked(output_root: Path) -> None:
    directory = output_root / ".publisher" / "transactions"
    require_plain_directory(directory)
    entries: list[os.DirEntry[str]] = []
    with os.scandir(directory) as iterator:
        for entry in iterator:
            if len(entries) >= _MAX_TRANSACTION_FILES * 3:
                raise ValueError("publisher_transaction_count_limit")
            entries.append(entry)
    for entry in sorted(entries, key=lambda row: row.name):
        if not (
            re.fullmatch(r"[0-9a-f]{32}\.json", entry.name)
            or re.fullmatch(r"\.[0-9a-f]{32}\.journal\.tmp", entry.name)
        ):
            continue
        path = Path(entry.path)
        status = path.lstat()
        if (
            not stat.S_ISREG(status.st_mode)
            or status_is_reparse(status)
            or status.st_nlink != 1
            or status.st_size > _MAX_TRANSACTION_FILE_BYTES
        ):
            raise ValueError("publisher_transaction_file_invalid")
        _require_plain_file_no_ads(path, status)
        transaction = _parse_transaction(
            read_file_no_follow(
                path,
                expected_status=status,
                maximum_size=_MAX_TRANSACTION_FILE_BYTES,
            )
        )
        if transaction.schema_version == _LIVE_START_TRANSACTION_SCHEMA_VERSION:
            raise ValueError("publisher_live_start_authority_active")


def validate_finalized_publication_authority(
    output_root: Path,
    publication: OutputPublication,
) -> None:
    """Validate the one immutable owner journal without performing recovery."""

    if not isinstance(publication, OutputPublication):
        raise TypeError("output_publication_required")
    root = Path(output_root)
    journals = _load_valid_transactions(root)
    owners = [
        transaction
        for _path, transaction in journals
        if transaction.owns_revision
        and transaction.revision == publication.revision
    ]
    if len(journals) != 1 or len(owners) != 1:
        raise ValueError("publisher_finalized_authority_invalid")
    owner = owners[0]
    revision_root = root / publication.revision
    if (
        owner.phase != "finalized"
        or owner.deck_name != publication.deck_name
        or owner.deck_fingerprint != publication.deck_fingerprint
        or owner.content_root_sha256 != publication.content_root_sha256
        or owner.revision_identity != path_identity(revision_root)
        or owner.staging_identity is not None
        or owner.previous_revision is not None
        or owner.previous_revision_identity is not None
        or owner.previous_owner_transaction_id is not None
    ):
        raise ValueError("publisher_finalized_authority_invalid")


def _reconcile_locked(output_root: Path) -> PublishedOutput | None:
    current: tuple[OutputPublication, Any] | None
    pointer_path = output_root / CURRENT_PATH
    if path_lexists(pointer_path):
        current = _resolve_current_publication_without_ads(output_root)
    else:
        current = None
    current_revision = current[0].revision if current is not None else None
    _recover_owned_atomic_temps(
        output_root,
        current_revision=current_revision,
        current=current,
    )
    journals = _load_valid_transactions(output_root)
    journal_identities = dict(
        getattr(journals, "identities", {})
    )
    _validate_publisher_residue(
        output_root,
        journals=journals,
        current_revision=current_revision,
    )

    recovered_journals: list[tuple[Path, _Transaction]] = []
    for journal_path, transaction in journals:
        recovered = _recover_interrupted_revision_move(
            output_root,
            journal_path,
            transaction,
        )
        if recovered != transaction:
            journal_identities[journal_path] = path_identity(journal_path)
        recovered_journals.append((journal_path, recovered))
    journals = recovered_journals
    journals = _canonicalize_legacy_finalized_owner(
        output_root,
        current=current,
        journals=journals,
        journal_identities=journal_identities,
    )

    current_owner: tuple[Path, _Transaction] | None = None
    for journal_path, transaction in journals:
        if transaction.revision == current_revision:
            if current_owner is None or transaction.owns_revision:
                current_owner = (journal_path, transaction)

    for journal_path, transaction in journals:
        staging_root = output_root / transaction.staging
        revision_root = output_root / transaction.revision
        if transaction.revision == current_revision:
            if not _cleanup_staging_if_owned(staging_root, transaction):
                raise ValueError(
                    "publisher_owned_staging_cleanup_incomplete"
                )
            if (
                transaction.previous_revision is not None
                and transaction.phase != "finalized"
            ):
                transaction = _continue_or_prepare_old_cleanup(
                    output_root,
                    transaction,
                    journal_path,
                    journals=journals,
                    fault_hook=no_fault,
                )
            if current_owner is not None and journal_path != current_owner[0]:
                _remove_file_if_plain(journal_path)
                continue
            if transaction.phase != "finalized":
                transaction = replace(
                    transaction,
                    staging_identity=None,
                    previous_revision=None,
                    previous_revision_identity=None,
                    previous_owner_transaction_id=None,
                    phase="finalized",
                )
                _write_transaction(journal_path, transaction)
            continue

        if (
            transaction.owns_revision
            and not path_lexists(revision_root)
            and current_owner is not None
            and current_owner[1].previous_revision == transaction.revision
        ):
            _remove_file_if_plain(journal_path)
            continue

        if current_revision == transaction.previous_revision or current is None:
            staging_cleanup_complete = _cleanup_staging_if_owned(
                staging_root,
                transaction,
            )
            revision_cleanup_complete = True
            if transaction.owns_revision:
                revision_cleanup_complete = _remove_owned_tree_if_present(
                    revision_root,
                    expected_identity=transaction.revision_identity,
                    require_verified_root=transaction.content_root_sha256,
                )
            if not revision_cleanup_complete:
                raise ValueError(
                    "publisher_owned_revision_cleanup_incomplete"
                )
            if not staging_cleanup_complete:
                raise ValueError(
                    "publisher_owned_staging_cleanup_incomplete"
                )
            _remove_file_if_plain(journal_path)

    if current is None:
        return None
    publication = current[0]
    _cleanup_detached_owned_revisions(output_root, publication)
    revision_root = output_root / publication.revision
    return PublishedOutput(
        output_root=output_root,
        revision_root=revision_root,
        package_root=revision_root / "04_package",
        content_root_sha256=publication.content_root_sha256,
        reused_existing_revision=True,
    )


def _canonicalize_legacy_finalized_owner(
    output_root: Path,
    *,
    current: tuple[OutputPublication, Any] | None,
    journals: list[tuple[Path, _Transaction]],
    journal_identities: dict[Path, tuple[int, int, int]],
) -> list[tuple[Path, _Transaction]]:
    if current is None:
        return journals
    publication, verified = current
    candidates = [
        (path, transaction)
        for path, transaction in journals
        if transaction.phase == "finalized"
        and transaction.owns_revision
        and transaction.revision == publication.revision
        and transaction.previous_revision is not None
    ]
    if not candidates:
        return journals
    if len(candidates) != 1 or len(journals) != 1:
        raise ValueError("publisher_finalized_legacy_authority_invalid")
    journal_path, owner = candidates[0]
    if (
        owner.previous_revision_identity is not None
        or owner.previous_owner_transaction_id is not None
        or not _current_owner_canonicalization_is_safe(
            output_root,
            current=(publication, verified),
            owner=owner,
        )
    ):
        raise ValueError("publisher_finalized_legacy_authority_invalid")
    repaired = replace(owner, previous_revision=None)
    expected_identity = journal_identities.get(journal_path)
    if expected_identity is None:
        raise ValueError("publisher_finalized_legacy_authority_invalid")
    _write_transaction(
        journal_path,
        repaired,
        expected_target_identity=expected_identity,
        expected_target_content=_transaction_bytes(owner),
    )
    return [(journal_path, repaired)]


def _current_owner_canonicalization_is_safe(
    output_root: Path,
    *,
    current: tuple[OutputPublication, Any],
    owner: _Transaction,
) -> bool:
    publication, verified = current
    previous_revision = owner.previous_revision
    if (
        not owner.owns_revision
        or owner.revision != publication.revision
        or previous_revision is None
        or previous_revision == owner.revision
        or owner.staging_identity is not None
        or path_lexists(output_root / owner.staging)
        or path_lexists(output_root / previous_revision)
    ):
        return False
    revision_root = output_root / publication.revision
    manifest = verified.manifest
    return (
        owner.revision_identity == path_identity(revision_root)
        and owner.deck_name == publication.deck_name
        and owner.deck_fingerprint == publication.deck_fingerprint
        and owner.content_root_sha256 == publication.content_root_sha256
        and manifest.deck_name == publication.deck_name
        and manifest.deck_fingerprint == publication.deck_fingerprint
        and manifest.content_root_sha256 == publication.content_root_sha256
    )


def _cleanup_detached_owned_revisions(
    output_root: Path,
    publication: OutputPublication,
) -> None:
    """Converge verified owned history through the crash-safe cleanup journal."""

    current_revision = publication.revision
    current_root = output_root / current_revision
    while True:
        journals = _load_valid_transactions(output_root)
        current_owners = [
            (path, transaction)
            for path, transaction in journals
            if transaction.revision == current_revision
            and transaction.owns_revision
        ]
        if len(current_owners) != 1:
            raise ValueError("publisher_current_owner_invalid")
        _current_owner_path, current_owner = current_owners[0]
        current_identity = path_identity(current_root)
        verified_current = snapshot_and_verify_revision(current_root)
        if (
            current_owner.phase != "finalized"
            or current_owner.revision_identity != current_identity
            or current_owner.deck_name != publication.deck_name
            or current_owner.deck_fingerprint
            != publication.deck_fingerprint
            or current_owner.content_root_sha256
            != publication.content_root_sha256
            or verified_current.manifest.deck_name
            != publication.deck_name
            or verified_current.manifest.deck_fingerprint
            != publication.deck_fingerprint
            or verified_current.manifest.content_root_sha256
            != publication.content_root_sha256
        ):
            raise ValueError("publisher_current_owner_invalid")

        revision_names: list[str] = []
        with os.scandir(output_root / "revisions") as iterator:
            for entry in iterator:
                if len(revision_names) >= _MAX_TRANSACTION_FILES * 2 + 1:
                    raise ValueError("publisher_residue_count_limit")
                status = Path(entry.path).lstat()
                if (
                    status_is_reparse(status)
                    or not stat.S_ISDIR(status.st_mode)
                ):
                    raise ValueError("publisher_revision_residue_invalid")
                revision_names.append(entry.name)
        stale_names = sorted(
            name
            for name in revision_names
            if name != Path(current_revision).name
        )
        if not stale_names:
            if len(journals) != 1 or journals[0][1] != current_owner:
                raise ValueError("publisher_noncurrent_journal_residue")
            _require_exact_directory_entries(
                output_root / "revisions",
                allowed={Path(current_revision).name},
                maximum=2,
                directories_only=True,
            )
            return

        stale_revision = f"revisions/{stale_names[0]}"
        owners = [
            (path, transaction)
            for path, transaction in journals
            if transaction.revision == stale_revision
            and transaction.owns_revision
        ]
        if len(owners) != 1:
            raise ValueError("publisher_cleanup_owner_ambiguous")
        _owner_path, owner = owners[0]
        if owner.phase != "finalized":
            raise ValueError("publisher_cleanup_owner_not_finalized")
        active_references = [
            transaction
            for _path, transaction in journals
            if transaction.transaction_id != owner.transaction_id
            and transaction.phase != "finalized"
            and (
                transaction.revision == stale_revision
                or transaction.previous_revision == stale_revision
            )
        ]
        if active_references:
            raise ValueError("publisher_cleanup_reference_ambiguous")
        stale_root = output_root / stale_revision
        stale_identity = path_identity(stale_root)
        verified_stale = snapshot_and_verify_revision(stale_root)
        if (
            owner.revision_identity != stale_identity
            or owner.revision
            != f"revisions/sha256-{owner.content_root_sha256}"
            or verified_stale.manifest.content_root_sha256
            != owner.content_root_sha256
            or verified_stale.manifest.deck_name != owner.deck_name
            or verified_stale.manifest.deck_fingerprint
            != owner.deck_fingerprint
        ):
            raise ValueError("publisher_cleanup_manifest_mismatch")

        coordinator_id = uuid.uuid4().hex
        coordinator = _Transaction(
            schema_version=_TRANSACTION_SCHEMA_VERSION,
            transaction_id=coordinator_id,
            deck_name=publication.deck_name,
            deck_fingerprint=publication.deck_fingerprint,
            content_root_sha256=publication.content_root_sha256,
            staging=f"revisions/.staging-{coordinator_id}",
            revision=current_revision,
            previous_revision=stale_revision,
            previous_revision_identity=None,
            previous_owner_transaction_id=None,
            staging_identity=None,
            revision_identity=current_identity,
            owns_revision=False,
            phase="pointer_committed",
        )
        coordinator_path = _journal_path(output_root, coordinator_id)
        _write_transaction(coordinator_path, coordinator)
        _cleanup_after_commit(
            output_root,
            coordinator,
            coordinator_path,
            fault_hook=no_fault,
        )


def _validate_publisher_residue(
    output_root: Path,
    *,
    journals: list[tuple[Path, _Transaction]],
    current_revision: str | None,
) -> None:
    if current_revision is not None:
        current_owners = [
            transaction
            for _path, transaction in journals
            if transaction.revision == current_revision
            and transaction.owns_revision
            and transaction.revision_identity is not None
        ]
        if len(current_owners) != 1:
            raise ValueError("publisher_current_owner_invalid")
    allowed_root = {
        ".publish.lock",
        ".publisher",
        "revisions",
        *(("current.json",) if current_revision is not None else ()),
    }
    _require_exact_directory_entries(
        output_root,
        allowed=allowed_root,
        maximum=10,
    )
    _require_exact_directory_entries(
        output_root / ".publisher",
        allowed={"transactions"},
        maximum=4,
    )
    allowed_revisions: set[str] = set()
    if current_revision is not None:
        allowed_revisions.add(Path(current_revision).name)
    for _journal_path, transaction in journals:
        if path_lexists(output_root / transaction.staging):
            allowed_revisions.add(Path(transaction.staging).name)
        if path_lexists(output_root / transaction.revision):
            allowed_revisions.add(Path(transaction.revision).name)
    _require_exact_directory_entries(
        output_root / "revisions",
        allowed=allowed_revisions,
        maximum=_MAX_TRANSACTION_FILES * 2 + 1,
        directories_only=True,
    )


def _require_exact_directory_entries(
    directory: Path,
    *,
    allowed: set[str],
    maximum: int,
    directories_only: bool = False,
) -> None:
    require_plain_directory(directory)
    names: list[str] = []
    folded: set[str] = set()
    with os.scandir(directory) as iterator:
        for entry in iterator:
            if len(names) >= maximum:
                raise ValueError("publisher_residue_count_limit")
            child = Path(entry.path)
            status = child.lstat()
            if status_is_reparse(status):
                raise ValueError("publisher_residue_reparse")
            if directories_only and not stat.S_ISDIR(status.st_mode):
                raise ValueError("publisher_revision_residue_invalid")
            folded_name = entry.name.casefold()
            if folded_name in folded:
                raise ValueError("publisher_residue_casefold_collision")
            folded.add(folded_name)
            names.append(entry.name)
    if set(names) != allowed:
        raise ValueError("publisher_residue_invalid")


def _recover_interrupted_revision_move(
    output_root: Path,
    journal_path: Path,
    transaction: _Transaction,
) -> _Transaction:
    """Close the rename-to-journal window using the recorded inode identity."""

    if (
        transaction.phase not in {"staging_owned", "staging_verified"}
        or transaction.staging_identity is None
    ):
        return transaction
    staging_root = output_root / transaction.staging
    revision_root = output_root / transaction.revision
    try:
        staging_identity = path_identity(staging_root)
    except FileNotFoundError:
        staging_identity = None
    try:
        revision_identity = path_identity(revision_root)
    except FileNotFoundError:
        revision_identity = None
    if staging_identity is not None:
        return transaction
    if revision_identity != transaction.staging_identity:
        return transaction
    try:
        verified = snapshot_and_verify_revision(revision_root)
    except Exception:
        return transaction
    if (
        verified.manifest.content_root_sha256
        != transaction.content_root_sha256
        or verified.manifest.deck_name != transaction.deck_name
        or verified.manifest.deck_fingerprint
        != transaction.deck_fingerprint
    ):
        return transaction
    recovered = replace(
        transaction,
        staging_identity=None,
        revision_identity=revision_identity,
        owns_revision=True,
        phase="revision_ready",
    )
    _write_transaction(journal_path, recovered)
    return recovered


def _cleanup_after_commit(
    output_root: Path,
    transaction: _Transaction,
    journal_path: Path,
    *,
    fault_hook: FaultHook,
) -> None:
    if transaction.previous_revision is not None:
        journals = _load_valid_transactions(output_root)
        transaction = _continue_or_prepare_old_cleanup(
            output_root,
            transaction,
            journal_path,
            journals=journals,
            fault_hook=fault_hook,
        )
    current_owner = transaction
    if not transaction.owns_revision:
        for other_path, other in _load_valid_transactions(output_root):
            if (
                other_path != journal_path
                and other.revision == transaction.revision
                and other.owns_revision
            ):
                current_owner = other
                _remove_file_if_plain(journal_path)
                break
    if current_owner is transaction:
        _write_transaction(
            journal_path,
            replace(
                transaction,
                staging_identity=None,
                previous_revision=None,
                previous_revision_identity=None,
                previous_owner_transaction_id=None,
                phase="finalized",
            ),
            fault_hook=fault_hook,
        )


def _continue_or_prepare_old_cleanup(
    output_root: Path,
    transaction: _Transaction,
    journal_path: Path,
    *,
    journals: list[tuple[Path, _Transaction]],
    fault_hook: FaultHook,
) -> _Transaction:
    previous_revision = transaction.previous_revision
    if (
        previous_revision is None
        or previous_revision == transaction.revision
    ):
        return transaction
    previous_root = output_root / previous_revision
    try:
        actual_identity = path_identity(previous_root)
    except FileNotFoundError:
        actual_identity = None
    if transaction.phase == "cleanup_started":
        if actual_identity is None:
            owner_path = next(
                (
                    path
                    for path, candidate in journals
                    if candidate.transaction_id
                    == transaction.previous_owner_transaction_id
                    and candidate.revision == previous_revision
                    and candidate.owns_revision
                    and candidate.revision_identity
                    == transaction.previous_revision_identity
                ),
                None,
            )
            if owner_path is not None:
                _remove_file_if_plain(owner_path)
            return transaction
        owner = next(
            (
                (path, candidate)
                for path, candidate in journals
                if candidate.transaction_id
                == transaction.previous_owner_transaction_id
                and candidate.revision == previous_revision
                and candidate.owns_revision
                and candidate.revision_identity
                == transaction.previous_revision_identity
            ),
            None,
        )
        if owner is None:
            raise ValueError("publisher_cleanup_owner_missing")
        owner_path, _owner_transaction = owner
        if actual_identity != transaction.previous_revision_identity:
            raise ValueError("publisher_cleanup_identity_changed")
    else:
        matching = [
            (path, candidate)
            for path, candidate in journals
            if candidate.revision == previous_revision
            and candidate.owns_revision
            and candidate.revision_identity == actual_identity
        ]
        if len(matching) != 1:
            raise ValueError("publisher_cleanup_owner_ambiguous")
        owner_path, owner_transaction = matching[0]
        verified = snapshot_and_verify_revision(previous_root)
        if (
            verified.manifest.content_root_sha256
            != owner_transaction.content_root_sha256
            or verified.manifest.deck_name != owner_transaction.deck_name
            or verified.manifest.deck_fingerprint
            != owner_transaction.deck_fingerprint
        ):
            raise ValueError("publisher_cleanup_manifest_mismatch")
        transaction = replace(
            transaction,
            previous_revision_identity=actual_identity,
            previous_owner_transaction_id=owner_transaction.transaction_id,
            phase="cleanup_started",
        )
        _write_transaction(
            journal_path,
            transaction,
            fault_hook=fault_hook,
        )
    _remove_owned_tree(
        previous_root,
        expected_identity=transaction.previous_revision_identity,
        after_first_delete=lambda: fault_hook(
            "during_old_revision_cleanup"
        ),
    )
    _remove_file_if_plain(owner_path)
    return transaction


def _cleanup_staging_if_owned(
    staging_root: Path,
    transaction: _Transaction,
) -> bool:
    if transaction.staging_identity is None:
        return not path_lexists(staging_root)
    return _remove_owned_tree_if_present(
        staging_root,
        expected_identity=transaction.staging_identity,
    )


def _remove_owned_tree_if_present(
    path: Path,
    *,
    expected_identity: tuple[int, int, int] | None,
    require_verified_root: str | None = None,
) -> bool:
    if expected_identity is None:
        return False
    try:
        current_identity = path_identity(path)
    except FileNotFoundError:
        return True
    if current_identity != expected_identity:
        return False
    if require_verified_root is not None:
        try:
            verified = snapshot_and_verify_revision(path)
        except Exception:
            return False
        if verified.manifest.content_root_sha256 != require_verified_root:
            return False
    _remove_owned_tree(path, expected_identity=expected_identity)
    return True


def _remove_owned_tree(
    path: Path,
    *,
    expected_identity: tuple[int, int, int],
    after_first_delete: Callable[[], None] | None = None,
) -> None:
    if path_identity(path) != expected_identity:
        raise ValueError("publisher_owned_path_identity_changed")
    rows: list[tuple[Path, os.stat_result]] = []
    pending = [(path, "", 0)]
    directory_count = 0
    node_count = 0
    while pending:
        directory_path, prefix, depth = pending.pop()
        if depth > MAX_FILESYSTEM_DEPTH:
            raise ValueError("publisher_owned_path_depth_limit")
        directory_status = directory_path.lstat()
        if (
            not stat.S_ISDIR(directory_status.st_mode)
            or status_is_reparse(directory_status)
        ):
            raise ValueError("publisher_owned_path_reparse")
        count = 0
        with os.scandir(directory_path) as iterator:
            for entry in iterator:
                count += 1
                if count > MAX_FILESYSTEM_ENTRIES_PER_DIRECTORY:
                    raise ValueError(
                        "publisher_owned_path_directory_entry_limit"
                    )
                node_count += 1
                if node_count > MAX_FILESYSTEM_NODES:
                    raise ValueError("publisher_owned_path_node_limit")
                child = Path(entry.path)
                status = child.lstat()
                if status_is_reparse(status) or entry.is_symlink():
                    raise ValueError("publisher_owned_path_reparse")
                relative = f"{prefix}{entry.name}"
                if len(relative.encode("utf-8")) > MAX_RUN_PATH_BYTES:
                    raise ValueError(
                        "publisher_owned_path_length_limit"
                    )
                if canonical_relative_path(relative) != relative:
                    raise ValueError("publisher_owned_path_invalid")
                rows.append((child, status))
                if stat.S_ISDIR(status.st_mode):
                    directory_count += 1
                    if directory_count > MAX_FILESYSTEM_DIRECTORIES:
                        raise ValueError(
                            "publisher_owned_path_directory_limit"
                        )
                    pending.append(
                        (child, f"{relative}/", depth + 1)
                    )
                elif not stat.S_ISREG(status.st_mode):
                    raise ValueError(
                        "publisher_owned_path_entry_invalid"
                    )
    deleted_one = False
    for child, expected_status in sorted(
        rows,
        key=lambda row: len(row[0].parts),
        reverse=True,
    ):
        try:
            current = child.lstat()
        except FileNotFoundError:
            continue
        if _identity(current) != _identity(expected_status):
            raise ValueError("publisher_owned_path_identity_changed")
        if stat.S_ISDIR(current.st_mode):
            secure_rmdir(
                child,
                expected_identity=_identity(expected_status),
                expected_parent_identity=path_identity(child.parent),
            )
        else:
            secure_unlink(
                child,
                expected_identity=_identity(expected_status),
                expected_parent_identity=path_identity(child.parent),
            )
        if not deleted_one:
            deleted_one = True
            if after_first_delete is not None:
                after_first_delete()
    if path_identity(path) != expected_identity:
        raise ValueError("publisher_owned_path_identity_changed")
    secure_rmdir(
        path,
        expected_identity=expected_identity,
        expected_parent_identity=path_identity(path.parent),
    )


def _new_transaction(
    rendered: RenderedConfigureRun,
    current: PublishedOutput | None,
    *,
    schema_version: int = _TRANSACTION_SCHEMA_VERSION,
) -> _Transaction:
    transaction_id = uuid.uuid4().hex
    return _Transaction(
        schema_version=schema_version,
        transaction_id=transaction_id,
        deck_name=rendered.model.deck_name,
        deck_fingerprint=rendered.model.deck_fingerprint,
        content_root_sha256=rendered.content_root_sha256,
        staging=f"revisions/.staging-{transaction_id}",
        revision=f"revisions/sha256-{rendered.content_root_sha256}",
        previous_revision=(
            current.revision_root.relative_to(
                current.output_root
            ).as_posix()
            if current is not None
            else None
        ),
        previous_revision_identity=None,
        previous_owner_transaction_id=None,
        staging_identity=None,
        revision_identity=None,
        owns_revision=False,
        phase="prepared",
    )


def _write_rendered_run(
    rendered: RenderedConfigureRun,
    destination: Path,
) -> None:
    """Write immutable bytes without following or overwriting any path."""

    guard = capture_plain_ancestor_guard(destination)
    require_plain_directory(destination)
    root_identity = path_identity(destination)
    owned_directories: dict[Path, tuple[int, int, int]] = {
        destination: root_identity
    }
    content = tuple(
        artifact
        for artifact in rendered.artifacts
        if artifact.relative_path != "package_manifest.json"
    )
    manifests = tuple(
        artifact
        for artifact in rendered.artifacts
        if artifact.relative_path == "package_manifest.json"
    )
    if len(manifests) != 1:
        raise ValueError("rendered_configure_run_manifest_missing")
    for artifact in (*content, *manifests):
        guard.validate()
        if path_identity(destination) != root_identity:
            raise ValueError("publication_staging_identity_changed")
        target = destination / artifact.relative_path
        current = destination
        for part in Path(artifact.relative_path).parts[:-1]:
            current /= part
            if current not in owned_directories:
                if path_lexists(current):
                    raise ValueError("publication_staging_path_preexisting")
                created_identity = secure_create_directory(
                    current,
                    expected_parent_identity=owned_directories[
                        current.parent
                    ],
                )
                require_plain_directory(current)
                if path_identity(current) != created_identity:
                    raise ValueError(
                        "publication_staging_directory_changed"
                    )
                owned_directories[current] = created_identity
            elif path_identity(current) != owned_directories[current]:
                raise ValueError("publication_staging_directory_changed")
        if path_lexists(target):
            raise ValueError("publication_staging_path_preexisting")
        descriptor = secure_open_file_descriptor(
            target,
            create=True,
            write=True,
            expected_parent_identity=owned_directories[target.parent],
        )
        try:
            opened = os.fstat(descriptor)
            target_status = target.lstat()
            if (
                path_identity_from_status(opened)
                != path_identity_from_status(target_status)
                or not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or status_is_reparse(target_status)
            ):
                raise ValueError("publication_staging_file_identity_invalid")
            with os.fdopen(descriptor, "wb", closefd=False) as handle:
                handle.write(artifact.content)
                handle.flush()
                os.fsync(descriptor)
            if (
                path_identity(target)
                != path_identity_from_status(opened)
                or any(
                    path_identity(path) != identity
                    for path, identity in owned_directories.items()
                )
            ):
                raise ValueError("publication_staging_path_changed")
        finally:
            os.close(descriptor)
        status = plain_file_status(target)
        _require_plain_file_no_ads(target, status)
        if read_file_no_follow(
            target,
            expected_status=status,
            maximum_size=len(artifact.content),
        ) != artifact.content:
            raise ValueError("publication_staging_write_failed")
    guard.validate()
    if path_identity(destination) != root_identity:
        raise ValueError("publication_staging_identity_changed")


def _replace_pointer_if_unchanged(
    output_root: Path,
    before: _PointerSnapshot,
    content: bytes,
    *,
    transaction_id: str,
    fault_hook: FaultHook,
) -> None:
    """Commit the pointer for cooperative publishers holding ``.publish.lock``.

    The comparison and target-identity binding protect against stale
    cooperative state, injected crash faults, and replacement in the final
    kernel commit window.
    """
    pointer_path = output_root / CURRENT_PATH

    def compare_and_swap() -> None:
        if _snapshot_pointer(output_root) != before:
            raise ValueError("current_output_concurrent_change")

    _owned_atomic_replace(
        pointer_path,
        content,
        temp_path=(
            output_root
            / ".publisher"
            / "transactions"
            / f".{transaction_id}.current.tmp"
        ),
        before_replace=compare_and_swap,
        expected_target_identity=(
            None if before.identity is None else before.identity[:3]
        ),
        expected_target_content=before.content,
        expected_target_absent=not before.existed,
        fault_hook=fault_hook,
        temp_stage="after_pointer_temp_write",
    )


def _owned_atomic_replace(
    target: Path,
    content: bytes,
    *,
    temp_path: Path,
    before_replace: Callable[[], None] | None = None,
    expected_target_identity: tuple[int, int, int] | None = None,
    expected_target_content: bytes | None = None,
    expected_target_absent: bool | None = None,
    fault_hook: FaultHook = no_fault,
    temp_stage: str,
    identity_bound_content: Callable[
        [tuple[int, int, int]], bytes
    ]
    | None = None,
) -> tuple[tuple[int, int, int], bytes]:
    target_must_be_absent = (
        expected_target_identity is None
        if expected_target_absent is None
        else expected_target_absent
    )
    if target_must_be_absent and expected_target_identity is not None:
        raise ValueError("publisher_owned_target_binding_invalid")
    if path_lexists(temp_path):
        raise ValueError("publisher_owned_temp_preexisting")
    parent_guard = capture_plain_ancestor_guard(target.parent)
    require_plain_directory(target.parent)
    require_plain_directory(temp_path.parent)
    target_parent_identity = path_identity(target.parent)
    temp_parent_identity = path_identity(temp_path.parent)
    descriptor = secure_open_file_descriptor(
        temp_path,
        create=True,
        write=True,
        expected_parent_identity=temp_parent_identity,
    )
    try:
        opened = os.fstat(descriptor)
        temp_status = temp_path.lstat()
        if (
            path_identity_from_status(opened)
            != path_identity_from_status(temp_status)
            or status_is_reparse(temp_status)
            or opened.st_nlink != 1
        ):
            raise ValueError("publisher_owned_temp_identity_invalid")
        temp_identity = path_identity_from_status(opened)
        published_content = (
            content
            if identity_bound_content is None
            else identity_bound_content(temp_identity)
        )
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(published_content)
            handle.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)
    parent_guard.validate()
    status = plain_file_status(temp_path)
    _require_plain_file_no_ads(temp_path, status)
    if read_file_no_follow(
        temp_path,
        expected_status=status,
        maximum_size=len(published_content),
    ) != published_content:
        raise ValueError("publisher_owned_temp_verification_failed")
    fault_hook(temp_stage)
    if before_replace is not None:
        before_replace()
    parent_guard.validate()
    _validate_owned_replace_target(
        target,
        expected_identity=expected_target_identity,
        expected_content=expected_target_content,
        expected_target_absent=target_must_be_absent,
    )
    secure_replace(
        temp_path,
        target,
        expected_source_identity=path_identity_from_status(status),
        expected_source_parent_identity=temp_parent_identity,
        expected_target_parent_identity=target_parent_identity,
        expected_target_identity=expected_target_identity,
        expected_target_absent=target_must_be_absent,
    )
    parent_guard.validate()
    return temp_identity, published_content


def _validate_owned_replace_target(
    target: Path,
    *,
    expected_identity: tuple[int, int, int] | None,
    expected_content: bytes | None,
    expected_target_absent: bool | None = None,
) -> None:
    target_must_be_absent = (
        expected_identity is None
        if expected_target_absent is None
        else expected_target_absent
    )
    if target_must_be_absent:
        if (
            expected_identity is not None
            or expected_content is not None
            or path_lexists(target)
        ):
            raise ValueError("publisher_owned_target_changed")
        return
    if expected_identity is None:
        raise ValueError("publisher_owned_target_changed")
    try:
        status = plain_file_status(target)
    except (OSError, ValueError) as error:
        raise ValueError("publisher_owned_target_changed") from error
    if path_identity_from_status(status) != expected_identity:
        raise ValueError("publisher_owned_target_changed")
    _require_plain_file_no_ads(target, status)
    try:
        if (
            expected_content is not None
            and read_file_no_follow(
                target,
                expected_status=status,
                maximum_size=_MAX_TRANSACTION_FILE_BYTES,
            )
            != expected_content
        ):
            raise ValueError("publisher_owned_target_changed")
    except (OSError, ValueError) as error:
        raise ValueError("publisher_owned_target_changed") from error


def _resolve_current_publication_without_ads(
    output_root: Path,
) -> tuple[OutputPublication, Any]:
    pointer_path = output_root / CURRENT_PATH
    status = plain_file_status(pointer_path)
    _require_plain_file_no_ads(pointer_path, status)
    return resolve_current_publication_unlocked(output_root)


def _snapshot_pointer(output_root: Path) -> _PointerSnapshot:
    pointer_path = output_root / CURRENT_PATH
    try:
        status = plain_file_status(pointer_path)
    except FileNotFoundError:
        return _PointerSnapshot(False, None, None)
    _require_plain_file_no_ads(pointer_path, status)
    content = read_file_no_follow(
        pointer_path,
        expected_status=status,
        maximum_size=1024 * 1024,
    )
    return _PointerSnapshot(True, content, _file_state(status))


def _validate_output_root_guard(
    output_root: Path,
    output_guard: PlainDirectoryMutationGuard,
) -> None:
    if Path(output_root) != output_guard.path:
        raise ValueError("filesystem_path_identity_changed")
    output_guard.validate()


def _ensure_layout(
    output_root: Path,
    *,
    output_guard: PlainDirectoryMutationGuard | None = None,
) -> None:
    if output_guard is None:
        _secure_create_directory_chain(output_root)
    else:
        _validate_output_root_guard(output_root, output_guard)
    for child in (
        output_root / "revisions",
        output_root / ".publisher",
        output_root / ".publisher" / "transactions",
    ):
        if output_guard is not None:
            _validate_output_root_guard(output_root, output_guard)
        if not path_lexists(child):
            try:
                secure_create_directory(
                    child,
                    expected_parent_identity=(
                        output_guard.identity
                        if output_guard is not None
                        and child.parent == output_root
                        else path_identity(child.parent)
                    ),
                )
            except FileExistsError:
                pass
        require_plain_directory(child)
        if output_guard is not None:
            _validate_output_root_guard(output_root, output_guard)
    lock_path = output_root / ".publish.lock"
    if output_guard is not None:
        _validate_output_root_guard(output_root, output_guard)
    if path_lexists(lock_path):
        plain_file_status(lock_path)
    if output_guard is not None:
        _validate_output_root_guard(output_root, output_guard)


def _secure_create_directory_chain(path: Path) -> None:
    missing: list[Path] = []
    current = Path(path).absolute()
    while not path_lexists(current):
        missing.append(current)
        current = current.parent
    require_plain_directory(current)
    guard = capture_plain_ancestor_guard(current)
    for directory in reversed(missing):
        guard.validate()
        try:
            secure_create_directory(
                directory,
                expected_parent_identity=path_identity(directory.parent),
            )
        except FileExistsError:
            require_plain_directory(directory)
        require_plain_directory(directory)
        guard = capture_plain_ancestor_guard(directory)


def _validate_existing_layout(
    output_root: Path,
    *,
    output_guard: PlainDirectoryMutationGuard | None = None,
) -> None:
    if output_guard is not None:
        _validate_output_root_guard(output_root, output_guard)
    require_plain_directory(output_root)
    for path in (
        output_root / "revisions",
        output_root / ".publisher",
        output_root / ".publisher" / "transactions",
    ):
        if output_guard is not None:
            _validate_output_root_guard(output_root, output_guard)
        require_plain_directory(path)
    if output_guard is not None:
        _validate_output_root_guard(output_root, output_guard)
    plain_file_status(output_root / ".publish.lock")
    if output_guard is not None:
        _validate_output_root_guard(output_root, output_guard)


def _capture_layout_guards(
    output_root: Path,
) -> tuple[FilesystemPathGuard, ...]:
    return (
        capture_plain_ancestor_guard(output_root / ".publish.lock"),
        capture_plain_ancestor_guard(output_root / "revisions"),
        capture_plain_ancestor_guard(
            output_root / ".publisher" / "transactions"
        ),
    )


def _validate_layout_guards(
    guards: tuple[FilesystemPathGuard, ...],
) -> None:
    for guard in guards:
        guard.validate()


def _journal_path(output_root: Path, transaction_id: str) -> Path:
    return (
        output_root
        / ".publisher"
        / "transactions"
        / f"{transaction_id}.json"
    )


def _preflight_live_start_transaction_temps(
    *,
    finals: Mapping[
        str,
        tuple[Path, _Transaction, tuple[int, int, int]],
    ],
    journal_temps: Mapping[
        str,
        tuple[Path, _Transaction, tuple[int, int, int]],
    ],
    pointer_temp_ids: frozenset[str],
    authority: _LiveStartTempRecoveryAuthority | None,
) -> None:
    if not journal_temps and not pointer_temp_ids:
        return
    for _path, transaction, _identity in journal_temps.values():
        if (
            transaction.schema_version
            == _LIVE_START_TRANSACTION_SCHEMA_VERSION
            and transaction.live_start_commit_receipt is None
        ):
            raise ValueError("publisher_transaction_temp_conflict")
    for transaction_id in pointer_temp_ids:
        final_row = finals.get(transaction_id)
        if (
            final_row is not None
            and final_row[1].schema_version
            == _LIVE_START_TRANSACTION_SCHEMA_VERSION
            and final_row[1].live_start_commit_receipt is None
        ):
            raise ValueError("publisher_transaction_temp_conflict")
    for _path, transaction, _identity in (
        *finals.values(),
        *journal_temps.values(),
    ):
        if transaction.schema_version != _LIVE_START_TRANSACTION_SCHEMA_VERSION:
            continue
        if authority is None:
            raise ValueError("publisher_live_start_authority_active")
        receipt = transaction.live_start_commit_receipt
        if receipt is not None:
            _require_live_start_temp_receipt_authority(
                receipt=receipt,
                authority=authority,
            )
    for transaction_id, (_path, transaction, _identity) in (
        journal_temps.items()
    ):
        if transaction.schema_version != _LIVE_START_TRANSACTION_SCHEMA_VERSION:
            continue
        receipt = transaction.live_start_commit_receipt
        if receipt is None:
            continue
        predecessor_identity = receipt.owner_journal_predecessor_identity
        if predecessor_identity is None:
            continue
        final_row = finals.get(transaction_id)
        if final_row is None or not _is_live_start_receipt_upgrade(
            final_row[1],
            transaction,
        ):
            raise ValueError("publisher_transaction_temp_conflict")
        if final_row[2] != predecessor_identity:
            raise ValueError("publisher_owned_target_changed")


def _recover_owned_atomic_temps(
    output_root: Path,
    *,
    current_revision: str | None,
    current: tuple[OutputPublication, Any] | None = None,
    preserve_bound_live_pointer_temps: bool = False,
    live_start_authority: _LiveStartTempRecoveryAuthority | None = None,
) -> frozenset[str]:
    directory = output_root / ".publisher" / "transactions"
    require_plain_directory(directory)
    entries: list[tuple[Path, os.stat_result]] = []
    with os.scandir(directory) as iterator:
        for entry in iterator:
            if len(entries) >= _MAX_TRANSACTION_FILES * 3:
                raise ValueError("publisher_transaction_count_limit")
            path = Path(entry.path)
            status = path.lstat()
            if (
                not stat.S_ISREG(status.st_mode)
                or status_is_reparse(status)
                or status.st_nlink != 1
                or status.st_size > _MAX_TRANSACTION_FILE_BYTES
            ):
                raise ValueError("publisher_transaction_file_invalid")
            entries.append((path, status))
    finals: dict[str, tuple[Path, _Transaction, tuple[int, int, int]]] = {}
    journal_temps: dict[
        str, tuple[Path, _Transaction, tuple[int, int, int]]
    ] = {}
    pointer_temps: list[
        tuple[
            str,
            Path,
            OutputPublication,
            tuple[int, int, int],
        ]
    ] = []
    for path, status in entries:
        _require_plain_file_no_ads(path, status)
        content = read_file_no_follow(
            path,
            expected_status=status,
            maximum_size=_MAX_TRANSACTION_FILE_BYTES,
        )
        final_match = re.fullmatch(r"([0-9a-f]{32})\.json", path.name)
        journal_match = re.fullmatch(
            r"\.([0-9a-f]{32})\.journal\.tmp",
            path.name,
        )
        pointer_match = re.fullmatch(
            r"\.([0-9a-f]{32})\.current\.tmp",
            path.name,
        )
        identity = path_identity_from_status(status)
        if final_match is not None:
            transaction = _parse_transaction(content)
            transaction_id = final_match.group(1)
            if transaction.transaction_id != transaction_id:
                raise ValueError("publisher_transaction_name_mismatch")
            _require_live_start_journal_identity(transaction, identity)
            finals[transaction_id] = (path, transaction, identity)
        elif journal_match is not None:
            transaction = _parse_transaction(content)
            transaction_id = journal_match.group(1)
            if transaction.transaction_id != transaction_id:
                raise ValueError("publisher_transaction_temp_mismatch")
            _require_live_start_journal_identity(transaction, identity)
            journal_temps[transaction_id] = (
                path,
                transaction,
                identity,
            )
        elif pointer_match is not None:
            pointer_temps.append(
                (
                    pointer_match.group(1),
                    path,
                    parse_output_publication(content),
                    identity,
                )
            )
        else:
            raise ValueError("publisher_transaction_residue_invalid")
    _preflight_live_start_transaction_temps(
        finals=finals,
        journal_temps=journal_temps,
        pointer_temp_ids=frozenset(row[0] for row in pointer_temps),
        authority=live_start_authority,
    )
    effective = dict(finals)
    journal_actions: list[
        tuple[
            str,
            Path,
            Path,
            tuple[int, int, int],
            tuple[int, int, int] | None,
            bytes | None,
        ]
    ] = []
    for transaction_id, temp_row in journal_temps.items():
        temp_path, temp_transaction, temp_identity = temp_row
        final_row = finals.get(transaction_id)
        final_path = _journal_path(output_root, transaction_id)
        if final_row is None:
            effective[transaction_id] = (
                final_path,
                temp_transaction,
                temp_identity,
            )
            journal_actions.append(
                (
                    "promote_create",
                    temp_path,
                    final_path,
                    temp_identity,
                    None,
                    None,
                )
            )
            continue
        _final_path, final_transaction, final_identity = final_row
        cleanup_successor = _is_finalized_canonical_successor(
            final_transaction,
            temp_transaction,
        )
        receipt_upgrade = _is_live_start_receipt_upgrade(
            final_transaction,
            temp_transaction,
        )
        canonical_successor = cleanup_successor or receipt_upgrade
        canonicalization_safe = (
            current is not None
            and (
                cleanup_successor
                and _current_owner_canonicalization_is_safe(
                    output_root,
                    current=current,
                    owner=final_transaction,
                )
                or receipt_upgrade
                and _current_owner_receipt_upgrade_is_safe(
                    output_root,
                    current=current,
                    owner=final_transaction,
                )
            )
        )
        if canonical_successor and (
            current is None
            or len(finals) != 1
            or len(journal_temps) != 1
            or pointer_temps
            or not canonicalization_safe
        ):
            raise ValueError("publisher_transaction_temp_conflict")
        if receipt_upgrade:
            receipt = temp_transaction.live_start_commit_receipt
            assert receipt is not None
            if receipt.output_child_identity != path_identity(output_root):
                raise ValueError("publisher_transaction_temp_conflict")
            try:
                _require_pointer_predecessor_exact(output_root, receipt)
                _require_current_pointer_receipt_exact(
                    output_root,
                    receipt,
                    output_publication_bytes(current[0]),
                )
            except ValueError as error:
                raise ValueError(
                    "publisher_transaction_temp_conflict"
                ) from error
        if not canonical_successor and not _same_transaction_identity(
            final_transaction,
            temp_transaction,
        ):
            raise ValueError("publisher_transaction_temp_conflict")
        temp_rank = _phase_rank(temp_transaction.phase)
        final_rank = _phase_rank(final_transaction.phase)
        if temp_rank < final_rank:
            journal_actions.append(
                ("remove", temp_path, final_path, temp_identity, None, None)
            )
        elif temp_rank == final_rank:
            if temp_transaction != final_transaction and not canonical_successor:
                raise ValueError("publisher_transaction_temp_conflict")
            if canonical_successor:
                effective[transaction_id] = (
                    final_path,
                    temp_transaction,
                    temp_identity,
                )
                journal_actions.append(
                    (
                        "promote_replace",
                        temp_path,
                        final_path,
                        temp_identity,
                        final_identity,
                        _transaction_bytes(final_transaction),
                    )
                )
            else:
                journal_actions.append(
                    (
                        "remove",
                        temp_path,
                        final_path,
                        temp_identity,
                        None,
                        None,
                    )
                )
        else:
            allowed_skip = (
                final_transaction.phase == "pointer_committed"
                and temp_transaction.phase == "finalized"
                and (
                    final_transaction.previous_revision is None
                    or final_transaction.previous_revision
                    == final_transaction.revision
                )
            )
            if temp_rank != final_rank + 1 and not allowed_skip:
                raise ValueError("publisher_transaction_phase_jump")
            effective[transaction_id] = (
                final_path,
                temp_transaction,
                temp_identity,
            )
            journal_actions.append(
                (
                    "promote_replace",
                    temp_path,
                    final_path,
                    temp_identity,
                    final_identity,
                    _transaction_bytes(final_transaction),
                )
            )
    pointer_actions: list[tuple[Path, tuple[int, int, int]]] = []
    preserved_pointer_temp_ids: set[str] = set()
    for transaction_id, path, publication, identity in pointer_temps:
        row = effective.get(transaction_id)
        if row is None:
            raise ValueError("publisher_pointer_temp_owner_missing")
        transaction = row[1]
        if (
            publication.deck_name != transaction.deck_name
            or publication.deck_fingerprint
            != transaction.deck_fingerprint
            or publication.revision != transaction.revision
            or publication.content_root_sha256
            != transaction.content_root_sha256
        ):
            raise ValueError("publisher_pointer_temp_owner_mismatch")
        receipt = transaction.live_start_commit_receipt
        bound_live_pointer = (
            preserve_bound_live_pointer_temps
            and transaction.phase == "pointer_staging_bound"
            and receipt is not None
            and receipt.disposition == "pointer_staged"
        )
        if bound_live_pointer:
            publication_bytes = output_publication_bytes(publication)
            if (
                receipt.pointer_staging_identity != identity
                or receipt.planned_pointer_size != len(publication_bytes)
                or receipt.planned_pointer_sha256
                != "sha256:" + sha256(publication_bytes).hexdigest()
            ):
                raise ValueError(
                    "live_start_publication_current_identity_changed"
                )
            preserved_pointer_temp_ids.add(transaction_id)
            continue
        pointer_actions.append((path, identity))
    _validate_publisher_residue(
        output_root,
        journals=[
            (row[0], row[1])
            for row in effective.values()
        ],
        current_revision=current_revision,
    )
    guard = capture_plain_ancestor_guard(directory)
    directory_identity = path_identity(directory)
    for (
        action,
        temp_path,
        final_path,
        identity,
        final_identity,
        final_content,
    ) in journal_actions:
        guard.validate()
        if path_identity(temp_path) != identity:
            raise ValueError("publisher_owned_temp_identity_changed")
        if action in {"promote_create", "promote_replace"}:
            _validate_owned_replace_target(
                final_path,
                expected_identity=final_identity,
                expected_content=final_content,
            )
            secure_replace(
                temp_path,
                final_path,
                expected_source_identity=identity,
                expected_source_parent_identity=directory_identity,
                expected_target_parent_identity=directory_identity,
                expected_target_identity=final_identity,
                expected_target_absent=action == "promote_create",
            )
        else:
            secure_unlink(
                temp_path,
                expected_identity=identity,
                expected_parent_identity=directory_identity,
            )
        guard.validate()
    for path, identity in pointer_actions:
        guard.validate()
        if path_identity(path) != identity:
            raise ValueError("publisher_owned_temp_identity_changed")
        secure_unlink(
            path,
            expected_identity=identity,
            expected_parent_identity=directory_identity,
        )
        guard.validate()
    return frozenset(preserved_pointer_temp_ids)


def _same_transaction_identity(
    left: _Transaction,
    right: _Transaction,
) -> bool:
    return (
        left.transaction_id,
        left.deck_name,
        left.deck_fingerprint,
        left.content_root_sha256,
        left.staging,
        left.revision,
        left.previous_revision,
    ) == (
        right.transaction_id,
        right.deck_name,
        right.deck_fingerprint,
        right.content_root_sha256,
        right.staging,
        right.revision,
        right.previous_revision,
    )


def _require_live_start_journal_identity(
    transaction: _Transaction,
    identity: tuple[int, int, int],
) -> None:
    receipt = transaction.live_start_commit_receipt
    if receipt is not None and receipt.owner_journal_identity != identity:
        raise ValueError("publisher_transaction_identity_changed")


def _is_finalized_canonical_successor(
    previous: _Transaction,
    successor: _Transaction,
) -> bool:
    return (
        previous.phase in {"cleanup_started", "finalized"}
        and previous.previous_revision is not None
        and successor
        == replace(
            previous,
            previous_revision=None,
            previous_revision_identity=None,
            previous_owner_transaction_id=None,
            phase="finalized",
        )
    )


def _is_live_start_receipt_upgrade(
    previous: _Transaction,
    successor: _Transaction,
) -> bool:
    receipt = successor.live_start_commit_receipt
    return (
        previous.schema_version == _TRANSACTION_SCHEMA_VERSION
        and previous.phase == "finalized"
        and previous.live_start_commit_receipt is None
        and receipt is not None
        and receipt.disposition == "reused_existing"
        and successor
        == replace(
            previous,
            schema_version=_LIVE_START_TRANSACTION_SCHEMA_VERSION,
            live_start_commit_receipt=receipt,
        )
    )


def _current_owner_receipt_upgrade_is_safe(
    output_root: Path,
    *,
    current: tuple[OutputPublication, Any],
    owner: _Transaction,
) -> bool:
    publication, verified = current
    if (
        not owner.owns_revision
        or owner.phase != "finalized"
        or owner.revision != publication.revision
        or owner.previous_revision is not None
        or owner.previous_revision_identity is not None
        or owner.previous_owner_transaction_id is not None
        or owner.staging_identity is not None
        or path_lexists(output_root / owner.staging)
    ):
        return False
    revision_root = output_root / publication.revision
    manifest = verified.manifest
    return (
        owner.revision_identity == path_identity(revision_root)
        and owner.deck_name == publication.deck_name
        and owner.deck_fingerprint == publication.deck_fingerprint
        and owner.content_root_sha256 == publication.content_root_sha256
        and manifest.deck_name == publication.deck_name
        and manifest.deck_fingerprint == publication.deck_fingerprint
        and manifest.content_root_sha256 == publication.content_root_sha256
    )


def _phase_rank(phase: str) -> int:
    order = (
        "prepared",
        "staging_owned",
        "staging_verified",
        "revision_ready",
        "pointer_staging_bound",
        "pointer_committed",
        "cleanup_started",
        "finalized",
    )
    return order.index(phase)


def _load_valid_transactions(
    output_root: Path,
    *,
    allowed_live_pointer_temp_ids: frozenset[str] = frozenset(),
) -> list[tuple[Path, _Transaction]]:
    directory = output_root / ".publisher" / "transactions"
    require_plain_directory(directory)
    result = _LoadedTransactions()
    entries: list[os.DirEntry[str]] = []
    with os.scandir(directory) as iterator:
        for entry in iterator:
            if len(entries) >= _MAX_TRANSACTION_FILES:
                raise ValueError("publisher_transaction_count_limit")
            entries.append(entry)
    total_bytes = 0
    for entry in sorted(entries, key=lambda row: row.name):
        pointer_temp_match = re.fullmatch(
            r"\.([0-9a-f]{32})\.current\.tmp",
            entry.name,
        )
        if (
            pointer_temp_match is not None
            and pointer_temp_match.group(1) in allowed_live_pointer_temp_ids
        ):
            continue
        if not re.fullmatch(r"[0-9a-f]{32}\.json", entry.name):
            raise ValueError("publisher_transaction_residue_invalid")
        status = Path(entry.path).lstat()
        if (
            not stat.S_ISREG(status.st_mode)
            or status_is_reparse(status)
            or status.st_nlink != 1
            or status.st_size > _MAX_TRANSACTION_FILE_BYTES
        ):
            raise ValueError("publisher_transaction_file_invalid")
        total_bytes += status.st_size
        if total_bytes > _MAX_TRANSACTION_BYTES:
            raise ValueError("publisher_transaction_bytes_limit")
        path = Path(entry.path)
        _require_plain_file_no_ads(path, status)
        try:
            transaction = _parse_transaction(
                read_file_no_follow(
                    path,
                    expected_status=status,
                    maximum_size=_MAX_TRANSACTION_FILE_BYTES,
                )
            )
        except Exception as error:
            raise ValueError("publisher_transaction_invalid") from error
        if transaction.transaction_id != entry.name[:-5]:
            raise ValueError("publisher_transaction_name_mismatch")
        identity = path_identity_from_status(status)
        _require_live_start_journal_identity(transaction, identity)
        result.append((path, transaction))
        result.identities[path] = identity
    owners: dict[str, list[_Transaction]] = {}
    for _path, transaction in result:
        if transaction.owns_revision:
            owners.setdefault(transaction.revision, []).append(transaction)
    if any(len(rows) != 1 for rows in owners.values()):
        raise ValueError("publisher_revision_owner_ambiguous")
    return result


def _write_transaction(
    path: Path,
    transaction: _Transaction,
    *,
    expected_target_identity: tuple[int, int, int] | None = None,
    expected_target_content: bytes | None = None,
    fault_hook: FaultHook = no_fault,
) -> _Transaction:
    def transaction_fault(stage: str) -> None:
        fault_hook(stage)
        if stage == "after_journal_temp_write":
            fault_hook(
                f"after_journal_{transaction.phase}_temp_write"
            )

    published_transaction = transaction
    bound_target_identity = expected_target_identity
    bound_target_content = expected_target_content
    target_must_be_absent = bound_target_identity is None
    if bound_target_identity is None and bound_target_content is None:
        if path_lexists(path):
            target_status = plain_file_status(path)
            bound_target_identity = path_identity_from_status(target_status)
            _require_plain_file_no_ads(path, target_status)
            bound_target_content = read_file_no_follow(
                path,
                expected_status=target_status,
                maximum_size=_MAX_TRANSACTION_FILE_BYTES,
            )
            target_must_be_absent = False
    elif bound_target_identity is not None:
        target_must_be_absent = False

    def identity_bound_content(
        identity: tuple[int, int, int],
    ) -> bytes:
        nonlocal published_transaction
        receipt = transaction.live_start_commit_receipt
        if receipt is None:
            return _transaction_bytes(transaction)
        bound_receipt = _bind_live_start_receipt_owner_journal_identity(
            receipt,
            identity,
        )
        published_transaction = replace(
            transaction,
            live_start_commit_receipt=bound_receipt,
        )
        return _transaction_bytes(published_transaction)

    _owned_atomic_replace(
        path,
        _transaction_bytes(transaction),
        temp_path=path.with_name(
            f".{transaction.transaction_id}.journal.tmp"
        ),
        expected_target_identity=bound_target_identity,
        expected_target_content=bound_target_content,
        expected_target_absent=target_must_be_absent,
        fault_hook=transaction_fault,
        temp_stage="after_journal_temp_write",
        identity_bound_content=identity_bound_content,
    )
    return published_transaction


def _transaction_bytes(transaction: _Transaction) -> bytes:
    payload = {
        "schema_version": transaction.schema_version,
        "transaction_id": transaction.transaction_id,
        "deck_name": transaction.deck_name,
        "deck_fingerprint": transaction.deck_fingerprint,
        "content_root_sha256": transaction.content_root_sha256,
        "staging": transaction.staging,
        "revision": transaction.revision,
        "previous_revision": transaction.previous_revision,
        "previous_revision_identity": (
            list(transaction.previous_revision_identity)
            if transaction.previous_revision_identity is not None
            else None
        ),
        "previous_owner_transaction_id": (
            transaction.previous_owner_transaction_id
        ),
        "staging_identity": (
            list(transaction.staging_identity)
            if transaction.staging_identity is not None
            else None
        ),
        "revision_identity": (
            list(transaction.revision_identity)
            if transaction.revision_identity is not None
            else None
        ),
        "owns_revision": transaction.owns_revision,
        "phase": transaction.phase,
    }
    if transaction.schema_version == _LIVE_START_TRANSACTION_SCHEMA_VERSION:
        payload["live_start_commit_receipt"] = (
            None
            if transaction.live_start_commit_receipt is None
            else _live_start_commit_receipt_payload(
                transaction.live_start_commit_receipt
            )
        )
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def _parse_transaction(content: bytes) -> _Transaction:
    payload = json.loads(
        content.decode("utf-8"),
        object_pairs_hook=_unique_json_object,
    )
    if not isinstance(payload, dict):
        raise ValueError("publisher_transaction_invalid")
    schema_version = payload.get("schema_version")
    expected_keys = (
        _JOURNAL_V1_KEYS
        if schema_version == _TRANSACTION_SCHEMA_VERSION
        else _JOURNAL_V2_KEYS
        if schema_version == _LIVE_START_TRANSACTION_SCHEMA_VERSION
        else None
    )
    if expected_keys is None or set(payload) != expected_keys:
        raise ValueError("publisher_transaction_invalid")
    transaction = _Transaction(
        schema_version=payload["schema_version"],
        transaction_id=payload["transaction_id"],
        deck_name=payload["deck_name"],
        deck_fingerprint=payload["deck_fingerprint"],
        content_root_sha256=payload["content_root_sha256"],
        staging=payload["staging"],
        revision=payload["revision"],
        previous_revision=payload["previous_revision"],
        previous_revision_identity=_parse_identity(
            payload["previous_revision_identity"]
        ),
        previous_owner_transaction_id=payload[
            "previous_owner_transaction_id"
        ],
        staging_identity=_parse_identity(payload["staging_identity"]),
        revision_identity=_parse_identity(payload["revision_identity"]),
        owns_revision=payload["owns_revision"],
        phase=payload["phase"],
        live_start_commit_receipt=(
            None
            if schema_version == _TRANSACTION_SCHEMA_VERSION
            or payload["live_start_commit_receipt"] is None
            else _parse_live_start_commit_receipt(
                payload["live_start_commit_receipt"]
            )
        ),
    )
    if content != _transaction_bytes(transaction):
        raise ValueError("publisher_transaction_noncanonical")
    return transaction


def _parse_identity(value: object) -> tuple[int, int, int] | None:
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(type(item) is not int or item < 0 for item in value)
    ):
        raise ValueError("publisher_transaction_identity_invalid")
    return value[0], value[1], value[2]


def _remove_file_if_plain(path: Path) -> None:
    try:
        status = path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(status.st_mode) or status_is_reparse(status):
        return
    secure_unlink(
        path,
        expected_identity=path_identity_from_status(status),
        expected_parent_identity=path_identity(path.parent),
    )


def _canonical_revision(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parts = value.split("/")
    return (
        len(parts) == 2
        and parts[0] == "revisions"
        and bool(_REVISION_NAME.fullmatch(parts[1]))
    )


def _identity_or_none(
    value: tuple[int, int, int] | None,
) -> bool:
    return value is None or (
        isinstance(value, tuple)
        and len(value) == 3
        and all(type(item) is int and item >= 0 for item in value)
    )


def _valid_phase_state(transaction: _Transaction) -> bool:
    receipt = transaction.live_start_commit_receipt
    if transaction.schema_version == _LIVE_START_TRANSACTION_SCHEMA_VERSION:
        if transaction.phase in {
            "pointer_staging_bound",
            "pointer_committed",
            "cleanup_started",
            "finalized",
        } and receipt is None:
            return False
        if receipt is not None:
            if receipt.disposition == "pointer_staged" and transaction.phase not in {
                "pointer_staging_bound",
                "pointer_committed",
                "cleanup_started",
                "finalized",
            }:
                return False
            if receipt.disposition == "reused_existing" and transaction.phase != "finalized":
                return False
    elif receipt is not None or transaction.phase == "pointer_staging_bound":
        return False
    cleanup_bound = (
        transaction.previous_revision_identity is not None
        and transaction.previous_owner_transaction_id is not None
        and transaction.previous_revision is not None
    )
    if transaction.phase == "cleanup_started":
        return (
            cleanup_bound
            and transaction.staging_identity is None
            and transaction.revision_identity is not None
        )
    if (
        transaction.previous_revision_identity is not None
        or transaction.previous_owner_transaction_id is not None
    ):
        return False
    if transaction.phase == "prepared":
        return (
            transaction.staging_identity is None
            and transaction.revision_identity is None
            and not transaction.owns_revision
        )
    if transaction.phase in {"staging_owned", "staging_verified"}:
        return (
            transaction.staging_identity is not None
            and transaction.revision_identity is None
            and not transaction.owns_revision
        )
    return (
        transaction.staging_identity is None
        and transaction.revision_identity is not None
    )


def _live_start_commit_receipt_payload(
    receipt: _LiveStartCommitReceipt,
) -> dict[str, Any]:
    return {
        "schema_version": receipt.schema_version,
        "receipt_kind": receipt.receipt_kind,
        "disposition": receipt.disposition,
        "expected_session_sha256": receipt.expected_session_sha256,
        "operation_admission_identity": list(
            receipt.operation_admission_identity
        ),
        "operation_admission_sha256": receipt.operation_admission_sha256,
        "claim_identity": list(receipt.claim_identity),
        "claim_sha256": receipt.claim_sha256,
        "output_child_identity": list(receipt.output_child_identity),
        "pointer_predecessor_identity": (
            None
            if receipt.pointer_predecessor_identity is None
            else list(receipt.pointer_predecessor_identity)
        ),
        "pointer_predecessor_size": receipt.pointer_predecessor_size,
        "pointer_predecessor_sha256": receipt.pointer_predecessor_sha256,
        "pointer_staging_identity": list(receipt.pointer_staging_identity),
        "planned_pointer_size": receipt.planned_pointer_size,
        "planned_pointer_sha256": receipt.planned_pointer_sha256,
        "owner_journal_predecessor_identity": (
            None
            if receipt.owner_journal_predecessor_identity is None
            else list(receipt.owner_journal_predecessor_identity)
        ),
        "owner_journal_identity": (
            None
            if receipt.owner_journal_identity is None
            else list(receipt.owner_journal_identity)
        ),
        "content_sha256": receipt.content_sha256,
    }


def _live_start_commit_receipt_unsigned_payload(
    receipt: _LiveStartCommitReceipt,
) -> dict[str, Any]:
    payload = _live_start_commit_receipt_payload(receipt)
    payload.pop("content_sha256")
    return payload


def _bind_live_start_receipt_owner_journal_identity(
    receipt: _LiveStartCommitReceipt,
    identity: tuple[int, int, int],
) -> _LiveStartCommitReceipt:
    unsigned = _live_start_commit_receipt_unsigned_payload(receipt)
    unsigned["owner_journal_identity"] = list(identity)
    return replace(
        receipt,
        owner_journal_identity=identity,
        content_sha256=(
            "sha256:" + sha256(_canonical_json_bytes(unsigned)).hexdigest()
        ),
    )


def _validate_live_start_commit_receipt(
    receipt: _LiveStartCommitReceipt,
) -> None:
    predecessor_present = receipt.pointer_predecessor_identity is not None
    if (
        type(receipt.schema_version) is not int
        or receipt.schema_version != _LIVE_START_COMMIT_RECEIPT_SCHEMA_VERSION
        or receipt.receipt_kind != _LIVE_START_COMMIT_RECEIPT_KIND
        or receipt.disposition not in {"pointer_staged", "reused_existing"}
        or not _is_prefixed_sha256(receipt.expected_session_sha256)
        or not _identity_or_none(receipt.operation_admission_identity)
        or receipt.operation_admission_identity is None
        or not _is_prefixed_sha256(receipt.operation_admission_sha256)
        or not _identity_or_none(receipt.claim_identity)
        or receipt.claim_identity is None
        or not _is_prefixed_sha256(receipt.claim_sha256)
        or not _identity_or_none(receipt.output_child_identity)
        or receipt.output_child_identity is None
        or not _identity_or_none(receipt.pointer_predecessor_identity)
        or (receipt.pointer_predecessor_size is not None)
        != predecessor_present
        or (receipt.pointer_predecessor_sha256 is not None)
        != predecessor_present
        or (
            receipt.pointer_predecessor_size is not None
            and (
                type(receipt.pointer_predecessor_size) is not int
                or receipt.pointer_predecessor_size < 0
                or not _is_prefixed_sha256(receipt.pointer_predecessor_sha256)
            )
        )
        or not _identity_or_none(receipt.pointer_staging_identity)
        or receipt.pointer_staging_identity is None
        or type(receipt.planned_pointer_size) is not int
        or receipt.planned_pointer_size <= 0
        or not _is_prefixed_sha256(receipt.planned_pointer_sha256)
        or not _identity_or_none(
            receipt.owner_journal_predecessor_identity
        )
        or (
            receipt.owner_journal_predecessor_identity is not None
        )
        != (receipt.disposition == "reused_existing")
        or not _identity_or_none(receipt.owner_journal_identity)
        or not _is_prefixed_sha256(receipt.content_sha256)
    ):
        raise ValueError("publisher_live_start_commit_receipt_invalid")
    expected_digest = "sha256:" + sha256(
        _canonical_json_bytes(
            _live_start_commit_receipt_unsigned_payload(receipt)
        )
    ).hexdigest()
    if receipt.content_sha256 != expected_digest:
        raise ValueError("publisher_live_start_commit_receipt_invalid")


def _parse_live_start_commit_receipt(
    value: object,
) -> _LiveStartCommitReceipt:
    if not isinstance(value, dict) or set(value) != _LIVE_START_COMMIT_RECEIPT_KEYS:
        raise ValueError("publisher_live_start_commit_receipt_invalid")
    return _LiveStartCommitReceipt(
        schema_version=value["schema_version"],
        receipt_kind=value["receipt_kind"],
        disposition=value["disposition"],
        expected_session_sha256=value["expected_session_sha256"],
        operation_admission_identity=_parse_required_identity(
            value["operation_admission_identity"]
        ),
        operation_admission_sha256=value["operation_admission_sha256"],
        claim_identity=_parse_required_identity(value["claim_identity"]),
        claim_sha256=value["claim_sha256"],
        output_child_identity=_parse_required_identity(
            value["output_child_identity"]
        ),
        pointer_predecessor_identity=_parse_identity(
            value["pointer_predecessor_identity"]
        ),
        pointer_predecessor_size=value["pointer_predecessor_size"],
        pointer_predecessor_sha256=value["pointer_predecessor_sha256"],
        pointer_staging_identity=_parse_required_identity(
            value["pointer_staging_identity"]
        ),
        planned_pointer_size=value["planned_pointer_size"],
        planned_pointer_sha256=value["planned_pointer_sha256"],
        owner_journal_predecessor_identity=_parse_identity(
            value["owner_journal_predecessor_identity"]
        ),
        owner_journal_identity=_parse_identity(
            value["owner_journal_identity"]
        ),
        content_sha256=value["content_sha256"],
    )


def _parse_required_identity(value: object) -> tuple[int, int, int]:
    parsed = _parse_identity(value)
    if parsed is None:
        raise ValueError("publisher_transaction_identity_invalid")
    return parsed


def _is_prefixed_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and _is_sha256(value[7:])
    )


def _identity(status: os.stat_result) -> tuple[int, int, int]:
    return status.st_dev, status.st_ino, status.st_mode


def _file_state(
    status: os.stat_result,
) -> tuple[int, int, int, int, int, int]:
    return (
        status.st_dev,
        status.st_ino,
        status.st_mode,
        status.st_size,
        status.st_mtime_ns,
        status.st_ctime_ns,
    )


def _unique_json_object(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and value == value.lower()
        and all(character in "0123456789abcdef" for character in value)
    )


__all__ = (
    "PublishedOutput",
    "publish_configure_run",
    "reconcile_output",
)
