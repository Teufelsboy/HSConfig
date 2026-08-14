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
