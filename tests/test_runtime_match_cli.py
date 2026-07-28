import json
from pathlib import Path

import pytest

from hsconfig.cli import main
from hsconfig.io import write_json


def _write_runtime_match_fixture(
    package: Path,
    runtime: Path,
    *,
    mapping_line: str,
) -> None:
    for root in (package, runtime):
        deck = root / "CustomConfig" / "shadowpriest"
        deck.mkdir(parents=True)
        write_json(deck / "GlobalValues.json", {"GameCardId": "GlobalValues"})
        write_json(deck / "Mulligan.json", {"Mulligan": {"values": []}})
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        mapping_line,
        encoding="utf-8",
    )


def test_runtime_match_cli_reports_matched_package(tmp_path: Path, capsys):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    _write_runtime_match_fixture(
        package,
        runtime,
        mapping_line="ShadowPriest=shadowpriest\n",
    )
    write_json(
        package / "reports" / "input_manifest.json",
        {
            "deck_name": "ShadowPriest",
            "deck_code": "fixture",
            "runtime_root": "unused",
        },
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


@pytest.mark.parametrize(
    ("manifest", "mapping_line"),
    [
        (None, "shadowpriest=shadowpriest\n"),
        (
            {
                "deck_name": "",
                "deck_code": "fixture",
                "runtime_root": "unused",
            },
            "shadowpriest=shadowpriest\n",
        ),
        (["shadowpriest"], "shadowpriest=shadowpriest\n"),
        ({"deck_name": "ShadowPriest"}, "ShadowPriest=shadowpriest\n"),
    ],
)
def test_runtime_match_cli_fails_closed_without_verified_manifest_identity(
    tmp_path: Path,
    capsys,
    manifest: object | None,
    mapping_line: str,
):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    _write_runtime_match_fixture(
        package,
        runtime,
        mapping_line=mapping_line,
    )
    if manifest is not None:
        write_json(package / "reports" / "input_manifest.json", manifest)

    code = main([
        "runtime-match",
        "--package",
        str(package),
        "--runtime-root",
        str(runtime),
        "--json",
    ])

    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert out["status"] == "failed"
    assert out["errors"]


def test_runtime_match_cli_returns_nonzero_for_mismatch(tmp_path: Path, capsys):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    (package / "CustomConfig" / "shadowpriest").mkdir(parents=True)
    (runtime / "CustomConfig" / "shadowpriest").mkdir(parents=True)
    write_json(package / "CustomConfig" / "shadowpriest" / "GlobalValues.json", {"GameCardId": "GlobalValues"})
    write_json(runtime / "CustomConfig" / "shadowpriest" / "GlobalValues.json", {"GameCardId": "Other"})
    write_json(
        package / "reports" / "input_manifest.json",
        {
            "deck_name": "ShadowPriest",
            "deck_code": "fixture",
            "runtime_root": "unused",
        },
    )

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
