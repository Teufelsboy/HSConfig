from __future__ import annotations

from datetime import date
from pathlib import Path

from hsconfig.deck_identity import stable_deck_fingerprint
from hsconfig.source_acquisition_provenance import (
    LIVE_HTTP,
    build_acquisition_provenance,
)
from hsconfig.source_autopilot import build_source_autopilot_bundle
from hsconfig.source_claim_compiler import compile_source_search_records
from hsconfig.source_evidence_policy import classify_source_evidence


CURRENT_DATE = date(2026, 7, 15)

SHADOW_DECK_IDENTITY = {
    "deck_name": "ShadowPriest",
    "deck_code_hash": "sha256:shadow",
    "deck_slug": "shadowpriest",
    "cards": [
        {
            "card_id": "SW_448",
            "name": "Darkbishop Benedictus",
            "cost": 5,
            "count": 1,
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
        },
        {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2},
        {"card_id": "SW_444", "name": "Twilight Deceptor", "cost": 2, "count": 2},
        {"card_id": "SCH_514", "name": "Raise Dead", "cost": 0, "count": 2},
        {"card_id": "GVG_009", "name": "Shadowbomber", "cost": 1, "count": 2},
    ],
}
SHADOW_DECK_IDENTITY["deck_fingerprint"] = stable_deck_fingerprint(
    (card["card_id"], card["count"]) for card in SHADOW_DECK_IDENTITY["cards"]
)


def _guide_record(claims: list[dict] | None = None) -> dict:
    return {
        "acquisition_provenance": build_acquisition_provenance(
            mode=LIVE_HTTP,
            content=(
                b"synthetic successful HTTP response for downstream authority tests"
            ),
        ),
        "source_url": "https://example.com/shadow-priest-guide-2026",
        "source_title": "ShadowPriest Current Public Guide 2026",
        "source_family": "guide",
        "source_visibility": "full_text",
        "publication_year": 2026,
        "source_record_strength": "candidate_strong",
        "normalized_text": (
            "ShadowPriest Current Public Guide 2026. Mulligan keeps cheap "
            "pressure cards, discards expensive cards, explains Mind Spike "
            "pressure, and maps card behavior for the current exact list."
        )
        * 2,
        "deck_match": {
            "deck_name": "ShadowPriest",
            "archetype": "aggro_burn_hero_power_transform",
            "matched_card_ids": [
                "SW_448",
                "SW_446",
                "TOY_381",
                "SW_444",
                "SCH_514",
                "GVG_009",
            ],
            "exact_deck_evidence": {
                "candidate_count": 1,
                "decoded_candidate_count": 1,
                "matched": True,
                "matched_deck_fingerprint": SHADOW_DECK_IDENTITY["deck_fingerprint"],
                "candidate_deck_code_hashes": ["sha256:lean-autopilot-source"],
            },
        },
        "deck_match_scope": "exact_deck_matched",
        "mulligan": {
            "keep_card_ids": ["TOY_381", "SW_444", "SCH_514", "GVG_009"],
            "discard_cost_min": 4,
            "evidence_text_short": (
                "Guide keeps cheap pressure cards and says not to keep "
                "cards costing 4 or more."
            ),
        },
        "claims": claims
        if claims is not None
        else [
            {
                "claim_kind": "gameplan_posture",
                "scope": "deck",
                "stance": "aggressive_burn_pressure",
                "source_confidence": "high",
            },
            {
                "claim_kind": "hero_power_transform",
                "cards": ["SW_448"],
                "timing": "start_of_game",
                "stance": "enable_mind_spike_shadow_hero_power",
                "source_confidence": "high",
            },
            {
                "claim_kind": "targeting_rule",
                "cards": ["SW_446"],
                "stance": "prefer_enemy_hero",
                "source_confidence": "high",
            },
            {
                "claim_kind": "card_role",
                "cards": ["TOY_381"],
                "stance": "zero_cost_mind_spike_pressure",
                "source_confidence": "high",
                "runtime_block": "BeforeUseHeroPowerBonus",
                "runtime_value": "8",
                "condition": "*",
            },
        ],
    }


