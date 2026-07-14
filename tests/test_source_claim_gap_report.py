from hsconfig.source_claim_gap_report import build_source_claim_gap_report
from hsconfig.source_claim_lifecycle import build_initial_lifecycle_rows
from hsconfig.source_contract_audit import build_source_contract_audit


def test_report_explains_each_first_missing_link():
    report = build_source_claim_gap_report(
        deck_name="Example",
        config_readiness_report={
            "summary": {
                "total_cards": 3,
                "cards_needing_guide_claims": 1,
                "cards_needing_runtime_surface": 1,
                "cards_needing_combo_sequence": 1,
            },
            "cards": {
                "CARD_A": {
                    "card_id": "CARD_A",
                    "name": "Needs Guide",
                    "readiness_lane": "generic_low_confidence",
                    "first_missing_link": "needs_guide_claim",
                    "runtime_surfaces": [],
                },
                "CARD_B": {
                    "card_id": "CARD_B",
                    "name": "Needs Runtime",
                    "readiness_lane": "report_only_supported",
                    "first_missing_link": "needs_runtime_surface",
                    "runtime_surfaces": ["Mulligan.json"],
                },
                "CARD_C": {
                    "card_id": "CARD_C",
                    "name": "Needs Combo",
                    "readiness_lane": "report_only_supported",
                    "first_missing_link": "needs_combo_sequence",
                    "runtime_surfaces": [],
                },
            },
        },
        claim_coverage_report={
            "cards": {
                "CARD_A": {"coverage_status": "uncovered_low_confidence", "source_claim_ids": []},
                "CARD_B": {"coverage_status": "guide_backed", "source_claim_ids": ["claim_b"]},
                "CARD_C": {"coverage_status": "guide_backed", "source_claim_ids": ["claim_c"]},
            }
        },
        card_behavior_plan={"rows": [], "suppressed": []},
        mulligan_plan={"rules": []},
        combo_plan={"combos": []},
    )

    assert report["deck_name"] == "Example"
    for key, value in {
        "total_cards": 3,
        "blocked_cards": 3,
        "needs_guide_claim": 1,
        "needs_runtime_surface": 1,
        "needs_combo_sequence": 1,
        "needs_mulligan_claim": 0,
        "needs_condition_lowering": 0,
        "needs_mechanic_lowering": 0,
    }.items():
        assert report["summary"][key] == value
    assert report["cards"]["CARD_A"]["recommended_source_claim_kind"] == "card_role"
    assert report["cards"]["CARD_B"]["recommended_source_claim_kind"] == "targeting_rule"
    assert report["cards"]["CARD_C"]["recommended_source_claim_kind"] == "combo_sequence"
    assert report["cards"]["CARD_B"]["priority_score"] > report["cards"]["CARD_A"]["priority_score"]
    assert report["summary"]["first_missing_chain"] == {
        "card_id": "CARD_B",
        "name": "Needs Runtime",
        "first_missing_link": "needs_runtime_surface",
        "source_depth_lane": "runtime_surface_gap",
        "recommended_source_claim_kind": "targeting_rule",
        "recommended_next_claim_kind": "targeting_rule",
        "recommended_next_claim_kinds": ["targeting_rule"],
        "next_action": "add_runtime_lowerable_claim_or_router_support",
        "priority_score": report["cards"]["CARD_B"]["priority_score"],
        "priority_reason": report["cards"]["CARD_B"]["priority_reason"],
    }
    assert report["summary"]["next_source_builder_action"] == "add_runtime_lowerable_claim_or_router_support"


def test_report_uses_none_when_card_is_ready():
    report = build_source_claim_gap_report(
        deck_name="Example",
        config_readiness_report={
            "summary": {"total_cards": 1},
            "cards": {
                "CARD_READY": {
                    "card_id": "CARD_READY",
                    "name": "Ready",
                    "readiness_lane": "runtime_emitted",
                    "first_missing_link": "none",
                    "runtime_surfaces": ["CARD_READY.json"],
                }
            },
        },
        claim_coverage_report={"cards": {"CARD_READY": {"coverage_status": "guide_backed"}}},
        card_behavior_plan={"rows": [], "suppressed": []},
        mulligan_plan={"rules": []},
        combo_plan={"combos": []},
    )

    assert report["summary"]["blocked_cards"] == 0
    assert report["summary"]["first_missing_chain"] is None
    assert report["summary"]["next_source_builder_action"] == "card_ready_for_strong_gate"
    assert report["cards"]["CARD_READY"]["recommended_source_claim_kind"] == "none"
    assert report["cards"]["CARD_READY"]["next_action"] == "card_ready_for_strong_gate"


