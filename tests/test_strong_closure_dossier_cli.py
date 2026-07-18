from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main
from hsconfig.io import write_json


def _package(tmp_path: Path) -> Path:
    package_dir = tmp_path / "04_package"
    write_json(
        package_dir / "reports" / "operator_summary.json",
        {
            "deck": {"name": "ShadowPriest"},
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "source_strong_ready": True,
            "first_missing_source_action": "none",
            "source_status_apply_blocking": False,
            "source_status_diagnostic_only": True,
            "default_only_runtime_surfaces": [],
            "no_default_only_runtime_status": "clean",
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
        },
    )
    write_json(
        package_dir / "reports" / "source_claim_gap_report.json",
        {"summary": {"blocked_cards": 0}, "cards": {}},
    )
    return package_dir


def test_strong_closure_dossier_cli_writes_diagnostic_report(
    tmp_path: Path,
    capsys,
) -> None:
    package_dir = _package(tmp_path)
    research_dir = tmp_path / "research"
    write_json(
        research_dir / "shadowpriest.json",
        {
            "deck_name": "ShadowPriest",
            "deck_code": "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
            "source_strength": "exact_full_text_guide",
            "source_visibility": "full_text",
            "freshness_status": "current",
            "lowerable_claim_kinds": ["mulligan_keep"],
            "first_missing_source_action": "none",
        },
    )
    out = tmp_path / "strong_closure_dossier.json"

    exit_code = main(
        [
            "strong-closure-dossier",
            "--package",
            str(package_dir),
            "--research-results-dir",
            str(research_dir),
            "--out",
            str(out),
            "--json",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    written = json.loads(out.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert output == written
    assert output["authority"] == "diagnostic_only"
    assert output["operator_gate_impact"] == "diagnostic_only"
    assert output["normal_apply_authority"] == "reports/operator_summary.json"
    assert output["deck_name"] == "ShadowPriest"
    assert output["strong_contract_closed"] is True
    assert output["source_status_apply_blocking"] is False
    assert "written_report" not in output
    assert output["research_snapshot_rows"][0]["canonical_promotion_allowed"] is True


def test_strong_closure_dossier_cli_allows_missing_research_dir(
    tmp_path: Path,
    capsys,
) -> None:
    package_dir = _package(tmp_path)

    exit_code = main(
        [
            "strong-closure-dossier",
            "--package",
            str(package_dir),
            "--research-results-dir",
            str(tmp_path / "missing-research"),
            "--json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["research_snapshot_rows"] == []
    assert output["summary"]["research_snapshot_count"] == 0
    assert output["source_status_apply_blocking"] is False


def test_strong_closure_dossier_cli_rejects_runtime_output_path(
    tmp_path: Path,
    capsys,
) -> None:
    package_dir = _package(tmp_path)
    runtime_out = tmp_path / "CustomConfig" / "ShadowPriest" / "Mulligan.json"

    exit_code = main(
        [
            "strong-closure-dossier",
            "--package",
            str(package_dir),
            "--research-results-dir",
            str(tmp_path / "research"),
            "--out",
            str(runtime_out),
            "--json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["status"] == "failed"
    assert "must not target HearthRanger runtime files" in output["errors"][0]
    assert not runtime_out.exists()


def test_strong_closure_dossier_cli_rejects_package_operator_summary_output_path(
    tmp_path: Path,
    capsys,
) -> None:
    package_dir = _package(tmp_path)
    out = package_dir / "reports" / "operator_summary.json"
    original_operator_summary = out.read_text(encoding="utf-8")

    exit_code = main(
        [
            "strong-closure-dossier",
            "--package",
            str(package_dir),
            "--research-results-dir",
            str(tmp_path / "research"),
            "--out",
            str(out),
            "--json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["status"] == "failed"
    assert "must not target package operator_summary.json" in output["errors"][0]
    assert out.read_text(encoding="utf-8") == original_operator_summary


def test_strong_closure_dossier_cli_rejects_non_json_output_path(
    tmp_path: Path,
    capsys,
) -> None:
    package_dir = _package(tmp_path)
    out = tmp_path / "strong_closure_dossier.txt"

    exit_code = main(
        [
            "strong-closure-dossier",
            "--package",
            str(package_dir),
            "--research-results-dir",
            str(tmp_path / "research"),
            "--out",
            str(out),
            "--json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["status"] == "failed"
    assert "must be a .json diagnostic report path" in output["errors"][0]
    assert not out.exists()
