from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
import multiprocessing
from multiprocessing.connection import Connection
import os
from pathlib import Path
from queue import Empty
import stat
from typing import Any

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import live_start_session as session
from hsconfig import output_publisher as publisher
from hsconfig.atomic_io import LockTimeoutError
from hsconfig.live_start_faults import LiveStartFaultPoint
from hsconfig.operator_profile import derive_deck_output_binding
from hsconfig.output_operation_admission import (
    output_operation_admission_path,
    output_operation_admission_reserved_temp_path,
    output_operation_admission_staging_path,
    output_operation_lock_path,
)
from hsconfig.package_io import path_identity
from hsconfig.runtime_live_admission import (
    load_runtime_live_attempt_admission,
    runtime_live_attempt_admission_path,
)
from hsconfig.runtime_transaction_journal import load_runtime_transaction_journals
from tests.test_codex_first_live_e2e import (
    _local_state,
    _matched_package,
    _prepare_approved,
)
from tests.test_configure_prepublication_apply import _physical_tree
from tests.test_output_publisher import build_rendered_run


_PROCESS_TIMEOUT_SECONDS = 360
_CONTROL_TIMEOUT_SECONDS = 180
_PROBE_RESULT_TIMEOUT_SECONDS = 60
_STABLE_SAMPLES_PER_BARRIER = 2


def _sha256_bytes(raw: bytes) -> str:
    return "sha256:" + sha256(raw).hexdigest()


def _queue_result(queue: Any, *, timeout_seconds: int) -> Any:
    try:
        return queue.get(timeout=timeout_seconds)
    except Empty:
        pytest.fail("spawned process did not report a bounded result")


def _stop_process(process: multiprocessing.Process) -> None:
    if process.pid is None:
        return
    if process.is_alive():
        process.terminate()
        process.join(10)
    if process.is_alive():
        process.kill()
        process.join(10)
    if not process.is_alive():
        process.close()


def _join_process(
    process: multiprocessing.Process,
    *,
    timeout_seconds: int,
) -> None:
    process.join(timeout_seconds)
    if process.is_alive():
        pytest.fail(f"spawned process did not finish within {timeout_seconds}s")
    assert process.exitcode == 0


def _close_queue(queue: Any) -> None:
    queue.close()
    queue.join_thread()


def _read_persisted_session_value(session_root: Path) -> dict[str, Any]:
    value = json.loads((session_root / "session.json").read_bytes())
    if not isinstance(value, dict):
        raise AssertionError("persisted live-start Session is not an object")
    return value


def _continuity_owner_worker(
    session_root_text: str,
    control: Connection,
    unlink_started: Any,
    result_queue: Any,
) -> None:
    session_root = Path(session_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])
    sampling = False
    barrier_index = 0

    def exchange(message: tuple[Any, ...], expected: tuple[Any, ...]) -> None:
        control.send(message)
        if not control.poll(_CONTROL_TIMEOUT_SECONDS):
            raise AssertionError("continuity sampler acknowledgement timeout")
        assert control.recv() == expected

    def observe(point: LiveStartFaultPoint) -> None:
        nonlocal barrier_index, sampling
        if point is LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_PREPARED:
            persisted = _read_persisted_session_value(session_root)
            pending = persisted.get("pending_transition")
            assert isinstance(pending, Mapping)
            external = pending.get("external_file_action")
            assert isinstance(external, Mapping)
            exchange(
                (
                    "prepared",
                    {
                        "run_id": persisted["run_id"],
                        "output_size": external["planned_successor_size"],
                        "output_sha256": external["planned_successor_sha256"],
                    },
                ),
                ("armed",),
            )
            return

        if point is (
            LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS
        ):
            sampling = True
        if not sampling:
            return

        barrier_index += 1
        if point is LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_UNLINK:
            unlink_started.set()
        exchange(
            ("barrier", barrier_index, point.value),
            ("sampled", barrier_index),
        )
        if point is LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_UNLINK:
            sampling = False

    try:
        result = controller._finalize_live_start(
            session_root=session_root,
            resume_intake=True,
            fault_hook=observe,
        )
        result_queue.put(("ok", result.status, str(result.run_root)))
    except BaseException as error:  # pragma: no cover - surfaced in parent
        result_queue.put(("error", type(error).__name__, str(error)))
    finally:
        control.close()


def _authority_presence() -> tuple[bool, bool, bool, bool]:
    return (
        os.path.lexists(output_operation_admission_reserved_temp_path()),
        os.path.lexists(output_operation_admission_staging_path()),
        os.path.lexists(output_operation_admission_path()),
        os.path.lexists(runtime_live_attempt_admission_path()),
    )


