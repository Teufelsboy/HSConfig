import json

import pytest

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.card_behavior_router import route_card_behavior_claims
from hsconfig.compile_cardid import compile_cardid_behaviors
from hsconfig.compile_mulligan import compile_mulligan
from hsconfig.gameplan_contract import build_gameplan_contract
from hsconfig.source_claim_gap_report import build_source_claim_gap_report
from hsconfig.guide_claim_builder import build_guide_claim_bundle
from hsconfig.mulligan_plan import build_mulligan_plan
from hsconfig.research_contract import build_research_contract_bundle
from hsconfig.operator_summary import build_operator_summary
from hsconfig.source_document_builder import build_source_document_bundle


def test_operator_summary_exposes_source_quality_without_apply_block():
    operator = build_operator_summary(
        validation_report={
            "valid": True,
            "errors": [],
            "warnings": [],
            "summary": {},
        },
        config_readiness_report={
            "summary": {
                "cards_total": 3,
                "cards_ready": 3,
                "cards_missing": 0,
            },
            "card_rows": {},
        },
        source_claim_gap_report={
            "summary": {
                "source_quality_lane_counts": {
                    "guide_backed": 1,
                    "source_backed_static_semantics": 1,
                    "generic_low_confidence": 1,
                },
                "cards_with_generic_low_confidence": 1,
                "cards_with_contract_gap": 0,
                "next_claim_kind_counts": {"card_role": 1},
            }
        },
    )

    assert operator["source_claim_quality_summary"] == {
        "source_quality_lane_counts": {
            "generic_low_confidence": 1,
            "guide_backed": 1,
            "source_backed_static_semantics": 1,
        },
        "cards_with_generic_low_confidence": 1,
        "cards_with_contract_gap": 0,
        "next_claim_kind_counts": {"card_role": 1},
        "non_blocking": True,
    }
    assert operator["runtime_apply_contract"]["apply_authority"] == "reports/operator_summary.json"


@pytest.mark.parametrize(
    ("family", "claims"),
    [
        (
            "targeting",
            [
                {
                    "claim_kind": "targeting_rule",
                    "cards": ["CARD_A"],
                    "target_scope": "enemy_hero",
                    "evidence_text_short": "Target the enemy hero.",
                    "source_confidence": "high",
                },
                {
                    "claim_kind": "targeting_rule",
                    "cards": ["CARD_A"],
                    "target_scope": "enemy_minion",
                    "evidence_text_short": "Target an enemy minion.",
                    "source_confidence": "high",
                },
            ],
        ),
        (
            "combo_timing",
            [
                {
                    "claim_kind": "combo_sequence",
                    "cards": ["CARD_A", "CARD_B"],
                    "sequence": ["CARD_A", "CARD_B"],
                    "timing_kind": "same_turn",
                    "evidence_text_short": "Play the combo in the same turn.",
                    "source_confidence": "high",
                },
                {
                    "claim_kind": "combo_sequence",
                    "cards": ["CARD_A", "CARD_B"],
                    "sequence": ["CARD_A", "CARD_B"],
                    "timing_kind": "cross_turn",
                    "evidence_text_short": "Set up the combo across turns.",
                    "source_confidence": "high",
                },
            ],
        ),
        (
            "option_choice",
            [
                {
                    "claim_kind": "discover_choice",
                    "cards": ["CARD_A"],
                    "option_card_id": "OPTION_A",
                    "evidence_text_short": "Discover Option A.",
                    "source_confidence": "high",
                },
                {
                    "claim_kind": "discover_choice",
                    "cards": ["CARD_A"],
                    "option_card_id": "OPTION_B",
                    "evidence_text_short": "Discover Option B.",
                    "source_confidence": "high",
                },
            ],
        ),
        (
            "role_vs_known_bad_pattern",
            [
                {
                    "claim_kind": "card_role",
                    "cards": ["CARD_A"],
                    "stance": "prefer_enemy_minion",
                    "evidence_text_short": "Use this card to target enemy minions.",
                    "source_confidence": "high",
                },
                {
                    "claim_kind": "known_bad_pattern",
                    "cards": ["CARD_A"],
                    "stance": "do_not_target_enemy_minion",
                    "evidence_text_short": "Do not target enemy minions with this card.",
                    "source_confidence": "high",
                },
            ],
        ),
    ],
)
def test_broader_claim_conflicts_remain_visible_without_blocking_apply(tmp_path, family, claims):
    deck_identity = {
        "deck_name": "Conflict Fixture",
        "cards": [
            {"card_id": "CARD_A", "count": 2},
            {"card_id": "CARD_B", "count": 2},
        ],
    }
    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=[
            {
                "source_url": "https://example.invalid/conflicts",
                "source_title": "Conflict Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-07T00:00:00Z",
                "claims": claims,
            }
        ],
    )
    conflicts = bundle["claim_conflict_report"]["conflicts"]
    assert [conflict["conflict_family"] for conflict in conflicts] == [family]
    assert conflicts[0]["resolution"] == "downgrade_to_report_visible_conflict"

    operator = build_operator_summary(
        technical_validation={"status": "passed", "errors": [], "warnings": []},
        claim_conflict_report=bundle["claim_conflict_report"],
    )
    package = tmp_path / family
    deck_dir = package / "CustomConfig" / "deck"
    reports = package / "reports"
    deck_dir.mkdir(parents=True)
    reports.mkdir()
    (deck_dir / "GlobalValues.json").write_text("{}", encoding="utf-8")
    (deck_dir / "Mulligan.json").write_text('{"mulligan": []}', encoding="utf-8")
    (reports / "input_manifest.json").write_text('{"deck_name": "deck"}', encoding="utf-8")
    operator["generated_files"] = [
        "CustomConfig/deck/GlobalValues.json",
        "CustomConfig/deck/Mulligan.json",
    ]
    (reports / "operator_summary.json").write_text(
        json.dumps(operator), encoding="utf-8"
    )

    gate = evaluate_apply_gate(package)
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert gate["allowed"] is True


