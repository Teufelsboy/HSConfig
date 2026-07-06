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
    assert bundle["claim_coverage_report"]["cards"]["CARD_B"]["coverage_status"] == "uncovered_low_confidence"
    assert bundle["source_evidence_index"][0]["source_url"] == "https://example.invalid/guide"


def test_source_document_builder_preserves_mulligan_selectors():
    deck_identity = {
        "deck_name": "Fixture",
        "cards": [
            {"card_id": "CARD_A", "count": 2, "name": "Card A"},
            {"card_id": "CARD_B", "count": 2, "name": "Card B"},
        ],
    }
    source_documents = [
        {
            "source_url": "https://example.invalid/guide",
            "source_title": "Fixture Guide",
            "source_family": "guide",
            "retrieved_at": "2026-07-07T00:00:00Z",
            "claims": [
                {
                    "claim_kind": "mulligan_keep",
                    "cards": ["CARD_A", "CARD_B"],
                    "selector_kind": "plus_combo",
                    "selector": "CARD_A + CARD_B",
                    "evidence_text_short": "Keep the two-card opener together.",
                    "source_confidence": "high",
                }
            ],
        }
    ]

    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=source_documents,
    )

    assert bundle["claims"][0]["selector_kind"] == "plus_combo"
    assert bundle["claims"][0]["selector"] == "CARD_A + CARD_B"


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


def test_missing_or_blank_source_confidence_is_not_promoted():
    deck_identity = {
        "deck_name": "Fixture",
        "cards": [{"card_id": "CARD_A", "count": 2, "name": "Card A"}],
    }
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
                    "evidence_text_short": "Keep Card A.",
                },
                {
                    "claim_kind": "mulligan_keep",
                    "cards": ["CARD_A"],
                    "evidence_text_short": "Keep Card A in slow matchups.",
                    "source_confidence": "   ",
                },
            ],
        }
    ]

    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=source_documents,
    )

    assert bundle["claims"] == []
    assert [claim["reason"] for claim in bundle["unsupported_claims"]] == [
        "missing_claim_keys",
        "missing_claim_keys",
    ]
    assert [claim["missing_claim_keys"] for claim in bundle["unsupported_claims"]] == [
        ["source_confidence"],
        ["source_confidence"],
    ]
    assert bundle["source_evidence_index"][0]["claim_count"] == 0


def test_missing_source_keys_reject_all_claims_from_document():
    deck_identity = {
        "deck_name": "Fixture",
        "cards": [{"card_id": "CARD_A", "count": 2, "name": "Card A"}],
    }
    source_documents = [
        {
            "source_title": "Fixture Guide",
            "source_family": "guide",
            "retrieved_at": "2026-07-07T00:00:00Z",
            "claims": [
                {
                    "claim_kind": "mulligan_keep",
                    "cards": ["CARD_A"],
                    "evidence_text_short": "Keep Card A.",
                    "source_confidence": "high",
                }
            ],
        }
    ]

    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=source_documents,
    )

    assert bundle["claims"] == []
    assert bundle["unsupported_claims"][0]["reason"] == "missing_source_keys"
    assert bundle["unsupported_claims"][0]["missing_source_keys"] == ["source_url"]
    assert bundle["unsupported_claims"][0]["claim_kind"] == "mulligan_keep"
    assert bundle["source_evidence_index"][0]["claim_count"] == 0
    assert bundle["source_evidence_index"][0]["missing_source_keys"] == ["source_url"]


def test_source_document_coverage_is_source_only_without_static_backfill():
    deck_identity = {
        "deck_name": "Fixture",
        "cards": [{"card_id": "CARD_A", "count": 2, "name": "Card A"}],
    }
    card_metadata = {
        "cards": [
            {
                "card_id": "CARD_A",
                "count": 2,
                "name": "Card A",
                "text": "Battlecry: Discover a spell.",
            }
        ]
    }

    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata=card_metadata,
        source_documents=[],
    )

    assert bundle["claims"] == []
    assert bundle["claim_coverage_report"]["cards"]["CARD_A"]["coverage_status"] == "uncovered_low_confidence"
    assert bundle["claim_coverage_report"]["summary"] == {
        "guide_backed": 0,
        "static_semantics_backfilled": 0,
        "uncovered_low_confidence": 1,
    }


