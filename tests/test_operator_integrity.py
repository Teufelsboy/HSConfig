from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
import re
from types import CellType, CodeType, FunctionType, ModuleType
from typing import Any

import pytest

from hsconfig import operator_integrity


FunctionRow = tuple[
    FunctionType,
    CodeType,
    tuple[tuple[str, Any], ...],
    tuple[tuple[CellType, Any], ...],
    Any,
    Any,
    tuple[tuple[str, Any], ...],
]
Manifest = tuple[
    tuple[FunctionRow, ...],
    tuple[tuple[type[Any], tuple[tuple[str, Any], ...]], ...],
    tuple[tuple[Any, type[Any], tuple[tuple[str, Any, bool], ...]], ...],
]


def _primary() -> str:
    return "primary"


def _backup() -> str:
    return "backup"


def _other() -> str:
    return "other"


def _manifest(function: FunctionType) -> Manifest:
    row: FunctionRow = (
        function,
        function.__code__,
        (),
        (),
        function.__defaults__,
        function.__kwdefaults__,
        tuple(sorted((function.__kwdefaults__ or {}).items())),
    )
    return ((row,), (), ())


def _callable(
    *,
    primary_manifest: Manifest,
    backup_manifest: Manifest,
) -> operator_integrity._GuardedOperatorCallable:
    return operator_integrity._GuardedOperatorCallable(
        primary=_primary,
        backup=_backup,
        primary_bound=(),
        backup_bound=(),
        primary_manifest=primary_manifest,
        backup_manifest=backup_manifest,
        name="fixture",
        qualname="fixture",
        signature=operator_integrity.inspect_signature(_primary),
        annotations={},
    )


def _function_fault(
    function: FunctionType,
    *,
    code: CodeType | None = None,
    globals_: tuple[tuple[str, Any], ...] = (),
    closure: tuple[tuple[CellType, Any], ...] = (),
    defaults: Any = None,
    kwdefaults: Any = None,
    kwdefault_rows: tuple[tuple[str, Any], ...] = (),
) -> Manifest:
    row: FunctionRow = (
        function,
        code or function.__code__,
        globals_,
        closure,
        defaults,
        kwdefaults,
        kwdefault_rows,
    )
    return ((row,), (), ())


class _Fixture:
    member = "actual"

    def __init__(self) -> None:
        self.scalar = 2
        self.reference = object()


class _IntegrityMode(str, Enum):
    __module__ = "hsconfig.fixture"

    FIRST = "first"
    FIRST_ALIAS = "first"
    SECOND = "second"


class _IntegrityFeature:
    __module__ = "hsconfig.fixture"
    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    @property
    def value(self) -> str:
        return self._value

    @value.setter
    def value(self, value: str) -> None:
        self._value = value

    @value.deleter
    def value(self) -> None:
        self._value = "deleted"

    @classmethod
    def from_value(cls, value: str) -> _IntegrityFeature:
        return cls(value)

    @staticmethod
    def normalize(value: str) -> str:
        return value.strip().lower()


class _IntegrityTuple(tuple[str]):
    __module__ = "hsconfig.fixture"
    _fields = ("first",)

    def __new__(cls, first: str) -> _IntegrityTuple:
        return tuple.__new__(cls, (first,))


_IntegrityEmpty = type(
    "_IntegrityEmpty",
    (),
    {"__module__": "hsconfig.fixture"},
)


def _integrity_projection_probe(
    value: str,
    counter_type: type[Counter[str]] = Counter,
    empty_type: type[object] = _IntegrityEmpty,
) -> tuple[bool, int, type[_IntegrityMode], type[_IntegrityFeature], type[_IntegrityTuple], type[object]]:
    return (
        re.fullmatch(r"x+", value) is not None,
        counter_type("aba")["a"],
        _IntegrityMode,
        _IntegrityFeature,
        _IntegrityTuple,
        empty_type,
    )


_integrity_projection_probe.__module__ = "hsconfig.fixture"


@dataclass
class _IntegrityDataclass:
    scalar: str
    reference: object


