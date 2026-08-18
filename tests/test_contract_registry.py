from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from types import MappingProxyType

import pytest

import hsconfig.globalvalues_key_authority as globalvalues_key_authority
import hsconfig.source_contract_matrix as source_contract_matrix
from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS
from hsconfig.visionai_registry import (
    CLAIM_SURFACE_REGISTRY,
    FORBIDDEN_RUNTIME_SURFACES,
    GLOBALVALUES_KEY_REGISTRY,
    NORMAL_APPLY_AUTHORITY,
    OPTIONAL_RUNTIME_SURFACES,
    REPORT_REGISTRY,
    REQUIRED_RUNTIME_SURFACES,
    RUNTIME_SURFACE_REGISTRY,
    STARTER_CARD_VALUE_CONSTRAINT,
    STARTER_COMBO_VALUE_CONSTRAINT,
    STARTER_GLOBALVALUE_CONSTRAINTS,
    ClaimSurfaceRule,
    GlobalValueKeySpec,
    ReportSpec,
    RuntimeSurfaceSpec,
    classify_runtime_surface,
    normalize_runtime_surface,
    report_spec,
    runtime_surface_spec,
    starter_globalvalue_constraint,
)
from hsconfig.globalvalues_decisions import GLOBALVALUES_BASELINE_DECISION_KEYS


def test_registry_has_one_normal_apply_authority():
    authorities = [
        spec.relative_path
        for spec in REPORT_REGISTRY.values()
        if spec.apply_authority
    ]
    assert authorities == ["reports/operator_summary.json"]
    assert NORMAL_APPLY_AUTHORITY == authorities[0]


def test_starter_globalvalue_constraints_cover_exact_baseline_keys():
    assert tuple(STARTER_GLOBALVALUE_CONSTRAINTS) == (
        GLOBALVALUES_BASELINE_DECISION_KEYS
    )
    for key in ("GameCardId", "ConfigComment"):
        constraint = starter_globalvalue_constraint(key)

        assert constraint.value_type_id == "copy_baseline"
        assert constraint.minimum is None
        assert constraint.maximum is None
        assert constraint.copy_baseline_only is True
    assert all(
        constraint.value_type_id == "safe_numeric_expression"
        and constraint.minimum == Decimal("-1000")
        and constraint.maximum == Decimal("1000")
        and not constraint.copy_baseline_only
        for key, constraint in STARTER_GLOBALVALUE_CONSTRAINTS.items()
        if key not in {"GameCardId", "ConfigComment"}
    )
    assert starter_globalvalue_constraint("GlobalTaunt") == (
        STARTER_GLOBALVALUE_CONSTRAINTS["GlobalTaunt"]
    )
    assert STARTER_CARD_VALUE_CONSTRAINT.value_type_id == "finite_decimal"
    assert STARTER_CARD_VALUE_CONSTRAINT.minimum == Decimal("-10000")
    assert STARTER_CARD_VALUE_CONSTRAINT.maximum == Decimal("10000")
    assert not STARTER_CARD_VALUE_CONSTRAINT.copy_baseline_only
    assert STARTER_COMBO_VALUE_CONSTRAINT == STARTER_CARD_VALUE_CONSTRAINT


def test_registry_classifies_normal_runtime_surfaces():
    assert classify_runtime_surface("GlobalValues.json") == "required"
    assert classify_runtime_surface("Mulligan.json") == "required"
    assert classify_runtime_surface("SW_448.json") == "conditional_card_surface"
    assert classify_runtime_surface("Combo.json") == "optional"
    assert classify_runtime_surface("Presume.json") == "forbidden"
    assert classify_runtime_surface("Concede.json") == "forbidden"
    assert classify_runtime_surface("CardBehavior.json") == "forbidden"


def test_registry_derives_runtime_classification_sets_from_specs():
    assert REQUIRED_RUNTIME_SURFACES == frozenset(
        {"GlobalValues.json", "Mulligan.json"}
    )
    assert OPTIONAL_RUNTIME_SURFACES == frozenset({"Combo.json"})
    assert FORBIDDEN_RUNTIME_SURFACES == frozenset(
        {"CardBehavior.json", "Concede.json", "Presume.json"}
    )
    assert all(
        spec.file_name == file_name
        for file_name, spec in RUNTIME_SURFACE_REGISTRY.items()
    )


