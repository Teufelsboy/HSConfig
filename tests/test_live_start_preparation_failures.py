from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

import hsconfig.live_start_controller as controller
import hsconfig.live_start_session as session
from hsconfig.live_start_session import load_live_start_session
from hsconfig.operator_profile import enable_operator_profile
from hsconfig.package_request import FrozenJsonDocument
from hsconfig.starter_context import build_single_candidate_starter_context
from tests.helpers.package_byte_contract import (
    _offline_build_inputs,
    _offline_network_and_card_data,
)
from tests.test_live_start_controller import _frozen_live_start_inputs


DECK_CODE = "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA="
PRIVATE_CAUSE = "private raw acquisition log " * 2000


@pytest.fixture
def local_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(state))
    return state


def _request(**changes: object) -> controller.LiveStartRequest:
    return controller.LiveStartRequest(**{
        "deck_name": "ShadowPriest", "deck_code": DECK_CODE,
        "preview_requested": True, **changes,
    })


def _profile(tmp_path: Path) -> None:
    (tmp_path / "runtime").mkdir()
    (tmp_path / "outputs").mkdir()
    enable_operator_profile(
        runtime_root=tmp_path / "runtime",
        output_base_root=tmp_path / "outputs",
        expected_predecessor_sha256=None,
    )


def _assert_pre_session(
    result: object, local_state: Path, *, name: str | None,
    status: str = "FAILED_PRESERVED", unique: int | None = None,
) -> None:
    assert isinstance(result, controller.LiveStartResult)
    assert result.status == status
    assert result.run_root is None
    value = result.summary.to_value()
    assert value["deck_name"] is None if name is None else value["deck_name"] == name
    assert value["run_root"] is None
    assert value["candidate_revision"] is None
    assert value["review_confidence"] is None
    assert value["unique_main_deck_cards"] == unique
    assert value["configured_cards"] is None
    assert value["deliberately_unconfigured_cards"] is None
    assert value["retained_safe_state"] == "NO_SESSION_OR_RUNTIME_WRITE"
    assert value["error_code"] in {"deck_or_input_invalid", "operator_profile_required"}
    assert len(result.summary.canonical_json) <= 16 * 1024
    assert b"private raw acquisition log" not in result.summary.canonical_json
    digest = value.pop("content_sha256")
    assert digest == "sha256:" + sha256(
        FrozenJsonDocument.from_value(value).canonical_json
    ).hexdigest()
    assert not (local_state / "HSConfig" / "runs").exists()
    assert not list(local_state.rglob("summary.json"))


@pytest.mark.parametrize(
    "name", [None, "", " bad ", "bad\nname", "x" * 17000],
    ids=["non-string", "empty", "spaces", "control", "oversize"],
)
def test_invalid_name_is_not_echoed_into_bounded_failure(
    name: object, local_state: Path,
) -> None:
    result = controller.prepare_live_start(_request(deck_name=name))
    _assert_pre_session(result, local_state, name=None)


def test_invalid_code_retains_safe_name_but_no_roster(local_state: Path) -> None:
    result = controller.prepare_live_start(_request(deck_code="not a deck"))
    _assert_pre_session(result, local_state, name="ShadowPriest")


@pytest.mark.parametrize("drifted", [False, True])
def test_missing_or_drifted_profile_precedes_capture(
    tmp_path: Path, local_state: Path, monkeypatch: pytest.MonkeyPatch,
    drifted: bool,
) -> None:
    if drifted:
        _profile(tmp_path)
        (tmp_path / "runtime").rename(tmp_path / "old-runtime")
        (tmp_path / "runtime").mkdir()

    def unexpected_capture(*_args: object) -> None:
        pytest.fail("profile failure reached acquisition")

    monkeypatch.setattr(controller, "_capture_live_start_inputs", unexpected_capture)
    result = controller.prepare_live_start(_request())
    _assert_pre_session(result, local_state, name="ShadowPriest", status="PROFILE_REQUIRED")
    if drifted:
        assert list((tmp_path / "outputs").iterdir()) == []
        assert list((tmp_path / "runtime").iterdir()) == []


