from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from hsconfig.card_metadata import analysis_cards_from_deck_identity
from hsconfig.visionai_registry import is_supported_card_behavior_block


def build_runtime_surface_ledger(
    *,
    deck_identity: Mapping[str, Any],
    compiled_mulligan: Mapping[str, Any],
    compiled_globalvalues: Mapping[str, Any],
    compiled_combo: Mapping[str, Any] | None,
    compiled_cardid_files: Mapping[str, Mapping[str, Any]],
    linked_runtime_owners: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """Describe emitted runtime surfaces from compiled payloads only."""
    cards: dict[str, dict[str, Any]] = {}
    for card in analysis_cards_from_deck_identity(dict(deck_identity)):
        card_id = str(card.get("card_id", ""))
        if not card_id:
            continue
        cards[card_id] = {
            "card_id": card_id,
            "deck_zone": str(card.get("deck_zone", "main")),
            "runtime_eligible": card.get("runtime_eligible", True) is True,
            "runtime_surfaces": [],
            "runtime_emitted": False,
        }

    mulligan_cards = _compiled_card_ids(compiled_mulligan)
    combo_cards = _compiled_card_ids(compiled_combo or {})
    globalvalues_emitted = bool(compiled_globalvalues)
    physical_cardids = {
        _filename_card_id(filename): payload
        for filename, payload in compiled_cardid_files.items()
        if _filename_card_id(filename)
    }
    for card_id, record in cards.items():
        if record["runtime_eligible"] and card_id in mulligan_cards:
            record["runtime_surfaces"].append("Mulligan.json")
        if record["runtime_eligible"] and card_id in combo_cards:
            record["runtime_surfaces"].append("Combo.json")
        if record["runtime_eligible"] and _has_runtime_effect(physical_cardids.get(card_id)):
            record["runtime_surfaces"].append(f"{card_id}.json")
        record["runtime_surfaces"].sort()
        record["runtime_emitted"] = bool(record["runtime_surfaces"])

    linked: dict[str, dict[str, Any]] = {}
    for owner in linked_runtime_owners:
        source_card_id = str(owner.get("source_card_id", ""))
        runtime_card_id = str(owner.get("runtime_card_id", ""))
        if not source_card_id or not runtime_card_id or source_card_id == runtime_card_id:
            continue
        payload = physical_cardids.get(runtime_card_id)
        emitted = _has_runtime_effect(payload) and _game_card_matches(payload, runtime_card_id)
        linked[runtime_card_id] = {
            "source_card_id": source_card_id,
            "runtime_card_id": runtime_card_id,
            "link_kind": str(owner.get("link_kind", "")),
            "runtime_surface": f"{runtime_card_id}.json",
            "runtime_emitted": emitted,
        }

    ledger = {
        "schema_version": 1,
        "cards": dict(sorted(cards.items())),
        "linked_runtime_entities": dict(sorted(linked.items())),
        "globalvalues_emitted": globalvalues_emitted,
    }
    ledger["surface_ledger_sha256"] = _sha256(ledger)
    return ledger


def _compiled_card_ids(payload: Mapping[str, Any]) -> set[str]:
    cards: set[str] = set()
    for key, value in _walk(payload):
        if key.lower() in {"cardid", "card_id", "card", "mulligan"} and isinstance(value, str):
            cards.add(value)
    return cards


def _walk(value: Any) -> Sequence[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            rows.append((str(key), item))
            rows.extend(_walk(item))
    elif isinstance(value, list):
        for item in value:
            rows.extend(_walk(item))
    return rows


def _filename_card_id(filename: object) -> str:
    value = str(filename).replace("\\", "/").rsplit("/", 1)[-1]
    return value[:-5] if value.endswith(".json") else ""


def _has_runtime_effect(payload: Any) -> bool:
    if not isinstance(payload, Mapping):
        return False
    for block, block_payload in payload.items():
        if not is_supported_card_behavior_block(str(block)):
            continue
        if isinstance(block_payload, Mapping) and isinstance(block_payload.get("values"), list):
            if block_payload["values"]:
                return True
    return False


def _game_card_matches(payload: Any, card_id: str) -> bool:
    return isinstance(payload, Mapping) and str(payload.get("GameCardId", "")) == card_id


def _sha256(value: Mapping[str, Any]) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
