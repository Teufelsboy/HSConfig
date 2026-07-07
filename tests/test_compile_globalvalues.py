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


def test_validate_package_rejects_globalvalues_rows_missing_condition_or_value(
    tmp_path: Path,
):
    deck_dir = tmp_path / "CustomConfig" / "deck"
    payload = {
        "GameCardId": "GlobalValues",
        "ConfigComment": "Fixture",
        "FirstTurnValueWeight": {"values": [{"value": "1.00"}]},
        "SecondTurnValueWeight": {"values": [{"condition": "*"}]},
    }
    write_json(deck_dir / "GlobalValues.json", payload)

    report = validate_config_package(tmp_path)

    assert report["status"] == "failed"
    assert any(
        "GlobalValues block FirstTurnValueWeight row 0 missing condition" in error
        for error in report["errors"]
    )
    assert any(
        "GlobalValues block SecondTurnValueWeight row 0 missing value" in error
        for error in report["errors"]
    )


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


def test_compile_globalvalues_adds_known_overlay_key_missing_from_runtime_baseline(tmp_path: Path):
    baseline = {
        "GameCardId": "GlobalValues",
        "ConfigComment": "Runtime default without hero power key",
        "GlobalHeroAttack": {"values": [{"condition": "*", "value": "1.00"}]},
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
    config = result["config"]
    profile = result["profile"]

    assert config["MyHeroPowerValue"]["values"][0]["value"] == "1.15"
    assert profile["generated_overlay_keys"] == ["MyHeroPowerValue"]
    assert profile["key_count"] == len(config)
    assert profile["keys"]["MyHeroPowerValue"]["decision"] == "overlay_changed"

    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(deck_dir / "GlobalValues.json", config)

    assert (
        validate_config_package(
            tmp_path,
            globalvalues_baseline=baseline,
            globalvalues_profile=profile,
        )["status"]
        == "passed"
    )


def test_compile_globalvalues_profile_includes_key_authority_fields():
    baseline = {
        "GameCardId": "GlobalValues",
        "ConfigComment": "Baseline",
        "FirstTurnValueWeight": {"values": [{"condition": "*", "value": "1.00"}]},
        "OpponentSpecificMatchupTuning": {"values": [{"condition": "*", "value": "1.00"}]},
        "GlobalTaunt": {"values": [{"condition": "*", "value": "1.00"}]},
    }
    contract = {
        "global_values_authority_matrix": {
            "allowed_step1_overlays": [
                {
                    "key": "FirstTurnValueWeight",
                    "operation": "set",
                    "value": "0.75",
                    "reason": "aggressive deck values first turns.",
                }
            ]
        }
    }

    result = compile_globalvalues(baseline, contract)
    profiles = result["profile"]["keys"]

    assert profiles["FirstTurnValueWeight"]["authority_category"] == "step1_posture_overlay_allowed"
    assert profiles["FirstTurnValueWeight"]["board_value_component"] == "turn_weight"
    assert profiles["OpponentSpecificMatchupTuning"]["authority_category"] == "runtime_evidence_required"
    assert profiles["OpponentSpecificMatchupTuning"]["board_value_component"] == "matchup_runtime"
    assert profiles["GlobalTaunt"]["authority_category"] == "copy_baseline"
    assert profiles["GlobalTaunt"]["board_value_component"] == "baseline"


def test_compile_globalvalues_accepts_operation_value_authority_rows():
    baseline = {
        "GameCardId": "GlobalValues",
        "ConfigComment": "Baseline",
        "FirstTurnValueWeight": {"values": [{"condition": "*", "value": "1.00"}]},
        "MyWeaponValue": {"values": [{"condition": "*", "value": "1.00"}]},
    }
    contract = {
        "global_values_authority_matrix": {
            "allowed_step1_overlays": [
                {
                    "key": "FirstTurnValueWeight",
                    "operation": "set",
                    "value": "0.70",
                    "reason": "weapon deck still values first turn.",
                },
                {
                    "key": "MyWeaponValue",
                    "operation": "increase",
                    "value": None,
                    "reason": "weapon pressure posture.",
                },
            ]
        }
    }

    result = compile_globalvalues(baseline, contract)

    assert result["config"]["FirstTurnValueWeight"]["values"][0]["value"] == "0.70"
    assert result["config"]["MyWeaponValue"]["values"][0]["value"] == "1.15"
