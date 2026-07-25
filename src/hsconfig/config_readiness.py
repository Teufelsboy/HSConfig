from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping

from hsconfig.mechanic_support import (
    support_for_roles,
    summarize_mechanic_support,
    summarize_mechanic_visibility,
)
from hsconfig.io import slugify_deck_name


RUNTIME_SURFACE_MULLIGAN = "Mulligan.json"
RUNTIME_SURFACE_COMBO = "Combo.json"
RUNTIME_SURFACE_GLOBALVALUES = "GlobalValues.json"
CARDID_SURFACE_FAMILY = "CARDID.json"
CARDID_SURFACE_ALIASES = {"CARDID.json", "CardID.json"}

LANES = (
    "runtime_emitted",
    "mulligan_only",
    "globalvalues_only",
    "report_only_supported",
    "archetype_inferred",
    "generic_low_confidence",
)
MISSING_LINKS = (
    "none",
    "needs_guide_claim",
    "needs_runtime_surface",
    "needs_mulligan_claim",
    "needs_combo_sequence",
    "needs_condition_lowering",
    "needs_mechanic_lowering",
)
SOURCE_DEPTH_LANE_BY_MISSING_LINK = {
    "none": "closed",
    "needs_guide_claim": "source_claim_gap",
    "needs_runtime_surface": "runtime_surface_gap",
    "needs_mulligan_claim": "mulligan_claim_gap",
    "needs_combo_sequence": "combo_sequence_gap",
    "needs_condition_lowering": "condition_lowering_gap",
    "needs_mechanic_lowering": "mechanic_lowering_gap",
}
GUIDE_BACKED_COVERAGE_STATUSES = {
    "guide_backed",
    "source_backed",
    "source_backed_static_semantics",
}
GLOBALVALUES_SUFFICIENT_ROLES = {"hero_power_transform"}
READINESS_MECHANIC_SUPPORT_INTERNAL_KEYS = {"role", "support_bucket"}


def build_config_readiness_report(
    *,
    deck_identity: dict[str, Any],
    claim_coverage: dict[str, Any],
    gameplan_contract: dict[str, Any],
    mulligan_plan: dict[str, Any],
    card_behavior_plan: dict[str, Any],
    combo_plan: dict[str, Any],
    global_values_authority_matrix: dict[str, Any],
    emitted_cardid_files: list[str] | tuple[str, ...] | set[str] | None = None,
) -> dict[str, Any]:
    cards = _cards_from_deck(deck_identity, gameplan_contract)
    uncovered = {str(card) for card in claim_coverage.get("uncovered_cards", [])}
    all_cardid_cards = _cards_from_any_card_behavior(card_behavior_plan)
    concrete_cardid_cards = _cards_from_card_behavior(card_behavior_plan)
    emitted_cardid_file_map = _emitted_cardid_file_map(
        emitted_cardid_files,
        fallback_cardids=all_cardid_cards,
    )
    emitted_cardid_cards = set(emitted_cardid_file_map) & concrete_cardid_cards
    unsupported_condition_cards = _cards_from_unsupported_condition_suppression(
        card_behavior_plan
    )
    mulligan_cards = _cards_from_mulligan(mulligan_plan)
    suppressed_mulligan_cards = _cards_from_suppressed_mulligan(mulligan_plan)
    combo_cards = _cards_from_combos(combo_plan)
    globalvalue_cards = _cards_from_globalvalues(
        gameplan_contract,
        global_values_authority_matrix,
    )

    rows: dict[str, dict[str, Any]] = {}
    lane_counter: Counter[str] = Counter()
    missing_counter: Counter[str] = Counter()

    for card_id, card in sorted(cards.items()):
        mechanic_support = _readiness_mechanic_support(card.get("roles", []))
        runtime_surfaces = _runtime_surfaces(
            card_id=card_id,
            emitted_cardid_file_map=emitted_cardid_file_map,
            mulligan_cards=mulligan_cards,
            combo_cards=combo_cards,
            globalvalue_cards=globalvalue_cards,
        )
        lane, missing = _lane_and_missing_link(
            card_id=card_id,
            card=card,
            uncovered=uncovered,
            concrete_cardid_cards=concrete_cardid_cards,
            emitted_cardid_cards=emitted_cardid_cards,
            unsupported_condition_cards=unsupported_condition_cards,
            mulligan_cards=mulligan_cards,
            suppressed_mulligan_cards=suppressed_mulligan_cards,
            combo_cards=combo_cards,
            globalvalue_cards=globalvalue_cards,
        )

        lane_counter[lane] += 1
        if missing != "none":
            missing_counter[missing] += 1

        rows[card_id] = {
            "card_id": card_id,
            "name": str(card.get("name", card_id)),
            "count": int(card.get("count", 1)),
            "coverage_status": str(card.get("coverage_status", card.get("confidence", ""))),
            "roles": [str(role) for role in card.get("roles", [])],
            "source_claim_ids": [str(item) for item in card.get("source_claim_ids", [])],
            "mechanic_support": mechanic_support,
            "runtime_surfaces": runtime_surfaces,
            "readiness_lane": lane,
            "first_missing_link": missing,
            "source_depth_lane": _source_depth_lane(missing),
        }

    deck_name = str(deck_identity.get("deck_name", gameplan_contract.get("deck_name", "Deck")))
    deck_slug = str(
        deck_identity.get(
            "deck_slug",
            gameplan_contract.get("deck_slug", slugify_deck_name(deck_name)),
        )
    )
    return {
        "deck_name": deck_name,
        "deck_slug": deck_slug,
        "summary": _summary(
            total_cards=len(rows),
            lane_counter=lane_counter,
            missing_counter=missing_counter,
            rows=rows.values(),
        ),
        "cards": rows,
    }


