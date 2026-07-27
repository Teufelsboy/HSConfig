from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_document_model import (
    claim_can_lower_to_runtime,
    normalized_claim_kind,
    surface_gate_decision,
)
from hsconfig.source_semantic_qualifiers import normalize_semantic_qualifiers


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
        semantic_qualifiers = normalize_semantic_qualifiers(migrated_claim)
        if semantic_qualifiers:
            migrated_claim["semantic_qualifiers"] = semantic_qualifiers
        claim_id = str(migrated_claim.get("claim_id") or f"claim_{index}")
        policy = source_contract_policy_by_claim_kind().get(claim_kind, {})
        source_confidence = str(
            migrated_claim.get("source_confidence")
            or migrated_claim.get("confidence")
            or migrated_claim.get("claim_readiness")
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
            "semantic_qualifiers": semantic_qualifiers,
            "quarantine_status": "quarantined" if quarantine_reason else "clear",
            "quarantine_reason": quarantine_reason or "",
            "runtime_eligibility": _runtime_eligibility(
                migrated_claim,
                source_confidence,
                quarantine_reason,
            ),
            "claim": migrated_claim,
        }
        rows.append(row)
    return rows


def select_claims_for_surface(
    rows: Sequence[Mapping[str, Any]],
    surface: str,
    *,
    context: Mapping[str, Any] | None = None,
    card_roles: Mapping[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return accepted and rejected runtime-eligible claims with lifecycle reasons."""
    gate_context = dict(context or {})
    if card_roles is not None:
        gate_context["card_roles"] = card_roles
    accepted_claims: list[dict[str, Any]] = []
    rejected_claims: list[dict[str, Any]] = []
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
        claim["claim_kind"] = claim_kind
        claim["_claim_lifecycle"] = {
            "claim_id": row.get("claim_id"),
            "surface": surface,
            "policy_lane": row.get("policy_lane"),
            "surface_gate_allowed": decision.allowed,
            "surface_gate_reason": decision.reason,
        }
        if decision.allowed:
            accepted_claims.append(claim)
        else:
            rejected_claims.append(claim)
    return {
        "accepted_claims": accepted_claims,
        "rejected_claims": rejected_claims,
    }


def runtime_claims_for_surface(
    rows: Sequence[Mapping[str, Any]],
    surface: str,
    *,
    context: Mapping[str, Any] | None = None,
    card_roles: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return select_claims_for_surface(
        rows,
        surface,
        context=context,
        card_roles=card_roles,
    )["accepted_claims"]


def diagnostic_claims_for_surface(
    rows: Sequence[Mapping[str, Any]],
    surface: str,
    *,
    context: Mapping[str, Any] | None = None,
    card_roles: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return non-accepted claims for a diagnostic-only surface path.

    These claims must never be passed to a runtime builder. The lifecycle
    annotation carries the precise reason that kept each claim out of the
    accepted runtime selection.
    """
    selection = select_claims_for_surface(
        rows,
        surface,
        context=context,
        card_roles=card_roles,
    )
    accepted_ids = {
        lifecycle_claim_id(claim)
        for claim in selection["accepted_claims"]
    }
    rejected_by_id = {
        lifecycle_claim_id(claim): claim
        for claim in selection["rejected_claims"]
    }
    diagnostic_claims: list[dict[str, Any]] = []
    for row in rows:
        if surface not in set(row.get("allowed_surfaces") or []):
            continue
        claim_id = str(row.get("claim_id") or "")
        if not claim_id or claim_id in accepted_ids:
            continue
        rejected = rejected_by_id.get(claim_id)
        if rejected is not None:
            diagnostic_claims.append(deepcopy(rejected))
            continue

        claim = deepcopy(dict(row.get("claim") or {}))
        claim_kind = str(row.get("claim_kind") or "")
        if not claim_kind:
            continue
        if row.get("quarantine_status") == "quarantined":
            reason = str(row.get("quarantine_reason") or "source_claim_conflict")
        elif row.get("runtime_eligibility") == "report_only":
            reason = "claim_not_runtime_lowerable"
        else:
            continue
        claim["claim_kind"] = claim_kind
        claim["_claim_lifecycle"] = {
            "claim_id": claim_id,
            "surface": surface,
            "policy_lane": row.get("policy_lane"),
            "surface_gate_allowed": False,
            "surface_gate_reason": reason,
        }
        diagnostic_claims.append(claim)
    return diagnostic_claims


def lifecycle_claim_id(claim: Mapping[str, Any]) -> str:
    lifecycle = claim.get("_claim_lifecycle")
    if isinstance(lifecycle, Mapping):
        value = lifecycle.get("claim_id")
        if value:
            return str(value)
    value = claim.get("claim_id")
    return str(value) if value else ""


def _runtime_eligibility(
    claim: Mapping[str, Any],
    source_confidence: str,
    quarantine_reason: str | None,
) -> str:
    if quarantine_reason:
        return "quarantined"
    if not claim_can_lower_to_runtime(dict(claim)):
        return "report_only"
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
