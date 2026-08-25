"""Canonical one-time operator policy and safe deck-output binding."""

from __future__ import annotations

import json
import os
import re
import stat
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from threading import Lock, get_ident
from typing import Any, Literal
from weakref import ReferenceType, ref

from hsconfig.atomic_io import ExclusiveFileLock, atomic_write_bytes
from hsconfig.io import slugify_deck_name
from hsconfig.output_operation_admission import (
    _require_lock_without_alternate_data_streams,
    _require_windows_safe_absolute_path,
    lease_output_operation_admission,
    output_operation_lock_path,
    require_output_operation_allows_profile_mutation,
)
from hsconfig.package_io import (
    PathIdentity,
    capture_plain_ancestor_guard,
    hold_plain_directory,
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
    status_is_reparse,
)


OPERATOR_PROFILE_SCHEMA_VERSION = 1
OPERATOR_PROFILE_MAX_BYTES = 64 * 1024
OPERATOR_PROFILE_FIELDS = frozenset(
    {
        "schema_version",
        "live_by_default",
        "runtime_root",
        "runtime_root_identity",
        "output_base_root",
        "output_base_root_identity",
        "content_sha256",
    }
)
OPERATOR_PROFILE_NAME = "operator-profile.json"
OPERATOR_PROFILE_LOCK_NAME = "operator-profile.lock"


_STANDARD_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_TOKEN_AUTHORITY = object()
_WINDOWS_RESERVED_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{index}" for index in range(1, 10)}
    | {f"lpt{index}" for index in range(1, 10)}
    | {
        f"{prefix}{suffix}"
        for prefix in ("com", "lpt")
        for suffix in ("¹", "²", "³")
    }
)


@dataclass(frozen=True, slots=True, weakref_slot=True)
class OperatorProfile:
    schema_version: int
    live_by_default: bool
    runtime_root: Path
    runtime_root_identity: PathIdentity
    output_base_root: Path
    output_base_root_identity: PathIdentity
    content_sha256: str


@dataclass(frozen=True, slots=True, init=False)
class OperatorProfileLockToken:
    """Opaque process-local capability for one held profile lock."""

    _nonce: object
    _thread_id: int

    def __init__(self, authority: object | None = None) -> None:
        if authority is not _TOKEN_AUTHORITY:
            raise TypeError("operator_profile_token_not_constructible")
        object.__setattr__(self, "_nonce", object())
        object.__setattr__(self, "_thread_id", get_ident())

    def __copy__(self) -> OperatorProfileLockToken:
        raise TypeError("operator_profile_token_not_copyable")

    def __deepcopy__(self, memo: dict[int, object]) -> OperatorProfileLockToken:
        raise TypeError("operator_profile_token_not_copyable")

    def __reduce__(self) -> object:
        raise TypeError("operator_profile_token_not_serializable")


@dataclass(frozen=True, slots=True)
class OperatorProfileLease:
    profile: OperatorProfile
    profile_path: Path
    profile_identity: PathIdentity
    profile_parent_identity: PathIdentity
    profile_lock_path: Path
    profile_lock_identity: PathIdentity
    lock_token: OperatorProfileLockToken


@dataclass(frozen=True, slots=True)
class DeckOutputBinding:
    output_name: str
    output_root: Path
    precondition_state: Literal["absent", "existing"]
    precondition_identity: PathIdentity | None


@dataclass(frozen=True, slots=True)
class _ProfileObservation:
    profile: OperatorProfile
    profile_path: Path
    profile_parent_identity: PathIdentity
    profile_identity: PathIdentity
    canonical_bytes: bytes


@dataclass(frozen=True, slots=True)
class _ProfileObservationBinding:
    profile_path: Path
    profile_parent_identity: PathIdentity
    profile_identity: PathIdentity
    canonical_bytes: bytes


_profile_observations: dict[
    int,
    tuple[ReferenceType[OperatorProfile], _ProfileObservationBinding],
] = {}
_profile_observations_lock = Lock()
_active_leases: dict[
    int,
    tuple[OperatorProfileLockToken, OperatorProfileLease, int],
] = {}
_active_leases_lock = Lock()


