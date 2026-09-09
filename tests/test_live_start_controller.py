from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import hsconfig.live_start_controller as controller
import hsconfig.live_start_session as session
from hsconfig.input_snapshot_manifest import FrozenCompilerInputs, freeze_compiler_inputs
from hsconfig.live_start_session import LiveStartPhase, load_live_start_session
from hsconfig.operator_profile import (
    disable_operator_profile,
    derive_deck_output_binding,
    enable_operator_profile,
    load_operator_profile,
)
from hsconfig.package_request import FrozenJsonDocument, PackageResolutionSnapshot
from hsconfig.starter_candidate import validate_starter_candidate
from hsconfig.starter_context import build_single_candidate_starter_context
from tests.helpers.audited_package_request import (
    audited_request_with_frozen_input_projections,
)
from tests.test_starter_candidate import sealed_single_candidate
from tests.test_starter_review import review_document


def _frozen_live_start_inputs(
    root: Path,
    *,
    deck_name: str = "ShadowPriest",
) -> tuple[str, FrozenCompilerInputs]:
    request, projections = audited_request_with_frozen_input_projections(
        root / "audited",
        deck_name,
    )
    runtime_root = root / "runtime"
    output_base_root = root / "outputs"
    runtime_root.mkdir(parents=True)
    output_base_root.mkdir(parents=True)
    profile = enable_operator_profile(
        runtime_root=runtime_root,
        output_base_root=output_base_root,
        expected_predecessor_sha256=None,
    )
    preconfig = request.snapshot.general_preconfig.to_value()
    preconfig["cards_payload"]["deck_code"] = str(request.invocation.deck_code)
    projections["deck"]["cards_payload"] = preconfig["cards_payload"]
    frozen = freeze_compiler_inputs(
        snapshot=PackageResolutionSnapshot.from_preconfig(preconfig),
        deck=projections["deck"],
        full_cards=projections["full_cards"],
        collectible_cards=projections["collectible_cards"],
        source_acquisition=projections["source_acquisition"],
        source_documents=projections["source_documents"],
        globalvalues_baseline=projections["globalvalues_baseline"],
        bound_date="2026-08-25",
        runtime_grammar_version="visionai-runtime-v1",
        compiler_contract_id="hsconfig-live-start-v1",
        operator_profile=profile,
        deck_output_binding=derive_deck_output_binding(profile, deck_name),
    )
    return str(request.invocation.deck_code), frozen


def _write_unsigned_document(path: Path, document: object) -> None:
    value = document.to_value()
    value.pop("content_sha256")
    path.write_bytes(FrozenJsonDocument.from_value(value).canonical_json)


def _prepared_run(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    preview_requested: bool = True,
) -> tuple[controller.LiveStartPreparation, FrozenCompilerInputs]:
    deck_code, frozen = _frozen_live_start_inputs(root)
    monkeypatch.setattr(
        controller,
        "_capture_live_start_inputs",
        lambda *_args: frozen,
    )
    prepared = controller._prepare_legacy_live_start(
        controller.LiveStartRequest(
            deck_name="ShadowPriest",
            deck_code=deck_code,
            preview_requested=preview_requested,
        )
    )
    assert isinstance(prepared, controller.LiveStartPreparation)
    return prepared, frozen


def _approved_run(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    preview_requested: bool = True,
) -> controller.LiveStartPreparation:
    prepared, frozen = _prepared_run(
        root, monkeypatch, preview_requested=preview_requested
    )
    context = build_single_candidate_starter_context(frozen)
    document = sealed_single_candidate(context)
    candidate_path = root / "candidate.json"
    _write_unsigned_document(candidate_path, document)
    controller.validate_live_start_candidate(
        session_root=prepared.run_root, draft_path=candidate_path
    )
    candidate = validate_starter_candidate(document, context=context)
    review = review_document(SimpleNamespace(context=context, candidate=candidate))
    review_path = root / "review.json"
    _write_unsigned_document(review_path, review)
    controller.validate_live_start_review(
        session_root=prepared.run_root, draft_path=review_path
    )
    return prepared


