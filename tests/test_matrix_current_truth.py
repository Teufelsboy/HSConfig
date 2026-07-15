import json
from pathlib import Path


MATRIX_PATH = Path("docs/operator/archetype-fixture-matrix.json")
OPERATOR_README = Path("docs/operator/README.md")


def _matrix_rows():
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))["decks"]


def test_active_matrix_has_expected_source_informed_partial_rows():
    source_informed = {
        row["deck_name"]
        for row in _matrix_rows()
        if row["fixture_stage"] == "source_informed_valid_fixture"
    }

    assert source_informed == {
        "CtAPaladin",
        "Discolock",
        "TreantDruid",
        "Kingslayer",
        "Boarlock",
        "PirateDH",
    }


def test_source_informed_rows_are_expected_current_candidates():
    source_informed = {
        row["deck_name"]: {
            "first_strongness_gap": row["strongness_visibility"]["first_strongness_gap"],
            "source_informed_apply_readiness": row["strongness_visibility"][
                "source_informed_apply_readiness"
            ],
            "source_informed_blocking_reasons": row["strongness_visibility"][
                "source_informed_blocking_reasons"
            ],
        }
        for row in _matrix_rows()
        if row["fixture_stage"] == "source_informed_valid_fixture"
    }

    assert source_informed == {
        "CtAPaladin": {
            "first_strongness_gap": "needs_explicit_mulligan_source",
            "source_informed_apply_readiness": "blocked",
            "source_informed_blocking_reasons": ["policy_claim_not_strong_evidence"],
        },
        "Discolock": {
            "first_strongness_gap": "needs_explicit_mulligan_source",
            "source_informed_apply_readiness": "blocked",
            "source_informed_blocking_reasons": [
                "policy_claim_not_strong_evidence",
                "source_evidence_warnings",
            ],
        },
        "TreantDruid": {
            "first_strongness_gap": "needs_card_specific_source_claim",
            "source_informed_apply_readiness": "blocked",
            "source_informed_blocking_reasons": [
                "generic_low_confidence_cards",
                "policy_claim_not_strong_evidence",
                "source_evidence_warnings",
                "uncovered_cards",
            ],
        },
        "Kingslayer": {
            "first_strongness_gap": "needs_mulligan_claim_for_quick_pick",
            "source_informed_apply_readiness": "blocked",
            "source_informed_blocking_reasons": ["unsupported_conditions_present"],
        },
        "Boarlock": {
            "first_strongness_gap": "needs_mulligan_claim_for_fracking",
            "source_informed_apply_readiness": "blocked",
            "source_informed_blocking_reasons": ["unsupported_conditions_present"],
        },
        "PirateDH": {
            "first_strongness_gap": "needs_card_specific_source_claim",
            "source_informed_apply_readiness": "blocked",
            "source_informed_blocking_reasons": [
                "generic_low_confidence_cards",
                "source_evidence_warnings",
                "uncovered_cards",
            ],
        },
    }


def test_active_operator_docs_do_not_claim_seven_source_informed_rows():
    text = OPERATOR_README.read_text(encoding="utf-8")

    assert "seven `source_informed_valid_fixture` rows" not in text
    assert (
        "Boarlock and Kingslayer are both durable source-informed controls with explicit"
        in text
    )
    assert (
        "Add or promote only when exact source evidence closes a"
        in text
    )
    assert (
        "Close the current Kingslayer and Boarlock `source_informed_valid_fixture` rows "
        "before widening the matrix."
    ) not in text
    assert (
        "Keep the current Kingslayer and Boarlock `source_informed_valid_fixture` rows "
        "closed before widening the matrix."
    ) not in text


def test_active_matrix_stays_at_eleven_representative_decks():
    rows = _matrix_rows()

    assert len(rows) == 11
    assert sum(row["fixture_stage"] == "core_source_backed_fixture" for row in rows) == 5
    assert sum(row["fixture_stage"] == "source_informed_valid_fixture" for row in rows) == 6


