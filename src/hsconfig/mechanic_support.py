from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from hsconfig.visionai_registry import CARD_BEHAVIOR_BLOCKS


MECHANIC_SUPPORT: dict[str, dict[str, Any]] = {
    "battlecry": {
        "support_level": "direct",
        "normal_path_surfaces": [
            "CARDID.json:BeforeBattlecryTargetBonus",
            "CARDID.json:BeforePlayCardBonus",
            "Combo.json:exact_sequence",
        ],
        "warning_boundary": (
            "Non-targeted battlecry value remains general card timing unless a source-backed target rule exists."
        ),
    },
    "discover": {
        "support_level": "direct",
        "normal_path_surfaces": [
            "CARDID.json:OnDiscoverCardBonus",
            "CARDID.json:BeforePlayCardBonus",
        ],
        "warning_boundary": "Only source-resolved option identity lowers; unresolved options stay suppressed.",
    },
    "choose_one": {
        "support_level": "direct",
        "normal_path_surfaces": [
            "CARDID.json:OnChooseOneCardBonus",
            "CARDID.json:BeforePlayCardBonus",
        ],
        "warning_boundary": "Only source-resolved Choose One option identity lowers; unresolved options stay suppressed.",
    },
    "damage": {
        "support_level": "direct",
        "normal_path_surfaces": [
            "CARDID.json:BeforePlayCardBonus",
            "CARDID.json:BeforeBattlecryTargetBonus",
            "CARDID.json:BeforeUseHeroPowerBonus",
        ],
        "warning_boundary": "Damage timing and targeting lower only through exact documented card or Hero Power surfaces.",
    },
    "draw": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "Mulligan.json:opening_hand"],
        "warning_boundary": "Draw timing can be encouraged; exact hand-state planning remains broader bot evaluation.",
    },
    "heal": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "GlobalValues.json:survivability_posture"],
        "warning_boundary": "Exact heal-threshold planning is not a dedicated normal-path surface.",
    },
    "overload": {
        "support_level": "direct",
        "normal_path_surfaces": [
            "CARDID.json:BeforePlayCardBonus",
            "GlobalValues.json:deck_posture",
        ],
        "warning_boundary": "Exact future-mana planning is heuristic, not a dedicated overload planner.",
    },
    "weapon": {
        "support_level": "direct",
        "normal_path_surfaces": [
            "CARDID.json:BeforePhysicalAttackBonus",
            "CARDID.json:BeforePlayCardBonus",
            "Combo.json:exact_sequence",
        ],
        "warning_boundary": "Exact weapon combos still require explicit sequence evidence.",
    },
    "hero_power": {
        "support_level": "direct",
        "normal_path_surfaces": ["CARDID.json:BeforeUseHeroPowerBonus"],
        "warning_boundary": "Unresolved or random hero-power identity stays warning-only.",
    },
    "hero_power_transform": {
        "support_level": "direct",
        "normal_path_surfaces": [
            "CARDID.json:BeforeUseHeroPowerBonus",
            "GlobalValues.json:deck_posture",
        ],
        "warning_boundary": "Only exact transformed hero-power identity lowers.",
    },
    "spell_damage": {
        "support_level": "partial",
        "normal_path_surfaces": [
            "CARDID.json:BeforePlayCardBonus",
            "GlobalValues.json:deck_posture",
        ],
        "warning_boundary": "Spell-damage synergy can be encouraged; exact hand and spell sequencing remains source-dependent.",
    },
    "start_of_game": {
        "support_level": "partial",
        "normal_path_surfaces": [
            "GlobalValues.json:deck_posture",
            "CARDID.json:resolved_identity",
        ],
        "warning_boundary": "Start-of-game effects are represented through deck posture or exact linked entities, not by executing a runtime action.",
    },
    "discard": {
        "support_level": "direct",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Hidden hand-discard outcomes follow card rules; enabler timing is lowerable.",
    },
    "overkill": {
        "support_level": "direct",
        "normal_path_surfaces": ["CARDID.json:BeforeOverkilledBonus"],
        "warning_boundary": "Overkill lowers when the card has a documented overkill behavior block.",
    },
    "deathrattle": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "CARDID.json:OnBoardBonus"],
        "warning_boundary": "Trigger ordering and resurrection quality are not dedicated normal-path surfaces.",
    },
    "reborn": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "CARDID.json:OnBoardBonus"],
        "warning_boundary": "Respawn value is represented only through deploy or preserve posture.",
    },
    "recruit": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "GlobalValues.json:board_pressure"],
        "warning_boundary": "HSConfig can time the recruiter, not choose the pulled card beyond deck construction.",
    },
    "summon": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "CARDID.json:OnBoardBonus"],
        "warning_boundary": "Generic summon value can be represented only through deploy or board posture.",
    },
    "freeze": {
        "support_level": "partial",
        "normal_path_surfaces": [
            "CARDID.json:BeforePlayCardBonus",
            "CARDID.json:BeforeBattlecryTargetBonus",
            "CARDID.json:BeforeUseHeroPowerBonus",
        ],
        "warning_boundary": "Generic spell-target freeze is not a dedicated normal-path target surface.",
    },
    "lifesteal": {
        "support_level": "partial",
        "normal_path_surfaces": [
            "CARDID.json:BeforePlayCardBonus",
            "CARDID.json:BeforePhysicalAttackBonus",
            "GlobalValues.json:survivability_posture",
        ],
        "warning_boundary": "Exact heal-threshold planning is not a dedicated normal-path surface.",
    },
    "taunt": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:OnBoardBonus", "CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Taunt is mostly defensive board value, not a dedicated taunt planner.",
    },
    "rush": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePhysicalAttackBonus", "CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Attack posture lowers; full trade selection remains broader bot evaluation.",
    },
    "charge": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePhysicalAttackBonus", "CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Attack posture lowers; lethal math remains broader bot evaluation.",
    },
    "location": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Repeated location activation and targeting are not first-class normal-path surfaces.",
    },
    "board_position": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Exact minion placement has no documented normal-path VisionAI positioning surface.",
    },
    "generic_spell_target": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Generic spell target selection is not lowerable unless a documented card-specific target surface exists.",
    },
    "location_activation": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Repeated location activation and target choice have no documented normal-path runtime row.",
    },
    "secret": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "Mulligan.json:opening_hand"],
        "warning_boundary": "Secret ordering and hidden-information trap timing are not separate normal-path surfaces.",
    },
    "secret_timing": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Hidden-information secret timing has no separate normal-path runtime row.",
    },
    "generated_entity": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:resolved_identity", "CARDID.json:OnDiscoverCardBonus"],
        "warning_boundary": "Random generation pools stay warning-only unless exact identity is source-backed.",
    },
    "generated_entity_random_pool": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Random generated-entity pools stay report-only unless exact generated identity is source-backed.",
    },
    "aura": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:OnBoardBonus", "CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Continuous aura math and stacked board effects are not dedicated normal-path surfaces.",
    },
    "divine_shield": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:OnBoardBonus", "CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Divine Shield is represented as board/deploy value, not a dedicated planner.",
    },
    "destroy": {
        "support_level": "partial",
        "normal_path_surfaces": [
            "CARDID.json:BeforeBattlecryTargetBonus",
            "CARDID.json:BeforePhysicalAttackBonus",
            "CARDID.json:BeforePlayCardBonus",
        ],
        "warning_boundary": "Generic targeted destroy spells are only partially lowerable.",
    },
    "silence": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforeBattlecryTargetBonus", "CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Generic silence spell targeting is not a dedicated normal-path surface.",
    },
    "transform": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforeBattlecryTargetBonus", "CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Random transform outcomes and generic spell targets stay warning-only.",
    },
    "dredge": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Dredge option selection has no documented normal-path VisionAI choice surface.",
    },
    "tradeable": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Trade-now decisions have no documented normal-path VisionAI runtime block.",
    },
    "kindred": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Kindred depends on prior card-type sequencing; no documented normal-path VisionAI state surface exists.",
    },
    "tourist": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Tourist is primarily deck-construction identity; it has no separate normal-path runtime action surface.",
    },
    "starship": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Starship build and launch choices have no documented normal-path VisionAI runtime block.",
    },
    "rewind": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Do not lower temporal replay/prior-state effects into card values without exact public VisionAI support.",
        "proof_basis": "text drift visibility only; no documented VisionAI temporal prior-state surface in the normal package",
        "never_autopatch_reason": "Do not lower temporal replay/prior-state effects into card values without exact public VisionAI support.",
    },
    "prepare": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Prepare is a pre-play setup action with no documented normal-path VisionAI runtime block.",
        "proof_basis": "text drift visibility only; no documented VisionAI prepare action surface",
        "never_autopatch_reason": "Do not lower Prepare into card values without exact public VisionAI support.",
    },
    "herald": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Do not infer a generic card-value action from a keyword whose concrete effect is card-specific.",
        "proof_basis": "text drift visibility only; no documented normal-path runtime action surface",
        "never_autopatch_reason": "Do not infer a generic card-value action from a keyword whose concrete effect is card-specific.",
    },
    "shatter": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Do not auto-patch conditional destroy/damage targeting without exact target and board-state semantics.",
        "proof_basis": "text drift visibility only; conditional frozen/minion state must stay review-visible unless exact card behavior is known",
        "never_autopatch_reason": "Do not auto-patch conditional destroy/damage targeting without exact target and board-state semantics.",
    },
    "spellburst": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Spellburst setup can be encouraged through timing; exact one-time trigger state remains broader bot evaluation.",
    },
    "miniaturize": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "CARDID.json:resolved_identity"],
        "warning_boundary": "The original card timing can be encouraged; generated mini-copy sequencing remains source-dependent.",
    },
    "quickdraw": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Quickdraw timing can be encouraged, but drawn-this-turn state is not a dedicated normal-path surface.",
    },
    "honorable_kill": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePhysicalAttackBonus", "CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Honorable Kill can influence attack or play posture; exact lethal-damage equality remains broader bot evaluation.",
    },
    "elusive": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:OnBoardBonus", "GlobalValues.json:survivability_posture"],
        "warning_boundary": "Elusive is represented as board/survivability value, not as a dedicated targeting planner.",
    },
    "poisonous": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePhysicalAttackBonus", "CARDID.json:OnBoardBonus"],
        "warning_boundary": "Poisonous can affect attack posture; exact trade selection remains broader bot evaluation.",
    },
    "imbue": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Imbue upgrade state has no documented normal-path runtime row; keep it report-visible until exact surface support exists.",
    },
    "questline": {
        "support_level": "partial",
        "normal_path_surfaces": ["GlobalValues.json:deck_posture", "CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Questline progress and reward timing can be encouraged, not fully planned as a separate action tree.",
    },
    "highlander": {
        "support_level": "partial",
        "normal_path_surfaces": ["GlobalValues.json:deck_posture", "CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "No-duplicate payoff posture can be represented; deck legality remains deck construction.",
    },
    "outcast": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Exact hand-edge position has no documented normal-path VisionAI surface.",
    },
    "infuse": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "GlobalValues.json:board_pressure"],
        "warning_boundary": "Infuse setup can be encouraged; exact counter state remains broader bot evaluation.",
    },
    "corrupt": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "Combo.json:exact_sequence"],
        "warning_boundary": "Corrupt sequencing can be represented when source-backed; exact hand-state timing remains partial.",
    },
    "finale": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Finale requires exact remaining-mana state, which is not a dedicated normal-path surface.",
    },
    "manathirst": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus"],
        "warning_boundary": "Mana-threshold timing can be encouraged; exact threshold control remains partial.",
    },
    "forge": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Forge is an alternate pre-play action with no documented normal-path runtime block.",
    },
    "excavate": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Excavate treasure-chain identity has no documented normal-path runtime row; keep it report-visible until exact surface support exists.",
    },
    "plague": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "GlobalValues.json:deck_posture"],
        "warning_boundary": "Shuffle-pressure posture can be represented; opponent draw timing remains outside pre-run control.",
    },
    "titan": {
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": "Titan ability choice is option identity and has no documented normal-path runtime row.",
    },
    "colossal": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "CARDID.json:OnBoardBonus"],
        "warning_boundary": "Colossal body timing can be represented; appendage interaction remains broader bot evaluation.",
    },
    "dormant": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "CARDID.json:OnBoardBonus"],
        "warning_boundary": "Dormant payoff timing can be represented; wake-up timing remains partial.",
    },
    "invoke": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "GlobalValues.json:deck_posture"],
        "warning_boundary": "Invoke progression can be encouraged; exact upgrade state remains partial.",
    },
    "jade": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "GlobalValues.json:board_pressure"],
        "warning_boundary": "Jade scaling posture can be represented; exact summoned stat line is not a separate runtime surface.",
    },
    "cthun_package": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "GlobalValues.json:deck_posture"],
        "warning_boundary": "C'Thun package setup can be represented; shard/order state remains broader bot evaluation.",
    },
    "spell_school": {
        "support_level": "partial",
        "normal_path_surfaces": ["CARDID.json:BeforePlayCardBonus", "GlobalValues.json:deck_posture"],
        "warning_boundary": "Spell-school synergy can be encouraged; exact school chain state remains source-dependent.",
    },
}

