from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.io import read_json, write_json
from tests.helpers.current_apply_eligible_package import (
    DEFAULT_RUNTIME_FILES,
    write_current_apply_eligible_package,
    write_current_pre_run_contract,
)
from tests.helpers.current_runtime_surface_ledger_contract import (
    write_current_runtime_surface_ledger,
)


RUNTIME_FILES = DEFAULT_RUNTIME_FILES


def _write_package(
    package: Path,
    *,
    technical_status: str = "VALID_PACKAGE",
    semantic_status: str = "SOURCE_BACKED_STRONG",
    next_action: str = "READY_TO_APPLY_OR_HANDOFF",
    apply_policy: str = "ALLOWED",
    runtime_files: dict[str, Any] | None = None,
    generated_files: list[str] | None = None,
    summary_payload: dict[str, Any] | None = None,
) -> Path:
    files = dict(RUNTIME_FILES)
    if runtime_files:
        files.update(runtime_files)
    summary = {
        "technical_status": technical_status,
        "semantic_status": semantic_status,
        "next_action": next_action,
        "apply_policy": apply_policy,
        "semantic_blockers": [],
        **dict(summary_payload or {}),
    }
    summary_files = generated_files
    if summary_files is None:
        payload_generated = summary.get("generated_files")
        summary_files = (
            list(payload_generated)
            if isinstance(payload_generated, list)
            else [f"CustomConfig/deck/{filename}" for filename in files]
        )
    return write_current_apply_eligible_package(
        package,
        operator_summary=summary,
        runtime_files=files,
        generated_files=summary_files,
    )


def _add_runtime_file_after_build(package: Path, filename: str) -> None:
    write_json(
        package / "CustomConfig" / "deck" / filename,
        {
            "GameCardId": filename.removesuffix(".json"),
            "ConfigComment": "added after build",
        },
    )
    write_current_runtime_surface_ledger(package)
    write_current_pre_run_contract(package)


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
    assert gate["policy"] == apply_policy
    expected_reasons = [{"reason": "runtime_load_safe_package"}]
    if semantic_status != "SOURCE_BACKED_STRONG":
        expected_reasons.append(
            {
                "reason": "semantic_strength_incomplete",
                "blocking": False,
            }
        )
    assert gate["reasons"] == expected_reasons


def test_valid_minimal_package_without_cardid_or_combo_is_allowed(tmp_path: Path):
    package = _write_package(tmp_path / "package")

    gate = evaluate_apply_gate(package)
    source_bundle = read_json(package / "reports" / "guide_claim_bundle.json")
    identity = read_json(package / "reports" / "deck_identity.json")
    ledger = read_json(package / "reports" / "runtime_surface_ledger.json")
    canonical_receipt = source_bundle["canonical_source_receipts"][0]

    assert gate["status"] == "allowed"
    assert gate["allowed"] is True
    assert gate["mode"] == "load_safe_apply"
    assert canonical_receipt["receipt_kind"] == (
        "canonical_exact_deck_source_document"
    )
    assert canonical_receipt["matched_deck_fingerprint"] == identity[
        "deck_fingerprint"
    ]
    assert canonical_receipt["claim_id"] == "claim_current_apply_eligible"
    assert canonical_receipt["claim_signature"].startswith("sha256:")
    assert canonical_receipt["acquisition_provenance"]["mode"] == "live_http"
    assert canonical_receipt["acquisition_provenance"]["authority"] == (
        "live_verified"
    )
    assert source_bundle["claims"][0]["acquisition_provenance"] == (
        canonical_receipt["acquisition_provenance"]
    )
    assert ledger["schema_version"] == 2


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
            lambda package: _add_runtime_file_after_build(package, "EX1_999.json"),
            "package_derivation_mismatch",
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
    assert gate["reasons"][0] == {
        "reason": "operator_summary_runtime_file_missing",
        "generated_file": "CustomConfig/deck/EX1_777.json",
    }
    assert gate["reasons"][-1]["reason"] == (
        "operator_summary_apply_decision_mismatch"
    )


