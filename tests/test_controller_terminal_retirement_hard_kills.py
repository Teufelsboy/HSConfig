from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
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
    _spawn_and_join,
    _start_apply_entry_observer,
)


_HARD_EXIT = 93
_RESULT_NAMES = ("summary.json", "summary.md")

_OWNING_POINTS = (
    LiveStartFaultPoint.AFTER_TERMINAL_CAS_BEFORE_ACK,
    LiveStartFaultPoint.AFTER_TERMINAL_RETIREMENT_PREPARED,
    LiveStartFaultPoint.AFTER_SUCCESS_ACK_FENCE_DELETE_BEFORE_EVIDENCE_CAS,
    LiveStartFaultPoint.AFTER_ATTEMPT_EVIDENCE_PHYSICAL_RETIREMENT_BEFORE_CAS,
    LiveStartFaultPoint.AFTER_SUCCESS_ACK_EVIDENCE_RETIRED_CAS,
    LiveStartFaultPoint.AFTER_ATTEMPT_EVIDENCE_RETIRED_BEFORE_ADMISSION_RELEASE,
    LiveStartFaultPoint.AFTER_ADMISSION_RELEASE_AUTHORIZED_BEFORE_RUNTIME_ADMISSION_UNLINK,
    LiveStartFaultPoint.AFTER_RUNTIME_ADMISSION_UNLINK,
)

_NONOWNING_POINTS = (
    LiveStartFaultPoint.AFTER_TERMINAL_CAS_BEFORE_ACK,
    LiveStartFaultPoint.AFTER_TERMINAL_RETIREMENT_PREPARED,
    LiveStartFaultPoint.AFTER_SUCCESS_ACK_JOURNAL_DELETE_BEFORE_STAGE_CAS,
    LiveStartFaultPoint.AFTER_SUCCESS_ACK_JOURNAL_RETIRED_CAS,
    LiveStartFaultPoint.AFTER_SUCCESS_ACK_FENCE_DELETE_BEFORE_EVIDENCE_CAS,
    LiveStartFaultPoint.AFTER_ATTEMPT_EVIDENCE_PHYSICAL_RETIREMENT_BEFORE_CAS,
    LiveStartFaultPoint.AFTER_SUCCESS_ACK_EVIDENCE_RETIRED_CAS,
    LiveStartFaultPoint.AFTER_ATTEMPT_EVIDENCE_RETIRED_BEFORE_ADMISSION_RELEASE,
    LiveStartFaultPoint.AFTER_ADMISSION_RELEASE_AUTHORIZED_BEFORE_RUNTIME_ADMISSION_UNLINK,
    LiveStartFaultPoint.AFTER_RUNTIME_ADMISSION_UNLINK,
)


@dataclass(frozen=True, slots=True)
class _PriorOwner:
    transaction_id: str
    journal_path: Path
    journal_fingerprint: tuple[tuple[int, int, int], int, str]
    target_path: Path
    target_identity: tuple[int, int, int]
    target_tree: dict[str, tuple[str, tuple[int, int, int], bytes | None]]


@dataclass(frozen=True, slots=True)
class _TerminalBaseline:
    attempt_id: str
    intent: Mapping[str, Any]
    acknowledgement: Mapping[str, Any]
    invocation_fingerprint: tuple[tuple[int, int, int], int, str]
    result_pair: Mapping[str, tuple[tuple[int, int, int], bytes]]
    profile_fingerprint: tuple[tuple[int, int, int], int, str]
    output_tree: Mapping[str, tuple[str, tuple[int, int, int], bytes | None]]
    runtime_tree: Mapping[str, tuple[str, tuple[int, int, int], bytes | None]]
    admission_fingerprint: tuple[tuple[int, int, int], int, str]
    fence_relative: str
    journal_relative: str
    owner_journal_fingerprint: tuple[tuple[int, int, int], int, str]
    target_identity: tuple[int, int, int]
    target_tree: Mapping[str, tuple[str, tuple[int, int, int], bytes | None]]


