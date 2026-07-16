import pytest

from hsconfig.source_text_claim_extractor import extract_text_claims


def _shadow_identity():
    return {
        "cards": [
            {
                "card_id": "SW_448",
                "name": "Darkbishop Benedictus",
                "cost": 5,
                "text": "Start of Game: If the spells in your deck are all Shadow, enter Shadowform.",
            },
            {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "text": ""},
            {"card_id": "SCH_514", "name": "Raise Dead", "cost": 0, "text": ""},
        ]
    }


def test_extracts_explicit_mulligan_keep_without_darkbishop_false_keep():
    source = {
        "source_url": "https://example.test/guide",
        "source_title": "Wild ShadowPriest Guide",
        "source_family": "guide",
        "source_visibility": "full_text",
        "source_lane": "deck_matched_public_guide",
        "source_rank_lane": "guide_current_deck_match",
        "publication_year": 2026,
        "deck_match": {"deck_name": "ShadowPriest", "matched_card_ids": ["SW_448", "TOY_381"]},
        "normalized_text": (
            "Mulligan: keep Papercraft Angel. "
            "Do not keep any 4-cost or higher card. "
            "Darkbishop Benedictus changes your hero power into Mind Spike at the start of the game."
        ),
        "source_record_strength": "candidate_strong",
    }

    claims = extract_text_claims(
        deck_name="ShadowPriest",
        deck_identity=_shadow_identity(),
        source_record=source,
        current_date="2026-07-16",
    )

    keep_cards = {
        card_id
        for claim in claims
        if claim["claim_kind"] == "mulligan_keep"
        for card_id in claim["cards"]
    }
    discard_cards = {
        card_id
        for claim in claims
        if claim["claim_kind"] == "mulligan_discard"
        for card_id in claim["cards"]
    }
    transform_cards = {
        card_id
        for claim in claims
        if claim["claim_kind"] == "hero_power_transform"
        for card_id in claim["cards"]
    }

    assert keep_cards == {"TOY_381"}
    assert "SW_448" in discard_cards
    assert transform_cards == {"SW_448"}


def test_decklist_only_source_extracts_no_runtime_claims():
    source = {
        "source_url": "https://example.test/decklist",
        "source_title": "Mech Paladin Decklist",
        "source_family": "decklist",
        "source_visibility": "decklist_only",
        "source_lane": "deck_matched_public_guide",
        "source_rank_lane": "guide_current_deck_match",
        "publication_year": 2026,
        "deck_match": {"deck_name": "MechPala", "matched_card_ids": ["CARD_1"]},
        "source_record_strength": "candidate_strong",
        "normalized_text": "Mulligan: keep Mech. Darkbishop Benedictus changes your hero power into Shadowform.",
    }

    assert extract_text_claims(
        deck_name="MechPala",
        deck_identity={"cards": [{"card_id": "CARD_1", "name": "Mech", "cost": 1}]},
        source_record=source,
        current_date="2026-07-16",
    ) == []


def test_stats_and_snippet_only_sources_extract_no_runtime_claims():
    for visibility in ("stats_only", "snippet_only"):
        source = {
            "source_family": "guide",
            "source_visibility": visibility,
            "source_lane": "deck_matched_public_guide",
            "source_rank_lane": "guide_current_deck_match",
            "publication_year": 2026,
            "deck_match": {"deck_name": "ShadowPriest", "matched_card_ids": ["SW_448", "TOY_381"]},
            "source_record_strength": "candidate_strong",
            "normalized_text": (
                "Mulligan: keep Papercraft Angel. "
                "Darkbishop Benedictus changes your hero power into Shadowform."
            ),
        }

        assert extract_text_claims(
            deck_name="ShadowPriest",
            deck_identity=_shadow_identity(),
            source_record=source,
            current_date="2026-07-16",
        ) == []


