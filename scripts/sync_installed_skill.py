from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

# Repository-local src bootstrap must precede this import.
from hsconfig.skill_sync_status import DEFAULT_INSTALL_ROOT, folder_diff  # noqa: E402


SOURCE_SKILL = REPO_ROOT / ".agents" / "skills" / "hsconfig"


def folders_match(left: Path, right: Path) -> bool:
    return bool(folder_diff(left, right).get("matches"))


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
        diff = folder_diff(SOURCE_SKILL, target)
        if diff["matches"]:
            print(f"HSConfig skill is in sync: {target}")
            return 0
        print(f"HSConfig skill drift detected: {target}", file=sys.stderr)
        for item in list(diff.get("diffs", []))[:10]:
            if not isinstance(item, dict):
                continue
            detail = f"- {item.get('path')}: {item.get('kind')}"
            if item.get("normalized_text_equal") is True:
                detail += " (normalized text matches; run without --check to re-sync exact bytes)"
            print(detail, file=sys.stderr)
        return 1

    synced = sync_skill(args.install_root)
    print(f"Synced HSConfig skill to {synced}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
