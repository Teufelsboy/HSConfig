from __future__ import annotations

from dataclasses import dataclass

from hsconfig.card_intent_taxonomy import CONDITION_REQUIRED_SEMANTIC_INTENTS


REPORT_ONLY_WITHOUT_EXACT_RUNTIME_EVIDENCE = {
    "automatic_from_deck_trigger",
    "automatic_from_hand_trigger",
    "conditional_cost_reduction",
    "conditional_self_damage_resource",
    "conditional_draw",
    "conditional_target_kill_burn",
    "reciprocal_hero_burn",
    "self_damage_liability_body",
    "location_activation",
}
STATIC_SOURCE_LANES = {
    "official_static_semantics",
    "source_backed_static_semantics",
}
GUIDE_SOURCE_LANES = {
    "deck_matched_public_guide",
    "archetype_matched_public_guide",
}
COMPATIBLE_TARGET_SCOPES = {
    "enemy_hero",
    "enemy_minion",
    "friendly_hero",
    "friendly_minion",
}
STATIC_ACTION_SURFACES = {
    "damage_aura_amplifier": {
        ("OnBoardBonus", "card_role", "*"),
        ("OnBoardBonus", "mechanic_usage", "*"),
    },
    "direct_enemy_hero_burn": {
        ("BeforePlayCardBonus", "card_role", "*"),
        ("BeforePlayCardBonus", "mechanic_usage", "*"),
        ("BeforePlayCardBonus", "targeting_rule", "*"),
    },
    "hero_power_cost_aura": {
        ("BeforeUseHeroPowerBonus", "card_role", "*"),
        ("BeforeUseHeroPowerBonus", "mechanic_usage", "*"),
        ("OnBoardBonus", "card_role", "*"),
        ("OnBoardBonus", "mechanic_usage", "*"),
    },
    "hero_power_transform": {
        ("BeforeUseHeroPowerBonus", "card_role", "*"),
        ("BeforeUseHeroPowerBonus", "hero_power_transform", "*"),
        ("BeforeUseHeroPowerBonus", "mechanic_usage", "*"),
    },
    "location_deploy": {
        ("BeforePlayCardBonus", "card_role", "*"),
        ("BeforePlayCardBonus", "mechanic_usage", "*"),
    },
    "summon_trigger_board_engine": {
        ("OnBoardBonus", "card_role", "*"),
        ("OnBoardBonus", "mechanic_usage", "*"),
    },
}


@dataclass(frozen=True)
class SurfaceGateDecision:
    allowed: bool
    reason: str


def semantic_runtime_decision(
    *,
    semantic_intent: str,
    source_lane: str,
    condition: str,
    runtime_block: str,
    claim_kind: str,
    card_type: str = "",
    target_scope: str = "",
    option_identity: str = "",
) -> SurfaceGateDecision:
    normalized_type = str(card_type).strip().upper()
    if normalized_type == "SPELL" and runtime_block == "OnBoardBonus":
        return SurfaceGateDecision(False, "spell_cannot_own_on_board")
    if normalized_type == "SPELL" and runtime_block == "BeforeBattlecryTargetBonus":
        return SurfaceGateDecision(False, "spell_cannot_use_battlecry_target")

    if semantic_intent in CONDITION_REQUIRED_SEMANTIC_INTENTS and condition == "*":
        has_exact_option_identity = bool(option_identity) and semantic_intent in {
            "choose_one_condition_not_encoded",
            "discover_condition_not_encoded",
        }
        if not has_exact_option_identity:
            return SurfaceGateDecision(False, semantic_intent)
    if semantic_intent in {
        "discard_trigger_not_manual_play",
        "trigger_owner_does_not_attack",
        "buff_target_owner_mismatch",
        "battlecry_owner_does_not_attack",
    }:
        return SurfaceGateDecision(False, semantic_intent)
    if runtime_block == "BeforeBattlecryTargetBonus":
        if not target_scope:
            return SurfaceGateDecision(False, "missing_target_scope")
        if target_scope not in COMPATIBLE_TARGET_SCOPES:
            return SurfaceGateDecision(False, "invalid_target_scope")

    if source_lane in STATIC_SOURCE_LANES | GUIDE_SOURCE_LANES:
        if semantic_intent in REPORT_ONLY_WITHOUT_EXACT_RUNTIME_EVIDENCE:
            return SurfaceGateDecision(False, "semantic_surface_not_expressible")
        allowed_surfaces = STATIC_ACTION_SURFACES.get(semantic_intent)
        if allowed_surfaces is not None:
            if (runtime_block, claim_kind, condition) not in allowed_surfaces:
                return SurfaceGateDecision(False, "semantic_surface_not_expressible")
            return SurfaceGateDecision(True, "semantic_surface_supported")
        if source_lane in STATIC_SOURCE_LANES:
            return SurfaceGateDecision(False, "semantic_surface_not_proven")
    if source_lane in GUIDE_SOURCE_LANES:
        return SurfaceGateDecision(True, "guide_surface_supported")
    return SurfaceGateDecision(False, "semantic_surface_not_proven")


def decide_semantic_runtime(
    *,
    semantic_reason: str,
    source_lane: str,
    condition: str,
    runtime_block: str,
    claim_kind: str,
    card_type: str = "",
    target_scope: str = "",
    option_identity: str = "",
) -> SurfaceGateDecision:
    """Backward-compatible name for callers predating the surface-gate API."""
    return semantic_runtime_decision(
        semantic_intent=semantic_reason,
        source_lane=source_lane,
        condition=condition,
        runtime_block=runtime_block,
        claim_kind=claim_kind,
        card_type=card_type,
        target_scope=target_scope,
        option_identity=option_identity,
    )


SemanticRuntimeDecision = SurfaceGateDecision


__all__ = (
    "SemanticRuntimeDecision",
    "SurfaceGateDecision",
    "decide_semantic_runtime",
    "semantic_runtime_decision",
)
