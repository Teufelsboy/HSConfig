from __future__ import annotations

from typing import Any

from hsconfig.source_document_builder import build_source_document_bundle


COMBO_AUTHORITY_FINGERPRINT = "sha256:test-combo-authority"

_DECK_CARDS = (
    "CARD_001",
    "CARD_A",
    "CARD_B",
    "CARD_MISSING",
    "EX1_001",
    "EX1_002",
)

_CANONICAL_COMBO_CLAIMS = (
    {
        "claim_id": "claim_same_turn",
        "claim_kind": "combo_sequence",
        "cards": ["CARD_A", "CARD_B"],
        "stance": "play_CARD_A_before_CARD_B",
        "sequence": ["CARD_A", "CARD_B"],
        "timing_kind": "same_turn",
        "operator": ">>",
        "values": ["12", "8"],
        "evidence_text_short": "Play CARD_A before CARD_B in the same turn.",
        "source_confidence": "high",
        "promotion_eligible": True,
    },
    {
        "claim_id": "combo-condition",
        "claim_kind": "combo_sequence",
        "cards": ["EX1_001", "EX1_002"],
        "sequence": ["EX1_001", "EX1_002"],
        "timing_kind": "same_turn",
        "operator": ">>",
        "values": ["10", "20"],
        "conditions": {"unknown": "value"},
        "evidence_text_short": "Play EX1_001 before EX1_002 under an unknown condition.",
        "source_confidence": "high",
        "promotion_eligible": True,
    },
    {
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
        "evidence_text_short": "Play EX1_001 before EX1_002 with a wrapped condition.",
        "source_confidence": "high",
        "promotion_eligible": True,
    },
    {
        "claim_id": "combo-falsey-condition",
        "claim_kind": "combo_sequence",
        "cards": ["EX1_001", "EX1_002"],
        "sequence": ["EX1_001", "EX1_002"],
        "timing_kind": "same_turn",
        "operator": ">>",
        "values": ["10", "20"],
        "conditions": {"coin": True, "hand_contains": ""},
        "evidence_text_short": "Play EX1_001 before EX1_002 with a card condition.",
        "source_confidence": "high",
        "promotion_eligible": True,
    },
    {
        "claim_id": "combo-falsey-partner",
        "claim_kind": "combo_sequence",
        "cards": ["EX1_001", "EX1_002"],
        "sequence": ["EX1_001", "EX1_002"],
        "timing_kind": "same_turn",
        "operator": ">>",
        "values": ["10", "20"],
        "conditions": {"coin": True, "combo_partner": ""},
        "evidence_text_short": "Play EX1_001 before EX1_002 with a partner condition.",
        "source_confidence": "high",
        "promotion_eligible": True,
    },
    {
        "claim_id": "combo-wrong-type-any",
        "claim_kind": "combo_sequence",
        "cards": ["EX1_001", "EX1_002"],
        "sequence": ["EX1_001", "EX1_002"],
        "timing_kind": "same_turn",
        "operator": ">>",
        "values": ["10", "20"],
        "conditions": {"hand_contains_any": 1},
        "evidence_text_short": "Play EX1_001 before EX1_002 with a hand condition.",
        "source_confidence": "high",
        "promotion_eligible": True,
    },
    {
        "claim_id": "raw_combo",
        "claim_kind": "combo_sequence",
        "cards": ["CARD_A", "CARD_B"],
        "sequence": ["CARD_A", "CARD_B"],
        "timing_kind": "same_turn",
        "operator": ">>",
        "values": ["12", "8"],
        "evidence_text_short": "Play CARD_A before CARD_B.",
        "source_confidence": "high",
        "promotion_eligible": True,
    },
    {
        "claim_id": "raw_missing",
        "claim_kind": "combo_sequence",
        "cards": ["CARD_A", "CARD_MISSING"],
        "sequence": ["CARD_A", "CARD_MISSING"],
        "timing_kind": "same_turn",
        "operator": ">>",
        "values": ["10", "10"],
        "evidence_text_short": "Play CARD_A before CARD_MISSING.",
        "source_confidence": "high",
        "promotion_eligible": True,
    },
    {
        "claim_id": "claim_missing",
        "claim_kind": "combo_sequence",
        "cards": ["CARD_A", "CARD_MISSING"],
        "sequence": ["CARD_A", "CARD_MISSING"],
        "timing_kind": "same_turn",
        "operator": ">>",
        "values": ["10", "10"],
        "evidence_text_short": "Play CARD_A before CARD_MISSING.",
        "source_confidence": "high",
        "promotion_eligible": True,
    },
    {
        "claim_id": "claim_vague_no_sequence",
        "claim_kind": "combo_sequence",
        "cards": ["CARD_A", "CARD_B"],
        "evidence_text_short": "CARD_A and CARD_B form a combo.",
        "source_confidence": "medium",
        "promotion_eligible": True,
    },
    {
        "claim_id": "claim_vague",
        "claim_kind": "combo_sequence",
        "cards": ["CARD_A", "CARD_B"],
        "evidence_text_short": "These cards work well together.",
        "source_confidence": "high",
        "promotion_eligible": True,
    },
    {
        "claim_id": "claim_cross_turn",
        "claim_kind": "combo_sequence",
        "cards": ["CARD_A", "CARD_B"],
        "sequence": ["CARD_A", "CARD_B"],
        "timing_kind": "cross_turn",
        "operator": ">->",
        "values": ["20", "30"],
        "evidence_text_short": "Play CARD_A before CARD_B across turns.",
        "source_confidence": "high",
        "promotion_eligible": True,
    },
    {
        "claim_id": "vague_combo",
        "claim_kind": "combo_sequence",
        "cards": ["CARD_001"],
        "sequence": ["CARD_001"],
        "timing_kind": "same_turn",
        "operator": ">>",
        "values": ["6"],
        "evidence_text_short": "Use CARD_001 as a one-card sequence.",
        "source_confidence": "high",
        "promotion_eligible": True,
    },
)