def _stable_authority_sample(
    *,
    expected_output_size: int,
    expected_output_sha256: str,
    expected_run_id: str,
) -> tuple[tuple[bool, bool, bool, bool], str | None]:
    output_paths = (
        output_operation_admission_reserved_temp_path(),
        output_operation_admission_staging_path(),
        output_operation_admission_path(),
    )
    output_presence: list[bool] = []
    for path in output_paths:
        present = os.path.lexists(path)
        output_presence.append(present)
        if not present:
            continue
        status = path.lstat()
        assert stat.S_ISREG(status.st_mode)
        assert status.st_nlink in {1, 2}
        raw = path.read_bytes()
        assert len(raw) == expected_output_size
        assert _sha256_bytes(raw) == expected_output_sha256

    runtime_present = os.path.lexists(runtime_live_attempt_admission_path())
    apply_attempt_id = None
    if runtime_present:
        admission = load_runtime_live_attempt_admission()
        assert admission is not None
        assert admission.run_id == expected_run_id
        apply_attempt_id = admission.apply_attempt_id
    return (*output_presence, runtime_present), apply_attempt_id


def _continuity_sampler_worker(
    local_app_data_text: str,
    control: Connection,
    unlink_started: Any,
    result_queue: Any,
) -> None:
    os.environ["LOCALAPPDATA"] = local_app_data_text
    physical_seen = False
    accepted_samples = 0
    discarded_samples = 0
    gap_samples = 0
    barrier_rows: list[dict[str, Any]] = []
    presence_counts: dict[str, int] = {}
    runtime_attempt_ids: set[str] = set()

    def record_presence(presence: tuple[bool, bool, bool, bool]) -> None:
        nonlocal accepted_samples, gap_samples, physical_seen
        if not any(presence) and not physical_seen:
            return
        physical_seen = physical_seen or any(presence)
        accepted_samples += 1
        key = "".join("1" if value else "0" for value in presence)
        presence_counts[key] = presence_counts.get(key, 0) + 1
        if not any(presence):
            gap_samples += 1

    try:
        if not control.poll(_CONTROL_TIMEOUT_SECONDS):
            raise AssertionError("continuity owner did not reach PREPARED")
        prepared_message = control.recv()
        assert prepared_message[0] == "prepared"
        expected = prepared_message[1]
        assert isinstance(expected, Mapping)
        expected_output_size = int(expected["output_size"])
        expected_output_sha256 = str(expected["output_sha256"])
        expected_run_id = str(expected["run_id"])
        control.send(("armed",))

        while True:
            if control.poll(0.01):
                message = control.recv()
                assert message[0] == "barrier"
                _, barrier_index, point_value = message
                stable_rows = []
                for _ in range(_STABLE_SAMPLES_PER_BARRIER):
                    presence, apply_attempt_id = _stable_authority_sample(
                        expected_output_size=expected_output_size,
                        expected_output_sha256=expected_output_sha256,
                        expected_run_id=expected_run_id,
                    )
                    stable_rows.append(presence)
                    record_presence(presence)
                    if apply_attempt_id is not None:
                        runtime_attempt_ids.add(apply_attempt_id)
                assert len(set(stable_rows)) == 1
                barrier_rows.append(
                    {
                        "index": barrier_index,
                        "point": point_value,
                        "presence": list(stable_rows[0]),
                        "sample_count": len(stable_rows),
                    }
                )
                control.send(("sampled", barrier_index))
                if point_value == (
                    LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_UNLINK.value
                ):
                    break
                continue

            stop_before = unlink_started.is_set()
            presence = _authority_presence()
            stop_after = unlink_started.is_set()
            if stop_before != stop_after or stop_before:
                discarded_samples += 1
                continue
            record_presence(presence)

        result_queue.put(
            (
                "ok",
                {
                    "physical_seen": physical_seen,
                    "accepted_samples": accepted_samples,
                    "discarded_samples": discarded_samples,
                    "gap_samples": gap_samples,
                    "barriers": barrier_rows,
                    "presence_counts": presence_counts,
                    "runtime_attempt_ids": sorted(runtime_attempt_ids),
                },
            )
        )
    except BaseException as error:  # pragma: no cover - surfaced in parent
        result_queue.put(("error", type(error).__name__, str(error)))
    finally:
        control.close()


