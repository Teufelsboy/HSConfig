from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, fields, is_dataclass
from types import MappingProxyType
from typing import Any, Callable, Iterator


StageObserver = Callable[[str, str], None]
_MAPPING_PROXY_TYPE = type(MappingProxyType({}))


class _FrozenList(tuple):
    """Immutable list representation that retains the source collection type."""


class _FrozenSet(frozenset):
    """Immutable set representation that remains distinct from frozenset."""


@dataclass(frozen=True)
class _FrozenDataclass(Mapping[str, Any]):
    qualified_type: str
    field_values: tuple[tuple[str, Any], ...]

    def __getitem__(self, key: str) -> Any:
        for field_name, value in self.field_values:
            if field_name == key:
                return value
        raise KeyError(key)

    def __iter__(self):
        return (field_name for field_name, _value in self.field_values)

    def __len__(self) -> int:
        return len(self.field_values)


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


def build_verified_deck_stage(
    *,
    identity: Mapping[str, Any],
    cards: Sequence[Mapping[str, Any]],
    input_verification: Mapping[str, Any],
) -> VerifiedDeckStage:
    return VerifiedDeckStage(
        identity=_freeze_mapping(identity, path="identity"),
        cards=tuple(
            _freeze_mapping(card, path=f"cards[{index}]")
            for index, card in enumerate(cards)
        ),
        input_verification=_freeze_mapping(
            input_verification,
            path="input_verification",
        ),
    )


def build_lowered_runtime_stage(
    *,
    runtime_files: Mapping[str, Mapping[str, Any]],
    warnings: Sequence[Mapping[str, Any]],
    source_contract: Mapping[str, Any],
) -> LoweredRuntimeStage:
    return LoweredRuntimeStage(
        runtime_files=_freeze_mapping(runtime_files, path="runtime_files"),
        warnings=tuple(
            _freeze_mapping(warning, path=f"warnings[{index}]")
            for index, warning in enumerate(warnings)
        ),
        source_contract=_freeze_mapping(
            source_contract,
            path="source_contract",
        ),
    )


