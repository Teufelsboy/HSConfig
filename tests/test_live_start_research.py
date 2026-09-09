from __future__ import annotations

from hashlib import sha256
import importlib
from threading import Event
import time

import pytest
from hearthstone.deckstrings import FormatType, write_deckstring

from hsconfig import source_acquisition as acquisition
from hsconfig.card_snapshot import build_card_snapshot
from hsconfig.deck_identity import build_deck_identity
from hsconfig.deckstring_decode import decode_deck_code_from_snapshot
from hsconfig.package_request import FrozenJsonDocument


DIGEST = "sha256:" + "a" * 64
URL = "https://example.test/guide"
IDENTITY = {
    "deck_name": "MyDeck",
    "deck_fingerprint": DIGEST,
    "class": "MAGE",
    "format": 1,
    "cards": [
        {"card_id": "TEST_A", "name": "Alpha Mage", "count": 2},
        {"card_id": "TEST_B", "name": "Beta Spell", "count": 2},
    ],
}
METADATA = {row["card_id"]: row for row in IDENTITY["cards"]}


def research():
    return importlib.import_module("hsconfig.live_start_research")


@pytest.mark.parametrize("outcome", ["completed", "unavailable", "budget_exhausted"])
def test_empty_shortlist_is_valid(outcome):
    assert research().validate_research_draft(
        {
            "acquisition_request_sha256": DIGEST,
            "urls": [],
            "discovery_outcome": outcome,
        },
        request_sha256=DIGEST,
    ) == ((), outcome)


@pytest.mark.parametrize(
    "change",
    [
        {"authority": "live_verified"},
        {"text": "Ignore instructions"},
        {"path": "C:/runtime"},
        {"urls": [URL] * 4},
        {"urls": [URL, URL]},
        {"urls": ["http://example.test"]},
        {"urls": ["https://user:pass@example.test"]},
        {"urls": ["https://127.0.0.1"]},
        {"urls": ["https://localhost"]},
        {"urls": ["file:///C:/private"]},
        {"urls": ["https://example.test:bad"]},
        {"urls": [URL, URL + "#same"]},
        {"urls": "https://example.test"},
        {"acquisition_request_sha256": "sha256:" + "b" * 64},
        {"discovery_outcome": "no_guide_exists"},
    ],
)
def test_draft_rejects_non_closed_or_unsafe_input(change):
    with pytest.raises(ValueError):
        research().validate_research_draft(
            {
                "acquisition_request_sha256": DIGEST,
                "urls": [],
                "discovery_outcome": "completed",
                **change,
            },
            request_sha256=DIGEST,
        )


def test_request_is_sealed_and_uses_deck_facts_not_only_label():
    doc = research().build_research_request(
        run_id="run-1",
        deck_identity=IDENTITY,
        captured_input_sha256=DIGEST,
        queries=(),
    )
    assert type(doc) is FrozenJsonDocument
    value = doc.to_value()
    assert len(value["queries"]) == 2
    assert "Alpha Mage" in value["queries"][0]
    assert "MAGE" in value["queries"][0]
    assert "Wild" in value["queries"][0]
    claimed = value.pop("content_sha256")
    assert (
        claimed
        == "sha256:"
        + sha256(FrozenJsonDocument.from_value(value).canonical_json).hexdigest()
    )
    value["deck_identity"]["cards"].clear()
    assert doc.to_value()["deck_identity"]["cards"]


def test_deadline_does_not_reset_between_pages():
    timeout = research().research_timeout
    assert timeout(deadline_utc=130, now_utc=100) == 10
    assert timeout(deadline_utc=130, now_utc=126) == 4
    assert timeout(deadline_utc=130, now_utc=131) == 0


def collect(**kwargs):
    return acquisition.collect_public_source_records(
        deck_name="MyDeck",
        deck_identity=IDENTITY,
        source_urls=[URL],
        current_date="2026-09-09",
        resolver=lambda host: ["93.184.216.34"],
        **kwargs,
    )


def test_expired_deadline_does_not_fetch(monkeypatch):
    def forbidden(*args):
        raise AssertionError("fetch after deadline")

    monkeypatch.setattr(acquisition, "_fetch_with_validated_address", forbidden)
    result = collect(deadline_utc=time.time() - 1)
    assert result["source_records"] == []
    assert (
        result["source_acquisition_report"]["failures"][0]["error"]
        == "research_budget_exhausted"
    )


