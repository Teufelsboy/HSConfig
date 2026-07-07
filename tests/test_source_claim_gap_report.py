from hsconfig.source_claim_gap_report import build_source_claim_gap_report


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
    assert report["summary"] == {
        "total_cards": 3,
        "blocked_cards": 3,
        "needs_guide_claim": 1,
        "needs_runtime_surface": 1,
        "needs_combo_sequence": 1,
        "needs_mulligan_claim": 0,
        "needs_condition_lowering": 0,
        "needs_mechanic_lowering": 0,
    }
    assert report["cards"]["CARD_A"]["recommended_source_claim_kind"] == "card_role"
    assert report["cards"]["CARD_B"]["recommended_source_claim_kind"] == "targeting_rule"
    assert report["cards"]["CARD_C"]["recommended_source_claim_kind"] == "combo_sequence"


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
    assert report["cards"]["CARD_READY"]["recommended_source_claim_kind"] == "none"
    assert report["cards"]["CARD_READY"]["next_action"] == "card_ready_for_strong_gate"
