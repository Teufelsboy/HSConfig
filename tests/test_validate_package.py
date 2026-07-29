import json
from pathlib import Path

import pytest

from hsconfig.io import write_json
from hsconfig.validate_package import validate_config_package
from hsconfig.visionai_registry import CARD_BEHAVIOR_BLOCKS, supported_surface


def _strict_package(tmp_path: Path) -> Path:
    package = tmp_path
    deck_dir = package / "CustomConfig" / "deck"
    write_json(
        deck_dir / "GlobalValues.json",
        {
            "GameCardId": "GlobalValues",
            "ConfigComment": "test",
            "FirstTurnValueWeight": {"values": [{"condition": "*", "value": "1"}]},
            "SecondTurnValueWeight": {"values": [{"condition": "*", "value": "0"}]},
        },
    )
    write_json(
        deck_dir / "Mulligan.json",
        {
            "GameCardId": "Mulligan",
            "ConfigComment": "test",
            "Mulligan": {"values": []},
        },
    )
    return package


@pytest.mark.parametrize(
    ("filename", "payload", "expected"),
    [
        (
            "Mulligan.json",
            {"GameCardId": "Mulligan", "ConfigComment": "x"},
            "missing required block Mulligan",
        ),
        (
            "Combo.json",
            {"GameCardId": "Combo", "ConfigComment": "x"},
            "missing required block ComboList",
        ),
    ],
)
def test_validate_package_rejects_semantically_invalid_rows(
    tmp_path, filename, payload, expected
):
    package = _strict_package(tmp_path)
    deck_dir = package / "CustomConfig" / "deck"
    (deck_dir / filename).write_text(json.dumps(payload), encoding="utf-8")

    result = validate_config_package(package, require_complete_package=True)

    assert result["status"] == "failed"
    assert any(expected in error for error in result["errors"])


def _write_card_behavior(package: Path, row: dict[str, object]) -> None:
    write_json(
        package / "CustomConfig" / "deck" / "EX1_001.json",
        {
            "GameCardId": "EX1_001",
            "ConfigComment": "x",
            "BeforePlayCardBonus": {"values": [row]},
        },
    )


def _write_combo(package: Path, row: dict[str, object]) -> None:
    write_json(
        package / "CustomConfig" / "deck" / "Combo.json",
        {
            "GameCardId": "Combo",
            "ConfigComment": "x",
            "ComboList": {"values": [row]},
        },
    )


def test_validate_package_rejects_ordinary_row_unsupported_condition(tmp_path):
    package = _strict_package(tmp_path)
    _write_card_behavior(package, {"condition": "nonsense", "value": "1"})

    result = validate_config_package(package, require_complete_package=True)

    assert result["status"] == "failed"
    assert any("unsupported runtime condition" in error for error in result["errors"])


def test_validate_package_rejects_ordinary_row_provenance_key(tmp_path):
    package = _strict_package(tmp_path)
    _write_card_behavior(
        package,
        {"condition": "*", "value": "1", "source_claim_ids": ["claim-a"]},
    )

    result = validate_config_package(package, require_complete_package=True)

    assert result["status"] == "failed"
    assert any("unsupported runtime row key source_claim_ids" in error for error in result["errors"])


def test_validate_package_rejects_ordinary_row_nonnumeric_value(tmp_path):
    package = _strict_package(tmp_path)
    _write_card_behavior(package, {"condition": "*", "value": "ten"})

    result = validate_config_package(package, require_complete_package=True)

    assert result["status"] == "failed"
    assert any("BeforePlayCardBonus row 0 ten must be numeric" in error for error in result["errors"])


def test_validate_package_rejects_ordinary_row_nonfinite_decimal(tmp_path):
    package = _strict_package(tmp_path)
    nonfinite_decimal = "9" * 400
    _write_card_behavior(package, {"condition": "*", "value": nonfinite_decimal})

    result = validate_config_package(package, require_complete_package=True)

    assert result["status"] == "failed"
    assert any("must be a finite decimal" in error for error in result["errors"])


