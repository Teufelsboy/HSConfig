from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import json
import multiprocessing
import os
from pathlib import Path
import stat
import sys
from typing import Any

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig import output_publisher as publisher
from hsconfig import published_apply
from hsconfig import runtime_apply
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.operator_profile import derive_deck_output_binding, operator_profile_path
from hsconfig.output_operation_admission import (
    output_operation_admission_path,
    output_operation_admission_reserved_temp_path,
    output_operation_admission_staging_path,
)
from hsconfig.output_publisher import (
    output_child_claim_path,
    output_child_claim_staging_inner_temp_path,
    output_child_claim_staging_path,
)
from hsconfig.package_io import path_identity
from hsconfig.runtime_transaction_journal import load_runtime_transaction_journals
from tests.test_codex_first_live_e2e import (
    _local_state,
    _matched_package,
    _prepare_approved,
)
from tests.test_configure_prepublication_apply import (
    _crash_cursor_projection,
    _file_fingerprint,
    _join_hard_kill_process,
    _persist_worker_oracle,
    _physical_tree,
)


@dataclass(frozen=True, slots=True)
class _InterruptedExpectation:
    phase: str
    pending_operation: str | None
    pending_stage: str | None
    external_action_kind: str | None
    external_action_stage: str | None
    operation_state: str | None
    child_state: str | None
    publication_bound: bool
    apply_invocation_bound: bool
    runtime_admission_bound: bool
    operation_final: bool
    operation_staging: bool
    claim_final: bool
    claim_staging: bool
    output_child_present: bool
    current_present: bool


_PREPUBLICATION = "PREPUBLICATION_CHECK_PASSED"
_PUBLICATION_COMMITTED = "PUBLICATION_COMMITTED"
_APPLY_STARTED = "APPLY_STARTED"
_OPERATION_STAGING = "materialize_output_operation_admission_staging"
_CLAIM_STAGING = "materialize_claim_staging"
_FRESH_APPLY_COUNT = "fresh_apply"
_RECOVERY_APPLY_COUNT = "recovery_apply"
_INSTALL_PREPARE_COUNT = "install_prepare"
_ATTEMPT_PREPARE_COUNT = "attempt_prepare"
_APPLY_COUNT_KEYS = (
    _FRESH_APPLY_COUNT,
    _RECOVERY_APPLY_COUNT,
    _INSTALL_PREPARE_COUNT,
    _ATTEMPT_PREPARE_COUNT,
)


_OUTPUT_OPERATION_CASES = (
    (
        LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_PREPARED,
        _InterruptedExpectation(
            _PREPUBLICATION,
            "install_output_operation_admission",
            "PREPARED",
            _OPERATION_STAGING,
            "PLANNED",
            None,
            None,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
        ),
    ),
    (
        LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS,
        _InterruptedExpectation(
            _PREPUBLICATION,
            "install_output_operation_admission",
            "PREPARED",
            _OPERATION_STAGING,
            "PLANNED",
            None,
            None,
            False,
            False,
            False,
            False,
            True,
            False,
            False,
            False,
            False,
        ),
    ),
    (
        LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_STAGING_BOUND,
        _InterruptedExpectation(
            _PREPUBLICATION,
            "install_output_operation_admission",
            "STAGING_BOUND",
            _OPERATION_STAGING,
            "STAGING_BOUND",
            None,
            None,
            False,
            False,
            False,
            False,
            True,
            False,
            False,
            False,
            False,
        ),
    ),
    (
        LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_BOUND_COMMIT_BEFORE_CAS,
        _InterruptedExpectation(
            _PREPUBLICATION,
            "install_output_operation_admission",
            "STAGING_BOUND",
            _OPERATION_STAGING,
            "STAGING_BOUND",
            None,
            None,
            False,
            False,
            False,
            True,
            False,
            False,
            False,
            False,
            False,
        ),
    ),
    (
        LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_BOUND,
        _InterruptedExpectation(
            _PREPUBLICATION,
            None,
            None,
            None,
            None,
            "ACTIVE",
            None,
            False,
            False,
            False,
            True,
            False,
            False,
            False,
            False,
            False,
        ),
    ),
    (
        LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_RELEASE_AUTHORIZED,
        _InterruptedExpectation(
            _APPLY_STARTED,
            None,
            None,
            None,
            None,
            "RUNTIME_HANDOFF_RELEASE_AUTHORIZED",
            "RETIRED",
            True,
            True,
            True,
            True,
            False,
            False,
            False,
            True,
            True,
        ),
    ),
    (
        LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_UNLINK,
        _InterruptedExpectation(
            _APPLY_STARTED,
            None,
            None,
            None,
            None,
            "RUNTIME_HANDOFF_RELEASE_AUTHORIZED",
            "RETIRED",
            True,
            True,
            True,
            False,
            False,
            False,
            False,
            True,
            True,
        ),
    ),
)


