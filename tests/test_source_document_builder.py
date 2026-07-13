from hsconfig.guide_source_builder import build_guide_sources
from hsconfig.source_document_model import (
    SUPPORTED_CLAIM_READINESS,
    SUPPORTED_SPECIFICITY_STATUSES,
    claim_can_lower_to_runtime,
)
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


def test_source_document_builder_preserves_mulligan_conditions_and_lowering_diagnostics():
    deck_identity = {
        "deck_name": "Fixture",
        "cards": [
            {"card_id": "CARD_A", "count": 2, "name": "Card A"},
            {"card_id": "CARD_B", "count": 2, "name": "Card B"},
        ],
    }
    source_documents = [
        {
            "source_url": "https://example.invalid/mulligan",
            "source_title": "Fixture Mulligan Guide",
            "source_family": "mulligan_guide",
            "retrieved_at": "2026-07-07T00:00:00Z",
            "claims": [
                {
                    "claim_kind": "mulligan_keep",
                    "cards": ["CARD_A"],
                    "selector_kind": "card",
                    "selector": "CARD_A",
                    "condition": {"coin": True},
                    "evidence_text_short": "Keep Card A with the Coin.",
                    "source_confidence": "high",
                },
                {
                    "claim_kind": "mulligan_keep",
                    "cards": ["CARD_A", "CARD_B"],
                    "selector": "CARD_A+CARD_B",
                    "condition": {"hand_contains": "CARD_B"},
                    "evidence_text_short": "Keep Card A with Card B already present.",
                    "source_confidence": "high",
                },
                {
                    "claim_kind": "mulligan_discard",
                    "cards": ["CARD_A"],
                    "selector": "DROP1",
                    "evidence_text_short": "Throw weak one-drops in this opener.",
                    "source_confidence": "high",
                },
                {
                    "claim_kind": "mulligan_keep",
                    "cards": ["CARD_B"],
                    "selector": "CARD_B",
                    "evidence_text_short": "Speculative keep only.",
                    "source_confidence": "low",
                },
            ],
        }
    ]

    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=source_documents,
    )

    first, second, third, fourth = bundle["claims"]
    assert first["selector_kind"] == "card"
    assert first["selector"] == "CARD_A"
    assert first["condition"] == {"coin": True}
    assert first["conditions"] == {"coin": True}
    assert first["runtime_lowerable"] is True
    assert first["runtime_lowering_reason"] == "runtime_lowerable"
    assert claim_can_lower_to_runtime(first)

    assert second["selector"] == "CARD_A+CARD_B"
    assert second["condition"] == {"hand_contains": "CARD_B"}
    assert second["runtime_lowerable"] is True
    assert claim_can_lower_to_runtime(second)

    assert third["selector"] == "DROP1"
    assert third["runtime_lowerable"] is True
    assert claim_can_lower_to_runtime(third)

    assert fourth["runtime_lowerable"] is False
    assert fourth["runtime_lowering_reason"] == "claim_not_runtime_lowerable"
    assert not claim_can_lower_to_runtime(fourth)


