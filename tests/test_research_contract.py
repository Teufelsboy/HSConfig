from pathlib import Path

from hsconfig.guide_research import normalize_source_claims
from hsconfig.io import read_json, write_json
from hsconfig.research_contract import (
    build_research_contract_bundle,
    write_research_contract_bundle,
)


def test_research_contract_emits_all_operator_artifacts():
    deck_identity = {
        "deck_name": "Fixture Aggro",
        "deck_slug": "fixture_aggro",
        "cards": [
            {"card_id": "EX1_001", "count": 2, "name": "Pressure One"},
            {"card_id": "EX1_002", "count": 1, "name": "Burst Two"},
            {"card_id": "EX1_003", "count": 1, "name": "Expensive Three"},
        ],
    }
    card_metadata = {
        "cards": [
            {
                "card_id": "EX1_001",
                "name": "Pressure One",
                "mechanic_families": ["battlecry", "damage"],
                "semantic_families": ["battlecry", "damage"],
            },
            {
                "card_id": "EX1_002",
                "name": "Burst Two",
                "mechanic_families": ["damage"],
                "semantic_families": ["damage"],
            },
            {
                "card_id": "EX1_003",
                "name": "Expensive Three",
                "mechanic_families": ["draw"],
                "semantic_families": ["draw"],
            },
        ]
    }
    source_claims = normalize_source_claims(
        [
            {
                "source": "guide",
                "url": "https://example.invalid/fixture-guide",
                "claim": "Always keep Pressure One and push face damage early.",
                "cards": ["EX1_001"],
                "claim_kind": "mulligan_keep",
                "claim_type": "mulligan_and_gameplan",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_candidate",
                "retrieved_at": "2026-07-05",
            },
            {
                "source": "guide",
                "url": "https://example.invalid/fixture-guide",
                "claim": "Use Pressure One with Burst Two for a combo burst turn.",
                "cards": ["EX1_001", "EX1_002"],
                "claim_type": "combo",
                "values": ["8", "14"],
            },
            {
                "source": "guide",
                "url": "https://example.invalid/fixture-guide",
                "claim": "Never keep Expensive Three in the opener.",
                "cards": ["EX1_003"],
                "claim_kind": "mulligan_discard",
                "claim_type": "bad_pattern",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_candidate",
            },
        ]
    )

    bundle = build_research_contract_bundle(deck_identity, card_metadata, source_claims)

    assert set(bundle) == {
        "archetype_research",
        "claims",
        "card_role_map",
        "mulligan_anchor_map",
        "card_usage_expectations",
        "known_bad_patterns",
        "globalvalue_intent",
        "coverage_summary",
        "guide_claim_bundle",
    }
    assert bundle["archetype_research"]["deck_name"] == "Fixture Aggro"
    assert bundle["archetype_research"]["confidence"] == "guide_backed"
    assert bundle["coverage_summary"]["deck_card_count"] == 3
    assert bundle["coverage_summary"]["guide_backed_card_count"] == 3
    assert bundle["card_role_map"]["EX1_001"]["confidence"] == "guide_backed"
    assert "pressure" in bundle["card_role_map"]["EX1_001"]["roles"]
    assert bundle["mulligan_anchor_map"]["EX1_001"]["intent"] == "hold"
    assert bundle["mulligan_anchor_map"]["EX1_003"]["intent"] == "avoid"
    assert bundle["card_usage_expectations"]["EX1_002"]["expected_use"] == "combo_burst_piece"
    assert bundle["known_bad_patterns"][0]["card_id"] == "EX1_003"
    assert bundle["globalvalue_intent"]["pressure_bias"] == "high"


