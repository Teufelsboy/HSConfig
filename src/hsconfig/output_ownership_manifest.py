from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from hsconfig.report_ownership import build_report_ownership
from hsconfig.runtime_entity_owner import partition_runtime_entity_owner_rows


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
        "reports/plan_input_diagnostics.json",
        "reports/runtime_apply_receipt.json",
        "reports/semantic_enrichment_report.json",
        "reports/source_contract_audit.md",
        "reports/source_evidence_closure.json",
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


def build_output_ownership_manifest(
    generated_files: Sequence[str],
    *,
    card_behavior_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report_rows = {row["file"]: dict(row) for row in build_report_ownership()}
    accepted_behavior_rows, owner_collisions = (
        partition_runtime_entity_owner_rows(
            row
            for row in (card_behavior_plan or {}).get("rows", [])
            if isinstance(row, dict)
        )
    )
    runtime_entity_ownership = _runtime_entity_ownership(
        accepted_behavior_rows
    )
    ownership_by_runtime_card_id = {
        row["runtime_card_id"]: row for row in runtime_entity_ownership
    }
    files = []
    for path in sorted(set(generated_files)):
        normalized_path = str(path).replace("\\", "/")
        row = _classify_file(normalized_path, report_rows)
        runtime_card_id = normalized_path.rsplit("/", 1)[-1].removesuffix(
            ".json"
        )
        ownership = ownership_by_runtime_card_id.get(runtime_card_id)
        if row["runtime_surface"] == "CARDID.json" and ownership is not None:
            row.update(
                {
                    key: ownership[key]
                    for key in (
                        "owner_kind",
                        "source_card_id",
                        "runtime_card_id",
                        "link_kind",
                    )
                }
            )
        files.append(row)
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
        "runtime_entity_ownership": runtime_entity_ownership,
        "runtime_entity_owner_collisions": owner_collisions,
    }


def _runtime_entity_ownership(
    behavior_rows: Sequence[dict[str, Any]],
) -> list[dict[str, str]]:
    rows: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in behavior_rows:
        source_card_id = str(row.get("source_card_id") or row.get("card_id") or "")
        runtime_card_id = str(row.get("runtime_card_id") or row.get("card_id") or "")
        link_kind = str(row.get("link_kind") or "self")
        if (
            row.get("meaningful_runtime_surface") is not True
            or not source_card_id
            or not runtime_card_id
            or source_card_id == runtime_card_id
            or link_kind == "self"
        ):
            continue
        key = (source_card_id, runtime_card_id, link_kind)
        rows[key] = {
            "path": f"CardID/{runtime_card_id}.json",
            "owner_kind": "linked_runtime_entity",
            "source_card_id": source_card_id,
            "runtime_card_id": runtime_card_id,
            "link_kind": link_kind,
        }
    return [rows[key] for key in sorted(rows)]


def _classify_file(path: str, report_rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if path == "package_derivation_receipt.json":
        return {
            "file": path,
            "producer": "prepare",
            "classification": "integrity_receipt",
            "authority": "package_derivation_receipt",
            "can_block_apply": True,
            "runtime_surface": None,
            "diagnostic_only": False,
        }
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
