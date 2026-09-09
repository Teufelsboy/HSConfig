from __future__ import annotations

import json
from pathlib import Path

from hsconfig import live_start_session as session
from hsconfig.apply_invocation import load_apply_invocation
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.operator_profile import derive_deck_output_binding, operator_profile_path
from hsconfig.runtime_live_admission import load_runtime_live_attempt_admission
from tests.test_codex_first_live_e2e import _local_state, _prepare_approved
from tests.test_configure_prepublication_apply import _file_fingerprint, _physical_tree
from tests.test_controller_output_hard_kills import (
    _expected_apply_entry_counts,
    _frozen_identity,
    _output_hard_kill_worker,
    _public_resume_worker,
    _spawn_and_join,
)


def test_nonterminal_observation_hook_is_before_prepare_cas_and_hard_kill_is_read_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A recovery observation can be interrupted before its consuming Session CAS."""
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "approved", monkeypatch)
    output_root = derive_deck_output_binding(
        fixture.profile, fixture.deck_name
    ).output_root
    handoff_oracle = tmp_path / "handoff-oracle.json"
    _spawn_and_join(
        target=_output_hard_kill_worker,
        args=(
            str(prepared.run_root),
            LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_UNLINK.value,
            str(handoff_oracle),
        ),
        expected_exitcode=93,
        timeout_seconds=360,
    )
    assert json.loads(handoff_oracle.read_bytes())["apply_entry_counts"] == (
        _expected_apply_entry_counts(fresh=1, install_prepare=1, attempt_prepare=1)
    )
    interrupted = session.load_live_start_session(prepared.run_root)
    assert interrupted.phase is session.LiveStartPhase.APPLY_STARTED
    assert interrupted.pending_transition is None
    assert interrupted.apply_recovery is None
    assert interrupted.result_intent is None
    assert interrupted.apply_invocation_sha256 is not None
    assert interrupted.runtime_admission_binding is not None
    physical_admission = load_runtime_live_attempt_admission()
    assert physical_admission is not None
    attempt_id = physical_admission.apply_attempt_id
    assert interrupted.runtime_layout_bootstrap["apply_attempt_id"] == attempt_id
    admission_path = Path(interrupted.runtime_admission_binding["admission_path"])
    invocation_path = prepared.run_root / "receipts/apply_invocation.json"
    session_path = prepared.run_root / "session.json"
    before = {
        "session": _file_fingerprint(session_path),
        "runtime": _physical_tree(fixture.profile.runtime_root),
        "output": _physical_tree(output_root),
        "profile": _file_fingerprint(operator_profile_path()),
        "invocation": _file_fingerprint(invocation_path),
        "admission": _file_fingerprint(admission_path),
    }
    invocation = load_apply_invocation(invocation_path)
    assert invocation.apply_attempt_id == attempt_id
    assert invocation.content_sha256 == interrupted.apply_invocation_sha256
    assert before["invocation"] is not None
    assert (
        before["invocation"][2]
        == interrupted.artifact_bindings["receipts/apply_invocation.json"]
    )
    binding = interrupted.runtime_admission_binding
    assert before["admission"] is not None
    assert (before["admission"][0], before["admission"][2]) == (
        tuple(binding["admission_identity"]),
        binding["admission_sha256"],
    )

    observation_oracle = tmp_path / "observation-oracle.json"
    _spawn_and_join(
        target=_output_hard_kill_worker,
        args=(
            str(prepared.run_root),
            LiveStartFaultPoint.AFTER_NONTERMINAL_OBSERVATION_BEFORE_PREPARE_CAS.value,
            str(observation_oracle),
        ),
        expected_exitcode=93,
        timeout_seconds=360,
    )
    assert json.loads(observation_oracle.read_bytes())["apply_entry_counts"] == (
        _expected_apply_entry_counts(recovery=1)
    )
    assert {
        "session": _file_fingerprint(session_path),
        "runtime": _physical_tree(fixture.profile.runtime_root),
        "output": _physical_tree(output_root),
        "profile": _file_fingerprint(operator_profile_path()),
        "invocation": _file_fingerprint(invocation_path),
        "admission": _file_fingerprint(admission_path),
    } == before

    resume_oracle = tmp_path / "resume-oracle.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(resume_oracle)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    resumed = json.loads(resume_oracle.read_bytes())
    assert resumed["status"] == "FAILED_PRESERVED"
    assert resumed["apply_entry_counts"] == _expected_apply_entry_counts(recovery=1)
    terminal = session.load_live_start_session(prepared.run_root)
    assert terminal.terminal_status == "FAILED_PRESERVED"
    assert terminal.pending_transition is None
    assert _frozen_identity(terminal) == _frozen_identity(interrupted)
    assert terminal.result_intent["apply_attempt_id"] == attempt_id
    assert terminal.result_intent["physical_disposition"] == "NOT_COMMITTED"
    assert terminal.apply_recovery is None
    assert terminal.apply_invocation_sha256 == interrupted.apply_invocation_sha256
    assert tuple(prepared.run_root.rglob("*apply_invocation*.json")) == (
        invocation_path,
    )
    assert _file_fingerprint(invocation_path) == before["invocation"]
    assert _physical_tree(fixture.profile.runtime_root) == before["runtime"]
    assert _physical_tree(output_root) == before["output"]
    assert _file_fingerprint(operator_profile_path()) == before["profile"]
    assert not admission_path.exists()

    final_session_tree = _physical_tree(prepared.run_root)
    replay_oracle = tmp_path / "replay-oracle.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(replay_oracle)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    replayed = json.loads(replay_oracle.read_bytes())
    assert replayed["status"] == "FAILED_PRESERVED"
    assert replayed.pop("apply_entry_counts") == _expected_apply_entry_counts()
    first_public_result = dict(resumed)
    first_public_result.pop("apply_entry_counts")
    assert replayed == first_public_result
    assert _physical_tree(prepared.run_root) == final_session_tree
    assert _physical_tree(fixture.profile.runtime_root) == before["runtime"]
    assert _physical_tree(output_root) == before["output"]
