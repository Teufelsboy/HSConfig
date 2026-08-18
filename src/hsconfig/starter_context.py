"""Deterministic, read-only context for optimized starter strategy."""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime, time as datetime_time
from decimal import Decimal, InvalidOperation
from enum import Enum
from hashlib import sha256
import json
import re
from typing import Any
import unicodedata
from urllib.parse import urlsplit

from hsconfig.audited_deck_catalog import load_audited_deck_catalog
from hsconfig.build_input_catalog import load_packaged_audited_build_inputs
from hsconfig.compile_globalvalues import validate_globalvalues_overlay_value
from hsconfig.condition_format import (
    ALLOWED_ATOM_PATTERNS,
    ALLOWED_HERO_CLASSES,
    REPORT_ONLY_CONDITION_KEYS,
    STRUCTURED_RUNTIME_CONDITION_KEYS,
    classify_runtime_condition,
)
from hsconfig.deck_identity import stable_deck_fingerprint
from hsconfig.globalvalues_decisions import (
    GLOBALVALUES_BASELINE_DECISION_KEYS,
    canonical_globalvalues_baseline_sha256,
)
from hsconfig.package_request import PackageResolutionSnapshot
from hsconfig.source_acquisition_provenance import (
    acquisition_provenance_is_canonical,
)
from hsconfig.source_evidence_verifier import source_ref_is_public_https
from hsconfig.source_document_model import (
    SUPPORTED_CLAIM_READINESS,
    SUPPORTED_SPECIFICITY_STATUSES,
)
from hsconfig.source_semantic_qualifiers import (
    QUALIFIER_KEYS,
    normalize_semantic_qualifiers,
)
from hsconfig.starter_contract import (
    STARTER_CONTEXT_MAX_BYTES,
    STARTER_CONTEXT_FIELDS,
    STARTER_SCHEMA_VERSION,
)
from hsconfig.starter_document import StarterDocument, seal_starter_document
from hsconfig.visionai_registry import (
    CARD_BEHAVIOR_BLOCKS,
    CLAIM_SURFACE_REGISTRY,
    GLOBALVALUES_KEY_REGISTRY,
    RUNTIME_ROW_SCHEMA_KEYS,
    RUNTIME_SURFACE_REGISTRY,
    STARTER_CARD_VALUE_CONSTRAINT,
    STARTER_COMBO_VALUE_CONSTRAINT,
    STARTER_GLOBALVALUE_CONSTRAINTS,
    RuntimeValueConstraint,
)


_RAW_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_EVIDENCE_HASH_RE = re.compile(r"[0-9a-f]{16}\Z")
_CARD_ID_RE = re.compile(
    r"(?=.{3,64}\Z)(?=.*[0-9])[A-Z0-9]+(?:_[A-Za-z0-9]+)+\Z"
)
_CARD_TEXT_FORMATTING_RE = re.compile(r"<(/?)(b|i)>", re.IGNORECASE)
_CANONICAL_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
_CANONICAL_REFERENCE_RE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._-]*(?::[A-Za-z0-9][A-Za-z0-9._-]*)?\Z"
)
_CONTENT_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_WINDOWS_DRIVE_PATH_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
_UNC_PATH_TOKEN_RE = re.compile(r"(?<![\\])\\\\[^\\/\s]+[\\/][^\\/\s]+")
_ROOTED_BACKSLASH_PATH_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9\\])\\(?![\\\s])"
)
_POSIX_ABSOLUTE_PATH_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9/])/(?![/\s])")
_RELATIVE_TRAVERSAL_PATH_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9.])\.\.[\\/]"
)
_URI_SCHEME_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9+.-])[A-Za-z][A-Za-z0-9+.-]{0,31}:(?=\S)"
)
_CANONICAL_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_CANONICAL_ISO_TIMESTAMP_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?\Z"
)
_CANONICAL_ISO_TIME_RE = re.compile(
    r"\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?\Z"
)
_CANONICAL_ISO_DURATION_RE = re.compile(
    r"P(?=.*\d)(?:\d+(?:\.\d+)?[YMWD])*"
    r"(?:T(?:\d+(?:\.\d+)?[HMS])*)?\Z"
)
_NUMERIC_DURATION_RE = re.compile(
    r"\d+(?:\.\d+)?(?:ns|us|ms|s|m|h|d)\Z",
    re.IGNORECASE,
)
_ALLOWED_REFERENCE_PREFIXES = frozenset({"sha256", "source"})
_EVIDENCE_GAP_KINDS = frozenset(
    {"missing_deck_identity", "uncovered_card", "unsupported_claim"}
)
_TRANSPORT_FIELD_FRAGMENTS = (
    "captured_at",
    "duration",
    "html",
    "path",
    "retrieved_at",
    "timestamp",
)
_CLAIM_AUTHORITY_TEXT_FIELDS = (
    "claim_confidence",
    "deck_match_scope",
    "freshness_status",
    "source_confidence",
    "source_family",
    "source_lane",
    "source_type",
    "source_visibility",
    "specificity_status",
    "scope",
    "support_status",
    "trust_ceiling",
)
_CLAIM_KIND_SEMANTIC_FIELDS = {
    "archetype": frozenset({"archetype", "stance"}),
    "mulligan_keep": frozenset({"archetype", "stance"}),
    "mulligan_discard": frozenset({"archetype", "stance"}),
    "card_role": frozenset(
        {"intent", "rule_id_suffix", "runtime_block", "runtime_value", "stance"}
    ),
    "targeting_rule": frozenset(
        {
            "intent",
            "rule_id_suffix",
            "runtime_block",
            "runtime_value",
            "stance",
            "target",
        }
    ),
    "combo_sequence": frozenset({"intent", "sequence", "stance"}),
    "gameplan_posture": frozenset({"archetype", "stance"}),
    "hero_power_transform": frozenset(
        {"archetype", "runtime_block", "runtime_value", "stance"}
    ),
    "mechanic_usage": frozenset(
        {
            "mechanic",
            "mechanic_family",
            "rule_id_suffix",
            "runtime_block",
            "runtime_value",
            "stance",
        }
    ),
    "known_bad_pattern": frozenset(
        {"rule_id_suffix", "runtime_block", "runtime_value", "stance"}
    ),
    "tech_slot": frozenset({"archetype", "stance"}),
    "replacement_option": frozenset({"archetype", "stance"}),
    "discover_choice": frozenset({"intent", "option_card_id", "stance"}),
    "choose_one_choice": frozenset({"intent", "option_card_id", "stance"}),
    "globalvalue_numeric_tuning": frozenset(
        {"key", "operation", "stance", "value"}
    ),
}
_AUTHORITATIVE_CLAIM_SEMANTIC_FIELDS = frozenset().union(
    *_CLAIM_KIND_SEMANTIC_FIELDS.values()
)
_RAW_CLAIM_STABLE_FIELDS = (
    frozenset(
        {
            "acquisition_provenance",
            "cards",
            "claim",
            "claim_id",
            "claim_kind",
            "claim_readiness",
            "confidence",
            "conditions",
            "deck_match",
            "evidence_text_short",
            "promotion_eligible",
            "runtime_lowerable",
            "runtime_lowering_reason",
            "semantic_qualifiers",
            "source_identity_signals",
            "source_refs",
        }
    )
    | frozenset(_CLAIM_AUTHORITY_TEXT_FIELDS)
    | _AUTHORITATIVE_CLAIM_SEMANTIC_FIELDS
)
_RAW_CLAIM_COMPATIBILITY_FIELDS = frozenset(
    {"claim_type", "condition", "deck_name", "source", "source_claim_ids"}
)
_RAW_CLAIM_TRANSPORT_FIELDS = frozenset({"retrieved_at", "source_url", "url"})
_RAW_CLAIM_PRESENTATION_FIELDS = frozenset({"evidence_hash", "source_title"})
_RAW_CLAIM_FIELDS = (
    _RAW_CLAIM_STABLE_FIELDS
    | _RAW_CLAIM_COMPATIBILITY_FIELDS
    | _RAW_CLAIM_TRANSPORT_FIELDS
    | _RAW_CLAIM_PRESENTATION_FIELDS
)
_LEGACY_CLAIM_TYPE_BY_KIND = {
    "archetype": "archetype",
    "mulligan_keep": "mulligan_keep",
    "mulligan_discard": "mulligan_discard",
    "card_role": "card_role",
    "targeting_rule": "targeting",
    "combo_sequence": "combo",
    "gameplan_posture": "gameplan_posture",
    "hero_power_transform": "hero_power_transform",
    "mechanic_usage": "mechanic_usage",
    "known_bad_pattern": "bad_pattern",
    "tech_slot": "tech_slot",
    "replacement_option": "replacement_option",
    "discover_choice": "discover_choice",
    "choose_one_choice": "choose_one_choice",
    "globalvalue_numeric_tuning": "globalvalue_numeric_tuning",
}
_LINKED_CARD_REFERENCE_CLAIM_KINDS = frozenset(
    {
        "card_role",
        "hero_power_transform",
        "known_bad_pattern",
        "mechanic_usage",
        "targeting_rule",
    }
)
_MAX_CLAIM_TEXT_CHARS = 4096
_MAX_CONTEXT_TOKEN_CHARS = 256
_MAX_CONTEXT_REFERENCE_CHARS = 2048
_MAX_CONTEXT_PUBLIC_URL_CHARS = 2048


