from hsconfig.config_readiness import build_config_readiness_report


def _report_for_card(
    *,
    card_id: str,
    roles: list[str],
    coverage_status: str = "guide_backed",
    claim_coverage: dict | None = None,
    mulligan_plan: dict | None = None,
    card_behavior_plan: dict | None = None,
    combo_plan: dict | None = None,
) -> dict:
    return build_config_readiness_report(
        deck_identity={
            "deck_name": "Fixture",
            "deck_slug": "fixture",
            "cards": [{"card_id": card_id, "name": card_id, "count": 1}],
        },
        claim_coverage=claim_coverage or {"uncovered_cards": [], "total_cards": 1},
        gameplan_contract={
            "cards": {
                card_id: {
                    "card_id": card_id,
                    "name": card_id,
                    "count": 1,
                    "coverage_status": coverage_status,
                    "roles": roles,
                    "source_claim_ids": [f"{card_id}_claim"],
                }
            }
        },
        mulligan_plan=mulligan_plan or {"rules": []},
        card_behavior_plan=card_behavior_plan or {"rows": []},
        combo_plan=combo_plan or {"combos": []},
        global_values_authority_matrix={"allowed_step1_overlays": []},
    )


def test_runtime_emitted_card_gets_runtime_lane():
    report = build_config_readiness_report(
        deck_identity={
            "deck_name": "Fixture",
            "deck_slug": "fixture",
            "cards": [{"card_id": "CARD_001", "name": "Burn Card", "count": 2}],
        },
        claim_coverage={"uncovered_cards": [], "total_cards": 1},
        gameplan_contract={
            "cards": {
                "CARD_001": {
                    "card_id": "CARD_001",
                    "name": "Burn Card",
                    "count": 2,
                    "coverage_status": "guide_backed",
                    "roles": ["pressure"],
                }
            }
        },
        mulligan_plan={"rules": []},
        card_behavior_plan={"rows": [{"card_id": "CARD_001", "surface": "CardID.json"}]},
        combo_plan={"combos": []},
        global_values_authority_matrix={"allowed_step1_overlays": []},
    )

    assert report["summary"]["runtime_emitted"] == 1
    row = report["cards"]["CARD_001"]
    assert row["readiness_lane"] == "runtime_emitted"
    assert row["first_missing_link"] == "none"
    assert row["runtime_surfaces"] == ["CARD_001.json"]


def test_mulligan_only_card_gets_specific_lane():
    report = build_config_readiness_report(
        deck_identity={
            "deck_name": "Fixture",
            "deck_slug": "fixture",
            "cards": [{"card_id": "CARD_002", "name": "Keep Card", "count": 1}],
        },
        claim_coverage={"uncovered_cards": [], "total_cards": 1},
        gameplan_contract={
            "cards": {
                "CARD_002": {
                    "card_id": "CARD_002",
                    "name": "Keep Card",
                    "count": 1,
                    "coverage_status": "guide_backed",
                    "roles": ["mulligan_anchor"],
                }
            }
        },
        mulligan_plan={"rules": [{"card": "CARD_002", "action": "hold"}]},
        card_behavior_plan={"rows": []},
        combo_plan={"combos": []},
        global_values_authority_matrix={"allowed_step1_overlays": []},
    )

    row = report["cards"]["CARD_002"]
    assert row["readiness_lane"] == "mulligan_only"
    assert row["first_missing_link"] == "needs_runtime_surface"


def test_uncovered_card_gets_guide_claim_missing_link():
    report = build_config_readiness_report(
        deck_identity={
            "deck_name": "Fixture",
            "deck_slug": "fixture",
            "cards": [{"card_id": "CARD_003", "name": "Unknown Card", "count": 2}],
        },
        claim_coverage={"uncovered_cards": ["CARD_003"], "total_cards": 1},
        gameplan_contract={
            "cards": {
                "CARD_003": {
                    "card_id": "CARD_003",
                    "name": "Unknown Card",
                    "count": 2,
                    "coverage_status": "generic_low_confidence",
                    "roles": [],
                }
            }
        },
        mulligan_plan={"rules": []},
        card_behavior_plan={"rows": []},
        combo_plan={"combos": []},
        global_values_authority_matrix={"allowed_step1_overlays": []},
    )

    row = report["cards"]["CARD_003"]
    assert row["readiness_lane"] == "generic_low_confidence"
    assert row["first_missing_link"] == "needs_guide_claim"
    assert report["summary"]["cards_needing_guide_claims"] == 1


def test_guide_backed_mulligan_anchor_without_rule_needs_mulligan_claim():
    report = _report_for_card(card_id="CARD_004", roles=["mulligan_anchor"])

    row = report["cards"]["CARD_004"]
    assert row["readiness_lane"] == "report_only_supported"
    assert row["first_missing_link"] == "needs_mulligan_claim"
    assert report["summary"]["cards_needing_mulligan_claims"] == 1


def test_guide_backed_combo_piece_without_combo_needs_combo_sequence():
    report = _report_for_card(card_id="CARD_005", roles=["combo_piece"])

    row = report["cards"]["CARD_005"]
    assert row["readiness_lane"] == "report_only_supported"
    assert row["first_missing_link"] == "needs_combo_sequence"
    assert report["summary"]["cards_needing_combo_sequence"] == 1


def test_unsupported_condition_suppression_needs_condition_lowering():
    report = _report_for_card(
        card_id="CARD_006",
        roles=["pressure"],
        card_behavior_plan={
            "rows": [],
            "suppressed": [
                {
                    "claim_id": "claim_unsupported_condition",
                    "cards": ["CARD_006"],
                    "reason": "unsupported_condition",
                }
            ],
        },
    )

    row = report["cards"]["CARD_006"]
    assert row["readiness_lane"] == "report_only_supported"
    assert row["first_missing_link"] == "needs_condition_lowering"
    assert report["summary"]["cards_needing_condition_lowering"] == 1


def test_non_cardid_diagnostic_row_does_not_count_as_runtime_surface():
    report = _report_for_card(
        card_id="CARD_007",
        roles=["pressure"],
        card_behavior_plan={
            "rows": [
                {
                    "card_id": "CARD_007",
                    "surface": "diagnostic_report.json",
                    "intent": "explain_gap",
                }
            ]
        },
    )

    row = report["cards"]["CARD_007"]
    assert row["runtime_surfaces"] == []
    assert row["readiness_lane"] == "report_only_supported"
    assert row["first_missing_link"] == "needs_runtime_surface"