def test_static_semantics_adds_visible_claims_for_common_mechanics():
    result = build_guide_claim_bundle(
        deck_identity={"deck_name": "Static Mechanics"},
        card_metadata=[
            {
                "id": "DISCOVER_CARD",
                "card_id": "DISCOVER_CARD",
                "name": "Discover Card",
                "text": "Discover a spell.",
            },
            {
                "id": "SILENCE_CARD",
                "card_id": "SILENCE_CARD",
                "name": "Silence Card",
                "text": "Silence a minion.",
            },
            {
                "id": "WEAPON_CARD",
                "card_id": "WEAPON_CARD",
                "name": "Weapon Card",
                "text": "Equip a 3/2 weapon.",
            },
        ],
        source_documents=[],
    )

    claims = result["claims"]
    by_card = {
        card_id: [
            claim
            for claim in claims
            if card_id in claim.get("cards", [])
            and claim.get("claim_readiness") == "source_backed_static_semantics"
        ]
        for card_id in ["DISCOVER_CARD", "SILENCE_CARD", "WEAPON_CARD"]
    }

    assert any(claim["claim_kind"] == "discover_choice" for claim in by_card["DISCOVER_CARD"])
    assert any(claim["claim_kind"] == "mechanic_usage" for claim in by_card["SILENCE_CARD"])
    assert any(claim["claim_kind"] == "mechanic_usage" for claim in by_card["WEAPON_CARD"])
    static_claims = [claim for claims_for_card in by_card.values() for claim in claims_for_card]
    assert all(not claim["claim_kind"].startswith("globalvalue_") for claim in static_claims)
    assert all(claim["claim_kind"] not in {"mulligan_keep", "mulligan_discard"} for claim in static_claims)
    assert all(claim["mechanic_family"] for claim in static_claims)
    assert next(
        claim for claim in by_card["DISCOVER_CARD"] if claim["claim_kind"] == "discover_choice"
    )["evidence_text_short"] == "Static card text contains discover."
    assert next(
        claim for claim in by_card["SILENCE_CARD"] if claim["claim_kind"] == "mechanic_usage"
    )["evidence_text_short"] == "Silence a minion."


