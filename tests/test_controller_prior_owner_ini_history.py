from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from typing import Any, Literal

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig.apply_invocation import load_apply_invocation
from hsconfig.deck_config_ini import read_deck_config, render_deck_config
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.operator_profile import derive_deck_output_binding, operator_profile_path
from hsconfig.package_io import path_identity
from hsconfig.package_request import FrozenJsonDocument
from hsconfig.runtime_live_admission import load_runtime_live_attempt_admission
from hsconfig.runtime_transaction_journal import (
    RuntimeTransactionPhase,
    load_runtime_transaction_journals,
    read_runtime_transaction_journal,
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
    _spawn_and_join,
    _start_apply_entry_observer,
)
from tests.test_controller_prior_owner_action_chain import (
    _PriorOwnerSeed,
    _result_pair,
    _seed_prior_owner,
)


_CLOSED = LiveStartFaultPoint.AFTER_RECOVERY_CLOSED_CAS_BEFORE_RESULT_INTENT
_INSTALLER_RETURN = LiveStartFaultPoint.AFTER_INSTALLER_RETURN_BEFORE_APPLY_COMMITTED
_EVIDENCE_RETIRED = (
    LiveStartFaultPoint.AFTER_ATTEMPT_EVIDENCE_RETIRED_BEFORE_ADMISSION_RELEASE
)
_HARD_EXIT = 93


def _raw_held_session(session_root: Path) -> session.LiveStartSession:
    path = session_root / "session.json"
    return session._load_session_bytes(
        path.read_bytes(),
        session_identity=path_identity(path),
    )


def _oracle_fingerprint(
    value: object,
) -> tuple[tuple[int, int, int], int, str]:
    assert isinstance(value, list)
    assert len(value) == 3
    identity = value[0]
    assert isinstance(identity, list)
    assert len(identity) == 3
    return tuple(identity), int(value[1]), str(value[2])


def _closed_prior_owner_projection(
    current: session.LiveStartSession,
    *,
    match_status: Literal["matched", "mismatch"],
) -> dict[str, object] | None:
    recovery = current.apply_recovery
    if (
        current.pending_transition is not None
        or not isinstance(recovery, Mapping)
        or recovery.get("recovery_stage") != "CLOSED"
        or recovery.get("install_route") != "prior_owner"
        or recovery.get("stable_physical_disposition") != "COMMITTED"
        or recovery.get("runtime_match_status") != match_status
        or recovery.get("expected_action") is not None
        or recovery.get("external_file_action") is not None
        or recovery.get("candidate_path") is not None
        or recovery.get("candidate_parent_identity") is not None
        or recovery.get("successor_candidate_identity") is not None
    ):
        return None

    attempt_id = str(recovery["apply_attempt_id"])
    journal_path = Path(str(recovery["predecessor_journal_path"]))
    owner_path = Path(str(recovery["predecessor_target_owner_journal_path"]))
    fence_path = Path(str(recovery["predecessor_attempt_record_path"]))
    journal = read_runtime_transaction_journal(journal_path)
    owner = read_runtime_transaction_journal(owner_path)
    journal_fingerprint = _file_fingerprint(journal_path)
    owner_fingerprint = _file_fingerprint(owner_path)
    fence_fingerprint = _file_fingerprint(fence_path)
    ini_path = Path(str(recovery["runtime_root"])) / "CustomConfig/deck_config.ini"
    ini = read_deck_config(ini_path, deck_name=current.deck_name)
    if (
        journal_fingerprint is None
        or owner_fingerprint is None
        or fence_fingerprint is None
        or journal.transaction_id != attempt_id
        or journal.phase is not RuntimeTransactionPhase.FINALIZED
        or journal.owns_target is not False
        or owner.transaction_id == attempt_id
        or owner.phase is not RuntimeTransactionPhase.FINALIZED
        or owner.owns_target is not True
        or journal.target_path != owner.target_path
        or journal.target_identity != owner.target_identity
        or journal.next_config_dir != owner.next_config_dir
        or ini.sha256 != journal.next_ini_sha256
        or journal.next_ini_sha256 == owner.next_ini_sha256
        or journal_fingerprint[0] != tuple(recovery["predecessor_journal_identity"])
        or journal_fingerprint[2] != recovery["predecessor_journal_sha256"]
        or owner_fingerprint[0]
        != tuple(recovery["predecessor_target_owner_journal_identity"])
        or owner_fingerprint[2] != recovery["predecessor_target_owner_journal_sha256"]
        or fence_fingerprint[0]
        != tuple(recovery["predecessor_attempt_record_identity"])
        or fence_fingerprint[2] != recovery["predecessor_attempt_record_sha256"]
    ):
        return None
    return {
        "attempt_id": attempt_id,
        "journal_path": str(journal_path),
        "journal_fingerprint": journal_fingerprint,
        "fence_path": str(fence_path),
        "fence_fingerprint": fence_fingerprint,
        "owner_path": str(owner_path),
        "owner_fingerprint": owner_fingerprint,
        "current_ini_sha256": "sha256:" + str(journal.next_ini_sha256),
        "historical_owner_ini_sha256": "sha256:" + str(owner.next_ini_sha256),
    }


