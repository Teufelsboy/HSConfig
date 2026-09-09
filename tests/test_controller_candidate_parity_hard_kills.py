from __future__ import annotations

from collections.abc import Mapping
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig import runtime_installer
from hsconfig.apply_invocation import load_apply_invocation
from hsconfig.live_start_faults import LiveStartFaultPoint, no_live_start_fault
from hsconfig.operator_profile import operator_profile_path
from hsconfig.package_io import path_identity
from hsconfig.runtime_live_admission import load_runtime_live_attempt_admission
from hsconfig.runtime_transaction_journal import (
    RuntimeTransactionJournal,
    RuntimeTransactionPhase,
    read_runtime_transaction_journal,
    runtime_transaction_journal_path,
)
from tests.test_codex_first_live_e2e import (
    _local_state,
    _matched_package,
    _prepare_approved,
)
from tests.test_configure_prepublication_apply import (
    _file_fingerprint,
    _persist_worker_oracle,
)
from tests.test_controller_output_hard_kills import (
    _expected_apply_entry_counts,
    _frozen_identity,
    _public_resume_worker,
    _runtime_apply_lock_metadata,
    _sha256_bytes,
    _spawn_and_join,
    _start_apply_entry_observer,
)
from tests.test_controller_runtime_action_chain import (
    _assert_tree_after_exit,
    _load_worker_session,
    _runtime_tree,
)
from tests.test_controller_runtime_hard_kills import _assert_complete_layout


_PRE_CAS = (
    LiveStartFaultPoint.AFTER_NONTERMINAL_RECOVERY_PHYSICAL_STEP_BEFORE_CURSOR_CAS
)
_POST_CAS = LiveStartFaultPoint.AFTER_NONTERMINAL_RECOVERY_CURSOR_CAS
_HARD_EXIT = 93


def _json_fingerprint(value: object) -> tuple[tuple[int, int, int], int, str]:
    assert isinstance(value, list)
    assert len(value) == 3
    identity = value[0]
    assert isinstance(identity, list)
    return tuple(identity), int(value[1]), str(value[2])


def _write_fsynced(path: Path, raw: bytes) -> None:
    with path.open("xb") as handle:
        assert handle.write(raw) == len(raw)
        handle.flush()
        os.fsync(handle.fileno())


def _overwrite_fsynced(path: Path, raw: bytes) -> None:
    with path.open("r+b") as handle:
        handle.seek(0)
        handle.write(raw)
        handle.truncate()
        handle.flush()
        os.fsync(handle.fileno())


def test_candidate_replacement_helper_preserves_exact_binary_bytes(
    tmp_path: Path,
) -> None:
    payload = b'{\n  "value": "line"\r\n}\n\x1a\x00'
    path = tmp_path / "replacement.json"
    _write_fsynced(path, payload)
    assert path.read_bytes() == payload


def _wrong_bytes(raw: bytes) -> bytes:
    if not raw:
        return b"x"
    return bytes((raw[0] ^ 1,)) + raw[1:]


def _read_single_journal(
    runtime_root: Path, attempt_id: str
) -> RuntimeTransactionJournal:
    path = runtime_transaction_journal_path(runtime_root, attempt_id)
    assert tuple(path.parent.glob("*.json")) == (path,)
    journal = read_runtime_transaction_journal(path)
    assert journal.transaction_id == attempt_id
    return journal


def _publication_tree_with_held_lock(output_root: Path) -> dict[str, dict[str, object]]:
    tree = _runtime_tree(output_root, held_lock_path=output_root / ".publish.lock")
    # The lock is identity-bound and size-zero; Windows denies reading it while held.
    tree[".publish.lock"]["sha256"] = _sha256_bytes(b"")
    return tree


def _source_root(current: session.LiveStartSession) -> tuple[Path, Path, Path]:
    publication = current.publication_binding
    assert isinstance(publication, Mapping)
    output_root = Path(str(publication["output_child_path"]))
    package_root = output_root / str(publication["revision"]) / "04_package"
    custom_config = package_root / "CustomConfig"
    children = tuple(path for path in custom_config.iterdir() if path.is_dir())
    assert len(children) == 1
    source_root = children[0]
    assert source_root.is_relative_to(package_root)
    return output_root, package_root, source_root


def _assert_attack_root_is_external(
    attack_root: Path,
    *,
    runtime_root: Path,
    session_root: Path,
    output_root: Path,
    source_root: Path,
) -> None:
    for authority_root in (runtime_root, session_root, output_root, source_root):
        assert not attack_root.is_relative_to(authority_root)
        assert not authority_root.is_relative_to(attack_root)


def _checkpoint_matches(
    *,
    checkpoint: str,
    point: LiveStartFaultPoint,
    recovery: Mapping[str, Any],
    attack_relative_path: Path,
) -> bool:
    action = recovery.get("expected_action")
    if checkpoint == "candidate_entry":
        return (
            point is _PRE_CAS
            and action == "materialize_candidate_tree_entry"
            and recovery.get("candidate_tree_next_kind") == "file"
            and recovery.get("candidate_tree_next_relative_path")
            == attack_relative_path.as_posix()
        )
    if checkpoint == "before_rename":
        return point is _POST_CAS and action == "rename_candidate_to_target"
    if checkpoint == "before_owner_bind":
        return point is _POST_CAS and action == "bind_renamed_target"
    raise AssertionError(f"unknown candidate parity checkpoint: {checkpoint}")


def _assert_materialized_candidate_prefix(
    *,
    source_root: Path,
    destination_root: Path,
    completed_entries: int,
) -> None:
    source = runtime_installer.snapshot_bounded_filesystem_package(source_root)
    destination = runtime_installer.snapshot_bounded_filesystem_package(
        destination_root
    )
    ordered_source_entries = tuple(
        sorted(
            (
                *((name, "file") for name in source.file_names()),
                *((name, "directory") for name in source.directory_names),
            ),
            key=lambda row: row[0],
        )
    )
    expected_entries = ordered_source_entries[:completed_entries]
    assert destination.file_names() == tuple(
        name for name, kind in expected_entries if kind == "file"
    )
    assert destination.directory_names == tuple(
        name for name, kind in expected_entries if kind == "directory"
    )
    for name in destination.file_names():
        assert destination.read_bytes(name) == source.read_bytes(name)


