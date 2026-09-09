"""Pure rich card facts, with identity separate from deck membership."""

from __future__ import annotations

import re
from typing import Any
import unicodedata

from hsconfig.card_metadata import analysis_cards_from_deck_identity
from hsconfig.semantic_enrichment import enrich_card_metadata


_ALIASES = {
    "dbf_id": {"dbfId", "dbf_id"},
    "name": {"name"},
    "text": {"text"},
    "type": {"type"},
    "cost": {"cost"},
    "attack": {"attack"},
    "health": {"health"},
    "durability": {"durability"},
    "races": {"race", "races"},
    "classes": {"cardClass", "card_class", "classes"},
    "spell_school": {"spellSchool", "spell_school"},
    "mechanics": {"mechanics"},
    "play_requirements": {"playRequirements", "play_requirements"},
}
CARD_FACT_FIELDS = frozenset(_ALIASES) | {
    "missing_fields",
    "inapplicable_fields",
    "mechanic_families",
}
RELATION_FIELDS = frozenset({"source_card_id", "card_id", "link_kind", "status"})


def _inapplicable(field: str, card_type: str | None) -> bool:
    types = {
        "attack": {"MINION", "WEAPON"},
        "health": {"MINION", "HERO", "LOCATION"},
        "durability": {"WEAPON", "LOCATION"},
        "races": {"MINION"},
        "spell_school": {"SPELL"},
    }
    return bool(
        card_type
        and card_type != "UNKNOWN"
        and field in types
        and card_type not in types[field]
    )


def _text(value: str) -> str:
    value = value.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    if any(unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in value):
        raise ValueError("starter_card_facts_control_character")
    return value


def _membership(row: Any) -> dict:
    if (
        not isinstance(row, dict)
        or not isinstance(row.get("card_id"), str)
        or re.fullmatch(r"[A-Za-z0-9_]+", row["card_id"]) is None
        or type(row.get("count")) is not int
        or row["count"] < 1
    ):
        raise ValueError("starter_card_facts_membership_invalid")
    return {"card_id": row["card_id"], "count": row["count"]}


