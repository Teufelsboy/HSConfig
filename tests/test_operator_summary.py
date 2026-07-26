import ast
from pathlib import Path

import pytest

from hsconfig.operator_summary import _closure_matches_surface, build_operator_summary
from hsconfig.source_to_runtime_explainability import (
    build_source_to_runtime_explainability_report,
)


def test_operator_summary_has_single_string_list_helper() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "hsconfig"
        / "operator_summary.py"
    ).read_text(encoding="utf-8")

    module = ast.parse(source)
    string_list_helpers = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "_string_list"
    ]

    assert len(string_list_helpers) == 1


def _source_backed_mulligan_plan_report():
    return {
        "rules": [
            {
                "card": "SOURCE_KEEP",
                "selector_kind": "card",
                "action": "hold",
                "source_type": "source_backed",
            }
        ],
        "quality": {
            "status": "rich",
            "has_concrete_keeps": True,
            "default_only": False,
            "source_backed_rule_count": 1,
        },
    }


def _strong_candidate_with_lane_counts(lane_counts):
    profile_lane = next(iter(lane_counts), "deck_matched_public_guide")
    return build_operator_summary(
        deck_name="LaneCountFixture",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 3,
            "source_evidence": {"warnings_count": 0},
        },
        unsupported_conditions=[],
        claim_coverage_report={
            "summary": {
                "guide_backed": 3,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 0,
            },
            "uncovered_cards": [],
        },
        config_readiness_summary={
            "total_cards": 3,
            "runtime_emitted": 3,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        claim_conflict_report={"conflict_count": 0, "conflicts": []},
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
        source_claim_gap_report={
            "summary": {"source_quality_lane_counts": lane_counts}
        },
        source_to_runtime_explainability_report=_guide_backed_profile_report(
            ["gameplan_posture"],
            source_lane=profile_lane,
        ),
        generated_files=[
            "CustomConfig/lanecountfixture/GlobalValues.json",
            "CustomConfig/lanecountfixture/Mulligan.json",
        ],
    )


def test_operator_summary_separates_pre_run_assurance_dimensions():
    summary = _strong_candidate_with_lane_counts(
        {"deck_matched_public_guide": 3}
    )

    assert summary["configuration_assurance"] == {
        "load_safety": "validated",
        "source_authority": "exact",
        "semantic_closure": "closed",
        "in_client_behavior": "not_proven_by_pre_run_contract",
        "optimality_claim_allowed": False,
        "runtime_gate_impact": "none",
    }


def test_operator_summary_does_not_allow_optimality_claim_for_archetype_only_source():
    summary = _strong_candidate_with_lane_counts(
        {"archetype_matched_public_guide": 3}
    )

    assert summary["configuration_assurance"]["source_authority"] == "archetype_only"
    assert summary["configuration_assurance"]["optimality_claim_allowed"] is False


def _guide_backed_profile_report(
    claim_kinds,
    *,
    source_lane="deck_matched_public_guide",
):
    return {
        "summary": {"cards_with_first_missing_link": 0},
        "claim_lifecycle_rows": [
            {
                "claim_kind": claim_kind,
                "source_lane": source_lane,
                "strategic_receipt_verified": (
                    source_lane == "deck_matched_public_guide"
                ),
            }
            for claim_kind in claim_kinds
        ],
        "card_rows": [],
    }


def _semantic_blocker_codes(summary):
    return {blocker.get("code") for blocker in summary.get("semantic_blockers", [])}


@pytest.mark.parametrize(
    ("surface", "runtime_files", "expected"),
    [
        ("mulligan", ["Mulligan.json"], True),
        ("mulligan", [], False),
        ("globalvalues", ["GlobalValues.json"], True),
        ("combo", ["Combo.json"], True),
        ("cardid_behavior", ["CARD_001.json"], True),
        (
            "cardid_behavior",
            ["Mulligan.json", "GlobalValues.json", "Combo.json"],
            False,
        ),
        ("cardid_behavior", ["diagnostic.txt"], False),
    ],
)
def test_operator_summary_maps_runtime_surfaces_to_declared_json_files(
    surface, runtime_files, expected
):
    row = {"closure": {"runtime_surfaces": runtime_files}}

    assert _closure_matches_surface(row, surface) is expected


def test_source_backed_valid_package_is_ready_to_apply():
    summary = build_operator_summary(
        deck_name="ShadowPriest",
        deck_code="deck-code",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "source_backed", "source_count": 2, "claim_count": 12},
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=[
            "CustomConfig/shadowpriest/GlobalValues.json",
            "CustomConfig/shadowpriest/Mulligan.json",
        ],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
        source_to_runtime_explainability_report=_guide_backed_profile_report(
            ["gameplan_posture", "mulligan_keep", "hero_power_transform"]
        ),
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert summary["next_action"] == "READY_TO_APPLY_OR_HANDOFF"
    assert summary["apply_policy"] == "ALLOWED"
    assert summary["runtime_load_safe"] is True
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["runtime_apply_requires_flag"] is None
    assert summary["primary_blockers"] == []
    assert summary["operator_guidance"]["safe_to_apply"] is True
    assert summary["operator_guidance"]["normal_next_step"] == "apply_or_handoff"


def test_operator_summary_keeps_load_apply_allowed_when_semantic_handoff_needs_attention():
    summary = build_operator_summary(
        deck_name="Semantic Attention",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 1,
            "source_evidence": {"warnings_count": 0},
        },
        card_behavior_plan_report={
            "rows": [],
            "suppressed": [
                {
                    "claim_id": "claim_semantic_gap",
                    "cards": ["CFM_637"],
                    "reason": "semantic_surface_not_expressible",
                }
            ],
        },
        source_claim_gap_report={
            "summary": {
                "source_quality_lane_counts": {
                    "deck_matched_public_guide": 1,
                }
            }
        },
    )

    assert summary["load_safe_to_install"] is True
    assert summary["use_config_now"] is True
    assert summary["use_config_now_scope"] == "load_safety_only"
    assert summary["semantic_handoff_status"] == "attention"
    assert summary["semantic_handoff_reasons"] == [
        "semantic_surface_not_expressible"
    ]
    assert summary["runtime_apply_allowed"] is True


def test_operator_summary_exposes_mechanic_warnings_without_blocking_apply():
    summary = build_operator_summary(
        deck_name="Warning Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed"},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        config_readiness_report={
            "summary": {
                "total_cards": 1,
                "generic_low_confidence": 0,
                "cards_needing_guide_claims": 0,
                "cards_needing_runtime_surface": 0,
                "cards_needing_mulligan_claims": 0,
                "cards_needing_combo_sequence": 0,
                "cards_needing_condition_lowering": 0,
                "cards_needing_mechanic_lowering": 0,
                "mechanic_support": {
                    "support_level_counts": {"direct": 0, "partial": 0, "warning_only": 1},
                    "warning_only_mechanics": ["dredge"],
                    "warning_only_card_count": 1,
                },
            },
            "cards": {},
        },
        generated_files=[
            "CustomConfig/warningdeck/GlobalValues.json",
            "CustomConfig/warningdeck/Mulligan.json",
            "CustomConfig/warningdeck/DREDGE_001.json",
        ],
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["mechanic_warning_summary"]["warning_only_mechanics"] == ["dredge"]
    assert summary["operator_guidance"]["safe_to_apply"] is True


def test_operator_summary_exposes_mechanic_visibility_without_blocking_apply():
    summary = build_operator_summary(
        deck_name="Mechanic Visibility",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed"},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        config_readiness_report={
            "summary": {
                "total_cards": 2,
                "generic_low_confidence": 0,
                "cards_needing_guide_claims": 0,
                "cards_needing_runtime_surface": 0,
                "cards_needing_mulligan_claims": 0,
                "cards_needing_combo_sequence": 0,
                "cards_needing_condition_lowering": 0,
                "cards_needing_mechanic_lowering": 0,
                "mechanic_visibility": {
                    "non_blocking": True,
                    "bucket_counts": {
                        "direct": 1,
                        "identity_gated_direct": 1,
                        "partial": 0,
                        "warning_only": 1,
                    },
                    "mechanics_by_bucket": {
                        "direct": ["battlecry"],
                        "identity_gated_direct": ["discover"],
                        "partial": [],
                        "warning_only": ["dredge"],
                    },
                    "warning_only_card_count": 1,
                    "first_warning_boundary": {
                        "mechanic": "dredge",
                        "warning_boundary": "Dredge option selection has no documented normal-path VisionAI choice surface.",
                    },
                    "warning_boundaries": [
                        {
                            "mechanic": "dredge",
                            "warning_boundary": "Dredge option selection has no documented normal-path VisionAI choice surface.",
                        }
                    ],
                },
            },
            "cards": {},
        },
        generated_files=[
            "CustomConfig/mechanicvisibility/GlobalValues.json",
            "CustomConfig/mechanicvisibility/Mulligan.json",
            "CustomConfig/mechanicvisibility/DREDGE_001.json",
        ],
    )

    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["mechanic_visibility_summary"]["non_blocking"] is True
    assert summary["mechanic_visibility_summary"]["mechanics_by_bucket"]["warning_only"] == [
        "dredge"
    ]
    assert summary["mechanic_visibility_summary"]["warning_only_mechanics"] == ["dredge"]
    assert summary["mechanic_visibility_summary"]["warning_boundaries"] == [
        {
            "mechanic": "dredge",
            "warning_boundary": "Dredge option selection has no documented normal-path VisionAI choice surface.",
        }
    ]
    assert summary["operator_guidance"]["mechanic_visibility_summary"]["warning_only_card_count"] == 1
    assert summary["operator_guidance"]["mechanic_visibility_summary"]["warning_boundaries"] == [
        {
            "mechanic": "dredge",
            "warning_boundary": "Dredge option selection has no documented normal-path VisionAI choice surface.",
        }
    ]


def test_operator_summary_exposes_static_semantic_warning_counts():
    summary = build_operator_summary(
        deck_name="deck",
        deck_code="fixture",
        technical_validation={"status": "passed"},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        semantic_enrichment_report={
            "non_blocking": True,
            "summary": {
                "total_cards": 3,
                "cards_with_warning_only_mechanics": 2,
                "deckwide_effect_count": 1,
                "warning_count": 0,
            },
        },
        config_readiness_report={
            "summary": {
                "mechanic_visibility": {
                    "non_blocking": True,
                    "bucket_counts": {
                        "direct": 2,
                        "identity_gated_direct": 1,
                        "partial": 3,
                        "warning_only": 4,
                    },
                    "mechanics_by_bucket": {
                        "direct": ["battlecry"],
                        "identity_gated_direct": ["hero_power_transform"],
                        "partial": ["deathrattle"],
                        "warning_only": ["dredge", "tradeable"],
                    },
                    "warning_only_card_count": 2,
                    "first_warning_boundary": {
                        "mechanic": "dredge",
                        "warning_boundary": "Dredge option selection has no documented normal-path VisionAI choice surface.",
                    },
                    "warning_boundaries": [],
                }
            }
        },
    )

    assert summary["runtime_apply_allowed"] is True
    assert summary["semantic_enrichment_summary"] == {
        "non_blocking": True,
        "total_cards": 3,
        "cards_with_warning_only_mechanics": 2,
        "deckwide_effect_count": 1,
        "warning_count": 0,
    }
    assert summary["mechanic_visibility_summary"]["non_blocking"] is True
    assert summary["mechanic_visibility_summary"]["bucket_counts"]["warning_only"] == 4
    assert summary["next_action"] in {
        "READY_TO_APPLY_WITH_WARNINGS",
        "READY_TO_APPLY_OR_HANDOFF",
    }


def test_operator_summary_uses_mechanic_warnings_from_summary_only_input():
    summary = build_operator_summary(
        deck_name="Summary Only",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed"},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        config_readiness_summary={
            "total_cards": 1,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
            "mechanic_support": {
                "support_level_counts": {"direct": 0, "partial": 0, "warning_only": 1},
                "warning_only_mechanics": ["future_keyword"],
                "warning_only_card_count": 1,
            },
        },
        generated_files=["CustomConfig/summaryonly/GlobalValues.json"],
    )

    assert summary["mechanic_warning_summary"]["warning_only_mechanics"] == [
        "future_keyword"
    ]
    assert summary["operator_guidance"]["mechanic_warning_summary"][
        "warning_only_card_count"
    ] == 1


