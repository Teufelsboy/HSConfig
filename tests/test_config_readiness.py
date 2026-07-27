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


def test_sideboard_cards_are_visible_but_do_not_expand_main_deck_readiness_counts():
    report = build_config_readiness_report(
        deck_identity={
            "deck_name": "MechPala",
            "deck_slug": "mechpala",
            "cards": [
                {"card_id": "TOY_330", "name": "Zilliax Deluxe 3000", "count": 1}
            ],
            "sideboards": [
                {
                    "owner_card_id": "TOY_330",
                    "cards": [
                        {"card_id": "TOY_330t95", "name": "Virus Module", "count": 1},
                        {"card_id": "TOY_330t98", "name": "Perfect Module", "count": 1},
                        {"card_id": "TOY_330t11", "name": "Power Module", "count": 1},
                    ],
                }
            ],
        },
        claim_coverage={"uncovered_cards": [], "total_cards": 1},
        gameplan_contract={
            "cards": {
                "TOY_330": {
                    "card_id": "TOY_330",
                    "name": "Zilliax Deluxe 3000",
                    "count": 1,
                    "coverage_status": "guide_backed",
                    "roles": ["deckbuilding_modifier", "sideboard_owner"],
                }
            }
        },
        mulligan_plan={"rules": []},
        card_behavior_plan={"rows": []},
        combo_plan={"combos": []},
        global_values_authority_matrix={"allowed_step1_overlays": []},
    )

    assert report["summary"]["total_cards"] == 1
    assert report["summary"]["analysis_only_sideboard_cards"] == 3
    for card_id in {"TOY_330t95", "TOY_330t98", "TOY_330t11"}:
        assert report["cards"][card_id] == {
            "card_id": card_id,
            "name": report["cards"][card_id]["name"],
            "count": 1,
            "coverage_status": "",
            "roles": [],
            "source_claim_ids": [],
            "mechanic_support": [],
            "deck_zone": "sideboard",
            "sideboard_owner_card_id": "TOY_330",
            "sideboard_owner_card_ids": ["TOY_330"],
            "sideboard_memberships": [
                {
                    "sideboard_index": 1,
                    "owner_card_id": "TOY_330",
                    "count": 1,
                }
            ],
            "runtime_eligible": False,
            "runtime_surfaces": [],
            "readiness_lane": "report_only_supported",
            "first_missing_link": "none",
            "source_depth_lane": "closed",
        }


def test_cross_zone_duplicate_keeps_main_readiness_and_sideboard_membership():
    report = build_config_readiness_report(
        deck_identity={
            "deck_name": "Collision",
            "deck_slug": "collision",
            "cards": [
                {"card_id": "OWNER_A", "count": 1},
                {"card_id": "SHARED", "count": 2, "name": "Main Copy"},
            ],
            "sideboards": [
                {
                    "sideboard_index": 1,
                    "owner_card_id": "OWNER_A",
                    "cards": [
                        {"card_id": "SHARED", "count": 1, "name": "Sideboard Copy"}
                    ],
                }
            ],
        },
        claim_coverage={"uncovered_cards": [], "total_cards": 2},
        gameplan_contract={
            "cards": {
                "OWNER_A": {"card_id": "OWNER_A", "count": 1, "roles": []},
                "SHARED": {"card_id": "SHARED", "count": 2, "roles": []},
            }
        },
        mulligan_plan={"rules": []},
        card_behavior_plan={"rows": []},
        combo_plan={"combos": []},
        global_values_authority_matrix={"allowed_step1_overlays": []},
    )

    assert report["summary"]["total_cards"] == 2
    assert report["summary"]["analysis_only_sideboard_cards"] == 0
    shared = report["cards"]["SHARED"]
    assert shared["name"] == "Main Copy"
    assert shared["count"] == 2
    assert shared["deck_zone"] == "main"
    assert shared["runtime_eligible"] is True
    assert shared["sideboard_owner_card_ids"] == ["OWNER_A"]
    assert shared["sideboard_memberships"] == [
        {
            "sideboard_index": 1,
            "owner_card_id": "OWNER_A",
            "count": 1,
        }
    ]


