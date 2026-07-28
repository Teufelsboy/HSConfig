from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from hsconfig.deck_identity import stable_deck_fingerprint
from hsconfig.deckstring_decode import decode_deck_code


_GLOBALVALUES_BASELINE_KEYS = (
    "ConfigComment",
    "FirstTurnValueWeight",
    "GameCardId",
    "GlobalCharge",
    "GlobalDivineShield",
    "GlobalDurability",
    "GlobalFrozen",
    "GlobalHeroAttack",
    "GlobalHeroHealth",
    "GlobalLocationHealth",
    "GlobalLocationIntrinsicValue",
    "GlobalMinionAttack",
    "GlobalMinionHealth",
    "GlobalMinionIntrinsicValue",
    "GlobalOverload",
    "GlobalQuestProgressValue",
    "GlobalStealth",
    "GlobalTaunt",
    "GlobalWeaponAttack",
    "GlobalWindfury",
    "OppGlobalCharge",
    "OppGlobalDivineShield",
    "OppGlobalDurability",
    "OppGlobalFrozen",
    "OppGlobalHeroAttack",
    "OppGlobalHeroHealth",
    "OppGlobalLocationHealth",
    "OppGlobalLocationIntrinsicValue",
    "OppGlobalMinionAttack",
    "OppGlobalMinionHealth",
    "OppGlobalMinionIntrinsicValue",
    "OppGlobalOverload",
    "OppGlobalQuestProgressValue",
    "OppGlobalStealth",
    "OppGlobalTaunt",
    "OppGlobalWeaponAttack",
    "OppGlobalWindfury",
    "SecondTurnValueWeight",
)
_INVENTORY_KEYS = frozenset(
    {"schema_version", "decks", "canonical_content_sha256"}
)
_DECK_KEYS = frozenset(
    {
        "deck_name",
        "deck_fingerprint",
        "main_cards",
        "sideboard_modules",
        "claims",
        "globalvalues_decisions",
    }
)
_MAIN_CARD_KEYS = frozenset({"card_id", "composite_card_key", "count"})
_SIDEBARD_MODULE_KEYS = frozenset(
    {
        "card_id",
        "composite_card_key",
        "count",
        "owner_card_id",
        "owner_dbf_id",
        "sideboard_index",
    }
)
_CLAIM_KEYS = frozenset({"claim_id", "claim_key"})


@dataclass(frozen=True, slots=True)
class SemanticInventorySummary:
    deck_count: int
    main_slot_count: int
    main_card_identity_count: int
    sideboard_module_count: int
    disposition_row_count: int
    claim_count: int
    globalvalues_decision_count: int


def validate_semantic_inventory(
    inventory: Mapping[str, Any],
    *,
    audited_catalog: Sequence[Mapping[str, Any]],
) -> SemanticInventorySummary:
    """Validate the tracked projection of the twelve audited package semantics."""
    _validate_inventory_content_sha256(inventory)
    if set(inventory) != _INVENTORY_KEYS or inventory.get("schema_version") != 1:
        raise ValueError("semantic_inventory_schema_invalid")

    rows = _mapping_rows(inventory.get("decks"), "semantic_inventory_deck_row_invalid")
    expected_catalog = _catalog_rows(audited_catalog)
    expected_names = tuple(str(row["deck_name"]) for row in expected_catalog)
    actual_names = tuple(_required_string(row, "deck_name") for row in rows)
    if actual_names != expected_names:
        raise ValueError("semantic_inventory_catalog_mismatch")
    if len(expected_names) != 12 or len(set(expected_names)) != 12:
        raise ValueError("semantic_inventory_deck_identity_invalid")

    main_cards: list[Mapping[str, Any]] = []
    modules: list[Mapping[str, Any]] = []
    claims: list[Mapping[str, Any]] = []
    decisions: list[str] = []
    all_claim_keys: list[str] = []

    for row, catalog_row in zip(rows, expected_catalog, strict=True):
        deck_main, deck_modules, deck_claims, deck_decisions = _validate_deck_row(
            row,
            catalog_row,
        )
        main_cards.extend(deck_main)
        modules.extend(deck_modules)
        claims.extend(deck_claims)
        decisions.extend(deck_decisions)
        all_claim_keys.extend(_required_string(claim, "claim_key") for claim in deck_claims)

    if len(set(all_claim_keys)) != len(all_claim_keys):
        raise ValueError("semantic_inventory_claim_key_invalid")
    for row in rows:
        _validate_claim_keys(row)

    return SemanticInventorySummary(
        deck_count=len(rows),
        main_slot_count=sum(_required_positive_int(card, "count") for card in main_cards),
        main_card_identity_count=len(main_cards),
        sideboard_module_count=len(modules),
        disposition_row_count=len(main_cards) + len(modules),
        claim_count=len(claims),
        globalvalues_decision_count=len(decisions),
    )


