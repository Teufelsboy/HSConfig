from __future__ import annotations

from typing import Any

_BLOCKED_NORMAL_PATH_SURFACES = {"Presume.json", "Concede.json"}


def build_strong_promotion_report(
    *,
    deck_name: str,
    fixture_stage: str,
    operator_summary: dict[str, Any],
    source_claim_gap_report: dict[str, Any],
) -> dict[str, Any]:
    semantic_blockers = [
        *list(operator_summary.get("semantic_blockers", [])),
        *_default_only_runtime_surface_blockers(operator_summary),
        *_normal_path_surface_blockers(operator_summary),
    ]
    source_gap_summary = source_claim_gap_report.get("summary", {})
    if not isinstance(source_gap_summary, dict):
        source_gap_summary = {}
    first_missing_chain = _first_missing_chain(source_claim_gap_report)
    source_gaps_closed = (
        int(source_gap_summary.get("blocked_cards", 0)) == 0
        and int(source_gap_summary.get("deck_surface_gap_count", 0)) == 0
        and first_missing_chain is None
    )
    promotion_ready = (
        operator_summary.get("technical_status") == "VALID_PACKAGE"
        and operator_summary.get("semantic_status") == "SOURCE_BACKED_STRONG"
        and operator_summary.get("next_action") == "READY_TO_APPLY_OR_HANDOFF"
        and not semantic_blockers
        and source_gaps_closed
    )
    operator_next_action = str(operator_summary.get("next_action", ""))
    first_missing_source_action = _first_missing_source_action(
        promotion_ready=promotion_ready,
        semantic_blockers=semantic_blockers,
        first_missing_chain=first_missing_chain,
    )
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "fixture_stage": fixture_stage,
        "promotion_ready": promotion_ready,
        "verdict": "SOURCE_BACKED_STRONG_CONFIRMED" if promotion_ready else "PROMOTION_BLOCKED",
        "static_contract_status": _static_contract_status(
            operator_summary=operator_summary,
            source_gaps_closed=source_gaps_closed,
            semantic_blockers=semantic_blockers,
        ),
        "runtime_lowering_status": _runtime_lowering_status(
            promotion_ready=promotion_ready,
            operator_summary=operator_summary,
        ),
        "first_missing_source_action": first_missing_source_action,
        "source_informed_apply_readiness": operator_summary.get(
            "source_informed_apply_readiness",
            {"status": "not_applicable"},
        ),
        "next_action": _report_next_action(
            promotion_ready=promotion_ready,
            operator_summary=operator_summary,
            first_missing_chain=first_missing_chain,
        ),
        "operator_status": {
            "technical_status": operator_summary.get("technical_status"),
            "semantic_status": operator_summary.get("semantic_status"),
            "operator_next_action": operator_next_action,
        },
        "semantic_blockers": semantic_blockers,
        "first_missing_chain": first_missing_chain,
    }


def _static_contract_status(
    *,
    operator_summary: dict[str, Any],
    source_gaps_closed: bool,
    semantic_blockers: list[dict[str, Any]],
) -> str:
    if (
        operator_summary.get("technical_status") == "VALID_PACKAGE"
        and operator_summary.get("semantic_status") == "SOURCE_BACKED_STRONG"
        and source_gaps_closed
        and not semantic_blockers
    ):
        return "SOURCE_BACKED_STRONG"
    if operator_summary.get("technical_status") == "VALID_PACKAGE":
        return "SOURCE_BACKED_PARTIAL"
    return str(operator_summary.get("semantic_status", "INVALID_PACKAGE"))


def _runtime_lowering_status(
    *,
    promotion_ready: bool,
    operator_summary: dict[str, Any],
) -> str:
    if promotion_ready:
        return "NO_DEFAULT_ONLY_RUNTIME_SURFACES"
    if operator_summary.get("technical_status") != "VALID_PACKAGE":
        return "NOT_LOAD_SAFE"
    return "LOAD_SAFE_WITH_POLICY_OR_REVIEW_ROWS"


def _first_missing_source_action(
    *,
    promotion_ready: bool,
    semantic_blockers: list[dict[str, Any]],
    first_missing_chain: dict[str, Any] | None,
) -> str:
    if promotion_ready:
        return "none"
    if first_missing_chain is not None:
        action = str(first_missing_chain.get("next_action") or "")
        if action:
            return action
        missing_link = str(first_missing_chain.get("first_missing_link") or "")
        return _source_action_for_missing_link(missing_link)
    for blocker in semantic_blockers:
        code = str(blocker.get("code") or blocker.get("reason") or "")
        action = _source_action_for_blocker(code)
        if action != "close_first_missing_chain":
            return action
    return "close_first_missing_chain"


