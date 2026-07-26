import pytest

from hsconfig.semantic_runtime_gate import decide_semantic_runtime


@pytest.mark.parametrize(
    "reason",
    [
        "automatic_from_deck_trigger",
        "automatic_from_hand_trigger",
        "conditional_cost_reduction",
        "conditional_self_damage_resource",
        "conditional_draw",
        "conditional_target_kill_burn",
        "self_damage_liability_body",
        "location_activation",
    ],
)
def test_risky_static_intent_is_report_only_without_exact_runtime_evidence(reason):
    decision = decide_semantic_runtime(
        semantic_reason=reason,
        source_lane="official_static_semantics",
        condition="*",
        runtime_block="BeforePlayCardBonus",
        claim_kind="mechanic_usage",
    )

    assert decision.allowed is False
    assert decision.reason == "semantic_surface_not_expressible"


def test_direct_enemy_hero_burn_can_lower_to_play_bonus():
    decision = decide_semantic_runtime(
        semantic_reason="direct_enemy_hero_burn",
        source_lane="official_static_semantics",
        condition="*",
        runtime_block="BeforePlayCardBonus",
        claim_kind="mechanic_usage",
    )

    assert decision.allowed is True
    assert decision.reason == "semantic_surface_supported"
