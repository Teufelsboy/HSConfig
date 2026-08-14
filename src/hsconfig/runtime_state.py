from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from hsconfig.package_io import (
    PlainDirectoryMutationGuard,
    capture_plain_ancestor_guard,
    hold_plain_directory,
    path_identity_from_status,
    path_lexists,
    status_is_reparse,
)


_STATE_SCHEMA_VERSION = 1
_MAX_STATE_BYTES = 1024 * 1024
_MAX_DECKS = 1024
_MAX_NAME_LENGTH = 255
_LOWER_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
_STATE_KEYS = frozenset({"schema_version", "decks"})
_DECK_KEYS = frozenset(
    {
        "state_key",
        "deck_name",
        "config_dir",
        "package_root_sha256",
        "ini_sha256",
    }
)


@dataclass(frozen=True, slots=True)
class RuntimeDeckState:
    state_key: str
    deck_name: str
    config_dir: str
    package_root_sha256: str
    ini_sha256: str


@dataclass(frozen=True, slots=True)
class RuntimeState:
    schema_version: int
    decks: tuple[RuntimeDeckState, ...]


def serialize_runtime_state(state: RuntimeState) -> bytes:
    """Return the one canonical, deterministic representation of state.

    Runtime state is advisory recovery metadata. Its contents do not select a
    runtime configuration; the verified ``deck_config.ini`` mapping remains
    authoritative.
    """

    _validate_runtime_state(state)
    ordered_decks = sorted(
        state.decks,
        key=lambda deck: (deck.state_key.casefold(), deck.state_key),
    )
    payload = {
        "schema_version": state.schema_version,
        "decks": [asdict(deck) for deck in ordered_decks],
    }
    return (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def read_runtime_state(runtime_root: Path) -> RuntimeState | None:
    """Read strict advisory state without consulting runtime configuration."""

    root = Path(runtime_root)
    state_dir = root / ".hsconfig"
    state_path = state_dir / "state.json"
    try:
        ancestor_guard = capture_plain_ancestor_guard(state_path)
        if not path_lexists(state_dir):
            ancestor_guard.validate()
            return None
        with hold_plain_directory(state_dir) as parent:
            ancestor_guard.validate()
            try:
                raw = _read_plain_file(state_path, parent=parent)
            except FileNotFoundError:
                ancestor_guard.validate()
                return None
            ancestor_guard.validate()
    except ValueError as exc:
        if str(exc) == "runtime_state_too_large":
            raise
        if str(exc) == "runtime_state_unsafe_path":
            raise
        raise ValueError("runtime_state_unsafe_path") from exc
    except OSError as exc:
        raise ValueError("runtime_state_unsafe_path") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("runtime_state_invalid_encoding") from exc
    try:
        payload = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except _DuplicateJsonKeyError as exc:
        raise ValueError("runtime_state_duplicate_json_key") from exc
    except (json.JSONDecodeError, _InvalidJsonConstantError) as exc:
        raise ValueError("runtime_state_invalid_json") from exc
    state = _state_from_payload(payload)
    if serialize_runtime_state(state) != raw:
        raise ValueError("runtime_state_noncanonical")
    return state


class _DuplicateJsonKeyError(ValueError):
    pass


class _InvalidJsonConstantError(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKeyError(key)
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise _InvalidJsonConstantError(value)


def _state_from_payload(payload: object) -> RuntimeState:
    if not isinstance(payload, dict) or frozenset(payload) != _STATE_KEYS:
        raise ValueError("runtime_state_invalid_schema")
    schema_version = payload["schema_version"]
    deck_rows = payload["decks"]
    if (
        type(schema_version) is not int
        or schema_version != _STATE_SCHEMA_VERSION
        or not isinstance(deck_rows, list)
        or len(deck_rows) > _MAX_DECKS
    ):
        raise ValueError("runtime_state_invalid_schema")
    decks: list[RuntimeDeckState] = []
    for row in deck_rows:
        if not isinstance(row, dict) or frozenset(row) != _DECK_KEYS:
            raise ValueError("runtime_state_invalid_schema")
        if any(type(row[key]) is not str for key in _DECK_KEYS):
            raise ValueError("runtime_state_invalid_schema")
        decks.append(
            RuntimeDeckState(
                state_key=row["state_key"],
                deck_name=row["deck_name"],
                config_dir=row["config_dir"],
                package_root_sha256=row["package_root_sha256"],
                ini_sha256=row["ini_sha256"],
            )
        )
    state = RuntimeState(schema_version=schema_version, decks=tuple(decks))
    _validate_runtime_state(state)
    return state


def _validate_runtime_state(state: RuntimeState) -> None:
    if (
        not isinstance(state, RuntimeState)
        or type(state.schema_version) is not int
        or state.schema_version != _STATE_SCHEMA_VERSION
        or not isinstance(state.decks, tuple)
        or len(state.decks) > _MAX_DECKS
    ):
        raise ValueError("runtime_state_invalid_schema")
    seen_state_keys: set[str] = set()
    seen_deck_names: set[str] = set()
    for deck in state.decks:
        if not isinstance(deck, RuntimeDeckState):
            raise ValueError("runtime_state_invalid_schema")
        _validate_child_name(deck.state_key)
        _validate_deck_name(deck.deck_name)
        _validate_child_name(deck.config_dir)
        if (
            type(deck.package_root_sha256) is not str
            or not _LOWER_HEX_64.fullmatch(deck.package_root_sha256)
        ):
            raise ValueError("runtime_state_invalid_digest")
        if (
            type(deck.ini_sha256) is not str
            or not _LOWER_HEX_64.fullmatch(deck.ini_sha256)
        ):
            raise ValueError("runtime_state_invalid_digest")
        state_key = deck.state_key.casefold()
        deck_name = deck.deck_name.casefold()
        if state_key in seen_state_keys or deck_name in seen_deck_names:
            raise ValueError("runtime_state_duplicate_identity")
        seen_state_keys.add(state_key)
        seen_deck_names.add(deck_name)


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
        raise ValueError("runtime_state_unsafe_name")


def _validate_child_name(value: str) -> None:
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
        raise ValueError("runtime_state_unsafe_name")


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
        raise ValueError("runtime_state_unsafe_path") from exc
    if (
        status_is_reparse(before)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
    ):
        raise ValueError("runtime_state_unsafe_path")
    if before.st_size > _MAX_STATE_BYTES:
        raise ValueError("runtime_state_too_large")
    try:
        descriptor = parent.open_file(path.name, create=False, write=False)
    except (OSError, ValueError) as exc:
        raise ValueError("runtime_state_unsafe_path") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            _stable_file_state(opened) != _stable_file_state(before)
            or status_is_reparse(opened)
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_size > _MAX_STATE_BYTES
        ):
            raise ValueError("runtime_state_unsafe_path")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            raw = handle.read(_MAX_STATE_BYTES + 1)
            after_descriptor = os.fstat(handle.fileno())
            if (
                _stable_file_state(after_descriptor)
                != _stable_file_state(opened)
                or status_is_reparse(after_descriptor)
                or not stat.S_ISREG(after_descriptor.st_mode)
                or after_descriptor.st_nlink != 1
                or len(raw) != after_descriptor.st_size
            ):
                raise ValueError("runtime_state_unsafe_path")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    try:
        after = parent.child_status(path.name)
    except (OSError, ValueError) as exc:
        raise ValueError("runtime_state_unsafe_path") from exc
    if (
        _stable_file_state(after) != _stable_file_state(opened)
        or status_is_reparse(after)
        or not stat.S_ISREG(after.st_mode)
        or after.st_nlink != 1
    ):
        raise ValueError("runtime_state_unsafe_path")
    parent.validate()
    return raw


def _stable_file_state(status: os.stat_result) -> tuple[int, int, int, int, int]:
    identity = path_identity_from_status(status)
    return (
        identity[0],
        identity[1],
        identity[2],
        status.st_size,
        status.st_mtime_ns,
    )
