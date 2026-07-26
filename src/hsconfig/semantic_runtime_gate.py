from __future__ import annotations

from dataclasses import dataclass


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
class SemanticRuntimeDecision:
    allowed: bool
    reason: str


def decide_semantic_runtime(
    *,
    semantic_reason: str,
    source_lane: str,
    condition: str,
    runtime_block: str,
    claim_kind: str,
) -> SemanticRuntimeDecision:
    if source_lane in STATIC_SOURCE_LANES | GUIDE_SOURCE_LANES:
        if semantic_reason in REPORT_ONLY_WITHOUT_EXACT_RUNTIME_EVIDENCE:
            return SemanticRuntimeDecision(False, "semantic_surface_not_expressible")
        allowed_surfaces = STATIC_ACTION_SURFACES.get(semantic_reason)
        if allowed_surfaces is not None:
            if (runtime_block, claim_kind, condition) not in allowed_surfaces:
                return SemanticRuntimeDecision(False, "semantic_surface_not_expressible")
            return SemanticRuntimeDecision(True, "semantic_surface_supported")
        if source_lane in STATIC_SOURCE_LANES:
            return SemanticRuntimeDecision(False, "semantic_surface_not_proven")
    if source_lane in GUIDE_SOURCE_LANES:
        return SemanticRuntimeDecision(True, "guide_surface_supported")
    return SemanticRuntimeDecision(False, "semantic_surface_not_proven")


__all__ = ("SemanticRuntimeDecision", "decide_semantic_runtime")