ROLE_ALIASES = {
    "quest": "questline",
    "sidequest": "questline",
    "no_duplicate": "highlander",
    "no_duplicates": "highlander",
    "cthun": "cthun_package",
    "c'thun": "cthun_package",
    "c’thun": "cthun_package",
    "c_thun": "cthun_package",
    "spell_burst": "spellburst",
    "honorablekill": "honorable_kill",
    "honorable_kill": "honorable_kill",
    "starship_piece": "starship",
    "starship_piece_tag": "starship",
    "starship_launch": "starship",
    "prepare_keyword": "prepare",
    "hero_power_imbue": "imbue",
    "shadow_hero_power": "hero_power_transform",
    "hero_power_pressure": "hero_power",
    "hero_attack": "weapon",
    "weapon_pressure": "weapon",
    "spell_generation": "generated_entity",
    "choose_one_choice": "choose_one",
    "positioning": "board_position",
    "spell_target": "generic_spell_target",
    "location_use": "location_activation",
    "secret_ordering": "secret_timing",
    "random_generation": "generated_entity_random_pool",
    "token_board": "aura",
    "board_buff": "aura",
    "board_scaling": "aura",
    "board_flood": "aura",
    "hand_mutation": "discard",
    "payoff_summon": "generated_entity",
    "magnetic": "aura",
    "treant": "aura",
}

