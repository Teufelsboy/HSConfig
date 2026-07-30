from __future__ import annotations

import builtins
from collections import Counter, namedtuple
from collections.abc import Mapping, Sequence
import hashlib
import json
import re
import sys
from enum import EnumType
from inspect import Signature, signature as inspect_signature
from types import (
    CellType,
    CodeType,
    FunctionType,
    MappingProxyType,
    MemberDescriptorType,
    ModuleType,
)
from typing import Any

class _StableCounter(dict[Any, int]):
    def __init__(
        self,
        values: Any = (),
        _dict_init: Any = dict.__init__,
    ) -> None:
        _dict_init(self)
        self.update(values)

    def __missing__(self, key: Any) -> int:
        return 0

    def update(
        self,
        values: Any = (),
        *,
        _dict_type: type[dict[Any, Any]] = dict,
        _int_type: type[int] = int,
        **keywords: int,
    ) -> None:
        is_mapping = values.__class__ is _dict_type
        iterator = values.items() if is_mapping else values
        if is_mapping:
            for key, count in iterator:
                self[key] = self.get(key, 0) + _int_type(count)
        else:
            for key in iterator:
                self[key] = self.get(key, 0) + 1
        for key, count in keywords.items():
            self[key] = self.get(key, 0) + _int_type(count)


def _referenced_global_names(code: CodeType) -> frozenset[str]:
    names = set(code.co_names)
    for value in code.co_consts:
        if isinstance(value, CodeType):
            names.update(_referenced_global_names(value))
    return frozenset(names)


