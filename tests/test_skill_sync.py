import subprocess
import sys
from pathlib import Path


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
    policy_text = (installed_root / "references" / "guide-research-policy.md").read_text(
        encoding="utf-8"
    )

    assert "For an optimal fresh deck config, prefer the source-backed path:" in skill_text
    reference_line = next(
        line for line in skill_text.splitlines() if line.startswith("## References:")
    )
    assert "references/contract-compiler-checklist.md" in reference_line
    assert (
        'hsconfig configure --deck-name "<DeckName>" --deck-code "<DeckCode>" '
        '--online-source --auto-source --apply'
    ) in skill_text
    assert "first_missing_source_action" in skill_text
    assert "source_backed_strong_closure" in policy_text
    assert "no_default_only_runtime_status" in policy_text


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