_OUTPUT_CHILD_CASES = (
    (
        LiveStartFaultPoint.AFTER_OUTPUT_CHILD_BOOTSTRAP_PREPARED,
        _InterruptedExpectation(
            _PREPUBLICATION,
            "bootstrap_output_child",
            "PREPARED",
            _CLAIM_STAGING,
            "PLANNED",
            "ACTIVE",
            None,
            False,
            False,
            False,
            True,
            False,
            False,
            False,
            False,
            False,
        ),
    ),
    (
        LiveStartFaultPoint.AFTER_OUTPUT_CHILD_CLAIM_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS,
        _InterruptedExpectation(
            _PREPUBLICATION,
            "bootstrap_output_child",
            "PREPARED",
            _CLAIM_STAGING,
            "PLANNED",
            "ACTIVE",
            None,
            False,
            False,
            False,
            True,
            False,
            False,
            True,
            False,
            False,
        ),
    ),
    (
        LiveStartFaultPoint.AFTER_OUTPUT_CHILD_CLAIM_STAGING_BOUND,
        _InterruptedExpectation(
            _PREPUBLICATION,
            "bootstrap_output_child",
            "STAGING_BOUND",
            _CLAIM_STAGING,
            "STAGING_BOUND",
            "ACTIVE",
            None,
            False,
            False,
            False,
            True,
            False,
            False,
            True,
            False,
            False,
        ),
    ),
    (
        LiveStartFaultPoint.AFTER_OUTPUT_CHILD_CLAIM_BOUND_COMMIT_BEFORE_CAS,
        _InterruptedExpectation(
            _PREPUBLICATION,
            "bootstrap_output_child",
            "STAGING_BOUND",
            _CLAIM_STAGING,
            "STAGING_BOUND",
            "ACTIVE",
            None,
            False,
            False,
            False,
            True,
            False,
            True,
            False,
            False,
            False,
        ),
    ),
    (
        LiveStartFaultPoint.AFTER_OUTPUT_CHILD_CLAIM_BOUND,
        _InterruptedExpectation(
            _PREPUBLICATION,
            "bootstrap_output_child",
            "PRIMARY_APPLIED",
            None,
            None,
            "ACTIVE",
            None,
            False,
            False,
            False,
            True,
            False,
            True,
            False,
            False,
            False,
        ),
    ),
    (
        LiveStartFaultPoint.AFTER_OUTPUT_CHILD_CREATE_BEFORE_CAS,
        _InterruptedExpectation(
            _PREPUBLICATION,
            "bootstrap_output_child",
            "PRIMARY_APPLIED",
            None,
            None,
            "ACTIVE",
            None,
            False,
            False,
            False,
            True,
            False,
            True,
            False,
            True,
            False,
        ),
    ),
    (
        LiveStartFaultPoint.AFTER_OUTPUT_CHILD_BOUND,
        _InterruptedExpectation(
            _PREPUBLICATION,
            None,
            None,
            None,
            None,
            "ACTIVE",
            "ACTIVE",
            False,
            False,
            False,
            True,
            False,
            True,
            False,
            True,
            False,
        ),
    ),
    (
        LiveStartFaultPoint.AFTER_PUBLICATION_COMMIT_BEFORE_OUTPUT_CHILD_CLAIM_RETIREMENT,
        _InterruptedExpectation(
            _PREPUBLICATION,
            None,
            None,
            None,
            None,
            "ACTIVE",
            "ACTIVE",
            False,
            False,
            False,
            True,
            False,
            True,
            False,
            True,
            True,
        ),
    ),
    (
        LiveStartFaultPoint.AFTER_OUTPUT_CHILD_CLAIM_RETIREMENT_PREPARED,
        _InterruptedExpectation(
            _PUBLICATION_COMMITTED,
            "retire_output_child_claim",
            "PREPARED",
            None,
            None,
            "ACTIVE",
            "ACTIVE",
            True,
            False,
            False,
            True,
            False,
            True,
            False,
            True,
            True,
        ),
    ),
    (
        LiveStartFaultPoint.AFTER_OUTPUT_CHILD_CLAIM_UNLINK_BEFORE_CAS,
        _InterruptedExpectation(
            _PUBLICATION_COMMITTED,
            "retire_output_child_claim",
            "PREPARED",
            None,
            None,
            "ACTIVE",
            "ACTIVE",
            True,
            False,
            False,
            True,
            False,
            False,
            False,
            True,
            True,
        ),
    ),
    (
        LiveStartFaultPoint.AFTER_OUTPUT_CHILD_CLAIM_UNLINK_CAS,
        _InterruptedExpectation(
            _PUBLICATION_COMMITTED,
            "retire_output_child_claim",
            "PRIMARY_APPLIED",
            None,
            None,
            "ACTIVE",
            "ACTIVE",
            True,
            False,
            False,
            True,
            False,
            False,
            False,
            True,
            True,
        ),
    ),
    (
        LiveStartFaultPoint.AFTER_OUTPUT_CHILD_CLAIM_CONFIRMATION_BEFORE_RETIRED_CAS,
        _InterruptedExpectation(
            _PUBLICATION_COMMITTED,
            "retire_output_child_claim",
            "PRIMARY_APPLIED",
            None,
            None,
            "ACTIVE",
            "ACTIVE",
            True,
            False,
            False,
            True,
            False,
            False,
            False,
            True,
            True,
        ),
    ),
    (
        LiveStartFaultPoint.AFTER_OUTPUT_CHILD_CLAIM_RETIRED,
        _InterruptedExpectation(
            _PUBLICATION_COMMITTED,
            None,
            None,
            None,
            None,
            "ACTIVE",
            "RETIRED",
            True,
            False,
            False,
            True,
            False,
            False,
            False,
            True,
            True,
        ),
    ),
)


def _sha256_bytes(raw: bytes) -> str:
    return "sha256:" + sha256(raw).hexdigest()


def _session_projection(current: session.LiveStartSession) -> dict[str, object]:
    value = current.to_value()
    return {
        **_crash_cursor_projection(current),
        "run_id": value["run_id"],
        "deck_name": value["deck_name"],
        "deck_code_sha256": value["deck_code_sha256"],
        "preview_requested": value["preview_requested"],
        "candidate_revision": value["candidate_revision"],
        "revisions_used": value["revisions_used"],
        "input_snapshot_manifest_sha256": value["input_snapshot_manifest_sha256"],
        "apply_invocation_sha256": value["apply_invocation_sha256"],
        "runtime_admission_binding": value["runtime_admission_binding"],
        "runtime_layout_bootstrap": value["runtime_layout_bootstrap"],
        "terminal_status": value["terminal_status"],
    }


def _runtime_apply_lock_metadata(
    current: session.LiveStartSession,
) -> tuple[tuple[int, int, int], int] | None:
    layout = current.runtime_layout_bootstrap
    if not isinstance(layout, Mapping):
        return None
    runtime_root = Path(str(layout["runtime_root"]))
    lock_path = runtime_root / ".hsconfig" / "apply.lock"
    lock_status = lock_path.lstat()
    assert stat.S_ISREG(lock_status.st_mode)
    assert lock_status.st_nlink == 1
    return path_identity(lock_path), lock_status.st_size


