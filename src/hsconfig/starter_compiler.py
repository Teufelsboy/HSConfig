"""Neutral lowering of one frozen optimized starter selection."""

from __future__ import annotations

from dataclasses import dataclass

from hsconfig.globalvalues_decisions import (
    build_optimized_globalvalues_decision_ledger,
)
from hsconfig.package_domain import (
    ComboPlanModel,
    GlobalValuesDecisionLedger,
    MulliganPlanModel,
)
from hsconfig.package_request import FrozenJsonDocument, ResolvedPackageRequest
from hsconfig.starter_contract import (
    STARTER_CANDIDATE_FILENAMES,
    STARTER_CONTEXT_FILENAME,
    STARTER_DECISION_FILENAME,
)
from hsconfig.starter_decision import ValidatedStarterSelection
from hsconfig.starter_document import StarterDocument


_OPTIMIZED_REPORT_ROOT = "reports/optimized_start"


@dataclass(frozen=True, slots=True)
class OptimizedStartLowering:
    mulligan_plan: MulliganPlanModel
    combo_plan: ComboPlanModel
    globalvalues_ledger: GlobalValuesDecisionLedger
    card_behavior_plan: FrozenJsonDocument
    optimized_projections: tuple[tuple[str, StarterDocument], ...]
    authority_id: str


def lower_optimized_start(
    *,
    request: ResolvedPackageRequest,
    selection: ValidatedStarterSelection,
) -> OptimizedStartLowering:
    """Lower one already revalidated selection without filesystem authority."""

    if not isinstance(request, ResolvedPackageRequest):
        raise TypeError("resolved_package_request_required")
    if not isinstance(selection, ValidatedStarterSelection):
        raise TypeError("validated_starter_selection_required")
    if request.starter_selection != selection:
        raise ValueError("starter_selection_request_mismatch")

    selected = selection.selected
    authority_id = f"starter:{selected.document.content_sha256}"
    context_value = selection.context.document.to_value()
    baseline = context_value["globalvalues_baseline"]["values"]
    globalvalues_ledger = build_optimized_globalvalues_decision_ledger(
        deck_fingerprint=selection.context.deck_fingerprint,
        baseline=baseline,
        baseline_sha256=selection.context.globalvalues_baseline_sha256,
        desired_state=selected.globalvalues.to_value(),
        authority_id=authority_id,
    )

    rows = [
        {
            **document.to_value(),
            "claim_id": (
                f"{authority_id}:{selected.candidate_id}:"
                f"{document.to_value()['rule_id_suffix']}"
            ),
            "meaningful_runtime_surface": True,
        }
        for document in selected.card_behavior_rows
    ]
    card_rows: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        card_rows.setdefault(str(row["card_id"]), []).append(row)
    card_behavior_plan = FrozenJsonDocument.from_value(
        {
            "card_rows": {
                card_id: card_rows[card_id]
                for card_id in sorted(card_rows)
            },
            "rows": rows,
            "suppressed": [],
            "option_resolution": [],
            "merged_duplicate_runtime_row_count": 0,
            "runtime_row_conflicts": [],
        }
    )

    optimized_projections = (
        (
            f"{_OPTIMIZED_REPORT_ROOT}/{STARTER_CONTEXT_FILENAME}",
            selection.context.document,
        ),
        *(
            (
                f"{_OPTIMIZED_REPORT_ROOT}/{filename}",
                candidate.document,
            )
            for filename, candidate in zip(
                STARTER_CANDIDATE_FILENAMES,
                selection.candidates,
                strict=True,
            )
        ),
        (
            f"{_OPTIMIZED_REPORT_ROOT}/{STARTER_DECISION_FILENAME}",
            selection.decision,
        ),
    )
    return OptimizedStartLowering(
        mulligan_plan=selected.mulligan_plan,
        combo_plan=selected.combo_plan,
        globalvalues_ledger=globalvalues_ledger,
        card_behavior_plan=card_behavior_plan,
        optimized_projections=optimized_projections,
        authority_id=authority_id,
    )


__all__ = ("OptimizedStartLowering", "lower_optimized_start")
