from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class ClosureProfileRequirement:
    profile_name: str
    required_any_claim_groups: tuple[tuple[str, ...], ...]
    required_surfaces: tuple[str, ...]


@dataclass(frozen=True)
class ClosureProfileVerdict:
    profile_name: str
    closed: bool
    strong_eligible: bool
    first_missing_link: str
    missing_claim_groups: tuple[str, ...]
    missing_surfaces: tuple[str, ...]
    apply_blocking: bool = False


PROFILE_REQUIREMENTS: dict[str, ClosureProfileRequirement] = {
    "aggro_burn_hero_power": ClosureProfileRequirement(
        profile_name="aggro_burn_hero_power",
        required_any_claim_groups=(
            ("gameplan_posture",),
            ("mulligan_keep", "mulligan_discard"),
            ("targeting_rule", "hero_power_transform", "card_role"),
        ),
        required_surfaces=("GlobalValues.json", "Mulligan.json"),
    ),
    "weapon_pressure": ClosureProfileRequirement(
        profile_name="weapon_pressure",
        required_any_claim_groups=(
            ("gameplan_posture",),
            ("mulligan_keep", "mulligan_discard", "card_role"),
            ("targeting_rule", "mechanic_usage", "card_role"),
        ),
        required_surfaces=("GlobalValues.json", "Mulligan.json"),
    ),
    "combo_setup": ClosureProfileRequirement(
        profile_name="combo_setup",
        required_any_claim_groups=(
            ("gameplan_posture",),
            ("combo_sequence", "card_role"),
            ("mulligan_keep", "mulligan_discard", "card_role"),
        ),
        required_surfaces=("GlobalValues.json", "Mulligan.json"),
    ),
    "board_flood_recruit": ClosureProfileRequirement(
        profile_name="board_flood_recruit",
        required_any_claim_groups=(
            ("gameplan_posture",),
            ("mulligan_keep", "mulligan_discard", "card_role"),
            ("mechanic_usage", "card_role"),
        ),
        required_surfaces=("GlobalValues.json", "Mulligan.json"),
    ),
    "cheat_recruit_big": ClosureProfileRequirement(
        profile_name="cheat_recruit_big",
        required_any_claim_groups=(
            ("gameplan_posture",),
            ("mulligan_keep", "mulligan_discard", "card_role"),
            ("mechanic_usage", "combo_sequence", "card_role"),
        ),
        required_surfaces=("GlobalValues.json", "Mulligan.json"),
    ),
    "discard_pressure": ClosureProfileRequirement(
        profile_name="discard_pressure",
        required_any_claim_groups=(
            ("gameplan_posture",),
            ("mulligan_keep", "mulligan_discard", "card_role"),
            ("mechanic_usage", "known_bad_pattern", "card_role"),
        ),
        required_surfaces=("GlobalValues.json", "Mulligan.json"),
    ),
    "hero_power_imbue": ClosureProfileRequirement(
        profile_name="hero_power_imbue",
        required_any_claim_groups=(
            ("gameplan_posture",),
            ("mulligan_keep", "mulligan_discard", "card_role"),
            ("hero_power_transform", "mechanic_usage", "card_role"),
        ),
        required_surfaces=("GlobalValues.json", "Mulligan.json"),
    ),
    "generic_no_block": ClosureProfileRequirement(
        profile_name="generic_no_block",
        required_any_claim_groups=(("gameplan_posture", "card_role", "mechanic_usage"),),
        required_surfaces=("GlobalValues.json", "Mulligan.json"),
    ),
}


def profile_for_archetype(archetype_bucket: str, mechanics: Iterable[str]) -> str:
    bucket = archetype_bucket.lower()
    mechanic_set = {mechanic.lower() for mechanic in mechanics}

    if "imbue" in bucket or "imbue" in mechanic_set:
        return "hero_power_imbue"
    if "discard" in bucket or "discard" in mechanic_set:
        return "discard_pressure"
    if (
        "big" in bucket
        or "cheat" in bucket
        or "big_minion" in mechanic_set
        or "cheat" in mechanic_set
        or "summon_from_deck" in mechanic_set
    ):
        return "cheat_recruit_big"
    if "hero_power" in bucket or "shadow_hero_power" in mechanic_set:
        return "aggro_burn_hero_power"
    if "weapon" in bucket or "weapon" in mechanic_set or "hero_attack" in mechanic_set:
        return "weapon_pressure"
    if "combo" in bucket or "combo" in mechanic_set:
        return "combo_setup"
    if (
        "recruit" in bucket
        or "mech_board_scaling" in bucket
        or "board_scaling" in bucket
        or "board_flood" in mechanic_set
        or "token_board" in mechanic_set
        or "mech" in mechanic_set
        or "magnetic" in mechanic_set
        or "board_scaling" in mechanic_set
    ):
        return "board_flood_recruit"
    if "aggro" in bucket or "burn" in mechanic_set or "pirate" in mechanic_set:
        return "aggro_burn_hero_power"
    return "generic_no_block"


def evaluate_closure_profile(
    *,
    archetype_bucket: str,
    primary_mechanics: Iterable[str],
    source_claim_kinds: Iterable[str],
    emitted_surfaces: Iterable[str],
    default_only_surfaces: Iterable[str],
    suppressed_claim_kinds: Iterable[str],
) -> ClosureProfileVerdict:
    profile_name = profile_for_archetype(archetype_bucket, primary_mechanics)
    requirement = PROFILE_REQUIREMENTS[profile_name]
    claims = {claim.lower() for claim in source_claim_kinds}
    emitted = set(emitted_surfaces)
    default_only = set(default_only_surfaces)
    suppressed = {claim.lower() for claim in suppressed_claim_kinds}

    if default_only:
        first = sorted(default_only)[0]
        return ClosureProfileVerdict(
            profile_name=profile_name,
            closed=False,
            strong_eligible=False,
            first_missing_link=f"default_only_surface:{first}",
            missing_claim_groups=(),
            missing_surfaces=(),
        )

    missing_groups: list[str] = []
    for group in requirement.required_any_claim_groups:
        if not any(claim in claims and claim not in suppressed for claim in group):
            missing_groups.append("|".join(group))

    missing_surfaces = tuple(
        surface for surface in requirement.required_surfaces if surface not in emitted
    )
    closed = not missing_groups and not missing_surfaces
    if closed:
        first_missing = "none"
    elif missing_groups:
        first_missing = f"missing_claim_group:{missing_groups[0]}"
    else:
        first_missing = f"missing_surface:{missing_surfaces[0]}"

    return ClosureProfileVerdict(
        profile_name=profile_name,
        closed=closed,
        strong_eligible=closed,
        first_missing_link=first_missing,
        missing_claim_groups=tuple(missing_groups),
        missing_surfaces=missing_surfaces,
    )
