import importlib.util

from hsconfig.card_behavior_router import route_card_behavior_claims


def test_card_behavior_router_routes_specific_runtime_blocks():
    claims = [
        {
            "claim_id": "claim_target",
            "claim_kind": "targeting_rule",
            "cards": ["CARD_A"],
            "stance": "prefer_enemy_hero",
            "runtime_block": "BeforePlayCardBonus",
            "condition": {"runtime_condition": "my_target(count(),hero=true) > 0"},
            "runtime_value": "12",
        },
        {
            "claim_id": "claim_discover",
            "claim_kind": "mechanic_usage",
            "cards": ["CARD_B"],
            "mechanic": "discover",
            "runtime_block": "OnDiscoverCardBonus",
            "condition": {"runtime_condition": "my_discover(count(),cardid=CARD_C) > 0"},
            "runtime_value": "10",
        },
    ]

    plan = route_card_behavior_claims(claims)

    assert plan["rows"][0]["behavior_block"] == "BeforePlayCardBonus"
    assert plan["rows"][0]["condition"] == "my_target(count(),hero=true) > 0"
    assert plan["rows"][1]["behavior_block"] == "OnDiscoverCardBonus"
    assert plan["rows"][1]["condition"] == "my_discover(count(),cardid=CARD_C) > 0"


def test_card_behavior_surface_router_routes_claim_kinds_in_input_order():
    spec = importlib.util.find_spec("hsconfig.card_behavior_surface_router")
    assert spec is not None, "card behavior surface router module is required"
    from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces

    claims = [
        {
            "claim_id": "claim_choose_one",
            "claim_kind": "choose_one_choice",
            "cards": ["CARD_Z"],
            "choice_card_id": "CHOICE_ALPHA",
            "runtime_value": "9",
        },
        {
            "claim_id": "claim_in_hand",
            "claim_kind": "in_hand_value",
            "cards": ["CARD_A"],
            "runtime_value": "4",
        },
        {
            "claim_id": "claim_target",
            "claim_kind": "targeting_rule",
            "cards": ["CARD_B"],
            "stance": "prefer_enemy_minion",
            "runtime_value": "8",
        },
    ]

    plan = route_card_behavior_surfaces(
        claims,
        identity_links={"CARD_Z": [{"link_kind": "entourage", "card_id": "CHOICE_ALPHA"}]},
    )

    assert [row["claim_id"] for row in plan["rows"]] == [
        "claim_choose_one",
        "claim_in_hand",
        "claim_target",
    ]
    assert [row["card_id"] for row in plan["rows"]] == ["CARD_Z", "CARD_A", "CARD_B"]
    assert [row["behavior_block"] for row in plan["rows"]] == [
        "OnChooseOneCardBonus",
        "InHandBonus",
        "BeforeBattlecryTargetBonus",
    ]
    assert plan["option_resolution"] == [
        {
            "claim_id": "claim_choose_one",
            "card_id": "CARD_Z",
            "option_card_id": "CHOICE_ALPHA",
            "status": "resolved",
        }
    ]
    assert plan["suppressed"] == []


def test_card_behavior_surface_router_suppresses_unresolved_option_identity():
    spec = importlib.util.find_spec("hsconfig.card_behavior_surface_router")
    assert spec is not None, "card behavior surface router module is required"
    from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces

    plan = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_discover_option",
                "claim_kind": "discover_choice",
                "cards": ["CARD_A"],
                "option_card_id": "CARD_MISSING",
            }
        ],
        identity_links={"CARD_A": [{"link_kind": "entourage", "card_id": "CARD_PRESENT"}]},
    )

    assert plan["rows"] == []
    assert plan["suppressed"] == [
        {
            "claim_id": "claim_discover_option",
            "claim_kind": "discover_choice",
            "cards": ["CARD_A"],
            "reason": "unresolved_option_identity",
        }
    ]
    assert plan["option_resolution"] == [
        {
            "claim_id": "claim_discover_option",
            "card_id": "CARD_A",
            "option_card_id": "CARD_MISSING",
            "status": "unresolved",
        }
    ]


