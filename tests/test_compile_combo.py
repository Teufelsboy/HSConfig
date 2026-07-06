from pathlib import Path

import pytest

from hsconfig.compile_combo import compile_combo
from hsconfig.io import write_json
from hsconfig.validate_package import validate_config_package


def test_compile_combo_returns_valid_segment_parity_payload(tmp_path: Path):
    contract = {
        "deck_name": "Fixture Aggro",
        "combos": [
            {
                "rule_id": "combo_1",
                "cards": ["EX1_001", "EX1_002"],
                "values": ["12", "8"],
                "source_claim_ids": ["claim_a"],
            }
        ],
    }

    combo = compile_combo(contract)

    assert combo is not None
    row = combo["ComboList"]["values"][0]
    assert row["combo"] == "EX1_001>>EX1_002"
    assert row["value"] == "12>>8"
    assert set(row) == {"comment", "condition", "combo", "value"}

    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(deck_dir / "Combo.json", combo)

    assert validate_config_package(tmp_path)["status"] == "passed"


def test_compile_combo_returns_none_without_combos():
    assert compile_combo({"deck_name": "Fixture", "combos": []}) is None


def test_compile_combo_rejects_invalid_segment_parity():
    with pytest.raises(ValueError, match="Invalid combo sequence"):
        compile_combo(
            {
                "deck_name": "Fixture",
                "combos": [{"rule_id": "bad", "cards": ["EX1_001", "EX1_002"], "values": ["10"]}],
            }
        )


def test_compile_combo_accepts_combo_plan_rows():
    combo = compile_combo(
        {"deck_name": "Fixture"},
        sequences=[
            {
                "rule_id": "combo_plan_1",
                "cards": ["CARD_A", "CARD_B"],
                "values": ["10", "10"],
                "operator": ">>",
                "source_claim_ids": ["claim_a"],
            }
        ],
    )

    assert combo is not None
    assert combo["ComboList"]["values"][0] == {
        "comment": "Fixture: combo_plan_1",
        "condition": "*",
        "combo": "CARD_A>>CARD_B",
        "value": "10>>10",
    }
