from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main
from hsconfig.io import write_json


def _package(tmp_path: Path, deck_name: str = "ShadowPriest") -> Path:
    package_dir = tmp_path / "04_package"
    write_json(
        package_dir / "reports" / "operator_summary.json",
        {
            "deck": {"name": deck_name},
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "source_strong_ready": True,
            "first_missing_source_action": "none",
            "source_status_apply_blocking": False,
            "source_status_diagnostic_only": True,
            "default_only_runtime_surfaces": [],
            "no_default_only_runtime_status": "clean",
        },
    )
    return package_dir


def test_research_status_sync_cli_writes_diagnostic_report(
    tmp_path: Path,
    capsys,
) -> None:
    package_dir = _package(tmp_path)
    research_dir = tmp_path / "research"
    write_json(
        research_dir / "shadowpriest.json",
        {
            "deck_name": "ShadowPriest",
            "source_strength": "unfetched_acquisition_seed",
            "first_missing_source_action": "fetch_and_normalize_candidate_full_text_claims",
        },
    )
    out = tmp_path / "research_status_sync.json"

    exit_code = main(
        [
            "research-status-sync",
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
    assert "written_report" not in output
    assert output["summary"]["canonical_source_backed_status"] == "SOURCE_BACKED_STRONG"
    assert output["summary"]["stale_or_seed_snapshot_count"] == 1
    assert output["summary"]["source_status_apply_blocking"] is False
    row = output["research_snapshot_rows"][0]
    assert row["snapshot_relation"] == "stale_or_seed_only"
    assert row["research_snapshot_kind"] == "seed_only"
    assert row["canonical_downgrade_allowed"] is False
    assert row["canonical_promotion_allowed"] is False


def test_research_status_sync_cli_reports_missing_snapshot_without_blocking(
    tmp_path: Path,
    capsys,
) -> None:
    package_dir = _package(tmp_path)

    exit_code = main(
        [
            "research-status-sync",
            "--package",
            str(package_dir),
            "--research-results-dir",
            str(tmp_path / "missing-research"),
            "--json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert "written_report" not in output
    assert output["research_snapshot_rows"] == []
    assert output["summary"]["missing_research_snapshot"] is True
    assert output["summary"]["source_status_apply_blocking"] is False


def test_research_status_sync_cli_rejects_runtime_output_path(
    tmp_path: Path,
    capsys,
) -> None:
    package_dir = _package(tmp_path)
    runtime_out = tmp_path / "CustomConfig" / "ShadowPriest" / "Mulligan.json"

    exit_code = main(
        [
            "research-status-sync",
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


def test_research_status_sync_cli_rejects_package_operator_summary_output_path(
    tmp_path: Path,
    capsys,
) -> None:
    package_dir = _package(tmp_path)
    out = package_dir / "reports" / "operator_summary.json"
    original_operator_summary = out.read_text(encoding="utf-8")

    exit_code = main(
        [
            "research-status-sync",
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


def test_research_status_sync_cli_rejects_non_json_output_path(
    tmp_path: Path,
    capsys,
) -> None:
    package_dir = _package(tmp_path)
    out = tmp_path / "research_status_sync.txt"

    exit_code = main(
        [
            "research-status-sync",
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
