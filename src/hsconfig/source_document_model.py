from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping

from hsconfig.role_tokens import (
    START_OF_GAME_NON_HAND_EFFECT_ROLES,
    card_role_tokens,
    has_explicit_opening_hand_mulligan_intent,
)
from hsconfig.source_exact_evidence import canonical_exact_deck_evidence
from hsconfig.source_semantic_qualifiers import has_qualifier, qualifier_values

SUPPORTED_ATOMIC_CLAIM_KINDS = frozenset(
    {
        "archetype",
        "mulligan_keep",
        "mulligan_discard",
        "card_role",
        "targeting_rule",
        "combo_sequence",
        "gameplan_posture",
        "hero_power_transform",
        "mechanic_usage",
        "known_bad_pattern",
        "tech_slot",
        "replacement_option",
        "discover_choice",
        "choose_one_choice",
        "globalvalue_numeric_tuning",
    }
)

REQUIRED_SOURCE_KEYS = ("source_url", "source_title", "source_family", "retrieved_at")
REQUIRED_CLAIM_KEYS = ("claim_kind", "evidence_text_short", "source_confidence")

SUPPORTED_CLAIM_READINESS = frozenset(
    {
        "guide_backed",
        "source_backed_static_semantics",
        "archetype_inferred",
        "explicit_low_confidence",
        "generic_low_confidence",
        "contract_gap",
    }
)

SUPPORTED_SPECIFICITY_STATUSES = frozenset(
    {
        "deck_scoped",
        "card_specific",
        "multi_card_specific",
        "not_card_specific",
    }
)

RUNTIME_LOWERABLE_CLAIM_READINESS = frozenset(
    {
        "guide_backed",
        "source_backed_static_semantics",
    }
)
RUNTIME_BLOCKED_CLAIM_READINESS = (
    SUPPORTED_CLAIM_READINESS - RUNTIME_LOWERABLE_CLAIM_READINESS
)
RUNTIME_BLOCKED_CONFIDENCE_LABELS = frozenset(
    {
        "low",
        "report_only",
        "explicit_low_confidence",
        "generic_low_confidence",
        "contract_gap",
    }
)

EXACT_LEGACY_RUNTIME_CLAIM_TYPES = frozenset(
    {
        "mulligan_keep",
        "mulligan_discard",
        "targeting_rule",
        "combo_sequence",
        "hero_power_transform",
        "mechanic_usage",
        "known_bad_pattern",
        "discover_choice",
        "choose_one_choice",
    }
)

EXACT_LEGACY_RUNTIME_CLAIM_TYPE_ALIASES = {
    "combo": "combo_sequence",
    "bad_pattern": "known_bad_pattern",
    "mulligan_throw": "mulligan_discard",
}

GLOBALVALUES_RUNTIME_EVIDENCE_CLAIM_KINDS = frozenset({"globalvalue_numeric_tuning"})
MULLIGAN_SURFACE_CLAIM_KINDS = frozenset({"mulligan_keep", "mulligan_discard"})
GLOBALVALUES_SURFACE_CLAIM_KINDS = frozenset({"gameplan_posture"})
COMBO_SURFACE_CLAIM_KINDS = frozenset({"combo_sequence"})
CARDID_SURFACE_CLAIM_KINDS = frozenset(
    {
        "card_role",
        "targeting_rule",
        "hero_power_transform",
        "mechanic_usage",
        "known_bad_pattern",
        "discover_choice",
        "choose_one_choice",
    }
)

DECK_EVALUATION_NON_HAND_EFFECTS = frozenset(
    {
        "highlander",
        "odd",
        "even",
        "deck_size",
        "start_in_deck",
        "all_shadow_spells",
    }
)

