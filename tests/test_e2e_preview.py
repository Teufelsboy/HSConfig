import json
from pathlib import Path

from hsconfig.cli import main


def test_build_preview_creates_valid_package_without_cards_json(tmp_path: Path, capsys):
    out = tmp_path / "fixturedeck"
    runtime = tmp_path / "runtime"
    runtime_default = {
        "GameCardId": "GlobalValues",
        "ConfigComment": "Runtime default baseline",
        "FirstTurnValueWeight": {"values": [{"condition": "*", "value": "0"}]},
        "SecondTurnValueWeight": {"values": [{"condition": "*", "value": "1"}]},
        "GlobalDivineShield": {"values": [{"condition": "*", "value": "2.74"}]},
        "RuntimeOnlyFullBaselineKey": {"values": [{"condition": "*", "value": "9"}]},
    }
    default_path = runtime / "CustomConfig" / "default" / "GlobalValues.json"
    default_path.parent.mkdir(parents=True)
    default_path.write_text(json.dumps(runtime_default), encoding="utf-8")

    code = main(
        [
            "build",
            "--deck-name",
            "Fixture Deck",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(runtime),
            "--out",
            str(out),
            "--json",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    deck_dir = out / "CustomConfig" / "fixture_deck"
    reports = out / "reports"

    assert code == 0
    assert payload["status"] == "passed"
    assert (deck_dir / "GlobalValues.json").exists()
    assert (deck_dir / "Mulligan.json").exists()
    assert not (deck_dir / "Presume.json").exists()
    assert not (deck_dir / "Concede.json").exists()
    assert not (deck_dir / "Combo.json").exists()
    assert len([path for path in deck_dir.glob("*.json") if path.stem.startswith("HSC_")]) >= 2
    for report_name in {
        "input_manifest.json",
        "deck_identity.json",
        "gameplan_contract.json",
        "surface_intent.json",
        "globalvalues_baseline.json",
        "globalvalues_baseline_receipt.json",
        "globalvalues_profile.json",
        "validation_report.json",
    }:
        assert (reports / report_name).exists()

    validation_report = json.loads((reports / "validation_report.json").read_text(encoding="utf-8"))
    globalvalues = json.loads((deck_dir / "GlobalValues.json").read_text(encoding="utf-8"))
    profile = json.loads((reports / "globalvalues_profile.json").read_text(encoding="utf-8"))
    deck_identity = json.loads((reports / "deck_identity.json").read_text(encoding="utf-8"))
    baseline = json.loads((reports / "globalvalues_baseline.json").read_text(encoding="utf-8"))
    baseline_receipt = json.loads(
        (reports / "globalvalues_baseline_receipt.json").read_text(encoding="utf-8")
    )

    assert validation_report["status"] == "passed"
    assert set(profile["keys"]) == set(globalvalues)
    assert "RuntimeOnlyFullBaselineKey" in globalvalues
    assert set(baseline) == set(runtime_default)
    assert baseline_receipt["source"] == "runtime_default"
    assert deck_identity["deck_slug"] == "fixture_deck"
    assert deck_identity["card_count_total"] > 0
