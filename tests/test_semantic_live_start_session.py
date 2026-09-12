"""Semantic early-session route guards; no future schema4 authority is fabricated."""

from dataclasses import replace
from pathlib import Path

import pytest

from hsconfig import live_start_session as sessions
from hsconfig.starter_contract import SEMANTIC_LIVE_CONTRACT, QUALITY_LIVE_CONTRACT
from tests.test_quality_live_start_controller import quality_request as quality_request
from hsconfig import live_start_controller as controller
from hsconfig.package_request import FrozenJsonDocument
from tests.test_semantic_input_snapshot import semantic_frozen_inputs


def _bootstrap_frozen(tmp_path, monkeypatch, *, compiler="hsconfig-live-start-v3"):
    frozen = semantic_frozen_inputs(tmp_path, monkeypatch, compiler=compiler)
    cards = FrozenJsonDocument.from_value(
        {
            "full_cards": frozen.full_cards.to_value(),
            "collectible_cards": frozen.collectible_cards.to_value(),
            "globalvalues_baseline": frozen.globalvalues_baseline.to_value(),
        }
    ).canonical_json
    # These carriers exercise session journaling, not research execution.
    seeds = {
        "inputs/deck.json": frozen.deck.canonical_json,
        "inputs/cards.json": cards,
        "inputs/quality_seed.json": b"{}",
        "research/request.json": b"{}",
        "research/progress.json": b"{}",
    }
    root = tmp_path / "local-app-data/HSConfig/runs/0123456789abcdef0123456789abcdef"
    current = sessions.create_live_start_session(
        session_root=root,
        repository_root=tmp_path / "repo",
        runtime_root=tmp_path / "runtime",
        output_base_root=tmp_path / "outputs",
        output_deck_root=tmp_path / "outputs/shadowpriest",
        installed_skill_root=tmp_path / "skill",
        deck_name="ShadowPriest",
        preview_requested=True,
        deck_code_sha256=frozen.manifest.compiler_inputs.to_value()["deck_code_sha256"],
        contract=SEMANTIC_LIVE_CONTRACT,
        _quality_documents=seeds,
        _research_binding={
            "request_sha256": sessions._bytes_sha256(b"{}"),
            "seed_sha256": sessions._bytes_sha256(b"{}"),
            "deck_sha256": sessions._bytes_sha256(seeds["inputs/deck.json"]),
            "cards_sha256": sessions._bytes_sha256(cards),
        },
    )
    with sessions.lease_live_start_session(root) as lease:
        current = controller._continue_quality_documents(
            session_lease=lease, current=current
        )
    documents = {
        "inputs/input_snapshot_manifest.json": frozen.manifest.document.canonical_json,
        "inputs/quality.json": frozen.quality_inputs.canonical_json,
        "inputs/sources.json": FrozenJsonDocument.from_value(
            {
                "source_acquisition": frozen.source_acquisition.to_value(),
                "source_documents": frozen.source_documents.to_value(),
            }
        ).canonical_json,
    }
    return root, current, frozen, documents


def _prepare_freeze(root, current, documents):
    actions = []
    for logical, payload in sorted(documents.items()):
        source = controller._write_external_authority_source(
            session_root=root,
            name=f"quality_freeze-{sessions._bytes_sha256(payload)[7:]}-{Path(logical).name}",
            payload=payload,
        )
        actions.append(
            sessions._quality_action(logical=logical, source=source, payload=payload)
        )
    pending = sessions._empty_pending_transition(
        session=current, operation="quality_freeze", external_file_action=None
    )
    pending.update(
        actions=actions,
        target_phase="INPUT_FROZEN",
        successor_artifact_bindings={
            **current.artifact_bindings,
            **{row["logical_path"]: row["sha256"] for row in actions},
        },
    )
    with sessions.lease_live_start_session(root) as lease:
        return controller._quality_checkpoint(
            session_lease=lease,
            current=current,
            changes={"pending_transition": sessions._seal_pending(pending)},
        )


def _primary(root, current):
    pending = sessions._thaw(current.pending_transition)
    pending["stage"] = "PRIMARY_APPLIED"
    with sessions.lease_live_start_session(root) as lease:
        return controller._quality_checkpoint(
            session_lease=lease,
            current=current,
            changes={"pending_transition": sessions._seal_pending(pending)},
        )