def test_prepare_requires_only_deck_name_and_code_after_profile_enablement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_app_data = tmp_path / "local-app-data"
    local_app_data.mkdir()
    with patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}):
        deck_code, frozen = _frozen_live_start_inputs(tmp_path)
        captures: list[tuple[str, str]] = []

        def capture(
            request: controller.LiveStartRequest,
            *_args: object,
        ) -> FrozenCompilerInputs:
            captures.append((request.deck_name, request.deck_code))
            return frozen

        monkeypatch.setattr(controller, "_capture_live_start_inputs", capture)
        result = controller._prepare_legacy_live_start(
            controller.LiveStartRequest(
                deck_name="ShadowPriest",
                deck_code=deck_code,
                preview_requested=True,
            )
        )

    assert isinstance(result, controller.LiveStartPreparation)
    assert captures == [("ShadowPriest", deck_code)]
    assert result.run_root.parent == local_app_data / "HSConfig" / "runs"
    assert result.run_root.name.isascii() and len(result.run_root.name) == 32
    assert result.starter_context_path.is_file()
    assert result.starter_context_path.is_relative_to(
        local_app_data / "HSConfig" / "contexts" / result.run_root.name
    )
    assert result.candidate_revision == 1


def test_missing_or_drifted_profile_stops_before_llm_output_or_runtime_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_app_data = tmp_path / "local-app-data"
    local_app_data.mkdir()
    request, _projections = audited_request_with_frozen_input_projections(
        tmp_path / "audited",
        "ShadowPriest",
    )

    def unexpected_capture(*_args: object) -> FrozenCompilerInputs:
        raise AssertionError("input capture reached without an operator profile")

    monkeypatch.setattr(
        controller,
        "_capture_live_start_inputs",
        unexpected_capture,
    )
    with patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}):
        result = controller._prepare_legacy_live_start(
            controller.LiveStartRequest(
                deck_name="ShadowPriest",
                deck_code=str(request.invocation.deck_code),
                preview_requested=False,
            )
        )

    assert isinstance(result, controller.LiveStartResult)
    assert result.status == "PROFILE_REQUIRED"
    assert result.run_root is None
    assert result.summary.to_value() == {
        "candidate_revision": None,
        "configured_cards": None,
        "content_sha256": result.summary.to_value()["content_sha256"],
        "deck_name": "ShadowPriest",
        "deliberately_unconfigured_cards": None,
        "error_code": "operator_profile_required",
        "review_confidence": None,
        "run_root": None,
        "schema_version": 1,
        "status": "PROFILE_REQUIRED",
        "summary_kind": "live_start_pre_session_result",
        "unique_main_deck_cards": None,
        "visible_limitations": [],
        "retained_safe_state": "NO_SESSION_OR_RUNTIME_WRITE",
    }
    assert not (local_app_data / "HSConfig" / "runs").exists()


def test_prepare_always_creates_a_new_run_and_only_resume_reuses_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_app_data = tmp_path / "local-app-data"
    local_app_data.mkdir()
    with patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}):
        deck_code, frozen = _frozen_live_start_inputs(tmp_path)
        monkeypatch.setattr(
            controller,
            "_capture_live_start_inputs",
            lambda *_args: frozen,
        )
        request = controller.LiveStartRequest(
            deck_name="ShadowPriest",
            deck_code=deck_code,
            preview_requested=True,
        )

        first = controller._prepare_legacy_live_start(request)
        second = controller._prepare_legacy_live_start(request)

    assert isinstance(first, controller.LiveStartPreparation)
    assert isinstance(second, controller.LiveStartPreparation)
    assert first.run_root != second.run_root
    assert first.starter_context_path.read_bytes() == (
        second.starter_context_path.read_bytes()
    )


def test_candidate_and_approved_review_gate_each_completed_phase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_app_data = tmp_path / "local-app-data"
    local_app_data.mkdir()
    with patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}):
        prepared, frozen = _prepared_run(tmp_path, monkeypatch)
        context = build_single_candidate_starter_context(frozen)
        candidate_document = sealed_single_candidate(context)
        candidate_path = tmp_path / "candidate.json"
        _write_unsigned_document(candidate_path, candidate_document)

        candidate_receipt = controller.validate_live_start_candidate(
            session_root=prepared.run_root,
            draft_path=candidate_path,
        )
        candidate = validate_starter_candidate(
            candidate_document,
            context=context,
        )
        review = review_document(
            SimpleNamespace(context=context, candidate=candidate)
        )
        review_path = tmp_path / "review.json"
        _write_unsigned_document(review_path, review)

        review_receipt = controller.validate_live_start_review(
            session_root=prepared.run_root,
            draft_path=review_path,
        )
        completed = load_live_start_session(prepared.run_root)
        with session.lease_live_start_session(prepared.run_root) as lease:
            resumed = session.validate_resume_under_lock(
                session_lease=lease,
                expected_deck_code_sha256=completed.deck_code_sha256,
                expected_input_snapshot_manifest_sha256=(
                    completed.input_snapshot_manifest_sha256
                ),
            )

    assert candidate_receipt.to_value()["status"] == "valid"
    assert review_receipt.to_value()["review_status"] == "approved"
    assert completed.phase is LiveStartPhase.REVIEW_APPROVED
    assert resumed.content_sha256 == completed.content_sha256
    assert set(completed.artifact_bindings) >= {
        "receipts/candidate_validation.json",
        "receipts/review_validation.json",
        "starter/starter_config_candidate.json",
        "starter/starter_config_review.json",
        "starter/starter_context.json",
    }