class _ContextScalarKind(Enum):
    PROSE = "prose"
    TOKEN = "token"
    SOURCE_REFERENCE = "source_reference"
    PUBLIC_HTTPS = "public_https"
    CARD_ID = "card_id"
    RAW_SHA256 = "raw_sha256"
    CONTENT_SHA256 = "content_sha256"
    VALIDATED = "validated"


@dataclass(frozen=True, slots=True)
class StarterContext:
    document: StarterDocument
    deck_fingerprint: str
    globalvalues_baseline_sha256: str


def build_starter_context(snapshot: PackageResolutionSnapshot) -> StarterContext:
    """Project one already-resolved package snapshot into stable starter input."""

    if not isinstance(snapshot, PackageResolutionSnapshot):
        raise TypeError("starter_context_snapshot_invalid")
    preconfig = snapshot.general_preconfig.to_value()
    deck_identity = _mapping(preconfig.get("deck_identity"), "deck_identity")
    cards = _card_rows(preconfig)
    identity_projection = _deck_identity(deck_identity, cards=cards)
    deck_fingerprint = str(identity_projection["deck_fingerprint"])
    baseline = _mapping(
        preconfig.get("globalvalues_baseline"),
        "globalvalues_baseline",
    )
    baseline_sha256 = canonical_globalvalues_baseline_sha256(baseline)
    draft = {
        "schema_version": STARTER_SCHEMA_VERSION,
        "deck_identity": identity_projection,
        "cards": cards,
        "deck_shape": _deck_shape(cards),
        "supported_runtime_contract": _runtime_contract(),
        "globalvalues_baseline": _baseline_projection(
            baseline,
            preconfig.get("globalvalues_baseline_receipt"),
            baseline_sha256=baseline_sha256,
        ),
        "source_evidence": _source_evidence(preconfig),
        "existing_claims": _existing_claims(
            preconfig,
            identity=identity_projection,
            cards=cards,
        ),
        "known_safety_boundaries": _known_safety_boundaries(cards),
    }
    document = seal_starter_document(
        draft,
        expected_fields=STARTER_CONTEXT_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )
    _enforce_starter_context_max_bytes(document.canonical_json)
    return StarterContext(
        document=document,
        deck_fingerprint=deck_fingerprint,
        globalvalues_baseline_sha256=baseline_sha256,
    )


def _enforce_starter_context_max_bytes(canonical_json: bytes) -> None:
    if len(canonical_json) > STARTER_CONTEXT_MAX_BYTES:
        raise ValueError("starter_context_maximum_bytes_exceeded")


def _deck_identity(
    deck_identity: Mapping[str, Any],
    *,
    cards: list[dict[str, Any]],
) -> dict[str, Any]:
    deck_name = _nonempty_string(
        deck_identity.get("deck_name"),
        "starter_context_deck_name_invalid",
    )
    deck_code_sha256 = _raw_sha256(
        deck_identity.get("deck_code_hash"),
        "starter_context_deck_code_sha256_invalid",
        allow_prefix=True,
    )
    roster = _identity_roster(deck_identity.get("main_deck"))
    projected_roster = [(str(card["card_id"]), int(card["count"])) for card in cards]
    if sorted(roster) != sorted(projected_roster):
        raise ValueError("starter_context_deck_roster_mismatch")
    card_count_total = _positive_int(
        deck_identity.get("card_count_total"),
        "starter_context_deck_card_count_mismatch",
    )
    if card_count_total != sum(count for _, count in roster):
        raise ValueError("starter_context_deck_card_count_mismatch")
    deck_fingerprint = _raw_sha256(
        deck_identity.get("deck_fingerprint"),
        "starter_context_deck_fingerprint_invalid",
    )
    if deck_fingerprint != stable_deck_fingerprint(roster):
        raise ValueError("starter_context_deck_fingerprint_mismatch")
    result: dict[str, Any] = {
        "card_count_total": card_count_total,
        "deck_code_sha256": deck_code_sha256,
        "deck_fingerprint": deck_fingerprint,
        "deck_name": deck_name,
        "format": _nonempty_string(
            deck_identity.get("format"),
            "starter_context_format_invalid",
        ),
        "hero_dbf_id": _positive_int(
            deck_identity.get("hero_dbf_id"),
            "starter_context_hero_invalid",
        ),
        "unique_card_count": len(roster),
    }
    catalog_rows = [
        row
        for row in load_audited_deck_catalog()
        if row["deck_name"] == deck_name
    ]
    if len(catalog_rows) > 1:
        raise ValueError("starter_context_audited_identity_ambiguous")
    if catalog_rows:
        catalog = catalog_rows[0]
        catalog_code_sha256 = sha256(
            str(catalog["deck_code"]).encode("utf-8")
        ).hexdigest()
        audited_builds = [
            build
            for build in load_packaged_audited_build_inputs().builds
            if build.deck_name == deck_name
        ]
        if (
            catalog_code_sha256 != deck_code_sha256
            or len(audited_builds) != 1
            or audited_builds[0].deck_code_sha256 != deck_code_sha256
            or audited_builds[0].deck_fingerprint != deck_fingerprint
        ):
            raise ValueError("starter_context_audited_identity_mismatch")
        result["hs_id"] = _nonempty_string(
            catalog.get("hs_id"),
            "starter_context_audited_identity_invalid",
        )
        result["hdt_deck_id"] = _nonempty_string(
            catalog.get("hdt_deck_id"),
            "starter_context_audited_identity_invalid",
        )
    return result


