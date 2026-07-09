from pathlib import Path

from hsconfig.operator_guidance import build_operator_guidance


def test_operator_docs_point_to_research_index_without_making_it_operator_path():
    text = Path("docs/operator/README.md").read_text(encoding="utf-8")

    assert "Research artifacts are evidence, not operator instructions." in text
    assert "docs/research/README.md" in text
    assert (
        "source-manifest -> draft-source-documents -> research-deck -> prepare -> validate -> apply"
        in text
    )


def test_guidance_for_source_backed_strong_package():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "runtime_apply_mode": "normal_apply",
            "runtime_apply_allowed": True,
            "runtime_apply_requires_flag": None,
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
        "runtime_apply_mode": "normal_apply",
        "runtime_apply_allowed": True,
        "runtime_apply_requires_flag": None,
    }


def test_guidance_mirrors_explicit_runtime_apply_fields_from_summary():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "next_action": "READY_TO_APPLY_OR_HANDOFF",
            "apply_policy": "ALLOWED",
            "runtime_apply_mode": "blocked",
            "runtime_apply_allowed": False,
            "runtime_apply_requires_flag": "--allow-source-informed",
            "semantic_blockers": [],
        }
    )

    assert guidance["runtime_apply_mode"] == "blocked"
    assert guidance["runtime_apply_allowed"] is False
    assert guidance["runtime_apply_requires_flag"] == "--allow-source-informed"


def test_guidance_for_load_safe_warning_package():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "runtime_load_safe": True,
            "runtime_apply_mode": "load_safe_apply",
            "runtime_apply_allowed": True,
            "runtime_apply_requires_flag": None,
            "semantic_blockers": [
                {
                    "reason": "cards_need_guide_claims",
                    "report": "reports/source_claim_gap_report.json",
                }
            ],
        }
    )

    assert guidance["first_report_to_open"] == "reports/operator_summary.json"
    assert guidance["next_report_to_open"] == "reports/source_claim_gap_report.json"
    assert guidance["normal_next_step"] == "apply_with_warnings"
    assert guidance["normal_next_command"] == (
        "hsconfig apply --package <package> --runtime-root <runtime-root> --json"
    )
    assert guidance["safe_to_apply"] is True
    assert guidance["requires_expert_flag"] is False
    assert guidance["runtime_apply_mode"] == "load_safe_apply"
    assert guidance["runtime_apply_allowed"] is True
    assert guidance["runtime_apply_requires_flag"] is None


def test_guidance_for_source_informed_apply_ready_package():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "SOURCE_INFORMED_APPLY_READY",
            "apply_policy": "ALLOWED_SOURCE_INFORMED",
            "runtime_apply_mode": "source_informed_apply_requires_flag",
            "runtime_apply_allowed": True,
            "runtime_apply_requires_flag": "--allow-source-informed",
            "source_informed_apply_readiness": {
                "status": "ready",
                "requires_flag": "--allow-source-informed",
                "source_gap_count": 2,
            },
            "semantic_blockers": [
                {"reason": "cards_need_guide_claims", "count": 1},
                {"reason": "cards_need_mulligan_claims", "count": 1},
            ],
        }
    )

    assert guidance == {
        "first_report_to_open": "reports/operator_summary.json",
        "next_report_to_open": "reports/source_claim_gap_report.json",
        "normal_next_step": "apply_source_informed",
        "normal_next_command": (
            "hsconfig apply --package <package> --runtime-root <runtime-root> "
            "--allow-source-informed --json"
        ),
        "safe_to_apply": True,
        "requires_expert_flag": True,
        "runtime_apply_mode": "source_informed_apply_requires_flag",
        "runtime_apply_allowed": True,
        "runtime_apply_requires_flag": "--allow-source-informed",
    }


def test_guidance_opens_first_semantic_blocker_report_for_claim_conflicts():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "runtime_load_safe": True,
            "runtime_apply_mode": "load_safe_apply",
            "runtime_apply_allowed": True,
            "runtime_apply_requires_flag": None,
            "semantic_blockers": [
                {"reason": "claim_conflicts_present", "report": "reports/claim_conflict_report.json"}
            ],
        }
    )

    assert guidance["next_report_to_open"] == "reports/claim_conflict_report.json"
    assert guidance["normal_next_step"] == "apply_with_warnings"
    assert guidance["safe_to_apply"] is True
    assert guidance["requires_expert_flag"] is False
    assert guidance["runtime_apply_mode"] == "load_safe_apply"
    assert guidance["runtime_apply_allowed"] is True
    assert guidance["runtime_apply_requires_flag"] is None


def test_guidance_opens_first_semantic_blocker_report_for_unsupported_conditions():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "runtime_load_safe": True,
            "runtime_apply_mode": "load_safe_apply",
            "runtime_apply_allowed": True,
            "runtime_apply_requires_flag": None,
            "semantic_blockers": [
                {
                    "reason": "unsupported_conditions_present",
                    "report": "reports/mulligan_plan_report.json",
                }
            ],
        }
    )

    assert guidance["next_report_to_open"] == "reports/mulligan_plan_report.json"
    assert guidance["normal_next_step"] == "apply_with_warnings"
    assert guidance["safe_to_apply"] is True
    assert guidance["requires_expert_flag"] is False
    assert guidance["runtime_apply_mode"] == "load_safe_apply"
    assert guidance["runtime_apply_allowed"] is True
    assert guidance["runtime_apply_requires_flag"] is None


def test_guidance_for_needs_more_research_does_not_offer_expert_flag():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "NEEDS_MORE_RESEARCH",
            "next_action": "RESEARCH_REQUIRED_BEFORE_STRONG_CONFIG",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "semantic_blockers": [],
        }
    )

    assert guidance["next_report_to_open"] == "reports/guide_source_depth_report.json"
    assert guidance["safe_to_apply"] is False
    assert guidance["requires_expert_flag"] is False
    assert guidance["runtime_apply_mode"] == "blocked"
    assert guidance["runtime_apply_allowed"] is False
    assert guidance["runtime_apply_requires_flag"] is None


def test_guidance_for_static_semantics_usable_offers_expert_flag():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "STATIC_SEMANTICS_USABLE",
            "next_action": "READY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "semantic_blockers": [],
        }
    )

    assert guidance["next_report_to_open"] == "reports/guide_source_depth_report.json"
    assert guidance["safe_to_apply"] is False
    assert guidance["requires_expert_flag"] is True
    assert guidance["runtime_apply_mode"] == "blocked"
    assert guidance["runtime_apply_allowed"] is False
    assert guidance["runtime_apply_requires_flag"] is None


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
    assert guidance["runtime_apply_mode"] == "blocked"
    assert guidance["runtime_apply_allowed"] is False
    assert guidance["runtime_apply_requires_flag"] is None
