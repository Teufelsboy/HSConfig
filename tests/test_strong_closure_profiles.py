from hsconfig.strong_closure_profiles import (
    PROFILE_REQUIREMENTS,
    evaluate_closure_profile,
    profile_for_archetype,
)


def test_shadowpriest_uses_aggro_hero_power_profile():
    assert (
        profile_for_archetype(
            "aggro_burn_hero_power_transform",
            ["aggro", "burn", "shadow_hero_power"],
        )
        == "aggro_burn_hero_power"
    )


def test_weapon_deck_uses_weapon_pressure_profile():
    assert (
        profile_for_archetype(
            "weapon_sequence_pressure",
            ["weapon", "pirate", "attack_sequence"],
        )
        == "weapon_pressure"
    )


def test_mech_board_scaling_uses_board_flood_profile_even_with_targeting():
    assert (
        profile_for_archetype(
            "mech_board_scaling",
            ["mech", "magnetic", "board_scaling", "burn"],
        )
        == "board_flood_recruit"
    )


def test_profile_routing_prefers_precise_wild_archetype_profiles():
    assert (
        profile_for_archetype(
            "big_recruit_deathrattle_cheat",
            ["big_minion", "recruit", "deathrattle", "cheat"],
        )
        == "cheat_recruit_big"
    )
    assert (
        profile_for_archetype(
            "discard_combo_pressure",
            ["discard", "combo", "payoff_summon"],
        )
        == "discard_pressure"
    )
    assert (
        profile_for_archetype(
            "hero_power_spell_generation",
            ["hero_power", "imbue", "spell_generation"],
        )
        == "hero_power_imbue"
    )
    assert (
        profile_for_archetype(
            "recruit_board_flood",
            ["recruit", "board_flood", "aura_pressure"],
        )
        == "board_flood_recruit"
    )


def test_specific_wild_profiles_declare_expected_claim_groups_and_surfaces():
    expected_profiles = {
        "cheat_recruit_big": (
            (
                ("gameplan_posture",),
                ("mulligan_keep", "mulligan_discard", "card_role"),
                ("mechanic_usage", "combo_sequence", "card_role"),
            ),
            ("GlobalValues.json", "Mulligan.json"),
        ),
        "discard_pressure": (
            (
                ("gameplan_posture",),
                ("mulligan_keep", "mulligan_discard", "card_role"),
                ("mechanic_usage", "known_bad_pattern", "card_role"),
            ),
            ("GlobalValues.json", "Mulligan.json"),
        ),
        "hero_power_imbue": (
            (
                ("gameplan_posture",),
                ("mulligan_keep", "mulligan_discard", "card_role"),
                ("hero_power_transform", "mechanic_usage", "card_role"),
            ),
            ("GlobalValues.json", "Mulligan.json"),
        ),
    }

    for profile_name, (claim_groups, surfaces) in expected_profiles.items():
        requirement = PROFILE_REQUIREMENTS[profile_name]

        assert requirement.profile_name == profile_name
        assert requirement.required_any_claim_groups == claim_groups
        assert requirement.required_surfaces == surfaces


def test_unknown_deck_uses_generic_profile_without_blocking():
    assert profile_for_archetype("unknown_homebrew", ["future_mechanic"]) == "generic_no_block"


def test_aggro_burn_profile_closes_with_mulligan_posture_and_targeting():
    verdict = evaluate_closure_profile(
        archetype_bucket="aggro_burn_hero_power_transform",
        primary_mechanics=["aggro", "burn", "shadow_hero_power"],
        source_claim_kinds=[
            "gameplan_posture",
            "mulligan_keep",
            "mulligan_discard",
            "targeting_rule",
            "hero_power_transform",
        ],
        emitted_surfaces=["GlobalValues.json", "Mulligan.json", "SW_448.json"],
        default_only_surfaces=[],
        suppressed_claim_kinds=[],
    )

    assert verdict.profile_name == "aggro_burn_hero_power"
    assert verdict.closed is True
    assert verdict.first_missing_link == "none"
    assert verdict.strong_eligible is True


def test_default_only_surface_blocks_profile_strong_but_not_load_safe():
    verdict = evaluate_closure_profile(
        archetype_bucket="aggro_burn_hero_power_transform",
        primary_mechanics=["aggro", "burn", "shadow_hero_power"],
        source_claim_kinds=[
            "gameplan_posture",
            "mulligan_keep",
            "targeting_rule",
            "hero_power_transform",
        ],
        emitted_surfaces=["GlobalValues.json", "Mulligan.json"],
        default_only_surfaces=["Mulligan.json"],
        suppressed_claim_kinds=[],
    )

    assert verdict.closed is False
    assert verdict.strong_eligible is False
    assert verdict.first_missing_link == "default_only_surface:Mulligan.json"
    assert verdict.apply_blocking is False