def stage_digest(value: Any) -> str:
    frozen_value = _freeze_value(value, path="$", active={})
    canonical = json.dumps(
        _typed_canonical_value(frozen_value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


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
    return _materialize_frozen_value(
        _freeze_value(value, path="$", active={})
    )


def _materialize_frozen_value(value: Any) -> Any:
    if isinstance(value, _FrozenDataclass):
        return {
            field_name: _materialize_frozen_value(item)
            for field_name, item in value.field_values
        }
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _materialize_frozen_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            key: _materialize_frozen_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [_materialize_frozen_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(
            (_materialize_frozen_value(item) for item in value),
            key=_canonical_sort_key,
        )
    return value


def _freeze_mapping(
    value: Mapping[Any, Any],
    *,
    path: str,
) -> Mapping[Any, Any]:
    frozen = _freeze_value(value, path=path, active={})
    if not isinstance(frozen, Mapping):
        raise TypeError(
            f"Stage value at {path} must be a supported mapping; "
            f"received {_qualified_type_name(value)}"
        )
    return frozen


def _freeze_value(
    value: Any,
    *,
    path: str,
    active: dict[int, str],
) -> Any:
    value_type = type(value)
    if value is None or value_type in {bool, int, str, bytes}:
        return value
    if value_type is float:
        if not math.isfinite(value):
            raise ValueError(
                f"Stage values must use finite floats at {path}; "
                f"received {value.hex()}"
            )
        return value
    if isinstance(value, _FrozenDataclass):
        with _active_value(value, path=path, active=active):
            return _FrozenDataclass(
                qualified_type=value.qualified_type,
                field_values=tuple(
                    (
                        field_name,
                        _freeze_value(
                            item,
                            path=f"{path}.{field_name}",
                            active=active,
                        ),
                    )
                    for field_name, item in value.field_values
                ),
            )
    if is_dataclass(value) and not isinstance(value, type):
        with _active_value(value, path=path, active=active):
            return _FrozenDataclass(
                qualified_type=_qualified_type_name(value),
                field_values=tuple(
                    (
                        field.name,
                        _freeze_value(
                            getattr(value, field.name),
                            path=f"{path}.{field.name}",
                            active=active,
                        ),
                    )
                    for field in fields(value)
                ),
            )
    if value_type in {dict, _MAPPING_PROXY_TYPE}:
        with _active_value(value, path=path, active=active):
            frozen_entries = []
            for index, (key, item) in enumerate(value.items()):
                frozen_key = _freeze_value(
                    key,
                    path=f"{path}[key#{index}]",
                    active=active,
                )
                frozen_item = _freeze_value(
                    item,
                    path=_mapping_value_path(path, key, index),
                    active=active,
                )
                frozen_entries.append((frozen_key, frozen_item))
            return MappingProxyType(dict(frozen_entries))
    if value_type is list:
        with _active_value(value, path=path, active=active):
            return _FrozenList(
                _freeze_value(
                    item,
                    path=f"{path}[{index}]",
                    active=active,
                )
                for index, item in enumerate(value)
            )
    if value_type is _FrozenList:
        with _active_value(value, path=path, active=active):
            return _FrozenList(
                _freeze_value(
                    item,
                    path=f"{path}[{index}]",
                    active=active,
                )
                for index, item in enumerate(value)
            )
    if value_type is tuple:
        with _active_value(value, path=path, active=active):
            return tuple(
                _freeze_value(
                    item,
                    path=f"{path}[{index}]",
                    active=active,
                )
                for index, item in enumerate(value)
            )
    if value_type is set:
        with _active_value(value, path=path, active=active):
            return _FrozenSet(
                _freeze_value(
                    item,
                    path=f"{path}[item#{index}]",
                    active=active,
                )
                for index, item in enumerate(value)
            )
    if value_type is _FrozenSet:
        with _active_value(value, path=path, active=active):
            return _FrozenSet(
                _freeze_value(
                    item,
                    path=f"{path}[item#{index}]",
                    active=active,
                )
                for index, item in enumerate(value)
            )
    if value_type is frozenset:
        with _active_value(value, path=path, active=active):
            return frozenset(
                _freeze_value(
                    item,
                    path=f"{path}[item#{index}]",
                    active=active,
                )
                for index, item in enumerate(value)
            )
    raise TypeError(
        f"Stage values must use supported canonical types at {path}; "
        f"received {_qualified_type_name(value)}"
    )


@contextmanager
def _active_value(
    value: Any,
    *,
    path: str,
    active: dict[int, str],
) -> Iterator[None]:
    identity = id(value)
    if identity in active:
        raise ValueError(
            "Stage values must be acyclic; "
            f"cycle detected at {path} (already active at {active[identity]})"
        )
    active[identity] = path
    try:
        yield
    finally:
        active.pop(identity, None)


def _mapping_value_path(path: str, key: Any, index: int) -> str:
    if type(key) is str and key.isidentifier():
        return f"{path}.{key}"
    return f"{path}[value#{index}]"


def _qualified_type_name(value: Any) -> str:
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"


def _typed_canonical_value(value: Any) -> dict[str, Any]:
    if isinstance(value, _FrozenDataclass):
        return {
            "kind": "dataclass",
            "type": value.qualified_type,
            "fields": [
                {
                    "name": field_name,
                    "value": _typed_canonical_value(item),
                }
                for field_name, item in value.field_values
            ],
        }
    if is_dataclass(value) and not isinstance(value, type):
        value_type = type(value)
        return {
            "kind": "dataclass",
            "type": f"{value_type.__module__}.{value_type.__qualname__}",
            "fields": [
                {
                    "name": field.name,
                    "value": _typed_canonical_value(getattr(value, field.name)),
                }
                for field in fields(value)
            ],
        }
    if isinstance(value, Mapping):
        entries = [
            {
                "key": _typed_canonical_value(key),
                "value": _typed_canonical_value(item),
            }
            for key, item in value.items()
        ]
        entries.sort(key=lambda entry: _encoded_typed_value(entry["key"]))
        return {"kind": "mapping", "entries": entries}
    if isinstance(value, _FrozenList):
        return {
            "kind": "list",
            "items": [_typed_canonical_value(item) for item in value],
        }
    if isinstance(value, tuple):
        return {
            "kind": "tuple",
            "items": [_typed_canonical_value(item) for item in value],
        }
    if isinstance(value, list):
        return {
            "kind": "list",
            "items": [_typed_canonical_value(item) for item in value],
        }
    if isinstance(value, _FrozenSet):
        items = [_typed_canonical_value(item) for item in value]
        items.sort(key=_encoded_typed_value)
        return {"kind": "set", "items": items}
    if isinstance(value, frozenset):
        items = [_typed_canonical_value(item) for item in value]
        items.sort(key=_encoded_typed_value)
        return {"kind": "frozenset", "items": items}
    if isinstance(value, set):
        items = [_typed_canonical_value(item) for item in value]
        items.sort(key=_encoded_typed_value)
        return {"kind": "set", "items": items}
    if value is None:
        return {"kind": "null"}
    if isinstance(value, bool):
        return {"kind": "bool", "value": value}
    if isinstance(value, int):
        return {"kind": "int", "value": str(value)}
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(
                "Stage values must use finite floats at canonical digest; "
                f"received {value.hex()}"
            )
        return {"kind": "float", "value": value.hex()}
    if isinstance(value, str):
        return {"kind": "string", "value": value}
    if isinstance(value, bytes):
        return {"kind": "bytes", "value": value.hex()}
    raise TypeError(
        "Stage values must use supported canonical types; "
        f"received {type(value).__module__}.{type(value).__qualname__}"
    )


def _encoded_typed_value(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _canonical_sort_key(value: Any) -> str:
    frozen_value = _freeze_value(value, path="$", active={})
    return _encoded_typed_value(_typed_canonical_value(frozen_value))