def test_summary_runtime_file_drift_blocks(tmp_path: Path):
    package = _write_package(
        tmp_path / "package",
        runtime_files={
            "EX1_001.json": {
                "GameCardId": "EX1_001",
                "ConfigComment": "fixture",
            }
        },
        generated_files=[
            "CustomConfig/deck/GlobalValues.json",
            "CustomConfig/deck/Mulligan.json",
        ],
    )

    gate = evaluate_apply_gate(package)

    assert gate["status"] == "blocked"
    assert gate["reasons"][0] == {
        "reason": "actual_runtime_file_not_in_operator_summary",
        "generated_file": str(package / "CustomConfig" / "deck" / "EX1_001.json"),
    }
    assert gate["reasons"][-1]["reason"] == (
        "operator_summary_apply_decision_mismatch"
    )


@pytest.mark.parametrize(
    "case",
    [
        {
            "name": "clean_source_backed",
            "summary_payload": {
                "technical_status": "VALID_PACKAGE",
                "semantic_status": "SOURCE_BACKED_STRONG",
                "next_action": "READY_TO_APPLY_OR_HANDOFF",
                "apply_policy": "ALLOWED",
                "semantic_blockers": [],
            },
            "mutate": None,
            "expected_status": "allowed",
            "expected_reason": "runtime_load_safe_package",
        },
        {
            "name": "valid_with_warning_only_mechanics",
            "summary_payload": {
                "technical_status": "VALID_PACKAGE",
                "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
                "next_action": "READY_TO_APPLY_WITH_WARNINGS",
                "apply_policy": "ALLOWED_WITH_WARNINGS",
                "semantic_blockers": [
                    {"reason": "warning_only_mechanic", "mechanic": "secret_timing"},
                    {"reason": "future_mechanic_drift", "mechanic": "rewind"},
                ],
            },
            "mutate": None,
            "expected_status": "allowed",
            "expected_reason": "runtime_load_safe_package",
        },
        {
            "name": "stale_summary_missing_actual_cardid",
            "summary_payload": {
                "technical_status": "VALID_PACKAGE",
                "semantic_status": "SOURCE_BACKED_STRONG",
                "next_action": "READY_TO_APPLY_OR_HANDOFF",
                "apply_policy": "ALLOWED",
                "semantic_blockers": [],
                "generated_files": [
                    "CustomConfig/deck/GlobalValues.json",
                    "CustomConfig/deck/Mulligan.json",
                ],
            },
            "mutate": lambda package: _add_runtime_file_after_build(
                package,
                "EX1_777.json",
            ),
            "expected_status": "blocked",
            "expected_reason": "package_derivation_mismatch",
        },
        {
            "name": "legacy_optional_surface",
            "summary_payload": {
                "technical_status": "VALID_PACKAGE",
                "semantic_status": "SOURCE_BACKED_STRONG",
                "next_action": "READY_TO_APPLY_OR_HANDOFF",
                "apply_policy": "ALLOWED",
                "semantic_blockers": [],
            },
            "mutate": lambda package: write_json(
                package / "CustomConfig" / "deck" / "Presume.json",
                {},
            ),
            "expected_status": "blocked",
            "expected_reason": "normal_path_optional_surface_present",
        },
    ],
    ids=lambda case: case["name"],
)
def test_apply_gate_contract_matrix_keeps_warnings_open_and_technical_blocks_closed(
    tmp_path: Path,
    case: dict[str, Any],
):
    package = _write_package(
        tmp_path / "package",
        summary_payload=case["summary_payload"],
    )
    if case["mutate"] is not None:
        case["mutate"](package)

    gate = evaluate_apply_gate(package)

    assert gate["status"] == case["expected_status"]
    assert gate["reasons"][0]["reason"] == case["expected_reason"]
