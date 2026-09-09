from __future__ import annotations

import errno
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import os
import stat
import time
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, BinaryIO, Literal

from hsconfig.package_io import (
    FilesystemPathGuard,
    PathIdentity,
    path_identity,
    path_identity_from_status,
    require_no_alternate_data_streams,
    require_open_file_descriptor_no_alternate_data_streams,
    secure_commit_sibling_no_replace,
    secure_open_file_descriptor,
    secure_replace,
    secure_unlink,
)


FaultHook = Callable[[str], None]
AtomicWriteFaultPoint = Literal[
    "temp_created",
    "temp_partial",
    "temp_full",
    "temp_flushed",
    "before_replace",
    "after_replace",
]
AtomicWriteFaultHook = Callable[[AtomicWriteFaultPoint], None]

STAGING_MATERIALIZE_FAULT_POINT = "after_staging_flush_before_identity_return"
NO_REPLACE_COMMIT_FAULT_POINT = "after_bound_staging_commit_before_return"
NO_REPLACE_POSIX_LINK_FAULT_POINT = (
    "after_bound_staging_posix_link_before_unlink"
)


@dataclass(frozen=True, slots=True)
class AtomicPublishedBytes:
    path: Path
    identity: PathIdentity
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class PublishedNoReplaceBytes:
    path: Path
    identity: PathIdentity
    size: int
    sha256: str


@dataclass(frozen=True, slots=True)
class MaterializedStagingBytes:
    path: Path
    identity: PathIdentity
    size: int
    sha256: str


class LockTimeoutError(TimeoutError):
    """Raised when an exclusive file lock cannot be acquired in time."""


class AtomicWriteConflictError(RuntimeError):
    """Raised when a path identity changes during an atomic write."""


def no_fault(stage: str) -> None:
    """Default fault hook that leaves the write uninterrupted."""


def no_atomic_write_fault(_point: AtomicWriteFaultPoint) -> None:
    """Default reserved-write fault hook."""


def atomic_materialize_staging_bytes(
    *,
    staging_path: Path,
    inner_temp_path: Path,
    payload: bytes,
    expected_parent_identity: PathIdentity,
    maximum_size: int,
    fault_hook: FaultHook = no_fault,
    inner_temp_fault_hook: FaultHook = no_fault,
) -> MaterializedStagingBytes:
    """Flush exact bytes to staging; keep inner faults off the legacy channel."""

    staging = Path(staging_path)
    inner = Path(inner_temp_path)
    content = _bounded_payload(payload, maximum_size=maximum_size)
    _require_reserved_staging_paths(staging=staging, inner=inner)
    if path_identity(staging.parent) != expected_parent_identity:
        raise AtomicWriteConflictError("parent directory changed before staging")
    if os.path.lexists(staging) or os.path.lexists(inner):
        raise AtomicWriteConflictError("reserved staging surface already exists")

    inner_identity: PathIdentity | None = None
    staging_bound = False
    try:
        descriptor = secure_open_file_descriptor(
            inner,
            create=True,
            write=True,
            expected_parent_identity=expected_parent_identity,
        )
        try:
            inner_identity = path_identity_from_status(os.fstat(descriptor))
            inner_temp_fault_hook("inner_temp_created")
            with os.fdopen(descriptor, "w+b", closefd=False) as handle:
                split = len(content) // 2
                if split and handle.write(content[:split]) != split:
                    raise OSError(errno.EIO, "atomic staging short write")
                inner_temp_fault_hook("inner_temp_partial")
                tail = content[split:]
                if tail and handle.write(tail) != len(tail):
                    raise OSError(errno.EIO, "atomic staging short write")
                inner_temp_fault_hook("inner_temp_full")
                handle.flush()
                os.fsync(descriptor)
                inner_temp_fault_hook("inner_temp_flushed")
            if path_identity_from_status(os.fstat(descriptor)) != inner_identity:
                raise AtomicWriteConflictError(
                    "owned staging inner identity changed"
                )
        finally:
            os.close(descriptor)

        secure_commit_sibling_no_replace(
            source_path=inner,
            target_path=staging,
            expected_source_identity=inner_identity,
            expected_parent_identity=expected_parent_identity,
        )
        identity, size, digest = _require_exact_bound_file(
            staging,
            expected_identity=inner_identity,
            expected_size=len(content),
            expected_sha256=_prefixed_sha256(content),
            expected_parent_identity=expected_parent_identity,
            allowed_links=frozenset({1}),
            maximum_size=maximum_size,
        )
        staging_bound = True
        fault_hook(STAGING_MATERIALIZE_FAULT_POINT)
        return MaterializedStagingBytes(
            path=staging,
            identity=identity,
            size=size,
            sha256=digest,
        )
    except BaseException as primary:
        if inner_identity is not None and not staging_bound:
            _cleanup_failed_staging_materialization(
                staging=staging,
                inner=inner,
                owned_identity=inner_identity,
                expected_parent_identity=expected_parent_identity,
                primary=primary,
            )
        raise


