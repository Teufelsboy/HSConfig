from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import pytest

from hsconfig import package_builder
from hsconfig.cli import main
from hsconfig.contract_preflight import build_package_contract_preflight
from hsconfig.io import write_json
from hsconfig.strict_package_validation import validate_complete_package
from tests.helpers.verified_deck_input import VERIFIED_TEST_DECK_CODE


@pytest.mark.parametrize(
    ("report", "expected"),
    [
        ({"status": "passed", "errors": []}, True),
        ({"status": "passed", "errors": ["contradictory error"]}, False),
        ({"status": "failed", "errors": []}, False),
        ({}, False),
    ],
)
def test_strict_validation_passed_requires_clean_passed_report(
    report: dict[str, Any],
    expected: bool,
) -> None:
    from hsconfig.strict_package_validation import strict_validation_passed

    assert strict_validation_passed(report) is expected


def _run_cli(capsys: pytest.CaptureFixture[str], args: list[str]) -> tuple[dict[str, Any], int]:
    code = main([*args, "--json"])
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out), code


def _clean_quality_report(_package: Path) -> dict[str, Any]:
    return {
        "status": "clean",
        "checks": {
            "operator_summary": {
                "present": True,
                "source_status_apply_blocking": False,
                "default_only_runtime_surfaces": [],
            },
            "closure_freshness": {
                "closure_schema_current": True,
                "cards_missing_closure": 0,
            },
            "config_intent_self_audit": {"status": "clean"},
            "surface_intent_projection": {
                "status": "clean",
                "present": True,
                "surface_count": 3,
                "fallback_intent_rows": [],
                "legacy_policy_surface_rows": [],
                "first_attention": None,
            },
        },
        "problems": [],
        "semantic_handoff_status": "closed",
        "semantic_handoff_reasons": [],
    }