def test_source_document_builder_accepts_kind_and_card_id_aliases():
    deck_identity = {
        "deck_name": "Fixture",
        "cards": [{"card_id": "TEST_001", "count": 2, "name": "Test Card"}],
    }
    source_documents = [
        {
            "source_url": "https://example.invalid/alias-guide",
            "source_title": "Alias Guide",
            "source_family": "mulligan_guide",
            "retrieved_at": "2026-07-07T00:00:00Z",
            "claims": [
                {
                    "kind": "mulligan_keep",
                    "card_id": "TEST_001",
                    "selector": "TEST_001",
                    "evidence_text_short": "Keep Test Card.",
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

    claim = bundle["claims"][0]
    assert claim["claim_kind"] == "mulligan_keep"
    assert claim["cards"] == ["TEST_001"]
    assert claim["runtime_lowerable"] is True


def test_source_document_builder_preserves_combo_timing_metadata_and_provenance():
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
                    "claim_kind": "combo_sequence",
                    "cards": ["CARD_A", "CARD_B"],
                    "sequence": ["CARD_A", "CARD_B"],
                    "timing_kind": "same_turn",
                    "operator": ">>",
                    "values": ["8", "14"],
                    "evidence_text_short": "Play Card A into Card B on the same turn.",
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

    claim = bundle["claims"][0]
    assert claim["timing_kind"] == "same_turn"
    assert claim["operator"] == ">>"
    assert claim["source_refs"] == ["source:1", "https://example.invalid/guide"]
    assert claim["source_claim_ids"] == [claim["claim_id"]]


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
    guide_sources = build_guide_sources(
        deck_name="Fixture",
        deck_identity=deck_identity,
        card_roles={},
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
    assert guide_sources["source_depth_status"] == "needs_more_research"
    assert guide_sources["summary"]["claim_count"] == 0
    assert guide_sources["sources"][0]["claims"] == []


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
        current_date="2026-07-07",
    )

    assert bundle["claims"][0]["freshness_status"] == "stale"
    assert bundle["claims"][0]["claim_confidence"] == "medium"


def test_freshness_uses_injected_current_date_in_source_document_and_guide_source_paths():
    deck_identity = {"deck_name": "Fixture", "deck_code_hash": "abc", "cards": [{"card_id": "CARD_A", "count": 2}]}
    source_documents = [
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
        current_date="2026-07-07",
    )
    guide_sources = build_guide_sources(
        deck_name="Fixture",
        deck_identity=deck_identity,
        card_roles={},
        source_documents=source_documents,
        current_date="2026-07-07",
    )

    assert bundle["claims"][0]["freshness_status"] == "current"
    assert bundle["claims"][0]["claim_confidence"] == "high"
    assert guide_sources["sources"][0]["warnings"] == []


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


def test_source_document_builder_reports_broader_diagnostic_conflict_families():
    deck_identity = {
        "deck_name": "Fixture",
        "cards": [
            {"card_id": "TARGET", "count": 2},
            {"card_id": "COMBO_A", "count": 2},
            {"card_id": "COMBO_B", "count": 2},
            {"card_id": "DISCOVER", "count": 2},
        ],
    }
    docs = [
        {
            "source_url": "https://example.invalid/targeting",
            "source_title": "Targeting Guide",
            "source_family": "guide",
            "retrieved_at": "2026-07-07T00:00:00Z",
            "claims": [
                {
                    "claim_kind": "targeting_rule",
                    "cards": ["TARGET"],
                    "target_scope": "enemy_hero",
                    "evidence_text_short": "Target the enemy hero.",
                    "source_confidence": "high",
                },
                {
                    "claim_kind": "targeting_rule",
                    "cards": ["TARGET"],
                    "target_scope": "enemy_minion",
                    "evidence_text_short": "Target an enemy minion.",
                    "source_confidence": "high",
                },
                {
                    "claim_kind": "combo_sequence",
                    "cards": ["COMBO_A", "COMBO_B"],
                    "sequence": ["COMBO_A", "COMBO_B"],
                    "timing_kind": "same_turn",
                    "evidence_text_short": "Play the combo in the same turn.",
                    "source_confidence": "high",
                },
                {
                    "claim_kind": "combo_sequence",
                    "cards": ["COMBO_A", "COMBO_B"],
                    "sequence": ["COMBO_A", "COMBO_B"],
                    "timing_kind": "cross_turn",
                    "evidence_text_short": "Set up the combo across turns.",
                    "source_confidence": "high",
                },
                {
                    "claim_kind": "discover_choice",
                    "cards": ["DISCOVER"],
                    "option_card_id": "OPTION_A",
                    "evidence_text_short": "Discover Option A.",
                    "source_confidence": "high",
                },
                {
                    "claim_kind": "discover_choice",
                    "cards": ["DISCOVER"],
                    "option_card_id": "OPTION_B",
                    "evidence_text_short": "Discover Option B.",
                    "source_confidence": "high",
                },
            ],
        }
    ]

    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=docs,
    )

    conflicts = bundle["claim_conflict_report"]["conflicts"]
    assert {conflict["conflict_family"] for conflict in conflicts} == {
        "targeting",
        "combo_timing",
        "option_choice",
    }
    assert all(
        conflict["resolution"] == "downgrade_to_report_visible_conflict"
        for conflict in conflicts
    )


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
        current_date="2026-07-07",
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
        current_date="2026-07-07",
    )

    assert bundle["claims"][0]["source_confidence"] == "medium"
    assert bundle["claims"][0]["freshness_status"] == "stale"
    assert bundle["claims"][0]["claim_confidence"] == "low"


DECK_IDENTITY = {
    "deck_name": "Fixture",
    "cards": [
        {"card_id": "CARD_A", "name": "Card A", "count": 2},
        {"card_id": "CARD_B", "name": "Card B", "count": 2},
    ],
}

CARD_METADATA = {
    "cards": [
        {"card_id": "CARD_A", "name": "Card A", "count": 2},
        {"card_id": "CARD_B", "name": "Card B", "count": 2},
    ]
}


def test_source_claims_get_readiness_and_specificity_fields():
    bundle = build_source_document_bundle(
        deck_identity=DECK_IDENTITY,
        card_metadata=CARD_METADATA,
        source_documents=[
            {
                "source_url": "https://example.invalid/fixture-guide",
                "source_title": "Fixture Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-07T00:00:00Z",
                "claims": [
                    {
                        "claim_kind": "targeting_rule",
                        "cards": ["CARD_A"],
                        "stance": "prefer_enemy_hero",
                        "evidence_text_short": "Use Card A as face damage.",
                        "source_confidence": "high",
                    }
                ],
            }
        ],
    )

    claim = bundle["claims"][0]
    assert claim["claim_readiness"] == "guide_backed"
    assert claim["specificity_status"] == "card_specific"
    assert claim["trust_ceiling"] == "guide"


def test_low_confidence_source_claim_is_visible_but_not_strong():
    bundle = build_source_document_bundle(
        deck_identity=DECK_IDENTITY,
        card_metadata=CARD_METADATA,
        source_documents=[
            {
                "source_url": "https://example.invalid/weak-guide",
                "source_title": "Weak Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-07T00:00:00Z",
                "claims": [
                    {
                        "claim_kind": "card_role",
                        "cards": ["CARD_B"],
                        "stance": "maybe_synergy",
                        "evidence_text_short": "Card B is sometimes used with the deck plan.",
                        "source_confidence": "low",
                    }
                ],
            }
        ],
    )

    claim = bundle["claims"][0]
    assert claim["claim_readiness"] == "explicit_low_confidence"
    assert claim["specificity_status"] == "card_specific"
    assert claim["trust_ceiling"] == "report_only"
    assert claim["claim_readiness"] in SUPPORTED_CLAIM_READINESS
    assert claim["specificity_status"] in SUPPORTED_SPECIFICITY_STATUSES
    assert bundle["claim_coverage_report"]["cards"]["CARD_B"]["coverage_status"] == (
        "uncovered_low_confidence"
    )
    assert bundle["claim_coverage_report"]["cards"]["CARD_B"]["source_claim_ids"] == [
        claim["claim_id"]
    ]
    assert bundle["claim_coverage_report"]["summary"] == {
        "guide_backed": 0,
        "static_semantics_backfilled": 0,
        "uncovered_low_confidence": 2,
    }


def test_runtime_lowering_guard_blocks_legacy_low_confidence_claims_without_readiness():
    assert not claim_can_lower_to_runtime(
        {
            "claim_kind": "targeting_rule",
            "cards": ["CARD_A"],
            "confidence": "low",
        }
    )
    assert claim_can_lower_to_runtime(
        {
            "claim_kind": "targeting_rule",
            "cards": ["CARD_A"],
            "confidence": "source_backed",
        }
    )


def test_source_document_claim_fields_use_supported_vocabularies():
    bundle = build_source_document_bundle(
        deck_identity=DECK_IDENTITY,
        card_metadata=CARD_METADATA,
        source_documents=[
            {
                "source_url": "https://example.invalid/fixture-guide",
                "source_title": "Fixture Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-07T00:00:00Z",
                "claims": [
                    {
                        "claim_kind": "targeting_rule",
                        "cards": ["CARD_A"],
                        "stance": "prefer_enemy_hero",
                        "evidence_text_short": "Use Card A as face damage.",
                        "source_confidence": "high",
                    },
                    {
                        "claim_kind": "card_role",
                        "cards": ["CARD_B"],
                        "stance": "maybe_synergy",
                        "evidence_text_short": "Card B is a speculative synergy card.",
                        "source_confidence": "low",
                    },
                ],
            }
        ],
    )

    assert {claim["claim_readiness"] for claim in bundle["claims"]} <= SUPPORTED_CLAIM_READINESS
    assert {
        claim["specificity_status"] for claim in bundle["claims"]
    } <= SUPPORTED_SPECIFICITY_STATUSES
