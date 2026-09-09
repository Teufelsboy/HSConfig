"""Neutral lowering of one frozen optimized starter selection."""

from __future__ import annotations

from dataclasses import dataclass

from hsconfig.globalvalues_decisions import (
    build_optimized_globalvalues_decision_ledger,
)
from hsconfig.gameplan_contract import build_gameplan_contract
from hsconfig.mechanic_drift import build_mechanic_drift_report
from hsconfig.package_domain import (
    ComboPlanModel,
    GlobalValuesDecisionLedger,
    MulliganPlanModel,
)
from hsconfig.package_request import (
    FrozenApprovedLiveConfigureRequest,
    FrozenJsonDocument,
    ResolvedPackageRequest,
)
from hsconfig.research_contract import build_research_contract_bundle
from hsconfig.starter_context import quality_main_card_rows
from hsconfig.starter_contract import (
    QUALITY_STARTER_SCHEMA_VERSION,
    STARTER_CANDIDATE_FILENAMES,
    STARTER_CONTEXT_FILENAME,
    STARTER_DECISION_FILENAME,
)
from hsconfig.starter_decision import ValidatedStarterSelection
from hsconfig.starter_document import StarterDocument
from hsconfig.optimized_start_authority import ValidatedSingleStarterApproval
from hsconfig.visionai_registry import SINGLE_CANDIDATE_REVIEW_REPORT_PATHS


_OPTIMIZED_REPORT_ROOT = "reports/optimized_start"


@dataclass(frozen=True, slots=True)
class OptimizedStartLowering:
    mulligan_plan: MulliganPlanModel
    combo_plan: ComboPlanModel
    globalvalues_ledger: GlobalValuesDecisionLedger
    card_behavior_plan: FrozenJsonDocument
    optimized_projections: tuple[tuple[str, StarterDocument], ...]
    authority_id: str


@dataclass(frozen=True, slots=True)
class SingleCandidateStartLowering:
    mulligan_plan: MulliganPlanModel
    combo_plan: ComboPlanModel
    globalvalues_ledger: GlobalValuesDecisionLedger
    card_behavior_plan: FrozenJsonDocument
    optimized_projections: tuple[tuple[str, StarterDocument], ...]
    compiler_state: FrozenJsonDocument
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


def lower_single_candidate_start(
    *,
    request: ResolvedPackageRequest | FrozenApprovedLiveConfigureRequest,
    approval: ValidatedSingleStarterApproval,
) -> SingleCandidateStartLowering:
    """Lower one durable V2 approval from its already frozen inputs only."""

    if not isinstance(
        request, (ResolvedPackageRequest, FrozenApprovedLiveConfigureRequest)
    ):
        raise TypeError("resolved_package_request_required")
    if not isinstance(approval, ValidatedSingleStarterApproval):
        raise TypeError("validated_single_starter_approval_required")
    if request.starter_approval != approval:
        raise ValueError("starter_approval_request_mismatch")
    frozen = request.frozen_compiler_inputs
    if frozen is None:
        raise ValueError("starter_approval_frozen_inputs_required")

    candidate = approval.candidate
    authority_id = f"starter:{candidate.document.content_sha256}"
    context_value = approval.context.document.to_value()
    baseline_projection = context_value["globalvalues_baseline"]
    baseline = baseline_projection["values"]
    globalvalues_ledger = build_optimized_globalvalues_decision_ledger(
        deck_fingerprint=approval.context.deck_fingerprint,
        baseline=baseline,
        baseline_sha256=baseline_projection["content_sha256"],
        desired_state=candidate.globalvalues.to_value(),
        authority_id=authority_id,
    )

    rows = [
        {
            **document.to_value(),
            "claim_id": (
                f"{authority_id}:{candidate.candidate_id}:"
                f"{document.to_value()['rule_id_suffix']}"
            ),
            "meaningful_runtime_surface": True,
        }
        for document in candidate.card_behavior_rows
    ]
    card_rows: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        runtime_card_id = str(row["runtime_card_id"])
        card_rows.setdefault(runtime_card_id, []).append(row)
    card_behavior_plan = FrozenJsonDocument.from_value(
        {
            "card_rows": {
                card_id: card_rows[card_id] for card_id in sorted(card_rows)
            },
            "rows": rows,
            "suppressed": [],
            "option_resolution": [],
            "merged_duplicate_runtime_row_count": 0,
            "runtime_row_conflicts": [],
        }
    )

    optimized_projections = tuple(
        zip(
            SINGLE_CANDIDATE_REVIEW_REPORT_PATHS,
            (
                approval.snapshot.document,
                approval.context.document,
                approval.candidate.document,
                approval.review.document,
            ),
            strict=True,
        )
    )
    compiler_state = FrozenJsonDocument.from_value(
        _single_candidate_compiler_state(
            request=request,
            approval=approval,
            card_behavior_plan=card_behavior_plan.to_value(),
        )
    )
    return SingleCandidateStartLowering(
        mulligan_plan=candidate.mulligan_plan,
        combo_plan=candidate.combo_plan,
        globalvalues_ledger=globalvalues_ledger,
        card_behavior_plan=card_behavior_plan,
        optimized_projections=optimized_projections,
        compiler_state=compiler_state,
        authority_id=authority_id,
    )