GENERATED_NON_OPENING_HAND_SCOPES = frozenset(
    {
        "generated",
        "random_pool",
        "discovered",
        "copied",
        "transformed",
        "shuffled",
    }
)
STATIC_SEMANTIC_SOURCE_FAMILIES = frozenset(
    {
        "card_text",
        "metadata",
        "hearthstonejson",
        "static_semantics",
        "hearthstonejson_static_semantics",
    }
)
PUBLIC_GUIDE_SOURCE_FAMILIES = frozenset(
    {
        "guide",
        "guide_fixture",
        "mulligan_guide",
        "matchup_guide",
        "public_guide",
        "community_guide",
    }
)
PUBLIC_GUIDE_IDENTITY_FIELDS = (
    "source_family",
    "source_type",
    "provenance",
    "source",
    "source_type_family",
)
STATISTICAL_ENRICHMENT_SOURCE_TYPES = frozenset(
    {
        "replay_stat_aggregate",
        "hs" + "replay",
        "hsguru",
    }
)
TRUE_TEXT_VALUES = frozenset({"1", "true", "yes", "y", "on"})
FALSE_TEXT_VALUES = frozenset({"", "0", "false", "no", "n", "off"})


@dataclass(frozen=True)
class SurfaceGateDecision:
    allowed: bool
    reason: str
    claim_kind: str
    surface: str


def normalized_claim_kind(claim: Mapping[str, Any]) -> str:
    """Return the semantic claim kind from explicit fields or exact legacy aliases."""
    explicit = str(claim.get("claim_kind", "")).strip().lower()
    if explicit:
        return explicit

    legacy = str(claim.get("claim_type", "")).strip().lower()
    if legacy in EXACT_LEGACY_RUNTIME_CLAIM_TYPE_ALIASES:
        return EXACT_LEGACY_RUNTIME_CLAIM_TYPE_ALIASES[legacy]
    if legacy in EXACT_LEGACY_RUNTIME_CLAIM_TYPES:
        return legacy

    return ""


def strict_claim_kind(claim: Mapping[str, Any]) -> str:
    """Return the stored modern claim kind after lifecycle ingestion."""
    value = claim.get("claim_kind")
    if isinstance(value, str) and value in SUPPORTED_ATOMIC_CLAIM_KINDS:
        return value
    return ""


def runtime_claim_kind(claim: Mapping[str, Any]) -> str:
    """Backward-compatible alias for normalized_claim_kind()."""
    return normalized_claim_kind(claim)


def qualify_source_claim(claim: Mapping[str, Any]) -> dict[str, Any]:
    """Return source-quality metadata for strong promotion diagnostics."""
    normalized = dict(claim)
    claim_kind = normalized_claim_kind(normalized)
    source_type = _quality_source_type(normalized)
    normalized["claim_kind"] = claim_kind
    normalized["source_lane"] = _source_lane(source_type, normalized)
    normalized["deck_match_scope"] = str(normalized.get("deck_match_scope") or "unknown")
    normalized["opening_hand_relevant"] = _opening_hand_relevant(claim_kind, normalized)
    normalized["runtime_lowering"] = _runtime_lowering(claim_kind)
    normalized["promotion_eligible"] = _promotion_eligible(source_type, normalized)
    normalized["strong_promotion_eligible"] = _strong_promotion_eligible(
        source_type,
        normalized,
    )
    normalized["strong_static_claim"] = bool(
        normalized["promotion_eligible"]
        and claim_kind
        in {
            "hero_power_transform",
            "card_role",
            "gameplan_posture",
            "targeting_rule",
            "combo_sequence",
            "mulligan_keep",
            "mulligan_discard",
        }
    )
    return normalized


def _quality_source_type(claim: Mapping[str, Any]) -> str:
    source_type = _normalized_text(claim.get("source_type") or claim.get("provenance"))
    if source_type:
        return source_type
    source_family = _normalized_text(claim.get("source_family"))
    if source_family in STATIC_SEMANTIC_SOURCE_FAMILIES:
        return "official_card_data"
    if source_family in PUBLIC_GUIDE_SOURCE_FAMILIES:
        return "public_guide"
    return ""


