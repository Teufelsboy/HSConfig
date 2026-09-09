from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from typing import Any
import uuid

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig import runtime_installer as runtime_apply
from hsconfig.apply_invocation import load_apply_invocation
from hsconfig.deck_config_ini import read_deck_config, render_deck_config
from hsconfig.io import slugify_deck_name
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.operator_profile import derive_deck_output_binding, operator_profile_path
from hsconfig.package_io import path_identity
from hsconfig.runtime_live_admission import load_runtime_live_attempt_admission
from hsconfig.runtime_transaction_journal import (
    RuntimeTransactionJournal,
    RuntimeTransactionPhase,
    load_runtime_transaction_journals,
    read_runtime_transaction_journal,
    runtime_transaction_journal_path,
    write_runtime_transaction_journal,
)
from tests.test_codex_first_live_e2e import (
    _local_state,
    _matched_package,
    _prepare_approved,
)
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
from tests.test_controller_runtime_action_chain import (
    _assert_tree_after_exit,
    _load_worker_session,
    _runtime_tree,
)


_PRE_CAS = (
    LiveStartFaultPoint.AFTER_NONTERMINAL_RECOVERY_PHYSICAL_STEP_BEFORE_CURSOR_CAS
)
_POST_CAS = LiveStartFaultPoint.AFTER_NONTERMINAL_RECOVERY_CURSOR_CAS
_HARD_EXIT = 93
_INITIALIZE = "initialize_owner_cleanup_journal"
_RETIRE_ROOT = "retire_owner_target_root"
_DELETE_ENTRY = "delete_owner_cleanup_entry"
_ADVANCE_JOURNAL = "advance_owner_cleanup_journal"
_RESULT_NAMES = ("summary.json", "summary.md")


@dataclass(frozen=True, slots=True)
class _LegacyOwner:
    journal: RuntimeTransactionJournal
    journal_path: Path
    journal_fingerprint: tuple[tuple[int, int, int], int, str]
    target_path: Path
    target_identity: tuple[int, int, int]
    target_tree: dict[str, tuple[str, tuple[int, int, int], bytes | None]]
    runtime_tree: dict[str, tuple[str, tuple[int, int, int], bytes | None]]
    ini_fingerprint: tuple[tuple[int, int, int], int, str]
    state_fingerprint: tuple[tuple[int, int, int], int, str]
    receipt_fingerprint: tuple[tuple[int, int, int], int, str]


def _write_fsynced(path: Path, raw: bytes) -> None:
    with path.open("xb") as handle:
        assert handle.write(raw) == len(raw)
        handle.flush()
        os.fsync(handle.fileno())


def _fingerprint_value(
    fingerprint: tuple[tuple[int, int, int], int, str],
) -> list[object]:
    return [list(fingerprint[0]), fingerprint[1], fingerprint[2]]


def _result_pair(
    session_root: Path,
) -> dict[str, tuple[tuple[int, int, int], bytes]]:
    return {
        name: (
            path_identity(session_root / "result" / name),
            (session_root / "result" / name).read_bytes(),
        )
        for name in _RESULT_NAMES
    }


def _owner_parts(
    current: session.LiveStartSession,
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any] | None]:
    recovery = current.apply_recovery
    if not isinstance(recovery, Mapping):
        raise AssertionError("runtime recovery is absent")
    owner = recovery.get("owner_retirement")
    if not isinstance(owner, Mapping):
        raise AssertionError("owner-retirement cursor is absent")
    external = recovery.get("external_file_action")
    if external is not None and not isinstance(external, Mapping):
        raise AssertionError("external file action is invalid")
    return recovery, owner, external


def _owner_action(current: session.LiveStartSession) -> str:
    _recovery, owner, external = _owner_parts(current)
    return session._owner_action_for_cursor(owner=owner, external=external)


def _plain_fingerprint(path: Path) -> tuple[tuple[int, int, int], int, str]:
    fingerprint = _file_fingerprint(path)
    assert fingerprint is not None
    return fingerprint


