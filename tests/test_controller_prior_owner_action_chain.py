from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

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
    _sha256_bytes,
    _spawn_and_join,
    _start_apply_entry_observer,
)


_PRE_CAS = (
    LiveStartFaultPoint.AFTER_NONTERMINAL_RECOVERY_PHYSICAL_STEP_BEFORE_CURSOR_CAS
)
_POST_CAS = LiveStartFaultPoint.AFTER_NONTERMINAL_RECOVERY_CURSOR_CAS
_HARD_EXIT = 93
_CHECKPOINTS = (
    "prior_owner_planned",
    "prepared_journal_physical",
    "prior_owner_bound",
    "ini_visible",
)
_RESULT_NAMES = ("summary.json", "summary.md")


@dataclass(frozen=True, slots=True)
class _PriorOwnerSeed:
    transaction_id: str
    journal_path: Path
    journal_fingerprint: tuple[tuple[int, int, int], int, str]
    target_path: Path
    target_identity: tuple[int, int, int]
    target_tree: dict[str, tuple[str, tuple[int, int, int], bytes | None]]
    remapped_ini_fingerprint: tuple[tuple[int, int, int], int, str]
    runtime_before_second: dict[
        str,
        tuple[str, tuple[int, int, int], bytes | None],
    ]


@dataclass(frozen=True, slots=True)
class _ChainAuthority:
    frozen_identity: dict[str, object]
    attempt_id: str
    apply_invocation_sha256: str
    invocation_fingerprint: tuple[tuple[int, int, int], int, str]
    runtime_admission_binding: dict[str, object]
    runtime_admission_fingerprint: tuple[tuple[int, int, int], int, str]
    runtime_layout_bootstrap: dict[str, object]
    output_operation_admission_binding: dict[str, object]
    output_child_binding: dict[str, object]
    publication_binding: dict[str, object]
    profile_fingerprint: tuple[tuple[int, int, int], int, str]
    output_root: Path
    output_tree: dict[str, tuple[str, tuple[int, int, int], bytes | None]]


def _checkpoint_hook(checkpoint: str) -> LiveStartFaultPoint:
    assert checkpoint in _CHECKPOINTS
    return (
        _POST_CAS
        if checkpoint in {"prior_owner_planned", "prior_owner_bound"}
        else _PRE_CAS
    )


def _prior_owner_common(current: session.LiveStartSession) -> Mapping[str, Any] | None:
    recovery = current.apply_recovery
    if (
        current.phase.value != "APPLY_STARTED"
        or current.pending_transition is not None
        or not isinstance(recovery, Mapping)
        or recovery.get("recovery_stage") != "ACTIVE"
        or recovery.get("install_route") != "prior_owner"
        or recovery.get("stable_physical_disposition") is not None
        or recovery.get("runtime_match_status") != "not_run"
        or recovery.get("deck_config_ini_sha256") is not None
        or recovery.get("owner_retirement") is not None
        or recovery.get("candidate_path") is not None
        or recovery.get("candidate_parent_identity") is not None
        or recovery.get("predecessor_candidate_identity") is not None
        or recovery.get("successor_candidate_identity") is not None
        or recovery.get("candidate_tree_manifest_sha256") is not None
        or recovery.get("candidate_tree_verified_sha256") is not None
        or recovery.get("predecessor_target_owner_journal_identity") is None
        or recovery.get("successor_renamed_target_identity") is None
    ):
        return None
    return recovery