def _source_lane(source_type: str, claim: Mapping[str, Any]) -> str:
    if source_type == "policy_backed_autonomous_mulligan":
        return "policy_fallback"
    if source_type in {"official_card_data", "hearthstonejson", "blizzard_card_library"}:
        return "official_static_semantics"
    if source_type in {"community_guide", "public_guide"}:
        explicit_lane = str(claim.get("source_lane") or "")
        if explicit_lane:
            return explicit_lane
        if str(claim.get("deck_match_scope") or "").lower() == "exact_deck_matched":
            return "deck_matched_public_guide"
        if str(claim.get("deck_match_scope") or "").lower() == "archetype_matched":
            return "archetype_matched_public_guide"
        return "unknown"
    if source_type in STATISTICAL_ENRICHMENT_SOURCE_TYPES:
        return "statistical_enrichment"
    return str(claim.get("source_lane") or "unknown")


def _opening_hand_relevant(claim_kind: str, claim: Mapping[str, Any]) -> bool:
    if claim_kind in {"mulligan_keep", "mulligan_discard"}:
        return True
    if "opening_hand_relevant" in claim:
        return _bool_value(claim["opening_hand_relevant"])
    return False


def _runtime_lowering(claim_kind: str) -> str:
    if claim_kind in {"mulligan_keep", "mulligan_discard"}:
        return "mulligan"
    if claim_kind == "combo_sequence":
        return "combo"
    if claim_kind in {"targeting_rule", "hero_power_transform", "card_role"}:
        return "cardid_or_contract_only"
    if claim_kind == "gameplan_posture":
        return "globalvalues_or_contract_only"
    return "contract_only"


def _promotion_eligible(source_type: str, claim: Mapping[str, Any]) -> bool:
    if "promotion_eligible" in claim and not _bool_value(claim["promotion_eligible"]):
        return False
    if source_type == "policy_backed_autonomous_mulligan":
        return False
    if source_type in {"default_runtime", "generated_default"}:
        return False
    if _bool_value(claim.get("source_blocked")):
        return False
    if _normalized_text(claim.get("source_visibility")) == "snippet_only":
        return False
    return source_type in {
        "official_card_data",
        "hearthstonejson",
        "blizzard_card_library",
        "community_guide",
        "public_guide",
    }


def _strong_promotion_eligible(source_type: str, claim: Mapping[str, Any]) -> bool:
    if not _promotion_eligible(source_type, claim):
        return False
    source_record_strength = _normalized_text(claim.get("source_record_strength"))
    if source_record_strength and source_record_strength != "candidate_strong":
        return False
    if source_type not in {"community_guide", "public_guide"}:
        return False
    freshness_status = _normalized_text(claim.get("freshness_status"))
    if freshness_status and freshness_status != "current":
        return False
    if _normalized_text(claim.get("source_visibility")) != "full_text":
        return False
    if _normalized_text(claim.get("source_lane")) != "deck_matched_public_guide":
        return False
    return _normalized_text(claim.get("deck_match_scope")) == "exact_deck_matched"


def _normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def is_public_guide_claim(claim: Mapping[str, Any]) -> bool:
    """Return whether any accepted provenance representation identifies a public guide."""
    return any(
        _normalized_text(claim.get(field)) in PUBLIC_GUIDE_SOURCE_FAMILIES
        for field in PUBLIC_GUIDE_IDENTITY_FIELDS
    )


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in TRUE_TEXT_VALUES:
            return True
        if normalized in FALSE_TEXT_VALUES:
            return False
    return bool(value)


def claim_can_lower_to_runtime(claim: dict) -> bool:
    """Return whether a source claim is allowed to affect generated runtime config."""
    trust_ceiling = str(claim.get("trust_ceiling", "")).strip().lower()
    if trust_ceiling == "report_only":
        return False

    readiness = str(claim.get("claim_readiness", "")).strip().lower()
    if readiness:
        return readiness in RUNTIME_LOWERABLE_CLAIM_READINESS

    confidence = str(
        claim.get(
            "confidence",
            claim.get("claim_confidence", claim.get("source_confidence", "")),
        )
    ).strip().lower()
    return (
        confidence not in RUNTIME_BLOCKED_CLAIM_READINESS
        and confidence not in RUNTIME_BLOCKED_CONFIDENCE_LABELS
    )