def _publication_projection(output_root: Path) -> dict[str, Any]:
    current_path = output_root / "current.json"
    current = None
    if current_path.is_file():
        current = {
            "identity": list(path_identity(current_path)),
            "raw": current_path.read_bytes().hex(),
        }
    revisions_root = output_root / "revisions"
    revisions: dict[str, dict[str, Any]] = {}
    if revisions_root.is_dir():
        for path in (revisions_root, *sorted(revisions_root.rglob("*"))):
            relative = (
                "."
                if path == revisions_root
                else path.relative_to(revisions_root).as_posix()
            )
            status = path.lstat()
            row: dict[str, Any] = {"identity": list(path_identity(path))}
            if stat.S_ISDIR(status.st_mode):
                row["kind"] = "directory"
            elif stat.S_ISREG(status.st_mode):
                row.update(
                    kind="file",
                    size=status.st_size,
                    sha256=_sha256_bytes(path.read_bytes()),
                )
            else:
                row["kind"] = "unsafe"
            revisions[relative] = row
    return {"current": current, "revisions": revisions}


def _stable_live_start_commit_receipt(
    receipt: publisher._LiveStartCommitReceipt,
) -> dict[str, Any]:
    value = publisher._live_start_commit_receipt_payload(receipt)
    value.pop("owner_journal_identity")
    value.pop("content_sha256")
    return value


def _publication_owner_worker(
    session_root_text: str,
    bootstrap_arrived: Any,
    bootstrap_release: Any,
    publication_arrived: Any,
    publication_release: Any,
    result_queue: Any,
) -> None:
    session_root = Path(session_root_text)
    os.environ["LOCALAPPDATA"] = str(session_root.parents[2])

    def wait_at(arrived: Any, release: Any, name: str) -> None:
        arrived.set()
        if not release.wait(_CONTROL_TIMEOUT_SECONDS):
            raise AssertionError(f"{name} release timeout")

    def pause(point: LiveStartFaultPoint) -> None:
        if point is LiveStartFaultPoint.AFTER_OUTPUT_CHILD_BOOTSTRAP_PREPARED:
            wait_at(bootstrap_arrived, bootstrap_release, "bootstrap")
        elif point is (
            LiveStartFaultPoint.AFTER_PUBLICATION_COMMIT_BEFORE_OUTPUT_CHILD_CLAIM_RETIREMENT
        ):
            wait_at(publication_arrived, publication_release, "publication")

    try:
        result = controller._finalize_live_start(
            session_root=session_root,
            resume_intake=True,
            fault_hook=pause,
        )
        result_queue.put(("ok", result.status, str(result.run_root)))
    except BaseException as error:  # pragma: no cover - surfaced in parent
        result_queue.put(("error", type(error).__name__, str(error)))


def _foreign_publisher_worker(
    source_root_text: str,
    revision: int,
    output_root_text: str,
    local_app_data_text: str,
    ready_queue: Any,
    go: Any,
    attempted: Any,
    result_queue: Any,
) -> None:
    os.environ["LOCALAPPDATA"] = local_app_data_text
    from hsconfig.output_publisher import publish_configure_run

    rendered = build_rendered_run(Path(source_root_text), revision)
    ready_queue.put(rendered.content_root_sha256)
    if not go.wait(_CONTROL_TIMEOUT_SECONDS):
        result_queue.put(("error", "StartTimeout", "publisher start timeout"))
        return
    attempted.set()
    try:
        published = publish_configure_run(rendered, Path(output_root_text))
    except BaseException as error:
        result_queue.put(
            (
                "error",
                rendered.content_root_sha256,
                type(error).__name__,
                str(error),
            )
        )
    else:
        result_queue.put(
            (
                "ok",
                rendered.content_root_sha256,
                published.content_root_sha256,
            )
        )


def _run_foreign_publisher(
    *,
    context: Any,
    source_root: Path,
    output_root: Path,
    local_app_data: Path,
    expected_digest: str,
) -> tuple[Any, ...]:
    ready_queue = context.Queue()
    result_queue = context.Queue()
    go = context.Event()
    attempted = context.Event()
    process = context.Process(
        target=_foreign_publisher_worker,
        args=(
            str(source_root),
            2,
            str(output_root),
            str(local_app_data),
            ready_queue,
            go,
            attempted,
            result_queue,
        ),
    )
    try:
        process.start()
        assert (
            _queue_result(
                ready_queue,
                timeout_seconds=_PROBE_RESULT_TIMEOUT_SECONDS,
            )
            == expected_digest
        )
        go.set()
        assert attempted.wait(10)
        result = _queue_result(
            result_queue,
            timeout_seconds=_PROBE_RESULT_TIMEOUT_SECONDS,
        )
        _join_process(process, timeout_seconds=10)
        return result
    finally:
        go.set()
        _stop_process(process)
        _close_queue(ready_queue)
        _close_queue(result_queue)


