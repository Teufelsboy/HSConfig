import json
from pathlib import Path

from hsconfig.cli import main
from hsconfig.io import write_json


def test_runtime_match_cli_reports_matched_package(tmp_path: Path, capsys):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    for root in (package, runtime):
        deck = root / "CustomConfig" / "shadowpriest"
        deck.mkdir(parents=True)
        write_json(deck / "GlobalValues.json", {"GameCardId": "GlobalValues"})
        write_json(deck / "Mulligan.json", {"Mulligan": {"values": []}})
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        "ShadowPriest=shadowpriest\n",
        encoding="utf-8",
    )

    code = main([
        "runtime-match",
        "--package",
        str(package),
        "--runtime-root",
        str(runtime),
        "--json",
    ])

    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["status"] == "matched"
    assert out["runtime_write_performed"] is False


def test_runtime_match_cli_returns_nonzero_for_mismatch(tmp_path: Path, capsys):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    (package / "CustomConfig" / "shadowpriest").mkdir(parents=True)
    (runtime / "CustomConfig" / "shadowpriest").mkdir(parents=True)
    write_json(package / "CustomConfig" / "shadowpriest" / "GlobalValues.json", {"GameCardId": "GlobalValues"})
    write_json(runtime / "CustomConfig" / "shadowpriest" / "GlobalValues.json", {"GameCardId": "Other"})

    code = main([
        "runtime-match",
        "--package",
        str(package),
        "--runtime-root",
        str(runtime),
        "--config-dir",
        "shadowpriest",
        "--json",
    ])

    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert out["status"] == "mismatch"
