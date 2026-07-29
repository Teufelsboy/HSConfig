from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Mapping

from hsconfig.commands.common import run_payload_command
from hsconfig.deck_identity import build_deck_identity
from hsconfig.evidence_contract import load_policy_profile
from hsconfig.guide_source_builder import build_candidate_archetypes
from hsconfig.hearthstonejson import fetch_latest_cards, fetch_latest_collectible_cards
from hsconfig.input_loading import (
    fixture_row_for,
    load_cards,
    load_source_evidence,
    load_source_search_records,
)
from hsconfig.io import read_json, write_json
from hsconfig.internal_source_authority import (
    InternalSourceAuthorityHandoff,
    _consume_acquired_search_records_handoff,
    _issue_acquired_search_records_handoff,
    _issue_generated_source_documents_handoff,
    reject_caller_supplied_source_authority,
)
from hsconfig.package_io import prepare_research_output_dir
from hsconfig.preconfig_context import build_preconfig_context
from hsconfig.research_status_sync import build_research_status_sync_report
from hsconfig.source_acquisition import collect_public_source_records, fetchable_source_url
from hsconfig.source_acquisition_closure import (
    acquisition_closure_payload,
    build_acquisition_closure,
    freeze_source_bundle,
)
from hsconfig.source_acquisition_provenance import FIXTURE_MAP, LIVE_HTTP
from hsconfig.source_autopilot import build_source_autopilot_bundle
from hsconfig.source_claim_compiler import compile_source_search_records
from hsconfig.source_closure_optimizer import build_source_closure_optimizer_report
from hsconfig.source_candidate_plan import (
    build_source_candidate_plan,
    dedupe_acquisition_urls,
)
from hsconfig.source_document_drafter import draft_source_documents
from hsconfig.source_evidence_verifier import verify_source_documents
from hsconfig.source_research_manifest import build_source_research_manifest
from hsconfig.strong_closure_dossier import build_strong_closure_dossier


def run_source_manifest_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, source_manifest_payload)


def run_draft_source_documents_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, draft_source_documents_payload)


def run_source_autopilot_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, source_autopilot_payload)


def run_source_acquire_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, source_acquire_payload)


def run_research_deck_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, research_deck_payload)


def run_research_status_sync_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, research_status_sync_payload)


def run_strong_closure_dossier_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, strong_closure_dossier_payload)


def run_source_closure_optimizer_command(args: argparse.Namespace) -> int:
    research_result_paths = (
        _research_result_paths(Path(args.research_results_dir))
        if getattr(args, "research_results_dir", None)
        else None
    )
    reports = [
        build_source_closure_optimizer_report(
            package_dir=package,
            candidate_proof_path=args.candidate_proof_json,
            research_result_paths=research_result_paths,
        )
        for package in args.package
    ]
    payload = {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "source_status_apply_blocking": False,
        "package_count": len(reports),
        "reports": reports,
    }
    out_path = Path(args.out)
    _assert_safe_closure_optimizer_output(out_path)
    write_json(out_path, payload)

    if args.markdown_out:
        md_path = Path(args.markdown_out)
        _assert_safe_closure_optimizer_output(md_path)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(
            _format_source_closure_optimizer_markdown(payload),
            encoding="utf-8",
        )

    print(f"Wrote source closure optimizer report: {out_path}")
    return 0


