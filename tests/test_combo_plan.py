from hsconfig.combo_plan import build_combo_plan


def test_exact_sequence_claim_becomes_combo_plan():
    plan = build_combo_plan(
        deck_cards={"CARD_A", "CARD_B"},
        claims=[
            {
                "claim_id": "claim_same_turn",
                "claim_kind": "combo_sequence",
                "cards": ["CARD_A", "CARD_B"],
                "stance": "play_CARD_A_before_CARD_B",
                "sequence": ["CARD_A", "CARD_B"],
                "timing_kind": "same_turn",
                "operator": ">>",
                "values": ["12", "8"],
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
                "claim_id": "claim_missing",
                "claim_kind": "combo_sequence",
                "cards": ["CARD_A", "CARD_MISSING"],
                "sequence": ["CARD_A", "CARD_MISSING"],
                "timing_kind": "same_turn",
                "operator": ">>",
                "values": ["10", "10"],
                "claim_confidence": "high",
            }
        ],
    )

    assert plan["combos"] == []
    assert plan["suppressed"][0]["reason"] == "card_not_in_deck"


def test_vague_combo_claim_without_ordered_sequence_is_suppressed():
    plan = build_combo_plan(
        deck_cards={"CARD_A", "CARD_B"},
        claims=[
            {
                "claim_id": "claim_vague_no_sequence",
                "claim_kind": "combo_sequence",
                "cards": ["CARD_A", "CARD_B"],
                "claim_confidence": "medium",
            }
        ],
    )

    assert plan["combos"] == []
    assert plan["suppressed"][0]["reason"] == "missing_timing"


def test_combo_plan_suppresses_vague_combo_without_timing():
    plan = build_combo_plan(
        deck_cards={"CARD_A", "CARD_B"},
        claims=[
            {
                "claim_id": "claim_vague",
                "claim_kind": "combo_sequence",
                "cards": ["CARD_A", "CARD_B"],
                "evidence_text_short": "These cards work well together.",
            }
        ],
    )

    assert plan["combos"] == []
    assert plan["suppressed"][0]["reason"] == "missing_timing"


def test_combo_plan_emits_cross_turn_operator_when_source_backed():
    plan = build_combo_plan(
        deck_cards={"CARD_A", "CARD_B"},
        claims=[
            {
                "claim_id": "claim_cross_turn",
                "claim_kind": "combo_sequence",
                "cards": ["CARD_A", "CARD_B"],
                "sequence": ["CARD_A", "CARD_B"],
                "timing_kind": "cross_turn",
                "operator": ">->",
                "values": ["20", "30"],
            }
        ],
    )

    assert plan["combos"][0]["operator"] == ">->"
    assert plan["combos"][0]["cards"] == ["CARD_A", "CARD_B"]
