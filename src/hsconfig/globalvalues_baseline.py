from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from hsconfig.io import file_sha256, read_json


FALLBACK_GLOBALVALUES_BASELINE: dict[str, Any] = {
    "GameCardId": "GlobalValues",
    "ConfigComment": "This is a special card for setup global values",
    "FirstTurnValueWeight": {"values": [{"condition": "*", "value": "0"}]},
    "SecondTurnValueWeight": {"values": [{"condition": "*", "value": "1.0"}]},
    "GlobalDivineShield": {"values": [{"condition": "*", "value": "2.74"}]},
    "GlobalDurability": {"values": [{"condition": "*", "value": "1.22"}]},
    "GlobalStealth": {"values": [{"condition": "*", "value": "1.21"}]},
    "GlobalHeroAttack": {"values": [{"condition": "*", "value": "0.81"}]},
    "GlobalMinionAttack": {"values": [{"condition": "*", "value": "0.81"}]},
    "GlobalWeaponAttack": {"values": [{"condition": "*", "value": "1.14"}]},
    "GlobalTaunt": {"values": [{"condition": "*", "value": "1.02"}]},
    "GlobalOverload": {"values": [{"condition": "*", "value": "1.68"}]},
    "GlobalQuestProgressValue": {"values": [{"condition": "*", "value": "2"}]},
    "GlobalFrozen": {"values": [{"condition": "*", "value": "2.04"}]},
    "GlobalWindfury": {"values": [{"condition": "*", "value": "0.96"}]},
    "GlobalHeroHealth": {"values": [{"condition": "*", "value": "1.14"}]},
    "GlobalMinionHealth": {"values": [{"condition": "*", "value": "1.14"}]},
    "GlobalLocationHealth": {"values": [{"condition": "*", "value": "1.14"}]},
    "GlobalCharge": {"values": [{"condition": "*", "value": "0.65"}]},
    "GlobalMinionIntrinsicValue": {"values": [{"condition": "*", "value": "3.32 + 2"}]},
    "GlobalLocationIntrinsicValue": {"values": [{"condition": "*", "value": "3.32 + 1"}]},
    "OppGlobalDivineShield": {"values": [{"condition": "*", "value": "2.74"}]},
    "OppGlobalDurability": {"values": [{"condition": "*", "value": "1.22"}]},
    "OppGlobalStealth": {"values": [{"condition": "*", "value": "1.21"}]},
    "OppGlobalHeroAttack": {"values": [{"condition": "*", "value": "1.14"}]},
    "OppGlobalMinionAttack": {"values": [{"condition": "*", "value": "1.14"}]},
    "OppGlobalWeaponAttack": {"values": [{"condition": "*", "value": "1.14"}]},
    "OppGlobalTaunt": {"values": [{"condition": "*", "value": "1.02"}]},
    "OppGlobalOverload": {"values": [{"condition": "*", "value": "1.68"}]},
    "OppGlobalQuestProgressValue": {"values": [{"condition": "*", "value": "2"}]},
    "OppGlobalFrozen": {"values": [{"condition": "*", "value": "2.04"}]},
    "OppGlobalWindfury": {"values": [{"condition": "*", "value": "0.96"}]},
    "OppGlobalHeroHealth": {"values": [{"condition": "*", "value": "0.81"}]},
    "OppGlobalMinionHealth": {"values": [{"condition": "*", "value": "0.81"}]},
    "OppGlobalLocationHealth": {"values": [{"condition": "*", "value": "0.81"}]},
    "OppGlobalCharge": {"values": [{"condition": "*", "value": "0.65"}]},
    "OppGlobalMinionIntrinsicValue": {"values": [{"condition": "*", "value": "3.32+6"}]},
    "OppGlobalLocationIntrinsicValue": {"values": [{"condition": "*", "value": "3.32+4"}]},
}


def load_globalvalues_baseline(runtime_root: str | Path | None = None) -> dict[str, Any]:
    runtime_path = _find_runtime_baseline(runtime_root)
    if runtime_path is not None:
        baseline = read_json(runtime_path)
        if not isinstance(baseline, dict):
            raise ValueError(f"Runtime GlobalValues baseline must be an object: {runtime_path}")
        return {
            "baseline": baseline,
            "source": "runtime_default",
            "path": str(runtime_path),
            "sha256": file_sha256(runtime_path),
            "key_count": len(baseline),
            "snapshot_status": "live_runtime",
            "snapshot_date": None,
        }
    fallback = deepcopy(FALLBACK_GLOBALVALUES_BASELINE)
    return {
        "baseline": fallback,
        "source": "bundled_fallback",
        "path": None,
        "sha256": None,
        "key_count": len(fallback),
        "snapshot_status": "known_runtime_snapshot",
        "snapshot_date": "2026-07-25",
    }


def _find_runtime_baseline(runtime_root: str | Path | None) -> Path | None:
    if runtime_root is None:
        return None
    root = Path(runtime_root)
    candidates = (
        root / "CustomConfig" / "default" / "GlobalValues.json",
        root / "CustomConfig" / "Default" / "GlobalValues.json",
    )
    return next((path for path in candidates if path.is_file()), None)
