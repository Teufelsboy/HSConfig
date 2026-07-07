from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from hsconfig.card_metadata import hydrate_card_metadata
from hsconfig.card_behavior_router import route_card_behavior_claims
from hsconfig.compile_cardid import compile_cardid_behaviors
from hsconfig.compile_combo import compile_combo
from hsconfig.compile_globalvalues import compile_globalvalues
from hsconfig.compile_mulligan import compile_mulligan
from hsconfig.combo_plan import build_combo_plan
from hsconfig.config_readiness import build_config_readiness_report
from hsconfig.deckstring_decode import decode_deck_code
from hsconfig.deck_identity import build_deck_identity
from hsconfig.gameplan_contract import build_gameplan_contract
from hsconfig.globalvalues_authority import build_globalvalues_authority_matrix
from hsconfig.globalvalues_baseline import load_globalvalues_baseline
from hsconfig.guide_claim_builder import build_guide_claim_bundle
from hsconfig.guide_research import normalize_source_claims
from hsconfig.guide_source_builder import (
    build_candidate_archetypes,
    build_deck_fingerprint,
    build_guide_builder_receipt,
    build_guide_sources,
)
from hsconfig.guide_source_depth import build_guide_source_depth_report
from hsconfig.hearthstonejson import fetch_latest_cards
from hsconfig.identity_graph import build_identity_gap_report, build_identity_graph_report
from hsconfig.io import read_json, slugify_deck_name, write_json
from hsconfig.mulligan_plan import build_mulligan_plan
from hsconfig.models import InputManifest
from hsconfig.operator_summary import build_operator_summary
from hsconfig.research_contract import (
    build_research_contract_bundle,
    write_research_contract_bundle,
    write_research_contract_bundle_to_dir,
)
from hsconfig.runtime_apply import apply_package
from hsconfig.semantic_audit import render_semantic_audit_markdown
from hsconfig.semantic_enrichment import enrich_card_metadata
from hsconfig.surface_intent import build_surface_intent
from hsconfig.validate_package import validate_config_package

LEGACY_CLAIMS_RETRIEVED_AT = "1970-01-01T00:00:00Z"


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "prepare":
            payload, code = _prepare(args)
        elif args.command == "build":
            payload, code = _build(args)
        elif args.command == "research-contract":
            payload, code = _research_contract(args)
        elif args.command == "research-deck":
            payload, code = _research_deck(args)
        elif args.command == "validate":
            payload, code = _validate(args)
        elif args.command == "apply":
            payload, code = _apply(args)
        else:
            payload, code = {"status": "failed", "errors": [f"Unknown command: {args.command}"]}, 1
    except Exception as exc:
        payload, code = {"status": "failed", "errors": [str(exc)]}, 1
    return _emit(payload, args.json, code)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hsconfig")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build")
    build.add_argument("--deck-name", required=True)
    build.add_argument("--deck-code", required=True)
    build.add_argument("--out", required=True)
    build.add_argument("--runtime-root", required=True)
    build.add_argument("--cards-json")
    build.add_argument("--claims-json")
    build.add_argument("--guide-sources-json")
    build.add_argument("--source-documents-json")
    build.add_argument("--plan-reports-dir")
    build.add_argument("--allow-placeholder", action="store_true")
    build.add_argument("--json", action="store_true")

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--deck-name", required=True)
    prepare.add_argument("--deck-code", required=True)
    prepare.add_argument("--out", required=True)
    prepare.add_argument("--runtime-root", required=True)
    prepare.add_argument("--cards-json")
    prepare.add_argument("--claims-json")
    prepare.add_argument("--guide-sources-json")
    prepare.add_argument("--source-documents-json")
    prepare.add_argument("--auto-research-fallback", action=argparse.BooleanOptionalAction, default=True)
    prepare.add_argument("--plan-reports-dir")
    prepare.add_argument("--allow-placeholder", action="store_true")
    prepare.add_argument("--json", action="store_true")

    research_contract = subparsers.add_parser("research-contract")
    research_contract.add_argument("--deck-name", required=True)
    research_contract.add_argument("--deck-code", required=True)
    research_contract.add_argument("--out", required=True)
    research_contract.add_argument("--cards-json")
    research_contract.add_argument("--claims-json")
    research_contract.add_argument("--guide-sources-json")
    research_contract.add_argument("--source-documents-json")
    research_contract.add_argument("--allow-placeholder", action="store_true")
    research_contract.add_argument("--json", action="store_true")

    research_deck = subparsers.add_parser("research-deck")
    research_deck.add_argument("--deck-name", required=True)
    research_deck.add_argument("--deck-code", required=True)
    research_deck.add_argument("--out", required=True)
    research_deck.add_argument("--cards-json")
    research_deck.add_argument("--source-documents-json")
    research_deck.add_argument("--allow-placeholder", action="store_true")
    research_deck.add_argument("--json", action="store_true")

    validate = subparsers.add_parser("validate")
    validate.add_argument("--package", required=True)
    validate.add_argument("--json", action="store_true")

    apply = subparsers.add_parser("apply")
    apply.add_argument("--package", required=True)
    apply.add_argument("--runtime-root", required=True)
    apply.add_argument("--json", action="store_true")
    return parser