def _is_exact_checkpoint(
    current: session.LiveStartSession,
    *,
    checkpoint: str,
) -> bool:
    recovery = _prior_owner_common(current)
    if recovery is None:
        return False
    external = recovery.get("external_file_action")
    if not isinstance(external, Mapping):
        return False
    runtime_root = Path(str(recovery["runtime_root"]))
    attempt_id = str(recovery["apply_attempt_id"])
    final_path = Path(str(external.get("final_path")))
    fence_path = Path(str(recovery.get("successor_attempt_record_path")))
    planned_journal = recovery.get("planned_journal_successor_path")
    if (
        external.get("action_index") != recovery.get("action_index")
        or fence_path
        != runtime_root / ".hsconfig" / "attempt-retention" / f"{attempt_id}.json"
        or planned_journal is None
        or Path(str(planned_journal))
        != runtime_transaction_journal_path(runtime_root, attempt_id)
    ):
        return False
    ini_planned = (
        external.get("action_kind") == "materialize_file_action_staging"
        and external.get("stage") == "PLANNED"
        and external.get("commit_mode") == "replace_exact"
        and external.get("predecessor_state") == "exact"
    )
    if checkpoint == "prior_owner_planned":
        return bool(
            recovery.get("expected_action") == "materialize_file_action_staging"
            and external.get("action_kind") == "materialize_file_action_staging"
            and external.get("stage") == "PLANNED"
            and external.get("commit_mode") == "create_no_replace"
            and external.get("predecessor_state") == "absent"
            and final_path == Path(str(planned_journal))
            and final_path != fence_path
            and recovery.get("successor_attempt_record_identity") is not None
            and recovery.get("successor_journal_identity") is None
            and recovery.get("planned_journal_successor_phase") == "PREPARED"
        )
    if checkpoint == "prepared_journal_physical":
        return bool(
            recovery.get("expected_action")
            == "advance_controller_transaction_journal_write"
            and external.get("action_kind")
            == "advance_controller_transaction_journal_write"
            and external.get("stage") == "STAGING_BOUND"
            and external.get("commit_mode") == "create_no_replace"
            and external.get("predecessor_state") == "absent"
            and final_path == Path(str(planned_journal))
            and recovery.get("successor_journal_identity") is None
            and recovery.get("planned_journal_successor_phase") == "PREPARED"
        )
    ini_path = runtime_root / "CustomConfig/deck_config.ini"
    if checkpoint == "prior_owner_bound":
        return bool(
            recovery.get("expected_action") == "materialize_file_action_staging"
            and ini_planned
            and final_path == ini_path
            and recovery.get("successor_journal_identity") is not None
            and recovery.get("planned_journal_successor_phase") == "INI_COMMITTED"
        )
    assert checkpoint == "ini_visible"
    return bool(
        recovery.get("expected_action") == "write_deck_config_ini"
        and external.get("action_kind") == "write_deck_config_ini"
        and external.get("stage") == "STAGING_BOUND"
        and external.get("commit_mode") == "replace_exact"
        and external.get("predecessor_state") == "exact"
        and final_path == ini_path
        and recovery.get("successor_journal_identity") is not None
        and recovery.get("planned_journal_successor_phase") == "INI_COMMITTED"
    )


def _held_apply_lock_metadata(
    current: session.LiveStartSession,
) -> tuple[tuple[int, int, int], int]:
    layout = current.runtime_layout_bootstrap
    assert isinstance(layout, Mapping)
    lock_path = Path(str(layout["runtime_root"])) / ".hsconfig/apply.lock"
    status = lock_path.lstat()
    assert stat.S_ISREG(status.st_mode)
    assert status.st_nlink == 1
    assert status.st_size == 0
    return path_identity(lock_path), status.st_size


