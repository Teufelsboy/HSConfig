from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from hsconfig.apply_decision import (
    apply_decision_payload,
    apply_decision_summary_projection,
)
from hsconfig.apply_gate import recompute_apply_decision
from hsconfig.commands.apply import apply_payload, validate_payload
from hsconfig.commands.common import emit_result
from hsconfig.commands.source_workflow import (
    draft_source_documents_payload,
    research_deck_payload,
    research_deck_for_configure,
    source_acquire_for_configure,
    source_autopilot_payload,
    source_autopilot_for_configure,
    source_manifest_payload,
)
from hsconfig.config_quality_contract import (
    build_config_quality_report,
    semantic_handoff_projection,
)
from hsconfig.configure_source_closure_receipt import (
    build_configure_source_closure_receipt,
)
from hsconfig.package_builder import prepare_package_payload
from hsconfig.io import read_json, write_json
from hsconfig.internal_source_authority import (
    reject_caller_supplied_source_authority,
    split_source_documents_handoff,
)
from hsconfig.operator_summary import refresh_generated_file_accounting
from hsconfig.output_ownership_manifest import build_output_ownership_manifest
from hsconfig.package_derivation_receipt import refresh_package_derivation_authority
from hsconfig.package_io import prepare_research_output_dir
from hsconfig.source_bundle import build_source_bundle
from hsconfig.source_closure_intake import (
    SOURCE_CLOSURE_INTAKE_RECEIPT_RELATIVE_PATH,
    build_source_closure_intake_receipt,
    summarize_source_closure_intake,
)
from hsconfig.source_evidence_closure import build_source_evidence_closure_report
from hsconfig.source_candidate_plan import (
    build_source_candidate_plan,
    dedupe_acquisition_urls,
    is_acquisition_url,
)
from hsconfig.source_readiness_preview import build_source_readiness_preview


def run_configure_command(args: argparse.Namespace) -> int:
    reject_caller_supplied_source_authority(args)
    try:
        payload, status = configure_payload(args)
    except Exception as exc:
        payload, status = _finish_stage_exception_for_args(args, "configure", exc)
    return emit_result(payload, bool(getattr(args, "json", False)), status)