def test_card_behavior_surface_router_suppresses_option_claim_without_identity_links():
    spec = importlib.util.find_spec("hsconfig.card_behavior_surface_router")
    assert spec is not None, "card behavior surface router module is required"
    from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces

    plan = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_choose_one",
                "claim_kind": "choose_one_choice",
                "cards": ["CARD_A"],
                "choice_card_id": "CARD_OPTION",
            }
        ]
    )

    assert plan["rows"] == []
    assert plan["suppressed"] == [
        {
            "claim_id": "claim_choose_one",
            "claim_kind": "choose_one_choice",
            "cards": ["CARD_A"],
            "reason": "unresolved_option_identity",
        }
    ]
    assert plan["option_resolution"] == [
        {
            "claim_id": "claim_choose_one",
            "card_id": "CARD_A",
            "option_card_id": "CARD_OPTION",
            "status": "unresolved",
        }
    ]


def test_hero_power_transform_claim_routes_to_hero_power_surface():
    spec = importlib.util.find_spec("hsconfig.card_behavior_surface_router")
    assert spec is not None, "card behavior surface router module is required"
    from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces

    plan = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_darkbishop",
                "claim_kind": "hero_power_transform",
                "cards": ["SW_448"],
                "claim_readiness": "source_backed_static_semantics",
                "stance": "shadow_hero_power_pressure",
                "runtime_block": "BeforeUseHeroPowerBonus",
                "runtime_value": "8",
                "condition": "*",
            }
        ]
    )

    assert plan["suppressed"] == []
    assert plan["rows"][0]["card_id"] == "SW_448"
    assert plan["rows"][0]["behavior_block"] == "BeforeUseHeroPowerBonus"
    assert plan["rows"][0]["meaningful_runtime_surface"] is True


def test_known_bad_pattern_stays_report_only_without_documented_block():
    spec = importlib.util.find_spec("hsconfig.card_behavior_surface_router")
    assert spec is not None, "card behavior surface router module is required"
    from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces

    plan = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_bad",
                "claim_kind": "known_bad_pattern",
                "cards": ["CARD_A"],
                "claim_readiness": "guide_backed",
                "stance": "do_not_target_enemy_minion",
                "condition": "*",
            }
        ]
    )

    assert plan["rows"] == []
    assert plan["suppressed"][0]["reason"] == "no_documented_card_behavior_surface"


def test_known_bad_pattern_routes_with_explicit_documented_block():
    spec = importlib.util.find_spec("hsconfig.card_behavior_surface_router")
    assert spec is not None, "card behavior surface router module is required"
    from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces

    plan = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_bad",
                "claim_kind": "known_bad_pattern",
                "cards": ["CARD_A"],
                "claim_readiness": "guide_backed",
                "stance": "do_not_target_enemy_minion",
                "runtime_block": "BeforePlayCardBonus",
                "condition": "*",
            }
        ]
    )

    assert plan["suppressed"] == []
    assert plan["rows"][0]["card_id"] == "CARD_A"
    assert plan["rows"][0]["behavior_block"] == "BeforePlayCardBonus"
    assert plan["rows"][0]["meaningful_runtime_surface"] is True


def test_card_behavior_router_preserves_claim_row_order_across_cards():
    plan = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_z",
                "claim_kind": "card_role",
                "cards": ["CARD_Z"],
                "runtime_block": "OnBoardBonus",
            },
            {
                "claim_id": "claim_a",
                "claim_kind": "card_role",
                "cards": ["CARD_A"],
                "runtime_block": "InHandBonus",
            },
        ]
    )

    assert [row["card_id"] for row in plan["rows"]] == ["CARD_Z", "CARD_A"]


def test_routes_targeting_claim_to_cardid_surface():
    claims = [
        {
            "claim_kind": "targeting_rule",
            "cards": ["DMF_090"],
            "stance": "prefer_enemy_hero",
            "conditions": {"phase": "burn"},
            "claim_confidence": "high",
            "source_refs": ["guide:1"],
        }
    ]

    routed = route_card_behavior_claims(claims)

    assert routed["card_rows"]["DMF_090"]
    assert routed["card_rows"]["DMF_090"][0]["surface"] == "CardID.json"
    assert routed["card_rows"]["DMF_090"][0]["intent"] == "prefer_enemy_hero"
    assert routed["suppressed"] == []


