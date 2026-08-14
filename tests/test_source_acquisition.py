from __future__ import annotations

from datetime import datetime
import importlib
import json
from pathlib import Path

import pytest

from hsconfig import source_acquisition as source_acquisition_module
from hsconfig.deck_identity import build_deck_identity
from hsconfig.deckstring_decode import decode_deck_code
from hsconfig.input_loading import (
    load_claims,
    load_guide_sources,
    load_source_documents,
    load_source_evidence,
    load_source_search_records,
)
from hsconfig.source_acquisition import (
    _candidate_matches_target_deck,
    _deck_match_evidence,
    collect_public_source_records,
    extract_visible_text,
    validate_public_source_url,
)
from hsconfig.source_acquisition_provenance import (
    acquisition_provenance_is_canonical,
)
from tests.helpers.live_acquisition import acquire_live_test_provenance


FIXTURES = Path(__file__).parent / "fixtures" / "source_pages"

SHADOWPRIEST_DECK_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQF"
    "yKEGxKgG/KgG17oG1cEGAAA="
)
DIFFERENT_40_CARD_DECK_CODE = (
    "AAEBAYsGABQHCAkMoQSRD5G8AumwA7q2A9fOA6P3A633A7v3A4aDBd2kBcihBsSo"
    "BvyoBte6BtXBBgAA"
)


def _exact_shadowpriest_identity() -> dict:
    decoded = decode_deck_code(SHADOWPRIEST_DECK_CODE)
    return build_deck_identity(
        deck_name="ShadowPriest",
        deck_code=SHADOWPRIEST_DECK_CODE,
        cards=decoded["cards"],
        hero_dbf_id=decoded["hero_dbf_id"],
        format=decoded["format"],
        sideboards=decoded["sideboards"],
    )


def _fixture_fetcher(filename: str):
    page = FIXTURES / filename

    def fetcher(
        url: str,
        timeout_seconds: float,
    ) -> tuple[int, str, bytes]:
        del url, timeout_seconds
        return 200, "text/html", page.read_bytes()

    return fetcher


def _public_resolver(hostname: str) -> list[str]:
    del hostname
    return ["93.184.216.34"]


def _fake_fetcher(url: str, timeout_seconds: float) -> tuple[int, str, bytes]:
    if url.endswith("shadowpriest"):
        return 200, "text/html", (FIXTURES / "shadowpriest_voidburn.html").read_bytes()
    if url.endswith("decklist"):
        return 200, "text/html", (FIXTURES / "decklist_only.html").read_bytes()
    return 404, "text/plain", b"not found"