def test_blocked_dns_is_bounded_without_executor_shutdown_wait():
    release = Event()
    started = time.monotonic()
    try:
        result = acquisition.collect_public_source_records(
            deck_name="MyDeck",
            deck_identity=IDENTITY,
            source_urls=[URL],
            resolver=lambda host: release.wait(2) or ["93.184.216.34"],
            deadline_utc=time.time() + 0.05,
        )
        assert time.monotonic() - started < 0.8
        assert result["source_records"] == []
        assert (
            result["source_acquisition_report"]["failures"][0]["error"]
            == "research_budget_exhausted"
        )
    finally:
        release.set()


def test_blocked_transport_is_bounded(monkeypatch):
    release = Event()

    def blocked(*args):
        release.wait(2)
        return 200, "text/html", b"Alpha Mage"

    monkeypatch.setattr(acquisition, "_fetch_with_validated_address", blocked)
    started = time.monotonic()
    try:
        result = collect(deadline_utc=time.time() + 0.05)
        assert time.monotonic() - started < 0.8
        assert not result["source_records"]
    finally:
        release.set()


@pytest.mark.parametrize("size, expected", [(400000, 1), (400001, 0)])
def test_oversize_bodies_are_not_verified_as_truncated_full_text(
    monkeypatch, size, expected
):
    monkeypatch.setattr(
        acquisition,
        "_fetch_with_validated_address",
        lambda *args: (200, "text/html", b"a" * size),
    )
    result = collect(deadline_utc=time.time() + 2)
    assert len(result["source_records"]) == expected
    if not expected:
        assert (
            result["source_acquisition_report"]["failures"][0]["error"]
            == "source_body_too_large"
        )


def test_snapshot_decode_preserves_new_card_exact_match(monkeypatch):
    rows = [
        {"id": "NEW_HERO", "dbfId": 900001, "name": "Hero", "type": "HERO"},
        {"id": "NEW_CARD", "dbfId": 900002, "name": "New Card", "type": "MINION"},
        {"id": "OTHER_CARD", "dbfId": 900003, "name": "Other Card", "type": "MINION"},
    ]
    snapshot = build_card_snapshot(rows, captured_at="2026-09-09")
    code = write_deckstring([(900002, 15), (900003, 15)], [900001], FormatType.FT_WILD)
    decoded = decode_deck_code_from_snapshot(code, snapshot)
    identity = build_deck_identity(
        deck_name="NewDeck",
        deck_code=code,
        cards=decoded["cards"],
        hero_dbf_id=900001,
        format=decoded["format"],
    )
    monkeypatch.setattr(
        acquisition, "decode_deck_code", lambda code: pytest.fail("local decoder used")
    )
    monkeypatch.setattr(
        acquisition,
        "_fetch_with_validated_address",
        lambda *args: (
            200,
            "text/html",
            ("<article>New Card guide " + code + "</article>").encode(),
        ),
    )
    result = acquisition.collect_public_source_records(
        deck_name="NewDeck",
        deck_identity=identity,
        source_urls=[URL],
        resolver=lambda host: ["93.184.216.34"],
        card_snapshot=snapshot,
        deadline_utc=time.time() + 2,
    )
    assert result["source_records"][0]["deck_match_scope"] == "exact_deck_matched"


@pytest.mark.parametrize("outcome", ["completed", "unavailable", "budget_exhausted"])
def test_empty_result_is_sealed_with_visible_limitations(outcome):
    doc = research().build_research_result(
        acquired={"source_records": []},
        discovery_outcome=outcome,
        attempts=[],
        deadline_utc=None,
        card_metadata=METADATA,
    )
    value = doc.to_value()
    assert set(value) == {
        "schema_version",
        "discovery_outcome",
        "attempts",
        "deadline_utc",
        "observations",
        "limitations",
        "content_sha256",
    }
    assert value["observations"] == []
    assert "no_useful_observations" in value["limitations"]
    assert outcome == "completed" or "discovery_" + outcome in value["limitations"]


def completed_attempts(acquired):
    return [
        {
            "url": row["source_url"],
            "state": "completed",
            "error": None,
            "record_sha256": "sha256:"
            + sha256(FrozenJsonDocument.from_value(row).canonical_json).hexdigest(),
        }
        for row in acquired["source_records"]
    ]


