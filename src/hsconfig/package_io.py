"""Filesystem helpers for HSConfig's cooperative publication contract.

All publishers must serialize through the shared publication lock. The
portable guarantees cover cooperative publishers plus crash/fault recovery.
On Windows, final child mutations are additionally bound to open handles. On
POSIX, ``dir_fd`` operations bind containment and parent directories, but
hostile same-user substitution of a final directory entry between validation
and mutation is outside the contract.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, get_ident
from types import MappingProxyType
from typing import Any, Callable, Iterator, Literal

from hsconfig.io import read_json
from hsconfig.package_domain import canonical_relative_path
from hsconfig.run_manifest import (
    MAX_MANIFEST_BYTES,
    MAX_RUN_FILES,
    MAX_RUN_PATH_BYTES,
    MAX_RUN_TOTAL_BYTES,
)


MAX_FILESYSTEM_DIRECTORIES = 10_000
MAX_FILESYSTEM_DEPTH = 64
MAX_FILESYSTEM_ENTRIES_PER_DIRECTORY = 10_000
MAX_FILESYSTEM_NODES = 110_000
_REPARSE_ATTRIBUTE = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
PathIdentity = tuple[int, int, int]
SiblingNoReplaceFaultPoint = Literal[
    "after_posix_link_before_source_unlink",
]
SiblingNoReplaceFaultHook = Callable[[SiblingNoReplaceFaultPoint], None]
_QUARANTINED_WINDOWS_HANDLES: list[_WindowsNativeHandleLease] = []
_DIRECTORY_GUARD_AUTHORITY = object()
_ACTIVE_DIRECTORY_GUARDS: dict[
    int,
    tuple[object, "PlainDirectoryMutationGuard", int],
] = {}
_ACTIVE_DIRECTORY_GUARDS_LOCK = Lock()
_POSIX_VERIFIED_UNLINK_CAPABLE = (
    hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
    and hasattr(os, "O_NONBLOCK")
    and {os.open, os.stat, os.unlink}.issubset(
        getattr(os, "supports_dir_fd", ())
    )
    and os.stat in getattr(os, "supports_follow_symlinks", ())
)
_POSIX_VERIFIED_RMDIR_CAPABLE = (
    hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
    and {os.open, os.stat, os.rmdir}.issubset(
        getattr(os, "supports_dir_fd", ())
    )
    and os.stat in getattr(os, "supports_follow_symlinks", ())
    and os.listdir in getattr(os, "supports_fd", ())
)


def no_sibling_no_replace_fault(
    _point: SiblingNoReplaceFaultPoint,
) -> None:
    """Default no-replace fault hook."""


class _WindowsNativeHandleLease:
    __slots__ = ("handle", "quarantined")

    def __init__(self) -> None:
        import ctypes

        self.handle = ctypes.c_void_p()
        self.quarantined = False

    @property
    def value(self) -> int:
        value = self.handle.value
        if value is None:
            raise ValueError("filesystem_windows_handle_unavailable")
        return int(value)


@dataclass(frozen=True, slots=True)
class _WindowsHandleState:
    volume_serial: int
    file_index: int
    attributes: int
    size: int
    links: int
    last_write: int


@dataclass(frozen=True, slots=True)
class FilesystemPathGuard:
    rows: tuple[tuple[Path, PathIdentity], ...]

    def validate(self) -> None:
        for path, expected in self.rows:
            status = path.lstat()
            if (
                status_is_reparse(status)
                or path_identity_from_status(status) != expected
            ):
                raise ValueError("filesystem_path_identity_changed")


@dataclass(frozen=True, slots=True, init=False)
class PlainDirectoryMutationGuard:
    path: Path
    descriptor: int
    identity: PathIdentity
    lease_rows: tuple[tuple[Path, int, PathIdentity], ...]
    _token: object

    def __init__(
        self,
        *,
        path: Path,
        descriptor: int,
        identity: PathIdentity,
        lease_rows: tuple[tuple[Path, int, PathIdentity], ...],
        authority: object | None = None,
    ) -> None:
        if authority is not _DIRECTORY_GUARD_AUTHORITY:
            raise TypeError("filesystem_directory_guard_not_constructible")
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "descriptor", descriptor)
        object.__setattr__(self, "identity", identity)
        object.__setattr__(self, "lease_rows", lease_rows)
        object.__setattr__(self, "_token", object())

    def validate(self) -> None:
        _require_active_directory_guard(self)
        for path, descriptor, identity in self.lease_rows:
            if (
                path_identity(path) != identity
                or path_identity_from_status(os.fstat(descriptor))
                != identity
            ):
                raise ValueError("filesystem_path_identity_changed")

    @contextmanager
    def hold_child_directory(
        self,
        name: str,
        *,
        expected_identity: PathIdentity | None = None,
    ) -> Iterator[PlainDirectoryMutationGuard]:
        """Hold one plain direct child relative to this active guard."""

        _require_child_name(name)
        self.validate()
        if os.name == "nt":
            descriptor = _open_plain_directory_descriptor(self.path / name)
            status = os.fstat(descriptor)
            visible = (self.path / name).lstat()
        else:
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            flags |= getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(name, flags, dir_fd=self.descriptor)
            status = os.fstat(descriptor)
            visible = os.stat(
                name,
                dir_fd=self.descriptor,
                follow_symlinks=False,
            )
        try:
            identity = path_identity_from_status(status)
            if (
                not stat.S_ISDIR(status.st_mode)
                or status_is_reparse(status)
                or status_is_reparse(visible)
                or path_identity_from_status(visible) != identity
                or (
                    expected_identity is not None
                    and identity != expected_identity
                )
            ):
                raise ValueError("filesystem_directory_identity_changed")
            child = PlainDirectoryMutationGuard(
                path=self.path / name,
                descriptor=descriptor,
                identity=identity,
                lease_rows=(*self.lease_rows, (self.path / name, descriptor, identity)),
                authority=_DIRECTORY_GUARD_AUTHORITY,
            )
            _register_directory_guard(child)
            try:
                child.validate()
                yield child
                child.validate()
            finally:
                _deregister_directory_guard(child)
        finally:
            os.close(descriptor)

    def open_file(
        self,
        name: str,
        *,
        create: bool,
        write: bool,
    ) -> int:
        _require_child_name(name)
        self.validate()
        flags = os.O_RDWR if write else os.O_RDONLY
        flags |= getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOINHERIT", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        if create:
            flags |= os.O_CREAT | os.O_EXCL
        if os.name == "nt":
            descriptor = _open_windows_child_file_descriptor(
                self.path / name,
                create=create,
                write=write,
            )
        else:
            descriptor = os.open(
                name,
                flags,
                0o600,
                dir_fd=self.descriptor,
            )
        try:
            os.set_inheritable(descriptor, False)
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or status_is_reparse(opened)
                or opened.st_nlink != 1
            ):
                raise ValueError("filesystem_file_invalid")
            if os.name == "nt":
                child_status = (self.path / name).lstat()
            else:
                child_status = os.stat(
                    name,
                    dir_fd=self.descriptor,
                    follow_symlinks=False,
                )
            if (
                path_identity_from_status(child_status)
                != path_identity_from_status(opened)
                or status_is_reparse(child_status)
            ):
                raise ValueError("filesystem_file_identity_changed")
            self.validate()
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    def create_directory(self, name: str) -> PathIdentity:
        _require_child_name(name)
        self.validate()
        if os.name == "nt":
            descriptor = _create_windows_child_directory_descriptor(
                self,
                name,
            )
            try:
                status = os.fstat(descriptor)
                child_status = (self.path / name).lstat()
                if (
                    path_identity_from_status(child_status)
                    != path_identity_from_status(status)
                    or status_is_reparse(child_status)
                ):
                    raise ValueError("filesystem_path_identity_changed")
                self.validate()
                return path_identity_from_status(status)
            finally:
                os.close(descriptor)
        else:
            os.mkdir(name, 0o700, dir_fd=self.descriptor)
            status = os.stat(
                name,
                dir_fd=self.descriptor,
                follow_symlinks=False,
            )
        if not stat.S_ISDIR(status.st_mode) or status_is_reparse(status):
            raise ValueError("filesystem_directory_invalid")
        self.validate()
        return path_identity_from_status(status)

    def child_status(self, name: str) -> os.stat_result:
        _require_child_name(name)
        self.validate()
        if os.name == "nt":
            return (self.path / name).lstat()
        return os.stat(
            name,
            dir_fd=self.descriptor,
            follow_symlinks=False,
        )


@contextmanager
def hold_plain_directory(
    path: Path,
    *,
    expected_identity: PathIdentity | None = None,
) -> Iterator[PlainDirectoryMutationGuard]:
    directory = Path(path)
    lease_rows: list[tuple[Path, int, PathIdentity]] = []
    try:
        lease_paths = (
            _windows_directory_chain(directory)
            if os.name == "nt"
            else (directory,)
        )
        for lease_path in lease_paths:
            status = lease_path.lstat()
            if (
                not stat.S_ISDIR(status.st_mode)
                or status_is_reparse(status)
            ):
                raise ValueError("filesystem_directory_invalid")
            identity = path_identity_from_status(status)
            descriptor = _open_plain_directory_descriptor(lease_path)
            opened_identity = path_identity_from_status(
                os.fstat(descriptor)
            )
            if opened_identity != identity:
                os.close(descriptor)
                raise ValueError("filesystem_path_identity_changed")
            lease_rows.append((lease_path, descriptor, identity))
        identity = lease_rows[-1][2]
        if expected_identity is not None and identity != expected_identity:
            raise ValueError("filesystem_path_identity_changed")
        guard = PlainDirectoryMutationGuard(
            path=directory,
            descriptor=lease_rows[-1][1],
            identity=identity,
            lease_rows=tuple(lease_rows),
            authority=_DIRECTORY_GUARD_AUTHORITY,
        )
        _register_directory_guard(guard)
        try:
            guard.validate()
            yield guard
            guard.validate()
        finally:
            _deregister_directory_guard(guard)
    finally:
        for _path, descriptor, _identity in reversed(lease_rows):
            os.close(descriptor)


def _register_directory_guard(guard: PlainDirectoryMutationGuard) -> None:
    with _ACTIVE_DIRECTORY_GUARDS_LOCK:
        _ACTIVE_DIRECTORY_GUARDS[id(guard._token)] = (
            guard._token,
            guard,
            get_ident(),
        )


def _deregister_directory_guard(guard: PlainDirectoryMutationGuard) -> None:
    with _ACTIVE_DIRECTORY_GUARDS_LOCK:
        active = _ACTIVE_DIRECTORY_GUARDS.get(id(guard._token))
        if active is not None and active[0] is guard._token and active[1] is guard:
            _ACTIVE_DIRECTORY_GUARDS.pop(id(guard._token), None)


def _require_active_directory_guard(
    guard: PlainDirectoryMutationGuard,
) -> None:
    if not isinstance(guard, PlainDirectoryMutationGuard):
        raise ValueError("filesystem_directory_guard_invalid")
    with _ACTIVE_DIRECTORY_GUARDS_LOCK:
        active = _ACTIVE_DIRECTORY_GUARDS.get(id(guard._token))
    if (
        active is None
        or active[0] is not guard._token
        or active[1] is not guard
        or active[2] != get_ident()
    ):
        raise ValueError("filesystem_directory_guard_inactive")


def bootstrap_plain_child_directory_under_guard(
    *,
    parent_guard: PlainDirectoryMutationGuard,
    child_name: str,
) -> PathIdentity:
    """Create once or bind an existing canonical plain direct child."""

    _require_child_name(child_name)
    parent_guard.validate()
    try:
        status = parent_guard.child_status(child_name)
    except FileNotFoundError:
        try:
            identity = parent_guard.create_directory(child_name)
        except FileExistsError:
            status = parent_guard.child_status(child_name)
        else:
            parent_guard.validate()
            return identity
    if (
        not stat.S_ISDIR(status.st_mode)
        or status_is_reparse(status)
    ):
        raise ValueError("filesystem_directory_invalid")
    identity = path_identity_from_status(status)
    require_same_identity_resolution(
        parent_guard.path / child_name,
        expected_status=status,
    )
    parent_guard.validate()
    return identity


def secure_create_directory(
    path: Path,
    *,
    expected_parent_identity: PathIdentity | None = None,
) -> PathIdentity:
    child = Path(path)
    with hold_plain_directory(
        child.parent,
        expected_identity=expected_parent_identity,
    ) as parent:
        return parent.create_directory(child.name)


def secure_open_file_descriptor(
    path: Path,
    *,
    create: bool,
    write: bool,
    expected_parent_identity: PathIdentity | None = None,
) -> int:
    child = Path(path)
    with hold_plain_directory(
        child.parent,
        expected_identity=expected_parent_identity,
    ) as parent:
        return parent.open_file(
            child.name,
            create=create,
            write=write,
        )


def secure_replace(
    source: Path,
    target: Path,
    *,
    expected_source_identity: PathIdentity | None = None,
    expected_source_parent_identity: PathIdentity | None = None,
    expected_target_parent_identity: PathIdentity | None = None,
    expected_target_identity: PathIdentity | None = None,
    expected_target_absent: bool = False,
) -> None:
    source_path = Path(source)
    target_path = Path(target)
    if source_path.parent == target_path.parent:
        with hold_plain_directory(
            source_path.parent,
            expected_identity=expected_source_parent_identity,
        ) as parent:
            if (
                expected_target_parent_identity is not None
                and parent.identity != expected_target_parent_identity
            ):
                raise ValueError("filesystem_path_identity_changed")
            source_status = _validate_replace_source(
                parent,
                source_path.name,
                expected_source_identity,
            )
            if expected_target_absent:
                _require_absent_child(parent, target_path.name)
            _replace_guarded(
                parent,
                source_path.name,
                parent,
                target_path.name,
                expected_source_identity=path_identity_from_status(
                    source_status
                ),
                expected_target_identity=expected_target_identity,
                source_directory=stat.S_ISDIR(source_status.st_mode),
                replace_if_exists=not expected_target_absent,
            )
        return
    with hold_plain_directory(
        source_path.parent,
        expected_identity=expected_source_parent_identity,
    ) as source_parent:
        with hold_plain_directory(
            target_path.parent,
            expected_identity=expected_target_parent_identity,
        ) as target_parent:
            source_status = _validate_replace_source(
                source_parent,
                source_path.name,
                expected_source_identity,
            )
            if expected_target_absent:
                _require_absent_child(
                    target_parent,
                    target_path.name,
                )
            _replace_guarded(
                source_parent,
                source_path.name,
                target_parent,
                target_path.name,
                expected_source_identity=path_identity_from_status(
                    source_status
                ),
                expected_target_identity=expected_target_identity,
                source_directory=stat.S_ISDIR(source_status.st_mode),
                replace_if_exists=not expected_target_absent,
            )


def secure_commit_sibling_no_replace(
    *,
    source_path: Path,
    target_path: Path,
    expected_source_identity: PathIdentity,
    expected_parent_identity: PathIdentity,
    fault_hook: SiblingNoReplaceFaultHook = no_sibling_no_replace_fault,
) -> PathIdentity:
    """Commit one already-bound sibling to an absent final name.

    The operation never selects authority from a live occupant.  A caller may
    resume from the exact final-only state or, on POSIX, from the exact
    two-name hard-link intermediate left after the atomic no-replace link.
    """

    source = Path(source_path)
    target = Path(target_path)
    if (
        source.parent != target.parent
        or source.name == target.name
        or source.parent != Path(source.parent).absolute()
        or target.parent != Path(target.parent).absolute()
    ):
        raise ValueError("filesystem_sibling_no_replace_contract_invalid")
    _require_child_name(source.name)
    _require_child_name(target.name)
    if (
        not isinstance(expected_source_identity, tuple)
        or len(expected_source_identity) != 3
        or any(type(item) is not int for item in expected_source_identity)
    ):
        raise ValueError("filesystem_sibling_no_replace_identity_invalid")

    with hold_plain_directory(
        source.parent,
        expected_identity=expected_parent_identity,
    ) as parent:
        source_status = _optional_child_status(parent, source.name)
        target_status = _optional_child_status(parent, target.name)

        if source_status is None:
            if target_status is None:
                raise FileNotFoundError(source)
            _require_bound_no_replace_file(
                target_status,
                expected_identity=expected_source_identity,
                allowed_link_counts=frozenset({1}),
            )
            parent.validate()
            return expected_source_identity

        allowed_source_links = frozenset({1}) if os.name == "nt" else frozenset({1, 2})
        _require_bound_no_replace_file(
            source_status,
            expected_identity=expected_source_identity,
            allowed_link_counts=allowed_source_links,
        )
        if os.name != "nt":
            _require_no_replace_link_state(
                source_status=source_status,
                target_status=target_status,
            )

        if target_status is not None:
            if os.name == "nt":
                raise FileExistsError(target)
            _require_bound_no_replace_file(
                target_status,
                expected_identity=expected_source_identity,
                allowed_link_counts=frozenset({2}),
            )
            if source_status.st_nlink != 2:
                raise ValueError("filesystem_sibling_no_replace_intermediate_invalid")
        elif os.name == "nt":
            _replace_guarded(
                parent,
                source.name,
                parent,
                target.name,
                expected_source_identity=expected_source_identity,
                source_directory=False,
                replace_if_exists=False,
            )
            committed = parent.child_status(target.name)
            _require_bound_no_replace_file(
                committed,
                expected_identity=expected_source_identity,
                allowed_link_counts=frozenset({1}),
            )
            return expected_source_identity
        else:
            parent.validate()
            os.link(
                source.name,
                target.name,
                src_dir_fd=parent.descriptor,
                dst_dir_fd=parent.descriptor,
                follow_symlinks=False,
            )
            parent.validate()

        # POSIX commit or exact crash-resume intermediate.
        source_after = parent.child_status(source.name)
        target_after = parent.child_status(target.name)
        _require_bound_no_replace_file(
            source_after,
            expected_identity=expected_source_identity,
            allowed_link_counts=frozenset({2}),
        )
        _require_bound_no_replace_file(
            target_after,
            expected_identity=expected_source_identity,
            allowed_link_counts=frozenset({2}),
        )
        if source_after.st_nlink != 2 or target_after.st_nlink != 2:
            raise ValueError("filesystem_sibling_no_replace_intermediate_invalid")
        fault_hook("after_posix_link_before_source_unlink")
        parent.validate()
        os.unlink(source.name, dir_fd=parent.descriptor)
        _flush_directory_descriptor(parent.descriptor)
        parent.validate()
        try:
            parent.child_status(source.name)
        except FileNotFoundError:
            pass
        else:
            raise ValueError("filesystem_sibling_no_replace_source_not_retired")
        final_status = parent.child_status(target.name)
        _require_bound_no_replace_file(
            final_status,
            expected_identity=expected_source_identity,
            allowed_link_counts=frozenset({1}),
        )
        return expected_source_identity


def _optional_child_status(
    parent: PlainDirectoryMutationGuard,
    name: str,
) -> os.stat_result | None:
    try:
        return parent.child_status(name)
    except FileNotFoundError:
        return None


def _require_no_replace_link_state(
    *,
    source_status: os.stat_result,
    target_status: os.stat_result | None,
) -> None:
    if target_status is None:
        if source_status.st_nlink != 1:
            raise ValueError(
                "filesystem_sibling_no_replace_foreign_link_forbidden"
            )
        return
    if source_status.st_nlink != 2 or target_status.st_nlink != 2:
        raise ValueError(
            "filesystem_sibling_no_replace_intermediate_link_invalid"
        )


def _require_bound_no_replace_file(
    status: os.stat_result,
    *,
    expected_identity: PathIdentity,
    allowed_link_counts: frozenset[int],
) -> None:
    if (
        path_identity_from_status(status) != expected_identity
        or not stat.S_ISREG(status.st_mode)
        or status_is_reparse(status)
        or status.st_nlink not in allowed_link_counts
    ):
        raise ValueError("filesystem_sibling_no_replace_identity_changed")


def _flush_directory_descriptor(descriptor: int) -> None:
    try:
        os.fsync(descriptor)
    except OSError as error:
        if error.errno not in {errno.EBADF, errno.EINVAL, errno.ENOTSUP}:
            raise


def _validate_replace_source(
    parent: PlainDirectoryMutationGuard,
    name: str,
    expected_identity: PathIdentity | None,
) -> os.stat_result:
    status = parent.child_status(name)
    if status_is_reparse(status):
        raise ValueError("filesystem_replace_source_invalid")
    if (
        expected_identity is not None
        and path_identity_from_status(status) != expected_identity
    ):
        raise ValueError("filesystem_path_identity_changed")
    return status


def _require_absent_child(
    parent: PlainDirectoryMutationGuard,
    name: str,
) -> None:
    try:
        parent.child_status(name)
    except FileNotFoundError:
        return
    raise FileExistsError(name)


def secure_unlink(
    path: Path,
    *,
    expected_identity: PathIdentity | None = None,
    expected_parent_identity: PathIdentity | None = None,
    missing_ok: bool = False,
) -> bool:
    child = Path(path)
    with hold_plain_directory(
        child.parent,
        expected_identity=expected_parent_identity,
    ) as parent:
        try:
            status = parent.child_status(child.name)
        except FileNotFoundError:
            if missing_ok:
                return False
            raise
        if (
            expected_identity is not None
            and path_identity_from_status(status) != expected_identity
        ):
            raise ValueError("filesystem_path_identity_changed")
        if (
            not stat.S_ISREG(status.st_mode)
            or status_is_reparse(status)
            or status.st_nlink != 1
        ):
            raise ValueError("filesystem_file_invalid")
        parent.validate()
        if os.name == "nt":
            _delete_windows_owned_child(
                parent,
                child.name,
                expected_identity=path_identity_from_status(status),
                directory=False,
            )
        else:
            os.unlink(child.name, dir_fd=parent.descriptor)
        parent.validate()
        return True


def secure_unlink_verified(
    path: Path,
    *,
    expected_identity: PathIdentity,
    expected_parent_identity: PathIdentity,
    expected_size: int,
    expected_sha256: str,
) -> None:
    if (
        type(expected_size) is not int
        or expected_size < 0
        or expected_size > MAX_RUN_TOTAL_BYTES
        or not isinstance(expected_sha256, str)
        or len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        raise ValueError("filesystem_verified_unlink_contract_invalid")
    if os.name != "nt":
        return _secure_unlink_verified_posix(
            path,
            expected_identity=expected_identity,
            expected_parent_identity=expected_parent_identity,
            expected_size=expected_size,
            expected_sha256=expected_sha256,
        )
    child = Path(path)
    with hold_plain_directory(
        child.parent,
        expected_identity=expected_parent_identity,
    ) as parent:
        status = parent.child_status(child.name)
        if (
            path_identity_from_status(status) != expected_identity
            or not stat.S_ISREG(status.st_mode)
            or status_is_reparse(status)
            or status.st_nlink != 1
            or status.st_size != expected_size
        ):
            raise ValueError("filesystem_verified_unlink_content_changed")
        parent.validate()
        with _hold_windows_owned_child_handle(
            parent,
            child.name,
            expected_identity=expected_identity,
            directory=False,
            content_read=True,
            deny_write_share=True,
        ) as lease:
            opened = _windows_native_handle_state(lease.value)
            digest = _windows_native_handle_sha256(lease.value, expected_size)
            after = _windows_native_handle_state(lease.value)
            current = parent.child_status(child.name)
            if (
                digest != expected_sha256
                or after != opened
                or (after.volume_serial, after.file_index) != expected_identity[:2]
                or path_identity_from_status(current) != expected_identity
                or after.attributes & 0x00000010
                or after.attributes & _REPARSE_ATTRIBUTE
                or status_is_reparse(current)
                or not stat.S_ISREG(current.st_mode)
                or after.links != 1
                or current.st_nlink != 1
                or after.size != expected_size
                or current.st_size != expected_size
            ):
                raise ValueError("filesystem_verified_unlink_content_changed")
            parent.validate()
            if _windows_native_handle_streams(lease.value) != (
                ("::$DATA", expected_size),
            ):
                raise ValueError("filesystem_verified_unlink_stream_invalid")
            commit_authorized = False
            primary_error: BaseException | None = None
            try:
                _set_windows_native_handle_delete(lease.value, delete=True)
                pending = _windows_native_handle_state(lease.value)
                if (
                    (pending.volume_serial, pending.file_index) != expected_identity[:2]
                    or pending.attributes != after.attributes
                    or pending.size != expected_size
                    or pending.links != 0
                    or pending.last_write != after.last_write
                ):
                    raise ValueError("filesystem_verified_unlink_content_changed")
                if _windows_native_handle_streams(lease.value) != (
                    ("::$DATA", expected_size),
                ):
                    raise ValueError("filesystem_verified_unlink_stream_invalid")
                commit_authorized = True
            except BaseException as error:
                primary_error = error
                raise
            finally:
                if not commit_authorized:
                    try:
                        _clear_windows_native_handle_delete(lease.value)
                    except BaseException as cleanup_error:
                        _quarantine_windows_native_handle(lease)
                        if primary_error is not None:
                            primary_error.add_note(
                                "failed to cancel verified unlink disposition: "
                                f"{type(cleanup_error).__name__}"
                            )
                        else:
                            raise
        parent.validate()


def secure_rmdir_verified(
    path: Path,
    *,
    expected_identity: PathIdentity,
    expected_parent_identity: PathIdentity,
) -> None:
    if os.name != "nt":
        return _secure_rmdir_verified_posix(
            path,
            expected_identity=expected_identity,
            expected_parent_identity=expected_parent_identity,
        )
    child = Path(path)
    with hold_plain_directory(
        child.parent,
        expected_identity=expected_parent_identity,
    ) as parent:
        status = parent.child_status(child.name)
        if (
            path_identity_from_status(status) != expected_identity
            or not stat.S_ISDIR(status.st_mode)
            or status_is_reparse(status)
        ):
            raise ValueError("filesystem_verified_rmdir_content_changed")
        parent.validate()
        with _hold_windows_owned_child_handle(
            parent,
            child.name,
            expected_identity=expected_identity,
            directory=True,
            deny_write_share=True,
        ) as lease:
            if _windows_native_handle_streams(lease.value):
                raise ValueError("filesystem_verified_rmdir_stream_invalid")
            commit_authorized = False
            primary_error: BaseException | None = None
            try:
                _set_windows_native_handle_delete(lease.value, delete=True)
                if _windows_native_handle_streams(lease.value):
                    raise ValueError("filesystem_verified_rmdir_stream_invalid")
                commit_authorized = True
            except BaseException as error:
                primary_error = error
                raise
            finally:
                if not commit_authorized:
                    try:
                        _clear_windows_native_handle_delete(lease.value)
                    except BaseException as cleanup_error:
                        _quarantine_windows_native_handle(lease)
                        if primary_error is not None:
                            primary_error.add_note(
                                "failed to cancel verified rmdir disposition: "
                                f"{type(cleanup_error).__name__}"
                            )
                        else:
                            raise
        parent.validate()


@contextmanager
def _hold_posix_advisory_exclusive_lock(
    descriptor: int,
) -> Iterator[None]:
    try:
        import fcntl
    except ImportError:
        yield
        return
    flock = getattr(fcntl, "flock", None)
    if flock is None:
        yield
        return
    try:
        flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        unsupported = {
            errno.EISDIR,
            errno.EINVAL,
            errno.ENOSYS,
            errno.ENOTSUP,
            getattr(errno, "EOPNOTSUPP", errno.ENOTSUP),
        }
        if error.errno not in unsupported:
            raise
        yield
        return
    try:
        yield
    finally:
        try:
            flock(descriptor, fcntl.LOCK_UN)
        except OSError:
            pass


def _require_posix_verified_mutation_capabilities(
    *,
    path: Path,
    directory: bool,
) -> None:
    supported = (
        _POSIX_VERIFIED_RMDIR_CAPABLE
        if directory
        else _POSIX_VERIFIED_UNLINK_CAPABLE
    )
    if supported:
        return
    reason = (
        "filesystem_verified_rmdir_unsupported"
        if directory
        else "filesystem_verified_unlink_unsupported"
    )
    raise OSError(errno.ENOTSUP, reason, str(path))


def _posix_descriptor_sha256(
    descriptor: int,
    *,
    expected_size: int,
) -> str:
    os.lseek(descriptor, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    remaining = expected_size
    while remaining:
        chunk = os.read(descriptor, min(1024 * 1024, remaining))
        if not chunk:
            raise ValueError("filesystem_verified_unlink_content_changed")
        digest.update(chunk)
        remaining -= len(chunk)
    if os.read(descriptor, 1):
        raise ValueError("filesystem_verified_unlink_content_changed")
    return digest.hexdigest()


def _require_posix_verified_file_state(
    status: os.stat_result,
    *,
    expected_identity: PathIdentity,
    expected_size: int,
) -> None:
    if (
        path_identity_from_status(status) != expected_identity
        or not stat.S_ISREG(status.st_mode)
        or status_is_reparse(status)
        or status.st_nlink != 1
        or status.st_size != expected_size
    ):
        raise ValueError("filesystem_verified_unlink_content_changed")


def _secure_unlink_verified_posix(
    path: Path,
    *,
    expected_identity: PathIdentity,
    expected_parent_identity: PathIdentity,
    expected_size: int,
    expected_sha256: str,
) -> None:
    child = Path(path)
    _require_posix_verified_mutation_capabilities(
        path=child,
        directory=False,
    )
    descriptor = -1
    try:
        with hold_plain_directory(
            child.parent,
            expected_identity=expected_parent_identity,
        ) as parent:
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            flags |= os.O_NOFOLLOW | os.O_NONBLOCK
            descriptor = os.open(
                child.name,
                flags,
                dir_fd=parent.descriptor,
            )
            os.set_inheritable(descriptor, False)
            with _hold_posix_advisory_exclusive_lock(descriptor):
                opened = os.fstat(descriptor)
                visible = parent.child_status(child.name)
                _require_posix_verified_file_state(
                    opened,
                    expected_identity=expected_identity,
                    expected_size=expected_size,
                )
                _require_posix_verified_file_state(
                    visible,
                    expected_identity=expected_identity,
                    expected_size=expected_size,
                )
                opened_state = _file_state(opened, platform_name="posix")
                if (
                    opened_state
                    != _file_state(visible, platform_name="posix")
                    or _posix_descriptor_sha256(
                        descriptor,
                        expected_size=expected_size,
                    )
                    != expected_sha256
                ):
                    raise ValueError(
                        "filesystem_verified_unlink_content_changed"
                    )
                before_delete = os.fstat(descriptor)
                visible_before_delete = parent.child_status(child.name)
                _require_posix_verified_file_state(
                    before_delete,
                    expected_identity=expected_identity,
                    expected_size=expected_size,
                )
                _require_posix_verified_file_state(
                    visible_before_delete,
                    expected_identity=expected_identity,
                    expected_size=expected_size,
                )
                if (
                    opened_state
                    != _file_state(before_delete, platform_name="posix")
                    or opened_state
                    != _file_state(
                        visible_before_delete,
                        platform_name="posix",
                    )
                ):
                    raise ValueError(
                        "filesystem_verified_unlink_content_changed"
                    )
                parent.validate()
                os.unlink(child.name, dir_fd=parent.descriptor)
                after_delete = os.fstat(descriptor)
                if (
                    path_identity_from_status(after_delete) != expected_identity
                    or not stat.S_ISREG(after_delete.st_mode)
                    or status_is_reparse(after_delete)
                    or after_delete.st_size != expected_size
                ):
                    raise ValueError(
                        "filesystem_verified_unlink_content_changed"
                    )
                try:
                    parent.child_status(child.name)
                except FileNotFoundError:
                    pass
                else:
                    raise ValueError(
                        "filesystem_verified_unlink_content_changed"
                    )
                parent.validate()
    except (OSError, ValueError) as error:
        if (
            isinstance(error, ValueError)
            and error.args == ("filesystem_verified_unlink_content_changed",)
        ):
            raise
        raise ValueError("filesystem_verified_unlink_content_changed") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _require_posix_verified_directory_state(
    status: os.stat_result,
    *,
    expected_identity: PathIdentity,
) -> None:
    if (
        path_identity_from_status(status) != expected_identity
        or not stat.S_ISDIR(status.st_mode)
        or status_is_reparse(status)
    ):
        raise ValueError("filesystem_verified_rmdir_content_changed")


def _secure_rmdir_verified_posix(
    path: Path,
    *,
    expected_identity: PathIdentity,
    expected_parent_identity: PathIdentity,
) -> None:
    child = Path(path)
    _require_posix_verified_mutation_capabilities(
        path=child,
        directory=True,
    )
    descriptor = -1
    try:
        with hold_plain_directory(
            child.parent,
            expected_identity=expected_parent_identity,
        ) as parent:
            flags = os.O_RDONLY | os.O_DIRECTORY
            flags |= getattr(os, "O_CLOEXEC", 0)
            flags |= os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0)
            descriptor = os.open(
                child.name,
                flags,
                dir_fd=parent.descriptor,
            )
            os.set_inheritable(descriptor, False)
            with _hold_posix_advisory_exclusive_lock(descriptor):
                opened = os.fstat(descriptor)
                visible = parent.child_status(child.name)
                _require_posix_verified_directory_state(
                    opened,
                    expected_identity=expected_identity,
                )
                _require_posix_verified_directory_state(
                    visible,
                    expected_identity=expected_identity,
                )
                opened_state = _file_state(opened, platform_name="posix")
                if (
                    opened_state
                    != _file_state(visible, platform_name="posix")
                    or os.listdir(descriptor)
                ):
                    raise ValueError(
                        "filesystem_verified_rmdir_content_changed"
                    )
                before_delete = os.fstat(descriptor)
                visible_before_delete = parent.child_status(child.name)
                _require_posix_verified_directory_state(
                    before_delete,
                    expected_identity=expected_identity,
                )
                _require_posix_verified_directory_state(
                    visible_before_delete,
                    expected_identity=expected_identity,
                )
                if (
                    opened_state
                    != _file_state(before_delete, platform_name="posix")
                    or opened_state
                    != _file_state(
                        visible_before_delete,
                        platform_name="posix",
                    )
                    or os.listdir(descriptor)
                ):
                    raise ValueError(
                        "filesystem_verified_rmdir_content_changed"
                    )
                parent.validate()
                os.rmdir(child.name, dir_fd=parent.descriptor)
                after_delete = os.fstat(descriptor)
                _require_posix_verified_directory_state(
                    after_delete,
                    expected_identity=expected_identity,
                )
                try:
                    parent.child_status(child.name)
                except FileNotFoundError:
                    pass
                else:
                    raise ValueError(
                        "filesystem_verified_rmdir_content_changed"
                    )
                parent.validate()
    except (OSError, ValueError) as error:
        if (
            isinstance(error, ValueError)
            and error.args == ("filesystem_verified_rmdir_content_changed",)
        ):
            raise
        raise ValueError("filesystem_verified_rmdir_content_changed") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def require_no_alternate_data_streams(
    path: Path,
    *,
    expected_identity: PathIdentity,
    expected_parent_identity: PathIdentity,
    directory: bool,
    expected_size: int | None = None,
) -> None:
    if os.name != "nt":
        return
    child = Path(path)
    if child.is_absolute() and child.parent == child:
        _require_no_alternate_data_streams_root(
            child,
            expected_identity=expected_identity,
            expected_parent_identity=expected_parent_identity,
            directory=directory,
            expected_size=expected_size,
        )
        return
    with hold_plain_directory(
        child.parent,
        expected_identity=expected_parent_identity,
    ) as parent:
        with _hold_windows_owned_child_handle(
            parent,
            child.name,
            expected_identity=expected_identity,
            directory=directory,
            content_read=False,
            deny_write_share=True,
            delete_access=False,
        ) as lease:
            streams = _windows_native_handle_streams(lease.value)
            expected = () if directory else (("::$DATA", expected_size),)
            if streams != expected:
                raise ValueError("filesystem_alternate_data_stream_forbidden")
        parent.validate()


def require_open_file_descriptor_no_alternate_data_streams(
    descriptor: int,
    *,
    expected_size: int,
) -> None:
    """Validate streams through an already-open, identity-bound file handle."""

    if os.name != "nt":
        return
    if type(descriptor) is not int or descriptor < 0:
        raise ValueError("filesystem_descriptor_invalid")
    if type(expected_size) is not int or expected_size < 0:
        raise ValueError("filesystem_stream_size_invalid")
    import msvcrt

    streams = _windows_native_handle_streams(
        msvcrt.get_osfhandle(descriptor)
    )
    if streams != (("::$DATA", expected_size),):
        raise ValueError("filesystem_alternate_data_stream_forbidden")


def _require_no_alternate_data_streams_root(
    root: Path,
    *,
    expected_identity: PathIdentity,
    expected_parent_identity: PathIdentity,
    directory: bool,
    expected_size: int | None,
) -> None:
    if not directory or expected_size is not None:
        raise ValueError("filesystem_root_stream_validation_invalid")
    if expected_parent_identity != expected_identity:
        raise ValueError("filesystem_path_identity_changed")

    import msvcrt

    descriptor = _open_plain_directory_descriptor(
        root,
        deny_write_share=True,
    )
    try:
        native_handle = msvcrt.get_osfhandle(descriptor)
        before = _require_windows_root_directory_binding(
            root,
            descriptor=descriptor,
            native_handle=native_handle,
            expected_identity=expected_identity,
        )
        streams = _windows_native_handle_streams(native_handle)
        after = _require_windows_root_directory_binding(
            root,
            descriptor=descriptor,
            native_handle=native_handle,
            expected_identity=expected_identity,
        )
        if streams != () or after != before:
            raise ValueError("filesystem_alternate_data_stream_forbidden")
    finally:
        os.close(descriptor)


def _require_windows_root_directory_binding(
    root: Path,
    *,
    descriptor: int,
    native_handle: int,
    expected_identity: PathIdentity,
) -> _WindowsHandleState:
    opened_status = os.fstat(descriptor)
    lexical_status = root.lstat()
    opened = _windows_native_handle_state(native_handle)
    if (
        path_identity_from_status(opened_status) != expected_identity
        or path_identity_from_status(lexical_status) != expected_identity
        or (opened.volume_serial, opened.file_index) != expected_identity[:2]
        or not stat.S_ISDIR(opened_status.st_mode)
        or not stat.S_ISDIR(lexical_status.st_mode)
        or status_is_reparse(opened_status)
        or status_is_reparse(lexical_status)
        or not bool(opened.attributes & 0x00000010)
        or bool(opened.attributes & _REPARSE_ATTRIBUTE)
    ):
        raise ValueError("filesystem_path_identity_changed")
    return opened


def secure_rmdir(
    path: Path,
    *,
    expected_identity: PathIdentity | None = None,
    expected_parent_identity: PathIdentity | None = None,
    missing_ok: bool = False,
) -> bool:
    child = Path(path)
    with hold_plain_directory(
        child.parent,
        expected_identity=expected_parent_identity,
    ) as parent:
        try:
            status = parent.child_status(child.name)
        except FileNotFoundError:
            if missing_ok:
                return False
            raise
        if (
            expected_identity is not None
            and path_identity_from_status(status) != expected_identity
        ):
            raise ValueError("filesystem_path_identity_changed")
        if not stat.S_ISDIR(status.st_mode) or status_is_reparse(status):
            raise ValueError("filesystem_directory_invalid")
        parent.validate()
        if os.name == "nt":
            _delete_windows_owned_child(
                parent,
                child.name,
                expected_identity=path_identity_from_status(status),
                directory=True,
            )
        else:
            os.rmdir(child.name, dir_fd=parent.descriptor)
        parent.validate()
        return True


def _replace_guarded(
    source_parent: PlainDirectoryMutationGuard,
    source_name: str,
    target_parent: PlainDirectoryMutationGuard,
    target_name: str,
    *,
    expected_source_identity: PathIdentity,
    expected_target_identity: PathIdentity | None = None,
    source_directory: bool,
    replace_if_exists: bool,
) -> None:
    _require_child_name(source_name)
    _require_child_name(target_name)
    source_parent.validate()
    target_parent.validate()
    if expected_target_identity is not None:
        target_status = target_parent.child_status(target_name)
        if (
            status_is_reparse(target_status)
            or path_identity_from_status(target_status)
            != expected_target_identity
        ):
            raise ValueError("filesystem_path_identity_changed")
    if os.name == "nt":
        _replace_windows_owned_child(
            source_parent,
            source_name,
            target_parent,
            target_name,
            expected_identity=expected_source_identity,
            directory=source_directory,
            replace_if_exists=replace_if_exists,
        )
    else:
        os.replace(
            source_name,
            target_name,
            src_dir_fd=source_parent.descriptor,
            dst_dir_fd=target_parent.descriptor,
        )
    source_parent.validate()
    target_parent.validate()


def _open_plain_directory_descriptor(
    path: Path,
    *,
    deny_write_share: bool = False,
) -> int:
    if os.name != "nt":
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        return os.open(path, flags)

    import ctypes
    import msvcrt

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    )
    create_file.restype = ctypes.c_void_p
    handle = create_file(
        str(path),
        0x80000000,
        0x00000001 | (0 if deny_write_share else 0x00000002),
        None,
        3,
        0x02000000 | 0x00200000,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle == invalid_handle:
        error = ctypes.get_last_error()
        raise OSError(error, ctypes.FormatError(error), str(path))
    try:
        return msvcrt.open_osfhandle(
            handle,
            os.O_RDONLY | getattr(os, "O_NOINHERIT", 0),
        )
    except BaseException:
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        raise


def _open_windows_child_file_descriptor(
    path: Path,
    *,
    create: bool,
    write: bool,
) -> int:
    import ctypes
    import msvcrt

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_file = kernel32.CreateFileW
    create_file.argtypes = (
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_void_p,
    )
    create_file.restype = ctypes.c_void_p
    desired_access = 0x80000000 | (0x40000000 if write else 0)
    handle = create_file(
        str(path),
        desired_access,
        0x00000001 | 0x00000002,
        None,
        1 if create else 3,
        0x00000080 | 0x00200000,
        None,
    )
    invalid_handle = ctypes.c_void_p(-1).value
    if handle == invalid_handle:
        error = ctypes.get_last_error()
        if error in {80, 183}:
            raise FileExistsError(
                error,
                ctypes.FormatError(error),
                str(path),
            )
        if error in {2, 3}:
            raise FileNotFoundError(
                error,
                ctypes.FormatError(error),
                str(path),
            )
        raise OSError(error, ctypes.FormatError(error), str(path))
    try:
        flags = os.O_RDWR if write else os.O_RDONLY
        flags |= getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOINHERIT", 0)
        return msvcrt.open_osfhandle(handle, flags)
    except BaseException:
        kernel32.CloseHandle(ctypes.c_void_p(handle))
        raise


@contextmanager
def _hold_windows_owned_child_handle(
    parent: PlainDirectoryMutationGuard,
    name: str,
    *,
    expected_identity: PathIdentity,
    directory: bool,
    content_read: bool = False,
    deny_write_share: bool = False,
    delete_access: bool = True,
) -> Iterator[_WindowsNativeHandleLease]:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class UnicodeString(ctypes.Structure):
        _fields_ = (
            ("length", wintypes.USHORT),
            ("maximum_length", wintypes.USHORT),
            ("buffer", ctypes.c_void_p),
        )

    class ObjectAttributes(ctypes.Structure):
        _fields_ = (
            ("length", wintypes.ULONG),
            ("root_directory", wintypes.HANDLE),
            ("object_name", ctypes.POINTER(UnicodeString)),
            ("attributes", wintypes.ULONG),
            ("security_descriptor", ctypes.c_void_p),
            ("security_quality_of_service", ctypes.c_void_p),
        )

    class IoStatusBlock(ctypes.Structure):
        _fields_ = (
            ("status", ctypes.c_void_p),
            ("information", ctypes.c_size_t),
        )

    _require_child_name(name)
    parent.validate()
    name_buffer = ctypes.create_unicode_buffer(name)
    encoded_length = len(name.encode("utf-16-le"))
    unicode_name = UnicodeString(
        encoded_length,
        encoded_length + 2,
        ctypes.cast(name_buffer, ctypes.c_void_p),
    )
    attributes = ObjectAttributes(
        ctypes.sizeof(ObjectAttributes),
        msvcrt.get_osfhandle(parent.descriptor),
        ctypes.pointer(unicode_name),
        0x00000040 | 0x00001000,
        None,
        None,
    )
    io_status = IoStatusBlock()
    lease = _WindowsNativeHandleLease()
    ntdll = ctypes.WinDLL("ntdll")
    open_file = ntdll.NtOpenFile
    open_file.argtypes = (
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.ULONG,
        ctypes.POINTER(ObjectAttributes),
        ctypes.POINTER(IoStatusBlock),
        wintypes.ULONG,
        wintypes.ULONG,
    )
    open_file.restype = ctypes.c_long
    try:
        desired_access = 0x00000080 | 0x00100000
        if delete_access:
            desired_access |= 0x00010000
        if content_read:
            desired_access |= 0x00000001
        share_mode = 0x00000001
        if not deny_write_share:
            share_mode |= 0x00000002
        options = 0x00200000 | 0x00000020
        options |= 0x00000001 if directory else 0x00000040
        status = open_file(
            ctypes.byref(lease.handle),
            desired_access,
            ctypes.byref(attributes),
            ctypes.byref(io_status),
            share_mode,
            options,
        )
        if status < 0:
            rtl_status_to_dos_error = ntdll.RtlNtStatusToDosError
            rtl_status_to_dos_error.argtypes = (ctypes.c_long,)
            rtl_status_to_dos_error.restype = wintypes.ULONG
            error = rtl_status_to_dos_error(status)
            raise OSError(
                error,
                ctypes.FormatError(error),
                str(parent.path / name),
            )
        native_handle = lease.value
        opened = _windows_native_handle_state(native_handle)
        current = parent.child_status(name)
        expected_directory = bool(opened.attributes & 0x00000010)
        if (
            (opened.volume_serial, opened.file_index) != expected_identity[:2]
            or path_identity_from_status(current) != expected_identity
            or bool(opened.attributes & _REPARSE_ATTRIBUTE)
            or status_is_reparse(current)
            or expected_directory != directory
            or stat.S_ISDIR(current.st_mode) != directory
        ):
            raise ValueError("filesystem_path_identity_changed")
        parent.validate()
        yield lease
    finally:
        if lease.handle.value and not lease.quarantined:
            native_handle = lease.value
            lease.handle.value = None
            _close_windows_native_handle(native_handle)


def _create_windows_child_directory_descriptor(
    parent: PlainDirectoryMutationGuard,
    name: str,
) -> int:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    _require_child_name(name)
    parent.validate()
    name_buffer = ctypes.create_unicode_buffer(name)

    class UnicodeString(ctypes.Structure):
        _fields_ = (
            ("length", wintypes.USHORT),
            ("maximum_length", wintypes.USHORT),
            ("buffer", ctypes.c_void_p),
        )

    class ObjectAttributes(ctypes.Structure):
        _fields_ = (
            ("length", wintypes.ULONG),
            ("root_directory", wintypes.HANDLE),
            ("object_name", ctypes.POINTER(UnicodeString)),
            ("attributes", wintypes.ULONG),
            ("security_descriptor", ctypes.c_void_p),
            ("security_quality_of_service", ctypes.c_void_p),
        )

    class IoStatusBlock(ctypes.Structure):
        _fields_ = (
            ("status", ctypes.c_void_p),
            ("information", ctypes.c_size_t),
        )

    encoded_length = len(name.encode("utf-16-le"))
    unicode_name = UnicodeString(
        encoded_length,
        encoded_length + 2,
        ctypes.cast(name_buffer, ctypes.c_void_p),
    )
    attributes = ObjectAttributes(
        ctypes.sizeof(ObjectAttributes),
        msvcrt.get_osfhandle(parent.descriptor),
        ctypes.pointer(unicode_name),
        0x00000040 | 0x00001000,
        None,
        None,
    )
    io_status = IoStatusBlock()
    handle = wintypes.HANDLE()
    ntdll = ctypes.WinDLL("ntdll")
    create_file = ntdll.NtCreateFile
    create_file.argtypes = (
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.ULONG,
        ctypes.POINTER(ObjectAttributes),
        ctypes.POINTER(IoStatusBlock),
        ctypes.c_void_p,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.ULONG,
        wintypes.ULONG,
        ctypes.c_void_p,
        wintypes.ULONG,
    )
    create_file.restype = ctypes.c_long
    status = create_file(
        ctypes.byref(handle),
        0x80000000 | 0x00100000,
        ctypes.byref(attributes),
        ctypes.byref(io_status),
        None,
        0x00000010,
        0x00000001 | 0x00000002,
        2,
        0x00000001 | 0x00000020 | 0x00200000,
        None,
        0,
    )
    if status < 0:
        rtl_status_to_dos_error = ntdll.RtlNtStatusToDosError
        rtl_status_to_dos_error.argtypes = (ctypes.c_long,)
        rtl_status_to_dos_error.restype = wintypes.ULONG
        dos_error = rtl_status_to_dos_error(status)
        if dos_error in {80, 183}:
            raise FileExistsError(
                dos_error,
                ctypes.FormatError(dos_error),
                str(parent.path / name),
            )
        raise OSError(
            dos_error,
            ctypes.FormatError(dos_error),
            str(parent.path / name),
        )
    try:
        return msvcrt.open_osfhandle(
            handle.value,
            os.O_RDONLY | getattr(os, "O_NOINHERIT", 0),
        )
    except BaseException:
        ctypes.WinDLL("kernel32").CloseHandle(handle)
        raise


def _replace_windows_owned_child(
    source_parent: PlainDirectoryMutationGuard,
    source_name: str,
    target_parent: PlainDirectoryMutationGuard,
    target_name: str,
    *,
    expected_identity: PathIdentity,
    directory: bool,
    replace_if_exists: bool,
) -> None:
    with _hold_windows_owned_child_handle(
        source_parent,
        source_name,
        expected_identity=expected_identity,
        directory=directory,
    ) as lease:
        _set_windows_handle_name(
            lease.value,
            target_parent.path / target_name,
            target_parent_descriptor=target_parent.descriptor,
            replace_if_exists=replace_if_exists,
        )


def _delete_windows_owned_child(
    parent: PlainDirectoryMutationGuard,
    name: str,
    *,
    expected_identity: PathIdentity,
    directory: bool,
) -> None:
    with _hold_windows_owned_child_handle(
        parent,
        name,
        expected_identity=expected_identity,
        directory=directory,
    ) as lease:
        _set_windows_handle_delete(lease.value)


def _set_windows_native_handle_name(
    native_handle: int,
    target: Path,
    *,
    target_parent_descriptor: int,
    replace_if_exists: bool = True,
) -> None:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    name = target.name
    if not name or name in {".", ".."} or Path(name).name != name:
        raise ValueError("filesystem_child_name_invalid")

    class FileRenameInfo(ctypes.Structure):
        _fields_ = (
            ("replace_or_flags", wintypes.ULONG),
            ("root_directory", wintypes.HANDLE),
            ("file_name_length", wintypes.DWORD),
            ("file_name", wintypes.WCHAR * max(1, len(name))),
        )

    info = FileRenameInfo()
    info.replace_or_flags = int(replace_if_exists)
    info.root_directory = msvcrt.get_osfhandle(target_parent_descriptor)
    info.file_name_length = len(name.encode("utf-16-le"))
    info.file_name = name

    class IoStatusBlock(ctypes.Structure):
        _fields_ = (
            ("status", ctypes.c_void_p),
            ("information", ctypes.c_size_t),
        )

    io_status = IoStatusBlock()
    ntdll = ctypes.WinDLL("ntdll")
    set_information = ntdll.NtSetInformationFile
    set_information.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(IoStatusBlock),
        ctypes.c_void_p,
        wintypes.ULONG,
        ctypes.c_int,
    )
    set_information.restype = ctypes.c_long
    information_size = max(
        24,
        FileRenameInfo.file_name.offset + info.file_name_length,
    )
    status = set_information(
        native_handle,
        ctypes.byref(io_status),
        ctypes.byref(info),
        information_size,
        10,
    )
    if status < 0:
        rtl_status_to_dos_error = ntdll.RtlNtStatusToDosError
        rtl_status_to_dos_error.argtypes = (ctypes.c_long,)
        rtl_status_to_dos_error.restype = wintypes.ULONG
        dos_error = rtl_status_to_dos_error(status)
        raise OSError(
            dos_error,
            ctypes.FormatError(dos_error),
            str(target),
        )


def _windows_native_handle_state(native_handle: int) -> _WindowsHandleState:
    import ctypes
    from ctypes import wintypes

    class FileId128(ctypes.Structure):
        _fields_ = (("identifier", ctypes.c_ubyte * 16),)

    class FileIdInfo(ctypes.Structure):
        _fields_ = (
            ("volume_serial", ctypes.c_ulonglong),
            ("file_id", FileId128),
        )

    class FileTime(ctypes.Structure):
        _fields_ = (("low", wintypes.DWORD), ("high", wintypes.DWORD))

    class ByHandleFileInformation(ctypes.Structure):
        _fields_ = (
            ("attributes", wintypes.DWORD),
            ("creation_time", FileTime),
            ("last_access_time", FileTime),
            ("last_write_time", FileTime),
            ("volume_serial", wintypes.DWORD),
            ("size_high", wintypes.DWORD),
            ("size_low", wintypes.DWORD),
            ("links", wintypes.DWORD),
            ("file_index_high", wintypes.DWORD),
            ("file_index_low", wintypes.DWORD),
        )
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_information = kernel32.GetFileInformationByHandle
    get_information.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(ByHandleFileInformation),
    )
    get_information.restype = wintypes.BOOL
    information = ByHandleFileInformation()
    if not get_information(native_handle, ctypes.byref(information)):
        error = ctypes.get_last_error()
        raise OSError(error, ctypes.FormatError(error))

    volume_serial = int(information.volume_serial)
    file_index = (information.file_index_high << 32) | information.file_index_low
    if sys.version_info >= (3, 12):
        get_information_ex = kernel32.GetFileInformationByHandleEx
        get_information_ex.argtypes = (
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        )
        get_information_ex.restype = wintypes.BOOL
        full_information = FileIdInfo()
        if not get_information_ex(
            native_handle,
            18,
            ctypes.byref(full_information),
            ctypes.sizeof(full_information),
        ):
            error = ctypes.get_last_error()
            raise OSError(error, ctypes.FormatError(error))
        volume_serial = int(full_information.volume_serial)
        file_index = int.from_bytes(
            bytes(full_information.file_id.identifier),
            "little",
        )
    return _WindowsHandleState(
        volume_serial=volume_serial,
        file_index=file_index,
        attributes=information.attributes,
        size=(information.size_high << 32) | information.size_low,
        links=information.links,
        last_write=(information.last_write_time.high << 32)
        | information.last_write_time.low,
    )


def _set_windows_handle_name(
    native_handle: int,
    target: Path,
    *,
    target_parent_descriptor: int,
    replace_if_exists: bool = True,
) -> None:
    _set_windows_native_handle_name(
        native_handle,
        target,
        target_parent_descriptor=target_parent_descriptor,
        replace_if_exists=replace_if_exists,
    )


def _windows_native_handle_sha256(native_handle: int, expected_size: int) -> str:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    set_pointer = kernel32.SetFilePointerEx
    set_pointer.argtypes = (
        wintypes.HANDLE,
        ctypes.c_longlong,
        ctypes.POINTER(ctypes.c_longlong),
        wintypes.DWORD,
    )
    set_pointer.restype = wintypes.BOOL
    if not set_pointer(native_handle, 0, None, 0):
        error = ctypes.get_last_error()
        raise OSError(error, ctypes.FormatError(error))
    read_file = kernel32.ReadFile
    read_file.argtypes = (
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    )
    read_file.restype = wintypes.BOOL
    digest = hashlib.sha256()
    remaining = expected_size
    while remaining:
        requested = min(1024 * 1024, remaining)
        buffer = ctypes.create_string_buffer(requested)
        read = wintypes.DWORD()
        if not read_file(
            native_handle,
            buffer,
            requested,
            ctypes.byref(read),
            None,
        ):
            error = ctypes.get_last_error()
            raise OSError(error, ctypes.FormatError(error))
        if read.value == 0:
            raise ValueError("filesystem_verified_unlink_content_changed")
        digest.update(buffer.raw[: read.value])
        remaining -= read.value
    extra = ctypes.create_string_buffer(1)
    read = wintypes.DWORD()
    if not read_file(native_handle, extra, 1, ctypes.byref(read), None):
        error = ctypes.get_last_error()
        raise OSError(error, ctypes.FormatError(error))
    if read.value:
        raise ValueError("filesystem_verified_unlink_content_changed")
    return digest.hexdigest()


def _windows_handle_streams(descriptor: int) -> tuple[tuple[str, int], ...]:
    import msvcrt

    return _windows_native_handle_streams(msvcrt.get_osfhandle(descriptor))


def _windows_native_handle_streams(
    native_handle: int,
) -> tuple[tuple[str, int], ...]:
    import ctypes
    import struct

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    get_information = kernel32.GetFileInformationByHandleEx
    get_information.argtypes = (
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
    )
    get_information.restype = ctypes.c_int
    size = 4096
    while True:
        buffer = ctypes.create_string_buffer(size)
        if get_information(
            native_handle,
            7,
            buffer,
            size,
        ):
            break
        error = ctypes.get_last_error()
        if error == 38:
            return ()
        if error not in {122, 234} or size >= 1024 * 1024:
            raise OSError(
                error,
                "filesystem_stream_inventory_unavailable",
            )
        size *= 2

    payload = memoryview(buffer).cast("B")
    rows: list[tuple[str, int]] = []
    seen: set[str] = set()
    offset = 0
    while True:
        if offset % 8 or offset + 24 > size:
            raise ValueError("filesystem_stream_inventory_invalid")
        next_offset, name_length = struct.unpack_from("<II", payload, offset)
        stream_size = struct.unpack_from("<q", payload, offset + 8)[0]
        if (
            name_length == 0
            or name_length % 2
            or name_length > 64 * 1024
            or offset + 24 + name_length > size
            or stream_size < 0
            or stream_size > MAX_RUN_TOTAL_BYTES
        ):
            raise ValueError("filesystem_stream_inventory_invalid")
        try:
            name = bytes(payload[offset + 24 : offset + 24 + name_length]).decode(
                "utf-16-le",
                errors="strict",
            )
        except UnicodeDecodeError as error:
            raise ValueError("filesystem_stream_inventory_invalid") from error
        folded = name.casefold()
        if "\0" in name or folded in seen:
            raise ValueError("filesystem_stream_inventory_invalid")
        seen.add(folded)
        rows.append((name, stream_size))
        if next_offset == 0:
            return tuple(rows)
        minimum = (24 + name_length + 7) & ~7
        if next_offset < minimum or next_offset % 8 or offset + next_offset >= size:
            raise ValueError("filesystem_stream_inventory_invalid")
        offset += next_offset


def _set_windows_handle_delete(descriptor: int, *, delete: bool = True) -> None:
    _set_windows_native_handle_delete(descriptor, delete=delete)


def _set_windows_native_handle_delete(
    native_handle: int,
    *,
    delete: bool,
) -> None:
    import ctypes
    from ctypes import wintypes

    class FileDispositionInfo(ctypes.Structure):
        _fields_ = (("delete_file", wintypes.BOOLEAN),)

    info = FileDispositionInfo(1 if delete else 0)
    _set_windows_file_information(
        native_handle,
        4,
        ctypes.byref(info),
        ctypes.sizeof(info),
    )


def _clear_windows_native_handle_delete(native_handle: int) -> None:
    last_error: OSError | None = None
    for _attempt in range(3):
        try:
            _set_windows_native_handle_delete(native_handle, delete=False)
            return
        except OSError as error:
            last_error = error
    if last_error is None:
        raise OSError(errno.EIO, "filesystem_delete_cancel_failed")
    try:
        _set_windows_native_handle_delete_nt(native_handle, delete=False)
    except OSError as fallback_error:
        last_error.add_note(
            "NtSetInformationFile cancellation fallback failed: "
            f"{fallback_error!r}"
        )
        raise last_error


def _clear_windows_handle_delete(descriptor: int) -> None:
    _clear_windows_native_handle_delete(descriptor)


def _set_windows_native_handle_delete_nt(
    native_handle: int,
    *,
    delete: bool,
) -> None:
    import ctypes
    from ctypes import wintypes

    class IoStatusBlock(ctypes.Structure):
        _fields_ = (
            ("status", ctypes.c_void_p),
            ("information", ctypes.c_size_t),
        )

    class FileDispositionInformation(ctypes.Structure):
        _fields_ = (("delete_file", wintypes.BOOLEAN),)

    io_status = IoStatusBlock()
    information = FileDispositionInformation(1 if delete else 0)
    ntdll = ctypes.WinDLL("ntdll")
    set_information = ntdll.NtSetInformationFile
    set_information.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(IoStatusBlock),
        ctypes.c_void_p,
        wintypes.ULONG,
        ctypes.c_int,
    )
    set_information.restype = ctypes.c_long
    status = set_information(
        native_handle,
        ctypes.byref(io_status),
        ctypes.byref(information),
        ctypes.sizeof(information),
        13,
    )
    if status < 0:
        rtl_status_to_dos_error = ntdll.RtlNtStatusToDosError
        rtl_status_to_dos_error.argtypes = (ctypes.c_long,)
        rtl_status_to_dos_error.restype = wintypes.ULONG
        error = rtl_status_to_dos_error(status)
        raise OSError(error, ctypes.FormatError(error))


def _close_windows_native_handle(native_handle: int) -> None:
    try:
        _close_windows_handle_primary(native_handle)
        return
    except OSError as primary:
        try:
            _close_windows_handle_nt(native_handle)
            return
        except OSError as fallback:
            primary.add_note(f"NtClose fallback failed: {fallback!r}")
            raise


def _close_windows_handle_primary(native_handle: int) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL
    if close_handle(native_handle):
        return
    error = ctypes.get_last_error()
    raise OSError(error, ctypes.FormatError(error))


def _close_windows_handle_nt(native_handle: int) -> None:
    import ctypes
    from ctypes import wintypes

    ntdll = ctypes.WinDLL("ntdll")
    nt_close = ntdll.NtClose
    nt_close.argtypes = (wintypes.HANDLE,)
    nt_close.restype = ctypes.c_long
    status = nt_close(native_handle)
    if status >= 0:
        return
    rtl_status_to_dos_error = ntdll.RtlNtStatusToDosError
    rtl_status_to_dos_error.argtypes = (ctypes.c_long,)
    rtl_status_to_dos_error.restype = wintypes.ULONG
    error = rtl_status_to_dos_error(status)
    raise OSError(error, ctypes.FormatError(error))


def _quarantine_windows_native_handle(lease: _WindowsNativeHandleLease) -> None:
    lease.quarantined = True
    _QUARANTINED_WINDOWS_HANDLES.append(lease)


def _set_windows_file_information(
    handle: int,
    information_class: int,
    information: object,
    size: int,
) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    set_information = kernel32.SetFileInformationByHandle
    set_information.argtypes = (
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    )
    set_information.restype = wintypes.BOOL
    if not set_information(
        handle,
        information_class,
        information,
        size,
    ):
        error = ctypes.get_last_error()
        raise OSError(error, ctypes.FormatError(error))


def _windows_directory_chain(path: Path) -> tuple[Path, ...]:
    absolute = Path(path).absolute()
    current = Path(absolute.anchor)
    rows = [current]
    for part in absolute.parts[1:]:
        current /= part
        rows.append(current)
    return tuple(rows)


def _require_child_name(name: str) -> None:
    if (
        not isinstance(name, str)
        or not name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or "\x00" in name
    ):
        raise ValueError("filesystem_child_name_invalid")


class BoundedFilesystemPackageView:
    """Immutable no-follow snapshot with bounded physical inventory."""

    __slots__ = ("_directories", "_files", "_names")

    def __init__(
        self,
        *,
        files: dict[str, bytes],
        directories: tuple[str, ...],
    ) -> None:
        copied = {
            name: bytes(content)
            for name, content in sorted(files.items())
        }
        self._files = MappingProxyType(copied)
        self._names = tuple(copied)
        self._directories = tuple(sorted(directories))

    @property
    def directory_names(self) -> tuple[str, ...]:
        return self._directories

    def file_names(self) -> tuple[str, ...]:
        return self._names

    def read_bytes(self, relative_path: str) -> bytes:
        try:
            return self._files[canonical_relative_path(relative_path)]
        except KeyError as error:
            raise FileNotFoundError(relative_path) from error

    def read_json(self, relative_path: str) -> Any:
        return json.loads(self.read_bytes(relative_path).decode("utf-8"))

    def exists(self, relative_path: str) -> bool:
        try:
            path = canonical_relative_path(relative_path)
        except ValueError:
            return False
        return path in self._files


def path_lexists(path: Path) -> bool:
    return os.path.lexists(Path(path))


def status_is_reparse(status: os.stat_result) -> bool:
    return stat.S_ISLNK(status.st_mode) or bool(
        getattr(status, "st_file_attributes", 0) & _REPARSE_ATTRIBUTE
    )


def path_identity_from_status(status: os.stat_result) -> PathIdentity:
    return status.st_dev, status.st_ino, status.st_mode


def path_identity(path: Path) -> PathIdentity:
    return path_identity_from_status(Path(path).lstat())


def require_plain_directory(path: Path) -> None:
    status = Path(path).lstat()
    if not stat.S_ISDIR(status.st_mode) or status_is_reparse(status):
        raise ValueError("filesystem_directory_invalid")


def plain_file_status(path: Path) -> os.stat_result:
    status = Path(path).lstat()
    if (
        not stat.S_ISREG(status.st_mode)
        or status_is_reparse(status)
        or status.st_nlink != 1
    ):
        raise ValueError("filesystem_file_invalid")
    return status


def require_same_identity_resolution(
    path: Path,
    *,
    expected_status: os.stat_result | None = None,
) -> None:
    """Reject resolution changes except Windows aliases of the same inode."""

    candidate = Path(path)
    lexical_status = candidate.lstat()
    if (
        expected_status is not None
        and path_identity_from_status(lexical_status)
        != path_identity_from_status(expected_status)
    ):
        raise ValueError("filesystem_path_resolution_changed")
    if status_is_reparse(lexical_status):
        raise ValueError("filesystem_path_resolution_changed")
    resolved = candidate.resolve(strict=True)
    if resolved == candidate.absolute():
        return
    resolved_status = resolved.lstat()
    if (
        os.name != "nt"
        or status_is_reparse(resolved_status)
        or path_identity_from_status(resolved_status)
        != path_identity_from_status(lexical_status)
    ):
        raise ValueError("filesystem_path_resolution_changed")


def capture_plain_ancestor_guard(path: Path) -> FilesystemPathGuard:
    """Bind every currently existing lexical ancestor without following links."""

    absolute = Path(path).absolute()
    rows: list[tuple[Path, PathIdentity]] = []
    current = Path(absolute.anchor)
    parts = absolute.parts[1:]
    for index, part in enumerate(parts):
        current /= part
        if not path_lexists(current):
            break
        status = current.lstat()
        if status_is_reparse(status):
            raise ValueError("filesystem_ancestor_reparse")
        if index < len(parts) - 1 and not stat.S_ISDIR(status.st_mode):
            raise ValueError("filesystem_ancestor_not_directory")
        try:
            require_same_identity_resolution(
                current,
                expected_status=status,
            )
        except ValueError as error:
            raise ValueError(
                "filesystem_ancestor_resolution_changed"
            ) from error
        rows.append((current, path_identity_from_status(status)))
    guard = FilesystemPathGuard(tuple(rows))
    guard.validate()
    return guard


def read_file_no_follow(
    path: Path,
    *,
    expected_status: os.stat_result,
    maximum_size: int,
) -> bytes:
    if (
        not stat.S_ISREG(expected_status.st_mode)
        or status_is_reparse(expected_status)
        or expected_status.st_nlink != 1
        or expected_status.st_size > maximum_size
    ):
        raise ValueError("filesystem_file_invalid")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (
            _file_state(opened) != _file_state(expected_status)
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_size > maximum_size
        ):
            raise ValueError("filesystem_file_identity_changed")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            content = handle.read(opened.st_size + 1)
        after = os.fstat(descriptor)
        if (
            _file_state(after) != _file_state(opened)
            or after.st_nlink != 1
            or len(content) != after.st_size
        ):
            raise ValueError("filesystem_file_changed")
        return content
    finally:
        os.close(descriptor)


def snapshot_bounded_filesystem_package(
    root: Path,
) -> BoundedFilesystemPackageView:
    """Take one bounded no-follow snapshot and reject any physical ambiguity."""

    root = Path(root)
    require_plain_directory(root)
    root_identity = path_identity(root)
    pending = [(root, "", 0)]
    file_rows: list[tuple[str, Path, os.stat_result]] = []
    directories: list[str] = []
    directory_identities: list[tuple[Path, PathIdentity]] = [
        (root, root_identity)
    ]
    total_size = 0
    node_count = 0
    while pending:
        directory, prefix, depth = pending.pop()
        if depth > MAX_FILESYSTEM_DEPTH:
            raise ValueError("filesystem_tree_depth_limit")
        bounded_entries: list[os.DirEntry[str]] = []
        with os.scandir(directory) as iterator:
            for entry in iterator:
                if len(bounded_entries) >= MAX_FILESYSTEM_ENTRIES_PER_DIRECTORY:
                    raise ValueError("filesystem_directory_entry_limit")
                bounded_entries.append(entry)
        for entry in sorted(bounded_entries, key=lambda row: row.name):
            node_count += 1
            if node_count > MAX_FILESYSTEM_NODES:
                raise ValueError("filesystem_node_limit")
            child = Path(entry.path)
            status = child.lstat()
            if status_is_reparse(status) or entry.is_symlink():
                raise ValueError("filesystem_tree_reparse_forbidden")
            relative = f"{prefix}{entry.name}"
            if len(relative.encode("utf-8")) > MAX_RUN_PATH_BYTES:
                raise ValueError("filesystem_path_length_limit")
            if stat.S_ISDIR(status.st_mode):
                if len(directories) >= MAX_FILESYSTEM_DIRECTORIES:
                    raise ValueError("filesystem_directory_limit")
                canonical = canonical_relative_path(relative)
                if canonical != relative:
                    raise ValueError("filesystem_path_invalid")
                directories.append(relative)
                directory_identities.append(
                    (child, path_identity_from_status(status))
                )
                pending.append((child, f"{relative}/", depth + 1))
                continue
            if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
                raise ValueError("filesystem_tree_entry_invalid")
            canonical = canonical_relative_path(relative)
            if canonical != relative:
                raise ValueError("filesystem_path_invalid")
            if len(file_rows) >= MAX_RUN_FILES:
                raise ValueError("filesystem_file_limit")
            total_size += status.st_size
            if total_size > MAX_RUN_TOTAL_BYTES:
                raise ValueError("filesystem_total_size_limit")
            file_rows.append((relative, child, status))
    files = {
        relative: read_file_no_follow(
            path,
            expected_status=status,
            maximum_size=(
                MAX_MANIFEST_BYTES
                if relative == "package_manifest.json"
                else MAX_RUN_TOTAL_BYTES
            ),
        )
        for relative, path, status in file_rows
    }
    names_after, directories_after = _bounded_inventory(root)
    if (
        tuple(sorted(files)) != names_after
        or tuple(sorted(directories)) != directories_after
    ):
        raise ValueError("filesystem_tree_membership_changed")
    for directory, identity in directory_identities:
        if path_identity(directory) != identity:
            raise ValueError("filesystem_tree_identity_changed")
    return BoundedFilesystemPackageView(
        files=files,
        directories=tuple(directories),
    )


def _bounded_inventory(root: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    pending = [(root, "", 0)]
    files: list[str] = []
    directories: list[str] = []
    nodes = 0
    while pending:
        directory, prefix, depth = pending.pop()
        if depth > MAX_FILESYSTEM_DEPTH:
            raise ValueError("filesystem_tree_depth_limit")
        count = 0
        with os.scandir(directory) as iterator:
            for entry in iterator:
                count += 1
                nodes += 1
                if (
                    count > MAX_FILESYSTEM_ENTRIES_PER_DIRECTORY
                    or nodes > MAX_FILESYSTEM_NODES
                ):
                    raise ValueError("filesystem_tree_inventory_limit")
                child = Path(entry.path)
                status = child.lstat()
                if status_is_reparse(status) or entry.is_symlink():
                    raise ValueError("filesystem_tree_reparse_forbidden")
                relative = f"{prefix}{entry.name}"
                if len(relative.encode("utf-8")) > MAX_RUN_PATH_BYTES:
                    raise ValueError("filesystem_path_length_limit")
                if stat.S_ISDIR(status.st_mode):
                    directories.append(relative)
                    pending.append((child, f"{relative}/", depth + 1))
                elif stat.S_ISREG(status.st_mode):
                    files.append(relative)
                else:
                    raise ValueError("filesystem_tree_entry_invalid")
    return tuple(sorted(files)), tuple(sorted(directories))


def _file_state(
    status: os.stat_result,
    *,
    platform_name: str | None = None,
) -> tuple[int, int, int, int, int, int | None]:
    if platform_name is None:
        platform_name = os.name
    return (
        status.st_dev,
        status.st_ino,
        status.st_mode,
        status.st_size,
        status.st_mtime_ns,
        None if platform_name == "nt" else status.st_ctime_ns,
    )


def read_optional_profile(package: Path) -> dict[str, Any] | None:
    profile_path = package / "reports" / "globalvalues_profile.json"
    if not profile_path.exists():
        return None
    profile = read_json(profile_path)
    if not isinstance(profile, dict):
        raise ValueError(f"GlobalValues profile must be an object: {profile_path}")
    return profile


def read_required_baseline(package: Path) -> dict[str, Any]:
    baseline_path = package / "reports" / "globalvalues_baseline.json"
    if not baseline_path.exists():
        raise ValueError(f"Missing GlobalValues baseline report: {baseline_path}")
    baseline = read_json(baseline_path)
    if not isinstance(baseline, dict):
        raise ValueError(f"GlobalValues baseline must be an object: {baseline_path}")
    return baseline


def read_required_globalvalues_authority_matrix(
    package: Path,
) -> dict[str, Any]:
    matrix_path = package / "reports" / "global_values_authority_matrix.json"
    if not matrix_path.exists():
        raise ValueError(
            f"Missing GlobalValues authority matrix report: {matrix_path}"
        )
    matrix = read_json(matrix_path)
    if not isinstance(matrix, dict):
        raise ValueError(
            f"GlobalValues authority matrix must be an object: {matrix_path}"
        )
    return matrix


def prepare_research_output_dir(out: Path) -> None:
    if not out.exists():
        return
    if not out.is_dir():
        raise ValueError(f"Research output path exists and is not a directory: {out}")
    if list(out.iterdir()):
        raise ValueError(f"Refusing to overwrite non-empty research output directory: {out}")
