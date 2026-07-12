from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

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
START_OF_GAME_NON_HAND_EFFECT_ROLES = frozenset(
    {
        "deck_state_modifier",
        "deckbuilding_modifier",
        "deck_size_modifier",
        "even_odd_modifier",
        "highlander_modifier",
        "hero_power_transform",
        "passive_start_effect",
        "start_in_deck_requirement",
        "start_of_game_modifier",
    }
)
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


def runtime_claim_kind(claim: Mapping[str, Any]) -> str:
    """Backward-compatible alias for normalized_claim_kind()."""
    return normalized_claim_kind(claim)


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
        return can_lower_to_mulligan(claim, card_roles=(context or {}).get("card_roles"))
    if normalized_surface == "globalvalues":
        return can_lower_to_globalvalues(claim)
    if normalized_surface == "combo":
        return can_lower_to_combo(claim)
    if normalized_surface == "cardid":
        return can_lower_to_cardid(claim)
    return SurfaceGateDecision(
        False, "unknown_surface", normalized_claim_kind(claim), normalized_surface
    )


def can_lower_to_mulligan(
    claim: Mapping[str, Any],
    *,
    card_roles: Mapping[str, Any] | None = None,
) -> SurfaceGateDecision:
    claim_kind = normalized_claim_kind(claim)
    if claim_kind not in MULLIGAN_SURFACE_CLAIM_KINDS:
        return SurfaceGateDecision(False, "claim_kind_not_mulligan_surface", claim_kind, "mulligan")
    if not claim_can_lower_to_runtime(dict(claim)):
        return SurfaceGateDecision(False, "claim_not_runtime_lowerable", claim_kind, "mulligan")
    cards = _claim_cards_from_mapping(claim)
    if claim_kind == "mulligan_keep" and _contains_start_of_game_non_hand_effect(
        cards, card_roles or {}
    ):
        return SurfaceGateDecision(
            False,
            "start_of_game_effect_does_not_require_opening_hand",
            claim_kind,
            "mulligan",
        )
    return SurfaceGateDecision(True, "allowed", claim_kind, "mulligan")


def can_lower_to_globalvalues(claim: Mapping[str, Any]) -> SurfaceGateDecision:
    claim_kind = normalized_claim_kind(claim)
    if claim_kind in GLOBALVALUES_RUNTIME_EVIDENCE_CLAIM_KINDS:
        return SurfaceGateDecision(False, "requires_runtime_evidence", claim_kind, "globalvalues")
    if claim_kind not in GLOBALVALUES_SURFACE_CLAIM_KINDS:
        return SurfaceGateDecision(
            False, "claim_kind_not_globalvalues_surface", claim_kind, "globalvalues"
        )
    if not claim_can_lower_to_runtime(dict(claim)):
        return SurfaceGateDecision(False, "claim_not_runtime_lowerable", claim_kind, "globalvalues")
    return SurfaceGateDecision(True, "allowed", claim_kind, "globalvalues")


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


def _contains_start_of_game_non_hand_effect(
    cards: list[str],
    card_roles: Mapping[str, Any],
) -> bool:
    for card_id in cards:
        role_row = card_roles.get(str(card_id), {})
        if not isinstance(role_row, Mapping):
            continue
        roles = {
            *[str(role).lower() for role in role_row.get("roles", [])],
            *[str(role).lower() for role in role_row.get("semantic_families", [])],
        }
        if "start_of_game" not in roles:
            continue
        if roles & START_OF_GAME_NON_HAND_EFFECT_ROLES:
            return True
        if "mulligan_anchor" not in roles:
            return True
    return False