def operator_profile_path(
    environ: Mapping[str, str] | None = None,
) -> Path:
    environment = os.environ if environ is None else environ
    raw = environment.get("LOCALAPPDATA")
    if not isinstance(raw, str) or not raw:
        raise ValueError("localappdata_missing")
    local_app_data = Path(raw)
    if not local_app_data.is_absolute():
        raise ValueError("localappdata_not_absolute")
    _require_windows_safe_absolute_path(
        local_app_data,
        error="localappdata_windows_namespace_invalid",
    )
    return local_app_data / "HSConfig" / OPERATOR_PROFILE_NAME


def enable_operator_profile(
    *,
    runtime_root: Path,
    output_base_root: Path,
    expected_predecessor_sha256: str | None,
) -> OperatorProfile:
    """Create, enable, or explicitly rebind the canonical operator profile."""

    if expected_predecessor_sha256 is not None:
        _require_standard_digest(expected_predecessor_sha256, "predecessor")
    requested_runtime = _validated_plain_root(Path(runtime_root))
    requested_output = _validated_plain_root(Path(output_base_root))
    requested_runtime_identity = path_identity(requested_runtime)
    requested_output_identity = path_identity(requested_output)
    state_root = _state_root_for_requested_roots(
        requested_runtime,
        requested_output,
    )
    state_root_identity = _ensure_state_root_for_enable(state_root)
    profile_path = state_root / OPERATOR_PROFILE_NAME
    profile_lock_path = state_root / OPERATOR_PROFILE_LOCK_NAME
    profile_lock_identity = _bootstrap_profile_lock(
        profile_lock_path,
        expected_parent_identity=state_root_identity,
    )
    state_guard = capture_plain_ancestor_guard(profile_lock_path)
    with ExclusiveFileLock(
        profile_lock_path,
        expected_parent_identity=state_root_identity,
        path_guard=state_guard,
        create_if_missing=False,
    ):
        _require_empty_plain_file_under_lock(
            profile_lock_path,
            "operator_profile_lock_not_empty",
            expected_identity=profile_lock_identity,
        )
        _bootstrap_output_operation_lock(state_root, state_root_identity)
        with lease_output_operation_admission() as operation_lease:
            require_output_operation_allows_profile_mutation(operation_lease)
            predecessor = _read_optional_observation(
                profile_path,
                expected_parent_identity=state_root_identity,
            )
            _require_enable_predecessor(predecessor, expected_predecessor_sha256)
            if predecessor is not None and _profile_matches_requested_enabled(
                predecessor.profile,
                requested_runtime=requested_runtime,
                requested_runtime_identity=requested_runtime_identity,
                requested_output=requested_output,
                requested_output_identity=requested_output_identity,
            ):
                return predecessor.profile
            canonical = _seal_profile(
                live_by_default=True,
                runtime_root=requested_runtime,
                runtime_root_identity=requested_runtime_identity,
                output_base_root=requested_output,
                output_base_root_identity=requested_output_identity,
            )
            _write_profile_cas(
                profile_path,
                canonical,
                predecessor=predecessor,
                expected_parent_identity=state_root_identity,
                expected_root_bindings=(
                    (requested_runtime, requested_runtime_identity),
                    (requested_output, requested_output_identity),
                ),
            )
            return _read_observation(
                profile_path,
                expected_parent_identity=state_root_identity,
            ).profile


