from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from types import MappingProxyType
from typing import Any, Callable


StageObserver = Callable[[str, str], None]


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
        identity=_freeze_mapping(identity),
        cards=tuple(_freeze_mapping(card) for card in cards),
        input_verification=_freeze_mapping(input_verification),
    )


def build_lowered_runtime_stage(
    *,
    runtime_files: Mapping[str, Mapping[str, Any]],
    warnings: Sequence[Mapping[str, Any]],
    source_contract: Mapping[str, Any],
) -> LoweredRuntimeStage:
    return LoweredRuntimeStage(
        runtime_files=_freeze_mapping(runtime_files),
        warnings=tuple(_freeze_mapping(warning) for warning in warnings),
        source_contract=_freeze_mapping(source_contract),
    )


def stage_digest(value: Any) -> str:
    canonical = json.dumps(
        _typed_canonical_value(value),
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
    if isinstance(value, _FrozenDataclass):
        return {
            field_name: materialize_stage_value(item)
            for field_name, item in value.field_values
        }
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: materialize_stage_value(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            key: materialize_stage_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [materialize_stage_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(
            (materialize_stage_value(item) for item in value),
            key=_canonical_sort_key,
        )
    return value


def _freeze_mapping(value: Mapping[Any, Any]) -> Mapping[Any, Any]:
    return MappingProxyType(
        {
            key: _freeze_value(item)
            for key, item in value.items()
        }
    )


def _freeze_value(value: Any) -> Any:
    if isinstance(value, _FrozenDataclass):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        value_type = type(value)
        return _FrozenDataclass(
            qualified_type=f"{value_type.__module__}.{value_type.__qualname__}",
            field_values=tuple(
                (field.name, _freeze_value(getattr(value, field.name)))
                for field in fields(value)
            ),
        )
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, list):
        return _FrozenList(_freeze_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, set):
        return _FrozenSet(_freeze_value(item) for item in value)
    if isinstance(value, frozenset):
        return frozenset(_freeze_value(item) for item in value)
    return value


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
    return _encoded_typed_value(_typed_canonical_value(value))
