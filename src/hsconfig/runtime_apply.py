from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from hsconfig.io import file_sha256, read_json, write_json
from hsconfig.validate_package import SPECIAL_SURFACE_NAMES, supported_surface


def apply_package(
    *,
    package_root: str | Path,
    runtime_root: str | Path,
    config_dir: str | None = None,
    replace: bool = True,
) -> dict[str, Any]:
    package = Path(package_root)
    runtime = Path(runtime_root)
    deck_dir_name = config_dir or _single_config_dir(package)
    _validate_config_dir(deck_dir_name)
    mapped_deck_name = _deck_name_from_manifest(package, fallback=deck_dir_name)

    source_dir = package / "CustomConfig" / deck_dir_name
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Package deck config not found: {source_dir}")
    _validate_complete_source_dir(source_dir)

    target_root = runtime / "CustomConfig"
    target_dir = target_root / deck_dir_name
    target_root.mkdir(parents=True, exist_ok=True)

    replaced_existing = target_dir.exists()
    if replaced_existing and replace:
        _ensure_child_path(target_dir, target_root)
        shutil.rmtree(target_dir)
    elif replaced_existing and not replace:
        raise FileExistsError(f"Runtime deck config already exists: {target_dir}")

    shutil.copytree(source_dir, target_dir)
    deck_config_receipt = _update_deck_config_ini(
        runtime=runtime,
        deck_name=mapped_deck_name,
        config_dir=deck_dir_name,
    )
    copied_files = sorted(
        path.relative_to(source_dir).as_posix() for path in source_dir.rglob("*") if path.is_file()
    )

    receipt = {
        "status": "applied",
        "runtime_write_performed": True,
        "package_root": str(package),
        "runtime_root": str(runtime),
        "config_dir": deck_dir_name,
        "source_path": str(source_dir),
        "target_path": str(target_dir),
        "replaced_existing": replaced_existing,
        "copied_files": copied_files,
        "mapped_deck_name": mapped_deck_name,
        "deck_config_ini_path": deck_config_receipt["path"],
        "deck_config_ini_updated": deck_config_receipt["updated"],
        "deck_config_ini_previous_sha256": deck_config_receipt["previous_sha256"],
        "deck_config_ini_current_sha256": deck_config_receipt["current_sha256"],
    }
    write_json(package / "reports" / "runtime_apply_receipt.json", receipt)
    return receipt


def _deck_name_from_manifest(package_root: Path, *, fallback: str) -> str:
    manifest_path = package_root / "reports" / "input_manifest.json"
    if not manifest_path.exists():
        return fallback
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict):
        return fallback
    deck_name = str(manifest.get("deck_name") or "").strip()
    _validate_ini_key(deck_name)
    return deck_name or fallback


def _update_deck_config_ini(
    *,
    runtime: Path,
    deck_name: str,
    config_dir: str,
) -> dict[str, Any]:
    target_root = runtime / "CustomConfig"
    target_root.mkdir(parents=True, exist_ok=True)
    ini_path = target_root / "deck_config.ini"
    previous_sha = file_sha256(ini_path) if ini_path.exists() else None
    original_text = ini_path.read_text(encoding="utf-8-sig") if ini_path.exists() else ""
    original_lines = original_text.splitlines()

    if not original_lines:
        new_lines = ["[CONFIGS]", _mapping_line(deck_name, config_dir)]
    else:
        new_lines = _upsert_config_mapping(original_lines, deck_name=deck_name, config_dir=config_dir)

    new_text = "\n".join(new_lines).rstrip() + "\n"
    previous_normalized = original_text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    updated = new_text != previous_normalized
    if updated:
        ini_path.write_text(new_text, encoding="utf-8", newline="\n")

    return {
        "path": str(ini_path),
        "updated": updated,
        "previous_sha256": previous_sha,
        "current_sha256": file_sha256(ini_path),
    }


def _upsert_config_mapping(lines: list[str], *, deck_name: str, config_dir: str) -> list[str]:
    output: list[str] = []
    in_configs = False
    saw_configs = False
    mapping_written = False
    normalized_target_key = _normalize_ini_key(deck_name)

    for raw_line in lines:
        line = raw_line.lstrip("\ufeff")
        stripped = line.strip()
        lower = stripped.lower()

        if _is_section(stripped):
            if in_configs and not mapping_written:
                output.append(_mapping_line(deck_name, config_dir))
                mapping_written = True
            in_configs = lower == "[configs]"
            saw_configs = saw_configs or in_configs
            output.append("[CONFIGS]" if in_configs else line)
            continue

        if in_configs and "=" in line and not _is_comment(stripped):
            key = line.split("=", 1)[0].strip()
            if _normalize_ini_key(key) == normalized_target_key:
                if not mapping_written:
                    output.append(_mapping_line(deck_name, config_dir))
                    mapping_written = True
                continue

        output.append(line)

    if in_configs and not mapping_written:
        output.append(_mapping_line(deck_name, config_dir))
    elif not saw_configs:
        if output and output[-1].strip():
            output.append("")
        output.extend(["[CONFIGS]", _mapping_line(deck_name, config_dir)])

    return output


def _mapping_line(deck_name: str, config_dir: str) -> str:
    _validate_ini_key(deck_name)
    return f"{deck_name} = {config_dir}"


def _is_section(stripped: str) -> bool:
    return stripped.startswith("[") and stripped.endswith("]")


def _is_comment(stripped: str) -> bool:
    return stripped.startswith(";") or stripped.startswith("#")


def _normalize_ini_key(key: str) -> str:
    return key.strip().casefold()


def _validate_ini_key(key: str) -> None:
    if not key:
        return
    if any(char in key for char in "\r\n="):
        raise ValueError(f"Deck name is not safe for deck_config.ini mapping: {key!r}")


def _single_config_dir(package_root: Path) -> str:
    custom_config = package_root / "CustomConfig"
    if not custom_config.is_dir():
        raise FileNotFoundError(f"Package CustomConfig directory not found: {custom_config}")
    deck_dirs = sorted(path.name for path in custom_config.iterdir() if path.is_dir())
    if len(deck_dirs) != 1:
        raise ValueError("Expected exactly one CustomConfig deck directory.")
    return deck_dirs[0]


def _validate_config_dir(config_dir: str) -> None:
    path = Path(config_dir)
    if not config_dir or path.name != config_dir or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"Invalid config directory name: {config_dir!r}")


def _ensure_child_path(child: Path, parent: Path) -> None:
    child_resolved = child.resolve()
    parent_resolved = parent.resolve()
    if child_resolved == parent_resolved or parent_resolved not in child_resolved.parents:
        raise ValueError(f"Refusing to remove path outside runtime CustomConfig: {child}")


def _validate_complete_source_dir(source_dir: Path) -> None:
    missing = []
    if not (source_dir / "GlobalValues.json").is_file():
        missing.append("GlobalValues.json")
    if not (source_dir / "Mulligan.json").is_file():
        missing.append("Mulligan.json")
    card_files = [
        path
        for path in source_dir.glob("*.json")
        if path.name not in SPECIAL_SURFACE_NAMES and supported_surface(path.name)
    ]
    if not card_files:
        missing.append("<CardID>.json")
    if missing:
        raise ValueError(
            f"Incomplete package deck config {source_dir}: missing {', '.join(missing)}"
        )
