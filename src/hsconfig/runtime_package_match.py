from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hsconfig.io import decode_json_bytes, read_json
from hsconfig.models import InputManifest
from hsconfig.package_io import (
    BoundedFilesystemPackageView,
    capture_plain_ancestor_guard,
    hold_plain_directory,
    path_lexists,
    path_identity_from_status,
    snapshot_bounded_filesystem_package,
    status_is_reparse,
)


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


def _resolve_logical_config_dir(
    custom_config: Path,
    snapshot: BoundedFilesystemPackageView,
    logical_config_dir: str | None,
) -> str:
    if logical_config_dir is not None:
        _validate_config_dir(logical_config_dir)
        return _resolve_snapshot_directory_name(snapshot, logical_config_dir)

    candidates = sorted(
        name
        for name in snapshot.directory_names
        if "/" not in name
    )
    if len(candidates) != 1:
        raise ValueError(
            "Expected exactly one package config directory under "
            f"{custom_config}, found {len(candidates)}."
        )
    return candidates[0]


def _resolve_snapshot_directory_name(
    snapshot: BoundedFilesystemPackageView | None,
    requested: str,
) -> str:
    if snapshot is None:
        return requested
    top_level = tuple(
        name for name in snapshot.directory_names if "/" not in name
    )
    matches = tuple(
        name
        for name in top_level
        if (
            name.casefold() == requested.casefold()
            if os.name == "nt"
            else name == requested
        )
    )
    if len(matches) > 1:
        raise ValueError("filesystem_directory_name_ambiguous")
    return matches[0] if matches else requested


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


def _snapshot_custom_config(
    path: Path,
) -> BoundedFilesystemPackageView | None:
    if not path_lexists(path):
        return None
    guard = capture_plain_ancestor_guard(path)
    with hold_plain_directory(path) as directory:
        guard.validate()
        snapshot = snapshot_bounded_filesystem_package(path)
        directory.validate()
        guard.validate()
    return snapshot


def _config_directory_exists(
    snapshot: BoundedFilesystemPackageView | None,
    config_dir: str,
) -> bool:
    return snapshot is not None and config_dir in snapshot.directory_names


def _snapshot_config_directory(
    custom_config: Path,
    config_dir: str,
) -> BoundedFilesystemPackageView | None:
    child = custom_config / config_dir
    if not path_lexists(child):
        return None
    guard = capture_plain_ancestor_guard(child)
    with hold_plain_directory(custom_config) as parent:
        status = parent.child_status(config_dir)
        if not stat.S_ISDIR(status.st_mode) or status_is_reparse(status):
            raise ValueError("filesystem_directory_invalid")
        identity = path_identity_from_status(status)
        with hold_plain_directory(
            child,
            expected_identity=identity,
        ) as directory:
            parent.validate()
            guard.validate()
            snapshot = snapshot_bounded_filesystem_package(child)
            directory.validate()
            parent.validate()
            guard.validate()
    return snapshot


def _json_files(
    snapshot: BoundedFilesystemPackageView | None,
) -> dict[str, Any]:
    if snapshot is None:
        return {}
    return {
        name: decode_json_bytes(snapshot.read_bytes(name))
        for name in snapshot.file_names()
        if "/" not in name
        and name.endswith(".json")
    }


def _deck_name_from_manifest(package_root: Path) -> str:
    manifest_path = package_root / "reports" / "input_manifest.json"
    if not manifest_path.is_file():
        raise ValueError(
            f"Runtime identity requires input manifest: {manifest_path}"
        )
    try:
        manifest = read_json(manifest_path)
    except (OSError, ValueError) as exc:
        raise ValueError(
            f"Runtime identity requires a valid input manifest: {manifest_path}"
        ) from exc
    if not isinstance(manifest, dict):
        raise ValueError(
            f"Runtime identity input manifest must be a JSON object: {manifest_path}"
        )
    required_fields = ("deck_name", "deck_code", "runtime_root")
    if any(
        not isinstance(manifest.get(field), str)
        or not str(manifest[field]).strip()
        for field in required_fields
    ):
        raise ValueError(
            "Runtime identity requires non-empty deck_name, deck_code, and "
            f"runtime_root in input manifest: {manifest_path}"
        )
    input_manifest = InputManifest.from_dict(manifest)
    deck_name = input_manifest.deck_name.strip()
    if any(char in deck_name for char in "\r\n="):
        raise ValueError(
            "Deck name is not safe for deck_config.ini mapping: "
            f"{deck_name!r}"
        )
    return deck_name


