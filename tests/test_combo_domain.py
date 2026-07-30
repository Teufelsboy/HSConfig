from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from hsconfig.combo_plan import build_typed_combo_plan
from hsconfig.compile_combo import compile_combo
from hsconfig.package_domain import (
    ComboDecisionModel,
    ComboPlanModel,
    ComboSuppressionModel,
    ComboTiming,
)
from tests.combo_authority_fixtures import build_canonical_combo_case


def test_typed_combo_plan_is_the_direct_report_and_runtime_authority() -> None:
    caller_cards = ["CARD_A", "CARD_B"]
    caller_values = ["12", "8"]
    caller_claim_ids = ["claim"]
    caller_source_refs = ["source:guide"]
    decision = ComboDecisionModel(
        rule_id="claim_combo",
        cards=caller_cards,
        timing=ComboTiming.SAME_TURN,
        values=caller_values,
        condition="*",
        source_claim_ids=caller_claim_ids,
        confidence="source_backed",
        source_refs=caller_source_refs,
        claim_id="claim",
    )
    plan = ComboPlanModel(decisions=[decision], suppressions=[])
    caller_cards.append("LATER")
    caller_values.append("99")
    caller_claim_ids.append("later")
    caller_source_refs.append("source:later")

    assert plan.to_report() == {
        "combos": [
            {
                "rule_id": "claim_combo",
                "cards": ["CARD_A", "CARD_B"],
                "timing_kind": "same_turn",
                "operator": ">>",
                "values": ["12", "8"],
                "condition": "*",
                "source_claim_ids": ["claim"],
                "confidence": "source_backed",
                "source_refs": ["source:guide"],
                "combo": "CARD_A>>CARD_B",
                "value": 12,
                "claim_id": "claim",
            }
        ],
        "suppressed": [],
    }
    assert compile_combo(plan, deck_name="Fixture") == {
        "GameCardId": "Combo",
        "ConfigComment": "Fixture generated combos",
        "ComboList": {
            "values": [
                {
                    "comment": "Fixture: claim_combo",
                    "condition": "*",
                    "combo": "CARD_A>>CARD_B",
                    "value": "12>>8",
                }
            ]
        },
    }
    assert decision.cards == ("CARD_A", "CARD_B")
    with pytest.raises(FrozenInstanceError):
        decision.rule_id = "changed"  # type: ignore[misc]


def test_typed_combo_plan_rejects_duplicate_decision_ids() -> None:
    first = _decision("b")

    with pytest.raises(ValueError, match="combo_decision_id_duplicate"):
        ComboPlanModel(decisions=(first, first), suppressions=())


def test_typed_combo_plan_preserves_authoritative_decision_order() -> None:
    plan = ComboPlanModel(
        decisions=(_decision("z"), _decision("a")),
        suppressions=(),
    )

    assert tuple(row.rule_id for row in plan.decisions) == ("z", "a")
    assert [row["rule_id"] for row in plan.to_report()["combos"]] == [
        "z",
        "a",
    ]


def test_direct_combo_decision_requires_an_authoritative_claim_identifier() -> None:
    with pytest.raises(ValueError, match="combo_decision_authority_missing"):
        ComboDecisionModel(
            rule_id="source_less",
            cards=("A", "B"),
            timing=ComboTiming.SAME_TURN,
            values=("10", "10"),
            condition="*",
            source_claim_ids=(),
            confidence="source_backed",
            source_refs=(),
            claim_id=None,
        )


def test_legacy_mapping_adapter_cannot_compile_a_source_less_decision() -> None:
    with pytest.raises(ValueError, match="Invalid combo sequence source_less"):
        compile_combo(
            {
                "deck_name": "Fixture",
                "combos": [
                    {
                        "rule_id": "source_less",
                        "cards": ["A", "B"],
                        "values": ["10", "10"],
                    }
                ],
            }
        )


def test_combo_suppression_requires_its_authoritative_claim_id() -> None:
    with pytest.raises(ValueError, match="combo_suppression_claim_id_invalid"):
        ComboSuppressionModel(
            cards=("A", "B"),
            reason_code="missing_timing",
            claim_id=None,
        )


