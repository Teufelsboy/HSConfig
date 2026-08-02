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
import hsconfig.package_io as package_io
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
    real_open_lock_file = atomic_io._open_lock_file

    def return_tracking_handle(
        path: Path,
        *,
        create: bool,
        expected_parent_identity: tuple[int, int, int],
    ):
        if path == lock_path:
            return handle
        return real_open_lock_file(
            path,
            create=create,
            expected_parent_identity=expected_parent_identity,
        )

    monkeypatch.setattr(
        atomic_io,
        "_open_lock_file",
        return_tracking_handle,
    )
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


def test_windows_lock_inode_cannot_be_renamed_while_lock_is_held(
    tmp_path: Path,
) -> None:
    if os.name != "nt":
        pytest.skip("Windows lock-handle share-mode regression")
    lock_path = tmp_path / "publisher.lock"
    moved_path = tmp_path / "publisher.lock.moved"

    with ExclusiveFileLock(lock_path, timeout_seconds=0.5):
        with pytest.raises(PermissionError):
            lock_path.rename(moved_path)
        assert lock_path.is_file()
        assert not moved_path.exists()

    lock_path.rename(moved_path)
    assert moved_path.is_file()
    assert not lock_path.exists()


def test_lock_swap_to_dangling_symlink_never_creates_external_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = tmp_path / "publisher.lock"
    external_target = tmp_path / "external-target"
    symlink_probe = tmp_path / "symlink-probe"
    try:
        os.symlink(external_target, symlink_probe)
    except OSError:
        pytest.skip("file symlinks unavailable")
    symlink_probe.unlink()
    lock_path.write_bytes(b"")
    real_path_open = Path.open
    real_os_open = os.open
    real_child_open = package_io._open_windows_child_file_descriptor
    swapped = False

    def swap_lock_path() -> None:
        nonlocal swapped
        if swapped:
            return
        swapped = True
        lock_path.unlink()
        os.symlink(external_target, lock_path)

    def hostile_path_open(
        path: Path,
        *args: object,
        **kwargs: object,
    ):
        if path == lock_path:
            swap_lock_path()
        return real_path_open(path, *args, **kwargs)

    def hostile_os_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if Path(path) == lock_path:
            swap_lock_path()
        return real_os_open(path, flags, mode, dir_fd=dir_fd)

    def hostile_child_open(
        path: Path,
        *,
        create: bool,
        write: bool,
    ) -> int:
        if path == lock_path:
            swap_lock_path()
        return real_child_open(path, create=create, write=write)

    monkeypatch.setattr(Path, "open", hostile_path_open)
    monkeypatch.setattr(os, "open", hostile_os_open)
    monkeypatch.setattr(
        package_io,
        "_open_windows_child_file_descriptor",
        hostile_child_open,
    )

    with pytest.raises(
        (OSError, ValueError, atomic_io.AtomicWriteConflictError)
    ):
        with ExclusiveFileLock(lock_path, timeout_seconds=0.1):
            pytest.fail("swapped lock unexpectedly acquired")

    assert swapped
    assert not external_target.exists()


