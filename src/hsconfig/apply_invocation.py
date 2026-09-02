"""Closed apply-invocation authority and read-only runtime snapshot capture."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from hashlib import sha256
from hmac import compare_digest
from pathlib import Path
from secrets import token_bytes
from threading import Lock, get_ident
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Mapping

from hsconfig.deck_config_ini import read_deck_config
from hsconfig.package_io import (
    PathIdentity,
    capture_plain_ancestor_guard,
    path_identity,
    path_identity_from_status,
    path_lexists,
    plain_file_status,
    read_file_no_follow,
    require_plain_directory,
    require_same_identity_resolution,
    snapshot_bounded_filesystem_package,
)

if TYPE_CHECKING:
    from hsconfig.operator_profile import OperatorProfileLease


APPLY_INVOCATION_SCHEMA_VERSION = 1
APPLY_INVOCATION_MAX_BYTES = 128 * 1024
PRE_APPLY_TRANSACTION_IDS_MAX = 128
PRE_APPLY_TRANSACTION_IDS_ADMISSION_MAX = 127
PRE_APPLY_DECK_NAME_MAX_CHARS = 128
APPLY_INVOCATION_FIELDS = frozenset(
    {
        "schema_version",
        "apply_attempt_id",
        "run_id",
        "publication_revision",
        "publication_content_root_sha256",
        "output_operation_admission_path",
        "output_operation_admission_identity",
        "output_operation_admission_sha256",
        "output_child_binding_sha256",
        "output_child_path",
        "output_child_identity",
        "operator_profile_sha256",
        "runtime_root",
        "runtime_root_identity",
        "pre_apply_runtime_snapshot",
        "content_sha256",
    }
)
PRE_APPLY_RUNTIME_SNAPSHOT_FIELDS = frozenset(
    {
        "deck_name",
        "mapping_value",
        "deck_config_ini_sha256",
        "runtime_state_sha256",
        "last_apply_receipt_sha256",
        "runtime_tree_sha256",
        "transaction_ids",
        "content_sha256",
    }
)


_STANDARD_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
_RUN_ID = re.compile(r"[0-9a-f]{32}\Z")
_REVISION = re.compile(r"revisions/sha256-[0-9a-f]{64}\Z")
_STATE_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_TRANSACTION_FILE = re.compile(r"([0-9a-f]{32})\.json\Z")
_CONSTRUCT = object()
_SAME_ATTEMPT_DELTA_BEARER_CONSTRUCT = object()
_OPTIONAL_RUNTIME_FILE_MAX_BYTES = 4 * 1024 * 1024
_RUNTIME_COMPONENT_MAX_CHARS = 255
_WINDOWS_RESERVED_RUNTIME_COMPONENT_STEMS = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{suffix}" for suffix in "123456789"),
        *(f"lpt{suffix}" for suffix in "123456789"),
        *(f"com{suffix}" for suffix in ("¹", "²", "³")),
        *(f"lpt{suffix}" for suffix in ("¹", "²", "³")),
    }
)


@dataclass(frozen=True, slots=True, init=False)
class PreApplyRuntimeSnapshot:
    deck_name: str
    mapping_value: str | None
    deck_config_ini_sha256: str | None
    runtime_state_sha256: str | None
    last_apply_receipt_sha256: str | None
    runtime_tree_sha256: str | None
    transaction_ids: tuple[str, ...]
    content_sha256: str
    canonical_json: bytes = field(repr=False)

    def __init__(
        self,
        *,
        authority: object | None = None,
        value: Mapping[str, Any] | None = None,
        canonical_json: bytes | None = None,
    ) -> None:
        if (
            authority is not _CONSTRUCT
            or value is None
            or canonical_json is None
        ):
            raise TypeError("pre_apply_runtime_snapshot_not_constructible")
        object.__setattr__(self, "deck_name", value["deck_name"])
        object.__setattr__(self, "mapping_value", value["mapping_value"])
        object.__setattr__(
            self,
            "deck_config_ini_sha256",
            value["deck_config_ini_sha256"],
        )
        object.__setattr__(
            self,
            "runtime_state_sha256",
            value["runtime_state_sha256"],
        )
        object.__setattr__(
            self,
            "last_apply_receipt_sha256",
            value["last_apply_receipt_sha256"],
        )
        object.__setattr__(
            self,
            "runtime_tree_sha256",
            value["runtime_tree_sha256"],
        )
        object.__setattr__(
            self,
            "transaction_ids",
            tuple(value["transaction_ids"]),
        )
        object.__setattr__(self, "content_sha256", value["content_sha256"])
        object.__setattr__(self, "canonical_json", bytes(canonical_json))

    @property
    def value(self) -> Mapping[str, Any]:
        return MappingProxyType(_decode_canonical(self.canonical_json))

    def as_build_arguments(self) -> dict[str, Any]:
        return {
            "deck_name": self.deck_name,
            "mapping_value": self.mapping_value,
            "deck_config_ini_sha256": self.deck_config_ini_sha256,
            "runtime_state_sha256": self.runtime_state_sha256,
            "last_apply_receipt_sha256": self.last_apply_receipt_sha256,
            "runtime_tree_sha256": self.runtime_tree_sha256,
            "transaction_ids": self.transaction_ids,
        }


@dataclass(frozen=True, slots=True, init=False)
class ApplyInvocation:
    schema_version: int
    apply_attempt_id: str
    run_id: str
    publication_revision: str
    publication_content_root_sha256: str
    output_operation_admission_path: Path
    output_operation_admission_identity: PathIdentity
    output_operation_admission_sha256: str
    output_child_binding_sha256: str
    output_child_path: Path
    output_child_identity: PathIdentity
    operator_profile_sha256: str
    runtime_root: Path
    runtime_root_identity: PathIdentity
    pre_apply_runtime_snapshot: PreApplyRuntimeSnapshot
    content_sha256: str
    canonical_json: bytes = field(repr=False)

    def __init__(
        self,
        *,
        authority: object | None = None,
        value: Mapping[str, Any] | None = None,
        snapshot: PreApplyRuntimeSnapshot | None = None,
        canonical_json: bytes | None = None,
    ) -> None:
        if (
            authority is not _CONSTRUCT
            or value is None
            or snapshot is None
            or canonical_json is None
        ):
            raise TypeError("apply_invocation_not_constructible")
        object.__setattr__(self, "schema_version", value["schema_version"])
        object.__setattr__(self, "apply_attempt_id", value["apply_attempt_id"])
        object.__setattr__(self, "run_id", value["run_id"])
        object.__setattr__(
            self,
            "publication_revision",
            value["publication_revision"],
        )
        object.__setattr__(
            self,
            "publication_content_root_sha256",
            value["publication_content_root_sha256"],
        )
        object.__setattr__(
            self,
            "output_operation_admission_path",
            Path(value["output_operation_admission_path"]),
        )
        object.__setattr__(
            self,
            "output_operation_admission_identity",
            tuple(value["output_operation_admission_identity"]),
        )
        object.__setattr__(
            self,
            "output_operation_admission_sha256",
            value["output_operation_admission_sha256"],
        )
        object.__setattr__(
            self,
            "output_child_binding_sha256",
            value["output_child_binding_sha256"],
        )
        object.__setattr__(
            self,
            "output_child_path",
            Path(value["output_child_path"]),
        )
        object.__setattr__(
            self,
            "output_child_identity",
            tuple(value["output_child_identity"]),
        )
        object.__setattr__(
            self,
            "operator_profile_sha256",
            value["operator_profile_sha256"],
        )
        object.__setattr__(self, "runtime_root", Path(value["runtime_root"]))
        object.__setattr__(
            self,
            "runtime_root_identity",
            tuple(value["runtime_root_identity"]),
        )
        object.__setattr__(self, "pre_apply_runtime_snapshot", snapshot)
        object.__setattr__(self, "content_sha256", value["content_sha256"])
        object.__setattr__(self, "canonical_json", bytes(canonical_json))

    @property
    def value(self) -> Mapping[str, Any]:
        return MappingProxyType(_decode_canonical(self.canonical_json))


class _SameAttemptDeltaBearer:
    __slots__ = (
        "active",
        "apply_attempt_id",
        "current_snapshot_sha256",
        "nonce",
        "sealed_snapshot_sha256",
        "thread_id",
    )

    def __init__(
        self,
        *,
        authority: object | None = None,
        apply_attempt_id: str,
        sealed_snapshot_sha256: str,
        current_snapshot_sha256: str,
    ) -> None:
        if authority is not _SAME_ATTEMPT_DELTA_BEARER_CONSTRUCT:
            raise TypeError("same_attempt_delta_bearer_not_constructible")
        self.active = True
        self.apply_attempt_id = apply_attempt_id
        self.sealed_snapshot_sha256 = sealed_snapshot_sha256
        self.current_snapshot_sha256 = current_snapshot_sha256
        self.nonce = token_bytes(32)
        self.thread_id = get_ident()


@dataclass(eq=False, frozen=True, slots=True, init=False)
class ValidatedSameAttemptJournalDelta:
    """Opaque bearer minted later only by the authenticated runtime pair."""

    _bearer: _SameAttemptDeltaBearer = field(repr=False, compare=False)

    def __init__(self, _authority: object | None = None) -> None:
        raise TypeError("validated_same_attempt_delta_not_constructible")

    def __copy__(self) -> ValidatedSameAttemptJournalDelta:
        return self

    def __deepcopy__(
        self,
        _memo: dict[int, object],
    ) -> ValidatedSameAttemptJournalDelta:
        return self

    def __reduce__(self) -> None:
        raise TypeError("validated_same_attempt_delta_not_serializable")


@dataclass(frozen=True, slots=True)
class _SameAttemptDeltaRegistration:
    delta: ValidatedSameAttemptJournalDelta
    bearer: _SameAttemptDeltaBearer
    pair_authority: object
    runtime_admission: object
    pair_lifetime_validator: Callable[[], None]
    nonce: bytes
    apply_attempt_id: str
    sealed_snapshot_sha256: str
    current_snapshot_sha256: str
    thread_id: int


_same_attempt_delta_registry: dict[int, _SameAttemptDeltaRegistration] = {}
_same_attempt_delta_registry_lock = Lock()


def _mint_validated_same_attempt_journal_delta(
    *,
    pair_authority: object,
    runtime_admission: object,
    pair_lifetime_validator: Callable[[], None],
    sealed: PreApplyRuntimeSnapshot,
    current: PreApplyRuntimeSnapshot,
    apply_attempt_id: str,
) -> ValidatedSameAttemptJournalDelta:
    """Privately mint one pair-lifetime, current-thread, single-use bearer."""

    if (
        pair_authority is None
        or runtime_admission is None
        or not callable(pair_lifetime_validator)
    ):
        raise TypeError("validated_same_attempt_delta_pair_authority_required")
    if not isinstance(sealed, PreApplyRuntimeSnapshot) or not isinstance(
        current,
        PreApplyRuntimeSnapshot,
    ):
        raise TypeError("pre_apply_snapshot_required")
    _require_run_id(apply_attempt_id, "apply_attempt_id")
    pair_lifetime_validator()
    _require_exact_own_journal_projection(
        sealed=sealed,
        current=current,
        apply_attempt_id=apply_attempt_id,
    )
    bearer = _SameAttemptDeltaBearer(
        authority=_SAME_ATTEMPT_DELTA_BEARER_CONSTRUCT,
        apply_attempt_id=apply_attempt_id,
        sealed_snapshot_sha256=sealed.content_sha256,
        current_snapshot_sha256=current.content_sha256,
    )
    delta = object.__new__(ValidatedSameAttemptJournalDelta)
    object.__setattr__(delta, "_bearer", bearer)
    registration = _SameAttemptDeltaRegistration(
        delta=delta,
        bearer=bearer,
        pair_authority=pair_authority,
        runtime_admission=runtime_admission,
        pair_lifetime_validator=pair_lifetime_validator,
        nonce=bytes(bearer.nonce),
        apply_attempt_id=apply_attempt_id,
        sealed_snapshot_sha256=sealed.content_sha256,
        current_snapshot_sha256=current.content_sha256,
        thread_id=get_ident(),
    )
    with _same_attempt_delta_registry_lock:
        if id(delta) in _same_attempt_delta_registry:
            raise RuntimeError("validated_same_attempt_delta_registry_collision")
        _same_attempt_delta_registry[id(delta)] = registration
    return delta


def _retire_validated_same_attempt_journal_delta(
    *,
    validated_delta: ValidatedSameAttemptJournalDelta,
    pair_authority: object,
    runtime_admission: object,
) -> None:
    """Privately expire an unused bearer when its authenticated pair exits."""

    if not isinstance(validated_delta, ValidatedSameAttemptJournalDelta):
        raise TypeError("validated_same_attempt_delta_required")
    try:
        bearer = validated_delta._bearer
    except AttributeError as error:
        raise ValueError("validated_same_attempt_delta_invalid") from error
    if not isinstance(bearer, _SameAttemptDeltaBearer):
        raise ValueError("validated_same_attempt_delta_invalid")
    try:
        bearer_active = bearer.active
        bearer_nonce = bearer.nonce
    except AttributeError as error:
        raise ValueError("validated_same_attempt_delta_invalid") from error
    with _same_attempt_delta_registry_lock:
        registration = _same_attempt_delta_registry.get(id(validated_delta))
        if registration is None:
            if bearer_active is False:
                return
            raise ValueError("validated_same_attempt_delta_invalid")
        if (
            registration.delta is not validated_delta
            or registration.bearer is not bearer
            or registration.pair_authority is not pair_authority
            or registration.runtime_admission is not runtime_admission
            or registration.thread_id != get_ident()
            or bearer_active is not True
            or not isinstance(bearer_nonce, bytes)
            or not compare_digest(bearer_nonce, registration.nonce)
        ):
            raise ValueError("validated_same_attempt_delta_invalid")
        _same_attempt_delta_registry.pop(id(validated_delta))
        bearer.active = False


def build_pre_apply_runtime_snapshot(
    *,
    deck_name: str,
    mapping_value: str | None,
    deck_config_ini_sha256: str | None,
    runtime_state_sha256: str | None,
    last_apply_receipt_sha256: str | None,
    runtime_tree_sha256: str | None,
    transaction_ids: tuple[str, ...],
) -> PreApplyRuntimeSnapshot:
    unsigned: dict[str, Any] = {
        "deck_name": deck_name,
        "mapping_value": mapping_value,
        "deck_config_ini_sha256": deck_config_ini_sha256,
        "runtime_state_sha256": runtime_state_sha256,
        "last_apply_receipt_sha256": last_apply_receipt_sha256,
        "runtime_tree_sha256": runtime_tree_sha256,
        "transaction_ids": list(transaction_ids),
    }
    sealed = {**unsigned, "content_sha256": _self_digest(unsigned)}
    raw = _canonical_json(sealed)
    return _snapshot_from_value(sealed, raw=raw)


def build_apply_invocation(
    *,
    apply_attempt_id: str,
    run_id: str,
    publication_revision: str,
    publication_content_root_sha256: str,
    output_operation_admission_path: Path,
    output_operation_admission_identity: PathIdentity,
    output_operation_admission_sha256: str,
    output_child_binding_sha256: str,
    output_child_path: Path,
    output_child_identity: PathIdentity,
    operator_profile_sha256: str,
    runtime_root: Path,
    runtime_root_identity: PathIdentity,
    pre_apply_runtime_snapshot: PreApplyRuntimeSnapshot,
) -> ApplyInvocation:
    if not isinstance(pre_apply_runtime_snapshot, PreApplyRuntimeSnapshot):
        raise TypeError("pre_apply_runtime_snapshot_required")
    snapshot = _decode_canonical(pre_apply_runtime_snapshot.canonical_json)
    unsigned: dict[str, Any] = {
        "schema_version": APPLY_INVOCATION_SCHEMA_VERSION,
        "apply_attempt_id": apply_attempt_id,
        "run_id": run_id,
        "publication_revision": publication_revision,
        "publication_content_root_sha256": publication_content_root_sha256,
        "output_operation_admission_path": str(
            Path(output_operation_admission_path)
        ),
        "output_operation_admission_identity": list(
            output_operation_admission_identity
        ),
        "output_operation_admission_sha256": (
            output_operation_admission_sha256
        ),
        "output_child_binding_sha256": output_child_binding_sha256,
        "output_child_path": str(Path(output_child_path)),
        "output_child_identity": list(output_child_identity),
        "operator_profile_sha256": operator_profile_sha256,
        "runtime_root": str(Path(runtime_root)),
        "runtime_root_identity": list(runtime_root_identity),
        "pre_apply_runtime_snapshot": snapshot,
    }
    sealed = {**unsigned, "content_sha256": _self_digest(unsigned)}
    raw = _canonical_json(sealed)
    _require_apply_invocation_size(raw)
    return _invocation_from_value(sealed, raw=raw)


def parse_apply_invocation(content: bytes) -> ApplyInvocation:
    if not isinstance(content, bytes):
        raise TypeError("apply_invocation_bytes_required")
    _require_apply_invocation_size(content)
    value = _decode_json(content)
    if _canonical_json(value) != content:
        raise ValueError("apply_invocation_noncanonical")
    return _invocation_from_value(value, raw=content)


def load_apply_invocation(
    path: Path,
    *,
    expected_parent_identity: PathIdentity | None = None,
) -> ApplyInvocation:
    target = Path(path)
    ancestor_guard = capture_plain_ancestor_guard(target)
    ancestor_guard.validate()
    if (
        expected_parent_identity is not None
        and path_identity(target.parent) != expected_parent_identity
    ):
        raise ValueError("apply_invocation_parent_identity_changed")
    status = plain_file_status(target)
    raw = read_file_no_follow(
        target,
        expected_status=status,
        maximum_size=APPLY_INVOCATION_MAX_BYTES,
    )
    ancestor_guard.validate()
    if (
        expected_parent_identity is not None
        and path_identity(target.parent) != expected_parent_identity
    ):
        raise ValueError("apply_invocation_parent_identity_changed")
    if path_identity_from_status(status) != path_identity(target):
        raise ValueError("apply_invocation_identity_changed")
    ancestor_guard.validate()
    invocation = parse_apply_invocation(raw)
    ancestor_guard.validate()
    if (
        expected_parent_identity is not None
        and path_identity(target.parent) != expected_parent_identity
    ):
        raise ValueError("apply_invocation_parent_identity_changed")
    if path_identity_from_status(status) != path_identity(target):
        raise ValueError("apply_invocation_identity_changed")
    return invocation


def capture_pre_apply_runtime_snapshot(
    *,
    runtime_root: Path,
    expected_runtime_root_identity: PathIdentity,
    deck_name: str,
    state_key: str,
    profile_lease: OperatorProfileLease,
) -> PreApplyRuntimeSnapshot:
    root = _require_runtime_root(
        runtime_root,
        expected_identity=expected_runtime_root_identity,
        profile_lease=profile_lease,
    )
    _require_deck_name(deck_name)
    if not isinstance(state_key, str) or _STATE_KEY.fullmatch(state_key) is None:
        raise ValueError("pre_apply_state_key_invalid")

    ini_path = root / "CustomConfig" / "deck_config.ini"
    ini_guard = capture_plain_ancestor_guard(ini_path)
    ini_guard.validate()
    if path_lexists(ini_path.parent):
        require_plain_directory(ini_path.parent)
        ini_snapshot = read_deck_config(ini_path, deck_name=deck_name)
    else:
        ini_snapshot = None
    ini_guard.validate()
    if ini_snapshot is None and path_lexists(ini_path):
        raise ValueError("pre_apply_deck_config_inventory_changed")
    mapping_value = (
        None if ini_snapshot is None else ini_snapshot.selected_config_dir
    )
    ini_digest = (
        None
        if ini_snapshot is None or ini_snapshot.sha256 is None
        else f"sha256:{ini_snapshot.sha256}"
    )

    runtime_state_sha256 = _optional_file_digest(
        root / ".hsconfig" / "state.json"
    )
    last_receipt_sha256 = _optional_file_digest(
        root
        / ".hsconfig"
        / "receipts"
        / state_key
        / "last_apply_receipt.json"
    )
    runtime_tree_sha256 = (
        None
        if mapping_value is None
        else _runtime_tree_digest(root / "CustomConfig" / mapping_value)
    )
    transaction_ids = _capture_transaction_ids(
        root / ".hsconfig" / "transactions"
    )
    _require_runtime_root(
        root,
        expected_identity=expected_runtime_root_identity,
        profile_lease=profile_lease,
    )
    return build_pre_apply_runtime_snapshot(
        deck_name=deck_name,
        mapping_value=mapping_value,
        deck_config_ini_sha256=ini_digest,
        runtime_state_sha256=runtime_state_sha256,
        last_apply_receipt_sha256=last_receipt_sha256,
        runtime_tree_sha256=runtime_tree_sha256,
        transaction_ids=transaction_ids,
    )


def require_apply_invocation_admission_capacity(
    invocation: ApplyInvocation,
) -> None:
    if not isinstance(invocation, ApplyInvocation):
        raise TypeError("apply_invocation_required")
    identifiers = invocation.pre_apply_runtime_snapshot.transaction_ids
    if len(identifiers) > PRE_APPLY_TRANSACTION_IDS_ADMISSION_MAX:
        raise ValueError("pre_apply_transaction_capacity_exhausted")
    if invocation.apply_attempt_id in identifiers:
        raise ValueError("pre_apply_attempt_id_already_present")


def require_same_attempt_pre_apply_snapshot(
    *,
    sealed: PreApplyRuntimeSnapshot,
    current: PreApplyRuntimeSnapshot,
    apply_attempt_id: str,
    validated_delta: ValidatedSameAttemptJournalDelta | None,
) -> None:
    if not isinstance(sealed, PreApplyRuntimeSnapshot) or not isinstance(
        current,
        PreApplyRuntimeSnapshot,
    ):
        raise TypeError("pre_apply_snapshot_required")
    _require_run_id(apply_attempt_id, "apply_attempt_id")
    if apply_attempt_id in sealed.transaction_ids:
        raise ValueError("pre_apply_snapshot_attempt_preexisting")
    if validated_delta is None:
        if current.canonical_json != sealed.canonical_json:
            raise ValueError("pre_apply_snapshot_changed")
        return
    if not isinstance(validated_delta, ValidatedSameAttemptJournalDelta):
        raise TypeError("validated_same_attempt_delta_required")
    registration = _consume_validated_same_attempt_delta(validated_delta)
    if (
        registration.apply_attempt_id != apply_attempt_id
        or registration.sealed_snapshot_sha256 != sealed.content_sha256
        or registration.current_snapshot_sha256 != current.content_sha256
    ):
        raise ValueError("validated_same_attempt_delta_invalid")
    _require_exact_own_journal_projection(
        sealed=sealed,
        current=current,
        apply_attempt_id=apply_attempt_id,
    )


def _consume_validated_same_attempt_delta(
    validated_delta: ValidatedSameAttemptJournalDelta,
) -> _SameAttemptDeltaRegistration:
    bearer = _delta_bearer_or_error(validated_delta)
    with _same_attempt_delta_registry_lock:
        registration = _same_attempt_delta_registry.pop(
            id(validated_delta),
            None,
        )
        if registration is None:
            raise ValueError("validated_same_attempt_delta_invalid")
        bearer.active = False
    try:
        bearer_matches = (
            bearer.thread_id == registration.thread_id
            and bearer.apply_attempt_id == registration.apply_attempt_id
            and bearer.sealed_snapshot_sha256
            == registration.sealed_snapshot_sha256
            and bearer.current_snapshot_sha256
            == registration.current_snapshot_sha256
            and compare_digest(bearer.nonce, registration.nonce)
        )
    except (AttributeError, TypeError):
        bearer_matches = False
    if (
        registration.delta is not validated_delta
        or registration.bearer is not bearer
        or registration.thread_id != get_ident()
        or not bearer_matches
    ):
        raise ValueError("validated_same_attempt_delta_invalid")
    try:
        registration.pair_lifetime_validator()
    except Exception as error:
        raise ValueError(
            "validated_same_attempt_delta_lifetime_invalid"
        ) from error
    return registration


def _delta_bearer_or_error(
    validated_delta: ValidatedSameAttemptJournalDelta,
) -> _SameAttemptDeltaBearer:
    try:
        bearer = validated_delta._bearer
    except AttributeError as error:
        raise ValueError("validated_same_attempt_delta_invalid") from error
    try:
        active = bearer.active
        nonce = bearer.nonce
    except AttributeError as error:
        raise ValueError("validated_same_attempt_delta_invalid") from error
    if (
        not isinstance(bearer, _SameAttemptDeltaBearer)
        or active is not True
        or not isinstance(nonce, bytes)
        or len(nonce) != 32
    ):
        raise ValueError("validated_same_attempt_delta_invalid")
    return bearer


def _require_exact_own_journal_projection(
    *,
    sealed: PreApplyRuntimeSnapshot,
    current: PreApplyRuntimeSnapshot,
    apply_attempt_id: str,
) -> None:
    if apply_attempt_id in sealed.transaction_ids:
        raise ValueError("pre_apply_snapshot_attempt_preexisting")
    expected_ids = tuple(sorted((*sealed.transaction_ids, apply_attempt_id)))
    if current.transaction_ids != expected_ids:
        raise ValueError("pre_apply_snapshot_transaction_delta_invalid")
    projected = build_pre_apply_runtime_snapshot(
        **{
            **current.as_build_arguments(),
            "transaction_ids": tuple(
                identifier
                for identifier in current.transaction_ids
                if identifier != apply_attempt_id
            ),
        }
    )
    if projected.canonical_json != sealed.canonical_json:
        raise ValueError("pre_apply_snapshot_projection_invalid")


def _snapshot_from_value(
    value: Any,
    *,
    raw: bytes,
) -> PreApplyRuntimeSnapshot:
    if not isinstance(value, dict) or set(value) != PRE_APPLY_RUNTIME_SNAPSHOT_FIELDS:
        raise ValueError("pre_apply_runtime_snapshot_fields_invalid")
    _require_deck_name(value.get("deck_name"))
    mapping = value.get("mapping_value")
    if mapping is not None:
        _require_safe_component(mapping, "mapping_value")
    for field_name in (
        "deck_config_ini_sha256",
        "runtime_state_sha256",
        "last_apply_receipt_sha256",
        "runtime_tree_sha256",
    ):
        digest = value.get(field_name)
        if digest is not None:
            _require_digest(digest, field_name)
    identifiers = value.get("transaction_ids")
    if (
        not isinstance(identifiers, list)
        or len(identifiers) > PRE_APPLY_TRANSACTION_IDS_MAX
        or any(
            not isinstance(identifier, str)
            or _RUN_ID.fullmatch(identifier) is None
            for identifier in identifiers
        )
        or identifiers != sorted(set(identifiers))
    ):
        raise ValueError("pre_apply_transaction_ids_invalid")
    _require_self_digest(value, "pre_apply_runtime_snapshot")
    if _canonical_json(value) != raw:
        raise ValueError("pre_apply_runtime_snapshot_noncanonical")
    return PreApplyRuntimeSnapshot(
        authority=_CONSTRUCT,
        value=value,
        canonical_json=raw,
    )


def _invocation_from_value(value: Any, *, raw: bytes) -> ApplyInvocation:
    _require_apply_invocation_size(raw)
    if not isinstance(value, dict) or set(value) != APPLY_INVOCATION_FIELDS:
        raise ValueError("apply_invocation_fields_invalid")
    if (
        type(value.get("schema_version")) is not int
        or value["schema_version"] != APPLY_INVOCATION_SCHEMA_VERSION
    ):
        raise ValueError("apply_invocation_schema_invalid")
    _require_run_id(value.get("apply_attempt_id"), "apply_attempt_id")
    _require_run_id(value.get("run_id"), "run_id")
    revision = value.get("publication_revision")
    if not isinstance(revision, str) or _REVISION.fullmatch(revision) is None:
        raise ValueError("apply_invocation_revision_invalid")
    for field_name in (
        "publication_content_root_sha256",
        "output_operation_admission_sha256",
        "output_child_binding_sha256",
        "operator_profile_sha256",
    ):
        _require_digest(value.get(field_name), field_name)
    for field_name in (
        "output_operation_admission_path",
        "output_child_path",
        "runtime_root",
    ):
        _require_canonical_absolute_path(value.get(field_name), field_name)
    for field_name in (
        "output_operation_admission_identity",
        "output_child_identity",
        "runtime_root_identity",
    ):
        _require_identity(value.get(field_name), field_name)
    snapshot_value = value.get("pre_apply_runtime_snapshot")
    snapshot_raw = _canonical_json(snapshot_value)
    snapshot = _snapshot_from_value(snapshot_value, raw=snapshot_raw)
    _require_self_digest(value, "apply_invocation")
    if _canonical_json(value) != raw:
        raise ValueError("apply_invocation_noncanonical")
    return ApplyInvocation(
        authority=_CONSTRUCT,
        value=value,
        snapshot=snapshot,
        canonical_json=raw,
    )


def _require_runtime_root(
    runtime_root: Path,
    *,
    expected_identity: PathIdentity,
    profile_lease: OperatorProfileLease,
) -> Path:
    root = Path(runtime_root)
    _require_canonical_absolute_path(str(root), "runtime_root")
    require_plain_directory(root)
    require_same_identity_resolution(root)
    identity = _require_identity(expected_identity, "runtime_root_identity")
    if path_identity(root) != identity:
        raise ValueError("pre_apply_runtime_root_identity_changed")
    from hsconfig.operator_profile import (
        OperatorProfileLease,
        revalidate_operator_profile_lease,
    )

    if not isinstance(profile_lease, OperatorProfileLease):
        raise TypeError("operator_profile_lease_required")
    profile = revalidate_operator_profile_lease(profile_lease)
    if profile.runtime_root != root or profile.runtime_root_identity != identity:
        raise ValueError("pre_apply_runtime_profile_binding_invalid")
    return root


def _optional_file_digest(path: Path) -> str | None:
    ancestor_guard = capture_plain_ancestor_guard(path)
    ancestor_guard.validate()
    if not path_lexists(path):
        ancestor_guard.validate()
        if path_lexists(path):
            raise ValueError("pre_apply_runtime_file_inventory_changed")
        return None
    status = plain_file_status(path)
    content = read_file_no_follow(
        path,
        expected_status=status,
        maximum_size=_OPTIONAL_RUNTIME_FILE_MAX_BYTES,
    )
    ancestor_guard.validate()
    if path_identity(path) != path_identity_from_status(status):
        raise ValueError("pre_apply_runtime_file_identity_changed")
    return "sha256:" + sha256(content).hexdigest()


def _runtime_tree_digest(root: Path) -> str | None:
    ancestor_guard = capture_plain_ancestor_guard(root)
    ancestor_guard.validate()
    if not path_lexists(root):
        ancestor_guard.validate()
        if path_lexists(root):
            raise ValueError("pre_apply_runtime_tree_inventory_changed")
        return None
    require_plain_directory(root)
    require_same_identity_resolution(root)
    root_identity = path_identity(root)
    view = snapshot_bounded_filesystem_package(root)
    ancestor_guard.validate()
    if path_identity(root) != root_identity:
        raise ValueError("pre_apply_runtime_tree_identity_changed")
    records = b"".join(
        (
            f"{name}\0{len(content)}\0{sha256(content).hexdigest()}\n"
        ).encode("utf-8")
        for name in view.file_names()
        for content in (view.read_bytes(name),)
    )
    return "sha256:" + sha256(records).hexdigest()


def _capture_transaction_ids(root: Path) -> tuple[str, ...]:
    ancestor_guard = capture_plain_ancestor_guard(root)
    ancestor_guard.validate()
    if not path_lexists(root):
        ancestor_guard.validate()
        if path_lexists(root):
            raise ValueError("pre_apply_transaction_inventory_changed")
        return ()
    require_plain_directory(root)
    require_same_identity_resolution(root)
    root_identity = path_identity(root)
    identifiers: list[str] = []
    inventory: list[tuple[str, PathIdentity]] = []
    with os.scandir(root) as iterator:
        for entry in iterator:
            if len(identifiers) >= PRE_APPLY_TRANSACTION_IDS_MAX:
                raise ValueError("pre_apply_transaction_inventory_limit")
            path = Path(entry.path)
            status = plain_file_status(path)
            match = _TRANSACTION_FILE.fullmatch(entry.name)
            if match is None:
                raise ValueError("pre_apply_transaction_inventory_invalid")
            if path_identity(path) != path_identity_from_status(status):
                raise ValueError("pre_apply_transaction_identity_changed")
            identifiers.append(match.group(1))
            inventory.append((entry.name, path_identity_from_status(status)))
    ancestor_guard.validate()
    if path_identity(root) != root_identity:
        raise ValueError("pre_apply_transaction_root_identity_changed")
    observed: list[tuple[str, PathIdentity]] = []
    with os.scandir(root) as iterator:
        for entry in iterator:
            if len(observed) >= PRE_APPLY_TRANSACTION_IDS_MAX:
                raise ValueError("pre_apply_transaction_inventory_limit")
            status = plain_file_status(Path(entry.path))
            observed.append((entry.name, path_identity_from_status(status)))
    if sorted(observed) != sorted(inventory):
        raise ValueError("pre_apply_transaction_inventory_changed")
    ancestor_guard.validate()
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("pre_apply_transaction_inventory_duplicate")
    return tuple(sorted(identifiers))


def _require_deck_name(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= PRE_APPLY_DECK_NAME_MAX_CHARS
        or value != value.strip()
        or any(ord(character) < 0x20 for character in value)
    ):
        raise ValueError("pre_apply_deck_name_invalid")
    return value


def _require_safe_component(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > _RUNTIME_COMPONENT_MAX_CHARS
        or value in {".", ".."}
        or Path(value).name != value
        or any(character in value for character in '<>:"/\\|?*\0')
        or any(ord(character) < 32 for character in value)
        or value.endswith((".", " "))
        or value.split(".", 1)[0].rstrip(" .").casefold()
        in _WINDOWS_RESERVED_RUNTIME_COMPONENT_STEMS
    ):
        raise ValueError(f"pre_apply_{field_name}_invalid")
    return value


def _require_digest(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _STANDARD_SHA256.fullmatch(value) is None:
        raise ValueError(f"apply_invocation_{field_name}_invalid")
    return value


def _require_run_id(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _RUN_ID.fullmatch(value) is None:
        raise ValueError(f"apply_invocation_{field_name}_invalid")
    return value


def _require_identity(value: object, field_name: str) -> PathIdentity:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 3
        or any(type(item) is not int or item < 0 for item in value)
    ):
        raise ValueError(f"apply_invocation_{field_name}_invalid")
    return value[0], value[1], value[2]


def _require_canonical_absolute_path(value: object, field_name: str) -> Path:
    if not isinstance(value, str):
        raise ValueError(f"apply_invocation_{field_name}_invalid")
    path = Path(value)
    if (
        not path.is_absolute()
        or os.path.abspath(os.path.normpath(value)) != value
        or str(path) != value
    ):
        raise ValueError(f"apply_invocation_{field_name}_invalid")
    return path


def _require_apply_invocation_size(content: bytes) -> None:
    if len(content) > APPLY_INVOCATION_MAX_BYTES:
        raise ValueError("apply_invocation_too_large")


def _require_self_digest(value: Mapping[str, Any], name: str) -> None:
    claimed = value.get("content_sha256")
    _require_digest(claimed, f"{name}_content_sha256")
    unsigned = dict(value)
    unsigned.pop("content_sha256")
    if claimed != _self_digest(unsigned):
        raise ValueError(f"{name}_content_sha256_mismatch")


def _decode_json(content: bytes) -> Any:
    try:
        return json.loads(
            content.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_non_finite,
        )
    except UnicodeDecodeError as error:
        raise ValueError("apply_invocation_encoding_invalid") from error
    except RecursionError as error:
        raise ValueError("apply_invocation_json_invalid") from error


def _decode_canonical(content: bytes) -> dict[str, Any]:
    value = _decode_json(content)
    if not isinstance(value, dict) or _canonical_json(value) != content:
        raise ValueError("apply_invocation_internal_noncanonical")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate_json_key")
        value[key] = item
    return value


def _reject_non_finite(value: str) -> None:
    raise ValueError(f"non_finite_json_value:{value}")


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (RecursionError, TypeError, ValueError) as error:
        raise ValueError("apply_invocation_json_invalid") from error


def _self_digest(value: Mapping[str, Any]) -> str:
    return "sha256:" + sha256(_canonical_json(value)).hexdigest()


__all__ = (
    "APPLY_INVOCATION_FIELDS",
    "APPLY_INVOCATION_MAX_BYTES",
    "APPLY_INVOCATION_SCHEMA_VERSION",
    "PRE_APPLY_DECK_NAME_MAX_CHARS",
    "PRE_APPLY_RUNTIME_SNAPSHOT_FIELDS",
    "PRE_APPLY_TRANSACTION_IDS_ADMISSION_MAX",
    "PRE_APPLY_TRANSACTION_IDS_MAX",
    "ApplyInvocation",
    "PreApplyRuntimeSnapshot",
    "ValidatedSameAttemptJournalDelta",
    "build_apply_invocation",
    "build_pre_apply_runtime_snapshot",
    "capture_pre_apply_runtime_snapshot",
    "load_apply_invocation",
    "parse_apply_invocation",
    "require_apply_invocation_admission_capacity",
    "require_same_attempt_pre_apply_snapshot",
)
