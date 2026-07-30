from __future__ import annotations

import ast
from collections.abc import Sequence
from copy import deepcopy
import json
import math
import operator
from typing import Any, Mapping

from hsconfig.globalvalues_key_authority import (
    STEP1_POSTURE_KEYS,
    authority_for_key,
)
from hsconfig.package_domain import (
    GlobalValueDecisionKind,
    GlobalValuesDecisionLedger,
    deep_freeze_definition,
    materialize_definition,
)


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
TOP_LEVEL_KEYS = deep_freeze_definition(TOP_LEVEL_KEYS)
KNOWN_GENERATED_OVERLAY_DEFAULTS = deep_freeze_definition(
    KNOWN_GENERATED_OVERLAY_DEFAULTS
)
NUMERIC_OPERATORS = deep_freeze_definition(NUMERIC_OPERATORS)


def compile_globalvalues(
    default_values: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
    *,
    baseline: dict[str, Any] | None = None,
    posture: dict[str, Any] | None = None,
    decision_ledger: GlobalValuesDecisionLedger | None = None,
) -> dict[str, Any]:
    if default_values is None:
        default_values = baseline
    if default_values is None:
        raise ValueError("default_values is required")
    contract = contract or {"aggression_profile": posture or {}}
    aggression_profile = contract.get("aggression_profile", posture or {})

    has_authority_overlays = "global_values_authority_matrix" in contract
    authority_matrix = contract.get("global_values_authority_matrix")
    if decision_ledger is not None and not has_authority_overlays:
        raise ValueError(
            "globalvalues_decision_ledger_authority_matrix_required"
        )
    allowed_rows: list[dict[str, Any]] = []
    if has_authority_overlays:
        allowed_rows = validated_globalvalues_authority_rows(authority_matrix)
    if decision_ledger is not None:
        _require_globalvalues_decision_ledger_authority_parity(
            default_values=default_values,
            allowed_rows=allowed_rows,
            decision_ledger=decision_ledger,
        )
    key_authorities = _key_authorities_from_matrix(authority_matrix)
    if has_authority_overlays:
        overlays = {str(row["key"]): _overlay_from_authority_row(row) for row in allowed_rows}
        overlay_reasons = {
            str(row["key"]): str(row["reason"])
            for row in allowed_rows
            if row.get("reason") is not None
        }
        authority_rows = {str(row["key"]): row for row in allowed_rows}
    else:
        overlays = dict(aggression_profile.get("global_value_overlays", {}))
        overlays.update(aggression_profile.get("mechanic_priorities", {}))
        overlay_reasons = dict(aggression_profile.get("global_value_overlay_reasons", {}))
        authority_rows = {}
    generated_overlay_candidates = set(overlays)
    generated_overlay_keys = (
        []
        if decision_ledger is not None
        else sorted(
            key
            for key in generated_overlay_candidates
            if key not in default_values
            and key in KNOWN_GENERATED_OVERLAY_DEFAULTS
        )
    )
    authorized_baseline_overlay_keys = sorted(
        key
        for key in overlays
        if key not in TOP_LEVEL_KEYS and key in default_values
    )
    expected_overlay_keys = sorted(
        key
        for key in overlays
        if key not in TOP_LEVEL_KEYS and key not in default_values
    )
    missing_overlay_keys = sorted(
        key
        for key in expected_overlay_keys
        if key not in default_values and key not in generated_overlay_keys
    )
    all_expected_overlay_keys_accounted_for = not missing_overlay_keys

    if decision_ledger is None:
        config = {
            key: deepcopy(value) if key in TOP_LEVEL_KEYS else _values_block(value)
            for key, value in default_values.items()
        }
        for key in generated_overlay_keys:
            config[key] = _values_block(KNOWN_GENERATED_OVERLAY_DEFAULTS[key])
        config["GameCardId"] = "GlobalValues"
        config.setdefault("ConfigComment", "Generated GlobalValues")
    else:
        config = {
            decision.key: json.loads(decision.emitted_canonical_json)
            for decision in decision_ledger.decisions
        }
        if set(config) != set(default_values):
            raise ValueError("globalvalues_decision_ledger_baseline_keys_mismatch")

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

        before = _first_value(
            _values_block(default_values[key])
            if key in default_values
            else config[key]
        )
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
            after = (
                _apply_overlay(config[key], overlay)
                if decision_ledger is None
                else _first_value(config[key])
            )
            decision.update(
                {
                    "decision": "overlay_changed" if after != before else "baseline_confirmed",
                    "status": "overlay_changed" if after != before else "baseline_confirmed",
                    "new_value": after,
                    "reason": overlay_reasons.get(key, _overlay_reason(key, overlay)),
                }
            )
            authority_row = authority_rows.get(key)
            if authority_row is not None:
                if authority_row.get("claim_id"):
                    decision["claim_id"] = str(authority_row["claim_id"])
                claim_refs = authority_row.get("claim_refs")
                if isinstance(claim_refs, list):
                    decision["claim_refs"] = [
                        str(claim_ref) for claim_ref in claim_refs
                    ]
        after = _first_value(config[key])
        if after != before:
            changed_keys.append(key)
        else:
            unchanged_keys.append(key)
        key_profiles[key] = decision

    changed_keys.sort()
    unchanged_keys.sort()
    emitted_overlay_keys = sorted(
        key for key in expected_overlay_keys if key in config
    )
    authority_parity = {
        "authorized_overlay_keys": expected_overlay_keys,
        "emitted_overlay_keys": emitted_overlay_keys,
        "status": (
            "matched"
            if expected_overlay_keys == emitted_overlay_keys
            else "mismatch"
        ),
    }
    emitted_baseline_overlay_keys = sorted(
        key for key in authorized_baseline_overlay_keys if key in config
    )
    baseline_overlay_parity = {
        "authorized_overlay_keys": authorized_baseline_overlay_keys,
        "emitted_overlay_keys": emitted_baseline_overlay_keys,
        "status": (
            "matched"
            if authorized_baseline_overlay_keys == emitted_baseline_overlay_keys
            else "mismatch"
        ),
    }
    status = (
        "attention"
        if (
            missing_overlay_keys
            or authority_parity["status"] == "mismatch"
            or baseline_overlay_parity["status"] == "mismatch"
        )
        else "overlay_changed"
        if changed_keys
        else "baseline_confirmed"
    )
    summary = {
        "status": status,
        "runtime_permission_impact": "none",
        "key_count": len(profile_keys),
        "changed_key_count": len(changed_keys),
        "unchanged_key_count": len(unchanged_keys),
        "expected_overlay_key_count": len(expected_overlay_keys),
        "generated_overlay_key_count": len(generated_overlay_keys),
        "all_baseline_keys_accounted_for": True,
        "all_expected_overlay_keys_accounted_for": all_expected_overlay_keys_accounted_for,
        "authority_parity": authority_parity,
        "baseline_overlay_parity": baseline_overlay_parity,
        "missing_overlay_keys": missing_overlay_keys,
    }

    return {
        "config": config,
        "profile": {
            "schema_version": 2,
            "status": status,
            "runtime_permission_impact": "none",
            "summary": summary,
            "key_count": len(profile_keys),
            "generated_overlay_keys": generated_overlay_keys,
            "expected_overlay_keys": expected_overlay_keys,
            "missing_overlay_keys": missing_overlay_keys,
            "all_expected_overlay_keys_accounted_for": all_expected_overlay_keys_accounted_for,
            "authority_parity": authority_parity,
            "baseline_overlay_parity": baseline_overlay_parity,
            "changed_keys": changed_keys,
            "unchanged_keys": unchanged_keys,
            "keys": key_profiles,
        },
    }


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _require_globalvalues_decision_ledger_authority_parity(
    *,
    default_values: Mapping[str, Any],
    allowed_rows: list[dict[str, Any]],
    decision_ledger: GlobalValuesDecisionLedger,
) -> None:
    decisions_by_key = {
        decision.key: decision for decision in decision_ledger.decisions
    }
    if set(decisions_by_key) != set(default_values):
        raise ValueError("globalvalues_decision_ledger_baseline_keys_mismatch")

    authority_rows = {str(row["key"]): row for row in allowed_rows}
    ledger_overlay_keys = {
        key
        for key, decision in decisions_by_key.items()
        if decision.kind is GlobalValueDecisionKind.AUTHORIZED_OVERLAY
    }
    if ledger_overlay_keys != set(authority_rows):
        raise ValueError("globalvalues_decision_ledger_authority_mismatch")

    for key, baseline_value in default_values.items():
        decision = decisions_by_key[key]
        baseline_canonical_json = _canonical_json_bytes(baseline_value)
        if decision.baseline_canonical_json != baseline_canonical_json:
            raise ValueError(
                "globalvalues_decision_ledger_authority_mismatch"
            )

        authority_row = authority_rows.get(key)
        if authority_row is None:
            if (
                decision.kind is not GlobalValueDecisionKind.COPY_BASELINE
                or decision.emitted_canonical_json
                != baseline_canonical_json
                or decision.authority_id != "globalvalues:baseline"
                or decision.claim_ids
                or decision.reason != "copied canonical baseline"
            ):
                raise ValueError(
                    "globalvalues_decision_ledger_authority_mismatch"
                )
            continue

        expected_emitted = _canonical_json_bytes(
            apply_globalvalues_overlay_operation(
                baseline_value,
                operation=str(authority_row["operation"]),
                value=authority_row.get("value"),
            )
        )
        if (
            decision.emitted_canonical_json != expected_emitted
            or decision.authority_id != authority_row.get("authority")
            or decision.claim_ids != (authority_row.get("claim_id"),)
            or decision.reason != authority_row.get("reason")
        ):
            raise ValueError(
                "globalvalues_decision_ledger_authority_mismatch"
            )


