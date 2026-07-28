from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.io import file_sha256, write_json
from hsconfig.runtime_apply_receipts import (
    build_failed_apply_payload,
    build_fake_apply_receipt,
    runtime_snapshot,
    verify_fake_apply_receipt,
    write_fake_apply_receipt,
    write_runtime_write_history,
)
from hsconfig.runtime_package_match import (
    _deck_name_from_manifest,
    assert_runtime_matches_package,
)
from hsconfig.strict_package_validation import (
    LINKED_RUNTIME_OWNER_EVIDENCE_INVALID,
    LINKED_RUNTIME_OWNER_EVIDENCE_MISSING,
    strict_validation_passed,
    validate_complete_package,
)


def plan_apply_package(
    *,
    package_root: str | Path,
    runtime_root: str | Path,
    config_dir: str | None = None,
    apply_gate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    package = Path(package_root)
    _validate_runtime_apply_package(package)
    resolved_apply_gate = _resolve_allowed_apply_gate(
        package=package,
        apply_gate=apply_gate,
        allow_source_informed=False,
    )
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
        apply_gate=resolved_apply_gate,
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
    _validate_runtime_apply_package(package)
    resolved_apply_gate = _resolve_allowed_apply_gate(
        package=package,
        apply_gate=apply_gate,
        allow_source_informed=allow_source_informed,
    )
    deck_dir_name = config_dir or _single_config_dir(package)
    _validate_config_dir(deck_dir_name)
    mapped_deck_name = _deck_name_from_manifest(package)

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

    rollback_snapshot_path: str | None = None
    mutation_started = False
    runtime_target_mutation_started = False
    try:
        mutation_started = True
        rollback_snapshot_path = _snapshot_existing_runtime_target(
            runtime=runtime,
            config_dir=deck_dir_name,
        )
        runtime_target_mutation_started = True
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
        runtime_package_match = assert_runtime_matches_package(
            package_root=package,
            runtime_root=runtime,
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
            "runtime_package_match": runtime_package_match,
            "runtime_package_match_status": runtime_package_match["status"],
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
            receipt["write_history_path"] = str(history_path)
        write_json(package / "reports" / "runtime_apply_receipt.json", receipt)
        return receipt
    except Exception as exc:
        if not mutation_started:
            raise
        rollback_restored = not runtime_target_mutation_started
        if runtime_target_mutation_started:
            try:
                _restore_runtime_target_snapshot(
                    runtime=runtime,
                    config_dir=deck_dir_name,
                    rollback_snapshot_path=rollback_snapshot_path,
                    runtime_snapshot_before=before_snapshot,
                )
                rollback_restored = True
            except Exception as restore_exc:
                exc.add_note(f"runtime rollback restore failed: {restore_exc}")

        try:
            after_rollback_snapshot = runtime_snapshot(runtime, deck_dir_name)
        except Exception as snapshot_exc:
            after_rollback_snapshot = {}
            exc.add_note(
                "runtime snapshot after rollback failed: "
                f"{snapshot_exc}"
            )

        try:
            failure_payload = build_failed_apply_payload(
                package_root=package,
                runtime_root=runtime,
                config_dir=deck_dir_name,
                target_path=target_dir,
                rollback_snapshot_path=rollback_snapshot_path,
                rollback_restored=rollback_restored,
                failure=exc,
                runtime_snapshot_before=before_snapshot,
                runtime_snapshot_after_rollback=after_rollback_snapshot,
            )
        except Exception as payload_exc:
            exc.add_note(
                "runtime apply failure payload build failed: "
                f"{payload_exc}"
            )
            failure_payload = {
                "schema_version": 1,
                "status": (
                    "rolled_back" if rollback_restored else "rollback_failed"
                ),
                "runtime_write_performed": True,
                "rollback_restored": rollback_restored,
                "failure_type": type(exc).__name__,
                "failure_message": str(exc),
                "runtime_snapshot_before": before_snapshot,
                "runtime_snapshot_after_rollback": after_rollback_snapshot,
            }
        try:
            write_json(
                package / "reports" / "runtime_apply_receipt.json",
                failure_payload,
            )
        except Exception as receipt_exc:
            exc.add_note(
                "runtime apply failure receipt write failed: "
                f"{receipt_exc}"
            )
        try:
            write_runtime_write_history(runtime, failure_payload)
        except Exception as history_exc:
            exc.add_note(f"runtime rollback history write failed: {history_exc}")
        raise


def _validate_runtime_apply_package(package: Path) -> None:
    try:
        report = validate_complete_package(package)
    except ValueError as exc:
        raise ValueError(
            "Runtime apply requires a valid complete package before fake/apply "
            f"receipt or runtime writes: {exc}"
        ) from exc

    if strict_validation_passed(report):
        return
    errors = report.get("errors") or ["unknown package validation failure"]
    first_error = next(
        (
            code
            for code in (
                LINKED_RUNTIME_OWNER_EVIDENCE_MISSING,
                LINKED_RUNTIME_OWNER_EVIDENCE_INVALID,
            )
            if code in errors
        ),
        str(errors[0]),
    )
    extra_count = max(len(errors) - 1, 0)
    suffix = f" (and {extra_count} more)" if extra_count else ""
    raise ValueError(
        "Runtime apply requires a valid complete package before fake/apply "
        f"receipt or runtime writes: {first_error}{suffix}"
    )


def _resolve_allowed_apply_gate(
    *,
    package: Path,
    apply_gate: dict[str, Any] | None,
    allow_source_informed: bool,
) -> dict[str, Any]:
    # Legacy CLI compatibility; no second apply path.
    del allow_source_informed
    evaluated = evaluate_apply_gate(package)
    if apply_gate is not None and apply_gate != evaluated:
        reason = _first_gate_reason(evaluated)
        raise ValueError(
            "Runtime apply requires an allowed apply gate from "
            f"reports/operator_summary.json; got apply_gate_mismatch:{reason}"
        )
    if not _is_allowed_gate_for_package(package=package, apply_gate=evaluated):
        reason = _first_gate_reason(evaluated)
        raise ValueError(
            "Runtime apply requires an allowed apply gate from "
            f"reports/operator_summary.json; got {reason}"
        )
    return evaluated


def _is_allowed_gate_for_package(
    *,
    package: Path,
    apply_gate: dict[str, Any] | None,
) -> bool:
    if not isinstance(apply_gate, dict):
        return False
    if apply_gate.get("allowed") is not True:
        return False
    if apply_gate.get("mode") != "load_safe_apply":
        return False
    if apply_gate.get("policy") not in {"ALLOWED", "ALLOWED_WITH_WARNINGS"}:
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
    runtime_snapshot_before: dict[str, Any],
) -> None:
    custom_config = runtime / "CustomConfig"
    target = custom_config / config_dir
    deck_config = custom_config / "deck_config.ini"
    backup = Path(rollback_snapshot_path) if rollback_snapshot_path else None
    backup_target = backup / config_dir if backup is not None else None
    backup_deck_config = backup / "deck_config.ini" if backup is not None else None

    _preflight_rollback_material(
        backup_target=backup_target,
        backup_deck_config=backup_deck_config,
        runtime_snapshot_before=runtime_snapshot_before,
    )

    if target.exists():
        _ensure_child_path(target, custom_config)
        shutil.rmtree(target)

    if backup_target is not None and backup_target.exists():
        custom_config.mkdir(parents=True, exist_ok=True)
        shutil.copytree(backup_target, target)

    if backup_deck_config is not None and backup_deck_config.exists():
        custom_config.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_deck_config, deck_config)
    elif deck_config.exists():
        deck_config.unlink()

    after_restore = runtime_snapshot(runtime, config_dir)
    if _runtime_restore_identity(after_restore) != _runtime_restore_identity(
        runtime_snapshot_before
    ):
        raise RuntimeError(
            "runtime rollback verification failed: restored target/INI "
            "does not match runtime_snapshot_before"
        )


