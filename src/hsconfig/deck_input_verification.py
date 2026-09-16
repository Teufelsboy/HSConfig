from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from hearthstone.deckstrings import parse_deckstring

from hsconfig.deck_identity import build_deck_identity, normalize_roster, stable_deck_fingerprint
from hsconfig.deckstring_decode import decode_deck_code, decode_deck_code_from_snapshot

if TYPE_CHECKING:
    from hsconfig.input_snapshot_manifest import FrozenCompilerInputs


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


def verify_frozen_deck_input(
    *,
    deck_code: str,
    deck_identity: Mapping[str, Any],
    source: str,
    frozen_compiler_inputs: FrozenCompilerInputs,
) -> dict[str, Any]:
    """Replay identity from the carrier already rebound to package approval.

    This is a recomputation, not an authority shortcut: the apply gate validates
    every frozen blob and rebuilds the approved context before calling here.
    """
    from hsconfig.input_snapshot_manifest import validate_quality_inputs
    from hsconfig.package_request import FrozenJsonDocument

    frozen = frozen_compiler_inputs
    deck = frozen.deck.to_value()
    if (
        source != "deckstring"
        or source != deck["cards_payload"]["card_source"]
        or deck_code != deck["cards_payload"]["deck_code"]
    ):
        raise ValueError("quality_deck_input_binding_mismatch")
    full_cards = frozen.full_cards.to_value()
    collectible_cards = frozen.collectible_cards.to_value()
    quality = validate_quality_inputs(
        frozen.quality_inputs, full_cards=full_cards, collectible_cards=collectible_cards,
    )
    snapshot = FrozenJsonDocument.from_value({
        "full_cards": full_cards,
        "collectible_cards": collectible_cards,
        "dbf_to_card_id": {
            str(row["dbf_id"]): row["id"]
            for row in full_cards if row.get("dbf_id") is not None
        },
        "captured_at": quality["card_snapshot_captured_at"],
        "upstream_version": quality["card_snapshot_upstream_version"],
        "dataset_sha256": quality["card_snapshot_sha256"],
    })
    normalized_code = deck_code.strip()
    normalized_code += "=" * (-len(normalized_code) % 4)
    parsed = parse_deckstring(normalized_code)
    heroes = parsed.heroes if hasattr(parsed, "heroes") else parsed[1]
    if len(heroes) != 1:
        raise ValueError("quality_deck_hero_invalid")
    decoded = decode_deck_code_from_snapshot(deck_code, snapshot)
    if decoded["hero"]["type"] != "HERO":
        raise ValueError("quality_deck_hero_invalid")
    recomputed = build_deck_identity(
        deck_name=deck["deck_identity"]["deck_name"], deck_code=deck_code,
        cards=decoded["cards"], hero_dbf_id=decoded["hero_dbf_id"],
        format=decoded["format"], sideboards=decoded["sideboards"],
    )
    if recomputed != deck["deck_identity"] or recomputed != deck_identity:
        raise ValueError("quality_deck_identity_mismatch")
    return {
        "status": DECODED_FROM_DECK_CODE,
        "runtime_apply_eligible": True,
        "normalized_roster_sha256": "sha256:" + stable_deck_fingerprint(
            normalize_roster(decoded["cards"])
        ),
    }
