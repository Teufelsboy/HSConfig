from hsconfig.gameplan_contract import build_gameplan_contract
from hsconfig.surface_intent import build_surface_intent


def test_surface_intent_routes_normal_runtime_surfaces_from_contract():
    contract = {
        "cards": {
            "EX1_001": {
                "roles": ["mulligan_anchor", "pressure"],
                "source_claim_ids": ["claim_a"],
                "confidence": "source_backed",
            },
            "EX1_002": {
                "roles": ["discover"],
                "source_claim_ids": [],
                "confidence": "generic_low_confidence",
            },
        },
        "mulligan_anchors": [{"card_id": "EX1_001", "source_claim_ids": ["claim_a"]}],
        "combos": [
            {
                "rule_id": "combo_1",
                "cards": ["EX1_001", "EX1_002"],
                "timing": "same_turn",
            }
        ],
        "policies": {
            "presume": [{"rule_id": "presume_1", "value": "opponent_is_slow"}],
            "concede": [{"rule_id": "concede_1", "value": "lethal_unavailable"}],
        },
    }

    intent = build_surface_intent(contract)

    surfaces = {(row.get("card_id"), row["surface"]) for row in intent["rows"]}
    assert (None, "GlobalValues.json") in surfaces
    assert ("EX1_001", "Mulligan.json") in surfaces
    assert ("EX1_001", "EX1_001.json") in surfaces
    assert ("EX1_002", "EX1_002.json") in surfaces
    assert (None, "Combo.json") in surfaces
    assert (None, "Presume.json") not in surfaces
    assert (None, "Concede.json") not in surfaces
    assert "GlobalValues.json" in intent["required_surfaces"]
    assert "Combo.json" in intent["optional_surfaces"]
    assert "Presume.json" not in intent["optional_surfaces"]
    assert "Concede.json" not in intent["optional_surfaces"]


def test_report_only_combo_does_not_make_combo_surface_expected():
    contract = {
        "deck_name": "ShadowPriest",
        "cards": {},
        "combos": [
            {
                "claim_id": "combo-report-only",
                "cards": ["DS1_233", "VAC_419"],
                "suppressed_reason": "missing_timing",
            }
        ],
    }

    intent = build_surface_intent(contract)

    assert "Combo.json" not in intent.get("required_surfaces", [])
    assert "Combo.json" not in intent.get("optional_surfaces", [])


def test_surface_intent_keeps_timed_combo_from_gameplan_contract():
    contract = build_gameplan_contract(
        {"deck_name": "Fixture", "cards": [{"card_id": "CARD_A"}, {"card_id": "CARD_B"}]},
        {
            "cards": [
                {"card_id": "CARD_A", "name": "Setup", "mechanic_families": []},
                {"card_id": "CARD_B", "name": "Payoff", "mechanic_families": []},
            ]
        },
        {
            "claims": [
                {
                    "claim_id": "combo_same_turn",
                    "source": "guide",
                    "claim": "Play Setup then Payoff as a combo.",
                    "claim_type": "combo_sequence",
                    "claim_kind": "combo_sequence",
                    "cards": ["CARD_A", "CARD_B"],
                    "timing_kind": "same_turn",
                    "values": ["10", "10"],
                    "confidence": "source_backed",
                }
            ]
        },
    )

    intent = build_surface_intent(contract)

    assert contract["combos"][0]["timing_kind"] == "same_turn"
    assert "Combo.json" in intent["optional_surfaces"]


def test_surface_intent_does_not_route_legacy_policy_surfaces_even_when_flagged():
    contract = {
        "cards": {},
        "policies": {
            "presume": [{"rule_id": "presume_1", "value": "opponent_is_slow"}],
            "concede": [{"rule_id": "concede_1", "value": "lethal_unavailable"}],
        },
        "legacy_policy_surfaces_enabled": True,
    }

    intent = build_surface_intent(contract)

    surfaces = {(row.get("card_id"), row["surface"]) for row in intent["rows"]}
    assert (None, "Presume.json") not in surfaces
    assert (None, "Concede.json") not in surfaces
    assert "Presume.json" not in intent["optional_surfaces"]
    assert "Concede.json" not in intent["optional_surfaces"]


def test_surface_intent_separates_minimum_load_safe_and_rich_optional_surfaces():
    report = build_surface_intent(
        {
            "deck_name": "Intent",
            "cards": {
                "CARD_001": {"card_id": "CARD_001", "roles": ["deck_card"]},
            },
            "mulligan_plan": {"rules": []},
            "card_behavior_plan": {"rows": [{"card_id": "CARD_001"}]},
            "combo_plan": {"combos": []},
        }
    )

    assert "GlobalValues.json" in report["minimum_required_runtime_surfaces"]
    assert "Mulligan.json" in report["minimum_required_runtime_surfaces"]
    assert "CARD_001.json" in report["rich_optional_runtime_surfaces"]
    assert "Presume.json" not in report["minimum_required_runtime_surfaces"]
    assert "Concede.json" not in report["minimum_required_runtime_surfaces"]


