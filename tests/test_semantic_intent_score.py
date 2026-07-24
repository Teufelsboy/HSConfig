from hsconfig.semantic_intent_score import SemanticIntentScore, score_card_behavior_claim


def test_explicit_runtime_value_is_authoritative():
    claim = {
        "claim_kind": "targeting_rule",
        "cards": ["NX2_019"],
        "runtime_value": "8",
        "stance": "prefer_enemy_minion",
        "evidence_text_short": (
            "Mind Sear deals 2 damage to a minion and deals 3 damage "
            "to the enemy hero if it dies."
        ),
    }

    score = score_card_behavior_claim(
        claim,
        behavior_block="BeforeBattlecryTargetBonus",
        intent="prefer_enemy_minion",
        roles=["prefer_enemy_minion"],
        value_default="6",
    )

    assert isinstance(score, SemanticIntentScore)
    assert score.value == "8"
    assert score.band == "explicit"
    assert score.reason == "explicit_runtime_value"
    assert score.profile == "source_claim"


def test_blank_runtime_value_falls_back_to_explicit_value():
    claim = {
        "claim_kind": "targeting_rule",
        "cards": ["NX2_019"],
        "runtime_value": "",
        "value": "8",
        "stance": "prefer_enemy_minion",
    }

    score = score_card_behavior_claim(
        claim,
        behavior_block="BeforeBattlecryTargetBonus",
        intent="prefer_enemy_minion",
        roles=["prefer_enemy_minion"],
        value_default="6",
    )

    assert score.value == "8"
    assert score.band == "explicit"
    assert score.reason == "explicit_runtime_value"
    assert score.profile == "source_claim"


def test_conditional_minion_death_burn_scores_above_generic_default():
    claim = {
        "claim_kind": "targeting_rule",
        "cards": ["NX2_019"],
        "stance": "prefer_enemy_minion",
        "evidence_text_short": (
            "Mind Sear deals 2 damage to a minion and deals 3 damage "
            "to the enemy hero if it dies."
        ),
    }

    score = score_card_behavior_claim(
        claim,
        behavior_block="BeforeBattlecryTargetBonus",
        intent="prefer_enemy_minion",
        roles=["prefer_enemy_minion"],
        value_default="6",
    )

    assert score.value == "10"
    assert score.band == "high"
    assert score.reason == "conditional_minion_death_burn"
    assert "enemy_hero_damage" in score.matched_signals
    assert "death_condition" in score.matched_signals


def test_hero_power_transform_scores_as_critical_engine_effect():
    claim = {
        "claim_kind": "hero_power_transform",
        "cards": ["SW_448"],
        "stance": "shadowform_engine",
        "evidence_text_short": (
            "Darkbishop Benedictus changes the starting hero power to Mind Spike."
        ),
    }

    score = score_card_behavior_claim(
        claim,
        behavior_block="BeforeUseHeroPowerBonus",
        intent="hero_power_transform",
        roles=["hero_power", "shadowform_engine"],
        value_default="6",
    )

    assert score.value == "10"
    assert score.band == "critical"
    assert score.reason == "hero_power_transform"
    assert "hero_power" in score.matched_signals


def test_location_claim_scores_as_tempo_not_as_blocker():
    claim = {
        "claim_kind": "card_role",
        "cards": ["REV_248"],
        "mechanic": "location",
        "semantic_families": ["location"],
        "evidence_text_short": "Cathedral of Atonement is a Location that gives tempo.",
    }

    score = score_card_behavior_claim(
        claim,
        behavior_block="BeforePlayCardBonus",
        intent="location_tempo",
        roles=["location"],
        value_default="6",
    )

    assert score.value == "8"
    assert score.band == "medium"
    assert score.reason == "location_tempo"
    assert "location" in score.matched_signals


def test_unrecognized_claim_keeps_default_value_with_report_reason():
    claim = {
        "claim_kind": "card_role",
        "cards": ["GENERIC_CARD"],
        "semantic_families": ["tradeable"],
        "evidence_text_short": "The card has Tradeable.",
    }

    score = score_card_behavior_claim(
        claim,
        behavior_block="BeforePlayCardBonus",
        intent="tradeable",
        roles=["tradeable"],
        value_default="6",
    )

    assert score.value == "6"
    assert score.band == "default"
    assert score.reason == "semantic_default"