def test_empty_per_card_file_is_visible_but_not_semantically_closed():
    report = build_config_readiness_report(
        deck_identity=_one_card_identity("CFM_637"),
        claim_coverage=_covered_claims(
            "CFM_637",
            "source_backed_static_semantics",
        ),
        card_behavior_plan={
            "rows": [],
            "suppressed": [
                {
                    "claim_id": "patches-trigger",
                    "claim_kind": "mechanic_usage",
                    "cards": ["CFM_637"],
                    "reason": "semantic_surface_not_expressible",
                }
            ],
        },
        emitted_cardid_files=["CFM_637.json"],
        mulligan_plan={"rules": [], "suppressed_rules": []},
        combo_plan={"combos": [], "suppressed": []},
        gameplan_contract={},
        global_values_authority_matrix={},
    )

    card = report["cards"]["CFM_637"]
    assert card["runtime_surfaces"] == ["CFM_637.json"]
    assert card["readiness_lane"] == "report_only_supported"
    assert card["first_missing_link"] == "semantic_surface_not_expressible"


def test_reciprocal_burn_report_only_suppression_is_semantically_closed():
    report = build_config_readiness_report(
        deck_identity=_one_card_identity("GVG_009"),
        claim_coverage=_covered_claims(
            "GVG_009",
            "source_backed_static_semantics",
        ),
        card_behavior_plan={
            "rows": [],
            "suppressed": [
                {
                    "claim_id": "shadowbomber-reciprocal-burn",
                    "claim_kind": "card_role",
                    "cards": ["GVG_009"],
                    "reason": "reciprocal_burn_report_only",
                }
            ],
        },
        emitted_cardid_files=[],
        mulligan_plan={"rules": [], "suppressed_rules": []},
        combo_plan={"combos": [], "suppressed": []},
        gameplan_contract={},
        global_values_authority_matrix={},
    )

    card = report["cards"]["GVG_009"]
    assert card["readiness_lane"] == "report_only_supported"
    assert card["first_missing_link"] == "semantic_surface_not_expressible"
    assert report["summary"]["report_only_supported"] == 1
    assert report["summary"]["cards_needing_mechanic_lowering"] == 0


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
        emitted_cardid_files={
            "CARD_001.json": {
                "GameCardId": "CARD_001",
                "ConfigComment": "Fixture",
                "BeforePlayCardBonus": {
                    "values": [{"condition": "*", "value": "8"}],
                },
            }
        },
    )

    assert report["summary"]["runtime_emitted"] == 1
    row = report["cards"]["CARD_001"]
    assert row["readiness_lane"] == "runtime_emitted"
    assert row["first_missing_link"] == "none"
    assert row["runtime_surfaces"] == ["CARD_001.json"]


def test_meaningful_report_row_requires_matching_emitted_cardid_file():
    report = _report_for_card(
        card_id="CARD_MISSING_FILE",
        roles=["pressure"],
        card_behavior_plan={
            "rows": [
                {
                    "card_id": "CARD_MISSING_FILE",
                    "surface": "CardID.json",
                    "surface_family": "CARDID.json",
                    "behavior_block": "BeforePlayCardBonus",
                    "meaningful_runtime_surface": True,
                }
            ],
            "suppressed": [],
        },
        emitted_cardid_files=[],
    )

    row = report["cards"]["CARD_MISSING_FILE"]
    assert row["runtime_surfaces"] == []
    assert row["readiness_lane"] == "report_only_supported"
    assert row["first_missing_link"] == "needs_runtime_surface"
    assert report["summary"]["runtime_emitted"] == 0


def test_missing_cardid_file_gap_is_not_hidden_by_source_backed_mulligan_surface():
    report = _report_for_card(
        card_id="CARD_MISSING_BEHAVIOR",
        roles=["mulligan_anchor"],
        coverage_status="source_backed",
        mulligan_plan={
            "rules": [
                {
                    "card": "CARD_MISSING_BEHAVIOR",
                    "action": "hold",
                    "source_claim_ids": ["CARD_MISSING_BEHAVIOR_claim"],
                }
            ]
        },
        card_behavior_plan={
            "rows": [
                {
                    "card_id": "CARD_MISSING_BEHAVIOR",
                    "surface": "CardID.json",
                    "surface_family": "CARDID.json",
                    "behavior_block": "BeforePlayCardBonus",
                    "meaningful_runtime_surface": True,
                }
            ],
            "suppressed": [],
        },
        emitted_cardid_files=[],
    )

    row = report["cards"]["CARD_MISSING_BEHAVIOR"]
    assert row["runtime_surfaces"] == ["Mulligan.json"]
    assert row["readiness_lane"] == "report_only_supported"
    assert row["first_missing_link"] == "needs_runtime_surface"
    assert report["summary"]["runtime_emitted"] == 0


