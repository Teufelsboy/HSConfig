from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any


GLOBAL_MINIMUM = 90.0
GLOBAL_TARGET = 95.0
CRITICAL_MODULES = (
    "src/hsconfig/atomic_io.py",
    "src/hsconfig/output_publisher.py",
    "src/hsconfig/current_output.py",
    "src/hsconfig/runtime_installer.py",
    "src/hsconfig/runtime_state.py",
    "src/hsconfig/deck_config_ini.py",
    "src/hsconfig/apply_gate.py",
    "src/hsconfig/apply_decision.py",
    "src/hsconfig/operator_status.py",
)


class CoverageDataError(ValueError):
    pass


def _empty_report(error: str) -> dict[str, Any]:
    return {
        "passed": False,
        "global_branch_percent": None,
        "global_minimum": GLOBAL_MINIMUM,
        "target_met": False,
        "critical_modules": [],
        "errors": [error],
    }


def _mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CoverageDataError(f"{name} must be an object")
    return value


def _count(mapping: dict[str, Any], field: str, name: str) -> int:
    value = mapping.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CoverageDataError(f"{name}.{field} must be a non-negative integer")
    return value


def _percent(covered: int, total: int) -> float:
    if total == 0:
        return 100.0
    return round(covered * 100.0 / total, 2)


def _meets_percent(covered: int, total: int, threshold: float) -> bool:
    if total == 0:
        return True
    return covered * 100 >= threshold * total


def _line_list(value: object, name: str) -> list[int]:
    if not isinstance(value, list) or any(
        isinstance(item, bool) or not isinstance(item, int) or item < 1
        for item in value
    ):
        raise CoverageDataError(f"{name} must be a list of positive integers")
    if len(value) != len(set(value)):
        raise CoverageDataError(f"{name} must not contain duplicates")
    return sorted(value)


def _branch_list(value: object, name: str) -> list[list[int]]:
    if not isinstance(value, list):
        raise CoverageDataError(f"{name} must be a list of line-number pairs")
    branches: list[list[int]] = []
    for branch in value:
        if (
            not isinstance(branch, list)
            or len(branch) != 2
            or any(isinstance(item, bool) or not isinstance(item, int) for item in branch)
        ):
            raise CoverageDataError(f"{name} must be a list of line-number pairs")
        branches.append(branch)
    if len(branches) != len({tuple(branch) for branch in branches}):
        raise CoverageDataError(f"{name} must not contain duplicate pairs")
    return sorted(branches)


def _module_row(
    module: str,
    data: dict[str, Any],
) -> tuple[dict[str, Any], bool, bool]:
    summary = _mapping(data.get("summary"), f"files[{module}].summary")
    covered_lines = _count(summary, "covered_lines", f"files[{module}].summary")
    num_statements = _count(summary, "num_statements", f"files[{module}].summary")
    covered_branches = _count(
        summary,
        "covered_branches",
        f"files[{module}].summary",
    )
    num_branches = _count(summary, "num_branches", f"files[{module}].summary")
    if covered_lines > num_statements:
        raise CoverageDataError(
            f"files[{module}].summary.covered_lines exceeds num_statements"
        )
    if covered_branches > num_branches:
        raise CoverageDataError(
            f"files[{module}].summary.covered_branches exceeds num_branches"
        )
    summary_missing_lines = _count(
        summary,
        "missing_lines",
        f"files[{module}].summary",
    )
    summary_missing_branches = _count(
        summary,
        "missing_branches",
        f"files[{module}].summary",
    )
    if summary_missing_lines != num_statements - covered_lines:
        raise CoverageDataError(
            f"files[{module}].summary.missing_lines is inconsistent with statement counts"
        )
    if summary_missing_branches != num_branches - covered_branches:
        raise CoverageDataError(
            f"files[{module}].summary.missing_branches is inconsistent with branch counts"
        )
    missing_lines = _line_list(
        data.get("missing_lines"),
        f"files[{module}].missing_lines",
    )
    missing_branches = _branch_list(
        data.get("missing_branches"),
        f"files[{module}].missing_branches",
    )
    if len(missing_lines) != summary_missing_lines:
        raise CoverageDataError(
            f"files[{module}].missing_lines count does not match summary.missing_lines"
        )
    if len(missing_branches) != summary_missing_branches:
        raise CoverageDataError(
            f"files[{module}].missing_branches count does not match summary.missing_branches"
        )
    row = {
        "module": module,
        "statement_percent": _percent(covered_lines, num_statements),
        "branch_percent": _percent(covered_branches, num_branches),
        "missing_lines": missing_lines,
        "missing_branches": missing_branches,
    }
    return row, covered_lines == num_statements, covered_branches == num_branches