def _source_action_for_blocker(code: str) -> str:
    if code == "policy_claim_not_strong_evidence":
        return "add_explicit_mulligan_source"
    if code == "default_only_surface_not_strong_evidence":
        return "replace_default_only_runtime_surface_with_source_or_policy_claim"
    if code == "snippet_only_source_not_strong_evidence":
        return "replace_snippet_only_source_with_accessible_source"
    if code == "runtime_row_missing_source_claim":
        return "add_runtime_source_claim"
    if code == "static_claim_not_runtime_observed":
        return "collect_runtime_evidence_or_mark_contract_only"
    if code == "cards_need_mulligan_claims":
        return "add_explicit_mulligan_source"
    if code == "cards_need_runtime_surface":
        return "add_runtime_lowerable_claim_or_router_support"
    if code == "cards_need_guide_claims":
        return "add_card_specific_source_claim"
    return "close_first_missing_chain"


def _source_action_for_missing_link(missing_link: str) -> str:
    if missing_link == "needs_mulligan_claim":
        return "add_explicit_mulligan_source"
    if missing_link == "needs_runtime_surface":
        return "add_runtime_lowerable_claim_or_router_support"
    if missing_link == "needs_guide_claim":
        return "add_card_specific_source_claim"
    if missing_link == "runtime_evidence":
        return "collect_runtime_evidence_or_mark_contract_only"
    return "close_first_missing_chain"


def _normal_path_surface_blockers(operator_summary: dict[str, Any]) -> list[dict[str, str]]:
    generated_files = operator_summary.get("generated_files", [])
    if not isinstance(generated_files, list):
        return []
    blockers: list[dict[str, str]] = []
    for path in generated_files:
        normalized_path = str(path).replace("\\", "/")
        filename = normalized_path.rsplit("/", 1)[-1]
        if filename not in _BLOCKED_NORMAL_PATH_SURFACES:
            continue
        blockers.append(
            {
                "reason": "normal_path_optional_surface_present",
                "generated_file": normalized_path,
            }
        )
    return blockers


def _default_only_runtime_surface_blockers(
    operator_summary: dict[str, Any],
) -> list[dict[str, str]]:
    surfaces = operator_summary.get("default_only_runtime_surfaces", [])
    if not isinstance(surfaces, list):
        return []
    existing_blocked_surfaces = {
        str(row.get("surface"))
        for row in operator_summary.get("semantic_blockers", [])
        if isinstance(row, dict)
        and str(row.get("reason") or row.get("code"))
        == "default_only_surface_not_strong_evidence"
    }
    blockers: list[dict[str, str]] = []
    for surface in sorted(str(item) for item in surfaces if str(item)):
        if surface in existing_blocked_surfaces:
            continue
        blockers.append(
            {
                "reason": "default_only_surface_not_strong_evidence",
                "surface": surface,
            }
        )
    return blockers


def _report_next_action(
    *,
    promotion_ready: bool,
    operator_summary: dict[str, Any],
    first_missing_chain: dict[str, Any] | None,
) -> str:
    if promotion_ready:
        return "fixture_can_be_core_source_backed"
    if operator_summary.get("technical_status") != "VALID_PACKAGE":
        return str(operator_summary.get("next_action", ""))
    readiness = operator_summary.get("source_informed_apply_readiness")
    if (
        operator_summary.get("semantic_status") != "SOURCE_BACKED_STRONG"
        and isinstance(readiness, dict)
        and readiness.get("status") == "ready"
    ):
        return "source_informed_apply_ready_but_not_strong"
    return "close_first_missing_chain"


def _first_missing_chain(source_claim_gap_report: dict[str, Any]) -> dict[str, Any] | None:
    summary = source_claim_gap_report.get("summary", {})
    if isinstance(summary, dict):
        canonical = summary.get("first_missing_chain")
        if isinstance(canonical, dict):
            return dict(canonical)

    cards = source_claim_gap_report.get("cards", {})
    if not isinstance(cards, dict):
        return None
    for card_id, row in sorted(cards.items()):
        if not isinstance(row, dict):
            continue
        if row.get("first_missing_link") == "none":
            continue
        return {
            "card_id": str(card_id),
            "first_missing_link": str(row.get("first_missing_link", "")),
            "recommended_source_claim_kind": str(row.get("recommended_source_claim_kind", "")),
            "next_action": str(row.get("next_action", "")),
        }
    return None
