"""Closed user-facing routes for persisted quality live-start sessions."""

from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace

import pytest

import hsconfig.live_start_controller as controller
import hsconfig.live_start_session as live_session
from hsconfig.live_start_session import LiveStartPhase, load_live_start_session
from hsconfig.package_request import FrozenJsonDocument
import tests.test_live_start_session as session_fixtures
from tests.test_quality_live_start_controller import quality_request as _quality_request


@pytest.fixture
def persisted_quality_request(tmp_path, monkeypatch):
    return _quality_request.__wrapped__(tmp_path, monkeypatch)


def test_research_messages_are_distinct_safe_and_bounded():
    codes = [
        "discovery_unavailable", "discovery_budget_exhausted",
        "no_useful_observations", "acquisition_http_status_503",
        "source_context_incomplete", "C" + ":/private/file", "https://secret.test/path",
        "\x00" + "x" * 10000, "\n", "\u202e", "acquisition_http_status_999",
        "acquisition_TimeoutError", "acquisition_source_body_too_large",
        "acquisition_research_budget_exhausted", "not_a_timeout",
    ]
    result = controller._visible_research_limitations(codes)
    assert result == tuple(sorted(set(result)))
    assert len(result) <= 32
    assert all(len(item) <= 256 and all(ord(c) >= 32 for c in item) for item in result)
    assert all("private" not in item and "secret.test" not in item for item in result)
    assert "Guide discovery was unavailable." in result
    assert "The guide search budget was exhausted." in result
    assert "A guide page returned an unsuccessful HTTP response." in result
    assert "A guide page request timed out." in result
    assert "A guide page or the shared acquisition exceeded its time limit." in result
    assert "Additional research limitations are present in the preserved evidence." in result


@pytest.mark.parametrize("codes", [None, "discovery_unavailable", {}, [1]])
def test_research_messages_reject_invalid_container(codes):
    with pytest.raises(controller.SessionConflictError, match="limitations_invalid"):
        controller._visible_research_limitations(codes)


def test_source_backed_context_does_not_erase_explicit_qualification():
    context = {
        "schema_version": 3,
        "source_evidence": {
            "guide_builder_receipt": {"source_depth_status": "source_backed"},
            "guide_sources_summary": {},
        },
        "research_evidence": {"limitations": ["source_context_incomplete"]},
    }
    assert controller._starter_context_limitations(context) == (
        "Some selected guide excerpts omit adjacent context; review the limitation before relying on them.",
    )
    review = SimpleNamespace(
        confidence="limited", document=SimpleNamespace(content_sha256="sha256:" + "a" * 64)
    )
    result = controller._starter_context_limitations(context, review=review)
    assert "Independent reviewer confidence is limited." in result
    assert "See the preserved review rationale bound to sha256:" + "a" * 64 + "." in result


@pytest.mark.parametrize("missing", ["research_evidence", "source_depth_status"])
def test_source_backed_context_requires_validated_research_and_receipt(missing):
    value = {"schema_version": 3, "research_evidence": {"limitations": []},
             "source_evidence": {"guide_builder_receipt": {"source_depth_status": "source_backed"}}}
    if missing == "research_evidence":
        value.pop(missing)
    else:
        value["source_evidence"]["guide_builder_receipt"].pop(missing)
    with pytest.raises(controller.SessionConflictError):
        controller._starter_context_limitations(value)


def _no_research_generation(monkeypatch):
    import hsconfig.live_start_research as research

    def forbidden(*args, **kwargs):
        pytest.fail("read-only projection reached research generation")

    monkeypatch.setattr(research, "build_research_result", forbidden)
    monkeypatch.setattr(research, "_observations", forbidden)


def _persist_progress(root, progress):
    """Rebind only fixture progress bytes, preserving all real session validators."""
    document = FrozenJsonDocument.from_value(progress)
    return _persist_bound_artifact(root, "research/progress.json", document.canonical_json)