def surface_gate_decision(
    claim: Mapping[str, Any],
    surface: str,
    context: Mapping[str, Any] | None = None,
) -> SurfaceGateDecision:
    normalized_surface = surface.strip().lower()
    if normalized_surface == "mulligan":
        return can_lower_to_mulligan(
            claim,
            card_roles=(context or {}).get("card_roles"),
            deck_identity=(context or {}).get("deck_identity"),
            verified_source_receipts=(context or {}).get(
                "verified_source_receipts"
            ),
        )
    if normalized_surface == "globalvalues":
        return can_lower_to_globalvalues(
            claim,
            deck_identity=(context or {}).get("deck_identity"),
            verified_source_receipts=(context or {}).get(
                "verified_source_receipts"
            ),
        )
    if normalized_surface == "combo":
        return can_lower_to_combo(claim)
    if normalized_surface == "cardid":
        return can_lower_to_cardid(claim)
    if normalized_surface == "card_behavior":
        claim_kind = normalized_claim_kind(claim)
        if claim_kind in {"discover_choice", "choose_one_choice"} and not _has_exact_option_identity(
            claim,
            (context or {}).get("identity_links"),
        ):
            return SurfaceGateDecision(
                False,
                "requires_exact_option_identity",
                claim_kind,
                normalized_surface,
            )
        return can_lower_to_cardid(claim)
    return SurfaceGateDecision(
        False, "unknown_surface", normalized_claim_kind(claim), normalized_surface
    )


def can_lower_to_mulligan(
    claim: Mapping[str, Any],
    *,
    card_roles: Mapping[str, Any] | None = None,
    deck_identity: Mapping[str, Any] | None = None,
    verified_source_receipts: Iterable[Mapping[str, Any]] | None = None,
) -> SurfaceGateDecision:
    claim_kind = normalized_claim_kind(claim)
    if claim_kind not in MULLIGAN_SURFACE_CLAIM_KINDS:
        return SurfaceGateDecision(False, "claim_kind_not_mulligan_surface", claim_kind, "mulligan")
    if not claim_can_lower_to_runtime(dict(claim)):
        return SurfaceGateDecision(False, "claim_not_runtime_lowerable", claim_kind, "mulligan")
    cards = _claim_cards_from_mapping(claim)
    start_of_game_non_hand_effect = (
        claim_kind == "mulligan_keep"
        and _contains_start_of_game_non_hand_effect(
            cards,
            card_roles or {},
            claim,
        )
    )
    if not _is_canonical_public_guide_source(claim):
        if start_of_game_non_hand_effect:
            return SurfaceGateDecision(
                False,
                "start_of_game_effect_does_not_require_opening_hand",
                claim_kind,
                "mulligan",
            )
        return SurfaceGateDecision(
            False,
            "mulligan_requires_public_guide_source",
            claim_kind,
            "mulligan",
        )
    if _normalized_text(claim.get("deck_match_scope")) != "exact_deck_matched":
        return SurfaceGateDecision(
            False,
            "mulligan_requires_exact_deck_match",
            claim_kind,
            "mulligan",
        )
    if not _bool_value(claim.get("promotion_eligible")):
        return SurfaceGateDecision(
            False,
            "mulligan_requires_promotion_eligible_source",
            claim_kind,
            "mulligan",
        )
    if _normalized_text(claim.get("source_visibility")) != "full_text":
        return SurfaceGateDecision(
            False,
            "mulligan_requires_full_text_source",
            claim_kind,
            "mulligan",
        )
    if _normalized_text(claim.get("source_lane")) != "deck_matched_public_guide":
        return SurfaceGateDecision(
            False,
            "mulligan_requires_deck_matched_public_guide_lane",
            claim_kind,
            "mulligan",
        )
    target_fingerprint = _normalized_text(
        (deck_identity or {}).get("deck_fingerprint")
    )
    if not target_fingerprint:
        return SurfaceGateDecision(
            False,
            "mulligan_requires_target_deck_fingerprint",
            claim_kind,
            "mulligan",
        )
    deck_match = claim.get("deck_match")
    exact_evidence = (
        deck_match.get("exact_deck_evidence")
        if isinstance(deck_match, Mapping)
        else None
    )
    evidence_fingerprint = (
        _normalized_text(exact_evidence.get("matched_deck_fingerprint"))
        if isinstance(exact_evidence, Mapping)
        else ""
    )
    if (
        not isinstance(exact_evidence, Mapping)
        or exact_evidence.get("matched") is not True
        or not evidence_fingerprint
    ):
        return SurfaceGateDecision(
            False,
            "mulligan_requires_verified_exact_deck_evidence",
            claim_kind,
            "mulligan",
        )
    if evidence_fingerprint != target_fingerprint:
        return SurfaceGateDecision(
            False,
            "mulligan_exact_deck_fingerprint_mismatch",
            claim_kind,
            "mulligan",
        )
    if not canonical_exact_deck_evidence(
        exact_evidence,
        target_fingerprint=target_fingerprint,
    ):
        return SurfaceGateDecision(
            False,
            "mulligan_requires_complete_exact_deck_evidence",
            claim_kind,
            "mulligan",
        )
    if not _has_verified_source_receipt(
        claim,
        target_fingerprint=target_fingerprint,
        verified_source_receipts=verified_source_receipts,
    ):
        return SurfaceGateDecision(
            False,
            "mulligan_requires_verified_source_receipt",
            claim_kind,
            "mulligan",
        )
    if start_of_game_non_hand_effect:
        return SurfaceGateDecision(
            False,
            "start_of_game_effect_does_not_require_opening_hand",
            claim_kind,
            "mulligan",
        )
    return SurfaceGateDecision(True, "allowed", claim_kind, "mulligan")


