from hsconfig.mulligan_plan import build_mulligan_plan


def test_mulligan_plan_has_concrete_keeps_before_wildcard_discard():
    claims = [
        {"claim_kind": "mulligan_keep", "cards": ["SW_448"], "stance": "keep", "claim_confidence": "high"},
        {
            "claim_kind": "mulligan_keep",
            "cards": ["CARD_002"],
            "stance": "keep",
            "claim_confidence": "medium",
        },
    ]

    plan = build_mulligan_plan(deck_name="ShadowPriest", claims=claims, card_roles={})

    assert [row["card"] for row in plan["rules"][:2]] == ["SW_448", "CARD_002"]
    assert plan["rules"][-1] == {
        "card": "*",
        "action": "discard",
        "reason": "discard_unlisted_cards_after_source_backed_keeps",
    }
    assert plan["quality"]["has_concrete_keeps"] is True


def test_mulligan_plan_blocks_lone_wildcard_discard():
    plan = build_mulligan_plan(deck_name="UnknownDeck", claims=[], card_roles={})

    assert plan["rules"] == []
    assert plan["quality"]["blocked_reason"] == "no_source_backed_mulligan_keeps"


def test_mulligan_plan_uses_early_role_fallback_without_source_claims():
    plan = build_mulligan_plan(
        deck_name="CurveDeck",
        claims=[],
        card_roles={
            "CARD_001": {
                "roles": ["one_drop", "early_pressure"],
                "confidence": "archetype_inferred",
                "source_claim_ids": [],
            }
        },
    )

    assert plan["rules"][0]["card"] == "CARD_001"
    assert plan["rules"][0]["action"] == "hold"
    assert plan["rules"][0]["confidence"] == "archetype_inferred"
    assert plan["rules"][-1]["card"] == "*"
