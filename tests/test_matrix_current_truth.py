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
            "source_informed_blocking_reasons": ["unsupported_conditions_present"],
        },
    }


def test_active_operator_docs_do_not_claim_seven_source_informed_rows():
    text = OPERATOR_README.read_text(encoding="utf-8")

    assert "seven `source_informed_valid_fixture` rows" not in text
    assert (
        "Boarlock and Kingslayer are both durable source-informed controls with explicit"
        in text
    )
    assert (
        "Add or promote only when exact source evidence closes a"
        in text
    )
    assert (
        "Close the current Kingslayer and Boarlock `source_informed_valid_fixture` rows "
        "before widening the matrix."
    ) not in text
    assert (
        "Keep the current Kingslayer and Boarlock `source_informed_valid_fixture` rows "
        "closed before widening the matrix."
    ) not in text


def test_active_matrix_stays_at_eleven_representative_decks():
    rows = _matrix_rows()

    assert len(rows) == 11
    assert sum(row["fixture_stage"] == "core_source_backed_fixture" for row in rows) == 9
    assert sum(row["fixture_stage"] == "source_informed_valid_fixture" for row in rows) == 2


def test_source_informed_rows_have_explicit_closure_decisions():
    by_name = {row["deck_name"]: row for row in _matrix_rows()}

    kingslayer = by_name["Kingslayer"]["strongness_visibility"]
    assert kingslayer["first_strongness_gap"] == "needs_mulligan_claim_for_quick_pick"
    assert kingslayer["source_informed_apply_readiness"] == "blocked"
    assert kingslayer["operator_action"] == (
        "preserve_source_informed_with_explicit_stop_condition"
    )
    assert (
        kingslayer["stop_condition"]
        == "exact_kingslayer_quick_pick_mulligan_source_unavailable"
    )

    boarlock = by_name["Boarlock"]["strongness_visibility"]
    assert boarlock["first_strongness_gap"] == "needs_mulligan_claim_for_fracking"
    assert boarlock["source_informed_apply_readiness"] == "blocked"
    assert boarlock["operator_action"] == "preserve_source_informed_with_explicit_stop_condition"
    assert boarlock["stop_condition"] == "exact_boarlock_fracking_mulligan_source_unavailable"


def test_operator_docs_name_both_preserved_rows_and_no_actionable_target():
    operator_text = OPERATOR_README.read_text(encoding="utf-8")
    closure_text = Path("docs/operator/source-backed-strong-closure.md").read_text(
        encoding="utf-8"
    )

    expected = (
        "After durable Boarlock and Kingslayer preservation, there is no current "
        "actionable source-informed closure target."
    )
    assert expected in operator_text
    assert expected in closure_text
    assert "Next actionable closure target after durable Boarlock preservation" not in operator_text
    assert "Next actionable closure target after durable Boarlock preservation" not in closure_text
    assert (
        "Do not treat Boarlock's low-confidence Fracking row as SOURCE_BACKED_STRONG."
        in closure_text
    )
