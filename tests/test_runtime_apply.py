import json
from pathlib import Path

import pytest

from hsconfig.io import write_json
from hsconfig.runtime_apply import apply_package


def test_apply_package_replaces_only_target_deck_folder(tmp_path: Path):
    package = tmp_path / "package"
    package_deck = package / "CustomConfig" / "deck"
    write_json(package_deck / "GlobalValues.json", {"GameCardId": "GlobalValues", "ConfigComment": "new"})
    write_json(package_deck / "Mulligan.json", {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}})
    write_json(
        package_deck / "EX1_001.json",
        {"GameCardId": "EX1_001", "ConfigComment": "new", "InHandPlayPriority": {"values": []}},
    )

    runtime = tmp_path / "runtime"
    stale_deck = runtime / "CustomConfig" / "deck"
    other_deck = runtime / "CustomConfig" / "other"
    write_json(stale_deck / "stale.json", {"old": True})
    write_json(other_deck / "keep.json", {"keep": True})

    receipt = apply_package(package_root=package, runtime_root=runtime, config_dir="deck")

    assert receipt["status"] == "applied"
    assert receipt["runtime_write_performed"] is True
    assert receipt["copied_files"] == ["EX1_001.json", "GlobalValues.json", "Mulligan.json"]
    assert (runtime / "CustomConfig" / "deck" / "GlobalValues.json").exists()
    assert not (runtime / "CustomConfig" / "deck" / "stale.json").exists()
    assert (runtime / "CustomConfig" / "other" / "keep.json").exists()
    receipt_path = package / "reports" / "runtime_apply_receipt.json"
    assert receipt_path.exists()
    assert json.loads(receipt_path.read_text(encoding="utf-8"))["status"] == "applied"


def test_apply_package_rejects_incomplete_source_before_replacing_runtime(tmp_path: Path):
    package = tmp_path / "package"
    package_deck = package / "CustomConfig" / "deck"
    write_json(package_deck / "GlobalValues.json", {"GameCardId": "GlobalValues", "ConfigComment": "new"})
    runtime_deck = tmp_path / "runtime" / "CustomConfig" / "deck"
    write_json(runtime_deck / "Mulligan.json", {"old": True})

    with pytest.raises(ValueError, match="Incomplete package"):
        apply_package(package_root=package, runtime_root=tmp_path / "runtime", config_dir="deck")

    assert (runtime_deck / "Mulligan.json").exists()


def test_apply_cli_rejects_incomplete_package_without_deleting_runtime(tmp_path: Path, capsys):
    package = tmp_path / "package"
    write_json(
        package / "CustomConfig" / "deck" / "GlobalValues.json",
        {"GameCardId": "GlobalValues", "ConfigComment": "new"},
    )
    runtime_deck = tmp_path / "runtime" / "CustomConfig" / "deck"
    write_json(runtime_deck / "Mulligan.json", {"old": True})

    from hsconfig.cli import main

    code = main(
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 1
    assert payload["status"] == "failed"
    assert "Missing GlobalValues baseline report" in payload["errors"][0]
    assert (runtime_deck / "Mulligan.json").exists()


def test_apply_cli_returns_json_status_for_built_package(tmp_path: Path, capsys):
    from hsconfig.cli import main

    package = tmp_path / "package"
    runtime = tmp_path / "runtime"

    build_code = main(
        [
            "build",
            "--deck-name",
            "Apply Deck",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(runtime),
            "--out",
            str(package),
            "--allow-placeholder",
            "--json",
        ]
    )
    capsys.readouterr()
    assert build_code == 0

    code = main(
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(runtime),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 0
    assert payload["status"] == "applied"
    assert payload["receipt"]["target_path"].endswith("CustomConfig/apply_deck") or payload[
        "receipt"
    ]["target_path"].endswith("CustomConfig\\apply_deck")
