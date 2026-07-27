from hsconfig.autonomous_mulligan_policy import build_policy_backed_mulligan_rules


def test_policy_selects_early_playable_pressure_cards():
    result = build_policy_backed_mulligan_rules(
        deck_name="CurveDeck",
        deck_cards={
            "CARD_1": {"name": "One Drop", "cost": 1},
            "CARD_5": {"name": "Five Drop", "cost": 5},
        },
        card_roles={
            "CARD_1": {"roles": ["early_pressure", "one_drop"]},
            "CARD_5": {"roles": ["late_payoff"]},
        },
    )

    assert result["status"] == "applied"
    assert result["rules"] == [
        {
            "card": "CARD_1",
            "selector_kind": "card",
            "selector": "CARD_1",
            "action": "hold",
            "condition": "*",
            "reason": "policy_backed_autonomous_mulligan:one_drop",
            "confidence": "policy_backed",
            "source_type": "policy_backed_autonomous_mulligan",
            "policy_lane": "aggro",
            "policy_reason": "one_drop",
            "source_claim_ids": [],
        }
    ]
    assert result["candidate_count"] == 1
    assert result["selected_count"] == 1


def test_policy_backed_aggro_lane_prioritizes_one_drops_pressure_and_draw():
    result = build_policy_backed_mulligan_rules(
        deck_name="PirateDH",
        deck_cards={
            "ONE_DROP": {"name": "One Drop", "cost": 1},
            "DRAW_TWO": {"name": "Draw Two", "cost": 2},
            "SLOW_PAYOFF": {"name": "Slow Payoff", "cost": 5},
        },
        card_roles={
            "ONE_DROP": {"roles": ["one_drop", "pirate_pressure"]},
            "DRAW_TWO": {"roles": ["tempo_draw"]},
            "SLOW_PAYOFF": {"roles": ["late_payoff"]},
        },
    )

    assert result["status"] == "applied"
    assert [row["card"] for row in result["rules"]] == ["ONE_DROP", "DRAW_TWO"]
    assert {row["policy_lane"] for row in result["rules"]} == {"aggro"}
    assert all(row["source_type"] == "policy_backed_autonomous_mulligan" for row in result["rules"])
    assert result["suppressed"][0]["card"] == "SLOW_PAYOFF"
    assert result["suppressed"][0]["reason"] == "excluded_policy_role"


def test_policy_backed_big_lane_prioritizes_ramp_cheat_and_defensive_setup():
    result = build_policy_backed_mulligan_rules(
        deck_name="BigShaman",
        deck_cards={
            "RAMP": {"name": "Ramp", "cost": 2},
            "CHEAT": {"name": "Cheat", "cost": 3},
            "BIG_MINION": {"name": "Big Minion", "cost": 8},
        },
        card_roles={
            "RAMP": {"roles": ["ramp", "mana_cheat_setup"]},
            "CHEAT": {"roles": ["summon_from_deck", "cheat"]},
            "BIG_MINION": {"roles": ["late_payoff"]},
        },
    )

    assert result["status"] == "applied"
    assert [row["card"] for row in result["rules"]] == ["RAMP", "CHEAT"]
    assert {row["policy_lane"] for row in result["rules"]} == {"big"}
    assert result["suppressed"][0]["card"] == "BIG_MINION"


def test_policy_excludes_start_of_game_hero_power_transform_cards():
    result = build_policy_backed_mulligan_rules(
        deck_name="ShadowPriest",
        deck_cards={
            "SW_448": {"name": "Darkbishop Benedictus", "cost": 5},
            "SW_446": {"name": "Voidtouched Attendant", "cost": 1},
        },
        card_roles={
            "SW_448": {
                "roles": ["start_of_game", "hero_power_transform", "hero_power_pressure"],
                "semantic_families": ["start_of_game", "hero_power_transform"],
            },
            "SW_446": {"roles": ["early_pressure", "one_drop"]},
        },
    )

    assert [row["card"] for row in result["rules"]] == ["SW_446"]
    assert result["suppressed"] == [
        {
            "card": "SW_448",
            "reason": "excluded_non_hand_start_of_game_effect",
            "policy_lane": "aggro",
            "source_type": "policy_backed_autonomous_mulligan",
        }
    ]


