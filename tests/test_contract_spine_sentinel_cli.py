from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main


def test_contract_spine_sentinel_cli_returns_clean_json(capsys):
    exit_code = main(["contract-spine-sentinel", "--json"])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["status"] == "clean"
    assert output["operator_gate_impact"] == "diagnostic_only"
    assert output["apply_blocking"] is False
    assert output["problems"] == []


def test_contract_spine_sentinel_cli_can_write_json_report(tmp_path: Path, capsys):
    out = tmp_path / "contract_spine_sentinel.json"

    exit_code = main(["contract-spine-sentinel", "--out", str(out), "--json"])
    output = json.loads(capsys.readouterr().out)
    written = json.loads(out.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert output["written_report"] == str(out)
    assert written["status"] == "clean"
    assert written["operator_gate_impact"] == "diagnostic_only"
