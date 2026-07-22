from __future__ import annotations

import pytest

from hsconfig.source_provenance import (
    normalize_source_provenance,
    research_payload_provenance,
)


DECK_IDENTITY = {
    "deck_name": "ShadowPriest",
    "deck_code_hash": "sha256:shadow",
    "deck_slug": "shadowpriest",
    "format": "wild",
    "cards": [
        {"card_id": "SW_448", "name": "Darkbishop Benedictus", "count": 1},
        {"card_id": "SW_446", "name": "Voidtouched Attendant", "count": 2},
    ],
}


def test_current_full_text_public_guide_projects_current_provenance() -> None:
    result = normalize_source_provenance(
        {
            "source_url": "https://example.test/shadow-guide",
            "source_title": "ShadowPriest Guide 2026",
            "source_family": "guide",
            "source_visibility": "full_text",
            "publication_year": 2026,
            "deck_match": {
                "deck_name": "ShadowPriest",
                "matched_card_ids": ["SW_448", "SW_446"],
            },
        },
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        current_date="2026-07-22",
    )

    assert result["source_visibility"] == "full_text"
    assert result["deck_identity_match"] is True
    assert result["deck_identity_match_basis"] == "deck_name_and_card_overlap"
    assert result["freshness_status"] == "current"
    assert result["current_or_evergreen"] is True
    assert result["current_or_evergreen_reason"] == "publication_year_matches_current_year"
    assert result["source_status_apply_blocking"] is False


def test_evergreen_wild_requires_wild_scope_and_card_overlap() -> None:
    result = normalize_source_provenance(
        {
            "source_url": "https://example.test/evergreen-shadow",
            "source_title": "Evergreen Wild Shadow Priest Guide",
            "source_family": "guide",
            "source_visibility": "full_text",
            "publication_year": 2023,
            "format_scope": "wild",
            "deck_match": {
                "deck_name": "ShadowPriest",
                "matched_card_ids": ["SW_448", "SW_446"],
            },
        },
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        current_date="2026-07-22",
    )

    assert result["freshness_status"] == "evergreen"
    assert result["current_or_evergreen"] is True
    assert result["current_or_evergreen_reason"] == "wild_guide_with_card_overlap"


def test_decklist_only_is_visible_but_never_current_guide_provenance() -> None:
    result = normalize_source_provenance(
        {
            "source_url": "https://example.test/decklist",
            "source_family": "decklist_only",
            "deck_match": {
                "deck_name": "ShadowPriest",
                "matched_card_ids": ["SW_448", "SW_446"],
            },
        },
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        current_date="2026-07-22",
    )

    assert result["source_visibility"] == "decklist_only"
    assert result["deck_identity_match"] is True
    assert result["freshness_status"] == "not_strategy_guide"
    assert result["current_or_evergreen"] is False
    assert result["current_or_evergreen_reason"] == "decklist_not_strategy_guide"
    assert result["source_status_apply_blocking"] is False


def test_unrelated_matched_cards_do_not_establish_deck_identity_match() -> None:
    result = normalize_source_provenance(
        {
            "source_family": "guide",
            "source_visibility": "full_text",
            "deck_match": {
                "deck_name": "OtherDeck",
                "matched_card_ids": ["OTHER_001", "OTHER_002"],
            },
        },
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        current_date="2026-07-22",
    )

    assert result["deck_identity_match"] is False
    assert result["deck_identity_match_basis"] == "no_identity_match"


def test_unrelated_wild_cards_do_not_establish_evergreen_provenance() -> None:
    result = normalize_source_provenance(
        {
            "source_family": "guide",
            "source_visibility": "full_text",
            "publication_year": 2023,
            "format_scope": "wild",
            "deck_match": {
                "deck_name": "OtherDeck",
                "matched_card_ids": ["OTHER_001", "OTHER_002"],
            },
        },
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        current_date="2026-07-22",
    )

    assert result["freshness_status"] == "stale"
    assert result["current_or_evergreen"] is False
    assert result["source_status_apply_blocking"] is False


def test_research_payload_provenance_accepts_nested_current_marker() -> None:
    result = research_payload_provenance(
        {
            "source_strength": "exact_full_text_guide",
            "source_visibility": "full_text",
            "guide_sources": [
                {
                    "source_freshness_lane": "guide_current_deck_match",
                    "current_or_evergreen_reason": "publication_year_matches_current_year",
                }
            ],
        }
    )

    assert result["freshness_status"] == "current"
    assert result["current_or_evergreen"] is True
    assert result["current_or_evergreen_reason"] == "publication_year_matches_current_year"
    assert result["source_status_apply_blocking"] is False


@pytest.mark.parametrize(
    ("payload", "freshness_status"),
    [
        ({"source_freshness": "current"}, "current"),
        ({"currency_status": "evergreen"}, "evergreen"),
        (
            {"guide_sources": [{"source_freshness": "current"}]},
            "current",
        ),
        (
            {"guide_sources": [{"currency_status": "evergreen"}]},
            "evergreen",
        ),
    ],
)
def test_research_payload_provenance_keeps_source_freshness_and_currency_compatibility(
    payload: dict[str, object], freshness_status: str
) -> None:
    result = research_payload_provenance(payload)

    assert result["freshness_status"] == freshness_status
    assert result["current_or_evergreen"] is True
    assert result["source_status_apply_blocking"] is False


@pytest.mark.parametrize(
    ("lane_key", "lane"),
    [
        ("source_freshness_lane", "guide_current_deck_match"),
        ("source_freshness_lane", "current"),
        ("source_rank_lane", "guide_current_deck_match"),
    ],
)
def test_research_payload_provenance_accepts_top_level_current_lane(
    lane_key: str,
    lane: str,
) -> None:
    result = research_payload_provenance({lane_key: lane})

    assert result["freshness_status"] == "current"
    assert result["current_or_evergreen"] is True
    assert result["source_status_apply_blocking"] is False


@pytest.mark.parametrize(
    "lane",
    ["guide_evergreen_wild_archetype", "evergreen_wild_archetype"],
)
def test_research_payload_provenance_accepts_top_level_evergreen_lane(
    lane: str,
) -> None:
    result = research_payload_provenance({"source_freshness_lane": lane})

    assert result["freshness_status"] == "evergreen"
    assert result["current_or_evergreen"] is True
    assert result["source_status_apply_blocking"] is False


def test_research_payload_provenance_reports_explicit_stale_top_level_lane() -> None:
    result = research_payload_provenance(
        {"source_freshness_lane": "stale_unproven_for_2026"}
    )

    assert result["freshness_status"] == "stale"
    assert result["current_or_evergreen"] is False
    assert result["current_or_evergreen_reason"] != "missing_current_or_evergreen_marker"
    assert result["source_status_apply_blocking"] is False
