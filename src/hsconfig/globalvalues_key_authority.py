from __future__ import annotations

from hsconfig.package_domain import deep_freeze_definition

from hsconfig.visionai_registry import GLOBALVALUES_KEY_REGISTRY


_BOARD_VALUE_COMPONENT_BY_KEY = {
    "FirstTurnValueWeight": "turn_weight",
    "SecondTurnValueWeight": "turn_weight",
    "MyHeroPowerValue": "hero_power",
    "GlobalMinionAttack": "board_pressure",
    "GlobalMinionIntrinsicValue": "board_pressure",
    "MyWeaponValue": "weapon_pressure",
    "LowHpBoardValuePenalty": "runtime_safety",
    "OpponentSpecificMatchupTuning": "matchup_runtime",
    "PostApplyRegressionTuning": "post_apply_validation",
}
_BOARD_VALUE_COMPONENT_BY_KEY = deep_freeze_definition(
    _BOARD_VALUE_COMPONENT_BY_KEY
)

STEP1_POSTURE_KEYS = {
    key: _BOARD_VALUE_COMPONENT_BY_KEY[key]
    for key, spec in GLOBALVALUES_KEY_REGISTRY.items()
    if spec.key_class == "step1_posture_overlay_allowed"
}

RUNTIME_EVIDENCE_KEYS = {
    key: _BOARD_VALUE_COMPONENT_BY_KEY[key]
    for key, spec in GLOBALVALUES_KEY_REGISTRY.items()
    if spec.key_class == "runtime_evidence_required"
}
STEP1_POSTURE_KEYS = deep_freeze_definition(STEP1_POSTURE_KEYS)
RUNTIME_EVIDENCE_KEYS = deep_freeze_definition(RUNTIME_EVIDENCE_KEYS)


def authority_for_key(key: str) -> dict[str, str]:
    spec = GLOBALVALUES_KEY_REGISTRY.get(key)
    category = spec.key_class if spec is not None else "copy_baseline"
    return {
        "key": key,
        "category": category,
        "board_value_component": _BOARD_VALUE_COMPONENT_BY_KEY.get(
            key, "baseline"
        ),
    }