def validated_globalvalues_authority_rows(
    authority_matrix: Any,
) -> list[dict[str, Any]]:
    if not isinstance(authority_matrix, Mapping):
        raise ValueError("globalvalues_authority_matrix_must_be_object")
    raw_rows = authority_matrix.get("allowed_step1_overlays")
    if not isinstance(raw_rows, list):
        raise ValueError(
            "globalvalues_authority_allowed_step1_overlays_must_be_list"
        )

    rows: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, Mapping):
            raise ValueError(
                f"globalvalues_authority_overlay_row_must_be_object:{index}"
            )
        key_value = raw_row.get("key")
        if (
            not isinstance(key_value, str)
            or not key_value
            or key_value != key_value.strip()
        ):
            raise ValueError(
                f"globalvalues_authority_overlay_key_invalid:{index}"
            )
        key = key_value
        if key in seen_keys:
            raise ValueError(
                f"globalvalues_authority_duplicate_overlay_key:{key}"
            )
        seen_keys.add(key)

        operation = str(raw_row.get("operation", "none"))
        overlay = str(raw_row.get("overlay", "none"))
        if key == "baseline":
            if (
                "operation" not in raw_row
                or "overlay" not in raw_row
                or "value" not in raw_row
                or operation != "none"
                or overlay != "none"
                or raw_row.get("value") is not None
            ):
                raise ValueError(
                    "globalvalues_authority_baseline_row_must_be_exact_noop"
                )
            continue
        if key not in STEP1_POSTURE_KEYS:
            raise ValueError(
                f"globalvalues_authority_overlay_key_not_step1:{key}"
            )
        validate_globalvalues_overlay_value(
            key=key,
            operation=raw_row.get("operation", "none"),
            value=raw_row.get("value"),
        )
        if operation == "set":
            value = raw_row.get("value")
            expected_overlay = f"set:{value}"
        else:
            expected_overlay = operation
        if "overlay" in raw_row and overlay != expected_overlay:
            raise ValueError(
                f"globalvalues_authority_overlay_semantics_conflict:{key}"
            )
        rows.append(dict(raw_row))
    return rows


