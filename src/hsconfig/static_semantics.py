from __future__ import annotations

import re
from collections.abc import Mapping
from hashlib import sha256
from typing import Any

from hsconfig.mechanic_drift import TEXT_MECHANIC_PATTERNS as DRIFT_TEXT_MECHANIC_PATTERNS
from hsconfig.mechanic_support import (
    MECHANIC_SUPPORT,
    mechanic_default_runtime_block,
    mechanic_report_only_reason,
    mechanic_static_claim_allowed,
)


TEXT_PATTERNS: dict[str, tuple[str, ...]] = {
    "battlecry": ("battlecry",),
    "deathrattle": ("deathrattle",),
    "discover": ("discover",),
    "dredge": ("dredge",),
    "tradeable": ("tradeable",),
    "overload": ("overload",),
    "weapon": ("weapon", "equip", "equips"),
    "freeze": ("freeze", "frozen"),
    "lifesteal": ("lifesteal",),
    "reborn": ("reborn",),
    "rush": ("rush",),
    "charge": ("charge",),
    "taunt": ("taunt",),
    "secret": ("secret",),
    "draw": ("draw", "draws", "drawn"),
    "heal": ("heal", "healed", "healing", "restore health"),
    "damage": ("damage", "deal damage", "deals damage"),
    "summon": ("summon", "summons", "summoned"),
    "recruit": ("recruit",),
    "discard": ("discard", "discards"),
    "silence": ("silence", "silences"),
    "transform": ("transform", "transforms", "becomes"),
    "destroy": ("destroy", "destroys"),
    "choose_one": ("choose one",),
    "aura": ("adjacent", "your other", "your minions have"),
    "spellburst": ("spellburst",),
    "quickdraw": ("quickdraw",),
    "finale": ("finale",),
    "manathirst": ("manathirst", "mana thirst"),
    "infuse": ("infuse", "infused"),
    "corrupt": ("corrupt", "corrupted"),
    "forge": ("forge", "forged"),
    "outcast": ("outcast",),
    "titan": ("titan",),
    "starship": ("starship", "launch your starship"),
}

DRIFT_TEXT_ONLY_RUNTIME_GUARDED_FAMILIES = frozenset(DRIFT_TEXT_MECHANIC_PATTERNS) - frozenset(
    TEXT_PATTERNS
)

MODERN_WARNING_ONLY_KEYWORDS = {
    "titan": "titan",
    "tourist": "tourist",
    "imbue": "imbue",
    "forge": "forge",
    "excavate": "excavate",
}

TYPE_TO_FAMILY = {
    "HERO_POWER": "hero_power",
    "LOCATION": "location",
    "MINION": "minion",
    "SPELL": "spell",
    "WEAPON": "weapon",
}

REFERENCED_TAG_TO_FAMILY = {
    "BATTLECRY": "battlecry",
    "CHOOSE_ONE": "choose_one",
    "DEATHRATTLE": "deathrattle",
    "DISCOVER": "discover",
    "DREDGE": "dredge",
    "TRADEABLE": "tradeable",
    "OVERLOAD": "overload",
    "FREEZE": "freeze",
    "LIFESTEAL": "lifesteal",
    "REBORN": "reborn",
    "RUSH": "rush",
    "CHARGE": "charge",
    "TAUNT": "taunt",
    "SECRET": "secret",
    "START_OF_GAME_KEYWORD": "start_of_game",
    "SPELLBURST": "spellburst",
    "QUICKDRAW": "quickdraw",
    "FINALE": "finale",
    "MANATHIRST": "manathirst",
    "INFUSE": "infuse",
    "CORRUPT": "corrupt",
    "FORGE": "forge",
    "OUTCAST": "outcast",
    "TITAN": "titan",
    "STARSHIP": "starship",
    "KINDRED": "kindred",
    "TOURIST": "tourist",
    "REWIND": "rewind",
    "HERALD": "herald",
    "SHATTER": "shatter",
}

