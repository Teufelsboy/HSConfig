from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces
from hsconfig.combo_plan import build_combo_plan
from hsconfig.globalvalues_authority import build_globalvalues_authority_matrix
from hsconfig.mulligan_plan import build_mulligan_plan
from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_document_model import (
    SUPPORTED_ATOMIC_CLAIM_KINDS,
    surface_gate_decision,
)


SURFACES = ("mulligan", "globalvalues", "cardid", "combo")
OPERATOR_GATE_IMPACT = "diagnostic_only"

_BUILDER_ROUTER_EXPECTATIONS = {
    "archetype": {"surface": None, "runner": "not_seen_by_builder", "outcome": "not_seen_by_builder"},
    "mulligan_keep": {"surface": "mulligan", "runner": "build_mulligan_plan", "outcome": "emitted"},
    "mulligan_discard": {"surface": "mulligan", "runner": "build_mulligan_plan", "outcome": "emitted"},
    "card_role": {"surface": "cardid", "runner": "route_card_behavior_surfaces", "outcome": "emitted"},
    "targeting_rule": {"surface": "cardid", "runner": "route_card_behavior_surfaces", "outcome": "emitted"},
    "combo_sequence": {"surface": "combo", "runner": "build_combo_plan", "outcome": "emitted"},
    "gameplan_posture": {"surface": "globalvalues", "runner": "build_globalvalues_authority_matrix", "outcome": "emitted"},
    "hero_power_transform": {"surface": "cardid", "runner": "route_card_behavior_surfaces", "outcome": "emitted"},
    "mechanic_usage": {"surface": "cardid", "runner": "route_card_behavior_surfaces", "outcome": "emitted"},
    "known_bad_pattern": {"surface": "cardid", "runner": "route_card_behavior_surfaces", "outcome": "emitted"},
    "tech_slot": {"surface": None, "runner": "not_seen_by_builder", "outcome": "not_seen_by_builder"},
    "replacement_option": {"surface": None, "runner": "not_seen_by_builder", "outcome": "not_seen_by_builder"},
    "discover_choice": {"surface": "cardid", "runner": "route_card_behavior_surfaces", "outcome": "emitted"},
    "choose_one_choice": {"surface": "cardid", "runner": "route_card_behavior_surfaces", "outcome": "emitted"},
    "globalvalue_numeric_tuning": {"surface": "globalvalues", "runner": "build_globalvalues_authority_matrix", "outcome": "suppressed"},
}


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
    policy_gate_mismatches = _policy_gate_mismatches(rows)
    builder_expectation_mismatches = _builder_expectation_mismatches(rows)
    surface_gate_builder_mismatches = _surface_gate_builder_mismatches(rows)
    return {
        "schema_version": 1,
        "operator_gate_impact": OPERATOR_GATE_IMPACT,
        "summary": {
            "claim_kinds_total": len(rows),
            "policy_lane_counts": dict(sorted(lane_counts.items())),
            "missing_claim_kinds": missing,
            "extra_claim_kinds": extra,
            "policy_gate_mismatch_count": len(policy_gate_mismatches),
            "policy_gate_mismatches": policy_gate_mismatches,
            "builder_router_expectation_mismatch_count": len(builder_expectation_mismatches),
            "builder_router_expectation_mismatches": builder_expectation_mismatches,
            "surface_gate_builder_mismatch_count": len(surface_gate_builder_mismatches),
            "surface_gate_builder_mismatches": surface_gate_builder_mismatches,
            "pipeline_mismatch_count": len(policy_gate_mismatches)
            + len(builder_expectation_mismatches)
            + len(surface_gate_builder_mismatches),
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
    lines.extend(
        [
            "",
            "## Builder/Router Outcomes",
            "",
            "| Claim Kind | Surface | Runner | Complete | Incomplete |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for claim_kind, row in sorted(rows.items()):
        if not isinstance(row, Mapping):
            continue
        builder_router = row.get("builder_router", {})
        if not isinstance(builder_router, Mapping):
            continue
        lines.append(
            "| {claim} | {surface} | {runner} | {complete} | {incomplete} |".format(
                claim=_escape_table(claim_kind),
                surface=_escape_table(builder_router.get("surface") or "none"),
                runner=_escape_table(builder_router.get("runner", "")),
                complete=_escape_table(_builder_outcome_summary(builder_router.get("complete"))),
                incomplete=_escape_table(
                    _builder_outcome_summary(builder_router.get("incomplete"))
                ),
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
        "builder_router": _builder_router_expectation(claim_kind),
    }


def _builder_router_expectation(claim_kind: str) -> dict[str, Any]:
    expectation = _BUILDER_ROUTER_EXPECTATIONS[claim_kind]
    complete = _builder_runner_result(
        claim_kind,
        _representative_claim(claim_kind),
        expectation,
    )
    row = {
        "surface": expectation["surface"],
        "runner": expectation["runner"],
        "complete": {
            "expected_outcome": expectation["outcome"],
            **complete,
        },
    }
    if claim_kind == "combo_sequence":
        incomplete_expectation = {**expectation, "outcome": "suppressed"}
        row["incomplete"] = {
            "expected_outcome": "suppressed",
            **_builder_runner_result(
                claim_kind,
                _representative_claim(claim_kind, incomplete=True),
                incomplete_expectation,
            ),
        }
    return row


def _representative_claim(claim_kind: str, *, incomplete: bool = False) -> dict[str, Any]:
    claim = {
        "claim_id": f"conformance_{claim_kind}",
        "claim_kind": claim_kind,
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["CARD_001"],
    }
    if claim_kind == "combo_sequence":
        cards = ["CARD_001"] if incomplete else ["CARD_001", "CARD_002"]
        return {
            **claim,
            "cards": cards,
            "sequence": cards,
            "timing_kind": "same_turn",
            "operator": ">>",
            "values": ["6"] * len(cards),
        }
    if claim_kind == "gameplan_posture":
        return {**claim, "cards": [], "stance": "aggro_burn"}
    if claim_kind == "globalvalue_numeric_tuning":
        return {**claim, "cards": [], "key": "LowHpBoardValuePenalty"}
    if claim_kind == "card_role":
        return {**claim, "runtime_block": "InHandBonus"}
    if claim_kind == "targeting_rule":
        return {**claim, "stance": "prefer_enemy_hero"}
    if claim_kind == "mechanic_usage":
        return {**claim, "mechanic": "deathrattle"}
    if claim_kind == "known_bad_pattern":
        return {**claim, "runtime_block": "BeforePlayCardBonus"}
    if claim_kind in {"discover_choice", "choose_one_choice"}:
        return {**claim, "option_card_id": "OPTION_001", "stance": "pick_option"}
    return claim


def _builder_runner_result(
    claim_kind: str,
    claim: dict[str, Any],
    expectation: Mapping[str, Any],
) -> dict[str, str]:
    runner = str(expectation["runner"])
    if runner == "not_seen_by_builder":
        return {"outcome": "not_seen_by_builder", "reason": "no_runtime_builder"}
    if runner == "build_combo_plan":
        plan = build_combo_plan(
            deck_cards={str(card) for card in claim.get("cards", [])},
            claims=[claim],
        )
        if plan["combos"]:
            return {"outcome": "emitted", "reason": "emitted"}
        return _suppressed_result(plan["suppressed"])
    if runner == "build_mulligan_plan":
        plan = build_mulligan_plan(
            deck_name="Conformance",
            claims=[claim],
            card_roles={"CARD_001": {"roles": ["mulligan_anchor"]}},
        )
        if any(row.get("source_claim_ids") == [claim["claim_id"]] for row in plan["rules"]):
            return {"outcome": "emitted", "reason": "emitted"}
        return _suppressed_result(plan["suppressed_rules"])
    if runner == "build_globalvalues_authority_matrix":
        plan = build_globalvalues_authority_matrix(
            aggression_profile="baseline",
            claims=[claim],
        )
        if any(claim["claim_id"] in row.get("claim_refs", []) for row in plan["allowed_step1_overlays"]):
            return {"outcome": "emitted", "reason": "emitted"}
        return _suppressed_result(plan["blocked_until_runtime_evidence"])
    if runner == "route_card_behavior_surfaces":
        plan = route_card_behavior_surfaces(
            [claim],
            identity_links={"CARD_001": [{"card_id": "OPTION_001"}]},
        )
        if any(row.get("claim_id") == claim["claim_id"] for row in plan["rows"]):
            return {"outcome": "emitted", "reason": "emitted"}
        return _suppressed_result(plan["suppressed"])
    raise RuntimeError(f"Unsupported conformance runner: {runner}")


def _suppressed_result(rows: list[Mapping[str, Any]]) -> dict[str, str]:
    reason = str(rows[0].get("reason", "not_emittable")) if rows else "not_seen_by_builder"
    outcome = "suppressed" if rows else "not_seen_by_builder"
    return {"outcome": outcome, "reason": reason}


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


def _builder_expectation_mismatches(rows: Mapping[str, Any]) -> list[dict[str, Any]]:
    mismatches = []
    for claim_kind, row in sorted(rows.items()):
        if not isinstance(row, Mapping):
            continue
        builder_router = row.get("builder_router", {})
        if not isinstance(builder_router, Mapping):
            continue
        for exemplar_name in ("complete", "incomplete"):
            exemplar = builder_router.get(exemplar_name)
            if not isinstance(exemplar, Mapping):
                continue
            if exemplar.get("expected_outcome") == exemplar.get("outcome"):
                continue
            mismatches.append(
                {
                    "claim_kind": claim_kind,
                    "exemplar": exemplar_name,
                    "expected_outcome": exemplar.get("expected_outcome", ""),
                    "builder_outcome": exemplar.get("outcome", ""),
                    "reason": exemplar.get("reason", ""),
                }
            )
    return mismatches


def _surface_gate_builder_mismatches(rows: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Expose builder prerequisites beyond an allowed runtime-surface gate."""
    mismatches = []
    for claim_kind, row in sorted(rows.items()):
        if not isinstance(row, Mapping):
            continue
        builder_router = row.get("builder_router", {})
        if not isinstance(builder_router, Mapping):
            continue
        surface = builder_router.get("surface")
        gates = row.get("surface_gates", {})
        if not isinstance(surface, str) or not isinstance(gates, Mapping):
            continue
        gate = gates.get(surface, {})
        if not isinstance(gate, Mapping) or gate.get("decision") != "allowed":
            continue
        for exemplar_name in ("complete", "incomplete"):
            exemplar = builder_router.get(exemplar_name)
            if not isinstance(exemplar, Mapping):
                continue
            if exemplar.get("outcome") == "emitted":
                continue
            mismatches.append(
                {
                    "claim_kind": claim_kind,
                    "surface": surface,
                    "builder_outcome": exemplar.get("outcome", ""),
                    "reason": exemplar.get("reason", ""),
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


def _builder_outcome_summary(exemplar: Any) -> str:
    if not isinstance(exemplar, Mapping):
        return "-"
    outcome = str(exemplar.get("outcome", ""))
    reason = str(exemplar.get("reason", ""))
    if outcome == reason or not reason:
        return outcome
    return f"{outcome}: {reason}"


def _escape_table(value: Any) -> str:
    return str(value).replace("|", "\\|")
