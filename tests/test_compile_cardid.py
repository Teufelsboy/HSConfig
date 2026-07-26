from pathlib import Path

from hsconfig.compile_cardid import compile_cardid_behaviors
from hsconfig.io import write_json
from hsconfig.validate_package import validate_config_package


def test_compile_cardid_does_not_invent_priority_for_report_only_card():
    contract = {
        "deck_name": "Fixture",
        "cards": {
            "EX1_001": {
                "card_id": "EX1_001",
                "name": "Report Only",
                "roles": ["pressure", "tradeable"],
                "confidence": "source_backed_static_semantics",
                "behavior_rows": [],
            }
        },
    }

    payload = compile_cardid_behaviors(contract)["EX1_001.json"]

    assert payload == {
        "GameCardId": "EX1_001",
        "ConfigComment": "Fixture: generated behavior for EX1_001",
    }


def test_compile_cardid_preserves_explicit_priority_row():
    rows = [
        {
            "surface": "CardID.json",
            "surface_family": "CARDID.json",
            "card_id": "EX1_001",
            "behavior_block": "InHandPlayPriority",
            "condition": "*",
            "value": "9",
            "rule_id_suffix": "guide_priority",
            "source_claim_ids": ["claim-priority"],
            "confidence": "guide_backed",
        }
    ]

    payload = compile_cardid_behaviors(
        {"deck_name": "Fixture", "cards": {}},
        rows=rows,
    )["EX1_001.json"]

    assert payload["InHandPlayPriority"]["values"][0]["value"] == "9"


def test_compile_cardid_behaviors_emit_valid_minimal_files_without_explicit_rows(
    tmp_path: Path,
):
    contract = {
        "deck_name": "Fixture Aggro",
        "cards": {
            "EX1_001": {
                "roles": ["battlecry", "pressure"],
                "source_claim_ids": ["claim_a"],
                "confidence": "source_backed",
            },
            "EX1_002": {
                "roles": ["discover"],
                "source_claim_ids": [],
                "confidence": "generic_low_confidence",
            },
        },
    }

    files = compile_cardid_behaviors(contract)

    assert set(files) == {"EX1_001.json", "EX1_002.json"}
    assert files["EX1_001.json"]["GameCardId"] == "EX1_001"
    assert set(files["EX1_001.json"]) == {"GameCardId", "ConfigComment"}
    assert set(files["EX1_002.json"]) == {"GameCardId", "ConfigComment"}

    deck_dir = tmp_path / "CustomConfig" / "deck"
    for filename, payload in files.items():
        write_json(deck_dir / filename, payload)

    assert validate_config_package(tmp_path)["status"] == "passed"


def test_compile_cardid_does_not_derive_behavior_block_from_row_roles():
    contract = {
        "deck_name": "Fixture Aggro",
        "cards": {
            "EX1_001": {
                "roles": ["pressure", "battlecry"],
                "source_claim_ids": ["claim_a"],
                "confidence": "source_backed",
            }
        },
    }
    rows = [
        {
            "surface": "EX1_001.json",
            "surface_family": "CARDID.json",
            "card_id": "EX1_001",
            "intent": "aggressive_card_behavior",
            "roles": ["pressure", "battlecry"],
            "source_claim_ids": ["claim_a"],
        }
    ]

    files = compile_cardid_behaviors(contract, rows=rows)

    assert set(files["EX1_001.json"]) == {"GameCardId", "ConfigComment"}


def test_compile_cardid_does_not_derive_priority_from_confidence_lane():
    contract = {
        "deck_name": "Fixture",
        "cards": {
            "EX1_GUIDE": {
                "roles": ["deck_card"],
                "source_claim_ids": ["claim_guide"],
                "confidence": "guide_backed",
            },
            "EX1_STATIC": {
                "roles": ["deck_card"],
                "source_claim_ids": [],
                "confidence": "source_backed_static_semantics",
            },
            "EX1_GENERIC": {
                "roles": ["deck_card"],
                "source_claim_ids": [],
                "confidence": "generic_low_confidence",
            },
        },
    }

    files = compile_cardid_behaviors(contract)

    for payload in files.values():
        assert set(payload) == {"GameCardId", "ConfigComment"}


