from hsconfig.source_document_builder import build_source_document_bundle
from hsconfig.source_document_drafter import draft_source_documents


DECK_IDENTITY = {
    "deck_name": "ShadowPriest",
    "deck_code_hash": "sha256:shadow",
    "cards": [
        {"card_id": "BAR_735", "name": "Darkbishop Benedictus", "count": 1},
        {"card_id": "SW_446", "name": "Mind Spike Enabler", "count": 2},
    ],
}


def test_drafter_resolves_card_mentions_to_strict_source_documents():
    draft = draft_source_documents(
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        evidence_rows=[
            {
                "source_url": "https://example.invalid/shadow-priest",
                "source_title": "Shadow Priest Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-07T12:00:00Z",
                "archetype": "aggro_burn_hero_power_transform",
                "claim_kind": "hero_power_transform",
                "card_mentions": ["Darkbishop Benedictus"],
                "stance": "enable_transformed_hero_power",
                "evidence_text_short": "The deck wants the Shadow hero power online.",
                "source_confidence": "high",
            }
        ],
        current_date="2026-07-07",
    )

    documents = draft["source_documents"]
    assert documents[0]["claims"][0]["cards"] == ["BAR_735"]
    assert documents[0]["claims"][0]["claim_kind"] == "hero_power_transform"
    assert draft["draft_summary"]["resolved_claims"] == 1
    assert draft["unresolved_mentions"] == []

    bundle = build_source_document_bundle(
        deck_identity=DECK_IDENTITY,
        card_metadata={"cards": DECK_IDENTITY["cards"]},
        source_documents=documents,
        current_date="2026-07-07",
    )
    assert bundle["unsupported_claims"] == []


def test_drafter_reports_unresolved_mentions_without_dropping_source_context():
    draft = draft_source_documents(
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        evidence_rows=[
            {
                "source_url": "https://example.invalid/shadow-priest",
                "source_title": "Shadow Priest Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-07T12:00:00Z",
                "claim_kind": "card_role",
                "card_mentions": ["Missing Card"],
                "stance": "core_card",
                "evidence_text_short": "Missing Card is important.",
                "source_confidence": "medium",
            }
        ],
        current_date="2026-07-07",
    )

    assert draft["source_documents"][0]["claims"] == []
    assert draft["unresolved_mentions"][0]["mention"] == "Missing Card"
    assert draft["draft_summary"]["unresolved_mentions"] == 1


def test_drafter_drops_partially_resolved_claims_until_all_mentions_are_resolved():
    draft = draft_source_documents(
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        evidence_rows=[
            {
                "source_url": "https://example.invalid/shadow-priest",
                "source_title": "Shadow Priest Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-07T12:00:00Z",
                "claim_kind": "card_role",
                "card_mentions": ["Darkbishop Benedictus", "Missing Card"],
                "stance": "core_card",
                "evidence_text_short": "These cards are important together.",
                "source_confidence": "medium",
            }
        ],
        current_date="2026-07-07",
    )

    assert draft["source_documents"][0]["claims"] == []
    assert [row["mention"] for row in draft["unresolved_mentions"]] == ["Missing Card"]
    assert draft["draft_summary"]["dropped_claims"] == 1
