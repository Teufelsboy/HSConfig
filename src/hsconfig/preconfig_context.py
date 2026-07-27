from __future__ import annotations

import argparse
from datetime import date
from typing import Any, Literal

from hsconfig.card_data_intake import build_card_data_context
from hsconfig.card_feed_loading import (
    card_feed_receipt_source,
    card_feed_receipt_status,
    load_optional_card_feed,
)
from hsconfig.card_metadata import hydrate_card_metadata
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
    guide_documents_from_legacy_claims,
    load_cards,
    load_claims,
    load_guide_sources,
    load_source_documents,
    load_source_evidence,
    source_records_from_cards,
)
from hsconfig.internal_source_authority import (
    InternalSourceAuthorityHandoff,
    reject_caller_supplied_source_authority,
    trusted_source_documents_from_handoff,
)
from hsconfig.research_contract import build_research_contract_bundle
from hsconfig.semantic_enrichment import append_semantic_warning, enrich_card_metadata
from hsconfig.source_document_drafter import draft_source_documents
from hsconfig.source_evidence_verifier import verify_source_documents


def build_preconfig_context(
    args: argparse.Namespace,
    *,
    current_date: date | None = None,
    source_authority_handoff: InternalSourceAuthorityHandoff | None = None,
    source_authority_consumer: Literal["research", "prepare"] | None = None,
    fetch_latest_cards_fn: Any = fetch_latest_cards,
    fetch_latest_collectible_cards_fn: Any | None = fetch_latest_collectible_cards,
    research_required_guide_sources_fn: Any = research_required_guide_sources,
) -> dict[str, Any]:
    """Build the shared deck/source context used by research and prepare commands."""
    reject_caller_supplied_source_authority(args)
    operator_date = (
        current_date
        if current_date is not None
        else getattr(args, "current_date", None)
    )
    cards_payload = load_cards(
        args.cards_json,
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        allow_placeholder=args.allow_placeholder,
    )
    cards = cards_payload["cards"]
    collectible_cards = load_optional_card_feed(getattr(args, "collectible_cards_json", None))
    full_cards = load_optional_card_feed(getattr(args, "full_cards_json", None))
    card_data_fetch_error: str | None = None
    semantic_fetch_skipped = bool(getattr(args, "skip_semantic_fetch", False))
    if not semantic_fetch_skipped:
        try:
            if collectible_cards is None and fetch_latest_collectible_cards_fn is not None:
                collectible_cards = fetch_latest_collectible_cards_fn(timeout=10.0)
            if full_cards is None:
                full_cards = fetch_latest_cards_fn(timeout=10.0)
        except Exception as exc:
            card_data_fetch_error = str(exc)
    collectible_cards = collectible_cards or []
    full_cards = full_cards or []
    claims = load_claims(getattr(args, "claims_json", None))
    if source_authority_handoff is not None and source_authority_consumer is None:
        raise ValueError("source_authority_consumer_mismatch")
    trusted_source_documents = (
        trusted_source_documents_from_handoff(
            source_authority_handoff,
            consumer=source_authority_consumer,
        )
        if source_authority_handoff is not None
        else None
    )
    source_documents_input = (
        trusted_source_documents
        if isinstance(trusted_source_documents, list)
        else load_source_documents(getattr(args, "source_documents_json", None))
    )
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
    semantic_report = enrich_card_metadata(
        card_metadata,
        hearthstonejson_cards=hearthstonejson_cards,
    )
    if card_data_fetch_error is not None:
        append_semantic_warning(
            semantic_report,
            {
                "card_id": None,
                "warning": f"hearthstonejson_fetch_failed: {card_data_fetch_error}",
            },
        )
    enriched_card_metadata = {"cards": semantic_report["cards"]}
    source_document_draft_report = None
    if source_evidence_rows:
        source_document_draft_report = draft_source_documents(
            deck_name=args.deck_name,
            deck_identity=deck_identity,
            evidence_rows=source_evidence_rows,
            current_date=operator_date,
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
            current_date=operator_date,
        )
        strict_source_documents = []
    elif not guide_sources:
        generated_guide_sources = research_required_guide_sources_fn(args.deck_name, deck_identity)
        strict_source_documents = []
    source_documents = [
        *strict_source_documents,
        *guide_documents_from_legacy_claims(claims),
    ]
    guide_claim_bundle = build_guide_claim_bundle(
        deck_identity=deck_identity,
        card_metadata=enriched_card_metadata,
        source_documents=source_documents,
        current_date=operator_date,
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
            current_date=operator_date,
        )
    elif generated_guide_sources is None and guide_sources:
        generated_guide_sources = build_guide_sources(
            deck_name=args.deck_name,
            deck_identity=deck_identity,
            card_roles=research_bundle.get("card_role_map", {}),
            source_documents=guide_sources,
            current_date=operator_date,
        )
    guide_builder_receipt = build_guide_builder_receipt(
        deck_name=args.deck_name,
        deck_identity=deck_identity,
        source_documents=source_documents_input,
        guide_sources=generated_guide_sources
        or build_guide_sources(
            deck_name=args.deck_name,
            deck_identity=deck_identity,
            card_roles=research_bundle.get("card_role_map", {}),
            source_documents=guide_sources,
            current_date=operator_date,
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
            "source": card_feed_receipt_source(
                collectible_cards_json=getattr(args, "collectible_cards_json", None),
                full_cards_json=getattr(args, "full_cards_json", None),
            ),
            "card_count": len(hearthstonejson_cards),
            "status": card_feed_receipt_status(
                collectible_cards_json=getattr(args, "collectible_cards_json", None),
                full_cards_json=getattr(args, "full_cards_json", None),
                semantic_fetch_skipped=semantic_fetch_skipped,
                semantic_fetch_error=card_data_fetch_error,
            ),
            "error": card_data_fetch_error,
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
