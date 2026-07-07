from pathlib import Path

from hsconfig.compile_cardid import compile_cardid_behaviors
from hsconfig.io import write_json
from hsconfig.validate_package import validate_config_package


def test_compile_cardid_behaviors_emit_valid_files_with_clean_runtime_rows(tmp_path: Path):
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
    priority_row = files["EX1_001.json"]["InHandPlayPriority"]["values"][0]
    assert set(priority_row) == {"comment", "condition", "value"}
    assert "BeforeBattlecryTargetBonus" in files["EX1_001.json"]
    assert "OnDiscoverCardBonus" in files["EX1_002.json"]

    deck_dir = tmp_path / "CustomConfig" / "deck"
    for filename, payload in files.items():
        write_json(deck_dir / filename, payload)

    assert validate_config_package(tmp_path)["status"] == "passed"


def test_compile_cardid_behaviors_preserves_roles_when_surface_rows_are_passed():
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

    assert "BeforePlayCardBonus" in files["EX1_001.json"]
    assert "BeforeBattlecryTargetBonus" in files["EX1_001.json"]


def test_compile_cardid_treats_backed_confidence_lanes_as_stronger_than_generic():
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

    assert files["EX1_GUIDE.json"]["InHandPlayPriority"]["values"][0]["value"] == "7"
    assert files["EX1_STATIC.json"]["InHandPlayPriority"]["values"][0]["value"] == "7"
    assert files["EX1_GENERIC.json"]["InHandPlayPriority"]["values"][0]["value"] == "5"


def test_compile_cardid_routes_targeting_intent_to_specific_bonus_block():
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

    assert "BeforePlayCardBonus" in files["DMF_090.json"]
    bonus_values = files["DMF_090.json"]["BeforePlayCardBonus"]["values"]
    assert len(bonus_values) == 1
    assert bonus_values[0]["value"] == "12"


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