def check_coverage(payload: object) -> dict[str, Any]:
    root = _mapping(payload, "root")
    meta = _mapping(root.get("meta"), "meta")
    if meta.get("branch_coverage") is not True:
        raise CoverageDataError("meta.branch_coverage must be true")
    files = _mapping(root.get("files"), "files")
    totals = _mapping(root.get("totals"), "totals")

    covered_branches = _count(totals, "covered_branches", "totals")
    num_branches = _count(totals, "num_branches", "totals")
    if covered_branches > num_branches:
        raise CoverageDataError("totals.covered_branches exceeds num_branches")
    missing_branches = _count(totals, "missing_branches", "totals")
    if missing_branches != num_branches - covered_branches:
        raise CoverageDataError(
            "totals.missing_branches is inconsistent with branch counts"
        )
    global_branch_percent = _percent(covered_branches, num_branches)

    normalized_files = {str(path).replace("\\", "/"): value for path, value in files.items()}
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for module in CRITICAL_MODULES:
        module_data = normalized_files.get(module)
        if module_data is None:
            rows.append(
                {
                    "module": module,
                    "statement_percent": None,
                    "branch_percent": None,
                    "missing_lines": [],
                    "missing_branches": [],
                }
            )
            errors.append(f"critical module missing from coverage data: {module}")
            continue
        row, statements_complete, branches_complete = _module_row(
            module,
            _mapping(module_data, f"files[{module}]"),
        )
        rows.append(row)
        if not statements_complete:
            errors.append(
                f"critical module {module} statement coverage "
                f"{row['statement_percent']:.2f}%; missing lines: {row['missing_lines']}"
            )
        if not branches_complete:
            errors.append(
                f"critical module {module} branch coverage "
                f"{row['branch_percent']:.2f}%; missing branches: "
                f"{row['missing_branches']}"
            )

    if not _meets_percent(covered_branches, num_branches, GLOBAL_MINIMUM):
        errors.insert(
            0,
            f"global branch coverage {global_branch_percent:.2f}% is below required "
            f"{GLOBAL_MINIMUM:.2f}%",
        )

    return {
        "passed": not errors,
        "global_branch_percent": global_branch_percent,
        "global_minimum": GLOBAL_MINIMUM,
        "target_met": _meets_percent(covered_branches, num_branches, GLOBAL_TARGET),
        "critical_modules": rows,
        "errors": errors,
    }


def _emit(report: dict[str, Any]) -> None:
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        _emit(_empty_report("usage: check_coverage_contract.py COVERAGE_JSON"))
        return 2
    coverage_path = Path(args[0])
    if not coverage_path.is_file():
        _emit(_empty_report(f"coverage file does not exist: {coverage_path}"))
        return 2
    try:
        payload = json.loads(coverage_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        _emit(_empty_report(f"malformed coverage JSON: {exc}"))
        return 2
    try:
        report = check_coverage(payload)
    except CoverageDataError as exc:
        _emit(_empty_report(f"malformed coverage data: {exc}"))
        return 2
    _emit(report)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
