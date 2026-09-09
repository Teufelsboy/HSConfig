from __future__ import annotations

from pathlib import Path

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig import output_publisher, runtime_installer
from hsconfig.apply_invocation import load_apply_invocation
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.operator_profile import (
    disable_operator_profile,
    enable_operator_profile,
    operator_profile_path,
)
from hsconfig.runtime_live_admission import (
    load_runtime_live_attempt_admission,
)
from hsconfig.runtime_package_match import build_runtime_package_match_report
from hsconfig.runtime_transaction_journal import (
    load_runtime_transaction_journals,
    runtime_transaction_journal_path,
)
from tests.test_codex_first_live_e2e import _local_state, _prepare_approved
from tests.test_output_publisher import build_rendered_run


class AdmissionStop(BaseException):
    pass


def _tree_bytes(root: Path) -> dict[str, bytes | None]:
    return {
        path.relative_to(root).as_posix(): (
            None if path.is_dir() else path.read_bytes()
        )
        for path in root.rglob("*")
    }


def test_crash_after_admission_before_receipt_blocks_every_affected_writer_and_continues_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A durable admission is committed work even before its invocation receipt."""
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(
        tmp_path / "pipeline",
        monkeypatch,
    )
    rendered = build_rendered_run(tmp_path / "publisher-source", 13)
    rebound_runtime = tmp_path / "rebound-runtime"
    rebound_output = tmp_path / "rebound-output"
    rebound_runtime.mkdir()
    rebound_output.mkdir()
    reached: list[LiveStartFaultPoint] = []

    def stop(observed: LiveStartFaultPoint) -> None:
        reached.append(observed)
        if (
            observed
            is LiveStartFaultPoint.AFTER_ADMISSION_BOUND_BEFORE_INVOCATION_WRITE
        ):
            raise AdmissionStop(observed.value)

    with pytest.raises(
        AdmissionStop,
        match="^after_admission_bound_before_invocation_write$",
    ):
        controller._finalize_live_start(
            session_root=prepared.run_root,
            fault_hook=stop,
        )

    interrupted = session.load_live_start_session(prepared.run_root)
    pending = interrupted.pending_transition
    assert interrupted.phase is session.LiveStartPhase.PUBLICATION_COMMITTED
    assert pending["operation"] == "install_apply_invocation"
    assert pending["stage"] == "PRIMARY_APPLIED"
    attempt_id = pending["apply_attempt_id"]
    assert len(attempt_id) == 32
    assert interrupted.apply_invocation_sha256 is None
    assert interrupted.runtime_layout_bootstrap is None
    assert interrupted.apply_recovery is None
    assert interrupted.result_intent is None
    assert interrupted.terminal_status is None

    invocation_path = prepared.run_root / "receipts/apply_invocation.json"
    assert not invocation_path.exists()
    admission = load_runtime_live_attempt_admission()
    assert admission is not None
    assert admission.run_id == interrupted.run_id
    assert admission.apply_attempt_id == attempt_id
    assert admission.retention_owner_run_id == interrupted.run_id
    assert admission.apply_invocation_sha256 == pending["apply_invocation_sha256"]
    assert admission.publication_revision == interrupted.publication_binding["revision"]
    assert (
        admission.publication_content_root_sha256
        == interrupted.publication_binding["content_root_sha256"]
    )
    assert interrupted.runtime_admission_binding is None
    assert pending["runtime_admission_path"] == str(admission.admission_path)
    assert (
        pending["runtime_admission_parent_identity"]
        == admission.admission_parent_identity
    )
    assert pending["runtime_admission_identity"] == admission.admission_identity
    assert pending["runtime_admission_sha256"] == admission.admission_sha256
    assert (
        pending["runtime_admission_document_sha256"]
        == admission.admission_sha256
    )

    # Freeze the same-deck contender after the owner publication exists, so
    # its output-child precondition remains valid up to the admission gate.
    _competing_fixture, competing = _prepare_approved(
        tmp_path / "competing-preview",
        monkeypatch,
        preview=True,
        profile=fixture.profile,
    )

    publication = interrupted.publication_binding
    output_root = Path(publication["output_child_path"])
    revision_root = output_root / publication["revision"]
    legacy_plan = runtime_installer.plan_runtime_install(
        published_output=output_publisher.PublishedOutput(
            output_root=output_root,
            revision_root=revision_root,
            package_root=revision_root / "04_package",
            content_root_sha256=publication["content_root_sha256"].removeprefix(
                "sha256:"
            ),
            reused_existing_revision=False,
        ),
        runtime_root=fixture.profile.runtime_root,
    )
    target = (
        fixture.profile.runtime_root
        / "CustomConfig"
        / legacy_plan.versioned_config_dir
    )
    assert load_runtime_transaction_journals(fixture.profile.runtime_root) == ()
    assert not target.exists()
    assert not (fixture.profile.runtime_root / "CustomConfig/deck_config.ini").exists()
    assert not (fixture.profile.runtime_root / ".hsconfig/state").exists()
    assert not (fixture.profile.runtime_root / ".hsconfig/receipts").exists()
    assert not admission.retention_fence_path.exists()

    runtime_before = _tree_bytes(fixture.profile.runtime_root)
    output_before = _tree_bytes(fixture.profile.output_base_root)
    profile_before = operator_profile_path().read_bytes()
    operation_path = Path(
        interrupted.output_operation_admission_binding["admission_path"]
    )
    operation_before = operation_path.read_bytes()
    admission_before = admission.admission_path.read_bytes()
    owner_session_before = (prepared.run_root / "session.json").read_bytes()

    def assert_owner_surfaces_unchanged() -> None:
        assert _tree_bytes(fixture.profile.runtime_root) == runtime_before
        assert _tree_bytes(fixture.profile.output_base_root) == output_before
        assert operator_profile_path().read_bytes() == profile_before
        assert operation_path.read_bytes() == operation_before
        assert admission.admission_path.read_bytes() == admission_before
        assert (prepared.run_root / "session.json").read_bytes() == owner_session_before

    with pytest.raises(
        ValueError,
        match="^output_operation_admission_blocks_runtime_mutation$",
    ):
        runtime_installer.install_runtime_package(legacy_plan)
    assert_owner_surfaces_unchanged()

    with pytest.raises(
        ValueError,
        match="^output_operation_admission_blocks_runtime_mutation$",
    ):
        runtime_installer.recover_runtime_state(fixture.profile.runtime_root)
    assert_owner_surfaces_unchanged()

    with pytest.raises(
        ValueError,
        match="^live_start_output_operation_already_present$",
    ):
        controller.finalize_live_start(session_root=competing.run_root)
    assert_owner_surfaces_unchanged()

    with pytest.raises(
        ValueError,
        match="^runtime_live_admission_blocks_publication$",
    ):
        output_publisher.publish_configure_run(
            rendered,
            output_root,
        )
    assert_owner_surfaces_unchanged()

    with pytest.raises(
        ValueError,
        match="^runtime_live_admission_blocks_profile_mutation$",
    ):
        disable_operator_profile(
            expected_predecessor_sha256=fixture.profile.content_sha256
        )
    assert_owner_surfaces_unchanged()

    with pytest.raises(
        ValueError,
        match="^runtime_live_admission_blocks_profile_mutation$",
    ):
        enable_operator_profile(
            runtime_root=rebound_runtime,
            output_base_root=rebound_output,
            expected_predecessor_sha256=fixture.profile.content_sha256,
        )
    assert_owner_surfaces_unchanged()
    assert _tree_bytes(rebound_runtime) == {}
    assert _tree_bytes(rebound_output) == {}

    result = controller._finalize_live_start(
        session_root=prepared.run_root,
        resume_intake=True,
        fault_hook=reached.append,
    )
    terminal = session.load_live_start_session(prepared.run_root)
    assert result.status == terminal.terminal_status == "LIVE_AND_MATCHED"
    runtime_binding = terminal.runtime_admission_binding
    assert runtime_binding["admission_path"] == str(admission.admission_path)
    assert runtime_binding["admission_identity"] == admission.admission_identity
    assert runtime_binding["admission_sha256"] == admission.admission_sha256
    assert terminal.publication_binding == publication
    assert terminal.input_snapshot_manifest_sha256 == (
        interrupted.input_snapshot_manifest_sha256
    )
    for logical_path in (
        "starter/starter_config_candidate.json",
        "starter/starter_config_review.json",
    ):
        assert (
            terminal.artifact_bindings[logical_path]
            == interrupted.artifact_bindings[logical_path]
        )
    invocation = load_apply_invocation(invocation_path)
    assert invocation.apply_attempt_id == attempt_id
    assert invocation.content_sha256 == admission.apply_invocation_sha256
    assert list(prepared.run_root.rglob("apply_invocation.json")) == [invocation_path]
    journals = load_runtime_transaction_journals(fixture.profile.runtime_root)
    assert len(journals) == 1
    owner = journals[0]
    assert owner.transaction_id == attempt_id
    assert owner.owns_target is True
    assert fixture.profile.runtime_root / owner.target_path == target
    assert runtime_transaction_journal_path(
        fixture.profile.runtime_root,
        attempt_id,
    ).is_file()
    report = build_runtime_package_match_report(
        package_root=revision_root / "04_package",
        runtime_root=fixture.profile.runtime_root,
    )
    assert report["status"] == "matched"
    assert report["runtime_mapping_identity_valid"] is True
    assert report["runtime_tree_identity_valid"] is True
    assert report["missing_in_runtime"] == report["extra_in_runtime"] == []
    assert report["semantic_mismatch_count"] == 0
    assert terminal.terminal_retirement["apply_attempt_id"] == attempt_id
    assert terminal.terminal_retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"
    assert not admission.admission_path.exists()
    assert not operation_path.exists()
    assert reached.count(
        LiveStartFaultPoint.AFTER_INVOCATION_PREPARED_BEFORE_ADMISSION
    ) == 1
    assert reached.count(
        LiveStartFaultPoint.AFTER_ADMISSION_BOUND_BEFORE_INVOCATION_WRITE
    ) == 1
    assert reached.count(LiveStartFaultPoint.AFTER_APPLY_STARTED) == 1

    terminal_session_bytes = (prepared.run_root / "session.json").read_bytes()
    terminal_runtime = _tree_bytes(fixture.profile.runtime_root)
    terminal_summary = result.summary.canonical_json
    again = controller.resume_live_start(session_root=prepared.run_root)
    assert again.summary.canonical_json == terminal_summary
    assert (prepared.run_root / "session.json").read_bytes() == terminal_session_bytes
    assert _tree_bytes(fixture.profile.runtime_root) == terminal_runtime
    assert load_runtime_transaction_journals(fixture.profile.runtime_root) == journals
    assert {
        path for path in (fixture.profile.runtime_root / "CustomConfig").iterdir()
        if path.is_dir()
    } == {target}


def _assert_same_attempt_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    point: LiveStartFaultPoint,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "pipeline", monkeypatch)
    reached: list[LiveStartFaultPoint] = []

    def stop(observed: LiveStartFaultPoint) -> None:
        reached.append(observed)
        if observed is point:
            raise AdmissionStop(point.value)

    with pytest.raises(AdmissionStop, match=point.value):
        controller._finalize_live_start(
            session_root=prepared.run_root, fault_hook=stop,
        )
    interrupted = session.load_live_start_session(prepared.run_root)
    invocation_path = prepared.run_root / "receipts/apply_invocation.json"
    invocation = load_apply_invocation(invocation_path)
    invocation_bytes = invocation_path.read_bytes()
    attempt_id = invocation.apply_attempt_id
    admission = load_runtime_live_attempt_admission()
    assert admission is not None
    assert admission.apply_attempt_id == attempt_id
    assert admission.apply_invocation_sha256 == invocation.content_sha256
    assert interrupted.runtime_layout_bootstrap["apply_attempt_id"] == attempt_id
    assert interrupted.runtime_layout_bootstrap["stage"] == "COMPLETE"
    assert interrupted.apply_recovery is None
    assert interrupted.closed_apply_recovery_commitment is None
    assert interrupted.result_intent is None
    assert load_runtime_transaction_journals(fixture.profile.runtime_root) == ()
    assert not (fixture.profile.runtime_root / "deck_config.ini").exists()
    runtime_before = {
        path.relative_to(fixture.profile.runtime_root): path.read_bytes()
        for path in fixture.profile.runtime_root.rglob("*") if path.is_file()
    }
    if point is not LiveStartFaultPoint.AFTER_APPLY_STARTED:
        assert interrupted.phase is session.LiveStartPhase.PUBLICATION_COMMITTED
        assert interrupted.pending_transition["operation"] == "install_apply_invocation"
        assert interrupted.pending_transition["stage"] == "PRIMARY_APPLIED"
        assert interrupted.pending_transition["apply_attempt_id"] == attempt_id
        if point is LiveStartFaultPoint.AFTER_INVOCATION_WRITE_BEFORE_APPLY_STARTED:
            assert interrupted.pending_transition["next_action_index"] == 1
            assert interrupted.pending_transition["external_file_action"] is None
        else:
            assert interrupted.pending_transition["next_action_index"] == 0
            external = interrupted.pending_transition["external_file_action"]
            assert external["stage"] == "STAGING_BOUND"
            assert external["final_path"] == str(invocation_path)
    else:
        assert interrupted.phase is session.LiveStartPhase.APPLY_STARTED
        assert interrupted.pending_transition is None

    def stop_after_recovered_intent(observed: LiveStartFaultPoint) -> None:
        reached.append(observed)
        if observed is LiveStartFaultPoint.AFTER_RESULT_INTENT:
            raise AdmissionStop(observed.value)

    with pytest.raises(AdmissionStop, match="after_result_intent"):
        controller._finalize_live_start(
            session_root=prepared.run_root, resume_intake=True,
            fault_hook=stop_after_recovered_intent,
        )
    recovered = session.load_live_start_session(prepared.run_root)
    assert recovered.phase is session.LiveStartPhase.APPLY_STARTED
    assert recovered.pending_transition is None
    assert recovered.apply_recovery is None
    closed = recovered.closed_apply_recovery_commitment
    assert closed["recovery_stage"] == "CLOSED"
    assert closed["apply_attempt_id"] == attempt_id
    assert closed["apply_invocation_sha256"] == invocation.content_sha256
    assert closed["stable_physical_disposition"] == "NOT_COMMITTED"
    assert closed["predecessor_journal_path"] is None
    assert closed["successor_journal_path"] is None
    assert closed["planned_journal_successor_phase"] is None
    intent = recovered.result_intent
    assert intent["apply_attempt_id"] == attempt_id
    assert intent["physical_disposition"] == "NOT_COMMITTED"
    assert intent["raw_apply_status"] is None
    assert intent["runtime_match_status"] == "not_run"
    assert intent["retained_journal_path"] is None
    assert recovered.attempt_acknowledgement is None
    assert invocation_path.read_bytes() == invocation_bytes
    journals = load_runtime_transaction_journals(fixture.profile.runtime_root)
    assert journals == ()
    transaction_root = fixture.profile.runtime_root / ".hsconfig/transactions"
    assert list(transaction_root.iterdir()) == []
    assert reached.count(LiveStartFaultPoint.AFTER_INVOCATION_PREPARED_BEFORE_ADMISSION) == 1
    assert reached.count(LiveStartFaultPoint.AFTER_APPLY_STARTED) == 1

    result = controller.resume_live_start(session_root=prepared.run_root)
    terminal = session.load_live_start_session(prepared.run_root)
    assert result.status == "FAILED_PRESERVED"
    assert terminal.result_intent == intent
    assert terminal.closed_apply_recovery_commitment is None
    assert terminal.terminal_retirement["apply_attempt_id"] == attempt_id
    assert terminal.terminal_retirement["operation"] == "release_not_committed"
    assert terminal.pending_transition is None
    assert terminal.apply_recovery is None
    assert load_runtime_live_attempt_admission() is None
    assert invocation_path.read_bytes() == invocation_bytes
    assert load_runtime_transaction_journals(fixture.profile.runtime_root) == journals
    assert {
        path.relative_to(fixture.profile.runtime_root): path.read_bytes()
        for path in fixture.profile.runtime_root.rglob("*") if path.is_file()
    } == runtime_before

    # Once terminal, a further public resume must not create a new cursor or file.
    terminal_bytes = (prepared.run_root / "session.json").read_bytes()
    again = controller.resume_live_start(session_root=prepared.run_root)
    assert again.summary.canonical_json == result.summary.canonical_json
    assert (prepared.run_root / "session.json").read_bytes() == terminal_bytes
    assert load_runtime_transaction_journals(fixture.profile.runtime_root) == journals
    assert list(transaction_root.iterdir()) == []


@pytest.mark.parametrize("point", [
    LiveStartFaultPoint.AFTER_INVOCATION_WRITE_BEFORE_APPLY_STARTED,
    LiveStartFaultPoint.AFTER_INVOCATION_RECEIPT_BOUND_COMMIT_BEFORE_CAS,
], ids=["receipt-cas-complete", "physical-receipt-before-cas"])
def test_crash_after_invocation_receipt_never_reapplies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, point: LiveStartFaultPoint,
) -> None:
    _assert_same_attempt_recovery(
        tmp_path, monkeypatch, point,
    )


def test_crash_after_apply_started_never_reapplies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_same_attempt_recovery(
        tmp_path, monkeypatch, LiveStartFaultPoint.AFTER_APPLY_STARTED,
    )
