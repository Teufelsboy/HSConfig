from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from hsconfig.deck_identity import normalize_roster, stable_deck_fingerprint
from hsconfig.deckstring_decode import decode_deck_code


DECODED_FROM_DECK_CODE = "decoded_from_deck_code"
CARDS_JSON_MATCHES_DECK_CODE = "cards_json_matches_deck_code"
CARDS_JSON_UNVERIFIED = "cards_json_unverified"
PLACEHOLDER_UNVERIFIED = "placeholder_unverified"

_APPLY_ELIGIBLE_STATUSES = {
    DECODED_FROM_DECK_CODE,
    CARDS_JSON_MATCHES_DECK_CODE,
}


def verify_deck_input(
    *,
    deck_code: str | None,
    cards: Sequence[Mapping[str, Any]],
    source: str,
) -> dict[str, Any]:
    normalized_cards = normalize_roster(cards)
    decoded_cards = _try_decode_roster(deck_code)
    if source == "deckstring" and decoded_cards == normalized_cards:
        status = DECODED_FROM_DECK_CODE
    elif source == "cards_json" and decoded_cards == normalized_cards:
        status = CARDS_JSON_MATCHES_DECK_CODE
    elif source == "placeholder":
        status = PLACEHOLDER_UNVERIFIED
    else:
        status = CARDS_JSON_UNVERIFIED
    return {
        "status": status,
        "runtime_apply_eligible": status in _APPLY_ELIGIBLE_STATUSES,
        "normalized_roster_sha256": (
            f"sha256:{stable_deck_fingerprint(normalized_cards)}"
        ),
    }


def _try_decode_roster(
    deck_code: str | None,
) -> tuple[tuple[str, int], ...] | None:
    if not isinstance(deck_code, str) or not deck_code.strip():
        return None
    try:
        decoded = decode_deck_code(deck_code)
    except (TypeError, ValueError):
        return None
    return normalize_roster(decoded["cards"])
