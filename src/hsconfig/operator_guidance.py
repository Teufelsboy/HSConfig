from __future__ import annotations

from typing import Any


SOURCE_INFORMED_EXPERT_STATUSES = {"VALID_BUT_NOT_GUIDE_STRONG", "STATIC_SEMANTICS_USABLE"}


def build_operator_guidance(summary: dict[str, Any]) -> dict[str, Any]:
    technical_status = str(summary.get("technical_status", ""))
    semantic_status = str(summary.get("semantic_status", ""))
    apply_policy = str(summary.get("apply_policy", ""))

    if (
        technical_status == "VALID_PACKAGE"
        and apply_policy == "BLOCKED"
        and str(summary.get("runtime_apply_reason", ""))
        == "diagnostic_source_not_apply_eligible"
    ):
        return {
            "first_report_to_open": "reports/operator_summary.json",
            "next_report_to_open": "reports/guide_source_depth_report.json",
            "normal_next_step": "acquire_live_verified_source",
            "normal_next_command": (
                "acquire live_verified exact-deck source and rebuild the package"
            ),
            "safe_to_apply": False,
            "requires_expert_flag": False,
            **_config_usefulness_fields(summary),
            **_mechanic_warning_fields(summary),
            **_mechanic_visibility_fields(summary),
            **_mechanic_drift_fields(summary),
            **_runtime_apply_fields(summary),
            **_configuration_assurance_fields(summary),
            **_source_informed_scope_fields(summary),
        }

    if technical_status == "INVALID_PACKAGE" or apply_policy == "BLOCKED":
        return {
            "first_report_to_open": "reports/operator_summary.json",
            "next_report_to_open": "reports/validation_report.json",
            "normal_next_step": "fix_package",
            "normal_next_command": "run hsconfig validate --package <package> --json and fix reported JSON/package errors",
            "safe_to_apply": False,
            "requires_expert_flag": False,
            **_mechanic_warning_fields(summary),
            **_mechanic_visibility_fields(summary),
            **_mechanic_drift_fields(summary),
            **_runtime_apply_fields(summary),
            **_configuration_assurance_fields(summary),
            **_source_informed_scope_fields(summary),
        }

    if bool(summary.get("runtime_apply_allowed")) and str(
        summary.get("runtime_apply_mode", "")
    ) == "load_safe_apply":
        if semantic_status == "SOURCE_BACKED_STRONG" and apply_policy == "ALLOWED":
            return {
                "first_report_to_open": "reports/operator_summary.json",
                "next_report_to_open": None,
                "normal_next_step": "apply_or_handoff",
                "normal_next_command": "hsconfig apply --package <package> --runtime-root <runtime-root> --json",
                "safe_to_apply": True,
                "requires_expert_flag": False,
                **_config_usefulness_fields(summary),
                **_mechanic_warning_fields(summary),
                **_mechanic_visibility_fields(summary),
                **_mechanic_drift_fields(summary),
                **_runtime_apply_fields(summary),
                **_configuration_assurance_fields(summary),
                **_source_informed_scope_fields(summary),
            }
        return {
            "first_report_to_open": "reports/operator_summary.json",
            "next_report_to_open": _first_semantic_blocker_report(summary)
            or "reports/source_claim_gap_report.json",
            "normal_next_step": "apply_with_warnings",
            "normal_next_command": "hsconfig apply --package <package> --runtime-root <runtime-root> --json",
            "safe_to_apply": True,
            "requires_expert_flag": False,
            **_config_usefulness_fields(summary),
            **_mechanic_warning_fields(summary),
            **_mechanic_visibility_fields(summary),
            **_mechanic_drift_fields(summary),
            **_runtime_apply_fields(summary),
            **_configuration_assurance_fields(summary),
            **_source_informed_scope_fields(summary),
        }

    if semantic_status == "SOURCE_BACKED_STRONG" and apply_policy == "ALLOWED":
        return {
            "first_report_to_open": "reports/operator_summary.json",
            "next_report_to_open": None,
            "normal_next_step": "apply_or_handoff",
            "normal_next_command": "hsconfig apply --package <package> --runtime-root <runtime-root> --json",
            "safe_to_apply": True,
            "requires_expert_flag": False,
            **_config_usefulness_fields(summary),
            **_mechanic_warning_fields(summary),
            **_mechanic_visibility_fields(summary),
            **_mechanic_drift_fields(summary),
            **_runtime_apply_fields(summary),
            **_configuration_assurance_fields(summary),
            **_source_informed_scope_fields(summary),
        }

    return {
        "first_report_to_open": "reports/operator_summary.json",
        "next_report_to_open": "reports/guide_source_depth_report.json",
        "normal_next_step": "inspect_operator_summary",
        "normal_next_command": "read reports/operator_summary.json and follow next_action",
        "safe_to_apply": False,
        "requires_expert_flag": _requires_expert_flag(semantic_status, apply_policy),
        **_config_usefulness_fields(summary),
        **_mechanic_warning_fields(summary),
        **_mechanic_visibility_fields(summary),
        **_mechanic_drift_fields(summary),
        **_runtime_apply_fields(summary),
        **_configuration_assurance_fields(summary),
        **_source_informed_scope_fields(summary),
    }


