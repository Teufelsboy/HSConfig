from __future__ import annotations

import json

import pytest

from tests.helpers.fixture_prepare import load_archetype_matrix, prepare_fixture_deck


TARGETS = {
    "Boarlock": {
        "first_card_id": "WW_092",
        "first_card_name": "Fracking",
        "expected_runtime_surfaces": {
            "GlobalValues.json",
            "Mulligan.json",
            "Combo.json",
        },
        "forbidden_surfaces": {"Presume.json", "Concede.json"},
    },
    "Kingslayer": {
        "first_card_id": "DEEP_014",
        "first_card_name": "Quick Pick",
        "expected_runtime_surfaces": {
            "GlobalValues.json",
            "Mulligan.json",
        },
        "forbidden_surfaces": {"Presume.json", "Concede.json", "Combo.json"},
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
    generated = set(result["generated_files"])
    target = TARGETS[deck_name]

    assert result["exit_code"] == 0
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert operator["next_action"] == "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY"
    assert operator["source_informed_apply_readiness"]["status"] == "blocked"
    assert promotion["promotion_ready"] is False

    first_chain = gap_report["summary"]["first_missing_chain"]
    assert first_chain["card_id"] == target["first_card_id"]
    assert first_chain["name"] == target["first_card_name"]
    assert first_chain["first_missing_link"] == "needs_mulligan_claim"
    assert first_chain["source_depth_lane"] == "mulligan_claim_gap"
    assert first_chain["next_action"] == "add_mulligan_keep_or_discard_claim"

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
