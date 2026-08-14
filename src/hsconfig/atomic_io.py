from __future__ import annotations

import errno
import json
import math
import os
import time
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, BinaryIO


FaultHook = Callable[[str], None]


class LockTimeoutError(TimeoutError):
    """Raised when an exclusive file lock cannot be acquired in time."""


class AtomicWriteConflictError(RuntimeError):
    """Raised when a path identity changes during an atomic write."""


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
    the old target in place, while failures after it leave the complete new
    target committed. Parent-directory flushing is best effort because Windows
    does not expose a generally usable directory handle through ``os.open``.
    Replacement correctness does not depend on that optional durability step.
    """

    target = Path(path)
    parent = target.parent
    temp_path: Path | None = None
    temp_cleanup_path: Path | None = None
    temp_handle: BinaryIO | None = None
    temp_identity: tuple[int, int, int] | None = None
    fault_hook("before_temp_write")
    parent_identity = _lstat_identity(parent)
    resolved_parent_identity = _stat_identity(parent)
    try:
        (
            temp_path,
            temp_handle,
            temp_identity,
            temp_cleanup_path,
        ) = _open_unique_sibling_temp(target)
        temp_handle.write(content)
        fault_hook("after_temp_write")
        temp_handle.flush()
        os.fsync(temp_handle.fileno())
        fault_hook("after_temp_flush")
        temp_handle.close()
        temp_handle = None

        fault_hook("before_replace")
        if _lstat_identity(parent) != parent_identity:
            raise AtomicWriteConflictError(
                f"parent directory changed before replace: {parent}"
            )
        if _stat_identity(parent) != resolved_parent_identity:
            raise AtomicWriteConflictError(
                f"resolved parent changed before replace: {parent}"
            )
        if _lstat_identity(temp_path) != temp_identity:
            raise AtomicWriteConflictError(
                f"owned temp identity changed before replace: {temp_path}"
            )
        os.replace(temp_path, target)
        temp_path = None
        temp_cleanup_path = None
        temp_identity = None
        fault_hook("after_replace")

        _flush_parent_directory(parent)
        fault_hook("after_parent_flush")
    except BaseException as primary:
        if temp_handle is not None:
            _close_without_masking(temp_handle, primary)
        if temp_path is not None and temp_identity is not None:
            if (
                temp_cleanup_path is not None
                and temp_cleanup_path != temp_path.absolute()
            ):
                _unlink_owned_temp_without_masking(
                    temp_cleanup_path,
                    temp_identity,
                    primary,
                )
            _unlink_owned_temp_without_masking(
                temp_path,
                temp_identity,
                primary,
            )
        raise


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
        if not math.isfinite(timeout_seconds) or timeout_seconds < 0:
            raise ValueError("timeout_seconds must be finite and non-negative")
        self.path = Path(path)
        self.timeout_seconds = timeout_seconds
        self._handle: BinaryIO | None = None

    def __enter__(self) -> ExclusiveFileLock:
        if self._handle is not None:
            raise RuntimeError(f"Lock is already acquired: {self.path}")

        handle = self.path.open("a+b")
        acquired = False
        try:
            os.set_inheritable(handle.fileno(), False)
            deadline = time.monotonic() + self.timeout_seconds
            while True:
                try:
                    _acquire_platform_lock(handle)
                except OSError as exc:
                    if not _is_lock_contention(exc):
                        raise
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise LockTimeoutError(
                            f"Timed out acquiring exclusive lock: {self.path}"
                        ) from exc
                    time.sleep(min(0.05, remaining))
                else:
                    acquired = True
                    self._handle = handle
                    return self
        except BaseException as primary:
            if acquired:
                _release_lock_without_masking(handle, primary)
            _close_without_masking(handle, primary)
            raise

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
        primary = exc if isinstance(exc, BaseException) else None
        release_error: BaseException | None = None
        try:
            _release_platform_lock(handle)
        except BaseException as error:
            if primary is not None:
                _add_cleanup_note(
                    primary,
                    "exclusive lock release failed",
                    error,
                )
            else:
                release_error = error
        finally:
            try:
                handle.close()
            except BaseException as close_error:
                if primary is not None:
                    _add_cleanup_note(
                        primary,
                        "exclusive lock handle close failed",
                        close_error,
                    )
                elif release_error is not None:
                    _add_cleanup_note(
                        release_error,
                        "exclusive lock handle close failed",
                        close_error,
                    )
                else:
                    raise
        if release_error is not None:
            raise release_error


def _open_unique_sibling_temp(
    target: Path,
) -> tuple[Path, BinaryIO, tuple[int, int, int], Path]:
    for _ in range(100):
        candidate = target.with_name(
            f".{target.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            handle = candidate.open("xb")
        except FileExistsError:
            continue
        initial_identity: tuple[int, int, int] | None = None
        cleanup_identity: tuple[int, int, int] | None = None
        cleanup_path: Path | None = None
        try:
            initial_identity = _lstat_identity(candidate)
            cleanup_identity = initial_identity
            owned_identity = _fstat_identity(handle)
            cleanup_identity = owned_identity
            if initial_identity != owned_identity:
                raise AtomicWriteConflictError(
                    f"owned temp identity changed after creation: {candidate}"
                )
            cleanup_path = candidate.resolve(strict=True)
            if _lstat_identity(cleanup_path) != owned_identity:
                raise AtomicWriteConflictError(
                    "resolved owned temp identity changed after creation: "
                    f"{candidate}"
                )
            return candidate, handle, owned_identity, cleanup_path
        except BaseException as primary:
            if cleanup_identity is None:
                try:
                    cleanup_identity = _fstat_identity(handle)
                except BaseException as cleanup_error:
                    _add_cleanup_note(
                        primary,
                        "owned temp identity recovery failed",
                        cleanup_error,
                    )
            _close_without_masking(handle, primary)
            if cleanup_identity is not None:
                if (
                    cleanup_path is not None
                    and cleanup_path != candidate.absolute()
                ):
                    _unlink_owned_temp_without_masking(
                        cleanup_path,
                        cleanup_identity,
                        primary,
                    )
                _unlink_owned_temp_without_masking(
                    candidate,
                    cleanup_identity,
                    primary,
                )
            raise
    raise FileExistsError(f"Unable to create a unique temp file beside {target}")


def _fstat_identity(handle: BinaryIO) -> tuple[int, int, int]:
    status = os.fstat(handle.fileno())
    return status.st_dev, status.st_ino, status.st_mode


def _lstat_identity(path: Path) -> tuple[int, int, int]:
    status = Path(path).lstat()
    return status.st_dev, status.st_ino, status.st_mode


def _stat_identity(path: Path) -> tuple[int, int, int]:
    status = Path(path).stat()
    return status.st_dev, status.st_ino, status.st_mode


def _add_cleanup_note(
    primary: BaseException,
    operation: str,
    cleanup_error: BaseException,
) -> None:
    try:
        message = (
            f"{operation}: {type(cleanup_error).__name__}: {cleanup_error}"
        )
    except BaseException:
        message = f"{operation}: cleanup failure detail unavailable"
    try:
        primary.add_note(message)
    except BaseException:
        pass


def _close_without_masking(
    handle: BinaryIO,
    primary: BaseException,
) -> None:
    try:
        handle.close()
    except BaseException as cleanup_error:
        _add_cleanup_note(primary, "file handle cleanup failed", cleanup_error)


def _release_lock_without_masking(
    handle: BinaryIO,
    primary: BaseException,
) -> None:
    try:
        _release_platform_lock(handle)
    except BaseException as cleanup_error:
        _add_cleanup_note(
            primary,
            "exclusive lock acquisition cleanup release failed",
            cleanup_error,
        )


def _unlink_owned_temp_without_masking(
    path: Path,
    owned_identity: tuple[int, int, int],
    primary: BaseException,
) -> None:
    try:
        current_identity = _lstat_identity(path)
    except FileNotFoundError:
        return
    except BaseException as cleanup_error:
        _add_cleanup_note(
            primary,
            "owned temp identity cleanup check failed",
            cleanup_error,
        )
        return
    if current_identity != owned_identity:
        return
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except BaseException as cleanup_error:
        _add_cleanup_note(primary, "owned temp cleanup failed", cleanup_error)


def _flush_parent_directory(parent: Path) -> None:
    """Best-effort directory durability after the replacement commit.

    Lexical and resolved parent identities are revalidated immediately before
    ``os.replace``. A tiny race remains after those checks, especially for
    Windows reparse points, because the standard library has no portable
    directory-relative replacement primitive.
    """

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
        try:
            os.close(descriptor)
        except OSError:
            pass


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
