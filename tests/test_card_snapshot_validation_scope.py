"""Acquisition-local reuse must never turn mutable data into authority."""

from contextvars import ContextVar
from threading import Event
from time import time

import pytest
from hearthstone.deckstrings import FormatType, write_deckstring

import hsconfig.card_snapshot as snapshots
from hsconfig.deckstring_decode import decode_deck_code_from_snapshot
from hsconfig.package_request import FrozenJsonDocument
from hsconfig.source_acquisition import _bounded_stage


@pytest.fixture
def snapshot():
    return snapshots.build_card_snapshot([
        {"id": "HERO", "dbfId": 1001, "type": "HERO", "name": "Hero"},
        {"id": "CARD", "dbfId": 1002, "type": "MINION", "name": "Card"},
    ], captured_at="2026-09-17")


@pytest.fixture
def checked_rows(monkeypatch):
    rows = []
    original = snapshots._validated_normalized_row

    def checked(row):
        rows.append(row["id"])
        return original(row)

    monkeypatch.setattr(snapshots, "_validated_normalized_row", checked)
    return rows


def test_reuse_returns_fresh_projections_and_ends_with_scope(snapshot, checked_rows):
    with snapshots.card_snapshot_validation_scope(snapshot):
        first = snapshots.validated_card_snapshot(snapshot)
        first["full_cards"][0]["name"] = "Tampered"
        first["dbf_to_card_id"]["1002"] = "HERO"
        second = snapshots.validated_card_snapshot(snapshot)
        assert second["full_cards"][0]["name"] == "Card"
        assert second["dbf_to_card_id"]["1002"] == "CARD"
        assert checked_rows == ["CARD", "HERO"]
    snapshots.validated_card_snapshot(snapshot)
    assert checked_rows == ["CARD", "HERO"] * 2


def test_nested_entry_revalidates_and_exception_restores_outer(snapshot, checked_rows):
    with snapshots.card_snapshot_validation_scope(snapshot):
        with pytest.raises(RuntimeError, match="stop"):
            with snapshots.card_snapshot_validation_scope(snapshot):
                raise RuntimeError("stop")
        snapshots.validated_card_snapshot(snapshot)
        assert checked_rows == ["CARD", "HERO"] * 2
    snapshots.validated_card_snapshot(snapshot)
    assert checked_rows == ["CARD", "HERO"] * 3


@pytest.mark.parametrize("defect", ["digest", "index", "projection", "type"])
def test_other_invalid_snapshot_cannot_use_active_scope(snapshot, defect):
    value = snapshot.to_value()
    if defect == "digest":
        value["dataset_sha256"] = "sha256:" + "0" * 64
    elif defect == "index":
        value["dbf_to_card_id"]["1002"] = "HERO"
    elif defect == "projection":
        value["full_cards"][0]["cost"] = True
    invalid = value if defect == "type" else FrozenJsonDocument.from_value(value)
    with snapshots.card_snapshot_validation_scope(snapshot):
        with pytest.raises(ValueError, match="^card_snapshot_invalid$"):
            snapshots.validated_card_snapshot(invalid)
        with pytest.raises(ValueError, match="^card_snapshot_invalid$"):
            with snapshots.card_snapshot_validation_scope(invalid):
                pytest.fail("invalid scope entered")
        assert snapshots.validated_card_snapshot(snapshot)["dbf_to_card_id"]["1002"] == "CARD"


def test_distinct_valid_snapshot_is_fully_checked(snapshot, checked_rows):
    other = FrozenJsonDocument.from_json_bytes(snapshot.canonical_json)
    assert other.canonical_json is not snapshot.canonical_json
    with snapshots.card_snapshot_validation_scope(snapshot):
        assert snapshots.validated_card_snapshot(other)["dbf_to_card_id"]["1002"] == "CARD"
        assert checked_rows == ["CARD", "HERO"] * 2


def test_worker_reuses_snapshot_without_inheriting_other_context(snapshot, checked_rows):
    unrelated_authority = ContextVar("unrelated_authority", default=None)
    code = write_deckstring([(1002, 2)], [1001], FormatType.FT_WILD)
    token = unrelated_authority.set("must-not-leak")
    try:
        with snapshots.card_snapshot_validation_scope(snapshot):
            decoded, unrelated = _bounded_stage(
                lambda: (decode_deck_code_from_snapshot(code, snapshot), unrelated_authority.get()),
                deadline_utc=time() + 2, timeout_seconds=2,
            )
        assert decoded["cards"][0]["card_id"] == "CARD"
        assert unrelated is None
        assert unrelated_authority.get() == "must-not-leak"
        assert checked_rows == ["CARD", "HERO"]
    finally:
        unrelated_authority.reset(token)


def test_timed_out_worker_cannot_extend_parent_scope(snapshot, checked_rows):
    started, release, finished = Event(), Event(), Event()

    def delayed():
        started.set()
        release.wait(2)
        try:
            return snapshots.validated_card_snapshot(snapshot)
        finally:
            finished.set()

    try:
        with snapshots.card_snapshot_validation_scope(snapshot):
            with pytest.raises(TimeoutError, match="research_budget_exhausted"):
                _bounded_stage(delayed, deadline_utc=time() + 0.05, timeout_seconds=0.05)
        assert started.is_set()
        release.set()
        assert finished.wait(2)
        assert checked_rows == ["CARD", "HERO"]
        snapshots.validated_card_snapshot(snapshot)
        assert checked_rows == ["CARD", "HERO"] * 2
    finally:
        release.set()
