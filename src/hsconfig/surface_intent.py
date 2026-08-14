from __future__ import annotations

from typing import Any, Mapping

from hsconfig.card_intent_taxonomy import classify_card_intent
from hsconfig.runtime_entity_owner import partition_runtime_entity_owner_rows


def build_surface_intent(
    contract: dict[str, Any],
    *,
    mulligan_plan_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    accepted_behavior_rows, owner_collisions = (
        partition_runtime_entity_owner_rows(
            row
            for row in _card_behavior_rows(contract)
            if isinstance(row, Mapping)
        )
    )
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
        diagnostic_intent = _diagnostic_card_intent(card_id, card)
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

    for runtime_card_id, ownership in _linked_runtime_entities(
        accepted_behavior_rows
    ).items():
        surface = f"{runtime_card_id}.json"
        if surface in required_surfaces:
            continue
        required_surfaces.add(surface)
        rows.append(
            {
                "rule_id": f"{runtime_card_id}_card_behavior",
                "card_id": runtime_card_id,
                "source_card_id": ownership["source_card_id"],
                "runtime_card_id": runtime_card_id,
                "link_kind": ownership["link_kind"],
                "owner_kind": "linked_runtime_entity",
                "surface": surface,
                "surface_family": "CARDID.json",
                "intent": "linked_runtime_entity_behavior",
                "intent_source": "runtime_entity_owner",
                "roles": [ownership["link_kind"]],
                "confidence": ownership["confidence"],
                "source_claim_ids": ownership["source_claim_ids"],
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

    delegated = (
        mulligan_plan_report.get("bot_delegated", ())
        if isinstance(mulligan_plan_report, Mapping)
        else ()
    )
    for delegation in delegated if isinstance(delegated, list) else ():
        if not isinstance(delegation, Mapping):
            continue
        card_id = str(delegation.get("card_id", "")).strip()
        if not card_id:
            continue
        rows.append(
            {
                "rule_id": f"{card_id}_mulligan_bot_delegation",
                "card_id": card_id,
                "surface": "Mulligan.json",
                "intent": "delegate_to_hearthranger_bot",
                "intent_source": "versioned_internal_policy",
                "confidence": "policy_backed",
                "evidence_lane": str(
                    delegation.get("evidence_lane", "")
                ),
                "policy_id": str(delegation.get("policy_id", "")),
                "reason_code": str(
                    delegation.get("reason_code", "")
                ),
                "source_claim_ids": [],
            }
        )

    lowerable_combos = [
        combo
        for combo in contract.get("combos", [])
        if isinstance(combo, Mapping) and _combo_claim_is_runtime_lowerable(combo)
    ]
    if lowerable_combos:
        optional_surfaces.add("Combo.json")
        rows.append(
            {
                "rule_id": "combo_sequences",
                "card_id": None,
                "surface": "Combo.json",
                "intent": "same_turn_combo_sequences",
                "source_claim_ids": _combo_claim_ids(lowerable_combos),
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
        "runtime_entity_owner_collisions": owner_collisions,
    }


def _cards(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cards = contract.get("cards", {})
    if isinstance(cards, dict):
        return {str(card_id): dict(card) for card_id, card in sorted(cards.items())}
    return {str(card["card_id"]): dict(card) for card in sorted(cards, key=lambda row: row["card_id"])}


def _card_behavior_rows(contract: Mapping[str, Any]) -> list[Any]:
    card_behavior_plan = contract.get("card_behavior_plan", {})
    if not isinstance(card_behavior_plan, Mapping):
        return []
    rows = card_behavior_plan.get("rows", [])
    return rows if isinstance(rows, list) else []


def _linked_runtime_entities(
    rows: list[Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    linked: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        source_card_id = str(
            row.get("source_card_id") or row.get("card_id") or ""
        ).strip()
        runtime_card_id = str(
            row.get("runtime_card_id") or row.get("card_id") or ""
        ).strip()
        link_kind = str(row.get("link_kind") or "self").strip()
        if (
            row.get("meaningful_runtime_surface") is not True
            or not source_card_id
            or not runtime_card_id
            or source_card_id == runtime_card_id
            or link_kind == "self"
        ):
            continue
        current = linked.setdefault(
            runtime_card_id,
            {
                "source_card_id": source_card_id,
                "link_kind": link_kind,
                "confidence": str(
                    row.get("confidence") or "source_backed"
                ),
                "source_claim_ids": [],
            },
        )
        current["source_claim_ids"] = sorted(
            {
                *current["source_claim_ids"],
                *[
                    str(claim_id)
                    for claim_id in row.get("source_claim_ids", [])
                ],
            }
        )
    return dict(sorted(linked.items()))


def _all_source_claim_ids(contract: dict[str, Any]) -> list[str]:
    return sorted(
        {
            str(claim_id)
            for card in _cards(contract).values()
            for claim_id in card.get("source_claim_ids", [])
        }
    )


def _combo_claim_ids(combos: list[Mapping[str, Any]]) -> list[str]:
    return sorted(
        {
            str(claim_id)
            for combo in combos
            for claim_id in combo.get("source_claim_ids", [])
        }
    )


def _combo_claim_is_runtime_lowerable(combo: Mapping[str, Any]) -> bool:
    if combo.get("suppressed_reason"):
        return False
    if combo.get("runtime_lowering_status") in {"emitted", "runtime_lowered"}:
        return True
    if combo.get("runtime_surface") == "Combo.json":
        return True
    qualifiers = combo.get("semantic_qualifiers")
    qualifier_timing = (
        qualifiers.get("timing") or qualifiers.get("sequence_timing")
        if isinstance(qualifiers, Mapping)
        else None
    )
    timing = str(
        combo.get("timing")
        or combo.get("timing_kind")
        or combo.get("sequence_timing")
        or qualifier_timing
        or ""
    ).strip()
    cards = combo.get("cards") or combo.get("card_ids") or []
    return timing in {"same_turn", "ordered", "exact_order"} and len(cards) >= 2


def _diagnostic_card_intent(card_id: str, card: dict[str, Any]) -> dict[str, str]:
    text = _card_intent_text(card)
    classification = classify_card_intent(
        text,
        card_identity=card_id or str(card.get("name") or ""),
    )
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
        " ".join(str(role) for role in card.get("roles", [])),
        " ".join(str(family) for family in card.get("semantic_families", [])),
        " ".join(str(family) for family in card.get("mechanic_families", [])),
    ]
    return " ".join(str(part).lower() for part in parts if part is not None)
