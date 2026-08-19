from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, Callable

import pytest

from hsconfig.package_request import FrozenJsonDocument
from hsconfig.starter_candidate import (
    ValidatedStarterCandidate,
    validate_starter_candidate,
)
from hsconfig.starter_context import StarterContext, build_starter_context
from hsconfig.starter_contract import (
    STARTER_CANDIDATE_FIELDS,
    STARTER_SCHEMA_VERSION,
)
from hsconfig.starter_document import StarterDocument, seal_starter_document
from tests.helpers.audited_package_request import audited_request


PROACTIVE_SUMMARY = (
    "Prioritize early pressure while preserving a bounded refill line."
)
ROLE_SUMMARIES = {
    "proactive_tempo": PROACTIVE_SUMMARY,
    "balanced": "Balance early pressure with measured resource use.",
    "resource_oriented": "Preserve resources while keeping a bounded pressure line.",
}


def build_shadowpriest_context(tmp_path: Path) -> StarterContext:
    return build_starter_context(audited_request(tmp_path, "ShadowPriest").snapshot)


def candidate_draft(
    context: StarterContext,
    *,
    candidate_id: str = "candidate-1",
    revision: int = 1,
    role: str = "proactive_tempo",
    changed_globalvalue_key: str = "FirstTurnValueWeight",
    changed_globalvalue_value: str = "0.75",
) -> dict[str, Any]:
    context_value = context.document.to_value()
    globalvalues = deepcopy(context_value["globalvalues_baseline"]["values"])
    globalvalues[changed_globalvalue_key]["values"][0]["value"] = (
        changed_globalvalue_value
    )
    mulligan_rule = {
        "rule_id": "keep-toy-518",
        "selector_kind": "card",
        "selector": "TOY_518",
        "action": "hold",
        "condition": "*",
    }
    card_rule = {
        "rule_id": "darkbishop-mind-spike",
        "source_card_id": "SW_448",
        "runtime_card_id": "EX1_625t",
        "link_kind": "hero_power_transform",
        "behavior_block": "BeforeUseHeroPowerBonus",
        "condition": "*",
        "value": "12",
    }
    card_dispositions = []
    for card in context_value["cards"]:
        card_id = card["card_id"]
        rule_ids = {
            "SW_448": ["darkbishop-mind-spike"],
            "TOY_518": ["keep-toy-518"],
        }.get(card_id, [])
        card_dispositions.append(
            {
                "card_id": card_id,
                "disposition": (
                    "configured" if rule_ids else "deliberately_unconfigured"
                ),
                "rule_ids": rule_ids,
                "reason": (
                    "Candidate contains a bounded explicit rule."
                    if rule_ids
                    else "No additional runtime rule is justified."
                ),
            }
        )
    return {
        "schema_version": STARTER_SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "candidate_revision": revision,
        "starter_context_sha256": context.document.content_sha256,
        "deck_fingerprint": context.deck_fingerprint,
        "strategy_summary": {
            "role": role,
            "summary": ROLE_SUMMARIES[role],
        },
        "mulligan": [mulligan_rule],
        "globalvalues": globalvalues,
        "card_rules": [card_rule],
        "combo": None,
        "card_dispositions": card_dispositions,
        "rule_rationales": {
            "darkbishop-mind-spike": (
                "The transformed hero power is owned by Mind Spike."
            ),
            "keep-toy-518": "Use one physical early-pressure keep.",
        },
        "assumptions": ["No post-game evidence is used."],
    }


def sealed_candidate(
    context: StarterContext,
    *,
    candidate_id: str = "candidate-1",
    revision: int = 1,
    role: str = "proactive_tempo",
    changed_globalvalue_key: str = "FirstTurnValueWeight",
    changed_globalvalue_value: str = "0.75",
    mutate: Callable[[dict[str, Any]], None] | None = None,
) -> StarterDocument:
    draft = candidate_draft(
        context,
        candidate_id=candidate_id,
        revision=revision,
        role=role,
        changed_globalvalue_key=changed_globalvalue_key,
        changed_globalvalue_value=changed_globalvalue_value,
    )
    if mutate is not None:
        mutate(draft)
    return seal_starter_document(
        draft,
        expected_fields=STARTER_CANDIDATE_FIELDS,
        schema_version=STARTER_SCHEMA_VERSION,
    )


def forged_candidate_document(
    context: StarterContext,
    *,
    mutate: Callable[[dict[str, Any]], None],
) -> StarterDocument:
    value = sealed_candidate(context).to_value()
    mutate(value)
    return StarterDocument(
        document=FrozenJsonDocument.from_value(value),
        content_sha256=str(value["content_sha256"]),
    )


