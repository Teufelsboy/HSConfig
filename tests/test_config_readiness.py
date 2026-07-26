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


def _one_card_identity(card_id: str) -> dict:
    return {
        "deck_name": "Fixture",
        "deck_slug": "fixture",
        "cards": [
            {
                "card_id": card_id,
                "name": card_id,
                "count": 1,
                "coverage_status": "guide_backed",
            }
        ],
    }


def _covered_claims(card_id: str, coverage_status: str) -> dict:
    return {
        "uncovered_cards": [],
        "cards": {card_id: {"coverage_status": coverage_status}},
        "total_cards": 1,
    }


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


def test_source_backed_mulligan_only_card_closes_runtime_surface():
    report = _report_for_card(
        card_id="CARD_SOURCE_KEEP",
        roles=["mulligan_anchor"],
        coverage_status="source_backed",
        mulligan_plan={
            "rules": [
                {
                    "card": "CARD_SOURCE_KEEP",
                    "action": "hold",
                    "source_claim_ids": ["CARD_SOURCE_KEEP_claim"],
                }
            ]
        },
    )

    row = report["cards"]["CARD_SOURCE_KEEP"]
    assert row["runtime_surfaces"] == ["Mulligan.json"]
    assert row["readiness_lane"] == "mulligan_only"
    assert row["first_missing_link"] == "none"
    assert report["summary"]["cards_needing_runtime_surface"] == 0


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


def test_targeting_suppression_does_not_count_as_runtime_closed():
    report = build_config_readiness_report(
        deck_identity=_one_card_identity("NX2_019"),
        claim_coverage=_covered_claims("NX2_019", "guide_backed"),
        card_behavior_plan={
            "rows": [],
            "suppressed": [
                {
                    "claim_id": "target",
                    "claim_kind": "targeting_rule",
                    "cards": ["NX2_019"],
                    "reason": "missing_target_scope",
                }
            ],
        },
        mulligan_plan={"rules": [], "suppressed_rules": []},
        combo_plan={"combos": [], "suppressed": []},
        gameplan_contract={},
        global_values_authority_matrix={},
    )

    assert report["cards"]["NX2_019"]["readiness_lane"] != "runtime_emitted"
    assert report["cards"]["NX2_019"]["first_missing_link"] == "needs_target_scope"
    assert report["summary"]["cards_needing_target_scope"] == 1


def test_invalid_target_scope_suppression_is_visible_in_readiness():
    report = build_config_readiness_report(
        deck_identity=_one_card_identity("NX2_019"),
        claim_coverage=_covered_claims("NX2_019", "guide_backed"),
        card_behavior_plan={
            "rows": [],
            "suppressed": [
                {
                    "claim_id": "target-invalid-scope",
                    "claim_kind": "targeting_rule",
                    "cards": ["NX2_019"],
                    "reason": "invalid_target_scope",
                }
            ],
        },
        mulligan_plan={"rules": [], "suppressed_rules": []},
        combo_plan={"combos": [], "suppressed": []},
        gameplan_contract={},
        global_values_authority_matrix={},
    )

    assert report["cards"]["NX2_019"]["first_missing_link"] == "needs_invalid_target_scope"
    assert report["summary"]["cards_needing_invalid_target_scope"] == 1


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
    assert row["runtime_surfaces"] == ["GlobalValues.json"]
    assert row["readiness_lane"] == "globalvalues_only"
    assert row["first_missing_link"] == "none"


def test_baseline_only_globalvalues_matrix_does_not_credit_source_cards():
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
        global_values_authority_matrix={
            "allowed_step1_overlays": [
                {
                    "key": "baseline",
                    "overlay": "none",
                    "operation": "none",
                    "authority": "baseline_default",
                }
            ]
        },
        emitted_cardid_files=[],
    )

    row = report["cards"]["SW_448"]
    assert row["runtime_surfaces"] == []
    assert row["readiness_lane"] != "globalvalues_only"
    assert row["first_missing_link"] != "none"


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


def test_config_readiness_reports_mechanic_support_without_blocking_load_safe():
    report = build_config_readiness_report(
        deck_identity={
            "deck_name": "Mechanic Deck",
            "deck_slug": "mechanicdeck",
            "cards": [
                {"card_id": "DREDGE_001", "name": "Dredge Card", "roles": ["dredge"], "count": 1},
                {"card_id": "BATTLE_001", "name": "Battlecry Card", "roles": ["battlecry"], "count": 1},
            ],
        },
        claim_coverage={"uncovered_cards": []},
        gameplan_contract={
            "deck_name": "Mechanic Deck",
            "deck_slug": "mechanicdeck",
            "cards": {
                "DREDGE_001": {
                    "card_id": "DREDGE_001",
                    "name": "Dredge Card",
                    "roles": ["dredge"],
                    "coverage_status": "source_backed_static_semantics",
                },
                "BATTLE_001": {
                    "card_id": "BATTLE_001",
                    "name": "Battlecry Card",
                    "roles": ["battlecry"],
                    "coverage_status": "source_backed_static_semantics",
                },
            },
        },
        mulligan_plan={"rules": []},
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": []},
        global_values_authority_matrix={"allowed_step1_overlays": []},
        emitted_cardid_files=["DREDGE_001.json", "BATTLE_001.json"],
    )

    assert report["cards"]["DREDGE_001"]["mechanic_support"][0]["mechanic"] == "dredge"
    assert report["cards"]["DREDGE_001"]["mechanic_support"][0]["support_level"] == "warning_only"
    assert report["cards"]["BATTLE_001"]["mechanic_support"][0]["support_level"] == "direct"
    assert report["summary"]["mechanic_support"]["warning_only_mechanics"] == ["dredge"]
    assert report["summary"]["mechanic_support"]["support_level_counts"]["direct"] == 1
    assert report["summary"]["mechanic_support"]["support_level_counts"]["warning_only"] == 1
    visibility = report["summary"]["mechanic_visibility"]
    assert visibility["non_blocking"] is True
    assert visibility["bucket_counts"]["direct"] == 1
    assert visibility["bucket_counts"]["warning_only"] == 1
    assert visibility["mechanics_by_bucket"]["warning_only"] == ["dredge"]
    assert visibility["first_warning_boundary"]["mechanic"] == "dredge"
    assert visibility["warning_boundaries"] == [
        {
            "mechanic": "dredge",
            "warning_boundary": "Dredge option selection has no documented normal-path VisionAI choice surface.",
        }
    ]


