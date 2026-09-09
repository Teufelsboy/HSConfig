"""Quality intake exercises real capture, closure, journal and package authority."""

import pytest

import hsconfig.live_start_controller as controller
from hsconfig.card_snapshot import build_card_snapshot
from hsconfig.live_start_session import load_live_start_session
from hsconfig.package_request import FrozenJsonDocument
from tests.test_live_start_controller import _frozen_live_start_inputs


@pytest.fixture
def quality_request(tmp_path, monkeypatch):
    local = tmp_path / "local-app-data"
    local.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    code, frozen = _frozen_live_start_inputs(tmp_path)
    payload = frozen.deck.to_value()["cards_payload"]
    hero = {
        "card_id": payload["deckstring_decode_receipt"]["hero_card_id"],
        "dbf_id": payload["hero_dbf_id"],
        "name": "Anduin Wrynn",
    }
    memberships = [*payload["cards"], hero]
    dbfs = {row["card_id"]: row["dbf_id"] for row in memberships}
    rows = [
        {
            **row,
            "dbfId": dbfs.get(row["id"], row.get("dbfId")),
            "collectible": row["id"] in {card["card_id"] for card in payload["cards"]},
        }
        for row in frozen.full_cards.to_value()
    ]
    if not any(row["id"] == hero["card_id"] for row in rows):
        rows.append(
            {
                "id": hero["card_id"],
                "dbfId": hero["dbf_id"],
                "name": hero["name"],
                "type": "HERO",
                "cardClass": "PRIEST",
                "collectible": False,
            }
        )
    snapshot = build_card_snapshot(rows, captured_at="2026-09-09T00:00:00Z")
    monkeypatch.setattr(
        controller, "fetch_card_snapshot", lambda **_: snapshot, raising=False
    )
    return controller.LiveStartRequest(
        deck_name="ShadowPriest",
        deck_code=code,
        preview_requested=True,
    )


def test_quality_prepare_seals_discovery_before_candidate_access(
    quality_request, monkeypatch
):
    import hsconfig.deck_input_verification as verification

    monkeypatch.setattr(
        verification,
        "decode_deck_code",
        lambda _: pytest.fail("quality identity used local cardxml"),
    )
    discovery = controller.prepare_quality_live_start(quality_request)
    assert discovery.acquisition_request_sha256
    value = load_live_start_session(discovery.run_root).to_value()
    assert value["schema_version"] == 2
    assert value["phase"] == "DISCOVERY_REQUIRED"
    assert value["input_snapshot_manifest_sha256"] is None
    assert value["apply_invocation_sha256"] is None
    assert value["publication_binding"] is None
    assert not (discovery.run_root / "starter").exists()


def test_large_card_seed_is_renamed_once_not_copied(
    quality_request, monkeypatch, tmp_path
):
    snapshot = controller.fetch_card_snapshot().to_value()
    rows = [
        *snapshot["full_cards"],
        {"id": "UNUSED_PADDING", "name": "x" * (2 * 1024 * 1024), "type": "SPELL"},
    ]
    large = build_card_snapshot(rows, captured_at=snapshot["captured_at"])
    monkeypatch.setattr(controller, "fetch_card_snapshot", lambda **_: large)
    identities = []

    def fault(point):
        if point == "before_quality_bootstrap_cursor":
            staged = next(
                (tmp_path / "local-app-data/HSConfig/runs").glob(
                    "*/inputs/.cards.json.live-start-atomic.tmp"
                )
            )
            identities.append(staged.stat().st_ino)

    monkeypatch.setattr(controller, "_quality_fault", fault)
    discovery = controller.prepare_quality_live_start(quality_request)
    cards = discovery.run_root / "inputs/cards.json"
    assert cards.stat().st_size > 2 * 1024 * 1024
    assert cards.stat().st_ino == identities[0]
    assert not (cards.parent / ".cards.json.live-start-atomic.tmp").exists()


def test_quality_missing_profile_stops_before_acquisition(tmp_path, monkeypatch):
    local = tmp_path / "local-app-data"
    local.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local))

    def forbidden(**_):
        raise AssertionError("acquisition without enabled profile")

    monkeypatch.setattr(controller, "fetch_card_snapshot", forbidden, raising=False)
    # Reuse the audited exact deck code without creating/enabling a profile.
    from tests.helpers.audited_package_request import (
        audited_request_with_frozen_input_projections,
    )

    audited, _ = audited_request_with_frozen_input_projections(
        tmp_path / "audited", "ShadowPriest"
    )
    request = controller.LiveStartRequest(
        deck_name="ShadowPriest",
        deck_code=str(audited.invocation.deck_code),
        preview_requested=True,
    )
    result = controller.prepare_quality_live_start(request)
    assert result.status == "PROFILE_REQUIRED"
    assert result.run_root is None
    assert not (local / "HSConfig" / "runs").exists()