def _prior_owner_history_hard_kill_worker(
    session_root_text: str,
    case: str,
    oracle_path_text: str,
) -> None:
    session_root = Path(session_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    counts, previous_profile = _start_apply_entry_observer()
    closed_projection: dict[str, object] | None = None
    drift_projection: dict[str, object] | None = None

    def hard_kill(point: LiveStartFaultPoint) -> None:
        nonlocal closed_projection, drift_projection
        if case == "mismatch" and point is _INSTALLER_RETURN:
            current = _raw_held_session(session_root)
            recovery = current.apply_recovery
            if (
                current.pending_transition is not None
                or not isinstance(recovery, Mapping)
                or recovery.get("recovery_stage") != "ACTIVE"
                or recovery.get("install_route") != "prior_owner"
                or recovery.get("stable_physical_disposition") != "COMMITTED"
                or recovery.get("runtime_match_status") != "unknown"
                or recovery.get("expected_action") is not None
                or recovery.get("external_file_action") is not None
            ):
                return
            journal_path = Path(str(recovery["predecessor_journal_path"]))
            owner_path = Path(str(recovery["predecessor_target_owner_journal_path"]))
            journal = read_runtime_transaction_journal(journal_path)
            owner = read_runtime_transaction_journal(owner_path)
            target = Path(str(recovery["renamed_target_path"]))
            ini = read_deck_config(
                Path(str(recovery["runtime_root"])) / "CustomConfig/deck_config.ini",
                deck_name=current.deck_name,
            )
            if (
                journal.transaction_id != recovery.get("apply_attempt_id")
                or journal.phase is not RuntimeTransactionPhase.FINALIZED
                or journal.owns_target is not False
                or owner.phase is not RuntimeTransactionPhase.FINALIZED
                or owner.owns_target is not True
                or journal.target_path != owner.target_path
                or journal.target_identity != owner.target_identity
                or target != Path(str(recovery["runtime_root"])) / journal.target_path
                or path_identity(target) != journal.target_identity
                or ini.sha256 != journal.next_ini_sha256
                or journal.next_ini_sha256 == owner.next_ini_sha256
            ):
                return
            assert drift_projection is None
            mulligan = _drift_owned_target_without_replacing_identity(target)
            drift_projection = {
                "path": str(mulligan),
                "fingerprint": _file_fingerprint(mulligan),
            }
            return

        if point is _CLOSED:
            current = _raw_held_session(session_root)
            projection = _closed_prior_owner_projection(
                current,
                match_status="matched" if case == "matched" else "mismatch",
            )
            if projection is None:
                return
            if case == "matched":
                _persist_worker_oracle(
                    Path(oracle_path_text),
                    {
                        "fault_value": point.value,
                        "closed": projection,
                        "session": current.to_value(),
                        "apply_entry_counts": counts,
                    },
                )
                os._exit(_HARD_EXIT)
            assert case == "mismatch"
            assert drift_projection is not None
            assert closed_projection is None
            closed_projection = projection
            return

        if case != "mismatch" or point is not _EVIDENCE_RETIRED:
            return
        current = _raw_held_session(session_root)
        intent = current.result_intent
        retirement = current.terminal_retirement
        if (
            closed_projection is None
            or current.terminal_status != "APPLIED_BUT_NOT_VERIFIED"
            or current.pending_transition is not None
            or current.apply_recovery is not None
            or current.closed_apply_recovery_commitment is not None
            or not isinstance(intent, Mapping)
            or intent.get("apply_attempt_id") != closed_projection["attempt_id"]
            or intent.get("physical_disposition") != "COMMITTED"
            or intent.get("runtime_match_status") != "mismatch"
            or intent.get("deck_config_ini_sha256")
            != closed_projection["current_ini_sha256"]
            or not isinstance(retirement, Mapping)
            or retirement.get("operation") != "release_committed_mismatch"
            or retirement.get("stage") != "EVIDENCE_RETIRED"
            or retirement.get("apply_attempt_id") != closed_projection["attempt_id"]
        ):
            return
        _persist_worker_oracle(
            Path(oracle_path_text),
            {
                "fault_value": point.value,
                "closed": closed_projection,
                "drift": drift_projection,
                "session": current.to_value(),
                "apply_entry_counts": counts,
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


def _drift_owned_target_without_replacing_identity(target: Path) -> Path:
    mulligan = target / "Mulligan.json"
    identity = path_identity(mulligan)
    value = json.loads(mulligan.read_bytes())
    assert value["GameCardId"] == "Mulligan"
    assert value["Mulligan"]["values"][0]["value"] == "hold"
    value["Mulligan"]["values"][0]["value"] = "discard"
    raw = FrozenJsonDocument.from_value(value).canonical_json
    with mulligan.open("r+b") as handle:
        handle.seek(0)
        assert handle.write(raw) == len(raw)
        handle.truncate()
        handle.flush()
        os.fsync(handle.fileno())
    assert path_identity(mulligan) == identity
    assert mulligan.read_bytes() == raw
    return mulligan


def _assert_history_fixture(
    *,
    fixture: Any,
    owner: _PriorOwnerSeed,
) -> tuple[bytes, str]:
    owner_journal = read_runtime_transaction_journal(owner.journal_path)
    assert owner_journal.transaction_id == owner.transaction_id
    assert owner_journal.phase is RuntimeTransactionPhase.FINALIZED
    assert owner_journal.owns_target is True
    assert owner_journal.target_identity == owner.target_identity
    assert fixture.profile.runtime_root / owner_journal.target_path == owner.target_path

    ini_path = fixture.profile.runtime_root / "CustomConfig/deck_config.ini"
    before = read_deck_config(ini_path, deck_name=fixture.deck_name)
    expected = render_deck_config(
        before,
        deck_name=fixture.deck_name,
        config_dir=owner.target_path.name,
    )
    digest = sha256(expected).hexdigest()
    assert b"OtherDeck = " in expected
    assert digest != owner_journal.next_ini_sha256
    return expected, "sha256:" + digest


def _exercise_prior_owner_ini_history(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: Literal["matched", "mismatch"],
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared, owner = _seed_prior_owner(tmp_path, monkeypatch)
    runtime_root = fixture.profile.runtime_root
    expected_ini, expected_ini_sha256 = _assert_history_fixture(
        fixture=fixture,
        owner=owner,
    )
    target_before = _physical_tree(owner.target_path)
    owner_before = _file_fingerprint(owner.journal_path)
    assert owner_before == owner.journal_fingerprint

    approved = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    frozen = _frozen_identity(approved)
    output_root = derive_deck_output_binding(
        fixture.profile,
        fixture.deck_name,
    ).output_root
    profile_before = _file_fingerprint(operator_profile_path())
    assert profile_before is not None

    oracle_path = tmp_path / f"prior-owner-{case}-ini-history-kill.json"
    _spawn_and_join(
        target=_prior_owner_history_hard_kill_worker,
        args=(str(prepared.run_root), case, str(oracle_path)),
        expected_exitcode=_HARD_EXIT,
        timeout_seconds=360,
    )
    oracle = json.loads(oracle_path.read_bytes())
    assert oracle["fault_value"] == (
        _CLOSED.value if case == "matched" else _EVIDENCE_RETIRED.value
    )
    assert oracle["apply_entry_counts"] == _expected_apply_entry_counts(
        fresh=1,
        install_prepare=1,
        attempt_prepare=1,
    )
    current = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    assert current.to_value() == oracle["session"]
    assert _frozen_identity(current) == frozen

    closed = oracle["closed"]
    assert isinstance(closed, Mapping)
    attempt_id = str(closed["attempt_id"])
    assert attempt_id != owner.transaction_id
    assert closed["current_ini_sha256"] == expected_ini_sha256
    assert closed["historical_owner_ini_sha256"] != expected_ini_sha256
    assert Path(str(closed["owner_path"])) == owner.journal_path
    assert _oracle_fingerprint(closed["owner_fingerprint"]) == owner_before
    assert _file_fingerprint(owner.journal_path) == owner_before
    assert path_identity(owner.target_path) == owner.target_identity
    target_at_kill = _physical_tree(owner.target_path)
    if case == "matched":
        assert target_at_kill == target_before
    else:
        drift = oracle["drift"]
        assert isinstance(drift, Mapping)
        drift_path = Path(str(drift["path"]))
        assert drift_path == owner.target_path / "Mulligan.json"
        assert _file_fingerprint(drift_path) == _oracle_fingerprint(
            drift["fingerprint"]
        )
        assert {
            path
            for path in set(target_before) | set(target_at_kill)
            if target_before.get(path) != target_at_kill.get(path)
        } == {"Mulligan.json"}
        assert target_before["Mulligan.json"][1] == (target_at_kill["Mulligan.json"][1])
    assert tuple(
        path for path in (runtime_root / "CustomConfig").iterdir() if path.is_dir()
    ) == (owner.target_path,)
    assert not tuple((runtime_root / ".hsconfig/staging").iterdir())
    ini_path = runtime_root / "CustomConfig/deck_config.ini"
    assert ini_path.read_bytes() == expected_ini
    assert _file_fingerprint(ini_path)[2] == expected_ini_sha256

    invocation_path = prepared.run_root / "receipts/apply_invocation.json"
    assert tuple(prepared.run_root.rglob("*apply_invocation*.json")) == (
        invocation_path,
    )
    invocation = load_apply_invocation(invocation_path)
    assert invocation.apply_attempt_id == attempt_id
    assert invocation.content_sha256 == current.apply_invocation_sha256
    invocation_before = _file_fingerprint(invocation_path)
    assert invocation_before is not None
    admission = load_runtime_live_attempt_admission()
    assert admission is not None
    assert admission.apply_attempt_id == attempt_id
    admission_before = _file_fingerprint(admission.admission_path)
    assert admission_before is not None

    journal_path = Path(str(closed["journal_path"]))
    fence_path = Path(str(closed["fence_path"]))
    journal_before = _oracle_fingerprint(closed["journal_fingerprint"])
    fence_before = _oracle_fingerprint(closed["fence_fingerprint"])
    assert _file_fingerprint(journal_path) == journal_before
    assert _file_fingerprint(fence_path) == fence_before
    if case == "matched":
        recovery = current.apply_recovery
        assert isinstance(recovery, Mapping)
        assert recovery["recovery_stage"] == "CLOSED"
        assert recovery["runtime_match_status"] == "matched"
        assert current.result_intent is None
        assert current.terminal_status is None
    else:
        intent = current.result_intent
        retirement = current.terminal_retirement
        assert isinstance(intent, Mapping)
        assert intent["deck_config_ini_sha256"] == expected_ini_sha256
        assert isinstance(retirement, Mapping)
        assert retirement["operation"] == "release_committed_mismatch"
        assert retirement["stage"] == "EVIDENCE_RETIRED"

    runtime_at_kill = _physical_tree(runtime_root)
    output_at_kill = _physical_tree(output_root)
    profile_at_kill = _file_fingerprint(operator_profile_path())
    assert profile_at_kill == profile_before

    resume_path = tmp_path / f"prior-owner-{case}-ini-history-resume.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(resume_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    resumed = json.loads(resume_path.read_bytes())
    expected_status = (
        "LIVE_AND_MATCHED" if case == "matched" else "APPLIED_BUT_NOT_VERIFIED"
    )
    assert resumed["status"] == expected_status
    assert resumed["apply_entry_counts"] == _expected_apply_entry_counts(recovery=1)
    terminal = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    assert terminal.content_sha256 == resumed["session_sha256"]
    assert terminal.terminal_status == expected_status
    assert _frozen_identity(terminal) == frozen
    intent = terminal.result_intent
    retirement = terminal.terminal_retirement
    assert isinstance(intent, Mapping)
    assert intent["apply_attempt_id"] == attempt_id
    assert intent["physical_disposition"] == "COMMITTED"
    assert intent["runtime_match_status"] == case
    assert intent["deck_config_ini_sha256"] == expected_ini_sha256
    assert isinstance(retirement, Mapping)
    assert retirement["apply_attempt_id"] == attempt_id
    assert retirement["operation"] == (
        "ack_success" if case == "matched" else "release_committed_mismatch"
    )
    assert retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"
    assert load_runtime_live_attempt_admission() is None
    assert not os.path.lexists(admission.admission_path)
    assert _file_fingerprint(invocation_path) == invocation_before
    assert _file_fingerprint(operator_profile_path()) == profile_before
    assert _physical_tree(output_root) == output_at_kill
    assert _file_fingerprint(owner.journal_path) == owner_before
    assert path_identity(owner.target_path) == owner.target_identity
    assert _physical_tree(owner.target_path) == target_at_kill
    assert ini_path.read_bytes() == expected_ini
    assert _file_fingerprint(ini_path)[2] == expected_ini_sha256
    journals = load_runtime_transaction_journals(runtime_root)
    if case == "matched":
        assert not os.path.lexists(journal_path)
        assert not os.path.lexists(fence_path)
        assert len(journals) == 1
        assert journals[0].transaction_id == owner.transaction_id
        assert journals[0].owns_target is True
    else:
        assert _file_fingerprint(journal_path) == journal_before
        assert _file_fingerprint(fence_path) == fence_before
        assert {row.transaction_id for row in journals} == {
            owner.transaction_id,
            attempt_id,
        }
        assert (
            next(
                row for row in journals if row.transaction_id == owner.transaction_id
            ).owns_target
            is True
        )
        assert (
            next(
                row for row in journals if row.transaction_id == attempt_id
            ).owns_target
            is False
        )
    assert tuple(
        path for path in (runtime_root / "CustomConfig").iterdir() if path.is_dir()
    ) == (owner.target_path,)
    assert not tuple((runtime_root / ".hsconfig/staging").iterdir())

    expected_runtime = dict(runtime_at_kill)
    if case == "matched":
        expected_runtime.pop(journal_path.relative_to(runtime_root).as_posix())
        expected_runtime.pop(fence_path.relative_to(runtime_root).as_posix())
    assert _physical_tree(runtime_root) == expected_runtime

    final_session = (prepared.run_root / "session.json").read_bytes()
    final_result = _result_pair(prepared.run_root)
    final_runtime = _physical_tree(runtime_root)
    replay_path = tmp_path / f"prior-owner-{case}-ini-history-replay.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(replay_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    replay = json.loads(replay_path.read_bytes())
    replay_without_counts = dict(replay)
    resumed_without_counts = dict(resumed)
    assert replay_without_counts.pop("apply_entry_counts") == (
        _expected_apply_entry_counts()
    )
    resumed_without_counts.pop("apply_entry_counts")
    assert replay_without_counts == resumed_without_counts
    assert (prepared.run_root / "session.json").read_bytes() == final_session
    assert _result_pair(prepared.run_root) == final_result
    assert _physical_tree(runtime_root) == final_runtime
    assert _physical_tree(output_root) == output_at_kill
    assert _file_fingerprint(operator_profile_path()) == profile_before
    assert _file_fingerprint(invocation_path) == invocation_before
    assert _file_fingerprint(owner.journal_path) == owner_before
    assert _physical_tree(owner.target_path) == target_at_kill
    if case == "mismatch":
        assert _file_fingerprint(journal_path) == journal_before
        assert _file_fingerprint(fence_path) == fence_before


def test_prior_owner_matched_closed_resume_accepts_current_full_ini_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _exercise_prior_owner_ini_history(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        case="matched",
    )


def test_prior_owner_committed_mismatch_release_accepts_current_full_ini_history(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _exercise_prior_owner_ini_history(
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        case="mismatch",
    )
