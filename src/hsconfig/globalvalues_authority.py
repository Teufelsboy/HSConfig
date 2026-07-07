from __future__ import annotations

from typing import Any

from hsconfig.globalvalues_key_authority import RUNTIME_EVIDENCE_KEYS, authority_for_key


POSTURE_OVERLAYS = {
    "aggro": {
        "FirstTurnValueWeight": ("set", "0.75", "aggressive_source_backed_posture"),
        "SecondTurnValueWeight": ("set", "0.25", "aggressive_source_backed_posture"),
        "GlobalMinionAttack": ("increase", None, "aggressive_source_backed_posture"),
        "GlobalMinionIntrinsicValue": ("increase", None, "aggressive_source_backed_posture"),
        "MyHeroPowerValue": ("increase", None, "aggressive_source_backed_posture"),
    },
    "aggro_burn": {
        "FirstTurnValueWeight": ("set", "0.75", "aggro_burn_prioritizes_early_damage"),
        "SecondTurnValueWeight": ("set", "0.25", "aggro_burn_prioritizes_early_damage"),
        "GlobalMinionAttack": ("increase", None, "aggro_burn_prioritizes_damage"),
        "GlobalMinionIntrinsicValue": ("increase", None, "aggro_burn_prioritizes_board_pressure"),
        "MyHeroPowerValue": ("increase", None, "aggro_burn_prioritizes_hero_power_damage"),
    },
    "token_board": {
        "GlobalMinionAttack": ("increase", None, "token_board_prioritizes_minion_damage"),
        "GlobalMinionIntrinsicValue": ("increase", None, "token_board_prioritizes_board_presence"),
    },
    "weapon_pressure": {
        "FirstTurnValueWeight": ("set", "0.70", "weapon_pressure_still_values_early_turns"),
        "MyWeaponValue": ("increase", None, "weapon_pressure_prioritizes_weapon_damage"),
    },
    "hero_power_pressure": {
        "MyHeroPowerValue": ("increase", None, "hero_power_pressure_prioritizes_hero_power"),
    },
    "combo_setup": {
        "SecondTurnValueWeight": ("set", "0.35", "combo_setup_values_followup_turns"),
    },
    "deathrattle_recruit": {
        "GlobalMinionIntrinsicValue": ("increase", None, "deathrattle_recruit_values_minion_bodies"),
        "SecondTurnValueWeight": ("set", "0.35", "deathrattle_recruit_values_followup_turns"),
    },
    "control_value": {
        "SecondTurnValueWeight": ("set", "0.40", "control_value_weights_followup_lines"),
    },
}
POSTURE_ALIASES = {
    "aggressive": "aggro",
    "tempo": "aggro",
}


def build_globalvalues_authority_matrix(
    *,
    aggression_profile: str,
    claims: list[dict[str, Any]],
) -> dict[str, Any]:
    claim_refs = _claim_refs(claims)
    posture = _resolve_posture(aggression_profile, claims)
    overlays = POSTURE_OVERLAYS.get(posture or "", {})
    if overlays:
        allowed = [
            _allowed_row(
                key=key,
                operation=operation,
                value=value,
                reason=reason,
                claim_refs=claim_refs,
            )
            for key, (operation, value, reason) in overlays.items()
        ]
    else:
        allowed = [
            {
                "key": "baseline",
                "overlay": "none",
                "operation": "none",
                "value": None,
                "authority": "baseline_default",
                "key_authority": authority_for_key("baseline"),
                "claim_refs": [],
                "reason": "no_source_backed_posture_overlay",
            }
        ]

    blocked = [
        {
            "key": key,
            "authority": "runtime_evidence_required",
            "key_authority": authority_for_key(key),
            "claim_refs": claim_refs,
            "reason": "requires_runtime_evidence",
            "blocked_reason": "requires_runtime_evidence",
        }
        for key in sorted(RUNTIME_EVIDENCE_KEYS)
    ]
    for claim in claims:
        if str(claim.get("claim_kind", claim.get("claim_type", ""))) == "globalvalue_numeric_tuning":
            blocked.append(
                {
                    "key": str(claim.get("key", "runtime_numeric_tuning")),
                    "authority": "runtime_evidence_required",
                    "key_authority": authority_for_key(
                        str(claim.get("key", "runtime_numeric_tuning"))
                    ),
                    "claim_refs": _claim_refs([claim]),
                    "reason": "requires_runtime_evidence",
                    "blocked_reason": "requires_runtime_evidence",
                }
            )
    return {
        "aggression_profile": aggression_profile,
        "posture": posture or "baseline",
        "allowed_step1_overlays": allowed,
        "blocked_until_runtime_evidence": blocked,
    }


def _allowed_row(
    *,
    key: str,
    operation: str,
    value: str | None,
    reason: str,
    claim_refs: list[str],
) -> dict[str, Any]:
    return {
        "key": key,
        "overlay": f"set:{value}" if operation == "set" else operation,
        "operation": operation,
        "value": value,
        "authority": "step1_source_backed_posture",
        "key_authority": authority_for_key(key),
        "claim_refs": claim_refs,
        "reason": reason,
    }


def _resolve_posture(aggression_profile: str, claims: list[dict[str, Any]]) -> str | None:
    for claim in claims:
        if str(claim.get("claim_kind", claim.get("claim_type", ""))) != "gameplan_posture":
            continue
        stance = _normalize_posture(str(claim.get("stance", "")))
        if stance in POSTURE_OVERLAYS:
            return stance
    profile = _normalize_posture(aggression_profile)
    if profile in POSTURE_OVERLAYS:
        return profile
    return None


def _normalize_posture(value: str) -> str:
    lowered = value.lower()
    return POSTURE_ALIASES.get(lowered, lowered)


def _claim_refs(claims: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for claim in claims:
        if claim.get("claim_id"):
            refs.append(str(claim["claim_id"]))
        refs.extend(str(item) for item in claim.get("source_refs", []))
    return list(dict.fromkeys(refs))
