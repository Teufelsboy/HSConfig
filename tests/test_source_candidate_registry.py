from __future__ import annotations

from hsconfig.source_candidate_registry import source_candidates_for_deck


def test_source_candidate_registry_returns_shadowpriest_current_guide():
    candidates = source_candidates_for_deck(
        "ShadowPriest",
        "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
    )

    assert candidates
    first = candidates[0]
    assert first.url == "https://www.hearthpwn.com/decks/1461644-voidburn-wild-aggro-shadow-priest"
    assert first.source_family == "guide"
    assert first.priority == 10
    assert first.expected_strength == "guide_current_deck_match"
    assert first.format_scope == "wild"
    assert first.strength_ceiling == "runtime_claims_possible"
    assert "archetype" in first.expected_claim_kinds


def test_source_candidate_registry_marks_bigshaman_as_evergreen_wild_archetype():
    candidates = source_candidates_for_deck(
        "BigShaman",
        "AAEBAaoIBpQD5LcDv84E9qMGgbgGmvYGDM4P0hP2vQKPlAPW9QO8tgT08gXqmAbGpgakpwb44gas/QYAAA==",
    )

    assert candidates
    assert candidates[0].url == "https://www.hearthpwn.com/decks/1186371-big-shaman-in-depth-guide"
    assert candidates[0].expected_strength == "guide_evergreen_wild_archetype"
    assert candidates[0].evergreen_wild_archetype is True


def test_source_candidate_registry_is_empty_for_unknown_decks():
    assert source_candidates_for_deck("UnknownDeck", "AAEBA-placeholder") == []


def test_source_candidate_metadata_is_seed_not_authority():
    candidates = source_candidates_for_deck(
        "ShadowPriest",
        "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
    )

    assert candidates
    first = candidates[0]
    assert first.source_visibility in {"full_text", "decklist_only", "snippet_only"}
    assert first.strength_ceiling in {
        "runtime_claims_possible",
        "candidate_partial",
        "context_only",
    }
    assert isinstance(first.expected_claim_kinds, tuple)
    assert "mulligan_keep" in first.expected_claim_kinds
    assert first.first_missing_source_action == "none"


def test_context_index_pages_are_registry_seeds_not_runtime_authority():
    warlock_context_urls = {
        candidate.url
        for deck_name in ("Discolock", "Boarlock")
        for candidate in source_candidates_for_deck(deck_name)
        if candidate.strength_ceiling == "context_only"
    }
    warrior_context_urls = {
        candidate.url
        for candidate in source_candidates_for_deck("CuteWarrior")
        if candidate.strength_ceiling == "context_only"
    }

    assert warlock_context_urls == {
        "https://hearthstone-decks.net/wild-decks/warlock-wild-decks/"
    }
    assert warrior_context_urls == {
        "https://hearthstone-decks.net/wild-decks/warrior-wild-decks/"
    }
