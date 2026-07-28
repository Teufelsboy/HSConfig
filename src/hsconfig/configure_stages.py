from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, cast


StageObserver = Callable[[str, str], None]
_MAPPING_PROXY_TYPE = type(MappingProxyType({}))
_MAX_STAGE_DEPTH = 128
_MISSING = object()


class _FrozenList(tuple):
    """Immutable list representation that retains the source collection type."""


@dataclass(frozen=True)
class VerifiedDeckStage:
    identity: Mapping[str, Any]
    cards: Sequence[Mapping[str, Any]]
    input_verification: Mapping[str, Any]


@dataclass(frozen=True)
class LoweredRuntimeStage:
    runtime_files: Mapping[str, Mapping[str, Any]]
    warnings: Sequence[Mapping[str, Any]]
    source_contract: Mapping[str, Any]


_STAGE_FIELDS = {
    VerifiedDeckStage: ("identity", "cards", "input_verification"),
    LoweredRuntimeStage: ("runtime_files", "warnings", "source_contract"),
}
_STAGE_MAPPING_FIELDS = {
    VerifiedDeckStage: ("identity", "input_verification"),
    LoweredRuntimeStage: ("runtime_files", "source_contract"),
}
_STAGE_MAPPING_SEQUENCE_FIELDS = {
    VerifiedDeckStage: ("cards",),
    LoweredRuntimeStage: ("warnings",),
}


def build_verified_deck_stage(
    *,
    identity: Mapping[str, Any],
    cards: Sequence[Mapping[str, Any]],
    input_verification: Mapping[str, Any],
) -> VerifiedDeckStage:
    stage = VerifiedDeckStage(identity, cards, input_verification)
    return cast(VerifiedDeckStage, _freeze_root(stage, path=""))


def build_lowered_runtime_stage(
    *,
    runtime_files: Mapping[str, Mapping[str, Any]],
    warnings: Sequence[Mapping[str, Any]],
    source_contract: Mapping[str, Any],
) -> LoweredRuntimeStage:
    stage = LoweredRuntimeStage(runtime_files, warnings, source_contract)
    return cast(LoweredRuntimeStage, _freeze_root(stage, path=""))


def stage_digest(value: Any) -> str:
    frozen = _freeze_root(value, path="$")
    return f"sha256:{_typed_canonical_value(frozen)}"


def observe_stage(
    observer: StageObserver | None,
    name: str,
    value: Any,
) -> None:
    if observer is None:
        return
    try:
        observer(name, stage_digest(value))
    except (Exception, SystemExit):
        # Stage observation is diagnostic only and must never control production.
        return


def materialize_stage_value(value: Any) -> Any:
    return _materialize_frozen_value(_freeze_root(value, path="$"))


def _freeze_root(value: Any, *, path: str) -> Any:
    return _freeze_value(value, path=path, depth=0, active={}, memo={}, allow_stage=True)