def _validate_inventory_content_sha256(inventory: Mapping[str, Any]) -> None:
    checksum = inventory.get("canonical_content_sha256")
    if not isinstance(checksum, str) or len(checksum) != 64:
        raise ValueError("semantic_inventory_content_sha256_invalid")
    content = {key: value for key, value in inventory.items() if key != "canonical_content_sha256"}
    canonical = json.dumps(content, separators=(",", ":"), sort_keys=True)
    actual_checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if actual_checksum != checksum:
        raise ValueError("semantic_inventory_content_sha256_invalid")


def _catalog_rows(
    audited_catalog: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    rows = tuple(audited_catalog)
    if any(not isinstance(row, Mapping) for row in rows):
        raise ValueError("semantic_inventory_deck_identity_invalid")
    if any(
        not isinstance(row.get("deck_name"), str)
        or not row["deck_name"].strip()
        or not isinstance(row.get("deck_code"), str)
        or not row["deck_code"].strip()
        for row in rows
    ):
        raise ValueError("semantic_inventory_deck_identity_invalid")
    return rows


def _validate_deck_row(
    row: Mapping[str, Any], catalog_row: Mapping[str, Any]
) -> tuple[
    tuple[Mapping[str, Any], ...],
    tuple[Mapping[str, Any], ...],
    tuple[Mapping[str, Any], ...],
    tuple[str, ...],
]:
    if set(row) != _DECK_KEYS:
        raise ValueError("semantic_inventory_deck_row_invalid")

    decoded = decode_deck_code(_required_string(catalog_row, "deck_code"))
    decoded_main = _mapping_rows(
        decoded.get("main_deck"), "semantic_inventory_main_cards_invalid"
    )
    fingerprint = stable_deck_fingerprint(
        (_required_string(card, "card_id"), _required_positive_int(card, "count"))
        for card in decoded_main
    )
    if _required_string(row, "deck_fingerprint") != fingerprint:
        raise ValueError("semantic_inventory_fingerprint_invalid")

    main_cards = _mapping_rows(
        row.get("main_cards"), "semantic_inventory_main_cards_invalid"
    )
    expected_main = tuple(
        {
            "card_id": _required_string(card, "card_id"),
            "count": _required_positive_int(card, "count"),
            "composite_card_key": f"{fingerprint}:main_deck:{card['card_id']}",
        }
        for card in decoded_main
    )
    _validate_cards(
        main_cards,
        expected_main,
        _MAIN_CARD_KEYS,
        "semantic_inventory_main_cards_invalid",
    )
    if sum(_required_positive_int(card, "count") for card in main_cards) != 30:
        raise ValueError("semantic_inventory_main_slot_count_invalid")

    modules = _mapping_rows(
        row.get("sideboard_modules"), "semantic_inventory_sideboard_module_invalid"
    )
    expected_modules = _expected_sideboard_modules(decoded, fingerprint)
    main_card_ids = {_required_string(card, "card_id") for card in main_cards}
    if any(
        _required_string(module, "owner_card_id") not in main_card_ids
        for module in modules
    ):
        raise ValueError("semantic_inventory_sideboard_owner_invalid")
    _validate_cards(
        modules,
        expected_modules,
        _SIDEBARD_MODULE_KEYS,
        "semantic_inventory_sideboard_module_invalid",
    )

    composite_keys = tuple(
        _required_string(card, "composite_card_key") for card in (*main_cards, *modules)
    )
    expected_composite_keys = tuple(
        _required_string(card, "composite_card_key")
        for card in (*expected_main, *expected_modules)
    )
    if composite_keys != expected_composite_keys or len(set(composite_keys)) != len(
        composite_keys
    ):
        raise ValueError("semantic_inventory_card_identity_invalid")

    claims = _mapping_rows(row.get("claims"), "semantic_inventory_claim_identity_invalid")
    if any(set(claim) != _CLAIM_KEYS for claim in claims):
        raise ValueError("semantic_inventory_claim_identity_invalid")
    claim_ids = tuple(_required_string(claim, "claim_id") for claim in claims)
    if len(set(claim_ids)) != len(claim_ids):
        raise ValueError("semantic_inventory_claim_identity_invalid")

    decisions = tuple(row.get("globalvalues_decisions", ()))
    if decisions != _GLOBALVALUES_BASELINE_KEYS:
        raise ValueError("semantic_inventory_globalvalues_keys_invalid")

    return main_cards, modules, claims, decisions


def _validate_claim_keys(row: Mapping[str, Any]) -> None:
    fingerprint = _required_string(row, "deck_fingerprint")
    claims = _mapping_rows(row.get("claims"), "semantic_inventory_claim_identity_invalid")
    expected_claim_keys = tuple(
        f"{fingerprint}:{_required_string(claim, 'claim_id')}" for claim in claims
    )
    claim_keys = tuple(_required_string(claim, "claim_key") for claim in claims)
    if claim_keys != expected_claim_keys:
        raise ValueError("semantic_inventory_claim_identity_invalid")


def _expected_sideboard_modules(
    decoded: Mapping[str, Any], fingerprint: str
) -> tuple[dict[str, Any], ...]:
    expected: list[dict[str, Any]] = []
    sideboards = _mapping_rows(
        decoded.get("sideboards"), "semantic_inventory_sideboard_module_invalid"
    )
    for sideboard in sideboards:
        owner_card_id = _required_string(sideboard, "owner_card_id")
        owner_dbf_id = _required_positive_int(sideboard, "owner_dbf_id")
        sideboard_index = _required_positive_int(sideboard, "sideboard_index")
        for card in _mapping_rows(
            sideboard.get("cards"), "semantic_inventory_sideboard_module_invalid"
        ):
            card_id = _required_string(card, "card_id")
            expected.append(
                {
                    "card_id": card_id,
                    "count": _required_positive_int(card, "count"),
                    "owner_card_id": owner_card_id,
                    "owner_dbf_id": owner_dbf_id,
                    "sideboard_index": sideboard_index,
                    "composite_card_key": (
                        f"{fingerprint}:sideboard_module:{owner_card_id}:{card_id}"
                    ),
                }
            )
    return tuple(expected)


def _validate_cards(
    actual: Sequence[Mapping[str, Any]],
    expected: Sequence[Mapping[str, Any]],
    expected_keys: frozenset[str],
    error_code: str,
) -> None:
    if len(actual) != len(expected) or any(set(card) != expected_keys for card in actual):
        raise ValueError(error_code)
    if any(dict(card) != dict(expected_card) for card, expected_card in zip(actual, expected, strict=True)):
        raise ValueError(error_code)


def _mapping_rows(value: Any, error_code: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or any(not isinstance(row, Mapping) for row in value):
        raise ValueError(error_code)
    return tuple(value)


def _required_string(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError("semantic_inventory_schema_invalid")
    return value


def _required_positive_int(row: Mapping[str, Any], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("semantic_inventory_schema_invalid")
    return value


__all__ = ("SemanticInventorySummary", "validate_semantic_inventory")