@pytest.mark.parametrize("candidate_state", ("missing", "rejected", "validated"))
def test_finalize_requires_approved_review_before_loading_candidate_or_compiling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, candidate_state: str,
) -> None:
    local_app_data = tmp_path / "local-app-data"
    local_app_data.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    prepared, frozen = _prepared_run(tmp_path, monkeypatch)
    if candidate_state != "missing":
        context = build_single_candidate_starter_context(frozen)
        candidate_value = sealed_single_candidate(context).to_value()
        candidate_value.pop("content_sha256")
        if candidate_state == "rejected":
            candidate_value["card_dispositions"].pop()
        draft = tmp_path / "candidate.json"
        draft.write_bytes(FrozenJsonDocument.from_value(candidate_value).canonical_json)
        controller.validate_live_start_candidate(session_root=prepared.run_root, draft_path=draft)
    before = (prepared.run_root / "session.json").read_bytes()

    def premature_compile(**_kwargs: object) -> None:
        pytest.fail("unapproved candidate reached compilation")

    monkeypatch.setattr(controller, "build_frozen_live_configure_run", premature_compile)
    with pytest.raises(session.SessionConflictError, match="^live_start_review_approval_required$"):
        controller.finalize_live_start(session_root=prepared.run_root)
    assert (prepared.run_root / "session.json").read_bytes() == before
    assert list((tmp_path / "outputs").iterdir()) == []
    assert list((tmp_path / "runtime").iterdir()) == []


def test_candidate_and_review_share_exact_two_revision_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_app_data = tmp_path / "local-app-data"
    local_app_data.mkdir()
    with patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}):
        prepared, frozen = _prepared_run(tmp_path, monkeypatch)
        context = build_single_candidate_starter_context(frozen)

        invalid = sealed_single_candidate(
            context,
            revision=1,
            mutate=lambda value: value["card_dispositions"].pop(),
        )
        invalid_path = tmp_path / "invalid-candidate.json"
        _write_unsigned_document(invalid_path, invalid)
        first_failure = controller.validate_live_start_candidate(
            session_root=prepared.run_root,
            draft_path=invalid_path,
        )

        candidate_two_document = sealed_single_candidate(context, revision=2)
        candidate_two_path = tmp_path / "candidate-2.json"
        _write_unsigned_document(candidate_two_path, candidate_two_document)
        controller.validate_live_start_candidate(
            session_root=prepared.run_root,
            draft_path=candidate_two_path,
        )
        candidate_two = validate_starter_candidate(
            candidate_two_document,
            context=context,
        )
        revision_review = review_document(
            SimpleNamespace(context=context, candidate=candidate_two),
            review_status="revision_requested",
            revision_requests=[
                {
                    "code": "tighten-mulligan",
                    "target": "mulligan",
                    "message": "Keep only the strongest supported opener.",
                }
            ],
        )
        revision_path = tmp_path / "revision-review.json"
        _write_unsigned_document(revision_path, revision_review)
        second_failure = controller.validate_live_start_review(
            session_root=prepared.run_root,
            draft_path=revision_path,
        )

        candidate_three_document = sealed_single_candidate(context, revision=3)
        candidate_three_path = tmp_path / "candidate-3.json"
        _write_unsigned_document(candidate_three_path, candidate_three_document)
        controller.validate_live_start_candidate(
            session_root=prepared.run_root,
            draft_path=candidate_three_path,
        )
        candidate_three = validate_starter_candidate(
            candidate_three_document,
            context=context,
        )
        exhausted_review = review_document(
            SimpleNamespace(context=context, candidate=candidate_three),
            review_status="revision_requested",
            revision_requests=[
                {
                    "code": "still-too-broad",
                    "target": "whole_candidate",
                    "message": "The candidate remains broader than needed.",
                }
            ],
        )
        exhausted_path = tmp_path / "exhausted-review.json"
        _write_unsigned_document(exhausted_path, exhausted_review)
        exhausted = controller.validate_live_start_review(
            session_root=prepared.run_root,
            draft_path=exhausted_path,
        )
        terminal = load_live_start_session(prepared.run_root)

    assert first_failure.to_value()["revisions_used"] == 1
    assert second_failure.to_value()["revisions_used"] == 2
    assert exhausted.to_value()["status"] == "FAILED_PRESERVED"
    assert terminal.candidate_revision == 3
    assert terminal.revisions_used == 2
    assert terminal.terminal_status == "FAILED_PRESERVED"


