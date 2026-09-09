from __future__ import annotations

from contextlib import contextmanager
import json
import multiprocessing
import os
from pathlib import Path
import time
from typing import Any

import pytest

from hsconfig import live_start_controller as controller
from hsconfig import output_operation_admission, published_apply
from hsconfig import runtime_apply, runtime_installer
from hsconfig.current_output import resolve_current_package
from hsconfig.live_start_session import load_live_start_session
from hsconfig.operator_profile import derive_deck_output_binding, operator_profile_path
from hsconfig.runtime_live_admission import (
    load_runtime_live_attempt_admission,
    runtime_live_attempt_admission_path,
)
from hsconfig.runtime_package_match import build_runtime_package_match_report
from tests.test_codex_first_live_e2e import _local_state, _prepare_approved
from tests.test_configure_prepublication_apply import (
    _join_hard_kill_process,
    _persist_worker_oracle,
)


def _trace_lease(
    real: Any,
    *,
    name: str,
    trace: list[dict[str, Any]],
    events: dict[str, Any],
    before_enter: Any = None,
) -> Any:
    def mark(stage: str) -> None:
        label = f"{name}_{stage}"
        trace.append({"event": label, "time_ns": time.monotonic_ns()})
        if label in events:
            events[label].set()

    @contextmanager
    def observed(*args: Any, **kwargs: Any) -> Any:
        mark("attempt")
        if before_enter is not None:
            before_enter()
        with real(*args, **kwargs) as lease:
            mark("held")
            try:
                yield lease
            finally:
                mark("releasing")
        mark("released")

    return observed


def _patient_output_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    real = output_operation_admission.ExclusiveFileLock

    def patient(*args: Any, **kwargs: Any) -> Any:
        return real(*args, **(kwargs | {"timeout_seconds": 600.0}))

    monkeypatch.setattr(output_operation_admission, "ExclusiveFileLock", patient)


def _controller_barrier_worker(
    session_root: str,
    local_app_data: str,
    events: dict[str, Any],
    oracle_path: str,
) -> None:
    os.environ["LOCALAPPDATA"] = local_app_data
    trace: list[dict[str, Any]] = []

    def before_package() -> None:
        assert events["allow_controller_package"].wait(60), "package barrier timeout"

    with pytest.MonkeyPatch.context() as patch:
        _patient_output_lock(patch)
        for module, attribute, name, callback in (
            (controller, "lease_output_operation_admission", "controller_output", None),
            (published_apply, "lease_package_input", "controller_package", before_package),
            (runtime_installer, "_lease_runtime_apply_after_gates", "controller_runtime", None),
        ):
            patch.setattr(module, attribute, _trace_lease(
                getattr(module, attribute), name=name, trace=trace,
                events=events, before_enter=callback,
            ))
        result = controller.resume_live_start(session_root=Path(session_root))
    _persist_worker_oracle(Path(oracle_path), {"status": result.status, "trace": trace})
    events["controller_done"].set()


def _legacy_barrier_worker(
    output_root: str,
    runtime_root: str,
    local_app_data: str,
    events: dict[str, Any],
    oracle_path: str,
) -> None:
    os.environ["LOCALAPPDATA"] = local_app_data
    trace: list[dict[str, Any]] = []
    runtime = Path(runtime_root)
    assert not runtime.exists()
    bootstrap_checked = False

    with pytest.MonkeyPatch.context() as patch:
        _patient_output_lock(patch)
        for module, attribute, name in (
            (runtime_apply, "lease_output_operation_admission", "legacy_output"),
            (runtime_apply, "lease_package_input", "legacy_package"),
            (runtime_installer, "_lease_runtime_apply_after_gates", "legacy_runtime"),
        ):
            patch.setattr(module, attribute, _trace_lease(
                getattr(module, attribute), name=name, trace=trace, events=events,
            ))
        real_bootstrap = runtime_apply._bootstrap_legacy_runtime_root_from_context

        def observed_bootstrap(*args: Any, **kwargs: Any) -> Any:
            nonlocal bootstrap_checked
            assert not runtime.exists()
            result = real_bootstrap(*args, **kwargs)
            assert runtime.is_dir() and not runtime.is_symlink()
            assert tuple(runtime.iterdir()) == ()
            assert events["legacy_output_held"].is_set()
            assert events["legacy_package_held"].is_set()
            assert not events["legacy_runtime_attempt"].is_set()
            bootstrap_checked = True
            trace.append({"event": "legacy_empty_root", "time_ns": time.monotonic_ns()})
            return result

        patch.setattr(runtime_apply, "_bootstrap_legacy_runtime_root_from_context", observed_bootstrap)
        result = runtime_apply.apply_package(package_root=Path(output_root), runtime_root=runtime)
    _persist_worker_oracle(Path(oracle_path), {
        "status": result["status"],
        "runtime_write_performed": result["runtime_write_performed"],
        "bootstrap_checked": bootstrap_checked,
        "trace": trace,
    })
    events["legacy_done"].set()


def _stop_process(process: Any) -> None:
    try:
        if process.is_alive():
            process.terminate()
            process.join(10)
        if process.is_alive():
            process.kill()
            process.join(10)
        assert not process.is_alive(), "lock-order process could not be stopped"
    finally:
        if not process.is_alive():
            process.close()


