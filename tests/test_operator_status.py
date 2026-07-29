from __future__ import annotations

from dataclasses import asdict, replace
import json
from pathlib import Path
import subprocess
import sys
import textwrap
from types import FunctionType, SimpleNamespace

import pytest

from hsconfig.operator_status import (
    build_operator_status,
    determine_operator_status,
)
import hsconfig.operator_status as operator_status_module
from hsconfig.operator_summary import build_operator_summary_from_inputs
from hsconfig.operator_summary_inputs import (
    OperatorSummaryInputs,
    freeze_operator_summary_inputs,
)
from tests.test_operator_summary import (
    _guide_backed_profile_report,
    _source_backed_mulligan_plan_report,
)


def _allowed_inputs(*, strong: bool = False):
    kwargs = {
        "deck_name": "Status",
        "deck_code": "AAE=",
        "technical_validation": {"status": "passed", "errors": []},
    }
    if strong:
        kwargs.update(
            {
                "guide_source_depth": {
                    "source_depth_status": "source_backed",
                    "claim_count": 3,
                    "source_evidence": {"warnings_count": 0},
                },
                "unsupported_conditions": [],
                "claim_coverage_report": {
                    "summary": {
                        "guide_backed": 3,
                        "static_semantics_backfilled": 0,
                        "uncovered_low_confidence": 0,
                    },
                    "uncovered_cards": [],
                },
                "config_readiness_summary": {
                    "total_cards": 3,
                    "runtime_emitted": 3,
                    "generic_low_confidence": 0,
                    "cards_needing_guide_claims": 0,
                    "cards_needing_runtime_surface": 0,
                    "cards_needing_mulligan_claims": 0,
                    "cards_needing_combo_sequence": 0,
                    "cards_needing_condition_lowering": 0,
                    "cards_needing_mechanic_lowering": 0,
                },
                "claim_conflict_report": {
                    "conflict_count": 0,
                    "conflicts": [],
                },
                "mulligan_plan_report": (
                    _source_backed_mulligan_plan_report()
                ),
                "source_claim_gap_report": {
                    "summary": {
                        "source_quality_lane_counts": {
                            "deck_matched_public_guide": 3
                        }
                    }
                },
                "source_to_runtime_explainability_report": (
                    _guide_backed_profile_report(
                        ["gameplan_posture"],
                    )
                ),
                "generated_files": [
                    "CustomConfig/status/GlobalValues.json",
                    "CustomConfig/status/Mulligan.json",
                ],
            }
        )
    return freeze_operator_summary_inputs(
        **kwargs,
    )


def _guarded_state(callable_):
    """Read opaque carrier state only for controlled fault injection."""

    return object.__getattribute__(
        callable_,
        "_GuardedOperatorCallable__state",
    )


