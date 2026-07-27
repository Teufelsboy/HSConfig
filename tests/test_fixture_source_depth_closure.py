from __future__ import annotations

import pytest

from hsconfig.source_depth_closure_index import build_source_depth_closure_index
from tests.helpers.fixture_prepare import load_archetype_matrix, prepare_fixture_deck


def _source_informed_rows():
    return [
        row
        for row in load_archetype_matrix()
        if row["fixture_stage"] == "source_informed_valid_fixture"
    ]


@pytest.mark.parametrize(
    "deck",
    _source_informed_rows(),
    ids=lambda row: row["deck_name"],
)
def test_source_informed_rows_have_actionable_closure_chain(tmp_path, monkeypatch, deck):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: []
    )

    result = prepare_fixture_deck(tmp_path, deck)
    operator = result["operator"]
    gap_report = result["source_claim_gap_report"]
    promotion = result["strong_promotion_report"]

    assert result["exit_code"] == 0
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert "Presume.json" not in result["generated_files"]
    assert "Concede.json" not in result["generated_files"]

    if promotion["promotion_ready"]:
        assert operator["semantic_status"] == "SOURCE_BACKED_STRONG"
        assert operator["next_action"] == "READY_TO_APPLY_OR_HANDOFF"
        assert gap_report["summary"]["blocked_cards"] == 0
        assert gap_report["summary"]["first_missing_chain"] is None
    else:
        chain = gap_report["summary"]["first_missing_chain"]
        assert operator["semantic_status"] in {
            "VALID_BUT_NOT_GUIDE_STRONG",
        }
        readiness = operator["source_informed_apply_readiness"]
        if readiness["status"] == "not_applicable":
            assert operator["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
            assert operator["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
            assert operator["apply_policy"] == "ALLOWED_WITH_WARNINGS"
            assert readiness["blocking_reasons"] == []
            assert promotion["next_action"] == "close_first_missing_chain"
            assert gap_report["summary"]["blocked_cards"] == 0
            assert chain is None
        elif readiness["status"] == "ready":
            assert operator["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
            assert operator["apply_policy"] == "ALLOWED_WITH_WARNINGS"
            assert readiness["blocking_reasons"] == []
            assert promotion["next_action"] == "source_informed_apply_ready_but_not_strong"
        else:
            assert operator["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
            assert operator["apply_policy"] == "ALLOWED_WITH_WARNINGS"
            assert readiness["status"] == "blocked"
            visibility = deck["strongness_visibility"]
            assert visibility["source_informed_apply_readiness"] == "blocked"
            assert {
                "cards_need_mechanic_lowering",
                "contract_gap_not_strong_evidence",
            } <= set(readiness["blocking_reasons"])
            assert promotion["next_action"] == "close_first_missing_chain"
        assert operator["runtime_load_safe"] is True
        assert operator["runtime_apply_mode"] == "blocked"
        assert operator["runtime_apply_allowed"] is False
        assert operator["source_apply_eligibility_reasons"] == [
            "diagnostic_source_not_apply_eligible"
        ]
        if readiness["status"] == "not_applicable":
            assert readiness["source_gap_count"] == 0
        else:
            assert readiness["source_gap_count"] > 0 or readiness["blocking_reasons"]
        assert (
            promotion["source_informed_apply_readiness"]
            == readiness
        )
        if chain is not None:
            assert gap_report["summary"]["blocked_cards"] > 0
            assert isinstance(chain, dict)
            assert chain["card_id"]
            assert chain["first_missing_link"] in {
                "needs_guide_claim",
                "needs_runtime_surface",
                "needs_mulligan_claim",
                "needs_combo_sequence",
                "needs_condition_lowering",
                "needs_target_scope",
                "needs_invalid_target_scope",
                "needs_target_surface",
                "needs_mechanic_lowering",
                "semantic_surface_not_expressible",
            }
            assert chain["next_action"]


def test_imbuemage_static_semantics_remain_load_safe_but_not_strong(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: []
    )

    deck = next(row for row in load_archetype_matrix() if row["deck_name"] == "ImbueMage")
    result = prepare_fixture_deck(tmp_path, deck)
    operator = result["operator"]
    gap_report = result["source_claim_gap_report"]
    promotion = result["strong_promotion_report"]

    assert result["exit_code"] == 0
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert operator["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert promotion["promotion_ready"] is False
    assert gap_report["summary"]["blocked_cards"] > 0
    assert gap_report["summary"]["first_missing_chain"] is not None


def test_discolock_remains_source_informed_with_visible_evidence_debt(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: []
    )

    deck = next(row for row in load_archetype_matrix() if row["deck_name"] == "Discolock")
    result = prepare_fixture_deck(tmp_path, deck)
    operator = result["operator"]
    gap_report = result["source_claim_gap_report"]
    promotion = result["strong_promotion_report"]
    readiness = operator["source_informed_apply_readiness"]

    assert result["exit_code"] == 0
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert operator["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert operator["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    assert readiness["status"] == "blocked"
    assert readiness["source_gap_count"] == 0
    assert {
        "policy_claim_not_strong_evidence",
        "source_evidence_warnings",
    } <= set(readiness["blocking_reasons"])
    assert promotion["promotion_ready"] is False
    assert promotion["next_action"] == "close_first_missing_chain"
    assert gap_report["summary"]["blocked_cards"] > 0
    assert gap_report["summary"]["first_missing_chain"] is not None


def test_source_informed_rows_explain_blocked_closure_decision_without_promotion():
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
                    ],
                    "operator_action": (
                        "preserve_source_informed_with_explicit_stop_condition"
                    ),
                    "stop_condition": (
                        "exact_boarlock_fracking_mulligan_source_unavailable"
                    ),
                },
            }
        ]
    }

    report = build_source_depth_closure_index(matrix, {})

    boarlock = report["decks"]["Boarlock"]
    assert boarlock["next_action"] == "run_prepare_fixture_and_collect_reports"
    assert boarlock["closure_decision"] == "preserve_source_informed_until_blockers_close"
    assert boarlock["first_blocking_reason"] == "cards_need_runtime_surface"
    assert boarlock["preserve_reason"] == (
        "source-informed row has hard blockers and cannot be promoted or applied as strong"
    )