def test_generic_static_target_text_stays_diagnostic_not_runtime_target_bonus():
    card_metadata = {
        "SILENCE_CARD": {
            "card_id": "SILENCE_CARD",
            "name": "Silence Card",
            "text": "Silence a minion.",
        }
    }
    result = build_guide_claim_bundle(
        deck_identity={"deck_name": "Static Target Mechanics"},
        card_metadata=card_metadata,
        source_documents=[],
    )

    claims = result["claims"]
    silence_claim = next(
        claim
        for claim in claims
        if claim["cards"] == ["SILENCE_CARD"] and claim.get("mechanic") == "silence"
    )
    behavior_plan = route_card_behavior_claims(claims)
    contract = build_gameplan_contract(
        {"deck_name": "Static Target Mechanics", "cards": [{"card_id": "SILENCE_CARD"}]},
        card_metadata,
        claims,
    )
    files = compile_cardid_behaviors(contract, rows=behavior_plan["rows"])

    assert silence_claim["claim_readiness"] == "source_backed_static_semantics"
    assert silence_claim["trust_ceiling"] == "report_only"
    assert behavior_plan["rows"] == []
    assert behavior_plan["suppressed"][0]["reason"] == "claim_not_runtime_lowerable"
    assert "BeforeBattlecryTargetBonus" not in files["SILENCE_CARD.json"]


def test_generic_hero_power_text_does_not_infer_transform_or_runtime_bonus():
    result = build_guide_claim_bundle(
        deck_identity={"deck_name": "Hero Power Mechanics"},
        card_metadata={
            "HERO_POWER_DRAW": {
                "name": "Hero Power Draw",
                "text": "After you use your Hero Power, draw a card.",
            }
        },
        source_documents=[],
    )

    claims = result["claims"]
    behavior_plan = route_card_behavior_claims(claims)

    assert not any(
        claim["claim_kind"] == "hero_power_transform" and claim["cards"] == ["HERO_POWER_DRAW"]
        for claim in claims
    )
    assert not any(
        row.get("behavior_block") == "BeforeUseHeroPowerBonus"
        for row in behavior_plan["rows"]
    )


def test_static_semantics_deduplicates_overlapping_weapon_rules():
    result = build_guide_claim_bundle(
        deck_identity={"deck_name": "Weapon Mechanics"},
        card_metadata={
            "WEAPON_CARD": {
                "name": "Weapon Card",
                "text": "Equip a 3/2 weapon.",
            }
        },
        source_documents=[],
    )

    weapon_claims = [
        claim
        for claim in result["claims"]
        if claim["cards"] == ["WEAPON_CARD"]
        and claim["claim_kind"] == "mechanic_usage"
        and claim["mechanic"] == "weapon"
    ]

    assert len(weapon_claims) == 1


def test_static_semantics_keeps_specialized_hero_power_claim_authoritative():
    result = build_guide_claim_bundle(
        deck_identity={"deck_name": "Hero Power Mechanics"},
        card_metadata={
            "HERO_POWER_CARD": {
                "name": "Hero Power Card",
                "text": "Start of Game: Enter Shadowform. Your hero power becomes Mind Spike.",
            }
        },
        source_documents=[],
    )

    hero_power_claims = [
        claim
        for claim in result["claims"]
        if claim["cards"] == ["HERO_POWER_CARD"]
        and claim["claim_kind"] == "hero_power_transform"
    ]

    assert len(hero_power_claims) == 1
    assert hero_power_claims[0]["mechanic"] == "hero_power_transform"
    assert hero_power_claims[0]["stance"] == "enable_transformed_hero_power"


def test_static_semantics_adds_choose_one_choice_claim():
    result = build_guide_claim_bundle(
        deck_identity={"deck_name": "Choose One Mechanics"},
        card_metadata={
            "CHOOSE_ONE_CARD": {
                "name": "Choose One Card",
                "text": "Choose One: Draw a card or gain 2 Armor.",
            }
        },
        source_documents=[],
    )

    choose_one_claims = [
        claim
        for claim in result["claims"]
        if claim["cards"] == ["CHOOSE_ONE_CARD"]
        and claim["claim_kind"] == "choose_one_choice"
        and claim["mechanic"] == "choose_one"
    ]

    assert len(choose_one_claims) == 1


