from __future__ import annotations

from pathlib import Path

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.io import write_json
from hsconfig.surface_intent import build_surface_intent


LEGACY_SURFACES = {"Presume.json", "Concede.json"}


def test_surface_intent_ignores_legacy_policy_surfaces_in_normal_path():
    contract = {
        "cards": {},
        "mulligan_anchors": [],
        "combos": [],
        "legacy_policy_surfaces_enabled": True,
        "policies": {
            "presume": [{"source_claim_ids": ["claim-presume"]}],
            "concede": [{"source_claim_ids": ["claim-concede"]}],
        },
    }

    intent = build_surface_intent(contract)

    assert set(intent["optional_surfaces"]).isdisjoint(LEGACY_SURFACES)
    assert all(row["surface"] not in LEGACY_SURFACES for row in intent["rows"])
    assert set(intent["required_surfaces"]) == {"GlobalValues.json", "Mulligan.json"}


def _write_minimal_package(
    package: Path,
    *,
    technical_status: str = "VALID_PACKAGE",
) -> None:
    deck_dir = package / "CustomConfig" / "deck"
    reports = package / "reports"
    deck_dir.mkdir(parents=True)
    reports.mkdir(parents=True)
    write_json(deck_dir / "GlobalValues.json", {})
    write_json(deck_dir / "Mulligan.json", {"mulligan": []})
    write_json(reports / "input_manifest.json", {"deck_name": "deck"})
    write_json(
        reports / "operator_summary.json",
        {
            "technical_status": technical_status,
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "generated_files": [
                "CustomConfig/deck/GlobalValues.json",
                "CustomConfig/deck/Mulligan.json",
            ],
        },
    )


def test_allow_source_informed_does_not_change_apply_gate(tmp_path):
    package = tmp_path / "package"
    _write_minimal_package(package)

    normal = evaluate_apply_gate(package)
    legacy_flag = evaluate_apply_gate(package, allow_source_informed=True)

    assert legacy_flag == normal
    assert normal["status"] == "allowed"
