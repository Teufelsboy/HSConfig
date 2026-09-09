from __future__ import annotations

from pathlib import Path

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig.apply_invocation import load_apply_invocation
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.package_io import path_identity
from hsconfig.runtime_live_admission import load_runtime_live_attempt_admission
from hsconfig.runtime_transaction_journal import (
    RuntimeTransactionPhase,
    load_runtime_transaction_journals,
    runtime_transaction_journal_path,
)
from tests.test_codex_first_live_e2e import _local_state, _prepare_approved
from tests.test_configure_prepublication_apply import _physical_tree


class RecoveryClosedStop(BaseException):
    pass


@pytest.mark.parametrize("committed", [True, False], ids=["committed", "not-committed"])
def test_crash_after_recovery_closed_before_result_intent_preserves_cursor_classification_and_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, committed: bool,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "pipeline", monkeypatch)
    runtime_root = fixture.profile.runtime_root
    closure_point = LiveStartFaultPoint.AFTER_RECOVERY_CLOSED_CAS_BEFORE_RESULT_INTENT
    reached: list[LiveStartFaultPoint] = []

    def stop_at(wanted: LiveStartFaultPoint):
        def stop(observed: LiveStartFaultPoint) -> None:
            reached.append(observed)
            if wanted is LiveStartFaultPoint.AFTER_RESULT_INTENT and observed is closure_point:
                raise AssertionError("already-CLOSED recovery fired the closure hook again")
            if observed is wanted:
                raise RecoveryClosedStop(observed.value)
        return stop

    if not committed:
        # A real committed invocation with no journal must recover observation-
        # only. It cannot initiate the first install after this interruption.
        with pytest.raises(RecoveryClosedStop, match="^after_apply_started$"):
            controller._finalize_live_start(
                session_root=prepared.run_root,
                fault_hook=stop_at(LiveStartFaultPoint.AFTER_APPLY_STARTED),
            )
        started = session.load_live_start_session(prepared.run_root)
        assert started.phase is session.LiveStartPhase.APPLY_STARTED
        assert started.apply_recovery is None
        assert load_runtime_transaction_journals(runtime_root) == ()
        before_observation = _physical_tree(runtime_root / "CustomConfig")

    with pytest.raises(RecoveryClosedStop, match=f"^{closure_point.value}$"):
        controller._finalize_live_start(
            session_root=prepared.run_root,
            resume_intake=not committed,
            fault_hook=stop_at(closure_point),
        )

    interrupted = session.load_live_start_session(prepared.run_root)
    closed = interrupted.apply_recovery
    assert closed is not None
    invocation_path = prepared.run_root / "receipts/apply_invocation.json"
    invocation = load_apply_invocation(invocation_path)
    invocation_before = (path_identity(invocation_path), invocation_path.read_bytes())
    admission = load_runtime_live_attempt_admission()
    assert admission is not None
    admission_before = (path_identity(admission.admission_path), admission.admission_path.read_bytes())
    attempt_id = invocation.apply_attempt_id
    disposition = "COMMITTED" if committed else "NOT_COMMITTED"
    match_status = "matched" if committed else "not_run"
    assert admission.apply_attempt_id == closed["apply_attempt_id"] == attempt_id
    assert closed["apply_invocation_sha256"] == invocation.content_sha256
    assert admission.apply_invocation_sha256 == invocation.content_sha256
    assert closed["recovery_stage"] == "CLOSED"
    assert closed["stable_physical_disposition"] == disposition
    assert closed["runtime_match_status"] == match_status
    assert closed["expected_action"] is None
    assert closed["external_file_action"] is None
    assert interrupted.pending_transition is None
    assert interrupted.closed_apply_recovery_commitment is None
    assert interrupted.result_intent is None
    assert interrupted.attempt_acknowledgement is None
    assert interrupted.terminal_status is None
    assert interrupted.terminal_retirement is None
    assert interrupted.phase is (
        session.LiveStartPhase.RUNTIME_MATCHED if committed else session.LiveStartPhase.APPLY_STARTED
    )
    result_paths = tuple(prepared.run_root / "result" / name for name in ("summary.json", "summary.md"))
    assert all(not path.exists() for path in result_paths)
    assert reached.count(closure_point) == 1
    assert reached.count(LiveStartFaultPoint.AFTER_APPLY_STARTED) == 1

    journals = load_runtime_transaction_journals(runtime_root)
    if committed:
        assert len(journals) == 1
        owner = journals[0]
        assert owner.transaction_id == attempt_id
        assert owner.phase is RuntimeTransactionPhase.FINALIZED
        assert owner.owns_target is True
        assert path_identity(runtime_root / owner.target_path) == owner.target_identity
        assert closed["predecessor_journal_path"] == str(runtime_transaction_journal_path(runtime_root, attempt_id))
    else:
        assert journals == ()
        assert closed["predecessor_journal_path"] is None
        assert _physical_tree(runtime_root / "CustomConfig") == before_observation
    journal_before = {
        runtime_transaction_journal_path(runtime_root, row.transaction_id): (
            path_identity(runtime_transaction_journal_path(runtime_root, row.transaction_id)),
            runtime_transaction_journal_path(runtime_root, row.transaction_id).read_bytes(),
        )
        for row in journals
    }
    custom_config_before = _physical_tree(runtime_root / "CustomConfig")

    with pytest.raises(RecoveryClosedStop, match="^after_result_intent$"):
        controller._finalize_live_start(
            session_root=prepared.run_root, resume_intake=True,
            fault_hook=stop_at(LiveStartFaultPoint.AFTER_RESULT_INTENT),
        )
    intent_cursor = session.load_live_start_session(prepared.run_root)
    assert intent_cursor.apply_recovery is None
    assert intent_cursor.closed_apply_recovery_commitment == closed
    assert intent_cursor.phase is interrupted.phase
    assert intent_cursor.terminal_status is None
    intent = intent_cursor.result_intent
    assert intent is not None
    assert intent["apply_attempt_id"] == attempt_id
    assert intent["physical_disposition"] == disposition
    assert intent["runtime_match_status"] == match_status
    assert intent["raw_apply_status"] == ("recovered" if committed else None)
    assert all(not path.exists() for path in result_paths)
    assert reached.count(closure_point) == 1
    assert reached.count(LiveStartFaultPoint.AFTER_APPLY_STARTED) == 1
    assert load_runtime_transaction_journals(runtime_root) == journals
    assert (path_identity(admission.admission_path), admission.admission_path.read_bytes()) == admission_before

    result = controller.resume_live_start(session_root=prepared.run_root)
    terminal = session.load_live_start_session(prepared.run_root)
    expected_status = "LIVE_AND_MATCHED" if committed else "FAILED_PRESERVED"
    assert result.status == terminal.terminal_status == expected_status
    assert terminal.result_intent == intent
    assert terminal.apply_recovery is None
    assert terminal.closed_apply_recovery_commitment is None
    assert terminal.terminal_retirement["apply_attempt_id"] == attempt_id
    assert terminal.terminal_retirement["operation"] == (
        "ack_success" if committed else "release_not_committed"
    )
    assert terminal.terminal_retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"
    assert load_runtime_live_attempt_admission() is None
    assert not admission.admission_path.exists()
    assert (path_identity(invocation_path), invocation_path.read_bytes()) == invocation_before
    assert load_runtime_transaction_journals(runtime_root) == journals
    assert {path: (path_identity(path), path.read_bytes()) for path in journal_before} == journal_before
    assert _physical_tree(runtime_root / "CustomConfig") == custom_config_before
    assert all(path.is_file() for path in result_paths)

    terminal_tree = _physical_tree(prepared.run_root)
    runtime_tree = _physical_tree(runtime_root)
    replayed = controller.resume_live_start(session_root=prepared.run_root)
    assert replayed.summary.canonical_json == result.summary.canonical_json
    assert _physical_tree(prepared.run_root) == terminal_tree
    assert _physical_tree(runtime_root) == runtime_tree
    assert load_runtime_live_attempt_admission() is None
