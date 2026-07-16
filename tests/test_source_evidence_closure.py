from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main


SHADOWPRIEST_DECK_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_fixture_package(
    tmp_path: Path,
    *,
    deck_name: str,
    source_documents_fixture: str,
) -> Path:
    package_dir = tmp_path / deck_name
    code = main(
        [
            "prepare",
            "--deck-name",
            deck_name,
            "--deck-code",
            SHADOWPRIEST_DECK_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package_dir),
            "--source-documents-json",
            str(Path("tests/fixtures") / source_documents_fixture),
            "--json",
        ]
    )

    assert code == 0
    return package_dir


def test_source_evidence_closure_reports_profile_verdict(tmp_path: Path):
    package_dir = prepare_fixture_package(
        tmp_path,
        deck_name="ShadowPriest",
        source_documents_fixture="source_documents_shadowpriest_strong.json",
    )

    report = read_json(package_dir / "reports" / "source_evidence_closure.json")

    assert report["closure_profile"] == "aggro_burn_hero_power"
    assert report["closure_profile_closed"] is True
    assert report["closure_profile_first_missing_link"] == "none"
