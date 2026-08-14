from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Any, Callable

from hsconfig.configure_stages import (
    StageObserver,
    build_lowered_runtime_stage,
    observe_stage,
)
from hsconfig.guide_source_builder import (
    research_required_guide_sources as build_research_required_guide_sources,
)
from hsconfig.hearthstonejson import fetch_latest_cards
from hsconfig.internal_source_authority import (
    InternalSourceAuthorityHandoff,
    reject_caller_supplied_source_authority,
)
from hsconfig.io import write_json
from hsconfig.package_assembler import PackageModel, assemble_package
from hsconfig.package_compiler import compile_package
from hsconfig.package_compiler_support import (
    _build_package_disposition_ledger,
    _filter_globalvalues_authority_matrix,
    _filter_runtime_rows_by_claim_ids,
    _with_strategic_receipt_verification,
    disposition_diagnostics_document,
)
from hsconfig.package_derivation_receipt import refresh_package_derivation_authority
from hsconfig.package_publication import (
    PublicationFaultHook,
    PublishedPackage,
    publish_rendered_package,
)
from hsconfig import package_research_workflow
from hsconfig.package_render_authority import (
    ArtifactSet,
    RenderFaultHook,
    RenderFaultPoint,
    RenderedAuthorityPackage,
    render_package_authority,
)
from hsconfig.package_research_workflow import ResearchWorkflowDependencies
from hsconfig.package_request import resolve_package_request
from hsconfig.source_acquisition_closure import AcquisitionClosure

__all__ = ("prepare_package_payload", "build_package_payload", "research_contract_payload", "fetch_latest_cards", "build_lowered_runtime_stage", "write_json", "refresh_package_derivation_authority", "_research_required_guide_sources", "_with_strategic_receipt_verification", "_build_package_disposition_ledger", "_filter_globalvalues_authority_matrix", "_filter_runtime_rows_by_claim_ids")

def prepare_package_payload(
    args: argparse.Namespace,
    *,
    current_date: date | None = None,
    source_authority_handoff: InternalSourceAuthorityHandoff | None = None,
    acquisition_closure: AcquisitionClosure | None = None,
    stage_observer: StageObserver | None = None,
    model_observer: Callable[[PackageModel], None] | None = None,
    mulligan_source_gaps: list[dict[str, str]] | None = None,
    render_fault_hook: RenderFaultHook | None = None,
    publication_fault_hook: PublicationFaultHook | None = None,
) -> tuple[dict[str, Any], int]:
    reject_caller_supplied_source_authority(args)
    operator_date = _package_current_date(args, current_date)
    payload, code = build_package_payload(
        args,
        current_date=operator_date,
        source_authority_handoff=source_authority_handoff,
        acquisition_closure=acquisition_closure,
        stage_observer=stage_observer,
        model_observer=model_observer,
        mulligan_source_gaps=mulligan_source_gaps,
        render_fault_hook=render_fault_hook,
        publication_fault_hook=publication_fault_hook,
    )
    payload = dict(payload)
    payload["command"] = "prepare"
    if code == 0:
        operator_summary = payload.get("operator_summary")
        if isinstance(operator_summary, dict):
            payload["next_action"] = operator_summary.get(
                "next_action",
                "READY_TO_APPLY_WITH_WARNINGS",
            )
        else:
            payload["next_action"] = "READY_TO_APPLY_OR_HANDOFF"
    return payload, code


def build_package_payload(
    args: argparse.Namespace,
    *,
    current_date: date | None = None,
    source_authority_handoff: InternalSourceAuthorityHandoff | None = None,
    acquisition_closure: AcquisitionClosure | None = None,
    stage_observer: StageObserver | None = None,
    model_observer: Callable[[PackageModel], None] | None = None,
    mulligan_source_gaps: list[dict[str, str]] | None = None,
    include_disposition_diagnostics: bool = False,
    render_fault_hook: RenderFaultHook | None = None,
    publication_fault_hook: PublicationFaultHook | None = None,
) -> tuple[dict[str, Any], int]:
    reject_caller_supplied_source_authority(args)
    request = resolve_package_request(
        args,
        current_date=_package_current_date(args, current_date),
        fetch_latest_cards_fn=fetch_latest_cards,
        research_required_guide_sources_fn=_research_required_guide_sources,
        source_authority_handoff=source_authority_handoff,
        acquisition_closure=acquisition_closure,
        mulligan_source_gaps=mulligan_source_gaps,
        include_disposition_diagnostics=include_disposition_diagnostics,
    )
    compiled = compile_package(
        request, build_lowered_runtime_stage_fn=build_lowered_runtime_stage
    )
    model = assemble_package(compiled)
    if model_observer is not None:
        model_observer(model)
    rendered = render_package_authority(
        model,
        fault_hook=_render_observer_hook(stage_observer, render_fault_hook),
    )
    published = publish_rendered_package(
        rendered,
        Path(args.out),
        fault_hook=publication_fault_hook,
    )
    return _package_result_payload(
        args=args,
        model=model,
        rendered=rendered,
        published=published,
        include_disposition_diagnostics=include_disposition_diagnostics,
    )


