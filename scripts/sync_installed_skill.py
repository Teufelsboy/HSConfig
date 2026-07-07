from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_SKILL = REPO_ROOT / ".agents" / "skills" / "hsconfig"
DEFAULT_INSTALL_ROOT = Path.home() / ".codex" / "skills"


def _iter_files(root: Path) -> list[Path]:
    return sorted(path.relative_to(root) for path in root.rglob("*") if path.is_file())


def folders_match(left: Path, right: Path) -> bool:
    if not left.exists() or not right.exists():
        return False

    left_files = _iter_files(left)
    right_files = _iter_files(right)
    if left_files != right_files:
        return False

    return all((left / rel).read_bytes() == (right / rel).read_bytes() for rel in left_files)


def sync_skill(install_root: Path) -> Path:
    target = install_root / "hsconfig"
    install_root.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    shutil.copytree(SOURCE_SKILL, target)
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync the repo hsconfig skill into the local Codex skill directory."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only check whether the installed skill matches the repo copy.",
    )
    parser.add_argument(
        "--install-root",
        type=Path,
        default=DEFAULT_INSTALL_ROOT,
        help="Root directory that contains installed skills.",
    )
    args = parser.parse_args(argv)

    if not SOURCE_SKILL.exists():
        print(f"Source skill folder not found: {SOURCE_SKILL}", file=sys.stderr)
        return 1

    target = args.install_root / "hsconfig"
    if args.check:
        if folders_match(SOURCE_SKILL, target):
            print(f"HSConfig skill is in sync: {target}")
            return 0
        print(f"HSConfig skill drift detected: {target}", file=sys.stderr)
        return 1

    synced = sync_skill(args.install_root)
    print(f"Synced HSConfig skill to {synced}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
