from datetime import date

from hsconfig.card_behavior_router import route_card_behavior_claims
from hsconfig.guide_claim_builder import build_guide_claim_bundle


def _mechanic_claims(bundle, mechanic):
    return [
        claim
        for claim in bundle["claims"]
        if claim["claim_kind"] == "mechanic_usage" and claim.get("mechanic") == mechanic
    ]


def _mechanics(bundle):
    return {
        claim.get("mechanic")
        for claim in bundle["claims"]
        if claim["claim_kind"] == "mechanic_usage"
    }


def test_guide_claim_builder_uses_explicit_operator_date_for_source_freshness():
    bundle = build_guide_claim_bundle(
        deck_identity={
            "deck_name": "FrozenDateDeck",
            "cards": [{"card_id": "CARD_001", "count": 1}],
        },
        card_metadata={
            "CARD_001": {
                "name": "Frozen Date Card",
                "text": "Battlecry: Draw a card.",
            }
        },
        source_documents=[
            {
                "source_url": "https://example.test/frozen-date-guide",
                "source_title": "Frozen Date Guide",
                "source_family": "guide",
                "retrieved_at": "2028-12-01",
                "claims": [
                    {
                        "claim_kind": "card_role",
                        "cards": ["CARD_001"],
                        "stance": "draw_engine",
                        "evidence_text_short": "Use this card as a draw engine.",
                        "source_confidence": "high",
                    }
                ],
            }
        ],
        current_date=date(2030, 1, 15),
    )

    claim = next(
        claim
        for claim in bundle["claims"]
        if claim.get("source_url") == "https://example.test/frozen-date-guide"
    )
    assert claim["freshness_status"] == "stale"
    assert claim["claim_confidence"] == "medium"
    assert claim["retrieved_at"] == "2028-12-01"


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


