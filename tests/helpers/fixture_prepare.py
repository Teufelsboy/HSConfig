from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hsconfig.audited_deck_catalog import load_audited_role_manifest
from hsconfig.cli import main


MATRIX = Path("docs/operator/archetype-fixture-matrix.json")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_archetype_matrix() -> list[dict[str, Any]]:
    return load_audited_role_manifest(MATRIX)


def fixture_path_for(deck: dict[str, Any]) -> Path:
    deck_name = str(deck["deck_name"]).lower()
    return Path(f"tests/fixtures/source_documents_{deck_name}_strong.json")


def prepare_fixture_deck(tmp_path: Path, deck: dict[str, Any]) -> dict[str, Any]:
    out = tmp_path / str(deck["deck_name"])
    code = main(
        [
            "prepare",
            "--deck-name",
            str(deck["deck_name"]),
            "--deck-code",
            str(deck["deck_code"]),
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--source-documents-json",
            str(fixture_path_for(deck)),
            "--json",
        ]
    )

    reports = out / "reports"
    operator = read_json(reports / "operator_summary.json")
    readiness = read_json(reports / "per_card_config_readiness_report.json")
    coverage = read_json(reports / "claim_coverage_report.json")
    source_gap = read_json(reports / "source_claim_gap_report.json")
    strong_promotion = read_json(reports / "strong_promotion_report.json")
    config_root = out / "CustomConfig"
    generated_files = sorted(path.name for path in config_root.rglob("*.json"))
    return {
        "exit_code": code,
        "out": out,
        "operator": operator,
        "readiness": readiness,
        "coverage": coverage,
        "source_gap": source_gap,
        "source_claim_gap_report": source_gap,
        "strong_promotion_report": strong_promotion,
        "generated_files": generated_files,
    }
