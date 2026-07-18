from __future__ import annotations

import json
from pathlib import Path

from hsconfig.source_closure_optimizer import build_source_closure_optimizer_report


DECKS = {
    "ShadowPriest": {
        "status": "SOURCE_BACKED_STRONG",
        "semantic": "SOURCE_BACKED_STRONG",
        "closed": True,
        "action": "none",
        "decision": "strong",
    },
    "Kingslayer": {
        "status": "SOURCE_BACKED_PARTIAL",
        "semantic": "VALID_BUT_NOT_GUIDE_STRONG",
        "closed": False,
        "action": "add_kingslayer_quick_pick_mulligan_source",
        "decision": "preserved_partial_stop_condition",
    },
    "Boarlock": {
        "status": "SOURCE_BACKED_PARTIAL",
        "semantic": "VALID_BUT_NOT_GUIDE_STRONG",
        "closed": False,
        "action": "add_boarlock_fracking_mulligan_source",
        "decision": "preserved_partial_stop_condition",
    },
    "MechPala": {
        "status": "SOURCE_BACKED_PARTIAL",
        "semantic": "VALID_BUT_NOT_GUIDE_STRONG",
        "closed": False,
        "action": "fetch_runtime_lowerable_public_guide",
        "decision": "partial_source_action_needed",
    },
}


def _write_package(tmp_path: Path, deck_name: str, row: dict[str, object]) -> Path:
    package = tmp_path / deck_name / "04_package"
    reports = package / "reports"
    reports.mkdir(parents=True)
    (reports / "operator_summary.json").write_text(
        json.dumps(
            {
                "deck_name": deck_name,
                "technical_status": "VALID_PACKAGE",
                "runtime_load_safe": True,
                "source_status_apply_blocking": False,
                "source_backed_status": row["status"],
                "semantic_status": row["semantic"],
                "default_only_runtime_surfaces": [],
                "default_only_runtime_surface_details": [],
                "no_default_only_runtime_status": "clean",
                "source_backed_strong_closure": {
                    "closed": row["closed"],
                    "first_missing_source_action": row["action"],
                },
            }
        ),
        encoding="utf-8",
    )
    return package


def test_source_closure_optimizer_preserves_representative_deck_contracts(
    tmp_path: Path,
) -> None:
    proof_manifest = Path("docs/operator/source-candidate-proof-decks.json")
    assert proof_manifest.exists()

    for deck_name, row in DECKS.items():
        package = _write_package(tmp_path, deck_name, row)
        report = build_source_closure_optimizer_report(
            package,
            candidate_proof_path=proof_manifest,
        )

        assert report["deck_name"] == deck_name
        assert report["decision"] == row["decision"]
        assert report["source_status_apply_blocking"] is False
        assert report["runtime_package_usable"] is True
        assert report["default_only_runtime_surfaces"] == []
