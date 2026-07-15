import json
from pathlib import Path

from hsconfig.matrix_visibility import build_matrix_visibility


def test_matrix_visibility_summarizes_core_and_source_informed_rows():
    matrix = json.loads(Path("docs/operator/archetype-fixture-matrix.json").read_text(encoding="utf-8"))
    report = build_matrix_visibility(matrix)

    assert report["total_decks"] == 11
    assert report["core_source_backed_fixture_count"] == 5
    assert report["source_informed_valid_fixture_count"] == 6
    assert report["normal_next_action"] == (
        "keep_closed_matrix_until_new_exact_source_or_family_gap"
    )


def test_each_matrix_row_exposes_first_strongness_link():
    matrix = json.loads(Path("docs/operator/archetype-fixture-matrix.json").read_text(encoding="utf-8"))

    for row in matrix["decks"]:
        visibility = row["strongness_visibility"]
        assert visibility["current_stage"] == row["fixture_stage"]
        assert visibility["first_strongness_gap"]
        assert visibility["operator_action"]
        if row["fixture_stage"] == "core_source_backed_fixture":
            assert visibility["first_strongness_gap"] == "none"
            assert visibility["operator_action"] == "keep_as_core_control_fixture"
        else:
            assert visibility["first_strongness_gap"] != "none"
            if row["deck_name"] == "Boarlock":
                assert visibility["operator_action"] == (
                    "preserve_source_informed_with_explicit_stop_condition"
                )
                assert visibility["stop_condition"] == (
                    "exact_boarlock_fracking_mulligan_source_unavailable"
                )
            elif row["deck_name"] == "Kingslayer":
                assert visibility["operator_action"] == (
                    "preserve_source_informed_with_explicit_stop_condition"
                )
                assert visibility["stop_condition"] == (
                    "exact_kingslayer_quick_pick_mulligan_source_unavailable"
                )
            else:
                assert visibility["operator_action"] == (
                    "preserve_source_informed_with_evidence_gap"
                )
                assert visibility.get("stop_condition") is None


def test_matrix_visibility_report_exposes_deck_level_strongness_gaps():
    matrix = json.loads(Path("docs/operator/archetype-fixture-matrix.json").read_text(encoding="utf-8"))
    report = build_matrix_visibility(matrix)

    assert len(report["deck_visibility"]) == 11
    assert report["deck_visibility"][0] == {
        "deck_name": "ShadowPriest",
        "fixture_stage": "core_source_backed_fixture",
        "first_strongness_gap": "none",
        "operator_action": "keep_as_core_control_fixture",
        "stop_condition": None,
        "closure_state": "core_strong",
        "source_informed_blocking_reasons": [],
        "closure_priority": 0,
    }
    assert {
        "deck_name": "CtAPaladin",
        "fixture_stage": "source_informed_valid_fixture",
        "first_strongness_gap": "needs_explicit_mulligan_source",
        "operator_action": "preserve_source_informed_with_evidence_gap",
        "stop_condition": None,
        "closure_state": "source_informed_blocked",
        "source_informed_blocking_reasons": ["policy_claim_not_strong_evidence"],
        "closure_priority": 2,
    } in report["deck_visibility"]


def test_matrix_visibility_exposes_source_informed_blockers_and_priority():
    matrix = json.loads(Path("docs/operator/archetype-fixture-matrix.json").read_text(encoding="utf-8"))
    report = build_matrix_visibility(matrix)

    by_name = {row["deck_name"]: row for row in report["deck_visibility"]}

    assert by_name["Kingslayer"]["closure_state"] == "source_informed_blocked"
    assert by_name["Kingslayer"]["source_informed_blocking_reasons"] == [
        "unsupported_conditions_present"
    ]
    assert by_name["Kingslayer"]["closure_priority"] == 2
    assert by_name["Kingslayer"]["operator_action"] == (
        "preserve_source_informed_with_explicit_stop_condition"
    )
    assert by_name["Kingslayer"]["stop_condition"] == (
        "exact_kingslayer_quick_pick_mulligan_source_unavailable"
    )

    assert by_name["Boarlock"]["closure_state"] == "source_informed_blocked"
    assert by_name["Boarlock"]["source_informed_blocking_reasons"] == [
        "unsupported_conditions_present",
    ]
    assert by_name["Boarlock"]["closure_priority"] == 2
    assert by_name["Boarlock"]["operator_action"] == (
        "preserve_source_informed_with_explicit_stop_condition"
    )
    assert by_name["Boarlock"]["stop_condition"] == (
        "exact_boarlock_fracking_mulligan_source_unavailable"
    )
