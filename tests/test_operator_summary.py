from hsconfig.operator_summary import build_operator_summary


def test_source_backed_valid_package_is_ready_to_apply():
    summary = build_operator_summary(
        deck_name="ShadowPriest",
        deck_code="deck-code",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "source_backed", "source_count": 2, "claim_count": 12},
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=["CustomConfig/shadowpriest/GlobalValues.json"],
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert summary["next_action"] == "READY_TO_APPLY_OR_HANDOFF"
    assert summary["apply_policy"] == "ALLOWED"
    assert summary["primary_blockers"] == []


def test_static_semantics_valid_package_is_ready_with_warnings():
    summary = build_operator_summary(
        deck_name="ShadowPriest",
        deck_code="deck-code",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "static_semantics_only", "source_count": 0},
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=[],
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "STATIC_SEMANTICS_USABLE"
    assert summary["next_action"] == "READY_WITH_WARNINGS"
    assert summary["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    assert any(warning["reason"] == "static_semantics_only" for warning in summary["warnings"])


def test_missing_guide_depth_requests_more_research_without_invalidating_package():
    summary = build_operator_summary(
        deck_name="ShadowPriest",
        deck_code="deck-code",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"depth_status": "needs_more_research"},
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=[],
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "NEEDS_MORE_RESEARCH"
    assert summary["next_action"] == "RESEARCH_REQUIRED_BEFORE_STRONG_CONFIG"
    assert summary["apply_policy"] == "ALLOWED_WITH_WARNINGS"


def test_source_backed_without_effective_claims_requests_more_research():
    summary = build_operator_summary(
        deck_name="ShadowPriest",
        deck_code="deck-code",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "source_count": 1,
            "claim_count": 0,
        },
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=[],
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "NEEDS_MORE_RESEARCH"
    assert summary["next_action"] == "RESEARCH_REQUIRED_BEFORE_STRONG_CONFIG"


def test_operator_summary_marks_valid_package_not_guide_strong_when_many_cards_need_claims():
    summary = build_operator_summary(
        deck_name="Fixture",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 3},
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=["CustomConfig/fixture/GlobalValues.json"],
        claim_coverage_report={
            "total_cards": 10,
            "guide_backed_cards": 1,
            "uncovered_cards": ["A", "B", "C"],
        },
        config_readiness_summary={"generic_low_confidence": 3},
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["next_action"] == "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY"


def test_operator_summary_marks_valid_package_not_guide_strong_when_claims_conflict():
    summary = build_operator_summary(
        deck_name="Fixture",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "source_backed", "claim_count": 12},
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=["CustomConfig/fixture/GlobalValues.json"],
        claim_conflict_report={"conflict_count": 1, "conflicts": [{"card_id": "CARD_A"}]},
        claim_coverage_report={
            "summary": {
                "guide_backed": 9,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 0,
            }
        },
        config_readiness_summary={"generic_low_confidence": 0},
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["next_action"] == "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY"


def test_invalid_package_blocks_apply():
    summary = build_operator_summary(
        deck_name="ShadowPriest",
        deck_code="deck-code",
        technical_validation={"status": "failed", "errors": ["bad json"]},
        guide_source_depth={"source_depth_status": "source_backed", "claim_count": 12},
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=[],
    )

    assert summary["technical_status"] == "INVALID_PACKAGE"
    assert summary["semantic_status"] == "INVALID_PACKAGE"
    assert summary["next_action"] == "FIX_PACKAGE_BEFORE_APPLY"
    assert summary["apply_policy"] == "BLOCKED"
    assert summary["primary_blockers"] == [{"reason": "bad json"}]


def test_unsupported_conditions_are_operator_warnings():
    summary = build_operator_summary(
        deck_name="ShadowPriest",
        deck_code="deck-code",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "source_backed", "claim_count": 12},
        unsupported_conditions=[{"card_id": "CARD_001", "reason": "unsupported_condition"}],
        globalvalue_authority={"blocked_until_runtime_evidence": [{"key": "LowHpBoardValuePenalty"}]},
        generated_files=[],
    )

    reasons = {warning["reason"] for warning in summary["warnings"]}
    assert "unsupported_condition" in reasons
    assert "globalvalue_runtime_evidence_required" in reasons


