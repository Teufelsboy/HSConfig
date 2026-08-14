from hsconfig.guide_source_builder import (
    build_candidate_archetypes,
    build_deck_fingerprint,
    build_guide_builder_receipt,
    build_guide_sources,
)


DECK_IDENTITY = {
    "deck_name": "ShadowPriest",
    "deck_code_hash": "abc123",
    "cards": [
        {"card_id": "SW_448", "count": 1},
        {"card_id": "SW_446", "count": 2},
    ],
}

CARD_ROLES = {
    "SW_448": {"roles": ["hero_power_transform"], "confidence": "source_backed_static_semantics"},
    "SW_446": {"roles": ["burn_payoff"], "confidence": "archetype_inferred"},
}


def test_source_backed_documents_are_normalized_to_guide_sources():
    docs = [
        {
            "source_id": "shadow-guide",
            "source_url": "https://example.invalid/shadow",
            "source_title": "Shadow Priest Guide",
            "source_family": "guide",
            "retrieved_at": "2026-07-06T00:00:00Z",
            "deck_name": "ShadowPriest",
            "archetype": "aggro_burn",
            "claims": [
                {
                    "claim_kind": "mulligan_keep",
                    "cards": ["SW_448"],
                    "condition": {"coin": True},
                    "confidence": "source_backed",
                    "reason": "Keep the enabler.",
                    "source_confidence": "high",
                }
            ],
        }
    ]

    guide_sources = build_guide_sources(
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        card_roles=CARD_ROLES,
        source_documents=docs,
    )
    receipt = build_guide_builder_receipt(
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        source_documents=docs,
        guide_sources=guide_sources,
    )

    assert guide_sources["source_depth_status"] == "source_backed"
    assert guide_sources["sources"][0]["claims"][0]["claim_id"].startswith("claim_")
    assert guide_sources["sources"][0]["claims"][0]["condition"] == {"coin": True}
    assert receipt["source_depth_status"] == "source_backed"
    assert receipt["claim_count"] == 1
    assert receipt["stale_source_count"] == 0


def test_empty_sources_emit_static_semantics_fallback():
    guide_sources = build_guide_sources(
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        card_roles=CARD_ROLES,
        source_documents=[],
    )
    receipt = build_guide_builder_receipt(
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        source_documents=[],
        guide_sources=guide_sources,
    )

    assert guide_sources["source_depth_status"] == "static_semantics_only"
    assert guide_sources["sources"] == []
    assert receipt["static_card_semantics_used"] is True


def test_stale_or_unmatched_source_is_downgraded_but_kept():
    docs = [
        {
            "source_url": "https://example.invalid/old",
            "source_title": "Old Guide",
            "source_family": "guide",
            "retrieved_at": "2024-01-01T00:00:00Z",
            "deck_name": "OtherDeck",
            "archetype": "control_value",
            "claims": [{"claim_kind": "card_role", "cards": ["SW_446"], "reason": "Burn."}],
        }
    ]

    guide_sources = build_guide_sources(
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        card_roles=CARD_ROLES,
        source_documents=docs,
    )
    warnings = guide_sources["sources"][0]["warnings"]

    assert guide_sources["source_depth_status"] == "needs_more_research"
    assert {warning["reason"] for warning in warnings} == {"stale_source", "deck_name_mismatch"}


def test_current_source_without_claims_needs_more_research():
    guide_sources = build_guide_sources(
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        card_roles=CARD_ROLES,
        source_documents=[
            {
                "source_url": "https://example.invalid/empty",
                "source_title": "Empty Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-06T00:00:00Z",
                "deck_name": "ShadowPriest",
                "claims": [],
            }
        ],
    )

    assert guide_sources["source_depth_status"] == "needs_more_research"
    assert guide_sources["summary"]["claim_count"] == 0


def test_candidate_archetypes_and_fingerprint_are_stable():
    fingerprint = build_deck_fingerprint(
        DECK_IDENTITY,
        [{"card_id": "SW_446", "count": 2}, {"card_id": "SW_448", "count": 1}],
    )
    archetypes = build_candidate_archetypes(
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        card_roles=CARD_ROLES,
        source_documents=[{"archetype": "aggro_burn", "claims": []}],
    )

    assert fingerprint["card_count"] == 3
    assert fingerprint["deck_fingerprint"].startswith("sha256:")
    assert archetypes["primary_archetype"] == "aggro_burn"
    assert archetypes["candidates"][0]["confidence"] == "source_backed"