def _primary_faults() -> list[tuple[str, Manifest]]:
    def with_keyword_default(*, flag: object = True) -> object:
        return flag

    closure_cell = CellType("actual")
    fixture = _Fixture()
    return [
        (
            "code",
            _function_fault(_primary, code=_other.__code__),
        ),
        (
            "defaults",
            _function_fault(_primary, defaults=()),
        ),
        (
            "kwdefaults-identity",
            _function_fault(_primary, kwdefaults={}),
        ),
        (
            "kwdefaults-length",
            _function_fault(
                with_keyword_default,
                defaults=with_keyword_default.__defaults__,
                kwdefaults=with_keyword_default.__kwdefaults__,
                kwdefault_rows=(),
            ),
        ),
        (
            "kwdefaults-value",
            _function_fault(
                with_keyword_default,
                defaults=with_keyword_default.__defaults__,
                kwdefaults=with_keyword_default.__kwdefaults__,
                kwdefault_rows=(("flag", object()),),
            ),
        ),
        (
            "global",
            _function_fault(
                _primary,
                globals_=(("missing_fixture_global", object()),),
            ),
        ),
        (
            "closure",
            _function_fault(
                _primary,
                closure=((closure_cell, object()),),
            ),
        ),
        (
            "class-member",
            ((), ((_Fixture, (("member", "expected"),)),), ()),
        ),
        (
            "instance-type",
            ((), (), ((fixture, dict, ()),)),
        ),
        (
            "instance-missing-attribute",
            ((), (), ((fixture, _Fixture, (("missing", None, True),)),)),
        ),
        (
            "instance-value",
            ((), (), ((fixture, _Fixture, (("scalar", 1, True),)),)),
        ),
        (
            "instance-identity",
            ((), (), ((fixture, _Fixture, (("reference", object(), False),)),)),
        ),
    ]


def test_stable_counter_supports_mapping_iterable_keywords_and_missing_keys() -> None:
    mapping_counter = operator_integrity._StableCounter({"a": "2"})
    assert mapping_counter == {"a": 2}
    mapping_counter.update({"a": 3, "b": 1}, c=4)
    assert mapping_counter == {"a": 5, "b": 1, "c": 4}

    iterable_counter = operator_integrity._StableCounter(["a", "a", "b"])
    iterable_counter.update([], b=2)
    assert iterable_counter == {"a": 2, "b": 3}
    assert iterable_counter["missing"] == 0


@pytest.mark.parametrize(
    ("fault_name", "primary_manifest"),
    _primary_faults(),
)
def test_guarded_callable_recovers_from_each_primary_manifest_fault(
    fault_name: str,
    primary_manifest: Manifest,
) -> None:
    guarded = _callable(
        primary_manifest=primary_manifest,
        backup_manifest=_manifest(_backup),
    )

    assert guarded() == "backup", fault_name


@pytest.mark.parametrize(
    ("fault_name", "backup_manifest"),
    _primary_faults(),
)
def test_guarded_callable_fails_closed_when_both_manifests_are_invalid(
    fault_name: str,
    backup_manifest: Manifest,
) -> None:
    guarded = _callable(
        primary_manifest=_function_fault(_primary, code=_other.__code__),
        backup_manifest=backup_manifest,
    )

    with pytest.raises(
        RuntimeError,
        match="operator_projection_integrity_failed",
    ):
        guarded()


def test_guarded_callable_metadata_is_read_only_and_hides_internal_state() -> None:
    guarded = _callable(
        primary_manifest=_manifest(_primary),
        backup_manifest=_manifest(_backup),
    )

    assert guarded() == "primary"
    assert guarded.__name__ == "fixture"
    assert guarded.__qualname__ == "fixture"
    assert dict(guarded.__annotations__) == {}
    with pytest.raises(AttributeError):
        getattr(guarded, "_GuardedOperatorCallable__state")
    with pytest.raises(TypeError, match="guarded_operator_callable_immutable"):
        guarded.extra = "forbidden"
    with pytest.raises(TypeError, match="guarded_operator_callable_immutable"):
        del guarded.extra
    with pytest.raises(
        TypeError,
        match="guarded_operator_callable_type_immutable",
    ):
        operator_integrity._GuardedOperatorCallable.extra = "forbidden"
    with pytest.raises(
        TypeError,
        match="guarded_operator_callable_type_immutable",
    ):
        del operator_integrity._GuardedOperatorCallable.extra


