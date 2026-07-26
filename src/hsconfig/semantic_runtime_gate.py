from __future__ import annotations

from dataclasses import dataclass


REPORT_ONLY_WITHOUT_EXACT_RUNTIME_EVIDENCE = {
    "automatic_from_deck_trigger",
    "automatic_from_hand_trigger",
    "conditional_cost_reduction",
    "conditional_self_damage_resource",
    "conditional_draw",
    "conditional_target_kill_burn",
    "self_damage_liability_body",
    "location_activation",
}
SUPPORTED_STATIC_ACTION_REASONS = {
    "damage_aura_amplifier",
    "direct_enemy_hero_burn",
    "hero_power_cost_aura",
    "hero_power_transform",
    "location_deploy",
    "reciprocal_hero_burn",
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
    del condition, runtime_block, claim_kind
    if (
        source_lane in {"official_static_semantics", "source_backed_static_semantics"}
        and semantic_reason in REPORT_ONLY_WITHOUT_EXACT_RUNTIME_EVIDENCE
    ):
        return SemanticRuntimeDecision(False, "semantic_surface_not_expressible")
    if semantic_reason in SUPPORTED_STATIC_ACTION_REASONS:
        return SemanticRuntimeDecision(True, "semantic_surface_supported")
    if source_lane in {
        "deck_matched_public_guide",
        "archetype_matched_public_guide",
    }:
        return SemanticRuntimeDecision(True, "guide_surface_supported")
    return SemanticRuntimeDecision(False, "semantic_surface_not_proven")


__all__ = ("SemanticRuntimeDecision", "decide_semantic_runtime")
