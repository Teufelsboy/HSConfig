"""Bounded query and literal-context quality without new evidence authority."""

from copy import deepcopy
from dataclasses import replace
import json

import pytest

from hsconfig import live_start_controller as controller
from hsconfig.card_snapshot import build_card_snapshot
from hsconfig.live_start_research import build_research_request, validate_research_request
from tests.test_live_start_research import (
    DIGEST,
    IDENTITY,
    projected_observations,
    synthetic_source_record,
)
from tests.test_quality_live_start_controller import quality_request  # noqa: F401


def request(identity, queries=()):
    return build_research_request(
        run_id="quality-query", deck_identity=identity,
        captured_input_sha256=DIGEST, queries=queries,
    ).to_value()


@pytest.mark.parametrize("label", ["Dragon Mage", "DragonMage"])
def test_query_selects_named_signature_and_class_cards_instead_of_roster_prefix(label):
    identity = {**IDENTITY, "deck_name": label, "cards": [
        {"card_id": "A", "name": "Neutral One", "card_class": "NEUTRAL"},
        {"card_id": "B", "name": "Neutral Two", "card_class": "NEUTRAL"},
        {"card_id": "C", "name": "Neutral Three", "card_class": "NEUTRAL"},
        {"card_id": "Z", "name": "Dragon Engine", "card_class": "NEUTRAL"},
        {"card_id": "Y", "name": "Arcane Focus", "card_class": "MAGE"},
        {"card_id": "X", "name": "Frost Anchor", "card_class": "MAGE"},
    ]}
    original = deepcopy(identity)
    value = request(identity)
    assert value["queries"][0] == (
        "Wild MAGE Dragon Engine Frost Anchor Arcane Focus guide mulligan"
    )
    assert identity == original
    assert value["deck_identity"] == original
    assert request({**identity, "cards": list(reversed(identity["cards"]))})["queries"] == value["queries"]


def test_query_deduplicates_names_and_uses_stable_ids_when_optional_facts_missing():
    identity = {**IDENTITY, "cards": [
        {"card_id": "Z", "name": "Same Card"},
        {"card_id": "Y", "name": "Same Card"},
        {"card_id": "A", "name": "First Card"},
        {"card_id": "B", "name": "Second Card"},
    ]}
    assert request(identity)["queries"][0] == (
        "Wild MAGE First Card Second Card Same Card guide mulligan"
    )


def test_query_ignores_missing_names_and_case_duplicate_aliases():
    identity = {**IDENTITY, "cards": [
        {"card_id": "A", "name": None},
        {"card_id": "B", "name": "   "},
        {"card_id": "C", "name": "Real Card"},
        {"card_id": "D", "name": "real card"},
        {"card_id": "E"},
    ]}
    assert request(identity)["queries"][0] == "Wild MAGE Real Card guide mulligan"


def test_explicit_queries_and_historical_request_do_not_follow_new_selection():
    queries = ("Wild old exact guide", "Wild older mulligan")
    value = request(IDENTITY, queries)
    assert value["queries"] == list(queries)
    assert value["limits"] == {"search_calls": 2, "pages": 3, "total_seconds": 30, "request_seconds": 10}
    assert validate_research_request(
        value, run_id="quality-query", deck_identity=IDENTITY,
        captured_input_sha256=DIGEST,
    ).to_value() == value


@pytest.mark.parametrize("reverse", [False, True])
def test_nearby_cardless_matchup_qualification_stays_with_literal_card_anchor(reverse):
    sentences = ["Alpha Mage is a flexible card.", "Matchup plan.", "Against aggro, never spend the last removal early."]
    if reverse:
        sentences.reverse()
    text = " ".join(sentences)
    rows = projected_observations(synthetic_source_record(text))
    assert any(row["supporting_text"] == text for row in rows)
    assert all(row["card_ids"] == ["TEST_A"] for row in rows)
    assert all(row["supporting_text"] in text and len(row["supporting_text"]) <= 600 for row in rows)
    assert all("context_only_not_runtime_authority" in row["limitations"] for row in rows)


def test_distant_cardless_strategy_is_not_attributed_to_unrelated_card():
    text = ("Alpha Mage is flexible. Details follow. Navigation here. Another section. "
            "Further discussion. Against aggro, never spend the last removal early.")
    rows = projected_observations(synthetic_source_record(text))
    assert rows
    assert all("Against aggro" not in row["supporting_text"] for row in rows)
    assert projected_observations(synthetic_source_record("Against aggro, never spend the last removal early.")) == []


def test_controller_query_uses_captured_class_without_changing_sealed_deck_identity(
    request, monkeypatch,
):
    quality_request_value = request.getfixturevalue("quality_request")
    snapshot = controller.fetch_card_snapshot().to_value()
    members = sorted(row["id"] for row in snapshot["full_cards"] if row["collectible"])
    selected = members[-3:]
    rows = [
        {**row, "cardClass": "PRIEST" if row["id"] in selected or row["type"] == "HERO" else "NEUTRAL"}
        for row in snapshot["full_cards"]
    ]
    captured = build_card_snapshot(rows, captured_at=snapshot["captured_at"])
    monkeypatch.setattr(controller, "fetch_card_snapshot", lambda **_: captured)
    result = controller.prepare_quality_live_start(replace(quality_request_value, deck_name="Custom Deck"))
    value = json.loads(result.acquisition_request_path.read_text(encoding="utf-8"))
    names = {row["id"]: row["name"] for row in rows}
    assert all(names[card_id] in value["queries"][0] for card_id in selected)
    assert all("card_class" not in row for row in value["deck_identity"]["cards"])


def test_context_extension_spends_at_most_two_extra_sentences_total():
    sentences = [
        "Against aggro, never spend the last removal early.",
        "Plan notes.", "Card notes.", "Alpha Mage is flexible.",
        "More card notes.", "More plan notes.",
        "Against control, never exhaust all resources early.",
    ]
    text = " ".join(sentences)
    rows = projected_observations(synthetic_source_record(text))
    assert len(rows) == 1
    assert rows[0]["supporting_text"] == " ".join(sentences[:5])


def test_long_qualified_context_keeps_card_anchor_and_marks_truncation():
    text = ("Alpha Mage is flexible. Plan notes. Against aggro, never "
            + "spend resources early " * 50 + ".")
    rows = projected_observations(synthetic_source_record(text))
    assert rows
    assert all(row["card_ids"] == ["TEST_A"] for row in rows)
    assert all(row["supporting_text"] in text and len(row["supporting_text"]) <= 600 for row in rows)
    assert all("source_context_incomplete" in row["limitations"] for row in rows)


@pytest.mark.parametrize("side", ["left", "right"])
def test_second_consecutive_qualifier_uses_one_remaining_sentence_not_original_distance(side):
    anchor = ["Alpha Mage is flexible.", "Plan notes."]
    qualifiers = [
        "Against aggro, keep your removal.",
        "However against control, never keep it.",
    ]
    sentences = anchor + qualifiers if side == "right" else qualifiers + list(reversed(anchor))
    text = " ".join(sentences)
    rows = projected_observations(synthetic_source_record(text))
    assert len(rows) == 1
    assert rows[0]["supporting_text"] == text
    assert rows[0]["card_ids"] == ["TEST_A"]
