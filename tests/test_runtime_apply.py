import json
from pathlib import Path

import pytest

from hsconfig.io import write_json
from hsconfig.runtime_apply import apply_package


def _complete_package(
    tmp_path: Path, *, semantic_status: str, next_action: str, apply_policy: str
):
    package = tmp_path / "package"
    deck = package / "CustomConfig" / "deck"
    globalvalues = {"GameCardId": "GlobalValues", "ConfigComment": "new"}
    write_json(deck / "GlobalValues.json", globalvalues)
    write_json(
        deck / "Mulligan.json",
        {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}},
    )
    write_json(
        deck / "EX1_001.json",
        {"GameCardId": "EX1_001", "ConfigComment": "new", "InHandPlayPriority": {"values": []}},
    )
    write_json(package / "reports" / "globalvalues_baseline.json", globalvalues)
    write_json(
        package / "reports" / "globalvalues_profile.json",
        {
            "key_count": len(globalvalues),
            "keys": {key: {"status": "unchanged"} for key in globalvalues},
            "generated_overlay_keys": [],
        },
    )
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "Gate Deck", "deck_code": "fixture", "runtime_root": "unused"},
    )
    write_json(
        package / "reports" / "operator_summary.json",
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": semantic_status,
            "next_action": next_action,
            "apply_policy": apply_policy,
            "semantic_blockers": [{"reason": "cards_need_guide_claims", "count": 1}]
            if semantic_status != "SOURCE_BACKED_STRONG"
            else [],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )
    return package


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
    deck_config = runtime / "CustomConfig" / "deck_config.ini"
    deck_config.write_text("[CONFIGS]\nOther Deck = other\n", encoding="utf-8")

    receipt = apply_package(package_root=package, runtime_root=runtime, config_dir="deck")

    assert receipt["status"] == "applied"
    assert receipt["runtime_write_performed"] is True
    assert receipt["copied_files"] == ["EX1_001.json", "GlobalValues.json", "Mulligan.json"]
    assert (runtime / "CustomConfig" / "deck" / "GlobalValues.json").exists()
    assert not (runtime / "CustomConfig" / "deck" / "stale.json").exists()
    assert (runtime / "CustomConfig" / "other" / "keep.json").exists()
    assert "Other Deck = other" in deck_config.read_text(encoding="utf-8")
    assert "deck = deck" in deck_config.read_text(encoding="utf-8")
    assert receipt["mapped_deck_name"] == "deck"
    assert receipt["deck_config_ini_updated"] is True
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


def test_apply_cli_blocks_valid_but_not_guide_strong_package_by_default(
    tmp_path: Path, capsys
):
    from hsconfig.cli import main

    package = _complete_package(
        tmp_path,
        semantic_status="VALID_BUT_NOT_GUIDE_STRONG",
        next_action="IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
        apply_policy="ALLOWED_WITH_WARNINGS",
    )
    runtime = tmp_path / "runtime"

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

    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["status"] == "blocked"
    assert payload["apply_gate"]["status"] == "blocked"
    assert payload["apply_gate"]["reasons"][0]["reason"] == "operator_summary_not_ready_to_apply"
    assert not (runtime / "CustomConfig" / "deck").exists()


def test_apply_cli_allows_valid_but_not_guide_strong_only_with_explicit_escape_hatch(
    tmp_path: Path, capsys
):
    from hsconfig.cli import main

    package = _complete_package(
        tmp_path,
        semantic_status="VALID_BUT_NOT_GUIDE_STRONG",
        next_action="IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
        apply_policy="ALLOWED_WITH_WARNINGS",
    )
    runtime = tmp_path / "runtime"

    code = main(
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(runtime),
            "--allow-source-informed",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "applied"
    assert payload["apply_gate"]["mode"] == "source_informed_with_warnings"
    assert (runtime / "CustomConfig" / "deck" / "GlobalValues.json").exists()


def test_apply_cli_blocks_missing_operator_summary(tmp_path: Path, capsys):
    from hsconfig.cli import main

    package = tmp_path / "package"
    deck = package / "CustomConfig" / "deck"
    globalvalues = {"GameCardId": "GlobalValues", "ConfigComment": "new"}
    write_json(deck / "GlobalValues.json", globalvalues)
    write_json(
        deck / "Mulligan.json",
        {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}},
    )
    write_json(
        deck / "EX1_001.json",
        {"GameCardId": "EX1_001", "ConfigComment": "new", "InHandPlayPriority": {"values": []}},
    )
    write_json(package / "reports" / "globalvalues_baseline.json", globalvalues)
    write_json(
        package / "reports" / "globalvalues_profile.json",
        {
            "key_count": len(globalvalues),
            "keys": {key: {"status": "unchanged"} for key in globalvalues},
            "generated_overlay_keys": [],
        },
    )

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

    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["status"] == "blocked"
    assert payload["apply_gate"]["reasons"][0]["reason"] == "missing_operator_summary"


