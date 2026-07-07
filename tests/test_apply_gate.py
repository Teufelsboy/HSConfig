from pathlib import Path

import pytest

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.io import write_json


def _write_operator_summary(package: Path, payload: dict) -> None:
    write_json(package / "reports" / "operator_summary.json", payload)


def test_apply_gate_allows_source_backed_ready_package(tmp_path: Path):
    package = tmp_path / "package"
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate == {
        "status": "allowed",
        "operator_summary_path": str(package / "reports" / "operator_summary.json"),
        "mode": "source_backed_strong",
        "reasons": [],
    }


def test_apply_gate_blocks_valid_but_not_guide_strong_by_default(tmp_path: Path):
    package = tmp_path / "package"
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "semantic_blockers": [{"reason": "cards_need_guide_claims", "count": 3}],
            "generated_files": ["CustomConfig\\deck\\GlobalValues.json"],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "blocked"
    assert gate["mode"] == "blocked"
    assert gate["reasons"] == [
        {
            "reason": "operator_summary_not_ready_to_apply",
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
        }
    ]


def test_apply_gate_allows_valid_source_informed_package_only_with_explicit_escape_hatch(
    tmp_path: Path,
):
    package = tmp_path / "package"
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "semantic_blockers": [{"reason": "cards_need_runtime_surface", "count": 2}],
            "generated_files": ["CustomConfig\\deck\\GlobalValues.json"],
        },
    )

    gate = evaluate_apply_gate(package, allow_source_informed=True)

    assert gate["status"] == "allowed"
    assert gate["mode"] == "source_informed_with_warnings"
    assert gate["reasons"] == [
        {
            "reason": "source_informed_escape_hatch_used",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
        }
    ]


def test_apply_gate_blocks_invalid_package_even_with_escape_hatch(tmp_path: Path):
    package = tmp_path / "package"
    _write_operator_summary(
        package,
        {
            "technical_status": "INVALID_PACKAGE",
            "semantic_status": "NEEDS_MORE_RESEARCH",
            "next_action": "FIX_PACKAGE_BEFORE_APPLY",
            "apply_policy": "BLOCKED",
            "semantic_blockers": [],
            "generated_files": [],
        },
    )

    gate = evaluate_apply_gate(package, allow_source_informed=True)

    assert gate["status"] == "blocked"
    assert gate["reasons"][0]["reason"] == "operator_summary_not_valid_package"


@pytest.mark.parametrize("surface", ["Presume.json", "Concede.json"])
def test_apply_gate_blocks_normal_path_optional_surfaces(tmp_path: Path, surface: str):
    package = tmp_path / "package"
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": [f"CustomConfig\\deck\\{surface}"],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "blocked"
    assert gate["reasons"] == [
        {
            "reason": "normal_path_optional_surface_present",
            "generated_file": f"CustomConfig\\deck\\{surface}",
        }
    ]


@pytest.mark.parametrize("surface", ["Presume.json", "Concede.json"])
def test_apply_gate_blocks_actual_optional_surface_when_summary_is_stale(
    tmp_path: Path, surface: str
):
    package = tmp_path / "package"
    write_json(package / "CustomConfig" / "deck" / "GlobalValues.json", {})
    write_json(package / "CustomConfig" / "deck" / "Mulligan.json", {})
    write_json(package / "CustomConfig" / "deck" / "EX1_001.json", {})
    write_json(package / "CustomConfig" / "deck" / surface, {})
    _write_operator_summary(
        package,
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
            "generated_files": [
                "CustomConfig\\deck\\GlobalValues.json",
                "CustomConfig\\deck\\Mulligan.json",
                "CustomConfig\\deck\\EX1_001.json",
            ],
        },
    )

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "blocked"
    assert gate["reasons"] == [
        {
            "reason": "normal_path_optional_surface_present",
            "generated_file": str(package / "CustomConfig" / "deck" / surface),
        }
    ]


def test_apply_gate_blocks_missing_operator_summary(tmp_path: Path):
    gate = evaluate_apply_gate(tmp_path / "package")

    assert gate["status"] == "blocked"
    assert gate["reasons"] == [
        {
            "reason": "missing_operator_summary",
            "path": str(tmp_path / "package" / "reports" / "operator_summary.json"),
        }
    ]