def _start_apply_entry_observer() -> tuple[dict[str, int], Any]:
    counts = dict.fromkeys(_APPLY_COUNT_KEYS, 0)
    previous = sys.getprofile()
    contextmanager_wrapper_code = published_apply._apply_and_match_published.__code__
    assert (
        published_apply._recover_apply_attempt_under_lock.__code__
        is contextmanager_wrapper_code
    )
    fresh_generator = published_apply._apply_and_match_published.__wrapped__
    recovery_generator = published_apply._recover_apply_attempt_under_lock.__wrapped__
    install_prepare_code = runtime_apply.prepare_package_install_from_lease.__code__
    attempt_prepare_code = session.prepare_apply_attempt_under_lock.__code__

    def observe(frame: Any, event: str, _arg: Any) -> None:
        if event != "call":
            return
        code = frame.f_code
        if code is contextmanager_wrapper_code:
            wrapped = frame.f_locals.get("func")
            if wrapped is fresh_generator:
                counts[_FRESH_APPLY_COUNT] += 1
            elif wrapped is recovery_generator:
                counts[_RECOVERY_APPLY_COUNT] += 1
        elif code is install_prepare_code:
            counts[_INSTALL_PREPARE_COUNT] += 1
        elif code is attempt_prepare_code:
            counts[_ATTEMPT_PREPARE_COUNT] += 1

    sys.setprofile(observe)
    return counts, previous


def _expected_apply_entry_counts(
    *,
    fresh: int = 0,
    recovery: int = 0,
    install_prepare: int = 0,
    attempt_prepare: int = 0,
) -> dict[str, int]:
    return {
        _FRESH_APPLY_COUNT: fresh,
        _RECOVERY_APPLY_COUNT: recovery,
        _INSTALL_PREPARE_COUNT: install_prepare,
        _ATTEMPT_PREPARE_COUNT: attempt_prepare,
    }


def _output_hard_kill_worker(
    session_root_text: str,
    fault_value: str,
    oracle_path_text: str,
) -> None:
    session_root = Path(session_root_text)
    local_app_data = session_root.parents[2]
    os.environ["LOCALAPPDATA"] = str(local_app_data)
    selected = LiveStartFaultPoint(fault_value)
    apply_entry_counts, previous_profile = _start_apply_entry_observer()

    def hard_kill(point: LiveStartFaultPoint) -> None:
        if point is not selected:
            return
        session_path = session_root / "session.json"
        persisted = session._load_session_bytes(
            session_path.read_bytes(),
            session_identity=path_identity(session_path),
        )
        oracle = _session_projection(persisted)
        oracle["fault_value"] = point.value
        oracle["apply_entry_counts"] = apply_entry_counts
        oracle["runtime_apply_lock_metadata"] = _runtime_apply_lock_metadata(persisted)
        _persist_worker_oracle(Path(oracle_path_text), oracle)
        os._exit(93)

    try:
        controller._finalize_live_start(
            session_root=session_root,
            resume_intake=True,
            fault_hook=hard_kill,
        )
    finally:
        sys.setprofile(previous_profile)


def _public_resume_worker(session_root_text: str, oracle_path_text: str) -> None:
    session_root = Path(session_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    apply_entry_counts, previous_profile = _start_apply_entry_observer()
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
            "apply_entry_counts": apply_entry_counts,
        },
    )


def _spawn_and_join(
    *,
    target: Any,
    args: tuple[str, ...],
    expected_exitcode: int,
    timeout_seconds: int = 120,
) -> None:
    process = multiprocessing.get_context("spawn").Process(target=target, args=args)
    process.start()
    _join_hard_kill_process(
        process,
        expected_exitcode=expected_exitcode,
        timeout_seconds=timeout_seconds,
    )


def _frozen_identity(current: session.LiveStartSession) -> dict[str, object]:
    selected_bindings = {
        logical_path: current.artifact_bindings[logical_path]
        for logical_path in (
            "starter/starter_context.json",
            "starter/starter_config_candidate.json",
            "starter/starter_config_review.json",
            "receipts/candidate_validation.json",
            "receipts/review_validation.json",
        )
    }
    return {
        "run_id": current.run_id,
        "deck_name": current.deck_name,
        "deck_code_sha256": current.deck_code_sha256,
        "preview_requested": current.preview_requested,
        "candidate_revision": current.candidate_revision,
        "revisions_used": current.revisions_used,
        "input_snapshot_manifest_sha256": current.input_snapshot_manifest_sha256,
        "artifact_bindings": selected_bindings,
    }


def _runtime_payload_tree(runtime_root: Path) -> dict[str, object]:
    return dict(_physical_tree(runtime_root))


def _assert_runtime_prewrite_tree(
    *,
    interrupted: session.LiveStartSession,
    runtime_root: Path,
    runtime_payload_before: dict[str, object],
    runtime_apply_lock_metadata: object,
) -> None:
    observed = _runtime_payload_tree(runtime_root)
    layout = interrupted.runtime_layout_bootstrap
    if layout is None:
        assert runtime_apply_lock_metadata is None
        assert observed == runtime_payload_before
        return

    assert interrupted.phase.value == _APPLY_STARTED
    assert layout["stage"] == "COMPLETE"
    rows = layout["directories"]
    assert tuple(row["role"] for row in rows) == session.RUNTIME_LAYOUT_DIRECTORY_ROLES

    expected = dict(runtime_payload_before)
    internal_relative = (
        (runtime_root / ".hsconfig").relative_to(runtime_root).as_posix()
    )
    internal_entry = observed.get(internal_relative)
    assert internal_entry is not None
    assert internal_entry[0] == "directory"
    expected[internal_relative] = internal_entry
    assert isinstance(runtime_apply_lock_metadata, list)
    assert len(runtime_apply_lock_metadata) == 2
    lock_identity, lock_size = runtime_apply_lock_metadata
    assert isinstance(lock_identity, list)
    assert len(lock_identity) == 3
    assert lock_size == 0
    lock_relative = ".hsconfig/apply.lock"
    lock_fingerprint = _file_fingerprint(runtime_root / lock_relative)
    assert lock_fingerprint == (tuple(lock_identity), 0, _sha256_bytes(b""))
    expected[lock_relative] = ("file", tuple(lock_identity), b"")
    for row in rows:
        path = Path(str(row["path"]))
        relative = path.relative_to(runtime_root).as_posix()
        assert row["successor_identity"] is not None
        expected[relative] = (
            "directory",
            tuple(row["successor_identity"]),
            None,
        )
    transactions_row = rows[
        session.RUNTIME_LAYOUT_DIRECTORY_ROLES.index("transactions")
    ]
    assert tuple(transactions_row["expected_parent_identity"]) == internal_entry[1]
    assert observed == expected


