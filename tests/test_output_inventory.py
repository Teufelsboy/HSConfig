from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts import report_output_inventory


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "report_output_inventory.py"
ALLOWED_ENTRY_FIELDS = {
    "deck",
    "path",
    "modified_time",
    "package_status",
}


def _write_package(
    entry: Path,
    *,
    deck_name: str,
    staged: bool,
    modified_time: int,
    include_custom_config: bool = True,
) -> None:
    package = entry / "04_package" if staged else entry
    reports = package / "reports"
    reports.mkdir(parents=True)
    (reports / "input_manifest.json").write_text(
        json.dumps(
            {
                "deck_name": deck_name,
                "deck_code": "PRIVATE-DECK-CODE",
                "runtime_apply_allowed": True,
                "runtime_root": "C:/private/runtime",
            }
        ),
        encoding="utf-8",
    )
    (reports / "operator_summary.json").write_text(
        json.dumps(
            {
                "technical_status": "VALID_PACKAGE",
                "runtime_apply_allowed": True,
            }
        ),
        encoding="utf-8",
    )
    if include_custom_config:
        config = package / "CustomConfig" / deck_name.casefold()
        config.mkdir(parents=True)
        (config / "GlobalValues.json").write_text("{}", encoding="utf-8")

    for path in sorted(entry.rglob("*"), reverse=True):
        os.utime(path, (modified_time, modified_time))
    os.utime(entry, (modified_time, modified_time))


def _snapshot_tree(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.relative_to(root).as_posix(): (
            path.read_bytes(),
            path.stat().st_mtime_ns,
        )
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_inventory_supports_staged_and_direct_packages_without_private_fields(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    old_entry = outputs / "shadow-old"
    new_entry = outputs / "shadow-new"
    other_entry = outputs / "other"
    _write_package(
        old_entry,
        deck_name="ShadowPriest",
        staged=True,
        modified_time=1_700_000_000,
    )
    _write_package(
        new_entry,
        deck_name="ShadowPriest",
        staged=False,
        modified_time=1_710_000_000,
    )
    _write_package(
        other_entry,
        deck_name="OtherDeck",
        staged=True,
        modified_time=1_705_000_000,
        include_custom_config=False,
    )

    inventory = report_output_inventory.build_inventory(outputs)

    assert inventory == {
        "entries": [
            {
                "deck": "OtherDeck",
                "path": "other",
                "modified_time": "2024-01-11T19:06:40Z",
                "package_status": "missing_custom_config",
            },
            {
                "deck": "ShadowPriest",
                "path": "shadow-new",
                "modified_time": "2024-03-09T16:00:00Z",
                "package_status": "complete",
            },
            {
                "deck": "ShadowPriest",
                "path": "shadow-old",
                "modified_time": "2023-11-14T22:13:20Z",
                "package_status": "complete",
            },
        ],
        "likely_duplicate_candidates": [
            {
                "deck": "ShadowPriest",
                "path": "shadow-old",
                "modified_time": "2023-11-14T22:13:20Z",
                "package_status": "complete",
            }
        ],
    }
    for collection in inventory.values():
        for row in collection:
            assert set(row) == ALLOWED_ENTRY_FIELDS
    assert "PRIVATE-DECK-CODE" not in json.dumps(inventory)
    assert "runtime_apply_allowed" not in json.dumps(inventory)
    assert "VALID_PACKAGE" not in json.dumps(inventory)


def test_inventory_is_read_only_and_cli_writes_only_stdout(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    _write_package(
        outputs / "deck",
        deck_name="Deck",
        staged=True,
        modified_time=1_700_000_000,
    )
    before = _snapshot_tree(outputs)

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), str(outputs)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout)["entries"][0]["deck"] == "Deck"
    assert completed.stderr == ""
    assert _snapshot_tree(outputs) == before


def test_inventory_cli_exposes_no_mutation_or_report_output_flags() -> None:
    parser = report_output_inventory.build_parser()
    option_strings = {
        option
        for action in parser._actions
        for option in action.option_strings
    }

    assert option_strings == {"-h", "--help"}
    for forbidden in (
        "--delete",
        "--clean",
        "--move",
        "--archive",
        "--retain",
        "--out",
    ):
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), forbidden],
            capture_output=True,
            text=True,
        )
        assert completed.returncode != 0