def test_blocks_unsupported_claim_from_runtime_rows():
    routed = route_card_behavior_claims(
        [
            {
                "claim_kind": "global_gameplan_advice",
                "cards": ["CARD_001"],
                "stance": "be aggressive",
                "claim_confidence": "medium",
            }
        ]
    )

    assert routed["card_rows"] == {}
    assert routed["suppressed"][0]["reason"] == "no_documented_card_behavior_surface"


def test_card_role_fallback_does_not_override_stronger_targeting_row():
    routed = route_card_behavior_claims(
        [
            {
                "claim_kind": "targeting_rule",
                "cards": ["CARD_001"],
                "stance": "prefer_enemy_hero",
                "claim_confidence": "high",
            },
            {
                "claim_kind": "card_role",
                "cards": ["CARD_001"],
                "stance": "pressure",
                "claim_confidence": "medium",
            },
        ]
    )

    intents = [row["intent"] for row in routed["card_rows"]["CARD_001"]]
    assert "prefer_enemy_hero" in intents
    assert "in_hand_priority" not in intents


def test_unimplemented_mechanic_claim_is_suppressed():
    routed = route_card_behavior_claims(
        [
            {
                "claim_kind": "mechanic_usage",
                "cards": ["CARD_001"],
                "mechanic": "deathrattle",
                "claim_confidence": "high",
            }
        ]
    )

    assert routed["card_rows"] == {}
    assert routed["suppressed"][0]["reason"] == "no_documented_card_behavior_surface"


def test_unmapped_mechanic_claim_with_explicit_documented_block_lowers():
    routed = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_discard_payoff",
                "claim_kind": "mechanic_usage",
                "cards": ["DISCARD_PAYOFF"],
                "mechanic": "discard",
                "stance": "convert_discard_pressure",
                "runtime_block": "BeforePlayCardBonus",
                "runtime_value": "10",
                "condition": "*",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_lowerable",
            }
        ]
    )

    row = routed["card_rows"]["DISCARD_PAYOFF"][0]

    assert routed["suppressed"] == []
    assert row["behavior_block"] == "BeforePlayCardBonus"
    assert row["intent"] == "convert_discard_pressure"
    assert row["roles"] == ["discard"]
    assert row["meaningful_runtime_surface"] is True


def test_recruit_claim_can_lower_to_before_play_when_explicit_block_is_supported():
    spec = importlib.util.find_spec("hsconfig.card_behavior_surface_router")
    assert spec is not None, "card behavior surface router module is required"
    from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces

    result = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_recruit",
                "claim_kind": "mechanic_usage",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "guide",
                "cards": ["CARD_RECRUIT"],
                "mechanic": "recruit",
                "runtime_block": "BeforePlayCardBonus",
                "runtime_value": "9",
                "condition": "*",
                "source_claim_ids": ["claim_recruit"],
            }
        ]
    )

    assert result["suppressed"] == []
    assert result["rows"][0]["card_id"] == "CARD_RECRUIT"
    assert result["rows"][0]["behavior_block"] == "BeforePlayCardBonus"
    assert result["rows"][0]["value"] == "9"
    assert result["rows"][0]["meaningful_runtime_surface"] is True


def test_deathrattle_claim_can_lower_to_on_board_when_explicit_block_is_supported():
    spec = importlib.util.find_spec("hsconfig.card_behavior_surface_router")
    assert spec is not None, "card behavior surface router module is required"
    from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces

    result = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_deathrattle",
                "claim_kind": "mechanic_usage",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "guide",
                "cards": ["CARD_DEATHRATTLE"],
                "mechanic": "deathrattle",
                "runtime_block": "OnBoardBonus",
                "runtime_value": "7",
                "condition": "*",
                "source_claim_ids": ["claim_deathrattle"],
            }
        ]
    )

    assert result["suppressed"] == []
    assert result["rows"][0]["card_id"] == "CARD_DEATHRATTLE"
    assert result["rows"][0]["behavior_block"] == "OnBoardBonus"
    assert result["rows"][0]["value"] == "7"