def _historical_operation_identity(
    current: session.LiveStartSession,
) -> tuple[int, int, int] | None:
    identities: list[tuple[int, int, int]] = []
    binding = current.output_operation_admission_binding
    if isinstance(binding, Mapping):
        identities.append(tuple(binding["admission_identity"]))
    pending = current.pending_transition
    external = (
        pending.get("external_file_action") if isinstance(pending, Mapping) else None
    )
    if (
        isinstance(external, Mapping)
        and external.get("stage") == "STAGING_BOUND"
        and external.get("action_kind") == _OPERATION_STAGING
    ):
        identities.append(tuple(external["staging_identity"]))
    assert len(set(identities)) <= 1
    return identities[0] if identities else None


def _historical_claim_identity(
    current: session.LiveStartSession,
    *,
    output_root: Path,
) -> tuple[int, int, int] | None:
    identities: list[tuple[int, int, int]] = []
    pending = current.pending_transition
    if (
        isinstance(pending, Mapping)
        and pending.get("output_claim_identity") is not None
    ):
        identities.append(tuple(pending["output_claim_identity"]))
    external = (
        pending.get("external_file_action") if isinstance(pending, Mapping) else None
    )
    if (
        isinstance(external, Mapping)
        and external.get("stage") == "STAGING_BOUND"
        and external.get("action_kind") == _CLAIM_STAGING
    ):
        identities.append(tuple(external["staging_identity"]))
    child = current.output_child_binding
    if isinstance(child, Mapping) and child.get("claim_identity") is not None:
        identities.append(tuple(child["claim_identity"]))
    if (output_root / "current.json").is_file():
        for _path, transaction in publisher._load_valid_transactions(output_root):
            receipt = transaction.live_start_commit_receipt
            if receipt is not None:
                identities.append(receipt.claim_identity)
    assert len(set(identities)) <= 1
    return identities[0] if identities else None


def _binding_state(binding: Mapping[str, Any] | None) -> str | None:
    return None if binding is None else str(binding["state"])


def _claim_state(binding: Mapping[str, Any] | None) -> str | None:
    return None if binding is None else str(binding["claim_state"])


def _publication_snapshot(output_root: Path) -> dict[str, object] | None:
    current_path = output_root / "current.json"
    if not current_path.is_file():
        return None
    current_value = json.loads(current_path.read_bytes())
    revision_root = output_root / str(current_value["revision"])
    transactions = publisher._load_valid_transactions(output_root)
    return {
        "output_root_identity": path_identity(output_root),
        "current_fingerprint": _file_fingerprint(current_path),
        "current_value": current_value,
        "revision_tree": _physical_tree(revision_root),
        "transaction_ids": tuple(
            transaction.transaction_id for _path, transaction in transactions
        ),
    }


def _assert_interrupted_state(
    *,
    interrupted: session.LiveStartSession,
    expectation: _InterruptedExpectation,
    output_root: Path,
    runtime_root: Path,
    runtime_payload_before: dict[str, object],
    runtime_apply_lock_metadata: object,
    profile_before: tuple[tuple[int, int, int], int, str],
) -> None:
    pending = interrupted.pending_transition
    external = (
        pending.get("external_file_action") if isinstance(pending, Mapping) else None
    )
    operation = interrupted.output_operation_admission_binding
    child = interrupted.output_child_binding
    operation_path = output_operation_admission_path()
    claim_path = output_child_claim_path(output_root)

    assert interrupted.phase.value == expectation.phase
    assert (pending.get("operation") if isinstance(pending, Mapping) else None) == (
        expectation.pending_operation
    )
    assert (pending.get("stage") if isinstance(pending, Mapping) else None) == (
        expectation.pending_stage
    )
    assert (external.get("action_kind") if isinstance(external, Mapping) else None) == (
        expectation.external_action_kind
    )
    assert (external.get("stage") if isinstance(external, Mapping) else None) == (
        expectation.external_action_stage
    )
    assert _binding_state(operation) == expectation.operation_state
    assert _claim_state(child) == expectation.child_state
    assert (
        interrupted.publication_binding is not None
    ) is expectation.publication_bound
    assert (interrupted.apply_invocation_sha256 is not None) is (
        expectation.apply_invocation_bound
    )
    assert (interrupted.runtime_admission_binding is not None) is (
        expectation.runtime_admission_bound
    )
    assert operation_path.is_file() is expectation.operation_final
    assert output_operation_admission_staging_path().is_file() is (
        expectation.operation_staging
    )
    assert not output_operation_admission_reserved_temp_path().exists()
    assert claim_path.is_file() is expectation.claim_final
    assert output_child_claim_staging_path(output_root).is_file() is (
        expectation.claim_staging
    )
    assert not output_child_claim_staging_inner_temp_path(output_root).exists()
    assert output_root.is_dir() is expectation.output_child_present
    assert (output_root / "current.json").is_file() is expectation.current_present
    revisions = (
        tuple((output_root / "revisions").glob("sha256-*"))
        if (output_root / "revisions").is_dir()
        else ()
    )
    transactions = (
        publisher._load_valid_transactions(output_root)
        if expectation.current_present
        else []
    )
    assert len(revisions) == int(expectation.current_present)
    assert len(transactions) == int(expectation.current_present)
    runtime_admission = interrupted.runtime_admission_binding
    if isinstance(runtime_admission, Mapping):
        assert Path(str(runtime_admission["admission_path"])).is_file()
        assert path_identity(Path(str(runtime_admission["admission_path"]))) == tuple(
            runtime_admission["admission_identity"]
        )
    _assert_runtime_prewrite_tree(
        interrupted=interrupted,
        runtime_root=runtime_root,
        runtime_payload_before=runtime_payload_before,
        runtime_apply_lock_metadata=runtime_apply_lock_metadata,
    )
    assert _file_fingerprint(operator_profile_path()) == profile_before

    if isinstance(operation, Mapping) and expectation.operation_final:
        assert path_identity(operation_path) == tuple(operation["admission_identity"])
    if expectation.claim_final:
        claim_identity = None
        if isinstance(pending, Mapping):
            claim_identity = pending.get("output_claim_identity")
        if claim_identity is None and isinstance(child, Mapping):
            claim_identity = child.get("claim_identity")
        if claim_identity is not None:
            assert path_identity(claim_path) == tuple(claim_identity)
    if isinstance(child, Mapping):
        assert path_identity(output_root) == tuple(child["output_child_identity"])
    if isinstance(interrupted.publication_binding, Mapping):
        publication = interrupted.publication_binding
        assert tuple(publication["output_child_identity"]) == path_identity(output_root)

    physical_work_started = (
        expectation.operation_staging
        or expectation.operation_final
        or expectation.claim_staging
        or expectation.claim_final
        or expectation.output_child_present
        or expectation.current_present
        or expectation.runtime_admission_bound
    )
    if physical_work_started:
        runtime_admission_present = (
            isinstance(runtime_admission, Mapping)
            and Path(str(runtime_admission["admission_path"])).is_file()
        )
        assert (
            operation_path.is_file()
            or output_operation_admission_staging_path().is_file()
            or output_operation_admission_reserved_temp_path().is_file()
            or runtime_admission_present
        )