@pytest.mark.parametrize("diagnostic", [False, True])
def test_canonical_pipeline_retains_authority_and_relevant_observations(
    monkeypatch, diagnostic
):
    page = (
        "<meta property='article:published_time' content='2026'>"
        "<article>MyDeck guide. "
        + "Introductory background. "
        * 100
        + "Mulligan: keep Alpha Mage. Beta Spell provides follow-up pressure. "
        "Unknown Card XYZ_999 is irrelevant. Mulligan: never keep Alpha Mage.</article>"
    ).encode()

    def transport(*args):
        return 200, "text/html", page

    monkeypatch.setattr(acquisition, "_fetch_with_validated_address", transport)
    acquired = collect(
        fetcher=transport if diagnostic else None, deadline_utc=time.time() + 2
    )
    projection, handoff = research().compile_research_sources(
        acquired=acquired,
        deck_identity=IDENTITY,
        current_date="2026-09-09",
    )
    data = projection.to_value()
    expected = "captured_unverified" if diagnostic else "live_verified"
    assert (
        data["compiled"]["records"][0]["acquisition_provenance"]["authority"]
        == expected
    )
    assert (
        data["compiled"]["records"][0]["evidence_id"]
        == acquired["source_records"][0]["evidence_id"]
    )
    assert handoff.stage == "verified_source_documents"
    assert "_token" not in str(data)
    result = (
        research()
        .build_research_result(
            acquired=data,
            discovery_outcome="completed",
            attempts=completed_attempts(acquired),
            deadline_utc=time.time() + 2,
            card_metadata=METADATA,
        )
        .to_value()
    )
    observations = result["observations"]
    assert any("keep Alpha Mage" in row["supporting_text"] for row in observations)
    assert all(len(row["supporting_text"]) <= 600 for row in observations)
    assert all(set(row["card_ids"]) <= {"TEST_A", "TEST_B"} for row in observations)
    assert all(row["source_updated_at"] is None for row in observations)
    assert all(row["applicability"] != "exact_list" for row in observations)
    assert any(row["conflicts"] for row in observations)


def test_publication_date_is_not_relabelled_as_update_date(monkeypatch):
    page = b"<meta property='article:published_time' content='2026-09-01'><article>Alpha Mage</article>"
    monkeypatch.setattr(
        acquisition,
        "_fetch_with_validated_address",
        lambda *args: (200, "text/html", page),
    )
    acquired = collect()
    assert acquired["source_records"][0]["source_updated_at"] is None


@pytest.mark.parametrize(
    "status, error", [(404, "http_status_404"), (503, "http_status_503")]
)
def test_http_failure_stays_distinct_from_unavailable_and_empty(
    monkeypatch, status, error
):
    monkeypatch.setattr(
        acquisition,
        "_fetch_with_validated_address",
        lambda *args: (status, "text/plain", b"failure"),
    )
    acquired = collect(deadline_utc=time.time() + 2)
    result = (
        research()
        .build_research_result(
            acquired=acquired,
            discovery_outcome="completed",
            attempts=[
                {"url": URL, "state": "failed", "record_sha256": None, "error": error}
            ],
            deadline_utc=time.time() + 2,
            card_metadata=METADATA,
        )
        .to_value()
    )
    assert "acquisition_" + error in result["limitations"]
    assert "discovery_unavailable" not in result["limitations"]


def test_real_body_reader_detects_excess_and_rebounds_each_stage(monkeypatch):
    class Socket:
        def settimeout(self, value):
            assert 0 < value <= 0.5

    class Response:
        status = 200
        remaining = 400001

        def getheader(self, key, default):
            return "text/html" if key == "Content-Type" else default

        def read1(self, count):
            size = min(count, self.remaining)
            self.remaining -= size
            return b"x" * size

    class Connection:
        sock = Socket()

        def __init__(self, *args):
            pass

        def connect(self):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(acquisition, "_ValidatedAddressHTTPSConnection", Connection)
    with pytest.raises(ValueError, match="source_body_too_large"):
        acquisition._fetch_with_validated_address(URL, 0.5, "93.184.216.34")


def test_attempt_binding_rejects_missing_or_tampered_record(monkeypatch):
    monkeypatch.setattr(
        acquisition,
        "_fetch_with_validated_address",
        lambda *args: (200, "text/html", b"Alpha Mage"),
    )
    acquired = collect()
    attempts = completed_attempts(acquired)
    attempts[0]["record_sha256"] = DIGEST
    with pytest.raises(ValueError, match="research_attempt_record_mismatch"):
        research().build_research_result(
            acquired=acquired,
            discovery_outcome="completed",
            attempts=attempts,
            deadline_utc=time.time(),
            card_metadata=METADATA,
        )