def test_source_document_builder_downgrades_stale_sources():
    deck_identity = {"deck_name": "Fixture", "cards": [{"card_id": "CARD_A", "count": 2}]}
    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=[
            {
                "source_url": "https://example.invalid/old",
                "source_title": "Old Guide",
                "source_family": "guide",
                "retrieved_at": "2024-01-01T00:00:00Z",
                "claims": [
                    {
                        "claim_kind": "mulligan_keep",
                        "cards": ["CARD_A"],
                        "stance": "keep",
                        "evidence_text_short": "Old guide keep.",
                        "source_confidence": "high",
                    }
                ],
            }
        ],
    )

    assert bundle["claims"][0]["freshness_status"] == "stale"
    assert bundle["claims"][0]["claim_confidence"] == "medium"


def test_source_document_builder_reports_conflicting_mulligan_claims():
    deck_identity = {"deck_name": "Fixture", "cards": [{"card_id": "CARD_A", "count": 2}]}
    docs = [
        {
            "source_url": "https://example.invalid/a",
            "source_title": "Guide A",
            "source_family": "guide",
            "retrieved_at": "2026-07-07T00:00:00Z",
            "claims": [
                {
                    "claim_kind": "mulligan_keep",
                    "cards": ["CARD_A"],
                    "stance": "keep",
                    "evidence_text_short": "Keep Card A.",
                    "source_confidence": "high",
                }
            ],
        },
        {
            "source_url": "https://example.invalid/b",
            "source_title": "Guide B",
            "source_family": "guide",
            "retrieved_at": "2026-07-07T00:00:00Z",
            "claims": [
                {
                    "claim_kind": "mulligan_discard",
                    "cards": ["CARD_A"],
                    "stance": "discard",
                    "evidence_text_short": "Throw Card A.",
                    "source_confidence": "high",
                }
            ],
        },
    ]

    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=docs,
    )

    assert bundle["claim_conflict_report"]["conflict_count"] == 1
    assert bundle["claim_conflict_report"]["conflicts"][0]["card_id"] == "CARD_A"


def test_source_document_builder_preserves_low_claim_confidence_from_current_high_source():
    deck_identity = {"deck_name": "Fixture", "cards": [{"card_id": "CARD_A", "count": 2}]}

    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=[
            {
                "source_url": "https://example.invalid/current",
                "source_title": "Current Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-07T00:00:00Z",
                "claims": [
                    {
                        "claim_kind": "mulligan_keep",
                        "cards": ["CARD_A"],
                        "stance": "keep",
                        "evidence_text_short": "Weakly keep Card A.",
                        "source_confidence": "high",
                        "claim_confidence": "low",
                    }
                ],
            }
        ],
    )

    assert bundle["claims"][0]["source_confidence"] == "high"
    assert bundle["claims"][0]["freshness_status"] == "current"
    assert bundle["claims"][0]["claim_confidence"] == "low"


def test_source_document_builder_preserves_low_claim_confidence_from_stale_medium_source():
    deck_identity = {"deck_name": "Fixture", "cards": [{"card_id": "CARD_A", "count": 2}]}

    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=[
            {
                "source_url": "https://example.invalid/stale",
                "source_title": "Stale Guide",
                "source_family": "guide",
                "retrieved_at": "2024-01-01T00:00:00Z",
                "claims": [
                    {
                        "claim_kind": "mulligan_keep",
                        "cards": ["CARD_A"],
                        "stance": "keep",
                        "evidence_text_short": "Old weak keep Card A.",
                        "source_confidence": "medium",
                        "claim_confidence": "low",
                    }
                ],
            }
        ],
    )

    assert bundle["claims"][0]["source_confidence"] == "medium"
    assert bundle["claims"][0]["freshness_status"] == "stale"
    assert bundle["claims"][0]["claim_confidence"] == "low"