def _single_candidate_compiler_state(
    *,
    request: ResolvedPackageRequest | FrozenApprovedLiveConfigureRequest,
    approval: ValidatedSingleStarterApproval,
    card_behavior_plan: dict[str, object],
) -> dict[str, object]:
    frozen = request.frozen_compiler_inputs
    if frozen is None:
        raise ValueError("starter_approval_frozen_inputs_required")
    context = approval.context.document.to_value()
    candidate = approval.candidate.document.to_value()
    frozen_deck = frozen.deck.to_value()
    frozen_sources = frozen.source_acquisition.to_value()
    frozen_documents = frozen.source_documents.to_value()
    cards_payload = frozen_deck["cards_payload"]
    deck_identity = frozen_deck["deck_identity"]
    context_cards = (
        quality_main_card_rows(context)
        if context["schema_version"] == QUALITY_STARTER_SCHEMA_VERSION
        else context["cards"]
    )
    card_metadata = {"cards": context_cards}
    physical_ids = sorted({str(row["card_id"]) for row in context_cards})
    existing_claims = list(context["existing_claims"])
    guide_sources_summary = dict(
        context["source_evidence"]["guide_sources_summary"]
    )
    claim_ids_by_card: dict[str, list[str]] = {
        card_id: [] for card_id in physical_ids
    }
    guide_backed_cards: set[str] = set()
    static_semantic_cards: set[str] = set()
    for claim in existing_claims:
        readiness = str(claim.get("claim_readiness", ""))
        source_family = str(claim.get("source_family", ""))
        claim_card_ids = {
            str(card_id)
            for card_id in claim.get("cards", [])
            if str(card_id) in claim_ids_by_card
        }
        for card_id in sorted(claim_card_ids):
            claim_ids_by_card[card_id].append(str(claim["claim_id"]))
        if (
            readiness in {"static_semantics", "static_semantics_backfilled"}
            or source_family == "hearthstonejson_static_semantics"
        ):
            static_semantic_cards.update(claim_card_ids)
        elif readiness == "guide_backed":
            guide_backed_cards.update(claim_card_ids)
    guide_backed_cards.difference_update(static_semantic_cards)
    uncovered_cards = sorted(
        set(physical_ids) - guide_backed_cards - static_semantic_cards
    )
    coverage_cards = {
        card_id: {
            "card_id": card_id,
            "coverage_status": (
                "guide_backed"
                if card_id in guide_backed_cards
                else (
                    "static_semantics_backfilled"
                    if card_id in static_semantic_cards
                    else "uncovered_low_confidence"
                )
            ),
            "source_claim_ids": claim_ids_by_card[card_id],
        }
        for card_id in physical_ids
    }
    coverage = {
        "cards": coverage_cards,
        "deck_name": deck_identity["deck_name"],
        "guide_backed_cards": len(guide_backed_cards),
        "static_semantic_cards": len(static_semantic_cards),
        "claim_kinds": sorted(
            {str(claim.get("claim_kind", "")) for claim in existing_claims}
        ),
        "summary": {
            "guide_backed": len(guide_backed_cards),
            "static_semantics_backfilled": len(static_semantic_cards),
            "uncovered_low_confidence": len(uncovered_cards),
        },
        "total_cards": len(physical_ids),
        "uncovered_cards": uncovered_cards,
    }
    guide_claim_bundle = {
        "authority": "diagnostic_only",
        "canonical_source_receipts": [],
        "claim_count": guide_sources_summary["claim_count"],
        "claim_conflict_report": {"conflict_count": 0, "conflicts": []},
        "claim_coverage_report": coverage,
        "claims": existing_claims,
        "coverage": coverage,
        "globalvalues_source_receipts": [],
        "guide_sources_summary": guide_sources_summary,
        "runtime_authorized": False,
        "source_count": guide_sources_summary["source_count"],
        "source_evidence_index": [],
        "unsupported_claims": [],
        "source_backed_status": "SOURCE_BACKED_PARTIAL",
    }
    diagnostic_source_claims = {
        "authority": "diagnostic_only",
        "claims": existing_claims,
        "claim_count": len(existing_claims),
        "runtime_authorized": False,
    }
    research_bundle = build_research_contract_bundle(
        deck_identity=deck_identity,
        card_metadata=card_metadata,
        source_claims=diagnostic_source_claims,
        guide_claim_bundle=guide_claim_bundle,
    )
    if guide_sources_summary["static_card_semantics_used"] is True:
        static_semantic_cards.update(
            card_id
            for card_id, row in research_bundle["card_role_map"].items()
            if row["confidence"] == "source_backed_static_semantics"
        )
        guide_backed_cards.difference_update(static_semantic_cards)
        uncovered_cards = sorted(
            set(physical_ids) - guide_backed_cards - static_semantic_cards
        )
        for card_id, row in coverage_cards.items():
            row["coverage_status"] = (
                "guide_backed"
                if card_id in guide_backed_cards
                else (
                    "static_semantics_backfilled"
                    if card_id in static_semantic_cards
                    else "uncovered_low_confidence"
                )
            )
        coverage.update(
            {
                "guide_backed_cards": len(guide_backed_cards),
                "static_semantic_cards": len(static_semantic_cards),
                "summary": {
                    "guide_backed": len(guide_backed_cards),
                    "static_semantics_backfilled": len(
                        static_semantic_cards
                    ),
                    "uncovered_low_confidence": len(uncovered_cards),
                },
                "uncovered_cards": uncovered_cards,
            }
        )
    gameplan_contract = build_gameplan_contract(
        deck_identity=deck_identity,
        card_metadata=card_metadata,
        source_claims=diagnostic_source_claims,
        research_bundle=research_bundle,
    )
    mulligan_plan = approval.candidate.mulligan_plan.to_report()
    combo_plan = approval.candidate.combo_plan.to_report()
    globalvalues_matrix = {
        "allowed_step1_overlays": [],
        "blocked_until_runtime_evidence": [],
    }
    runtime_owner_cards: dict[str, dict[str, object]] = {}
    for row in card_behavior_plan["rows"]:
        runtime_card_id = str(row["runtime_card_id"])
        owner = {
            "authority": "candidate_rule",
            "card_id": runtime_card_id,
            "confidence": "llm_optimized_start",
            "link_kind": str(row["link_kind"]),
            "roles": [],
            "runtime_authorized": True,
            "runtime_card_id": runtime_card_id,
            "source_card_id": str(row["source_card_id"]),
            "source_claim_ids": [],
        }
        previous = runtime_owner_cards.setdefault(runtime_card_id, owner)
        if previous != owner:
            raise ValueError("starter_candidate_runtime_owner_binding_invalid")
    gameplan_contract.update(
        {
            "cards": runtime_owner_cards,
            "guide_claim_bundle": guide_claim_bundle,
            "mulligan_plan": mulligan_plan,
            "card_behavior_plan": card_behavior_plan,
            "combo_plan": combo_plan,
            "global_values_authority_matrix": globalvalues_matrix,
        }
    )
    semantic_cards = [
        {
            **row,
            "deck_zone": "main",
            "runtime_eligible": True,
            "semantic_families": list(row.get("mechanic_families", [])),
            "warning_only_mechanics": [],
        }
        for row in context_cards
    ]
    baseline = context["globalvalues_baseline"]
    guide_sources = frozen_documents.get("guide_sources")
    source_evidence = frozen_sources.get(
        "source_evidence_report",
        {
            "schema_version": 1,
            "status": "not_available",
            "claims": [],
            "warnings": [],
            "summary": {
                "claim_count": 0,
                "document_count": 0,
                "runtime_lowering_claims": 0,
                "warnings_count": 0,
            },
        },
    )
    return {
        "authority_guide_claim_bundle": guide_claim_bundle,
        "card_behavior_plan": card_behavior_plan,
        "card_metadata": card_metadata,
        "cards_payload": cards_payload,
        "candidate_archetypes": {
            "schema_version": 1,
            "deck_code_hash": deck_identity["deck_code_hash"],
            "deck_name": deck_identity["deck_name"],
            "primary_archetype": candidate["strategy_summary"]["role"],
            "candidates": [
                {
                    "archetype": candidate["strategy_summary"]["role"],
                    "confidence": "candidate_reviewed",
                    "reason": "single_candidate_review_authority",
                    "source_count": guide_sources_summary["source_count"],
                }
            ],
        },
        "combo_plan": combo_plan,
        "deck_fingerprint": {
            "schema_version": 1,
            "deck_name": deck_identity["deck_name"],
            "deck_code_hash": deck_identity["deck_code_hash"],
            "deck_fingerprint": f"sha256:{deck_identity['deck_fingerprint']}",
            "card_count": deck_identity["card_count_total"],
            "unique_card_count": len(physical_ids),
            "cards": [
                {"card_id": row["card_id"], "count": row["count"]}
                for row in sorted(context_cards, key=lambda item: item["card_id"])
            ],
        },
        "deck_identity": deck_identity,
        "deck_input_verification": cards_payload["deck_input_verification"],
        "gameplan_contract": gameplan_contract,
        "global_values_authority_matrix": globalvalues_matrix,
        "globalvalues_baseline": baseline["values"],
        "globalvalues_baseline_receipt": {
            "baseline": baseline["values"],
            "key_count": baseline["key_count"],
            "path": None,
            "sha256": baseline["content_sha256"],
            "snapshot_date": frozen.manifest.compiler_inputs.to_value()[
                "bound_date"
            ],
            "snapshot_status": "frozen_input_snapshot",
            "source": "input_snapshot_manifest",
        },
        "guide_builder_receipt": context["source_evidence"][
            "guide_builder_receipt"
        ],
        "guide_claim_bundle": guide_claim_bundle,
        "guide_sources_generated": guide_sources,
        "identity_gap_report": {
            "schema_version": 1,
            "deck_name": deck_identity["deck_name"],
            "gap_count": 0,
            "missing_identity_fields": [],
        },
        "identity_graph_report": {
            "schema_version": 1,
            "deck_name": deck_identity["deck_name"],
            "deck_code_hash": deck_identity["deck_code_hash"],
            "format": deck_identity["format"],
            "hero_dbf_id": deck_identity["hero_dbf_id"],
            "main_deck_card_count": deck_identity["card_count_total"],
            "main_deck_multiset": {
                row["card_id"]: row["count"] for row in context_cards
            },
            "sideboard_card_count": 0,
            "sideboard_multiset": {},
            "generated_token_closure": "frozen_context_only",
            "hearthstonejson_receipt": {
                "status": "frozen_input_snapshot",
                "source": "input_snapshot_manifest",
                "card_count": len(frozen.full_cards.to_value()),
                "error": None,
            },
            "starting_hero_power_id": None,
        },
        "initial_lifecycle_rows": [],
        "mechanic_drift_report": build_mechanic_drift_report(
            cards_payload["cards"]
        ),
        "mulligan_plan": mulligan_plan,
        "plan_input_diagnostics": None,
        "policy_profile": {
            "authority": "not_frozen",
            "runtime_authorized": False,
        },
        "research_bundle": research_bundle,
        "semantic_report": {
            "schema_version": 1,
            "semantic_enrichment_status": "frozen_context",
            "semantic_enrichment_warnings": [],
            "non_blocking": True,
            "cards": semantic_cards,
            "deckwide_effects": [],
            "summary": {
                "card_count": len(semantic_cards),
                "warning_count": 0,
            },
        },
        "source_claim_conflict_report": {
            "conflict_count": 0,
            "conflicts": [],
        },
        "source_evidence_report": source_evidence,
    }


__all__ = (
    "OptimizedStartLowering",
    "SingleCandidateStartLowering",
    "lower_optimized_start",
    "lower_single_candidate_start",
)
