from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


VALID_TECHNICAL_STATUS = "VALID_PACKAGE"
STRONG_SOURCE_STATUS = "SOURCE_BACKED_STRONG"
PARTIAL_SOURCE_STATUS = "SOURCE_BACKED_PARTIAL"
INVALID_SOURCE_STATUS = "INVALID_PACKAGE"
READY_ACTION = "READY_TO_APPLY_OR_HANDOFF"
NO_MISSING_SOURCE_ACTION = "none"
DEFAULT_ONLY_SOURCE_ACTION = "replace_default_only_runtime_surface_with_source_or_policy_claim"
FALLBACK_SOURCE_ACTION = "close_first_missing_chain"


@dataclass(frozen=True)
class SourceStatusResolution:
    source_backed_status: str
    strong_ready: bool
    first_missing_source_action: str
    default_only_runtime_surfaces: tuple[str, ...]
    missing_source_actions: tuple[str, ...]
    reasons: tuple[str, ...]
    diagnostic_only: bool = True
    apply_blocking: bool = False

    def as_operator_fields(self) -> dict[str, object]:
        return {
            "source_backed_status": self.source_backed_status,
            "source_strong_ready": self.strong_ready,
            "first_missing_source_action": self.first_missing_source_action,
            "source_missing_source_actions": self.missing_source_actions,
            "source_status_reasons": self.reasons,
            "source_status_diagnostic_only": self.diagnostic_only,
            "source_status_apply_blocking": self.apply_blocking,
        }


def first_missing_chain_from_report(
    report: Mapping[str, object] | None,
) -> dict[str, object] | None:
    chain = _first_missing_chain(report)
    return dict(chain) if chain is not None else None


def resolve_source_status(
    *,
    technical_status: str,
    semantic_status: str,
    next_action: str,
    semantic_blockers: Sequence[object],
    default_only_runtime_surfaces: Sequence[str],
    source_claim_gap_report: Mapping[str, object] | None,
    closure_profile_closed: bool,
    closure_profile_first_missing_link: str = "",
) -> SourceStatusResolution:
    default_only_surfaces = _string_tuple(default_only_runtime_surfaces)
    first_missing_chain = _first_missing_chain(source_claim_gap_report)

    if default_only_surfaces:
        return _resolution(
            source_backed_status=PARTIAL_SOURCE_STATUS,
            action=DEFAULT_ONLY_SOURCE_ACTION,
            default_only_runtime_surfaces=default_only_surfaces,
            reasons=("default_only_runtime_surface",),
        )

    if technical_status != VALID_TECHNICAL_STATUS:
        action = _first_nonempty(next_action, _action_from_status(semantic_status))
        return _resolution(
            source_backed_status=_invalid_source_status(semantic_status),
            action=action,
            default_only_runtime_surfaces=default_only_surfaces,
            reasons=("technical_status_not_valid",),
        )

    if first_missing_chain is not None:
        action = _first_nonempty(
            _report_next_action(source_claim_gap_report),
            _chain_next_action(first_missing_chain),
            _source_action_for_missing_link(first_missing_chain),
        )
        return _resolution(
            source_backed_status=PARTIAL_SOURCE_STATUS,
            action=action,
            default_only_runtime_surfaces=default_only_surfaces,
            reasons=("first_missing_claim_chain",),
        )

    if semantic_blockers:
        action = _first_nonempty(
            _action_from_semantic_blockers(semantic_blockers),
            next_action,
            FALLBACK_SOURCE_ACTION,
        )
        return _resolution(
            source_backed_status=PARTIAL_SOURCE_STATUS,
            action=action,
            default_only_runtime_surfaces=default_only_surfaces,
            reasons=("semantic_blocker",),
        )

    if _has_unclosed_source_gap_summary(source_claim_gap_report):
        action = _first_nonempty(
            _report_next_action(source_claim_gap_report),
            FALLBACK_SOURCE_ACTION,
        )
        return _resolution(
            source_backed_status=PARTIAL_SOURCE_STATUS,
            action=action,
            default_only_runtime_surfaces=default_only_surfaces,
            reasons=("source_claim_gap_summary_not_closed",),
        )

    if (
        closure_profile_closed
        and semantic_status == STRONG_SOURCE_STATUS
        and next_action == READY_ACTION
    ):
        return SourceStatusResolution(
            source_backed_status=STRONG_SOURCE_STATUS,
            strong_ready=True,
            first_missing_source_action=NO_MISSING_SOURCE_ACTION,
            default_only_runtime_surfaces=default_only_surfaces,
            missing_source_actions=(),
            reasons=("source_backed_strong_ready",),
        )

    if not closure_profile_closed:
        action = _first_nonempty(
            _source_action_for_profile_miss(closure_profile_first_missing_link),
            FALLBACK_SOURCE_ACTION,
        )
        return _resolution(
            source_backed_status=PARTIAL_SOURCE_STATUS,
            action=action,
            default_only_runtime_surfaces=default_only_surfaces,
            reasons=("closure_profile_not_closed",),
        )

    return _resolution(
        source_backed_status=PARTIAL_SOURCE_STATUS,
        action=_first_nonempty(next_action, _action_from_status(semantic_status)),
        default_only_runtime_surfaces=default_only_surfaces,
        reasons=("semantic_status_not_strong",),
    )


