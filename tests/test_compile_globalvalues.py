import json
from pathlib import Path

import pytest

from hsconfig.compile_globalvalues import compile_globalvalues
from hsconfig.globalvalues_baseline import load_globalvalues_baseline
from hsconfig.io import write_json
from hsconfig.validate_package import validate_config_package


def test_fallback_contains_current_runtime_key_families():
    baseline = load_globalvalues_baseline(None)

    assert baseline["source"] == "bundled_fallback"
    assert baseline["snapshot_status"] == "known_runtime_snapshot"
    assert baseline["snapshot_date"] == "2026-07-25"
    keys = set(baseline["baseline"])
    assert {
        "GlobalMinionAttack",
        "GlobalMinionIntrinsicValue",
        "GlobalLocationHealth",
        "GlobalLocationIntrinsicValue",
        "OppGlobalMinionAttack",
        "OppGlobalMinionIntrinsicValue",
        "OppGlobalLocationHealth",
        "OppGlobalLocationIntrinsicValue",
    } <= keys


def test_compile_globalvalues_reports_authorized_overlay_missing_from_baseline():
    result = compile_globalvalues(
        {
            "GameCardId": "GlobalValues",
            "ConfigComment": "thin",
            "FirstTurnValueWeight": {
                "values": [{"condition": "*", "value": "0"}]
            },
        },
        {
            "global_values_authority_matrix": {
                "allowed_step1_overlays": [
                    {
                        "key": "GlobalMinionAttack",
                        "operation": "increase",
                        "reason": "aggro",
                    }
                ]
            }
        },
    )

    assert result["profile"]["summary"]["all_expected_overlay_keys_accounted_for"] is False
    assert result["profile"]["missing_overlay_keys"] == ["GlobalMinionAttack"]
    assert result["profile"]["status"] == "attention"


def test_compile_globalvalues_exposes_overlay_coverage_in_profile_and_summary():
    result = compile_globalvalues(
        {
            "GameCardId": "GlobalValues",
            "ConfigComment": "thin",
        },
        {
            "global_values_authority_matrix": {
                "allowed_step1_overlays": [
                    {
                        "key": "GlobalMinionAttack",
                        "operation": "increase",
                        "reason": "aggro",
                    }
                ]
            }
        },
    )

    assert result["profile"]["all_expected_overlay_keys_accounted_for"] is False
    assert result["profile"]["summary"]["missing_overlay_keys"] == ["GlobalMinionAttack"]


def test_compile_globalvalues_keeps_known_hero_power_overlay_in_profile_when_authority_is_baseline():
    baseline = load_globalvalues_baseline(None)["baseline"]
    result = compile_globalvalues(
        baseline,
        {
            "aggression_profile": {
                "global_value_overlays": {"MyHeroPowerValue": "increase"}
            },
            "global_values_authority_matrix": {
                "allowed_step1_overlays": [
                    {
                        "key": "baseline",
                        "operation": "none",
                        "reason": "no_source_backed_posture_overlay",
                    }
                ]
            },
        },
    )

    assert "MyHeroPowerValue" not in baseline
    assert result["profile"]["generated_overlay_keys"] == ["MyHeroPowerValue"]
    assert result["profile"]["keys"]["MyHeroPowerValue"]["decision"] == "baseline_confirmed"
    assert result["config"]["MyHeroPowerValue"]["values"][0]["value"] == "1.00"


def test_validate_package_rejects_required_globalvalues_profile_with_missing_overlay_coverage(
    tmp_path: Path,
):
    baseline = {
        "GameCardId": "GlobalValues",
        "ConfigComment": "Baseline",
        "FirstTurnValueWeight": {"values": [{"condition": "*", "value": "0"}]},
    }
    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(deck_dir / "GlobalValues.json", baseline)
    profile = {
        "key_count": len(baseline),
        "generated_overlay_keys": [],
        "keys": {key: {} for key in baseline},
        "summary": {"all_expected_overlay_keys_accounted_for": False},
    }

    report = validate_config_package(
        tmp_path,
        globalvalues_baseline=baseline,
        globalvalues_profile=profile,
        require_globalvalues_profile=True,
    )

    assert report["status"] == "failed"
    assert any(
        "GlobalValues profile does not account for every expected overlay key" in error
        for error in report["errors"]
    )


def test_validate_package_allows_legacy_globalvalues_profile_when_profile_is_not_required(
    tmp_path: Path,
):
    baseline = {
        "GameCardId": "GlobalValues",
        "ConfigComment": "Baseline",
    }
    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(deck_dir / "GlobalValues.json", baseline)
    profile = {
        "key_count": len(baseline),
        "generated_overlay_keys": [],
        "keys": {key: {} for key in baseline},
    }

    report = validate_config_package(
        tmp_path,
        globalvalues_baseline=baseline,
        globalvalues_profile=profile,
    )

    assert report["status"] == "passed"


