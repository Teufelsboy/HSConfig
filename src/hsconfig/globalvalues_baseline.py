from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from hsconfig.io import file_sha256, read_json


FALLBACK_GLOBALVALUES_BASELINE: dict[str, Any] = {
    "GameCardId": "GlobalValues",
    "ConfigComment": "Bundled fallback GlobalValues baseline; prefer runtime default.",
    "FirstTurnValueWeight": {"values": [{"condition": "*", "value": "0"}]},
    "SecondTurnValueWeight": {"values": [{"condition": "*", "value": "1"}]},
    "GlobalDivineShield": {"values": [{"condition": "*", "value": "2.74"}]},
    "GlobalTaunt": {"values": [{"condition": "*", "value": "1.25"}]},
    "GlobalWindfury": {"values": [{"condition": "*", "value": "2.50"}]},
    "GlobalRush": {"values": [{"condition": "*", "value": "1.85"}]},
    "GlobalCharge": {"values": [{"condition": "*", "value": "3.25"}]},
    "GlobalLifesteal": {"values": [{"condition": "*", "value": "1.70"}]},
    "MyHeroPowerValue": {"values": [{"condition": "*", "value": "1.00"}]},
    "EnemyHeroPowerValue": {"values": [{"condition": "*", "value": "1.00"}]},
    "MyWeaponValue": {"values": [{"condition": "*", "value": "1.00"}]},
    "EnemyWeaponValue": {"values": [{"condition": "*", "value": "1.00"}]},
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
        }
    fallback = deepcopy(FALLBACK_GLOBALVALUES_BASELINE)
    return {
        "baseline": fallback,
        "source": "bundled_fallback",
        "path": None,
        "sha256": None,
        "key_count": len(fallback),
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
