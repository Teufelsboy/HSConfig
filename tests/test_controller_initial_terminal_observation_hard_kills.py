from __future__ import annotations

from collections.abc import Mapping
import json
import os
from pathlib import Path
import sys
from typing import Any

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig.apply_invocation import load_apply_invocation
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.operator_profile import derive_deck_output_binding, operator_profile_path
from hsconfig.package_io import path_identity
from hsconfig.runtime_live_admission import load_runtime_live_attempt_admission
from tests.test_codex_first_live_e2e import _local_state, _prepare_approved
from tests.test_configure_prepublication_apply import (
    _file_fingerprint,
    _persist_worker_oracle,
    _physical_tree,
)
from tests.test_controller_candidate_parity_hard_kills import (
    _publication_tree_with_held_lock,
)
from tests.test_controller_failure_hook_wiring import (
    _fail_before_candidate_and_kill_selection_worker,
)
from tests.test_controller_output_hard_kills import (
    _expected_apply_entry_counts,
    _frozen_identity,
    _public_resume_worker,
    _spawn_and_join,
    _start_apply_entry_observer,
)
from tests.test_controller_prior_owner_action_chain import _result_pair
from tests.test_controller_runtime_action_chain import (
    _assert_tree_after_exit,
    _runtime_tree,
)
from tests.test_controller_runtime_hard_kills import _runtime_hard_kill_worker


_FIRST_INSTALL = "first_install"
_TERMINAL_RESOLUTION = "terminal_resolution"
_FIRST_INSTALL_HOOK = (
    LiveStartFaultPoint.AFTER_FIRST_INSTALL_OBSERVATION_BEFORE_PREPARE_CAS
)
_TERMINAL_RESOLUTION_HOOK = (
    LiveStartFaultPoint.AFTER_TERMINAL_RESOLUTION_OBSERVATION_BEFORE_PREPARE_CAS
)
_INITIAL_JOURNAL_BOUND_HOOK = (
    LiveStartFaultPoint.AFTER_RUNTIME_CANDIDATE_JOURNAL_BOUND_BEFORE_CANDIDATE_CREATE
)
_RESULT_NAMES = ("summary.json", "summary.md")
_HARD_EXIT = 93


def _raw_held_session(session_root: Path) -> session.LiveStartSession:
    path = session_root / "session.json"
    return session._load_session_bytes(
        path.read_bytes(),
        session_identity=path_identity(path),
    )


def _result_fingerprints(
    session_root: Path,
) -> dict[str, tuple[tuple[int, int, int], int, str] | None]:
    return {
        name: _file_fingerprint(session_root / "result" / name)
        for name in _RESULT_NAMES
    }


def _observation_snapshot(
    *,
    session_root: Path,
    output_root: Path,
) -> dict[str, object]:
    current = _raw_held_session(session_root)
    layout = current.runtime_layout_bootstrap
    admission = current.runtime_admission_binding
    assert isinstance(layout, Mapping)
    assert isinstance(admission, Mapping)
    runtime_root = Path(str(layout["runtime_root"]))
    admission_path = Path(str(admission["admission_path"]))
    invocation_path = session_root / "receipts" / "apply_invocation.json"
    return {
        "session": current.to_value(),
        "session_fingerprint": _file_fingerprint(session_root / "session.json"),
        "runtime_tree": _runtime_tree(
            runtime_root,
            held_lock_path=runtime_root / ".hsconfig" / "apply.lock",
        ),
        "output_tree": _publication_tree_with_held_lock(output_root),
        "profile_fingerprint": _file_fingerprint(operator_profile_path()),
        "invocation_fingerprint": _file_fingerprint(invocation_path),
        "admission_fingerprint": _file_fingerprint(admission_path),
        "result_fingerprints": _result_fingerprints(session_root),
    }