def test_research_contract_uses_static_semantics_without_guide_claims():
    deck_identity = {
        "deck_name": "ShadowPriest",
        "deck_slug": "shadowpriest",
        "cards": [{"card_id": "SW_448", "count": 1}],
    }
    card_metadata = {
        "cards": [
            {
                "card_id": "SW_448",
                "name": "Darkbishop Benedictus",
                "semantic_families": [
                    "minion",
                    "start_of_game",
                    "shadowform",
                    "hero_power_transform",
                    "hero_power_pressure",
                ],
                "linked_entities": [
                    {
                        "card_id": "EX1_625t",
                        "name": "Mind Spike",
                        "type": "HERO_POWER",
                        "text": "Deal $2 damage.",
                    }
                ],
            }
        ]
    }

    bundle = build_research_contract_bundle(deck_identity, card_metadata, {"claims": []})

    assert bundle["archetype_research"]["confidence"] == "source_backed_static_semantics"
    assert bundle["card_role_map"]["SW_448"]["confidence"] == "source_backed_static_semantics"
    assert "hero_power_transform" in bundle["card_role_map"]["SW_448"]["roles"]
    assert bundle["card_usage_expectations"]["SW_448"]["expected_use"] == (
        "start_of_game_shadowform_enables_hero_power_pressure"
    )
    assert bundle["globalvalue_intent"]["overlays"]["MyHeroPowerValue"] == "increase"
    assert "Mind Spike" in bundle["globalvalue_intent"]["overlay_reasons"]["MyHeroPowerValue"]


def test_research_contract_marks_uncovered_cards_explicitly():
    deck_identity = {
        "deck_name": "Uncovered",
        "deck_slug": "uncovered",
        "cards": [{"card_id": "EX1_999", "count": 1}],
    }
    card_metadata = {"cards": [{"card_id": "EX1_999", "name": "Unknown Card"}]}

    bundle = build_research_contract_bundle(deck_identity, card_metadata, {"claims": []})

    assert bundle["archetype_research"]["confidence"] == "generic_low_confidence"
    assert bundle["card_role_map"]["EX1_999"]["confidence"] == "generic_low_confidence"
    assert bundle["card_usage_expectations"]["EX1_999"]["expected_use"] == "follow_archetype_plan"
    assert bundle["coverage_summary"]["generic_low_confidence_card_count"] == 1


def test_write_research_contract_bundle_writes_expected_files(tmp_path: Path):
    bundle = build_research_contract_bundle(
        {"deck_name": "Fixture", "deck_slug": "fixture", "cards": [{"card_id": "EX1_001"}]},
        {"cards": [{"card_id": "EX1_001", "name": "One"}]},
        {"claims": []},
    )

    write_research_contract_bundle(bundle, tmp_path / "reports")

    research_dir = tmp_path / "reports" / "research"
    assert read_json(research_dir / "archetype_research.json")["deck_name"] == "Fixture"
    assert read_json(research_dir / "claims.json")["claims"] == []
    assert "EX1_001" in read_json(research_dir / "card_role_map.json")
    assert "EX1_001" in read_json(research_dir / "mulligan_anchor_map.json")
    assert "EX1_001" in read_json(research_dir / "card_usage_expectations.json")
    assert read_json(research_dir / "known_bad_patterns.json") == []
    assert read_json(research_dir / "coverage_summary.json")["deck_card_count"] == 1
    assert read_json(research_dir / "guide_claim_bundle.json")["claims"] == []


def test_write_research_contract_bundle_reuses_existing_canonical_guide_claim_bytes(
    tmp_path: Path,
):
    reports_dir = tmp_path / "reports"
    canonical_path = reports_dir / "guide_claim_bundle.json"
    write_json(canonical_path, {"claims": [{"claim_id": "canonical"}]})
    bundle = build_research_contract_bundle(
        {"deck_name": "Fixture", "deck_slug": "fixture", "cards": []},
        {"cards": []},
        {"claims": []},
        guide_claim_bundle={"claims": [{"claim_id": "stale-research-copy"}]},
    )

    write_research_contract_bundle(bundle, reports_dir)

    assert (reports_dir / "research" / "guide_claim_bundle.json").read_bytes() == (
        canonical_path.read_bytes()
    )
