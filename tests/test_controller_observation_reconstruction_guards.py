from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
from typing import Any, Literal

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig import runtime_installer
from hsconfig.apply_invocation import load_apply_invocation
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.operator_profile import derive_deck_output_binding, operator_profile_path
from hsconfig.package_io import path_identity
from hsconfig.runtime_live_admission import load_runtime_live_attempt_admission
from tests.test_codex_first_live_e2e import _local_state, _prepare_approved
from tests.test_configure_prepublication_apply import _file_fingerprint, _physical_tree
from tests.test_controller_failure_hook_wiring import (
    _fail_before_candidate_and_kill_selection_worker,
)
from tests.test_controller_initial_terminal_observation_hard_kills import (
    _assert_canonical_empty_complete_runtime,
    _assert_optional_fingerprint,
    _assert_preexisting_session_authority_preserved,
    _assert_snapshot_after_exit,
    _json_fingerprint,
    _observation_snapshot,
)
from tests.test_controller_output_hard_kills import (
    _expected_apply_entry_counts,
    _frozen_identity,
    _public_resume_worker,
    _spawn_and_join,
    _start_apply_entry_observer,
)
from tests.test_controller_runtime_hard_kills import _runtime_hard_kill_worker
from tests.test_controller_runtime_hard_kills import (
    _assert_final_state,
    _publication_transaction_snapshot,
)
from tests.test_controller_runtime_action_chain import _runtime_tree
from tests.test_controller_prior_owner_action_chain import _result_pair


_HARD_EXIT = 93
_INITIAL_JOURNAL_BOUND = (
    LiveStartFaultPoint.AFTER_RUNTIME_CANDIDATE_JOURNAL_BOUND_BEFORE_CANDIDATE_CREATE
)
_OUTPUT_HANDOFF = LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_UNLINK
_RESULT_NAMES = ("summary.json", "summary.md")
_ObservationFamily = Literal[
    "first_install",
    "nonterminal_apply",
    "terminal_classification",
    "terminal_resolution",
]


@dataclass(frozen=True, slots=True)
class _ObservationCase:
    family: _ObservationFamily
    hook: LiveStartFaultPoint
    expected_terminal_status: Literal["FAILED_PRESERVED", "LIVE_AND_MATCHED"]
    expected_disposition: Literal["NOT_COMMITTED", "COMMITTED"]
    expected_retirement_operation: str


_CASES = (
    _ObservationCase(
        family="first_install",
        hook=LiveStartFaultPoint.AFTER_FIRST_INSTALL_OBSERVATION_BEFORE_PREPARE_CAS,
        expected_terminal_status="FAILED_PRESERVED",
        expected_disposition="NOT_COMMITTED",
        expected_retirement_operation="release_not_committed",
    ),
    _ObservationCase(
        family="nonterminal_apply",
        hook=LiveStartFaultPoint.AFTER_NONTERMINAL_OBSERVATION_BEFORE_PREPARE_CAS,
        expected_terminal_status="FAILED_PRESERVED",
        expected_disposition="NOT_COMMITTED",
        expected_retirement_operation="release_not_committed",
    ),
    _ObservationCase(
        family="terminal_classification",
        hook=(
            LiveStartFaultPoint.AFTER_TERMINAL_CLASSIFICATION_OBSERVATION_BEFORE_SELECTION_CAS
        ),
        expected_terminal_status="LIVE_AND_MATCHED",
        expected_disposition="COMMITTED",
        expected_retirement_operation="ack_success",
    ),
    _ObservationCase(
        family="terminal_resolution",
        hook=(
            LiveStartFaultPoint.AFTER_TERMINAL_RESOLUTION_OBSERVATION_BEFORE_PREPARE_CAS
        ),
        expected_terminal_status="FAILED_PRESERVED",
        expected_disposition="NOT_COMMITTED",
        expected_retirement_operation="release_resolved_terminal",
    ),
)