def _build_preconfig_context(args: argparse.Namespace) -> dict[str, Any]:
    cards_payload = _load_cards(
        args.cards_json,
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        allow_placeholder=args.allow_placeholder,
    )
    cards = cards_payload["cards"]
    claims = _load_claims(getattr(args, "claims_json", None))
    source_documents_input = _load_source_documents(getattr(args, "source_documents_json", None))
    guide_sources = _load_guide_sources(getattr(args, "guide_sources_json", None))
    source_records = _source_records_from_cards(cards)
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
    hearthstonejson_cards: list[dict[str, Any]] = []
    semantic_fetch_error: str | None = None
    semantic_fetch_skipped = bool(getattr(args, "skip_semantic_fetch", False))
    if not semantic_fetch_skipped:
        try:
            hearthstonejson_cards = fetch_latest_cards(timeout=10.0)
        except Exception as exc:
            semantic_fetch_error = str(exc)
    semantic_report = enrich_card_metadata(
        card_metadata,
        hearthstonejson_cards=hearthstonejson_cards,
    )
    if semantic_fetch_error is not None:
        semantic_report.setdefault("semantic_enrichment_warnings", []).append(
            {"card_id": None, "warning": f"hearthstonejson_fetch_failed: {semantic_fetch_error}"}
        )
        semantic_report["semantic_enrichment_status"] = "partial"
    enriched_card_metadata = {"cards": semantic_report["cards"]}
    generated_guide_sources = None
    if source_documents_input:
        generated_guide_sources = build_guide_sources(
            deck_name=args.deck_name,
            deck_identity=deck_identity,
            card_roles={},
            source_documents=source_documents_input,
        )
        guide_sources = generated_guide_sources["sources"]
    elif not guide_sources and getattr(args, "auto_research_fallback", True):
        generated_guide_sources = build_guide_sources(
            deck_name=args.deck_name,
            deck_identity=deck_identity,
            card_roles={},
            source_documents=[],
        )
    elif not guide_sources:
        generated_guide_sources = _research_required_guide_sources(args.deck_name, deck_identity)
    source_documents = [*guide_sources, *_guide_documents_from_legacy_claims(claims)]
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
    if generated_guide_sources is None and guide_sources:
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
    }


