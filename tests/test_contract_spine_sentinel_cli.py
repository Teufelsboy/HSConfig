from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main


def test_contract_spine_sentinel_cli_returns_clean_json(capsys):
    repo_root = Path(__file__).resolve().parents[1]

    exit_code = main(
        [
            "contract-spine-sentinel",
            "--repo-root",
            str(repo_root),
            "--json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["status"] == "clean"
    assert output["operator_gate_impact"] == "diagnostic_only"
    assert output["apply_blocking"] is False
    assert output["problems"] == []


def test_contract_spine_sentinel_cli_uses_explicit_root_from_foreign_cwd(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    from hsconfig import contract_spine_sentinel as sentinel

    repo_root = Path(__file__).resolve().parents[1]
    foreign_cwd = tmp_path / "foreign"
    foreign_cwd.mkdir()
    installed_module = (
        tmp_path
        / "environment"
        / "Lib"
        / "site-packages"
        / "hsconfig"
        / "contract_spine_sentinel.py"
    )
    monkeypatch.chdir(foreign_cwd)
    monkeypatch.setattr(sentinel, "__file__", str(installed_module))

    exit_code = main(
        [
            "contract-spine-sentinel",
            "--repo-root",
            str(repo_root),
            "--json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["status"] == "clean"
    assert output["problems"] == []


def test_contract_spine_sentinel_cli_rejects_non_repository_root(
    tmp_path: Path,
    capsys,
):
    exit_code = main(
        [
            "contract-spine-sentinel",
            "--repo-root",
            str(tmp_path),
            "--json",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["status"] == "failed"
    assert "must be an HSConfig repository root" in output["errors"][0]


def test_contract_spine_sentinel_cli_can_write_json_report(tmp_path: Path, capsys):
    out = tmp_path / "contract_spine_sentinel.json"

    exit_code = main(["contract-spine-sentinel", "--out", str(out), "--json"])
    output = json.loads(capsys.readouterr().out)
    written = json.loads(out.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert output["written_report"] == str(out)
    assert written["status"] == "clean"
    assert written["operator_gate_impact"] == "diagnostic_only"


def test_contract_spine_sentinel_cli_rejects_runtime_output_path(
    tmp_path: Path, capsys
):
    out = tmp_path / "CustomConfig" / "ShadowPriest" / "Mulligan.json"

    exit_code = main(["contract-spine-sentinel", "--out", str(out), "--json"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["status"] == "failed"
    assert "must not target HearthRanger runtime files" in output["errors"][0]
    assert not out.exists()


def test_contract_spine_sentinel_cli_rejects_non_json_output_path(
    tmp_path: Path, capsys
):
    out = tmp_path / "contract_spine_sentinel.txt"

    exit_code = main(["contract-spine-sentinel", "--out", str(out), "--json"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["status"] == "failed"
    assert "must be a .json diagnostic report path" in output["errors"][0]
    assert not out.exists()


def test_contract_spine_sentinel_cli_returns_failure_for_drift(
    monkeypatch, capsys
):
    from hsconfig.commands import contract_spine_sentinel as command

    def drifted_report(*, repo_root: Path):
        assert repo_root == Path.cwd().resolve(strict=True)
        return {
            "status": "drift_detected",
            "operator_gate_impact": "diagnostic_only",
            "apply_blocking": False,
            "problems": [{"check": "test_drift", "value": ["example"]}],
        }

    monkeypatch.setattr(command, "build_contract_spine_sentinel_report", drifted_report)

    exit_code = main(["contract-spine-sentinel", "--json"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["status"] == "drift_detected"
    assert output["problems"] == [{"check": "test_drift", "value": ["example"]}]