NON_MECHANIC_ROLES = {
    "burn_payoff",
    "combo_piece",
    "deck_card",
    "early_pressure",
    "minion",
    "mulligan_anchor",
    "one_drop",
    "prefer_enemy_hero",
    "pressure",
    "spell",
}

IDENTITY_GATED_DIRECT_MECHANICS = {
    "choose_one",
    "discover",
    "hero_power_transform",
}
VISIBILITY_BUCKETS = ("direct", "identity_gated_direct", "partial", "warning_only")

LOWERING_POLICIES = {"lowerable", "identity_gated", "report_only"}
IDENTITY_GATED_LOWERING_MECHANICS = {
    "choose_one",
    "discover",
    "generated_entity",
    "hero_power_transform",
    "start_of_game",
}
NO_DEFAULT_RUNTIME_BLOCK_MECHANICS = {
    "choose_one",
    "generated_entity",
    "start_of_game",
}
STATIC_CLAIM_DISABLED_MECHANICS = {
    "choose_one",
    "generated_entity",
    "start_of_game",
}
UNKNOWN_MECHANIC_LOWERING_POLICY: dict[str, Any] = {
    "policy": "report_only",
    "static_claim_allowed": False,
    "default_block": None,
    "allowed_blocks": [],
    "default_value": "6",
    "default_condition": "*",
    "default_intent": None,
    "suppression_reason": "unregistered_mechanic_runtime_surface",
}


