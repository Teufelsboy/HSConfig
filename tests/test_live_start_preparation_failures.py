from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

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


_LEGACY_FAILURE_BYTES = b'{"apply_attempt_id":null,"candidate_revision":1,"configured_cards":null,"content_sha256":"sha256:50e3d6433542e622a3161bfd2d1a99998e711d154d56b04fe928577d081108fb","deck_config_ini_sha256":null,"deck_name":"ShadowPriest","deliberately_unconfigured_cards":null,"error_code":"deck_or_input_invalid","intent_kind":"live_start_result_intent","last_apply_receipt_sha256":null,"package_root_sha256":null,"physical_disposition":null,"publication_content_root_sha256":null,"publication_revision":null,"raw_apply_status":null,"retained_attempt_record_identity":null,"retained_attempt_record_path":null,"retained_attempt_record_sha256":null,"retained_candidate_identity":null,"retained_journal_identity":null,"retained_journal_path":null,"retained_journal_sha256":null,"retained_safe_state":"NO_PUBLICATION_OR_RUNTIME_WRITE","retained_target_owner_journal_identity":null,"retained_target_owner_journal_path":null,"retained_target_owner_journal_sha256":null,"review_confidence":null,"run_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","runtime_admission_identity":null,"runtime_admission_parent_identity":null,"runtime_admission_path":null,"runtime_admission_sha256":null,"runtime_match_sha256":null,"runtime_match_status":"not_run","runtime_state_sha256":null,"schema_version":1,"terminal_status":"FAILED_PRESERVED","unique_main_deck_cards":2,"visible_limitations":[]}'


def _assert_valid_intent(intent):
    value = dict(intent)
    digest = value.pop("content_sha256")
    checked = session.seal_embedded_document("result_intent", value)
    assert checked["content_sha256"] == digest


@pytest.mark.parametrize("schema,with_context", [(1, False), (1, True), (2, False), (2, True)])
def test_failure_constructor_preserves_legacy_bytes_and_frozen_quality(schema, with_context):
    current = SimpleNamespace(schema_version=schema, publication_binding=None, run_id="a" * 32,
        deck_name="ShadowPriest", candidate_revision=1,
        input_snapshot_manifest_sha256="sha256:" + "1" * 64,
        research_binding={"request_sha256": "sha256:" + "2" * 64})
    limitations = ["discovery_unavailable", "no_useful_observations", "source_context_incomplete"]
    frozen = SimpleNamespace(
        deck=FrozenJsonDocument.from_value({"deck_identity": {"cards": [{}, {}]}}),
        manifest=SimpleNamespace(document=SimpleNamespace(content_sha256=current.input_snapshot_manifest_sha256)),
        quality_inputs=FrozenJsonDocument.from_value({"research_request_sha256": current.research_binding["request_sha256"],
                                                     "research_result": {"limitations": limitations}}))
    context = None if not with_context else SimpleNamespace(document=FrozenJsonDocument.from_value({
        "schema_version": 3 if schema == 2 else 2, "cards": [{}, {}],
        "source_evidence": {"guide_builder_receipt": {"source_depth_status": "source_backed"},
                            "guide_sources_summary": {"source_depth_status": "source_backed"}},
        "research_evidence": {"limitations": limitations}}))
    intent = controller._failure_result_intent(current=current, context=context, candidate=None,
                                              error_code="deck_or_input_invalid", frozen=frozen)
    _assert_valid_intent(intent)
    if schema == 1:
        assert FrozenJsonDocument.from_value(dict(intent)).canonical_json == _LEGACY_FAILURE_BYTES
    else:
        assert list(intent["visible_limitations"]) == sorted([
            "Guide discovery was unavailable.", "No useful card-specific guide observations were retained.",
            "Some selected guide excerpts omit adjacent context; review the limitation before relying on them.",
        ])


@pytest.mark.parametrize("defect", ["missing", "manifest", "request"])
def test_contextless_quality_failure_rejects_missing_or_mismatched_frozen_quality(defect):
    current = SimpleNamespace(schema_version=2, publication_binding=None, run_id="a" * 32,
        deck_name="ShadowPriest", candidate_revision=1, input_snapshot_manifest_sha256="sha256:" + "1" * 64,
        research_binding={"request_sha256": "sha256:" + "2" * 64})
    frozen = SimpleNamespace(
        deck=FrozenJsonDocument.from_value({"deck_identity": {"cards": [{}, {}]}}),
        manifest=SimpleNamespace(document=SimpleNamespace(content_sha256="sha256:" + ("0" if defect == "manifest" else "1") * 64)),
        quality_inputs=None if defect == "missing" else FrozenJsonDocument.from_value({
            "research_request_sha256": "sha256:" + ("0" if defect == "request" else "2") * 64,
            "research_result": {"limitations": []}}))
    with pytest.raises(controller.SessionConflictError):
        controller._failure_result_intent(current=current, context=None, candidate=None,
                                         error_code="deck_or_input_invalid", frozen=frozen)


class _CapturedFailureIntent(Exception):
    pass


