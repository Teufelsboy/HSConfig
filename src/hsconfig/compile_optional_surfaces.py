from __future__ import annotations

from typing import Any


def compile_presume(
    contract: dict[str, Any] | None = None,
    *,
    deck_name: str | None = None,
    assumptions: list[dict[str, Any]] | None = None,
    enabled: bool | None = None,
) -> dict[str, Any] | None:
    if contract is None:
        return _compile_legacy_surface(
            "Presume",
            "PresumeOppInHandCard",
            deck_name or "Deck",
            assumptions or [],
            enabled=bool(enabled),
        )
    return _compile_contract_surface(
        contract,
        "presume",
        "Presume",
        "PresumeOppInHandCard",
        enabled=bool(enabled),
    )


def compile_concede(
    contract: dict[str, Any] | None = None,
    *,
    deck_name: str | None = None,
    rules: list[dict[str, Any]] | None = None,
    enabled: bool | None = None,
) -> dict[str, Any] | None:
    if contract is None:
        return _compile_legacy_surface(
            "Concede",
            "ExtraConcdeSettings",
            deck_name or "Deck",
            rules or [],
            enabled=bool(enabled),
        )
    return _compile_contract_surface(
        contract,
        "concede",
        "Concede",
        "ExtraConcdeSettings",
        enabled=bool(enabled),
    )


def _compile_contract_surface(
    contract: dict[str, Any],
    policy_key: str,
    surface_name: str,
    block_name: str,
    *,
    enabled: bool,
) -> dict[str, Any] | None:
    policy_rows = list(contract.get("policies", {}).get(policy_key, []))
    if not policy_rows or not enabled:
        return None
    deck_name = str(contract.get("deck_name", "Deck"))
    return {
        "GameCardId": surface_name,
        "ConfigComment": f"{deck_name} generated {surface_name.lower()} rules",
        block_name: {"values": [_policy_row(row, deck_name, policy_key) for row in policy_rows]},
    }


def _compile_legacy_surface(
    surface_name: str,
    block_name: str,
    deck_name: str,
    rows: list[dict[str, Any]],
    *,
    enabled: bool,
) -> dict[str, Any]:
    if not enabled:
        return {
            "emitted": False,
            "reason": f"{surface_name} surface not enabled for this package.",
        }
    return {
        "emitted": True,
        "config": {
            "GameCardId": surface_name,
            "ConfigComment": f"{deck_name} generated {surface_name.lower()} rules",
            block_name: {"values": [_policy_row(row, deck_name, surface_name.lower()) for row in rows]},
        },
    }


def _policy_row(row: dict[str, Any], deck_name: str, policy_key: str) -> dict[str, Any]:
    rule_id = str(row.get("rule_id", f"{policy_key}_policy"))
    return {
        "comment": row.get("comment", f"{deck_name}: {rule_id}"),
        "condition": row.get("condition", "*"),
        "value": str(row.get("value", policy_key)),
        "source_rule_id": rule_id,
        "source_claim_ids": list(row.get("source_claim_ids", [])),
        "confidence": row.get("confidence", "source_backed"),
    }
