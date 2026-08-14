from __future__ import annotations

from pathlib import Path
from typing import Any

from hsconfig.io import read_json


def read_optional_profile(package: Path) -> dict[str, Any] | None:
    profile_path = package / "reports" / "globalvalues_profile.json"
    if not profile_path.exists():
        return None
    profile = read_json(profile_path)
    if not isinstance(profile, dict):
        raise ValueError(f"GlobalValues profile must be an object: {profile_path}")
    return profile


def read_required_baseline(package: Path) -> dict[str, Any]:
    baseline_path = package / "reports" / "globalvalues_baseline.json"
    if not baseline_path.exists():
        raise ValueError(f"Missing GlobalValues baseline report: {baseline_path}")
    baseline = read_json(baseline_path)
    if not isinstance(baseline, dict):
        raise ValueError(f"GlobalValues baseline must be an object: {baseline_path}")
    return baseline


def read_required_globalvalues_authority_matrix(
    package: Path,
) -> dict[str, Any]:
    matrix_path = package / "reports" / "global_values_authority_matrix.json"
    if not matrix_path.exists():
        raise ValueError(
            f"Missing GlobalValues authority matrix report: {matrix_path}"
        )
    matrix = read_json(matrix_path)
    if not isinstance(matrix, dict):
        raise ValueError(
            f"GlobalValues authority matrix must be an object: {matrix_path}"
        )
    return matrix


def prepare_research_output_dir(out: Path) -> None:
    if not out.exists():
        return
    if not out.is_dir():
        raise ValueError(f"Research output path exists and is not a directory: {out}")
    if list(out.iterdir()):
        raise ValueError(f"Refusing to overwrite non-empty research output directory: {out}")