def test_physical_runtime_row_takes_precedence_over_report_suppression():
    report = _report_for_card(
        card_id="CARD_PARTIAL",
        roles=["pressure"],
        card_behavior_plan={
            "rows": [
                {
                    "card_id": "CARD_PARTIAL",
                    "surface": "CardID.json",
                    "surface_family": "CARDID.json",
                    "behavior_block": "BeforePlayCardBonus",
                    "meaningful_runtime_surface": True,
                }
            ],
            "suppressed": [
                {
                    "claim_id": "conditional_claim",
                    "cards": ["CARD_PARTIAL"],
                    "reason": "unsupported_condition",
                }
            ],
        },
        emitted_cardid_files={
            "CARD_PARTIAL.json": {
                "GameCardId": "CARD_PARTIAL",
                "ConfigComment": "Fixture generated behavior",
                "BeforePlayCardBonus": {
                    "values": [
                        {
                            "comment": "Fixture behavior",
                            "condition": "*",
                            "value": "8",
                        }
                    ]
                },
            }
        },
    )

    row = report["cards"]["CARD_PARTIAL"]
    assert row["runtime_surfaces"] == ["CARD_PARTIAL.json"]
    assert row["readiness_lane"] == "runtime_emitted"
    assert row["first_missing_link"] == "none"
    assert row["source_depth_lane"] == "closed"
    assert report["summary"]["runtime_emitted"] == 1


def test_identity_only_cardid_payload_is_visible_but_not_meaningful_emission():
    report = _report_for_card(
        card_id="CARD_METADATA_ONLY",
        roles=["pressure"],
        card_behavior_plan={
            "rows": [
                {
                    "card_id": "CARD_METADATA_ONLY",
                    "surface": "CardID.json",
                    "surface_family": "CARDID.json",
                    "behavior_block": "BeforePlayCardBonus",
                    "meaningful_runtime_surface": True,
                }
            ],
            "suppressed": [],
        },
        emitted_cardid_files={
            "CARD_METADATA_ONLY.json": {
                "GameCardId": "CARD_METADATA_ONLY",
                "ConfigComment": "Identity only",
            }
        },
    )

    row = report["cards"]["CARD_METADATA_ONLY"]
    assert row["runtime_surfaces"] == ["CARD_METADATA_ONLY.json"]
    assert row["readiness_lane"] == "report_only_supported"
    assert row["first_missing_link"] == "needs_runtime_surface"
    assert report["summary"]["runtime_emitted"] == 0


def test_cardid_filename_presence_without_parsed_payload_is_not_runtime_emission():
    report = _report_for_card(
        card_id="CARD_FILENAME_ONLY",
        roles=["pressure"],
        card_behavior_plan={
            "rows": [
                {
                    "card_id": "CARD_FILENAME_ONLY",
                    "surface": "CardID.json",
                    "surface_family": "CARDID.json",
                    "behavior_block": "BeforePlayCardBonus",
                    "meaningful_runtime_surface": True,
                }
            ],
            "suppressed": [],
        },
        emitted_cardid_files=["CARD_FILENAME_ONLY.json"],
    )

    row = report["cards"]["CARD_FILENAME_ONLY"]
    assert row["runtime_surfaces"] == ["CARD_FILENAME_ONLY.json"]
    assert row["readiness_lane"] == "report_only_supported"
    assert row["first_missing_link"] == "needs_runtime_surface"
    assert report["summary"]["runtime_emitted"] == 0


def test_unsupported_physical_behavior_block_is_not_runtime_emission():
    report = _report_for_card(
        card_id="CARD_UNSUPPORTED_BLOCK",
        roles=["pressure"],
        card_behavior_plan={
            "rows": [
                {
                    "card_id": "CARD_UNSUPPORTED_BLOCK",
                    "surface_family": "CARDID.json",
                    "behavior_block": "BeforePlayCardBonus",
                    "meaningful_runtime_surface": True,
                }
            ],
            "suppressed": [],
        },
        emitted_cardid_files={
            "CARD_UNSUPPORTED_BLOCK.json": {
                "GameCardId": "CARD_UNSUPPORTED_BLOCK",
                "ConfigComment": "Fixture",
                "InventedBehaviorBlock": {
                    "values": [{"condition": "*", "value": "8"}],
                },
            }
        },
    )

    row = report["cards"]["CARD_UNSUPPORTED_BLOCK"]
    assert row["readiness_lane"] == "report_only_supported"
    assert row["first_missing_link"] == "needs_runtime_surface"
    assert report["summary"]["runtime_emitted"] == 0


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