def disable_operator_profile(
    *, expected_predecessor_sha256: str
) -> OperatorProfile:
    """Disable live-by-default without changing either bound root."""

    _require_standard_digest(expected_predecessor_sha256, "predecessor")
    state_root, state_root_identity = _require_existing_state_root()
    profile_path = state_root / OPERATOR_PROFILE_NAME
    profile_lock_path = state_root / OPERATOR_PROFILE_LOCK_NAME
    profile_lock_identity = _require_empty_plain_file(
        profile_lock_path,
        "operator_profile_lock_not_empty",
        expected_parent_identity=state_root_identity,
        wait_for_active_lock=True,
    )
    state_guard = capture_plain_ancestor_guard(profile_lock_path)
    with ExclusiveFileLock(
        profile_lock_path,
        expected_parent_identity=state_root_identity,
        path_guard=state_guard,
        create_if_missing=False,
    ):
        _require_empty_plain_file_under_lock(
            profile_lock_path,
            "operator_profile_lock_not_empty",
            expected_identity=profile_lock_identity,
        )
        with lease_output_operation_admission() as operation_lease:
            require_output_operation_allows_profile_mutation(operation_lease)
            predecessor = _read_observation(
                profile_path,
                expected_parent_identity=state_root_identity,
            )
            if predecessor.profile.content_sha256 != expected_predecessor_sha256:
                raise ValueError("operator_profile_predecessor_mismatch")
            if not predecessor.profile.live_by_default:
                return predecessor.profile
            canonical = _seal_profile(
                live_by_default=False,
                runtime_root=predecessor.profile.runtime_root,
                runtime_root_identity=predecessor.profile.runtime_root_identity,
                output_base_root=predecessor.profile.output_base_root,
                output_base_root_identity=(
                    predecessor.profile.output_base_root_identity
                ),
            )
            _write_profile_cas(
                profile_path,
                canonical,
                predecessor=predecessor,
                expected_parent_identity=state_root_identity,
                expected_root_bindings=(
                    (
                        predecessor.profile.runtime_root,
                        predecessor.profile.runtime_root_identity,
                    ),
                    (
                        predecessor.profile.output_base_root,
                        predecessor.profile.output_base_root_identity,
                    ),
                ),
            )
            return _read_observation(
                profile_path,
                expected_parent_identity=state_root_identity,
            ).profile


def load_operator_profile() -> OperatorProfile:
    """Load the profile with no lock creation, rewrite, or timestamp change."""

    state_root, state_root_identity = _require_existing_state_root()
    return _read_observation(
        state_root / OPERATOR_PROFILE_NAME,
        expected_parent_identity=state_root_identity,
    ).profile


def revalidate_operator_profile(profile: OperatorProfile) -> OperatorProfile:
    """Require the same profile bytes, file identity, parent, and root identities."""

    expected = _registered_observation(profile)
    current = _read_observation(
        expected.profile_path,
        expected_parent_identity=expected.profile_parent_identity,
    )
    _require_same_observation(current, expected)
    return profile


@contextmanager
def lease_operator_profile(
    *, expected_profile: OperatorProfile
) -> Iterator[OperatorProfileLease]:
    expected = _registered_observation(expected_profile)
    profile_lock_path = expected.profile_path.with_name(OPERATOR_PROFILE_LOCK_NAME)
    profile_lock_identity = _require_empty_plain_file(
        profile_lock_path,
        "operator_profile_lock_not_empty",
        expected_parent_identity=expected.profile_parent_identity,
        wait_for_active_lock=True,
    )
    state_guard = capture_plain_ancestor_guard(profile_lock_path)
    with ExclusiveFileLock(
        profile_lock_path,
        expected_parent_identity=expected.profile_parent_identity,
        path_guard=state_guard,
        create_if_missing=False,
    ):
        _require_empty_plain_file_under_lock(
            profile_lock_path,
            "operator_profile_lock_not_empty",
            expected_identity=profile_lock_identity,
        )
        current = _read_observation(
            expected.profile_path,
            expected_parent_identity=expected.profile_parent_identity,
        )
        _require_same_observation(current, expected)
        token = OperatorProfileLockToken(_TOKEN_AUTHORITY)
        lease = OperatorProfileLease(
            profile=expected_profile,
            profile_path=expected.profile_path,
            profile_identity=expected.profile_identity,
            profile_parent_identity=expected.profile_parent_identity,
            profile_lock_path=profile_lock_path,
            profile_lock_identity=profile_lock_identity,
            lock_token=token,
        )
        with _active_leases_lock:
            _active_leases[id(token)] = (token, lease, get_ident())
        try:
            yield lease
        finally:
            with _active_leases_lock:
                _active_leases.pop(id(token), None)