@pytest.mark.parametrize(
    "crash_action",
    (
        "materialize_review_revision_staging",
        "commit_bound_review_revision_request",
        "retire_candidate_validation_receipt",
    ),
)
def test_review_revision_resumes_after_physical_step_without_second_charge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    crash_action: str,
) -> None:
    local_app_data = tmp_path / "local-app-data"
    local_app_data.mkdir()
    with patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}):
        prepared, frozen = _prepared_run(tmp_path, monkeypatch)
        context = build_single_candidate_starter_context(frozen)
        document = sealed_single_candidate(context)
        candidate_path = tmp_path / "candidate.json"
        _write_unsigned_document(candidate_path, document)
        controller.validate_live_start_candidate(
            session_root=prepared.run_root, draft_path=candidate_path
        )
        candidate = validate_starter_candidate(document, context=context)
        review = review_document(
            SimpleNamespace(context=context, candidate=candidate),
            review_status="revision_requested",
            revision_requests=[
                {
                    "code": "tighten-mulligan",
                    "target": "mulligan",
                    "message": "Keep only the strongest supported opener.",
                }
            ],
        )
        review_path = tmp_path / "review.json"
        _write_unsigned_document(review_path, review)
        physical_step = controller._review_revision_physical_step

        def crash_after_step(**kwargs: object) -> object:
            result = physical_step(**kwargs)
            if kwargs["action"] == crash_action:
                raise RuntimeError("simulated process stop after physical step")
            return result

        with monkeypatch.context() as fault:
            fault.setattr(controller, "_review_revision_physical_step", crash_after_step)
            with pytest.raises(RuntimeError, match="simulated process stop"):
                controller.validate_live_start_review(
                    session_root=prepared.run_root, draft_path=review_path
                )

        with session.lease_live_start_session(prepared.run_root) as lease:
            interrupted = session.load_live_start_session_under_lock(session_lease=lease)
            resumed = controller._drive_candidate_review_revision(
                session_lease=lease, current=interrupted
            )

        completed = load_live_start_session(prepared.run_root)
        assert completed.content_sha256 == resumed.content_sha256
        assert completed.phase is LiveStartPhase.CANDIDATE_DRAFTED
        assert completed.revisions_used == 1
        assert completed.candidate_revision == 1
        assert completed.pending_transition is None
        assert not (prepared.run_root / "receipts").exists()


@pytest.mark.parametrize("tamper", (False, True))
def test_candidate_replacement_restart_accepts_only_bound_successor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tamper: bool,
) -> None:
    local_app_data = tmp_path / "local-app-data"
    local_app_data.mkdir()
    with patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}):
        prepared, frozen = _prepared_run(tmp_path, monkeypatch)
        context = build_single_candidate_starter_context(frozen)
        draft_path = tmp_path / "candidate.json"
        invalid = sealed_single_candidate(
            context, mutate=lambda value: value["card_dispositions"].pop()
        )
        _write_unsigned_document(draft_path, invalid)
        controller.validate_live_start_candidate(
            session_root=prepared.run_root, draft_path=draft_path
        )
        replacement = sealed_single_candidate(context, revision=2)
        _write_unsigned_document(draft_path, replacement)
        materialize = controller._materialize_pending_document

        def crash_after_replace(**kwargs: object) -> None:
            materialize(**kwargs)
            raise RuntimeError("simulated stop after candidate replacement")

        with monkeypatch.context() as fault:
            fault.setattr(controller, "_materialize_pending_document", crash_after_replace)
            with pytest.raises(RuntimeError, match="simulated stop"):
                controller.validate_live_start_candidate(
                    session_root=prepared.run_root, draft_path=draft_path
                )

        bound_path = prepared.run_root / "starter/starter_config_candidate.json"
        if tamper:
            bound_path.write_bytes(b'{"unbound":true}')
            with pytest.raises(session.SessionConflictError):
                load_live_start_session(prepared.run_root)
            return

        with session.lease_live_start_session(prepared.run_root) as lease:
            interrupted = session.load_live_start_session_under_lock(session_lease=lease)
            resumed = controller._continue_pending_document_install(
                session_lease=lease,
                current=interrupted,
                final_event="replacement_draft",
            )
        assert resumed.candidate_revision == 2
        assert resumed.revisions_used == 1
        assert resumed.pending_transition is None
        assert bound_path.read_bytes() == replacement.canonical_json


