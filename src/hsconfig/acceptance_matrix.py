from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.io import read_json
from hsconfig.package_io import read_optional_profile, read_required_baseline
from hsconfig.validate_package import validate_config_package


SPECIAL_RUNTIME_FILES = {
    "Combo.json",
    "GlobalValues.json",
    "Mulligan.json",
    "Presume.json",
    "Concede.json",
}


def build_acceptance_matrix(package_paths: Sequence[str | Path]) -> dict[str, Any]:
    rows = [_inspect_package(Path(package_path)) for package_path in package_paths]
    hard_block_count = sum(
        int(row.get("technical_hard_block_count", 0)) for row in rows
    )
    valid_count = sum(
        1 for row in rows if row.get("technical_status") == "VALID_PACKAGE"
    )
    load_safe_count = sum(
        1 for row in rows if row.get("runtime_apply_mode") == "load_safe_apply"
    )
    validation_pass_count = sum(
        1 for row in rows if row.get("validation_status") == "passed"
    )
    warning_count = sum(
        1 for row in rows if int(row.get("warning_boundary_count", 0)) > 0
    )
    apply_allowed_count = sum(1 for row in rows if row.get("apply_gate_allowed") is True)
    status = (
        "passed"
        if hard_block_count == 0
        and len(rows) == valid_count
        and len(rows) == load_safe_count
        and len(rows) == validation_pass_count
        and len(rows) == apply_allowed_count
        else "failed"
    )

    return {
        "schema_version": 1,
        "status": status,
        "summary": {
            "package_count": len(rows),
            "valid_package_count": valid_count,
            "load_safe_apply_count": load_safe_count,
            "validation_pass_count": validation_pass_count,
            "apply_gate_allowed_count": apply_allowed_count,
            "technical_hard_block_count": hard_block_count,
            "warning_package_count": warning_count,
        },
        "packages": rows,
    }


def _inspect_package(package: Path) -> dict[str, Any]:
    operator_path = package / "reports" / "operator_summary.json"
    if not operator_path.is_file():
        return _missing_operator_summary_row(package, operator_path)

    operator = _read_json(operator_path)
    apply_gate = evaluate_apply_gate(package)
    validation_report = _validation_report(package)
    deck_dir = _single_deck_dir(package / "CustomConfig")
    runtime_files = _runtime_files(deck_dir)
    warning_boundaries = _warning_boundaries(operator)
    technical_status = str(operator.get("technical_status", ""))
    technical_hard_blocks = _technical_hard_blocks(operator)
    hard_block_count = len(technical_hard_blocks)
    if apply_gate.get("status") != "allowed" and hard_block_count == 0:
        hard_block_count = 1
    if validation_report.get("status") != "passed" and hard_block_count == 0:
        hard_block_count = 1
    if technical_status != "VALID_PACKAGE" and hard_block_count == 0:
        hard_block_count = 1

    return {
        "package": str(package),
        "inspection_status": "inspected",
        "deck_name": str(_deck_name(operator)),
        "technical_status": technical_status,
        "semantic_status": str(operator.get("semantic_status", "")),
        "next_action": str(operator.get("next_action", "")),
        "runtime_apply_mode": str(operator.get("runtime_apply_mode", "")),
        "runtime_apply_allowed": bool(operator.get("runtime_apply_allowed", False)),
        "validation_status": str(validation_report.get("status", "")),
        "validation_error_count": len(_list(validation_report.get("errors"))),
        "validation_errors": _list(validation_report.get("errors")),
        "apply_gate_status": str(apply_gate.get("status", "")),
        "apply_gate_allowed": bool(apply_gate.get("allowed", False)),
        "apply_gate_mode": str(apply_gate.get("mode", "")),
        "apply_gate_reasons": _list(apply_gate.get("reasons")),
        "technical_hard_block_count": hard_block_count,
        "config_usefulness_status": str(
            _dict(operator.get("config_usefulness")).get("status", "")
        ),
        "first_warning_boundary": _dict(
            operator.get("mechanic_visibility_summary")
        ).get("first_warning_boundary"),
        "warning_boundaries": warning_boundaries,
        "warning_boundary_count": len(warning_boundaries),
        "runtime_file_count": len(runtime_files),
        "cardid_file_count": _cardid_file_count(runtime_files),
        "has_globalvalues": "GlobalValues.json" in runtime_files,
        "has_mulligan": "Mulligan.json" in runtime_files,
        "has_combo": "Combo.json" in runtime_files,
        "has_presume": "Presume.json" in runtime_files,
        "has_concede": "Concede.json" in runtime_files,
    }


