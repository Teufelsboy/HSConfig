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