def test_finalize_preview_publishes_without_any_runtime_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_app_data = tmp_path / "local-app-data"
    local_app_data.mkdir()
    with patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}):
        prepared = _approved_run(tmp_path, monkeypatch)

        result = controller.finalize_live_start(session_root=prepared.run_root)
        repeated = controller.resume_live_start(session_root=prepared.run_root)
        completed = load_live_start_session(prepared.run_root)

    assert result.status == "PREVIEW_READY"
    assert repeated.summary.canonical_json == result.summary.canonical_json
    assert result.run_root == prepared.run_root
    assert completed.phase is LiveStartPhase.PUBLICATION_COMMITTED
    assert completed.terminal_status == "PREVIEW_READY"
    assert completed.runtime_admission_binding is None
    assert completed.apply_invocation_sha256 is None
    assert (tmp_path / "outputs" / "ShadowPriest" / "current.json").is_file()
    assert list((tmp_path / "runtime").iterdir()) == []


def test_finalize_live_uses_one_composite_and_returns_runtime_match_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_app_data = tmp_path / "local-app-data"
    local_app_data.mkdir()
    with patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}):
        prepared = _approved_run(tmp_path, monkeypatch, preview_requested=False)
        result = controller.finalize_live_start(session_root=prepared.run_root)
        repeated = controller.resume_live_start(session_root=prepared.run_root)
        completed = load_live_start_session(prepared.run_root)

    assert result.status == "LIVE_AND_MATCHED"
    assert repeated.summary.canonical_json == result.summary.canonical_json
    assert completed.phase is LiveStartPhase.RUNTIME_MATCHED
    assert completed.terminal_status == "LIVE_AND_MATCHED"
    assert completed.apply_recovery is None
    assert completed.terminal_retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"


def test_capture_preserves_raw_deck_code_in_existing_frozen_deck_blob(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_app_data = tmp_path / "local-app-data"
    local_app_data.mkdir()
    with patch.dict(os.environ, {"LOCALAPPDATA": str(local_app_data)}):
        code, _frozen = _frozen_live_start_inputs(tmp_path)
        source_request, projections = audited_request_with_frozen_input_projections(
            tmp_path / "source", "ShadowPriest"
        )
        preconfig = source_request.snapshot.general_preconfig.to_value()
        monkeypatch.setattr(controller, "fetch_latest_cards", lambda **_: projections["full_cards"])
        monkeypatch.setattr(
            controller, "fetch_latest_collectible_cards", lambda **_: projections["collectible_cards"]
        )
        monkeypatch.setattr(controller, "build_preconfig_context", lambda *_, **__: preconfig)
        monkeypatch.setattr(
            controller, "load_globalvalues_baseline", lambda *_: preconfig["globalvalues_baseline_receipt"]
        )
        profile = load_operator_profile()
        captured = controller._capture_live_start_inputs(
            controller.LiveStartRequest("ShadowPriest", code, True),
            profile,
            derive_deck_output_binding(profile, "ShadowPriest"),
        )

    assert captured.deck.to_value()["cards_payload"]["deck_code"] == code
    assert set(captured.deck.to_value()) == {"cards_payload", "deck_identity"}
    assert len(captured.manifest.compiler_inputs.to_value()["blobs"]) == 6


def test_disabled_profile_requires_explicit_preview_before_input_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    local = tmp_path / "local-app-data"
    local.mkdir()
    with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}):
        code, _ = _frozen_live_start_inputs(tmp_path)
        disable_operator_profile(expected_predecessor_sha256=load_operator_profile().content_sha256)

        def unexpected_capture(*_args: object) -> FrozenCompilerInputs:
            raise AssertionError("disabled live profile reached input capture")

        monkeypatch.setattr(controller, "_capture_live_start_inputs", unexpected_capture)
        result = controller._prepare_legacy_live_start(
            controller.LiveStartRequest("ShadowPriest", code, False)
        )
        assert result.status == "PROFILE_REQUIRED"
        assert result.run_root is None
        assert not (local / "HSConfig" / "runs").exists()