def _configure_builder_report_mutation(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    original_write_json = package_builder.write_json

    def write_mutated_report(path: Path, payload: Any) -> None:
        if mutation == "missing_baseline" and path.name == "globalvalues_baseline.json":
            return
        if mutation == "missing_profile" and path.name == "globalvalues_profile.json":
            return
        if mutation == "missing_overlay_keys" and path.name == "globalvalues_profile.json":
            mutated_profile = deepcopy(payload)
            mutated_profile["missing_overlay_keys"] = ["GlobalMinionAttack"]
            original_write_json(path, mutated_profile)
            return
        original_write_json(path, payload)

    monkeypatch.setattr(package_builder, "write_json", write_mutated_report)


def _build_fixture(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> tuple[dict[str, Any], int]:
    return _run_cli(
        capsys,
        [
            "build",
            "--deck-name",
            "Strict Fixture",
            "--deck-code",
            VERIFIED_TEST_DECK_CODE,
            "--runtime-root",
            str(tmp_path / "build-runtime"),
            "--out",
            str(tmp_path / "build-package"),
        ],
    )


def test_valid_package_passes_build_validate_apply_and_preflight(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    package = Path(build_result["package"])
    runtime = tmp_path / "runtime"

    validate_result, validate_code = _run_cli(
        capsys,
        ["validate", "--package", str(package)],
    )
    apply_result, apply_code = _run_cli(
        capsys,
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(runtime),
            "--fake",
        ],
    )
    monkeypatch.setattr(
        "hsconfig.config_quality_contract.build_config_quality_report",
        _clean_quality_report,
    )
    preflight = build_package_contract_preflight(package)

    assert build_code == 0
    assert build_result["status"] == "passed"
    assert validate_code == 0
    assert validate_result["status"] == "passed"
    assert apply_code == 0
    assert apply_result["status"] == "fake_apply_ready"
    assert not runtime.exists()
    assert preflight is not None
    assert preflight["validation_status"] == "passed"
    assert preflight["package_contract_current"] is True
    assert preflight["authority"] == "diagnostic_only"
    assert preflight["apply_blocking"] is False
    assert preflight["runtime_write_performed"] is False


@pytest.mark.parametrize(
    "mutation",
    ["missing_baseline", "missing_profile", "missing_overlay_keys"],
)
def test_invalid_globalvalues_reports_fail_all_strict_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    _configure_builder_report_mutation(monkeypatch, mutation)
    build_result, build_code = _build_fixture(tmp_path, capsys)

    package = tmp_path / "build-package"
    runtime = tmp_path / "runtime"

    validate_result, validate_code = _run_cli(
        capsys,
        ["validate", "--package", str(package)],
    )
    apply_result, apply_code = _run_cli(
        capsys,
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(runtime),
            "--fake",
        ],
    )
    monkeypatch.setattr(
        "hsconfig.config_quality_contract.build_config_quality_report",
        _clean_quality_report,
    )
    preflight = build_package_contract_preflight(package)

    assert preflight is not None
    assert preflight["validation_status"] == "failed"
    assert preflight["package_contract_current"] is False
    assert preflight["authority"] == "diagnostic_only"
    assert preflight["apply_blocking"] is False
    assert preflight["runtime_write_performed"] is False
    assert build_code == 1
    assert build_result["status"] == "failed"
    assert validate_code == 1
    assert validate_result["status"] == "failed"
    assert apply_code == 1
    assert apply_result["status"] in {"failed", "blocked"}
    assert not runtime.exists()


def test_strict_validation_rejects_linked_runtime_filename_gamecardid_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    assert build_code == 0
    package = Path(build_result["package"])
    deck_dir = next((package / "CustomConfig").iterdir())
    write_json(
        package / "reports" / "card_behavior_plan_report.json",
        {
            "rows": [
                {
                    "claim_id": "claim_darkbishop",
                    "card_id": "SW_448",
                    "source_card_id": "SW_448",
                    "runtime_card_id": "EX1_625t",
                    "link_kind": "hero_power_transform",
                    "behavior_block": "BeforeUseHeroPowerBonus",
                    "semantic_score": {
                        "semantic_reason": "hero_power_transform",
                    },
                    "meaningful_runtime_surface": True,
                }
            ]
        },
    )
    write_json(
        deck_dir / "EX1_625t.json",
        {
            "GameCardId": "SW_448",
            "ConfigComment": "wrong linked runtime owner",
            "BeforeUseHeroPowerBonus": {
                "values": [{"condition": "*", "value": "10"}]
            },
        },
    )

    report = validate_complete_package(package)

    assert report["status"] == "failed"
    assert any(
        "linked runtime entity filename/GameCardId mismatch: "
        "EX1_625t.json owns EX1_625t, got SW_448"
        in error
        for error in report["errors"]
    )


def test_strict_validation_accepts_exact_curated_linked_runtime_relation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    assert build_code == 0
    package = Path(build_result["package"])
    deck_dir = next((package / "CustomConfig").iterdir())
    write_json(
        package / "reports" / "card_behavior_plan_report.json",
        {
            "rows": [
                {
                    "claim_id": "claim_darkbishop",
                    "card_id": "SW_448",
                    "source_card_id": "SW_448",
                    "runtime_card_id": "EX1_625t",
                    "link_kind": "hero_power_transform",
                    "behavior_block": "BeforeUseHeroPowerBonus",
                    "semantic_score": {
                        "semantic_reason": "hero_power_transform",
                    },
                    "meaningful_runtime_surface": True,
                }
            ]
        },
    )
    write_json(
        deck_dir / "EX1_625t.json",
        {
            "GameCardId": "EX1_625t",
            "ConfigComment": "curated linked runtime owner",
            "BeforeUseHeroPowerBonus": {
                "values": [{"condition": "*", "value": "10"}]
            },
        },
    )

    report = validate_complete_package(package)

    assert report["status"] == "passed"
    assert report["errors"] == []


@pytest.mark.parametrize(
    (
        "source_card_id",
        "runtime_card_id",
        "link_kind",
        "behavior_block",
    ),
    [
        (
            "SW_448",
            "SW_448",
            "hero_power_transform",
            "BeforeUseHeroPowerBonus",
        ),
        (
            "SW_448",
            "WRONG_TARGET",
            "hero_power_transform",
            "BeforeUseHeroPowerBonus",
        ),
        (
            "SW_448",
            "EX1_625t",
            "wrong_link",
            "BeforeUseHeroPowerBonus",
        ),
        (
            "SW_448",
            "EX1_625t",
            "hero_power_transform",
            "OnBoardBonus",
        ),
    ],
)
def test_strict_validation_rejects_non_curated_linked_runtime_relation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    source_card_id: str,
    runtime_card_id: str,
    link_kind: str,
    behavior_block: str,
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    assert build_code == 0
    package = Path(build_result["package"])
    write_json(
        package / "reports" / "card_behavior_plan_report.json",
        {
            "rows": [
                {
                    "claim_id": "invalid_linked_owner",
                    "card_id": source_card_id,
                    "source_card_id": source_card_id,
                    "runtime_card_id": runtime_card_id,
                    "link_kind": link_kind,
                    "behavior_block": behavior_block,
                    "semantic_score": {
                        "semantic_reason": "hero_power_transform",
                    },
                    "meaningful_runtime_surface": True,
                }
            ]
        },
    )

    report = validate_complete_package(package)

    assert report["status"] == "failed"
    assert any(
        error.startswith("linked_runtime_entity_relation_invalid:")
        for error in report["errors"]
    )
