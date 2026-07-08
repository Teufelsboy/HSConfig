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
    surface_blockers = _normal_path_surface_blockers(operator_summary)
    semantic_blockers = [
        *list(operator_summary.get("semantic_blockers", [])),
        *surface_blockers,
    ]
    promotion_ready = (
        operator_summary.get("technical_status") == "VALID_PACKAGE"
        and operator_summary.get("semantic_status") == "SOURCE_BACKED_STRONG"
        and operator_summary.get("next_action") == "READY_TO_APPLY_OR_HANDOFF"
        and not semantic_blockers
        and int(source_claim_gap_report.get("summary", {}).get("blocked_cards", 0)) == 0
    )
    first_missing_chain = _first_missing_chain(source_claim_gap_report)
    operator_next_action = str(operator_summary.get("next_action", ""))
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "fixture_stage": fixture_stage,
        "promotion_ready": promotion_ready,
        "verdict": "SOURCE_BACKED_STRONG_CONFIRMED" if promotion_ready else "PROMOTION_BLOCKED",
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


def _report_next_action(
    *,
    promotion_ready: bool,
    operator_summary: dict[str, Any],
    first_missing_chain: dict[str, str] | None,
) -> str:
    if promotion_ready:
        return "fixture_can_be_core_source_backed"
    if operator_summary.get("technical_status") != "VALID_PACKAGE":
        return str(operator_summary.get("next_action", ""))
    if (
        operator_summary.get("next_action") == "SOURCE_INFORMED_APPLY_READY"
        and isinstance(operator_summary.get("source_informed_apply_readiness"), dict)
        and operator_summary["source_informed_apply_readiness"].get("status") == "ready"
    ):
        return "source_informed_apply_ready_but_not_strong"
    return "close_first_missing_chain"


def _first_missing_chain(source_claim_gap_report: dict[str, Any]) -> dict[str, str] | None:
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
