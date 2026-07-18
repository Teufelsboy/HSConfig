from __future__ import annotations

import json
from pathlib import Path

from hsconfig.source_candidate_registry import source_candidates_for_deck


PROOF_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "operator"
    / "source-candidate-proof-decks.json"
)


DECKS = {
    "ShadowPriest": "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
    "CtAPaladin": "AAEBAZ8FBowBwP0ChJYFzpwGprMGg8IHDIgO+NICg94DkeQDzusDyaAE4aQEwcQFhY4GmY4G9ZUGmvwHAAA=",
    "PirateRogue": "AAEBAaIHApG8AuXRAg6MAtQF+w/psAPz3QOvoASKyQSa2wTXowW/9wXWngb8pQb8qAatxQYAAA==",
    "BigShaman": "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==",
    "Discolock": "AAEBAf0GBM4Hj4ID8aEG9qEGDbW5A9XRA9DhA5iSBauSBZXKBteXB4SZB6StB8ayB9a+B9m+B8+/BwAA",
    "TreantDruid": "AAEBAZICAt/7ApOyBw7NuwLB8wL8rQP/rQOV4APs9QOvgASuwASy3QTO5AWw+gXZ/wXJ0Aat4gYAAA==",
    "ImbueMage": "AAEBAf0EBIUXm80DvO0Egb8GDcAB9KsD0+wD1uwDr8QForMG1voG3PoG9PwG94EHs4cHwIcH7o0HAAA=",
    "MechPala": "AAEBAZ8FAtS9BMekBg6f9QLW/gLX/gKHrgOStQThtQTa0wTZ0AW5/gWf4Qa08Qbi8Qa6lgea/AcAAQPzswbHpAb2swbHpAbu3gbHpAYAAA==",
    "Kingslayer": "AAEBAaIHBpG8ApKDB4aoB4eoB4ioB4jZBwyMAtQF6bAD1bYEiskE16MF7p4G/KUG/KgGs8EG6sQGrcUGAAA=",
    "Boarlock": "AAEBAf0GBuAF054G7qEGxKIG0YIHqYgHDJDHAvLQAp2pA5vNA9P5A6bqBPTGBYSeBpWzBpTKBoSZB4adBwAA",
    "PirateDH": "AAEBAea5AwaRvALUyAP51QOHiwTh+AX8wAYM+w/psAPyyQPltgSl4gSr4gSVqgX8qAbYwAb2wAatxQax6wYAAA==",
    "CuteWarrior": "AAEBAQcEkbwCkdAD69YHstgHDY0Q6bADpLYDxN4D/9sEj5UFlaoFtNEF9PIFovoF/KgGltMGtI8HAAA=",
}


EXPECTED_STRENGTH = {
    "ShadowPriest": "runtime_claims_possible",
    "CtAPaladin": "runtime_claims_possible",
    "PirateRogue": "candidate_partial",
    "BigShaman": "candidate_partial",
    "Discolock": "runtime_claims_possible",
    "TreantDruid": "runtime_claims_possible",
    "ImbueMage": "runtime_claims_possible",
    "MechPala": "candidate_partial",
    "Kingslayer": "candidate_partial",
    "Boarlock": "candidate_partial",
    "PirateDH": "runtime_claims_possible",
    "CuteWarrior": "candidate_partial",
}

EXPECTED_STRONG_PROMOTION_STATUS = {
    "ShadowPriest": "runtime_claims_possible_if_fetched_claims_close",
    "CtAPaladin": "runtime_claims_possible_if_fetched_claims_close",
    "PirateRogue": "partial_until_missing_source_action_closes",
    "BigShaman": "partial_until_missing_source_action_closes",
    "Discolock": "runtime_claims_possible_if_fetched_claims_close",
    "TreantDruid": "runtime_claims_possible_if_fetched_claims_close",
    "ImbueMage": "runtime_claims_possible_if_fetched_claims_close",
    "MechPala": "partial_until_missing_source_action_closes",
    "Kingslayer": "partial_until_missing_source_action_closes",
    "Boarlock": "partial_until_missing_source_action_closes",
    "PirateDH": "runtime_claims_possible_if_fetched_claims_close",
    "CuteWarrior": "partial_until_missing_source_action_closes",
}


