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


def _run_cli(capsys: pytest.CaptureFixture[str], args: list[str]) -> tuple[dict[str, Any], int]:
    code = main([*args, "--json"])
    captured = capsys.readouterr()
    assert captured.err == ""
    return json.loads(captured.out), code


def _write_strict_package(package: Path) -> None:
    globalvalues = {
        "GameCardId": "GlobalValues",
        "ConfigComment": "strict validation fixture",
    }
    write_json(package / "CustomConfig" / "deck" / "GlobalValues.json", globalvalues)
    write_json(
        package / "CustomConfig" / "deck" / "Mulligan.json",
        {
            "GameCardId": "Mulligan",
            "ConfigComment": "strict validation fixture",
            "Mulligan": {"values": []},
        },
    )
    write_json(
        package / "CustomConfig" / "deck" / "EX1_001.json",
        {
            "GameCardId": "EX1_001",
            "ConfigComment": "strict validation fixture",
            "InHandPlayPriority": {"values": []},
        },
    )
    write_json(package / "reports" / "globalvalues_baseline.json", globalvalues)
    write_json(
        package / "reports" / "globalvalues_profile.json",
        {
            "key_count": len(globalvalues),
            "keys": {key: {"status": "unchanged"} for key in globalvalues},
            "generated_overlay_keys": [],
            "summary": {"all_expected_overlay_keys_accounted_for": True},
            "expected_overlay_keys": [],
            "missing_overlay_keys": [],
        },
    )
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "Strict Fixture", "deck_code": "fixture", "runtime_root": "unused"},
    )
    write_json(
        package / "reports" / "operator_summary.json",
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "runtime_apply_contract": {
                "apply_authority": "reports/operator_summary.json",
            },
            "source_status_apply_blocking": False,
            "default_only_runtime_surfaces": [],
            "semantic_blockers": [],
            "generated_files": [
                "CustomConfig/deck/GlobalValues.json",
                "CustomConfig/deck/Mulligan.json",
                "CustomConfig/deck/EX1_001.json",
            ],
        },
    )


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


def _mutate_package_report(package: Path, mutation: str) -> None:
    reports = package / "reports"
    if mutation == "missing_baseline":
        (reports / "globalvalues_baseline.json").unlink()
        return
    if mutation == "missing_profile":
        (reports / "globalvalues_profile.json").unlink()
        return
    profile_path = reports / "globalvalues_profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    profile["missing_overlay_keys"] = ["GlobalMinionAttack"]
    write_json(profile_path, profile)


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
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "build-runtime"),
            "--out",
            str(tmp_path / "build-package"),
            "--allow-placeholder",
        ],
    )


def test_valid_package_passes_build_validate_apply_and_preflight(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    _write_strict_package(package)

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

    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    _write_strict_package(package)
    _mutate_package_report(package, mutation)

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