def _mapping_lines_for_deck_name(
    content: bytes | None,
    *,
    expected_deck_name: str,
    allow_sectionless: bool = False,
) -> list[str]:
    if content is None:
        return []
    lines = content.decode("utf-8-sig").splitlines()
    has_sections = any(
        stripped.startswith("[") and stripped.endswith("]")
        for line in lines
        if (stripped := line.strip())
    )
    matched_lines = []
    in_configs = allow_sectionless and not has_sections
    expected = expected_deck_name.casefold()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_configs = stripped.casefold() == "[configs]"
            continue
        if not stripped or stripped.startswith(("#", ";")) or "=" not in stripped:
            continue
        key, _ = stripped.split("=", 1)
        if in_configs and key.strip().casefold() == expected:
            matched_lines.append(line)
    return matched_lines


def _matching_mapping_lines(
    content: bytes | None,
    *,
    expected_deck_name: str,
    config_dir: str,
    allow_sectionless: bool = False,
) -> list[str]:
    return [
        line
        for line in _mapping_lines_for_deck_name(
            content,
            expected_deck_name=expected_deck_name,
            allow_sectionless=allow_sectionless,
        )
        if (
            line.split("=", 1)[1].strip().casefold()
            == config_dir.casefold()
            if os.name == "nt"
            else line.split("=", 1)[1].strip() == config_dir
        )
    ]


def _resolve_mapped_runtime_config_dir(
    content: bytes | None,
    *,
    expected_deck_name: str,
    fallback_config_dir: str,
    expected_config_dir: str,
) -> tuple[str, bool]:
    mapping_lines = _mapping_lines_for_deck_name(
        content,
        expected_deck_name=expected_deck_name,
    )
    if len(mapping_lines) != 1:
        return fallback_config_dir, False
    mapped_config_dir = mapping_lines[0].split("=", 1)[1].strip()
    try:
        _validate_config_dir(mapped_config_dir)
    except ValueError:
        return fallback_config_dir, False
    if mapped_config_dir != expected_config_dir:
        return fallback_config_dir, False
    return mapped_config_dir, True


