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

    if _has_any(
        normalized,
        (
            "extra damage",
            "all sources",
            "both heroes take",
            "voidtouched",
            "attendant",
        ),
    ):
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
                    _has_any(normalized, ("voidtouched", "attendant")),
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


def _has_conditional_minion_death_burn(text: str) -> bool:
    return (
        "enemy hero" in text
        and _has_any(text, ("if it dies", "dies"))
        and _has_any(text, ("minion", "prefer_enemy_minion", "enemy minion"))
    )


def _has_direct_enemy_hero_burn(text: str) -> bool:
    return _has_any(
        text,
        ("prefer_enemy_hero", "enemy hero", "face", "hero damage"),
    ) and _has_damage_wording(text)


def _has_damage_wording(text: str) -> bool:
    return _has_any(text, ("damage", "deals", "deal ", "burn"))


def _has_any(text: str, needles: Sequence[str]) -> bool:
    return any(needle in text for needle in needles)


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