def _required_globalvalues_fixture(tmp_path: Path) -> tuple[dict, dict, dict]:
    baseline = {
        "GameCardId": "GlobalValues",
        "ConfigComment": "Baseline",
        "FirstTurnValueWeight": {"values": [{"condition": "*", "value": "0"}]},
    }
    result = compile_globalvalues(
        baseline,
        {
            "global_values_authority_matrix": {
                "allowed_step1_overlays": [
                    {
                        "key": "FirstTurnValueWeight",
                        "operation": "set",
                        "value": "0.75",
                        "reason": "source-backed posture",
                    }
                ]
            }
        },
    )
    write_json(tmp_path / "CustomConfig" / "deck" / "GlobalValues.json", result["config"])
    return baseline, result["config"], result["profile"]


def test_validate_package_accepts_required_profile_with_emitted_expected_overlay(
    tmp_path: Path,
):
    baseline, _, profile = _required_globalvalues_fixture(tmp_path)

    report = validate_config_package(
        tmp_path,
        globalvalues_baseline=baseline,
        globalvalues_profile=profile,
        require_globalvalues_profile=True,
    )

    assert report["status"] == "passed"


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        (
            lambda profile: profile.update({"missing_overlay_keys": ["GlobalMinionAttack"]}),
            "missing_overlay_keys must be an empty list",
        ),
        (
            lambda profile: profile.pop("missing_overlay_keys"),
            "missing_overlay_keys must be an empty list",
        ),
        (
            lambda profile: profile.update({"missing_overlay_keys": "none"}),
            "missing_overlay_keys must be an empty list",
        ),
        (
            lambda profile: (
                profile.update({"expected_overlay_keys": ["GlobalMinionAttack"]}),
                profile["keys"].update({"GlobalMinionAttack": {}}),
            ),
            "expected overlay key GlobalMinionAttack is not emitted or generated",
        ),
    ],
)
def test_validate_package_rejects_required_profile_overlay_coverage_mutations(
    tmp_path: Path,
    mutation,
    expected_error: str,
):
    baseline, _, profile = _required_globalvalues_fixture(tmp_path)
    mutation(profile)

    report = validate_config_package(
        tmp_path,
        globalvalues_baseline=baseline,
        globalvalues_profile=profile,
        require_globalvalues_profile=True,
    )

    assert report["status"] == "failed"
    assert any(expected_error in error for error in report["errors"])


def _empty_required_globalvalues_fixture(tmp_path: Path) -> tuple[dict, dict, dict]:
    baseline = {
        "GameCardId": "GlobalValues",
        "ConfigComment": "Baseline",
    }
    result = compile_globalvalues(baseline, {})
    write_json(tmp_path / "CustomConfig" / "deck" / "GlobalValues.json", result["config"])
    return baseline, result["config"], result["profile"]


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    [
        ("generated_overlay_keys", None, "generated_overlay_keys must be a list"),
        ("generated_overlay_keys", 1, "generated_overlay_keys must be a list"),
        ("generated_overlay_keys", {"MyHeroPowerValue": {}}, "generated_overlay_keys must be a list"),
        (
            "generated_overlay_keys",
            ["MyHeroPowerValue", 1],
            "generated_overlay_keys item must be a non-empty string",
        ),
        ("keys", None, "profile keys must be an object"),
        ("keys", 1, "profile keys must be an object"),
        ("keys", [], "profile keys must be an object"),
        ({"keys": {1: {}}}, None, "profile keys must use non-empty string names"),
    ],
)
def test_validate_package_rejects_malformed_required_profile_ledger_types(
    tmp_path: Path,
    field: str | dict,
    value: object,
    expected_error: str,
):
    baseline, _, profile = _empty_required_globalvalues_fixture(tmp_path)
    if isinstance(field, dict):
        profile.update(field)
    else:
        profile[field] = value

    report = validate_config_package(
        tmp_path,
        globalvalues_baseline=baseline,
        globalvalues_profile=profile,
        require_globalvalues_profile=True,
    )

    assert report["status"] == "failed"
    assert any(expected_error in error for error in report["errors"])


def test_validate_package_rejects_generated_overlay_injection_not_expected_or_known(
    tmp_path: Path,
):
    baseline, config, profile = _empty_required_globalvalues_fixture(tmp_path)
    config["InjectedKey"] = {"values": [{"condition": "*", "value": "1.00"}]}
    profile["generated_overlay_keys"].append("InjectedKey")
    profile["keys"]["InjectedKey"] = {"status": "baseline_confirmed"}
    write_json(tmp_path / "CustomConfig" / "deck" / "GlobalValues.json", config)

    report = validate_config_package(
        tmp_path,
        globalvalues_baseline=baseline,
        globalvalues_profile=profile,
        require_globalvalues_profile=True,
    )

    assert report["status"] == "failed"
    assert any(
        "generated overlay key InjectedKey is neither expected nor known generated default"
        in error
        for error in report["errors"]
    )