def _cards_from_deck(
    deck_identity: dict[str, Any],
    gameplan_contract: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {}
    for card in deck_identity.get("cards", []):
        if not isinstance(card, dict) or not card.get("card_id"):
            continue
        card_id = str(card["card_id"])
        cards[card_id] = {"card_id": card_id, **dict(card)}

    contract_cards = gameplan_contract.get("cards", {})
    if isinstance(contract_cards, dict):
        for card_id, card in contract_cards.items():
            if not isinstance(card, dict):
                continue
            normalized_id = str(card.get("card_id", card_id))
            cards[normalized_id] = {**cards.get(normalized_id, {}), **dict(card)}
            cards[normalized_id]["card_id"] = normalized_id

    return cards


def _readiness_mechanic_support(roles: Iterable[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in support_for_roles(roles):
        rows.append(
            {
                key: value
                for key, value in row.items()
                if key not in READINESS_MECHANIC_SUPPORT_INTERNAL_KEYS
            }
        )
    return rows


def _cards_from_any_card_behavior(card_behavior_plan: dict[str, Any]) -> set[str]:
    return {
        str(row["card_id"])
        for row in card_behavior_plan.get("rows", [])
        if _is_cardid_runtime_row(row)
    }


def _cards_from_card_behavior(card_behavior_plan: dict[str, Any]) -> set[str]:
    return {
        str(row["card_id"])
        for row in card_behavior_plan.get("rows", [])
        if _is_meaningful_cardid_runtime_row(row)
    }


def _is_meaningful_cardid_runtime_row(row: Any) -> bool:
    return (
        _is_cardid_runtime_row(row)
        and row.get("meaningful_runtime_surface") is True
        and bool(row.get("behavior_block"))
    )


def _emitted_cardid_file_map(
    emitted_cardid_files: list[str] | tuple[str, ...] | set[str] | None,
    *,
    fallback_cardids: set[str],
) -> dict[str, str]:
    if emitted_cardid_files is None:
        return {card_id: f"{card_id}.json" for card_id in fallback_cardids}

    file_map: dict[str, str] = {}
    for emitted_file in emitted_cardid_files:
        filename = str(emitted_file).replace("\\", "/").rsplit("/", 1)[-1]
        if not filename.endswith(".json"):
            continue
        card_id = filename.removesuffix(".json")
        if not card_id:
            continue
        file_map[card_id] = filename
    return file_map


def _is_cardid_runtime_row(row: Any) -> bool:
    return (
        isinstance(row, dict)
        and bool(row.get("card_id"))
        and (
            row.get("surface_family") == CARDID_SURFACE_FAMILY
            or row.get("surface") in CARDID_SURFACE_ALIASES
        )
    )


def _cards_from_unsupported_condition_suppression(
    card_behavior_plan: dict[str, Any],
) -> set[str]:
    cards: set[str] = set()
    for row in card_behavior_plan.get("suppressed", []):
        if not isinstance(row, dict) or row.get("reason") != "unsupported_condition":
            continue
        for key in ("card_id", "card"):
            if row.get(key):
                cards.add(str(row[key]))
        suppressed_cards = row.get("cards", [])
        if isinstance(suppressed_cards, str):
            suppressed_cards = [suppressed_cards]
        cards.update(str(card) for card in suppressed_cards if str(card))
    return cards


def _cards_from_mulligan(mulligan_plan: dict[str, Any]) -> set[str]:
    cards: set[str] = set()
    for row in mulligan_plan.get("rules", []):
        if not isinstance(row, dict):
            continue
        selector_cards = _normalize_card_list(row.get("selector_cards", row.get("cards", [])))
        if selector_cards:
            cards.update(card for card in selector_cards if card != "*")
            continue
        if row.get("card") and str(row["card"]) != "*":
            cards.add(str(row["card"]))
    return cards


def _cards_from_suppressed_mulligan(mulligan_plan: dict[str, Any]) -> set[str]:
    cards: set[str] = set()
    for row in mulligan_plan.get("suppressed_rules", []):
        if not isinstance(row, dict):
            continue
        if row.get("reason") != "claim_not_runtime_lowerable":
            continue
        selector_cards = _normalize_card_list(row.get("selector_cards", row.get("cards", [])))
        if selector_cards:
            cards.update(card for card in selector_cards if card != "*")
            continue
        if row.get("card") and str(row["card"]) != "*":
            cards.add(str(row["card"]))
    return cards


def _normalize_card_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(card) for card in value if str(card)]


def _cards_from_combos(combo_plan: dict[str, Any]) -> set[str]:
    cards: set[str] = set()
    for combo in combo_plan.get("combos", []):
        if not isinstance(combo, dict):
            continue
        combo_cards = combo.get("cards", [])
        if isinstance(combo_cards, str):
            combo_cards = [combo_cards]
        cards.update(str(card) for card in combo_cards if str(card))
    return cards


def _cards_from_globalvalues(
    gameplan_contract: dict[str, Any],
    global_values_authority_matrix: dict[str, Any],
) -> set[str]:
    allowed_overlays = [
        row
        for row in global_values_authority_matrix.get("allowed_step1_overlays", [])
        if isinstance(row, dict) and row.get("key") != "baseline"
    ]
    if not allowed_overlays:
        return set()

    cards: set[str] = set()
    for effect in gameplan_contract.get("deckwide_effects", []):
        if isinstance(effect, dict) and effect.get("source_card_id"):
            cards.add(str(effect["source_card_id"]))
    for expectation in gameplan_contract.get("hero_power_expectations", []):
        if isinstance(expectation, dict) and expectation.get("source_card_id"):
            cards.add(str(expectation["source_card_id"]))
    return cards


def _runtime_surfaces(
    *,
    card_id: str,
    emitted_cardid_file_map: dict[str, str],
    mulligan_cards: set[str],
    combo_cards: set[str],
    globalvalue_cards: set[str],
) -> list[str]:
    surfaces = []
    if card_id in emitted_cardid_file_map:
        surfaces.append(emitted_cardid_file_map[card_id])
    if card_id in mulligan_cards:
        surfaces.append(RUNTIME_SURFACE_MULLIGAN)
    if card_id in combo_cards:
        surfaces.append(RUNTIME_SURFACE_COMBO)
    if card_id in globalvalue_cards:
        surfaces.append(RUNTIME_SURFACE_GLOBALVALUES)
    return surfaces


def _lane_and_missing_link(
    *,
    card_id: str,
    card: dict[str, Any],
    uncovered: set[str],
    concrete_cardid_cards: set[str],
    emitted_cardid_cards: set[str],
    unsupported_condition_cards: set[str],
    mulligan_cards: set[str],
    suppressed_mulligan_cards: set[str],
    combo_cards: set[str],
    globalvalue_cards: set[str],
) -> tuple[str, str]:
    coverage = str(card.get("coverage_status", card.get("confidence", ""))).lower()
    roles = {str(role).lower() for role in card.get("roles", [])}
    is_guide_backed = coverage in GUIDE_BACKED_COVERAGE_STATUSES

    if card_id in uncovered or coverage == "generic_low_confidence":
        return "generic_low_confidence", "needs_guide_claim"
    if coverage == "archetype_inferred":
        return "archetype_inferred", "needs_guide_claim"
    if is_guide_backed and card_id in suppressed_mulligan_cards:
        return "report_only_supported", "needs_mulligan_claim"
    if card_id in concrete_cardid_cards or card_id in combo_cards:
        return "runtime_emitted", "none"
    if card_id in mulligan_cards:
        if is_guide_backed and _has_source_claim_ids(card):
            return "mulligan_only", "none"
        return "mulligan_only", "needs_runtime_surface"
    if card_id in globalvalue_cards:
        if is_guide_backed and roles and roles <= GLOBALVALUES_SUFFICIENT_ROLES:
            return "globalvalues_only", "none"
        return "globalvalues_only", "needs_runtime_surface"
    if card_id in unsupported_condition_cards:
        return "report_only_supported", "needs_condition_lowering"
    if is_guide_backed and "mulligan_anchor" in roles:
        return "report_only_supported", "needs_mulligan_claim"
    if is_guide_backed and "combo_piece" in roles:
        return "report_only_supported", "needs_combo_sequence"
    if _roles_need_mechanic_lowering(roles):
        return "report_only_supported", "needs_mechanic_lowering"
    if card_id in emitted_cardid_cards:
        return "report_only_supported", "none"
    return "report_only_supported", "needs_runtime_surface"


def _roles_need_mechanic_lowering(roles: set[str]) -> bool:
    for support in support_for_roles(roles):
        lowering = support.get("lowering", {})
        if not isinstance(lowering, dict):
            continue
        if lowering.get("policy") == "report_only":
            continue
        if lowering.get("default_block") is not None:
            return True
    return False


def _has_source_claim_ids(card: Mapping[str, Any]) -> bool:
    value = card.get("source_claim_ids", [])
    if isinstance(value, str):
        return bool(value.strip())
    return isinstance(value, list) and any(str(item).strip() for item in value)


def _source_depth_lane(first_missing_link: str) -> str:
    return SOURCE_DEPTH_LANE_BY_MISSING_LINK.get(first_missing_link, "inspect_card_gap")


def _summary(
    *,
    total_cards: int,
    lane_counter: Counter[str],
    missing_counter: Counter[str],
    rows: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "total_cards": total_cards,
        **{lane: lane_counter[lane] for lane in LANES},
        "cards_needing_guide_claims": missing_counter["needs_guide_claim"],
        "cards_needing_runtime_surface": missing_counter["needs_runtime_surface"],
        "cards_needing_mulligan_claims": missing_counter["needs_mulligan_claim"],
        "cards_needing_combo_sequence": missing_counter["needs_combo_sequence"],
        "cards_needing_condition_lowering": missing_counter["needs_condition_lowering"],
        "cards_needing_mechanic_lowering": missing_counter["needs_mechanic_lowering"],
        "mechanic_support": summarize_mechanic_support(rows),
        "mechanic_visibility": summarize_mechanic_visibility(rows),
    }
