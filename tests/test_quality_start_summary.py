"""Closed user-facing routes for persisted quality live-start sessions."""

from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace

import pytest

import hsconfig.live_start_controller as controller
from hsconfig.live_start_session import LiveStartPhase
from hsconfig.package_request import FrozenJsonDocument


def _progress(root):
    progress = FrozenJsonDocument.from_value(
        {
            "schema_version": 1,
            "request_sha256": "sha256:" + "1" * 64,
            "search_slots": [
                {"query": "ShadowPriest current guide", "state": "reserved_unknown"},
                {"query": "ShadowPriest mulligan", "state": "reserved_unknown"},
            ],
            "draft": {
                "acquisition_request_sha256": "sha256:" + "1" * 64,
                "urls": [],
                "discovery_outcome": "unavailable",
            },
            "deadline_utc": None,
            "attempts": [],
            "source_records": [],
            "source_acquisition_reports": [],
        }
    )
    path = root / "research/progress.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(progress.canonical_json)
    return "sha256:" + sha256(progress.canonical_json).hexdigest()


@pytest.mark.parametrize(
    (
        "phase",
        "terminal_status",
        "revisions_used",
        "apply_invocation",
        "result_intent",
        "artifacts",
        "next_action",
        "runtime_write_state",
    ),
    [
        (
            LiveStartPhase.DISCOVERY_REQUIRED,
            None,
            0,
            None,
            None,
            {"research/request.json"},
            "complete_or_resume_same_research_request",
            "no",
        ),
        (
            LiveStartPhase.CANDIDATE_VALIDATED,
            None,
            0,
            None,
            None,
            {"receipts/candidate_validation.json"},
            "dispatch_independent_reviewer",
            "no",
        ),
        (
            LiveStartPhase.CANDIDATE_DRAFTED,
            None,
            1,
            None,
            None,
            {
                "starter/starter_config_candidate.json",
                "starter/starter_config_review.json",
            },
            "return_exact_findings_to_same_lead",
            "no",
        ),
        (
            LiveStartPhase.CANDIDATE_VALIDATED,
            "FAILED_PRESERVED",
            2,
            None,
            {
                "visible_limitations": ["limited public guide evidence"],
                "physical_disposition": None,
            },
            {"result/summary.json"},
            "inspect_preserved_review_finding",
            "no",
        ),
        (
            LiveStartPhase.APPLY_STARTED,
            None,
            0,
            "sha256:" + "2" * 64,
            None,
            {"receipts/apply_invocation.json"},
            "resume_existing_recovery",
            "unknown",
        ),
        (
            LiveStartPhase.RUNTIME_MATCHED,
            "ALREADY_LIVE",
            0,
            "sha256:" + "2" * 64,
            {
                "visible_limitations": [],
                "physical_disposition": "COMMITTED",
            },
            {"result/summary.json"},
            "use_installed_configuration",
            "yes",
        ),
    ],
)
def test_quality_summary_has_one_closed_action_and_honest_budgets(
    tmp_path,
    monkeypatch,
    phase,
    terminal_status,
    revisions_used,
    apply_invocation,
    result_intent,
    artifacts,
    next_action,
    runtime_write_state,
):
    progress_sha256 = _progress(tmp_path)
    bindings = {
        "research/progress.json": progress_sha256,
        **{path: "sha256:" + "3" * 64 for path in artifacts},
    }
    current = SimpleNamespace(
        schema_version=2,
        phase=phase,
        terminal_status=terminal_status,
        candidate_revision=1,
        revisions_used=revisions_used,
        apply_invocation_sha256=apply_invocation,
        runtime_admission_binding=None,
        apply_recovery=None,
        pending_transition=None,
        result_intent=result_intent,
        artifact_bindings=bindings,
        research_binding={"request_sha256": "sha256:" + "1" * 64},
        deck_name="ShadowPriest",
        content_sha256="sha256:" + "4" * 64,
        canonical_json=b"{}",
    )
    monkeypatch.setattr(
        controller._session, "load_live_start_session", lambda _root: current
    )

    summary = controller.quality_start_summary(run_root=tmp_path).to_value()

    assert summary["schema_version"] == 2
    assert summary["phase"] == phase.value
    assert summary["deck_name"] == "ShadowPriest"
    assert "sha256" not in summary["deck_name"].casefold()
    assert summary["source_evidence"] == "limited"
    assert summary["acquisition_budget"] == {
        "search_query_limit": 2,
        "search_queries_reserved_unknown": 2,
        "search_queries_remaining": 0,
        "page_url_limit": 3,
        "page_urls_admitted": 0,
        "resume_resets_budget": False,
    }
    assert summary["revision_budget"] == {
        "maximum": 2,
        "used": revisions_used,
        "remaining": max(0, 2 - revisions_used),
    }
    assert summary["runtime_write_state"] == runtime_write_state
    assert summary["next_action"] == next_action
    assert set(summary["preserved_artifact"]) == {"path", "sha256"}
    assert "apply_authority" not in summary
    assert "confidence" not in summary


def test_quality_summary_preserves_schema_one_terminal_summary(tmp_path, monkeypatch):
    summary = FrozenJsonDocument.from_value(
        {
            "schema_version": 1,
            "summary_kind": "live_start_result",
            "status": "PREVIEW_READY",
        }
    )
    result_path = tmp_path / "result/summary.json"
    result_path.parent.mkdir()
    result_path.write_bytes(summary.canonical_json)
    current = SimpleNamespace(schema_version=1, terminal_status="PREVIEW_READY")
    monkeypatch.setattr(
        controller._session, "load_live_start_session", lambda _root: current
    )

    projected = controller.quality_start_summary(run_root=tmp_path)

    assert projected.canonical_json == summary.canonical_json


def test_quality_summary_rejects_changed_progress_bytes(tmp_path, monkeypatch):
    _progress(tmp_path)
    current = SimpleNamespace(
        schema_version=2,
        artifact_bindings={
            "research/progress.json": "sha256:" + "0" * 64,
        },
    )
    monkeypatch.setattr(
        controller._session, "load_live_start_session", lambda _root: current
    )

    with pytest.raises(RuntimeError, match="progress_binding_changed"):
        controller.quality_start_summary(run_root=tmp_path)
