from __future__ import annotations

import pytest

from tests.helpers.fixture_prepare import load_archetype_matrix, prepare_fixture_deck


@pytest.mark.parametrize("deck", load_archetype_matrix(), ids=lambda row: row["deck_name"])
def test_core_source_backed_fixture_stage_respects_fail_closed_runtime_gate(
    tmp_path,
    monkeypatch,
    deck,
):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: []
    )
    if deck["fixture_stage"] != "core_source_backed_fixture":
        pytest.skip(f"{deck['deck_name']} is not marked as a core source-backed fixture")

    result = prepare_fixture_deck(tmp_path, deck)
    promotion = result["strong_promotion_report"]

    assert result["exit_code"] == 0
    assert result["operator"]["technical_status"] == "VALID_PACKAGE"
    assert result["operator"]["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert result["operator"]["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert result["operator"]["semantic_blockers"]
    assert promotion["verdict"] == "PROMOTION_BLOCKED"
    assert promotion["static_contract_status"] == "SOURCE_BACKED_PARTIAL"
    assert promotion["runtime_lowering_status"] == "LOAD_SAFE_WITH_POLICY_OR_REVIEW_ROWS"
    assert promotion["first_missing_source_action"] != "none"
    assert result["readiness"]["summary"]["cards_needing_guide_claims"] == 0
    assert result["readiness"]["summary"]["cards_needing_mechanic_lowering"] > 0
    assert "Presume.json" not in result["generated_files"]
    assert "Concede.json" not in result["generated_files"]


@pytest.mark.parametrize("deck", load_archetype_matrix(), ids=lambda row: row["deck_name"])
def test_source_backed_partial_fixtures_stay_load_safe_without_strong_claim(
    tmp_path,
    monkeypatch,
    deck,
):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: []
    )
    if deck.get("expected_semantic_status") != "SOURCE_BACKED_PARTIAL":
        pytest.skip(f"{deck['deck_name']} is not expected to stay source-backed partial")

    result = prepare_fixture_deck(tmp_path, deck)
    operator = result["operator"]
    promotion = result["strong_promotion_report"]

    assert result["exit_code"] == 0
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_allowed"] is True
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["semantic_status"] != "SOURCE_BACKED_STRONG"
    assert operator["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert promotion["verdict"] == "PROMOTION_BLOCKED"
    assert promotion["static_contract_status"] == "SOURCE_BACKED_PARTIAL"
