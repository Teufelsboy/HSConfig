from __future__ import annotations

import errno
import math
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import BinaryIO

import pytest

import hsconfig.atomic_io as atomic_io
from hsconfig.atomic_io import ExclusiveFileLock, LockTimeoutError


HOLDER_SCRIPT = """
import sys
import time
from pathlib import Path
from hsconfig.atomic_io import ExclusiveFileLock

lock_path = Path(sys.argv[1])
ready_path = Path(sys.argv[2])
release_path = Path(sys.argv[3])
with ExclusiveFileLock(lock_path, timeout_seconds=2.0):
    ready_path.write_text("LOCKED", encoding="utf-8")
    while not release_path.exists():
        time.sleep(0.01)
"""

DESCENDANT_HOLDER_SCRIPT = r"""
import subprocess
import sys
import time
from pathlib import Path
from hsconfig.atomic_io import ExclusiveFileLock

lock_path = Path(sys.argv[1])
ready_path = Path(sys.argv[2])
descendant_pid_path = Path(sys.argv[3])
descendant_release_path = Path(sys.argv[4])
descendant_done_path = Path(sys.argv[5])
descendant_ready_path = Path(sys.argv[6])
descendant_code = (
    "import sys, time\n"
    "from pathlib import Path\n"
    "release = Path(sys.argv[1])\n"
    "done = Path(sys.argv[2])\n"
    "ready = Path(sys.argv[3])\n"
    "ready.write_text('ready', encoding='utf-8')\n"
    "while not release.exists():\n"
    "    time.sleep(0.01)\n"
    "done.write_text('done', encoding='utf-8')\n"
)
with ExclusiveFileLock(lock_path, timeout_seconds=2.0):
    descendant = subprocess.Popen(
        [
            sys.executable,
            "-c",
            descendant_code,
            str(descendant_release_path),
            str(descendant_done_path),
            str(descendant_ready_path),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=False,
    )
    descendant_pid_path.write_text(str(descendant.pid), encoding="utf-8")
    deadline = time.monotonic() + 5.0
    while not descendant_ready_path.is_file():
        if descendant.poll() is not None:
            raise RuntimeError(
                f"descendant exited before readiness: {descendant.returncode}"
            )
        if time.monotonic() >= deadline:
            descendant.kill()
            descendant.wait(timeout=5)
            raise RuntimeError("descendant readiness deadline expired")
        time.sleep(0.01)
    ready_path.write_text("LOCKED", encoding="utf-8")
    while True:
        time.sleep(1)
"""

PROBE_SCRIPT = """
import sys
from pathlib import Path
from hsconfig.atomic_io import ExclusiveFileLock

with ExclusiveFileLock(Path(sys.argv[1]), timeout_seconds=5.0):
    Path(sys.argv[2]).write_text("ACQUIRED", encoding="utf-8")
"""


class InjectedBaseFault(BaseException):
    pass


class CleanupFault(RuntimeError):
    pass


def _subprocess_environment() -> dict[str, str]:
    environment = os.environ.copy()
    source_root = str(Path(__file__).parents[1] / "src")
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        source_root
        if not existing_pythonpath
        else os.pathsep.join((source_root, existing_pythonpath))
    )
    return environment


def _start_holder(
    lock_path: Path,
    ready_path: Path,
    release_path: Path,
) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            sys.executable,
            "-c",
            HOLDER_SCRIPT,
            str(lock_path),
            str(ready_path),
            str(release_path),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        close_fds=True,
        env=_subprocess_environment(),
    )


def _start_descendant_holder(
    lock_path: Path,
    ready_path: Path,
    descendant_pid_path: Path,
    descendant_release_path: Path,
    descendant_done_path: Path,
    descendant_ready_path: Path,
) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            sys.executable,
            "-c",
            DESCENDANT_HOLDER_SCRIPT,
            str(lock_path),
            str(ready_path),
            str(descendant_pid_path),
            str(descendant_release_path),
            str(descendant_done_path),
            str(descendant_ready_path),
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        close_fds=True,
        env=_subprocess_environment(),
    )