def _persist_bound_artifact(root, logical, payload):
    """Bind controlled fixture bytes without changing production installation code."""
    (root / logical).write_bytes(payload)
    value = live_session._decode_canonical_json((root / "session.json").read_bytes())
    value["artifact_bindings"][logical] = "sha256:" + sha256(payload).hexdigest()
    value.pop("content_sha256")
    value["content_sha256"] = "sha256:" + sha256(live_session._canonical_json(value)).hexdigest()
    (root / "session.json").write_bytes(live_session._canonical_json(value))
    return load_live_start_session(root)


def _completed_progress(root, record=None):
    progress = FrozenJsonDocument.from_json_bytes((root / "research/progress.json").read_bytes()).to_value()
    record = {"source_url": "https://example.test/guide", "evidence_id": "e1"} if record is None else record
    progress["draft"] = {
        "acquisition_request_sha256": progress["request_sha256"],
        "discovery_outcome": "completed", "urls": ["https://example.test/guide"],
    }
    progress["deadline_utc"] = 100.0
    progress["source_records"] = [record]
    progress["attempts"] = [{"url": "https://example.test/guide", "state": "completed",
        "record_sha256": "sha256:" + sha256(FrozenJsonDocument.from_value(record).canonical_json).hexdigest(),
        "error": None}]
    _persist_progress(root, progress)
    return progress


def test_discovery_summary_does_not_synthesize_observation_absence(persisted_quality_request, monkeypatch):
    discovery = controller.prepare_quality_live_start(persisted_quality_request)
    _no_research_generation(monkeypatch)
    result = controller.quality_start_summary(run_root=discovery.run_root).to_value()
    assert result["visible_limitations"] == ["Guide research is not complete."]


def test_completed_draft_summary_never_builds_research(persisted_quality_request, monkeypatch):
    discovery = controller.prepare_quality_live_start(persisted_quality_request)
    _completed_progress(discovery.run_root)
    _no_research_generation(monkeypatch)
    result = controller.quality_start_summary(run_root=discovery.run_root).to_value()
    assert result["visible_limitations"] == ["Guide research is not complete."]


@pytest.mark.parametrize("record,error", [
    ({"source_url": "https://example.test/guide"}, KeyError),
    ({"source_url": "https://example.test/guide", "evidence_id": "e1", "normalized_text": 123}, TypeError),
    ({"source_url": "https://example.test/guide", "evidence_id": None}, None),
])
def test_summary_and_state_reject_invalid_record_structure_without_extraction(
    persisted_quality_request, monkeypatch, record, error
):
    discovery = controller.prepare_quality_live_start(persisted_quality_request)
    _completed_progress(discovery.run_root, record)
    current = load_live_start_session(discovery.run_root)
    _no_research_generation(monkeypatch)
    calls = [lambda: controller.quality_start_summary(run_root=discovery.run_root),
             lambda: controller._load_quality_state(root=discovery.run_root, current=current,
                                                    profile=controller.load_operator_profile())]
    for call in calls:
        if error:
            with pytest.raises(error):
                call()
        else:
            assert call() is not None


@pytest.mark.parametrize("defect", ["draft_digest", "draft_extra", "unadmitted", "attempt_digest", "no_draft"])
def test_summary_keeps_progress_validation_without_extraction(persisted_quality_request, monkeypatch, defect):
    discovery = controller.prepare_quality_live_start(persisted_quality_request)
    progress = _completed_progress(discovery.run_root)
    if defect == "draft_digest":
        progress["draft"]["acquisition_request_sha256"] = "sha256:" + "0" * 64
    elif defect == "draft_extra":
        progress["draft"]["content_sha256"] = "sha256:" + "0" * 64
    elif defect == "unadmitted":
        progress["attempts"][0]["url"] = "https://example.test/unadmitted"
    elif defect == "attempt_digest":
        progress["attempts"][0]["record_sha256"] = "sha256:" + "0" * 64
    else:
        progress["draft"] = None
    current = _persist_progress(discovery.run_root, progress)
    _no_research_generation(monkeypatch)
    with pytest.raises((ValueError, controller.SessionConflictError)):
        controller._quality_summary_progress(run_root=discovery.run_root, current=current)


