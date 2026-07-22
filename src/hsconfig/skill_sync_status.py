from __future__ import annotations

from pathlib import Path


DEFAULT_INSTALL_ROOT = Path.home() / ".codex" / "skills"
TEXT_LIKE_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".toml"}


def _iter_files(root: Path) -> list[Path]:
    return sorted(path.relative_to(root) for path in root.rglob("*") if path.is_file())


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
            entry["normalized_text_equal"] = _normalized_text_equal(
                left_bytes, right_bytes
            )
        diffs.append(entry)

    return {
        "matches": not diffs,
        "reason": "diffs_found" if diffs else "in_sync",
        "diffs": diffs,
    }


def build_installed_skill_sync_status(
    repo_root: str | Path,
    install_root: str | Path | None = None,
) -> dict[str, object]:
    root = Path(repo_root).resolve()
    source_skill = root / ".agents" / "skills" / "hsconfig"
    resolved_install_root = (
        Path(install_root).expanduser() if install_root else DEFAULT_INSTALL_ROOT
    )
    installed_skill = resolved_install_root / "hsconfig"
    diff = folder_diff(source_skill, installed_skill)
    matches = bool(diff.get("matches"))

    return {
        "status": "in_sync" if matches else "attention",
        "source_skill_path": str(source_skill),
        "installed_skill_path": str(installed_skill),
        "installed_skill_present": installed_skill.exists(),
        "matches_repo_skill": matches,
        "reason": str(diff.get("reason") or "unknown"),
        "diffs": list(diff.get("diffs", [])),
        "recommended_action": "none"
        if matches
        else "python scripts\\sync_installed_skill.py",
        "diagnostic_only": True,
        "runtime_apply_authority": "reports/operator_summary.json",
    }