def normalize_role_token(role: object) -> str:
    return (
        str(role)
        .strip()
        .lower()
        .replace("'", "")
        .replace("’", "")
        .replace(" ", "_")
        .replace("-", "_")
    )


def _canonical_mechanic(mechanic: object) -> str:
    token = normalize_role_token(mechanic)
    return ROLE_ALIASES.get(token, token)


def _copy_lowering_policy(policy: dict[str, Any]) -> dict[str, Any]:
    copied = dict(policy)
    copied["allowed_blocks"] = list(policy.get("allowed_blocks", []))
    return copied


def _card_behavior_blocks_from_surfaces(surfaces: Iterable[str]) -> list[str]:
    blocks: list[str] = []
    for surface in surfaces:
        text = str(surface)
        prefix = "CARDID.json:"
        if not text.startswith(prefix):
            continue
        block = text.removeprefix(prefix)
        if block not in CARD_BEHAVIOR_BLOCKS:
            continue
        if block not in blocks:
            blocks.append(block)
    return blocks


def _report_only_lowering_policy(mechanic: str) -> dict[str, Any]:
    policy = dict(UNKNOWN_MECHANIC_LOWERING_POLICY)
    policy["suppression_reason"] = f"{mechanic}_has_no_documented_runtime_block"
    return policy


