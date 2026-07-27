from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import pytest

from hsconfig import package_builder
import hsconfig.strict_package_validation as strict_package_validation
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
        if (
            mutation == "missing_authority_matrix"
            and path.name == "global_values_authority_matrix.json"
        ):
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


@pytest.mark.parametrize(
    "forgery",
    ["generated_overlay", "baseline_overlay"],
)
def test_strict_validation_binds_globalvalues_to_canonical_authority_matrix(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    forgery: str,
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    assert build_code == 0
    package = Path(build_result["package"])
    reports = package / "reports"
    deck_dir = next((package / "CustomConfig").iterdir())
    config_path = deck_dir / "GlobalValues.json"
    profile_path = reports / "globalvalues_profile.json"
    authority = json.loads(
        (reports / "global_values_authority_matrix.json").read_text(
            encoding="utf-8"
        )
    )
    config = json.loads(config_path.read_text(encoding="utf-8"))
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    assert {
        row["key"] for row in authority["allowed_step1_overlays"]
    } == {"baseline"}

    if forgery == "generated_overlay":
        key = "MyHeroPowerValue"
        config[key] = {"values": [{"condition": "*", "value": "1.15"}]}
        profile["generated_overlay_keys"] = [key]
        profile["expected_overlay_keys"] = [key]
        profile["authority_parity"] = {
            "authorized_overlay_keys": [key],
            "emitted_overlay_keys": [key],
            "status": "matched",
        }
        profile["keys"][key] = {
            "decision": "overlay_changed",
            "status": "overlay_changed",
            "reason": "forged generated overlay",
        }
        profile["key_count"] = len(config)
    else:
        key = "GlobalMinionAttack"
        config[key]["values"][0]["value"] = "999"
        profile["baseline_overlay_parity"] = {
            "authorized_overlay_keys": [key],
            "emitted_overlay_keys": [key],
            "status": "matched",
        }
        profile["keys"][key].update(
            {
                "decision": "overlay_changed",
                "status": "overlay_changed",
                "new_value": "999",
                "reason": "forged baseline overlay",
            }
        )
        profile["changed_keys"] = [key]
        profile["unchanged_keys"] = [
            existing
            for existing in profile["unchanged_keys"]
            if existing != key
        ]

    profile["summary"].update(
        {
            "authority_parity": profile["authority_parity"],
            "baseline_overlay_parity": profile["baseline_overlay_parity"],
            "changed_key_count": len(profile["changed_keys"]),
            "unchanged_key_count": len(profile["unchanged_keys"]),
            "expected_overlay_key_count": len(profile["expected_overlay_keys"]),
            "generated_overlay_key_count": len(profile["generated_overlay_keys"]),
            "key_count": profile["key_count"],
        }
    )
    write_json(config_path, config)
    write_json(profile_path, profile)

    report = validate_complete_package(package)

    assert report["status"] == "failed"
    assert any(
        "GlobalValues config does not match canonical authority matrix" in error
        or "GlobalValues profile does not match canonical authority matrix" in error
        for error in report["errors"]
    )


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        (
            "string_schema",
            "GlobalValues profile schema_version must be a non-bool integer",
        ),
        (
            "schema_downgrade",
            "GlobalValues authority matrix requires profile schema_version 2",
        ),
        (
            "duplicate_ledgers",
            "GlobalValues profile generated_overlay_keys contains duplicate key "
            "MyHeroPowerValue",
        ),
    ],
)
def test_strict_validation_rejects_schema_downgrade_and_duplicate_ledgers(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mutation: str,
    expected_error: str,
) -> None:
    build_result, build_code = _build_fixture(tmp_path, capsys)
    assert build_code == 0
    package = Path(build_result["package"])
    reports = package / "reports"
    deck_dir = next((package / "CustomConfig").iterdir())
    config_path = deck_dir / "GlobalValues.json"
    profile_path = reports / "globalvalues_profile.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    profile = json.loads(profile_path.read_text(encoding="utf-8"))

    if mutation == "string_schema":
        profile["schema_version"] = "2"
    elif mutation == "schema_downgrade":
        profile["schema_version"] = 1
        profile.pop("authority_parity")
        profile.pop("baseline_overlay_parity")
        profile["summary"].pop("authority_parity")
        profile["summary"].pop("baseline_overlay_parity")
    else:
        key = "MyHeroPowerValue"
        profile["schema_version"] = 1
        profile.pop("authority_parity")
        profile.pop("baseline_overlay_parity")
        profile["summary"].pop("authority_parity")
        profile["summary"].pop("baseline_overlay_parity")
        config[key] = {"values": [{"condition": "*", "value": "1.15"}]}
        profile["generated_overlay_keys"] = [key, key]
        profile["expected_overlay_keys"] = [key, key]
        profile["keys"][key] = {
            "decision": "overlay_changed",
            "status": "overlay_changed",
            "reason": "forged duplicate ledger",
        }
        profile["key_count"] = len(config)

    write_json(config_path, config)
    write_json(profile_path, profile)

    report = validate_complete_package(package)

    assert report["status"] == "failed"
    assert any(expected_error in error for error in report["errors"])


