from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")
ENGINE_OID = "b736b4c1501494e555dee38fdd5ce9ea24a00c47"
SUBJECTS = (
    "feat: establish the HSConfig pre-run contract engine",
    "feat: add the audited twelve-deck contract catalog",
    "fix: harden atomic publication and pre-run authority",
    "chore: establish proprietary repository governance",
)
OBSOLETE_OPERATOR_PATHS = (
    "docs/operator/autonomous-source-builder-next.md",
    "docs/operator/boarlock-fracking-source-decision.md",
    "docs/operator/git-branch-cleanup-audit-2026-07-17.md",
    "docs/operator/kingslayer-quick-pick-source-decision.md",
    "docs/operator/source-backed-strong-closure.md",
    "docs/operator/source-builder-workflow.md",
    "docs/operator/universal-wild-no-block-contract.md",
)


def _run(*argv: str, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=cwd,
        check=check,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def _git(repository: Path, *arguments: str) -> str:
    return _run("git", *arguments, cwd=repository).stdout.strip()


def _parse_script(path: Path) -> dict[str, object]:
    assert POWERSHELL is not None
    command = r"""
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:TASK4_AST_PATH, [ref]$tokens, [ref]$errors
)
$commands = @($ast.FindAll({
    param($node)
    $node -is [System.Management.Automation.Language.CommandAst]
}, $true) | ForEach-Object { $_.Extent.Text })
$parameters = @($ast.ParamBlock.Parameters | ForEach-Object { $_.Name.VariablePath.UserPath })
[pscustomobject]@{
    errors = @($errors | ForEach-Object { $_.Message })
    commands = $commands
    parameters = $parameters
    text = $ast.Extent.Text
} | ConvertTo-Json -Depth 5 -Compress
"""
    environment = dict(os.environ)
    environment["TASK4_AST_PATH"] = str(path)
    completed = subprocess.run(
        (POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", command),
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
    )
    return json.loads(completed.stdout)


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required")
def test_build_script_ast_freezes_signed_four_commit_graph_without_ref_mutation() -> None:
    parsed = _parse_script(SCRIPTS / "build_curated_history.ps1")
    assert parsed["errors"] == []
    parameters = set(parsed["parameters"])
    assert {
        "ExpectedOldOid",
        "EngineMilestoneOid",
        "HardeningMilestoneOid",
        "GovernanceMilestoneOid",
        "TemporaryIndexPath",
    } <= parameters
    text = str(parsed["text"])
    assert ENGINE_OID in text
    assert all(subject in text for subject in SUBJECTS)
    assert all(path in text for path in OBSOLETE_OPERATOR_PATHS)
    verifier_text = str(_parse_script(SCRIPTS / "verify_curated_history.ps1")["text"])
    assert all(path in verifier_text for path in OBSOLETE_OPERATOR_PATHS)
    commands = [str(item).lower() for item in parsed["commands"]]
    commit_tree = [item for item in commands if "commit-tree" in item]
    assert len(commit_tree) == 4
    assert all("-s" in item for item in commit_tree)
    assert sum("'-p'" in item for item in commit_tree) == 3
    assert "'rm', '-r', '-f', '--cached'" in text
    prohibited = ("git checkout", "git switch", "git branch", "git push --force")
    assert not any(token in item for token in prohibited for item in commands)
    assert "update-ref refs/heads/main" not in text.lower()
    assert "finally" in text.lower()


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required")
def test_builder_rejects_wrong_engine_oid_and_repository_internal_index(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.name", "Test")
    _git(repository, "config", "user.email", "test@example.invalid")
    (repository / "README.md").write_text("test\n", encoding="utf-8")
    _git(repository, "add", "README.md")
    _git(repository, "commit", "-q", "-m", "seed")
    oid = _git(repository, "rev-parse", "HEAD")
    script = SCRIPTS / "build_curated_history.ps1"

    wrong_engine = _run(
        POWERSHELL,
        "-NoProfile",
        "-NonInteractive",
        "-File",
        str(script),
        "-ExpectedOldOid",
        oid,
        "-EngineMilestoneOid",
        oid,
        "-HardeningMilestoneOid",
        oid,
        "-GovernanceMilestoneOid",
        oid,
        "-TemporaryIndexPath",
        str(tmp_path / "index"),
        cwd=repository,
        check=False,
    )
    assert wrong_engine.returncode != 0
    assert "engine_milestone_oid_mismatch" in (wrong_engine.stdout + wrong_engine.stderr)

    internal_index = _run(
        POWERSHELL,
        "-NoProfile",
        "-NonInteractive",
        "-File",
        str(script),
        "-ExpectedOldOid",
        oid,
        "-EngineMilestoneOid",
        ENGINE_OID,
        "-HardeningMilestoneOid",
        oid,
        "-GovernanceMilestoneOid",
        oid,
        "-TemporaryIndexPath",
        str(repository / ".git" / "task4.index"),
        cwd=repository,
        check=False,
    )
    assert internal_index.returncode != 0
    assert "temporary_index_must_be_external" in (
        internal_index.stdout + internal_index.stderr
    )


def test_cutover_candidate_ignore_is_exact_and_does_not_mask_adjacent_names(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _git(repository, "init", "-q")
    (repository / ".gitignore").write_text(
        (ROOT / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8"
    )
    candidate = repository / ".cutover-candidate" / "detached"
    candidate.mkdir(parents=True)
    (candidate / "member").write_text("x", encoding="utf-8")
    adjacent = repository / ".cutover-candidate-nearby" / "member"
    adjacent.parent.mkdir()
    adjacent.write_text("x", encoding="utf-8")
    ignored = _run(
        "git", "check-ignore", "-q", ".cutover-candidate/detached/member", cwd=repository, check=False
    )
    visible = _run(
        "git", "check-ignore", "-q", ".cutover-candidate-nearby/member", cwd=repository, check=False
    )
    assert ignored.returncode == 0
    assert visible.returncode == 1
    rules = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert rules.count("/.cutover-candidate/") == 1


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required")
def test_sync_script_deletes_only_unchanged_old_tracked_paths(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.name", "Test")
    _git(repository, "config", "user.email", "test@example.invalid")
    (repository / "drop.txt").write_text("old\n", encoding="utf-8")
    (repository / "keep.txt").write_text("keep\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-q", "-m", "old")
    old_oid = _git(repository, "rev-parse", "HEAD")
    (repository / "drop.txt").unlink()
    _git(repository, "add", "-u")
    _git(repository, "commit", "-q", "-m", "new")
    new_oid = _git(repository, "rev-parse", "HEAD")
    _git(repository, "reset", "--hard", "-q", old_oid)

    script = SCRIPTS / "sync_curated_worktree.ps1"
    dry = _run(
        POWERSHELL,
        "-NoProfile",
        "-NonInteractive",
        "-File",
        str(script),
        "-OldOid",
        old_oid,
        "-NewTipOid",
        new_oid,
        "-DryRun",
        cwd=repository,
    )
    manifest = json.loads(dry.stdout)
    assert manifest["paths"] == ["drop.txt"]
    assert (repository / "drop.txt").exists()
    _run(
        POWERSHELL,
        "-NoProfile",
        "-NonInteractive",
        "-File",
        str(script),
        "-OldOid",
        old_oid,
        "-NewTipOid",
        new_oid,
        "-Apply",
        "-ExpectedManifestSha256",
        manifest["manifest_sha256"],
        cwd=repository,
    )
    assert not (repository / "drop.txt").exists()
    assert (repository / "keep.txt").read_text(encoding="utf-8") == "keep\n"


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required")
def test_sync_script_fails_closed_for_modified_deletion_candidate(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.name", "Test")
    _git(repository, "config", "user.email", "test@example.invalid")
    (repository / "drop.txt").write_text("old\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-q", "-m", "old")
    old_oid = _git(repository, "rev-parse", "HEAD")
    (repository / "drop.txt").unlink()
    _git(repository, "add", "-u")
    _git(repository, "commit", "-q", "-m", "new")
    new_oid = _git(repository, "rev-parse", "HEAD")
    _git(repository, "reset", "--hard", "-q", old_oid)
    (repository / "drop.txt").write_text("changed\n", encoding="utf-8")
    result = _run(
        POWERSHELL,
        "-NoProfile",
        "-NonInteractive",
        "-File",
        str(SCRIPTS / "sync_curated_worktree.ps1"),
        "-OldOid",
        old_oid,
        "-NewTipOid",
        new_oid,
        "-DryRun",
        cwd=repository,
        check=False,
    )
    assert result.returncode != 0
    assert "worktree_path_modified" in (result.stdout + result.stderr)
    assert (repository / "drop.txt").read_text(encoding="utf-8") == "changed\n"
