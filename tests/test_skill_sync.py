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