def test_source_candidate_registry_covers_user_supplied_wild_decks():
    missing = [
        deck_name
        for deck_name, deck_code in DECKS.items()
        if not source_candidates_for_deck(deck_name, deck_code)
    ]

    assert missing == []


def test_candidate_strength_ceiling_is_explicit_for_every_user_deck():
    for deck_name, deck_code in DECKS.items():
        candidates = source_candidates_for_deck(deck_name, deck_code)
        assert candidates, deck_name
        assert candidates[0].strength_ceiling == EXPECTED_STRENGTH[deck_name]
        assert candidates[0].strength_ceiling in {
            "runtime_claims_possible",
            "candidate_partial",
            "context_only",
        }, deck_name
        assert candidates[0].first_missing_source_action, deck_name


def test_context_only_candidates_do_not_claim_none_missing_action():
    for deck_name, deck_code in DECKS.items():
        for candidate in source_candidates_for_deck(deck_name, deck_code):
            if candidate.strength_ceiling == "context_only":
                assert candidate.first_missing_source_action != "none", candidate.url
                assert candidate.expected_claim_kinds == (), candidate.url


def test_live_source_refresh_supplemental_candidates_are_registered():
    cta_candidates = {
        candidate.url: candidate for candidate in source_candidates_for_deck("CtAPaladin")
    }
    cta_url = (
        "https://www.reddit.com/r/wildhearthstone/comments/1qdrc06/"
        "the_xl_cta_paladin_experience/"
    )
    assert cta_url in cta_candidates
    assert cta_candidates[cta_url].strength_ceiling == "candidate_partial"
    assert cta_candidates[cta_url].first_missing_source_action != "none"

    treant_candidates = {
        candidate.url: candidate for candidate in source_candidates_for_deck("TreantDruid")
    }
    treant_url = (
        "https://www.reddit.com/r/CompetitiveHS/comments/1oty3l8/"
        "treant_druid_wild_legend_deck/"
    )
    assert treant_url in treant_candidates
    assert treant_candidates[treant_url].strength_ceiling == "candidate_partial"
    assert treant_candidates[treant_url].first_missing_source_action != "none"


def test_source_closure_wave_downgrades_overstated_support_sources():
    cta_candidates = {
        candidate.url: candidate
        for candidate in source_candidates_for_deck("CtAPaladin")
    }
    cta_old_discussion = cta_candidates[
        "https://www.reddit.com/r/wildhearthstone/comments/1jydz4q/"
        "i_dont_understand_how_cta_paladin_is_any_good/"
    ]
    assert cta_old_discussion.strength_ceiling == "candidate_partial"
    assert cta_old_discussion.first_missing_source_action == (
        "add_current_cta_paladin_mulligan_keep_source"
    )
    assert "mulligan_keep" not in cta_old_discussion.expected_claim_kinds

    discolock_candidates = {
        candidate.url: candidate
        for candidate in source_candidates_for_deck("Discolock")
    }
    discolock_advice = discolock_candidates[
        "https://www.reddit.com/r/wildhearthstone/comments/1nhpuu1/"
        "how_to_play_discolock/"
    ]
    assert discolock_advice.strength_ceiling == "candidate_partial"
    assert discolock_advice.first_missing_source_action == (
        "add_current_discolock_full_text_mulligan_or_gameplan_source"
    )

    big_shaman = source_candidates_for_deck("BigShaman")[0]
    assert big_shaman.strength_ceiling == "candidate_partial"
    assert big_shaman.first_missing_source_action == (
        "add_current_big_shaman_full_text_mulligan_or_gameplan_source"
    )

    pirate_dh = source_candidates_for_deck("PirateDH")[0]
    assert pirate_dh.publication_year == 2024
    assert pirate_dh.expected_strength == "guide_historical_archetype_match"