def _prepare(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    payload, code = _build(args)
    payload = dict(payload)
    payload["command"] = "prepare"
    if code == 0:
        operator_summary = payload.get("operator_summary")
        if isinstance(operator_summary, dict):
            payload["next_action"] = operator_summary.get("next_action", "READY_WITH_WARNINGS")
        else:
            payload["next_action"] = "READY_TO_APPLY_OR_HANDOFF"
    return payload, code


def _build(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    out = Path(args.out)
    deck_slug = slugify_deck_name(args.deck_name)
    deck_dir = out / "CustomConfig" / deck_slug
    reports_dir = out / "reports"

    context = _build_preconfig_context(args)
    cards_payload = context["cards_payload"]
    deck_identity = context["deck_identity"]
    card_metadata = context["card_metadata"]
    semantic_report = context["semantic_report"]
    guide_claim_bundle = context["guide_claim_bundle"]
    source_claims = context["source_claims"]
    research_bundle = context["research_bundle"]
    gameplan_contract = build_gameplan_contract(
        deck_identity=deck_identity,
        card_metadata=card_metadata,
        source_claims=source_claims,
        research_bundle=research_bundle,
    )
    plan_claims = list(guide_claim_bundle.get("claims", []))
    mulligan_plan = build_mulligan_plan(
        deck_name=args.deck_name,
        claims=plan_claims,
        card_roles=research_bundle.get("card_role_map", {}),
    )
    card_behavior_plan = route_card_behavior_claims(plan_claims)
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
            plan_dir, "card_behavior_plan_report.json", card_behavior_plan
        )
        combo_plan = _read_plan_report(plan_dir, "combo_plan_report.json", combo_plan)
        global_values_authority_matrix = _read_plan_report(
            plan_dir, "global_values_authority_matrix.json", global_values_authority_matrix
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
        gameplan_contract, rows=card_behavior_plan["rows"]
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
    )
    surface_intent = build_surface_intent(gameplan_contract)

    baseline_receipt = load_globalvalues_baseline(args.runtime_root)
    baseline = baseline_receipt["baseline"]
    globalvalues = compile_globalvalues(baseline, gameplan_contract)
    if deck_dir.exists():
        shutil.rmtree(deck_dir)
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
    if context.get("guide_sources_generated") is not None:
        write_json(reports_dir / "guide_sources.json", context["guide_sources_generated"])
    write_json(reports_dir / "deck_fingerprint.json", context["deck_fingerprint"])
    write_json(reports_dir / "candidate_archetypes.json", context["candidate_archetypes"])
    write_json(reports_dir / "guide_builder_receipt.json", context["guide_builder_receipt"])
    write_json(reports_dir / "identity_graph_report.json", context["identity_graph_report"])
    write_json(reports_dir / "identity_gap_report.json", context["identity_gap_report"])
    write_json(reports_dir / "guide_claim_bundle.json", guide_claim_bundle)
    write_json(reports_dir / "source_evidence_index.json", guide_claim_bundle["source_evidence_index"])
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
    write_json(reports_dir / "unsupported_claims_report.json", guide_claim_bundle["unsupported_claims"])
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
    write_json(
        reports_dir / "global_values_blocked_changes.json",
        global_values_authority_matrix["blocked_until_runtime_evidence"],
    )
    write_json(reports_dir / "globalvalues_baseline.json", baseline)
    write_json(reports_dir / "globalvalues_baseline_receipt.json", baseline_receipt)
    write_json(reports_dir / "globalvalues_profile.json", globalvalues["profile"])

    report = validate_config_package(
        out,
        globalvalues_baseline=baseline,
        globalvalues_profile=globalvalues["profile"],
        require_complete_package=True,
        require_globalvalues_profile=True,
    )
    write_json(reports_dir / "validation_report.json", report)
    generated_files = _generated_package_files(out, deck_dir, reports_dir)
    operator_summary = build_operator_summary(
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        technical_validation=report,
        guide_source_depth=context["guide_builder_receipt"],
        unsupported_conditions=mulligan_plan.get("suppressed_rules", []),
        globalvalue_authority=global_values_authority_matrix,
        generated_files=generated_files,
        claim_coverage_report=guide_claim_bundle["coverage"],
        config_readiness_summary=config_readiness_report["summary"],
        claim_conflict_report=guide_claim_bundle.get("claim_conflict_report"),
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
            "operator_summary": operator_summary,
            "next_action": operator_summary["next_action"],
        },
        code,
    )


