from __future__ import annotations

from typing import Any


def build_report_ownership() -> list[dict[str, Any]]:
    return [
        {
            "file": "reports/operator_summary.json",
            "authority": "normal_operator_gate",
            "answers": "what to do next",
            "open_order": "1",
            "contains": ["config_usefulness"],
        },
        {
            "file": "reports/source_claim_gap_report.json",
            "authority": "repair_contract",
            "answers": "which card link is missing first",
            "open_order": "2",
        },
        {
            "file": "reports/strong_promotion_report.json",
            "authority": "promotion_confirmation",
            "answers": "whether the package can be called source-backed strong",
            "open_order": "3",
        },
        {
            "file": "reports/per_card_config_readiness_report.json",
            "authority": "card_lane_diagnostics",
            "answers": "which lane each card occupies",
            "open_order": "4",
        },
        {
            "file": "reports/guide_source_depth_report.json",
            "authority": "source_depth_diagnostics",
            "answers": "how strong the guide and source coverage is",
            "open_order": "5",
        },
        {
            "file": "reports/global_values_authority_matrix.json",
            "authority": "globalvalues_diagnostics",
            "answers": "which GlobalValues keys are source-backed or archetype-inferred",
            "open_order": "6",
        },
        {
            "file": "reports/mechanic_drift_report.json",
            "producer": "prepare",
            "authority": "non_blocking_mechanic_drift_visibility",
            "open_when": (
                "mechanic_drift_summary shows unknown mechanics, text-only mechanics, "
                "or unknown card types"
            ),
            "open_order": "7",
        },
    ]
