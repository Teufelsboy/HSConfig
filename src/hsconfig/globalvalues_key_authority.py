from __future__ import annotations


STEP1_POSTURE_KEYS = {
    "FirstTurnValueWeight": "turn_weight",
    "SecondTurnValueWeight": "turn_weight",
    "MyHeroPowerValue": "hero_power",
    "GlobalMinionAttack": "board_pressure",
    "GlobalMinionIntrinsicValue": "board_pressure",
    "MyWeaponValue": "weapon_pressure",
}

RUNTIME_EVIDENCE_KEYS = {
    "LowHpBoardValuePenalty": "runtime_safety",
    "OpponentSpecificMatchupTuning": "matchup_runtime",
    "PostApplyRegressionTuning": "post_apply_validation",
}


def authority_for_key(key: str) -> dict[str, str]:
    if key in STEP1_POSTURE_KEYS:
        return {
            "key": key,
            "category": "step1_posture_overlay_allowed",
            "board_value_component": STEP1_POSTURE_KEYS[key],
        }
    if key in RUNTIME_EVIDENCE_KEYS:
        return {
            "key": key,
            "category": "runtime_evidence_required",
            "board_value_component": RUNTIME_EVIDENCE_KEYS[key],
        }
    return {"key": key, "category": "copy_baseline", "board_value_component": "baseline"}
