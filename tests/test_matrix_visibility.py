import json
from pathlib import Path

from hsconfig.matrix_visibility import build_matrix_visibility


def test_matrix_visibility_summarizes_core_and_source_informed_rows():
    matrix = json.loads(Path("docs/operator/archetype-fixture-matrix.json").read_text(encoding="utf-8"))
    report = build_matrix_visibility(matrix)

    assert report["total_decks"] == 11
    assert report["core_source_backed_fixture_count"] == 4
    assert report["source_informed_valid_fixture_count"] == 7
    assert report["normal_next_action"] == "close_existing_source_informed_rows_before_adding_more_decks"


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
            assert visibility["operator_action"].startswith("close_existing_")


def test_matrix_visibility_report_exposes_deck_level_strongness_gaps():
    matrix = json.loads(Path("docs/operator/archetype-fixture-matrix.json").read_text(encoding="utf-8"))
    report = build_matrix_visibility(matrix)

    assert len(report["deck_visibility"]) == 11
    assert report["deck_visibility"][0] == {
        "deck_name": "ShadowPriest",
        "fixture_stage": "core_source_backed_fixture",
        "first_strongness_gap": "none",
        "operator_action": "keep_as_core_control_fixture",
    }
    assert {
        "deck_name": "CtAPaladin",
        "fixture_stage": "source_informed_valid_fixture",
        "first_strongness_gap": "needs_recruit_aura_runtime_surface_closure",
        "operator_action": "close_existing_source_informed_fixture",
    } in report["deck_visibility"]
