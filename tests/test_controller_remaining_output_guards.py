from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
from typing import Any

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig import output_publisher as publisher
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.operator_profile import (
    derive_deck_output_binding,
    load_operator_profile,
    operator_profile_path,
)
from hsconfig.output_operation_admission import (
    build_output_operation_admission_bytes,
    lease_output_operation_admission,
    observe_output_operation_admission_under_lease,
    output_operation_admission_path,
    output_operation_admission_reserved_temp_path,
    output_operation_admission_staging_path,
)
from hsconfig.output_publisher import output_child_claim_path
from hsconfig.package_io import path_identity
from hsconfig.runtime_live_admission import load_runtime_live_attempt_admission
from hsconfig.runtime_transaction_journal import load_runtime_transaction_journals
from tests.test_codex_first_live_e2e import _local_state, _prepare_approved
from tests.test_configure_prepublication_apply import (
    _file_fingerprint,
    _persist_worker_oracle,
    _physical_tree,
)
from tests.test_controller_output_hard_kills import (
    _OUTPUT_CHILD_CASES,
    _assert_interrupted_state,
    _expected_apply_entry_counts,
    _frozen_identity,
    _output_hard_kill_worker,
    _publication_snapshot,
    _public_resume_worker,
    _runtime_payload_tree,
    _session_projection,
    _sha256_bytes,
    _spawn_and_join,
    _start_apply_entry_observer,
)


_HARD_EXIT = 93
_PROCESS_TIMEOUT_SECONDS = 360
_FOREIGN_RUN_ID = "f" * 32


def _load_raw_session(session_root: Path) -> session.LiveStartSession:
    session_path = session_root / "session.json"
    return session._load_session_bytes(
        session_path.read_bytes(),
        session_identity=path_identity(session_path),
    )


def _result_pair(session_root: Path) -> dict[str, bytes]:
    return {
        name: (session_root / "result" / name).read_bytes()
        for name in ("summary.json", "summary.md")
    }


def _assert_single_finalized_publication(
    *,
    current: session.LiveStartSession,
    output_root: Path,
) -> None:
    operation = current.output_operation_admission_binding
    child = current.output_child_binding
    publication = current.publication_binding
    assert isinstance(operation, Mapping)
    assert isinstance(child, Mapping)
    assert isinstance(publication, Mapping)
    transactions = publisher._load_valid_transactions(output_root)
    assert len(transactions) == 1
    _transaction_path, transaction = transactions[0]
    assert transaction.phase == "finalized"
    assert transaction.owns_revision is True
    assert transaction.revision == publication["revision"]
    receipt = transaction.live_start_commit_receipt
    assert receipt is not None
    assert receipt.operation_admission_identity == tuple(
        operation["admission_identity"]
    )
    assert receipt.operation_admission_sha256 == operation["admission_sha256"]
    assert child["claim_state"] == "RETIRED"
    assert child["claim_identity"] is None
    assert child["claim_sha256"] is None
    assert publication["output_child_binding_sha256"] == child["content_sha256"]
    assert receipt.output_child_identity == tuple(child["output_child_identity"])


