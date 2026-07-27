from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Any

from hsconfig.card_behavior_router import route_card_behavior_claims
from hsconfig.combo_plan import build_combo_plan
from hsconfig.compile_cardid import compile_cardid_behaviors
from hsconfig.compile_combo import compile_combo
from hsconfig.compile_globalvalues import compile_globalvalues
from hsconfig.compile_mulligan import compile_mulligan
from hsconfig.config_readiness import build_config_readiness_report
from hsconfig.gameplan_contract import build_gameplan_contract
from hsconfig.globalvalues_authority import build_globalvalues_authority_matrix
from hsconfig.globalvalues_baseline import load_globalvalues_baseline
from hsconfig.guide_source_depth import build_guide_source_depth_report
from hsconfig.guide_source_builder import (
    research_required_guide_sources as build_research_required_guide_sources,
)
from hsconfig.hearthstonejson import fetch_latest_cards
from hsconfig.io import read_json, slugify_deck_name, write_json
from hsconfig.linked_entity_supplement import curated_links_for
from hsconfig.mechanic_drift import build_mechanic_drift_report
from hsconfig.models import InputManifest
from hsconfig.mulligan_plan import build_mulligan_plan, mulligan_rule_key
from hsconfig.operator_summary import build_operator_summary
from hsconfig.output_ownership_manifest import build_output_ownership_manifest
from hsconfig.package_derivation_receipt import (
    DERIVATION_RECEIPT_PATH,
    build_package_authority_context,
    refresh_package_derivation_authority,
)
from hsconfig.package_io import prepare_research_output_dir
from hsconfig.preconfig_context import build_preconfig_context
from hsconfig.research_contract import (
    build_research_contract_bundle,
    write_research_contract_bundle,
    write_research_contract_bundle_to_dir,
)
from hsconfig.semantic_audit import render_semantic_audit_markdown
from hsconfig.source_claim_conflicts import build_claim_conflict_report
from hsconfig.source_claim_gap_report import build_source_claim_gap_report
from hsconfig.source_claim_lifecycle import (
    build_initial_lifecycle_rows,
    lifecycle_claim_id,
    runtime_claims_for_surface,
    select_claims_for_surface,
)
from hsconfig.source_contract_audit import (
    build_source_contract_audit,
    render_source_contract_audit_markdown,
)
from hsconfig.source_evidence_closure import build_source_evidence_closure_report
from hsconfig.source_to_runtime_explainability import (
    build_source_to_runtime_explainability_report,
)
from hsconfig.source_document_model import (
    claim_can_lower_to_runtime,
    normalized_claim_kind,
    source_claim_signature,
)
from hsconfig.strict_package_validation import validate_complete_package
from hsconfig.strong_promotion_report import build_strong_promotion_report
from hsconfig.surface_intent import build_surface_intent


_STRATEGIC_STRONG_CLOSURE_CLAIM_KINDS = {
    "combo_sequence",
    "mulligan_keep",
    "mulligan_discard",
    "targeting_rule",
    "gameplan_posture",
    "globalvalue_numeric_tuning",
}