def source_manifest_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    out = Path(args.out)
    prepare_research_output_dir(out)

    cards_payload = load_cards(
        args.cards_json,
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        allow_placeholder=args.allow_placeholder,
    )
    deck_identity = build_deck_identity(
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        cards=cards_payload["cards"],
        hero_dbf_id=cards_payload.get("hero_dbf_id"),
        format=cards_payload.get("format"),
        sideboards=cards_payload.get("sideboards", []),
    )
    candidate_archetypes = build_candidate_archetypes(
        deck_name=args.deck_name,
        deck_identity=deck_identity,
        card_roles={},
        source_documents=[],
    )
    source_candidate_plan = build_source_candidate_plan(
        deck_name=args.deck_name,
        deck_identity=deck_identity,
        candidate_archetypes=candidate_archetypes,
        explicit_source_urls=list(getattr(args, "source_url", []) or []),
        current_date=getattr(args, "current_date", None),
    )
    manifest = build_source_research_manifest(
        deck_name=args.deck_name,
        deck_identity=deck_identity,
        candidate_archetypes=candidate_archetypes,
        fixture_row=fixture_row_for(args.deck_name),
        current_date=getattr(args, "current_date", None),
        attempted_queries=_candidate_query_texts(source_candidate_plan),
        checked_dossier=True,
        policy_profile=load_policy_profile(),
    )
    output_path = out / "source_research_manifest.json"
    candidate_plan_path = out / "source_candidate_plan.json"
    write_json(output_path, manifest)
    write_json(candidate_plan_path, source_candidate_plan)
    return (
        {
            "status": "OK",
            "deck_name": args.deck_name,
            "deck_slug": deck_identity["deck_slug"],
            "written_files": [str(output_path), str(candidate_plan_path)],
        },
        0,
    )


def draft_source_documents_payload(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], int]:
    out = Path(args.out)
    prepare_research_output_dir(out)

    cards_payload = load_cards(
        args.cards_json,
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        allow_placeholder=args.allow_placeholder,
    )
    deck_identity = build_deck_identity(
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        cards=cards_payload["cards"],
        hero_dbf_id=cards_payload.get("hero_dbf_id"),
        format=cards_payload.get("format"),
        sideboards=cards_payload.get("sideboards", []),
    )
    draft = draft_source_documents(
        deck_name=args.deck_name,
        deck_identity=deck_identity,
        evidence_rows=load_source_evidence(args.source_evidence_json),
    )
    source_documents_payload = {
        "schema_version": 1,
        "deck_name": args.deck_name,
        "source_documents": draft["source_documents"],
    }
    report = {
        "schema_version": 1,
        "deck_name": args.deck_name,
        "draft_summary": draft["draft_summary"],
        "unresolved_mentions": draft["unresolved_mentions"],
        "source_evidence_report": verify_source_documents(draft["source_documents"]),
    }
    source_path = out / "source_documents.json"
    report_path = out / "source_document_draft_report.json"
    write_json(source_path, source_documents_payload)
    write_json(report_path, report)
    return (
        {
            "status": "OK",
            "deck_name": args.deck_name,
            "deck_slug": deck_identity["deck_slug"],
            "written_files": [str(source_path), str(report_path)],
            "draft_summary": draft["draft_summary"],
        },
        0,
    )


def source_autopilot_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    reject_caller_supplied_source_authority(args)
    payload, status, _documents = _source_autopilot_payload(args)
    return payload, status


def source_autopilot_for_configure(
    args: argparse.Namespace,
    source_authority_handoff: InternalSourceAuthorityHandoff,
) -> tuple[dict[str, Any], int, InternalSourceAuthorityHandoff]:
    source_records, lineage = _consume_acquired_search_records_handoff(
        source_authority_handoff
    )
    payload, status, documents = _source_autopilot_payload(
        args,
        source_records=source_records,
    )
    output_handoff = _issue_generated_source_documents_handoff(
        lineage,
        documents,
    )
    return payload, status, output_handoff


