from __future__ import annotations

import math
import struct
from dataclasses import FrozenInstanceError, dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

import pytest


@dataclass
class MutableNestedStageValue:
    labels: list[str]
    payload: dict[str, list[int]]


@dataclass
class DataclassList(list):
    label: str


@dataclass(eq=False)
class IdentityDataclass:
    payload: object


class MutableUnsupported(list):
    pass


class DictSubclass(dict):
    pass


class TupleSubclass(tuple):
    pass


class StringSubclass(str):
    pass


class IntegerSubclass(int):
    pass


class FloatSubclass(float):
    pass


class ExampleEnum(Enum):
    VALUE = "value"


def test_verified_deck_stage_is_deeply_immutable_with_stable_digest() -> None:
    from hsconfig.configure_stages import (
        build_verified_deck_stage,
        stage_digest,
    )

    identity = {
        "deck_name": "ShadowPriest",
        "deck_fingerprint": "abc",
    }
    cards = [
        {
            "card_id": "SW_448",
            "dbf_id": 64443,
            "count": 1,
        }
    ]
    verification = {"status": "verified"}

    stage = build_verified_deck_stage(
        identity=identity,
        cards=cards,
        input_verification=verification,
    )
    identity["deck_name"] = "mutated"
    cards[0]["count"] = 99
    verification["status"] = "mutated"

    assert dict(stage.identity) == {
        "deck_name": "ShadowPriest",
        "deck_fingerprint": "abc",
    }
    assert [dict(card) for card in stage.cards] == [
        {
            "card_id": "SW_448",
            "dbf_id": 64443,
            "count": 1,
        }
    ]
    assert dict(stage.input_verification) == {"status": "verified"}
    assert stage_digest(stage) == (
        "sha256:a6457453efe86b8486b2d9ee9e0d33b6e05c49c4ee190297fc068e9b56e1c547"
    )
    with pytest.raises(TypeError):
        stage.identity["deck_name"] = "mutated"
    with pytest.raises(TypeError):
        stage.cards[0]["count"] = 99
    with pytest.raises(FrozenInstanceError):
        stage.identity = {}


@pytest.mark.parametrize("boundary", ["construction", "digest", "materialization"])
def test_nested_dataclasses_are_rejected_at_every_stage_boundary(
    boundary: str,
) -> None:
    from hsconfig.configure_stages import (
        build_verified_deck_stage,
        materialize_stage_value,
        stage_digest,
    )

    nested = MutableNestedStageValue(
        labels=["alpha"],
        payload={"values": [1, 2]},
    )

    with pytest.raises(
        TypeError,
        match=(
            r"Stage value at (identity\.nested|\$) must use exact "
            r"stage-domain types; received "
            r"tests\.test_configure_stages\.MutableNestedStageValue"
        ),
    ):
        if boundary == "construction":
            build_verified_deck_stage(
                identity={"nested": nested},
                cards=[],
                input_verification={"status": "verified"},
            )
        elif boundary == "digest":
            stage_digest(nested)
        else:
            materialize_stage_value(nested)


def test_dataclass_list_content_collision_is_rejected() -> None:
    from hsconfig.configure_stages import stage_digest

    left = DataclassList("same")
    left.extend([1])
    right = DataclassList("same")
    right.extend([2])

    for value in (left, right):
        with pytest.raises(
            TypeError,
            match=(
                r"Stage value at \$ must use exact stage-domain types; "
                r"received tests\.test_configure_stages\.DataclassList"
            ),
        ):
            stage_digest(value)


def test_identity_dataclass_set_and_mapping_collapse_are_rejected() -> None:
    from hsconfig.configure_stages import stage_digest

    first = IdentityDataclass("same")
    second = IdentityDataclass("same")

    with pytest.raises(
        TypeError,
        match=(
            r"Stage value at \$ must use exact stage-domain types; "
            r"received builtins\.set"
        ),
    ):
        stage_digest({first, second})
    with pytest.raises(
        TypeError,
        match=(
            r"Stage mapping key at \$\[key#0\] must be exact builtins\.str; "
            r"received tests\.test_configure_stages\.IdentityDataclass"
        ),
    ):
        stage_digest({first: "first", second: "second"})


