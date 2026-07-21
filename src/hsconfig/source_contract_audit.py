from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Mapping, Sequence

from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_document_model import (
    claim_can_lower_to_runtime,
    normalized_claim_kind,
    surface_gate_decision,
)


SURFACES = ("mulligan", "globalvalues", "cardid", "combo")
_DIAGNOSTIC_OPERATOR_IMPACT = "diagnostic_only"


def build_source_contract_audit(
    *,
    deck_name: str,
    deck_identity: Mapping[str, Any] | None = None,
    guide_claim_bundle: Mapping[str, Any] | None = None,
    mulligan_plan: Mapping[str, Any] | None = None,
    card_behavior_plan: Mapping[str, Any] | None = None,
    combo_plan: Mapping[str, Any] | None = None,
    global_values_authority_matrix: Mapping[str, Any] | None = None,
    config_readiness_report: Mapping[str, Any] | None = None,
    runtime_emission_index: Mapping[str, Mapping[str, Any]] | None = None,
    initial_lifecycle_rows: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Explain why source claims did or did not lower into runtime surfaces."""
    deck_identity = deck_identity or {}
    guide_claim_bundle = guide_claim_bundle or {}
    mulligan_plan = mulligan_plan or {}
    card_behavior_plan = card_behavior_plan or {}
    combo_plan = combo_plan or {}
    global_values_authority_matrix = global_values_authority_matrix or {}
    config_readiness_report = config_readiness_report or {}

    emitted_claim_ids = _emitted_claim_ids(
        mulligan_plan=mulligan_plan,
        card_behavior_plan=card_behavior_plan,
        combo_plan=combo_plan,
        global_values_authority_matrix=global_values_authority_matrix,
    )
    suppressed_reasons = _suppressed_reasons(
        mulligan_plan=mulligan_plan,
        card_behavior_plan=card_behavior_plan,
        combo_plan=combo_plan,
        global_values_authority_matrix=global_values_authority_matrix,
    )
    card_roles = _card_roles_from_readiness(config_readiness_report)
    runtime_emission_index = runtime_emission_index or _runtime_emission_index(
        mulligan_plan=mulligan_plan,
        card_behavior_plan=card_behavior_plan,
        combo_plan=combo_plan,
        global_values_authority_matrix=global_values_authority_matrix,
    )

    claim_rows: dict[str, dict[str, Any]] = {}
    card_claim_lanes: dict[str, Counter[str]] = defaultdict(Counter)
    claims = _guide_claims(guide_claim_bundle)
    try:
        policy_by_claim_kind = source_contract_policy_by_claim_kind()
    except RuntimeError:
        policy_by_claim_kind = {}
    policy_lane_counts: Counter[str] = Counter()
    for index, claim in enumerate(claims, start=1):
        claim_id = _claim_id(claim, index)
        cards = _claim_cards(claim)
        decisions = {
            surface: _decision_row(
                surface_gate_decision(
                    claim,
                    surface,
                    context={"card_roles": card_roles},
                )
            )
            for surface in SURFACES
        }
        suppressed_reason = suppressed_reasons.get(claim_id)
        emitted_surfaces = [
            surface
            for surface in SURFACES
            if decisions[surface]["allowed"]
            if _claim_lowered_to_surface(
                claim_id=claim_id,
                claim=claim,
                surface=surface,
                emitted_claim_ids=emitted_claim_ids,
                mulligan_plan=mulligan_plan,
                card_behavior_plan=card_behavior_plan,
                combo_plan=combo_plan,
                allow_legacy_card_fallback=suppressed_reason is None,
            )
        ]
        first_reason = suppressed_reason or _first_gate_reason(decisions)
        lane = _claim_lane(
            claim=claim,
            emitted_surfaces=emitted_surfaces,
            suppressed_reason=suppressed_reason,
            decisions=decisions,
        )
        policy_lane = str(
            policy_by_claim_kind.get(normalized_claim_kind(claim), {}).get(
                "lane", "unsupported_or_unmapped"
            )
        )
        policy_lane_counts[policy_lane] += 1
        claim_rows[claim_id] = {
            "claim_id": claim_id,
            "claim_kind": normalized_claim_kind(claim),
            "claim_readiness": str(claim.get("claim_readiness", "")),
            "trust_ceiling": str(claim.get("trust_ceiling", "")),
            "source_title": str(claim.get("source_title", "")),
            "evidence_text_short": str(claim.get("evidence_text_short", "")),
            "source_type": str(claim.get("source_type", "")),
            "source_lane": str(claim.get("source_lane", "")),
            "cards": cards,
            "lane": lane,
            "policy_lane": policy_lane,
            "first_reason": first_reason,
            "lowered_surfaces": emitted_surfaces,
            "surfaces": decisions,
        }
        for card_id in cards:
            card_claim_lanes[card_id][lane] += 1

    card_rows = _card_rows(
        deck_identity=deck_identity,
        config_readiness_report=config_readiness_report,
        card_claim_lanes=card_claim_lanes,
    )
    summary = _summary(
        claim_rows=claim_rows,
        card_rows=card_rows,
        policy_lane_counts=policy_lane_counts,
    )
    if initial_lifecycle_rows is not None:
        claim_lifecycle_rows = _build_claim_lifecycle_rows_from_initial(
            initial_lifecycle_rows,
            claim_rows_by_id=claim_rows,
            runtime_emission_index=runtime_emission_index,
        )
    else:
        claim_lifecycle_rows = _build_claim_lifecycle_rows(
            list(claim_rows.values()),
            runtime_emission_index=runtime_emission_index,
        )
    summary["claim_lifecycle_decision_counts"] = _claim_lifecycle_decision_counts(
        claim_lifecycle_rows
    )
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "summary": summary,
        "claim_rows": claim_rows,
        "claim_lifecycle_rows": claim_lifecycle_rows,
        "card_rows": card_rows,
    }


def render_source_contract_audit_markdown(report: Mapping[str, Any]) -> str:
    """Render the audit as a compact operator-readable Markdown report."""
    summary = report.get("summary", {})
    if not isinstance(summary, Mapping):
        summary = {}
    lines = [
        f"# Source Contract Audit - {report.get('deck_name', '')}",
        "",
        "This report is diagnostic only. It explains the existing source-to-runtime gates and does not grant apply permission.",
        "",
        "## Summary",
        "",
        f"- Claims total: {_int(summary.get('claims_total'))}",
        f"- Runtime-lowered claims: {_int(summary.get('runtime_lowered_claims'))}",
        f"- Suppressed claims: {_int(summary.get('suppressed_claims'))}",
        f"- Runtime-evidence-required claims: {_int(summary.get('runtime_evidence_required_claims'))}",
        f"- Report-only claims: {_int(summary.get('report_only_claims'))}",
        f"- Cards with missing links: {_int(summary.get('cards_with_missing_links'))}",
        "",
        "## First Card Gaps",
        "",
        "| Card | Lane | First Missing Link | Runtime Surfaces | Claim Lanes |",
        "| --- | --- | --- | --- | --- |",
    ]

    rows = report.get("card_rows", {})
    if isinstance(rows, Mapping):
        sorted_rows = sorted(
            rows.items(),
            key=lambda item: (
                str(item[1].get("first_missing_link", "none")) in {"none", "closed", ""},
                str(item[1].get("name", item[0])),
            )
            if isinstance(item[1], Mapping)
            else (True, str(item[0])),
        )
        for card_id, row in sorted_rows[:20]:
            if not isinstance(row, Mapping):
                continue
            claim_lanes = row.get("claim_lanes", {})
            claim_lane_text = ", ".join(
                f"{key}:{value}" for key, value in sorted(claim_lanes.items())
            )
            surfaces = ", ".join(str(surface) for surface in row.get("runtime_surfaces", []))
            lines.append(
                "| {card} | {lane} | {missing} | {surfaces} | {claim_lanes} |".format(
                    card=_escape_table(f"{card_id} {row.get('name', '')}".strip()),
                    lane=_escape_table(row.get("readiness_lane", "")),
                    missing=_escape_table(row.get("first_missing_link", "")),
                    surfaces=_escape_table(surfaces),
                    claim_lanes=_escape_table(claim_lane_text),
                )
            )
    lines.append("")
    lifecycle_rows = report.get("claim_lifecycle_rows", [])
    if isinstance(lifecycle_rows, list):
        lines.extend(
            [
                "## Claim Lifecycle Trace",
                "",
                "This section is diagnostic only. `operator_summary.json` remains the normal apply gate.",
                "",
                "| Claim | Kind | Policy Lane | Surface Gate | Builder/Router | Runtime Surface | First Missing Link |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in lifecycle_rows[:30]:
            if not isinstance(row, Mapping):
                continue
            lines.append(
                "| {claim} | {kind} | {policy} | {gate} | {builder} | {surface} | {missing} |".format(
                    claim=_escape_table(row.get("claim_id", "")),
                    kind=_escape_table(row.get("claim_kind", "")),
                    policy=_escape_table(row.get("policy_lane", "")),
                    gate=_escape_table(
                        f"{row.get('surface_gate_decision', '')}:{row.get('surface_gate_reason', '')}"
                    ),
                    builder=_escape_table(row.get("builder_or_router_decision", "")),
                    surface=_escape_table(row.get("runtime_surface", "")),
                    missing=_escape_table(row.get("first_missing_link", "")),
                )
            )
        lines.append("")
    return "\n".join(lines)


def _guide_claims(bundle: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    claims = bundle.get("claims", [])
    if not isinstance(claims, list):
        return []
    return [claim for claim in claims if isinstance(claim, Mapping)]


def _claim_id(claim: Mapping[str, Any], index: int) -> str:
    explicit = str(claim.get("claim_id", "")).strip()
    return explicit or f"claim_{index:04d}"


def _claim_cards(claim: Mapping[str, Any]) -> list[str]:
    cards = claim.get("cards", [])
    if isinstance(cards, str):
        cards = [cards]
    if not isinstance(cards, list):
        cards = []
    for fallback_key in ("card_id", "card"):
        if not cards and claim.get(fallback_key):
            cards = [claim[fallback_key]]
    return sorted({str(card) for card in cards if str(card)})


def _decision_row(decision: Any) -> dict[str, Any]:
    return {
        "allowed": bool(decision.allowed),
        "reason": str(decision.reason),
        "claim_kind": str(decision.claim_kind),
        "surface": str(decision.surface),
    }


def _claim_lane(
    *,
    claim: Mapping[str, Any],
    emitted_surfaces: list[str],
    suppressed_reason: str | None,
    decisions: Mapping[str, Mapping[str, Any]],
) -> str:
    if emitted_surfaces:
        return "runtime_lowered"
    if any(row.get("reason") == "requires_runtime_evidence" for row in decisions.values()):
        return "runtime_evidence_required"
    if suppressed_reason:
        return "suppressed_with_reason"
    if not claim_can_lower_to_runtime(dict(claim)):
        return "report_only"
    return "unsupported_or_unmapped"


def _first_gate_reason(decisions: Mapping[str, Mapping[str, Any]]) -> str:
    for row in decisions.values():
        reason = str(row.get("reason", ""))
        if reason and reason != "allowed":
            return reason
    return "allowed"


def _emitted_claim_ids(
    *,
    mulligan_plan: Mapping[str, Any],
    card_behavior_plan: Mapping[str, Any],
    combo_plan: Mapping[str, Any],
    global_values_authority_matrix: Mapping[str, Any],
) -> dict[str, set[str]]:
    return {
        "mulligan": _ids_from_rows(mulligan_plan.get("rules", [])),
        "cardid": _ids_from_rows(card_behavior_plan.get("rows", [])),
        "combo": _ids_from_rows(combo_plan.get("combos", [])),
        "globalvalues": _ids_from_rows(
            global_values_authority_matrix.get("allowed_step1_overlays", [])
        ),
    }


def _suppressed_reasons(
    *,
    mulligan_plan: Mapping[str, Any],
    card_behavior_plan: Mapping[str, Any],
    combo_plan: Mapping[str, Any],
    global_values_authority_matrix: Mapping[str, Any],
) -> dict[str, str]:
    reasons: dict[str, str] = {}
    for rows in (
        mulligan_plan.get("suppressed_rules", []),
        card_behavior_plan.get("suppressed", []),
        combo_plan.get("suppressed", []),
        global_values_authority_matrix.get("blocked_until_runtime_evidence", []),
    ):
        for row in _rows(rows):
            reason = _normalized_suppression_reason(row)
            for claim_id in _row_claim_ids(row):
                reasons.setdefault(claim_id, reason)
    return reasons


def _runtime_emission_index(
    *,
    mulligan_plan: Mapping[str, Any],
    card_behavior_plan: Mapping[str, Any],
    combo_plan: Mapping[str, Any],
    global_values_authority_matrix: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    _merge_emission_rows(
        index,
        _runtime_rows(
            rows=mulligan_plan.get("rules", []),
            decision="emitted",
            surface="mulligan",
            runtime_surface="Mulligan.json",
            emitted_files=["Mulligan.json"],
        ),
    )
    _merge_emission_rows(
        index,
        _runtime_rows(
            rows=mulligan_plan.get("suppressed_rules", []),
            decision="suppressed",
            surface="mulligan",
        ),
    )
    _merge_emission_rows(
        index,
        _cardid_runtime_rows(card_behavior_plan.get("rows", [])),
    )
    _merge_emission_rows(
        index,
        _runtime_rows(
            rows=card_behavior_plan.get("suppressed", []),
            decision="suppressed",
            surface="cardid",
        ),
    )
    _merge_emission_rows(
        index,
        _runtime_rows(
            rows=combo_plan.get("combos", []),
            decision="emitted",
            surface="combo",
            runtime_surface="Combo.json",
            emitted_files=["Combo.json"],
        ),
    )
    _merge_emission_rows(
        index,
        _runtime_rows(
            rows=combo_plan.get("suppressed", []),
            decision="suppressed",
            surface="combo",
        ),
    )
    _merge_emission_rows(
        index,
        _runtime_rows(
            rows=global_values_authority_matrix.get("allowed_step1_overlays", []),
            decision="emitted",
            surface="globalvalues",
            runtime_surface="GlobalValues.json",
            emitted_files=["GlobalValues.json"],
        ),
    )
    _merge_emission_rows(
        index,
        _runtime_rows(
            rows=global_values_authority_matrix.get("blocked_until_runtime_evidence", []),
            decision="suppressed",
            surface="globalvalues",
        ),
    )
    return index


def _runtime_rows(
    *,
    rows: Any,
    decision: str,
    surface: str,
    runtime_surface: str | None = None,
    emitted_files: list[str] | None = None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in _rows(rows):
        claim_ids = _row_claim_ids(row)
        if not claim_ids:
            continue
        for claim_id in claim_ids:
            result.append(
                {
                    "claim_id": claim_id,
                    "decision": decision,
                    "surface": surface,
                    "runtime_surface": runtime_surface,
                    "emitted_files": list(emitted_files or []),
                    "suppressed_reason": None
                    if decision == "emitted"
                    else _normalized_suppression_reason(row),
                }
            )
    return result


def _cardid_runtime_rows(rows: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in _rows(rows):
        claim_ids = _row_claim_ids(row)
        if not claim_ids:
            continue
        card_id = str(row.get("card_id", "")).strip()
        meaningful = bool(row.get("meaningful_runtime_surface", True))
        if meaningful and card_id:
            runtime_surface = f"{card_id}.json"
            decision = "emitted"
            emitted_files = [runtime_surface]
            suppressed_reason = None
        else:
            runtime_surface = None
            decision = "suppressed"
            emitted_files = []
            suppressed_reason = "no_meaningful_runtime_surface"
        for claim_id in claim_ids:
            result.append(
                {
                    "claim_id": claim_id,
                    "decision": decision,
                    "surface": "cardid",
                    "runtime_surface": runtime_surface,
                    "emitted_files": emitted_files,
                    "suppressed_reason": suppressed_reason,
                }
            )
    return result


def _merge_emission_rows(
    index: dict[str, dict[str, Any]],
    rows: list[dict[str, Any]],
) -> None:
    for row in rows:
        claim_id = str(row.get("claim_id", "")).strip()
        if not claim_id:
            continue
        current = index.get(claim_id)
        if current is None:
            index[claim_id] = {
                "decision": str(row.get("decision", "")),
                "surface": row.get("surface"),
                "runtime_surface": row.get("runtime_surface"),
                "emitted_files": list(row.get("emitted_files", [])),
                "suppressed_reason": row.get("suppressed_reason"),
            }
            continue
        current_files = {
            str(item) for item in current.get("emitted_files", []) if str(item)
        }
        current_files.update(str(item) for item in row.get("emitted_files", []) if str(item))
        current["emitted_files"] = sorted(current_files)
        if row.get("decision") == "emitted":
            current["decision"] = "emitted"
            current["suppressed_reason"] = None
            if row.get("runtime_surface"):
                current["runtime_surface"] = row["runtime_surface"]
            if row.get("surface"):
                current["surface"] = row["surface"]
            continue
        if current.get("decision") != "emitted":
            reason = _more_specific_suppression_reason(
                str(current.get("suppressed_reason", "") or ""),
                str(row.get("suppressed_reason", "") or ""),
            )
            current["decision"] = "suppressed"
            current["suppressed_reason"] = reason
            if row.get("surface") and not current.get("surface"):
                current["surface"] = row["surface"]


def _more_specific_suppression_reason(current: str, incoming: str) -> str:
    priority = {
        "runtime_evidence_required": 0,
        "requires_runtime_evidence": 1,
        "source_evidence_required": 2,
        "surface_gate_rejected": 3,
        "builder_or_router_missing": 4,
    }
    if not current:
        return incoming or "suppressed"
    if not incoming:
        return current
    return min((current, incoming), key=lambda value: priority.get(value, 100))


def _normalized_suppression_reason(row: Mapping[str, Any]) -> str:
    reason = str(row.get("reason") or row.get("blocked_reason") or "suppressed")
    if reason == "requires_runtime_evidence":
        return "runtime_evidence_required"
    return reason


def _build_claim_lifecycle_rows(
    claim_rows: list[dict[str, Any]],
    *,
    runtime_emission_index: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    runtime_emission_index = runtime_emission_index or {}
    rows: list[dict[str, Any]] = []
    for index, claim_row in enumerate(claim_rows, start=1):
        claim_id = str(claim_row.get("claim_id") or f"claim_{index:04d}")
        emission = runtime_emission_index.get(claim_id, {})
        emitted_surfaces = [
            str(surface) for surface in claim_row.get("lowered_surfaces", []) if str(surface)
        ]
        surface = _lifecycle_surface(
            emission=emission,
            emitted_surfaces=emitted_surfaces,
            claim_row=claim_row,
        )
        gate = _lifecycle_gate(claim_row, surface)
        decision = str(emission.get("decision", ""))
        if not decision:
            decision = _fallback_builder_decision(gate)
        decision = _normalized_lifecycle_decision(decision, gate)
        suppressed_reason = emission.get("suppressed_reason")
        if decision == "emitted":
            suppressed_reason = None
        elif suppressed_reason is None:
            suppressed_reason = _fallback_suppressed_reason(gate, decision)
        runtime_surface = emission.get("runtime_surface")
        emitted_files = list(emission.get("emitted_files", []))
        rows.append(
            {
                "claim_id": claim_id,
                "claim_kind": str(claim_row.get("claim_kind", "")),
                "policy_lane": str(claim_row.get("policy_lane", "")),
                "surface_gate_decision": "allowed" if gate.get("allowed") else "rejected",
                "surface_gate_reason": str(gate.get("reason", "")),
                "builder_or_router_decision": decision,
                "runtime_surface": runtime_surface if runtime_surface else None,
                "emitted_files": emitted_files,
                "suppressed_reason": suppressed_reason,
                "first_missing_link": None
                if decision == "emitted"
                else _first_missing_link_for_suppression(str(suppressed_reason or "")),
                "operator_impact": _DIAGNOSTIC_OPERATOR_IMPACT,
            }
        )
    return rows


def _build_claim_lifecycle_rows_from_initial(
    initial_lifecycle_rows: Sequence[Mapping[str, Any]],
    *,
    claim_rows_by_id: Mapping[str, Mapping[str, Any]],
    runtime_emission_index: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    runtime_emission_index = runtime_emission_index or {}
    rows: list[dict[str, Any]] = []
    for index, initial_row in enumerate(initial_lifecycle_rows, start=1):
        if not isinstance(initial_row, Mapping):
            continue
        claim_id = str(initial_row.get("claim_id") or f"claim_{index:04d}")
        claim_row = claim_rows_by_id.get(claim_id, {})
        if not isinstance(claim_row, Mapping):
            claim_row = {}
        emission = runtime_emission_index.get(claim_id, {})
        if not isinstance(emission, Mapping):
            emission = {}
        emitted_surfaces = [
            str(surface)
            for surface in claim_row.get("lowered_surfaces", [])
            if str(surface)
        ]
        surface = _lifecycle_surface(
            emission=emission,
            emitted_surfaces=emitted_surfaces,
            claim_row=claim_row,
        )
        gate = _lifecycle_gate(claim_row, surface)
        quarantine_status = str(initial_row.get("quarantine_status") or "clear")
        quarantine_reason = str(initial_row.get("quarantine_reason") or "")
        runtime_eligibility = str(initial_row.get("runtime_eligibility") or "")
        policy_lane = str(
            initial_row.get("policy_lane") or claim_row.get("policy_lane", "")
        )
        if quarantine_status == "quarantined":
            decision = "suppressed"
            suppressed_reason = quarantine_reason or "source_claim_conflict"
            first_missing_link = "source_claim_conflict"
            final_runtime_effect = "suppressed_quarantined_claim"
        elif policy_lane == "runtime_evidence_required":
            decision = "suppressed"
            suppressed_reason = "runtime_evidence_required"
            first_missing_link = "runtime_evidence"
            final_runtime_effect = "suppressed_runtime_claim"
        elif policy_lane == "report_only":
            decision = "not_seen_by_builder"
            suppressed_reason = "claim_kind_policy"
            first_missing_link = "claim_kind_policy"
            final_runtime_effect = "not_emitted_by_builder_or_router"
        elif runtime_eligibility == "report_only":
            decision = "not_seen_by_builder"
            suppressed_reason = "source_eligibility"
            first_missing_link = "source_eligibility"
            final_runtime_effect = "not_emitted_by_builder_or_router"
        else:
            decision = str(emission.get("decision", ""))
            if not decision:
                decision = _fallback_builder_decision(gate)
            decision = _normalized_lifecycle_decision(decision, gate)
            suppressed_reason = emission.get("suppressed_reason")
            if decision == "emitted":
                suppressed_reason = None
                first_missing_link = None
                final_runtime_effect = "emitted_runtime_row"
            else:
                if suppressed_reason is None:
                    suppressed_reason = _fallback_suppressed_reason(gate, decision)
                first_missing_link = _first_missing_link_for_suppression(
                    str(suppressed_reason or "")
                )
                final_runtime_effect = (
                    "suppressed_runtime_claim"
                    if decision == "suppressed"
                    else "not_emitted_by_builder_or_router"
                )
        runtime_surface = emission.get("runtime_surface")
        emitted_files = list(emission.get("emitted_files", []))
        rows.append(
            {
                "claim_id": claim_id,
                "claim_kind": str(
                    initial_row.get("claim_kind") or claim_row.get("claim_kind", "")
                ),
                "policy_lane": policy_lane,
                "surface_gate_decision": "allowed" if gate.get("allowed") else "rejected",
                "surface_gate_reason": str(gate.get("reason", "")),
                "builder_or_router_decision": decision,
                "runtime_surface": runtime_surface if runtime_surface else None,
                "emitted_files": emitted_files,
                "suppressed_reason": suppressed_reason,
                "first_missing_link": first_missing_link,
                "operator_impact": _DIAGNOSTIC_OPERATOR_IMPACT,
                "quarantine_status": quarantine_status,
                "quarantine_reason": quarantine_reason,
                "runtime_eligibility": runtime_eligibility,
                "final_runtime_effect": final_runtime_effect,
            }
        )
    return rows


def _claim_lifecycle_decision_counts(
    claim_lifecycle_rows: list[Mapping[str, Any]],
) -> dict[str, int]:
    counts = Counter(
        str(row.get("builder_or_router_decision", ""))
        for row in claim_lifecycle_rows
        if isinstance(row, Mapping)
    )
    allowed_order = ("emitted", "not_seen_by_builder", "suppressed")
    return {decision: counts[decision] for decision in allowed_order if counts[decision]}


def _normalized_lifecycle_decision(
    decision: str,
    gate: Mapping[str, Any],
) -> str:
    if decision == "lowered":
        return "emitted"
    if decision in {"emitted", "suppressed", "not_seen_by_builder"}:
        return decision
    return _fallback_builder_decision(gate)


def _lifecycle_surface(
    *,
    emission: Mapping[str, Any],
    emitted_surfaces: list[str],
    claim_row: Mapping[str, Any],
) -> str:
    surface = str(emission.get("surface", "") or "")
    if surface:
        return surface
    if emitted_surfaces:
        return emitted_surfaces[0]
    surfaces = claim_row.get("surfaces", {})
    if isinstance(surfaces, Mapping):
        for name, row in surfaces.items():
            if isinstance(row, Mapping) and row.get("reason") == "requires_runtime_evidence":
                return str(name)
        for name, row in surfaces.items():
            if isinstance(row, Mapping) and row.get("allowed"):
                return str(name)
        for name in SURFACES:
            if name in surfaces:
                return name
    return ""


def _lifecycle_gate(claim_row: Mapping[str, Any], surface: str) -> Mapping[str, Any]:
    surfaces = claim_row.get("surfaces", {})
    if isinstance(surfaces, Mapping):
        gate = surfaces.get(surface)
        if isinstance(gate, Mapping):
            return gate
    return {"allowed": False, "reason": str(claim_row.get("first_reason", ""))}


def _fallback_builder_decision(gate: Mapping[str, Any]) -> str:
    if not bool(gate.get("allowed")):
        return "suppressed"
    return "not_seen_by_builder"


def _fallback_suppressed_reason(gate: Mapping[str, Any], decision: str) -> str:
    if decision == "not_seen_by_builder":
        return "builder_or_router_missing"
    reason = str(gate.get("reason", "") or "surface_gate_rejected")
    if reason == "requires_runtime_evidence":
        return "runtime_evidence_required"
    return reason


def _first_missing_link_for_suppression(reason: str | None) -> str | None:
    if not reason:
        return None
    lowered = reason.lower()
    if "runtime_evidence" in lowered or "requires_runtime_evidence" in lowered:
        return "runtime_evidence"
    if "source" in lowered or "guide" in lowered:
        return "source_evidence"
    if "surface_gate" in lowered:
        return "surface_gate"
    if "builder" in lowered or "router" in lowered:
        return "builder_or_router"
    return "runtime_surface"


def _claim_lowered_to_surface(
    *,
    claim_id: str,
    claim: Mapping[str, Any],
    surface: str,
    emitted_claim_ids: Mapping[str, set[str]],
    mulligan_plan: Mapping[str, Any],
    card_behavior_plan: Mapping[str, Any],
    combo_plan: Mapping[str, Any],
    allow_legacy_card_fallback: bool,
) -> bool:
    if _claim_reference_keys(claim_id, claim) & emitted_claim_ids.get(surface, set()):
        return True
    if surface == "globalvalues":
        return False
    if not allow_legacy_card_fallback:
        return False
    cards = set(_claim_cards(claim))
    if not cards:
        return False
    if surface == "mulligan":
        return any(str(row.get("card", "")) in cards for row in _rows(mulligan_plan.get("rules", [])))
    if surface == "cardid":
        return any(
            str(row.get("card_id", "")) in cards
            and bool(row.get("meaningful_runtime_surface", True))
            for row in _rows(card_behavior_plan.get("rows", []))
        )
    if surface == "combo":
        return any(
            bool(cards & set(_combo_cards(row)))
            for row in _rows(combo_plan.get("combos", []))
        )
    return False


def _claim_reference_keys(claim_id: str, claim: Mapping[str, Any]) -> set[str]:
    keys = {claim_id}
    explicit = str(claim.get("claim_id", "")).strip()
    if explicit:
        keys.add(explicit)
    refs = claim.get("source_refs", [])
    if isinstance(refs, str):
        refs = [refs]
    if isinstance(refs, list):
        keys.update(str(ref) for ref in refs if str(ref))
    return keys


def _ids_from_rows(rows: Any) -> set[str]:
    ids: set[str] = set()
    for row in _rows(rows):
        ids.update(_row_claim_ids(row))
    return ids


def _row_claim_ids(row: Mapping[str, Any]) -> set[str]:
    ids: set[str] = set()
    for key in ("claim_id", "source_claim_id"):
        value = row.get(key)
        if value:
            ids.add(str(value))
    for key in ("claim_ids", "source_claim_ids", "merged_claim_ids"):
        value = row.get(key, [])
        if isinstance(value, str):
            value = [value]
        if isinstance(value, list):
            ids.update(str(item) for item in value if str(item))
    claim_refs = row.get("claim_refs", [])
    if isinstance(claim_refs, str):
        claim_refs = [claim_refs]
    if isinstance(claim_refs, list):
        ids.update(str(item) for item in claim_refs if str(item))
    return ids


def _combo_cards(row: Mapping[str, Any]) -> list[str]:
    cards = row.get("cards", [])
    if isinstance(cards, str):
        cards = [cards]
    if isinstance(cards, list) and cards:
        return [str(card) for card in cards if str(card)]
    combo = str(row.get("combo", ""))
    if ">>" in combo:
        return [part.strip() for part in combo.split(">>") if part.strip()]
    return []


def _rows(rows: Any) -> list[Mapping[str, Any]]:
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, Mapping)]


def _card_roles_from_readiness(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    cards = report.get("cards", {})
    if not isinstance(cards, Mapping):
        return {}
    return {
        str(card_id): row
        for card_id, row in cards.items()
        if isinstance(row, Mapping)
    }


def _card_rows(
    *,
    deck_identity: Mapping[str, Any],
    config_readiness_report: Mapping[str, Any],
    card_claim_lanes: Mapping[str, Counter[str]],
) -> dict[str, dict[str, Any]]:
    readiness_cards = config_readiness_report.get("cards", {})
    if not isinstance(readiness_cards, Mapping):
        readiness_cards = {}
    deck_cards = _deck_cards(deck_identity)
    all_card_ids = sorted({*deck_cards, *[str(card_id) for card_id in readiness_cards]})
    rows: dict[str, dict[str, Any]] = {}
    for card_id in all_card_ids:
        readiness = readiness_cards.get(card_id, {})
        if not isinstance(readiness, Mapping):
            readiness = {}
        deck_card = deck_cards.get(card_id, {})
        rows[card_id] = {
            "card_id": card_id,
            "name": str(readiness.get("name") or deck_card.get("name") or ""),
            "roles": list(readiness.get("roles", []))
            if isinstance(readiness.get("roles", []), list)
            else [],
            "runtime_surfaces": list(readiness.get("runtime_surfaces", []))
            if isinstance(readiness.get("runtime_surfaces", []), list)
            else [],
            "readiness_lane": str(readiness.get("readiness_lane", "")),
            "first_missing_link": str(readiness.get("first_missing_link", "")),
            "claim_lanes": dict(sorted(card_claim_lanes.get(card_id, Counter()).items())),
        }
    return rows


def _deck_cards(deck_identity: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    cards = deck_identity.get("cards", [])
    if not isinstance(cards, list):
        return {}
    result: dict[str, Mapping[str, Any]] = {}
    for row in cards:
        if not isinstance(row, Mapping):
            continue
        card_id = str(row.get("card_id", "")).strip()
        if card_id:
            result[card_id] = row
    return result


def _summary(
    *,
    claim_rows: Mapping[str, Mapping[str, Any]],
    card_rows: Mapping[str, Mapping[str, Any]],
    policy_lane_counts: Counter[str],
) -> dict[str, Any]:
    claim_lanes = Counter(str(row.get("lane", "")) for row in claim_rows.values())
    return {
        "claims_total": len(claim_rows),
        "runtime_lowered_claims": claim_lanes["runtime_lowered"],
        "suppressed_claims": claim_lanes["suppressed_with_reason"],
        "runtime_evidence_required_claims": claim_lanes["runtime_evidence_required"],
        "report_only_claims": claim_lanes["report_only"],
        "unsupported_or_unmapped_claims": claim_lanes["unsupported_or_unmapped"],
        "claim_kind_policy_counts": dict(sorted(policy_lane_counts.items())),
        "cards_total": len(card_rows),
        "cards_with_missing_links": sum(
            1
            for row in card_rows.values()
            if str(row.get("first_missing_link", "")).lower() not in {"", "none", "closed"}
        ),
        "cards_with_runtime_lowered_claims": sum(
            1
            for row in card_rows.values()
            if _int(row.get("claim_lanes", {}).get("runtime_lowered", 0)) > 0
        ),
        "cards_with_suppressed_claims": sum(
            1
            for row in card_rows.values()
            if _int(row.get("claim_lanes", {}).get("suppressed_with_reason", 0)) > 0
        ),
    }


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _escape_table(value: Any) -> str:
    return str(value).replace("|", "\\|")
