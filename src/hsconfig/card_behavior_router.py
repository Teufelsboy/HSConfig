from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from hsconfig.card_behavior_surface_router import (
    diagnose_card_behavior_surfaces,
    route_card_behavior_surfaces,
)


def diagnose_card_behavior_claims(
    claims: list[dict[str, Any]],
    *,
    card_metadata: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return suppressions only; diagnostic claims have no runtime-row API."""
    return diagnose_card_behavior_surfaces(
        claims,
        card_metadata=card_metadata,
    )


def route_card_behavior_claims(
    claims: list[dict[str, Any]],
    identity_links: dict[str, Any] | None = None,
    *,
    deck_identity: Mapping[str, Any] | None = None,
    card_metadata: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None = None,
    verified_source_receipts: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    plan = route_card_behavior_surfaces(
        claims,
        identity_links=identity_links,
        deck_identity=deck_identity,
        card_metadata=card_metadata,
        verified_source_receipts=verified_source_receipts,
    )
    card_rows: dict[str, list[dict[str, Any]]] = {}
    for row in plan["rows"]:
        card_rows.setdefault(str(row["card_id"]), []).append(row)

    return {
        "card_rows": {card_id: card_rows[card_id] for card_id in sorted(card_rows)},
        "rows": plan["rows"],
        "suppressed": plan["suppressed"],
        "option_resolution": plan["option_resolution"],
        "merged_duplicate_runtime_row_count": plan[
            "merged_duplicate_runtime_row_count"
        ],
        "runtime_row_conflicts": plan["runtime_row_conflicts"],
    }
