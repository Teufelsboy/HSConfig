from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

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


def _make_directory_symlink(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")


def _make_junction(link: Path, target: Path) -> None:
    if os.name != "nt":
        pytest.skip("Windows junction coverage")
    completed = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        pytest.skip(f"directory junctions unavailable: {completed.stderr}")


class _ScandirContext:
    def __init__(self, entries) -> None:
        self._entries = iter(entries)

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._entries)


class _NamedDirEntry:
    def __init__(self, path: Path, name: str) -> None:
        self.path = str(path)
        self.name = name

    def stat(self, *, follow_symlinks: bool):
        return os.stat(self.path, follow_symlinks=follow_symlinks)


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


def test_duplicate_selection_uses_mtime_before_display_case(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    _write_package(
        outputs / "uppercase-old",
        deck_name="SHADOWPRIEST",
        staged=True,
        modified_time=1_700_000_000,
    )
    _write_package(
        outputs / "lowercase-new",
        deck_name="shadowpriest",
        staged=True,
        modified_time=1_710_000_000,
    )

    inventory = report_output_inventory.build_inventory(outputs)

    assert [row["path"] for row in inventory["likely_duplicate_candidates"]] == [
        "uppercase-old"
    ]


def test_duplicate_selection_uses_path_as_equal_mtime_tie_breaker(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    _write_package(
        outputs / "z-candidate",
        deck_name="Deck",
        staged=True,
        modified_time=1_700_000_000,
    )
    _write_package(
        outputs / "a-current",
        deck_name="Deck",
        staged=True,
        modified_time=1_700_000_000,
    )

    inventory = report_output_inventory.build_inventory(outputs)

    assert [row["path"] for row in inventory["likely_duplicate_candidates"]] == [
        "z-candidate"
    ]


def test_duplicate_selection_includes_newer_nested_package_file_mtime(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    nested_newer = outputs / "nested-newer"
    nominally_newer = outputs / "nominally-newer"
    _write_package(
        nested_newer,
        deck_name="Deck",
        staged=True,
        modified_time=1_700_000_000,
    )
    _write_package(
        nominally_newer,
        deck_name="Deck",
        staged=True,
        modified_time=1_710_000_000,
    )
    nested_file = (
        nested_newer
        / "04_package"
        / "CustomConfig"
        / "deck"
        / "GlobalValues.json"
    )
    os.utime(nested_file, (1_720_000_000, 1_720_000_000))

    inventory = report_output_inventory.build_inventory(outputs)

    assert inventory["entries"][0]["path"] == "nested-newer"
    assert inventory["entries"][0]["modified_time"] == "2024-07-03T09:46:40Z"
    assert [row["path"] for row in inventory["likely_duplicate_candidates"]] == [
        "nominally-newer"
    ]


def test_package_mtime_cap_bounds_scandir_consumption_and_stat_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = tmp_path / "outputs" / "entry" / "04_package"
    package.mkdir(parents=True)
    for index in range(10):
        (package / f"{index:02d}.json").write_text("{}", encoding="utf-8")
    original_scandir = os.scandir
    consumed = 0
    stated = 0

    class CountingEntry:
        def __init__(self, entry) -> None:
            self._entry = entry
            self.name = entry.name
            self.path = entry.path

        def stat(self, *, follow_symlinks: bool):
            nonlocal stated
            stated += 1
            return self._entry.stat(follow_symlinks=follow_symlinks)

    class CountingScandir:
        def __init__(self, path: Path) -> None:
            self._iterator = original_scandir(path)

        def __enter__(self):
            self._iterator.__enter__()
            return self

        def __exit__(self, *args):
            return self._iterator.__exit__(*args)

        def __iter__(self):
            nonlocal consumed
            for entry in self._iterator:
                consumed += 1
                yield CountingEntry(entry)

    monkeypatch.setattr(report_output_inventory, "_MAX_METADATA_NODES", 3)
    monkeypatch.setattr(os, "scandir", CountingScandir)

    modified_epoch = report_output_inventory._package_modified_epoch(
        package.resolve(),
        (tmp_path / "outputs").resolve(),
    )

    assert modified_epoch is None
    assert consumed == 4
    assert stated == 3


def test_inventory_limit_exceeded_cannot_displace_a_valid_duplicate_current(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = tmp_path / "outputs"
    valid = outputs / "valid"
    overflowing = outputs / "overflowing"
    _write_package(
        valid,
        deck_name="Deck",
        staged=True,
        modified_time=1_700_000_000,
    )
    _write_package(
        overflowing,
        deck_name="Deck",
        staged=True,
        modified_time=1_710_000_000,
    )
    package = overflowing / "04_package"
    for index in range(20):
        extra = package / f"extra-{index:02d}.json"
        extra.write_text("{}", encoding="utf-8")
        os.utime(extra, (1_720_000_000, 1_720_000_000))
    os.utime(package, (1_720_000_000, 1_720_000_000))
    monkeypatch.setattr(report_output_inventory, "_MAX_METADATA_NODES", 8)

    inventory = report_output_inventory.build_inventory(outputs)

    rows = {row["path"]: row for row in inventory["entries"]}
    assert rows["overflowing"] == {
        "deck": "Deck",
        "path": "overflowing",
        "modified_time": None,
        "package_status": "inventory_limit_exceeded",
    }
    assert rows["valid"]["package_status"] == "complete"
    assert rows["valid"]["modified_time"] == "2023-11-14T22:13:20Z"
    assert inventory["likely_duplicate_candidates"] == []
    assert all(set(row) == ALLOWED_ENTRY_FIELDS for row in rows.values())


def test_package_mtime_casefold_tie_overflow_fails_closed_for_any_scandir_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "outputs"
    package = root / "entry" / "04_package"
    package.mkdir(parents=True)
    upper = package / "upper-source"
    lower = package / "lower-source"
    upper.write_text("{}", encoding="utf-8")
    lower.write_text("{}", encoding="utf-8")
    os.utime(package, (1_600_000_000, 1_600_000_000))
    os.utime(upper, (1_700_000_000, 1_700_000_000))
    os.utime(lower, (1_800_000_000, 1_800_000_000))
    monkeypatch.setattr(report_output_inventory, "_MAX_METADATA_NODES", 1)

    def measured(order: list[_NamedDirEntry]) -> float | None:
        monkeypatch.setattr(
            os,
            "scandir",
            lambda _path: _ScandirContext(order),
        )
        return report_output_inventory._package_modified_epoch(
            package.resolve(),
            root.resolve(),
        )

    uppercase = _NamedDirEntry(upper, "A")
    lowercase = _NamedDirEntry(lower, "a")

    assert measured([uppercase, lowercase]) is None
    assert measured([lowercase, uppercase]) is None


def test_manifest_swap_after_resolution_cannot_emit_outside_deck(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = tmp_path / "outputs"
    entry = outputs / "local-entry"
    _write_package(
        entry,
        deck_name="LOCAL-DECK",
        staged=True,
        modified_time=1_700_000_000,
    )
    manifest = entry / "04_package" / "reports" / "input_manifest.json"
    outside_manifest = tmp_path / "outside-manifest.json"
    outside_manifest.write_text(
        json.dumps({"deck_name": "OUTSIDE-PRIVATE-DECK"}),
        encoding="utf-8",
    )
    original_resolve = report_output_inventory._resolve_selected
    swapped = False

    def resolve_then_swap(path: Path, root: Path) -> Path | None:
        nonlocal swapped
        resolved = original_resolve(path, root)
        if path == manifest and resolved is not None and not swapped:
            manifest.unlink()
            try:
                manifest.symlink_to(outside_manifest)
            except OSError as exc:
                pytest.skip(f"file symlinks unavailable: {exc}")
            swapped = True
        return resolved

    monkeypatch.setattr(
        report_output_inventory,
        "_resolve_selected",
        resolve_then_swap,
    )

    inventory = report_output_inventory.build_inventory(outputs)

    assert swapped
    assert inventory["entries"][0]["deck"] is None
    assert "OUTSIDE-PRIVATE-DECK" not in json.dumps(inventory)


def test_manifest_read_fails_closed_without_open_handle_final_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = tmp_path / "outputs"
    _write_package(
        outputs / "entry",
        deck_name="MUST-NOT-BE-EMITTED",
        staged=True,
        modified_time=1_700_000_000,
    )
    monkeypatch.setattr(
        report_output_inventory,
        "_opened_final_path",
        lambda _descriptor: None,
    )

    inventory = report_output_inventory.build_inventory(outputs)

    assert inventory["entries"][0]["deck"] is None
    assert "MUST-NOT-BE-EMITTED" not in json.dumps(inventory)


def test_inventory_skips_output_entry_symlink_that_escapes_root(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    external = tmp_path / "external-package"
    _write_package(
        external,
        deck_name="EXTERNAL-PRIVATE-DECK",
        staged=False,
        modified_time=1_700_000_000,
    )
    _make_directory_symlink(outputs / "escaped", external)
    before = _snapshot_tree(tmp_path)

    inventory = report_output_inventory.build_inventory(outputs)

    assert inventory == {"entries": [], "likely_duplicate_candidates": []}
    assert "EXTERNAL-PRIVATE-DECK" not in json.dumps(inventory)
    assert _snapshot_tree(tmp_path) == before


def test_inventory_skips_output_entry_junction_that_escapes_root(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    external = tmp_path / "junction-target"
    _write_package(
        external,
        deck_name="EXTERNAL-JUNCTION-DECK",
        staged=False,
        modified_time=1_700_000_000,
    )
    _make_junction(outputs / "escaped-junction", external)

    inventory = report_output_inventory.build_inventory(outputs)

    assert inventory == {"entries": [], "likely_duplicate_candidates": []}
    assert "EXTERNAL-JUNCTION-DECK" not in json.dumps(inventory)


@pytest.mark.parametrize("linked_component", ["04_package", "reports"])
def test_inventory_does_not_read_nested_package_links_that_escape_root(
    tmp_path: Path,
    linked_component: str,
) -> None:
    outputs = tmp_path / "outputs"
    entry = outputs / "local-entry"
    external = tmp_path / "external-package"
    _write_package(
        external,
        deck_name="EXTERNAL-NESTED-DECK",
        staged=False,
        modified_time=1_700_000_000,
    )
    if linked_component == "04_package":
        entry.mkdir(parents=True)
        _make_directory_symlink(entry / "04_package", external)
    else:
        package = entry / "04_package"
        (package / "CustomConfig").mkdir(parents=True)
        _make_directory_symlink(
            package / "reports",
            external / "reports",
        )

    inventory = report_output_inventory.build_inventory(outputs)

    assert inventory["entries"] == [
        {
            "deck": None,
            "path": "local-entry",
            "modified_time": inventory["entries"][0]["modified_time"],
            "package_status": "package_not_found",
        }
    ]
    assert inventory["likely_duplicate_candidates"] == []
    assert "EXTERNAL-NESTED-DECK" not in json.dumps(inventory)


def test_inventory_treats_broken_nested_package_link_as_not_found(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    entry = outputs / "broken-entry"
    entry.mkdir(parents=True)
    _make_directory_symlink(entry / "04_package", tmp_path / "missing-package")

    inventory = report_output_inventory.build_inventory(outputs)

    assert inventory["entries"][0]["deck"] is None
    assert inventory["entries"][0]["package_status"] == "package_not_found"


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
