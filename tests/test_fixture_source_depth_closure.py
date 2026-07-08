from __future__ import annotations

import pytest

from tests.helpers.fixture_prepare import load_archetype_matrix, prepare_fixture_deck


def _source_informed_rows():
    return [
        row
        for row in load_archetype_matrix()
        if row["fixture_stage"] == "source_informed_valid_fixture"
    ]


EXPECTED_SOURCE_INFORMED_BLOCKERS = {
    "Kingslayer": {"unsupported_conditions_present"},
    "Boarlock": {
        "cards_need_runtime_surface",
        "generic_low_confidence_cards",
        "uncovered_cards",
        "unsupported_conditions_present",
    },
}


@pytest.mark.parametrize(
    "deck",
    _source_informed_rows(),
    ids=lambda row: row["deck_name"],
)
def test_source_informed_rows_have_actionable_closure_chain(tmp_path, monkeypatch, deck):
    monkeypatch.setattr("hsconfig.cli.fetch_latest_cards", lambda timeout=10.0: [])

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
        assert operator["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
        readiness = operator["source_informed_apply_readiness"]
        if readiness["status"] == "ready":
            assert operator["next_action"] == "SOURCE_INFORMED_APPLY_READY"
            assert operator["apply_policy"] == "ALLOWED_SOURCE_INFORMED"
            assert readiness["blocking_reasons"] == []
            assert promotion["next_action"] == "source_informed_apply_ready_but_not_strong"
        else:
            assert operator["next_action"] == "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY"
            assert operator["apply_policy"] == "ALLOWED_WITH_WARNINGS"
            assert readiness["status"] == "blocked"
            assert set(readiness["blocking_reasons"]) == EXPECTED_SOURCE_INFORMED_BLOCKERS[
                deck["deck_name"]
            ]
            assert promotion["next_action"] == "close_first_missing_chain"
        assert readiness["source_gap_count"] > 0
        assert (
            promotion["source_informed_apply_readiness"]
            == readiness
        )
        assert gap_report["summary"]["blocked_cards"] > 0
        assert isinstance(chain, dict)
        assert chain["card_id"]
        assert chain["first_missing_link"] in {
            "needs_guide_claim",
            "needs_runtime_surface",
            "needs_mulligan_claim",
            "needs_combo_sequence",
            "needs_condition_lowering",
            "needs_mechanic_lowering",
        }
        assert chain["next_action"]


@pytest.mark.parametrize("deck_name", ["Discolock", "ImbueMage"])
def test_discolock_and_imbuemage_are_now_source_backed_strong(
    tmp_path,
    monkeypatch,
    deck_name,
):
    monkeypatch.setattr("hsconfig.cli.fetch_latest_cards", lambda timeout=10.0: [])

    deck = next(row for row in load_archetype_matrix() if row["deck_name"] == deck_name)
    result = prepare_fixture_deck(tmp_path, deck)
    operator = result["operator"]
    gap_report = result["source_claim_gap_report"]
    promotion = result["strong_promotion_report"]

    assert result["exit_code"] == 0
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert operator["next_action"] == "READY_TO_APPLY_OR_HANDOFF"
    assert promotion["promotion_ready"] is True
    assert gap_report["summary"]["blocked_cards"] == 0
    assert gap_report["summary"]["first_missing_chain"] is None
