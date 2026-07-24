from __future__ import annotations

from hsconfig.source_readiness_preview import build_source_readiness_preview


def test_preview_reports_source_backed_strong_without_creating_apply_gate() -> None:
    preview = build_source_readiness_preview(
        source_candidate_plan={
            "authority": "diagnostic_source_candidate_plan",
            "source_urls": ["https://example.test/shadowpriest-guide"],
            "target_summary": {
                "card_targets": 3,
                "mulligan_keep_source_targets": 2,
                "effect_semantics_not_mulligan_keep_targets": 1,
            },
            "first_missing_source_action": "none",
        },
        source_autopilot_report={
            "semantic_status": "SOURCE_BACKED_STRONG",
            "strong_candidate": True,
            "strong_closure_summary": {
                "source_backed_strong_ready": True,
                "strong_evidence_row_count": 8,
                "first_missing_source_action": "none",
            },
            "source_backed_strong_closure": {
                "promotion_ready": True,
                "first_missing_source_action": "none",
            },
            "card_rows": [
                {"card_id": "SW_446", "lane": "lowered"},
                {"card_id": "NX2_019", "lane": "lowered"},
            ],
            "surface_rows": [
                {"surface": "Mulligan.json", "lane": "emitted"},
                {"surface": "NX2_019.json", "lane": "emitted"},
            ],
        },
        operator_summary={
            "semantic_status": "SOURCE_BACKED_STRONG",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "default_only_runtime_surfaces": [],
            "source_status_apply_blocking": False,
            "runtime_apply_contract": {
                "apply_authority": "reports/operator_summary.json",
            },
        },
    )

    assert preview == {
        "schema_version": 1,
        "authority": "diagnostic_source_readiness_preview",
        "diagnostic_only": True,
        "runtime_apply_authority": "reports/operator_summary.json",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "source_status_apply_blocking": False,
        "source_candidate_plan_present": True,
        "source_autopilot_report_present": True,
        "operator_summary_present": True,
        "semantic_status": "SOURCE_BACKED_STRONG",
        "source_backed_strong_ready": True,
        "strong_candidate": True,
        "readiness_lane": "source_backed_strong_ready",
        "first_missing_source_action": "none",
        "recommended_next_source_action": "none",
        "candidate_source_url_count": 1,
        "strong_evidence_row_count": 8,
        "card_target_count": 3,
        "mulligan_keep_source_target_count": 2,
        "effect_semantics_not_mulligan_keep_target_count": 1,
        "card_source_gap_count": 0,
        "surface_source_gap_count": 0,
        "default_only_clean": True,
        "default_only_runtime_surfaces": [],
        "runtime_apply_allowed": True,
        "runtime_apply_mode": "load_safe_apply",
        "readiness_summary": "source-backed strong; no source action required",
    }