def test_compile_cardid_does_not_derive_block_from_targeting_intent():
    contract = {
        "deck_name": "Fixture",
        "cards": {
            "DMF_090": {
                "roles": ["deck_card"],
                "source_claim_ids": [],
                "confidence": "generic_low_confidence",
            }
        },
    }
    rows = [
        {
            "surface": "CardID.json",
            "surface_family": "CARDID.json",
            "card_id": "DMF_090",
            "intent": "prefer_enemy_hero",
            "roles": ["prefer_enemy_hero"],
            "source_claim_ids": ["claim_a"],
            "confidence": "guide_backed",
        }
    ]

    files = compile_cardid_behaviors(contract, rows=rows)

    assert set(files["DMF_090.json"]) == {"GameCardId", "ConfigComment"}


def test_compile_cardid_uses_explicit_behavior_block_rows():
    contract = {
        "deck_name": "Fixture",
        "cards": {
            "EX1_001": {
                "roles": ["deck_card"],
                "source_claim_ids": [],
                "confidence": "generic_low_confidence",
            }
        },
    }
    rows = [
        {
            "surface": "CardID.json",
            "surface_family": "CARDID.json",
            "card_id": "EX1_001",
            "behavior_block": "BeforeOverkilledBonus",
            "rule_id_suffix": "overkill_behavior",
            "condition": "my_target(count(),minion=true) > 0",
            "value": "11",
            "roles": ["overkill"],
            "source_claim_ids": ["claim_overkill"],
            "confidence": "guide_backed",
            "meaningful_runtime_surface": True,
        }
    ]

    files = compile_cardid_behaviors(contract, rows=rows)

    assert files["EX1_001.json"]["BeforeOverkilledBonus"]["values"] == [
        {
            "comment": "Fixture: EX1_001_overkill_behavior",
            "condition": "my_target(count(),minion=true) > 0",
            "value": "11",
        }
    ]


def test_compile_cardid_strips_diagnostic_semantic_score_from_runtime_rows():
    contract = {
        "deck_name": "Fixture",
        "cards": {
            "NX2_019": {
                "roles": ["prefer_enemy_minion"],
                "source_claim_ids": ["mind_sear_source"],
                "confidence": "guide_backed",
            }
        },
    }
    rows = [
        {
            "surface": "CardID.json",
            "surface_family": "CARDID.json",
            "card_id": "NX2_019",
            "behavior_block": "BeforeBattlecryTargetBonus",
            "rule_id_suffix": "prefer_enemy_minion",
            "condition": "*",
            "value": "10",
            "roles": ["prefer_enemy_minion"],
            "source_claim_ids": ["mind_sear_source"],
            "confidence": "guide_backed",
            "meaningful_runtime_surface": True,
            "semantic_score": {
                "band": "high",
                "reason": "conditional_minion_death_burn",
                "profile": "source_claim",
                "matched_signals": ["enemy_hero_damage", "death_condition"],
            },
        }
    ]

    files = compile_cardid_behaviors(contract, rows=rows)

    value_row = files["NX2_019.json"]["BeforeBattlecryTargetBonus"]["values"][0]
    assert value_row == {
        "comment": "Fixture: NX2_019_prefer_enemy_minion",
        "condition": "*",
        "value": "10",
    }
    assert "semantic_score" not in value_row


def test_compile_cardid_does_not_duplicate_role_fallback_for_explicit_block():
    contract = {
        "deck_name": "Fixture",
        "cards": {
            "EX1_002": {
                "roles": ["discover"],
                "source_claim_ids": [],
                "confidence": "generic_low_confidence",
            }
        },
    }
    rows = [
        {
            "surface": "CardID.json",
            "surface_family": "CARDID.json",
            "card_id": "EX1_002",
            "behavior_block": "OnDiscoverCardBonus",
            "rule_id_suffix": "prefer_specific_discover",
            "condition": "my_discover(count(),cardid=EX1_003) > 0",
            "value": "12",
            "roles": ["discover"],
            "source_claim_ids": ["claim_discover"],
            "confidence": "guide_backed",
        }
    ]

    files = compile_cardid_behaviors(contract, rows=rows)

    discover_values = files["EX1_002.json"]["OnDiscoverCardBonus"]["values"]
    assert len(discover_values) == 1
    assert discover_values[0]["condition"] == "my_discover(count(),cardid=EX1_003) > 0"
    assert discover_values[0]["value"] == "12"