def test_surface_intent_projects_specific_card_intent_when_known():
    report = build_surface_intent(
        {
            "cards": {
                "LOC_001": {
                    "roles": ["location"],
                    "source_claim_ids": ["claim_location"],
                    "confidence": "source_backed",
                    "semantic_families": ["location"],
                },
                "DRAW_001": {
                    "roles": ["cycle"],
                    "source_claim_ids": ["claim_draw"],
                    "confidence": "source_backed",
                },
                "GENERIC_001": {
                    "roles": ["tradeable"],
                    "source_claim_ids": [],
                    "confidence": "generic_low_confidence",
                    "semantic_families": ["tradeable"],
                },
            }
        }
    )

    rows = {row["card_id"]: row for row in report["rows"] if row.get("card_id")}

    assert rows["LOC_001"]["intent"] == "location_tempo"
    assert rows["LOC_001"]["intent_source"] == "card_intent_taxonomy"
    assert rows["DRAW_001"]["intent"] == "draw_cycle"
    assert rows["DRAW_001"]["intent_source"] == "card_intent_taxonomy"
    assert rows["GENERIC_001"]["intent"] == "aggressive_card_behavior"
    assert rows["GENERIC_001"]["intent_source"] == "fallback"


def test_surface_intent_projects_shadowpriest_specific_card_intents_without_fallback():
    report = build_surface_intent(
        {
            "cards": {
                "DS1_233": {
                    "name": "Mind Blast",
                    "roles": ["combo_piece", "damage", "pressure", "spell"],
                    "semantic_families": ["damage", "spell"],
                    "mechanic_families": ["damage", "spell"],
                },
                "GVG_009": {
                    "name": "Shadowbomber",
                    "roles": ["battlecry", "damage", "minion", "pressure"],
                    "semantic_families": ["battlecry", "damage", "minion"],
                    "mechanic_families": ["battlecry", "damage", "minion"],
                },
                "NX2_019": {
                    "name": "Mind Sear",
                    "roles": ["damage", "pressure", "spell"],
                    "semantic_families": ["damage", "spell"],
                    "mechanic_families": ["damage", "spell"],
                },
                "SCH_514": {
                    "name": "Raise Dead",
                    "roles": ["damage", "pressure", "spell"],
                    "semantic_families": ["damage", "spell"],
                    "mechanic_families": ["damage", "spell"],
                },
                "SW_446": {
                    "name": "Voidtouched Attendant",
                    "roles": ["aura", "damage", "minion", "pressure"],
                    "semantic_families": ["aura", "damage", "minion"],
                    "mechanic_families": ["damage", "minion"],
                },
                "TOY_381": {
                    "name": "Papercraft Angel",
                    "roles": ["aura", "combo_piece", "hero_power", "minion", "pressure"],
                    "semantic_families": ["aura", "hero_power", "minion"],
                    "mechanic_families": ["minion"],
                },
                "VAC_419": {
                    "name": "Acupuncture",
                    "roles": ["combo_piece", "damage", "pressure", "spell"],
                    "semantic_families": ["damage", "spell"],
                    "mechanic_families": ["damage", "spell"],
                },
                "VAC_512": {
                    "name": "Brain Masseuse",
                    "roles": ["damage", "minion", "pressure", "trigger_visual"],
                    "semantic_families": ["damage", "minion", "trigger_visual"],
                    "mechanic_families": ["damage", "minion"],
                },
                "YOD_032": {
                    "name": "Frenzied Felwing",
                    "roles": ["damage", "minion", "pressure"],
                    "semantic_families": ["damage", "minion"],
                    "mechanic_families": ["damage", "minion"],
                },
            }
        }
    )

    rows = {row["card_id"]: row for row in report["rows"] if row.get("card_id")}

    assert rows["DS1_233"]["intent"] == "direct_enemy_hero_burn"
    assert rows["GVG_009"]["intent"] == "reciprocal_hero_burn"
    assert rows["NX2_019"]["intent"] == "conditional_minion_death_burn"
    assert rows["SCH_514"]["intent"] == "self_damage_resource"
    assert rows["SW_446"]["intent"] == "damage_aura_amplifier"
    assert rows["TOY_381"]["intent"] == "hero_power_cost_aura"
    assert rows["VAC_419"]["intent"] == "reciprocal_hero_burn"
    assert rows["VAC_512"]["intent"] == "self_damage_liability_body"
    assert rows["YOD_032"]["intent"] == "opponent_damage_discount_tempo"
    assert all(row["intent_source"] == "card_intent_taxonomy" for row in rows.values())