def _cleanup_failed_staging_materialization(
    *,
    staging: Path,
    inner: Path,
    owned_identity: PathIdentity,
    expected_parent_identity: PathIdentity,
    primary: BaseException,
) -> None:
    """Retire only the exact unbound identity created by this call."""

    try:
        secure_commit_sibling_no_replace(
            source_path=inner,
            target_path=staging,
            expected_source_identity=owned_identity,
            expected_parent_identity=expected_parent_identity,
        )
    except FileNotFoundError:
        pass
    except BaseException as cleanup_error:
        _add_cleanup_note(
            primary,
            "owned staging convergence failed",
            cleanup_error,
        )

    for path in (staging, inner):
        try:
            secure_unlink(
                path,
                expected_identity=owned_identity,
                expected_parent_identity=expected_parent_identity,
                missing_ok=True,
            )
        except FileNotFoundError:
            pass
        except BaseException as cleanup_error:
            _add_cleanup_note(
                primary,
                "owned staging cleanup failed",
                cleanup_error,
            )


def atomic_commit_bound_staging_no_replace(
    *,
    path: Path,
    staging_path: Path,
    expected_staging_identity: PathIdentity,
    expected_size: int,
    expected_sha256: str,
    expected_parent_identity: PathIdentity,
    fault_hook: FaultHook = no_fault,
) -> PublishedNoReplaceBytes:
    """Publish only one previously persisted staging identity."""

    target = Path(path)
    staging = Path(staging_path)
    if target.parent != staging.parent or target.name == staging.name:
        raise ValueError("atomic_no_replace_paths_invalid")
    if type(expected_size) is not int or expected_size < 0:
        raise ValueError("atomic_no_replace_size_invalid")
    _require_prefixed_sha256(expected_sha256)

    def adapt_fault(point: str) -> None:
        if point != "after_posix_link_before_source_unlink":
            raise AtomicWriteConflictError("unknown no-replace fault point")
        fault_hook(NO_REPLACE_POSIX_LINK_FAULT_POINT)

    try:
        _require_exact_bound_file(
            staging,
            expected_identity=expected_staging_identity,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            expected_parent_identity=expected_parent_identity,
            allowed_links=frozenset({1, 2}) if os.name != "nt" else frozenset({1}),
            maximum_size=max(expected_size, 1),
        )
    except FileNotFoundError:
        # Exact final-only resume is verified after the neutral commit helper.
        pass
    try:
        committed_identity = secure_commit_sibling_no_replace(
            source_path=staging,
            target_path=target,
            expected_source_identity=expected_staging_identity,
            expected_parent_identity=expected_parent_identity,
            fault_hook=adapt_fault,
        )
    except (OSError, ValueError, FileExistsError, FileNotFoundError) as error:
        raise AtomicWriteConflictError("bound no-replace commit conflict") from error
    identity, size, digest = _require_exact_bound_file(
        target,
        expected_identity=committed_identity,
        expected_size=expected_size,
        expected_sha256=expected_sha256,
        expected_parent_identity=expected_parent_identity,
        allowed_links=frozenset({1}),
        maximum_size=max(expected_size, 1),
    )
    if os.path.lexists(staging):
        raise AtomicWriteConflictError("bound staging was not retired")
    fault_hook(NO_REPLACE_COMMIT_FAULT_POINT)
    return PublishedNoReplaceBytes(target, identity, size, digest)