def configure_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    reject_caller_supplied_source_authority(args)
    current_date = _normalize_operator_date(
        getattr(args, "current_date", None)
    )
    out = Path(args.out)
    prepare_research_output_dir(out)

    manifest_dir = out / "01_manifest"
    draft_dir = out / "02_source_documents"
    source_acquisition_dir = out / "02_source_acquisition"
    autopilot_dir = (
        out / "03_source_autopilot"
        if bool(getattr(args, "online_source", False))
        else out / "02_source_autopilot"
    )
    research_dir = out / "03_research"
    package_dir = out / "04_package"
    stage_dirs = [manifest_dir, draft_dir, autopilot_dir, research_dir, package_dir]
    if bool(getattr(args, "online_source", False)):
        stage_dirs.append(source_acquisition_dir)
    for stage_dir in stage_dirs:
        stage_dir.mkdir(parents=True, exist_ok=True)

    common = {
        "deck_name": args.deck_name,
        "deck_code": args.deck_code,
        "cards_json": getattr(args, "cards_json", None),
        "collectible_cards_json": getattr(args, "collectible_cards_json", None),
        "full_cards_json": getattr(args, "full_cards_json", None),
        "allow_placeholder": bool(getattr(args, "allow_placeholder", False)),
        "source_url": list(getattr(args, "source_url", []) or []),
        "current_date": current_date,
        "json": True,
    }

    try:
        manifest_payload, manifest_status = source_manifest_payload(
            SimpleNamespace(**common, out=str(manifest_dir))
        )
    except Exception as exc:
        return _finish_stage_exception(out, "source-manifest", exc)
    if manifest_status != 0:
        return _finish(
            out,
            "failed",
            {"stage": "source-manifest", **manifest_payload},
            manifest_status,
        )

    source_acquisition_path = None
    source_documents_json = None
    source_authority_handoff = None
    research_source_authority_handoff = None
    prepare_source_authority_handoff = None
    source_autopilot_path = None
    source_closure_intake_receipt_path = None
    source_candidate_plan_path = manifest_dir / "source_candidate_plan.json"
    explicit_source_urls = dedupe_acquisition_urls(
        list(getattr(args, "source_url", []) or [])
    )
    source_candidate_plan = _load_source_candidate_plan(
        source_candidate_plan_path,
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        explicit_source_urls=explicit_source_urls,
        current_date=current_date,
    )
    source_candidate_urls: list[str] = []
    source_urls: list[str] = []
    if bool(getattr(args, "online_source", False)):
        source_candidate_urls = _plan_urls(source_candidate_plan, "candidate_urls")
        if not source_candidate_urls:
            source_candidate_urls = _plan_candidate_row_urls(source_candidate_plan)
        source_urls = _plan_urls(source_candidate_plan, "source_urls")
        if not source_urls:
            source_urls = dedupe_acquisition_urls(
                [*explicit_source_urls, *source_candidate_urls]
            )
        surviving_registry_urls = [
            url
            for url in source_candidate_urls
            if url not in explicit_source_urls and url in source_urls
        ]
        try:
            acquisition_args = SimpleNamespace(
                **{
                    **common,
                    "source_url": source_urls,
                    "current_date": current_date.isoformat(),
                },
                candidate_registry_url_count=len(surviving_registry_urls),
                source_fixture_url_map_json=getattr(
                    args,
                    "source_fixture_url_map_json",
                    None,
                ),
                source_fetch_timeout_seconds=getattr(
                    args,
                    "source_fetch_timeout_seconds",
                    6.0,
                ),
                out=str(source_acquisition_dir),
            )
            (
                acquire_payload,
                acquire_status,
                source_authority_handoff,
            ) = source_acquire_for_configure(
                acquisition_args
            )
        except Exception as exc:
            return _finish_stage_exception(out, "source-acquire", exc)
        if acquire_status != 0:
            return _finish(
                out,
                "failed",
                {"stage": "source-acquire", **acquire_payload},
                acquire_status,
            )
        args.source_search_results_json = acquire_payload["source_search_results_json"]
        args.auto_source = True
        source_acquisition_path = source_acquisition_dir

    if bool(getattr(args, "auto_source", False)):
        if not getattr(args, "source_search_results_json", None):
            return _finish(
                out,
                "failed",
                {
                    "stage": "source-autopilot",
                    "errors": [
                        "--source-search-results-json is required when --auto-source is used"
                    ],
                },
                1,
            )
        try:
            autopilot_args = SimpleNamespace(
                **common,
                source_search_results_json=args.source_search_results_json,
                out=str(autopilot_dir),
            )
            if source_authority_handoff is not None:
                (
                    autopilot_payload,
                    autopilot_status,
                    source_authority_handoff,
                ) = source_autopilot_for_configure(
                    autopilot_args,
                    source_authority_handoff,
                )
            else:
                autopilot_payload, autopilot_status = source_autopilot_payload(
                    autopilot_args
                )
        except Exception as exc:
            return _finish_stage_exception(out, "source-autopilot", exc)
        if autopilot_status != 0:
            return _finish(
                out,
                "failed",
                {"stage": "source-autopilot", **autopilot_payload},
                autopilot_status,
            )
        if source_authority_handoff is not None:
            (
                research_source_authority_handoff,
                prepare_source_authority_handoff,
            ) = split_source_documents_handoff(source_authority_handoff)
        source_autopilot_path = autopilot_dir
        source_documents_json = autopilot_dir / "source_documents.json"
    elif getattr(args, "source_evidence_json", None):
        try:
            draft_args = SimpleNamespace(
                **common,
                source_evidence_json=args.source_evidence_json,
                out=str(draft_dir),
            )
            draft_payload, draft_status = draft_source_documents_payload(
                draft_args
            )
        except Exception as exc:
            return _finish_stage_exception(out, "draft-source-documents", exc)
        if draft_status != 0:
            return _finish(
                out,
                "failed",
                {"stage": "draft-source-documents", **draft_payload},
                draft_status,
            )
        source_documents_json = draft_dir / "source_documents.json"

    research_source_evidence_json = None
    if source_documents_json is None:
        research_source_evidence_json = getattr(args, "source_evidence_json", None)
    try:
        research_args = SimpleNamespace(
                **common,
                out=str(research_dir),
                source_documents_json=str(source_documents_json) if source_documents_json else None,
                source_evidence_json=research_source_evidence_json,
                guide_sources_json=None,
                claims_json=None,
                skip_semantic_fetch=False,
                auto_research_fallback=True,
            )
        if research_source_authority_handoff is not None:
            research_payload, research_status = research_deck_for_configure(
                research_args,
                research_source_authority_handoff,
            )
        else:
            research_payload, research_status = research_deck_payload(research_args)
    except Exception as exc:
        return _finish_stage_exception(out, "research-deck", exc)
    if research_status != 0:
        return _finish(
            out,
            "failed",
            {"stage": "research-deck", **research_payload},
            research_status,
        )

    try:
        prepare_payload, prepare_status = prepare_package_payload(
            SimpleNamespace(
                deck_name=args.deck_name,
                deck_code=args.deck_code,
                out=str(package_dir),
                runtime_root=args.runtime_root,
                guide_sources_json=str(research_dir / "guide_sources.json"),
                source_documents_json=(
                    str(source_documents_json) if source_documents_json else None
                ),
                cards_json=getattr(args, "cards_json", None),
                collectible_cards_json=getattr(args, "collectible_cards_json", None),
                full_cards_json=getattr(args, "full_cards_json", None),
                claims_json=None,
                plan_reports_dir=None,
                allow_placeholder=bool(getattr(args, "allow_placeholder", False)),
                auto_research_fallback=True,
                current_date=current_date,
                json=True,
            ),
            current_date=current_date,
            source_authority_handoff=prepare_source_authority_handoff,
        )
    except Exception as exc:
        return _finish_stage_exception(out, "prepare", exc)
    if prepare_status != 0:
        return _finish(out, "failed", {"stage": "prepare", **prepare_payload}, prepare_status)

    reports_dir = package_dir / "reports"
    guide_claim_bundle = read_json(reports_dir / "guide_claim_bundle.json")
    operator_summary = read_json(reports_dir / "operator_summary.json")
    explainability_report = read_json(
        reports_dir / "source_to_runtime_explainability.json"
    )
    source_claim_gap_report = read_json(reports_dir / "source_claim_gap_report.json")
    source_bundle_path = reports_dir / "source_bundle.json"
    source_closure_intake_receipt = None
    if bool(getattr(args, "online_source", False)) or bool(
        getattr(args, "auto_source", False)
    ):
        source_closure_intake_receipt = build_source_closure_intake_receipt(
            deck_name=args.deck_name,
            deck_code=args.deck_code,
            fetched_records=_source_search_records(
                getattr(args, "source_search_results_json", None)
            ),
        )
        source_closure_intake_receipt_path = (
            package_dir / SOURCE_CLOSURE_INTAKE_RECEIPT_RELATIVE_PATH
        )
        write_json(source_closure_intake_receipt_path, source_closure_intake_receipt)

    write_json(
        source_bundle_path,
        build_source_bundle(
            deck_name=args.deck_name,
            deck_code=args.deck_code,
            source_records=guide_claim_bundle.get("source_evidence_index", []),
            claims=guide_claim_bundle.get("claims", []),
            operator_summary=operator_summary,
            explainability_report=explainability_report,
        ),
    )
    generated_files = sorted(
        {
            *(str(path) for path in operator_summary.get("generated_files", [])),
            "reports/source_bundle.json",
            *(
                [SOURCE_CLOSURE_INTAKE_RECEIPT_RELATIVE_PATH]
                if source_closure_intake_receipt is not None
                else []
            ),
        }
    )
    output_ownership_manifest = build_output_ownership_manifest(generated_files)
    write_json(reports_dir / "output_ownership_manifest.json", output_ownership_manifest)
    operator_summary = refresh_generated_file_accounting(
        operator_summary,
        generated_files=generated_files,
        output_ownership_manifest=output_ownership_manifest,
    )
    operator_summary["package_derivation"] = refresh_package_derivation_authority(
        package_dir
    )
    if source_closure_intake_receipt is not None:
        operator_summary["source_closure_intake"] = summarize_source_closure_intake(
            source_closure_intake_receipt
        )
    source_evidence_closure_path = reports_dir / "source_evidence_closure.json"
    write_json(
        source_evidence_closure_path,
        build_source_evidence_closure_report(
            deck_name=args.deck_name,
            deck_code=args.deck_code,
            operator_summary=operator_summary,
            source_to_runtime_explainability_report=explainability_report,
            source_claim_gap_report=source_claim_gap_report,
        ),
    )
    write_json(reports_dir / "operator_summary.json", operator_summary)
    config_quality_summary = _build_config_quality_summary(package_dir)

    try:
        validate_payload_result, validate_status = validate_payload(
            SimpleNamespace(package=str(package_dir), json=True)
        )
    except Exception as exc:
        return _finish_stage_exception(out, "validate", exc)
    if validate_status != 0:
        return _finish(
            out,
            "failed",
            {"stage": "validate", **validate_payload_result},
            validate_status,
        )
    semantic_handoff = _configure_semantic_handoff(
        operator_summary,
        config_quality_summary,
    )
    apply_decision, apply_facts = recompute_apply_decision(
        package_dir,
        operator_summary,
        enforce_summary_core_fields=False,
    )
    operator_summary.update(
        apply_decision_summary_projection(
            apply_decision,
            apply_facts,
        )
    )
    load_safe_to_install = (
        apply_decision.allowed
        and apply_decision.mode == "load_safe_apply"
        and validate_status == 0
    )
    operator_summary.update(semantic_handoff)
    operator_summary["load_safe_to_install"] = load_safe_to_install
    operator_summary["use_config_now"] = load_safe_to_install
    operator_summary["use_config_now_scope"] = "load_safety_only"
    write_json(reports_dir / "operator_summary.json", operator_summary)

    apply_payload_result: dict[str, Any] | None = None
    apply_status = None
    if bool(getattr(args, "apply", False)):
        deck_input_verification = operator_summary.get(
            "deck_input_verification",
            {},
        )
        if (
            not isinstance(deck_input_verification, Mapping)
            or deck_input_verification.get("runtime_apply_eligible") is not True
        ):
            return _finish(
                out,
                "failed",
                {
                    "stage": "apply",
                    "reason": "deck_input_not_verified",
                    "errors": ["deck_input_not_verified"],
                },
                1,
            )
        try:
            apply_payload_result, apply_status = apply_payload(
                SimpleNamespace(
                    package=str(package_dir),
                    runtime_root=args.runtime_root,
                    allow_source_informed=False,
                    fake=False,
                    from_fake_receipt=None,
                    json=True,
                )
            )
        except Exception as exc:
            return _finish_stage_exception(out, "apply", exc)
        if apply_status != 0:
            return _finish(out, "failed", {"stage": "apply", **apply_payload_result}, apply_status)

    apply_receipt = (
        apply_payload_result.get("receipt")
        if isinstance(apply_payload_result, dict)
        else None
    )
    runtime_package_match = (
        apply_receipt.get("runtime_package_match")
        if isinstance(apply_receipt, dict)
        else None
    )
    runtime_package_match_status = (
        runtime_package_match.get("status")
        if isinstance(runtime_package_match, dict)
        else "not_checked"
    )
    if bool(getattr(args, "apply", False)) and runtime_package_match_status != "matched":
        return _finish(
            out,
            "failed",
            {
                **(apply_payload_result if isinstance(apply_payload_result, dict) else {}),
                "stage": "apply",
                "status": "failed",
                "errors": [
                    "Successful apply receipt lacks runtime_package_match.status=matched."
                ],
            },
            1,
        )

    acceptance_summary = _build_acceptance_summary(
        operator_summary=operator_summary,
        validate_status=validate_status,
        apply_requested=bool(getattr(args, "apply", False)),
        apply_status=apply_status,
        config_quality_summary=config_quality_summary,
    )
    config_proof_summary = _build_config_proof_summary(
        operator_summary=operator_summary,
        validate_status=validate_status,
        apply_requested=bool(getattr(args, "apply", False)),
        apply_status=apply_status,
        config_quality_summary=config_quality_summary,
    )
    handoff_contract = _build_handoff_contract(
        operator_summary=operator_summary,
        acceptance_summary=acceptance_summary,
        config_proof_summary=config_proof_summary,
        config_quality_summary=config_quality_summary,
    )
    source_closure_receipt = build_configure_source_closure_receipt(
        operator_summary=operator_summary,
        acceptance_summary=acceptance_summary,
        guide_claim_bundle=guide_claim_bundle,
        source_documents_payload=_read_optional_json(source_documents_json),
        source_candidate_urls=source_candidate_urls,
        source_urls=source_urls,
        source_closure_intake_receipt=source_closure_intake_receipt,
    )
    source_autopilot_report = (
        _read_optional_json(source_autopilot_path / "source_autopilot_report.json")
        if source_autopilot_path
        else None
    )
    source_readiness_preview = build_source_readiness_preview(
        source_candidate_plan=source_candidate_plan,
        source_autopilot_report=source_autopilot_report,
        operator_summary=operator_summary,
    )

    return _finish(
        out,
        "OK",
        {
            "manifest_path": str(manifest_dir / "source_research_manifest.json"),
            "source_candidate_plan_path": str(source_candidate_plan_path),
            "source_candidate_plan_summary": _compact_source_candidate_plan_summary(
                source_candidate_plan,
                source_candidate_urls=source_candidate_urls,
            ),
            "source_acquisition_path": (
                str(source_acquisition_path) if source_acquisition_path else None
            ),
            "source_autopilot_path": (
                str(source_autopilot_path) if source_autopilot_path else None
            ),
            "source_documents_json": (
                str(source_documents_json) if source_documents_json else None
            ),
            "research_path": str(research_dir),
            "package_path": str(package_dir),
            "source_bundle_path": str(source_bundle_path),
            "source_evidence_closure_path": str(source_evidence_closure_path),
            "source_closure_intake_receipt_path": (
                str(source_closure_intake_receipt_path)
                if source_closure_intake_receipt_path
                else None
            ),
            "source_backed_status": operator_summary.get("source_backed_status"),
            "source_status_reason": _first_source_status_reason(operator_summary),
            "source_status_reasons": list(
                operator_summary.get("source_status_reasons") or []
            ),
            "source_readiness_preview": source_readiness_preview,
            "source_status_apply_blocking": bool(
                operator_summary.get("source_status_apply_blocking", False)
            ),
            "first_missing_source_action": operator_summary.get(
                "first_missing_source_action"
            ),
            "default_only_runtime_surfaces": list(
                operator_summary.get("default_only_runtime_surfaces") or []
            ),
            "source_candidate_urls": source_candidate_urls,
            "source_urls": source_urls,
            "config_quality_summary": config_quality_summary,
            "acceptance_summary": acceptance_summary,
            "config_proof_summary": config_proof_summary,
            "handoff_contract": handoff_contract,
            "source_closure_receipt": source_closure_receipt,
            "apply_decision": apply_decision_payload(apply_decision),
            "apply_performed": bool(getattr(args, "apply", False)),
            "apply_status": apply_status,
            "runtime_package_match_status": runtime_package_match_status,
            "runtime_package_match": runtime_package_match,
        },
        0,
    )


