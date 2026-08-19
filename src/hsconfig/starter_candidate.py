"""Typed fail-closed validation for one optimized starter candidate."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import math
import re
from typing import Any

from hsconfig.compile_globalvalues import (
    _numeric_value,
    validate_globalvalues_overlay_value,
)
from hsconfig.condition_format import classify_runtime_condition
from hsconfig.globalvalues_decisions import (
    canonical_globalvalues_baseline_sha256,
)
from hsconfig.mulligan_selector import normalize_mulligan_selector
from hsconfig.package_domain import (
    ComboDecisionModel,
    ComboPlanModel,
    ComboTiming,
    MulliganPlanModel,
    MulliganRuleModel,
)
from hsconfig.package_request import FrozenJsonDocument
from hsconfig.runtime_entity_owner import (
    linked_runtime_entity_semantic_surface,
    runtime_entity_owner_relation_is_authorized,
)
from hsconfig.runtime_row_identity import canonicalize_runtime_rows
from hsconfig.starter_context import StarterContext
from hsconfig.starter_contract import (
    STARTER_CANDIDATE_FIELDS,
    STARTER_CARD_DISPOSITION_FIELDS,
    STARTER_CARD_RULE_FIELDS,
    STARTER_COMBO_FIELDS,
    STARTER_CONTEXT_FIELDS,
    STARTER_MULLIGAN_ROW_FIELDS,
    STARTER_SCHEMA_VERSION,
    STARTER_STRATEGY_SUMMARY_FIELDS,
    StarterStrategyRole,
    reject_path_like_fields,
    require_closed_object,
    validate_candidate_revision,
)
from hsconfig.starter_document import StarterDocument, seal_starter_document
from hsconfig.visionai_registry import (
    CARD_BEHAVIOR_BLOCKS,
    STARTER_CARD_VALUE_CONSTRAINT,
    STARTER_COMBO_VALUE_CONSTRAINT,
    STARTER_GLOBALVALUE_CONSTRAINTS,
)


_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_RAW_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_FINITE_DECIMAL_RE = re.compile(
    r"[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)\Z"
)
_CARD_DISPOSITIONS = frozenset(
    {"configured", "deliberately_unconfigured"}
)
_MAX_SUMMARY_CHARS = 2048
_MAX_RATIONALE_CHARS = 4096
_MAX_ASSUMPTIONS = 32


@dataclass(frozen=True, slots=True)
class ValidatedStarterCandidate:
    document: StarterDocument
    candidate_id: str
    candidate_revision: int
    strategy_role: str
    runtime_intent_sha256: str
    mulligan_plan: MulliganPlanModel
    globalvalues: FrozenJsonDocument
    card_behavior_rows: tuple[FrozenJsonDocument, ...]
    combo_plan: ComboPlanModel


def validate_starter_candidate(
    document: StarterDocument,
    *,
    context: StarterContext,
) -> ValidatedStarterCandidate:
    """Validate and freeze one complete candidate against one exact context."""

    if not isinstance(document, StarterDocument):
        raise TypeError("starter_candidate_document_invalid")
    value = _validated_candidate_document_value(document)
    context_value, physical_cards, linked_entities, baseline = (
        _validated_context(context)
    )
    reject_path_like_fields(value, error="starter_candidate_path_forbidden")

    candidate_id = _identifier(
        value.get("candidate_id"),
        error="starter_candidate_id_invalid",
    )
    candidate_revision = validate_candidate_revision(
        value.get("candidate_revision")
    )
    if value.get("starter_context_sha256") != context.document.content_sha256:
        raise ValueError("starter_candidate_context_sha256_mismatch")
    if value.get("deck_fingerprint") != context.deck_fingerprint:
        raise ValueError("starter_candidate_deck_fingerprint_mismatch")

    strategy_role = _validate_strategy_summary(value.get("strategy_summary"))
    mulligan_rows = _validate_mulligan_rows(
        value.get("mulligan"),
        physical_cards=physical_cards,
    )
    globalvalues, globalvalues_changed = _validate_globalvalues(
        value.get("globalvalues"),
        baseline=baseline,
    )
    candidate_card_rows, card_behavior_rows = _validate_card_rules(
        value.get("card_rules"),
        physical_cards=physical_cards,
        linked_entities=linked_entities,
    )
    candidate_combo, combo_decision = _validate_combo(
        value.get("combo"),
        physical_cards=physical_cards,
    )

    all_rule_ids = [
        *(row["rule_id"] for row in mulligan_rows),
        *(row["rule_id"] for row in candidate_card_rows),
        *(
            (candidate_combo["rule_id"],)
            if candidate_combo is not None
            else ()
        ),
    ]
    if len(set(all_rule_ids)) != len(all_rule_ids):
        raise ValueError("starter_candidate_rule_id_duplicate")
    physical_rule_ids = _physical_rule_ids(
        physical_cards=physical_cards,
        mulligan_rows=mulligan_rows,
        card_rows=candidate_card_rows,
        combo=candidate_combo,
    )
    if set().union(*physical_rule_ids.values()) != set(all_rule_ids):
        raise ValueError("starter_candidate_rule_source_invalid")
    rationales = _validate_rule_rationales(
        value.get("rule_rationales"),
        rule_ids=set(all_rule_ids),
    )
    mulligan_plan = _build_mulligan_plan(
        mulligan_rows,
        candidate_id=candidate_id,
        candidate_digest=document.content_sha256,
        deck_name=str(context_value["deck_identity"]["deck_name"]),
        rationales=rationales,
    )
    combo_plan = _build_combo_plan(
        combo_decision,
        candidate_id=candidate_id,
        candidate_digest=document.content_sha256,
    )
    _validate_card_dispositions(
        value.get("card_dispositions"),
        expected_rule_ids=physical_rule_ids,
    )
    _validate_assumptions(value.get("assumptions"))

    if not globalvalues_changed and not card_behavior_rows and combo_decision is None:
        raise ValueError("starter_candidate_material_runtime_intent_required")

    runtime_intent_sha256 = _runtime_intent_sha256(
        mulligan_rows=mulligan_rows,
        globalvalues=globalvalues,
        card_rows=candidate_card_rows,
        combo=candidate_combo,
    )
    return ValidatedStarterCandidate(
        document=document,
        candidate_id=candidate_id,
        candidate_revision=candidate_revision,
        strategy_role=strategy_role,
        runtime_intent_sha256=runtime_intent_sha256,
        mulligan_plan=mulligan_plan,
        globalvalues=globalvalues,
        card_behavior_rows=card_behavior_rows,
        combo_plan=combo_plan,
    )


def _validated_candidate_document_value(
    document: StarterDocument,
) -> dict[str, Any]:
    return _validated_starter_document_value(
        document,
        expected_fields=STARTER_CANDIDATE_FIELDS,
        fields_error="starter_candidate_fields_invalid",
        schema_error="starter_candidate_schema_version_invalid",
        digest_error="starter_candidate_content_sha256_invalid",
    )


def _validated_starter_document_value(
    document: StarterDocument,
    *,
    expected_fields: frozenset[str],
    fields_error: str,
    schema_error: str,
    digest_error: str,
) -> dict[str, Any]:
    try:
        value = document.to_value()
    except (TypeError, ValueError):
        raise ValueError(fields_error) from None
    if set(value) != expected_fields:
        raise ValueError(fields_error)
    if (
        type(value.get("schema_version")) is not int
        or value["schema_version"] != STARTER_SCHEMA_VERSION
    ):
        raise ValueError(schema_error)
    content_sha256 = value.get("content_sha256")
    unsigned = dict(value)
    del unsigned["content_sha256"]
    try:
        sealed = seal_starter_document(
            unsigned,
            expected_fields=expected_fields,
            schema_version=STARTER_SCHEMA_VERSION,
        )
    except (TypeError, ValueError):
        raise ValueError(digest_error) from None
    if (
        not isinstance(content_sha256, str)
        or content_sha256 != document.content_sha256
        or content_sha256 != sealed.content_sha256
        or document.canonical_json != sealed.canonical_json
    ):
        raise ValueError(digest_error)
    return value


def _validated_context(
    context: StarterContext,
) -> tuple[
    dict[str, Any],
    dict[str, int],
    dict[str, tuple[tuple[str, str], ...]],
    dict[str, Any],
]:
    if not isinstance(context, StarterContext):
        raise TypeError("starter_candidate_context_invalid")
    if not isinstance(context.document, StarterDocument):
        raise TypeError("starter_candidate_context_invalid")
    value = _validated_starter_document_value(
        context.document,
        expected_fields=STARTER_CONTEXT_FIELDS,
        fields_error="starter_candidate_context_invalid",
        schema_error="starter_candidate_context_invalid",
        digest_error="starter_candidate_context_invalid",
    )
    identity = value.get("deck_identity")
    if not isinstance(identity, Mapping):
        raise ValueError("starter_candidate_context_invalid")
    fingerprint = identity.get("deck_fingerprint")
    if (
        not isinstance(fingerprint, str)
        or _RAW_SHA256_RE.fullmatch(fingerprint) is None
        or fingerprint != context.deck_fingerprint
    ):
        raise ValueError("starter_candidate_context_invalid")
    if not _nonempty_text(identity.get("deck_name"), maximum=256):
        raise ValueError("starter_candidate_context_invalid")

    raw_cards = value.get("cards")
    if not isinstance(raw_cards, list) or not raw_cards:
        raise ValueError("starter_candidate_context_invalid")
    physical_cards: dict[str, int] = {}
    linked_entities: dict[str, tuple[tuple[str, str], ...]] = {}
    for raw_card in raw_cards:
        if not isinstance(raw_card, Mapping):
            raise ValueError("starter_candidate_context_invalid")
        card_id = raw_card.get("card_id")
        count = raw_card.get("count")
        if (
            not isinstance(card_id, str)
            or not card_id
            or card_id in physical_cards
            or type(count) is not int
            or count <= 0
        ):
            raise ValueError("starter_candidate_context_invalid")
        physical_cards[card_id] = count
        raw_links = raw_card.get("linked_entities", [])
        if not isinstance(raw_links, list):
            raise ValueError("starter_candidate_context_invalid")
        links: list[tuple[str, str]] = []
        for raw_link in raw_links:
            if not isinstance(raw_link, Mapping):
                raise ValueError("starter_candidate_context_invalid")
            linked_id = raw_link.get("card_id")
            link_kind = raw_link.get("link_kind")
            if not isinstance(linked_id, str) or not isinstance(link_kind, str):
                raise ValueError("starter_candidate_context_invalid")
            links.append((linked_id, link_kind))
        linked_entities[card_id] = tuple(sorted(links))
    if (
        identity.get("unique_card_count") != len(physical_cards)
        or identity.get("card_count_total") != sum(physical_cards.values())
    ):
        raise ValueError("starter_candidate_context_invalid")

    baseline_envelope = value.get("globalvalues_baseline")
    if not isinstance(baseline_envelope, Mapping):
        raise ValueError("starter_candidate_context_invalid")
    baseline = baseline_envelope.get("values")
    if not isinstance(baseline, Mapping):
        raise ValueError("starter_candidate_context_invalid")
    baseline_copy = dict(baseline)
    if (
        baseline_envelope.get("content_sha256")
        != context.globalvalues_baseline_sha256
        or baseline_envelope.get("key_count") != len(baseline_copy)
        or canonical_globalvalues_baseline_sha256(baseline_copy)
        != context.globalvalues_baseline_sha256
    ):
        raise ValueError("starter_candidate_context_invalid")
    _validate_globalvalues(baseline_copy, baseline=baseline_copy)
    return value, physical_cards, linked_entities, baseline_copy


def _validate_strategy_summary(value: object) -> str:
    summary = require_closed_object(
        value,
        expected_fields=STARTER_STRATEGY_SUMMARY_FIELDS,
        error="starter_candidate_strategy_summary_invalid",
    )
    try:
        role = StarterStrategyRole(summary.get("role"))
    except (TypeError, ValueError):
        raise ValueError("starter_candidate_strategy_role_invalid") from None
    if not _nonempty_text(summary.get("summary"), maximum=_MAX_SUMMARY_CHARS):
        raise ValueError("starter_candidate_strategy_summary_invalid")
    return role.value


def _validate_mulligan_rows(
    value: object,
    *,
    physical_cards: Mapping[str, int],
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("starter_candidate_mulligan_required")
    result: list[dict[str, Any]] = []
    actions_by_match: dict[tuple[str, tuple[str, ...], str], str] = {}
    actions_by_card: dict[str, list[tuple[str, str]]] = {}
    for raw_row in value:
        row = require_closed_object(
            raw_row,
            expected_fields=STARTER_MULLIGAN_ROW_FIELDS,
            error="starter_candidate_mulligan_fields_invalid",
        )
        rule_id = _identifier(
            row.get("rule_id"),
            error="starter_candidate_rule_id_invalid",
        )
        normalized = normalize_mulligan_selector(row)
        selector_kind = normalized.get("selector_kind")
        if not normalized.get("supported"):
            raise ValueError("starter_candidate_mulligan_selector_invalid")
        if selector_kind in {"wildcard", "drop_n"}:
            raise ValueError("starter_candidate_mulligan_selector_forbidden")
        selector_cards = normalized.get("selector_cards")
        if (
            selector_kind not in {"card", "card_list", "plus_combo"}
            or not isinstance(selector_cards, list)
            or not selector_cards
            or any(card_id not in physical_cards for card_id in selector_cards)
        ):
            raise ValueError("starter_candidate_mulligan_card_invalid")
        action = row.get("action")
        if not isinstance(action, str) or action not in {"hold", "discard"}:
            raise ValueError("starter_candidate_mulligan_action_invalid")
        condition = _runtime_condition(row.get("condition"))
        match_key = (
            str(selector_kind),
            tuple(sorted(set(selector_cards))),
            condition,
        )
        prior_action = actions_by_match.get(match_key)
        if prior_action is not None:
            if prior_action == action:
                raise ValueError("starter_candidate_mulligan_duplicate")
            raise ValueError("starter_candidate_mulligan_conflict")
        actions_by_match[match_key] = action
        for card_id in match_key[1]:
            prior_matches = actions_by_card.setdefault(card_id, [])
            if any(
                prior_action != action
                and _mulligan_conditions_overlap(
                    prior_condition,
                    condition,
                )
                for prior_condition, prior_action in prior_matches
            ):
                raise ValueError("starter_candidate_mulligan_conflict")
            prior_matches.append((condition, action))
        result.append(
            {
                "rule_id": rule_id,
                "selector_kind": str(selector_kind),
                "selector": str(normalized["selector"]),
                "action": str(action),
                "condition": condition,
                "card_id": str(selector_cards[0]),
                "selector_cards": tuple(sorted(set(selector_cards))),
            }
        )
    return sorted(
        result,
        key=lambda row: (
            row["card_id"],
            row["selector_kind"],
            row["selector"],
            row["action"],
            row["condition"],
            row["rule_id"],
        ),
    )


def _mulligan_conditions_overlap(left: str, right: str) -> bool:
    if "*" in {left, right}:
        return True
    left_atoms = _required_mulligan_condition_atoms(left)
    right_atoms = _required_mulligan_condition_atoms(right)
    return not (
        ("coin" in left_atoms and "nocoin" in right_atoms)
        or ("nocoin" in left_atoms and "coin" in right_atoms)
    )


def _required_mulligan_condition_atoms(condition: str) -> frozenset[str]:
    if " OR " in condition:
        return frozenset()
    return frozenset(condition.split(" AND "))


def _validate_globalvalues(
    value: object,
    *,
    baseline: Mapping[str, Any],
) -> tuple[FrozenJsonDocument, bool]:
    if not isinstance(value, Mapping) or (
        len(value) != 38
        or set(value) != set(STARTER_GLOBALVALUE_CONSTRAINTS)
    ):
        raise ValueError("starter_candidate_globalvalues_keys_invalid")
    desired = dict(value)
    for key, constraint in STARTER_GLOBALVALUE_CONSTRAINTS.items():
        raw_value = desired[key]
        if constraint.copy_baseline_only:
            if raw_value != baseline.get(key):
                raise ValueError(
                    "starter_candidate_globalvalues_metadata_mismatch"
                )
            continue
        if not isinstance(raw_value, Mapping) or set(raw_value) != {"values"}:
            raise ValueError("starter_candidate_globalvalue_block_invalid")
        rows = raw_value.get("values")
        if not isinstance(rows, list) or not rows:
            raise ValueError("starter_candidate_globalvalue_block_invalid")
        values_by_condition: dict[str, str] = {}
        for raw_row in rows:
            if not isinstance(raw_row, Mapping) or set(raw_row) != {
                "condition",
                "value",
            }:
                raise ValueError("starter_candidate_globalvalue_row_invalid")
            try:
                condition = _runtime_condition(raw_row.get("condition"))
            except ValueError:
                raise ValueError(
                    "starter_candidate_globalvalue_condition_invalid"
                ) from None
            numeric_text = raw_row.get("value")
            if not _nonempty_text(numeric_text, maximum=256):
                raise ValueError("starter_candidate_globalvalue_value_invalid")
            try:
                validate_globalvalues_overlay_value(
                    key=key,
                    operation="set",
                    value=numeric_text,
                )
                numeric_value = _numeric_value(str(numeric_text))
            except (OverflowError, ValueError, ZeroDivisionError):
                raise ValueError(
                    "starter_candidate_globalvalue_value_invalid"
                ) from None
            if (
                not math.isfinite(numeric_value)
                or (
                    constraint.minimum is not None
                    and numeric_value < float(constraint.minimum)
                )
                or (
                    constraint.maximum is not None
                    and numeric_value > float(constraint.maximum)
                )
            ):
                raise ValueError("starter_candidate_globalvalue_value_invalid")
            semantic_value = _semantic_globalvalue_numeric(numeric_text)
            prior_value = values_by_condition.get(condition)
            if prior_value is not None:
                if prior_value == semantic_value:
                    raise ValueError(
                        "starter_candidate_globalvalue_row_duplicate"
                    )
                raise ValueError(
                    "starter_candidate_globalvalue_row_conflict"
                )
            values_by_condition[condition] = semantic_value
    frozen = FrozenJsonDocument.from_value(desired)
    desired_semantics = _globalvalues_semantic_projection(desired)
    baseline_semantics = _globalvalues_semantic_projection(baseline)
    return frozen, desired_semantics != baseline_semantics


def _validate_card_rules(
    value: object,
    *,
    physical_cards: Mapping[str, int],
    linked_entities: Mapping[str, tuple[tuple[str, str], ...]],
) -> tuple[list[dict[str, str]], tuple[FrozenJsonDocument, ...]]:
    if not isinstance(value, list):
        raise ValueError("starter_candidate_card_rules_invalid")
    candidate_rows: list[dict[str, str]] = []
    runtime_rows: list[dict[str, Any]] = []
    for raw_row in value:
        row = require_closed_object(
            raw_row,
            expected_fields=STARTER_CARD_RULE_FIELDS,
            error="starter_candidate_card_rule_fields_invalid",
        )
        rule_id = _identifier(
            row.get("rule_id"),
            error="starter_candidate_rule_id_invalid",
        )
        source_card_id = row.get("source_card_id")
        runtime_card_id = row.get("runtime_card_id")
        link_kind = row.get("link_kind")
        behavior_block = row.get("behavior_block")
        if (
            not isinstance(source_card_id, str)
            or source_card_id not in physical_cards
        ):
            raise ValueError("starter_candidate_card_id_unknown")
        if (
            not isinstance(behavior_block, str)
            or behavior_block not in CARD_BEHAVIOR_BLOCKS
        ):
            raise ValueError("starter_candidate_behavior_block_invalid")
        if not all(
            isinstance(item, str) and item
            for item in (runtime_card_id, link_kind)
        ):
            raise ValueError("starter_candidate_runtime_owner_unauthorized")
        if not _runtime_owner_authorized(
            source_card_id=str(source_card_id),
            runtime_card_id=str(runtime_card_id),
            link_kind=str(link_kind),
            behavior_block=str(behavior_block),
            linked_entities=linked_entities,
        ):
            raise ValueError("starter_candidate_runtime_owner_unauthorized")
        condition = _runtime_condition(row.get("condition"))
        numeric_value = _bounded_decimal(
            row.get("value"),
            minimum=STARTER_CARD_VALUE_CONSTRAINT.minimum,
            maximum=STARTER_CARD_VALUE_CONSTRAINT.maximum,
            error="starter_candidate_card_value_invalid",
        )
        candidate_row = {
            "rule_id": rule_id,
            "source_card_id": str(source_card_id),
            "runtime_card_id": str(runtime_card_id),
            "link_kind": str(link_kind),
            "behavior_block": str(behavior_block),
            "condition": condition,
            "value": numeric_value,
        }
        candidate_rows.append(candidate_row)
        runtime_rows.append(
            {
                "authority_id": "LLM_OPTIMIZED_START",
                "behavior_block": str(behavior_block),
                "card_id": str(runtime_card_id),
                "condition": condition,
                "confidence": "llm_optimized_start",
                "link_kind": str(link_kind),
                "rule_id_suffix": rule_id,
                "runtime_card_id": str(runtime_card_id),
                "source_card_id": str(source_card_id),
                "source_claim_ids": [],
                "surface_family": "CARDID.json",
                "value": numeric_value,
            }
        )
    canonical = canonicalize_runtime_rows(runtime_rows)
    if canonical["conflicts"]:
        raise ValueError("starter_candidate_runtime_row_conflict")
    if canonical["merged_duplicate_count"]:
        raise ValueError("starter_candidate_runtime_row_duplicate")
    candidate_rows.sort(
        key=lambda row: (
            row["runtime_card_id"],
            row["behavior_block"],
            row["condition"],
            row["value"],
            row["rule_id"],
        )
    )
    frozen_rows = tuple(
        FrozenJsonDocument.from_value(row) for row in canonical["rows"]
    )
    return candidate_rows, frozen_rows


def _runtime_owner_authorized(
    *,
    source_card_id: str,
    runtime_card_id: str,
    link_kind: str,
    behavior_block: str,
    linked_entities: Mapping[str, tuple[tuple[str, str], ...]],
) -> bool:
    if link_kind == "self":
        return (
            source_card_id == runtime_card_id
            and not (
                source_card_id == "SW_448"
                and behavior_block == "BeforeUseHeroPowerBonus"
            )
        )
    if (runtime_card_id, link_kind) not in linked_entities.get(
        source_card_id, ()
    ):
        return False
    semantic_reason = linked_runtime_entity_semantic_surface(
        behavior_block=behavior_block,
        link_kind=link_kind,
    )
    if semantic_reason is None:
        return False
    return runtime_entity_owner_relation_is_authorized(
        source_card_id=source_card_id,
        semantic_reason=semantic_reason,
        link_kind=link_kind,
        runtime_card_id=runtime_card_id,
    )


def _validate_combo(
    value: object,
    *,
    physical_cards: Mapping[str, int],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if value is None:
        return None, None
    row = require_closed_object(
        value,
        expected_fields=STARTER_COMBO_FIELDS,
        error="starter_candidate_combo_fields_invalid",
    )
    rule_id = _identifier(
        row.get("rule_id"),
        error="starter_candidate_rule_id_invalid",
    )
    cards = row.get("cards")
    if (
        not isinstance(cards, list)
        or len(cards) < 2
        or any(
            not isinstance(card_id, str) or card_id not in physical_cards
            for card_id in cards
        )
    ):
        raise ValueError("starter_candidate_combo_card_invalid")
    values = row.get("values")
    if not isinstance(values, list) or len(values) != len(cards):
        raise ValueError("starter_candidate_combo_values_invalid")
    numeric_values = tuple(
        _bounded_decimal(
            numeric_value,
            minimum=STARTER_COMBO_VALUE_CONSTRAINT.minimum,
            maximum=STARTER_COMBO_VALUE_CONSTRAINT.maximum,
            error="starter_candidate_combo_values_invalid",
        )
        for numeric_value in values
    )
    try:
        timing = ComboTiming(row.get("timing"))
    except (TypeError, ValueError):
        raise ValueError("starter_candidate_combo_timing_invalid") from None
    condition = _runtime_condition(row.get("condition"))
    normalized = {
        "rule_id": rule_id,
        "cards": list(cards),
        "timing": timing.value,
        "values": list(numeric_values),
        "condition": condition,
    }
    return normalized, {
        "rule_id": rule_id,
        "cards": tuple(str(card_id) for card_id in cards),
        "timing": timing,
        "values": numeric_values,
        "condition": condition,
    }


def _validate_rule_rationales(
    value: object,
    *,
    rule_ids: set[str],
) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != rule_ids:
        raise ValueError("starter_candidate_rule_rationales_invalid")
    rationales: dict[str, str] = {}
    for rule_id, rationale in value.items():
        if not _nonempty_text(rationale, maximum=_MAX_RATIONALE_CHARS):
            raise ValueError("starter_candidate_rule_rationales_invalid")
        rationales[str(rule_id)] = str(rationale)
    return rationales


def _build_mulligan_plan(
    rows: list[dict[str, Any]],
    *,
    candidate_id: str,
    candidate_digest: str,
    deck_name: str,
    rationales: Mapping[str, str],
) -> MulliganPlanModel:
    rules = tuple(
        sorted(
            (
                MulliganRuleModel(
                    card_id=row["card_id"],
                    selector_kind=row["selector_kind"],
                    selector_canonical_json=_canonical_json_bytes(
                        row["selector"]
                    ),
                    action=row["action"],
                    condition_canonical_json=_canonical_json_bytes(
                        row["condition"]
                    ),
                    reason=rationales[row["rule_id"]],
                    confidence="llm_optimized_start",
                    source_claim_ids=(),
                    claim_id=_starter_rule_authority(
                        candidate_id,
                        candidate_digest,
                        row["rule_id"],
                    ),
                )
                for row in rows
            ),
            key=lambda rule: rule.identity,
        )
    )
    try:
        return MulliganPlanModel(
            deck_name=deck_name,
            rules=rules,
            suppressed=(),
            bot_delegated=(),
            merged_duplicate_rule_count=0,
        )
    except ValueError as error:
        if str(error) == "mulligan_duplicate_rule_identity":
            raise ValueError("starter_candidate_mulligan_duplicate") from error
        raise


def _build_combo_plan(
    row: dict[str, Any] | None,
    *,
    candidate_id: str,
    candidate_digest: str,
) -> ComboPlanModel:
    if row is None:
        return ComboPlanModel(decisions=(), suppressions=())
    decision = ComboDecisionModel(
        rule_id=row["rule_id"],
        cards=row["cards"],
        timing=row["timing"],
        values=row["values"],
        condition=row["condition"],
        source_claim_ids=(),
        confidence="llm_optimized_start",
        source_refs=(),
        claim_id=_starter_rule_authority(
            candidate_id,
            candidate_digest,
            row["rule_id"],
        ),
    )
    return ComboPlanModel(decisions=(decision,), suppressions=())


def _validate_card_dispositions(
    value: object,
    *,
    expected_rule_ids: Mapping[str, set[str]],
) -> None:
    if not isinstance(value, list):
        raise ValueError("starter_candidate_card_dispositions_invalid")
    seen: set[str] = set()
    for raw_row in value:
        if not isinstance(raw_row, Mapping) or set(raw_row) != (
            STARTER_CARD_DISPOSITION_FIELDS
        ):
            raise ValueError("starter_candidate_card_dispositions_invalid")
        card_id = raw_row.get("card_id")
        disposition = raw_row.get("disposition")
        row_rule_ids = raw_row.get("rule_ids")
        reason = raw_row.get("reason")
        if (
            not isinstance(card_id, str)
            or card_id not in expected_rule_ids
            or card_id in seen
            or not isinstance(disposition, str)
            or disposition not in _CARD_DISPOSITIONS
            or not isinstance(row_rule_ids, list)
            or any(
                not isinstance(rule_id, str)
                for rule_id in row_rule_ids
            )
            or len(set(row_rule_ids)) != len(row_rule_ids)
            or set(row_rule_ids) != expected_rule_ids[card_id]
            or not _nonempty_text(reason, maximum=_MAX_RATIONALE_CHARS)
            or (disposition == "configured") != bool(row_rule_ids)
        ):
            raise ValueError("starter_candidate_card_dispositions_invalid")
        seen.add(card_id)
    if seen != set(expected_rule_ids) or len(value) != len(expected_rule_ids):
        raise ValueError("starter_candidate_card_dispositions_invalid")


def _physical_rule_ids(
    *,
    physical_cards: Mapping[str, int],
    mulligan_rows: list[dict[str, Any]],
    card_rows: list[dict[str, str]],
    combo: dict[str, Any] | None,
) -> dict[str, set[str]]:
    expected = {card_id: set() for card_id in physical_cards}
    for row in mulligan_rows:
        for card_id in row["selector_cards"]:
            expected[card_id].add(row["rule_id"])
    for row in card_rows:
        expected[row["source_card_id"]].add(row["rule_id"])
    if combo is not None:
        for card_id in combo["cards"]:
            expected[card_id].add(combo["rule_id"])
    return expected


def _validate_assumptions(value: object) -> None:
    if (
        not isinstance(value, list)
        or len(value) > _MAX_ASSUMPTIONS
        or any(
            not _nonempty_text(assumption, maximum=_MAX_RATIONALE_CHARS)
            for assumption in value
        )
    ):
        raise ValueError("starter_candidate_assumptions_invalid")


def _runtime_intent_sha256(
    *,
    mulligan_rows: list[dict[str, Any]],
    globalvalues: FrozenJsonDocument,
    card_rows: list[dict[str, str]],
    combo: dict[str, Any] | None,
) -> str:
    payload = {
        "mulligan": _mulligan_semantic_projection(mulligan_rows),
        "globalvalues": _globalvalues_semantic_projection(
            globalvalues.to_value()
        ),
        "card_rules": [
            {
                key: (
                    _semantic_decimal_projection(row[key])
                    if key == "value"
                    else row[key]
                )
                for key in (
                    "source_card_id",
                    "runtime_card_id",
                    "link_kind",
                    "behavior_block",
                    "condition",
                    "value",
                )
            }
            for row in card_rows
        ],
        "combo": (
            None
            if combo is None
            else {
                key: (
                    [
                        _semantic_decimal_projection(value)
                        for value in combo[key]
                    ]
                    if key == "values"
                    else combo[key]
                )
                for key in ("cards", "timing", "values", "condition")
            }
        ),
    }
    canonical = FrozenJsonDocument.from_value(payload).canonical_json
    return "sha256:" + sha256(canonical).hexdigest()


def _mulligan_semantic_projection(
    rows: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    atomic_matches: set[tuple[str, str, str]] = set()
    plus_combo_matches: set[tuple[tuple[str, ...], str, str]] = set()
    for row in rows:
        selector_cards = tuple(row["selector_cards"])
        condition = row["condition"]
        action = row["action"]
        if row["selector_kind"] == "plus_combo":
            plus_combo_matches.add((selector_cards, condition, action))
            continue
        atomic_matches.update(
            (card_id, condition, action) for card_id in selector_cards
        )
    return {
        "atomic_card_matches": [
            {"card_id": card_id, "condition": condition, "action": action}
            for card_id, condition, action in sorted(atomic_matches)
        ],
        "plus_combo_matches": [
            {
                "selector_cards": list(selector_cards),
                "condition": condition,
                "action": action,
            }
            for selector_cards, condition, action in sorted(
                plus_combo_matches
            )
        ],
    }


def _runtime_condition(value: object) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise ValueError("starter_candidate_condition_invalid")
    classified = classify_runtime_condition(value)
    if classified.status != "runtime_safe" or classified.value != value:
        raise ValueError("starter_candidate_condition_invalid")
    return value


def _bounded_decimal(
    value: object,
    *,
    minimum: Decimal | None,
    maximum: Decimal | None,
    error: str,
) -> str:
    if not _nonempty_text(value, maximum=256):
        raise ValueError(error)
    text = str(value)
    if _FINITE_DECIMAL_RE.fullmatch(text) is None:
        raise ValueError(error)
    try:
        number = Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError(error) from None
    if (
        not number.is_finite()
        or (minimum is not None and number < minimum)
        or (maximum is not None and number > maximum)
    ):
        raise ValueError(error)
    return text


def _globalvalues_semantic_projection(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    projection: dict[str, Any] = {}
    for key, raw_value in value.items():
        constraint = STARTER_GLOBALVALUE_CONSTRAINTS[key]
        if constraint.copy_baseline_only:
            projection[key] = raw_value
            continue
        projection[key] = {
            "values": [
                {
                    "condition": row["condition"],
                    "value": _semantic_globalvalue_numeric(row["value"]),
                }
                for row in raw_value["values"]
            ]
        }
    return projection


def _semantic_globalvalue_numeric(value: str) -> str:
    number = _numeric_value(value)
    if number == 0.0:
        return "0x0.0p+0"
    return number.hex()


def _semantic_decimal_projection(value: str) -> str:
    number = Decimal(value)
    if number == 0:
        return "0"
    sign, raw_digits, raw_exponent = number.as_tuple()
    digits = list(raw_digits)
    exponent = int(raw_exponent)
    while digits[-1] == 0:
        digits.pop()
        exponent += 1
    coefficient = "".join(str(digit) for digit in digits)
    if exponent >= 0:
        magnitude = coefficient + ("0" * exponent)
    else:
        decimal_point = len(coefficient) + exponent
        if decimal_point > 0:
            magnitude = (
                coefficient[:decimal_point]
                + "."
                + coefficient[decimal_point:]
            )
        else:
            magnitude = "0." + ("0" * -decimal_point) + coefficient
    return ("-" if sign else "") + magnitude


def _identifier(value: object, *, error: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        raise ValueError(error)
    return value


def _nonempty_text(value: object, *, maximum: int) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and value == value.strip()
        and len(value) <= maximum
        and not any(ord(character) < 32 for character in value)
    )


def _starter_rule_authority(
    candidate_id: str,
    candidate_digest: str,
    rule_id: str,
) -> str:
    return f"starter:{candidate_digest}:{candidate_id}:{rule_id}"


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


__all__ = ("ValidatedStarterCandidate", "validate_starter_candidate")
