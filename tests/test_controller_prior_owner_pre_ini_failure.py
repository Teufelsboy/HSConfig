from __future__ import annotations

from collections.abc import Mapping
import json
import os
from pathlib import Path
import stat
import sys

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig import runtime_installer as runtime_apply
from hsconfig.apply_invocation import load_apply_invocation
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.operator_profile import derive_deck_output_binding, operator_profile_path
from hsconfig.package_io import path_identity
from hsconfig.runtime_live_admission import load_runtime_live_attempt_admission
from hsconfig.runtime_transaction_journal import (
    RuntimeTransactionPhase,
    load_runtime_transaction_journals,
    runtime_transaction_journal_path,
)
from tests.test_codex_first_live_e2e import _local_state
from tests.test_configure_prepublication_apply import (
    _file_fingerprint,
    _persist_worker_oracle,
    _physical_tree,
)
from tests.test_controller_output_hard_kills import (
    _expected_apply_entry_counts,
    _frozen_identity,
    _public_resume_worker,
    _sha256_bytes,
    _spawn_and_join,
    _start_apply_entry_observer,
)
from tests.test_controller_prior_owner_action_chain import (
    _capture_authority,
    _changed_paths,
    _is_exact_checkpoint,
    _result_pair,
    _seed_prior_owner,
)
from tests.test_controller_runtime_hard_kills import _tree_projection


_CONSUMED = LiveStartFaultPoint.AFTER_AUTHORIZATION_CONSUMED_BEFORE_PHYSICAL_CALLBACK
_OBSERVED = (
    LiveStartFaultPoint.AFTER_TERMINAL_CLASSIFICATION_OBSERVATION_BEFORE_SELECTION_CAS
)
_SELECTED = LiveStartFaultPoint.AFTER_TERMINAL_CLASSIFICATION_SELECTION_CAS
_HARD_EXIT = 93


def _raw_held_session(session_root: Path) -> session.LiveStartSession:
    session_path = session_root / "session.json"
    return session._load_session_bytes(
        session_path.read_bytes(),
        session_identity=path_identity(session_path),
    )


