from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from hsconfig.report_ownership import build_report_ownership


KNOWN_DIAGNOSTIC_REPORT_FILES = frozenset(
    {
        "reports/card_behavior_plan_report.json",
        "reports/card_behavior_suppression_report.json",
        "reports/card_id_map.json",
        "reports/card_semantic_audit.md",
        "reports/candidate_archetypes.json",
        "reports/claim_conflict_report.json",
        "reports/claim_coverage_report.json",
        "reports/combo_plan_report.json",
        "reports/combo_suppression_report.json",
        "reports/deck_fingerprint.json",
        "reports/deck_identity.json",
        "reports/deckstring_decode_receipt.json",
        "reports/fake_apply_receipt.json",
        "reports/gameplan_contract.json",
        "reports/global_values_blocked_changes.json",
        "reports/global_values_key_profile_report.json",
        "reports/globalvalues_baseline.json",
        "reports/globalvalues_baseline_receipt.json",
        "reports/globalvalues_profile.json",
        "reports/guide_builder_receipt.json",
        "reports/guide_claim_bundle.json",
        "reports/guide_sources.json",
        "reports/identity_gap_report.json",
        "reports/identity_graph_report.json",
        "reports/input_manifest.json",
        "reports/mulligan_plan_report.json",
        "reports/runtime_apply_receipt.json",
        "reports/semantic_enrichment_report.json",
        "reports/source_contract_audit.md",
        "reports/source_evidence_index.json",
        "reports/source_evidence_verification_report.json",
        "reports/source_bundle.json",
        "reports/surface_intent.json",
        "reports/unsupported_claims_report.json",
        "reports/validation_report.json",
    }
)
KNOWN_RESEARCH_REPORT_FILES = frozenset(
    {
        "reports/research/archetype_research.json",
        "reports/research/card_role_map.json",
        "reports/research/card_usage_expectations.json",
        "reports/research/claims.json",
        "reports/research/coverage_summary.json",
        "reports/research/globalvalue_intent.json",
        "reports/research/guide_claim_bundle.json",
        "reports/research/known_bad_patterns.json",
        "reports/research/mulligan_anchor_map.json",
    }
)
LEGACY_NON_NORMAL_SURFACES = frozenset({"Presume.json", "Concede.json"})


def build_output_ownership_manifest(generated_files: Sequence[str]) -> dict[str, Any]:
    report_rows = {row["file"]: dict(row) for row in build_report_ownership()}
    files = [
        _classify_file(str(path).replace("\\", "/"), report_rows)
        for path in sorted(set(generated_files))
    ]
    unclassified = [row for row in files if row["classification"] == "unclassified"]
    forbidden_legacy_surfaces = [
        row for row in files if row["classification"] == "forbidden_legacy_surface"
    ]
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
            "forbidden_legacy_surface_count": len(forbidden_legacy_surfaces),
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
    legacy_surface = _legacy_non_normal_surface(path)
    if legacy_surface:
        return {
            "file": path,
            "producer": "unexpected",
            "classification": "forbidden_legacy_surface",
            "authority": "normal_path_drift",
            "can_block_apply": False,
            "runtime_surface": legacy_surface,
            "diagnostic_only": True,
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
    if _known_diagnostic_report(path):
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


def _known_diagnostic_report(path: str) -> bool:
    return path in KNOWN_DIAGNOSTIC_REPORT_FILES or path in KNOWN_RESEARCH_REPORT_FILES


def _legacy_non_normal_surface(path: str) -> str | None:
    if not path.startswith("CustomConfig/") or not path.endswith(".json"):
        return None
    filename = path.rsplit("/", 1)[-1]
    if filename in LEGACY_NON_NORMAL_SURFACES:
        return "legacy_non_normal_surface"
    return None


def _runtime_surface(path: str) -> str | None:
    if not path.startswith("CustomConfig/") or not path.endswith(".json"):
        return None
    filename = path.rsplit("/", 1)[-1]
    if filename in {"GlobalValues.json", "Mulligan.json", "Combo.json"}:
        return filename
    return "CARDID.json"
