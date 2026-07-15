from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from hsconfig.commands.common import run_payload_command
from hsconfig.deck_identity import build_deck_identity
from hsconfig.guide_source_builder import build_candidate_archetypes
from hsconfig.hearthstonejson import fetch_latest_cards, fetch_latest_collectible_cards
from hsconfig.input_loading import (
    fixture_row_for,
    load_cards,
    load_source_evidence,
)
from hsconfig.io import read_json, write_json
from hsconfig.package_io import prepare_research_output_dir
from hsconfig.preconfig_context import build_preconfig_context
from hsconfig.source_autopilot import build_source_autopilot_bundle
from hsconfig.source_document_drafter import draft_source_documents
from hsconfig.source_evidence_verifier import verify_source_documents
from hsconfig.source_research_manifest import build_source_research_manifest


def run_source_manifest_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, source_manifest_payload)


def run_draft_source_documents_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, draft_source_documents_payload)


def run_source_autopilot_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, source_autopilot_payload)


def run_research_deck_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, research_deck_payload)


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
    manifest = build_source_research_manifest(
        deck_name=args.deck_name,
        deck_identity=deck_identity,
        candidate_archetypes=candidate_archetypes,
        fixture_row=fixture_row_for(args.deck_name),
    )
    output_path = out / "source_research_manifest.json"
    write_json(output_path, manifest)
    return (
        {
            "status": "OK",
            "deck_name": args.deck_name,
            "deck_slug": deck_identity["deck_slug"],
            "written_files": [str(output_path)],
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
    source_payload = read_json(args.source_search_results_json)
    source_records = source_payload.get("records", source_payload) if isinstance(source_payload, dict) else source_payload
    if not isinstance(source_records, list):
        raise ValueError(
            "--source-search-results-json must contain a list or an object with a records list"
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
    return (
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


def research_deck_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    out = Path(args.out)
    prepare_research_output_dir(out)
    if not hasattr(args, "skip_semantic_fetch"):
        args.skip_semantic_fetch = True

    context = build_preconfig_context(
        args,
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
