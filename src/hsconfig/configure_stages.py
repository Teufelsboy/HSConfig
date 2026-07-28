from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from types import MappingProxyType
from typing import Any, Callable


StageObserver = Callable[[str, str], None]


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
        _stage_payload(value),
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
    if observer is not None:
        observer(name, stage_digest(value))


def materialize_stage_value(value: Any) -> Any:
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
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_value(item) for item in value)
    return value


def _stage_payload(value: Any) -> Any:
    payload = materialize_stage_value(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {"stage_type": type(value).__name__, **payload}
    return payload


def _canonical_sort_key(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
