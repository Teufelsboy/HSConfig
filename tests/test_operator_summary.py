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
    assert summary["semantic_status"] == "SOURCE_BACKED_STRONG"
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