def _assert_natural_operation_lock_timeout(
    result: tuple[Any, ...],
    *,
    expected_digest: str,
) -> None:
    assert len(result) == 4
    assert result[:3] == (
        "error",
        expected_digest,
        LockTimeoutError.__name__,
    )
    assert str(output_operation_lock_path()) in result[3]


def test_live_handoff_never_has_both_output_and_runtime_admissions_absent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "pipeline", monkeypatch)
    context = multiprocessing.get_context("spawn")
    owner_control, sampler_control = context.Pipe(duplex=True)
    unlink_started = context.Event()
    owner_results = context.Queue()
    sampler_results = context.Queue()
    owner = context.Process(
        target=_continuity_owner_worker,
        args=(
            str(prepared.run_root),
            owner_control,
            unlink_started,
            owner_results,
        ),
    )
    sampler = context.Process(
        target=_continuity_sampler_worker,
        args=(
            os.environ["LOCALAPPDATA"],
            sampler_control,
            unlink_started,
            sampler_results,
        ),
    )
    try:
        sampler.start()
        owner.start()
        owner_control.close()
        sampler_control.close()
        sampler_result = _queue_result(
            sampler_results,
            timeout_seconds=_PROCESS_TIMEOUT_SECONDS,
        )
        _join_process(sampler, timeout_seconds=10)
        assert sampler_result[0] == "ok", sampler_result
        summary = sampler_result[1]
        assert summary["physical_seen"] is True
        assert summary["gap_samples"] == 0
        assert summary["accepted_samples"] >= 8
        assert len(summary["runtime_attempt_ids"]) == 1
        barriers = summary["barriers"]
        assert barriers
        assert all(
            row["sample_count"] == _STABLE_SAMPLES_PER_BARRIER for row in barriers
        )
        observed = {row["point"]: row["presence"] for row in barriers}
        assert observed[
            LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_STAGING_FLUSH_BEFORE_STAGING_BOUND_CAS.value
        ] == [False, True, False, False]
        assert observed[
            LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_BOUND.value
        ] == [False, False, True, False]
        assert observed[
            LiveStartFaultPoint.AFTER_RUNTIME_ADMISSION_BOUND_COMMIT_BEFORE_CAS.value
        ] == [False, False, True, True]
        assert observed[
            LiveStartFaultPoint.AFTER_OUTPUT_OPERATION_ADMISSION_UNLINK.value
        ] == [False, False, False, True]

        _join_process(owner, timeout_seconds=_PROCESS_TIMEOUT_SECONDS)
        owner_result = _queue_result(owner_results, timeout_seconds=10)
        assert owner_result == (
            "ok",
            "LIVE_AND_MATCHED",
            str(prepared.run_root),
        )
    finally:
        unlink_started.set()
        _stop_process(sampler)
        _stop_process(owner)
        owner_control.close()
        sampler_control.close()
        _close_queue(owner_results)
        _close_queue(sampler_results)

    terminal = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    attempt_id = summary["runtime_attempt_ids"][0]
    assert terminal.terminal_status == "LIVE_AND_MATCHED"
    assert terminal.attempt_acknowledgement["apply_attempt_id"] == attempt_id
    invocation_paths = tuple(prepared.run_root.rglob("*apply_invocation*.json"))
    assert invocation_paths == (
        prepared.run_root / "receipts" / "apply_invocation.json",
    )
    journals = load_runtime_transaction_journals(fixture.profile.runtime_root)
    assert len(journals) == 1
    assert journals[0].transaction_id == attempt_id
    assert not output_operation_admission_reserved_temp_path().exists()
    assert not output_operation_admission_staging_path().exists()
    assert not output_operation_admission_path().exists()
    assert load_runtime_live_attempt_admission() is None
    _matched_package(fixture)


