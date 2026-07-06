from hsconfig.card_behavior_router import route_card_behavior_claims


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
