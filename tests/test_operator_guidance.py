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


def test_operator_readme_has_compact_quick_start_before_details():
    text = Path("docs/operator/README.md").read_text(encoding="utf-8")

    quick_start_index = text.index("## Quick Start")
    preferred_path_index = text.index("## Preferred Normal Path")
    expert_path_index = text.index("## Expert Paths")

    assert quick_start_index < preferred_path_index < expert_path_index
    quick_start = text[quick_start_index:preferred_path_index]

    assert "Run `hsconfig configure` for normal operation." in quick_start
    assert (
        "After `configure`, read `<out>/configure_summary.json.acceptance_summary` first; "
        "it is an operator projection. Use `reports/operator_summary.json` as the "
        "apply authority."
    ) in quick_start
    assert "`technical_status=VALID_PACKAGE` plus `runtime_apply_mode=load_safe_apply` means runtime apply is allowed." in quick_start
    assert "Warnings are follow-up work, not a second apply path." in quick_start
    assert "HSTuner owns post-run evaluation and tuning." in quick_start
    assert len([line for line in quick_start.splitlines() if line.strip().startswith("- ")]) <= 6


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
        "config_usefulness_status": "unknown",
        "config_usefulness_next_report": "reports/operator_summary.json",
        "mechanic_warning_summary": {
            "support_level_counts": {"direct": 0, "partial": 0, "warning_only": 0},
            "warning_only_mechanics": [],
            "warning_only_card_count": 0,
        },
        "mechanic_visibility_summary": {
            "non_blocking": True,
            "bucket_counts": {
                "direct": 0,
                "identity_gated_direct": 0,
                "partial": 0,
                "warning_only": 0,
            },
            "mechanics_by_bucket": {
                "direct": [],
                "identity_gated_direct": [],
                "partial": [],
                "warning_only": [],
            },
            "warning_only_card_count": 0,
            "first_warning_boundary": None,
            "warning_boundaries": [],
        },
        "mechanic_drift_summary": {
            "non_blocking": True,
            "mechanic_count": 0,
            "unknown_mechanic_count": 0,
            "text_only_mechanic_count": 0,
            "unknown_card_type_count": 0,
            "unknown_mechanics": [],
            "text_only_mechanics": [],
            "unknown_card_types": [],
        },
        "runtime_apply_mode": "normal_apply",
        "runtime_apply_allowed": True,
        "runtime_apply_requires_flag": None,
        "runtime_gate_truth": "runtime_apply_mode",
        "source_informed_readiness_scope": "not_present",
        "legacy_source_informed_flag_scope": "not_present",
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


def test_operator_guidance_mentions_config_usefulness_when_load_safe_but_thin():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "STATIC_SEMANTICS_USABLE",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "runtime_apply_mode": "load_safe_apply",
            "runtime_apply_allowed": True,
            "primary_blockers": [],
            "semantic_blockers": [],
            "config_usefulness": {
                "status": "load_safe_but_thin",
                "headline": "Package is load-safe, but config richness is thin; first gap is runtime_surface_gap.",
                "first_usefulness_gap": "runtime_surface_gap",
                "next_report_to_open": "reports/per_card_config_readiness_report.json",
            },
        }
    )

    assert guidance["safe_to_apply"] is True
    assert guidance["config_usefulness_status"] == "load_safe_but_thin"
    assert (
        guidance["config_usefulness_next_report"]
        == "reports/per_card_config_readiness_report.json"
    )


def test_warning_guidance_carries_mechanic_warning_summary():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "mechanic_warning_summary": {
                "support_level_counts": {"direct": 0, "partial": 0, "warning_only": 1},
                "warning_only_mechanics": ["tradeable"],
                "warning_only_card_count": 1,
            },
            "semantic_blockers": [],
        }
    )

    assert guidance["safe_to_apply"] is True
    assert guidance["normal_next_step"] == "apply_with_warnings"
    assert guidance["mechanic_warning_summary"]["warning_only_mechanics"] == ["tradeable"]


