from __future__ import annotations

import json
from pathlib import Path

from hsconfig.source_depth_closure_index import build_source_depth_closure_index
from tests.helpers.fixture_prepare import load_archetype_matrix, prepare_fixture_deck


def _explainability(result):
    return json.loads(
        (result["out"] / "reports" / "source_to_runtime_explainability.json").read_text(
            encoding="utf-8"
        )
    )


def _card_explainability(result, card_id: str):
    explainability = _explainability(result)
    return next(row for row in explainability["card_rows"] if row["card_id"] == card_id)


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
                        "unsupported_conditions_present",
                    ],
                    "closure_state": "source_informed_blocked",
                    "closure_priority": 1,
                    "operator_action": "preserve_source_informed_with_explicit_stop_condition",
                    "stop_condition": "exact_boarlock_fracking_mulligan_source_unavailable",
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
                    "operator_action": "preserve_source_informed_with_explicit_stop_condition",
                    "stop_condition": "exact_kingslayer_quick_pick_mulligan_source_unavailable",
                },
            },
        ]
    }

    report = build_source_depth_closure_index(matrix, {})

    assert report["summary"]["next_closure_target"] == "Boarlock"
    assert report["summary"]["closure_sequence"] == ["Boarlock", "Kingslayer"]
    assert report["summary"]["preserved_source_informed_targets"] == [
        "Boarlock",
        "Kingslayer",
    ]
    assert report["summary"]["next_actionable_closure_target"] is None

    boarlock = report["decks"]["Boarlock"]
    assert boarlock["closure_decision"] == "preserve_source_informed_until_blockers_close"
    assert boarlock["closure_blocker_stack"] == [
        "unsupported_conditions_present",
    ]
    assert boarlock["stop_condition"] == "exact_boarlock_fracking_mulligan_source_unavailable"
    assert boarlock["stop_condition_reason"] == (
        "source-informed row has hard blockers and cannot be promoted or applied as strong"
    )
    assert boarlock["recommended_next_target"] == "Boarlock"

    kingslayer = report["decks"]["Kingslayer"]
    assert kingslayer["closure_decision"] == "preserve_source_informed_until_blockers_close"
    assert kingslayer["stop_condition"] == (
        "exact_kingslayer_quick_pick_mulligan_source_unavailable"
    )
    assert kingslayer["recommended_next_target"] is None