def _identity_roster(value: object) -> list[tuple[str, int]]:
    roster: list[tuple[str, int]] = []
    seen: set[str] = set()
    for raw_card in _sequence(value, "deck_main"):
        card = _mapping(raw_card, "deck_main_row")
        card_id = _nonempty_string(
            card.get("card_id"),
            "starter_context_deck_card_id_invalid",
        )
        if card_id in seen:
            raise ValueError("starter_context_deck_roster_duplicate")
        seen.add(card_id)
        roster.append(
            (
                card_id,
                _positive_int(
                    card.get("count"),
                    "starter_context_deck_card_count_invalid",
                ),
            )
        )
    if not roster:
        raise ValueError("starter_context_deck_roster_missing")
    return roster


def _raw_sha256(
    value: object,
    error: str,
    *,
    allow_prefix: bool = False,
) -> str:
    normalized = _nonempty_string(value, error)
    if allow_prefix:
        normalized = normalized.removeprefix("sha256:")
    if _RAW_SHA256_RE.fullmatch(normalized) is None:
        raise ValueError(error)
    return normalized


def _card_rows(preconfig: Mapping[str, Any]) -> list[dict[str, Any]]:
    metadata = _mapping(preconfig.get("card_metadata"), "card_metadata")
    raw_cards = _sequence(metadata.get("cards"), "card_metadata_cards")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_card in raw_cards:
        card = _mapping(raw_card, "card_metadata_row")
        if card.get("deck_zone") != "main":
            continue
        card_id = _nonempty_string(
            card.get("card_id"),
            "starter_context_card_id_invalid",
        )
        if card_id in seen:
            raise ValueError(f"starter_context_duplicate_card_id:{card_id}")
        seen.add(card_id)
        semantic_families = _sorted_strings(
            card.get("semantic_families", []),
            "starter_context_card_mechanics_invalid",
        )
        rows.append(
            {
                "card_id": card_id,
                "count": _positive_int(
                    card.get("count"),
                    "starter_context_card_count_invalid",
                ),
                "cost": _nonnegative_int(
                    card.get("cost"),
                    "starter_context_card_cost_invalid",
                ),
                "dbf_id": _positive_int(
                    card.get("dbf_id"),
                    "starter_context_card_dbf_id_invalid",
                ),
                "linked_entities": _linked_entities(card.get("linked_entities", [])),
                "mechanic_families": semantic_families,
                "mechanics": _sorted_strings(
                    card.get("mechanics", []),
                    "starter_context_card_mechanics_invalid",
                ),
                "name": _nonempty_string(
                    card.get("name"),
                    "starter_context_card_name_invalid",
                ),
                "text": str(card.get("text") or ""),
                "type": _nonempty_string(
                    card.get("type"),
                    "starter_context_card_type_invalid",
                ),
            }
        )
    if not rows:
        raise ValueError("starter_context_cards_missing")
    rows.sort(key=lambda row: row["card_id"])
    return rows


def _linked_entities(value: object) -> list[dict[str, Any]]:
    entities: list[dict[str, Any]] = []
    for raw_entity in _sequence(value, "linked_entities"):
        entity = _mapping(raw_entity, "linked_entity")
        entities.append(
            {
                "card_id": _nonempty_string(
                    entity.get("card_id"),
                    "starter_context_linked_card_id_invalid",
                ),
                "dbf_id": _positive_int(
                    entity.get("dbf_id"),
                    "starter_context_linked_dbf_id_invalid",
                ),
                "link_kind": _nonempty_string(
                    entity.get("link_kind"),
                    "starter_context_link_kind_invalid",
                ),
                "name": _nonempty_string(
                    entity.get("name"),
                    "starter_context_link_name_invalid",
                ),
                "type": _nonempty_string(
                    entity.get("type"),
                    "starter_context_link_type_invalid",
                ),
            }
        )
    return sorted(entities, key=_canonical_bytes)


def _deck_shape(cards: list[dict[str, Any]]) -> dict[str, Any]:
    curve: Counter[str] = Counter()
    card_types: Counter[str] = Counter()
    mechanics: Counter[str] = Counter()
    for card in cards:
        count = int(card["count"])
        curve[str(card["cost"])] += count
        card_types[str(card["type"])] += count
        for mechanic in card["mechanic_families"]:
            mechanics[str(mechanic)] += count
    return {
        "curve_counts": dict(sorted(curve.items())),
        "mechanic_counts": dict(sorted(mechanics.items())),
        "physical_card_count": sum(int(card["count"]) for card in cards),
        "type_counts": dict(sorted(card_types.items())),
        "unique_card_count": len(cards),
    }


def _runtime_contract() -> dict[str, Any]:
    return {
        "card_behavior_blocks": sorted(CARD_BEHAVIOR_BLOCKS),
        "card_value_constraint": _constraint(STARTER_CARD_VALUE_CONSTRAINT),
        "claim_surface_registry": {
            key: asdict(value) for key, value in sorted(CLAIM_SURFACE_REGISTRY.items())
        },
        "combo_value_constraint": _constraint(STARTER_COMBO_VALUE_CONSTRAINT),
        "condition_grammar": {
            "allowed_atom_patterns": sorted(
                pattern.pattern for pattern in ALLOWED_ATOM_PATTERNS
            ),
            "allowed_hero_classes": list(ALLOWED_HERO_CLASSES),
            "report_only_keys": sorted(REPORT_ONLY_CONDITION_KEYS),
            "structured_runtime_keys": sorted(STRUCTURED_RUNTIME_CONDITION_KEYS),
        },
        "globalvalue_constraints": {
            key: _constraint(value)
            for key, value in STARTER_GLOBALVALUE_CONSTRAINTS.items()
        },
        "globalvalue_key_registry": {
            key: asdict(value)
            for key, value in sorted(GLOBALVALUES_KEY_REGISTRY.items())
        },
        "row_schemas": {
            key: sorted(value) for key, value in sorted(RUNTIME_ROW_SCHEMA_KEYS.items())
        },
        "surface_registry": {
            key: asdict(value)
            for key, value in sorted(RUNTIME_SURFACE_REGISTRY.items())
        },
    }