def _frozen_quality(request, tmp_path):
    from tests.test_quality_live_start_controller import _empty_draft
    discovery = controller.prepare_quality_live_start(request)
    return controller.complete_live_start_research(
        session_root=discovery.run_root, draft_path=_empty_draft(tmp_path, discovery)
    )


def _approved_quality(request, tmp_path, *, install_review=True):
    from hsconfig.input_snapshot_manifest import load_frozen_compiler_inputs
    from hsconfig.starter_context import build_quality_starter_context
    from tests.test_quality_starter_candidate import quality_draft, seal_quality_candidate
    from tests.test_quality_starter_review import quality_review
    prepared = _frozen_quality(request, tmp_path)
    context = build_quality_starter_context(load_frozen_compiler_inputs(prepared.run_root))
    draft = quality_draft(context)
    path = tmp_path / "candidate.json"
    path.write_bytes(FrozenJsonDocument.from_value(draft).canonical_json)
    receipt = controller.validate_live_start_candidate(session_root=prepared.run_root, draft_path=path)
    candidate = controller.validate_starter_candidate(seal_quality_candidate(draft), context=context)
    review = quality_review(context, candidate, receipt)
    if install_review:
        value = review.to_value()
        value.pop("content_sha256")
        path = tmp_path / "review.json"
        path.write_bytes(FrozenJsonDocument.from_value(value).canonical_json)
        controller.validate_live_start_review(session_root=prepared.run_root, draft_path=path)
    return prepared, context, candidate, receipt, review


def test_input_frozen_summary_reads_bound_quality_without_materializing_context(
    persisted_quality_request, tmp_path, monkeypatch
):
    prepared = _frozen_quality(persisted_quality_request, tmp_path)
    _no_research_generation(monkeypatch)
    monkeypatch.setattr(controller, "_materialize_starter_context", lambda **_: pytest.fail("context materialized"))
    result = controller.quality_start_summary(run_root=prepared.run_root).to_value()
    assert result["visible_limitations"] == sorted([
        "Guide discovery was unavailable.",
        "No useful card-specific guide observations were retained.",
        "No retained observation has verified exact-deck guide identity.",
    ])


def test_preintent_summary_rejects_changed_quality_bytes(persisted_quality_request, tmp_path, monkeypatch):
    prepared = _frozen_quality(persisted_quality_request, tmp_path)
    captured = live_session.load_live_start_session_snapshot(prepared.run_root)
    (prepared.run_root / "inputs/quality.json").write_bytes(b"{}")
    monkeypatch.setattr(live_session, "load_live_start_session_snapshot", lambda _: captured)
    monkeypatch.setattr(controller, "_load_bound_starter_context", lambda **_: pytest.fail("alternate context read"))
    with pytest.raises(controller.SessionConflictError, match="input_changed"):
        controller.quality_start_summary(run_root=prepared.run_root)


def test_preintent_summary_treats_unbound_staged_quality_as_unavailable(tmp_path, monkeypatch):
    current = SimpleNamespace(result_intent=None, phase=LiveStartPhase.INPUT_FROZEN, artifact_bindings={})
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs/quality.json").write_bytes(b"private staged file")
    monkeypatch.setattr(controller, "_read_plain_bytes", lambda *a, **k: pytest.fail("unbound file read"))
    assert controller._quality_available_limitations(run_root=tmp_path, current=current, progress={}) == (
        "Frozen research qualifications are not yet available.",
    )


