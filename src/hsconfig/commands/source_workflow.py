from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from hsconfig.card_data_intake import build_card_data_context
from hsconfig.card_metadata import hydrate_card_metadata
from hsconfig.commands.common import run_payload_command
from hsconfig.package_io import prepare_research_output_dir
from hsconfig.deck_identity import build_deck_identity
from hsconfig.guide_claim_builder import build_guide_claim_bundle
from hsconfig.guide_source_builder import (
    build_candidate_archetypes,
    build_deck_fingerprint,
    build_guide_builder_receipt,
    build_guide_sources,
    research_required_guide_sources,
)
from hsconfig.hearthstonejson import fetch_latest_cards, fetch_latest_collectible_cards
from hsconfig.identity_graph import build_identity_gap_report, build_identity_graph_report
from hsconfig.input_loading import (
    fixture_row_for,
    guide_documents_from_legacy_claims,
    load_cards,
    load_claims,
    load_guide_sources,
    load_source_documents,
    load_source_evidence,
    source_records_from_cards,
)
from hsconfig.io import write_json
from hsconfig.research_contract import build_research_contract_bundle
from hsconfig.semantic_enrichment import append_semantic_warning, enrich_card_metadata
from hsconfig.source_document_drafter import draft_source_documents
from hsconfig.source_evidence_verifier import verify_source_documents
from hsconfig.source_research_manifest import build_source_research_manifest


def run_source_manifest_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, source_manifest_payload)


def run_draft_source_documents_command(args: argparse.Namespace) -> int:
    return run_payload_command(args, draft_source_documents_payload)


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


def draft_source_documents_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
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


def research_deck_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    out = Path(args.out)
    prepare_research_output_dir(out)
    args.skip_semantic_fetch = True

    context = _build_research_context(args)
    deck_identity = context["deck_identity"]
    write_json(out / "deck_fingerprint.json", context["deck_fingerprint"])
    write_json(out / "candidate_archetypes.json", context["candidate_archetypes"])
    write_json(out / "guide_sources.json", context["guide_sources_generated"])
    write_json(out / "guide_builder_receipt.json", context["guide_builder_receipt"])
    write_json(out / "identity_graph_report.json", context["identity_graph_report"])
    write_json(out / "identity_gap_report.json", context["identity_gap_report"])
    write_json(out / "card_data_intake_report.json", context["card_data_intake_report"])
    write_json(out / "source_evidence_verification_report.json", context["source_evidence_report"])
    if context.get("source_document_draft_report") is not None:
        report = context["source_document_draft_report"]
        write_json(
            out / "source_document_draft_report.json",
            {
                "schema_version": 1,
                "deck_name": args.deck_name,
                "draft_summary": report["draft_summary"],
                "unresolved_mentions": report["unresolved_mentions"],
                "source_evidence_report": verify_source_documents(report["source_documents"]),
            },
        )

    written_files = [str(path) for path in sorted(out.glob("*.json"))]
    return (
        {
            "status": "OK",
            "deck_name": args.deck_name,
            "deck_slug": deck_identity["deck_slug"],
            "source_depth_status": context["guide_builder_receipt"]["source_depth_status"],
            "written_files": written_files,
        },
        0,
    )