def _finish_freeze(root, current, documents):
    current = _prepare_freeze(root, current, documents)
    with sessions.lease_live_start_session(root) as lease:
        return controller._continue_quality_documents(
            session_lease=lease, current=current
        )


@pytest.mark.parametrize(
    "compiler", ["hsconfig-live-start-v3", "hsconfig-live-start-v2"]
)
def test_semantic_internal_frozen_validation_binds_descriptor(
    tmp_path, monkeypatch, compiler
):
    frozen = semantic_frozen_inputs(tmp_path, monkeypatch, compiler=compiler)
    operator = frozen.manifest.operator_bindings.to_value()
    kwargs = dict(
        deck_name="ShadowPriest",
        deck_code_sha256=frozen.manifest.compiler_inputs.to_value()["deck_code_sha256"],
        runtime_root=Path(operator["runtime_root"]),
        output_base_root=Path(operator["output_base_root"]),
        output_deck_root=Path(operator["output_base_root"])
        / operator["deck_output_name"],
        contract=SEMANTIC_LIVE_CONTRACT,
    )
    if compiler == "hsconfig-live-start-v2":
        with pytest.raises((ValueError, sessions.SessionConflictError)):
            sessions._validate_frozen_compiler_inputs(frozen, **kwargs)
    else:
        documents, digest = sessions._validate_frozen_compiler_inputs(frozen, **kwargs)
        assert documents["inputs/quality.json"] == frozen.quality_inputs.canonical_json
        assert digest == frozen.manifest.document.content_sha256


@pytest.mark.parametrize("mutation", ["identity", "bytes", "size", "premature_target"])
def test_semantic_pending_manifest_physical_guards(tmp_path, monkeypatch, mutation):
    root, current, _, documents = _bootstrap_frozen(tmp_path, monkeypatch)
    current = _prepare_freeze(root, current, documents)
    row = current.pending_transition["actions"][0]
    source = Path(row["source_path"])
    raw = source.read_bytes()
    if mutation == "identity":
        source.rename(source.with_suffix(".retained"))
        source.write_bytes(raw)
    elif mutation == "bytes":
        source.write_bytes(raw.replace(b"visionai-runtime-v1", b"visionai-runtime-v2"))
    elif mutation == "size":
        source.write_bytes(raw + b" ")
    else:
        (root / row["logical_path"]).write_bytes(raw)
    with pytest.raises((ValueError, OSError, sessions.SessionConflictError)):
        sessions.load_live_start_session(root)


@pytest.mark.parametrize(
    "mutation",
    ["quality_missing", "quality_tampered", "commitment", "version_bool", "manifest2"],
)
def test_semantic_final_binding_rejects_coherent_mutation(
    tmp_path, monkeypatch, mutation
):
    root, current, frozen, documents = _bootstrap_frozen(tmp_path, monkeypatch)
    current = _finish_freeze(root, current, documents)
    value = current.to_value()
    if mutation == "quality_missing":
        (root / "inputs/quality.json").unlink()
    elif mutation == "quality_tampered":
        quality = frozen.quality_inputs.to_value()
        quality["card_snapshot_captured_at"] = "2026-09-10T00:00:00Z"
        raw = FrozenJsonDocument.from_value(quality).canonical_json
        (root / "inputs/quality.json").write_bytes(raw)
        value["artifact_bindings"]["inputs/quality.json"] = sessions._bytes_sha256(raw)
    elif mutation == "commitment":
        value["input_snapshot_manifest_sha256"] = "sha256:" + "a" * 64
    elif mutation == "version_bool":
        value["schema_version"] = True
    else:
        # An adversarial coherent downgrade; the original positive was genuinely frozen as v3.
        from hsconfig.starter_document import seal_starter_document
        from hsconfig.input_snapshot_manifest import INPUT_SNAPSHOT_FIELDS

        manifest = frozen.manifest.document.to_value()
        manifest.pop("content_sha256")
        manifest["schema_version"] = 2
        manifest["compiler_inputs"]["compiler_contract_id"] = "hsconfig-live-start-v2"
        downgraded = seal_starter_document(
            manifest, expected_fields=INPUT_SNAPSHOT_FIELDS, schema_version=2
        )
        (root / "inputs/input_snapshot_manifest.json").write_bytes(
            downgraded.canonical_json
        )
        value["artifact_bindings"]["inputs/input_snapshot_manifest.json"] = (
            sessions._bytes_sha256(downgraded.canonical_json)
        )
        value["input_snapshot_manifest_sha256"] = downgraded.content_sha256
    value.pop("content_sha256")
    value["content_sha256"] = sessions._self_digest(value)
    (root / "session.json").write_bytes(sessions._canonical_json(value))
    with pytest.raises((ValueError, OSError, sessions.SessionConflictError)):
        sessions.load_live_start_session(root)