def test_boarlock_prepare_keeps_full_blocker_stack_visible(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: []
    )
    deck = next(
        row for row in load_archetype_matrix() if row["deck_name"] == "Boarlock"
    )

    result = prepare_fixture_deck(tmp_path, deck)

    operator = result["operator"]
    gap_report = result["source_claim_gap_report"]
    promotion = result["strong_promotion_report"]
    readiness = result["readiness"]
    fracking = _card_explainability(result, "WW_092")

    assert result["exit_code"] == 0
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] == "STATIC_SEMANTICS_USABLE"
    assert operator["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert operator["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    assert operator["runtime_load_safe"] is True
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["source_informed_apply_readiness"]["status"] == "not_applicable"
    assert operator["source_informed_apply_readiness"]["blocking_reasons"] == []

    assert promotion["promotion_ready"] is False
    assert promotion["next_action"] == "close_first_missing_chain"
    assert "Combo.json" in result["generated_files"]
    assert "Presume.json" not in result["generated_files"]
    assert "Concede.json" not in result["generated_files"]

    assert gap_report["summary"]["first_missing_chain"] is None
    assert gap_report["summary"]["blocked_cards"] == 0
    assert fracking["name"] == "Fracking"
    assert fracking["first_missing_link"] == "source_eligibility"
    assert fracking["next_source_action"] == "add_explicit_mulligan_claim"
    assert fracking["apply_blocked"] is False
    assert "Mulligan.json" in fracking["not_emitted_runtime_files"]

    summary = readiness["summary"]
    assert summary["cards_needing_mulligan_claims"] == 0
    assert summary["cards_needing_runtime_surface"] == 0
    assert summary["generic_low_confidence"] == 0
    assert summary["report_only_supported"] == 0
    assert operator["config_usefulness"]["surfaces"]["mulligan"]["status"] == "policy_backed"
    assert operator["config_usefulness"]["surfaces"]["mulligan"]["default_only"] is False
    assert (
        operator["config_usefulness"]["surfaces"]["mulligan"][
            "policy_backed_keep_rule_count"
        ]
        > 0
    )


def test_boarlock_closure_outcome_is_either_strong_or_explicitly_preserved(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: []
    )
    deck = next(
        row for row in load_archetype_matrix() if row["deck_name"] == "Boarlock"
    )

    result = prepare_fixture_deck(tmp_path, deck)
    operator = result["operator"]
    gap_report = result["source_claim_gap_report"]
    promotion = result["strong_promotion_report"]
    explainability = _explainability(result)

    if promotion["promotion_ready"]:
        assert operator["semantic_status"] == "SOURCE_BACKED_STRONG"
        assert operator["next_action"] == "READY_TO_APPLY_OR_HANDOFF"
        assert gap_report["summary"]["blocked_cards"] == 0
        assert gap_report["summary"]["first_missing_chain"] is None
    else:
        assert operator["semantic_status"] == "STATIC_SEMANTICS_USABLE"
        assert operator["source_informed_apply_readiness"]["status"] == "not_applicable"
        assert gap_report["summary"]["first_missing_chain"] is None
        assert explainability["summary"]["cards_with_first_missing_link"] > 0
        assert promotion["next_action"] == "close_first_missing_chain"


def test_low_confidence_fracking_mulligan_row_does_not_satisfy_missing_chain(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: []
    )
    deck = next(
        row for row in load_archetype_matrix() if row["deck_name"] == "Boarlock"
    )

    fixture = json.loads(
        Path("tests/fixtures/source_documents_boarlock_strong.json").read_text(
            encoding="utf-8"
        )
    )
    fracking_mulligan_claims = [
        claim
        for source in fixture["source_documents"]
        for claim in source["claims"]
        if claim.get("claim_kind") == "mulligan_keep"
        and "WW_092" in claim.get("cards", [])
    ]
    assert len(fracking_mulligan_claims) == 1
    assert fracking_mulligan_claims[0]["source_confidence"] == "low"

    result = prepare_fixture_deck(tmp_path, deck)
    operator = result["operator"]
    gap_report = result["source_claim_gap_report"]
    fracking = _card_explainability(result, "WW_092")

    assert operator["semantic_status"] == "STATIC_SEMANTICS_USABLE"
    assert operator["source_informed_apply_readiness"]["status"] == "not_applicable"
    assert gap_report["summary"]["first_missing_chain"] is None
    assert fracking["card_id"] == "WW_092"
    assert fracking["first_missing_link"] == "source_eligibility"
    assert fracking["next_source_action"] == "add_explicit_mulligan_claim"
    assert fracking["apply_blocked"] is False


def test_boarlock_closure_does_not_widen_runtime_surfaces(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: []
    )
    deck = next(
        row for row in load_archetype_matrix() if row["deck_name"] == "Boarlock"
    )

    result = prepare_fixture_deck(tmp_path, deck)
    deck_identity = json.loads(
        (result["out"] / "reports" / "deck_identity.json").read_text(encoding="utf-8")
    )

    generated = set(result["generated_files"])
    allowed_non_card_surfaces = {
        "GlobalValues.json",
        "Mulligan.json",
        "Combo.json",
    }
    allowed_card_surfaces = {
        f"{card['card_id']}.json" for card in deck_identity["cards"]
    }
    allowed_surfaces = allowed_non_card_surfaces | allowed_card_surfaces

    assert generated == allowed_surfaces
    assert "Presume.json" not in generated
    assert "Concede.json" not in generated
