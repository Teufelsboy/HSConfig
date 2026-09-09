from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import sys
from typing import Any

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig import published_apply
from hsconfig import runtime_apply
from hsconfig.apply_invocation import load_apply_invocation
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.operator_profile import derive_deck_output_binding, operator_profile_path
from hsconfig.output_operation_admission import (
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
from tests.test_controller_candidate_parity_hard_kills import (
    _publication_tree_with_held_lock,
)
from tests.test_controller_output_hard_kills import (
    _expected_apply_entry_counts,
    _frozen_identity,
    _public_resume_worker,
    _spawn_and_join,
    _start_apply_entry_observer,
)
from tests.test_controller_prior_owner_action_chain import _result_pair
from tests.test_controller_runtime_admission_staging_hard_kills import (
    _assert_held_tree_after_exit,
    _json_fingerprint,
    _json_identity,
    _raw_held_session,
    _tree_with_unreadable_files,
)
from tests.test_controller_runtime_action_chain import _runtime_tree
from tests.test_controller_runtime_hard_kills import (
    _assert_complete_layout,
    _assert_final_state,
    _publication_transaction_snapshot,
)


_HARD_EXIT = 93


@dataclass(frozen=True, slots=True)
class _InvocationCase:
    name: str
    fault: LiveStartFaultPoint
    external_stage: str
    physical_surface: str
    terminal_status: str


_CASES = (
    _InvocationCase(
        name="staging-flushed-planned",
        fault=(
            LiveStartFaultPoint.AFTER_INVOCATION_RECEIPT_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS
        ),
        external_stage="PLANNED",
        physical_surface="staging",
        terminal_status="LIVE_AND_MATCHED",
    ),
    _InvocationCase(
        name="bound-final-before-cas",
        fault=LiveStartFaultPoint.AFTER_INVOCATION_RECEIPT_BOUND_COMMIT_BEFORE_CAS,
        external_stage="STAGING_BOUND",
        physical_surface="final",
        terminal_status="FAILED_PRESERVED",
    ),
)


def _receipt_surfaces(
    *,
    final_path: Path,
    staging_path: Path,
    inner_path: Path,
) -> dict[str, object]:
    result: dict[str, object] = {}
    for name, path in (
        ("final", final_path),
        ("staging", staging_path),
        ("inner", inner_path),
    ):
        if not os.path.lexists(path):
            result[name] = None
            continue
        status = path.lstat()
        assert stat.S_ISREG(status.st_mode)
        result[name] = {
            "identity": list(path_identity(path)),
            "size": status.st_size,
            "nlink": status.st_nlink,
            "sha256": "sha256:" + sha256(path.read_bytes()).hexdigest(),
        }
    return result


def _invocation_receipt_hard_kill_worker(
    session_root_text: str,
    output_root_text: str,
    runtime_root_text: str,
    fault_value: str,
    oracle_path_text: str,
) -> None:
    session_root = Path(session_root_text)
    output_root = Path(output_root_text)
    runtime_root = Path(runtime_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    selected = LiveStartFaultPoint(fault_value)
    counts, previous_profile = _start_apply_entry_observer()

    def hard_kill(point: LiveStartFaultPoint) -> None:
        if point is not selected:
            return
        current = _raw_held_session(session_root)
        pending = current.pending_transition
        assert isinstance(pending, Mapping)
        external = pending["external_file_action"]
        assert isinstance(external, Mapping)
        final_path = Path(str(external["final_path"]))
        staging_path = Path(str(external["staging_path"]))
        inner_path = Path(str(external["inner_temp_path"]))
        operation = current.output_operation_admission_binding
        assert isinstance(operation, Mapping)
        operation_path = Path(str(operation["admission_path"]))
        _persist_worker_oracle(
            Path(oracle_path_text),
            {
                "fault_value": point.value,
                "session": current.to_value(),
                "session_fingerprint": _file_fingerprint(session_root / "session.json"),
                "apply_entry_counts": counts,
                "runtime_tree": _tree_with_unreadable_files(
                    runtime_root,
                    unreadable=frozenset({runtime_root / ".hsconfig" / "apply.lock"}),
                ),
                "output_tree": _publication_tree_with_held_lock(output_root),
                "profile_fingerprint": _file_fingerprint(operator_profile_path()),
                "operation_fingerprint": _file_fingerprint(operation_path),
                "receipt_surfaces": _receipt_surfaces(
                    final_path=final_path,
                    staging_path=staging_path,
                    inner_path=inner_path,
                ),
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


def _public_resume_observing_receipt_retirement_worker(
    session_root_text: str,
    output_root_text: str,
    runtime_root_text: str,
    old_action_index_text: str,
    final_path_text: str,
    staging_path_text: str,
    inner_path_text: str,
    oracle_path_text: str,
) -> None:
    session_root = Path(session_root_text)
    output_root = Path(output_root_text)
    runtime_root = Path(runtime_root_text)
    final_path = Path(final_path_text)
    staging_path = Path(staging_path_text)
    inner_path = Path(inner_path_text)
    old_action_index = int(old_action_index_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    counts = _expected_apply_entry_counts()
    retire_rows: list[dict[str, object]] = []
    previous_profile = sys.getprofile()
    contextmanager_wrapper_code = published_apply._apply_and_match_published.__code__
    assert (
        published_apply._recover_apply_attempt_under_lock.__code__
        is contextmanager_wrapper_code
    )
    fresh_generator = published_apply._apply_and_match_published.__wrapped__
    recovery_generator = published_apply._recover_apply_attempt_under_lock.__wrapped__
    install_prepare_code = runtime_apply.prepare_package_install_from_lease.__code__
    attempt_prepare_code = session.prepare_apply_attempt_under_lock.__code__
    advance_code = session.advance_runtime_admission_under_lock.__code__

    def observe(frame: Any, event: str, arg: Any) -> None:
        code = frame.f_code
        if event == "call":
            if code is contextmanager_wrapper_code:
                wrapped = frame.f_locals.get("func")
                if wrapped is fresh_generator:
                    counts["fresh_apply"] += 1
                elif wrapped is recovery_generator:
                    counts["recovery_apply"] += 1
            elif code is install_prepare_code:
                counts["install_prepare"] += 1
            elif code is attempt_prepare_code:
                counts["attempt_prepare"] += 1
            return
        if (
            event != "return"
            or code is not advance_code
            or frame.f_locals.get("transition")
            != "invocation_receipt_unbound_staging_retired"
        ):
            return
        assert isinstance(arg, session.LiveStartSession)
        current = _raw_held_session(session_root)
        assert current.to_value() == arg.to_value()
        pending = current.pending_transition
        assert isinstance(pending, Mapping)
        external = pending["external_file_action"]
        assert isinstance(external, Mapping)
        assert current.phase is session.LiveStartPhase.PUBLICATION_COMMITTED
        assert pending["operation"] == "install_apply_invocation"
        assert pending["stage"] == "PRIMARY_APPLIED"
        assert pending["next_action_index"] == 0
        assert external["stage"] == "PLANNED"
        assert external["action_kind"] == "materialize_invocation_receipt_staging"
        assert external["action_index"] == old_action_index + 1
        assert Path(str(external["final_path"])) == final_path
        assert Path(str(external["staging_path"])) == staging_path
        assert Path(str(external["inner_temp_path"])) == inner_path
        assert not any(
            os.path.lexists(path) for path in (final_path, staging_path, inner_path)
        )
        current_value = current.to_value()
        retire_rows.append(
            {
                "session": current_value,
                "frozen_identity": _frozen_identity(current),
                "operation": current_value["output_operation_admission_binding"],
                "child": current_value["output_child_binding"],
                "publication": current_value["publication_binding"],
                "profile_fingerprint": _file_fingerprint(operator_profile_path()),
                "output_tree": _publication_tree_with_held_lock(output_root),
                "runtime_tree": _tree_with_unreadable_files(
                    runtime_root,
                    unreadable=frozenset({runtime_root / ".hsconfig" / "apply.lock"}),
                ),
                "receipt_surfaces": _receipt_surfaces(
                    final_path=final_path,
                    staging_path=staging_path,
                    inner_path=inner_path,
                ),
            }
        )

    sys.setprofile(observe)
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
    assert len(retire_rows) == 1
    _persist_worker_oracle(
        Path(oracle_path_text),
        {
            "status": result.status,
            "run_root": str(result.run_root),
            "summary_sha256": (
                "sha256:" + sha256(result.summary.canonical_json).hexdigest()
            ),
            "session_sha256": terminal.content_sha256,
            "apply_entry_counts": counts,
            "retired_unbound_receipt": retire_rows[0],
        },
    )


def _assert_interrupted_receipt(
    *,
    case: _InvocationCase,
    current: session.LiveStartSession,
    oracle: Mapping[str, Any],
    runtime_root: Path,
) -> tuple[str, Path, Path, Path, Mapping[str, Any]]:
    assert oracle["fault_value"] == case.fault.value
    assert oracle["apply_entry_counts"] == _expected_apply_entry_counts(
        fresh=1,
        install_prepare=1,
        attempt_prepare=1,
    )
    assert current.to_value() == oracle["session"]
    assert current.phase is session.LiveStartPhase.PUBLICATION_COMMITTED
    assert current.apply_invocation_sha256 is None
    assert current.runtime_admission_binding is None
    assert current.apply_recovery is None
    assert current.result_intent is None
    assert current.terminal_status is None
    pending = current.pending_transition
    assert isinstance(pending, Mapping)
    assert pending["operation"] == "install_apply_invocation"
    assert pending["stage"] == "PRIMARY_APPLIED"
    assert pending["next_action_index"] == 0
    attempt_id = str(pending["apply_attempt_id"])
    assert len(attempt_id) == 32
    external = pending["external_file_action"]
    assert isinstance(external, Mapping)
    assert external["stage"] == case.external_stage
    assert external["action_kind"] == (
        "materialize_invocation_receipt_staging"
        if case.external_stage == "PLANNED"
        else "commit_bound_invocation_receipt"
    )
    final_path = Path(str(external["final_path"]))
    staging_path = Path(str(external["staging_path"]))
    inner_path = Path(str(external["inner_temp_path"]))
    operation = current.output_operation_admission_binding
    assert isinstance(operation, Mapping)
    assert final_path == (
        Path(str(operation["session_root"])) / "receipts/apply_invocation.json"
    )
    assert final_path.parent == staging_path.parent == inner_path.parent
    assert path_identity(final_path.parent) == tuple(external["parent_identity"])
    assert (
        external["planned_successor_size"] == pending["apply_invocation_document_size"]
    )
    assert (
        external["planned_successor_sha256"]
        == pending["successor_artifact_bindings"]["receipts/apply_invocation.json"]
    )
    surfaces = oracle["receipt_surfaces"]
    assert isinstance(surfaces, Mapping)
    assert surfaces["inner"] is None
    physical = surfaces[case.physical_surface]
    assert isinstance(physical, Mapping)
    assert physical["size"] == external["planned_successor_size"]
    assert physical["sha256"] == external["planned_successor_sha256"]
    assert physical["nlink"] == 1
    if case.external_stage == "PLANNED":
        assert surfaces["final"] is None
        assert external["staging_identity"] is None
    else:
        assert surfaces["staging"] is None
        assert _json_identity(physical["identity"]) == tuple(
            external["staging_identity"]
        )
    admission = load_runtime_live_attempt_admission()
    assert admission is not None
    assert admission.apply_attempt_id == attempt_id
    assert admission.admission_path == Path(str(pending["runtime_admission_path"]))
    assert admission.admission_identity == tuple(pending["runtime_admission_identity"])
    assert admission.admission_sha256 == pending["runtime_admission_sha256"]
    _assert_complete_layout(current)
    layout = current.runtime_layout_bootstrap
    assert isinstance(layout, Mapping)
    assert layout["apply_attempt_id"] == attempt_id
    expected_runtime_paths = {".", ".hsconfig", ".hsconfig/apply.lock"}
    expected_runtime_paths.update(
        Path(str(row["path"])).relative_to(runtime_root).as_posix()
        for row in layout["directories"]
    )
    runtime_tree = oracle["runtime_tree"]
    assert isinstance(runtime_tree, Mapping)
    assert set(runtime_tree) == expected_runtime_paths
    assert runtime_tree[".hsconfig/apply.lock"]["size"] == 0
    assert runtime_tree[".hsconfig/apply.lock"]["sha256"] is None
    assert operation["state"] == "ACTIVE"
    assert isinstance(current.output_child_binding, Mapping)
    assert current.output_child_binding["claim_state"] == "RETIRED"
    assert isinstance(current.publication_binding, Mapping)
    assert "receipts/apply_invocation.json" not in current.artifact_bindings
    assert load_runtime_transaction_journals(runtime_root) == ()
    return attempt_id, final_path, staging_path, inner_path, external


def _assert_failed_no_commit_terminal(
    *,
    fixture: Any,
    session_root: Path,
    frozen_identity: dict[str, object],
    interrupted: session.LiveStartSession,
    output_root: Path,
    profile_before: tuple[tuple[int, int, int], int, str],
    runtime_at_kill: dict[str, object],
    publication_at_kill: dict[str, object],
    publication_transactions_at_kill: dict[str, dict[str, object]],
    attempt_id: str,
    bound_receipt_identity: tuple[int, int, int],
) -> session.LiveStartSession:
    terminal = session.load_live_start_session(
        session_root,
        local_app_data_root=session_root.parents[2],
    )
    assert terminal.phase is session.LiveStartPhase.APPLY_STARTED
    assert terminal.terminal_status == "FAILED_PRESERVED"
    assert _frozen_identity(terminal) == frozen_identity
    assert terminal.pending_transition is None
    assert terminal.apply_recovery is None
    assert terminal.closed_apply_recovery_commitment is None
    assert terminal.attempt_acknowledgement is None
    assert terminal.runtime_layout_bootstrap == interrupted.runtime_layout_bootstrap
    assert terminal.output_child_binding == interrupted.output_child_binding
    assert terminal.publication_binding == interrupted.publication_binding
    assert terminal.runtime_layout_bootstrap["apply_attempt_id"] == attempt_id
    operation = terminal.output_operation_admission_binding
    interrupted_operation = interrupted.output_operation_admission_binding
    assert isinstance(operation, Mapping)
    assert isinstance(interrupted_operation, Mapping)
    assert operation["state"] == "RUNTIME_HANDOFF_RELEASE_AUTHORIZED"
    assert operation["release_handoff_kind"] == "runtime_admission"
    for key in (
        "admission_path",
        "admission_parent_identity",
        "admission_identity",
        "admission_size",
        "admission_sha256",
        "session_root",
        "session_root_identity",
        "operator_profile_sha256",
        "state_root_identity",
        "output_base_root",
        "output_base_root_identity",
    ):
        assert operation[key] == interrupted_operation[key]
    runtime_admission = terminal.runtime_admission_binding
    intent = terminal.result_intent
    retirement = terminal.terminal_retirement
    assert isinstance(runtime_admission, Mapping)
    assert isinstance(intent, Mapping)
    assert isinstance(retirement, Mapping)
    assert (
        runtime_admission["admission_identity"]
        == interrupted.pending_transition["runtime_admission_identity"]
    )
    assert (
        runtime_admission["admission_sha256"]
        == interrupted.pending_transition["runtime_admission_sha256"]
    )
    assert intent["apply_attempt_id"] == attempt_id
    assert intent["physical_disposition"] == "NOT_COMMITTED"
    assert intent["raw_apply_status"] is None
    assert intent["runtime_match_status"] == "not_run"
    assert intent["runtime_match_sha256"] is None
    assert intent["last_apply_receipt_sha256"] is None
    assert intent["runtime_state_sha256"] is None
    assert intent["deck_config_ini_sha256"] is None
    assert intent["error_code"] == "apply_not_committed"
    assert intent["retained_safe_state"] == "PREVIOUS_RUNTIME_UNCHANGED"
    assert retirement["apply_attempt_id"] == attempt_id
    assert retirement["operation"] == "release_not_committed"
    assert retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"
    assert retirement["result_intent_sha256"] == intent["content_sha256"]
    invocation_path = session_root / "receipts/apply_invocation.json"
    invocation = load_apply_invocation(invocation_path)
    assert invocation.apply_attempt_id == attempt_id
    assert invocation.content_sha256 == terminal.apply_invocation_sha256
    assert path_identity(invocation_path) == bound_receipt_identity
    assert terminal.artifact_bindings["receipts/apply_invocation.json"] == (
        "sha256:" + sha256(invocation_path.read_bytes()).hexdigest()
    )
    assert _physical_tree(fixture.profile.runtime_root) == runtime_at_kill
    assert _physical_tree(output_root) == publication_at_kill
    assert (
        _publication_transaction_snapshot(output_root)
        == publication_transactions_at_kill
    )
    assert _file_fingerprint(operator_profile_path()) == profile_before
    assert load_runtime_transaction_journals(fixture.profile.runtime_root) == ()
    assert not tuple((fixture.profile.runtime_root / "CustomConfig").iterdir())
    assert not tuple(
        (fixture.profile.runtime_root / ".hsconfig/transactions").iterdir()
    )
    assert not tuple((fixture.profile.runtime_root / ".hsconfig/staging").iterdir())
    assert not tuple(
        (fixture.profile.runtime_root / ".hsconfig/attempt-retention").iterdir()
    )
    assert not tuple(
        (fixture.profile.runtime_root / ".hsconfig/owner-retirements").iterdir()
    )
    assert not (fixture.profile.runtime_root / ".hsconfig/state.json").exists()
    assert not Path(str(runtime_admission["admission_path"])).exists()
    assert not output_operation_admission_path().exists()
    assert not output_operation_admission_staging_path().exists()
    assert not output_operation_admission_reserved_temp_path().exists()
    assert not output_child_claim_path(output_root).exists()
    assert not tuple(fixture.profile.output_base_root.glob("*.claim.json*"))
    assert not tuple(session_root.parents[2].rglob("*.staged"))
    assert not tuple(session_root.parents[2].rglob("*.live-start-atomic.tmp"))
    return terminal


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.name)
def test_invocation_receipt_staging_hard_kills_use_only_bound_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: _InvocationCase,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "pipeline", monkeypatch)
    approved = session.load_live_start_session(prepared.run_root)
    frozen = _frozen_identity(approved)
    runtime_root = fixture.profile.runtime_root
    output_root = derive_deck_output_binding(
        fixture.profile,
        fixture.deck_name,
    ).output_root
    oracle_path = tmp_path / "invocation-hard-kill.json"

    _spawn_and_join(
        target=_invocation_receipt_hard_kill_worker,
        args=(
            str(prepared.run_root),
            str(output_root),
            str(runtime_root),
            case.fault.value,
            str(oracle_path),
        ),
        expected_exitcode=_HARD_EXIT,
        timeout_seconds=360,
    )
    oracle = json.loads(oracle_path.read_bytes())
    interrupted = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    attempt_id, final_path, staging_path, inner_path, external = (
        _assert_interrupted_receipt(
            case=case,
            current=interrupted,
            oracle=oracle,
            runtime_root=runtime_root,
        )
    )
    assert _frozen_identity(interrupted) == frozen
    apply_lock = runtime_root / ".hsconfig/apply.lock"
    _assert_held_tree_after_exit(
        root=runtime_root,
        recorded=oracle["runtime_tree"],
        unreadable_at_kill=frozenset({apply_lock}),
    )
    assert (
        _receipt_surfaces(
            final_path=final_path,
            staging_path=staging_path,
            inner_path=inner_path,
        )
        == oracle["receipt_surfaces"]
    )
    assert _runtime_tree(output_root, held_lock_path=None) == oracle["output_tree"]
    assert _file_fingerprint(operator_profile_path()) == _json_fingerprint(
        oracle["profile_fingerprint"]
    )
    operation = interrupted.output_operation_admission_binding
    assert isinstance(operation, Mapping)
    operation_path = Path(str(operation["admission_path"]))
    assert _file_fingerprint(operation_path) == _json_fingerprint(
        oracle["operation_fingerprint"]
    )
    runtime_at_kill = _physical_tree(runtime_root)
    publication_at_kill = _physical_tree(output_root)
    publication_transactions_at_kill = _publication_transaction_snapshot(output_root)
    profile_before = _file_fingerprint(operator_profile_path())
    assert profile_before is not None

    resume_path = tmp_path / "public-resume.json"
    if case.external_stage == "PLANNED":
        resume_target = _public_resume_observing_receipt_retirement_worker
        resume_args = (
            str(prepared.run_root),
            str(output_root),
            str(runtime_root),
            str(external["action_index"]),
            str(final_path),
            str(staging_path),
            str(inner_path),
            str(resume_path),
        )
    else:
        resume_target = _public_resume_worker
        resume_args = (str(prepared.run_root), str(resume_path))
    _spawn_and_join(
        target=resume_target,
        args=resume_args,
        expected_exitcode=0,
        timeout_seconds=360,
    )
    resumed = json.loads(resume_path.read_bytes())
    if case.external_stage == "PLANNED":
        retired = resumed.pop("retired_unbound_receipt")
        interrupted_value = interrupted.to_value()
        assert retired["frozen_identity"] == frozen
        assert (
            retired["operation"]
            == interrupted_value["output_operation_admission_binding"]
        )
        assert retired["child"] == interrupted_value["output_child_binding"]
        assert retired["publication"] == interrupted_value["publication_binding"]
        assert retired["profile_fingerprint"] == oracle["profile_fingerprint"]
        assert retired["output_tree"] == oracle["output_tree"]
        assert retired["runtime_tree"] == oracle["runtime_tree"]
        assert retired["receipt_surfaces"] == {
            "final": None,
            "staging": None,
            "inner": None,
        }
        retired_session = retired["session"]
        assert retired_session["phase"] == "PUBLICATION_COMMITTED"
        assert retired_session["pending_transition"]["stage"] == "PRIMARY_APPLIED"
        assert (
            retired_session["pending_transition"]["external_file_action"][
                "action_index"
            ]
            == external["action_index"] + 1
        )
        assert retired_session["apply_invocation_sha256"] is None
        assert retired_session["runtime_admission_binding"] is None
        assert (
            retired_session["runtime_layout_bootstrap"]
            == interrupted_value["runtime_layout_bootstrap"]
        )
        retired_runtime = retired["runtime_tree"]
        assert retired_runtime[".hsconfig/apply.lock"]["size"] == 0
        assert retired_runtime[".hsconfig/apply.lock"]["sha256"] is None
    assert resumed["status"] == case.terminal_status
    assert resumed["run_root"] == str(prepared.run_root)
    assert resumed["apply_entry_counts"] == _expected_apply_entry_counts(
        recovery=1,
        install_prepare=1,
    )

    bound_at_kill = oracle["receipt_surfaces"][case.physical_surface]
    assert isinstance(bound_at_kill, Mapping)
    if case.terminal_status == "LIVE_AND_MATCHED":
        terminal = _assert_final_state(
            fixture=fixture,
            session_root=prepared.run_root,
            frozen_identity=frozen,
            output_root=output_root,
            publication_at_kill=publication_at_kill,
            publication_transactions_at_kill=publication_transactions_at_kill,
            profile_before=profile_before,
            expected_attempt_id=attempt_id,
            expected_owner_id=None,
            prior_owner_state=None,
        )
    else:
        terminal = _assert_failed_no_commit_terminal(
            fixture=fixture,
            session_root=prepared.run_root,
            frozen_identity=frozen,
            interrupted=interrupted,
            output_root=output_root,
            profile_before=profile_before,
            runtime_at_kill=runtime_at_kill,
            publication_at_kill=publication_at_kill,
            publication_transactions_at_kill=publication_transactions_at_kill,
            attempt_id=attempt_id,
            bound_receipt_identity=_json_identity(bound_at_kill["identity"]),
        )
    assert resumed["session_sha256"] == terminal.content_sha256
    assert terminal.runtime_layout_bootstrap["apply_attempt_id"] == attempt_id
    assert terminal.result_intent["apply_attempt_id"] == attempt_id
    assert terminal.terminal_retirement["apply_attempt_id"] == attempt_id
    invocation_path = prepared.run_root / "receipts/apply_invocation.json"
    assert tuple(prepared.run_root.rglob("*apply_invocation*.json")) == (
        invocation_path,
    )
    invocation = load_apply_invocation(invocation_path)
    assert invocation.apply_attempt_id == attempt_id
    assert invocation.content_sha256 == terminal.apply_invocation_sha256
    assert terminal.artifact_bindings["receipts/apply_invocation.json"] == (
        "sha256:" + sha256(invocation_path.read_bytes()).hexdigest()
    )
    terminal_admission = terminal.runtime_admission_binding
    assert isinstance(terminal_admission, Mapping)
    assert (
        terminal_admission["admission_identity"]
        == interrupted.pending_transition["runtime_admission_identity"]
    )
    assert (
        terminal_admission["admission_sha256"]
        == interrupted.pending_transition["runtime_admission_sha256"]
    )
    terminal_operation = terminal.output_operation_admission_binding
    assert isinstance(terminal_operation, Mapping)
    assert invocation.output_operation_admission_path == Path(
        str(terminal_operation["admission_path"])
    )
    assert invocation.output_operation_admission_identity == tuple(
        terminal_operation["admission_identity"]
    )
    assert (
        invocation.output_operation_admission_sha256
        == terminal_operation["admission_sha256"]
    )
    assert (
        invocation.output_child_binding_sha256
        == terminal.output_child_binding["content_sha256"]
    )
    assert invocation.publication_revision == terminal.publication_binding["revision"]
    assert (
        invocation.publication_content_root_sha256
        == terminal.publication_binding["content_root_sha256"]
    )
    assert (
        invocation.operator_profile_sha256
        == terminal_operation["operator_profile_sha256"]
    )
    if case.external_stage == "STAGING_BOUND":
        assert path_identity(invocation_path) == _json_identity(
            bound_at_kill["identity"]
        )
    assert not any(os.path.lexists(path) for path in (staging_path, inner_path))

    terminal_snapshot = {
        "session": _file_fingerprint(prepared.run_root / "session.json"),
        "run": _physical_tree(prepared.run_root),
        "result": _result_pair(prepared.run_root),
        "runtime": _physical_tree(runtime_root),
        "output": _physical_tree(fixture.profile.output_base_root),
        "profile": _file_fingerprint(operator_profile_path()),
        "invocation": _file_fingerprint(invocation_path),
    }
    replay_path = tmp_path / "public-replay.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(replay_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    replayed = json.loads(replay_path.read_bytes())
    assert replayed.pop("apply_entry_counts") == _expected_apply_entry_counts()
    resumed_without_counts = dict(resumed)
    resumed_without_counts.pop("apply_entry_counts")
    assert replayed == resumed_without_counts
    assert terminal_snapshot == {
        "session": _file_fingerprint(prepared.run_root / "session.json"),
        "run": _physical_tree(prepared.run_root),
        "result": _result_pair(prepared.run_root),
        "runtime": _physical_tree(runtime_root),
        "output": _physical_tree(fixture.profile.output_base_root),
        "profile": _file_fingerprint(operator_profile_path()),
        "invocation": _file_fingerprint(invocation_path),
    }