def _observation_hard_kill_worker(
    session_root_text: str,
    output_root_text: str,
    observation_family: str,
    fault_value: str,
    oracle_path_text: str,
) -> None:
    session_root = Path(session_root_text)
    output_root = Path(output_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    selected_hook = LiveStartFaultPoint(fault_value)
    counts, previous_profile = _start_apply_entry_observer()
    apply_observer = sys.getprofile()
    assert apply_observer is not None
    observation_calls: list[str] = []
    before: dict[str, object] | None = None

    def observe(frame: Any, event: str, arg: Any) -> None:
        nonlocal before
        apply_observer(frame, event, arg)
        if (
            event != "call"
            or frame.f_code is not session._execute_runtime_observation.__code__
        ):
            return
        family = frame.f_locals.get("observation_family")
        assert isinstance(family, str)
        observation_calls.append(family)
        if family != observation_family:
            return
        assert before is None
        before = _observation_snapshot(
            session_root=session_root,
            output_root=output_root,
        )

    def hard_kill(point: LiveStartFaultPoint) -> None:
        if point is not selected_hook:
            return
        assert before is not None
        assert observation_calls.count(observation_family) == 1
        after = _observation_snapshot(
            session_root=session_root,
            output_root=output_root,
        )
        assert after == before
        _persist_worker_oracle(
            Path(oracle_path_text),
            {
                "observation_family": observation_family,
                "fault_value": point.value,
                "observation_calls": observation_calls,
                "apply_entry_counts": counts,
                "snapshot": before,
            },
        )
        os._exit(_HARD_EXIT)

    sys.setprofile(observe)
    try:
        controller._finalize_live_start(
            session_root=session_root,
            resume_intake=True,
            fault_hook=hard_kill,
        )
    finally:
        sys.setprofile(previous_profile)
    os._exit(_HARD_EXIT + 1)


def _json_fingerprint(value: object) -> tuple[tuple[int, int, int], int, str]:
    assert isinstance(value, list)
    assert len(value) == 3
    identity, size, digest = value
    assert isinstance(identity, list)
    assert len(identity) == 3
    assert type(size) is int
    assert isinstance(digest, str)
    return tuple(identity), size, digest


def _assert_optional_fingerprint(path: Path, value: object) -> None:
    if value is None:
        assert not path.exists()
    else:
        assert _file_fingerprint(path) == _json_fingerprint(value)


def _assert_snapshot_after_exit(
    *,
    session_root: Path,
    output_root: Path,
    snapshot: Mapping[str, Any],
) -> session.LiveStartSession:
    current = session.load_live_start_session(
        session_root,
        local_app_data_root=session_root.parents[2],
    )
    assert current.to_value() == snapshot["session"]
    _assert_optional_fingerprint(
        session_root / "session.json",
        snapshot["session_fingerprint"],
    )
    layout = current.runtime_layout_bootstrap
    admission = current.runtime_admission_binding
    assert isinstance(layout, Mapping)
    assert isinstance(admission, Mapping)
    runtime_root = Path(str(layout["runtime_root"]))
    _assert_tree_after_exit(
        runtime_root=runtime_root,
        snapshot={"tree": snapshot["runtime_tree"]},
    )
    assert _runtime_tree(output_root, held_lock_path=None) == snapshot["output_tree"]
    _assert_optional_fingerprint(
        operator_profile_path(),
        snapshot["profile_fingerprint"],
    )
    _assert_optional_fingerprint(
        session_root / "receipts" / "apply_invocation.json",
        snapshot["invocation_fingerprint"],
    )
    _assert_optional_fingerprint(
        Path(str(admission["admission_path"])),
        snapshot["admission_fingerprint"],
    )
    result_fingerprints = snapshot["result_fingerprints"]
    assert isinstance(result_fingerprints, Mapping)
    for name in _RESULT_NAMES:
        _assert_optional_fingerprint(
            session_root / "result" / name,
            result_fingerprints[name],
        )
    return current


def _canonical_complete_runtime_paths(
    current: session.LiveStartSession,
) -> tuple[set[str], Mapping[str, Any]]:
    layout = current.runtime_layout_bootstrap
    assert isinstance(layout, Mapping)
    assert layout["stage"] == "COMPLETE"
    assert layout["next_directory_index"] == layout["directory_count"] == 7
    rows = layout["directories"]
    assert tuple(row["role"] for row in rows) == session.RUNTIME_LAYOUT_DIRECTORY_ROLES
    runtime_root = Path(str(layout["runtime_root"]))
    expected_paths = {".", ".hsconfig", ".hsconfig/apply.lock"}
    expected_paths.update(
        Path(str(row["path"])).relative_to(runtime_root).as_posix() for row in rows
    )
    return expected_paths, layout


def _assert_canonical_empty_complete_runtime(
    *,
    current: session.LiveStartSession,
    runtime_tree: Mapping[str, Any],
) -> None:
    expected_paths, layout = _canonical_complete_runtime_paths(current)
    rows = layout["directories"]
    runtime_root = Path(str(layout["runtime_root"]))
    assert set(runtime_tree) == expected_paths
    assert runtime_tree["."] == {
        "kind": "directory",
        "identity": list(layout["runtime_root_identity"]),
    }
    transactions = rows[session.RUNTIME_LAYOUT_DIRECTORY_ROLES.index("transactions")]
    assert runtime_tree[".hsconfig"] == {
        "kind": "directory",
        "identity": list(transactions["expected_parent_identity"]),
    }
    assert runtime_tree[".hsconfig/apply.lock"]["kind"] == "file"
    assert runtime_tree[".hsconfig/apply.lock"]["size"] == 0
    assert runtime_tree[".hsconfig/apply.lock"]["sha256"] is None
    for row in rows:
        relative = Path(str(row["path"])).relative_to(runtime_root).as_posix()
        assert runtime_tree[relative] == {
            "kind": "directory",
            "identity": list(row["successor_identity"]),
        }


def _assert_preexisting_session_authority_preserved(
    *,
    predecessor_value: Mapping[str, Any],
    terminal: session.LiveStartSession,
) -> None:
    terminal_value = terminal.to_value()
    for field in (
        "run_id",
        "deck_name",
        "deck_code_sha256",
        "preview_requested",
        "candidate_revision",
        "revisions_used",
        "input_snapshot_manifest_sha256",
        "apply_invocation_sha256",
        "runtime_admission_binding",
        "runtime_layout_bootstrap",
        "output_operation_admission_binding",
        "output_child_binding",
        "publication_binding",
    ):
        assert terminal_value[field] == predecessor_value[field]
    for logical_path, digest in predecessor_value["artifact_bindings"].items():
        assert terminal_value["artifact_bindings"][logical_path] == digest


def test_first_install_observation_is_read_only_before_prepare_and_resumes_not_committed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "first-install", monkeypatch)
    runtime_root = fixture.profile.runtime_root
    output_root = derive_deck_output_binding(
        fixture.profile,
        fixture.deck_name,
    ).output_root
    approved = session.load_live_start_session(prepared.run_root)
    approved_frozen = _frozen_identity(approved)

    marker = tmp_path / "first-install-observation.json"
    _spawn_and_join(
        target=_observation_hard_kill_worker,
        args=(
            str(prepared.run_root),
            str(output_root),
            _FIRST_INSTALL,
            _FIRST_INSTALL_HOOK.value,
            str(marker),
        ),
        expected_exitcode=_HARD_EXIT,
        timeout_seconds=360,
    )
    oracle = json.loads(marker.read_bytes())
    assert oracle["observation_family"] == _FIRST_INSTALL
    assert oracle["fault_value"] == _FIRST_INSTALL_HOOK.value
    assert oracle["observation_calls"] == [_FIRST_INSTALL]
    assert oracle["apply_entry_counts"] == _expected_apply_entry_counts(
        fresh=1,
        install_prepare=1,
        attempt_prepare=1,
    )
    snapshot = oracle["snapshot"]
    current = _assert_snapshot_after_exit(
        session_root=prepared.run_root,
        output_root=output_root,
        snapshot=snapshot,
    )
    assert current.phase is session.LiveStartPhase.APPLY_STARTED
    assert current.pending_transition is None
    assert current.apply_recovery is None
    assert current.result_intent is None
    assert current.terminal_status is None
    assert _frozen_identity(current) == approved_frozen
    invocation_path = prepared.run_root / "receipts" / "apply_invocation.json"
    invocation = load_apply_invocation(invocation_path)
    assert invocation.content_sha256 == current.apply_invocation_sha256
    attempt_id = invocation.apply_attempt_id
    assert current.runtime_layout_bootstrap["apply_attempt_id"] == attempt_id
    admission = load_runtime_live_attempt_admission()
    assert admission is not None
    assert admission.apply_attempt_id == attempt_id
    _assert_canonical_empty_complete_runtime(
        current=current,
        runtime_tree=snapshot["runtime_tree"],
    )
    assert not tuple((runtime_root / ".hsconfig" / "transactions").glob("*.json"))
    assert not tuple((runtime_root / ".hsconfig" / "attempt-retention").iterdir())
    assert not tuple((runtime_root / ".hsconfig" / "staging").iterdir())
    runtime_before = _physical_tree(runtime_root)
    output_before = _physical_tree(output_root)
    profile_before = _file_fingerprint(operator_profile_path())
    invocation_before = _file_fingerprint(invocation_path)

    resume_marker = tmp_path / "first-install-public-resume.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(resume_marker)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    resumed = json.loads(resume_marker.read_bytes())
    assert resumed["status"] == "FAILED_PRESERVED"
    assert resumed["apply_entry_counts"] == _expected_apply_entry_counts(recovery=1)
    terminal = session.load_live_start_session(prepared.run_root)
    assert terminal.content_sha256 == resumed["session_sha256"]
    assert terminal.terminal_status == "FAILED_PRESERVED"
    assert terminal.apply_recovery is None
    assert terminal.closed_apply_recovery_commitment is None
    assert terminal.attempt_acknowledgement is None
    assert terminal.result_intent["apply_attempt_id"] == attempt_id
    assert terminal.result_intent["raw_apply_status"] is None
    assert terminal.result_intent["physical_disposition"] == "NOT_COMMITTED"
    assert terminal.result_intent["runtime_match_status"] == "not_run"
    assert terminal.result_intent["error_code"] == "apply_not_committed"
    for prefix in (
        "retained_attempt_record",
        "retained_journal",
        "retained_target_owner_journal",
    ):
        for suffix in ("path", "identity", "sha256"):
            assert terminal.result_intent[f"{prefix}_{suffix}"] is None
    assert terminal.terminal_retirement["operation"] == "release_not_committed"
    assert terminal.terminal_retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"
    _assert_preexisting_session_authority_preserved(
        predecessor_value=snapshot["session"],
        terminal=terminal,
    )
    assert load_runtime_live_attempt_admission() is None
    assert _physical_tree(runtime_root) == runtime_before
    assert _physical_tree(output_root) == output_before
    assert _file_fingerprint(operator_profile_path()) == profile_before
    assert _file_fingerprint(invocation_path) == invocation_before

    terminal_snapshot = {
        "session": (prepared.run_root / "session.json").read_bytes(),
        "result": _result_pair(prepared.run_root),
        "run_tree": _physical_tree(prepared.run_root),
        "runtime": _physical_tree(runtime_root),
        "output": _physical_tree(output_root),
        "profile": _file_fingerprint(operator_profile_path()),
        "invocation": _file_fingerprint(invocation_path),
    }
    replay_marker = tmp_path / "first-install-public-replay.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(replay_marker)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    replayed = json.loads(replay_marker.read_bytes())
    assert replayed.pop("apply_entry_counts") == _expected_apply_entry_counts()
    resumed_without_counts = dict(resumed)
    resumed_without_counts.pop("apply_entry_counts")
    assert replayed == resumed_without_counts
    assert terminal_snapshot == {
        "session": (prepared.run_root / "session.json").read_bytes(),
        "result": _result_pair(prepared.run_root),
        "run_tree": _physical_tree(prepared.run_root),
        "runtime": _physical_tree(runtime_root),
        "output": _physical_tree(output_root),
        "profile": _file_fingerprint(operator_profile_path()),
        "invocation": _file_fingerprint(invocation_path),
    }


