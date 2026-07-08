from hsconfig.source_depth_closure_index import build_source_depth_closure_index


def test_index_exposes_ordered_source_informed_closure_targets():
    matrix = {
        "decks": [
            {
                "deck_name": "ShadowPriest",
                "fixture_stage": "core_source_backed_fixture",
                "strongness_visibility": {"closure_priority": 0},
            },
            {
                "deck_name": "Kingslayer",
                "fixture_stage": "source_informed_valid_fixture",
                "strongness_visibility": {
                    "closure_priority": 2,
                    "source_informed_blocking_reasons": ["unsupported_conditions_present"],
                    "operator_action": "close_existing_source_informed_fixture",
                },
            },
            {
                "deck_name": "Boarlock",
                "fixture_stage": "source_informed_valid_fixture",
                "strongness_visibility": {
                    "closure_priority": 1,
                    "source_informed_blocking_reasons": [
                        "cards_need_runtime_surface",
                        "generic_low_confidence_cards",
                    ],
                    "operator_action": (
                        "preserve_source_informed_with_explicit_stop_condition"
                    ),
                    "stop_condition": (
                        "exact_boarlock_fracking_mulligan_source_unavailable"
                    ),
                },
            },
        ]
    }

    report = build_source_depth_closure_index(matrix, {})

    assert report["summary"]["next_closure_target"] == "Boarlock"
    assert report["summary"]["closure_sequence"] == ["Boarlock", "Kingslayer"]
    assert report["summary"]["preserved_source_informed_targets"] == ["Boarlock"]


def test_index_skips_durably_preserved_rows_for_next_actionable_target():
    matrix = {
        "decks": [
            {
                "deck_name": "Boarlock",
                "fixture_stage": "source_informed_valid_fixture",
                "strongness_visibility": {
                    "closure_priority": 1,
                    "operator_action": (
                        "preserve_source_informed_with_explicit_stop_condition"
                    ),
                    "stop_condition": (
                        "exact_boarlock_fracking_mulligan_source_unavailable"
                    ),
                    "source_informed_blocking_reasons": [
                        "cards_need_runtime_surface",
                        "generic_low_confidence_cards",
                    ],
                },
            },
            {
                "deck_name": "Kingslayer",
                "fixture_stage": "source_informed_valid_fixture",
                "strongness_visibility": {
                    "closure_priority": 2,
                    "operator_action": "close_existing_source_informed_fixture",
                    "source_informed_blocking_reasons": [
                        "unsupported_conditions_present"
                    ],
                },
            },
        ]
    }

    report = build_source_depth_closure_index(matrix, {})

    assert report["summary"]["next_closure_target"] == "Boarlock"
    assert report["summary"]["closure_sequence"] == ["Boarlock", "Kingslayer"]
    assert report["summary"]["preserved_source_informed_targets"] == ["Boarlock"]
    assert report["summary"]["next_actionable_closure_target"] == "Kingslayer"


def test_index_reports_first_missing_link_for_source_informed_rows():
    matrix = {
        "decks": [
            {
                "deck_name": "CtAPaladin",
                "fixture_stage": "source_informed_valid_fixture",
                "strongness_visibility": {
                    "first_strongness_gap": "needs_recruit_aura_runtime_surface_closure",
                    "operator_action": "close_existing_source_informed_fixture",
                },
            },
            {
                "deck_name": "ShadowPriest",
                "fixture_stage": "core_source_backed_fixture",
                "strongness_visibility": {
                    "first_strongness_gap": "none",
                    "operator_action": "keep_as_core_control_fixture",
                },
            },
        ]
    }
    report = build_source_depth_closure_index(
        matrix,
        {
            "CtAPaladin": {
                "operator_summary": {
                    "technical_status": "VALID_PACKAGE",
                    "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
                    "next_action": "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY",
                },
                "source_claim_gap_report": {
                    "summary": {
                        "blocked_cards": 2,
                        "first_missing_chain": {
                            "card_id": "AT_075",
                            "name": "Warhorse Trainer",
                            "first_missing_link": "needs_runtime_surface",
                            "next_action": "add_runtime_lowerable_claim_or_router_support",
                        },
                    }
                },
                "strong_promotion_report": {
                    "promotion_ready": False,
                    "verdict": "PROMOTION_BLOCKED",
                },
            },
            "ShadowPriest": {
                "operator_summary": {
                    "technical_status": "VALID_PACKAGE",
                    "semantic_status": "SOURCE_BACKED_STRONG",
                    "next_action": "READY_TO_APPLY_OR_HANDOFF",
                },
                "source_claim_gap_report": {
                    "summary": {
                        "blocked_cards": 0,
                        "first_missing_chain": None,
                    }
                },
                "strong_promotion_report": {
                    "promotion_ready": True,
                    "verdict": "SOURCE_BACKED_STRONG_CONFIRMED",
                },
            },
        },
    )

    assert report["summary"] == {
        "total_decks": 2,
        "core_source_backed_fixture": 1,
        "source_informed_valid_fixture": 1,
        "promotion_ready": 1,
        "promotion_blocked": 1,
        "next_closure_target": None,
        "next_actionable_closure_target": None,
        "closure_sequence": [],
        "preserved_source_informed_targets": [],
    }
    cta = report["decks"]["CtAPaladin"]
    assert cta["first_missing_chain"]["card_id"] == "AT_075"
    assert cta["first_matrix_gap"] == "needs_recruit_aura_runtime_surface_closure"
    assert cta["next_action"] == "close_first_missing_chain"
    shadow = report["decks"]["ShadowPriest"]
    assert shadow["first_missing_chain"] is None
    assert shadow["next_action"] == "keep_as_core_control_fixture"


def test_index_excludes_non_source_informed_rows_from_preserved_targets():
    matrix = {
        "decks": [
            {
                "deck_name": "Boarlock",
                "fixture_stage": "source_informed_valid_fixture",
                "strongness_visibility": {
                    "closure_priority": 1,
                    "source_informed_blocking_reasons": ["cards_need_runtime_surface"],
                    "operator_action": (
                        "preserve_source_informed_with_explicit_stop_condition"
                    ),
                    "stop_condition": (
                        "exact_boarlock_fracking_mulligan_source_unavailable"
                    ),
                },
            },
            {
                "deck_name": "ShadowPriest",
                "fixture_stage": "core_source_backed_fixture",
                "strongness_visibility": {
                    "operator_action": (
                        "preserve_source_informed_with_explicit_stop_condition"
                    ),
                    "stop_condition": "should_not_be_preserved",
                },
            },
        ]
    }

    report = build_source_depth_closure_index(matrix, {})

    assert report["summary"]["preserved_source_informed_targets"] == ["Boarlock"]


def test_index_uses_matrix_gap_when_reports_are_missing():
    matrix = {
        "decks": [
            {
                "deck_name": "PirateDH",
                "fixture_stage": "source_informed_valid_fixture",
                "strongness_visibility": {
                    "first_strongness_gap": "needs_hero_attack_runtime_surface_closure",
                    "operator_action": "close_existing_source_informed_fixture",
                },
            }
        ]
    }

    report = build_source_depth_closure_index(matrix, {})

    assert report["decks"]["PirateDH"]["report_status"] == "missing_reports"
    assert (
        report["decks"]["PirateDH"]["first_matrix_gap"]
        == "needs_hero_attack_runtime_surface_closure"
    )
    assert report["decks"]["PirateDH"]["next_action"] == "run_prepare_fixture_and_collect_reports"