def test_unhashable_frozen_dataclass_key_uses_domain_error_not_raw_typeerror() -> None:
    from hsconfig.configure_stages import stage_digest

    key = IdentityDataclass({"nested": 1})

    with pytest.raises(
        TypeError,
        match=(
            r"Stage mapping key at \$\[key#0\] must be exact builtins\.str; "
            r"received tests\.test_configure_stages\.IdentityDataclass"
        ),
    ):
        stage_digest({key: "value"})


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(b"bytes", id="bytes"),
        pytest.param({1, 2}, id="set"),
        pytest.param(frozenset({1, 2}), id="frozenset"),
        pytest.param(Path("unsafe"), id="path"),
        pytest.param(ExampleEnum.VALUE, id="enum"),
        pytest.param(Decimal("1.5"), id="decimal"),
        pytest.param(MutableUnsupported(["unsafe"]), id="list-subclass"),
        pytest.param(DictSubclass(value=1), id="dict-subclass"),
        pytest.param(TupleSubclass((1, 2)), id="tuple-subclass"),
        pytest.param(IntegerSubclass(1), id="int-subclass"),
        pytest.param(FloatSubclass(1.0), id="float-subclass"),
        pytest.param(StringSubclass("unsafe"), id="str-subclass"),
    ],
)
def test_values_outside_the_exact_stage_domain_are_rejected(value: Any) -> None:
    from hsconfig.configure_stages import stage_digest

    with pytest.raises(
        TypeError,
        match=(
            r"Stage value at \$ must use exact stage-domain types; received "
        ),
    ):
        stage_digest(value)


@pytest.mark.parametrize(
    "key",
    [
        pytest.param(1, id="integer"),
        pytest.param(1.5, id="float"),
        pytest.param(True, id="boolean"),
        pytest.param(None, id="null"),
        pytest.param(StringSubclass("key"), id="string-subclass"),
    ],
)
def test_mapping_keys_must_be_exact_strings(key: Any) -> None:
    from hsconfig.configure_stages import stage_digest

    with pytest.raises(
        TypeError,
        match=(
            r"Stage mapping key at \$\[key#0\] must be exact builtins\.str; "
            r"received "
        ),
    ):
        stage_digest({key: "value"})


@pytest.mark.parametrize(
    "cycle_factory",
    [
        pytest.param(lambda: _self_referential_list(), id="list"),
        pytest.param(lambda: _self_referential_mapping(), id="mapping"),
    ],
)
@pytest.mark.parametrize("boundary", ["construction", "digest", "materialization"])
def test_stage_cycles_fail_explicitly_and_deterministically(
    cycle_factory,
    boundary: str,
) -> None:
    from hsconfig.configure_stages import (
        build_verified_deck_stage,
        materialize_stage_value,
        stage_digest,
    )

    messages = []
    for _attempt in range(2):
        cyclic = cycle_factory()
        with pytest.raises(
            ValueError,
            match=r"Stage values must be acyclic; cycle detected at ",
        ) as error:
            if boundary == "construction":
                build_verified_deck_stage(
                    identity={"cyclic": cyclic},
                    cards=[],
                    input_verification={"status": "verified"},
                )
            elif boundary == "digest":
                stage_digest(cyclic)
            else:
                materialize_stage_value(cyclic)
        messages.append(str(error.value))

    assert messages[0] == messages[1]


@pytest.mark.parametrize("boundary", ["construction", "digest", "materialization"])
def test_stage_depth_is_bounded_before_python_recursion_limit(
    boundary: str,
) -> None:
    from hsconfig.configure_stages import (
        build_verified_deck_stage,
        materialize_stage_value,
        stage_digest,
    )

    messages = []
    for _attempt in range(2):
        deep_value = _nested_list(1500)
        with pytest.raises(
            ValueError,
            match=r"Stage value exceeds maximum depth 128 at ",
        ) as error:
            if boundary == "construction":
                build_verified_deck_stage(
                    identity={"deep": deep_value},
                    cards=[],
                    input_verification={"status": "verified"},
                )
            elif boundary == "digest":
                stage_digest(deep_value)
            else:
                materialize_stage_value(deep_value)
        messages.append(str(error.value))

    assert messages[0] == messages[1]


