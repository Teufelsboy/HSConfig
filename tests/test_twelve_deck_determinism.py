from __future__ import annotations

import json
from pathlib import Path
import subprocess

from hsconfig.build_input_catalog import load_audited_build_inputs


BUILD_INPUTS_PATH = Path("src/hsconfig/resources/audited_build_inputs.json")
BUILD_RESOURCES_PATH = Path("src/hsconfig/resources/audited_build_resources.json")
COVERAGE_SAFE_TIMEOUT_SECONDS = 900


def test_cli_verifies_all_audited_decks_deterministically(
) -> None:
    """Catches a deck-specific build drift or unsafe exception recovery."""
    audited = load_audited_build_inputs(BUILD_INPUTS_PATH)
    completed = subprocess.run(
        [
            "py",
            "-3.11",
            "scripts/verify_twelve_decks.py",
            "--build-inputs", str(BUILD_INPUTS_PATH),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        timeout=COVERAGE_SAFE_TIMEOUT_SECONDS,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    rows = payload["decks"]

    assert payload["passed"] is True
    assert tuple(row["deck_name"] for row in rows) == tuple(
        build.deck_name for build in audited.builds
    )
    assert len(rows) == 12
    assert all(
        row["first_content_root_sha256"] == row["second_content_root_sha256"]
        and row["configure_run_bytes_equal"]
        and row["runtime_old_or_new_safe"]
        for row in rows
    )