def project_card_facts(deck: dict, full_cards: list[dict]) -> dict:
    """Project main/sideboard memberships and one-hop factual relations only."""
    if not isinstance(deck, dict) or type(deck.get("cards")) is not list:
        raise ValueError("starter_card_facts_deck_invalid")
    cards = [_membership(row) for row in deck["cards"]]
    if not cards or len({row["card_id"] for row in cards}) != len(cards):
        raise ValueError("starter_card_facts_membership_invalid")
    boards = deck.get("sideboards", [])
    if type(boards) is not list or type(full_cards) is not list:
        raise ValueError("starter_card_facts_deck_invalid")
    sideboards = []
    indexes = set()
    owners = set()
    main_ids = {row["card_id"] for row in cards}
    for board in boards:
        if (
            not isinstance(board, dict)
            or board.get("owner_card_id") not in main_ids
            or type(board.get("sideboard_index")) is not int
            or board["sideboard_index"] < 1
            or board["sideboard_index"] in indexes
            or board["owner_card_id"] in owners
            or type(board.get("cards")) is not list
        ):
            raise ValueError("starter_card_facts_sideboard_invalid")
        indexes.add(board["sideboard_index"])
        owners.add(board["owner_card_id"])
        seen_members = set()
        for row in board["cards"]:
            member = _membership(row)
            if member["card_id"] in seen_members:
                raise ValueError("starter_card_facts_membership_invalid")
            seen_members.add(member["card_id"])
            sideboards.append(
                {
                    "owner_card_id": board["owner_card_id"],
                    "index": board["sideboard_index"],
                    **member,
                }
            )
    index = {}
    dbfs = {}
    for row in full_cards:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            raise ValueError("starter_card_facts_identity_invalid")
        if row["id"] in index and row != index[row["id"]]:
            raise ValueError("starter_card_facts_identity_conflict")
        index[row["id"]] = row
        dbf = row.get("dbf_id")
        if dbf is not None:
            if dbf in dbfs and dbfs[dbf] != row["id"]:
                raise ValueError("starter_card_facts_identity_conflict")
            dbfs[dbf] = row["id"]
    analysis = analysis_cards_from_deck_identity({"cards": cards, "sideboards": boards})
    relevant = {row["card_id"] for row in analysis}
    if not relevant <= index.keys():
        raise ValueError("starter_card_facts_required_identity_unresolved")
    enriched = enrich_card_metadata(
        {"cards": [{**index[row["card_id"]], **row} for row in analysis]},
        hearthstonejson_cards=full_cards,
    )["cards"]
    semantic = {row["card_id"]: row for row in enriched}
    relations = []
    for card in enriched:
        source = card["card_id"]
        raw = index[source]
        candidates = [
            (link["link_kind"], link.get("card_id"))
            for link in card.get("linked_entities", [])
        ]
        candidates += [("entourage", target) for target in raw.get("entourage", [])]
        candidates += [("child", target) for target in raw.get("child_ids", [])]
        if raw.get("quest_reward"):
            candidates.append(("quest_reward", raw["quest_reward"]))
        if raw.get("hero_power_dbf_id") is not None:
            candidates.append(
                ("starting_hero_power", dbfs.get(raw["hero_power_dbf_id"]))
            )
        if "random" in str(raw.get("text", "")).lower():
            candidates.append(("random_pool", None))
        for kind, target in candidates:
            if target is not None and target not in index and str(target).isdigit():
                target = dbfs.get(int(target))
            status = (
                "random"
                if kind == "random_pool"
                else ("resolved" if target in index else "unresolved")
            )
            relation = {
                "source_card_id": source,
                "card_id": target,
                "link_kind": kind,
                "status": status,
            }
            if relation not in relations:
                relations.append(relation)
            if status == "resolved":
                relevant.add(target)
    metadata = {}
    for card_id in sorted(relevant):
        raw = index[card_id]
        present = set(raw.get("source_fields", []))
        facts = {
            "missing_fields": [],
            "inapplicable_fields": [],
            "mechanic_families": sorted(
                set(semantic.get(card_id, {}).get("semantic_families", []))
            ),
        }
        for field, aliases in _ALIASES.items():
            value = raw.get(field)
            if _inapplicable(field, raw.get("type")) and not (aliases & present):
                facts["inapplicable_fields"].append(field)
                value = None
            elif not aliases & present or value is None:
                facts["missing_fields"].append(field)
                value = None
            if isinstance(value, str):
                value = _text(value)
            facts[field] = value
        facts["missing_fields"].sort()
        facts["inapplicable_fields"].sort()
        metadata[card_id] = facts
    result = {
        "cards": cards,
        "card_metadata": metadata,
        "sideboards": sideboards,
        "linked_entities": relations,
    }
    validate_card_facts(result)
    return result


