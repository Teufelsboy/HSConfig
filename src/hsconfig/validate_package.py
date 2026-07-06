from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from hsconfig.io import read_json
from hsconfig.mulligan_selector import normalize_mulligan_selector
from hsconfig.visionai_registry import (
    CARD_BEHAVIOR_BLOCKS,
    expected_game_card_id,
    supported_surface,
)


SPECIAL_SURFACE_NAMES = {
    "GlobalValues.json",
    "Mulligan.json",
    "Combo.json",
    "Presume.json",
    "Concede.json",
}


def validate_config_package(
    package_root: str | Path,
    *,
    globalvalues_baseline: dict[str, Any] | None = None,
    globalvalues_profile: dict[str, Any] | None = None,
    require_complete_package: bool = False,
    require_globalvalues_profile: bool = False,
) -> dict[str, Any]:
    root = Path(package_root)
    errors: list[str] = []
    checked_files = 0

    custom_config = root / "CustomConfig"
    if not custom_config.exists():
        return {
            "status": "failed",
            "errors": [f"{custom_config}: missing CustomConfig directory"],
            "checked_files": checked_files,
        }

    deck_dirs = sorted(path for path in custom_config.iterdir() if path.is_dir())
    if not deck_dirs:
        errors.append(f"{custom_config}: no deck config directories found")

    for deck_dir in deck_dirs:
        if require_complete_package:
            errors.extend(_validate_required_package_files(deck_dir))
        for path in sorted(item for item in deck_dir.iterdir() if item.is_file()):
            if not supported_surface(path.name):
                errors.append(f"{path}: unsupported VisionAI surface")
                continue
            checked_files += 1
            try:
                data = read_json(path)
            except Exception as exc:
                errors.append(f"{path}: invalid JSON: {exc}")
                continue
            if not isinstance(data, dict):
                errors.append(f"{path}: top-level JSON value must be an object")
                continue
            errors.extend(_validate_top_level(path, data))
            errors.extend(
                _validate_blocks(
                    path,
                    data,
                    globalvalues_baseline=globalvalues_baseline,
                    globalvalues_profile=globalvalues_profile,
                )
            )
        if require_globalvalues_profile and globalvalues_profile is None:
            errors.append(f"{deck_dir}: missing required GlobalValues profile")

    return {
        "status": "failed" if errors else "passed",
        "errors": errors,
        "checked_files": checked_files,
    }


def _validate_required_package_files(deck_dir: Path) -> list[str]:
    errors = []
    if not (deck_dir / "GlobalValues.json").is_file():
        errors.append(f"{deck_dir}: missing required runtime file GlobalValues.json")
    if not (deck_dir / "Mulligan.json").is_file():
        errors.append(f"{deck_dir}: missing required runtime file Mulligan.json")
    card_files = [
        path
        for path in deck_dir.glob("*.json")
        if path.name not in SPECIAL_SURFACE_NAMES and supported_surface(path.name)
    ]
    if not card_files:
        errors.append(f"{deck_dir}: missing at least one per-card CardID runtime file")
    return errors


def _validate_top_level(path: Path, data: dict[str, Any]) -> list[str]:
    errors = []
    expected = expected_game_card_id(path.name)
    actual = data.get("GameCardId")
    if actual is None:
        errors.append(f"{path}: missing required top-level key GameCardId")
    elif actual != expected:
        errors.append(f"{path}: GameCardId mismatch: expected {expected}, got {actual}")
    if "ConfigComment" not in data:
        errors.append(f"{path}: missing required top-level key ConfigComment")
    return errors


def _validate_blocks(
    path: Path,
    data: dict[str, Any],
    *,
    globalvalues_baseline: dict[str, Any] | None,
    globalvalues_profile: dict[str, Any] | None,
) -> list[str]:
    if path.name == "Mulligan.json":
        return _validate_mulligan(path, data)
    if path.name == "Combo.json":
        return _validate_combo(path, data)
    if path.name == "Presume.json":
        return _validate_named_values_blocks(path, data, {"PresumeOppInHandCard"})
    if path.name == "Concede.json":
        return _validate_named_values_blocks(path, data, {"ExtraConcdeSettings"})
    if path.name == "GlobalValues.json":
        return _validate_globalvalues(path, data, globalvalues_baseline, globalvalues_profile)
    if path.name in SPECIAL_SURFACE_NAMES:
        return _validate_values_blocks(path, data)
    return _validate_card_behavior_blocks(path, data)


def _validate_card_behavior_blocks(path: Path, data: dict[str, Any]) -> list[str]:
    errors = []
    for key, value in data.items():
        if key in {"GameCardId", "ConfigComment"}:
            continue
        if key not in CARD_BEHAVIOR_BLOCKS:
            errors.append(f"{path}: unsupported card behavior block {key}")
        elif not _has_values_array(value):
            errors.append(f"{path}: block {key} must contain values array")
    return errors


def _validate_values_blocks(path: Path, data: dict[str, Any]) -> list[str]:
    errors = []
    for key, value in data.items():
        if key in {"GameCardId", "ConfigComment"}:
            continue
        if not _has_values_array(value):
            errors.append(f"{path}: block {key} must contain values array")
    return errors