@pytest.mark.parametrize("source_record_strength", ["candidate_only", "candidate_partial"])
def test_non_strong_source_records_extract_no_runtime_claims(source_record_strength):
    source = {
        "source_url": "https://example.test/candidate",
        "source_title": "Candidate Guide",
        "source_family": "guide",
        "source_visibility": "full_text",
        "source_lane": "deck_matched_public_guide",
        "source_rank_lane": "guide_current_deck_match",
        "normalized_text": (
            "Mulligan: keep Papercraft Angel. "
            "Darkbishop Benedictus changes your hero power into Mind Spike at the start of the game."
        ),
        "source_record_strength": source_record_strength,
    }

    assert extract_text_claims(
        deck_name="ShadowPriest",
        deck_identity=_shadow_identity(),
        source_record=source,
        current_date="2026-07-16",
    ) == []


def test_disjoint_card_and_hero_power_mentions_do_not_create_transform_claim():
    source = {
        "source_url": "https://example.test/disjoint",
        "source_title": "Unrelated Guide",
        "source_family": "guide",
        "source_visibility": "full_text",
        "source_lane": "deck_matched_public_guide",
        "source_rank_lane": "guide_current_deck_match",
        "normalized_text": (
            "Darkbishop Benedictus is in the deck. Mind Spike is effective. "
            "Start of Game effects are checked before turn one."
        ),
        "source_record_strength": "candidate_strong",
    }

    claims = extract_text_claims(
        deck_name="ShadowPriest",
        deck_identity=_shadow_identity(),
        source_record=source,
        current_date="2026-07-16",
    )

    assert not any(claim["claim_kind"] == "hero_power_transform" for claim in claims)


def test_same_sentence_disjoint_clauses_do_not_create_transform_claim():
    source = {
        "source_url": "https://example.test/disjoint-clauses",
        "source_title": "Unrelated Guide",
        "source_family": "guide",
        "source_visibility": "full_text",
        "source_lane": "deck_matched_public_guide",
        "source_rank_lane": "guide_current_deck_match",
        "normalized_text": (
            "Darkbishop Benedictus changes the matchup; Mind Spike is the hero power to use."
        ),
        "source_record_strength": "candidate_strong",
    }

    claims = extract_text_claims(
        deck_name="ShadowPriest",
        deck_identity=_shadow_identity(),
        source_record=source,
        current_date="2026-07-16",
    )

    assert not any(claim["claim_kind"] == "hero_power_transform" for claim in claims)


def test_hero_power_strategy_is_not_a_direct_transform_claim():
    source = {
        "source_family": "guide",
        "source_visibility": "full_text",
        "source_lane": "deck_matched_public_guide",
        "source_rank_lane": "guide_current_deck_match",
        "publication_year": 2026,
        "deck_match": {"deck_name": "ShadowPriest", "matched_card_ids": ["SW_448"]},
        "source_record_strength": "candidate_strong",
        "normalized_text": "Darkbishop Benedictus changes your hero power strategy.",
    }

    claims = extract_text_claims(
        deck_name="ShadowPriest",
        deck_identity=_shadow_identity(),
        source_record=source,
        current_date="2026-07-16",
    )

    assert not any(claim["claim_kind"] == "hero_power_transform" for claim in claims)


def test_direct_shadowform_wording_creates_transform_claim():
    source = {
        "source_family": "guide",
        "source_visibility": "full_text",
        "source_lane": "deck_matched_public_guide",
        "source_rank_lane": "guide_current_deck_match",
        "publication_year": 2026,
        "deck_match": {"deck_name": "ShadowPriest", "matched_card_ids": ["SW_448"]},
        "source_record_strength": "candidate_strong",
        "normalized_text": "Darkbishop Benedictus changes your hero power into Shadowform.",
    }

    claims = extract_text_claims(
        deck_name="ShadowPriest",
        deck_identity=_shadow_identity(),
        source_record=source,
        current_date="2026-07-16",
    )

    assert [claim["claim_kind"] for claim in claims] == ["hero_power_transform"]
    assert claims[0]["cards"] == ["SW_448"]
