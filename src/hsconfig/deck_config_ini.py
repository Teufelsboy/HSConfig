from __future__ import annotations

import ctypes
import errno
import hashlib
import os
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO

from hsconfig.atomic_io import FaultHook, atomic_write_bytes, no_fault
from hsconfig.package_io import (
    PlainDirectoryMutationGuard,
    capture_plain_ancestor_guard,
    hold_plain_directory,
    path_identity_from_status,
    secure_replace,
    secure_unlink,
    status_is_reparse,
)


_UTF8_BOM = b"\xef\xbb\xbf"
MAX_DECK_CONFIG_BYTES = 1024 * 1024
_MAX_NAME_LENGTH = 255
_PLATFORM_NAME = os.name
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


@dataclass(frozen=True, slots=True)
class DeckConfigSnapshot:
    path: Path
    existed: bool
    content: bytes | None
    sha256: str | None
    selected_config_dir: str | None


def read_deck_config(path: Path, *, deck_name: str) -> DeckConfigSnapshot:
    _validate_deck_name(deck_name)
    target = Path(path)
    try:
        ancestor_guard = capture_plain_ancestor_guard(target)
        with hold_plain_directory(target.parent) as parent:
            ancestor_guard.validate()
            try:
                content = _read_plain_file(target, parent=parent)
            except FileNotFoundError:
                ancestor_guard.validate()
                return DeckConfigSnapshot(target, False, None, None, None)
            ancestor_guard.validate()
    except ValueError as exc:
        if str(exc) in {
            "deck_config_ini_too_large",
            "deck_config_ini_unsafe_path",
        }:
            raise
        raise ValueError("deck_config_ini_unsafe_path") from exc
    except OSError as exc:
        raise ValueError("deck_config_ini_unsafe_path") from exc
    text, _has_bom = _decode(content)
    mappings = _mapping_values(text, deck_name)
    if len(mappings) > 1:
        raise ValueError("deck_config_ini_ambiguous_mapping")
    selected = mappings[0] if mappings else None
    if selected is not None:
        _validate_config_dir(selected)
    return DeckConfigSnapshot(
        path=target,
        existed=True,
        content=content,
        sha256=hashlib.sha256(content).hexdigest(),
        selected_config_dir=selected,
    )


def render_deck_config(
    snapshot: DeckConfigSnapshot,
    *,
    deck_name: str,
    config_dir: str,
) -> bytes:
    _validate_deck_name(deck_name)
    _validate_config_dir(config_dir)
    if snapshot.existed != (snapshot.content is not None):
        raise ValueError("deck_config_ini_invalid_snapshot")
    original = snapshot.content or b""
    text, has_bom = _decode(original)
    matches = _mapping_indexes(text, deck_name)
    if len(matches) > 1:
        raise ValueError("deck_config_ini_ambiguous_mapping")
    if matches:
        lines = _split_lines(text)
        index = matches[0]
        line, newline = lines[index]
        equals = line.index("=")
        old_value = line[equals + 1 :].strip()
        if old_value == config_dir:
            return original
        value_region = line[equals + 1 :]
        leading = value_region[: len(value_region) - len(value_region.lstrip(" \t"))]
        trailing = value_region[len(value_region.rstrip(" \t")) :]
        lines[index] = (
            line[: equals + 1] + leading + config_dir + trailing,
            newline,
        )
        rendered_text = "".join(line + newline for line, newline in lines)
    else:
        rendered_text = _insert_mapping(text, deck_name, config_dir)
    encoding = "utf-8-sig" if has_bom else "utf-8"
    return rendered_text.encode(encoding)


