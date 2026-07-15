import json
from pathlib import Path


MATRIX_PATH = Path("docs/operator/archetype-fixture-matrix.json")
EXPECTED_DECKS = {
    "ShadowPriest",
    "CtAPaladin",
    "PirateRogue",
    "BigShaman",
    "Discolock",
    "TreantDruid",
    "ImbueMage",
    "MechPala",
    "Kingslayer",
    "Boarlock",
    "PirateDH",
}
CORE_FIXTURES = {
    "BigShaman",
    "ImbueMage",
    "MechPala",
    "PirateRogue",
    "ShadowPriest",
}
SOURCE_INFORMED_VALID_FIXTURES = EXPECTED_DECKS - CORE_FIXTURES
EXPECTED_STRONGNESS_GAPS = {
    "ShadowPriest": "none",
    "CtAPaladin": "needs_explicit_mulligan_source",
    "PirateRogue": "none",
    "BigShaman": "none",
    "Discolock": "needs_explicit_mulligan_source",
    "TreantDruid": "needs_card_specific_source_claim",
    "ImbueMage": "none",
    "MechPala": "none",
    "Kingslayer": "needs_mulligan_claim_for_quick_pick",
    "Boarlock": "needs_mulligan_claim_for_fracking",
    "PirateDH": "needs_card_specific_source_claim",
}
EXPECTED_FIRST_MISSING_SOURCE_ACTIONS = {
    "ShadowPriest": "none",
    "CtAPaladin": "add_current_cta_paladin_mulligan_keep_source",
    "PirateRogue": "none",
    "BigShaman": "none",
    "Discolock": "add_current_discolock_mulligan_keep_source",
    "TreantDruid": "add_treant_card_role_or_mulligan_source",
    "ImbueMage": "none",
    "MechPala": "none",
    "Kingslayer": "add_quick_pick_mulligan_keep_or_discard_source",
    "Boarlock": "add_fracking_mulligan_keep_or_discard_source",
    "PirateDH": "add_pirate_dh_card_role_or_mulligan_source",
}
EXPECTED_SOURCE_INFORMED_VISIBILITY = {
    "CtAPaladin": {
        "operator_action": "preserve_source_informed_with_evidence_gap",
        "source_informed_blocking_reasons": ["policy_claim_not_strong_evidence"],
        "stop_condition": None,
    },
    "Discolock": {
        "operator_action": "preserve_source_informed_with_evidence_gap",
        "source_informed_blocking_reasons": [
            "policy_claim_not_strong_evidence",
            "source_evidence_warnings",
        ],
        "stop_condition": None,
    },
    "TreantDruid": {
        "operator_action": "preserve_source_informed_with_evidence_gap",
        "source_informed_blocking_reasons": [
            "generic_low_confidence_cards",
            "generic_low_confidence_not_strong_evidence",
            "policy_claim_not_strong_evidence",
            "source_evidence_warnings",
            "uncovered_cards",
        ],
        "stop_condition": None,
    },
    "Kingslayer": {
        "operator_action": "preserve_source_informed_with_explicit_stop_condition",
        "source_informed_blocking_reasons": ["unsupported_conditions_present"],
        "stop_condition": "exact_kingslayer_quick_pick_mulligan_source_unavailable",
    },
    "Boarlock": {
        "operator_action": "preserve_source_informed_with_explicit_stop_condition",
        "source_informed_blocking_reasons": ["unsupported_conditions_present"],
        "stop_condition": "exact_boarlock_fracking_mulligan_source_unavailable",
    },
    "PirateDH": {
        "operator_action": "preserve_source_informed_with_evidence_gap",
        "source_informed_blocking_reasons": [
            "generic_low_confidence_cards",
            "generic_low_confidence_not_strong_evidence",
            "source_evidence_warnings",
            "uncovered_cards",
        ],
        "stop_condition": None,
    },
}
EXPECTED_DECK_IDENTITIES = {
    "ShadowPriest": {
        "deck_code": "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
        "hs_id": "2737726722",
        "hdt_deck_id": "c4c8b6b9-1d8e-4c07-a6cd-1c0de84f7602",
    },
    "CtAPaladin": {
        "deck_code": "AAEBAZ8FBowBwP0ChJYFzpwGprMGg8IHDIgO+NICg94DkeQDzusDyaAE4aQEwcQFhY4GmY4G9ZUGmvwHAAA=",
        "hs_id": "2737744316",
        "hdt_deck_id": "f9b54950-ca24-48cf-805e-bf620eab47a0",
    },
    "PirateRogue": {
        "deck_code": "AAEBAaIHApG8AuXRAg6MAtQF+w/psAPz3QOvoASKyQSa2wTXowW/9wXWngb8pQb8qAatxQYAAA==",
        "hs_id": "2740734095",
        "hdt_deck_id": "c1e87d43-5802-460b-b955-31ae458eb41a",
    },
    "BigShaman": {
        "deck_code": "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==",
        "hs_id": "2737735409",
        "hdt_deck_id": "6b26f907-6f1e-44c8-a4e4-d14e9d51f819",
    },
    "Discolock": {
        "deck_code": "AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA",
        "hs_id": "2740357533",
        "hdt_deck_id": "55241397-ac74-4d46-a662-089e5858839c",
    },
    "TreantDruid": {
        "deck_code": "AAEBAZICAt/7ApOyBw7NuwLB8wL8rQP/rQOV4APs9QOvgASuwASy3QTO5AWw+gXZ/wXJ0Aat4gYAAA==",
        "hs_id": "2740360895",
        "hdt_deck_id": "a120a28b-1840-4032-a3c9-2da4c51338ed",
    },
    "ImbueMage": {
        "deck_code": "AAEBAf0EBIUXm80DvO0Egb8GDcAB9KsD0+wD1uwDr8QForMG1voG3PoG9PwG94EHs4cHwIcH7o0HAAA=",
        "hs_id": "2740361888",
        "hdt_deck_id": "49c05560-8b30-4d06-b3a2-a8b0ff36d005",
    },
    "MechPala": {
        "deck_code": "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA==",
        "hs_id": "2740734214",
        "hdt_deck_id": "8f011f55-8ae2-436c-b53a-315f280e8833",
    },
    "Kingslayer": {
        "deck_code": "AAEBAaIHBpG8ApKDB4aoB4eoB4ioB4jZBwyMAtQF6bAD1bYEiskE16MF7p4G/KUG/KgGs8EG6sQGrcUGAAA=",
        "hs_id": "2740733989",
        "hdt_deck_id": "1292ff02-8ebe-47a5-90b1-9a1899acd6aa",
    },
    "Boarlock": {
        "deck_code": "AAEBAf0GBuAF054G7qEGxKIG0YIHqYgHDJDHAvLQAp2pA5vNA9P5A6bqBPTGBYSeBpWzBpTKBoSZB4adBwAA",
        "hs_id": "2740361505",
        "hdt_deck_id": "7727c718-c93c-47ca-a766-5612c3806f0f",
    },
    "PirateDH": {
        "deck_code": "AAEBAea5AwaRvALUyAP51QOHiwTh+AX8wAYM+w/psAPyyQPltgSl4gSr4gSVqgX8qAbYwAb2wAatxQax6wYAAA==",
        "hs_id": "2737737281",
        "hdt_deck_id": "2bc184ed-b59a-4420-900d-b0ed3d153979",
    },
}


