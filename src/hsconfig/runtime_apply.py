from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from hsconfig.io import write_json
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
    }
    write_json(package / "reports" / "runtime_apply_receipt.json", receipt)
    return receipt


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
