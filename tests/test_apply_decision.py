from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest


def _valid_facts():
    from hsconfig.apply_decision import ApplyFacts

    return ApplyFacts(
        strict_package_validation=True,
        actual_runtime_surface_inventory=True,
        deck_input_verification=True,
        source_receipt_validity=True,
        source_acquisition_eligibility=True,
        derivation_receipt_validity=True,
        package_summary_parity=True,
    )


def test_apply_decision_is_an_immutable_literal_load_safe_projection() -> None:
    from hsconfig.apply_decision import ApplyDecision, build_apply_decision

    decision = build_apply_decision(_valid_facts())

    assert decision == ApplyDecision(
        allowed=True,
        mode="load_safe_apply",
        policy="ALLOWED",
        reasons=({"reason": "runtime_load_safe_package"},),
    )
    with pytest.raises(FrozenInstanceError):
        decision.allowed = False  # type: ignore[misc]


@pytest.mark.parametrize(
    ("fact_name", "reason"),
    [
        ("strict_package_validation", "strict_package_validation_failed"),
        ("actual_runtime_surface_inventory", "normal_path_optional_surface_present"),
        ("deck_input_verification", "deck_input_not_verified"),
        ("source_receipt_validity", "source_authority_receipt_invalid"),
        ("source_acquisition_eligibility", "source_acquisition_not_eligible"),
        ("derivation_receipt_validity", "package_derivation_mismatch"),
        ("package_summary_parity", "operator_summary_runtime_file_missing"),
    ],
)
def test_apply_decision_blocks_each_recomputed_integrity_fact_with_literal_reason(
    fact_name: str,
    reason: str,
) -> None:
    from hsconfig.apply_decision import ApplyFacts, build_apply_decision

    facts = {
        "strict_package_validation": True,
        "actual_runtime_surface_inventory": True,
        "deck_input_verification": True,
        "source_receipt_validity": True,
        "source_acquisition_eligibility": True,
        "derivation_receipt_validity": True,
        "package_summary_parity": True,
    }
    facts[fact_name] = False

    decision = build_apply_decision(
        ApplyFacts(
            **facts,
            blocking_reasons=({"reason": reason, "code": reason},),
        )
    )

    assert decision.allowed is False
    assert decision.mode == "blocked"
    assert decision.policy == "BLOCKED"
    assert decision.reasons == ({"reason": reason, "code": reason},)


def test_missing_exact_source_is_visible_without_becoming_a_second_gate() -> None:
    from hsconfig.apply_decision import ApplyFacts, build_apply_decision

    decision = build_apply_decision(
        ApplyFacts(
            strict_package_validation=True,
            actual_runtime_surface_inventory=True,
            deck_input_verification=True,
            source_receipt_validity=True,
            source_acquisition_eligibility=True,
            derivation_receipt_validity=True,
            package_summary_parity=True,
            informational_reasons=(
                {
                    "reason": "exact_source_not_closed",
                    "blocking": False,
                },
            ),
        )
    )

    assert decision.allowed is True
    assert decision.mode == "load_safe_apply"
    assert decision.policy == "ALLOWED_WITH_WARNINGS"
    assert decision.reasons == (
        {"reason": "runtime_load_safe_package"},
        {"reason": "exact_source_not_closed", "blocking": False},
    )


def test_blocked_decision_derives_literal_reasons_when_caller_provides_none() -> None:
    from hsconfig.apply_decision import ApplyFacts, build_apply_decision

    decision = build_apply_decision(
        ApplyFacts(
            strict_package_validation=False,
            actual_runtime_surface_inventory=True,
            deck_input_verification=True,
            source_receipt_validity=True,
            source_acquisition_eligibility=True,
            derivation_receipt_validity=True,
            package_summary_parity=False,
        )
    )

    assert decision.reasons == (
        {
            "reason": "strict_package_validation_failed",
            "code": "strict_package_validation_failed",
        },
        {
            "reason": "operator_summary_package_parity_mismatch",
            "code": "operator_summary_package_parity_mismatch",
        },
    )