@pytest.fixture
def linked_owner_package(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> Path:
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
    return package


@pytest.mark.parametrize(
    "mutation",
    [
        "remove",
        "invalid_json",
        "non_object",
        "empty_rows",
        "invalid_rows_container",
    ],
)
def test_linked_owner_package_fails_closed_without_valid_plan_report(
    linked_owner_package: Path,
    mutation: str,
) -> None:
    path = linked_owner_package / "reports" / "card_behavior_plan_report.json"
    if mutation == "remove":
        path.unlink()
    elif mutation == "invalid_json":
        path.write_text("{", encoding="utf-8")
    elif mutation == "non_object":
        path.write_text("[]", encoding="utf-8")
    elif mutation == "empty_rows":
        write_json(path, {"rows": []})
    else:
        write_json(path, {"rows": {}})

    report = validate_complete_package(linked_owner_package)

    assert report["status"] == "failed"
    assert any(
        code in report["errors"]
        for code in {
            "linked_runtime_owner_evidence_missing",
            "linked_runtime_owner_evidence_invalid",
        }
    )


def test_linked_runtime_owner_projection_has_exact_authority_fields() -> None:
    projection = strict_package_validation.linked_runtime_owner_projection(
        {
            "rows": [
                {
                    "claim_id": "claim_darkbishop",
                    "card_id": "SW_448",
                    "source_card_id": "SW_448",
                    "runtime_card_id": "EX1_625t",
                    "link_kind": "hero_power_transform",
                    "behavior_block": "BeforeUseHeroPowerBonus",
                    "meaningful_runtime_surface": True,
                    "diagnostic_prose": "must not enter authority",
                }
            ]
        }
    )

    assert projection == [
        {
            "source_card_id": "SW_448",
            "runtime_card_id": "EX1_625t",
            "link_kind": "hero_power_transform",
            "semantic_surface": "hero_power_before_use",
            "behavior_block": "BeforeUseHeroPowerBonus",
        }
    ]


@pytest.mark.parametrize(
    "rows",
    [{}, None, "corrupt", [None]],
    ids=["object", "null", "string", "non_object_row"],
)
def test_ownerless_package_rejects_invalid_behavior_plan_rows(
    linked_owner_package: Path,
    rows: object,
) -> None:
    for owner_path in (linked_owner_package / "CustomConfig").glob(
        "*/EX1_625t.json"
    ):
        owner_path.unlink()
    write_json(
        linked_owner_package
        / "reports"
        / "card_behavior_plan_report.json",
        {"rows": rows},
    )

    report = validate_complete_package(linked_owner_package)

    assert report["status"] == "failed"
    assert "linked_runtime_owner_evidence_invalid" in report["errors"]


@pytest.mark.parametrize(
    "rows",
    [{}, None, "corrupt", [None]],
    ids=["object", "null", "string", "non_object_row"],
)
def test_linked_runtime_owner_projection_rejects_invalid_rows(
    rows: object,
) -> None:
    with pytest.raises(
        ValueError,
        match="^linked_runtime_owner_evidence_invalid$",
    ):
        strict_package_validation.linked_runtime_owner_projection(
            {"rows": rows}
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
    [
        "missing_baseline",
        "missing_profile",
        "missing_authority_matrix",
        "missing_overlay_keys",
    ],
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


def test_strict_validation_rejects_linked_relation_masked_as_not_meaningful(
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
                    "claim_id": "masked_linked_owner",
                    "card_id": "SW_448",
                    "source_card_id": "SW_448",
                    "runtime_card_id": "EX1_625t",
                    "link_kind": "hero_power_transform",
                    "behavior_block": "BeforeUseHeroPowerBonus",
                    "semantic_score": {
                        "semantic_reason": "hero_power_before_use",
                    },
                    "meaningful_runtime_surface": False,
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

    assert report["status"] == "failed"
    assert any(
        error.startswith("linked_runtime_entity_relation_invalid:")
        for error in report["errors"]
    )


@pytest.mark.parametrize(
    (
        "source_card_id",
        "runtime_card_id",
        "link_kind",
        "behavior_block",
        "semantic_reason",
    ),
    [
        (
            "SW_448",
            "SW_448",
            "hero_power_transform",
            "BeforeUseHeroPowerBonus",
            "hero_power_transform",
        ),
        (
            "SW_448",
            "WRONG_TARGET",
            "hero_power_transform",
            "BeforeUseHeroPowerBonus",
            "hero_power_transform",
        ),
        (
            "SW_448",
            "EX1_625t",
            "wrong_link",
            "BeforeUseHeroPowerBonus",
            "hero_power_before_use",
        ),
        (
            "SW_448",
            "EX1_625t",
            "hero_power_transform",
            "OnBoardBonus",
            "hero_power_before_use",
        ),
        (
            "SW_448",
            "EX1_625t",
            "hero_power_transform",
            "BeforePlayCardBonus",
            "hero_power_before_use",
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
    semantic_reason: str,
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
                        "semantic_reason": semantic_reason,
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
