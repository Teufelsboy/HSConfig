from __future__ import annotations

from typing import Any


def build_report_ownership() -> list[dict[str, Any]]:
    return [
        {
            "file": "reports/operator_summary.json",
            "authority": "normal_operator_gate",
            "classification": "gate",
            "answers": "what to do next",
            "open_order": "1",
            "contains": ["config_usefulness"],
        },
        {
            "file": "reports/output_ownership_manifest.json",
            "producer": "prepare",
            "authority": "diagnostic_artifact_ownership",
            "classification": "diagnostic",
            "answers": "which generated artifact owns which responsibility",
            "open_order": "11",
            "notes": "diagnostic only; does not replace operator_summary.json",
        },
        {
            "file": "reports/source_bundle.json",
            "producer": "configure",
            "authority": "diagnostic_source_bundle",
            "classification": "diagnostic",
            "answers": "the collected source-to-runtime diagnostic chain for configure",
            "open_order": "12",
            "notes": "diagnostic only; does not replace operator_summary.json",
        },
        {
            "file": "reports/source_contract_audit.json",
            "authority": "diagnostic_source_to_runtime_explanation",
            "classification": "diagnostic",
            "answers": "why each source claim did or did not lower to runtime config",
            "contains": "claim lanes, surface gate decisions, policy lanes, first missing links",
            "notes": (
                "diagnostic only; does not grant apply permission; "
                "does not replace operator_summary.json"
            ),
            "open_order": "3",
        },
        {
            "file": "reports/source_to_runtime_explainability.json",
            "authority": "diagnostic_source_to_runtime_projection",
            "classification": "diagnostic",
            "answers": (
                "which exact source-to-runtime link is missing before a card can be stronger"
            ),
            "contains": (
                "claim rows, card rows, emitted runtime files, missing runtime files, "
                "first missing links, next source actions"
            ),
            "notes": (
                "diagnostic only; does not grant apply permission; "
                "does not replace operator_summary.json"
            ),
            "open_order": "2",
        },
        {
            "file": "reports/source_claim_gap_report.json",
            "authority": "repair_contract",
            "classification": "diagnostic",
            "answers": "which card link is missing first",
            "open_order": "4",
        },
        {
            "file": "reports/strong_promotion_report.json",
            "authority": "promotion_confirmation",
            "classification": "diagnostic",
            "answers": "whether the package can be called source-backed strong",
            "open_order": "5",
        },
        {
            "file": "reports/per_card_config_readiness_report.json",
            "authority": "card_lane_diagnostics",
            "classification": "diagnostic",
            "answers": "which lane each card occupies",
            "open_order": "6",
        },
        {
            "file": "reports/guide_source_depth_report.json",
            "authority": "source_depth_diagnostics",
            "classification": "diagnostic",
            "answers": "how strong the guide and source coverage is",
            "open_order": "7",
        },
        {
            "file": "reports/global_values_authority_matrix.json",
            "authority": "globalvalues_diagnostics",
            "classification": "diagnostic",
            "answers": "which GlobalValues keys are source-backed or archetype-inferred",
            "open_order": "8",
        },
        {
            "file": "reports/mechanic_drift_report.json",
            "producer": "prepare",
            "authority": "non_blocking_mechanic_drift_visibility",
            "classification": "mechanic_drift",
            "open_when": (
                "mechanic_drift_summary shows unknown mechanics, text-only mechanics, "
                "or unknown card types"
            ),
            "open_order": "9",
        },
        {
            "file": "reports/semantic_enrichment_report.json",
            "producer": "prepare",
            "authority": "semantic_mechanic_diagnostics",
            "classification": "diagnostic",
            "open_when": (
                "mechanic_visibility_summary or config_usefulness points to static, "
                "partial, or warning-only mechanic coverage"
            ),
            "open_order": "10",
        },
    ]