def _matrix():
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def test_archetype_fixture_matrix_covers_supplied_decks():
    matrix = _matrix()
    assert matrix["schema_version"] == 1
    decks = {row["deck_name"] for row in matrix["decks"]}
    assert decks == EXPECTED_DECKS


def test_archetype_fixture_matrix_has_actionable_rows():
    for row in _matrix()["decks"]:
        assert row["deck_code"]
        assert row["hs_id"]
        assert row["hdt_deck_id"]
        assert row["archetype_bucket"]
        assert row["primary_mechanics"]
        assert "GlobalValues.json" in row["expected_runtime_surfaces"]
        assert "Mulligan.json" in row["expected_runtime_surfaces"]
        assert "<CARDID>.json" in row["expected_runtime_surfaces"]
        assert row["runtime_apply_allowed"] is True
        assert row["default_only_runtime_surfaces"] == []
        assert row["fixture_stage"] in {
            "core_source_backed_fixture",
            "source_informed_valid_fixture",
            "future_fixture",
        }
        assert row["expected_semantic_status"] in {
            "SOURCE_BACKED_STRONG",
            "SOURCE_BACKED_PARTIAL",
        }
        assert row.get("first_missing_source_action", "none") == (
            EXPECTED_FIRST_MISSING_SOURCE_ACTIONS[row["deck_name"]]
        )
        if row["fixture_stage"] == "core_source_backed_fixture":
            assert row["expected_semantic_status"] == "SOURCE_BACKED_STRONG"
        elif row["fixture_stage"] == "source_informed_valid_fixture":
            assert row["expected_semantic_status"] == "SOURCE_BACKED_PARTIAL"