@pytest.mark.parametrize(
    ("field_name", "value", "error"),
    [
        ("cards", "AB", "combo_cards_container_invalid"),
        ("cards", b"AB", "combo_cards_container_invalid"),
        ("cards", bytearray(b"AB"), "combo_cards_container_invalid"),
        ("cards", memoryview(b"AB"), "combo_cards_container_invalid"),
        ("values", "12", "combo_values_container_invalid"),
        (
            "source_claim_ids",
            "claim",
            "combo_source_claim_ids_container_invalid",
        ),
        ("source_refs", "source", "combo_source_refs_container_invalid"),
    ],
)
def test_direct_combo_decision_rejects_scalar_tuple_containers(
    field_name: str,
    value: object,
    error: str,
) -> None:
    values = {
        "rule_id": "combo",
        "cards": ("A", "B"),
        "timing": ComboTiming.SAME_TURN,
        "values": ("10", "10"),
        "condition": "*",
        "source_claim_ids": ("claim",),
        "confidence": "source_backed",
        "source_refs": ("source",),
        "claim_id": "claim",
    }
    values[field_name] = value

    with pytest.raises(ValueError, match=error):
        ComboDecisionModel(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value",
    [
        {"10": 1, "20": 2},
        {"10", "20"},
        frozenset({"10", "20"}),
        iter(("10", "20")),
        range(2),
    ],
    ids=["mapping", "set", "frozenset", "generator", "range"],
)
def test_direct_combo_decision_requires_ordered_list_or_tuple_fields(
    value: object,
) -> None:
    for field_name in (
        "cards",
        "values",
        "source_claim_ids",
        "source_refs",
    ):
        fields = {
            "rule_id": "combo",
            "cards": ("A", "B"),
            "timing": ComboTiming.SAME_TURN,
            "values": ("10", "10"),
            "condition": "*",
            "source_claim_ids": ("claim",),
            "confidence": "source_backed",
            "source_refs": ("source",),
            "claim_id": "claim",
        }
        fields[field_name] = value

        with pytest.raises(
            ValueError,
            match=f"combo_{field_name}_container_invalid",
        ):
            ComboDecisionModel(**fields)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("cards", "AB"),
        ("values", "12"),
        ("source_claim_ids", "claim"),
        ("source_refs", "source"),
    ],
)
def test_mapping_adapter_rejects_scalar_tuple_containers(
    field_name: str,
    value: object,
) -> None:
    row = {
        "rule_id": "malformed",
        "cards": ["A", "B"],
        "values": ["10", "10"],
        "source_claim_ids": ["claim"],
        "source_refs": ["source"],
    }
    row[field_name] = value

    with pytest.raises(ValueError, match="Invalid combo sequence malformed"):
        compile_combo({"deck_name": "Fixture", "combos": [row]})


@pytest.mark.parametrize(
    "field_name",
    ["cards", "values", "source_claim_ids", "source_refs"],
)
def test_mapping_adapter_rejects_unordered_tuple_fields(
    field_name: str,
) -> None:
    row = {
        "rule_id": "malformed",
        "cards": ["A", "B"],
        "values": ["10", "10"],
        "source_claim_ids": ["claim"],
        "source_refs": ["source"],
    }
    row[field_name] = (
        {"10": 1, "20": 2}
        if field_name == "values"
        else {"A": 1, "B": 2}
    )

    with pytest.raises(ValueError, match="Invalid combo sequence malformed"):
        compile_combo({"deck_name": "Fixture", "combos": [row]})


@pytest.mark.parametrize("field_name", ["cards", "missing_cards"])
def test_combo_suppression_requires_ordered_list_or_tuple_fields(
    field_name: str,
) -> None:
    fields = {
        "cards": ("A", "B"),
        "reason_code": "missing_card",
        "claim_id": "claim",
        "missing_cards": ("B",),
    }
    fields[field_name] = {"A", "B"}

    with pytest.raises(
        ValueError,
        match=f"combo_suppression_{field_name}_container_invalid",
    ):
        ComboSuppressionModel(**fields)  # type: ignore[arg-type]


def test_suppression_mapping_adapter_rejects_unordered_card_fields() -> None:
    with pytest.raises(
        ValueError,
        match="combo_missing_cards_container_invalid",
    ):
        ComboSuppressionModel.from_report_row(
            {
                "cards": ["A", "B"],
                "reason": "missing_card",
                "claim_id": "claim",
                "missing_cards": {"A": True, "B": True},
            }
        )