def _physical_membership(root: Path) -> tuple[tuple[str, str], ...]:
    return tuple(
        (
            path.relative_to(root).as_posix(),
            "directory" if path.is_dir() else "file",
        )
        for path in sorted(root.rglob("*"))
    )


def _assert_checkpoint_semantics(
    *,
    checkpoint: str,
    current: session.LiveStartSession,
    recovery: Mapping[str, Any],
    runtime_root: Path,
    attack_relative_path: Path,
) -> tuple[Path, Path, Path]:
    assert current.phase is session.LiveStartPhase.APPLY_STARTED
    _assert_complete_layout(current)
    assert recovery["recovery_stage"] == "ACTIVE"
    assert recovery["install_route"] == "new_target"
    assert recovery["runtime_root"] == str(runtime_root)
    assert tuple(recovery["runtime_root_identity"]) == path_identity(runtime_root)
    cursor = int(recovery["candidate_tree_cursor"])
    entry_count = int(recovery["candidate_tree_entry_count"])
    assert 0 <= cursor <= entry_count
    candidate = Path(str(recovery["candidate_path"]))
    target = Path(str(recovery["renamed_target_path"]))
    staging_rows = [
        row
        for row in current.runtime_layout_bootstrap["directories"]
        if row["role"] == "staging"
    ]
    assert len(staging_rows) == 1
    staging_row = staging_rows[0]
    assert candidate.parent == Path(str(staging_row["path"]))
    assert (
        candidate == runtime_root / ".hsconfig/staging" / recovery["apply_attempt_id"]
    )
    assert tuple(recovery["candidate_parent_identity"]) == tuple(
        staging_row["successor_identity"]
    )
    assert path_identity(candidate.parent) == tuple(
        recovery["candidate_parent_identity"]
    )
    leaf_root = candidate
    external = recovery.get("external_file_action")

    journal = _read_single_journal(runtime_root, str(recovery["apply_attempt_id"]))
    journal_path = Path(str(recovery["successor_journal_path"]))
    journal_fingerprint = _file_fingerprint(journal_path)
    assert journal_fingerprint[0] == tuple(recovery["successor_journal_identity"])
    assert journal_fingerprint[2] == recovery["successor_journal_sha256"]
    retention_path = Path(str(recovery["successor_attempt_record_path"]))
    retention_fingerprint = _file_fingerprint(retention_path)
    assert retention_fingerprint[0] == tuple(
        recovery["successor_attempt_record_identity"]
    )
    assert retention_fingerprint[2] == recovery["successor_attempt_record_sha256"]
    retention = runtime_installer._runtime_attempt_retention_from_raw(
        retention_path.read_bytes(),
        runtime_root=runtime_root,
    )
    assert retention.state == "CANDIDATE_BOUND"
    assert retention.apply_attempt_id == recovery["apply_attempt_id"]
    assert retention.candidate_path == candidate
    assert retention.candidate_identity == tuple(
        recovery.get("successor_candidate_identity")
        or recovery.get("predecessor_candidate_identity")
    )

    if checkpoint == "candidate_entry":
        assert recovery["expected_action"] == "materialize_candidate_tree_entry"
        assert external is None
        assert cursor < entry_count
        assert recovery["candidate_tree_next_kind"] == "file"
        assert recovery["candidate_tree_next_source_identity"] is not None
        assert recovery["candidate_tree_next_parent_identity"] is not None
        assert recovery["candidate_tree_next_size"] is not None
        assert recovery["candidate_tree_next_sha256"] is not None
        assert recovery["candidate_tree_next_successor_identity"] is None
        assert recovery["successor_candidate_identity"] is not None
        assert journal.phase is RuntimeTransactionPhase.PREPARED
        assert candidate.is_dir()
        assert path_identity(candidate) == tuple(
            recovery["successor_candidate_identity"]
        )
        assert not target.exists()
        assert not tuple(runtime_root.rglob("*.live-start-atomic.tmp"))
    elif checkpoint == "before_rename":
        assert recovery["expected_action"] == "rename_candidate_to_target"
        assert external is None
        assert cursor == entry_count
        assert (
            recovery["candidate_tree_verified_sha256"]
            == recovery["candidate_tree_manifest_sha256"]
        )
        assert recovery["successor_candidate_identity"] is not None
        assert journal.phase is RuntimeTransactionPhase.RUNTIME_VERIFIED
        assert candidate.is_dir()
        assert path_identity(candidate) == tuple(
            recovery["successor_candidate_identity"]
        )
        assert not target.exists()
        assert tuple(candidate.parent.iterdir()) == (candidate,)
        assert not tuple(runtime_root.rglob("*.live-start-atomic.tmp"))
    else:
        assert checkpoint == "before_owner_bind"
        assert recovery["expected_action"] == "bind_renamed_target"
        assert cursor == entry_count
        assert (
            recovery["candidate_tree_verified_sha256"]
            == recovery["candidate_tree_manifest_sha256"]
        )
        assert recovery["predecessor_candidate_identity"] is not None
        assert recovery["successor_candidate_identity"] is None
        assert recovery["predecessor_renamed_target_identity"] is None
        assert recovery["successor_renamed_target_identity"] is not None
        assert not candidate.exists()
        assert target.is_dir()
        assert path_identity(target) == tuple(
            recovery["successor_renamed_target_identity"]
        )
        assert isinstance(external, Mapping)
        assert external["action_kind"] == "bind_renamed_target"
        assert external["stage"] == "STAGING_BOUND"
        assert external["commit_mode"] == "replace_exact"
        assert external["final_path"] == recovery["successor_journal_path"]
        assert external["staging_identity"] is not None
        assert external["staging_size"] == external["planned_successor_size"]
        assert external["staging_sha256"] == external["planned_successor_sha256"]
        staging = Path(str(external["staging_path"]))
        assert staging.is_file()
        assert path_identity(staging) == tuple(external["staging_identity"])
        assert _sha256_bytes(staging.read_bytes()) == external["staging_sha256"]
        assert not Path(str(external["inner_temp_path"])).exists()
        assert journal.phase is RuntimeTransactionPhase.RUNTIME_VERIFIED
        leaf_root = target

    leaf = leaf_root / attack_relative_path
    source_identity = recovery.get("candidate_tree_next_source_identity")
    assert leaf.is_file()
    if checkpoint == "candidate_entry":
        assert leaf.stat().st_size == recovery["candidate_tree_next_size"]
        assert (
            _sha256_bytes(leaf.read_bytes()) == recovery["candidate_tree_next_sha256"]
        )
        assert source_identity is not None
        assert path_identity(leaf.parent) == tuple(
            recovery["candidate_tree_next_parent_identity"]
        )
    assert not tuple(runtime_root.rglob("*.live-start-atomic.tmp"))
    expected_staging = (
        (Path(str(external["staging_path"])),)
        if checkpoint == "before_owner_bind"
        else ()
    )
    assert tuple(sorted(runtime_root.rglob("*.staged"))) == expected_staging
    return candidate, target, leaf


