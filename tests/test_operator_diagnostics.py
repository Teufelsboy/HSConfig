from __future__ import annotations

from dataclasses import fields, replace
import json
from types import FunctionType, SimpleNamespace

import pytest

from hsconfig.operator_diagnostics import build_operator_diagnostics
from hsconfig.operator_status import build_operator_status
from hsconfig.operator_summary import (
    build_operator_summary_from_inputs,
    refresh_generated_file_accounting,
)
from hsconfig.operator_summary_inputs import freeze_operator_summary_inputs
from hsconfig.operator_summary_inputs import OperatorDiagnosticInputs


def _diagnostic_inputs():
    return freeze_operator_summary_inputs(
        deck_name="Diagnostics",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        unsupported_conditions=[
            {"reason": "z_reason", "card_id": "Z"},
            {"reason": "a_reason", "card_id": "A"},
        ],
        mechanic_drift_report={
            "unknown_mechanics": ["future_mechanic"],
        },
    )


def _guarded_state(callable_):
    """Read opaque carrier state only for controlled fault injection."""

    return object.__getattribute__(
        callable_,
        "_GuardedOperatorCallable__state",
    )


def _canonical_diagnostic_bytes(inputs) -> bytes:
    return json.dumps(
        build_operator_diagnostics(inputs),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def test_diagnostics_are_stably_sorted_and_diagnostic_only() -> None:
    rows = build_operator_diagnostics(_diagnostic_inputs())

    assert tuple(row["reason_code"] for row in rows) == tuple(
        sorted(row["reason_code"] for row in rows)
    )
    assert rows
    assert all(row["gate_impact"] == "diagnostic_only" for row in rows)
    assert all(row["apply_blocking"] is False for row in rows)


def test_diagnostic_mutation_cannot_change_apply_core() -> None:
    inputs = _diagnostic_inputs()
    expected = build_operator_status(inputs)
    mutated = replace(
        inputs,
        diagnostics=replace(
            inputs.diagnostics,
            reason_rows=(
                {
                    "reason_code": "forged",
                    "gate_impact": "gate",
                    "apply_blocking": True,
                },
            ),
        ),
    )

    actual = build_operator_status(mutated)

    assert (
        actual.runtime_apply_allowed,
        actual.runtime_apply_mode,
        actual.runtime_apply_reason,
    ) == (
        expected.runtime_apply_allowed,
        expected.runtime_apply_mode,
        expected.runtime_apply_reason,
    )


def test_every_diagnostic_field_is_apply_core_neutral() -> None:
    inputs = _diagnostic_inputs()
    expected = build_operator_status(inputs)
    core = (
        expected.runtime_apply_allowed,
        expected.runtime_apply_mode,
        expected.runtime_apply_reason,
    )

    for field in fields(inputs.diagnostics):
        current = getattr(inputs.diagnostics, field.name)
        if isinstance(current, tuple):
            poisoned = ()
        else:
            poisoned = {}
        mutated = replace(
            inputs,
            diagnostics=replace(
                inputs.diagnostics,
                **{field.name: poisoned},
            ),
        )
        actual = build_operator_status(mutated)
        assert (
            actual.runtime_apply_allowed,
            actual.runtime_apply_mode,
            actual.runtime_apply_reason,
        ) == core, field.name


def test_nested_diagnostic_detail_order_is_canonical() -> None:
    first = freeze_operator_summary_inputs(
        technical_validation={"status": "passed", "errors": []},
        unsupported_conditions=[
            {
                "reason": "same",
                "details": {"b": 2, "a": 1},
            }
        ],
    )
    second = freeze_operator_summary_inputs(
        technical_validation={"errors": [], "status": "passed"},
        unsupported_conditions=[
            {
                "details": {"a": 1, "b": 2},
                "reason": "same",
            }
        ],
    )

    assert build_operator_diagnostics(first) == build_operator_diagnostics(
        second
    )


def test_diagnostics_ignore_origin_descriptor_and_json_poison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = _diagnostic_inputs()
    expected = build_operator_diagnostics(inputs)
    reason_rows_slot = OperatorDiagnosticInputs.__dict__["reason_rows"]
    try:
        monkeypatch.setattr(
            OperatorDiagnosticInputs,
            "reason_rows",
            (),
        )
        monkeypatch.setattr(
            json,
            "dumps",
            lambda *args, **kwargs: "poisoned",
        )
        assert build_operator_diagnostics(inputs) == expected
    finally:
        monkeypatch.setattr(
            OperatorDiagnosticInputs,
            "reason_rows",
            reason_rows_slot,
        )


def test_diagnostic_primary_binding_tamper_recovers_exactly_from_backup() -> None:
    assert not isinstance(build_operator_diagnostics, FunctionType)
    for attribute in (
        "__closure__",
        "__defaults__",
        "__kwdefaults__",
        "args",
        "func",
        "keywords",
    ):
        assert getattr(
            build_operator_diagnostics,
            attribute,
            None,
        ) is None
    with pytest.raises(AttributeError):
        build_operator_diagnostics._GuardedOperatorCallable__state

    inputs = _diagnostic_inputs()
    expected = _canonical_diagnostic_bytes(inputs)
    state = _guarded_state(build_operator_diagnostics)
    primary_kernel = state[2][0]
    original_json = primary_kernel.__globals__["json"]
    primary_kernel.__globals__["json"] = SimpleNamespace(
        dumps=lambda *args, **kwargs: "poisoned",
    )
    try:
        actual = _canonical_diagnostic_bytes(inputs)
    finally:
        primary_kernel.__globals__["json"] = original_json

    assert actual == expected


def test_refresh_generated_file_accounting_is_status_neutral() -> None:
    inputs = _diagnostic_inputs()
    before = build_operator_summary_from_inputs(inputs)

    after = refresh_generated_file_accounting(
        before,
        generated_files=["reports/z.json", "reports/a.json"],
        output_ownership_manifest={
            "summary": {
                "generated_file_count": 2,
                "unclassified_file_count": 0,
                "gate_count": 1,
            }
        },
    )

    for field in (
        "technical_status",
        "next_action",
        "apply_policy",
        "runtime_apply_allowed",
        "runtime_apply_mode",
        "runtime_apply_reason",
    ):
        assert after[field] == before[field]
    assert after["generated_files"] == [
        "reports/a.json",
        "reports/z.json",
    ]