def test_validate_combo_rejects_unsupported_condition(tmp_path):
    package = _strict_package(tmp_path)
    _write_combo(
        package,
        {
            "comment": "bad",
            "condition": "nonsense",
            "combo": "EX1_001 >> EX1_002",
            "value": "10 >> 20",
        },
    )

    result = validate_config_package(package, require_complete_package=True)

    assert result["status"] == "failed"
    assert any("unsupported runtime condition" in error for error in result["errors"])


def test_validate_combo_rejects_invalid_card_id(tmp_path):
    package = _strict_package(tmp_path)
    _write_combo(
        package,
        {
            "comment": "bad",
            "condition": "*",
            "combo": "BAD-ID >> EX1_002",
            "value": "10 >> 20",
        },
    )

    result = validate_config_package(package, require_complete_package=True)

    assert result["status"] == "failed"
    assert any("invalid Combo card id BAD-ID" in error for error in result["errors"])


def test_validate_combo_rejects_nonnumeric_value_segment(tmp_path):
    package = _strict_package(tmp_path)
    _write_combo(
        package,
        {
            "comment": "bad",
            "condition": "*",
            "combo": "EX1_001 >> EX1_002",
            "value": "ten >> 20",
        },
    )

    result = validate_config_package(package, require_complete_package=True)

    assert result["status"] == "failed"
    assert any("Combo value segment ten must be numeric" in error for error in result["errors"])


def test_validate_combo_rejects_nonfinite_value_segment(tmp_path):
    package = _strict_package(tmp_path)
    nonfinite_decimal = "9" * 400
    _write_combo(
        package,
        {
            "comment": "bad",
            "condition": "*",
            "combo": "EX1_001 >> EX1_002",
            "value": f"10 >> {nonfinite_decimal}",
        },
    )

    result = validate_config_package(package, require_complete_package=True)

    assert result["status"] == "failed"
    assert any("must be a finite decimal" in error for error in result["errors"])


def test_validate_globalvalues_rejects_unsupported_condition(tmp_path):
    package = _strict_package(tmp_path)
    write_json(
        package / "CustomConfig" / "deck" / "GlobalValues.json",
        {
            "GameCardId": "GlobalValues",
            "ConfigComment": "x",
            "FirstTurnValueWeight": {"values": [{"condition": "nonsense", "value": "1"}]},
        },
    )

    result = validate_config_package(package, require_complete_package=True)

    assert result["status"] == "failed"
    assert any("unsupported runtime condition" in error for error in result["errors"])


def test_validate_globalvalues_rejects_provenance_key(tmp_path):
    package = _strict_package(tmp_path)
    write_json(
        package / "CustomConfig" / "deck" / "GlobalValues.json",
        {
            "GameCardId": "GlobalValues",
            "ConfigComment": "x",
            "FirstTurnValueWeight": {
                "values": [{"condition": "*", "value": "1", "metadata": "leak"}]
            },
        },
    )

    result = validate_config_package(package, require_complete_package=True)

    assert result["status"] == "failed"
    assert any("unsupported runtime row key metadata" in error for error in result["errors"])


@pytest.mark.parametrize(
    "expression",
    ["1 / 0", "True", "False", "-True", "True + 1"],
)
def test_validate_globalvalues_rejects_unsafe_expression(
    tmp_path,
    expression: str,
):
    package = _strict_package(tmp_path)
    write_json(
        package / "CustomConfig" / "deck" / "GlobalValues.json",
        {
            "GameCardId": "GlobalValues",
            "ConfigComment": "x",
            "FirstTurnValueWeight": {
                "values": [{"condition": "*", "value": expression}]
            },
        },
    )

    result = validate_config_package(package, require_complete_package=True)

    assert result["status"] == "failed"
    assert any("must be a safe numeric expression" in error for error in result["errors"])


def test_validate_globalvalues_preserves_safe_arithmetic_expression(tmp_path):
    package = _strict_package(tmp_path)
    write_json(
        package / "CustomConfig" / "deck" / "GlobalValues.json",
        {
            "GameCardId": "GlobalValues",
            "ConfigComment": "x",
            "FirstTurnValueWeight": {"values": [{"condition": "*", "value": "3.32 + 2"}]},
        },
    )

    result = validate_config_package(package, require_complete_package=True)

    assert result["status"] == "passed"


