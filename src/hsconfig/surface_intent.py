from __future__ import annotations

from typing import Any

from hsconfig.card_intent_taxonomy import classify_card_intent


def build_surface_intent(contract: dict[str, Any]) -> dict[str, Any]:
    rows = [
        {
            "rule_id": "globalvalues_full_key_profile",
            "card_id": None,
            "surface": "GlobalValues.json",
            "intent": "profile_and_overlay_full_global_values",
            "source_claim_ids": _all_source_claim_ids(contract),
        }
    ]
    required_surfaces = {"GlobalValues.json", "Mulligan.json"}
    optional_surfaces: set[str] = set()

    for card_id, card in _cards(contract).items():
        surface = f"{card_id}.json"
        required_surfaces.add(surface)
        diagnostic_intent = _diagnostic_card_intent(card)
        rows.append(
            {
                "rule_id": f"{card_id}_card_behavior",
                "card_id": card_id,
                "surface": surface,
                "surface_family": "CARDID.json",
                "intent": diagnostic_intent["intent"],
                "intent_source": diagnostic_intent["source"],
                "roles": list(card.get("roles", [])),
                "confidence": card.get("confidence", card.get("coverage_status", "generic_low_confidence")),
                "source_claim_ids": list(card.get("source_claim_ids", [])),
            }
        )

    for anchor in contract.get("mulligan_anchors", []):
        card_id = str(anchor["card_id"])
        rows.append(
            {
                "rule_id": f"{card_id}_mulligan_hold",
                "card_id": card_id,
                "surface": "Mulligan.json",
                "intent": "hold",
                "condition": anchor.get("condition", "*"),
                "confidence": anchor.get("confidence", "source_backed"),
                "source_claim_ids": list(anchor.get("source_claim_ids", [])),
            }
        )

    if contract.get("combos"):
        optional_surfaces.add("Combo.json")
        rows.append(
            {
                "rule_id": "combo_sequences",
                "card_id": None,
                "surface": "Combo.json",
                "intent": "same_turn_combo_sequences",
                "source_claim_ids": _combo_claim_ids(contract),
            }
        )

    minimum_required_runtime_surfaces = ["GlobalValues.json", "Mulligan.json"]
    existing_runtime_surfaces = required_surfaces | optional_surfaces
    rich_optional_runtime_surfaces = sorted(
        surface
        for surface in existing_runtime_surfaces
        if surface not in minimum_required_runtime_surfaces
        and surface not in {"Presume.json", "Concede.json"}
    )

    return {
        "rows": rows,
        "required_surfaces": sorted(required_surfaces),
        "optional_surfaces": sorted(optional_surfaces),
        "minimum_required_runtime_surfaces": minimum_required_runtime_surfaces,
        "rich_optional_runtime_surfaces": rich_optional_runtime_surfaces,
        "surface_count": len(required_surfaces) + len(optional_surfaces),
    }


def _cards(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cards = contract.get("cards", {})
    if isinstance(cards, dict):
        return {str(card_id): dict(card) for card_id, card in sorted(cards.items())}
    return {str(card["card_id"]): dict(card) for card in sorted(cards, key=lambda row: row["card_id"])}


def _all_source_claim_ids(contract: dict[str, Any]) -> list[str]:
    return sorted(
        {
            str(claim_id)
            for card in _cards(contract).values()
            for claim_id in card.get("source_claim_ids", [])
        }
    )


def _combo_claim_ids(contract: dict[str, Any]) -> list[str]:
    return sorted(
        {
            str(claim_id)
            for combo in contract.get("combos", [])
            for claim_id in combo.get("source_claim_ids", [])
        }
    )


def _diagnostic_card_intent(card: dict[str, Any]) -> dict[str, str]:
    text = _card_intent_text(card)
    classification = classify_card_intent(text)
    if classification.reason == "semantic_default":
        return {"intent": "aggressive_card_behavior", "source": "fallback"}
    return {"intent": classification.reason, "source": "card_intent_taxonomy"}


def _card_intent_text(card: dict[str, Any]) -> str:
    parts = [
        card.get("claim_kind"),
        card.get("stance"),
        card.get("intent"),
        card.get("mechanic"),
        card.get("evidence_text_short"),
        card.get("source_title"),
        " ".join(str(role) for role in card.get("roles", [])),
        " ".join(str(family) for family in card.get("semantic_families", [])),
    ]
    return " ".join(str(part).lower() for part in parts if part is not None)
