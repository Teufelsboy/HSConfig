import json
from pathlib import Path

from hsconfig.cli import main


SUPPLEMENTAL_PATH = Path("docs/operator/supplemental-proof-decks.json")


def test_supplemental_fixtures_separate_load_safety_from_apply_authority():
    manifest = json.loads(SUPPLEMENTAL_PATH.read_text(encoding="utf-8"))
    rows = {row["deck_name"]: row for row in manifest["decks"]}

    assert set(rows) == {"CuteWarrior", "SecretMage", "HighlanderPriest"}
    for row in rows.values():
        assert row["fixture_expected_load_safe"] is True
        assert row["fixture_runtime_apply_authority"] == "diagnostic_only"
        assert "runtime_apply_allowed" not in row

    cute_warrior = rows["CuteWarrior"]
    assert cute_warrior["proof_scope"] == "supplemental_load_safe_only"
    assert cute_warrior["representative_output_competence"] is False


def test_cute_warrior_supplemental_prepare_path_is_load_safe(
    tmp_path: Path,
    capsys,
    monkeypatch,
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    out = tmp_path / "CuteWarrior"

    code = main(
        [
            "prepare",
            "--deck-name",
            "CuteWarrior",
            "--deck-code",
            "AAEBAQcEkbwCkdAD69YHstgHDY0Q6bADpLYDxN4D/9sEj5UFlaoFtNEF9PIFovoF/KgGltMGtI8HAAA=",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    operator = json.loads((out / "reports" / "operator_summary.json").read_text(encoding="utf-8"))
    custom_config_dirs = list((out / "CustomConfig").iterdir())
    deck_dir = custom_config_dirs[0]
    card_files = [
        path
        for path in deck_dir.glob("*.json")
        if path.name not in {"Combo.json", "GlobalValues.json", "Mulligan.json"}
    ]

    assert code == 0
    assert payload["status"] == "passed"
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_load_safe"] is True
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["runtime_apply_allowed"] is True
    assert operator["runtime_apply_reason"] == (
        "current_package_operator_gate_allowed"
    )
    assert operator["runtime_apply_contract"]["authority_scope"] == (
        "current_package_operator_gate"
    )
    assert (deck_dir / "GlobalValues.json").is_file()
    assert (deck_dir / "Mulligan.json").is_file()
    assert card_files
