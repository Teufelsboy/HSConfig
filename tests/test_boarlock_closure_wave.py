from __future__ import annotations

from hsconfig.source_depth_closure_index import build_source_depth_closure_index
from tests.helpers.fixture_prepare import load_archetype_matrix, prepare_fixture_deck


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


def test_boarlock_prepare_keeps_full_blocker_stack_visible(tmp_path, monkeypatch):
    monkeypatch.setattr("hsconfig.cli.fetch_latest_cards", lambda timeout=10.0: [])
    deck = next(
        row for row in load_archetype_matrix() if row["deck_name"] == "Boarlock"
    )

    result = prepare_fixture_deck(tmp_path, deck)

    operator = result["operator"]
    gap_report = result["source_claim_gap_report"]
    promotion = result["strong_promotion_report"]
    readiness = result["readiness"]

    assert result["exit_code"] == 0
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert operator["next_action"] == "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY"
    assert operator["source_informed_apply_readiness"]["status"] == "blocked"
    assert operator["source_informed_apply_readiness"]["blocking_reasons"] == [
        "cards_need_runtime_surface",
        "generic_low_confidence_cards",
        "uncovered_cards",
        "unsupported_conditions_present",
    ]

    assert promotion["promotion_ready"] is False
    assert promotion["next_action"] == "close_first_missing_chain"
    assert "Combo.json" in result["generated_files"]
    assert "Presume.json" not in result["generated_files"]
    assert "Concede.json" not in result["generated_files"]

    first_chain = gap_report["summary"]["first_missing_chain"]
    assert first_chain == {
        "card_id": "WW_092",
        "name": "Fracking",
        "first_missing_link": "needs_mulligan_claim",
        "recommended_source_claim_kind": "mulligan_keep",
        "next_action": "add_mulligan_keep_or_discard_claim",
        "priority_score": 85,
        "priority_reason": "missing_link:needs_mulligan_claim, report_only_supported:+5, partial_runtime_surface:-10",
    }

    summary = readiness["summary"]
    assert summary["cards_needing_mulligan_claims"] >= 1
    assert summary["cards_needing_runtime_surface"] >= 1
    assert summary["generic_low_confidence"] >= 1


def test_boarlock_closure_outcome_is_either_strong_or_explicitly_preserved(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("hsconfig.cli.fetch_latest_cards", lambda timeout=10.0: [])
    deck = next(
        row for row in load_archetype_matrix() if row["deck_name"] == "Boarlock"
    )

    result = prepare_fixture_deck(tmp_path, deck)
    operator = result["operator"]
    gap_report = result["source_claim_gap_report"]
    promotion = result["strong_promotion_report"]

    if promotion["promotion_ready"]:
        assert operator["semantic_status"] == "SOURCE_BACKED_STRONG"
        assert operator["next_action"] == "READY_TO_APPLY_OR_HANDOFF"
        assert gap_report["summary"]["blocked_cards"] == 0
        assert gap_report["summary"]["first_missing_chain"] is None
    else:
        assert operator["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
        assert operator["source_informed_apply_readiness"]["status"] == "blocked"
        assert gap_report["summary"]["first_missing_chain"]["card_id"] == "WW_092"
        assert promotion["next_action"] == "close_first_missing_chain"
