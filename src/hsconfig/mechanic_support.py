from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


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
}

ROLE_ALIASES = {
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


def support_for_roles(roles: Iterable[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for role in roles:
        raw_role = str(role).lower()
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

    return {
        "non_blocking": True,
        "bucket_counts": {bucket: bucket_counts[bucket] for bucket in VISIBILITY_BUCKETS},
        "mechanics_by_bucket": {
            bucket: sorted(mechanics_by_bucket.get(bucket, set()))
            for bucket in VISIBILITY_BUCKETS
        },
        "warning_only_card_count": len(warning_cards),
        "first_warning_boundary": first_warning_boundary,
    }