def _public_resume_error_worker(
    session_root_text: str,
    oracle_path_text: str,
) -> None:
    session_root = Path(session_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    apply_entry_counts, previous_profile = _start_apply_entry_observer()
    try:
        try:
            controller.resume_live_start(session_root=session_root)
        except Exception as error:
            persisted = _load_raw_session(session_root)
            oracle = {
                "error_type": type(error).__name__,
                "error_message": str(error),
                "session_sha256": persisted.content_sha256,
                "apply_entry_counts": apply_entry_counts,
            }
        else:
            raise AssertionError("public resume unexpectedly succeeded")
    finally:
        sys.setprofile(previous_profile)
    _persist_worker_oracle(Path(oracle_path_text), oracle)


def _output_child_expectation(point: LiveStartFaultPoint) -> Any:
    return next(
        expectation
        for candidate, expectation in _OUTPUT_CHILD_CASES
        if candidate is point
    )


def _assert_preview_cursor(
    *,
    current: session.LiveStartSession,
    frozen: dict[str, object],
    output_root: Path,
    expected_operation_state: str,
    operation_present: bool,
) -> None:
    assert current.phase is session.LiveStartPhase.PUBLICATION_COMMITTED
    assert current.terminal_status == "PREVIEW_READY"
    assert current.result_intent["terminal_status"] == "PREVIEW_READY"
    assert current.result_intent["physical_disposition"] is None
    assert current.result_intent["runtime_match_status"] == "not_run"
    assert current.result_intent["apply_attempt_id"] is None
    assert current.pending_transition is None
    assert current.apply_invocation_sha256 is None
    assert current.runtime_admission_binding is None
    assert current.runtime_layout_bootstrap is None
    assert current.apply_recovery is None
    assert current.closed_apply_recovery_commitment is None
    assert current.attempt_acknowledgement is None
    assert current.terminal_retirement is None
    assert _frozen_identity(current) == frozen
    operation = current.output_operation_admission_binding
    child = current.output_child_binding
    publication = current.publication_binding
    assert isinstance(operation, Mapping)
    assert operation["state"] == expected_operation_state
    assert isinstance(child, Mapping)
    assert child["claim_state"] == "RETIRED"
    assert isinstance(publication, Mapping)
    assert publication["output_child_path"] == str(output_root)
    assert tuple(publication["output_child_identity"]) == path_identity(output_root)
    assert output_operation_admission_path().is_file() is operation_present
    if operation_present:
        assert path_identity(output_operation_admission_path()) == tuple(
            operation["admission_identity"]
        )
    assert not output_operation_admission_staging_path().exists()
    assert not output_operation_admission_reserved_temp_path().exists()
    assert not output_child_claim_path(output_root).exists()
    assert (output_root / "current.json").is_file()
    _assert_single_finalized_publication(current=current, output_root=output_root)


def test_preview_releases_output_operation_only_after_terminal_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(
        tmp_path / "preview",
        monkeypatch,
        preview=True,
    )
    approved = session.load_live_start_session(prepared.run_root)
    frozen = _frozen_identity(approved)
    profile_before = _file_fingerprint(operator_profile_path())
    assert profile_before is not None
    inputs_before = _physical_tree(prepared.run_root / "inputs")
    runtime_before = _physical_tree(fixture.profile.runtime_root)
    assert set(runtime_before) == {"."}
    output_root = derive_deck_output_binding(
        fixture.profile,
        fixture.deck_name,
    ).output_root

    points = (
        (
            LiveStartFaultPoint.AFTER_TERMINAL_CAS_BEFORE_ACK,
            "ACTIVE",
            True,
        ),
        (
            LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_RELEASE_AUTHORIZED,
            "TERMINAL_RELEASE_AUTHORIZED",
            True,
        ),
        (
            LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_UNLINK,
            "TERMINAL_RELEASE_AUTHORIZED",
            False,
        ),
    )
    result_pair: dict[str, bytes] | None = None
    result_tree: dict[str, object] | None = None
    publication_tree: dict[str, object] | None = None
    output_base_tree: dict[str, object] | None = None
    operation_fingerprint = None
    previous_session_bytes: bytes | None = None

    for ordinal, (point, expected_state, operation_present) in enumerate(points):
        oracle_path = tmp_path / f"preview-{ordinal:02d}.json"
        _spawn_and_join(
            target=_output_hard_kill_worker,
            args=(str(prepared.run_root), point.value, str(oracle_path)),
            expected_exitcode=_HARD_EXIT,
            timeout_seconds=_PROCESS_TIMEOUT_SECONDS,
        )
        interrupted = session.load_live_start_session(prepared.run_root)
        oracle = json.loads(oracle_path.read_bytes())
        assert oracle.pop("fault_value") == point.value
        assert oracle.pop("apply_entry_counts") == _expected_apply_entry_counts()
        assert oracle.pop("runtime_apply_lock_metadata") is None
        assert oracle == _session_projection(interrupted)
        _assert_preview_cursor(
            current=interrupted,
            frozen=frozen,
            output_root=output_root,
            expected_operation_state=expected_state,
            operation_present=operation_present,
        )
        assert _file_fingerprint(operator_profile_path()) == profile_before
        assert _physical_tree(prepared.run_root / "inputs") == inputs_before
        assert _physical_tree(fixture.profile.runtime_root) == runtime_before
        assert load_runtime_live_attempt_admission() is None
        assert load_runtime_transaction_journals(fixture.profile.runtime_root) == ()

        current_pair = _result_pair(prepared.run_root)
        current_publication_tree = _physical_tree(output_root)
        if result_pair is None:
            result_pair = current_pair
            result_tree = _physical_tree(prepared.run_root / "result")
            publication_tree = current_publication_tree
            output_base_tree = _physical_tree(fixture.profile.output_base_root)
            operation_fingerprint = _file_fingerprint(output_operation_admission_path())
            assert operation_fingerprint is not None
        else:
            assert current_pair == result_pair
            assert _physical_tree(prepared.run_root / "result") == result_tree
            assert current_publication_tree == publication_tree
            assert _physical_tree(fixture.profile.output_base_root) == (
                output_base_tree
            )
        if operation_present:
            assert _file_fingerprint(output_operation_admission_path()) == (
                operation_fingerprint
            )
        else:
            assert _file_fingerprint(output_operation_admission_path()) is None
        current_session_bytes = (prepared.run_root / "session.json").read_bytes()
        if ordinal == 2:
            assert current_session_bytes == previous_session_bytes
        previous_session_bytes = current_session_bytes

    assert result_pair is not None
    assert publication_tree is not None
    assert output_base_tree is not None
    terminal_tree = _physical_tree(prepared.run_root)
    terminal_session_bytes = (prepared.run_root / "session.json").read_bytes()
    resume_oracle_path = tmp_path / "preview-public-resume.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(resume_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=_PROCESS_TIMEOUT_SECONDS,
    )
    resume_oracle = json.loads(resume_oracle_path.read_bytes())
    assert resume_oracle.pop("apply_entry_counts") == _expected_apply_entry_counts()
    assert resume_oracle["status"] == "PREVIEW_READY"
    assert resume_oracle["run_root"] == str(prepared.run_root)
    assert resume_oracle["summary_sha256"] == _sha256_bytes(result_pair["summary.json"])
    assert (prepared.run_root / "session.json").read_bytes() == (terminal_session_bytes)
    assert _physical_tree(prepared.run_root) == terminal_tree
    assert _physical_tree(output_root) == publication_tree
    assert _physical_tree(fixture.profile.output_base_root) == output_base_tree
    assert _physical_tree(fixture.profile.runtime_root) == runtime_before
    assert _physical_tree(prepared.run_root / "inputs") == inputs_before

    replay_oracle_path = tmp_path / "preview-public-replay.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(replay_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=_PROCESS_TIMEOUT_SECONDS,
    )
    replay_oracle = json.loads(replay_oracle_path.read_bytes())
    assert replay_oracle.pop("apply_entry_counts") == _expected_apply_entry_counts()
    assert replay_oracle == resume_oracle
    assert (prepared.run_root / "session.json").read_bytes() == (terminal_session_bytes)
    assert _physical_tree(prepared.run_root) == terminal_tree
    assert _physical_tree(output_root) == publication_tree
    assert _physical_tree(fixture.profile.output_base_root) == output_base_tree
    assert _physical_tree(fixture.profile.runtime_root) == runtime_before
    assert _physical_tree(prepared.run_root / "inputs") == inputs_before
    assert _file_fingerprint(operator_profile_path()) == profile_before
    assert not output_operation_admission_path().exists()