@pytest.mark.parametrize("mutation", ["old_inner", "unbound_context"])
def test_semantic_completed_receipt_rejects_genuine_old_authority(
    tmp_path, monkeypatch, mutation
):
    from hsconfig.starter_context import (
        build_quality_starter_context,
        validate_starter_context_document,
    )
    from hsconfig.starter_contract import (
        QUALITY_STARTER_CONTEXT_FIELDS,
        QUALITY_CANDIDATE_VALIDATION_RECEIPT_FIELDS,
    )
    from hsconfig.starter_document import seal_starter_document
    from hsconfig.starter_candidate import validate_starter_candidate
    from hsconfig.starter_review import build_candidate_review_facts
    from tests.test_quality_starter_candidate import (
        quality_draft,
        seal_quality_candidate,
    )

    root, current, frozen, documents = _bootstrap_frozen(tmp_path, monkeypatch)
    current = _finish_freeze(root, current, documents)
    old_root = tmp_path / "old-context-fixture"
    old_root.mkdir()
    old_inputs = semantic_frozen_inputs(
        old_root, monkeypatch, compiler="hsconfig-live-start-v2"
    )
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    old = build_quality_starter_context(old_inputs).document.to_value()
    old.pop("content_sha256")
    old["input_snapshot_manifest_sha256"] = frozen.manifest.document.content_sha256
    context = validate_starter_context_document(
        seal_starter_document(
            old, expected_fields=QUALITY_STARTER_CONTEXT_FIELDS, schema_version=3
        )
    )
    candidate = validate_starter_candidate(
        seal_quality_candidate(quality_draft(context)), context=context
    )
    facts = build_candidate_review_facts(
        context=context, candidate=candidate
    ).to_value()
    assert facts["schema_version"] == 1
    receipt = seal_starter_document(
        {
            "schema_version": 3,
            "receipt_kind": "candidate_validation",
            "run_id": current.run_id,
            "candidate_revision": 1,
            "starter_context_sha256": context.document.content_sha256,
            "candidate_sha256": candidate.document.content_sha256,
            "status": "valid",
            "findings": [],
            "review_facts": facts,
        },
        expected_fields=QUALITY_CANDIDATE_VALIDATION_RECEIPT_FIELDS,
        schema_version=3,
    )
    sessions.validate_validation_receipt(
        receipt_kind="candidate_validation",
        value=receipt.to_value(),
        run_id=current.run_id,
        candidate_revision=1,
    )
    value = current.to_value()
    for logical, raw in {
        "starter/starter_context.json": context.document.canonical_json,
        "starter/starter_config_candidate.json": candidate.document.canonical_json,
        "receipts/candidate_validation.json": receipt.canonical_json + b"\n",
    }.items():
        path = root / logical
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(raw)
        value["artifact_bindings"][logical] = sessions._bytes_sha256(raw)
    value["phase"] = "CANDIDATE_VALIDATED"
    sealed = sessions._seal_session_value(value, session_identity=None)
    (root / "session.json").write_bytes(sealed.canonical_json)
    current = sessions.load_live_start_session(root)
    if mutation == "unbound_context":
        # A freshly sealed, valid old context still cannot replace bound bytes.
        old["input_snapshot_manifest_sha256"] = "sha256:" + "b" * 64
        fresh = seal_starter_document(
            old, expected_fields=QUALITY_STARTER_CONTEXT_FIELDS, schema_version=3
        )
        (root / "starter/starter_context.json").write_bytes(fresh.canonical_json)
    error = (
        "artifact_changed"
        if mutation == "unbound_context"
        else "semantic_context_version"
    )
    with pytest.raises(sessions.SessionConflictError, match=error):
        sessions._require_completed_receipt_binding(
            session=current,
            session_root=root,
            receipt_kind="candidate_validation",
            receipt=receipt.to_value(),
            receipt_bytes_sha256=sessions._bytes_sha256(receipt.canonical_json + b"\n"),
            receipt_logical_path="receipts/candidate_validation.json",
        )
    with (
        sessions.lease_live_start_session(root) as lease,
        pytest.raises(sessions.SessionConflictError),
    ):
        sessions.validate_resume_under_lock(
            session_lease=lease,
            expected_deck_code_sha256=current.deck_code_sha256,
            expected_input_snapshot_manifest_sha256=current.input_snapshot_manifest_sha256,
        )


