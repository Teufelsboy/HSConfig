from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Sequence


@dataclass(frozen=True)
class CardIntentClassification:
    reason: str
    value: str
    band: str
    matched_signals: tuple[str, ...] = ()


def classify_card_intent(
    text: str,
    *,
    value_default: str = "6",
) -> CardIntentClassification:
    normalized = str(text or "").lower()

    if _has_hero_power_transform(normalized):
        return CardIntentClassification(
            reason="hero_power_transform",
            value="10",
            band="critical",
            matched_signals=_signals(
                ("hero_power", _has_any(normalized, ("hero power", "hero_power"))),
                (
                    "transform",
                    _has_any(
                        normalized,
                        ("transform", "change", "changes", "starting"),
                    ),
                ),
                ("shadowform", "shadowform" in normalized),
                ("mind_spike", "mind spike" in normalized),
            ),
        )

    if _has_damage_aura_amplifier(normalized):
        return CardIntentClassification(
            reason="damage_aura_amplifier",
            value="10",
            band="critical",
            matched_signals=_signals(
                ("extra_damage", "extra damage" in normalized),
                ("all_sources", "all sources" in normalized),
                ("both_heroes_take", "both heroes take" in normalized),
                (
                    "voidtouched_attendant",
                    _has_voidtouched_attendant_identity(normalized),
                ),
            ),
        )

    if _has_conditional_minion_death_burn(normalized):
        return CardIntentClassification(
            reason="conditional_minion_death_burn",
            value="10",
            band="high",
            matched_signals=_signals(
                ("enemy_hero_damage", "enemy hero" in normalized),
                ("death_condition", _has_any(normalized, ("if it dies", "dies"))),
                (
                    "minion_targeting",
                    _has_any(
                        normalized,
                        ("minion", "prefer_enemy_minion", "enemy minion"),
                    ),
                ),
            ),
        )

    if _has_self_damage_resource(normalized):
        return CardIntentClassification(
            reason="self_damage_resource",
            value="8",
            band="medium",
            matched_signals=_signals(
                ("raise_dead", "raise dead" in normalized),
                ("self_damage", _has_self_damage_to_own_hero(normalized)),
                (
                    "return_dead_friendly_minions",
                    _has_any(
                        normalized,
                        (
                            "return two friendly minions",
                            "friendly minions that died",
                            "died this game to your hand",
                        ),
                    ),
                ),
            ),
        )

    if _has_opponent_damage_discount_tempo(normalized):
        return CardIntentClassification(
            reason="opponent_damage_discount_tempo",
            value="8",
            band="medium",
            matched_signals=_signals(
                ("frenzied_felwing", "frenzied felwing" in normalized),
                (
                    "cost_reduction",
                    _has_any(normalized, ("costs (1) less", "costs less")),
                ),
                (
                    "opponent_damage_this_turn",
                    _has_any(
                        normalized,
                        (
                            "damage dealt to your opponent this turn",
                            "opponent this turn",
                            "opponent_damage",
                        ),
                    ),
                ),
            ),
        )

    if _has_self_damage_liability_body(normalized):
        return CardIntentClassification(
            reason="self_damage_liability_body",
            value="6",
            band="medium",
            matched_signals=_signals(
                ("brain_masseuse", "brain masseuse" in normalized),
                (
                    "takes_damage_reflects_to_own_hero",
                    _has_any(
                        normalized,
                        (
                            "whenever this minion takes damage",
                            "also deal that amount to your hero",
                            "takes damage",
                        ),
                    )
                    and _has_self_damage_to_own_hero(normalized),
                ),
            ),
        )

    if _has_hero_power_cost_aura(normalized):
        return CardIntentClassification(
            reason="hero_power_cost_aura",
            value="8",
            band="medium",
            matched_signals=_signals(
                ("papercraft_angel", "papercraft angel" in normalized),
                ("hero_power", _has_any(normalized, ("hero power", "hero_power"))),
                (
                    "cost_zero",
                    _has_any(normalized, ("costs (0)", "costs 0", "cost 0")),
                ),
            ),
        )

    if _has_direct_enemy_hero_burn(normalized):
        return CardIntentClassification(
            reason="direct_enemy_hero_burn",
            value="12",
            band="critical",
            matched_signals=_signals(
                (
                    "enemy_hero_targeting",
                    _has_any(
                        normalized,
                        ("prefer_enemy_hero", "enemy hero", "face", "hero damage"),
                    ),
                ),
                ("damage", _has_damage_wording(normalized)),
            ),
        )

    if _has_reciprocal_hero_burn(normalized):
        return CardIntentClassification(
            reason="reciprocal_hero_burn",
            value="10",
            band="high",
            matched_signals=_signals(
                ("shadowbomber", "shadowbomber" in normalized),
                ("acupuncture", "acupuncture" in normalized),
                ("each_hero", "each hero" in normalized),
                ("both_heroes", "both heroes" in normalized),
                ("damage", _has_damage_wording(normalized)),
            ),
        )

    if _has_any(normalized, ("location", "cathedral", "atonement")):
        return CardIntentClassification(
            reason="location_tempo",
            value="8",
            band="medium",
            matched_signals=_signals(
                ("location", "location" in normalized),
                ("cathedral", "cathedral" in normalized),
                ("atonement", "atonement" in normalized),
            ),
        )

    if _has_any(normalized, ("draw", "cycle", "discover", "generate", "copy")):
        return CardIntentClassification(
            reason="draw_cycle",
            value="8",
            band="medium",
            matched_signals=_signals(
                ("draw", "draw" in normalized),
                ("cycle", "cycle" in normalized),
                ("discover", "discover" in normalized),
                ("generate", "generate" in normalized),
                ("copy", "copy" in normalized),
            ),
        )

    if _has_any(
        normalized,
        ("summon", "pirate", "treant", "board", "on_board"),
    ) or _has_token(normalized, "mech"):
        return CardIntentClassification(
            reason="board_tempo",
            value="8",
            band="medium",
            matched_signals=_signals(
                ("summon", "summon" in normalized),
                ("pirate", "pirate" in normalized),
                ("treant", "treant" in normalized),
                ("mech", _has_token(normalized, "mech")),
                ("board", _has_any(normalized, ("board", "on_board"))),
            ),
        )

    return CardIntentClassification(
        reason="semantic_default",
        value=bounded_default_value(value_default),
        band="default",
    )