def _assert_final_live_state(
    *,
    fixture: Any,
    session_root: Path,
    frozen_identity: dict[str, object],
    interrupted: session.LiveStartSession,
    output_root: Path,
    profile_before: tuple[tuple[int, int, int], int, str],
    publication_at_kill: dict[str, object] | None,
    planned_staging_identity: tuple[int, int, int] | None,
    bound_staging_identity: tuple[int, int, int] | None,
    operation_identity_at_kill: tuple[int, int, int] | None,
    claim_identity_at_kill: tuple[int, int, int] | None,
    child_identity_at_kill: tuple[int, int, int] | None,
) -> session.LiveStartSession:
    terminal = session.load_live_start_session(
        session_root,
        local_app_data_root=session_root.parents[2],
    )
    assert terminal.terminal_status == "LIVE_AND_MATCHED"
    assert _frozen_identity(terminal) == frozen_identity
    assert terminal.pending_transition is None
    assert terminal.output_child_binding["claim_state"] == "RETIRED"
    assert terminal.publication_binding is not None
    assert terminal.apply_invocation_sha256 is not None
    assert terminal.runtime_admission_binding is not None
    assert terminal.terminal_retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"

    output, package, runtime_target = _matched_package(fixture)
    assert output == output_root
    assert (
        package == output_root / terminal.publication_binding["revision"] / "04_package"
    )
    assert _file_fingerprint(operator_profile_path()) == profile_before

    current_path = output_root / "current.json"
    current_value = json.loads(current_path.read_bytes())
    assert current_value["revision"] == terminal.publication_binding["revision"]
    assert (
        "sha256:" + current_value["content_root_sha256"]
        == terminal.publication_binding["content_root_sha256"]
    )
    revisions = tuple((output_root / "revisions").glob("sha256-*"))
    output_transactions = publisher._load_valid_transactions(output_root)
    assert len(revisions) == len(output_transactions) == 1
    _output_transaction_path, output_transaction = output_transactions[0]
    assert output_transaction.owns_revision is True
    assert output_transaction.revision == terminal.publication_binding["revision"]
    assert output_transaction.phase == "finalized"
    commit_receipt = output_transaction.live_start_commit_receipt
    assert commit_receipt is not None
    assert commit_receipt.operation_admission_identity == tuple(
        terminal.output_operation_admission_binding["admission_identity"]
    )
    assert commit_receipt.output_child_identity == tuple(
        terminal.output_child_binding["output_child_identity"]
    )
    if operation_identity_at_kill is not None:
        assert (
            tuple(terminal.output_operation_admission_binding["admission_identity"])
            == operation_identity_at_kill
        )
        assert commit_receipt.operation_admission_identity == operation_identity_at_kill

    journals = load_runtime_transaction_journals(fixture.profile.runtime_root)
    owners = [
        journal
        for journal in journals
        if journal.owns_target
        and fixture.profile.runtime_root / journal.target_path == runtime_target
    ]
    assert len(journals) == len(owners) == 1
    assert owners[0].phase.value == "finalized"
    assert path_identity(runtime_target) == tuple(owners[0].target_identity)
    target_directories = tuple(
        path
        for path in (fixture.profile.runtime_root / "CustomConfig").iterdir()
        if path.is_dir()
    )
    assert target_directories == (runtime_target,)

    invocation_paths = tuple(session_root.rglob("apply_invocation.json"))
    assert invocation_paths == (session_root / "receipts/apply_invocation.json",)
    invocation_value = json.loads(invocation_paths[0].read_bytes())
    assert invocation_value["content_sha256"] == terminal.apply_invocation_sha256
    assert terminal.artifact_bindings["receipts/apply_invocation.json"] == (
        _sha256_bytes(invocation_paths[0].read_bytes())
    )

    claim_path = output_child_claim_path(output_root)
    assert not claim_path.exists()
    assert not tuple(fixture.profile.output_base_root.glob("*.claim.json*"))
    assert not output_operation_admission_path().exists()
    assert not output_operation_admission_staging_path().exists()
    assert not output_operation_admission_reserved_temp_path().exists()
    assert not Path(terminal.runtime_admission_binding["admission_path"]).exists()
    assert not tuple(session_root.parents[2].rglob("*.staged"))
    assert not tuple(session_root.parents[2].rglob("*.live-start-atomic.tmp"))

    if publication_at_kill is not None:
        resumed_publication = _publication_snapshot(output_root)
        assert resumed_publication is not None
        assert (
            resumed_publication["output_root_identity"]
            == publication_at_kill["output_root_identity"]
        )
        assert (
            resumed_publication["current_fingerprint"]
            == publication_at_kill["current_fingerprint"]
        )
        assert (
            resumed_publication["current_value"] == publication_at_kill["current_value"]
        )
        assert (
            resumed_publication["revision_tree"] == publication_at_kill["revision_tree"]
        )
        assert (
            resumed_publication["transaction_ids"]
            == publication_at_kill["transaction_ids"]
        )
    if planned_staging_identity is not None:
        external_kind = interrupted.pending_transition["external_file_action"][
            "action_kind"
        ]
        adopted_identity = (
            commit_receipt.operation_admission_identity
            if external_kind == _OPERATION_STAGING
            else commit_receipt.claim_identity
        )
        assert adopted_identity != planned_staging_identity
    if bound_staging_identity is not None:
        external_kind = interrupted.pending_transition["external_file_action"][
            "action_kind"
        ]
        adopted_identity = (
            commit_receipt.operation_admission_identity
            if external_kind == _OPERATION_STAGING
            else commit_receipt.claim_identity
        )
        assert adopted_identity == bound_staging_identity
    if claim_identity_at_kill is not None:
        assert commit_receipt.claim_identity == claim_identity_at_kill
    if child_identity_at_kill is not None:
        assert tuple(terminal.output_child_binding["output_child_identity"]) == (
            child_identity_at_kill
        )
    if interrupted.apply_invocation_sha256 is not None:
        assert terminal.apply_invocation_sha256 == interrupted.apply_invocation_sha256
        assert (
            terminal.runtime_admission_binding == interrupted.runtime_admission_binding
        )
        assert (
            terminal.runtime_layout_bootstrap["apply_attempt_id"]
            == (interrupted.runtime_layout_bootstrap["apply_attempt_id"])
        )
        assert (
            terminal.result_intent["apply_attempt_id"]
            == (interrupted.runtime_layout_bootstrap["apply_attempt_id"])
        )
    return terminal