def test_prepare_freezes_inputs_once_and_resume_performs_no_second_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    local = tmp_path / "local-app-data"
    local.mkdir()
    with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}):
        prepared, _ = _prepared_run(tmp_path, monkeypatch)

        def no_second_capture(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("resume attempted another input capture")

        monkeypatch.setattr(controller, "_capture_live_start_inputs", no_second_capture)
        monkeypatch.setattr(controller, "fetch_latest_cards", no_second_capture)
        monkeypatch.setattr(controller, "fetch_latest_collectible_cards", no_second_capture)
        result = controller.resume_live_start(session_root=prepared.run_root)
        assert result.to_value()["status"] == "awaiting_candidate"
        assert result.to_value()["run_root"] == str(prepared.run_root)
        assert result.to_value()["next_candidate_revision"] == 1
        assert list((tmp_path / "runtime").iterdir()) == []


def test_candidate_pending_transition_resumes_without_redispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    local = tmp_path / "local-app-data"
    local.mkdir()
    with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}):
        prepared, frozen = _prepared_run(tmp_path, monkeypatch)
        context = build_single_candidate_starter_context(frozen)
        draft = tmp_path / "candidate.json"
        _write_unsigned_document(draft, sealed_single_candidate(context))
        materialize = controller._materialize_pending_document

        def stop_after_materialize(**kwargs: object) -> None:
            materialize(**kwargs)
            raise RuntimeError("candidate intake interrupted")

        with monkeypatch.context() as fault:
            fault.setattr(controller, "_materialize_pending_document", stop_after_materialize)
            with pytest.raises(RuntimeError, match="candidate intake interrupted"):
                controller.validate_live_start_candidate(session_root=prepared.run_root, draft_path=draft)
        draft.unlink()
        result = controller.resume_live_start(session_root=prepared.run_root)
        cursor = load_live_start_session(prepared.run_root)
        assert result.to_value()["status"] == "awaiting_review"
        assert cursor.phase is LiveStartPhase.CANDIDATE_VALIDATED
        assert cursor.candidate_revision == 1 and cursor.revisions_used == 0
        assert cursor.pending_transition is None


@pytest.mark.parametrize("point", (
    "after_invocation_prepared_before_admission",
    "after_apply_started",
    "after_result_intent",
    "after_result_json",
    "after_terminal_cas_before_ack",
))
def test_resume_after_controller_fault_uses_frozen_same_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, point: str,
) -> None:
    harness = controller._finalize_live_start
    local = tmp_path / "local-app-data"
    local.mkdir()
    reached: list[str] = []

    class SimulatedStop(BaseException):
        pass

    def stop_at(observed: object) -> None:
        reached.append(str(observed))
        if str(observed) == point:
            raise SimulatedStop(point)

    with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}):
        prepared = _approved_run(tmp_path, monkeypatch, preview_requested=False)
        with pytest.raises(SimulatedStop):
            harness(session_root=prepared.run_root, fault_hook=stop_at)
        assert point in reached
        interrupted = load_live_start_session(prepared.run_root)
        old_intent = interrupted.result_intent

        def no_reapply(**_kwargs: object) -> None:
            raise AssertionError("admitted resume attempted a new apply")

        if point != "after_invocation_prepared_before_admission":
            monkeypatch.setattr(controller._published_apply, "_apply_and_match_published", no_reapply)
        result = controller.resume_live_start(session_root=prepared.run_root)
        cursor = load_live_start_session(prepared.run_root)
        assert result.run_root == prepared.run_root
        assert result.status in {"LIVE_AND_MATCHED", "FAILED_PRESERVED"}
        assert cursor.pending_transition is None
        if old_intent is not None:
            assert cursor.result_intent == old_intent