WARNING_ONLY_MECHANICS = {
    "board_position",
    "dredge",
    "generated_entity_random_pool",
    "location_activation",
    "secret_timing",
    "forge",
    "tradeable",
    "outcast",
    "titan",
    "starship",
    "kindred",
    "tourist",
    "imbue",
    "rewind",
    "herald",
    "shatter",
    "excavate",
}

SOURCE_FAMILY = "hearthstonejson_static_semantics"
SOURCE_TYPE = "official_card_data"


def _text_patterns() -> dict[str, tuple[str, ...]]:
    merged = {
        family: tuple(patterns)
        for family, patterns in DRIFT_TEXT_MECHANIC_PATTERNS.items()
    }
    for family, patterns in TEXT_PATTERNS.items():
        merged[family] = tuple(dict.fromkeys((*merged.get(family, ()), *patterns)))
    return merged


def _has_deck_condition(lowered: str) -> bool:
    return any(
        phrase in lowered
        for phrase in (
            "if your deck",
            "your deck has",
            "the spells in your deck",
            "the minions in your deck",
            "cards in your deck",
            "deck size",
            "starting deck",
            "in your deck at the start",
        )
    )


def _has_even_odd_deck_condition(lowered: str) -> bool:
    return any(
        phrase in lowered
        for phrase in (
            "only even-cost",
            "only even cost",
            "only even-cost cards",
            "only odd-cost",
            "only odd cost",
            "only odd-cost cards",
        )
    )


def _has_highlander_condition(lowered: str) -> bool:
    return "no duplicates" in lowered or "no duplicate" in lowered


def _has_deck_size_or_starting_health_modifier(lowered: str) -> bool:
    return (
        "deck size" in lowered
        or "starting health" in lowered
        or "starting health are" in lowered
    )


def _has_start_in_deck_requirement(lowered: str) -> bool:
    return (
        "if this is in your deck" in lowered
        or "if this is in your starting deck" in lowered
        or "in your deck at the start of the game" in lowered
    )


def _is_warning_only_family(family: str) -> bool:
    return family in WARNING_ONLY_MECHANICS or (
        family in MECHANIC_SUPPORT and bool(mechanic_report_only_reason(family))
    )


def static_semantic_runtime_claim_allowed(
    family: str,
    semantics: Mapping[str, Any] | None = None,
) -> bool:
    if family in DRIFT_TEXT_ONLY_RUNTIME_GUARDED_FAMILIES and not _has_non_text_evidence(
        family,
        semantics,
    ):
        return _is_warning_only_family(family)
    return mechanic_static_claim_allowed(family) or _is_warning_only_family(family)


def _static_claim_allowed_for_family(
    family: str,
    semantics: Mapping[str, Any] | None = None,
) -> bool:
    return static_semantic_runtime_claim_allowed(family, semantics)


def _has_non_text_evidence(
    family: str,
    semantics: Mapping[str, Any] | None,
) -> bool:
    if not isinstance(semantics, Mapping):
        return False
    for row in semantics.get("evidence", []) or []:
        if not isinstance(row, Mapping):
            continue
        if row.get("family") == family and row.get("source") != "text":
            return True
    return False


