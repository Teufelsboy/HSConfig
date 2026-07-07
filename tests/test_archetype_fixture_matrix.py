import json
from pathlib import Path


MATRIX_PATH = Path("docs/operator/archetype-fixture-matrix.json")
EXPECTED_DECKS = {
    "ShadowPriest",
    "CtAPaladin",
    "PirateRogue",
    "BigShaman",
    "Discolock",
    "TreantDruid",
    "ImbueMage",
    "MechPala",
    "Kingslayer",
    "Boarlock",
    "PirateDH",
}
CORE_FIXTURES = {"ShadowPriest", "BigShaman", "Discolock", "Kingslayer", "ImbueMage"}


def _matrix():
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def test_archetype_fixture_matrix_covers_supplied_decks():
    matrix = _matrix()
    assert matrix["schema_version"] == 1
    decks = {row["deck_name"] for row in matrix["decks"]}
    assert decks == EXPECTED_DECKS


def test_archetype_fixture_matrix_has_actionable_rows():
    for row in _matrix()["decks"]:
        assert row["deck_code"]
        assert row["hs_id"]
        assert row["hdt_deck_id"]
        assert row["archetype_bucket"]
        assert row["primary_mechanics"]
        assert "GlobalValues.json" in row["expected_runtime_surfaces"]
        assert "Mulligan.json" in row["expected_runtime_surfaces"]
        assert "<CARDID>.json" in row["expected_runtime_surfaces"]
        assert row["fixture_stage"] in {
            "core_source_backed_fixture",
            "second_wave_source_fixture",
        }


def test_archetype_fixture_matrix_marks_core_wave():
    core = {
        row["deck_name"]
        for row in _matrix()["decks"]
        if row["fixture_stage"] == "core_source_backed_fixture"
    }
    assert core == CORE_FIXTURES
