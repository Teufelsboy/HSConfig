from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.io import file_sha256, read_json, write_json
from hsconfig.runtime_apply_receipts import (
    build_fake_apply_receipt,
    runtime_snapshot,
    verify_fake_apply_receipt,
    write_fake_apply_receipt,
    write_runtime_write_history,
)
from hsconfig.validate_package import SPECIAL_SURFACE_NAMES, supported_surface


def plan_apply_package(
    *,
    package_root: str | Path,
    runtime_root: str | Path,
    config_dir: str | None = None,
    apply_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    package = Path(package_root)
    deck_dir_name = config_dir or _single_config_dir(package)
    _validate_config_dir(deck_dir_name)
    source_dir = package / "CustomConfig" / deck_dir_name
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Package deck config not found: {source_dir}")
    _validate_complete_source_dir(source_dir)
    receipt = build_fake_apply_receipt(
        package_root=package,
        runtime_root=runtime_root,
        config_dir=deck_dir_name,
        apply_gate=apply_gate or {"status": "not_checked"},
    )
    write_fake_apply_receipt(package, receipt)
    return receipt


def apply_package(
    *,
    package_root: str | Path,
    runtime_root: str | Path,
    config_dir: str | None = None,
    replace: bool = True,
    fake_receipt: dict[str, Any] | None = None,
    apply_gate: dict[str, Any] | None = None,
    allow_source_informed: bool = False,
    write_history: bool = True,
) -> dict[str, Any]:
    package = Path(package_root)
    runtime = Path(runtime_root)
    resolved_apply_gate = _resolve_allowed_apply_gate(
        package=package,
        apply_gate=apply_gate,
        allow_source_informed=allow_source_informed,
    )
    deck_dir_name = config_dir or _single_config_dir(package)
    _validate_config_dir(deck_dir_name)
    mapped_deck_name = _deck_name_from_manifest(package, fallback=deck_dir_name)

    source_dir = package / "CustomConfig" / deck_dir_name
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Package deck config not found: {source_dir}")
    _validate_complete_source_dir(source_dir)

    if fake_receipt is not None:
        fake_verification = verify_fake_apply_receipt(
            package_root=package,
            runtime_root=runtime,
            config_dir=deck_dir_name,
            receipt=fake_receipt,
        )
    else:
        fake_receipt = plan_apply_package(
            package_root=package,
            runtime_root=runtime,
            config_dir=deck_dir_name,
            apply_gate=resolved_apply_gate,
        )
        fake_verification = verify_fake_apply_receipt(
            package_root=package,
            runtime_root=runtime,
            config_dir=deck_dir_name,
            receipt=fake_receipt,
        )

    before_snapshot = runtime_snapshot(runtime, deck_dir_name)
    target_root = runtime / "CustomConfig"
    target_dir = target_root / deck_dir_name

    replaced_existing = target_dir.exists()
    if replaced_existing and not replace:
        raise FileExistsError(f"Runtime deck config already exists: {target_dir}")

    rollback_snapshot_path = _snapshot_existing_runtime_target(
        runtime=runtime,
        config_dir=deck_dir_name,
    )
    success_history_written = False
    try:
        target_root.mkdir(parents=True, exist_ok=True)
        if replaced_existing and replace:
            _ensure_child_path(target_dir, target_root)
            shutil.rmtree(target_dir)

        shutil.copytree(source_dir, target_dir)
        deck_config_receipt = _update_deck_config_ini(
            runtime=runtime,
            deck_name=mapped_deck_name,
            config_dir=deck_dir_name,
        )
        copied_files = sorted(
            path.relative_to(source_dir).as_posix()
            for path in source_dir.rglob("*")
            if path.is_file()
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
            "fake_receipt_verified": fake_verification,
            "runtime_snapshot_before": before_snapshot,
            "runtime_snapshot_after": runtime_snapshot(runtime, deck_dir_name),
            "rollback_snapshot_path": rollback_snapshot_path,
        }
        receipt["apply_gate"] = resolved_apply_gate
        if write_history:
            history_path = write_runtime_write_history(
                runtime,
                {
                    "status": "applied",
                    "package_root": str(package),
                    "config_dir": deck_dir_name,
                    "target_path": str(target_dir),
                    "rollback_snapshot_path": rollback_snapshot_path,
                    "package_sha256": fake_verification["package_sha256"],
                },
            )
            success_history_written = True
            receipt["write_history_path"] = str(history_path)
        write_json(package / "reports" / "runtime_apply_receipt.json", receipt)
        return receipt
    except Exception as exc:
        rollback_restored = False
        try:
            _restore_runtime_target_snapshot(
                runtime=runtime,
                config_dir=deck_dir_name,
                rollback_snapshot_path=rollback_snapshot_path,
            )
            rollback_restored = True
        except Exception as restore_exc:
            exc.add_note(f"runtime rollback restore failed: {restore_exc}")
        if write_history and success_history_written:
            try:
                write_runtime_write_history(
                    runtime,
                    {
                        "status": "rolled_back",
                        "failed_status": "applied",
                        "package_root": str(package),
                        "config_dir": deck_dir_name,
                        "target_path": str(target_dir),
                        "rollback_snapshot_path": rollback_snapshot_path,
                        "rollback_restored": rollback_restored,
                        "failure_type": type(exc).__name__,
                        "failure_message": str(exc),
                    },
                )
            except Exception as history_exc:
                exc.add_note(f"runtime rollback history write failed: {history_exc}")
        raise


def _resolve_allowed_apply_gate(
    *,
    package: Path,
    apply_gate: dict[str, Any] | None,
    allow_source_informed: bool,
) -> dict[str, Any]:
    resolved = apply_gate
    if resolved is None:
        resolved = evaluate_apply_gate(
            package,
            allow_source_informed=allow_source_informed,
        )
    if not _is_allowed_gate_for_package(package=package, apply_gate=resolved):
        reason = _first_gate_reason(resolved)
        raise ValueError(
            "Runtime apply requires an allowed apply gate from "
            f"reports/operator_summary.json; got {reason}"
        )
    return resolved


def _is_allowed_gate_for_package(
    *,
    package: Path,
    apply_gate: dict[str, Any] | None,
) -> bool:
    if not isinstance(apply_gate, dict):
        return False
    if apply_gate.get("status") != "allowed":
        return False
    operator_summary_path = apply_gate.get("operator_summary_path")
    if not operator_summary_path:
        return False
    expected = package / "reports" / "operator_summary.json"
    try:
        return Path(str(operator_summary_path)).resolve() == expected.resolve()
    except OSError:
        return False


def _first_gate_reason(apply_gate: dict[str, Any] | None) -> str:
    if not isinstance(apply_gate, dict):
        return "missing_apply_gate"
    reasons = apply_gate.get("reasons")
    if isinstance(reasons, list) and reasons:
        first = reasons[0]
        if isinstance(first, dict):
            return str(first.get("reason", "blocked"))
        return str(first)
    status = apply_gate.get("status", "missing_apply_gate")
    mode = apply_gate.get("mode", "")
    return f"{status}:{mode}" if mode else str(status)


def _snapshot_existing_runtime_target(*, runtime: Path, config_dir: str) -> str | None:
    target = runtime / "CustomConfig" / config_dir
    deck_config = runtime / "CustomConfig" / "deck_config.ini"
    if not target.exists() and not deck_config.exists():
        return None
    snapshot_root = runtime / "CustomConfig" / ".hsconfig_backups"
    snapshot_root.mkdir(parents=True, exist_ok=True)
    stamp = str(time.time_ns())
    backup = snapshot_root / f"{config_dir}-{stamp}"
    backup.mkdir(parents=True, exist_ok=False)
    if target.exists():
        shutil.copytree(target, backup / config_dir)
    if deck_config.exists():
        shutil.copy2(deck_config, backup / "deck_config.ini")
    return str(backup)


def _restore_runtime_target_snapshot(
    *,
    runtime: Path,
    config_dir: str,
    rollback_snapshot_path: str | None,
) -> None:
    custom_config = runtime / "CustomConfig"
    target = custom_config / config_dir
    deck_config = custom_config / "deck_config.ini"

    if target.exists():
        _ensure_child_path(target, custom_config)
        shutil.rmtree(target)

    if rollback_snapshot_path is None:
        if deck_config.exists():
            deck_config.unlink()
        return

    backup = Path(rollback_snapshot_path)
    backup_target = backup / config_dir
    if backup_target.exists():
        custom_config.mkdir(parents=True, exist_ok=True)
        shutil.copytree(backup_target, target)

    backup_deck_config = backup / "deck_config.ini"
    if backup_deck_config.exists():
        custom_config.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_deck_config, deck_config)
    elif deck_config.exists():
        deck_config.unlink()


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
