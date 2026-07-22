import subprocess
import sys
from pathlib import Path

from hsconfig.skill_sync_status import build_installed_skill_sync_status


SCRIPT = Path("scripts/sync_installed_skill.py")


def test_skill_sync_check_passes_when_installed_copy_matches(tmp_path: Path):
    install_root = tmp_path / "codex" / "skills"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--install-root",
            str(install_root),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    check = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--check",
            "--install-root",
            str(install_root),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert check.returncode == 0, check.stdout + check.stderr
    assert "in sync" in check.stdout.lower()


def test_skill_sync_check_fails_when_installed_copy_drifts(tmp_path: Path):
    install_root = tmp_path / "codex" / "skills"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--install-root",
            str(install_root),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    installed_skill = install_root / "hsconfig" / "SKILL.md"
    installed_skill.write_text(
        installed_skill.read_text(encoding="utf-8") + "\n# drift\n",
        encoding="utf-8",
    )

    check = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--check",
            "--install-root",
            str(install_root),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert check.returncode == 1
    assert "drift" in (check.stdout + check.stderr).lower()


def test_skill_sync_propagates_source_backed_closure_guidance(tmp_path: Path):
    install_root = tmp_path / "codex" / "skills"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--install-root",
            str(install_root),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr

    installed_root = install_root / "hsconfig"
    skill_text = (installed_root / "SKILL.md").read_text(encoding="utf-8")
    workflow_text = (installed_root / "references" / "workflow.md").read_text(
        encoding="utf-8"
    )
    policy_text = (installed_root / "references" / "guide-research-policy.md").read_text(
        encoding="utf-8"
    )

    assert "For an optimal fresh deck config, prefer:" in skill_text
    references_block = skill_text.split("## References:", 1)[1]
    assert "references/contract-compiler-checklist.md" in references_block
    assert (
        'hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" '
        '--runtime-root "<HearthRangerRoot>" --out "outputs/<DeckName>" '
        '--online-source --auto-source --apply --json'
    ) in skill_text
    assert "first_missing_source_action" in skill_text
    assert "config_intent_self_audit" in workflow_text
    assert "source_backed_strong_closure" in policy_text
    assert "no_default_only_runtime_status" in policy_text
    assert "runtime-file intent" in workflow_text


def test_skill_sync_check_explains_newline_only_drift(tmp_path: Path):
    install_root = tmp_path / "codex" / "skills"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--install-root",
            str(install_root),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    installed_skill = install_root / "hsconfig" / "SKILL.md"
    original_bytes = installed_skill.read_bytes()
    if b"\r\n" in original_bytes:
        drift_bytes = original_bytes.replace(b"\r\n", b"\n")
    elif b"\n" in original_bytes:
        drift_bytes = original_bytes.replace(b"\n", b"\r\n")
    else:
        drift_bytes = original_bytes + b"\r\n"
    assert drift_bytes != original_bytes
    installed_skill.write_bytes(drift_bytes)

    check = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--check",
            "--install-root",
            str(install_root),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    output = check.stdout + check.stderr
    assert check.returncode == 1
    assert "SKILL.md" in output
    assert "normalized text matches" in output
    assert "run without --check to re-sync" in output


def test_shared_skill_sync_status_reports_in_sync_after_script_sync(tmp_path: Path):
    install_root = tmp_path / "codex" / "skills"
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--install-root",
            str(install_root),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    status = build_installed_skill_sync_status(Path("."), install_root)

    assert status["status"] == "in_sync"
    assert status["installed_skill_present"] is True
    assert status["matches_repo_skill"] is True
    assert status["reason"] == "in_sync"
    assert status["diffs"] == []
    assert status["recommended_action"] == "none"
    assert status["diagnostic_only"] is True
    assert status["runtime_apply_authority"] == "reports/operator_summary.json"


def test_shared_skill_sync_status_reports_attention_on_drift(tmp_path: Path):
    install_root = tmp_path / "custom skill root"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--install-root",
            str(install_root),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    installed_skill = install_root / "hsconfig" / "SKILL.md"
    installed_skill.write_text(
        installed_skill.read_text(encoding="utf-8") + "\n# drift\n",
        encoding="utf-8",
    )

    status = build_installed_skill_sync_status(Path("."), install_root)

    assert status["status"] == "attention"
    assert status["installed_skill_present"] is True
    assert status["matches_repo_skill"] is False
    assert status["reason"] == "diffs_found"
    assert status["recommended_action"] == (
        'python scripts\\sync_installed_skill.py --install-root '
        f'"{install_root.resolve()}"'
    )
    assert status["diagnostic_only"] is True
    assert any(item["path"] == "SKILL.md" for item in status["diffs"])


def test_shared_skill_sync_status_reports_missing_install_folder_without_writes(
    tmp_path: Path,
):
    install_root = tmp_path / "missing skill root"

    status = build_installed_skill_sync_status(Path("."), install_root)

    assert status["status"] == "attention"
    assert status["installed_skill_present"] is False
    assert status["matches_repo_skill"] is False
    assert status["reason"] == "missing_folder"
    assert status["recommended_action"] == (
        'python scripts\\sync_installed_skill.py --install-root '
        f'"{install_root.resolve()}"'
    )
    assert status["diagnostic_only"] is True
    assert status["runtime_apply_authority"] == "reports/operator_summary.json"
    assert not install_root.exists()
    assert list(tmp_path.rglob("*")) == []
