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
        "normal_next_action": "close_existing_source_informed_rows_before_adding_more_decks",
    }
