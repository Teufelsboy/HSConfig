from __future__ import annotations

import ast
from copy import deepcopy
import operator
from typing import Any


TOP_LEVEL_KEYS = {"GameCardId", "ConfigComment"}
NUMERIC_OPERATORS = {
    ast.Add: operator.add,
    ast.Div: operator.truediv,
    ast.Mult: operator.mul,
    ast.Sub: operator.sub,
}


def compile_globalvalues(
    default_values: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
    *,
    baseline: dict[str, Any] | None = None,
    posture: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if default_values is None:
        default_values = baseline
    if default_values is None:
        raise ValueError("default_values is required")
    contract = contract or {"aggression_profile": posture or {}}
    aggression_profile = contract.get("aggression_profile", posture or {})

    config = {
        key: deepcopy(value) if key in TOP_LEVEL_KEYS else _values_block(value)
        for key, value in default_values.items()
    }
    config["GameCardId"] = "GlobalValues"
    config.setdefault("ConfigComment", "Generated GlobalValues")

    changed_keys: list[str] = []
    unchanged_keys: list[str] = []
    key_profiles: dict[str, dict[str, Any]] = {}
    overlays = dict(aggression_profile.get("global_value_overlays", {}))
    overlays.update(aggression_profile.get("mechanic_priorities", {}))

    for key in default_values:
        if key in TOP_LEVEL_KEYS:
            key_profiles[key] = {
                "category": "metadata",
                "decision": "baseline_confirmed",
                "reason": "Required top-level metadata key.",
            }
            unchanged_keys.append(key)
            continue

        before = _first_value(config[key])
        decision = {
            "category": _classify_key(key),
            "baseline_value": before,
            "decision": "baseline_confirmed",
            "reason": "No deck-specific overlay required.",
        }
        overlay = _overlay_for_key(key, aggression_profile, overlays)
        if overlay is not None:
            after = _apply_overlay(config[key], overlay)
            decision.update(
                {
                    "decision": "overlay_changed" if after != before else "baseline_confirmed",
                    "new_value": after,
                    "reason": _overlay_reason(key, overlay),
                }
            )
        after = _first_value(config[key])
        if after != before:
            changed_keys.append(key)
        else:
            unchanged_keys.append(key)
        key_profiles[key] = decision

    return {
        "config": config,
        "profile": {
            "key_count": len(default_values),
            "changed_keys": changed_keys,
            "unchanged_keys": unchanged_keys,
            "keys": key_profiles,
        },
    }


def _values_block(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("values"), list):
        block = deepcopy(value)
        if not block["values"]:
            block["values"].append({"condition": "*", "value": "0"})
        return block
    if isinstance(value, dict):
        return {"values": [{"condition": value.get("condition", "*"), "value": str(value.get("value", "0"))}]}
    return {"values": [{"condition": "*", "value": str(value)}]}


def _first_value(block: dict[str, Any]) -> str | None:
    values = block.get("values", [])
    if not values:
        return None
    return str(values[0].get("value"))


def _set_first_value(block: dict[str, Any], value: str) -> str:
    if not block.get("values"):
        block["values"] = [{"condition": "*", "value": value}]
    else:
        block["values"][0]["value"] = value
    return value


def _overlay_for_key(
    key: str,
    aggression_profile: dict[str, Any],
    overlays: dict[str, Any],
) -> str | None:
    speed = str(aggression_profile.get("speed", "balanced")).lower()
    if key == "FirstTurnValueWeight" and speed in {"aggro", "aggressive", "tempo"}:
        return "set:0.75"
    if key == "SecondTurnValueWeight" and speed in {"aggro", "aggressive", "tempo"}:
        return "set:0.25"
    if key in overlays:
        return str(overlays[key])
    return None


def _apply_overlay(block: dict[str, Any], overlay: str) -> str:
    before = _first_value(block)
    if overlay.startswith("set:"):
        return _set_first_value(block, overlay.removeprefix("set:"))
    if overlay == "increase":
        return _set_first_value(block, _scale_numeric_string(before, 1.15))
    if overlay == "decrease":
        return _set_first_value(block, _scale_numeric_string(before, 0.85))
    return _set_first_value(block, overlay)


def _scale_numeric_string(value: str | None, multiplier: float) -> str:
    if value is None:
        return "1"
    try:
        scaled = _numeric_value(value) * multiplier
    except ValueError:
        return value
    return f"{scaled:.2f}"


def _numeric_value(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        pass
    try:
        return float(_eval_numeric_expression(ast.parse(value, mode="eval").body))
    except (SyntaxError, ValueError, ZeroDivisionError):
        raise ValueError(value) from None


def _eval_numeric_expression(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_numeric_expression(node.operand)
    if isinstance(node, ast.BinOp):
        operator_fn = NUMERIC_OPERATORS.get(type(node.op))
        if operator_fn is None:
            raise ValueError("unsupported numeric operator")
        return float(
            operator_fn(
                _eval_numeric_expression(node.left),
                _eval_numeric_expression(node.right),
            )
        )
    raise ValueError("unsupported numeric expression")


def _classify_key(key: str) -> str:
    lowered = key.lower()
    if "turnvalueweight" in lowered:
        return "turn_weight"
    if "weapon" in lowered:
        return "weapon"
    if "secret" in lowered:
        return "secret"
    if "hero" in lowered:
        return "hero"
    if "deck" in lowered:
        return "deck"
    return "mechanic_modifier"


def _overlay_reason(key: str, overlay: str) -> str:
    if overlay.startswith("set:") and "turnvalueweight" in key.lower():
        return "Aggressive profile adjusts early turn weighting."
    if overlay == "increase":
        return "Aggressive gameplan prioritizes this mechanic."
    if overlay == "decrease":
        return "Aggressive gameplan deprioritizes this defensive mechanic."
    return "Deck-specific GlobalValues overlay."