def test_policy_excludes_start_of_game_even_when_mulligan_anchor_is_present():
    result = build_policy_backed_mulligan_rules(
        deck_name="StartEffectDeck",
        deck_cards={
            "CARD_EFFECT": {"name": "Start Effect", "cost": 1},
            "CARD_CURVE": {"name": "Curve Card", "cost": 2},
        },
        card_roles={
            "CARD_EFFECT": {
                "roles": ["start_of_game", "mulligan_anchor"],
                "semantic_families": ["start_of_game"],
            }
        },
    )

    assert [row["card"] for row in result["rules"]] == ["CARD_CURVE"]
    assert {
        "card": "CARD_EFFECT",
        "reason": "excluded_non_hand_start_of_game_effect",
        "policy_lane": "generic",
        "source_type": "policy_backed_autonomous_mulligan",
    } in result["suppressed"]


def test_policy_uses_last_resort_curve_anchor_when_roles_are_unknown():
    result = build_policy_backed_mulligan_rules(
        deck_name="UnknownDeck",
        deck_cards={
            "CARD_2": {"name": "Two Drop", "cost": 2},
            "CARD_7": {"name": "Seven Drop", "cost": 7},
        },
        card_roles={},
    )

    assert result["status"] == "applied"
    assert [row["card"] for row in result["rules"]] == ["CARD_2"]
    assert result["rules"][0]["reason"] == (
        "policy_backed_autonomous_mulligan:lowest_curve_anchor"
    )


def test_policy_veto_preserves_ordinary_safe_curve_fallback():
    result = build_policy_backed_mulligan_rules(
        deck_name="UnknownDeck",
        deck_cards={
            "SOURCE_GAP": {"name": "Unresolved Source Card", "cost": 1},
            "SAFE_CURVE": {"name": "Safe Curve Card", "cost": 2},
        },
        card_roles={},
        excluded_card_reasons={
            "SOURCE_GAP": "explicit_source_gap_requires_resolution",
        },
    )

    assert [row["card"] for row in result["rules"]] == ["SAFE_CURVE"]
    assert {
        "card": "SOURCE_GAP",
        "reason": "explicit_source_gap_requires_resolution",
        "policy_lane": "source_veto",
        "source_type": "policy_backed_autonomous_mulligan",
    } in result["suppressed"]


def test_policy_excludes_mixed_late_payoff_even_when_it_has_pressure_role():
    result = build_policy_backed_mulligan_rules(
        deck_name="MixedRoleDeck",
        deck_cards={
            "CARD_MIXED": {"name": "Mixed Role Card", "cost": 1},
            "CARD_SAFE": {"name": "Safe One Drop", "cost": 1},
        },
        card_roles={
            "CARD_MIXED": {"roles": ["early_pressure", "late_payoff"]},
            "CARD_SAFE": {"roles": ["one_drop"]},
        },
    )

    assert [row["card"] for row in result["rules"]] == ["CARD_SAFE"]
    assert {
        "card": "CARD_MIXED",
        "reason": "excluded_policy_role",
        "policy_lane": "aggro",
        "source_type": "policy_backed_autonomous_mulligan",
    } in result["suppressed"]


def test_policy_excludes_start_of_game_roles_from_mechanic_families_before_fallback():
    result = build_policy_backed_mulligan_rules(
        deck_name="MechanicFamilyDeck",
        deck_cards={
            "CARD_EFFECT": {"name": "Effect Card", "cost": 1},
            "CARD_CURVE": {"name": "Curve Card", "cost": 2},
        },
        card_roles={
            "CARD_EFFECT": {
                "semantic_families": ["start_of_game"],
                "mechanic_families": ["hero_power_transform"],
            }
        },
    )

    assert [row["card"] for row in result["rules"]] == ["CARD_CURVE"]
    assert result["suppressed"] == [
        {
            "card": "CARD_EFFECT",
            "reason": "excluded_non_hand_start_of_game_effect",
            "policy_lane": "generic",
            "source_type": "policy_backed_autonomous_mulligan",
        }
    ]