@pytest.mark.parametrize("boundary", ["construction", "digest", "materialization"])
def test_shared_subtree_cannot_bypass_depth_limit_through_completed_memo(
    boundary: str,
) -> None:
    from hsconfig.configure_stages import (
        build_verified_deck_stage,
        materialize_stage_value,
        stage_digest,
    )

    variants = []
    for deep_first, shared in ((False, True), (True, True), (False, False)):
        shallow = _nested_list(10)
        deep_leaf = shallow if shared else _nested_list(10)
        deep = _nested_wrapper(deep_leaf, 120)
        entries = (
            (("deep", deep), ("shallow", shallow))
            if deep_first
            else (("shallow", shallow), ("deep", deep))
        )
        variants.append(dict(entries))

    for value in variants:
        with pytest.raises(
            ValueError,
            match=r"Stage value exceeds maximum depth 128 at ",
        ):
            if boundary == "construction":
                build_verified_deck_stage(
                    identity=value,
                    cards=[],
                    input_verification={"status": "verified"},
                )
            elif boundary == "digest":
                stage_digest(value)
            else:
                materialize_stage_value(value)


@pytest.mark.parametrize("boundary", ["construction", "digest", "materialization"])
def test_depth_limit_has_exact_root_and_stage_wrapper_semantics(
    boundary: str,
) -> None:
    from hsconfig.configure_stages import (
        build_verified_deck_stage,
        materialize_stage_value,
        stage_digest,
    )

    if boundary == "construction":
        build_verified_deck_stage(
            identity={"edge": _nested_list(127)},
            cards=[],
            input_verification={"status": "verified"},
        )
        with pytest.raises(ValueError):
            build_verified_deck_stage(
                identity={"edge": _nested_list(128)},
                cards=[],
                input_verification={"status": "verified"},
            )
    else:
        operation = (
            stage_digest if boundary == "digest" else materialize_stage_value
        )
        operation(_nested_list(128))
        with pytest.raises(ValueError):
            operation(_nested_list(129))


_NON_FINITE_FLOATS = [
    pytest.param(
        struct.unpack(">d", bytes.fromhex("7ff8000000000001"))[0],
        id="nan-payload-1",
    ),
    pytest.param(
        struct.unpack(">d", bytes.fromhex("7ff8000000000002"))[0],
        id="nan-payload-2",
    ),
    pytest.param(float("inf"), id="positive-infinity"),
    pytest.param(float("-inf"), id="negative-infinity"),
]


@pytest.mark.parametrize("value", _NON_FINITE_FLOATS)
@pytest.mark.parametrize("position", ["scalar", "mapping-value"])
def test_non_finite_floats_are_rejected_at_stage_boundaries(
    value: float,
    position: str,
) -> None:
    from hsconfig.configure_stages import (
        build_verified_deck_stage,
        stage_digest,
    )

    with pytest.raises(
        ValueError,
        match=r"Stage values must use finite floats at ",
    ):
        if position == "scalar":
            stage_digest(value)
        else:
            build_verified_deck_stage(
                identity={"unsafe": value},
                cards=[],
                input_verification={"status": "verified"},
            )


def test_non_string_nan_mapping_keys_use_the_mapping_key_domain_error() -> None:
    from hsconfig.configure_stages import stage_digest

    first_nan = struct.unpack(">d", bytes.fromhex("7ff8000000000001"))[0]
    second_nan = struct.unpack(">d", bytes.fromhex("7ff8000000000002"))[0]

    for value in (
        {first_nan: "first", second_nan: "second"},
        {second_nan: "second", first_nan: "first"},
    ):
        with pytest.raises(
            TypeError,
            match=(
                r"Stage mapping key at \$\[key#0\] must be exact "
                r"builtins\.str; received builtins\.float"
            ),
        ):
            stage_digest(value)


