"""Report a bounded, read-only inventory of HSConfig output packages."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def _deck_name(manifest: Path | None) -> str | None:
    if manifest is None or not manifest.is_file():
        return None
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    deck_name = payload.get("deck_name") if isinstance(payload, dict) else None
    if not isinstance(deck_name, str) or not deck_name.strip():
        return None
    return deck_name


def _modified_epoch(paths: list[Path]) -> float:
    modified = 0.0
    for path in paths:
        try:
            modified = max(modified, path.stat().st_mtime)
        except OSError:
            continue
    return modified


def _inspect_entry(
    root: Path,
    entry: Path,
    resolved_entry: Path,
) -> tuple[str | None, str, float]:
    selected = [resolved_entry]
    try:
        staged_path = entry / "04_package"
        staged = _resolve_selected(staged_path, root)
        if staged is not None and not staged.is_dir():
            raise _UnsafePathError
        package_path = staged_path if staged is not None else entry
        package = staged if staged is not None else resolved_entry
        selected.append(package)

        reports = _resolve_selected(package_path / "reports", root)
        if reports is None or not reports.is_dir():
            return None, "missing_reports", _modified_epoch(selected)
        selected.append(reports)

        manifest = _resolve_selected(reports / "input_manifest.json", root)
        if manifest is None or not manifest.is_file():
            return None, "missing_input_manifest", _modified_epoch(selected)
        selected.append(manifest)

        custom_config = _resolve_selected(package_path / "CustomConfig", root)
        if custom_config is None or not custom_config.is_dir():
            return (
                _deck_name(manifest),
                "missing_custom_config",
                _modified_epoch(selected),
            )
        selected.append(custom_config)
    except _UnsafePathError:
        return None, "package_not_found", _modified_epoch([resolved_entry])

    return _deck_name(manifest), "complete", _modified_epoch(selected)


def _utc_timestamp(epoch: float) -> str:
    return (
        datetime.fromtimestamp(epoch, tz=timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def build_inventory(output_root: Path) -> dict[str, list[dict[str, Any]]]:
    """Return package rows and deterministic older same-deck candidates."""
    root = output_root.resolve()
    internal_rows: list[tuple[dict[str, Any], float]] = []
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
                "modified_time": _utc_timestamp(modified_epoch),
                "package_status": package_status,
            }
            internal_rows.append((row, modified_epoch))

    internal_rows.sort(
        key=lambda item: (
            (item[0]["deck"] or "").casefold(),
            -item[1],
            item[0]["path"].casefold(),
            item[0]["path"],
            item[0]["deck"] or "",
        )
    )
    grouped: dict[str, list[tuple[dict[str, Any], float]]] = defaultdict(list)
    for row in internal_rows:
        deck = row[0]["deck"]
        if isinstance(deck, str):
            grouped[deck.casefold()].append(row)

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
