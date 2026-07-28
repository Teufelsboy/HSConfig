from __future__ import annotations

import math
import struct
from collections.abc import Mapping
from dataclasses import FrozenInstanceError, dataclass, make_dataclass
from typing import Any

import pytest


@dataclass
class MutableNestedStageValue:
    labels: list[str]
    payload: dict[str, list[int]]


class MutableUnsupported(list):
    pass


@dataclass
class CyclicStageValue:
    child: Any = None


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
        "sha256:af1cc6c05a641b5ebc29e6622a938bc9bfdd608b380b6040345f696aa5cbe5bd"
    )
    with pytest.raises(TypeError):
        stage.identity["deck_name"] = "mutated"
    with pytest.raises(TypeError):
        stage.cards[0]["count"] = 99
    with pytest.raises(FrozenInstanceError):
        stage.identity = {}


def test_stage_recursively_freezes_nested_dataclass_and_list_aliases() -> None:
    from hsconfig.configure_stages import (
        build_verified_deck_stage,
        materialize_stage_value,
        stage_digest,
    )

    nested = MutableNestedStageValue(
        labels=["alpha"],
        payload={"values": [1, 2]},
    )
    stage = build_verified_deck_stage(
        identity={"nested": nested},
        cards=[],
        input_verification={"status": "verified"},
    )
    original_digest = stage_digest(stage)

    nested.labels.append("external-mutation")
    nested.payload["values"][0] = 99

    frozen_nested = stage.identity["nested"]
    assert isinstance(frozen_nested, Mapping)
    assert materialize_stage_value(frozen_nested) == {
        "labels": ["alpha"],
        "payload": {"values": [1, 2]},
    }
    assert stage_digest(stage) == original_digest
    materialized = materialize_stage_value(frozen_nested)
    materialized["labels"].append("materialized-mutation")
    materialized["payload"]["values"][0] = 101
    assert materialize_stage_value(frozen_nested) == {
        "labels": ["alpha"],
        "payload": {"values": [1, 2]},
    }
    assert stage_digest(stage) == original_digest
    with pytest.raises(AttributeError):
        frozen_nested["labels"].append("stage-mutation")
    with pytest.raises(TypeError):
        frozen_nested["payload"]["values"][0] = 99


def test_stage_construction_rejects_unsupported_mutable_list_subclass() -> None:
    from hsconfig.configure_stages import build_verified_deck_stage

    unsafe = MutableUnsupported(["aliased"])

    with pytest.raises(
        TypeError,
        match=(
            r"Stage values must use supported canonical types at "
            r"identity\.unsafe; received "
            r"tests\.test_configure_stages\.MutableUnsupported"
        ),
    ):
        build_verified_deck_stage(
            identity={"unsafe": unsafe},
            cards=[],
            input_verification={"status": "verified"},
        )


@pytest.mark.parametrize(
    "cycle_factory",
    [
        pytest.param(lambda: _self_referential_list(), id="list"),
        pytest.param(lambda: _self_referential_mapping(), id="mapping"),
        pytest.param(lambda: _self_referential_dataclass(), id="dataclass"),
    ],
)
@pytest.mark.parametrize("boundary", ["construction", "digest"])
def test_stage_cycles_fail_explicitly_and_deterministically(
    cycle_factory,
    boundary: str,
) -> None:
    from hsconfig.configure_stages import (
        build_verified_deck_stage,
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
            else:
                stage_digest(cyclic)
        messages.append(str(error.value))

    assert messages[0] == messages[1]


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
@pytest.mark.parametrize("position", ["scalar", "mapping-value", "mapping-key"])
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
        elif position == "mapping-value":
            build_verified_deck_stage(
                identity={"unsafe": value},
                cards=[],
                input_verification={"status": "verified"},
            )
        else:
            build_verified_deck_stage(
                identity={value: "unsafe"},
                cards=[],
                input_verification={"status": "verified"},
            )


def test_distinct_nan_keys_are_rejected_independent_of_insertion_order() -> None:
    from hsconfig.configure_stages import stage_digest

    first_nan = struct.unpack(">d", bytes.fromhex("7ff8000000000001"))[0]
    second_nan = struct.unpack(">d", bytes.fromhex("7ff8000000000002"))[0]
    left = {first_nan: "first", second_nan: "second"}
    right = {second_nan: "second", first_nan: "first"}

    for value in (left, right):
        with pytest.raises(
            ValueError,
            match=r"Stage values must use finite floats at ",
        ):
            stage_digest(value)


def test_finite_float_canonicalization_preserves_binary_distinctions() -> None:
    from hsconfig.configure_stages import stage_digest

    assert stage_digest(0.0) != stage_digest(-0.0)
    assert stage_digest(1.0) != stage_digest(math.nextafter(1.0, 2.0))


def test_acyclic_shared_references_do_not_trigger_false_cycle_detection() -> None:
    from hsconfig.configure_stages import (
        build_verified_deck_stage,
        materialize_stage_value,
    )

    shared = [{"value": 1}]
    stage = build_verified_deck_stage(
        identity={"left": shared, "right": shared},
        cards=[],
        input_verification={"status": "verified"},
    )
    shared[0]["value"] = 99

    assert materialize_stage_value(stage.identity) == {
        "left": [{"value": 1}],
        "right": [{"value": 1}],
    }


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ({1: "value"}, {"1": "value"}),
        ({"value": [1, 2]}, {"value": (1, 2)}),
        (True, 1),
        (1, 1.0),
        (None, "null"),
        (1.0, "1.0"),
    ],
)
def test_stage_digest_preserves_canonical_value_types(left, right) -> None:
    from hsconfig.configure_stages import stage_digest

    assert stage_digest(left) != stage_digest(right)


def test_stage_digest_supports_mixed_mapping_key_types_deterministically() -> None:
    from hsconfig.configure_stages import stage_digest

    left = {
        7: "integer",
        "7": "string",
        None: "null",
        2.5: "float",
    }
    right = {
        2.5: "float",
        None: "null",
        "7": "string",
        7: "integer",
    }

    assert stage_digest(left) == stage_digest(right)


def test_stage_digest_includes_fully_qualified_dataclass_type() -> None:
    from hsconfig.configure_stages import stage_digest

    first_type = make_dataclass("TwinStageValue", [("value", int)])
    second_type = make_dataclass("TwinStageValue", [("value", int)])
    first_type.__module__ = "tests.stage_type_a"
    second_type.__module__ = "tests.stage_type_b"

    assert stage_digest(first_type(1)) != stage_digest(second_type(1))


def test_stage_digest_includes_dataclass_field_definition_order() -> None:
    from hsconfig.configure_stages import stage_digest

    first_type = make_dataclass(
        "OrderedStageValue",
        [("left", int), ("right", int)],
    )
    second_type = make_dataclass(
        "OrderedStageValue",
        [("right", int), ("left", int)],
    )
    first_type.__module__ = second_type.__module__ = "tests.stage_layout"

    assert stage_digest(first_type(1, 2)) != stage_digest(second_type(2, 1))


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
        "sha256:f2e1d4e7035dc967e9348d3701935cfae730128f00d472e17433c7813e9f96fd"
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


def _self_referential_dataclass() -> CyclicStageValue:
    value = CyclicStageValue()
    value.child = value
    return value
