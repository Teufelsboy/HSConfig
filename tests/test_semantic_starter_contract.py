"""Closed semantic route descriptors and additive schema-four field contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, astuple, replace
from types import SimpleNamespace

import pytest

from hsconfig import starter_contract as contracts
from hsconfig.starter_document import seal_starter_document


class IntegerSubclass(int):
    pass


class StringSubclass(str):
    pass


ROUTES = (
    ("LEGACY_LIVE_CONTRACT", (
        "legacy_live", 1, 1, 2, 2, 2, "hsconfig-live-start-v1",
        "single_candidate_review_v1", 1, None,
    )),
    ("QUALITY_LIVE_CONTRACT", (
        "quality_live", 2, 2, 3, 3, 3, "hsconfig-live-start-v2",
        "single_candidate_review_v2", 2, 1,
    )),
    ("SEMANTIC_LIVE_CONTRACT", (
        "semantic_live", 3, 3, 4, 4, 4, "hsconfig-live-start-v3",
        "single_candidate_review_v3", 3, 2,
    )),
)


def semantic_versions() -> dict[str, object]:
    return dict(
        session=3, manifest=3, context=4, candidate=4, review=4,
        compiler="hsconfig-live-start-v3",
    )


def test_new_tuple_is_closed() -> None:
    # Break caught: the new live tuple is absent or dispatched to an older route.
    assert contracts.live_contract_for_versions(
        session=3, manifest=3, context=4, candidate=4, review=4,
        compiler="hsconfig-live-start-v3",
    ) == "semantic_live"


@pytest.mark.parametrize(
    "field", ["session", "manifest", "context", "candidate", "review", "compiler"],
)
def test_new_tuple_rejects_mixed_versions(field: str) -> None:
    # Break caught: any one version can cross between closed live routes.
    values = semantic_versions()
    values[field] = "hsconfig-live-start-v2" if field == "compiler" else 2
    with pytest.raises(ValueError, match="^live_start_contract_combination_invalid$"):
        contracts.live_contract_for_versions(**values)


@pytest.mark.parametrize("field", ["session", "manifest", "context", "candidate", "review"])
@pytest.mark.parametrize("kind", ["true", "false", "float", "string", "int_subclass"])
def test_live_tuple_requires_exact_integer_types(field: str, kind: str) -> None:
    # Break caught: integer equality admits a boolean or coercible version value.
    values = semantic_versions()
    version = values[field]
    values[field] = {
        "true": True, "false": False, "float": float(version),
        "string": str(version), "int_subclass": IntegerSubclass(version),
    }[kind]
    with pytest.raises(ValueError, match="^live_start_contract_combination_invalid$"):
        contracts.live_contract_for_versions(**values)


@pytest.mark.parametrize("compiler", [None, 3, StringSubclass("hsconfig-live-start-v3")])
def test_live_tuple_requires_exact_compiler_string(compiler: object) -> None:
    # Break caught: compiler comparison accepts a non-exact string scalar.
    values = {**semantic_versions(), "compiler": compiler}
    with pytest.raises(ValueError, match="^live_start_contract_combination_invalid$"):
        contracts.live_contract_for_versions(**values)


@pytest.mark.parametrize(("name", "expected"), ROUTES)
def test_closed_lookups_return_the_registered_complete_descriptor(
    name: str, expected: tuple[object, ...],
) -> None:
    # Break caught: a lookup returns a copy, wrong authority, receipt, or facts route.
    route = getattr(contracts, name)
    assert astuple(route) == expected
    assert contracts.require_live_starter_contract(route) is route
    assert contracts.live_contract_for_session_version(expected[1]) is route
    assert contracts.live_contract_for_context_version(expected[3]) is route
    assert contracts.live_contract_for_authority(expected[7]) is route
    assert contracts.live_contract_for_versions(
        session=expected[1], manifest=expected[2], context=expected[3],
        candidate=expected[4], review=expected[5], compiler=expected[6],
    ) == expected[0]


@pytest.mark.parametrize("changes", [
    {"route_id": "arbitrary"}, {"session": 2}, {"manifest": 2},
    {"context": 3}, {"candidate": 3}, {"review": 3},
    {"compiler": "hsconfig-live-start-v2"},
    {"authority": "single_candidate_review_v2"},
    {"validation_receipt": 2}, {"review_facts": 1},
    {"review_facts": None},
])
def test_descriptor_constructor_rejects_every_nonclosed_field(
    changes: dict[str, object],
) -> None:
    # Break caught: constructing a mixed descriptor bypasses six-field dispatch.
    with pytest.raises(ValueError, match="^live_start_contract_combination_invalid$"):
        replace(contracts.SEMANTIC_LIVE_CONTRACT, **changes)


@pytest.mark.parametrize(
    "field", ["session", "manifest", "context", "candidate", "review", "validation_receipt", "review_facts"],
)
@pytest.mark.parametrize("kind", ["boolean", "int_subclass", "float"])
def test_descriptor_constructor_requires_exact_integer_types(field: str, kind: str) -> None:
    # Break caught: the descriptor constructor permits equality-compatible scalars.
    route = contracts.QUALITY_LIVE_CONTRACT
    version = getattr(route, field)
    value = {
        "boolean": True, "int_subclass": IntegerSubclass(version),
        "float": float(version),
    }[kind]
    with pytest.raises(ValueError, match="^live_start_contract_combination_invalid$"):
        replace(route, **{field: value})


@pytest.mark.parametrize("field", ["route_id", "compiler", "authority"])
@pytest.mark.parametrize("kind", ["none", "str_subclass"])
def test_descriptor_constructor_requires_exact_string_types(field: str, kind: str) -> None:
    # Break caught: a string subclass can masquerade as a closed descriptor value.
    route = contracts.SEMANTIC_LIVE_CONTRACT
    value = None if kind == "none" else StringSubclass(getattr(route, field))
    with pytest.raises(ValueError, match="^live_start_contract_combination_invalid$"):
        replace(route, **{field: value})


@pytest.mark.parametrize(("name", "_expected"), ROUTES)
def test_only_registered_descriptor_can_select_route(name: str, _expected: object) -> None:
    # Break caught: an equal-valued, newly constructed object acquires authority.
    route = getattr(contracts, name)
    duplicate = replace(route)
    assert duplicate == route
    assert duplicate is not route
    with pytest.raises(ValueError, match="^live_start_contract_combination_invalid$"):
        contracts.require_live_starter_contract(duplicate)


@pytest.mark.parametrize("kind", ["subclass", "duck", "mapping", "none"])
def test_unregistered_object_types_cannot_select_a_route(kind: str) -> None:
    # Break caught: isinstance or duck typing admits nonregistered route objects.
    route = contracts.SEMANTIC_LIVE_CONTRACT
    if kind == "subclass":
        class ContractSubclass(contracts.LiveStarterContract):
            pass
        value = ContractSubclass(*astuple(route))
    elif kind == "duck":
        value = SimpleNamespace(**{
            field: getattr(route, field) for field in route.__dataclass_fields__
        })
    elif kind == "mapping":
        value = {"route_id": "semantic_live", **semantic_versions()}
    else:
        value = None
    with pytest.raises(ValueError, match="^live_start_contract_combination_invalid$"):
        contracts.require_live_starter_contract(value)


def test_fabricated_mixed_descriptor_is_revalidated() -> None:
    # Break caught: the authority boundary skips validation after construction.
    duplicate = replace(contracts.SEMANTIC_LIVE_CONTRACT)
    object.__setattr__(duplicate, "review_facts", 1)
    with pytest.raises(ValueError, match="^live_start_contract_combination_invalid$"):
        contracts.require_live_starter_contract(duplicate)


def test_registered_descriptor_cannot_be_normally_mutated() -> None:
    # Break caught: callers can rewrite the shared registered route in place.
    with pytest.raises(FrozenInstanceError):
        contracts.SEMANTIC_LIVE_CONTRACT.review = 3


@pytest.mark.parametrize("value", [0, 4, True, False, 3.0, "3", IntegerSubclass(3), None])
def test_session_lookup_rejects_unknown_or_non_exact_versions(value: object) -> None:
    # Break caught: session lookup coerces values or creates an unregistered route.
    with pytest.raises(ValueError, match="^live_start_contract_combination_invalid$"):
        contracts.live_contract_for_session_version(value)


@pytest.mark.parametrize("value", [0, 1, 5, True, 4.0, "4", IntegerSubclass(4), None])
def test_context_lookup_keeps_schema_one_historical_only(value: object) -> None:
    # Break caught: context1 becomes a live tuple or lookup relaxes scalar types.
    with pytest.raises(ValueError, match="^live_start_contract_combination_invalid$"):
        contracts.live_contract_for_context_version(value)


@pytest.mark.parametrize("value", [
    "", "arbitrary", "single_candidate_review_v4", None, True, 3,
    StringSubclass("single_candidate_review_v3"),
])
def test_authority_lookup_rejects_unknown_or_non_exact_values(value: object) -> None:
    # Break caught: an unknown or string-compatible authority selects a route.
    with pytest.raises(ValueError, match="^live_start_contract_combination_invalid$"):
        contracts.live_contract_for_authority(value)


DOCUMENT_FIELDS = (
    ("SEMANTIC_STARTER_CONTEXT_FIELDS", frozenset({
        "schema_version", "deck_identity", "cards", "deck_shape",
        "supported_runtime_contract", "globalvalues_baseline", "source_evidence",
        "existing_claims", "known_safety_boundaries", "content_sha256",
        "input_snapshot_manifest_sha256", "card_metadata", "sideboards",
        "linked_entities", "research_evidence", "temporal_provenance",
    })),
    ("SEMANTIC_STARTER_CANDIDATE_FIELDS", frozenset({
        "schema_version", "candidate_id", "candidate_revision",
        "starter_context_sha256", "deck_fingerprint", "strategy_summary",
        "mulligan", "globalvalues", "card_rules", "combo", "card_dispositions",
        "rule_rationales", "assumptions", "content_sha256",
        "globalvalues_justifications", "rule_justifications",
    })),
    ("SEMANTIC_STARTER_REVIEW_FIELDS", frozenset({
        "schema_version", "review_id", "review_status", "confidence",
        "starter_context_sha256", "candidate_id", "candidate_revision",
        "candidate_sha256", "revision_requests", "review_summary",
        "content_sha256", "candidate_validation_receipt_sha256",
    })),
)


@pytest.mark.parametrize(("name", "expected"), DOCUMENT_FIELDS)
def test_schema_four_field_sets_seal_only_the_closed_document_shape(
    name: str, expected: frozenset[str],
) -> None:
    # Break caught: a semantic field contract adds, drops, or permits extra fields.
    fields = getattr(contracts, name)
    assert type(fields) is frozenset
    assert fields == expected
    draft = {field: None for field in expected - {"content_sha256"}}
    draft["schema_version"] = 4
    sealed = seal_starter_document(
        draft, expected_fields=fields,
        schema_version=contracts.SEMANTIC_STARTER_SCHEMA_VERSION,
    )
    assert set(sealed.to_value()) == expected
    assert sealed.to_value()["schema_version"] == 4
    with pytest.raises(ValueError, match="^starter_document_fields_invalid$"):
        seal_starter_document(
            {**draft, "unexpected": None}, expected_fields=fields,
            schema_version=contracts.SEMANTIC_STARTER_SCHEMA_VERSION,
        )


@pytest.mark.parametrize(("name", "expected"), DOCUMENT_FIELDS)
@pytest.mark.parametrize("version", [1, 2, 3, True, 4.0, "4"])
def test_schema_four_field_contracts_reject_older_or_noninteger_versions(
    name: str, expected: frozenset[str], version: object,
) -> None:
    # Break caught: the new field set can be sealed under an older schema version.
    draft = {field: None for field in expected - {"content_sha256"}}
    draft["schema_version"] = version
    with pytest.raises(ValueError, match="^starter_document_schema_version_invalid$"):
        seal_starter_document(
            draft, expected_fields=getattr(contracts, name),
            schema_version=contracts.SEMANTIC_STARTER_SCHEMA_VERSION,
        )


@pytest.mark.parametrize("missing", ["basis", "evidence_refs", "assumption", None])
def test_rule_justifications_have_only_the_three_required_fields(missing: str | None) -> None:
    # Break caught: rule justifications accept missing provenance or extra authority.
    fields = contracts.SEMANTIC_RULE_JUSTIFICATION_FIELDS
    source = {"basis": "source", "evidence_refs": ["evidence-1"], "assumption": None}
    assert type(fields) is frozenset
    assert contracts.require_closed_object(
        source, expected_fields=fields, error="justification_fields_invalid",
    ) == source
    if missing is None:
        source["unexpected"] = None
    else:
        del source[missing]
    with pytest.raises(ValueError, match="^justification_fields_invalid$"):
        contracts.require_closed_object(
            source, expected_fields=fields, error="justification_fields_invalid",
        )


def test_semantic_fields_do_not_replace_historical_defaults() -> None:
    # Break caught: adding schema4 silently changes a historical caller's defaults.
    assert contracts.STARTER_SCHEMA_VERSION == 1
    assert contracts.STARTER_CONTEXT_FIELDS is contracts.LEGACY_STARTER_CONTEXT_FIELDS
    assert contracts.STARTER_CANDIDATE_FIELDS is contracts.LEGACY_STARTER_CANDIDATE_FIELDS
    assert contracts.SEMANTIC_STARTER_CONTEXT_FIELDS - contracts.QUALITY_STARTER_CONTEXT_FIELDS == {"temporal_provenance"}
    assert contracts.SEMANTIC_STARTER_CANDIDATE_FIELDS - contracts.QUALITY_STARTER_CANDIDATE_FIELDS == {"rule_justifications"}
    assert contracts.SEMANTIC_STARTER_REVIEW_FIELDS == contracts.QUALITY_STARTER_REVIEW_FIELDS