@pytest.mark.parametrize(
    "value",
    ["nan", "NaN", "inf", "-inf", "Infinity", "-Infinity", "not-a-number"],
)
def test_combo_values_must_be_finite_decimal_strings(value: str) -> None:
    with pytest.raises(ValueError, match="combo_value_invalid"):
        ComboDecisionModel(
            rule_id="invalid_value",
            cards=("A", "B"),
            timing=ComboTiming.SAME_TURN,
            values=(value, "2"),
            condition="*",
            source_claim_ids=("claim",),
            confidence="source_backed",
            source_refs=(),
            claim_id="claim",
        )


def test_dictionary_compile_adapter_validates_the_complete_plan() -> None:
    row = {
        "rule_id": "duplicate",
        "cards": ["A", "B"],
        "values": ["10", "10"],
        "source_claim_ids": ["claim"],
    }

    with pytest.raises(ValueError, match="combo_decision_id_duplicate"):
        compile_combo(
            {
                "deck_name": "Fixture",
                "combos": [row, row],
            }
        )
    with pytest.raises(ValueError, match="Invalid combo sequence collection"):
        compile_combo({"deck_name": "Fixture", "combos": ""})


@pytest.mark.parametrize("field_name", ["decisions", "suppressions"])
@pytest.mark.parametrize(
    "container_kind",
    [
        "mapping",
        "set",
        "frozenset",
        "generator",
        "range",
        "str",
        "bytes",
        "bytearray",
        "memoryview",
    ],
)
def test_combo_plan_requires_ordered_list_or_tuple_fields(
    field_name: str,
    container_kind: str,
) -> None:
    values: tuple[object, ...]
    if field_name == "decisions":
        values = (_decision("a"), _decision("z"))
    else:
        values = (
            ComboSuppressionModel(
                cards=("A", "B"),
                reason_code="missing_card",
                claim_id="claim",
            ),
        )
    value = _invalid_container(container_kind, values)
    fields = {"decisions": (), "suppressions": ()}
    fields[field_name] = value

    with pytest.raises(
        ValueError,
        match=f"combo_{field_name}_container_invalid",
    ):
        ComboPlanModel(**fields)  # type: ignore[arg-type]


@pytest.mark.parametrize("field_name", ["combos", "suppressed"])
@pytest.mark.parametrize(
    "container_kind",
    [
        "mapping",
        "set",
        "frozenset",
        "generator",
        "range",
        "str",
        "bytes",
        "bytearray",
        "memoryview",
    ],
)
def test_combo_plan_report_adapter_requires_ordered_list_or_tuple_rows(
    field_name: str,
    container_kind: str,
) -> None:
    row = (
        {
            "rule_id": "a",
            "cards": ["A", "B"],
            "values": ["10", "10"],
            "source_claim_ids": ["claim-a"],
        }
        if field_name == "combos"
        else {
            "cards": ["A", "B"],
            "reason": "missing_card",
            "claim_id": "claim-a",
        }
    )
    report = {"combos": [], "suppressed": []}
    report[field_name] = _invalid_container(container_kind, (row,))

    with pytest.raises(
        ValueError,
        match="Invalid combo sequence collection",
    ):
        ComboPlanModel.from_report(report)


@pytest.mark.parametrize("entrypoint", ["contract", "sequences"])
@pytest.mark.parametrize(
    "container_kind",
    [
        "mapping",
        "set",
        "frozenset",
        "generator",
        "range",
        "str",
        "bytes",
        "bytearray",
        "memoryview",
    ],
)
def test_legacy_compile_adapters_require_ordered_list_or_tuple_rows(
    entrypoint: str,
    container_kind: str,
) -> None:
    first = _decision("a")
    second = _decision("z")
    invalid = _invalid_container(container_kind, (first, second))

    with pytest.raises(
        ValueError,
        match="Invalid combo sequence collection",
    ):
        if entrypoint == "contract":
            compile_combo({"deck_name": "Fixture", "combos": invalid})
        else:
            compile_combo(
                {"deck_name": "Fixture"},
                sequences=invalid,  # type: ignore[arg-type]
            )


def test_legacy_compile_adapter_preserves_deterministic_multi_row_order() -> None:
    compiled = compile_combo(
        {
            "deck_name": "Fixture",
            "combos": [
                _decision("z"),
                _decision("a"),
            ],
        }
    )

    assert compiled is not None
    assert [
        row["comment"] for row in compiled["ComboList"]["values"]
    ] == ["Fixture: z", "Fixture: a"]


