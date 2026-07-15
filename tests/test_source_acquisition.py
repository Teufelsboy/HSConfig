from __future__ import annotations

from pathlib import Path

from hsconfig.source_acquisition import collect_public_source_records, extract_visible_text


FIXTURES = Path(__file__).parent / "fixtures" / "source_pages"


def _fake_fetcher(url: str, timeout_seconds: float) -> tuple[int, str, bytes]:
    if url.endswith("shadowpriest"):
        return 200, "text/html", (FIXTURES / "shadowpriest_voidburn.html").read_bytes()
    if url.endswith("decklist"):
        return 200, "text/html", (FIXTURES / "decklist_only.html").read_bytes()
    return 404, "text/plain", b"not found"


def test_extract_visible_text_removes_markup_and_keeps_title():
    html = (FIXTURES / "shadowpriest_voidburn.html").read_text(encoding="utf-8")

    parsed = extract_visible_text(html)

    assert parsed["title"] == "Voidburn Wild Aggro Shadow Priest"
    assert "Keep Papercraft Angel" in parsed["text"]
    assert "<p>" not in parsed["text"]


def test_collect_public_source_records_fetches_bounded_public_pages():
    deck_identity = {
        "deck_name": "ShadowPriest",
        "deck_slug": "shadowpriest",
        "deck_code_hash": "sha256:shadow",
        "cards": [
            {"card_id": "BAR_735", "name": "Darkbishop Benedictus", "cost": 5, "count": 1},
            {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2},
            {"card_id": "SW_444", "name": "Twilight Deceptor", "cost": 2, "count": 2},
            {"card_id": "SCH_514", "name": "Raise Dead", "cost": 0, "count": 2},
            {"card_id": "GVG_009", "name": "Shadowbomber", "cost": 1, "count": 2},
        ],
    }

    payload = collect_public_source_records(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        source_urls=["https://example.test/shadowpriest"],
        current_date="2026-07-15",
        fetcher=_fake_fetcher,
        timeout_seconds=2.0,
    )

    assert payload["status"] == "OK"
    assert payload["source_records"][0]["source_family"] == "guide"
    assert payload["source_records"][0]["source_title"] == "Voidburn Wild Aggro Shadow Priest"
    assert "Keep Papercraft Angel" in payload["source_records"][0]["normalized_text"]
    assert payload["source_acquisition_report"]["failed_fetch_count"] == 0


def test_collect_public_source_records_keeps_fetch_failures_non_blocking():
    deck_identity = {
        "deck_name": "ThinDeck",
        "deck_slug": "thindeck",
        "deck_code_hash": "sha256:thin",
        "cards": [{"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}],
    }

    payload = collect_public_source_records(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        source_urls=["https://example.test/missing"],
        current_date="2026-07-15",
        fetcher=_fake_fetcher,
        timeout_seconds=2.0,
    )

    assert payload["status"] == "OK"
    assert payload["source_records"] == []
    assert payload["source_acquisition_report"]["failed_fetch_count"] == 1
    assert (
        payload["source_acquisition_report"]["first_missing_source_action"]
        == "add_public_guide_url_or_use_static_semantics"
    )
