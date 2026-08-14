from __future__ import annotations

import json
import subprocess

from scripts import check_hsconfig_currentness as currentness_script
from scripts.check_hsconfig_currentness import (
    RepoCurrentness,
    build_currentness,
    parse_ahead_behind,
    parse_status_short,
)


def test_parse_clean_branch_status() -> None:
    branch, dirty = parse_status_short("## codex/hsconfig-canonical-source-status-sync\n")

    assert branch == "codex/hsconfig-canonical-source-status-sync"
    assert dirty is False


def test_parse_dirty_branch_status() -> None:
    branch, dirty = parse_status_short(
        "## codex/hsconfig-canonical-source-status-sync\n"
        " M src/hsconfig/source_candidate_registry.py\n"
    )

    assert branch == "codex/hsconfig-canonical-source-status-sync"
    assert dirty is True


def test_parse_ahead_behind_counts() -> None:
    assert parse_ahead_behind("54\t0\n") == (54, 0)
    assert parse_ahead_behind("0 2\n") == (0, 2)


def test_build_currentness_reports_git_snapshot(monkeypatch, tmp_path) -> None:
    def fake_run_git(cwd, *args, check=True):
        assert cwd == tmp_path
        if args == ("status", "--short", "--branch"):
            stdout = "## codex/hsconfig-audit...origin/codex/hsconfig-audit\n"
            return subprocess.CompletedProcess(["git", *args], 0, stdout=stdout, stderr="")
        if args == (
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{u}",
        ):
            return subprocess.CompletedProcess(
                ["git", *args],
                0,
                stdout="origin/codex/hsconfig-audit\n",
                stderr="",
            )
        if args == ("rev-list", "--left-right", "--count", "HEAD...origin/main"):
            return subprocess.CompletedProcess(["git", *args], 0, stdout="7\t0\n", stderr="")
        raise AssertionError(args)

    monkeypatch.setattr(currentness_script, "_run_git", fake_run_git)

    currentness = build_currentness(tmp_path)

    assert currentness == RepoCurrentness(
        cwd=str(tmp_path),
        branch="codex/hsconfig-audit",
        upstream="origin/codex/hsconfig-audit",
        dirty=False,
        ahead_origin_main=7,
        behind_origin_main=0,
        clean_for_runtime_work=True,
        origin_main_error=None,
    )


def test_build_currentness_marks_missing_origin_main_not_clean(monkeypatch, tmp_path) -> None:
    def fake_run_git(cwd, *args, check=True):
        if args == ("status", "--short", "--branch"):
            return subprocess.CompletedProcess(
                ["git", *args],
                0,
                stdout="## codex/hsconfig-audit\n",
                stderr="",
            )
        if args == (
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{u}",
        ):
            return subprocess.CompletedProcess(["git", *args], 1, stdout="", stderr="")
        if args == ("rev-list", "--left-right", "--count", "HEAD...origin/main"):
            return subprocess.CompletedProcess(
                ["git", *args],
                128,
                stdout="",
                stderr="fatal: ambiguous argument 'HEAD...origin/main'",
            )
        raise AssertionError(args)

    monkeypatch.setattr(currentness_script, "_run_git", fake_run_git)

    currentness = build_currentness(tmp_path)

    assert currentness.clean_for_runtime_work is False
    assert currentness.behind_origin_main == 1
    assert "origin/main" in currentness.origin_main_error


def test_currentness_cli_json_exit_code_reflects_clean_for_runtime_work(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        currentness_script,
        "build_currentness",
        lambda cwd: RepoCurrentness(
            cwd=str(cwd),
            branch="codex/hsconfig-audit",
            upstream=None,
            dirty=True,
            ahead_origin_main=0,
            behind_origin_main=0,
            clean_for_runtime_work=False,
            origin_main_error=None,
        ),
    )

    exit_code = currentness_script.main(["--cwd", ".", "--json"])

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["dirty"] is True
    assert payload["clean_for_runtime_work"] is False