def _fail_prior_owner_pre_ini_and_kill_selection_worker(
    session_root_text: str,
    oracle_path_text: str,
) -> None:
    session_root = Path(session_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    counts, previous_profile = _start_apply_entry_observer()
    failure_count = 0
    observation_count = 0
    selection_count = 0
    failure_session: session.LiveStartSession | None = None
    failure_runtime: dict[str, dict[str, object]] | None = None
    lock_identity: tuple[int, int, int] | None = None

    def fault(point: LiveStartFaultPoint) -> None:
        nonlocal failure_count
        nonlocal observation_count
        nonlocal selection_count
        nonlocal failure_session
        nonlocal failure_runtime
        nonlocal lock_identity

        if point is _CONSUMED:
            current = _raw_held_session(session_root)
            if not _is_exact_checkpoint(current, checkpoint="prior_owner_bound"):
                return
            assert failure_count == observation_count == selection_count == 0
            recovery = current.apply_recovery
            assert isinstance(recovery, Mapping)
            external = recovery["external_file_action"]
            assert isinstance(external, Mapping)
            runtime_root = Path(str(recovery["runtime_root"]))
            lock_path = runtime_root / ".hsconfig/apply.lock"
            lock_status = lock_path.lstat()
            assert stat.S_ISREG(lock_status.st_mode)
            assert lock_status.st_nlink == 1
            assert lock_status.st_size == 0
            lock_identity = path_identity(lock_path)
            assert not Path(str(external["staging_path"])).exists()
            assert not Path(str(external["inner_temp_path"])).exists()
            failure_session = current
            failure_runtime = _tree_projection(
                runtime_root,
                held_lock_path=lock_path,
            )
            failure_count += 1
            raise OSError("test-only prior-owner failure before INI staging")

        if point is _OBSERVED:
            assert failure_count == 1
            assert observation_count == selection_count == 0
            assert failure_session is not None
            assert failure_runtime is not None
            current = _raw_held_session(session_root)
            recovery = current.apply_recovery
            assert isinstance(recovery, Mapping)
            runtime_root = Path(str(recovery["runtime_root"]))
            assert current.canonical_json == failure_session.canonical_json
            assert current.session_identity == failure_session.session_identity
            assert (
                _tree_projection(
                    runtime_root,
                    held_lock_path=runtime_root / ".hsconfig/apply.lock",
                )
                == failure_runtime
            )
            observation_count += 1
            return

        if point is not _SELECTED:
            return
        assert failure_count == observation_count == 1
        assert selection_count == 0
        assert failure_session is not None
        assert failure_runtime is not None
        assert lock_identity is not None
        current = _raw_held_session(session_root)
        before = failure_session.to_value()["apply_recovery"]
        selected = current.to_value()["apply_recovery"]
        assert isinstance(before, dict)
        assert isinstance(selected, dict)
        assert selected["expected_action"] == "observe_not_committed"
        assert selected["action_index"] == before["action_index"] + 1
        assert selected["recovery_stage"] == "ACTIVE"
        assert selected["stable_physical_disposition"] is None
        changed = {"expected_action", "action_index", "content_sha256"}
        assert {
            key: value for key, value in selected.items() if key not in changed
        } == {key: value for key, value in before.items() if key not in changed}
        runtime_root = Path(str(selected["runtime_root"]))
        assert (
            _tree_projection(
                runtime_root,
                held_lock_path=runtime_root / ".hsconfig/apply.lock",
            )
            == failure_runtime
        )
        journal_path = Path(str(selected["successor_journal_path"]))
        fence_path = Path(str(selected["successor_attempt_record_path"]))
        journal_fingerprint = _file_fingerprint(journal_path)
        fence_fingerprint = _file_fingerprint(fence_path)
        assert journal_fingerprint is not None
        assert fence_fingerprint is not None
        selection_count += 1
        _persist_worker_oracle(
            Path(oracle_path_text),
            {
                "failure_count": failure_count,
                "observation_count": observation_count,
                "selection_count": selection_count,
                "apply_entry_counts": counts,
                "failure_session": failure_session.to_value(),
                "selected_session": current.to_value(),
                "failure_runtime": failure_runtime,
                "journal_path": str(journal_path),
                "journal_fingerprint": journal_fingerprint,
                "fence_path": str(fence_path),
                "fence_fingerprint": fence_fingerprint,
                "apply_lock_identity": lock_identity,
                "apply_lock_size": 0,
            },
        )
        os._exit(_HARD_EXIT)

    try:
        controller._finalize_live_start(
            session_root=session_root,
            resume_intake=True,
            fault_hook=fault,
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
    return (tuple(identity), size, digest)


def test_prior_owner_pre_ini_consumed_failure_selects_not_committed_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared, owner = _seed_prior_owner(tmp_path, monkeypatch)
    runtime_root = fixture.profile.runtime_root
    output_root = derive_deck_output_binding(
        fixture.profile,
        fixture.deck_name,
    ).output_root
    profile_before = _file_fingerprint(operator_profile_path())
    assert profile_before is not None
    approved = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    approved_frozen = _frozen_identity(approved)
    assert approved.apply_invocation_sha256 is None
    assert approved.apply_recovery is None

    selected_oracle_path = tmp_path / "prior-owner-pre-ini-selected.json"
    _spawn_and_join(
        target=_fail_prior_owner_pre_ini_and_kill_selection_worker,
        args=(str(prepared.run_root), str(selected_oracle_path)),
        expected_exitcode=_HARD_EXIT,
        timeout_seconds=360,
    )
    oracle = json.loads(selected_oracle_path.read_bytes())
    assert oracle["failure_count"] == 1
    assert oracle["observation_count"] == 1
    assert oracle["selection_count"] == 1
    assert oracle["apply_entry_counts"] == _expected_apply_entry_counts(
        fresh=1,
        install_prepare=1,
        attempt_prepare=1,
    )

    selected = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    assert selected.to_value() == oracle["selected_session"]
    assert _frozen_identity(selected) == approved_frozen
    recovery = selected.apply_recovery
    assert isinstance(recovery, Mapping)
    assert recovery["install_route"] == "prior_owner"
    assert recovery["expected_action"] == "observe_not_committed"
    assert recovery["stable_physical_disposition"] is None
    assert recovery["runtime_match_status"] == "not_run"
    assert recovery["deck_config_ini_sha256"] is None
    assert recovery["owner_retirement"] is None
    assert recovery["candidate_path"] is None
    assert recovery["candidate_parent_identity"] is None
    assert recovery["predecessor_candidate_identity"] is None
    assert recovery["successor_candidate_identity"] is None
    assert recovery["candidate_tree_manifest_sha256"] is None
    assert recovery["candidate_tree_verified_sha256"] is None
    external = recovery["external_file_action"]
    assert isinstance(external, Mapping)
    assert external["action_kind"] == "materialize_file_action_staging"
    assert external["stage"] == "PLANNED"
    assert external["commit_mode"] == "replace_exact"
    assert external["predecessor_state"] == "exact"
    assert recovery["action_index"] == external["action_index"] + 1
    assert not Path(str(external["staging_path"])).exists()
    assert not Path(str(external["inner_temp_path"])).exists()

    authority = _capture_authority(
        fixture=fixture,
        prepared=prepared,
        current=selected,
    )
    assert authority.attempt_id != owner.transaction_id
    assert authority.attempt_id == recovery["apply_attempt_id"]
    admission_path = Path(str(authority.runtime_admission_binding["admission_path"]))
    assert not admission_path.is_relative_to(runtime_root)
    admission_fingerprint = _file_fingerprint(admission_path)
    assert admission_fingerprint is not None
    assert admission_fingerprint[0] == tuple(
        authority.runtime_admission_binding["admission_identity"]
    )
    assert (
        admission_fingerprint[2]
        == authority.runtime_admission_binding["admission_sha256"]
    )
    invocation_path = prepared.run_root / "receipts/apply_invocation.json"
    invocation = load_apply_invocation(invocation_path)
    assert invocation.apply_attempt_id == authority.attempt_id
    assert invocation.content_sha256 == authority.apply_invocation_sha256
    assert tuple(prepared.run_root.rglob("*apply_invocation*.json")) == (
        invocation_path,
    )
    journal_path = Path(str(oracle["journal_path"]))
    fence_path = Path(str(oracle["fence_path"]))
    journal_fingerprint = _json_fingerprint(oracle["journal_fingerprint"])
    fence_fingerprint = _json_fingerprint(oracle["fence_fingerprint"])
    assert journal_path == runtime_transaction_journal_path(
        runtime_root,
        authority.attempt_id,
    )
    assert _file_fingerprint(journal_path) == journal_fingerprint
    assert _file_fingerprint(fence_path) == fence_fingerprint
    assert journal_fingerprint[0] == tuple(recovery["successor_journal_identity"])
    assert journal_fingerprint[2] == recovery["successor_journal_sha256"]
    assert fence_fingerprint[0] == tuple(recovery["successor_attempt_record_identity"])
    assert fence_fingerprint[2] == recovery["successor_attempt_record_sha256"]
    nonowning_journal = next(
        item
        for item in load_runtime_transaction_journals(runtime_root)
        if item.transaction_id == authority.attempt_id
    )
    assert nonowning_journal.phase is RuntimeTransactionPhase.PREPARED
    assert nonowning_journal.owns_target is False
    fence = runtime_apply._runtime_attempt_retention_from_raw(
        fence_path.read_bytes(),
        runtime_root=runtime_root,
    )
    assert fence.state == "PRIOR_OWNER_BOUND"
    assert fence.apply_attempt_id == authority.attempt_id
    assert fence.retention_owner_run_id == selected.run_id
    assert fence.target_path == owner.target_path
    assert fence.target_identity == owner.target_identity
    assert fence.owns_target is False
    assert fence.target_owner_journal_path == owner.journal_path
    assert fence.target_owner_journal_identity == owner.journal_fingerprint[0]
    assert fence.target_owner_journal_sha256 == owner.journal_fingerprint[2]
    assert fence.candidate_path is None
    assert not tuple((runtime_root / ".hsconfig/staging").iterdir())
    lock_path = runtime_root / ".hsconfig/apply.lock"
    assert (
        _tree_projection(runtime_root, held_lock_path=lock_path)
        == oracle["failure_runtime"]
    )
    assert _file_fingerprint(lock_path) == (
        tuple(oracle["apply_lock_identity"]),
        0,
        _sha256_bytes(b""),
    )
    assert _file_fingerprint(owner.journal_path) == owner.journal_fingerprint
    assert path_identity(owner.target_path) == owner.target_identity
    assert _physical_tree(owner.target_path) == owner.target_tree
    assert (
        _file_fingerprint(runtime_root / "CustomConfig/deck_config.ini")
        == owner.remapped_ini_fingerprint
    )
    assert _file_fingerprint(operator_profile_path()) == profile_before
    assert _changed_paths(
        owner.runtime_before_second,
        _physical_tree(runtime_root),
    ) == {
        journal_path.relative_to(runtime_root).as_posix(),
        fence_path.relative_to(runtime_root).as_posix(),
    }
    assert _file_fingerprint(admission_path) == admission_fingerprint
    assert tuple(
        path for path in (runtime_root / "CustomConfig").iterdir() if path.is_dir()
    ) == (owner.target_path,)
    selected_output = _physical_tree(output_root)
    selected_invocation = _file_fingerprint(invocation_path)
    assert selected_invocation == authority.invocation_fingerprint

    resume_oracle_path = tmp_path / "prior-owner-pre-ini-resume.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(resume_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    resumed = json.loads(resume_oracle_path.read_bytes())
    assert resumed["status"] == "FAILED_PRESERVED"
    assert resumed["apply_entry_counts"] == _expected_apply_entry_counts(recovery=1)
    terminal = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    assert terminal.content_sha256 == resumed["session_sha256"]
    assert terminal.terminal_status == "FAILED_PRESERVED"
    assert terminal.pending_transition is None
    assert terminal.apply_recovery is None
    assert terminal.closed_apply_recovery_commitment is None
    assert terminal.attempt_acknowledgement is None
    assert _frozen_identity(terminal) == approved_frozen
    assert terminal.apply_invocation_sha256 == authority.apply_invocation_sha256
    terminal_value = terminal.to_value()
    assert (
        terminal_value["runtime_admission_binding"]
        == authority.runtime_admission_binding
    )
    assert (
        terminal_value["runtime_layout_bootstrap"] == authority.runtime_layout_bootstrap
    )
    assert (
        terminal_value["output_operation_admission_binding"]
        == authority.output_operation_admission_binding
    )
    assert terminal_value["output_child_binding"] == authority.output_child_binding
    assert terminal_value["publication_binding"] == authority.publication_binding
    assert terminal.result_intent["apply_attempt_id"] == authority.attempt_id
    assert terminal.result_intent["raw_apply_status"] is None
    assert terminal.result_intent["physical_disposition"] == "NOT_COMMITTED"
    assert terminal.result_intent["runtime_match_status"] == "not_run"
    assert terminal.result_intent["error_code"] == "apply_not_committed"
    assert terminal.terminal_retirement["operation"] == "release_resolved_terminal"
    assert terminal.terminal_retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"
    resolution = terminal.terminal_retirement["terminal_resolution_evidence"]
    assert resolution["resolved_physical_disposition"] == "NOT_COMMITTED"
    assert resolution["owner_retirement"] is None
    assert resolution["external_file_action"] is None
    for prefix, expected_path, expected_fingerprint in (
        ("retained_attempt_record", fence_path, fence_fingerprint),
        ("retained_journal", journal_path, journal_fingerprint),
        (
            "retained_target_owner_journal",
            owner.journal_path,
            owner.journal_fingerprint,
        ),
    ):
        assert Path(str(terminal.result_intent[f"{prefix}_path"])) == expected_path
        assert (
            tuple(terminal.result_intent[f"{prefix}_identity"])
            == (expected_fingerprint[0])
        )
        assert terminal.result_intent[f"{prefix}_sha256"] == expected_fingerprint[2]

    assert _physical_tree(runtime_root) == owner.runtime_before_second
    assert not journal_path.exists()
    assert not fence_path.exists()
    assert not tuple((runtime_root / ".hsconfig/staging").iterdir())
    assert load_runtime_live_attempt_admission() is None
    assert not admission_path.exists()
    journals = load_runtime_transaction_journals(runtime_root)
    assert len(journals) == 1
    assert journals[0].transaction_id == owner.transaction_id
    assert journals[0].phase is RuntimeTransactionPhase.FINALIZED
    assert journals[0].owns_target is True
    assert _file_fingerprint(owner.journal_path) == owner.journal_fingerprint
    assert path_identity(owner.target_path) == owner.target_identity
    assert _physical_tree(owner.target_path) == owner.target_tree
    assert tuple(
        path for path in (runtime_root / "CustomConfig").iterdir() if path.is_dir()
    ) == (owner.target_path,)
    assert (
        _file_fingerprint(runtime_root / "CustomConfig/deck_config.ini")
        == owner.remapped_ini_fingerprint
    )
    assert _physical_tree(output_root) == selected_output
    assert _file_fingerprint(operator_profile_path()) == profile_before
    assert _file_fingerprint(invocation_path) == selected_invocation
    assert tuple(prepared.run_root.rglob("*apply_invocation*.json")) == (
        invocation_path,
    )

    terminal_snapshot = {
        "session": (prepared.run_root / "session.json").read_bytes(),
        "result": _result_pair(prepared.run_root),
        "run_tree": _physical_tree(prepared.run_root),
        "runtime": _physical_tree(runtime_root),
        "output": _physical_tree(output_root),
        "profile": _file_fingerprint(operator_profile_path()),
        "invocation": _file_fingerprint(invocation_path),
    }
    replay_oracle_path = tmp_path / "prior-owner-pre-ini-replay.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(replay_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    replayed = json.loads(replay_oracle_path.read_bytes())
    assert replayed.pop("apply_entry_counts") == _expected_apply_entry_counts()
    first_public = dict(resumed)
    first_public.pop("apply_entry_counts")
    assert replayed == first_public
    assert (prepared.run_root / "session.json").read_bytes() == terminal_snapshot[
        "session"
    ]
    assert _result_pair(prepared.run_root) == terminal_snapshot["result"]
    assert _physical_tree(prepared.run_root) == terminal_snapshot["run_tree"]
    assert _physical_tree(runtime_root) == terminal_snapshot["runtime"]
    assert _physical_tree(output_root) == terminal_snapshot["output"]
    assert _file_fingerprint(operator_profile_path()) == terminal_snapshot["profile"]
    assert _file_fingerprint(invocation_path) == terminal_snapshot["invocation"]
    assert not admission_path.exists()