def _finish(
    out: Path,
    status: str,
    payload: dict[str, Any],
    exit_code: int,
) -> tuple[dict[str, Any], int]:
    summary = {"schema_version": 1, "status": status, **payload}
    write_json(out / "configure_summary.json", summary)
    return summary, exit_code


def _finish_stage_exception(out: Path, stage: str, exc: Exception) -> tuple[dict[str, Any], int]:
    return _finish(out, "failed", _stage_exception_payload(stage, exc), 1)


def _finish_stage_exception_for_args(
    args: argparse.Namespace,
    stage: str,
    exc: Exception,
) -> tuple[dict[str, Any], int]:
    payload = {
        "schema_version": 1,
        "status": "failed",
        **_stage_exception_payload(stage, exc),
    }
    out_value = getattr(args, "out", None)
    if out_value is None:
        return payload, 1
    try:
        return _finish(Path(out_value), "failed", _stage_exception_payload(stage, exc), 1)
    except Exception:
        return payload, 1


def _stage_exception_payload(stage: str, exc: Exception) -> dict[str, Any]:
    return {"stage": stage, "errors": [str(exc)]}


def _compact_config_quality_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    problems_raw = report.get("problems", [])
    problems = problems_raw if isinstance(problems_raw, list) else []

    problem_checks: list[str] = []
    for problem in problems:
        if not isinstance(problem, Mapping):
            continue
        check = str(problem.get("check", "")).strip()
        if check and check not in problem_checks:
            problem_checks.append(check)

    summary: dict[str, Any] = {
        "status": str(report.get("status") or "attention"),
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "problem_count": len(problems),
        "problem_checks": problem_checks,
    }
    summary.update(semantic_handoff_projection(report))
    checks = report.get("checks", {})
    if isinstance(checks, Mapping):
        semantic_intent = checks.get("semantic_intent_coverage")
        if isinstance(semantic_intent, Mapping):
            summary["semantic_intent_status"] = str(
                semantic_intent.get("status") or ""
            )
            first_attention = semantic_intent.get("first_attention")
            if first_attention is not None:
                summary["semantic_intent_first_attention"] = str(first_attention)
        config_intent = checks.get("config_intent_self_audit")
        if isinstance(config_intent, Mapping):
            summary["config_intent_self_audit_status"] = str(
                config_intent.get("status") or ""
            )
            first_attention = config_intent.get("first_attention")
            if first_attention is not None:
                summary["config_intent_first_attention"] = str(first_attention)
            summary["config_intent_runtime_files_total"] = int(
                config_intent.get("runtime_files_total") or 0
            )
            summary["config_intent_runtime_files_without_intent"] = len(
                [
                    item
                    for item in config_intent.get("runtime_files_without_intent", [])
                    if str(item)
                ]
            )
            summary["config_intent_unsupported_runtime_files"] = [
                str(item)
                for item in config_intent.get("unsupported_runtime_files", [])
                if str(item)
            ]
            summary["config_intent_default_only_runtime_surfaces"] = [
                str(item)
                for item in config_intent.get("default_only_runtime_surfaces", [])
                if str(item)
            ]
        surface_intent = checks.get("surface_intent_projection")
        if isinstance(surface_intent, Mapping):
            summary["surface_intent_status"] = str(surface_intent.get("status") or "")
            summary["surface_intent_present"] = bool(
                surface_intent.get("present", False)
            )
            summary["surface_intent_surface_count"] = int(
                surface_intent.get("surface_count") or 0
            )
            summary["surface_intent_fallback_intent_rows"] = len(
                [
                    item
                    for item in surface_intent.get("fallback_intent_rows", [])
                    if isinstance(item, Mapping)
                ]
            )
            summary["surface_intent_legacy_policy_surface_rows"] = [
                str(item.get("surface"))
                for item in surface_intent.get("legacy_policy_surface_rows", [])
                if isinstance(item, Mapping) and str(item.get("surface") or "")
            ]
            first_attention = surface_intent.get("first_attention")
            if first_attention is not None:
                summary["surface_intent_first_attention"] = str(first_attention)
        visionai_surface = checks.get("visionai_semantic_surface")
        if isinstance(visionai_surface, Mapping):
            summary["visionai_semantic_surface_status"] = str(
                visionai_surface.get("status") or ""
            )
            summary["visionai_non_targeted_battlecry_target_rows"] = len(
                [
                    item
                    for item in visionai_surface.get(
                        "non_targeted_battlecry_target_rows", []
                    )
                    if isinstance(item, Mapping)
                ]
            )
            summary["visionai_effect_only_body_rows"] = len(
                [
                    item
                    for item in visionai_surface.get("effect_only_body_rows", [])
                    if isinstance(item, Mapping)
                ]
            )
            summary["visionai_unsupported_report_only_runtime_rows"] = len(
                [
                    item
                    for item in visionai_surface.get(
                        "unsupported_report_only_runtime_rows", []
                    )
                    if isinstance(item, Mapping)
                ]
            )
            summary["visionai_semantic_default_runtime_rows"] = len(
                [
                    item
                    for item in visionai_surface.get(
                        "semantic_default_runtime_rows", []
                    )
                    if isinstance(item, Mapping)
                ]
            )
        legacy_surfaces = checks.get("legacy_surfaces")
        if isinstance(legacy_surfaces, Mapping):
            legacy_present = [
                str(surface)
                for surface in legacy_surfaces.get("present", [])
                if str(surface)
            ]
            summary["legacy_surfaces_present"] = legacy_present
            summary["forbidden_normal_surfaces_absent"] = not legacy_present
            summary["forbidden_normal_surfaces_status"] = (
                "clean" if not legacy_present else "attention"
            )

        darkbishop = checks.get("darkbishop_boundary")
        if isinstance(darkbishop, Mapping):
            mulligan_keep_present = bool(darkbishop.get("mulligan_keep_present"))
            effect_runtime_present = bool(darkbishop.get("effect_runtime_present"))
            if mulligan_keep_present:
                status = "mulligan_keep_present"
            elif effect_runtime_present:
                status = "effect_without_mulligan_keep"
            else:
                status = "not_seen"
            summary["darkbishop_boundary_status"] = status

        runtime_json = checks.get("runtime_json")
        if isinstance(runtime_json, Mapping):
            metadata_leaks = runtime_json.get("metadata_leaks", [])
            stray_cardid_files = runtime_json.get("stray_cardid_files", [])
            summary["runtime_json_status"] = (
                "clean" if not metadata_leaks and not stray_cardid_files else "attention"
            )

        explainability = checks.get("source_to_runtime_explainability")
        if isinstance(explainability, Mapping):
            trace_completeness = checks.get("trace_completeness")
            runtime_rows_missing_trace = (
                trace_completeness.get("runtime_rows_missing_trace")
                if isinstance(trace_completeness, Mapping)
                else None
            )
            if not bool(explainability.get("present")) or not isinstance(
                runtime_rows_missing_trace, list
            ):
                summary["source_to_runtime_status"] = "missing"
            elif runtime_rows_missing_trace:
                summary["source_to_runtime_status"] = "attention"
            else:
                summary["source_to_runtime_status"] = "clean"

        if isinstance(explainability, Mapping) or "closure_freshness" in checks:
            closure_freshness = checks.get("closure_freshness")
            if isinstance(closure_freshness, Mapping):
                closure_present = bool(closure_freshness.get("present"))
                closure_schema_current = bool(
                    closure_freshness.get("closure_schema_current")
                )
                cards_missing_closure = int(
                    closure_freshness.get("cards_missing_closure") or 0
                )
                cards_total = int(closure_freshness.get("cards_total") or 0)
                cards_with_closure = int(
                    closure_freshness.get("cards_with_closure") or 0
                )
            else:
                closure_present = False
                closure_schema_current = False
                cards_missing_closure = 0
                cards_total = 0
                cards_with_closure = 0

            summary["currentness_status"] = (
                "clean"
                if (
                    closure_present
                    and closure_schema_current
                    and cards_missing_closure == 0
                )
                else "attention" if closure_present else "missing"
            )
            summary["closure_schema_current"] = closure_schema_current
            summary["cards_missing_closure"] = cards_missing_closure
            summary["cards_total"] = cards_total
            summary["cards_with_closure"] = cards_with_closure

        mechanic = checks.get("mechanic_runtime_discipline")
        if isinstance(mechanic, Mapping):
            summary["mechanic_runtime_discipline_status"] = str(
                mechanic.get("status") or ""
            )
    if problem_checks:
        summary["next_action"] = "run_contract_doctor_for_details"
    return summary