def revalidate_operator_profile_lease(
    lease: OperatorProfileLease,
) -> OperatorProfile:
    _require_active_lease(lease)
    _require_empty_plain_file_under_lock(
        lease.profile_lock_path,
        "operator_profile_lock_not_empty",
        expected_identity=lease.profile_lock_identity,
    )
    expected = _registered_observation(lease.profile)
    if (
        expected.profile_path != lease.profile_path
        or expected.profile_identity != lease.profile_identity
        or expected.profile_parent_identity != lease.profile_parent_identity
    ):
        raise ValueError("operator_profile_lease_binding_invalid")
    current = _read_observation(
        lease.profile_path,
        expected_parent_identity=lease.profile_parent_identity,
    )
    _require_same_observation(current, expected)
    return lease.profile


def derive_deck_output_binding(
    profile: OperatorProfile, deck_name: str
) -> DeckOutputBinding:
    revalidate_operator_profile(profile)
    if not isinstance(deck_name, str):
        raise ValueError("deck_output_name_invalid")
    output_name = slugify_deck_name(deck_name)
    _require_safe_output_name(output_name)
    output_root = profile.output_base_root / output_name
    with hold_plain_directory(
        profile.output_base_root,
        expected_identity=profile.output_base_root_identity,
    ) as output_base:
        try:
            status = output_base.child_status(output_name)
        except FileNotFoundError:
            return DeckOutputBinding(
                output_name=output_name,
                output_root=output_root,
                precondition_state="absent",
                precondition_identity=None,
            )
        if not stat.S_ISDIR(status.st_mode) or status_is_reparse(status):
            raise ValueError("deck_output_root_not_plain_directory")
        identity = path_identity_from_status(status)
        require_same_identity_resolution(output_root, expected_status=status)
        output_base.validate()
        return DeckOutputBinding(
            output_name=output_name,
            output_root=output_root,
            precondition_state="existing",
            precondition_identity=identity,
        )


def _state_root_for_requested_roots(runtime_root: Path, output_base_root: Path) -> Path:
    local_app_data = _validated_plain_root(operator_profile_path().parent.parent)
    state_root = local_app_data / "HSConfig"
    _require_disjoint_roots(runtime_root, output_base_root, state_root)
    return state_root


def _ensure_state_root_for_enable(state_root: Path) -> PathIdentity:
    local_app_data = state_root.parent
    local_identity = path_identity(local_app_data)
    ancestor_guard = capture_plain_ancestor_guard(state_root)
    with hold_plain_directory(local_app_data, expected_identity=local_identity):
        if path_lexists(state_root):
            _require_canonical_plain_directory(state_root)
        else:
            secure_create_directory(
                state_root,
                expected_parent_identity=local_identity,
            )
    ancestor_guard.validate()
    _require_canonical_plain_directory(state_root)
    return path_identity(state_root)


def _require_existing_state_root() -> tuple[Path, PathIdentity]:
    local_app_data = _validated_plain_root(operator_profile_path().parent.parent)
    state_root = local_app_data / "HSConfig"
    _require_canonical_plain_directory(state_root)
    return state_root, path_identity(state_root)


def _bootstrap_output_operation_lock(
    state_root: Path,
    state_root_identity: PathIdentity,
) -> None:
    locks_root = state_root / "locks"
    with hold_plain_directory(state_root, expected_identity=state_root_identity):
        if path_lexists(locks_root):
            _require_canonical_plain_directory(locks_root)
        else:
            secure_create_directory(
                locks_root,
                expected_parent_identity=state_root_identity,
            )
    locks_identity = path_identity(locks_root)
    operation_lock = output_operation_lock_path()
    if path_lexists(operation_lock):
        _require_empty_plain_file(
            operation_lock,
            "output_operation_lock_not_empty",
            expected_parent_identity=locks_identity,
            wait_for_active_lock=True,
        )
        return
    descriptor = secure_open_file_descriptor(
        operation_lock,
        create=True,
        write=True,
        expected_parent_identity=locks_identity,
    )
    os.close(descriptor)
    _require_empty_plain_file(
        operation_lock,
        "output_operation_lock_not_empty",
        expected_parent_identity=locks_identity,
        wait_for_active_lock=True,
    )