def _source_autopilot_payload(
    args: argparse.Namespace,
    *,
    source_records: list[dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], int, list[dict[str, Any]]]:
    out = Path(args.out)
    prepare_research_output_dir(out)

    cards_payload = load_cards(
        args.cards_json,
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        allow_placeholder=args.allow_placeholder,
    )
    deck_identity = build_deck_identity(
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        cards=cards_payload["cards"],
        hero_dbf_id=cards_payload.get("hero_dbf_id"),
        format=cards_payload.get("format"),
        sideboards=cards_payload.get("sideboards", []),
    )
    source_records = (
        source_records
        if source_records is not None
        else load_source_search_records(args.source_search_results_json)
    )

    bundle = build_source_autopilot_bundle(
        deck_name=args.deck_name,
        deck_identity=deck_identity,
        source_search_records=source_records,
        current_date=getattr(args, "current_date", None),
    )
    ranked_path = out / "ranked_sources.json"
    evidence_path = out / "source_evidence_rows.json"
    source_path = out / "source_documents.json"
    draft_report_path = out / "source_document_draft_report.json"
    report_path = out / "source_autopilot_report.json"
    write_json(ranked_path, {"schema_version": 1, "ranked_sources": bundle["ranked_sources"]})
    write_json(
        evidence_path,
        {"schema_version": 1, "evidence_rows": bundle["source_evidence_rows"]},
    )
    write_json(source_path, bundle["source_documents_payload"])
    write_json(draft_report_path, bundle["source_document_draft_report"])
    write_json(report_path, bundle["source_autopilot_report"])
    payload_and_status = (
        {
            "status": "OK",
            "deck_name": args.deck_name,
            "deck_slug": deck_identity["deck_slug"],
            "source_autopilot_report": str(report_path),
            "source_documents_json": str(source_path),
            "source_evidence_json": str(evidence_path),
            "written_files": [
                str(ranked_path),
                str(evidence_path),
                str(source_path),
                str(draft_report_path),
                str(report_path),
            ],
        },
        0,
    )
    return (
        *payload_and_status,
        bundle["source_documents_payload"]["source_documents"],
    )


def source_acquire_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    payload, status, _handoff = _source_acquire_payload(args)
    return payload, status


def source_acquire_for_configure(
    args: argparse.Namespace,
) -> tuple[dict[str, Any], int, InternalSourceAuthorityHandoff]:
    payload, status, handoff = _source_acquire_payload(
        args,
        issue_authority_handoff=True,
    )
    if handoff is None:
        raise ValueError("source_acquisition_handoff_not_issued")
    return payload, status, handoff