def _build_config_quality_summary(package_dir: Path) -> dict[str, Any]:
    try:
        return _compact_config_quality_summary(build_config_quality_report(package_dir))
    except Exception as exc:
        summary = {
            "status": "attention",
            "authority": "diagnostic_only",
            "apply_blocking": False,
            "runtime_write_performed": False,
            "problem_count": 1,
            "problem_checks": ["config_quality_summary_failed"],
            "next_action": "run_contract_doctor_for_details",
            "error": f"{type(exc).__name__}: {exc}",
        }
        summary.update(
            semantic_handoff_projection(
                {
                    "checks": {
                        "source_evidence": {
                            "source_lanes": ["generic_low_confidence"],
                            "semantic_runtime_rows": 0,
                        }
                    }
                }
            )
        )
        return summary


def _build_acceptance_summary(
    *,
    operator_summary: Mapping[str, Any],
    apply_requested: bool,
    apply_status: int | None,
    config_quality_summary: Mapping[str, Any],
    validate_status: int | None = None,
    validation_status: str | None = None,
) -> dict[str, Any]:
    runtime_contract = operator_summary.get("runtime_apply_contract", {})
    if not isinstance(runtime_contract, Mapping):
        runtime_contract = {}

    normal_apply_authority = str(
        runtime_contract.get("apply_authority") or "reports/operator_summary.json"
    )
    runtime_apply_allowed = bool(operator_summary.get("runtime_apply_allowed", False))
    runtime_apply_mode = str(operator_summary.get("runtime_apply_mode", ""))
    technical_status = str(operator_summary.get("technical_status", ""))
    source_status_apply_blocking = bool(
        operator_summary.get("source_status_apply_blocking", False)
    )
    default_only_runtime_surfaces = [
        str(surface)
        for surface in operator_summary.get("default_only_runtime_surfaces", [])
        if str(surface)
    ]
    problem_checks = [
        str(check)
        for check in config_quality_summary.get("problem_checks", [])
        if str(check)
    ]
    semantic_intent_status = str(
        config_quality_summary.get("semantic_intent_status") or ""
    )
    semantic_intent_first_attention = config_quality_summary.get(
        "semantic_intent_first_attention"
    )

    validation_passed = (
        str(validation_status) == "passed"
        if validation_status is not None
        else validate_status == 0
    )
    load_safe_to_install = (
        technical_status == "VALID_PACKAGE"
        and runtime_apply_allowed is True
        and runtime_apply_mode == "load_safe_apply"
        and validation_passed
    )
    semantic_handoff = _configure_semantic_handoff(
        operator_summary,
        config_quality_summary,
    )

    if not load_safe_to_install:
        next_report_to_open = "reports/operator_summary.json"
        interpretation = (
            "Package is not usable now; inspect reports/operator_summary.json first."
        )
    elif problem_checks or default_only_runtime_surfaces:
        next_report_to_open = "reports/contract_doctor.json"
        interpretation = (
            "Package is usable now according to reports/operator_summary.json; "
            "source and config-quality details remain diagnostic."
        )
    else:
        next_report_to_open = normal_apply_authority
        interpretation = (
            "Package is usable now according to reports/operator_summary.json; "
            "source and config-quality details remain diagnostic."
        )

    summary = {
        "schema_version": 1,
        "load_safe_to_install": load_safe_to_install,
        "use_config_now": load_safe_to_install,
        "use_config_now_scope": "load_safety_only",
        **semantic_handoff,
        "normal_apply_authority": normal_apply_authority,
        "runtime_apply_allowed": runtime_apply_allowed,
        "runtime_apply_mode": runtime_apply_mode,
        "technical_status": technical_status,
        "validation_status": "passed" if validation_passed else "failed",
        "apply_requested": apply_requested,
        "apply_status": apply_status,
        "source_strength": str(operator_summary.get("source_backed_status", "")),
        "source_gaps_apply_blocking": source_status_apply_blocking,
        "default_only_clean": not default_only_runtime_surfaces,
        "default_only_runtime_surfaces": default_only_runtime_surfaces,
        "config_quality_status": str(config_quality_summary.get("status", "")),
        "config_quality_problem_checks": problem_checks,
        "first_missing_source_action": operator_summary.get("first_missing_source_action"),
        "next_report_to_open": next_report_to_open,
        "interpretation": interpretation,
    }
    if semantic_intent_status:
        summary["semantic_intent_status"] = semantic_intent_status
    if semantic_intent_first_attention is not None:
        summary["semantic_intent_first_attention"] = str(
            semantic_intent_first_attention
        )
    return summary


