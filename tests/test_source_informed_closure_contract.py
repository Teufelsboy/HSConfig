from __future__ import annotations

import json

import pytest

from tests.helpers.fixture_prepare import load_archetype_matrix, prepare_fixture_deck


TARGETS = {
    "Boarlock": {
        "first_card_id": "WW_092",
        "first_card_name": "Fracking",
        "expected_source_depth_lane": "mulligan_claim_gap",
        "expected_stop_condition": "exact_boarlock_fracking_mulligan_source_unavailable",
        "expected_runtime_surfaces": {
            "GlobalValues.json",
            "Mulligan.json",
            "Combo.json",
        },
        "forbidden_surfaces": {"Presume.json", "Concede.json", "CardBehavior.json"},
    },
    "Kingslayer": {
        "first_card_id": "DEEP_014",
        "first_card_name": "Quick Pick",
        "expected_source_depth_lane": "mulligan_claim_gap",
        "expected_stop_condition": None,
        "expected_runtime_surfaces": {
            "GlobalValues.json",
            "Mulligan.json",
        },
        "forbidden_surfaces": {"Presume.json", "Concede.json", "CardBehavior.json", "Combo.json"},
    },
}


@pytest.mark.parametrize("deck_name", ["Boarlock", "Kingslayer"])
def test_source_informed_rows_expose_first_missing_chain_without_apply_ready(
    tmp_path,
    monkeypatch,
    deck_name: str,
):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: []
    )
    deck = next(row for row in load_archetype_matrix() if row["deck_name"] == deck_name)

    result = prepare_fixture_deck(tmp_path, deck)
    operator = result["operator"]
    gap_report = result["source_claim_gap_report"]
    promotion = result["strong_promotion_report"]
    deck_identity = json.loads(
        (result["out"] / "reports" / "deck_identity.json").read_text(encoding="utf-8")
    )
    explainability = json.loads(
        (
            result["out"] / "reports" / "source_to_runtime_explainability.json"
        ).read_text(encoding="utf-8")
    )
    generated = set(result["generated_files"])
    target = TARGETS[deck_name]
    target_card_row = next(
        row for row in explainability["card_rows"] if row["card_id"] == target["first_card_id"]
    )

    assert result["exit_code"] == 0
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert operator["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert operator["runtime_load_safe"] is True
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["source_informed_apply_readiness"]["status"] == "blocked"
    assert {
        "cards_need_mechanic_lowering",
        "contract_gap_not_strong_evidence",
    } <= set(operator["source_informed_apply_readiness"]["blocking_reasons"])
    assert promotion["promotion_ready"] is False

    first_chain = gap_report["summary"]["first_missing_chain"]
    assert first_chain is not None
    assert gap_report["summary"]["blocked_cards"] > 0
    assert target_card_row["name"] == target["first_card_name"]
    if target_card_row["first_missing_link"] == "needs_mechanic_lowering":
        assert (
            target_card_row["next_source_action"]
            == "add_documented_mechanic_runtime_lowering"
        )
    else:
        assert target_card_row["first_missing_link"] == "source_eligibility"
        assert target_card_row["next_source_action"] == "add_explicit_mulligan_claim"
    assert target_card_row["apply_blocked"] is False
    assert "Mulligan.json" in target_card_row["not_emitted_runtime_files"]

    visibility = deck["strongness_visibility"]
    if target["expected_stop_condition"] is not None:
        assert visibility["stop_condition"] == target["expected_stop_condition"]
    assert visibility["closure_state"] == "source_informed_blocked"
    assert visibility["source_informed_apply_readiness"] == "blocked"

    card_surfaces = {f"{card['card_id']}.json" for card in deck_identity["cards"]}
    assert target["expected_runtime_surfaces"] <= generated
    assert generated <= card_surfaces | target["expected_runtime_surfaces"]
    assert not (target["forbidden_surfaces"] & generated)


def test_representative_matrix_remains_eleven_rows():
    matrix = load_archetype_matrix()
    names = [row["deck_name"] for row in matrix]

    assert len(matrix) == 11
    assert names.count("Boarlock") == 1
    assert names.count("Kingslayer") == 1
    assert names.count("CuteWarrior") == 0