def _source_acquire_payload(
    args: argparse.Namespace,
    *,
    issue_authority_handoff: bool = False,
) -> tuple[dict[str, Any], int, InternalSourceAuthorityHandoff | None]:
    out = Path(args.out)
    prepare_research_output_dir(out)
    source_urls = dedupe_acquisition_urls(
        list(getattr(args, "source_url", []) or [])
    )

    cards_payload = load_cards(
        getattr(args, "cards_json", None),
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        allow_placeholder=bool(getattr(args, "allow_placeholder", False)),
    )
    deck_identity = build_deck_identity(
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        cards=cards_payload["cards"],
        hero_dbf_id=cards_payload.get("hero_dbf_id"),
        format=cards_payload.get("format"),
        sideboards=cards_payload.get("sideboards", []),
    )
    policy_profile = load_policy_profile()
    candidate_archetypes = build_candidate_archetypes(
        deck_name=args.deck_name,
        deck_identity=deck_identity,
        card_roles={},
        source_documents=[],
    )
    source_candidate_plan = build_source_candidate_plan(
        deck_name=args.deck_name,
        deck_identity=deck_identity,
        candidate_archetypes=candidate_archetypes,
        explicit_source_urls=source_urls,
        current_date=getattr(args, "current_date", None),
    )
    manifest_path_value = getattr(args, "source_research_manifest_json", None)
    if manifest_path_value:
        research_manifest = read_json(manifest_path_value)
        if not isinstance(research_manifest, dict):
            raise ValueError("source_research_manifest_json_invalid")
    else:
        research_manifest = build_source_research_manifest(
            deck_name=args.deck_name,
            deck_identity=deck_identity,
            candidate_archetypes=candidate_archetypes,
            fixture_row=fixture_row_for(args.deck_name),
            current_date=getattr(args, "current_date", None),
            attempted_queries=_candidate_query_texts(source_candidate_plan),
            checked_dossier=True,
            policy_profile=policy_profile,
        )
    fixture_map_path = getattr(args, "source_fixture_url_map_json", None)
    acquired = collect_public_source_records(
        deck_name=args.deck_name,
        deck_identity=deck_identity,
        source_urls=source_urls,
        current_date=getattr(args, "current_date", None),
        fetcher=_fixture_fetcher(fixture_map_path),
        resolver=_fixture_resolver(fixture_map_path),
        timeout_seconds=float(getattr(args, "source_fetch_timeout_seconds", 6.0)),
        candidate_registry_url_count=int(
            getattr(args, "candidate_registry_url_count", 0) or 0
        ),
        acquisition_mode=FIXTURE_MAP if fixture_map_path else LIVE_HTTP,
        checked_dossier=research_manifest.get("checked_dossier") is True,
        policy_profile=policy_profile,
    )
    compiled = compile_source_search_records(
        deck_name=args.deck_name,
        deck_identity=deck_identity,
        acquired_records=acquired["source_records"],
        current_date=getattr(args, "current_date", None),
    )
    for acquired_record, compiled_record in zip(
        acquired["source_records"],
        compiled["records"],
        strict=True,
    ):
        for key in (
            "evidence_id",
            "source_id",
            "source_identity",
            "as_of_date",
            "content_sha256",
            "acquisition_provenance",
        ):
            compiled_record[key] = acquired_record[key]
    closure = build_acquisition_closure(
        deck_identity=deck_identity,
        research_manifest=research_manifest,
        acquisition_report=acquired["source_acquisition_report"],
        source_records=compiled["records"],
        policy_profile=policy_profile,
    )
    closure_payload = acquisition_closure_payload(closure)
    frozen_bundle = (
        freeze_source_bundle(
            deck_identity=deck_identity,
            closure=closure,
            source_records=compiled["records"],
            policy_profile=policy_profile,
        )
        if closure.status != "open"
        else None
    )
    authority_handoff = (
        _issue_acquired_search_records_handoff(compiled["records"])
        if issue_authority_handoff
        else None
    )

    acquisition_path = out / "source_acquisition_report.json"
    compiler_path = out / "source_claim_compiler_report.json"
    source_search_path = out / "source_search_results.json"
    closure_path = out / "source_acquisition_closure.json"
    frozen_bundle_path = out / "frozen_source_bundle.json"
    write_json(acquisition_path, acquired["source_acquisition_report"])
    write_json(compiler_path, compiled["source_claim_compiler_report"])
    write_json(source_search_path, compiled)
    write_json(closure_path, closure_payload)
    if frozen_bundle is not None:
        write_json(frozen_bundle_path, frozen_bundle)
    payload_and_status = (
        {
            "status": "OK",
            "deck_name": args.deck_name,
            "deck_slug": deck_identity["deck_slug"],
            "source_search_results_json": str(source_search_path),
            "source_acquisition_report": acquired["source_acquisition_report"],
            "source_claim_compiler_report": compiled["source_claim_compiler_report"],
            "source_acquisition_closure": closure_payload,
            "source_acquisition_closure_json": str(closure_path),
            "frozen_source_bundle": frozen_bundle,
            "frozen_source_bundle_json": (
                str(frozen_bundle_path) if frozen_bundle is not None else None
            ),
            "frozen_source_bundle_sha256": (
                frozen_bundle["content_sha256"]
                if frozen_bundle is not None
                else None
            ),
            "source_acquisition_report_json": str(acquisition_path),
            "source_claim_compiler_report_json": str(compiler_path),
            "written_files": [
                str(acquisition_path),
                str(compiler_path),
                str(source_search_path),
                str(closure_path),
                *(
                    [str(frozen_bundle_path)]
                    if frozen_bundle is not None
                    else []
                ),
            ],
        },
        0,
    )
    return *payload_and_status, authority_handoff


