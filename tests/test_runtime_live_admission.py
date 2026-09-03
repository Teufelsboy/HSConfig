from __future__ import annotations

import ast
from dataclasses import replace
from hashlib import sha256
import json
import multiprocessing
import os
from pathlib import Path
from typing import Any

import pytest

import hsconfig.atomic_io as atomic_io
import hsconfig.runtime_live_admission as runtime_live_admission
from hsconfig.package_io import path_identity
from hsconfig.runtime_live_admission import (
    RUNTIME_LIVE_ATTEMPT_ADMISSION_FIELDS,
    RUNTIME_LIVE_ATTEMPT_ADMISSION_KIND,
    RUNTIME_LIVE_ATTEMPT_ADMISSION_MAX_BYTES,
    RUNTIME_LIVE_ATTEMPT_ADMISSION_SCHEMA_VERSION,
    RuntimeLiveAttemptAdmissionEvidence,
    build_runtime_live_attempt_admission_bytes,
    load_runtime_live_attempt_admission,
    release_runtime_live_attempt_exact,
    require_live_admission_allows_legacy_root_bootstrap,
    require_live_admission_allows_publication,
    runtime_live_attempt_admission_path,
)


def _digest(character: str) -> str:
    return "sha256:" + character * 64


def _runtime_admission_claim_contender(
    *,
    parent_text: str,
    final_text: str,
    staging_text: str,
    payload: bytes,
    ready: Any,
    start: Any,
    outcomes: Any,
) -> None:
    parent = Path(parent_text)
    final = Path(final_text)
    staging = Path(staging_text)
    parent_identity = path_identity(parent)
    try:
        materialized = atomic_io.atomic_materialize_staging_bytes(
            staging_path=staging,
            inner_temp_path=staging.with_name(
                f".{staging.name}.live-start-atomic.tmp"
            ),
            payload=payload,
            expected_parent_identity=parent_identity,
            maximum_size=RUNTIME_LIVE_ATTEMPT_ADMISSION_MAX_BYTES,
        )
        ready.put(("ready", materialized.identity))
        if not start.wait(15):
            outcomes.put(("error", "start-timeout"))
            return
        try:
            published = atomic_io.atomic_commit_bound_staging_no_replace(
                path=final,
                staging_path=staging,
                expected_staging_identity=materialized.identity,
                expected_size=materialized.size,
                expected_sha256=materialized.sha256,
                expected_parent_identity=parent_identity,
            )
        except atomic_io.AtomicWriteConflictError:
            if os.path.lexists(staging):
                atomic_io.secure_unlink(
                    staging,
                    expected_identity=materialized.identity,
                    expected_parent_identity=parent_identity,
                )
            outcomes.put(("lost", materialized.identity))
        else:
            outcomes.put(("won", published.identity))
    except BaseException as error:  # pragma: no cover - surfaced in parent
        outcomes.put(("error", repr(error)))
        raise


def _runtime_admission_hard_kill_worker(
    *,
    mode: str,
    local_app_data_text: str,
    final_text: str,
    staging_text: str,
    inner_text: str,
    payload: bytes,
) -> None:
    os.environ["LOCALAPPDATA"] = local_app_data_text
    final = Path(final_text)
    staging = Path(staging_text)
    inner = Path(inner_text)
    parent_identity = path_identity(final.parent)

    if mode == "before_inner_commit":

        def kill_before_inner_commit(**_kwargs: object) -> tuple[int, int, int]:
            os._exit(91)

        atomic_io.secure_commit_sibling_no_replace = kill_before_inner_commit
        atomic_io.atomic_materialize_staging_bytes(
            staging_path=staging,
            inner_temp_path=inner,
            payload=payload,
            expected_parent_identity=parent_identity,
            maximum_size=RUNTIME_LIVE_ATTEMPT_ADMISSION_MAX_BYTES,
        )
    elif mode == "after_staging_flush":

        def kill_after_staging(point: str) -> None:
            if point == atomic_io.STAGING_MATERIALIZE_FAULT_POINT:
                os._exit(92)

        atomic_io.atomic_materialize_staging_bytes(
            staging_path=staging,
            inner_temp_path=inner,
            payload=payload,
            expected_parent_identity=parent_identity,
            maximum_size=RUNTIME_LIVE_ATTEMPT_ADMISSION_MAX_BYTES,
            fault_hook=kill_after_staging,
        )
    elif mode == "before_final_no_replace":
        atomic_io.atomic_materialize_staging_bytes(
            staging_path=staging,
            inner_temp_path=inner,
            payload=payload,
            expected_parent_identity=parent_identity,
            maximum_size=RUNTIME_LIVE_ATTEMPT_ADMISSION_MAX_BYTES,
        )
        os._exit(93)
    elif mode == "after_final_commit":
        materialized = atomic_io.atomic_materialize_staging_bytes(
            staging_path=staging,
            inner_temp_path=inner,
            payload=payload,
            expected_parent_identity=parent_identity,
            maximum_size=RUNTIME_LIVE_ATTEMPT_ADMISSION_MAX_BYTES,
        )

        def kill_after_commit(point: str) -> None:
            if point == atomic_io.NO_REPLACE_COMMIT_FAULT_POINT:
                os._exit(94)

        atomic_io.atomic_commit_bound_staging_no_replace(
            path=final,
            staging_path=staging,
            expected_staging_identity=materialized.identity,
            expected_size=materialized.size,
            expected_sha256=materialized.sha256,
            expected_parent_identity=parent_identity,
            fault_hook=kill_after_commit,
        )
    else:  # pragma: no cover - child reports invalid test protocol by exit code
        os._exit(99)

    os._exit(98)