def _freeze_value(
    value: Any,
    *,
    path: str,
    depth: int,
    active: dict[int, str],
    memo: dict[int, tuple[Any, int]],
    allow_stage: bool = False,
) -> Any:
    _check_depth(path, depth)
    value_type = type(value)
    if value is None or value_type in {bool, int}:
        return value
    if value_type is str:
        _check_unicode_scalar_string(value, path)
        return value
    if value_type is float:
        if not math.isfinite(value):
            raise ValueError(
                f"Stage values must use finite floats at {path}; "
                f"received {value.hex()}"
            )
        return value

    is_stage = allow_stage and value_type in _STAGE_FIELDS
    is_mapping = value_type in {dict, _MAPPING_PROXY_TYPE}
    is_sequence = value_type in {list, tuple, _FrozenList}
    if not (is_stage or is_mapping or is_sequence):
        _raise_unsupported_value(value, path)

    cached = _enter_container(value, path=path, active=active, memo=memo)
    if cached is not _MISSING:
        frozen, height = cast(tuple[Any, int], cached)
        _check_depth(path, depth + height)
        return frozen
    try:
        if is_stage:
            field_names = _STAGE_FIELDS[value_type]
            frozen = value_type(
                **{
                    name: _freeze_value(
                        getattr(value, name),
                        path=_stage_field_path(path, name),
                        depth=depth,
                        active=active,
                        memo=memo,
                    )
                    for name in field_names
                }
            )
            height = max((_memo_height(getattr(value, name), memo) for name in field_names), default=0)
            _validate_stage_shape(frozen, path=path)
        elif is_mapping:
            entries: dict[str, Any] = {}
            height = 0
            for index, (key, item) in enumerate(value.items()):
                if type(key) is not str:
                    raise TypeError(
                        f"Stage mapping key at {path}[key#{index}] must be "
                        "exact builtins.str; "
                        f"received {_qualified_type_name(key)}"
                    )
                _check_unicode_scalar_string(key, f"{path}[key#{index}]")
                entries[key] = _freeze_value(
                    item,
                    path=_mapping_value_path(path, key),
                    depth=depth + 1,
                    active=active,
                    memo=memo,
                )
                height = max(height, 1 + _memo_height(item, memo))
            frozen = MappingProxyType(entries)
        else:
            items = tuple(
                _freeze_value(
                    item,
                    path=f"{path}[{index}]",
                    depth=depth + 1,
                    active=active,
                    memo=memo,
                )
                for index, item in enumerate(value)
            )
            height = max((1 + _memo_height(item, memo) for item in value), default=0)
            frozen = items if value_type is tuple else _FrozenList(items)
    finally:
        active.pop(id(value), None)
    memo[id(value)] = (frozen, height)
    return frozen


def _validate_stage_shape(value: Any, *, path: str) -> None:
    value_type = type(value)
    for name in _STAGE_MAPPING_FIELDS[value_type]:
        item = getattr(value, name)
        if type(item) is not _MAPPING_PROXY_TYPE:
            _raise_unsupported_value(item, _stage_field_path(path, name))
    for name in _STAGE_MAPPING_SEQUENCE_FIELDS[value_type]:
        item = getattr(value, name)
        item_path = _stage_field_path(path, name)
        if type(item) not in {tuple, _FrozenList}:
            _raise_unsupported_value(item, item_path)
        for index, row in enumerate(item):
            if type(row) is not _MAPPING_PROXY_TYPE:
                _raise_unsupported_value(row, f"{item_path}[{index}]")
    if value_type is LoweredRuntimeStage:
        for key, item in value.runtime_files.items():
            if type(item) is not _MAPPING_PROXY_TYPE:
                _raise_unsupported_value(
                    item,
                    _mapping_value_path(
                        _stage_field_path(path, "runtime_files"),
                        key,
                    ),
                )


def _materialize_frozen_value(
    value: Any,
    *,
    path: str = "$",
    depth: int = 0,
    memo: dict[int, Any] | None = None,
) -> Any:
    if memo is None:
        memo = {}
    _check_depth(path, depth)
    value_type = type(value)
    if value is None or value_type in {bool, int, float, str}:
        return value
    cached = memo.get(id(value), _MISSING)
    if cached is not _MISSING:
        return cached
    if value_type in _STAGE_FIELDS:
        result = {
            name: _materialize_frozen_value(
                getattr(value, name),
                path=_stage_field_path(path, name),
                depth=depth,
                memo=memo,
            )
            for name in _STAGE_FIELDS[value_type]
        }
    elif value_type is _MAPPING_PROXY_TYPE:
        result = {
            key: _materialize_frozen_value(
                item,
                path=_mapping_value_path(path, key),
                depth=depth + 1,
                memo=memo,
            )
            for key, item in value.items()
        }
    elif value_type in {_FrozenList, tuple}:
        result = [
            _materialize_frozen_value(
                item,
                path=f"{path}[{index}]",
                depth=depth + 1,
                memo=memo,
            )
            for index, item in enumerate(value)
        ]
    else:
        _raise_unsupported_value(value, path)
    memo[id(value)] = result
    return result


