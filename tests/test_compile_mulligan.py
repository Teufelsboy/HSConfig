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
    assert set(result["Mulligan"]["values"][0]) == {"comment", "mulligan", "condition", "value"}

    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(deck_dir / "Mulligan.json", result)

    assert validate_config_package(tmp_path)["status"] == "passed"


def test_compile_mulligan_consumes_plan_and_omits_lone_wildcard(tmp_path: Path):
    contract = {
        "deck_name": "Fixture",
        "mulligan_plan": {
            "rules": [],
            "quality": {"blocked_reason": "no_source_backed_mulligan_keeps"},
        },
    }

    result = compile_mulligan(contract)

    assert result["Mulligan"]["values"] == []

    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(deck_dir / "Mulligan.json", result)
    assert validate_config_package(tmp_path)["status"] == "passed"


def test_compile_mulligan_emits_drop_and_plus_selectors_in_plan_order():
    config = compile_mulligan(
        {
            "deck_name": "Fixture",
            "mulligan_plan": {
                "rules": [
                    {
                        "rule_id": "keep_drop1",
                        "selector_kind": "drop_n",
                        "selector": "DROP1",
                        "action": "hold",
                        "condition": "*",
                    },
                    {
                        "rule_id": "keep_combo",
                        "selector_kind": "plus_combo",
                        "selector": "CARD_A + CARD_B",
                        "action": "hold",
                        "condition": "coin",
                    },
                    {
                        "rule_id": "throw_card_c",
                        "selector_kind": "card",
                        "selector": "CARD_C",
                        "action": "discard",
                        "condition": "*",
                    },
                ]
            },
        }
    )

    rows = config["Mulligan"]["values"]
    assert [row["mulligan"] for row in rows] == ["DROP1", "CARD_A + CARD_B", "CARD_C"]
    assert rows[1]["condition"] == "coin"
    assert rows[2]["value"] == "discard"


def test_compile_mulligan_blocks_lone_wildcard_discard():
    config = compile_mulligan(
        {
            "deck_name": "Fixture",
            "mulligan_plan": {
                "rules": [
                    {
                        "rule_id": "discard_all",
                        "selector_kind": "wildcard",
                        "selector": "*",
                        "action": "discard",
                        "condition": "*",
                    }
                ]
            },
        }
    )

    assert config["Mulligan"]["values"] == []