def _runtime_admission_recovery_worker(
    *,
    action: str,
    local_app_data_text: str,
    final_text: str,
    staging_text: str,
    inner_text: str,
    runtime_root_text: str,
    payload: bytes,
    expected_identity: tuple[int, int, int] | None,
    outcomes: Any,
) -> None:
    os.environ["LOCALAPPDATA"] = local_app_data_text
    final = Path(final_text)
    staging = Path(staging_text)
    inner = Path(inner_text)
    runtime_root = Path(runtime_root_text)
    parent_identity = path_identity(final.parent)
    try:
        if action == "delete_inner":
            assert expected_identity is not None
            assert not final.exists() and not staging.exists()
            assert inner.read_bytes() == payload
            atomic_io.secure_unlink(
                inner,
                expected_identity=expected_identity,
                expected_parent_identity=parent_identity,
            )
        elif action == "delete_staging":
            assert expected_identity is not None
            assert not final.exists() and not inner.exists()
            assert staging.read_bytes() == payload
            atomic_io.secure_unlink(
                staging,
                expected_identity=expected_identity,
                expected_parent_identity=parent_identity,
            )
        elif action == "commit_bound":
            assert expected_identity is not None
            atomic_io.atomic_commit_bound_staging_no_replace(
                path=final,
                staging_path=staging,
                expected_staging_identity=expected_identity,
                expected_size=len(payload),
                expected_sha256="sha256:" + sha256(payload).hexdigest(),
                expected_parent_identity=parent_identity,
            )
        elif action == "publish_retry":
            atomic_io.atomic_publish_bytes_no_replace(
                path=final,
                staging_path=staging,
                payload=payload,
                expected_parent_identity=parent_identity,
                maximum_size=RUNTIME_LIVE_ATTEMPT_ADMISSION_MAX_BYTES,
            )
        elif action != "observe":
            raise AssertionError(f"unknown recovery action: {action}")

        observed = load_runtime_live_attempt_admission()
        outcomes.put(
            (
                "ok",
                final.read_bytes() if final.exists() else None,
                observed is not None,
                staging.exists(),
                inner.exists(),
                tuple(sorted(path.name for path in runtime_root.iterdir())),
            )
        )
    except BaseException as error:  # pragma: no cover - surfaced in parent
        outcomes.put(("error", repr(error)))
        raise


def _spawn_runtime_admission_hard_kill(
    *,
    mode: str,
    expected_exitcode: int,
    local_app_data: Path,
    final: Path,
    staging: Path,
    inner: Path,
    payload: bytes,
) -> None:
    process = multiprocessing.get_context("spawn").Process(
        target=_runtime_admission_hard_kill_worker,
        kwargs={
            "mode": mode,
            "local_app_data_text": str(local_app_data),
            "final_text": str(final),
            "staging_text": str(staging),
            "inner_text": str(inner),
            "payload": payload,
        },
    )
    process.start()
    process.join(20)
    if process.is_alive():
        process.kill()
        process.join(10)
        pytest.fail(f"hard-kill worker hung at {mode}")
    assert process.exitcode == expected_exitcode


def _spawn_runtime_admission_recovery(
    *,
    action: str,
    local_app_data: Path,
    final: Path,
    staging: Path,
    inner: Path,
    runtime_root: Path,
    payload: bytes,
    expected_identity: tuple[int, int, int] | None = None,
) -> tuple[object, ...]:
    context = multiprocessing.get_context("spawn")
    outcomes = context.Queue()
    process = context.Process(
        target=_runtime_admission_recovery_worker,
        kwargs={
            "action": action,
            "local_app_data_text": str(local_app_data),
            "final_text": str(final),
            "staging_text": str(staging),
            "inner_text": str(inner),
            "runtime_root_text": str(runtime_root),
            "payload": payload,
            "expected_identity": expected_identity,
            "outcomes": outcomes,
        },
    )
    process.start()
    result = outcomes.get(timeout=20)
    process.join(20)
    if process.is_alive():
        process.kill()
        process.join(10)
        pytest.fail(f"recovery worker hung at {action}")
    assert process.exitcode == 0
    assert result[0] == "ok"
    return result