@pytest.mark.parametrize(
    ("value", "codepoint"),
    [
        pytest.param("\ud800", "D800", id="high-surrogate"),
        pytest.param("\udfff", "DFFF", id="low-surrogate"),
    ],
)
@pytest.mark.parametrize("position", ["value", "key"])
@pytest.mark.parametrize("boundary", ["construction", "digest", "materialization"])
def test_lone_surrogates_are_rejected_early_with_stable_paths(
    value: str,
    codepoint: str,
    position: str,
    boundary: str,
) -> None:
    from hsconfig.configure_stages import (
        build_verified_deck_stage,
        materialize_stage_value,
        stage_digest,
    )

    if boundary == "construction":
        candidate = {"unsafe": value} if position == "value" else {value: "unsafe"}
        expected_path = "identity.unsafe" if position == "value" else "identity[key#0]"
    else:
        candidate = value if position == "value" else {value: "unsafe"}
        expected_path = "$" if position == "value" else "$[key#0]"
    messages = []
    for _attempt in range(2):
        with pytest.raises(ValueError) as error:
            if boundary == "construction":
                build_verified_deck_stage(
                    identity=candidate,
                    cards=[],
                    input_verification={"status": "verified"},
                )
            elif boundary == "digest":
                stage_digest(candidate)
            else:
                materialize_stage_value(candidate)
        messages.append(str(error.value))

    assert messages == [
        (
            f"Stage string at {expected_path} contains invalid Unicode "
            f"surrogate U+{codepoint} at index 0"
        )
    ] * 2


def test_valid_supplementary_unicode_is_materialized_and_digested_deterministically() -> None:
    from hsconfig.configure_stages import (
        build_verified_deck_stage,
        materialize_stage_value,
        stage_digest,
    )

    key = "emoji-\U0001f600"
    value = "deseret-\U00010437"
    left = {key: value, "plain": "ok"}
    right = {"plain": "ok", key: value}
    stage = build_verified_deck_stage(
        identity=left,
        cards=[],
        input_verification={"status": "verified"},
    )

    assert materialize_stage_value(stage.identity) == left
    assert stage_digest(left) == stage_digest(right)
    assert stage_digest(left) == stage_digest(left)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(10**4299, id="positive-boundary"),
        pytest.param(-(10**4299), id="negative-boundary"),
        pytest.param(10**4300, id="positive-over-decimal-limit"),
        pytest.param(-(10**4300), id="negative-over-decimal-limit"),
    ],
)
def test_arbitrary_exact_integer_scalars_materialize_and_digest(value: int) -> None:
    from hsconfig.configure_stages import materialize_stage_value, stage_digest

    assert materialize_stage_value(value) == value
    assert stage_digest(value) == stage_digest(value)


def test_large_integer_mapping_values_ignore_insertion_and_sharing_topology() -> None:
    from hsconfig.configure_stages import stage_digest

    large = 10**4300
    shared = [large]
    shared_tree = {"alpha": shared, "beta": shared}
    duplicated_tree = {"beta": [large], "alpha": [large]}

    assert stage_digest(shared_tree) == stage_digest(duplicated_tree)


def test_verified_stage_accepts_and_preserves_large_exact_integers() -> None:
    from hsconfig.configure_stages import (
        build_verified_deck_stage,
        materialize_stage_value,
        stage_digest,
    )

    positive = 10**4300
    negative = -positive
    stage = build_verified_deck_stage(
        identity={"positive": positive},
        cards=[{"card_id": "LARGE", "dbf_id": negative, "count": 1}],
        input_verification={"boundary": 10**4299},
    )

    assert materialize_stage_value(stage.identity)["positive"] == positive
    assert materialize_stage_value(stage.cards)[0]["dbf_id"] == negative
    assert stage_digest(stage) == stage_digest(stage)


