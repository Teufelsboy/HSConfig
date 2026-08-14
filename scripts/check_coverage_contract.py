from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys
from typing import Any


GLOBAL_MINIMUM = 90.0
GLOBAL_TARGET = 95.0
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src" / "hsconfig"
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


_SUMMARY_COUNT_FIELDS = (
    "covered_lines",
    "num_statements",
    "missing_lines",
    "excluded_lines",
    "num_branches",
    "num_partial_branches",
    "covered_branches",
    "missing_branches",
)


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


def _is_reparse(metadata: os.stat_result) -> bool:
    return bool(
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _production_module_inventory() -> tuple[str, ...]:
    try:
        root_metadata = SOURCE_ROOT.lstat()
        if (
            SOURCE_ROOT.resolve(strict=True) != SOURCE_ROOT
            or not stat.S_ISDIR(root_metadata.st_mode)
            or stat.S_ISLNK(root_metadata.st_mode)
            or _is_reparse(root_metadata)
        ):
            raise CoverageDataError("production source inventory is unsafe")
        modules: list[str] = []
        for path in sorted(SOURCE_ROOT.rglob("*")):
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode) or _is_reparse(metadata):
                raise CoverageDataError("production source inventory is unsafe")
            if stat.S_ISDIR(metadata.st_mode):
                continue
            relative_source = path.relative_to(SOURCE_ROOT)
            if "resources" in relative_source.parts or path.suffix != ".py":
                continue
            if (
                not stat.S_ISREG(metadata.st_mode)
                or getattr(metadata, "st_nlink", 1) not in {0, 1}
                or SOURCE_ROOT not in path.resolve(strict=True).parents
            ):
                raise CoverageDataError("production source inventory is unsafe")
            modules.append(path.relative_to(REPOSITORY_ROOT).as_posix())
    except CoverageDataError:
        raise
    except OSError as exc:
        raise CoverageDataError("production source inventory is unavailable") from exc
    if not modules or len(modules) != len(set(modules)):
        raise CoverageDataError("production source inventory is invalid")
    return tuple(modules)


def _normalized_coverage_module(path: object) -> str:
    if not isinstance(path, str) or not path:
        raise CoverageDataError("production module inventory differs")
    candidate = Path(path)
    if not candidate.is_absolute():
        return path.replace("\\", "/")
    if os.name != "nt" or any(
        segment in {".", ".."} for segment in path.replace("/", "\\").split("\\")
    ):
        raise CoverageDataError("production module inventory differs")
    try:
        relative = candidate.relative_to(SOURCE_ROOT)
    except ValueError as exc:
        raise CoverageDataError("production module inventory differs") from exc
    if not relative.parts or any(part in {".", ".."} for part in relative.parts):
        raise CoverageDataError("production module inventory differs")
    return (Path("src") / "hsconfig" / relative).as_posix()


def _summary_counts(module: str, data: dict[str, Any]) -> dict[str, int]:
    summary = _mapping(data.get("summary"), f"files[{module}].summary")
    counts = {
        field: _count(summary, field, f"files[{module}].summary")
        for field in _SUMMARY_COUNT_FIELDS
    }
    if counts["covered_lines"] > counts["num_statements"]:
        raise CoverageDataError(
            f"files[{module}].summary.covered_lines exceeds num_statements"
        )
    if counts["covered_branches"] > counts["num_branches"]:
        raise CoverageDataError(
            f"files[{module}].summary.covered_branches exceeds num_branches"
        )
    if counts["missing_lines"] != counts["num_statements"] - counts["covered_lines"]:
        raise CoverageDataError(
            f"files[{module}].summary.missing_lines is inconsistent with statement counts"
        )
    if (
        counts["missing_branches"]
        != counts["num_branches"] - counts["covered_branches"]
    ):
        raise CoverageDataError(
            f"files[{module}].summary.missing_branches is inconsistent with branch counts"
        )
    if counts["num_partial_branches"] > counts["missing_branches"]:
        raise CoverageDataError(
            f"files[{module}].summary.num_partial_branches exceeds missing_branches"
        )
    return counts


def _module_row(
    module: str,
    data: dict[str, Any],
) -> tuple[dict[str, Any], bool, bool]:
    counts = _summary_counts(module, data)
    covered_lines = counts["covered_lines"]
    num_statements = counts["num_statements"]
    covered_branches = counts["covered_branches"]
    num_branches = counts["num_branches"]
    summary_missing_lines = counts["missing_lines"]
    summary_missing_branches = counts["missing_branches"]
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

    expected_modules = _production_module_inventory()
    normalized_files: dict[str, object] = {}
    for path, value in files.items():
        normalized = _normalized_coverage_module(path)
        if normalized in normalized_files:
            raise CoverageDataError("production module inventory differs")
        normalized_files[normalized] = value
    if tuple(sorted(normalized_files)) != expected_modules:
        raise CoverageDataError("production module inventory differs")

    file_totals = {field: 0 for field in _SUMMARY_COUNT_FIELDS}
    for module in expected_modules:
        counts = _summary_counts(
            module,
            _mapping(normalized_files[module], f"files[{module}]"),
        )
        for field, count in counts.items():
            file_totals[field] += count
    reported_totals = {
        field: _count(totals, field, "totals") for field in _SUMMARY_COUNT_FIELDS
    }
    covered_branches = reported_totals["covered_branches"]
    num_branches = reported_totals["num_branches"]
    if covered_branches > num_branches:
        raise CoverageDataError("totals.covered_branches exceeds num_branches")
    missing_branches = reported_totals["missing_branches"]
    if missing_branches != num_branches - covered_branches:
        raise CoverageDataError(
            "totals.missing_branches is inconsistent with branch counts"
        )
    global_branch_percent = _percent(covered_branches, num_branches)

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

    if reported_totals != file_totals:
        raise CoverageDataError("totals do not match production file summaries")

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
