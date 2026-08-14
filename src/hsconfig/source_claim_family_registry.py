from __future__ import annotations

from typing import Any

from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS


NORMAL_APPLY_GATE = "reports/operator_summary.json"
DIAGNOSTIC_AUTHORITY = "diagnostic_only"

_CONFLICT_FAMILY_BY_CLAIM_KIND = {
    "mulligan_keep": "mulligan",
    "mulligan_discard": "mulligan",
    "targeting_rule": "targeting",
    "combo_sequence": "combo_timing",
    "discover_choice": "option_choice",
    "choose_one_choice": "option_choice",
    "card_role": "role_vs_known_bad_pattern",
    "known_bad_pattern": "role_vs_known_bad_pattern",
}

_NEGATIVE_BOUNDARY_BY_CLAIM_KIND = {
    "archetype": "report_only_not_runtime_surface",
    "mulligan_keep": "requires_explicit_opening_hand_intent",
    "mulligan_discard": "requires_explicit_opening_hand_discard_intent",
    "card_role": "requires_supported_cardid_surface",
    "targeting_rule": "requires_supported_target_and_block_identity",
    "combo_sequence": "requires_complete_ordered_sequence",
    "gameplan_posture": "posture_only_not_numeric_tuning",
    "hero_power_transform": "not_opening_hand_keep_without_explicit_mulligan_claim",
    "mechanic_usage": "requires_documented_cardid_surface",
    "known_bad_pattern": "requires_supported_negative_behavior_row",
    "tech_slot": "report_only_deck_construction_advice",
    "replacement_option": "report_only_deck_construction_advice",
    "discover_choice": "requires_exact_option_identity",
    "choose_one_choice": "requires_exact_option_identity",
    "globalvalue_numeric_tuning": "requires_runtime_evidence_before_numeric_write",
}


def claim_family_registry() -> dict[str, dict[str, Any]]:
    """Return diagnostic guardrails derived from the source-contract policy."""
    policy = source_contract_policy_by_claim_kind()
    return {
        claim_kind: {
            "claim_kind": claim_kind,
            "policy_lane": row["lane"],
            "allowed_surfaces": tuple(row["allowed_surfaces"]),
            "conflict_family": _CONFLICT_FAMILY_BY_CLAIM_KIND.get(claim_kind, "none"),
            "negative_boundary": _NEGATIVE_BOUNDARY_BY_CLAIM_KIND.get(
                claim_kind, ""
            ),
            "operator_gate_impact": DIAGNOSTIC_AUTHORITY,
            "normal_apply_gate": NORMAL_APPLY_GATE,
        }
        for claim_kind, row in sorted(policy.items())
    }


def build_claim_family_registry_report() -> dict[str, Any]:
    registry = claim_family_registry()
    problems = _registry_problems(registry)
    return {
        "schema_version": 1,
        "status": "clean" if not problems else "drift_detected",
        "authority": DIAGNOSTIC_AUTHORITY,
        "apply_blocking": False,
        "normal_apply_gate": NORMAL_APPLY_GATE,
        "registry": registry,
        "problems": problems,
    }


def _registry_problems(registry: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []
    expected = set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    actual = set(registry)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        problems.append({"check": "missing_claim_kinds", "value": missing})
    if extra:
        problems.append({"check": "extra_claim_kinds", "value": extra})

    for claim_kind, row in sorted(registry.items()):
        if row.get("operator_gate_impact") != DIAGNOSTIC_AUTHORITY:
            problems.append(
                {
                    "check": "non_diagnostic_operator_gate_impact",
                    "claim_kind": claim_kind,
                    "value": row.get("operator_gate_impact"),
                }
            )
        if row.get("normal_apply_gate") != NORMAL_APPLY_GATE:
            problems.append(
                {
                    "check": "wrong_normal_apply_gate",
                    "claim_kind": claim_kind,
                    "value": row.get("normal_apply_gate"),
                }
            )
        if not row.get("negative_boundary"):
            problems.append(
                {"check": "missing_negative_boundary", "claim_kind": claim_kind}
            )
    return problems