def _empty_draft(root, discovery):
    path = root / "shortlist.json"
    path.write_bytes(
        FrozenJsonDocument.from_value(
            {
                "acquisition_request_sha256": discovery.acquisition_request_sha256,
                "urls": [],
                "discovery_outcome": "unavailable",
            }
        ).canonical_json
    )
    return path


def test_empty_research_freezes_same_seed_bytes(quality_request, tmp_path):
    discovery = controller.prepare_quality_live_start(quality_request)
    deck = (discovery.run_root / "inputs/deck.json").read_bytes()
    cards = (discovery.run_root / "inputs/cards.json").read_bytes()
    prepared = controller.complete_live_start_research(
        session_root=discovery.run_root,
        draft_path=_empty_draft(tmp_path, discovery),
    )
    assert isinstance(prepared, controller.LiveStartPreparation)
    assert prepared.run_root == discovery.run_root
    assert (prepared.run_root / "inputs/deck.json").read_bytes() == deck
    assert (prepared.run_root / "inputs/cards.json").read_bytes() == cards
    assert load_live_start_session(prepared.run_root).phase.value == "INPUT_FROZEN"
    context = FrozenJsonDocument.from_json_bytes(
        prepared.starter_context_path.read_bytes()
    ).to_value()
    assert context["schema_version"] == 3
    assert context["research_evidence"]["discovery_outcome"] == "unavailable"


@pytest.mark.parametrize("point", ["after_seed_install", "after_request_install"])
def test_bootstrap_fault_resumes_same_request(
    quality_request, monkeypatch, tmp_path, point
):
    class Crash(BaseException):
        pass

    def fault(name):
        if name == point:
            raise Crash

    monkeypatch.setattr(controller, "_quality_fault", fault)
    with pytest.raises(Crash):
        controller.prepare_quality_live_start(quality_request)
    run = next((tmp_path / "local-app-data/HSConfig/runs").iterdir())
    before = load_live_start_session(run)
    monkeypatch.setattr(controller, "_quality_fault", lambda _: None)
    monkeypatch.setattr(
        controller,
        "fetch_card_snapshot",
        lambda **_: pytest.fail("resume refetched cards"),
    )
    discovery = controller.resume_live_start(session_root=run)
    assert discovery.run_root == run
    assert (
        discovery.acquisition_request_sha256
        == before.research_binding["request_sha256"]
    )
    after = load_live_start_session(run)
    assert after.research_binding == before.research_binding
    assert after.phase.value == "DISCOVERY_REQUIRED"


@pytest.mark.parametrize(
    "point",
    [
        "after_started_attempt_checkpoint",
        "after_fetched_record_persistence",
        "after_final_input_installation",
        "during_input_frozen_transition",
    ],
)
def test_research_fault_spends_attempt_and_keeps_deadline(
    quality_request, monkeypatch, tmp_path, point
):
    from functools import partial
    from hsconfig.source_acquisition import collect_public_source_records
    import hsconfig.source_acquisition as acquisition

    calls = []

    def fetch(url, timeout):
        assert 0 < timeout <= 10
        calls.append(url)
        return (
            200,
            "text/html",
            b"<html><body><p>Darkbishop Benedictus is essential to Shadow Priest.</p></body></html>",
        )

    # Exercise the real collector and preserve injected-fetcher provenance.
    monkeypatch.setattr(
        acquisition,
        "collect_public_source_records",
        partial(
            collect_public_source_records,
            fetcher=fetch,
            resolver=lambda _: ["93.184.216.34"],
        ),
    )
    discovery = controller.prepare_quality_live_start(quality_request)
    root = discovery.run_root
    draft = tmp_path / "shortlist.json"
    draft.write_bytes(
        FrozenJsonDocument.from_value(
            {
                "acquisition_request_sha256": discovery.acquisition_request_sha256,
                "urls": ["https://example.test/guide"],
                "discovery_outcome": "completed",
            }
        ).canonical_json
    )

    class Crash(BaseException):
        pass

    def fault(name):
        if name == point:
            raise Crash

    monkeypatch.setattr(controller, "_quality_fault", fault)
    with pytest.raises(Crash):
        controller.complete_live_start_research(session_root=root, draft_path=draft)
    progress_before = FrozenJsonDocument.from_json_bytes(
        (root / "research/progress.json").read_bytes()
    ).to_value()
    binding_before = load_live_start_session(root).research_binding
    calls_before = list(calls)
    monkeypatch.setattr(controller, "_quality_fault", lambda _: None)
    prepared = controller.resume_live_start(session_root=root)
    assert isinstance(prepared, controller.LiveStartPreparation)
    assert calls == calls_before
    after = load_live_start_session(root)
    assert after.research_binding == binding_before
    quality = FrozenJsonDocument.from_json_bytes(
        (root / "inputs/quality.json").read_bytes()
    ).to_value()
    research = quality["research_result"]
    assert research["deadline_utc"] == progress_before["deadline_utc"]
    assert len(research["attempts"]) == 1
    assert research["attempts"][0]["state"] == (
        "interrupted" if point == "after_started_attempt_checkpoint" else "completed"
    )


