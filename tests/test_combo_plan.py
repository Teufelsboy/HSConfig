from hsconfig.combo_plan import build_combo_plan as _build_combo_plan
from tests.combo_authority_fixtures import build_canonical_combo_case


def build_authorized_combo_case(*, deck_cards, case_id):
    bundle, deck_identity = build_canonical_combo_case(case_id)
    return _build_combo_plan(
        deck_cards=deck_cards,
        claims=bundle["claims"],
        deck_identity=deck_identity,
        verified_source_receipts=bundle["canonical_source_receipts"],
    )


def test_exact_sequence_claim_becomes_combo_plan():
    plan = build_authorized_combo_case(
        deck_cards={"CARD_A", "CARD_B"},
        case_id="claim_same_turn",
    )

    assert plan["combos"][0]["combo"] == "CARD_A>>CARD_B"
    assert plan["combos"][0]["value"] > 0
    assert plan["suppressed"] == []


def test_static_combo_claim_cannot_emit_runtime_combo_row():
    claim = {
        "claim_id": "combo-static-bypass",
        "claim_kind": "combo_sequence",
        "claim_readiness": "source_backed_static_semantics",
        "source_lane": "source_backed_static_semantics",
        "cards": ["EX1_001", "EX1_002"],
        "sequence": ["EX1_001", "EX1_002"],
        "timing_kind": "same_turn",
        "operator": ">>",
        "values": ["7", "9"],
    }

    plan = _build_combo_plan(
        deck_cards={"EX1_001", "EX1_002"},
        claims=[claim],
    )

    assert [row.get("combo") for row in plan["combos"]] == []
    assert plan["suppressed"] == [
        {
            "claim_id": "combo-static-bypass",
            "cards": ["EX1_001", "EX1_002"],
            "reason": "combo_requires_public_guide_source",
        }
    ]


def test_combo_with_unsupported_condition_is_suppressed():
    plan = build_authorized_combo_case(
        deck_cards={"EX1_001", "EX1_002"},
        case_id="combo-condition",
    )

    assert plan["combos"] == []
    assert plan["suppressed"] == [
        {
            "claim_id": "combo-condition",
            "cards": ["EX1_001", "EX1_002"],
            "reason": "unsupported_condition",
        }
    ]


def test_combo_rejects_runtime_condition_wrapper_with_condition_sibling():
    plan = build_authorized_combo_case(
        deck_cards={"EX1_001", "EX1_002"},
        case_id="combo-wrapped-condition",
    )

    assert plan["combos"] == []
    assert plan["suppressed"] == [
        {
            "claim_id": "combo-wrapped-condition",
            "cards": ["EX1_001", "EX1_002"],
            "reason": "unsupported_condition",
        }
    ]


def test_combo_with_falsey_structured_card_operand_is_suppressed():
    plan = build_authorized_combo_case(
        deck_cards={"EX1_001", "EX1_002"},
        case_id="combo-falsey-condition",
    )

    assert plan["combos"] == []
    assert plan["suppressed"] == [
        {
            "claim_id": "combo-falsey-condition",
            "cards": ["EX1_001", "EX1_002"],
            "reason": "unsupported_condition",
        }
    ]


def test_combo_with_falsey_combo_partner_is_suppressed():
    plan = build_authorized_combo_case(
        deck_cards={"EX1_001", "EX1_002"},
        case_id="combo-falsey-partner",
    )

    assert plan["combos"] == []
    assert plan["suppressed"] == [
        {
            "claim_id": "combo-falsey-partner",
            "cards": ["EX1_001", "EX1_002"],
            "reason": "unsupported_condition",
        }
    ]


def test_combo_with_wrong_type_hand_contains_any_is_suppressed():
    plan = build_authorized_combo_case(
        deck_cards={"EX1_001", "EX1_002"},
        case_id="combo-wrong-type-any",
    )

    assert plan["combos"] == []
    assert plan["suppressed"] == [
        {
            "claim_id": "combo-wrong-type-any",
            "cards": ["EX1_001", "EX1_002"],
            "reason": "unsupported_condition",
        }
    ]


def test_combo_plan_rows_use_lifecycle_claim_id_without_rewriting_source_claim_ids():
    emitted_bundle, deck_identity = build_canonical_combo_case("raw_combo")
    suppressed_bundle, _ = build_canonical_combo_case("raw_missing")
    claims = [*emitted_bundle["claims"], *suppressed_bundle["claims"]]
    receipts = [
        *emitted_bundle["canonical_source_receipts"],
        *suppressed_bundle["canonical_source_receipts"],
    ]
    lifecycle_ids = {
        "raw_combo": "lifecycle_combo",
        "raw_missing": "lifecycle_missing",
    }
    claims = [
        {
            **claim,
            "_claim_lifecycle": {
                "claim_id": lifecycle_ids[claim["claim_id"]],
                "surface": "combo",
            },
        }
        for claim in claims
    ]
    plan = _build_combo_plan(
        deck_cards={"CARD_A", "CARD_B"},
        claims=claims,
        deck_identity=deck_identity,
        verified_source_receipts=receipts,
    )

    assert plan["combos"][0]["claim_id"] == "lifecycle_combo"
    assert plan["combos"][0]["source_claim_ids"] == ["raw_combo"]
    assert plan["suppressed"][0]["claim_id"] == "lifecycle_missing"


def test_missing_deck_card_sequence_is_suppressed():
    plan = build_authorized_combo_case(
        deck_cards={"CARD_A"},
        case_id="claim_missing",
    )

    assert plan["combos"] == []
    assert plan["suppressed"][0]["reason"] == "card_not_in_deck"


def test_vague_combo_claim_without_ordered_sequence_is_suppressed():
    plan = build_authorized_combo_case(
        deck_cards={"CARD_A", "CARD_B"},
        case_id="claim_vague_no_sequence",
    )

    assert plan["combos"] == []
    assert plan["suppressed"][0]["reason"] == "missing_timing"


def test_combo_plan_suppresses_vague_combo_without_timing():
    plan = build_authorized_combo_case(
        deck_cards={"CARD_A", "CARD_B"},
        case_id="claim_vague",
    )

    assert plan["combos"] == []
    assert plan["suppressed"][0]["reason"] == "missing_timing"


def test_combo_plan_emits_cross_turn_operator_when_source_backed():
    plan = build_authorized_combo_case(
        deck_cards={"CARD_A", "CARD_B"},
        case_id="claim_cross_turn",
    )

    assert plan["combos"][0]["operator"] == ">->"
    assert plan["combos"][0]["cards"] == ["CARD_A", "CARD_B"]


def test_combo_plan_reports_non_combo_claim_surface_rejection():
    plan = _build_combo_plan(
        deck_cards={"A", "B"},
        claims=[
            {
                "claim_kind": "card_role",
                "runtime_surface": "Combo.json",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_candidate",
                "cards": ["A"],
                "claim_id": "not_combo",
            }
        ],
    )

    assert plan["combos"] == []
    assert plan["suppressed"][0]["reason"] == "claim_kind_not_combo_surface"
