from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from hsconfig.commands.apply import apply_payload, validate_payload
from hsconfig.commands.common import emit_result
from hsconfig.commands.source_workflow import (
    draft_source_documents_payload,
    research_deck_payload,
    source_acquire_payload,
    source_autopilot_payload,
    source_manifest_payload,
)
from hsconfig.config_quality_contract import build_config_quality_report
from hsconfig.package_builder import prepare_package_payload
from hsconfig.io import read_json, write_json
from hsconfig.operator_summary import refresh_generated_file_accounting
from hsconfig.output_ownership_manifest import build_output_ownership_manifest
from hsconfig.package_io import prepare_research_output_dir
from hsconfig.source_bundle import build_source_bundle
from hsconfig.source_candidate_registry import candidate_urls, source_candidates_for_deck
from hsconfig.source_closure_intake import (
    SOURCE_CLOSURE_INTAKE_RECEIPT_RELATIVE_PATH,
    build_source_closure_intake_receipt,
    summarize_source_closure_intake,
)
from hsconfig.source_evidence_closure import build_source_evidence_closure_report


def run_configure_command(args: argparse.Namespace) -> int:
    try:
        payload, status = configure_payload(args)
    except Exception as exc:
        payload, status = _finish_stage_exception_for_args(args, "configure", exc)
    return emit_result(payload, bool(getattr(args, "json", False)), status)


def configure_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
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
    source_autopilot_path = None
    source_closure_intake_receipt_path = None
    source_candidate_urls: list[str] = []
    source_urls: list[str] = []
    if bool(getattr(args, "online_source", False)):
        explicit_source_urls = list(getattr(args, "source_url", []) or [])
        source_candidates = source_candidates_for_deck(args.deck_name, args.deck_code)
        source_candidate_urls = candidate_urls(source_candidates)
        source_urls = _dedupe_preserve_order([*explicit_source_urls, *source_candidate_urls])
        try:
            acquire_payload, acquire_status = source_acquire_payload(
                SimpleNamespace(
                    **common,
                    source_url=source_urls,
                    candidate_registry_url_count=len(source_candidate_urls),
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
                    current_date=getattr(args, "current_date", None),
                    out=str(source_acquisition_dir),
                )
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
            autopilot_payload, autopilot_status = source_autopilot_payload(
                SimpleNamespace(
                    **common,
                    source_search_results_json=args.source_search_results_json,
                    current_date=getattr(args, "current_date", None),
                    out=str(autopilot_dir),
                )
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
        source_autopilot_path = autopilot_dir
        source_documents_json = autopilot_dir / "source_documents.json"
    elif getattr(args, "source_evidence_json", None):
        try:
            draft_payload, draft_status = draft_source_documents_payload(
                SimpleNamespace(
                    **common,
                    source_evidence_json=args.source_evidence_json,
                    out=str(draft_dir),
                )
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
        research_payload, research_status = research_deck_payload(
            SimpleNamespace(
                **common,
                out=str(research_dir),
                source_documents_json=str(source_documents_json) if source_documents_json else None,
                source_evidence_json=research_source_evidence_json,
                guide_sources_json=None,
                claims_json=None,
                skip_semantic_fetch=False,
                auto_research_fallback=True,
            )
        )
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
                json=True,
            )
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

    apply_status = None
    if bool(getattr(args, "apply", False)):
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

    return _finish(
        out,
        "OK",
        {
            "manifest_path": str(manifest_dir / "source_research_manifest.json"),
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
            "apply_performed": bool(getattr(args, "apply", False)),
            "apply_status": apply_status,
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
    if problem_checks:
        summary["next_action"] = "run_contract_doctor_for_details"
    return summary


def _build_config_quality_summary(package_dir: Path) -> dict[str, Any]:
    try:
        return _compact_config_quality_summary(build_config_quality_report(package_dir))
    except Exception as exc:
        return {
            "status": "attention",
            "authority": "diagnostic_only",
            "apply_blocking": False,
            "runtime_write_performed": False,
            "problem_count": 1,
            "problem_checks": ["config_quality_summary_failed"],
            "next_action": "run_contract_doctor_for_details",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _build_acceptance_summary(
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

    validation_passed = validate_status == 0
    apply_passed = (not apply_requested) or apply_status == 0
    use_config_now = (
        technical_status == "VALID_PACKAGE"
        and runtime_apply_allowed
        and runtime_apply_mode == "load_safe_apply"
        and validation_passed
        and apply_passed
    )

    if not use_config_now:
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

    return {
        "schema_version": 1,
        "use_config_now": use_config_now,
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


def _first_source_status_reason(operator_summary: dict[str, Any]) -> str:
    reasons = operator_summary.get("source_status_reasons") or []
    if isinstance(reasons, list) and reasons:
        return str(reasons[0])
    return ""


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