def _assert_lease_order(trace: list[dict[str, Any]], prefix: str) -> None:
    held: set[str] = set()
    observed: set[str] = set()
    for row in trace:
        event = row["event"]
        for resource in ("output", "package", "runtime"):
            if event == f"{prefix}_{resource}_held":
                assert resource not in held
                if resource == "package":
                    assert "output" in held
                if resource == "runtime":
                    assert {"output", "package"} <= held
                held.add(resource)
                observed.add(resource)
            elif event == f"{prefix}_{resource}_releasing":
                assert resource in held
                if resource == "package":
                    assert "runtime" not in held
                if resource == "output":
                    assert held == {"output"}
                held.remove(resource)
    assert not held
    assert observed == {"output", "package", "runtime"}


def test_controller_and_legacy_install_lock_order_completes_without_deadlock_or_early_runtime_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _local_state(tmp_path, monkeypatch)
    fixture, prepared = _prepare_approved(tmp_path / "pipeline", monkeypatch)
    output = derive_deck_output_binding(fixture.profile, fixture.deck_name).output_root
    profile_before = operator_profile_path().read_bytes()
    legacy_runtime = tmp_path / "legacy-runtime"
    assert not legacy_runtime.exists()
    ctx = multiprocessing.get_context("spawn")
    events = {name: ctx.Event() for name in (
        "controller_output_held", "controller_package_attempt",
        "controller_package_held", "controller_runtime_attempt", "controller_done",
        "allow_controller_package", "legacy_output_attempt", "legacy_output_held",
        "legacy_package_attempt", "legacy_package_held", "legacy_runtime_attempt",
        "legacy_done",
    )}
    controller_oracle = tmp_path / "controller-oracle.json"
    legacy_oracle = tmp_path / "legacy-oracle.json"
    children: list[Any] = []
    try:
        owner = ctx.Process(target=_controller_barrier_worker, args=(
            str(prepared.run_root), os.environ["LOCALAPPDATA"], events, str(controller_oracle),
        ))
        owner.start()
        children.append(owner)
        assert events["controller_output_held"].wait(120)
        assert events["controller_package_attempt"].wait(120)
        assert not events["controller_package_held"].is_set()
        assert not events["controller_runtime_attempt"].is_set()
        assert not legacy_runtime.exists()
        legacy = ctx.Process(target=_legacy_barrier_worker, args=(
            str(output), str(legacy_runtime), os.environ["LOCALAPPDATA"], events, str(legacy_oracle),
        ))
        legacy.start()
        children.append(legacy)
        assert events["legacy_output_attempt"].wait(30)
        assert not events["legacy_output_held"].wait(0.2)
        assert not events["legacy_package_attempt"].is_set()
        assert not events["legacy_runtime_attempt"].is_set()
        assert not events["legacy_done"].is_set()
        assert not legacy_runtime.exists()
        assert operator_profile_path().read_bytes() == profile_before
        events["allow_controller_package"].set()
        while children:
            _join_hard_kill_process(
                children.pop(0), expected_exitcode=0, timeout_seconds=360,
            )
    finally:
        events["allow_controller_package"].set()
        for child in children:
            _stop_process(child)

    owner_result = json.loads(controller_oracle.read_bytes())
    legacy_result = json.loads(legacy_oracle.read_bytes())
    assert events["controller_done"].is_set() and events["legacy_done"].is_set()
    assert owner_result["status"] == "LIVE_AND_MATCHED"
    assert legacy_result["status"] == "applied"
    assert legacy_result["runtime_write_performed"] is True
    assert legacy_result["bootstrap_checked"] is True
    _assert_lease_order(owner_result["trace"], "controller")
    _assert_lease_order(legacy_result["trace"], "legacy")
    owner_release = next(row["time_ns"] for row in owner_result["trace"]
                         if row["event"] == "controller_output_releasing")
    legacy_held = next(row["time_ns"] for row in legacy_result["trace"]
                      if row["event"] == "legacy_output_held")
    assert owner_release <= legacy_held
    package = resolve_current_package(output)
    for runtime in (fixture.profile.runtime_root, legacy_runtime):
        report = build_runtime_package_match_report(package_root=package, runtime_root=runtime)
        assert report["status"] == "matched"
        assert report["runtime_mapping_identity_valid"] is True
        assert report["runtime_tree_identity_valid"] is True
        assert report["missing_in_runtime"] == report["extra_in_runtime"] == []
        assert report["semantic_mismatch_count"] == 0
    assert operator_profile_path().read_bytes() == profile_before
    assert load_runtime_live_attempt_admission() is None
    terminal = load_live_start_session(prepared.run_root)
    runtime_admission = runtime_live_attempt_admission_path()
    runtime_staging = runtime_admission.with_name(
        ".live-start-active-attempt."
        f"{terminal.run_id}.{terminal.terminal_retirement['apply_attempt_id']}.staged"
    )
    runtime_inner = runtime_staging.with_name(
        f".{runtime_staging.name}.live-start-atomic.tmp"
    )
    for path in (
        output_operation_admission.output_operation_admission_path(),
        output_operation_admission.output_operation_admission_staging_path(),
        output_operation_admission.output_operation_admission_reserved_temp_path(),
        runtime_admission,
        runtime_staging,
        runtime_inner,
    ):
        assert not os.path.lexists(path)