@pytest.mark.parametrize(
    "logical", ["inputs/deck.json", "inputs/cards.json", "inputs/quality_seed.json"]
)
def test_replaced_seed_rejected_before_draft(quality_request, tmp_path, logical):
    discovery = controller.prepare_quality_live_start(quality_request)
    (discovery.run_root / logical).write_bytes(b"{}")
    with pytest.raises((ValueError, RuntimeError)):
        controller.complete_live_start_research(
            session_root=discovery.run_root, draft_path=tmp_path / "missing.json"
        )


def test_premature_finalize_rejects_without_installing_candidate(quality_request):
    discovery = controller.prepare_quality_live_start(quality_request)
    with pytest.raises(RuntimeError, match="discovery_required"):
        controller.finalize_live_start(session_root=discovery.run_root)
    assert not (discovery.run_root / "starter").exists()


def test_pre_cursor_failure_preserves_unsealed_staging(
    quality_request, monkeypatch, tmp_path
):
    class Crash(BaseException):
        pass

    def fault(point):
        if point == "before_quality_bootstrap_cursor":
            raise Crash

    monkeypatch.setattr(controller, "_quality_fault", fault)
    with pytest.raises(Crash):
        controller.prepare_quality_live_start(quality_request)
    runs = list((tmp_path / "local-app-data/HSConfig/runs").iterdir())
    assert len(runs) == 1
    root = runs[0]
    assert not (root / "session.json").exists()
    assert (root / "inputs/.cards.json.live-start-atomic.tmp").exists()
    with pytest.raises((OSError, ValueError, RuntimeError)):
        controller.resume_live_start(session_root=root)
    assert list(root.parent.iterdir()) == [root]


def test_changed_profile_stops_before_research(quality_request, tmp_path):
    from hsconfig.operator_profile import load_operator_profile, enable_operator_profile

    discovery = controller.prepare_quality_live_start(quality_request)
    profile = load_operator_profile()
    output = tmp_path / "changed-outputs"
    output.mkdir()
    enable_operator_profile(
        runtime_root=profile.runtime_root,
        output_base_root=output,
        expected_predecessor_sha256=profile.content_sha256,
    )
    with pytest.raises((ValueError, RuntimeError), match="profile_changed"):
        controller.complete_live_start_research(
            session_root=discovery.run_root, draft_path=tmp_path / "missing.json"
        )