def test_source_backed_lowerable_mechanic_without_runtime_row_needs_mechanic_lowering():
    report = _report_for_card(
        card_id="DEATH_001",
        roles=["deathrattle"],
        coverage_status="source_backed_static_semantics",
        card_behavior_plan={"rows": [], "suppressed": []},
        emitted_cardid_files=["DEATH_001.json"],
    )

    row = report["cards"]["DEATH_001"]

    assert row["readiness_lane"] == "report_only_supported"
    assert row["first_missing_link"] == "needs_mechanic_lowering"
    assert row["source_depth_lane"] == "mechanic_lowering_gap"
    assert report["summary"]["cards_needing_mechanic_lowering"] == 1


def test_report_only_mechanics_do_not_create_mechanic_lowering_gaps():
    report = build_config_readiness_report(
        deck_identity={
            "deck_name": "Warning Deck",
            "deck_slug": "warningdeck",
            "cards": [
                {"card_id": "DREDGE_001", "name": "Dredge Card", "count": 1},
                {"card_id": "TRADE_001", "name": "Tradeable Card", "count": 1},
                {"card_id": "FUTURE_001", "name": "Future Card", "count": 1},
            ],
        },
        claim_coverage={"uncovered_cards": [], "total_cards": 3},
        gameplan_contract={
            "deck_name": "Warning Deck",
            "deck_slug": "warningdeck",
            "cards": {
                "DREDGE_001": {
                    "card_id": "DREDGE_001",
                    "name": "Dredge Card",
                    "roles": ["dredge"],
                    "coverage_status": "source_backed_static_semantics",
                },
                "TRADE_001": {
                    "card_id": "TRADE_001",
                    "name": "Tradeable Card",
                    "roles": ["tradeable"],
                    "coverage_status": "source_backed_static_semantics",
                },
                "FUTURE_001": {
                    "card_id": "FUTURE_001",
                    "name": "Future Card",
                    "roles": ["future_keyword"],
                    "coverage_status": "source_backed_static_semantics",
                },
            },
        },
        mulligan_plan={"rules": []},
        card_behavior_plan={"rows": [], "suppressed": []},
        combo_plan={"combos": []},
        global_values_authority_matrix={"allowed_step1_overlays": []},
        emitted_cardid_files=["DREDGE_001.json", "TRADE_001.json", "FUTURE_001.json"],
    )

    assert report["summary"]["cards_needing_mechanic_lowering"] == 0
    assert "needs_mechanic_lowering" not in {
        row["first_missing_link"] for row in report["cards"].values()
    }
    assert report["summary"]["mechanic_visibility"]["mechanics_by_bucket"]["warning_only"] == [
        "dredge",
        "future_keyword",
        "tradeable",
    ]


def test_identity_gated_mechanic_without_default_block_is_not_mechanic_lowering_gap():
    report = _report_for_card(
        card_id="START_001",
        roles=["start_of_game"],
        coverage_status="source_backed_static_semantics",
        card_behavior_plan={"rows": [], "suppressed": []},
        emitted_cardid_files=["START_001.json"],
    )

    row = report["cards"]["START_001"]

    assert row["first_missing_link"] != "needs_mechanic_lowering"
    assert report["summary"]["cards_needing_mechanic_lowering"] == 0


def test_config_readiness_keeps_unknown_mechanic_role_visible_as_warning_only():
    report = _report_for_card(
        card_id="FUTURE_001",
        roles=["future_keyword", "pressure"],
        coverage_status="source_backed_static_semantics",
        emitted_cardid_files=["FUTURE_001.json"],
    )

    mechanic_support = report["cards"]["FUTURE_001"]["mechanic_support"]

    assert mechanic_support[0] == {
        "mechanic": "future_keyword",
        "support_level": "warning_only",
        "normal_path_surfaces": ["report-only"],
        "warning_boundary": (
            "No registered VisionAI normal-path surface exists for role "
            "'future_keyword'; keep it visible as warning-only until mapped."
        ),
        "lowering": {
            "policy": "report_only",
            "static_claim_allowed": False,
            "default_block": None,
            "allowed_blocks": [],
            "default_value": "6",
            "default_condition": "*",
            "default_intent": None,
            "suppression_reason": "unregistered_mechanic_runtime_surface",
        },
        "registered": False,
    }
    assert report["summary"]["mechanic_support"]["warning_only_mechanics"] == [
        "future_keyword"
    ]
    assert report["summary"]["mechanic_support"]["warning_only_card_count"] == 1
