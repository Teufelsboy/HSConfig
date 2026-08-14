from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts import report_output_inventory
from scripts.reconcile_outputs import reconcile_audited_outputs
from tests.helpers.controlled_subprocess import controlled_python_environment


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "docs" / "operator" / "audited-deck-catalog.json"
SCRIPT = ROOT / "scripts" / "report_output_inventory.py"


def test_report_adapter_uses_the_canonical_inventory(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"

    adapted = report_output_inventory.build_inventory(outputs)
    canonical = reconcile_audited_outputs(
        outputs_root=outputs,
        catalog_path=CATALOG,
    )

    assert adapted == {
        "audited_decks": canonical.audited_decks,
        "current_outputs": canonical.current_outputs,
        "revision_count": canonical.revision_count,
        "staging_count": canonical.staging_count,
        "unreferenced_revision_count": canonical.unreferenced_revision_count,
        "backup_count": canonical.backup_count,
        "rollback_count": canonical.rollback_count,
        "orphan_transaction_count": canonical.orphan_transaction_count,
        "orphan_receipt_count": canonical.orphan_receipt_count,
        "temporary_file_count": canonical.temporary_file_count,
        "invalid_count": canonical.invalid_count,
    }


def test_report_cli_is_read_only_and_emits_the_same_canonical_json(
    tmp_path: Path,
) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    sentinel = outputs / "sentinel.txt"
    sentinel.write_bytes(b"unchanged")
    before = (sentinel.read_bytes(), sentinel.stat().st_mtime_ns)

    completed = subprocess.run(
        [sys.executable, str(SCRIPT), str(outputs)],
        cwd=ROOT,
        env=controlled_python_environment(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == (
        report_output_inventory.build_inventory(outputs)
    )
    assert (sentinel.read_bytes(), sentinel.stat().st_mtime_ns) == before


def test_report_cli_has_no_mutation_mode() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "outputs", "--apply"],
        cwd=ROOT,
        env=controlled_python_environment(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "unrecognized arguments: --apply" in completed.stderr
