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


@pytest.mark.parametrize(
    ("semantic_reason", "runtime_block", "claim_kind"),
    [
        ("direct_enemy_hero_burn", "InHandPlayPriority", "targeting_rule"),
        ("hero_power_transform", "InHandPlayPriority", "hero_power_transform"),
    ],
)
def test_supported_reason_cannot_bypass_static_surface_compatibility(
    semantic_reason, runtime_block, claim_kind
):
    decision = decide_semantic_runtime(
        semantic_reason=semantic_reason,
        source_lane="official_static_semantics",
        condition="*",
        runtime_block=runtime_block,
        claim_kind=claim_kind,
    )

    assert decision.allowed is False
    assert decision.reason == "semantic_surface_not_expressible"


def test_supported_reason_cannot_bypass_source_lane_authority():
    decision = decide_semantic_runtime(
        semantic_reason="direct_enemy_hero_burn",
        source_lane="policy_fallback",
        condition="*",
        runtime_block="BeforePlayCardBonus",
        claim_kind="targeting_rule",
    )

    assert decision.allowed is False
    assert decision.reason == "semantic_surface_not_proven"


@pytest.mark.parametrize(
    ("semantic_reason", "runtime_block", "claim_kind"),
    [
        ("direct_enemy_hero_burn", "BeforePlayCardBonus", "targeting_rule"),
        ("reciprocal_hero_burn", "BeforePlayCardBonus", "card_role"),
        ("damage_aura_amplifier", "OnBoardBonus", "card_role"),
        ("damage_aura_amplifier", "BeforePlayCardBonus", "mechanic_usage"),
        ("hero_power_cost_aura", "BeforeUseHeroPowerBonus", "card_role"),
        (
            "hero_power_transform",
            "BeforeUseHeroPowerBonus",
            "hero_power_transform",
        ),
        ("location_deploy", "BeforePlayCardBonus", "card_role"),
    ],
)
def test_documented_static_reason_surface_pairs_remain_supported(
    semantic_reason, runtime_block, claim_kind
):
    decision = decide_semantic_runtime(
        semantic_reason=semantic_reason,
        source_lane="source_backed_static_semantics",
        condition="*",
        runtime_block=runtime_block,
        claim_kind=claim_kind,
    )

    assert decision.allowed is True
    assert decision.reason == "semantic_surface_supported"


@pytest.mark.parametrize(
    ("condition", "claim_kind"),
    [
        ("my_hand(count(),cardid=DS1_233) > 0", "targeting_rule"),
        ("*", "hero_power_transform"),
    ],
)
def test_static_surface_requires_compatible_condition_and_claim_kind(
    condition, claim_kind
):
    decision = decide_semantic_runtime(
        semantic_reason="direct_enemy_hero_burn",
        source_lane="official_static_semantics",
        condition=condition,
        runtime_block="BeforePlayCardBonus",
        claim_kind=claim_kind,
    )

    assert decision.allowed is False
    assert decision.reason == "semantic_surface_not_expressible"
