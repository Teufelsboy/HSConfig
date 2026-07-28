"""Report a bounded, read-only inventory of HSConfig output packages."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _package_root(entry: Path) -> Path:
    staged_package = entry / "04_package"
    return staged_package if staged_package.is_dir() else entry


def _package_status(package: Path) -> str:
    reports = package / "reports"
    if not reports.is_dir():
        return "missing_reports"
    if not (reports / "input_manifest.json").is_file():
        return "missing_input_manifest"
    if not (package / "CustomConfig").is_dir():
        return "missing_custom_config"
    return "complete"


def _deck_name(package: Path) -> str | None:
    manifest = package / "reports" / "input_manifest.json"
    if not manifest.is_file():
        return None
    try:
        payload = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    deck_name = payload.get("deck_name") if isinstance(payload, dict) else None
    if not isinstance(deck_name, str) or not deck_name.strip():
        return None
    return deck_name


def _modified_epoch(package: Path) -> float:
    modified = package.stat().st_mtime
    for path in package.rglob("*"):
        try:
            modified = max(modified, path.stat().st_mtime)
        except OSError:
            continue
    return modified


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
        for entry in sorted(
            (path for path in root.iterdir() if path.is_dir()),
            key=lambda path: path.name.casefold(),
        ):
            package = _package_root(entry)
            modified_epoch = _modified_epoch(package)
            row = {
                "deck": _deck_name(package),
                "path": entry.relative_to(root).as_posix(),
                "modified_time": _utc_timestamp(modified_epoch),
                "package_status": _package_status(package),
            }
            internal_rows.append((row, modified_epoch))

    internal_rows.sort(
        key=lambda item: (
            (item[0]["deck"] or "").casefold(),
            item[0]["deck"] or "",
            -item[1],
            item[0]["path"].casefold(),
            item[0]["path"],
        )
    )
    grouped: dict[str, list[tuple[dict[str, Any], float]]] = defaultdict(list)
    for row in internal_rows:
        deck = row[0]["deck"]
        if isinstance(deck, str):
            grouped[deck.casefold()].append(row)

    likely_duplicates = [
        row
        for deck_key in sorted(grouped)
        for row, _modified in grouped[deck_key][1:]
    ]
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
