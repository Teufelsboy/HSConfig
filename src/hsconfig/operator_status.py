"""Pure operator apply-authority projection."""

from __future__ import annotations

import builtins
from dataclasses import dataclass
from types import FunctionType, MappingProxyType, SimpleNamespace
from typing import Any, NamedTuple

from hsconfig.apply_decision import build_apply_decision
from hsconfig.operator_summary_inputs import (
    OperatorAuthorityInputs,
    OperatorSummaryInputs,
)


_FACT_REASON = (
    ("strict_package_validation", "strict_package_validation_failed"),
    (
        "actual_runtime_surface_inventory",
        "runtime_surface_inventory_invalid",
    ),
    ("deck_input_verification", "deck_input_not_verified"),
    ("source_receipt_validity", "source_authority_receipt_invalid"),
    (
        "source_acquisition_eligibility",
        "source_acquisition_not_eligible",
    ),
    ("derivation_receipt_validity", "package_derivation_mismatch"),
    (
        "package_summary_parity",
        "operator_summary_package_parity_mismatch",
    ),
)


class _SealedApplyFacts(NamedTuple):
    strict_package_validation: bool
    actual_runtime_surface_inventory: bool
    deck_input_verification: bool
    source_receipt_validity: bool
    source_acquisition_eligibility: bool
    derivation_receipt_validity: bool
    package_summary_parity: bool
    blocking_reasons: tuple[dict[str, Any], ...]
    informational_reasons: tuple[dict[str, Any], ...]

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


@dataclass(frozen=True, slots=True)
class OperatorStatusProjection:
    technical_status: str
    semantic_status: str
    next_action: str
    apply_policy: str
    runtime_load_safe: bool
    runtime_apply_mode: str
    runtime_apply_allowed: bool
    runtime_apply_reason: str
    runtime_apply_requires_flag: bool | None
    load_safe_to_install: bool
    use_config_now: bool
    use_config_now_scope: str


def _sealed_reason_tuple(reasons: Any) -> tuple[dict[str, Any], ...]:
    return tuple(dict(reason) for reason in reasons)


def _seal_reason_tuple() -> FunctionType:
    source = _sealed_reason_tuple
    namespace = dict(source.__globals__)
    namespace["__builtins__"] = MappingProxyType(dict(vars(builtins)))
    return FunctionType(
        source.__code__,
        namespace,
        source.__name__,
        source.__defaults__,
        source.__closure__,
    )


def _seal_build_apply_decision() -> FunctionType:
    source = build_apply_decision
    namespace = dict(source.__globals__)
    namespace["__builtins__"] = MappingProxyType(dict(vars(builtins)))
    namespace["_FACT_REASON"] = _FACT_REASON
    namespace["_reason_tuple"] = _seal_reason_tuple()
    return FunctionType(
        source.__code__,
        namespace,
        source.__name__,
        source.__defaults__,
        source.__closure__,
    )


_BUILD_APPLY_DECISION = _seal_build_apply_decision()
_SUMMARY_AUTHORITY = OperatorSummaryInputs.__dict__["authority"]
_AUTHORITY_TYPE = OperatorAuthorityInputs
_AUTHORITY_SLOTS = tuple(
    _AUTHORITY_TYPE.__dict__[name]
    for name in (
        "package_authority",
        "strict_package_validation",
        "actual_runtime_surface_inventory",
        "deck_input_verification",
        "source_receipt_validity",
        "source_acquisition_eligibility",
        "derivation_receipt_validity",
        "package_summary_parity",
        "blocking_reasons",
    )
)


def _status_semantic_projector_unbound(
    inputs: OperatorSummaryInputs,
) -> str:
    raise RuntimeError("operator_status_semantic_projector_unbound")


_STATUS_SEMANTIC_PROJECTOR = _status_semantic_projector_unbound


