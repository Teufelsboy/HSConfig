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
        row["deck_name"]: {
            "first_strongness_gap": row["strongness_visibility"]["first_strongness_gap"],
            "source_informed_apply_readiness": row["strongness_visibility"][
                "source_informed_apply_readiness"
            ],
            "source_informed_blocking_reasons": row["strongness_visibility"][
                "source_informed_blocking_reasons"
            ],
        }
        for row in _matrix_rows()
        if row["fixture_stage"] == "source_informed_valid_fixture"
    }

    assert source_informed == {
        "Kingslayer": {
            "first_strongness_gap": "needs_mulligan_claim_for_quick_pick",
            "source_informed_apply_readiness": "blocked",
            "source_informed_blocking_reasons": ["unsupported_conditions_present"],
        },
        "Boarlock": {
            "first_strongness_gap": "needs_mulligan_claim_for_fracking",
            "source_informed_apply_readiness": "blocked",
            "source_informed_blocking_reasons": [
                "cards_need_runtime_surface",
                "generic_low_confidence_cards",
                "uncovered_cards",
                "unsupported_conditions_present",
            ],
        },
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