def _foreign_output_operation_bytes(historical: Any) -> bytes:
    return build_output_operation_admission_bytes(
        run_id=_FOREIGN_RUN_ID,
        session_root=historical.session_root,
        session_root_identity=historical.session_root_identity,
        expected_session_sha256=historical.expected_session_sha256,
        operator_profile=load_operator_profile(),
        operator_profile_path=historical.operator_profile_path,
        operator_profile_parent_identity=(historical.operator_profile_parent_identity),
        operator_profile_identity=historical.operator_profile_identity,
        state_root_identity=historical.state_root_identity,
        output_base_root=historical.output_base_root,
        output_base_root_identity=historical.output_base_root_identity,
        output_child_path=historical.output_child_path,
        output_child_predecessor_state=(historical.output_child_predecessor_state),
        output_child_predecessor_identity=(
            historical.output_child_predecessor_identity
        ),
        output_bootstrap_lock_path=historical.output_bootstrap_lock_path,
        output_bootstrap_lock_identity=(historical.output_bootstrap_lock_identity),
        output_claim_path=historical.output_claim_path,
    )


def test_valid_foreign_output_operation_successor_is_never_deleted_by_old_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "owner", monkeypatch)
    approved = session.load_live_start_session(prepared.run_root)
    frozen = _frozen_identity(approved)
    profile_before = _file_fingerprint(operator_profile_path())
    assert profile_before is not None
    inputs_before = _physical_tree(prepared.run_root / "inputs")
    output_root = derive_deck_output_binding(
        fixture.profile,
        fixture.deck_name,
    ).output_root
    kill_oracle_path = tmp_path / "owner-release-authorized.json"

    _spawn_and_join(
        target=_output_hard_kill_worker,
        args=(
            str(prepared.run_root),
            LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_RELEASE_AUTHORIZED.value,
            str(kill_oracle_path),
        ),
        expected_exitcode=_HARD_EXIT,
        timeout_seconds=_PROCESS_TIMEOUT_SECONDS,
    )
    interrupted = session.load_live_start_session(prepared.run_root)
    kill_oracle = json.loads(kill_oracle_path.read_bytes())
    assert kill_oracle.pop("fault_value") == (
        LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_RELEASE_AUTHORIZED.value
    )
    assert kill_oracle.pop("apply_entry_counts") == _expected_apply_entry_counts(
        fresh=1,
        install_prepare=1,
        attempt_prepare=1,
    )
    assert kill_oracle.pop("runtime_apply_lock_metadata") is not None
    assert kill_oracle == _session_projection(interrupted)
    assert _frozen_identity(interrupted) == frozen
    assert interrupted.phase is session.LiveStartPhase.APPLY_STARTED
    assert interrupted.pending_transition is None
    assert interrupted.apply_recovery is None
    assert interrupted.result_intent is None
    operation = interrupted.output_operation_admission_binding
    runtime_admission = interrupted.runtime_admission_binding
    layout = interrupted.runtime_layout_bootstrap
    assert isinstance(operation, Mapping)
    assert operation["state"] == "RUNTIME_HANDOFF_RELEASE_AUTHORIZED"
    assert isinstance(runtime_admission, Mapping)
    assert isinstance(layout, Mapping)
    assert layout["stage"] == "COMPLETE"

    operation_path = output_operation_admission_path()
    with lease_output_operation_admission() as operation_lease:
        historical = observe_output_operation_admission_under_lease(operation_lease)
    assert historical is not None
    assert historical.run_id == interrupted.run_id
    historical_fingerprint = _file_fingerprint(operation_path)
    assert historical_fingerprint is not None
    assert historical_fingerprint[0] == tuple(operation["admission_identity"])

    publication_at_kill = _publication_snapshot(output_root)
    publication_tree_at_kill = _physical_tree(output_root)
    runtime_tree_at_kill = _runtime_payload_tree(fixture.profile.runtime_root)
    invocation_path = prepared.run_root / "receipts/apply_invocation.json"
    invocation_fingerprint = _file_fingerprint(invocation_path)
    assert invocation_fingerprint is not None
    child_binding = interrupted.output_child_binding
    publication_binding = interrupted.publication_binding
    assert isinstance(child_binding, Mapping)
    assert child_binding["claim_state"] == "RETIRED"
    assert isinstance(publication_binding, Mapping)

    held_old = tmp_path / "held-old-output-operation-admission.json"
    operation_path.rename(held_old)
    assert _file_fingerprint(held_old) == historical_fingerprint
    foreign_raw = _foreign_output_operation_bytes(historical)
    with operation_path.open("xb") as stream:
        stream.write(foreign_raw)
        stream.flush()
        os.fsync(stream.fileno())
    foreign_fingerprint = _file_fingerprint(operation_path)
    assert foreign_fingerprint is not None
    assert foreign_fingerprint[0] != historical_fingerprint[0]
    assert foreign_fingerprint[2] != historical_fingerprint[2]
    with lease_output_operation_admission() as operation_lease:
        foreign = observe_output_operation_admission_under_lease(operation_lease)
    assert foreign is not None
    assert foreign.run_id == _FOREIGN_RUN_ID
    assert foreign.admission_identity == foreign_fingerprint[0]
    assert (
        replace(
            foreign,
            admission_identity=historical.admission_identity,
            admission_sha256=historical.admission_sha256,
            run_id=historical.run_id,
        )
        == historical
    )
    assert foreign.state == "ACTIVE"
    assert foreign.session_root == historical.session_root
    assert foreign.session_root_identity == historical.session_root_identity
    assert foreign.operator_profile_path == historical.operator_profile_path
    assert foreign.operator_profile_identity == historical.operator_profile_identity
    assert foreign.operator_profile_sha256 == historical.operator_profile_sha256
    assert foreign.state_root_identity == historical.state_root_identity
    assert foreign.output_base_root == historical.output_base_root
    assert foreign.output_base_root_identity == historical.output_base_root_identity
    assert foreign.output_child_path == historical.output_child_path
    assert (
        foreign.output_child_predecessor_state
        == historical.output_child_predecessor_state
    )
    assert (
        foreign.output_child_predecessor_identity
        == historical.output_child_predecessor_identity
    )
    assert foreign.output_bootstrap_lock_path == (historical.output_bootstrap_lock_path)
    assert foreign.output_bootstrap_lock_identity == (
        historical.output_bootstrap_lock_identity
    )
    assert foreign.output_claim_path == historical.output_claim_path
    assert operation_path.read_bytes() == foreign_raw

    resume_oracle_path = tmp_path / "foreign-public-resume.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(resume_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=_PROCESS_TIMEOUT_SECONDS,
    )
    resume_oracle = json.loads(resume_oracle_path.read_bytes())
    resume_counts = resume_oracle.pop("apply_entry_counts")
    assert resume_counts == _expected_apply_entry_counts(recovery=1)
    assert resume_oracle["status"] == "FAILED_PRESERVED"
    assert resume_oracle["run_root"] == str(prepared.run_root)

    terminal = session.load_live_start_session(prepared.run_root)
    assert terminal.phase is session.LiveStartPhase.APPLY_STARTED
    assert terminal.terminal_status == "FAILED_PRESERVED"
    assert _frozen_identity(terminal) == frozen
    assert terminal.output_operation_admission_binding == operation
    assert terminal.output_child_binding == child_binding
    assert terminal.publication_binding == publication_binding
    assert terminal.runtime_admission_binding == runtime_admission
    assert terminal.runtime_layout_bootstrap == layout
    assert terminal.apply_invocation_sha256 == (interrupted.apply_invocation_sha256)
    assert terminal.pending_transition is None
    assert terminal.apply_recovery is None
    assert terminal.closed_apply_recovery_commitment is None
    assert terminal.attempt_acknowledgement is None
    intent = terminal.result_intent
    retirement = terminal.terminal_retirement
    assert isinstance(intent, Mapping)
    assert intent["terminal_status"] == "FAILED_PRESERVED"
    assert intent["physical_disposition"] == "NOT_COMMITTED"
    assert intent["raw_apply_status"] is None
    assert intent["runtime_match_status"] == "not_run"
    assert intent["runtime_match_sha256"] is None
    assert intent["error_code"] == "apply_not_committed"
    assert intent["apply_attempt_id"] == layout["apply_attempt_id"]
    assert isinstance(retirement, Mapping)
    assert retirement["operation"] == "release_not_committed"
    assert retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"
    assert retirement["apply_attempt_id"] == layout["apply_attempt_id"]
    assert retirement["result_intent_sha256"] == intent["content_sha256"]

    assert _file_fingerprint(operator_profile_path()) == profile_before
    assert _physical_tree(prepared.run_root / "inputs") == inputs_before
    assert _publication_snapshot(output_root) == publication_at_kill
    assert _physical_tree(output_root) == publication_tree_at_kill
    assert _runtime_payload_tree(fixture.profile.runtime_root) == (runtime_tree_at_kill)
    assert _file_fingerprint(invocation_path) == invocation_fingerprint
    assert load_runtime_transaction_journals(fixture.profile.runtime_root) == ()
    assert load_runtime_live_attempt_admission() is None
    assert not Path(str(runtime_admission["admission_path"])).exists()
    assert not output_operation_admission_staging_path().exists()
    assert not output_operation_admission_reserved_temp_path().exists()
    assert not output_child_claim_path(output_root).exists()
    assert _file_fingerprint(held_old) == historical_fingerprint
    assert _file_fingerprint(operation_path) == foreign_fingerprint
    assert operation_path.read_bytes() == foreign_raw

    assert _file_fingerprint(operator_profile_path()) == profile_before
    _assert_single_finalized_publication(current=terminal, output_root=output_root)
    assert tuple(prepared.run_root.rglob("*apply_invocation*.json")) == (
        invocation_path,
    )

    result_pair = _result_pair(prepared.run_root)
    assert resume_oracle["summary_sha256"] == _sha256_bytes(result_pair["summary.json"])
    assert resume_oracle["session_sha256"] == terminal.content_sha256
    final_session_bytes = (prepared.run_root / "session.json").read_bytes()
    final_run_tree = _physical_tree(prepared.run_root)
    final_runtime_tree = _physical_tree(fixture.profile.runtime_root)
    final_output_tree = _physical_tree(output_root)

    replay_oracle_path = tmp_path / "foreign-public-replay.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(replay_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=_PROCESS_TIMEOUT_SECONDS,
    )
    replay_oracle = json.loads(replay_oracle_path.read_bytes())
    assert replay_oracle.pop("apply_entry_counts") == _expected_apply_entry_counts()
    assert replay_oracle == resume_oracle
    assert (prepared.run_root / "session.json").read_bytes() == final_session_bytes
    assert _physical_tree(prepared.run_root) == final_run_tree
    assert _physical_tree(fixture.profile.runtime_root) == final_runtime_tree
    assert _physical_tree(output_root) == final_output_tree
    assert _physical_tree(prepared.run_root / "inputs") == inputs_before
    assert _result_pair(prepared.run_root) == result_pair
    assert _file_fingerprint(held_old) == historical_fingerprint
    assert _file_fingerprint(operation_path) == foreign_fingerprint
    assert operation_path.read_bytes() == foreign_raw
    assert _file_fingerprint(operator_profile_path()) == profile_before


