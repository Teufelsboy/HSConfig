from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from hsconfig.globalvalues_decisions import GLOBALVALUES_BASELINE_DECISION_KEYS
from hsconfig.globalvalues_key_authority import RUNTIME_EVIDENCE_KEYS, authority_for_key
from hsconfig.source_claim_lifecycle import lifecycle_claim_id
from hsconfig.source_document_model import can_lower_to_globalvalues, normalized_claim_kind


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
    deck_identity: Mapping[str, Any] | None = None,
    verified_source_receipts: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    claim_decisions = [
        (
            claim,
            can_lower_to_globalvalues(
                claim,
                deck_identity=deck_identity,
                verified_source_receipts=verified_source_receipts,
            ),
        )
        for claim in claims
    ]
    lowerable_claims = [
        claim for claim, decision in claim_decisions if decision.allowed
    ]
    claim_refs = _claim_refs(lowerable_claims)
    posture = _resolve_posture(aggression_profile, lowerable_claims)
    posture_claim_id = _posture_claim_id(posture, lowerable_claims)
    overlays = POSTURE_OVERLAYS.get(posture or "", {})
    baseline_overlays = {
        key: value
        for key, value in overlays.items()
        if key in GLOBALVALUES_BASELINE_DECISION_KEYS
    }
    nonbaseline_overlays = {
        key: value
        for key, value in overlays.items()
        if key not in GLOBALVALUES_BASELINE_DECISION_KEYS
    }
    if baseline_overlays:
        allowed = [
            _allowed_row(
                key=key,
                operation=operation,
                value=value,
                reason=reason,
                claim_refs=claim_refs,
                claim_id=posture_claim_id,
            )
            for key, (operation, value, reason) in baseline_overlays.items()
        ]
    else:
        allowed = [_baseline_default_row()]

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
    blocked.extend(
        _nonbaseline_posture_suppressed_row(
            key=key,
            operation=operation,
            value=value,
            candidate_reason=reason,
            claim_refs=claim_refs,
            claim_id=posture_claim_id,
        )
        for key, (operation, value, reason) in nonbaseline_overlays.items()
    )
    blocked_claim_id = _single_claim_id(lowerable_claims)
    if blocked_claim_id:
        for row in blocked:
            row["claim_id"] = blocked_claim_id
    for claim in claims:
        if normalized_claim_kind(claim) == "globalvalue_numeric_tuning":
            blocked.append(_numeric_tuning_blocked_row(claim))
    for claim, decision in claim_decisions:
        if (
            normalized_claim_kind(claim) == "gameplan_posture"
            and not decision.allowed
            and decision.reason.startswith("globalvalues_")
        ):
            blocked.append(_source_contract_suppressed_row(claim, decision.reason))
    return {
        "aggression_profile": aggression_profile,
        "posture": posture or "baseline",
        "allowed_step1_overlays": allowed,
        "blocked_until_runtime_evidence": blocked,
    }


def _baseline_default_row() -> dict[str, Any]:
    return {
        "key": "baseline",
        "overlay": "none",
        "operation": "none",
        "value": None,
        "authority": "baseline_default",
        "key_authority": authority_for_key("baseline"),
        "claim_refs": [],
        "reason": "no_source_backed_posture_overlay",
    }


def _allowed_row(
    *,
    key: str,
    operation: str,
    value: str | None,
    reason: str,
    claim_refs: list[str],
    claim_id: str,
) -> dict[str, Any]:
    row = {
        "key": key,
        "overlay": f"set:{value}" if operation == "set" else operation,
        "operation": operation,
        "value": value,
        "authority": "step1_source_backed_posture",
        "key_authority": authority_for_key(key),
        "claim_refs": claim_refs,
        "reason": reason,
    }
    if claim_id:
        row["claim_id"] = claim_id
    return row


def _nonbaseline_posture_suppressed_row(
    *,
    key: str,
    operation: str,
    value: str | None,
    candidate_reason: str,
    claim_refs: list[str],
    claim_id: str,
) -> dict[str, Any]:
    reason = "globalvalues_key_outside_baseline_decision_registry"
    row = {
        "key": key,
        "overlay": f"set:{value}" if operation == "set" else operation,
        "operation": operation,
        "value": value,
        "authority": "source_contract_suppressed",
        "key_authority": authority_for_key(key),
        "claim_refs": claim_refs,
        "reason": reason,
        "blocked_reason": reason,
        "candidate_reason": candidate_reason,
    }
    if claim_id:
        row["claim_id"] = claim_id
    return row


def _resolve_posture(aggression_profile: str, claims: list[dict[str, Any]]) -> str | None:
    for claim in claims:
        if normalized_claim_kind(claim) != "gameplan_posture":
            continue
        stance = _normalize_posture(str(claim.get("stance", "")))
        if stance in POSTURE_OVERLAYS:
            return stance
    return None


def _posture_claim_id(posture: str | None, claims: list[dict[str, Any]]) -> str:
    if not posture:
        return ""
    for claim in claims:
        if normalized_claim_kind(claim) != "gameplan_posture":
            continue
        if _normalize_posture(str(claim.get("stance", ""))) == posture:
            return lifecycle_claim_id(claim)
    return ""


def _single_claim_id(claims: list[dict[str, Any]]) -> str:
    claim_ids = [lifecycle_claim_id(claim) for claim in claims]
    claim_ids = [claim_id for claim_id in claim_ids if claim_id]
    if len(set(claim_ids)) == 1:
        return claim_ids[0]
    return ""


def _numeric_tuning_blocked_row(claim: dict[str, Any]) -> dict[str, Any]:
    key = str(claim.get("key", "runtime_numeric_tuning"))
    row = {
        "key": key,
        "authority": "runtime_evidence_required",
        "key_authority": authority_for_key(key),
        "claim_refs": _claim_refs([claim]),
        "reason": "requires_runtime_evidence",
        "blocked_reason": "requires_runtime_evidence",
    }
    claim_id = lifecycle_claim_id(claim)
    if claim_id:
        row["claim_id"] = claim_id
    return row


def _source_contract_suppressed_row(
    claim: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    row = {
        "key": "gameplan_posture",
        "authority": "source_contract_suppressed",
        "key_authority": authority_for_key("gameplan_posture"),
        "claim_refs": _claim_refs([claim]),
        "reason": reason,
        "blocked_reason": reason,
    }
    claim_id = lifecycle_claim_id(claim)
    if claim_id:
        row["claim_id"] = claim_id
    return row


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