def _build_operator_status_unsealed(
    inputs: OperatorSummaryInputs,
) -> OperatorStatusProjection:
    """Project the exact existing status core from immutable facts."""

    authority = _SUMMARY_AUTHORITY.__get__(inputs, OperatorSummaryInputs)
    (
        package_authority_slot,
        strict_package_validation_slot,
        actual_runtime_surface_inventory_slot,
        deck_input_verification_slot,
        source_receipt_validity_slot,
        source_acquisition_eligibility_slot,
        derivation_receipt_validity_slot,
        package_summary_parity_slot,
        blocking_reasons_slot,
    ) = _AUTHORITY_SLOTS
    package_authority = package_authority_slot.__get__(
        authority,
        _AUTHORITY_TYPE,
    )
    strict_package_validation = strict_package_validation_slot.__get__(
        authority,
        _AUTHORITY_TYPE,
    )
    actual_runtime_surface_inventory = (
        actual_runtime_surface_inventory_slot.__get__(
            authority,
            _AUTHORITY_TYPE,
        )
    )
    deck_input_verification = deck_input_verification_slot.__get__(
        authority,
        _AUTHORITY_TYPE,
    )
    source_receipt_validity = source_receipt_validity_slot.__get__(
        authority,
        _AUTHORITY_TYPE,
    )
    source_acquisition_eligibility = (
        source_acquisition_eligibility_slot.__get__(
            authority,
            _AUTHORITY_TYPE,
        )
    )
    derivation_receipt_validity = (
        derivation_receipt_validity_slot.__get__(
            authority,
            _AUTHORITY_TYPE,
        )
    )
    package_summary_parity = package_summary_parity_slot.__get__(
        authority,
        _AUTHORITY_TYPE,
    )
    blocking_reasons = blocking_reasons_slot.__get__(
        authority,
        _AUTHORITY_TYPE,
    )
    semantic_status = _STATUS_SEMANTIC_PROJECTOR(inputs)
    informational: list[dict[str, Any]] = []
    if (
        package_authority is not None
        and source_receipt_validity
        and package_authority.get("exact_source_closed") is not True
    ):
        informational.append(
            {"reason": "exact_source_not_closed", "blocking": False}
        )
    if semantic_status != "SOURCE_BACKED_STRONG":
        informational.append(
            {"reason": "semantic_strength_incomplete", "blocking": False}
        )
    facts = SimpleNamespace(
        strict_package_validation=strict_package_validation,
        actual_runtime_surface_inventory=actual_runtime_surface_inventory,
        deck_input_verification=deck_input_verification,
        source_receipt_validity=source_receipt_validity,
        source_acquisition_eligibility=source_acquisition_eligibility,
        derivation_receipt_validity=derivation_receipt_validity,
        package_summary_parity=package_summary_parity,
        blocking_reasons=tuple(
            dict(reason) for reason in blocking_reasons
        ),
        informational_reasons=tuple(informational),
    )
    decision = _BUILD_APPLY_DECISION(facts)
    technical_valid = all(
        (
            strict_package_validation,
            actual_runtime_surface_inventory,
            deck_input_verification,
            source_receipt_validity,
            derivation_receipt_validity,
            package_summary_parity,
        )
    )
    technical_status = (
        "VALID_PACKAGE" if technical_valid else "INVALID_PACKAGE"
    )
    runtime_apply_reason = (
        str(decision.reasons[0].get("reason") or "blocked")
        if decision.reasons
        else ("runtime_load_safe_package" if decision.allowed else "blocked")
    )
    if decision.allowed:
        next_action = (
            "READY_TO_APPLY_OR_HANDOFF"
            if semantic_status == "SOURCE_BACKED_STRONG"
            else "READY_TO_APPLY_WITH_WARNINGS"
        )
    elif (
        technical_valid
        and not source_acquisition_eligibility
    ):
        next_action = "ACQUIRE_LIVE_VERIFIED_SOURCE_BEFORE_APPLY"
    else:
        next_action = "FIX_PACKAGE_BEFORE_APPLY"
    load_safe_to_install = (
        technical_status == "VALID_PACKAGE"
        and decision.allowed is True
        and decision.mode == "load_safe_apply"
    )
    return OperatorStatusProjection(
        technical_status=technical_status,
        semantic_status=semantic_status,
        next_action=next_action,
        apply_policy=str(decision.policy),
        runtime_load_safe=technical_status == "VALID_PACKAGE",
        runtime_apply_mode=str(decision.mode),
        runtime_apply_allowed=decision.allowed is True,
        runtime_apply_reason=runtime_apply_reason,
        runtime_apply_requires_flag=None,
        load_safe_to_install=load_safe_to_install,
        use_config_now=load_safe_to_install,
        use_config_now_scope="load_safety_only",
    )


def _invoke_status_projection(
    kernel: FunctionType,
    inputs: OperatorSummaryInputs,
) -> OperatorStatusProjection:
    """Project status through the definitions-bound authority kernel."""

    return kernel(inputs)


def _invoke_status_name(
    project: FunctionType,
    inputs: OperatorSummaryInputs,
) -> str:
    """Return the existing public next-action status."""

    return project(inputs).next_action


build_operator_status = _status_semantic_projector_unbound
determine_operator_status = _status_semantic_projector_unbound


def _install_operator_status_kernel(
    semantic_projector: FunctionType,
    freezer: FunctionType,
    guard_factory: Any,
) -> None:
    global _STATUS_SEMANTIC_PROJECTOR
    global build_operator_status
    global determine_operator_status

    _STATUS_SEMANTIC_PROJECTOR = semantic_projector
    (primary_kernel,) = freezer((_build_operator_status_unsealed,))
    (backup_kernel,) = freezer((_build_operator_status_unsealed,))
    (primary_invoker,) = freezer((_invoke_status_projection,))
    (backup_invoker,) = freezer((_invoke_status_projection,))
    build_operator_status = guard_factory(
        primary=primary_invoker,
        backup=backup_invoker,
        primary_bound=(primary_kernel,),
        backup_bound=(backup_kernel,),
        name="build_operator_status",
        signature_source=_status_semantic_projector_unbound,
    )
    (primary_name_invoker,) = freezer((_invoke_status_name,))
    (backup_name_invoker,) = freezer((_invoke_status_name,))
    determine_operator_status = guard_factory(
        primary=primary_name_invoker,
        backup=backup_name_invoker,
        primary_bound=(build_operator_status,),
        backup_bound=(build_operator_status,),
        name="determine_operator_status",
        signature_source=_status_semantic_projector_unbound,
    )
    _STATUS_SEMANTIC_PROJECTOR = _status_semantic_projector_unbound


__all__ = (
    "OperatorStatusProjection",
    "build_operator_status",
    "determine_operator_status",
)


import hsconfig.operator_summary as _operator_summary_binding  # noqa: E402,F401

del _operator_summary_binding