def _terminal_retirement_hard_kill_worker(
    session_root_text: str,
    fault_value: str,
    oracle_path_text: str,
) -> None:
    session_root = Path(session_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    selected = LiveStartFaultPoint(fault_value)
    counts, previous_profile = _start_apply_entry_observer()

    def hard_kill(point: LiveStartFaultPoint) -> None:
        if point is not selected:
            return
        session_path = session_root / "session.json"
        persisted = session._load_session_bytes(
            session_path.read_bytes(),
            session_identity=path_identity(session_path),
        )
        _persist_worker_oracle(
            Path(oracle_path_text),
            {
                "fault_value": point.value,
                "session": persisted.to_value(),
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


def _expected_retirement_stage(
    *,
    point: LiveStartFaultPoint,
    owning: bool,
) -> str | None:
    if point is LiveStartFaultPoint.AFTER_TERMINAL_CAS_BEFORE_ACK:
        return None
    if point in {
        LiveStartFaultPoint.AFTER_TERMINAL_RETIREMENT_PREPARED,
        LiveStartFaultPoint.AFTER_SUCCESS_ACK_JOURNAL_DELETE_BEFORE_STAGE_CAS,
    }:
        return "PREPARED"
    if point is LiveStartFaultPoint.AFTER_SUCCESS_ACK_JOURNAL_RETIRED_CAS:
        return "ACK_JOURNAL_RETIRED"
    if point in {
        LiveStartFaultPoint.AFTER_SUCCESS_ACK_FENCE_DELETE_BEFORE_EVIDENCE_CAS,
        LiveStartFaultPoint.AFTER_ATTEMPT_EVIDENCE_PHYSICAL_RETIREMENT_BEFORE_CAS,
    }:
        return "PREPARED" if owning else "ACK_JOURNAL_RETIRED"
    if point in {
        LiveStartFaultPoint.AFTER_SUCCESS_ACK_EVIDENCE_RETIRED_CAS,
        LiveStartFaultPoint.AFTER_ATTEMPT_EVIDENCE_RETIRED_BEFORE_ADMISSION_RELEASE,
    }:
        return "EVIDENCE_RETIRED"
    return "ADMISSION_RELEASE_AUTHORIZED"


def _expected_kill_counts(
    point: LiveStartFaultPoint,
) -> dict[str, int]:
    if point is LiveStartFaultPoint.AFTER_TERMINAL_CAS_BEFORE_ACK:
        return _expected_apply_entry_counts(
            fresh=1,
            install_prepare=1,
            attempt_prepare=1,
        )
    if point is LiveStartFaultPoint.AFTER_RUNTIME_ADMISSION_UNLINK:
        return _expected_apply_entry_counts()
    return _expected_apply_entry_counts(recovery=1)


def _assert_attempt_bindings(
    *,
    current: session.LiveStartSession,
    baseline: _TerminalBaseline,
    session_root: Path,
    owning: bool,
) -> None:
    intent = current.result_intent
    acknowledgement = current.attempt_acknowledgement
    layout = current.runtime_layout_bootstrap
    assert current.terminal_status == "LIVE_AND_MATCHED"
    assert current.pending_transition is None
    assert current.apply_recovery is None
    assert intent == baseline.intent
    assert acknowledgement == baseline.acknowledgement
    assert isinstance(intent, Mapping)
    assert isinstance(acknowledgement, Mapping)
    assert isinstance(layout, Mapping)
    assert layout["apply_attempt_id"] == baseline.attempt_id
    assert intent["apply_attempt_id"] == baseline.attempt_id
    assert acknowledgement["apply_attempt_id"] == baseline.attempt_id
    assert acknowledgement["journal_owns_target"] is owning
    assert acknowledgement["acknowledgement_action"] == (
        "retain_target_owner_delete_fence"
        if owning
        else "delete_nonowning_attempt_and_fence"
    )
    invocation_path = session_root / "receipts/apply_invocation.json"
    invocation = load_apply_invocation(invocation_path)
    assert invocation.apply_attempt_id == baseline.attempt_id
    assert invocation.content_sha256 == current.apply_invocation_sha256
    assert _file_fingerprint(invocation_path) == baseline.invocation_fingerprint
    assert _result_pair(session_root) == baseline.result_pair


def _assert_physical_state(
    *,
    fixture: Any,
    current: session.LiveStartSession,
    baseline: _TerminalBaseline,
    output_root: Path,
    point: LiveStartFaultPoint,
    owning: bool,
    prior_owner: _PriorOwner | None,
) -> None:
    acknowledgement = baseline.acknowledgement
    runtime_root = fixture.profile.runtime_root
    journal_path = Path(str(acknowledgement["journal_path"]))
    owner_path = Path(str(acknowledgement["target_owner_journal_path"]))
    fence_path = Path(str(acknowledgement["retention_fence_path"]))
    admission_path = Path(str(acknowledgement["runtime_admission_path"]))
    target_path = Path(str(acknowledgement["target_path"]))

    journal_retired = not owning and point in _NONOWNING_POINTS[2:]
    fence_retired = point in (_OWNING_POINTS[2:] if owning else _NONOWNING_POINTS[4:])
    admission_retired = point is LiveStartFaultPoint.AFTER_RUNTIME_ADMISSION_UNLINK

    expected_runtime = dict(baseline.runtime_tree)
    if journal_retired:
        del expected_runtime[baseline.journal_relative]
    if fence_retired:
        del expected_runtime[baseline.fence_relative]
    assert _physical_tree(runtime_root) == expected_runtime
    assert _physical_tree(output_root) == baseline.output_tree
    assert _file_fingerprint(operator_profile_path()) == baseline.profile_fingerprint
    assert path_identity(target_path) == baseline.target_identity
    assert _physical_tree(target_path) == baseline.target_tree
    assert _file_fingerprint(owner_path) == baseline.owner_journal_fingerprint
    assert journal_path.exists() is (not journal_retired)
    assert fence_path.exists() is (not fence_retired)
    assert admission_path.exists() is (not admission_retired)
    if not admission_retired:
        assert _file_fingerprint(admission_path) == baseline.admission_fingerprint
    assert (load_runtime_live_attempt_admission() is None) is admission_retired

    journals = {
        journal.transaction_id: journal
        for journal in load_runtime_transaction_journals(runtime_root)
    }
    owner_id = owner_path.stem
    assert journals[owner_id].phase is RuntimeTransactionPhase.FINALIZED
    assert journals[owner_id].owns_target is True
    if owning:
        assert owner_id == baseline.attempt_id
        assert set(journals) == {baseline.attempt_id}
        assert prior_owner is None
    else:
        assert prior_owner is not None
        assert owner_id == prior_owner.transaction_id
        assert baseline.attempt_id != owner_id
        expected_ids = (
            {owner_id} if journal_retired else {owner_id, baseline.attempt_id}
        )
        assert set(journals) == expected_ids
        if not journal_retired:
            assert journals[baseline.attempt_id].owns_target is False
        assert _file_fingerprint(prior_owner.journal_path) == (
            prior_owner.journal_fingerprint
        )
        assert path_identity(prior_owner.target_path) == prior_owner.target_identity
        assert _physical_tree(prior_owner.target_path) == prior_owner.target_tree

    retirement = current.terminal_retirement
    expected_stage = _expected_retirement_stage(point=point, owning=owning)
    if expected_stage is None:
        assert retirement is None
        assert isinstance(current.closed_apply_recovery_commitment, Mapping)
    else:
        assert isinstance(retirement, Mapping)
        assert retirement["operation"] == "ack_success"
        assert retirement["stage"] == expected_stage
        assert retirement["apply_attempt_id"] == baseline.attempt_id
        assert current.closed_apply_recovery_commitment is None


def _capture_terminal_baseline(
    *,
    fixture: Any,
    current: session.LiveStartSession,
    session_root: Path,
    output_root: Path,
) -> _TerminalBaseline:
    intent = current.result_intent
    acknowledgement = current.attempt_acknowledgement
    layout = current.runtime_layout_bootstrap
    assert isinstance(intent, Mapping)
    assert isinstance(acknowledgement, Mapping)
    assert isinstance(layout, Mapping)
    attempt_id = str(layout["apply_attempt_id"])
    assert intent["apply_attempt_id"] == attempt_id
    assert acknowledgement["apply_attempt_id"] == attempt_id
    invocation_path = session_root / "receipts/apply_invocation.json"
    invocation_fingerprint = _file_fingerprint(invocation_path)
    profile_fingerprint = _file_fingerprint(operator_profile_path())
    admission_path = Path(str(acknowledgement["runtime_admission_path"]))
    admission_fingerprint = _file_fingerprint(admission_path)
    owner_path = Path(str(acknowledgement["target_owner_journal_path"]))
    owner_journal_fingerprint = _file_fingerprint(owner_path)
    target_path = Path(str(acknowledgement["target_path"]))
    assert invocation_fingerprint is not None
    assert profile_fingerprint is not None
    assert admission_fingerprint is not None
    assert owner_journal_fingerprint is not None
    runtime_root = fixture.profile.runtime_root
    return _TerminalBaseline(
        attempt_id=attempt_id,
        intent=intent,
        acknowledgement=acknowledgement,
        invocation_fingerprint=invocation_fingerprint,
        result_pair=_result_pair(session_root),
        profile_fingerprint=profile_fingerprint,
        output_tree=_physical_tree(output_root),
        runtime_tree=_physical_tree(runtime_root),
        admission_fingerprint=admission_fingerprint,
        fence_relative=Path(str(acknowledgement["retention_fence_path"]))
        .relative_to(runtime_root)
        .as_posix(),
        journal_relative=Path(str(acknowledgement["journal_path"]))
        .relative_to(runtime_root)
        .as_posix(),
        owner_journal_fingerprint=owner_journal_fingerprint,
        target_identity=path_identity(target_path),
        target_tree=_physical_tree(target_path),
    )


def _seed_prior_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Any, Any, _PriorOwner]:
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
    prior_owner = _PriorOwner(
        transaction_id=owner.transaction_id,
        journal_path=owner_path,
        journal_fingerprint=owner_fingerprint,
        target_path=target_path,
        target_identity=path_identity(target_path),
        target_tree=_physical_tree(target_path),
    )
    ini_path = first_fixture.profile.runtime_root / "CustomConfig/deck_config.ini"
    ini_path.write_text(
        "[CONFIGS]\n"
        "ShadowPriest = shadowpriest-previous\n"
        f"OtherDeck = {target_path.name}",
        encoding="utf-8",
    )
    fixture, prepared = _prepare_approved(
        tmp_path / "second",
        monkeypatch,
        profile=first_fixture.profile,
    )
    return fixture, prepared, prior_owner


def _exercise_terminal_retirement_chain(
    *,
    fixture: Any,
    prepared: Any,
    owning: bool,
    prior_owner: _PriorOwner | None,
) -> None:
    session_root = prepared.run_root
    approved = session.load_live_start_session(
        session_root,
        local_app_data_root=session_root.parents[2],
    )
    frozen = _frozen_identity(approved)
    points = _OWNING_POINTS if owning else _NONOWNING_POINTS
    output_root = derive_deck_output_binding(
        fixture.profile,
        fixture.deck_name,
    ).output_root
    markers = session_root.parent / "terminal-retirement-hard-kills"
    markers.mkdir()
    baseline: _TerminalBaseline | None = None
    for ordinal, point in enumerate(points):
        marker = markers / f"{ordinal:02d}-{point.value}.json"
        _spawn_and_join(
            target=_terminal_retirement_hard_kill_worker,
            args=(str(session_root), point.value, str(marker)),
            expected_exitcode=_HARD_EXIT,
            timeout_seconds=360,
        )
        oracle = json.loads(marker.read_bytes())
        assert oracle["fault_value"] == point.value
        assert oracle["apply_entry_counts"] == _expected_kill_counts(point)
        current = session.load_live_start_session(
            session_root,
            local_app_data_root=session_root.parents[2],
        )
        assert oracle["session"] == current.to_value()
        assert _frozen_identity(current) == frozen
        if baseline is None:
            baseline = _capture_terminal_baseline(
                fixture=fixture,
                current=current,
                session_root=session_root,
                output_root=output_root,
            )
            assert baseline.acknowledgement["journal_owns_target"] is owning
        _assert_attempt_bindings(
            current=current,
            baseline=baseline,
            session_root=session_root,
            owning=owning,
        )
        _assert_physical_state(
            fixture=fixture,
            current=current,
            baseline=baseline,
            output_root=output_root,
            point=point,
            owning=owning,
            prior_owner=prior_owner,
        )

    assert baseline is not None
    final_oracle_path = markers / "final-public-resume.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(session_root), str(final_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    final_oracle = json.loads(final_oracle_path.read_bytes())
    assert final_oracle.pop("apply_entry_counts") == _expected_apply_entry_counts()
    assert final_oracle["status"] == "LIVE_AND_MATCHED"
    terminal = session.load_live_start_session(
        session_root,
        local_app_data_root=session_root.parents[2],
    )
    assert final_oracle["session_sha256"] == terminal.content_sha256
    _assert_attempt_bindings(
        current=terminal,
        baseline=baseline,
        session_root=session_root,
        owning=owning,
    )
    assert isinstance(terminal.terminal_retirement, Mapping)
    assert terminal.terminal_retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"
    assert load_runtime_live_attempt_admission() is None
    _assert_physical_state(
        fixture=fixture,
        current=terminal,
        baseline=baseline,
        output_root=output_root,
        point=LiveStartFaultPoint.AFTER_RUNTIME_ADMISSION_UNLINK,
        owning=owning,
        prior_owner=prior_owner,
    )
    final_session_bytes = (session_root / "session.json").read_bytes()
    final_runtime_tree = _physical_tree(fixture.profile.runtime_root)
    final_output_tree = _physical_tree(output_root)

    replay_oracle_path = markers / "public-replay.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(session_root), str(replay_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    replay_oracle = json.loads(replay_oracle_path.read_bytes())
    assert replay_oracle.pop("apply_entry_counts") == _expected_apply_entry_counts()
    assert replay_oracle == final_oracle
    replayed_terminal = session.load_live_start_session(
        session_root,
        local_app_data_root=session_root.parents[2],
    )
    _assert_attempt_bindings(
        current=replayed_terminal,
        baseline=baseline,
        session_root=session_root,
        owning=owning,
    )
    assert _file_fingerprint(operator_profile_path()) == baseline.profile_fingerprint
    assert (session_root / "session.json").read_bytes() == final_session_bytes
    assert _physical_tree(fixture.profile.runtime_root) == final_runtime_tree
    assert _physical_tree(output_root) == final_output_tree
    assert _result_pair(session_root) == baseline.result_pair


def test_new_target_success_terminal_retirement_hard_kills_resume_each_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "new-target", monkeypatch)
    _exercise_terminal_retirement_chain(
        fixture=fixture,
        prepared=prepared,
        owning=True,
        prior_owner=None,
    )


def test_prior_owner_success_terminal_retirement_hard_kills_resume_each_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared, prior_owner = _seed_prior_owner(tmp_path, monkeypatch)
    _exercise_terminal_retirement_chain(
        fixture=fixture,
        prepared=prepared,
        owning=False,
        prior_owner=prior_owner,
    )
