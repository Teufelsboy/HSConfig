from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from hsconfig.io import file_sha256, write_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _iter_package_files(package_root: Path) -> list[Path]:
    receipt_path = Path("reports") / "runtime_apply_fake_receipt.json"
    return sorted(
        path
        for path in package_root.rglob("*")
        if path.is_file() and path.relative_to(package_root) != receipt_path
    )


def package_fingerprint(package_root: str | Path) -> dict[str, Any]:
    package = Path(package_root)
    file_rows: list[dict[str, str]] = []
    digest = sha256()
    for path in _iter_package_files(package):
        rel = path.relative_to(package).as_posix()
        path_hash = file_sha256(path)
        file_rows.append({"path": rel, "sha256": path_hash})
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path_hash.encode("ascii"))
        digest.update(b"\0")
    return {
        "package_root": str(package),
        "package_sha256": digest.hexdigest(),
        "file_count": len(file_rows),
        "files": file_rows,
    }


def runtime_snapshot(runtime_root: str | Path, config_dir: str) -> dict[str, Any]:
    runtime = Path(runtime_root)
    custom_config = runtime / "CustomConfig"
    target = custom_config / config_dir
    deck_config = custom_config / "deck_config.ini"
    target_files = (
        sorted(path for path in target.rglob("*") if path.is_file())
        if target.exists()
        else []
    )
    return {
        "runtime_root": str(runtime),
        "config_dir": config_dir,
        "target_path": str(target),
        "target_exists": target.exists(),
        "target_file_count": len(target_files),
        "target_files": [
            {"path": path.relative_to(target).as_posix(), "sha256": file_sha256(path)}
            for path in target_files
        ],
        "deck_config_ini_path": str(deck_config),
        "deck_config_ini_exists": deck_config.exists(),
        "deck_config_ini_sha256": file_sha256(deck_config) if deck_config.exists() else None,
    }


def build_fake_apply_receipt(
    *,
    package_root: str | Path,
    runtime_root: str | Path,
    config_dir: str,
    apply_gate: dict[str, Any],
) -> dict[str, Any]:
    package = Path(package_root)
    runtime = Path(runtime_root)
    fingerprint = package_fingerprint(package)
    before = runtime_snapshot(runtime, config_dir)
    return {
        "schema_version": 1,
        "status": "fake_apply_ready",
        "created_at_utc": _utc_now(),
        "runtime_write_performed": False,
        "package_root": str(package),
        "runtime_root": str(runtime),
        "config_dir": config_dir,
        "package_fingerprint": fingerprint,
        "runtime_snapshot_before": before,
        "apply_gate": apply_gate,
    }


def write_fake_apply_receipt(package_root: str | Path, receipt: dict[str, Any]) -> Path:
    path = Path(package_root) / "reports" / "runtime_apply_fake_receipt.json"
    write_json(path, receipt)
    return path


def verify_fake_apply_receipt(
    *,
    package_root: str | Path,
    runtime_root: str | Path,
    config_dir: str,
    receipt: dict[str, Any],
) -> dict[str, Any]:
    package = Path(package_root)
    runtime = Path(runtime_root)
    if receipt.get("status") != "fake_apply_ready":
        raise ValueError("fake apply receipt is not ready")
    if str(package) != str(Path(str(receipt.get("package_root", "")))):
        raise ValueError("fake apply receipt package path does not match package")
    if str(runtime) != str(Path(str(receipt.get("runtime_root", "")))):
        raise ValueError("fake apply receipt runtime path does not match runtime")
    if receipt.get("config_dir") != config_dir:
        raise ValueError("fake apply receipt config_dir does not match request")
    current = package_fingerprint(package)
    expected = receipt.get("package_fingerprint", {})
    if current.get("package_sha256") != expected.get("package_sha256"):
        raise ValueError("fake apply receipt does not match package")
    expected_runtime = receipt.get("runtime_snapshot_before")
    if not isinstance(expected_runtime, dict):
        raise ValueError("fake apply receipt does not include runtime snapshot")
    current_runtime = runtime_snapshot(runtime, config_dir)
    if _runtime_snapshot_contract(current_runtime) != _runtime_snapshot_contract(
        expected_runtime
    ):
        raise ValueError("fake apply receipt does not match runtime")
    return {
        "status": "verified",
        "package_sha256": current["package_sha256"],
        "config_dir": config_dir,
    }


def write_runtime_write_history(runtime_root: str | Path, entry: dict[str, Any]) -> Path:
    path = Path(runtime_root) / "CustomConfig" / "hsconfig_write_history.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"created_at_utc": _utc_now(), **entry}
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
    return path


def _runtime_snapshot_contract(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "target_exists": snapshot.get("target_exists"),
        "target_file_count": snapshot.get("target_file_count"),
        "target_files": snapshot.get("target_files"),
        "deck_config_ini_exists": snapshot.get("deck_config_ini_exists"),
        "deck_config_ini_sha256": snapshot.get("deck_config_ini_sha256"),
    }