def test_source_claim_gap_report_classifies_package_builder_inputs_by_quality():
    report = build_source_claim_gap_report(
        deck_name="Production Shape",
        config_readiness_report={
            "cards": {
                "GUIDE": {
                    "card_id": "GUIDE",
                    "name": "Guide-backed Card",
                    "readiness_lane": "runtime_emitted",
                    "source_depth_lane": "closed",
                    "first_missing_link": "none",
                    "runtime_surfaces": ["GUIDE.json"],
                },
                "STATIC": {
                    "card_id": "STATIC",
                    "name": "Static Card",
                    "readiness_lane": "runtime_emitted",
                    "source_depth_lane": "closed",
                    "first_missing_link": "none",
                    "runtime_surfaces": ["STATIC.json"],
                },
                "UNCOVERED": {
                    "card_id": "UNCOVERED",
                    "name": "Uncovered Card",
                    "readiness_lane": "generic_low_confidence",
                    "source_depth_lane": "source_claim_gap",
                    "first_missing_link": "needs_guide_claim",
                    "runtime_surfaces": [],
                },
                "LOWERING": {
                    "card_id": "LOWERING",
                    "name": "Lowering Gap",
                    "readiness_lane": "report_only_supported",
                    "source_depth_lane": "runtime_surface_gap",
                    "first_missing_link": "needs_runtime_surface",
                    "runtime_surfaces": ["Mulligan.json"],
                },
            }
        },
        claim_coverage_report={
            "cards": {
                "GUIDE": {"coverage_status": "guide_backed", "source_claim_ids": ["guide"]},
                "STATIC": {
                    "coverage_status": "static_semantics_backfilled",
                    "source_claim_ids": ["static"],
                },
                "UNCOVERED": {
                    "coverage_status": "uncovered_low_confidence",
                    "source_claim_ids": [],
                },
                "LOWERING": {"coverage_status": "guide_backed", "source_claim_ids": ["lower"]},
            }
        },
        card_behavior_plan={"rows": []},
        mulligan_plan={"rules": []},
        combo_plan={"combos": []},
    )

    assert report["summary"]["source_quality_lane_counts"] == {
        "contract_gap": 1,
        "generic_low_confidence": 1,
        "guide_backed": 1,
        "source_backed_static_semantics": 1,
    }
    assert report["summary"]["cards_with_generic_low_confidence"] == 1
    assert report["summary"]["cards_with_contract_gap"] == 1
    assert report["cards"]["UNCOVERED"]["source_quality_lane"] == "generic_low_confidence"
    assert report["cards"]["LOWERING"]["source_quality_lane"] == "contract_gap"


def test_source_claim_gap_report_exposes_quality_lanes_for_every_card():
    report = build_source_claim_gap_report(
        deck_cards=[
            {"card_id": "A", "name": "Guide Card"},
            {"card_id": "B", "name": "Static Card"},
            {"card_id": "C", "name": "Thin Card"},
        ],
        claim_coverage_report={
            "card_rows": {
                "A": {
                    "source_depth_lane": "guide_backed",
                    "claim_kinds": ["mulligan_keep"],
                },
                "B": {
                    "source_depth_lane": "source_backed_static_semantics",
                    "claim_kinds": ["mechanic_usage"],
                },
                "C": {
                    "source_depth_lane": "generic_low_confidence",
                    "claim_kinds": [],
                },
            }
        },
        source_contract_audit={
            "card_rows": {
                "A": {"first_missing_link": "closed", "runtime_surfaces": ["Mulligan.json"]},
                "B": {"first_missing_link": "closed", "runtime_surfaces": ["B.json"]},
                "C": {"first_missing_link": "missing_source_claim", "runtime_surfaces": []},
            }
        },
    )

    assert report["summary"]["source_quality_lane_counts"] == {
        "generic_low_confidence": 1,
        "guide_backed": 1,
        "source_backed_static_semantics": 1,
    }
    assert report["summary"]["cards_with_generic_low_confidence"] == 1
    assert report["summary"]["cards_with_contract_gap"] == 0
    assert report["summary"]["next_claim_kind_counts"] == {"card_role": 1}
    assert report["card_rows"]["C"]["source_quality_lane"] == "generic_low_confidence"
    assert report["card_rows"]["C"]["recommended_next_claim_kind"] == "card_role"
    assert report["card_rows"]["C"]["recommended_next_source_action"] == (
        "add a card-specific guide claim or source-backed static semantic claim"
    )