@pytest.mark.parametrize("after_roster", [False, True])
def test_acquisition_failure_uses_only_completely_validated_roster_count(
    tmp_path: Path, local_state: Path, monkeypatch: pytest.MonkeyPatch,
    after_roster: bool,
) -> None:
    _profile(tmp_path)
    _decks, cards, database = _offline_build_inputs()

    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise OSError(PRIVATE_CAUSE)

    monkeypatch.setattr(controller, "fetch_latest_cards", lambda **_kwargs: deepcopy(cards))
    monkeypatch.setattr(controller, "fetch_latest_collectible_cards", lambda **_kwargs: deepcopy(cards))
    monkeypatch.setattr(
        controller, "load_globalvalues_baseline" if after_roster else "fetch_latest_cards",
        unavailable,
    )
    with _offline_network_and_card_data(cards, database):
        result = controller.prepare_live_start(_request())
    _assert_pre_session(result, local_state, name="ShadowPriest", unique=16 if after_roster else None)
    assert list((tmp_path / "outputs").iterdir()) == []
    assert list((tmp_path / "runtime").iterdir()) == []


def test_context_io_failure_after_session_creation_is_durable_bounded_failure(
    tmp_path: Path, local_state: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    code, frozen = _frozen_live_start_inputs(tmp_path)
    monkeypatch.setattr(controller, "_capture_live_start_inputs", lambda *_args: frozen)

    def unavailable(**_kwargs: object) -> None:
        raise OSError(PRIVATE_CAUSE)

    monkeypatch.setattr(controller, "_materialize_starter_context", unavailable)
    result = controller.prepare_live_start(_request(deck_code=code))
    assert isinstance(result, controller.LiveStartResult)
    assert result.status == "FAILED_PRESERVED"
    assert result.run_root is not None
    current = load_live_start_session(result.run_root)
    assert current.terminal_status == "FAILED_PRESERVED"
    value = result.summary.to_value()
    assert value["unique_main_deck_cards"] == 16
    assert value["configured_cards"] is None
    assert value["deliberately_unconfigured_cards"] is None
    assert b"private raw acquisition log" not in result.summary.canonical_json
    assert (result.run_root / "result/summary.json").read_bytes() == result.summary.canonical_json
    assert list((tmp_path / "outputs").iterdir()) == []
    assert list((tmp_path / "runtime").iterdir()) == []


def test_partial_resolved_roster_never_supplies_a_failure_count(
    tmp_path: Path, local_state: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _profile(tmp_path)
    decks, cards, database = _offline_build_inputs()
    database.pop(decks["ShadowPriest"][0]["dbf_id"])
    monkeypatch.setattr(controller, "fetch_latest_cards", lambda **_kwargs: deepcopy(cards))
    monkeypatch.setattr(controller, "fetch_latest_collectible_cards", lambda **_kwargs: deepcopy(cards))

    def unavailable(*_args: object) -> None:
        raise OSError(PRIVATE_CAUSE)

    monkeypatch.setattr(controller, "load_globalvalues_baseline", unavailable)
    with _offline_network_and_card_data(cards, database):
        result = controller.prepare_live_start(_request())
    _assert_pre_session(result, local_state, name="ShadowPriest")
    assert list((tmp_path / "outputs").iterdir()) == []
    assert list((tmp_path / "runtime").iterdir()) == []


def test_early_failure_renders_coverage_unavailable_not_unconfigured(
    tmp_path: Path, local_state: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    code, frozen = _frozen_live_start_inputs(tmp_path)
    monkeypatch.setattr(controller, "_capture_live_start_inputs", lambda *_args: frozen)
    prepared = controller.prepare_live_start(_request(deck_code=code))
    assert isinstance(prepared, controller.LiveStartPreparation)
    current = load_live_start_session(prepared.run_root)
    intent = controller._failure_result_intent(
        current=current, context=build_single_candidate_starter_context(frozen),
        candidate=None, error_code="deck_or_input_invalid",
    )
    _summary, markdown = session._live_start_result_payloads(intent)
    assert b"- Card coverage: unavailable\n" in markdown
    assert b"deliberately unconfigured" not in markdown


@pytest.mark.parametrize(
    "error_type",
    [session.SessionCapabilityError, session.SessionConflictError, session.SessionValidationError],
)
def test_context_authority_errors_are_not_relabelled_as_input_failure(
    tmp_path: Path, local_state: Path, monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
) -> None:
    code, frozen = _frozen_live_start_inputs(tmp_path)
    monkeypatch.setattr(controller, "_capture_live_start_inputs", lambda *_args: frozen)

    def rejected(**_kwargs: object) -> None:
        raise error_type("bound_context_authority_changed")

    monkeypatch.setattr(controller, "_materialize_starter_context", rejected)
    with pytest.raises(error_type, match="bound_context_authority_changed"):
        controller.prepare_live_start(_request(deck_code=code))
    assert not list(local_state.rglob("summary.json"))
    assert list((tmp_path / "outputs").iterdir()) == []
    assert list((tmp_path / "runtime").iterdir()) == []