def test_typed_combo_builder_preserves_multi_decision_source_order() -> None:
    first_bundle, deck_identity = build_canonical_combo_case("raw_combo")
    second_bundle, _ = build_canonical_combo_case("claim_same_turn")

    plan = build_typed_combo_plan(
        deck_cards={"CARD_A", "CARD_B"},
        claims=[*first_bundle["claims"], *second_bundle["claims"]],
        deck_identity=deck_identity,
        verified_source_receipts=[
            *first_bundle["canonical_source_receipts"],
            *second_bundle["canonical_source_receipts"],
        ],
    )

    assert tuple(decision.rule_id for decision in plan.decisions) == (
        "raw_combo_combo",
        "claim_same_turn_combo",
    )
    assert [
        row["rule_id"]
        for row in plan.to_report()["combos"]
    ] == ["raw_combo_combo", "claim_same_turn_combo"]
    compiled = compile_combo(plan, deck_name="General Deck")
    assert compiled is not None
    assert [
        row["comment"] for row in compiled["ComboList"]["values"]
    ] == [
        "General Deck: raw_combo_combo",
        "General Deck: claim_same_turn_combo",
    ]


def test_suppression_identity_includes_missing_cards() -> None:
    first = ComboSuppressionModel(
        cards=("A", "B"),
        reason_code="card_not_in_deck",
        claim_id="claim",
        missing_cards=("A",),
    )
    second = ComboSuppressionModel(
        cards=("A", "B"),
        reason_code="card_not_in_deck",
        claim_id="claim",
        missing_cards=("B",),
    )

    plan = ComboPlanModel(decisions=(), suppressions=(first, second))

    assert [
        row["missing_cards"] for row in plan.to_report()["suppressed"]
    ] == [["A"], ["B"]]


def test_typed_combo_builder_preserves_legacy_serialization() -> None:
    bundle, deck_identity = build_canonical_combo_case("claim_cross_turn")

    plan = build_typed_combo_plan(
        deck_cards={"CARD_A", "CARD_B"},
        claims=bundle["claims"],
        deck_identity=deck_identity,
        verified_source_receipts=bundle["canonical_source_receipts"],
    )

    assert isinstance(plan, ComboPlanModel)
    assert plan.decisions[0].timing is ComboTiming.CROSS_TURN
    assert plan.to_report()["combos"][0]["operator"] == ">->"
    assert plan.to_report()["combos"][0]["combo"] == "CARD_A>->CARD_B"


def test_empty_typed_decisions_keep_suppression_but_render_no_combo() -> None:
    plan = ComboPlanModel(
        decisions=(),
        suppressions=(
            ComboSuppressionModel(
                cards=("SW_075", "UNG_832", "DINO_402", "ULD_717"),
                reason_code="combo_requires_public_guide_source",
                claim_id="claim_6fab20d29b8d",
            ),
        ),
    )

    assert plan.to_report() == {
        "combos": [],
        "suppressed": [
            {
                "claim_id": "claim_6fab20d29b8d",
                "cards": ["SW_075", "UNG_832", "DINO_402", "ULD_717"],
                "reason": "combo_requires_public_guide_source",
            }
        ],
    }
    assert compile_combo(plan, deck_name="Boarlock") is None


def _decision(rule_id: str) -> ComboDecisionModel:
    return ComboDecisionModel(
        rule_id=rule_id,
        cards=("A", "B"),
        timing=ComboTiming.SAME_TURN,
        values=("10", "10"),
        condition="*",
        source_claim_ids=(f"claim-{rule_id}",),
        confidence="source_backed",
        source_refs=(),
        claim_id=f"claim-{rule_id}",
    )


def _invalid_container(
    kind: str,
    values: tuple[object, ...],
) -> object:
    if kind == "mapping":
        return {
            f"item-{index}": value
            for index, value in enumerate(values)
        }
    if kind == "set":
        try:
            return set(values)
        except TypeError:
            return set()
    if kind == "frozenset":
        try:
            return frozenset(values)
        except TypeError:
            return frozenset()
    if kind == "generator":
        return (value for value in values)
    if kind == "range":
        return range(len(values))
    if kind == "str":
        return "invalid"
    if kind == "bytes":
        return b"invalid"
    if kind == "bytearray":
        return bytearray(b"invalid")
    if kind == "memoryview":
        return memoryview(b"invalid")
    raise AssertionError(f"unknown test container kind: {kind}")
