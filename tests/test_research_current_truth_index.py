from __future__ import annotations

import json
from pathlib import Path


def test_current_truth_index_is_machine_readable_and_diagnostic_only():
    data = json.loads(Path("docs/research/current-truth-index.json").read_text(encoding="utf-8"))

    assert data["schema_version"] == 1
    assert data["authority"] == "evidence_index_only"
    assert data["operator_gate_impact"] == "diagnostic_only"
    assert data["normal_operator_path"] == "docs/operator/README.md"
    assert data["normal_apply_authority"] == "reports/operator_summary.json"
    assert data["active_runtime_surfaces"] == [
        "Mulligan.json",
        "GlobalValues.json",
        "Combo.json",
        "CARDID.json",
    ]
    assert data["excluded_normal_surfaces"] == ["Concede.json", "Presume.json"]
    assert data["warning_only_runtime_policy"] == (
        "report_visible_no_runtime_rows_without_documented_surface"
    )
    assert (
        "docs/research/2026-07-14-hsconfig-source-contract-logic-guardrail-audit/"
        in {item["path"] for item in data["active_research_packages"]}
    )


def test_current_truth_index_does_not_claim_apply_authority():
    raw = Path("docs/research/current-truth-index.json").read_text(encoding="utf-8")
    forbidden = {
        "runtime_apply_authorized",
        "apply_gate_authority",
        "operator_summary_replacement",
    }

    assert not any(token in raw for token in forbidden)