def forged_starter_context(
    context: StarterContext,
    *,
    mutate: Callable[[dict[str, Any]], None],
) -> StarterContext:
    value = context.document.to_value()
    mutate(value)
    return StarterContext(
        document=StarterDocument(
            document=FrozenJsonDocument.from_value(value),
            content_sha256=str(value["content_sha256"]),
        ),
        deck_fingerprint=context.deck_fingerprint,
        globalvalues_baseline_sha256=context.globalvalues_baseline_sha256,
    )


def _set_card_rule(draft: dict[str, Any], key: str, value: Any) -> None:
    draft["card_rules"][0][key] = value


def _remove_globalvalue(draft: dict[str, Any]) -> None:
    draft["globalvalues"].pop("GlobalTaunt")


def _add_globalvalue(draft: dict[str, Any]) -> None:
    draft["globalvalues"]["InventedValue"] = {
        "values": [{"condition": "*", "value": "1"}]
    }


def _change_metadata(draft: dict[str, Any]) -> None:
    draft["globalvalues"]["GameCardId"] = "Invented"


def _unsafe_globalvalue_condition(draft: dict[str, Any]) -> None:
    draft["globalvalues"]["GlobalTaunt"]["values"][0]["condition"] = (
        "play this if ahead"
    )


def _repeat_globalvalue_condition(
    draft: dict[str, Any], *, value: str
) -> None:
    draft["globalvalues"]["GlobalTaunt"]["values"].append(
        {"condition": "*", "value": value}
    )


def _set_mulligan_selector(
    draft: dict[str, Any], selector_kind: str, selector: str
) -> None:
    draft["mulligan"][0]["selector_kind"] = selector_kind
    draft["mulligan"][0]["selector"] = selector


def _add_equivalent_mulligan_rule(
    draft: dict[str, Any],
    *,
    selector_kind: str,
    first_selector: str,
    second_selector: str,
    second_action: str,
) -> None:
    first = draft["mulligan"][0]
    first["selector_kind"] = selector_kind
    first["selector"] = first_selector
    second = deepcopy(first)
    second["rule_id"] = "equivalent-mulligan"
    second["selector"] = second_selector
    second["action"] = second_action
    draft["mulligan"].append(second)
    draft["rule_rationales"][second["rule_id"]] = (
        "Equivalent selector coverage must not add another runtime decision."
    )
    covered_cards = {
        card_id.strip()
        for card_id in first_selector.replace("+", ",").split(",")
    }
    for row in draft["card_dispositions"]:
        if row["card_id"] in covered_cards:
            row["disposition"] = "configured"
            if second["rule_id"] not in row["rule_ids"]:
                row["rule_ids"].append(second["rule_id"])


def _add_overlapping_mulligan_rule(
    draft: dict[str, Any],
    *,
    first_kind: str,
    first_selector: str,
    second_kind: str,
    second_selector: str,
    second_action: str,
    first_condition: str = "*",
    second_condition: str | None = None,
) -> None:
    first = draft["mulligan"][0]
    first["selector_kind"] = first_kind
    first["selector"] = first_selector
    first["condition"] = first_condition
    second = deepcopy(first)
    second["rule_id"] = "overlapping-mulligan"
    second["selector_kind"] = second_kind
    second["selector"] = second_selector
    second["action"] = second_action
    second["condition"] = (
        first_condition if second_condition is None else second_condition
    )
    draft["mulligan"].append(second)
    draft["rule_rationales"][second["rule_id"]] = (
        "Exercise shared physical-card Mulligan coverage."
    )


def _add_same_action_mulligan_overlap(draft: dict[str, Any]) -> None:
    _add_overlapping_mulligan_rule(
        draft,
        first_kind="card_list",
        first_selector="TOY_518, TOY_381",
        second_kind="card",
        second_selector="TOY_381",
        second_action="hold",
    )
    _set_disposition_rule_ids(
        draft,
        "TOY_381",
        ["keep-toy-518", "overlapping-mulligan"],
    )


def _add_mutually_exclusive_mulligan_overlap(
    draft: dict[str, Any]
) -> None:
    _add_overlapping_mulligan_rule(
        draft,
        first_kind="card_list",
        first_selector="TOY_518, TOY_381",
        second_kind="card",
        second_selector="TOY_381",
        second_action="discard",
        first_condition="coin",
        second_condition="nocoin",
    )
    _set_disposition_rule_ids(
        draft,
        "TOY_381",
        ["keep-toy-518", "overlapping-mulligan"],
    )


def _add_second_mulligan_for_digest(
    draft: dict[str, Any], *, list_selector: str
) -> None:
    first = draft["mulligan"][0]
    first["selector_kind"] = "card_list"
    first["selector"] = list_selector
    second = {
        "rule_id": "keep-sw-444",
        "selector_kind": "card",
        "selector": "SW_444",
        "action": "hold",
        "condition": "*",
    }
    draft["mulligan"].append(second)
    draft["rule_rationales"][second["rule_id"]] = (
        "Keep the additional independent physical card."
    )
    _set_disposition_rule_ids(draft, "GVG_009", ["keep-toy-518"])
    _set_disposition_rule_ids(draft, "SW_444", [second["rule_id"]])