def test_start_of_game_hero_power_effect_does_not_infer_mulligan_keep():
    deck_identity = {
        "deck_name": "ShadowPriest",
        "cards": [
            {
                "card_id": "SW_448",
                "count": 1,
                "name": "Darkbishop Benedictus",
            }
        ],
    }
    darkbishop = {
        "card_id": "SW_448",
        "id": "SW_448",
        "name": "Darkbishop Benedictus",
        "text": (
            "Start of Game: If the spells in your deck are all Shadow, "
            "enter Shadowform."
        ),
        "semantic_families": ["start_of_game", "hero_power_transform"],
    }
    result = build_guide_claim_bundle(
        deck_identity=deck_identity,
        card_metadata={"SW_448": darkbishop},
        source_documents=[
            {
                "source_url": "local://shadowpriest-test",
                "source_title": "ShadowPriest effect source",
                "source_family": "card_text",
                "retrieved_at": "2026-07-12T00:00:00Z",
                "deck_name": "ShadowPriest",
                "claims": [
                    {
                        "claim_kind": "hero_power_transform",
                        "cards": ["SW_448"],
                        "evidence_text_short": "Start of Game changes the Hero Power.",
                        "source_confidence": "high",
                    }
                ],
            }
        ],
    )

    claims = result["claims"]
    assert not any(
        claim["claim_kind"] == "mulligan_keep" and "SW_448" in claim.get("cards", [])
        for claim in claims
    )
    hero_power_claims = [
        claim
        for claim in claims
        if claim["claim_kind"] == "hero_power_transform" and claim["cards"] == ["SW_448"]
    ]

    assert len(hero_power_claims) == 1
    hero_power_claim = hero_power_claims[0]
    assert hero_power_claim["source_url"] == "local://shadowpriest-test"
    assert hero_power_claim["source_family"] == "card_text"
    assert hero_power_claim["evidence_text_short"] == "Start of Game changes the Hero Power."

    research_bundle = build_research_contract_bundle(
        deck_identity,
        {"cards": [darkbishop]},
        claims,
    )
    contract = build_gameplan_contract(
        deck_identity,
        {"cards": [darkbishop]},
        claims,
        research_bundle=research_bundle,
    )
    card_behavior_plan = route_card_behavior_claims(claims)
    mulligan_plan = build_mulligan_plan(
        deck_name="ShadowPriest",
        claims=claims,
        card_roles=research_bundle["card_role_map"],
    )
    runtime_mulligan = compile_mulligan(
        {"deck_name": "ShadowPriest", "mulligan_plan": mulligan_plan}
    )

    assert "hero_power_transform" in contract["cards"]["SW_448"]["roles"]
    contract_hero_power_claim = next(
        claim
        for claim in contract["source_claims"]
        if claim["claim_kind"] == "hero_power_transform" and claim["cards"] == ["SW_448"]
    )
    assert contract_hero_power_claim["url"] == "local://shadowpriest-test"
    assert contract_hero_power_claim["claim"] == "Start of Game changes the Hero Power."
    assert contract_hero_power_claim["claim_id"] in contract["cards"]["SW_448"]["source_claim_ids"]
    card_behavior_row = next(
        row
        for row in card_behavior_plan["card_rows"]["SW_448"]
        if row["claim_id"] == hero_power_claim["claim_id"]
    )
    assert card_behavior_row["behavior_block"] == "BeforeUseHeroPowerBonus"
    assert card_behavior_row["source_claim_ids"] == [hero_power_claim["claim_id"]]
    assert "local://shadowpriest-test" in card_behavior_row["source_refs"]

    assert not any(
        rule["card"] == "SW_448" and rule["action"] == "hold"
        for rule in mulligan_plan["rules"]
    )
    assert not any(
        row["mulligan"] == "SW_448" and row["value"] == "hold"
        for row in runtime_mulligan["Mulligan"]["values"]
    )