def test_warning_guidance_carries_mechanic_visibility_summary():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "mechanic_visibility_summary": {
                "non_blocking": True,
                "bucket_counts": {
                    "direct": 0,
                    "identity_gated_direct": 0,
                    "partial": 1,
                    "warning_only": 1,
                },
                "mechanics_by_bucket": {
                    "direct": [],
                    "identity_gated_direct": [],
                    "partial": ["aura"],
                    "warning_only": ["tradeable"],
                },
                "warning_only_card_count": 1,
                "first_warning_boundary": {
                    "mechanic": "tradeable",
                    "warning_boundary": "Trade-now decisions have no documented normal-path VisionAI runtime block.",
                },
                "warning_boundaries": [
                    {
                        "mechanic": "tradeable",
                        "warning_boundary": "Trade-now decisions have no documented normal-path VisionAI runtime block.",
                    }
                ],
            },
            "semantic_blockers": [],
        }
    )

    assert guidance["safe_to_apply"] is True
    assert guidance["normal_next_step"] == "apply_with_warnings"
    assert guidance["mechanic_visibility_summary"]["non_blocking"] is True
    assert guidance["mechanic_visibility_summary"]["mechanics_by_bucket"]["partial"] == [
        "aura"
    ]
    assert guidance["mechanic_visibility_summary"]["warning_boundaries"] == [
        {
            "mechanic": "tradeable",
            "warning_boundary": "Trade-now decisions have no documented normal-path VisionAI runtime block.",
        }
    ]


def test_warning_guidance_carries_mechanic_drift_summary():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "mechanic_drift_summary": {
                "non_blocking": True,
                "mechanic_count": 3,
                "unknown_mechanic_count": 1,
                "text_only_mechanic_count": 1,
                "unknown_card_type_count": 1,
                "unknown_mechanics": ["future_keyword"],
                "text_only_mechanics": ["tradeable"],
                "unknown_card_types": ["starship"],
            },
            "semantic_blockers": [],
        }
    )

    assert guidance["safe_to_apply"] is True
    assert guidance["normal_next_step"] == "apply_with_warnings"
    assert guidance["mechanic_drift_summary"]["unknown_mechanics"] == [
        "future_keyword"
    ]
    assert guidance["mechanic_drift_summary"]["unknown_card_types"] == ["starship"]


def test_guidance_for_valid_warning_package_with_source_gap_readiness():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "runtime_apply_mode": "load_safe_apply",
            "runtime_apply_allowed": True,
            "runtime_apply_requires_flag": None,
            "source_informed_apply_readiness": {
                "status": "ready",
                "requires_flag": None,
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
        "normal_next_step": "apply_with_warnings",
        "normal_next_command": "hsconfig apply --package <package> --runtime-root <runtime-root> --json",
        "safe_to_apply": True,
        "requires_expert_flag": False,
        "config_usefulness_status": "unknown",
        "config_usefulness_next_report": "reports/operator_summary.json",
        "mechanic_warning_summary": {
            "support_level_counts": {"direct": 0, "partial": 0, "warning_only": 0},
            "warning_only_mechanics": [],
            "warning_only_card_count": 0,
        },
        "mechanic_visibility_summary": {
            "non_blocking": True,
            "bucket_counts": {
                "direct": 0,
                "identity_gated_direct": 0,
                "partial": 0,
                "warning_only": 0,
            },
            "mechanics_by_bucket": {
                "direct": [],
                "identity_gated_direct": [],
                "partial": [],
                "warning_only": [],
            },
            "warning_only_card_count": 0,
            "first_warning_boundary": None,
            "warning_boundaries": [],
        },
        "mechanic_drift_summary": {
            "non_blocking": True,
            "mechanic_count": 0,
            "unknown_mechanic_count": 0,
            "text_only_mechanic_count": 0,
            "unknown_card_type_count": 0,
            "unknown_mechanics": [],
            "text_only_mechanics": [],
            "unknown_card_types": [],
        },
        "runtime_apply_mode": "load_safe_apply",
        "runtime_apply_allowed": True,
        "runtime_apply_requires_flag": None,
        "runtime_gate_truth": "runtime_apply_mode",
        "source_informed_readiness_scope": "diagnostic_only",
        "legacy_source_informed_flag_scope": "backward_compatible_only",
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


def test_operator_guidance_names_runtime_apply_mode_as_gate_truth():
    guidance = build_operator_guidance(
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "runtime_apply_mode": "load_safe_apply",
            "runtime_apply_allowed": True,
            "runtime_apply_requires_flag": None,
            "source_informed_apply_readiness": {
                "status": "blocked",
                "requires_flag": "--allow-source-informed",
                "runtime_gate_impact": "diagnostic_only",
                "legacy_flag_scope": "backward_compatible_only",
                "allowed_blocker_reasons": ["cards_need_guide_claims"],
                "blocking_reasons": ["cards_need_runtime_surface"],
                "source_gap_count": 0,
            },
        }
    )

    assert guidance["safe_to_apply"] is True
    assert guidance["runtime_apply_mode"] == "load_safe_apply"
    assert guidance["runtime_gate_truth"] == "runtime_apply_mode"
    assert guidance["source_informed_readiness_scope"] == "diagnostic_only"
    assert guidance["legacy_source_informed_flag_scope"] == "backward_compatible_only"
