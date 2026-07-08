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


def _deck_visibility(row: dict[str, Any]) -> dict[str, Any]:
    visibility = row.get("strongness_visibility", {})
    if not isinstance(visibility, dict):
        visibility = {}
    fixture_stage = str(row.get("fixture_stage", ""))
    blocking_reasons = visibility.get("source_informed_blocking_reasons", [])
    if not isinstance(blocking_reasons, list):
        blocking_reasons = []
    blocking_reasons = [str(reason) for reason in blocking_reasons]
    first_gap = str(
        visibility.get("first_strongness_gap", "missing_strongness_visibility")
    )
    operator_action = str(
        visibility.get("operator_action", "add_strongness_visibility")
    )
    stop_condition = visibility.get("stop_condition")
    if stop_condition is not None:
        stop_condition = str(stop_condition)

    closure_state = "core_strong"
    if fixture_stage == "source_informed_valid_fixture":
        closure_state = (
            "source_informed_blocked" if blocking_reasons else "source_informed_gap_only"
        )

    closure_priority = 0
    if closure_state == "source_informed_blocked":
        closure_priority = 1 if len(blocking_reasons) > 1 else 2

    return {
        "deck_name": str(row.get("deck_name", "")),
        "fixture_stage": fixture_stage,
        "first_strongness_gap": first_gap,
        "operator_action": operator_action,
        "stop_condition": stop_condition,
        "closure_state": closure_state,
        "source_informed_blocking_reasons": blocking_reasons,
        "closure_priority": closure_priority,
    }