def test_source_policy_has_strong_only_for_current_public_guides():
    strong = classify_source_evidence(
        _guide_record(),
        deck_name="ShadowPriest",
        current_date=CURRENT_DATE,
        deck_identity=SHADOW_DECK_IDENTITY,
    )
    decklist = classify_source_evidence(
        {
            **_guide_record(),
            "source_family": "decklist_only",
            "source_visibility": "decklist_only",
        },
        deck_name="ShadowPriest",
        current_date=CURRENT_DATE,
        deck_identity=SHADOW_DECK_IDENTITY,
    )
    stats = classify_source_evidence(
        {**_guide_record(), "source_family": "stats"},
        deck_name="ShadowPriest",
        current_date=CURRENT_DATE,
        deck_identity=SHADOW_DECK_IDENTITY,
    )
    static = classify_source_evidence(
        {
            **_guide_record(),
            "source_family": "official_static_semantics",
            "deck_match": {"deck_name": "ShadowPriest", "matched_card_ids": ["SW_448"]},
        },
        deck_name="ShadowPriest",
        current_date=CURRENT_DATE,
        deck_identity=SHADOW_DECK_IDENTITY,
    )

    assert strong["trust_ceiling"] == "source_backed_strong"
    assert strong["strong_promotion_eligible"] is True
    assert decklist["trust_ceiling"] == "decklist_informed"
    assert decklist["strong_promotion_eligible"] is False
    assert "decklist_not_guide" in decklist["promotion_blockers"]
    assert stats["trust_ceiling"] == "source_informed_partial"
    assert stats["strong_promotion_eligible"] is False
    assert "stats_not_guide" in stats["promotion_blockers"]
    assert static["trust_ceiling"] == "static_semantics_only"
    assert static["strong_promotion_eligible"] is False
    assert "static_semantics_not_deck_strategy" in static["promotion_blockers"]


def test_compiler_cost_band_discard_can_apply_to_darkbishop_but_keep_cannot():
    payload = compile_source_search_records(
        deck_name="ShadowPriest",
        deck_identity=SHADOW_DECK_IDENTITY,
        acquired_records=[
            {
                **_guide_record(claims=[]),
                "normalized_text": (
                    "Mulligan: Keep Papercraft Angel. Do not keep any "
                    "4 cost or higher cards. Darkbishop Benedictus enables "
                    "Mind Spike at the start of the game."
                ),
            }
        ],
        current_date="2026-07-15",
    )

    claims = payload["records"][0]["claims"]
    assert any(
        claim["claim_kind"] == "mulligan_keep" and claim.get("cards") == ["TOY_381"]
        for claim in claims
    )
    assert any(
        claim["claim_kind"] == "mulligan_discard" and claim.get("cards") == ["SW_448"]
        for claim in claims
    )
    assert any(
        claim["claim_kind"] == "hero_power_transform"
        and claim.get("cards") == ["SW_448"]
        for claim in claims
    )
    assert not any(
        claim["claim_kind"] == "mulligan_keep" and claim.get("cards") == ["SW_448"]
        for claim in claims
    )


