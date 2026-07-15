from __future__ import annotations

from datetime import date

from hsconfig.source_evidence_policy import classify_source_evidence


def test_current_full_text_deck_matched_guide_can_promote():
    row = classify_source_evidence(
        {
            "source_family": "public_guide",
            "source_title": "ShadowPriest Guide",
            "normalized_text": (
                "ShadowPriest guide. Mulligan: keep Voidtouched Attendant "
                "and Mind Blast against slow decks. "
            )
            * 4,
            "publication_year": 2026,
            "source_visibility": "full_text",
            "deck_match": {
                "deck_name": "ShadowPriest",
                "matched_card_ids": ["SW_448"],
            },
        },
        deck_name="ShadowPriest",
        current_date=date(2026, 7, 15),
    )

    assert row["source_visibility"] == "full_text"
    assert row["source_lane"] == "deck_matched_public_guide"
    assert row["source_rank_lane"] == "guide_current_deck_match"
    assert row["promotion_eligible"] is True
    assert row["strong_promotion_eligible"] is True
    assert row["promotion_blockers"] == []
    assert row["first_missing_source_action"] == "none"


def test_decklist_stats_snippet_policy_and_partial_records_never_promote():
    cases = [
        {"source_family": "decklist", "source_visibility": "decklist_only"},
        {"source_family": "stats", "source_visibility": "full_text"},
        {"source_family": "public_guide", "source_visibility": "snippet_only"},
        {
            "source_type": "policy_backed_autonomous_mulligan",
            "source_visibility": "full_text",
        },
        {
            "source_family": "public_guide",
            "source_visibility": "full_text",
            "source_record_strength": "partial",
        },
    ]

    for case in cases:
        row = classify_source_evidence(
            {
                **case,
                "source_title": "ShadowPriest",
                "normalized_text": "ShadowPriest guide text " * 20,
                "publication_year": 2026,
                "deck_match": {
                    "deck_name": "ShadowPriest",
                    "matched_card_ids": ["SW_448"],
                },
            },
            deck_name="ShadowPriest",
            current_date=date(2026, 7, 15),
        )

        assert row["strong_promotion_eligible"] is False
        assert row["first_missing_source_action"] != "none"


def test_retrieved_at_does_not_count_as_publication_year():
    row = classify_source_evidence(
        {
            "source_family": "public_guide",
            "source_title": "ShadowPriest Guide",
            "normalized_text": "ShadowPriest guide text " * 20,
            "retrieved_at": "2026-07-15T12:00:00Z",
            "source_visibility": "full_text",
            "deck_match": {
                "deck_name": "ShadowPriest",
                "matched_card_ids": ["SW_448"],
            },
        },
        deck_name="ShadowPriest",
        current_date=date(2026, 7, 15),
    )

    assert row["source_rank_lane"] != "guide_current_deck_match"
    assert "missing_publication_year" in row["promotion_blockers"]