def test_existing_intent_summary_does_not_read_new_qualifications(tmp_path, monkeypatch):
    intent = {"visible_limitations": ["historically retained qualification"]}
    current = SimpleNamespace(result_intent=intent)
    monkeypatch.setattr(controller, "_read_quality_bound_document", lambda **_: pytest.fail("fresh read"), raising=False)
    monkeypatch.setattr(controller, "_quality_bound_review", lambda **_: pytest.fail("fresh review"), raising=False)
    assert controller._quality_available_limitations(run_root=tmp_path, current=current, progress={}) == tuple(intent["visible_limitations"])


def test_installed_receipt_newline_and_starter_adapters_reach_real_validators(
    persisted_quality_request, tmp_path, monkeypatch
):
    prepared, context, candidate, receipt, review = _approved_quality(persisted_quality_request, tmp_path)
    raw = (prepared.run_root / "receipts/candidate_validation.json").read_bytes()
    assert raw == receipt.canonical_json + b"\n"
    snapshot = live_session.load_live_start_session_snapshot

    def capture(root):
        current = snapshot(root)
        assert current.artifact_bindings["receipts/candidate_validation.json"] == "sha256:" + sha256(raw).hexdigest()
        monkeypatch.setattr(live_session, "_load_session_bytes", lambda *a, **k: pytest.fail("second session read"))
        monkeypatch.setattr(controller, "load_starter_document", lambda *a, **k: pytest.fail("second document read"))
        return current

    monkeypatch.setattr(live_session, "load_live_start_session_snapshot", capture)
    _no_research_generation(monkeypatch)
    result = controller.quality_start_summary(run_root=prepared.run_root).to_value()
    assert "Independent reviewer confidence is limited." in result["visible_limitations"]
    assert "See the preserved review rationale bound to " + review.content_sha256 + "." in result["visible_limitations"]
    assert "Guide discovery was unavailable." in result["visible_limitations"]


@pytest.mark.parametrize("tamper", ["receipt", "candidate"])
def test_limited_current_review_reference_is_digest_bound(persisted_quality_request, tmp_path, monkeypatch, tamper):
    prepared, context, candidate, receipt, review = _approved_quality(persisted_quality_request, tmp_path)
    result = controller.quality_start_summary(run_root=prepared.run_root).to_value()
    assert "See the preserved review rationale bound to " + review.content_sha256 + "." in result["visible_limitations"]
    captured = live_session.load_live_start_session_snapshot(prepared.run_root)
    monkeypatch.setattr(live_session, "load_live_start_session_snapshot", lambda _: captured)
    path = "receipts/candidate_validation.json" if tamper == "receipt" else "starter/starter_config_candidate.json"
    (prepared.run_root / path).write_bytes(b"{}")
    with pytest.raises(controller.SessionConflictError):
        controller.quality_start_summary(run_root=prepared.run_root)


