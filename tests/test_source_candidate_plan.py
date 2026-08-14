from __future__ import annotations

import pytest

from hsconfig.source_candidate_plan import build_source_candidate_plan


def shadowpriest_identity() -> dict:
    return {
        "deck_name": "ShadowPriest",
        "deck_code_hash": "sha256:shadow",
        "cards": [
            {
                "card_id": "SW_448",
                "name": "Darkbishop Benedictus",
                "cost": 5,
                "count": 1,
                "type": "MINION",
                "referenced_tags": ["START_OF_GAME_KEYWORD"],
                "text": (
                    "Start of Game: If the spells in your deck are all Shadow, "
                    "enter Shadowform."
                ),
            },
            {
                "card_id": "SW_446",
                "name": "Voidtouched Attendant",
                "cost": 1,
                "count": 2,
                "type": "MINION",
                "text": "Your hero deals 1 extra damage.",
            },
            {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2},
        ],
    }


def unknown_identity() -> dict:
    return {
        "deck_name": "UnknownDeck",
        "deck_code_hash": "sha256:unknown",
        "cards": [
            {"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2},
        ],
    }


def test_source_candidate_plan_rejects_stale_deck_code_argument():
    with pytest.raises(TypeError):
        build_source_candidate_plan(
            deck_name="ShadowPriest",
            deck_code="stale-deck-code",
            deck_identity=shadowpriest_identity(),
            candidate_archetypes={
                "primary_archetype": "wild_aggro_shadow_priest"
            },
        )


def test_source_candidate_plan_is_diagnostic_and_non_blocking_for_shadowpriest():
    plan = build_source_candidate_plan(
        deck_name="ShadowPriest",
        deck_identity=shadowpriest_identity(),
        candidate_archetypes={"primary_archetype": "wild_aggro_shadow_priest"},
        explicit_source_urls=[],
        current_date="2026-07-24",
    )

    assert plan["authority"] == "diagnostic_source_candidate_plan"
    assert plan["apply_blocking"] is False
    assert plan["runtime_write_performed"] is False
    assert plan["source_status_apply_blocking"] is False
    assert plan["candidate_registry_url_count"] >= 1
    assert plan["source_urls"][0].endswith("voidburn-wild-aggro-shadow-priest")
    assert plan["first_missing_source_action"] == "none"
    assert plan["query_count"] >= 1
    assert plan["target_summary"]["card_role_targets"] == len(plan["card_targets"])
    assert plan["promotion_boundaries"] == {
        "candidate_plan_can_promote": False,
        "candidate_plan_can_block_apply": False,
        "normal_apply_authority": "reports/operator_summary.json",
        "source_status_apply_blocking": False,
    }
    assert plan["queries"][0] == {
        "query": "2026 Wild ShadowPriest guide mulligan",
        "priority": 10,
        "target_claim_kinds": ["mulligan_keep", "card_role"],
        "reason": "find_public_guide_or_mulligan_source",
    }
    assert plan["queries"][1]["query"] == "2026 Wild ShadowPriest card roles"
    first_candidate = plan["candidate_url_rows"][0]
    assert set(first_candidate) == {
        "url",
        "source_family",
        "archetype",
        "priority",
        "expected_strength",
        "strength_ceiling",
        "expected_claim_kinds",
        "first_missing_source_action",
        "evergreen_wild_archetype",
    }
    assert first_candidate["url"] == plan["candidate_urls"][0]
    assert first_candidate["first_missing_source_action"] == "none"


def test_source_candidate_plan_keeps_darkbishop_effect_separate_from_mulligan():
    plan = build_source_candidate_plan(
        deck_name="ShadowPriest",
        deck_identity=shadowpriest_identity(),
        candidate_archetypes={"primary_archetype": "wild_aggro_shadow_priest"},
        explicit_source_urls=[],
        current_date="2026-07-24",
    )

    darkbishop = {row["card_id"]: row for row in plan["card_targets"]}["SW_448"]

    assert "hero_power_transform" in darkbishop["supported_static_claim_kinds"]
    assert "mulligan_keep" not in darkbishop["supported_static_claim_kinds"]
    assert "mulligan_keep" in darkbishop["requires_explicit_source_claim_kinds"]
    assert darkbishop["effect_semantics_not_mulligan_keep"] is True


def test_source_candidate_plan_for_unknown_deck_suggests_queries_without_blocking():
    plan = build_source_candidate_plan(
        deck_name="UnknownDeck",
        deck_identity=unknown_identity(),
        candidate_archetypes={"primary_archetype": "generic_low_confidence"},
        explicit_source_urls=[],
        current_date="2026-07-24",
    )

    assert plan["candidate_registry_url_count"] == 0
    assert plan["source_urls"] == []
    assert plan["query_count"] >= 2
    assert (
        plan["first_missing_source_action"]
        == "add_public_guide_url_or_use_static_semantics"
    )
    assert plan["apply_blocking"] is False
    assert plan["source_status_apply_blocking"] is False


def test_source_candidate_plan_for_unknown_deck_with_explicit_source_fetches_it():
    explicit = ["https://example.com/manual-guide"]
    plan = build_source_candidate_plan(
        deck_name="UnknownDeck",
        deck_identity=unknown_identity(),
        candidate_archetypes={"primary_archetype": "generic_low_confidence"},
        explicit_source_urls=explicit,
        current_date="2026-07-24",
    )

    assert plan["candidate_registry_url_count"] == 0
    assert plan["source_urls"] == explicit
    assert plan["first_missing_source_action"] == "fetch_and_validate_explicit_source_urls"
    assert plan["apply_blocking"] is False
    assert plan["source_status_apply_blocking"] is False


def test_source_candidate_plan_filters_invalid_explicit_source_urls():
    plan = build_source_candidate_plan(
        deck_name="UnknownDeck",
        deck_identity=unknown_identity(),
        candidate_archetypes={"primary_archetype": "generic_low_confidence"},
        explicit_source_urls=[
            "UnknownDeck deck guide 2026",
            "https://example.com/manual-guide",
        ],
        current_date="2026-07-24",
    )

    assert plan["explicit_source_urls"] == ["https://example.com/manual-guide"]
    assert plan["explicit_source_url_count"] == 1
    assert plan["source_urls"] == ["https://example.com/manual-guide"]


def test_source_candidate_plan_keeps_explicit_urls_before_registry_urls():
    explicit = ["https://example.com/manual-guide"]
    plan = build_source_candidate_plan(
        deck_name="ShadowPriest",
        deck_identity=shadowpriest_identity(),
        candidate_archetypes={"primary_archetype": "wild_aggro_shadow_priest"},
        explicit_source_urls=explicit,
        current_date="2026-07-24",
    )

    assert plan["explicit_source_url_count"] == 1
    assert plan["source_urls"][0] == explicit[0]
    assert len(plan["source_urls"]) == len(set(plan["source_urls"]))