def _validate_mulligan(path: Path, data: dict[str, Any]) -> list[str]:
    errors = _validate_named_values_blocks(path, data, {"Mulligan"})
    block = data.get("Mulligan", {})
    values = block.get("values") if isinstance(block, dict) else []
    if not isinstance(values, list):
        values = []
    if (
        len(values) == 1
        and isinstance(values[0], dict)
        and values[0].get("mulligan") == "*"
        and values[0].get("value") == "discard"
    ):
        errors.append(f"{path}: lone_wildcard_discard")
    has_previous_non_wildcard_hold = False
    for index, row in enumerate(values):
        if not isinstance(row, dict):
            errors.append(f"{path}: Mulligan row {index} must be an object")
            continue
        selector_info: dict[str, Any] | None = None
        if not row.get("mulligan"):
            errors.append(f"{path}: Mulligan row {index} missing mulligan")
        else:
            selector_info = normalize_mulligan_selector({"selector": row.get("mulligan")})
            if not selector_info["supported"]:
                errors.append(
                    f"{path}: Mulligan row {index} unsupported_mulligan_selector "
                    f"{selector_info['selector']}"
                )
        if "condition" not in row:
            errors.append(f"{path}: Mulligan row {index} missing condition")
        if row.get("value") not in {"hold", "discard"}:
            errors.append(f"{path}: Mulligan row {index} value must be hold or discard")
        if selector_info is None or not selector_info["supported"]:
            continue
        is_wildcard = selector_info["selector_kind"] == "wildcard"
        if row.get("value") == "discard" and is_wildcard and not has_previous_non_wildcard_hold:
            errors.append(
                f"{path}: Mulligan wildcard discard appears before any non-wildcard hold"
            )
        if row.get("value") == "hold" and not is_wildcard:
            has_previous_non_wildcard_hold = True
    return errors


def _validate_globalvalues(
    path: Path,
    data: dict[str, Any],
    baseline: dict[str, Any] | None,
    profile: dict[str, Any] | None,
) -> list[str]:
    errors = _validate_values_blocks(path, data)
    if baseline is not None:
        generated_overlay_keys = set()
        if profile is not None:
            generated_overlay_keys = {str(key) for key in profile.get("generated_overlay_keys", [])}
        for key in baseline:
            if key not in data:
                errors.append(f"{path}: GlobalValues missing baseline key {key}")
        extra_keys = set(data) - set(baseline) - generated_overlay_keys
        for key in sorted(extra_keys):
            errors.append(f"{path}: GlobalValues unexpected key {key}")
    if profile is not None:
        generated_overlay_keys = {str(key) for key in profile.get("generated_overlay_keys", [])}
        expected_key_count = (
            len(baseline) + len(generated_overlay_keys) if baseline is not None else len(data)
        )
        if profile.get("key_count") != expected_key_count:
            errors.append(
                f"{path}: GlobalValues profile key_count mismatch: "
                f"expected {expected_key_count}, got {profile.get('key_count')}"
            )
        profiled_keys = set(profile.get("keys", {}))
        runtime_keys = set(data)
        missing_profiles = runtime_keys - profiled_keys
        for key in sorted(missing_profiles):
            errors.append(f"{path}: GlobalValues profile missing key {key}")
    return errors


def _validate_named_values_blocks(
    path: Path, data: dict[str, Any], allowed_blocks: set[str]
) -> list[str]:
    errors = []
    for key, value in data.items():
        if key in {"GameCardId", "ConfigComment"}:
            continue
        if key not in allowed_blocks:
            errors.append(f"{path}: unsupported block {key}; expected one of {sorted(allowed_blocks)}")
            continue
        if not _has_values_array(value):
            errors.append(f"{path}: block {key} must contain values array")
    return errors


def _validate_combo(path: Path, data: dict[str, Any]) -> list[str]:
    errors = _validate_values_blocks(path, data)
    combo_list = data.get("ComboList")
    if combo_list is not None and not _has_values_array(combo_list):
        errors.append(f"{path}: ComboList must contain values array")
        return errors
    if _has_values_array(combo_list):
        for index, row in enumerate(combo_list["values"]):
            errors.extend(_validate_combo_row(path, index, row))
    return errors


def _has_values_array(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("values"), list)


def _validate_combo_row(path: Path, index: int, row: Any) -> list[str]:
    if not isinstance(row, dict):
        return [f"{path}: ComboList row {index} must be an object"]
    allowed_keys = {"comment", "condition", "combo", "value"}
    errors = [
        f"{path}: ComboList row {index} unsupported ComboList row key {key}"
        for key in sorted(set(row) - allowed_keys)
    ]
    combo = str(row.get("combo", "")).strip()
    value = str(row.get("value", "")).strip()
    combo_segments = _split_combo_segments(combo)
    value_segments = _split_combo_segments(value)
    if len(combo_segments) < 2:
        errors.append(f"{path}: ComboList row {index} combo row must contain at least two cards")
    if len(combo_segments) != len(value_segments):
        errors.append(
            f"{path}: ComboList row {index} combo/value segment count mismatch: "
            f"{len(combo_segments)} combo segments, {len(value_segments)} value segments"
        )
    return errors


def _split_combo_segments(text: str) -> list[str]:
    if not text:
        return []
    return [part.strip() for part in re.split(r"\s*(?:>>|>->)\s*", text) if part.strip()]
