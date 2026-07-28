import pytest

from hsconfig.source_claim_context import has_explicit_mulligan_context


@pytest.mark.parametrize(
    "text",
    [
        "Play Fixture One on curve to pressure the opponent.",
        "Keep pressure on the opponent with Fixture One.",
        "Fixture One changes the Hero Power at the start of the game.",
        "Use premulligan planning for Fixture One.",
        "Fixture One supports the opening handrail setup.",
    ],
)
def test_ordinary_strategy_text_has_no_explicit_mulligan_context(text):
    assert has_explicit_mulligan_context(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "Mulligan: keep Fixture One.",
        "Keep Fixture One in the opening hand.",
        "Keep Fixture One in the opening-hand.",
    ],
)
def test_opening_hand_or_mulligan_text_has_explicit_context(text):
    assert has_explicit_mulligan_context(text) is True