def _apply_attack(
    *,
    attack: str,
    leaf: Path,
    attack_root: Path,
) -> dict[str, object]:
    raw = leaf.read_bytes()
    original_identity = path_identity(leaf)
    original_status = leaf.lstat()
    assert stat.S_ISREG(original_status.st_mode)
    assert original_status.st_nlink == 1

    if attack == "safe_same_bytes_new_identity":
        held = attack_root / "held-original-leaf"
        replacement = leaf.with_name(f".{leaf.name}.candidate-parity-replacement")
        assert not held.exists()
        assert not replacement.exists()
        os.replace(leaf, held)
        _write_fsynced(replacement, raw)
        os.replace(replacement, leaf)
        replacement_status = leaf.lstat()
        replacement_identity = path_identity(leaf)
        assert stat.S_ISREG(replacement_status.st_mode)
        assert replacement_status.st_nlink == 1
        assert replacement_identity != original_identity
        assert leaf.read_bytes() == held.read_bytes() == raw
        assert path_identity(held) == original_identity
        assert not replacement.exists()
        return {
            "kind": attack,
            "original_identity": original_identity,
            "replacement_identity": replacement_identity,
            "size": len(raw),
            "sha256": _sha256_bytes(raw),
            "raw_hex": raw.hex(),
            "held_path": str(held),
        }

    if attack == "wrong_bytes":
        attacked = _wrong_bytes(raw)
        _overwrite_fsynced(leaf, attacked)
        assert path_identity(leaf) == original_identity
        assert leaf.read_bytes() == attacked != raw
        if raw:
            assert len(attacked) == len(raw)
        return {
            "kind": attack,
            "identity": original_identity,
            "original_size": len(raw),
            "original_sha256": _sha256_bytes(raw),
            "original_hex": raw.hex(),
            "attacked_size": len(attacked),
            "attacked_sha256": _sha256_bytes(attacked),
            "attacked_hex": attacked.hex(),
        }

    assert attack == "unsafe_hardlink"
    peer = attack_root / "candidate-leaf-hardlink-peer"
    assert not peer.exists()
    os.link(leaf, peer)
    leaf_status = leaf.lstat()
    peer_status = peer.lstat()
    assert leaf_status.st_nlink == peer_status.st_nlink == 2
    assert path_identity(peer) == path_identity(leaf) == original_identity
    assert peer.read_bytes() == leaf.read_bytes() == raw
    return {
        "kind": attack,
        "identity": original_identity,
        "size": len(raw),
        "sha256": _sha256_bytes(raw),
        "raw_hex": raw.hex(),
        "peer_path": str(peer),
        "link_count": 2,
    }


