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
from hsconfig import runtime_installer
from hsconfig.apply_invocation import load_apply_invocation
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.operator_profile import derive_deck_output_binding, operator_profile_path
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
from tests.test_controller_runtime_action_chain import _runtime_tree
from tests.test_controller_runtime_hard_kills import (
    _assert_final_state,
    _publication_transaction_snapshot,
)
from tests.test_controller_terminal_writer_fencing import (
    _published_output_from_owner,
    _runtime_mutation_entry_codes,
)


_HARD_EXIT = 93


@dataclass(frozen=True, slots=True)
class _AdmissionCase:
    name: str
    fault: LiveStartFaultPoint
    pending_stage: str
    physical_state: str
    preserves_attempt: bool


_CASES = (
    _AdmissionCase(
        name="inner-created-planned",
        fault=LiveStartFaultPoint.AFTER_GENERIC_FILE_INNER_TEMP_CREATED,
        pending_stage="PREPARED",
        physical_state="inner",
        preserves_attempt=False,
    ),
    _AdmissionCase(
        name="staging-flushed-planned",
        fault=(
            LiveStartFaultPoint.AFTER_RUNTIME_ADMISSION_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS
        ),
        pending_stage="PREPARED",
        physical_state="staging_unbound",
        preserves_attempt=False,
    ),
    _AdmissionCase(
        name="staging-bound",
        fault=LiveStartFaultPoint.AFTER_RUNTIME_ADMISSION_STAGING_BOUND,
        pending_stage="STAGING_BOUND",
        physical_state="staging_bound",
        preserves_attempt=True,
    ),
    _AdmissionCase(
        name="bound-final-before-cas",
        fault=LiveStartFaultPoint.AFTER_RUNTIME_ADMISSION_BOUND_COMMIT_BEFORE_CAS,
        pending_stage="STAGING_BOUND",
        physical_state="final_before_cas",
        preserves_attempt=True,
    ),
    _AdmissionCase(
        name="final-admission-cas",
        fault=LiveStartFaultPoint.AFTER_ADMISSION_BOUND_BEFORE_INVOCATION_WRITE,
        pending_stage="PRIMARY_APPLIED",
        physical_state="final_bound",
        preserves_attempt=True,
    ),
)


def _raw_held_session(session_root: Path) -> session.LiveStartSession:
    path = session_root / "session.json"
    return session._load_session_bytes(
        path.read_bytes(),
        session_identity=path_identity(path),
    )


def _tree_with_unreadable_files(
    root: Path,
    *,
    unreadable: frozenset[Path],
) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for path in (root, *sorted(root.rglob("*"))):
        relative = "." if path == root else path.relative_to(root).as_posix()
        status = path.lstat()
        identity = list(path_identity(path))
        if stat.S_ISDIR(status.st_mode):
            result[relative] = {"kind": "directory", "identity": identity}
        elif stat.S_ISREG(status.st_mode):
            row: dict[str, object] = {
                "kind": "file",
                "identity": identity,
                "size": status.st_size,
                "nlink": status.st_nlink,
            }
            row["sha256"] = (
                None
                if path in unreadable
                else "sha256:" + sha256(path.read_bytes()).hexdigest()
            )
            result[relative] = row
        else:
            result[relative] = {"kind": "unsafe", "identity": identity}
    return result


def _admission_surface_snapshot(
    *,
    final_path: Path,
    staging_path: Path,
    inner_path: Path,
    held_inner: bool,
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
            "sha256": (
                None
                if held_inner and path == inner_path
                else "sha256:" + sha256(path.read_bytes()).hexdigest()
            ),
        }
    return result