def _freeze_operator_function_graph(
    roots: tuple[FunctionType, ...],
) -> tuple[FunctionType, ...]:
    """Clone the complete reachable HSConfig evaluator graph."""

    private_builtins = MappingProxyType(dict(vars(builtins)))
    stable_sha256 = hashlib.sha256
    receipt_sha256_pattern = re.compile(
        r"sha256:[0-9a-f]{64}"
    )
    original_fullmatch = re.fullmatch

    def stable_fullmatch(pattern: Any, value: Any, flags: int = 0) -> Any:
        if (
            pattern == r"sha256:[0-9a-f]{64}"
            and flags == 0
        ):
            return receipt_sha256_pattern.fullmatch(value)
        return original_fullmatch(pattern, value, flags)

    stable_hashlib = namedtuple(
        "_StableHashlib",
        ("sha256",),
    )(stable_sha256)
    stable_re = namedtuple(
        "_StableRegex",
        ("compile", "fullmatch"),
    )(re.compile, stable_fullmatch)
    stable_json = namedtuple(
        "_StableJson",
        ("dumps",),
    )(json.dumps)
    stable_mapping_types = (dict, MappingProxyType)
    stable_sequence_types = (list, tuple)
    stable_tuple_getitem = tuple.__getitem__
    stable_string_type = str
    stable_value_error = ValueError
    namespaces: dict[int, dict[str, Any]] = {}
    functions: dict[int, FunctionType] = {}
    classes: dict[int, type[Any]] = {}
    cells: dict[int, CellType] = {}

    class _StableMappingMeta(type):
        def __instancecheck__(self, value: Any) -> bool:
            return value.__class__ in stable_mapping_types

    class _StableSequenceMeta(type):
        def __instancecheck__(self, value: Any) -> bool:
            return value.__class__ in stable_sequence_types

    class _StableMapping(metaclass=_StableMappingMeta):
        pass

    class _StableSequence(metaclass=_StableSequenceMeta):
        pass

    def freeze_value(value: Any) -> Any:
        if isinstance(value, FunctionType):
            if value.__module__.startswith("hsconfig."):
                return freeze_function(value)
            return value
        if isinstance(value, type):
            if value is Counter:
                return _StableCounter
            if value.__module__.startswith("hsconfig."):
                return freeze_class(value)
            return value
        value_type = value.__class__
        if value_type is dict or value_type is MappingProxyType:
            return MappingProxyType(
                {
                    freeze_value(key): freeze_value(nested)
                    for key, nested in value.items()
                }
            )
        if value_type is list:
            return tuple(freeze_value(item) for item in value)
        if value_type is tuple:
            return tuple(freeze_value(item) for item in value)
        if value_type is set:
            return frozenset(freeze_value(item) for item in value)
        if value_type is frozenset:
            return frozenset(freeze_value(item) for item in value)
        value_class = value.__class__
        dataclass_fields = getattr(value_class, "__dataclass_fields__", None)
        if (
            isinstance(dataclass_fields, dict)
            and value_class.__module__.startswith("hsconfig.")
        ):
            frozen_class = freeze_class(value_class)
            return frozen_class(
                **{
                    name: freeze_value(getattr(value, name))
                    for name in dataclass_fields
                }
            )
        if isinstance(value, ModuleType) and value.__name__ == "hashlib":
            return stable_hashlib
        if isinstance(value, ModuleType) and value.__name__ == "re":
            return stable_re
        if isinstance(value, ModuleType) and value.__name__ == "json":
            return stable_json
        return value

    def freeze_cell(cell: CellType) -> CellType:
        existing = cells.get(id(cell))
        if existing is not None:
            return existing
        try:
            frozen = CellType(freeze_value(cell.cell_contents))
        except ValueError:
            frozen = CellType()
        cells[id(cell)] = frozen
        return frozen

    def freeze_enum(enum_type: EnumType) -> type[str]:
        projected_values: tuple[str, ...] = ()

        def __new__(class_: type[str], value: Any) -> str:
            for projected in projected_values:
                if projected == value:
                    return projected
            raise stable_value_error(
                f"{value!r} is not a valid {enum_type.__name__}"
            )

        projected = type(
            enum_type.__name__,
            (str,),
            {
                "__module__": enum_type.__module__,
                "__slots__": (),
                "__new__": __new__,
                "value": property(lambda self: stable_string_type(self)),
            },
        )
        projected.__qualname__ = enum_type.__qualname__
        by_value: dict[str, str] = {}
        for name, member in enum_type.__members__.items():
            member_value = stable_string_type(member.value)
            enum_member = by_value.get(member_value)
            if enum_member is None:
                enum_member = str.__new__(projected, member_value)
                by_value[member_value] = enum_member
            type.__setattr__(projected, name, enum_member)
        projected_values = tuple(by_value.values())
        return projected

    def freeze_class(class_: type[Any]) -> type[Any]:
        existing = classes.get(id(class_))
        if existing is not None:
            return existing
        if isinstance(class_, EnumType) and issubclass(class_, str):
            frozen_enum = freeze_enum(class_)
            classes[id(class_)] = frozen_enum
            return frozen_enum
        if type(class_) is not type:
            return class_
        members = {
            name: value
            for name, value in class_.__dict__.items()
            if isinstance(
                value,
                (FunctionType, MemberDescriptorType, property),
            )
            or isinstance(value, (classmethod, staticmethod))
        }
        if not members:
            return class_
        classes[id(class_)] = class_
        frozen_members: dict[str, Any] = {}
        for name, member in members.items():
            if isinstance(member, FunctionType):
                frozen_members[name] = freeze_function(member)
            elif isinstance(member, MemberDescriptorType):
                frozen_members[name] = member
            elif isinstance(member, property):
                frozen_members[name] = property(
                    freeze_function(member.fget)
                    if isinstance(member.fget, FunctionType)
                    else member.fget,
                    freeze_function(member.fset)
                    if isinstance(member.fset, FunctionType)
                    else member.fset,
                    freeze_function(member.fdel)
                    if isinstance(member.fdel, FunctionType)
                    else member.fdel,
                    member.__doc__,
                )
            elif isinstance(member, classmethod):
                frozen_members[name] = classmethod(
                    freeze_function(member.__func__)
                )
            else:
                frozen_members[name] = staticmethod(
                    freeze_function(member.__func__)
                )
        if issubclass(class_, tuple):
            for index, field_name in enumerate(
                getattr(class_, "_fields", ()),
            ):
                frozen_members[field_name] = property(
                    lambda self, index=index, getitem=stable_tuple_getitem: (
                        getitem(self, index)
                    )
                )
        frozen = type(
            class_.__name__,
            (class_,),
            {
                "__module__": class_.__module__,
                "__slots__": (),
                **frozen_members,
            },
        )
        frozen.__qualname__ = class_.__qualname__
        classes[id(class_)] = frozen
        for namespace in namespaces.values():
            for name, value in tuple(namespace.items()):
                if value is class_:
                    namespace[name] = frozen
        return frozen

    def freeze_function(function: FunctionType) -> FunctionType:
        existing = functions.get(id(function))
        if existing is not None:
            return existing
        source_globals = function.__globals__
        frozen_globals = namespaces.get(id(source_globals))
        if frozen_globals is None:
            frozen_globals = dict(source_globals)
            frozen_globals["__builtins__"] = private_builtins
            namespaces[id(source_globals)] = frozen_globals
        frozen_closure = (
            tuple(freeze_cell(cell) for cell in function.__closure__)
            if function.__closure__ is not None
            else None
        )
        frozen = FunctionType(
            function.__code__,
            frozen_globals,
            function.__name__,
            freeze_value(function.__defaults__),
            frozen_closure,
        )
        functions[id(function)] = frozen
        frozen_kwdefaults = freeze_value(function.__kwdefaults__)
        frozen.__kwdefaults__ = (
            dict(frozen_kwdefaults)
            if frozen_kwdefaults is not None
            else None
        )
        frozen.__annotations__ = dict(function.__annotations__)
        frozen.__dict__.update(function.__dict__)
        frozen.__doc__ = function.__doc__
        frozen.__module__ = function.__module__
        frozen.__qualname__ = function.__qualname__
        for name in _referenced_global_names(function.__code__):
            if name not in source_globals:
                continue
            dependency = source_globals.get(name)
            if dependency is Mapping:
                frozen_globals[name] = _StableMapping
            elif dependency is Sequence:
                frozen_globals[name] = _StableSequence
            elif dependency is Counter:
                frozen_globals[name] = _StableCounter
            else:
                frozen_globals[name] = freeze_value(dependency)
        return frozen

    return tuple(freeze_function(root) for root in roots)