def can_lower_to_globalvalues(
    claim: Mapping[str, Any],
    *,
    deck_identity: Mapping[str, Any] | None = None,
    verified_source_receipts: Iterable[Mapping[str, Any]] | None = None,
) -> SurfaceGateDecision:
    claim_kind = normalized_claim_kind(claim)
    if claim_kind in GLOBALVALUES_RUNTIME_EVIDENCE_CLAIM_KINDS:
        return SurfaceGateDecision(False, "requires_runtime_evidence", claim_kind, "globalvalues")
    if claim_kind not in GLOBALVALUES_SURFACE_CLAIM_KINDS:
        return SurfaceGateDecision(
            False, "claim_kind_not_globalvalues_surface", claim_kind, "globalvalues"
        )
    if not claim_can_lower_to_runtime(dict(claim)):
        return SurfaceGateDecision(False, "claim_not_runtime_lowerable", claim_kind, "globalvalues")
    if not _is_canonical_public_guide_source(claim):
        return SurfaceGateDecision(
            False,
            "globalvalues_requires_public_guide_source",
            claim_kind,
            "globalvalues",
        )
    if _normalized_text(claim.get("deck_match_scope")) != "exact_deck_matched":
        return SurfaceGateDecision(
            False,
            "globalvalues_requires_exact_deck_match",
            claim_kind,
            "globalvalues",
        )
    target_fingerprint = _normalized_text(
        (deck_identity or {}).get("deck_fingerprint")
    )
    if not target_fingerprint:
        return SurfaceGateDecision(
            False,
            "globalvalues_requires_target_deck_fingerprint",
            claim_kind,
            "globalvalues",
        )
    deck_match = claim.get("deck_match", {})
    exact_evidence = (
        deck_match.get("exact_deck_evidence", {})
        if isinstance(deck_match, Mapping)
        else {}
    )
    evidence_fingerprint = (
        _normalized_text(exact_evidence.get("matched_deck_fingerprint"))
        if isinstance(exact_evidence, Mapping)
        else ""
    )
    if (
        not isinstance(exact_evidence, Mapping)
        or exact_evidence.get("matched") is not True
        or not evidence_fingerprint
    ):
        return SurfaceGateDecision(
            False,
            "globalvalues_requires_verified_exact_deck_evidence",
            claim_kind,
            "globalvalues",
        )
    if evidence_fingerprint != target_fingerprint:
        return SurfaceGateDecision(
            False,
            "globalvalues_exact_deck_fingerprint_mismatch",
            claim_kind,
            "globalvalues",
        )
    if not _has_verified_source_receipt(
        claim,
        target_fingerprint=target_fingerprint,
        verified_source_receipts=verified_source_receipts,
    ):
        return SurfaceGateDecision(
            False,
            "globalvalues_requires_verified_source_receipt",
            claim_kind,
            "globalvalues",
        )
    if not _bool_value(claim.get("promotion_eligible")):
        return SurfaceGateDecision(
            False,
            "globalvalues_requires_promotion_eligible_source",
            claim_kind,
            "globalvalues",
        )
    if _normalized_text(claim.get("source_visibility")) != "full_text":
        return SurfaceGateDecision(
            False,
            "globalvalues_requires_full_text_source",
            claim_kind,
            "globalvalues",
        )
    if _normalized_text(claim.get("source_lane")) != "deck_matched_public_guide":
        return SurfaceGateDecision(
            False,
            "globalvalues_requires_deck_matched_public_guide_lane",
            claim_kind,
            "globalvalues",
        )
    return SurfaceGateDecision(True, "allowed", claim_kind, "globalvalues")