def _seed_legacy_zero_entry_owner(
    *,
    runtime_root: Path,
    deck_name: str,
) -> _LegacyOwner:
    # The hand-authored boundary is only historical Runtime authority.  Public
    # recovery validates it before the controller under test is allowed to run.
    assert runtime_apply.recover_runtime_state(runtime_root) is None
    logical = slugify_deck_name(deck_name)
    entries = runtime_apply._collect_owner_retirement_cleanup_entries
    package_digest = runtime_apply._owner_retirement_package_digest(())
    target_name = f"{logical}--sha256-{package_digest}"
    target_path = runtime_root / "CustomConfig" / target_name
    target_path.mkdir()
    target_identity = path_identity(target_path)
    assert entries(target_path) == ()
    assert runtime_apply._owner_retirement_package_digest(entries(target_path)) == (
        package_digest
    )

    ini_path = runtime_root / "CustomConfig" / "deck_config.ini"
    absent = read_deck_config(ini_path, deck_name=deck_name)
    assert absent.existed is False
    ini_raw = render_deck_config(
        absent,
        deck_name=deck_name,
        config_dir=target_name,
    )
    _write_fsynced(ini_path, ini_raw)
    selected = read_deck_config(ini_path, deck_name=deck_name)
    assert selected.content == ini_raw
    assert selected.selected_config_dir == target_name

    transaction_id = uuid.uuid4().hex
    state_key = runtime_apply._state_key(deck_name)
    journal = RuntimeTransactionJournal(
        schema_version=1,
        transaction_id=transaction_id,
        deck_name=deck_name,
        source_manifest_sha256=sha256(
            b"task13-zero-entry-unavailable-legacy-manifest"
        ).hexdigest(),
        state_key=state_key,
        logical_config_dir=logical,
        package_root_sha256=package_digest,
        candidate_path=f".hsconfig/staging/{transaction_id}",
        target_path=f"CustomConfig/{target_name}",
        candidate_identity=target_identity,
        target_identity=target_identity,
        owns_target=True,
        previous_config_dir=None,
        next_config_dir=target_name,
        previous_ini_sha256=None,
        next_ini_sha256=sha256(ini_raw).hexdigest(),
        phase=RuntimeTransactionPhase.FINALIZED,
    )
    journal_path = runtime_transaction_journal_path(runtime_root, transaction_id)
    write_runtime_transaction_journal(journal_path, journal)
    assert read_runtime_transaction_journal(journal_path) == journal
    journal_fingerprint = _plain_fingerprint(journal_path)

    accepted = runtime_apply.recover_runtime_state(runtime_root)
    assert accepted is not None
    assert len(accepted.decks) == 1
    accepted_deck = accepted.decks[0]
    assert accepted_deck.state_key == state_key
    assert accepted_deck.deck_name == deck_name
    assert accepted_deck.config_dir == target_name
    assert accepted_deck.package_root_sha256 == package_digest
    assert accepted_deck.ini_sha256 == sha256(ini_raw).hexdigest()
    assert read_runtime_transaction_journal(journal_path) == journal
    assert path_identity(target_path) == target_identity
    assert entries(target_path) == ()

    state_path = runtime_root / ".hsconfig" / "state.json"
    receipt_path = runtime_apply._receipt_path(runtime_root, state_key)
    ini_fingerprint = _plain_fingerprint(ini_path)
    state_fingerprint = _plain_fingerprint(state_path)
    receipt_fingerprint = _plain_fingerprint(receipt_path)
    assert load_runtime_transaction_journals(runtime_root) == (journal,)
    return _LegacyOwner(
        journal=journal,
        journal_path=journal_path,
        journal_fingerprint=journal_fingerprint,
        target_path=target_path,
        target_identity=target_identity,
        target_tree=_physical_tree(target_path),
        runtime_tree=_physical_tree(runtime_root),
        ini_fingerprint=ini_fingerprint,
        state_fingerprint=state_fingerprint,
        receipt_fingerprint=receipt_fingerprint,
    )


def _action_counts() -> dict[str, dict[str, int]]:
    return {
        boundary: {
            action: 0
            for action in (
                _INITIALIZE,
                _RETIRE_ROOT,
                _DELETE_ENTRY,
                _ADVANCE_JOURNAL,
            )
        }
        for boundary in ("pre", "post")
    }