def _shadowpriest_identity() -> dict:
    return {
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


def _identity_with_unique_cards(card_count: int) -> dict:
    return {
        "deck_name": "ShadowPriest",
        "deck_slug": "shadowpriest",
        "deck_code_hash": "sha256:shadow",
        "cards": [
            {
                "card_id": f"CARD_{index:03d}",
                "name": f"Fixture Card {index}",
                "cost": index,
                "count": 1,
            }
            for index in range(card_count)
        ],
    }


@pytest.mark.parametrize(
    ("mode", "authority"),
    [
        ("live_http", "live_verified"),
        ("captured_record", "captured_unverified"),
        ("manual_evidence", "manual_unverified"),
        ("fixture_map", "fixture_only"),
        ("legacy_claims_json", "legacy_unverified"),
    ],
)
def test_acquisition_provenance_classifies_mode_with_canonical_digest(
    mode,
    authority,
):
    provenance_module = importlib.import_module(
        "hsconfig.source_acquisition_provenance"
    )

    first = provenance_module.build_acquisition_provenance(
        mode=mode,
        content=b"same content",
    )
    second = provenance_module.build_acquisition_provenance(
        mode=mode,
        content="same content",
    )

    assert first == second == {
        "mode": mode,
        "content_sha256": (
            "sha256:a636bd7cd42060a4d07fa1bfbcc010eb7794c2ba721e1e3e4c"
            "20335a15b66eaf"
        ),
        "authority": authority,
    }
    assert json.dumps(first, separators=(",", ":"), sort_keys=True) == json.dumps(
        second,
        separators=(",", ":"),
        sort_keys=True,
    )


def test_acquisition_provenance_digest_changes_with_one_content_byte():
    provenance_module = importlib.import_module(
        "hsconfig.source_acquisition_provenance"
    )

    original = provenance_module.build_acquisition_provenance(
        mode="live_http",
        content=b"same content",
    )
    changed = provenance_module.build_acquisition_provenance(
        mode="live_http",
        content=b"same contenU",
    )

    assert original["content_sha256"] == (
        "sha256:a636bd7cd42060a4d07fa1bfbcc010eb7794c2ba721e1e3e4c"
        "20335a15b66eaf"
    )
    assert changed["content_sha256"] == (
        "sha256:ed4201a9f7d47bc1044061ede0ceb596caa754f7c5789c86f"
        "73633f6ab9bef6b"
    )
    assert original["content_sha256"] != changed["content_sha256"]


def test_acquisition_provenance_rejects_unknown_mode():
    provenance_module = importlib.import_module(
        "hsconfig.source_acquisition_provenance"
    )

    with pytest.raises(ValueError, match="unknown acquisition provenance mode"):
        provenance_module.build_acquisition_provenance(
            mode="caller_claimed_live",
            content=b"same content",
        )


def test_successful_direct_http_fetch_records_live_verified_provenance(
    monkeypatch,
):
    body = b"<html><body><main>ShadowPriest guide text.</main></body></html>"
    monkeypatch.setattr(
        "hsconfig.source_acquisition._fetch_with_validated_address",
        lambda _url, _timeout, _address: (200, "text/html", body),
    )

    result = collect_public_source_records(
        deck_name="ShadowPriest",
        deck_identity=_shadowpriest_identity(),
        source_urls=["https://example.test/guide"],
        current_date="2026-07-26",
        resolver=_public_resolver,
    )

    assert result["source_records"][0]["acquisition_provenance"] == {
        "mode": "live_http",
        "content_sha256": (
            "sha256:ddf17db1bed3db3ec0e6aac3669a50508e9995afe53759b3f0"
            "d9d5ca80e51c63"
        ),
        "authority": "live_verified",
    }


@pytest.mark.parametrize(
    "acquisition_kwargs",
    [
        pytest.param({}, id="default-mode"),
        pytest.param({"acquisition_mode": "live_http"}, id="forged-live-mode"),
    ],
)
def test_injected_fetcher_cannot_assign_live_authority(acquisition_kwargs):
    result = collect_public_source_records(
        deck_name="ShadowPriest",
        deck_identity=_shadowpriest_identity(),
        source_urls=["https://example.test/captured"],
        current_date="2026-07-26",
        fetcher=lambda _url, _timeout: (
            200,
            "text/html",
            b"<html><body>Captured response.</body></html>",
        ),
        resolver=_public_resolver,
        **acquisition_kwargs,
    )

    provenance = result["source_records"][0]["acquisition_provenance"]
    assert provenance["mode"] == "captured_record"
    assert provenance["authority"] == "captured_unverified"


@pytest.mark.parametrize(
    ("extra_key", "sensitive_value"),
    [
        ("raw_html", "<script>secret</script>"),
        ("local_path", "C:" + "/" + "/".join(("Users", "operator", "private", "source.html"))),
        ("source_url", "https://example.test/guide?token=super-secret"),
    ],
)
def test_canonical_provenance_rejects_additional_fields(
    extra_key,
    sensitive_value,
):
    provenance = {
        **acquire_live_test_provenance(),
        extra_key: sensitive_value,
    }

    assert acquisition_provenance_is_canonical(provenance) is False


@pytest.mark.parametrize(
    ("loader", "payload", "expected_mode", "expected_authority"),
    [
        (
            load_claims,
            {"claims": [{"claim_kind": "mulligan_keep"}]},
            "legacy_claims_json",
            "legacy_unverified",
        ),
        (
            load_source_evidence,
            {"evidence_rows": [{"claim_kind": "mulligan_keep"}]},
            "manual_evidence",
            "manual_unverified",
        ),
        (
            load_guide_sources,
            {"sources": [{"claims": []}]},
            "manual_evidence",
            "manual_unverified",
        ),
        (
            load_source_documents,
            {"source_documents": [{"claims": []}]},
            "captured_record",
            "captured_unverified",
        ),
        (
            load_source_search_records,
            {"records": [{"claims": []}]},
            "captured_record",
            "captured_unverified",
        ),
    ],
)
def test_import_loaders_overwrite_forged_live_provenance(
    tmp_path,
    loader,
    payload,
    expected_mode,
    expected_authority,
):
    rows = next(value for value in payload.values() if isinstance(value, list))
    rows[0]["acquisition_provenance"] = {
        "mode": "live_http",
        "content_sha256": "sha256:" + ("f" * 64),
        "authority": "live_verified",
    }
    path = tmp_path / f"{expected_mode}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = loader(str(path))

    assert loaded[0]["acquisition_provenance"]["mode"] == expected_mode
    assert loaded[0]["acquisition_provenance"]["authority"] == expected_authority
    assert loaded[0]["acquisition_provenance"]["content_sha256"].startswith(
        "sha256:"
    )
    assert loaded[0]["acquisition_provenance"]["content_sha256"] != (
        "sha256:" + ("f" * 64)
    )


def test_fixture_transport_overwrites_forged_live_provenance():
    body = json.dumps(
        {
            "acquisition_provenance": {
                "mode": "live_http",
                "content_sha256": "sha256:" + ("f" * 64),
                "authority": "live_verified",
            }
        }
    ).encode("utf-8")

    result = collect_public_source_records(
        deck_name="ShadowPriest",
        deck_identity=_shadowpriest_identity(),
        source_urls=["https://example.test/fixture"],
        current_date="2026-07-26",
        fetcher=lambda _url, _timeout: (200, "text/html", body),
        resolver=_public_resolver,
        acquisition_mode="fixture_map",
    )

    provenance = result["source_records"][0]["acquisition_provenance"]
    assert provenance["mode"] == "fixture_map"
    assert provenance["authority"] == "fixture_only"
    assert provenance["content_sha256"] != "sha256:" + ("f" * 64)


def test_footer_year_does_not_make_old_guide_current():
    html = b"""
    <html>
      <head><title>Shadow Priest Guide</title></head>
      <body>
        <article><p>Published 2021. Mulligan: keep Mind Blast.</p></article>
        <footer>Copyright 2026</footer>
      </body>
    </html>
    """

    result = collect_public_source_records(
        deck_name="ShadowPriest",
        deck_identity=_shadowpriest_identity(),
        source_urls=["https://example.test/guide"],
        current_date="2026-07-25",
        fetcher=lambda _url, _timeout: (200, "text/html", html),
        resolver=lambda _host: ["93.184.216.34"],
    )

    record = result["source_records"][0]
    assert record["publication_year"] is None
    assert record["source_record_strength"] != "candidate_strong"


def test_explicit_article_published_time_is_used():
    html = b"""
    <html>
      <head>
        <meta property="article:published_time" content="2026-05-03T12:00:00Z">
        <title>Shadow Priest Guide</title>
      </head>
      <body><article>Mulligan: keep Mind Blast.</article></body>
    </html>
    """

    result = collect_public_source_records(
        deck_name="ShadowPriest",
        deck_identity=_shadowpriest_identity(),
        source_urls=["https://example.test/guide"],
        current_date="2026-07-25",
        fetcher=lambda _url, _timeout: (200, "text/html", html),
        resolver=lambda _host: ["93.184.216.34"],
    )

    assert result["source_records"][0]["publication_year"] == 2026


def test_five_of_sixteen_cards_is_archetype_not_exact_deck_match():
    identity = _identity_with_unique_cards(16)
    text = "ShadowPriest guide " + " ".join(
        card["name"] for card in identity["cards"][:5]
    )

    evidence, scope = _deck_match_evidence(
        "ShadowPriest",
        identity,
        "ShadowPriest Guide",
        text,
    )

    assert evidence["matched_card_count"] == 5
    assert evidence["unique_deck_card_count"] == 16
    assert evidence["card_overlap_ratio"] == 0.3125
    assert scope == "archetype_matched"


def test_exact_source_deckstring_promotes_to_exact_deck_scope():
    shadowpriest_identity = _exact_shadowpriest_identity()
    report = collect_public_source_records(
        deck_name="ShadowPriest",
        deck_identity=shadowpriest_identity,
        source_urls=["https://example.test/exact"],
        current_date="2026-07-26",
        fetcher=_fixture_fetcher("shadowpriest_current_guide.html"),
        resolver=_public_resolver,
    )

    record = report["source_records"][0]
    assert record["deck_match_scope"] == "exact_deck_matched"
    exact = record["deck_match"]["exact_deck_evidence"]
    assert exact["matched"] is True
    assert exact["matched_deck_fingerprint"] == shadowpriest_identity["deck_fingerprint"]
    assert "deck_code" not in exact
    assert "AAEBA" not in json.dumps(record)


def test_source_record_redacts_deckstrings_from_title_and_url_fields():
    shadowpriest_identity = _exact_shadowpriest_identity()
    source_url = (
        "https://www.reddit.com/r/wildhearthstone/comments/1/"
        f"{SHADOWPRIEST_DECK_CODE}/"
    )
    html = f"""
    <html>
      <head>
        <meta property="article:published_time" content="2026-07-26T00:00:00Z">
        <title>ShadowPriest Guide {SHADOWPRIEST_DECK_CODE}</title>
      </head>
      <body><main><p>Mulligan: Keep Papercraft Angel and Twilight Deceptor.</p></main></body>
    </html>
    """.encode()

    report = collect_public_source_records(
        deck_name="ShadowPriest",
        deck_identity=shadowpriest_identity,
        source_urls=[source_url],
        current_date="2026-07-26",
        fetcher=lambda _url, _timeout: (200, "text/html", html),
        resolver=_public_resolver,
    )

    record = report["source_records"][0]
    assert "source_fetch_url" in record
    assert "AAEBA" not in json.dumps(record)


def test_target_hero_requires_observed_candidate_hero():
    shadowpriest_identity = _exact_shadowpriest_identity()
    candidate = {
        "deck_fingerprint": shadowpriest_identity["deck_fingerprint"],
        "hero_dbf_id": None,
        "format": shadowpriest_identity["format"],
        "card_count_total": shadowpriest_identity["card_count_total"],
        "sideboard_count": shadowpriest_identity["sideboard_count"],
    }

    assert _candidate_matches_target_deck(candidate, shadowpriest_identity) is False


def test_name_and_card_overlap_remains_archetype_only():
    shadowpriest_identity = _exact_shadowpriest_identity()
    report = collect_public_source_records(
        deck_name="ShadowPriest",
        deck_identity=shadowpriest_identity,
        source_urls=["https://example.test/archetype"],
        current_date="2026-07-26",
        fetcher=_fixture_fetcher("shadowpriest_archetype_only_guide.html"),
        resolver=_public_resolver,
    )

    record = report["source_records"][0]
    assert record["deck_match_scope"] == "archetype_matched"
    assert record["strong_promotion_eligible"] is False
    assert "exact_deck_match_required" in record["promotion_blockers"]


def test_different_40_card_source_deckstring_remains_archetype_only():
    shadowpriest_identity = _exact_shadowpriest_identity()
    assert decode_deck_code(DIFFERENT_40_CARD_DECK_CODE)["card_count_total"] == 40
    html = f"""
    <html>
      <head>
        <meta property="article:published_time" content="2026-07-26T00:00:00Z">
        <title>Wild ShadowPriest Guide</title>
      </head>
      <body>
        <main>
          <h1>Wild ShadowPriest Guide</h1>
          <p>Exact deck code: {DIFFERENT_40_CARD_DECK_CODE}</p>
          <p>Mulligan: Keep Papercraft Angel and Twilight Deceptor.</p>
        </main>
      </body>
    </html>
    """.encode()
    report = collect_public_source_records(
        deck_name="ShadowPriest",
        deck_identity=shadowpriest_identity,
        source_urls=["https://example.test/different"],
        current_date="2026-07-26",
        fetcher=lambda _url, _timeout: (200, "text/html", html),
        resolver=_public_resolver,
    )

    record = report["source_records"][0]
    assert record["deck_match_scope"] == "archetype_matched"
    assert record["deck_match"]["exact_deck_evidence"]["matched"] is False


def test_extract_visible_text_removes_markup_and_keeps_title():
    html = (FIXTURES / "shadowpriest_voidburn.html").read_text(encoding="utf-8")

    parsed = extract_visible_text(html)

    assert parsed["title"] == "Voidburn Wild Aggro Shadow Priest"
    assert "Keep Papercraft Angel" in parsed["text"]
    assert "<p>" not in parsed["text"]


def test_visible_text_prefers_main_and_excludes_page_chrome():
    parsed = extract_visible_text(
        """
        <html>
          <head>
            <title>ShadowPriest Guide</title>
            <meta property="article:published_time" content="2026-07-25T00:00:00Z">
          </head>
          <body>
            <header>Help Sign In</header>
            <nav>Decks Cards Forums</nav>
            <main>
              <h1>Exact ShadowPriest plan</h1>
              <p>Keep the documented one-drop against slow decks.</p>
            </main>
            <aside>Follow Us On Twitter</aside>
            <footer>Privacy Terms</footer>
          </body>
        </html>
        """
    )

    assert parsed["title"] == "ShadowPriest Guide"
    assert parsed["content_scope"] == "main_or_article"
    assert "Exact ShadowPriest plan" in parsed["text"]
    assert "Keep the documented one-drop" in parsed["text"]
    assert "Help Sign In" not in parsed["text"]
    assert "Follow Us On Twitter" not in parsed["text"]
    assert parsed["publication_values"] == ["2026-07-25T00:00:00Z"]


def test_visible_text_uses_sanitized_body_when_primary_content_is_absent():
    parsed = extract_visible_text(
        """
        <html>
          <head><title>Legacy guide</title></head>
          <body>
            <nav>Help Sign In</nav>
            <section><h1>Mulligan</h1><p>Keep CARD_A.</p></section>
            <footer>Follow Us On Twitter</footer>
          </body>
        </html>
        """
    )

    assert parsed["content_scope"] == "visible_body_fallback"
    assert parsed["text"] == "Mulligan Keep CARD_A."


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


def test_collect_public_source_records_uses_utc_year_when_current_date_is_not_supplied(
    monkeypatch,
):
    class FrozenDatetime(datetime):
        @classmethod
        def utcnow(cls):
            return cls(2026, 7, 15)

    monkeypatch.setattr(source_acquisition_module, "datetime", FrozenDatetime)
    deck_identity = {
        "deck_name": "ShadowPriest",
        "deck_slug": "shadowpriest",
        "deck_code_hash": "sha256:shadow",
        "cards": [
            {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2},
            {"card_id": "SW_444", "name": "Twilight Deceptor", "cost": 2, "count": 2},
        ],
    }

    def current_guide_fetcher(url: str, timeout_seconds: float) -> tuple[int, str, bytes]:
        del url, timeout_seconds
        return (
            200,
            "text/html",
            b"""
            <html>
              <head>
                <meta property="article:published_time" content="2026-07-15T00:00:00Z">
                <title>ShadowPriest 2026 Guide</title>
              </head>
              <body>
                <h1>ShadowPriest 2026 Guide</h1>
                <p>Mulligan: Keep Papercraft Angel and Twilight Deceptor.</p>
                <p>This public guide explains the opening hand, early pressure,
                Shadow hero power plan, and matchup posture for the current
                wild ShadowPriest archetype with enough full-text context to
                qualify as a guide rather than a snippet.</p>
              </body>
            </html>
            """,
        )

    payload = collect_public_source_records(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        source_urls=["https://example.test/shadowpriest"],
        current_date=None,
        fetcher=current_guide_fetcher,
        resolver=_public_resolver,
        timeout_seconds=2.0,
    )

    record = payload["source_records"][0]
    assert record["publication_year"] == 2026
    assert record["source_record_strength"] == "partial"
    assert record["source_strength"] == "partial"
    assert record["strong_promotion_eligible"] is False
    assert "exact_deck_match_required" in record["promotion_blockers"]


def test_collect_public_source_records_reports_candidate_registry_url_count():
    deck_identity = {
        "deck_name": "ShadowPriest",
        "deck_slug": "shadowpriest",
        "deck_code_hash": "sha256:shadow",
        "cards": [
            {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2},
            {"card_id": "SW_444", "name": "Twilight Deceptor", "cost": 2, "count": 2},
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
        candidate_registry_url_count=1,
    )

    assert payload["source_acquisition_report"]["candidate_registry_url_count"] == 1
    assert payload["source_acquisition_report"]["explicit_source_url_count"] == 0


def test_reddit_thread_urls_fetch_through_old_reddit_but_preserve_source_url():
    original_url = (
        "https://www.reddit.com/r/wildhearthstone/comments/"
        "1u0kd33/any_help_with_cta_paladin_mulligan/"
    )
    fetch_url = (
        "https://old.reddit.com/r/wildhearthstone/comments/"
        "1u0kd33/any_help_with_cta_paladin_mulligan/"
    )
    seen_fetch_urls: list[str] = []
    deck_identity = {
        "deck_name": "CtAPaladin",
        "deck_slug": "ctapaladin",
        "deck_code_hash": "sha256:cta",
        "cards": [
            {"card_id": "ETC_318", "name": "Boogie Down", "cost": 3, "count": 2},
            {"card_id": "LOOT_093", "name": "Call to Arms", "cost": 4, "count": 2},
        ],
    }

    def reddit_fetcher(url: str, timeout_seconds: float) -> tuple[int, str, bytes]:
        del timeout_seconds
        seen_fetch_urls.append(url)
        return (
            200,
            "text/html",
            b"""
            <html>
              <head>
                <meta property="article:published_time" content="2026-07-18T00:00:00Z">
                <title>Any help with CtA Paladin mulligan 2026</title>
              </head>
              <body>
                <p>Published July 18, 2026.</p>
                <p>Mulligan: Keep Boogie Down and Call to Arms for the current
                Wild CtA Paladin opening.</p>
                <p>This full public Reddit thread also discusses early pressure,
                card roles, matchup posture, and current Wild ladder context.</p>
              </body>
            </html>
            """,
        )

    payload = collect_public_source_records(
        deck_name="CtAPaladin",
        deck_identity=deck_identity,
        source_urls=[original_url],
        current_date="2026-07-18",
        fetcher=reddit_fetcher,
        resolver=_public_resolver,
        timeout_seconds=2.0,
    )

    record = payload["source_records"][0]
    assert seen_fetch_urls == [fetch_url]
    assert record["source_url"] == original_url
    assert record["source_fetch_url"] == fetch_url
    assert record["source_record_strength"] == "partial"
    assert record["strong_promotion_eligible"] is False
    assert record["first_missing_source_action"] == "add_exact_deck_matched_source"


def test_decklist_and_stats_sources_are_non_promoting():
    deck_identity = {
        "deck_name": "ThinDeck",
        "deck_slug": "thindeck",
        "deck_code_hash": "sha256:thin",
        "cards": [
            {"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}
        ],
    }

    def decklist_and_stats_fetcher(
        url: str, timeout_seconds: float
    ) -> tuple[int, str, bytes]:
        del timeout_seconds
        if url.endswith("decklist"):
            return 200, "text/html", (FIXTURES / "decklist_only.html").read_bytes()
        if "hsguru" in url:
            return (
                200,
                "text/html",
                b"""
                <html>
                  <head><title>HSGuru ThinDeck public stats</title></head>
                  <body>
                    <h1>ThinDeck popularity and aggregate statistics</h1>
                    <p>Aggregate statistics, popularity, performance table,
                    and card inclusion data for a Wild decklist. This page is
                    stats support only and contains no full-text guide
                    instructions for runtime surface claims.</p>
                  </body>
                </html>
                """,
            )
        return 404, "text/plain", b"not found"

    payload = collect_public_source_records(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        source_urls=[
            "https://example.test/decklist",
            "https://www.hsguru.com/deck/12345",
        ],
        current_date="2026-07-15",
        fetcher=decklist_and_stats_fetcher,
        resolver=_public_resolver,
        timeout_seconds=2.0,
    )

    records = {record["source_category"]: record for record in payload["source_records"]}

    assert set(records) == {"decklist", "stats"}
    for record in records.values():
        assert record["promotion_eligible"] is False
        assert record["strong_promotion_eligible"] is False
        assert record["promotion_blockers"]
        assert record["first_missing_source_action"] != "none"


def test_hsreplay_stats_sources_are_non_promoting_even_with_guide_words():
    deck_identity = {
        "deck_name": "ThinDeck",
        "deck_slug": "thindeck",
        "deck_code_hash": "sha256:thin",
        "cards": [
            {"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}
        ],
    }

    def hsreplay_stats_fetcher(
        url: str, timeout_seconds: float
    ) -> tuple[int, str, bytes]:
        del url, timeout_seconds
        return (
            200,
            "text/html",
            b"""
            <html>
              <head><title>HSReplay ThinDeck mulligan guide stats</title></head>
              <body>
                <h1>ThinDeck aggregate stats and performance table</h1>
                <p>HSReplay deck statistics, popularity, mulligan guide data,
                performance table, winrate, and card inclusion data for a Wild
                decklist. This is aggregate statistical support only and does
                not contain complete strategy instructions for runtime claims.</p>
                <p>2026 Wild stats support for ThinDeck includes Fixture Card.</p>
              </body>
            </html>
            """,
        )

    payload = collect_public_source_records(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        source_urls=["https://hsreplay.net/decks/example"],
        current_date="2026-07-15",
        fetcher=hsreplay_stats_fetcher,
        resolver=_public_resolver,
        timeout_seconds=2.0,
    )

    record = payload["source_records"][0]
    assert record["source_family"] == "stats"
    assert record["source_visibility"] == "stats_only"
    assert record["source_category"] == "stats"
    assert record["source_record_strength"] != "candidate_strong"
    assert record["promotion_eligible"] is False
    assert record["strong_promotion_eligible"] is False
    assert record["promotion_blockers"]
    assert record["first_missing_source_action"] != "none"


def test_full_text_guide_wins_over_stats_context_markers():
    deck_identity = {
        "deck_name": "ShadowPriest",
        "deck_slug": "shadowpriest",
        "deck_code_hash": "sha256:shadow",
        "cards": [
            {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2},
            {"card_id": "SW_444", "name": "Twilight Deceptor", "cost": 2, "count": 2},
        ],
    }

    def guide_with_stats_context(
        url: str, timeout_seconds: float
    ) -> tuple[int, str, bytes]:
        del url, timeout_seconds
        return (
            200,
            "text/html",
            b"""
            <html>
              <head>
                <meta property="article:published_time" content="2026-07-15T00:00:00Z">
                <title>ShadowPriest 2026 Mulligan Guide</title>
              </head>
              <body>
                <h1>ShadowPriest 2026 Mulligan Guide</h1>
                <p>Mulligan: Keep Papercraft Angel and Twilight Deceptor.</p>
                <p>The guide mentions aggregate statistics and popularity as
                context, but the strategic full-text guide content and explicit
                opening-hand keep instructions remain the source family signal.</p>
                <p>This current Wild guide explains early pressure, Shadow
                damage, matchup posture, and card-specific opening decisions
                with enough full-text context to qualify as a guide.</p>
              </body>
            </html>
            """,
        )

    payload = collect_public_source_records(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        source_urls=["https://example.test/shadowpriest-guide-with-stats-context"],
        current_date="2026-07-15",
        fetcher=guide_with_stats_context,
        resolver=_public_resolver,
        timeout_seconds=2.0,
    )

    record = payload["source_records"][0]
    assert record["source_family"] == "guide"
    assert record["source_visibility"] == "full_text"
    assert record["source_category"] == "public_guide"
    assert record["promotion_eligible"] is False
    assert record["strong_promotion_eligible"] is False
    assert "exact_deck_match_required" in record["promotion_blockers"]


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