def _default_lowering_policy(mechanic: str, spec: dict[str, Any]) -> dict[str, Any]:
    support_level = str(spec.get("support_level", ""))
    if support_level == "warning_only":
        return _report_only_lowering_policy(mechanic)

    allowed_blocks = _card_behavior_blocks_from_surfaces(
        spec.get("normal_path_surfaces", [])
    )
    policy_name = (
        "identity_gated"
        if mechanic in IDENTITY_GATED_LOWERING_MECHANICS or not allowed_blocks
        else "lowerable"
    )
    default_block = (
        None
        if mechanic in NO_DEFAULT_RUNTIME_BLOCK_MECHANICS or not allowed_blocks
        else allowed_blocks[0]
    )
    return {
        "policy": policy_name,
        "static_claim_allowed": mechanic not in STATIC_CLAIM_DISABLED_MECHANICS,
        "default_block": default_block,
        "allowed_blocks": allowed_blocks,
        "default_value": "6",
        "default_condition": "*",
        "default_intent": f"use_{mechanic}_according_to_card_text",
        "suppression_reason": None,
    }


def _validate_lowering_policy(mechanic: str, policy: dict[str, Any]) -> None:
    policy_name = str(policy.get("policy", ""))
    if policy_name not in LOWERING_POLICIES:
        raise ValueError(f"{mechanic}: unsupported lowering policy {policy_name!r}")
    if not isinstance(policy.get("static_claim_allowed"), bool):
        raise ValueError(f"{mechanic}: static_claim_allowed must be bool")

    allowed_blocks = list(policy.get("allowed_blocks", []))
    undocumented_blocks = sorted(set(allowed_blocks) - CARD_BEHAVIOR_BLOCKS)
    if undocumented_blocks:
        raise ValueError(
            f"{mechanic}: unsupported card behavior blocks {undocumented_blocks!r}"
        )

    default_block = policy.get("default_block")
    if default_block is not None and default_block not in allowed_blocks:
        raise ValueError(f"{mechanic}: default_block must be in allowed_blocks")
    if policy_name == "report_only" and (allowed_blocks or default_block is not None):
        raise ValueError(f"{mechanic}: report_only policies cannot emit runtime blocks")
    if policy_name == "report_only" and not policy.get("suppression_reason"):
        raise ValueError(f"{mechanic}: report_only policies need suppression_reason")


def _install_lowering_policies() -> None:
    for mechanic, spec in MECHANIC_SUPPORT.items():
        policy = _default_lowering_policy(mechanic, spec)
        _validate_lowering_policy(mechanic, policy)
        spec["lowering"] = policy


_install_lowering_policies()


def mechanic_lowering_policy(mechanic: str) -> dict[str, Any]:
    canonical = _canonical_mechanic(mechanic)
    spec = MECHANIC_SUPPORT.get(canonical)
    if spec is None:
        return _copy_lowering_policy(UNKNOWN_MECHANIC_LOWERING_POLICY)
    return _copy_lowering_policy(spec["lowering"])


def mechanic_static_claim_allowed(mechanic: str) -> bool:
    return bool(mechanic_lowering_policy(mechanic)["static_claim_allowed"])


def mechanic_allowed_runtime_blocks(mechanic: str) -> set[str]:
    return set(mechanic_lowering_policy(mechanic)["allowed_blocks"])


def mechanic_default_runtime_block(mechanic: str) -> str | None:
    block = mechanic_lowering_policy(mechanic)["default_block"]
    return str(block) if block is not None else None


def mechanic_report_only_reason(mechanic: str) -> str:
    policy = mechanic_lowering_policy(mechanic)
    if policy["policy"] != "report_only":
        return ""
    return str(policy["suppression_reason"])


