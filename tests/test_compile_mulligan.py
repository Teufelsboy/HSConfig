from pathlib import Path

from hsconfig.compile_mulligan import compile_mulligan
from hsconfig.io import write_json
from hsconfig.validate_package import validate_config_package


def test_compile_mulligan_emits_valid_mulligan_block(tmp_path: Path):
    contract = {
        "deck_name": "Fixture Aggro",
        "mulligan_anchors": [
            {"card_id": "EX1_001", "source_claim_ids": ["claim_a"], "confidence": "source_backed"}
        ],
    }

    result = compile_mulligan(contract)

    assert result["GameCardId"] == "Mulligan"
    assert set(result) == {"GameCardId", "ConfigComment", "Mulligan"}
    assert result["Mulligan"]["values"][0]["mulligan"] == "EX1_001"
    assert result["Mulligan"]["values"][0]["value"] == "hold"
    assert result["Mulligan"]["values"][1]["mulligan"] == "*"
    assert result["Mulligan"]["values"][1]["value"] == "discard"
    assert result["Mulligan"]["values"][0]["source_claim_ids"] == ["claim_a"]

    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(deck_dir / "Mulligan.json", result)

    assert validate_config_package(tmp_path)["status"] == "passed"
