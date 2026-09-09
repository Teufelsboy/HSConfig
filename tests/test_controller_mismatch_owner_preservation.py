from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from typing import Any, Mapping

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig import runtime_installer
from hsconfig.apply_invocation import load_apply_invocation
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.operator_profile import derive_deck_output_binding, operator_profile_path
from hsconfig.package_io import path_identity
from hsconfig.package_request import FrozenJsonDocument
from hsconfig.runtime_live_admission import load_runtime_live_attempt_admission
from hsconfig.runtime_transaction_journal import (
    RuntimeTransactionPhase,
    load_runtime_transaction_journals,
)
from tests.test_codex_first_live_e2e import (
    _approve,
    _changed_candidate,
    _local_state,
    _matched_package,
    _prepare,
    _prepare_approved,
)
from tests.test_configure_prepublication_apply import _file_fingerprint, _physical_tree
from tests.test_controller_output_hard_kills import (
    _expected_apply_entry_counts,
    _persist_worker_oracle,
    _public_resume_worker,
    _sha256_bytes,
    _spawn_and_join,
    _start_apply_entry_observer,
)


def _committed_mismatch_worker(
    session_root_text: str,
    oracle_path_text: str,
) -> None:
    session_root = Path(session_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    runtime_root: Path | None = None
    changed: list[tuple[Path, bytes, tuple[int, int, int]]] = []
    counts, previous_profile = _start_apply_entry_observer()

    def drift_after_commit(point: LiveStartFaultPoint) -> None:
        nonlocal runtime_root
        if (
            point
            is not LiveStartFaultPoint.AFTER_INSTALLER_RETURN_BEFORE_APPLY_COMMITTED
        ):
            return
        assert not changed
        invocation = load_apply_invocation(
            session_root / "receipts/apply_invocation.json"
        )
        admission = load_runtime_live_attempt_admission()
        assert admission is not None
        runtime_root = admission.runtime_root
        journals = load_runtime_transaction_journals(runtime_root)
        assert len(journals) == 1
        owner = journals[0]
        assert owner.phase is RuntimeTransactionPhase.FINALIZED
        assert owner.owns_target is True
        assert owner.transaction_id == invocation.apply_attempt_id
        assert owner.transaction_id == admission.apply_attempt_id
        target = runtime_root / owner.target_path
        assert target.is_relative_to(runtime_root)
        mulligan = target / "Mulligan.json"
        before = mulligan.read_bytes()
        identity = path_identity(mulligan)
        value = json.loads(before)
        assert value["GameCardId"] == "Mulligan"
        assert value["Mulligan"]["values"][0]["value"] == "hold"
        value["Mulligan"]["values"][0]["value"] = "discard"
        drifted = FrozenJsonDocument.from_value(value).canonical_json
        assert drifted != before
        mulligan.write_bytes(drifted)
        assert path_identity(mulligan) == identity
        changed.append((mulligan, drifted, identity))

    try:
        result = controller._finalize_live_start(
            session_root=session_root,
            fault_hook=drift_after_commit,
        )
        assert isinstance(result, controller.LiveStartResult)
        terminal = session.load_live_start_session(
            session_root,
            local_app_data_root=session_root.parents[2],
        )
    finally:
        sys.setprofile(previous_profile)

    assert runtime_root is not None
    assert len(changed) == 1
    mulligan, drifted, identity = changed[0]
    assert mulligan.read_bytes() == drifted
    assert path_identity(mulligan) == identity
    _persist_worker_oracle(
        Path(oracle_path_text),
        {
            "status": result.status,
            "run_root": str(result.run_root),
            "summary_sha256": _sha256_bytes(result.summary.canonical_json),
            "session_sha256": terminal.content_sha256,
            "apply_entry_counts": counts,
        },
    )


def _bound_file_snapshot(
    intent: Mapping[str, Any],
    *,
    prefix: str,
) -> tuple[Path, tuple[tuple[int, int, int], bytes]]:
    path = Path(str(intent[f"{prefix}_path"]))
    raw = path.read_bytes()
    identity = path_identity(path)
    assert identity == tuple(intent[f"{prefix}_identity"])
    assert "sha256:" + sha256(raw).hexdigest() == intent[f"{prefix}_sha256"]
    return path, (identity, raw)


def test_committed_mismatch_fence_survives_later_changed_install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later package cannot retire an earlier committed-mismatch owner."""

    _local_state(tmp_path, monkeypatch)
    first_fixture, first = _prepare_approved(tmp_path / "first", monkeypatch)
    first_oracle_path = tmp_path / "first-mismatch-oracle.json"
    _spawn_and_join(
        target=_committed_mismatch_worker,
        args=(str(first.run_root), str(first_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    first_oracle = json.loads(first_oracle_path.read_bytes())
    assert first_oracle["status"] == "APPLIED_BUT_NOT_VERIFIED"
    assert first_oracle["apply_entry_counts"] == _expected_apply_entry_counts(
        fresh=1,
        install_prepare=1,
        attempt_prepare=1,
    )

    runtime_root = first_fixture.profile.runtime_root
    first_terminal = session.load_live_start_session(
        first.run_root,
        local_app_data_root=first.run_root.parents[2],
    )
    first_intent = first_terminal.result_intent
    assert isinstance(first_intent, Mapping)
    assert first_terminal.phase is session.LiveStartPhase.APPLY_COMMITTED
    assert first_terminal.terminal_status == "APPLIED_BUT_NOT_VERIFIED"
    assert first_terminal.apply_recovery is None
    assert first_terminal.closed_apply_recovery_commitment is None
    assert first_terminal.attempt_acknowledgement is None
    assert isinstance(first_terminal.runtime_layout_bootstrap, Mapping)
    assert isinstance(first_terminal.terminal_retirement, Mapping)
    assert first_intent["physical_disposition"] == "COMMITTED"
    assert first_intent["runtime_match_status"] == "mismatch"
    assert first_intent["error_code"] == "runtime_mismatch"
    assert first_terminal.terminal_retirement["operation"] == (
        "release_committed_mismatch"
    )
    assert first_terminal.terminal_retirement["stage"] == (
        "ADMISSION_RELEASE_AUTHORIZED"
    )
    assert load_runtime_live_attempt_admission() is None

    first_attempt_id = str(first_intent["apply_attempt_id"])
    first_invocation_path = first.run_root / "receipts/apply_invocation.json"
    assert tuple(first.run_root.rglob("*apply_invocation*.json")) == (
        first_invocation_path,
    )
    first_invocation_raw = first_invocation_path.read_bytes()
    first_invocation = load_apply_invocation(first_invocation_path)
    assert first_invocation.apply_attempt_id == first_attempt_id
    assert first_terminal.runtime_layout_bootstrap["apply_attempt_id"] == (
        first_attempt_id
    )
    assert first_terminal.terminal_retirement["apply_attempt_id"] == first_attempt_id
    assert first_terminal.apply_invocation_sha256 == first_invocation.content_sha256
    assert (
        "sha256:" + sha256(first_invocation_raw).hexdigest()
        == (first_terminal.artifact_bindings["receipts/apply_invocation.json"])
    )
    fence_path, fence_snapshot = _bound_file_snapshot(
        first_intent,
        prefix="retained_attempt_record",
    )
    journal_path, journal_snapshot = _bound_file_snapshot(
        first_intent,
        prefix="retained_journal",
    )
    owner_path, owner_snapshot = _bound_file_snapshot(
        first_intent,
        prefix="retained_target_owner_journal",
    )
    assert journal_path == owner_path
    assert journal_snapshot == owner_snapshot
    assert len(load_runtime_transaction_journals(runtime_root)) == 1
    first_owner = load_runtime_transaction_journals(runtime_root)[0]
    assert first_owner.transaction_id == first_attempt_id
    assert first_owner.phase is RuntimeTransactionPhase.FINALIZED
    assert first_owner.owns_target is True
    assert first_owner.cleanup_started is False
    first_target = runtime_root / first_owner.target_path
    assert first_target.is_dir()
    first_target_snapshot = _physical_tree(first_target)
    first_fence = runtime_installer._runtime_attempt_retention_from_raw(
        fence_snapshot[1],
        runtime_root=runtime_root,
    )
    assert first_fence.state == "FINALIZED"
    assert first_fence.apply_attempt_id == first_attempt_id
    assert first_fence.owns_target is True
    assert first_fence.journal_path == journal_path
    assert first_fence.journal_identity == journal_snapshot[0]
    assert first_fence.journal_sha256 == first_intent["retained_journal_sha256"]
    assert first_fence.target_path == first_target
    assert first_fence.target_identity == path_identity(first_target)
    assert first_fence.target_owner_journal_path == owner_path
    assert first_fence.target_owner_journal_identity == owner_snapshot[0]
    assert (
        first_fence.target_owner_journal_sha256
        == (first_intent["retained_target_owner_journal_sha256"])
    )
    first_tombstone = (
        runtime_root / ".hsconfig/owner-retirements" / f"{first_attempt_id}.json"
    )
    assert not os.path.lexists(first_tombstone)

    first_session_bytes = (first.run_root / "session.json").read_bytes()
    first_result_tree = _physical_tree(first.run_root / "result")
    first_run_tree = _physical_tree(first.run_root)
    profile_snapshot = _file_fingerprint(operator_profile_path())
    assert profile_snapshot is not None
    output_root = derive_deck_output_binding(
        first_fixture.profile,
        first_fixture.deck_name,
    ).output_root
    first_publication = first_terminal.publication_binding
    assert isinstance(first_publication, Mapping)

    second_fixture, second = _prepare(
        tmp_path / "second",
        monkeypatch,
        profile=first_fixture.profile,
    )
    second_fixture = _changed_candidate(second_fixture)
    _approve(tmp_path / "second", second_fixture, second)
    second_oracle_path = tmp_path / "second-install-oracle.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(second.run_root), str(second_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    second_oracle = json.loads(second_oracle_path.read_bytes())
    assert second_oracle["status"] == "LIVE_AND_MATCHED"
    assert second_oracle["apply_entry_counts"] == _expected_apply_entry_counts(
        fresh=1,
        install_prepare=1,
        attempt_prepare=1,
    )

    second_terminal = session.load_live_start_session(
        second.run_root,
        local_app_data_root=second.run_root.parents[2],
    )
    second_intent = second_terminal.result_intent
    assert isinstance(second_intent, Mapping)
    assert isinstance(second_terminal.runtime_layout_bootstrap, Mapping)
    assert isinstance(second_terminal.attempt_acknowledgement, Mapping)
    assert isinstance(second_terminal.terminal_retirement, Mapping)
    second_invocation_path = second.run_root / "receipts/apply_invocation.json"
    assert tuple(second.run_root.rglob("*apply_invocation*.json")) == (
        second_invocation_path,
    )
    second_invocation = load_apply_invocation(second_invocation_path)
    second_invocation_raw = second_invocation_path.read_bytes()
    second_attempt_id = second_invocation.apply_attempt_id
    assert second_attempt_id != first_attempt_id
    assert second_terminal.runtime_layout_bootstrap["apply_attempt_id"] == (
        second_attempt_id
    )
    assert second_intent["apply_attempt_id"] == second_attempt_id
    assert second_terminal.attempt_acknowledgement["apply_attempt_id"] == (
        second_attempt_id
    )
    assert second_terminal.terminal_retirement["apply_attempt_id"] == (
        second_attempt_id
    )
    assert second_terminal.apply_invocation_sha256 == second_invocation.content_sha256
    assert (
        "sha256:" + sha256(second_invocation_raw).hexdigest()
        == (second_terminal.artifact_bindings["receipts/apply_invocation.json"])
    )
    assert second_terminal.terminal_status == "LIVE_AND_MATCHED"
    assert second_terminal.apply_recovery is None
    assert second_terminal.pending_transition is None
    assert second_terminal.terminal_retirement["stage"] == (
        "ADMISSION_RELEASE_AUTHORIZED"
    )

    second_output, second_package, second_target = _matched_package(second_fixture)
    assert second_output == output_root
    assert second_target != first_target
    second_publication = second_terminal.publication_binding
    assert isinstance(second_publication, Mapping)
    assert second_publication["revision"] != first_publication["revision"]
    assert second_package == output_root / second_publication["revision"] / "04_package"
    journals = load_runtime_transaction_journals(runtime_root)
    assert {row.transaction_id for row in journals} == {
        first_attempt_id,
        second_attempt_id,
    }
    second_owner = next(
        row for row in journals if row.transaction_id == second_attempt_id
    )
    assert second_owner.phase is RuntimeTransactionPhase.FINALIZED
    assert second_owner.owns_target is True
    assert runtime_root / second_owner.target_path == second_target
    assert second_owner.previous_config_dir == first_target.name
    assert second_owner.next_config_dir == second_target.name
    assert second_owner.package_root_sha256 != first_owner.package_root_sha256

    retained_snapshots = {
        fence_path: fence_snapshot,
        journal_path: journal_snapshot,
    }
    assert {
        path: (path_identity(path), path.read_bytes()) for path in retained_snapshots
    } == retained_snapshots
    assert _physical_tree(first_target) == first_target_snapshot
    assert not os.path.lexists(first_tombstone)
    assert (first.run_root / "session.json").read_bytes() == first_session_bytes
    assert _physical_tree(first.run_root / "result") == first_result_tree
    assert _physical_tree(first.run_root) == first_run_tree
    assert _file_fingerprint(operator_profile_path()) == profile_snapshot

    runtime_after_second = _physical_tree(runtime_root)
    output_after_second = _physical_tree(output_root)
    second_session_bytes = (second.run_root / "session.json").read_bytes()
    second_result_tree = _physical_tree(second.run_root / "result")
    second_run_tree = _physical_tree(second.run_root)

    first_replay_oracle_path = tmp_path / "first-replay-oracle.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(first.run_root), str(first_replay_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    first_replay = json.loads(first_replay_oracle_path.read_bytes())
    assert first_replay.pop("apply_entry_counts") == _expected_apply_entry_counts()
    first_result = dict(first_oracle)
    first_result.pop("apply_entry_counts")
    assert first_replay == first_result
    assert (first.run_root / "session.json").read_bytes() == first_session_bytes
    assert _physical_tree(first.run_root / "result") == first_result_tree
    assert {
        path: (path_identity(path), path.read_bytes()) for path in retained_snapshots
    } == retained_snapshots
    assert _physical_tree(first_target) == first_target_snapshot
    assert not os.path.lexists(first_tombstone)

    assert _physical_tree(first.run_root) == first_run_tree
    assert _physical_tree(second.run_root) == second_run_tree
    assert _physical_tree(runtime_root) == runtime_after_second
    assert _physical_tree(output_root) == output_after_second
    assert _file_fingerprint(operator_profile_path()) == profile_snapshot
    second_replay_oracle_path = tmp_path / "second-replay-oracle.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(second.run_root), str(second_replay_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    second_replay = json.loads(second_replay_oracle_path.read_bytes())
    assert second_replay.pop("apply_entry_counts") == _expected_apply_entry_counts()
    second_result = dict(second_oracle)
    second_result.pop("apply_entry_counts")
    assert second_replay == second_result
    assert (second.run_root / "session.json").read_bytes() == second_session_bytes
    assert _physical_tree(second.run_root / "result") == second_result_tree
    assert _physical_tree(runtime_root) == runtime_after_second
    assert _physical_tree(output_root) == output_after_second
    assert _physical_tree(first.run_root) == first_run_tree
    assert _physical_tree(second.run_root) == second_run_tree
    assert _file_fingerprint(operator_profile_path()) == profile_snapshot