def bounded_default_value(value_default: str) -> str:
    try:
        value = int(str(value_default).strip())
    except ValueError:
        value = 6
    return str(min(12, max(4, value)))


def _has_hero_power_transform(text: str) -> bool:
    if _has_any(text, ("hero_power_transform", "shadowform", "mind spike")):
        return True
    return _has_any(text, ("hero power", "hero_power")) and _has_any(
        text,
        ("transform", "start", "starting", "change", "changes", "changed"),
    )


def _has_damage_aura_amplifier(text: str) -> bool:
    if _has_voidtouched_attendant_identity(text):
        return True
    return _has_damage_wording(text) and _has_any(
        text,
        (
            "extra damage",
            "all sources",
            "both heroes take",
            "amplifier",
            "amplify",
            "increased",
            "increase",
        ),
    )


def _has_voidtouched_attendant_identity(text: str) -> bool:
    return "voidtouched attendant" in text or _has_token(text, "voidtouched")


def _has_conditional_minion_death_burn(text: str) -> bool:
    if "mind sear" in text:
        return True
    return (
        "enemy hero" in text
        and _has_any(text, ("if it dies", "dies"))
        and _has_any(text, ("minion", "prefer_enemy_minion", "enemy minion"))
    )


def _has_direct_enemy_hero_burn(text: str) -> bool:
    if "mind blast" in text:
        return True
    return any(
        _has_phrase_or_token(text, needle)
        for needle in ("prefer_enemy_hero", "enemy hero", "face", "hero damage")
    ) and _has_damage_wording(text)


def _has_reciprocal_hero_burn(text: str) -> bool:
    if _has_any(text, ("shadowbomber", "acupuncture")):
        return True
    return _has_damage_wording(text) and _has_any(
        text,
        ("each hero", "both heroes"),
    )


def _has_self_damage_resource(text: str) -> bool:
    if "raise dead" in text:
        return True
    return _has_self_damage_to_own_hero(text) and _has_any(
        text,
        (
            "return two friendly minions",
            "friendly minions that died",
            "died this game to your hand",
        ),
    )


def _has_opponent_damage_discount_tempo(text: str) -> bool:
    if "frenzied felwing" in text:
        return True
    return _has_any(text, ("costs (1) less", "costs less")) and _has_any(
        text,
        (
            "damage dealt to your opponent this turn",
            "opponent this turn",
            "opponent_damage",
        ),
    )


def _has_self_damage_liability_body(text: str) -> bool:
    if "brain masseuse" in text:
        return True
    return _has_any(
        text,
        ("whenever this minion takes damage", "also deal that amount to your hero"),
    ) and _has_self_damage_to_own_hero(text)


def _has_hero_power_cost_aura(text: str) -> bool:
    if "papercraft angel" in text:
        return True
    return _has_any(text, ("hero power", "hero_power")) and _has_any(
        text,
        ("costs (0)", "costs 0", "cost 0", "free hero power"),
    )


def _has_self_damage_to_own_hero(text: str) -> bool:
    return _has_any(
        text,
        (
            "damage to your hero",
            "deal that amount to your hero",
            "your hero",
        ),
    ) and _has_damage_wording(text)


def _has_damage_wording(text: str) -> bool:
    return _has_any(text, ("damage", "deals", "deal ", "burn"))


def _has_any(text: str, needles: Sequence[str]) -> bool:
    return any(needle in text for needle in needles)


def _has_phrase_or_token(text: str, needle: str) -> bool:
    return re.search(
        rf"(?<![a-z0-9_]){re.escape(needle)}(?![a-z0-9_])",
        text,
    ) is not None


def _has_token(text: str, token: str) -> bool:
    return re.search(
        rf"(?<![a-z0-9_]){re.escape(token)}(?![a-z0-9_])",
        text,
    ) is not None


def _signals(*candidates: tuple[str, bool]) -> tuple[str, ...]:
    return tuple(signal for signal, matched in candidates if matched)


__all__ = (
    "CardIntentClassification",
    "bounded_default_value",
    "classify_card_intent",
)