def _runtime_admission_hard_kill_worker(
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
        if point is LiveStartFaultPoint.AFTER_GENERIC_FILE_INNER_TEMP_CREATED and (
            not isinstance(pending, Mapping)
            or pending.get("operation") != "install_apply_invocation"
            or pending.get("stage") != "PREPARED"
        ):
            return
        assert isinstance(pending, Mapping)
        final_path = Path(str(pending["runtime_admission_path"]))
        staging_path = Path(str(pending["runtime_admission_staging_path"]))
        inner_path = Path(str(pending["runtime_admission_staging_inner_temp_path"]))
        operation = current.output_operation_admission_binding
        assert isinstance(operation, Mapping)
        operation_path = Path(str(operation["admission_path"]))
        held_inner = point is LiveStartFaultPoint.AFTER_GENERIC_FILE_INNER_TEMP_CREATED
        _persist_worker_oracle(
            Path(oracle_path_text),
            {
                "fault_value": point.value,
                "session": current.to_value(),
                "session_fingerprint": _file_fingerprint(session_root / "session.json"),
                "apply_entry_counts": counts,
                "runtime_tree": _tree_with_unreadable_files(
                    runtime_root,
                    unreadable=frozenset(
                        {
                            runtime_root / ".hsconfig" / "apply.lock",
                        }
                    ),
                ),
                "output_tree": _publication_tree_with_held_lock(output_root),
                "profile_fingerprint": _file_fingerprint(operator_profile_path()),
                "operation_fingerprint": _file_fingerprint(operation_path),
                "admission_surfaces": _admission_surface_snapshot(
                    final_path=final_path,
                    staging_path=staging_path,
                    inner_path=inner_path,
                    held_inner=held_inner,
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


def _blocked_runtime_writers_worker(
    session_root_text: str,
    runtime_root_text: str,
    oracle_path_text: str,
) -> None:
    session_root = Path(session_root_text)
    runtime_root = Path(runtime_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    owner = session.load_live_start_session(
        session_root,
        local_app_data_root=session_root.parents[2],
    )
    published = _published_output_from_owner(owner=owner)
    plan = runtime_installer.plan_runtime_install(
        published_output=published,
        runtime_root=runtime_root,
    )
    mutation_codes = _runtime_mutation_entry_codes()
    mutation_counts = dict.fromkeys(mutation_codes.values(), 0)
    previous_profile = sys.getprofile()

    def observe(frame: Any, event: str, _arg: Any) -> None:
        if event == "call" and frame.f_code in mutation_codes:
            mutation_counts[mutation_codes[frame.f_code]] += 1

    errors: dict[str, list[str]] = {}
    sys.setprofile(observe)
    try:
        for action in ("legacy_install", "broad_recovery"):
            try:
                if action == "legacy_install":
                    runtime_installer.install_runtime_package(plan)
                else:
                    runtime_installer.recover_runtime_state(runtime_root)
            except Exception as error:
                errors[action] = [type(error).__name__, str(error)]
            else:
                errors[action] = ["", ""]
    finally:
        sys.setprofile(previous_profile)
    _persist_worker_oracle(
        Path(oracle_path_text),
        {
            "errors": errors,
            "runtime_mutation_counts": mutation_counts,
        },
    )


def _public_resume_observing_prepared_rollback_worker(
    session_root_text: str,
    output_root_text: str,
    runtime_root_text: str,
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
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    counts = _expected_apply_entry_counts()
    rollback_rows: list[dict[str, object]] = []
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
    rollback_code = session.resume_pending_apply_invocation_under_lock.__code__

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
            or code is not rollback_code
            or frame.f_locals.get("transition") != "rollback_prepared"
        ):
            return
        assert isinstance(arg, session.LiveStartSession)
        current = _raw_held_session(session_root)
        assert current.to_value() == arg.to_value()
        assert current.phase is session.LiveStartPhase.PUBLICATION_COMMITTED
        assert current.pending_transition is None
        assert current.apply_invocation_sha256 is None
        assert current.runtime_admission_binding is None
        assert current.runtime_layout_bootstrap is None
        assert current.apply_recovery is None
        assert current.result_intent is None
        assert current.terminal_status is None
        assert not any(
            os.path.lexists(path) for path in (final_path, staging_path, inner_path)
        )
        current_value = current.to_value()
        rollback_rows.append(
            {
                "session": current_value,
                "frozen_identity": _frozen_identity(current),
                "operation": current_value["output_operation_admission_binding"],
                "child": current_value["output_child_binding"],
                "publication": current_value["publication_binding"],
                "session_fingerprint": _file_fingerprint(session_root / "session.json"),
                "profile_fingerprint": _file_fingerprint(operator_profile_path()),
                "output_tree": _publication_tree_with_held_lock(output_root),
                "runtime_tree": _tree_with_unreadable_files(
                    runtime_root,
                    unreadable=frozenset({runtime_root / ".hsconfig" / "apply.lock"}),
                ),
                "admission_surfaces": _admission_surface_snapshot(
                    final_path=final_path,
                    staging_path=staging_path,
                    inner_path=inner_path,
                    held_inner=False,
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
    assert len(rollback_rows) == 1
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
            "rollback": rollback_rows[0],
        },
    )


def _json_identity(value: object) -> tuple[int, int, int]:
    assert isinstance(value, list)
    assert len(value) == 3
    return tuple(value)


def _json_fingerprint(value: object) -> tuple[tuple[int, int, int], int, str]:
    assert isinstance(value, list)
    assert len(value) == 3
    identity, size, digest = value
    assert type(size) is int
    assert isinstance(digest, str)
    return _json_identity(identity), size, digest


def _assert_interrupted_case(
    *,
    case: _AdmissionCase,
    current: session.LiveStartSession,
    oracle: Mapping[str, Any],
    runtime_root: Path,
) -> tuple[str, Path, Path, Path]:
    assert oracle["fault_value"] == case.fault.value
    assert oracle["apply_entry_counts"] == _expected_apply_entry_counts(
        fresh=1,
        attempt_prepare=1,
    )
    assert current.to_value() == oracle["session"]
    assert current.phase is session.LiveStartPhase.PUBLICATION_COMMITTED
    pending = current.pending_transition
    assert isinstance(pending, Mapping)
    assert pending["operation"] == "install_apply_invocation"
    assert pending["stage"] == case.pending_stage
    attempt_id = str(pending["apply_attempt_id"])
    assert len(attempt_id) == 32
    assert current.apply_invocation_sha256 is None
    assert current.runtime_admission_binding is None
    assert current.runtime_layout_bootstrap is None
    assert current.apply_recovery is None
    assert current.result_intent is None
    assert current.terminal_status is None
    runtime_tree = oracle["runtime_tree"]
    assert isinstance(runtime_tree, Mapping)
    assert set(runtime_tree) == {".", ".hsconfig", ".hsconfig/apply.lock"}
    assert (
        runtime_tree["."]["kind"] == runtime_tree[".hsconfig"]["kind"] == ("directory")
    )
    assert runtime_tree[".hsconfig/apply.lock"]["kind"] == "file"
    assert runtime_tree[".hsconfig/apply.lock"]["size"] == 0
    assert runtime_tree[".hsconfig/apply.lock"]["sha256"] is None
    operation = current.output_operation_admission_binding
    assert isinstance(operation, Mapping)
    assert operation["state"] == "ACTIVE"
    child = current.output_child_binding
    assert isinstance(child, Mapping)
    assert child["claim_state"] == "RETIRED"
    assert isinstance(current.publication_binding, Mapping)
    invocation_path = current.output_operation_admission_binding["session_root"]
    assert not (Path(str(invocation_path)) / "receipts/apply_invocation.json").exists()
    assert load_runtime_transaction_journals(runtime_root) == ()
    surfaces = oracle["admission_surfaces"]
    assert isinstance(surfaces, Mapping)
    final_path = Path(str(pending["runtime_admission_path"]))
    staging_path = Path(str(pending["runtime_admission_staging_path"]))
    inner_path = Path(str(pending["runtime_admission_staging_inner_temp_path"]))
    final = surfaces["final"]
    staging = surfaces["staging"]
    inner = surfaces["inner"]
    for path, observed in (
        (final_path, final),
        (staging_path, staging),
        (inner_path, inner),
    ):
        if observed is not None:
            assert path_identity(path.parent) == tuple(
                pending["runtime_admission_parent_identity"]
            )
            assert observed["nlink"] == 1
    if case.physical_state == "inner":
        assert final is staging is None
        assert isinstance(inner, Mapping)
        assert inner["sha256"] is None
    elif case.physical_state == "staging_unbound":
        assert final is inner is None
        assert isinstance(staging, Mapping)
        assert staging["size"] == pending["runtime_admission_document_size"]
        assert staging["sha256"] == pending["runtime_admission_document_sha256"]
        assert pending["runtime_admission_staging_identity"] is None
    elif case.physical_state == "staging_bound":
        assert final is inner is None
        assert isinstance(staging, Mapping)
        assert _json_identity(staging["identity"]) == tuple(
            pending["runtime_admission_staging_identity"]
        )
        assert staging["size"] == pending["runtime_admission_staging_size"]
        assert staging["sha256"] == pending["runtime_admission_staging_sha256"]
    elif case.physical_state == "final_before_cas":
        assert staging is inner is None
        assert isinstance(final, Mapping)
        assert _json_identity(final["identity"]) == tuple(
            pending["runtime_admission_staging_identity"]
        )
        assert pending["runtime_admission_identity"] is None
        admission = load_runtime_live_attempt_admission()
        assert admission is not None
        assert admission.apply_attempt_id == attempt_id
    else:
        assert case.physical_state == "final_bound"
        assert staging is inner is None
        assert isinstance(final, Mapping)
        assert _json_identity(final["identity"]) == tuple(
            pending["runtime_admission_identity"]
        )
        admission = load_runtime_live_attempt_admission()
        assert admission is not None
        assert admission.apply_attempt_id == attempt_id
    if case.physical_state not in {"final_before_cas", "final_bound"}:
        assert load_runtime_live_attempt_admission() is None
    return attempt_id, final_path, staging_path, inner_path


def _assert_held_tree_after_exit(
    *,
    root: Path,
    recorded: Mapping[str, Any],
    unreadable_at_kill: frozenset[Path],
) -> None:
    observed = _tree_with_unreadable_files(root, unreadable=frozenset())
    for path in unreadable_at_kill:
        relative = path.relative_to(root).as_posix()
        assert observed[relative]["identity"] == recorded[relative]["identity"]
        assert observed[relative]["size"] == recorded[relative]["size"]
        assert observed[relative]["nlink"] == recorded[relative]["nlink"] == 1
        observed[relative]["sha256"] = None
    assert observed == recorded


@pytest.mark.parametrize("case", _CASES, ids=lambda case: case.name)
def test_runtime_admission_staging_hard_kills_preserve_or_rollback_exact_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: _AdmissionCase,
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
    oracle_path = tmp_path / "admission-hard-kill.json"

    _spawn_and_join(
        target=_runtime_admission_hard_kill_worker,
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
    old_attempt_id, final_path, staging_path, inner_path = _assert_interrupted_case(
        case=case,
        current=interrupted,
        oracle=oracle,
        runtime_root=runtime_root,
    )
    assert _frozen_identity(interrupted) == frozen
    apply_lock = runtime_root / ".hsconfig" / "apply.lock"
    _assert_held_tree_after_exit(
        root=runtime_root,
        recorded=oracle["runtime_tree"],
        unreadable_at_kill=frozenset({apply_lock}),
    )
    surfaces_after_exit = _admission_surface_snapshot(
        final_path=final_path,
        staging_path=staging_path,
        inner_path=inner_path,
        held_inner=False,
    )
    expected_surfaces = dict(oracle["admission_surfaces"])
    if case.physical_state == "inner":
        inner = dict(expected_surfaces["inner"])
        assert inner["size"] == 0
        inner["sha256"] = "sha256:" + sha256(b"").hexdigest()
        expected_surfaces["inner"] = inner
    assert surfaces_after_exit == expected_surfaces
    assert _runtime_tree(output_root, held_lock_path=None) == oracle["output_tree"]
    assert _file_fingerprint(operator_profile_path()) == _json_fingerprint(
        oracle["profile_fingerprint"]
    )
    operation = interrupted.output_operation_admission_binding
    assert isinstance(operation, Mapping)
    operation_path = Path(str(operation["admission_path"]))
    operation_fingerprint = _file_fingerprint(operation_path)
    assert operation_fingerprint is not None
    assert operation_fingerprint == _json_fingerprint(oracle["operation_fingerprint"])
    fenced = {
        "session": _file_fingerprint(prepared.run_root / "session.json"),
        "run": _physical_tree(prepared.run_root),
        "runtime": _physical_tree(runtime_root),
        "output": _physical_tree(fixture.profile.output_base_root),
        "profile": _file_fingerprint(operator_profile_path()),
        "operation": operation_fingerprint,
        "admission_surfaces": _admission_surface_snapshot(
            final_path=final_path,
            staging_path=staging_path,
            inner_path=inner_path,
            held_inner=False,
        ),
    }

    writer_oracle_path = tmp_path / "blocked-runtime-writers.json"
    _spawn_and_join(
        target=_blocked_runtime_writers_worker,
        args=(str(prepared.run_root), str(runtime_root), str(writer_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    writer_oracle = json.loads(writer_oracle_path.read_bytes())
    assert writer_oracle["errors"] == {
        "legacy_install": [
            "ValueError",
            "output_operation_admission_blocks_runtime_mutation",
        ],
        "broad_recovery": [
            "ValueError",
            "output_operation_admission_blocks_runtime_mutation",
        ],
    }
    assert writer_oracle["runtime_mutation_counts"] == dict.fromkeys(
        _runtime_mutation_entry_codes().values(),
        0,
    )
    assert fenced == {
        "session": _file_fingerprint(prepared.run_root / "session.json"),
        "run": _physical_tree(prepared.run_root),
        "runtime": _physical_tree(runtime_root),
        "output": _physical_tree(fixture.profile.output_base_root),
        "profile": _file_fingerprint(operator_profile_path()),
        "operation": _file_fingerprint(operation_path),
        "admission_surfaces": _admission_surface_snapshot(
            final_path=final_path,
            staging_path=staging_path,
            inner_path=inner_path,
            held_inner=False,
        ),
    }

    publication_at_kill = _physical_tree(output_root)
    publication_transactions_at_kill = _publication_transaction_snapshot(output_root)
    profile_before = _file_fingerprint(operator_profile_path())
    assert profile_before is not None
    resume_path = tmp_path / "public-resume.json"
    resume_target = (
        _public_resume_worker
        if case.preserves_attempt
        else _public_resume_observing_prepared_rollback_worker
    )
    resume_args = (
        (str(prepared.run_root), str(resume_path))
        if case.preserves_attempt
        else (
            str(prepared.run_root),
            str(output_root),
            str(runtime_root),
            str(final_path),
            str(staging_path),
            str(inner_path),
            str(resume_path),
        )
    )
    _spawn_and_join(
        target=resume_target,
        args=resume_args,
        expected_exitcode=0,
        timeout_seconds=360,
    )
    resumed = json.loads(resume_path.read_bytes())
    if not case.preserves_attempt:
        rollback = resumed.pop("rollback")
        interrupted_value = interrupted.to_value()
        assert rollback["frozen_identity"] == frozen
        assert (
            rollback["operation"]
            == interrupted_value["output_operation_admission_binding"]
        )
        assert rollback["child"] == interrupted_value["output_child_binding"]
        assert rollback["publication"] == interrupted_value["publication_binding"]
        rollback_session = rollback["session"]
        assert rollback_session["phase"] == "PUBLICATION_COMMITTED"
        assert rollback_session["pending_transition"] is None
        assert rollback_session["runtime_admission_binding"] is None
        assert rollback_session["runtime_layout_bootstrap"] is None
        assert rollback_session["apply_invocation_sha256"] is None
        assert rollback["profile_fingerprint"] == oracle["profile_fingerprint"]
        assert rollback["output_tree"] == oracle["output_tree"]
        assert rollback["admission_surfaces"] == {
            "final": None,
            "staging": None,
            "inner": None,
        }
        rollback_runtime_tree = rollback["runtime_tree"]
        assert rollback_runtime_tree == oracle["runtime_tree"]
        assert set(rollback_runtime_tree) == {
            ".",
            ".hsconfig",
            ".hsconfig/apply.lock",
        }
        assert rollback_runtime_tree[".hsconfig/apply.lock"]["size"] == 0
        assert rollback_runtime_tree[".hsconfig/apply.lock"]["sha256"] is None
    assert resumed["status"] == "LIVE_AND_MATCHED"
    assert resumed["apply_entry_counts"] == _expected_apply_entry_counts(
        **(
            {"recovery": 1, "install_prepare": 1}
            if case.preserves_attempt
            else {"fresh": 1, "install_prepare": 1, "attempt_prepare": 1}
        )
    )
    terminal = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    invocation = load_apply_invocation(
        prepared.run_root / "receipts" / "apply_invocation.json"
    )
    terminal_attempt_id = invocation.apply_attempt_id
    if case.preserves_attempt:
        assert terminal_attempt_id == old_attempt_id
    else:
        assert terminal_attempt_id != old_attempt_id
        assert old_attempt_id not in (prepared.run_root / "session.json").read_text(
            encoding="utf-8"
        )
        assert not (
            runtime_root / ".hsconfig/transactions" / f"{old_attempt_id}.json"
        ).exists()
        assert not (
            runtime_root / ".hsconfig/attempt-retention" / f"{old_attempt_id}.json"
        ).exists()
    asserted_terminal = _assert_final_state(
        fixture=fixture,
        session_root=prepared.run_root,
        frozen_identity=frozen,
        output_root=output_root,
        publication_at_kill=publication_at_kill,
        publication_transactions_at_kill=publication_transactions_at_kill,
        profile_before=profile_before,
        expected_attempt_id=terminal_attempt_id,
        expected_owner_id=None,
        prior_owner_state=None,
    )
    assert asserted_terminal.content_sha256 == terminal.content_sha256
    assert resumed["session_sha256"] == terminal.content_sha256
    terminal_operation = terminal.output_operation_admission_binding
    assert isinstance(terminal_operation, Mapping)
    for field in (
        "admission_path",
        "admission_parent_identity",
        "admission_identity",
        "admission_sha256",
        "session_root",
        "session_root_identity",
        "operator_profile_sha256",
        "state_root_identity",
        "output_base_root",
        "output_base_root_identity",
    ):
        assert terminal_operation[field] == operation[field]
    assert terminal.output_child_binding == interrupted.output_child_binding
    assert terminal.publication_binding == interrupted.publication_binding
    if case.preserves_attempt:
        terminal_admission = terminal.runtime_admission_binding
        assert isinstance(terminal_admission, Mapping)
        surface_name = "staging" if case.physical_state == "staging_bound" else "final"
        physical = oracle["admission_surfaces"][surface_name]
        assert isinstance(physical, Mapping)
        assert tuple(terminal_admission["admission_identity"]) == _json_identity(
            physical["identity"]
        )
        assert (
            physical["size"]
            == interrupted.pending_transition["runtime_admission_document_size"]
        )
        assert terminal_admission["admission_sha256"] == physical["sha256"]
    assert not any(
        os.path.lexists(path) for path in (final_path, staging_path, inner_path)
    )

    terminal_snapshot = {
        "session": _file_fingerprint(prepared.run_root / "session.json"),
        "run": _physical_tree(prepared.run_root),
        "result": _result_pair(prepared.run_root),
        "runtime": _physical_tree(runtime_root),
        "output": _physical_tree(fixture.profile.output_base_root),
        "profile": _file_fingerprint(operator_profile_path()),
        "invocation": _file_fingerprint(
            prepared.run_root / "receipts/apply_invocation.json"
        ),
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
        "invocation": _file_fingerprint(
            prepared.run_root / "receipts/apply_invocation.json"
        ),
    }
