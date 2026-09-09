from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from hsconfig import live_start_controller as controller
from hsconfig.live_start_session import (
    LiveStartPhase,
    LiveStartSession,
    SessionConflictError,
    load_live_start_session,
)
from hsconfig.operator_profile import operator_profile_path
from hsconfig.package_request import FrozenJsonDocument
from hsconfig.starter_candidate import (
    ValidatedStarterCandidate,
    validate_starter_candidate,
)
from hsconfig.starter_context import (
    StarterContext,
    build_single_candidate_starter_context,
)
from hsconfig.starter_review import (
    ValidatedStarterReview,
    validate_starter_review,
)
from tests.test_controller_candidate_feedback import (
    _diagnostic_without_digest,
    _file_fingerprint,
    _physical_tree,
)
from tests.test_live_start_controller import _prepared_run, _write_unsigned_document
from tests.test_starter_candidate import sealed_single_candidate
from tests.test_starter_review import review_document


def _revision_requests() -> list[dict[str, str]]:
    return [
        {
            "code": "a-tighten-mulligan",
            "target": "mulligan",
            "message": "Keep only the strongest supported opener.",
        },
        {
            "code": "a-tighten-mulligan",
            "target": "mulligan",
            "message": "Keep only the strongest supported opener.",
        },
        {
            "code": "b-explain-rationale",
            "target": "rule_rationales",
            "message": "Explain the transformed owner more directly.",
        },
    ]


