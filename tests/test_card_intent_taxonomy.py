from hsconfig.card_intent_taxonomy import (
    CardIntentClassification,
    bounded_default_value,
    classify_card_intent,
)


def test_taxonomy_classifies_shadowpriest_core_effects_in_priority_order():
    transform = classify_card_intent(
        "Darkbishop Benedictus changes your starting Hero Power to Mind Spike."
    )
    aura = classify_card_intent(
        "Voidtouched Attendant makes both heroes take extra damage from all sources."
    )
    mind_sear = classify_card_intent(
        "Mind Sear deals 2 damage to a minion and 3 damage to the enemy hero if it dies."
    )

    assert isinstance(transform, CardIntentClassification)
    assert transform.reason == "hero_power_transform"
    assert transform.value == "10"
    assert transform.band == "critical"
    assert "hero_power" in transform.matched_signals

    assert aura.reason == "damage_aura_amplifier"
    assert aura.value == "10"
    assert aura.band == "critical"
    assert "voidtouched_attendant" in aura.matched_signals

    assert mind_sear.reason == "conditional_minion_death_burn"
    assert mind_sear.value == "10"
    assert mind_sear.band == "high"
    assert "death_condition" in mind_sear.matched_signals


def test_taxonomy_classifies_direct_burn_location_draw_and_board_tempo():
    direct = classify_card_intent("Prefer enemy hero face damage burn.")
    location = classify_card_intent("Cathedral of Atonement is a location tempo card.")
    draw = classify_card_intent("Draw and cycle through the deck.")
    board = classify_card_intent("Summon pirates and build a board.")

    assert direct.reason == "direct_enemy_hero_burn"
    assert direct.value == "12"
    assert direct.band == "critical"

    assert location.reason == "location_tempo"
    assert location.value == "8"
    assert location.band == "medium"

    assert draw.reason == "draw_cycle"
    assert draw.value == "8"
    assert draw.band == "medium"

    assert board.reason == "board_tempo"
    assert board.value == "8"
    assert board.band == "medium"


def test_taxonomy_keeps_unknown_mechanics_visible_as_bounded_default():
    low = classify_card_intent("This card has Tradeable.", value_default="2")
    normal = classify_card_intent("This card has Tradeable.", value_default="6")
    high = classify_card_intent("This card has Tradeable.", value_default="99")

    assert low.reason == "semantic_default"
    assert low.value == "4"
    assert low.band == "default"

    assert normal.reason == "semantic_default"
    assert normal.value == "6"
    assert normal.band == "default"

    assert high.reason == "semantic_default"
    assert high.value == "12"
    assert high.band == "default"


def test_bounded_default_value_handles_non_numeric_input():
    assert bounded_default_value("not-a-number") == "6"