def test_registry_normalizes_concrete_cardid_without_globally_requiring_it():
    assert normalize_runtime_surface("CustomConfig/deck/SW_448.json") == "CARDID.json"
    spec = runtime_surface_spec("SW_448.json")
    assert spec.file_name == "CARDID.json"
    assert spec.classification == "conditional_card_surface"
    assert spec.normal_apply_allowed is True


def test_registry_fails_closed_for_unknown_runtime_and_report_names():
    with pytest.raises(KeyError):
        classify_runtime_surface("FutureOptionalSurface.json")
    with pytest.raises(KeyError):
        runtime_surface_spec("reports/operator_summary.json")
    with pytest.raises(KeyError):
        report_spec("reports/future_report.json")


def test_registry_specs_are_frozen_slotted_contract_values():
    runtime = runtime_surface_spec("Mulligan.json")
    report = report_spec(NORMAL_APPLY_AUTHORITY)
    claim = next(iter(CLAIM_SURFACE_REGISTRY.values()))
    globalvalue = next(iter(GLOBALVALUES_KEY_REGISTRY.values()))

    assert isinstance(runtime, RuntimeSurfaceSpec)
    assert isinstance(report, ReportSpec)
    assert isinstance(claim, ClaimSurfaceRule)
    assert isinstance(globalvalue, GlobalValueKeySpec)
    assert not hasattr(runtime, "__dict__")
    with pytest.raises(FrozenInstanceError):
        runtime.classification = "optional"


def test_registry_entries_repeat_their_lookup_identity():
    assert all(
        spec.relative_path == relative_path
        for relative_path, spec in REPORT_REGISTRY.items()
    )
    assert all(
        rule.claim_kind == claim_kind
        for claim_kind, rule in CLAIM_SURFACE_REGISTRY.items()
    )
    assert all(
        spec.key == key for key, spec in GLOBALVALUES_KEY_REGISTRY.items()
    )


def test_every_supported_claim_policy_classification_matches_the_registry():
    policy = source_contract_matrix.source_contract_policy_by_claim_kind()

    assert set(policy) == set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    assert set(policy) == set(CLAIM_SURFACE_REGISTRY)
    for claim_kind, rule in CLAIM_SURFACE_REGISTRY.items():
        assert len(rule.required_authority_lanes) == 1
        assert policy[claim_kind]["lane"] == rule.required_authority_lanes[0]
        assert policy[claim_kind]["semantic_lane"] == rule.required_authority_lanes[0]
        assert policy[claim_kind]["allowed_surfaces"] == tuple(
            surface.removesuffix(".json").lower()
            for surface in rule.allowed_surfaces
        )


def test_source_contract_policy_reads_claim_classification_from_registry(
    monkeypatch,
):
    claim_kind = "mulligan_keep"
    original = CLAIM_SURFACE_REGISTRY[claim_kind]
    mutated = {
        **CLAIM_SURFACE_REGISTRY,
        claim_kind: replace(
            original,
            allowed_surfaces=(),
            required_authority_lanes=("report_only",),
        ),
    }
    monkeypatch.setattr(
        source_contract_matrix,
        "CLAIM_SURFACE_REGISTRY",
        MappingProxyType(mutated),
        raising=False,
    )

    row = source_contract_matrix.source_contract_policy_by_claim_kind()[claim_kind]

    assert row["lane"] == "report_only"
    assert row["semantic_lane"] == "report_only"
    assert row["allowed_surfaces"] == ()


def test_every_classified_globalvalues_key_authority_matches_the_registry():
    for key, spec in GLOBALVALUES_KEY_REGISTRY.items():
        assert globalvalues_key_authority.authority_for_key(key)["category"] == (
            spec.key_class
        )


def test_globalvalues_key_authority_reads_key_class_from_registry(monkeypatch):
    key = "FirstTurnValueWeight"
    original = GLOBALVALUES_KEY_REGISTRY[key]
    mutated = {
        **GLOBALVALUES_KEY_REGISTRY,
        key: replace(original, key_class="runtime_evidence_required"),
    }
    monkeypatch.setattr(
        globalvalues_key_authority,
        "GLOBALVALUES_KEY_REGISTRY",
        MappingProxyType(mutated),
        raising=False,
    )

    assert globalvalues_key_authority.authority_for_key(key)["category"] == (
        "runtime_evidence_required"
    )