def test_unrecognized_claim_bounds_default_value():
    claim = {
        "claim_kind": "card_role",
        "cards": ["GENERIC_CARD"],
        "semantic_families": ["tradeable"],
        "evidence_text_short": "The card has Tradeable.",
    }

    low_score = score_card_behavior_claim(
        claim,
        behavior_block="BeforePlayCardBonus",
        intent="tradeable",
        roles=["tradeable"],
        value_default="2",
    )
    high_score = score_card_behavior_claim(
        claim,
        behavior_block="BeforePlayCardBonus",
        intent="tradeable",
        roles=["tradeable"],
        value_default="99",
    )

    assert low_score.value == "4"
    assert low_score.band == "default"
    assert low_score.reason == "semantic_default"
    assert high_score.value == "12"
    assert high_score.band == "default"
    assert high_score.reason == "semantic_default"


def test_semantic_score_reuses_taxonomy_reason_for_board_tempo():
    claim = {
        "claim_kind": "card_role",
        "cards": ["BOARD_001"],
        "stance": "pressure",
        "evidence_text_short": "Summon pirates to build a board.",
    }

    score = score_card_behavior_claim(
        claim,
        behavior_block="BeforePlayCardBonus",
        intent="board_tempo",
        roles=["pirate", "pressure"],
        value_default="6",
    )

    assert score.value == "8"
    assert score.band == "medium"
    assert score.reason == "board_tempo"
    assert score.profile == "semantic_intent"
    assert "pirate" in score.matched_signals


def test_shadowpriest_static_damage_claims_receive_specific_semantic_scores():
    cases = [
        (
            {
                "claim_kind": "mechanic_usage",
                "cards": ["GVG_009"],
                "evidence_text_short": "<b>Battlecry:</b> Deal 3 damage to each hero. battlecry BATTLECRY",
            },
            "BeforePlayCardBonus",
            "use_damage_according_to_card_text",
            ["damage"],
            "reciprocal_hero_burn",
            "10",
            "high",
        ),
        (
            {
                "claim_kind": "mechanic_usage",
                "cards": ["SCH_514"],
                "evidence_text_short": (
                    "Deal $3 damage to your hero. Return two friendly minions that died this game to your hand."
                ),
            },
            "BeforePlayCardBonus",
            "use_damage_according_to_card_text",
            ["damage"],
            "self_damage_resource",
            "8",
            "medium",
        ),
        (
            {
                "claim_kind": "mechanic_usage",
                "cards": ["VAC_419"],
                "evidence_text_short": "[x]Deal $4 damage to both heroes.",
            },
            "BeforePlayCardBonus",
            "use_damage_according_to_card_text",
            ["damage"],
            "reciprocal_hero_burn",
            "10",
            "high",
        ),
        (
            {
                "claim_kind": "mechanic_usage",
                "cards": ["VAC_512"],
                "evidence_text_short": (
                    "[x]Whenever this minion takes damage, also deal that amount to your hero. TRIGGER_VISUAL"
                ),
            },
            "BeforePlayCardBonus",
            "use_damage_according_to_card_text",
            ["damage"],
            "self_damage_liability_body",
            "6",
            "medium",
        ),
        (
            {
                "claim_kind": "mechanic_usage",
                "cards": ["YOD_032"],
                "evidence_text_short": (
                    "Costs (1) less for each damage dealt to your opponent this turn."
                ),
            },
            "BeforePlayCardBonus",
            "use_damage_according_to_card_text",
            ["damage"],
            "opponent_damage_discount_tempo",
            "8",
            "medium",
        ),
    ]

    for claim, block, intent, roles, reason, value, band in cases:
        score = score_card_behavior_claim(
            claim,
            behavior_block=block,
            intent=intent,
            roles=roles,
            value_default="6",
        )
        assert score.reason == reason
        assert score.value == value
        assert score.band == band
        assert score.profile == "semantic_intent"
        assert score.matched_signals
