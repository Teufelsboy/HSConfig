from hsconfig.role_tokens import (
    card_role_tokens,
    claim_role_tokens,
    has_start_of_game_non_hand_effect,
    role_tokens,
)


def test_role_tokens_normalizes_strings_iterables_and_ignores_empty_values():
    assert role_tokens(" Start_Of_Game ") == {"start_of_game"}
    assert role_tokens([" Pressure ", "", None, "Hero_Power_Transform"]) == {
        "pressure",
        "hero_power_transform",
    }
    assert role_tokens(("Highlander_Modifier", "Deck_Size_Modifier")) == {
        "highlander_modifier",
        "deck_size_modifier",
    }
    assert role_tokens({"Even_Odd_Modifier", "start_of_game"}) == {
        "even_odd_modifier",
        "start_of_game",
    }
    assert role_tokens({"nested": "ignored"}) == set()


def test_claim_role_tokens_merges_standard_role_family_keys():
    claim = {
        "roles": "start_of_game",
        "semantic_families": ("hero_power_transform",),
        "mechanic_families": {"shadowform"},
    }

    assert claim_role_tokens(claim) == {
        "start_of_game",
        "hero_power_transform",
        "shadowform",
    }


def test_card_role_tokens_merges_card_and_claim_context():
    card_role = {"roles": ["start_of_game"], "semantic_families": ["hero_power_transform"]}
    claim = {"mechanic_families": ["shadowform"]}

    assert card_role_tokens(card_role, claim) == {
        "start_of_game",
        "hero_power_transform",
        "shadowform",
    }


def test_has_start_of_game_non_hand_effect_requires_start_and_non_hand_family():
    assert has_start_of_game_non_hand_effect(["start_of_game", "hero_power_transform"]) is True
    assert has_start_of_game_non_hand_effect(["start_of_game", "mulligan_anchor"]) is False
    assert has_start_of_game_non_hand_effect(["hero_power_transform"]) is False
