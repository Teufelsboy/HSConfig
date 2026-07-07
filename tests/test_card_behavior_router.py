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