def replace_deck_config_if_unchanged(
    snapshot: DeckConfigSnapshot,
    content: bytes,
    *,
    fault_hook: FaultHook = no_fault,
) -> str:
    """Commit rendered bytes if the raw snapshot is still current.

    This is a low-level primitive. The caller must hold the shared
    ``.hsconfig/apply.lock`` for the full read/render/replace operation.
    Arbitrary non-cooperating editors are detected where observable but are
    outside the portable serialization guarantee.
    """

    target = snapshot.path
    if len(content) > MAX_DECK_CONFIG_BYTES:
        raise ValueError("deck_config_ini_too_large")
    _decode(content)
    try:
        ancestor_guard = capture_plain_ancestor_guard(target.parent)
        with hold_plain_directory(target.parent) as parent:
            ancestor_guard.validate()
            current = _current_bytes_or_none(target, parent=parent)
            if snapshot.existed:
                if (
                    snapshot.content is None
                    or snapshot.sha256 is None
                    or current != snapshot.content
                    or hashlib.sha256(current or b"").hexdigest()
                    != snapshot.sha256
                ):
                    raise RuntimeError("deck_config_ini_concurrent_change")
                if current == content:
                    ancestor_guard.validate()
                    return hashlib.sha256(content).hexdigest()

                def compare_and_swap_fault_hook(stage: str) -> None:
                    fault_hook(stage)
                    if stage == "before_replace" and _current_bytes_or_none(
                        target,
                        parent=parent,
                    ) != snapshot.content:
                        raise RuntimeError("deck_config_ini_concurrent_change")

                atomic_write_bytes(
                    target,
                    content,
                    fault_hook=compare_and_swap_fault_hook,
                )
            else:
                if snapshot.content is not None or snapshot.sha256 is not None:
                    raise ValueError("deck_config_ini_invalid_snapshot")
                if current is not None:
                    raise RuntimeError("deck_config_ini_concurrent_change")
                _atomic_create_if_absent(
                    target,
                    content,
                    parent=parent,
                    fault_hook=fault_hook,
                )
            committed = _current_bytes_or_none(target, parent=parent)
            if committed != content:
                raise RuntimeError("deck_config_ini_commit_verification_failed")
            ancestor_guard.validate()
    except ValueError as exc:
        if str(exc).startswith("deck_config_ini_"):
            raise
        raise ValueError("deck_config_ini_unsafe_path") from exc
    except OSError as exc:
        if _is_already_exists_error(exc):
            raise RuntimeError("deck_config_ini_concurrent_change") from exc
        raise ValueError("deck_config_ini_unsafe_path") from exc
    return hashlib.sha256(content).hexdigest()


def _decode(content: bytes) -> tuple[str, bool]:
    has_bom = content.startswith(_UTF8_BOM)
    try:
        return content.decode("utf-8-sig"), has_bom
    except UnicodeDecodeError as exc:
        raise ValueError("deck_config_ini_invalid_encoding") from exc


def _split_lines(text: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for row in text.splitlines(keepends=True):
        if row.endswith("\r\n"):
            rows.append((row[:-2], "\r\n"))
        elif row.endswith(("\r", "\n")):
            rows.append((row[:-1], row[-1]))
        else:
            rows.append((row, ""))
    if text == "":
        return []
    return rows


def _mapping_values(text: str, deck_name: str) -> list[str]:
    lines = _split_lines(text)
    return [lines[index][0].split("=", 1)[1].strip() for index in _mapping_indexes(text, deck_name)]


def _mapping_indexes(text: str, deck_name: str) -> list[int]:
    target = deck_name.casefold()
    in_configs = False
    matches: list[int] = []
    for index, (line, _newline) in enumerate(_split_lines(text)):
        stripped = line.strip()
        if _is_section(stripped):
            in_configs = stripped.casefold() == "[configs]"
            continue
        if (
            in_configs
            and stripped
            and not stripped.startswith((";", "#"))
            and "=" in line
            and line.split("=", 1)[0].strip().casefold() == target
        ):
            matches.append(index)
    return matches


def _insert_mapping(text: str, deck_name: str, config_dir: str) -> str:
    newline = _first_newline(text) or "\n"
    mapping = f"{deck_name} = {config_dir}"
    lines = _split_lines(text)
    configs_start: int | None = None
    configs_end: int | None = None
    in_configs = False
    for index, (line, _line_ending) in enumerate(lines):
        stripped = line.strip()
        if not _is_section(stripped):
            continue
        if in_configs:
            configs_end = index
            break
        if stripped.casefold() == "[configs]" and configs_start is None:
            configs_start = index
            in_configs = True
    if configs_start is not None:
        insertion = configs_end if configs_end is not None else len(lines)
        _insert_line(lines, insertion, mapping, newline, text.endswith(("\r", "\n")))
        return "".join(line + ending for line, ending in lines)
    if not text:
        return f"[CONFIGS]{newline}{mapping}"
    had_final_newline = text.endswith(("\r", "\n"))
    prefix = text if had_final_newline else text + newline
    suffix = newline if had_final_newline else ""
    return prefix + f"[CONFIGS]{newline}{mapping}" + suffix


def _insert_line(
    lines: list[tuple[str, str]],
    index: int,
    value: str,
    newline: str,
    original_had_final_newline: bool,
) -> None:
    if index < len(lines):
        lines.insert(index, (value, newline))
        return
    if not lines:
        lines.append((value, newline if original_had_final_newline else ""))
        return
    last_line, last_ending = lines[-1]
    if last_ending:
        lines.append((value, newline if original_had_final_newline else ""))
    else:
        lines[-1] = (last_line, newline)
        lines.append((value, ""))


def _first_newline(text: str) -> str | None:
    for index, character in enumerate(text):
        if character == "\r":
            return "\r\n" if text[index : index + 2] == "\r\n" else "\r"
        if character == "\n":
            return "\n"
    return None


def _is_section(value: str) -> bool:
    return len(value) >= 2 and value.startswith("[") and value.endswith("]")


def _validate_deck_name(value: str) -> None:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > _MAX_NAME_LENGTH
        or value.startswith((";", "#"))
        or any(character in value for character in "\r\n=\0")
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError("deck_config_ini_unsafe_deck_name")


def _validate_config_dir(value: str) -> None:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > _MAX_NAME_LENGTH
        or value in {".", ".."}
        or Path(value).name != value
        or any(character in value for character in '<>:"/\\|?*\0')
        or any(ord(character) < 32 for character in value)
        or value.endswith((".", " "))
        or value.split(".", 1)[0].upper() in _WINDOWS_RESERVED
    ):
        raise ValueError("deck_config_ini_unsafe_config_dir")


