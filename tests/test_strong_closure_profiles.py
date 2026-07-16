from hsconfig.strong_closure_profiles import (
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
