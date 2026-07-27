from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from hsconfig.card_metadata import analysis_cards_from_deck_identity
from hsconfig.compile_globalvalues import KNOWN_GENERATED_OVERLAY_DEFAULTS
from hsconfig.io import read_json
from hsconfig.visionai_registry import is_supported_card_behavior_block

COMBO_SEPARATORS = (">->", ">>")
_METADATA_KEYS = {"GameCardId", "ConfigComment"}


def build_runtime_surface_ledger(
    *,
    deck_identity: Mapping[str, Any],
    compiled_mulligan: Mapping[str, Any],
    compiled_globalvalues: Mapping[str, Any],
    globalvalues_baseline: Mapping[str, Any] | None = None,
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
    mulligan_rows = _mulligan_rows(compiled_mulligan)
    mulligan_cards = {str(row["mulligan"]) for row in mulligan_rows if row["mulligan"] != "*"}
    combo_rows, combo_errors = _combo_rows(compiled_combo)
    combo_cards = {card_id for row in combo_rows for card_id in row["cards"]}
    cardid_payloads, cardid_errors = _valid_cardid_payloads(compiled_cardid_files)
    explicit_linked_runtime_ids = {
        str(owner.get("runtime_card_id", ""))
        for owner in linked_runtime_owners
        if str(owner.get("runtime_card_id", ""))
    }
    ownership_errors = [
        *[
            f"mulligan_out_of_deck_card:{row['mulligan']}"
            for row in mulligan_rows
            if row["mulligan"] != "*" and row["mulligan"] not in cards
        ],
        *[
            f"combo_out_of_deck_card:{card_id}"
            for card_id in sorted(combo_cards - set(cards))
        ],
        *[
            f"cardid_orphan_runtime_entity:{card_id}"
            for card_id in sorted(set(cardid_payloads) - set(cards) - explicit_linked_runtime_ids)
        ],
    ]
    globalvalues, globalvalue_errors = _globalvalues_metrics(
        compiled_globalvalues, globalvalues_baseline
    )
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
        "globalvalues_emitted": globalvalues["physical_key_count"] > 0,
        "mulligan": {
            "rule_count": len(mulligan_rows),
            "card_ids": sorted({str(row["mulligan"]) for row in mulligan_rows if row["mulligan"] != "*"}),
            "rules": mulligan_rows,
        },
        "combo": {
            "row_count": len(combo_rows),
            "card_ids": sorted(combo_cards),
            "rows": [str(row["canonical"]) for row in combo_rows],
        },
        "cardid": _cardid_metrics(cardid_payloads),
        "globalvalues": globalvalues,
        "physical_errors": sorted([*combo_errors, *cardid_errors, *globalvalue_errors, *ownership_errors]),
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


def _mulligan_rows(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    values = (
        payload.get("Mulligan", {}).get("values", [])
        if isinstance(payload, Mapping)
        else []
    )
    return [
        {
            "mulligan": str(row["mulligan"]),
            "value": str(row["value"]),
            "condition": str(row.get("condition", "*")),
        }
        for row in values
        if isinstance(row, Mapping)
        and row.get("mulligan")
        and row.get("value") in {"hold", "discard"}
    ]


def _combo_rows(
    payload: Mapping[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    if payload is None:
        return [], []
    values = (
        payload.get("ComboList", {}).get("values", [])
        if isinstance(payload, Mapping)
        else []
    )
    if not isinstance(values, list):
        return [], ["combo_values_malformed"]
    parsed_rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, row in enumerate(values):
        raw = row.get("combo") if isinstance(row, Mapping) else None
        parsed = _parse_combo(raw)
        if parsed is None:
            errors.append(f"combo_malformed:{index}")
        else:
            parsed_rows.append(parsed)
    return parsed_rows, errors


def _parse_combo(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, str):
        return None
    separators = [token for token in COMBO_SEPARATORS if token in raw]
    if len(separators) != 1:
        return None
    parts = [part.strip() for part in raw.split(separators[0])]
    if len(parts) < 2 or not all(parts) or any(">" in part for part in parts):
        return None
    return {"cards": parts, "operator": separators[0], "canonical": separators[0].join(parts)}


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


def _cardid_metrics(payloads: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    entities: list[dict[str, Any]] = []
    for card_id, payload in sorted(payloads.items()):
        blocks = {
            str(block): len(value["values"])
            for block, value in payload.items()
            if is_supported_card_behavior_block(str(block))
            and isinstance(value, Mapping)
            and isinstance(value.get("values"), list)
            and _has_nonempty_mapping_rows(value)
        }
        entities.append({"card_id": card_id, "behavior_blocks": blocks})
    return {
        "entity_count": len(entities),
        "behavior_row_count": sum(sum(entity["behavior_blocks"].values()) for entity in entities),
        "card_ids": [entity["card_id"] for entity in entities],
        "entities": entities,
    }


def _globalvalues_metrics(
    payload: Mapping[str, Any], baseline: Mapping[str, Any] | None
) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(payload, Mapping):
        return {"physical_key_count": 0, "changed_key_count": 0, "changed_keys": [], "keys": []}, ["globalvalues_payload_invalid"]
    keys = sorted(
        key for key, value in payload.items()
        if key not in _METADATA_KEYS and _has_nonempty_mapping_rows(value)
    )
    errors: list[str] = []
    if baseline is not None:
        known = set(baseline) | set(KNOWN_GENERATED_OVERLAY_DEFAULTS)
        errors.extend(f"globalvalues_unknown_key:{key}" for key in keys if key not in known)
        changed = [key for key in keys if key not in baseline or _normalized_values(payload[key]) != _normalized_values(baseline[key])]
    else:
        changed = list(keys)
    return {
        "physical_key_count": len(keys),
        "changed_key_count": len(changed),
        "changed_keys": changed,
        "keys": keys,
        "baseline_compared": baseline is not None,
    }, errors


def _normalized_values(value: object) -> list[dict[str, str]]:
    if isinstance(value, Mapping) and isinstance(value.get("values"), list):
        return [
            {"condition": str(row.get("condition", "*")), "value": str(row.get("value", ""))}
            for row in value["values"]
            if isinstance(row, Mapping)
        ]
    if isinstance(value, Mapping):
        return [{"condition": str(value.get("condition", "*")), "value": str(value.get("value", ""))}]
    return [{"condition": "*", "value": str(value)}]


def rederive_runtime_surface_ledger_from_package(package: str | Path) -> dict[str, Any]:
    package_path = Path(package)
    reports = package_path / "reports"
    deck_identity = read_json(reports / "deck_identity.json")
    baseline = read_json(reports / "globalvalues_baseline.json")
    behavior_plan = read_json(reports / "card_behavior_plan_report.json")
    if not isinstance(deck_identity, Mapping) or not isinstance(baseline, Mapping):
        raise ValueError("runtime_surface_ledger_report_invalid")
    if not isinstance(behavior_plan, Mapping):
        raise ValueError("runtime_surface_ledger_behavior_plan_invalid")
    deck_dirs = sorted(path for path in (package_path / "CustomConfig").iterdir() if path.is_dir())
    if len(deck_dirs) != 1:
        raise ValueError("runtime_surface_ledger_customconfig_dir_invalid")
    payloads = {
        path.name: read_json(path)
        for path in deck_dirs[0].glob("*.json")
    }
    return build_runtime_surface_ledger(
        deck_identity=deck_identity,
        compiled_mulligan=payloads.get("Mulligan.json", {}),
        compiled_globalvalues=payloads.get("GlobalValues.json", {}),
        globalvalues_baseline=baseline,
        compiled_combo=payloads.get("Combo.json"),
        compiled_cardid_files={
            name: payload
            for name, payload in payloads.items()
            if name not in {"Mulligan.json", "GlobalValues.json", "Combo.json"}
        },
        linked_runtime_owners=[
            {
                "source_card_id": str(row.get("source_card_id") or row.get("card_id", "")),
                "runtime_card_id": str(row.get("runtime_card_id") or row.get("card_id", "")),
                "link_kind": str(row.get("link_kind") or "self"),
            }
            for row in behavior_plan.get("rows", [])
            if isinstance(row, Mapping) and row.get("meaningful_runtime_surface") is True
        ],
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