def test_gap_report_threads_source_depth_lane_into_first_missing_chain():
    report = build_source_claim_gap_report(
        deck_name="Kingslayer",
        config_readiness_report={
            "cards": {
                "DEEP_014": {
                    "card_id": "DEEP_014",
                    "name": "Quick Pick",
                    "readiness_lane": "report_only_supported",
                    "source_depth_lane": "mulligan_claim_gap",
                    "first_missing_link": "needs_mulligan_claim",
                    "runtime_surfaces": [],
                }
            }
        },
        claim_coverage_report={
            "cards": {
                "DEEP_014": {
                    "coverage_status": "source_backed",
                    "source_claim_ids": ["claim_quick_pick"],
                }
            }
        },
        card_behavior_plan={"rows": []},
        mulligan_plan={"rules": []},
        combo_plan={"combos": []},
    )

    row = report["cards"]["DEEP_014"]
    assert row["source_depth_lane"] == "mulligan_claim_gap"
    assert report["summary"]["first_missing_chain"]["source_depth_lane"] == "mulligan_claim_gap"


def test_mulligan_gap_recommends_neutral_claim_choice_not_keep_by_default():
    report = build_source_claim_gap_report(
        deck_name="Kingslayer",
        config_readiness_report={
            "cards": {
                "DEEP_014": {
                    "card_id": "DEEP_014",
                    "name": "Quick Pick",
                    "readiness_lane": "report_only_supported",
                    "source_depth_lane": "mulligan_claim_gap",
                    "first_missing_link": "needs_mulligan_claim",
                    "runtime_surfaces": [],
                }
            }
        },
        claim_coverage_report={
            "cards": {
                "DEEP_014": {
                    "coverage_status": "source_backed",
                    "source_claim_ids": ["claim_quick_pick"],
                }
            }
        },
        card_behavior_plan={"rows": []},
        mulligan_plan={"rules": []},
        combo_plan={"combos": []},
    )

    row = report["cards"]["DEEP_014"]
    assert row["recommended_source_claim_kind"] == "mulligan_claim"
    assert row["recommended_next_claim_kind"] == "mulligan_claim"
    assert row["recommended_next_claim_kinds"] == ["mulligan_keep", "mulligan_discard"]
    assert row["recommended_next_source_action"] == (
        "add explicit mulligan_keep or mulligan_discard source evidence"
    )
    assert report["summary"]["first_missing_chain"]["recommended_source_claim_kind"] == "mulligan_claim"
    assert report["summary"]["first_missing_chain"]["recommended_next_claim_kind"] == "mulligan_claim"
    assert report["summary"]["first_missing_chain"]["recommended_next_claim_kinds"] == [
        "mulligan_keep",
        "mulligan_discard",
    ]


def test_gap_report_includes_deck_level_mulligan_gap_when_default_only():
    report = build_source_claim_gap_report(
        deck_name="DefaultOnly",
        config_readiness_report={"cards": {}},
        claim_coverage_report={"cards": {}},
        mulligan_plan={
            "rules": [],
            "quality": {
                "status": "thin",
                "has_concrete_keeps": False,
                "source_backed_keep_rule_count": 0,
                "policy_backed_keep_rule_count": 0,
                "default_only": True,
            },
        },
        card_behavior_plan={"rows": []},
        combo_plan={"combos": []},
    )

    mulligan = report["deck_surfaces"]["mulligan"]
    assert mulligan["first_missing_link"] == "needs_mulligan_claim"
    assert mulligan["source_depth_lane"] == "mulligan_claim_gap"
    assert mulligan["recommended_source_claim_kind"] == "mulligan_claim"
    assert mulligan["recommended_next_claim_kind"] == "mulligan_claim"
    assert mulligan["recommended_next_claim_kinds"] == ["mulligan_keep", "mulligan_discard"]
    assert report["summary"]["deck_surface_gap_count"] == 1
    assert report["summary"]["first_missing_chain"]["surface"] == "mulligan"
    assert report["summary"]["first_missing_chain"]["recommended_source_claim_kind"] == (
        "mulligan_claim"
    )
    assert report["summary"]["first_missing_chain"]["recommended_next_claim_kind"] == (
        "mulligan_claim"
    )