def _preflight_rollback_material(
    *,
    backup_target: Path | None,
    backup_deck_config: Path | None,
    runtime_snapshot_before: dict[str, Any],
) -> None:
    expected = _runtime_restore_identity(runtime_snapshot_before)
    problems: list[str] = []

    target_exists = backup_target is not None and backup_target.is_dir()
    if target_exists != expected["target_exists"]:
        problems.append("target backup existence does not match before snapshot")
    elif target_exists:
        target_files = sorted(
            path for path in backup_target.rglob("*") if path.is_file()
        )
        backup_target_identity = {
            "target_file_count": len(target_files),
            "target_files": [
                {
                    "path": path.relative_to(backup_target).as_posix(),
                    "sha256": file_sha256(path),
                }
                for path in target_files
            ],
        }
        if backup_target_identity != {
            "target_file_count": expected["target_file_count"],
            "target_files": expected["target_files"],
        }:
            problems.append("target backup hashes do not match before snapshot")

    deck_config_exists = (
        backup_deck_config is not None and backup_deck_config.is_file()
    )
    if deck_config_exists != expected["deck_config_ini_exists"]:
        problems.append(
            "deck_config.ini backup existence does not match before snapshot"
        )
    elif (
        deck_config_exists
        and file_sha256(backup_deck_config)
        != expected["deck_config_ini_sha256"]
    ):
        problems.append(
            "deck_config.ini backup hash does not match before snapshot"
        )

    if problems:
        raise RuntimeError(
            "runtime rollback backup validation failed: "
            + "; ".join(problems)
        )


def _runtime_restore_identity(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_exists": snapshot.get("target_exists"),
        "target_file_count": snapshot.get("target_file_count"),
        "target_files": snapshot.get("target_files"),
        "deck_config_ini_exists": snapshot.get("deck_config_ini_exists"),
        "deck_config_ini_sha256": snapshot.get("deck_config_ini_sha256"),
    }


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
    if missing:
        raise ValueError(
            f"Incomplete package deck config {source_dir}: missing {', '.join(missing)}"
        )