def _duplicate_card_rule(draft: dict[str, Any]) -> None:
    duplicate = deepcopy(draft["card_rules"][0])
    duplicate["rule_id"] = "darkbishop-mind-spike-duplicate"
    draft["card_rules"].append(duplicate)
    draft["rule_rationales"][duplicate["rule_id"]] = "Duplicate semantic row."


def _conflict_card_rule(draft: dict[str, Any]) -> None:
    conflict = deepcopy(draft["card_rules"][0])
    conflict["rule_id"] = "darkbishop-mind-spike-conflict"
    conflict["value"] = "13"
    draft["card_rules"].append(conflict)
    draft["rule_rationales"][conflict["rule_id"]] = "Conflicting semantic row."


def _remove_disposition(draft: dict[str, Any]) -> None:
    draft["card_dispositions"].pop()


def _duplicate_disposition(draft: dict[str, Any]) -> None:
    draft["card_dispositions"].append(
        deepcopy(draft["card_dispositions"][0])
    )


def _add_unknown_disposition(draft: dict[str, Any]) -> None:
    draft["card_dispositions"].append(
        {
            "card_id": "UNKNOWN_999",
            "disposition": "deliberately_unconfigured",
            "rule_ids": [],
            "reason": "Not in the deck.",
        }
    )


def _expand_physical_dispositions(draft: dict[str, Any]) -> None:
    by_id = {row["card_id"]: row for row in draft["card_dispositions"]}
    context_counts = {
        "CFM_637": 1,
        "DRG_056": 2,
        "DS1_233": 2,
        "GVG_009": 2,
        "NX2_019": 2,
        "REV_290": 2,
        "SCH_514": 2,
        "SW_444": 2,
        "SW_446": 2,
        "SW_448": 1,
        "TOY_381": 2,
        "TOY_518": 2,
        "VAC_419": 2,
        "VAC_512": 2,
        "WON_065": 2,
        "YOD_032": 2,
    }
    draft["card_dispositions"] = [
        deepcopy(by_id[card_id])
        for card_id, count in context_counts.items()
        for _copy in range(count)
    ]


def _add_inexpressible_combo(draft: dict[str, Any]) -> None:
    draft["combo"] = {
        "rule_id": "bad-combo",
        "cards": ["TOY_518", "UNKNOWN_999"],
        "timing": "same_turn",
        "values": ["10", "10"],
        "condition": "*",
    }
    draft["rule_rationales"]["bad-combo"] = "Unknown physical card."


def _set_numeric_surface_value(
    draft: dict[str, Any], *, surface: str, value: Any
) -> None:
    if surface == "card":
        draft["card_rules"][0]["value"] = value
        return
    draft["combo"] = {
        "rule_id": "numeric-combo",
        "cards": ["TOY_518", "TOY_381"],
        "timing": "same_turn",
        "values": [value, "10"],
        "condition": "*",
    }
    draft["rule_rationales"]["numeric-combo"] = (
        "Exercise the exact Combo numeric contract."
    )


def _disposition(draft: dict[str, Any], card_id: str) -> dict[str, Any]:
    return next(
        row for row in draft["card_dispositions"] if row["card_id"] == card_id
    )


def _set_disposition_rule_ids(
    draft: dict[str, Any], card_id: str, rule_ids: list[str]
) -> None:
    row = _disposition(draft, card_id)
    row["rule_ids"] = rule_ids
    row["disposition"] = (
        "configured" if rule_ids else "deliberately_unconfigured"
    )


def _swap_disposition_owners(draft: dict[str, Any]) -> None:
    _set_disposition_rule_ids(draft, "SW_448", ["keep-toy-518"])
    _set_disposition_rule_ids(
        draft,
        "TOY_518",
        ["darkbishop-mind-spike"],
    )


def _omit_disposition_owner(draft: dict[str, Any]) -> None:
    _set_disposition_rule_ids(draft, "TOY_518", [])


def _duplicate_disposition_owner(draft: dict[str, Any]) -> None:
    _set_disposition_rule_ids(draft, "CFM_637", ["keep-toy-518"])


def _add_expanded_physical_rule(
    draft: dict[str, Any], *, surface: str
) -> None:
    if surface in {"card_list", "plus_combo"}:
        separator = ", " if surface == "card_list" else " + "
        draft["mulligan"][0]["selector_kind"] = surface
        draft["mulligan"][0]["selector"] = separator.join(
            ("TOY_518", "TOY_381")
        )
        _set_disposition_rule_ids(draft, "TOY_381", ["keep-toy-518"])
        return
    _set_numeric_surface_value(draft, surface="combo", value="10")
    for card_id in ("TOY_518", "TOY_381"):
        row = _disposition(draft, card_id)
        _set_disposition_rule_ids(
            draft,
            card_id,
            [*row["rule_ids"], "numeric-combo"],
        )


