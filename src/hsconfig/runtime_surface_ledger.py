from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from hsconfig.card_metadata import analysis_cards_from_deck_identity
from hsconfig.visionai_registry import is_supported_card_behavior_block

COMBO_SEPARATORS = (">->", ">>")
_METADATA_KEYS = {"GameCardId", "ConfigComment"}


def build_runtime_surface_ledger(
    *,
    deck_identity: Mapping[str, Any],
    compiled_mulligan: Mapping[str, Any],
    compiled_globalvalues: Mapping[str, Any],
    compiled_combo: Mapping[str, Any] | None,
    compiled_cardid_files: Mapping[str, Mapping[str, Any]],
    linked_runtime_owners: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """Project emitted surfaces from physical payloads; never from plan rows."""
    cards = {
        str(card["card_id"]): {
            "card_id": str(card["card_id"]),
            "deck_zone": str(card.get("deck_zone", "main")),
            "runtime_eligible": card.get("runtime_eligible", True) is True,
            "runtime_surfaces": [],
            "runtime_emitted": False,
        }
        for card in analysis_cards_from_deck_identity(dict(deck_identity))
        if card.get("card_id")
    }
    mulligan_cards = _mulligan_cards(compiled_mulligan)
    combo_cards, combo_errors = _combo_cards(compiled_combo)
    cardid_payloads, cardid_errors = _valid_cardid_payloads(compiled_cardid_files)
    unexpected: list[dict[str, str]] = []
    for card_id, record in cards.items():
        if card_id in mulligan_cards:
            _add_surface(record, "Mulligan.json")
        if card_id in combo_cards:
            _add_surface(record, "Combo.json")
        if card_id in cardid_payloads:
            _add_surface(record, f"{card_id}.json")
        if not record["runtime_eligible"] and record["runtime_surfaces"]:
            unexpected.append(
                {"card_id": card_id, "reason": "ineligible_card_runtime_emitted"}
            )
        record["runtime_emitted"] = bool(record["runtime_surfaces"])
    linked, collisions = _linked_entities(linked_runtime_owners, cardid_payloads)
    ledger = {
        "schema_version": 2,
        "cards": dict(sorted(cards.items())),
        "linked_runtime_entities": linked,
        "globalvalues_emitted": _valid_globalvalues(compiled_globalvalues),
        "physical_errors": sorted([*combo_errors, *cardid_errors]),
        "unexpected_runtime_emissions": sorted(
            unexpected, key=lambda row: row["card_id"]
        ),
        "linked_runtime_owner_collisions": collisions,
    }
    ledger["surface_ledger_sha256"] = _sha256(ledger)
    return ledger


def _add_surface(record: dict[str, Any], surface: str) -> None:
    if surface not in record["runtime_surfaces"]:
        record["runtime_surfaces"].append(surface)
        record["runtime_surfaces"].sort()


def _mulligan_cards(payload: Mapping[str, Any]) -> set[str]:
    values = (
        payload.get("Mulligan", {}).get("values", [])
        if isinstance(payload, Mapping)
        else []
    )
    return {
        str(row["mulligan"])
        for row in values
        if isinstance(row, Mapping)
        and row.get("mulligan")
        and row.get("value") == "hold"
    }


def _combo_cards(payload: Mapping[str, Any] | None) -> tuple[set[str], list[str]]:
    if payload is None:
        return set(), []
    values = (
        payload.get("ComboList", {}).get("values", [])
        if isinstance(payload, Mapping)
        else []
    )
    if not isinstance(values, list):
        return set(), ["combo_values_malformed"]
    cards: set[str] = set()
    errors: list[str] = []
    for index, row in enumerate(values):
        raw = row.get("combo") if isinstance(row, Mapping) else None
        parsed = _parse_combo(raw)
        if parsed is None:
            errors.append(f"combo_malformed:{index}")
        else:
            cards.update(parsed)
    return cards, errors


def _parse_combo(raw: Any) -> list[str] | None:
    if not isinstance(raw, str):
        return None
    separators = [token for token in COMBO_SEPARATORS if token in raw]
    if len(separators) != 1:
        return None
    parts = [part.strip() for part in raw.split(separators[0])]
    return (
        parts
        if len(parts) >= 2 and all(parts) and all(">" not in part for part in parts)
        else None
    )


def _valid_cardid_payloads(
    files: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Mapping[str, Any]], list[str]]:
    valid: dict[str, Mapping[str, Any]] = {}
    errors: list[str] = []
    for filename, payload in files.items():
        card_id = _filename_card_id(filename)
        if (
            not card_id
            or not isinstance(payload, Mapping)
            or str(payload.get("GameCardId", "")) != card_id
        ):
            errors.append(f"cardid_identity_invalid:{filename}")
            continue
        has_behavior_payload = any(key not in _METADATA_KEYS for key in payload)
        if has_behavior_payload and not _has_runtime_effect(payload):
            errors.append(f"cardid_runtime_block_invalid:{filename}")
            continue
        if _has_runtime_effect(payload):
            valid[card_id] = payload
    return valid, errors


def _has_runtime_effect(payload: Mapping[str, Any]) -> bool:
    return any(
        is_supported_card_behavior_block(str(block))
        and _has_nonempty_mapping_rows(value)
        for block, value in payload.items()
    )


def _valid_globalvalues(payload: Mapping[str, Any]) -> bool:
    return isinstance(payload, Mapping) and any(
        key not in _METADATA_KEYS and _has_nonempty_mapping_rows(value)
        for key, value in payload.items()
    )


def _has_nonempty_mapping_rows(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and isinstance(value.get("values"), list)
        and any(isinstance(row, Mapping) and bool(row) for row in value["values"])
    )


def _linked_entities(
    owners: Sequence[Mapping[str, str]], payloads: Mapping[str, Mapping[str, Any]]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for owner in owners:
        source, runtime = (
            str(owner.get("source_card_id", "")),
            str(owner.get("runtime_card_id", "")),
        )
        if source and runtime and source != runtime:
            grouped[runtime].append((source, runtime, str(owner.get("link_kind", ""))))
    rows: dict[str, dict[str, Any]] = {}
    collisions: list[dict[str, Any]] = []
    for runtime, candidates in sorted(grouped.items()):
        unique = sorted(set(candidates))
        if len(unique) != 1:
            collisions.append(
                {
                    "runtime_card_id": runtime,
                    "owners": [
                        {"source_card_id": source, "link_kind": kind}
                        for source, _, kind in unique
                    ],
                }
            )
            continue
        source, _, kind = unique[0]
        rows[runtime] = {
            "source_card_id": source,
            "runtime_card_id": runtime,
            "link_kind": kind,
            "runtime_surface": f"{runtime}.json",
            "runtime_emitted": runtime in payloads,
        }
    return rows, collisions


def _filename_card_id(filename: object) -> str:
    value = str(filename).replace("\\", "/").rsplit("/", 1)[-1]
    return value[:-5] if value.endswith(".json") else ""


def _sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
    ).hexdigest()