def test_source_candidate_proof_doc_matches_registry_expectations():
    proof = json.loads(
        Path("docs/operator/source-candidate-proof-decks.json").read_text(
            encoding="utf-8"
        )
    )
    rows = {row["deck_name"]: row for row in proof["decks"]}

    assert set(rows) == set(EXPECTED_STRENGTH)
    for deck_name, expected_strength in EXPECTED_STRENGTH.items():
        candidates = source_candidates_for_deck(deck_name, DECKS[deck_name])
        assert rows[deck_name]["expected_strength_ceiling"] == expected_strength
        assert rows[deck_name]["expected_runtime_generation_status"] == (
            "load_safe_no_default_only"
        )
        assert rows[deck_name]["expected_candidate_count_min"] >= 1
        assert rows[deck_name]["expected_candidate_count_min"] <= len(candidates)
        assert rows[deck_name]["first_missing_source_action"] == (
            candidates[0].first_missing_source_action
        )
        documented_urls = (
            rows[deck_name]["candidate_urls"]
            + rows[deck_name].get("support_seed_urls", [])
            + rows[deck_name].get("context_seed_urls", [])
        )
        assert documented_urls == [candidate.url for candidate in candidates]
        assert rows[deck_name]["expected_strong_promotion_status"] == (
            EXPECTED_STRONG_PROMOTION_STATUS[deck_name]
        )


def test_source_candidate_proof_rows_match_registry_contract():
    proof = json.loads(PROOF_PATH.read_text(encoding="utf-8"))

    assert proof["strongness_policy"].startswith("Candidate URLs are source acquisition seeds")

    for row in proof["decks"]:
        deck_name = row["deck_name"]
        candidates = source_candidates_for_deck(deck_name)
        urls = {candidate.url for candidate in candidates}
        expected_urls = set(row["candidate_urls"])
        support_seed_urls = set(row.get("support_seed_urls", []))
        context_seed_urls = set(row.get("context_seed_urls", []))

        assert len(candidates) >= row["expected_candidate_count_min"], deck_name
        assert expected_urls <= urls, deck_name
        assert support_seed_urls <= urls, deck_name
        assert context_seed_urls <= urls, deck_name
        assert {
            candidate.strength_ceiling for candidate in candidates
            if candidate.url in expected_urls
        } == {row["expected_strength_ceiling"]}, deck_name
        assert {
            candidate.strength_ceiling for candidate in candidates
            if candidate.url in support_seed_urls
        } <= {"candidate_partial", "context_only"}, deck_name
        assert {
            candidate.strength_ceiling for candidate in candidates
            if candidate.url in context_seed_urls
        } <= {"context_only"}, deck_name

        expected_action = row["first_missing_source_action"]
        matching_actions = {
            candidate.first_missing_source_action
            for candidate in candidates
            if candidate.url in expected_urls
        }
        assert matching_actions == {expected_action}, deck_name
        context_actions = {
            candidate.first_missing_source_action
            for candidate in candidates
            if candidate.url in context_seed_urls
        }
        assert "none" not in context_actions, deck_name


def test_context_only_candidates_cannot_declare_runtime_claim_kinds():
    for deck_name in ["MechPala", "Discolock", "Boarlock", "CuteWarrior"]:
        candidates = source_candidates_for_deck(deck_name)
        context_candidates = [
            candidate for candidate in candidates
            if candidate.strength_ceiling == "context_only"
        ]

        assert context_candidates
        assert all(candidate.expected_claim_kinds == () for candidate in context_candidates)
        assert all(candidate.first_missing_source_action != "none" for candidate in context_candidates)