def _set_long_exact_runtime_value(
    draft: dict[str, Any], *, surface: str, value: str
) -> None:
    if surface == "card":
        draft["card_rules"][0]["value"] = value
        return
    _add_expanded_physical_rule(draft, surface="combo")
    draft["combo"]["values"][0] = value


def _make_default_only(draft: dict[str, Any], context: StarterContext) -> None:
    draft["globalvalues"] = deepcopy(
        context.document.to_value()["globalvalues_baseline"]["values"]
    )
    draft["card_rules"] = []
    draft["combo"] = None
    draft["rule_rationales"] = {"keep-toy-518": "Physical keep remains."}
    for row in draft["card_dispositions"]:
        if row["card_id"] == "SW_448":
            row["disposition"] = "deliberately_unconfigured"
            row["rule_ids"] = []


def _make_semantically_default_only(
    draft: dict[str, Any], context: StarterContext
) -> None:
    _make_default_only(draft, context)
    draft["globalvalues"]["FirstTurnValueWeight"]["values"][0][
        "value"
    ] = "+0.0"


@pytest.mark.parametrize(
    ("case", "mutate", "error"),
    [
        (
            "wrong context digest",
            lambda draft: draft.__setitem__(
                "starter_context_sha256", "sha256:" + "0" * 64
            ),
            "starter_candidate_context_sha256_mismatch",
        ),
        (
            "wrong deck fingerprint",
            lambda draft: draft.__setitem__("deck_fingerprint", "0" * 64),
            "starter_candidate_deck_fingerprint_mismatch",
        ),
        (
            "unknown physical card",
            lambda draft: _set_card_rule(
                draft, "source_card_id", "UNKNOWN_999"
            ),
            "starter_candidate_card_id_unknown",
        ),
        (
            "unauthorized linked owner",
            lambda draft: _set_card_rule(
                draft, "runtime_card_id", "HERO_999"
            ),
            "starter_candidate_runtime_owner_unauthorized",
        ),
        (
            "unsupported block",
            lambda draft: _set_card_rule(
                draft, "behavior_block", "InventedBonus"
            ),
            "starter_candidate_behavior_block_invalid",
        ),
        (
            "document controlled surface",
            lambda draft: _set_card_rule(draft, "surface", "Presume.json"),
            "starter_candidate_card_rule_fields_invalid",
        ),
        (
            "unsafe card condition",
            lambda draft: _set_card_rule(
                draft, "condition", "coin | nocoin"
            ),
            "starter_candidate_condition_invalid",
        ),
        (
            "non finite card value",
            lambda draft: _set_card_rule(draft, "value", "NaN"),
            "starter_candidate_card_value_invalid",
        ),
        (
            "card value above bound",
            lambda draft: _set_card_rule(draft, "value", "10001"),
            "starter_candidate_card_value_invalid",
        ),
        (
            "missing globalvalue",
            _remove_globalvalue,
            "starter_candidate_globalvalues_keys_invalid",
        ),
        (
            "extra globalvalue",
            _add_globalvalue,
            "starter_candidate_globalvalues_keys_invalid",
        ),
        (
            "changed metadata key",
            _change_metadata,
            "starter_candidate_globalvalues_metadata_mismatch",
        ),
        (
            "unsafe globalvalue condition",
            _unsafe_globalvalue_condition,
            "starter_candidate_globalvalue_condition_invalid",
        ),
        (
            "globalvalue above bound",
            lambda draft: draft["globalvalues"]["GlobalTaunt"]["values"][
                0
            ].__setitem__("value", "1001"),
            "starter_candidate_globalvalue_value_invalid",
        ),
        (
            "wildcard mulligan",
            lambda draft: _set_mulligan_selector(draft, "wildcard", "*"),
            "starter_candidate_mulligan_selector_forbidden",
        ),
        (
            "drop mulligan",
            lambda draft: _set_mulligan_selector(draft, "drop_n", "DROP2"),
            "starter_candidate_mulligan_selector_forbidden",
        ),
        (
            "missing mulligan",
            lambda draft: draft.__setitem__("mulligan", []),
            "starter_candidate_mulligan_required",
        ),
        (
            "duplicate runtime row",
            _duplicate_card_rule,
            "starter_candidate_runtime_row_duplicate",
        ),
        (
            "conflicting runtime row",
            _conflict_card_rule,
            "starter_candidate_runtime_row_conflict",
        ),
        (
            "physical transformed owner",
            lambda draft: (
                _set_card_rule(draft, "runtime_card_id", "SW_448"),
                _set_card_rule(draft, "link_kind", "self"),
            ),
            "starter_candidate_runtime_owner_unauthorized",
        ),
        (
            "missing disposition",
            _remove_disposition,
            "starter_candidate_card_dispositions_invalid",
        ),
        (
            "duplicate disposition",
            _duplicate_disposition,
            "starter_candidate_card_dispositions_invalid",
        ),
        (
            "extra disposition",
            _add_unknown_disposition,
            "starter_candidate_card_dispositions_invalid",
        ),
        (
            "physical copy dispositions",
            _expand_physical_dispositions,
            "starter_candidate_card_dispositions_invalid",
        ),
        (
            "inexpressible combo",
            _add_inexpressible_combo,
            "starter_candidate_combo_card_invalid",
        ),
        (
            "fabricated guide claim fields",
            lambda draft: _set_card_rule(
                draft, "source_claim_ids", ["invented-guide-claim"]
            ),
            "starter_candidate_card_rule_fields_invalid",
        ),
        (
            "document controlled path",
            lambda draft: draft["strategy_summary"].__setitem__(
                "output_path", "C:" + "/runtime"
            ),
            "starter_candidate_path_forbidden",
        ),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_candidate_rejects_one_invalid_field_at_a_time(
    tmp_path: Path,
    case: str,
    mutate: Callable[[dict[str, Any]], None],
    error: str,
) -> None:
    # Break caught: one untrusted candidate field bypasses the closed runtime gate.
    del case
    context = build_shadowpriest_context(tmp_path)
    document = sealed_candidate(context, mutate=mutate)

    with pytest.raises(ValueError, match=error):
        validate_starter_candidate(document, context=context)


def test_candidate_rejects_wholly_baseline_default_only_runtime_intent(
    tmp_path: Path,
) -> None:
    # Break caught: a prose-heavy candidate can pass without a material runtime change.
    context = build_shadowpriest_context(tmp_path)
    document = sealed_candidate(
        context,
        mutate=lambda draft: _make_default_only(draft, context),
    )

    with pytest.raises(
        ValueError,
        match="starter_candidate_material_runtime_intent_required",
    ):
        validate_starter_candidate(document, context=context)


def test_candidate_rejects_semantically_equivalent_baseline_spelling(
    tmp_path: Path,
) -> None:
    # Break caught: +0.0 is treated as a material change from baseline 0.
    context = build_shadowpriest_context(tmp_path)
    document = sealed_candidate(
        context,
        mutate=lambda draft: _make_semantically_default_only(draft, context),
    )

    with pytest.raises(
        ValueError,
        match="starter_candidate_material_runtime_intent_required",
    ):
        validate_starter_candidate(document, context=context)


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (
            lambda value: value.__setitem__("schema_version", True),
            "starter_candidate_schema_version_invalid",
        ),
        (
            lambda value: value.__setitem__(
                "content_sha256", "sha256:" + "0" * 64
            ),
            "starter_candidate_content_sha256_invalid",
        ),
    ],
)
def test_candidate_rejects_forged_public_starter_document(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
    error: str,
) -> None:
    # Break caught: a direct public dataclass bypasses Task 2 sealing authority.
    context = build_shadowpriest_context(tmp_path)
    document = forged_candidate_document(context, mutate=mutate)

    with pytest.raises(ValueError, match=error):
        validate_starter_candidate(document, context=context)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.__setitem__("schema_version", True),
        lambda value: value.__setitem__(
            "content_sha256", "sha256:" + "0" * 64
        ),
    ],
)
def test_candidate_rejects_forged_public_starter_context(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    # Break caught: direct context dataclasses bypass Task 2 sealing authority.
    context = build_shadowpriest_context(tmp_path)
    candidate = sealed_candidate(context)
    forged = forged_starter_context(context, mutate=mutate)

    with pytest.raises(
        ValueError,
        match="^starter_candidate_context_invalid$",
    ):
        validate_starter_candidate(candidate, context=forged)


@pytest.mark.parametrize(
    ("selector_kind", "first_selector", "second_selector"),
    [
        ("card", "TOY_518", "TOY_518"),
        ("card_list", "TOY_518, TOY_381", "TOY_381,TOY_518"),
        ("plus_combo", "TOY_518 + TOY_381", "TOY_381+TOY_518"),
    ],
)
@pytest.mark.parametrize(
    ("second_action", "error"),
    [
        ("hold", "starter_candidate_mulligan_duplicate"),
        ("discard", "starter_candidate_mulligan_conflict"),
    ],
)
def test_candidate_rejects_duplicate_or_conflicting_mulligan_match(
    tmp_path: Path,
    selector_kind: str,
    first_selector: str,
    second_selector: str,
    second_action: str,
    error: str,
) -> None:
    # Break caught: textual selector variants can target one canonical match twice.
    context = build_shadowpriest_context(tmp_path)
    document = sealed_candidate(
        context,
        mutate=lambda draft: _add_equivalent_mulligan_rule(
            draft,
            selector_kind=selector_kind,
            first_selector=first_selector,
            second_selector=second_selector,
            second_action=second_action,
        ),
    )

    with pytest.raises(ValueError, match=error):
        validate_starter_candidate(document, context=context)


@pytest.mark.parametrize(
    ("first_kind", "first_selector", "second_kind", "second_selector"),
    [
        ("card_list", "TOY_518, TOY_381", "card", "TOY_381"),
        ("plus_combo", "TOY_518 + TOY_381", "card", "TOY_381"),
        ("card", "TOY_381", "card_list", "TOY_381, SW_444"),
    ],
)
def test_candidate_rejects_opposite_actions_on_overlapping_physical_card(
    tmp_path: Path,
    first_kind: str,
    first_selector: str,
    second_kind: str,
    second_selector: str,
) -> None:
    # Break caught: whole-selector keys miss an opposite action on a shared card.
    context = build_shadowpriest_context(tmp_path)
    document = sealed_candidate(
        context,
        mutate=lambda draft: _add_overlapping_mulligan_rule(
            draft,
            first_kind=first_kind,
            first_selector=first_selector,
            second_kind=second_kind,
            second_selector=second_selector,
            second_action="discard",
        ),
    )

    with pytest.raises(
        ValueError,
        match="^starter_candidate_mulligan_conflict$",
    ):
        validate_starter_candidate(document, context=context)


def test_candidate_allows_same_action_on_overlapping_physical_card(
    tmp_path: Path,
) -> None:
    # Break caught: overlap closure rejects two compatible holds as a conflict.
    context = build_shadowpriest_context(tmp_path)
    document = sealed_candidate(
        context,
        mutate=_add_same_action_mulligan_overlap,
    )

    validated = validate_starter_candidate(document, context=context)

    assert len(validated.mulligan_plan.rules) == 2


@pytest.mark.parametrize(
    ("first_condition", "second_condition"),
    [
        ("*", "coin"),
        (
            "coin AND my_hand(count(),cardid=TOY_518) > 0",
            "coin",
        ),
    ],
)
def test_candidate_rejects_opposite_actions_on_overlapping_conditions(
    tmp_path: Path,
    first_condition: str,
    second_condition: str,
) -> None:
    # Break caught: textually different overlapping conditions evade conflict.
    context = build_shadowpriest_context(tmp_path)
    document = sealed_candidate(
        context,
        mutate=lambda draft: _add_overlapping_mulligan_rule(
            draft,
            first_kind="card_list",
            first_selector="TOY_518, TOY_381",
            second_kind="card",
            second_selector="TOY_381",
            second_action="discard",
            first_condition=first_condition,
            second_condition=second_condition,
        ),
    )

    with pytest.raises(
        ValueError,
        match="^starter_candidate_mulligan_conflict$",
    ):
        validate_starter_candidate(document, context=context)


def test_candidate_allows_opposite_actions_on_coin_nocoin_conditions(
    tmp_path: Path,
) -> None:
    # Break caught: conservative overlap rejects a provably disjoint branch pair.
    context = build_shadowpriest_context(tmp_path)
    document = sealed_candidate(
        context,
        mutate=_add_mutually_exclusive_mulligan_overlap,
    )

    validated = validate_starter_candidate(document, context=context)

    assert len(validated.mulligan_plan.rules) == 2


@pytest.mark.parametrize(
    ("value", "error"),
    [
        ("1.02", "starter_candidate_globalvalue_row_duplicate"),
        ("2", "starter_candidate_globalvalue_row_conflict"),
    ],
)
def test_candidate_rejects_repeated_globalvalue_condition(
    tmp_path: Path,
    value: str,
    error: str,
) -> None:
    # Break caught: one key can silently carry two rows for the same match.
    context = build_shadowpriest_context(tmp_path)
    document = sealed_candidate(
        context,
        mutate=lambda draft: _repeat_globalvalue_condition(
            draft,
            value=value,
        ),
    )

    with pytest.raises(ValueError, match=error):
        validate_starter_candidate(document, context=context)


@pytest.mark.parametrize(
    "value",
    ["1e2", "1_0", "１２", "+-1", "1."],
)
@pytest.mark.parametrize(
    ("surface", "error"),
    [
        ("card", "starter_candidate_card_value_invalid"),
        ("combo", "starter_candidate_combo_values_invalid"),
    ],
)
def test_candidate_rejects_non_package_decimal_grammar(
    tmp_path: Path,
    surface: str,
    error: str,
    value: str,
) -> None:
    # Break caught: Decimal accepts syntax the downstream package does not emit.
    context = build_shadowpriest_context(tmp_path)
    document = sealed_candidate(
        context,
        mutate=lambda draft: _set_numeric_surface_value(
            draft,
            surface=surface,
            value=value,
        ),
    )

    with pytest.raises(ValueError, match=error):
        validate_starter_candidate(document, context=context)


@pytest.mark.parametrize(
    "mutate",
    [
        _swap_disposition_owners,
        _omit_disposition_owner,
        _duplicate_disposition_owner,
    ],
)
def test_candidate_rejects_inexact_physical_rule_ownership(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    # Break caught: known rule IDs can be swapped, omitted, or assigned twice.
    context = build_shadowpriest_context(tmp_path)
    document = sealed_candidate(context, mutate=mutate)

    with pytest.raises(
        ValueError,
        match="starter_candidate_card_dispositions_invalid",
    ):
        validate_starter_candidate(document, context=context)


@pytest.mark.parametrize("surface", ["card_list", "plus_combo", "combo"])
def test_candidate_maps_expanded_rules_to_every_physical_participant(
    tmp_path: Path,
    surface: str,
) -> None:
    # Break caught: only the first selector or Combo card owns the runtime rule.
    context = build_shadowpriest_context(tmp_path)
    document = sealed_candidate(
        context,
        mutate=lambda draft: _add_expanded_physical_rule(
            draft,
            surface=surface,
        ),
    )

    validated = validate_starter_candidate(document, context=context)

    assert validated.candidate_id == "candidate-1"


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (
            lambda draft: draft["mulligan"][0].__setitem__("action", []),
            "starter_candidate_mulligan_action_invalid",
        ),
        (
            lambda draft: _set_card_rule(draft, "source_card_id", []),
            "starter_candidate_card_id_unknown",
        ),
        (
            lambda draft: _set_card_rule(draft, "behavior_block", []),
            "starter_candidate_behavior_block_invalid",
        ),
        (
            lambda draft: _set_card_rule(draft, "runtime_card_id", []),
            "starter_candidate_runtime_owner_unauthorized",
        ),
        (
            lambda draft: _disposition(draft, "TOY_518").__setitem__(
                "card_id", []
            ),
            "starter_candidate_card_dispositions_invalid",
        ),
        (
            lambda draft: _disposition(draft, "TOY_518").__setitem__(
                "disposition", []
            ),
            "starter_candidate_card_dispositions_invalid",
        ),
        (
            lambda draft: _disposition(draft, "TOY_518").__setitem__(
                "rule_ids", [[]]
            ),
            "starter_candidate_card_dispositions_invalid",
        ),
        (
            lambda draft: _set_numeric_surface_value(
                draft,
                surface="combo",
                value=[],
            ),
            "starter_candidate_combo_values_invalid",
        ),
    ],
)
def test_candidate_rejects_unhashable_nested_json_with_stable_error(
    tmp_path: Path,
    mutate: Callable[[dict[str, Any]], None],
    error: str,
) -> None:
    # Break caught: wrong JSON types leak Python set/dict membership TypeErrors.
    context = build_shadowpriest_context(tmp_path)
    document = sealed_candidate(context, mutate=mutate)

    with pytest.raises(ValueError, match=f"^{error}$"):
        validate_starter_candidate(document, context=context)