def _prior_owner_hard_kill_worker(
    session_root_text: str,
    checkpoint: str,
    oracle_path_text: str,
) -> None:
    session_root = Path(session_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    selected_hook = _checkpoint_hook(checkpoint)
    counts, previous_profile = _start_apply_entry_observer()

    def hard_kill(point: LiveStartFaultPoint) -> None:
        if point is not selected_hook:
            return
        session_path = session_root / "session.json"
        persisted = session._load_session_bytes(
            session_path.read_bytes(),
            session_identity=path_identity(session_path),
        )
        if not _is_exact_checkpoint(persisted, checkpoint=checkpoint):
            return
        lock_identity, lock_size = _held_apply_lock_metadata(persisted)
        _persist_worker_oracle(
            Path(oracle_path_text),
            {
                "checkpoint": checkpoint,
                "fault_value": point.value,
                "session": persisted.to_value(),
                "apply_entry_counts": counts,
                "apply_lock_identity": lock_identity,
                "apply_lock_size": lock_size,
            },
        )
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


def _changed_paths(
    before: Mapping[str, object],
    after: Mapping[str, object],
) -> set[str]:
    return {
        path for path in set(before) | set(after) if before.get(path) != after.get(path)
    }


def _seed_prior_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Any, Any, _PriorOwnerSeed]:
    first_fixture, first = _prepare_approved(tmp_path / "first", monkeypatch)
    assert controller.finalize_live_start(session_root=first.run_root).status == (
        "LIVE_AND_MATCHED"
    )
    _output, _package, target_path = _matched_package(first_fixture)
    owners = [
        journal
        for journal in load_runtime_transaction_journals(
            first_fixture.profile.runtime_root
        )
        if journal.owns_target
        and first_fixture.profile.runtime_root / journal.target_path == target_path
    ]
    assert len(owners) == 1
    owner = owners[0]
    owner_path = runtime_transaction_journal_path(
        first_fixture.profile.runtime_root,
        owner.transaction_id,
    )
    owner_fingerprint = _file_fingerprint(owner_path)
    assert owner_fingerprint is not None
    ini_path = first_fixture.profile.runtime_root / "CustomConfig/deck_config.ini"
    ini_path.write_text(
        "[CONFIGS]\n"
        "ShadowPriest = shadowpriest-previous\n"
        f"OtherDeck = {target_path.name}",
        encoding="utf-8",
    )
    remapped_ini_fingerprint = _file_fingerprint(ini_path)
    assert remapped_ini_fingerprint is not None
    fixture, prepared = _prepare_approved(
        tmp_path / "second",
        monkeypatch,
        profile=first_fixture.profile,
    )
    return (
        fixture,
        prepared,
        _PriorOwnerSeed(
            transaction_id=owner.transaction_id,
            journal_path=owner_path,
            journal_fingerprint=owner_fingerprint,
            target_path=target_path,
            target_identity=path_identity(target_path),
            target_tree=_physical_tree(target_path),
            remapped_ini_fingerprint=remapped_ini_fingerprint,
            runtime_before_second=_physical_tree(first_fixture.profile.runtime_root),
        ),
    )


def _capture_authority(
    *,
    fixture: Any,
    prepared: Any,
    current: session.LiveStartSession,
) -> _ChainAuthority:
    value = current.to_value()
    recovery = value["apply_recovery"]
    admission = value["runtime_admission_binding"]
    layout = value["runtime_layout_bootstrap"]
    operation = value["output_operation_admission_binding"]
    child = value["output_child_binding"]
    publication = value["publication_binding"]
    for row in (recovery, admission, layout, operation, child, publication):
        assert isinstance(row, dict)
    attempt_id = str(recovery["apply_attempt_id"])
    invocation_path = prepared.run_root / "receipts/apply_invocation.json"
    invocation_fingerprint = _file_fingerprint(invocation_path)
    admission_fingerprint = _file_fingerprint(Path(str(admission["admission_path"])))
    profile_fingerprint = _file_fingerprint(operator_profile_path())
    assert invocation_fingerprint is not None
    assert admission_fingerprint is not None
    assert profile_fingerprint is not None
    invocation = load_apply_invocation(invocation_path)
    assert invocation.apply_attempt_id == attempt_id
    assert invocation.content_sha256 == current.apply_invocation_sha256
    output_root = derive_deck_output_binding(
        fixture.profile,
        fixture.deck_name,
    ).output_root
    return _ChainAuthority(
        frozen_identity=_frozen_identity(current),
        attempt_id=attempt_id,
        apply_invocation_sha256=str(current.apply_invocation_sha256),
        invocation_fingerprint=invocation_fingerprint,
        runtime_admission_binding=admission,
        runtime_admission_fingerprint=admission_fingerprint,
        runtime_layout_bootstrap=layout,
        output_operation_admission_binding=operation,
        output_child_binding=child,
        publication_binding=publication,
        profile_fingerprint=profile_fingerprint,
        output_root=output_root,
        output_tree=_physical_tree(output_root),
    )