def _with_strategic_receipt_verification(
    claims: Any,
    *,
    deck_identity: dict[str, Any],
    verified_source_receipts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    target_fingerprint = str(deck_identity.get("deck_fingerprint", "")).strip().lower()
    verified_claim_signatures = {
        (
            str(receipt.get("claim_id", "")).strip(),
            str(receipt.get("claim_signature", "")).strip(),
        )
        for receipt in verified_source_receipts
        if isinstance(receipt, dict)
        and receipt.get("receipt_kind") == "canonical_exact_deck_source_document"
        and str(receipt.get("matched_deck_fingerprint", "")).strip().lower()
        == target_fingerprint
    }
    result: list[dict[str, Any]] = []
    for claim in claims if isinstance(claims, list) else []:
        if not isinstance(claim, dict):
            continue
        normalized = dict(claim)
        if normalized_claim_kind(normalized) in _STRATEGIC_STRONG_CLOSURE_CLAIM_KINDS:
            normalized["strategic_receipt_verified"] = (
                str(normalized.get("claim_id", "")).strip(),
                source_claim_signature(normalized),
            ) in verified_claim_signatures
        result.append(normalized)
    return result


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

    context = build_preconfig_context(
        args,
        fetch_latest_cards_fn=fetch_latest_cards,
        fetch_latest_collectible_cards_fn=None,
        research_required_guide_sources_fn=_research_required_guide_sources,
    )
    cards_payload = context["cards_payload"]
    mechanic_drift_report = build_mechanic_drift_report(cards_payload["cards"])
    deck_identity = context["deck_identity"]
    card_metadata = context["card_metadata"]
    semantic_report = context["semantic_report"]
    guide_claim_bundle = context["guide_claim_bundle"]
    guide_claim_bundle = _normalize_claim_conflict_report(guide_claim_bundle)
    canonical_guide_claim_bundle = guide_claim_bundle
    verified_source_receipts = list(
        canonical_guide_claim_bundle.get(
            "canonical_source_receipts",
            canonical_guide_claim_bundle.get("globalvalues_source_receipts", []),
        )
    )
    plan_claims = _with_strategic_receipt_verification(
        guide_claim_bundle.get("claims", []),
        deck_identity=deck_identity,
        verified_source_receipts=verified_source_receipts,
    )
    authority_guide_claim_bundle = {
        **guide_claim_bundle,
        "claims": plan_claims,
    }
    source_claim_conflict_report = guide_claim_bundle.get(
        "claim_conflict_report",
        {"conflict_count": 0, "conflicts": []},
    )
    runtime_claims = [claim for claim in plan_claims if claim_can_lower_to_runtime(claim)]
    initial_lifecycle_rows = build_initial_lifecycle_rows(
        plan_claims,
        conflict_report=source_claim_conflict_report,
    )
    non_mulligan_runtime_claims = [
        claim
        for claim in runtime_claims
        if normalized_claim_kind(claim) not in {"mulligan_keep", "mulligan_discard"}
    ]
    preliminary_research_bundle = build_research_contract_bundle(
        deck_identity=deck_identity,
        card_metadata=card_metadata,
        source_claims={
            "claims": non_mulligan_runtime_claims,
            "claim_count": len(non_mulligan_runtime_claims),
        },
        guide_claim_bundle=guide_claim_bundle,
    )
    mulligan_selection = select_claims_for_surface(
        initial_lifecycle_rows,
        "mulligan",
        context={
            "deck_identity": deck_identity,
            "verified_source_receipts": verified_source_receipts,
        },
        card_roles=preliminary_research_bundle.get("card_role_map", {}),
    )
    mulligan_runtime_claims = mulligan_selection["accepted_claims"]
    runtime_source_claims = {
        "claims": [*non_mulligan_runtime_claims, *mulligan_runtime_claims],
        "claim_count": len(non_mulligan_runtime_claims) + len(mulligan_runtime_claims),
    }
    research_bundle = build_research_contract_bundle(
        deck_identity=deck_identity,
        card_metadata=card_metadata,
        source_claims=runtime_source_claims,
        guide_claim_bundle=guide_claim_bundle,
    )
    gameplan_contract = build_gameplan_contract(
        deck_identity=deck_identity,
        card_metadata=card_metadata,
        source_claims=runtime_source_claims,
        research_bundle=research_bundle,
    )
    card_roles = research_bundle.get("card_role_map", {})
    mulligan_report_claims = [
        *mulligan_runtime_claims,
        *mulligan_selection["rejected_claims"],
    ]
    cardid_claims = runtime_claims_for_surface(initial_lifecycle_rows, "cardid")
    combo_claims = runtime_claims_for_surface(
        initial_lifecycle_rows,
        "combo",
        context={
            "deck_identity": deck_identity,
            "verified_source_receipts": verified_source_receipts,
        },
    )
    globalvalues_selection = select_claims_for_surface(
        initial_lifecycle_rows,
        "globalvalues",
        context={
            "deck_identity": deck_identity,
            "verified_source_receipts": verified_source_receipts,
        },
    )
    globalvalues_claims = globalvalues_selection["accepted_claims"]
    globalvalues_decision_claims = [
        *globalvalues_claims,
        *globalvalues_selection["rejected_claims"],
    ]
    globalvalues_decision_claim_ids = {
        lifecycle_claim_id(claim) for claim in globalvalues_decision_claims
    }
    globalvalues_authority_claims = [
        *globalvalues_decision_claims,
        *[
            claim
            for claim in _runtime_evidence_globalvalue_claims(
                initial_lifecycle_rows
            )
            if lifecycle_claim_id(claim) not in globalvalues_decision_claim_ids
        ],
    ]
    mulligan_plan = build_mulligan_plan(
        deck_name=args.deck_name,
        claims=mulligan_report_claims,
        card_roles=card_roles,
        deck_cards=_policy_mulligan_deck_cards(
            gameplan_contract.get("cards", {}),
            card_metadata,
        ),
        allow_policy_backed=True,
        policy_excluded_card_ids=_policy_mulligan_excluded_card_ids(
            mulligan_runtime_claims
        ),
        deck_identity=deck_identity,
        verified_source_receipts=verified_source_receipts,
    )
    card_behavior_plan = route_card_behavior_claims(
        cardid_claims,
        identity_links=_card_behavior_identity_links(gameplan_contract),
    )
    combo_plan = build_combo_plan(
        deck_cards=set(gameplan_contract.get("cards", {})),
        claims=combo_claims,
        deck_identity=deck_identity,
        verified_source_receipts=verified_source_receipts,
    )
    global_values_authority_matrix = build_globalvalues_authority_matrix(
        aggression_profile=str(gameplan_contract.get("aggression_profile", {}).get("speed", "balanced")),
        claims=globalvalues_authority_claims,
        deck_identity=deck_identity,
        verified_source_receipts=verified_source_receipts,
    )
    canonical_global_values_authority_matrix = global_values_authority_matrix
    plan_input_diagnostics: dict[str, Any] | None = None
    plan_reports_dir = getattr(args, "plan_reports_dir", None)
    if plan_reports_dir is not None:
        plan_dir = Path(plan_reports_dir)
        if not plan_dir.is_dir():
            raise ValueError(f"--plan-reports-dir must be an existing directory: {plan_dir}")
        imported_guide_claim_bundle = _read_plan_report(
            plan_dir,
            "guide_claim_bundle.json",
        )
        imported_plan_guide_claim_bundle = _normalize_claim_conflict_report(
            imported_guide_claim_bundle or {}
        )
        imported_mulligan_plan = _read_plan_report(
            plan_dir,
            "mulligan_plan_report.json",
        )
        imported_card_behavior_plan = _read_plan_report(
            plan_dir,
            "card_behavior_plan_report.json",
        )
        imported_combo_plan = _read_plan_report(
            plan_dir,
            "combo_plan_report.json",
        )
        imported_global_values_authority_matrix = _read_plan_report(
            plan_dir,
            "global_values_authority_matrix.json",
        )
        if imported_global_values_authority_matrix is not None:
            global_values_authority_matrix = (
                imported_global_values_authority_matrix
            )
        plan_input_diagnostics = _build_plan_input_diagnostics(
            canonical_guide_claim_bundle=canonical_guide_claim_bundle,
            imported_guide_claim_bundle=imported_plan_guide_claim_bundle,
            imported_mulligan_plan=imported_mulligan_plan,
            imported_card_behavior_plan=imported_card_behavior_plan,
            imported_combo_plan=imported_combo_plan,
            imported_global_values_authority_matrix=(
                imported_global_values_authority_matrix or {}
            ),
        )
        (
            mulligan_plan,
            card_behavior_plan,
            combo_plan,
            global_values_authority_matrix,
        ) = _filter_plan_reports_by_lifecycle(
            initial_lifecycle_rows=initial_lifecycle_rows,
            mulligan_plan=mulligan_plan,
            card_behavior_plan=card_behavior_plan,
            combo_plan=combo_plan,
            global_values_authority_matrix=global_values_authority_matrix,
            canonical_global_values_authority_matrix=(
                canonical_global_values_authority_matrix
            ),
            card_roles=card_roles,
            deck_identity=deck_identity,
            verified_source_receipts=verified_source_receipts,
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
        static_runtime_suppressed_card_ids=card_behavior_plan.get(
            "static_runtime_suppressed_card_ids",
            [],
        ),
    )
    card_behavior_plan.setdefault("merged_duplicate_runtime_row_count", 0)
    card_behavior_plan.setdefault("runtime_row_conflicts", [])
    card_behavior_plan["compiler_merged_duplicate_runtime_row_count"] = (
        cardid_behavior_files.merged_duplicate_runtime_row_count
    )
    card_behavior_plan["compiler_runtime_row_conflicts"] = (
        cardid_behavior_files.runtime_row_conflicts
    )
    config_readiness_report = build_config_readiness_report(
        deck_identity=deck_identity,
        claim_coverage=guide_claim_bundle["coverage"],
        gameplan_contract=gameplan_contract,
        mulligan_plan=mulligan_plan,
        card_behavior_plan=card_behavior_plan,
        combo_plan=combo_plan,
        global_values_authority_matrix=global_values_authority_matrix,
        emitted_cardid_files=cardid_behavior_files,
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
    derivation_receipt_path = out / DERIVATION_RECEIPT_PATH
    if derivation_receipt_path.is_file():
        derivation_receipt_path.unlink()
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
        source_claim_conflict_report,
    )
    write_json(
        reports_dir / "unsupported_claims_report.json",
        guide_claim_bundle["unsupported_claims"],
    )
    write_research_contract_bundle(
        research_bundle,
        reports_dir,
        guide_claim_bundle=guide_claim_bundle,
    )
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
    if plan_input_diagnostics is not None:
        write_json(
            reports_dir / "plan_input_diagnostics.json",
            plan_input_diagnostics,
        )
    write_json(reports_dir / "per_card_config_readiness_report.json", config_readiness_report)
    write_json(reports_dir / "guide_source_depth_report.json", guide_source_depth_report)
    source_contract_audit_report = build_source_contract_audit(
        deck_name=args.deck_name,
        deck_identity=deck_identity,
        guide_claim_bundle=authority_guide_claim_bundle,
        mulligan_plan=mulligan_plan,
        card_behavior_plan=card_behavior_plan,
        combo_plan=combo_plan,
        global_values_authority_matrix=global_values_authority_matrix,
        config_readiness_report=config_readiness_report,
        initial_lifecycle_rows=initial_lifecycle_rows,
        plan_input_diagnostics=plan_input_diagnostics,
    )
    write_json(reports_dir / "source_contract_audit.json", source_contract_audit_report)
    (reports_dir / "source_contract_audit.md").write_text(
        render_source_contract_audit_markdown(source_contract_audit_report),
        encoding="utf-8",
        newline="\n",
    )
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
        source_contract_audit=source_contract_audit_report,
    )
    write_json(reports_dir / "source_claim_gap_report.json", source_claim_gap_report)
    source_to_runtime_explainability_report = (
        build_source_to_runtime_explainability_report(
            source_contract_audit_report,
            card_behavior_plan=card_behavior_plan,
        )
    )
    write_json(
        reports_dir / "source_to_runtime_explainability.json",
        source_to_runtime_explainability_report,
    )
    write_json(
        reports_dir / "global_values_blocked_changes.json",
        global_values_authority_matrix["blocked_until_runtime_evidence"],
    )
    write_json(reports_dir / "globalvalues_baseline.json", baseline)
    write_json(reports_dir / "globalvalues_baseline_receipt.json", baseline_receipt)
    write_json(reports_dir / "globalvalues_profile.json", globalvalues["profile"])
    write_json(reports_dir / "global_values_key_profile_report.json", globalvalues["profile"])

    report = validate_complete_package(out)
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
        "source_claim_gap_report": source_claim_gap_report,
        "source_contract_audit_report": source_contract_audit_report,
        "source_to_runtime_explainability_report": (
            source_to_runtime_explainability_report
        ),
        "gameplan_contract": gameplan_contract,
    }
    generated_files = _generated_package_files(
        out,
        deck_dir,
        reports_dir,
        expected_report_files=(
            "card_semantic_audit.md",
            "operator_summary.json",
            "strong_promotion_report.json",
            "output_ownership_manifest.json",
            "source_evidence_closure.json",
        ),
        expected_package_files=(DERIVATION_RECEIPT_PATH,),
    )
    output_ownership_manifest = build_output_ownership_manifest(
        generated_files,
        card_behavior_plan=card_behavior_plan,
    )
    write_json(reports_dir / "output_ownership_manifest.json", output_ownership_manifest)
    package_derivation = refresh_package_derivation_authority(out)
    package_authority = build_package_authority_context(out)
    operator_summary = build_operator_summary(
        generated_files=generated_files,
        output_ownership_manifest=output_ownership_manifest,
        package_derivation=package_derivation,
        package_authority=package_authority,
        **operator_summary_kwargs,
    )
    (reports_dir / "card_semantic_audit.md").write_text(
        render_semantic_audit_markdown(
            {
                **semantic_report,
                "configuration_assurance": operator_summary[
                    "configuration_assurance"
                ],
            }
        ),
        encoding="utf-8",
        newline="\n",
    )
    strong_promotion_report = build_strong_promotion_report(
        deck_name=args.deck_name,
        fixture_stage="runtime_prepare",
        operator_summary=operator_summary,
        source_claim_gap_report=source_claim_gap_report,
    )
    source_evidence_closure_report = build_source_evidence_closure_report(
        deck_name=args.deck_name,
        deck_code=args.deck_code,
        operator_summary=operator_summary,
        source_to_runtime_explainability_report=(
            source_to_runtime_explainability_report
        ),
        source_claim_gap_report=source_claim_gap_report,
    )
    write_json(reports_dir / "strong_promotion_report.json", strong_promotion_report)
    write_json(
        reports_dir / "source_evidence_closure.json",
        source_evidence_closure_report,
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

    context = build_preconfig_context(
        args,
        fetch_latest_cards_fn=fetch_latest_cards,
        fetch_latest_collectible_cards_fn=None,
        research_required_guide_sources_fn=_research_required_guide_sources,
    )
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


def _runtime_evidence_globalvalue_claims(
    lifecycle_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    claims: list[dict[str, Any]] = []
    for row in lifecycle_rows:
        if row.get("quarantine_status") == "quarantined":
            continue
        if row.get("claim_kind") != "globalvalue_numeric_tuning":
            continue
        claim = dict(row.get("claim") or {})
        claim["claim_kind"] = "globalvalue_numeric_tuning"
        claim["_claim_lifecycle"] = {
            "claim_id": row.get("claim_id"),
            "surface": "globalvalues",
            "policy_lane": row.get("policy_lane"),
            "surface_gate_reason": "requires_runtime_evidence",
        }
        claims.append(claim)
    return claims


def _generated_package_files(
    out: Path,
    deck_dir: Path,
    reports_dir: Path,
    *,
    expected_report_files: tuple[str, ...] = ("operator_summary.json",),
    expected_package_files: tuple[str, ...] = (),
) -> list[str]:
    files = [
        *sorted(deck_dir.glob("*.json")),
        *sorted(path for path in reports_dir.rglob("*") if path.is_file()),
        *(reports_dir / filename for filename in expected_report_files),
        *(out / filename for filename in expected_package_files),
    ]
    return sorted({str(path.relative_to(out)) for path in files})


def _reset_generated_package_dirs(deck_dir: Path, reports_dir: Path) -> None:
    for target in (deck_dir, reports_dir):
        if target.exists():
            shutil.rmtree(target)


def _read_plan_report(
    plan_dir: Path,
    filename: str,
) -> dict[str, Any] | None:
    path = plan_dir / filename
    if not path.exists():
        return None
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Plan report must be an object: {path}")
    return payload


def _normalize_claim_conflict_report(bundle: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(bundle)
    claims = normalized.get("claims", [])
    if not isinstance(claims, list):
        claims = []
    normalized["claim_conflict_report"] = build_claim_conflict_report(
        [claim for claim in claims if isinstance(claim, dict)]
    )
    return normalized


def _build_plan_input_diagnostics(
    *,
    canonical_guide_claim_bundle: dict[str, Any],
    imported_guide_claim_bundle: dict[str, Any],
    imported_mulligan_plan: dict[str, Any] | None,
    imported_card_behavior_plan: dict[str, Any] | None,
    imported_combo_plan: dict[str, Any] | None,
    imported_global_values_authority_matrix: dict[str, Any],
) -> dict[str, Any]:
    imported_mulligan_payload = imported_mulligan_plan or {}
    imported_card_behavior_payload = imported_card_behavior_plan or {}
    imported_combo_payload = imported_combo_plan or {}
    canonical_claim_ids = {
        str(claim.get("claim_id", ""))
        for claim in canonical_guide_claim_bundle.get("claims", [])
        if isinstance(claim, dict) and claim.get("claim_id")
    }
    imported_claims = [
        claim
        for claim in imported_guide_claim_bundle.get("claims", [])
        if isinstance(claim, dict)
    ]
    ignored_claims = []
    for claim in imported_claims:
        claim_id = str(claim.get("claim_id", ""))
        ignored_claims.append(
            {
                "claim_id": claim_id,
                "claim_kind": normalized_claim_kind(claim),
                "reason": (
                    "plan_claim_reference_only_canonical_truth_retained"
                    if claim_id and claim_id in canonical_claim_ids
                    else "plan_claim_not_canonical_source_truth"
                ),
                "runtime_gate_impact": "none",
            }
        )

    imported_rows: list[dict[str, Any]] = []
    for report_name, section, rows in (
        (
            "mulligan_plan_report.json",
            "rules",
            imported_mulligan_payload.get("rules", []),
        ),
        (
            "card_behavior_plan_report.json",
            "rows",
            imported_card_behavior_payload.get("rows", []),
        ),
        (
            "combo_plan_report.json",
            "combos",
            imported_combo_payload.get("combos", []),
        ),
        (
            "global_values_authority_matrix.json",
            "allowed_step1_overlays",
            imported_global_values_authority_matrix.get(
                "allowed_step1_overlays",
                [],
            ),
        ),
        (
            "global_values_authority_matrix.json",
            "blocked_until_runtime_evidence",
            imported_global_values_authority_matrix.get(
                "blocked_until_runtime_evidence",
                [],
            ),
        ),
    ):
        if not isinstance(rows, list):
            continue
        imported_rows.extend(
            {
                "report": report_name,
                "section": section,
                "row": dict(row),
            }
            for row in rows
            if isinstance(row, dict)
        )

    imported_receipts = imported_guide_claim_bundle.get(
        "canonical_source_receipts",
        imported_guide_claim_bundle.get("globalvalues_source_receipts", []),
    )
    imported_plan_reports = {
        filename: dict(payload)
        for filename, payload in (
            ("mulligan_plan_report.json", imported_mulligan_plan),
            (
                "card_behavior_plan_report.json",
                imported_card_behavior_plan,
            ),
            ("combo_plan_report.json", imported_combo_plan),
        )
        if payload is not None
    }
    return {
        "authority": "diagnostic_only",
        "runtime_gate_impact": "none",
        "guide_claim_bundle_status": "ignored_as_runtime_authority",
        "source_receipts_status": "ignored_as_runtime_authority",
        "canonical_claim_ids": sorted(canonical_claim_ids),
        "imported_claim_count": len(imported_claims),
        "imported_claims": [dict(claim) for claim in imported_claims],
        "imported_source_receipt_count": (
            len(imported_receipts) if isinstance(imported_receipts, list) else 0
        ),
        "imported_source_receipts": (
            [
                dict(receipt) if isinstance(receipt, dict) else receipt
                for receipt in imported_receipts
            ]
            if isinstance(imported_receipts, list)
            else []
        ),
        "ignored_claims": ignored_claims,
        "imported_row_count": len(imported_rows),
        "imported_rows": imported_rows,
        "imported_plan_reports": imported_plan_reports,
    }


def _policy_mulligan_deck_cards(
    gameplan_cards: Any,
    card_metadata: dict[str, Any] | list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    metadata_by_card = _metadata_rows_by_card(card_metadata)
    if isinstance(gameplan_cards, dict):
        rows = gameplan_cards.items()
    elif isinstance(gameplan_cards, list):
        rows = (
            (str(row.get("card_id", row.get("id", ""))), row)
            for row in gameplan_cards
            if isinstance(row, dict)
        )
    else:
        rows = []
    merged: dict[str, dict[str, Any]] = {}
    for card_id, row in rows:
        card_id = str(card_id)
        if not card_id:
            continue
        base = metadata_by_card.get(card_id, {})
        if isinstance(row, dict):
            merged[card_id] = {**base, **row}
        else:
            merged[card_id] = {**base, "card_id": card_id}
    return merged


def _policy_mulligan_excluded_card_ids(
    accepted_mulligan_claims: list[dict[str, Any]],
) -> set[str]:
    cards: set[str] = set()
    for claim in accepted_mulligan_claims:
        if str(claim.get("claim_kind", "")) not in {"mulligan_keep", "mulligan_discard"}:
            continue
        cards.update(_claim_card_ids(claim))
    return cards


def _claim_card_ids(claim: dict[str, Any]) -> set[str]:
    cards = claim.get("cards", [])
    if isinstance(cards, str):
        cards = [cards]
    if not isinstance(cards, list):
        return set()
    return {str(card) for card in cards if str(card)}


def _metadata_rows_by_card(
    card_metadata: dict[str, Any] | list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    rows = card_metadata.get("cards", []) if isinstance(card_metadata, dict) else card_metadata
    if not isinstance(rows, list):
        return {}
    return {
        str(row["card_id"]): dict(row)
        for row in rows
        if isinstance(row, dict) and row.get("card_id")
    }


def _filter_plan_reports_by_lifecycle(
    *,
    initial_lifecycle_rows: list[dict[str, Any]],
    mulligan_plan: dict[str, Any],
    card_behavior_plan: dict[str, Any],
    combo_plan: dict[str, Any],
    global_values_authority_matrix: dict[str, Any],
    canonical_global_values_authority_matrix: dict[str, Any],
    card_roles: dict[str, Any],
    deck_identity: dict[str, Any],
    verified_source_receipts: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    globalvalues_selection = select_claims_for_surface(
        initial_lifecycle_rows,
        "globalvalues",
        context={
            "deck_identity": deck_identity,
            "verified_source_receipts": verified_source_receipts,
        },
    )
    globalvalues_decision_claims = [
        *globalvalues_selection["accepted_claims"],
        *globalvalues_selection["rejected_claims"],
    ]
    del card_roles
    globalvalues_diagnostics = build_globalvalues_authority_matrix(
        aggression_profile="baseline",
        claims=globalvalues_decision_claims,
        deck_identity=deck_identity,
        verified_source_receipts=verified_source_receipts,
    )
    return (
        mulligan_plan,
        card_behavior_plan,
        combo_plan,
        _filter_globalvalues_authority_matrix(
            global_values_authority_matrix,
            canonical_matrix=canonical_global_values_authority_matrix,
            diagnostic_matrix=globalvalues_diagnostics,
        ),
    )


def _runtime_claim_ids_for_surface(
    lifecycle_rows: list[dict[str, Any]],
    surface: str,
    *,
    card_roles: dict[str, Any] | None = None,
) -> set[str]:
    claims = runtime_claims_for_surface(
        lifecycle_rows,
        surface,
        card_roles=card_roles,
    )
    claim_ids: set[str] = set()
    for claim in claims:
        lifecycle = claim.get("_claim_lifecycle")
        if isinstance(lifecycle, dict) and lifecycle.get("claim_id"):
            claim_ids.add(str(lifecycle["claim_id"]))
            continue
        if claim.get("claim_id"):
            claim_ids.add(str(claim["claim_id"]))
    return claim_ids


def _filter_mulligan_plan(
    plan: dict[str, Any],
    allowed_claim_ids: set[str],
) -> dict[str, Any]:
    result = dict(plan)
    filtered_rules = _filter_runtime_rows_by_claim_ids(
        plan.get("rules", []),
        allowed_claim_ids,
    )
    seen_rule_keys = {mulligan_rule_key(row) for row in filtered_rules}
    for row in plan.get("rules", []):
        if not _is_policy_backed_mulligan_row(row):
            continue
        key = mulligan_rule_key(row)
        if key in seen_rule_keys:
            continue
        seen_rule_keys.add(key)
        filtered_rules.append(row)
    if _has_concrete_mulligan_hold(filtered_rules):
        filtered_rules.extend(
            row
            for row in plan.get("rules", [])
            if _is_unreferenced_wildcard_discard(row)
            and not any(_is_unreferenced_wildcard_discard(existing) for existing in filtered_rules)
        )
    result["rules"] = filtered_rules
    return result


def _filter_card_behavior_plan(
    plan: dict[str, Any],
    allowed_claim_ids: set[str],
) -> dict[str, Any]:
    result = dict(plan)
    original_card_ids = _card_ids_from_card_behavior_rows(plan.get("rows", []))
    rows = _filter_runtime_rows_by_claim_ids(plan.get("rows", []), allowed_claim_ids)
    card_rows: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get("card_id"):
            continue
        card_rows.setdefault(str(row["card_id"]), []).append(row)
    kept_card_ids = set(card_rows)
    existing_suppressed = _string_set(plan.get("static_runtime_suppressed_card_ids", []))
    result["rows"] = rows
    result["card_rows"] = {
        card_id: card_rows[card_id] for card_id in sorted(card_rows)
    }
    result["static_runtime_suppressed_card_ids"] = sorted(
        existing_suppressed | (original_card_ids - kept_card_ids)
    )
    return result


def _card_ids_from_card_behavior_rows(rows: Any) -> set[str]:
    if not isinstance(rows, list):
        return set()
    return {
        str(row["card_id"])
        for row in rows
        if isinstance(row, dict)
        and row.get("card_id")
        and (
            row.get("surface_family") == "CARDID.json"
            or row.get("surface") in {"CARDID.json", "CardID.json"}
        )
    }


def _string_set(value: Any) -> set[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return set()
    return {str(item) for item in value if str(item)}


def _filter_combo_plan(
    plan: dict[str, Any],
    allowed_claim_ids: set[str],
) -> dict[str, Any]:
    result = dict(plan)
    result["combos"] = _filter_runtime_rows_by_claim_ids(
        plan.get("combos", []),
        allowed_claim_ids,
    )
    return result


def _filter_globalvalues_authority_matrix(
    matrix: dict[str, Any],
    *,
    canonical_matrix: dict[str, Any],
    diagnostic_matrix: dict[str, Any],
) -> dict[str, Any]:
    result = dict(canonical_matrix)
    allowed_rows = [
        dict(row)
        for row in canonical_matrix.get("allowed_step1_overlays", [])
        if isinstance(row, dict)
    ]
    diagnostic_blocked = [
        row
        for row in diagnostic_matrix.get("blocked_until_runtime_evidence", [])
        if isinstance(row, dict)
    ]
    blocked_rows = [
        dict(row)
        for row in canonical_matrix.get("blocked_until_runtime_evidence", [])
        if isinstance(row, dict)
    ]
    for row in diagnostic_blocked:
        if row not in blocked_rows:
            blocked_rows.append(dict(row))
    canonical_signatures = {
        _globalvalues_plan_row_signature(row)
        for row in allowed_rows
    }
    for row in matrix.get("allowed_step1_overlays", []):
        if not isinstance(row, dict):
            continue
        if row.get("key") == "baseline":
            if any(
                row == canonical_row
                for canonical_row in allowed_rows
                if canonical_row.get("key") == "baseline"
            ):
                continue
        elif _globalvalues_plan_row_signature(row) in canonical_signatures:
            continue
        blocked_rows.append(
            {
                "key": str(row.get("key", "")),
                "operation": str(row.get("operation", "")),
                "overlay": str(row.get("overlay", "")),
                "value": (
                    None
                    if row.get("value") is None
                    else str(row.get("value"))
                ),
                "authority": "source_contract_suppressed",
                "claim_id": str(row.get("claim_id", "")),
                "claim_refs": sorted(_row_claim_ids(row)),
                "reason": "globalvalues_plan_row_not_canonical",
                "blocked_reason": "globalvalues_plan_row_not_canonical",
            }
        )
    result["allowed_step1_overlays"] = allowed_rows
    result["blocked_until_runtime_evidence"] = blocked_rows
    return result


def _globalvalues_plan_row_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(row.get("key", "")),
        str(row.get("operation", "")),
        str(row.get("overlay", "")),
        None if row.get("value") is None else str(row.get("value")),
        str(row.get("reason", "")),
        str(row.get("authority", "")),
        tuple(sorted(_row_claim_ids(row))),
    )


def _filter_runtime_rows_by_claim_ids(
    rows: Any,
    allowed_claim_ids: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    filtered: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_claim_ids = _row_claim_ids(row)
        if not row_claim_ids:
            continue
        if not row_claim_ids & allowed_claim_ids:
            continue
        filtered.append(row)
    return filtered


def _row_claim_ids(row: dict[str, Any]) -> set[str]:
    claim_ids: set[str] = set()
    for key in ("claim_id", "source_claim_id"):
        value = row.get(key)
        if value:
            claim_ids.add(str(value))
    for key in ("claim_ids", "source_claim_ids", "claim_refs", "merged_claim_ids"):
        value = row.get(key, [])
        if isinstance(value, str):
            value = [value]
        if isinstance(value, list):
            claim_ids.update(str(item) for item in value if str(item))
    return claim_ids


def _has_concrete_mulligan_hold(rows: list[dict[str, Any]]) -> bool:
    return any(
        str(row.get("action", row.get("intent", ""))) == "hold"
        and str(row.get("selector_kind", "")) != "wildcard"
        for row in rows
    )


def _is_unreferenced_wildcard_discard(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    if _row_claim_ids(row):
        return False
    return (
        str(row.get("action", row.get("intent", ""))) == "discard"
        and str(row.get("selector_kind", "")) == "wildcard"
        and str(row.get("selector", row.get("card", ""))) == "*"
    )


def _is_policy_backed_mulligan_row(row: Any) -> bool:
    return (
        isinstance(row, dict)
        and str(row.get("source_type")) == "policy_backed_autonomous_mulligan"
    )


def _card_behavior_identity_links(gameplan_contract: dict[str, Any]) -> dict[str, Any]:
    cards = gameplan_contract.get("cards", {})
    if not isinstance(cards, dict):
        return {}
    identity_links: dict[str, Any] = {}
    for card_id, row in cards.items():
        if not isinstance(row, dict):
            continue
        source_card_id = str(card_id)
        links = list(row.get("linked_entities", []))
        owner_links: dict[str, Any] = {"links": links}
        for curated_link in curated_links_for(source_card_id):
            link_kind = str(curated_link.get("link_kind", "")).strip()
            runtime_card_id = str(curated_link.get("card_id", "")).strip()
            if link_kind and runtime_card_id:
                owner_links[link_kind] = runtime_card_id
        identity_links[source_card_id] = owner_links
    return identity_links
