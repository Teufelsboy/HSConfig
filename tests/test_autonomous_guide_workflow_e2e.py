import json
from pathlib import Path

import pytest

from hsconfig.cli import main


DECKS = [
    (
        "ShadowPriest",
        "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
    ),
    (
        "BigShaman",
        "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==",
    ),
    (
        "PirateRogue",
        "AAEBAaIHApG8AuXRAg6MAtQF+w/psAPz3QOvoASKyQSa2wTXowW/9wXWngb8pQb8qAatxQYAAA==",
    ),
]


@pytest.mark.parametrize(("deck_name", "deck_code"), DECKS)
def test_autonomous_guide_workflow_builds_valid_deck_neutral_package(
    tmp_path: Path, capsys, deck_name: str, deck_code: str
):
    research = tmp_path / deck_name / "research"
    package = tmp_path / deck_name / "package"

    research_code = main(
        [
            "research-deck",
            "--deck-name",
            deck_name,
            "--deck-code",
            deck_code,
            "--out",
            str(research),
            "--json",
        ]
    )
    research_payload = json.loads(capsys.readouterr().out)

    prepare_code = main(
        [
            "prepare",
            "--deck-name",
            deck_name,
            "--deck-code",
            deck_code,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--guide-sources-json",
            str(research / "guide_sources.json"),
            "--json",
        ]
    )
    prepare_payload = json.loads(capsys.readouterr().out)
    reports = package / "reports"
    operator_summary = json.loads((reports / "operator_summary.json").read_text(encoding="utf-8"))
    deck_slug = prepare_payload["deck_slug"]
    deck_dir = package / "CustomConfig" / deck_slug

    assert research_code == 0
    assert research_payload["status"] == "OK"
    assert prepare_code == 0
    assert operator_summary["technical_status"] == "VALID_PACKAGE"
    assert (deck_dir / "GlobalValues.json").exists()
    assert (deck_dir / "Mulligan.json").exists()
    assert any(
        path.suffix == ".json"
        and path.name not in {"GlobalValues.json", "Mulligan.json", "Combo.json"}
        for path in deck_dir.iterdir()
    )
    assert "operator_summary" in prepare_payload
