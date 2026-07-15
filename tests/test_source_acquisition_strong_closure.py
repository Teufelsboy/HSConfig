from __future__ import annotations

from hsconfig.source_acquisition import collect_public_source_records


def _fetcher(url: str, timeout_seconds: float) -> tuple[int, str, bytes]:
    del timeout_seconds
    pages = {
        "https://example.test/shadow-guide": (
            "<html><head><title>Shadow Priest Guide 2026</title></head>"
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
    assert record["publication_year"] == 2026
    assert record["source_record_strength"] == "candidate_strong"


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
    assert by_url["https://example.test/snippet"]["source_visibility"] == "snippet_only"
    assert by_url["https://example.test/snippet"]["source_record_strength"] == "diagnostic_only"
