from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hsconfig.io import read_json


@dataclass(frozen=True)
class _JsonComparison:
    missing_keys_in_runtime: list[str]
    extra_keys_in_runtime: list[str]
    changed_common_keys: list[str]


class RuntimePackageMismatchError(RuntimeError):
    def __init__(self, report: dict[str, Any]) -> None:
        self.report = report
        super().__init__(_format_mismatch_message(report))


def _format_mismatch_message(report: dict[str, Any]) -> str:
    return (
        "Runtime config does not match package: "
        f"{report['semantic_mismatch_count']} semantic mismatches, "
        f"{len(report['missing_in_runtime'])} missing files, "
        f"{len(report['extra_in_runtime'])} extra files."
    )


def _resolve_config_dir(package_root: Path, config_dir: str | None) -> str:
    if config_dir is not None:
        _validate_config_dir(config_dir)
        return config_dir

    custom_config = package_root / "CustomConfig"
    candidates = sorted(
        path.name for path in custom_config.iterdir() if path.is_dir()
    ) if custom_config.is_dir() else []
    if len(candidates) != 1:
        raise ValueError(
            "Expected exactly one package config directory under "
            f"{custom_config}, found {len(candidates)}."
        )
    return candidates[0]


def _validate_config_dir(config_dir: str) -> None:
    path = Path(config_dir)
    if (
        not isinstance(config_dir, str)
        or not config_dir.strip()
        or config_dir != config_dir.strip()
        or path.is_absolute()
        or path.name != config_dir
        or any(part in {"", ".", ".."} for part in path.parts)
        or any(separator in config_dir for separator in ("/", "\\"))
    ):
        raise ValueError(f"Invalid config directory name: {config_dir!r}")


def _json_files(path: Path) -> dict[str, Any]:
    if not path.is_dir():
        return {}
    return {
        file.name: read_json(file)
        for file in sorted(path.glob("*.json"))
        if file.is_file()
    }


def _matching_mapping_lines(path: Path, config_dir: str) -> list[str]:
    if not path.is_file():
        return []
    matched_lines = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", ";")) or "=" not in stripped:
            continue
        _, value = stripped.split("=", 1)
        if value.strip() == config_dir:
            matched_lines.append(line)
    return matched_lines


def _compare_json(package_value: Any, runtime_value: Any) -> _JsonComparison:
    if isinstance(package_value, dict) and isinstance(runtime_value, dict):
        package_keys = set(package_value)
        runtime_keys = set(runtime_value)
        return _JsonComparison(
            missing_keys_in_runtime=sorted(package_keys - runtime_keys),
            extra_keys_in_runtime=sorted(runtime_keys - package_keys),
            changed_common_keys=sorted(
                key
                for key in package_keys & runtime_keys
                if not _json_semantically_equal(
                    package_value[key], runtime_value[key]
                )
            ),
        )
    return _JsonComparison(
        missing_keys_in_runtime=[],
        extra_keys_in_runtime=[],
        changed_common_keys=(
            ["__root__"]
            if not _json_semantically_equal(package_value, runtime_value)
            else []
        ),
    )


def _json_semantically_equal(package_value: Any, runtime_value: Any) -> bool:
    if isinstance(package_value, bool) or isinstance(runtime_value, bool):
        return type(package_value) is type(runtime_value) and package_value == runtime_value
    if isinstance(package_value, dict) and isinstance(runtime_value, dict):
        return (
            set(package_value) == set(runtime_value)
            and all(
                _json_semantically_equal(package_value[key], runtime_value[key])
                for key in package_value
            )
        )
    if isinstance(package_value, list) and isinstance(runtime_value, list):
        return len(package_value) == len(runtime_value) and all(
            _json_semantically_equal(package_item, runtime_item)
            for package_item, runtime_item in zip(package_value, runtime_value)
        )
    return package_value == runtime_value


def build_runtime_package_match_report(
    *,
    package_root: str | Path,
    runtime_root: str | Path,
    config_dir: str | None = None,
) -> dict[str, Any]:
    package = Path(package_root)
    runtime = Path(runtime_root)
    resolved_config_dir = _resolve_config_dir(package, config_dir)
    package_dir = package / "CustomConfig" / resolved_config_dir
    runtime_dir = runtime / "CustomConfig" / resolved_config_dir
    deck_config_ini = runtime / "CustomConfig" / "deck_config.ini"

    package_files = _json_files(package_dir)
    runtime_files = _json_files(runtime_dir)
    package_names = set(package_files)
    runtime_names = set(runtime_files)
    missing_in_runtime = sorted(package_names - runtime_names)
    extra_in_runtime = sorted(runtime_names - package_names)

    semantic_mismatches: list[dict[str, Any]] = []
    for name in sorted(package_names & runtime_names):
        comparison = _compare_json(package_files[name], runtime_files[name])
        if (
            comparison.missing_keys_in_runtime
            or comparison.extra_keys_in_runtime
            or comparison.changed_common_keys
        ):
            semantic_mismatches.append(
                {
                    "file": name,
                    "missing_keys_in_runtime": comparison.missing_keys_in_runtime,
                    "extra_keys_in_runtime": comparison.extra_keys_in_runtime,
                    "changed_common_keys": comparison.changed_common_keys,
                }
            )

    matched_lines = _matching_mapping_lines(deck_config_ini, resolved_config_dir)
    mentions_config_dir = bool(matched_lines)
    status = "matched"
    if (
        not package_dir.is_dir()
        or not runtime_dir.is_dir()
        or missing_in_runtime
        or extra_in_runtime
        or semantic_mismatches
        or not mentions_config_dir
    ):
        status = "mismatch"

    return {
        "schema_version": 1,
        "status": status,
        "runtime_write_performed": False,
        "runtime_permission_impact": "none",
        "package_root": str(package),
        "runtime_root": str(runtime),
        "config_dir": resolved_config_dir,
        "package_config_path": str(package_dir),
        "runtime_config_path": str(runtime_dir),
        "package_config_exists": package_dir.is_dir(),
        "runtime_config_exists": runtime_dir.is_dir(),
        "package_file_count": len(package_files),
        "runtime_file_count": len(runtime_files),
        "missing_in_runtime": missing_in_runtime,
        "extra_in_runtime": extra_in_runtime,
        "semantic_mismatch_count": len(semantic_mismatches),
        "semantic_mismatches": semantic_mismatches,
        "deck_config_ini": {
            "path": str(deck_config_ini),
            "exists": deck_config_ini.is_file(),
            "mentions_config_dir": mentions_config_dir,
            "matched_lines": matched_lines,
        },
    }


def assert_runtime_matches_package(
    *,
    package_root: str | Path,
    runtime_root: str | Path,
    config_dir: str | None = None,
) -> dict[str, Any]:
    report = build_runtime_package_match_report(
        package_root=package_root,
        runtime_root=runtime_root,
        config_dir=config_dir,
    )
    if report["status"] != "matched":
        raise RuntimePackageMismatchError(report)
    return report
