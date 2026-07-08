from __future__ import annotations

import re
from pathlib import Path
from typing import Any


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

CARD_BEHAVIOR_BLOCK_REGISTRY: dict[str, dict[str, Any]] = {
    block: {
        "support": "supported",
        "normal_path_runtime": True,
        "surface_family": "card_behavior",
    }
    for block in CARD_BEHAVIOR_BLOCKS
}

CARD_BEHAVIOR_BLOCK_REGISTRY.update(
    {
        "Presume.json": {
            "support": "known_non_normal_surface",
            "normal_path_runtime": False,
            "surface_family": "legacy_gated",
        },
        "Concede.json": {
            "support": "known_non_normal_surface",
            "normal_path_runtime": False,
            "surface_family": "legacy_gated",
        },
    }
)

SPECIAL_SURFACES = {
    "GlobalValues.json": "GlobalValues",
    "Mulligan.json": "Mulligan",
    "Combo.json": "Combo",
    "Presume.json": "Presume",
    "Concede.json": "Concede",
}

CARD_ID_SURFACE_RE = re.compile(r"^(?=.*\d)[A-Za-z0-9_]+\.json$")

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


def runtime_block_support(block_name: str) -> dict[str, Any]:
    if block_name in CARD_BEHAVIOR_BLOCK_REGISTRY:
        return dict(CARD_BEHAVIOR_BLOCK_REGISTRY[block_name])
    return {
        "support": "unsupported",
        "normal_path_runtime": False,
        "surface_family": "unknown",
    }


def is_supported_card_behavior_block(block_name: str) -> bool:
    row = runtime_block_support(block_name)
    return row["support"] == "supported" and row["normal_path_runtime"] is True


def expected_game_card_id(filename: str | Path) -> str | None:
    name = Path(filename).name
    if name in SPECIAL_SURFACES:
        return SPECIAL_SURFACES[name]
    if supported_surface(name):
        return name[:-5]
    return None


def is_special_surface(filename: str | Path) -> bool:
    return Path(filename).name in SPECIAL_SURFACES