def test_source_autopilot_report_has_lean_machine_authority_fields():
    bundle = build_source_autopilot_bundle(
        deck_name="ShadowPriest",
        deck_identity=SHADOW_DECK_IDENTITY,
        source_search_records=[_guide_record()],
        current_date="2026-07-15",
    )

    report = bundle["source_autopilot_report"]
    assert report["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert report["runtime_apply_authority"] == "reports/operator_summary.json"
    assert report["default_only_runtime_surfaces"] == []
    assert report["source_backed_strong_closure"]["closed"] is True
    assert report["source_backed_strong_closure"]["promotion_ready"] is True
    assert report["first_missing_source_action_by_card"] == {}
    assert report["first_missing_source_action_by_surface"] == {}
    assert report["card_closure_lanes"]["SW_448"] == "lowered"
    assert report["surface_closure_lanes"]["Mulligan.json"] == "emitted"
    card_rows = {row["card_id"]: row for row in report["card_rows"]}
    assert card_rows["SW_448"]["lane"] == "lowered"
    assert "hero_power_transform" in card_rows["SW_448"]["claim_kinds"]
    assert {row["lane"] for row in report["card_rows"]} <= {
        "lowered",
        "suppressed",
        "source_gap",
        "static_only",
        "not_applicable",
    }
    surface_rows = {row["surface"]: row for row in report["surface_rows"]}
    assert surface_rows["Mulligan.json"]["lane"] == "emitted"
    assert surface_rows["GlobalValues.json"]["lane"] == "emitted"
    assert {row["lane"] for row in report["surface_rows"]} <= {
        "emitted",
        "suppressed",
        "source_gap",
        "profile_not_required",
    }


def test_source_autopilot_partial_report_names_first_missing_link():
    bundle = build_source_autopilot_bundle(
        deck_name="ThinDeck",
        deck_identity={
            "deck_name": "ThinDeck",
            "deck_code_hash": "sha256:thin",
            "deck_slug": "thindeck",
            "cards": [
                {"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}
            ],
        },
        source_search_records=[
            {
                "source_url": "https://example.com/thin-decklist",
                "source_title": "Thin Decklist",
                "source_family": "decklist_only",
                "source_visibility": "decklist_only",
                "deck_match": {
                    "deck_name": "ThinDeck",
                    "matched_card_ids": ["CARD_001"],
                },
                "claims": [
                    {
                        "claim_kind": "card_role",
                        "cards": ["CARD_001"],
                        "source_confidence": "medium",
                        "promotion_eligible": False,
                    }
                ],
            }
        ],
        current_date="2026-07-15",
    )

    report = bundle["source_autopilot_report"]
    assert report["semantic_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["runtime_apply_authority"] == "reports/operator_summary.json"
    assert report["source_backed_strong_closure"]["closed"] is False
    assert report["first_missing_source_action_by_card"] == {
        "CARD_001": "add_current_card_specific_runtime_source"
    }
    assert report["first_missing_source_action_by_surface"]
    assert report["card_rows"] == [
        {
            "card_id": "CARD_001",
            "card_name": "Fixture Card",
            "lane": "source_gap",
            "claim_kinds": ["card_role"],
            "source_families": ["metadata"],
            "source_lanes": ["decklist_only"],
            "runtime_surfaces": ["CardID.json"],
        }
    ]
    assert any(row["lane"] == "source_gap" for row in report["surface_rows"])


def test_compact_source_guide_fixtures_exist_and_are_not_raw_page_dumps():
    fixture_dir = Path(__file__).parent / "fixtures" / "source_guides"
    expected = {
        "shadowpriest_current_guide.html",
        "ctapaladin_current_guide.html",
        "piraterogue_current_guide.html",
        "decklist_only_page.html",
        "stats_only_page.html",
    }

    found = {path.name for path in fixture_dir.glob("*.html")}
    assert expected <= found
    for name in expected:
        text = (fixture_dir / name).read_text(encoding="utf-8")
        assert "<html" in text.lower()
        assert len(text.split()) < 250


def test_source_autopilot_default_only_fields_are_preflight_not_runtime_authority():
    bundle = build_source_autopilot_bundle(
        deck_name="ShadowPriest",
        deck_identity=SHADOW_DECK_IDENTITY,
        source_search_records=[_guide_record()],
        current_date="2026-07-16",
    )

    report = bundle["source_autopilot_report"]

    assert report["runtime_apply_authority"] == "reports/operator_summary.json"
    assert report["default_only_runtime_surfaces"] == []
    assert report["default_only_runtime_surface_status"] == (
        "not_evaluated_in_source_preflight"
    )
    assert report["default_only_runtime_surfaces_scope"] == (
        "source_preflight_not_runtime_proof"
    )
    assert report["source_backed_strong_closure"]["diagnostic_only"] is True
