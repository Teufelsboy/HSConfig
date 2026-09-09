from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.operator_profile import derive_deck_output_binding, operator_profile_path
from hsconfig.package_io import path_identity
from hsconfig.runtime_transaction_journal import load_runtime_transaction_journals
from tests.test_codex_first_live_e2e import _local_state, _prepare_approved
from tests.test_configure_prepublication_apply import (
    _file_fingerprint,
    _persist_worker_oracle,
    _physical_tree,
)
from tests.test_controller_output_hard_kills import (
    _expected_apply_entry_counts,
    _frozen_identity,
    _public_resume_worker,
    _spawn_and_join,
    _start_apply_entry_observer,
)
from tests.test_controller_runtime_hard_kills import (
    _runtime_hard_kill_worker,
    _tree_projection,
)


def _fail_before_candidate_and_kill_selection_worker(
    session_root_text: str,
    oracle_path_text: str,
) -> None:
    session_root = Path(session_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    predecessor = session.load_live_start_session(session_root)
    recovery_before = predecessor.to_value()["apply_recovery"]
    runtime_root = Path(recovery_before["runtime_root"])
    lock_path = runtime_root / ".hsconfig/apply.lock"
    counts, previous_profile = _start_apply_entry_observer()
    failure_count = 0
    observation_count = 0
    physical_before = None

    def observe_held_session() -> session.LiveStartSession:
        session_path = session_root / "session.json"
        return session._load_session_bytes(
            session_path.read_bytes(),
            session_identity=path_identity(session_path),
        )

    def fail_then_kill(point: LiveStartFaultPoint) -> None:
        nonlocal failure_count, observation_count, physical_before
        if (
            point
            is LiveStartFaultPoint.AFTER_AUTHORIZATION_CONSUMED_BEFORE_PHYSICAL_CALLBACK
        ):
            current = observe_held_session()
            if current.apply_recovery["expected_action"] != "bind_created_candidate":
                return
            assert failure_count == 0
            assert current.canonical_json == predecessor.canonical_json
            assert current.session_identity == predecessor.session_identity
            assert not Path(recovery_before["candidate_path"]).exists()
            physical_before = _tree_projection(runtime_root, held_lock_path=lock_path)
            failure_count += 1
            raise OSError("test-only candidate creation failure after consumption")
        if point is (
            LiveStartFaultPoint.AFTER_TERMINAL_CLASSIFICATION_OBSERVATION_BEFORE_SELECTION_CAS
        ):
            assert failure_count == 1
            observation_count += 1
            assert observation_count == 1
            current = observe_held_session()
            assert current.canonical_json == predecessor.canonical_json
            assert current.session_identity == predecessor.session_identity
            assert (
                _tree_projection(runtime_root, held_lock_path=lock_path)
                == physical_before
            )
        if point is LiveStartFaultPoint.AFTER_TERMINAL_CLASSIFICATION_SELECTION_CAS:
            assert failure_count == observation_count == 1
            current = observe_held_session()
            selected = current.to_value()["apply_recovery"]
            assert selected["expected_action"] == "observe_not_committed"
            assert selected["action_index"] == recovery_before["action_index"] + 1
            assert selected["recovery_stage"] == "ACTIVE"
            changed_fields = {"expected_action", "action_index", "content_sha256"}
            assert {
                key: value
                for key, value in selected.items()
                if key not in changed_fields
            } == {
                key: value
                for key, value in recovery_before.items()
                if key not in changed_fields
            }
            assert current.result_intent is None
            assert current.terminal_status is None
            assert (
                _tree_projection(runtime_root, held_lock_path=lock_path)
                == physical_before
            )
            _persist_worker_oracle(
                Path(oracle_path_text),
                {
                    "failure_count": failure_count,
                    "observation_count": observation_count,
                    "apply_entry_counts": counts,
                    "selected_recovery": selected,
                },
            )
            os._exit(93)

    try:
        controller._finalize_live_start(
            session_root=session_root,
            resume_intake=True,
            fault_hook=fail_then_kill,
        )
    finally:
        sys.setprofile(previous_profile)


def test_consumed_runtime_failure_hook_selects_once_and_recovers_without_candidate_creation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "approved", monkeypatch)
    initial_oracle = tmp_path / "candidate-planned-oracle.json"
    _spawn_and_join(
        target=_runtime_hard_kill_worker,
        args=(
            str(prepared.run_root),
            LiveStartFaultPoint.AFTER_RUNTIME_CANDIDATE_JOURNAL_BOUND_BEFORE_CANDIDATE_CREATE.value,
            1,
            str(initial_oracle),
        ),
        expected_exitcode=93,
        timeout_seconds=360,
    )
    initial = session.load_live_start_session(prepared.run_root)
    initial_observed = json.loads(initial_oracle.read_bytes())
    assert initial_observed["apply_entry_counts"] == (
        _expected_apply_entry_counts(fresh=1, install_prepare=1, attempt_prepare=1)
    )
    assert initial_observed["fault_value"] == (
        LiveStartFaultPoint.AFTER_RUNTIME_CANDIDATE_JOURNAL_BOUND_BEFORE_CANDIDATE_CREATE.value
    )
    assert initial_observed["occurrence"] == 1
    recovery = initial.apply_recovery
    assert recovery["expected_action"] == "bind_created_candidate"
    assert recovery["install_route"] == "new_target"
    assert recovery["successor_candidate_identity"] is None
    candidate_path = Path(recovery["candidate_path"])
    assert not candidate_path.exists()
    attempt_id = recovery["apply_attempt_id"]
    journal_path = Path(recovery["successor_journal_path"])
    fence_path = Path(recovery["successor_attempt_record_path"])
    assert journal_path.is_file() and fence_path.is_file()
    runtime_root = fixture.profile.runtime_root
    runtime_before = _physical_tree(runtime_root)
    output_root = derive_deck_output_binding(
        fixture.profile, fixture.deck_name
    ).output_root
    output_before = _physical_tree(output_root)
    profile_before = _file_fingerprint(operator_profile_path())
    assert profile_before is not None
    invocation_path = prepared.run_root / "receipts/apply_invocation.json"
    invocation_before = _file_fingerprint(invocation_path)
    assert invocation_before is not None
    admission_path = Path(initial.runtime_admission_binding["admission_path"])
    admission_before = _file_fingerprint(admission_path)
    assert admission_before is not None

    selected_oracle = tmp_path / "selected-oracle.json"
    _spawn_and_join(
        target=_fail_before_candidate_and_kill_selection_worker,
        args=(str(prepared.run_root), str(selected_oracle)),
        expected_exitcode=93,
        timeout_seconds=360,
    )
    selected = session.load_live_start_session(prepared.run_root)
    observed = json.loads(selected_oracle.read_bytes())
    assert observed["failure_count"] == observed["observation_count"] == 1
    assert observed["apply_entry_counts"] == _expected_apply_entry_counts(recovery=1)
    assert selected.to_value()["apply_recovery"] == observed["selected_recovery"]
    assert _frozen_identity(selected) == _frozen_identity(initial)
    assert _physical_tree(runtime_root) == runtime_before
    assert _physical_tree(output_root) == output_before
    assert _file_fingerprint(operator_profile_path()) == profile_before
    assert _file_fingerprint(invocation_path) == invocation_before
    assert _file_fingerprint(admission_path) == admission_before

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
    assert terminal.apply_recovery is None
    assert terminal.result_intent["apply_attempt_id"] == attempt_id
    assert terminal.result_intent["physical_disposition"] == "NOT_COMMITTED"
    assert terminal.result_intent["runtime_match_status"] == "not_run"
    assert terminal.attempt_acknowledgement is None
    assert terminal.terminal_retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"
    assert _frozen_identity(terminal) == _frozen_identity(initial)
    expected_runtime = dict(runtime_before)
    del expected_runtime[journal_path.relative_to(runtime_root).as_posix()]
    del expected_runtime[fence_path.relative_to(runtime_root).as_posix()]
    assert _physical_tree(runtime_root) == expected_runtime
    assert load_runtime_transaction_journals(runtime_root) == ()
    assert not candidate_path.exists()
    assert not admission_path.exists()
    assert tuple(prepared.run_root.rglob("*apply_invocation*.json")) == (
        invocation_path,
    )
    assert _file_fingerprint(invocation_path) == invocation_before
    assert _physical_tree(output_root) == output_before
    assert _file_fingerprint(operator_profile_path()) == profile_before

    final_session_tree = _physical_tree(prepared.run_root)
    replay_oracle = tmp_path / "replay-oracle.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(replay_oracle)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    replayed = json.loads(replay_oracle.read_bytes())
    assert replayed.pop("apply_entry_counts") == _expected_apply_entry_counts()
    first_public_result = dict(resumed)
    first_public_result.pop("apply_entry_counts")
    assert replayed == first_public_result
    assert _physical_tree(prepared.run_root) == final_session_tree
    assert _physical_tree(runtime_root) == expected_runtime
    assert _physical_tree(output_root) == output_before