def _assert_final_failed_preserved_state(
    *,
    fixture: Any,
    session_root: Path,
    frozen_identity: dict[str, object],
    interrupted: session.LiveStartSession,
    output_root: Path,
    profile_before: tuple[tuple[int, int, int], int, str],
    publication_at_kill: dict[str, object],
    publication_tree_at_kill: dict[str, object],
    runtime_at_kill: dict[str, object],
    operation_identity_at_kill: tuple[int, int, int],
    claim_identity_at_kill: tuple[int, int, int],
    child_identity_at_kill: tuple[int, int, int],
) -> session.LiveStartSession:
    terminal = session.load_live_start_session(
        session_root,
        local_app_data_root=session_root.parents[2],
    )
    assert terminal.phase.value == _APPLY_STARTED
    assert terminal.terminal_status == "FAILED_PRESERVED"
    assert _frozen_identity(terminal) == frozen_identity
    assert terminal.pending_transition is None
    assert terminal.apply_recovery is None
    assert terminal.closed_apply_recovery_commitment is None
    assert terminal.attempt_acknowledgement is None
    assert terminal.apply_invocation_sha256 == interrupted.apply_invocation_sha256
    assert terminal.runtime_admission_binding == interrupted.runtime_admission_binding
    assert terminal.runtime_layout_bootstrap == interrupted.runtime_layout_bootstrap
    assert (
        terminal.output_operation_admission_binding
        == interrupted.output_operation_admission_binding
    )
    assert terminal.output_child_binding == interrupted.output_child_binding
    assert terminal.publication_binding == interrupted.publication_binding

    intent = terminal.result_intent
    retirement = terminal.terminal_retirement
    layout = terminal.runtime_layout_bootstrap
    runtime_admission = terminal.runtime_admission_binding
    assert isinstance(intent, Mapping)
    assert isinstance(retirement, Mapping)
    assert isinstance(layout, Mapping)
    assert isinstance(runtime_admission, Mapping)
    attempt_id = str(layout["apply_attempt_id"])
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
    for prefix in (
        "retained_attempt_record",
        "retained_journal",
        "retained_target_owner_journal",
    ):
        assert intent[f"{prefix}_path"] is None
        assert intent[f"{prefix}_identity"] is None
        assert intent[f"{prefix}_sha256"] is None
    assert intent["retained_candidate_identity"] is None
    for intent_key, binding_key in (
        ("runtime_admission_path", "admission_path"),
        ("runtime_admission_parent_identity", "admission_parent_identity"),
        ("runtime_admission_identity", "admission_identity"),
        ("runtime_admission_sha256", "admission_sha256"),
    ):
        assert intent[intent_key] == runtime_admission[binding_key]

    assert retirement["apply_attempt_id"] == attempt_id
    assert retirement["operation"] == "release_not_committed"
    assert retirement["stage"] == "ADMISSION_RELEASE_AUTHORIZED"
    assert retirement["result_intent_sha256"] == intent["content_sha256"]
    assert retirement["terminal_resolution_evidence"] is None
    for prefix in (
        "retained_attempt_record",
        "retained_journal",
        "retained_target_owner_journal",
    ):
        assert retirement[f"{prefix}_path"] is None
        assert retirement[f"{prefix}_identity"] is None
        assert retirement[f"{prefix}_sha256"] is None
    assert retirement["retained_candidate_identity"] is None
    for retirement_key, binding_key in (
        ("runtime_admission_path", "admission_path"),
        ("runtime_admission_parent_identity", "admission_parent_identity"),
        ("runtime_admission_identity", "admission_identity"),
        ("runtime_admission_sha256", "admission_sha256"),
    ):
        assert retirement[retirement_key] == runtime_admission[binding_key]

    invocation_path = session_root / "receipts/apply_invocation.json"
    assert tuple(session_root.rglob("*apply_invocation*.json")) == (invocation_path,)
    invocation_raw = invocation_path.read_bytes()
    invocation = json.loads(invocation_raw)
    assert invocation["apply_attempt_id"] == attempt_id
    assert invocation["content_sha256"] == terminal.apply_invocation_sha256
    assert terminal.artifact_bindings["receipts/apply_invocation.json"] == (
        _sha256_bytes(invocation_raw)
    )

    assert _file_fingerprint(operator_profile_path()) == profile_before
    assert _runtime_payload_tree(fixture.profile.runtime_root) == runtime_at_kill
    resumed_publication = _publication_snapshot(output_root)
    assert resumed_publication == publication_at_kill
    assert _physical_tree(output_root) == publication_tree_at_kill
    output_transactions = publisher._load_valid_transactions(output_root)
    assert len(output_transactions) == 1
    _transaction_path, output_transaction = output_transactions[0]
    assert output_transaction.owns_revision is True
    assert output_transaction.phase == "finalized"
    assert output_transaction.revision == terminal.publication_binding["revision"]
    commit_receipt = output_transaction.live_start_commit_receipt
    assert commit_receipt is not None
    assert commit_receipt.operation_admission_identity == operation_identity_at_kill
    assert (
        commit_receipt.operation_admission_sha256
        == (terminal.output_operation_admission_binding["admission_sha256"])
    )
    assert commit_receipt.claim_identity == claim_identity_at_kill
    assert commit_receipt.output_child_identity == child_identity_at_kill
    assert tuple(terminal.output_operation_admission_binding["admission_identity"]) == (
        operation_identity_at_kill
    )
    assert tuple(terminal.output_child_binding["output_child_identity"]) == (
        child_identity_at_kill
    )

    runtime_root = fixture.profile.runtime_root
    assert load_runtime_transaction_journals(runtime_root) == ()
    assert not tuple((runtime_root / ".hsconfig/transactions").iterdir())
    assert not tuple((runtime_root / ".hsconfig/staging").iterdir())
    layout_rows = layout["directories"]
    state_receipts_row = layout_rows[
        session.RUNTIME_LAYOUT_DIRECTORY_ROLES.index("state_receipts")
    ]
    state_receipts = Path(str(state_receipts_row["path"]))
    receipts_root = runtime_root / ".hsconfig/receipts"
    assert state_receipts.parent == receipts_root
    assert tuple(receipts_root.iterdir()) == (state_receipts,)
    assert path_identity(state_receipts) == tuple(
        state_receipts_row["successor_identity"]
    )
    assert not tuple(state_receipts.iterdir())
    assert not tuple((runtime_root / ".hsconfig/attempt-retention").iterdir())
    assert not tuple((runtime_root / ".hsconfig/owner-retirements").iterdir())
    assert not tuple((runtime_root / "CustomConfig").iterdir())
    assert not (runtime_root / ".hsconfig/state.json").exists()
    assert not Path(str(runtime_admission["admission_path"])).exists()
    assert not output_operation_admission_path().exists()
    assert not output_operation_admission_staging_path().exists()
    assert not output_operation_admission_reserved_temp_path().exists()
    assert not output_child_claim_path(output_root).exists()
    assert not tuple(fixture.profile.output_base_root.glob("*.claim.json*"))
    assert not tuple(session_root.parents[2].rglob("*.staged"))
    assert not tuple(session_root.parents[2].rglob("*.live-start-atomic.tmp"))
    return terminal


