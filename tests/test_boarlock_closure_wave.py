from __future__ import annotations

from hsconfig.source_depth_closure_index import build_source_depth_closure_index


def test_boarlock_source_informed_row_exposes_explicit_stop_condition():
    matrix = {
        "decks": [
            {
                "deck_name": "Boarlock",
                "fixture_stage": "source_informed_valid_fixture",
                "strongness_visibility": {
                    "first_strongness_gap": "needs_mulligan_claim_for_fracking",
                    "source_informed_apply_readiness": "blocked",
                    "source_informed_blocking_reasons": [
                        "cards_need_runtime_surface",
                        "generic_low_confidence_cards",
                        "uncovered_cards",
                        "unsupported_conditions_present",
                    ],
                    "closure_state": "source_informed_blocked",
                    "closure_priority": 1,
                    "operator_action": "close_existing_source_informed_fixture",
                },
            },
            {
                "deck_name": "Kingslayer",
                "fixture_stage": "source_informed_valid_fixture",
                "strongness_visibility": {
                    "first_strongness_gap": "needs_mulligan_claim_for_quick_pick",
                    "source_informed_apply_readiness": "blocked",
                    "source_informed_blocking_reasons": [
                        "unsupported_conditions_present",
                    ],
                    "closure_state": "source_informed_blocked",
                    "closure_priority": 2,
                    "operator_action": "close_existing_source_informed_fixture",
                },
            },
        ]
    }

    report = build_source_depth_closure_index(matrix, {})

    boarlock = report["decks"]["Boarlock"]
    assert boarlock["closure_decision"] == "preserve_source_informed_until_blockers_close"
    assert boarlock["closure_blocker_stack"] == [
        "cards_need_runtime_surface",
        "generic_low_confidence_cards",
        "uncovered_cards",
        "unsupported_conditions_present",
    ]
    assert boarlock["stop_condition"] == "exact_source_or_lowering_gap_still_open"
    assert boarlock["stop_condition_reason"] == (
        "source-informed row has hard blockers and cannot be promoted or applied as strong"
    )
    assert boarlock["recommended_next_target"] == "Boarlock"

    kingslayer = report["decks"]["Kingslayer"]
    assert kingslayer["recommended_next_target"] is None
