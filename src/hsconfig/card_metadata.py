from __future__ import annotations

from typing import Any

from hsconfig.static_semantics import infer_static_semantics


def assign_mechanic_families(card: dict[str, Any]) -> list[str]:
    return infer_static_semantics(card)["families"]


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
        metadata_status = "source_record" if source else "missing_source_record"
        if not source:
            missing_count += 1
        merged = {
            "card_id": card_id,
            "dbf_id": int(dbf_id) if dbf_id is not None else None,
            "count": int(card.get("count", 1)),
            "name": source.get("name", card_id),
            "cost": source.get("cost"),
            "type": source.get("type", card.get("type", "UNKNOWN")),
            "card_class": source.get("card_class", source.get("class")),
            "text": source.get("text", ""),
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
            "source_record_key": source_key if source else None,
        }
        semantic_result = infer_static_semantics(merged)
        merged["mechanic_families"] = semantic_result["families"]
        merged["static_semantic_evidence"] = semantic_result["evidence"]
        merged["warning_only_mechanics"] = semantic_result["warning_only"]
        hydrated.append(merged)
    return {"cards": hydrated, "unresolved_metadata_count": missing_count}
