from __future__ import annotations

import re
from pathlib import Path


CARD_BEHAVIOR_BLOCKS = frozenset(
    {
        "InHandBonus",
        "OnBoardBonus",
        "BeforePlayCardBonus",
        "BeforeBattlecryTargetBonus",
        "BeforeUseHeroPowerBonus",
        "BeforePhysicalAttackBonus",
        "BeforeEndTurnBonus",
        "BeforeOverkilledBonus",
        "OnDiscoverCardBonus",
        "OnChooseOneCardBonus",
        "OnAdaptCardBonus",
        "BeforeUpgradeCardBonus",
        "InHandPlayPriority",
        "OnBoardPlayPriority",
    }
)

SPECIAL_SURFACES = {
    "GlobalValues.json": "GlobalValues",
    "Mulligan.json": "Mulligan",
    "Combo.json": "Combo",
    "Presume.json": "Presume",
    "Concede.json": "Concede",
}

CARD_ID_SURFACE_RE = re.compile(r"^(?:(?=.*\d)|(?=.*_)(?=.*[A-Z]))[A-Za-z0-9_]+\.json$")

RESERVED_NON_RUNTIME_SURFACES = frozenset(
    {
        "CardBehavior.json",
        "card_role_map.json",
        "config_row_provenance.json",
        "operator_review.json",
        "package_validation.json",
        "validation_report.json",
    }
)


def supported_surface(filename: str | Path) -> bool:
    name = Path(filename).name
    if name in SPECIAL_SURFACES:
        return True
    if name in RESERVED_NON_RUNTIME_SURFACES:
        return False
    if not name.endswith(".json"):
        return False
    return bool(CARD_ID_SURFACE_RE.fullmatch(name)) and bool(name[:-5])


def expected_game_card_id(filename: str | Path) -> str | None:
    name = Path(filename).name
    if name in SPECIAL_SURFACES:
        return SPECIAL_SURFACES[name]
    if supported_surface(name):
        return name[:-5]
    return None


def is_special_surface(filename: str | Path) -> bool:
    return Path(filename).name in SPECIAL_SURFACES