def _prepare_review_revision(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[
    controller.LiveStartPreparation,
    StarterContext,
    ValidatedStarterCandidate,
    FrozenJsonDocument,
    bytes,
]:
    local_app_data = tmp_path / "local-app-data"
    local_app_data.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    prepared, frozen = _prepared_run(tmp_path, monkeypatch)
    context = build_single_candidate_starter_context(frozen)
    candidate_document = sealed_single_candidate(context)
    candidate_path = tmp_path / "candidate.json"
    _write_unsigned_document(candidate_path, candidate_document)
    candidate_validation = controller.validate_live_start_candidate(
        session_root=prepared.run_root,
        draft_path=candidate_path,
    )
    assert candidate_validation.to_value()["status"] == "valid"
    candidate = validate_starter_candidate(candidate_document, context=context)
    review = review_document(
        SimpleNamespace(context=context, candidate=candidate),
        review_status="revision_requested",
        revision_requests=_revision_requests(),
    )
    review_path = tmp_path / "revision-review.json"
    _write_unsigned_document(review_path, review)
    first = controller.validate_live_start_review(
        session_root=prepared.run_root,
        draft_path=review_path,
    )
    return prepared, context, candidate, first, review.canonical_json + b"\n"


def _assert_charged_review_revision(
    *,
    prepared: controller.LiveStartPreparation,
) -> LiveStartSession:
    charged = load_live_start_session(prepared.run_root)
    assert charged.phase is LiveStartPhase.CANDIDATE_DRAFTED
    assert charged.candidate_revision == 1
    assert charged.revisions_used == 1
    assert charged.pending_transition is None
    assert charged.terminal_status is None
    assert charged.publication_binding is None
    assert charged.output_operation_admission_binding is None
    assert charged.output_child_binding is None
    assert charged.apply_invocation_sha256 is None
    assert charged.runtime_admission_binding is None
    assert charged.runtime_layout_bootstrap is None
    assert charged.apply_recovery is None
    assert charged.result_intent is None
    assert set(charged.artifact_bindings) >= {
        "starter/starter_context.json",
        "starter/starter_config_candidate.json",
        "starter/starter_config_review.json",
    }
    assert not any(
        logical.startswith("receipts/") for logical in charged.artifact_bindings
    )
    assert not (prepared.run_root / "receipts").exists()
    return charged


def test_review_revision_feedback_repeats_exact_rows_without_second_charge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Break caught: resume of a charged reviewer revision drops the bounded
    # code/target/message rows or charges the shared revision budget again.
    prepared, context, _candidate, first, expected_review_raw = (
        _prepare_review_revision(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
        )
    )
    expected = {
        "candidate_revision": 1,
        "diagnostic_kind": "live_start_review_validation",
        "findings": [
            "a-tighten-mulligan",
            "a-tighten-mulligan",
            "b-explain-rationale",
        ],
        "next_candidate_revision": 2,
        "revision_requests": _revision_requests(),
        "revisions_used": 1,
        "schema_version": 1,
        "status": "revision_required",
    }
    assert _diagnostic_without_digest(first) == expected
    charged = _assert_charged_review_revision(prepared=prepared)
    stored_review = prepared.run_root / "starter/starter_config_review.json"
    stored_review_raw = stored_review.read_bytes()
    assert stored_review_raw == expected_review_raw

    local_authority_root = tmp_path / "local-app-data" / "HSConfig"
    local_authority_tree = _physical_tree(local_authority_root)
    runtime_tree = _physical_tree(tmp_path / "runtime")
    output_tree = _physical_tree(tmp_path / "outputs")
    profile_fingerprint = _file_fingerprint(operator_profile_path())

    for _ in range(2):
        resumed = controller.resume_live_start(session_root=prepared.run_root)
        assert isinstance(resumed, FrozenJsonDocument)
        assert resumed.canonical_json == first.canonical_json
        assert _diagnostic_without_digest(resumed) == expected
        persisted = load_live_start_session(prepared.run_root)
        assert persisted.canonical_json == charged.canonical_json
        assert persisted.content_sha256 == charged.content_sha256
        assert persisted.session_identity == charged.session_identity
        assert _physical_tree(local_authority_root) == local_authority_tree
        assert _physical_tree(tmp_path / "runtime") == runtime_tree
        assert _physical_tree(tmp_path / "outputs") == output_tree
        assert _file_fingerprint(operator_profile_path()) == profile_fingerprint
        assert stored_review.read_bytes() == stored_review_raw
        assert not (prepared.run_root / "receipts").exists()

    corrected = sealed_single_candidate(context, revision=2)
    corrected_path = tmp_path / "corrected-candidate.json"
    _write_unsigned_document(corrected_path, corrected)
    validation = controller.validate_live_start_candidate(
        session_root=prepared.run_root,
        draft_path=corrected_path,
    )
    assert validation.to_value()["status"] == "valid"
    completed = load_live_start_session(prepared.run_root)
    assert completed.phase is LiveStartPhase.CANDIDATE_VALIDATED
    assert completed.candidate_revision == 2
    assert completed.revisions_used == 1
    assert completed.pending_transition is None
    assert (
        prepared.run_root / "starter/starter_config_candidate.json"
    ).read_bytes() == corrected.canonical_json
    assert not stored_review.exists()
    assert (prepared.run_root / "receipts/candidate_validation.json").is_file()


@pytest.mark.parametrize(
    "contradiction",
    ("approved-status", "candidate-revision"),
)
def test_review_revision_resume_rejects_contradictory_validated_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    contradiction: str,
) -> None:
    # Break caught: reconstructed review evidence that no longer reports
    # revision_requested must not be treated as repeatable charged feedback.
    prepared, context, candidate, _first, _expected_review_raw = (
        _prepare_review_revision(
            tmp_path=tmp_path,
            monkeypatch=monkeypatch,
        )
    )
    charged = _assert_charged_review_revision(prepared=prepared)
    if contradiction == "candidate-revision":
        contradictory_candidate = validate_starter_candidate(
            sealed_single_candidate(context, revision=2),
            context=context,
        )
        contradictory_document = review_document(
            SimpleNamespace(
                context=context,
                candidate=contradictory_candidate,
            ),
            review_status="revision_requested",
            revision_requests=_revision_requests(),
        )
    else:
        contradictory_candidate = candidate
        contradictory_document = review_document(
            SimpleNamespace(context=context, candidate=candidate)
        )
    contradictory_review = validate_starter_review(
        contradictory_document,
        context=context,
        candidate=contradictory_candidate,
    )
    assert isinstance(contradictory_review, ValidatedStarterReview)
    assert (
        contradictory_review.review_status != "revision_requested"
        or contradictory_review.candidate_revision != charged.candidate_revision
    )

    local_authority_root = tmp_path / "local-app-data" / "HSConfig"
    local_authority_tree = _physical_tree(local_authority_root)
    runtime_tree = _physical_tree(tmp_path / "runtime")
    output_tree = _physical_tree(tmp_path / "outputs")

    monkeypatch.setattr(
        controller,
        "validate_starter_review",
        lambda *_args, **_kwargs: contradictory_review,
    )
    with pytest.raises(SessionConflictError):
        controller.resume_live_start(session_root=prepared.run_root)

    persisted = load_live_start_session(prepared.run_root)
    assert persisted.canonical_json == charged.canonical_json
    assert persisted.content_sha256 == charged.content_sha256
    assert persisted.session_identity == charged.session_identity
    assert _physical_tree(local_authority_root) == local_authority_tree
    assert _physical_tree(tmp_path / "runtime") == runtime_tree
    assert _physical_tree(tmp_path / "outputs") == output_tree
    assert not (prepared.run_root / "receipts").exists()


def test_review_revision_resume_rejects_changed_bytes_at_read_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepared, _context, _candidate, _first, _expected_raw = _prepare_review_revision(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )
    charged = _assert_charged_review_revision(prepared=prepared)
    before = _physical_tree(tmp_path)
    review_path = prepared.run_root / "starter/starter_config_review.json"
    read_plain_bytes = controller._read_plain_bytes
    intercepted = []

    def change_review_read(path: Path, *, maximum_size: int) -> bytes:
        raw = read_plain_bytes(path, maximum_size=maximum_size)
        if path == review_path:
            intercepted.append(path)
            return raw + b" "
        return raw

    monkeypatch.setattr(controller, "_read_plain_bytes", change_review_read)
    with pytest.raises(
        SessionConflictError,
        match="^live_start_revision_review_bytes_changed$",
    ):
        controller.resume_live_start(session_root=prepared.run_root)
    assert intercepted == [review_path]
    persisted = load_live_start_session(prepared.run_root)
    assert persisted.canonical_json == charged.canonical_json
    assert persisted.session_identity == charged.session_identity
    assert _physical_tree(tmp_path) == before