def _candidate_query_texts(
    source_candidate_plan: Mapping[str, Any],
) -> list[str]:
    rows = source_candidate_plan.get("queries")
    if not isinstance(rows, list):
        return []
    return [
        str(row.get("query", "")).strip()
        for row in rows
        if isinstance(row, Mapping) and str(row.get("query", "")).strip()
    ]


def _fixture_fetcher(path_value: str | None):
    if not path_value:
        return None
    mapping = read_json(path_value)
    if not isinstance(mapping, dict):
        raise ValueError("--source-fixture-url-map-json must contain a URL to file path object")
    normalized_mapping = _fetchable_fixture_mapping(mapping)

    def fetcher(url: str, timeout_seconds: float) -> tuple[int, str, bytes]:
        del timeout_seconds
        fixture_path = normalized_mapping.get(url)
        if fixture_path is None:
            return 404, "text/plain", b"fixture url not mapped"
        return 200, "text/html", Path(str(fixture_path)).read_bytes()

    return fetcher


def _fetchable_fixture_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for url, fixture_path in mapping.items():
        original_url = str(url)
        normalized[original_url] = fixture_path
        normalized[fetchable_source_url(original_url)] = fixture_path
    return normalized


def _fixture_resolver(path_value: str | None):
    if not path_value:
        return None

    def resolver(hostname: str) -> list[str]:
        del hostname
        return ["93.184.216.34"]

    return resolver


def research_deck_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    reject_caller_supplied_source_authority(args)
    return _research_deck_payload(args)


def research_deck_for_configure(
    args: argparse.Namespace,
    source_authority_handoff: InternalSourceAuthorityHandoff,
) -> tuple[dict[str, Any], int]:
    return _research_deck_payload(
        args,
        source_authority_handoff=source_authority_handoff,
    )


def _research_deck_payload(
    args: argparse.Namespace,
    *,
    source_authority_handoff: InternalSourceAuthorityHandoff | None = None,
) -> tuple[dict[str, Any], int]:
    out = Path(args.out)
    prepare_research_output_dir(out)
    if not hasattr(args, "skip_semantic_fetch"):
        args.skip_semantic_fetch = True

    context = build_preconfig_context(
        args,
        source_authority_handoff=source_authority_handoff,
        source_authority_consumer="research",
        fetch_latest_cards_fn=fetch_latest_cards,
        fetch_latest_collectible_cards_fn=fetch_latest_collectible_cards,
    )
    deck_identity = context["deck_identity"]
    write_json(out / "deck_fingerprint.json", context["deck_fingerprint"])
    write_json(out / "candidate_archetypes.json", context["candidate_archetypes"])
    write_json(out / "guide_sources.json", context["guide_sources_generated"])
    write_json(out / "guide_builder_receipt.json", context["guide_builder_receipt"])
    write_json(out / "identity_graph_report.json", context["identity_graph_report"])
    write_json(out / "identity_gap_report.json", context["identity_gap_report"])
    write_json(out / "card_data_intake_report.json", context["card_data_intake_report"])
    write_json(
        out / "source_evidence_verification_report.json",
        context["source_evidence_report"],
    )
    if context.get("source_document_draft_report") is not None:
        report = context["source_document_draft_report"]
        write_json(
            out / "source_document_draft_report.json",
            {
                "schema_version": 1,
                "deck_name": args.deck_name,
                "draft_summary": report["draft_summary"],
                "unresolved_mentions": report["unresolved_mentions"],
                "source_evidence_report": verify_source_documents(
                    report["source_documents"]
                ),
            },
        )

    written_files = [str(path) for path in sorted(out.glob("*.json"))]
    return (
        {
            "status": "OK",
            "deck_name": args.deck_name,
            "deck_slug": deck_identity["deck_slug"],
            "source_depth_status": context["guide_builder_receipt"][
                "source_depth_status"
            ],
            "written_files": written_files,
        },
        0,
    )