def test_supported_surface_accepts_special_and_cardid_json():
    assert supported_surface("Mulligan.json")
    assert supported_surface("GlobalValues.json")
    assert supported_surface("Combo.json")
    assert supported_surface("Presume.json")
    assert supported_surface("Concede.json")
    assert supported_surface("EX1_001.json")
    assert supported_surface("VAN_EX1_001.json")
    assert "BeforeBattlecryTargetBonus" in CARD_BEHAVIOR_BLOCKS
    assert "OnDiscoverCardBonus" in CARD_BEHAVIOR_BLOCKS


def test_card_behavior_registry_includes_before_overkilled_bonus():
    assert "BeforeOverkilledBonus" in CARD_BEHAVIOR_BLOCKS


def test_supported_surface_rejects_non_json_and_invalid_cardid_names():
    assert not supported_surface("EX1_001.txt")
    assert not supported_surface("notes_EX1_001")
    assert not supported_surface("EX1-001.json")
    assert not supported_surface("DISCOVER_CARD.json")
    assert not supported_surface("CARD_A.json")
    assert not supported_surface("notes.json")
    assert not supported_surface("CardBehavior.json")
    assert not supported_surface(".json")


def test_validate_package_rejects_cardid_mismatch(tmp_path: Path):
    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(deck_dir / "ABC_001.json", {"GameCardId": "XYZ", "ConfigComment": "bad"})

    report = validate_config_package(tmp_path)

    assert report["status"] == "failed"
    assert any("GameCardId mismatch" in error for error in report["errors"])


def test_validate_package_accepts_minimal_globalvalues(tmp_path: Path):
    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(
        deck_dir / "GlobalValues.json",
        {
            "GameCardId": "GlobalValues",
            "ConfigComment": "test",
            "FirstTurnValueWeight": {"values": [{"condition": "*", "value": "1"}]},
            "SecondTurnValueWeight": {"values": [{"condition": "*", "value": "0"}]},
        },
    )

    report = validate_config_package(tmp_path)

    assert report == {"status": "passed", "errors": [], "checked_files": 1}


def test_validate_package_strict_mode_rejects_incomplete_package(tmp_path: Path):
    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(
        deck_dir / "GlobalValues.json",
        {
            "GameCardId": "GlobalValues",
            "ConfigComment": "test",
            "FirstTurnValueWeight": {"values": [{"condition": "*", "value": "1"}]},
            "SecondTurnValueWeight": {"values": [{"condition": "*", "value": "0"}]},
        },
    )

    report = validate_config_package(tmp_path, require_complete_package=True)

    assert report["status"] == "failed"
    assert any("missing required runtime file Mulligan.json" in error for error in report["errors"])
    assert not any("per-card CardID runtime file" in error for error in report["errors"])


def test_validate_package_strict_mode_accepts_minimal_load_safe_package_without_cardid(
    tmp_path: Path,
):
    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(
        deck_dir / "GlobalValues.json",
        {
            "GameCardId": "GlobalValues",
            "ConfigComment": "test",
            "FirstTurnValueWeight": {"values": [{"condition": "*", "value": "1"}]},
            "SecondTurnValueWeight": {"values": [{"condition": "*", "value": "0"}]},
        },
    )
    write_json(
        deck_dir / "Mulligan.json",
        {
            "GameCardId": "Mulligan",
            "ConfigComment": "test",
            "Mulligan": {
                "values": [
                    {
                        "comment": "hold early pressure",
                        "mulligan": "EX1_001",
                        "condition": "*",
                        "value": "hold",
                    }
                ]
            },
        },
    )

    report = validate_config_package(tmp_path, require_complete_package=True)

    assert report == {"status": "passed", "errors": [], "checked_files": 2}