def _is_canonical_public_guide_source(claim: Mapping[str, Any]) -> bool:
    identities = [
        _normalized_text(claim.get(field))
        for field in PUBLIC_GUIDE_IDENTITY_FIELDS
        if _normalized_text(claim.get(field))
    ]
    signals = claim.get("source_identity_signals", ())
    if isinstance(signals, Iterable) and not isinstance(
        signals,
        (str, bytes, Mapping),
    ):
        for signal in signals:
            if not isinstance(signal, Mapping):
                continue
            if _normalized_text(signal.get("field")) not in PUBLIC_GUIDE_IDENTITY_FIELDS:
                continue
            value = _normalized_text(signal.get("value"))
            if value:
                identities.append(value)
    return bool(identities) and all(
        identity in PUBLIC_GUIDE_SOURCE_FAMILIES for identity in identities
    )


def source_claim_signature(claim: Mapping[str, Any]) -> str:
    payload = {
        str(key): value
        for key, value in claim.items()
        if not str(key).startswith("_") and key != "claim_type"
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"


def globalvalues_claim_signature(claim: Mapping[str, Any]) -> str:
    """Compatibility alias for the canonical source claim signature."""
    return source_claim_signature(claim)


def _has_verified_source_receipt(
    claim: Mapping[str, Any],
    *,
    target_fingerprint: str,
    verified_source_receipts: Iterable[Mapping[str, Any]] | None,
) -> bool:
    signature = source_claim_signature(claim)
    claim_id = str(claim.get("claim_id", "")).strip()
    for receipt in verified_source_receipts or ():
        if not isinstance(receipt, Mapping):
            continue
        if receipt.get("receipt_kind") != "canonical_exact_deck_source_document":
            continue
        if _normalized_text(receipt.get("matched_deck_fingerprint")) != target_fingerprint:
            continue
        if str(receipt.get("claim_id", "")).strip() != claim_id:
            continue
        if str(receipt.get("claim_signature", "")).strip() != signature:
            continue
        return True
    return False


def _is_globalvalues_public_guide_source(claim: Mapping[str, Any]) -> bool:
    """Compatibility alias for callers using the earlier surface-specific name."""
    return _is_canonical_public_guide_source(claim)


def _has_verified_globalvalues_source_receipt(
    claim: Mapping[str, Any],
    *,
    target_fingerprint: str,
    verified_source_receipts: Iterable[Mapping[str, Any]] | None,
) -> bool:
    """Compatibility alias for callers using the earlier surface-specific name."""
    return _has_verified_source_receipt(
        claim,
        target_fingerprint=target_fingerprint,
        verified_source_receipts=verified_source_receipts,
    )


def can_lower_to_combo(claim: Mapping[str, Any]) -> SurfaceGateDecision:
    claim_kind = normalized_claim_kind(claim)
    if claim_kind not in COMBO_SURFACE_CLAIM_KINDS:
        return SurfaceGateDecision(False, "claim_kind_not_combo_surface", claim_kind, "combo")
    if not claim_can_lower_to_runtime(dict(claim)):
        return SurfaceGateDecision(False, "claim_not_runtime_lowerable", claim_kind, "combo")
    return SurfaceGateDecision(True, "allowed", claim_kind, "combo")


def can_lower_to_cardid(claim: Mapping[str, Any]) -> SurfaceGateDecision:
    claim_kind = normalized_claim_kind(claim)
    if claim_kind not in CARDID_SURFACE_CLAIM_KINDS:
        return SurfaceGateDecision(False, "claim_kind_not_cardid_surface", claim_kind, "cardid")
    if not claim_can_lower_to_runtime(dict(claim)):
        return SurfaceGateDecision(False, "claim_not_runtime_lowerable", claim_kind, "cardid")
    return SurfaceGateDecision(True, "allowed", claim_kind, "cardid")


def _claim_cards_from_mapping(claim: Mapping[str, Any]) -> list[str]:
    cards = claim.get("cards", [])
    if isinstance(cards, str):
        cards = [cards]
    return [str(card) for card in cards if str(card)]


def _has_exact_option_identity(
    claim: Mapping[str, Any], identity_links: Mapping[str, Any] | None
) -> bool:
    """Return whether every choice source card links to the requested concrete option."""
    option_card_id = next(
        (
            str(claim[key])
            for key in ("option_card_id", "option_card", "choice_card_id", "choice_card")
            if claim.get(key)
        ),
        None,
    )
    cards = _claim_cards_from_mapping(claim)
    if not option_card_id or not cards:
        return False

    links_by_card = identity_links or {}
    return all(
        option_card_id in _linked_identity_card_ids(links_by_card.get(card_id, []))
        for card_id in cards
    )


def _linked_identity_card_ids(value: Any) -> set[str]:
    if isinstance(value, Mapping):
        if isinstance(value.get("links"), list):
            value = value["links"]
        elif value.get("card_id"):
            return {str(value["card_id"])}
        else:
            return set()
    if not isinstance(value, list):
        return set()
    return {
        str(row["card_id"])
        for row in value
        if isinstance(row, Mapping) and row.get("card_id")
    } | {row for row in value if isinstance(row, str)}


def _contains_start_of_game_non_hand_effect(
    cards: list[str],
    card_roles: Mapping[str, Any],
    claim: Mapping[str, Any] | None = None,
) -> bool:
    for card_id in cards:
        roles = _roles_for_card(card_id, card_roles, claim)
        if "start_of_game" not in roles:
            continue
        has_opening_hand_intent = _has_explicit_opening_hand_mulligan_evidence(
            claim,
            roles=roles,
        )
        if roles & START_OF_GAME_NON_HAND_EFFECT_ROLES:
            return not has_opening_hand_intent
        if "mulligan_anchor" not in roles and not has_opening_hand_intent:
            return True
    deck_evaluation_effect = bool(
        qualifier_values(claim or {}, "deck_evaluation").intersection(
            DECK_EVALUATION_NON_HAND_EFFECTS
        )
    )
    generated_effect = bool(
        qualifier_values(claim or {}, "generation_scope").intersection(
            GENERATED_NON_OPENING_HAND_SCOPES
        )
    )
    qualifier_start_effect = (
        has_qualifier(claim or {}, "timing", "start_of_game")
        or has_qualifier(claim or {}, "zone_scope", "deck")
        or has_qualifier(claim or {}, "state_requirements", "hero_power_transform")
        or has_qualifier(claim or {}, "state_requirements", "deckbuilding_effect")
        or deck_evaluation_effect
        or generated_effect
    )
    if qualifier_start_effect and not _has_explicit_opening_hand_mulligan_evidence(
        claim,
        roles={"start_of_game"},
    ):
        return True
    return False


def _has_explicit_opening_hand_mulligan_evidence(
    claim: Mapping[str, Any] | None,
    *,
    roles: Iterable[str] = (),
) -> bool:
    return has_explicit_opening_hand_mulligan_intent(
        claim,
        roles=roles,
    ) or (
        isinstance(claim, Mapping)
        and has_qualifier(claim, "timing", "mulligan")
    )


def _roles_for_card(
    card_id: str,
    card_roles: Mapping[str, Any],
    claim: Mapping[str, Any] | None,
) -> set[str]:
    role_row = card_roles.get(str(card_id), {})
    if not isinstance(role_row, Mapping):
        role_row = {}
    return card_role_tokens(role_row, claim)