@pytest.mark.parametrize("defect", ["quality_replaced", "mixed_compiler"])
def test_frozen_quality_authority_rejected_before_candidate_draft(
    quality_request, tmp_path, monkeypatch, defect
):
    import hsconfig.live_start_session as session

    discovery = controller.prepare_quality_live_start(quality_request)
    prepared = controller.complete_live_start_research(
        session_root=discovery.run_root, draft_path=_empty_draft(tmp_path, discovery)
    )
    root = prepared.run_root
    if defect == "quality_replaced":
        (root / "inputs/quality.json").write_bytes(b"{}")
    else:
        from hashlib import sha256

        current = load_live_start_session(root).to_value()
        manifest_path = root / "inputs/input_snapshot_manifest.json"
        value = FrozenJsonDocument.from_json_bytes(
            manifest_path.read_bytes()
        ).to_value()
        value["compiler_inputs"]["compiler_contract_id"] = "hsconfig-live-start-v1"
        value.pop("content_sha256")
        value["content_sha256"] = (
            "sha256:"
            + sha256(FrozenJsonDocument.from_value(value).canonical_json).hexdigest()
        )
        raw = FrozenJsonDocument.from_value(value).canonical_json
        manifest_path.write_bytes(raw)
        current["input_snapshot_manifest_sha256"] = value["content_sha256"]
        current["artifact_bindings"]["inputs/input_snapshot_manifest.json"] = (
            "sha256:" + sha256(raw).hexdigest()
        )
        current.pop("content_sha256")
        (root / "session.json").write_bytes(
            session._seal_session_value(current, session_identity=None).canonical_json
        )
    monkeypatch.setattr(
        controller,
        "_load_unsigned_draft",
        lambda *_args, **_kwargs: pytest.fail("read draft before frozen validation"),
    )
    with pytest.raises((ValueError, RuntimeError)):
        controller.validate_live_start_candidate(
            session_root=root, draft_path=tmp_path / "missing.json"
        )


@pytest.mark.parametrize("separator", ["/", "\\"])
def test_quality_receipt_ownership_normalizes_render_paths(separator):
    from hsconfig.output_ownership_manifest import build_output_ownership_manifest
    path = "reports/optimized_start/candidate_validation_receipt.json"
    manifest = build_output_ownership_manifest([path.replace("/", separator)])
    row = manifest["files"][0]
    assert row["classification"] == "diagnostic"
    assert row["configuration_modes"] == ["LLM_OPTIMIZED_START"]
    assert row["diagnostic_only"] is True and row["can_block_apply"] is False
    assert manifest["summary"]["unclassified_file_count"] == 0


def test_quality_approved_preview_has_full_receipt_and_strict_derivation(
    quality_request, tmp_path, monkeypatch
):
    from hsconfig.input_snapshot_manifest import load_frozen_compiler_inputs
    from hsconfig.starter_context import build_quality_starter_context
    from hsconfig.starter_candidate import validate_starter_candidate
    from tests.test_quality_starter_candidate import (
        quality_draft,
        seal_quality_candidate,
    )
    from tests.test_quality_starter_review import quality_review
    import hsconfig.package_render_authority as renderer

    strict_validate = renderer.validate_complete_package_from_view

    def assert_strict(package):
        result = strict_validate(package)
        assert result.get("status") == "passed", result.get("errors")
        return result

    monkeypatch.setattr(renderer, "validate_complete_package_from_view", assert_strict)
    discovery = controller.prepare_quality_live_start(quality_request)
    prepared = controller.complete_live_start_research(
        session_root=discovery.run_root, draft_path=_empty_draft(tmp_path, discovery)
    )
    context = build_quality_starter_context(
        load_frozen_compiler_inputs(prepared.run_root)
    )
    draft = quality_draft(context)
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_bytes(FrozenJsonDocument.from_value(draft).canonical_json)
    receipt = controller.validate_live_start_candidate(
        session_root=prepared.run_root, draft_path=candidate_path
    )
    assert receipt.to_value()["schema_version"] == 2
    assert receipt.to_value()["run_id"] == prepared.run_root.name
    assert receipt.to_value()["review_facts"]["runtime_authorized"] is False
    candidate = validate_starter_candidate(
        seal_quality_candidate(draft), context=context
    )
    review = quality_review(context, candidate, receipt)
    review_value = review.to_value()
    review_value.pop("content_sha256")
    review_path = tmp_path / "review.json"
    review_path.write_bytes(FrozenJsonDocument.from_value(review_value).canonical_json)
    controller.validate_live_start_review(
        session_root=prepared.run_root, draft_path=review_path
    )
    result = controller.finalize_live_start(session_root=prepared.run_root)
    assert result.status == "PREVIEW_READY"
    from pathlib import Path
    from hsconfig.visionai_registry import (
        optimized_start_report_paths_for_manifest,
        SINGLE_CANDIDATE_REVIEW_REPORT_PATHS,
    )
    from hsconfig.optimized_start_authority import load_optimized_start_authority
    from hsconfig.package_derivation_receipt import (
        build_package_derivation_receipt,
        verify_package_derivation_receipt,
    )

    published = load_live_start_session(prepared.run_root).publication_binding
    package = Path(published["output_child_path"]) / published["revision"] / "04_package"
    manifest = FrozenJsonDocument.from_json_bytes(
        (package / "reports/input_manifest.json").read_bytes()
    ).to_value()
    receipt_logical = "reports/optimized_start/candidate_validation_receipt.json"
    assert optimized_start_report_paths_for_manifest(manifest) == (
        *SINGLE_CANDIDATE_REVIEW_REPORT_PATHS,
        receipt_logical,
    )
    authority = load_optimized_start_authority(
        report_root=package / "reports/optimized_start", manifest=manifest
    )
    assert authority.validation_receipt == receipt
    derivation = build_package_derivation_receipt(package)
    assert derivation["schema_version"] == 4
    assert verify_package_derivation_receipt(package, derivation) == (True, [])
    ownership = FrozenJsonDocument.from_json_bytes(
        (package / "reports/output_ownership_manifest.json").read_bytes()
    ).to_value()
    row = next(row for row in ownership["files"] if row["file"] == receipt_logical)
    assert row["classification"] == "diagnostic"
    assert row["configuration_modes"] == ["LLM_OPTIMIZED_START"]
    assert row["diagnostic_only"] is True and row["can_block_apply"] is False
    report = package / receipt_logical
    original = report.read_bytes()
    for payload in (None, b"{}"):
        if payload is None:
            report.unlink()
        else:
            report.write_bytes(payload)
        with pytest.raises((ValueError, OSError)):
            load_optimized_start_authority(report_root=report.parent, manifest=manifest)
        assert verify_package_derivation_receipt(package, derivation)[0] is False
    report.write_bytes(original)


