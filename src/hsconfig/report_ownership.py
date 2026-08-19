from __future__ import annotations

from typing import Any

from hsconfig.visionai_registry import (
    OPTIMIZED_START_REPORT_PATHS,
    report_spec,
)


def build_report_ownership(
    *,
    include_optimized_start: bool = False,
) -> list[dict[str, Any]]:
    rows = [
        _report_row(
            "reports/operator_summary.json",
            classification="gate",
            answers="what to do next",
            open_order="1",
            contains=["config_usefulness"],
        ),
        _report_row(
            "reports/output_ownership_manifest.json",
            producer="prepare",
            classification="diagnostic",
            answers="which generated artifact owns which responsibility",
            open_order="11",
            notes="diagnostic only; does not replace operator_summary.json",
        ),
        _report_row(
            "reports/source_bundle.json",
            producer="configure",
            classification="diagnostic",
            answers="the collected source-to-runtime diagnostic chain for configure",
            open_order="12",
            notes="diagnostic only; does not replace operator_summary.json",
        ),
        _report_row(
            "reports/02_source_acquisition/source_closure_intake_receipt.json",
            producer="configure",
            classification="diagnostic",
            answers="which source-candidate rows and fetched records entered configure",
            open_order="12.5",
            notes=(
                "diagnostic only; cannot promote a deck; cannot block apply; "
                "does not replace operator_summary.json"
            ),
        ),
        _report_row(
            "reports/source_contract_audit.json",
            classification="diagnostic",
            answers="why each source claim did or did not lower to runtime config",
            contains="claim lanes, surface gate decisions, policy lanes, first missing links",
            notes=(
                "diagnostic only; does not grant apply permission; "
                "does not replace operator_summary.json"
            ),
            open_order="3",
        ),
        _report_row(
            "reports/source_to_runtime_explainability.json",
            classification="diagnostic",
            answers=(
                "which exact source-to-runtime link is missing before a card can be stronger"
            ),
            contains=(
                "claim rows, card rows, emitted runtime files, missing runtime files, "
                "first missing links, next source actions"
            ),
            notes=(
                "diagnostic only; does not grant apply permission; "
                "does not replace operator_summary.json"
            ),
            open_order="2",
        ),
        _report_row(
            "reports/source_evidence_closure.json",
            producer="prepare",
            classification="diagnostic",
            answers=(
                "compact source evidence closure summary for generated package quality"
            ),
            contains=(
                "semantic status, runtime apply mode, default-only surfaces, "
                "source-to-runtime summary, source evidence closure summary"
            ),
            notes=(
                "diagnostic only; does not grant apply permission; "
                "does not replace operator_summary.json"
            ),
            open_order="2.5",
        ),
        _report_row(
            "reports/layered_evidence_contract.json",
            producer="prepare",
            classification="diagnostic",
            answers="which classified evidence authority binds each package claim",
            open_order="13",
            notes="diagnostic only; does not replace operator_summary.json",
        ),
        _report_row(
            "reports/source_acquisition_closure.json",
            producer="prepare",
            classification="diagnostic",
            answers="whether the typed source acquisition attempt is closed",
            open_order="14",
            notes="diagnostic only; does not replace operator_summary.json",
        ),
        _report_row(
            "reports/disposition_ledger.json",
            producer="prepare",
            classification="diagnostic",
            answers="the final per-card and per-claim semantic disposition",
            open_order="15",
            notes="diagnostic only; does not replace operator_summary.json",
        ),
        _report_row(
            "reports/globalvalues_decision_ledger.json",
            producer="prepare",
            classification="diagnostic",
            answers="the typed decision for every GlobalValues key",
            open_order="16",
            notes="diagnostic only; does not replace operator_summary.json",
        ),
        _report_row(
            "reports/pre_run_closure.json",
            producer="prepare",
            classification="diagnostic",
            answers="whether this package closes the complete pre-run contract",
            open_order="17",
            notes="diagnostic only; does not replace operator_summary.json",
        ),
        _report_row(
            "reports/source_claim_gap_report.json",
            classification="diagnostic",
            answers="which card link is missing first",
            open_order="4",
        ),
        _report_row(
            "reports/strong_promotion_report.json",
            classification="diagnostic",
            answers="whether the package can be called source-backed strong",
            open_order="5",
        ),
        _report_row(
            "reports/per_card_config_readiness_report.json",
            classification="diagnostic",
            answers="which lane each card occupies",
            open_order="6",
        ),
        _report_row(
            "reports/guide_source_depth_report.json",
            classification="diagnostic",
            answers="how strong the guide and source coverage is",
            open_order="7",
        ),
        _report_row(
            "reports/global_values_authority_matrix.json",
            classification="diagnostic",
            answers="which GlobalValues keys are source-backed or archetype-inferred",
            open_order="8",
        ),
        _report_row(
            "reports/mechanic_drift_report.json",
            producer="prepare",
            classification="mechanic_drift",
            open_when=(
                "mechanic_drift_summary shows unknown mechanics, text-only mechanics, "
                "or unknown card types"
            ),
            open_order="9",
        ),
        _report_row(
            "reports/semantic_enrichment_report.json",
            producer="prepare",
            classification="diagnostic",
            open_when=(
                "mechanic_visibility_summary or config_usefulness points to static, "
                "partial, or warning-only mechanic coverage"
            ),
            open_order="10",
        ),
    ]
    if include_optimized_start:
        rows.extend(
            _report_row(
                path,
                producer="prepare",
                classification="diagnostic",
                answers="which frozen optimized-start document bound package strategy",
                open_order="18",
                configuration_modes=["LLM_OPTIMIZED_START"],
                notes=(
                    "mode-bound derivation evidence; diagnostic for human review; "
                    "does not replace operator_summary.json"
                ),
            )
            for path in OPTIMIZED_START_REPORT_PATHS
        )
    return rows


def _report_row(relative_path: str, **metadata: Any) -> dict[str, Any]:
    spec = report_spec(relative_path)
    return {
        "file": spec.relative_path,
        **metadata,
        "authority": spec.ownership,
    }