def test_output_child_replacement_after_bound_never_reaches_admission_or_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "replacement", monkeypatch)
    approved = session.load_live_start_session(prepared.run_root)
    frozen = _frozen_identity(approved)
    profile_before = _file_fingerprint(operator_profile_path())
    assert profile_before is not None
    inputs_before = _physical_tree(prepared.run_root / "inputs")
    runtime_before = _runtime_payload_tree(fixture.profile.runtime_root)
    output_root = derive_deck_output_binding(
        fixture.profile,
        fixture.deck_name,
    ).output_root
    kill_oracle_path = tmp_path / "output-child-bound.json"

    _spawn_and_join(
        target=_output_hard_kill_worker,
        args=(
            str(prepared.run_root),
            LiveStartFaultPoint.AFTER_OUTPUT_CHILD_BOUND.value,
            str(kill_oracle_path),
        ),
        expected_exitcode=_HARD_EXIT,
        timeout_seconds=_PROCESS_TIMEOUT_SECONDS,
    )
    interrupted = session.load_live_start_session(prepared.run_root)
    oracle = json.loads(kill_oracle_path.read_bytes())
    assert (
        oracle.pop("fault_value") == LiveStartFaultPoint.AFTER_OUTPUT_CHILD_BOUND.value
    )
    assert oracle.pop("apply_entry_counts") == _expected_apply_entry_counts()
    runtime_lock_metadata = oracle.pop("runtime_apply_lock_metadata")
    assert runtime_lock_metadata is None
    assert oracle == _session_projection(interrupted)
    _assert_interrupted_state(
        interrupted=interrupted,
        expectation=_output_child_expectation(
            LiveStartFaultPoint.AFTER_OUTPUT_CHILD_BOUND
        ),
        output_root=output_root,
        runtime_root=fixture.profile.runtime_root,
        runtime_payload_before=runtime_before,
        runtime_apply_lock_metadata=runtime_lock_metadata,
        profile_before=profile_before,
    )
    assert _frozen_identity(interrupted) == frozen
    assert set(_physical_tree(output_root)) == {"."}
    child = interrupted.output_child_binding
    operation = interrupted.output_operation_admission_binding
    assert isinstance(child, Mapping)
    assert isinstance(operation, Mapping)
    old_child_identity = tuple(child["output_child_identity"])
    operation_fingerprint = _file_fingerprint(output_operation_admission_path())
    claim_fingerprint = _file_fingerprint(output_child_claim_path(output_root))
    assert operation_fingerprint is not None
    assert claim_fingerprint is not None
    interrupted_session_bytes = (prepared.run_root / "session.json").read_bytes()
    interrupted_session_tree = _physical_tree(prepared.run_root)

    held_original = tmp_path / "held-original-output-child"
    output_root.rename(held_original)
    output_root.mkdir()
    replacement_identity = path_identity(output_root)
    assert replacement_identity != old_child_identity
    assert path_identity(held_original) == old_child_identity
    assert set(_physical_tree(held_original)) == {"."}
    assert set(_physical_tree(output_root)) == {"."}
    replacement_tree = _physical_tree(output_root)
    held_tree = _physical_tree(held_original)
    output_base_tree = _physical_tree(fixture.profile.output_base_root)

    error_oracle_path = tmp_path / "replacement-public-resume.json"
    _spawn_and_join(
        target=_public_resume_error_worker,
        args=(str(prepared.run_root), str(error_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=_PROCESS_TIMEOUT_SECONDS,
    )
    error_oracle = json.loads(error_oracle_path.read_bytes())
    assert error_oracle.pop("apply_entry_counts") == _expected_apply_entry_counts()
    assert error_oracle == {
        "error_type": "ValueError",
        "error_message": "live_start_output_child_identity_changed",
        "session_sha256": interrupted.content_sha256,
    }
    preserved = session.load_live_start_session(prepared.run_root)
    assert preserved == interrupted
    assert preserved.canonical_json == interrupted.canonical_json
    assert (prepared.run_root / "session.json").read_bytes() == (
        interrupted_session_bytes
    )
    assert _physical_tree(prepared.run_root) == interrupted_session_tree
    assert _frozen_identity(preserved) == frozen
    assert _file_fingerprint(operator_profile_path()) == profile_before
    assert _physical_tree(prepared.run_root / "inputs") == inputs_before
    assert _file_fingerprint(output_operation_admission_path()) == (
        operation_fingerprint
    )
    assert _file_fingerprint(output_child_claim_path(output_root)) == (
        claim_fingerprint
    )
    assert path_identity(output_root) == replacement_identity
    assert path_identity(held_original) == old_child_identity
    assert _physical_tree(output_root) == replacement_tree
    assert _physical_tree(held_original) == held_tree
    assert _physical_tree(fixture.profile.output_base_root) == output_base_tree
    assert _runtime_payload_tree(fixture.profile.runtime_root) == runtime_before
    assert load_runtime_live_attempt_admission() is None
    assert load_runtime_transaction_journals(fixture.profile.runtime_root) == ()
    assert preserved.publication_binding is None
    assert preserved.apply_invocation_sha256 is None
    assert preserved.runtime_admission_binding is None
    assert preserved.runtime_layout_bootstrap is None
    assert preserved.apply_recovery is None
    assert preserved.result_intent is None
    assert preserved.terminal_status is None
    assert not os.path.lexists(output_root / ".publisher")
    assert not (output_root / "current.json").exists()
    assert not tuple(prepared.run_root.rglob("*apply_invocation*.json"))
    assert not output_operation_admission_staging_path().exists()
    assert not output_operation_admission_reserved_temp_path().exists()