def test_runtime_evidence_globalvalues_are_warnings_not_semantic_blockers():
    summary = build_operator_summary(
        deck_name="ShadowPriest",
        deck_code="deck-code",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "source_backed", "source_count": 2, "claim_count": 12},
        unsupported_conditions=[],
        globalvalue_authority={
            "blocked_until_runtime_evidence": [
                {"key": "LowHpBoardValuePenalty"},
                {"key": "EnemySecretValue"},
            ]
        },
        generated_files=[
            "CustomConfig/shadowpriest/GlobalValues.json",
            "CustomConfig/shadowpriest/Mulligan.json",
        ],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
        source_to_runtime_explainability_report=_guide_backed_profile_report(
            ["gameplan_posture", "mulligan_keep", "hero_power_transform"]
        ),
        claim_coverage_report={
            "summary": {
                "guide_backed": 2,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 0,
            },
            "uncovered_cards": [],
        },
        config_readiness_summary={
            "total_cards": 2,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        claim_conflict_report={"conflict_count": 0, "conflicts": []},
    )

    assert summary["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert summary["semantic_blockers"] == []
    assert {
        "reason": "globalvalue_runtime_evidence_required",
        "key": "LowHpBoardValuePenalty",
    } in summary["warnings"]


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
    assert summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert summary["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    assert summary["runtime_load_safe"] is True
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["runtime_apply_requires_flag"] is None
    assert any(warning["reason"] == "static_semantics_only" for warning in summary["warnings"])


def test_surface_rejection_rows_do_not_degrade_static_semantics_status():
    summary = build_operator_summary(
        deck_name="ShadowPriest",
        deck_code="deck-code",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "static_semantics_only", "source_count": 0},
        unsupported_conditions=[
            {
                "card": "SW_448",
                "action": "none",
                "reason": "claim_kind_not_mulligan_surface",
                "source_claim_ids": ["claim_static_hero_power_transform"],
            }
        ],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=[],
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "STATIC_SEMANTICS_USABLE"
    assert summary["source_informed_apply_readiness"]["status"] == "not_applicable"
    assert not any(
        blocker["reason"] == "unsupported_conditions_present"
        for blocker in summary["semantic_blockers"]
    )
    assert not any(
        warning["reason"] == "claim_kind_not_mulligan_surface"
        for warning in summary["warnings"]
    )


def test_policy_backed_mulligan_suppression_does_not_degrade_static_semantics_status():
    summary = build_operator_summary(
        deck_name="ShadowPriest",
        deck_code="deck-code",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "static_semantics_only", "source_count": 0},
        unsupported_conditions=[
            {
                "card": "SW_448",
                "reason": "excluded_non_hand_start_of_game_effect",
                "source_type": "policy_backed_autonomous_mulligan",
            }
        ],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=[],
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "STATIC_SEMANTICS_USABLE"
    assert summary["source_informed_apply_readiness"]["status"] == "not_applicable"
    assert not any(
        blocker["reason"] == "unsupported_conditions_present"
        for blocker in summary["semantic_blockers"]
    )
    assert not any(
        warning["reason"] == "excluded_non_hand_start_of_game_effect"
        for warning in summary["warnings"]
    )


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
    assert summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert summary["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    assert summary["runtime_load_safe"] is True
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True


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
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "NEEDS_MORE_RESEARCH"
    assert summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"


def test_operator_summary_marks_valid_package_not_guide_strong_when_many_cards_need_claims():
    summary = build_operator_summary(
        deck_name="Fixture",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 3},
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=["CustomConfig/fixture/GlobalValues.json"],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
        claim_coverage_report={
            "total_cards": 10,
            "guide_backed_cards": 1,
            "uncovered_cards": ["A", "B", "C"],
        },
        config_readiness_summary={"generic_low_confidence": 3},
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"


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
    assert summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert summary["source_informed_apply_readiness"]["status"] == "blocked"
    assert "claim_conflicts_present" in summary["source_informed_apply_readiness"]["blocking_reasons"]


@pytest.mark.parametrize(
    "summary_key",
    [
        "cards_needing_guide_claims",
        "cards_needing_runtime_surface",
        "cards_needing_mulligan_claims",
        "cards_needing_combo_sequence",
        "cards_needing_condition_lowering",
        "cards_needing_target_scope",
        "cards_needing_invalid_target_scope",
        "cards_needing_target_surface",
        "cards_needing_mechanic_lowering",
    ],
)
def test_operator_summary_demotes_when_readiness_gaps_remain(summary_key):
    summary = build_operator_summary(
        deck_name="Fixture",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "source_backed", "claim_count": 12},
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=["CustomConfig/fixture/GlobalValues.json"],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
        claim_coverage_report={
            "summary": {
                "guide_backed": 3,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 0,
            },
            "uncovered_cards": [],
        },
        config_readiness_summary={
            "total_cards": 3,
            "generic_low_confidence": 0,
            summary_key: 1,
        },
    )

    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert summary["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    if summary_key in {"cards_needing_guide_claims", "cards_needing_mulligan_claims"}:
        assert summary["source_informed_apply_readiness"] == {
            "status": "ready",
            "requires_flag": "--allow-source-informed",
            "runtime_gate_impact": "diagnostic_only",
            "legacy_flag_scope": "backward_compatible_only",
            "allowed_blocker_reasons": [
                "cards_need_guide_claims",
                "cards_need_mulligan_claims",
            ],
            "blocking_reasons": [],
            "source_gap_count": 1,
        }
        assert summary["runtime_apply_mode"] == "load_safe_apply"
        assert summary["runtime_apply_allowed"] is True
        assert summary["runtime_apply_requires_flag"] is None
    else:
        assert summary["source_informed_apply_readiness"]["status"] == "blocked"
        assert summary["runtime_apply_mode"] == "load_safe_apply"
        assert summary["runtime_apply_allowed"] is True
        assert summary["runtime_apply_requires_flag"] is None
    assert summary["guide_strength_summary"][summary_key] == 1


def test_target_scope_gap_prevents_strong_status_with_visible_source_action():
    summary = build_operator_summary(
        deck_name="Fixture",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 3,
            "source_evidence": {"warnings_count": 0},
        },
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=["CustomConfig/fixture/GlobalValues.json"],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
        claim_coverage_report={
            "summary": {
                "guide_backed": 3,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 0,
            },
            "uncovered_cards": [],
        },
        config_readiness_report={
            "cards": {
                "CARD_TARGET": {
                    "card_id": "CARD_TARGET",
                    "name": "Target Card",
                    "readiness_lane": "report_only_supported",
                    "first_missing_link": "needs_target_scope",
                }
            }
        },
        source_claim_gap_report={
            "summary": {
                "blocked_cards": 1,
                "first_missing_chain": {
                    "card_id": "CARD_TARGET",
                    "first_missing_link": "needs_target_scope",
                    "next_action": "add_explicit_target_scope",
                },
            }
        },
    )

    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["source_backed_status"] == "SOURCE_BACKED_PARTIAL"
    assert summary["first_missing_source_action"] == "add_explicit_target_scope"
    assert {
        "reason": "cards_need_target_scope",
        "count": 1,
        "blocking_strength": "blocks_source_backed_strong",
        "report": "reports/per_card_config_readiness_report.json",
        "affected_cards": [{"card_id": "CARD_TARGET", "name": "Target Card"}],
    } in summary["semantic_blockers"]
    assert summary["runtime_apply_allowed"] is True


def test_operator_summary_demotes_from_per_card_report_when_summary_is_omitted():
    summary = build_operator_summary(
        deck_name="Fixture",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "source_backed", "claim_count": 12},
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=["CustomConfig/fixture/GlobalValues.json"],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
        claim_coverage_report={
            "summary": {
                "guide_backed": 2,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 0,
            },
            "uncovered_cards": [],
        },
        config_readiness_report={
            "cards": {
                "CARD_A": {
                    "name": "Card A",
                    "readiness_lane": "report_only_supported",
                    "first_missing_link": "needs_runtime_surface",
                }
            }
        },
    )

    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert {
        "reason": "cards_need_runtime_surface",
        "count": 1,
        "blocking_strength": "report_visible_gap",
        "report": "reports/per_card_config_readiness_report.json",
        "affected_cards": [{"card_id": "CARD_A", "name": "Card A"}],
    } in summary["semantic_blockers"]


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
    assert summary["runtime_apply_mode"] == "blocked"
    assert summary["runtime_apply_allowed"] is False
    assert summary["runtime_apply_requires_flag"] is None
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
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["runtime_apply_requires_flag"] is None


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
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["runtime_apply_requires_flag"] is None


def test_operator_summary_explains_valid_but_not_guide_strong_with_semantic_blockers():
    summary = build_operator_summary(
        deck_name="Fixture",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "source_backed", "claim_count": 8},
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=["CustomConfig/fixture/GlobalValues.json"],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
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
        "lowerable_claims": 0,
        "report_only_claims": 0,
        "source_evidence_warnings": 0,
        "runtime_emitted_cards": 1,
        "cards_needing_guide_claims": 2,
        "cards_needing_runtime_surface": 1,
        "cards_needing_mulligan_claims": 0,
        "cards_needing_combo_sequence": 0,
        "cards_needing_condition_lowering": 0,
        "cards_needing_target_scope": 0,
        "cards_needing_invalid_target_scope": 0,
        "cards_needing_target_surface": 0,
        "cards_needing_mechanic_lowering": 0,
        "source_backed_strong_requires": [
            "technical_status=VALID_PACKAGE",
            "source_depth_status=source_backed",
            "claim_count>0",
            "source_evidence_warnings=0",
            "generic_low_confidence_cards=0",
            "uncovered_cards=0",
            "claim_conflicts=0",
            "cards_needing_guide_claims=0",
            "cards_needing_runtime_surface=0",
            "cards_needing_mulligan_claims=0",
            "cards_needing_combo_sequence=0",
            "cards_needing_condition_lowering=0",
            "cards_needing_target_scope=0",
            "cards_needing_invalid_target_scope=0",
            "cards_needing_target_surface=0",
            "cards_needing_mechanic_lowering=0",
            "positive_strong_source_quality_lane>0_when_lane_summary_present",
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
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["runtime_apply_requires_flag"] is None


def test_valid_but_not_guide_strong_is_load_safe_but_not_semantically_strong():
    summary = build_operator_summary(
        deck_name="ShadowPriest",
        deck_code="deck-code",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "source_count": 1,
            "claim_count": 1,
            "warnings": [{"reason": "cards_need_guide_claims", "count": 2}],
        },
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=["CustomConfig/shadowpriest/GlobalValues.json"],
        config_readiness_summary={
            "total_cards": 3,
            "generic_low_confidence": 1,
            "cards_needing_guide_claims": 2,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        claim_conflict_report={"conflict_count": 0, "conflicts": []},
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert summary["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    assert summary["runtime_load_safe"] is True
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["source_informed_apply_readiness"]["status"] == "blocked"
    assert summary["semantic_blockers"]


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


def test_operator_summary_uses_readiness_summary_when_per_card_report_is_omitted():
    summary = build_operator_summary(
        deck_name="Fixture",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "source_backed", "claim_count": 8},
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=[],
        claim_coverage_report={
            "summary": {
                "guide_backed": 3,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 1,
            },
            "uncovered_cards": ["CARD_A"],
        },
        config_readiness_summary={
            "total_cards": 4,
            "generic_low_confidence": 1,
            "cards_needing_guide_claims": 1,
            "cards_needing_runtime_surface": 2,
            "cards_needing_mulligan_claims": 1,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 1,
            "cards_needing_mechanic_lowering": 0,
        },
    )

    assert {
        "reason": "cards_need_guide_claims",
        "count": 1,
        "blocking_strength": "blocks_source_backed_strong",
        "report": "reports/per_card_config_readiness_report.json",
        "affected_cards": [],
    } in summary["semantic_blockers"]
    assert {
        "reason": "cards_need_runtime_surface",
        "count": 2,
        "blocking_strength": "report_visible_gap",
        "report": "reports/per_card_config_readiness_report.json",
        "affected_cards": [],
    } in summary["semantic_blockers"]
    assert {
        "reason": "cards_need_mulligan_claims",
        "count": 1,
        "blocking_strength": "report_visible_gap",
        "report": "reports/per_card_config_readiness_report.json",
        "affected_cards": [],
    } in summary["semantic_blockers"]
    assert {
        "reason": "cards_need_condition_lowering",
        "count": 1,
        "blocking_strength": "report_visible_gap",
        "report": "reports/per_card_config_readiness_report.json",
        "affected_cards": [],
    } in summary["semantic_blockers"]


def test_operator_summary_exposes_lowerable_and_report_only_claim_counts():
    summary = build_operator_summary(
        deck_name="Fixture",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 2,
            "summary": {
                "lowerable_claims": 1,
                "report_only_claims": 1,
            },
        },
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=[],
        claim_coverage_report={
            "summary": {
                "guide_backed": 1,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 1,
            },
            "uncovered_cards": ["CARD_B"],
        },
        config_readiness_summary={
            "total_cards": 2,
            "generic_low_confidence": 1,
            "cards_needing_guide_claims": 1,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        claim_conflict_report={"conflict_count": 0, "conflicts": []},
    )

    assert summary["guide_strength_summary"]["lowerable_claims"] == 1
    assert summary["guide_strength_summary"]["report_only_claims"] == 1
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["runtime_apply_requires_flag"] is None


def test_source_evidence_warnings_prevent_source_backed_strong():
    summary = build_operator_summary(
        deck_name="Deck",
        deck_code="AAEBAQ==",
        technical_validation={"status": "passed"},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "summary": {"claim_count": 3, "lowerable_claims": 3, "report_only_claims": 0},
            "source_evidence": {"warnings_count": 1},
        },
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=["CustomConfig/deck/GlobalValues.json"],
        claim_coverage_report={
            "summary": {"guide_backed": 1, "static_semantics_backfilled": 0},
            "uncovered_cards": [],
        },
        config_readiness_summary={
            "total_cards": 1,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        claim_conflict_report={"conflict_count": 0},
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
    )

    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert summary["guide_strength_summary"]["source_evidence_warnings"] == 1
    assert summary["source_informed_apply_readiness"]["status"] == "blocked"
    assert summary["source_informed_apply_readiness"]["blocking_reasons"] == [
        "source_evidence_warnings"
    ]
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["runtime_apply_requires_flag"] is None


def test_operator_summary_can_mark_source_informed_ready_for_source_depth_only_gap():
    summary = build_operator_summary(
        validation_report={"status": "passed", "errors": []},
        config_readiness_report={
            "summary": {
                "cards_needing_guide_claims": 1,
                "cards_needing_mulligan_claims": 1,
                "cards_need_runtime_surface": 0,
                "generic_low_confidence_cards": 0,
                "uncovered_cards": 0,
                "unsupported_conditions_present": 0,
                "combo_blockers": 0,
                "mechanic_blockers": 0,
            }
        },
        guide_source_depth_report={"depth_status": "source_informed"},
        source_claim_gap_report={
            "summary": {
                "blocked_cards": 2,
                "first_missing_chain": {
                    "card_id": "EXAMPLE_001",
                    "card_name": "Example Card",
                    "first_missing_link": "needs_mulligan_claim",
                    "next_action": "add_exact_mulligan_claim",
                },
            }
        },
        strong_promotion_report={"promotion_ready": False},
        generated_files=[
            "CustomConfig\\deck\\GlobalValues.json",
            "CustomConfig\\deck\\Mulligan.json",
            "CustomConfig\\deck\\EXAMPLE_001.json",
        ],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert summary["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    assert summary["source_informed_apply_readiness"]["status"] == "ready"
    assert summary["source_informed_apply_readiness"]["blocking_reasons"] == []
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["runtime_apply_requires_flag"] is None


def test_operator_summary_blocks_source_informed_ready_when_compat_summary_has_alias_hard_blockers():
    summary = build_operator_summary(
        validation_report={"status": "passed", "errors": []},
        config_readiness_report={
            "summary": {
                "cards_needing_guide_claims": 1,
                "cards_needing_mulligan_claims": 1,
                "cards_need_runtime_surface": 0,
                "generic_low_confidence_cards": 2,
                "uncovered_cards": 1,
                "unsupported_conditions_present": 1,
                "combo_blockers": 0,
                "mechanic_blockers": 0,
            }
        },
        guide_source_depth_report={"depth_status": "source_informed"},
        source_claim_gap_report={
            "summary": {
                "blocked_cards": 2,
                "first_missing_chain": {
                    "card_id": "EXAMPLE_001",
                    "card_name": "Example Card",
                    "first_missing_link": "needs_mulligan_claim",
                    "next_action": "add_exact_mulligan_claim",
                },
            }
        },
        strong_promotion_report={"promotion_ready": False},
        generated_files=[
            "CustomConfig\\deck\\GlobalValues.json",
            "CustomConfig\\deck\\Mulligan.json",
            "CustomConfig\\deck\\EXAMPLE_001.json",
        ],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert summary["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    assert summary["source_informed_apply_readiness"]["status"] == "blocked"
    assert summary["source_informed_apply_readiness"]["blocking_reasons"] == [
        "generic_low_confidence_cards",
        "uncovered_cards",
        "unsupported_conditions_present",
    ]
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["runtime_apply_requires_flag"] is None


@pytest.mark.parametrize(
    ("readiness_overrides", "expected_reason"),
    [
        ({"uncovered_cards": 1}, "uncovered_cards"),
        ({"unsupported_conditions_present": 1}, "unsupported_conditions_present"),
        (
            {"generic_low_confidence": 0, "generic_low_confidence_cards": 1},
            "generic_low_confidence_cards",
        ),
    ],
)
def test_operator_summary_blocks_source_backed_strong_when_compat_summary_has_pure_alias_hard_blockers(
    readiness_overrides, expected_reason
):
    readiness_summary = {
        "cards_needing_guide_claims": 0,
        "cards_need_runtime_surface": 0,
        "cards_needing_mulligan_claims": 0,
        "cards_need_combo_sequence": 0,
        "cards_need_condition_lowering": 0,
        "cards_need_mechanic_lowering": 0,
        "generic_low_confidence_cards": 0,
        "uncovered_cards": 0,
        "unsupported_conditions_present": 0,
    }
    readiness_summary.update(readiness_overrides)

    summary = build_operator_summary(
        validation_report={"status": "passed", "errors": []},
        config_readiness_report={"summary": readiness_summary},
        guide_source_depth_report={
            "depth_status": "source_backed",
            "summary": {"claim_count": 3},
            "source_evidence": {"warnings_count": 0},
        },
        claim_conflict_report={"conflict_count": 0},
        generated_files=[
            "CustomConfig\\deck\\GlobalValues.json",
            "CustomConfig\\deck\\Mulligan.json",
        ],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert summary["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    assert summary["operator_guidance"]["safe_to_apply"] is True
    assert expected_reason in summary["source_informed_apply_readiness"]["blocking_reasons"]
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["runtime_apply_requires_flag"] is None


def test_operator_summary_marks_mulligan_only_gap_source_informed_apply_ready():
    summary = build_operator_summary(
        deck_name="Kingslayer",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 12,
            "source_evidence": {"warnings_count": 0},
        },
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=["CustomConfig/kingslayer/GlobalValues.json"],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
        claim_coverage_report={
            "summary": {
                "guide_backed": 10,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 0,
            },
            "uncovered_cards": [],
        },
        config_readiness_summary={
            "total_cards": 10,
            "runtime_emitted": 9,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 1,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        config_readiness_report={
            "cards": {
                "DEEP_014": {
                    "name": "Quick Pick",
                    "readiness_lane": "report_only_supported",
                    "first_missing_link": "needs_mulligan_claim",
                }
            }
        },
        claim_conflict_report={"conflict_count": 0, "conflicts": []},
    )

    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert summary["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    assert summary["source_informed_apply_readiness"] == {
        "status": "ready",
        "requires_flag": "--allow-source-informed",
        "runtime_gate_impact": "diagnostic_only",
        "legacy_flag_scope": "backward_compatible_only",
        "allowed_blocker_reasons": [
            "cards_need_guide_claims",
            "cards_need_mulligan_claims",
        ],
        "blocking_reasons": [],
        "source_gap_count": 1,
    }
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["runtime_apply_requires_flag"] is None


def test_operator_summary_blocks_strong_apply_when_unsupported_conditions_are_present():
    summary = build_operator_summary(
        deck_name="Fixture",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 12,
            "source_evidence": {"warnings_count": 0},
        },
        unsupported_conditions=[{"card_id": "CARD_A", "reason": "unsupported_condition"}],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=["CustomConfig/fixture/GlobalValues.json"],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
        claim_coverage_report={
            "summary": {
                "guide_backed": 10,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 0,
            },
            "uncovered_cards": [],
        },
        config_readiness_summary={
            "total_cards": 10,
            "runtime_emitted": 10,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        claim_conflict_report={"conflict_count": 0, "conflicts": []},
    )

    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert summary["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    assert summary["source_informed_apply_readiness"]["status"] == "blocked"
    assert summary["source_informed_apply_readiness"]["blocking_reasons"] == [
        "unsupported_conditions_present"
    ]
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["runtime_apply_requires_flag"] is None


def test_operator_summary_blocks_source_informed_apply_when_uncovered_summary_is_present():
    summary = build_operator_summary(
        deck_name="Fixture",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 12,
            "source_evidence": {"warnings_count": 0},
        },
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=["CustomConfig/fixture/GlobalValues.json"],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
        claim_coverage_report={
            "summary": {
                "guide_backed": 9,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 1,
            },
            "uncovered_cards": [],
        },
        config_readiness_summary={
            "total_cards": 10,
            "runtime_emitted": 9,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 1,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        claim_conflict_report={"conflict_count": 0, "conflicts": []},
    )

    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert summary["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    assert summary["guide_strength_summary"]["uncovered_cards"] == 1
    assert summary["source_informed_apply_readiness"]["status"] == "blocked"
    assert summary["source_informed_apply_readiness"]["blocking_reasons"] == [
        "uncovered_cards"
    ]
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["runtime_apply_requires_flag"] is None


def test_operator_summary_blocks_source_informed_apply_when_runtime_surface_gap_exists():
    summary = build_operator_summary(
        deck_name="Fixture",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 12,
            "source_evidence": {"warnings_count": 0},
        },
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=["CustomConfig/fixture/GlobalValues.json"],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
        claim_coverage_report={
            "summary": {
                "guide_backed": 10,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 0,
            },
            "uncovered_cards": [],
        },
        config_readiness_summary={
            "total_cards": 10,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 1,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        config_readiness_report={
            "cards": {
                "CARD_A": {
                    "name": "Needs Runtime Surface",
                    "readiness_lane": "report_only_supported",
                    "first_missing_link": "needs_runtime_surface",
                }
            }
        },
        claim_conflict_report={"conflict_count": 0, "conflicts": []},
    )

    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert summary["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    assert summary["source_informed_apply_readiness"]["status"] == "blocked"
    assert summary["source_informed_apply_readiness"]["blocking_reasons"] == [
        "cards_need_runtime_surface"
    ]
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["runtime_apply_requires_flag"] is None


def test_operator_summary_source_backed_exposes_load_safe_runtime_apply_mode():
    summary = build_operator_summary(
        deck_name="StrongDeck",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "source_count": 1,
            "claim_count": 1,
            "source_evidence": {"warnings_count": 0},
        },
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=[
            "CustomConfig/strongdeck/GlobalValues.json",
            "CustomConfig/strongdeck/Mulligan.json",
            "CustomConfig/strongdeck/EX1_001.json",
        ],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
        claim_coverage_report={
            "summary": {
                "guide_backed": 1,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 0,
            },
            "uncovered_cards": [],
        },
        config_readiness_summary={
            "total_cards": 1,
            "runtime_emitted": 1,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        claim_conflict_report={"conflict_count": 0, "conflicts": []},
        source_to_runtime_explainability_report=_guide_backed_profile_report(
            ["gameplan_posture"]
        ),
    )

    assert summary["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert summary["next_action"] == "READY_TO_APPLY_OR_HANDOFF"
    assert summary["apply_policy"] == "ALLOWED"
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["runtime_apply_requires_flag"] is None


def test_operator_summary_includes_nonblocking_config_usefulness():
    summary = build_operator_summary(
        deck_name="UsefulDeck",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 3,
            "source_evidence": {"warnings_count": 0},
        },
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=[
            "CustomConfig/usefuldeck/GlobalValues.json",
            "CustomConfig/usefuldeck/Mulligan.json",
            "CustomConfig/usefuldeck/CARD_A.json",
        ],
        claim_coverage_report={
            "summary": {
                "guide_backed": 1,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 0,
            },
            "uncovered_cards": [],
        },
        config_readiness_summary={
            "total_cards": 1,
            "runtime_emitted": 1,
            "mulligan_only": 0,
            "globalvalues_only": 0,
            "report_only_supported": 0,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        claim_conflict_report={"conflict_count": 0, "conflicts": []},
        mulligan_plan_report={
            "rules": [{"action": "keep", "card": "CARD_A"}],
            "suppressed_rules": [],
            "quality": {"has_concrete_keeps": True},
        },
        card_behavior_plan_report={
            "rows": [
                {
                    "card_id": "CARD_A",
                    "surface_family": "CARDID.json",
                    "meaningful_runtime_surface": True,
                    "behavior_block": {"BeforePlayCardBonus": {"values": []}},
                }
            ]
        },
        combo_plan_report={"combos": [], "suppressed": []},
        globalvalues_profile_report={"changed_keys": ["FirstTurnValueWeight"]},
        source_to_runtime_explainability_report=_guide_backed_profile_report(
            ["gameplan_posture"]
        ),
    )

    assert summary["config_usefulness"]["status"] == "guide_aligned"
    assert summary["config_usefulness"]["runtime_permission_impact"] == "none"
    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True


def test_operator_summary_thin_usefulness_does_not_block_apply():
    summary = build_operator_summary(
        deck_name="ThinDeck",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        unsupported_conditions=[],
        globalvalue_authority={"blocked_until_runtime_evidence": []},
        generated_files=[
            "CustomConfig/thindeck/GlobalValues.json",
            "CustomConfig/thindeck/Mulligan.json",
        ],
        config_readiness_summary={
            "total_cards": 10,
            "runtime_emitted": 1,
            "mulligan_only": 0,
            "globalvalues_only": 0,
            "report_only_supported": 8,
            "generic_low_confidence": 1,
            "cards_needing_guide_claims": 1,
            "cards_needing_runtime_surface": 5,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        mulligan_plan_report={
            "rules": [],
            "suppressed_rules": [],
            "quality": {"has_concrete_keeps": False},
        },
        card_behavior_plan_report={"rows": []},
        combo_plan_report={"combos": [], "suppressed": []},
        globalvalues_profile_report={"changed_keys": []},
    )

    assert summary["config_usefulness"]["status"] == "load_safe_but_thin"
    assert summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert summary["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    assert summary["runtime_apply_allowed"] is True


def test_operator_summary_exposes_policy_backed_mulligan_status_without_default_only():
    summary = build_operator_summary(
        deck_name="PirateRogue",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        generated_files=[
            "CustomConfig/piraterogue/GlobalValues.json",
            "CustomConfig/piraterogue/Mulligan.json",
        ],
        mulligan_plan_report={
            "rules": [
                {
                    "card": "PIRATE",
                    "selector_kind": "card",
                    "action": "hold",
                    "source_type": "policy_backed_autonomous_mulligan",
                    "policy_lane": "aggro",
                    "policy_reason": "pirate_pressure",
                }
            ],
            "quality": {
                "status": "policy_backed",
                "has_concrete_keeps": True,
                "default_only": False,
                "policy_backed_rule_count": 1,
                "policy_backed_keep_rule_count": 1,
                "policy_lanes": ["aggro"],
                "policy_reasons": ["pirate_pressure"],
            },
        },
    )

    assert summary["mulligan_policy_status"] == {
        "status": "policy_backed",
        "default_only": False,
        "policy_lanes": ["aggro"],
        "policy_reasons": ["pirate_pressure"],
    }
    assert summary["default_only_runtime_surfaces"] == []


def test_policy_backed_package_is_load_safe_but_not_source_backed_strong():
    summary = build_operator_summary(
        deck_name="PolicyBackedDeck",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 2,
            "source_evidence": {"warnings_count": 0},
        },
        unsupported_conditions=[],
        generated_files=[
            "CustomConfig/policybackeddeck/GlobalValues.json",
            "CustomConfig/policybackeddeck/Mulligan.json",
        ],
        claim_coverage_report={
            "summary": {
                "guide_backed": 2,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 0,
            },
            "uncovered_cards": [],
        },
        config_readiness_summary={
            "total_cards": 2,
            "runtime_emitted": 1,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        claim_conflict_report={"conflict_count": 0, "conflicts": []},
        mulligan_plan_report={
            "rules": [
                {
                    "card": "PIRATE",
                    "selector_kind": "card",
                    "action": "hold",
                    "source_type": "policy_backed_autonomous_mulligan",
                }
            ],
            "quality": {
                "status": "policy_backed",
                "has_concrete_keeps": True,
                "default_only": False,
                "policy_backed_rule_count": 1,
                "policy_backed_keep_rule_count": 1,
                "policy_lanes": ["aggro"],
                "policy_reasons": ["pirate_pressure"],
            },
        },
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_allowed"] is True
    assert summary["default_only_runtime_surfaces"] == []
    assert summary["semantic_status"] != "SOURCE_BACKED_STRONG"
    assert any(
        row.get("code") == "policy_claim_not_strong_evidence"
        for row in summary.get("semantic_blockers", [])
    )


def test_operator_summary_names_default_only_mulligan_surface_when_present():
    summary = build_operator_summary(
        deck_name="ThinDeck",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        generated_files=[
            "CustomConfig/thindeck/GlobalValues.json",
            "CustomConfig/thindeck/Mulligan.json",
        ],
        mulligan_plan_report={
            "rules": [],
            "suppressed_rules": [],
            "quality": {
                "status": "thin",
                "has_concrete_keeps": False,
                "default_only": True,
                "policy_lanes": [],
                "policy_reasons": [],
            },
        },
    )

    assert summary["default_only_runtime_surfaces"] == ["mulligan"]
    assert summary["mulligan_policy_status"]["default_only"] is True


def test_default_only_surface_blocks_strong_promotion_but_not_load_safe_apply():
    summary = build_operator_summary(
        deck_name="DefaultOnlyStrongCandidate",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 2,
            "source_evidence": {"warnings_count": 0},
        },
        unsupported_conditions=[],
        generated_files=[
            "CustomConfig/defaultonlystrongcandidate/GlobalValues.json",
            "CustomConfig/defaultonlystrongcandidate/Mulligan.json",
        ],
        claim_coverage_report={
            "summary": {
                "guide_backed": 2,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 0,
            },
            "uncovered_cards": [],
        },
        config_readiness_summary={
            "total_cards": 2,
            "runtime_emitted": 1,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        claim_conflict_report={"conflict_count": 0, "conflicts": []},
        mulligan_plan_report={
            "rules": [],
            "suppressed_rules": [],
            "quality": {
                "status": "thin",
                "has_concrete_keeps": False,
                "default_only": True,
                "first_gap_reason": "no_source_backed_or_policy_backed_mulligan_keeps",
            },
        },
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_allowed"] is True
    assert summary["default_only_runtime_surfaces"] == ["mulligan"]
    assert summary["source_backed_status"] == "SOURCE_BACKED_PARTIAL"
    assert summary["source_strong_ready"] is False
    assert summary["first_missing_source_action"] == (
        "replace_default_only_runtime_surface_with_source_or_policy_claim"
    )
    assert summary["source_missing_source_actions"] == [
        "replace_default_only_runtime_surface_with_source_or_policy_claim"
    ]
    assert summary["source_status_reasons"] == ["default_only_runtime_surface"]
    assert summary["source_status_diagnostic_only"] is True
    assert summary["source_status_apply_blocking"] is False
    assert summary["semantic_status"] != "SOURCE_BACKED_STRONG"
    assert any(
        row.get("code") == "default_only_surface_not_strong_evidence"
        for row in summary.get("semantic_blockers", [])
    )


def test_missing_mulligan_report_default_only_surface_blocks_strong_promotion():
    summary = build_operator_summary(
        deck_name="MissingMulliganReport",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 2,
            "source_evidence": {"warnings_count": 0},
        },
        unsupported_conditions=[],
        generated_files=[
            "CustomConfig/missingmulliganreport/GlobalValues.json",
            "CustomConfig/missingmulliganreport/Mulligan.json",
        ],
        claim_coverage_report={
            "summary": {
                "guide_backed": 2,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 0,
            },
            "uncovered_cards": [],
        },
        config_readiness_summary={
            "total_cards": 2,
            "runtime_emitted": 1,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        claim_conflict_report={"conflict_count": 0, "conflicts": []},
        globalvalues_profile_report={
            "changed_keys": ["FirstTurnValueWeight"],
            "unchanged_keys": [],
        },
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_allowed"] is True
    assert summary["default_only_runtime_surfaces"] == ["mulligan"]
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert any(
        row.get("code") == "default_only_surface_not_strong_evidence"
        and row.get("surface") == "mulligan"
        for row in summary.get("semantic_blockers", [])
    )


def test_policy_backed_mulligan_blocks_strong_even_when_globalvalues_is_rich():
    summary = build_operator_summary(
        deck_name="MixedPolicyBackedDeck",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 2,
            "source_evidence": {"warnings_count": 0},
        },
        unsupported_conditions=[],
        generated_files=[
            "CustomConfig/mixedpolicybackeddeck/GlobalValues.json",
            "CustomConfig/mixedpolicybackeddeck/Mulligan.json",
        ],
        claim_coverage_report={
            "summary": {
                "guide_backed": 2,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 0,
            },
            "uncovered_cards": [],
        },
        config_readiness_summary={
            "total_cards": 2,
            "runtime_emitted": 1,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        claim_conflict_report={"conflict_count": 0, "conflicts": []},
        globalvalues_profile_report={
            "changed_keys": ["FirstTurnValueWeight"],
            "unchanged_keys": [],
        },
        mulligan_plan_report={
            "rules": [
                {
                    "card": "PIRATE",
                    "selector_kind": "card",
                    "action": "hold",
                    "source_type": "policy_backed_autonomous_mulligan",
                }
            ],
            "quality": {
                "status": "policy_backed",
                "has_concrete_keeps": True,
                "default_only": False,
                "policy_backed_rule_count": 1,
                "policy_backed_keep_rule_count": 1,
                "policy_lanes": ["aggro"],
                "policy_reasons": ["pirate_pressure"],
            },
        },
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_allowed"] is True
    assert summary["default_only_runtime_surfaces"] == []
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert any(
        row.get("code") == "policy_claim_not_strong_evidence"
        and row.get("surface") == "mulligan"
        for row in summary.get("semantic_blockers", [])
    )


def test_operator_summary_source_quality_lanes_block_strong_without_blocking_apply():
    summary = build_operator_summary(
        deck_name="LaneCountFixture",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 3,
            "source_evidence": {"warnings_count": 0},
        },
        unsupported_conditions=[],
        claim_coverage_report={
            "summary": {
                "guide_backed": 3,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 0,
            },
            "uncovered_cards": [],
        },
        config_readiness_summary={
            "total_cards": 3,
            "runtime_emitted": 3,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        claim_conflict_report={"conflict_count": 0, "conflicts": []},
        source_claim_gap_report={
            "summary": {
                "source_quality_lane_counts": {
                    "deck_matched_public_guide": 1,
                    "default_runtime": 1,
                    "snippet_only": 1,
                }
            }
        },
        generated_files=["CustomConfig/lanecountfixture/GlobalValues.json"],
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_allowed"] is True
    assert summary["semantic_status"] != "SOURCE_BACKED_STRONG"
    blocker_codes = {
        blocker.get("code") for blocker in summary.get("semantic_blockers", [])
    }
    assert "default_runtime_not_strong_evidence" in blocker_codes
    assert "snippet_only_source_not_strong_evidence" in blocker_codes


def test_policy_backed_lane_count_blocks_strong_without_blocking_apply():
    summary = _strong_candidate_with_lane_counts(
        {"policy_backed": 1, "guide_backed": 1}
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_allowed"] is True
    assert summary["semantic_status"] != "SOURCE_BACKED_STRONG"
    assert "policy_claim_not_strong_evidence" in _semantic_blocker_codes(summary)


def test_policy_fallback_lane_count_blocks_strong_without_blocking_apply():
    summary = _strong_candidate_with_lane_counts(
        {"policy_fallback": 1, "guide_backed": 1}
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_allowed"] is True
    assert summary["semantic_status"] != "SOURCE_BACKED_STRONG"
    assert "policy_claim_not_strong_evidence" in _semantic_blocker_codes(summary)


def test_decklist_only_lane_count_blocks_strong_without_blocking_apply():
    summary = _strong_candidate_with_lane_counts(
        {"decklist_only": 1, "guide_backed": 1}
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_allowed"] is True
    assert summary["semantic_status"] != "SOURCE_BACKED_STRONG"
    assert "decklist_only_not_strong_evidence" in _semantic_blocker_codes(summary)


def test_present_lane_summary_without_positive_strong_lane_blocks_strong():
    summary = _strong_candidate_with_lane_counts({"generic_low_confidence": 1})

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_allowed"] is True
    assert summary["semantic_status"] != "SOURCE_BACKED_STRONG"
    assert "missing_positive_strong_source_lane" in _semantic_blocker_codes(summary)


def test_empty_present_lane_summary_blocks_strong():
    summary = _strong_candidate_with_lane_counts({})

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_allowed"] is True
    assert summary["semantic_status"] != "SOURCE_BACKED_STRONG"
    assert "missing_positive_strong_source_lane" in _semantic_blocker_codes(summary)


def test_guide_backed_lane_count_without_exact_claim_receipt_cannot_promote():
    summary = _strong_candidate_with_lane_counts({"guide_backed": 1})

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_allowed"] is True
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"


def test_source_informed_blocked_readiness_is_diagnostic_only_for_load_safe_apply():
    summary = build_operator_summary(
        deck_name="DiagnosticDeck",
        deck_code="AAECAf0EAAAA",
        technical_validation={"status": "passed"},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 1,
            "source_evidence": {"warnings_count": 0},
        },
        config_readiness_summary={
            "total_cards": 1,
            "runtime_emitted": 1,
            "cards_needing_runtime_surface": 1,
        },
        config_readiness_report={
            "cards": {
                "TEST_001": {
                    "first_missing_link": "needs_runtime_surface",
                    "name": "Test Card",
                }
            },
            "summary": {
                "mechanic_support": {
                    "support_level_counts": {
                        "direct": 0,
                        "partial": 0,
                        "warning_only": 0,
                    },
                    "warning_only_mechanics": [],
                    "warning_only_card_count": 0,
                },
                "mechanic_visibility": {
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
            },
        },
        claim_coverage_report={"summary": {"guide_backed": 1}},
        generated_files=[
            "CustomConfig/DiagnosticDeck/GlobalValues.json",
            "CustomConfig/DiagnosticDeck/Mulligan.json",
        ],
    )

    readiness = summary["source_informed_apply_readiness"]
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert readiness["status"] == "blocked"
    assert readiness["runtime_gate_impact"] == "diagnostic_only"
    assert readiness["legacy_flag_scope"] == "backward_compatible_only"
    assert readiness["requires_flag"] == "--allow-source-informed"


def test_operator_summary_names_first_mechanic_drift_followup():
    summary = build_operator_summary(
        deck_name="MechanicTest",
        deck_code="AAEBAfake",
        technical_validation={"status": "passed"},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 1},
        mechanic_drift_report={
            "non_blocking": True,
            "unknown_mechanics": ["future_keyword"],
            "text_only_mechanics": ["kindred", "starship"],
            "unknown_card_types": ["lettuce_ability"],
            "summary": {
                "mechanic_count": 3,
                "unknown_mechanic_count": 1,
                "text_only_mechanic_count": 2,
                "unknown_card_type_count": 1,
            },
        },
    )

    drift = summary["mechanic_drift_summary"]
    assert drift["non_blocking"] is True
    assert drift["first_unknown_mechanic"] == "future_keyword"
    assert drift["first_text_only_mechanic"] == "kindred"
    assert drift["first_unknown_card_type"] == "lettuce_ability"
    assert drift["next_report_to_open"] == "reports/mechanic_drift_report.json"


def test_operator_summary_threads_nonblocking_mechanic_drift_summary():
    summary = build_operator_summary(
        deck_name="DriftDeck",
        deck_code="AAECAf0EAAAA",
        technical_validation={"status": "passed"},
        guide_source_depth={
            "source_depth_status": "static_semantics_only",
            "claim_count": 0,
        },
        mechanic_drift_report={
            "non_blocking": True,
            "summary": {
                "mechanic_count": 3,
                "unknown_mechanic_count": 1,
                "text_only_mechanic_count": 1,
                "unknown_card_type_count": 1,
            },
            "unknown_mechanics": ["future_keyword"],
            "text_only_mechanics": ["tradeable"],
            "unknown_card_types": ["starship"],
        },
        generated_files=[
            "CustomConfig/DriftDeck/GlobalValues.json",
            "CustomConfig/DriftDeck/Mulligan.json",
            "reports/mechanic_drift_report.json",
        ],
    )

    drift = summary["mechanic_drift_summary"]
    assert drift == {
        "non_blocking": True,
        "mechanic_count": 3,
        "unknown_mechanic_count": 1,
        "text_only_mechanic_count": 1,
        "unknown_card_type_count": 1,
        "unknown_mechanics": ["future_keyword"],
        "text_only_mechanics": ["tradeable"],
        "unknown_card_types": ["starship"],
        "first_unknown_mechanic": "future_keyword",
        "first_text_only_mechanic": "tradeable",
        "first_unknown_card_type": "starship",
        "next_report_to_open": "reports/mechanic_drift_report.json",
    }
    assert summary["runtime_apply_mode"] == "load_safe_apply"


def test_no_block_failure_mode_summary_keeps_valid_warning_package_applyable():
    summary = build_operator_summary(
        deck_name="Warning Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={
            "source_depth_status": "static_semantics_only",
            "claim_count": 0,
            "warnings": [
                {
                    "reason": "source_url_not_public_https",
                    "document_index": 1,
                }
            ],
        },
        claim_coverage_report={
            "summary": {
                "guide_backed": 1,
                "static_semantics_backfilled": 1,
                "uncovered_low_confidence": 2,
            },
            "uncovered_cards": ["CARD_A", "CARD_B"],
        },
        config_readiness_summary={
            "total_cards": 3,
            "generic_low_confidence": 2,
            "cards_needing_guide_claims": 2,
            "cards_needing_runtime_surface": 1,
            "cards_needing_mulligan_claims": 1,
            "cards_needing_combo_sequence": 1,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 1,
        },
        config_readiness_report={
            "summary": {
                "mechanic_visibility": {
                    "non_blocking": True,
                    "bucket_counts": {
                        "direct": 1,
                        "identity_gated_direct": 0,
                        "partial": 1,
                        "warning_only": 2,
                    },
                    "mechanics_by_bucket": {
                        "direct": ["battlecry"],
                        "identity_gated_direct": [],
                        "partial": ["generated_entity"],
                        "warning_only": ["dredge", "tradeable"],
                    },
                    "warning_only_card_count": 2,
                    "first_warning_boundary": {
                        "mechanic": "dredge",
                        "warning_boundary": "Dredge option selection has no documented normal-path VisionAI choice surface.",
                    },
                    "warning_boundaries": [
                        {
                            "mechanic": "dredge",
                            "warning_boundary": "Dredge option selection has no documented normal-path VisionAI choice surface.",
                        },
                        {
                            "mechanic": "tradeable",
                            "warning_boundary": "Trade-now decisions have no documented normal-path VisionAI runtime block.",
                        },
                    ],
                }
            },
            "cards": {
                "CARD_A": {
                    "name": "Card A",
                    "first_missing_link": "needs_guide_claim",
                },
                "CARD_B": {
                    "name": "Card B",
                    "first_missing_link": "needs_runtime_surface",
                },
                "CARD_C": {
                    "name": "Card C",
                    "first_missing_link": "needs_combo_sequence",
                },
            },
        },
        mechanic_drift_report={
            "non_blocking": True,
            "unknown_mechanics": ["future_keyword"],
            "text_only_mechanics": ["rewind"],
            "unknown_card_types": ["future_type"],
            "summary": {
                "mechanic_count": 2,
                "unknown_mechanic_count": 1,
                "text_only_mechanic_count": 1,
                "unknown_card_type_count": 1,
            },
        },
        combo_plan_report={
            "summary": {
                "combo_count": 0,
                "cards_needing_combo_sequence": 1,
            }
        },
        generated_files=[
            "CustomConfig/warningdeck/GlobalValues.json",
            "CustomConfig/warningdeck/Mulligan.json",
            "CustomConfig/warningdeck/CARD_A.json",
            "CustomConfig/warningdeck/CARD_B.json",
            "CustomConfig/warningdeck/CARD_C.json",
        ],
    )

    no_block = summary["no_block_failure_mode_summary"]

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert no_block["overall"] == "load_safe_apply_allowed_with_warnings"
    assert no_block["hard_block"] is False
    assert no_block["runtime_apply_allowed"] is True
    assert no_block["operator_message"] == (
        "Package is load-safe. Listed warnings explain source or mechanic limits; "
        "they do not block hsconfig apply."
    )
    assert no_block["categories"]["technical_hard_block"] == []
    assert no_block["categories"]["source_depth_warning"] == [
        {"reason": "static_semantics_only"},
        {"reason": "source_url_not_public_https", "document_index": 1},
    ]
    assert "cards_need_combo_sequence" not in {
        row["reason"] for row in no_block["categories"]["source_depth_warning"]
    }
    assert no_block["categories"]["warning_only_mechanic"] == [
        {"mechanic": "dredge"},
        {"mechanic": "tradeable"},
    ]
    assert no_block["categories"]["future_mechanic_drift"] == [
        {"kind": "unknown_mechanic", "value": "future_keyword"},
        {"kind": "text_only_mechanic", "value": "rewind"},
        {"kind": "unknown_card_type", "value": "future_type"},
    ]
    assert any(
        row["reason"] == "generic_low_confidence_cards"
        for row in no_block["categories"]["guide_strength_gap"]
    )
    source_informed_gap = next(
        row
        for row in no_block["categories"]["guide_strength_gap"]
        if row["reason"] == "source_informed_apply_gap"
    )
    assert {
        "cards_need_runtime_surface",
        "cards_need_mechanic_lowering",
    } <= set(source_informed_gap["values"])
    assert "cards_need_combo_sequence" not in source_informed_gap["values"]
    usefulness_gap = next(
        row
        for row in no_block["categories"]["guide_strength_gap"]
        if row["reason"] == "config_usefulness_gap"
    )
    assert usefulness_gap["first_usefulness_gap"] == "runtime_surface_gap"
    assert usefulness_gap["next_report_to_open"] == (
        "reports/per_card_config_readiness_report.json"
    )
    assert no_block["categories"]["combo_uncertainty"] == [
        {"reason": "cards_need_combo_sequence", "count": 1}
    ]
    assert no_block["categories"]["runtime_evidence_only_tuning"] == []
    assert no_block["first_non_blocking_followup"]["category"] == "source_depth_warning"


def test_no_block_summary_keeps_authoritative_static_source_depth_when_not_guide_strong():
    summary = build_operator_summary(
        deck_name="Static Depth Gap Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed"},
        guide_source_depth={
            "source_depth_status": "static_semantics_only",
            "claim_count": 0,
        },
        claim_coverage_report={
            "summary": {
                "guide_backed": 0,
                "static_semantics_backfilled": 0,
                "uncovered_low_confidence": 1,
            },
            "uncovered_cards": ["CARD_A"],
        },
        config_readiness_summary={
            "total_cards": 1,
            "generic_low_confidence": 1,
        },
        generated_files=[
            "CustomConfig/staticdepthgapdeck/GlobalValues.json",
            "CustomConfig/staticdepthgapdeck/Mulligan.json",
        ],
    )

    no_block = summary["no_block_failure_mode_summary"]

    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert no_block["categories"]["source_depth_warning"] == [
        {"reason": "static_semantics_only"}
    ]
    assert no_block["first_non_blocking_followup"]["category"] == "source_depth_warning"


def test_no_block_failure_mode_summary_marks_invalid_package_as_hard_block():
    summary = build_operator_summary(
        deck_name="Broken Deck",
        deck_code="bad-code",
        technical_validation={
            "status": "failed",
            "errors": ["missing_required_runtime_file"],
        },
        generated_files=[],
    )

    no_block = summary["no_block_failure_mode_summary"]

    assert summary["technical_status"] == "INVALID_PACKAGE"
    assert summary["runtime_apply_mode"] == "blocked"
    assert summary["runtime_apply_allowed"] is False
    assert no_block["overall"] == "technical_hard_block"
    assert no_block["hard_block"] is True
    assert no_block["runtime_apply_allowed"] is False
    assert no_block["categories"]["technical_hard_block"] == [
        {"reason": "missing_required_runtime_file"}
    ]
    assert all(
        no_block["categories"][category] == []
        for category in no_block["categories"]
        if category != "technical_hard_block"
    )
    assert no_block["first_non_blocking_followup"] is None
    assert no_block["operator_message"] == (
        "Package is not load-safe. Fix technical_hard_block items before hsconfig apply."
    )


def test_no_block_summary_surfaces_future_mechanic_drift_without_blocking_apply():
    summary = build_operator_summary(
        deck_name="FutureMechanicDeck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed"},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        mechanic_drift_report={
            "non_blocking": True,
            "unknown_mechanics": [],
            "text_only_mechanics": ["herald", "kindred", "rewind", "shatter", "tourist"],
            "unknown_card_types": [],
            "summary": {
                "mechanic_count": 5,
                "unknown_mechanic_count": 0,
                "text_only_mechanic_count": 5,
                "unknown_card_type_count": 0,
            },
        },
        generated_files=[
            "CustomConfig/futuremechanicdeck/GlobalValues.json",
            "CustomConfig/futuremechanicdeck/Mulligan.json",
        ],
    )

    no_block = summary["no_block_failure_mode_summary"]

    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert no_block["hard_block"] is False
    assert no_block["categories"]["future_mechanic_drift"] == [
        {"kind": "text_only_mechanic", "value": "herald"},
        {"kind": "text_only_mechanic", "value": "kindred"},
        {"kind": "text_only_mechanic", "value": "rewind"},
        {"kind": "text_only_mechanic", "value": "shatter"},
        {"kind": "text_only_mechanic", "value": "tourist"},
    ]


def test_no_block_summary_surfaces_runtime_evidence_only_tuning_without_blocking_apply():
    summary = build_operator_summary(
        deck_name="Runtime Evidence Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed"},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 1,
            "source_evidence": {"warnings_count": 0},
        },
        globalvalue_authority={
            "blocked_until_runtime_evidence": [{"key": "LowHpBoardValuePenalty"}]
        },
        generated_files=[
            "CustomConfig/runtimeevidencedeck/GlobalValues.json",
            "CustomConfig/runtimeevidencedeck/Mulligan.json",
        ],
    )

    no_block = summary["no_block_failure_mode_summary"]

    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert no_block["hard_block"] is False
    assert no_block["categories"]["runtime_evidence_only_tuning"] == [
        {
            "reason": "globalvalue_runtime_evidence_required",
            "key": "LowHpBoardValuePenalty",
        }
    ]


def test_operator_summary_exposes_source_contract_audit_without_blocking_apply():
    summary = build_operator_summary(
        deck_name="Audit Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed"},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 2,
            "source_evidence": {"warnings_count": 0},
        },
        source_contract_audit_report={
            "summary": {
                "claims_total": 2,
                "runtime_lowered_claims": 1,
                "suppressed_claims": 1,
                "runtime_evidence_required_claims": 0,
                "report_only_claims": 0,
                "cards_total": 1,
                "cards_with_missing_links": 1,
            }
        },
        generated_files=[
            "CustomConfig/auditdeck/GlobalValues.json",
            "CustomConfig/auditdeck/Mulligan.json",
        ],
    )

    audit = summary["source_contract_audit_summary"]

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert audit["non_blocking"] is True
    assert audit["runtime_lowered_claims"] == 1
    assert audit["suppressed_claims"] == 1
    assert audit["next_report_to_open"] == "reports/source_contract_audit.json"


def test_operator_summary_exposes_source_to_runtime_explainability_without_blocking_apply():
    summary = build_operator_summary(
        deck_name="Explain Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed"},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 2,
            "source_evidence": {"warnings_count": 0},
        },
        source_to_runtime_explainability_report={
            "summary": {
                "cards_total": 2,
                "claims_total": 3,
                "runtime_lowered_claims": 1,
                "claims_with_first_missing_link": 2,
                "cards_with_first_missing_link": 1,
                "next_report_to_open": "reports/source_to_runtime_explainability.json",
            }
        },
        generated_files=[
            "CustomConfig/explaindeck/GlobalValues.json",
            "CustomConfig/explaindeck/Mulligan.json",
        ],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
    )

    explainability = summary["source_to_runtime_explainability_summary"]

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert summary["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    assert explainability == {
        "non_blocking": True,
        "cards_total": 2,
        "claims_total": 3,
        "runtime_lowered_claims": 1,
        "claims_with_first_missing_link": 2,
        "cards_with_first_missing_link": 1,
        "closure_lane_counts": {},
        "cards_with_closure": 0,
        "cards_missing_closure": 0,
        "closure_schema_current": False,
        "next_report_to_open": "reports/source_to_runtime_explainability.json",
    }


def test_operator_summary_counts_closure_lanes_without_apply_authority():
    summary = build_operator_summary(
        deck_name="Closure Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed"},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 2,
            "source_evidence": {"warnings_count": 0},
        },
        source_to_runtime_explainability_report={
            "authority": "diagnostic_only",
            "operator_gate_impact": "diagnostic_only",
            "apply_blocking": False,
            "summary": {
                "cards_total": 3,
                "claims_total": 4,
                "runtime_lowered_claims": 2,
                "claims_with_first_missing_link": 1,
                "cards_with_first_missing_link": 1,
                "next_report_to_open": "reports/source_to_runtime_explainability.json",
            },
            "card_rows": [
                {
                    "card_id": "CARD_RUNTIME",
                    "name": "Runtime Card",
                    "closure": {
                        "lane": "runtime_backed",
                        "default_only_risk": False,
                    },
                },
                {
                    "card_id": "CARD_GAP",
                    "name": "Gap Card",
                    "closure": {
                        "lane": "source_action_needed",
                        "default_only_risk": False,
                    },
                },
                {
                    "card_id": "CARD_BASELINE",
                    "name": "Baseline Card",
                    "closure": {
                        "lane": "baseline_only_visible",
                        "default_only_risk": True,
                    },
                },
            ],
        },
        generated_files=[
            "CustomConfig/closuredeck/GlobalValues.json",
            "CustomConfig/closuredeck/Mulligan.json",
        ],
    )

    explainability = summary["source_to_runtime_explainability_summary"]
    closure_summary = summary["source_evidence_closure_summary"]

    assert summary["runtime_apply_allowed"] is True
    assert explainability["non_blocking"] is True
    assert explainability["closure_lane_counts"] == {
        "baseline_only_visible": 1,
        "runtime_backed": 1,
        "source_action_needed": 1,
    }
    assert explainability["cards_with_closure"] == 3
    assert explainability["cards_missing_closure"] == 0
    assert explainability["closure_schema_current"] is True
    assert closure_summary == {
        "non_blocking": True,
        "cards_total": 3,
        "lane_counts": {
            "baseline_only_visible": 1,
            "runtime_backed": 1,
            "source_action_needed": 1,
        },
        "default_only_risk_count": 1,
        "cards_with_evidence_chain": 0,
        "cards_missing_evidence_chain": 3,
        "first_missing_source_action_counts": {},
        "next_report_to_open": "reports/source_to_runtime_explainability.json",
    }


def test_operator_summary_marks_missing_closure_rows_as_non_blocking_diagnostic():
    summary = build_operator_summary(
        deck_name="Old Artifact Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed"},
        source_to_runtime_explainability_report={
            "authority": "diagnostic_only",
            "operator_gate_impact": "diagnostic_only",
            "apply_blocking": False,
            "summary": {
                "cards_total": 2,
                "claims_total": 1,
                "runtime_lowered_claims": 1,
                "claims_with_first_missing_link": 0,
                "cards_with_first_missing_link": 0,
            },
            "card_rows": [
                {"card_id": "CARD_OLD", "name": "Old Card"},
                {
                    "card_id": "CARD_RUNTIME",
                    "name": "Runtime Card",
                    "closure": {
                        "lane": "runtime_backed",
                        "default_only_risk": False,
                    },
                },
            ],
        },
        generated_files=[
            "CustomConfig/oldartifactdeck/GlobalValues.json",
            "CustomConfig/oldartifactdeck/Mulligan.json",
        ],
    )

    explainability = summary["source_to_runtime_explainability_summary"]

    assert summary["runtime_apply_allowed"] is True
    assert explainability["non_blocking"] is True
    assert explainability["cards_with_closure"] == 1
    assert explainability["cards_missing_closure"] == 1
    assert explainability["closure_schema_current"] is False
    assert explainability["next_report_to_open"] == (
        "reports/source_to_runtime_explainability.json"
    )


@pytest.mark.parametrize("malformed_counts", [None, [], "emitted"])
def test_operator_summary_ignores_malformed_source_contract_lifecycle_counts(
    malformed_counts,
):
    summary = build_operator_summary(
        deck_name="Audit Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed"},
        source_contract_audit_report={
            "summary": {
                "claim_lifecycle_decision_counts": malformed_counts,
            }
        },
    )

    assert summary["runtime_apply_allowed"] is True
    assert summary["source_contract_audit_summary"][
        "claim_lifecycle_decision_counts"
    ] == {}


def test_source_contract_policy_counts_do_not_block_valid_package():
    summary = build_operator_summary(
        deck_name="FixtureDeck",
        technical_validation={"status": "passed"},
        source_contract_audit_report={
            "summary": {
                "claims_total": 2,
                "runtime_lowered_claims": 0,
                "suppressed_claims": 1,
                "runtime_evidence_required_claims": 1,
                "report_only_claims": 0,
                "unsupported_or_unmapped_claims": 0,
                "cards_total": 1,
                "cards_with_missing_links": 1,
                "claim_kind_policy_counts": {
                    "runtime_evidence_required": 1,
                    "suppressed_or_conditional": 1,
                },
            }
        },
    )

    assert summary["technical_status"] == "VALID_PACKAGE"
    assert summary["runtime_apply_allowed"] is True
    assert summary["source_contract_audit_summary"]["non_blocking"] is True
    assert summary["next_action"] in {
        "READY_TO_APPLY_OR_HANDOFF",
        "READY_TO_APPLY_WITH_WARNINGS",
    }


def test_operator_summary_explains_default_only_surfaces_without_blocking_apply():
    summary = build_operator_summary(
        deck_name="DefaultOnlyFixture",
        deck_code="fixture",
        technical_validation={"status": "passed"},
        config_readiness_report={"summary": {}},
        mulligan_plan_report={
            "status": "default_only",
            "default_only": True,
            "policy_lanes": [],
            "policy_reasons": [],
            "quality": {
                "status": "thin",
                "has_concrete_keeps": False,
                "first_gap_reason": "no_source_backed_or_policy_backed_mulligan_keeps",
            },
        },
        source_to_runtime_explainability_report={
            "authority": "diagnostic_only",
            "operator_gate_impact": "diagnostic_only",
            "apply_blocking": False,
            "summary": {
                "cards_total": 1,
                "claims_total": 0,
                "runtime_lowered_claims": 0,
                "claims_with_first_missing_link": 0,
                "cards_with_first_missing_link": 0,
            },
            "card_rows": [
                {
                    "card_id": "CARD_001",
                    "name": "Fixture Card",
                    "closure": {
                        "lane": "baseline_only_visible",
                        "claim_kinds": [],
                        "source_lanes": [],
                        "runtime_surfaces": [],
                        "default_only_risk": True,
                        "suppressed_reasons": [],
                        "first_missing_link": None,
                        "next_source_action": "none",
                    },
                }
            ],
        },
    )

    assert summary["default_only_runtime_surfaces"] == ["mulligan"]
    assert summary["default_only_runtime_surface_details"] == [
        {
            "surface": "mulligan",
            "status": "default_only",
            "card_count_with_default_only_risk": 0,
            "example_cards": [],
            "example_card_details": [],
            "first_missing_link": "no_source_backed_or_policy_backed_mulligan_keeps",
            "next_source_action": "source_backed_or_policy_backed_mulligan_keeps",
            "operator_impact": "diagnostic_only",
            "apply_blocking": False,
        }
    ]
    assert summary["runtime_apply_contract"]["apply_authority"] == (
        "reports/operator_summary.json"
    )
    assert summary["runtime_apply_allowed"] is True
    assert summary["no_default_only_verdict"]["blocking"] is False


def test_operator_summary_exposes_strong_closure_without_apply_gate_change():
    summary = build_operator_summary(
        deck_name="ShadowPriest",
        deck_code="AAEBA-test",
        technical_validation={"status": "passed"},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 3,
            "source_evidence": {"warnings_count": 0},
        },
        generated_files=["Mulligan.json", "GlobalValues.json"],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
        source_to_runtime_explainability_report={
            "summary": {"cards_with_first_missing_link": 0},
            "claim_lifecycle_rows": [
                {
                    "claim_kind": "gameplan_posture",
                    "promotion_eligible": True,
                    "source_lane": "deck_matched_public_guide",
                    "strategic_receipt_verified": True,
                },
                {
                    "claim_kind": "mulligan_keep",
                    "promotion_eligible": True,
                    "source_lane": "deck_matched_public_guide",
                    "strategic_receipt_verified": True,
                },
                {
                    "claim_kind": "hero_power_transform",
                    "promotion_eligible": True,
                    "source_lane": "deck_matched_public_guide",
                },
            ],
            "card_rows": [],
        },
        strong_promotion_report={
            "promotion_ready": True,
            "first_missing_source_action": "none",
        },
    )

    assert summary["runtime_apply_contract"]["apply_authority"] == (
        "reports/operator_summary.json"
    )
    assert summary["source_backed_strong_closure"] == {
        "status": "ready",
        "promotion_ready": True,
        "first_missing_source_action": "none",
        "diagnostic_only": True,
        "default_only_runtime_surfaces": [],
        "closure_profile": "aggro_burn_hero_power",
        "closure_profile_closed": True,
        "closure_profile_first_missing_link": "none",
        "closure_profile_missing_claim_groups": [],
        "closure_profile_missing_surfaces": [],
        "closure_profile_apply_blocking": False,
        "strong_closure_diagnostics": [],
    }
    assert summary["source_backed_status"] == "SOURCE_BACKED_STRONG"
    assert summary["source_strong_ready"] is True
    assert summary["first_missing_source_action"] == "none"
    assert summary["source_missing_source_actions"] == []
    assert summary["source_status_reasons"] == ["source_backed_strong_ready"]
    assert summary["source_status_diagnostic_only"] is True
    assert summary["source_status_apply_blocking"] is False
    assert summary["no_default_only_runtime_status"] == "clean"
    assert summary["runtime_apply_allowed"] is True


def test_operator_summary_profile_miss_stays_non_apply_blocking():
    summary = build_operator_summary(
        deck_name="ShadowPriest",
        deck_code="AAEBA-test",
        technical_validation={"status": "passed"},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 2,
            "source_evidence": {"warnings_count": 0},
        },
        generated_files=["GlobalValues.json", "Mulligan.json"],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
        source_to_runtime_explainability_report={
            "summary": {"cards_with_first_missing_link": 0},
            "claim_lifecycle_rows": [
                {
                    "claim_kind": "gameplan_posture",
                    "promotion_eligible": True,
                    "source_lane": "deck_matched_public_guide",
                    "strategic_receipt_verified": True,
                },
                {
                    "claim_kind": "mulligan_keep",
                    "promotion_eligible": True,
                    "source_lane": "deck_matched_public_guide",
                    "strategic_receipt_verified": True,
                },
            ],
            "card_rows": [],
        },
    )

    closure = summary["source_backed_strong_closure"]
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert closure["closure_profile"] == "aggro_burn_hero_power"
    assert closure["closure_profile_closed"] is False
    assert closure["closure_profile_first_missing_link"] == (
        "missing_claim_group:targeting_rule|hero_power_transform|card_role"
    )
    assert closure["closure_profile_missing_claim_groups"] == [
        "targeting_rule|hero_power_transform|card_role"
    ]
    assert closure["closure_profile_missing_surfaces"] == []
    assert closure["closure_profile_apply_blocking"] is False
    assert summary["source_backed_status"] == "SOURCE_BACKED_PARTIAL"
    assert summary["source_strong_ready"] is False
    assert summary["first_missing_source_action"] == "add_profile_claim_group_source"
    assert summary["source_missing_source_actions"] == [
        "add_profile_claim_group_source"
    ]
    assert summary["source_status_reasons"] == ["closure_profile_not_closed"]
    assert summary["source_status_diagnostic_only"] is True
    assert summary["source_status_apply_blocking"] is False
    assert summary["runtime_apply_allowed"] is True


def _source_backed_profile_summary(rows, *, gameplan_contract=None):
    return build_operator_summary(
        deck_name="Neutral Deck",
        deck_code="AAEBA-test",
        technical_validation={"status": "passed"},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": len(rows),
            "source_evidence": {"warnings_count": 0},
        },
        generated_files=["GlobalValues.json", "Mulligan.json"],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
        source_to_runtime_explainability_report={
            "summary": {"cards_with_first_missing_link": 0},
            "claim_lifecycle_rows": rows,
            "card_rows": [],
        },
        gameplan_contract=gameplan_contract,
    )


def _profile_claim_rows(*, source_lane=None, promotion_eligible=None):
    row = {}
    if source_lane is not None:
        row["source_lane"] = source_lane
    if promotion_eligible is not None:
        row["promotion_eligible"] = promotion_eligible
    if source_lane == "deck_matched_public_guide":
        row["strategic_receipt_verified"] = True
    return [
        {"claim_kind": "gameplan_posture", **row},
        {"claim_kind": "mulligan_keep", **row},
        {"claim_kind": "hero_power_transform", **row},
    ]


@pytest.mark.parametrize(
    "source_lane",
    [
        "stats",
        "unsupported_runtime_hint",
        "decklist_only",
        "snippet_only",
        "policy_fallback",
        "policy_backed",
        "default_runtime",
        "archetype_inferred",
        "explicit_low_confidence",
        "generic_low_confidence",
        "contract_gap",
    ],
)
def test_operator_summary_prohibited_lane_with_promotion_flag_cannot_close_profile(
    source_lane,
):
    summary = _source_backed_profile_summary(
        _profile_claim_rows(source_lane=source_lane, promotion_eligible=True)
    )

    closure = summary["source_backed_strong_closure"]
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert closure["closure_profile_closed"] is False
    assert closure["closure_profile_first_missing_link"].startswith(
        "missing_claim_group:"
    )
    assert closure["closure_profile_missing_claim_groups"]
    assert summary["runtime_apply_allowed"] is True


def test_operator_summary_bare_promotion_flag_cannot_close_profile():
    summary = _source_backed_profile_summary(
        _profile_claim_rows(promotion_eligible=True)
    )

    closure = summary["source_backed_strong_closure"]
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert closure["closure_profile_closed"] is False
    assert closure["promotion_ready"] is False
    assert summary["runtime_apply_allowed"] is True


def test_operator_summary_card_rows_fallback_without_source_provenance_cannot_promote():
    summary = build_operator_summary(
        deck_name="ShadowPriest",
        deck_code="AAEBA-test",
        technical_validation={"status": "passed"},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 3,
            "source_evidence": {"warnings_count": 0},
        },
        generated_files=["GlobalValues.json", "Mulligan.json"],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
        source_to_runtime_explainability_report={
            "summary": {"cards_with_first_missing_link": 0},
            "claim_lifecycle_rows": [],
            "card_rows": [
                {
                    "card_id": "CARD_ONLY",
                    "closure": {
                        "promotion_eligible": True,
                        "claim_kinds": [
                            "gameplan_posture",
                            "mulligan_keep",
                            "hero_power_transform",
                        ],
                    },
                }
            ],
        },
    )

    closure = summary["source_backed_strong_closure"]
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert closure["closure_profile_closed"] is False
    assert summary["runtime_apply_allowed"] is True


def test_operator_summary_missing_claim_evidence_fails_closed_for_strong_confidence():
    summary = build_operator_summary(
        deck_name="No Evidence Deck",
        deck_code="AAEBA-test",
        technical_validation={"status": "passed"},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 3,
            "source_evidence": {"warnings_count": 0},
        },
        generated_files=["GlobalValues.json", "Mulligan.json"],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
        source_to_runtime_explainability_report={
            "summary": {"cards_with_first_missing_link": 0},
            "claim_lifecycle_rows": [],
            "card_rows": [],
        },
    )

    closure = summary["source_backed_strong_closure"]
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert closure["closure_profile_closed"] is False
    assert closure["promotion_ready"] is False
    assert closure["status"] == "needs_source_closure"
    assert summary["runtime_apply_allowed"] is True


def test_operator_summary_allowed_strong_lane_closes_profile_without_promotion_flag():
    summary = _source_backed_profile_summary(
        _profile_claim_rows(source_lane="deck_matched_public_guide")
    )

    closure = summary["source_backed_strong_closure"]
    assert summary["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert closure["closure_profile_closed"] is True
    assert closure["promotion_ready"] is True
    assert summary["runtime_apply_allowed"] is True


def test_static_combo_lane_cannot_satisfy_strong_closure():
    rows = [
        {
            "claim_id": "guide-gameplan",
            "claim_kind": "gameplan_posture",
            "source_lane": "deck_matched_public_guide",
            "strategic_receipt_verified": True,
        },
        {
            "claim_id": "combo-static-bypass",
            "claim_kind": "combo_sequence",
            "source_lane": "source_backed_static_semantics",
            "strategic_receipt_verified": False,
        },
        {
            "claim_id": "guide-mulligan",
            "claim_kind": "mulligan_keep",
            "source_lane": "deck_matched_public_guide",
            "strategic_receipt_verified": True,
        },
    ]

    summary = _source_backed_profile_summary(
        rows,
        gameplan_contract={"archetype": "combo_setup", "primary_mechanics": ["combo"]},
    )

    closure = summary["source_backed_strong_closure"]
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert closure["closure_profile_closed"] is False
    assert closure["closure_profile_first_missing_link"] == (
        "missing_claim_group:combo_sequence|card_role"
    )
    assert closure["strong_closure_diagnostics"] == [
        {
            "claim_id": "combo-static-bypass",
            "reason": "strong_closure_claim_not_eligible",
        }
    ]


@pytest.mark.parametrize("confidence_key", ["source_confidence", "claim_confidence"])
def test_operator_summary_low_confidence_blocks_guide_backed_profile_closure(
    confidence_key,
):
    rows = [
        {
            "claim_kind": "gameplan_posture",
            "source_lane": "guide_backed",
            confidence_key: "low",
        },
        {
            "claim_kind": "mulligan_keep",
            "source_lane": "guide_backed",
            confidence_key: "low",
        },
        {
            "claim_kind": "hero_power_transform",
            "source_lane": "guide_backed",
            confidence_key: "low",
        },
    ]

    summary = _source_backed_profile_summary(rows)

    closure = summary["source_backed_strong_closure"]
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert closure["closure_profile_closed"] is False
    assert closure["promotion_ready"] is False
    assert summary["runtime_apply_allowed"] is True


def test_operator_summary_card_rows_policy_lane_only_cannot_close_profile():
    summary = build_operator_summary(
        deck_name="ShadowPriest",
        deck_code="AAEBA-test",
        technical_validation={"status": "passed"},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 3,
            "source_evidence": {"warnings_count": 0},
        },
        generated_files=["GlobalValues.json", "Mulligan.json"],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
        source_to_runtime_explainability_report={
            "summary": {"cards_with_first_missing_link": 0},
            "claim_lifecycle_rows": [],
            "card_rows": [
                {
                    "card_id": "CARD_ONLY",
                    "closure": {
                        "policy_lane": "guide_backed",
                        "claim_kinds": [
                            "gameplan_posture",
                            "mulligan_keep",
                            "hero_power_transform",
                        ],
                    },
                }
            ],
        },
    )

    closure = summary["source_backed_strong_closure"]
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert closure["closure_profile_closed"] is False
    assert summary["runtime_apply_allowed"] is True


@pytest.mark.parametrize("confidence_key", ["source_confidence", "claim_confidence"])
def test_operator_summary_card_rows_low_confidence_source_lane_cannot_close_profile(
    confidence_key,
):
    summary = build_operator_summary(
        deck_name="ShadowPriest",
        deck_code="AAEBA-test",
        technical_validation={"status": "passed"},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 3,
            "source_evidence": {"warnings_count": 0},
        },
        generated_files=["GlobalValues.json", "Mulligan.json"],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
        source_to_runtime_explainability_report={
            "summary": {"cards_with_first_missing_link": 0},
            "claim_lifecycle_rows": [],
            "card_rows": [
                {
                    "card_id": "CARD_ONLY",
                    "closure": {
                        "source_lane": "deck_matched_public_guide",
                        "strategic_receipt_verified": True,
                        confidence_key: "low",
                        "claim_kinds": [
                            "gameplan_posture",
                            "mulligan_keep",
                            "hero_power_transform",
                        ],
                    },
                }
            ],
        },
    )

    closure = summary["source_backed_strong_closure"]
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert closure["closure_profile_closed"] is False
    assert summary["runtime_apply_allowed"] is True


def test_operator_summary_card_rows_explicit_source_lane_can_close_profile():
    summary = build_operator_summary(
        deck_name="ShadowPriest",
        deck_code="AAEBA-test",
        technical_validation={"status": "passed"},
        guide_source_depth={
            "source_depth_status": "source_backed",
            "claim_count": 3,
            "source_evidence": {"warnings_count": 0},
        },
        generated_files=["GlobalValues.json", "Mulligan.json"],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
        source_to_runtime_explainability_report={
            "summary": {"cards_with_first_missing_link": 0},
            "claim_lifecycle_rows": [],
            "card_rows": [
                {
                    "card_id": "CARD_ONLY",
                    "closure": {
                        "source_lane": "deck_matched_public_guide",
                        "strategic_receipt_verified": True,
                        "claim_kinds": [
                            "gameplan_posture",
                            "mulligan_keep",
                            "hero_power_transform",
                        ],
                    },
                }
            ],
        },
    )

    closure = summary["source_backed_strong_closure"]
    assert summary["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert closure["closure_profile_closed"] is True
    assert summary["runtime_apply_allowed"] is True


def test_operator_summary_strong_report_ready_is_reconciled_with_profile_miss():
    summary = build_operator_summary(
        deck_name="ShadowPriest",
        deck_code="AAEBA-test",
        technical_validation={"status": "passed"},
        generated_files=["GlobalValues.json", "Mulligan.json"],
        mulligan_plan_report=_source_backed_mulligan_plan_report(),
        source_to_runtime_explainability_report={
            "summary": {"cards_with_first_missing_link": 0},
            "claim_lifecycle_rows": [
                {
                    "claim_kind": "gameplan_posture",
                    "promotion_eligible": True,
                    "source_lane": "guide_backed",
                },
                {
                    "claim_kind": "mulligan_keep",
                    "promotion_eligible": True,
                    "source_lane": "guide_backed",
                },
            ],
            "card_rows": [],
        },
        strong_promotion_report={
            "promotion_ready": True,
            "first_missing_source_action": "none",
        },
    )

    closure = summary["source_backed_strong_closure"]
    assert closure["closure_profile_closed"] is False
    assert closure["promotion_ready"] is False
    assert closure["status"] == "needs_source_closure"
    assert summary["runtime_apply_allowed"] is True


@pytest.mark.parametrize(
    ("gameplan_contract", "claim_kinds", "expected_profile"),
    [
        (
            {
                "archetype_bucket": "weapon_sequence_pressure",
                "primary_mechanics": ["weapon"],
            },
            ["gameplan_posture", "mulligan_keep", "targeting_rule"],
            "weapon_pressure",
        ),
        (
            {"archetype": "combo_setup", "primary_mechanics": ["combo"]},
            ["gameplan_posture", "combo_sequence", "mulligan_keep"],
            "combo_setup",
        ),
        (
            {
                "archetype_bucket": "board_flood_recruit",
                "cards": {
                    "CARD_A": {"mechanics": ["recruit"]},
                },
            },
            ["gameplan_posture", "mulligan_keep", "mechanic_usage"],
            "board_flood_recruit",
        ),
    ],
)
def test_operator_summary_uses_gameplan_contract_for_profile_selection(
    gameplan_contract, claim_kinds, expected_profile
):
    rows = [
        {
            "claim_kind": claim_kind,
            "promotion_eligible": True,
            "source_lane": "deck_matched_public_guide",
            "strategic_receipt_verified": True,
        }
        for claim_kind in claim_kinds
    ]

    summary = _source_backed_profile_summary(
        rows,
        gameplan_contract=gameplan_contract,
    )

    closure = summary["source_backed_strong_closure"]
    assert closure["closure_profile"] == expected_profile
    assert closure["closure_profile_closed"] is True


def test_operator_summary_no_default_only_verdict_none_detected():
    summary = build_operator_summary(
        deck_name="Clean Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        mulligan_plan_report={
            "rules": [
                {
                    "card": "CARD_A",
                    "selector_kind": "card",
                    "action": "hold",
                    "source_type": "policy_backed_autonomous_mulligan",
                }
            ],
            "quality": {
                "status": "policy_backed",
                "has_concrete_keeps": True,
                "policy_backed_rule_count": 1,
                "policy_backed_keep_rule_count": 1,
            },
        },
        card_behavior_plan_report={"rows": []},
        combo_plan_report={"combos": [], "suppressed": []},
        globalvalues_profile_report={
            "changed_keys": ["FirstTurnValueWeight"],
            "unchanged_keys": [],
        },
        generated_files=[
            "CustomConfig/cleandeck/GlobalValues.json",
            "CustomConfig/cleandeck/Mulligan.json",
        ],
    )

    assert summary["runtime_apply_allowed"] is True
    assert summary["default_only_runtime_surfaces"] == []
    assert summary["no_default_only_verdict"] == {
        "status": "none_detected",
        "default_only_runtime_surface_count": 0,
        "runtime_permission_impact": "none",
        "blocking": False,
        "next_report_to_open": "reports/operator_summary.json",
    }


def test_operator_summary_no_default_only_verdict_visible_warning():
    summary = build_operator_summary(
        deck_name="Thin Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        config_readiness_summary={
            "total_cards": 3,
            "runtime_emitted": 1,
            "report_only_supported": 1,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        mulligan_plan_report={
            "rules": [],
            "suppressed_rules": [],
            "quality": {
                "status": "thin",
                "has_concrete_keeps": False,
                "first_gap_reason": "no_source_backed_or_policy_backed_mulligan_keeps",
            },
        },
        card_behavior_plan_report={
            "rows": [
                {
                    "card_id": "CARD_A",
                    "meaningful_runtime_surface": True,
                    "behavior_block": {"BeforePlayCardBonus": {"values": []}},
                }
            ]
        },
        combo_plan_report={"combos": [], "suppressed": []},
        globalvalues_profile_report={"changed_keys": ["FirstTurnValueWeight"]},
        generated_files=[
            "CustomConfig/thindeck/GlobalValues.json",
            "CustomConfig/thindeck/Mulligan.json",
            "CustomConfig/thindeck/CARD_A.json",
        ],
    )

    assert summary["runtime_apply_allowed"] is True
    assert summary["default_only_runtime_surfaces"] == ["mulligan"]
    assert summary["no_default_only_runtime_status"] == "has_default_only_surfaces"
    assert summary["no_default_only_verdict"] == {
        "status": "visible_warning",
        "default_only_runtime_surface_count": 1,
        "runtime_permission_impact": "none",
        "blocking": False,
        "next_report_to_open": "reports/operator_summary.json",
    }


def test_operator_summary_no_default_only_verdict_not_applicable_for_invalid_package():
    summary = build_operator_summary(
        deck_name="Invalid Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "failed", "errors": ["bad json"]},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        generated_files=[],
    )

    assert summary["runtime_apply_allowed"] is False
    assert summary["no_default_only_verdict"] == {
        "status": "not_applicable",
        "default_only_runtime_surface_count": 0,
        "runtime_permission_impact": "none",
        "blocking": False,
        "next_report_to_open": "reports/validation_report.json",
    }


def test_operator_summary_surface_status_ledger_marks_policy_backed_mulligan():
    summary = build_operator_summary(
        deck_name="PirateRogue",
        deck_code="AAE=",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        generated_files=[
            "CustomConfig/piraterogue/GlobalValues.json",
            "CustomConfig/piraterogue/Mulligan.json",
        ],
        mulligan_plan_report={
            "rules": [
                {
                    "card": "PIRATE",
                    "selector_kind": "card",
                    "action": "hold",
                    "source_type": "policy_backed_autonomous_mulligan",
                    "policy_lane": "aggro",
                    "policy_reason": "pirate_pressure",
                }
            ],
            "quality": {
                "status": "policy_backed",
                "has_concrete_keeps": True,
                "default_only": False,
                "policy_backed_rule_count": 1,
                "policy_backed_keep_rule_count": 1,
                "policy_lanes": ["aggro"],
                "policy_reasons": ["pirate_pressure"],
            },
        },
    )

    rows = {row["surface"]: row for row in summary["surface_status_ledger"]}
    assert rows["mulligan"] == {
        "surface": "mulligan",
        "status": "policy_backed",
        "default_only": False,
        "apply_blocking": False,
        "operator_impact": "diagnostic_only",
        "runtime_permission_impact": "none",
        "first_missing_link": "none",
        "next_source_action": "none",
        "next_report_to_open": "reports/operator_summary.json",
    }


def test_operator_summary_surface_status_ledger_marks_default_only_mulligan():
    summary = build_operator_summary(
        deck_name="DefaultOnlyFixture",
        deck_code="fixture",
        technical_validation={"status": "passed"},
        mulligan_plan_report={
            "rules": [],
            "suppressed_rules": [],
            "quality": {
                "status": "thin",
                "has_concrete_keeps": False,
                "first_gap_reason": "no_source_backed_or_policy_backed_mulligan_keeps",
            },
        },
        source_to_runtime_explainability_report={
            "authority": "diagnostic_only",
            "operator_gate_impact": "diagnostic_only",
            "apply_blocking": False,
            "card_rows": [
                {
                    "card_id": "CARD_001",
                    "name": "Fixture Card",
                    "closure": {
                        "lane": "baseline_only_visible",
                        "default_only_risk": True,
                        "first_missing_link": "needs_source_claim",
                        "next_source_action": "add_mulligan_keep_or_discard_claim",
                    },
                }
            ],
        },
    )

    rows = {row["surface"]: row for row in summary["surface_status_ledger"]}
    assert rows["mulligan"] == {
        "surface": "mulligan",
        "status": "default_only",
        "default_only": True,
        "apply_blocking": False,
        "operator_impact": "diagnostic_only",
        "runtime_permission_impact": "none",
        "first_missing_link": "no_source_backed_or_policy_backed_mulligan_keeps",
        "next_source_action": "source_backed_or_policy_backed_mulligan_keeps",
        "next_report_to_open": "reports/operator_summary.json",
    }
    assert summary["runtime_apply_allowed"] is True


def test_operator_summary_surface_status_ledger_is_empty_for_invalid_package():
    summary = build_operator_summary(
        deck_name="Invalid Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "failed", "errors": ["bad json"]},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        generated_files=[],
    )

    assert summary["surface_status_ledger"] == []
    assert summary["runtime_apply_allowed"] is False


def test_default_only_surface_details_ignore_risky_card_without_surface_intent():
    summary = build_operator_summary(
        deck_name="Thin Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed", "errors": []},
        guide_source_depth={"source_depth_status": "static_semantics_only", "claim_count": 0},
        mulligan_plan_report={
            "rules": [],
            "suppressed_rules": [],
            "quality": {
                "status": "thin",
                "has_concrete_keeps": False,
                "first_gap_reason": "no_source_backed_or_policy_backed_mulligan_keeps",
            },
        },
        card_behavior_plan_report={
            "rows": [
                {
                    "card_id": "CARD_A",
                    "meaningful_runtime_surface": True,
                    "behavior_block": {"BeforePlayCardBonus": {"values": []}},
                }
            ]
        },
        combo_plan_report={"combos": [], "suppressed": []},
        globalvalues_profile_report={"changed_keys": ["FirstTurnValueWeight"]},
        source_to_runtime_explainability_report={
            "card_rows": [
                {
                    "card_id": "CARD_MISSING",
                    "name": "Missing Keep",
                    "closure": {
                        "lane": "baseline_only_visible",
                        "default_only_risk": True,
                        "first_missing_link": None,
                        "next_source_action": "none",
                    },
                }
            ]
        },
    )

    assert summary["default_only_runtime_surface_details"] == [
        {
            "surface": "mulligan",
            "status": "default_only",
            "card_count_with_default_only_risk": 0,
            "example_cards": [],
            "example_card_details": [],
            "first_missing_link": "no_source_backed_or_policy_backed_mulligan_keeps",
            "next_source_action": "source_backed_or_policy_backed_mulligan_keeps",
            "operator_impact": "diagnostic_only",
            "apply_blocking": False,
        }
    ]
    assert summary["runtime_apply_allowed"] is True
    assert summary["no_default_only_verdict"]["blocking"] is False


def test_default_only_surface_details_filter_example_cards_to_runtime_surface():
    summary = build_operator_summary(
        deck_name="Thin Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed", "errors": []},
        mulligan_plan_report={
            "rules": [],
            "suppressed_rules": [],
            "quality": {
                "status": "thin",
                "has_concrete_keeps": False,
                "first_gap_reason": "no_source_backed_or_policy_backed_mulligan_keeps",
            },
        },
        source_to_runtime_explainability_report={
            "card_rows": [
                {
                    "card_id": "MULL_001",
                    "name": "Mulligan Missing Card",
                    "closure": {
                        "lane": "baseline_only_visible",
                        "runtime_surfaces": ["Mulligan.json"],
                        "default_only_risk": True,
                        "first_missing_link": "needs_mulligan_claim",
                        "next_source_action": "add_mulligan_keep_or_discard_claim",
                    },
                },
                {
                    "card_id": "CARDID_001",
                    "name": "CardID Missing Card",
                    "closure": {
                        "lane": "baseline_only_visible",
                        "runtime_surfaces": ["CARDID_001.json"],
                        "default_only_risk": True,
                        "first_missing_link": "needs_runtime_surface",
                        "next_source_action": "add_cardid_behavior_claim",
                    },
                },
            ]
        },
    )

    assert summary["default_only_runtime_surface_details"] == [
        {
            "surface": "mulligan",
            "status": "default_only",
            "card_count_with_default_only_risk": 1,
            "example_cards": ["MULL_001 Mulligan Missing Card"],
            "example_card_details": [
                {
                    "card_id": "MULL_001",
                    "name": "Mulligan Missing Card",
                    "closure_lane": "baseline_only_visible",
                    "first_missing_link": "needs_mulligan_claim",
                    "next_source_action": "add_mulligan_keep_or_discard_claim",
                }
            ],
            "first_missing_link": "no_source_backed_or_policy_backed_mulligan_keeps",
            "next_source_action": "source_backed_or_policy_backed_mulligan_keeps",
            "operator_impact": "diagnostic_only",
            "apply_blocking": False,
        }
    ]


def test_surface_status_ledger_uses_surface_specific_default_only_details():
    summary = build_operator_summary(
        deck_name="Thin Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed", "errors": []},
        config_readiness_summary={
            "runtime_emitted": 0,
            "report_only_supported": 0,
            "cards_needing_runtime_surface": 1,
        },
        mulligan_plan_report={
            "rules": [],
            "suppressed_rules": [],
            "quality": {
                "status": "thin",
                "has_concrete_keeps": False,
                "first_gap_reason": "no_source_backed_or_policy_backed_mulligan_keeps",
            },
        },
        card_behavior_plan_report={"rows": []},
        source_to_runtime_explainability_report={
            "card_rows": [
                {
                    "card_id": "AAA_MULL",
                    "name": "Mulligan Missing Card",
                    "closure": {
                        "lane": "baseline_only_visible",
                        "runtime_surfaces": ["Mulligan.json"],
                        "default_only_risk": True,
                        "first_missing_link": "needs_mulligan_claim",
                        "next_source_action": "add_mulligan_keep_or_discard_claim",
                    },
                },
                {
                    "card_id": "ZZZ_CARDID",
                    "name": "CardID Missing Card",
                    "closure": {
                        "lane": "baseline_only_visible",
                        "runtime_surfaces": ["ZZZ_CARDID.json"],
                        "default_only_risk": True,
                        "first_missing_link": "needs_runtime_surface",
                        "next_source_action": "add_cardid_behavior_claim",
                    },
                },
            ]
        },
    )

    rows = {row["surface"]: row for row in summary["surface_status_ledger"]}

    assert rows["mulligan"]["first_missing_link"] == (
        "no_source_backed_or_policy_backed_mulligan_keeps"
    )
    assert rows["cardid_behavior"]["first_missing_link"] == "needs_runtime_surface"
    assert rows["cardid_behavior"]["next_source_action"] == "add_cardid_behavior_claim"