def test_lowered_stage_accepts_and_preserves_large_exact_integers() -> None:
    from hsconfig.configure_stages import (
        build_lowered_runtime_stage,
        materialize_stage_value,
        stage_digest,
    )

    positive = 10**4300
    negative = -positive
    stage = build_lowered_runtime_stage(
        runtime_files={"GlobalValues.json": {"positive": positive}},
        warnings=[{"negative": negative}],
        source_contract={"boundary": -(10**4299)},
    )

    assert materialize_stage_value(stage.runtime_files)[
        "GlobalValues.json"
    ]["positive"] == positive
    assert materialize_stage_value(stage.warnings)[0]["negative"] == negative
    assert stage_digest(stage) == stage_digest(stage)


def test_every_accepted_scalar_has_deterministic_distinct_canonicalization() -> None:
    from hsconfig.configure_stages import stage_digest

    values = [
        None,
        False,
        True,
        0,
        1,
        -1,
        10**4300,
        -(10**4300),
        10**4300 + 1,
        0.0,
        -0.0,
        1.5,
        "",
        "0",
        "valid-\U0001f600",
    ]

    digests = [stage_digest(value) for value in values]

    assert len(set(digests)) == len(values)
    assert digests == [stage_digest(value) for value in values]


def test_finite_float_canonicalization_preserves_binary_distinctions() -> None:
    from hsconfig.configure_stages import stage_digest

    assert stage_digest(0.0) != stage_digest(-0.0)
    assert stage_digest(1.0) != stage_digest(math.nextafter(1.0, 2.0))


def test_acyclic_shared_references_are_reused_immutably() -> None:
    from hsconfig.configure_stages import (
        build_verified_deck_stage,
        materialize_stage_value,
        stage_digest,
    )

    shared = [{"value": 1}]
    stage = build_verified_deck_stage(
        identity={"left": shared, "right": shared},
        cards=[],
        input_verification={"status": "verified"},
    )
    shared[0]["value"] = 99

    assert stage.identity["left"] is stage.identity["right"]
    assert materialize_stage_value(stage.identity) == {
        "left": [{"value": 1}],
        "right": [{"value": 1}],
    }
    materialized = materialize_stage_value(stage.identity)
    assert materialized["left"] is materialized["right"]
    materialized["left"][0]["value"] = 101
    assert materialize_stage_value(stage.identity)["left"][0]["value"] == 1
    assert stage_digest(
        {"left": shared, "right": shared}
    ) == stage_digest(
        {
            "left": [{"value": 99}],
            "right": [{"value": 99}],
        }
    )


def test_stage_digest_ignores_mapping_insertion_and_sharing_topology() -> None:
    from hsconfig.configure_stages import stage_digest

    shared = {"value": [1, 2]}
    shared_tree = {"alpha": shared, "beta": shared}
    duplicated_tree = {
        "beta": {"value": [1, 2]},
        "alpha": {"value": [1, 2]},
    }

    assert stage_digest(shared_tree) == stage_digest(duplicated_tree)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ({"value": [1, 2]}, {"value": (1, 2)}),
        (True, 1),
        (1, 1.0),
        (None, "null"),
        (1.0, "1.0"),
    ],
)
def test_stage_digest_preserves_allowed_value_types(left, right) -> None:
    from hsconfig.configure_stages import stage_digest

    assert stage_digest(left) != stage_digest(right)


@pytest.mark.parametrize("boundary", ["construction", "digest", "materialization"])
def test_shared_dag_processing_scales_with_unique_nodes(
    boundary: str,
    monkeypatch,
) -> None:
    import hsconfig.configure_stages as configure_stages

    original_freeze = configure_stages._freeze_value
    original_digest = configure_stages._typed_canonical_value
    original_materialize = configure_stages._materialize_frozen_value
    visits = 0

    def counted_freeze(*args, **kwargs):
        nonlocal visits
        visits += 1
        return original_freeze(*args, **kwargs)

    def counted_digest(*args, **kwargs):
        nonlocal visits
        visits += 1
        return original_digest(*args, **kwargs)

    def counted_materialize(*args, **kwargs):
        nonlocal visits
        visits += 1
        return original_materialize(*args, **kwargs)

    monkeypatch.setattr(configure_stages, "_freeze_value", counted_freeze)
    monkeypatch.setattr(
        configure_stages,
        "_typed_canonical_value",
        counted_digest,
    )
    monkeypatch.setattr(
        configure_stages,
        "_materialize_frozen_value",
        counted_materialize,
    )

    observed_visits = []
    for depth in (11, 14, 17):
        visits = 0
        dag = _shared_dag(depth)
        if boundary == "construction":
            configure_stages.build_verified_deck_stage(
                identity={"dag": dag},
                cards=[],
                input_verification={"status": "verified"},
            )
        elif boundary == "digest":
            configure_stages.stage_digest(dag)
        else:
            configure_stages.materialize_stage_value(dag)
        observed_visits.append(visits)
        assert visits <= 12 * depth + 24

    assert observed_visits == sorted(observed_visits)


