import pytest

from hsconfig.static_semantics import infer_static_semantics


CASES = [
    (
        "secret_hidden_interrupt",
        {
            "type": "SPELL",
            "mechanics": ["SECRET"],
            "text": "Secret: When your opponent plays a minion, counter it.",
        },
        {"secret", "secret_timing"},
        {"secret_timing"},
    ),
    (
        "dredge_tradeable",
        {"type": "SPELL", "mechanics": ["TRADEABLE"], "text": "Dredge. Tradeable."},
        {"dredge", "tradeable"},
        {"dredge", "tradeable"},
    ),
    (
        "deathrattle_reborn",
        {
            "type": "MINION",
            "mechanics": ["DEATHRATTLE", "REBORN"],
            "text": "Deathrattle: Summon a minion.",
        },
        {"minion", "deathrattle", "reborn", "summon"},
        set(),
    ),
    (
        "recruit_from_deck",
        {"type": "SPELL", "text": "Recruit a minion from your deck."},
        {"spell", "recruit"},
        set(),
    ),
    (
        "location_activation",
        {"type": "LOCATION", "text": "Give a minion +2 Attack."},
        {"location", "location_activation"},
        {"location_activation"},
    ),
    (
        "discard_destroy_silence_transform",
        {
            "type": "SPELL",
            "text": "Discard a card. Destroy a minion. Silence it, then transform it.",
        },
        {"spell", "discard", "destroy", "silence", "transform"},
        set(),
    ),
    (
        "modern_lowerable_and_report_only_keywords",
        {
            "type": "SPELL",
            "text": (
                "Spellburst: Draw a card. Quickdraw: Deal 2 damage. "
                "Finale: Summon a minion. Manathirst (6): Gain +2/+2. "
                "Infuse (3): Costs less. Corrupt: Become upgraded. "
                "Forge: Gain Armor. Outcast: Draw a card. Titan. Launch your Starship."
            ),
        },
        {
            "spellburst",
            "quickdraw",
            "finale",
            "manathirst",
            "infuse",
            "corrupt",
            "forge",
            "outcast",
            "titan",
            "starship",
        },
        {"forge", "outcast", "titan", "starship"},
    ),
]


@pytest.mark.parametrize(
    ("name", "card", "expected_families", "expected_warning_only"),
    CASES,
)
def test_static_semantic_micro_fixture(
    name,
    card,
    expected_families,
    expected_warning_only,
):
    result = infer_static_semantics({"id": name, **card})

    assert expected_families <= set(result["families"])
    assert expected_warning_only <= set(result["warning_only"])