def test_archetype_fixture_matrix_uses_supplied_deck_identities():
    for row in _matrix()["decks"]:
        identity = EXPECTED_DECK_IDENTITIES[row["deck_name"]]
        for field in ("deck_code", "hs_id", "hdt_deck_id"):
            assert row[field] == identity[field]
            assert not row[field].startswith("fixture-local")
            assert "fixture-local" not in row[field]


def test_archetype_fixture_matrix_marks_core_wave():
    core = {
        row["deck_name"]
        for row in _matrix()["decks"]
        if row["fixture_stage"] == "core_source_backed_fixture"
    }
    assert core == CORE_FIXTURES


def test_archetype_fixture_matrix_marks_source_informed_valid_wave():
    source_informed = {
        row["deck_name"]
        for row in _matrix()["decks"]
        if row["fixture_stage"] == "source_informed_valid_fixture"
    }
    assert source_informed == SOURCE_INFORMED_VALID_FIXTURES


def test_each_fixture_row_documents_decision_family_and_limits():
    matrix = _matrix()

    expected_families = {
        "ShadowPriest": {"aggro_burn_targeting", "hero_power_transform"},
        "CtAPaladin": {"recruit_board_flood", "aura_pressure"},
        "PirateRogue": {"pirate_tempo", "weapon_pressure"},
        "BigShaman": {"big_minion_cheat", "recruit", "deathrattle"},
        "Discolock": {"discard_payoff", "hand_mutation"},
        "TreantDruid": {"token_board", "board_buff"},
        "ImbueMage": {"hero_power", "spell_generation"},
        "MechPala": {"mech_board_scaling", "magnetic"},
        "Kingslayer": {"weapon_sequence", "attack_pressure"},
        "Boarlock": {"combo_control", "resource_setup"},
        "PirateDH": {"pirate_tempo", "hero_attack"},
    }

    for deck in matrix["decks"]:
        deck_name = deck["deck_name"]
        families = set(deck.get("decision_families_proven", []))
        assert families >= expected_families[deck_name]
        assert deck.get("known_coverage_limits"), deck_name
        assert all(isinstance(item, str) and item for item in deck["known_coverage_limits"])


def test_each_fixture_row_documents_strongness_visibility():
    for row in _matrix()["decks"]:
        deck_name = row["deck_name"]
        visibility = row["strongness_visibility"]
        assert visibility["current_stage"] == row["fixture_stage"]
        assert visibility["first_strongness_gap"] == EXPECTED_STRONGNESS_GAPS[deck_name]
        if row["fixture_stage"] == "core_source_backed_fixture":
            assert visibility["operator_action"] == "keep_as_core_control_fixture"
            assert visibility.get("stop_condition") is None
        else:
            expected = EXPECTED_SOURCE_INFORMED_VISIBILITY[deck_name]
            assert visibility["operator_action"] == expected["operator_action"]
            assert (
                visibility["source_informed_blocking_reasons"]
                == expected["source_informed_blocking_reasons"]
            )
            assert visibility.get("stop_condition") == expected["stop_condition"]