def _build_config_proof_summary(
    *,
    operator_summary: Mapping[str, Any],
    validate_status: int,
    apply_requested: bool,
    apply_status: int | None,
    config_quality_summary: Mapping[str, Any],
) -> dict[str, Any]:
    runtime_contract = operator_summary.get("runtime_apply_contract", {})
    if not isinstance(runtime_contract, Mapping):
        runtime_contract = {}

    mechanic_visibility = operator_summary.get("mechanic_visibility_summary", {})
    if not isinstance(mechanic_visibility, Mapping):
        mechanic_visibility = {}

    default_only_runtime_surfaces = [
        str(surface)
        for surface in operator_summary.get("default_only_runtime_surfaces", [])
        if str(surface)
    ]
    forbidden_surfaces = [
        str(surface)
        for surface in config_quality_summary.get("legacy_surfaces_present", [])
        if str(surface)
    ]
    forbidden_normal_surfaces_status = str(
        config_quality_summary.get("forbidden_normal_surfaces_status") or ""
    )
    if forbidden_normal_surfaces_status not in {"clean", "attention"}:
        if "legacy_surfaces_present" in config_quality_summary:
            forbidden_normal_surfaces_status = (
                "clean" if not forbidden_surfaces else "attention"
            )
        else:
            forbidden_normal_surfaces_status = "unknown"
    forbidden_normal_surfaces_absent: bool | None
    if forbidden_normal_surfaces_status == "clean":
        forbidden_normal_surfaces_absent = True
    elif forbidden_normal_surfaces_status == "attention":
        forbidden_normal_surfaces_absent = False
    else:
        forbidden_normal_surfaces_absent = None
    problem_checks = [
        str(check)
        for check in config_quality_summary.get("problem_checks", [])
        if str(check)
    ]

    has_attention = bool(
        problem_checks
        or default_only_runtime_surfaces
        or forbidden_surfaces
        or str(config_quality_summary.get("status", "")) == "attention"
        or str(config_quality_summary.get("config_intent_self_audit_status", ""))
        == "attention"
    )

    return {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "normal_apply_authority": str(
            runtime_contract.get("apply_authority") or "reports/operator_summary.json"
        ),
        "technical_load_safe": bool(
            operator_summary.get("runtime_load_safe")
            or operator_summary.get("runtime_apply_allowed")
        ),
        "technical_status": str(operator_summary.get("technical_status", "")),
        "validation_status": "passed" if validate_status == 0 else "failed",
        "apply_requested": apply_requested,
        "apply_status": apply_status,
        "source_strength": str(operator_summary.get("source_backed_status", "")),
        "source_status_apply_blocking": bool(
            operator_summary.get("source_status_apply_blocking", False)
        ),
        "first_missing_source_action": operator_summary.get(
            "first_missing_source_action"
        ),
        "no_default_only_clean": not default_only_runtime_surfaces,
        "default_only_runtime_surfaces": default_only_runtime_surfaces,
        "forbidden_normal_surfaces_absent": forbidden_normal_surfaces_absent,
        "forbidden_normal_surfaces_status": forbidden_normal_surfaces_status,
        "forbidden_normal_surfaces_present": (
            forbidden_surfaces
            if forbidden_normal_surfaces_status != "unknown"
            else None
        ),
        "runtime_surface_boundary": [
            "GlobalValues.json",
            "Mulligan.json",
            "per-card <CARDID>.json",
            "Combo.json",
        ],
        "runtime_surface_boundary_details": {
            "unconditional_surfaces": [
                "GlobalValues.json",
                "Mulligan.json",
                "per-card <CARDID>.json",
            ],
            "conditional_surfaces": {
                "Combo.json": "complete_source_backed_combo",
            },
        },
        "darkbishop_boundary_status": str(
            config_quality_summary.get("darkbishop_boundary_status", "")
        ),
        "mechanic_visibility_non_blocking": bool(
            mechanic_visibility.get("non_blocking", True)
        ),
        "first_warning_boundary": mechanic_visibility.get("first_warning_boundary"),
        "runtime_json_status": str(config_quality_summary.get("runtime_json_status", "")),
        "source_to_runtime_status": str(
            config_quality_summary.get("source_to_runtime_status") or "missing"
        ),
        "currentness_status": str(
            config_quality_summary.get("currentness_status") or "missing"
        ),
        "closure_schema_current": bool(
            config_quality_summary.get("closure_schema_current", False)
        ),
        "cards_missing_closure": int(
            config_quality_summary.get("cards_missing_closure") or 0
        ),
        "cards_total": int(config_quality_summary.get("cards_total") or 0),
        "cards_with_closure": int(
            config_quality_summary.get("cards_with_closure") or 0
        ),
        "semantic_intent_status": str(
            config_quality_summary.get("semantic_intent_status", "")
        ),
        "surface_intent_status": str(
            config_quality_summary.get("surface_intent_status", "")
        ),
        "surface_intent_present": bool(
            config_quality_summary.get("surface_intent_present", False)
        ),
        "surface_intent_surface_count": int(
            config_quality_summary.get("surface_intent_surface_count") or 0
        ),
        "surface_intent_fallback_intent_rows": int(
            config_quality_summary.get("surface_intent_fallback_intent_rows") or 0
        ),
        "surface_intent_legacy_policy_surface_rows": [
            str(surface)
            for surface in config_quality_summary.get(
                "surface_intent_legacy_policy_surface_rows", []
            )
            if str(surface)
        ],
        "surface_intent_first_attention": (
            str(config_quality_summary.get("surface_intent_first_attention"))
            if config_quality_summary.get("surface_intent_first_attention") is not None
            else None
        ),
        "config_intent_self_audit_status": str(
            config_quality_summary.get("config_intent_self_audit_status", "")
        ),
        "config_intent_first_attention": (
            str(config_quality_summary.get("config_intent_first_attention"))
            if config_quality_summary.get("config_intent_first_attention") is not None
            else None
        ),
        "config_intent_runtime_files_without_intent": int(
            config_quality_summary.get("config_intent_runtime_files_without_intent")
            or 0
        ),
        "config_quality_status": str(config_quality_summary.get("status", "")),
        "config_quality_problem_checks": problem_checks,
        "next_report_to_open": (
            "reports/contract_doctor.json"
            if has_attention
            else str(
                runtime_contract.get("apply_authority")
                or "reports/operator_summary.json"
            )
        ),
    }


