import pytest

from hsconfig.source_claim_context import (
    has_explicit_mulligan_context,
    is_explicit_combo_sentence,
)


@pytest.mark.parametrize(
    "text",
    [
        "Play Fixture One on curve to pressure the opponent.",
        "Keep pressure on the opponent with Fixture One.",
        "Fixture One changes the Hero Power at the start of the game.",
        "Use premulligan planning for Fixture One.",
        "Fixture One supports the opening handrail setup.",
        "Use an opening hand-off with Fixture One.",
        "Follow the opening hand-written plan for Fixture One.",
    ],
)
def test_ordinary_strategy_text_has_no_explicit_mulligan_context(text):
    assert has_explicit_mulligan_context(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "Mulligan: keep Fixture One.",
        "When mulliganing, keep Fixture One.",
        "Keep Fixture One in the opening hand.",
        "Keep Fixture One in the opening-hand.",
    ],
)
def test_opening_hand_or_mulligan_text_has_explicit_context(text):
    assert has_explicit_mulligan_context(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Card A + Card B",
        "Combo:\n- Card A\n- Card B",
        "Use Card A with Card B in this deck.",
        "Exact deck list: Card A, Card B.",
    ],
)
def test_combo_coexistence_without_directed_connector_is_not_explicit(text):
    assert is_explicit_combo_sentence(text, ["Card A", "Card B"]) is False


@pytest.mark.parametrize(
    "text",
    [
        "Card A then Card B",
        "Card A into Card B",
        "Card A followed by Card B",
        "Card A -> Card B",
    ],
)
def test_supported_directed_connector_is_explicit_combo_evidence(text):
    assert is_explicit_combo_sentence(text, ["Card A", "Card B"]) is True


def test_combo_card_order_must_match_textual_left_to_right_order():
    text = "Combo: Card B then Card A."

    assert is_explicit_combo_sentence(text, ["Card B", "Card A"]) is True
    assert is_explicit_combo_sentence(text, ["Card A", "Card B"]) is False
