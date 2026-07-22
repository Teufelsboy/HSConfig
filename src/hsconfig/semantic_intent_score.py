from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from hsconfig.card_intent_taxonomy import classify_card_intent


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
    explicit = _explicit_value(claim)
    if explicit is not None and str(explicit).strip():
        return SemanticIntentScore(
            value=str(explicit),
            band="explicit",
            reason="explicit_runtime_value",
            profile="source_claim",
            matched_signals=("explicit_value",),
        )

    classification = classify_card_intent(
        _normalized_claim_text(
            claim,
            behavior_block=behavior_block,
            intent=intent,
            roles=roles,
        ),
        value_default=value_default,
    )
    return SemanticIntentScore(
        value=classification.value,
        band=classification.band,
        reason=classification.reason,
        profile="semantic_intent",
        matched_signals=classification.matched_signals,
    )


def _explicit_value(claim: Mapping[str, Any]) -> Any:
    for key in ("runtime_value", "value"):
        explicit = claim.get(key)
        if explicit is not None and str(explicit).strip():
            return explicit
    return None


def _normalized_claim_text(
    claim: Mapping[str, Any],
    *,
    behavior_block: str,
    intent: str,
    roles: Sequence[str],
) -> str:
    semantic_families = claim.get("semantic_families", [])
    if not isinstance(semantic_families, Sequence) or isinstance(
        semantic_families,
        (str, bytes),
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


__all__ = ("SemanticIntentScore", "score_card_behavior_claim")