def _build_handoff_contract(
    *,
    operator_summary: Mapping[str, Any],
    acceptance_summary: Mapping[str, Any],
    config_proof_summary: Mapping[str, Any],
    config_quality_summary: Mapping[str, Any],
) -> dict[str, Any]:
    runtime_contract = operator_summary.get("runtime_apply_contract", {})
    if not isinstance(runtime_contract, Mapping):
        runtime_contract = {}

    normal_apply_authority = str(
        acceptance_summary.get("normal_apply_authority")
        or config_proof_summary.get("normal_apply_authority")
        or runtime_contract.get("apply_authority")
        or "reports/operator_summary.json"
    )
    default_only_runtime_surfaces = [
        str(surface)
        for surface in (
            acceptance_summary.get("default_only_runtime_surfaces")
            or config_proof_summary.get("default_only_runtime_surfaces")
            or []
        )
        if str(surface)
    ]
    problem_checks = [
        str(check)
        for check in config_quality_summary.get("problem_checks", [])
        if str(check)
    ]
    source_status_apply_blocking = bool(
        operator_summary.get(
            "source_status_apply_blocking",
            acceptance_summary.get("source_gaps_apply_blocking", False),
        )
    )
    source_gaps_apply_blocking = bool(
        acceptance_summary.get(
            "source_gaps_apply_blocking",
            source_status_apply_blocking,
        )
    )
    forbidden_normal_surfaces_absent = config_proof_summary.get(
        "forbidden_normal_surfaces_absent"
    )
    semantic_handoff = _configure_semantic_handoff(
        operator_summary,
        config_quality_summary,
    )
    status = (
        "clean"
        if (
            bool(acceptance_summary.get("use_config_now"))
            and semantic_handoff["semantic_handoff_status"] == "closed"
            and normal_apply_authority == "reports/operator_summary.json"
            and not source_status_apply_blocking
            and not source_gaps_apply_blocking
            and bool(acceptance_summary.get("default_only_clean"))
            and not default_only_runtime_surfaces
            and forbidden_normal_surfaces_absent is True
            and str(config_proof_summary.get("runtime_json_status") or "") == "clean"
            and str(config_proof_summary.get("source_to_runtime_status") or "")
            == "clean"
            and str(config_proof_summary.get("config_intent_self_audit_status") or "")
            in {"", "clean"}
            and int(
                config_proof_summary.get("config_intent_runtime_files_without_intent")
                or 0
            )
            == 0
            and str(config_quality_summary.get("status") or "") == "clean"
            and not problem_checks
        )
        else "attention"
    )

    return {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "status": status,
        "normal_apply_authority": normal_apply_authority,
        "single_apply_authority_confirmed": (
            normal_apply_authority == "reports/operator_summary.json"
        ),
        "load_safe_to_install": bool(
            acceptance_summary.get(
                "load_safe_to_install",
                acceptance_summary.get("use_config_now", False),
            )
        ),
        "use_config_now": bool(acceptance_summary.get("use_config_now")),
        "use_config_now_scope": "load_safety_only",
        **semantic_handoff,
        "runtime_apply_allowed": bool(
            acceptance_summary.get("runtime_apply_allowed", False)
        ),
        "runtime_apply_mode": str(acceptance_summary.get("runtime_apply_mode", "")),
        "technical_status": str(acceptance_summary.get("technical_status", "")),
        "source_strength": str(acceptance_summary.get("source_strength", "")),
        "source_status_apply_blocking": source_status_apply_blocking,
        "source_gaps_apply_blocking": source_gaps_apply_blocking,
        "first_missing_source_action": (
            acceptance_summary.get("first_missing_source_action")
            or operator_summary.get("first_missing_source_action")
        ),
        "default_only_clean": bool(acceptance_summary.get("default_only_clean")),
        "default_only_runtime_surfaces": default_only_runtime_surfaces,
        "forbidden_normal_surfaces_absent": forbidden_normal_surfaces_absent,
        "forbidden_normal_surfaces_status": str(
            config_proof_summary.get("forbidden_normal_surfaces_status") or ""
        ),
        "runtime_surface_boundary": [
            str(surface)
            for surface in config_proof_summary.get("runtime_surface_boundary", [])
            if str(surface)
        ],
        "darkbishop_boundary_status": str(
            config_proof_summary.get("darkbishop_boundary_status") or ""
        ),
        "runtime_json_status": str(
            config_proof_summary.get("runtime_json_status") or ""
        ),
        "source_to_runtime_status": str(
            config_proof_summary.get("source_to_runtime_status") or ""
        ),
        "currentness_status": str(
            config_proof_summary.get("currentness_status") or ""
        ),
        "closure_schema_current": bool(
            config_proof_summary.get("closure_schema_current", False)
        ),
        "cards_missing_closure": int(
            config_proof_summary.get("cards_missing_closure") or 0
        ),
        "semantic_intent_status": str(
            config_proof_summary.get("semantic_intent_status") or ""
        ),
        "surface_intent_status": str(
            config_proof_summary.get("surface_intent_status") or ""
        ),
        "surface_intent_present": bool(
            config_proof_summary.get("surface_intent_present", False)
        ),
        "surface_intent_surface_count": int(
            config_proof_summary.get("surface_intent_surface_count") or 0
        ),
        "surface_intent_fallback_intent_rows": int(
            config_proof_summary.get("surface_intent_fallback_intent_rows") or 0
        ),
        "surface_intent_legacy_policy_surface_rows": [
            str(surface)
            for surface in config_proof_summary.get(
                "surface_intent_legacy_policy_surface_rows", []
            )
            if str(surface)
        ],
        "surface_intent_first_attention": (
            str(config_proof_summary.get("surface_intent_first_attention"))
            if config_proof_summary.get("surface_intent_first_attention") is not None
            else None
        ),
        **(
            {
                "config_intent_self_audit_status": str(
                    config_proof_summary.get("config_intent_self_audit_status") or ""
                ),
                "config_intent_first_attention": (
                    str(config_proof_summary.get("config_intent_first_attention"))
                    if config_proof_summary.get("config_intent_first_attention")
                    is not None
                    else None
                ),
                "config_intent_runtime_files_without_intent": int(
                    config_proof_summary.get(
                        "config_intent_runtime_files_without_intent"
                    )
                    or 0
                ),
            }
            if "config_intent_self_audit_status" in config_proof_summary
            else {}
        ),
        "mechanic_runtime_discipline_status": str(
            config_quality_summary.get("mechanic_runtime_discipline_status") or ""
        ),
        "config_quality_status": str(config_quality_summary.get("status") or ""),
        "config_quality_problem_checks": problem_checks,
        "next_report_to_open": str(
            acceptance_summary.get("next_report_to_open")
            or config_proof_summary.get("next_report_to_open")
            or "reports/operator_summary.json"
        ),
    }