@pytest.mark.parametrize("installed", [False, True])
def test_semantic_pending_rejects_real_manifest2(tmp_path, monkeypatch, installed):
    root, current, _, documents = _bootstrap_frozen(
        tmp_path, monkeypatch, compiler="hsconfig-live-start-v2"
    )
    # A coherent manifest2 is forbidden even before remaining envelopes exist.
    if installed:
        # Create a valid pending journal offline, then reproduce installed-before-cursor.
        original = sessions._validate_semantic_manifest_binding
        monkeypatch.setattr(
            sessions, "_validate_semantic_manifest_binding", lambda **_: None
        )
        current = _prepare_freeze(root, current, documents)
        current = _primary(root, current)
        row = current.pending_transition["actions"][0]
        controller._quality_materialize(session_root=root, current=current, row=row)
        monkeypatch.setattr(sessions, "_validate_semantic_manifest_binding", original)
        with pytest.raises(sessions.SessionConflictError, match="semantic_manifest"):
            sessions.load_live_start_session(root)
    else:
        with pytest.raises(sessions.SessionConflictError, match="semantic_manifest"):
            _prepare_freeze(root, current, documents)


@pytest.mark.parametrize(
    "point",
    [
        "staged",
        "installed_before_cursor",
        "after_final_input_installation",
        "during_input_frozen_transition",
    ],
)
def test_semantic_freeze_resume_preserves_route_and_full_binding(
    tmp_path, monkeypatch, point
):
    root, current, frozen, documents = _bootstrap_frozen(tmp_path, monkeypatch)
    if point == "staged":
        progress = b'{"checkpoint":1}'
        with sessions.lease_live_start_session(root) as lease:
            current = controller._install_quality_documents(
                session_lease=lease,
                current=current,
                operation="quality_progress",
                documents={"research/progress.json": progress},
            )
        assert current.schema_version == 3
        assert (root / "research/progress.json").read_bytes() == progress
    current = _prepare_freeze(root, current, documents)
    assert current.pending_transition["schema_version"] == 1
    assert current.input_snapshot_manifest_sha256 is None
    if point == "installed_before_cursor":
        current = _primary(root, current)
        controller._quality_materialize(
            session_root=root,
            current=current,
            row=current.pending_transition["actions"][0],
        )
        assert not (root / "inputs/quality.json").exists()

    class Crash(BaseException):
        pass

    def fault(name):
        if name == point:
            raise Crash

    if point in {"after_final_input_installation", "during_input_frozen_transition"}:
        monkeypatch.setattr(controller, "_quality_fault", fault)
        with sessions.lease_live_start_session(root) as lease, pytest.raises(Crash):
            controller._continue_quality_documents(session_lease=lease, current=current)
    monkeypatch.setattr(controller, "_quality_fault", lambda _: None)
    with sessions.lease_live_start_session(root) as lease:
        current = sessions.load_live_start_session_under_lock(session_lease=lease)
        current = controller._continue_quality_documents(
            session_lease=lease, current=current
        )
    assert current.schema_version == 3
    assert current.phase.value == "INPUT_FROZEN"
    assert (
        current.input_snapshot_manifest_sha256
        == frozen.manifest.document.content_sha256
    )
    assert current.pending_transition is None
    assert (
        sessions.load_live_start_session(root).canonical_json == current.canonical_json
    )
    with sessions.lease_live_start_session(root) as lease:
        resumed = sessions.validate_resume_under_lock(
            session_lease=lease,
            expected_deck_code_sha256=current.deck_code_sha256,
            expected_input_snapshot_manifest_sha256=current.input_snapshot_manifest_sha256,
        )
    assert resumed.canonical_json == current.canonical_json


