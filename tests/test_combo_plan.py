from hsconfig.combo_plan import build_combo_plan


def test_exact_sequence_claim_becomes_combo_plan():
    plan = build_combo_plan(
        deck_cards={"CARD_A", "CARD_B"},
        claims=[
            {
                "claim_kind": "combo_sequence",
                "cards": ["CARD_A", "CARD_B"],
                "stance": "play_CARD_A_before_CARD_B",
                "sequence": ["CARD_A", "CARD_B"],
                "claim_confidence": "high",
                "source_refs": ["guide:combo"],
            }
        ],
    )

    assert plan["combos"][0]["combo"] == "CARD_A>>CARD_B"
    assert plan["combos"][0]["value"] > 0
    assert plan["suppressed"] == []


def test_missing_deck_card_sequence_is_suppressed():
    plan = build_combo_plan(
        deck_cards={"CARD_A"},
        claims=[
            {
                "claim_kind": "combo_sequence",
                "cards": ["CARD_A", "CARD_MISSING"],
                "sequence": ["CARD_A", "CARD_MISSING"],
                "claim_confidence": "high",
            }
        ],
    )

    assert plan["combos"] == []
    assert plan["suppressed"][0]["reason"] == "sequence_card_not_in_deck"


def test_vague_combo_claim_without_ordered_sequence_is_suppressed():
    plan = build_combo_plan(
        deck_cards={"CARD_A", "CARD_B"},
        claims=[
            {
                "claim_kind": "combo_sequence",
                "cards": ["CARD_A", "CARD_B"],
                "claim_confidence": "medium",
            }
        ],
    )

    assert plan["combos"] == []
    assert plan["suppressed"][0]["reason"] == "missing_ordered_sequence"
