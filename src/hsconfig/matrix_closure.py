from __future__ import annotations

from typing import Any


def build_matrix_closure_summary(
    *,
    matrix_rows: list[dict[str, Any]],
    results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    decks: dict[str, dict[str, Any]] = {}
    valid_package_count = 0
    strong_count = 0
    source_informed_count = 0
    blocked_card_count = 0

    for row in matrix_rows:
        deck_name = str(row.get("deck_name", ""))
        result = results.get(deck_name, {})
        operator = result.get("operator", {})
        source_gap = result.get("source_gap", {})
        gap_summary = source_gap.get("summary", {}) if isinstance(source_gap, dict) else {}
        technical_status = str(operator.get("technical_status", ""))
        semantic_status = str(operator.get("semantic_status", ""))
        blocked_cards = int(gap_summary.get("blocked_cards", 0))
        valid_package_count += int(technical_status == "VALID_PACKAGE")
        strong_count += int(semantic_status == "SOURCE_BACKED_STRONG")
        source_informed_count += int(semantic_status == "VALID_BUT_NOT_GUIDE_STRONG")
        blocked_card_count += blocked_cards
        decks[deck_name] = {
            "fixture_stage": str(row.get("fixture_stage", "")),
            "technical_status": technical_status,
            "semantic_status": semantic_status,
            "blocked_cards": blocked_cards,
            "first_missing_chain": gap_summary.get("first_missing_chain"),
        }

    return {
        "schema_version": 1,
        "summary": {
            "deck_count": len(matrix_rows),
            "valid_package_count": valid_package_count,
            "source_backed_strong_count": strong_count,
            "source_informed_count": source_informed_count,
            "blocked_card_count": blocked_card_count,
        },
        "decks": decks,
    }