def _bootstrap_profile_lock(
    profile_lock_path: Path,
    *,
    expected_parent_identity: PathIdentity,
) -> PathIdentity:
    if not path_lexists(profile_lock_path):
        try:
            descriptor = secure_open_file_descriptor(
                profile_lock_path,
                create=True,
                write=True,
                expected_parent_identity=expected_parent_identity,
            )
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
    return _require_empty_plain_file(
        profile_lock_path,
        "operator_profile_lock_not_empty",
        expected_parent_identity=expected_parent_identity,
        wait_for_active_lock=True,
    )


def _read_optional_observation(
    path: Path,
    *,
    expected_parent_identity: PathIdentity,
) -> _ProfileObservation | None:
    if not path_lexists(path):
        return None
    return _read_observation(
        path,
        expected_parent_identity=expected_parent_identity,
    )


def _read_observation(
    path: Path,
    *,
    expected_parent_identity: PathIdentity,
) -> _ProfileObservation:
    profile_path = Path(path)
    parent = profile_path.parent
    _require_canonical_plain_directory(parent)
    if path_identity(parent) != expected_parent_identity:
        raise ValueError("operator_profile_parent_identity_changed")
    status = plain_file_status(profile_path)
    raw = read_file_no_follow(
        profile_path,
        expected_status=status,
        maximum_size=OPERATOR_PROFILE_MAX_BYTES,
    )
    require_no_alternate_data_streams(
        profile_path,
        expected_identity=path_identity_from_status(status),
        expected_parent_identity=expected_parent_identity,
        directory=False,
        expected_size=len(raw),
    )
    document = _load_canonical_document(raw)
    profile = _parse_profile_document(document, state_root=parent)
    observation = _ProfileObservation(
        profile=profile,
        profile_path=profile_path,
        profile_parent_identity=expected_parent_identity,
        profile_identity=path_identity_from_status(status),
        canonical_bytes=raw,
    )
    if path_identity(profile_path) != observation.profile_identity:
        raise ValueError("operator_profile_identity_changed")
    _register_observation(observation)
    return observation


