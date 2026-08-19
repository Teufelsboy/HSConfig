from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class ApplyFacts:
    strict_package_validation: bool
    actual_runtime_surface_inventory: bool
    deck_input_verification: bool
    source_receipt_validity: bool
    source_acquisition_eligibility: bool
    derivation_receipt_validity: bool
    package_summary_parity: bool
    strategy_authority_mode: Literal[
        "source_contract",
        "llm_optimized_start",
    ] = "source_contract"
    optimized_start_derivation_validity: bool = False
    blocking_reasons: Sequence[Mapping[str, Any]] = ()
    informational_reasons: Sequence[Mapping[str, Any]] = ()

    @property
    def technical_valid(self) -> bool:
        return all(
            (
                self.strict_package_validation,
                self.actual_runtime_surface_inventory,
                self.deck_input_verification,
                self.source_receipt_validity,
                self.derivation_receipt_validity,
                self.package_summary_parity,
            )
        )


@dataclass(frozen=True)
class ApplyDecision:
    allowed: bool
    mode: str
    policy: str
    reasons: Sequence[Mapping[str, Any]]


_FACT_REASON = (
    ("strict_package_validation", "strict_package_validation_failed"),
    ("actual_runtime_surface_inventory", "runtime_surface_inventory_invalid"),
    ("deck_input_verification", "deck_input_not_verified"),
    ("source_receipt_validity", "source_authority_receipt_invalid"),
    ("source_acquisition_eligibility", "source_acquisition_not_eligible"),
    ("derivation_receipt_validity", "package_derivation_mismatch"),
    ("package_summary_parity", "operator_summary_package_parity_mismatch"),
)


def build_apply_decision(facts: ApplyFacts) -> ApplyDecision:
    if facts.strategy_authority_mode == "source_contract":
        fact_reasons = _FACT_REASON
    elif facts.strategy_authority_mode == "llm_optimized_start":
        fact_reasons = tuple(
            (
                "optimized_start_derivation_validity",
                "optimized_start_derivation_invalid",
            )
            if fact_name == "source_acquisition_eligibility"
            else (fact_name, reason)
            for fact_name, reason in _FACT_REASON
        )
    else:
        return ApplyDecision(
            allowed=False,
            mode="blocked",
            policy="BLOCKED",
            reasons=(
                {
                    "reason": "strategy_authority_mode_invalid",
                    "code": "strategy_authority_mode_invalid",
                },
            ),
        )
    allowed = all(
        bool(getattr(facts, fact_name))
        for fact_name, _reason in fact_reasons
    )
    if not allowed:
        reasons = _reason_tuple(facts.blocking_reasons)
        if not reasons:
            reasons = tuple(
                {"reason": reason, "code": reason}
                for fact_name, reason in fact_reasons
                if not bool(getattr(facts, fact_name))
            )
        return ApplyDecision(
            allowed=False,
            mode="blocked",
            policy="BLOCKED",
            reasons=reasons,
        )

    informational = _reason_tuple(facts.informational_reasons)
    return ApplyDecision(
        allowed=True,
        mode="load_safe_apply",
        policy="ALLOWED_WITH_WARNINGS" if informational else "ALLOWED",
        reasons=(
            {"reason": "runtime_load_safe_package"},
            *informational,
        ),
    )


def apply_decision_payload(decision: ApplyDecision) -> dict[str, Any]:
    return {
        "allowed": decision.allowed,
        "mode": decision.mode,
        "policy": decision.policy,
        "reasons": [dict(reason) for reason in decision.reasons],
    }


def apply_decision_summary_projection(
    decision: ApplyDecision,
    facts: ApplyFacts,
) -> dict[str, Any]:
    projection = {
        "technical_status": (
            "VALID_PACKAGE" if facts.technical_valid else "INVALID_PACKAGE"
        ),
        "apply_policy": decision.policy,
        "runtime_apply_allowed": decision.allowed,
        "runtime_apply_mode": decision.mode,
        "runtime_apply_reason": primary_apply_reason(decision),
    }
    if facts.strategy_authority_mode == "llm_optimized_start":
        projection.update(
            {
                "strategy_authority_mode": "llm_optimized_start",
                "optimized_start_derivation_validity": (
                    facts.optimized_start_derivation_validity
                ),
            }
        )
    return projection


def primary_apply_reason(decision: ApplyDecision) -> str:
    if not decision.reasons:
        return "runtime_load_safe_package" if decision.allowed else "blocked"
    return str(decision.reasons[0].get("reason") or "blocked")


def _reason_tuple(
    reasons: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    return tuple(dict(reason) for reason in reasons)
