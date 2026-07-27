from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from hsconfig.compile_globalvalues import compile_globalvalues
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
    compiled = compile_globalvalues(
        globalvalues,
        {"global_values_authority_matrix": authority_matrix},
    )
    if compiled["config"] != globalvalues:
        raise AssertionError(
            "baseline-only GlobalValues fixture must compile without changes"
        )

    reports = package / "reports"
    write_json(reports / "globalvalues_baseline.json", globalvalues)
    write_json(reports / "globalvalues_profile.json", compiled["profile"])
    write_json(
        reports / "global_values_authority_matrix.json",
        authority_matrix,
    )
