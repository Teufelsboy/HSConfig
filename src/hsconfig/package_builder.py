from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Any

from hsconfig.card_feed_loading import (
    card_feed_receipt_source,
    card_feed_receipt_status,
    load_optional_card_feed,
)
from hsconfig.card_behavior_router import route_card_behavior_claims
from hsconfig.card_metadata import hydrate_card_metadata
from hsconfig.combo_plan import build_combo_plan
from hsconfig.compile_cardid import compile_cardid_behaviors
from hsconfig.compile_combo import compile_combo
from hsconfig.compile_globalvalues import compile_globalvalues
from hsconfig.compile_mulligan import compile_mulligan
from hsconfig.config_readiness import build_config_readiness_report
from hsconfig.deck_identity import build_deck_identity
from hsconfig.gameplan_contract import build_gameplan_contract
from hsconfig.globalvalues_authority import build_globalvalues_authority_matrix
from hsconfig.globalvalues_baseline import load_globalvalues_baseline
from hsconfig.guide_claim_builder import build_guide_claim_bundle
from hsconfig.guide_source_builder import (
    build_candidate_archetypes,
    build_deck_fingerprint,
    build_guide_builder_receipt,
    build_guide_sources,
    research_required_guide_sources as build_research_required_guide_sources,
)
from hsconfig.guide_source_depth import build_guide_source_depth_report
from hsconfig.hearthstonejson import fetch_latest_cards
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
from hsconfig.io import read_json, slugify_deck_name, write_json
from hsconfig.mechanic_drift import build_mechanic_drift_report
from hsconfig.models import InputManifest
from hsconfig.mulligan_plan import build_mulligan_plan
from hsconfig.operator_summary import build_operator_summary
from hsconfig.package_io import prepare_research_output_dir
from hsconfig.research_contract import (
    build_research_contract_bundle,
    write_research_contract_bundle,
    write_research_contract_bundle_to_dir,
)
from hsconfig.semantic_audit import render_semantic_audit_markdown
from hsconfig.semantic_enrichment import append_semantic_warning, enrich_card_metadata
from hsconfig.source_claim_gap_report import build_source_claim_gap_report
from hsconfig.source_document_drafter import draft_source_documents
from hsconfig.source_document_model import claim_can_lower_to_runtime
from hsconfig.source_evidence_verifier import verify_source_documents
from hsconfig.strong_promotion_report import build_strong_promotion_report
from hsconfig.surface_intent import build_surface_intent
from hsconfig.validate_package import validate_config_package