def validate_card_facts(value: dict) -> None:
    """Validate the closed schema-3 facts projection without source observation."""
    if type(value) is not dict or set(value) != {
        "cards", "card_metadata", "sideboards", "linked_entities"
    }:
        raise ValueError("starter_card_facts_fields_invalid")
    if any(type(value[field]) is not list for field in ("cards", "sideboards", "linked_entities")):
        raise ValueError("starter_card_facts_fields_invalid")
    metadata = value["card_metadata"]
    if type(metadata) is not dict or not metadata:
        raise ValueError("starter_card_facts_metadata_invalid")
    main_ids = set()
    for row in value["cards"]:
        if set(row) != {"card_id", "count"} or _membership(row) != row:
            raise ValueError("starter_card_facts_membership_invalid")
        if row["card_id"] in main_ids or row["card_id"] not in metadata:
            raise ValueError("starter_card_facts_membership_invalid")
        main_ids.add(row["card_id"])
    if not main_ids:
        raise ValueError("starter_card_facts_membership_invalid")
    relevant = set(main_ids)
    board_owners = {}
    seen = set()
    for row in value["sideboards"]:
        if (
            set(row) != {"owner_card_id", "index", "card_id", "count"}
            or row["owner_card_id"] not in main_ids
            or type(row["index"]) is not int
            or row["index"] < 1
            or row["card_id"] not in metadata
        ):
            raise ValueError("starter_card_facts_sideboard_invalid")
        _membership(row)
        key = (row["index"], row["card_id"])
        if (
            key in seen
            or board_owners.get(row["index"], row["owner_card_id"])
            != row["owner_card_id"]
        ):
            raise ValueError("starter_card_facts_sideboard_invalid")
        seen.add(key)
        board_owners[row["index"]] = row["owner_card_id"]
        relevant.add(row["card_id"])
    if len(set(board_owners.values())) != len(board_owners):
        raise ValueError("starter_card_facts_sideboard_invalid")
    sources = set(relevant)
    seen_relations = set()
    for row in value["linked_entities"]:
        if (
            set(row) != RELATION_FIELDS
            or row["source_card_id"] not in sources
            or row["status"] not in {"resolved", "unresolved", "random"}
            or not isinstance(row["link_kind"], str)
            or re.fullmatch(r"[a-z_]+", row["link_kind"]) is None
            or (
                row["card_id"] is not None
                and (
                    not isinstance(row["card_id"], str)
                    or re.fullmatch(r"[A-Za-z0-9_]+", row["card_id"]) is None
                )
            )
        ):
            raise ValueError("starter_card_facts_relation_invalid")
        key = tuple(row[field] for field in sorted(RELATION_FIELDS))
        if key in seen_relations:
            raise ValueError("starter_card_facts_relation_invalid")
        seen_relations.add(key)
        if row["status"] == "resolved":
            if row["card_id"] not in metadata:
                raise ValueError("starter_card_facts_relation_invalid")
            relevant.add(row["card_id"])
        elif row["status"] == "random" and row["card_id"] is not None:
            raise ValueError("starter_card_facts_relation_invalid")
    if relevant != metadata.keys():
        raise ValueError("starter_card_facts_metadata_invalid")
    dbfs = set()
    for card_id, row in metadata.items():
        if (
            re.fullmatch(r"[A-Za-z0-9_]+", card_id) is None
            or set(row) != CARD_FACT_FIELDS
        ):
            raise ValueError("starter_card_facts_metadata_invalid")
        missing, inapplicable = row["missing_fields"], row["inapplicable_fields"]
        for fields in (missing, inapplicable):
            if (
                type(fields) is not list
                or any(type(field) is not str for field in fields)
                or fields != sorted(set(fields))
                or not set(fields) <= _ALIASES.keys()
            ):
                raise ValueError("starter_card_facts_fields_invalid")
        if set(missing) & set(inapplicable):
            raise ValueError("starter_card_facts_fields_invalid")
        for field in _ALIASES:
            item = row[field]
            if (item is None) != (field in missing or field in inapplicable):
                raise ValueError("starter_card_facts_null_invalid")
            if field in inapplicable and not _inapplicable(field, row["type"]):
                raise ValueError("starter_card_facts_applicability_invalid")
            if item is None:
                continue
            if field in {"dbf_id", "cost", "attack", "health", "durability"}:
                if type(item) is not int or item < (1 if field == "dbf_id" else 0):
                    raise ValueError("starter_card_facts_number_invalid")
            elif field in {"races", "classes", "mechanics"}:
                if type(item) is not list or any(
                    type(token) is not str
                    or re.fullmatch(r"[A-Za-z0-9_]+", token) is None
                    for token in item
                ):
                    raise ValueError("starter_card_facts_tokens_invalid")
            elif field == "play_requirements":
                if type(item) is not dict or any(
                    type(key) is not str
                    or re.fullmatch(r"[A-Za-z0-9_]+", key) is None
                    or type(number) is not int
                    for key, number in item.items()
                ):
                    raise ValueError("starter_card_facts_requirements_invalid")
            elif field in {"type", "spell_school"}:
                if (
                    type(item) is not str
                    or re.fullmatch(r"[A-Za-z0-9_]+", item) is None
                ):
                    raise ValueError("starter_card_facts_tokens_invalid")
            elif type(item) is not str or _text(item) != item:
                raise ValueError("starter_card_facts_text_invalid")
        if row["dbf_id"] is not None:
            if row["dbf_id"] in dbfs:
                raise ValueError("starter_card_facts_identity_conflict")
            dbfs.add(row["dbf_id"])
        families = row["mechanic_families"]
        if (
            type(families) is not list
            or any(
                type(token) is not str or re.fullmatch(r"[A-Za-z0-9_]+", token) is None
                for token in families
            )
            or families != sorted(set(families))
        ):
            raise ValueError("starter_card_facts_tokens_invalid")
