from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_document_model import normalized_claim_kind, surface_gate_decision


def build_initial_lifecycle_rows(
    claims: Sequence[Mapping[str, Any]],
    *,
    conflict_report: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    quarantined = _quarantined_claim_ids(conflict_report or {})
    rows: list[dict[str, Any]] = []
    for index, claim in enumerate(claims, start=1):
        original = dict(claim)
        claim_kind = normalized_claim_kind(original)
        migrated_claim = deepcopy(original)
        legacy_claim_type = migrated_claim.pop("claim_type", None)
        if claim_kind:
            migrated_claim["claim_kind"] = claim_kind
        claim_id = str(migrated_claim.get("claim_id") or f"claim_{index}")
        policy = source_contract_policy_by_claim_kind().get(claim_kind, {})
        source_confidence = str(
            migrated_claim.get("source_confidence")
            or migrated_claim.get("confidence")
            or "unknown"
        )
        quarantine_reason = quarantined.get(claim_id)
        row = {
            "claim_id": claim_id,
            "claim_kind": claim_kind,
            "legacy_claim_type": legacy_claim_type,
            "migration_status": (
                "legacy_claim_type_migrated"
                if legacy_claim_type and claim_kind
                else "modern_claim_kind"
            ),
            "source_confidence": source_confidence,
            "policy_lane": policy.get("lane", "unknown"),
            "allowed_surfaces": list(policy.get("allowed_surfaces", ())),
            "semantic_qualifiers": migrated_claim.get("semantic_qualifiers", {}),
            "quarantine_status": "quarantined" if quarantine_reason else "clear",
            "quarantine_reason": quarantine_reason or "",
            "runtime_eligibility": _runtime_eligibility(
                source_confidence, quarantine_reason
            ),
            "claim": migrated_claim,
        }
        rows.append(row)
    return rows


def runtime_claims_for_surface(
    rows: Sequence[Mapping[str, Any]],
    surface: str,
    *,
    context: Mapping[str, Any] | None = None,
    card_roles: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    gate_context = dict(context or {})
    if card_roles is not None:
        gate_context["card_roles"] = card_roles
    runtime_claims: list[dict[str, Any]] = []
    for row in rows:
        if row.get("quarantine_status") == "quarantined":
            continue
        if row.get("runtime_eligibility") == "report_only":
            continue
        claim = dict(row.get("claim") or {})
        claim_kind = str(row.get("claim_kind") or "")
        if not claim_kind:
            continue
        decision = surface_gate_decision(claim, surface, context=gate_context)
        if not decision.allowed:
            continue
        claim["claim_kind"] = claim_kind
        claim["_claim_lifecycle"] = {
            "claim_id": row.get("claim_id"),
            "surface": surface,
            "policy_lane": row.get("policy_lane"),
            "surface_gate_reason": decision.reason,
        }
        runtime_claims.append(claim)
    return runtime_claims


def _runtime_eligibility(source_confidence: str, quarantine_reason: str | None) -> str:
    if quarantine_reason:
        return "quarantined"
    normalized_confidence = str(source_confidence or "unknown").strip().lower()
    if normalized_confidence in {
        "report_only",
        "unsupported",
        "unknown",
        "unknown_future_mechanic",
    }:
        return "report_only"
    return "runtime_candidate"


def _quarantined_claim_ids(conflict_report: Mapping[str, Any]) -> dict[str, str]:
    quarantined: dict[str, str] = {}
    for conflict in conflict_report.get("conflicts", []) or []:
        reason = str(conflict.get("reason") or "source_claim_conflict")
        for claim_id in conflict.get("claim_ids", []) or []:
            quarantined[str(claim_id)] = reason
    return quarantined
