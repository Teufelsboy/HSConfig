from __future__ import annotations

from collections import Counter
from typing import Any, Mapping

from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces
from hsconfig.combo_plan import build_combo_plan
from hsconfig.globalvalues_authority import build_globalvalues_authority_matrix
from hsconfig.linked_entity_supplement import curated_links_for
from hsconfig.mulligan_plan import build_mulligan_plan
from hsconfig.source_acquisition_provenance import (
    FIXTURE_MAP,
    build_acquisition_provenance,
)
from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_document_builder import build_source_document_bundle
from hsconfig.source_document_model import (
    SUPPORTED_ATOMIC_CLAIM_KINDS,
    surface_gate_decision,
)


SURFACES = ("mulligan", "globalvalues", "cardid", "combo")
OPERATOR_GATE_IMPACT = "diagnostic_only"
_CONFORMANCE_DECK_FINGERPRINT = "conformance-deck-fingerprint"
_EXPECTED_DIAGNOSTIC_GATE_REASONS = frozenset(
    {"strategic_provenance_not_live_verified"}
)

_BUILDER_ROUTER_EXPECTATIONS = {
    "archetype": {"surface": None, "runner": "not_seen_by_builder", "outcome": "not_seen_by_builder"},
    "mulligan_keep": {"surface": "mulligan", "runner": "build_mulligan_plan", "outcome": "suppressed"},
    "mulligan_discard": {"surface": "mulligan", "runner": "build_mulligan_plan", "outcome": "suppressed"},
    "card_role": {"surface": "cardid", "runner": "route_card_behavior_surfaces", "outcome": "emitted"},
    "targeting_rule": {"surface": "cardid", "runner": "route_card_behavior_surfaces", "outcome": "emitted"},
    "combo_sequence": {"surface": "combo", "runner": "build_combo_plan", "outcome": "suppressed"},
    "gameplan_posture": {"surface": "globalvalues", "runner": "build_globalvalues_authority_matrix", "outcome": "suppressed"},
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
    builder_prerequisite_gaps = _builder_prerequisite_gaps(rows)
    unexpected_contract_drifts = [
        *policy_gate_mismatches,
        *builder_expectation_mismatches,
    ]
    pipeline_attention_count = len(unexpected_contract_drifts) + len(
        builder_prerequisite_gaps
    )
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
            "unexpected_contract_drift_count": len(unexpected_contract_drifts),
            "unexpected_contract_drifts": unexpected_contract_drifts,
            "builder_prerequisite_gap_count": len(builder_prerequisite_gaps),
            "builder_prerequisite_gaps": builder_prerequisite_gaps,
            "pipeline_attention_count": pipeline_attention_count,
            "surface_gate_builder_mismatch_count": len(builder_prerequisite_gaps),
            "surface_gate_builder_mismatches": builder_prerequisite_gaps,
            "pipeline_mismatch_count": pipeline_attention_count,
        },
        "claim_kind_rows": rows,
        "contract_spine_rows": _contract_spine_rows(rows),
        "start_of_game_mulligan_suppression": _start_of_game_suppression_row(),
    }