def test_audited_semantic_suppressions_have_stable_readiness_links():
    expected_by_reason = {
        "variable_cost_condition_not_encoded": "needs_condition_lowering",
        "symmetric_board_condition_not_encoded": "needs_condition_lowering",
        "shatter_state_not_encoded": "needs_condition_lowering",
        "combo_target_condition_not_encoded": "needs_condition_lowering",
        "combo_count_condition_not_encoded": "needs_condition_lowering",
        "hand_position_condition_not_encoded": "needs_condition_lowering",
        "symmetric_summon_condition_not_encoded": "needs_condition_lowering",
        "health_cost_condition_not_encoded": "needs_condition_lowering",
        "spell_cannot_use_battlecry_target": "semantic_surface_not_expressible",
        "spell_cannot_own_on_board": "semantic_surface_not_expressible",
        "trigger_owner_does_not_attack": "semantic_surface_not_expressible",
        "buff_target_owner_mismatch": "needs_target_scope",
        "battlecry_owner_does_not_attack": "semantic_surface_not_expressible",
        "attack_owner_not_proven": "semantic_surface_not_expressible",
    }

    for reason, expected_link in expected_by_reason.items():
        report = _report_for_card(
            card_id="AUDITED_CARD",
            roles=["pressure"],
            card_behavior_plan={
                "rows": [],
                "suppressed": [
                    {
                        "claim_id": f"claim_{reason}",
                        "cards": ["AUDITED_CARD"],
                        "reason": reason,
                    }
                ],
            },
        )

        assert report["cards"]["AUDITED_CARD"]["first_missing_link"] == expected_link


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
        emitted_cardid_files={
            "EX1_GENERIC.json": {
                "GameCardId": "EX1_GENERIC",
                "ConfigComment": "Fixture",
            },
            "EX1_DEEP.json": {
                "GameCardId": "EX1_DEEP",
                "ConfigComment": "Fixture",
                "BeforeOverkilledBonus": {
                    "values": [{"condition": "*", "value": "8"}],
                },
            },
        },
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


def test_linked_runtime_entity_readiness_is_separate_from_deck_card_readiness():
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
        card_behavior_plan={
            "rows": [
                {
                    "surface": "CardID.json",
                    "surface_family": "CARDID.json",
                    "card_id": "SW_448",
                    "source_card_id": "SW_448",
                    "runtime_card_id": "EX1_625t",
                    "link_kind": "hero_power_transform",
                    "behavior_block": "BeforeUseHeroPowerBonus",
                    "meaningful_runtime_surface": True,
                }
            ],
            "suppressed": [],
        },
        combo_plan={"combos": []},
        global_values_authority_matrix={
            "allowed_step1_overlays": [{"key": "MyHeroPowerValue"}]
        },
        emitted_cardid_files={
            "SW_448.json": {
                "GameCardId": "SW_448",
                "ConfigComment": "metadata only",
            },
            "EX1_625t.json": {
                "GameCardId": "EX1_625t",
                "ConfigComment": "linked runtime owner",
                "BeforeUseHeroPowerBonus": {
                    "values": [{"condition": "*", "value": "10"}],
                },
            },
        },
    )

    assert report["summary"]["total_cards"] == 1
    assert report["summary"]["runtime_emitted"] == 0
    assert report["summary"]["linked_runtime_source"] == 1
    assert report["summary"]["linked_runtime_entity"] == 1
    assert report["cards"]["SW_448"]["readiness_lane"] == "linked_runtime_source"
    assert report["cards"]["SW_448"]["runtime_surfaces"] == [
        "SW_448.json",
        "EX1_625t.json",
        "GlobalValues.json",
    ]
    assert report["linked_runtime_entities"]["EX1_625t"] == {
        "readiness_category": "linked_runtime_entity",
        "source_card_id": "SW_448",
        "runtime_card_id": "EX1_625t",
        "link_kind": "hero_power_transform",
        "runtime_surface": "EX1_625t.json",
        "runtime_emitted": True,
        "filename_game_card_id_match": True,
    }


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
