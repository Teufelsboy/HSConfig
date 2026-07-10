from __future__ import annotations

import json
from pathlib import Path

from hsconfig.acceptance_matrix import build_acceptance_matrix
from hsconfig.cli import main
from hsconfig.io import write_json


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)
BIGSHAMAN_CODE = (
    "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA=="
)


def _prepare_package(tmp_path: Path, deck_name: str, deck_code: str) -> Path:
    out = tmp_path / deck_name
    assert (
        main(
            [
                "prepare",
                "--deck-name",
                deck_name,
                "--deck-code",
                deck_code,
                "--runtime-root",
                str(tmp_path / "runtime"),
                "--out",
                str(out),
                "--json",
            ]
        )
        == 0
    )
    return out


def test_build_acceptance_matrix_summarizes_load_safe_packages(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])

    shadow = _prepare_package(tmp_path, "ShadowPriest", SHADOWPRIEST_CODE)
    shaman = _prepare_package(tmp_path, "BigShaman", BIGSHAMAN_CODE)

    matrix = build_acceptance_matrix([shadow, shaman])

    assert matrix["schema_version"] == 1
    assert matrix["status"] == "passed"
    assert matrix["summary"]["package_count"] == 2
    assert matrix["summary"]["valid_package_count"] == 2
    assert matrix["summary"]["load_safe_apply_count"] == 2
    assert matrix["summary"]["technical_hard_block_count"] == 0
    assert {row["deck_name"] for row in matrix["packages"]} == {
        "ShadowPriest",
        "BigShaman",
    }
    for row in matrix["packages"]:
        assert row["technical_status"] == "VALID_PACKAGE"
        assert row["runtime_apply_mode"] == "load_safe_apply"
        assert row["runtime_apply_allowed"] is True
        assert row["has_globalvalues"] is True
        assert row["has_mulligan"] is True
        assert row["has_presume"] is False
        assert row["has_concede"] is False
        assert row["cardid_file_count"] > 0
        assert isinstance(row["warning_boundaries"], list)


def test_build_acceptance_matrix_reports_missing_operator_summary(tmp_path: Path):
    package = tmp_path / "broken-package"
    package.mkdir()

    matrix = build_acceptance_matrix([package])

    assert matrix["status"] == "failed"
    assert matrix["summary"]["package_count"] == 1
    assert matrix["summary"]["technical_hard_block_count"] == 1
    assert matrix["packages"][0]["inspection_status"] == "missing_operator_summary"
    assert matrix["packages"][0]["technical_status"] == "INVALID_PACKAGE"
    assert matrix["packages"][0]["apply_gate_status"] == "blocked"


def test_build_acceptance_matrix_uses_apply_gate_for_stale_valid_summary(
    tmp_path: Path,
):
    package = tmp_path / "stale-valid-summary"
    reports = package / "reports"
    reports.mkdir(parents=True)
    (reports / "operator_summary.json").write_text(
        json.dumps(
            {
                "deck": {"name": "StaleDeck"},
                "technical_status": "VALID_PACKAGE",
                "semantic_status": "SOURCE_BACKED_STRONG",
                "next_action": "READY_TO_APPLY_OR_HANDOFF",
                "runtime_apply_mode": "load_safe_apply",
                "runtime_apply_allowed": True,
                "config_usefulness": {"status": "guide_aligned"},
                "no_block_failure_mode_summary": {
                    "categories": {"technical_hard_block": []}
                },
            }
        ),
        encoding="utf-8",
    )

    matrix = build_acceptance_matrix([package])
    row = matrix["packages"][0]

    assert matrix["status"] == "failed"
    assert matrix["summary"]["valid_package_count"] == 1
    assert matrix["summary"]["apply_gate_allowed_count"] == 0
    assert matrix["summary"]["technical_hard_block_count"] == 1
    assert row["technical_status"] == "VALID_PACKAGE"
    assert row["apply_gate_status"] == "blocked"
    assert row["apply_gate_allowed"] is False
    assert row["apply_gate_reasons"][0]["reason"] == "missing_custom_config_directory"


def test_build_acceptance_matrix_uses_package_validation_for_missing_baseline(
    tmp_path: Path,
):
    package = tmp_path / "missing-baseline"
    deck_dir = package / "CustomConfig" / "deck"
    reports = package / "reports"
    write_json(
        deck_dir / "GlobalValues.json",
        {"GameCardId": "GlobalValues", "ConfigComment": "new"},
    )
    write_json(
        deck_dir / "Mulligan.json",
        {"GameCardId": "Mulligan", "ConfigComment": "new", "Mulligan": {"values": []}},
    )
    write_json(reports / "input_manifest.json", {"deck_name": "deck"})
    write_json(
        reports / "operator_summary.json",
        {
            "deck": {"name": "MissingBaseline"},
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "runtime_apply_mode": "load_safe_apply",
            "runtime_apply_allowed": True,
            "generated_files": [
                "CustomConfig/deck/GlobalValues.json",
                "CustomConfig/deck/Mulligan.json",
            ],
            "config_usefulness": {"status": "guide_aligned"},
            "no_block_failure_mode_summary": {
                "categories": {"technical_hard_block": []}
            },
        },
    )

    matrix = build_acceptance_matrix([package])
    row = matrix["packages"][0]

    assert matrix["status"] == "failed"
    assert matrix["summary"]["valid_package_count"] == 1
    assert matrix["summary"]["load_safe_apply_count"] == 1
    assert matrix["summary"]["apply_gate_allowed_count"] == 1
    assert matrix["summary"]["validation_pass_count"] == 0
    assert matrix["summary"]["technical_hard_block_count"] == 1
    assert row["apply_gate_allowed"] is True
    assert row["validation_status"] == "failed"
    assert "Missing GlobalValues baseline report" in row["validation_errors"][0]


def test_build_acceptance_matrix_fails_when_operator_runtime_mode_is_blocked(
    tmp_path: Path,
):
    package = _prepare_package(tmp_path, "ShadowPriest", SHADOWPRIEST_CODE)
    operator_path = package / "reports" / "operator_summary.json"
    operator = json.loads(operator_path.read_text(encoding="utf-8"))
    operator["runtime_apply_mode"] = "blocked"
    operator["runtime_apply_allowed"] = False
    write_json(operator_path, operator)

    matrix = build_acceptance_matrix([package])
    row = matrix["packages"][0]

    assert matrix["status"] == "failed"
    assert matrix["summary"]["valid_package_count"] == 1
    assert matrix["summary"]["validation_pass_count"] == 1
    assert matrix["summary"]["apply_gate_allowed_count"] == 1
    assert matrix["summary"]["load_safe_apply_count"] == 0
    assert matrix["summary"]["technical_hard_block_count"] == 0
    assert row["runtime_apply_mode"] == "blocked"
    assert row["validation_status"] == "passed"
    assert row["apply_gate_allowed"] is True


def test_acceptance_matrix_cli_outputs_json_and_optional_file(
    tmp_path: Path, capsys, monkeypatch
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    package = _prepare_package(tmp_path, "ShadowPriest", SHADOWPRIEST_CODE)
    capsys.readouterr()
    out_file = tmp_path / "acceptance_matrix.json"

    code = main(
        [
            "acceptance-matrix",
            "--package",
            str(package),
            "--out",
            str(out_file),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    written = json.loads(out_file.read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "passed"
    assert payload == written
    assert payload["summary"]["package_count"] == 1
    assert payload["packages"][0]["deck_name"] == "ShadowPriest"
