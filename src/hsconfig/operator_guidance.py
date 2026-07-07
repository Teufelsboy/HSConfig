from __future__ import annotations

from typing import Any


def build_operator_guidance(summary: dict[str, Any]) -> dict[str, Any]:
    technical_status = str(summary.get("technical_status", ""))
    semantic_status = str(summary.get("semantic_status", ""))
    apply_policy = str(summary.get("apply_policy", ""))

    if technical_status == "INVALID_PACKAGE" or apply_policy == "BLOCKED":
        return {
            "first_report_to_open": "reports/operator_summary.json",
            "next_report_to_open": "reports/validation_report.json",
            "normal_next_step": "fix_package",
            "normal_next_command": "run hsconfig validate --package <package> --json and fix reported JSON/package errors",
            "safe_to_apply": False,
            "requires_expert_flag": False,
        }

    if semantic_status == "SOURCE_BACKED_STRONG" and apply_policy == "ALLOWED":
        return {
            "first_report_to_open": "reports/operator_summary.json",
            "next_report_to_open": None,
            "normal_next_step": "apply_or_handoff",
            "normal_next_command": "hsconfig apply --package <package> --runtime-root <runtime-root> --json",
            "safe_to_apply": True,
            "requires_expert_flag": False,
        }

    if semantic_status == "VALID_BUT_NOT_GUIDE_STRONG":
        return {
            "first_report_to_open": "reports/operator_summary.json",
            "next_report_to_open": "reports/source_claim_gap_report.json",
            "normal_next_step": "improve_sources",
            "normal_next_command": "update source_documents.json, rerun hsconfig research-deck, then rerun hsconfig prepare",
            "safe_to_apply": False,
            "requires_expert_flag": True,
        }

    return {
        "first_report_to_open": "reports/operator_summary.json",
        "next_report_to_open": "reports/guide_source_depth_report.json",
        "normal_next_step": "inspect_operator_summary",
        "normal_next_command": "read reports/operator_summary.json and follow next_action",
        "safe_to_apply": False,
        "requires_expert_flag": apply_policy == "ALLOWED_WITH_WARNINGS",
    }
