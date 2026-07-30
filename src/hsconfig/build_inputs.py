from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
from pathlib import PurePosixPath, PureWindowsPath
import re
from typing import Any

from hsconfig.package_domain import _ImmutableAuthorityNode


_SCHEMA_VERSION = 2
_PAYLOAD_FIELDS = frozenset(
    {
        "schema_version",
        "generator_version",
        "generator_commit",
        "deck_name",
        "deck_code_sha256",
        "deck_fingerprint",
        "card_snapshot_id",
        "card_snapshot_sha256",
        "policy_profile_id",
        "policy_profile_sha256",
        "as_of_date",
        "source_bundle_sha256s",
        "evidence_policy_ids",
        "deck_cards_resource_sha256",
        "card_snapshot_resource_sha256",
        "policy_profile_resource_sha256",
        "evidence_contract_resource_sha256",
        "source_bundle_resource_sha256s",
        "globalvalues_baseline_resource_sha256",
    }
)
_RAW_DECK_CODE_FIELDS = frozenset(
    {"deck_code", "deck_code_raw", "deckstring", "raw_deck_code"}
)
_RAW_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_CONTENT_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
_STABLE_IDENTIFIER_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]*(?::[A-Za-z0-9][A-Za-z0-9._-]*)*"
)
_WINDOWS_DRIVE_PREFIX_PATTERN = re.compile(r"[A-Za-z]:")


@dataclass(frozen=True, init=False)
class CanonicalBuildInputs(_ImmutableAuthorityNode):
    schema_version: int
    generator_version: str
    generator_commit: str
    deck_name: str
    deck_code_sha256: str
    deck_fingerprint: str
    card_snapshot_id: str
    card_snapshot_sha256: str
    policy_profile_id: str
    policy_profile_sha256: str
    as_of_date: str
    source_bundle_sha256s: tuple[str, ...]
    evidence_policy_ids: tuple[str, ...]
    deck_cards_resource_sha256: str
    card_snapshot_resource_sha256: str
    policy_profile_resource_sha256: str
    evidence_contract_resource_sha256: str
    source_bundle_resource_sha256s: tuple[str, ...]
    globalvalues_baseline_resource_sha256: str
    canonical_payload: bytes
    input_sha256: str


