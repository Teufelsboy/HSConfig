import pytest

from hsconfig.semantic_runtime_gate import (
    SemanticRuntimeDecision,
    decide_semantic_runtime,
)


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


def test_summon_trigger_engine_allows_only_on_board_value():
    allowed = decide_semantic_runtime(
        semantic_reason="summon_trigger_board_engine",
        source_lane="official_static_semantics",
        condition="*",
        runtime_block="OnBoardBonus",
        claim_kind="mechanic_usage",
    )
    rejected = decide_semantic_runtime(
        semantic_reason="summon_trigger_board_engine",
        source_lane="official_static_semantics",
        condition="*",
        runtime_block="BeforePlayCardBonus",
        claim_kind="mechanic_usage",
    )

    assert allowed.allowed is True
    assert rejected == SemanticRuntimeDecision(
        False,
        "semantic_surface_not_expressible",
    )


@pytest.mark.parametrize(
    "source_lane",
    ["official_static_semantics", "deck_matched_public_guide"],
)
def test_reciprocal_hero_burn_wildcard_row_is_report_only(source_lane):
    decision = decide_semantic_runtime(
        semantic_reason="reciprocal_hero_burn",
        source_lane=source_lane,
        condition="*",
        runtime_block="BeforePlayCardBonus",
        claim_kind="card_role",
    )

    assert decision == SemanticRuntimeDecision(
        False,
        "semantic_surface_not_expressible",
    )


@pytest.mark.parametrize(
    ("runtime_block", "allowed"),
    [
        ("OnBoardBonus", True),
        ("BeforePlayCardBonus", False),
    ],
)
def test_damage_aura_amplifier_allows_only_on_board_bonus(runtime_block, allowed):
    decision = decide_semantic_runtime(
        semantic_reason="damage_aura_amplifier",
        source_lane="official_static_semantics",
        condition="*",
        runtime_block=runtime_block,
        claim_kind="mechanic_usage",
    )

    assert decision.allowed is allowed
    assert decision.reason == (
        "semantic_surface_supported"
        if allowed
        else "semantic_surface_not_expressible"
    )


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
        ("damage_aura_amplifier", "OnBoardBonus", "card_role"),
        ("hero_power_cost_aura", "OnBoardBonus", "card_role"),
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


@pytest.mark.parametrize("runtime_block", ["InHandPlayPriority", "BeforePlayCardBonus"])
def test_hero_power_cost_aura_rejects_unrelated_static_surfaces(runtime_block):
    decision = decide_semantic_runtime(
        semantic_reason="hero_power_cost_aura",
        source_lane="official_static_semantics",
        condition="*",
        runtime_block=runtime_block,
        claim_kind="card_role",
    )

    assert decision.allowed is False
    assert decision.reason == "semantic_surface_not_expressible"