def _constraint(value: RuntimeValueConstraint) -> dict[str, Any]:
    return {
        "copy_baseline_only": value.copy_baseline_only,
        "maximum": None if value.maximum is None else str(value.maximum),
        "minimum": None if value.minimum is None else str(value.minimum),
        "value_type_id": value.value_type_id,
    }


def _baseline_projection(
    baseline: Mapping[str, Any],
    raw_receipt: object,
    *,
    baseline_sha256: str,
) -> dict[str, Any]:
    receipt = _mapping(raw_receipt, "globalvalues_baseline_receipt")
    _validate_globalvalues_baseline(baseline)
    _validate_globalvalues_receipt(receipt, baseline=baseline)
    projected_receipt = {
        key: receipt.get(key)
        for key in ("key_count", "snapshot_date", "snapshot_status", "source")
    }
    return {
        "content_sha256": baseline_sha256,
        "key_count": len(baseline),
        "receipt": projected_receipt,
        "values": dict(baseline),
    }


def _validate_globalvalues_baseline(baseline: Mapping[str, Any]) -> None:
    if (
        len(baseline) != len(GLOBALVALUES_BASELINE_DECISION_KEYS)
        or set(baseline) != set(GLOBALVALUES_BASELINE_DECISION_KEYS)
        or len(baseline) != 38
    ):
        raise ValueError("starter_context_globalvalues_baseline_invalid")
    for key in GLOBALVALUES_BASELINE_DECISION_KEYS:
        value = baseline[key]
        constraint = STARTER_GLOBALVALUE_CONSTRAINTS[key]
        if constraint.copy_baseline_only:
            if not isinstance(value, str) or not value.strip():
                raise ValueError("starter_context_globalvalues_baseline_invalid")
            continue
        if not isinstance(value, Mapping) or set(value) != {"values"}:
            raise ValueError("starter_context_globalvalues_baseline_invalid")
        rows = value.get("values")
        if not isinstance(rows, list) or not rows:
            raise ValueError("starter_context_globalvalues_baseline_invalid")
        for raw_row in rows:
            if not isinstance(raw_row, Mapping) or set(raw_row) != {
                "condition",
                "value",
            }:
                raise ValueError("starter_context_globalvalues_baseline_invalid")
            if classify_runtime_condition(raw_row["condition"]).status != "runtime_safe":
                raise ValueError("starter_context_globalvalues_baseline_invalid")
            try:
                validate_globalvalues_overlay_value(
                    key=key,
                    operation="set",
                    value=raw_row["value"],
                )
            except ValueError as error:
                raise ValueError(
                    "starter_context_globalvalues_baseline_invalid"
                ) from error


def _validate_globalvalues_receipt(
    receipt: Mapping[str, Any],
    *,
    baseline: Mapping[str, Any],
) -> None:
    if set(receipt) != {
        "baseline",
        "key_count",
        "path",
        "sha256",
        "snapshot_date",
        "snapshot_status",
        "source",
    }:
        raise ValueError("starter_context_globalvalues_baseline_invalid")
    key_count = receipt.get("key_count")
    if type(key_count) is not int or key_count != 38 or key_count != len(baseline):
        raise ValueError("starter_context_globalvalues_baseline_invalid")
    receipt_baseline = receipt.get("baseline")
    if not isinstance(receipt_baseline, Mapping) or dict(receipt_baseline) != dict(
        baseline
    ):
        raise ValueError("starter_context_globalvalues_baseline_invalid")
    source = receipt.get("source")
    status = receipt.get("snapshot_status")
    snapshot_date = receipt.get("snapshot_date")
    if source == "bundled_fallback":
        if (
            status != "known_runtime_snapshot"
            or receipt.get("path") is not None
            or receipt.get("sha256") is not None
            or not _canonical_nullable_date(snapshot_date, allow_none=False)
        ):
            raise ValueError("starter_context_globalvalues_baseline_invalid")
        return
    if source == "runtime_default":
        path = receipt.get("path")
        digest = receipt.get("sha256")
        if (
            status != "live_runtime"
            or not isinstance(path, str)
            or not path.strip()
            or not isinstance(digest, str)
            or _RAW_SHA256_RE.fullmatch(digest) is None
            or not _canonical_nullable_date(snapshot_date, allow_none=True)
            or snapshot_date is not None
        ):
            raise ValueError("starter_context_globalvalues_baseline_invalid")
        return
    raise ValueError("starter_context_globalvalues_baseline_invalid")


def _canonical_nullable_date(value: object, *, allow_none: bool) -> bool:
    if value is None:
        return allow_none
    if not isinstance(value, str):
        return False
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return False
    return parsed.isoformat() == value


def _source_evidence(preconfig: Mapping[str, Any]) -> dict[str, Any]:
    claim_bundle = _mapping(
        preconfig.get("guide_claim_bundle"),
        "guide_claim_bundle",
    )
    rows: list[dict[str, Any]] = []
    for raw_row in _sequence(
        claim_bundle.get("source_evidence_index", []),
        "source_evidence_index",
    ):
        row = _mapping(raw_row, "source_evidence_row")
        if not set(row) <= {
            "acquisition_provenance",
            "claim_count",
            "missing_source_keys",
            "retrieved_at",
            "source_family",
            "source_id",
            "source_ref",
            "source_title",
            "source_url",
            "unsupported_claim_count",
        }:
            raise ValueError("starter_context_source_evidence_invalid")
        provenance = _mapping(
            row.get("acquisition_provenance"),
            "source_evidence_provenance",
        )
        projected = {
            "claim_count": _nonnegative_int(
                row.get("claim_count", 0),
                "starter_context_source_evidence_invalid",
            ),
            "missing_source_keys": sorted(
                _context_safe_scalar(
                    value,
                    kind=_ContextScalarKind.TOKEN,
                    error="starter_context_source_evidence_invalid",
                )
                for value in _sequence(
                    row.get("missing_source_keys", []),
                    "source_evidence_missing_source_keys",
                )
            ),
            "provenance": _closed_provenance(
                provenance,
                error="starter_context_source_evidence_invalid",
            ),
            "source_family": _context_safe_scalar(
                row.get("source_family"),
                kind=_ContextScalarKind.TOKEN,
                error="starter_context_source_evidence_invalid",
            ),
            "source_id": _context_safe_scalar(
                row.get("source_id"),
                kind=_ContextScalarKind.TOKEN,
                error="starter_context_source_evidence_invalid",
            ),
            "source_ref": _closed_source_reference(row.get("source_ref")),
            "source_title": _closed_source_scalar(row.get("source_title")),
            "unsupported_claim_count": _nonnegative_int(
                row.get("unsupported_claim_count", 0),
                "starter_context_source_evidence_invalid",
            ),
        }
        source_url = _closed_public_url(row.get("source_url"))
        if source_url is not None:
            projected["source_url"] = source_url
        rows.append(projected)
    return {
        "gaps": _source_gaps(preconfig, claim_bundle),
        "rows": sorted(rows, key=_canonical_bytes),
    }