def test_default_only_surface_details_do_not_assign_producer_unassigned_rows():
    explainability_report = build_source_to_runtime_explainability_report(
        {
            "schema_version": 1,
            "deck_name": "Thin Deck",
            "claim_rows": {},
            "claim_lifecycle_rows": [],
            "card_rows": {
                "BASE_001": {
                    "name": "Unassigned Baseline Card",
                    "readiness_lane": "generic_low_confidence",
                    "first_missing_link": "none",
                    "runtime_surfaces": [],
                    "claim_lanes": {},
                }
            },
        }
    )

    closure = explainability_report["card_rows"][0]["closure"]
    assert closure["default_only_risk"] is True
    assert closure["expected_runtime_surfaces"] == []
    assert closure["missing_runtime_surfaces"] == []

    summary = build_operator_summary(
        deck_name="Thin Deck",
        deck_code="AAEBAQAAAA==",
        technical_validation={"status": "passed", "errors": []},
        mulligan_plan_report={
            "rules": [],
            "suppressed_rules": [],
            "quality": {
                "status": "thin",
                "has_concrete_keeps": False,
                "first_gap_reason": "no_source_backed_or_policy_backed_mulligan_keeps",
            },
        },
        source_to_runtime_explainability_report=explainability_report,
    )

    assert summary["default_only_runtime_surfaces"] == ["mulligan"]
    assert summary["default_only_runtime_surface_details"] == [
        {
            "surface": "mulligan",
            "status": "default_only",
            "card_count_with_default_only_risk": 0,
            "example_cards": [],
            "example_card_details": [],
            "first_missing_link": "no_source_backed_or_policy_backed_mulligan_keeps",
            "next_source_action": "source_backed_or_policy_backed_mulligan_keeps",
            "operator_impact": "diagnostic_only",
            "apply_blocking": False,
        }
    ]
