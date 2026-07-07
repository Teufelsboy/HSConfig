from __future__ import annotations

from typing import Any


def build_matrix_visibility(matrix: dict[str, Any]) -> dict[str, Any]:
    rows = list(matrix.get("decks", []))
    core = [row for row in rows if row.get("fixture_stage") == "core_source_backed_fixture"]
    source_informed = [
        row for row in rows if row.get("fixture_stage") == "source_informed_valid_fixture"
    ]
    missing_visibility = [
        row.get("deck_name", "")
        for row in rows
        if not isinstance(row.get("strongness_visibility"), dict)
    ]

    return {
        "schema_version": 1,
        "total_decks": len(rows),
        "core_source_backed_fixture_count": len(core),
        "source_informed_valid_fixture_count": len(source_informed),
        "decks_missing_visibility": missing_visibility,
        "deck_visibility": [_deck_visibility(row) for row in rows],
        "normal_next_action": "close_existing_source_informed_rows_before_adding_more_decks",
    }


def _deck_visibility(row: dict[str, Any]) -> dict[str, str]:
    visibility = row.get("strongness_visibility", {})
    if not isinstance(visibility, dict):
        visibility = {}
    return {
        "deck_name": str(row.get("deck_name", "")),
        "fixture_stage": str(row.get("fixture_stage", "")),
        "first_strongness_gap": str(
            visibility.get("first_strongness_gap", "missing_strongness_visibility")
        ),
        "operator_action": str(
            visibility.get("operator_action", "add_strongness_visibility")
        ),
    }
