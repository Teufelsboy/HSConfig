from __future__ import annotations

from pathlib import Path

import pytest

import hsconfig.live_start_controller as controller
import hsconfig.live_start_session as session
import hsconfig.published_apply as published_apply
from hsconfig.live_start_faults import LiveStartFaultPoint
from tests.test_live_start_controller import _approved_run


class TerminalStop(BaseException):
    pass


def _stop_at(wanted: LiveStartFaultPoint):
    def stop(point: LiveStartFaultPoint) -> None:
        if point is wanted:
            raise TerminalStop(point.value)
    return stop


def _result_pair(root: Path) -> dict[str, bytes]:
    return {
        name: (root / "result" / name).read_bytes()
        for name in ("summary.json", "summary.md")
    }


def test_real_controller_terminal_hooks_resume_same_result_without_reapply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    local = tmp_path / "local"
    local.mkdir()
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    prepared = _approved_run(tmp_path, monkeypatch, preview_requested=False)
    with pytest.raises(TerminalStop, match="after_success_ack_fence_delete_before_evidence_cas"):
        controller._finalize_live_start(
            session_root=prepared.run_root,
            fault_hook=_stop_at(
                LiveStartFaultPoint.AFTER_SUCCESS_ACK_FENCE_DELETE_BEFORE_EVIDENCE_CAS
            ),
        )
    interrupted = session.load_live_start_session(prepared.run_root)
    assert interrupted.terminal_status == "LIVE_AND_MATCHED"
    assert interrupted.terminal_retirement["stage"] == "PREPARED"
    acknowledgement = interrupted.attempt_acknowledgement
    fence = Path(acknowledgement["retention_fence_path"])
    owner = Path(acknowledgement["target_owner_journal_path"])
    admission = Path(interrupted.result_intent["runtime_admission_path"])
    assert not fence.exists()
    assert admission.exists()
    owner_bytes = owner.read_bytes()
    result_bytes = _result_pair(prepared.run_root)

    def no_reapply(**_kwargs):
        raise AssertionError("terminal resume attempted a new apply")

    monkeypatch.setattr(published_apply, "_apply_and_match_published", no_reapply)
    with pytest.raises(TerminalStop, match="after_admission_release_authorized_before_runtime_admission_unlink"):
        controller._finalize_live_start(
            session_root=prepared.run_root, resume_intake=True,
            fault_hook=_stop_at(
                LiveStartFaultPoint.AFTER_ADMISSION_RELEASE_AUTHORIZED_BEFORE_RUNTIME_ADMISSION_UNLINK
            ),
        )
    release_authorized = session.load_live_start_session(prepared.run_root)
    assert release_authorized.terminal_retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"
    assert admission.exists()
    assert release_authorized.result_intent == interrupted.result_intent
    assert _result_pair(prepared.run_root) == result_bytes

    result = controller.resume_live_start(session_root=prepared.run_root)
    completed = session.load_live_start_session(prepared.run_root)
    assert result.status == "LIVE_AND_MATCHED"
    assert completed.result_intent == interrupted.result_intent
    assert completed.attempt_acknowledgement == acknowledgement
    assert _result_pair(prepared.run_root) == result_bytes
    assert owner.read_bytes() == owner_bytes
    assert not admission.exists()


def test_nonowning_journal_delete_hook_precedes_stage_cas_and_resumes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.test_apply_and_match_published import (
        _composite,
        _install_identical_runtime,
        _lease_published_capabilities,
        _prepare_pipeline,
        _terminalize_success,
    )

    prepared = _prepare_pipeline(tmp_path, monkeypatch)
    _install_identical_runtime(prepared, tmp_path / "preinstall")
    with pytest.raises(TerminalStop, match="after_success_ack_journal_delete_before_stage_cas"):
        with _lease_published_capabilities(prepared) as capabilities:
            with _composite(
                published_apply, capabilities, apply_attempt_id="b" * 32,
                fault_hook=_stop_at(
                    LiveStartFaultPoint.AFTER_SUCCESS_ACK_JOURNAL_DELETE_BEFORE_STAGE_CAS
                ),
            ) as held:
                evidence = held.acknowledgement_evidence
                assert evidence.journal_owns_target is False
                historical = held.result
                owner_bytes = evidence.target_owner_journal_path.read_bytes()
                terminal = _terminalize_success(
                    session_lease=capabilities.session_lease, held=held
                )
                result_bytes = _result_pair(prepared.session_root)
                held.acknowledge_after_terminal(
                    session_lease=capabilities.session_lease,
                    expected_terminal_session=terminal,
                )
    interrupted = session.load_live_start_session(prepared.session_root)
    assert interrupted.terminal_retirement["stage"] == "PREPARED"
    assert not evidence.journal_path.exists()
    assert evidence.retention_fence_path.exists()
    recovered = published_apply.recover_apply_attempt(session_root=prepared.session_root)
    assert recovered == historical
    assert _result_pair(prepared.session_root) == result_bytes
    assert evidence.target_owner_journal_path.read_bytes() == owner_bytes
    assert not evidence.retention_fence_path.exists()
    assert not evidence.runtime_admission_path.exists()