def _assert_authority(
    *,
    prepared: Any,
    current: session.LiveStartSession,
    authority: _ChainAuthority,
    owner: _PriorOwnerSeed,
) -> None:
    value = current.to_value()
    recovery = value["apply_recovery"]
    assert isinstance(recovery, dict)
    assert _frozen_identity(current) == authority.frozen_identity
    assert recovery["apply_attempt_id"] == authority.attempt_id
    assert recovery["install_route"] == "prior_owner"
    assert current.apply_invocation_sha256 == authority.apply_invocation_sha256
    assert value["runtime_admission_binding"] == authority.runtime_admission_binding
    assert value["runtime_layout_bootstrap"] == authority.runtime_layout_bootstrap
    assert (
        value["output_operation_admission_binding"]
        == authority.output_operation_admission_binding
    )
    assert value["output_child_binding"] == authority.output_child_binding
    assert value["publication_binding"] == authority.publication_binding
    assert (
        _file_fingerprint(prepared.run_root / "receipts/apply_invocation.json")
        == authority.invocation_fingerprint
    )
    assert tuple(prepared.run_root.rglob("*apply_invocation*.json")) == (
        prepared.run_root / "receipts/apply_invocation.json",
    )
    assert _file_fingerprint(operator_profile_path()) == authority.profile_fingerprint
    assert _physical_tree(authority.output_root) == authority.output_tree
    admission_path = Path(str(authority.runtime_admission_binding["admission_path"]))
    assert _file_fingerprint(admission_path) == authority.runtime_admission_fingerprint
    physical_admission = load_runtime_live_attempt_admission()
    assert physical_admission is not None
    assert physical_admission.apply_attempt_id == authority.attempt_id
    assert physical_admission.admission_path == admission_path
    assert (
        physical_admission.admission_identity
        == authority.runtime_admission_fingerprint[0]
    )
    assert (
        physical_admission.admission_sha256
        == (authority.runtime_admission_fingerprint[2])
    )
    assert _file_fingerprint(owner.journal_path) == owner.journal_fingerprint
    assert path_identity(owner.target_path) == owner.target_identity
    assert _physical_tree(owner.target_path) == owner.target_tree


def _assert_lock_after_exit(
    *,
    runtime_root: Path,
    oracle: Mapping[str, object],
) -> None:
    lock_identity = tuple(oracle["apply_lock_identity"])
    assert oracle["apply_lock_size"] == 0
    assert _file_fingerprint(runtime_root / ".hsconfig/apply.lock") == (
        lock_identity,
        0,
        _sha256_bytes(b""),
    )


