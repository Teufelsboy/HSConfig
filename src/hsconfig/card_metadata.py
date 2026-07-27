from __future__ import annotations

from typing import Any, Mapping

from hsconfig.static_semantics import infer_static_semantics


def assign_mechanic_families(card: dict[str, Any]) -> list[str]:
    return infer_static_semantics(card)["families"]


def analysis_cards_from_deck_identity(
    deck_identity: Mapping[str, Any],
) -> list[dict[str, Any]]:
    sideboards = [
        sideboard
        for sideboard in deck_identity.get("sideboards", [])
        if isinstance(sideboard, Mapping)
    ]
    owner_card_ids = {
        str(sideboard.get("owner_card_id"))
        for sideboard in sideboards
        if sideboard.get("owner_card_id")
    }
    cards_by_id: dict[str, dict[str, Any]] = {}
    card_order: list[str] = []
    for raw_card in deck_identity.get("cards", []):
        if not isinstance(raw_card, Mapping):
            continue
        card_id = str(raw_card.get("card_id", "")).strip()
        if not card_id:
            continue
        card = {
            **dict(raw_card),
            "deck_zone": "main",
            "sideboard_owner_card_id": None,
            "sideboard_owner_card_ids": [],
            "sideboard_memberships": [],
            "runtime_eligible": True,
        }
        if card_id in owner_card_ids:
            card["analysis_roles"] = sorted(
                {
                    *[str(role) for role in card.get("analysis_roles", [])],
                    "deckbuilding_modifier",
                    "sideboard_owner",
                }
            )
        cards_by_id[card_id] = card
        card_order.append(card_id)

    for sideboard_index, sideboard in enumerate(sideboards, start=1):
        owner_card_id = (
            str(sideboard.get("owner_card_id"))
            if sideboard.get("owner_card_id")
            else None
        )
        normalized_sideboard_index = int(
            sideboard.get("sideboard_index", sideboard_index)
        )
        for raw_card in sideboard.get("cards", []):
            if not isinstance(raw_card, Mapping):
                continue
            card_id = str(raw_card.get("card_id", "")).strip()
            if not card_id:
                continue
            membership = {
                "sideboard_index": normalized_sideboard_index,
                "owner_card_id": owner_card_id,
                "count": int(raw_card.get("count", 1)),
            }
            card = cards_by_id.get(card_id)
            if card is None:
                card = {
                    **dict(raw_card),
                    "deck_zone": "sideboard",
                    "sideboard_owner_card_id": None,
                    "sideboard_owner_card_ids": [],
                    "sideboard_memberships": [],
                    "runtime_eligible": False,
                }
                cards_by_id[card_id] = card
                card_order.append(card_id)
            elif card.get("deck_zone") == "sideboard":
                card["count"] = int(card.get("count", 0)) + int(
                    raw_card.get("count", 1)
                )
            card["sideboard_memberships"].append(membership)
            if owner_card_id is not None:
                card["sideboard_owner_card_ids"] = sorted(
                    {
                        *[str(owner) for owner in card["sideboard_owner_card_ids"]],
                        owner_card_id,
                    }
                )

    for card in cards_by_id.values():
        owners = card.get("sideboard_owner_card_ids", [])
        card["sideboard_owner_card_id"] = (
            owners[0]
            if card.get("deck_zone") == "sideboard" and len(owners) == 1
            else None
        )
        card["sideboard_memberships"] = sorted(
            card.get("sideboard_memberships", []),
            key=lambda row: (
                int(row["sideboard_index"]),
                str(row.get("owner_card_id") or ""),
            ),
        )
    return [cards_by_id[card_id] for card_id in card_order]


def hydrate_card_metadata(
    *,
    cards: list[dict[str, Any]],
    source_records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    hydrated = []
    missing_count = 0
    for card in cards:
        card_id = str(card["card_id"])
        dbf_id = card.get("dbf_id")
        source_key = card_id if card_id in source_records else str(dbf_id)
        source = source_records.get(source_key, {})
        has_source_record = bool(source) or card.get("metadata_status") == "source_record"
        metadata_status = "source_record" if has_source_record else "missing_source_record"
        if not has_source_record:
            missing_count += 1
        merged = {
            "card_id": card_id,
            "dbf_id": int(dbf_id) if dbf_id is not None else None,
            "count": int(card.get("count", 1)),
            "name": source.get("name", card.get("name", card_id)),
            "cost": source.get("cost", card.get("cost")),
            "type": source.get("type", card.get("type", "UNKNOWN")),
            "card_class": source.get(
                "card_class",
                source.get("class", card.get("card_class")),
            ),
            "text": source.get("text", card.get("text", "")),
            "mechanics": list(source.get("mechanics", card.get("mechanics", [])) or []),
            "referenced_tags": list(
                source.get("referenced_tags", source.get("referencedTags", [])) or []
            ),
            "entourage": list(source.get("entourage", []) or []),
            "overload": source.get("overload"),
            "spell_damage": source.get("spell_damage", source.get("spellDamage")),
            "targeting_arrow_text": source.get(
                "targeting_arrow_text",
                source.get("targetingArrowText", ""),
            ),
            "hero_power_dbf_id": source.get("hero_power_dbf_id", source.get("heroPowerDbfId")),
            "metadata_status": metadata_status,
            "source_record_key": source_key if has_source_record else None,
            "deck_zone": str(card.get("deck_zone", "main")),
            "sideboard_owner_card_id": card.get("sideboard_owner_card_id"),
            "sideboard_owner_card_ids": [
                str(owner) for owner in card.get("sideboard_owner_card_ids", [])
            ],
            "sideboard_memberships": [
                dict(membership)
                for membership in card.get("sideboard_memberships", [])
                if isinstance(membership, Mapping)
            ],
            "runtime_eligible": card.get("runtime_eligible", True) is True,
            "analysis_roles": sorted(
                {str(role) for role in card.get("analysis_roles", [])}
            ),
        }
        semantic_result = infer_static_semantics(merged)
        merged["mechanic_families"] = semantic_result["families"]
        merged["static_semantic_evidence"] = semantic_result["evidence"]
        merged["warning_only_mechanics"] = semantic_result["warning_only"]
        hydrated.append(merged)
    return {"cards": hydrated, "unresolved_metadata_count": missing_count}