def test_prior_revision_review_is_not_current_rationale(persisted_quality_request, tmp_path):
    from tests.test_quality_starter_candidate import quality_draft
    from tests.test_quality_starter_review import quality_review
    prepared, context, candidate, receipt, _ = _approved_quality(persisted_quality_request, tmp_path, install_review=False)
    review = quality_review(context, candidate, receipt, mutate=lambda value: value.update(
        review_status="revision_requested", revision_requests=[{
            "code": "tighten-mulligan", "target": "mulligan", "message": "Keep only the strongest opener."
        }]))
    value = review.to_value()
    assert value["confidence"] == "limited"
    value.pop("content_sha256")
    review_path = tmp_path / "feedback.json"
    review_path.write_bytes(FrozenJsonDocument.from_value(value).canonical_json)
    controller.validate_live_start_review(session_root=prepared.run_root, draft_path=review_path)
    # Feedback phase preserves Session-canonical review plus LF, with no current receipt.
    feedback_bytes = (prepared.run_root / "starter/starter_config_review.json").read_bytes()
    assert feedback_bytes.endswith(b"\n")
    feedback_binding = load_live_start_session(prepared.run_root).artifact_bindings["starter/starter_config_review.json"]
    feedback_summary = controller.quality_start_summary(run_root=prepared.run_root).to_value()
    assert not any("rationale" in row for row in feedback_summary["visible_limitations"])
    assert "Independent reviewer confidence is limited." not in feedback_summary["visible_limitations"]
    assert load_live_start_session(prepared.run_root).artifact_bindings["starter/starter_config_review.json"] == feedback_binding
    assert (prepared.run_root / "starter/starter_config_review.json").read_bytes() == feedback_bytes
    draft = quality_draft(context)
    draft["candidate_revision"] = 2
    candidate_path = tmp_path / "replacement.json"
    candidate_path.write_bytes(FrozenJsonDocument.from_value(draft).canonical_json)
    controller.validate_live_start_candidate(session_root=prepared.run_root, draft_path=candidate_path)
    assert load_live_start_session(prepared.run_root).candidate_revision == 2
    assert not (prepared.run_root / "starter/starter_config_review.json").exists()
    assert "starter/starter_config_review.json" not in load_live_start_session(prepared.run_root).artifact_bindings
    external = prepared.run_root.parent.parent / "contexts" / prepared.run_root.name / "review-revision-r1-u0.json"
    assert external.read_bytes() == feedback_bytes
    result = controller.quality_start_summary(run_root=prepared.run_root).to_value()
    assert not any("rationale" in row for row in result["visible_limitations"])
    assert "Independent reviewer confidence is limited." not in result["visible_limitations"]


@pytest.mark.parametrize("status", ["LIVE_AND_MATCHED", "ALREADY_LIVE", "APPLIED_BUT_NOT_VERIFIED"])
@pytest.mark.parametrize("existing", [False, True])
def test_held_live_first_intent_uses_current_qualifications_once(
    persisted_quality_request, tmp_path, monkeypatch, status, existing
):
    from dataclasses import replace
    from tests.test_live_start_preparation_failures import _LEGACY_FAILURE_BYTES
    import hsconfig.runtime_apply as runtime
    prepared, context, candidate, receipt, review = _approved_quality(persisted_quality_request, tmp_path)
    captured = load_live_start_session(prepared.run_root)
    unsigned = FrozenJsonDocument.from_json_bytes(_LEGACY_FAILURE_BYTES).to_value()
    unsigned.pop("content_sha256")
    unsigned.update(run_id=captured.run_id, terminal_status=status, unique_main_deck_cards=16,
        configured_cards=16, deliberately_unconfigured_cards=0, review_confidence="limited",
        error_code="runtime_mismatch" if status == "APPLIED_BUT_NOT_VERIFIED" else None,
        physical_disposition="COMMITTED", runtime_match_status="mismatch" if status == "APPLIED_BUT_NOT_VERIFIED" else "matched",
        runtime_match_sha256="sha256:" + "b" * 64, retained_safe_state="ATTEMPT_EVIDENCE_RETAINED")
    retained = live_session.seal_embedded_document("result_intent", unsigned)
    current = replace(captured, result_intent=retained if existing else None)
    before = FrozenJsonDocument.from_value(dict(retained)).canonical_json
    held = SimpleNamespace(updated_session=current, acknowledgement_evidence=None)
    lease = SimpleNamespace(session_root=prepared.run_root)

    class Stop(Exception):
        pass

    intents = []
    monkeypatch.setattr(controller._published_apply, "_sealed_result_intent_from_held", lambda **_: retained)

    def bind(**kwargs):
        intents.append(kwargs["result_intent"])
        assert kwargs["attempt_acknowledgement"] is None
        raise Stop

    def complete(**kwargs):
        assert existing
        assert FrozenJsonDocument.from_value(dict(kwargs["expected_result_session"].result_intent)).canonical_json == before
        raise Stop

    monkeypatch.setattr(live_session, "bind_result_intent_under_lock", bind)
    monkeypatch.setattr(live_session, "_complete_live_start_under_lock", complete)
    for name in ("apply_package", "install_runtime_package"):
        monkeypatch.setattr(runtime, name, lambda **_: pytest.fail("runtime write"))
    monkeypatch.setattr(controller._published_apply, "_apply_and_match_published", lambda **_: pytest.fail("apply entry"))
    if existing:
        monkeypatch.setattr(controller, "_quality_available_limitations", lambda **_: pytest.fail("fresh qualifications"))
        monkeypatch.setattr(controller, "_quality_bound_review", lambda **_: pytest.fail("fresh review"))
        monkeypatch.setattr(controller, "_load_bound_starter_context", lambda **_: pytest.fail("fresh context"))
    with pytest.raises(Stop):
        controller._complete_held_live_result(session_lease=lease, held=held)
    if existing:
        assert intents == []
    else:
        value = dict(intents[0])
        digest = value.pop("content_sha256")
        assert live_session.seal_embedded_document("result_intent", value)["content_sha256"] == digest
        assert "Guide discovery was unavailable." in value["visible_limitations"]
        assert "Independent reviewer confidence is limited." in value["visible_limitations"]
        assert "See the preserved review rationale bound to " + review.content_sha256 + "." in value["visible_limitations"]


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
                "error_code": "revision_budget_exhausted",
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
        controller._session,
        "load_live_start_session_snapshot",
        lambda _root: current,
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
        controller._session,
        "load_live_start_session_snapshot",
        lambda _root: current,
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
        controller._session,
        "load_live_start_session_snapshot",
        lambda _root: current,
    )

    with pytest.raises(RuntimeError, match="progress_binding_changed"):
        controller.quality_start_summary(run_root=tmp_path)