def test_claim_conflicts_and_low_confidence_coverage_are_operator_warnings():
    summary = build_operator_summary(
        deck_name="ShadowPriest",
        deck_code="deck-code",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "source_backed", "claim_count": 12},
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        claim_conflict_report={"conflict_count": 1, "conflicts": [{"card_id": "CARD_A"}]},
        claim_coverage_report={
            "summary": {
                "guide_backed": 1,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 2,
            }
        },
        generated_files=[],
    )

    assert {"reason": "claim_conflicts_present", "conflict_count": 1} in summary["warnings"]
    assert {"reason": "cards_still_low_confidence", "card_count": 2} in summary["warnings"]


def test_operator_summary_explains_valid_but_not_guide_strong_with_semantic_blockers():
    summary = build_operator_summary(
        deck_name="Fixture",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "source_backed", "claim_count": 8},
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=["CustomConfig/fixture/GlobalValues.json"],
        claim_coverage_report={
            "summary": {
                "guide_backed": 2,
                "static_semantics_backfilled": 1,
                "uncovered_low_confidence": 2,
            },
            "uncovered_cards": ["CARD_A", "CARD_B"],
        },
        config_readiness_summary={
            "total_cards": 5,
            "runtime_emitted": 1,
            "mulligan_only": 1,
            "globalvalues_only": 0,
            "report_only_supported": 1,
            "archetype_inferred": 0,
            "generic_low_confidence": 2,
            "cards_needing_guide_claims": 2,
            "cards_needing_runtime_surface": 1,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        config_readiness_report={
            "cards": {
                "CARD_A": {
                    "name": "Card A",
                    "readiness_lane": "generic_low_confidence",
                    "first_missing_link": "needs_guide_claim",
                },
                "CARD_B": {
                    "name": "Card B",
                    "readiness_lane": "generic_low_confidence",
                    "first_missing_link": "needs_guide_claim",
                },
                "CARD_C": {
                    "name": "Card C",
                    "readiness_lane": "report_only_supported",
                    "first_missing_link": "needs_runtime_surface",
                },
            }
        },
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["guide_strength_summary"] == {
        "total_cards": 5,
        "guide_backed_cards": 2,
        "static_semantics_cards": 1,
        "generic_low_confidence_cards": 2,
        "uncovered_cards": 2,
        "claim_conflicts": 0,
        "runtime_emitted_cards": 1,
        "cards_needing_guide_claims": 2,
        "cards_needing_runtime_surface": 1,
        "cards_needing_mulligan_claims": 0,
        "cards_needing_combo_sequence": 0,
        "cards_needing_condition_lowering": 0,
        "cards_needing_mechanic_lowering": 0,
        "source_backed_strong_requires": [
            "technical_status=VALID_PACKAGE",
            "source_depth_status=source_backed",
            "claim_count>0",
            "generic_low_confidence_cards=0",
            "uncovered_cards=0",
            "claim_conflicts=0",
        ],
    }
    assert summary["semantic_blockers"][0] == {
        "reason": "cards_need_guide_claims",
        "count": 2,
        "blocking_strength": "blocks_source_backed_strong",
        "report": "reports/per_card_config_readiness_report.json",
        "affected_cards": [
            {"card_id": "CARD_A", "name": "Card A"},
            {"card_id": "CARD_B", "name": "Card B"},
        ],
    }
    assert {
        "reason": "cards_need_runtime_surface",
        "count": 1,
        "blocking_strength": "report_visible_gap",
        "report": "reports/per_card_config_readiness_report.json",
        "affected_cards": [{"card_id": "CARD_C", "name": "Card C"}],
    } in summary["semantic_blockers"]


def test_operator_summary_explains_claim_conflict_blocker():
    summary = build_operator_summary(
        deck_name="Fixture",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "source_backed", "claim_count": 8},
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=[],
        claim_conflict_report={"conflict_count": 1, "conflicts": [{"card_id": "CARD_A"}]},
        claim_coverage_report={
            "summary": {
                "guide_backed": 3,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 0,
            },
            "uncovered_cards": [],
        },
        config_readiness_summary={"total_cards": 3, "generic_low_confidence": 0},
    )

    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert {
        "reason": "claim_conflicts_present",
        "count": 1,
        "blocking_strength": "blocks_source_backed_strong",
        "report": "reports/claim_conflict_report.json",
        "affected_cards": [{"card_id": "CARD_A", "name": "CARD_A"}],
    } in summary["semantic_blockers"]