def _function_dependency_manifest(
    *roots: Any,
) -> tuple[
    tuple[
        tuple[
            FunctionType,
            CodeType,
            tuple[tuple[str, Any], ...],
            tuple[tuple[CellType, Any], ...],
            Any,
            Any,
            tuple[tuple[str, Any], ...],
        ],
        ...,
    ],
    tuple[
        tuple[
            type[Any],
            tuple[tuple[str, Any], ...],
        ],
        ...,
    ],
    tuple[
        tuple[
            Any,
            type[Any],
            tuple[tuple[str, Any, bool], ...],
        ],
        ...,
    ],
]:
    """Capture an immutable identity manifest for reachable functions."""

    pending = list(roots)
    seen_functions: set[int] = set()
    seen_classes: set[int] = set()
    function_rows: list[
        tuple[
            FunctionType,
            CodeType,
            tuple[tuple[str, Any], ...],
            tuple[tuple[CellType, Any], ...],
            Any,
            Any,
            tuple[tuple[str, Any], ...],
        ]
    ] = []
    class_rows: list[
        tuple[
            type[Any],
            tuple[tuple[str, Any], ...],
        ]
    ] = []
    instance_rows: list[
        tuple[
            Any,
            type[Any],
            tuple[tuple[str, Any, bool], ...],
        ]
    ] = []
    seen_values: set[int] = set()

    def queue(value: Any) -> None:
        if isinstance(value, FunctionType):
            pending.append(value)
            return
        if isinstance(value, type):
            class_id = id(value)
            if class_id in seen_classes:
                return
            seen_classes.add(class_id)
            guarded_members: list[tuple[str, Any]] = []
            for name, member in sorted(value.__dict__.items()):
                if isinstance(member, FunctionType):
                    guarded_members.append((name, member))
                    pending.append(member)
                elif isinstance(member, (classmethod, staticmethod)):
                    guarded_members.append((name, member))
                    pending.append(member.__func__)
                elif isinstance(member, property):
                    guarded_members.append((name, member))
                    for accessor in (
                        member.fget,
                        member.fset,
                        member.fdel,
                    ):
                        if isinstance(accessor, FunctionType):
                            pending.append(accessor)
                elif isinstance(member, MemberDescriptorType):
                    guarded_members.append((name, member))
            class_rows.append((value, tuple(guarded_members)))
            return
        value_type = value.__class__
        value_id = id(value)
        if value_type is dict or value_type is MappingProxyType:
            if value_id in seen_values:
                return
            seen_values.add(value_id)
            for key, nested in value.items():
                queue(key)
                queue(nested)
            return
        if value_type is tuple or value_type is frozenset:
            if value_id in seen_values:
                return
            seen_values.add(value_id)
            for nested in value:
                queue(nested)
            return
        dataclass_fields = getattr(
            value_type,
            "__dataclass_fields__",
            None,
        )
        if not isinstance(dataclass_fields, dict):
            return
        if value_id in seen_values:
            return
        seen_values.add(value_id)
        field_rows: list[tuple[str, Any, bool]] = []
        for name in sorted(dataclass_fields):
            nested = object.__getattribute__(value, name)
            compare_by_value = (
                nested is None
                or nested.__class__ in (bool, int, float, str, bytes)
            )
            field_rows.append((name, nested, compare_by_value))
            queue(nested)
        instance_rows.append((value, value_type, tuple(field_rows)))
        queue(value_type)

    while pending:
        candidate = pending.pop()
        if not isinstance(candidate, FunctionType):
            queue(candidate)
            continue
        function_id = id(candidate)
        if function_id in seen_functions:
            continue
        seen_functions.add(function_id)
        global_rows = tuple(
            (name, candidate.__globals__[name])
            for name in sorted(
                _referenced_global_names(candidate.__code__)
            )
            if name in candidate.__globals__
        )
        closure_rows = tuple(
            (cell, cell.cell_contents)
            for cell in (candidate.__closure__ or ())
        )
        kwdefaults = candidate.__kwdefaults__
        kwdefault_rows = tuple(
            sorted((kwdefaults or {}).items())
        )
        function_rows.append(
            (
                candidate,
                candidate.__code__,
                global_rows,
                closure_rows,
                candidate.__defaults__,
                kwdefaults,
                kwdefault_rows,
            )
        )
        for _name, dependency in global_rows:
            queue(dependency)
        for _cell, dependency in closure_rows:
            queue(dependency)
        for dependency in candidate.__defaults__ or ():
            queue(dependency)
        for _name, dependency in kwdefault_rows:
            queue(dependency)
    return (
        tuple(function_rows),
        tuple(class_rows),
        tuple(instance_rows),
    )