def _raw_held_session(session_root: Path) -> session.LiveStartSession:
    session_path = session_root / "session.json"
    return session._load_session_bytes(
        session_path.read_bytes(),
        session_identity=path_identity(session_path),
    )


def _ordinary_observation_value(
    *,
    family: _ObservationFamily,
    predecessor: session.LiveStartSession,
    postcondition: session.RuntimeObservationPostcondition,
) -> object:
    evidence = postcondition.evidence
    if family in {"first_install", "nonterminal_apply"}:
        recovery = evidence.get("apply_recovery")
        assert isinstance(recovery, Mapping)
        return session.RuntimeApplyRecoveryEvidence(recovery)
    if family == "terminal_resolution":
        resolution = evidence.get("terminal_resolution_evidence")
        assert isinstance(resolution, Mapping)
        return session.TerminalResolutionEvidence(resolution)
    recovery = predecessor.apply_recovery
    successor = evidence.get("apply_recovery")
    assert isinstance(recovery, Mapping)
    assert isinstance(successor, Mapping)
    assert successor["action_index"] == recovery["action_index"] + 1
    return runtime_installer.RuntimeFailureSelection(
        disposition="select_terminal_observation",
        expected_recovery_sha256=str(recovery["content_sha256"]),
        expected_action_index=int(recovery["action_index"]),
        expected_action=str(recovery["expected_action"]),
        selected_observation=str(successor["expected_action"]),
    )