def test_source_documents_are_integrated_before_static_semantic_backfill():
    bundle = build_guide_claim_bundle(
        deck_identity={
            "deck_name": "ShadowPriest",
            "cards": [
                {"card_id": "SW_448", "count": 1},
                {"card_id": "CORE_CS2_235", "count": 1},
            ],
        },
        card_metadata={
            "SW_448": {
                "name": "Darkbishop Benedictus",
                "text": "At the start of the game, if the spells in your deck are all Shadow, enter Shadowform.",
            },
            "CORE_CS2_235": {
                "name": "Shadowform",
                "text": "Your Hero Power becomes 'Deal 2 damage'.",
            },
        },
        source_documents=[
            {
                "source_url": "https://example.invalid/shadow-priest-guide",
                "source_title": "Shadow Priest Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-07T00:00:00Z",
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
        ],
    )

    assert bundle["claims"][0]["claim_kind"] == "mulligan_keep"
    assert bundle["claims"][0]["support_status"] == "source_backed"
    assert any(claim["support_status"] == "static_semantics" for claim in bundle["claims"][1:])
    assert bundle["claim_coverage_report"]["cards"]["SW_448"]["coverage_status"] == "guide_backed"
    assert bundle["claim_conflict_report"]["conflict_count"] == 0
    assert bundle["coverage"]["guide_backed_cards"] == 1


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


def test_low_confidence_source_claims_do_not_count_as_guide_backed_coverage():
    bundle = build_guide_claim_bundle(
        deck_identity={
            "deck_name": "WeakDeck",
            "cards": [
                {"card_id": "CARD_001", "count": 2},
                {"card_id": "CARD_002", "count": 2},
            ],
        },
        card_metadata={
            "CARD_001": {"name": "Weak Card One", "text": "Fixture card."},
            "CARD_002": {"name": "Weak Card Two", "text": "Fixture card."},
        },
        source_documents=[
            {
                "source_url": "https://example.invalid/weak-guide",
                "source_title": "Weak Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-07T00:00:00Z",
                "claims": [
                    {
                        "claim_kind": "card_role",
                        "cards": ["CARD_001"],
                        "stance": "maybe_core",
                        "evidence_text_short": "Card one might be part of the plan.",
                        "source_confidence": "low",
                    },
                    {
                        "claim_kind": "targeting_rule",
                        "cards": ["CARD_002"],
                        "stance": "maybe_face",
                        "evidence_text_short": "Card two might go face.",
                        "source_confidence": "low",
                    },
                ],
            }
        ],
    )

    low_claim_ids = [claim["claim_id"] for claim in bundle["claims"]]

    assert bundle["coverage"]["guide_backed_cards"] == 0
    assert bundle["coverage"]["uncovered_cards"] == ["CARD_001", "CARD_002"]
    assert bundle["claim_coverage_report"]["summary"] == {
        "guide_backed": 0,
        "static_semantics_backfilled": 0,
        "uncovered_low_confidence": 2,
    }
    assert bundle["claim_coverage_report"]["cards"]["CARD_001"]["source_claim_ids"] == [
        low_claim_ids[0]
    ]
    assert bundle["claim_coverage_report"]["cards"]["CARD_002"]["source_claim_ids"] == [
        low_claim_ids[1]
    ]


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
    assert bundle["claim_coverage_report"]["cards"]["CARD_001"]["coverage_status"] == "static_semantics_backfilled"
    assert bundle["claim_coverage_report"]["cards"]["CARD_002"]["coverage_status"] == "static_semantics_backfilled"
    assert bundle["claim_coverage_report"]["summary"]["static_semantics_backfilled"] == 2


def test_static_semantics_emit_deathrattle_mechanic_usage():
    bundle = build_guide_claim_bundle(
        deck_identity={"deck_name": "DeathrattleDeck"},
        card_metadata={
            "CARD_DEATHRATTLE": {
                "name": "Deathrattle Card",
                "text": "Deathrattle: Summon a 1/1 Spirit.",
            }
        },
        source_documents=[],
    )

    claims = _mechanic_claims(bundle, "deathrattle")

    assert len(claims) == 1
    assert claims[0]["cards"] == ["CARD_DEATHRATTLE"]
    assert claims[0]["confidence"] == "source_backed_static_semantics"
    assert claims[0]["claim_readiness"] == "source_backed_static_semantics"
    assert claims[0]["trust_ceiling"] == "static_semantics"


def test_static_semantics_emit_rush_and_charge_mechanic_usage():
    bundle = build_guide_claim_bundle(
        deck_identity={"deck_name": "AttackKeywordDeck"},
        card_metadata={
            "CARD_RUSH": {"name": "Rush Card", "text": "Rush"},
            "CARD_CHARGE": {"name": "Charge Card", "text": "Charge"},
        },
        source_documents=[],
    )

    assert _mechanic_claims(bundle, "rush")[0]["cards"] == ["CARD_RUSH"]
    assert _mechanic_claims(bundle, "charge")[0]["cards"] == ["CARD_CHARGE"]


def test_static_semantics_emit_spellburst_quickdraw_finale_manathirst_infuse_corrupt():
    bundle = build_guide_claim_bundle(
        deck_identity={"deck_name": "ModernLowerableDeck"},
        card_metadata={
            "CARD_SPELLBURST": {"name": "Spellburst Card", "text": "Spellburst: Draw a card."},
            "CARD_QUICKDRAW": {"name": "Quickdraw Card", "text": "Quickdraw: Deal 2 damage."},
            "CARD_FINALE": {"name": "Finale Card", "text": "Finale: Summon a 2/2."},
            "CARD_MANATHIRST": {"name": "Manathirst Card", "text": "Manathirst (6): Gain +2/+2."},
            "CARD_INFUSE": {"name": "Infuse Card", "text": "Infuse (3): Costs (2) less."},
            "CARD_CORRUPT": {"name": "Corrupt Card", "text": "Corrupt: Become upgraded."},
        },
        source_documents=[],
    )

    mechanics = _mechanics(bundle)

    assert {
        "spellburst",
        "quickdraw",
        "finale",
        "manathirst",
        "infuse",
        "corrupt",
    } <= mechanics


def test_static_semantics_keep_registry_only_partial_text_mechanics_visibility_only():
    bundle = build_guide_claim_bundle(
        deck_identity={
            "deck_name": "RegistryPartialDeck",
            "cards": [{"card_id": "CARD_DRIFT_PARTIAL", "count": 1}],
        },
        card_metadata={
            "CARD_DRIFT_PARTIAL": {
                "name": "Drift Partial Card",
                "text": (
                    "Battlecry: If your deck has no duplicates, Invoke Galakrond. "
                    "Dormant for 2 turns. Miniaturize. Honorable Kill. Elusive. "
                    "Poisonous. Summon a Jade Golem. Add C'Thun. This is an Arcane spell."
                ),
            }
        },
        source_documents=[],
    )

    mechanics = _mechanics(bundle)

    assert not {
        "cthun_package",
        "dormant",
        "elusive",
        "highlander",
        "honorable_kill",
        "invoke",
        "jade",
        "miniaturize",
        "poisonous",
        "spell_school",
    } & mechanics
    assert "battlecry" in mechanics


def test_static_semantics_do_not_lower_unsatisfied_highlander_payoff():
    bundle = build_guide_claim_bundle(
        deck_identity={
            "deck_name": "NonHighlanderDeck",
            "cards": [{"card_id": "CARD_HIGHLANDER_PAYOFF", "count": 2}],
        },
        card_metadata={
            "CARD_HIGHLANDER_PAYOFF": {
                "name": "Highlander Payoff",
                "text": "Battlecry: If your deck has no duplicates, deal 10 damage.",
            }
        },
        source_documents=[],
    )

    assert _mechanics(bundle) == set()
    assert route_card_behavior_claims(bundle["claims"])["card_rows"] == {}


def test_static_semantics_do_not_emit_runtime_lowering_claim_for_tradeable():
    bundle = build_guide_claim_bundle(
        deck_identity={"deck_name": "TradeableDeck"},
        card_metadata={
            "CARD_TRADEABLE": {"name": "Tradeable Card", "text": "Tradeable. Draw a card."}
        },
        source_documents=[],
    )

    assert _mechanic_claims(bundle, "tradeable") == []
    assert "draw" in _mechanics(bundle)


def test_static_semantics_do_not_emit_runtime_lowering_claim_for_forge_outcast_titan_starship():
    bundle = build_guide_claim_bundle(
        deck_identity={"deck_name": "ReportOnlyModernDeck"},
        card_metadata={
            "CARD_FORGE": {"name": "Forge Card", "text": "Forge: Gain +2/+2."},
            "CARD_OUTCAST": {"name": "Outcast Card", "text": "Outcast: Draw a card."},
            "CARD_TITAN": {"name": "Titan Card", "text": "Titan. Choose an ability."},
            "CARD_STARSHIP": {"name": "Starship Card", "text": "Launch your Starship."},
        },
        source_documents=[],
    )

    mechanics = _mechanics(bundle)

    assert not {"forge", "outcast", "titan", "starship"} & mechanics
    assert "draw" in mechanics


def test_existing_guide_claim_prevents_duplicate_static_claim():
    bundle = build_guide_claim_bundle(
        deck_identity={"deck_name": "GuideBackedMechanicDeck"},
        card_metadata={
            "CARD_DEATHRATTLE": {
                "name": "Deathrattle Card",
                "text": "Deathrattle: Summon a 1/1 Spirit.",
            }
        },
        source_documents=[
            {
                "source_url": "https://example.invalid/guide",
                "source_title": "Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-10T00:00:00Z",
                "claims": [
                    {
                        "claim_kind": "mechanic_usage",
                        "cards": ["CARD_DEATHRATTLE"],
                        "mechanic": "deathrattle",
                        "stance": "guide_deathrattle_timing",
                        "evidence_text_short": "Use the Deathrattle card for tempo.",
                        "source_confidence": "high",
                    }
                ],
            }
        ],
    )

    claims = _mechanic_claims(bundle, "deathrattle")

    assert len(claims) == 1
    assert claims[0]["confidence"] == "guide_backed"
    assert claims[0]["stance"] == "guide_deathrattle_timing"


def test_off_deck_card_claim_is_reported_not_promoted():
    bundle = build_guide_claim_bundle(
        deck_identity={"deck_name": "Deck"},
        card_metadata={"CARD_001": {"name": "In Deck", "text": "Battlecry: Deal 2 damage."}},
        source_documents=[
            {
                "source_url": "https://example.invalid/guide",
                "source_title": "Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-06T12:00:00Z",
                "claims": [
                    {
                        "claim_kind": "mulligan_keep",
                        "cards": ["CARD_MISSING"],
                        "stance": "keep",
                        "evidence_text_short": "Keep a card that is not in this deck.",
                        "source_confidence": "high",
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
                "retrieved_at": "2026-07-06T12:00:00Z",
                "claims": [
                    {
                        "claim_kind": "gameplan_posture",
                        "scope": "deck",
                        "stance": "aggressive",
                        "evidence_text_short": "This archetype plays aggressively.",
                        "source_confidence": "medium",
                    }
                ],
            }
        ],
    )

    posture_claims = [claim for claim in bundle["claims"] if claim["claim_kind"] == "gameplan_posture"]
    assert posture_claims
    assert posture_claims[0]["cards"] == []
    assert posture_claims[0]["scope"] == "deck"


def test_preserves_explicit_runtime_lowering_fields_before_semantic_gate():
    bundle = build_guide_claim_bundle(
        deck_identity={"deck_name": "ShadowPriest"},
        card_metadata={"SW_446": {"name": "Voidtouched Attendant", "text": ""}},
        source_documents=[
            {
                "source_url": "https://example.invalid/shadow-priest-guide",
                "source_title": "Shadow Priest Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-06T12:00:00Z",
                "claims": [
                    {
                        "claim_kind": "card_role",
                        "cards": ["SW_446"],
                        "stance": "prefer_enemy_hero",
                        "runtime_block": "BeforePlayCardBonus",
                        "runtime_value": "12",
                        "condition": "*",
                        "evidence_text_short": "Voidtouched Attendant should support the face-damage pressure plan.",
                        "source_confidence": "high",
                    }
                ],
            }
        ],
    )

    claim = next(claim for claim in bundle["claims"] if claim["claim_kind"] == "card_role")
    routed = route_card_behavior_claims([claim])

    assert claim["runtime_block"] == "BeforePlayCardBonus"
    assert claim["runtime_value"] == "12"
    assert claim["condition"] == "*"
    assert claim["conditions"] == "*"
    assert routed["card_rows"] == {}
    assert routed["suppressed"][0]["claim_id"] == claim["claim_id"]
    assert routed["suppressed"][0]["cards"] == ["SW_446"]
    assert (
        routed["suppressed"][0]["reason"]
        == "semantic_surface_not_expressible"
    )


def test_explicit_runtime_lowering_prefers_singular_condition_before_semantic_gate():
    bundle = build_guide_claim_bundle(
        deck_identity={"deck_name": "ShadowPriest"},
        card_metadata={"SW_446": {"name": "Voidtouched Attendant", "text": ""}},
        source_documents=[
            {
                "source_url": "https://example.invalid/shadow-priest-guide",
                "source_title": "Shadow Priest Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-06T12:00:00Z",
                "claims": [
                    {
                        "claim_kind": "card_role",
                        "cards": ["SW_446"],
                        "stance": "prefer_enemy_hero",
                        "conditions": {"posture": "burn"},
                        "condition": "my_target(count(),hero=true) > 0",
                        "runtime_block": "BeforePlayCardBonus",
                        "runtime_value": "12",
                        "evidence_text_short": "Voidtouched Attendant should support burn pressure when the runtime condition is active.",
                        "source_confidence": "high",
                    }
                ],
            }
        ],
    )

    claim = next(claim for claim in bundle["claims"] if claim["claim_kind"] == "card_role")
    routed = route_card_behavior_claims([claim])

    assert claim["condition"] == "my_target(count(),hero=true) > 0"
    assert claim["conditions"] == "my_target(count(),hero=true) > 0"
    assert routed["card_rows"] == {}
    assert routed["suppressed"][0]["claim_id"] == claim["claim_id"]
    assert routed["suppressed"][0]["cards"] == ["SW_446"]
    assert (
        routed["suppressed"][0]["reason"]
        == "semantic_surface_not_expressible"
    )
