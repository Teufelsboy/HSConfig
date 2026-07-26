from __future__ import annotations

from hsconfig.source_acquisition import collect_public_source_records


def _fetcher(url: str, timeout_seconds: float) -> tuple[int, str, bytes]:
    del timeout_seconds
    pages = {
        "https://example.test/shadow-guide": (
            "<html><head><meta property=\"article:published_time\" content=\"2026-07-15T00:00:00Z\">"
            "<title>Shadow Priest Guide 2026</title></head>"
            "<body><h1>Shadow Priest Mulligan Guide</h1>"
            "<p>Published July 15, 2026.</p>"
            "<p>Mulligan: Keep Papercraft Angel, Twilight Deceptor, Raise Dead, and Shadowbomber.</p>"
            "<p>Darkbishop Benedictus enables the Shadow hero power. Mind Spike can go face or clear minions.</p>"
            "</body></html>"
        ),
        "https://example.test/decklist-only": (
            "<html><head><title>Wild Pirate Demon Hunter Decklist</title></head>"
            "<body><p>Deck code: AAEBA-example</p><ul><li>Patches the Pirate</li></ul></body></html>"
        ),
        "https://example.test/snippet": "<html><body><p>Shadow Priest list.</p></body></html>",
        "https://example.test/multi-year-guide": (
            "<html><head><meta property=\"article:published_time\" content=\"2026-07-15T00:00:00Z\">"
            "<title>Shadow Priest Guide 2026</title></head>"
            "<body><p>Originally tested in 2024.</p>"
            "<p>Updated July 15, 2026.</p>"
            "<p>Mulligan: Keep Papercraft Angel.</p>"
            "<p>This current Wild guide explains the opening turns, pressure plan, "
            "hero power usage, matchup posture, and exact mulligan priorities for "
            "the current Shadow Priest deck.</p>"
            "</body></html>"
        ),
        "https://example.test/stale-guide": (
            "<html><head><meta property=\"article:published_time\" content=\"2025-07-15T00:00:00Z\">"
            "<title>Shadow Priest Mulligan Guide 2025</title></head>"
            "<body><p>Published July 15, 2025.</p>"
            "<p>Mulligan: Keep Papercraft Angel.</p>"
            "<p>This full current-looking guide explains opening turns, matchup posture, "
            "hero power usage, pressure planning, and detailed mulligan priorities.</p>"
            "</body></html>"
        ),
    }
    return 200, "text/html", pages[url].encode("utf-8")


def _resolver(hostname: str) -> list[str]:
    assert hostname == "example.test"
    return ["93.184.216.34"]


def test_acquisition_marks_full_text_guides_as_candidate_strong():
    deck_identity = {
        "deck_name": "ShadowPriest",
        "deck_slug": "shadowpriest",
        "deck_code_hash": "sha256:shadow",
        "cards": [
            {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2},
            {"card_id": "SW_444", "name": "Twilight Deceptor", "cost": 2, "count": 2},
            {"card_id": "SCH_514", "name": "Raise Dead", "cost": 0, "count": 2},
            {"card_id": "GVG_009", "name": "Shadowbomber", "cost": 1, "count": 2},
            {"card_id": "SW_448", "name": "Darkbishop Benedictus", "cost": 5, "count": 1},
        ],
    }

    payload = collect_public_source_records(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        source_urls=["https://example.test/shadow-guide"],
        current_date="2026-07-15",
        fetcher=_fetcher,
        resolver=_resolver,
    )

    record = payload["source_records"][0]
    assert record["source_visibility"] == "full_text"
    assert record["source_lane_hint"] == "public_guide"
    assert record["source_category"] == "public_guide"
    assert record["source_document_kind"] == "guide"
    assert record["publication_year"] == 2026
    assert record["source_record_strength"] == "partial"
    assert record["source_strength"] == "partial"
    assert record["strong_promotion_eligible"] is False
    assert record["first_missing_source_action"] == "add_exact_deck_matched_source"


