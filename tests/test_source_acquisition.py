from __future__ import annotations

from pathlib import Path

from hsconfig import source_acquisition as source_acquisition_module
from hsconfig.source_acquisition import (
    collect_public_source_records,
    extract_visible_text,
    validate_public_source_url,
)


FIXTURES = Path(__file__).parent / "fixtures" / "source_pages"


def _public_resolver(hostname: str) -> list[str]:
    del hostname
    return ["93.184.216.34"]


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
        resolver=_public_resolver,
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
        resolver=_public_resolver,
        timeout_seconds=2.0,
    )

    assert payload["status"] == "OK"
    assert payload["source_records"] == []
    assert payload["source_acquisition_report"]["failed_fetch_count"] == 1
    assert (
        payload["source_acquisition_report"]["first_missing_source_action"]
        == "add_public_guide_url_or_use_static_semantics"
    )


def test_collect_public_source_records_does_not_assign_requested_deck_without_page_evidence():
    deck_identity = {
        "deck_name": "ThinDeck",
        "deck_slug": "thindeck",
        "deck_code_hash": "sha256:thin",
        "cards": [{"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}],
    }

    def unrelated_fetcher(url: str, timeout_seconds: float) -> tuple[int, str, bytes]:
        del url, timeout_seconds
        return 200, "text/html", b"<html><title>Other Deck</title><p>Unrelated page.</p></html>"

    payload = collect_public_source_records(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        source_urls=["https://example.test/unrelated"],
        current_date="2026-07-15",
        fetcher=unrelated_fetcher,
        resolver=_public_resolver,
        timeout_seconds=2.0,
    )

    record = payload["source_records"][0]
    assert record["deck_match"]["deck_name"] == "unknown"
    assert record["deck_match"]["matched_card_ids"] == []
    assert record["deck_match_scope"] == "unknown"
    assert "publication_date" not in record


def test_validate_public_source_url_rejects_local_and_private_targets():
    assert validate_public_source_url("https://example.test/guide", resolver=_public_resolver) is None
    assert validate_public_source_url("http://example.test/guide") == "non_public_https_url"
    assert validate_public_source_url("https://localhost/guide") == "non_public_https_url"
    assert validate_public_source_url("https://127.0.0.1/guide") == "non_public_https_url"
    assert validate_public_source_url("https://10.0.0.1/guide") == "non_public_https_url"
    assert validate_public_source_url("https://192.168.1.2/guide") == "non_public_https_url"


def test_validate_public_source_url_rejects_hostname_resolving_to_private_target():
    def resolver(hostname: str) -> list[str]:
        if hostname == "private-alias.example.test":
            return ["10.0.0.1"]
        return ["93.184.216.34"]

    assert (
        validate_public_source_url("https://private-alias.example.test/guide", resolver=resolver)
        == "non_public_https_url"
    )


def test_collect_public_source_records_rejects_private_redirect_targets():
    deck_identity = {
        "deck_name": "ThinDeck",
        "deck_slug": "thindeck",
        "deck_code_hash": "sha256:thin",
        "cards": [{"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}],
    }

    def redirect_fetcher(url: str, timeout_seconds: float) -> tuple[int, str, bytes]:
        assert timeout_seconds == 2.0
        if url == "https://example.test/redirect":
            return 302, "text/html; location=https://127.0.0.1/private", b""
        raise AssertionError(f"unexpected redirected fetch: {url}")

    payload = collect_public_source_records(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        source_urls=["https://example.test/redirect"],
        current_date="2026-07-15",
        fetcher=redirect_fetcher,
        resolver=_public_resolver,
        timeout_seconds=2.0,
    )

    assert payload["source_records"] == []
    assert payload["source_acquisition_report"]["failed_fetch_count"] == 1
    assert payload["source_acquisition_report"]["failures"] == [
        {
            "url": "https://example.test/redirect",
            "error": "redirect_target_non_public_https_url",
        }
    ]


def test_collect_public_source_records_rejects_redirect_hostnames_resolving_private():
    deck_identity = {
        "deck_name": "ThinDeck",
        "deck_slug": "thindeck",
        "deck_code_hash": "sha256:thin",
        "cards": [{"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}],
    }

    def resolver(hostname: str) -> list[str]:
        if hostname == "private-alias.example.test":
            return ["10.0.0.1"]
        return ["93.184.216.34"]

    def redirect_fetcher(url: str, timeout_seconds: float) -> tuple[int, str, bytes]:
        assert timeout_seconds == 2.0
        if url == "https://example.test/redirect":
            return 302, "text/html; location=https://private-alias.example.test/private", b""
        raise AssertionError(f"unexpected redirected fetch: {url}")

    payload = collect_public_source_records(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        source_urls=["https://example.test/redirect"],
        current_date="2026-07-15",
        fetcher=redirect_fetcher,
        resolver=resolver,
        timeout_seconds=2.0,
    )

    assert payload["source_records"] == []
    assert payload["source_acquisition_report"]["failed_fetch_count"] == 1
    assert payload["source_acquisition_report"]["failures"] == [
        {
            "url": "https://example.test/redirect",
            "error": "redirect_target_non_public_https_url",
        }
    ]


def test_collect_public_source_records_binds_default_fetch_to_validated_address(monkeypatch):
    deck_identity = {
        "deck_name": "ThinDeck",
        "deck_slug": "thindeck",
        "deck_code_hash": "sha256:thin",
        "cards": [{"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}],
    }
    resolved_hosts: list[str] = []
    observed_fetch: dict[str, object] = {}

    def resolver(hostname: str) -> list[str]:
        resolved_hosts.append(hostname)
        if len(resolved_hosts) == 1:
            return ["93.184.216.34"]
        return ["10.0.0.1"]

    def fetch_with_validated_address(
        url: str,
        timeout_seconds: float,
        validated_address: str,
    ) -> tuple[int, str, bytes]:
        observed_fetch.update(
            {
                "url": url,
                "timeout_seconds": timeout_seconds,
                "validated_address": validated_address,
            }
        )
        return 200, "text/html", (FIXTURES / "shadowpriest_voidburn.html").read_bytes()

    monkeypatch.setattr(
        source_acquisition_module,
        "_fetch_with_validated_address",
        fetch_with_validated_address,
    )

    payload = collect_public_source_records(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        source_urls=["https://example.test/shadowpriest"],
        current_date="2026-07-15",
        resolver=resolver,
        timeout_seconds=2.0,
    )

    assert payload["source_acquisition_report"]["failed_fetch_count"] == 0
    assert observed_fetch == {
        "url": "https://example.test/shadowpriest",
        "timeout_seconds": 2.0,
        "validated_address": "93.184.216.34",
    }
    assert resolved_hosts == ["example.test"]
