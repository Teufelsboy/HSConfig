from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from hsconfig.contract_preflight import GitPreflight, build_contract_preflight


def _clean_git() -> GitPreflight:
    return GitPreflight(
        branch="codex/test",
        upstream="origin/codex/test",
        dirty=False,
        ahead_origin_main=1,
        behind_origin_main=0,
        clean_for_runtime_work=True,
        ahead_upstream=0,
        behind_upstream=0,
    )


def test_contract_preflight_passes_for_repo_contract_with_clean_git_snapshot() -> None:
    payload = build_contract_preflight(Path("."), git=_clean_git())

    assert payload["status"] == "PASS"
    assert payload["runtime_apply_authority"] == "reports/operator_summary.json"
    assert payload["source_status_apply_blocking"] is False
    assert payload["diagnostic_only"] is True
    assert payload["failures"] == []
    assert payload["checks"]["repo_current"] is True
    assert payload["checks"]["checklist_listed_in_references"] is True
    assert payload["checks"]["no_default_only_visible"] is True
    assert payload["checks"]["source_status_nonblocking_visible"] is True
    assert payload["checks"]["runtime_surface_boundary_visible"] is True
    assert payload["checks"]["negative_scope_visible"] is True


def test_contract_preflight_reports_attention_when_git_is_dirty() -> None:
    dirty_git = GitPreflight(
        branch="codex/test",
        upstream="origin/codex/test",
        dirty=True,
        ahead_origin_main=1,
        behind_origin_main=0,
        clean_for_runtime_work=False,
        ahead_upstream=0,
        behind_upstream=0,
    )

    payload = build_contract_preflight(Path("."), git=dirty_git)

    assert payload["status"] == "ATTENTION"
    assert "repo_current" in payload["failures"]
    assert payload["source_status_apply_blocking"] is False
    assert payload["runtime_apply_authority"] == "reports/operator_summary.json"


def test_contract_preflight_cli_emits_json_without_writing_files(tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    before = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    result = subprocess.run(
        [sys.executable, "-m", "hsconfig.cli", "contract-preflight", "--repo-root", ".", "--json"],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    after = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout

    assert result.returncode in (0, 1)
    payload = json.loads(result.stdout)
    assert payload["diagnostic_only"] is True
    assert payload["runtime_apply_authority"] == "reports/operator_summary.json"
    assert before == after


def test_contract_preflight_is_registered_but_not_part_of_configure_path() -> None:
    parser_help = subprocess.run(
        [sys.executable, "-m", "hsconfig.cli", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert parser_help.returncode == 0
    assert "contract-preflight" in parser_help.stdout

    configure_help = subprocess.run(
        [sys.executable, "-m", "hsconfig.cli", "configure", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert configure_help.returncode == 0
    assert "contract-preflight" not in configure_help.stdout
