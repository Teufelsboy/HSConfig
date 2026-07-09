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


TEXT_LIKE_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".toml"}


def _normalized_text_equal(left_bytes: bytes, right_bytes: bytes) -> bool:
    return left_bytes.replace(b"\r\n", b"\n") == right_bytes.replace(b"\r\n", b"\n")


def folder_diff(left: Path, right: Path) -> dict[str, object]:
    if not left.exists() or not right.exists():
        return {
            "matches": False,
            "reason": "missing_folder",
            "left_exists": left.exists(),
            "right_exists": right.exists(),
            "diffs": [],
        }

    left_files = _iter_files(left)
    right_files = _iter_files(right)
    diffs: list[dict[str, object]] = []
    if left_files != right_files:
        left_set = set(left_files)
        right_set = set(right_files)
        for rel in sorted(left_set - right_set):
            diffs.append({"path": rel.as_posix(), "kind": "missing_installed_file"})
        for rel in sorted(right_set - left_set):
            diffs.append({"path": rel.as_posix(), "kind": "unexpected_installed_file"})

    for rel in left_files:
        if rel not in right_files:
            continue
        left_bytes = (left / rel).read_bytes()
        right_bytes = (right / rel).read_bytes()
        if left_bytes == right_bytes:
            continue
        entry: dict[str, object] = {"path": rel.as_posix(), "kind": "bytes_differ"}
        if rel.suffix.lower() in TEXT_LIKE_SUFFIXES:
            entry["normalized_text_equal"] = _normalized_text_equal(left_bytes, right_bytes)
        diffs.append(entry)

    return {"matches": not diffs, "reason": "diffs_found" if diffs else "in_sync", "diffs": diffs}


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