def test_compile_cardid_does_not_duplicate_pressure_fallbacks_for_explicit_before_play_block():
    contract = {
        "deck_name": "Fixture",
        "cards": {
            "EX1_PRESSURE": {
                "roles": ["pressure", "prefer_enemy_hero"],
                "source_claim_ids": [],
                "confidence": "generic_low_confidence",
            }
        },
    }
    rows = [
        {
            "surface": "CardID.json",
            "surface_family": "CARDID.json",
            "card_id": "EX1_PRESSURE",
            "behavior_block": "BeforePlayCardBonus",
            "rule_id_suffix": "explicit_before_play",
            "condition": "my_hero(count(),damaged=true) > 0",
            "value": "15",
            "roles": ["pressure", "prefer_enemy_hero"],
            "source_claim_ids": ["claim_before_play"],
            "confidence": "guide_backed",
        }
    ]

    files = compile_cardid_behaviors(contract, rows=rows)

    before_play_values = files["EX1_PRESSURE.json"]["BeforePlayCardBonus"]["values"]
    assert len(before_play_values) == 1
    assert before_play_values[0]["condition"] == "my_hero(count(),damaged=true) > 0"
    assert before_play_values[0]["value"] == "15"


def test_compile_cardid_does_not_emit_tradeable_fallback_from_roles():
    contract = {
        "deck_name": "Fixture",
        "cards": {
            "CARD_TRADEABLE": {
                "roles": ["tradeable"],
                "source_claim_ids": ["claim_tradeable"],
                "confidence": "source_backed_static_semantics",
            }
        },
    }

    files = compile_cardid_behaviors(contract)

    card_file = files["CARD_TRADEABLE.json"]
    assert card_file["GameCardId"] == "CARD_TRADEABLE"
    assert "InHandPlayPriority" not in card_file
    assert "BeforePlayCardBonus" not in card_file


def test_compile_cardid_does_not_emit_dredge_fallback_from_roles():
    contract = {
        "deck_name": "Fixture",
        "cards": {
            "CARD_DREDGE": {
                "roles": ["dredge"],
                "source_claim_ids": ["claim_dredge"],
                "confidence": "source_backed_static_semantics",
            }
        },
    }

    files = compile_cardid_behaviors(contract)

    card_file = files["CARD_DREDGE.json"]
    assert card_file["GameCardId"] == "CARD_DREDGE"
    assert "InHandPlayPriority" not in card_file
    assert "BeforePlayCardBonus" not in card_file
    assert "OnDiscoverCardBonus" not in card_file


def test_compile_cardid_emits_behavior_rows_from_router_for_lowerable_mechanics():
    contract = {
        "deck_name": "Fixture",
        "cards": {
            "CARD_DEATHRATTLE": {
                "roles": ["deathrattle"],
                "source_claim_ids": ["claim_deathrattle_static"],
                "confidence": "source_backed_static_semantics",
            }
        },
    }
    rows = [
        {
            "surface": "CardID.json",
            "surface_family": "CARDID.json",
            "card_id": "CARD_DEATHRATTLE",
            "behavior_block": "BeforePlayCardBonus",
            "rule_id_suffix": "use_deathrattle_according_to_card_text",
            "condition": "*",
            "value": "6",
            "roles": ["deathrattle"],
            "source_claim_ids": ["claim_deathrattle_static"],
            "confidence": "source_backed_static_semantics",
            "meaningful_runtime_surface": True,
        }
    ]

    files = compile_cardid_behaviors(contract, rows=rows)

    before_play_values = files["CARD_DEATHRATTLE.json"]["BeforePlayCardBonus"]["values"]
    assert before_play_values == [
        {
            "comment": "Fixture: CARD_DEATHRATTLE_use_deathrattle_according_to_card_text",
            "condition": "*",
            "value": "6",
        }
    ]


