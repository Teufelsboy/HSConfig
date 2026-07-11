from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.io import write_json


RUNTIME_FILES = {
    "GlobalValues.json": {"GameCardId": "GlobalValues", "ConfigComment": "new"},
    "Mulligan.json": {
        "GameCardId": "Mulligan",
        "ConfigComment": "new",
        "Mulligan": {"values": []},
    },
}


def _write_package(
    package: Path,
    *,
    technical_status: str = "VALID_PACKAGE",
    semantic_status: str = "SOURCE_BACKED_STRONG",
    next_action: str = "READY_TO_APPLY_OR_HANDOFF",
    apply_policy: str = "ALLOWED",
    runtime_files: dict[str, Any] | None = None,
    generated_files: list[str] | None = None,
    write_manifest: bool = True,
    write_summary: bool = True,
    summary_payload: dict[str, Any] | None = None,
) -> Path:
    deck_dir = package / "CustomConfig" / "deck"
    files = dict(RUNTIME_FILES)
    if runtime_files:
        files.update(runtime_files)
    for filename, payload in files.items():
        write_json(deck_dir / filename, payload)

    if write_manifest:
        write_json(
            package / "reports" / "input_manifest.json",
            {"deck_name": "deck", "deck_code": "fixture", "runtime_root": "unused"},
        )

    if write_summary:
        if generated_files is None:
            generated_files = [
                f"CustomConfig/deck/{filename}" for filename in files
            ]
        summary = {
            "technical_status": technical_status,
            "semantic_status": semantic_status,
            "next_action": next_action,
            "apply_policy": apply_policy,
            "semantic_blockers": [],
            "generated_files": generated_files,
        }
        if summary_payload:
            summary.update(summary_payload)
        write_json(package / "reports" / "operator_summary.json", summary)

    return package


@pytest.mark.parametrize(
    "semantic_status,next_action,apply_policy,semantic_blockers",
    [
        ("SOURCE_BACKED_STRONG", "READY_TO_APPLY_OR_HANDOFF", "ALLOWED", []),
        ("STATIC_SEMANTICS_USABLE", "READY_TO_APPLY_WITH_WARNINGS", "ALLOWED_WITH_WARNINGS", []),
        (
            "VALID_BUT_NOT_GUIDE_STRONG",
            "READY_TO_APPLY_WITH_WARNINGS",
            "ALLOWED_WITH_WARNINGS",
            [{"reason": "cards_need_guide_claims", "count": 4}],
        ),
        (
            "NEEDS_MORE_RESEARCH",
            "READY_TO_APPLY_WITH_WARNINGS",
            "ALLOWED_WITH_WARNINGS",
            [{"reason": "cards_need_mulligan_claims", "count": 2}],
        ),
        (
            "LOW_CONFIDENCE_BUT_STRUCTURALLY_VALID",
            "READY_TO_APPLY_WITH_WARNINGS",
            "ALLOWED_WITH_WARNINGS",
            [{"reason": "generic_low_confidence", "count": 30}],
        ),
    ],
)
def test_valid_package_variants_remain_load_safe_apply(
    tmp_path: Path,
    semantic_status: str,
    next_action: str,
    apply_policy: str,
    semantic_blockers: list[dict[str, Any]],
):
    package = _write_package(
        tmp_path / "package",
        semantic_status=semantic_status,
        next_action=next_action,
        apply_policy=apply_policy,
        summary_payload={"semantic_blockers": semantic_blockers},
    )

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "allowed"
    assert gate["allowed"] is True
    assert gate["mode"] == "load_safe_apply"
    assert gate["reasons"] == [
        {
            "reason": "runtime_load_safe_package",
            "technical_status": "VALID_PACKAGE",
            "semantic_status": semantic_status,
            "next_action": next_action,
            "apply_policy": apply_policy,
            "semantic_blocker_count": len(semantic_blockers),
        }
    ]


def test_valid_minimal_package_without_cardid_or_combo_is_allowed(tmp_path: Path):
    package = _write_package(tmp_path / "package")

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "allowed"
    assert gate["allowed"] is True
    assert gate["mode"] == "load_safe_apply"


@pytest.mark.parametrize(
    "mutate,reason",
    [
        (lambda package: (package / "reports" / "operator_summary.json").unlink(), "missing_operator_summary"),
        (lambda package: (package / "reports" / "input_manifest.json").unlink(), "missing_input_manifest"),
        (
            lambda package: (package / "CustomConfig" / "deck" / "GlobalValues.json").unlink(),
            "missing_required_runtime_file",
        ),
        (
            lambda package: (package / "CustomConfig" / "deck" / "Mulligan.json").unlink(),
            "missing_required_runtime_file",
        ),
        (
            lambda package: (package / "reports" / "operator_summary.json").write_text("{", encoding="utf-8"),
            "invalid_operator_summary_json",
        ),
        (
            lambda package: (package / "CustomConfig" / "deck" / "GlobalValues.json").write_text("{", encoding="utf-8"),
            "invalid_runtime_json",
        ),
        (
            lambda package: write_json(package / "CustomConfig" / "deck" / "Presume.json", {}),
            "normal_path_optional_surface_present",
        ),
        (
            lambda package: write_json(package / "CustomConfig" / "deck" / "Concede.json", {}),
            "normal_path_optional_surface_present",
        ),
        (
            lambda package: write_json(package / "CustomConfig" / "deck" / "EX1_999.json", {}),
            "actual_runtime_file_not_in_operator_summary",
        ),
        (
            lambda package: write_json(package / "CustomConfig" / "deck" / "nested" / "EX1_999.json", {}),
            "nested_runtime_file_present",
        ),
    ],
)
def test_structural_hard_blocks_are_still_blocked(tmp_path: Path, mutate, reason: str):
    package = _write_package(tmp_path / "package")
    mutate(package)

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "blocked"
    assert gate["allowed"] is False
    assert gate["mode"] == "blocked"
    assert gate["reasons"][0]["reason"] == reason


def test_declared_runtime_file_missing_from_disk_blocks(tmp_path: Path):
    package = _write_package(
        tmp_path / "package",
        generated_files=[
            "CustomConfig/deck/GlobalValues.json",
            "CustomConfig/deck/Mulligan.json",
            "CustomConfig/deck/EX1_777.json",
        ],
    )

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "blocked"
    assert gate["reasons"] == [
        {
            "reason": "operator_summary_runtime_file_missing",
            "generated_file": "CustomConfig/deck/EX1_777.json",
        }
    ]


def test_summary_runtime_file_drift_blocks(tmp_path: Path):
    package = _write_package(
        tmp_path / "package",
        runtime_files={"EX1_001.json": {"GameCardId": "EX1_001"}},
        generated_files=[
            "CustomConfig/deck/GlobalValues.json",
            "CustomConfig/deck/Mulligan.json",
        ],
    )

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "blocked"
    assert gate["reasons"] == [
        {
            "reason": "actual_runtime_file_not_in_operator_summary",
            "generated_file": str(package / "CustomConfig" / "deck" / "EX1_001.json"),
        }
    ]