def _assert_checkpoint_physical(
    *,
    checkpoint: str,
    current: session.LiveStartSession,
    authority: _ChainAuthority,
    owner: _PriorOwnerSeed,
    tree: Mapping[str, object],
) -> None:
    recovery = current.apply_recovery
    assert isinstance(recovery, Mapping)
    external = recovery["external_file_action"]
    assert isinstance(external, Mapping)
    runtime_root = Path(str(recovery["runtime_root"]))
    fence_path = Path(str(recovery["successor_attempt_record_path"]))
    fence_fingerprint = _file_fingerprint(fence_path)
    assert fence_fingerprint is not None
    assert fence_fingerprint[0] == tuple(recovery["successor_attempt_record_identity"])
    assert fence_fingerprint[2] == recovery["successor_attempt_record_sha256"]
    fence = runtime_apply._runtime_attempt_retention_from_raw(
        fence_path.read_bytes(),
        runtime_root=runtime_root,
    )
    attempt_journal_path = runtime_transaction_journal_path(
        runtime_root,
        authority.attempt_id,
    )
    assert fence.apply_attempt_id == authority.attempt_id
    assert fence.retention_owner_run_id == current.run_id
    assert fence.target_path == owner.target_path
    assert fence.target_identity == owner.target_identity
    assert fence.owns_target is False
    assert fence.target_owner_journal_path == owner.journal_path
    assert fence.target_owner_journal_identity == owner.journal_fingerprint[0]
    assert fence.target_owner_journal_sha256 == owner.journal_fingerprint[2]
    assert fence.planned_journal_path == attempt_journal_path
    assert fence.candidate_path is None
    assert fence.candidate_parent_identity is None
    assert fence.candidate_identity is None
    expected_fence_state = {
        "prior_owner_planned": "PRIOR_OWNER_PLANNED",
        "prepared_journal_physical": "PRIOR_OWNER_PLANNED",
        "prior_owner_bound": "PRIOR_OWNER_BOUND",
        "ini_visible": "PRIOR_OWNER_BOUND",
    }[checkpoint]
    assert fence.state == expected_fence_state
    if checkpoint in {"prior_owner_planned", "prepared_journal_physical"}:
        assert fence.journal_path is None
        assert fence.journal_identity is None
        assert fence.journal_sha256 is None
    else:
        assert fence.journal_path == attempt_journal_path
        assert fence.journal_identity == tuple(recovery["successor_journal_identity"])
        assert fence.journal_sha256 == recovery["successor_journal_sha256"]

    journals = {
        journal.transaction_id: journal
        for journal in load_runtime_transaction_journals(runtime_root)
    }
    assert journals[owner.transaction_id].phase is RuntimeTransactionPhase.FINALIZED
    assert journals[owner.transaction_id].owns_target is True
    if checkpoint == "prior_owner_planned":
        assert set(journals) == {owner.transaction_id}
    else:
        assert set(journals) == {owner.transaction_id, authority.attempt_id}
        attempt = journals[authority.attempt_id]
        assert attempt.phase is RuntimeTransactionPhase.PREPARED
        assert attempt.owns_target is False
        assert attempt.target_identity is None
        attempt_fingerprint = _file_fingerprint(attempt_journal_path)
        assert attempt_fingerprint is not None
        if checkpoint == "prepared_journal_physical":
            assert recovery["successor_journal_identity"] is None
            assert attempt_fingerprint == (
                tuple(external["staging_identity"]),
                external["planned_successor_size"],
                external["planned_successor_sha256"],
            )
        else:
            assert attempt_fingerprint[0] == tuple(
                recovery["successor_journal_identity"]
            )
            assert attempt_fingerprint[2] == recovery["successor_journal_sha256"]

    staging_root = runtime_root / ".hsconfig/staging"
    assert not tuple(staging_root.iterdir())
    assert recovery["candidate_path"] is None
    assert recovery["predecessor_candidate_identity"] is None
    assert recovery["successor_candidate_identity"] is None
    ini_path = runtime_root / "CustomConfig/deck_config.ini"
    if checkpoint in {"prior_owner_bound", "ini_visible"}:
        assert (
            tuple(external["predecessor_identity"])
            == (owner.remapped_ini_fingerprint[0])
        )
        assert external["predecessor_size"] == owner.remapped_ini_fingerprint[1]
        assert external["predecessor_sha256"] == owner.remapped_ini_fingerprint[2]
    if checkpoint != "ini_visible":
        assert _file_fingerprint(ini_path) == owner.remapped_ini_fingerprint
    else:
        assert _file_fingerprint(ini_path) == (
            tuple(external["staging_identity"]),
            external["planned_successor_size"],
            external["planned_successor_sha256"],
        )
        assert not Path(str(external["staging_path"])).exists()
        assert not Path(str(external["inner_temp_path"])).exists()
        selected = runtime_apply.read_deck_config(
            ini_path,
            deck_name=current.deck_name,
        )
        assert selected.selected_config_dir == owner.target_path.name
    assert tree == _physical_tree(runtime_root)


