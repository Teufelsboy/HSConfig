from __future__ import annotations

from typing import Any


STEP1_POSTURE_KEYS = {
    "FirstTurnValueWeight": "set:0.75",
    "SecondTurnValueWeight": "set:0.25",
    "GlobalMinionAttack": "increase",
    "GlobalMinionIntrinsicValue": "increase",
    "MyHeroPowerValue": "increase",
}
RUNTIME_EVIDENCE_KEYS = {
    "LowHpBoardValuePenalty",
    "OpponentSpecificMatchupTuning",
    "PostApplyRegressionTuning",
}


def build_globalvalues_authority_matrix(
    *,
    aggression_profile: str,
    claims: list[dict[str, Any]],
) -> dict[str, Any]:
    claim_refs = _claim_refs(claims)
    aggressive = aggression_profile.lower() in {"aggro", "aggressive", "tempo"} or any(
        str(claim.get("stance", "")).lower() in {"aggro", "aggressive", "tempo"}
        for claim in claims
        if str(claim.get("claim_kind", claim.get("claim_type", ""))) == "gameplan_posture"
    )
    allowed: list[dict[str, Any]] = []
    if aggressive:
        for key, overlay in STEP1_POSTURE_KEYS.items():
            allowed.append(
                {
                    "key": key,
                    "overlay": overlay,
                    "authority": "step1_source_backed_posture",
                    "claim_refs": claim_refs,
                    "reason": "aggressive_source_backed_posture",
                }
            )
    else:
        allowed.append(
            {
                "key": "baseline",
                "overlay": "none",
                "authority": "baseline_default",
                "claim_refs": [],
                "reason": "no_source_backed_posture_overlay",
            }
        )

    blocked = [
        {
            "key": key,
            "authority": "runtime_evidence_required",
            "claim_refs": claim_refs,
            "reason": "requires_runtime_evidence",
        }
        for key in sorted(RUNTIME_EVIDENCE_KEYS)
    ]
    for claim in claims:
        if str(claim.get("claim_kind", claim.get("claim_type", ""))) == "globalvalue_numeric_tuning":
            blocked.append(
                {
                    "key": str(claim.get("key", "runtime_numeric_tuning")),
                    "authority": "runtime_evidence_required",
                    "claim_refs": _claim_refs([claim]),
                    "reason": "requires_runtime_evidence",
                }
            )
    return {
        "aggression_profile": aggression_profile,
        "allowed_step1_overlays": allowed,
        "blocked_until_runtime_evidence": blocked,
    }


def _claim_refs(claims: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for claim in claims:
        if claim.get("claim_id"):
            refs.append(str(claim["claim_id"]))
        refs.extend(str(item) for item in claim.get("source_refs", []))
    return list(dict.fromkeys(refs))