def _missing_operator_summary_row(package: Path, operator_path: Path) -> dict[str, Any]:
    apply_gate = evaluate_apply_gate(package)
    return {
        "package": str(package),
        "inspection_status": "missing_operator_summary",
        "missing_path": str(operator_path),
        "deck_name": "",
        "technical_status": "INVALID_PACKAGE",
        "semantic_status": "INVALID_PACKAGE",
        "next_action": "FIX_PACKAGE_BEFORE_APPLY",
        "runtime_apply_mode": "blocked",
        "runtime_apply_allowed": False,
        "validation_status": "failed",
        "validation_error_count": 1,
        "validation_errors": [f"Missing operator summary: {operator_path}"],
        "apply_gate_status": str(apply_gate.get("status", "blocked")),
        "apply_gate_allowed": bool(apply_gate.get("allowed", False)),
        "apply_gate_mode": str(apply_gate.get("mode", "blocked")),
        "apply_gate_reasons": _list(apply_gate.get("reasons")),
        "technical_hard_block_count": 1,
        "config_usefulness_status": "",
        "first_warning_boundary": None,
        "warning_boundaries": [],
        "warning_boundary_count": 0,
        "runtime_file_count": 0,
        "cardid_file_count": 0,
        "has_globalvalues": False,
        "has_mulligan": False,
        "has_combo": False,
        "has_presume": False,
        "has_concede": False,
    }


def _read_json(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    return payload if isinstance(payload, dict) else {}


def _validation_report(package: Path) -> dict[str, Any]:
    try:
        baseline = read_required_baseline(package)
        profile = read_optional_profile(package)
        return validate_config_package(
            package,
            globalvalues_baseline=baseline,
            globalvalues_profile=profile,
            require_complete_package=True,
            require_globalvalues_profile=True,
        )
    except Exception as exc:
        return {"status": "failed", "errors": [str(exc)], "checked_files": 0}


def _single_deck_dir(custom_config_root: Path) -> Path | None:
    if not custom_config_root.is_dir():
        return None
    deck_dirs = [path for path in custom_config_root.iterdir() if path.is_dir()]
    return deck_dirs[0] if len(deck_dirs) == 1 else None


def _runtime_files(deck_dir: Path | None) -> set[str]:
    if deck_dir is None:
        return set()
    return {path.name for path in deck_dir.glob("*.json")}


def _cardid_file_count(runtime_files: set[str]) -> int:
    return sum(1 for filename in runtime_files if filename not in SPECIAL_RUNTIME_FILES)


def _warning_boundaries(operator: dict[str, Any]) -> list[dict[str, str]]:
    visibility = _dict(operator.get("mechanic_visibility_summary"))
    boundaries = visibility.get("warning_boundaries", [])
    if not isinstance(boundaries, list):
        return []

    normalized = []
    for boundary in boundaries:
        if isinstance(boundary, dict):
            normalized.append(
                {
                    "mechanic": str(boundary.get("mechanic", "")),
                    "warning_boundary": str(boundary.get("warning_boundary", "")),
                }
            )
        else:
            normalized.append({"mechanic": "", "warning_boundary": str(boundary)})
    return normalized


def _technical_hard_blocks(operator: dict[str, Any]) -> list[dict[str, Any]]:
    no_block = _dict(operator.get("no_block_failure_mode_summary"))
    categories = _dict(no_block.get("categories"))
    rows = categories.get("technical_hard_block", [])
    return rows if isinstance(rows, list) else []


def _deck_name(operator: dict[str, Any]) -> str:
    deck = _dict(operator.get("deck"))
    return str(deck.get("name", ""))


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
