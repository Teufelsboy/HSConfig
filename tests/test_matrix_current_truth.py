import json
from pathlib import Path


MATRIX_PATH = Path("docs/operator/archetype-fixture-matrix.json")
OPERATOR_README = Path("docs/operator/README.md")


def _matrix_rows():
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))["decks"]


def test_active_matrix_has_only_kingslayer_and_boarlock_source_informed():
    source_informed = {
        row["deck_name"]
        for row in _matrix_rows()
        if row["fixture_stage"] == "source_informed_valid_fixture"
    }

    assert source_informed == {"Kingslayer", "Boarlock"}


def test_source_informed_rows_are_expected_current_candidates():
    source_informed = {
        row["deck_name"]: row["strongness_visibility"]["first_strongness_gap"]
        for row in _matrix_rows()
        if row["fixture_stage"] == "source_informed_valid_fixture"
    }

    assert source_informed == {
        "Kingslayer": "needs_mulligan_claim_for_quick_pick",
        "Boarlock": "needs_mulligan_claim_for_fracking",
    }


def test_active_operator_docs_do_not_claim_seven_source_informed_rows():
    text = OPERATOR_README.read_text(encoding="utf-8")

    assert "seven `source_informed_valid_fixture` rows" not in text
    assert (
        "Close the current Kingslayer and Boarlock `source_informed_valid_fixture` rows "
        "before widening the matrix."
    ) in text
    assert (
        "Keep the current Kingslayer and Boarlock `source_informed_valid_fixture` rows "
        "closed before widening the matrix."
    ) not in text