def test_unmapped_mechanic_claim_with_unsupported_explicit_block_stays_report_only():
    routed = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_unknown",
                "claim_kind": "mechanic_usage",
                "cards": ["UNKNOWN_MECHANIC_CARD"],
                "mechanic": "unknown_combo_window",
                "runtime_block": "BeforePlayCardBonus",
                "condition": "*",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_lowerable",
            }
        ]
    )

    assert routed["card_rows"] == {}
    assert routed["suppressed"] == [
        {
            "claim_id": "claim_unknown",
            "claim_kind": "mechanic_usage",
            "cards": ["UNKNOWN_MECHANIC_CARD"],
            "reason": "unsupported_mechanic_runtime_block",
            "mechanic": "unknown_combo_window",
            "runtime_block": "BeforePlayCardBonus",
        }
    ]


def test_mapped_mechanic_claim_rejects_wrong_explicit_runtime_block():
    routed = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_weapon_wrong_block",
                "claim_kind": "mechanic_usage",
                "cards": ["WEAPON_CARD"],
                "mechanic": "weapon",
                "runtime_block": "OnBoardBonus",
                "condition": "*",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_lowerable",
            }
        ]
    )

    assert routed["card_rows"] == {}
    assert routed["suppressed"] == [
        {
            "claim_id": "claim_weapon_wrong_block",
            "claim_kind": "mechanic_usage",
            "cards": ["WEAPON_CARD"],
            "reason": "unsupported_mechanic_runtime_block",
            "mechanic": "weapon",
            "runtime_block": "OnBoardBonus",
        }
    ]


def test_unsupported_structured_condition_is_suppressed():
    routed = route_card_behavior_claims(
        [
            {
                "claim_kind": "targeting_rule",
                "cards": ["CARD_001"],
                "stance": "prefer_enemy_hero",
                "conditions": {"board_state": {"minions": 3}},
            }
        ]
    )

    assert routed["card_rows"] == {}
    assert routed["suppressed"][0]["reason"] == "unsupported_condition"


def test_router_maps_overkill_mechanic_to_before_overkilled_bonus():
    report = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_overkill",
                "claim_kind": "mechanic_usage",
                "cards": ["EX1_001"],
                "mechanic": "overkill",
                "source_confidence": "high",
            }
        ]
    )

    row = report["card_rows"]["EX1_001"][0]

    assert row["behavior_block"] == "BeforeOverkilledBonus"
    assert row["intent"] == "use_overkill_according_to_card_text"
    assert row["roles"] == ["overkill"]
    assert row["meaningful_runtime_surface"] is True
    assert row["value"] == "6"


def test_router_preserves_dredge_discover_cardid_fallback():
    report = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_dredge",
                "claim_kind": "mechanic_usage",
                "cards": ["TSC_001"],
                "mechanic": "dredge",
                "source_confidence": "high",
            }
        ]
    )

    row = report["card_rows"]["TSC_001"][0]

    assert row["behavior_block"] == "OnDiscoverCardBonus"
    assert row["roles"] == ["discover"]


def test_router_accepts_explicit_documented_runtime_block():
    report = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_on_board",
                "claim_kind": "card_role",
                "cards": ["EX1_002"],
                "stance": "keep_on_board",
                "runtime_block": "OnBoardBonus",
                "runtime_value": "9",
                "condition": "my_minion(count(),cardid=EX1_002) > 0",
            }
        ]
    )

    row = report["card_rows"]["EX1_002"][0]

    assert row["behavior_block"] == "OnBoardBonus"
    assert row["intent"] == "keep_on_board"
    assert row["roles"] == ["keep_on_board"]
    assert row["condition"] == "my_minion(count(),cardid=EX1_002) > 0"
    assert row["value"] == "9"
    assert row["meaningful_runtime_surface"] is True


def test_router_suppresses_unsupported_explicit_runtime_block():
    report = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_bad_block",
                "claim_kind": "card_role",
                "cards": ["EX1_003"],
                "runtime_block": "NotARealVisionAIBlock",
            }
        ]
    )

    assert "EX1_003" not in report["card_rows"]
    assert report["suppressed"] == [
        {
            "claim_id": "claim_bad_block",
            "claim_kind": "card_role",
            "cards": ["EX1_003"],
            "reason": "unsupported_card_behavior_block",
            "runtime_block": "NotARealVisionAIBlock",
        }
    ]
