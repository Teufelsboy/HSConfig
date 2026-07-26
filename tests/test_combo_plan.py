from hsconfig.combo_plan import build_combo_plan as _build_combo_plan
from hsconfig.source_document_model import source_claim_signature


_COMBO_TEST_FINGERPRINT = "combo-plan-test-fingerprint"


def build_combo_plan(*, deck_cards, claims):
    authoritative_claims = [
        {
            **claim,
            "source_family": "guide",
            "source_type": "public_guide",
            "source_visibility": "full_text",
            "source_lane": "deck_matched_public_guide",
            "deck_match_scope": "exact_deck_matched",
            "promotion_eligible": True,
            "deck_match": {
                "exact_deck_evidence": {
                    "candidate_count": 1,
                    "decoded_candidate_count": 1,
                    "matched": True,
                    "matched_deck_fingerprint": _COMBO_TEST_FINGERPRINT,
                    "candidate_deck_code_hashes": ["sha256:combo-plan-test"],
                }
            },
        }
        for claim in claims
    ]
    receipts = [
        {
            "receipt_kind": "canonical_exact_deck_source_document",
            "matched_deck_fingerprint": _COMBO_TEST_FINGERPRINT,
            "claim_id": str(claim.get("claim_id", "")),
            "claim_signature": source_claim_signature(claim),
        }
        for claim in authoritative_claims
    ]
    return _build_combo_plan(
        deck_cards=deck_cards,
        claims=authoritative_claims,
        deck_identity={"deck_fingerprint": _COMBO_TEST_FINGERPRINT},
        verified_source_receipts=receipts,
    )


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
    claim = {
        "claim_id": "combo-condition",
        "claim_kind": "combo_sequence",
        "cards": ["EX1_001", "EX1_002"],
        "sequence": ["EX1_001", "EX1_002"],
        "timing_kind": "same_turn",
        "operator": ">>",
        "values": ["10", "20"],
        "conditions": {"unknown": "value"},
    }

    plan = build_combo_plan(
        deck_cards={"EX1_001", "EX1_002"},
        claims=[claim],
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
    claim = {
        "claim_id": "combo-wrapped-condition",
        "claim_kind": "combo_sequence",
        "cards": ["EX1_001", "EX1_002"],
        "sequence": ["EX1_001", "EX1_002"],
        "timing_kind": "same_turn",
        "operator": ">>",
        "values": ["10", "20"],
        "conditions": {
            "runtime_condition": "coin",
            "hand_contains": "BAD-ID",
        },
    }

    plan = build_combo_plan(
        deck_cards={"EX1_001", "EX1_002"},
        claims=[claim],
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
    claim = {
        "claim_id": "combo-falsey-condition",
        "claim_kind": "combo_sequence",
        "cards": ["EX1_001", "EX1_002"],
        "sequence": ["EX1_001", "EX1_002"],
        "timing_kind": "same_turn",
        "operator": ">>",
        "values": ["10", "20"],
        "conditions": {"coin": True, "hand_contains": ""},
    }

    plan = build_combo_plan(
        deck_cards={"EX1_001", "EX1_002"},
        claims=[claim],
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
    claim = {
        "claim_id": "combo-falsey-partner",
        "claim_kind": "combo_sequence",
        "cards": ["EX1_001", "EX1_002"],
        "sequence": ["EX1_001", "EX1_002"],
        "timing_kind": "same_turn",
        "operator": ">>",
        "values": ["10", "20"],
        "conditions": {"coin": True, "combo_partner": ""},
    }

    plan = build_combo_plan(
        deck_cards={"EX1_001", "EX1_002"},
        claims=[claim],
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
    claim = {
        "claim_id": "combo-wrong-type-any",
        "claim_kind": "combo_sequence",
        "cards": ["EX1_001", "EX1_002"],
        "sequence": ["EX1_001", "EX1_002"],
        "timing_kind": "same_turn",
        "operator": ">>",
        "values": ["10", "20"],
        "conditions": {"hand_contains_any": 1},
    }

    plan = build_combo_plan(
        deck_cards={"EX1_001", "EX1_002"},
        claims=[claim],
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
    plan = build_combo_plan(
        deck_cards={"CARD_A", "CARD_B"},
        claims=[
            {
                "claim_id": "raw_combo",
                "claim_kind": "combo_sequence",
                "cards": ["CARD_A", "CARD_B"],
                "sequence": ["CARD_A", "CARD_B"],
                "timing_kind": "same_turn",
                "operator": ">>",
                "values": ["12", "8"],
                "_claim_lifecycle": {
                    "claim_id": "lifecycle_combo",
                    "surface": "combo",
                },
            },
            {
                "claim_id": "raw_missing",
                "claim_kind": "combo_sequence",
                "cards": ["CARD_A", "CARD_MISSING"],
                "sequence": ["CARD_A", "CARD_MISSING"],
                "timing_kind": "same_turn",
                "operator": ">>",
                "values": ["10", "10"],
                "_claim_lifecycle": {
                    "claim_id": "lifecycle_missing",
                    "surface": "combo",
                },
            },
        ],
    )

    assert plan["combos"][0]["claim_id"] == "lifecycle_combo"
    assert plan["combos"][0]["source_claim_ids"] == ["raw_combo"]
    assert plan["suppressed"][0]["claim_id"] == "lifecycle_missing"


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


def test_combo_plan_reports_non_combo_claim_surface_rejection():
    plan = build_combo_plan(
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