def test_foreign_publisher_cannot_win_during_output_child_bootstrap_or_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "pipeline", monkeypatch)
    output_root = derive_deck_output_binding(
        fixture.profile,
        fixture.deck_name,
    ).output_root
    foreign_source = tmp_path / "foreign-source"
    foreign_source.mkdir()
    foreign_digest = build_rendered_run(foreign_source, 2).content_root_sha256
    context = multiprocessing.get_context("spawn")
    bootstrap_arrived = context.Event()
    bootstrap_release = context.Event()
    publication_arrived = context.Event()
    publication_release = context.Event()
    owner_results = context.Queue()
    owner = context.Process(
        target=_publication_owner_worker,
        args=(
            str(prepared.run_root),
            bootstrap_arrived,
            bootstrap_release,
            publication_arrived,
            publication_release,
            owner_results,
        ),
    )
    publication_at_commit: dict[str, Any] | None = None
    receipt_at_commit = None
    try:
        owner.start()
        assert bootstrap_arrived.wait(_CONTROL_TIMEOUT_SECONDS)
        bootstrap_projection = _publication_projection(output_root)
        assert bootstrap_projection == {"current": None, "revisions": {}}
        bootstrap_probe = _run_foreign_publisher(
            context=context,
            source_root=foreign_source,
            output_root=output_root,
            local_app_data=prepared.run_root.parents[2],
            expected_digest=foreign_digest,
        )
        _assert_natural_operation_lock_timeout(
            bootstrap_probe,
            expected_digest=foreign_digest,
        )
        assert _publication_projection(output_root) == bootstrap_projection

        bootstrap_release.set()
        assert publication_arrived.wait(_CONTROL_TIMEOUT_SECONDS)
        publication_at_commit = _publication_projection(output_root)
        committed_transactions = publisher._load_valid_transactions(output_root)
        assert len(committed_transactions) == 1
        _transaction_path, transaction = committed_transactions[0]
        assert transaction.live_start_commit_receipt is not None
        assert transaction.owns_revision is True
        receipt_at_commit = (
            transaction.transaction_id,
            transaction.revision,
            transaction.owns_revision,
            _stable_live_start_commit_receipt(transaction.live_start_commit_receipt),
        )
        transaction_tree_at_commit = _physical_tree(
            output_root / ".publisher/transactions"
        )
        assert publication_at_commit["current"] is not None
        assert publication_at_commit["revisions"]
        assert all(
            foreign_digest not in relative
            for relative in publication_at_commit["revisions"]
        )
        publication_probe = _run_foreign_publisher(
            context=context,
            source_root=foreign_source,
            output_root=output_root,
            local_app_data=prepared.run_root.parents[2],
            expected_digest=foreign_digest,
        )
        _assert_natural_operation_lock_timeout(
            publication_probe,
            expected_digest=foreign_digest,
        )
        assert _publication_projection(output_root) == publication_at_commit
        assert _physical_tree(output_root / ".publisher/transactions") == (
            transaction_tree_at_commit
        )

        publication_release.set()
        _join_process(owner, timeout_seconds=_PROCESS_TIMEOUT_SECONDS)
        owner_result = _queue_result(owner_results, timeout_seconds=10)
        assert owner_result == (
            "ok",
            "LIVE_AND_MATCHED",
            str(prepared.run_root),
        )
    finally:
        bootstrap_release.set()
        publication_release.set()
        _stop_process(owner)
        _close_queue(owner_results)

    assert publication_at_commit is not None
    assert receipt_at_commit is not None
    assert _publication_projection(output_root) == publication_at_commit
    finalized_transactions = publisher._load_valid_transactions(output_root)
    assert len(finalized_transactions) == 1
    _transaction_path, finalized_transaction = finalized_transactions[0]
    assert finalized_transaction.phase == "finalized"
    finalized_receipt = finalized_transaction.live_start_commit_receipt
    assert finalized_receipt is not None
    assert (
        finalized_transaction.transaction_id,
        finalized_transaction.revision,
        finalized_transaction.owns_revision,
        _stable_live_start_commit_receipt(finalized_receipt),
    ) == receipt_at_commit
    assert finalized_receipt.disposition == "pointer_staged"
    finalized_journal_identity = path_identity(_transaction_path)
    assert finalized_receipt.owner_journal_identity == finalized_journal_identity
    assert (
        publisher._bind_live_start_receipt_owner_journal_identity(
            finalized_receipt,
            finalized_journal_identity,
        )
        == finalized_receipt
    )
    terminal = session.load_live_start_session(
        prepared.run_root,
        local_app_data_root=prepared.run_root.parents[2],
    )
    publication = terminal.publication_binding
    assert isinstance(publication, Mapping)
    owner_current = json.loads(bytes.fromhex(publication_at_commit["current"]["raw"]))
    assert owner_current["content_root_sha256"] == str(
        publication["content_root_sha256"]
    ).removeprefix("sha256:")
    assert owner_current["revision"] == publication["revision"]
    assert owner_current["content_root_sha256"] != foreign_digest
    _matched_package(fixture)

    successful_probe = _run_foreign_publisher(
        context=context,
        source_root=foreign_source,
        output_root=output_root,
        local_app_data=prepared.run_root.parents[2],
        expected_digest=foreign_digest,
    )
    assert successful_probe == ("ok", foreign_digest, foreign_digest)
    foreign_current = json.loads((output_root / "current.json").read_bytes())
    assert foreign_current["content_root_sha256"] == foreign_digest
    assert (output_root / foreign_current["revision"]).is_dir()