def _worker_snapshot(
    current: session.LiveStartSession,
    *,
    output_root: Path,
    invocation_path: Path,
    action_counts: Mapping[str, object],
) -> dict[str, object]:
    recovery, owner, _external = _owner_parts(current)
    layout = current.runtime_layout_bootstrap
    admission = current.runtime_admission_binding
    assert isinstance(layout, Mapping)
    assert isinstance(admission, Mapping)
    runtime_root = Path(str(layout["runtime_root"]))
    apply_lock = runtime_root / ".hsconfig" / "apply.lock"
    admission_path = Path(str(admission["admission_path"]))
    successor_owner = Path(str(owner["successor_owner_journal_path"]))
    successor_target = Path(str(recovery["renamed_target_path"]))
    output_tree = _runtime_tree(
        output_root, held_lock_path=output_root / ".publish.lock"
    )
    # _runtime_tree verifies this held lock is a plain, single-link, empty file.
    output_tree[".publish.lock"]["sha256"] = "sha256:" + sha256(b"").hexdigest()
    return {
        "session": current.to_value(),
        "frozen_identity": _frozen_identity(current),
        "runtime_tree": _runtime_tree(runtime_root, held_lock_path=apply_lock),
        "output_tree": output_tree,
        "profile_fingerprint": _plain_fingerprint(operator_profile_path()),
        "invocation_fingerprint": _plain_fingerprint(invocation_path),
        "admission_fingerprint": _plain_fingerprint(admission_path),
        "successor_owner_fingerprint": _plain_fingerprint(successor_owner),
        "successor_target_identity": path_identity(successor_target),
        "successor_target_tree": _runtime_tree(
            successor_target,
            held_lock_path=None,
        ),
        "action_counts": action_counts,
        "apply_attempt_id": recovery["apply_attempt_id"],
    }


