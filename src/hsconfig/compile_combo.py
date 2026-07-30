from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from hsconfig.package_domain import (
    ComboDecisionModel,
    ComboPlanModel,
    ComboSuppressionModel,
    ComboTiming,
)


SUPPORTED_OPERATORS = frozenset(timing.operator for timing in ComboTiming)



def compile_combo(
    contract: Mapping[str, Any] | ComboPlanModel | None = None,
    *,
    deck_name: str | None = None,
    sequences: (
        list[Mapping[str, Any] | ComboDecisionModel]
        | tuple[Mapping[str, Any] | ComboDecisionModel, ...]
        | None
    ) = None,
) -> dict[str, Any] | None:
    contract_deck_name = (
        str(contract.get("deck_name", "Deck"))
        if isinstance(contract, Mapping)
        else "Deck"
    )
    deck_name = deck_name or contract_deck_name
    plan: ComboPlanModel
    if sequences is not None:
        plan = _plan_from_legacy_rows(sequences)
    elif isinstance(contract, ComboPlanModel):
        plan = contract
    elif isinstance(contract, Mapping):
        plan = _plan_from_legacy_report(contract)
    else:
        plan = ComboPlanModel(decisions=(), suppressions=())
    if not plan.decisions:
        return None

    values: list[dict[str, str]] = []
    for decision in plan.decisions:
        values.append(
            {
                "comment": f"{deck_name}: {decision.rule_id}",
                "condition": decision.condition,
                "combo": decision.operator.join(decision.cards),
                "value": decision.operator.join(decision.values),
            }
        )
    return {
        "GameCardId": "Combo",
        "ConfigComment": f"{deck_name} generated combos",
        "ComboList": {"values": values},
    }


def _plan_from_legacy_report(
    report: Mapping[str, Any],
) -> ComboPlanModel:
    suppressions = _legacy_rows(report.get("suppressed", ()))
    return ComboPlanModel(
        decisions=_legacy_decisions(report.get("combos", ())),
        suppressions=tuple(
            ComboSuppressionModel.from_report_row(row)
            for row in suppressions
        ),
    )


def _plan_from_legacy_rows(
    rows: (
        list[Mapping[str, Any] | ComboDecisionModel]
        | tuple[Mapping[str, Any] | ComboDecisionModel, ...]
    ),
) -> ComboPlanModel:
    return ComboPlanModel(
        decisions=_legacy_decisions(rows),
        suppressions=(),
    )


def _legacy_decisions(
    rows: Any,
) -> tuple[ComboDecisionModel, ...]:
    decisions: list[ComboDecisionModel] = []
    for sequence in _legacy_rows(rows):
        if isinstance(sequence, ComboDecisionModel):
            decisions.append(sequence)
            continue
        rule_id = str(sequence.get("rule_id", "combo_sequence"))
        try:
            decisions.append(ComboDecisionModel.from_plan_row(sequence))
        except (TypeError, ValueError) as error:
            raise ValueError(f"Invalid combo sequence {rule_id}") from error
    return tuple(decisions)


def _legacy_rows(
    rows: Any,
) -> tuple[Mapping[str, Any] | ComboDecisionModel, ...]:
    if not isinstance(rows, (list, tuple)):
        raise ValueError("Invalid combo sequence collection")
    frozen = tuple(rows)
    if any(
        not isinstance(row, (Mapping, ComboDecisionModel))
        for row in frozen
    ):
        raise ValueError("Invalid combo sequence collection")
    return frozen