def test_lock_parent_swap_cannot_create_external_lock_node(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = tmp_path / "deck"
    parent.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    moved = tmp_path / "deck-owned-moved"
    lock_path = parent / ".publish.lock"
    original_open = os.open
    original_child_open = package_io._open_windows_child_file_descriptor
    swapped = False

    def swap_then_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        if not swapped and Path(path) == lock_path:
            swapped = True
            parent.rename(moved)
            os.symlink(external, parent, target_is_directory=True)
        return original_open(
            path,
            flags,
            mode,
            **({"dir_fd": dir_fd} if dir_fd is not None else {}),
        )

    def swap_then_child_open(
        path: Path,
        *,
        create: bool,
        write: bool,
    ) -> int:
        nonlocal swapped
        if not swapped and path == lock_path:
            swapped = True
            parent.rename(moved)
            os.symlink(external, parent, target_is_directory=True)
        return original_child_open(
            path,
            create=create,
            write=write,
        )

    monkeypatch.setattr(os, "open", swap_then_open)
    monkeypatch.setattr(
        package_io,
        "_open_windows_child_file_descriptor",
        swap_then_child_open,
    )

    with pytest.raises((OSError, ValueError)):
        with ExclusiveFileLock(lock_path):
            pytest.fail("parent-swapped lock unexpectedly acquired")

    assert swapped
    assert not (external / ".publish.lock").exists()


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


class _CountingPathGuard:
    def __init__(self, *, fail_at: int | None = None) -> None:
        self.calls = 0
        self.fail_at = fail_at

    def validate(self) -> None:
        self.calls += 1
        if self.calls == self.fail_at:
            raise InjectedBaseFault("guard")


def test_lock_rejects_reentry_and_exit_without_handle_is_a_noop(
    tmp_path: Path,
) -> None:
    lock = ExclusiveFileLock(tmp_path / "publisher.lock")
    lock.__exit__(None, None, None)
    with lock:
        with pytest.raises(RuntimeError, match="already acquired"):
            lock.__enter__()


def test_lock_validates_guard_through_acquisition(
    tmp_path: Path,
) -> None:
    guard = _CountingPathGuard()
    with ExclusiveFileLock(
        tmp_path / "publisher.lock",
        path_guard=guard,  # type: ignore[arg-type]
    ):
        pass

    assert guard.calls == 6


def test_lock_releases_when_final_guard_validation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard = _CountingPathGuard(fail_at=6)
    releases: list[BinaryIO] = []
    real_release = atomic_io._release_platform_lock
    monkeypatch.setattr(
        atomic_io,
        "_release_platform_lock",
        lambda handle: (releases.append(handle), real_release(handle))[1],
    )

    with pytest.raises(InjectedBaseFault, match="guard"):
        ExclusiveFileLock(
            tmp_path / "publisher.lock",
            path_guard=guard,  # type: ignore[arg-type]
        ).__enter__()

    assert len(releases) == 1


def test_lock_rejects_expected_parent_identity_mismatch(tmp_path: Path) -> None:
    identity = atomic_io._lstat_identity(tmp_path)
    changed = (identity[0], identity[1] + 1, identity[2])

    with pytest.raises(ValueError, match="filesystem_path_identity_changed"):
        ExclusiveFileLock(
            tmp_path / "publisher.lock",
            expected_parent_identity=changed,
        ).__enter__()


def test_lock_rejects_reparse_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(atomic_io, "_status_is_reparse", lambda _status: True)

    with pytest.raises(ValueError, match="parent is a reparse point"):
        ExclusiveFileLock(tmp_path / "publisher.lock").__enter__()


def test_lock_does_not_create_missing_path_when_disabled(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ExclusiveFileLock(
            tmp_path / "missing.lock",
            create_if_missing=False,
        ).__enter__()


def test_lock_retries_create_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_open = atomic_io._open_lock_file
    calls = 0

    def collide_once(*args: object, **kwargs: object) -> BinaryIO:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise FileExistsError()
        return real_open(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(atomic_io, "_open_lock_file", collide_once)

    with ExclusiveFileLock(tmp_path / "publisher.lock"):
        pass

    assert calls == 2


def test_lock_retries_existing_path_that_disappears_while_opening(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = tmp_path / "publisher.lock"
    lock_path.touch()
    real_open = atomic_io._open_lock_file
    calls = 0

    def disappear_once(*args: object, **kwargs: object) -> BinaryIO:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise FileNotFoundError()
        return real_open(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(atomic_io, "_open_lock_file", disappear_once)

    with ExclusiveFileLock(lock_path):
        pass

    assert calls == 2


def test_lock_exhausts_unstable_open_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = tmp_path / "publisher.lock"
    lock_path.touch()
    monkeypatch.setattr(
        atomic_io,
        "_open_lock_file",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )

    with pytest.raises(
        atomic_io.AtomicWriteConflictError,
        match="did not stabilize",
    ):
        ExclusiveFileLock(lock_path).__enter__()


def test_lock_rejects_non_plain_existing_path(tmp_path: Path) -> None:
    lock_path = tmp_path / "publisher.lock"
    lock_path.mkdir()

    with pytest.raises(ValueError, match="not a plain file"):
        ExclusiveFileLock(lock_path).__enter__()


def test_lock_rejects_identity_change_while_opening(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = tmp_path / "publisher.lock"
    lock_path.touch()
    real_fstat = atomic_io._fstat_identity
    monkeypatch.setattr(
        atomic_io,
        "_fstat_identity",
        lambda handle: (
            lambda identity: (identity[0], identity[1] + 1, identity[2])
        )(real_fstat(handle)),
    )

    with pytest.raises(
        atomic_io.AtomicWriteConflictError,
        match="changed while opening",
    ):
        ExclusiveFileLock(lock_path).__enter__()


def test_lock_rejects_identity_change_after_acquisition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = tmp_path / "publisher.lock"
    real_lstat = atomic_io._lstat_identity
    def changed_after_acquire(path: Path) -> tuple[int, int, int]:
        identity = real_lstat(path)
        if path == lock_path:
            return (identity[0], identity[1] + 1, identity[2])
        return identity

    monkeypatch.setattr(atomic_io, "_lstat_identity", changed_after_acquire)

    with pytest.raises(
        atomic_io.AtomicWriteConflictError,
        match="changed after acquisition",
    ):
        ExclusiveFileLock(lock_path).__enter__()


class _ExitHandle:
    def __init__(self, *, close_error: BaseException | None = None) -> None:
        self.close_error = close_error

    def close(self) -> None:
        if self.close_error is not None:
            raise self.close_error


@pytest.mark.parametrize(
    ("body_error", "release_error", "expected_error", "note_fragment"),
    (
        (InjectedBaseFault("body"), None, InjectedBaseFault, "handle close"),
        (None, CleanupFault("release"), CleanupFault, "handle close"),
        (None, None, CleanupFault, None),
    ),
)
def test_lock_exit_routes_close_failure_without_masking_primary_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    body_error: BaseException | None,
    release_error: BaseException | None,
    expected_error: type[BaseException],
    note_fragment: str | None,
) -> None:
    lock = ExclusiveFileLock(tmp_path / "publisher.lock")
    handle = _ExitHandle(close_error=CleanupFault("close"))
    lock._handle = handle  # type: ignore[assignment]
    if release_error is not None:
        monkeypatch.setattr(
            atomic_io,
            "_release_platform_lock",
            lambda _handle: (_ for _ in ()).throw(release_error),
        )
    else:
        monkeypatch.setattr(atomic_io, "_release_platform_lock", lambda _handle: None)

    if body_error is not None:
        lock.__exit__(type(body_error), body_error, None)
        caught = body_error
    else:
        with pytest.raises(expected_error) as result:
            lock.__exit__(None, None, None)
        caught = result.value

    if note_fragment is not None:
        assert any(
            note_fragment in note
            for note in getattr(caught, "__notes__", [])
        )


def test_posix_lock_adapter_uses_flock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int]] = []

    class FakeFcntl:
        LOCK_EX = 1
        LOCK_NB = 2
        LOCK_UN = 4

        @staticmethod
        def flock(descriptor: int, operation: int) -> None:
            calls.append((descriptor, operation))

    monkeypatch.setattr(atomic_io.os, "name", "posix")
    monkeypatch.setitem(sys.modules, "fcntl", FakeFcntl())
    with (tmp_path / "lock").open("a+b") as handle:
        atomic_io._acquire_platform_lock(handle)
        atomic_io._release_platform_lock(handle)
        descriptor = handle.fileno()

    assert calls == [(descriptor, 3), (descriptor, 4)]


def test_lock_propagates_disappearance_when_creation_is_disabled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock_path = tmp_path / "publisher.lock"
    lock_path.touch()
    monkeypatch.setattr(
        atomic_io,
        "_open_lock_file",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )

    with pytest.raises(FileNotFoundError):
        ExclusiveFileLock(
            lock_path,
            create_if_missing=False,
        ).__enter__()
