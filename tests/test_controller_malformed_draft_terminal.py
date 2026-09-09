from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import hsconfig.live_start_controller as controller
import hsconfig.live_start_session as session
from hsconfig.operator_profile import operator_profile_path
from hsconfig.package_io import path_identity
from hsconfig.package_request import FrozenJsonDocument
from hsconfig.starter_candidate import validate_starter_candidate
from hsconfig.starter_context import build_single_candidate_starter_context
from tests.test_configure_prepublication_apply import _physical_tree
from tests.test_live_start_controller import _prepared_run, _write_unsigned_document
from tests.test_starter_candidate import sealed_single_candidate
from tests.test_starter_review import review_document


@pytest.mark.parametrize(
    ("cursor_kind", "malformation", "error_code"),
    (
        ("initial", "extra_field", "candidate_document_invalid"),
        ("technical_revision", "wrong_schema", "candidate_document_invalid"),
        ("review_revision", "wrong_revision", "candidate_revision_invalid"),
        ("awaiting_review", "extra_field", "review_document_invalid"),
    ),
)
def test_malformed_draft_stops_once_without_an_uncounted_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cursor_kind: str,
    malformation: str,
    error_code: str,
) -> None:
    local_app_data = tmp_path / "local-app-data"
    local_app_data.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    prepared, frozen = _prepared_run(tmp_path, monkeypatch)
    context = build_single_candidate_starter_context(frozen)
    valid_document = sealed_single_candidate(context)
    candidate = validate_starter_candidate(valid_document, context=context)
    valid_path = tmp_path / "valid-candidate.json"
    _write_unsigned_document(valid_path, valid_document)

    if cursor_kind == "technical_revision":
        rejected = sealed_single_candidate(
            context,
            mutate=lambda value: value["card_dispositions"].pop(),
        )
        rejected_path = tmp_path / "rejected-candidate.json"
        _write_unsigned_document(rejected_path, rejected)
        response = controller.validate_live_start_candidate(
            session_root=prepared.run_root,
            draft_path=rejected_path,
        )
        assert response.to_value()["status"] == "revision_required"
    elif cursor_kind in {"review_revision", "awaiting_review"}:
        response = controller.validate_live_start_candidate(
            session_root=prepared.run_root,
            draft_path=valid_path,
        )
        assert response.to_value()["status"] == "valid"
        if cursor_kind == "review_revision":
            revision = review_document(
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
            revision_path = tmp_path / "revision-review.json"
            _write_unsigned_document(revision_path, revision)
            response = controller.validate_live_start_review(
                session_root=prepared.run_root,
                draft_path=revision_path,
            )
            assert response.to_value()["status"] == "revision_required"

    before = session.load_live_start_session(prepared.run_root)
    expected_phase = (
        session.LiveStartPhase.INPUT_FROZEN
        if cursor_kind == "initial"
        else session.LiveStartPhase.CANDIDATE_VALIDATED
        if cursor_kind == "awaiting_review"
        else session.LiveStartPhase.CANDIDATE_DRAFTED
    )
    assert before.phase is expected_phase
    assert before.pending_transition is None
    is_review = cursor_kind == "awaiting_review"
    document = (
        review_document(SimpleNamespace(context=context, candidate=candidate))
        if is_review
        else sealed_single_candidate(
            context,
            revision=2 if cursor_kind.endswith("revision") else 1,
        )
    )
    malformed = document.to_value()
    malformed.pop("content_sha256")
    if malformation == "extra_field":
        malformed["unexpected_field"] = True
    elif malformation == "wrong_schema":
        malformed["schema_version"] = 999
    else:
        malformed["candidate_revision"] = 99
    malformed_path = tmp_path / "malformed-draft.json"
    malformed_raw = FrozenJsonDocument.from_value(malformed).canonical_json
    malformed_path.write_bytes(malformed_raw)
    malformed_identity = path_identity(malformed_path)
    profile_path = operator_profile_path()
    profile_before = (path_identity(profile_path), profile_path.read_bytes())
    runtime_before = _physical_tree(tmp_path / "runtime")
    output_before = _physical_tree(tmp_path / "outputs")

    def forbid_compilation(**_kwargs: object) -> None:
        pytest.fail("malformed intake reached compilation")

    monkeypatch.setattr(
        controller, "build_frozen_live_configure_run", forbid_compilation
    )
    intake = (
        controller.validate_live_start_review
        if is_review
        else controller.validate_live_start_candidate
    )
    result = intake(session_root=prepared.run_root, draft_path=malformed_path)
    assert result.to_value()["status"] == "FAILED_PRESERVED"
    terminal = session.load_live_start_session(prepared.run_root)
    assert terminal.phase is before.phase
    assert terminal.terminal_status == "FAILED_PRESERVED"
    assert terminal.pending_transition is None
    assert terminal.candidate_revision == before.candidate_revision
    assert terminal.revisions_used == before.revisions_used
    assert terminal.result_intent["error_code"] == error_code
    assert terminal.result_intent["retained_safe_state"] == (
        "NO_PUBLICATION_OR_RUNTIME_WRITE"
    )
    for field in (
        "publication_binding",
        "output_operation_admission_binding",
        "output_child_binding",
        "apply_invocation_sha256",
        "runtime_admission_binding",
        "runtime_layout_bootstrap",
        "apply_recovery",
    ):
        assert getattr(terminal, field) is None
    result_paths = {"result/summary.json", "result/summary.md"}
    assert (
        set(terminal.artifact_bindings) == set(before.artifact_bindings) | result_paths
    )
    for path, digest in before.artifact_bindings.items():
        assert terminal.artifact_bindings[path] == digest
    if cursor_kind == "review_revision":
        assert "starter/starter_config_review.json" in terminal.artifact_bindings
        for mutation in (
            "unknown_extra",
            "missing_result",
            "wrong_budget",
            "premature_result",
            "missing_intent",
            "wrong_terminal",
            "pending_result",
        ):
            value = terminal.to_value()
            bindings = dict(terminal.artifact_bindings)
            if mutation == "unknown_extra":
                bindings["receipts/unexpected.json"] = "sha256:" + "0" * 64
            elif mutation == "missing_result":
                bindings.pop("result/summary.md")
            elif mutation == "wrong_budget":
                value["revisions_used"] = terminal.candidate_revision + 1
            elif mutation == "premature_result":
                value["terminal_status"] = None
            elif mutation == "missing_intent":
                value["result_intent"] = None
            elif mutation == "wrong_terminal":
                value["terminal_status"] = "LIVE_AND_MATCHED"
            else:
                value["pending_transition"] = {"operation": "unexpected"}
            with pytest.raises(session.SessionValidationError):
                session._validate_phase_artifact_bindings(
                    value=value,
                    phase=terminal.phase,
                    artifact_bindings=bindings,
                )
    stable_run = _physical_tree(prepared.run_root)
    for _ in range(2):
        replay = controller.resume_live_start(session_root=prepared.run_root)
        assert isinstance(replay, controller.LiveStartResult)
        assert replay.summary.canonical_json == result.canonical_json
        assert (
            intake(
                session_root=prepared.run_root, draft_path=malformed_path
            ).canonical_json
            == result.canonical_json
        )
        assert (
            controller.validate_live_start_candidate(
                session_root=prepared.run_root, draft_path=valid_path
            ).canonical_json
            == result.canonical_json
        )
        assert _physical_tree(prepared.run_root) == stable_run
    assert (path_identity(profile_path), profile_path.read_bytes()) == profile_before
    assert _physical_tree(tmp_path / "runtime") == runtime_before
    assert _physical_tree(tmp_path / "outputs") == output_before
    assert malformed_path.read_bytes() == malformed_raw
    assert path_identity(malformed_path) == malformed_identity
