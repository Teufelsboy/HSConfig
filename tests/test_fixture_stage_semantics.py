from __future__ import annotations

from tests.helpers.fixture_prepare import load_archetype_matrix


ALLOWED_FIXTURE_STAGES = {
    "core_source_backed_fixture",
    "source_informed_valid_fixture",
    "future_fixture",
}


def test_fixture_stage_values_are_explicit():
    decks = load_archetype_matrix()

    assert {deck["fixture_stage"] for deck in decks} <= ALLOWED_FIXTURE_STAGES


def test_shadowpriest_remains_core_source_backed_fixture():
    decks = {deck["deck_name"]: deck for deck in load_archetype_matrix()}

    assert decks["ShadowPriest"]["fixture_stage"] == "core_source_backed_fixture"