def _source_gaps(
    preconfig: Mapping[str, Any],
    claim_bundle: Mapping[str, Any],
) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    identity_gaps = _mapping(
        preconfig.get("identity_gap_report", {}),
        "identity_gap_report",
    )
    for field in _sorted_strings(
        identity_gaps.get("missing_identity_fields", []),
        "starter_context_identity_gaps_invalid",
    ):
        gaps.append(
            {
                "gap_kind": _evidence_gap_kind("missing_deck_identity"),
                "value": _context_safe_scalar(
                    field,
                    kind=_ContextScalarKind.TOKEN,
                    error="starter_context_source_evidence_invalid",
                ),
            }
        )
    coverage = _mapping(
        claim_bundle.get("claim_coverage_report", {}),
        "claim_coverage_report",
    )
    coverage_cards = _mapping(
        coverage.get("cards", {}),
        "claim_coverage_cards",
    )
    for card_id, raw_row in sorted(coverage_cards.items()):
        row = _mapping(raw_row, "claim_coverage_card")
        if row.get("coverage_status") == "uncovered_low_confidence":
            gaps.append(
                {
                    "gap_kind": _evidence_gap_kind("uncovered_card"),
                    "value": _context_safe_scalar(
                        card_id,
                        kind=_ContextScalarKind.CARD_ID,
                        error="starter_context_source_evidence_invalid",
                    ),
                }
            )
    for raw_claim in _sequence(
        claim_bundle.get("unsupported_claims", []),
        "unsupported_claims",
    ):
        claim = _mapping(raw_claim, "unsupported_claim")
        claim_id = claim.get("claim_id") or "unknown"
        gaps.append(
            {
                "gap_kind": _evidence_gap_kind("unsupported_claim"),
                "value": _context_safe_scalar(
                    claim_id,
                    kind=_ContextScalarKind.TOKEN,
                    error="starter_context_source_evidence_invalid",
                ),
            }
        )
    return sorted(gaps, key=_canonical_bytes)


