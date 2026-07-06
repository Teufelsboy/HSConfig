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


def test_mulligan_plan_preserves_multiple_conditions_for_same_card():
    claims = [
        {
            "claim_kind": "mulligan_keep",
            "cards": ["SW_448"],
            "conditions": {"coin": True},
            "claim_id": "keep_coin",
        },
        {
            "claim_kind": "mulligan_discard",
            "cards": ["SW_448"],
            "conditions": {"nocoin": True},
            "claim_id": "discard_no_coin",
        },
    ]

    plan = build_mulligan_plan(deck_name="ShadowPriest", claims=claims, card_roles={})

    sw448_rules = [row for row in plan["rules"] if row["card"] == "SW_448"]
    assert [(row["action"], row["condition"]) for row in sw448_rules] == [
        ("hold", "coin"),
        ("discard", "nocoin"),
    ]
    assert plan["suppressed_rules"] == []


def test_mulligan_plan_suppresses_unsupported_conditions_instead_of_broadening_to_wildcard():
    claims = [
        {
            "claim_kind": "mulligan_keep",
            "cards": ["CARD_001"],
            "conditions": "keep if the hand feels good",
            "claim_id": "bad_condition",
        }
    ]

    plan = build_mulligan_plan(deck_name="Deck", claims=claims, card_roles={})

    assert plan["rules"] == []
    assert plan["suppressed_rules"][0]["card"] == "CARD_001"
    assert plan["suppressed_rules"][0]["reason"] == "unsupported_condition"
    assert plan["quality"]["blocked_reason"] == "no_source_backed_mulligan_keeps"


def test_mulligan_plan_orders_conflicting_exact_rules_by_precedence():
    claims = [
        {
            "claim_kind": "mulligan_keep",
            "cards": ["CARD_001"],
            "conditions": {"coin": True},
            "claim_id": "keep_coin",
        },
        {
            "claim_kind": "mulligan_discard",
            "cards": ["CARD_001"],
            "conditions": {"coin": True},
            "claim_id": "discard_coin",
        },
    ]

    plan = build_mulligan_plan(deck_name="Deck", claims=claims, card_roles={})

    exact_rules = [
        (row["action"], row["condition"])
        for row in plan["rules"]
        if row["card"] == "CARD_001"
    ]
    assert exact_rules == [("discard", "coin"), ("hold", "coin")]


def test_mulligan_plan_source_discard_prevents_role_fallback_for_same_card():
    plan = build_mulligan_plan(
        deck_name="Deck",
        claims=[
            {
                "claim_kind": "mulligan_discard",
                "cards": ["CARD_001"],
                "conditions": {"nocoin": True},
                "claim_id": "discard_no_coin",
            }
        ],
        card_roles={
            "CARD_001": {
                "roles": ["one_drop"],
                "confidence": "archetype_inferred",
                "source_claim_ids": [],
            }
        },
    )

    card_rules = [row for row in plan["rules"] if row["card"] == "CARD_001"]
    assert len(card_rules) == 1
    assert card_rules[0]["action"] == "discard"
    assert card_rules[0]["condition"] == "nocoin"