def test_gap_report_marks_policy_backed_mulligan_as_closed_not_source_backed():
    report = build_source_claim_gap_report(
        deck_name="PolicyClosed",
        config_readiness_report={"cards": {}},
        claim_coverage_report={"cards": {}},
        mulligan_plan={
            "rules": [
                {
                    "card": "CARD_1",
                    "action": "hold",
                    "selector_kind": "card",
                    "source_type": "policy_backed_autonomous_mulligan",
                }
            ],
            "quality": {
                "status": "policy_backed",
                "has_concrete_keeps": True,
                "source_backed_keep_rule_count": 0,
                "policy_backed_keep_rule_count": 1,
                "default_only": False,
            },
        },
        card_behavior_plan={"rows": []},
        combo_plan={"combos": []},
    )

    mulligan = report["deck_surfaces"]["mulligan"]
    assert mulligan["first_missing_link"] == "none"
    assert mulligan["source_depth_lane"] == "policy_backed_autonomous_mulligan"
    assert mulligan["source_quality_lane"] == "policy_backed"
    assert mulligan["recommended_source_claim_kind"] == "none"
    assert mulligan["recommended_next_claim_kind"] == "none"
    assert report["summary"]["deck_surface_gap_count"] == 0


def test_gap_report_includes_policy_lane_for_policy_backed_mulligan_surface():
    report = build_source_claim_gap_report(
        deck_name="PirateRogue",
        config_readiness_report={"cards": {}},
        claim_coverage_report={"cards": {}},
        mulligan_plan={
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
                "policy_backed_keep_rule_count": 1,
                "policy_lanes": ["aggro"],
                "policy_reasons": ["pirate_pressure"],
            },
        },
        card_behavior_plan={"rows": []},
        combo_plan={"combos": []},
    )

    mulligan = report["deck_surfaces"]["mulligan"]
    assert mulligan["source_depth_lane"] == "policy_backed_autonomous_mulligan"
    assert mulligan["policy_lanes"] == ["aggro"]
    assert mulligan["policy_reasons"] == ["pirate_pressure"]
    assert report["summary"]["deck_surface_gap_count"] == 0


def test_suppressed_runtime_claims_report_first_missing_link():
    report = build_source_claim_gap_report(
        deck_name="Suppressed Claims",
        config_readiness_report={"cards": {}},
        claim_coverage_report={"cards": {}},
        card_behavior_plan={
            "rows": [],
            "suppressed": [
                {
                    "claim_id": "runtime_numeric",
                    "claim_kind": "globalvalue_numeric_tuning",
                    "reason": "requires_runtime_evidence",
                },
                {
                    "claim_id": "unresolved_discover",
                    "claim_kind": "discover_choice",
                    "reason": "unresolved_option_identity",
                },
                {
                    "claim_id": "future_mechanic",
                    "claim_kind": "mechanic_usage",
                    "reason": "requires_supported_cardid_surface",
                },
                {
                    "claim_id": "fallback_claim",
                    "claim_kind": "card_role",
                },
            ],
        },
        mulligan_plan={"rules": []},
        combo_plan={"combos": []},
        source_contract_audit={
            "claim_lifecycle_rows": [
                {
                    "claim_id": "conflicting_claim",
                    "claim_kind": "mulligan_keep",
                    "builder_or_router_decision": "suppressed",
                    "first_missing_link": "source_claim_conflict",
                }
            ]
        },
    )

    rows_by_claim_id = {
        row["claim_id"]: row for row in report["suppressed_claim_rows"]
    }
    for claim_id, first_missing_link in {
        "runtime_numeric": "runtime_evidence",
        "unresolved_discover": "option_identity",
        "future_mechanic": "supported_cardid_surface",
        "fallback_claim": "claim_kind_supported_surface",
        "conflicting_claim": "source_claim_conflict",
    }.items():
        row = rows_by_claim_id[claim_id]
        assert row["builder_or_router_decision"] == "suppressed"
        assert row["first_missing_link"] == first_missing_link
        assert row["operator_impact"] == "diagnostic_only"


