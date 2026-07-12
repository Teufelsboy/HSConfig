from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_document_model import (
    SUPPORTED_ATOMIC_CLAIM_KINDS,
    surface_gate_decision,
)


SURFACES = ("mulligan", "globalvalues", "cardid", "combo")
OPERATOR_GATE_IMPACT = "diagnostic_only"


def build_source_contract_conformance_snapshot() -> dict[str, Any]:
    """Build a deck-neutral proof that policy lanes and live surface gates align."""
    policy = source_contract_policy_by_claim_kind()
    rows = {
        claim_kind: _claim_kind_row(claim_kind, row)
        for claim_kind, row in policy.items()
    }
    missing = sorted(set(SUPPORTED_ATOMIC_CLAIM_KINDS) - set(rows))
    extra = sorted(set(rows) - set(SUPPORTED_ATOMIC_CLAIM_KINDS))
    lane_counts = Counter(str(row["policy_lane"]) for row in rows.values())
    mismatches = _policy_gate_mismatches(rows)
    return {
        "schema_version": 1,
        "operator_gate_impact": OPERATOR_GATE_IMPACT,
        "summary": {
            "claim_kinds_total": len(rows),
            "policy_lane_counts": dict(sorted(lane_counts.items())),
            "missing_claim_kinds": missing,
            "extra_claim_kinds": extra,
            "policy_gate_mismatch_count": len(mismatches),
            "policy_gate_mismatches": mismatches,
        },
        "claim_kind_rows": rows,
        "start_of_game_mulligan_suppression": _start_of_game_suppression_row(),
    }


def render_source_contract_conformance_markdown(snapshot: Mapping[str, Any]) -> str:
    """Render the conformance snapshot as compact operator/developer Markdown."""
    rows = snapshot.get("claim_kind_rows", {})
    if not isinstance(rows, Mapping):
        rows = {}
    lines = [
        "# Source Contract Conformance Snapshot",
        "",
        "Diagnostic only. operator_summary.json remains the apply authority.",
        "",
        "| Claim Kind | Policy Lane | Allowed Surfaces | Gate Summary |",
        "| --- | --- | --- | --- |",
    ]
    for claim_kind, row in sorted(rows.items()):
        if not isinstance(row, Mapping):
            continue
        allowed = row.get("allowed_surfaces", [])
        surfaces = ", ".join(str(surface) for surface in allowed) or "none"
        gate_summary = _gate_summary(row.get("surface_gates", {}))
        lines.append(
            "| {claim} | {lane} | {surfaces} | {gates} |".format(
                claim=_escape_table(claim_kind),
                lane=_escape_table(row.get("policy_lane", "")),
                surfaces=_escape_table(surfaces),
                gates=_escape_table(gate_summary),
            )
        )
    lines.append("")
    suppression = snapshot.get("start_of_game_mulligan_suppression", {})
    if isinstance(suppression, Mapping):
        lines.extend(
            [
                "## Start-of-Game Mulligan Boundary",
                "",
                "- Decision: {decision}".format(decision=suppression.get("decision", "")),
                "- Reason: {reason}".format(reason=suppression.get("reason", "")),
                "- Meaning: {meaning}".format(
                    meaning=suppression.get("operator_meaning", "")
                ),
            ]
        )
    return "\n".join(lines)


def _claim_kind_row(claim_kind: str, policy_row: Mapping[str, object]) -> dict[str, Any]:
    claim = {
        "claim_kind": claim_kind,
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["CARD_001"],
    }
    context = {
        "card_roles": {
            "CARD_001": {
                "roles": ["mulligan_anchor"],
                "semantic_families": [],
            }
        }
    }
    gates = {
        surface: _decision_row(surface_gate_decision(claim, surface, context=context))
        for surface in SURFACES
    }
    return {
        "claim_kind": claim_kind,
        "policy_lane": str(policy_row.get("lane", "")),
        "allowed_surfaces": list(policy_row.get("allowed_surfaces", ())),
        "operator_meaning": str(policy_row.get("operator_meaning", "")),
        "surface_gates": gates,
    }


def _start_of_game_suppression_row() -> dict[str, Any]:
    decision = surface_gate_decision(
        {
            "claim_kind": "mulligan_keep",
            "claim_readiness": "guide_backed",
            "trust_ceiling": "runtime_candidate",
            "cards": ["SW_448"],
        },
        "mulligan",
        context={
            "card_roles": {
                "SW_448": {
                    "roles": ["start_of_game", "hero_power_transform"],
                    "semantic_families": ["start_of_game", "hero_power_transform"],
                }
            }
        },
    )
    row = _decision_row(decision)
    row["operator_meaning"] = (
        "Start-of-game effects remain effect-visible but do not become opening-hand keeps."
    )
    return row


def _decision_row(decision: Any) -> dict[str, Any]:
    return {
        "claim_kind": str(decision.claim_kind),
        "surface": str(decision.surface),
        "decision": "allowed" if bool(decision.allowed) else "rejected",
        "reason": str(decision.reason),
    }


def _policy_gate_mismatches(rows: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return diagnostic disagreements between policy surfaces and live gates."""
    mismatches = []
    for claim_kind, row in sorted(rows.items()):
        if not isinstance(row, Mapping):
            continue
        allowed_surfaces = set(row.get("allowed_surfaces", ()))
        gates = row.get("surface_gates", {})
        if not isinstance(gates, Mapping):
            continue
        for surface in SURFACES:
            gate = gates.get(surface, {})
            if not isinstance(gate, Mapping):
                continue
            policy_allowed = surface in allowed_surfaces
            gate_allowed = gate.get("decision") == "allowed"
            if policy_allowed == gate_allowed:
                continue
            mismatches.append(
                {
                    "claim_kind": claim_kind,
                    "surface": surface,
                    "policy_allowed": policy_allowed,
                    "gate_decision": gate.get("decision", ""),
                    "gate_reason": gate.get("reason", ""),
                }
            )
    return mismatches


def _gate_summary(gates: Any) -> str:
    if not isinstance(gates, Mapping):
        return ""
    parts = []
    for surface in SURFACES:
        row = gates.get(surface, {})
        if not isinstance(row, Mapping):
            continue
        parts.append(f"{surface}:{row.get('decision')}:{row.get('reason')}")
    return "; ".join(parts)


def _escape_table(value: Any) -> str:
    return str(value).replace("|", "\\|")