def test_valid_shadowpriest_candidate_returns_only_immutable_typed_authority(
    tmp_path: Path,
) -> None:
    # Break caught: validation leaves mutable caller JSON or loses typed runtime rows.
    context = build_shadowpriest_context(tmp_path)
    document = sealed_candidate(context)

    validated = validate_starter_candidate(document, context=context)

    assert isinstance(validated, ValidatedStarterCandidate)
    assert validated.document is document
    assert validated.candidate_id == "candidate-1"
    assert validated.candidate_revision == 1
    assert validated.strategy_role == "proactive_tempo"
    assert validated.runtime_intent_sha256.startswith("sha256:")
    assert len(validated.globalvalues.to_value()) == 38
    assert len(validated.mulligan_plan.rules) == 1
    assert validated.mulligan_plan.rules[0].source_claim_ids == ()
    assert validated.mulligan_plan.rules[0].claim_id.startswith("starter:")
    assert validated.combo_plan.decisions == ()
    assert [row.to_value()["card_id"] for row in validated.card_behavior_rows] == [
        "EX1_625t"
    ]
    detached = validated.globalvalues.to_value()
    detached["GameCardId"] = "mutated"
    assert validated.globalvalues.to_value()["GameCardId"] == "GlobalValues"
    with pytest.raises(FrozenInstanceError):
        validated.candidate_revision = 2  # type: ignore[misc]


