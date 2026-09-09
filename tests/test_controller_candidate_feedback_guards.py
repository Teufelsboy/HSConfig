from __future__ import annotations

from pathlib import Path

import pytest

from hsconfig import live_start_controller as controller
from hsconfig.live_start_session import (
    LiveStartPhase,
    SessionConflictError,
    load_live_start_session,
)
from hsconfig.starter_candidate import validate_starter_candidate
from tests.test_controller_candidate_feedback import (
    _diagnostic_without_digest,
    _physical_tree,
    _prepare_candidate,
    _remove_card_disposition,
)
from tests.test_starter_candidate import sealed_single_candidate


@pytest.mark.parametrize(
    ("error_type", "message", "expected_finding"),
    (
        (
            ValueError,
            "starter_candidate_card_dispositions_invalid",
            "starter_candidate_card_dispositions_invalid",
        ),
        (
            ValueError,
            "starter_candidate_card_dispositions_invalid: private-detail",
            "candidate_semantics_invalid",
        ),
        (
            TypeError,
            "private-validator-type-detail",
            "candidate_semantics_invalid",
        ),
    ),
    ids=("exact-allowlisted", "allowlisted-prefix", "unknown-type-error"),
)
def test_candidate_feedback_exposes_only_exact_allowlisted_error_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_type: type[Exception],
    message: str,
    expected_finding: str,
) -> None:
    # Break caught: prefix matching or raw exception passthrough can expose an
    # unbounded private validator message as public candidate feedback.
    monkeypatch.setattr(
        controller,
        "_load_bound_starter_context",
        lambda **_kwargs: object(),
    )

    def reject_candidate(**_kwargs: object) -> None:
        raise error_type(message)

    monkeypatch.setattr(controller, "_load_bound_candidate", reject_candidate)

    assert (
        controller._candidate_validation_finding(
            session_root=tmp_path,
        )
        == expected_finding
    )


def test_resume_rejects_charged_candidate_that_unexpectedly_now_validates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Break caught: treating a charged immutable rejection as newly valid can
    # advance the same revision or mint downstream authority without a new draft.
    prepared, context, draft_path = _prepare_candidate(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        mutate=_remove_card_disposition,
    )
    valid_candidate = validate_starter_candidate(
        sealed_single_candidate(context),
        context=context,
    )
    rejected_diagnostic = controller.validate_live_start_candidate(
        session_root=prepared.run_root,
        draft_path=draft_path,
    )
    assert _diagnostic_without_digest(rejected_diagnostic) == {
        "candidate_revision": 1,
        "diagnostic_kind": "live_start_candidate_validation",
        "findings": ["starter_candidate_card_dispositions_invalid"],
        "next_candidate_revision": 2,
        "revisions_used": 1,
        "schema_version": 1,
        "status": "revision_required",
    }

    rejected = load_live_start_session(prepared.run_root)
    assert rejected.phase is LiveStartPhase.CANDIDATE_DRAFTED
    assert rejected.candidate_revision == 1
    assert rejected.revisions_used == 1
    assert rejected.pending_transition is None
    assert rejected.terminal_status is None
    assert rejected.publication_binding is None
    assert rejected.output_operation_admission_binding is None
    assert rejected.output_child_binding is None
    assert rejected.apply_invocation_sha256 is None
    assert rejected.runtime_admission_binding is None
    assert rejected.runtime_layout_bootstrap is None
    assert rejected.apply_recovery is None
    assert rejected.result_intent is None
    assert "starter/starter_config_candidate.json" in rejected.artifact_bindings
    assert "receipts/candidate_validation.json" not in rejected.artifact_bindings
    assert not (prepared.run_root / "receipts/candidate_validation.json").exists()

    local_authority_root = tmp_path / "local-app-data" / "HSConfig"
    local_authority_tree = _physical_tree(local_authority_root)
    runtime_tree = _physical_tree(tmp_path / "runtime")
    output_tree = _physical_tree(tmp_path / "outputs")

    monkeypatch.setattr(
        controller,
        "_load_bound_candidate",
        lambda **_kwargs: valid_candidate,
    )
    with pytest.raises(
        SessionConflictError,
        match="^live_start_rejected_candidate_now_valid$",
    ):
        controller.resume_live_start(session_root=prepared.run_root)

    persisted = load_live_start_session(prepared.run_root)
    assert persisted.canonical_json == rejected.canonical_json
    assert persisted.content_sha256 == rejected.content_sha256
    assert persisted.session_identity == rejected.session_identity
    assert _physical_tree(local_authority_root) == local_authority_tree
    assert _physical_tree(tmp_path / "runtime") == runtime_tree
    assert _physical_tree(tmp_path / "outputs") == output_tree
    assert not (prepared.run_root / "receipts/candidate_validation.json").exists()