def infer_static_semantics(card: Mapping[str, Any]) -> dict[str, Any]:
    families: set[str] = set()
    evidence: list[dict[str, str]] = []

    card_type = str(card.get("type", "") or "").upper()
    if card_type in TYPE_TO_FAMILY:
        _add(families, evidence, TYPE_TO_FAMILY[card_type], "type", card_type)

    for mechanic in card.get("mechanics", []) or []:
        family = _normalize_family(str(mechanic))
        _add(families, evidence, family, "mechanics", str(mechanic))

    for tag in card.get("referenced_tags", card.get("referencedTags", [])) or []:
        tag_text = str(tag).upper()
        family = REFERENCED_TAG_TO_FAMILY.get(tag_text)
        if family:
            _add(families, evidence, family, "referenced_tags", tag_text)

    text = _plain_text(
        f"{card.get('name', '')} {card.get('text', '')} {card.get('targeting_arrow_text', '')}"
    )
    lowered = text.lower()
    for family, patterns in _text_patterns().items():
        match = next((pattern for pattern in patterns if _contains(lowered, pattern)), None)
        if match:
            _add(families, evidence, family, "text", match)
    for keyword, family in MODERN_WARNING_ONLY_KEYWORDS.items():
        if _contains(lowered, keyword):
            _add(families, evidence, family, "text", keyword)

    if card.get("overload") is not None:
        _add(families, evidence, "overload", "overload", str(card["overload"]))
    if card.get("spell_damage") is not None:
        _add(families, evidence, "spell_damage", "spell_damage", str(card["spell_damage"]))
    if card.get("hero_power_dbf_id") is not None:
        _add(families, evidence, "hero_power", "heroPowerDbfId", str(card["hero_power_dbf_id"]))

    if "start of game" in lowered:
        _add(families, evidence, "start_of_game", "text", "start of game")
    if "start_of_game" in families:
        _add(families, evidence, "start_of_game_modifier", "text", "start of game")
        _add(families, evidence, "passive_start_effect", "text", "start of game")
    if _has_deck_condition(lowered):
        _add(families, evidence, "deckbuilding_modifier", "text", "deck condition")
    if _has_even_odd_deck_condition(lowered):
        _add(families, evidence, "deckbuilding_modifier", "text", "odd/even deck condition")
        _add(families, evidence, "even_odd_modifier", "text", "odd/even deck condition")
    if _has_highlander_condition(lowered):
        _add(families, evidence, "deckbuilding_modifier", "text", "no duplicates")
        _add(families, evidence, "highlander_modifier", "text", "no duplicates")
    if _has_deck_size_or_starting_health_modifier(lowered):
        _add(families, evidence, "deckbuilding_modifier", "text", "deck size or starting health")
        _add(families, evidence, "deck_size_modifier", "text", "deck size or starting health")
        _add(families, evidence, "deck_state_modifier", "text", "deck size or starting health")
    if _has_start_in_deck_requirement(lowered):
        _add(families, evidence, "deckbuilding_modifier", "text", "in deck at start")
        _add(families, evidence, "start_in_deck_requirement", "text", "in deck at start")
        _add(families, evidence, "start_of_game", "text", "in deck at start")
    if "shadowform" in lowered:
        _add(families, evidence, "shadowform", "text", "shadowform")
        _add(families, evidence, "hero_power", "text", "shadowform")
        if "start_of_game" in families:
            _add(families, evidence, "hero_power_transform", "text", "shadowform start of game")
    if (
        "random" in lowered
        and (
            "summon" in families
            or _contains(lowered, "add")
            or _contains(lowered, "generate")
        )
        and any(
            _contains(lowered, object_word)
            for object_word in ("card", "copy", "minion", "secret", "spell", "weapon")
        )
    ):
        _add(families, evidence, "generated_entity", "text", "random generated entity")
        _add(families, evidence, "generated_entity_random_pool", "text", "random generated entity")
    if "secret" in families:
        _add(families, evidence, "secret_timing", "mechanic", "secret")
    if "location" in families:
        _add(families, evidence, "location_activation", "type", "LOCATION")

    return {
        "families": sorted(families),
        "evidence": _dedupe_evidence(evidence),
        "warning_only": sorted(
            family for family in families if _is_warning_only_family(family)
        ),
    }


