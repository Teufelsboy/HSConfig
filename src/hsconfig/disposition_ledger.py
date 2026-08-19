"""Canonical disposition and dual-closure projections."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any, Mapping, Sequence

from hsconfig.package_domain import (
    CardDisposition,
    CardDispositionRow,
    ClaimDisposition,
    ClaimDispositionRow,
    ComboPlanModel,
    DispositionLedger,
    DualClosureStatus,
    EvidenceLane,
    GlobalValuesDecisionLedger,
    MulliganPlanModel,
    deep_freeze_definition,
    disposition_ledger_content_sha256,
)
from hsconfig.globalvalues_decisions import (
    GLOBALVALUES_BASELINE_DECISION_KEYS,
)


_KNOWN_DISPOSITIONS = {
    disposition.value: disposition
    for disposition in (
        CardDisposition.RUNTIME_EMITTED,
        CardDisposition.BOT_DELEGATED,
        CardDisposition.SUPPRESSED_UNSUPPORTED_SURFACE,
        CardDisposition.SUPPRESSED_INSUFFICIENT_AUTHORITY,
    )
}
_KNOWN_DISPOSITIONS = deep_freeze_definition(_KNOWN_DISPOSITIONS)


def _canonical_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        decoded = json.loads(value)
    elif isinstance(value, str):
        decoded = json.loads(value)
    else:
        decoded = value
    return json.dumps(
        decoded,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _runtime_paths(
    *,
    composite_card_key: str,
    physical_owner: str,
    physical_emission_index: Mapping[str, Sequence[str]],
    runtime_surface_ledger: Mapping[str, Any],
) -> tuple[str, ...]:
    expected_path = f"{physical_owner}.json"
    meaningful_paths = {
        row.get("relative_path")
        for row in runtime_surface_ledger.get("physical_emissions", ())
        if isinstance(row, Mapping)
        and row.get("composite_card_key") == composite_card_key
        and row.get("physical_owner") == physical_owner
        and row.get("relative_path") == expected_path
        and row.get("meaningful") is True
        and isinstance(row.get("relative_path"), str)
    }
    indexed_paths = {
        path
        for path in physical_emission_index.get(composite_card_key, ())
        if isinstance(path, str)
    }
    return tuple(sorted(meaningful_paths & indexed_paths))


def _card_disposition(
    *,
    card: Mapping[str, Any],
    lifecycle_rows: Sequence[Mapping[str, Any]],
    runtime_paths: tuple[str, ...],
) -> tuple[CardDisposition, str]:
    if runtime_paths:
        return CardDisposition.RUNTIME_EMITTED, "physical_meaningful_emission"
    if card.get("zone") == "sideboard_module":
        return CardDisposition.ANALYSIS_ONLY_SIDEBOARD, "sideboard_analysis_only"

    states = {
        row.get("builder_state")
        for row in lifecycle_rows
        if isinstance(row.get("builder_state"), str)
    }
    if len(states) > 1:
        return (
            CardDisposition.SUPPRESSED_INSUFFICIENT_AUTHORITY,
            "conflicting_card_disposition",
        )
    if not states:
        return (
            CardDisposition.SUPPRESSED_INSUFFICIENT_AUTHORITY,
            "unclassified_card_disposition",
        )
    state = next(iter(states))
    if state == CardDisposition.RUNTIME_EMITTED.value:
        return (
            CardDisposition.SUPPRESSED_UNSUPPORTED_SURFACE,
            "runtime_claim_without_cardid_surface",
        )
    disposition = _KNOWN_DISPOSITIONS.get(state)
    if disposition is None:
        return (
            CardDisposition.SUPPRESSED_INSUFFICIENT_AUTHORITY,
            "unclassified_card_disposition",
        )
    if disposition is CardDisposition.BOT_DELEGATED and (
        card.get("authority_lane") != EvidenceLane.BOT_DELEGATION.value
        or any(
            row.get("policy_id") != "BOT_NATIVE_PRE_RUN"
            for row in lifecycle_rows
        )
    ):
        return (
            CardDisposition.SUPPRESSED_INSUFFICIENT_AUTHORITY,
            "unclassified_card_disposition",
        )
    return disposition, state


def _claim_disposition(
    *,
    row: Mapping[str, Any],
    card_disposition: CardDisposition,
    runtime_paths: tuple[str, ...],
) -> tuple[ClaimDisposition, str]:
    if (
        card_disposition is CardDisposition.RUNTIME_EMITTED
        and runtime_paths
    ):
        return ClaimDisposition.RUNTIME_EMITTED, "physical_meaningful_emission"
    if card_disposition is CardDisposition.ANALYSIS_ONLY_SIDEBOARD:
        return ClaimDisposition.CONTRACT_ONLY, "sideboard_analysis_only"
    try:
        return ClaimDisposition(card_disposition.value), str(
            row.get("builder_state") or card_disposition.value
        )
    except ValueError:
        return (
            ClaimDisposition.SUPPRESSED_INSUFFICIENT_AUTHORITY,
            "unclassified_card_disposition",
        )


def build_disposition_ledger(
    *,
    evidence_contract: Mapping[str, Any],
    claim_lifecycle_rows: Sequence[Mapping[str, Any]],
    physical_emission_index: Mapping[str, Sequence[str]],
    runtime_surface_ledger: Mapping[str, Any],
) -> DispositionLedger:
    """Build one deterministic disposition row per card and exact claim."""

    deck_fingerprint = str(evidence_contract["deck_fingerprint"])
    evidence_cards = tuple(evidence_contract.get("cards", ()))
    expected_contract_claim_ids = {
        str(claim_id)
        for card in evidence_cards
        for claim_id in card.get("claim_ids", ())
    }
    expected_contract_claim_ids.update(
        str(claim_id)
        for claim_id in evidence_contract.get("claim_ids", ())
    )
    lifecycle_by_card: dict[str, list[Mapping[str, Any]]] = {}
    seen_claim_ids: set[str] = set()
    for row in claim_lifecycle_rows:
        if str(row.get("deck_fingerprint", "")) != deck_fingerprint:
            raise ValueError("claim_lifecycle_deck_fingerprint_mismatch")
        claim_id = str(row["claim_id"])
        if claim_id in seen_claim_ids:
            raise ValueError(f"claim_disposition_duplicate:{claim_id}")
        if claim_id not in expected_contract_claim_ids:
            raise ValueError(
                f"claim_lifecycle_not_in_evidence_contract:{claim_id}"
            )
        seen_claim_ids.add(claim_id)
        lifecycle_by_card.setdefault(str(row["composite_card_key"]), []).append(row)

    card_rows: list[CardDispositionRow] = []
    claim_rows: list[ClaimDispositionRow] = []
    projected_claim_ids: set[str] = set()
    for card in sorted(
        evidence_cards,
        key=lambda item: str(item["composite_card_key"]),
    ):
        composite_card_key = str(card["composite_card_key"])
        lifecycle_rows = sorted(
            lifecycle_by_card.get(composite_card_key, ()),
            key=lambda row: str(row["claim_id"]),
        )
        runtime_paths = _runtime_paths(
            composite_card_key=composite_card_key,
            physical_owner=str(card["physical_owner"]),
            physical_emission_index=physical_emission_index,
            runtime_surface_ledger=runtime_surface_ledger,
        )
        disposition, reason_code = _card_disposition(
            card=card,
            lifecycle_rows=lifecycle_rows,
            runtime_paths=runtime_paths,
        )
        expected_card_claim_ids = {
            str(claim_id) for claim_id in card.get("claim_ids", ())
        }
        missing_claim_ids = sorted(
            expected_card_claim_ids - seen_claim_ids
        )
        if missing_claim_ids and disposition is not CardDisposition.RUNTIME_EMITTED:
            disposition = CardDisposition.SUPPRESSED_INSUFFICIENT_AUTHORITY
            reason_code = "missing_claim_lifecycle"
        if disposition is not CardDisposition.RUNTIME_EMITTED:
            runtime_paths = ()
        card_rows.append(
            CardDispositionRow(
                deck_fingerprint=deck_fingerprint,
                composite_card_key=composite_card_key,
                zone=card["zone"],
                official_semantics_canonical_json=_canonical_bytes(
                    card["official_semantics_canonical_json"]
                ),
                authority_lane=EvidenceLane(card["authority_lane"]),
                evidence_ids=tuple(sorted(set(card.get("evidence_ids", ())))),
                claim_ids=tuple(sorted(set(card.get("claim_ids", ())))),
                physical_owner=str(card["physical_owner"]),
                disposition=disposition,
                runtime_paths=runtime_paths,
                reason_code=reason_code,
            )
        )
        for lifecycle_row in lifecycle_rows:
            claim_disposition, claim_reason = _claim_disposition(
                row=lifecycle_row,
                card_disposition=disposition,
                runtime_paths=runtime_paths,
            )
            claim_rows.append(
                ClaimDispositionRow(
                    deck_fingerprint=deck_fingerprint,
                    claim_id=str(lifecycle_row["claim_id"]),
                    claim_kind=str(lifecycle_row["claim_kind"]),
                    evidence_id=str(lifecycle_row["evidence_id"]),
                    disposition=claim_disposition,
                    runtime_paths=(
                        runtime_paths
                        if claim_disposition
                        is ClaimDisposition.RUNTIME_EMITTED
                        else ()
                    ),
                    reason_code=claim_reason,
                )
            )
            projected_claim_ids.add(str(lifecycle_row["claim_id"]))
        fallback_evidence_id = next(
            iter(sorted(str(value) for value in card.get("evidence_ids", ()))),
            "missing_evidence",
        )
        claim_rows.extend(
            ClaimDispositionRow(
                deck_fingerprint=deck_fingerprint,
                claim_id=claim_id,
                claim_kind="unclassified",
                evidence_id=fallback_evidence_id,
                disposition=(
                    ClaimDisposition.SUPPRESSED_INSUFFICIENT_AUTHORITY
                ),
                runtime_paths=(),
                reason_code="missing_claim_lifecycle",
            )
            for claim_id in missing_claim_ids
        )
        projected_claim_ids.update(missing_claim_ids)

    for lifecycle_row in sorted(
        claim_lifecycle_rows,
        key=lambda row: str(row["claim_id"]),
    ):
        claim_id = str(lifecycle_row["claim_id"])
        if claim_id in projected_claim_ids:
            continue
        claim_disposition, claim_reason = _claim_disposition(
            row=lifecycle_row,
            card_disposition=(
                CardDisposition.SUPPRESSED_INSUFFICIENT_AUTHORITY
            ),
            runtime_paths=(),
        )
        claim_rows.append(
            ClaimDispositionRow(
                deck_fingerprint=deck_fingerprint,
                claim_id=claim_id,
                claim_kind=str(lifecycle_row["claim_kind"]),
                evidence_id=str(
                    lifecycle_row.get("evidence_id") or claim_id
                ),
                disposition=claim_disposition,
                runtime_paths=(),
                reason_code=claim_reason,
            )
        )
        projected_claim_ids.add(claim_id)

    missing_contract_claim_ids = sorted(
        expected_contract_claim_ids - projected_claim_ids
    )
    claim_rows.extend(
        ClaimDispositionRow(
            deck_fingerprint=deck_fingerprint,
            claim_id=claim_id,
            claim_kind="unclassified",
            evidence_id="missing_evidence",
            disposition=(
                ClaimDisposition.SUPPRESSED_INSUFFICIENT_AUTHORITY
            ),
            runtime_paths=(),
            reason_code="missing_claim_lifecycle",
        )
        for claim_id in missing_contract_claim_ids
    )

    cards = tuple(card_rows)
    claims = tuple(sorted(claim_rows, key=lambda row: row.claim_id))
    return DispositionLedger(
        deck_fingerprint=deck_fingerprint,
        cards=cards,
        claims=claims,
        content_sha256=disposition_ledger_content_sha256(
            deck_fingerprint=deck_fingerprint,
            cards=cards,
            claims=claims,
        ),
    )


def build_optimized_start_disposition_ledger(
    *,
    base_dispositions: DispositionLedger,
    card_behavior_plan: Mapping[str, Any],
    mulligan_plan: MulliganPlanModel,
    combo_plan: ComboPlanModel,
    authority_id: str,
) -> DispositionLedger:
    """Replace physical source attribution with selected starter rules."""

    if not isinstance(base_dispositions, DispositionLedger):
        raise TypeError("optimized_base_dispositions_invalid")
    if not isinstance(card_behavior_plan, Mapping):
        raise TypeError("optimized_card_behavior_plan_invalid")
    if not isinstance(mulligan_plan, MulliganPlanModel):
        raise TypeError("optimized_mulligan_plan_invalid")
    if not isinstance(combo_plan, ComboPlanModel):
        raise TypeError("optimized_combo_plan_invalid")
    if not isinstance(authority_id, str) or not authority_id.startswith(
        "starter:"
    ):
        raise ValueError("optimized_authority_id_invalid")

    candidate_rows = [
        row
        for row in card_behavior_plan.get("rows", ())
        if isinstance(row, Mapping)
        and row.get("meaningful_runtime_surface") is True
        and isinstance(row.get("claim_id"), str)
        and row.get("claim_id")
        and row.get("authority_id") == "LLM_OPTIMIZED_START"
        and not row.get("source_claim_ids")
    ]
    claims_by_runtime_path: dict[str, set[str]] = {}
    for row in candidate_rows:
        runtime_card_id = str(
            row.get("runtime_card_id") or row.get("card_id") or ""
        )
        if runtime_card_id:
            claims_by_runtime_path.setdefault(
                f"{runtime_card_id}.json",
                set(),
            ).add(str(row["claim_id"]))

    card_rows: list[CardDispositionRow] = []
    for row in base_dispositions.cards:
        starter_claim_ids = tuple(
            sorted(
                {
                    claim_id
                    for path in row.runtime_paths
                    for claim_id in claims_by_runtime_path.get(path, ())
                }
            )
        )
        if not starter_claim_ids:
            card_rows.append(row)
            continue
        card_rows.append(
            CardDispositionRow(
                deck_fingerprint=row.deck_fingerprint,
                composite_card_key=row.composite_card_key,
                zone=row.zone,
                official_semantics_canonical_json=(
                    row.official_semantics_canonical_json
                ),
                authority_lane=row.authority_lane,
                evidence_ids=(authority_id,),
                claim_ids=starter_claim_ids,
                physical_owner=row.physical_owner,
                disposition=row.disposition,
                runtime_paths=row.runtime_paths,
                reason_code="optimized_start_physical_emission",
            )
        )

    claim_rows = [
        (
            ClaimDispositionRow(
                deck_fingerprint=row.deck_fingerprint,
                claim_id=row.claim_id,
                claim_kind=row.claim_kind,
                evidence_id=row.evidence_id,
                disposition=(
                    ClaimDisposition.SUPPRESSED_INSUFFICIENT_AUTHORITY
                ),
                runtime_paths=(),
                reason_code="replaced_by_optimized_start",
            )
            if row.runtime_paths
            else row
        )
        for row in base_dispositions.claims
    ]
    claim_rows.extend(
        ClaimDispositionRow(
            deck_fingerprint=base_dispositions.deck_fingerprint,
            claim_id=str(row["claim_id"]),
            claim_kind="llm_optimized_start_card_rule",
            evidence_id=authority_id,
            disposition=ClaimDisposition.RUNTIME_EMITTED,
            runtime_paths=(
                f"{str(row.get('runtime_card_id') or row.get('card_id'))}.json",
            ),
            reason_code="optimized_start_physical_emission",
        )
        for row in candidate_rows
    )
    claim_rows.extend(
        ClaimDispositionRow(
            deck_fingerprint=base_dispositions.deck_fingerprint,
            claim_id=str(rule.claim_id),
            claim_kind="llm_optimized_start_mulligan_rule",
            evidence_id=authority_id,
            disposition=ClaimDisposition.RUNTIME_EMITTED,
            runtime_paths=("Mulligan.json",),
            reason_code="optimized_start_physical_emission",
        )
        for rule in mulligan_plan.rules
        if rule.claim_id is not None
    )
    claim_rows.extend(
        ClaimDispositionRow(
            deck_fingerprint=base_dispositions.deck_fingerprint,
            claim_id=str(decision.claim_id),
            claim_kind="llm_optimized_start_combo_rule",
            evidence_id=authority_id,
            disposition=ClaimDisposition.RUNTIME_EMITTED,
            runtime_paths=("Combo.json",),
            reason_code="optimized_start_physical_emission",
        )
        for decision in combo_plan.decisions
        if decision.claim_id is not None
    )
    cards = tuple(card_rows)
    claims = tuple(sorted(claim_rows, key=lambda row: row.claim_id))
    if len({row.claim_id for row in claims}) != len(claims):
        raise ValueError("optimized_claim_disposition_duplicate")
    return DispositionLedger(
        deck_fingerprint=base_dispositions.deck_fingerprint,
        cards=cards,
        claims=claims,
        content_sha256=disposition_ledger_content_sha256(
            deck_fingerprint=base_dispositions.deck_fingerprint,
            cards=cards,
            claims=claims,
        ),
    )


def build_dual_closure(
    *,
    dispositions: DispositionLedger,
    globalvalues_ledger: GlobalValuesDecisionLedger,
    strategy_source_status: str,
) -> DualClosureStatus:
    """Project independent completeness and strategy-authority statuses."""

    if strategy_source_status not in {"partial", "strong"}:
        raise ValueError("strategy_source_status_invalid")
    unresolved = {
        row.reason_code
        for row in dispositions.cards
        if row.reason_code
        in {
            "conflicting_card_disposition",
            "missing_claim_lifecycle",
            "unclassified_card_disposition",
        }
    }
    unresolved.update(
        row.reason_code
        for row in dispositions.claims
        if row.reason_code
        in {
            "conflicting_claim_disposition",
            "missing_claim_lifecycle",
            "unclassified_card_disposition",
        }
    )
    if globalvalues_ledger.deck_fingerprint != dispositions.deck_fingerprint:
        raise ValueError("globalvalues_disposition_fingerprint_mismatch")
    globalvalue_keys = [
        decision.key for decision in globalvalues_ledger.decisions
    ]
    if (
        len(globalvalue_keys) != len(GLOBALVALUES_BASELINE_DECISION_KEYS)
        or len(set(globalvalue_keys)) != len(globalvalue_keys)
        or tuple(globalvalue_keys) != GLOBALVALUES_BASELINE_DECISION_KEYS
    ):
        unresolved.add("incomplete_globalvalues_decision")
    strategy_status = strategy_source_status
    return DualClosureStatus(
        pre_run_contract_status="incomplete" if unresolved else "complete",
        strategy_authority_status=strategy_status,
        exact_guide_authority=(
            strategy_status == "strong"
            and any(
                row.authority_lane is EvidenceLane.EXACT_LIVE_GUIDE
                for row in dispositions.cards
            )
        ),
        unresolved_reasons=tuple(sorted(unresolved)),
    )


def disposition_projection(
    *,
    dispositions: DispositionLedger,
    dual_closure: DualClosureStatus,
) -> dict[str, Any]:
    """Return shared diagnostic-only disposition metadata."""

    return {
        "authority": "diagnostic_only",
        "operator_gate_impact": "diagnostic_only",
        "apply_blocking": False,
        "normal_apply_authority": "reports/operator_summary.json",
        "content_sha256": dispositions.content_sha256,
        "deck_fingerprint": dispositions.deck_fingerprint,
        "card_count": len(dispositions.cards),
        "claim_count": len(dispositions.claims),
        "card_disposition_counts": dict(
            sorted(
                Counter(
                    row.disposition.value for row in dispositions.cards
                ).items()
            )
        ),
        "claim_disposition_counts": dict(
            sorted(
                Counter(
                    row.disposition.value for row in dispositions.claims
                ).items()
            )
        ),
        "pre_run_contract_status": dual_closure.pre_run_contract_status,
        "strategy_authority_status": dual_closure.strategy_authority_status,
        "exact_guide_authority": dual_closure.exact_guide_authority,
        "unresolved_reasons": list(dual_closure.unresolved_reasons),
    }