def test_quality_summary_preserves_valid_reserved_session_temp(
    persisted_quality_request,
):
    discovery = controller.prepare_quality_live_start(persisted_quality_request)
    session_path = discovery.run_root / "session.json"
    reserved_temp = discovery.run_root / ".session.json.live-start-atomic.tmp"
    reserved_temp.write_bytes(session_path.read_bytes())
    before = {
        path.relative_to(discovery.run_root): path.read_bytes()
        for path in discovery.run_root.rglob("*")
        if path.is_file()
    }

    with pytest.raises(RuntimeError, match="reserved_temp_pending"):
        controller.quality_start_summary(run_root=discovery.run_root)

    after = {
        path.relative_to(discovery.run_root): path.read_bytes()
        for path in discovery.run_root.rglob("*")
        if path.is_file()
    }
    assert after == before

    reconciled = load_live_start_session(discovery.run_root)
    assert reconciled.run_id == discovery.run_root.name
    assert not reserved_temp.exists()
    assert session_path.read_bytes() == before[
        session_path.relative_to(discovery.run_root)
    ]


def test_terminal_not_committed_retained_recovery_routes_to_resume(tmp_path):
    root, closed, _acknowledgement = session_fixtures._closed_result_cursor(
        tmp_path,
        success=False,
    )
    intent = session_fixtures._result_intent(cursor=closed, success=False)
    with session_fixtures._lease(root) as lease:
        result_bound = live_session.bind_result_intent_under_lock(
            session_lease=lease,
            expected_session=closed,
            result_intent=intent,
        )
        terminal = live_session.record_terminal_status_under_lock(
            session_lease=lease,
            expected_result_session=result_bound,
        )
        persisted = live_session.load_live_start_session_under_lock(
            session_lease=lease
        )

    assert persisted.canonical_json == terminal.canonical_json
    assert persisted.schema_version == 1
    assert persisted.terminal_status == "FAILED_PRESERVED"
    assert persisted.result_intent["physical_disposition"] == "NOT_COMMITTED"
    assert persisted.apply_recovery is None
    assert persisted.closed_apply_recovery_commitment is not None
    assert controller._quality_summary_route(persisted) == (
        "result/summary.json",
        "resume_existing_recovery",
    )
    assert controller._quality_summary_runtime_write_state(persisted) == "no"


