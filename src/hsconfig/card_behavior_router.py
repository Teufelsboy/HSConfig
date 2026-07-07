from __future__ import annotations

from typing import Any

from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces


def route_card_behavior_claims(
    claims: list[dict[str, Any]],
    identity_links: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan = route_card_behavior_surfaces(claims, identity_links=identity_links)
    card_rows: dict[str, list[dict[str, Any]]] = {}
    for row in plan["rows"]:
        card_rows.setdefault(str(row["card_id"]), []).append(row)

    return {
        "card_rows": {card_id: card_rows[card_id] for card_id in sorted(card_rows)},
        "rows": plan["rows"],
        "suppressed": plan["suppressed"],
        "option_resolution": plan["option_resolution"],
    }
