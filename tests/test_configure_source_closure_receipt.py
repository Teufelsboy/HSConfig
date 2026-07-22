from __future__ import annotations

from hsconfig.configure_source_closure_receipt import (
    build_configure_source_closure_receipt,
)


def test_configure_source_closure_receipt_reports_strong_clean_source_closure():
    receipt = build_configure_source_closure_receipt(
        operator_summary={
            "runtime_apply_contract": {
                "apply_authority": "reports/operator_summary.json",
            },
            "technical_status": "VALID_PACKAGE",
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "source_strong_ready": True,
            "source_status_apply_blocking": False,
            "source_status_diagnostic_only": True,
            "source_status_reasons": ["source_backed_strong_ready"],
            "first_missing_source_action": "none",
            "default_only_runtime_surfaces": [],
        },
        acceptance_summary={
            "use_config_now": True,
            "normal_apply_authority": "reports/operator_summary.json",
            "next_report_to_open": "reports/operator_summary.json",
        },
        guide_claim_bundle={
            "claims": [
                {"claim_kind": "gameplan_posture"},
                {"claim_kind": "mulligan_keep"},
                {"claim_kind": "hero_power_transform"},
                {"claim_kind": "archetype"},
            ],
        },
        source_documents_payload={
            "source_documents": [
                {"claims": [{"claim_kind": "mulligan_keep"}]},
                {"claims": [{"claim_kind": "targeting_rule"}]},
            ],
        },
        source_candidate_urls=["https://example.test/seed"],
        source_urls=["https://example.test/seed"],
        source_closure_intake_receipt={
            "candidate_count": 1,
            "fetched_record_count": 1,
            "promotion_eligible_seed_count": 1,
            "first_missing_source_action": "none",
        },
    )

    assert receipt == {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "classification": "diagnostic",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "operator_gate": "reports/operator_summary.json",
        "normal_apply_authority": "reports/operator_summary.json",
        "use_config_now": True,
        "technical_status": "VALID_PACKAGE",
        "runtime_apply_allowed": True,
        "runtime_apply_mode": "load_safe_apply",
        "source_backed_status": "SOURCE_BACKED_STRONG",
        "source_strong_ready": True,
        "source_status_diagnostic_only": True,
        "source_status_apply_blocking": False,
        "source_status_reasons": ["source_backed_strong_ready"],
        "first_missing_source_action": "none",
        "source_closure_lane": "strong",
        "default_only_clean": True,
        "default_only_runtime_surfaces": [],
        "source_candidate_url_count": 1,
        "source_url_count": 1,
        "source_intake_candidate_count": 1,
        "source_intake_promotion_eligible_seed_count": 1,
        "fetched_record_count": 1,
        "source_documents_count": 2,
        "compiled_claim_count": 4,
        "compiled_claim_kind_counts": {
            "archetype": 1,
            "gameplan_posture": 1,
            "hero_power_transform": 1,
            "mulligan_keep": 1,
        },
        "runtime_lowerable_claim_count": 3,
        "runtime_lowerable_claim_kind_count": 3,
        "next_report_to_open": "reports/operator_summary.json",
    }


def test_configure_source_closure_receipt_names_runtime_lowerable_claim_gap():
    receipt = build_configure_source_closure_receipt(
        operator_summary={
            "runtime_apply_contract": {
                "apply_authority": "reports/operator_summary.json",
            },
            "technical_status": "VALID_PACKAGE",
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "source_backed_status": "SOURCE_BACKED_PARTIAL",
            "source_strong_ready": False,
            "source_status_apply_blocking": False,
            "source_status_diagnostic_only": True,
            "source_status_reasons": ["semantic_blocker"],
            "first_missing_source_action": "add_card_specific_source_claim",
            "default_only_runtime_surfaces": [],
        },
        acceptance_summary={
            "use_config_now": True,
            "normal_apply_authority": "reports/operator_summary.json",
            "next_report_to_open": "reports/operator_summary.json",
        },
        guide_claim_bundle={
            "claims": [
                {"claim_kind": "archetype"},
                {"claim_kind": "tech_slot"},
            ],
        },
        source_documents_payload={
            "source_documents": [
                {"claims": [{"claim_kind": "archetype"}]},
            ],
        },
        source_candidate_urls=[],
        source_urls=["https://example.test/decklist"],
        source_closure_intake_receipt={
            "candidate_count": 0,
            "fetched_record_count": 1,
            "promotion_eligible_seed_count": 0,
            "first_missing_source_action": "add_card_specific_source_claim",
        },
    )

    assert receipt["authority"] == "diagnostic_only"
    assert receipt["apply_blocking"] is False
    assert receipt["source_status_apply_blocking"] is False
    assert receipt["source_backed_status"] == "SOURCE_BACKED_PARTIAL"
    assert receipt["source_strong_ready"] is False
    assert receipt["source_closure_lane"] == "runtime_lowerable_claim_needed"
    assert receipt["runtime_lowerable_claim_count"] == 0
    assert receipt["first_missing_source_action"] == "add_card_specific_source_claim"
    assert receipt["next_report_to_open"] == "reports/source_to_runtime_explainability.json"


def test_configure_source_closure_receipt_default_only_overrides_strong_claim():
    receipt = build_configure_source_closure_receipt(
        operator_summary={
            "runtime_apply_contract": {
                "apply_authority": "reports/operator_summary.json",
            },
            "technical_status": "VALID_PACKAGE",
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "source_strong_ready": True,
            "source_status_apply_blocking": False,
            "source_status_diagnostic_only": True,
            "source_status_reasons": ["default_only_runtime_surface"],
            "first_missing_source_action": (
                "replace_default_only_runtime_surface_with_source_or_policy_claim"
            ),
            "default_only_runtime_surfaces": ["Mulligan.json"],
        },
        acceptance_summary={
            "use_config_now": True,
            "normal_apply_authority": "reports/operator_summary.json",
            "next_report_to_open": "reports/contract_doctor.json",
        },
        guide_claim_bundle={"claims": [{"claim_kind": "mulligan_keep"}]},
        source_documents_payload=None,
        source_candidate_urls=[],
        source_urls=[],
        source_closure_intake_receipt=None,
    )

    assert receipt["source_backed_status"] == "SOURCE_BACKED_STRONG"
    assert receipt["source_strong_ready"] is False
    assert receipt["default_only_clean"] is False
    assert receipt["default_only_runtime_surfaces"] == ["Mulligan.json"]
    assert receipt["source_closure_lane"] == "default_only_runtime_surface"
    assert receipt["next_report_to_open"] == "reports/contract_doctor.json"