def _exercise_output_hard_kill(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    fault: LiveStartFaultPoint,
    expectation: _InterruptedExpectation,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "approved", monkeypatch)
    approved = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    frozen_identity = _frozen_identity(approved)
    profile_before = _file_fingerprint(operator_profile_path())
    assert profile_before is not None
    runtime_payload_before = _runtime_payload_tree(fixture.profile.runtime_root)
    output_root = derive_deck_output_binding(
        fixture.profile,
        fixture.deck_name,
    ).output_root
    oracle_path = tmp_path / "hard-kill-oracle.json"

    _spawn_and_join(
        target=_output_hard_kill_worker,
        args=(str(prepared.run_root), fault.value, str(oracle_path)),
        expected_exitcode=93,
        timeout_seconds=360,
    )
    interrupted = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    oracle = json.loads(oracle_path.read_bytes())
    assert oracle.pop("fault_value") == fault.value
    kill_counts = oracle.pop("apply_entry_counts")
    runtime_apply_lock_metadata = oracle.pop("runtime_apply_lock_metadata")
    handoff_interruption = expectation.phase == _APPLY_STARTED
    assert kill_counts == (
        _expected_apply_entry_counts(
            fresh=1,
            install_prepare=1,
            attempt_prepare=1,
        )
        if handoff_interruption
        else _expected_apply_entry_counts()
    )
    assert oracle == _session_projection(interrupted)
    assert _frozen_identity(interrupted) == frozen_identity
    _assert_interrupted_state(
        interrupted=interrupted,
        expectation=expectation,
        output_root=output_root,
        runtime_root=fixture.profile.runtime_root,
        runtime_payload_before=runtime_payload_before,
        runtime_apply_lock_metadata=runtime_apply_lock_metadata,
        profile_before=profile_before,
    )

    publication_at_kill = _publication_snapshot(output_root)
    publication_tree_at_kill = (
        _physical_tree(output_root) if handoff_interruption else None
    )
    runtime_at_kill = _runtime_payload_tree(fixture.profile.runtime_root)
    child_identity_at_kill = (
        path_identity(output_root) if output_root.is_dir() else None
    )
    claim_path = output_child_claim_path(output_root)
    operation_identity_at_kill = _historical_operation_identity(interrupted)
    claim_identity_at_kill = _historical_claim_identity(
        interrupted,
        output_root=output_root,
    )
    if output_operation_admission_path().is_file():
        assert operation_identity_at_kill is not None
        assert path_identity(output_operation_admission_path()) == (
            operation_identity_at_kill
        )
    if claim_path.is_file():
        assert claim_identity_at_kill is not None
        assert path_identity(claim_path) == claim_identity_at_kill
    pending = interrupted.pending_transition
    external = (
        pending.get("external_file_action") if isinstance(pending, Mapping) else None
    )
    planned_staging_identity = None
    bound_staging_identity = None
    if isinstance(external, Mapping):
        staging_path = Path(str(external["staging_path"]))
        if external["stage"] == "PLANNED" and staging_path.is_file():
            planned_staging_identity = path_identity(staging_path)
        elif external["stage"] == "STAGING_BOUND":
            bound_staging_identity = tuple(external["staging_identity"])
            physical_bound_path = (
                staging_path
                if staging_path.is_file()
                else Path(str(external["final_path"]))
            )
            assert path_identity(physical_bound_path) == bound_staging_identity

    resume_oracle_path = tmp_path / "public-resume-oracle.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(resume_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    resume_oracle = json.loads(resume_oracle_path.read_bytes())
    resume_counts = resume_oracle.pop("apply_entry_counts")
    assert resume_counts == (
        _expected_apply_entry_counts(recovery=1)
        if handoff_interruption
        else _expected_apply_entry_counts(
            fresh=1,
            install_prepare=1,
            attempt_prepare=1,
        )
    )
    assert kill_counts[_FRESH_APPLY_COUNT] + resume_counts[_FRESH_APPLY_COUNT] == 1
    assert (
        kill_counts[_INSTALL_PREPARE_COUNT] + resume_counts[_INSTALL_PREPARE_COUNT] == 1
    )
    assert (
        kill_counts[_ATTEMPT_PREPARE_COUNT] + resume_counts[_ATTEMPT_PREPARE_COUNT] == 1
    )
    assert resume_oracle["status"] == (
        "FAILED_PRESERVED" if handoff_interruption else "LIVE_AND_MATCHED"
    )
    assert resume_oracle["run_root"] == str(prepared.run_root)
    if handoff_interruption:
        assert publication_at_kill is not None
        assert publication_tree_at_kill is not None
        assert operation_identity_at_kill is not None
        assert claim_identity_at_kill is not None
        assert child_identity_at_kill is not None
        terminal = _assert_final_failed_preserved_state(
            fixture=fixture,
            session_root=prepared.run_root,
            frozen_identity=frozen_identity,
            interrupted=interrupted,
            output_root=output_root,
            profile_before=profile_before,
            publication_at_kill=publication_at_kill,
            publication_tree_at_kill=publication_tree_at_kill,
            runtime_at_kill=runtime_at_kill,
            operation_identity_at_kill=operation_identity_at_kill,
            claim_identity_at_kill=claim_identity_at_kill,
            child_identity_at_kill=child_identity_at_kill,
        )
    else:
        terminal = _assert_final_live_state(
            fixture=fixture,
            session_root=prepared.run_root,
            frozen_identity=frozen_identity,
            interrupted=interrupted,
            output_root=output_root,
            profile_before=profile_before,
            publication_at_kill=publication_at_kill,
            planned_staging_identity=planned_staging_identity,
            bound_staging_identity=bound_staging_identity,
            operation_identity_at_kill=operation_identity_at_kill,
            claim_identity_at_kill=claim_identity_at_kill,
            child_identity_at_kill=child_identity_at_kill,
        )
    summary_json = (prepared.run_root / "result/summary.json").read_bytes()
    assert resume_oracle["summary_sha256"] == _sha256_bytes(summary_json)
    assert resume_oracle["session_sha256"] == terminal.content_sha256

    terminal_bytes = {
        "session": (prepared.run_root / "session.json").read_bytes(),
        "summary_json": summary_json,
        "summary_markdown": (prepared.run_root / "result/summary.md").read_bytes(),
        "runtime": _physical_tree(fixture.profile.runtime_root),
        "publication": _physical_tree(output_root),
    }
    terminal_journals = tuple(
        journal.transaction_id
        for journal in load_runtime_transaction_journals(fixture.profile.runtime_root)
    )
    terminal_invocations = tuple(
        path.name
        for path in (prepared.run_root / "receipts").glob("*apply_invocation*.json")
    )

    replay_oracle_path = tmp_path / "public-replay-oracle.json"
    _spawn_and_join(
        target=_public_resume_worker,
        args=(str(prepared.run_root), str(replay_oracle_path)),
        expected_exitcode=0,
        timeout_seconds=360,
    )
    replay_oracle = json.loads(replay_oracle_path.read_bytes())
    replay_counts = replay_oracle.pop("apply_entry_counts")
    assert replay_counts == _expected_apply_entry_counts()
    assert replay_oracle == resume_oracle
    assert (prepared.run_root / "session.json").read_bytes() == terminal_bytes[
        "session"
    ]
    assert (prepared.run_root / "result/summary.json").read_bytes() == terminal_bytes[
        "summary_json"
    ]
    assert (prepared.run_root / "result/summary.md").read_bytes() == terminal_bytes[
        "summary_markdown"
    ]
    assert _physical_tree(fixture.profile.runtime_root) == terminal_bytes["runtime"]
    assert _physical_tree(output_root) == terminal_bytes["publication"]
    assert (
        tuple(
            journal.transaction_id
            for journal in load_runtime_transaction_journals(
                fixture.profile.runtime_root
            )
        )
        == terminal_journals
    )
    assert (
        tuple(
            path.name
            for path in (prepared.run_root / "receipts").glob("*apply_invocation*.json")
        )
        == terminal_invocations
    )


@pytest.mark.parametrize(
    ("fault", "expectation"),
    _OUTPUT_OPERATION_CASES,
    ids=[fault.name.lower() for fault, _expectation in _OUTPUT_OPERATION_CASES],
)
def test_output_operation_admission_hard_kills_resume_every_create_bind_and_release_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: LiveStartFaultPoint,
    expectation: _InterruptedExpectation,
) -> None:
    _exercise_output_hard_kill(
        tmp_path,
        monkeypatch,
        fault=fault,
        expectation=expectation,
    )


@pytest.mark.parametrize(
    ("fault", "expectation"),
    _OUTPUT_CHILD_CASES,
    ids=[fault.name.lower() for fault, _expectation in _OUTPUT_CHILD_CASES],
)
def test_output_child_bootstrap_hard_kills_resume_every_claim_and_child_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: LiveStartFaultPoint,
    expectation: _InterruptedExpectation,
) -> None:
    _exercise_output_hard_kill(
        tmp_path,
        monkeypatch,
        fault=fault,
        expectation=expectation,
    )