def validate_globalvalues_overlay_value(
    *,
    key: str,
    operation: Any,
    value: Any,
) -> None:
    if not isinstance(operation, str) or operation not in {
        "set",
        "increase",
        "decrease",
    }:
        raise ValueError(
            f"globalvalues_authority_overlay_operation_unsupported:{key}"
        )
    if operation == "set":
        if (
            not isinstance(value, str)
            or not value
            or value != value.strip()
        ):
            raise ValueError(
                f"globalvalues_authority_overlay_value_invalid:{key}"
            )
        try:
            numeric_value = _numeric_value(value)
        except (OverflowError, ValueError, ZeroDivisionError):
            raise ValueError(
                f"globalvalues_authority_overlay_value_invalid:{key}"
            ) from None
        if not math.isfinite(numeric_value):
            raise ValueError(
                f"globalvalues_authority_overlay_value_invalid:{key}"
            )
    elif value is not None:
        raise ValueError(
            f"globalvalues_authority_overlay_value_invalid:{key}"
        )


def _values_block(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping) and isinstance(
        value.get("values"), Sequence
    ):
        block = materialize_definition(value)
        if not block["values"]:
            block["values"].append({"condition": "*", "value": "0"})
        return block
    if isinstance(value, Mapping):
        return {"values": [{"condition": value.get("condition", "*"), "value": str(value.get("value", "0"))}]}
    return {"values": [{"condition": "*", "value": str(value)}]}


def apply_globalvalues_overlay_operation(
    baseline_value: Any,
    *,
    operation: str,
    value: Any,
) -> dict[str, Any]:
    block = _values_block(deepcopy(baseline_value))
    if operation == "set":
        if value is None:
            raise ValueError("globalvalues_overlay_set_value_missing")
        overlay = f"set:{value}"
    elif operation in {"increase", "decrease"}:
        if value is not None:
            raise ValueError("globalvalues_overlay_numeric_value_conflict")
        overlay = operation
    else:
        raise ValueError("globalvalues_overlay_operation_unsupported")
    _apply_overlay(block, overlay)
    return block


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
    if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
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
