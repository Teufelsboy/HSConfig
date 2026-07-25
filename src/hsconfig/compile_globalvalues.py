from __future__ import annotations

import ast
from copy import deepcopy
import operator
from typing import Any

from hsconfig.globalvalues_key_authority import authority_for_key


TOP_LEVEL_KEYS = {"GameCardId", "ConfigComment"}
KNOWN_GENERATED_OVERLAY_DEFAULTS = {
    "MyHeroPowerValue": {"values": [{"condition": "*", "value": "1.00"}]},
    "EnemyHeroPowerValue": {"values": [{"condition": "*", "value": "1.00"}]},
    "MyWeaponValue": {"values": [{"condition": "*", "value": "1.00"}]},
    "EnemyWeaponValue": {"values": [{"condition": "*", "value": "1.00"}]},
}
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

    authority_matrix = contract.get("global_values_authority_matrix", {})
    has_authority_overlays = (
        isinstance(authority_matrix, dict)
        and isinstance(authority_matrix.get("allowed_step1_overlays"), list)
    )
    key_authorities = _key_authorities_from_matrix(authority_matrix)
    if has_authority_overlays:
        allowed_rows = [
            row
            for row in authority_matrix.get("allowed_step1_overlays", [])
            if isinstance(row, dict) and row.get("key") not in {None, "baseline"}
        ]
        overlays = {str(row["key"]): _overlay_from_authority_row(row) for row in allowed_rows}
        overlay_reasons = {
            str(row["key"]): str(row["reason"])
            for row in allowed_rows
            if row.get("reason") is not None
        }
    else:
        overlays = dict(aggression_profile.get("global_value_overlays", {}))
        overlays.update(aggression_profile.get("mechanic_priorities", {}))
        overlay_reasons = dict(aggression_profile.get("global_value_overlay_reasons", {}))
    generated_overlay_keys = sorted(
        key
        for key in overlays
        if key not in default_values and key in KNOWN_GENERATED_OVERLAY_DEFAULTS
    )
    expected_overlay_keys = sorted(
        key for key in overlays if key not in TOP_LEVEL_KEYS
    )

    config = {
        key: deepcopy(value) if key in TOP_LEVEL_KEYS else _values_block(value)
        for key, value in default_values.items()
    }
    for key in generated_overlay_keys:
        config[key] = _values_block(KNOWN_GENERATED_OVERLAY_DEFAULTS[key])
    config["GameCardId"] = "GlobalValues"
    config.setdefault("ConfigComment", "Generated GlobalValues")

    changed_keys: list[str] = []
    unchanged_keys: list[str] = []
    key_profiles: dict[str, dict[str, Any]] = {}
    profile_keys = [*default_values, *generated_overlay_keys]

    for key in profile_keys:
        key_authority = key_authorities.get(key, authority_for_key(key))
        if key in TOP_LEVEL_KEYS:
            key_profiles[key] = {
                "category": "metadata",
                "authority_category": key_authority["category"],
                "board_value_component": key_authority["board_value_component"],
                "decision": "baseline_confirmed",
                "status": "baseline_confirmed",
                "reason": "Required top-level metadata key.",
            }
            unchanged_keys.append(key)
            continue

        before = _first_value(config[key])
        decision = {
            "category": _classify_key(key),
            "authority_category": key_authority["category"],
            "board_value_component": key_authority["board_value_component"],
            "baseline_value": before,
            "decision": "baseline_confirmed",
            "status": "baseline_confirmed",
            "reason": "No deck-specific overlay required.",
        }
        if key in generated_overlay_keys:
            decision["generated_overlay_key"] = True
            decision["reason"] = "Known deck-specific overlay key was absent from runtime default."
        overlay = _overlay_for_key(
            key,
            aggression_profile,
            overlays,
            allow_speed_fallback=not has_authority_overlays,
        )
        if overlay is not None:
            after = _apply_overlay(config[key], overlay)
            decision.update(
                {
                    "decision": "overlay_changed" if after != before else "baseline_confirmed",
                    "status": "overlay_changed" if after != before else "baseline_confirmed",
                    "new_value": after,
                    "reason": overlay_reasons.get(key, _overlay_reason(key, overlay)),
                }
            )
        after = _first_value(config[key])
        if after != before:
            changed_keys.append(key)
        else:
            unchanged_keys.append(key)
        key_profiles[key] = decision

    status = "overlay_changed" if changed_keys else "baseline_confirmed"
    summary = {
        "status": status,
        "runtime_permission_impact": "none",
        "key_count": len(profile_keys),
        "changed_key_count": len(changed_keys),
        "unchanged_key_count": len(unchanged_keys),
        "expected_overlay_key_count": len(expected_overlay_keys),
        "generated_overlay_key_count": len(generated_overlay_keys),
        "all_baseline_keys_accounted_for": True,
    }

    return {
        "config": config,
        "profile": {
            "schema_version": 1,
            "status": status,
            "runtime_permission_impact": "none",
            "summary": summary,
            "key_count": len(profile_keys),
            "generated_overlay_keys": generated_overlay_keys,
            "expected_overlay_keys": expected_overlay_keys,
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
    *,
    allow_speed_fallback: bool = True,
) -> str | None:
    speed = str(aggression_profile.get("speed", "balanced")).lower()
    if allow_speed_fallback:
        if key == "FirstTurnValueWeight" and speed in {"aggro", "aggressive", "tempo"}:
            return "set:0.75"
        if key == "SecondTurnValueWeight" and speed in {"aggro", "aggressive", "tempo"}:
            return "set:0.25"
    if key in overlays:
        return str(overlays[key])
    return None


def _overlay_from_authority_row(row: dict[str, Any]) -> str:
    if row.get("overlay") is not None:
        return str(row["overlay"])
    operation = str(row.get("operation", "none"))
    if operation == "set":
        return f"set:{row.get('value')}"
    if operation in {"increase", "decrease"}:
        return operation
    return str(row.get("value", "none"))


def _key_authorities_from_matrix(authority_matrix: Any) -> dict[str, dict[str, str]]:
    if not isinstance(authority_matrix, dict):
        return {}
    key_authorities: dict[str, dict[str, str]] = {}
    for section in ("allowed_step1_overlays", "blocked_until_runtime_evidence"):
        rows = authority_matrix.get(section, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict) or row.get("key") is None:
                continue
            key = str(row["key"])
            key_authority = row.get("key_authority")
            fallback = authority_for_key(key)
            if isinstance(key_authority, dict):
                key_authorities[key] = {
                    "key": str(key_authority.get("key", key)),
                    "category": str(key_authority.get("category", fallback["category"])),
                    "board_value_component": str(
                        key_authority.get(
                            "board_value_component",
                            fallback["board_value_component"],
                        )
                    ),
                }
            else:
                key_authorities[key] = fallback
    return key_authorities


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