def build_static_semantics_source_records(
    deck_identity: Mapping[str, Any],
    cards_by_id: Mapping[str, Mapping[str, Any]],
    *,
    build_id: str | None = None,
) -> list[dict[str, Any]]:
    """Build source-record rows from deterministic card data.

    This intentionally emits effect/mechanic claims only. Opening-hand
    decisions still require explicit guide claims and are never inferred here.
    """
    source_build_id = str(build_id or "unresolved-build")
    records: list[dict[str, Any]] = []
    deck_name = str(deck_identity.get("deck_name") or deck_identity.get("name") or "Deck")

    source_cards = {str(card_id): dict(card) for card_id, card in cards_by_id.items()}
    deck_card_counts = static_semantic_deck_card_counts(deck_identity)
    for target_card_id in _deck_card_ids(deck_identity, source_cards):
        raw_card = source_cards.get(target_card_id)
        if not isinstance(raw_card, Mapping):
            continue
        card = dict(raw_card)
        card_id = str(card.get("card_id") or card.get("id") or target_card_id)
        claims = _static_claims_for_card(
            card_id,
            card,
            deck_card_counts=deck_card_counts,
        )
        if not claims:
            continue
        records.append(
            {
                "source_family": SOURCE_FAMILY,
                "source_type": SOURCE_TYPE,
                "source_title": f"HearthstoneJSON static semantics {source_build_id} {card_id}",
                "source_url": f"hearthstonejson://{source_build_id}/{card_id}",
                "source_visibility": "full_text",
                "source_record_strength": "static_semantics",
                "source_rank_lane": "static_semantics_only",
                "source_lane": "official_static_semantics",
                "deck_match_scope": "deck_identity_static",
                "promotion_eligible": True,
                "strong_promotion_eligible": False,
                "trust_ceiling": "static_semantics",
                "promotion_blockers": ["static_semantics_not_public_guide"],
                "first_missing_source_action": "none",
                "deck_name": deck_name,
                "card_id": card_id,
                "card_name": str(card.get("name") or card_id),
                "build_id": source_build_id,
                "claims": claims,
            }
        )
    return records