def test_runtime_intent_digest_ignores_rule_labels_and_rationale_prose(
    tmp_path: Path,
) -> None:
    # Break caught: renamed labels make narrative-only candidates look diverse.
    context = build_shadowpriest_context(tmp_path)
    original = validate_starter_candidate(
        sealed_candidate(context),
        context=context,
    )

    def rename_labels(draft: dict[str, Any]) -> None:
        replacements = {
            "keep-toy-518": "renamed-mulligan-label",
            "darkbishop-mind-spike": "renamed-card-label",
        }
        draft["mulligan"][0]["rule_id"] = replacements["keep-toy-518"]
        draft["card_rules"][0]["rule_id"] = replacements[
            "darkbishop-mind-spike"
        ]
        draft["rule_rationales"] = {
            replacements[rule_id]: rationale + " Different prose."
            for rule_id, rationale in draft["rule_rationales"].items()
        }
        for row in draft["card_dispositions"]:
            row["rule_ids"] = [
                replacements.get(rule_id, rule_id)
                for rule_id in row["rule_ids"]
            ]

    relabeled = validate_starter_candidate(
        sealed_candidate(context, mutate=rename_labels),
        context=context,
    )

    assert relabeled.document.content_sha256 != original.document.content_sha256
    assert relabeled.runtime_intent_sha256 == original.runtime_intent_sha256


