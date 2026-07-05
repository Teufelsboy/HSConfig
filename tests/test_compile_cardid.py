from pathlib import Path

from hsconfig.compile_cardid import compile_cardid_behaviors
from hsconfig.io import write_json
from hsconfig.validate_package import validate_config_package


def test_compile_cardid_behaviors_emit_valid_files_with_provenance(tmp_path: Path):
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
    assert files["EX1_001.json"]["InHandPlayPriority"]["values"][0]["source_claim_ids"] == [
        "claim_a"
    ]
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