def _build_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    run_id: str = "1" * 32,
    attempt_id: str = "2" * 32,
    session_root_input: str = "canonical",
) -> tuple[Path, bytes]:
    local = tmp_path / "local"
    state_root = local / "HSConfig"
    session_root = tmp_path / f"session-{run_id}"
    runtime_root = tmp_path / "runtime"
    output_base = tmp_path / "output"
    output_root = output_base / "ShadowPriest"
    operation = state_root / "output-operation-admission.json"
    for directory in (
        state_root,
        session_root,
        runtime_root,
        output_root,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    operation.write_bytes(f"operation:{run_id}\n".encode())
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    if session_root_input == "relative":
        monkeypatch.chdir(tmp_path)
        session_root_argument = Path(session_root.name)
    elif session_root_input == "dotdot":
        detour = tmp_path / "detour"
        detour.mkdir()
        session_root_argument = detour / ".." / session_root.name
    elif session_root_input == "symlink":
        session_root_argument = tmp_path / "session-link"
        try:
            session_root_argument.symlink_to(session_root, target_is_directory=True)
        except OSError as error:
            pytest.skip(f"directory symlink unavailable: {error}")
    elif session_root_input == "canonical":
        session_root_argument = session_root
    else:
        raise AssertionError(session_root_input)
    final = runtime_live_attempt_admission_path()
    raw = build_runtime_live_attempt_admission_bytes(
        run_id=run_id,
        apply_attempt_id=attempt_id,
        retention_owner_run_id=run_id,
        session_root=session_root_argument,
        session_root_identity=path_identity(session_root),
        operator_profile_sha256=_digest("3"),
        state_root_identity=path_identity(state_root),
        runtime_root=runtime_root,
        runtime_root_identity=path_identity(runtime_root),
        output_base_root=output_base,
        output_base_root_identity=path_identity(output_base),
        output_root=output_root,
        output_root_identity=path_identity(output_root),
        output_operation_admission_path=operation,
        output_operation_admission_identity=path_identity(operation),
        output_operation_admission_sha256=_digest("4"),
        output_child_binding_sha256=_digest("5"),
        publication_revision="revisions/sha256-" + "6" * 64,
        publication_content_root_sha256=_digest("6"),
        package_root_sha256=_digest("7"),
        pre_apply_runtime_snapshot_sha256=_digest("8"),
        apply_invocation_sha256=_digest("9"),
        retention_fence_path=(
            runtime_root
            / ".hsconfig"
            / "attempt-retention"
            / f"{attempt_id}.json"
        ),
    )
    return final, raw


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _admission_projection_arguments(raw: bytes) -> dict[str, object]:
    document = json.loads(raw)
    return {
        "run_id": document["run_id"],
        "apply_attempt_id": document["apply_attempt_id"],
        "retention_owner_run_id": document["retention_owner_run_id"],
        "session_root": Path(document["session_root"]),
        "session_root_identity": tuple(document["session_root_identity"]),
        "operator_profile_sha256": document["operator_profile_sha256"],
        "state_root_identity": tuple(document["state_root_identity"]),
        "runtime_root": Path(document["runtime_root"]),
        "runtime_root_identity": tuple(document["runtime_root_identity"]),
        "output_base_root": Path(document["output_base_root"]),
        "output_base_root_identity": tuple(
            document["output_base_root_identity"]
        ),
        "output_root": Path(document["output_root"]),
        "output_root_identity": tuple(document["output_root_identity"]),
        "output_operation_admission_path": Path(
            document["output_operation_admission_path"]
        ),
        "output_operation_admission_identity": tuple(
            document["output_operation_admission_identity"]
        ),
        "output_operation_admission_sha256": document[
            "output_operation_admission_sha256"
        ],
        "output_child_binding_sha256": document[
            "output_child_binding_sha256"
        ],
        "publication_revision": document["publication_revision"],
        "publication_content_root_sha256": document[
            "publication_content_root_sha256"
        ],
        "package_root_sha256": document["package_root_sha256"],
        "pre_apply_runtime_snapshot_sha256": document[
            "pre_apply_runtime_snapshot_sha256"
        ],
        "apply_invocation_sha256": document["apply_invocation_sha256"],
        "retention_fence_path": Path(document["retention_fence_path"]),
    }


def _reseal(document: dict[str, object]) -> bytes:
    unsigned = dict(document)
    unsigned.pop("content_sha256", None)
    document = {
        **unsigned,
        "content_sha256": "sha256:" + sha256(_canonical(unsigned)).hexdigest(),
    }
    return _canonical(document)


def _write_and_load(
    final: Path,
    raw: bytes,
) -> RuntimeLiveAttemptAdmissionEvidence:
    final.write_bytes(raw)
    loaded = load_runtime_live_attempt_admission()
    assert loaded is not None
    return loaded


def test_runtime_live_admission_projection_matches_live_builder_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _final, raw = _build_admission(tmp_path, monkeypatch)

    def forbidden_live_binding(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise AssertionError("projection-observed-live-filesystem")

    monkeypatch.setattr(
        runtime_live_admission,
        "_require_existing_directory_binding",
        forbidden_live_binding,
    )
    monkeypatch.setattr(
        runtime_live_admission,
        "_require_existing_file_binding",
        forbidden_live_binding,
    )

    projected = (
        runtime_live_admission._project_runtime_live_attempt_admission_bytes(
            **_admission_projection_arguments(raw)
        )
    )

    assert projected == raw


def test_runtime_live_admission_projection_rejects_unbound_publication_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _final, raw = _build_admission(tmp_path, monkeypatch)
    arguments = _admission_projection_arguments(raw)
    arguments["publication_revision"] = "revisions/sha256-" + "a" * 64

    with pytest.raises(
        ValueError,
        match="^runtime_live_admission_publication_binding_invalid$",
    ):
        runtime_live_admission._project_runtime_live_attempt_admission_bytes(
            **arguments
        )


def test_runtime_live_admission_builder_normalizes_each_path_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _final, raw = _build_admission(tmp_path, monkeypatch)
    arguments = _admission_projection_arguments(raw)
    session_root = Path(arguments["session_root"])

    class SingleUsePath:
        def __init__(self, value: Path) -> None:
            self.value = value
            self.calls = 0

        def __fspath__(self) -> str:
            self.calls += 1
            if self.calls != 1:
                raise AssertionError("builder-reobserved-caller-path")
            return os.fspath(self.value)

    single_use_path = SingleUsePath(session_root)
    arguments["session_root"] = single_use_path

    rebuilt = build_runtime_live_attempt_admission_bytes(**arguments)

    assert rebuilt == raw
    assert single_use_path.calls == 1


def test_runtime_live_admission_builder_still_requires_live_operation_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _final, raw = _build_admission(tmp_path, monkeypatch)
    arguments = _admission_projection_arguments(raw)
    operation_path = Path(arguments["output_operation_admission_path"])
    operation_path.unlink()

    with pytest.raises(
        ValueError,
        match="^runtime_live_admission_output_operation_admission_path_invalid$",
    ):
        build_runtime_live_attempt_admission_bytes(**arguments)


def test_runtime_live_admission_has_closed_bounded_schema_fixed_path_and_absent_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fresh_local = tmp_path / "fresh-local"
    monkeypatch.setenv("LOCALAPPDATA", str(fresh_local))
    fixed_path = runtime_live_attempt_admission_path()
    assert fixed_path == (
        fresh_local / "HSConfig" / "live-start-active-attempt.json"
    )
    assert load_runtime_live_attempt_admission() is None
    assert not fresh_local.exists()

    final, raw = _build_admission(tmp_path / "valid", monkeypatch)
    document = json.loads(raw)
    assert set(document) == RUNTIME_LIVE_ATTEMPT_ADMISSION_FIELDS
    assert len(document) == len(RUNTIME_LIVE_ATTEMPT_ADMISSION_FIELDS) == 26
    assert document["schema_version"] == (
        RUNTIME_LIVE_ATTEMPT_ADMISSION_SCHEMA_VERSION
    )
    assert document["record_kind"] == RUNTIME_LIVE_ATTEMPT_ADMISSION_KIND
    assert raw == _canonical(document)
    assert len(raw) <= RUNTIME_LIVE_ATTEMPT_ADMISSION_MAX_BYTES
    expected = _write_and_load(final, raw)
    assert expected.admission_path == final

    malformed_documents: list[bytes] = []
    for mutate in ("unknown", "missing", "wrong_schema", "self_digest"):
        candidate = dict(document)
        if mutate == "unknown":
            candidate["unknown"] = None
        elif mutate == "missing":
            del candidate["run_id"]
        elif mutate == "wrong_schema":
            candidate["schema_version"] = True
        else:
            candidate["content_sha256"] = _digest("a")
        malformed_documents.append(_canonical(candidate))
    malformed_documents.extend(
        (
            b'{"schema_version":1,"schema_version":1}',
            b'{"value":NaN}',
            b"[" * 2_000 + b"0" + b"]" * 2_000,
            b"{" + b" " * RUNTIME_LIVE_ATTEMPT_ADMISSION_MAX_BYTES + b"}",
        )
    )
    for malformed in malformed_documents:
        final.write_bytes(malformed)
        with pytest.raises(ValueError, match="runtime_live_admission"):
            load_runtime_live_attempt_admission()


def _assert_two_process_admission_claim_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final, first_raw = _build_admission(
        tmp_path,
        monkeypatch,
        run_id="1" * 32,
        attempt_id="2" * 32,
    )
    _same_final, second_raw = _build_admission(
        tmp_path,
        monkeypatch,
        run_id="a" * 32,
        attempt_id="b" * 32,
    )
    context = multiprocessing.get_context("spawn")
    ready = context.Queue()
    start = context.Event()
    outcomes = context.Queue()
    payloads = (first_raw, second_raw)
    processes = [
        context.Process(
            target=_runtime_admission_claim_contender,
            kwargs={
                "parent_text": str(final.parent),
                "final_text": str(final),
                "staging_text": str(
                    final.with_name(f".{final.name}.contender-{index}.staged")
                ),
                "payload": payload,
                "ready": ready,
                "start": start,
                "outcomes": outcomes,
            },
        )
        for index, payload in enumerate(payloads)
    ]
    for process in processes:
        process.start()
    assert [ready.get(timeout=20)[0] for _process in processes] == [
        "ready",
        "ready",
    ]
    assert not final.exists()
    start.set()
    result_rows = [outcomes.get(timeout=20) for _process in processes]
    for process in processes:
        process.join(20)
        assert process.exitcode == 0

    assert sorted(row[0] for row in result_rows) == ["lost", "won"]
    assert final.read_bytes() in payloads
    observed = load_runtime_live_attempt_admission()
    assert observed is not None
    assert observed.run_id in {"1" * 32, "a" * 32}
    assert not list(final.parent.glob(f".{final.name}.contender-*.staged"))


def test_two_process_claim_race_creates_exactly_one_admission_without_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_two_process_admission_claim_race(tmp_path, monkeypatch)


def test_admission_atomic_no_replace_never_overwrites_two_process_winner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _assert_two_process_admission_claim_race(tmp_path, monkeypatch)


def test_admission_atomic_no_replace_is_absent_or_complete_at_every_crash_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crash_rows = (
        ("before_final_no_replace", 93, False),
        ("after_final_commit", 94, True),
    )
    for mode, exitcode, final_committed in crash_rows:
        case = tmp_path / mode
        final, raw = _build_admission(case, monkeypatch)
        staging = final.with_name(f".{final.name}.attempt.staged")
        inner = staging.with_name(f".{staging.name}.live-start-atomic.tmp")
        runtime_root = case / "runtime"
        runtime_before = tuple(runtime_root.iterdir())
        local_app_data = case / "local"

        _spawn_runtime_admission_hard_kill(
            mode=mode,
            expected_exitcode=exitcode,
            local_app_data=local_app_data,
            final=final,
            staging=staging,
            inner=inner,
            payload=raw,
        )

        assert final.exists() is final_committed
        if final_committed:
            assert final.read_bytes() == raw
            assert not staging.exists()
            result = _spawn_runtime_admission_recovery(
                action="observe",
                local_app_data=local_app_data,
                final=final,
                staging=staging,
                inner=inner,
                runtime_root=runtime_root,
                payload=raw,
            )
        else:
            assert staging.read_bytes() == raw
            assert not inner.exists()
            result = _spawn_runtime_admission_recovery(
                action="commit_bound",
                local_app_data=local_app_data,
                final=final,
                staging=staging,
                inner=inner,
                runtime_root=runtime_root,
                payload=raw,
                expected_identity=path_identity(staging),
            )

        assert result[1:] == (raw, True, False, False, ())
        assert final.read_bytes() == raw
        assert load_runtime_live_attempt_admission() is not None
        assert tuple(runtime_root.iterdir()) == runtime_before
        assert not staging.exists()
        assert not inner.exists()


def test_admission_staging_inner_temp_hard_kills_reconcile_before_no_replace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final, raw = _build_admission(tmp_path, monkeypatch)
    staging = final.with_name(f".{final.name}.attempt.staged")
    inner = staging.with_name(f".{staging.name}.live-start-atomic.tmp")
    runtime_root = tmp_path / "runtime"
    runtime_before = tuple(runtime_root.iterdir())
    local_app_data = tmp_path / "local"

    _spawn_runtime_admission_hard_kill(
        mode="before_inner_commit",
        expected_exitcode=91,
        local_app_data=local_app_data,
        final=final,
        staging=staging,
        inner=inner,
        payload=raw,
    )

    assert not final.exists()
    assert not staging.exists()
    assert inner.read_bytes() == raw
    deleted = _spawn_runtime_admission_recovery(
        action="delete_inner",
        local_app_data=local_app_data,
        final=final,
        staging=staging,
        inner=inner,
        runtime_root=runtime_root,
        payload=raw,
        expected_identity=path_identity(inner),
    )
    assert deleted[1:] == (None, False, False, False, ())
    assert not final.exists()
    retried = _spawn_runtime_admission_recovery(
        action="publish_retry",
        local_app_data=local_app_data,
        final=final,
        staging=staging,
        inner=inner,
        runtime_root=runtime_root,
        payload=raw,
    )
    assert retried[1:] == (raw, True, False, False, ())
    assert final.read_bytes() == raw
    assert tuple(runtime_root.iterdir()) == runtime_before
    assert not staging.exists()
    assert not inner.exists()


def test_staging_flush_crash_is_cleaned_without_promotion_or_runtime_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final, raw = _build_admission(tmp_path, monkeypatch)
    runtime_root = tmp_path / "runtime"
    runtime_before = tuple(runtime_root.iterdir())
    staging = final.with_name(f".{final.name}.attempt.staged")
    inner = staging.with_name(f".{staging.name}.live-start-atomic.tmp")
    local_app_data = tmp_path / "local"

    _spawn_runtime_admission_hard_kill(
        mode="after_staging_flush",
        expected_exitcode=92,
        local_app_data=local_app_data,
        final=final,
        staging=staging,
        inner=inner,
        payload=raw,
    )

    assert not final.exists()
    assert staging.read_bytes() == raw
    assert not inner.exists()
    deleted = _spawn_runtime_admission_recovery(
        action="delete_staging",
        local_app_data=local_app_data,
        final=final,
        staging=staging,
        inner=inner,
        runtime_root=runtime_root,
        payload=raw,
        expected_identity=path_identity(staging),
    )
    assert deleted[1:] == (None, False, False, False, ())
    assert not final.exists()
    assert not staging.exists()
    assert not inner.exists()
    assert tuple(runtime_root.iterdir()) == runtime_before

    retried = _spawn_runtime_admission_recovery(
        action="publish_retry",
        local_app_data=local_app_data,
        final=final,
        staging=staging,
        inner=inner,
        runtime_root=runtime_root,
        payload=raw,
    )
    assert retried[1:] == (raw, True, False, False, ())
    assert final.read_bytes() == raw
    assert tuple(runtime_root.iterdir()) == runtime_before


def test_crash_after_admission_before_invocation_receipt_continues_same_attempt_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final, raw = _build_admission(tmp_path, monkeypatch)
    staging = final.with_name(f".{final.name}.attempt.staged")
    parent_identity = path_identity(final.parent)
    published = atomic_io.atomic_publish_bytes_no_replace(
        path=final,
        staging_path=staging,
        payload=raw,
        expected_parent_identity=parent_identity,
        maximum_size=RUNTIME_LIVE_ATTEMPT_ADMISSION_MAX_BYTES,
    )
    expected = load_runtime_live_attempt_admission()
    assert expected is not None
    assert expected.admission_identity == published.identity
    invocation_receipt = (
        expected.runtime_root
        / ".hsconfig"
        / "receipts"
        / "apply_invocation.json"
    )
    assert not invocation_receipt.exists()
    assert (
        runtime_live_admission._require_exact_runtime_live_attempt(expected)
        == expected
    )

    competitor_staging = final.with_name(f".{final.name}.competitor.staged")
    contender = atomic_io.atomic_materialize_staging_bytes(
        staging_path=competitor_staging,
        inner_temp_path=competitor_staging.with_name(
            f".{competitor_staging.name}.live-start-atomic.tmp"
        ),
        payload=raw,
        expected_parent_identity=parent_identity,
        maximum_size=RUNTIME_LIVE_ATTEMPT_ADMISSION_MAX_BYTES,
    )
    with pytest.raises(atomic_io.AtomicWriteConflictError):
        atomic_io.atomic_commit_bound_staging_no_replace(
            path=final,
            staging_path=competitor_staging,
            expected_staging_identity=contender.identity,
            expected_size=contender.size,
            expected_sha256=contender.sha256,
            expected_parent_identity=parent_identity,
        )
    atomic_io.secure_unlink(
        competitor_staging,
        expected_identity=contender.identity,
        expected_parent_identity=parent_identity,
    )
    assert load_runtime_live_attempt_admission() == expected


def test_runtime_live_admission_has_no_installer_controller_or_published_apply_import() -> None:
    module_path = Path(__file__).parents[1] / "src" / "hsconfig" / "runtime_live_admission.py"
    module = ast.parse(module_path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                package = "hsconfig"
                base = (
                    f"{package}.{node.module}"
                    if node.module
                    else package
                )
            else:
                base = node.module or ""
            if base:
                imports.add(base)
                imports.update(
                    f"{base}.{alias.name}"
                    for alias in node.names
                    if alias.name != "*"
                )
        elif (
            isinstance(node, ast.Call)
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
            and (
                isinstance(node.func, ast.Name)
                and node.func.id == "__import__"
                or isinstance(node.func, ast.Attribute)
                and node.func.attr == "import_module"
            )
        ):
            imports.add(node.args[0].value)
    forbidden = {
        "hsconfig.runtime_installer",
        "hsconfig.live_start_controller",
        "hsconfig.published_apply",
        "hsconfig.operator_profile",
        "hsconfig.output_publisher",
    }
    assert not {
        candidate
        for candidate in imports
        if any(
            candidate == forbidden_name
            or candidate.startswith(f"{forbidden_name}.")
            for forbidden_name in forbidden
        )
    }


@pytest.mark.parametrize("session_root_input", ("relative", "dotdot", "symlink"))
def test_runtime_live_admission_builder_rejects_noncanonical_input_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    session_root_input: str,
) -> None:
    with pytest.raises(ValueError, match="runtime_live_admission_session_root"):
        _build_admission(
            tmp_path,
            monkeypatch,
            session_root_input=session_root_input,
        )


def test_runtime_live_admission_loader_rejects_negative_path_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final, raw = _build_admission(tmp_path, monkeypatch)
    document = json.loads(raw)
    document["session_root_identity"] = [-1, 2, 3]
    final.write_bytes(_reseal(document))

    with pytest.raises(ValueError, match="runtime_live_admission_session_root_identity"):
        load_runtime_live_attempt_admission()


def test_runtime_live_admission_absence_rejects_non_directory_ancestor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocking_ancestor = tmp_path / "local" / "blocking-file"
    blocking_ancestor.parent.mkdir()
    blocking_ancestor.write_bytes(b"not-a-directory")
    monkeypatch.setenv("LOCALAPPDATA", str(blocking_ancestor / "descendant"))
    admission = runtime_live_attempt_admission_path()

    with pytest.raises(ValueError, match="runtime_live_admission_parent_invalid"):
        load_runtime_live_attempt_admission()

    assert not admission.exists()


@pytest.mark.parametrize(
    ("path_relation", "identity_relation", "expected_error"),
    (
        ("same", "same", "runtime_live_admission_blocks_publication"),
        (
            "same",
            "different",
            "runtime_live_admission_output_root_identity_changed",
        ),
        ("same", "absent", "runtime_live_admission_blocks_publication"),
        ("different", "same", "runtime_live_admission_blocks_publication"),
        ("different", "different", None),
        ("different", "absent", None),
    ),
)
def test_publication_gate_blocks_same_path_or_identity_and_allows_only_unrelated_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path_relation: str,
    identity_relation: str,
    expected_error: str | None,
) -> None:
    final, raw = _build_admission(tmp_path, monkeypatch)
    observed = _write_and_load(final, raw)
    admitted_identity = observed.output_root_identity
    foreign_identity = (
        admitted_identity[0],
        admitted_identity[1],
        admitted_identity[2] + 1,
    )
    caller_path = (
        observed.output_root
        if path_relation == "same"
        else tmp_path / "unrelated-output" / "OtherDeck"
    )
    caller_identity = {
        "same": admitted_identity,
        "different": foreign_identity,
        "absent": None,
    }[identity_relation]

    if expected_error is None:
        require_live_admission_allows_publication(
            output_root=caller_path,
            output_root_identity=caller_identity,
        )
    else:
        with pytest.raises(ValueError, match=rf"^{expected_error}$"):
            require_live_admission_allows_publication(
                output_root=caller_path,
                output_root_identity=caller_identity,
            )


def test_legacy_root_bootstrap_gate_rejects_same_path_active_or_malformed_final_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final, raw = _build_admission(tmp_path, monkeypatch)
    runtime_root = tmp_path / "runtime"

    require_live_admission_allows_legacy_root_bootstrap(
        runtime_root=runtime_root,
    )
    final.write_bytes(raw)
    with pytest.raises(
        ValueError,
        match="runtime_live_admission_blocks_legacy_root_bootstrap",
    ):
        require_live_admission_allows_legacy_root_bootstrap(
            runtime_root=runtime_root,
        )

    final.write_bytes(b"{}")
    with pytest.raises(ValueError, match="runtime_live_admission"):
        require_live_admission_allows_legacy_root_bootstrap(
            runtime_root=runtime_root,
        )


def test_same_attempt_recovery_revalidates_exact_admission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final, raw = _build_admission(tmp_path, monkeypatch)
    expected = _write_and_load(final, raw)

    assert (
        runtime_live_admission._require_exact_runtime_live_attempt(expected)
        == expected
    )

    final.write_bytes(raw.replace(b'"run_id":"', b'"run_id":"a', 1))
    with pytest.raises(ValueError, match="runtime_live_admission"):
        runtime_live_admission._require_exact_runtime_live_attempt(expected)


def test_forged_replaced_wrong_run_or_wrong_attempt_admission_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final, raw = _build_admission(tmp_path, monkeypatch)
    expected = _write_and_load(final, raw)
    forged_rows = (
        object(),
        replace(expected, run_id="a" * 32),
        replace(expected, apply_attempt_id="b" * 32),
    )
    for forged in forged_rows:
        with pytest.raises((TypeError, ValueError), match="runtime_live_admission"):
            runtime_live_admission._require_exact_runtime_live_attempt(forged)  # type: ignore[arg-type]

    held = final.with_name("held-admission.json")
    final.rename(held)
    final.write_bytes(raw)
    assert path_identity(final) != expected.admission_identity
    with pytest.raises(
        ValueError,
        match="runtime_live_admission_exact_binding_invalid",
    ):
        runtime_live_admission._require_exact_runtime_live_attempt(expected)


def test_release_exact_runtime_admission_unlinks_only_bound_old_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final, raw = _build_admission(tmp_path, monkeypatch)
    expected = _write_and_load(final, raw)

    observed = release_runtime_live_attempt_exact(expected=expected)

    assert observed.disposition == "old_unlinked"
    _assert_historical_release_binding(observed, expected)
    assert observed.foreign_successor_identity is None
    assert observed.foreign_successor_sha256 is None
    assert not final.exists()


def test_release_exact_runtime_admission_accepts_absence_idempotently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final, raw = _build_admission(tmp_path, monkeypatch)
    expected = _write_and_load(final, raw)
    final.unlink()

    observed = release_runtime_live_attempt_exact(expected=expected)

    assert observed.disposition == "already_absent"
    _assert_historical_release_binding(observed, expected)
    assert observed.foreign_successor_identity is None
    assert observed.foreign_successor_sha256 is None


def test_release_exact_runtime_admission_preserves_valid_foreign_successor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    final, raw = _build_admission(tmp_path, monkeypatch)
    expected = _write_and_load(final, raw)
    held_old = final.with_name("held-old-admission.json")
    final.rename(held_old)
    _foreign_path, foreign_raw = _build_admission(
        tmp_path,
        monkeypatch,
        run_id="a" * 32,
        attempt_id="b" * 32,
    )
    final.write_bytes(foreign_raw)
    foreign_identity = path_identity(final)
    assert foreign_identity != expected.admission_identity

    observed = release_runtime_live_attempt_exact(expected=expected)

    assert observed.disposition == "valid_foreign_successor"
    _assert_historical_release_binding(observed, expected)
    assert observed.foreign_successor_identity == foreign_identity
    assert observed.foreign_successor_sha256 == (
        "sha256:" + sha256(foreign_raw).hexdigest()
    )
    assert final.read_bytes() == foreign_raw


def test_release_exact_runtime_admission_rejects_replaced_malformed_or_same_identity_changed_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for case in ("same_identity_changed", "same_bytes_replaced", "malformed"):
        case_root = tmp_path / case
        final, raw = _build_admission(case_root, monkeypatch)
        expected = _write_and_load(final, raw)
        if case == "same_identity_changed":
            _same_path, replacement = _build_admission(
                case_root,
                monkeypatch,
                run_id="a" * 32,
                attempt_id="b" * 32,
            )
            final.write_bytes(replacement)
            assert path_identity(final) == expected.admission_identity
        else:
            held_old = final.with_name("held-old-admission.json")
            final.rename(held_old)
            final.write_bytes(raw if case == "same_bytes_replaced" else b"{}\n")
            assert path_identity(final) != expected.admission_identity
        before = final.read_bytes()

        with pytest.raises(ValueError, match="runtime_live_admission"):
            release_runtime_live_attempt_exact(expected=expected)

        assert final.read_bytes() == before


def _assert_historical_release_binding(
    observed: object,
    expected: RuntimeLiveAttemptAdmissionEvidence,
) -> None:
    assert getattr(observed, "admission_path") == expected.admission_path
    assert (
        getattr(observed, "admission_parent_identity")
        == expected.admission_parent_identity
    )
    assert (
        getattr(observed, "historical_admission_identity")
        == expected.admission_identity
    )
    assert (
        getattr(observed, "historical_admission_sha256")
        == expected.admission_sha256
    )