class _LockedGuardedCallableType(type):
    def __setattr__(cls, name: str, value: Any) -> None:
        raise TypeError("guarded_operator_callable_type_immutable")

    def __delattr__(cls, name: str) -> None:
        raise TypeError("guarded_operator_callable_type_immutable")


class _GuardedOperatorCallable(metaclass=_LockedGuardedCallableType):
    """Opaque dual-kernel callable with transparent single-fault recovery."""

    __slots__ = ("__state",)
    _read = staticmethod(object.__getattribute__)
    _write = staticmethod(object.__setattr__)

    def __init__(
        self,
        *,
        primary: FunctionType,
        backup: FunctionType,
        primary_bound: tuple[Any, ...],
        backup_bound: tuple[Any, ...],
        primary_manifest: tuple[Any, ...],
        backup_manifest: tuple[Any, ...],
        name: str,
        qualname: str,
        signature: Signature,
        annotations: Mapping[str, Any],
    ) -> None:
        state = (
            primary,
            backup,
            primary_bound,
            backup_bound,
            primary_manifest,
            backup_manifest,
            name,
            qualname,
            signature,
            MappingProxyType(dict(annotations)),
            RuntimeError("operator_projection_integrity_failed"),
        )
        object.__getattribute__(self, "_write")(
            self,
            "_GuardedOperatorCallable__state",
            state,
        )

    def __setattr__(self, name: str, value: Any) -> None:
        raise TypeError("guarded_operator_callable_immutable")

    def __delattr__(self, name: str) -> None:
        raise TypeError("guarded_operator_callable_immutable")

    def __getattribute__(self, name: str) -> Any:
        if name == "_GuardedOperatorCallable__state":
            raise AttributeError(name)
        metadata_indexes = {
            "__name__": 6,
            "__qualname__": 7,
            "__signature__": 8,
            "__annotations__": 9,
        }
        if name in metadata_indexes:
            return object.__getattribute__(self, "_read")(
                self,
                "_GuardedOperatorCallable__state",
            )[metadata_indexes[name]]
        return object.__getattribute__(self, "_read")(self, name)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        state = object.__getattribute__(self, "_read")(
            self,
            "_GuardedOperatorCallable__state",
        )
        primary_ok = True
        for (
            function,
            code,
            global_rows,
            closure_rows,
            defaults,
            kwdefaults,
            kwdefault_rows,
        ) in state[4][0]:
            if function.__code__ is not code:
                primary_ok = False
                break
            if function.__defaults__ is not defaults:
                primary_ok = False
                break
            if function.__kwdefaults__ is not kwdefaults:
                primary_ok = False
                break
            if kwdefaults is not None:
                if kwdefaults.__len__() != kwdefault_rows.__len__():
                    primary_ok = False
                    break
                for name, expected in kwdefault_rows:
                    if kwdefaults.get(name) is not expected:
                        primary_ok = False
                        break
            if not primary_ok:
                break
            for name, expected in global_rows:
                if function.__globals__.get(name) is not expected:
                    primary_ok = False
                    break
            if not primary_ok:
                break
            for cell, expected in closure_rows:
                if cell.cell_contents is not expected:
                    primary_ok = False
                    break
            if not primary_ok:
                break
        if primary_ok:
            for class_, member_rows in state[4][1]:
                class_namespace = class_.__dict__
                for name, expected in member_rows:
                    if class_namespace.get(name) is not expected:
                        primary_ok = False
                        break
                if not primary_ok:
                    break
        if primary_ok:
            for instance, instance_type, field_rows in state[4][2]:
                if instance.__class__ is not instance_type:
                    primary_ok = False
                    break
                for name, expected, compare_by_value in field_rows:
                    try:
                        actual = object.__getattribute__(instance, name)
                    except AttributeError:
                        primary_ok = False
                        break
                    if compare_by_value:
                        if (
                            actual.__class__ is not expected.__class__
                            or actual != expected
                        ):
                            primary_ok = False
                            break
                    elif actual is not expected:
                        primary_ok = False
                        break
                if not primary_ok:
                    break
        if primary_ok:
            return state[0](*state[2], *args, **kwargs)

        backup_ok = True
        for (
            function,
            code,
            global_rows,
            closure_rows,
            defaults,
            kwdefaults,
            kwdefault_rows,
        ) in state[5][0]:
            if function.__code__ is not code:
                backup_ok = False
                break
            if function.__defaults__ is not defaults:
                backup_ok = False
                break
            if function.__kwdefaults__ is not kwdefaults:
                backup_ok = False
                break
            if kwdefaults is not None:
                if kwdefaults.__len__() != kwdefault_rows.__len__():
                    backup_ok = False
                    break
                for name, expected in kwdefault_rows:
                    if kwdefaults.get(name) is not expected:
                        backup_ok = False
                        break
            if not backup_ok:
                break
            for name, expected in global_rows:
                if function.__globals__.get(name) is not expected:
                    backup_ok = False
                    break
            if not backup_ok:
                break
            for cell, expected in closure_rows:
                if cell.cell_contents is not expected:
                    backup_ok = False
                    break
            if not backup_ok:
                break
        if backup_ok:
            for class_, member_rows in state[5][1]:
                class_namespace = class_.__dict__
                for name, expected in member_rows:
                    if class_namespace.get(name) is not expected:
                        backup_ok = False
                        break
                if not backup_ok:
                    break
        if backup_ok:
            for instance, instance_type, field_rows in state[5][2]:
                if instance.__class__ is not instance_type:
                    backup_ok = False
                    break
                for name, expected, compare_by_value in field_rows:
                    try:
                        actual = object.__getattribute__(instance, name)
                    except AttributeError:
                        backup_ok = False
                        break
                    if compare_by_value:
                        if (
                            actual.__class__ is not expected.__class__
                            or actual != expected
                        ):
                            backup_ok = False
                            break
                    elif actual is not expected:
                        backup_ok = False
                        break
                if not backup_ok:
                    break
        if backup_ok:
            return state[1](*state[3], *args, **kwargs)
        raise state[10]


