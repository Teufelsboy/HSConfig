import json
from pathlib import Path

from hsconfig.compile_globalvalues import compile_globalvalues
from hsconfig.io import write_json
from hsconfig.validate_package import validate_config_package


def test_compile_globalvalues_preserves_and_profiles_every_key(tmp_path: Path):
    default_values = json.loads(
        Path("tests/fixtures/default_globalvalues.json").read_text(encoding="utf-8")
    )
    contract = {
        "deck_name": "Fixture Aggro",
        "aggression_profile": {
            "speed": "aggro",
            "global_value_overlays": {"GlobalDivineShield": "increase"},
        },
    }

    result = compile_globalvalues(default_values, contract)
    config = result["config"]
    profile = result["profile"]

    assert set(config) == set(default_values)
    assert profile["key_count"] == len(default_values)
    assert set(profile["changed_keys"]) == {
        "FirstTurnValueWeight",
        "SecondTurnValueWeight",
        "GlobalDivineShield",
    }
    assert "GlobalTaunt" in profile["unchanged_keys"]
    for key, value in config.items():
        if key not in {"GameCardId", "ConfigComment"}:
            assert isinstance(value, dict)
            assert isinstance(value["values"], list)

    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(deck_dir / "GlobalValues.json", config)

    assert (
        validate_config_package(
            tmp_path,
            globalvalues_baseline=default_values,
            globalvalues_profile=profile,
        )["status"]
        == "passed"
    )


def test_validate_package_rejects_globalvalues_missing_baseline_keys(tmp_path: Path):
    default_values = json.loads(
        Path("tests/fixtures/default_globalvalues.json").read_text(encoding="utf-8")
    )
    deck_dir = tmp_path / "CustomConfig" / "deck"
    partial = {
        "GameCardId": "GlobalValues",
        "ConfigComment": "partial",
        "FirstTurnValueWeight": {"values": [{"condition": "*", "value": "1"}]},
    }
    write_json(deck_dir / "GlobalValues.json", partial)

    report = validate_config_package(tmp_path, globalvalues_baseline=default_values)

    assert report["status"] == "failed"
    assert any("GlobalValues missing baseline key" in error for error in report["errors"])


def test_compile_globalvalues_scales_simple_numeric_expressions():
    default_values = {
        "GameCardId": "GlobalValues",
        "ConfigComment": "Default GlobalValues fixture",
        "GlobalMinionIntrinsicValue": {"values": [{"condition": "*", "value": "3.32 + 2"}]},
    }
    contract = {
        "deck_name": "Fixture Aggro",
        "aggression_profile": {
            "speed": "aggro",
            "global_value_overlays": {"GlobalMinionIntrinsicValue": "increase"},
        },
    }

    result = compile_globalvalues(default_values, contract)

    assert result["config"]["GlobalMinionIntrinsicValue"]["values"][0]["value"] == "6.12"
    assert result["profile"]["changed_keys"] == ["GlobalMinionIntrinsicValue"]


def test_compile_globalvalues_uses_hero_power_overlay_reason():
    baseline = {
        "GameCardId": "GlobalValues",
        "ConfigComment": "Baseline",
        "MyHeroPowerValue": {"values": [{"condition": "*", "value": "1.00"}]},
    }
    contract = {
        "aggression_profile": {
            "speed": "aggro",
            "global_value_overlays": {"MyHeroPowerValue": "increase"},
            "global_value_overlay_reasons": {
                "MyHeroPowerValue": "Darkbishop Benedictus enables Mind Spike as pressure damage."
            },
        }
    }

    result = compile_globalvalues(baseline, contract)

    assert result["config"]["MyHeroPowerValue"]["values"][0]["value"] == "1.15"
    profile = result["profile"]["keys"]["MyHeroPowerValue"]
    assert profile["decision"] == "overlay_changed"
    assert profile["reason"] == "Darkbishop Benedictus enables Mind Spike as pressure damage."