def _typed_canonical_value(
    value: Any,
    *,
    path: str = "$",
    depth: int = 0,
    memo: dict[int, str] | None = None,
) -> str:
    if memo is None:
        memo = {}
    _check_depth(path, depth)
    value_type = type(value)
    if value is None:
        return _digest_record({"kind": "null"})
    if value_type is bool:
        return _digest_record({"kind": "bool", "value": value})
    if value_type is int:
        return _digest_record({"kind": "int", "value": str(value)})
    if value_type is float:
        return _digest_record({"kind": "float", "value": value.hex()})
    if value_type is str:
        return _digest_record({"kind": "string", "value": value})
    cached = memo.get(id(value))
    if cached is not None:
        return cached
    if value_type in _STAGE_FIELDS:
        record = {
            "kind": "stage",
            "type": _qualified_type_name(value),
            "fields": [
                {
                    "name": name,
                    "digest": _typed_canonical_value(
                        getattr(value, name),
                        path=_stage_field_path(path, name),
                        depth=depth,
                        memo=memo,
                    ),
                }
                for name in _STAGE_FIELDS[value_type]
            ],
        }
    elif value_type is _MAPPING_PROXY_TYPE:
        record = {
            "kind": "mapping",
            "entries": [
                {
                    "key": key,
                    "digest": _typed_canonical_value(
                        value[key],
                        path=_mapping_value_path(path, key),
                        depth=depth + 1,
                        memo=memo,
                    ),
                }
                for key in sorted(value)
            ],
        }
    elif value_type in {_FrozenList, tuple}:
        record = {
            "kind": "list" if value_type is _FrozenList else "tuple",
            "items": [
                _typed_canonical_value(
                    item,
                    path=f"{path}[{index}]",
                    depth=depth + 1,
                    memo=memo,
                )
                for index, item in enumerate(value)
            ],
        }
    else:
        _raise_unsupported_value(value, path)
    digest = _digest_record(record)
    memo[id(value)] = digest
    return digest


def _enter_container(
    value: Any,
    *,
    path: str,
    active: dict[int, str],
    memo: dict[int, tuple[Any, int]],
) -> Any:
    identity = id(value)
    if identity in active:
        raise ValueError(
            "Stage values must be acyclic; "
            f"cycle detected at {path} (already active at {active[identity]})"
        )
    if identity in memo:
        return memo[identity]
    active[identity] = path
    return _MISSING


def _memo_height(value: Any, memo: dict[int, tuple[Any, int]]) -> int:
    completed = memo.get(id(value))
    return 0 if completed is None else completed[1]


def _check_depth(path: str, depth: int) -> None:
    if depth > _MAX_STAGE_DEPTH:
        raise ValueError(
            f"Stage value exceeds maximum depth {_MAX_STAGE_DEPTH} at {path}"
        )


def _check_unicode_scalar_string(value: str, path: str) -> None:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        codepoint = ord(value[error.start])
        message = (f"Stage string at {path} contains invalid Unicode surrogate "
                   f"U+{codepoint:04X} at index {error.start}")
        raise ValueError(message) from None


def _stage_field_path(path: str, field_name: str) -> str:
    return field_name if not path else f"{path}.{field_name}"


def _mapping_value_path(path: str, key: str) -> str:
    if key.isidentifier():
        return f"{path}.{key}"
    return f"{path}[{json.dumps(key, ensure_ascii=False)}]"


def _raise_unsupported_value(value: Any, path: str) -> None:
    raise TypeError(
        f"Stage value at {path} must use exact stage-domain types; "
        f"received {_qualified_type_name(value)}"
    )


def _qualified_type_name(value: Any) -> str:
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"


def _digest_record(record: dict[str, Any]) -> str:
    canonical = json.dumps(
        record, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