def _existing_claims(
    preconfig: Mapping[str, Any],
    *,
    identity: Mapping[str, Any],
    cards: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    claim_bundle = _mapping(
        preconfig.get("guide_claim_bundle"),
        "guide_claim_bundle",
    )
    claims: list[dict[str, Any]] = []
    for raw_claim in _sequence(claim_bundle.get("claims", []), "existing_claims"):
        claim = _mapping(raw_claim, "existing_claim")
        claim_kind = _claim_semantic_text(
            claim.get("claim_kind"),
            allowed_values=CLAIM_SURFACE_REGISTRY,
        )
        _validate_raw_claim_schema(
            claim,
            claim_kind=claim_kind,
            identity=identity,
        )
        conditions = _claim_conditions(claim.get("conditions", {}))
        runtime_lowerable = claim.get("runtime_lowerable", False)
        if type(runtime_lowerable) is not bool:
            raise ValueError("starter_context_claim_semantics_invalid")
        projection = {
            "cards": _claim_card_references(
                claim.get("cards", []),
                claim_kind=claim_kind,
                cards=cards,
            ),
            "claim_id": _context_safe_scalar(
                claim.get("claim_id"),
                kind=_ContextScalarKind.TOKEN,
                error="starter_context_claim_semantics_invalid",
            ),
            "claim_kind": claim_kind,
            "claim": _claim_text(claim.get("claim")),
            "claim_readiness": _claim_semantic_text(
                claim.get("claim_readiness"),
                allowed_values=SUPPORTED_CLAIM_READINESS,
            ),
            "confidence": _claim_semantic_text(claim.get("confidence")),
            "conditions": conditions,
            "evidence_text_short": _claim_evidence_text(
                claim.get("evidence_text_short")
            ),
            "runtime_lowerable": runtime_lowerable,
            "runtime_lowering_reason": _claim_optional_semantic_text(
                claim.get("runtime_lowering_reason")
            ),
            "source_family": _claim_semantic_text(claim.get("source_family")),
            "source_refs": sorted(
                _closed_source_reference(value)
                for value in _sequence(
                    claim.get("source_refs", []),
                    "starter_context_claim_source_refs_invalid",
                )
            ),
            "support_status": _claim_semantic_text(claim.get("support_status")),
        }
        qualifiers = _claim_semantic_qualifiers(claim)
        if qualifiers:
            projection["semantic_qualifiers"] = qualifiers
        for field in _CLAIM_AUTHORITY_TEXT_FIELDS:
            if field in claim:
                projection[field] = _claim_semantic_text(
                    claim[field],
                    allowed_values=(
                        SUPPORTED_SPECIFICITY_STATUSES
                        if field == "specificity_status"
                        else None
                    ),
                )
        if "promotion_eligible" in claim:
            if type(claim["promotion_eligible"]) is not bool:
                raise ValueError("starter_context_claim_semantics_invalid")
            projection["promotion_eligible"] = claim["promotion_eligible"]
        if "acquisition_provenance" in claim:
            projection["acquisition_provenance"] = _closed_provenance(
                claim["acquisition_provenance"],
                error="starter_context_claim_semantics_invalid",
            )
        if "source_identity_signals" in claim:
            projection["source_identity_signals"] = _claim_identity_signals(
                claim["source_identity_signals"]
            )
        if "deck_match" in claim:
            projection["deck_match"] = _claim_deck_match(
                claim["deck_match"],
                identity=identity,
            )
        projection.update(_claim_kind_semantics(claim, claim_kind=claim_kind))
        claims.append(projection)
    return sorted(claims, key=_canonical_bytes)


def _claim_card_references(
    value: object,
    *,
    claim_kind: str,
    cards: list[dict[str, Any]],
) -> list[str]:
    error = "starter_context_claim_cards_invalid"
    references = _sequence(value, "claim_cards")
    try:
        normalized_references = [
            _context_safe_scalar(
                reference,
                kind=_ContextScalarKind.CARD_ID,
                error=error,
            )
            for reference in references
        ]
    except ValueError as validation_error:
        raise ValueError(error) from validation_error
    physical_card_ids = {str(card["card_id"]) for card in cards}
    allowed_card_ids = set(physical_card_ids)
    if claim_kind in _LINKED_CARD_REFERENCE_CLAIM_KINDS:
        allowed_card_ids.update(
            str(entity["card_id"])
            for card in cards
            for entity in card["linked_entities"]
        )
    if not set(normalized_references) <= allowed_card_ids:
        raise ValueError(error)
    return sorted(set(normalized_references))


def _validate_raw_claim_schema(
    claim: Mapping[str, Any],
    *,
    claim_kind: str,
    identity: Mapping[str, Any],
) -> None:
    if not set(claim) <= _RAW_CLAIM_FIELDS:
        raise ValueError("starter_context_claim_schema_invalid")
    expected_claim_type = _LEGACY_CLAIM_TYPE_BY_KIND.get(claim_kind)
    if expected_claim_type is None:
        raise ValueError("starter_context_claim_alias_invalid")
    if "claim_type" in claim and claim.get("claim_type") != expected_claim_type:
        raise ValueError("starter_context_claim_alias_invalid")
    if "condition" in claim and claim.get("condition") != claim.get("conditions"):
        raise ValueError("starter_context_claim_alias_invalid")
    if "deck_name" in claim and claim.get("deck_name") != identity.get("deck_name"):
        raise ValueError("starter_context_claim_alias_invalid")
    if "source" in claim and claim.get("source") != claim.get("source_family"):
        raise ValueError("starter_context_claim_alias_invalid")
    if "source_claim_ids" in claim and claim.get("source_claim_ids") != [
        claim.get("claim_id")
    ]:
        raise ValueError("starter_context_claim_alias_invalid")
    for field in _RAW_CLAIM_TRANSPORT_FIELDS | {"source_title"}:
        if field in claim and not isinstance(claim[field], str):
            raise ValueError("starter_context_claim_schema_invalid")
    if "evidence_hash" in claim and (
        not isinstance(claim["evidence_hash"], str)
        or _EVIDENCE_HASH_RE.fullmatch(claim["evidence_hash"]) is None
    ):
        raise ValueError("starter_context_claim_schema_invalid")


def _claim_conditions(value: object) -> dict[str, Any]:
    _reject_unsafe_semantic_tree(value)
    if isinstance(value, Mapping):
        keys = {str(key) for key in value}
        allowed = (
            set(REPORT_ONLY_CONDITION_KEYS)
            | set(STRUCTURED_RUNTIME_CONDITION_KEYS)
            | {"runtime_condition"}
        )
        if not keys <= allowed:
            raise ValueError("starter_context_claim_semantics_invalid")
    classified = classify_runtime_condition(value)
    if classified.status != "runtime_safe":
        raise ValueError("starter_context_claim_semantics_invalid")
    result: dict[str, Any] = {
        "runtime_condition": _context_safe_scalar(
            classified.value,
            kind=_ContextScalarKind.VALIDATED,
            error="starter_context_claim_semantics_invalid",
        )
    }
    if isinstance(value, Mapping):
        report_only = {
            str(key): _claim_semantic_text(value[key])
            for key in sorted(set(value) & set(REPORT_ONLY_CONDITION_KEYS))
        }
        if report_only:
            result["report_only"] = report_only
    return result


def _claim_semantic_qualifiers(claim: Mapping[str, Any]) -> dict[str, Any]:
    raw = claim.get("semantic_qualifiers", {})
    if not isinstance(raw, Mapping):
        raise ValueError("starter_context_claim_semantics_invalid")
    if not {str(key) for key in raw} <= set(QUALIFIER_KEYS):
        raise ValueError("starter_context_claim_semantics_invalid")
    _reject_unsafe_semantic_tree(raw)
    for value in raw.values():
        if not isinstance(value, (str, list)) or (
            isinstance(value, list)
            and any(not isinstance(item, str) for item in value)
        ):
            raise ValueError("starter_context_claim_semantics_invalid")
    normalized = normalize_semantic_qualifiers(
        {"semantic_qualifiers": dict(raw)}
    )
    result: dict[str, Any] = {}
    for key, value in sorted(normalized.items()):
        if isinstance(value, list):
            result[key] = sorted(
                _claim_semantic_text(item)
                for item in value
            )
        else:
            result[key] = _claim_semantic_text(value)
    return result


def _claim_identity_signals(value: object) -> list[dict[str, str]]:
    signals: list[dict[str, str]] = []
    for raw_signal in _sequence(value, "source_identity_signals"):
        signal = _mapping(raw_signal, "source_identity_signal")
        if set(signal) != {"field", "origin", "value"}:
            raise ValueError("starter_context_claim_semantics_invalid")
        signals.append(
            {
                key: _context_safe_scalar(
                    signal[key],
                    kind=_ContextScalarKind.TOKEN,
                    error="starter_context_claim_semantics_invalid",
                )
                for key in ("field", "origin", "value")
            }
        )
    return sorted(signals, key=_canonical_bytes)


def _claim_deck_match(
    value: object,
    *,
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    error = "starter_context_claim_deck_match_invalid"
    deck_match = _mapping(value, "claim_deck_match")
    deck_match_fields = {"exact_deck_evidence"}
    if not set(deck_match) <= deck_match_fields:
        raise ValueError("starter_context_claim_semantics_invalid")
    if set(deck_match) != deck_match_fields:
        raise ValueError(error)
    evidence = _mapping(
        deck_match.get("exact_deck_evidence"),
        "claim_exact_deck_evidence",
    )
    evidence_fields = {
        "candidate_count",
        "candidate_deck_code_hashes",
        "decoded_candidate_count",
        "matched",
        "matched_deck_fingerprint",
    }
    if not set(evidence) <= evidence_fields:
        raise ValueError("starter_context_claim_semantics_invalid")
    if set(evidence) != evidence_fields:
        raise ValueError(error)
    candidate_count = _nonnegative_int(
        evidence.get("candidate_count"),
        error,
    )
    decoded_count = _nonnegative_int(
        evidence.get("decoded_candidate_count"),
        error,
    )
    if decoded_count > candidate_count or type(evidence.get("matched")) is not bool:
        raise ValueError(error)
    matched = evidence["matched"]
    fingerprint = evidence.get("matched_deck_fingerprint")
    if matched:
        if (
            candidate_count < 1
            or decoded_count < 1
            or fingerprint != identity.get("deck_fingerprint")
        ):
            raise ValueError(error)
        fingerprint = _context_safe_scalar(
            fingerprint,
            kind=_ContextScalarKind.RAW_SHA256,
            error=error,
        )
    elif fingerprint is not None:
        raise ValueError(error)
    try:
        candidate_hashes = [
            _closed_source_reference(item)
            for item in _sequence(
                evidence.get("candidate_deck_code_hashes"),
                "claim_candidate_deck_code_hashes",
            )
        ]
    except ValueError as source_error:
        raise ValueError(error) from source_error
    if (
        len(candidate_hashes) != candidate_count
        or len(set(candidate_hashes)) != len(candidate_hashes)
    ):
        raise ValueError(error)
    target_deck_code_sha256 = _raw_sha256(
        identity.get("deck_code_sha256"),
        error,
    )
    target_deck_code_sha256 = _context_safe_scalar(
        target_deck_code_sha256,
        kind=_ContextScalarKind.RAW_SHA256,
        error=error,
    )
    return {
        "exact_deck_evidence": {
            "candidate_count": candidate_count,
            "candidate_deck_code_hashes": sorted(candidate_hashes),
            "decoded_candidate_count": decoded_count,
            "matched": matched,
            "matched_deck_fingerprint": fingerprint,
        },
        "target_deck_code_sha256": target_deck_code_sha256,
    }


def _claim_kind_semantics(
    claim: Mapping[str, Any],
    *,
    claim_kind: str,
) -> dict[str, Any]:
    allowed = _CLAIM_KIND_SEMANTIC_FIELDS.get(claim_kind)
    if allowed is None or claim_kind not in CLAIM_SURFACE_REGISTRY:
        raise ValueError("starter_context_claim_semantics_invalid")
    present = set(claim) & _AUTHORITATIVE_CLAIM_SEMANTIC_FIELDS
    if not present <= allowed:
        raise ValueError("starter_context_claim_semantics_invalid")
    result: dict[str, Any] = {}
    scalar_token_fields = present - {
        "option_card_id",
        "runtime_value",
        "sequence",
        "value",
    }
    for field in sorted(scalar_token_fields):
        value = _claim_semantic_text(claim[field])
        if field == "runtime_block" and value not in CARD_BEHAVIOR_BLOCKS:
            raise ValueError("starter_context_claim_semantics_invalid")
        if field == "operation" and value not in {"set", "increase", "decrease"}:
            raise ValueError("starter_context_claim_semantics_invalid")
        if field == "key" and value not in STARTER_GLOBALVALUE_CONSTRAINTS:
            raise ValueError("starter_context_claim_semantics_invalid")
        result[field] = value
    if "option_card_id" in present:
        result["option_card_id"] = _context_safe_scalar(
            claim["option_card_id"],
            kind=_ContextScalarKind.CARD_ID,
            error="starter_context_claim_semantics_invalid",
        )
    if "runtime_value" in present:
        result["runtime_value"] = _bounded_decimal_scalar(
            claim["runtime_value"],
            minimum=STARTER_CARD_VALUE_CONSTRAINT.minimum,
            maximum=STARTER_CARD_VALUE_CONSTRAINT.maximum,
        )
    if "value" in present:
        key = result.get("key")
        operation = result.get("operation")
        if not isinstance(key, str) or not isinstance(operation, str):
            raise ValueError("starter_context_claim_semantics_invalid")
        value = _context_safe_scalar(
            claim["value"],
            kind=_ContextScalarKind.VALIDATED,
            error="starter_context_claim_semantics_invalid",
        )
        try:
            validate_globalvalues_overlay_value(
                key=key,
                operation=operation,
                value=value,
            )
        except ValueError as validation_error:
            raise ValueError("starter_context_claim_semantics_invalid") from (
                validation_error
            )
        result["value"] = value
    if "sequence" in present:
        sequence = [
            _context_safe_scalar(
                value,
                kind=_ContextScalarKind.CARD_ID,
                error="starter_context_claim_semantics_invalid",
            )
            for value in _sequence(claim["sequence"], "claim_sequence")
        ]
        if not sequence:
            raise ValueError("starter_context_claim_semantics_invalid")
        result["sequence"] = sequence
    return result


def _claim_text(value: object) -> str:
    return _normalized_claim_prose(
        value,
        error="starter_context_claim_text_invalid",
    )


def _claim_semantic_text(
    value: object,
    *,
    allowed_values: Collection[str] | None = None,
) -> str:
    return _context_safe_scalar(
        value,
        kind=_ContextScalarKind.TOKEN,
        error="starter_context_claim_semantics_invalid",
        allowed_values=allowed_values,
    )


def _closed_source_scalar(value: object) -> str:
    return _context_safe_scalar(
        value,
        kind=_ContextScalarKind.PROSE,
        error="starter_context_source_evidence_invalid",
        strip_presentation=False,
    )


def _closed_source_reference(value: object) -> str:
    return _context_safe_scalar(
        value,
        kind=_ContextScalarKind.SOURCE_REFERENCE,
        error="starter_context_source_evidence_invalid",
    )


def _closed_public_url(value: object) -> str | None:
    if value is None or value == "":
        return None
    return _context_safe_scalar(
        value,
        kind=_ContextScalarKind.PUBLIC_HTTPS,
        error="starter_context_source_evidence_invalid",
    )


def _claim_optional_semantic_text(value: object) -> str:
    if value is None or value == "":
        return _context_safe_scalar(
            "",
            kind=_ContextScalarKind.TOKEN,
            error="starter_context_claim_semantics_invalid",
            allow_empty=True,
        )
    return _claim_semantic_text(value)


def _claim_evidence_text(value: object) -> str:
    return _normalized_claim_prose(
        value,
        error="starter_context_claim_semantics_invalid",
    )


def _normalized_claim_prose(value: object, *, error: str) -> str:
    return _context_safe_scalar(
        value,
        kind=_ContextScalarKind.PROSE,
        error=error,
        strip_presentation=True,
    )


def _context_safe_scalar(
    value: object,
    *,
    kind: _ContextScalarKind,
    error: str,
    allow_empty: bool = False,
    allowed_values: Collection[str] | None = None,
    strip_presentation: bool = False,
) -> str:
    """Validate one emitted context string through its explicit scalar family."""
    if not isinstance(value, str):
        raise ValueError(error)
    maximum = _context_scalar_maximum(kind)
    if len(value) > maximum or _contains_unsafe_control(value):
        raise ValueError(error)
    if kind is _ContextScalarKind.PROSE:
        prepared = (
            _strip_paired_presentation_tags(value, error=error)
            if strip_presentation
            else value
        )
        text = " ".join(prepared.split())
    else:
        if value != value.strip():
            raise ValueError(error)
        text = value
    if not text:
        if allow_empty:
            return ""
        raise ValueError(error)
    if len(text) > maximum or "<" in text or ">" in text:
        raise ValueError(error)
    if kind is _ContextScalarKind.PUBLIC_HTTPS:
        return _validated_public_https(text, error=error)
    if kind is _ContextScalarKind.SOURCE_REFERENCE and text.startswith(
        ("http://", "https://")
    ):
        return _validated_public_https(text, error=error)
    if _contains_absolute_path_token(text) or _canonical_transport_value(text):
        raise ValueError(error)
    if kind in {_ContextScalarKind.PROSE, _ContextScalarKind.VALIDATED}:
        if _URI_SCHEME_TOKEN_RE.search(text) is not None:
            raise ValueError(error)
    elif kind is _ContextScalarKind.TOKEN:
        if _CANONICAL_TOKEN_RE.fullmatch(text) is None:
            raise ValueError(error)
    elif kind is _ContextScalarKind.SOURCE_REFERENCE:
        if _CANONICAL_REFERENCE_RE.fullmatch(text) is None:
            raise ValueError(error)
        if ":" in text and text.partition(":")[0] not in _ALLOWED_REFERENCE_PREFIXES:
            raise ValueError(error)
    elif kind is _ContextScalarKind.CARD_ID:
        if _CARD_ID_RE.fullmatch(text) is None:
            raise ValueError(error)
    elif kind is _ContextScalarKind.RAW_SHA256:
        if _RAW_SHA256_RE.fullmatch(text) is None:
            raise ValueError(error)
    elif kind is _ContextScalarKind.CONTENT_SHA256:
        if _CONTENT_SHA256_RE.fullmatch(text) is None:
            raise ValueError(error)
    if allowed_values is not None and text not in allowed_values:
        raise ValueError(error)
    return text


def _context_scalar_maximum(kind: _ContextScalarKind) -> int:
    if kind is _ContextScalarKind.PROSE:
        return _MAX_CLAIM_TEXT_CHARS
    if kind is _ContextScalarKind.PUBLIC_HTTPS:
        return _MAX_CONTEXT_PUBLIC_URL_CHARS
    if kind is _ContextScalarKind.SOURCE_REFERENCE:
        return _MAX_CONTEXT_REFERENCE_CHARS
    return _MAX_CONTEXT_TOKEN_CHARS


def _contains_unsafe_control(value: str) -> bool:
    return any(
        unicodedata.category(character) in {"Cc", "Cf", "Cs"}
        for character in value
    )


def _contains_absolute_path_token(value: str) -> bool:
    return any(
        pattern.search(value) is not None
        for pattern in (
            _WINDOWS_DRIVE_PATH_TOKEN_RE,
            _UNC_PATH_TOKEN_RE,
            _ROOTED_BACKSLASH_PATH_TOKEN_RE,
            _POSIX_ABSOLUTE_PATH_TOKEN_RE,
            _RELATIVE_TRAVERSAL_PATH_TOKEN_RE,
        )
    )


def _validated_public_https(value: str, *, error: str) -> str:
    parsed = urlsplit(value)
    if (
        not source_ref_is_public_https(value)
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError(error)
    return value


def _closed_provenance(value: object, *, error: str) -> dict[str, str]:
    if not acquisition_provenance_is_canonical(value):
        raise ValueError(error)
    provenance = dict(value)
    return {
        "authority": _context_safe_scalar(
            provenance["authority"],
            kind=_ContextScalarKind.TOKEN,
            error=error,
        ),
        "content_sha256": _context_safe_scalar(
            provenance["content_sha256"],
            kind=_ContextScalarKind.CONTENT_SHA256,
            error=error,
        ),
        "mode": _context_safe_scalar(
            provenance["mode"],
            kind=_ContextScalarKind.TOKEN,
            error=error,
        ),
    }


def _evidence_gap_kind(value: str) -> str:
    return _context_safe_scalar(
        value,
        kind=_ContextScalarKind.TOKEN,
        error="starter_context_source_evidence_invalid",
        allowed_values=_EVIDENCE_GAP_KINDS,
    )


def _bounded_decimal_scalar(
    value: object,
    *,
    minimum: Decimal | None,
    maximum: Decimal | None,
) -> str:
    error = "starter_context_claim_semantics_invalid"
    text = _context_safe_scalar(
        value,
        kind=_ContextScalarKind.VALIDATED,
        error=error,
    )
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError(error) from None
    if (
        not number.is_finite()
        or (minimum is not None and number < minimum)
        or (maximum is not None and number > maximum)
    ):
        raise ValueError(error)
    return text


def _strip_paired_presentation_tags(value: str, *, error: str) -> str:
    parts: list[str] = []
    stack: list[str] = []
    cursor = 0
    for match in _CARD_TEXT_FORMATTING_RE.finditer(value):
        between = value[cursor : match.start()]
        if "<" in between or ">" in between:
            raise ValueError(error)
        parts.append(between)
        closing = bool(match.group(1))
        tag = match.group(2).lower()
        if closing:
            if not stack or stack.pop() != tag:
                raise ValueError(error)
        else:
            stack.append(tag)
        cursor = match.end()
    tail = value[cursor:]
    if "<" in tail or ">" in tail or stack:
        raise ValueError(error)
    parts.append(tail)
    return "".join(parts)


def _canonical_transport_value(value: str) -> bool:
    if _NUMERIC_DURATION_RE.fullmatch(value) is not None:
        return True
    if _CANONICAL_ISO_DATE_RE.fullmatch(value) is not None:
        try:
            return date.fromisoformat(value).isoformat() == value
        except ValueError:
            return False
    if _CANONICAL_ISO_TIMESTAMP_RE.fullmatch(value) is not None:
        try:
            timestamp = value.removesuffix("Z")
            if value.endswith("Z"):
                timestamp += "+00:00"
            datetime.fromisoformat(timestamp)
        except ValueError:
            return False
        return True
    if _CANONICAL_ISO_TIME_RE.fullmatch(value) is not None:
        try:
            time_value = value.removesuffix("Z")
            if value.endswith("Z"):
                time_value += "+00:00"
            datetime_time.fromisoformat(time_value)
        except ValueError:
            return False
        return True
    return _CANONICAL_ISO_DURATION_RE.fullmatch(value) is not None


def _reject_unsafe_semantic_tree(value: object) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized_key = str(key).strip().lower()
            if any(fragment in normalized_key for fragment in _TRANSPORT_FIELD_FRAGMENTS):
                raise ValueError("starter_context_claim_semantics_invalid")
            _reject_unsafe_semantic_tree(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _reject_unsafe_semantic_tree(item)
        return
    if isinstance(value, str):
        _context_safe_scalar(
            value,
            kind=_ContextScalarKind.VALIDATED,
            error="starter_context_claim_semantics_invalid",
        )


def _known_safety_boundaries(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    boundaries: list[dict[str, Any]] = [
        {
            "boundary_id": "starter_context_read_only",
            "restrictions": [
                "no_strategy_generation",
                "no_runtime_write_authority",
            ],
        }
    ]
    darkbishop = next(
        (card for card in cards if card["card_id"] == "SW_448"),
        None,
    )
    if darkbishop is not None and any(
        entity["card_id"] == "EX1_625t"
        and entity["link_kind"] == "hero_power_transform"
        for entity in darkbishop["linked_entities"]
    ):
        boundaries.append(
            {
                "boundary_id": "darkbishop_transformed_hero_power_owner",
                "behavior_block": "BeforeUseHeroPowerBonus",
                "linked_card_id": "EX1_625t",
                "restrictions": [
                    "do_not_infer_mulligan_keep",
                    "do_not_target_source_card_for_transformed_hero_power",
                ],
                "source_card_id": "SW_448",
            }
        )
    return sorted(boundaries, key=_canonical_bytes)


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"starter_context_{label}_invalid")
    return dict(value)


def _sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"starter_context_{label}_invalid")
    return list(value)


def _sorted_strings(value: object, label: str) -> list[str]:
    rows = _sequence(value, label)
    if any(not isinstance(item, str) or not item for item in rows):
        raise ValueError(f"starter_context_{label}_invalid")
    return sorted(set(rows))


def _nonempty_string(value: object, error: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(error)
    return value


def _positive_int(value: object, error: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(error)
    return value


def _nonnegative_int(value: object, error: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(error)
    return value


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


__all__ = ("StarterContext", "build_starter_context")
