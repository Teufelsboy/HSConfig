"""Deterministic non-authoritative operator diagnostics."""

from __future__ import annotations

import json
from typing import Any

from hsconfig.operator_summary import (
    _freeze_operator_function_graph,
    _guard_operator_callable,
)
from hsconfig.operator_summary_inputs import (
    OperatorDiagnosticInputs,
    OperatorSummaryInputs,
)


_SUMMARY_DIAGNOSTICS = OperatorSummaryInputs.__dict__["diagnostics"]
_DIAGNOSTIC_REASON_ROWS = OperatorDiagnosticInputs.__dict__["reason_rows"]


def _build_operator_diagnostics_unsealed(
    inputs: OperatorSummaryInputs,
) -> tuple[dict[str, Any], ...]:
    """Return stable explanatory rows with no gate authority."""

    diagnostics = _SUMMARY_DIAGNOSTICS.__get__(
        inputs,
        OperatorSummaryInputs,
    )
    rows = [
        {
            **_plain_mapping(row),
            "gate_impact": "diagnostic_only",
            "apply_blocking": False,
        }
        for row in _DIAGNOSTIC_REASON_ROWS.__get__(
            diagnostics,
            OperatorDiagnosticInputs,
        )
    ]
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                str(row.get("reason_code", "")),
                str(row.get("source", "")),
                json.dumps(
                    row.get("details", {}),
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            ),
        )
    )


def _plain_mapping(value: Any) -> dict[str, Any]:
    return {
        str(key): _plain_value(nested)
        for key, nested in value.items()
    }


def _plain_value(value: Any) -> Any:
    value_type = value.__class__
    if value_type.__name__ == "mappingproxy" or value_type is dict:
        return _plain_mapping(value)
    if value_type is tuple or value_type is list:
        return [_plain_value(item) for item in value]
    if value_type is frozenset or value_type is set:
        return sorted(_plain_value(item) for item in value)
    return value


(_operator_diagnostics_primary,) = _freeze_operator_function_graph(
    (_build_operator_diagnostics_unsealed,)
)
(_operator_diagnostics_backup,) = _freeze_operator_function_graph(
    (_build_operator_diagnostics_unsealed,)
)


def _invoke_diagnostic_projection(
    kernel: Any,
    inputs: OperatorSummaryInputs,
) -> tuple[dict[str, Any], ...]:
    """Return diagnostics through the definitions-bound pure kernel."""

    return kernel(inputs)


(_diagnostic_invoker_primary,) = _freeze_operator_function_graph(
    (_invoke_diagnostic_projection,)
)
(_diagnostic_invoker_backup,) = _freeze_operator_function_graph(
    (_invoke_diagnostic_projection,)
)
build_operator_diagnostics = _guard_operator_callable(
    primary=_diagnostic_invoker_primary,
    backup=_diagnostic_invoker_backup,
    primary_bound=(_operator_diagnostics_primary,),
    backup_bound=(_operator_diagnostics_backup,),
    name="build_operator_diagnostics",
    signature_source=_build_operator_diagnostics_unsealed,
)
del (
    _operator_diagnostics_primary,
    _operator_diagnostics_backup,
    _diagnostic_invoker_primary,
    _diagnostic_invoker_backup,
)

__all__ = ("build_operator_diagnostics",)
