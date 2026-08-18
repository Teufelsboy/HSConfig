from __future__ import annotations

import errno
import json
import math
import os
import stat
import time
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, BinaryIO

from hsconfig.package_io import (
    FilesystemPathGuard,
    secure_open_file_descriptor,
    secure_replace,
    secure_unlink,
)


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
    expected_parent_identity: tuple[int, int, int] | None = None,
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
    if (
        expected_parent_identity is not None
        and parent_identity != expected_parent_identity
    ):
        raise AtomicWriteConflictError(
            f"parent directory changed before atomic write: {parent}"
        )
    resolved_parent_identity = _stat_identity(parent)
    try:
        (
            temp_path,
            temp_handle,
            temp_identity,
            temp_cleanup_path,
        ) = _open_unique_sibling_temp(
            target,
            expected_parent_identity=parent_identity,
        )
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
        secure_replace(
            temp_path,
            target,
            expected_source_identity=temp_identity,
            expected_source_parent_identity=parent_identity,
            expected_target_parent_identity=parent_identity,
        )
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

    def __init__(
        self,
        path: Path,
        *,
        timeout_seconds: float = 30.0,
        expected_parent_identity: tuple[int, int, int] | None = None,
        path_guard: FilesystemPathGuard | None = None,
        create_if_missing: bool = True,
    ) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds < 0:
            raise ValueError("timeout_seconds must be finite and non-negative")
        self.path = Path(path)
        self.timeout_seconds = timeout_seconds
        self.expected_parent_identity = expected_parent_identity
        self.path_guard = path_guard
        self.create_if_missing = create_if_missing
        self._handle: BinaryIO | None = None

    def __enter__(self) -> ExclusiveFileLock:
        if self._handle is not None:
            raise RuntimeError(f"Lock is already acquired: {self.path}")

        parent = self.path.parent
        if self.path_guard is not None:
            self.path_guard.validate()
        parent_status = parent.lstat()
        parent_identity = _identity_from_status(parent_status)
        if (
            self.expected_parent_identity is not None
            and parent_identity != self.expected_parent_identity
        ):
            raise ValueError("filesystem_path_identity_changed")
        resolved_parent_identity = _stat_identity(parent)
        if _status_is_reparse(parent_status):
            raise ValueError(f"Lock parent is a reparse point: {parent}")
        if self.path_guard is not None:
            self.path_guard.validate()
        before_identity: tuple[int, int, int] | None = None
        handle: BinaryIO | None = None
        for _ in range(100):
            if self.path_guard is not None:
                self.path_guard.validate()
            try:
                before_status = self.path.lstat()
            except FileNotFoundError:
                if not self.create_if_missing:
                    raise
                try:
                    handle = _open_lock_file(
                        self.path,
                        create=True,
                        expected_parent_identity=parent_identity,
                    )
                except FileExistsError:
                    continue
                before_identity = None
                break
            before_identity = _identity_from_status(before_status)
            if (
                not stat.S_ISREG(before_identity[2])
                or _status_is_reparse(before_status)
            ):
                raise ValueError(f"Lock path is not a plain file: {self.path}")
            try:
                handle = _open_lock_file(
                    self.path,
                    create=False,
                    expected_parent_identity=parent_identity,
                )
            except FileNotFoundError:
                if not self.create_if_missing:
                    raise
                continue
            break
        if handle is None:
            raise AtomicWriteConflictError(
                f"Lock path did not stabilize while opening: {self.path}"
            )
        acquired = False
        try:
            opened_identity = _fstat_identity(handle)
            if self.path_guard is not None:
                self.path_guard.validate()
            path_status = self.path.lstat()
            path_identity = _identity_from_status(path_status)
            if (
                not stat.S_ISREG(opened_identity[2])
                or _status_is_reparse(path_status)
                or path_identity != opened_identity
                or (
                    before_identity is not None
                    and before_identity != opened_identity
                )
                or _lstat_identity(parent) != parent_identity
                or _stat_identity(parent) != resolved_parent_identity
            ):
                raise AtomicWriteConflictError(
                    f"Lock path identity changed while opening: {self.path}"
                )
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
                    if self.path_guard is not None:
                        self.path_guard.validate()
                    if (
                        _lstat_identity(self.path) != opened_identity
                        or _lstat_identity(parent) != parent_identity
                        or _stat_identity(parent)
                        != resolved_parent_identity
                    ):
                        raise AtomicWriteConflictError(
                            "Lock path identity changed after acquisition: "
                            f"{self.path}"
                        )
                    acquired = True
                    if self.path_guard is not None:
                        self.path_guard.validate()
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


def _open_lock_file(
    path: Path,
    *,
    create: bool,
    expected_parent_identity: tuple[int, int, int],
) -> BinaryIO:
    descriptor = secure_open_file_descriptor(
        path,
        create=create,
        write=True,
        expected_parent_identity=expected_parent_identity,
    )
    try:
        os.set_inheritable(descriptor, False)
        return os.fdopen(descriptor, "r+b")
    except BaseException:
        os.close(descriptor)
        raise


def _open_unique_sibling_temp(
    target: Path,
    *,
    expected_parent_identity: tuple[int, int, int],
) -> tuple[Path, BinaryIO, tuple[int, int, int], Path]:
    for _ in range(100):
        candidate = target.with_name(
            f".{target.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            descriptor = secure_open_file_descriptor(
                candidate,
                create=True,
                write=True,
                expected_parent_identity=expected_parent_identity,
            )
            handle = os.fdopen(descriptor, "w+b")
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


def _identity_from_status(
    status: os.stat_result,
) -> tuple[int, int, int]:
    return status.st_dev, status.st_ino, status.st_mode


def _status_is_reparse(status: os.stat_result) -> bool:
    return stat.S_ISLNK(status.st_mode) or bool(
        getattr(status, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


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
        secure_unlink(
            path,
            expected_identity=owned_identity,
            missing_ok=True,
        )
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