def _read_plain_file(
    path: Path,
    *,
    parent: PlainDirectoryMutationGuard,
) -> bytes:
    try:
        before = parent.child_status(path.name)
    except FileNotFoundError:
        raise
    except (OSError, ValueError) as exc:
        raise ValueError("deck_config_ini_unsafe_path") from exc
    if (
        not stat.S_ISREG(before.st_mode)
        or status_is_reparse(before)
        or before.st_nlink != 1
    ):
        raise ValueError("deck_config_ini_unsafe_path")
    if before.st_size > MAX_DECK_CONFIG_BYTES:
        raise ValueError("deck_config_ini_too_large")
    try:
        descriptor = parent.open_file(path.name, create=False, write=False)
    except (OSError, ValueError) as exc:
        raise ValueError("deck_config_ini_unsafe_path") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            _stable_file_state(opened) != _stable_file_state(before)
            or status_is_reparse(opened)
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_size > MAX_DECK_CONFIG_BYTES
        ):
            raise ValueError("deck_config_ini_unsafe_path")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            content = handle.read(MAX_DECK_CONFIG_BYTES + 1)
            after_descriptor = os.fstat(handle.fileno())
            if (
                _stable_file_state(after_descriptor)
                != _stable_file_state(opened)
                or status_is_reparse(after_descriptor)
                or not stat.S_ISREG(after_descriptor.st_mode)
                or after_descriptor.st_nlink != 1
                or len(content) != after_descriptor.st_size
            ):
                raise ValueError("deck_config_ini_unsafe_path")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(content) > MAX_DECK_CONFIG_BYTES:
        raise ValueError("deck_config_ini_too_large")
    try:
        after = parent.child_status(path.name)
    except (OSError, ValueError) as exc:
        raise ValueError("deck_config_ini_unsafe_path") from exc
    if (
        _stable_file_state(after) != _stable_file_state(opened)
        or status_is_reparse(after)
        or not stat.S_ISREG(after.st_mode)
        or after.st_nlink != 1
    ):
        raise ValueError("deck_config_ini_unsafe_path")
    parent.validate()
    return content


def _current_bytes_or_none(
    path: Path,
    *,
    parent: PlainDirectoryMutationGuard,
) -> bytes | None:
    try:
        return _read_plain_file(path, parent=parent)
    except FileNotFoundError:
        return None


def _atomic_create_if_absent(
    target: Path,
    content: bytes,
    *,
    parent: PlainDirectoryMutationGuard,
    fault_hook: FaultHook,
) -> None:
    parent_identity = parent.identity
    temp_path: Path | None = None
    temp_identity: tuple[int, int, int] | None = None
    handle: BinaryIO | None = None
    fault_hook("before_temp_write")
    try:
        for _ in range(100):
            candidate = target.with_name(
                f".{target.name}.{uuid.uuid4().hex}.tmp"
            )
            try:
                descriptor = parent.open_file(
                    candidate.name,
                    create=True,
                    write=True,
                )
            except FileExistsError:
                continue
            temp_path = candidate
            handle = os.fdopen(descriptor, "w+b")
            opened = os.fstat(handle.fileno())
            temp_identity = (opened.st_dev, opened.st_ino, opened.st_mode)
            break
        else:
            raise FileExistsError("deck_config_ini_temp_creation_failed")
        handle.write(content)
        fault_hook("after_temp_write")
        handle.flush()
        os.fsync(handle.fileno())
        fault_hook("after_temp_flush")
        handle.close()
        handle = None
        fault_hook("before_replace")
        parent.validate()
        try:
            _commit_owned_temp_no_replace(
                parent,
                temp_name=temp_path.name,
                target_name=target.name,
                expected_identity=temp_identity,
                expected_content=content,
                platform_name=_PLATFORM_NAME,
            )
            temp_path = None
            temp_identity = None
        except OSError as exc:
            if not _is_already_exists_error(exc):
                raise
            raise RuntimeError("deck_config_ini_concurrent_change") from exc
        fault_hook("after_replace")
        _flush_parent(parent)
        fault_hook("after_parent_flush")
    except BaseException as primary:
        if handle is not None:
            try:
                handle.close()
            except BaseException as cleanup_error:
                _add_note(primary, "temp handle close failed", cleanup_error)
        if temp_path is not None and temp_identity is not None:
            try:
                current_status = parent.child_status(temp_path.name)
                if path_identity_from_status(current_status) == temp_identity:
                    secure_unlink(
                        temp_path,
                        expected_identity=temp_identity,
                        expected_parent_identity=parent_identity,
                        missing_ok=True,
                    )
            except FileNotFoundError:
                pass
            except BaseException as cleanup_error:
                _add_note(primary, "owned temp cleanup failed", cleanup_error)
        raise


