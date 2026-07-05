from pathlib import Path

from hsconfig.io import write_json
from hsconfig.validate_package import validate_config_package
from hsconfig.visionai_registry import CARD_BEHAVIOR_BLOCKS, supported_surface


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


def test_supported_surface_rejects_non_json_and_invalid_cardid_names():
    assert not supported_surface("EX1_001.txt")
    assert not supported_surface("notes_EX1_001")
    assert not supported_surface("EX1-001.json")
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
    assert any("missing at least one per-card CardID runtime file" in error for error in report["errors"])


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


def test_validate_package_rejects_non_json_surface_with_underscore(tmp_path: Path):
    deck_dir = tmp_path / "CustomConfig" / "deck"
    deck_dir.mkdir(parents=True)
    (deck_dir / "EX1_001.txt").write_text("not json", encoding="utf-8")

    report = validate_config_package(tmp_path)

    assert report["status"] == "failed"
    assert any("unsupported VisionAI surface" in error for error in report["errors"])