@pytest.mark.parametrize("schema", [1, 2])
def test_contextless_quality_failure_preserves_frozen_research_at_actual_terminalize_seam(
    tmp_path, local_state, monkeypatch, schema
):
    if schema == 2:
        from tests.test_quality_live_start_controller import quality_request
        from tests.test_quality_start_summary import _frozen_quality
        request = quality_request.__wrapped__(tmp_path, monkeypatch)
        prepared = _frozen_quality(request, tmp_path)
    else:
        code, frozen = _frozen_live_start_inputs(tmp_path)
        monkeypatch.setattr(controller, "_capture_live_start_inputs", lambda *_: frozen)
        prepared = controller._prepare_legacy_live_start(_request(deck_code=code))
    root = prepared.run_root
    current = load_live_start_session(root)
    before = {p.name: p.read_bytes() for p in (root / "inputs").glob("*.json")}
    captured = []

    def stop(**kwargs):
        captured.append(kwargs["changes"]["result_intent"])
        raise _CapturedFailureIntent

    monkeypatch.setattr(session, "_transition_receipt_authorized_under_lock", stop)
    monkeypatch.setattr(controller, "_materialize_starter_context", lambda **_: pytest.fail("materialization"))
    monkeypatch.setattr(controller, "fetch_card_snapshot", lambda **_: pytest.fail("acquisition"))
    monkeypatch.setattr(controller, "plan_apply_package", lambda **_: pytest.fail("runtime"))
    with session.lease_live_start_session(root) as lease:
        with pytest.raises(_CapturedFailureIntent):
            controller._terminalize_preapply_failure_under_lock(
                session_lease=lease, current=current, context=None, candidate=None,
                error_code="deck_or_input_invalid")
    intent = captured[0]
    _assert_valid_intent(intent)
    assert intent["unique_main_deck_cards"] == 16
    assert intent["configured_cards"] is None
    assert intent["runtime_match_status"] == "not_run"
    assert {p.name: p.read_bytes() for p in (root / "inputs").glob("*.json")} == before
    if schema == 2:
        assert list(intent["visible_limitations"]) == sorted([
            "Guide discovery was unavailable.", "No useful card-specific guide observations were retained.",
            "No retained observation has verified exact-deck guide identity.",
        ])
    else:
        expected = FrozenJsonDocument.from_json_bytes(_LEGACY_FAILURE_BYTES).to_value()
        expected.update(run_id=current.run_id, unique_main_deck_cards=16)
        expected.pop("content_sha256")
        expected["content_sha256"] = "sha256:" + sha256(session._canonical_json(expected)).hexdigest()
        assert FrozenJsonDocument.from_value(dict(intent)).canonical_json == FrozenJsonDocument.from_value(expected).canonical_json


@pytest.mark.parametrize("defect", ["missing", "request"])
def test_contextless_quality_failure_invalid_frozen_input_stops_before_intent_capture(
    tmp_path, monkeypatch, defect
):
    from tests.test_quality_live_start_controller import quality_request
    from tests.test_quality_start_summary import _frozen_quality
    request = quality_request.__wrapped__(tmp_path, monkeypatch)
    prepared = _frozen_quality(request, tmp_path)
    current = load_live_start_session(prepared.run_root)
    path = prepared.run_root / "inputs/quality.json"
    if defect == "missing":
        path.unlink()
    else:
        quality = FrozenJsonDocument.from_json_bytes(path.read_bytes()).to_value()
        quality["research_request_sha256"] = "sha256:" + "0" * 64
        path.write_bytes(FrozenJsonDocument.from_value(quality).canonical_json)
    monkeypatch.setattr(session, "_transition_receipt_authorized_under_lock", lambda **_: pytest.fail("invalid quality reached intent capture"))
    with session.lease_live_start_session(prepared.run_root) as lease:
        with pytest.raises((controller.SessionConflictError, OSError)):
            controller._terminalize_preapply_failure_under_lock(
                session_lease=lease, current=current, context=None, candidate=None,
                error_code="deck_or_input_invalid")


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
    result = controller._prepare_legacy_live_start(_request(deck_name=name))
    _assert_pre_session(result, local_state, name=None)


def test_invalid_code_retains_safe_name_but_no_roster(local_state: Path) -> None:
    result = controller._prepare_legacy_live_start(_request(deck_code="not a deck"))
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
    result = controller._prepare_legacy_live_start(_request())
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
        result = controller._prepare_legacy_live_start(_request())
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
    result = controller._prepare_legacy_live_start(_request(deck_code=code))
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
        result = controller._prepare_legacy_live_start(_request())
    _assert_pre_session(result, local_state, name="ShadowPriest")
    assert list((tmp_path / "outputs").iterdir()) == []
    assert list((tmp_path / "runtime").iterdir()) == []


def test_early_failure_renders_coverage_unavailable_not_unconfigured(
    tmp_path: Path, local_state: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    code, frozen = _frozen_live_start_inputs(tmp_path)
    monkeypatch.setattr(controller, "_capture_live_start_inputs", lambda *_args: frozen)
    prepared = controller._prepare_legacy_live_start(_request(deck_code=code))
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
        controller._prepare_legacy_live_start(_request(deck_code=code))
    assert not list(local_state.rglob("summary.json"))
    assert list((tmp_path / "outputs").iterdir()) == []
    assert list((tmp_path / "runtime").iterdir()) == []