def test_suppressed_claim_rows_preserve_precise_lifecycle_missing_link():
    report = build_source_claim_gap_report(
        deck_name="Suppressed Claim Collision",
        config_readiness_report={"cards": {}},
        claim_coverage_report={"cards": {}},
        card_behavior_plan={
            "rows": [],
            "suppressed": [
                {
                    "claim_id": "discover_collision",
                    "claim_kind": "discover_choice",
                    "reason": "source_claim_conflict",
                }
            ],
        },
        mulligan_plan={"rules": []},
        combo_plan={"combos": []},
        source_contract_audit={
            "claim_lifecycle_rows": [
                {
                    "claim_id": "discover_collision",
                    "claim_kind": "discover_choice",
                    "builder_or_router_decision": "suppressed",
                    "suppressed_reason": "requires_exact_option_identity",
                    "first_missing_link": "source_claim_conflict",
                }
            ]
        },
    )

    assert report["suppressed_claim_rows"] == [
        {
            "claim_id": "discover_collision",
            "claim_kind": "discover_choice",
            "builder_or_router_decision": "suppressed",
            "first_missing_link": "source_claim_conflict",
            "operator_impact": "diagnostic_only",
        }
    ]


def test_suppressed_claim_rows_include_report_only_not_seen_lifecycle_rows():
    report = build_source_claim_gap_report(
        deck_name="Report Only Claim",
        config_readiness_report={"cards": {}},
        claim_coverage_report={"cards": {}},
        card_behavior_plan={
            "rows": [],
            "suppressed": [
                {
                    "claim_id": "report_only_claim",
                    "claim_kind": "archetype",
                    "reason": "requires_supported_cardid_surface",
                }
            ],
        },
        mulligan_plan={"rules": []},
        combo_plan={"combos": []},
        source_contract_audit={
            "claim_lifecycle_rows": [
                {
                    "claim_id": "report_only_claim",
                    "claim_kind": "archetype",
                    "builder_or_router_decision": "not_seen_by_builder",
                    "suppressed_reason": "no_runtime_builder",
                    "first_missing_link": "claim_kind_policy",
                }
            ]
        },
    )

    assert report["suppressed_claim_rows"] == [
        {
            "claim_id": "report_only_claim",
            "claim_kind": "archetype",
            "builder_or_router_decision": "not_seen_by_builder",
            "first_missing_link": "claim_kind_policy",
            "operator_impact": "diagnostic_only",
        }
    ]


def test_gap_report_projects_initial_source_ineligible_lifecycle_once_with_source_reason():
    claims = [
        {
            "claim_id": "report_only_posture",
            "claim_kind": "gameplan_posture",
            "source_confidence": "report_only",
            "source_title": "Fixture Guide",
            "evidence_text_short": "Maintain an aggressive posture.",
        }
    ]
    source_contract_audit = build_source_contract_audit(
        deck_name="FixtureDeck",
        deck_identity={"deck_name": "FixtureDeck", "cards": []},
        guide_claim_bundle={"claims": claims},
        mulligan_plan={"rules": [], "suppressed_rules": []},
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": [], "suppressed": []},
        global_values_authority_matrix={
            "allowed_step1_overlays": [],
            "blocked_until_runtime_evidence": [],
        },
        config_readiness_report={"cards": {}},
        initial_lifecycle_rows=build_initial_lifecycle_rows(claims),
    )

    report = build_source_claim_gap_report(
        deck_name="FixtureDeck",
        config_readiness_report={"cards": {}},
        claim_coverage_report={"cards": {}},
        card_behavior_plan={"rows": [], "suppressed": []},
        mulligan_plan={"rules": []},
        combo_plan={"combos": []},
        source_contract_audit=source_contract_audit,
    )

    assert report["suppressed_claim_rows"] == [
        {
            "claim_id": "report_only_posture",
            "claim_kind": "gameplan_posture",
            "builder_or_router_decision": "not_seen_by_builder",
            "first_missing_link": "source_eligibility",
            "operator_impact": "diagnostic_only",
        }
    ]
