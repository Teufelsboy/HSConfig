from hsconfig.operator_guidance import build_operator_guidance


def test_guidance_for_source_backed_strong_package():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "semantic_blockers": [],
        }
    )

    assert guidance == {
        "first_report_to_open": "reports/operator_summary.json",
        "next_report_to_open": None,
        "normal_next_step": "apply_or_handoff",
        "normal_next_command": "hsconfig apply --package <package> --runtime-root <runtime-root> --json",
        "safe_to_apply": True,
        "requires_expert_flag": False,
    }


def test_guidance_for_valid_but_not_guide_strong_package():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "semantic_blockers": [{"reason": "cards_need_guide_claims", "count": 2}],
        }
    )

    assert guidance["first_report_to_open"] == "reports/operator_summary.json"
    assert guidance["next_report_to_open"] == "reports/source_claim_gap_report.json"
    assert guidance["normal_next_step"] == "improve_sources"
    assert (
        guidance["normal_next_command"]
        == "update source_documents.json, rerun hsconfig research-deck, then rerun hsconfig prepare"
    )
    assert guidance["safe_to_apply"] is False
    assert guidance["requires_expert_flag"] is True


def test_guidance_for_invalid_package():
    guidance = build_operator_guidance(
        {
            "technical_status": "INVALID_PACKAGE",
            "semantic_status": "INVALID_PACKAGE",
            "next_action": "FIX_PACKAGE_BEFORE_APPLY",
            "apply_policy": "BLOCKED",
            "semantic_blockers": [],
        }
    )

    assert guidance["next_report_to_open"] == "reports/validation_report.json"
    assert guidance["normal_next_step"] == "fix_package"
    assert guidance["safe_to_apply"] is False
    assert guidance["requires_expert_flag"] is False
