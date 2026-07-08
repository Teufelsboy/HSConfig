import json
from pathlib import Path


MATRIX_PATH = Path("docs/operator/archetype-fixture-matrix.json")
DOC_PATH = Path("docs/operator/kingslayer-quick-pick-source-decision.md")


def _kingslayer_row() -> dict:
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    return next(row for row in matrix["decks"] if row["deck_name"] == "Kingslayer")


def test_kingslayer_quick_pick_decision_doc_records_stop_condition():
    text = DOC_PATH.read_text(encoding="utf-8")

    assert "# Kingslayer Quick Pick Source Decision" in text
    assert "`DEEP_014` / `Quick Pick`" in text
    assert "Do not promote Kingslayer to `core_source_backed_fixture`" in text
    assert "exact_kingslayer_quick_pick_mulligan_source_unavailable" in text
    assert "Adjacent archetype advice is not source-backed evidence" in text


def test_kingslayer_matrix_row_preserves_source_informed_until_exact_source_exists():
    row = _kingslayer_row()
    visibility = row["strongness_visibility"]

    assert row["fixture_stage"] == "source_informed_valid_fixture"
    assert visibility["first_strongness_gap"] == "needs_mulligan_claim_for_quick_pick"
    assert visibility["operator_action"] == (
        "preserve_source_informed_with_explicit_stop_condition"
    )
    assert visibility["stop_condition"] == (
        "exact_kingslayer_quick_pick_mulligan_source_unavailable"
    )
    assert visibility["source_informed_blocking_reasons"] == [
        "unsupported_conditions_present"
    ]
