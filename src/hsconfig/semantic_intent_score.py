from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class SemanticIntentScore:
    value: str
    band: str
    reason: str
    profile: str
    matched_signals: tuple[str, ...] = ()


def score_card_behavior_claim(
    claim: Mapping[str, Any],
    *,
    behavior_block: str,
    intent: str,
    roles: Sequence[str],
    value_default: str = "6",
) -> SemanticIntentScore:
    explicit = claim.get("runtime_value", claim.get("value"))
    if explicit is not None and str(explicit).strip():
        return SemanticIntentScore(
            value=str(explicit),
            band="explicit",
            reason="explicit_runtime_value",
            profile="source_claim",
            matched_signals=("explicit_value",),
        )

    text = _normalized_claim_text(
        claim,
        behavior_block=behavior_block,
        intent=intent,
        roles=roles,
    )

    if _has_hero_power_transform(text):
        return SemanticIntentScore(
            value="10",
            band="critical",
            reason="hero_power_transform",
            profile="semantic_intent",
            matched_signals=_signals(
                ("hero_power", _has_any(text, ("hero power", "hero_power"))),
                ("transform", _has_any(text, ("transform", "change", "changes", "starting"))),
                ("shadowform", "shadowform" in text),
                ("mind_spike", "mind spike" in text),
            ),
        )

    if _has_any(
        text,
        (
            "extra damage",
            "all sources",
            "both heroes take",
            "voidtouched",
            "attendant",
        ),
    ):
        return SemanticIntentScore(
            value="10",
            band="critical",
            reason="damage_aura_amplifier",
            profile="semantic_intent",
            matched_signals=_signals(
                ("extra_damage", "extra damage" in text),
                ("all_sources", "all sources" in text),
                ("both_heroes_take", "both heroes take" in text),
                ("voidtouched_attendant", _has_any(text, ("voidtouched", "attendant"))),
            ),
        )

    if _has_conditional_minion_death_burn(text):
        return SemanticIntentScore(
            value="10",
            band="high",
            reason="conditional_minion_death_burn",
            profile="semantic_intent",
            matched_signals=_signals(
                ("enemy_hero_damage", "enemy hero" in text),
                ("death_condition", _has_any(text, ("if it dies", "dies"))),
                (
                    "minion_targeting",
                    _has_any(text, ("minion", "prefer_enemy_minion", "enemy minion")),
                ),
            ),
        )

    if _has_direct_enemy_hero_burn(text):
        return SemanticIntentScore(
            value="12",
            band="critical",
            reason="direct_enemy_hero_burn",
            profile="semantic_intent",
            matched_signals=_signals(
                (
                    "enemy_hero_targeting",
                    _has_any(
                        text,
                        ("prefer_enemy_hero", "enemy hero", "face", "hero damage"),
                    ),
                ),
                ("damage", _has_damage_wording(text)),
            ),
        )

    if _has_any(text, ("location", "cathedral", "atonement")):
        return SemanticIntentScore(
            value="8",
            band="medium",
            reason="location_tempo",
            profile="semantic_intent",
            matched_signals=_signals(
                ("location", "location" in text),
                ("cathedral", "cathedral" in text),
                ("atonement", "atonement" in text),
            ),
        )

    if _has_any(text, ("draw", "cycle", "discover", "generate", "copy")):
        return SemanticIntentScore(
            value="8",
            band="medium",
            reason="draw_cycle",
            profile="semantic_intent",
            matched_signals=_signals(
                ("draw", "draw" in text),
                ("cycle", "cycle" in text),
                ("discover", "discover" in text),
                ("generate", "generate" in text),
                ("copy", "copy" in text),
            ),
        )

    if _has_any(text, ("summon", "pirate", "treant", "mech", "board", "on_board")):
        return SemanticIntentScore(
            value="8",
            band="medium",
            reason="board_tempo",
            profile="semantic_intent",
            matched_signals=_signals(
                ("summon", "summon" in text),
                ("pirate", "pirate" in text),
                ("treant", "treant" in text),
                ("mech", "mech" in text),
                ("board", _has_any(text, ("board", "on_board"))),
            ),
        )

    return SemanticIntentScore(
        value=str(value_default),
        band="default",
        reason="semantic_default",
        profile="semantic_intent",
    )


def _normalized_claim_text(
    claim: Mapping[str, Any],
    *,
    behavior_block: str,
    intent: str,
    roles: Sequence[str],
) -> str:
    semantic_families = claim.get("semantic_families", [])
    if not isinstance(semantic_families, Sequence) or isinstance(
        semantic_families, (str, bytes)
    ):
        semantic_families = []

    parts = (
        claim.get("claim_kind"),
        claim.get("stance"),
        claim.get("intent"),
        claim.get("mechanic"),
        claim.get("evidence_text_short"),
        claim.get("source_title"),
        behavior_block,
        intent,
        " ".join(str(role) for role in roles),
        " ".join(str(family) for family in semantic_families),
    )
    return " ".join(str(part).lower() for part in parts if part is not None)


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


def _signals(*candidates: tuple[str, bool]) -> tuple[str, ...]:
    return tuple(signal for signal, matched in candidates if matched)


__all__ = ("SemanticIntentScore", "score_card_behavior_claim")