def _config_usefulness_fields(summary: dict[str, Any]) -> dict[str, str]:
    return {
        "config_usefulness_status": str(
            summary.get("config_usefulness", {}).get("status", "unknown")
        ),
        "config_usefulness_next_report": str(
            summary.get("config_usefulness", {}).get(
                "next_report_to_open",
                "reports/operator_summary.json",
            )
        ),
    }


def _runtime_apply_fields(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "runtime_apply_mode": summary.get("runtime_apply_mode", "blocked"),
        "runtime_apply_allowed": bool(summary.get("runtime_apply_allowed", False)),
        "runtime_apply_requires_flag": summary.get("runtime_apply_requires_flag"),
    }


def _configuration_assurance_fields(summary: dict[str, Any]) -> dict[str, Any]:
    assurance = summary.get("configuration_assurance")
    if not isinstance(assurance, dict):
        return {}
    return {"configuration_assurance": dict(assurance)}


def _source_informed_scope_fields(summary: dict[str, Any]) -> dict[str, Any]:
    readiness = summary.get("source_informed_apply_readiness")
    if not isinstance(readiness, dict):
        return {
            "runtime_gate_truth": "runtime_apply_mode",
            "source_informed_readiness_scope": "not_present",
            "legacy_source_informed_flag_scope": "not_present",
        }
    return {
        "runtime_gate_truth": "runtime_apply_mode",
        "source_informed_readiness_scope": str(
            readiness.get("runtime_gate_impact", "diagnostic_only")
        ),
        "legacy_source_informed_flag_scope": str(
            readiness.get("legacy_flag_scope", "backward_compatible_only")
        ),
    }


def _mechanic_warning_fields(summary: dict[str, Any]) -> dict[str, Any]:
    mechanic_warning_summary = summary.get("mechanic_warning_summary")
    if isinstance(mechanic_warning_summary, dict):
        return {"mechanic_warning_summary": mechanic_warning_summary}
    return {
        "mechanic_warning_summary": {
            "support_level_counts": {"direct": 0, "partial": 0, "warning_only": 0},
            "warning_only_mechanics": [],
            "warning_only_card_count": 0,
        }
    }


def _mechanic_visibility_fields(summary: dict[str, Any]) -> dict[str, Any]:
    mechanic_visibility_summary = summary.get("mechanic_visibility_summary")
    if isinstance(mechanic_visibility_summary, dict):
        return {"mechanic_visibility_summary": mechanic_visibility_summary}
    return {
        "mechanic_visibility_summary": {
            "non_blocking": True,
            "bucket_counts": {
                "direct": 0,
                "identity_gated_direct": 0,
                "partial": 0,
                "warning_only": 0,
            },
            "mechanics_by_bucket": {
                "direct": [],
                "identity_gated_direct": [],
                "partial": [],
                "warning_only": [],
            },
            "warning_only_card_count": 0,
            "first_warning_boundary": None,
            "warning_boundaries": [],
        }
    }


def _mechanic_drift_fields(summary: dict[str, Any]) -> dict[str, Any]:
    drift = summary.get("mechanic_drift_summary")
    if isinstance(drift, dict):
        return {"mechanic_drift_summary": drift}
    return {
        "mechanic_drift_summary": {
            "non_blocking": True,
            "mechanic_count": 0,
            "unknown_mechanic_count": 0,
            "text_only_mechanic_count": 0,
            "unknown_card_type_count": 0,
            "unknown_mechanics": [],
            "text_only_mechanics": [],
            "unknown_card_types": [],
        }
    }


def _first_semantic_blocker_report(summary: dict[str, Any]) -> str | None:
    blockers = summary.get("semantic_blockers", [])
    if not isinstance(blockers, list):
        return None
    for blocker in blockers:
        if not isinstance(blocker, dict):
            continue
        report = blocker.get("report")
        if isinstance(report, str) and report.strip():
            return report
    return None


def _requires_expert_flag(semantic_status: str, apply_policy: str) -> bool:
    return (
        semantic_status in SOURCE_INFORMED_EXPERT_STATUSES
        and apply_policy == "ALLOWED_WITH_WARNINGS"
    )