@pytest.mark.parametrize(
    "point",
    [
        None,
        "before_quality_bootstrap_cursor",
        "after_seed_install",
        "after_request_install",
    ],
)
def test_semantic_bootstrap_crash_retains_route(
    quality_request, monkeypatch, tmp_path, point
):
    original = sessions.create_live_start_session
    monkeypatch.setattr(
        sessions,
        "create_live_start_session",
        lambda **kw: original(**kw, contract=SEMANTIC_LIVE_CONTRACT),
    )

    class Crash(BaseException):
        pass

    def fault(name):
        if name == point:
            raise Crash

    monkeypatch.setattr(controller, "_quality_fault", fault)
    if point is None:
        discovery = controller.prepare_quality_live_start(quality_request)
        run = discovery.run_root
    else:
        with pytest.raises(Crash):
            controller.prepare_quality_live_start(quality_request)
        run = next((tmp_path / "local-app-data/HSConfig/runs").iterdir())
    if point == "before_quality_bootstrap_cursor":
        assert not (run / "session.json").exists()
        assert (run / "inputs/.cards.json.live-start-atomic.tmp").exists()
        return
    current = sessions.load_live_start_session(run)
    assert current.schema_version == 3
    assert current.input_snapshot_manifest_sha256 is None
    binding = current.research_binding
    monkeypatch.setattr(controller, "_quality_fault", lambda _: None)
    monkeypatch.setattr(
        controller, "fetch_card_snapshot", lambda **_: pytest.fail("replayed discovery")
    )
    with sessions.lease_live_start_session(run) as lease:
        current = controller._continue_quality_documents(
            session_lease=lease, current=current
        )
    assert current.schema_version == 3
    assert current.pending_transition is None
    assert current.research_binding == binding
    assert current.phase.value == "DISCOVERY_REQUIRED"


@pytest.mark.parametrize(
    "contract",
    [SEMANTIC_LIVE_CONTRACT, QUALITY_LIVE_CONTRACT, replace(SEMANTIC_LIVE_CONTRACT)],
)
def test_explicit_nonlegacy_direct_creation_rejected_before_writes(tmp_path, contract):
    with pytest.raises(ValueError):
        sessions.create_live_start_session(
            session_root=tmp_path / "local/HSConfig/runs/semantic-test",
            local_app_data_root=tmp_path / "local",
            repository_root=tmp_path / "repo",
            runtime_root=tmp_path / "runtime",
            output_base_root=tmp_path / "output",
            output_deck_root=tmp_path / "output/deck",
            installed_skill_root=tmp_path / "skill",
            deck_name="ShadowPriest",
            deck_code_sha256="sha256:" + "a" * 64,
            preview_requested=True,
            contract=contract,
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("field", ["context", "candidate", "review_facts"])
@pytest.mark.parametrize("bad", [1, 3, True, False, 999, None])
def test_semantic_inner_header_guard_rejects_wrong_exact_versions(field, bad):
    # Header-only values test a predicate, never full document validity.
    values = {
        "context": {"schema_version": 4},
        "candidate": {"schema_version": 4},
        "review_facts": {"schema_version": 2},
    }
    values[field]["schema_version"] = bad
    with pytest.raises(sessions.SessionConflictError, match="semantic"):
        sessions._require_semantic_receipt_headers(
            contract=SEMANTIC_LIVE_CONTRACT, **values
        )


@pytest.mark.parametrize("bad", [1, 3, True, False, 999, None])
def test_rebuilt_semantic_facts_header_rejects_old_or_bool(bad):
    with pytest.raises(sessions.SessionConflictError, match="semantic"):
        sessions._require_semantic_facts_version(
            {"schema_version": bad}, contract=SEMANTIC_LIVE_CONTRACT
        )