def build_preconfig_context(args: argparse.Namespace) -> dict[str, Any]:
    cards_payload = load_cards(
        args.cards_json,
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        allow_placeholder=args.allow_placeholder,
    )
    cards = cards_payload["cards"]
    claims = load_claims(getattr(args, "claims_json", None))
    source_documents_input = load_source_documents(getattr(args, "source_documents_json", None))
    source_evidence_rows = load_source_evidence(getattr(args, "source_evidence_json", None))
    guide_sources = load_guide_sources(getattr(args, "guide_sources_json", None))
    source_records = source_records_from_cards(cards)
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
    collectible_cards = load_optional_card_feed(getattr(args, "collectible_cards_json", None))
    full_cards = load_optional_card_feed(getattr(args, "full_cards_json", None))
    semantic_fetch_error: str | None = None
    semantic_fetch_skipped = bool(getattr(args, "skip_semantic_fetch", False))
    if not semantic_fetch_skipped:
        try:
            if full_cards is None:
                full_cards = fetch_latest_cards(timeout=10.0)
        except Exception as exc:
            semantic_fetch_error = str(exc)
    collectible_cards = collectible_cards or []
    full_cards = full_cards or []
    hearthstonejson_cards = [*collectible_cards, *full_cards]
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
        generated_guide_sources = _research_required_guide_sources(
            args.deck_name,
            deck_identity,
        )
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
        guide_sources=generated_guide_sources
        or build_guide_sources(
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
            "source": card_feed_receipt_source(
                collectible_cards_json=getattr(args, "collectible_cards_json", None),
                full_cards_json=getattr(args, "full_cards_json", None),
            ),
            "card_count": len(hearthstonejson_cards),
            "status": card_feed_receipt_status(
                collectible_cards_json=getattr(args, "collectible_cards_json", None),
                full_cards_json=getattr(args, "full_cards_json", None),
                semantic_fetch_skipped=semantic_fetch_skipped,
                semantic_fetch_error=semantic_fetch_error,
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
        "source_evidence_report": verify_source_documents(source_documents),
        "source_document_draft_report": source_document_draft_report,
    }


def prepare_package_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    payload, code = build_package_payload(args)
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


def build_package_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    out = Path(args.out)
    deck_slug = slugify_deck_name(args.deck_name)
    deck_dir = out / "CustomConfig" / deck_slug
    reports_dir = out / "reports"

    context = build_preconfig_context(args)
    cards_payload = context["cards_payload"]
    mechanic_drift_report = build_mechanic_drift_report(cards_payload["cards"])
    deck_identity = context["deck_identity"]
    card_metadata = context["card_metadata"]
    semantic_report = context["semantic_report"]
    guide_claim_bundle = context["guide_claim_bundle"]
    research_bundle = context["research_bundle"]
    plan_claims = list(guide_claim_bundle.get("claims", []))
    runtime_claims = [claim for claim in plan_claims if claim_can_lower_to_runtime(claim)]
    runtime_source_claims = {"claims": runtime_claims, "claim_count": len(runtime_claims)}
    runtime_research_bundle = build_research_contract_bundle(
        deck_identity=deck_identity,
        card_metadata=card_metadata,
        source_claims=runtime_source_claims,
        guide_claim_bundle=guide_claim_bundle,
    )
    gameplan_contract = build_gameplan_contract(
        deck_identity=deck_identity,
        card_metadata=card_metadata,
        source_claims=runtime_source_claims,
        research_bundle=runtime_research_bundle,
    )
    mulligan_plan = build_mulligan_plan(
        deck_name=args.deck_name,
        claims=plan_claims,
        card_roles=runtime_research_bundle.get("card_role_map", {}),
    )
    card_behavior_plan = route_card_behavior_claims(
        plan_claims,
        identity_links=_card_behavior_identity_links(gameplan_contract),
    )
    combo_plan = build_combo_plan(
        deck_cards=set(gameplan_contract.get("cards", {})),
        claims=plan_claims,
    )
    global_values_authority_matrix = build_globalvalues_authority_matrix(
        aggression_profile=str(gameplan_contract.get("aggression_profile", {}).get("speed", "balanced")),
        claims=plan_claims,
    )
    plan_reports_dir = getattr(args, "plan_reports_dir", None)
    if plan_reports_dir is not None:
        plan_dir = Path(plan_reports_dir)
        if not plan_dir.is_dir():
            raise ValueError(f"--plan-reports-dir must be an existing directory: {plan_dir}")
        guide_claim_bundle = _read_plan_report(plan_dir, "guide_claim_bundle.json", guide_claim_bundle)
        mulligan_plan = _read_plan_report(plan_dir, "mulligan_plan_report.json", mulligan_plan)
        card_behavior_plan = _read_plan_report(
            plan_dir,
            "card_behavior_plan_report.json",
            card_behavior_plan,
        )
        combo_plan = _read_plan_report(plan_dir, "combo_plan_report.json", combo_plan)
        global_values_authority_matrix = _read_plan_report(
            plan_dir,
            "global_values_authority_matrix.json",
            global_values_authority_matrix,
        )
    gameplan_contract = {
        **gameplan_contract,
        "guide_claim_bundle": guide_claim_bundle,
        "mulligan_plan": mulligan_plan,
        "card_behavior_plan": card_behavior_plan,
        "combo_plan": combo_plan,
        "global_values_authority_matrix": global_values_authority_matrix,
    }
    cardid_behavior_files = compile_cardid_behaviors(
        gameplan_contract,
        rows=card_behavior_plan["rows"],
    )
    config_readiness_report = build_config_readiness_report(
        deck_identity=deck_identity,
        claim_coverage=guide_claim_bundle["coverage"],
        gameplan_contract=gameplan_contract,
        mulligan_plan=mulligan_plan,
        card_behavior_plan=card_behavior_plan,
        combo_plan=combo_plan,
        global_values_authority_matrix=global_values_authority_matrix,
        emitted_cardid_files=cardid_behavior_files.keys(),
    )
    guide_source_depth_report = build_guide_source_depth_report(
        guide_claim_bundle=guide_claim_bundle,
        config_readiness_report=config_readiness_report,
        source_evidence_verification_report=context["source_evidence_report"],
    )
    surface_intent = build_surface_intent(gameplan_contract)

    baseline_receipt = load_globalvalues_baseline(args.runtime_root)
    baseline = baseline_receipt["baseline"]
    globalvalues = compile_globalvalues(baseline, gameplan_contract)
    _reset_generated_package_dirs(deck_dir, reports_dir)
    write_json(deck_dir / "GlobalValues.json", globalvalues["config"])
    write_json(deck_dir / "Mulligan.json", compile_mulligan(gameplan_contract))
    for filename, payload in cardid_behavior_files.items():
        write_json(deck_dir / filename, payload)

    combo = compile_combo(gameplan_contract, sequences=combo_plan["combos"])
    if combo is not None:
        write_json(deck_dir / "Combo.json", combo)

    manifest = InputManifest(
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        runtime_root=args.runtime_root,
        target_config_mode="preview",
        format=cards_payload.get("format"),
    ).to_dict()
    manifest["cards_json"] = str(Path(args.cards_json)) if args.cards_json else None
    manifest["claims_json"] = str(Path(args.claims_json)) if args.claims_json else None
    manifest["guide_sources_json"] = (
        str(Path(args.guide_sources_json)) if getattr(args, "guide_sources_json", None) else None
    )
    manifest["plan_reports_dir"] = (
        str(Path(args.plan_reports_dir)) if getattr(args, "plan_reports_dir", None) else None
    )
    manifest["card_source"] = cards_payload["card_source"]
    write_json(reports_dir / "input_manifest.json", manifest)
    write_json(reports_dir / "deck_identity.json", deck_identity)
    if cards_payload.get("deckstring_decode_receipt") is not None:
        write_json(
            reports_dir / "deckstring_decode_receipt.json",
            cards_payload["deckstring_decode_receipt"],
        )
    if cards_payload.get("card_id_map") is not None:
        write_json(reports_dir / "card_id_map.json", cards_payload["card_id_map"])
    write_json(reports_dir / "semantic_enrichment_report.json", semantic_report)
    write_json(reports_dir / "mechanic_drift_report.json", mechanic_drift_report)
    if context.get("guide_sources_generated") is not None:
        write_json(reports_dir / "guide_sources.json", context["guide_sources_generated"])
    write_json(reports_dir / "deck_fingerprint.json", context["deck_fingerprint"])
    write_json(reports_dir / "candidate_archetypes.json", context["candidate_archetypes"])
    write_json(reports_dir / "guide_builder_receipt.json", context["guide_builder_receipt"])
    write_json(reports_dir / "identity_graph_report.json", context["identity_graph_report"])
    write_json(reports_dir / "identity_gap_report.json", context["identity_gap_report"])
    write_json(
        reports_dir / "source_evidence_verification_report.json",
        context["source_evidence_report"],
    )
    write_json(reports_dir / "guide_claim_bundle.json", guide_claim_bundle)
    write_json(
        reports_dir / "source_evidence_index.json",
        guide_claim_bundle["source_evidence_index"],
    )
    write_json(
        reports_dir / "claim_coverage_report.json",
        {
            **guide_claim_bundle.get("coverage", {}),
            **guide_claim_bundle.get("claim_coverage_report", {}),
        },
    )
    write_json(
        reports_dir / "claim_conflict_report.json",
        guide_claim_bundle.get("claim_conflict_report", {"conflict_count": 0, "conflicts": []}),
    )
    write_json(
        reports_dir / "unsupported_claims_report.json",
        guide_claim_bundle["unsupported_claims"],
    )
    (reports_dir / "card_semantic_audit.md").write_text(
        render_semantic_audit_markdown(semantic_report),
        encoding="utf-8",
        newline="\n",
    )
    write_research_contract_bundle(research_bundle, reports_dir)
    write_json(reports_dir / "gameplan_contract.json", gameplan_contract)
    write_json(reports_dir / "surface_intent.json", surface_intent)
    write_json(reports_dir / "mulligan_plan_report.json", mulligan_plan)
    write_json(reports_dir / "card_behavior_plan_report.json", card_behavior_plan)
    write_json(
        reports_dir / "card_behavior_suppression_report.json",
        card_behavior_plan.get("suppressed", []),
    )
    write_json(reports_dir / "combo_plan_report.json", combo_plan)
    write_json(reports_dir / "combo_suppression_report.json", combo_plan.get("suppressed", []))
    write_json(reports_dir / "global_values_authority_matrix.json", global_values_authority_matrix)
    write_json(reports_dir / "per_card_config_readiness_report.json", config_readiness_report)
    write_json(reports_dir / "guide_source_depth_report.json", guide_source_depth_report)
    source_claim_gap_report = build_source_claim_gap_report(
        deck_name=args.deck_name,
        config_readiness_report=config_readiness_report,
        claim_coverage_report=guide_claim_bundle.get(
            "claim_coverage_report",
            guide_claim_bundle["coverage"],
        ),
        card_behavior_plan=card_behavior_plan,
        mulligan_plan=mulligan_plan,
        combo_plan=combo_plan,
    )
    write_json(reports_dir / "source_claim_gap_report.json", source_claim_gap_report)
    write_json(
        reports_dir / "global_values_blocked_changes.json",
        global_values_authority_matrix["blocked_until_runtime_evidence"],
    )
    write_json(reports_dir / "globalvalues_baseline.json", baseline)
    write_json(reports_dir / "globalvalues_baseline_receipt.json", baseline_receipt)
    write_json(reports_dir / "globalvalues_profile.json", globalvalues["profile"])
    write_json(reports_dir / "global_values_key_profile_report.json", globalvalues["profile"])

    report = validate_config_package(
        out,
        globalvalues_baseline=baseline,
        globalvalues_profile=globalvalues["profile"],
        require_complete_package=True,
        require_globalvalues_profile=True,
    )
    write_json(reports_dir / "validation_report.json", report)
    operator_summary_kwargs = {
        "deck_name": args.deck_name,
        "deck_code": args.deck_code,
        "technical_validation": report,
        "guide_source_depth": guide_source_depth_report,
        "unsupported_conditions": mulligan_plan.get("suppressed_rules", []),
        "globalvalue_authority": global_values_authority_matrix,
        "claim_coverage_report": guide_claim_bundle.get(
            "claim_coverage_report",
            guide_claim_bundle["coverage"],
        ),
        "config_readiness_summary": config_readiness_report["summary"],
        "config_readiness_report": config_readiness_report,
        "claim_conflict_report": guide_claim_bundle.get("claim_conflict_report"),
        "mulligan_plan_report": mulligan_plan,
        "card_behavior_plan_report": card_behavior_plan,
        "combo_plan_report": combo_plan,
        "globalvalues_profile_report": globalvalues["profile"],
        "semantic_enrichment_report": semantic_report,
        "mechanic_drift_report": mechanic_drift_report,
    }
    generated_files = _generated_package_files(out, deck_dir, reports_dir)
    operator_summary = build_operator_summary(
        generated_files=generated_files,
        **operator_summary_kwargs,
    )
    strong_promotion_report = build_strong_promotion_report(
        deck_name=args.deck_name,
        fixture_stage="runtime_prepare",
        operator_summary=operator_summary,
        source_claim_gap_report=source_claim_gap_report,
    )
    write_json(reports_dir / "strong_promotion_report.json", strong_promotion_report)
    generated_files = _generated_package_files(out, deck_dir, reports_dir)
    operator_summary = build_operator_summary(
        generated_files=generated_files,
        **operator_summary_kwargs,
    )
    write_json(reports_dir / "operator_summary.json", operator_summary)
    code = 0 if report["status"] == "passed" else 1
    return (
        {
            "status": report["status"],
            "package": str(out),
            "deck_slug": deck_slug,
            "errors": report["errors"],
            "guide_claims_count": len(guide_claim_bundle["claims"]),
            "guide_backed_cards": guide_claim_bundle["coverage"]["guide_backed_cards"],
            "uncovered_cards_count": len(guide_claim_bundle["coverage"]["uncovered_cards"]),
            "config_readiness_summary": config_readiness_report["summary"],
            "guide_source_depth_status": guide_source_depth_report["depth_status"],
            "guide_strength_summary": operator_summary["guide_strength_summary"],
            "semantic_blockers": operator_summary["semantic_blockers"],
            "operator_summary": operator_summary,
            "next_action": operator_summary["next_action"],
        },
        code,
    )


def research_contract_payload(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    out = Path(args.out)
    prepare_research_output_dir(out)

    context = build_preconfig_context(args)
    deck_identity = context["deck_identity"]
    bundle = context["research_bundle"]
    write_research_contract_bundle_to_dir(bundle, out)

    return (
        {
            "status": "passed",
            "research_dir": str(out),
            "deck_slug": deck_identity["deck_slug"],
            "confidence": bundle["archetype_research"]["confidence"],
        },
        0,
    )


def _research_required_guide_sources(deck_name: str, deck_identity: dict[str, Any]) -> dict[str, Any]:
    return build_research_required_guide_sources(deck_name, deck_identity)


def _generated_package_files(out: Path, deck_dir: Path, reports_dir: Path) -> list[str]:
    files = [
        *sorted(deck_dir.glob("*.json")),
        *sorted(path for path in reports_dir.rglob("*") if path.is_file()),
        reports_dir / "operator_summary.json",
    ]
    return sorted({str(path.relative_to(out)) for path in files})


def _reset_generated_package_dirs(deck_dir: Path, reports_dir: Path) -> None:
    for target in (deck_dir, reports_dir):
        if target.exists():
            shutil.rmtree(target)


def _read_plan_report(plan_dir: Path, filename: str, fallback: dict[str, Any]) -> dict[str, Any]:
    path = plan_dir / filename
    if not path.exists():
        return fallback
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Plan report must be an object: {path}")
    return payload


def _card_behavior_identity_links(gameplan_contract: dict[str, Any]) -> dict[str, Any]:
    cards = gameplan_contract.get("cards", {})
    if not isinstance(cards, dict):
        return {}
    return {
        str(card_id): list(row.get("linked_entities", []))
        for card_id, row in cards.items()
        if isinstance(row, dict)
    }
