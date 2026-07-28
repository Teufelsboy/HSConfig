from __future__ import annotations

import errno
import json
import os
import time
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, BinaryIO


FaultHook = Callable[[str], None]


class LockTimeoutError(TimeoutError):
    """Raised when an exclusive file lock cannot be acquired in time."""


def no_fault(stage: str) -> None:
    """Default fault hook that leaves the write uninterrupted."""


def atomic_write_bytes(
    path: Path,
    content: bytes,
    *,
    fault_hook: FaultHook = no_fault,
) -> None:
    """Durably replace *path* with complete bytes from a sibling temp file.

    A successful ``os.replace`` is the commit point: failures before it leave
    the old target in place, while failures after it may leave the new target
    committed. Parent-directory flushing is best effort because Windows does
    not expose a generally usable directory handle through ``os.open``.
    Replacement correctness does not depend on that optional durability step.
    """

    target = Path(path)
    temp_path: Path | None = None
    temp_handle: BinaryIO | None = None
    fault_hook("before_temp_write")
    try:
        temp_path, temp_handle = _open_unique_sibling_temp(target)
        with temp_handle:
            temp_handle.write(content)
            fault_hook("after_temp_write")
            temp_handle.flush()
            os.fsync(temp_handle.fileno())
            fault_hook("after_temp_flush")
        temp_handle = None

        fault_hook("before_replace")
        os.replace(temp_path, target)
        fault_hook("after_replace")

        _flush_parent_directory(target.parent)
        fault_hook("after_parent_flush")
    finally:
        if temp_handle is not None:
            temp_handle.close()
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def atomic_write_json(
    path: Path,
    payload: Mapping[str, Any],
    *,
    fault_hook: FaultHook = no_fault,
) -> None:
    content = (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    atomic_write_bytes(path, content, fault_hook=fault_hook)


def flush_file(path: Path) -> None:
    """Flush an existing file's kernel buffers to durable storage."""

    with Path(path).open("r+b") as handle:
        os.fsync(handle.fileno())


class ExclusiveFileLock:
    """Cross-process exclusive lock backed by a persistent empty lock inode."""

    def __init__(self, path: Path, *, timeout_seconds: float = 30.0) -> None:
        self.path = Path(path)
        self.timeout_seconds = timeout_seconds
        self._handle: BinaryIO | None = None

    def __enter__(self) -> ExclusiveFileLock:
        if self._handle is not None:
            raise RuntimeError(f"Lock is already acquired: {self.path}")

        handle = self.path.open("a+b")
        deadline = time.monotonic() + max(0.0, self.timeout_seconds)
        while True:
            try:
                _acquire_platform_lock(handle)
            except OSError as exc:
                if not _is_lock_contention(exc):
                    handle.close()
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    handle.close()
                    raise LockTimeoutError(
                        f"Timed out acquiring exclusive lock: {self.path}"
                    ) from exc
                time.sleep(min(0.05, remaining))
            else:
                self._handle = handle
                return self

    def __exit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        try:
            _release_platform_lock(handle)
        finally:
            handle.close()


def _open_unique_sibling_temp(target: Path) -> tuple[Path, BinaryIO]:
    for _ in range(100):
        candidate = target.with_name(
            f".{target.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            return candidate, candidate.open("xb")
        except FileExistsError:
            continue
    raise FileExistsError(f"Unable to create a unique temp file beside {target}")


def _flush_parent_directory(parent: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(parent, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _acquire_platform_lock(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release_platform_lock(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _is_lock_contention(exc: OSError) -> bool:
    return exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}