def test_integrity_bootstrap_dispatches_known_operations_and_rejects_unknown() -> None:
    def freezer(*args: object, **kwargs: object) -> object:
        return "freeze", args, kwargs

    def guard(*args: object, **kwargs: object) -> object:
        return "guard", args, kwargs

    assert operator_integrity._invoke_integrity_bootstrap(
        freezer,
        guard,
        "freeze",
        1,
        option=2,
    ) == ("freeze", (1,), {"option": 2})
    assert operator_integrity._invoke_integrity_bootstrap(
        freezer,
        guard,
        "guard",
        3,
    ) == ("guard", (3,), {})
    with pytest.raises(
        ValueError,
        match="unknown_operator_integrity_operation:other",
    ):
        operator_integrity._invoke_integrity_bootstrap(
            freezer,
            guard,
            "other",
        )


def test_protected_integrity_module_type_guards_only_the_capability_binding() -> None:
    capability = object()
    protected_type = operator_integrity._protected_integrity_module_type(capability)
    module = ModuleType("fixture_operator_integrity")
    module.__class__ = protected_type

    assert module._operator_integrity_bootstrap is capability
    module.ordinary = "value"
    assert module.ordinary == "value"
    del module.ordinary
    with pytest.raises(
        AttributeError,
        match="protected_operator_integrity_binding:_operator_integrity_bootstrap",
    ):
        module._operator_integrity_bootstrap = object()
    with pytest.raises(
        AttributeError,
        match="protected_operator_integrity_binding:_operator_integrity_bootstrap",
    ):
        del module._operator_integrity_bootstrap
    with pytest.raises(
        AttributeError,
        match="protected_operator_integrity_binding:__class__",
    ):
        module.__class__ = ModuleType


def test_frozen_operator_graph_projects_regex_counter_enum_and_class_behavior() -> None:
    (frozen_probe,) = operator_integrity._freeze_operator_function_graph(
        (_integrity_projection_probe,)
    )

    matched, count, mode_type, feature_type, tuple_type, empty_type = frozen_probe(
        "xxx"
    )
    assert matched is True
    assert count == 2
    assert mode_type is not _IntegrityMode
    assert mode_type.FIRST is mode_type.FIRST_ALIAS
    assert mode_type("first") is mode_type.FIRST
    assert mode_type.SECOND.value == "second"
    with pytest.raises(ValueError, match="not a valid _IntegrityMode"):
        mode_type("unknown")

    feature = feature_type.from_value(" Value ")
    assert feature_type.normalize(feature.value) == "value"
    feature.value = "changed"
    assert feature.value == "changed"
    del feature.value
    assert feature.value == "deleted"

    projected_tuple = tuple_type("one")
    assert projected_tuple.first == "one"
    assert empty_type is _IntegrityEmpty


def test_dependency_manifest_deduplicates_recursive_containers_and_instances() -> None:
    recursive_mapping: dict[str, object] = {}
    recursive_mapping["self"] = recursive_mapping
    repeated_tuple = ("one",)
    repeated_dataclass = _IntegrityDataclass("value", object())

    functions, classes, instances = operator_integrity._function_dependency_manifest(
        recursive_mapping,
        recursive_mapping,
        repeated_tuple,
        repeated_tuple,
        repeated_dataclass,
        repeated_dataclass,
    )

    function_names = [row[0].__name__ for row in functions]
    assert sorted(function_names) == ["__eq__", "__init__", "__repr__", "__repr__"]
    assert len(classes) == 1
    assert classes[0][0] is _IntegrityDataclass
    assert len(instances) == 1
    instance, instance_type, fields = instances[0]
    assert instance is repeated_dataclass
    assert instance_type is _IntegrityDataclass
    assert fields[0] == ("reference", repeated_dataclass.reference, False)
    assert fields[1] == ("scalar", "value", True)
