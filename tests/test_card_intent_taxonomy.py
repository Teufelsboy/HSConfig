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


def test_taxonomy_does_not_treat_attendant_title_alone_as_damage_aura():
    classification = classify_card_intent(
        "Defensive source note from Attendant deck guide with unrelated tech choices."
    )

    assert classification.reason == "semantic_default"
    assert classification.value == "6"
    assert classification.band == "default"
    assert classification.matched_signals == ()


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


def test_direct_burn_does_not_match_face_inside_surface_word():
    classification = classify_card_intent(
        "Card behavior surface damage row without targeting guidance."
    )

    assert classification.reason == "semantic_default"
    assert classification.value == "6"
    assert classification.band == "default"


def test_direct_burn_does_not_match_embedded_phrase_prefixes():
    for text in (
        "enemy heroic damage plan",
        "prefer_enemy_heroic damage plan",
        "hero damageable effect",
    ):
        classification = classify_card_intent(text)
        assert classification.reason == "semantic_default"
        assert classification.value == "6"
        assert classification.band == "default"


def test_direct_burn_still_matches_real_enemy_hero_and_face_phrases():
    for text in (
        "Prefer enemy hero face damage burn.",
        "prefer_enemy_hero damage plan",
        "Deal hero damage directly.",
        "Send face damage now.",
    ):
        classification = classify_card_intent(text)
        assert classification.reason == "direct_enemy_hero_burn"
        assert classification.value == "12"
        assert classification.band == "critical"


def test_taxonomy_classifies_shadowpriest_reciprocal_and_self_damage_semantics():
    shadowbomber = classify_card_intent(
        "<b>Battlecry:</b> Deal 3 damage to each hero. battlecry BATTLECRY"
    )
    acupuncture = classify_card_intent("[x]Deal $4 damage to both heroes.")
    raise_dead = classify_card_intent(
        "Deal $3 damage to your hero. Return two friendly minions that died this game to your hand."
    )
    brain_masseuse = classify_card_intent(
        "[x]Whenever this minion takes damage, also deal that amount to your hero. TRIGGER_VISUAL"
    )
    felwing = classify_card_intent(
        "Costs (1) less for each damage dealt to your opponent this turn."
    )

    assert shadowbomber.reason == "reciprocal_hero_burn"
    assert shadowbomber.value == "10"
    assert shadowbomber.band == "high"
    assert "each_hero" in shadowbomber.matched_signals

    assert acupuncture.reason == "reciprocal_hero_burn"
    assert acupuncture.value == "10"
    assert acupuncture.band == "high"
    assert "both_heroes" in acupuncture.matched_signals

    assert raise_dead.reason == "self_damage_resource"
    assert raise_dead.value == "8"
    assert raise_dead.band == "medium"
    assert "return_dead_friendly_minions" in raise_dead.matched_signals

    assert brain_masseuse.reason == "self_damage_liability_body"
    assert brain_masseuse.value == "6"
    assert brain_masseuse.band == "medium"
    assert "takes_damage_reflects_to_own_hero" in brain_masseuse.matched_signals

    assert felwing.reason == "opponent_damage_discount_tempo"
    assert felwing.value == "8"
    assert felwing.band == "medium"
    assert "opponent_damage_this_turn" in felwing.matched_signals


def test_taxonomy_classifies_shadowpriest_card_identity_when_surface_has_no_card_text():
    assert classify_card_intent("Shadowbomber battlecry damage minion pressure").reason == (
        "reciprocal_hero_burn"
    )
    assert classify_card_intent("Acupuncture combo_piece damage pressure spell").reason == (
        "reciprocal_hero_burn"
    )
    assert classify_card_intent("Raise Dead damage pressure spell").reason == (
        "self_damage_resource"
    )
    assert classify_card_intent("Brain Masseuse damage minion pressure").reason == (
        "self_damage_liability_body"
    )
    assert classify_card_intent("Frenzied Felwing damage minion pressure").reason == (
        "opponent_damage_discount_tempo"
    )
    assert classify_card_intent("Papercraft Angel aura hero_power minion pressure").reason == (
        "hero_power_cost_aura"
    )
    assert classify_card_intent("Mind Blast combo_piece damage pressure spell").reason == (
        "direct_enemy_hero_burn"
    )
    assert classify_card_intent("Mind Sear damage pressure spell").reason == (
        "conditional_minion_death_burn"
    )


def test_damage_aura_still_wins_before_reciprocal_hero_burn():
    classification = classify_card_intent(
        "Voidtouched Attendant makes both heroes take extra damage from all sources."
    )

    assert classification.reason == "damage_aura_amplifier"
    assert classification.value == "10"
    assert classification.band == "critical"