def _deck_card_ids(
    deck_identity: Mapping[str, Any],
    cards_by_id: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    deck_cards = deck_identity.get("cards")
    ids: list[str] = []
    if isinstance(deck_cards, list):
        for row in deck_cards:
            if not isinstance(row, Mapping):
                continue
            card_id = row.get("card_id") or row.get("id") or row.get("cardId")
            if card_id:
                ids.append(str(card_id))
    return sorted(dict.fromkeys(ids))


def static_semantic_deck_card_counts(deck_identity: Mapping[str, Any]) -> dict[str, int]:
    """Return deck card counts used by static condition guards."""
    deck_cards = deck_identity.get("cards")
    counts: dict[str, int] = {}
    if not isinstance(deck_cards, list):
        return counts
    for row in deck_cards:
        if not isinstance(row, Mapping):
            continue
        card_id = row.get("card_id") or row.get("id") or row.get("cardId")
        if not card_id:
            continue
        key = str(card_id)
        counts[key] = counts.get(key, 0) + _card_count(row.get("count", 1))
    return counts


def _card_count(value: object) -> int:
    try:
        count = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1
    return max(count, 0)


def _static_semantic_is_highlander_deck(deck_card_counts: Mapping[str, int]) -> bool:
    return bool(deck_card_counts) and all(count <= 1 for count in deck_card_counts.values())


def static_semantic_has_unsatisfied_highlander_condition(
    semantics: Mapping[str, Any],
    deck_card_counts: Mapping[str, int],
) -> bool:
    return "highlander" in set(
        semantics.get("families", [])
    ) and not _static_semantic_is_highlander_deck(deck_card_counts)


def _static_claims_for_card(
    card_id: str,
    card: Mapping[str, Any],
    *,
    deck_card_counts: Mapping[str, int] | None = None,
) -> list[dict[str, Any]]:
    semantics = infer_static_semantics(card)
    families = set(semantics["families"])
    unsatisfied_highlander = static_semantic_has_unsatisfied_highlander_condition(
        semantics,
        deck_card_counts or {},
    )
    claims: list[dict[str, Any]] = []

    if "hero_power_transform" in families and not unsatisfied_highlander:
        claims.append(
            _static_source_claim(
                card_id,
                card,
                claim_kind="hero_power_transform",
                mechanic="hero_power_transform",
                stance="enable_transformed_hero_power",
                semantics=semantics,
            )
        )

    emitted = {
        (str(claim["claim_kind"]), str(claim.get("mechanic", ""))) for claim in claims
    }
    for family in sorted(families):
        if family == "hero_power_transform":
            continue
        if family == "hero_power" and "hero_power_transform" in families:
            continue
        if unsatisfied_highlander and mechanic_static_claim_allowed(family):
            continue
        if not _static_claim_allowed_for_family(family, semantics):
            continue
        key = ("mechanic_usage", family)
        if key in emitted:
            continue
        claims.append(
            _static_source_claim(
                card_id,
                card,
                claim_kind="mechanic_usage",
                mechanic=family,
                stance=f"use_{family}_according_to_card_text",
                semantics=semantics,
            )
        )
        emitted.add(key)

    return claims


def _static_source_claim(
    card_id: str,
    card: Mapping[str, Any],
    *,
    claim_kind: str,
    mechanic: str,
    stance: str,
    semantics: Mapping[str, Any],
) -> dict[str, Any]:
    evidence = _plain_text(str(card.get("text") or ""))
    card_name = str(card.get("name") or card_id)
    runtime_block = mechanic_default_runtime_block(mechanic) or ""
    report_only_reason = mechanic_report_only_reason(mechanic)
    trust_ceiling = "report_only" if report_only_reason and not runtime_block else "static_semantics"
    claim = {
        "claim_id": _static_claim_id(card_id, claim_kind, mechanic, evidence),
        "claim_kind": claim_kind,
        "claim_type": claim_kind,
        "source": SOURCE_FAMILY,
        "source_family": SOURCE_FAMILY,
        "source_type": SOURCE_TYPE,
        "source_title": "HearthstoneJSON static card text",
        "source_url": "",
        "source_lane": "official_static_semantics",
        "source_rank_lane": "static_semantics_only",
        "source_record_strength": "static_semantics",
        "source_visibility": "full_text",
        "deck_match_scope": "deck_identity_static",
        "promotion_eligible": trust_ceiling != "report_only",
        "strong_promotion_eligible": False,
        "claim_readiness": "source_backed_static_semantics",
        "trust_ceiling": trust_ceiling,
        "confidence": "source_backed_static_semantics",
        "source_confidence": "high",
        "claim_confidence": "high",
        "support_status": "static_semantics",
        "cards": [card_id],
        "card_mentions": [card_name],
        "stance": stance,
        "mechanic": mechanic,
        "mechanic_family": mechanic,
        "semantic_families": sorted(semantics.get("families", [])),
        "warning_only": sorted(semantics.get("warning_only", [])),
        "opening_hand_relevant": False,
        "runtime_block": runtime_block,
        "runtime_suppression_reason": report_only_reason,
        "first_missing_source_action": "none",
        "claim": evidence or f"{card_name} static semantics.",
        "evidence_text_short": evidence or f"{card_name} static semantics.",
        "source_refs": [SOURCE_FAMILY],
    }
    if evidence:
        claim["evidence_hash"] = sha256(evidence.encode("utf-8")).hexdigest()[:16]
    claim["source_claim_ids"] = [claim["claim_id"]]
    return claim


def _static_claim_id(card_id: str, claim_kind: str, mechanic: str, evidence: str) -> str:
    digest = sha256(f"{card_id}|{claim_kind}|{mechanic}|{evidence}".encode("utf-8")).hexdigest()
    return f"static-{digest[:16]}"


def _add(families: set[str], evidence: list[dict[str, str]], family: str, source: str, value: str) -> None:
    if not family:
        return
    families.add(family)
    evidence.append({"family": family, "source": source, "value": value})


def _normalize_family(value: str) -> str:
    return value.strip().lower().replace(" ", "_")


def _plain_text(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).replace("$", "")


def _contains(haystack: str, needle: str) -> bool:
    if " " in needle:
        return needle in haystack
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack))


def _dedupe_evidence(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str]] = set()
    deduped = []
    for row in rows:
        key = (row["family"], row["source"], row["value"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return sorted(deduped, key=lambda row: (row["family"], row["source"], row["value"]))
