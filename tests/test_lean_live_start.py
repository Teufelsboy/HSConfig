"""Reject malformed new intake before sealing a session or touching runtime."""

import base64
from dataclasses import replace

import pytest
from hearthstone.deckstrings import parse_deckstring, write_deckstring

import hsconfig.live_start_controller as controller
import hsconfig.live_start_research as research
from hsconfig.deckstring_decode import decode_deck_code_from_snapshot
from tests.test_quality_live_start_controller import quality_request as _quality_request


@pytest.fixture
def quality_request(tmp_path, monkeypatch):
    return _quality_request.__wrapped__(tmp_path, monkeypatch)


@pytest.fixture(
    params=[
        ((), b"\x00"),
        ((813, 999999), b"\x02\xad\x06\xbf\x84\x3d"),
        ((999999, 813), b"\x02\xbf\x84\x3d\xad\x06"),
    ],
    ids=["zero-heroes", "two-heroes", "two-heroes-reversed"],
)
def invalid_hero_count_request(quality_request, request):
    heroes, encoded_heroes = request.param
    cards, valid_heroes, deck_format, sideboards = parse_deckstring(
        quality_request.deck_code
    )
    assert cards and valid_heroes == [813]
    assert "999999" not in controller.fetch_card_snapshot().to_value()["dbf_to_card_id"]
    original = base64.b64decode(quality_request.deck_code)
    assert original[:3] == bytes((0, 1, int(deck_format)))
    assert original[3:6] == b"\x01\xad\x06"
    # The normal writer requires one hero. Replace only that byte section,
    # preserving the real roster, format and sideboards exactly.
    code = base64.b64encode(original[:3] + encoded_heroes + original[6:]).decode()
    assert parse_deckstring(code) == (cards, sorted(heroes), deck_format, sideboards)
    return replace(quality_request, deck_code=code)


def _forbidden(*_args, **_kwargs):
    pytest.fail("invalid new intake reached a forbidden later operation")


def _assert_no_session_result(result, tmp_path):
    assert result.status == "FAILED_PRESERVED"
    assert result.run_root is None
    summary = result.summary.to_value()
    assert summary["error_code"] == "deck_or_input_invalid"
    assert summary["retained_safe_state"] == "NO_SESSION_OR_RUNTIME_WRITE"
    assert not (tmp_path / "local-app-data/HSConfig/runs").exists()
    assert not list((tmp_path / "outputs").iterdir())
    assert not list((tmp_path / "runtime").iterdir())


def test_request_validator_rejects_real_zero_or_multiple_hero_codes(
    invalid_hero_count_request,
):
    with pytest.raises(ValueError, match="^live_start_deck_code_invalid$"):
        controller._validate_live_start_request(invalid_hero_count_request)


@pytest.mark.parametrize("preview_requested", [False, True])
def test_new_intake_rejects_hero_count_before_profile_or_acquisition(
    invalid_hero_count_request, monkeypatch, tmp_path, preview_requested
):
    monkeypatch.setattr(controller, "load_operator_profile", _forbidden)
    monkeypatch.setattr(controller, "fetch_card_snapshot", _forbidden)
    monkeypatch.setattr(controller._session, "create_live_start_session", _forbidden)
    result = controller.prepare_live_start(
        replace(invalid_hero_count_request, preview_requested=preview_requested)
    )
    _assert_no_session_result(result, tmp_path)


@pytest.mark.parametrize("preview_requested", [False, True])
def test_new_quality_intake_rejects_resolved_minion_hero_before_baseline_or_session(
    quality_request, monkeypatch, tmp_path, preview_requested
):
    snapshot = controller.fetch_card_snapshot()
    captured = snapshot.to_value()
    rows = {row["id"]: row for row in captured["full_cards"]}
    assert captured["dbf_to_card_id"]["64443"] == "SW_448"
    assert rows["SW_448"]["type"] == "MINION"
    assert rows["SW_448"]["card_class"] == "PRIEST"
    assert captured["dbf_to_card_id"]["813"] == "HERO_09"
    assert rows["HERO_09"]["type"] == "HERO"
    cards, heroes, deck_format, sideboards = parse_deckstring(quality_request.deck_code)
    assert cards and heroes == [813]
    code = write_deckstring(cards, [64443], deck_format, sideboards)
    assert parse_deckstring(code) == (cards, [64443], deck_format, sideboards)
    decoded = decode_deck_code_from_snapshot(code, snapshot)
    assert decoded["hero"]["card_id"] == "SW_448"
    assert decoded["hero"]["type"] == "MINION"

    calls = []
    original_load_profile = controller.load_operator_profile

    def load_profile(*args, **kwargs):
        calls.append("profile")
        return original_load_profile(*args, **kwargs)

    def fetch_snapshot(**_kwargs):
        calls.append("snapshot")
        return snapshot

    monkeypatch.setattr(controller, "load_operator_profile", load_profile)
    monkeypatch.setattr(controller, "fetch_card_snapshot", fetch_snapshot)
    monkeypatch.setattr(controller, "load_globalvalues_baseline", _forbidden)
    monkeypatch.setattr(research, "build_research_request", _forbidden)
    monkeypatch.setattr(controller._session, "create_live_start_session", _forbidden)
    result = controller.prepare_quality_live_start(
        replace(quality_request, deck_code=code, preview_requested=preview_requested)
    )
    _assert_no_session_result(result, tmp_path)
    assert calls == ["profile", "snapshot"]