def test_validate_package_strict_mode_rejects_multiple_deck_directories(tmp_path: Path):
    for deck_name in ("shadowpriest", "piraterogue"):
        deck_dir = tmp_path / "CustomConfig" / deck_name
        write_json(
            deck_dir / "GlobalValues.json",
            {
                "GameCardId": "GlobalValues",
                "ConfigComment": "test",
                "FirstTurnValueWeight": {"values": [{"condition": "*", "value": "1"}]},
                "SecondTurnValueWeight": {"values": [{"condition": "*", "value": "0"}]},
            },
        )
        write_json(
            deck_dir / "Mulligan.json",
            {
                "GameCardId": "Mulligan",
                "ConfigComment": "test",
                "Mulligan": {"values": []},
            },
        )

    report = validate_config_package(tmp_path, require_complete_package=True)

    assert report["status"] == "failed"
    assert any(
        "expected exactly one deck config directory" in error
        and "piraterogue" in error
        and "shadowpriest" in error
        for error in report["errors"]
    )


def test_validate_package_rejects_special_surface_scalar_blocks(tmp_path: Path):
    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(
        deck_dir / "GlobalValues.json",
        {
            "GameCardId": "GlobalValues",
            "ConfigComment": "bad",
            "FirstTurnValueWeight": "1",
        },
    )

    report = validate_config_package(tmp_path)

    assert report["status"] == "failed"
    assert any("FirstTurnValueWeight must contain values array" in error for error in report["errors"])


def test_validate_package_rejects_special_surface_blocks_without_values(tmp_path: Path):
    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(
        deck_dir / "Mulligan.json",
        {
            "GameCardId": "Mulligan",
            "ConfigComment": "bad",
            "EX1_001": {"condition": "*", "value": "hold"},
        },
    )

    report = validate_config_package(tmp_path)

    assert report["status"] == "failed"
    assert any("unsupported block EX1_001" in error for error in report["errors"])


def test_validate_package_rejects_lone_wildcard_mulligan_discard(tmp_path: Path):
    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(
        deck_dir / "Mulligan.json",
        {
            "GameCardId": "Mulligan",
            "ConfigComment": "bad",
            "Mulligan": {
                "values": [
                    {
                        "comment": "discard everything",
                        "mulligan": "*",
                        "condition": "*",
                        "value": "discard",
                    }
                ]
            },
        },
    )

    report = validate_config_package(tmp_path)

    assert report["status"] == "failed"
    assert any("lone_wildcard_discard" in error for error in report["errors"])


def test_validate_package_rejects_mulligan_wildcard_discard_before_hold(tmp_path: Path):
    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(
        deck_dir / "Mulligan.json",
        {
            "GameCardId": "Mulligan",
            "ConfigComment": "bad",
            "Mulligan": {
                "values": [
                    {
                        "comment": "discard everything too early",
                        "mulligan": "*",
                        "condition": "*",
                        "value": "discard",
                    },
                    {
                        "comment": "hold later",
                        "mulligan": "EX1_001",
                        "condition": "*",
                        "value": "hold",
                    },
                ]
            },
        },
    )

    report = validate_config_package(tmp_path)

    assert report["status"] == "failed"
    assert any(
        "Mulligan wildcard discard appears before any non-wildcard hold" in error
        for error in report["errors"]
    )


def test_validate_package_rejects_unsupported_mulligan_selector(tmp_path: Path):
    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(
        deck_dir / "Mulligan.json",
        {
            "GameCardId": "Mulligan",
            "ConfigComment": "bad",
            "Mulligan": {
                "values": [
                    {
                        "comment": "unsupported selector",
                        "mulligan": "EX1_001 | EX1_002",
                        "condition": "*",
                        "value": "hold",
                    }
                ]
            },
        },
    )

    report = validate_config_package(tmp_path)

    assert report["status"] == "failed"
    assert any("unsupported_mulligan_selector" in error for error in report["errors"])


def test_validate_package_rejects_combo_segment_mismatch(tmp_path: Path):
    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(
        deck_dir / "Combo.json",
        {
            "GameCardId": "Combo",
            "ConfigComment": "bad",
            "ComboList": {"values": [{"combo": "EX1_001 >> EX1_002", "value": "10"}]},
        },
    )

    report = validate_config_package(tmp_path)

    assert report["status"] == "failed"
    assert any("combo/value segment count mismatch" in error for error in report["errors"])