def research_contract_payload(
    args: argparse.Namespace,
    *,
    current_date: date | None = None,
) -> tuple[dict[str, Any], int]:
    dependencies = ResearchWorkflowDependencies(
        fetch_latest_cards=fetch_latest_cards,
        research_required_guide_sources=_research_required_guide_sources,
    )
    return package_research_workflow.research_contract_payload(
        args,
        current_date=_package_current_date(args, current_date),
        dependencies=dependencies,
    )


def _package_current_date(
    args: argparse.Namespace,
    current_date: date | None,
) -> date:
    value = current_date or getattr(args, "current_date", None)
    if value is None:
        return date.today()
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def _research_required_guide_sources(
    deck_name: str,
    deck_identity: dict[str, Any],
) -> dict[str, Any]:
    return build_research_required_guide_sources(deck_name, deck_identity)


def _package_result_payload(
    *,
    args: argparse.Namespace,
    model: PackageModel,
    rendered: RenderedAuthorityPackage,
    published: PublishedPackage,
    include_disposition_diagnostics: bool,
) -> tuple[dict[str, Any], int]:
    del published
    artifacts = rendered.artifacts
    validation = artifacts.read_json("reports/validation_report.json")
    guide_claims = artifacts.read_json("reports/guide_claim_bundle.json")
    readiness = artifacts.read_json(
        "reports/per_card_config_readiness_report.json"
    )
    source_depth = artifacts.read_json(
        "reports/guide_source_depth_report.json"
    )
    operator_summary = artifacts.read_json(
        "reports/operator_summary.json"
    )
    payload = {
        "status": validation["status"],
        "package": str(Path(args.out)),
        "deck_slug": model.compiled.deck_slug,
        "errors": validation["errors"],
        "guide_claims_count": len(guide_claims["claims"]),
        "guide_backed_cards": guide_claims["coverage"][
            "guide_backed_cards"
        ],
        "uncovered_cards_count": len(
            guide_claims["coverage"]["uncovered_cards"]
        ),
        "config_readiness_summary": readiness["summary"],
        "guide_source_depth_status": source_depth["depth_status"],
        "guide_strength_summary": operator_summary[
            "guide_strength_summary"
        ],
        "semantic_blockers": operator_summary["semantic_blockers"],
        "operator_summary": operator_summary,
        "next_action": operator_summary["next_action"],
    }
    if include_disposition_diagnostics:
        payload["disposition_diagnostics"] = (
            disposition_diagnostics_document(
                dispositions=model.compiled.disposition_ledger,
                dual_closure=model.compiled.dual_closure,
            )
        )
    return payload, 0 if validation["status"] == "passed" else 1


def _render_observer_hook(
    observer: StageObserver | None,
    fault_hook: RenderFaultHook | None,
) -> RenderFaultHook | None:
    if observer is None:
        return fault_hook
    names = {
        RenderFaultPoint.FINAL_PLAN: "verified_deck",
        RenderFaultPoint.PRE_AUTHORITY: "normalized_source",
        RenderFaultPoint.RUNTIME_LEDGER: "claim_surfaces",
        RenderFaultPoint.VALIDATION: "lowered_runtime",
        RenderFaultPoint.AUTHORITY: "validated_authority",
        RenderFaultPoint.FINAL_VERIFICATION: "artifact_writing",
    }

    def combined(point: RenderFaultPoint, artifacts: ArtifactSet) -> None:
        name = names.get(point)
        if name is not None:
            observe_stage(
                observer,
                name,
                [row.relative_path for row in artifacts.artifacts],
            )
        if fault_hook is not None:
            fault_hook(point, artifacts)

    return combined
