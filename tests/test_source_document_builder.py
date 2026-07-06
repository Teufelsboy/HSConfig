from hsconfig.source_document_builder import build_source_document_bundle


def test_source_document_builder_atomizes_claims_and_tracks_coverage():
    deck_identity = {
        "deck_name": "Fixture",
        "cards": [
            {"card_id": "CARD_A", "count": 2, "name": "Card A"},
            {"card_id": "CARD_B", "count": 2, "name": "Card B"},
        ],
    }
    card_metadata = {"cards": deck_identity["cards"]}
    source_documents = [
        {
            "source_url": "https://example.invalid/guide",
            "source_title": "Fixture Guide",
            "source_family": "guide",
            "retrieved_at": "2026-07-07T00:00:00Z",
            "claims": [
                {
                    "claim_kind": "mulligan_keep",
                    "cards": ["CARD_A"],
                    "stance": "keep",
                    "evidence_text_short": "Keep Card A as opener.",
                    "source_confidence": "high",
                }
            ],
        }
    ]

    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata=card_metadata,
        source_documents=source_documents,
    )

    assert bundle["claims"][0]["claim_kind"] == "mulligan_keep"
    assert bundle["claims"][0]["support_status"] == "source_backed"
    assert bundle["claim_coverage_report"]["cards"]["CARD_A"]["coverage_status"] == "guide_backed"
    assert bundle["claim_coverage_report"]["cards"]["CARD_B"]["coverage_status"] in {
        "static_semantics_backfilled",
        "uncovered_low_confidence",
    }
    assert bundle["source_evidence_index"][0]["source_url"] == "https://example.invalid/guide"


def test_source_document_builder_reports_unsupported_and_off_deck_claims():
    deck_identity = {
        "deck_name": "Fixture",
        "cards": [{"card_id": "CARD_A", "count": 2, "name": "Card A"}],
    }
    card_metadata = {"cards": deck_identity["cards"]}
    source_documents = [
        {
            "source_url": "https://example.invalid/guide",
            "source_title": "Fixture Guide",
            "source_family": "guide",
            "retrieved_at": "2026-07-07T00:00:00Z",
            "claims": [
                {
                    "claim_kind": "generic_advice",
                    "cards": ["CARD_A"],
                    "evidence_text_short": "Play well.",
                    "source_confidence": "medium",
                },
                {
                    "claim_kind": "mulligan_keep",
                    "cards": ["CARD_MISSING"],
                    "evidence_text_short": "Keep a card that is not in the deck.",
                    "source_confidence": "high",
                },
            ],
        }
    ]

    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata=card_metadata,
        source_documents=source_documents,
    )

    assert bundle["claims"] == []
    assert [claim["reason"] for claim in bundle["unsupported_claims"]] == [
        "unsupported_claim_kind",
        "card_not_in_deck",
    ]
    assert bundle["unsupported_claims"][1]["missing_cards"] == ["CARD_MISSING"]
    assert bundle["claim_conflict_report"]["conflict_count"] == 0
