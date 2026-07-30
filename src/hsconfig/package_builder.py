from __future__ import annotations

import argparse
from datetime import date
from typing import Any

from hsconfig.configure_stages import StageObserver, build_lowered_runtime_stage
from hsconfig.guide_source_builder import (
    research_required_guide_sources as build_research_required_guide_sources,
)
from hsconfig.hearthstonejson import fetch_latest_cards
from hsconfig.internal_source_authority import (
    InternalSourceAuthorityHandoff,
    reject_caller_supplied_source_authority,
)
from hsconfig.io import write_json
from hsconfig.package_derivation_receipt import refresh_package_derivation_authority
from hsconfig.package_legacy_workflow import (
    LegacyWorkflowDependencies,
    _build_package_disposition_ledger as _build_package_disposition_ledger,
    _filter_globalvalues_authority_matrix as _filter_globalvalues_authority_matrix,
    _filter_runtime_rows_by_claim_ids as _filter_runtime_rows_by_claim_ids,
    _with_strategic_receipt_verification as _with_strategic_receipt_verification,
)
from hsconfig import package_legacy_workflow, package_research_workflow
from hsconfig.package_research_workflow import ResearchWorkflowDependencies
from hsconfig.source_acquisition_closure import AcquisitionClosure


def prepare_package_payload(
    args: argparse.Namespace,
    *,
    current_date: date | None = None,
    source_authority_handoff: InternalSourceAuthorityHandoff | None = None,
    acquisition_closure: AcquisitionClosure | None = None,
    stage_observer: StageObserver | None = None,
    mulligan_source_gaps: list[dict[str, str]] | None = None,
) -> tuple[dict[str, Any], int]:
    reject_caller_supplied_source_authority(args)
    operator_date = _package_current_date(args, current_date)
    payload, code = build_package_payload(
        args,
        current_date=operator_date,
        source_authority_handoff=source_authority_handoff,
        acquisition_closure=acquisition_closure,
        stage_observer=stage_observer,
        mulligan_source_gaps=mulligan_source_gaps,
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
    mulligan_source_gaps: list[dict[str, str]] | None = None,
    include_disposition_diagnostics: bool = False,
) -> tuple[dict[str, Any], int]:
    dependencies = LegacyWorkflowDependencies(
        fetch_latest_cards=fetch_latest_cards,
        research_required_guide_sources=_research_required_guide_sources,
        build_lowered_runtime_stage=build_lowered_runtime_stage,
        write_json=write_json,
        refresh_package_derivation_authority=refresh_package_derivation_authority,
    )
    return package_legacy_workflow.build_package_payload(
        args,
        dependencies=dependencies,
        current_date=current_date,
        source_authority_handoff=source_authority_handoff,
        acquisition_closure=acquisition_closure,
        stage_observer=stage_observer,
        mulligan_source_gaps=mulligan_source_gaps,
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
    if current_date is not None:
        return current_date
    argument_date = getattr(args, "current_date", None)
    if isinstance(argument_date, date):
        return argument_date
    if argument_date is not None:
        return date.fromisoformat(str(argument_date))
    return date.today()


def _research_required_guide_sources(
    deck_name: str,
    deck_identity: dict[str, Any],
) -> dict[str, Any]:
    return build_research_required_guide_sources(deck_name, deck_identity)
