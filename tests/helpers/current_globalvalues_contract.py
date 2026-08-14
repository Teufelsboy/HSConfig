from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from hsconfig.compile_globalvalues import compile_globalvalues
from hsconfig.globalvalues_decisions import (
    build_globalvalues_decision_ledger,
    canonical_globalvalues_baseline_sha256,
    normalize_globalvalues_decision_baseline,
)
from hsconfig.io import write_json


GLOBALVALUES_AUTHORITY_MATRIX_PATH = (
    "reports/global_values_authority_matrix.json"
)

_BASELINE_AUTHORITY_MATRIX = {
    "allowed_step1_overlays": [
        {
            "key": "baseline",
            "overlay": "none",
            "operation": "none",
            "value": None,
            "reason": "test fixture preserves the complete baseline",
        }
    ]
}


def write_current_globalvalues_contract(
    package: Path,
    globalvalues: dict[str, Any],
) -> None:
    """Install the current schema-2 baseline-only contract in a test package."""
    authority_matrix = deepcopy(_BASELINE_AUTHORITY_MATRIX)
    baseline = normalize_globalvalues_decision_baseline(globalvalues)
    decision_ledger = build_globalvalues_decision_ledger(
        deck_fingerprint="0" * 64,
        baseline=baseline,
        baseline_sha256=canonical_globalvalues_baseline_sha256(baseline),
        authority_matrix=authority_matrix,
    )
    compiled = compile_globalvalues(
        baseline,
        {"global_values_authority_matrix": authority_matrix},
        decision_ledger=decision_ledger,
    )

    globalvalues_paths = sorted(
        (package / "CustomConfig").glob("*/GlobalValues.json")
    )
    if len(globalvalues_paths) != 1:
        raise AssertionError(
            "current GlobalValues fixture requires exactly one runtime file"
        )
    write_json(globalvalues_paths[0], compiled["config"])

    reports = package / "reports"
    write_json(reports / "globalvalues_baseline.json", baseline)
    write_json(reports / "globalvalues_profile.json", compiled["profile"])
    write_json(
        reports / "global_values_authority_matrix.json",
        authority_matrix,
    )
