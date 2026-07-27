from __future__ import annotations

from typing import Any

from hearthstone import cardxml
from hearthstone.deckstrings import FormatType, parse_deckstring


TYPE_NAMES = {
    3: "HERO",
    4: "MINION",
    5: "SPELL",
    7: "WEAPON",
    10: "HERO_POWER",
    39: "LOCATION",
}

MECHANIC_ATTRS = (
    "battlecry",
    "charge",
    "deathrattle",
    "discover",
    "dredge",
    "lifesteal",
    "overload",
    "reborn",
    "rush",
    "secret",
    "taunt",
    "tradeable",
)


def decode_deck_code(deck_code: str) -> dict[str, Any]:
    normalized_deck_code = deck_code.strip()
    normalized_deck_code += "=" * (-len(normalized_deck_code) % 4)
    parsed = _parse_deckstring(normalized_deck_code)
    cards_db, _ = cardxml.load_dbf()

    cards: list[dict[str, Any]] = []
    card_id_map: dict[str, dict[str, Any]] = {}
    unresolved: list[dict[str, Any]] = []

    for dbf_id, count in sorted(parsed["cards"], key=lambda row: row[0]):
        row = _card_row(cards_db, dbf_id, count)
        cards.append(row)
        card_id_map[str(dbf_id)] = {
            "dbf_id": dbf_id,
            "card_id": row["card_id"],
            "name": row["name"],
            "count": count,
        }
        if row["metadata_status"] != "source_record":
            unresolved.append({"dbf_id": dbf_id, "count": count})

    hero_dbf_id = parsed["heroes"][0] if parsed["heroes"] else None
    format_name = _format_name(parsed["format"])
    card_count_total = sum(card["count"] for card in cards)
    sideboards = _sideboard_rows(cards_db, parsed.get("sideboards", []))
    sideboard_count = sum(
        card["count"]
        for sideboard in sideboards
        for card in sideboard.get("cards", [])
    )
    receipt = {
        "decoder": "hearthstone.deckstrings",
        "deck_code_length": len(deck_code),
        "format": format_name,
        "hero_dbf_id": hero_dbf_id,
        "card_count_total": card_count_total,
        "unique_card_count": len(cards),
        "sideboard_count": sideboard_count,
        "sideboard_unique_card_count": sum(len(sideboard.get("cards", [])) for sideboard in sideboards),
        "unresolved_card_count": len(unresolved),
        "unresolved_cards": unresolved,
    }

    return {
        "cards": cards,
        "main_deck": cards,
        "sideboards": sideboards,
        "hero_dbf_id": hero_dbf_id,
        "format": format_name,
        "card_count": card_count_total,
        "card_count_total": card_count_total,
        "sideboard_count": sideboard_count,
        "unresolved_card_count": len(unresolved),
        "deckstring_decode_receipt": receipt,
        "card_id_map": card_id_map,
    }


def _parse_deckstring(deck_code: str) -> dict[str, Any]:
    parsed = parse_deckstring(deck_code)
    if hasattr(parsed, "cards"):
        return {
            "cards": parsed.cards,
            "heroes": parsed.heroes,
            "format": parsed.format,
            "sideboards": getattr(parsed, "sideboards", []),
        }

    cards, heroes, format_value, sideboards = parsed
    return {
        "cards": cards,
        "heroes": heroes,
        "format": format_value,
        "sideboards": sideboards,
    }


def _card_row(cards_db: dict[int, Any], dbf_id: int, count: int) -> dict[str, Any]:
    card = cards_db.get(dbf_id)
    if card is None:
        return {
            "card_id": f"UNRESOLVED_DBF_{dbf_id}",
            "dbf_id": dbf_id,
            "count": count,
            "name": f"Unresolved DBF {dbf_id}",
            "cost": None,
            "type": "UNKNOWN",
            "card_class": None,
            "text": "",
            "mechanics": [],
            "metadata_status": "missing_source_record",
        }

    mechanics = [name for name in MECHANIC_ATTRS if getattr(card, name, None)]
    return {
        "card_id": str(card.card_id),
        "dbf_id": int(dbf_id),
        "count": int(count),
        "name": str(card.english_name or card.name or card.card_id),
        "cost": int(card.cost) if card.cost is not None else None,
        "type": _enum_name(card.type),
        "card_class": _enum_name(card.card_class),
        "text": str(card.english_description or "").replace("\n", " "),
        "mechanics": sorted(set(mechanics)),
        "metadata_status": "source_record",
    }


def _sideboard_rows(cards_db: dict[int, Any], sideboards: Any) -> list[dict[str, Any]]:
    grouped: dict[int | None, list[tuple[int, int]]] = {}
    if not sideboards:
        return []

    for sideboard in sideboards:
        if isinstance(sideboard, tuple) and len(sideboard) == 3:
            card_dbf_id, count, owner_dbf_id = sideboard
            grouped.setdefault(int(owner_dbf_id), []).append((int(card_dbf_id), int(count)))
            continue
        if isinstance(sideboard, tuple) and len(sideboard) >= 2:
            owner_dbf_id = int(sideboard[0]) if sideboard[0] is not None else None
            cards_payload = sideboard[1] or []
            grouped.setdefault(owner_dbf_id, []).extend(
                (int(dbf_id), int(count)) for dbf_id, count in cards_payload
            )
            continue
        if isinstance(sideboard, dict):
            owner = sideboard.get("owner") or sideboard.get("owner_dbf_id")
            owner_dbf_id = int(owner) if owner is not None else None
            cards_payload = sideboard.get("cards", [])
            grouped.setdefault(owner_dbf_id, []).extend(
                (int(dbf_id), int(count)) for dbf_id, count in cards_payload
            )
            continue
        raise ValueError(f"Unsupported sideboard row shape: {sideboard!r}")

    rows: list[dict[str, Any]] = []
    for index, (owner_dbf_id, cards_payload) in enumerate(
        sorted(grouped.items(), key=lambda item: str(item[0])),
        start=1,
    ):
        owner_card_id = None
        if owner_dbf_id is not None:
            owner_card = cards_db.get(owner_dbf_id)
            owner_card_id = str(owner_card.card_id) if owner_card is not None else None
        rows.append(
            {
                "sideboard_index": index,
                "owner_dbf_id": owner_dbf_id,
                "owner_card_id": owner_card_id,
                "cards": [
                    _card_row(cards_db, dbf_id, count)
                    for dbf_id, count in sorted(cards_payload)
                ],
            }
        )
    return rows


def _format_name(format_value: FormatType | int | None) -> str | None:
    if format_value is None:
        return None
    try:
        return FormatType(format_value).name
    except ValueError:
        return str(format_value)


def _enum_name(value: Any) -> str | None:
    if value is None:
        return None
    name = getattr(value, "name", None)
    if name is not None:
        return str(name)
    try:
        return TYPE_NAMES.get(int(value), str(value))
    except (TypeError, ValueError):
        return str(value)