def _build_research_context(args: argparse.Namespace) -> dict[str, Any]:
    cards_payload = load_cards(
        args.cards_json,
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        allow_placeholder=args.allow_placeholder,
    )
    cards = cards_payload["cards"]
    collectible_cards: list[dict[str, Any]] = []
    full_cards: list[dict[str, Any]] = []
    card_data_fetch_error: str | None = None
    semantic_fetch_skipped = bool(getattr(args, "skip_semantic_fetch", False))
    if not semantic_fetch_skipped:
        try:
            collectible_cards = fetch_latest_collectible_cards(timeout=10.0)
            full_cards = fetch_latest_cards(timeout=10.0)
        except Exception as exc:
            card_data_fetch_error = str(exc)
    claims = load_claims(getattr(args, "claims_json", None))
    source_documents_input = load_source_documents(getattr(args, "source_documents_json", None))
    source_evidence_rows = load_source_evidence(getattr(args, "source_evidence_json", None))
    guide_sources = load_guide_sources(getattr(args, "guide_sources_json", None))
    card_data_context = build_card_data_context(
        deck_cards=cards,
        collectible_cards=collectible_cards,
        full_cards=full_cards,
    )
    source_records = {
        **source_records_from_cards(cards),
        **card_data_context["deck_source_records"],
        **card_data_context["companion_source_records"],
    }
    if card_data_fetch_error is not None:
        card_data_context["card_data_intake_report"]["warnings"].append(
            {"reason": "hearthstonejson_fetch_failed", "message": card_data_fetch_error}
        )
    deck_identity = build_deck_identity(
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        cards=cards,
        hero_dbf_id=cards_payload.get("hero_dbf_id"),
        format=cards_payload.get("format"),
        sideboards=cards_payload.get("sideboards", []),
    )
    card_metadata = hydrate_card_metadata(
        cards=deck_identity["cards"],
        source_records=source_records,
    )
    hearthstonejson_cards = [*collectible_cards, *full_cards]
    semantic_fetch_error = card_data_fetch_error
    semantic_report = enrich_card_metadata(
        card_metadata,
        hearthstonejson_cards=hearthstonejson_cards,
    )
    if semantic_fetch_error is not None:
        append_semantic_warning(
            semantic_report,
            {"card_id": None, "warning": f"hearthstonejson_fetch_failed: {semantic_fetch_error}"},
        )
    enriched_card_metadata = {"cards": semantic_report["cards"]}
    source_document_draft_report = None
    if source_evidence_rows:
        source_document_draft_report = draft_source_documents(
            deck_name=args.deck_name,
            deck_identity=deck_identity,
            evidence_rows=source_evidence_rows,
        )
        source_documents_input = [
            *source_documents_input,
            *source_document_draft_report["source_documents"],
        ]
    generated_guide_sources = None
    strict_source_documents = guide_sources
    if source_documents_input:
        strict_source_documents = source_documents_input
    elif not guide_sources and getattr(args, "auto_research_fallback", True):
        generated_guide_sources = build_guide_sources(
            deck_name=args.deck_name,
            deck_identity=deck_identity,
            card_roles={},
            source_documents=[],
        )
        strict_source_documents = []
    elif not guide_sources:
        generated_guide_sources = research_required_guide_sources(args.deck_name, deck_identity)
        strict_source_documents = []
    source_documents = [*strict_source_documents, *guide_documents_from_legacy_claims(claims)]
    guide_claim_bundle = build_guide_claim_bundle(
        deck_identity=deck_identity,
        card_metadata=enriched_card_metadata,
        source_documents=source_documents,
    )
    source_claims = {
        "claims": guide_claim_bundle["claims"],
        "claim_count": len(guide_claim_bundle["claims"]),
    }
    research_bundle = build_research_contract_bundle(
        deck_identity=deck_identity,
        card_metadata=enriched_card_metadata,
        source_claims=source_claims,
        guide_claim_bundle=guide_claim_bundle,
    )
    if source_documents_input:
        generated_guide_sources = build_guide_sources(
            deck_name=args.deck_name,
            deck_identity=deck_identity,
            card_roles=research_bundle.get("card_role_map", {}),
            source_documents=source_documents_input,
            validated_claim_bundle=guide_claim_bundle,
        )
    elif generated_guide_sources is None and guide_sources:
        generated_guide_sources = build_guide_sources(
            deck_name=args.deck_name,
            deck_identity=deck_identity,
            card_roles=research_bundle.get("card_role_map", {}),
            source_documents=guide_sources,
        )
    guide_builder_receipt = build_guide_builder_receipt(
        deck_name=args.deck_name,
        deck_identity=deck_identity,
        source_documents=source_documents_input,
        guide_sources=generated_guide_sources or build_guide_sources(
            deck_name=args.deck_name,
            deck_identity=deck_identity,
            card_roles=research_bundle.get("card_role_map", {}),
            source_documents=guide_sources,
        ),
    )
    deck_fingerprint = build_deck_fingerprint(deck_identity, deck_identity["cards"])
    candidate_archetypes = build_candidate_archetypes(
        deck_name=args.deck_name,
        deck_identity=deck_identity,
        card_roles=research_bundle.get("card_role_map", {}),
        source_documents=source_documents_input or guide_sources,
    )
    identity_graph_report = build_identity_graph_report(
        deck_identity=deck_identity,
        hearthstonejson_receipt={
            "source": "hearthstonejson_latest_enus_cards",
            "card_count": len(hearthstonejson_cards),
            "status": (
                "skipped"
                if semantic_fetch_skipped
                else "fetched"
                if semantic_fetch_error is None
                else "fetch_failed"
            ),
            "error": semantic_fetch_error,
        },
    )
    return {
        "cards_payload": cards_payload,
        "deck_identity": deck_identity,
        "card_metadata": enriched_card_metadata,
        "semantic_report": semantic_report,
        "guide_claim_bundle": guide_claim_bundle,
        "source_claims": source_claims,
        "research_bundle": research_bundle,
        "guide_sources_generated": generated_guide_sources,
        "guide_builder_receipt": guide_builder_receipt,
        "deck_fingerprint": deck_fingerprint,
        "candidate_archetypes": candidate_archetypes,
        "identity_graph_report": identity_graph_report,
        "identity_gap_report": build_identity_gap_report(identity_graph_report),
        "card_data_intake_report": card_data_context["card_data_intake_report"],
        "source_evidence_report": verify_source_documents(source_documents),
        "source_document_draft_report": source_document_draft_report,
    }