def _canonical_status_bytes(inputs) -> bytes:
    return json.dumps(
        asdict(build_operator_status(inputs)),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _canonical_summary_bytes(inputs) -> bytes:
    return json.dumps(
        build_operator_summary_from_inputs(inputs),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _primary_summary_evaluator():
    summary_state = _guarded_state(build_operator_summary_from_inputs)
    evaluator_carrier = summary_state[2][0]
    evaluator_state = _guarded_state(evaluator_carrier)
    return evaluator_state[2][0]


def test_status_preserves_exact_ready_and_warning_domain() -> None:
    warning = build_operator_status(_allowed_inputs())
    strong = build_operator_status(_allowed_inputs(strong=True))

    assert warning.next_action == "READY_TO_APPLY_WITH_WARNINGS"
    assert warning.apply_policy == "ALLOWED_WITH_WARNINGS"
    assert warning.runtime_apply_allowed is True
    assert strong.next_action == "READY_TO_APPLY_OR_HANDOFF"
    assert strong.apply_policy == "ALLOWED"


@pytest.mark.parametrize(
    ("fact_name", "reason", "next_action"),
    [
        (
            "strict_package_validation",
            "strict_package_validation_failed",
            "FIX_PACKAGE_BEFORE_APPLY",
        ),
        (
            "actual_runtime_surface_inventory",
            "runtime_surface_inventory_invalid",
            "FIX_PACKAGE_BEFORE_APPLY",
        ),
        (
            "deck_input_verification",
            "deck_input_not_verified",
            "FIX_PACKAGE_BEFORE_APPLY",
        ),
        (
            "source_receipt_validity",
            "source_authority_receipt_invalid",
            "FIX_PACKAGE_BEFORE_APPLY",
        ),
        (
            "source_acquisition_eligibility",
            "source_acquisition_not_eligible",
            "ACQUIRE_LIVE_VERIFIED_SOURCE_BEFORE_APPLY",
        ),
        (
            "derivation_receipt_validity",
            "package_derivation_mismatch",
            "FIX_PACKAGE_BEFORE_APPLY",
        ),
        (
            "package_summary_parity",
            "operator_summary_package_parity_mismatch",
            "FIX_PACKAGE_BEFORE_APPLY",
        ),
    ],
)
def test_each_authority_fact_fails_closed_with_existing_precedence(
    fact_name: str,
    reason: str,
    next_action: str,
) -> None:
    inputs = _allowed_inputs()
    authority = replace(inputs.authority, **{fact_name: False})
    blocked = replace(inputs, authority=authority)

    projection = build_operator_status(blocked)

    assert projection.runtime_apply_allowed is False
    assert projection.runtime_apply_mode == "blocked"
    assert projection.runtime_apply_reason == reason
    assert determine_operator_status(blocked) == next_action


def test_combined_authority_failures_keep_literal_fact_order() -> None:
    inputs = _allowed_inputs()
    blocked = replace(
        inputs,
        authority=replace(
            inputs.authority,
            strict_package_validation=False,
            deck_input_verification=False,
            derivation_receipt_validity=False,
        ),
    )

    projection = build_operator_status(blocked)

    assert projection.runtime_apply_reason == (
        "strict_package_validation_failed"
    )
    assert projection.technical_status == "INVALID_PACKAGE"


def test_pre_run_gameplay_marker_is_explicit_and_status_neutral() -> None:
    base = _allowed_inputs()
    with_pre_run = freeze_operator_summary_inputs(
        deck_name="Status",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        pre_run_closure_report={
            "pre_run_contract_status": "complete",
            "strategy_authority_status": "strong",
        },
    )

    assert build_operator_status(with_pre_run) == build_operator_status(base)
    summary = build_operator_summary_from_inputs(with_pre_run)
    assert summary["gameplay_quality"] == "OUT_OF_SCOPE_ASSUMED_EXTERNAL"


def test_status_ignores_builtin_and_authority_descriptor_poison() -> None:
    script = textwrap.dedent(
        """
        import builtins

        from hsconfig.operator_summary import (
            build_operator_summary_from_inputs,
        )
        from hsconfig.operator_summary_inputs import (
            OperatorAuthorityInputs,
            freeze_operator_summary_inputs,
        )

        inputs = freeze_operator_summary_inputs(
            technical_validation={
                "status": "failed",
                "errors": ["expected_failure"],
            }
        )
        expected = build_operator_summary_from_inputs(inputs)
        strict_slot = OperatorAuthorityInputs.__dict__[
            "strict_package_validation"
        ]
        original_dict = builtins.dict
        original_tuple = builtins.tuple
        try:
            OperatorAuthorityInputs.strict_package_validation = False
            builtins.dict = lambda *args, **kwargs: {"poisoned": True}
            builtins.tuple = lambda *args, **kwargs: ("poisoned",)
            actual = build_operator_summary_from_inputs(inputs)
            assert actual == expected
        finally:
            builtins.dict = original_dict
            builtins.tuple = original_tuple
            OperatorAuthorityInputs.strict_package_validation = strict_slot
        """
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, (
        completed.stdout + completed.stderr
    )


def test_public_status_binding_has_no_writable_closure_or_installer() -> None:
    for projection in (
        build_operator_status,
        determine_operator_status,
    ):
        assert not isinstance(projection, FunctionType)
        for attribute in (
            "__closure__",
            "__defaults__",
            "__kwdefaults__",
            "args",
            "func",
            "keywords",
        ):
            assert getattr(projection, attribute, None) is None
        with pytest.raises(AttributeError):
            projection._GuardedOperatorCallable__state
    assert not hasattr(
        operator_status_module,
        "_install_operator_status_kernel",
    )


def test_status_primary_kernel_tamper_recovers_exactly_from_backup() -> None:
    inputs = _allowed_inputs()
    inputs = replace(
        inputs,
        authority=replace(
            inputs.authority,
            strict_package_validation=False,
        ),
    )
    expected = _canonical_status_bytes(inputs)
    state = _guarded_state(build_operator_status)
    primary_kernel = state[2][0]
    original_decider = primary_kernel.__globals__[
        "_BUILD_APPLY_DECISION"
    ]
    primary_kernel.__globals__["_BUILD_APPLY_DECISION"] = (
        lambda _facts: SimpleNamespace(
            allowed=True,
            reasons=(),
            policy="POISONED_ALLOWED",
            mode="load_safe_apply",
        )
    )
    try:
        actual = _canonical_status_bytes(inputs)
    finally:
        primary_kernel.__globals__[
            "_BUILD_APPLY_DECISION"
        ] = original_decider

    assert actual == expected


def test_status_primary_projection_class_tamper_uses_backup() -> None:
    inputs = _allowed_inputs()
    inputs = replace(
        inputs,
        authority=replace(
            inputs.authority,
            strict_package_validation=False,
        ),
    )
    expected = _canonical_status_bytes(inputs)
    state = _guarded_state(build_operator_status)
    primary_kernel = state[2][0]
    projection_type = primary_kernel.__globals__[
        "OperatorStatusProjection"
    ]
    original_init = projection_type.__dict__["__init__"]

    def forged_init(instance, *args, **kwargs) -> None:
        original_init(instance, *args, **kwargs)
        object.__setattr__(
            instance,
            "technical_status",
            "VALID_PACKAGE",
        )
        object.__setattr__(
            instance,
            "runtime_apply_allowed",
            True,
        )
        object.__setattr__(
            instance,
            "next_action",
            "READY_TO_APPLY_WITH_WARNINGS",
        )

    projection_type.__init__ = forged_init
    try:
        actual = _canonical_status_bytes(inputs)
    finally:
        projection_type.__init__ = original_init

    assert actual == expected


def test_status_primary_code_tamper_uses_backup() -> None:
    inputs = _allowed_inputs()
    inputs = replace(
        inputs,
        authority=replace(
            inputs.authority,
            strict_package_validation=False,
        ),
    )
    expected = _canonical_status_bytes(inputs)
    state = _guarded_state(build_operator_status)
    primary_kernel = state[2][0]
    original_code = primary_kernel.__code__
    forged_projection = replace(
        build_operator_status(inputs),
        technical_status="VALID_PACKAGE",
        runtime_apply_allowed=True,
        next_action="READY_TO_APPLY_WITH_WARNINGS",
    )

    def forged_status(_inputs):
        return _ROUND4_FORGED_STATUS  # noqa: F821

    primary_kernel.__globals__[
        "_ROUND4_FORGED_STATUS"
    ] = forged_projection
    primary_kernel.__code__ = forged_status.__code__
    try:
        actual = _canonical_status_bytes(inputs)
    finally:
        primary_kernel.__code__ = original_code
        del primary_kernel.__globals__["_ROUND4_FORGED_STATUS"]

    assert actual == expected


def test_primary_registry_instance_change_uses_backup() -> None:
    inputs = _allowed_inputs()
    expected = _canonical_summary_bytes(inputs)
    evaluator = _primary_summary_evaluator()
    report_spec = evaluator.__globals__["report_spec"]
    report_registry = report_spec.__globals__["REPORT_REGISTRY"]
    spec = report_registry["reports/operator_summary.json"]
    original_ownership = spec.ownership
    object.__setattr__(
        spec,
        "ownership",
        "poisoned_primary_ownership",
    )
    try:
        actual = _canonical_summary_bytes(inputs)
    finally:
        object.__setattr__(
            spec,
            "ownership",
            original_ownership,
        )

    assert actual == expected


def test_primary_profile_instance_change_uses_backup() -> None:
    inputs = _allowed_inputs(strong=True)
    expected = _canonical_summary_bytes(inputs)
    evaluator = _primary_summary_evaluator()
    evaluate_profile = evaluator.__globals__[
        "evaluate_closure_profile"
    ]
    requirements = evaluate_profile.__globals__[
        "PROFILE_REQUIREMENTS"
    ]
    requirement = requirements["generic_no_block"]
    original_surfaces = requirement.required_surfaces
    object.__setattr__(
        requirement,
        "required_surfaces",
        ("Poison.json",),
    )
    try:
        actual = _canonical_summary_bytes(inputs)
    finally:
        object.__setattr__(
            requirement,
            "required_surfaces",
            original_surfaces,
        )

    assert actual == expected


def test_public_input_descriptor_rebind_does_not_disable_both_paths() -> None:
    inputs = _allowed_inputs()
    expected = _canonical_summary_bytes(inputs)
    original_descriptor = OperatorSummaryInputs.__dict__[
        "legacy_kwargs"
    ]
    OperatorSummaryInputs.legacy_kwargs = None
    try:
        actual = _canonical_summary_bytes(inputs)
    finally:
        OperatorSummaryInputs.legacy_kwargs = original_descriptor

    assert actual == expected