def test_preview_intent_resume_does_not_recompile_or_republish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    local = tmp_path / "local-app-data"
    local.mkdir()

    class SimulatedStop(BaseException):
        pass

    def stop_after_intent(point: object) -> None:
        if str(point) == "after_result_intent":
            raise SimulatedStop

    with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}):
        prepared = _approved_run(tmp_path, monkeypatch)
        with pytest.raises(SimulatedStop):
            controller._finalize_live_start(session_root=prepared.run_root, fault_hook=stop_after_intent)
        interrupted = load_live_start_session(prepared.run_root)
        bound = interrupted.result_intent
        publication = interrupted.publication_binding
        assert publication is not None
        pointer = Path(publication["output_child_path"]) / "current.json"
        original = tmp_path / "held-current.json"
        pointer.rename(original)
        with pytest.raises(session.SessionConflictError, match="publication_current_changed"):
            controller.resume_live_start(session_root=prepared.run_root)
        pointer.write_bytes(original.read_bytes())
        with pytest.raises(ValueError, match="current_identity_changed"):
            controller.resume_live_start(session_root=prepared.run_root)
        assert load_live_start_session(prepared.run_root).terminal_status is None
        pointer.unlink()
        original.rename(pointer)

        def no_second_pipeline(**_kwargs: object) -> None:
            raise AssertionError("bound preview intent re-entered generation")

        monkeypatch.setattr(controller, "build_frozen_live_configure_run", no_second_pipeline)
        monkeypatch.setattr(controller, "_drive_live_start_pipeline", no_second_pipeline)
        def remove_pointer_at_terminal_boundary(point: object) -> None:
            if str(point) == "before_terminal_cas":
                pointer.rename(original)

        with pytest.raises(session.SessionConflictError, match="publication_current_changed"):
            controller._finalize_live_start(
                session_root=prepared.run_root, fault_hook=remove_pointer_at_terminal_boundary,
                resume_intake=True,
            )
        assert load_live_start_session(prepared.run_root).terminal_status is None
        original.rename(pointer)
        operation = controller.output_operation_admission_path()
        held_operation = tmp_path / "held-operation.json"
        operation.rename(held_operation)
        with pytest.raises(session.SessionConflictError, match="output_operation_binding_changed"):
            controller.resume_live_start(session_root=prepared.run_root)
        operation.write_bytes(held_operation.read_bytes())
        with pytest.raises(session.SessionConflictError, match="output_operation_binding_changed"):
            controller.resume_live_start(session_root=prepared.run_root)
        operation.unlink()
        held_operation.rename(operation)

        def remove_admission_at_terminal_boundary(point: object) -> None:
            if str(point) == "before_terminal_cas":
                operation.rename(held_operation)

        with pytest.raises(session.SessionConflictError, match="output_operation_binding_changed"):
            controller._finalize_live_start(
                session_root=prepared.run_root, fault_hook=remove_admission_at_terminal_boundary,
                resume_intake=True,
            )
        assert load_live_start_session(prepared.run_root).terminal_status is None
        held_operation.rename(operation)
        result = controller.resume_live_start(session_root=prepared.run_root)
        assert result.status == "PREVIEW_READY"
        assert load_live_start_session(prepared.run_root).result_intent == bound
        assert list((tmp_path / "runtime").iterdir()) == []


def test_terminal_preview_rejects_same_byte_admission_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    local = tmp_path / "local-app-data"
    local.mkdir()
    captured: dict[str, object] = {}

    class SimulatedStop(BaseException):
        pass

    def capture_then_stop(point: object) -> None:
        if str(point) == "after_output_operation_release_authorized":
            path = controller.output_operation_admission_path()
            captured["path"] = path
            captured["bytes"] = path.read_bytes()
        if str(point) == "after_output_operation_admission_unlink":
            raise SimulatedStop

    with patch.dict(os.environ, {"LOCALAPPDATA": str(local)}):
        prepared = _approved_run(tmp_path, monkeypatch)
        with pytest.raises(SimulatedStop):
            controller._finalize_live_start(session_root=prepared.run_root, fault_hook=capture_then_stop)
        target = captured["path"]
        assert isinstance(target, Path) and not target.exists()
        target.write_bytes(captured["bytes"])
        before = target.read_bytes()
        with pytest.raises(session.SessionConflictError, match="replaced_ambiguous"):
            controller.resume_live_start(session_root=prepared.run_root)
        assert target.read_bytes() == before
