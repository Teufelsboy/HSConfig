import pytest

from hsconfig.static_semantics import (
    build_static_semantics_source_records,
    infer_static_semantics,
)


def _families(card):
    return set(infer_static_semantics(card)["families"])


def test_infers_mechanics_from_type_mechanics_referenced_tags_and_text():
    card = {
        "id": "TEST_001",
        "type": "WEAPON",
        "mechanics": ["TRADEABLE"],
        "referenced_tags": ["OVERLOAD"],
        "text": "Battlecry: Discover a spell. Dredge. Silence an enemy minion.",
    }

    families = _families(card)

    assert {"weapon", "tradeable", "overload", "battlecry", "discover", "dredge", "silence"} <= families


def test_infers_location_secret_and_generated_entity_patterns():
    card = {
        "id": "TEST_002",
        "type": "LOCATION",
        "mechanics": ["SECRET"],
        "text": "Secret: When your opponent plays a minion, summon a random minion.",
    }

    families = _families(card)

    assert {"location", "secret", "summon", "generated_entity", "generated_entity_random_pool"} <= families


def test_infers_hero_power_transform_and_start_of_game_from_tags_and_text():
    card = {
        "id": "SW_448",
        "type": "MINION",
        "referenced_tags": ["START_OF_GAME_KEYWORD"],
        "text": "Start of Game: If the spells in your deck are all Shadow, enter Shadowform.",
    }

    families = _families(card)

    assert {"start_of_game", "shadowform", "hero_power", "hero_power_transform"} <= families


@pytest.mark.parametrize(
    ("card_id", "card_name", "text"),
    [
        (
            "TOY_518",
            "Treasure Distributor",
            "After you summon a Pirate, give it +1 Attack.",
        ),
        (
            "WON_065",
            "Ship's Chirurgeon",
            "After you summon a minion, give it +1 Health.",
        ),
    ],
)
def test_summon_trigger_board_engine_static_claim_uses_on_board_bonus(
    card_id, card_name, text
):
    card = {
        "id": card_id,
        "name": card_name,
        "type": "MINION",
        "text": text,
    }

    assert "summon_trigger_board_engine" in _families(card)

    records = build_static_semantics_source_records(
        {
            "deck_name": "ShadowPriest",
            "cards": [{"card_id": card_id, "count": 1}],
        },
        {card_id: card},
    )
    claim = next(
        claim
        for claim in records[0]["claims"]
        if claim["mechanic"] == "summon_trigger_board_engine"
    )

    assert claim["runtime_block"] == "OnBoardBonus"


def test_warning_only_contains_unlowerable_choice_surfaces():
    result = infer_static_semantics(
        {
            "id": "TEST_003",
            "type": "SPELL",
            "text": "Dredge. Tradeable. Choose One - Summon a minion; or Draw a card.",
        }
    )

    assert "dredge" in result["families"]
    assert "tradeable" in result["families"]
    assert "choose_one" in result["families"]
    assert "dredge" in result["warning_only"]
    assert "tradeable" in result["warning_only"]


def test_draw_from_deck_is_not_recruit_without_recruit_wording():
    result = infer_static_semantics(
        {
            "id": "TEST_004",
            "type": "SPELL",
            "text": "Draw a card from your deck.",
        }
    )

    assert "draw" in result["families"]
    assert "recruit" not in result["families"]


def test_whenever_trigger_is_not_aura_without_ongoing_board_grant():
    result = infer_static_semantics(
        {
            "id": "TEST_005",
            "type": "MINION",
            "text": "Whenever a minion is healed, draw a card.",
        }
    )

    assert "draw" in result["families"]
    assert "aura" not in result["families"]


def test_random_damage_is_not_generated_entity_pool():
    result = infer_static_semantics(
        {
            "id": "TEST_006",
            "type": "SPELL",
            "text": "Deal random damage to enemies.",
        }
    )

    assert "damage" in result["families"]
    assert "generated_entity_random_pool" not in result["families"]


def test_infers_odd_even_deckbuilding_start_of_game_modifiers():
    genn = {
        "id": "GIL_692",
        "type": "MINION",
        "text": (
            "Start of Game: If your deck has only even-Cost cards, "
            "your starting Hero Power costs (1)."
        ),
    }
    baku = {
        "id": "GIL_826",
        "type": "MINION",
        "text": "Start of Game: If your deck has only odd-Cost cards, upgrade your Hero Power.",
    }

    assert {"start_of_game", "deckbuilding_modifier", "even_odd_modifier"} <= _families(genn)
    assert {"start_of_game", "deckbuilding_modifier", "even_odd_modifier"} <= _families(baku)


def test_infers_highlander_deckbuilding_modifier():
    card = {
        "id": "HIGHLANDER_FIXTURE",
        "type": "MINION",
        "text": "Battlecry: If your deck has no duplicates, deal 10 damage.",
    }

    assert {"deckbuilding_modifier", "highlander_modifier"} <= _families(card)


def test_infers_deck_size_and_starting_health_modifier():
    card = {
        "id": "REV_018",
        "type": "MINION",
        "text": "Your deck size and starting Health are 40.",
    }

    assert {"deckbuilding_modifier", "deck_size_modifier", "deck_state_modifier"} <= _families(card)


def test_infers_start_in_deck_requirement_without_mulligan_semantics():
    card = {
        "id": "START_DECK_FIXTURE",
        "type": "MINION",
        "text": "If this is in your deck at the start of the game, draw it later.",
    }

    assert {"start_of_game", "start_in_deck_requirement", "deckbuilding_modifier"} <= _families(card)


def test_static_semantics_uses_drift_text_registry_for_modern_mechanics():
    result = infer_static_semantics(
        {
            "id": "MODERN_001",
            "type": "SPELL",
            "text": (
                "Rewind. Prepare. Miniaturize. Honorable Kill. "
                "Elusive. Poisonous. Kindred."
            ),
        }
    )

    families = set(result["families"])
    assert {
        "rewind",
        "prepare",
        "miniaturize",
        "honorable_kill",
        "elusive",
        "poisonous",
        "kindred",
    } <= families
    assert {"rewind", "prepare", "kindred"} <= set(result["warning_only"])


def test_plain_card_types_do_not_become_warning_only_mechanics():
    assert infer_static_semantics({"id": "SPELL_ONLY", "type": "SPELL"})["warning_only"] == []
    assert infer_static_semantics({"id": "MINION_ONLY", "type": "MINION"})["warning_only"] == []