def build_canonical_combo_case(
    claim_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    matching_claims = [
        claim
        for claim in _CANONICAL_COMBO_CLAIMS
        if claim["claim_id"] == claim_id
    ]
    if len(matching_claims) != 1:
        raise KeyError(f"unknown canonical combo case: {claim_id}")
    deck_identity = {
        "deck_name": "CanonicalComboFixture",
        "deck_fingerprint": COMBO_AUTHORITY_FINGERPRINT,
        "cards": [
            {
                "card_id": card_id,
                "name": f"Fixture {card_id}",
                "count": 1,
            }
            for card_id in _DECK_CARDS
        ],
    }
    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=[
            {
                "source_url": "https://example.test/canonical-combo-guide",
                "source_title": "Canonical Exact Deck Combo Guide",
                "source_family": "guide",
                "source_type": "public_guide",
                "retrieved_at": "2026-07-26T00:00:00Z",
                "acquisition_provenance": {
                    "mode": "live_http",
                    "content_sha256": "sha256:" + ("a" * 64),
                    "authority": "live_verified",
                },
                "source_visibility": "full_text",
                "source_lane": "deck_matched_public_guide",
                "deck_match_scope": "exact_deck_matched",
                "deck_match": {
                    "exact_deck_evidence": {
                        "candidate_count": 1,
                        "decoded_candidate_count": 1,
                        "matched": True,
                        "matched_deck_fingerprint": COMBO_AUTHORITY_FINGERPRINT,
                        "candidate_deck_code_hashes": [
                            "sha256:test-combo-source"
                        ],
                    }
                },
                "claims": matching_claims,
            }
        ],
        current_date="2026-07-26",
    )
    if (
        len(bundle["claims"]) != 1
        or len(bundle["canonical_source_receipts"]) != 1
    ):
        raise AssertionError(
            f"canonical combo case must yield one claim and one receipt: {claim_id}"
        )
    return bundle, deck_identity