def test_validate_package_accepts_known_generated_hero_power_overlay_exception(tmp_path: Path):
    baseline = {
        "GameCardId": "GlobalValues",
        "ConfigComment": "Baseline",
    }
    result = compile_globalvalues(
        baseline,
        {
            "aggression_profile": {
                "global_value_overlays": {"MyHeroPowerValue": "increase"}
            },
            "global_values_authority_matrix": {
                "allowed_step1_overlays": [
                    {
                        "key": "baseline",
                        "operation": "none",
                        "reason": "no_source_backed_posture_overlay",
                    }
                ]
            },
        },
    )
    write_json(tmp_path / "CustomConfig" / "deck" / "GlobalValues.json", result["config"])

    report = validate_config_package(
        tmp_path,
        globalvalues_baseline=baseline,
        globalvalues_profile=result["profile"],
        require_globalvalues_profile=True,
    )

    assert result["profile"]["expected_overlay_keys"] == []
    assert result["profile"]["generated_overlay_keys"] == ["MyHeroPowerValue"]
    assert report["status"] == "passed"


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
    assert profile["expected_overlay_keys"] == ["MyHeroPowerValue"]
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


def test_compile_globalvalues_authority_matrix_baseline_blocks_implicit_overlays():
    baseline = {
        "GameCardId": "GlobalValues",
        "ConfigComment": "Baseline",
        "FirstTurnValueWeight": {"values": [{"condition": "*", "value": "0"}]},
        "SecondTurnValueWeight": {"values": [{"condition": "*", "value": "1"}]},
        "MyHeroPowerValue": {"values": [{"condition": "*", "value": "1.00"}]},
        "GlobalDivineShield": {"values": [{"condition": "*", "value": "1.00"}]},
    }
    contract = {
        "aggression_profile": {
            "speed": "aggro",
            "global_value_overlays": {
                "MyHeroPowerValue": "increase",
                "GlobalDivineShield": "increase",
            },
            "mechanic_priorities": {"SecondTurnValueWeight": "set:0.25"},
        },
        "global_values_authority_matrix": {
            "posture": "baseline",
            "allowed_step1_overlays": [
                {
                    "key": "baseline",
                    "overlay": "none",
                    "operation": "none",
                    "value": None,
                    "authority": "baseline_default",
                    "reason": "no_source_backed_posture_overlay",
                }
            ],
            "blocked_until_runtime_evidence": [],
        },
    }

    result = compile_globalvalues(baseline, contract)

    assert result["config"]["FirstTurnValueWeight"]["values"][0]["value"] == "0"
    assert result["config"]["SecondTurnValueWeight"]["values"][0]["value"] == "1"
    assert result["config"]["MyHeroPowerValue"]["values"][0]["value"] == "1.00"
    assert result["config"]["GlobalDivineShield"]["values"][0]["value"] == "1.00"
    assert result["profile"]["changed_keys"] == []
    assert result["profile"]["expected_overlay_keys"] == []
    assert result["profile"]["keys"]["MyHeroPowerValue"]["decision"] == "baseline_confirmed"


def test_compile_globalvalues_authority_matrix_uses_only_allowed_rows_and_reasons():
    baseline = {
        "GameCardId": "GlobalValues",
        "ConfigComment": "Baseline",
        "FirstTurnValueWeight": {"values": [{"condition": "*", "value": "0"}]},
        "SecondTurnValueWeight": {"values": [{"condition": "*", "value": "1"}]},
        "MyHeroPowerValue": {"values": [{"condition": "*", "value": "1.00"}]},
    }
    contract = {
        "aggression_profile": {
            "speed": "aggro",
            "global_value_overlays": {"MyHeroPowerValue": "decrease"},
            "global_value_overlay_reasons": {
                "MyHeroPowerValue": "legacy aggression-profile reason"
            },
        },
        "global_values_authority_matrix": {
            "posture": "hero_power_pressure",
            "allowed_step1_overlays": [
                {
                    "key": "MyHeroPowerValue",
                    "overlay": "increase",
                    "operation": "increase",
                    "value": None,
                    "authority": "step1_source_backed_posture",
                    "reason": "hero_power_pressure_prioritizes_hero_power",
                }
            ],
            "blocked_until_runtime_evidence": [],
        },
    }

    result = compile_globalvalues(baseline, contract)

    assert result["config"]["FirstTurnValueWeight"]["values"][0]["value"] == "0"
    assert result["config"]["SecondTurnValueWeight"]["values"][0]["value"] == "1"
    assert result["config"]["MyHeroPowerValue"]["values"][0]["value"] == "1.15"
    assert result["profile"]["changed_keys"] == ["MyHeroPowerValue"]
    assert result["profile"]["expected_overlay_keys"] == ["MyHeroPowerValue"]
    profile = result["profile"]["keys"]["MyHeroPowerValue"]
    assert profile["decision"] == "overlay_changed"
    assert profile["reason"] == "hero_power_pressure_prioritizes_hero_power"