def render_source_contract_conformance_markdown(snapshot: Mapping[str, Any]) -> str:
    """Render the conformance snapshot as compact operator/developer Markdown."""
    rows = snapshot.get("claim_kind_rows", {})
    if not isinstance(rows, Mapping):
        rows = {}
    summary = snapshot.get("summary", {})
    if not isinstance(summary, Mapping):
        summary = {}
    spine_rows = snapshot.get("contract_spine_rows", [])
    if not isinstance(spine_rows, list):
        spine_rows = []
    lines = [
        "# Source Contract Conformance Snapshot",
        "",
        "Diagnostic only. operator_summary.json remains the apply authority.",
        "",
        "## Summary",
        "",
        "- Unexpected contract drift: {count}".format(
            count=summary.get("unexpected_contract_drift_count", 0)
        ),
        "- Builder prerequisite gaps: {count}".format(
            count=summary.get("builder_prerequisite_gap_count", 0)
        ),
        "- Pipeline attention rows: {count}".format(
            count=summary.get("pipeline_attention_count", 0)
        ),
        "",
        "## Contract Spine",
        "",
        "| Claim Kind | Policy Lane | Surface Gate | Builder Status | Final Runtime Effect | Operator Gate Impact |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in spine_rows:
        if not isinstance(row, Mapping):
            continue
        lines.append(
            "| {claim} | {lane} | {gate} | {builder} | {effect} | {impact} |".format(
                claim=_escape_table(row.get("claim_kind", "")),
                lane=_escape_table(row.get("policy_lane", "")),
                gate=_escape_table(row.get("surface_gate_status", "")),
                builder=_escape_table(row.get("builder_status", "")),
                effect=_escape_table(row.get("final_runtime_effect", "")),
                impact=_escape_table(row.get("operator_gate_impact", "")),
            )
        )
    lines.extend(
        [
            "",
            "## Claim Kind Surface Matrix",
            "",
        "| Claim Kind | Policy Lane | Allowed Surfaces | Gate Summary |",
        "| --- | --- | --- | --- |",
        ]
    )
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
    gaps = summary.get("builder_prerequisite_gaps", [])
    lines.extend(
        [
            "",
            "## Builder Prerequisite Gaps",
            "",
            "| Claim Kind | Surface | Builder Outcome | Reason | Operator Meaning |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    if isinstance(gaps, list) and gaps:
        for gap in gaps:
            if not isinstance(gap, Mapping):
                continue
            lines.append(
                "| {claim} | {surface} | {outcome} | {reason} | {meaning} |".format(
                    claim=_escape_table(gap.get("claim_kind", "")),
                    surface=_escape_table(gap.get("surface", "")),
                    outcome=_escape_table(gap.get("builder_outcome", "")),
                    reason=_escape_table(gap.get("reason", "")),
                    meaning=_escape_table(gap.get("operator_meaning", "")),
                )
            )
    else:
        lines.append("| none | none | none | none | none |")
    lines.extend(
        [
            "",
            "## Claim Lifecycle",
            "",
            "| Claim Kind | Policy Lane | Surface Gate | Builder Status | Final Runtime Effect |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for claim_kind, row in sorted(rows.items()):
        if not isinstance(row, Mapping):
            continue
        lifecycle = row.get("lifecycle", {})
        if not isinstance(lifecycle, Mapping):
            continue
        lines.append(
            "| {claim} | {lane} | {gate} | {builder} | {effect} |".format(
                claim=_escape_table(claim_kind),
                lane=_escape_table(lifecycle.get("policy_lane", "")),
                gate=_escape_table(lifecycle.get("surface_gate_status", "")),
                builder=_escape_table(lifecycle.get("builder_status", "")),
                effect=_escape_table(lifecycle.get("final_runtime_effect", "")),
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
    if claim_kind in {"mulligan_keep", "mulligan_discard"}:
        bundle = _fixture_mulligan_bundle(claim_kind)
        claim = bundle["claims"][0]
        context["deck_identity"] = {
            "deck_fingerprint": _CONFORMANCE_DECK_FINGERPRINT,
        }
        context["verified_source_receipts"] = bundle[
            "canonical_source_receipts"
        ]
    elif claim_kind == "gameplan_posture":
        bundle = _fixture_gameplan_posture_bundle()
        claim = bundle["claims"][0]
        context["deck_identity"] = {
            "deck_fingerprint": _CONFORMANCE_DECK_FINGERPRINT,
        }
        context["verified_source_receipts"] = bundle[
            "canonical_source_receipts"
        ]
    elif claim_kind == "combo_sequence":
        bundle = _fixture_combo_bundle()
        claim = bundle["claims"][0]
        context["deck_identity"] = {
            "deck_fingerprint": _CONFORMANCE_DECK_FINGERPRINT,
        }
        context["verified_source_receipts"] = bundle[
            "canonical_source_receipts"
        ]
    gates = {
        surface: _decision_row(surface_gate_decision(claim, surface, context=context))
        for surface in SURFACES
    }
    row = {
        "claim_kind": claim_kind,
        "policy_lane": str(policy_row.get("lane", "")),
        "semantic_lane": str(policy_row.get("semantic_lane", policy_row.get("lane", ""))),
        "allowed_surfaces": list(policy_row.get("allowed_surfaces", ())),
        "required_fields": [
            str(field) for field in policy_row.get("required_fields", ())
        ],
        "runtime_lowerable": bool(policy_row.get("runtime_lowerable", False)),
        "default_suppression_reason": str(
            policy_row.get("default_suppression_reason", "")
        ),
        "operator_gate_impact": str(
            policy_row.get("operator_gate_impact", OPERATOR_GATE_IMPACT)
        ),
        "operator_meaning": str(policy_row.get("operator_meaning", "")),
        "surface_gates": gates,
        "builder_router": _builder_router_expectation(claim_kind),
    }
    row["lifecycle"] = _claim_lifecycle(row)
    return row


def _claim_lifecycle(row: Mapping[str, Any]) -> dict[str, Any]:
    allowed_surfaces = [str(surface) for surface in row.get("allowed_surfaces", [])]
    return {
        "policy_lane": str(row.get("policy_lane", "")),
        "allowed_surfaces": allowed_surfaces,
        "surface_gate_status": _surface_gate_status(row),
        "builder_status": _builder_status(row.get("builder_router", {})),
        "final_runtime_effect": _final_runtime_effect(row),
        "operator_meaning": str(row.get("operator_meaning", "")),
    }


def _contract_spine_rows(rows: Mapping[str, Any]) -> list[dict[str, Any]]:
    spine: list[dict[str, Any]] = []
    for claim_kind, row in sorted(rows.items()):
        if not isinstance(row, Mapping):
            continue
        lifecycle = row.get("lifecycle", {})
        if not isinstance(lifecycle, Mapping):
            lifecycle = {}
        spine.append(
            {
                "claim_kind": str(claim_kind),
                "policy_lane": str(lifecycle.get("policy_lane", "")),
                "semantic_lane": str(
                    row.get("semantic_lane", lifecycle.get("policy_lane", ""))
                ),
                "allowed_surfaces": [
                    str(surface) for surface in lifecycle.get("allowed_surfaces", [])
                ],
                "required_fields": [
                    str(field) for field in row.get("required_fields", [])
                ],
                "runtime_lowerable": bool(row.get("runtime_lowerable", False)),
                "surface_gate_status": str(lifecycle.get("surface_gate_status", "")),
                "builder_status": str(lifecycle.get("builder_status", "")),
                "final_runtime_effect": str(lifecycle.get("final_runtime_effect", "")),
                "default_suppression_reason": str(
                    row.get("default_suppression_reason", "")
                ),
                "operator_gate_impact": OPERATOR_GATE_IMPACT,
            }
        )
    return spine


def _surface_gate_status(row: Mapping[str, Any]) -> str:
    allowed_surfaces = [str(surface) for surface in row.get("allowed_surfaces", [])]
    if not allowed_surfaces:
        return "no_allowed_surface"
    gates = row.get("surface_gates", {})
    if not isinstance(gates, Mapping):
        return "missing_surface_gates"
    statuses = []
    for surface in allowed_surfaces:
        gate = gates.get(surface, {})
        if not isinstance(gate, Mapping):
            statuses.append(f"{surface}:missing")
            continue
        statuses.append(f"{surface}:{gate.get('decision', '')}")
    return "; ".join(statuses)


def _builder_status(builder_router: Any) -> str:
    if not isinstance(builder_router, Mapping):
        return "no_builder_router"
    runner = str(builder_router.get("runner", ""))
    complete = builder_router.get("complete", {})
    if not isinstance(complete, Mapping):
        return f"{runner}:missing_complete_exemplar"
    status = f"{runner}:{complete.get('outcome', '')}"
    incomplete = builder_router.get("incomplete")
    if isinstance(incomplete, Mapping):
        status = (
            f"{status}; incomplete:{incomplete.get('outcome', '')}:"
            f"{incomplete.get('reason', '')}"
        )
    elif complete.get("reason") and complete.get("reason") != complete.get("outcome"):
        status = f"{status}:{complete.get('reason')}"
    return status


def _final_runtime_effect(row: Mapping[str, Any]) -> str:
    claim_kind = str(row.get("claim_kind", ""))
    builder_router = row.get("builder_router", {})
    if claim_kind == "globalvalue_numeric_tuning":
        return "suppressed_until_runtime_evidence"
    if claim_kind in {"archetype", "tech_slot", "replacement_option"}:
        return "report_only_no_runtime_row"
    if not isinstance(builder_router, Mapping):
        return "unknown_runtime_effect"
    surface = builder_router.get("surface")
    complete = builder_router.get("complete", {})
    if not isinstance(complete, Mapping):
        return "unknown_runtime_effect"
    if complete.get("outcome") != "emitted":
        return f"suppressed:{complete.get('reason', '')}"
    if surface == "mulligan":
        return "emits_mulligan_runtime_row"
    if surface == "globalvalues":
        return "emits_globalvalues_posture_overlay"
    if surface == "cardid":
        return "emits_cardid_runtime_row"
    if surface == "combo":
        return "emits_combo_runtime_row"
    return "report_only_no_runtime_row"


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
        return _fixture_combo_bundle(incomplete=incomplete)["claims"][0]
    if claim_kind == "gameplan_posture":
        return _fixture_gameplan_posture_bundle()["claims"][0]
    if claim_kind in {"mulligan_keep", "mulligan_discard"}:
        return _fixture_mulligan_bundle(claim_kind)["claims"][0]
    if claim_kind == "globalvalue_numeric_tuning":
        return {**claim, "cards": [], "key": "LowHpBoardValuePenalty"}
    if claim_kind == "hero_power_transform":
        return {**claim, "cards": ["SW_448"]}
    if claim_kind == "card_role":
        return {**claim, "runtime_block": "InHandBonus"}
    if claim_kind == "targeting_rule":
        return {
            **claim,
            "stance": "prefer_enemy_hero",
            "target_scope": "enemy_hero",
            "runtime_block": "BeforeBattlecryTargetBonus",
        }
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
        fixture_bundle = _fixture_combo_bundle(
            incomplete=len(claim.get("cards", [])) < 2
        )
        plan = build_combo_plan(
            deck_cards={str(card) for card in claim.get("cards", [])},
            claims=[claim],
            deck_identity={
                "deck_fingerprint": _CONFORMANCE_DECK_FINGERPRINT,
            },
            verified_source_receipts=fixture_bundle["canonical_source_receipts"],
        )
        if plan["combos"]:
            return {"outcome": "emitted", "reason": "emitted"}
        return _suppressed_result(plan["suppressed"])
    if runner == "build_mulligan_plan":
        fixture_bundle = _fixture_mulligan_bundle(claim_kind)
        plan = build_mulligan_plan(
            deck_name="Conformance",
            claims=[claim],
            card_roles={"CARD_001": {"roles": ["mulligan_anchor"]}},
            deck_identity={
                "deck_fingerprint": _CONFORMANCE_DECK_FINGERPRINT,
            },
            verified_source_receipts=fixture_bundle[
                "canonical_source_receipts"
            ],
        )
        if any(row.get("source_claim_ids") == [claim["claim_id"]] for row in plan["rules"]):
            return {"outcome": "emitted", "reason": "emitted"}
        return _suppressed_result(plan["suppressed_rules"])
    if runner == "build_globalvalues_authority_matrix":
        fixture_source_receipts = (
            _fixture_gameplan_posture_bundle()["globalvalues_source_receipts"]
            if claim_kind == "gameplan_posture"
            else []
        )
        plan = build_globalvalues_authority_matrix(
            aggression_profile="baseline",
            claims=[claim],
            deck_identity={
                "deck_fingerprint": _CONFORMANCE_DECK_FINGERPRINT,
            },
            verified_source_receipts=fixture_source_receipts,
        )
        if any(claim["claim_id"] in row.get("claim_refs", []) for row in plan["allowed_step1_overlays"]):
            return {"outcome": "emitted", "reason": "emitted"}
        return _suppressed_result(plan["blocked_until_runtime_evidence"])
    if runner == "route_card_behavior_surfaces":
        identity_links: dict[str, Any] = {
            "CARD_001": [{"card_id": "OPTION_001"}],
        }
        if claim_kind == "hero_power_transform":
            identity_links = {
                "SW_448": {
                    str(link["link_kind"]): str(link["card_id"])
                    for link in curated_links_for("SW_448")
                },
            }
        plan = route_card_behavior_surfaces(
            [claim],
            identity_links=identity_links,
        )
        if any(row.get("claim_id") == claim["claim_id"] for row in plan["rows"]):
            return {"outcome": "emitted", "reason": "emitted"}
        return _suppressed_result(plan["suppressed"])
    raise RuntimeError(f"Unsupported conformance runner: {runner}")


def _fixture_gameplan_posture_bundle() -> dict[str, Any]:
    deck_identity = {
        "deck_name": "Conformance",
        "deck_fingerprint": _CONFORMANCE_DECK_FINGERPRINT,
        "cards": [{"card_id": "CARD_001", "name": "Conformance Card", "count": 1}],
    }
    return build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=[
            {
                "source_url": "https://example.invalid/conformance-guide",
                "source_title": "Conformance exact-deck guide",
                "source_family": "guide",
                "source_type": "public_guide",
                "retrieved_at": "2026-07-26T00:00:00Z",
                "acquisition_provenance": (
                    _conformance_fixture_provenance()
                ),
                "source_visibility": "full_text",
                "source_lane": "deck_matched_public_guide",
                "deck_match_scope": "exact_deck_matched",
                "deck_match": {
                    "exact_deck_evidence": {
                        "candidate_count": 1,
                        "decoded_candidate_count": 1,
                        "matched": True,
                        "matched_deck_fingerprint": _CONFORMANCE_DECK_FINGERPRINT,
                        "candidate_deck_code_hashes": ["sha256:conformance-source"],
                    }
                },
                "claims": [
                    {
                        "claim_id": "conformance_gameplan_posture",
                        "claim_kind": "gameplan_posture",
                        "cards": ["CARD_001"],
                        "scope": "deck",
                        "stance": "aggro_burn",
                        "evidence_text_short": "Use the aggro burn posture.",
                        "source_confidence": "high",
                        "promotion_eligible": True,
                    }
                ],
            }
        ],
        current_date="2026-07-26",
    )


def _fixture_combo_bundle(*, incomplete: bool = False) -> dict[str, Any]:
    cards = ["CARD_001"] if incomplete else ["CARD_001", "CARD_002"]
    deck_identity = {
        "deck_name": "Conformance",
        "deck_fingerprint": _CONFORMANCE_DECK_FINGERPRINT,
        "cards": [
            {"card_id": card_id, "name": card_id, "count": 1}
            for card_id in cards
        ],
    }
    return build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=[
            {
                "source_url": "https://example.invalid/conformance-combo-guide",
                "source_title": "Conformance exact-deck Combo guide",
                "source_family": "guide",
                "source_type": "public_guide",
                "retrieved_at": "2026-07-26T00:00:00Z",
                "acquisition_provenance": (
                    _conformance_fixture_provenance()
                ),
                "source_visibility": "full_text",
                "source_lane": "deck_matched_public_guide",
                "deck_match_scope": "exact_deck_matched",
                "deck_match": {
                    "exact_deck_evidence": {
                        "candidate_count": 1,
                        "decoded_candidate_count": 1,
                        "matched": True,
                        "matched_deck_fingerprint": _CONFORMANCE_DECK_FINGERPRINT,
                        "candidate_deck_code_hashes": ["sha256:conformance-combo-source"],
                    }
                },
                "claims": [
                    {
                        "claim_id": "conformance_combo_sequence",
                        "claim_kind": "combo_sequence",
                        "cards": cards,
                        "sequence": cards,
                        "scope": "card",
                        "stance": "ordered_combo_sequence",
                        "timing_kind": "same_turn",
                        "operator": ">>",
                        "values": ["6"] * len(cards),
                        "evidence_text_short": "Play CARD_001 before CARD_002.",
                        "source_confidence": "high",
                        "promotion_eligible": True,
                    }
                ],
            }
        ],
        current_date="2026-07-26",
    )


def _fixture_mulligan_bundle(claim_kind: str) -> dict[str, Any]:
    deck_identity = {
        "deck_name": "Conformance",
        "deck_fingerprint": _CONFORMANCE_DECK_FINGERPRINT,
        "cards": [
            {"card_id": "CARD_001", "name": "Conformance Card", "count": 1}
        ],
    }
    return build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=[
            {
                "source_url": "https://example.invalid/conformance-mulligan-guide",
                "source_title": "Conformance exact-deck Mulligan guide",
                "source_family": "guide",
                "source_type": "public_guide",
                "retrieved_at": "2026-07-26T00:00:00Z",
                "acquisition_provenance": (
                    _conformance_fixture_provenance()
                ),
                "source_visibility": "full_text",
                "source_lane": "deck_matched_public_guide",
                "deck_match_scope": "exact_deck_matched",
                "deck_match": {
                    "exact_deck_evidence": {
                        "candidate_count": 1,
                        "decoded_candidate_count": 1,
                        "matched": True,
                        "matched_deck_fingerprint": (
                            _CONFORMANCE_DECK_FINGERPRINT
                        ),
                        "candidate_deck_code_hashes": [
                            "sha256:conformance-mulligan-source"
                        ],
                    }
                },
                "claims": [
                    {
                        "claim_id": f"conformance_{claim_kind}",
                        "claim_kind": claim_kind,
                        "cards": ["CARD_001"],
                        "scope": "card",
                        "stance": (
                            "keep"
                            if claim_kind == "mulligan_keep"
                            else "discard"
                        ),
                        "evidence_text_short": (
                            "Keep the card in the opening hand."
                            if claim_kind == "mulligan_keep"
                            else "Discard the card from the opening hand."
                        ),
                        "source_confidence": "high",
                        "promotion_eligible": True,
                    }
                ],
            }
        ],
        current_date="2026-07-26",
    )


def _conformance_fixture_provenance() -> dict[str, str]:
    return build_acquisition_provenance(
        mode=FIXTURE_MAP,
        content=b"Conformance fixture source response.",
    )


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
            if (
                policy_allowed
                and gate.get("reason") in _EXPECTED_DIAGNOSTIC_GATE_REASONS
            ):
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


def _builder_prerequisite_gaps(rows: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Expose expected builder prerequisites beyond an allowed surface gate."""
    gaps = []
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
            gaps.append(
                {
                    "claim_kind": claim_kind,
                    "surface": surface,
                    "builder_outcome": exemplar.get("outcome", ""),
                    "reason": exemplar.get("reason", ""),
                    "operator_meaning": (
                        "Surface gate allows this claim kind, but the builder still needs "
                        "a complete sequence before runtime JSON can be emitted."
                    ),
                }
            )
    return gaps


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
