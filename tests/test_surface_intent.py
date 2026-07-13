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
        "combos": [{"rule_id": "combo_1", "cards": ["EX1_001", "EX1_002"]}],
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
