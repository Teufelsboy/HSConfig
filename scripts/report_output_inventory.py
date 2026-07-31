"""Report a bounded, read-only inventory of HSConfig output packages."""

from __future__ import annotations

import argparse
import json
import os
import stat
from collections import defaultdict
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path
from typing import Any

from hsconfig.current_output import lease_package_input


_MAX_METADATA_DEPTH = 128
_MAX_METADATA_NODES = 100_000


class _UnsafePathError(Exception):
    """A selected inventory path escaped the resolved output root."""


def _resolve_selected(path: Path, root: Path) -> Path | None:
    if not os.path.lexists(path):
        return None
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise _UnsafePathError from exc
    return resolved


def _windows_opened_final_path(descriptor: int) -> Path | None:
    try:
        import ctypes
        import msvcrt
        from ctypes import wintypes

        handle = msvcrt.get_osfhandle(descriptor)
        if handle == -1:
            return None
        get_final_path = ctypes.WinDLL(
            "kernel32",
            use_last_error=True,
        ).GetFinalPathNameByHandleW
        get_final_path.argtypes = [
            wintypes.HANDLE,
            wintypes.LPWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        get_final_path.restype = wintypes.DWORD
        size = get_final_path(handle, None, 0, 0)
        if size == 0:
            return None
        buffer = ctypes.create_unicode_buffer(size + 1)
        copied = get_final_path(handle, buffer, len(buffer), 0)
        if copied == 0 or copied >= len(buffer):
            return None
        final_path = buffer.value
    except (AttributeError, ImportError, OSError, ValueError):
        return None

    if final_path.startswith("\\\\?\\UNC\\"):
        final_path = "\\\\" + final_path[8:]
    elif final_path.startswith("\\\\?\\"):
        final_path = final_path[4:]
    result = Path(final_path)
    return result if result.is_absolute() else None


def _posix_opened_final_path(descriptor: int) -> Path | None:
    descriptor_link = Path("/proc/self/fd") / str(descriptor)
    try:
        final_path = os.readlink(descriptor_link)
    except OSError:
        return None
    if final_path.endswith(" (deleted)"):
        return None
    result = Path(final_path)
    return result if result.is_absolute() else None


def _opened_final_path(descriptor: int) -> Path | None:
    if os.name == "nt":
        return _windows_opened_final_path(descriptor)
    if os.name == "posix":
        return _posix_opened_final_path(descriptor)
    return None


def _descriptor_deck_name(
    manifest: Path,
    root: Path,
) -> tuple[bool, str | None]:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if os.name == "posix":
        flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(manifest, flags)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            return False, None
        final_path = _opened_final_path(descriptor)
        if final_path is None:
            return False, None
        try:
            final_path.relative_to(root)
        except ValueError:
            return False, None
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            payload = json.loads(handle.read().decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False, None
    finally:
        if descriptor is not None:
            os.close(descriptor)

    deck_name = payload.get("deck_name") if isinstance(payload, dict) else None
    if not isinstance(deck_name, str) or not deck_name.strip():
        return True, None
    return True, deck_name


def _selected_modified_epoch(paths: list[Path]) -> float:
    modified = 0.0
    for path in paths:
        try:
            modified = max(modified, path.stat().st_mtime)
        except OSError:
            continue
    return modified


def _is_link_or_reparse(path_stat: os.stat_result) -> bool:
    if stat.S_ISLNK(path_stat.st_mode):
        return True
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    file_attributes = getattr(path_stat, "st_file_attributes", 0)
    return bool(reparse_flag and file_attributes & reparse_flag)


def _package_modified_epoch(package: Path, root: Path) -> float | None:
    modified = _selected_modified_epoch([package])
    stack = [(package, 0)]
    visited: set[Path] = set()
    enumerated_nodes = 0
    inspected_nodes = 0
    incomplete = False
    while (
        stack
        and inspected_nodes < _MAX_METADATA_NODES
        and enumerated_nodes <= _MAX_METADATA_NODES
    ):
        directory, depth = stack.pop()
        if directory in visited or depth > _MAX_METADATA_DEPTH:
            continue
        visited.add(directory)
        processing_remaining = _MAX_METADATA_NODES - inspected_nodes
        enumeration_remaining = _MAX_METADATA_NODES + 1 - enumerated_nodes
        take = min(processing_remaining + 1, enumeration_remaining)
        if take <= 0:
            break
        try:
            with os.scandir(directory) as iterator:
                entries = list(islice(iterator, take))
        except OSError:
            incomplete = True
            continue
        enumerated_nodes += len(entries)
        entries.sort(
            key=lambda entry: (
                entry.name.casefold(),
                entry.name,
                os.path.normcase(os.path.abspath(entry.path)),
                os.path.abspath(entry.path),
            )
        )
        if len(entries) > processing_remaining:
            incomplete = True
        child_directories: list[Path] = []
        for entry in entries[:processing_remaining]:
            if inspected_nodes >= _MAX_METADATA_NODES:
                break
            inspected_nodes += 1
            try:
                entry_stat = entry.stat(follow_symlinks=False)
            except OSError:
                incomplete = True
                continue
            if _is_link_or_reparse(entry_stat):
                continue
            entry_path = Path(entry.path)
            try:
                resolved = _resolve_selected(entry_path, root)
            except _UnsafePathError:
                incomplete = True
                continue
            if resolved is None:
                incomplete = True
                continue
            modified = max(modified, entry_stat.st_mtime)
            if stat.S_ISDIR(entry_stat.st_mode):
                if depth < _MAX_METADATA_DEPTH:
                    child_directories.append(resolved)
                else:
                    incomplete = True
        stack.extend(
            (child, depth + 1) for child in reversed(child_directories)
        )
    if stack:
        incomplete = True
    return None if incomplete else modified


def _package_inventory_result(
    deck: str | None,
    package_status: str,
    package: Path,
    root: Path,
) -> tuple[str | None, str, float | None]:
    modified_epoch = _package_modified_epoch(package, root)
    if modified_epoch is None:
        return deck, "inventory_limit_exceeded", None
    return deck, package_status, modified_epoch


def _inspect_entry(
    root: Path,
    entry: Path,
    resolved_entry: Path,
) -> tuple[str | None, str, float | None]:
    try:
        with lease_package_input(entry) as lease:
            if lease.publication is not None:
                package_path = lease.package_root
                package = _resolve_selected(package_path, root)
                if package is None or not package.is_dir():
                    raise _UnsafePathError
            else:
                staged_path = entry / "04_package"
                staged = _resolve_selected(staged_path, root)
                if staged is not None and not staged.is_dir():
                    raise _UnsafePathError
                package_path = staged_path if staged is not None else entry
                package = staged if staged is not None else resolved_entry

            reports = _resolve_selected(package_path / "reports", root)
            if reports is None or not reports.is_dir():
                return _package_inventory_result(
                    None,
                    "missing_reports",
                    package,
                    root,
                )

            manifest = _resolve_selected(
                reports / "input_manifest.json",
                root,
            )
            if manifest is None:
                return _package_inventory_result(
                    None,
                    "missing_input_manifest",
                    package,
                    root,
                )

            custom_config = _resolve_selected(
                package_path / "CustomConfig",
                root,
            )
            if custom_config is None or not custom_config.is_dir():
                manifest_safe, deck_name = _descriptor_deck_name(
                    manifest,
                    root,
                )
                if not manifest_safe:
                    return (
                        None,
                        "package_not_found",
                        _selected_modified_epoch([resolved_entry]),
                    )
                return _package_inventory_result(
                    deck_name,
                    "missing_custom_config",
                    package,
                    root,
                )

            manifest_safe, deck_name = _descriptor_deck_name(manifest, root)
            if not manifest_safe:
                return (
                    None,
                    "package_not_found",
                    _selected_modified_epoch([resolved_entry]),
                )
            return _package_inventory_result(
                deck_name,
                "complete",
                package,
                root,
            )
    except _UnsafePathError:
        return (
            None,
            "package_not_found",
            _selected_modified_epoch([resolved_entry]),
        )
    except ValueError:
        return (
            None,
            "current_output_invalid",
            _selected_modified_epoch([resolved_entry]),
        )


def _utc_timestamp(epoch: float) -> str:
    return (
        datetime.fromtimestamp(epoch, tz=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def build_inventory(output_root: Path) -> dict[str, list[dict[str, Any]]]:
    """Return package rows and deterministic older same-deck candidates."""
    root = output_root.resolve()
    internal_rows: list[tuple[dict[str, Any], float | None]] = []
    if root.is_dir():
        for entry in sorted(root.iterdir(), key=lambda path: path.name.casefold()):
            try:
                resolved_entry = _resolve_selected(entry, root)
            except _UnsafePathError:
                continue
            if resolved_entry is None or not resolved_entry.is_dir():
                continue
            deck, package_status, modified_epoch = _inspect_entry(
                root,
                entry,
                resolved_entry,
            )
            row = {
                "deck": deck,
                "path": entry.relative_to(root).as_posix(),
                "modified_time": (
                    _utc_timestamp(modified_epoch)
                    if modified_epoch is not None
                    else None
                ),
                "package_status": package_status,
            }
            internal_rows.append((row, modified_epoch))

    internal_rows.sort(
        key=lambda item: (
            (item[0]["deck"] or "").casefold(),
            item[1] is None,
            -(item[1] if item[1] is not None else 0.0),
            item[0]["path"].casefold(),
            item[0]["path"],
            item[0]["deck"] or "",
        )
    )
    grouped: dict[str, list[tuple[dict[str, Any], float]]] = defaultdict(list)
    for row in internal_rows:
        row_data, modified_epoch = row
        deck = row_data["deck"]
        if isinstance(deck, str) and modified_epoch is not None:
            grouped[deck.casefold()].append((row_data, modified_epoch))

    likely_duplicates = []
    for deck_key in sorted(grouped):
        same_deck = sorted(
            grouped[deck_key],
            key=lambda item: (
                -item[1],
                item[0]["path"].casefold(),
                item[0]["path"],
            ),
        )
        likely_duplicates.extend(row for row, _modified in same_deck[1:])
    return {
        "entries": [row for row, _modified in internal_rows],
        "likely_duplicate_candidates": likely_duplicates,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output_root",
        nargs="?",
        type=Path,
        default=Path("outputs"),
        help="output root to inspect (default: outputs)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    print(json.dumps(build_inventory(args.output_root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