def test_runtime_intent_digest_canonicalizes_all_numeric_semantics(
    tmp_path: Path,
) -> None:
    # Break caught: equivalent decimal or safe-expression spelling appears diverse.
    context = build_shadowpriest_context(tmp_path)
    decimal = validate_starter_candidate(
        sealed_candidate(
            context,
            changed_globalvalue_value="0.75",
            mutate=lambda draft: _set_card_rule(draft, "value", "12"),
        ),
        context=context,
    )
    equivalent = validate_starter_candidate(
        sealed_candidate(
            context,
            changed_globalvalue_value="3/4",
            mutate=lambda draft: _set_card_rule(draft, "value", "+12.00"),
        ),
        context=context,
    )

    assert equivalent.document.content_sha256 != decimal.document.content_sha256
    assert equivalent.runtime_intent_sha256 == decimal.runtime_intent_sha256


def test_runtime_intent_digest_sorts_canonical_mulligan_semantics(
    tmp_path: Path,
) -> None:
    # Break caught: raw first-selector order changes the semantic row order.
    context = build_shadowpriest_context(tmp_path)

    def validated(selector: str) -> ValidatedStarterCandidate:
        return validate_starter_candidate(
            sealed_candidate(
                context,
                mutate=lambda draft: _add_second_mulligan_for_digest(
                    draft,
                    list_selector=selector,
                ),
            ),
            context=context,
        )

    original = validated("GVG_009, TOY_518")
    reversed_selector = validated("TOY_518,GVG_009")

    assert original.runtime_intent_sha256 == (
        reversed_selector.runtime_intent_sha256
    )