def _configure_semantic_handoff(
    operator_summary: Mapping[str, Any],
    config_quality_summary: Mapping[str, Any],
) -> dict[str, Any]:
    quality_projection = semantic_handoff_projection(config_quality_summary)
    operator_projection = semantic_handoff_projection(operator_summary)
    if (
        quality_projection["semantic_handoff_status"] == "closed"
        and operator_projection["semantic_handoff_status"] != "closed"
    ):
        return operator_projection
    return quality_projection


def _first_source_status_reason(operator_summary: dict[str, Any]) -> str:
    reasons = operator_summary.get("source_status_reasons") or []
    if isinstance(reasons, list) and reasons:
        return str(reasons[0])
    return ""


def _read_optional_json(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        payload = read_json(Path(path))
    except FileNotFoundError:
        return None
    return payload if isinstance(payload, dict) else None


def _normalize_operator_date(value: Any) -> date:
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as error:
        raise ValueError("current_date_invalid") from error


def _load_source_candidate_plan(
    path: Path,
    *,
    deck_name: str,
    deck_code: str,
    explicit_source_urls: list[str],
    current_date: date | None,
) -> dict[str, Any]:
    explicit_source_urls = dedupe_acquisition_urls(explicit_source_urls)
    try:
        payload = read_json(path)
    except (FileNotFoundError, ValueError, TypeError):
        return _rebuild_source_candidate_plan(
            deck_name=deck_name,
            deck_code=deck_code,
            explicit_source_urls=explicit_source_urls,
            current_date=current_date,
        )
    if not _source_candidate_plan_is_usable(payload, explicit_source_urls):
        return _rebuild_source_candidate_plan(
            deck_name=deck_name,
            deck_code=deck_code,
            explicit_source_urls=explicit_source_urls,
            current_date=current_date,
        )
    return dict(payload)


def _rebuild_source_candidate_plan(
    *,
    deck_name: str,
    deck_code: str,
    explicit_source_urls: list[str],
    current_date: date | None,
) -> dict[str, Any]:
    return build_source_candidate_plan(
        deck_name=deck_name,
        deck_code=deck_code,
        deck_identity={"deck_name": deck_name, "cards": []},
        candidate_archetypes={},
        explicit_source_urls=explicit_source_urls,
        current_date=current_date,
    )


def _source_candidate_plan_is_usable(
    payload: Any,
    explicit_source_urls: list[str],
) -> bool:
    if not isinstance(payload, Mapping):
        return False
    if payload.get("authority") != "diagnostic_source_candidate_plan":
        return False
    candidate_urls = payload.get("candidate_urls")
    source_urls = payload.get("source_urls")
    if not isinstance(candidate_urls, list) or not isinstance(source_urls, list):
        return False
    if not all(isinstance(url, str) for url in [*candidate_urls, *source_urls]):
        return False
    if not all(is_acquisition_url(url) for url in [*candidate_urls, *source_urls]):
        return False
    row_urls = _raw_plan_candidate_row_urls(payload)
    if not all(is_acquisition_url(url) for url in row_urls):
        return False
    expected_source_urls = dedupe_acquisition_urls(
        [*explicit_source_urls, *candidate_urls]
    )
    return _plan_urls(payload, "source_urls") == expected_source_urls


def _plan_urls(plan: Mapping[str, Any], key: str) -> list[str]:
    values = plan.get(key)
    if not isinstance(values, list):
        return []
    return dedupe_acquisition_urls(values)


def _plan_candidate_row_urls(plan: Mapping[str, Any]) -> list[str]:
    return dedupe_acquisition_urls(_raw_plan_candidate_row_urls(plan))


def _raw_plan_candidate_row_urls(plan: Mapping[str, Any]) -> list[str]:
    rows = plan.get("candidate_url_rows")
    if not isinstance(rows, list):
        return []
    return _dedupe_preserve_order(
        [str(row.get("url", "")) for row in rows if isinstance(row, Mapping)]
    )


def _compact_source_candidate_plan_summary(
    plan: Mapping[str, Any],
    *,
    source_candidate_urls: list[str],
) -> dict[str, Any]:
    return {
        "authority": "diagnostic_source_candidate_plan",
        "apply_blocking": False,
        "source_status_apply_blocking": False,
        "candidate_registry_url_count": _plan_nonnegative_int(
            plan.get("candidate_registry_url_count"),
            default=len(source_candidate_urls),
        ),
        "explicit_source_url_count": _plan_nonnegative_int(
            plan.get("explicit_source_url_count"),
            default=0,
        ),
        "query_count": _plan_nonnegative_int(plan.get("query_count"), default=0),
        "first_missing_source_action": str(
            plan.get("first_missing_source_action") or ""
        ),
    }


def _plan_nonnegative_int(value: Any, *, default: int) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _source_search_records(path: str | Path | None) -> list[dict[str, Any]]:
    if not path:
        return []
    payload = read_json(path)
    records = payload.get("records", payload) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, dict)]


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result