def test_preview_keeps_strong_default_only_surface_out_of_clean_ready_lane() -> None:
    preview = build_source_readiness_preview(
        operator_summary={
            "semantic_status": "SOURCE_BACKED_STRONG",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "default_only_runtime_surfaces": ["Mulligan.json"],
            "first_missing_source_action": (
                "replace_default_only_runtime_surface_with_source_or_policy_claim"
            ),
            "runtime_apply_contract": {
                "apply_authority": "bad-authority.json",
            },
        },
    )

    assert preview["apply_blocking"] is False
    assert preview["source_status_apply_blocking"] is False
    assert preview["runtime_write_performed"] is False
    assert preview["runtime_apply_allowed"] is True
    assert preview["runtime_apply_mode"] == "load_safe_apply"
    assert preview["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert preview["source_backed_strong_ready"] is False
    assert preview["readiness_lane"] == "default_only_runtime_surface_no_block"
    assert preview["default_only_clean"] is False
    assert preview["default_only_runtime_surfaces"] == ["Mulligan.json"]
    assert preview["first_missing_source_action"] == (
        "replace_default_only_runtime_surface_with_source_or_policy_claim"
    )
    assert preview["recommended_next_source_action"] == (
        "replace_default_only_runtime_surface_with_source_or_policy_claim"
    )
    assert (
        "default_only_runtime_surface_no_block"
        in preview["readiness_summary"]
    )
    assert preview["runtime_apply_authority"] == "reports/operator_summary.json"


def test_preview_reports_partial_source_gap_without_blocking_apply() -> None:
    preview = build_source_readiness_preview(
        source_candidate_plan={
            "source_urls": ["https://example.test/thin-guide"],
            "target_summary": {
                "card_targets": 2,
                "mulligan_keep_source_targets": 1,
            },
            "first_missing_source_action": "fetch_and_normalize_candidate_full_text_claims",
        },
        source_autopilot_report={
            "semantic_status": "SOURCE_BACKED_PARTIAL",
            "strong_candidate": False,
            "strong_closure_summary": {
                "source_backed_strong_ready": False,
                "strong_evidence_row_count": 0,
                "first_missing_source_action": "add_current_card_specific_runtime_source",
            },
            "card_rows": [
                {"card_id": "CARD_001", "lane": "source_gap"},
                {"card_id": "CARD_002", "lane": "static_only"},
            ],
            "surface_rows": [
                {"surface": "Mulligan.json", "lane": "source_gap"},
            ],
        },
        operator_summary={
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "source_status_apply_blocking": False,
            "default_only_runtime_surfaces": [],
        },
    )

    assert preview["authority"] == "diagnostic_source_readiness_preview"
    assert preview["diagnostic_only"] is True
    assert preview["apply_blocking"] is False
    assert preview["source_status_apply_blocking"] is False
    assert preview["semantic_status"] == "SOURCE_BACKED_PARTIAL"
    assert preview["source_backed_strong_ready"] is False
    assert preview["readiness_lane"] == "source_partial_no_block"
    assert preview["first_missing_source_action"] == "add_current_card_specific_runtime_source"
    assert preview["recommended_next_source_action"] == "add_current_card_specific_runtime_source"
    assert preview["card_source_gap_count"] == 1
    assert preview["surface_source_gap_count"] == 1
    assert preview["default_only_clean"] is True
    assert preview["runtime_apply_allowed"] is True


def test_preview_normalizes_boolean_strings_without_blocking_default_only_surfaces() -> None:
    preview = build_source_readiness_preview(
        source_autopilot_report={
            "semantic_status": "SOURCE_BACKED_PARTIAL",
            "strong_candidate": "0",
            "strong_closure_summary": {
                "source_backed_strong_ready": "False",
                "first_missing_source_action": "add_current_card_specific_runtime_source",
            },
        },
        operator_summary={
            "runtime_apply_allowed": "False",
            "default_only_runtime_surfaces": ["Mulligan.json"],
            "source_status_apply_blocking": False,
        },
    )

    assert preview["runtime_apply_allowed"] is False
    assert preview["source_backed_strong_ready"] is False
    assert preview["strong_candidate"] is False
    assert preview["default_only_clean"] is False
    assert preview["default_only_runtime_surfaces"] == ["Mulligan.json"]
    assert preview["apply_blocking"] is False
    assert preview["source_status_apply_blocking"] is False


def test_preview_uses_candidate_plan_when_autopilot_is_not_available() -> None:
    preview = build_source_readiness_preview(
        source_candidate_plan={
            "source_urls": ["https://example.test/guide"],
            "target_summary": {"card_targets": 1},
            "first_missing_source_action": "fetch_and_validate_explicit_source_urls",
        }
    )

    assert preview["source_candidate_plan_present"] is True
    assert preview["source_autopilot_report_present"] is False
    assert preview["operator_summary_present"] is False
    assert preview["readiness_lane"] == "acquisition_plan_ready_no_block"
    assert preview["first_missing_source_action"] == "fetch_and_validate_explicit_source_urls"
    assert preview["source_status_apply_blocking"] is False


def test_preview_handles_missing_inputs_without_runtime_write_or_block() -> None:
    preview = build_source_readiness_preview()

    assert preview["source_candidate_plan_present"] is False
    assert preview["source_autopilot_report_present"] is False
    assert preview["operator_summary_present"] is False
    assert preview["readiness_lane"] == "source_context_missing_no_block"
    assert preview["first_missing_source_action"] == "add_public_guide_url_or_use_static_semantics"
    assert preview["apply_blocking"] is False
    assert preview["runtime_write_performed"] is False
    assert preview["source_status_apply_blocking"] is False