def test_runtime_intent_digest_preserves_plus_combo_group_semantics(
    tmp_path: Path,
) -> None:
    # Break caught: atomic coverage folding erases conjunctive plus-combo intent.
    context = build_shadowpriest_context(tmp_path)
    card_list = validate_starter_candidate(
        sealed_candidate(
            context,
            mutate=lambda draft: _add_expanded_physical_rule(
                draft,
                surface="card_list",
            ),
        ),
        context=context,
    )
    plus_combo = validate_starter_candidate(
        sealed_candidate(
            context,
            mutate=lambda draft: _add_expanded_physical_rule(
                draft,
                surface="plus_combo",
            ),
        ),
        context=context,
    )

    assert card_list.runtime_intent_sha256 != plus_combo.runtime_intent_sha256


@pytest.mark.parametrize("surface", ["card", "combo"])
def test_runtime_intent_digest_preserves_long_exact_decimal_coefficients(
    tmp_path: Path,
    surface: str,
) -> None:
    # Break caught: Decimal.normalize rounds distinct coefficients after 28 digits.
    context = build_shadowpriest_context(tmp_path)
    first_value = "1.1234567890123456789012345678901"
    second_value = "1.1234567890123456789012345678902"
    equivalent_value = "+1.12345678901234567890123456789010"

    def validated(value: str) -> ValidatedStarterCandidate:
        return validate_starter_candidate(
            sealed_candidate(
                context,
                mutate=lambda draft: _set_long_exact_runtime_value(
                    draft,
                    surface=surface,
                    value=value,
                ),
            ),
            context=context,
        )

    first = validated(first_value)
    distinct = validated(second_value)
    equivalent = validated(equivalent_value)

    assert first.runtime_intent_sha256 != distinct.runtime_intent_sha256
    assert first.runtime_intent_sha256 == equivalent.runtime_intent_sha256
