from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hsconfig.cli import main


MATRIX = Path("docs/operator/archetype-fixture-matrix.json")


def load_archetype_matrix() -> list[dict[str, Any]]:
    payload = json.loads(MATRIX.read_text(encoding="utf-8"))
    return list(payload["decks"])


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
    operator = json.loads((reports / "operator_summary.json").read_text(encoding="utf-8"))
    readiness = json.loads(
        (reports / "per_card_config_readiness_report.json").read_text(encoding="utf-8")
    )
    coverage = json.loads((reports / "claim_coverage_report.json").read_text(encoding="utf-8"))
    source_gap = json.loads((reports / "source_claim_gap_report.json").read_text(encoding="utf-8"))
    config_root = out / "CustomConfig"
    generated_files = sorted(path.name for path in config_root.rglob("*.json"))
    return {
        "exit_code": code,
        "out": out,
        "operator": operator,
        "readiness": readiness,
        "coverage": coverage,
        "source_gap": source_gap,
        "generated_files": generated_files,
    }