def _research_deck(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    out = Path(args.out)
    _prepare_research_output_dir(out)
    args.skip_semantic_fetch = True

    context = _build_preconfig_context(args)
    deck_identity = context["deck_identity"]
    write_json(out / "deck_fingerprint.json", context["deck_fingerprint"])
    write_json(out / "candidate_archetypes.json", context["candidate_archetypes"])
    write_json(out / "guide_sources.json", context["guide_sources_generated"])
    write_json(out / "guide_builder_receipt.json", context["guide_builder_receipt"])
    write_json(out / "identity_graph_report.json", context["identity_graph_report"])
    write_json(out / "identity_gap_report.json", context["identity_gap_report"])

    written_files = [
        str(path)
        for path in sorted(out.glob("*.json"))
    ]
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


def _research_required_guide_sources(deck_name: str, deck_identity: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "deck_name": deck_name,
        "deck_code_hash": str(deck_identity.get("deck_code_hash", "")),
        "source_depth_status": "needs_more_research",
        "sources": [],
        "summary": {
            "source_count": 0,
            "claim_count": 0,
            "stale_source_count": 0,
            "downgraded_source_count": 0,
            "static_card_semantics_used": False,
        },
    }


def _generated_package_files(out: Path, deck_dir: Path, reports_dir: Path) -> list[str]:
    files = [
        *sorted(deck_dir.glob("*.json")),
        *sorted(path for path in reports_dir.rglob("*") if path.is_file()),
        reports_dir / "operator_summary.json",
    ]
    return sorted({str(path.relative_to(out)) for path in files})


def _research_contract(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    out = Path(args.out)
    _prepare_research_output_dir(out)

    context = _build_preconfig_context(args)
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


def _prepare_research_output_dir(out: Path) -> None:
    if not out.exists():
        return
    if not out.is_dir():
        raise ValueError(f"Research output path exists and is not a directory: {out}")
    children = list(out.iterdir())
    if not children:
        return
    raise ValueError(f"Refusing to overwrite non-empty research output directory: {out}")


def _validate(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    package = Path(args.package)
    if not package.exists():
        return {"status": "failed", "errors": [f"Package not found: {package}"], "checked_files": 0}, 1
    baseline = _read_required_baseline(package)
    profile = _read_optional_profile(package)
    report = validate_config_package(
        package,
        globalvalues_baseline=baseline,
        globalvalues_profile=profile,
        require_complete_package=True,
        require_globalvalues_profile=True,
    )
    return report, 0 if report["status"] == "passed" else 1


def _apply(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
    package = Path(args.package)
    if not package.exists():
        return {"status": "failed", "errors": [f"Package not found: {package}"]}, 1

    baseline = _read_required_baseline(package)
    profile = _read_optional_profile(package)
    report = validate_config_package(
        package,
        globalvalues_baseline=baseline,
        globalvalues_profile=profile,
        require_complete_package=True,
        require_globalvalues_profile=True,
    )
    if report["status"] != "passed":
        return {"status": "failed", "errors": report["errors"], "validation_report": report}, 1

    receipt = apply_package(package_root=package, runtime_root=args.runtime_root)
    return {"status": "applied", "receipt": receipt}, 0


def _load_cards(
    cards_json: str | None,
    *,
    deck_name: str,
    deck_code: str,
    allow_placeholder: bool = False,
) -> dict[str, Any]:
    if cards_json is None and not allow_placeholder:
        decoded = decode_deck_code(deck_code)
        return {
            "cards": decoded["cards"],
            "hero_dbf_id": decoded["hero_dbf_id"],
            "format": decoded["format"],
            "sideboards": decoded.get("sideboards", []),
            "deckstring_decode_receipt": decoded["deckstring_decode_receipt"],
            "card_id_map": decoded["card_id_map"],
            "card_source": "deckstring",
        }
    if cards_json is None:
        return {
            "cards": _placeholder_cards(deck_name=deck_name, deck_code=deck_code),
            "hero_dbf_id": None,
            "format": None,
            "sideboards": [],
            "deckstring_decode_receipt": None,
            "card_id_map": None,
            "card_source": "placeholder",
        }
    payload = read_json(cards_json)
    if isinstance(payload, dict):
        payload = payload.get("cards")
    if not isinstance(payload, list):
        raise ValueError("--cards-json must contain a list or an object with a cards list")
    cards = [_normalize_card_input(card) for card in payload]
    if not cards:
        raise ValueError("--cards-json did not contain any cards")
    return {
        "cards": cards,
        "hero_dbf_id": None,
        "format": None,
        "sideboards": [],
        "deckstring_decode_receipt": None,
        "card_id_map": None,
        "card_source": "cards_json",
    }


def _load_claims(claims_json: str | None) -> list[dict[str, Any]]:
    if claims_json is None:
        return []
    payload = read_json(claims_json)
    if isinstance(payload, dict):
        payload = payload.get("claims")
    if not isinstance(payload, list):
        raise ValueError("--claims-json must contain a list or an object with a claims list")
    claims = []
    for claim in payload:
        if not isinstance(claim, dict):
            raise ValueError("Every claim row must be an object")
        claims.append(dict(claim))
    return claims


def _load_guide_sources(guide_sources_json: str | None) -> list[dict[str, Any]]:
    if guide_sources_json is None:
        return []
    payload = read_json(guide_sources_json)
    if isinstance(payload, dict):
        payload = payload.get("sources", payload.get("documents", payload.get("guide_sources")))
    if not isinstance(payload, list):
        raise ValueError("--guide-sources-json must contain a list or an object with a sources list")
    sources = []
    for source in payload:
        if not isinstance(source, dict):
            raise ValueError("Every guide source row must be an object")
        sources.append(dict(source))
    return sources


def _load_source_documents(source_documents_json: str | None) -> list[dict[str, Any]]:
    if source_documents_json is None:
        return []
    payload = read_json(source_documents_json)
    if isinstance(payload, dict):
        payload = payload.get("source_documents", payload.get("documents", payload.get("sources")))
    if not isinstance(payload, list):
        raise ValueError("--source-documents-json must contain a list or an object with a source_documents list")
    documents = []
    for document in payload:
        if not isinstance(document, dict):
            raise ValueError("Every source document row must be an object")
        documents.append(dict(document))
    return documents


def _guide_documents_from_legacy_claims(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not claims:
        return []
    documents: dict[tuple[str, str], dict[str, Any]] = {}
    for claim in claims:
        source_url = str(claim.get("url", ""))
        source_title = str(claim.get("source_title", claim.get("source", "legacy claims")))
        key = (source_url, source_title)
        document = documents.setdefault(
            key,
            {
                "source_url": source_url,
                "source_title": source_title,
                "source_family": str(claim.get("source", "legacy_claims")),
                "retrieved_at": _legacy_claim_retrieved_at(claim),
                "claims": [],
            },
        )
        document["claims"].append(_legacy_claim_to_guide_claim(claim))
    return list(documents.values())


def _legacy_claim_retrieved_at(claim: dict[str, Any]) -> str:
    retrieved_at = str(claim.get("retrieved_at", "")).strip()
    return retrieved_at or LEGACY_CLAIMS_RETRIEVED_AT


def _legacy_claim_to_guide_claim(claim: dict[str, Any]) -> dict[str, Any]:
    text = str(claim.get("claim", ""))
    claim_type = str(claim.get("claim_type", "general")).lower()
    cards = [str(card) for card in claim.get("cards", [])]
    if "combo" in claim_type:
        claim_kind = "combo_sequence"
    elif "mulligan" in claim_type or "keep" in text.lower():
        claim_kind = "mulligan_keep"
    elif any(marker in text.lower() for marker in ("face", "target", "enemy hero")):
        claim_kind = "targeting_rule"
    elif any(marker in text.lower() for marker in ("pressure", "aggressive", "aggro", "burn")):
        claim_kind = "gameplan_posture"
    else:
        claim_kind = "card_role"
    converted = {
        "claim_kind": claim_kind,
        "cards": cards,
        "stance": _legacy_stance(claim_kind, text),
        "evidence_text_short": text,
        "source_confidence": "high" if claim.get("source") == "guide" else "medium",
    }
    if claim_kind == "combo_sequence":
        converted["sequence"] = cards
        if "values" in claim:
            converted["values"] = claim["values"]
    for optional_key in ("condition", "conditions"):
        if optional_key in claim:
            converted[optional_key] = claim[optional_key]
    return converted


def _legacy_stance(claim_kind: str, text: str) -> str:
    lowered = text.lower()
    if claim_kind == "mulligan_keep":
        return "keep"
    if claim_kind == "combo_sequence":
        return "ordered_combo"
    if claim_kind == "targeting_rule" and ("face" in lowered or "enemy hero" in lowered):
        return "prefer_enemy_hero"
    if claim_kind == "gameplan_posture":
        return "aggressive"
    if "pressure" in lowered:
        return "pressure"
    return "deck_card"


def _read_plan_report(plan_dir: Path, filename: str, fallback: dict[str, Any]) -> dict[str, Any]:
    path = plan_dir / filename
    if not path.exists():
        return fallback
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Plan report must be an object: {path}")
    return payload


def _placeholder_cards(*, deck_name: str, deck_code: str) -> list[dict[str, Any]]:
    seed = hashlib.sha256(f"{deck_name}\0{deck_code}".encode("utf-8")).hexdigest().upper()
    cards: list[dict[str, Any]] = []
    for index, count in enumerate((2, 2, 1), start=1):
        chunk = seed[(index - 1) * 6 : index * 6]
        cards.append(
            {
                "card_id": f"HSC_{chunk}_{index}",
                "dbf_id": int(seed[index * 6 : index * 6 + 6], 16),
                "count": count,
                "name": f"Preview Placeholder {index}",
                "type": "MINION",
                "text": "Generated preview placeholder for deterministic package validation.",
                "mechanics": [],
            }
        )
    return cards


def _normalize_card_input(card: Any) -> dict[str, Any]:
    if not isinstance(card, dict):
        raise ValueError("Every card row must be an object")
    if not card.get("card_id"):
        raise ValueError("Every card row must include card_id")
    normalized = {
        "card_id": str(card["card_id"]),
        "dbf_id": int(card["dbf_id"]) if card.get("dbf_id") is not None else None,
        "count": int(card.get("count", 1)),
    }
    for optional_key in ("name", "cost", "type", "text", "mechanics", "card_class", "class"):
        if optional_key in card:
            normalized[optional_key] = card[optional_key]
    return normalized


def _source_records_from_cards(cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    metadata_keys = {"name", "cost", "type", "text", "mechanics", "card_class", "class"}
    for card in cards:
        source = {key: card[key] for key in metadata_keys if key in card}
        if source:
            records[str(card["card_id"])] = source
    return records


def _read_optional_profile(package: Path) -> dict[str, Any] | None:
    profile_path = package / "reports" / "globalvalues_profile.json"
    if not profile_path.exists():
        return None
    profile = read_json(profile_path)
    if not isinstance(profile, dict):
        raise ValueError(f"GlobalValues profile must be an object: {profile_path}")
    return profile


def _read_required_baseline(package: Path) -> dict[str, Any]:
    baseline_path = package / "reports" / "globalvalues_baseline.json"
    if not baseline_path.exists():
        raise ValueError(f"Missing GlobalValues baseline report: {baseline_path}")
    baseline = read_json(baseline_path)
    if not isinstance(baseline, dict):
        raise ValueError(f"GlobalValues baseline must be an object: {baseline_path}")
    return baseline


def _emit(payload: dict[str, Any], as_json: bool, code: int) -> int:
    if as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
