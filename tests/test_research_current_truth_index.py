from __future__ import annotations

import json
import re
from pathlib import Path

CURRENT_TRUTH = Path("docs/research/current-truth.md")
CURRENT_TRUTH_INDEX = Path("docs/research/current-truth-index.json")


def _current_active_evidence_package_paths() -> set[str]:
    raw = CURRENT_TRUTH.read_text(encoding="utf-8")
    match = re.search(
        r"(?ms)^## Current Active Evidence\s*$\n(?P<body>.*?)(?=^## |\Z)",
        raw,
    )
    assert match is not None

    paths: set[str] = set()
    for token in re.findall(
        r"`(?P<path>(?:docs/research/)?20\d{2}-\d{2}-\d{2}-[A-Za-z0-9_-]+/?)`",
        match.group("body"),
    ):
        if token.startswith("docs/research/"):
            paths.add(token if token.endswith("/") else f"{token}/")
        else:
            paths.add(f"docs/research/{token}/")
    return paths


def test_current_truth_index_is_machine_readable_and_diagnostic_only():
    data = json.loads(CURRENT_TRUTH_INDEX.read_text(encoding="utf-8"))

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


def test_current_truth_index_includes_every_current_active_evidence_package():
    data = json.loads(CURRENT_TRUTH_INDEX.read_text(encoding="utf-8"))

    markdown_paths = _current_active_evidence_package_paths()
    packages = data["active_research_packages"]
    index_paths = [item["path"] for item in packages]

    assert markdown_paths
    assert len(index_paths) == len(set(index_paths))
    assert markdown_paths == set(index_paths)
    assert all(
        set(item) == {"path", "role", "current_implication"} for item in packages
    )


def test_current_truth_index_does_not_claim_apply_authority():
    raw = CURRENT_TRUTH_INDEX.read_text(encoding="utf-8")
    forbidden = {
        "runtime_apply_authorized",
        "apply_gate_authority",
        "operator_summary_replacement",
    }

    assert not any(token in raw for token in forbidden)
