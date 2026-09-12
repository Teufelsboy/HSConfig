"""Read-only historical starter projections; there is deliberately no updater."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Mapping

from hsconfig.compile_mulligan import compile_mulligan
from hsconfig.package_request import FrozenJsonDocument
from hsconfig.starter_candidate import ValidatedStarterCandidate, validate_starter_candidate
from hsconfig.starter_context import StarterContext
from hsconfig.starter_contract import (
    QUALITY_CANDIDATE_VALIDATION_RECEIPT_FIELDS,
    QUALITY_STARTER_CANDIDATE_FIELDS,
    QUALITY_STARTER_CONTEXT_FIELDS,
    QUALITY_STARTER_REVIEW_FIELDS,
    SINGLE_CANDIDATE_STARTER_CANDIDATE_FIELDS,
    SINGLE_CANDIDATE_STARTER_CONTEXT_FIELDS,
    STARTER_CANDIDATE_FIELDS,
    STARTER_CANDIDATE_MAX_BYTES,
    STARTER_CONTEXT_FIELDS,
    STARTER_CONTEXT_MAX_BYTES,
    STARTER_DECISION_FIELDS,
    STARTER_DECISION_MAX_BYTES,
    STARTER_REVIEW_FIELDS,
    STARTER_REVIEW_MAX_BYTES,
)
from hsconfig.starter_document import StarterDocument, load_starter_document, seal_starter_document
from hsconfig.starter_review import build_candidate_review_facts
from tests.test_quality_starter_candidate import quality_draft, seal_quality_candidate
from tests.test_starter_candidate import candidate_draft


BASELINE_COMMIT = "aae2eb793b8a7daa52f7bd7dfd98e02005bfade4"
FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "starter_historical"

_JSON_NAMES = frozenset({"projection", "mutations", "derivation"})
_DOCUMENT_SPECS: dict[int, dict[str, tuple[str, frozenset[str], int, int]]] = {
    1: {
        "starter_context": (
            "starter_context.json", STARTER_CONTEXT_FIELDS, 1, STARTER_CONTEXT_MAX_BYTES
        ),
        "candidate-1": (
            "candidate-1.json", STARTER_CANDIDATE_FIELDS, 1, STARTER_CANDIDATE_MAX_BYTES
        ),
        "candidate-2": (
            "candidate-2.json", STARTER_CANDIDATE_FIELDS, 1, STARTER_CANDIDATE_MAX_BYTES
        ),
        "candidate-3": (
            "candidate-3.json", STARTER_CANDIDATE_FIELDS, 1, STARTER_CANDIDATE_MAX_BYTES
        ),
        "starter_config_decision": (
            "starter_config_decision.json", STARTER_DECISION_FIELDS, 1, STARTER_DECISION_MAX_BYTES
        ),
    },
    2: {
        "starter_context": (
            "starter_context.json", SINGLE_CANDIDATE_STARTER_CONTEXT_FIELDS, 2, STARTER_CONTEXT_MAX_BYTES
        ),
        "starter_config_candidate": (
            "starter_config_candidate.json", SINGLE_CANDIDATE_STARTER_CANDIDATE_FIELDS, 2, STARTER_CANDIDATE_MAX_BYTES
        ),
        "starter_config_review": (
            "starter_config_review.json", STARTER_REVIEW_FIELDS, 2, STARTER_REVIEW_MAX_BYTES
        ),
    },
    3: {
        "starter_context": (
            "starter_context.json", QUALITY_STARTER_CONTEXT_FIELDS, 3, STARTER_CONTEXT_MAX_BYTES
        ),
        "starter_config_candidate": (
            "starter_config_candidate.json", QUALITY_STARTER_CANDIDATE_FIELDS, 3, STARTER_CANDIDATE_MAX_BYTES
        ),
        "starter_config_review": (
            "starter_config_review.json", QUALITY_STARTER_REVIEW_FIELDS, 3, STARTER_REVIEW_MAX_BYTES
        ),
    },
}


def capture_historical_projection(
    context: StarterContext,
    candidate: ValidatedStarterCandidate,
    *,
    receipt: FrozenJsonDocument | None = None,
    review: Any | None = None,
) -> dict[str, Any]:
    """Project the exact historical typed outputs selected by the task brief."""

    value = {
        "context_bytes": context.document.canonical_json.decode("utf-8"),
        "candidate_bytes": candidate.document.canonical_json.decode("utf-8"),
        "runtime_intent_sha256": candidate.runtime_intent_sha256,
        "mulligan_report": candidate.mulligan_plan.to_report(),
        "mulligan_runtime": compile_mulligan(candidate.mulligan_plan),
        "globalvalues": candidate.globalvalues.to_value(),
        "card_behavior_rows": [row.to_value() for row in candidate.card_behavior_rows],
    }
    if context.document.to_value()["schema_version"] == 3:
        value["review_facts"] = build_candidate_review_facts(
            context=context, candidate=candidate
        ).to_value()
    if receipt is not None:
        value["validation_receipt_bytes"] = receipt.canonical_json.decode("utf-8")
    if review is not None:
        value["review_bytes"] = review.document.canonical_json.decode("utf-8")
    return value


def capture_historical_mutations(
    context: StarterContext,
    *,
    schema: int,
) -> dict[str, Any]:
    """Measure specified historical cases without reinterpreting their outcome."""

    _require_schema(schema)
    mutations = {
        "duplicate_comma_selector": _duplicate_comma_selector,
        "duplicate_plus_multiplicity": _duplicate_plus_multiplicity,
        "sorted_cardid_rows": _out_of_order_cardid_rows,
        "globally_valid_wrong_owner": _globally_valid_wrong_owner,
        "globally_valid_wrong_phase": _globally_valid_wrong_phase,
    }
    results = {
        name: _capture_candidate_outcome(context, schema=schema, mutate=mutate)
        for name, mutate in mutations.items()
    }
    results["reordered_globalvalues"] = _capture_reordered_globalvalues(
        context, schema=schema
    )
    return results


def load_historical_document(schema: int, name: str) -> StarterDocument:
    """Load one frozen document through its original closed field/version set."""

    specs = _DOCUMENT_SPECS.get(schema)
    if specs is None or name not in specs:
        raise ValueError("historical_document_name_invalid")
    filename, fields, version, maximum_bytes = specs[name]
    return load_starter_document(
        FIXTURE_ROOT / f"schema{schema}" / filename,
        maximum_bytes=maximum_bytes,
        expected_fields=fields,
        schema_version=version,
    )


def load_historical_receipt(schema: int) -> FrozenJsonDocument | None:
    """Load the original schema-3 receipt; old routes intentionally have none."""

    _require_schema(schema)
    if schema != 3:
        return None
    document = load_starter_document(
        FIXTURE_ROOT / "schema3" / "candidate_validation_receipt.json",
        maximum_bytes=STARTER_REVIEW_MAX_BYTES,
        expected_fields=QUALITY_CANDIDATE_VALIDATION_RECEIPT_FIELDS,
        schema_version=2,
    )
    return document.document


def load_historical_json(schema: int, name: str) -> Any:
    """Load a reviewed public golden; this API has no write/update mode."""

    _require_schema(schema)
    if name not in _JSON_NAMES:
        raise ValueError("historical_json_name_invalid")
    return json.loads(
        (FIXTURE_ROOT / f"schema{schema}" / f"{name}.json").read_bytes()
    )


def _capture_candidate_outcome(
    context: StarterContext,
    *,
    schema: int,
    mutate: Any,
) -> dict[str, Any]:
    draft = _base_draft(context, schema=schema)
    mutate(draft)
    try:
        candidate = validate_starter_candidate(
            _seal_draft(draft, schema=schema), context=context
        )
    except (TypeError, ValueError) as error:
        return {"status": "rejected", "error": str(error)}
    value: dict[str, Any] = {
        "status": "accepted",
        "candidate_sha256": candidate.document.content_sha256,
        "runtime_intent_sha256": candidate.runtime_intent_sha256,
        "mulligan_report": candidate.mulligan_plan.to_report(),
        "mulligan_runtime": compile_mulligan(candidate.mulligan_plan),
        "card_behavior_rows": [row.to_value() for row in candidate.card_behavior_rows],
    }
    if schema == 3:
        value["review_facts"] = build_candidate_review_facts(
            context=context, candidate=candidate
        ).to_value()
    return value


def _capture_reordered_globalvalues(
    context: StarterContext,
    *,
    schema: int,
) -> dict[str, Any]:
    first_draft = _base_draft(context, schema=schema)
    values = first_draft["globalvalues"]["FirstTurnValueWeight"]["values"]
    values.append({"condition": "coin", "value": "0.5"})
    second_draft = deepcopy(first_draft)
    second_draft["globalvalues"]["FirstTurnValueWeight"]["values"].reverse()
    try:
        first = validate_starter_candidate(
            _seal_draft(first_draft, schema=schema), context=context
        )
        second = validate_starter_candidate(
            _seal_draft(second_draft, schema=schema), context=context
        )
    except (TypeError, ValueError) as error:
        return {"status": "rejected", "error": str(error)}
    return {
        "status": "accepted",
        "first_candidate_sha256": first.document.content_sha256,
        "second_candidate_sha256": second.document.content_sha256,
        "first_runtime_intent_sha256": first.runtime_intent_sha256,
        "second_runtime_intent_sha256": second.runtime_intent_sha256,
        "runtime_intent_equivalent": (
            first.runtime_intent_sha256 == second.runtime_intent_sha256
        ),
        "first_values": first.globalvalues.to_value()["FirstTurnValueWeight"]["values"],
        "second_values": second.globalvalues.to_value()["FirstTurnValueWeight"]["values"],
    }


def _base_draft(context: StarterContext, *, schema: int) -> dict[str, Any]:
    if schema == 3:
        return quality_draft(context)
    return candidate_draft(
        context,
        candidate_id="candidate-1" if schema == 1 else "lead",
        role="proactive_tempo" if schema == 1 else "lead_strategist",
        schema_version=schema,
    )


def _seal_draft(draft: Mapping[str, Any], *, schema: int) -> StarterDocument:
    if schema == 3:
        return seal_quality_candidate(draft)
    return seal_starter_document(
        draft,
        expected_fields=(
            STARTER_CANDIDATE_FIELDS
            if schema == 1
            else SINGLE_CANDIDATE_STARTER_CANDIDATE_FIELDS
        ),
        schema_version=schema,
    )


def _duplicate_comma_selector(draft: dict[str, Any]) -> None:
    draft["mulligan"][0].update(
        selector_kind="card_list", selector="TOY_518, TOY_518"
    )


def _duplicate_plus_multiplicity(draft: dict[str, Any]) -> None:
    draft["mulligan"][0].update(
        selector_kind="plus_combo", selector="TOY_518 + TOY_518"
    )


def _out_of_order_cardid_rows(draft: dict[str, Any]) -> None:
    first = draft["card_rules"][0]
    first["condition"] = "nocoin"
    second = deepcopy(first)
    second.update(rule_id="second-cardid-row", condition="coin", value="13")
    draft["card_rules"].append(second)
    draft["rule_rationales"][second["rule_id"]] = "Second valid conditional row."
    disposition = next(
        row
        for row in draft["card_dispositions"]
        if row["card_id"] == first["source_card_id"]
    )
    disposition["rule_ids"].append(second["rule_id"])


def _globally_valid_wrong_owner(draft: dict[str, Any]) -> None:
    row = draft["card_rules"][0]
    old_rule_id = row["rule_id"]
    row.update(
        rule_id="minion-hero-power-phase",
        source_card_id="TOY_518",
        runtime_card_id="TOY_518",
        link_kind="self",
        behavior_block="BeforeUseHeroPowerBonus",
    )
    draft["rule_rationales"].pop(old_rule_id)
    draft["rule_rationales"][row["rule_id"]] = (
        "Historically globally valid owner case."
    )
    for disposition in draft["card_dispositions"]:
        disposition["rule_ids"] = [
            row["rule_id"] if rule_id == old_rule_id else rule_id
            for rule_id in disposition["rule_ids"]
        ]
        if (
            disposition["card_id"] == "TOY_518"
            and row["rule_id"] not in disposition["rule_ids"]
        ):
            disposition["rule_ids"].append(row["rule_id"])
        if disposition["card_id"] == "SW_448":
            disposition["rule_ids"] = [
                rule_id
                for rule_id in disposition["rule_ids"]
                if rule_id != row["rule_id"]
            ]
        disposition["disposition"] = (
            "configured"
            if disposition["rule_ids"]
            else "deliberately_unconfigured"
        )


def _globally_valid_wrong_phase(draft: dict[str, Any]) -> None:
    draft["mulligan"][0]["condition"] = (
        "my_discover(count(),cardid=TOY_518) > 0"
    )


def _require_schema(schema: int) -> None:
    if type(schema) is not int or schema not in {1, 2, 3}:
        raise ValueError("historical_schema_invalid")


__all__ = (
    "BASELINE_COMMIT",
    "FIXTURE_ROOT",
    "capture_historical_mutations",
    "capture_historical_projection",
    "load_historical_document",
    "load_historical_json",
    "load_historical_receipt",
)