def canonicalize_build_inputs(
    payload: Mapping[str, Any],
) -> CanonicalBuildInputs:
    if not isinstance(payload, Mapping):
        raise ValueError("build_inputs_payload_invalid")
    payload_keys = frozenset(payload)
    if payload_keys & _RAW_DECK_CODE_FIELDS:
        raise ValueError("build_inputs_raw_deck_code_forbidden")
    missing = _PAYLOAD_FIELDS - payload_keys
    if missing:
        raise ValueError("build_inputs_missing_keys")
    unknown = payload_keys - _PAYLOAD_FIELDS
    if unknown:
        raise ValueError("build_inputs_unknown_keys")
    if (
        type(payload["schema_version"]) is not int
        or payload["schema_version"] != _SCHEMA_VERSION
    ):
        raise ValueError("build_inputs_schema_version_invalid")

    generator_version = _normalized_text(payload["generator_version"])
    generator_commit = _normalized_text(payload["generator_commit"])
    deck_name = _normalized_text(payload["deck_name"])
    deck_code_sha256 = _raw_sha256(payload["deck_code_sha256"])
    deck_fingerprint = _raw_sha256(payload["deck_fingerprint"])
    card_snapshot_id = _normalized_stable_identifier(payload["card_snapshot_id"])
    card_snapshot_sha256 = _content_sha256(payload["card_snapshot_sha256"])
    policy_profile_id = _normalized_stable_identifier(payload["policy_profile_id"])
    policy_profile_sha256 = _content_sha256(payload["policy_profile_sha256"])
    as_of_date = _normalized_date(payload["as_of_date"])
    source_bundle_sha256s = _normalized_reference_sequence(
        payload["source_bundle_sha256s"],
        normalizer=_content_sha256,
    )
    evidence_policy_ids = _normalized_reference_sequence(
        payload["evidence_policy_ids"],
        normalizer=_normalized_stable_identifier,
    )
    deck_cards_resource_sha256 = _content_sha256(
        payload["deck_cards_resource_sha256"]
    )
    card_snapshot_resource_sha256 = _content_sha256(
        payload["card_snapshot_resource_sha256"]
    )
    policy_profile_resource_sha256 = _content_sha256(
        payload["policy_profile_resource_sha256"]
    )
    evidence_contract_resource_sha256 = _content_sha256(
        payload["evidence_contract_resource_sha256"]
    )
    source_bundle_resource_sha256s = _normalized_reference_sequence(
        payload["source_bundle_resource_sha256s"],
        normalizer=_content_sha256,
    )
    globalvalues_baseline_resource_sha256 = _content_sha256(
        payload["globalvalues_baseline_resource_sha256"]
    )

    normalized_payload = {
        "schema_version": _SCHEMA_VERSION,
        "generator_version": generator_version,
        "generator_commit": generator_commit,
        "deck_name": deck_name,
        "deck_code_sha256": deck_code_sha256,
        "deck_fingerprint": deck_fingerprint,
        "card_snapshot_id": card_snapshot_id,
        "card_snapshot_sha256": card_snapshot_sha256,
        "policy_profile_id": policy_profile_id,
        "policy_profile_sha256": policy_profile_sha256,
        "as_of_date": as_of_date,
        "source_bundle_sha256s": source_bundle_sha256s,
        "evidence_policy_ids": evidence_policy_ids,
        "deck_cards_resource_sha256": deck_cards_resource_sha256,
        "card_snapshot_resource_sha256": card_snapshot_resource_sha256,
        "policy_profile_resource_sha256": policy_profile_resource_sha256,
        "evidence_contract_resource_sha256": (
            evidence_contract_resource_sha256
        ),
        "source_bundle_resource_sha256s": (
            source_bundle_resource_sha256s
        ),
        "globalvalues_baseline_resource_sha256": (
            globalvalues_baseline_resource_sha256
        ),
    }
    canonical_payload = json.dumps(
        normalized_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return CanonicalBuildInputs(
        schema_version=_SCHEMA_VERSION,
        generator_version=generator_version,
        generator_commit=generator_commit,
        deck_name=deck_name,
        deck_code_sha256=deck_code_sha256,
        deck_fingerprint=deck_fingerprint,
        card_snapshot_id=card_snapshot_id,
        card_snapshot_sha256=card_snapshot_sha256,
        policy_profile_id=policy_profile_id,
        policy_profile_sha256=policy_profile_sha256,
        as_of_date=as_of_date,
        source_bundle_sha256s=source_bundle_sha256s,
        evidence_policy_ids=evidence_policy_ids,
        deck_cards_resource_sha256=deck_cards_resource_sha256,
        card_snapshot_resource_sha256=card_snapshot_resource_sha256,
        policy_profile_resource_sha256=policy_profile_resource_sha256,
        evidence_contract_resource_sha256=evidence_contract_resource_sha256,
        source_bundle_resource_sha256s=source_bundle_resource_sha256s,
        globalvalues_baseline_resource_sha256=(
            globalvalues_baseline_resource_sha256
        ),
        canonical_payload=canonical_payload,
        input_sha256=sha256(canonical_payload).hexdigest(),
    )


def _normalized_text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("build_inputs_text_invalid")
    normalized = value.strip()
    if any(ord(character) < 32 for character in normalized):
        raise ValueError("build_inputs_text_invalid")
    if _is_absolute_path(normalized):
        raise ValueError("build_inputs_absolute_path_forbidden")
    return normalized


def _is_absolute_path(value: str) -> bool:
    return (
        value.lower().startswith("file:")
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
    )


def _normalized_stable_identifier(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("build_inputs_identifier_invalid")
    normalized = value.strip()
    if (
        any(ord(character) < 32 for character in normalized)
        or "/" in normalized
        or "\\" in normalized
        or ".." in normalized
        or normalized.casefold().startswith("file:")
        or _WINDOWS_DRIVE_PREFIX_PATTERN.match(normalized) is not None
        or normalized.casefold().endswith(".json")
        or _STABLE_IDENTIFIER_PATTERN.fullmatch(normalized) is None
    ):
        raise ValueError("build_inputs_identifier_invalid")
    return normalized


def _raw_sha256(value: Any) -> str:
    if not isinstance(value, str) or _RAW_SHA256_PATTERN.fullmatch(value) is None:
        raise ValueError("build_inputs_sha256_invalid")
    return value


def _content_sha256(value: Any) -> str:
    if (
        not isinstance(value, str)
        or _CONTENT_SHA256_PATTERN.fullmatch(value) is None
    ):
        raise ValueError("build_inputs_sha256_invalid")
    return value


def _normalized_date(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("build_inputs_as_of_date_invalid")
    normalized = value.strip()
    try:
        return date.fromisoformat(normalized).isoformat()
    except ValueError as error:
        raise ValueError("build_inputs_as_of_date_invalid") from error


def _normalized_reference_sequence(
    value: Any,
    *,
    normalizer: Callable[[Any], str],
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("build_inputs_reference_sequence_invalid")
    normalized = tuple(normalizer(item) for item in value)
    if len(set(normalized)) != len(normalized):
        raise ValueError("build_inputs_duplicate_ids")
    return tuple(sorted(normalized))


__all__ = ("CanonicalBuildInputs", "canonicalize_build_inputs")