def test_apply_cli_blocks_empty_operator_summary_runtime_files(tmp_path: Path, capsys):
    from hsconfig.cli import main

    package = _complete_package(
        tmp_path,
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        apply_policy="ALLOWED",
    )
    operator_path = package / "reports" / "operator_summary.json"
    summary = json.loads(operator_path.read_text(encoding="utf-8"))
    summary["generated_files"] = []
    write_json(operator_path, summary)
    runtime = tmp_path / "runtime"

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

    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["status"] == "blocked"
    assert (
        payload["apply_gate"]["reasons"][0]["reason"]
        == "required_runtime_file_not_in_operator_summary"
    )
    assert (
        payload["apply_gate"]["reasons"][0]["generated_file"]
        == "CustomConfig/deck/GlobalValues.json"
    )
    assert not runtime.exists()


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

    generated_files = [
        str(path.relative_to(package)).replace("/", "\\")
        for path in sorted((package / "CustomConfig" / "apply_deck").glob("*.json"))
    ]
    write_json(
        package / "reports" / "operator_summary.json",
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": generated_files,
        },
    )

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
    assert payload["receipt"]["mapped_deck_name"] == "Apply Deck"
    assert payload["receipt"]["deck_config_ini_updated"] is True
    deck_config = runtime / "CustomConfig" / "deck_config.ini"
    assert "Apply Deck = apply_deck" in deck_config.read_text(encoding="utf-8")


def test_apply_package_updates_bom_deck_config_without_duplicate_configs_section(tmp_path: Path):
    package = tmp_path / "package"
    package_deck = package / "CustomConfig" / "shadowpriest"
    write_json(package_deck / "GlobalValues.json", {"GameCardId": "GlobalValues", "ConfigComment": "new"})
    write_json(package_deck / "Mulligan.json", {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}})
    write_json(
        package_deck / "EX1_001.json",
        {"GameCardId": "EX1_001", "ConfigComment": "new", "InHandPlayPriority": {"values": []}},
    )
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "ShadowPriest", "deck_code": "fixture", "runtime_root": "unused"},
    )

    runtime = tmp_path / "runtime"
    deck_config = runtime / "CustomConfig" / "deck_config.ini"
    deck_config.parent.mkdir(parents=True)
    deck_config.write_bytes(
        "\ufeff[CONFIGS]\r\nShadowPriest = old_shadow\r\nOther Deck = other\r\n".encode("utf-8")
    )

    receipt = apply_package(package_root=package, runtime_root=runtime)
    text = deck_config.read_text(encoding="utf-8")

    assert receipt["mapped_deck_name"] == "ShadowPriest"
    assert receipt["config_dir"] == "shadowpriest"
    assert receipt["deck_config_ini_previous_sha256"] != receipt["deck_config_ini_current_sha256"]
    assert text.count("[CONFIGS]") == 1
    assert "ShadowPriest = shadowpriest" in text
    assert "ShadowPriest = old_shadow" not in text
    assert "Other Deck = other" in text


def test_apply_package_rejects_manifest_deck_name_that_breaks_ini_mapping(tmp_path: Path):
    package = tmp_path / "package"
    package_deck = package / "CustomConfig" / "deck"
    write_json(package_deck / "GlobalValues.json", {"GameCardId": "GlobalValues", "ConfigComment": "new"})
    write_json(package_deck / "Mulligan.json", {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}})
    write_json(
        package_deck / "EX1_001.json",
        {"GameCardId": "EX1_001", "ConfigComment": "new", "InHandPlayPriority": {"values": []}},
    )
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "Bad\nDeck", "deck_code": "fixture", "runtime_root": "unused"},
    )

    with pytest.raises(ValueError, match="deck_config.ini"):
        apply_package(package_root=package, runtime_root=tmp_path / "runtime")

    assert not (tmp_path / "runtime" / "CustomConfig" / "deck").exists()