def test_validate_package_rejects_one_card_combo(tmp_path: Path):
    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(
        deck_dir / "Combo.json",
        {
            "GameCardId": "Combo",
            "ConfigComment": "bad",
            "ComboList": {"values": [{"combo": "EX1_001", "value": "10"}]},
        },
    )

    report = validate_config_package(tmp_path)

    assert report["status"] == "failed"
    assert any("combo row must contain at least two cards" in error for error in report["errors"])


def test_validate_package_rejects_combo_runtime_provenance_keys(tmp_path: Path):
    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(
        deck_dir / "Combo.json",
        {
            "GameCardId": "Combo",
            "ConfigComment": "bad",
            "ComboList": {
                "values": [
                    {
                        "comment": "bad",
                        "condition": "*",
                        "combo": "EX1_001>>EX1_002",
                        "value": "10>>10",
                        "source_claim_ids": ["claim_a"],
                    }
                ]
            },
        },
    )

    report = validate_config_package(tmp_path)

    assert report["status"] == "failed"
    assert any("unsupported ComboList row key source_claim_ids" in error for error in report["errors"])


def test_validate_package_rejects_unsupported_card_behavior_block(tmp_path: Path):
    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(
        deck_dir / "EX1_001.json",
        {
            "GameCardId": "EX1_001",
            "ConfigComment": "bad",
            "UnknownBlock": {"values": []},
        },
    )

    report = validate_config_package(tmp_path)

    assert report["status"] == "failed"
    assert any("unsupported card behavior block UnknownBlock" in error for error in report["errors"])


def test_validate_package_accepts_before_overkilled_bonus_block(tmp_path: Path):
    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(
        deck_dir / "EX1_001.json",
        {
            "GameCardId": "EX1_001",
            "ConfigComment": "test",
            "BeforeOverkilledBonus": {"values": [{"condition": "*", "value": "1"}]},
        },
    )

    report = validate_config_package(tmp_path)

    assert report["status"] == "passed"


def test_validate_package_rejects_trailing_comma_runtime_json(tmp_path: Path):
    deck_dir = tmp_path / "CustomConfig" / "deck"
    deck_dir.mkdir(parents=True)
    (deck_dir / "EX1_001.json").write_text(
        '{\n'
        '  "GameCardId": "EX1_001",\n'
        '  "ConfigComment": "bad",\n'
        '  "InHandPlayPriority": {"values": []},\n'
        '}\n',
        encoding="utf-8",
    )

    report = validate_config_package(tmp_path)

    assert report["status"] == "failed"
    assert any("EX1_001.json: invalid JSON" in error for error in report["errors"])


@pytest.mark.parametrize(
    ("raw_json", "constant"),
    [
        ('{"GameCardId":"EX1_001","ConfigComment":NaN}', "NaN"),
        (
            '{"GameCardId":"EX1_001","ConfigComment":"x",'
            '"BeforePlayCardBonus":{"values":[{"condition":"*","value":Infinity}]}}',
            "Infinity",
        ),
        (
            '{"GameCardId":"EX1_001","ConfigComment":"x",'
            '"BeforePlayCardBonus":{"values":[{"comment":-Infinity,'
            '"condition":"*","value":"1"}]}}',
            "-Infinity",
        ),
    ],
)
def test_validate_package_rejects_nonstandard_json_constants_in_checked_and_unchecked_fields(
    tmp_path: Path, raw_json: str, constant: str
):
    deck_dir = tmp_path / "CustomConfig" / "deck"
    deck_dir.mkdir(parents=True)
    (deck_dir / "EX1_001.json").write_text(raw_json, encoding="utf-8")

    report = validate_config_package(tmp_path)

    assert report["status"] == "failed"
    assert any("invalid JSON" in error and constant in error for error in report["errors"])


def test_validate_package_rejects_non_json_surface_with_underscore(tmp_path: Path):
    deck_dir = tmp_path / "CustomConfig" / "deck"
    deck_dir.mkdir(parents=True)
    (deck_dir / "EX1_001.txt").write_text("not json", encoding="utf-8")

    report = validate_config_package(tmp_path)

    assert report["status"] == "failed"
    assert any("unsupported VisionAI surface" in error for error in report["errors"])
