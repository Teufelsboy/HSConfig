"""Pure Mulligan runtime compiler for the typed plan boundary."""

from __future__ import annotations

import json
from typing import Any

from hsconfig.package_domain import MulliganPlanModel


def compile_mulligan(plan: MulliganPlanModel) -> dict[str, Any]:
    """Serialize an authorized plan to HearthRanger's runtime shape."""

    if not isinstance(plan, MulliganPlanModel):
        raise TypeError("mulligan_plan_model_required")

    values: list[dict[str, Any]] = []
    for index, rule in enumerate(plan.rules, start=1):
        selector = json.loads(rule.selector_canonical_json)
        condition = json.loads(rule.condition_canonical_json)
        if rule.selector_kind == "wildcard" or selector == "*":
            raise ValueError("mulligan_wildcard_rule_forbidden")
        rule_id = rule.claim_id or (
            f"{rule.card_id}_mulligan_{index}"
        )
        values.append(
            {
                "comment": f"{plan.deck_name}: {rule_id}",
                "mulligan": selector,
                "condition": condition,
                "value": rule.action,
            }
        )

    return {
        "GameCardId": "Mulligan",
        "ConfigComment": (
            f"{plan.deck_name} generated mulligan rules"
        ),
        "Mulligan": {"values": values},
    }