def _load_canonical_document(raw: bytes) -> dict[str, Any]:
    if not raw or len(raw) > OPERATOR_PROFILE_MAX_BYTES:
        raise ValueError("operator_profile_size_invalid")
    if raw.startswith(b"\xef\xbb\xbf") or b"\x00" in raw:
        raise ValueError("operator_profile_bytes_invalid")

    def reject_constant(value: str) -> None:
        raise ValueError(f"operator_profile_non_finite:{value}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("operator_profile_duplicate_key")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("operator_profile_json_invalid") from error
    if not isinstance(value, dict):
        raise ValueError("operator_profile_root_invalid")
    if _canonical_json(value) != raw:
        raise ValueError("operator_profile_not_canonical")
    return value


def _parse_profile_document(
    document: dict[str, Any], *, state_root: Path
) -> OperatorProfile:
    if set(document) != OPERATOR_PROFILE_FIELDS:
        raise ValueError("operator_profile_fields_invalid")
    if type(document["schema_version"]) is not int or document[
        "schema_version"
    ] != OPERATOR_PROFILE_SCHEMA_VERSION:
        raise ValueError("operator_profile_schema_version_invalid")
    if type(document["live_by_default"]) is not bool:
        raise ValueError("operator_profile_live_flag_invalid")
    content_sha256 = _require_standard_digest(
        document["content_sha256"], "content_sha256"
    )
    unsigned = dict(document)
    del unsigned["content_sha256"]
    if content_sha256 != "sha256:" + sha256(_canonical_json(unsigned)).hexdigest():
        raise ValueError("operator_profile_content_sha256_invalid")
    runtime_root = _canonical_existing_root(document["runtime_root"], "runtime_root")
    output_base_root = _canonical_existing_root(
        document["output_base_root"], "output_base_root"
    )
    _require_disjoint_roots(runtime_root, output_base_root, state_root)
    runtime_identity = _identity(document["runtime_root_identity"], "runtime_root")
    output_identity = _identity(
        document["output_base_root_identity"], "output_base_root"
    )
    if path_identity(runtime_root) != runtime_identity:
        raise ValueError("operator_profile_runtime_root_identity_changed")
    if path_identity(output_base_root) != output_identity:
        raise ValueError("operator_profile_output_base_root_identity_changed")
    return OperatorProfile(
        schema_version=OPERATOR_PROFILE_SCHEMA_VERSION,
        live_by_default=document["live_by_default"],
        runtime_root=runtime_root,
        runtime_root_identity=runtime_identity,
        output_base_root=output_base_root,
        output_base_root_identity=output_identity,
        content_sha256=content_sha256,
    )


def _seal_profile(
    *,
    live_by_default: bool,
    runtime_root: Path,
    runtime_root_identity: PathIdentity,
    output_base_root: Path,
    output_base_root_identity: PathIdentity,
) -> bytes:
    unsigned: dict[str, object] = {
        "schema_version": OPERATOR_PROFILE_SCHEMA_VERSION,
        "live_by_default": live_by_default,
        "runtime_root": str(runtime_root),
        "runtime_root_identity": list(runtime_root_identity),
        "output_base_root": str(output_base_root),
        "output_base_root_identity": list(output_base_root_identity),
    }
    digest = "sha256:" + sha256(_canonical_json(unsigned)).hexdigest()
    return _canonical_json({**unsigned, "content_sha256": digest})


def _write_profile_cas(
    path: Path,
    canonical: bytes,
    *,
    predecessor: _ProfileObservation | None,
    expected_parent_identity: PathIdentity,
    expected_root_bindings: tuple[tuple[Path, PathIdentity], ...],
) -> None:
    _require_root_bindings_unchanged(expected_root_bindings)
    _require_predecessor_unchanged(
        path,
        predecessor=predecessor,
        expected_parent_identity=expected_parent_identity,
    )

    def check_before_replace(stage: str) -> None:
        if stage == "before_replace":
            _require_root_bindings_unchanged(expected_root_bindings)
            _require_predecessor_unchanged(
                path,
                predecessor=predecessor,
                expected_parent_identity=expected_parent_identity,
            )

    atomic_write_bytes(
        path,
        canonical,
        expected_parent_identity=expected_parent_identity,
        fault_hook=check_before_replace,
    )


def _require_predecessor_unchanged(
    path: Path,
    *,
    predecessor: _ProfileObservation | None,
    expected_parent_identity: PathIdentity,
) -> None:
    current = _read_optional_observation(
        path,
        expected_parent_identity=expected_parent_identity,
    )
    if predecessor is None:
        if current is not None:
            raise ValueError("operator_profile_predecessor_changed")
        return
    if current is None:
        raise ValueError("operator_profile_predecessor_missing")
    _require_same_observation(current, predecessor)


def _require_enable_predecessor(
    predecessor: _ProfileObservation | None,
    expected_predecessor_sha256: str | None,
) -> None:
    if expected_predecessor_sha256 is None:
        if predecessor is not None:
            raise ValueError("operator_profile_predecessor_expected_absent")
        return
    if (
        predecessor is None
        or predecessor.profile.content_sha256 != expected_predecessor_sha256
    ):
        raise ValueError("operator_profile_predecessor_mismatch")


def _profile_matches_requested_enabled(
    profile: OperatorProfile,
    *,
    requested_runtime: Path,
    requested_runtime_identity: PathIdentity,
    requested_output: Path,
    requested_output_identity: PathIdentity,
) -> bool:
    return (
        profile.live_by_default
        and profile.runtime_root == requested_runtime
        and profile.runtime_root_identity == requested_runtime_identity
        and profile.output_base_root == requested_output
        and profile.output_base_root_identity == requested_output_identity
    )


def _require_root_bindings_unchanged(
    bindings: tuple[tuple[Path, PathIdentity], ...],
) -> None:
    for root, expected_identity in bindings:
        try:
            current_root = _validated_plain_root(root)
            current_identity = path_identity(current_root)
        except (FileNotFoundError, OSError, ValueError) as error:
            raise ValueError("operator_profile_root_identity_changed") from error
        if current_root != root or current_identity != expected_identity:
            raise ValueError("operator_profile_root_identity_changed")


def _register_observation(observation: _ProfileObservation) -> None:
    profile = observation.profile
    profile_id = id(profile)
    binding = _ProfileObservationBinding(
        profile_path=observation.profile_path,
        profile_parent_identity=observation.profile_parent_identity,
        profile_identity=observation.profile_identity,
        canonical_bytes=observation.canonical_bytes,
    )

    def discard(reference: ReferenceType[OperatorProfile]) -> None:
        with _profile_observations_lock:
            registered = _profile_observations.get(profile_id)
            if registered is not None and registered[0] is reference:
                _profile_observations.pop(profile_id, None)

    reference = ref(profile, discard)
    with _profile_observations_lock:
        _profile_observations[profile_id] = (reference, binding)


def _registered_observation(profile: OperatorProfile) -> _ProfileObservation:
    if not isinstance(profile, OperatorProfile):
        raise ValueError("operator_profile_expected_invalid")
    with _profile_observations_lock:
        registered = _profile_observations.get(id(profile))
    if registered is None or registered[0]() is not profile:
        raise ValueError("operator_profile_unbound")
    binding = registered[1]
    return _ProfileObservation(
        profile=profile,
        profile_path=binding.profile_path,
        profile_parent_identity=binding.profile_parent_identity,
        profile_identity=binding.profile_identity,
        canonical_bytes=binding.canonical_bytes,
    )


def _require_same_observation(
    current: _ProfileObservation,
    expected: _ProfileObservation,
) -> None:
    if current.profile_path != expected.profile_path:
        raise ValueError("operator_profile_path_changed")
    if current.profile_parent_identity != expected.profile_parent_identity:
        raise ValueError("operator_profile_parent_identity_changed")
    if current.profile_identity != expected.profile_identity:
        raise ValueError("operator_profile_identity_changed")
    if current.canonical_bytes != expected.canonical_bytes:
        raise ValueError("operator_profile_bytes_changed")
    if current.profile != expected.profile:
        raise ValueError("operator_profile_value_changed")


def _require_active_lease(lease: OperatorProfileLease) -> None:
    if not isinstance(lease, OperatorProfileLease):
        raise ValueError("operator_profile_lease_invalid")
    token = lease.lock_token
    if not isinstance(token, OperatorProfileLockToken):
        raise ValueError("operator_profile_lease_invalid")
    with _active_leases_lock:
        active = _active_leases.get(id(token))
    if active is None:
        raise ValueError("operator_profile_lease_inactive")
    active_token, active_lease, thread_id = active
    if active_token is not token or active_lease is not lease:
        raise ValueError("operator_profile_lease_invalid")
    if token._thread_id != thread_id or thread_id != get_ident():
        raise ValueError("operator_profile_lease_wrong_thread")


def _validated_plain_root(path: Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        raise ValueError("operator_profile_root_not_absolute")
    _require_windows_safe_absolute_path(
        candidate,
        error="operator_profile_root_windows_namespace_invalid",
    )
    require_plain_directory(candidate)
    require_same_identity_resolution(candidate)
    resolved = candidate.resolve(strict=True)
    _require_canonical_plain_directory(resolved)
    return resolved


def _canonical_existing_root(value: object, field: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(f"operator_profile_{field}_invalid")
    candidate = _require_windows_safe_absolute_path(
        Path(value),
        error=f"operator_profile_{field}_windows_namespace_invalid",
    )
    root = _validated_plain_root(candidate)
    if str(root) != value:
        raise ValueError(f"operator_profile_{field}_not_canonical")
    return root


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


def _require_disjoint_roots(
    runtime_root: Path,
    output_base_root: Path,
    state_root: Path,
) -> None:
    runtime_mapping = _physical_identity_mapping(runtime_root)
    output_mapping = _physical_identity_mapping(output_base_root)
    state_mapping = _physical_identity_mapping(state_root)
    if _identity_mappings_overlap(
        left_identities=runtime_mapping[0],
        left_remaining=runtime_mapping[1],
        right_identities=output_mapping[0],
        right_remaining=output_mapping[1],
    ):
        raise ValueError("operator_profile_root_overlap")
    if _identity_mappings_overlap(
        left_identities=runtime_mapping[0],
        left_remaining=runtime_mapping[1],
        right_identities=state_mapping[0],
        right_remaining=state_mapping[1],
    ) or _identity_mappings_overlap(
        left_identities=output_mapping[0],
        left_remaining=output_mapping[1],
        right_identities=state_mapping[0],
        right_remaining=state_mapping[1],
    ):
        raise ValueError("operator_profile_state_root_overlap")


def _physical_identity_mapping(
    path: Path,
) -> tuple[tuple[PathIdentity, ...], tuple[str, ...]]:
    nearest_existing = Path(path)
    remaining: list[str] = []
    while not path_lexists(nearest_existing):
        parent = nearest_existing.parent
        if parent == nearest_existing:
            raise FileNotFoundError(nearest_existing)
        remaining.append(nearest_existing.name)
        nearest_existing = parent

    identities: list[PathIdentity] = []
    current = nearest_existing
    while True:
        require_plain_directory(current)
        require_same_identity_resolution(current)
        identities.append(path_identity(current))
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
        raise ValueError("filesystem_identity_mapping_empty")
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


def _identity(value: object, field: str) -> PathIdentity:
    if (
        not isinstance(value, list)
        or len(value) != 3
        or any(type(item) is not int for item in value)
    ):
        raise ValueError(f"operator_profile_{field}_identity_invalid")
    return value[0], value[1], value[2]


def _require_standard_digest(value: object, field: str) -> str:
    if not isinstance(value, str) or _STANDARD_SHA256.fullmatch(value) is None:
        raise ValueError(f"operator_profile_{field}_sha256_invalid")
    return value


def _require_empty_plain_file(
    path: Path,
    error: str,
    *,
    expected_parent_identity: PathIdentity,
    wait_for_active_lock: bool = False,
) -> PathIdentity:
    status = plain_file_status(path)
    if status.st_size != 0:
        raise ValueError(error)
    identity = path_identity_from_status(status)
    if wait_for_active_lock:
        _require_lock_without_alternate_data_streams(
            path,
            expected_identity=identity,
            expected_parent_identity=expected_parent_identity,
        )
    else:
        require_no_alternate_data_streams(
            path,
            expected_identity=identity,
            expected_parent_identity=expected_parent_identity,
            directory=False,
            expected_size=0,
        )
    return identity


def _require_empty_plain_file_under_lock(
    path: Path,
    error: str,
    *,
    expected_identity: PathIdentity,
) -> None:
    status = plain_file_status(path)
    if status.st_size != 0:
        raise ValueError(error)
    if path_identity_from_status(status) != expected_identity:
        raise ValueError("operator_profile_lock_identity_changed")


def _require_safe_output_name(output_name: str) -> None:
    if (
        not output_name
        or output_name in {".", ".."}
        or "/" in output_name
        or "\\" in output_name
        or "\x00" in output_name
    ):
        raise ValueError("deck_output_name_component_invalid")
    if len(output_name) > 128:
        raise ValueError("deck_output_name_length_invalid")
    if output_name.endswith((".", " ")):
        raise ValueError("deck_output_name_trailing_character_invalid")
    if output_name.split(".", 1)[0].casefold() in _WINDOWS_RESERVED_NAMES:
        raise ValueError("deck_output_name_reserved")


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


__all__ = (
    "DeckOutputBinding",
    "OPERATOR_PROFILE_FIELDS",
    "OPERATOR_PROFILE_MAX_BYTES",
    "OPERATOR_PROFILE_SCHEMA_VERSION",
    "OperatorProfile",
    "OperatorProfileLease",
    "OperatorProfileLockToken",
    "derive_deck_output_binding",
    "disable_operator_profile",
    "enable_operator_profile",
    "lease_operator_profile",
    "load_operator_profile",
    "operator_profile_path",
    "revalidate_operator_profile",
    "revalidate_operator_profile_lease",
)