def test_prior_owner_runtime_action_chain_preserves_owner_and_resumes_post_ini(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared, owner = _seed_prior_owner(tmp_path, monkeypatch)
    runtime_root = fixture.profile.runtime_root
    markers = tmp_path / "prior-owner-action-chain"
    markers.mkdir()
    approved = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    approved_frozen = _frozen_identity(approved)
    authority: _ChainAuthority | None = None
    previous_tree: Mapping[str, object] = owner.runtime_before_second

    for ordinal, checkpoint in enumerate(_CHECKPOINTS):
        marker = markers / f"{ordinal:02d}-{checkpoint}.json"
        _spawn_and_join(
            target=_prior_owner_hard_kill_worker,
            args=(str(prepared.run_root), checkpoint, str(marker)),
            expected_exitcode=_HARD_EXIT,
            timeout_seconds=360,
        )
        oracle = json.loads(marker.read_bytes())
        assert oracle["checkpoint"] == checkpoint
        assert oracle["fault_value"] == _checkpoint_hook(checkpoint).value
        expected_counts = (
            _expected_apply_entry_counts(
                fresh=1,
                install_prepare=1,
                attempt_prepare=1,
            )
            if ordinal == 0
            else _expected_apply_entry_counts(recovery=1)
        )
        assert oracle["apply_entry_counts"] == expected_counts
        current = session.load_live_start_session(
            prepared.run_root,
            local_app_data_root=prepared.run_root.parents[2],
        )
        assert oracle["session"] == current.to_value()
        assert _is_exact_checkpoint(current, checkpoint=checkpoint)
        assert _frozen_identity(current) == approved_frozen
        if authority is None:
            authority = _capture_authority(
                fixture=fixture,
                prepared=prepared,
                current=current,
            )
            assert authority.attempt_id != owner.transaction_id
        _assert_authority(
            prepared=prepared,
            current=current,
            authority=authority,
            owner=owner,
        )
        _assert_lock_after_exit(runtime_root=runtime_root, oracle=oracle)
        tree = _physical_tree(runtime_root)
        expected_changed = {
            "prior_owner_planned": {
                Path(str(current.apply_recovery["successor_attempt_record_path"]))
                .relative_to(runtime_root)
                .as_posix()
            },
            "prepared_journal_physical": {
                Path(str(current.apply_recovery["external_file_action"]["final_path"]))
                .relative_to(runtime_root)
                .as_posix(),
            },
            "prior_owner_bound": {
                Path(str(current.apply_recovery["successor_attempt_record_path"]))
                .relative_to(runtime_root)
                .as_posix()
            },
            "ini_visible": {"CustomConfig/deck_config.ini"},
        }[checkpoint]
        assert _changed_paths(previous_tree, tree) == expected_changed
        _assert_checkpoint_physical(
            checkpoint=checkpoint,
            current=current,
            authority=authority,
            owner=owner,
            tree=tree,
        )
        previous_tree = tree

    assert authority is not None
    final_oracle_path = markers / "final-public-resume.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(final_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    final_oracle = json.loads(final_oracle_path.read_bytes())
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
    assert _frozen_identity(terminal) == authority.frozen_identity
    assert terminal.apply_invocation_sha256 == authority.apply_invocation_sha256
    terminal_value = terminal.to_value()
    assert (
        terminal_value["runtime_admission_binding"]
        == authority.runtime_admission_binding
    )
    assert (
        terminal_value["runtime_layout_bootstrap"] == authority.runtime_layout_bootstrap
    )
    assert terminal_value["publication_binding"] == authority.publication_binding
    assert (
        terminal_value["output_operation_admission_binding"]
        == authority.output_operation_admission_binding
    )
    assert terminal_value["output_child_binding"] == authority.output_child_binding
    assert terminal.result_intent["apply_attempt_id"] == authority.attempt_id
    assert terminal.result_intent["raw_apply_status"] == "recovered"
    assert terminal.result_intent["physical_disposition"] == "COMMITTED"
    assert terminal.result_intent["runtime_match_status"] == "matched"
    assert terminal.attempt_acknowledgement["apply_attempt_id"] == authority.attempt_id
    assert terminal.attempt_acknowledgement["journal_owns_target"] is False
    assert terminal.attempt_acknowledgement["acknowledgement_action"] == (
        "delete_nonowning_attempt_and_fence"
    )
    assert (
        Path(str(terminal.attempt_acknowledgement["target_owner_journal_path"]))
        == owner.journal_path
    )
    assert terminal.terminal_retirement["apply_attempt_id"] == authority.attempt_id
    acknowledgement = terminal.attempt_acknowledgement
    intent = terminal.result_intent
    assert (
        tuple(acknowledgement["target_owner_journal_identity"])
        == (owner.journal_fingerprint[0])
    )
    assert (
        acknowledgement["target_owner_journal_sha256"] == owner.journal_fingerprint[2]
    )
    assert Path(acknowledgement["target_path"]) == owner.target_path
    assert tuple(acknowledgement["target_identity"]) == owner.target_identity
    for acknowledgement_prefix, intent_prefix, expected_path in (
        (
            "retention_fence",
            "retained_attempt_record",
            runtime_root
            / ".hsconfig/attempt-retention"
            / f"{authority.attempt_id}.json",
        ),
        (
            "journal",
            "retained_journal",
            runtime_root / ".hsconfig/transactions" / f"{authority.attempt_id}.json",
        ),
        ("target_owner_journal", "retained_target_owner_journal", owner.journal_path),
    ):
        assert Path(acknowledgement[f"{acknowledgement_prefix}_path"]) == expected_path
        for suffix in ("path", "identity", "sha256"):
            assert (
                acknowledgement[f"{acknowledgement_prefix}_{suffix}"]
                == (intent[f"{intent_prefix}_{suffix}"])
            )
    assert terminal.terminal_retirement["operation"] == "ack_success"
    assert terminal.terminal_retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"
    assert (
        _file_fingerprint(prepared.run_root / "receipts/apply_invocation.json")
        == authority.invocation_fingerprint
    )
    assert _file_fingerprint(operator_profile_path()) == authority.profile_fingerprint
    assert _physical_tree(authority.output_root) == authority.output_tree
    assert load_runtime_live_attempt_admission() is None
    assert _file_fingerprint(owner.journal_path) == owner.journal_fingerprint
    assert path_identity(owner.target_path) == owner.target_identity
    assert _physical_tree(owner.target_path) == owner.target_tree
    _output, _package, matched_target = _matched_package(fixture)
    assert matched_target == owner.target_path
    assert not tuple((runtime_root / ".hsconfig/staging").iterdir())
    assert not tuple((runtime_root / ".hsconfig/attempt-retention").iterdir())
    journals = load_runtime_transaction_journals(runtime_root)
    assert len(journals) == 1
    assert journals[0].transaction_id == owner.transaction_id
    assert journals[0].owns_target is True
    assert tuple(
        path for path in (runtime_root / "CustomConfig").iterdir() if path.is_dir()
    ) == (owner.target_path,)

    terminal_bytes = {
        "session": (prepared.run_root / "session.json").read_bytes(),
        "results": _result_pair(prepared.run_root),
        "runtime": _physical_tree(runtime_root),
        "output": _physical_tree(authority.output_root),
        "profile": _file_fingerprint(operator_profile_path()),
        "invocation": _file_fingerprint(
            prepared.run_root / "receipts/apply_invocation.json"
        ),
    }
    assert {
        relative: row[0] for relative, row in terminal_bytes["runtime"].items()
    } == {relative: row[0] for relative, row in owner.runtime_before_second.items()}
    runtime_artifacts = (
        ("CustomConfig/deck_config.ini", "deck_config_ini_sha256"),
        (".hsconfig/state.json", "runtime_state_sha256"),
        (
            f".hsconfig/receipts/{journals[0].state_key}/last_apply_receipt.json",
            "last_apply_receipt_sha256",
        ),
    )
    assert _changed_paths(owner.runtime_before_second, terminal_bytes["runtime"]) <= {
        relative for relative, _digest_field in runtime_artifacts
    }
    for relative, digest_field in runtime_artifacts:
        fingerprint = _file_fingerprint(runtime_root / relative)
        assert fingerprint is not None
        assert fingerprint[2] == intent[digest_field]
        predecessor = owner.runtime_before_second[relative]
        if _sha256_bytes(predecessor[2]) == intent[digest_field]:
            assert terminal_bytes["runtime"][relative] == predecessor
    replay_path = markers / "public-replay.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(replay_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    replay = json.loads(replay_path.read_bytes())
    assert replay.pop("apply_entry_counts") == _expected_apply_entry_counts()
    assert replay == final_oracle
    assert (prepared.run_root / "session.json").read_bytes() == terminal_bytes[
        "session"
    ]
    assert _result_pair(prepared.run_root) == terminal_bytes["results"]
    assert _physical_tree(runtime_root) == terminal_bytes["runtime"]
    assert _physical_tree(authority.output_root) == terminal_bytes["output"]
    assert _file_fingerprint(operator_profile_path()) == terminal_bytes["profile"]
    assert (
        _file_fingerprint(prepared.run_root / "receipts/apply_invocation.json")
        == terminal_bytes["invocation"]
    )
