from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


EXPLICIT_SOURCE_GAP_REASON = "explicit_source_gap_requires_resolution"


@dataclass(frozen=True)
class MulliganSourceGapRegistration:
    deck_name: str
    card_id: str
    first_missing_source_action: str
    reason: str = EXPLICIT_SOURCE_GAP_REASON


REGISTERED_MULLIGAN_SOURCE_GAPS = (
    MulliganSourceGapRegistration(
        deck_name="Boarlock",
        card_id="WW_092",
        first_missing_source_action=(
            "add_boarlock_fracking_mulligan_source"
        ),
    ),
    MulliganSourceGapRegistration(
        deck_name="Kingslayer",
        card_id="DEEP_014",
        first_missing_source_action=(
            "add_kingslayer_quick_pick_mulligan_source"
        ),
    ),
)


def registered_mulligan_source_gap(
    deck_name: str,
    card_id: str,
) -> MulliganSourceGapRegistration | None:
    normalized_deck_name = normalize_registered_deck_name(deck_name)
    for registration in REGISTERED_MULLIGAN_SOURCE_GAPS:
        if (
            normalize_registered_deck_name(registration.deck_name)
            == normalized_deck_name
            and registration.card_id == card_id
        ):
            return registration
    return None


def build_bound_mulligan_source_gap_rows(
    *,
    deck_name: str,
    deck_identity: Mapping[str, Any],
    unresolved_card_ids: set[str],
) -> list[dict[str, str]]:
    fingerprint = _nonempty_text(deck_identity.get("deck_fingerprint"))
    deck_code_hash = _nonempty_text(deck_identity.get("deck_code_hash"))
    if not fingerprint or not deck_code_hash:
        return []
    deck_card_ids = _deck_card_ids(deck_identity)
    rows: list[dict[str, str]] = []
    for registration in REGISTERED_MULLIGAN_SOURCE_GAPS:
        if (
            normalize_registered_deck_name(registration.deck_name)
            != normalize_registered_deck_name(deck_name)
            or registration.card_id not in unresolved_card_ids
            or registration.card_id not in deck_card_ids
        ):
            continue
        rows.append(
            {
                "target_deck_name": registration.deck_name,
                "target_deck_fingerprint": fingerprint,
                "target_deck_code_hash": deck_code_hash,
                "card_id": registration.card_id,
                "first_missing_source_action": (
                    registration.first_missing_source_action
                ),
                "reason": registration.reason,
            }
        )
    return rows


def normalize_registered_deck_name(value: str) -> str:
    return "".join(
        character.lower()
        for character in str(value)
        if character.isalnum()
    )


def _deck_card_ids(deck_identity: Mapping[str, Any]) -> set[str]:
    cards = deck_identity.get("cards", [])
    if not isinstance(cards, list):
        return set()
    return {
        card_id
        for row in cards
        if isinstance(row, Mapping)
        and (card_id := _nonempty_text(row.get("card_id")))
    }


def _exact_text(value: Any) -> str:
    return value if type(value) is str else ""


def _nonempty_text(value: Any) -> str:
    return _exact_text(value).strip()
