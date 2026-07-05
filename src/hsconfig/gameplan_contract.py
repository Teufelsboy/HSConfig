from __future__ import annotations

from typing import Any

from hsconfig.guide_research import normalize_source_claims
from hsconfig.io import slugify_deck_name


NEGATIVE_KEEP_MARKERS = (
    "never keep",
    "do not keep",
    "don't keep",
    "dont keep",
    "avoid keeping",
    "avoid keep",
)


def build_gameplan_contract(
    deck_identity: dict[str, Any] | None = None,
    card_metadata: dict[str, Any] | list[dict[str, Any]] | None = None,
    source_claims: dict[str, Any] | list[dict[str, Any]] | None = None,
    *,
    deck_name: str | None = None,
    cards: list[dict[str, Any]] | None = None,
    claims: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if deck_identity is None:
        deck_identity = {"deck_name": deck_name or "Deck", "cards": cards or []}
    if card_metadata is None:
        card_metadata = {"cards": cards or deck_identity.get("cards", [])}
    if source_claims is None:
        source_claims = claims

    deck_cards = _deck_cards(deck_identity)
    metadata_by_card = _metadata_by_card(card_metadata)
    normalized_claims = _coerce_source_claims(source_claims)
    claim_rows = normalized_claims["claims"]
    claims_by_card = _claims_by_card(claim_rows)

    card_map: dict[str, dict[str, Any]] = {}
    role_rows: list[dict[str, Any]] = []
    usage_expectations: dict[str, dict[str, Any]] = {}
    mulligan_anchors: list[dict[str, Any]] = []
    known_bad_patterns: list[dict[str, Any]] = []

    for deck_card in deck_cards:
        card_id = str(deck_card["card_id"])
        metadata = metadata_by_card.get(card_id, {})
        related_claims = claims_by_card.get(card_id, [])
        mechanic_families = sorted(
            {
                str(item)
                for item in metadata.get(
                    "mechanic_families", deck_card.get("mechanic_families", [])
                )
            }
        )
        semantic_families = sorted(
            {
                *mechanic_families,
                *[str(item) for item in metadata.get("semantic_families", [])],
            }
        )
        roles = _infer_roles(semantic_families, related_claims)
        coverage_status = "source_backed" if related_claims else "generic_low_confidence"
        source_claim_ids = [str(claim["claim_id"]) for claim in related_claims]
        card_record = {
            "card_id": card_id,
            "name": metadata.get("name", deck_card.get("name", card_id)),
            "count": int(deck_card.get("count", metadata.get("count", 1))),
            "mechanic_families": mechanic_families,
            "semantic_families": semantic_families,
            "linked_entities": list(metadata.get("linked_entities", [])),
            "roles": roles,
            "coverage_status": coverage_status,
            "confidence": coverage_status,
            "source_claim_ids": source_claim_ids,
        }
        card_map[card_id] = card_record
        role_rows.append(card_record)

        expectation = {
            "card_id": card_id,
            "expected_use": _infer_expected_use(roles, related_claims),
            "coverage_status": coverage_status,
            "source_claim_ids": source_claim_ids,
        }
        usage_expectations[card_id] = expectation

        if "mulligan_anchor" in roles:
            mulligan_anchors.append(
                {
                    "card_id": card_id,
                    "intent": "hold",
                    "condition": "*",
                    "confidence": coverage_status,
                    "source_claim_ids": source_claim_ids,
                }
            )

        for claim in related_claims:
            if _is_bad_pattern(claim):
                known_bad_patterns.append(
                    {
                        "card_id": card_id,
                        "claim_id": claim["claim_id"],
                        "pattern": claim["claim"],
                        "source_claim_ids": [claim["claim_id"]],
                    }
                )

    combos, combo_suppression_report = _infer_combos(claim_rows, set(card_map))
    policies = _infer_policies(claim_rows)
    confidence_label = _confidence_label(card_map, claim_rows)
    deckwide_effects = _deckwide_effects(card_map, metadata_by_card)
    global_value_overlays, global_value_overlay_reasons = _global_value_overlay_profile(
        card_map, deckwide_effects
    )

    return {
        "deck_name": str(deck_identity.get("deck_name", deck_name or "Deck")),
        "deck_slug": str(
            deck_identity.get(
                "deck_slug",
                slugify_deck_name(str(deck_identity.get("deck_name", deck_name or "Deck"))),
            )
        ),
        "archetype": "aggressive_gameplan",
        "aggression_profile": {
            "speed": "aggro",
            "pressure_bias": "high",
            "global_value_overlays": global_value_overlays,
            "global_value_overlay_reasons": global_value_overlay_reasons,
        },
        "deckwide_effects": deckwide_effects,
        "cards": card_map,
        "card_role_map": role_rows,
        "mulligan_anchors": sorted(mulligan_anchors, key=lambda row: row["card_id"]),
        "card_usage_expectations": usage_expectations,
        "card_usage_expectation_rows": [
            usage_expectations[card_id] for card_id in sorted(usage_expectations)
        ],
        "known_bad_patterns": sorted(
            known_bad_patterns, key=lambda row: (row["card_id"], row["claim_id"])
        ),
        "combos": combos,
        "combo_suppression_report": combo_suppression_report,
        "policies": policies,
        "confidence_label": confidence_label,
        "source_claims": claim_rows,
    }


def _deck_cards(deck_identity: dict[str, Any]) -> list[dict[str, Any]]:
    cards = deck_identity.get("cards", [])
    return sorted((dict(card) for card in cards), key=lambda card: str(card["card_id"]))


def _metadata_by_card(
    card_metadata: dict[str, Any] | list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    rows = card_metadata.get("cards", []) if isinstance(card_metadata, dict) else card_metadata
    return {str(row["card_id"]): dict(row) for row in rows}


def _coerce_source_claims(
    source_claims: dict[str, Any] | list[dict[str, Any]] | None,
) -> dict[str, Any]:
    if source_claims is None:
        return {"claims": [], "claim_count": 0}
    if isinstance(source_claims, list):
        return normalize_source_claims(source_claims)
    claims = [dict(claim) for claim in source_claims.get("claims", [])]
    if not all("claim_id" in claim for claim in claims):
        return normalize_source_claims(claims)
    for claim in claims:
        claim.setdefault("cards", [])
        claim["cards"] = list(dict.fromkeys(str(card) for card in claim.get("cards", [])))
        claim.setdefault("claim_type", "general")
        claim.setdefault("confidence", "source_backed")
        claim.setdefault("source_claim_ids", [claim["claim_id"]])
    claims.sort(key=lambda claim: str(claim["claim_id"]))
    return {"claims": claims, "claim_count": len(claims)}


def _claims_by_card(claims: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_card: dict[str, list[dict[str, Any]]] = {}
    for claim in claims:
        for card_id in claim.get("cards", []):
            by_card.setdefault(str(card_id), []).append(claim)
    return by_card


def _infer_roles(mechanic_families: list[str], claims: list[dict[str, Any]]) -> list[str]:
    text = _claim_text(claims)
    claim_types = {str(claim.get("claim_type", "")).lower() for claim in claims}
    roles = set(mechanic_families)
    if "keep" in text and not _has_negative_keep(text):
        roles.add("mulligan_anchor")
    if any(marker in text for marker in ("face", "damage", "pressure", "push", "burst")):
        roles.add("pressure")
    if "combo" in claim_types or "combo" in text:
        roles.add("combo_piece")
    return sorted(roles) or ["deck_card"]


def _infer_expected_use(roles: list[str], claims: list[dict[str, Any]]) -> str:
    text = _claim_text(claims)
    if "mulligan_anchor" in roles and "pressure" in roles:
        return "keep_and_pressure"
    if "mulligan_anchor" in roles:
        return "keep_and_play_on_plan"
    if "hero_power_transform" in roles and "hero_power_pressure" in roles:
        return "start_of_game_shadowform_enables_hero_power_pressure"
    if "combo_piece" in roles:
        return "hold_for_combo_window"
    if _has_negative_keep(text):
        return "avoid_low_value_timing"
    if "pressure" in roles:
        return "prioritize_for_pressure"
    return "follow_archetype_plan"


def _is_bad_pattern(claim: dict[str, Any]) -> bool:
    claim_type = str(claim.get("claim_type", "")).lower()
    text = str(claim.get("claim", "")).lower()
    return claim_type in {"bad_pattern", "known_bad_pattern"} or any(
        marker in text for marker in ("never", "avoid", "do not", "don't", "dont")
    )


def _infer_combos(
    claims: list[dict[str, Any]], deck_card_ids: set[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    combos = []
    suppressions = []
    for claim in claims:
        cards = [str(card) for card in claim.get("cards", [])]
        claim_type = str(claim.get("claim_type", "")).lower()
        if len(cards) < 2 or ("combo" not in claim_type and "combo" not in str(claim.get("claim", "")).lower()):
            continue
        missing_cards = [card for card in cards if card not in deck_card_ids]
        if missing_cards:
            suppressions.append(
                {
                    "claim_id": claim["claim_id"],
                    "cards": cards,
                    "missing_cards": missing_cards,
                    "reason": "card_not_in_deck",
                }
            )
            continue
        values = claim.get("values")
        if not isinstance(values, list) or len(values) != len(cards):
            values = ["10" for _ in cards]
        combos.append(
            {
                "rule_id": f"{claim['claim_id']}_combo",
                "cards": cards,
                "operator": str(claim.get("operator", ">>")),
                "values": [str(value) for value in values],
                "source_claim_ids": [claim["claim_id"]],
                "confidence": claim.get("confidence", "source_backed"),
            }
        )
    return sorted(combos, key=lambda row: row["rule_id"]), sorted(
        suppressions, key=lambda row: row["claim_id"]
    )


def _infer_policies(claims: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    policies: dict[str, list[dict[str, Any]]] = {}
    for claim in claims:
        claim_type = str(claim.get("claim_type", "")).lower()
        if claim_type not in {"presume", "concede"}:
            continue
        policies.setdefault(claim_type, []).append(
            {
                "rule_id": f"{claim['claim_id']}_{claim_type}",
                "condition": claim.get("condition", "*"),
                "value": claim.get("policy", claim.get("claim", claim_type)),
                "source_claim_ids": [claim["claim_id"]],
                "confidence": claim.get("confidence", "source_backed"),
            }
        )
    return {key: sorted(value, key=lambda row: row["rule_id"]) for key, value in policies.items()}


def _confidence_label(card_map: dict[str, dict[str, Any]], claims: list[dict[str, Any]]) -> str:
    if not claims:
        return "generic_low_confidence"
    statuses = {card["coverage_status"] for card in card_map.values()}
    if statuses == {"source_backed"}:
        return "source_backed"
    return "mixed"


def _global_value_overlay_profile(
    card_map: dict[str, dict[str, Any]],
    deckwide_effects: list[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str]]:
    overlays: dict[str, str] = {}
    reasons: dict[str, str] = {}
    all_roles = {role for card in card_map.values() for role in card.get("roles", [])}
    if {"pressure", "damage", "combo_piece"} & all_roles:
        overlays.update(
            {
                "GlobalMinionAttack": "increase",
                "GlobalMinionIntrinsicValue": "increase",
                "OppGlobalHeroHealth": "increase",
                "OppGlobalMinionAttack": "decrease",
                "OppGlobalMinionHealth": "decrease",
                "OppGlobalMinionIntrinsicValue": "decrease",
            }
        )
    if "divine_shield" in all_roles:
        overlays["GlobalDivineShield"] = "increase"
    if "charge" in all_roles:
        overlays["GlobalCharge"] = "increase"
    if "rush" in all_roles:
        overlays["GlobalRush"] = "increase"
    if "location" in all_roles:
        overlays["GlobalLocationIntrinsicValue"] = "increase"
        overlays["GlobalLocationHealth"] = "increase"
    if {"hero_power", "hero_power_pressure", "hero_power_transform"} & all_roles:
        overlays["MyHeroPowerValue"] = "increase"
        reasons["MyHeroPowerValue"] = _hero_power_overlay_reason(deckwide_effects)
    if "taunt" in all_roles:
        overlays["GlobalTaunt"] = "decrease"
    return overlays, reasons


def _hero_power_overlay_reason(deckwide_effects: list[dict[str, Any]]) -> str:
    for effect in deckwide_effects:
        if effect.get("effect") == "replace_starting_hero_power":
            return (
                f"{effect.get('source_card_name', effect.get('source_card_id'))} "
                f"enters Shadowform and enables {effect.get('target_name', 'the Hero Power')} "
                "as pressure damage."
            )
    return "Hero Power pressure is part of this deck plan."


def _deckwide_effects(
    card_map: dict[str, dict[str, Any]],
    metadata_by_card: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for card_id, card in card_map.items():
        _metadata = metadata_by_card.get(card_id, {})
        for linked in card.get("linked_entities", []):
            if "hero_power_transform" not in card.get("roles", []):
                continue
            rows.append(
                {
                    "source_card_id": card_id,
                    "source_card_name": card.get("name", card_id),
                    "effect": "replace_starting_hero_power",
                    "target_card_id": linked.get("card_id"),
                    "target_name": linked.get("name"),
                    "target_type": linked.get("type"),
                    "reason": (
                        f"{card.get('name', card_id)} enables "
                        f"{linked.get('name', linked.get('card_id'))} as the deck's pressure Hero Power."
                    ),
                }
            )
    return sorted(rows, key=lambda row: (row["source_card_id"], row["effect"], str(row["target_card_id"])))


def _claim_text(claims: list[dict[str, Any]]) -> str:
    return " ".join(str(claim.get("claim", "")) for claim in claims).lower()


def _has_negative_keep(text: str) -> bool:
    return any(marker in text for marker in NEGATIVE_KEEP_MARKERS)