def _observation_reconstruction_guard_worker(
    session_root_text: str,
    output_root_text: str,
    family: _ObservationFamily,
    hook_value: str,
    oracle_path_text: str,
) -> None:
    session_root = Path(session_root_text)
    output_root = Path(output_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    selected_hook = LiveStartFaultPoint(hook_value)
    counts, previous_profile = _start_apply_entry_observer()
    apply_observer = sys.getprofile()
    assert apply_observer is not None
    observation_calls: list[str] = []
    hook_seen = False
    failure_count = 0
    snapshot: dict[str, object] | None = None
    rejection_count = 0

    real_first = session.prepare_first_runtime_install_under_lock
    real_nonterminal = session.prepare_nonterminal_apply_recovery_under_lock
    real_advance = session.advance_nonterminal_apply_recovery_under_lock
    real_terminal = session.prepare_terminal_retirement_under_lock

    def observe(frame: Any, event: str, arg: Any) -> None:
        apply_observer(frame, event, arg)
        if (
            event == "call"
            and frame.f_code is session._execute_runtime_observation.__code__
        ):
            observed_family = frame.f_locals.get("observation_family")
            assert isinstance(observed_family, str)
            observation_calls.append(observed_family)

    def fault(point: LiveStartFaultPoint) -> None:
        nonlocal failure_count, hook_seen, snapshot
        if (
            family == "terminal_classification"
            and point
            is LiveStartFaultPoint.AFTER_AUTHORIZATION_CONSUMED_BEFORE_PHYSICAL_CALLBACK
        ):
            current = _raw_held_session(session_root)
            recovery = current.apply_recovery
            if (
                isinstance(recovery, Mapping)
                and recovery.get("expected_action") == "bind_created_candidate"
                and failure_count == 0
            ):
                failure_count += 1
                raise OSError("test-only consumed candidate action failure")
        if point is not selected_hook:
            return
        assert not hook_seen
        assert observation_calls.count(family) == 1
        hook_seen = True
        snapshot = _observation_snapshot(
            session_root=session_root,
            output_root=output_root,
        )

    def reject_reconstructed(
        *,
        receipt: session.RuntimeObservationReceipt,
        session_lease: session.LiveStartSessionLease,
        predecessor: session.LiveStartSession,
        real_consumer: Any,
        consumer_arguments: dict[str, object],
        receipt_argument: str,
    ) -> None:
        nonlocal rejection_count
        assert hook_seen
        assert snapshot is not None
        assert rejection_count == 0
        assert (
            _observation_snapshot(
                session_root=session_root,
                output_root=output_root,
            )
            == snapshot
        )
        postcondition = session._consume_runtime_observation_receipt_under_lock(
            receipt=receipt,
            session_lease=session_lease,
            expected_session=predecessor,
            observation_family=family,
            apply_attempt_id=session._session_apply_attempt_id(predecessor),
        )
        ordinary = _ordinary_observation_value(
            family=family,
            predecessor=predecessor,
            postcondition=postcondition,
        )
        reconstructed_arguments = dict(consumer_arguments)
        reconstructed_arguments[receipt_argument] = ordinary
        try:
            real_consumer(**reconstructed_arguments)
        except session.SessionCapabilityError as error:
            assert error.args == ("live_start_runtime_observation_receipt_forged",)
        else:
            raise AssertionError("ordinary observation evidence reached Session CAS")
        rejection_count += 1
        assert (
            _observation_snapshot(
                session_root=session_root,
                output_root=output_root,
            )
            == snapshot
        )
        _persist_guard_oracle(
            path=Path(oracle_path_text),
            family=family,
            hook=selected_hook,
            ordinary=ordinary,
            observation_calls=observation_calls,
            failure_count=failure_count,
            rejection_count=rejection_count,
            counts=counts,
            snapshot=snapshot,
        )
        os._exit(_HARD_EXIT)

    def guarded_first(*args: object, **kwargs: object) -> session.LiveStartSession:
        if not hook_seen:
            return real_first(*args, **kwargs)
        assert not args
        reject_reconstructed(
            receipt=kwargs["runtime_observation_receipt"],  # type: ignore[arg-type]
            session_lease=kwargs["session_lease"],  # type: ignore[arg-type]
            predecessor=kwargs["expected_apply_started_session"],  # type: ignore[arg-type]
            real_consumer=real_first,
            consumer_arguments=dict(kwargs),
            receipt_argument="runtime_observation_receipt",
        )
        raise AssertionError("unreachable")

    def guarded_nonterminal(
        *args: object, **kwargs: object
    ) -> session.LiveStartSession:
        if not hook_seen:
            return real_nonterminal(*args, **kwargs)
        assert not args
        reject_reconstructed(
            receipt=kwargs["runtime_observation_receipt"],  # type: ignore[arg-type]
            session_lease=kwargs["session_lease"],  # type: ignore[arg-type]
            predecessor=kwargs["expected_nonterminal_session"],  # type: ignore[arg-type]
            real_consumer=real_nonterminal,
            consumer_arguments=dict(kwargs),
            receipt_argument="runtime_observation_receipt",
        )
        raise AssertionError("unreachable")

    def guarded_advance(*args: object, **kwargs: object) -> session.LiveStartSession:
        if (
            not hook_seen
            or kwargs.get("transition") != "select_terminal_classification"
        ):
            return real_advance(*args, **kwargs)
        assert not args
        reject_reconstructed(
            receipt=kwargs["runtime_observation_receipt"],  # type: ignore[arg-type]
            session_lease=kwargs["session_lease"],  # type: ignore[arg-type]
            predecessor=kwargs["expected_recovery_session"],  # type: ignore[arg-type]
            real_consumer=real_advance,
            consumer_arguments=dict(kwargs),
            receipt_argument="runtime_observation_receipt",
        )
        raise AssertionError("unreachable")

    def guarded_terminal(*args: object, **kwargs: object) -> session.LiveStartSession:
        if not hook_seen:
            return real_terminal(*args, **kwargs)
        assert not args
        reject_reconstructed(
            receipt=kwargs["runtime_observation_receipt"],  # type: ignore[arg-type]
            session_lease=kwargs["session_lease"],  # type: ignore[arg-type]
            predecessor=kwargs["expected_terminal_session"],  # type: ignore[arg-type]
            real_consumer=real_terminal,
            consumer_arguments=dict(kwargs),
            receipt_argument="runtime_observation_receipt",
        )
        raise AssertionError("unreachable")

    if family == "first_install":
        session.prepare_first_runtime_install_under_lock = guarded_first
    elif family == "nonterminal_apply":
        session.prepare_nonterminal_apply_recovery_under_lock = guarded_nonterminal
    elif family == "terminal_classification":
        session.advance_nonterminal_apply_recovery_under_lock = guarded_advance
    else:
        session.prepare_terminal_retirement_under_lock = guarded_terminal

    sys.setprofile(observe)
    try:
        controller._finalize_live_start(
            session_root=session_root,
            resume_intake=True,
            fault_hook=fault,
        )
    finally:
        sys.setprofile(previous_profile)
    os._exit(_HARD_EXIT + 1)


def _persist_guard_oracle(
    *,
    path: Path,
    family: _ObservationFamily,
    hook: LiveStartFaultPoint,
    ordinary: object,
    observation_calls: list[str],
    failure_count: int,
    rejection_count: int,
    counts: Mapping[str, int],
    snapshot: Mapping[str, object],
) -> None:
    from tests.test_configure_prepublication_apply import _persist_worker_oracle

    _persist_worker_oracle(
        path,
        {
            "family": family,
            "hook": hook.value,
            "ordinary_type": type(ordinary).__name__,
            "observation_calls": observation_calls,
            "failure_count": failure_count,
            "rejection_count": rejection_count,
            "apply_entry_counts": counts,
            "snapshot": snapshot,
        },
    )


def _prepare_observation_case(
    *,
    base: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: _ObservationCase,
) -> tuple[Any, Any, Path]:
    fixture, prepared = _prepare_approved(base / "approved", monkeypatch)
    output_root = derive_deck_output_binding(
        fixture.profile,
        fixture.deck_name,
    ).output_root
    if case.family == "first_install":
        return fixture, prepared, output_root

    initial_marker = base / "initial-state.json"
    initial_hook = (
        _OUTPUT_HANDOFF
        if case.family == "nonterminal_apply"
        else _INITIAL_JOURNAL_BOUND
    )
    _spawn_and_join(
        target=_runtime_hard_kill_worker,
        args=(str(prepared.run_root), initial_hook.value, 1, str(initial_marker)),
        expected_exitcode=_HARD_EXIT,
        timeout_seconds=360,
    )
    initial = json.loads(initial_marker.read_bytes())
    assert initial["fault_value"] == initial_hook.value
    assert initial["apply_entry_counts"] == _expected_apply_entry_counts(
        fresh=1,
        install_prepare=1,
        attempt_prepare=1,
    )
    if case.family == "nonterminal_apply":
        assert initial["session"]["apply_recovery"] is None
        return fixture, prepared, output_root

    recovery = initial["session"]["apply_recovery"]
    assert isinstance(recovery, dict)
    assert recovery["expected_action"] == "bind_created_candidate"
    assert recovery["successor_candidate_identity"] is None
    if case.family == "terminal_classification":
        return fixture, prepared, output_root

    selection_marker = base / "terminal-selection.json"
    _spawn_and_join(
        target=_fail_before_candidate_and_kill_selection_worker,
        args=(str(prepared.run_root), str(selection_marker)),
        expected_exitcode=_HARD_EXIT,
        timeout_seconds=360,
    )
    selection = json.loads(selection_marker.read_bytes())
    assert selection["failure_count"] == selection["observation_count"] == 1
    assert selection["apply_entry_counts"] == _expected_apply_entry_counts(recovery=1)
    selected = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    assert selected.apply_recovery is not None
    assert selected.apply_recovery["expected_action"] == "observe_not_committed"
    return fixture, prepared, output_root


def _terminal_snapshot(
    *,
    session_root: Path,
    runtime_root: Path,
    output_root: Path,
) -> dict[str, object]:
    return {
        "session": (session_root / "session.json").read_bytes(),
        "result": _result_pair(session_root),
        "run_tree": _physical_tree(session_root),
        "runtime_tree": _physical_tree(runtime_root),
        "output_tree": _physical_tree(output_root),
        "profile": _file_fingerprint(operator_profile_path()),
        "invocation": _file_fingerprint(
            session_root / "receipts" / "apply_invocation.json"
        ),
    }


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.family)
def test_controller_rejects_reconstructed_observation_evidence_before_consuming_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: _ObservationCase,
) -> None:
    case_root = tmp_path / case.family
    case_root.mkdir()
    _local_state(case_root, monkeypatch)
    fixture, prepared, output_root = _prepare_observation_case(
        base=case_root,
        monkeypatch=monkeypatch,
        case=case,
    )
    session_root = prepared.run_root
    runtime_root = fixture.profile.runtime_root
    predecessor = session.load_live_start_session(
        session_root,
        local_app_data_root=session_root.parents[2],
    )
    invocation_path = session_root / "receipts" / "apply_invocation.json"
    preexisting_invocation_fingerprint = _file_fingerprint(invocation_path)
    if case.family == "first_install":
        assert preexisting_invocation_fingerprint is None
        assert predecessor.apply_invocation_sha256 is None
    else:
        preexisting_invocation = load_apply_invocation(invocation_path)
        assert (
            preexisting_invocation.content_sha256 == predecessor.apply_invocation_sha256
        )
        assert preexisting_invocation_fingerprint is not None

    guard_marker = case_root / "reconstruction-guard.json"
    _spawn_and_join(
        target=_observation_reconstruction_guard_worker,
        args=(
            str(session_root),
            str(output_root),
            case.family,
            case.hook.value,
            str(guard_marker),
        ),
        expected_exitcode=_HARD_EXIT,
        timeout_seconds=360,
    )
    oracle = json.loads(guard_marker.read_bytes())
    assert oracle["family"] == case.family
    assert oracle["hook"] == case.hook.value
    assert (
        oracle["ordinary_type"]
        == {
            "first_install": "RuntimeApplyRecoveryEvidence",
            "nonterminal_apply": "RuntimeApplyRecoveryEvidence",
            "terminal_classification": "RuntimeFailureSelection",
            "terminal_resolution": "TerminalResolutionEvidence",
        }[case.family]
    )
    assert oracle["observation_calls"] == [case.family]
    assert oracle["failure_count"] == (
        1 if case.family == "terminal_classification" else 0
    )
    assert oracle["rejection_count"] == 1
    assert oracle["apply_entry_counts"] == (
        _expected_apply_entry_counts(
            fresh=1,
            install_prepare=1,
            attempt_prepare=1,
        )
        if case.family == "first_install"
        else _expected_apply_entry_counts(recovery=1)
    )
    guard_snapshot = oracle["snapshot"]
    guarded = _assert_snapshot_after_exit(
        session_root=session_root,
        output_root=output_root,
        snapshot=guard_snapshot,
    )
    if case.family in {"nonterminal_apply", "terminal_classification"}:
        assert guarded.to_value() == predecessor.to_value()
    invocation = load_apply_invocation(invocation_path)
    attempt_id = invocation.apply_attempt_id
    invocation_fingerprint = _file_fingerprint(invocation_path)
    assert invocation_fingerprint is not None
    assert invocation_fingerprint == _json_fingerprint(
        guard_snapshot["invocation_fingerprint"]
    )
    if preexisting_invocation_fingerprint is not None:
        assert invocation_fingerprint == preexisting_invocation_fingerprint
    assert guarded.apply_invocation_sha256 == invocation.content_sha256
    assert guarded.runtime_layout_bootstrap["apply_attempt_id"] == attempt_id
    assert guarded.runtime_admission_binding is not None
    admission = load_runtime_live_attempt_admission()
    assert admission is not None
    assert guarded.runtime_admission_binding["admission_path"] == str(
        admission.admission_path
    )
    frozen_identity = _frozen_identity(guarded)
    publication_at_guard = _physical_tree(output_root)
    publication_transactions_at_guard = _publication_transaction_snapshot(output_root)
    profile_at_guard = _file_fingerprint(operator_profile_path())
    assert profile_at_guard is not None

    resume_marker = case_root / "public-resume.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(session_root), str(resume_marker)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    resumed = json.loads(resume_marker.read_bytes())
    assert resumed["status"] == case.expected_terminal_status
    assert resumed.pop("apply_entry_counts") == _expected_apply_entry_counts(recovery=1)
    terminal = session.load_live_start_session(
        session_root,
        local_app_data_root=session_root.parents[2],
    )
    assert terminal.content_sha256 == resumed["session_sha256"]
    assert terminal.terminal_status == case.expected_terminal_status
    assert terminal.result_intent["apply_attempt_id"] == attempt_id
    assert terminal.result_intent["physical_disposition"] == case.expected_disposition
    assert (
        terminal.terminal_retirement["operation"] == case.expected_retirement_operation
    )
    assert terminal.terminal_retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"
    assert terminal.apply_recovery is None
    assert load_runtime_live_attempt_admission() is None
    _assert_preexisting_session_authority_preserved(
        predecessor_value=guard_snapshot["session"],
        terminal=terminal,
    )
    final_invocation = load_apply_invocation(invocation_path)
    assert final_invocation.apply_attempt_id == attempt_id
    assert final_invocation.content_sha256 == invocation.content_sha256
    assert _file_fingerprint(invocation_path) == invocation_fingerprint
    assert tuple(session_root.rglob("*apply_invocation*.json")) == (invocation_path,)
    if case.expected_terminal_status == "LIVE_AND_MATCHED":
        asserted_terminal = _assert_final_state(
            fixture=fixture,
            session_root=session_root,
            frozen_identity=frozen_identity,
            output_root=output_root,
            publication_at_kill=publication_at_guard,
            publication_transactions_at_kill=publication_transactions_at_guard,
            profile_before=profile_at_guard,
            expected_attempt_id=attempt_id,
            expected_owner_id=None,
            prior_owner_state=None,
        )
        assert asserted_terminal.content_sha256 == terminal.content_sha256
        assert terminal.result_intent["runtime_match_status"] == "matched"
        assert terminal.attempt_acknowledgement["apply_attempt_id"] == attempt_id
    else:
        assert terminal.result_intent["runtime_match_status"] == "not_run"
        assert terminal.attempt_acknowledgement is None
        _assert_canonical_empty_complete_runtime(
            current=terminal,
            runtime_tree=_runtime_tree(
                runtime_root,
                held_lock_path=runtime_root / ".hsconfig" / "apply.lock",
            ),
        )
        assert (
            _runtime_tree(output_root, held_lock_path=None)
            == guard_snapshot["output_tree"]
        )
        assert (
            _publication_transaction_snapshot(output_root)
            == publication_transactions_at_guard
        )
        _assert_optional_fingerprint(
            operator_profile_path(),
            guard_snapshot["profile_fingerprint"],
        )
    if case.family == "terminal_resolution":
        result_fingerprints = guard_snapshot["result_fingerprints"]
        assert isinstance(result_fingerprints, Mapping)
        for name in _RESULT_NAMES:
            _assert_optional_fingerprint(
                session_root / "result" / name,
                result_fingerprints[name],
            )

    frozen_terminal = _terminal_snapshot(
        session_root=session_root,
        runtime_root=runtime_root,
        output_root=output_root,
    )
    replay_marker = case_root / "public-replay.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(session_root), str(replay_marker)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    replayed = json.loads(replay_marker.read_bytes())
    assert replayed.pop("apply_entry_counts") == _expected_apply_entry_counts()
    assert replayed == resumed
    assert (
        _terminal_snapshot(
            session_root=session_root,
            runtime_root=runtime_root,
            output_root=output_root,
        )
        == frozen_terminal
    )