def atomic_commit_bound_staging_replace(
    *,
    path: Path,
    staging_path: Path,
    expected_predecessor_identity: PathIdentity,
    expected_staging_identity: PathIdentity,
    expected_size: int,
    expected_sha256: str,
    expected_parent_identity: PathIdentity,
    fault_hook: FaultHook = no_fault,
) -> PublishedNoReplaceBytes:
    """Replace one exact predecessor with one already-bound staging file."""

    target = Path(path)
    staging = Path(staging_path)
    if target.parent != staging.parent or target == staging:
        raise ValueError("atomic_bound_replace_paths_invalid")
    if type(expected_size) is not int or expected_size < 0:
        raise ValueError("atomic_bound_replace_size_invalid")
    _require_prefixed_sha256(expected_sha256)
    if path_identity(target.parent) != expected_parent_identity:
        raise AtomicWriteConflictError("bound replace parent changed")
    try:
        if path_identity(target) != expected_predecessor_identity:
            raise AtomicWriteConflictError(
                "bound replace predecessor changed"
            )
        _require_exact_bound_file(
            staging,
            expected_identity=expected_staging_identity,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
            expected_parent_identity=expected_parent_identity,
            allowed_links=frozenset({1}),
            maximum_size=max(expected_size, 1),
        )
        secure_replace(
            staging,
            target,
            expected_source_identity=expected_staging_identity,
            expected_source_parent_identity=expected_parent_identity,
            expected_target_parent_identity=expected_parent_identity,
            expected_target_identity=expected_predecessor_identity,
            expected_target_absent=False,
        )
    except (AtomicWriteConflictError, FileNotFoundError, ValueError) as error:
        # A hard exit after replacement resumes from exact final-only state.
        try:
            _require_exact_bound_file(
                target,
                expected_identity=expected_staging_identity,
                expected_size=expected_size,
                expected_sha256=expected_sha256,
                expected_parent_identity=expected_parent_identity,
                allowed_links=frozenset({1}),
                maximum_size=max(expected_size, 1),
            )
        except (
            AtomicWriteConflictError,
            FileNotFoundError,
            ValueError,
        ) as final_error:
            raise AtomicWriteConflictError(
                "bound replace commit conflict"
            ) from final_error
        if os.path.lexists(staging):
            raise AtomicWriteConflictError(
                "bound replace staging was not retired"
            ) from error
    identity, size, digest = _require_exact_bound_file(
        target,
        expected_identity=expected_staging_identity,
        expected_size=expected_size,
        expected_sha256=expected_sha256,
        expected_parent_identity=expected_parent_identity,
        allowed_links=frozenset({1}),
        maximum_size=max(expected_size, 1),
    )
    _flush_parent_directory(target.parent)
    fault_hook(NO_REPLACE_COMMIT_FAULT_POINT)
    return PublishedNoReplaceBytes(target, identity, size, digest)


def atomic_publish_bytes_no_replace(
    *,
    path: Path,
    staging_path: Path,
    payload: bytes,
    expected_parent_identity: PathIdentity,
    maximum_size: int,
    fault_hook: FaultHook = no_fault,
) -> PublishedNoReplaceBytes:
    """Legacy composition of staged materialization and no-replace commit."""

    staging = Path(staging_path)
    materialized = atomic_materialize_staging_bytes(
        staging_path=staging,
        inner_temp_path=staging.with_name(
            f".{staging.name}.live-start-atomic.tmp"
        ),
        payload=payload,
        expected_parent_identity=expected_parent_identity,
        maximum_size=maximum_size,
        fault_hook=fault_hook,
    )
    try:
        return atomic_commit_bound_staging_no_replace(
            path=path,
            staging_path=staging,
            expected_staging_identity=materialized.identity,
            expected_size=materialized.size,
            expected_sha256=materialized.sha256,
            expected_parent_identity=expected_parent_identity,
            fault_hook=fault_hook,
        )
    except AtomicWriteConflictError:
        try:
            secure_unlink(
                staging,
                expected_identity=materialized.identity,
                expected_parent_identity=expected_parent_identity,
                missing_ok=True,
            )
        except (FileNotFoundError, ValueError):
            pass
        raise