def research_status_sync_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    report = build_research_status_sync_report(
        package_dir=args.package,
        research_result_paths=_research_result_paths(Path(args.research_results_dir)),
    )
    if getattr(args, "out", None):
        out = Path(args.out)
        _assert_safe_research_status_sync_output(out, package_dir=Path(args.package))
        write_json(out, report)
    return report, 0


def strong_closure_dossier_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    research_results_dir = getattr(args, "research_results_dir", None)
    report = build_strong_closure_dossier(
        package_dir=args.package,
        research_result_paths=(
            _research_result_paths(Path(research_results_dir))
            if research_results_dir
            else []
        ),
        source_autopilot_report_path=getattr(
            args, "source_autopilot_report_json", None
        ),
    )
    if getattr(args, "out", None):
        out = Path(args.out)
        _assert_safe_diagnostic_json_output(
            out,
            package_dir=Path(args.package),
            command_name="strong-closure-dossier",
        )
        write_json(out, report)
    return report, 0


def _research_result_paths(research_results_dir: Path) -> list[Path]:
    if not research_results_dir.exists():
        return []
    if research_results_dir.is_file():
        return [research_results_dir]
    return sorted(research_results_dir.rglob("*.json"), key=lambda path: str(path))


def _assert_safe_research_status_sync_output(path: Path, *, package_dir: Path) -> None:
    _assert_safe_diagnostic_json_output(
        path,
        package_dir=package_dir,
        command_name="research-status-sync",
    )


def _assert_safe_diagnostic_json_output(
    path: Path,
    *,
    package_dir: Path,
    command_name: str,
) -> None:
    if path.suffix.lower() != ".json":
        raise ValueError(f"{command_name} --out must be a .json diagnostic report path")
    operator_summary_path = package_dir / "reports" / "operator_summary.json"
    if path.resolve() == operator_summary_path.resolve():
        raise ValueError(
            f"{command_name} --out must not target package operator_summary.json"
        )
    if _is_hs_runtime_output_path(path):
        raise ValueError(
            f"{command_name} --out must not target HearthRanger runtime files"
        )


def _assert_safe_closure_optimizer_output(path: Path) -> None:
    name = path.name.lower()
    if name == "operator_summary.json":
        raise ValueError(
            "source-closure-optimizer must not overwrite operator_summary.json"
        )
    if _is_hs_runtime_output_path(path):
        raise ValueError(
            "source-closure-optimizer output must not target HearthRanger runtime files"
        )


def _is_hs_runtime_output_path(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    name = path.name.lower()
    runtime_file_names = {
        "combo.json",
        "concede.json",
        "deck_config.ini",
        "globalvalues.json",
        "mulligan.json",
        "presume.json",
    }
    return (
        "customconfig" in parts
        or name in runtime_file_names
        or (path.suffix.lower() == ".json" and path.stem.isdigit())
    )


def _format_source_closure_optimizer_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# HSConfig Source Closure Optimizer",
        "",
        f"- Authority: `{payload['authority']}`",
        f"- Source status apply blocking: `{payload['source_status_apply_blocking']}`",
        f"- Package count: `{payload['package_count']}`",
        "",
        "| Deck | Decision | Runtime usable | First missing source action | Default-only surfaces | Research relation | Research refresh action |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for report in payload["reports"]:
        default_only = ", ".join(report["default_only_runtime_surfaces"]) or "none"
        lines.append(
            "| {deck} | `{decision}` | `{usable}` | `{action}` | `{default_only}` | `{research_relation}` | `{research_action}` |".format(
                deck=report["deck_name"],
                decision=report["decision"],
                usable=report["runtime_package_usable"],
                action=report["first_missing_source_action"],
                default_only=default_only,
                research_relation=report.get(
                    "research_snapshot_relation",
                    "not_evaluated",
                ),
                research_action=report.get(
                    "research_recommended_refresh_action",
                    "not_evaluated",
                ),
            )
        )
    lines.append("")
    return "\n".join(lines)
