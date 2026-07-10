from __future__ import annotations

from typing import Any


DECK_ALIASES = {
    "ShadowPriest": ["ShadowPriest", "Shadow Priest"],
    "CtAPaladin": ["CtAPaladin", "Call to Arms Paladin", "CTA Paladin"],
    "PirateRogue": ["PirateRogue", "Pirate Rogue"],
    "BigShaman": ["BigShaman", "Big Shaman"],
    "Discolock": ["Discolock", "Discard Warlock", "Discardlock"],
    "TreantDruid": ["TreantDruid", "Treant Druid", "Token Druid"],
    "ImbueMage": ["ImbueMage", "Imbue Mage", "Hero Power Mage"],
    "MechPala": ["MechPala", "Mech Paladin"],
    "Kingslayer": ["Kingslayer", "Kingsbane Rogue"],
    "Boarlock": ["Boarlock", "Boar Warlock"],
    "PirateDH": ["PirateDH", "Pirate Demon Hunter"],
}

MECHANIC_REQUIRED_CLAIMS = {
    "aggro": ["card_role", "targeting_rule"],
    "burn": ["card_role", "targeting_rule"],
    "shadow_hero_power": ["hero_power_transform", "mechanic_usage"],
    "recruit": ["card_role", "mechanic_usage"],
    "board_flood": ["card_role", "mechanic_usage"],
    "aura_pressure": ["card_role", "mechanic_usage"],
    "pirate": ["card_role", "targeting_rule"],
    "tempo": ["card_role", "targeting_rule"],
    "deathrattle": ["card_role", "mechanic_usage"],
    "big_minion": ["card_role", "mechanic_usage"],
    "cheat": ["card_role", "mechanic_usage"],
    "discard": ["card_role", "mechanic_usage"],
    "hand_mutation": ["card_role", "mechanic_usage"],
    "payoff_summon": ["card_role", "mechanic_usage"],
    "token_board": ["card_role", "mechanic_usage"],
    "treant": ["card_role", "mechanic_usage"],
    "board_buff": ["card_role", "mechanic_usage"],
    "hero_power": ["card_role", "targeting_rule"],
    "imbue": ["card_role", "mechanic_usage"],
    "spell_generation": ["card_role", "mechanic_usage"],
    "mech": ["card_role", "mechanic_usage"],
    "magnetic": ["card_role", "mechanic_usage"],
    "board_scaling": ["card_role", "mechanic_usage"],
    "weapon_pressure": ["card_role", "targeting_rule"],
    "weapon": ["card_role", "targeting_rule"],
    "attack_sequence": ["card_role", "targeting_rule"],
    "combo": ["card_role", "combo_sequence"],
    "control": ["card_role", "mechanic_usage"],
    "resource_setup": ["card_role", "mechanic_usage"],
    "hero_attack": ["card_role", "targeting_rule"],
    "tempo_pressure": ["card_role", "targeting_rule"],
}


def build_source_research_manifest(
    *,
    deck_name: str,
    deck_identity: dict[str, Any],
    candidate_archetypes: dict[str, Any],
    fixture_row: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mechanics = _mechanic_focus(candidate_archetypes, fixture_row)
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "deck_code_hash": str(deck_identity.get("deck_code_hash", "")),
        "search_aliases": DECK_ALIASES.get(deck_name, [deck_name]),
        "primary_archetype": str(candidate_archetypes.get("primary_archetype", "")),
        "mechanic_focus": mechanics,
        "required_source_families": ["guide", "mulligan_guide", "card_text", "metadata"],
        "research_questions": _research_questions(mechanics),
        "card_targets": _card_targets(deck_identity, mechanics),
    }


def _mechanic_focus(
    candidate_archetypes: dict[str, Any],
    fixture_row: dict[str, Any] | None,
) -> list[str]:
    if fixture_row and isinstance(fixture_row.get("primary_mechanics"), list):
        return [str(item) for item in fixture_row["primary_mechanics"]]
    primary = str(candidate_archetypes.get("primary_archetype", "")).strip()
    inferred = sorted(
        (mechanic for mechanic in MECHANIC_REQUIRED_CLAIMS if mechanic in primary),
        key=lambda mechanic: primary.index(mechanic),
    )
    if inferred:
        return _dedupe_covered_mechanics(inferred)
    return [primary or "generic_low_confidence"]


def _dedupe_covered_mechanics(mechanics: list[str]) -> list[str]:
    output: list[str] = []
    for mechanic in mechanics:
        if any(mechanic != other and mechanic in other for other in mechanics):
            continue
        output.append(mechanic)
    return output


def _research_questions(mechanics: list[str]) -> list[dict[str, str]]:
    questions = [
        {
            "claim_kind": "card_role",
            "question": "Which deck cards are core plan cards, payoffs, enablers, or flex cards?",
        },
        {
            "claim_kind": "mulligan_keep",
            "question": "Which exact cards are always keep cards in the mulligan?",
        },
        {
            "claim_kind": "mulligan_keep",
            "question": "Which exact cards are conditional mulligan keeps with Coin or without Coin?",
        },
        {
            "claim_kind": "mulligan_keep",
            "question": "Which exact cards are conditional mulligan keeps by opponent class or matchup speed?",
        },
        {
            "claim_kind": "mulligan_keep",
            "question": "Which exact cards are kept only with a hand partner or with another card already present?",
        },
        {
            "claim_kind": "mulligan_discard",
            "question": "Which exact cards should be thrown or discarded away in mulligan?",
        },
        {
            "claim_kind": "mulligan_keep",
            "question": "Which one-drop, early-curve, or mulligan-anchor cards are kept because of source-backed guide confidence?",
        },
        {
            "claim_kind": "mulligan_keep",
            "question": "What is the source confidence for each mulligan claim, and is it from a guide, archetype analysis, or static card semantics?",
        },
        {
            "claim_kind": "gameplan_posture",
            "question": "What pre-game board-value posture should GlobalValues express?",
        },
    ]
    if {"weapon", "weapon_pressure", "hero_attack"} & set(mechanics):
        questions.append(
            {
                "claim_kind": "targeting_rule",
                "question": "Which cards or attacks should prefer enemy hero versus board targets?",
            }
        )
    if "combo" in mechanics:
        questions.append(
            {
                "claim_kind": "combo_sequence",
                "question": "Which exact card order is source-backed enough for Combo.json?",
            }
        )
    return questions


def _card_targets(deck_identity: dict[str, Any], mechanics: list[str]) -> list[dict[str, Any]]:
    required = sorted(
        {
            claim
            for mechanic in mechanics
            for claim in MECHANIC_REQUIRED_CLAIMS.get(mechanic, ["card_role"])
        }
    )
    if not required:
        required = ["card_role"]
    return [
        {
            "card_id": str(card.get("card_id", "")),
            "name": str(card.get("name", card.get("card_id", ""))),
            "required_claims": required,
        }
        for card in deck_identity.get("cards", [])
        if isinstance(card, dict) and str(card.get("card_id", "")).strip()
    ]