def atomic_write_reserved_bytes(
    *,
    path: Path,
    payload: bytes,
    expected_parent_identity: PathIdentity,
    expected_predecessor_identity: PathIdentity | None,
    expected_predecessor_sha256: str | None,
    maximum_size: int,
    fault_hook: AtomicWriteFaultHook = no_atomic_write_fault,
) -> AtomicPublishedBytes:
    """CAS one special leaf through its deterministic reserved sibling."""

    target = Path(path)
    content = _bounded_payload(payload, maximum_size=maximum_size)
    if (expected_predecessor_identity is None) != (
        expected_predecessor_sha256 is None
    ):
        raise ValueError("atomic_reserved_predecessor_binding_invalid")
    if expected_predecessor_sha256 is not None:
        _require_prefixed_sha256(expected_predecessor_sha256)
    if path_identity(target.parent) != expected_parent_identity:
        raise AtomicWriteConflictError("parent directory changed before reserved write")
    _require_reserved_predecessor(
        target,
        expected_identity=expected_predecessor_identity,
        expected_sha256=expected_predecessor_sha256,
        expected_parent_identity=expected_parent_identity,
        maximum_size=maximum_size,
    )
    temp = target.with_name(f".{target.name}.live-start-atomic.tmp")
    if os.path.lexists(temp):
        raise AtomicWriteConflictError("reserved atomic temp already exists")
    descriptor = secure_open_file_descriptor(
        temp,
        create=True,
        write=True,
        expected_parent_identity=expected_parent_identity,
    )
    try:
        temp_identity = path_identity_from_status(os.fstat(descriptor))
        fault_hook("temp_created")
        split = len(content) // 2
        if split:
            if os.write(descriptor, content[:split]) != split:
                raise OSError(errno.EIO, "atomic reserved short write")
        fault_hook("temp_partial")
        tail = content[split:]
        if tail and os.write(descriptor, tail) != len(tail):
            raise OSError(errno.EIO, "atomic reserved short write")
        fault_hook("temp_full")
        os.fsync(descriptor)
        fault_hook("temp_flushed")
    finally:
        os.close(descriptor)
    _require_exact_bound_file(
        temp,
        expected_identity=temp_identity,
        expected_size=len(content),
        expected_sha256=_prefixed_sha256(content),
        expected_parent_identity=expected_parent_identity,
        allowed_links=frozenset({1}),
        maximum_size=maximum_size,
    )
    _require_reserved_predecessor(
        target,
        expected_identity=expected_predecessor_identity,
        expected_sha256=expected_predecessor_sha256,
        expected_parent_identity=expected_parent_identity,
        maximum_size=maximum_size,
    )
    fault_hook("before_replace")
    _require_reserved_predecessor(
        target,
        expected_identity=expected_predecessor_identity,
        expected_sha256=expected_predecessor_sha256,
        expected_parent_identity=expected_parent_identity,
        maximum_size=maximum_size,
    )
    try:
        secure_replace(
            temp,
            target,
            expected_source_identity=temp_identity,
            expected_source_parent_identity=expected_parent_identity,
            expected_target_parent_identity=expected_parent_identity,
            expected_target_identity=expected_predecessor_identity,
            expected_target_absent=expected_predecessor_identity is None,
        )
    except (ValueError, FileExistsError, FileNotFoundError) as error:
        raise AtomicWriteConflictError("reserved atomic CAS conflict") from error
    fault_hook("after_replace")
    identity, size, digest = _require_exact_bound_file(
        target,
        expected_identity=temp_identity,
        expected_size=len(content),
        expected_sha256=_prefixed_sha256(content),
        expected_parent_identity=expected_parent_identity,
        allowed_links=frozenset({1}),
        maximum_size=maximum_size,
    )
    _flush_parent_directory(target.parent)
    return AtomicPublishedBytes(target, identity, size, digest)


def _bounded_payload(payload: bytes, *, maximum_size: int) -> bytes:
    if type(maximum_size) is not int or maximum_size < 1:
        raise ValueError("atomic_maximum_size_invalid")
    if not isinstance(payload, bytes) or len(payload) > maximum_size:
        raise ValueError("atomic_payload_invalid")
    return bytes(payload)


