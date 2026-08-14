from __future__ import annotations

from collections.abc import Mapping
from types import FunctionType, MemberDescriptorType
from typing import Any

from hsconfig.operator_integrity import _operator_integrity_bootstrap
from hsconfig.operator_summary_evaluator import (
    _operator_summary_evaluator_bootstrap,
    refresh_generated_file_accounting as refresh_generated_file_accounting,
)
from hsconfig.operator_summary_inputs import (
    OperatorSummaryInputs,
    freeze_operator_summary_inputs,
)
from hsconfig.package_domain import MulliganPlanModel


def _freeze_operator_roots(
    roots: tuple[FunctionType, ...],
) -> tuple[FunctionType, ...]:
    return _operator_integrity_bootstrap("freeze", roots)


def _guard_operator_root(**kwargs: Any) -> Any:
    return _operator_integrity_bootstrap("guard", **kwargs)


(
    _operator_summary_evaluator_primary,
    _thaw_operator_value_primary,
) = _operator_summary_evaluator_bootstrap()
(
    _operator_summary_evaluator_backup,
    _thaw_operator_value_backup,
) = _operator_summary_evaluator_bootstrap()
_INPUT_LEGACY_KWARGS = OperatorSummaryInputs.__dict__["legacy_kwargs"]


def _invoke_operator_summary_evaluator(
    evaluator: FunctionType,
    thaw: FunctionType,
    legacy_kwargs_slot: MemberDescriptorType,
    inputs: OperatorSummaryInputs,
) -> dict[str, Any]:
    legacy_kwargs = thaw(
        legacy_kwargs_slot.__get__(inputs, None)
    )
    return evaluator(**legacy_kwargs)


(_operator_summary_invoker_primary,) = _freeze_operator_roots(
    (_invoke_operator_summary_evaluator,)
)
(_operator_summary_invoker_backup,) = _freeze_operator_roots(
    (_invoke_operator_summary_evaluator,)
)
_evaluate_operator_summary_inputs = _guard_operator_root(
    primary=_operator_summary_invoker_primary,
    backup=_operator_summary_invoker_backup,
    primary_bound=(
        _operator_summary_evaluator_primary,
        _thaw_operator_value_primary,
        _INPUT_LEGACY_KWARGS,
    ),
    backup_bound=(
        _operator_summary_evaluator_backup,
        _thaw_operator_value_backup,
        _INPUT_LEGACY_KWARGS,
    ),
    name="_evaluate_operator_summary_inputs",
)


def _operator_semantic_status_from_inputs(
    inputs: OperatorSummaryInputs,
) -> str:
    return str(_evaluate_operator_summary_inputs(inputs)["semantic_status"])


import hsconfig.operator_status as _operator_status_module  # noqa: E402

_operator_status_module._install_operator_status_kernel(
    _operator_semantic_status_from_inputs,
    _freeze_operator_roots,
    _guard_operator_root,
)
_operator_status_projector = (
    _operator_status_module.build_operator_status
)
delattr(
    _operator_status_module,
    "_install_operator_status_kernel",
)


def _invoke_operator_summary_projection(
    evaluate: FunctionType,
    project_status: FunctionType,
    inputs: OperatorSummaryInputs,
) -> dict[str, Any]:
    """Build the public summary from the immutable input boundary."""

    summary = evaluate(inputs)
    status = project_status(inputs)
    summary.update(
        {
            "technical_status": status.technical_status,
            "semantic_status": status.semantic_status,
            "next_action": status.next_action,
            "apply_policy": status.apply_policy,
            "runtime_load_safe": status.runtime_load_safe,
            "runtime_apply_mode": status.runtime_apply_mode,
            "runtime_apply_allowed": status.runtime_apply_allowed,
            "runtime_apply_reason": status.runtime_apply_reason,
            "runtime_apply_requires_flag": (
                status.runtime_apply_requires_flag
            ),
            "load_safe_to_install": status.load_safe_to_install,
            "use_config_now": status.use_config_now,
            "use_config_now_scope": status.use_config_now_scope,
        }
    )
    return summary


(_summary_projection_primary,) = _freeze_operator_roots(
    (_invoke_operator_summary_projection,)
)
(_summary_projection_backup,) = _freeze_operator_roots(
    (_invoke_operator_summary_projection,)
)
build_operator_summary_from_inputs = _guard_operator_root(
    primary=_summary_projection_primary,
    backup=_summary_projection_backup,
    primary_bound=(
        _evaluate_operator_summary_inputs,
        _operator_status_projector,
    ),
    backup_bound=(
        _evaluate_operator_summary_inputs,
        _operator_status_projector,
    ),
    name="build_operator_summary_from_inputs",
    signature_source=_operator_semantic_status_from_inputs,
)
del (
    _operator_summary_evaluator_primary,
    _operator_summary_evaluator_backup,
    _thaw_operator_value_primary,
    _thaw_operator_value_backup,
    _operator_summary_invoker_primary,
    _operator_summary_invoker_backup,
    _summary_projection_primary,
    _summary_projection_backup,
    _operator_status_module,
    _operator_status_projector,
)


