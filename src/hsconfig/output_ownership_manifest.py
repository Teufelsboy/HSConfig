from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from hsconfig.report_ownership import build_report_ownership


def build_output_ownership_manifest(generated_files: Sequence[str]) -> dict[str, Any]:
    report_rows = {row["file"]: dict(row) for row in build_report_ownership()}
    files = [
        _classify_file(str(path).replace("\\", "/"), report_rows)
        for path in sorted(set(generated_files))
    ]
    unclassified = [row for row in files if row["classification"] == "unclassified"]
    gates = [row for row in files if row["classification"] == "gate"]
    return {
        "schema_version": 1,
        "authority": "diagnostic_manifest",
        "operator_gate": "reports/operator_summary.json",
        "summary": {
            "generated_file_count": len(files),
            "unclassified_file_count": len(unclassified),
            "gate_count": len(gates),
            "runtime_surface_count": sum(1 for row in files if row["runtime_surface"]),
        },
        "files": files,
    }


def _classify_file(path: str, report_rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if path in report_rows:
        row = dict(report_rows[path])
        return {
            "file": path,
            "producer": row.get("producer", "prepare"),
            "classification": row.get("classification", "diagnostic"),
            "authority": row.get("authority", "diagnostic"),
            "can_block_apply": row.get("classification") == "gate",
            "runtime_surface": None,
            "diagnostic_only": row.get("classification") != "gate",
        }
    runtime_surface = _runtime_surface(path)
    if runtime_surface:
        return {
            "file": path,
            "producer": "prepare",
            "classification": "runtime_surface",
            "authority": "operator_summary_listed_runtime_file",
            "can_block_apply": False,
            "runtime_surface": runtime_surface,
            "diagnostic_only": False,
        }
    if path.startswith("reports/"):
        return {
            "file": path,
            "producer": "prepare",
            "classification": "diagnostic",
            "authority": "diagnostic_artifact",
            "can_block_apply": False,
            "runtime_surface": None,
            "diagnostic_only": True,
        }
    return {
        "file": path,
        "producer": "unknown",
        "classification": "unclassified",
        "authority": "unknown",
        "can_block_apply": False,
        "runtime_surface": None,
        "diagnostic_only": True,
    }


def _runtime_surface(path: str) -> str | None:
    if not path.startswith("CustomConfig/") or not path.endswith(".json"):
        return None
    filename = path.rsplit("/", 1)[-1]
    if filename in {"GlobalValues.json", "Mulligan.json", "Combo.json"}:
        return filename
    if filename in {"Presume.json", "Concede.json"}:
        return "legacy_non_normal_surface"
    return "CARDID.json"
