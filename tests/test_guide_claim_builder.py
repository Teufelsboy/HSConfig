from hsconfig.guide_claim_builder import build_guide_claim_bundle


def test_builds_atomic_claims_from_structured_sources():
    cards = {
        "SW_448": {
            "name": "Darkbishop Benedictus",
            "text": "At the start of the game, if the spells in your deck are all Shadow, enter Shadowform.",
        },
        "SW_446": {"name": "Mind Spike", "text": "Hero Power: Deal 2 damage."},
        "CORE_CS2_235": {
            "name": "Shadowform",
            "text": "Your Hero Power becomes 'Deal 2 damage'.",
        },
    }
    sources = [
        {
            "source_url": "https://example.invalid/shadow-priest-guide",
            "source_title": "Shadow Priest Guide",
            "source_family": "guide",
            "retrieved_at": "2026-07-06T12:00:00Z",
            "claims": [
                {
                    "claim_kind": "mulligan_keep",
                    "cards": ["SW_448"],
                    "stance": "keep",
                    "evidence_text_short": "Keep Darkbishop Benedictus in every opener.",
                    "source_confidence": "high",
                }
            ],
        }
    ]

    bundle = build_guide_claim_bundle(
        deck_identity={"deck_name": "ShadowPriest"},
        card_metadata=cards,
        source_documents=sources,
    )

    claims = bundle["claims"]
    assert any(c["claim_kind"] == "mulligan_keep" and c["cards"] == ["SW_448"] for c in claims)
    assert any(c["claim_kind"] == "hero_power_transform" for c in claims)
    assert bundle["coverage"]["total_cards"] == 3
    assert bundle["coverage"]["guide_backed_cards"] == 1
    assert bundle["coverage"]["static_semantic_cards"] >= 1
    assert bundle["source_evidence_index"][0]["claim_count"] == 1


def test_vague_source_text_is_reported_not_promoted():
    bundle = build_guide_claim_bundle(
        deck_identity={"deck_name": "AnyDeck"},
        card_metadata={"CARD_001": {"name": "Example Card", "text": "Battlecry: Deal 2 damage."}},
        source_documents=[
            {
                "source_url": "https://example.invalid/guide",
                "source_title": "Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-06T12:00:00Z",
                "claims": [
                    {
                        "claim_kind": "generic_advice",
                        "cards": [],
                        "stance": "play well",
                        "evidence_text_short": "Use your cards wisely and pressure when possible.",
                        "source_confidence": "medium",
                    }
                ],
            }
        ],
    )

    assert not any(claim["claim_kind"] == "generic_advice" for claim in bundle["claims"])
    assert bundle["unsupported_claims"][0]["reason"] == "not_card_specific"


def test_static_semantics_cover_mechanic_text_without_guide_sources():
    bundle = build_guide_claim_bundle(
        deck_identity={"deck_name": "MechanicDeck"},
        card_metadata={
            "CARD_001": {"name": "Discover Card", "text": "Battlecry: Discover a spell."},
            "CARD_002": {"name": "Weapon Card", "text": "Battlecry: Equip a 3/2 weapon."},
        },
        source_documents=[],
    )

    claims = bundle["claims"]
    assert any(c["claim_kind"] == "mechanic_usage" and c["mechanic"] == "discover" for c in claims)
    assert any(c["claim_kind"] == "mechanic_usage" and c["mechanic"] == "weapon" for c in claims)
    assert bundle["coverage"]["guide_backed_cards"] == 0
    assert bundle["coverage"]["static_semantic_cards"] == 2


def test_off_deck_card_claim_is_reported_not_promoted():
    bundle = build_guide_claim_bundle(
        deck_identity={"deck_name": "Deck"},
        card_metadata={"CARD_001": {"name": "In Deck", "text": "Battlecry: Deal 2 damage."}},
        source_documents=[
            {
                "source_url": "https://example.invalid/guide",
                "source_title": "Guide",
                "source_family": "guide",
                "claims": [
                    {
                        "claim_kind": "mulligan_keep",
                        "cards": ["CARD_MISSING"],
                        "stance": "keep",
                        "evidence_text_short": "Keep a card that is not in this deck.",
                    }
                ],
            }
        ],
    )

    assert not any("CARD_MISSING" in claim.get("cards", []) for claim in bundle["claims"])
    assert bundle["unsupported_claims"][0]["reason"] == "card_not_in_deck"
    assert bundle["unsupported_claims"][0]["missing_cards"] == ["CARD_MISSING"]


def test_deck_scoped_gameplan_posture_claim_is_promoted_without_cards():
    bundle = build_guide_claim_bundle(
        deck_identity={"deck_name": "Aggro Deck"},
        card_metadata={"CARD_001": {"name": "In Deck", "text": ""}},
        source_documents=[
            {
                "source_url": "https://example.invalid/guide",
                "source_title": "Guide",
                "source_family": "guide",
                "claims": [
                    {
                        "claim_kind": "gameplan_posture",
                        "scope": "deck",
                        "stance": "aggressive",
                        "evidence_text_short": "This archetype plays aggressively.",
                    }
                ],
            }
        ],
    )

    posture_claims = [claim for claim in bundle["claims"] if claim["claim_kind"] == "gameplan_posture"]
    assert posture_claims
    assert posture_claims[0]["cards"] == []
    assert posture_claims[0]["scope"] == "deck"
