from dataclasses import FrozenInstanceError

import pytest

from hsconfig.visionai_registry import (
    CLAIM_SURFACE_REGISTRY,
    FORBIDDEN_RUNTIME_SURFACES,
    GLOBALVALUES_KEY_REGISTRY,
    NORMAL_APPLY_AUTHORITY,
    OPTIONAL_RUNTIME_SURFACES,
    REPORT_REGISTRY,
    REQUIRED_RUNTIME_SURFACES,
    RUNTIME_SURFACE_REGISTRY,
    ClaimSurfaceRule,
    GlobalValueKeySpec,
    ReportSpec,
    RuntimeSurfaceSpec,
    classify_runtime_surface,
    normalize_runtime_surface,
    report_spec,
    runtime_surface_spec,
)


def test_registry_has_one_normal_apply_authority():
    authorities = [
        spec.relative_path
        for spec in REPORT_REGISTRY.values()
        if spec.apply_authority
    ]
    assert authorities == ["reports/operator_summary.json"]
    assert NORMAL_APPLY_AUTHORITY == authorities[0]


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