@pytest.mark.parametrize("defect", [None, "missing", "tampered"])
def test_quality_revision_resume_requires_original_receipt(
    quality_request, tmp_path, defect
):
    from hsconfig.input_snapshot_manifest import load_frozen_compiler_inputs
    from hsconfig.starter_context import build_quality_starter_context
    from hsconfig.starter_candidate import validate_starter_candidate
    from tests.test_quality_starter_candidate import (
        quality_draft,
        seal_quality_candidate,
    )
    from tests.test_quality_starter_review import quality_review

    discovery = controller.prepare_quality_live_start(quality_request)
    prepared = controller.complete_live_start_research(
        session_root=discovery.run_root, draft_path=_empty_draft(tmp_path, discovery)
    )
    context = build_quality_starter_context(
        load_frozen_compiler_inputs(prepared.run_root)
    )
    draft = quality_draft(context)
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_bytes(FrozenJsonDocument.from_value(draft).canonical_json)
    receipt = controller.validate_live_start_candidate(
        session_root=prepared.run_root, draft_path=candidate_path
    )
    candidate = validate_starter_candidate(
        seal_quality_candidate(draft), context=context
    )
    review = quality_review(
        context,
        candidate,
        receipt,
        mutate=lambda value: value.update(
            {
                "review_status": "revision_requested",
                "revision_requests": [
                    {
                        "code": "tighten-mulligan",
                        "target": "mulligan",
                        "message": "Keep only the strongest opener.",
                    }
                ],
            }
        ),
    ).to_value()
    review.pop("content_sha256")
    review_path = tmp_path / "review.json"
    review_path.write_bytes(FrozenJsonDocument.from_value(review).canonical_json)
    result = controller.validate_live_start_review(
        session_root=prepared.run_root, draft_path=review_path
    )
    assert result.to_value()["status"] == "revision_required"
    before = load_live_start_session(prepared.run_root)
    assert before.revisions_used == 1
    assert before.candidate_revision == 1
    assert not (prepared.run_root / "receipts/candidate_validation.json").exists()
    original = (
        prepared.run_root.parent.parent
        / "contexts"
        / before.run_id
        / "install_candidate_validation-r1-u0-0-candidate_validation.json"
    )
    if defect == "missing":
        original.unlink()
    elif defect == "tampered":
        original.write_bytes(b"{}")
    if defect is None:
        resumed = controller.resume_live_start(session_root=prepared.run_root)
        assert resumed.to_value()["status"] == "revision_required"
    else:
        with pytest.raises((OSError, RuntimeError, ValueError)):
            controller.resume_live_start(session_root=prepared.run_root)
    after = load_live_start_session(prepared.run_root)
    assert (after.candidate_revision, after.revisions_used) == (1, 1)
