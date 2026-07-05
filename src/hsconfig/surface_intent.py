from __future__ import annotations

from typing import Any


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
        rows.append(
            {
                "rule_id": f"{card_id}_card_behavior",
                "card_id": card_id,
                "surface": surface,
                "surface_family": "CARDID.json",
                "intent": "aggressive_card_behavior",
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

    policies = contract.get("policies", {}) if contract.get("legacy_policy_surfaces_enabled") else {}
    if policies.get("presume"):
        optional_surfaces.add("Presume.json")
        rows.append(
            {
                "rule_id": "presume_policy",
                "card_id": None,
                "surface": "Presume.json",
                "intent": "presume_policy",
                "source_claim_ids": _policy_claim_ids(policies["presume"]),
            }
        )
    if policies.get("concede"):
        optional_surfaces.add("Concede.json")
        rows.append(
            {
                "rule_id": "concede_policy",
                "card_id": None,
                "surface": "Concede.json",
                "intent": "concede_policy",
                "source_claim_ids": _policy_claim_ids(policies["concede"]),
            }
        )

    return {
        "rows": rows,
        "required_surfaces": sorted(required_surfaces),
        "optional_surfaces": sorted(optional_surfaces),
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


def _policy_claim_ids(rows: list[dict[str, Any]]) -> list[str]:
    return sorted({str(claim_id) for row in rows for claim_id in row.get("source_claim_ids", [])})