def test_source_informed_rows_have_explicit_closure_decisions():
    by_name = {row["deck_name"]: row for row in _matrix_rows()}

    cta_paladin = by_name["CtAPaladin"]["strongness_visibility"]
    assert cta_paladin["first_strongness_gap"] == "needs_explicit_mulligan_source"
    assert cta_paladin["source_informed_apply_readiness"] == "blocked"
    assert (
        cta_paladin["operator_action"]
        == "preserve_source_informed_with_evidence_gap"
    )
    assert cta_paladin["source_informed_blocking_reasons"] == [
        "policy_claim_not_strong_evidence"
    ]

    discolock = by_name["Discolock"]["strongness_visibility"]
    assert discolock["first_strongness_gap"] == "needs_explicit_mulligan_source"
    assert discolock["source_informed_apply_readiness"] == "blocked"
    assert (
        discolock["operator_action"]
        == "preserve_source_informed_with_evidence_gap"
    )
    assert discolock["source_informed_blocking_reasons"] == [
        "policy_claim_not_strong_evidence",
        "source_evidence_warnings",
    ]

    treant_druid = by_name["TreantDruid"]["strongness_visibility"]
    assert treant_druid["first_strongness_gap"] == "needs_card_specific_source_claim"
    assert treant_druid["source_informed_apply_readiness"] == "blocked"
    assert (
        treant_druid["operator_action"]
        == "preserve_source_informed_with_evidence_gap"
    )
    assert treant_druid["source_informed_blocking_reasons"] == [
        "generic_low_confidence_cards",
        "policy_claim_not_strong_evidence",
        "source_evidence_warnings",
        "uncovered_cards",
    ]

    kingslayer = by_name["Kingslayer"]["strongness_visibility"]
    assert kingslayer["first_strongness_gap"] == "needs_mulligan_claim_for_quick_pick"
    assert kingslayer["source_informed_apply_readiness"] == "blocked"
    assert kingslayer["operator_action"] == (
        "preserve_source_informed_with_explicit_stop_condition"
    )
    assert (
        kingslayer["stop_condition"]
        == "exact_kingslayer_quick_pick_mulligan_source_unavailable"
    )

    boarlock = by_name["Boarlock"]["strongness_visibility"]
    assert boarlock["first_strongness_gap"] == "needs_mulligan_claim_for_fracking"
    assert boarlock["source_informed_apply_readiness"] == "blocked"
    assert boarlock["operator_action"] == "preserve_source_informed_with_explicit_stop_condition"
    assert boarlock["stop_condition"] == "exact_boarlock_fracking_mulligan_source_unavailable"

    pirate_dh = by_name["PirateDH"]["strongness_visibility"]
    assert pirate_dh["first_strongness_gap"] == "needs_card_specific_source_claim"
    assert pirate_dh["source_informed_apply_readiness"] == "blocked"
    assert (
        pirate_dh["operator_action"]
        == "preserve_source_informed_with_evidence_gap"
    )
    assert pirate_dh["source_informed_blocking_reasons"] == [
        "generic_low_confidence_cards",
        "source_evidence_warnings",
        "uncovered_cards",
    ]


def test_closure_doc_names_partial_rows_without_claiming_them_strong():
    operator_text = OPERATOR_README.read_text(encoding="utf-8")
    closure_text = Path("docs/operator/source-backed-strong-closure.md").read_text(
        encoding="utf-8"
    )

    expected = (
        "After durable Boarlock and Kingslayer preservation, the current actionable "
        "source-informed closure targets are the four partial representative rows"
    )
    assert expected in operator_text
    assert "Next actionable closure target after durable Boarlock preservation" not in operator_text
    assert "Next actionable closure target after durable Boarlock preservation" not in closure_text
    assert (
        "Do not treat Boarlock's low-confidence Fracking row as SOURCE_BACKED_STRONG."
        in closure_text
    )
    assert "| CtAPaladin | `SOURCE_BACKED_PARTIAL`" in closure_text
    assert "| Discolock | `SOURCE_BACKED_PARTIAL`" in closure_text
    assert "| TreantDruid | `SOURCE_BACKED_PARTIAL`" in closure_text
    assert "| PirateDH | `SOURCE_BACKED_PARTIAL`" in closure_text
    assert "| CtAPaladin | `SOURCE_BACKED_STRONG`" not in closure_text
    assert "| Discolock | `SOURCE_BACKED_STRONG`" not in closure_text
    assert "| TreantDruid | `SOURCE_BACKED_STRONG`" not in closure_text
    assert "| PirateDH | `SOURCE_BACKED_STRONG`" not in closure_text