def _candidate_parity_hard_kill_worker(
    session_root_text: str,
    oracle_path_text: str,
    attack_root_text: str,
    checkpoint: str,
    attack: str,
) -> None:
    session_root = Path(session_root_text)
    attack_root = Path(attack_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    counts, previous_profile = _start_apply_entry_observer()
    fired = False

    def hard_kill(point: LiveStartFaultPoint) -> None:
        nonlocal fired
        if point not in {_PRE_CAS, _POST_CAS}:
            return
        current = _load_worker_session(session_root)
        if not isinstance(current.publication_binding, Mapping):
            return
        output_root, package_root, source_root = _source_root(current)
        source = runtime_installer.snapshot_bounded_filesystem_package(source_root)
        source_files = source.file_names()
        assert source_files
        attack_relative_path = Path(source_files[0])
        recovery = current.apply_recovery
        if not isinstance(recovery, Mapping) or not _checkpoint_matches(
            checkpoint=checkpoint,
            point=point,
            recovery=recovery,
            attack_relative_path=attack_relative_path,
        ):
            return
        assert not fired
        fired = True
        runtime_root = Path(str(recovery["runtime_root"]))
        _assert_attack_root_is_external(
            attack_root,
            runtime_root=runtime_root,
            session_root=session_root,
            output_root=output_root,
            source_root=source_root,
        )
        candidate, target, leaf = _assert_checkpoint_semantics(
            checkpoint=checkpoint,
            current=current,
            recovery=recovery,
            runtime_root=runtime_root,
            attack_relative_path=attack_relative_path,
        )
        source_leaf = source_root / attack_relative_path
        assert source_leaf.is_file()
        assert source_leaf.read_bytes() == leaf.read_bytes()
        if checkpoint == "candidate_entry":
            assert path_identity(source_leaf) == tuple(
                recovery["candidate_tree_next_source_identity"]
            )
        completed_entries = int(recovery["candidate_tree_cursor"])
        if checkpoint == "candidate_entry":
            completed_entries += 1
        _assert_materialized_candidate_prefix(
            source_root=source_root,
            destination_root=candidate if checkpoint != "before_owner_bind" else target,
            completed_entries=completed_entries,
        )
        attack_tree_root = candidate if checkpoint != "before_owner_bind" else target
        membership_before = _physical_membership(attack_tree_root)
        source_tree_before = _runtime_tree(source_root, held_lock_path=None)
        attack_evidence = _apply_attack(
            attack=attack,
            leaf=leaf,
            attack_root=attack_root,
        )
        assert _physical_membership(attack_tree_root) == membership_before
        assert _runtime_tree(source_root, held_lock_path=None) == source_tree_before
        session_path = session_root / "session.json"
        invocation_path = session_root / "receipts" / "apply_invocation.json"
        admission_path = Path(str(recovery["runtime_admission_path"]))
        journal = _read_single_journal(runtime_root, str(recovery["apply_attempt_id"]))
        journal_path = runtime_transaction_journal_path(
            runtime_root,
            journal.transaction_id,
        )
        oracle: dict[str, object] = {
            "session_root": str(session_root),
            "checkpoint": checkpoint,
            "attack": attack_evidence,
            "fault_point": point.value,
            "apply_entry_counts": counts,
            "session_value": current.to_value(),
            "session_fingerprint": _file_fingerprint(session_path),
            "frozen_identity": _frozen_identity(current),
            "profile_fingerprint": _file_fingerprint(operator_profile_path()),
            "output_root": str(output_root),
            "package_root": str(package_root),
            "source_root": str(source_root),
            "publication_tree": _publication_tree_with_held_lock(output_root),
            "source_tree": source_tree_before,
            "runtime_root": str(runtime_root),
            "runtime_tree": _runtime_tree(
                runtime_root,
                held_lock_path=runtime_root / ".hsconfig" / "apply.lock",
            ),
            "runtime_apply_lock_metadata": _runtime_apply_lock_metadata(current),
            "invocation_fingerprint": _file_fingerprint(invocation_path),
            "runtime_admission_fingerprint": _file_fingerprint(admission_path),
            "candidate_path": str(candidate),
            "target_path": str(target),
            "leaf_path": str(leaf),
            "attack_relative_path": attack_relative_path.as_posix(),
            "attempt_id": str(recovery["apply_attempt_id"]),
            "journal_phase": journal.phase.value,
            "journal_path": str(journal_path),
            "journal_fingerprint": _file_fingerprint(journal_path),
            "retention_fingerprint": _file_fingerprint(
                Path(str(recovery["successor_attempt_record_path"]))
            ),
        }
        _persist_worker_oracle(Path(oracle_path_text), oracle)
        os._exit(_HARD_EXIT)

    try:
        controller._finalize_live_start(
            session_root=session_root,
            resume_intake=True,
            fault_hook=hard_kill,
        )
    finally:
        sys.setprofile(previous_profile)
    raise AssertionError(f"candidate parity checkpoint was not reached: {checkpoint}")


def _public_rejection_worker(
    session_root_text: str,
    oracle_path_text: str,
) -> None:
    session_root = Path(session_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    counts, terminal_hooks, selected_actions, previous_profile = (
        _start_public_continuation_observer(session_root)
    )
    error: ValueError | None = None
    try:
        try:
            controller.resume_live_start(session_root=session_root)
        except ValueError as caught:
            error = caught
    finally:
        sys.setprofile(previous_profile)
    if error is None:
        raise AssertionError(
            "public resume unexpectedly accepted candidate parity drift"
        )
    _persist_worker_oracle(
        Path(oracle_path_text),
        {
            "error_type": type(error).__name__,
            "error": str(error),
            "apply_entry_counts": counts,
            "terminal_hooks": terminal_hooks,
            "selected_actions": selected_actions,
            "session_fingerprint": _file_fingerprint(session_root / "session.json"),
        },
    )


def _terminal_negative_resume_worker(
    session_root_text: str,
    oracle_path_text: str,
) -> None:
    session_root = Path(session_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    counts, terminal_hooks, selected_actions, previous_profile = (
        _start_public_continuation_observer(session_root)
    )
    try:
        result = controller.resume_live_start(session_root=session_root)
        if not isinstance(result, controller.LiveStartResult):
            raise AssertionError("public resume did not return a terminal result")
        terminal = session.load_live_start_session(
            session_root,
            local_app_data_root=session_root.parents[2],
        )
    finally:
        sys.setprofile(previous_profile)
    _persist_worker_oracle(
        Path(oracle_path_text),
        {
            "status": result.status,
            "run_root": str(result.run_root),
            "summary_sha256": _sha256_bytes(result.summary.canonical_json),
            "session_sha256": terminal.content_sha256,
            "apply_entry_counts": counts,
            "terminal_hooks": terminal_hooks,
            "selected_actions": selected_actions,
        },
    )


def _start_public_continuation_observer(
    session_root: Path,
) -> tuple[dict[str, int], dict[str, int], list[str], Any]:
    counts, previous_profile = _start_apply_entry_observer()
    apply_observer = sys.getprofile()
    assert apply_observer is not None
    hooks = {
        "observation_before_selection": 0,
        "selection": 0,
    }
    selected_actions: list[str] = []

    def observe(frame: Any, event: str, arg: Any) -> None:
        apply_observer(frame, event, arg)
        if event != "call" or frame.f_code is not no_live_start_fault.__code__:
            return
        point = frame.f_locals.get("_point")
        if point is (
            LiveStartFaultPoint.AFTER_TERMINAL_CLASSIFICATION_OBSERVATION_BEFORE_SELECTION_CAS
        ):
            hooks["observation_before_selection"] += 1
        elif point is LiveStartFaultPoint.AFTER_TERMINAL_CLASSIFICATION_SELECTION_CAS:
            hooks["selection"] += 1
            current = _load_worker_session(session_root)
            recovery = current.apply_recovery
            assert isinstance(recovery, Mapping)
            selected_actions.append(str(recovery["expected_action"]))

    sys.setprofile(observe)
    return counts, hooks, selected_actions, previous_profile


def _load_oracle(path: Path) -> dict[str, object]:
    value = json.loads(path.read_bytes())
    assert isinstance(value, dict)
    return value


def _assert_fingerprint(path: Path, value: object) -> None:
    assert _file_fingerprint(path) == _json_fingerprint(value)


def _assert_common_kill_state(
    *,
    prepared: Any,
    oracle: Mapping[str, Any],
) -> session.LiveStartSession:
    assert oracle["apply_entry_counts"] == _expected_apply_entry_counts(
        fresh=1,
        install_prepare=1,
        attempt_prepare=1,
    )
    runtime_root = Path(str(oracle["runtime_root"]))
    _assert_tree_after_exit(
        runtime_root=runtime_root,
        snapshot={"tree": oracle["runtime_tree"]},
    )
    lock_metadata = oracle["runtime_apply_lock_metadata"]
    assert isinstance(lock_metadata, list)
    assert _file_fingerprint(runtime_root / ".hsconfig" / "apply.lock") == (
        tuple(lock_metadata[0]),
        0,
        _sha256_bytes(b""),
    )
    current = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    assert current.to_value() == oracle["session_value"]
    _assert_fingerprint(
        prepared.run_root / "session.json",
        oracle["session_fingerprint"],
    )
    assert _frozen_identity(current) == oracle["frozen_identity"]
    assert current.apply_invocation_sha256 is not None
    invocation_path = prepared.run_root / "receipts" / "apply_invocation.json"
    invocation = load_apply_invocation(invocation_path)
    assert invocation.apply_attempt_id == oracle["attempt_id"]
    assert invocation.content_sha256 == current.apply_invocation_sha256
    _assert_fingerprint(invocation_path, oracle["invocation_fingerprint"])
    admission = load_runtime_live_attempt_admission()
    assert admission is not None
    assert admission.apply_attempt_id == oracle["attempt_id"]
    _assert_fingerprint(
        admission.admission_path,
        oracle["runtime_admission_fingerprint"],
    )
    _assert_fingerprint(operator_profile_path(), oracle["profile_fingerprint"])
    assert (
        _runtime_tree(Path(str(oracle["output_root"])), held_lock_path=None)
        == oracle["publication_tree"]
    )
    assert (
        _runtime_tree(Path(str(oracle["source_root"])), held_lock_path=None)
        == oracle["source_tree"]
    )
    journal = _read_single_journal(runtime_root, str(oracle["attempt_id"]))
    assert journal.phase.value == oracle["journal_phase"]
    _assert_fingerprint(
        runtime_transaction_journal_path(runtime_root, journal.transaction_id),
        oracle["journal_fingerprint"],
    )
    recovery = current.apply_recovery
    assert isinstance(recovery, Mapping)
    _assert_fingerprint(
        Path(str(recovery["successor_attempt_record_path"])),
        oracle["retention_fingerprint"],
    )
    return current


def _assert_public_authority_unchanged(oracle: Mapping[str, Any]) -> None:
    _assert_fingerprint(
        Path(str(oracle["session_root"])) / "receipts/apply_invocation.json",
        oracle["invocation_fingerprint"],
    )
    _assert_fingerprint(operator_profile_path(), oracle["profile_fingerprint"])
    assert (
        _runtime_tree(Path(str(oracle["output_root"])), held_lock_path=None)
        == oracle["publication_tree"]
    )
    assert (
        _runtime_tree(Path(str(oracle["source_root"])), held_lock_path=None)
        == oracle["source_tree"]
    )


def _assert_terminal_result_evidence(
    *,
    session_root: Path,
    terminal: session.LiveStartSession,
    resume_oracle: Mapping[str, Any],
    attempt_id: str,
) -> None:
    assert resume_oracle["run_root"] == str(session_root)
    assert resume_oracle["session_sha256"] == terminal.content_sha256
    intent = terminal.result_intent
    assert isinstance(intent, Mapping)
    assert intent["apply_attempt_id"] == attempt_id
    for name in ("summary.json", "summary.md"):
        path = session_root / "result" / name
        raw = path.read_bytes()
        assert terminal.artifact_bindings[f"result/{name}"] == _sha256_bytes(raw)
    assert resume_oracle["summary_sha256"] == _sha256_bytes(
        (session_root / "result" / "summary.json").read_bytes()
    )


def _assert_no_committed_runtime_payload(runtime_root: Path) -> None:
    assert not (runtime_root / "CustomConfig" / "deck_config.ini").exists()
    assert not (runtime_root / ".hsconfig" / "state.json").exists()
    receipts = runtime_root / ".hsconfig" / "receipts"
    assert receipts.is_dir()
    assert not tuple(path for path in receipts.rglob("*") if path.is_file())


def _assert_retained_negative_evidence(
    *,
    carrier: Mapping[str, Any],
    oracle: Mapping[str, Any],
) -> None:
    killed_recovery = oracle["session_value"]["apply_recovery"]
    assert isinstance(killed_recovery, Mapping)
    if carrier.get("recovery_stage") == "CLOSED":
        prefixes = ("predecessor_attempt_record", "predecessor_journal")
    else:
        assert carrier.get("intent_kind") == session.LIVE_START_RESULT_INTENT_KIND
        prefixes = ("retained_attempt_record", "retained_journal")
    for prefix, oracle_key, expected_path in (
        (
            prefixes[0],
            "retention_fingerprint",
            killed_recovery["successor_attempt_record_path"],
        ),
        (
            prefixes[1],
            "journal_fingerprint",
            oracle["journal_path"],
        ),
    ):
        fingerprint = _json_fingerprint(oracle[oracle_key])
        path = Path(str(carrier[f"{prefix}_path"]))
        assert path == Path(str(expected_path))
        assert tuple(carrier[f"{prefix}_identity"]) == fingerprint[0]
        assert carrier[f"{prefix}_sha256"] == fingerprint[2]
        assert _file_fingerprint(path) == fingerprint


def _assert_canonical_live_runtime(
    *,
    runtime_root: Path,
    source_root: Path,
    target: Path,
    owner: Any,
    intent: Mapping[str, Any],
) -> None:
    target_relative = target.relative_to(runtime_root).as_posix()
    expected_kinds = dict.fromkeys(
        (
            ".",
            "CustomConfig",
            ".hsconfig",
            ".hsconfig/transactions",
            ".hsconfig/staging",
            ".hsconfig/receipts",
            f".hsconfig/receipts/{owner.state_key}",
            ".hsconfig/attempt-retention",
            ".hsconfig/owner-retirements",
        ),
        "directory",
    )
    expected_kinds.update(
        dict.fromkeys(
            (
                "CustomConfig/deck_config.ini",
                ".hsconfig/apply.lock",
                ".hsconfig/state.json",
                f".hsconfig/transactions/{owner.transaction_id}.json",
                f".hsconfig/receipts/{owner.state_key}/last_apply_receipt.json",
            ),
            "file",
        )
    )
    source_tree = _runtime_tree(source_root, held_lock_path=None)
    for relative, row in source_tree.items():
        member = target_relative if relative == "." else f"{target_relative}/{relative}"
        expected_kinds[member] = str(row["kind"])
    runtime_tree = _runtime_tree(runtime_root, held_lock_path=None)
    assert {
        relative: str(row["kind"]) for relative, row in runtime_tree.items()
    } == expected_kinds
    assert runtime_tree[".hsconfig/apply.lock"]["size"] == 0
    assert runtime_tree[".hsconfig/apply.lock"]["sha256"] == _sha256_bytes(b"")
    assert not tuple((runtime_root / ".hsconfig" / "staging").iterdir())
    assert not tuple((runtime_root / ".hsconfig" / "attempt-retention").iterdir())
    control_paths = {
        "deck_config_ini_sha256": runtime_root / "CustomConfig" / "deck_config.ini",
        "runtime_state_sha256": runtime_root / ".hsconfig" / "state.json",
        "last_apply_receipt_sha256": (
            runtime_root
            / ".hsconfig"
            / "receipts"
            / owner.state_key
            / "last_apply_receipt.json"
        ),
    }
    for intent_key, path in control_paths.items():
        assert _file_fingerprint(path)[2] == intent[intent_key]


def _prepare_case(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Any, Any, Path, Path]:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "pipeline", monkeypatch)
    attack_root = tmp_path / "candidate-parity-attack"
    attack_root.mkdir()
    oracle_path = tmp_path / "candidate-parity-kill-oracle.json"
    return fixture, prepared, attack_root, oracle_path


def _require_hardlink_support(attack_root: Path) -> None:
    source = attack_root / "hardlink-probe-source"
    peer = attack_root / "hardlink-probe-peer"
    _write_fsynced(source, b"candidate-parity-hardlink-probe")
    try:
        os.link(source, peer)
    except OSError as error:
        source.unlink()
        pytest.skip(f"plain hard-link creation is unavailable: {error}")
    assert path_identity(peer) == path_identity(source)
    peer.unlink()
    source.unlink()


def test_candidate_leaf_pre_cas_safe_same_bytes_new_identity_resumes_same_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture, prepared, attack_root, oracle_path = _prepare_case(
        tmp_path,
        monkeypatch,
    )
    _spawn_and_join(
        target=_candidate_parity_hard_kill_worker,
        args=(
            str(prepared.run_root),
            str(oracle_path),
            str(attack_root),
            "candidate_entry",
            "safe_same_bytes_new_identity",
        ),
        expected_exitcode=_HARD_EXIT,
        timeout_seconds=360,
    )
    oracle = _load_oracle(oracle_path)
    _assert_common_kill_state(prepared=prepared, oracle=oracle)
    attack = oracle["attack"]
    assert isinstance(attack, Mapping)
    held = Path(str(attack["held_path"]))
    _assert_fingerprint(
        held,
        [attack["original_identity"], attack["size"], attack["sha256"]],
    )
    replacement_identity = tuple(attack["replacement_identity"])
    assert replacement_identity != tuple(attack["original_identity"])

    resume_oracle_path = tmp_path / "candidate-parity-resume-oracle.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(resume_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    resume_oracle = _load_oracle(resume_oracle_path)
    assert resume_oracle["status"] == "LIVE_AND_MATCHED"
    assert resume_oracle["apply_entry_counts"] == _expected_apply_entry_counts(
        recovery=1,
    )
    terminal = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    intent = terminal.result_intent
    assert terminal.terminal_status == "LIVE_AND_MATCHED"
    assert _frozen_identity(terminal) == oracle["frozen_identity"]
    assert terminal.apply_recovery is None
    assert terminal.closed_apply_recovery_commitment is None
    assert isinstance(intent, Mapping)
    assert intent["apply_attempt_id"] == oracle["attempt_id"]
    assert intent["physical_disposition"] == "COMMITTED"
    assert intent["runtime_match_status"] == "matched"
    assert intent["error_code"] is None
    for field in (
        "runtime_layout_bootstrap",
        "terminal_retirement",
        "attempt_acknowledgement",
    ):
        binding = getattr(terminal, field)
        assert isinstance(binding, Mapping)
        assert binding["apply_attempt_id"] == oracle["attempt_id"]
    _assert_terminal_result_evidence(
        session_root=prepared.run_root,
        terminal=terminal,
        resume_oracle=resume_oracle,
        attempt_id=str(oracle["attempt_id"]),
    )
    output_root, package_root, target = _matched_package(fixture)
    assert output_root == Path(str(oracle["output_root"]))
    assert package_root == Path(str(oracle["package_root"]))
    target_leaf = target / Path(str(oracle["attack_relative_path"]))
    assert path_identity(target_leaf) == replacement_identity
    assert _file_fingerprint(target_leaf) == (
        replacement_identity,
        int(attack["size"]),
        str(attack["sha256"]),
    )
    assert _file_fingerprint(held) == (
        tuple(attack["original_identity"]),
        int(attack["size"]),
        str(attack["sha256"]),
    )
    assert (
        held.read_bytes()
        == target_leaf.read_bytes()
        == bytes.fromhex(str(attack["raw_hex"]))
    )
    assert not Path(str(oracle["candidate_path"])).exists()
    journal = _read_single_journal(
        fixture.profile.runtime_root, str(oracle["attempt_id"])
    )
    assert journal.phase is RuntimeTransactionPhase.FINALIZED
    assert journal.owns_target is True
    assert fixture.profile.runtime_root / journal.target_path == target
    assert path_identity(target) == tuple(journal.target_identity)
    _assert_canonical_live_runtime(
        runtime_root=fixture.profile.runtime_root,
        source_root=Path(str(oracle["source_root"])),
        target=target,
        owner=journal,
        intent=intent,
    )
    assert load_runtime_live_attempt_admission() is None
    _assert_public_authority_unchanged(oracle)

    session_before = _runtime_tree(prepared.run_root, held_lock_path=None)
    runtime_before = _runtime_tree(fixture.profile.runtime_root, held_lock_path=None)
    replay_oracle_path = tmp_path / "candidate-parity-replay-oracle.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(replay_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    replay_oracle = _load_oracle(replay_oracle_path)
    assert replay_oracle["status"] == "LIVE_AND_MATCHED"
    assert replay_oracle["apply_entry_counts"] == _expected_apply_entry_counts()
    replay_without_counts = dict(replay_oracle)
    resume_without_counts = dict(resume_oracle)
    replay_without_counts.pop("apply_entry_counts")
    resume_without_counts.pop("apply_entry_counts")
    assert replay_without_counts == resume_without_counts
    assert _runtime_tree(prepared.run_root, held_lock_path=None) == session_before
    assert (
        _runtime_tree(fixture.profile.runtime_root, held_lock_path=None)
        == runtime_before
    )
    _assert_public_authority_unchanged(oracle)


@pytest.mark.parametrize("attack_kind", ("wrong_bytes", "unsafe_hardlink"))
def test_candidate_leaf_pre_cas_rejects_wrong_bytes_or_unsafe_hardlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    attack_kind: str,
) -> None:
    _fixture, prepared, attack_root, oracle_path = _prepare_case(
        tmp_path,
        monkeypatch,
    )
    if attack_kind == "unsafe_hardlink":
        _require_hardlink_support(attack_root)
    _spawn_and_join(
        target=_candidate_parity_hard_kill_worker,
        args=(
            str(prepared.run_root),
            str(oracle_path),
            str(attack_root),
            "candidate_entry",
            attack_kind,
        ),
        expected_exitcode=_HARD_EXIT,
        timeout_seconds=360,
    )
    oracle = _load_oracle(oracle_path)
    interrupted = _assert_common_kill_state(prepared=prepared, oracle=oracle)
    interrupted_recovery = interrupted.apply_recovery
    assert isinstance(interrupted_recovery, Mapping)
    assert interrupted_recovery["expected_action"] == (
        "materialize_candidate_tree_entry"
    )
    assert interrupted_recovery["candidate_tree_next_successor_identity"] is None

    resume_oracle_path = tmp_path / "candidate-parity-negative-resume.json"
    _spawn_and_join(
        target=_terminal_negative_resume_worker,
        args=(str(prepared.run_root), str(resume_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    resume_oracle = _load_oracle(resume_oracle_path)
    assert resume_oracle["status"] == "APPLIED_BUT_NOT_VERIFIED"
    assert resume_oracle["apply_entry_counts"] == _expected_apply_entry_counts(
        recovery=1,
    )
    assert resume_oracle["terminal_hooks"] == {
        "observation_before_selection": 1,
        "selection": 1,
    }
    assert resume_oracle["selected_actions"] == ["observe_pending"]
    terminal = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    intent = terminal.result_intent
    closed = terminal.closed_apply_recovery_commitment
    assert terminal.phase is session.LiveStartPhase.APPLY_STARTED
    assert terminal.terminal_status == "APPLIED_BUT_NOT_VERIFIED"
    assert _frozen_identity(terminal) == oracle["frozen_identity"]
    assert terminal.apply_recovery is None
    assert terminal.pending_transition is None
    assert terminal.attempt_acknowledgement is None
    assert terminal.terminal_retirement is None
    assert isinstance(intent, Mapping)
    assert isinstance(closed, Mapping)
    assert closed["recovery_stage"] == "CLOSED"
    assert closed["apply_attempt_id"] == oracle["attempt_id"]
    assert closed["stable_physical_disposition"] == ("COMMITTED_RECOVERY_PENDING")
    assert closed["runtime_match_status"] == "not_run"
    assert intent["apply_attempt_id"] == oracle["attempt_id"]
    assert intent["physical_disposition"] == "COMMITTED_RECOVERY_PENDING"
    assert intent["raw_apply_status"] == "committed_receipt_pending"
    assert intent["runtime_match_status"] == "not_run"
    assert intent["error_code"] == "apply_recovery_pending"
    _assert_retained_negative_evidence(carrier=closed, oracle=oracle)
    _assert_retained_negative_evidence(carrier=intent, oracle=oracle)
    _assert_terminal_result_evidence(
        session_root=prepared.run_root,
        terminal=terminal,
        resume_oracle=resume_oracle,
        attempt_id=str(oracle["attempt_id"]),
    )
    admission = load_runtime_live_attempt_admission()
    assert admission is not None
    assert admission.apply_attempt_id == oracle["attempt_id"]
    _assert_fingerprint(
        admission.admission_path,
        oracle["runtime_admission_fingerprint"],
    )
    _assert_tree_after_exit(
        runtime_root=Path(str(oracle["runtime_root"])),
        snapshot={"tree": oracle["runtime_tree"]},
    )
    journal = _read_single_journal(
        Path(str(oracle["runtime_root"])), str(oracle["attempt_id"])
    )
    assert journal.phase is RuntimeTransactionPhase.PREPARED
    _assert_fingerprint(
        runtime_transaction_journal_path(
            Path(str(oracle["runtime_root"])),
            journal.transaction_id,
        ),
        oracle["journal_fingerprint"],
    )
    candidate = Path(str(oracle["candidate_path"]))
    target = Path(str(oracle["target_path"]))
    leaf = Path(str(oracle["leaf_path"]))
    attack = oracle["attack"]
    assert isinstance(attack, Mapping)
    assert candidate.is_dir()
    assert not target.exists()
    _assert_no_committed_runtime_payload(Path(str(oracle["runtime_root"])))
    if attack_kind == "wrong_bytes":
        assert _file_fingerprint(leaf) == (
            tuple(attack["identity"]),
            int(attack["attacked_size"]),
            str(attack["attacked_sha256"]),
        )
        assert leaf.read_bytes() == bytes.fromhex(str(attack["attacked_hex"]))
    else:
        peer = Path(str(attack["peer_path"]))
        assert path_identity(leaf) == path_identity(peer) == tuple(attack["identity"])
        assert leaf.lstat().st_nlink == peer.lstat().st_nlink == 2
        assert (
            leaf.read_bytes()
            == peer.read_bytes()
            == bytes.fromhex(str(attack["raw_hex"]))
        )
    _assert_public_authority_unchanged(oracle)


@pytest.mark.parametrize(
    "checkpoint",
    ("before_rename", "before_owner_bind"),
)
def test_candidate_complete_parity_reread_rejects_wrong_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    checkpoint: str,
) -> None:
    _fixture, prepared, attack_root, oracle_path = _prepare_case(
        tmp_path,
        monkeypatch,
    )
    _spawn_and_join(
        target=_candidate_parity_hard_kill_worker,
        args=(
            str(prepared.run_root),
            str(oracle_path),
            str(attack_root),
            checkpoint,
            "wrong_bytes",
        ),
        expected_exitcode=_HARD_EXIT,
        timeout_seconds=360,
    )
    oracle = _load_oracle(oracle_path)
    interrupted = _assert_common_kill_state(prepared=prepared, oracle=oracle)
    interrupted_recovery = interrupted.apply_recovery
    assert isinstance(interrupted_recovery, Mapping)
    expected_action = {
        "before_rename": "rename_candidate_to_target",
        "before_owner_bind": "bind_renamed_target",
    }[checkpoint]
    assert interrupted_recovery["expected_action"] == expected_action
    session_at_kill = (prepared.run_root / "session.json").read_bytes()

    rejection_oracle_path = tmp_path / "candidate-parity-rejection.json"
    _spawn_and_join(
        target=_public_rejection_worker,
        args=(str(prepared.run_root), str(rejection_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    rejection = _load_oracle(rejection_oracle_path)
    assert rejection["error_type"] == "ValueError"
    assert rejection["error"] == "runtime_new_target_precommit_authority_invalid"
    assert rejection["apply_entry_counts"] == _expected_apply_entry_counts(
        recovery=1,
    )
    assert rejection["terminal_hooks"] == {
        "observation_before_selection": 0,
        "selection": 0,
    }
    assert rejection["selected_actions"] == []
    assert (prepared.run_root / "session.json").read_bytes() == session_at_kill
    assert rejection["session_fingerprint"] == oracle["session_fingerprint"]
    current = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    assert current.to_value() == oracle["session_value"]
    assert current.phase is session.LiveStartPhase.APPLY_STARTED
    assert current.terminal_status is None
    assert current.result_intent is None
    assert current.attempt_acknowledgement is None
    assert current.terminal_retirement is None
    assert not (prepared.run_root / "result" / "summary.json").exists()
    assert not (prepared.run_root / "result" / "summary.md").exists()
    _assert_no_committed_runtime_payload(Path(str(oracle["runtime_root"])))
    admission = load_runtime_live_attempt_admission()
    assert admission is not None
    assert admission.apply_attempt_id == oracle["attempt_id"]
    _assert_fingerprint(
        admission.admission_path,
        oracle["runtime_admission_fingerprint"],
    )
    _assert_tree_after_exit(
        runtime_root=Path(str(oracle["runtime_root"])),
        snapshot={"tree": oracle["runtime_tree"]},
    )
    journal = _read_single_journal(
        Path(str(oracle["runtime_root"])), str(oracle["attempt_id"])
    )
    assert journal.phase is RuntimeTransactionPhase.RUNTIME_VERIFIED
    _assert_fingerprint(
        runtime_transaction_journal_path(
            Path(str(oracle["runtime_root"])),
            journal.transaction_id,
        ),
        oracle["journal_fingerprint"],
    )
    attack = oracle["attack"]
    assert isinstance(attack, Mapping)
    leaf = Path(str(oracle["leaf_path"]))
    assert _file_fingerprint(leaf) == (
        tuple(attack["identity"]),
        int(attack["attacked_size"]),
        str(attack["attacked_sha256"]),
    )
    assert leaf.read_bytes() == bytes.fromhex(str(attack["attacked_hex"]))
    candidate = Path(str(oracle["candidate_path"]))
    target = Path(str(oracle["target_path"]))
    if checkpoint == "before_rename":
        assert candidate.is_dir()
        assert leaf.is_relative_to(candidate)
        assert not target.exists()
    else:
        assert not candidate.exists()
        assert target.is_dir()
        assert leaf.is_relative_to(target)
        external = interrupted_recovery["external_file_action"]
        assert isinstance(external, Mapping)
        staging = Path(str(external["staging_path"]))
        assert path_identity(staging) == tuple(external["staging_identity"])
        assert _sha256_bytes(staging.read_bytes()) == external["staging_sha256"]
    _assert_public_authority_unchanged(oracle)