def _flush_parent(parent: PlainDirectoryMutationGuard) -> None:
    try:
        os.fsync(parent.descriptor)
    except OSError:
        pass


def _commit_owned_temp_no_replace(
    parent: PlainDirectoryMutationGuard,
    *,
    temp_name: str,
    target_name: str,
    expected_identity: tuple[int, int, int],
    expected_content: bytes,
    platform_name: str,
) -> None:
    _validate_owned_child(
        parent,
        name=temp_name,
        expected_identity=expected_identity,
        expected_content=expected_content,
        error_code="deck_config_ini_temp_identity_changed",
    )
    parent.validate()
    if platform_name == "nt":
        secure_replace(
            parent.path / temp_name,
            parent.path / target_name,
            expected_source_identity=expected_identity,
            expected_source_parent_identity=parent.identity,
            expected_target_parent_identity=parent.identity,
            expected_target_absent=True,
        )
    elif platform_name == "posix":
        _rename_noreplace_posix(
            parent.descriptor,
            temp_name,
            target_name,
        )
    else:
        raise RuntimeError("deck_config_ini_atomic_create_unsupported")
    parent.validate()
    _validate_owned_child(
        parent,
        name=target_name,
        expected_identity=expected_identity,
        expected_content=expected_content,
        error_code="deck_config_ini_commit_verification_failed",
    )


def _validate_owned_child(
    parent: PlainDirectoryMutationGuard,
    *,
    name: str,
    expected_identity: tuple[int, int, int],
    expected_content: bytes,
    error_code: str,
) -> None:
    try:
        status = parent.child_status(name)
        if (
            path_identity_from_status(status) != expected_identity
            or not stat.S_ISREG(status.st_mode)
            or status_is_reparse(status)
            or status.st_nlink != 1
            or status.st_size != len(expected_content)
        ):
            raise RuntimeError(error_code)
        actual = _read_plain_file(parent.path / name, parent=parent)
        final_status = parent.child_status(name)
        if (
            actual != expected_content
            or path_identity_from_status(final_status) != expected_identity
            or not stat.S_ISREG(final_status.st_mode)
            or status_is_reparse(final_status)
            or final_status.st_nlink != 1
        ):
            raise RuntimeError(error_code)
    except RuntimeError:
        raise
    except (OSError, ValueError) as exc:
        raise RuntimeError(error_code) from exc


def _rename_noreplace_posix(
    parent_descriptor: int,
    source_name: str,
    target_name: str,
) -> None:
    renameat2 = _load_renameat2()
    if renameat2 is None:
        raise RuntimeError("deck_config_ini_atomic_create_unsupported")
    ctypes.set_errno(0)
    result = renameat2(
        parent_descriptor,
        os.fsencode(source_name),
        parent_descriptor,
        os.fsencode(target_name),
        1,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number == errno.EEXIST:
        raise FileExistsError(error_number, os.strerror(error_number), target_name)
    unsupported = {
        errno.ENOSYS,
        errno.EINVAL,
        getattr(errno, "ENOTSUP", errno.EINVAL),
        getattr(errno, "EOPNOTSUPP", errno.EINVAL),
    }
    if error_number in unsupported:
        raise RuntimeError("deck_config_ini_atomic_create_unsupported")
    raise OSError(error_number, os.strerror(error_number), target_name)


def _load_renameat2() -> Any | None:
    try:
        function = ctypes.CDLL(None, use_errno=True).renameat2
    except (AttributeError, OSError):
        return None
    function.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    function.restype = ctypes.c_int
    return function


def _stable_file_state(status: os.stat_result) -> tuple[int, int, int, int, int]:
    identity = path_identity_from_status(status)
    return (
        identity[0],
        identity[1],
        identity[2],
        status.st_size,
        status.st_mtime_ns,
    )


def _is_already_exists_error(error: OSError) -> bool:
    return (
        isinstance(error, FileExistsError)
        or error.errno in {17, 80, 183}
        or getattr(error, "winerror", None) in {80, 183}
    )


def _add_note(
    primary: BaseException,
    operation: str,
    error: BaseException,
) -> None:
    try:
        primary.add_note(f"{operation}: {type(error).__name__}: {error}")
    except BaseException:
        pass
