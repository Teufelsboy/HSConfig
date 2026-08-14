from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "cutover_v1.ps1"
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")
BOUNDARIES = (
    "reversible_github_preflight",
    "candidate_verification",
    "bundle_creation",
    "final_lease_check",
    "remote_main_update",
    "local_worktree_sync",
    "exact_oid_ci",
    "ruleset_activation",
    "tag_creation",
    "release_creation",
    "final_cache_cleanup",
    "canonical_final_product_gate",
    "persisted_commit_decision",
    "bundle_directory_deletion",
    "sibling_journal_deletion",
)


def _run(*argv: str, cwd: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    inherited = dict(os.environ)
    environment = {
        name: value
        for name, value in inherited.items()
        if name.upper() != "VIRTUAL_ENV"
        and not name.upper().startswith(
            ("COVERAGE_", "GITHUB_", "HSCONFIG_", "PYTEST_", "PYTHON")
        )
    }
    return subprocess.run(
        argv,
        cwd=cwd,
        env=environment,
        check=check,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _write_envelope(path: Path, payload: dict[str, object]) -> None:
    canonical = _canonical(payload)
    path.write_text(
        _canonical(
            {
                "payload": canonical,
                "payload_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
                "schema_version": 1,
            }
        ),
        encoding="utf-8",
    )


def _fixture(tmp_path: Path) -> dict[str, Path | str]:
    token = "a" * 32
    state_dir = tmp_path / f"hsconfig-cutover-{token}"
    state_dir.mkdir()
    journal = tmp_path / f"hsconfig-cutover-{token}.journal.json"
    external = tmp_path / "external-state.json"
    graph = state_dir / "curated-graph.json"
    snapshot = state_dir / "github-settings-before.json"
    old_oid = "1" * 40
    new_oid = "2" * 40
    graph.write_text(
        _canonical(
            {
                "schema_version": 1,
                "old_oid": old_oid,
                "new_tip_oid": new_oid,
                "new_tree_oid": "3" * 40,
                "commit_oids": ["4" * 40, "5" * 40, "6" * 40, new_oid],
            }
        ),
        encoding="utf-8",
    )
    snapshot.write_text(_canonical({"schema_version": 1, "rulesets": []}), encoding="utf-8")
    external.write_text(
        _canonical(
            {
                "old_oid": old_oid,
                "new_oid": new_oid,
                "remote_main": old_oid,
                "local_main": old_oid,
                "worktree_oid": old_oid,
                "github_snapshot_restored": True,
                "ruleset": None,
                "local_tag": False,
                "remote_tag": False,
                "release": False,
                "bundle": False,
                "final_gate": False,
                "calls": [],
            }
        ),
        encoding="utf-8",
    )
    adapter = tmp_path / "adapter.ps1"
    adapter.write_text(
        r'''param([string]$Operation,[string]$StatePath)
$state = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
$calls = @($state.calls) + @($Operation)
$state.calls = $calls
switch ($Operation) {
  'github-preflight' { $state.github_snapshot_restored = $false; $state.ruleset = 'inactive' }
  'candidate-verify' { }
  'bundle-create' { $state.bundle = $true }
  'lease-check' { }
  'remote-update' { $state.remote_main = $state.new_oid }
  'local-sync' { $state.local_main = $state.new_oid; $state.worktree_oid = $state.new_oid }
  'ci' { }
  'ruleset-activate' { $state.ruleset = 'active' }
  'tag-create' { $state.local_tag = $true; $state.remote_tag = $true }
  'release-create' { $state.release = $true }
  'cache-cleanup' { }
  'final-gate' { $state.final_gate = $true }
  'verify-final' { if (-not $state.final_gate) { exit 91 } }
  'delete-bundle-dir' { $state.bundle = $false }
  'delete-journal' { }
  'rollback-release-tag' { $state.release = $false; $state.local_tag = $false; $state.remote_tag = $false }
  'rollback-github' { $state.github_snapshot_restored = $true; $state.ruleset = $null }
  'rollback-remote' { $state.remote_main = $state.old_oid }
  'rollback-local' { $state.local_main = $state.old_oid; $state.worktree_oid = $state.old_oid }
  'verify-rollback' {
    if (-not $state.github_snapshot_restored -or $state.ruleset -ne $null -or $state.release -or
        $state.local_tag -or $state.remote_tag -or $state.remote_main -ne $state.old_oid -or
        $state.local_main -ne $state.old_oid -or $state.worktree_oid -ne $state.old_oid) { exit 92 }
  }
  default { exit 93 }
}
$state | ConvertTo-Json -Depth 8 -Compress | Set-Content -LiteralPath $StatePath -Encoding UTF8
''',
        encoding="utf-8",
    )
    return {
        "state_dir": state_dir,
        "journal": journal,
        "external": external,
        "graph": graph,
        "snapshot": snapshot,
        "adapter": adapter,
        "old_oid": old_oid,
        "new_oid": new_oid,
    }


def _invoke(fixture: dict[str, Path | str], *extra: str) -> subprocess.CompletedProcess[str]:
    assert POWERSHELL is not None
    arguments = [
        POWERSHELL,
        "-NoProfile",
        "-NonInteractive",
        "-File",
        str(SCRIPT),
        "-GraphStatePath",
        str(fixture["graph"]),
        "-GithubSnapshotPath",
        str(fixture["snapshot"]),
        "-JournalPath",
        str(fixture["journal"]),
        "-ExpectedOldOid",
        str(fixture["old_oid"]),
        "-NewTipOid",
        str(fixture["new_oid"]),
        "-OperationAdapterPath",
        str(fixture["adapter"]),
        "-AdapterStatePath",
        str(fixture["external"]),
    ]
    if "-PythonPath" not in extra:
        arguments.extend(("-PythonPath", sys.executable))
    arguments.extend(extra)
    return _run(*arguments, check=False)


def _failing_executable(tmp_path: Path, name: str) -> Path:
    source = tmp_path / f"{name}.cs"
    executable = tmp_path / f"{name}.exe"
    source.write_text(
        "public static class Program { public static int Main(string[] args) { return 41; } }\n",
        encoding="utf-8",
    )
    windows = Path(os.environ["SystemRoot"])
    compilers = (
        windows / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe",
        windows / "Microsoft.NET" / "Framework" / "v4.0.30319" / "csc.exe",
    )
    compiler = next(path for path in compilers if path.exists())
    completed = _run(
        str(compiler),
        "/nologo",
        "/target:exe",
        f"/out:{executable}",
        str(source),
        cwd=tmp_path,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return executable


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required")
@pytest.mark.parametrize("boundary", BOUNDARIES[:12])
def test_every_predecision_failure_rolls_back_without_retry_and_retains_verified_bundle(
    tmp_path: Path, boundary: str
) -> None:
    fixture = _fixture(tmp_path)
    result = _invoke(fixture, "-FaultAfter", boundary)
    assert result.returncode != 0
    state = json.loads(Path(fixture["external"]).read_text(encoding="utf-8-sig"))
    assert state["remote_main"] == fixture["old_oid"]
    assert state["local_main"] == fixture["old_oid"]
    assert state["worktree_oid"] == fixture["old_oid"]
    assert state["github_snapshot_restored"] is True
    assert state["ruleset"] is None
    assert state["release"] is False
    assert state["local_tag"] is False and state["remote_tag"] is False
    bundle_was_created = BOUNDARIES.index(boundary) >= BOUNDARIES.index("bundle_creation")
    assert state["bundle"] is bundle_was_created, result.stdout + result.stderr
    assert state["calls"].count("github-preflight") == 1
    assert Path(fixture["journal"]).exists()
    journal = json.loads(Path(fixture["journal"]).read_text(encoding="utf-8-sig"))
    payload = json.loads(journal["payload"])
    assert payload["decision"] == "rollback"


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required")
def test_hard_kill_before_decision_recovers_by_rollback(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    killed = _invoke(fixture, "-HardKillAfter", "canonical_final_product_gate")
    assert killed.returncode != 0
    recovered = _invoke(fixture, "-Recover")
    assert recovered.returncode != 0
    state = json.loads(Path(fixture["external"]).read_text(encoding="utf-8-sig"))
    assert state["remote_main"] == fixture["old_oid"]
    assert state["release"] is False
    assert state["bundle"] is True


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required")
@pytest.mark.parametrize(
    "boundary",
    ("persisted_commit_decision", "bundle_directory_deletion", "sibling_journal_deletion"),
)
def test_postdecision_failure_and_recovery_roll_forward_preserving_release(
    tmp_path: Path, boundary: str
) -> None:
    fixture = _fixture(tmp_path)
    failed = _invoke(fixture, "-FaultAfter", boundary)
    assert failed.returncode != 0
    recovered = _invoke(fixture, "-Recover")
    assert recovered.returncode == 0, recovered.stdout + recovered.stderr
    state = json.loads(Path(fixture["external"]).read_text(encoding="utf-8-sig"))
    assert state["remote_main"] == fixture["new_oid"]
    assert state["local_main"] == fixture["new_oid"]
    assert state["release"] is True
    assert state["local_tag"] is True and state["remote_tag"] is True
    assert state["ruleset"] == "active"
    assert state["bundle"] is False
    assert not Path(fixture["journal"]).exists()


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required")
def test_hard_kill_after_decision_recovers_by_roll_forward(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    killed = _invoke(fixture, "-HardKillAfter", "persisted_commit_decision")
    assert killed.returncode != 0
    recovered = _invoke(fixture, "-Recover")
    assert recovered.returncode == 0
    state = json.loads(Path(fixture["external"]).read_text(encoding="utf-8-sig"))
    assert state["release"] is True
    assert state["bundle"] is False


@pytest.mark.skipif(POWERSHELL is None, reason="PowerShell is required")
@pytest.mark.parametrize("native_failure", ("git", "gh", "python"))
def test_native_nonzero_enters_the_same_compensation_path(
    tmp_path: Path, native_failure: str
) -> None:
    fixture = _fixture(tmp_path)
    fake = _failing_executable(tmp_path, native_failure)
    path_parameter = {
        "git": "-GitPath",
        "gh": "-GhPath",
        "python": "-PythonPath",
    }[native_failure]
    result = _invoke(
        fixture,
        path_parameter,
        str(fake),
        "-AdapterFailCommand",
        native_failure,
    )
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    normalized = "".join(combined.split())
    expected = "".join(f"native_command_failed:{fake}:exit=41".split())
    assert expected in normalized
    state = json.loads(Path(fixture["external"]).read_text(encoding="utf-8-sig"))
    assert state["remote_main"] == fixture["old_oid"]
    assert state["github_snapshot_restored"] is True


def test_journal_loader_rejects_duplicate_keys_digest_mismatch_and_identity_mismatch(
    tmp_path: Path,
) -> None:
    module_path = ROOT / "scripts" / "github_governance.py"
    assert module_path.exists()
    fixture = _fixture(tmp_path)
    journal = Path(fixture["journal"])
    journal.write_text('{"payload":"{}","payload":"{}","payload_sha256":"x"}', encoding="utf-8")
    assert POWERSHELL is not None
    duplicate = _invoke(fixture, "-Recover")
    assert duplicate.returncode != 0
    assert "duplicate_json_key" in (duplicate.stdout + duplicate.stderr)

    payload = {
        "schema_version": 1,
        "decision": "rollback",
        "phase": "initialized",
        "old_oid": fixture["old_oid"],
        "new_oid": fixture["new_oid"],
        "state_directory": str(fixture["state_dir"]),
        "graph_sha256": "0" * 64,
        "snapshot_sha256": "0" * 64,
    }
    _write_envelope(journal, payload)
    envelope = json.loads(journal.read_text(encoding="utf-8"))
    envelope["payload_sha256"] = "f" * 64
    journal.write_text(_canonical(envelope), encoding="utf-8")
    digest = _invoke(fixture, "-Recover")
    assert digest.returncode != 0
    assert "journal_digest_mismatch" in (digest.stdout + digest.stderr)