def test_apply_decision_payload_returns_detached_plain_reason_rows() -> None:
    from hsconfig.apply_decision import (
        ApplyDecision,
        apply_decision_payload,
    )

    reason = {"reason": "blocked", "detail": "original"}
    payload = apply_decision_payload(
        ApplyDecision(
            allowed=False,
            mode="blocked",
            policy="BLOCKED",
            reasons=(reason,),
        )
    )
    payload["reasons"][0]["detail"] = "changed"

    assert payload == {
        "allowed": False,
        "mode": "blocked",
        "policy": "BLOCKED",
        "reasons": [{"reason": "blocked", "detail": "changed"}],
    }
    assert reason == {"reason": "blocked", "detail": "original"}


def test_summary_projection_reports_invalid_technical_facts_and_primary_reason() -> None:
    from hsconfig.apply_decision import (
        ApplyFacts,
        apply_decision_summary_projection,
        build_apply_decision,
    )

    facts = ApplyFacts(
        strict_package_validation=True,
        actual_runtime_surface_inventory=False,
        deck_input_verification=True,
        source_receipt_validity=True,
        source_acquisition_eligibility=True,
        derivation_receipt_validity=True,
        package_summary_parity=True,
    )
    decision = build_apply_decision(facts)

    assert facts.technical_valid is False
    assert apply_decision_summary_projection(decision, facts) == {
        "technical_status": "INVALID_PACKAGE",
        "apply_policy": "BLOCKED",
        "runtime_apply_allowed": False,
        "runtime_apply_mode": "blocked",
        "runtime_apply_reason": "runtime_surface_inventory_invalid",
    }


@pytest.mark.parametrize(
    ("allowed", "expected"),
    ((True, "runtime_load_safe_package"), (False, "blocked")),
)
def test_primary_apply_reason_handles_decisions_without_reason_rows(
    allowed: bool,
    expected: str,
) -> None:
    from hsconfig.apply_decision import ApplyDecision, primary_apply_reason

    decision = ApplyDecision(
        allowed=allowed,
        mode="load_safe_apply" if allowed else "blocked",
        policy="ALLOWED" if allowed else "BLOCKED",
        reasons=(),
    )

    assert primary_apply_reason(decision) == expected


def test_primary_apply_reason_fails_closed_for_blank_reason_value() -> None:
    from hsconfig.apply_decision import ApplyDecision, primary_apply_reason

    decision = ApplyDecision(
        allowed=True,
        mode="load_safe_apply",
        policy="ALLOWED_WITH_WARNINGS",
        reasons=({"reason": ""},),
    )

    assert primary_apply_reason(decision) == "blocked"


def test_optimized_apply_uses_bound_starter_derivation_without_fabricated_source_authority() -> None:
    from hsconfig.apply_decision import ApplyFacts, build_apply_decision

    common = {
        "strict_package_validation": True,
        "actual_runtime_surface_inventory": True,
        "deck_input_verification": True,
        "source_receipt_validity": True,
        "source_acquisition_eligibility": False,
        "derivation_receipt_validity": True,
        "package_summary_parity": True,
    }
    conservative = build_apply_decision(
        ApplyFacts(
            **common,
            strategy_authority_mode="source_contract",
            optimized_start_derivation_validity=False,
        )
    )
    optimized = build_apply_decision(
        ApplyFacts(
            **common,
            strategy_authority_mode="llm_optimized_start",
            optimized_start_derivation_validity=True,
            informational_reasons=(
                {
                    "reason": "diagnostic_source_not_apply_eligible",
                    "blocking": False,
                },
            ),
        )
    )
    stale = build_apply_decision(
        ApplyFacts(
            **common,
            strategy_authority_mode="llm_optimized_start",
            optimized_start_derivation_validity=False,
        )
    )

    assert conservative.allowed is False
    assert conservative.reasons[0]["reason"] == (
        "source_acquisition_not_eligible"
    )
    assert optimized.allowed is True
    assert optimized.policy == "ALLOWED_WITH_WARNINGS"
    assert optimized.reasons[-1] == {
        "reason": "diagnostic_source_not_apply_eligible",
        "blocking": False,
    }
    assert stale.allowed is False
    assert stale.reasons == (
        {
            "reason": "optimized_start_derivation_invalid",
            "code": "optimized_start_derivation_invalid",
        },
    )