def _require_reserved_staging_paths(*, staging: Path, inner: Path) -> None:
    expected = staging.with_name(f".{staging.name}.live-start-atomic.tmp")
    if (
        staging.parent != inner.parent
        or inner != expected
        or staging.name in {"", ".", ".."}
    ):
        raise ValueError("atomic_staging_paths_invalid")


def _require_prefixed_sha256(value: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError("atomic_sha256_invalid")


def _prefixed_sha256(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"


def _require_reserved_predecessor(
    path: Path,
    *,
    expected_identity: PathIdentity | None,
    expected_sha256: str | None,
    expected_parent_identity: PathIdentity,
    maximum_size: int,
) -> None:
    if path_identity(path.parent) != expected_parent_identity:
        raise AtomicWriteConflictError("reserved predecessor parent changed")
    if expected_identity is None:
        if os.path.lexists(path):
            raise AtomicWriteConflictError("reserved target unexpectedly exists")
        return
    try:
        _require_exact_bound_file(
            path,
            expected_identity=expected_identity,
            expected_size=None,
            expected_sha256=expected_sha256,
            expected_parent_identity=expected_parent_identity,
            allowed_links=frozenset({1}),
            maximum_size=maximum_size,
        )
    except (AtomicWriteConflictError, FileNotFoundError) as error:
        raise AtomicWriteConflictError(
            "reserved predecessor changed"
        ) from error


def _require_exact_bound_file(
    path: Path,
    *,
    expected_identity: PathIdentity,
    expected_size: int | None,
    expected_sha256: str | None,
    expected_parent_identity: PathIdentity,
    allowed_links: frozenset[int],
    maximum_size: int,
) -> tuple[PathIdentity, int, str]:
    if path_identity(path.parent) != expected_parent_identity:
        raise AtomicWriteConflictError("bound file parent changed")
    status = Path(path).lstat()
    identity = path_identity_from_status(status)
    if (
        identity != expected_identity
        or not stat.S_ISREG(status.st_mode)
        or status.st_nlink not in allowed_links
        or status.st_size > maximum_size
    ):
        raise AtomicWriteConflictError("bound file identity changed")
    if os.name == "nt":
        require_no_alternate_data_streams(
            path,
            expected_identity=identity,
            expected_parent_identity=expected_parent_identity,
            directory=False,
            expected_size=status.st_size,
        )
    descriptor = secure_open_file_descriptor(
        path,
        create=False,
        write=False,
        expected_parent_identity=expected_parent_identity,
    )
    try:
        opened = os.fstat(descriptor)
        if (
            path_identity_from_status(opened) != identity
            or opened.st_nlink not in allowed_links
            or opened.st_size != status.st_size
        ):
            raise AtomicWriteConflictError("bound file changed while opening")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            content = handle.read(maximum_size + 1)
        after = os.fstat(descriptor)
        if (
            path_identity_from_status(after) != identity
            or after.st_size != len(content)
            or after.st_nlink not in allowed_links
        ):
            raise AtomicWriteConflictError("bound file changed while reading")
    finally:
        os.close(descriptor)
    size = len(content)
    digest = _prefixed_sha256(content)
    if expected_size is not None and size != expected_size:
        raise AtomicWriteConflictError("bound file size changed")
    if expected_sha256 is not None and digest != expected_sha256:
        raise AtomicWriteConflictError("bound file digest changed")
    return identity, size, digest


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
        self._created_file = False

    @property
    def created_file(self) -> bool:
        """Whether this active acquisition created the persistent lock file."""

        if self._handle is None:
            raise RuntimeError(f"Lock is not acquired: {self.path}")
        return self._created_file

    def __enter__(self) -> ExclusiveFileLock:
        if self._handle is not None:
            raise RuntimeError(f"Lock is already acquired: {self.path}")
        self._created_file = False

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
                    self._created_file = before_identity is None
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
        self._created_file = False
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

    def validate_no_alternate_data_streams(
        self,
        *,
        expected_size: int = 0,
    ) -> None:
        handle = self._handle
        if handle is None:
            raise RuntimeError(f"Lock is not acquired: {self.path}")
        require_open_file_descriptor_no_alternate_data_streams(
            handle.fileno(),
            expected_size=expected_size,
        )


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