def _runtime_package_root_sha256(
    snapshot: BoundedFilesystemPackageView,
) -> str:
    files = snapshot.file_names()
    records = b"".join(
        (
            f"{name}\0{len(snapshot.read_bytes(name))}\0"
            f"{hashlib.sha256(snapshot.read_bytes(name)).hexdigest()}\n"
        ).encode("utf-8")
        for name in files
    )
    return hashlib.sha256(records).hexdigest()


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
    logical_config_dir: str | None = None,
    runtime_config_dir: str | None = None,
) -> dict[str, Any]:
    package = Path(package_root)
    runtime = Path(runtime_root)
    if config_dir is not None and (
        logical_config_dir is not None or runtime_config_dir is not None
    ):
        raise ValueError("config directory arguments conflict")
    package_custom_config = package / "CustomConfig"
    runtime_custom_config = runtime / "CustomConfig"
    deck_config_ini = runtime_custom_config / "deck_config.ini"
    package_snapshot = _snapshot_custom_config(package_custom_config)
    if package_snapshot is None:
        raise ValueError(
            f"Expected package CustomConfig directory: {package_custom_config}"
        )
    runtime_snapshot = _snapshot_custom_config(runtime_custom_config)
    deck_config_content = (
        runtime_snapshot.read_bytes("deck_config.ini")
        if runtime_snapshot is not None
        and runtime_snapshot.exists("deck_config.ini")
        else None
    )
    expected_deck_name: str | None = None
    auto_resolution = config_dir is None and runtime_config_dir is None
    runtime_mapping_identity_valid = not auto_resolution
    if config_dir is not None:
        _validate_config_dir(config_dir)
        resolved_logical_config_dir = _resolve_snapshot_directory_name(
            package_snapshot,
            config_dir,
        )
    else:
        resolved_logical_config_dir = _resolve_logical_config_dir(
            package_custom_config,
            package_snapshot,
            logical_config_dir,
        )
    package_config_snapshot = _snapshot_config_directory(
        package_custom_config,
        resolved_logical_config_dir,
    )
    package_runtime_root_sha256 = (
        _runtime_package_root_sha256(package_config_snapshot)
        if package_config_snapshot is not None
        else hashlib.sha256(b"").hexdigest()
    )
    if config_dir is not None:
        resolved_runtime_config_dir = _resolve_snapshot_directory_name(
            runtime_snapshot,
            config_dir,
        )
    else:
        if runtime_config_dir is None:
            expected_deck_name = _deck_name_from_manifest(package)
            expected_runtime_config_dir = (
                f"{resolved_logical_config_dir}--sha256-"
                f"{package_runtime_root_sha256}"
            )
            (
                resolved_runtime_config_dir,
                runtime_mapping_identity_valid,
            ) = _resolve_mapped_runtime_config_dir(
                deck_config_content,
                expected_deck_name=expected_deck_name,
                fallback_config_dir=resolved_logical_config_dir,
                expected_config_dir=expected_runtime_config_dir,
            )
            resolved_runtime_config_dir = _resolve_snapshot_directory_name(
                runtime_snapshot,
                resolved_runtime_config_dir,
            )
        else:
            _validate_config_dir(runtime_config_dir)
            resolved_runtime_config_dir = _resolve_snapshot_directory_name(
                runtime_snapshot,
                runtime_config_dir,
            )
        _validate_config_dir(resolved_runtime_config_dir)
    package_dir = package / "CustomConfig" / resolved_logical_config_dir
    if not auto_resolution:
        expected_runtime_config_dir = resolved_runtime_config_dir
    runtime_dir = runtime / "CustomConfig" / resolved_runtime_config_dir
    runtime_config_snapshot = _snapshot_config_directory(
        runtime_custom_config,
        resolved_runtime_config_dir,
    )
    runtime_package_root_sha256 = (
        _runtime_package_root_sha256(runtime_config_snapshot)
        if runtime_config_snapshot is not None
        else None
    )
    runtime_tree_identity_valid = (
        not auto_resolution
        or runtime_package_root_sha256 == package_runtime_root_sha256
    )
    if expected_deck_name is None:
        expected_deck_name = _deck_name_from_manifest(package)

    package_files = _json_files(package_config_snapshot)
    runtime_files = _json_files(runtime_config_snapshot)
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

    matched_lines = _matching_mapping_lines(
        deck_config_content,
        expected_deck_name=expected_deck_name,
        config_dir=resolved_runtime_config_dir,
        allow_sectionless=not auto_resolution,
    )
    deck_name_mapping_lines = _mapping_lines_for_deck_name(
        deck_config_content,
        expected_deck_name=expected_deck_name,
        allow_sectionless=not auto_resolution,
    )
    matching_mapping_count = len(matched_lines)
    mapping_ambiguous = len(deck_name_mapping_lines) > 1
    mentions_config_dir = bool(matched_lines)
    status = "matched"
    if (
        package_config_snapshot is None
        or runtime_config_snapshot is None
        or not package_files
        or missing_in_runtime
        or extra_in_runtime
        or semantic_mismatches
        or matching_mapping_count != 1
        or mapping_ambiguous
        or not runtime_mapping_identity_valid
        or not runtime_tree_identity_valid
    ):
        status = "mismatch"

    return {
        "schema_version": 1,
        "status": status,
        "runtime_write_performed": False,
        "runtime_permission_impact": "none",
        "package_root": str(package),
        "runtime_root": str(runtime),
        "config_dir": resolved_runtime_config_dir,
        "logical_config_dir": resolved_logical_config_dir,
        "runtime_config_dir": resolved_runtime_config_dir,
        "expected_runtime_config_dir": expected_runtime_config_dir,
        "runtime_mapping_identity_valid": runtime_mapping_identity_valid,
        "package_runtime_root_sha256": package_runtime_root_sha256,
        "runtime_package_root_sha256": runtime_package_root_sha256,
        "runtime_tree_identity_valid": runtime_tree_identity_valid,
        "expected_deck_name": expected_deck_name,
        "matching_mapping_count": matching_mapping_count,
        "mapping_ambiguous": mapping_ambiguous,
        "package_config_path": str(package_dir),
        "runtime_config_path": str(runtime_dir),
        "package_config_exists": package_config_snapshot is not None,
        "runtime_config_exists": runtime_config_snapshot is not None,
        "package_file_count": len(package_files),
        "runtime_file_count": len(runtime_files),
        "missing_in_runtime": missing_in_runtime,
        "extra_in_runtime": extra_in_runtime,
        "semantic_mismatch_count": len(semantic_mismatches),
        "semantic_mismatches": semantic_mismatches,
        "deck_config_ini": {
            "path": str(deck_config_ini),
            "exists": deck_config_content is not None,
            "mentions_config_dir": mentions_config_dir,
            "matched_lines": matched_lines,
        },
    }


def assert_runtime_matches_package(
    *,
    package_root: str | Path,
    runtime_root: str | Path,
    config_dir: str | None = None,
    logical_config_dir: str | None = None,
    runtime_config_dir: str | None = None,
) -> dict[str, Any]:
    report = build_runtime_package_match_report(
        package_root=package_root,
        runtime_root=runtime_root,
        config_dir=config_dir,
        logical_config_dir=logical_config_dir,
        runtime_config_dir=runtime_config_dir,
    )
    if report["status"] != "matched":
        raise RuntimePackageMismatchError(report)
    return report
