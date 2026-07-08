from hsconfig.config_readiness import build_config_readiness_report


def _two_card_readiness_report(*, mulligan_rule: dict) -> dict:
    return build_config_readiness_report(
        deck_identity={
            "deck_name": "Fixture",
            "deck_slug": "fixture",
            "cards": [
                {"card_id": "CARD_A", "name": "CARD_A", "count": 1},
                {"card_id": "CARD_B", "name": "CARD_B", "count": 1},
            ],
        },
        claim_coverage={"uncovered_cards": [], "total_cards": 2},
        gameplan_contract={
            "cards": {
                "CARD_A": {
                    "card_id": "CARD_A",
                    "name": "CARD_A",
                    "count": 1,
                    "coverage_status": "guide_backed",
                    "roles": ["mulligan_anchor"],
                },
                "CARD_B": {
                    "card_id": "CARD_B",
                    "name": "CARD_B",
                    "count": 1,
                    "coverage_status": "guide_backed",
                    "roles": ["mulligan_anchor"],
                },
            }
        },
        mulligan_plan={"rules": [mulligan_rule]},
        card_behavior_plan={"rows": []},
        combo_plan={"combos": []},
        global_values_authority_matrix={"allowed_step1_overlays": []},
    )


def _report_for_card(
    *,
    card_id: str,
    roles: list[str],
    coverage_status: str = "guide_backed",
    claim_coverage: dict | None = None,
    mulligan_plan: dict | None = None,
    card_behavior_plan: dict | None = None,
    combo_plan: dict | None = None,
    emitted_cardid_files: list[str] | None = None,
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
        emitted_cardid_files=emitted_cardid_files,
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
        card_behavior_plan={
            "rows": [
                {
                    "card_id": "CARD_001",
                    "surface": "CardID.json",
                    "behavior_block": "BeforePlayCardBonus",
                    "meaningful_runtime_surface": True,
                }
            ]
        },
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


def test_multi_card_mulligan_selectors_credit_every_selector_card():
    for selector_kind, selector in (
        ("plus_combo", "CARD_A + CARD_B"),
        ("card_list", "CARD_A, CARD_B"),
    ):
        report = _two_card_readiness_report(
            mulligan_rule={
                "card": "CARD_A",
                "selector_kind": selector_kind,
                "selector": selector,
                "selector_cards": ["CARD_A", "CARD_B"],
                "action": "hold",
            }
        )

        assert report["cards"]["CARD_A"]["runtime_surfaces"] == ["Mulligan.json"]
        assert report["cards"]["CARD_B"]["runtime_surfaces"] == ["Mulligan.json"]


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
    assert row["source_depth_lane"] == "source_claim_gap"
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


def test_non_meaningful_cardid_row_keeps_fallback_runtime_surface_visibility():
    report = _report_for_card(
        card_id="CARD_009",
        roles=["pressure"],
        card_behavior_plan={
            "rows": [
                {
                    "card_id": "CARD_009",
                    "surface": "CardID.json",
                    "meaningful_runtime_surface": False,
                }
            ]
        },
    )

    row = report["cards"]["CARD_009"]
    assert row["runtime_surfaces"] == ["CARD_009.json"]
    assert row["readiness_lane"] == "report_only_supported"
    assert row["first_missing_link"] == "needs_runtime_surface"


def test_emitted_cardid_files_add_runtime_surface_without_marking_generic_card_ready():
    report = _report_for_card(
        card_id="CARD_008",
        roles=[],
        coverage_status="generic_low_confidence",
        claim_coverage={"uncovered_cards": ["CARD_008"], "total_cards": 1},
        card_behavior_plan={"rows": []},
        emitted_cardid_files=["CARD_008.json"],
    )

    row = report["cards"]["CARD_008"]
    assert row["runtime_surfaces"] == ["CARD_008.json"]
    assert row["readiness_lane"] == "generic_low_confidence"
    assert row["first_missing_link"] == "needs_guide_claim"
    assert report["summary"]["runtime_emitted"] == 0
    assert report["summary"]["cards_needing_guide_claims"] == 1


def test_suppressed_mulligan_claim_does_not_hide_generic_low_confidence_gap():
    report = _report_for_card(
        card_id="CARD_008_SUPPRESSED",
        roles=["mulligan_anchor"],
        coverage_status="generic_low_confidence",
        claim_coverage={"uncovered_cards": ["CARD_008_SUPPRESSED"], "total_cards": 1},
        mulligan_plan={
            "rules": [],
            "suppressed_rules": [
                {
                    "card": "CARD_008_SUPPRESSED",
                    "reason": "claim_not_runtime_lowerable",
                }
            ],
        },
    )

    row = report["cards"]["CARD_008_SUPPRESSED"]
    assert row["readiness_lane"] == "generic_low_confidence"
    assert row["first_missing_link"] == "needs_guide_claim"
    assert report["summary"]["generic_low_confidence"] == 1
    assert report["summary"]["cards_needing_mulligan_claims"] == 0


def test_guide_backed_suppressed_mulligan_claim_blocks_runtime_emitted_lane():
    report = _report_for_card(
        card_id="DEEP_014",
        roles=["mulligan_anchor", "weapon"],
        coverage_status="source_backed",
        mulligan_plan={
            "rules": [],
            "suppressed_rules": [
                {
                    "card": "DEEP_014",
                    "reason": "claim_not_runtime_lowerable",
                }
            ],
        },
        card_behavior_plan={
            "rows": [
                {
                    "card_id": "DEEP_014",
                    "surface": "CardID.json",
                    "surface_family": "CARDID.json",
                    "behavior_block": "BeforePlayCardBonus = attack_pressure",
                    "meaningful_runtime_surface": True,
                }
            ],
            "suppressed": [],
        },
        emitted_cardid_files=["DEEP_014.json"],
    )

    row = report["cards"]["DEEP_014"]
    assert row["runtime_surfaces"] == ["DEEP_014.json"]
    assert row["readiness_lane"] == "report_only_supported"
    assert row["first_missing_link"] == "needs_mulligan_claim"
    assert row["source_depth_lane"] == "mulligan_claim_gap"
    assert report["summary"]["runtime_emitted"] == 0
    assert report["summary"]["cards_needing_mulligan_claims"] == 1


def test_readiness_counts_only_meaningful_cardid_rows_as_runtime_emitted():
    report = build_config_readiness_report(
        deck_identity={
            "deck_name": "Fixture",
            "deck_slug": "fixture",
            "cards": [
                {"card_id": "EX1_GENERIC", "name": "Generic", "count": 1},
                {"card_id": "EX1_DEEP", "name": "Deep", "count": 1},
            ],
        },
        claim_coverage={"uncovered_cards": []},
        gameplan_contract={
            "deck_name": "Fixture",
            "deck_slug": "fixture",
            "cards": {
                "EX1_GENERIC": {
                    "card_id": "EX1_GENERIC",
                    "name": "Generic",
                    "coverage_status": "guide_backed",
                    "roles": ["deck_card"],
                },
                "EX1_DEEP": {
                    "card_id": "EX1_DEEP",
                    "name": "Deep",
                    "coverage_status": "guide_backed",
                    "roles": ["overkill"],
                },
            },
        },
        mulligan_plan={"rules": []},
        card_behavior_plan={
            "rows": [
                {
                    "surface": "CardID.json",
                    "surface_family": "CARDID.json",
                    "card_id": "EX1_GENERIC",
                    "roles": ["deck_card"],
                    "meaningful_runtime_surface": False,
                },
                {
                    "surface": "CardID.json",
                    "surface_family": "CARDID.json",
                    "card_id": "EX1_DEEP",
                    "roles": ["overkill"],
                    "behavior_block": "BeforeOverkilledBonus",
                    "meaningful_runtime_surface": True,
                },
            ],
            "suppressed": [],
        },
        combo_plan={"combos": []},
        global_values_authority_matrix={"allowed_step1_overlays": []},
        emitted_cardid_files={"EX1_GENERIC.json", "EX1_DEEP.json"},
    )

    assert report["cards"]["EX1_DEEP"]["readiness_lane"] == "runtime_emitted"
    assert report["cards"]["EX1_DEEP"]["first_missing_link"] == "none"
    assert report["cards"]["EX1_GENERIC"]["readiness_lane"] == "report_only_supported"
    assert report["cards"]["EX1_GENERIC"]["first_missing_link"] == "needs_runtime_surface"


def test_source_backed_hero_power_transform_can_be_satisfied_by_globalvalues():
    report = build_config_readiness_report(
        deck_identity={
            "deck_name": "Deck",
            "cards": [{"card_id": "SW_448", "name": "Darkbishop Benedictus"}],
        },
        claim_coverage={"uncovered_cards": []},
        gameplan_contract={
            "deck_name": "Deck",
            "cards": {
                "SW_448": {
                    "card_id": "SW_448",
                    "name": "Darkbishop Benedictus",
                    "coverage_status": "source_backed_static_semantics",
                    "roles": ["hero_power_transform"],
                }
            },
            "hero_power_expectations": [{"source_card_id": "SW_448"}],
        },
        mulligan_plan={"rules": []},
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": []},
        global_values_authority_matrix={"allowed_step1_overlays": [{"key": "MyHeroPowerValue"}]},
        emitted_cardid_files=[],
    )

    row = report["cards"]["SW_448"]
    assert row["readiness_lane"] == "globalvalues_only"
    assert row["first_missing_link"] == "none"


def test_globalvalues_card_with_empty_roles_still_needs_runtime_surface():
    report = build_config_readiness_report(
        deck_identity={
            "deck_name": "Deck",
            "cards": [{"card_id": "SW_448", "name": "Darkbishop Benedictus"}],
        },
        claim_coverage={"uncovered_cards": []},
        gameplan_contract={
            "deck_name": "Deck",
            "cards": {
                "SW_448": {
                    "card_id": "SW_448",
                    "name": "Darkbishop Benedictus",
                    "coverage_status": "source_backed_static_semantics",
                    "roles": [],
                }
            },
            "hero_power_expectations": [{"source_card_id": "SW_448"}],
        },
        mulligan_plan={"rules": []},
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": []},
        global_values_authority_matrix={"allowed_step1_overlays": [{"key": "MyHeroPowerValue"}]},
        emitted_cardid_files=[],
    )

    row = report["cards"]["SW_448"]
    assert row["readiness_lane"] == "globalvalues_only"
    assert row["first_missing_link"] == "needs_runtime_surface"
