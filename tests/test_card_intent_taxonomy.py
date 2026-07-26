import pytest

from hsconfig.card_intent_taxonomy import (
    CardIntentClassification,
    bounded_default_value,
    classify_card_intent,
)


@pytest.mark.parametrize(
    ("card_id", "expected_reason"),
    [
        ("CFM_637", "automatic_from_deck_trigger"),
        ("DRG_056", "automatic_from_hand_trigger"),
        ("YOD_032", "conditional_cost_reduction"),
        ("SCH_514", "conditional_self_damage_resource"),
        ("SW_444", "conditional_draw"),
        ("NX2_019", "conditional_target_kill_burn"),
        ("VAC_512", "self_damage_liability_body"),
        ("REV_290", "location_deploy"),
    ],
)
def test_shadowpriest_risky_cards_have_precise_semantic_reason(
    card_id, expected_reason
):
    result = classify_card_intent("", card_identity=card_id)
    assert result.reason == expected_reason


def test_taxonomy_classifies_shadowpriest_core_effects_in_priority_order():
    transform = classify_card_intent(
        "Darkbishop Benedictus changes your starting Hero Power to Mind Spike."
    )
    aura = classify_card_intent(
        "Voidtouched Attendant makes both heroes take extra damage from all sources.",
        card_identity="SW_446",
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

    assert mind_sear.reason == "conditional_target_kill_burn"
    assert mind_sear.value == "10"
    assert mind_sear.band == "high"
    assert "death_condition" in mind_sear.matched_signals


@pytest.mark.parametrize(
    ("card_id", "text"),
    [
        ("TOY_518", "After you summon a Pirate, give it +1 Attack."),
        ("WON_065", "After you summon a minion, give it +1 Health."),
    ],
)
def test_taxonomy_classifies_summon_trigger_board_engines(card_id, text):
    classification = classify_card_intent(text, card_identity=card_id)

    assert classification.reason == "summon_trigger_board_engine"
    assert classification.value == "8"
    assert classification.band == "medium"


@pytest.mark.parametrize(
    "card_identity",
    [
        "TOY_518",
        "Treasure Distributor",
        "WON_065",
        "Ship's Chirurgeon",
        "Ship’s Chirurgeon",
    ],
)
def test_taxonomy_maps_summon_trigger_board_engine_identities(card_identity):
    classification = classify_card_intent("", card_identity=card_identity)

    assert classification.reason == "summon_trigger_board_engine"
    assert classification.value == "8"


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

    assert raise_dead.reason == "conditional_self_damage_resource"
    assert raise_dead.value == "8"
    assert raise_dead.band == "medium"
    assert "return_dead_friendly_minions" in raise_dead.matched_signals

    assert brain_masseuse.reason == "self_damage_liability_body"
    assert brain_masseuse.value == "6"
    assert brain_masseuse.band == "medium"
    assert "takes_damage_reflects_to_own_hero" in brain_masseuse.matched_signals

    assert felwing.reason == "conditional_cost_reduction"
    assert felwing.value == "8"
    assert felwing.band == "medium"
    assert "opponent_damage_this_turn" in felwing.matched_signals


def test_taxonomy_classifies_shadowpriest_card_identity_when_surface_has_no_card_text():
    assert classify_card_intent(
        "battlecry damage minion pressure", card_identity="GVG_009"
    ).reason == (
        "reciprocal_hero_burn"
    )
    assert classify_card_intent(
        "combo_piece damage pressure spell", card_identity="Acupuncture"
    ).reason == (
        "reciprocal_hero_burn"
    )
    assert classify_card_intent(
        "damage pressure spell", card_identity="SCH_514"
    ).reason == (
        "conditional_self_damage_resource"
    )
    assert classify_card_intent(
        "damage minion pressure", card_identity="Brain Masseuse"
    ).reason == (
        "self_damage_liability_body"
    )
    assert classify_card_intent(
        "damage minion pressure", card_identity="YOD_032"
    ).reason == (
        "conditional_cost_reduction"
    )
    assert classify_card_intent(
        "aura hero_power minion pressure", card_identity="TOY_381"
    ).reason == (
        "hero_power_cost_aura"
    )
    assert classify_card_intent(
        "combo_piece damage pressure spell", card_identity="DS1_233"
    ).reason == (
        "direct_enemy_hero_burn"
    )
    assert classify_card_intent(
        "damage pressure spell", card_identity="NX2_019"
    ).reason == (
        "conditional_target_kill_burn"
    )


def test_id_only_conditional_semantics_report_current_matched_signals():
    raise_dead = classify_card_intent("", card_identity="SCH_514")
    felwing = classify_card_intent("", card_identity="YOD_032")

    assert raise_dead.matched_signals == ("raise_dead",)
    assert felwing.matched_signals == ("frenzied_felwing",)


def test_taxonomy_rejects_substring_card_identities_without_card_text():
    for card_identity in ("Mind Blaster", "Raise Deadly"):
        classification = classify_card_intent(
            "unrelated pressure claim", card_identity=card_identity
        )

        assert classification.reason == "semantic_default"
        assert classification.value == "6"
        assert classification.band == "default"


def test_damage_aura_still_wins_before_reciprocal_hero_burn():
    classification = classify_card_intent(
        "Voidtouched Attendant makes both heroes take extra damage from all sources."
    )

    assert classification.reason == "damage_aura_amplifier"
    assert classification.value == "10"
    assert classification.band == "critical"


def test_twilight_deceptor_identity_precedes_broad_enemy_hero_damage_context():
    classification = classify_card_intent(
        (
            "If any hero took damage this turn, Twilight Deceptor draws a Shadow "
            "spell. enemy hero damage"
        ),
        card_identity="SW_444",
    )

    assert classification.reason == "conditional_draw"
    assert classification.value == "8"
    assert classification.band == "medium"