def _wait_for_holder_ready(
    holder: subprocess.Popen[str],
    ready_path: Path,
    *,
    timeout_seconds: float = 5.0,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while True:
        if ready_path.is_file():
            return
        return_code = holder.poll()
        if return_code is not None:
            _, stderr = holder.communicate(timeout=1)
            pytest.fail(
                f"lock holder exited before readiness: {return_code}: {stderr}"
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            pytest.fail("lock holder readiness deadline expired")
        time.sleep(min(0.01, remaining))


def _release_and_reap(
    holder: subprocess.Popen[str],
    release_path: Path,
) -> str | None:
    problems: list[str] = []
    try:
        release_path.write_text("release", encoding="utf-8")
    except Exception as exc:
        problems.append(f"release signal failed: {exc!r}")
    try:
        _, stderr = holder.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            holder.kill()
        except Exception as exc:
            problems.append(f"holder kill failed: {exc!r}")
        try:
            _, stderr = holder.communicate(timeout=5)
        except Exception as exc:
            problems.append(f"holder reap failed: {exc!r}")
            stderr = ""
    except Exception as exc:
        problems.append(f"holder communicate failed: {exc!r}")
        try:
            holder.kill()
            holder.communicate(timeout=5)
        except Exception as reap_exc:
            problems.append(f"holder forced reap failed: {reap_exc!r}")
        stderr = ""
    if holder.returncode not in {0, None}:
        problems.append(f"holder exited {holder.returncode}: {stderr}")
    return "; ".join(problems) if problems else None


def _stop_descendant(
    descendant_pid: int,
    release_path: Path,
    done_path: Path,
) -> str | None:
    problems: list[str] = []
    try:
        release_path.write_text("release", encoding="utf-8")
    except Exception as exc:
        problems.append(f"descendant release signal failed: {exc!r}")
    deadline = time.monotonic() + 5.0
    while not done_path.is_file() and time.monotonic() < deadline:
        time.sleep(0.01)
    if not done_path.is_file():
        try:
            os.kill(descendant_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except Exception as exc:
            problems.append(f"descendant terminate failed: {exc!r}")
        else:
            problems.append("descendant required forced termination")
    return "; ".join(problems) if problems else None


def _tracking_handle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, BinaryIO]:
    lock_path = tmp_path / "publisher.lock"
    handle = lock_path.open("a+b")
    real_path_open = Path.open

    def return_tracking_handle(
        path: Path,
        *args: object,
        **kwargs: object,
    ):
        if path == lock_path:
            return handle
        return real_path_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", return_tracking_handle)
    return lock_path, handle


def test_exclusive_file_lock_times_out_across_processes_then_can_be_reacquired(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "publisher.lock"
    ready_path = tmp_path / "holder.ready"
    release_path = tmp_path / "holder.release"
    holder = _start_holder(lock_path, ready_path, release_path)
    cleanup_problem: str | None = None
    try:
        _wait_for_holder_ready(holder, ready_path)

        started = time.monotonic()
        with pytest.raises(LockTimeoutError, match=re.escape(str(lock_path))):
            with ExclusiveFileLock(lock_path, timeout_seconds=0.2):
                pytest.fail("a second process acquired an already-held lock")
        elapsed = time.monotonic() - started

        assert elapsed >= 0.15
    finally:
        cleanup_problem = _release_and_reap(holder, release_path)

    assert cleanup_problem is None
    with ExclusiveFileLock(lock_path, timeout_seconds=0.5):
        assert lock_path.exists()
    assert lock_path.read_bytes() == b""


def test_exclusive_file_lock_can_be_reacquired_after_holder_is_hard_killed(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "publisher.lock"
    ready_path = tmp_path / "holder.ready"
    release_path = tmp_path / "holder.release"
    holder = _start_holder(lock_path, ready_path, release_path)
    cleanup_problem: str | None = None
    try:
        _wait_for_holder_ready(holder, ready_path)
        holder.kill()
        holder.communicate(timeout=5)

        with ExclusiveFileLock(lock_path, timeout_seconds=5.0):
            assert lock_path.exists()
    finally:
        if holder.poll() is None:
            cleanup_problem = _release_and_reap(holder, release_path)

    assert cleanup_problem is None


def test_noninherited_lock_handle_allows_probe_while_descendant_is_alive(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "publisher.lock"
    ready_path = tmp_path / "holder.ready"
    descendant_pid_path = tmp_path / "descendant.pid"
    descendant_release_path = tmp_path / "descendant.release"
    descendant_done_path = tmp_path / "descendant.done"
    descendant_ready_path = tmp_path / "descendant.ready"
    probe_path = tmp_path / "probe.acquired"
    holder = _start_descendant_holder(
        lock_path,
        ready_path,
        descendant_pid_path,
        descendant_release_path,
        descendant_done_path,
        descendant_ready_path,
    )
    descendant_pid = 0
    cleanup_problem: str | None = None
    try:
        _wait_for_holder_ready(holder, ready_path)
        descendant_pid = int(
            descendant_pid_path.read_text(encoding="utf-8")
        )
        assert descendant_ready_path.read_text(encoding="utf-8") == "ready"
        assert not descendant_done_path.exists()
        holder.kill()
        holder.communicate(timeout=5)
        assert not descendant_done_path.exists()

        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                PROBE_SCRIPT,
                str(lock_path),
                str(probe_path),
            ],
            capture_output=True,
            text=True,
            close_fds=True,
            env=_subprocess_environment(),
            timeout=10,
            check=False,
        )

        assert probe.returncode == 0, probe.stderr
        assert probe_path.read_text(encoding="utf-8") == "ACQUIRED"
        assert descendant_ready_path.read_text(encoding="utf-8") == "ready"
        assert not descendant_done_path.exists()
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.communicate(timeout=5)
        if not descendant_pid:
            try:
                recovered_pid = int(
                    descendant_pid_path.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeError, ValueError):
                pass
            else:
                if recovered_pid > 0:
                    descendant_pid = recovered_pid
        if descendant_pid:
            cleanup_problem = _stop_descendant(
                descendant_pid,
                descendant_release_path,
                descendant_done_path,
            )

    assert cleanup_problem is None


@pytest.mark.parametrize(
    "timeout_seconds",
    (-0.01, math.inf, -math.inf, math.nan),
)
def test_exclusive_file_lock_rejects_negative_or_non_finite_timeout(
    tmp_path: Path,
    timeout_seconds: float,
) -> None:
    with pytest.raises(ValueError, match="finite and non-negative"):
        ExclusiveFileLock(
            tmp_path / "publisher.lock",
            timeout_seconds=timeout_seconds,
        )


def test_zero_timeout_makes_exactly_one_immediate_acquire_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def reject_acquire(_handle: BinaryIO) -> None:
        nonlocal attempts
        attempts += 1
        raise OSError(errno.EACCES, "busy")

    monkeypatch.setattr(atomic_io, "_acquire_platform_lock", reject_acquire)

    with pytest.raises(LockTimeoutError):
        with ExclusiveFileLock(
            tmp_path / "publisher.lock",
            timeout_seconds=0.0,
        ):
            pytest.fail("zero-timeout lock unexpectedly succeeded")

    assert attempts == 1


def test_lock_retry_sleeps_only_for_monotonic_remaining_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0
    monotonic_values = iter((10.0, 10.02, 10.08, 10.11))
    sleeps: list[float] = []

    def reject_acquire(_handle: BinaryIO) -> None:
        nonlocal attempts
        attempts += 1
        raise OSError(errno.EACCES, "busy")

    monkeypatch.setattr(atomic_io, "_acquire_platform_lock", reject_acquire)
    monkeypatch.setattr(time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(time, "sleep", sleeps.append)

    with pytest.raises(LockTimeoutError):
        with ExclusiveFileLock(
            tmp_path / "publisher.lock",
            timeout_seconds=0.1,
        ):
            pytest.fail("contended lock unexpectedly succeeded")

    assert attempts == 3
    assert sleeps == pytest.approx([0.05, 0.02])


def test_non_contention_oserror_propagates_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def reject_acquire(_handle: BinaryIO) -> None:
        nonlocal attempts
        attempts += 1
        raise OSError(errno.EIO, "storage failure")

    monkeypatch.setattr(atomic_io, "_acquire_platform_lock", reject_acquire)

    with pytest.raises(OSError, match="storage failure"):
        with ExclusiveFileLock(
            tmp_path / "publisher.lock",
            timeout_seconds=1.0,
        ):
            pytest.fail("non-contention failure unexpectedly acquired")

    assert attempts == 1


@pytest.mark.parametrize("interruption_stage", ("acquire", "retry", "sleep"))
def test_pre_acquire_base_exception_never_unlocks_and_closes_handle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interruption_stage: str,
) -> None:
    lock_path, handle = _tracking_handle(tmp_path, monkeypatch)
    release_calls: list[BinaryIO] = []

    if interruption_stage == "acquire":
        monkeypatch.setattr(
            atomic_io,
            "_acquire_platform_lock",
            lambda _handle: (_ for _ in ()).throw(
                InjectedBaseFault("acquire")
            ),
        )
    else:
        monkeypatch.setattr(
            atomic_io,
            "_acquire_platform_lock",
            lambda _handle: (_ for _ in ()).throw(
                OSError(errno.EACCES, "busy")
            ),
        )
        if interruption_stage == "retry":
            monotonic_values = iter((1.0, InjectedBaseFault("retry")))

            def interrupted_monotonic() -> float:
                value = next(monotonic_values)
                if isinstance(value, BaseException):
                    raise value
                return value

            monkeypatch.setattr(time, "monotonic", interrupted_monotonic)
        else:
            monkeypatch.setattr(time, "monotonic", lambda: 1.0)
            monkeypatch.setattr(
                time,
                "sleep",
                lambda _seconds: (_ for _ in ()).throw(
                    InjectedBaseFault("sleep")
                ),
            )

    monkeypatch.setattr(
        atomic_io,
        "_release_platform_lock",
        release_calls.append,
    )

    try:
        with pytest.raises(InjectedBaseFault, match=interruption_stage):
            with ExclusiveFileLock(lock_path, timeout_seconds=0.5):
                pytest.fail("interrupted acquisition unexpectedly succeeded")

        assert release_calls == []
        assert handle.closed
    finally:
        handle.close()


def test_timeout_never_attempts_unlock_or_adds_misleading_cleanup_note(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path, handle = _tracking_handle(tmp_path, monkeypatch)
    release_calls = 0

    def reject_acquire(_handle: BinaryIO) -> None:
        raise OSError(errno.EACCES, "busy")

    def reject_release(_handle: BinaryIO) -> None:
        nonlocal release_calls
        release_calls += 1
        raise CleanupFault("must-not-release")

    monkeypatch.setattr(
        atomic_io,
        "_acquire_platform_lock",
        reject_acquire,
    )
    monkeypatch.setattr(
        atomic_io,
        "_release_platform_lock",
        reject_release,
    )

    try:
        with pytest.raises(LockTimeoutError) as caught:
            with ExclusiveFileLock(lock_path, timeout_seconds=0.0):
                pytest.fail("contended acquisition unexpectedly succeeded")

        assert handle.closed
        assert release_calls == 0
        assert getattr(caught.value, "__notes__", []) == []
    finally:
        handle.close()


def test_lock_body_base_exception_releases_and_instance_can_be_reused(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "publisher.lock"
    lock = ExclusiveFileLock(lock_path, timeout_seconds=0.5)

    with pytest.raises(InjectedBaseFault, match="body"):
        with lock:
            raise InjectedBaseFault("body")

    with lock:
        assert lock_path.exists()


def test_release_error_does_not_mask_body_base_exception_and_adds_note(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock = ExclusiveFileLock(
        tmp_path / "publisher.lock",
        timeout_seconds=0.5,
    )
    real_release = atomic_io._release_platform_lock
    monkeypatch.setattr(
        atomic_io,
        "_release_platform_lock",
        lambda _handle: (_ for _ in ()).throw(
            CleanupFault("secondary-release")
        ),
    )

    with pytest.raises(InjectedBaseFault, match="body") as caught:
        with lock:
            raise InjectedBaseFault("body")

    assert any(
        "secondary-release" in note
        for note in getattr(caught.value, "__notes__", [])
    )
    monkeypatch.setattr(atomic_io, "_release_platform_lock", real_release)
    with lock:
        assert lock.path.exists()


def test_release_error_propagates_when_lock_body_succeeds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock = ExclusiveFileLock(
        tmp_path / "publisher.lock",
        timeout_seconds=0.5,
    )
    real_release = atomic_io._release_platform_lock
    monkeypatch.setattr(
        atomic_io,
        "_release_platform_lock",
        lambda _handle: (_ for _ in ()).throw(
            CleanupFault("release-failed")
        ),
    )

    with pytest.raises(CleanupFault, match="release-failed"):
        with lock:
            pass

    monkeypatch.setattr(atomic_io, "_release_platform_lock", real_release)
    with lock:
        assert lock.path.exists()


def test_lock_handle_is_not_inheritable_by_descendant_processes(
    tmp_path: Path,
) -> None:
    with ExclusiveFileLock(
        tmp_path / "publisher.lock",
        timeout_seconds=0.5,
    ) as lock:
        assert lock._handle is not None
        assert os.get_inheritable(lock._handle.fileno()) is False


@pytest.mark.skipif(os.name != "nt", reason="Windows msvcrt adapter only")
def test_windows_adapter_locks_byte_zero_without_growing_empty_file(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "publisher.lock"
    with lock_path.open("a+b") as handle:
        handle.seek(99)
        atomic_io._acquire_platform_lock(handle)
        try:
            assert handle.tell() == 0
            assert os.fstat(handle.fileno()).st_size == 0
        finally:
            atomic_io._release_platform_lock(handle)

    assert lock_path.read_bytes() == b""