def _guard_operator_callable(
    *,
    primary: FunctionType,
    backup: FunctionType,
    primary_bound: tuple[Any, ...] = (),
    backup_bound: tuple[Any, ...] = (),
    name: str,
    qualname: str | None = None,
    signature_source: Any | None = None,
    annotations: Mapping[str, Any] | None = None,
) -> _GuardedOperatorCallable:
    return _GuardedOperatorCallable(
        primary=primary,
        backup=backup,
        primary_bound=primary_bound,
        backup_bound=backup_bound,
        primary_manifest=_function_dependency_manifest(
            primary,
            *primary_bound,
        ),
        backup_manifest=_function_dependency_manifest(
            backup,
            *backup_bound,
        ),
        name=name,
        qualname=qualname or name,
        signature=inspect_signature(
            signature_source if signature_source is not None else primary
        ),
        annotations=(
            annotations
            if annotations is not None
            else getattr(primary, "__annotations__", {})
        ),
    )


def _invoke_integrity_bootstrap(
    freezer: FunctionType,
    guard_factory: FunctionType,
    operation: str,
    *args: Any,
    **kwargs: Any,
) -> Any:
    if operation == "freeze":
        return freezer(*args, **kwargs)
    if operation == "guard":
        return guard_factory(*args, **kwargs)
    raise ValueError(f"unknown_operator_integrity_operation:{operation}")