def _terminal_route_cursor(phase, code):
    return SimpleNamespace(
        phase=phase,
        terminal_status="FAILED_PRESERVED",
        result_intent={"error_code": code, "physical_disposition": None},
        apply_invocation_sha256=None,
        runtime_admission_binding=None,
        apply_recovery=None,
        closed_apply_recovery_commitment=None,
        pending_transition=None,
        artifact_bindings={},
    )


@pytest.mark.parametrize("phase", list(LiveStartPhase))
@pytest.mark.parametrize(
    "code, review_phases",
    [
        ("candidate_document_invalid", {"INPUT_FROZEN", "CANDIDATE_DRAFTED"}),
        ("candidate_revision_invalid", {"INPUT_FROZEN", "CANDIDATE_DRAFTED"}),
        ("review_document_invalid", {"CANDIDATE_VALIDATED"}),
        ("revision_budget_exhausted", {"CANDIDATE_DRAFTED", "CANDIDATE_VALIDATED"}),
        ("card_snapshot_unavailable", set()),
        ("compile_failed", set()),
        ("unknown_failure", set()),
        (None, set()),
    ],
)
def test_terminal_error_route_uses_closed_code_phase_matrix(phase, code, review_phases):
    current = _terminal_route_cursor(phase, code)
    if code is None:
        current.result_intent.pop("error_code")
    expected = (
        "inspect_preserved_review_finding"
        if phase.value in review_phases else "inspect_preserved_failure"
    )
    assert controller._quality_summary_route(current) == ("result/summary.json", expected)


@pytest.mark.parametrize("code", [None, "unknown_failure"])
@pytest.mark.parametrize("phase", [LiveStartPhase.CANDIDATE_DRAFTED,
                                   LiveStartPhase.CANDIDATE_VALIDATED])
def test_terminal_old_review_artifacts_do_not_classify_failure(phase, code):
    current = _terminal_route_cursor(phase, code)
    current.artifact_bindings = {
        "starter/starter_config_candidate.json": "sha256:" + "1" * 64,
        "starter/starter_config_review.json": "sha256:" + "2" * 64,
    }
    if code is None:
        current.result_intent.pop("error_code")
    assert controller._quality_summary_route(current) == (
        "result/summary.json", "inspect_preserved_failure",
    )


@pytest.mark.parametrize(
    "marker",
    [
        "apply_invocation_sha256", "runtime_admission_binding", "apply_recovery",
        "closed_apply_recovery_commitment", "NOT_COMMITTED",
        "COMMITTED_RECOVERY_PENDING", "UNKNOWN_REQUIRES_RECOVERY",
    ],
)
@pytest.mark.parametrize("code", ["revision_budget_exhausted", "compile_failed"])
def test_terminal_recovery_markers_precede_error_matrix(marker, code):
    current = _terminal_route_cursor(LiveStartPhase.CANDIDATE_VALIDATED, code)
    if marker.isupper():
        current.result_intent["physical_disposition"] = marker
    else:
        setattr(current, marker, "sha256:" + "3" * 64)
    assert controller._quality_summary_route(current) == (
        "result/summary.json", "resume_existing_recovery",
    )


@pytest.mark.parametrize(
    "status, expected",
    [
        ("LIVE_AND_MATCHED", "use_installed_configuration"),
        ("ALREADY_LIVE", "use_installed_configuration"),
        ("PREVIEW_READY", "inspect_preserved_preview"),
        ("APPLIED_BUT_NOT_VERIFIED", "resume_existing_recovery"),
    ],
)
@pytest.mark.parametrize("has_recovery_marker", [False, True])
def test_terminal_status_route_precedes_recovery_markers_and_errors(
    status, expected, has_recovery_marker
):
    current = _terminal_route_cursor(LiveStartPhase.RUNTIME_MATCHED, "compile_failed")
    current.terminal_status = status
    if has_recovery_marker:
        current.apply_recovery = {"retained": True}
    assert controller._quality_summary_route(current) == ("result/summary.json", expected)