def build_operator_summary(
    *,
    deck_name: str | None = None,
    deck_code: str | None = None,
    technical_validation: dict[str, Any] | None = None,
    guide_source_depth: dict[str, Any] | None = None,
    unsupported_conditions: list[dict[str, Any]] | None = None,
    globalvalue_authority: dict[str, Any] | None = None,
    generated_files: list[str] | None = None,
    claim_coverage_report: dict[str, Any] | None = None,
    config_readiness_summary: dict[str, Any] | None = None,
    config_readiness_report: dict[str, Any] | None = None,
    claim_conflict_report: dict[str, Any] | None = None,
    mulligan_plan_report: (
        Mapping[str, Any] | MulliganPlanModel | None
    ) = None,
    card_behavior_plan_report: dict[str, Any] | None = None,
    combo_plan_report: dict[str, Any] | None = None,
    globalvalues_profile_report: dict[str, Any] | None = None,
    semantic_enrichment_report: dict[str, Any] | None = None,
    mechanic_drift_report: dict[str, Any] | None = None,
    validation_report: dict[str, Any] | None = None,
    guide_source_depth_report: dict[str, Any] | None = None,
    source_claim_gap_report: dict[str, Any] | None = None,
    source_contract_audit_report: dict[str, Any] | None = None,
    source_to_runtime_explainability_report: dict[str, Any] | None = None,
    strong_promotion_report: dict[str, Any] | None = None,
    output_ownership_manifest: dict[str, Any] | None = None,
    gameplan_contract: dict[str, Any] | None = None,
    package_derivation: dict[str, Any] | None = None,
    package_authority: dict[str, Any] | None = None,
    deck_input_verification: dict[str, Any] | None = None,
    runtime_surface_ledger: Mapping[str, Any] | None = None,
    pre_run_closure_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compatibility facade over frozen in-memory inputs."""

    inputs = freeze_operator_summary_inputs(
        deck_name=deck_name,
        deck_code=deck_code,
        technical_validation=technical_validation,
        guide_source_depth=guide_source_depth,
        unsupported_conditions=unsupported_conditions,
        globalvalue_authority=globalvalue_authority,
        generated_files=generated_files,
        claim_coverage_report=claim_coverage_report,
        config_readiness_summary=config_readiness_summary,
        config_readiness_report=config_readiness_report,
        claim_conflict_report=claim_conflict_report,
        mulligan_plan_report=mulligan_plan_report,
        card_behavior_plan_report=card_behavior_plan_report,
        combo_plan_report=combo_plan_report,
        globalvalues_profile_report=globalvalues_profile_report,
        semantic_enrichment_report=semantic_enrichment_report,
        mechanic_drift_report=mechanic_drift_report,
        validation_report=validation_report,
        guide_source_depth_report=guide_source_depth_report,
        source_claim_gap_report=source_claim_gap_report,
        source_contract_audit_report=source_contract_audit_report,
        source_to_runtime_explainability_report=(
            source_to_runtime_explainability_report
        ),
        strong_promotion_report=strong_promotion_report,
        output_ownership_manifest=output_ownership_manifest,
        gameplan_contract=gameplan_contract,
        package_derivation=package_derivation,
        package_authority=package_authority,
        deck_input_verification=deck_input_verification,
        runtime_surface_ledger=runtime_surface_ledger,
        pre_run_closure_report=pre_run_closure_report,
    )
    return build_operator_summary_from_inputs(inputs)


(_legacy_operator_summary_primary,) = _freeze_operator_roots(
    (build_operator_summary,)
)
(_legacy_operator_summary_backup,) = _freeze_operator_roots(
    (build_operator_summary,)
)


def _invoke_legacy_operator_summary(
    kernel: FunctionType,
    *args: Any,
    **kwargs: Any,
) -> dict[str, Any]:
    return kernel(*args, **kwargs)


(_legacy_invoker_primary,) = _freeze_operator_roots(
    (_invoke_legacy_operator_summary,)
)
(_legacy_invoker_backup,) = _freeze_operator_roots(
    (_invoke_legacy_operator_summary,)
)
_legacy_operator_summary_source = build_operator_summary
build_operator_summary = _guard_operator_root(
    primary=_legacy_invoker_primary,
    backup=_legacy_invoker_backup,
    primary_bound=(_legacy_operator_summary_primary,),
    backup_bound=(_legacy_operator_summary_backup,),
    name="build_operator_summary",
    signature_source=_legacy_operator_summary_source,
    annotations=_legacy_operator_summary_source.__annotations__,
)
del (
    _legacy_operator_summary_primary,
    _legacy_operator_summary_backup,
    _legacy_invoker_primary,
    _legacy_invoker_backup,
    _legacy_operator_summary_source,
)