def _zero_entry_hard_kill_worker(
    session_root_text: str,
    output_root_text: str,
    invocation_path_text: str,
    old_journal_path_text: str,
    old_target_path_text: str,
    checkpoint: str,
    oracle_path_text: str,
) -> None:
    session_root = Path(session_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    output_root = Path(output_root_text)
    invocation_path = Path(invocation_path_text)
    old_journal_path = Path(old_journal_path_text)
    old_target_path = Path(old_target_path_text)
    start = _load_worker_session(session_root)
    counts, previous_profile = _start_apply_entry_observer()
    actions = _action_counts()
    last_pre: str | None = None
    initialization_successor: dict[str, object] | None = None

    def hard_kill(point: LiveStartFaultPoint) -> None:
        nonlocal last_pre, initialization_successor
        if point not in {_PRE_CAS, _POST_CAS}:
            return
        current = _load_worker_session(session_root)
        try:
            action = _owner_action(current)
        except AssertionError:
            return
        if point is _PRE_CAS:
            last_pre = action
            if action in actions["pre"]:
                actions["pre"][action] += 1
        else:
            if last_pre in actions["post"]:
                actions["post"][last_pre] += 1
            if last_pre == _INITIALIZE:
                session._validate_owner_retirement_successor(
                    predecessor=start.apply_recovery,
                    successor=current.apply_recovery,
                    action=_INITIALIZE,
                )
                initialization_successor = current.to_value()

        selected = False
        if checkpoint == "initialization_pre":
            selected = point is _PRE_CAS and action == _INITIALIZE
        elif checkpoint == "root_pre":
            selected = point is _PRE_CAS and action == _RETIRE_ROOT
        elif checkpoint == "root_post":
            selected = point is _POST_CAS and last_pre == _RETIRE_ROOT
        else:
            raise AssertionError("unknown zero-entry checkpoint")
        if not selected:
            return

        recovery, owner, external = _owner_parts(current)
        assert owner["cleanup_entry_count"] == 0
        assert owner["cleanup_cursor"] == 0
        assert owner["next_entry_relative_path"] is None
        assert owner["next_entry_kind"] is None
        assert actions["pre"][_DELETE_ENTRY] == 0
        assert actions["post"][_DELETE_ENTRY] == 0
        assert actions["pre"][_ADVANCE_JOURNAL] == 0
        assert actions["post"][_ADVANCE_JOURNAL] == 0
        if checkpoint == "initialization_pre":
            assert owner["stage"] == "PREPARED"
            assert isinstance(external, Mapping)
            assert external["action_kind"] == _INITIALIZE
            assert external["stage"] == "STAGING_BOUND"
            assert os.path.lexists(old_target_path)
        elif checkpoint == "root_pre":
            assert initialization_successor is not None
            assert owner["stage"] == "CLEANING"
            assert recovery["expected_action"] == _RETIRE_ROOT
            assert external is None
            assert not os.path.lexists(old_target_path)
        else:
            assert owner["stage"] == "TARGET_RETIRED"
            assert recovery["expected_action"] == "materialize_file_action_staging"
            assert isinstance(external, Mapping)
            assert external["action_kind"] == "commit_owner_retirement_completed"
            assert external["stage"] == "PLANNED"
            assert not os.path.lexists(old_target_path)
        old_journal_fingerprint = _plain_fingerprint(old_journal_path)
        snapshot = _worker_snapshot(
            current,
            output_root=output_root,
            invocation_path=invocation_path,
            action_counts=actions,
        )
        snapshot.update(
            {
                "checkpoint": checkpoint,
                "fault_value": point.value,
                "apply_entry_counts": counts,
                "start_session": start.to_value(),
                "initialization_successor": initialization_successor,
                "old_journal_fingerprint": old_journal_fingerprint,
            }
        )
        _persist_worker_oracle(Path(oracle_path_text), snapshot)
        os._exit(_HARD_EXIT)

    try:
        controller._finalize_live_start(
            session_root=session_root,
            resume_intake=True,
            fault_hook=hard_kill,
        )
    finally:
        sys.setprofile(previous_profile)
    os._exit(_HARD_EXIT + 1)


def _load_oracle(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    assert isinstance(value, dict)
    return value


def _runtime_projection(
    tree: Mapping[str, object],
    *,
    mutable_paths: tuple[str, ...],
) -> dict[str, object]:
    return {
        relative: row
        for relative, row in tree.items()
        if not any(
            relative == mutable or relative.startswith(mutable + "/")
            for mutable in mutable_paths
        )
    }


def _assert_common_authority(
    oracle: Mapping[str, Any],
    *,
    authority: Mapping[str, Any],
) -> None:
    for field in (
        "frozen_identity",
        "output_tree",
        "profile_fingerprint",
        "invocation_fingerprint",
        "admission_fingerprint",
        "successor_owner_fingerprint",
        "successor_target_identity",
        "successor_target_tree",
        "apply_attempt_id",
    ):
        assert oracle[field] == authority[field]
    current = oracle["session"]
    reference = authority["session"]
    for field in (
        "runtime_admission_binding",
        "runtime_layout_bootstrap",
        "output_operation_admission_binding",
        "output_child_binding",
        "publication_binding",
        "apply_invocation_sha256",
    ):
        assert current[field] == reference[field]


def _assert_zero_forbidden_actions(*oracles: Mapping[str, Any]) -> None:
    for oracle in oracles:
        counts = oracle["action_counts"]
        for boundary in ("pre", "post"):
            assert counts[boundary][_DELETE_ENTRY] == 0
            assert counts[boundary][_ADVANCE_JOURNAL] == 0


def test_zero_entry_legacy_owner_retires_root_once_and_resumes_same_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Catch a zero-entry owner taking entry deletion or losing its root CAS."""

    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "new", monkeypatch)
    runtime_root = fixture.profile.runtime_root
    output_root = derive_deck_output_binding(
        fixture.profile,
        fixture.deck_name,
    ).output_root
    assert not output_root.exists()
    legacy = _seed_legacy_zero_entry_owner(
        runtime_root=runtime_root,
        deck_name=fixture.deck_name,
    )
    assert _plain_fingerprint(legacy.journal_path) == legacy.journal_fingerprint
    assert path_identity(legacy.target_path) == legacy.target_identity
    assert _physical_tree(legacy.target_path) == legacy.target_tree
    assert _physical_tree(runtime_root) == legacy.runtime_tree
    assert _plain_fingerprint(runtime_root / "CustomConfig/deck_config.ini") == (
        legacy.ini_fingerprint
    )
    assert _plain_fingerprint(runtime_root / ".hsconfig/state.json") == (
        legacy.state_fingerprint
    )
    assert (
        _plain_fingerprint(
            runtime_apply._receipt_path(runtime_root, legacy.journal.state_key)
        )
        == legacy.receipt_fingerprint
    )
    assert not output_root.exists()

    invocation_path = prepared.run_root / "receipts" / "apply_invocation.json"
    markers = tmp_path / "zero-entry-owner-retirement"
    markers.mkdir()

    def run(checkpoint: str) -> dict[str, Any]:
        marker = markers / f"{checkpoint}.json"
        _spawn_and_join(
            target=_zero_entry_hard_kill_worker,
            args=(
                str(prepared.run_root),
                str(output_root),
                str(invocation_path),
                str(legacy.journal_path),
                str(legacy.target_path),
                checkpoint,
                str(marker),
            ),
            expected_exitcode=_HARD_EXIT,
            timeout_seconds=360,
        )
        oracle = _load_oracle(marker)
        assert oracle["checkpoint"] == checkpoint
        assert oracle["session"] == _load_worker_session(prepared.run_root).to_value()
        _assert_tree_after_exit(
            runtime_root=runtime_root,
            snapshot={"tree": oracle["runtime_tree"]},
        )
        return oracle

    initial = run("initialization_pre")
    assert initial["fault_value"] == _PRE_CAS.value
    assert initial["apply_entry_counts"] == _expected_apply_entry_counts(
        fresh=1,
        install_prepare=1,
        attempt_prepare=1,
    )
    authority = initial
    initial_current = _load_worker_session(prepared.run_root)
    initial_recovery, initial_owner, initial_external = _owner_parts(initial_current)
    assert initial_recovery["install_route"] == "new_target"
    assert initial_owner["stage"] == "PREPARED"
    assert (
        tuple(initial_owner["initial_owner_journal_identity"])
        == (legacy.journal_fingerprint[0])
    )
    assert (
        initial_owner["initial_owner_journal_sha256"] == (legacy.journal_fingerprint[2])
    )
    assert (
        tuple(initial_owner["current_owner_journal_identity"])
        == (legacy.journal_fingerprint[0])
    )
    assert (
        initial_owner["current_owner_journal_sha256"] == (legacy.journal_fingerprint[2])
    )
    assert initial_owner["cleanup_entry_count"] == 0
    assert initial_owner["cleanup_cursor"] == 0
    assert initial_owner["planned_completed_tombstone_size"] is None
    assert initial_owner["planned_completed_tombstone_sha256"] is None
    assert isinstance(initial_external, Mapping)
    initialized_journal_fingerprint = _plain_fingerprint(legacy.journal_path)
    assert (
        _fingerprint_value(initialized_journal_fingerprint)
        == initial["old_journal_fingerprint"]
    )
    assert initialized_journal_fingerprint != legacy.journal_fingerprint
    initialized_journal = read_runtime_transaction_journal(legacy.journal_path)
    assert initialized_journal.cleanup_started is True
    assert initialized_journal.cleanup_entries == ()
    assert initialized_journal.cleanup_cursor == 0
    assert initialized_journal.phase is RuntimeTransactionPhase.FINALIZED
    assert path_identity(legacy.target_path) == legacy.target_identity
    assert _physical_tree(legacy.target_path) == legacy.target_tree
    tombstone_path = Path(str(initial_owner["tombstone_path"]))
    prepared_tombstone = runtime_apply._parse_owner_retirement_tombstone_bytes(
        tombstone_path.read_bytes(),
        runtime_root=runtime_root,
    )
    prepared_tombstone_fingerprint = _plain_fingerprint(tombstone_path)
    assert (
        tuple(initial_owner["tombstone_identity"])
        == (prepared_tombstone_fingerprint[0])
    )
    assert initial_owner["tombstone_sha256"] == prepared_tombstone_fingerprint[2]
    assert prepared_tombstone["state"] == "PREPARED"
    assert prepared_tombstone["cleanup_entries"] == []
    assert prepared_tombstone["cleanup_entry_count"] == 0
    assert prepared_tombstone["completed_cleanup_cursor"] is None

    root_pre = run("root_pre")
    _assert_common_authority(root_pre, authority=authority)
    assert root_pre["fault_value"] == _PRE_CAS.value
    assert root_pre["apply_entry_counts"] == _expected_apply_entry_counts(recovery=1)
    assert root_pre["action_counts"] == {
        "pre": {
            _INITIALIZE: 1,
            _RETIRE_ROOT: 1,
            _DELETE_ENTRY: 0,
            _ADVANCE_JOURNAL: 0,
        },
        "post": {
            _INITIALIZE: 1,
            _RETIRE_ROOT: 0,
            _DELETE_ENTRY: 0,
            _ADVANCE_JOURNAL: 0,
        },
    }
    root_pre_current = _load_worker_session(prepared.run_root)
    root_recovery, root_owner, root_external = _owner_parts(root_pre_current)
    assert root_pre["initialization_successor"] == root_pre["session"]
    assert root_owner["stage"] == "CLEANING"
    assert root_recovery["expected_action"] == _RETIRE_ROOT
    assert root_external is None
    assert root_owner["cleanup_entry_count"] == root_owner["cleanup_cursor"] == 0
    commitment = (
        root_owner["planned_completed_tombstone_size"],
        root_owner["planned_completed_tombstone_sha256"],
    )
    assert type(commitment[0]) is int and commitment[0] > 0
    assert isinstance(commitment[1], str) and commitment[1].startswith("sha256:")
    assert (
        tuple(root_owner["current_owner_journal_identity"])
        == (initialized_journal_fingerprint[0])
    )
    assert (
        root_owner["current_owner_journal_sha256"]
        == (initialized_journal_fingerprint[2])
    )
    assert _plain_fingerprint(legacy.journal_path) == initialized_journal_fingerprint
    assert not os.path.lexists(legacy.target_path)
    assert (
        runtime_apply._parse_owner_retirement_tombstone_bytes(
            tombstone_path.read_bytes(),
            runtime_root=runtime_root,
        )["state"]
        == "PREPARED"
    )

    root_post = run("root_post")
    _assert_common_authority(root_post, authority=authority)
    assert root_post["fault_value"] == _POST_CAS.value
    assert root_post["apply_entry_counts"] == _expected_apply_entry_counts(recovery=1)
    assert root_post["action_counts"] == {
        "pre": {
            _INITIALIZE: 0,
            _RETIRE_ROOT: 1,
            _DELETE_ENTRY: 0,
            _ADVANCE_JOURNAL: 0,
        },
        "post": {
            _INITIALIZE: 0,
            _RETIRE_ROOT: 1,
            _DELETE_ENTRY: 0,
            _ADVANCE_JOURNAL: 0,
        },
    }
    root_post_current = _load_worker_session(prepared.run_root)
    post_recovery, post_owner, post_external = _owner_parts(root_post_current)
    session._validate_owner_retirement_successor(
        predecessor=root_pre_current.apply_recovery,
        successor=root_post_current.apply_recovery,
        action=_RETIRE_ROOT,
    )
    assert post_owner["stage"] == "TARGET_RETIRED"
    assert post_recovery["expected_action"] == "materialize_file_action_staging"
    assert isinstance(post_external, Mapping)
    assert post_external["action_kind"] == "commit_owner_retirement_completed"
    assert post_external["stage"] == "PLANNED"
    assert (
        post_external["planned_successor_size"],
        post_external["planned_successor_sha256"],
    ) == commitment
    assert not os.path.lexists(legacy.target_path)
    assert _plain_fingerprint(legacy.journal_path) == initialized_journal_fingerprint
    assert (
        runtime_apply._parse_owner_retirement_tombstone_bytes(
            tombstone_path.read_bytes(),
            runtime_root=runtime_root,
        )["state"]
        == "PREPARED"
    )
    _assert_zero_forbidden_actions(initial, root_pre, root_post)
    assert (
        sum(
            oracle["action_counts"]["post"][_INITIALIZE]
            for oracle in (initial, root_pre, root_post)
        )
        == 1
    )
    assert (
        sum(
            oracle["action_counts"]["post"][_RETIRE_ROOT]
            for oracle in (initial, root_pre, root_post)
        )
        == 1
    )

    old_target_relative = legacy.target_path.relative_to(runtime_root).as_posix()
    old_journal_relative = legacy.journal_path.relative_to(runtime_root).as_posix()
    tombstone_relative = tombstone_path.relative_to(runtime_root).as_posix()
    attempt_relative = (
        Path(str(initial_recovery["successor_attempt_record_path"]))
        .relative_to(runtime_root)
        .as_posix()
    )
    mutable_paths = (
        old_target_relative,
        old_journal_relative,
        tombstone_relative,
        attempt_relative,
    )
    immutable_runtime = _runtime_projection(
        initial["runtime_tree"],
        mutable_paths=mutable_paths,
    )
    assert (
        _runtime_projection(
            root_pre["runtime_tree"],
            mutable_paths=mutable_paths,
        )
        == immutable_runtime
    )
    assert (
        _runtime_projection(
            root_post["runtime_tree"],
            mutable_paths=mutable_paths,
        )
        == immutable_runtime
    )

    invocation = load_apply_invocation(invocation_path)
    attempt_id = str(initial["apply_attempt_id"])
    assert invocation.apply_attempt_id == attempt_id
    assert invocation.content_sha256 == initial_current.apply_invocation_sha256
    assert legacy.journal.transaction_id != attempt_id
    successor_owner_path = Path(str(initial_owner["successor_owner_journal_path"]))
    successor_owner = read_runtime_transaction_journal(successor_owner_path)
    assert successor_owner.transaction_id == attempt_id
    assert successor_owner.owns_target is True
    assert successor_owner.previous_config_dir == legacy.target_path.name
    assert successor_owner.package_root_sha256 != legacy.journal.package_root_sha256

    final_marker = markers / "final-public-resume.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(final_marker)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    final_oracle = _load_oracle(final_marker)
    assert final_oracle.pop("apply_entry_counts") == _expected_apply_entry_counts(
        recovery=1
    )
    assert final_oracle["status"] == "LIVE_AND_MATCHED"
    terminal = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    assert terminal.content_sha256 == final_oracle["session_sha256"]
    assert terminal.terminal_status == "LIVE_AND_MATCHED"
    assert terminal.pending_transition is None
    assert terminal.apply_recovery is None
    assert terminal.closed_apply_recovery_commitment is None
    assert _frozen_identity(terminal) == initial["frozen_identity"]
    terminal_value = terminal.to_value()
    for field in (
        "apply_invocation_sha256",
        "runtime_admission_binding",
        "runtime_layout_bootstrap",
        "output_operation_admission_binding",
        "output_child_binding",
        "publication_binding",
    ):
        assert terminal_value[field] == initial["session"][field]
    assert terminal.result_intent["apply_attempt_id"] == attempt_id
    assert terminal.result_intent["physical_disposition"] == "COMMITTED"
    assert terminal.result_intent["runtime_match_status"] == "matched"
    assert terminal.attempt_acknowledgement["apply_attempt_id"] == attempt_id
    assert terminal.attempt_acknowledgement["journal_owns_target"] is True
    assert load_runtime_live_attempt_admission() is None
    assert not tuple((runtime_root / ".hsconfig/attempt-retention").iterdir())
    assert not tuple((runtime_root / ".hsconfig/staging").iterdir())
    assert not os.path.lexists(legacy.target_path)
    assert not os.path.lexists(legacy.journal_path)
    assert load_runtime_transaction_journals(runtime_root) == (successor_owner,)

    matched_output, matched_package, matched_target = _matched_package(fixture)
    assert matched_output == output_root
    assert matched_package == (
        output_root / str(terminal.publication_binding["revision"]) / "04_package"
    )
    assert matched_target == runtime_root / successor_owner.target_path
    assert (
        _fingerprint_value(_plain_fingerprint(successor_owner_path))
        == initial["successor_owner_fingerprint"]
    )
    assert list(path_identity(matched_target)) == initial["successor_target_identity"]
    assert (
        _runtime_tree(matched_target, held_lock_path=None)
        == initial["successor_target_tree"]
    )
    assert _runtime_tree(output_root, held_lock_path=None) == initial["output_tree"]
    assert (
        _fingerprint_value(_plain_fingerprint(operator_profile_path()))
        == initial["profile_fingerprint"]
    )
    assert (
        _fingerprint_value(_plain_fingerprint(invocation_path))
        == initial["invocation_fingerprint"]
    )

    completed = runtime_apply._parse_owner_retirement_tombstone_bytes(
        tombstone_path.read_bytes(),
        runtime_root=runtime_root,
    )
    completed_fingerprint = _plain_fingerprint(tombstone_path)
    assert completed["state"] == "COMPLETED"
    assert completed["retired_owner_transaction_id"] == (legacy.journal.transaction_id)
    assert Path(str(completed["initial_owner_journal_path"])) == (legacy.journal_path)
    assert (
        tuple(completed["initial_owner_journal_identity"])
        == (legacy.journal_fingerprint[0])
    )
    assert completed["initial_owner_journal_sha256"] == (legacy.journal_fingerprint[2])
    assert Path(str(completed["retired_target_path"])) == legacy.target_path
    assert tuple(completed["retired_target_parent_identity"]) == path_identity(
        legacy.target_path.parent
    )
    assert tuple(completed["retired_target_identity"]) == legacy.target_identity
    assert (
        completed["retired_target_tree_sha256"]
        == initial_owner["retired_target_tree_sha256"]
    )
    assert completed["cleanup_entries"] == []
    assert completed["cleanup_entry_count"] == 0
    assert completed["completed_cleanup_cursor"] == 0
    assert (
        tuple(completed["completed_owner_journal_identity"])
        == (initialized_journal_fingerprint[0])
    )
    assert (
        completed["completed_owner_journal_sha256"]
        == (initialized_journal_fingerprint[2])
    )
    assert completed["successor_transaction_id"] == attempt_id
    assert (
        completed["successor_package_root_sha256"]
        == (initial_current.publication_binding["content_root_sha256"])
    )
    assert (
        str(completed["successor_package_root_sha256"]).removeprefix("sha256:")
        == successor_owner.source_manifest_sha256
    )
    assert Path(str(completed["successor_owner_journal_path"])) == (
        successor_owner_path
    )
    assert (
        tuple(completed["successor_owner_journal_identity"])
        == (_plain_fingerprint(successor_owner_path)[0])
    )
    assert (
        completed["successor_owner_journal_sha256"]
        == (_plain_fingerprint(successor_owner_path)[2])
    )
    assert completed_fingerprint[1:] == commitment

    final_runtime = _runtime_tree(runtime_root, held_lock_path=None)
    final_runtime[".hsconfig/apply.lock"]["sha256"] = None
    assert (
        _runtime_projection(
            final_runtime,
            mutable_paths=mutable_paths,
        )
        == immutable_runtime
    )
    terminal_snapshot = {
        "session": _file_fingerprint(prepared.run_root / "session.json"),
        "results": _result_pair(prepared.run_root),
        "runtime": _physical_tree(runtime_root),
        "output": _physical_tree(output_root),
        "profile": _file_fingerprint(operator_profile_path()),
        "invocation": _file_fingerprint(invocation_path),
    }
    replay_marker = markers / "public-replay.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(replay_marker)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    replay = _load_oracle(replay_marker)
    assert replay.pop("apply_entry_counts") == _expected_apply_entry_counts()
    assert replay == final_oracle
    assert terminal_snapshot == {
        "session": _file_fingerprint(prepared.run_root / "session.json"),
        "results": _result_pair(prepared.run_root),
        "runtime": _physical_tree(runtime_root),
        "output": _physical_tree(output_root),
        "profile": _file_fingerprint(operator_profile_path()),
        "invocation": _file_fingerprint(invocation_path),
    }
    assert (
        sum(
            oracle["apply_entry_counts"]["fresh_apply"]
            for oracle in (initial, root_pre, root_post)
        )
        == 1
    )
    assert (
        sum(
            oracle["apply_entry_counts"]["install_prepare"]
            for oracle in (initial, root_pre, root_post)
        )
        == 1
    )
    assert (
        sum(
            oracle["apply_entry_counts"]["attempt_prepare"]
            for oracle in (initial, root_pre, root_post)
        )
        == 1
    )