(
    _integrity_invoker_primary,
    _integrity_freezer_primary,
    _integrity_guard_primary,
) = _freeze_operator_function_graph(
    (
        _invoke_integrity_bootstrap,
        _freeze_operator_function_graph,
        _guard_operator_callable,
    )
)
(
    _integrity_invoker_backup,
    _integrity_freezer_backup,
    _integrity_guard_backup,
) = _freeze_operator_function_graph(
    (
        _invoke_integrity_bootstrap,
        _freeze_operator_function_graph,
        _guard_operator_callable,
    )
)
_operator_integrity_bootstrap = _guard_operator_callable(
    primary=_integrity_invoker_primary,
    backup=_integrity_invoker_backup,
    primary_bound=(
        _integrity_freezer_primary,
        _integrity_guard_primary,
    ),
    backup_bound=(
        _integrity_freezer_backup,
        _integrity_guard_backup,
    ),
    name="_operator_integrity_bootstrap",
)
del (
    _integrity_invoker_primary,
    _integrity_freezer_primary,
    _integrity_guard_primary,
    _integrity_invoker_backup,
    _integrity_freezer_backup,
    _integrity_guard_backup,
)


def _protected_integrity_module_type(
    capability: Any,
) -> type[ModuleType]:
    class _ProtectedIntegrityModuleType(ModuleType):
        def __getattribute__(self, name: str) -> Any:
            if name == "_operator_integrity_bootstrap":
                return capability
            return super().__getattribute__(name)

        def __setattr__(self, name: str, value: Any) -> None:
            if name in {"_operator_integrity_bootstrap", "__class__"}:
                raise AttributeError(
                    f"protected_operator_integrity_binding:{name}"
                )
            super().__setattr__(name, value)

        def __delattr__(self, name: str) -> None:
            if name == "_operator_integrity_bootstrap":
                raise AttributeError(
                    f"protected_operator_integrity_binding:{name}"
                )
            super().__delattr__(name)

    return _ProtectedIntegrityModuleType


_ProtectedIntegrityModule = _protected_integrity_module_type(
    _operator_integrity_bootstrap
)
_integrity_module = sys.modules[__name__]
_integrity_module.__class__ = _ProtectedIntegrityModule
del _integrity_module.__dict__["_operator_integrity_bootstrap"]
del _integrity_module