def test_acquisition_marks_decklist_and_snippets_non_promoting():
    deck_identity = {
        "deck_name": "PirateDH",
        "deck_slug": "piratedh",
        "deck_code_hash": "sha256:pirate",
        "cards": [{"card_id": "CARD_001", "name": "Patches the Pirate", "cost": 1, "count": 1}],
    }

    payload = collect_public_source_records(
        deck_name="PirateDH",
        deck_identity=deck_identity,
        source_urls=["https://example.test/decklist-only", "https://example.test/snippet"],
        current_date="2026-07-15",
        fetcher=_fetcher,
        resolver=_resolver,
    )

    by_url = {record["source_url"]: record for record in payload["source_records"]}
    assert by_url["https://example.test/decklist-only"]["source_visibility"] == "decklist_only"
    assert by_url["https://example.test/decklist-only"]["source_record_strength"] == "partial"
    assert by_url["https://example.test/decklist-only"]["source_category"] == "decklist"
    assert by_url["https://example.test/decklist-only"]["source_document_kind"] == "decklist"
    assert by_url["https://example.test/decklist-only"]["source_strength"] == "partial"
    assert by_url["https://example.test/decklist-only"]["strong_promotion_eligible"] is False
    assert by_url["https://example.test/decklist-only"]["first_missing_source_action"] != "none"
    assert by_url["https://example.test/snippet"]["source_visibility"] == "snippet_only"
    assert by_url["https://example.test/snippet"]["source_record_strength"] == "diagnostic_only"
    assert by_url["https://example.test/snippet"]["source_category"] == "diagnostic"
    assert by_url["https://example.test/snippet"]["source_document_kind"] == "snippet"
    assert by_url["https://example.test/snippet"]["source_strength"] == "diagnostic_only"
    assert by_url["https://example.test/snippet"]["strong_promotion_eligible"] is False


def test_acquisition_report_uses_first_missing_action_from_non_strong_records():
    deck_identity = {
        "deck_name": "ShadowPriest",
        "deck_slug": "shadowpriest",
        "deck_code_hash": "sha256:shadow",
        "cards": [
            {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2},
            {"card_id": "CARD_001", "name": "Patches the Pirate", "cost": 1, "count": 1},
        ],
    }

    payload = collect_public_source_records(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        source_urls=[
            "https://example.test/decklist-only",
            "https://example.test/snippet",
            "https://example.test/stale-guide",
        ],
        current_date="2026-07-15",
        fetcher=_fetcher,
        resolver=_resolver,
    )

    records = payload["source_records"]
    assert [record["source_document_kind"] for record in records] == [
        "decklist",
        "snippet",
        "guide",
    ]
    assert {record["strong_promotion_eligible"] for record in records} == {False}
    missing_actions = [
        record["first_missing_source_action"]
        for record in records
        if record["first_missing_source_action"] != "none"
    ]
    assert missing_actions
    assert payload["source_acquisition_report"]["first_missing_source_action"] == missing_actions[0]


def test_acquisition_prefers_current_publication_year_over_older_history():
    deck_identity = {
        "deck_name": "ShadowPriest",
        "deck_slug": "shadowpriest",
        "deck_code_hash": "sha256:shadow",
        "cards": [{"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2}],
    }

    payload = collect_public_source_records(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        source_urls=["https://example.test/multi-year-guide"],
        current_date="2026-07-15",
        fetcher=_fetcher,
        resolver=_resolver,
    )

    record = payload["source_records"][0]
    assert record["publication_year"] == 2026
    assert record["source_record_strength"] == "partial"


def test_acquisition_policy_fields_make_stale_guides_non_strong():
    deck_identity = {
        "deck_name": "ShadowPriest",
        "deck_slug": "shadowpriest",
        "deck_code_hash": "sha256:shadow",
        "cards": [{"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2}],
    }

    payload = collect_public_source_records(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        source_urls=["https://example.test/stale-guide"],
        current_date="2026-07-15",
        fetcher=_fetcher,
        resolver=_resolver,
    )

    record = payload["source_records"][0]
    assert record["source_visibility"] == "full_text"
    assert record["publication_year"] == 2025
    assert record["source_freshness_lane"] == "stale_or_not_current"
    assert record["source_rank_lane"] == "guide_full_text_not_current"
    assert record["strong_promotion_eligible"] is False
    assert "source_not_current_or_evergreen_wild" in record["promotion_blockers"]
    assert record["first_missing_source_action"] == "add_current_or_evergreen_wild_public_guide"