def _resolution(
    *,
    source_backed_status: str,
    action: str,
    default_only_runtime_surfaces: tuple[str, ...],
    reasons: tuple[str, ...],
) -> SourceStatusResolution:
    normalized_action = action or FALLBACK_SOURCE_ACTION
    return SourceStatusResolution(
        source_backed_status=source_backed_status,
        strong_ready=False,
        first_missing_source_action=normalized_action,
        default_only_runtime_surfaces=default_only_runtime_surfaces,
        missing_source_actions=()
        if normalized_action == NO_MISSING_SOURCE_ACTION
        else (normalized_action,),
        reasons=reasons,
    )


def _string_tuple(values: Sequence[str]) -> tuple[str, ...]:
    if isinstance(values, str):
        return (values,) if values else ()
    return tuple(str(value) for value in values if str(value))


def _first_missing_chain(
    report: Mapping[str, object] | None,
) -> Mapping[str, object] | None:
    if not isinstance(report, Mapping):
        return None
    summary = report.get("summary")
    if isinstance(summary, Mapping):
        canonical = summary.get("first_missing_chain")
        if isinstance(canonical, Mapping):
            return canonical

    legacy = report.get("first_missing_chain")
    if isinstance(legacy, Mapping):
        return legacy

    cards = report.get("cards")
    if not isinstance(cards, Mapping):
        return None
    for card_id, row in sorted(cards.items(), key=lambda item: str(item[0])):
        if not isinstance(row, Mapping):
            continue
        if str(row.get("first_missing_link") or "") == "none":
            continue
        first_missing_link = str(row.get("first_missing_link") or "")
        if not first_missing_link:
            continue
        return {
            "card_id": str(card_id),
            "first_missing_link": first_missing_link,
            "recommended_source_claim_kind": str(
                row.get("recommended_source_claim_kind") or ""
            ),
            "next_action": str(row.get("next_action") or ""),
        }
    return None


def _report_next_action(report: Mapping[str, object] | None) -> str:
    if not isinstance(report, Mapping):
        return ""
    action = str(report.get("next_action") or "")
    if action:
        return action
    summary = report.get("summary")
    if isinstance(summary, Mapping):
        return str(
            summary.get("next_source_builder_action")
            or summary.get("next_action")
            or ""
        )
    return ""


def _chain_next_action(chain: Mapping[str, object]) -> str:
    return str(chain.get("next_action") or "")


def _source_action_for_missing_link(chain: Mapping[str, object]) -> str:
    missing_link = str(chain.get("first_missing_link") or "")
    if missing_link == "needs_mulligan_claim":
        return "add_explicit_mulligan_source"
    if missing_link == "needs_runtime_surface":
        return "add_runtime_lowerable_claim_or_router_support"
    if missing_link == "needs_guide_claim":
        return "add_card_specific_source_claim"
    if missing_link == "runtime_evidence":
        return "collect_runtime_evidence_or_mark_contract_only"
    return FALLBACK_SOURCE_ACTION


def _action_from_semantic_blockers(blockers: Sequence[object]) -> str:
    for blocker in blockers:
        if not isinstance(blocker, Mapping):
            continue
        code = str(blocker.get("code") or blocker.get("reason") or "")
        action = _source_action_for_blocker(code)
        if action != FALLBACK_SOURCE_ACTION:
            return action
    return ""


def _source_action_for_blocker(code: str) -> str:
    if code == "policy_claim_not_strong_evidence":
        return "add_explicit_mulligan_source"
    if code == "default_only_surface_not_strong_evidence":
        return DEFAULT_ONLY_SOURCE_ACTION
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
    return FALLBACK_SOURCE_ACTION


def _source_action_for_profile_miss(first_missing_link: str) -> str:
    if first_missing_link == "none":
        return NO_MISSING_SOURCE_ACTION
    if first_missing_link.startswith("missing_claim_group:"):
        return "add_profile_claim_group_source"
    if first_missing_link.startswith("missing_surface:"):
        return "add_profile_runtime_surface"
    if first_missing_link.startswith("default_only_surface:"):
        return DEFAULT_ONLY_SOURCE_ACTION
    return ""


def _has_unclosed_source_gap_summary(report: Mapping[str, object] | None) -> bool:
    if not isinstance(report, Mapping):
        return False
    summary = report.get("summary")
    if not isinstance(summary, Mapping):
        return False
    return (
        _int_value(summary.get("blocked_cards")) > 0
        or _int_value(summary.get("deck_surface_gap_count")) > 0
    )


def _invalid_source_status(semantic_status: str) -> str:
    return INVALID_SOURCE_STATUS


def _action_from_status(status: str) -> str:
    if status == INVALID_SOURCE_STATUS:
        return "FIX_PACKAGE_BEFORE_APPLY"
    return status or FALLBACK_SOURCE_ACTION


def _first_nonempty(*values: str) -> str:
    for value in values:
        normalized = str(value or "")
        if normalized:
            return normalized
    return FALLBACK_SOURCE_ACTION


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
