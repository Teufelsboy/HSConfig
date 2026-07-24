from __future__ import annotations

import re
from pathlib import Path
from typing import Any


PUBLIC_DOC_CONFIRMED_CARD_BEHAVIOR_BLOCKS = frozenset(
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
        "InHandPlayPriority",
    }
)

REPO_SUPPORTED_SOURCE_GAP_CARD_BEHAVIOR_BLOCKS = frozenset(
    {
        "OnAdaptCardBonus",
        "BeforeUpgradeCardBonus",
        "OnBoardPlayPriority",
    }
)

CARD_BEHAVIOR_BLOCKS = (
    PUBLIC_DOC_CONFIRMED_CARD_BEHAVIOR_BLOCKS
    | REPO_SUPPORTED_SOURCE_GAP_CARD_BEHAVIOR_BLOCKS
)


def _card_behavior_registry_row(block: str) -> dict[str, Any]:
    if block in REPO_SUPPORTED_SOURCE_GAP_CARD_BEHAVIOR_BLOCKS:
        return {
            "support": "supported",
            "normal_path_runtime": True,
            "surface_family": "card_behavior",
            "source_backing": "repo_supported_source_gap",
            "source_note": (
                "Repo-supported block; not confirmed in the latest public-doc audit."
            ),
        }
    return {
        "support": "supported",
        "normal_path_runtime": True,
        "surface_family": "card_behavior",
        "source_backing": "public_doc_confirmed",
        "source_note": (
            "Confirmed by HearthRanger VisionAI public docs or prior HSConfig surface audit."
        ),
    }


CARD_BEHAVIOR_BLOCK_REGISTRY: dict[str, dict[str, Any]] = {
    block: _card_behavior_registry_row(block) for block in CARD_BEHAVIOR_BLOCKS
}

CARD_BEHAVIOR_BLOCK_REGISTRY.update(
    {
        "Presume.json": {
            "support": "known_non_normal_surface",
            "normal_path_runtime": False,
            "surface_family": "legacy_gated",
            "source_backing": "legacy_gated",
            "source_note": "Known surface, intentionally outside the normal HSConfig path.",
        },
        "Concede.json": {
            "support": "known_non_normal_surface",
            "normal_path_runtime": False,
            "surface_family": "legacy_gated",
            "source_backing": "legacy_gated",
            "source_note": "Known surface, intentionally outside the normal HSConfig path.",
        },
    }
)

NORMAL_PATH_FORBIDDEN_SURFACES = frozenset(
    {
        "Presume.json",
        "Concede.json",
        "CardBehavior.json",
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
        "source_backing": "unsupported",
        "source_note": "No HSConfig runtime support.",
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