def test_compile_cardid_keeps_report_only_card_files_minimal():
    contract = {
        "deck_name": "Fixture",
        "cards": {
            "CARD_TRADEABLE": {
                "roles": ["tradeable"],
                "source_claim_ids": ["claim_tradeable"],
                "confidence": "source_backed_static_semantics",
            },
            "CARD_DREDGE": {
                "roles": ["dredge"],
                "source_claim_ids": ["claim_dredge"],
                "confidence": "source_backed_static_semantics",
            },
        },
    }

    files = compile_cardid_behaviors(contract)

    for filename in ("CARD_TRADEABLE.json", "CARD_DREDGE.json"):
        card_file = files[filename]
        assert set(card_file) == {"GameCardId", "ConfigComment"}


def test_effect_only_darkbishop_keeps_hero_power_bonus_without_body_priority():
    contract = {
        "deck_name": "ShadowPriest",
        "cards": {
            "SW_448": {
                "name": "Darkbishop Benedictus",
                "roles": [
                    "deckbuilding_modifier",
                    "hero_power_transform",
                    "passive_start_effect",
                    "pressure",
                    "shadowform",
                    "start_of_game_keyword",
                ],
                "source_claim_ids": ["claim-darkbishop-effect"],
                "confidence": "source_backed",
                "behavior_rows": [
                    {
                        "behavior_block": "BeforeUseHeroPowerBonus",
                        "condition": "*",
                        "value": "10",
                        "comment": "ShadowPriest: SW_448_enable_shadow_hero_power",
                        "source_claim_ids": ["claim-darkbishop-effect"],
                    }
                ],
            }
        },
    }

    card_files = compile_cardid_behaviors(contract)
    darkbishop = card_files["SW_448.json"]

    assert "BeforeUseHeroPowerBonus" in darkbishop
    assert "InHandPlayPriority" not in darkbishop
    assert "BeforePlayCardBonus" not in darkbishop


def test_explicit_body_behavior_row_is_not_removed_for_effect_only_card():
    contract = {
        "deck_name": "ShadowPriest",
        "cards": {
            "SW_448": {
                "name": "Darkbishop Benedictus",
                "roles": ["hero_power_transform", "shadowform"],
                "source_claim_ids": ["claim-effect", "claim-body"],
                "behavior_rows": [
                    {
                        "behavior_block": "BeforePlayCardBonus",
                        "condition": "*",
                        "value": "4",
                        "comment": "ShadowPriest: explicit_body_source",
                        "source_claim_ids": ["claim-body"],
                    }
                ],
            }
        },
    }

    card_files = compile_cardid_behaviors(contract)

    assert "BeforePlayCardBonus" in card_files["SW_448.json"]


def test_compile_cardid_preserves_explicit_behavior_row_order_with_same_block():
    rows = [
        {
            "surface": "CardID.json",
            "surface_family": "CARDID.json",
            "card_id": "EX1_ORDER",
            "behavior_block": "OnDiscoverCardBonus",
            "rule_id_suffix": "second_source_claim",
            "condition": "my_discover(count(),cardid=CARD_B) > 0",
            "value": "8",
            "roles": ["discover"],
            "source_claim_ids": ["claim_second"],
            "confidence": "guide_backed",
        },
        {
            "surface": "CardID.json",
            "surface_family": "CARDID.json",
            "card_id": "EX1_ORDER",
            "behavior_block": "OnDiscoverCardBonus",
            "rule_id_suffix": "first_source_claim",
            "condition": "my_discover(count(),cardid=CARD_A) > 0",
            "value": "12",
            "roles": ["discover"],
            "source_claim_ids": ["claim_first"],
            "confidence": "guide_backed",
        },
    ]

    files = compile_cardid_behaviors(
        {
            "deck_name": "Fixture",
            "cards": {
                "EX1_ORDER": {
                    "roles": ["discover"],
                    "source_claim_ids": [],
                    "confidence": "source_backed",
                }
            },
        },
        rows=rows,
    )

    discover_values = files["EX1_ORDER.json"]["OnDiscoverCardBonus"]["values"]
    assert [row["comment"] for row in discover_values] == [
        "Fixture: EX1_ORDER_second_source_claim",
        "Fixture: EX1_ORDER_first_source_claim",
    ]
    assert [row["value"] for row in discover_values] == ["8", "12"]