def test_only_exact_public_stage_dataclasses_are_accepted_at_the_root() -> None:
    from hsconfig.configure_stages import (
        VerifiedDeckStage,
        build_verified_deck_stage,
        stage_digest,
    )

    class VerifiedDeckStageSubclass(VerifiedDeckStage):
        pass

    stage = build_verified_deck_stage(
        identity={"deck_name": "ShadowPriest"},
        cards=[],
        input_verification={"status": "verified"},
    )
    derived = VerifiedDeckStageSubclass(
        identity=stage.identity,
        cards=stage.cards,
        input_verification=stage.input_verification,
    )

    assert stage_digest(stage).startswith("sha256:")
    with pytest.raises(
        TypeError,
        match=(
            r"Stage value at \$ must use exact stage-domain types; received "
            r"tests\.test_configure_stages\."
            r"test_only_exact_public_stage_dataclasses_are_accepted_at_the_root"
            r"\.<locals>\.VerifiedDeckStageSubclass"
        ),
    ):
        stage_digest(derived)


def test_lowered_runtime_stage_is_deeply_immutable_with_stable_digest() -> None:
    from hsconfig.configure_stages import (
        build_lowered_runtime_stage,
        stage_digest,
    )

    runtime_files = {
        "GlobalValues.json": {"A": 1},
        "Mulligan.json": {"B": []},
    }
    warnings = [{"reason": "thin"}]
    source_contract = {"status": "closed"}

    stage = build_lowered_runtime_stage(
        runtime_files=runtime_files,
        warnings=warnings,
        source_contract=source_contract,
    )
    runtime_files["GlobalValues.json"]["A"] = 2
    warnings[0]["reason"] = "mutated"
    source_contract["status"] = "mutated"

    assert {
        filename: dict(payload)
        for filename, payload in stage.runtime_files.items()
    } == {
        "GlobalValues.json": {"A": 1},
        "Mulligan.json": {"B": ()},
    }
    assert [dict(warning) for warning in stage.warnings] == [{"reason": "thin"}]
    assert dict(stage.source_contract) == {"status": "closed"}
    assert stage_digest(stage) == (
        "sha256:d2a9c785b9af32a01aedc7b914cd4d9e6ee92d440903f336ec5e2e10404d68f8"
    )
    with pytest.raises(TypeError):
        stage.runtime_files["GlobalValues.json"]["A"] = 2
    with pytest.raises(TypeError):
        stage.warnings[0]["reason"] = "mutated"
    with pytest.raises(FrozenInstanceError):
        stage.runtime_files = {}


def _self_referential_list() -> list[Any]:
    value: list[Any] = []
    value.append(value)
    return value


def _self_referential_mapping() -> dict[str, Any]:
    value: dict[str, Any] = {}
    value["self"] = value
    return value


def _nested_list(depth: int) -> Any:
    value: Any = "leaf"
    for _index in range(depth):
        value = [value]
    return value


def _nested_wrapper(value: Any, depth: int) -> Any:
    for _index in range(depth):
        value = [value]
    return value


def _shared_dag(depth: int) -> dict[str, Any]:
    value: dict[str, Any] = {"leaf": "value"}
    for _index in range(depth):
        value = {"left": value, "right": value}
    return value