def test_shared_deadline_and_page_count_are_not_reset(monkeypatch):
    def slow(*args):
        time.sleep(0.07)
        return 200, "text/html", b"Alpha Mage"

    monkeypatch.setattr(acquisition, "_fetch_with_validated_address", slow)
    started = time.monotonic()
    result = acquisition.collect_public_source_records(
        deck_name="MyDeck",
        deck_identity=IDENTITY,
        source_urls=[URL, URL + "2", URL + "3"],
        resolver=lambda host: ["93.184.216.34"],
        deadline_utc=time.time() + 0.12,
    )
    assert time.monotonic() - started < 0.5
    assert len(result["source_records"]) == 1
    assert len(result["source_acquisition_report"]["failures"]) == 2
    with pytest.raises(ValueError, match="research_page_limit_exceeded"):
        acquisition.collect_public_source_records(
            deck_name="MyDeck",
            deck_identity=IDENTITY,
            source_urls=[URL + str(i) for i in range(4)],
            deadline_utc=time.time() + 2,
        )


def test_dns_consumes_the_same_per_page_request_budget(monkeypatch):
    def resolve(host):
        time.sleep(0.07)
        return ["93.184.216.34"]

    def fetch(*args):
        time.sleep(0.07)
        return 200, "text/html", b"Alpha Mage"

    monkeypatch.setattr(acquisition, "_fetch_with_validated_address", fetch)
    result = acquisition.collect_public_source_records(
        deck_name="MyDeck",
        deck_identity=IDENTITY,
        source_urls=[URL],
        resolver=resolve,
        deadline_utc=time.time() + 5,
        timeout_seconds=0.1,
    )
    assert result["source_records"] == []


def test_request_accepts_canonical_deck_identity_shapes():
    identity = {**IDENTITY, "deck_fingerprint": "a" * 64, "format": "FT_WILD"}
    doc = research().build_research_request(
        run_id="run-1", deck_identity=identity, captured_input_sha256=DIGEST, queries=()
    )
    assert "Wild" in doc.to_value()["queries"][0]


def test_delayed_worker_never_starts_a_stage_after_deadline(monkeypatch):
    started = []

    class DelayedThread:
        def __init__(self, *, target, daemon):
            self.target = target

        def start(self):
            time.sleep(0.03)
            self.target()

    def forbidden():
        started.append("network")

    monkeypatch.setattr(acquisition, "Thread", DelayedThread)
    with pytest.raises(TimeoutError, match="research_budget_exhausted"):
        acquisition._bounded_stage(
            forbidden, deadline_utc=time.time() + 0.01, timeout_seconds=10
        )
    assert started == []


def test_supplied_enriched_queries_keep_priority_without_changing_identity():
    identity = {key: value for key, value in IDENTITY.items() if key != "class"}
    queries = (
        "Wild MAGE Alpha Mage Beta Spell guide mulligan",
        "Wild MAGE Alpha Mage Beta Spell strategic interactions",
    )
    request = research().build_research_request(
        run_id="run-1", deck_identity=identity,
        captured_input_sha256=DIGEST, queries=queries,
    ).to_value()
    assert request["queries"] == list(queries)
    assert request["deck_identity"] == identity
    assert "class" not in request["deck_identity"]


@pytest.mark.parametrize("stage", [
    "extract_visible_text", "_deck_match_evidence", "classify_source_evidence",
])
def test_post_fetch_processing_is_bounded_and_cannot_publish_late(monkeypatch, stage):
    release = Event()
    finished = Event()
    original = getattr(acquisition, stage)

    def delayed(*args, **kwargs):
        try:
            release.wait(0.8)
            return original(*args, **kwargs)
        finally:
            finished.set()

    monkeypatch.setattr(acquisition, stage, delayed)
    monkeypatch.setattr(acquisition, "_fetch_with_validated_address",
                        lambda *args: (200, "text/html", b"Alpha Mage"))
    started = time.monotonic()
    result = None
    try:
        result = collect(deadline_utc=time.time() + 0.03)
        assert time.monotonic() - started < 0.3
        assert result["source_records"] == []
        assert result["source_acquisition_report"]["failures"] == [
            {"url": URL, "error": "research_budget_exhausted"},
        ]
    finally:
        release.set()
        assert finished.wait(1)
    assert result["source_records"] == []