def mechanics_with_executable_lowering() -> set[str]:
    return {
        mechanic
        for mechanic, spec in MECHANIC_SUPPORT.items()
        if spec["lowering"]["policy"] in {"lowerable", "identity_gated"}
    }


def support_for_roles(roles: Iterable[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for role in roles:
        raw_role = normalize_role_token(role)
        if raw_role in NON_MECHANIC_ROLES:
            continue
        mechanic = ROLE_ALIASES.get(raw_role, raw_role)
        spec = MECHANIC_SUPPORT.get(mechanic)
        if mechanic in seen:
            continue
        seen.add(mechanic)
        if spec is None:
            rows.append(
                {
                    "mechanic": mechanic,
                    "support_level": "warning_only",
                    "normal_path_surfaces": ["report-only"],
                    "warning_boundary": (
                        "No registered VisionAI normal-path surface exists for role "
                        f"'{mechanic}'; keep it visible as warning-only until mapped."
                    ),
                    "lowering": mechanic_lowering_policy(mechanic),
                    "registered": False,
                }
            )
            continue
        rows.append({"mechanic": mechanic, **spec})
    return sorted(rows, key=lambda row: row["mechanic"])


def operator_visibility_bucket(support: dict[str, Any]) -> str:
    mechanic = str(support.get("mechanic", ""))
    support_level = str(support.get("support_level", ""))
    if support_level == "direct" and mechanic in IDENTITY_GATED_DIRECT_MECHANICS:
        return "identity_gated_direct"
    if support_level in {"direct", "partial", "warning_only"}:
        return support_level
    return "warning_only"


def summarize_mechanic_support(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    level_counts: Counter[str] = Counter()
    warning_mechanics: set[str] = set()
    warning_cards: set[str] = set()
    for row in rows:
        card_id = str(row.get("card_id", ""))
        for support in row.get("mechanic_support", []):
            if not isinstance(support, dict):
                continue
            level = str(support.get("support_level", ""))
            mechanic = str(support.get("mechanic", ""))
            if not level:
                continue
            level_counts[level] += 1
            if level == "warning_only":
                warning_mechanics.add(mechanic)
                if card_id:
                    warning_cards.add(card_id)
    return {
        "support_level_counts": {
            "direct": level_counts["direct"],
            "partial": level_counts["partial"],
            "warning_only": level_counts["warning_only"],
        },
        "warning_only_mechanics": sorted(warning_mechanics),
        "warning_only_card_count": len(warning_cards),
    }


def summarize_mechanic_visibility(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    bucket_counts: Counter[str] = Counter()
    mechanics_by_bucket: dict[str, set[str]] = {bucket: set() for bucket in VISIBILITY_BUCKETS}
    warning_cards: set[str] = set()
    first_warning_boundary: dict[str, str] | None = None
    warning_boundaries_by_mechanic: dict[str, str] = {}

    for row in rows:
        card_id = str(row.get("card_id", ""))
        for support in row.get("mechanic_support", []):
            if not isinstance(support, dict):
                continue
            mechanic = str(support.get("mechanic", ""))
            bucket = operator_visibility_bucket(support)
            bucket_counts[bucket] += 1
            if mechanic:
                mechanics_by_bucket.setdefault(bucket, set()).add(mechanic)
            if bucket == "warning_only":
                if card_id:
                    warning_cards.add(card_id)
                if first_warning_boundary is None:
                    first_warning_boundary = {
                        "mechanic": mechanic,
                        "warning_boundary": str(support.get("warning_boundary", "")),
                    }
                if mechanic and mechanic not in warning_boundaries_by_mechanic:
                    warning_boundaries_by_mechanic[mechanic] = str(
                        support.get("warning_boundary", "")
                    )

    return {
        "non_blocking": True,
        "bucket_counts": {bucket: bucket_counts[bucket] for bucket in VISIBILITY_BUCKETS},
        "mechanics_by_bucket": {
            bucket: sorted(mechanics_by_bucket.get(bucket, set()))
            for bucket in VISIBILITY_BUCKETS
        },
        "warning_only_card_count": len(warning_cards),
        "first_warning_boundary": first_warning_boundary,
        "warning_boundaries": [
            {
                "mechanic": mechanic,
                "warning_boundary": warning_boundaries_by_mechanic[mechanic],
            }
            for mechanic in sorted(warning_boundaries_by_mechanic)
        ],
    }