def test_terminal_resolution_observation_is_read_only_before_prepare_and_cleans_no_tree_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(
        tmp_path / "terminal-resolution",
        monkeypatch,
    )
    runtime_root = fixture.profile.runtime_root
    output_root = derive_deck_output_binding(
        fixture.profile,
        fixture.deck_name,
    ).output_root

    initial_marker = tmp_path / "journal-bound-no-candidate.json"
    _spawn_and_join(
        target=_runtime_hard_kill_worker,
        args=(
            str(prepared.run_root),
            _INITIAL_JOURNAL_BOUND_HOOK.value,
            1,
            str(initial_marker),
        ),
        expected_exitcode=_HARD_EXIT,
        timeout_seconds=360,
    )
    initial_oracle = json.loads(initial_marker.read_bytes())
    assert initial_oracle["fault_value"] == _INITIAL_JOURNAL_BOUND_HOOK.value
    assert initial_oracle["occurrence"] == 1
    assert initial_oracle["apply_entry_counts"] == _expected_apply_entry_counts(
        fresh=1,
        install_prepare=1,
        attempt_prepare=1,
    )
    initial = session.load_live_start_session(prepared.run_root)
    initial_recovery = initial.apply_recovery
    assert isinstance(initial_recovery, Mapping)
    assert initial_recovery["expected_action"] == "bind_created_candidate"
    assert initial_recovery["install_route"] == "new_target"
    assert initial_recovery["successor_candidate_identity"] is None
    attempt_id = str(initial_recovery["apply_attempt_id"])
    journal_path = Path(str(initial_recovery["successor_journal_path"]))
    fence_path = Path(str(initial_recovery["successor_attempt_record_path"]))
    candidate_path = Path(str(initial_recovery["candidate_path"]))
    assert journal_path.is_file()
    assert fence_path.is_file()
    assert not candidate_path.exists()
    runtime_before_selection = _physical_tree(runtime_root)
    journal_relative = journal_path.relative_to(runtime_root).as_posix()
    fence_relative = fence_path.relative_to(runtime_root).as_posix()
    expected_runtime_paths, _layout = _canonical_complete_runtime_paths(initial)
    assert set(runtime_before_selection) == expected_runtime_paths | {
        journal_relative,
        fence_relative,
    }
    journal_row = runtime_before_selection[journal_relative]
    fence_row = runtime_before_selection[fence_relative]
    assert journal_row[0] == fence_row[0] == "file"

    selection_marker = tmp_path / "terminal-classification-selected.json"
    _spawn_and_join(
        target=_fail_before_candidate_and_kill_selection_worker,
        args=(str(prepared.run_root), str(selection_marker)),
        expected_exitcode=_HARD_EXIT,
        timeout_seconds=360,
    )
    selection_oracle = json.loads(selection_marker.read_bytes())
    assert selection_oracle["failure_count"] == 1
    assert selection_oracle["observation_count"] == 1
    assert selection_oracle["apply_entry_counts"] == _expected_apply_entry_counts(
        recovery=1
    )
    selected = session.load_live_start_session(prepared.run_root)
    assert (
        selected.to_value()["apply_recovery"] == selection_oracle["selected_recovery"]
    )
    assert selected.apply_recovery["expected_action"] == "observe_not_committed"
    assert _physical_tree(runtime_root) == runtime_before_selection
    selected_frozen = _frozen_identity(selected)
    selected_value = selected.to_value()
    selected_invocation = _file_fingerprint(
        prepared.run_root / "receipts" / "apply_invocation.json"
    )
    selected_admission_path = Path(
        str(selected.runtime_admission_binding["admission_path"])
    )
    selected_admission = _file_fingerprint(selected_admission_path)
    selected_profile = _file_fingerprint(operator_profile_path())
    selected_output = _physical_tree(output_root)

    observation_marker = tmp_path / "terminal-resolution-observation.json"
    _spawn_and_join(
        target=_observation_hard_kill_worker,
        args=(
            str(prepared.run_root),
            str(output_root),
            _TERMINAL_RESOLUTION,
            _TERMINAL_RESOLUTION_HOOK.value,
            str(observation_marker),
        ),
        expected_exitcode=_HARD_EXIT,
        timeout_seconds=360,
    )
    oracle = json.loads(observation_marker.read_bytes())
    assert oracle["observation_family"] == _TERMINAL_RESOLUTION
    assert oracle["fault_value"] == _TERMINAL_RESOLUTION_HOOK.value
    assert oracle["observation_calls"] == [_TERMINAL_RESOLUTION]
    assert oracle["apply_entry_counts"] == _expected_apply_entry_counts(recovery=1)
    snapshot = oracle["snapshot"]
    observed = _assert_snapshot_after_exit(
        session_root=prepared.run_root,
        output_root=output_root,
        snapshot=snapshot,
    )
    assert observed.terminal_status == "FAILED_PRESERVED"
    assert observed.pending_transition is None
    assert observed.apply_recovery is None
    assert isinstance(observed.closed_apply_recovery_commitment, Mapping)
    assert observed.terminal_retirement is None
    assert observed.attempt_acknowledgement is None
    assert observed.result_intent["apply_attempt_id"] == attempt_id
    assert observed.result_intent["physical_disposition"] == "NOT_COMMITTED"
    assert observed.result_intent["runtime_match_status"] == "not_run"
    assert _frozen_identity(observed) == selected_frozen
    observed_value = observed.to_value()
    for field in (
        "apply_invocation_sha256",
        "runtime_admission_binding",
        "runtime_layout_bootstrap",
        "output_operation_admission_binding",
        "output_child_binding",
        "publication_binding",
    ):
        assert observed_value[field] == selected_value[field]
    assert _physical_tree(runtime_root) == runtime_before_selection
    assert journal_path.is_file()
    assert fence_path.is_file()
    assert not candidate_path.exists()
    assert (
        _file_fingerprint(prepared.run_root / "receipts" / "apply_invocation.json")
        == selected_invocation
    )
    assert _file_fingerprint(operator_profile_path()) == selected_profile
    assert _physical_tree(output_root) == selected_output
    assert _file_fingerprint(selected_admission_path) == selected_admission
    observed_results = _result_pair(prepared.run_root)

    completion_marker = tmp_path / "terminal-resolution-public-completion.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(completion_marker)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    completed_result = json.loads(completion_marker.read_bytes())
    assert completed_result["status"] == "FAILED_PRESERVED"
    assert completed_result["apply_entry_counts"] == _expected_apply_entry_counts(
        recovery=1
    )
    terminal = session.load_live_start_session(prepared.run_root)
    assert terminal.content_sha256 == completed_result["session_sha256"]
    assert terminal.terminal_status == "FAILED_PRESERVED"
    assert terminal.apply_recovery is None
    assert terminal.closed_apply_recovery_commitment is None
    assert terminal.attempt_acknowledgement is None
    assert terminal.result_intent == observed.result_intent
    assert terminal.terminal_retirement["operation"] == "release_resolved_terminal"
    assert terminal.terminal_retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"
    resolution = terminal.terminal_retirement["terminal_resolution_evidence"]
    assert resolution["resolved_physical_disposition"] == "NOT_COMMITTED"
    assert resolution["owner_retirement"] is None
    assert resolution["external_file_action"] is None
    _assert_preexisting_session_authority_preserved(
        predecessor_value=snapshot["session"],
        terminal=terminal,
    )
    assert load_runtime_live_attempt_admission() is None
    assert not journal_path.exists()
    assert not fence_path.exists()
    assert not candidate_path.exists()
    expected_runtime = dict(runtime_before_selection)
    del expected_runtime[journal_path.relative_to(runtime_root).as_posix()]
    del expected_runtime[fence_path.relative_to(runtime_root).as_posix()]
    assert _physical_tree(runtime_root) == expected_runtime
    assert _result_pair(prepared.run_root) == observed_results
    assert (
        _file_fingerprint(prepared.run_root / "receipts" / "apply_invocation.json")
        == selected_invocation
    )
    assert _file_fingerprint(operator_profile_path()) == selected_profile
    assert _physical_tree(output_root) == selected_output

    terminal_snapshot = {
        "session": (prepared.run_root / "session.json").read_bytes(),
        "result": _result_pair(prepared.run_root),
        "run_tree": _physical_tree(prepared.run_root),
        "runtime": _physical_tree(runtime_root),
        "output": _physical_tree(output_root),
        "profile": _file_fingerprint(operator_profile_path()),
        "invocation": _file_fingerprint(
            prepared.run_root / "receipts" / "apply_invocation.json"
        ),
    }
    replay_marker = tmp_path / "terminal-resolution-public-replay.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(replay_marker)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    replayed = json.loads(replay_marker.read_bytes())
    assert replayed.pop("apply_entry_counts") == _expected_apply_entry_counts()
    completion_without_counts = dict(completed_result)
    completion_without_counts.pop("apply_entry_counts")
    assert replayed == completion_without_counts
    assert terminal_snapshot == {
        "session": (prepared.run_root / "session.json").read_bytes(),
        "result": _result_pair(prepared.run_root),
        "run_tree": _physical_tree(prepared.run_root),
        "runtime": _physical_tree(runtime_root),
        "output": _physical_tree(output_root),
        "profile": _file_fingerprint(operator_profile_path()),
        "invocation": _file_fingerprint(
            prepared.run_root / "receipts" / "apply_invocation.json"
        ),
    }
