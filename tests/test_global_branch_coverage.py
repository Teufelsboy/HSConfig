from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import Enum
import hashlib
import json
import os
from pathlib import Path, PurePath, PurePosixPath
import stat
from types import MappingProxyType, ModuleType, SimpleNamespace

import pytest
from hearthstone.deckstrings import write_deckstring

from hsconfig import config_quality_checks
from hsconfig import configure_workflow
from hsconfig import compile_globalvalues
from hsconfig import build_context
from hsconfig import guide_claim_builder
from hsconfig import operator_summary_evaluator
from hsconfig import package_domain
from hsconfig import package_request
from hsconfig import source_document_model
from hsconfig import strict_package_validation
from hsconfig import runtime_transaction_journal
from hsconfig import validate_package
from hsconfig import package_compiler_support
from hsconfig import package_derivation_receipt
from hsconfig import package_publication
from hsconfig import source_acquisition
from hsconfig import source_to_runtime_explainability
from hsconfig import release_verification
from hsconfig import runtime_package_match
from hsconfig import semantic_inventory
from hsconfig.audited_build_request import _render_selected_run
from hsconfig.audited_deck_catalog import load_audited_deck_catalog
from hsconfig.build_input_catalog import (
    FrozenBuildResourceStore,
    load_audited_build_inputs,
    load_audited_build_resource_store,
)
from hsconfig.build_inputs import CanonicalBuildInputs
from hsconfig.config_quality_inputs import FrozenPackageSnapshot
from hsconfig.configure_run_model import RenderedConfigureRun
from hsconfig.deck_identity import stable_deck_fingerprint
from hsconfig.deckstring_decode import _parse_deckstring, decode_deck_code
from hsconfig.io import write_json
from hsconfig.output_publisher import publish_configure_run
from hsconfig.package_io import BoundedFilesystemPackageView
from hsconfig.runtime_installer import (
    RuntimeInstallPlan,
    RuntimeInstallResult,
    install_runtime_package,
    plan_runtime_install,
)
from hsconfig.source_acquisition_provenance import build_acquisition_provenance


def _quality_package_root(
    documents: dict[str, object],
) -> object:
    names = tuple(sorted(documents))
    files = {
        name: json.dumps(value, sort_keys=True).encode("utf-8")
        for name, value in documents.items()
    }
    snapshot = FrozenPackageSnapshot(
        package_label="fixture-package",
        _names=names,
        _files=MappingProxyType(files),
        _json_documents=MappingProxyType(dict(documents)),
        _canonical_json_bytes=MappingProxyType(files),
        _canonical_json_sha256=MappingProxyType({}),
        _content_sha256_without_self=MappingProxyType({}),
        _validation_errors=MappingProxyType({}),
    )
    return snapshot.root_path()


def _normalize_guide_claim(
    raw_claim: dict[str, object],
    *,
    document: dict[str, object] | None = None,
) -> tuple[dict[str, object] | None, dict[str, object] | None]:
    return guide_claim_builder._normalize_source_claim(
        raw_claim,
        document=document or {},
        source_ref="guide:fixture",
        claim_index=3,
        known_card_ids={"CARD_001", "CARD_002"},
    )


def test_guide_claim_normalizer_classifies_non_card_and_unsupported_claims() -> None:
    claim, unsupported = _normalize_guide_claim(
        {"claim_kind": "card_role", "cards": []}
    )

    assert claim is None
    assert unsupported == {
        "source_ref": "guide:fixture",
        "claim_index": 3,
        "reason": "not_card_specific",
        "claim_kind": "card_role",
        "cards": [],
        "source_url": "",
        "source_title": "",
        "evidence_text_short": "",
    }

    claim, unsupported = _normalize_guide_claim(
        {"claim_kind": "future_claim_kind", "cards": ["CARD_001"]}
    )

    assert claim is None
    assert unsupported is not None
    assert unsupported["reason"] == "unsupported_claim_kind"


def test_guide_claim_normalizer_reports_cards_outside_the_deck() -> None:
    claim, unsupported = _normalize_guide_claim(
        {
            "claim_kind": "card_role",
            "cards": ["CARD_001", "CARD_999"],
        }
    )

    assert claim is None
    assert unsupported is not None
    assert unsupported["reason"] == "card_not_in_deck"
    assert unsupported["missing_cards"] == ["CARD_999"]


def test_guide_claim_normalizer_preserves_every_supported_optional_field() -> None:
    claim, unsupported = _normalize_guide_claim(
        {
            "claim_type": "combo_sequence",
            "cards": [" CARD_001 ", "CARD_001", "CARD_002"],
            "scope": " Card ",
            "claim": "  play   these together ",
            "source_refs": ["guide:fixture", "guide:secondary"],
            "source_confidence": " high ",
            "claim_confidence": " high ",
            "stance": " preferred ",
            "sequence": ["CARD_002", "CARD_001"],
            "values": {"z": ["  one  ", 2], "a": " three "},
            "condition": {"mana": "  five  "},
            "runtime_block": " combo ",
            "runtime_value": " 42 ",
            "mechanic": " COMBO ",
        },
        document={
            "source_url": "https://example.invalid/guide",
            "source_title": "Fixture Guide",
            "source_family": "guide",
            "retrieved_at": "2026-08-01",
        },
    )

    assert unsupported is None
    assert claim is not None
    assert claim["claim_kind"] == "combo_sequence"
    assert claim["claim_type"] == "combo"
    assert claim["cards"] == ["CARD_001", "CARD_002"]
    assert claim["source_refs"] == [
        "guide:fixture",
        "guide:secondary",
        "https://example.invalid/guide",
    ]
    assert claim["sequence"] == ["CARD_002", "CARD_001"]
    assert claim["values"] == {"a": "three", "z": ["one", 2]}
    assert claim["conditions"] == {"mana": "five"}
    assert claim["runtime_block"] == "combo"
    assert claim["runtime_value"] == "42"
    assert claim["mechanic"] == "combo"
    assert claim["evidence_hash"]
    assert claim["source_claim_ids"] == [claim["claim_id"]]


def test_deck_scoped_gameplan_claim_needs_no_card_and_no_optional_fields() -> None:
    claim, unsupported = _normalize_guide_claim(
        {"claim_kind": "gameplan_posture", "scope": "deck"}
    )

    assert unsupported is None
    assert claim is not None
    assert claim["cards"] == []
    assert claim["scope"] == "deck"
    assert "sequence" not in claim
    assert "values" not in claim
    assert "condition" not in claim
    assert "runtime_block" not in claim
    assert "runtime_value" not in claim
    assert "mechanic" not in claim
    assert "evidence_hash" not in claim


def test_guide_claim_metadata_and_readiness_helpers_normalize_real_shapes() -> None:
    assert guide_claim_builder._card_metadata_by_id(
        [{"card_id": "CARD_001", "name": "One"}]
    ) == {"CARD_001": {"card_id": "CARD_001", "name": "One"}}
    assert guide_claim_builder._card_metadata_by_id(
        {"cards": [{"card_id": "CARD_002", "name": "Two"}]}
    ) == {"CARD_002": {"card_id": "CARD_002", "name": "Two"}}
    assert guide_claim_builder._card_metadata_by_id(
        {"CARD_001": {"name": "One"}, "ignored": "not-a-row"}
    ) == {"CARD_001": {"card_id": "CARD_001", "name": "One"}}
    assert guide_claim_builder._card_metadata_by_id("invalid") == {}

    first = {"claim_id": "one", "claim": "first"}
    duplicate = {"claim_id": "one", "claim": "duplicate"}
    second = {"claim_id": "two", "claim": "second"}
    assert guide_claim_builder._dedupe_claims([first, duplicate, second]) == [
        first,
        second,
    ]

    assert guide_claim_builder._claim_counts_as_guide_backed(
        {"claim_readiness": "GUIDE_BACKED"}
    )
    assert not guide_claim_builder._claim_counts_as_guide_backed(
        {"claim_readiness": "unverified"}
    )
    assert guide_claim_builder._claim_counts_as_guide_backed(
        {"support_status": "source_backed", "confidence": "source_backed"}
    )
    assert not guide_claim_builder._claim_counts_as_guide_backed({})

    assert guide_claim_builder._claim_counts_as_static_semantics(
        {"claim_readiness": "SOURCE_BACKED_STATIC_SEMANTICS"}
    )
    assert not guide_claim_builder._claim_counts_as_static_semantics(
        {"claim_readiness": "guide_backed"}
    )
    assert guide_claim_builder._claim_counts_as_static_semantics(
        {"source_family": "hearthstonejson_static_semantics"}
    )
    assert guide_claim_builder._claim_counts_as_static_semantics(
        {"support_status": "STATIC_SEMANTICS"}
    )
    assert guide_claim_builder._claim_counts_as_static_semantics(
        {"confidence": "SOURCE_BACKED_STATIC_SEMANTICS"}
    )
    assert not guide_claim_builder._claim_counts_as_static_semantics({})


def test_guide_claim_value_helpers_preserve_canonical_nested_values() -> None:
    assert guide_claim_builder._normalize_cards(None) == []
    assert guide_claim_builder._normalize_cards(" CARD_001 ") == ["CARD_001"]
    assert guide_claim_builder._normalize_cards(
        ["CARD_001", " ", "CARD_001", "CARD_002"]
    ) == ["CARD_001", "CARD_002"]
    assert guide_claim_builder._normalize_optional("  two   words ") == "two words"
    assert guide_claim_builder._normalize_optional(
        [" one ", {"z": " two ", "a": 3}]
    ) == ["one", {"a": 3, "z": "two"}]
    assert guide_claim_builder._normalize_optional(7) == 7
    assert guide_claim_builder._card_text(
        {"text": "Battlecry", "mechanics": ["TAUNT", "RUSH"]}
    ) == "Battlecry TAUNT RUSH"
    assert guide_claim_builder._card_text(
        {"text": "Spell", "mechanics": "not-a-list"}
    ) == "Spell"


def test_operator_source_lanes_collect_positive_summary_and_nested_lanes() -> None:
    assert operator_summary_evaluator._operator_source_lanes(
        {
            "summary": {
                "source_quality_lane_counts": {
                    "deck_matched_public_guide": "2",
                    "ignored": 0,
                }
            },
            "nested": [
                {"source_lane": "static_semantics"},
                {"source_lane": ""},
            ],
        },
        {"summary": [], "source_lane": "archetype_matched_public_guide"},
    ) == [
        "archetype_matched_public_guide",
        "deck_matched_public_guide",
        "static_semantics",
    ]


def test_operator_runtime_surface_status_handles_missing_invalid_and_default_only() -> None:
    assert operator_summary_evaluator._no_default_only_runtime_status(None) == (
        "not_reported"
    )
    assert operator_summary_evaluator._no_default_only_runtime_status([]) == "clean"
    assert operator_summary_evaluator._no_default_only_runtime_status(
        ["mulligan"]
    ) == "has_default_only_surfaces"
    assert operator_summary_evaluator._default_only_runtime_surfaces(
        {"surfaces": []}
    ) == []
    assert operator_summary_evaluator._default_only_runtime_surfaces(
        {
            "surfaces": {
                "combo": "invalid",
                "mulligan": {"default_only": True},
                "cardid": {"default_only": False},
            }
        }
    ) == ["mulligan"]


def test_operator_mulligan_policy_distinguishes_bot_delegation_from_physical_rules() -> None:
    delegated = operator_summary_evaluator._mulligan_policy_status(
        {"surfaces": {"mulligan": []}},
        mulligan_plan_report={
            "bot_delegated": [
                "invalid",
                {"reason_code": "start_of_game_effect"},
            ],
            "rules": "invalid",
        },
    )
    assert delegated == {
        "status": "bot_delegated",
        "default_only": False,
        "policy_lanes": ["E"],
        "policy_reasons": ["start_of_game_effect"],
    }
    assert operator_summary_evaluator._mulligan_policy_status(
        {"surfaces": []},
        mulligan_plan_report={"bot_delegated": "invalid", "rules": []},
    ) == {
        "status": "unknown",
        "default_only": False,
        "policy_lanes": [],
        "policy_reasons": [],
    }


def test_operator_collection_helpers_accept_only_documented_container_shapes() -> None:
    one = {"id": 1}
    two = {"id": 2}
    assert operator_summary_evaluator._list_of_dicts(
        {"one": one, "bad": [], "two": two}
    ) == [one, two]
    assert operator_summary_evaluator._list_of_dicts([one, [], two]) == [one, two]
    assert operator_summary_evaluator._list_of_dicts("invalid") == []
    assert operator_summary_evaluator._string_list("one") == ["one"]
    assert operator_summary_evaluator._string_list("") == []
    assert operator_summary_evaluator._string_list(["one", "", 2]) == ["one", "2"]
    assert operator_summary_evaluator._string_list(None) == []
    assert operator_summary_evaluator._mechanics_from_gameplan_cards([]) == []
    assert operator_summary_evaluator._mechanics_from_gameplan_cards(
            {
                "A": {"mechanics": ["burn", ""]},
                "B": "invalid",
                "C": {"mechanic_families": "combo"},
            }
    ) == ["burn", "combo"]


def test_operator_source_evidence_summary_counts_only_real_evidence_chains() -> None:
    empty = operator_summary_evaluator._source_evidence_closure_summary(None)
    assert empty["cards_total"] == 0
    assert empty["next_report_to_open"] is None

    summary = operator_summary_evaluator._source_evidence_closure_summary(
        {
            "card_rows": [
                "invalid",
                {
                    "closure": {
                        "lane": "runtime_lowered",
                        "default_only_risk": True,
                    },
                    "evidence_chain": ["source"],
                    "first_missing_source_action": "none",
                },
                {
                    "closure": [],
                    "evidence_chain": [],
                    "first_missing_source_action": "add_guide",
                },
            ],
            "summary": [],
        }
    )
    assert summary["cards_total"] == 3
    assert summary["lane_counts"] == {"runtime_lowered": 1}
    assert summary["default_only_risk_count"] == 1
    assert summary["cards_with_evidence_chain"] == 1
    assert summary["cards_missing_evidence_chain"] == 2
    assert summary["first_missing_source_action_counts"] == {"add_guide": 1}
    assert summary["next_report_to_open"] == (
        "reports/source_to_runtime_explainability.json"
    )


def test_operator_summary_fallback_helpers_derive_counts_from_legacy_rows() -> None:
    assert operator_summary_evaluator._low_confidence_card_count(
        {"summary": {"uncovered_low_confidence": "2"}}
    ) == 2
    assert operator_summary_evaluator._low_confidence_card_count(
        {"uncovered_cards": ["A", "B"]}
    ) == 2
    assert operator_summary_evaluator._low_confidence_card_count(
        {"uncovered_cards": {}, "cards": []}
    ) == 0
    assert operator_summary_evaluator._low_confidence_card_count(
        {
            "uncovered_cards": {},
            "cards": {
                "A": {"coverage_status": "uncovered_low_confidence"},
                "B": "invalid",
            },
        }
    ) == 1

    assert operator_summary_evaluator._uncovered_cards(
        {"uncovered_cards": ["A", 2]}
    ) == ["A", "2"]
    assert operator_summary_evaluator._uncovered_cards(
        {"uncovered_cards": {}, "cards": []}
    ) == []
    assert operator_summary_evaluator._uncovered_cards(
        {
            "uncovered_cards": {},
            "cards": {
                "A": {"coverage_status": "uncovered_low_confidence"},
                "B": {},
            },
        }
    ) == ["A"]


def test_effective_readiness_summary_counts_lanes_and_actionable_missing_links() -> None:
    supplied = {"total_cards": 3}
    assert operator_summary_evaluator._effective_config_readiness_summary(
        supplied,
        None,
    ) is supplied
    assert operator_summary_evaluator._effective_config_readiness_summary(
        None,
        None,
    ) == {}
    assert operator_summary_evaluator._effective_config_readiness_summary(
        None,
        {"cards": []},
    ) == {}
    summary = operator_summary_evaluator._effective_config_readiness_summary(
        None,
        {
            "cards": {
                "invalid": [],
                "A": {
                    "readiness_lane": "runtime_emitted",
                    "first_missing_link": "none",
                },
                "B": {
                    "readiness_lane": "generic_low_confidence",
                    "first_missing_link": "needs_target_scope",
                },
            }
        },
    )
    assert summary["total_cards"] == 3
    assert summary["runtime_emitted"] == 1
    assert summary["generic_low_confidence"] == 1
    assert summary["cards_needing_target_scope"] == 1


def test_operator_numeric_and_source_depth_helpers_fail_softly() -> None:
    assert operator_summary_evaluator._int_value("4") == 4
    assert operator_summary_evaluator._int_value("invalid") == 0
    assert operator_summary_evaluator._source_depth_status(
        {"source_depth_status": "STRONG"}
    ) == "source_backed"
    assert operator_summary_evaluator._source_depth_status(
        {"depth_status": "usable"}
    ) == "static_semantics_only"
    assert operator_summary_evaluator._source_depth_status({}) == ""
    assert operator_summary_evaluator._claim_count({"claim_count": "3"}) == 3
    assert operator_summary_evaluator._claim_count(
        {"summary": {"claim_count": "2"}}
    ) == 2
    assert operator_summary_evaluator._claim_count({"summary": []}) == 0


def test_operator_remaining_projection_helpers_fail_closed_on_malformed_blocks() -> (
    None
):
    assert operator_summary_evaluator._default_only_runtime_surface_details(
        {"surfaces": []},
        {},
    ) == []
    assert operator_summary_evaluator._surface_status_ledger(
        {"surfaces": []},
        {},
    ) == []
    assert operator_summary_evaluator._surface_status_ledger(
        {"surfaces": {"bad": "invalid"}},
        {},
    ) == []
    assert operator_summary_evaluator._surface_ledger_next_report(
        "combo",
        "attention",
    ).endswith("combo_plan_report.json")
    assert operator_summary_evaluator._runtime_surfaces_from_closure(
        {"closure": []}
    ) == set()
    assert not operator_summary_evaluator._closure_matches_surface(
        {"closure": {}},
        "combo",
    )
    assert operator_summary_evaluator._default_only_risk_card_details(
        {"card_rows": ["invalid"]}
    ) == []
    assert operator_summary_evaluator._strong_promotion_evidence_blockers(
        {"surfaces": []}
    ) == []
    assert operator_summary_evaluator._strong_promotion_evidence_blockers(
        {"surfaces": {"bad": "invalid"}}
    ) == []

    assert operator_summary_evaluator._normalize_readiness_summary_aliases(
        {"summary": []}
    ) is None
    empty_mechanic = {
        "support_level_counts": {"direct": 0, "partial": 0, "warning_only": 0},
        "warning_only_mechanics": [],
        "warning_only_card_count": 0,
    }
    assert operator_summary_evaluator._mechanic_warning_summary(
        {"summary": []},
        [],
    ) == empty_mechanic
    assert operator_summary_evaluator._mechanic_warning_summary(
        {"summary": {"mechanic_support": []}},
        None,
    ) == empty_mechanic

    empty_visibility = operator_summary_evaluator._mechanic_visibility_summary(
        {"summary": []},
        [],
    )
    assert empty_visibility["bucket_counts"]["direct"] == 0
    assert operator_summary_evaluator._mechanic_visibility_summary(
        {"summary": {"mechanic_visibility": []}},
        None,
    ) == empty_visibility
    normalized_visibility = operator_summary_evaluator._mechanic_visibility_summary(
        {
            "summary": {
                "mechanic_visibility": {
                    "bucket_counts": {},
                    "mechanics_by_bucket": [],
                }
            }
        }
    )
    assert normalized_visibility["mechanics_by_bucket"]["direct"] == []

    assert operator_summary_evaluator._affected_cards_by_missing_link(
        {"cards": []},
        "claim",
    ) == []
    assert operator_summary_evaluator._affected_cards_from_conditions(
        [{"card": "CARD_001"}]
    ) == [{"card_id": "CARD_001", "name": "CARD_001"}]
    assert operator_summary_evaluator._generic_low_confidence_count(
        config_readiness_summary={"generic_low_confidence": 2},
        claim_coverage_report=None,
    ) == 2
    assert operator_summary_evaluator._readiness_gap_count([]) == 0
    assert operator_summary_evaluator._uncovered_card_count_with_fallback(
        claim_coverage_report=None,
        config_readiness_summary={"uncovered_cards": 3},
    ) == 3

    empty_plan = package_domain.MulliganPlanModel(
        deck_name="Deck",
        rules=(),
        suppressed=(),
        bot_delegated=(),
        merged_duplicate_rule_count=0,
    )
    assert operator_summary_evaluator._mulligan_plan_report_payload(empty_plan)[
        "deck_name"
    ] == "Deck"
    details = operator_summary_evaluator._default_only_runtime_surface_details(
        {
            "surfaces": {
                "mulligan": {
                    "default_only": True,
                    "first_gap_reason": "gap",
                    "next_source_need": "research",
                }
            }
        },
        {},
    )
    assert details[0]["first_missing_link"] == "gap"
    non_mulligan_details = (
        operator_summary_evaluator._default_only_runtime_surface_details(
            {"surfaces": {"combo": {"default_only": True}}},
            {},
        )
    )
    assert non_mulligan_details[0]["surface"] == "combo"
    assert operator_summary_evaluator._surface_ledger_next_report(
        "future",
        "attention",
    ) == operator_summary_evaluator.NORMAL_APPLY_AUTHORITY
    assert operator_summary_evaluator._runtime_surfaces_from_closure(
        {
            "closure": {
                "expected_runtime_surfaces": ["Combo.json"],
                "runtime_surfaces": ["Mulligan.json"],
            }
        }
    ) == {"Combo.json", "Mulligan.json"}
    assert operator_summary_evaluator._runtime_surfaces_from_closure(
        {
            "closure": {
                "expected_runtime_surfaces": {},
                "runtime_surfaces": [],
            }
        }
    ) == set()

    apply_facts = operator_summary_evaluator._operator_apply_facts(
        technical_status="INVALID_PACKAGE",
        primary_blockers=[],
        package_derivation=None,
        package_authority=None,
        source_apply_eligible=True,
        source_apply_eligibility_reasons=[],
        exact_source_closed=False,
        semantic_status="SOURCE_BACKED_STRONG",
    )
    assert apply_facts.blocking_reasons[0]["code"] == "invalid_package"
    assert operator_summary_evaluator._closure_profile_claim_rows(
        source_claim_gap_report=None,
        source_contract_audit_report=None,
        source_to_runtime_explainability_report={
            "card_rows": [{"strongest_claim_kind": "mulligan", "closure": []}]
        },
    )[0]["claim_kind"] == "mulligan"
    assert operator_summary_evaluator._claim_row_from_card_row(
        {"closure": []},
        "mulligan",
    ) == {"claim_kind": "mulligan", "reconstructed_from_card_row": True}
    diagnostics = operator_summary_evaluator._strong_closure_diagnostics(
        [
            {"claim_id": "claim", "claim_kind": "mulligan"},
            {"claim_id": "claim", "claim_kind": "mulligan"},
        ]
    )
    assert diagnostics
    assert operator_summary_evaluator._runtime_surface_filenames(
        ["", "CustomConfig/Deck/Combo.json"]
    ) == ["Combo.json"]
    assert operator_summary_evaluator._mechanic_warning_summary(
        {"summary": []},
        ["invalid"],
    ) == empty_mechanic
    assert operator_summary_evaluator._mechanic_visibility_summary(
        {"summary": []},
        ["invalid"],
    ) == empty_visibility
    strength = operator_summary_evaluator._guide_strength_summary(
        guide_source_depth={"source_evidence": []},
        claim_coverage_report={},
        config_readiness_summary={},
        claim_conflict_report={},
    )
    assert strength["source_evidence_warnings"] == 0
    assert operator_summary_evaluator._affected_cards_from_conditions(
        [{}, {"card_id": "CARD_002"}]
    ) == [{"card_id": "CARD_002", "name": "CARD_002"}]
    assert operator_summary_evaluator._generic_low_confidence_count(
        config_readiness_summary=None,
        claim_coverage_report={"uncovered_cards": ["CARD_001"]},
    ) == 1
    assert operator_summary_evaluator._uncovered_card_count_with_fallback(
        claim_coverage_report=None,
        config_readiness_summary=None,
    ) == 0


def test_protected_evaluator_module_guards_only_the_bootstrap_binding() -> None:
    capability = object()
    protected_type = operator_summary_evaluator._protected_evaluator_module_type(
        capability
    )
    module = ModuleType("fixture_operator_evaluator")
    module.__class__ = protected_type

    assert module._operator_summary_evaluator_bootstrap is capability
    module.ordinary = "value"
    assert module.ordinary == "value"
    del module.ordinary
    for name in ("_operator_summary_evaluator_bootstrap", "__class__"):
        try:
            setattr(module, name, object())
        except AttributeError as error:
            assert str(error) == f"protected_operator_evaluator_binding:{name}"
        else:
            raise AssertionError(f"protected binding accepted: {name}")
    try:
        del module._operator_summary_evaluator_bootstrap
    except AttributeError as error:
        assert str(error) == (
            "protected_operator_evaluator_binding:_operator_summary_evaluator_bootstrap"
        )
    else:
        raise AssertionError("protected binding deletion unexpectedly succeeded")


def test_config_quality_disposition_identity_uses_documented_fallback_order() -> None:
    assert config_quality_checks._disposition_card_id(
        {
            "composite_card_key": "deck:CARD_A",
            "official_semantics": {"GameCardId": "CARD_B"},
            "physical_owner": "CARD_C",
        }
    ) == "CARD_A"
    assert config_quality_checks._disposition_card_id(
        {"official_semantics": {"GameCardId": " CARD_B "}}
    ) == "CARD_B"
    assert config_quality_checks._disposition_card_id(
        {"official_semantics": [], "physical_owner": " CARD_C "}
    ) == "CARD_C"
    assert config_quality_checks._disposition_card_id({}) == ""


def test_config_quality_trace_index_uses_only_emitted_source_backed_runtime_rows() -> None:
    explainability = {
        "claim_rows": [
            "invalid",
                {
                    "builder_or_router_decision": "suppressed",
                    "emitted_runtime_files": ["SW_448.json"],
                },
                {
                    "builder_or_router_decision": "emitted",
                    "claim_id": "claim-a",
                    "emitted_runtime_files": ["SW_448.json", "Mulligan.json", ""],
            },
        ],
        "card_rows": [
            "invalid",
            {"card_id": "ignored", "evidence_chain": "invalid"},
            {
                    "card_id": "SW_446",
                    "source_lane": "deck_matched_public_guide",
                    "emitted_runtime_files": ["TOY_381.json"],
                "evidence_chain": [
                    "invalid",
                    {
                        "claim_id": "claim-c",
                            "runtime_files": ["TOY_381.json"],
                    },
                ],
            },
        ],
    }

    assert config_quality_checks._traced_card_ids(explainability) == {
        "SW_448",
        "SW_446",
        "TOY_381",
    }
    assert config_quality_checks._traced_claim_ids_by_card(explainability) == {
        "SW_448": {"claim-a"},
        "TOY_381": {"claim-c"},
    }
    assert config_quality_checks._traced_card_ids(
        {"claim_rows": {}, "card_rows": {}}
    ) == set()
    assert config_quality_checks._traced_claim_ids_by_card(
        {"claim_rows": {}, "card_rows": {}}
    ) == {}


def test_config_quality_runtime_trace_matching_prefers_claim_bindings_when_present() -> None:
    traced_cards = {"A"}
    traced_claims = {"A": {"claim-one"}}
    assert config_quality_checks._runtime_row_has_trace(
        {"card_id": "A"},
        traced_cards,
        traced_claims,
    )
    assert config_quality_checks._runtime_row_has_trace(
        {"runtime_card_id": "A", "source_claim_ids": ["claim-one", ""]},
        set(),
        traced_claims,
    )
    assert not config_quality_checks._runtime_row_has_trace(
        {"card_id": "A", "claim_id": "claim-other"},
        traced_cards,
        traced_claims,
    )


def test_config_quality_runtime_cardid_reader_ignores_metadata_and_malformed_blocks(
) -> None:
    package = _quality_package_root(
        {
            "CustomConfig/Deck/INVALID.json": [],
            "CustomConfig/Deck/SW_448.json": {
                "GameCardId": "SW_448",
                "ConfigComment": "ignored",
                "Play": {
                    "values": [
                        "invalid",
                        {"condition": "mana>=2", "value": 1},
                    ]
                },
                "Target": [{"condition": "enemy", "value": "best"}],
                "BadValues": {"values": {}},
                "BadBlock": "invalid",
            },
        }
    )

    rows = config_quality_checks._runtime_cardid_value_rows(package)

    assert rows == [
        {
            "card_id": "SW_448",
            "behavior_block": "Play",
            "condition": "mana>=2",
            "value": "1",
        },
        {
            "card_id": "SW_448",
            "behavior_block": "Target",
            "condition": "enemy",
            "value": "best",
        },
    ]


def test_config_quality_mulligan_claim_acceptance_requires_keep_action_card_and_claim(
) -> None:
    package = _quality_package_root(
        {
            "reports/mulligan_plan_report.json": {
                "rules": [
                    "invalid",
                    {"action": "discard", "card": "CARD_A", "claim_id": "claim"},
                    {"action": "keep", "card": "CARD_B", "claim_id": "claim"},
                    {"action": "hold", "card": "CARD_A", "claim_id": "other"},
                    {
                        "value": "keep",
                        "card": "CARD_A",
                        "source_claim_ids": ["claim"],
                    },
                ]
            },
        }
    )

    assert config_quality_checks._mulligan_plan_accepts_claim(
        package,
        "CARD_A",
        {"claim"},
    )
    assert not config_quality_checks._mulligan_plan_accepts_claim(
        package,
        "CARD_Z",
        {"claim"},
    )


def test_config_quality_source_contract_acceptance_checks_both_reports(
) -> None:
    package = _quality_package_root(
        {
            "reports/source_contract_audit.json": {
                "claim_rows": {
                    "ignored": "invalid",
                    "wrong-claim": {
                        "claim_kind": "mulligan_keep",
                        "cards": ["CARD_A"],
                        "claim_id": "other",
                        "builder_or_router_decision": "emitted",
                    },
                    "wrong-card": {
                        "claim_kind": "mulligan_keep",
                        "cards": ["CARD_B"],
                        "claim_id": "claim",
                        "builder_or_router_decision": "emitted",
                    },
                }
            },
            "reports/source_to_runtime_explainability.json": {
                "claim_rows": [
                    {
                        "claim_kind": "mulligan_keep",
                        "cards": ["CARD_A"],
                        "claim_id": "claim",
                        "runtime_surfaces": ["Mulligan.json"],
                    }
                ]
            },
        }
    )

    assert config_quality_checks._source_contract_accepts_claim(
        package,
        "CARD_A",
        {"claim"},
    )
    assert not config_quality_checks._source_contract_accepts_claim(
        package,
        "CARD_Z",
        {"claim"},
    )


def test_config_quality_report_row_and_json_helpers_reject_invalid_shapes() -> None:
    one = {"claim_id": "one"}
    two = {"claim_id": "two"}
    assert config_quality_checks._report_rows([], ("rows",)) == []
    assert config_quality_checks._report_rows(
        {"rows": [one, "invalid"], "mapping": {"two": two, "bad": []}},
        ("rows", "mapping"),
    ) == [one, two]
    assert config_quality_checks._row_claim_ids(
        {
            "claim_id": "one",
            "source_claim_ids": [" two ", ""],
            "claim_ids": "three",
        }
    ) == {"one", "two", "three"}
    assert config_quality_checks._json_mentions(
        {"nested": ["CARD_A", {"other": "value"}]},
        "CARD_A",
    )
    assert not config_quality_checks._json_mentions(3, "CARD_A")


def test_config_quality_source_contract_decision_recognizes_emission_signals() -> None:
    assert config_quality_checks._source_contract_row_is_accepted_for_mulligan(
        {"builder_or_router_decision": "emitted"}
    )
    assert config_quality_checks._source_contract_row_is_accepted_for_mulligan(
        {"emitted_runtime_files": ["Mulligan.json"]}
    )
    assert config_quality_checks._source_contract_row_is_accepted_for_mulligan(
        {"runtime_surfaces": ["Mulligan.json"]}
    )
    assert not config_quality_checks._source_contract_row_is_accepted_for_mulligan({})


class _BuildResourceStore:
    def __init__(self, value: object) -> None:
        self.value = value

    def read_by_sha256(self, _content_sha256: str) -> object:
        return self.value


def test_build_context_resource_loader_requires_immutable_hash_bound_canonical_bytes() -> None:
    canonical = b'{"value":1}'
    digest = build_context._raw_sha256(canonical)
    assert build_context._resource(
        _BuildResourceStore(canonical),
        digest,
        error="fixture",
    ) == (canonical, {"value": 1})

    try:
        build_context._resource(
            _BuildResourceStore(bytearray(canonical)),
            digest,
            error="fixture",
        )
    except ValueError as error:
        assert str(error) == "fixture_resource_mutable"
    else:
        raise AssertionError("mutable build resource unexpectedly accepted")

    try:
        build_context._resource(
            _BuildResourceStore(canonical),
            "sha256:" + ("0" * 64),
            error="fixture",
        )
    except ValueError as error:
        assert str(error) == "fixture_resource_sha256_mismatch"
    else:
        raise AssertionError("stale build resource digest unexpectedly accepted")


def test_resolved_resource_bytes_freeze_buffer_types_and_reject_bad_inputs() -> None:
    canonical = b'{"value":1}'
    digest = build_context._raw_sha256(canonical)
    assert build_context._resolved_context_resource_bytes(
        memoryview(canonical),
        expected_sha256=digest,
        label="fixture",
    ) == canonical
    for value, reason in (
        ("not-bytes", "resolved_build_fixture_resource_mutable"),
        (b'{"value": 1}', "resolved_build_fixture_json_noncanonical"),
        (canonical, "resolved_build_fixture_resource_sha256_mismatch"),
    ):
        expected_digest = digest if value != canonical else "sha256:" + ("0" * 64)
        try:
            build_context._resolved_context_resource_bytes(
                value,  # type: ignore[arg-type]
                expected_sha256=expected_digest,
                label="fixture",
            )
        except ValueError as error:
            assert str(error) == reason
        else:
            raise AssertionError(f"invalid resolved resource accepted: {value!r}")


def test_build_context_canonical_document_rejects_encoding_order_and_duplicate_keys() -> None:
    assert build_context._canonical_document(
        b'{"a":1,"b":2}',
        error="fixture",
    ) == {"a": 1, "b": 2}
    invalid_cases = [
        (b"\xff", "fixture_json_invalid"),
        (b"{not-json", "fixture_json_invalid"),
        (b'{"b":2,"a":1}', "fixture_json_noncanonical"),
        (b'{"a":1,"a":2}', "fixture_json_invalid"),
    ]
    for raw, reason in invalid_cases:
        try:
            build_context._canonical_document(raw, error="fixture")
        except ValueError as error:
            assert str(error) == reason
        else:
            raise AssertionError(f"invalid canonical document accepted: {raw!r}")


def test_build_context_row_order_date_and_self_hash_helpers_are_fail_closed() -> None:
    assert build_context._rows_are_canonical([{"a": 1}, {"b": 2}])
    assert not build_context._rows_are_canonical([{"b": 2}, {"a": 1}])
    assert not build_context._rows_are_canonical([{"a": 1}, {"a": 1}])
    assert build_context._valid_date("2026-08-01")
    assert not build_context._valid_date(None)
    assert not build_context._valid_date("2026-99-99")

    payload = {"schema_version": 1, "value": "fixture"}
    document = {
        **payload,
        "content_sha256": build_context._raw_sha256(
            build_context._canonical_json(payload)
        ),
    }
    build_context._validate_self_hash(document, error="fixture_hash_stale")
    try:
        build_context._validate_self_hash(
            {**document, "value": "changed"},
            error="fixture_hash_stale",
        )
    except ValueError as error:
        assert str(error) == "fixture_hash_stale"
    else:
        raise AssertionError("stale self hash unexpectedly accepted")


def test_build_context_canonical_json_rejects_unserializable_and_recursive_values() -> None:
    recursive: list[object] = []
    recursive.append(recursive)
    for value in ({"bad": object()}, recursive):
        try:
            build_context._canonical_json(value)
        except ValueError as error:
            assert str(error) == "resolved_build_json_invalid"
        else:
            raise AssertionError("unserializable build document unexpectedly accepted")


def test_authority_node_constructor_rejects_ambiguous_missing_and_extra_arguments() -> None:
    status = package_domain.DualClosureStatus(
        "complete",
        "strong",
        True,
        (),
    )
    assert status.pre_run_contract_status == "complete"
    assert status.__reduce__() == (package_domain.DualClosureStatus, tuple(status))
    invalid_calls = [
        lambda: package_domain.DualClosureStatus("complete", "strong", True, (), "extra"),
        lambda: package_domain.DualClosureStatus(
            "complete",
            strategy_authority_status="strong",
            exact_guide_authority=True,
            unresolved_reasons=(),
            pre_run_contract_status="complete",
        ),
        lambda: package_domain.DualClosureStatus("complete"),
        lambda: package_domain.DualClosureStatus(
            pre_run_contract_status="complete",
            strategy_authority_status="strong",
            exact_guide_authority=True,
            unresolved_reasons=(),
            unexpected=True,
        ),
    ]
    for call in invalid_calls:
        try:
            call()
        except TypeError:
            pass
        else:
            raise AssertionError("invalid authority constructor call unexpectedly accepted")


def test_frozen_definition_containers_are_mapping_compatible_but_immutable() -> None:
    mapping = package_domain.FrozenDefinitionMapping(
        {"one": 1, "nested": {"two": [2]}}
    )
    assert mapping["one"] == 1
    assert "one" in mapping
    assert "missing" not in mapping
    assert repr(mapping) == "{'one': 1, 'nested': {'two': [2]}}"
    assert mapping == {"one": 1, "nested": {"two": [2]}}
    assert mapping != [("one", 1)]
    try:
        mapping["missing"]
    except KeyError as error:
        assert error.args == ("missing",)
    else:
        raise AssertionError("missing frozen mapping key unexpectedly resolved")
    for mutation in (
        lambda: mapping.__setattr__("x", 1),
        lambda: mapping.__setitem__("x", 1),
        lambda: mapping.__delitem__("one"),
        lambda: mapping.__ior__({"x": 1}),
    ):
        try:
            mutation()
        except TypeError as error:
            assert str(error) == "frozen_definition"
        else:
            raise AssertionError("frozen mapping mutation unexpectedly accepted")

    sequence = package_domain.FrozenDefinitionList([1, {"two": 2}])
    assert repr(sequence) == "[1, {'two': 2}]"
    assert sequence == [1, {"two": 2}]
    assert sequence != {1, 2}
    try:
        sequence.__setattr__("x", 1)
    except TypeError as error:
        assert str(error) == "frozen_definition"
    else:
        raise AssertionError("frozen list mutation unexpectedly accepted")


def test_deep_freeze_and_materialize_round_trip_nested_definition_shapes() -> None:
    original = {
        "list": [1, {"nested": 2}],
        "tuple": (3, 4),
        "set": {5, 6},
    }
    frozen = package_domain.deep_freeze_definition(original)
    assert isinstance(frozen, package_domain.FrozenDefinitionMapping)
    assert isinstance(frozen["list"], package_domain.FrozenDefinitionList)
    materialized = package_domain.materialize_definition(frozen)
    assert materialized == {
        "list": [1, {"nested": 2}],
        "tuple": [3, 4],
        "set": {5, 6},
    }
    assert package_domain.deep_freeze_definition("value") == "value"
    assert package_domain.materialize_definition("value") == "value"


def test_package_domain_canonical_json_stable_strings_and_paths_fail_closed() -> None:
    assert package_domain._canonical_json(b'{"a":1}') == b'{"a":1}'
    for raw, reason in (
        (b"{invalid", "canonical_json_invalid"),
        (b'{"a": 1}', "canonical_json_required"),
    ):
        try:
            package_domain._canonical_json(raw)
        except ValueError as error:
            assert str(error) == reason
        else:
            raise AssertionError(f"invalid canonical JSON accepted: {raw!r}")
    assert package_domain._freeze_stable_strings(
        ("a", "b"),
        field="fixture",
    ) == ("a", "b")
    for values, reason in (
        (("",), "fixture_invalid"),
        ((" padded ",), "fixture_invalid"),
        (("b", "a"), "fixture_must_be_unique_sorted"),
        (("a", "a"), "fixture_must_be_unique_sorted"),
    ):
        try:
            package_domain._freeze_stable_strings(values, field="fixture")
        except ValueError as error:
            assert str(error) == reason
        else:
            raise AssertionError(f"invalid stable strings accepted: {values!r}")
    assert package_domain.canonical_relative_path("reports/file.json") == (
        "reports/file.json"
    )
    for value in (None, "", "a\\b", "a\x00b", "C:a", "/a", "a//b", "a/./b", "a/../b"):
        try:
            package_domain.canonical_relative_path(value)  # type: ignore[arg-type]
        except ValueError as error:
            assert str(error) == "runtime_surface_path_invalid"
        else:
            raise AssertionError(f"unsafe runtime path accepted: {value!r}")


def test_policy_profile_validates_identity_date_digest_and_nonempty_rules() -> None:
    rules = b'[{"id":"rule"}]'
    digest = "sha256:" + __import__("hashlib").sha256(rules).hexdigest()
    profile = package_domain.PolicyProfile(
        policy_id="policy",
        version=1,
        effective_date="2026-08-01",
        content_sha256=digest,
        rules_canonical_json=rules,
    )
    assert profile.policy_id == "policy"
    invalid = [
        ({"policy_id": " padded "}, "policy_profile_id_invalid"),
        ({"version": True}, "policy_profile_version_invalid"),
        ({"version": 0}, "policy_profile_version_invalid"),
        ({"effective_date": "invalid"}, "policy_profile_effective_date_invalid"),
        ({"content_sha256": "sha256:stale"}, "policy_profile_content_sha256_invalid"),
    ]
    base = dict(zip((field.name for field in __import__("dataclasses").fields(profile)), tuple(profile)))
    for changes, reason in invalid:
        try:
            package_domain.PolicyProfile(**{**base, **changes})
        except ValueError as error:
            assert str(error) == reason
        else:
            raise AssertionError(f"invalid policy profile accepted: {changes!r}")


def test_combo_model_helpers_reject_bad_operators_containers_and_authority() -> None:
    assert package_domain.ComboTiming.SAME_TURN.operator == ">>"
    assert package_domain.ComboTiming.CROSS_TURN.operator == ">->"
    assert package_domain.ComboTiming.from_operator(">>") is (
        package_domain.ComboTiming.SAME_TURN
    )
    try:
        package_domain.ComboTiming.from_operator("?")
    except ValueError as error:
        assert str(error) == "combo_operator_invalid"
    else:
        raise AssertionError("unknown combo operator unexpectedly accepted")

    for values, reason in (
        ("A", "combo_cards_container_invalid"),
        (["A", ""], "combo_cards_invalid"),
        ([" A "], "combo_cards_invalid"),
    ):
        try:
            package_domain._combo_strings(values, field="combo_cards")
        except ValueError as error:
            assert str(error) == reason
        else:
            raise AssertionError(f"invalid combo strings accepted: {values!r}")
    try:
        package_domain._combo_report_rows({"combos": ["invalid"]}, "combos")
    except ValueError as error:
        assert str(error) == "Invalid combo sequence collection"
    else:
        raise AssertionError("invalid combo report rows unexpectedly accepted")


def _runtime_surface(
    family: str,
    relative_path: str,
    owner: str,
    decision_ids: tuple[str, ...],
) -> package_domain.RuntimeSurfaceDecision:
    return package_domain.RuntimeSurfaceDecision(
        family=family,
        relative_path=relative_path,
        owner=owner,
        decision_ids=decision_ids,
    )


def test_runtime_surface_plan_validates_family_owner_core_paths_ids_and_forbidden_files() -> None:
    globalvalues = _runtime_surface(
        "GlobalValues",
        "GlobalValues.json",
        "globalvalues",
        ("globalvalues:one",),
    )
    mulligan = _runtime_surface(
        "Mulligan",
        "Mulligan.json",
        "mulligan",
        ("mulligan:one",),
    )
    assert package_domain.RuntimeSurfacePlan(
        surfaces=(globalvalues, mulligan)
    ).expected_files == ("GlobalValues.json", "Mulligan.json")

    for args, reason in (
        (("Unknown", "Unknown.json", "unknown", ()), "runtime_surface_family_unknown"),
        (("Mulligan", "Mulligan.json", "wrong", ()), "runtime_surface_owner_unknown"),
    ):
        try:
            _runtime_surface(*args)
        except ValueError as error:
            assert str(error) == reason
        else:
            raise AssertionError(f"invalid runtime surface accepted: {args!r}")

    invalid_plans = [
        ((mulligan, globalvalues), "runtime_surface_paths_not_unique_sorted"),
        ((globalvalues,), "runtime_surface_core_missing_or_duplicate"),
        (
                (
                    mulligan,
                    _runtime_surface("GlobalValues", "Other.json", "globalvalues", ()),
                ),
            "runtime_surface_core_path_invalid",
        ),
        (
            (
                _runtime_surface("GlobalValues", "GlobalValues.json", "globalvalues", ("bad",)),
                mulligan,
            ),
            "runtime_surface_globalvalues_id_invalid",
        ),
        (
            (
                globalvalues,
                _runtime_surface("Mulligan", "Mulligan.json", "mulligan", ("bad",)),
            ),
            "runtime_surface_mulligan_id_invalid",
        ),
        (
            (
                globalvalues,
                mulligan,
                _runtime_surface("CardID", "Presume.json", "cardid", ("card:Presume",)),
            ),
            "runtime_surface_forbidden",
        ),
    ]
    for surfaces, reason in invalid_plans:
        try:
            package_domain.RuntimeSurfacePlan(surfaces=surfaces)
        except ValueError as error:
            assert str(error) == reason
        else:
            raise AssertionError(f"invalid runtime surface plan accepted: {surfaces!r}")


def test_source_claim_lifecycle_distinguishes_modern_legacy_and_quality_lanes() -> None:
    assert source_document_model.strict_claim_kind(
        {"claim_kind": "mulligan_keep"}
    ) == "mulligan_keep"
    assert source_document_model.strict_claim_kind(
        {"claim_kind": "MULLIGAN_KEEP"}
    ) == ""
    assert source_document_model.normalized_claim_kind(
        {"claim_type": " combo "}
    ) == "combo_sequence"
    assert source_document_model.normalized_claim_kind(
        {"claim_type": " targeting_rule "}
    ) == "targeting_rule"
    assert source_document_model.normalized_claim_kind(
        {"claim_type": "similar but unsupported"}
    ) == ""

    statistical = source_document_model.qualify_source_claim(
        {
            "claim_kind": "archetype",
            "source_type": "replay_stat_aggregate",
        }
    )
    assert statistical["source_lane"] == "statistical_enrichment"
    assert statistical["runtime_lowering"] == "contract_only"
    assert statistical["promotion_eligible"] is False
    assert statistical["evidence_lane_candidate"] is None

    assert source_document_model.evidence_lane_candidate(
        {
            "source_type": "public_guide",
            "source_visibility": "full_text",
            "deck_match_scope": "mechanic_matched",
        }
    ) == "C"

    runtime_lowerings = {
        claim_kind: source_document_model.qualify_source_claim(
            {
                "claim_kind": claim_kind,
                "source_type": "official_card_data",
            }
        )["runtime_lowering"]
        for claim_kind in ("combo_sequence", "gameplan_posture", "card_role")
    }
    assert runtime_lowerings == {
        "combo_sequence": "combo",
        "gameplan_posture": "globalvalues_or_contract_only",
        "card_role": "cardid_or_contract_only",
    }

    weak_exact_guide = source_document_model.qualify_source_claim(
        {
            "claim_kind": "mulligan_keep",
            "source_type": "public_guide",
            "source_visibility": "full_text",
            "source_lane": "deck_matched_public_guide",
            "deck_match_scope": "exact_deck_matched",
            "source_record_strength": "weak",
        }
    )
    assert weak_exact_guide["promotion_eligible"] is True
    assert weak_exact_guide["strong_promotion_eligible"] is False


def test_source_claim_context_and_boolean_normalization_preserve_explicit_intent() -> None:
    assert source_document_model.claim_has_explicit_mulligan_context(
        {"semantic_qualifiers": {"timing": " opening hand "}}
    )
    assert not source_document_model.claim_has_explicit_mulligan_context(
        {"semantic_qualifiers": []}
    )
    assert source_document_model._bool_value("maybe") is True
    assert source_document_model._bool_value(" off ") is False

    assert not source_document_model.claim_can_lower_to_runtime(
        {
            "trust_ceiling": "report_only",
            "claim_readiness": "guide_backed",
        }
    )
    assert source_document_model.claim_can_lower_to_runtime(
        {"claim_readiness": "source_backed_static_semantics"}
    )
    assert not source_document_model.claim_can_lower_to_runtime(
        {"claim_readiness": "contract_gap", "confidence": "high"}
    )
    assert not source_document_model.claim_can_lower_to_runtime(
        {"confidence": "generic_low_confidence"}
    )
    assert source_document_model.claim_can_lower_to_runtime(
        {"confidence": "high"}
    )


def test_public_guide_identity_signals_require_only_recognized_nonempty_values() -> None:
    signal_only_claim = {
        "source_identity_signals": [
            "invalid",
            {"field": "unknown", "value": "public_guide"},
            {"field": "source_family", "value": ""},
            {"field": "source_type", "value": "public_guide"},
            {"field": "provenance", "value": "community_guide"},
        ]
    }
    assert source_document_model._is_canonical_public_guide_source(
        signal_only_claim
    )
    assert not source_document_model._is_canonical_public_guide_source(
        {
            **signal_only_claim,
            "source_family": "static_semantics",
        }
    )
    assert not source_document_model._is_canonical_public_guide_source(
        {"source_identity_signals": {"field": "source_type", "value": "public_guide"}}
    )


def test_verified_source_receipts_bind_claim_identity_signature_and_provenance() -> None:
    provenance = {
        "mode": "live_http",
        "content_sha256": "sha256:" + ("1" * 64),
        "authority": "live_verified",
    }
    claim = {
        "claim_id": "claim-one",
        "claim_kind": "mulligan_keep",
        "cards": ["CARD_001"],
        "acquisition_provenance": provenance,
    }
    signature = source_document_model.source_claim_signature(claim)
    matching = {
        "receipt_kind": "canonical_exact_deck_source_document",
        "matched_deck_fingerprint": "deck-one",
        "claim_id": "claim-one",
        "claim_signature": signature,
        "acquisition_provenance": provenance,
    }
    rejected_receipts: list[object] = [
        "invalid",
        {**matching, "receipt_kind": "other"},
        {**matching, "matched_deck_fingerprint": "other-deck"},
        {**matching, "claim_id": "other-claim"},
        {**matching, "claim_signature": "sha256:stale"},
        {
            **matching,
            "acquisition_provenance": {**provenance, "authority": "captured_unverified"},
        },
    ]

    assert not source_document_model.has_verified_source_receipt(
        claim,
        target_fingerprint="deck-one",
        verified_source_receipts=rejected_receipts,  # type: ignore[arg-type]
    )
    assert source_document_model.has_verified_source_receipt(
        claim,
        target_fingerprint="deck-one",
        verified_source_receipts=[*rejected_receipts, matching],  # type: ignore[list-item]
    )
    assert source_document_model.strategic_provenance_diagnostic(
        {"claim_kind": "card_role"}
    ) is None
    assert source_document_model.strategic_provenance_diagnostic(claim) is None


def test_combo_deck_cards_and_cardid_choice_gates_normalize_supported_shapes() -> None:
    assert source_document_model._combo_contract_deck_cards(
        {},
        deck_identity=None,
        deck_cards=["CARD_A", "CARD_B"],
    ) == {"CARD_A", "CARD_B"}
    assert source_document_model._combo_contract_deck_cards(
        {},
        deck_identity={"cards": {"CARD_A": {}, "CARD_B": {}}},
        deck_cards=None,
    ) == {"CARD_A", "CARD_B"}
    assert source_document_model._combo_contract_deck_cards(
        {},
        deck_identity={
            "cards": [
                {"card_id": "CARD_A"},
                {"card_id": ""},
                "invalid",
            ]
        },
        deck_cards=None,
    ) == {"CARD_A"}
    assert source_document_model._combo_contract_deck_cards(
        {},
        deck_identity={"cards": "invalid"},
        deck_cards=None,
    ) == set()
    assert source_document_model._combo_contract_deck_cards(
        {"sequence": "CARD_A"},
        deck_identity=None,
        deck_cards=None,
    ) == {"CARD_A"}
    assert source_document_model._combo_contract_deck_cards(
        {"sequence": 3},
        deck_identity=None,
        deck_cards=None,
    ) == set()

    blocked = source_document_model.can_lower_to_cardid(
        {"claim_kind": "card_role", "claim_readiness": "contract_gap"}
    )
    assert (blocked.allowed, blocked.reason) == (
        False,
        "claim_not_runtime_lowerable",
    )
    strategic = source_document_model.can_lower_to_cardid(
        {"claim_kind": "targeting_rule"}
    )
    assert (strategic.allowed, strategic.reason) == (
        False,
        "targeting_requires_public_guide_source",
    )
    assert source_document_model.can_lower_to_cardid(
        {"claim_kind": "card_role"}
    ).allowed

    choice = {
        "claim_kind": "discover_choice",
        "cards": "CARD_A",
        "option_card_id": "OPTION_1",
    }
    missing_identity = source_document_model.surface_gate_decision(
        choice,
        "card_behavior",
    )
    assert (missing_identity.allowed, missing_identity.reason) == (
        False,
        "requires_exact_option_identity",
    )
    linked_identity = source_document_model.surface_gate_decision(
        choice,
        "card_behavior",
        context={
            "identity_links": {
                "CARD_A": {"links": [{"card_id": "OPTION_1"}]},
            }
        },
    )
    assert linked_identity.allowed
    unknown = source_document_model.surface_gate_decision(choice, "future_surface")
    assert (unknown.allowed, unknown.reason, unknown.surface) == (
        False,
        "unknown_surface",
        "future_surface",
    )

    assert source_document_model._linked_identity_card_ids(
        {"card_id": "OPTION_1"}
    ) == {"OPTION_1"}
    assert source_document_model._linked_identity_card_ids({"other": 1}) == set()
    assert source_document_model._linked_identity_card_ids("invalid") == set()
    assert source_document_model._linked_identity_card_ids(
        ["OPTION_1", {"card_id": "OPTION_2"}, {"card_id": ""}, 3]
    ) == {"OPTION_1", "OPTION_2"}


def test_config_quality_report_only_mechanics_obey_source_field_policy() -> None:
    row = {
        "mechanic": "Combo",
        "mechanic_families": ["mulligan anchor", "battlecry"],
        "semantic_families": ["combo", "unknown"],
        "roles": ["body pressure", "combo"],
    }

    assert config_quality_checks._report_only_mechanics_from_row(row) == [
        "combo",
        "mulligan_anchor",
    ]
    assert config_quality_checks._report_only_mechanics_from_value(
        "combo",
        source_key="unknown",
    ) == set()
    assert config_quality_checks._canonical_mechanic_token(
        "Mulligan Anchor"
    ) == "mulligan_anchor"
    assert not config_quality_checks._is_report_only_mechanic_token(
        "body_pressure",
        "body_pressure",
        source_key="roles",
    )
    assert not config_quality_checks._is_report_only_mechanic_token(
        "battlecry",
        "battlecry",
        source_key="mechanic",
    )


def test_config_quality_claim_index_and_link_projection_deduplicate_source_rows() -> None:
    shared = {"claim_id": "claim-shared", "stance": "battlecry"}
    by_claim = config_quality_checks._source_rows_by_claim_id(
        {
            "source_claims": [shared, "invalid"],
            "source_backed_actions": {
                "one": {"source_claim_ids": ["claim-one", "claim-shared"]}
            },
            "guide_claim_bundle": {
                "unsupported_claims": [
                    {"claim_id": "claim-nested", "claim_kind": "card_role"}
                ]
            },
        },
        {
            "claims": [
                {"claim_id": "claim-guide", "claim_kind": "targeting_rule"}
            ]
        },
    )

    assert set(by_claim) == {
        "claim-guide",
        "claim-nested",
        "claim-one",
        "claim-shared",
    }
    linked = config_quality_checks._linked_source_rows(
        {
            "claim_id": "claim-shared",
            "source_claim_ids": ["claim-one", "claim-shared"],
        },
        by_claim,
    )
    assert len(linked) == 2
    assert shared in linked


def test_config_quality_target_and_battlecry_authority_fail_closed() -> None:
    assert not config_quality_checks._has_only_non_targeted_battlecry_authority(
        {},
        [],
    )
    battlecry = {
        "claim_id": "claim-battlecry",
        "behavior_block": "BeforeBattlecryTargetBonus",
    }
    assert config_quality_checks._has_only_non_targeted_battlecry_authority(
        battlecry,
        [],
    )
    for row in (
        {"target_scope": "enemy_hero"},
        {"semantic_qualifiers": {"target_scope": "enemy_minion"}},
        {"stance": "prefer_enemy_hero"},
    ):
        assert config_quality_checks._has_target_authority([row])
    assert not config_quality_checks._has_target_authority(
        [{"semantic_qualifiers": [], "stance": "battlecry"}]
    )
    assert not config_quality_checks._has_only_non_targeted_battlecry_authority(
        battlecry,
        [{"claim_id": "claim-battlecry", "stance": "targeting_rule"}],
    )
    assert config_quality_checks._mentions_battlecry(
        {"mechanic": "battlecry"}
    )
    assert not config_quality_checks._has_explicit_behavior_row_authority(
        {
            "claim_id": "claim-default",
            "semantic_score": {"reason": "semantic_default"},
        }
    )
    assert config_quality_checks._has_explicit_behavior_row_authority(
        {"claim_id": "claim-explicit"}
    )


def test_config_quality_metadata_rows_roles_and_source_cards_accept_real_shapes() -> None:
    mapping_rows = config_quality_checks._card_metadata_rows(
        {
            "A": {"roles": ["Burn"]},
            "B": "invalid",
            "C": {"card_id": "EXPLICIT", "classification": "tempo"},
        }
    )
    assert mapping_rows == [
        {"roles": ["Burn"], "card_id": "A"},
        {"card_id": "EXPLICIT", "classification": "tempo"},
    ]
    assert config_quality_checks._card_metadata_rows(
        [{"card_id": "D"}, "invalid"]
    ) == [{"card_id": "D"}]
    assert config_quality_checks._card_metadata_rows("invalid") == []

    assert config_quality_checks._has_card_specific_source_metadata(
        {"source_claim_ids": ["claim"]}
    )
    assert config_quality_checks._has_card_specific_source_metadata(
        {"classification": {"role": "burn"}}
    )
    assert config_quality_checks._has_card_specific_source_metadata(
        {"classification": "tempo"}
    )
    assert not config_quality_checks._has_card_specific_source_metadata({})

    roles = config_quality_checks._semantic_surface_roles_by_card(
        {
            "rows": [
                {
                    "card_id": "A",
                    "surface_family": "CARDID.json",
                    "meaningful_runtime_surface": True,
                    "behavior_block": "BeforePlayCardBonus",
                    "roles": ["Burn"],
                }
            ]
        },
        {
            "cards": {"A": {"semantic_families": ["Aggro"]}},
            "card_role_map": [
                {"card_id": "B", "mechanic_families": ["Combo"]}
            ],
        },
        {"cards": [{"card_id": "C", "roles": ["Taunt"]}]},
    )
    assert roles == {
        "A": {"aggro", "beforeplaycardbonus", "burn"},
        "B": {"combo"},
        "C": {"taunt"},
    }
    assert config_quality_checks._card_specific_source_metadata_cards(
        {
            "cards": {"A": {"roles": ["burn"]}},
            "card_role_map": [{"card_id": "B", "classification": "tempo"}],
        },
        {"cards": [{"card_id": "C"}, {"card_id": "D", "roles": ["taunt"]}]},
    ) == {"A", "B", "D"}


def test_config_quality_token_deduplication_and_warning_summary_are_deterministic() -> None:
    assert config_quality_checks._semantic_surface_role_tokens(
        {
            "roles": ["Body Pressure", ""],
            "semantic_families": "Burn",
            "mechanic_families": None,
        }
    ) == {"body_pressure", "burn"}
    assert config_quality_checks._semantic_surface_tokens(
        {
            "roles": ["Body Pressure"],
            "behavior_block": "Before-Play Card Bonus",
            "stance": "Prefer Enemy's Hero",
        }
    ) == {
        "body_pressure",
        "before_play_card_bonus",
        "prefer_enemys_hero",
    }
    assert config_quality_checks._normalized_tokens("  ") == set()

    duplicate = {"card_id": "B", "behavior_block": "Block", "value": "2"}
    assert config_quality_checks._dedupe_sorted_rows(
        [
            duplicate,
            dict(duplicate),
            {"card_id": "A", "behavior_block": "Block", "value": "1"},
        ]
    ) == [
        {"card_id": "A", "behavior_block": "Block", "value": "1"},
        duplicate,
    ]
    assert config_quality_checks._compact_runtime_row(duplicate) == duplicate
    assert config_quality_checks._semantic_warning_only_summary(
        {
            "cards": {
                "A": {
                    "warning_only_mechanics": ["discover", ""],
                    "warning_only": "combo",
                },
                "B": "invalid",
                "C": {"warning_only": []},
            }
        }
    ) == {"card_count": 1, "mechanics": ["combo", "discover"]}
    assert config_quality_checks._semantic_warning_only_summary(
        {"cards": "invalid"}
    ) == {"card_count": 0, "mechanics": []}
    assert config_quality_checks._list_of_mappings(
        [{"reason": "one"}, "invalid"]
    ) == [{"reason": "one"}]
    assert config_quality_checks._list_of_mappings({}) == []
    assert config_quality_checks._taxonomy_reason_counts(
        {
            "semantic_score_rows": [
                {"reason": "semantic_default"},
                {"reason": "semantic_default"},
                {"reason": ""},
            ]
        }
    ) == {"semantic_default": 2}


def test_config_quality_mulligan_and_runtime_value_helpers_accept_only_explicit_intent() -> None:
    assert not config_quality_checks._mulligan_keep_mentions_card(
        "invalid",
        "CARD_A",
    )
    assert config_quality_checks._mulligan_keep_mentions_card(
        {"Keep": ["CARD_A"]},
        "CARD_A",
    )
    assert not config_quality_checks._mulligan_keep_mentions_card(
        {"Mulligan": []},
        "CARD_A",
    )
    assert not config_quality_checks._mulligan_keep_mentions_card(
        {"Mulligan": {"values": "invalid"}},
        "CARD_A",
    )
    assert config_quality_checks._mulligan_keep_mentions_card(
        {
            "Mulligan": {
                "values": [
                    "invalid",
                    {"action": "discard", "cards": ["CARD_A"]},
                    {"value": "keep", "selector": {"card_id": "CARD_A"}},
                ]
            }
        },
        "CARD_A",
    )
    assert not config_quality_checks._mulligan_keep_mentions_card(
        {"Mulligan": {"values": [{"value": "hold", "cards": ["OTHER"]}]}},
        "CARD_A",
    )

    assert config_quality_checks._has_runtime_effect_rows(
        {
            "GameCardId": "CARD_A",
            "BeforePlayCardBonus": {"values": [{"condition": "*", "value": "6"}]},
        }
    )
    assert not config_quality_checks._has_runtime_effect_rows(
        {
            "ConfigComment": "diagnostic",
            "Ignored": [],
            "Empty": {"values": []},
        }
    )


def test_config_quality_public_guide_claim_authority_requires_complete_source_binding() -> None:
    bundle = {
        "source_evidence_index": [
            "invalid",
            {
                "source_ref": "missing-keys",
                "source_family": "guide",
                "missing_source_keys": ["source_title"],
            },
            {
                "source_ref": "wrong-family",
                "source_family": "decklist",
                "source_url": "https://example.test/deck",
                "source_title": "Deck",
                "retrieved_at": "2026-08-01",
            },
            {
                "source_ref": "incomplete",
                "source_family": "guide",
                "source_url": "https://example.test/guide",
                "source_title": "",
                "retrieved_at": "2026-08-01",
            },
            {
                "source_ref": "guide:one",
                "source_family": "guide",
                "source_url": "https://example.test/guide",
                "source_title": "Guide",
                "retrieved_at": "2026-08-01",
            },
        ]
    }
    refs = config_quality_checks._eligible_public_guide_source_refs(bundle)
    assert refs == {"guide:one"}

    claim = {
        "claim_kind": "mulligan_keep",
        "cards": ["CARD_A"],
        "evidence_text_short": "Keep CARD_A in your opening hand.",
        "source_lane": "deck_matched_public_guide",
        "source_refs": ["guide:one"],
        "claim_readiness": "guide_backed",
    }
    assert config_quality_checks._is_source_backed_opening_hand_claim(
        claim,
        refs,
    )
    assert not config_quality_checks._is_source_backed_opening_hand_claim(
        {**claim, "trust_ceiling": "report_only"},
        refs,
    )
    assert not config_quality_checks._is_source_backed_opening_hand_claim(
        {**claim, "evidence_text_short": "Do not keep CARD_A in the opening hand."},
        refs,
    )
    assert not config_quality_checks._is_source_backed_opening_hand_claim(
        {**claim, "source_lane": "static_semantics"},
        refs,
    )
    assert not config_quality_checks._is_source_backed_opening_hand_claim(
        {
            **claim,
            "source_lane": "",
            "source_type": "static_semantics",
        },
        refs,
    )
    assert not config_quality_checks._is_source_backed_opening_hand_claim(
        {**claim, "source_refs": ["guide:other"]},
        refs,
    )


def test_config_quality_report_and_json_search_helpers_normalize_container_shapes() -> None:
    assert config_quality_checks._report_rows("invalid", ("rows",)) == []
    one = {"claim_id": "one"}
    two = {"claim_id": "two"}
    assert config_quality_checks._report_rows(
        {"rows": [one, "invalid"], "mapped": {"two": two, "bad": []}},
        ("rows", "mapped", "missing"),
    ) == [one, two]
    assert config_quality_checks._row_claim_ids(
        {
            "claim_id": "one",
            "source_claim_ids": ["two", ""],
            "claim_ids": "three",
        }
    ) == {"one", "two", "three"}
    assert config_quality_checks._json_mentions("prefix-CARD_A-suffix", "CARD_A")
    assert config_quality_checks._json_mentions(
        {"nested": [{"card": "CARD_A"}]},
        "CARD_A",
    )
    assert not config_quality_checks._json_mentions(7, "CARD_A")

    explicit = {
        "claim_type": "mulligan_keep",
        "cards": ["CARD_A"],
    }
    assert config_quality_checks._is_explicit_mulligan_keep_claim(
        explicit,
        "CARD_A",
    )
    assert not config_quality_checks._is_explicit_mulligan_keep_claim(
        {"claim_kind": "mulligan_discard", "cards": ["CARD_A"]},
        "CARD_A",
    )
    assert config_quality_checks._source_contract_row_is_accepted_for_mulligan(
        {"builder_or_router_decision": "runtime_emitted"}
    )
    assert config_quality_checks._source_contract_row_is_accepted_for_mulligan(
        {"emitted_runtime_files": ["Mulligan.json"]}
    )
    assert not config_quality_checks._source_contract_row_is_accepted_for_mulligan({})


def test_config_quality_emitted_intent_and_surface_rows_cover_all_canonical_families() -> None:
    base = {
        "required_surfaces": ["GlobalValues.json", "Mulligan.json", "CARD_A.json"],
        "optional_surfaces": ["Combo.json"],
    }
    rows = [
        {
            "surface": "GlobalValues.json",
            "rule_id": "globalvalues_full_key_profile",
            "intent": "baseline",
        },
        {
            "surface": "Combo.json",
            "rule_id": "combo_sequences",
            "intent": "sequence",
        },
        {
            "surface": "Mulligan.json",
            "card_id": "CARD_A",
            "rule_id": "CARD_A_mulligan_hold",
            "intent": "hold",
        },
        {
            "surface": "Mulligan.json",
            "card_id": "CARD_A",
            "rule_id": "CARD_A_mulligan_bot_delegation",
            "intent": "delegate_to_hearthranger_bot",
            "intent_source": "versioned_internal_policy",
            "evidence_lane": "E",
            "policy_id": "BOT_NATIVE_PRE_RUN",
            "reason_code": "start_of_game_effect",
        },
        {
            "surface": "CARD_A.json",
            "surface_family": "CARDID.json",
            "card_id": "CARD_A",
            "rule_id": "CARD_A_card_behavior",
            "intent": "behavior",
        },
    ]
    for row in rows:
        assert config_quality_checks._is_canonical_surface_intent_row(base, row)

    invalid_rows = [
        {"surface": "nested/CARD_A.json", "intent": "bad"},
        {"surface": "Presume.json", "intent": "bad"},
        {
            "surface": "GlobalValues.json",
            "card_id": "CARD_A",
            "rule_id": "globalvalues_full_key_profile",
            "intent": "bad",
        },
        {"surface": "Combo.json", "rule_id": "wrong", "intent": "bad"},
        {
            "surface": "CARD_A.json",
            "surface_family": "wrong",
            "card_id": "CARD_A",
            "rule_id": "CARD_A_card_behavior",
            "intent": "bad",
        },
    ]
    for row in invalid_rows:
        assert not config_quality_checks._is_canonical_surface_intent_row(base, row)

    surface_intent = {**base, "rows": [*rows, *invalid_rows]}
    assert config_quality_checks._surface_intent_runtime_files(surface_intent) == {
        "GlobalValues.json",
        "Combo.json",
        "Mulligan.json",
        "CARD_A.json",
    }
    assert config_quality_checks._surface_intent_row_summary(rows[-1]) == {
        "card_id": "CARD_A",
        "rule_id": "CARD_A_card_behavior",
        "surface": "CARD_A.json",
    }

    for row in (
        {"builder_or_router_decision": "emitted"},
        {"runtime_lowering_status": "runtime_lowered"},
        {"resolution_reason": "policy_backed_runtime"},
    ):
        assert config_quality_checks._has_emitted_runtime_intent(row)
    for row in (
        {"first_missing_link": "needs_source"},
        {"suppressed_reason": "policy"},
        {"claim_lane": "report_only"},
    ):
        assert config_quality_checks._has_non_emitted_runtime_marker(row)
        assert not config_quality_checks._has_emitted_runtime_intent(row)
    assert not config_quality_checks._has_non_emitted_runtime_marker({})
    assert config_quality_checks._standard_surface_name(None) == ""
    assert config_quality_checks._standard_surface_name("Combo") == "Combo"


def test_config_quality_explained_runtime_files_merge_claim_card_operator_and_intent_rows() -> None:
    explained = config_quality_checks._explained_runtime_files_from_reports(
        operator={
            "surface_status_ledger": [
                "invalid",
                {"status": "missing", "surface": "Ignored"},
                {"status": "emitted", "surface": "GlobalValues"},
                {
                    "status": "source_backed",
                    "surface": "per-card <CARDID>.json",
                },
            ]
        },
        card_behavior={
            "rows": [
                {
                    "card_id": "CARD_B",
                    "surface_family": "CARDID.json",
                    "behavior_block": "BeforePlayCardBonus",
                }
            ]
        },
        explainability={
            "claim_rows": [
                {
                    "builder_or_router_decision": "emitted",
                    "emitted_runtime_files": ["CustomConfig/deck/CARD_A.json"],
                    "runtime_surfaces": ["Mulligan.json"],
                    "closure": {"runtime_surfaces": ["Combo.json"]},
                    "evidence_chain": [
                        "invalid",
                        {
                            "runtime_lowering_status": "runtime_lowered",
                            "runtime_files": ["CustomConfig/deck/CARD_C.json"],
                        },
                    ],
                },
                {
                    "first_missing_link": "source",
                    "emitted_runtime_files": ["Ignored.json"],
                },
            ]
        },
        surface_intent={
            "required_surfaces": ["GlobalValues.json"],
            "optional_surfaces": [],
            "rows": [
                {
                    "surface": "GlobalValues.json",
                    "rule_id": "globalvalues_full_key_profile",
                    "intent": "baseline",
                }
            ],
        },
    )

    assert explained == {
        "CARD_A.json",
        "CARD_B.json",
        "CARD_C.json",
        "Combo.json",
        "GlobalValues",
        "GlobalValues.json",
        "Mulligan.json",
        "per-card <CARDID>.json",
    }


def test_config_quality_default_surface_claim_and_handoff_helpers_fail_softly() -> None:
    payload = {
        "default_only_runtime_surfaces": [],
        "records": [
            "invalid",
            {"default_only_runtime_surfaces": "invalid"},
            {"records": [{"default_only_runtime_surfaces": ["Combo"]}]},
        ],
    }
    assert config_quality_checks._default_only_runtime_surface_errors(payload) == [
        "default_only_runtime_surfaces_must_be_list"
    ]
    assert config_quality_checks._has_default_only_runtime_surfaces(payload)
    assert not config_quality_checks._has_default_only_runtime_surfaces(
        {"records": ["invalid", {"default_only_runtime_surfaces": []}]}
    )

    assert not config_quality_checks._claim_can_lower_to_runtime(
        {"trust_ceiling": "report_only"}
    )
    assert config_quality_checks._claim_can_lower_to_runtime(
        {"claim_readiness": "guide_backed"}
    )
    assert not config_quality_checks._claim_can_lower_to_runtime(
        {"claim_readiness": "runtime_blocked"}
    )
    assert config_quality_checks._claim_can_lower_to_runtime(
        {"source_confidence": "high"}
    )
    assert not config_quality_checks._claim_can_lower_to_runtime(
        {"confidence": "low"}
    )
    assert config_quality_checks._claim_role_tokens(
        {
            "roles": [" KEEP ", "", 2],
            "semantic_families": "Burn",
            "mechanic_families": {"Combo"},
        }
    ) == {"keep", "burn", "combo"}

    assert not config_quality_checks._has_explicit_opening_hand_mulligan_intent(
        {"claim": "Do not keep this in your opening hand."}
    )
    assert config_quality_checks._has_explicit_opening_hand_mulligan_intent(
        {"roles": ["mulligan_keep"]}
    )
    assert config_quality_checks._has_explicit_opening_hand_mulligan_intent(
        {"text": "Keep this card in your opening hand."}
    )
    assert not config_quality_checks._has_explicit_opening_hand_mulligan_intent({})

    assert config_quality_checks.semantic_handoff_projection(
        {
            "semantic_handoff_status": "attention",
            "semantic_handoff_reasons": ["two", "one", "two", ""],
        }
    ) == {
        "semantic_handoff_status": "attention",
        "semantic_handoff_reasons": ["one", "two"],
    }
    projected = config_quality_checks.semantic_handoff_projection(
        {
            "checks": {
                "runtime_row_trace_inventory": {
                    "unreported_runtime_rows": [1],
                    "reported_rows_missing_runtime": [2],
                },
                "visionai_semantic_surface": {
                    "attention": ["warning", ""],
                    "effect_only_body_rows": [1],
                },
                "globalvalues": {"missing_overlay_keys": ["One"]},
                "operator_summary": {"present": False},
                "source_evidence": {
                    "source_lanes": ["default_runtime"],
                    "semantic_runtime_rows": 0,
                },
            },
            "problems": [{"check": "config_quality_exception"}, "invalid"],
        }
    )
    assert projected["semantic_handoff_status"] == "insufficient_evidence"
    assert set(projected["semantic_handoff_reasons"]) == {
        "config_quality_exception",
        "effect_only_body_rows",
        "missing_globalvalues_overlay_keys",
        "operator_summary_missing_or_invalid",
        "reported_rows_missing_runtime",
        "semantic_runtime_evidence_missing",
        "unreported_runtime_rows",
        "warning",
    }
    assert config_quality_checks.semantic_handoff_projection(
        {"checks": "invalid", "problems": "invalid"}
    ) == {
        "semantic_handoff_status": "closed",
        "semantic_handoff_reasons": [],
    }


def test_config_quality_frozen_projection_lane_and_operator_helpers_preserve_plain_data() -> None:
    assert config_quality_checks._frozen_mapping_sequence("invalid") == ()
    assert config_quality_checks._frozen_mapping_sequence(
        [{"one": 1}, "invalid"]
    ) == ({"one": 1},)
    assert config_quality_checks._frozen_string_sequence(b"invalid") == ()
    assert config_quality_checks._frozen_string_sequence(
        ["one", "", 2]
    ) == ("one", "2")
    assert config_quality_checks._plain_frozen_value(
        {1: ({"two": 2},)}
    ) == {"1": [{"two": 2}]}
    assert config_quality_checks._plain_frozen_value("value") == "value"

    assert config_quality_checks._globalvalues_handoff_check(
        {"missing_overlay_keys": ["One"]}
    ) == {"present": True, "missing_overlay_keys": ["One"]}
    assert config_quality_checks._collect_source_lanes(
        {
            "source_lane": "deck_matched_public_guide",
            "nested": [
                {"source_lane": "static_semantics"},
                "invalid",
            ],
        }
    ) == {"deck_matched_public_guide", "static_semantics"}
    assert config_quality_checks._collect_source_lanes(7) == set()

    assert config_quality_checks._operator_summary_check(
        {
            "technical_status": "load_safe",
            "semantic_status": "attention",
            "source_status_apply_blocking": True,
            "default_only_runtime_surfaces": "invalid",
            "no_default_only_runtime_status": ["invalid"],
        }
    ) == {
        "present": True,
        "technical_status": "load_safe",
        "semantic_status": "attention",
        "source_status_apply_blocking": True,
        "default_only_runtime_surfaces": [
            "__invalid_default_only_runtime_surfaces__"
        ],
        "no_default_only_runtime_status": "['invalid']",
    }
    assert config_quality_checks._operator_summary_check(
        {"no_default_only_runtime_status": {"status": "clean"}}
    )["no_default_only_runtime_status"] == {"status": "clean"}


def test_config_quality_card_behavior_projection_classifies_semantics_and_ranges() -> None:
    report = config_quality_checks._card_behavior_check(
        {
            "rows": [
                "invalid",
                {"surface": "unknown", "behavior_block": "Block"},
                {
                    "card_id": "A",
                    "surface_family": "CARDID.json",
                    "behavior_block": "BeforePlayCardBonus",
                    "value": "3",
                },
                {
                    "card_id": "B",
                    "runtime_surface": "CARD_123.json",
                    "behavior_block": "OnBoardBonus",
                    "value": "6",
                    "semantic_score": {"reason": "semantic_default"},
                },
                {
                    "card_id": "C",
                    "surface_family": "CARDID.json",
                    "behavior_block": "BeforePlayCardBonus",
                    "value": "13",
                    "semantic_score": {"reason": "source_backed"},
                    "meaningful_runtime_surface": False,
                },
            ]
        }
    )
    assert report["accepted_cardid_runtime_rows"] == 2
    assert len(report["semantic_score_missing_rows"]) == 1
    assert len(report["semantic_default_rows"]) == 1
    assert {row["reason"] for row in report["semantic_score_rows"]} == {
        "semantic_default"
    }
    assert len(report["out_of_range_value_rows"]) == 1
    assert config_quality_checks._is_meaningful_cardid_row(
        {
            "surface_family": "CARDID.json",
            "behavior_block": "Block",
        }
    )
    assert not config_quality_checks._is_meaningful_cardid_row(
        {"surface_family": "CARDID.json", "behavior_block": ""}
    )
    assert config_quality_checks._looks_like_cardid_surface("CARD_123.json")
    assert not config_quality_checks._looks_like_cardid_surface("unknown")
    assert not config_quality_checks._numeric_value_out_of_runtime_range(
        "invalid"
    )
    assert not config_quality_checks._numeric_value_out_of_runtime_range(6)
    assert config_quality_checks._numeric_value_out_of_runtime_range(13)


def test_package_request_frozen_json_normalizes_supported_authority_values() -> None:
    @dataclass(frozen=True)
    class Record:
        value: int

    class Label(Enum):
        VALUE = "value"

    value = {
        "record": Record(1),
        "enum": Label.VALUE,
        "date": date(2026, 8, 1),
        "datetime": datetime(2026, 8, 1, 12, 30),
        "path": PurePath("reports", "result.json"),
        "sequence": (1, 2),
        "set": frozenset({"b", "a"}),
    }
    frozen = package_request.FrozenJsonDocument.from_value(value)

    assert frozen.to_value() == {
        "date": "2026-08-01",
        "datetime": "2026-08-01T12:30:00",
        "enum": "value",
        "path": str(PurePath("reports", "result.json")),
        "record": {"value": 1},
        "sequence": [1, 2],
        "set": ["a", "b"],
    }
    assert package_request.FrozenJsonDocument.from_json_bytes(
        frozen.canonical_json
    ) == frozen

    with pytest.raises(TypeError, match="frozen_json_mapping_key_invalid"):
        package_request._json_value({1: "invalid"})
    with pytest.raises(TypeError, match="frozen_json_value_invalid"):
        package_request._json_value(object())
    with pytest.raises(ValueError, match="frozen_json_not_canonical"):
        package_request.FrozenJsonDocument(canonical_json=b'{"b":1,"a":2}')
    for malformed in (b'{"a":1,"a":2}', b'{"value":NaN}', b"{"):
        with pytest.raises(ValueError):
            package_request.FrozenJsonDocument.from_json_bytes(malformed)


def _open_acquisition_closure() -> dict[str, object]:
    return {
        "deck_fingerprint": "sha256:" + ("a" * 64),
        "attempt_id": "",
        "attempted_at": "",
        "attempted_urls": [],
        "successful_evidence_ids": [],
        "failed_attempts": [],
        "negative_search_documented": False,
        "checked_dossier": False,
        "policy_id": None,
        "status": "open",
        "content_sha256": "sha256:" + ("b" * 64),
    }


def test_package_request_schema_nodes_fail_closed_at_collection_boundaries() -> None:
    assert package_request.AcquisitionClosureInput.from_value(
        _open_acquisition_closure()
    ).to_value()["status"] == "open"
    assert package_request.PlanOverrides.from_value(
        {"combo_plan_report.json": {"combos": []}}
    ).to_value() == {"combo_plan_report.json": {"combos": []}}
    valid_gap = {
        "target_deck_name": "Deck",
        "target_deck_fingerprint": "sha256:" + ("a" * 64),
        "target_deck_code_hash": "sha256:" + ("b" * 64),
        "card_id": "CARD_001",
        "first_missing_source_action": "research",
        "reason": "source_missing",
    }
    assert package_request.MulliganGapInput.from_value([valid_gap]).to_value() == [
        valid_gap
    ]

    for malformed in (
        [],
        {"future.json": {}},
        {"combo_plan_report.json": []},
    ):
        with pytest.raises(ValueError, match="plan_overrides_schema_invalid"):
            package_request.PlanOverrides.from_value(malformed)

    for changes in (
        {"status": "future"},
        {"attempted_urls": "not-a-list"},
        {"attempted_urls": [""]},
        {"successful_evidence_ids": [""]},
        {"failed_attempts": ["invalid"]},
        {"negative_search_documented": 0},
        {"checked_dossier": 0},
        {"policy_id": " padded "},
        {"content_sha256": "invalid"},
    ):
        malformed = {**_open_acquisition_closure(), **changes}
        with pytest.raises(ValueError, match="acquisition_closure_schema_invalid"):
            package_request.AcquisitionClosureInput.from_value(malformed)

    closed = {
        **_open_acquisition_closure(),
        "attempt_id": "attempt-1",
        "attempted_at": "2026-08-01T12:00:00Z",
        "failed_attempts": [
            {
                "source_identity": "source-1",
                "reason_code": "not_found",
                "attempted_at": "2026-08-01T12:00:00Z",
            }
        ],
        "status": "closed_negative_search",
        "negative_search_documented": True,
    }
    assert package_request.AcquisitionClosureInput.from_value(closed).to_value() == closed
    malformed_failure = {**closed, "failed_attempts": [{"reason_code": "missing"}]}
    with pytest.raises(ValueError, match="acquisition_closure_schema_invalid"):
        package_request.AcquisitionClosureInput.from_value(malformed_failure)

    for malformed in ("not-a-list", ["invalid"], [{**valid_gap, "reason": ""}]):
        with pytest.raises(ValueError, match="mulligan_gap_schema_invalid"):
            package_request.MulliganGapInput.from_value(malformed)


def test_package_request_typed_nodes_reject_unfrozen_constructor_values(
    tmp_path: PurePath,
) -> None:
    for node_type, reason in (
        (
            package_request.GeneralPreconfigSnapshot,
            "general_preconfig_document_invalid",
        ),
        (package_request.PlanOverrides, "plan_overrides_document_invalid"),
        (
            package_request.AcquisitionClosureInput,
            "acquisition_closure_document_invalid",
        ),
        (package_request.MulliganGapInput, "mulligan_gap_document_invalid"),
    ):
        with pytest.raises(TypeError, match=reason):
            node_type(document=object())

    with pytest.raises(TypeError, match="preconfig_snapshot_invalid"):
        package_request.PackageResolutionSnapshot(
            general_preconfig=object(),
            strict_build_context=None,
        )
    forged_preconfig = tuple.__new__(
        package_request.GeneralPreconfigSnapshot,
        (package_request.FrozenJsonDocument.from_value({}),),
    )
    with pytest.raises(TypeError, match="strict_build_context_invalid"):
        package_request.PackageResolutionSnapshot(
            general_preconfig=forged_preconfig,
            strict_build_context=object(),
        )
    with pytest.raises(TypeError, match="strict_build_context_invalid"):
        package_request.PackageResolutionSnapshot.from_strict(object(), {})

    not_directory = tmp_path / "plan.json"
    not_directory.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="must be an existing directory"):
        package_request._read_plan_overrides(not_directory)

    plan_dir = tmp_path / "plans"
    plan_dir.mkdir()
    first_name = sorted(package_request._PLAN_OVERRIDE_FILENAMES)[0]
    (plan_dir / first_name).write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="Plan report must be an object"):
        package_request._read_plan_overrides(plan_dir)


def test_package_invocation_rejects_noncanonical_transport_and_mode_values() -> None:
    values: dict[str, object] = {
        "deck_code": "deck-code",
        "runtime_root": "runtime",
        "cards_json": None,
        "claims_json": None,
        "guide_sources_json": None,
        "plan_reports_dir": None,
        "target_config_mode": "preview",
        "include_disposition_diagnostics": False,
    }
    invocation = package_request.PackageInvocation(
        **{**values, "cards_json": PurePath("cards.json")}
    )
    assert invocation.cards_json == "cards.json"

    invalid_cases = (
        ({"deck_code": ""}, "package_invocation_deck_code_invalid"),
        ({"runtime_root": " padded "}, "package_invocation_runtime_root_invalid"),
        ({"claims_json": ""}, "package_invocation_claims_json_invalid"),
        ({"target_config_mode": "apply"}, "package_invocation_target_config_mode_invalid"),
        (
            {"include_disposition_diagnostics": 0},
            "package_invocation_disposition_diagnostics_invalid",
        ),
    )
    for changes, reason in invalid_cases:
        with pytest.raises(ValueError, match=reason):
            package_request.PackageInvocation(**{**values, **changes})


def test_package_domain_authority_constructor_and_policy_validation_fail_closed() -> None:
    rules = b'["rule"]'
    digest = "sha256:" + package_domain.sha256(rules).hexdigest()
    profile = package_domain.PolicyProfile(
        "policy",
        1,
        "2026-08-01",
        digest,
        rules,
    )
    assert profile.policy_id == "policy"

    with pytest.raises(TypeError, match="expected at most"):
        package_domain.PolicyProfile("a", 1, "2026-08-01", digest, rules, "extra")
    with pytest.raises(TypeError, match="multiple values"):
        package_domain.PolicyProfile("a", policy_id="b")
    with pytest.raises(TypeError, match="missing required argument"):
        package_domain.PolicyProfile(policy_id="a")
    with pytest.raises(TypeError, match="unexpected argument"):
        package_domain.PolicyProfile(
            policy_id="a",
            version=1,
            effective_date="2026-08-01",
            content_sha256=digest,
            rules_canonical_json=rules,
            extra=True,
        )

    invalid_cases = (
        ({"policy_id": ""}, "policy_profile_id_invalid"),
        ({"version": True}, "policy_profile_version_invalid"),
        ({"effective_date": "01-08-2026"}, "policy_profile_effective_date_invalid"),
        ({"content_sha256": "invalid"}, "policy_profile_content_sha256_invalid"),
        (
            {
                "rules_canonical_json": b"[]",
                "content_sha256": "sha256:" + package_domain.sha256(b"[]").hexdigest(),
            },
            "policy_profile_rules_invalid",
        ),
    )
    base = {
        "policy_id": "policy",
        "version": 1,
        "effective_date": "2026-08-01",
        "content_sha256": digest,
        "rules_canonical_json": rules,
    }
    for changes, reason in invalid_cases:
        with pytest.raises(ValueError, match=reason):
            package_domain.PolicyProfile(**{**base, **changes})


def test_package_domain_mulligan_models_reject_ambiguous_authority_and_order() -> None:
    rule = package_domain.MulliganRuleModel(
        card_id="CARD_001",
        selector_kind="card",
        selector_canonical_json=b'{"card_id":"CARD_001"}',
        action="hold",
        condition_canonical_json=b"{}",
        reason="source_backed",
        confidence="high",
        source_claim_ids=("claim-1",),
    )
    suppression = package_domain.MulliganSuppressionModel(
        card_id="CARD_002",
        action="none",
        reason_code="unsupported",
        source_claim_ids=("claim-2",),
        source_type=None,
        source_url=None,
    )
    delegated = package_domain.BotDelegationModel(
        card_id="CARD_003",
        evidence_lane="E",
        policy_id="BOT_NATIVE_PRE_RUN",
        reason_code="bot_native",
    )
    plan = package_domain.MulliganPlanModel(
        deck_name="Deck",
        rules=(rule,),
        suppressed=(suppression,),
        bot_delegated=(delegated,),
        merged_duplicate_rule_count=0,
    )
    assert plan.to_report()["quality"]["status"] == "rich"

    rule_values = {
        "card_id": "CARD_001",
        "selector_kind": "card",
        "selector_canonical_json": b'{"card_id":"CARD_001"}',
        "action": "hold",
        "condition_canonical_json": b"{}",
        "reason": "source_backed",
        "confidence": "high",
        "source_claim_ids": ("claim-1",),
    }
    for changes, reason in (
        ({"card_id": ""}, "mulligan_rule_invalid"),
        ({"claim_id": " padded "}, "mulligan_rule_claim_id_invalid"),
        ({"source_claim_ids": ()}, "mulligan_rule_authorization_missing"),
    ):
        with pytest.raises(ValueError, match=reason):
            package_domain.MulliganRuleModel(**{**rule_values, **changes})

    with pytest.raises(ValueError, match="mulligan_suppression_source_type_invalid"):
        package_domain.MulliganSuppressionModel(
            card_id="CARD_002",
            action="none",
            reason_code="unsupported",
            source_claim_ids=("claim-2",),
            source_type="",
            source_url=None,
        )
    with pytest.raises(ValueError, match="bot_delegation_invalid"):
        package_domain.BotDelegationModel(
            card_id="CARD_003",
            evidence_lane="D",
            policy_id="BOT_NATIVE_PRE_RUN",
            reason_code="bot_native",
        )
    for changes, reason in (
        ({"rules": (rule, rule)}, "mulligan_duplicate_rule_identity"),
        ({"bot_delegated": (delegated, delegated)}, "mulligan_delegation_order_unstable"),
        ({"merged_duplicate_rule_count": -1}, "mulligan_merged_duplicate_count_invalid"),
    ):
        with pytest.raises(ValueError, match=reason):
            package_domain.MulliganPlanModel(
                deck_name="Deck",
                rules=changes.get("rules", (rule,)),
                suppressed=(suppression,),
                bot_delegated=changes.get("bot_delegated", (delegated,)),
                merged_duplicate_rule_count=changes.get(
                    "merged_duplicate_rule_count", 0
                ),
            )


def test_package_domain_remaining_typed_model_guards_reject_invalid_authority() -> (
    None
):
    with pytest.raises(ValueError, match="globalvalue_overlay_authority_missing"):
        package_domain.GlobalValueDecision(
            deck_fingerprint="fingerprint",
            key="Key",
            kind=package_domain.GlobalValueDecisionKind.AUTHORIZED_OVERLAY,
            baseline_canonical_json=b'"0"',
            emitted_canonical_json=b'"1"',
            authority_id="authority",
            claim_ids=(),
            reason="reason",
        )
    with pytest.raises(ValueError, match="globalvalues_deck_fingerprint_invalid"):
        package_domain.GlobalValuesDecisionLedger(
            deck_fingerprint="",
            baseline_sha256="sha256:" + ("0" * 64),
            decisions=(),
            content_sha256="sha256:" + ("0" * 64),
        )
    with pytest.raises(ValueError, match="mulligan_suppression_invalid"):
        package_domain.MulliganSuppressionModel(
            card_id="",
            action="hold",
            reason_code="reason",
            source_claim_ids=(),
        )

    combo_values: dict[str, object] = {
        "rule_id": "combo",
        "cards": ("A", "B"),
        "timing": package_domain.ComboTiming.SAME_TURN,
        "values": ("1", "2"),
        "condition": "*",
        "source_claim_ids": ("claim",),
        "confidence": "high",
        "source_refs": ("source",),
        "claim_id": None,
    }
    for changes, reason in (
        ({"rule_id": ""}, "combo_rule_id_invalid"),
        ({"timing": object()}, "combo_timing_invalid"),
        ({"cards": ("A",), "values": ("1",)}, "combo_sequence_too_short"),
        ({"claim_id": ""}, "combo_claim_id_invalid"),
    ):
        with pytest.raises(ValueError, match=reason):
            package_domain.ComboDecisionModel(**{**combo_values, **changes})

    with pytest.raises(TypeError, match="combo_decision_invalid"):
        package_domain.ComboPlanModel(decisions=(object(),), suppressions=())
    with pytest.raises(TypeError, match="combo_suppression_invalid"):
        package_domain.ComboPlanModel(decisions=(), suppressions=(object(),))


def test_strict_validation_runtime_ledger_reports_each_physical_contract_error() -> None:
    ledger = {"surface_ledger_sha256": "sha256:ledger"}
    rederived = {
        "surface_ledger_sha256": "sha256:rederived",
        "physical_errors": ["bad-file", "bad-file"],
        "unexpected_runtime_emissions": [
            {"card_id": "CARD_001", "reason": "not_declared"},
            "invalid",
        ],
        "linked_runtime_owner_collisions": [
            {"runtime_card_id": "HERO_POWER"},
            "invalid",
        ],
    }

    assert strict_package_validation._runtime_surface_ledger_errors(
        ledger,
        rederived,
    ) == sorted(
        {
            "runtime_surface_ledger_sha256_mismatch",
            "runtime_surface_ledger_content_mismatch",
            "runtime_surface_ledger_physical_error:bad-file",
            "runtime_surface_ledger_unexpected_emission:CARD_001:not_declared",
            "runtime_surface_ledger_unexpected_emission:invalid",
            "runtime_surface_ledger_owner_collision:HERO_POWER",
            "runtime_surface_ledger_owner_collision:invalid",
        }
    )
    canonical = {"surface_ledger_sha256": "sha256:same"}
    assert strict_package_validation._runtime_surface_ledger_errors(
        canonical,
        canonical,
    ) == []


def test_strict_validation_linked_owner_projection_rejects_unclassified_rows() -> None:
    source, semantic, link_kind, runtime = (
        strict_package_validation.AUTHORIZED_HERO_POWER_OWNER
    )
    block = "BeforeUseHeroPowerBonus"
    behavior = {
        "rows": [
            {"card_id": "SELF", "link_kind": "self"},
            {
                "source_card_id": source,
                "runtime_card_id": runtime,
                "link_kind": link_kind,
                "behavior_block": block,
                "meaningful_runtime_surface": False,
            },
            {
                "source_card_id": source,
                "runtime_card_id": runtime,
                "link_kind": link_kind,
                "behavior_block": block,
                "meaningful_runtime_surface": True,
            },
        ]
    }
    relations, errors = strict_package_validation._linked_runtime_relations(behavior)

    assert relations == [
        {
            "source_card_id": source,
            "runtime_card_id": runtime,
            "link_kind": link_kind,
            "semantic_surface": semantic,
            "behavior_block": block,
        }
    ]
    assert len(errors) == 1
    assert strict_package_validation._has_curated_linked_runtime_owner_relation(
        relations
    )
    assert not strict_package_validation._has_curated_linked_runtime_owner_relation([])
    with pytest.raises(
        ValueError,
        match=strict_package_validation.LINKED_RUNTIME_OWNER_EVIDENCE_INVALID,
    ):
        strict_package_validation._validated_behavior_plan_rows({"rows": ["invalid"]})


def test_strict_validation_memory_view_distinguishes_missing_multiple_and_invalid() -> None:
    missing = strict_package_validation._validate_config_package_view(
        _quality_package_root({}).package,
        globalvalues_baseline={},
        globalvalues_profile=None,
        globalvalues_authority_matrix=None,
    )
    assert "no deck config directories found" in missing["errors"][0]

    multiple = strict_package_validation._validate_config_package_view(
        _quality_package_root(
            {
                "CustomConfig/A/Unsupported.json": {},
                "CustomConfig/B/Mulligan.json": [],
            }
        ).package,
        globalvalues_baseline={},
        globalvalues_profile=None,
        globalvalues_authority_matrix=None,
    )
    assert any("expected exactly one deck config directory" in row for row in multiple["errors"])
    assert any("unsupported VisionAI surface" in row for row in multiple["errors"])
    assert any("top-level JSON value must be an object" in row for row in multiple["errors"])
    assert any("missing required GlobalValues profile" in row for row in multiple["errors"])

    package = _quality_package_root(
        {
            "reports/object.json": {},
            "reports/list.json": [],
        }
    ).package
    assert strict_package_validation._required_view_mapping(
        package,
        "reports/object.json",
        "Object",
    ) == {}
    assert strict_package_validation._optional_view_mapping(
        package,
        "reports/missing.json",
        "Missing",
    ) is None
    with pytest.raises(ValueError, match="Missing Object report"):
        strict_package_validation._required_view_mapping(
            package,
            "reports/missing.json",
            "Object",
        )
    for function in (
        strict_package_validation._required_view_mapping,
        strict_package_validation._optional_view_mapping,
    ):
        with pytest.raises(ValueError, match="must be an object"):
            function(package, "reports/list.json", "List")


def test_strict_validation_pre_run_view_distinguishes_legacy_and_current_markers() -> (
    None
):
    empty = _quality_package_root({}).package
    assert strict_package_validation._validate_pre_run_contract_reports_view(
        empty,
        legacy_contract_version=0,
    ) == []
    assert strict_package_validation._validate_pre_run_contract_reports_view(
        empty,
        legacy_contract_version=None,
    ) == [
        "pre_run_contract_validation_failed:pre_run_current_reports_missing"
    ]

    marked = _quality_package_root(
        {"reports/input_manifest.json": {"pre_run_contract_schema_version": 1}}
    ).package
    assert strict_package_validation._validate_pre_run_contract_reports_view(
        marked,
        legacy_contract_version=0,
    ) == [
        "pre_run_contract_validation_failed:pre_run_current_reports_missing"
    ]

    malformed_manifest = _quality_package_root(
        {"reports/input_manifest.json": []}
    ).package
    assert strict_package_validation._validate_pre_run_contract_reports_view(
        malformed_manifest,
        legacy_contract_version=0,
    ) == []


def test_strict_validation_linked_runtime_view_covers_missing_and_malformed_owners(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_card_id = strict_package_validation.AUTHORIZED_HERO_POWER_OWNER[3]
    curated_path = f"CustomConfig/Deck/{runtime_card_id}.json"

    curated_without_plan = _quality_package_root({curated_path: {}}).package
    assert strict_package_validation._validate_linked_runtime_entities_view(
        curated_without_plan
    ) == [strict_package_validation.LINKED_RUNTIME_OWNER_EVIDENCE_MISSING]

    invalid_plan = _quality_package_root(
        {"reports/card_behavior_plan_report.json": []}
    ).package
    assert strict_package_validation._validate_linked_runtime_entities_view(
        invalid_plan
    ) == [strict_package_validation.LINKED_RUNTIME_OWNER_EVIDENCE_INVALID]

    source, _semantic, link_kind, runtime = (
        strict_package_validation.AUTHORIZED_HERO_POWER_OWNER
    )
    plan = {
        "rows": [
            {
                "source_card_id": source,
                "runtime_card_id": runtime,
                "link_kind": link_kind,
                "behavior_block": "BeforeUseHeroPowerBonus",
                "meaningful_runtime_surface": True,
            }
        ]
    }
    missing_file = _quality_package_root(
        {"reports/card_behavior_plan_report.json": plan}
    ).package
    assert strict_package_validation._validate_linked_runtime_entities_view(
        missing_file
    ) == [f"linked runtime entity missing required owner file: {runtime}.json"]

    non_object_owner = _quality_package_root(
        {
            "reports/card_behavior_plan_report.json": plan,
            curated_path: [],
        }
    ).package
    assert strict_package_validation._validate_linked_runtime_entities_view(
        non_object_owner
    ) == []

    wrong_owner = _quality_package_root(
        {
            "reports/card_behavior_plan_report.json": plan,
            curated_path: {"GameCardId": "WRONG"},
        }
    ).package
    assert "filename/GameCardId mismatch" in (
        strict_package_validation._validate_linked_runtime_entities_view(
            wrong_owner
        )[0]
    )

    plan_only = _quality_package_root(
        {"reports/card_behavior_plan_report.json": {}}
    ).package
    monkeypatch.setattr(
        strict_package_validation,
        "_linked_runtime_relations",
        lambda _plan: (_ for _ in ()).throw(
            ValueError(strict_package_validation.LINKED_RUNTIME_OWNER_EVIDENCE_INVALID)
        ),
    )
    assert strict_package_validation._validate_linked_runtime_entities_view(
        plan_only
    ) == [strict_package_validation.LINKED_RUNTIME_OWNER_EVIDENCE_INVALID]

    monkeypatch.setattr(
        strict_package_validation,
        "_linked_runtime_relations",
        lambda _plan: (_ for _ in ()).throw(ValueError("unexpected")),
    )
    with pytest.raises(ValueError, match="unexpected"):
        strict_package_validation._validate_linked_runtime_entities_view(plan_only)


def test_strict_validation_current_contract_requires_globalvalues_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = _quality_package_root(
        {"reports/globalvalues_baseline.json": {}}
    ).package
    monkeypatch.setattr(
        strict_package_validation,
        "_validate_config_package_view",
        lambda *_args, **_kwargs: {"status": "ok", "errors": []},
    )
    monkeypatch.setattr(
        strict_package_validation,
        "_validate_linked_runtime_entities_view",
        lambda _package: [],
    )
    monkeypatch.setattr(
        strict_package_validation,
        "_validate_runtime_surface_ledger_view",
        lambda _package: [],
    )
    monkeypatch.setattr(
        strict_package_validation,
        "_validate_pre_run_contract_reports_view",
        lambda *_args, **_kwargs: [],
    )

    report = strict_package_validation.validate_complete_package_from_view(package)

    assert report["status"] == "failed"
    assert "requires authority matrix" in report["errors"][0]


def test_strict_validation_filesystem_pre_run_marker_and_ledger_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: PurePath,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "input_manifest.json").write_text("{}", encoding="utf-8")
    assert strict_package_validation._validate_pre_run_contract_reports(
        tmp_path, legacy_contract_version=0
    ) == []
    (reports / "input_manifest.json").write_text("[]", encoding="utf-8")
    assert strict_package_validation._validate_pre_run_contract_reports(
        tmp_path, legacy_contract_version=0
    ) == []

    ledger_path = reports / "runtime_surface_ledger.json"
    ledger_path.write_text("[]", encoding="utf-8")
    assert strict_package_validation._validate_runtime_surface_ledger(tmp_path) == [
        "runtime_surface_ledger_invalid"
    ]

    ledger_path.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")
    monkeypatch.setattr(
        strict_package_validation,
        "rederive_runtime_surface_ledger_from_package",
        lambda _package: {
            "surface_ledger_sha256": "different",
            "physical_errors": ["physical"],
            "unexpected_runtime_emissions": [
                {"card_id": "CARD_001", "reason": "unexpected"},
                "invalid",
            ],
            "linked_runtime_owner_collisions": [
                {"runtime_card_id": "CARD_002"},
                "invalid",
            ],
        },
    )
    errors = strict_package_validation._validate_runtime_surface_ledger(tmp_path)
    assert "runtime_surface_ledger_unexpected_emission:CARD_001:unexpected" in errors
    assert "runtime_surface_ledger_unexpected_emission:invalid" in errors
    assert "runtime_surface_ledger_owner_collision:CARD_002" in errors
    assert "runtime_surface_ledger_owner_collision:invalid" in errors

    behavior = reports / "card_behavior_plan_report.json"
    behavior.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        strict_package_validation,
        "_linked_runtime_relations",
        lambda _plan: (_ for _ in ()).throw(ValueError("unexpected")),
    )
    with pytest.raises(ValueError, match="unexpected"):
        strict_package_validation._validate_linked_runtime_entities(tmp_path)

    monkeypatch.setattr(
        strict_package_validation,
        "_linked_runtime_relations",
        lambda _plan: (
            [
                {
                    "runtime_card_id": "CARD_001",
                    "source_card_id": "SOURCE",
                    "link_kind": "transform",
                }
            ],
            [],
        ),
    )
    missing_errors = strict_package_validation._validate_linked_runtime_entities(
        tmp_path
    )
    assert "CARD_001.json" in missing_errors[0]

    deck_dir = tmp_path / "CustomConfig" / "Deck"
    deck_dir.mkdir(parents=True)
    (deck_dir / "CARD_001.json").write_text("[]", encoding="utf-8")
    assert strict_package_validation._validate_linked_runtime_entities(tmp_path) == []


def test_strict_validation_view_ledger_and_curated_owner_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_ledger = _quality_package_root(
        {"reports/runtime_surface_ledger.json": []}
    ).package
    assert strict_package_validation._validate_runtime_surface_ledger_view(
        invalid_ledger
    ) == ["runtime_surface_ledger_invalid"]
    missing_ledger = _quality_package_root({}).package
    assert strict_package_validation._validate_runtime_surface_ledger_view(
        missing_ledger
    ) == ["runtime_surface_ledger_missing"]
    schema_ledger = _quality_package_root(
        {"reports/runtime_surface_ledger.json": {"schema_version": 1}}
    ).package
    assert strict_package_validation._validate_runtime_surface_ledger_view(
        schema_ledger
    ) == ["runtime_surface_ledger_schema_invalid"]

    no_behavior = _quality_package_root({}).package
    monkeypatch.setattr(
        strict_package_validation,
        "_has_curated_linked_runtime_owner_file_view",
        lambda _package: True,
    )
    assert strict_package_validation._validate_linked_runtime_entities_view(
        no_behavior
    ) == [strict_package_validation.LINKED_RUNTIME_OWNER_EVIDENCE_MISSING]

    behavior = _quality_package_root(
        {"reports/card_behavior_plan_report.json": {"rows": []}}
    ).package
    monkeypatch.setattr(
        strict_package_validation,
        "_linked_runtime_relations",
        lambda _plan: ([], []),
    )
    assert strict_package_validation._validate_linked_runtime_entities_view(
        behavior
    ) == [strict_package_validation.LINKED_RUNTIME_OWNER_EVIDENCE_MISSING]
    monkeypatch.setattr(
        strict_package_validation,
        "_has_curated_linked_runtime_owner_file_view",
        lambda _package: False,
    )
    assert strict_package_validation._validate_linked_runtime_entities_view(
        no_behavior
    ) == []


class _ResourceStore:
    def __init__(self, value: object) -> None:
        self.value = value

    def read_by_sha256(self, content_sha256: str) -> object:
        del content_sha256
        return self.value


def test_build_context_resource_boundary_requires_immutable_canonical_bytes() -> None:
    canonical = b'{"value":1}'
    digest = build_context._raw_sha256(canonical)
    assert build_context._resource(
        _ResourceStore(canonical),
        digest,
        error="fixture",
    ) == (canonical, {"value": 1})

    with pytest.raises(ValueError, match="fixture_resource_mutable"):
        build_context._resource(_ResourceStore(bytearray(canonical)), digest, error="fixture")
    with pytest.raises(ValueError, match="fixture_resource_sha256_mismatch"):
        build_context._resource(_ResourceStore(canonical), "sha256:" + ("0" * 64), error="fixture")
    with pytest.raises(ValueError, match="resolved_build_fixture_resource_mutable"):
        build_context._resolved_context_resource_bytes(
            "not-bytes",  # type: ignore[arg-type]
            expected_sha256=digest,
            label="fixture",
        )
    with pytest.raises(ValueError, match="resolved_build_fixture_resource_sha256_mismatch"):
        build_context._resolved_context_resource_bytes(
            canonical,
            expected_sha256="sha256:" + ("0" * 64),
            label="fixture",
        )
    noncanonical = b'{"value": 1}'
    with pytest.raises(ValueError, match="resolved_build_fixture_json_noncanonical"):
        build_context._resolved_context_resource_bytes(
            noncanonical,
            expected_sha256=build_context._raw_sha256(noncanonical),
            label="fixture",
        )


def test_build_context_deck_and_snapshot_validators_report_structural_failures() -> None:
    inputs = SimpleNamespace(
        deck_name="Deck",
        deck_fingerprint="fingerprint",
        deck_code_sha256="sha256:code",
        card_snapshot_id="snapshot",
        card_snapshot_sha256="sha256:snapshot",
    )
    with pytest.raises(ValueError, match="deck_cards_fields_invalid"):
        build_context._validate_deck_resource(
            {},
            inputs=inputs,
            snapshot_card_ids=frozenset(),
        )
    deck = {key: None for key in build_context._DECK_RESOURCE_FIELDS}
    with pytest.raises(ValueError, match="deck_cards_identity_mismatch"):
        build_context._validate_deck_resource(
            deck,
            inputs=inputs,
            snapshot_card_ids=frozenset(),
        )
    deck.update(
        {
            "schema_version": 1,
            "inventory_content_sha256": build_context._APPROVED_SEMANTIC_INVENTORY_SHA256,
            "deck_name": "Deck",
            "deck_fingerprint": "fingerprint",
            "deck_code_sha256": "sha256:code",
            "main_cards": {},
            "sideboard_modules": [],
            "claims": [],
            "globalvalues_decisions": [],
        }
    )
    with pytest.raises(ValueError, match="deck_cards_projection_invalid"):
        build_context._validate_deck_resource(
            deck,
            inputs=inputs,
            snapshot_card_ids=frozenset(),
        )
    deck["main_cards"] = ["invalid"]
    with pytest.raises(ValueError, match="deck_cards_main_card_invalid"):
        build_context._validate_deck_resource(
            deck,
            inputs=inputs,
            snapshot_card_ids=frozenset(),
        )

    with pytest.raises(ValueError, match="card_snapshot_invalid"):
        build_context._validate_card_snapshot({}, inputs=inputs)
    snapshot = {"schema_version": 1, "metadata": [], "cards": []}
    with pytest.raises(ValueError, match="card_snapshot_unpinned"):
        build_context._validate_card_snapshot(snapshot, inputs=inputs)
    snapshot["metadata"] = {}
    with pytest.raises(ValueError, match="card_snapshot_identity_mismatch"):
        build_context._validate_card_snapshot(snapshot, inputs=inputs)


def test_build_context_policy_and_evidence_contract_reject_unbound_authority() -> None:
    inputs = SimpleNamespace(
        policy_profile_id=build_context._APPROVED_POLICY_ID,
        policy_profile_sha256=build_context._APPROVED_POLICY_SHA256,
        deck_fingerprint="fingerprint",
    )
    with pytest.raises(ValueError, match="policy_profile_fields_invalid"):
        build_context._validate_policy({}, inputs=inputs)
    policy = {key: None for key in build_context._POLICY_FIELDS}
    with pytest.raises(ValueError, match="policy_profile_identity_invalid"):
        build_context._validate_policy(policy, inputs=inputs)
    policy.update(
        {
            "policy_id": build_context._APPROVED_POLICY_ID,
            "content_sha256": build_context._APPROVED_POLICY_SHA256,
            "version": 1,
            "rules": ["invalid"],
        }
    )
    with pytest.raises(ValueError, match="policy_profile_rule_invalid"):
        build_context._validate_policy(policy, inputs=inputs)

    profile = SimpleNamespace(
        policy_id="policy",
        version=1,
        effective_date="2026-08-01",
        content_sha256="sha256:" + ("a" * 64),
    )
    with pytest.raises(ValueError, match="evidence_contract_identity_invalid"):
        build_context._validate_evidence_contract(
            {},
            inputs=inputs,
            profile=profile,
            expected_claim_ids=(),
        )
    contract = {
        key: None for key in build_context._EVIDENCE_CONTRACT_FIELDS
    }
    contract.update(
        {
            "schema_version": 1,
            "deck_fingerprint": "fingerprint",
            "authorities": [],
            "content_sha256": "sha256:" + ("0" * 64),
        }
    )
    with pytest.raises(ValueError, match="evidence_contract_hash_stale"):
        build_context._validate_evidence_contract(
            contract,
            inputs=inputs,
            profile=profile,
            expected_claim_ids=(),
        )
    contract["content_sha256"] = build_context._raw_sha256(
        build_context._canonical_json(
            {key: value for key, value in contract.items() if key != "content_sha256"}
        )
    )
    contract["authorities"] = {}
    contract["content_sha256"] = build_context._raw_sha256(
        build_context._canonical_json(
            {key: value for key, value in contract.items() if key != "content_sha256"}
        )
    )
    with pytest.raises(ValueError, match="evidence_contract_authorities_invalid"):
        build_context._validate_evidence_contract(
            contract,
            inputs=inputs,
            profile=profile,
            expected_claim_ids=(),
        )
    contract["authorities"] = ["invalid"]
    contract["content_sha256"] = build_context._raw_sha256(
        build_context._canonical_json(
            {key: value for key, value in contract.items() if key != "content_sha256"}
        )
    )
    with pytest.raises(ValueError, match="evidence_contract_raw_guide_forbidden"):
        build_context._validate_evidence_contract(
            contract,
            inputs=inputs,
            profile=profile,
            expected_claim_ids=(),
        )


def test_build_context_source_and_baseline_helpers_fail_closed() -> None:
    inputs = SimpleNamespace(deck_name="Deck", deck_fingerprint="fingerprint")
    profile = SimpleNamespace(
        policy_id="policy",
        version=1,
        effective_date="2026-08-01",
        content_sha256="sha256:" + ("a" * 64),
    )
    with pytest.raises(ValueError, match="source_bundle_resource_set_invalid"):
        build_context._validate_source_resources(
            (),
            inputs=inputs,
            profile=profile,
            expected_domain_sha256s=(),
        )
    with pytest.raises(ValueError, match="source_bundle_fields_invalid"):
        build_context._validate_source_resources(
            ({}, {}),
            inputs=inputs,
            profile=profile,
            expected_domain_sha256s=("a", "b"),
        )

    assert build_context._rows_are_canonical([{"a": 1}, {"b": 2}])
    assert not build_context._rows_are_canonical([{"b": 2}, {"a": 1}])
    assert build_context._valid_date("2026-08-01")
    assert not build_context._valid_date(20260801)
    assert not build_context._valid_date("01-08-2026")

    with pytest.raises(ValueError, match="globalvalues_baseline_substitution"):
        build_context._validate_globalvalues_baseline(
            {},
            resource_sha256="invalid",
            expected_keys=[],
        )
    baseline = {key: {} for key in build_context._GLOBALVALUES_KEYS}
    baseline["GameCardId"] = "wrong"
    baseline["ConfigComment"] = "comment"
    with pytest.raises(ValueError, match="globalvalues_baseline_gamecardid_invalid"):
        build_context._validate_globalvalues_baseline(
            baseline,
            resource_sha256=build_context._APPROVED_GLOBALVALUES_BASELINE_RESOURCE_SHA256,
            expected_keys=list(build_context._GLOBALVALUES_KEYS),
        )
    baseline["GameCardId"] = "GlobalValues"
    baseline["ConfigComment"] = 1
    with pytest.raises(ValueError, match="globalvalues_baseline_configcomment_invalid"):
        build_context._validate_globalvalues_baseline(
            baseline,
            resource_sha256=build_context._APPROVED_GLOBALVALUES_BASELINE_RESOURCE_SHA256,
            expected_keys=list(build_context._GLOBALVALUES_KEYS),
        )
    baseline["ConfigComment"] = "comment"
    with pytest.raises(ValueError, match="globalvalues_baseline_value_invalid"):
        build_context._validate_globalvalues_baseline(
            baseline,
            resource_sha256=build_context._APPROVED_GLOBALVALUES_BASELINE_RESOURCE_SHA256,
            expected_keys=list(build_context._GLOBALVALUES_KEYS),
        )

    with pytest.raises(ValueError, match="general_preconfig_resource_schema_invalid"):
        build_context._validate_general_preconfig(b"{}", {})


def test_build_context_deck_projection_rejects_each_nested_identity_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fingerprint = "fingerprint"
    inputs = SimpleNamespace(
        deck_name="Deck",
        deck_fingerprint=fingerprint,
        deck_code_sha256="sha256:code",
    )
    main_cards = [
        {
            "card_id": f"CARD_{index:03d}",
            "composite_card_key": f"{fingerprint}:main_deck:CARD_{index:03d}",
            "count": 2,
        }
        for index in range(15)
    ]
    snapshot_ids = frozenset(row["card_id"] for row in main_cards)
    base = {
        "schema_version": 1,
        "inventory_content_sha256": build_context._APPROVED_SEMANTIC_INVENTORY_SHA256,
        "deck_name": "Deck",
        "deck_fingerprint": fingerprint,
        "deck_code_sha256": "sha256:code",
        "main_cards": main_cards,
        "sideboard_modules": [],
        "claims": [{"claim_id": "claim_123456789abc", "claim_key": f"{fingerprint}:claim_123456789abc"}],
        "globalvalues_decisions": sorted(build_context._GLOBALVALUES_KEYS),
    }
    monkeypatch.setattr(
        build_context, "stable_deck_fingerprint", lambda _rows: fingerprint
    )

    invalid_main = json.loads(json.dumps(base))
    invalid_main["main_cards"][0]["count"] = 0
    with pytest.raises(ValueError, match="deck_cards_main_card_invalid"):
        build_context._validate_deck_resource(
            invalid_main, inputs=inputs, snapshot_card_ids=snapshot_ids
        )

    with pytest.raises(ValueError, match="deck_cards_snapshot_card_missing"):
        build_context._validate_deck_resource(
            base, inputs=inputs, snapshot_card_ids=frozenset()
        )

    invalid_sideboard = {**base, "sideboard_modules": ["invalid"]}
    with pytest.raises(ValueError, match="deck_cards_sideboard_invalid"):
        build_context._validate_deck_resource(
            invalid_sideboard, inputs=inputs, snapshot_card_ids=snapshot_ids
        )

    for claims in (
        ["invalid"],
        [{"claim_id": "invalid", "claim_key": "invalid"}],
        [],
    ):
        with pytest.raises(ValueError, match="deck_cards_claim_invalid"):
            build_context._validate_deck_resource(
                {**base, "claims": claims},
                inputs=inputs,
                snapshot_card_ids=snapshot_ids,
            )

    with pytest.raises(ValueError, match="globalvalues_decisions_invalid"):
        build_context._validate_deck_resource(
            {**base, "globalvalues_decisions": []},
            inputs=inputs,
            snapshot_card_ids=snapshot_ids,
        )
    assert build_context._validate_deck_resource(
        base, inputs=inputs, snapshot_card_ids=snapshot_ids
    ) == ("claim_123456789abc",)


def test_build_context_acquisition_closure_rejects_container_and_failure_rows() -> None:
    inputs = SimpleNamespace(deck_fingerprint="fingerprint")
    rules = b'[{"id":"rule"}]'
    profile = package_domain.PolicyProfile(
        policy_id="policy",
        version=1,
        effective_date="2026-08-01",
        content_sha256="sha256:"
        + __import__("hashlib").sha256(rules).hexdigest(),
        rules_canonical_json=rules,
    )
    with pytest.raises(ValueError, match="source_bundle_acquisition_invalid"):
        build_context._typed_acquisition_closure(
            {}, inputs=inputs, profile=profile
        )

    document = {
        "deck_fingerprint": "fingerprint",
        "attempt_id": "attempt",
        "attempted_at": "2026-08-01",
        "attempted_urls": [],
        "failed_attempts": ["invalid"],
        "policy_id": "policy",
        "status": "open",
        "successful_evidence_ids": [],
        "checked_dossier": False,
        "negative_search_documented": False,
        "content_sha256": "sha256:" + ("a" * 64),
    }
    with pytest.raises(ValueError, match="source_bundle_acquisition_invalid"):
        build_context._typed_acquisition_closure(
            document, inputs=inputs, profile=profile
        )

    document["failed_attempts"] = [
        {
            "source_identity": "https://example.invalid",
            "reason_code": "unavailable",
            "attempted_at": "2026-08-01",
        }
    ]
    with pytest.raises(ValueError, match="source_bundle_acquisition_hash_stale"):
        build_context._typed_acquisition_closure(
            document, inputs=inputs, profile=profile
        )


def test_configure_workflow_small_runtime_and_exception_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(TypeError, match="configure_request_required"):
        configure_workflow.execute_configure(object())  # type: ignore[arg-type]
    assert configure_workflow._runtime_apply_status({"receipt": "invalid"}) is None
    summary: dict[str, object] = {
        "acceptance_summary": {"status": "ready"},
        "config_proof_summary": "invalid",
    }
    configure_workflow._project_transient_apply_state(summary, apply_status=7)
    assert summary["acceptance_summary"] == {
        "status": "ready",
        "apply_requested": True,
        "apply_status": 7,
    }
    payload, status = configure_workflow._finish_stage_exception_for_args(
        SimpleNamespace(out=None), "stage", ValueError("failure")
    )
    assert status == 1
    assert payload["stage"] == "stage"

    monkeypatch.setattr(
        configure_workflow,
        "_finish",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("blocked")),
    )
    payload, status = configure_workflow._finish_stage_exception_for_args(
        SimpleNamespace(out="output"), "stage", ValueError("failure")
    )
    assert status == 1
    assert payload["stage"] == "stage"


def test_config_quality_remaining_projection_helpers_preserve_contract_edges() -> None:
    assert config_quality_checks._has_default_only_runtime_surfaces(
        {"default_only_runtime_surfaces": ["Combo"]}
    )
    handoff = config_quality_checks.semantic_handoff_projection(
        {
            "checks": {
                "runtime_row_trace_inventory": {
                    "unreported_runtime_rows": ["row"],
                    "reported_rows_missing_runtime": ["row"],
                },
                "visionai_semantic_surface": {
                    "attention": "invalid",
                    "effect_only_body_rows": ["row"],
                    "semantic_default_runtime_rows": ["row"],
                },
                "globalvalues": {"missing_overlay_keys": ["Coin"]},
                "operator_summary": {"present": False},
            },
            "problems": [{"check": "config_quality_exception"}],
        }
    )
    assert handoff["semantic_handoff_status"] == "insufficient_evidence"
    assert set(handoff["semantic_handoff_reasons"]) >= {
        "unreported_runtime_rows",
        "reported_rows_missing_runtime",
        "effect_only_body_rows",
        "semantic_default_runtime_rows",
        "missing_globalvalues_overlay_keys",
        "operator_summary_missing_or_invalid",
        "config_quality_exception",
    }

    assert config_quality_checks._disposition_card_id(
        {"official_semantics": {"GameCardId": "CARD_001"}}
    ) == "CARD_001"
    assert config_quality_checks._disposition_card_id(
        {"physical_owner": "CARD_002"}
    ) == "CARD_002"
    assert config_quality_checks._disposition_card_id({}) == ""
    assert config_quality_checks._card_behavior_check({"rows": {}})[
        "accepted_cardid_runtime_rows"
    ] == 0
    assert config_quality_checks._meaningful_cardid_rows({"rows": {}}) == []
    blank_reason = config_quality_checks._card_behavior_check(
        {
            "rows": [
                {
                    "card_id": "CARD_001",
                    "surface_family": "CARDID.json",
                    "behavior_block": "OnBoardBonus",
                    "semantic_score": {"reason": ""},
                }
            ]
        }
    )
    assert blank_reason["semantic_score_rows"] == []


def test_config_quality_trace_helpers_bind_only_emitted_card_claim_pairs() -> None:
    explainability = {
        "claim_rows": [
            {"builder_or_router_decision": "emitted", "emitted_runtime_files": ["CARD_001.json"]},
            {
                "builder_or_router_decision": "emitted",
                "claim_id": "claim-1",
                "emitted_runtime_files": ["CARD_001.json"],
            },
        ],
        "card_rows": [
            {
                "card_id": "CARD_002",
                "source_lane": "deck_matched_public_guide",
                "emitted_runtime_files": ["CARD_003.json"],
                "evidence_chain": [
                    {"runtime_files": ["CARD_002.json"]},
                    {"claim_id": "claim-2", "runtime_files": ["CARD_002.json"]},
                ],
            }
        ],
    }
    assert config_quality_checks._traced_card_ids(explainability) == {
        "CARD_001",
        "CARD_002",
        "CARD_003",
    }
    assert config_quality_checks._traced_claim_ids_by_card(explainability) == {
        "CARD_001": {"claim-1"},
        "CARD_002": {"claim-2"},
    }
    assert config_quality_checks._runtime_row_claim_ids(
        {"claim_id": "claim-1", "source_claim_ids": ["", " claim-2 "]}
    ) == {"claim-1", "claim-2"}
    assert config_quality_checks._card_row_has_source_trace(
        {"closure": {"lane": "deck_matched_public_guide"}}
    )
    assert not config_quality_checks._card_row_has_source_trace(
        {"evidence_chain": "invalid"}
    )
    assert config_quality_checks._card_row_has_source_trace(
        {
            "evidence_chain": [
                {
                    "source_type": "static_semantics",
                    "runtime_files": ["CARD_001.json"],
                }
            ]
        }
    )


def test_config_quality_identity_and_role_helpers_accept_mixed_report_shapes() -> None:
    assert config_quality_checks._deck_identity_card_ids(
        {
            "cards": ["CARD_001", {"card_id": "CARD_002"}, ""],
            "main_deck": "invalid",
            "sideboards": ["invalid", {"cards": ["CARD_003"]}],
        }
    ) == {"CARD_001", "CARD_002", "CARD_003"}
    assert config_quality_checks._card_ids_from_rows("invalid") == set()
    assert config_quality_checks._diagnostic_runtime_value_row_keys(
        "CARD_DEFAULT.json"
    )
    with pytest.raises(KeyError):
        config_quality_checks._diagnostic_runtime_value_row_keys("future.json")

    roles = config_quality_checks._semantic_surface_roles_by_card(
        {
            "rows": [
                {
                    "card_id": "CARD_001",
                    "surface_family": "CARDID.json",
                    "behavior_block": "OnBoardBonus",
                    "roles": ["engine"],
                }
            ]
        },
        {
            "cards": {"CARD_002": {"roles": ["payoff"]}, "bad": "invalid"},
            "card_role_map": [{"card_id": "CARD_003", "roles": ["removal"]}],
        },
        {"cards": [{"card_id": "CARD_004", "roles": ["draw"]}]},
    )
    assert set(roles) == {"CARD_001", "CARD_002", "CARD_003", "CARD_004"}

    metadata = config_quality_checks._card_specific_source_metadata_cards(
        {
            "cards": {
                "CARD_001": {"source_claim_ids": ["claim"]},
                "EMPTY": {},
            },
            "card_role_map": [
                {"card_id": "CARD_002", "roles": ["engine"]},
                {"roles": ["engine"]},
            ],
        },
        {
            "cards": [
                {"card_id": "CARD_003", "semantic_families": ["draw"]},
                {"semantic_families": ["draw"]},
            ]
        },
    )
    assert metadata == {"CARD_001", "CARD_002", "CARD_003"}


def test_config_quality_explained_runtime_files_cover_closure_and_operator_ledgers() -> None:
    explained = config_quality_checks._explained_runtime_files_from_reports(
        operator={
            "surface_status_ledger": [
                "invalid",
                {"status": "unsupported", "surface": "Combo"},
                {"status": "emitted", "surface": "Combo"},
                {"status": "emitted", "surface": "per-card <CARDID>.json"},
            ]
        },
        card_behavior={
            "rows": [
                {
                    "card_id": "CARD_001",
                    "surface_family": "CARDID.json",
                    "behavior_block": "OnBoardBonus",
                },
                {
                    "surface_family": "CARDID.json",
                    "behavior_block": "OnBoardBonus",
                },
            ]
        },
        explainability={
            "claim_rows": [
                {
                    "builder_or_router_decision": "emitted",
                    "closure": {"runtime_surfaces": ["GlobalValues.json"]},
                    "evidence_chain": [
                        "invalid",
                        {"builder_or_router_decision": "suppressed"},
                        {
                            "builder_or_router_decision": "emitted",
                            "runtime_files": ["Mulligan.json"],
                        },
                    ],
                }
            ]
        },
        surface_intent={
            "required_surfaces": ["Legacy.json"],
            "optional_surfaces": ["Combo.json"],
            "rows": [
                {
                    "surface": "Combo.json",
                    "intent": "combo",
                    "rule_id": "combo_sequences",
                },
                {"surface": "Legacy.json", "intent": "legacy_policy_surface"},
            ],
        },
    )
    assert explained >= {
        "GlobalValues.json",
        "Mulligan.json",
        "CARD_001.json",
        "Combo",
        "per-card <CARDID>.json",
        "Combo.json",
    }
    assert config_quality_checks._normal_apply_authority_drift(
        {"runtime_apply_contract": "invalid"}
    ) is None
    assert config_quality_checks._normal_apply_authority_drift(
        {"runtime_apply_contract": {"apply_authority": "future"}}
    ) == {
        "expected": config_quality_checks._NORMAL_APPLY_AUTHORITY,
        "reported": "future",
    }


def test_globalvalues_value_blocks_and_overlay_operations_are_deterministic() -> None:
    assert compile_globalvalues._values_block({"values": []}) == {
        "values": [{"condition": "*", "value": "0"}]
    }
    assert compile_globalvalues._values_block(
        {"condition": "mana", "value": 2}
    ) == {"values": [{"condition": "mana", "value": "2"}]}
    assert compile_globalvalues._values_block(3) == {
        "values": [{"condition": "*", "value": "3"}]
    }

    baseline = {"values": [{"condition": "*", "value": "10"}]}
    assert compile_globalvalues.apply_globalvalues_overlay_operation(
        baseline,
        operation="set",
        value="4",
    )["values"][0]["value"] == "4"
    assert compile_globalvalues.apply_globalvalues_overlay_operation(
        baseline,
        operation="increase",
        value=None,
    )["values"][0]["value"] == "11.50"
    assert compile_globalvalues.apply_globalvalues_overlay_operation(
        baseline,
        operation="decrease",
        value=None,
    )["values"][0]["value"] == "8.50"
    for operation, value, reason in (
        ("set", None, "globalvalues_overlay_set_value_missing"),
        ("increase", "1", "globalvalues_overlay_numeric_value_conflict"),
        ("future", None, "globalvalues_overlay_operation_unsupported"),
    ):
        with pytest.raises(ValueError, match=reason):
            compile_globalvalues.apply_globalvalues_overlay_operation(
                baseline,
                operation=operation,
                value=value,
            )

    assert compile_globalvalues._first_value({"values": []}) is None
    block: dict[str, object] = {}
    assert compile_globalvalues._set_first_value(block, "2") == "2"
    assert block == {"values": [{"condition": "*", "value": "2"}]}


def test_globalvalues_overlay_selection_authority_and_numeric_parser_edges() -> None:
    aggressive = {"speed": "tempo"}
    assert compile_globalvalues._overlay_for_key(
        "FirstTurnValueWeight", aggressive, {}
    ) == "set:0.75"
    assert compile_globalvalues._overlay_for_key(
        "SecondTurnValueWeight", aggressive, {}
    ) == "set:0.25"
    assert compile_globalvalues._overlay_for_key(
        "Other", aggressive, {"Other": "increase"}
    ) == "increase"
    assert compile_globalvalues._overlay_for_key(
        "Other", aggressive, {}, allow_speed_fallback=False
    ) is None

    assert compile_globalvalues._overlay_from_authority_row({"overlay": "set:3"}) == "set:3"
    assert compile_globalvalues._overlay_from_authority_row(
        {"operation": "set", "value": "3"}
    ) == "set:3"
    assert compile_globalvalues._overlay_from_authority_row(
        {"operation": "increase"}
    ) == "increase"
    assert compile_globalvalues._overlay_from_authority_row(
        {"operation": "none", "value": "none"}
    ) == "none"

    matrix = {
        "allowed_step1_overlays": [
            "invalid",
            {"key": None},
            {"key": "A", "key_authority": {"category": "custom"}},
        ],
        "blocked_until_runtime_evidence": [
            {"key": "B", "key_authority": "invalid"}
        ],
        "other": "ignored",
    }
    authorities = compile_globalvalues._key_authorities_from_matrix(matrix)
    assert authorities["A"]["category"] == "custom"
    assert authorities["B"] == compile_globalvalues.authority_for_key("B")
    assert compile_globalvalues._key_authorities_from_matrix([]) == {}
    assert compile_globalvalues._key_authorities_from_matrix(
        {
            "allowed_step1_overlays": {},
            "blocked_until_runtime_evidence": [],
        }
    ) == {}

    for operation, value in (("set", "NaN"), ("increase", "1")):
        with pytest.raises(
            ValueError,
            match="globalvalues_authority_overlay_value_invalid:Key",
        ):
            compile_globalvalues.validate_globalvalues_overlay_value(
                key="Key",
                operation=operation,
                value=value,
            )

    for overlay, expected in (
        ("set:7", "7"),
        ("increase", "11.50"),
        ("decrease", "8.50"),
        ("literal", "literal"),
    ):
        value_block = {"values": [{"condition": "*", "value": "10"}]}
        assert compile_globalvalues._apply_overlay(value_block, overlay) == expected

    assert compile_globalvalues._scale_numeric_string(None, 2) == "1"
    assert compile_globalvalues._scale_numeric_string("not-numeric", 2) == "not-numeric"
    assert compile_globalvalues._numeric_value("1 + 2 * 3") == 7.0
    assert compile_globalvalues._numeric_value("-2") == -2.0
    for malformed in ("1 // 2", "name", "1 / 0"):
        with pytest.raises(ValueError):
            compile_globalvalues._numeric_value(malformed)


def test_globalvalues_authority_rows_and_classification_fail_closed() -> None:
    for matrix, reason in (
        ([], "globalvalues_authority_matrix_must_be_object"),
        ({}, "globalvalues_authority_allowed_step1_overlays_must_be_list"),
        (
            {"allowed_step1_overlays": ["invalid"]},
            "globalvalues_authority_overlay_row_must_be_object:0",
        ),
        (
            {"allowed_step1_overlays": [{"key": ""}]},
            "globalvalues_authority_overlay_key_invalid:0",
        ),
        (
            {
                "allowed_step1_overlays": [
                    {
                        "key": "MyHeroPowerValue",
                        "overlay": "increase",
                        "operation": "increase",
                        "reason": "first",
                    },
                    {
                        "key": "MyHeroPowerValue",
                        "overlay": "decrease",
                        "operation": "decrease",
                        "reason": "second",
                    },
                ]
            },
            "globalvalues_authority_duplicate_overlay_key:MyHeroPowerValue",
        ),
    ):
        with pytest.raises(ValueError, match=reason):
            compile_globalvalues.validated_globalvalues_authority_rows(matrix)

    with pytest.raises(ValueError, match="default_values is required"):
        compile_globalvalues.compile_globalvalues()

    assert compile_globalvalues._classify_key("FirstTurnValueWeight") == "turn_weight"
    assert compile_globalvalues._classify_key("WeaponAttack") == "weapon"
    assert compile_globalvalues._classify_key("SecretValue") == "secret"
    assert compile_globalvalues._classify_key("HeroPower") == "hero"
    assert compile_globalvalues._classify_key("DeckValue") == "deck"
    assert compile_globalvalues._classify_key("DrawValue") == "mechanic_modifier"
    assert "early turn" in compile_globalvalues._overlay_reason(
        "FirstTurnValueWeight", "set:1"
    )
    assert "prioritizes" in compile_globalvalues._overlay_reason("Draw", "increase")
    assert "deprioritizes" in compile_globalvalues._overlay_reason("Armor", "decrease")
    assert "Deck-specific" in compile_globalvalues._overlay_reason("Other", "literal")


def _runtime_journal(**changes: object) -> runtime_transaction_journal.RuntimeTransactionJournal:
    transaction_id = "1" * 32
    root_digest = "a" * 64
    values: dict[str, object] = {
        "schema_version": 1,
        "transaction_id": transaction_id,
        "deck_name": "ShadowPriest",
        "source_manifest_sha256": "b" * 64,
        "state_key": f"shadowpriest--sha256-{'c' * 64}",
        "logical_config_dir": "shadowpriest",
        "package_root_sha256": root_digest,
        "candidate_path": f".hsconfig/staging/{transaction_id}",
        "target_path": f"CustomConfig/shadowpriest--sha256-{root_digest}",
        "candidate_identity": (7, 8, 0o40700),
        "target_identity": None,
        "owns_target": False,
        "previous_config_dir": "shadowpriest--sha256-" + ("d" * 64),
        "next_config_dir": f"shadowpriest--sha256-{root_digest}",
        "previous_ini_sha256": "e" * 64,
        "next_ini_sha256": "f" * 64,
        "phase": runtime_transaction_journal.RuntimeTransactionPhase.RUNTIME_VERIFIED,
    }
    values.update(changes)
    return runtime_transaction_journal.RuntimeTransactionJournal(**values)  # type: ignore[arg-type]


def test_runtime_journal_cleanup_and_identity_parsers_fail_closed() -> None:
    entry = runtime_transaction_journal.RuntimeCleanupEntry(
        kind="file",
        relative_path="CustomConfig/Deck/file.json",
        identity=(1, 2, 3),
    )
    assert entry.kind == "file"
    for changes in (
        {"kind": "link"},
        {"relative_path": "../escape"},
        {"identity": (1, -1, 3)},
    ):
        with pytest.raises(ValueError, match="runtime_cleanup_entry_invalid"):
            runtime_transaction_journal.RuntimeCleanupEntry(
                kind=changes.get("kind", "file"),
                relative_path=changes.get(
                    "relative_path", "CustomConfig/Deck/file.json"
                ),
                identity=changes.get("identity", (1, 2, 3)),
            )

    assert runtime_transaction_journal._parse_identity(None) is None
    assert runtime_transaction_journal._parse_identity([1, 2, 3]) == (1, 2, 3)
    for malformed in ((1, 2, 3), [1, 2], [1, True, 3], [1, -1, 3]):
        with pytest.raises(ValueError, match="identity"):
            runtime_transaction_journal._parse_identity(malformed)
    assert runtime_transaction_journal._unique_object([("a", 1)]) == {"a": 1}
    with pytest.raises(ValueError, match="duplicate"):
        runtime_transaction_journal._unique_object([("a", 1), ("a", 2)])
    with pytest.raises(ValueError, match="NaN"):
        runtime_transaction_journal._reject_constant("NaN")


def test_runtime_journal_serialization_path_and_payload_require_canonical_shape(
    tmp_path: PurePath,
) -> None:
    journal = _runtime_journal()
    assert runtime_transaction_journal.runtime_transaction_journal_bytes(journal).endswith(
        b"\n"
    )
    with pytest.raises(TypeError, match="runtime_transaction_journal_required"):
        runtime_transaction_journal.runtime_transaction_journal_bytes(object())  # type: ignore[arg-type]
    assert runtime_transaction_journal.runtime_transaction_journal_path(
        tmp_path,
        journal.transaction_id,
    ).name == f"{journal.transaction_id}.json"
    for invalid in ("", "short", "g" * 32):
        with pytest.raises(ValueError, match="runtime_transaction_journal_invalid"):
            runtime_transaction_journal.runtime_transaction_journal_path(tmp_path, invalid)

    payload = json.loads(
        runtime_transaction_journal.runtime_transaction_journal_bytes(journal)
    )
    assert runtime_transaction_journal._journal_from_payload(payload) == journal
    for malformed in (
        [],
        {**payload, "extra": True},
        {**payload, "cleanup_entries": {}},
        {**payload, "cleanup_entries": ["invalid"]},
        {
            **payload,
            "cleanup_entries": [
                {"kind": "file", "relative_path": "a", "identity": None}
            ],
        },
    ):
        with pytest.raises(ValueError):
            runtime_transaction_journal._journal_from_payload(malformed)


def test_runtime_journal_monotonic_successor_enforces_progress_and_ownership() -> None:
    prepared = _runtime_journal(
        candidate_identity=None,
        phase=runtime_transaction_journal.RuntimeTransactionPhase.PREPARED,
    )
    staged = _runtime_journal(
        phase=runtime_transaction_journal.RuntimeTransactionPhase.RUNTIME_STAGED
    )
    verified = _runtime_journal()
    finalized = _runtime_journal(
        target_identity=(7, 8, 0o40700),
        owns_target=True,
        phase=runtime_transaction_journal.RuntimeTransactionPhase.FINALIZED,
    )
    assert runtime_transaction_journal._is_monotonic_successor(prepared, staged)
    assert runtime_transaction_journal._is_monotonic_successor(staged, verified)
    assert runtime_transaction_journal._is_monotonic_successor(verified, finalized)
    assert not runtime_transaction_journal._is_monotonic_successor(
        replace(prepared, deck_name="Other"),
        staged,
    )
    assert not runtime_transaction_journal._is_monotonic_successor(verified, staged)
    assert not runtime_transaction_journal._is_monotonic_successor(
        replace(verified, candidate_identity=(1, 2, 3)),
        finalized,
    )
    assert not runtime_transaction_journal._is_monotonic_successor(
        replace(finalized, target_identity=(1, 2, 3), candidate_identity=(1, 2, 3)),
        finalized,
    )
    assert not runtime_transaction_journal._is_monotonic_successor(
        finalized,
        replace(finalized, owns_target=False),
    )

    cleanup_entry = runtime_transaction_journal.RuntimeCleanupEntry(
        kind="file",
        relative_path="CustomConfig/Deck/file.json",
        identity=(1, 2, 3),
    )
    cleanup = replace(
        finalized,
        cleanup_started=True,
        cleanup_entries=(cleanup_entry,),
        cleanup_cursor=0,
    )
    advanced = replace(cleanup, cleanup_cursor=1)
    assert runtime_transaction_journal._is_monotonic_successor(cleanup, advanced)
    assert not runtime_transaction_journal._is_monotonic_successor(advanced, cleanup)
    assert not runtime_transaction_journal._is_monotonic_successor(
        cleanup,
        replace(cleanup, cleanup_entries=()),
    )
    assert not runtime_transaction_journal._is_monotonic_successor(
        replace(verified, target_identity=(1, 2, 3)),
        replace(finalized, candidate_identity=verified.candidate_identity),
    )


def test_runtime_journal_size_path_and_filename_guards_are_explicit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: PurePath,
) -> None:
    journal = _runtime_journal()
    monkeypatch.setattr(runtime_transaction_journal, "MAX_RUNTIME_TRANSACTION_BYTES", 1)
    with pytest.raises(ValueError, match="too_large"):
        runtime_transaction_journal.runtime_transaction_journal_bytes(journal)
    monkeypatch.setattr(
        runtime_transaction_journal, "MAX_RUNTIME_TRANSACTION_BYTES", 1024 * 1024
    )

    with pytest.raises(ValueError, match="runtime_transaction_journal_invalid"):
        runtime_transaction_journal.write_runtime_transaction_journal(
            tmp_path / f"{journal.transaction_id}.json", journal
        )

    wrong_id = "2" * 32
    wrong_name = tmp_path / f"{wrong_id}.json"
    wrong_name.write_bytes(
        runtime_transaction_journal.runtime_transaction_journal_bytes(journal)
    )
    with pytest.raises(ValueError, match="runtime_transaction_journal_invalid"):
        runtime_transaction_journal.read_runtime_transaction_journal(wrong_name)


def test_runtime_journal_loader_promotes_valid_temp_and_ignores_invalid_temp(
    tmp_path: PurePath,
) -> None:
    assert runtime_transaction_journal.load_runtime_transaction_journals(tmp_path) == ()
    transactions = tmp_path / ".hsconfig" / "transactions"
    transactions.mkdir(parents=True)
    prepared = _runtime_journal(
        candidate_identity=None,
        phase=runtime_transaction_journal.RuntimeTransactionPhase.PREPARED,
    )
    temp = transactions / f".{prepared.transaction_id}.json.{'2' * 32}.tmp"
    temp.write_bytes(
        runtime_transaction_journal.runtime_transaction_journal_bytes(prepared)
    )

    assert runtime_transaction_journal.load_runtime_transaction_journals(tmp_path) == (
        prepared,
    )
    assert (transactions / f"{prepared.transaction_id}.json").is_file()
    assert not temp.exists()

    invalid_root = tmp_path / "invalid"
    invalid_transactions = invalid_root / ".hsconfig" / "transactions"
    invalid_transactions.mkdir(parents=True)
    invalid_temp = (
        invalid_transactions / f".{prepared.transaction_id}.json.{'3' * 32}.tmp"
    )
    invalid_temp.write_text("not-json", encoding="utf-8")
    assert runtime_transaction_journal.load_runtime_transaction_journals(
        invalid_root
    ) == ()


def test_runtime_journal_loader_rejects_nonprepared_initial_temp(
    tmp_path: PurePath,
) -> None:
    transactions = tmp_path / ".hsconfig" / "transactions"
    transactions.mkdir(parents=True)
    staged = _runtime_journal(
        phase=runtime_transaction_journal.RuntimeTransactionPhase.RUNTIME_STAGED
    )
    temp = transactions / f".{staged.transaction_id}.json.{'4' * 32}.tmp"
    temp.write_bytes(
        runtime_transaction_journal.runtime_transaction_journal_bytes(staged)
    )

    with pytest.raises(ValueError, match="runtime_transaction_store_invalid"):
        runtime_transaction_journal.load_runtime_transaction_journals(tmp_path)


def test_package_validation_surface_and_row_dispatch_reports_schema_errors() -> None:
    path = PurePath("Deck", "CARD_001.json")
    card_errors = validate_package._validate_card_behavior_blocks(
        path,
        {
            "GameCardId": "CARD_001",
            "FutureBlock": {},
            "OnBoardBonus": {},
            "BeforePlayCardBonus": {"values": ["invalid"]},
        },
    )
    assert any("unsupported card behavior block FutureBlock" in row for row in card_errors)
    assert any("block OnBoardBonus must contain values array" in row for row in card_errors)
    assert any("must be an object" in row for row in card_errors)

    assert validate_package._validate_values_blocks(
        path,
        {"GameCardId": "CARD_001", "Block": {}},
    ) == [f"{path}: block Block must contain values array"]
    global_errors = validate_package._validate_globalvalues_rows(
        PurePath("GlobalValues.json"),
        {
            "Skip": "invalid",
            "NoValues": {},
            "Rows": {
                "values": [
                    "invalid",
                    {"value": "unsafe"},
                    {"condition": "*"},
                ]
            },
        },
    )
    assert any("must be an object" in row for row in global_errors)
    assert any("missing condition" in row for row in global_errors)
    assert any("missing value" in row for row in global_errors)
    assert any("safe numeric expression" in row for row in global_errors)


def test_package_validation_mulligan_combo_and_numeric_edges_are_actionable() -> None:
    mulligan_path = PurePath("Mulligan.json")
    lone = validate_package._validate_mulligan(
        mulligan_path,
        {"Mulligan": {"values": [{"mulligan": "*", "condition": "*", "value": "discard"}]}},
    )
    assert any("lone_wildcard_discard" in row for row in lone)
    assert any("before any non-wildcard hold" in row for row in lone)
    malformed = validate_package._validate_mulligan(
        mulligan_path,
        {
            "Mulligan": {
                "values": [
                    "invalid",
                    {"mulligan": "", "value": "future"},
                    {"mulligan": "CARD_001", "condition": "*", "value": "hold"},
                    {"mulligan": "*", "condition": "*", "value": "discard"},
                ]
            }
        },
    )
    assert any("must be an object" in row for row in malformed)
    assert any("missing mulligan" in row for row in malformed)
    assert not any("before any non-wildcard hold" in row for row in malformed)

    combo_path = PurePath("Combo.json")
    assert any(
        "missing required block ComboList" in row
        for row in validate_package._validate_combo(combo_path, {})
    )
    combo_errors = validate_package._validate_combo_row(
        combo_path,
        0,
        {
            "extra": True,
            "condition": "*",
            "combo": "bad >> CARD_001",
            "value": "1 >> invalid",
        },
    )
    assert any("unsupported ComboList row key extra" in row for row in combo_errors)
    assert any("invalid Combo card id bad" in row for row in combo_errors)
    assert any("must be numeric" in row for row in combo_errors)
    assert validate_package._split_combo_segments("") == []
    assert validate_package._split_combo_segments(" A >-> B ") == ["A", "B"]
    assert validate_package._finite_decimal_error("9" * 400) == "must be a finite decimal"
    assert validate_package._finite_decimal_error("invalid") == "must be numeric"
    assert validate_package._finite_decimal_error("1.5") is None
    with pytest.raises(ValueError, match="non-standard JSON constant"):
        validate_package._reject_nonstandard_json_constant("NaN")

    assert validate_package._validate_named_values_blocks(
        combo_path,
        {"Other": {}},
        {"ComboList"},
    )
    assert validate_package._validate_combo(
        combo_path,
        {"ComboList": {}},
    )
    invalid_rows = validate_package._validate_combo(
        combo_path,
        {"ComboList": {"values": ["invalid"]}},
    )
    assert any("must be an object" in row for row in invalid_rows)
    missing_fields = validate_package._validate_combo_row(combo_path, 0, {})
    assert any("missing combo" in row for row in missing_fields)
    assert any("missing value" in row for row in missing_fields)
    assert validate_package._validate_globalvalues_value(
        PurePath("GlobalValues.json"),
        "Key",
        "NaN",
    )


def test_package_validation_globalvalues_profile_parity_and_ledgers_fail_closed() -> None:
    path = PurePath("GlobalValues.json")
    assert validate_package._validate_required_globalvalues_profile_schema(
        path,
        {},
        authority_matrix_present=False,
    ) == []
    for profile, matrix_present in (
        ({}, True),
        ({"schema_version": True}, False),
        ({"schema_version": 3}, False),
        ({"schema_version": 1}, True),
    ):
        assert validate_package._validate_required_globalvalues_profile_schema(
            path,
            profile,
            authority_matrix_present=matrix_present,
        )

    assert validate_package._requires_globalvalues_authority_parity(
        {"schema_version": 2}
    )
    assert not validate_package._requires_globalvalues_authority_parity(
        {"schema_version": True}
    )
    for key in ("", "   ", 3):
        assert not validate_package._is_safe_globalvalues_key(key)

    generated, profiled, errors = validate_package._normalize_globalvalues_profile_ledgers(
        path,
        {"generated_overlay_keys": "invalid", "keys": []},
    )
    assert generated == set()
    assert profiled == set()
    assert len(errors) == 2
    generated, profiled, errors = validate_package._normalize_globalvalues_profile_ledgers(
        path,
        {
            "generated_overlay_keys": ["", "A", "A"],
            "keys": {"": {}, "A": {}},
        },
    )
    assert generated == {"A"}
    assert profiled == {"A"}
    assert len(errors) == 3

    coverage_errors, expected = validate_package._validate_required_globalvalues_overlay_coverage(
        path,
        {},
        {"expected_overlay_keys": ["", "A", "A"]},
        generated_overlay_keys=set(),
        profiled_keys=set(),
    )
    assert expected == {"A"}
    assert len(coverage_errors) >= 4
    assert validate_package._validate_required_generated_overlay_keys(
        path,
        {},
        {"Unknown"},
        set(),
        set(),
    )

    for function, parity_key in (
        (
            validate_package._validate_required_globalvalues_authority_parity,
            "authority_parity",
        ),
        (
            validate_package._validate_required_globalvalues_baseline_overlay_parity,
            "baseline_overlay_parity",
        ),
    ):
        assert function(
            path,
            {},
            {
                parity_key: {
                    "authorized_overlay_keys": "invalid",
                    "emitted_overlay_keys": [],
                }
            },
            set(),
        )
        assert function(
            path,
            {},
            {
                parity_key: {
                    "authorized_overlay_keys": [],
                    "emitted_overlay_keys": "invalid",
                }
            },
            set(),
        )
        assert function(
            path,
            {},
            {
                parity_key: {
                    "status": "mismatch",
                    "authorized_overlay_keys": ["A"],
                    "emitted_overlay_keys": [],
                }
            },
            set(),
        )


def test_package_validation_filesystem_entry_edges(tmp_path: PurePath) -> None:
    missing = validate_package.validate_config_package(tmp_path / "missing")
    assert missing["status"] == "failed"
    root = tmp_path / "package"
    custom = root / "CustomConfig"
    custom.mkdir(parents=True)
    no_deck = validate_package.validate_config_package(root)
    assert any("no deck config directories" in row for row in no_deck["errors"])
    deck = custom / "Deck"
    deck.mkdir()
    (deck / "Mulligan.json").write_text("[]", encoding="utf-8")
    invalid = validate_package.validate_config_package(root)
    assert any("top-level JSON value must be an object" in row for row in invalid["errors"])


def test_compiler_support_receipt_and_authority_helpers_keep_only_typed_claims() -> None:
    claims = package_compiler_support._with_strategic_receipt_verification(
        [
            "invalid",
            {"claim_kind": "card_role", "claim_id": "card"},
            {"claim_kind": "mulligan_keep", "claim_id": "mulligan"},
        ],
        deck_identity={"deck_fingerprint": " FINGERPRINT "},
        verified_source_receipts=[],
    )
    assert len(claims) == 2
    assert "strategic_receipt_verified" not in claims[0]
    assert claims[1]["strategic_receipt_verified"] is False
    assert package_compiler_support._with_strategic_receipt_verification(
        {},
        deck_identity={},
        verified_source_receipts=[],
    ) == []

    claim_rows = {
        "one": {"evidence_authority": {"authority_id": "authority-1", "policy_id": "policy"}},
        "two": {"evidence_authority": {"authority_id": ""}},
        "three": {"evidence_authority": "invalid"},
    }
    assert package_compiler_support._card_evidence_authority_ids(
        claim_ids=["one", "two", "three", "missing"],
        claim_rows=claim_rows,
    ) == ["authority-1"]
    assert package_compiler_support._claim_evidence_authority("invalid") is None
    assert package_compiler_support._claim_evidence_authority_id(
        claim_rows["one"], fallback="fallback"
    ) == "authority-1"
    assert package_compiler_support._claim_evidence_authority_id(
        claim_rows["two"], fallback="fallback"
    ) == "fallback"
    assert package_compiler_support._claim_evidence_policy_id(claim_rows["one"]) == "policy"
    assert package_compiler_support._claim_evidence_policy_id(claim_rows["two"]) is None

    assert not package_compiler_support._is_exact_bot_delegation("invalid", {})
    assert package_compiler_support._is_exact_bot_delegation(
        {"builder_or_router_decision": "bot_delegated"},
        {"policy_id": "BOT_NATIVE_PRE_RUN"},
    )
    assert package_compiler_support._is_exact_bot_delegation(
        {"builder_or_router_decision": "bot_delegated"},
        {"evidence_authority": {"policy_id": "BOT_NATIVE_PRE_RUN"}},
    )


def test_compiler_support_policy_card_and_claim_helpers_normalize_mixed_inputs() -> None:
    assert package_compiler_support._normalize_claim_conflict_report(
        {"claims": "invalid"}
    )["claim_conflict_report"]
    merged = package_compiler_support._policy_mulligan_deck_cards(
        {
            "CARD_001": {"role": "engine"},
            "CARD_002": "invalid",
            "": {},
        },
        {
            "cards": [
                {"card_id": "CARD_001", "name": "One"},
                {"card_id": "CARD_002", "name": "Two"},
            ]
        },
    )
    assert merged["CARD_001"] == {
        "card_id": "CARD_001",
        "name": "One",
        "role": "engine",
    }
    assert merged["CARD_002"]["card_id"] == "CARD_002"
    assert package_compiler_support._policy_mulligan_deck_cards(
        "invalid", {}
    ) == {}

    delegated = package_compiler_support._explicit_bot_delegation_claims(
        card_ids={"CARD_001": {}, "CARD_002": {}, "": {}},
        existing_claims=[{"cards": "CARD_001"}, {"cards": {}}],
        policy_id="BOT_NATIVE_PRE_RUN",
    )
    assert delegated[0]["cards"] == ["CARD_002"]
    assert package_compiler_support._explicit_bot_delegation_claims(
        card_ids={"CARD_001": {}},
        existing_claims=[{"cards": ["CARD_001"]}],
        policy_id="BOT_NATIVE_PRE_RUN",
    ) == []
    assert package_compiler_support._claim_card_ids({"cards": {}}) == set()

    for claim in (
        {"claim_kind": "mulligan_bot_delegation"},
        {"source_type": "versioned_internal_policy"},
        {"source_family": "versioned_internal_policy"},
        {"policy_rule_id": "explicit_policy_claim"},
    ):
        assert package_compiler_support._is_internal_mulligan_policy_claim(claim)
    assert not package_compiler_support._is_internal_mulligan_policy_claim({})
    assert package_compiler_support._metadata_rows_by_card({"cards": "invalid"}) == {}


def test_compiler_support_diagnostic_rows_and_claim_filters_are_bounded() -> None:
    diagnostics = package_compiler_support._build_plan_input_diagnostics(
        canonical_guide_claim_bundle={"claims": [{"claim_id": "canonical"}]},
        imported_guide_claim_bundle={
            "claims": ["invalid", {"claim_id": "imported"}],
            "canonical_source_receipts": ["opaque", {"receipt": "row"}],
        },
        imported_mulligan_plan=None,
        imported_card_behavior_plan={"rows": []},
        imported_combo_plan=None,
        imported_global_values_authority_matrix={
            "allowed_step1_overlays": "invalid",
            "blocked_until_runtime_evidence": ["invalid", {"key": "A"}],
        },
    )
    assert diagnostics["canonical_claim_ids"] == ["canonical"]
    assert diagnostics["imported_claim_count"] == 1
    assert diagnostics["imported_source_receipt_count"] == 2
    assert diagnostics["imported_row_count"] == 1
    assert set(diagnostics["imported_plan_reports"]) == {
        "card_behavior_plan_report.json"
    }

    assert package_compiler_support._row_claim_ids(
        {
            "claim_id": "one",
            "source_claim_id": "two",
            "claim_ids": "three",
            "source_claim_ids": ["four", ""],
            "claim_refs": {},
        }
    ) == {"one", "two", "three", "four"}
    assert package_compiler_support._filter_runtime_rows_by_claim_ids(
        "invalid", {"one"}
    ) == []
    assert package_compiler_support._filter_runtime_rows_by_claim_ids(
        ["invalid", {"claim_id": "one"}, {"claim_id": "two"}],
        {"one"},
    ) == [{"claim_id": "one"}]
    assert package_compiler_support._card_behavior_identity_links(
        {"cards": []}
    ) == {}


def test_compiler_support_list_cards_and_globalvalue_filters_cover_all_row_lanes() -> None:
    merged = package_compiler_support._policy_mulligan_deck_cards(
        ["invalid", {"card_id": "CARD_001", "role": "engine"}],
        [],
    )
    assert merged == {"CARD_001": {"card_id": "CARD_001", "role": "engine"}}

    canonical = {
        "allowed_step1_overlays": [
            {"key": "baseline", "operation": "set", "value": "1"},
            {"key": "same", "operation": "set", "value": "2"},
        ],
        "blocked_until_runtime_evidence": [{"key": "already"}],
    }
    filtered = package_compiler_support._filter_globalvalues_authority_matrix(
        {
            "allowed_step1_overlays": [
                "invalid",
                {"key": "baseline", "operation": "set", "value": "1"},
                {"key": "same", "operation": "set", "value": "2"},
                {"key": "new", "operation": "set", "value": 3},
            ]
        },
        canonical_matrix=canonical,
        diagnostic_matrix={
            "blocked_until_runtime_evidence": [
                {"key": "already"},
                {"key": "diagnostic"},
            ]
        },
    )
    assert filtered["allowed_step1_overlays"] == canonical["allowed_step1_overlays"]
    assert [row["key"] for row in filtered["blocked_until_runtime_evidence"]] == [
        "already",
        "diagnostic",
        "new",
    ]

    assert package_compiler_support._card_behavior_identity_links(
        {"cards": {"bad": "invalid", "CARD_001": {"linked_entities": []}}}
    )["CARD_001"] == {"links": []}


def test_derivation_receipt_schema_and_authority_context_fail_closed() -> None:
    assert not package_derivation_receipt.package_authority_context_verified(None)
    assert package_derivation_receipt.package_authority_context_verified(
        {
            "strict_validation_passed": True,
            "deck_input_apply_eligible": True,
            "source_authority_verified": True,
            "derivation_receipt_verified": True,
        }
    )
    assert not package_derivation_receipt.package_authority_context_verified(
        {
            "strict_validation_passed": True,
            "deck_input_apply_eligible": True,
            "source_authority_verified": True,
            "derivation_receipt_verified": 1,
        }
    )

    package = _quality_package_root({}).package
    valid, reasons = package_derivation_receipt.verify_package_derivation_receipt_from_view(
        package,
        {"schema_version": 999},
    )
    assert not valid
    assert reasons[0]["code"] == "package_derivation_receipt_schema_unsupported"


def test_derivation_receipt_source_container_and_claim_identity_edges() -> None:
    deck = {"deck_fingerprint": "fingerprint"}
    assert package_derivation_receipt.canonical_source_receipt_reasons(
        bundle={"canonical_source_receipts": "invalid"},
        deck_identity=deck,
    )[0]["code"] == "source_authority_receipt_invalid"
    assert package_derivation_receipt.canonical_source_receipt_reasons(
        bundle={"canonical_source_receipts": []},
        deck_identity=deck,
    ) == []
    assert package_derivation_receipt.canonical_source_receipt_reasons(
        bundle={"canonical_source_receipts": ["invalid"]},
        deck_identity=deck,
    )[0]["code"] == "source_authority_receipt_invalid"

    invalid_provenance = {
        "receipt_kind": "canonical_exact_deck_source_document",
        "acquisition_provenance": {},
    }
    assert package_derivation_receipt.canonical_source_receipt_reasons(
        bundle={"canonical_source_receipts": [invalid_provenance]},
        deck_identity=deck,
    )[0]["code"] == "source_authority_receipt_invalid"

    missing_claim = {
        **invalid_provenance,
        "acquisition_provenance": {
            "acquisition_mode": "frozen_resource",
            "retrieved_at": "2026-08-01",
            "content_sha256": "sha256:" + ("a" * 64),
        },
    }
    reason = package_derivation_receipt.canonical_source_receipt_reasons(
        bundle={"canonical_source_receipts": [missing_claim]},
        deck_identity=deck,
    )[0]
    assert reason["code"] in {
        "source_authority_receipt_invalid",
        "source_receipt_claim_missing",
    }

    assert package_derivation_receipt._claim_deck_fingerprint({}) == ""
    assert package_derivation_receipt._claim_deck_fingerprint(
        {"deck_match": {"exact_deck_evidence": "invalid"}}
    ) == ""
    assert package_derivation_receipt._claim_deck_fingerprint(
        {
            "deck_match": {
                "exact_deck_evidence": {"matched_deck_fingerprint": " fingerprint "}
            }
        }
    ) == "fingerprint"


def test_derivation_receipt_claim_parity_checks_source_and_provenance_binding() -> None:
    receipt = {
        "source_ref": "source-1",
        "source_url": "https://example.invalid/guide",
        "claim_kind": "mulligan_keep",
        "acquisition_provenance": {"mode": "fixture"},
    }
    claim = {
        "source_refs": "invalid",
        "source_ref": "source-1",
        "source_url": "https://example.invalid/guide",
        "claim_kind": "mulligan_keep",
        "acquisition_provenance": {"mode": "fixture"},
    }
    assert not package_derivation_receipt._receipt_claim_parity_verified(
        receipt=receipt,
        claim=claim,
        source_evidence_rows=[],
    )
    source_row = {
        "source_ref": "source-1",
        "source_url": "https://example.invalid/guide",
        "acquisition_provenance": {"mode": "fixture"},
    }
    claim["source_refs"] = ["source-1"]
    assert not package_derivation_receipt._receipt_claim_parity_verified(
        receipt=receipt,
        claim=claim,
        source_evidence_rows=[source_row, source_row],
    )
    mismatched_kind = {**receipt, "claim_kind": "play_order"}
    assert not package_derivation_receipt._receipt_claim_parity_verified(
        receipt=mismatched_kind,
        claim=claim,
        source_evidence_rows=[source_row],
    )


def test_derivation_receipt_stable_projections_filter_malformed_rows() -> None:
    assert package_derivation_receipt._stable_authority_value(
        {"b": (2, 1), "a": {"nested": True}}
    ) == {"a": {"nested": True}, "b": [2, 1]}
    with pytest.raises(ValueError, match="Canonical source receipts must be a list"):
        package_derivation_receipt._canonical_receipt_sequence("invalid")
    assert package_derivation_receipt._canonical_receipt_sequence(
        [{"b": 2}, {"a": 1}]
    ) == [{"a": 1}, {"b": 2}]
    projection = package_derivation_receipt._source_provenance_projection(
        {
            "claims": "invalid",
            "source_evidence_index": [
                "invalid",
                {"source_ref": "without-provenance"},
                {
                    "source_ref": "source-1",
                    "source_id": "id-1",
                    "acquisition_provenance": {"mode": "fixture"},
                },
            ],
        }
    )
    assert projection == [
        {
            "record_kind": "source_evidence",
            "record_ids": {"source_ref": "source-1", "source_id": "id-1"},
            "acquisition_provenance": {"mode": "fixture"},
        }
    ]


def test_derivation_receipt_file_backed_authority_helpers_reject_wrong_shapes(
    tmp_path: PurePath,
) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    manifest = reports / "input_manifest.json"
    manifest.write_text("[]", encoding="utf-8")
    assert package_derivation_receipt.deck_input_apply_eligibility_reasons(
        tmp_path
    ) == []

    bundle = reports / "guide_claim_bundle.json"
    bundle.write_text("[]", encoding="utf-8")
    assert package_derivation_receipt._source_authority_state(tmp_path)[1] == 0
    assert package_derivation_receipt.source_apply_eligibility_reasons(tmp_path)[
        0
    ]["code"] == "diagnostic_source_not_apply_eligible"

    bundle.write_text(
        json.dumps({"canonical_source_receipts": "invalid"}), encoding="utf-8"
    )
    assert package_derivation_receipt._source_authority_state(tmp_path)[0][0][
        "code"
    ] == "source_authority_receipt_invalid"

    bundle.write_text(
        json.dumps({"canonical_source_receipts": [{"receipt_kind": "invalid"}]}),
        encoding="utf-8",
    )
    (reports / "deck_identity.json").write_text("[]", encoding="utf-8")
    reasons, count = package_derivation_receipt._source_authority_state(tmp_path)
    assert count == 1
    assert reasons[0]["code"] == "source_authority_receipt_invalid"

    behavior = reports / "card_behavior_plan_report.json"
    behavior.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="Linked runtime owner evidence"):
        package_derivation_receipt._linked_runtime_owners(tmp_path)
    assert package_derivation_receipt._runtime_file_digests(tmp_path) == {}

    view = _quality_package_root(
        {"reports/card_behavior_plan_report.json": []}
    ).package
    with pytest.raises(ValueError, match="Linked runtime owner evidence"):
        package_derivation_receipt._linked_runtime_owners_from_view(view)


def test_derivation_receipt_claim_parity_reaches_claim_kind_mismatch() -> None:
    provenance = build_acquisition_provenance(
        mode="live_http", content="complete exact guide text"
    )
    source_url = "https://example.invalid/guide"
    claim = {
        "claim_kind": "mulligan_keep",
        "source_refs": ["source-1"],
        "source_url": source_url,
        "acquisition_provenance": provenance,
    }
    source_row = {
        "source_ref": "source-1",
        "source_url": source_url,
        "acquisition_provenance": provenance,
    }
    receipt = {
        "source_ref": "source-1",
        "source_url": source_url,
        "claim_kind": "play_order",
        "acquisition_provenance": provenance,
    }

    assert not package_derivation_receipt._receipt_claim_parity_verified(
        receipt=receipt,
        claim=claim,
        source_evidence_rows=[source_row],
    )


def test_derivation_receipt_remaining_authority_and_view_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: PurePath,
) -> None:
    provenance = build_acquisition_provenance(
        mode="live_http", content="complete exact guide text"
    )
    reasons = package_derivation_receipt.canonical_source_receipt_reasons(
        bundle={
            "canonical_source_receipts": [
                {
                    "receipt_kind": "canonical_exact_deck_source_document",
                    "acquisition_provenance": provenance,
                }
            ]
        },
        deck_identity={"deck_fingerprint": "fingerprint"},
    )
    assert reasons[0]["code"] == "source_receipt_claim_missing"

    monkeypatch.setattr(
        package_derivation_receipt,
        "build_package_derivation_receipt",
        lambda _package: {"schema_version": 1},
    )
    monkeypatch.setattr(
        package_derivation_receipt,
        "verify_package_derivation_receipt",
        lambda *_args: (False, [{"code": "reason"}]),
    )
    monkeypatch.setattr(
        package_derivation_receipt,
        "write_package_derivation_receipt",
        lambda *_args: "sha256:" + ("a" * 64),
    )
    authority = package_derivation_receipt.refresh_package_derivation_authority(
        tmp_path
    )
    assert authority["reasons"] == [{"code": "reason"}]

    monkeypatch.setattr(
        package_derivation_receipt,
        "validate_complete_package",
        lambda _package: {"status": "ok", "errors": []},
    )
    real_read_json = package_derivation_receipt.read_json
    monkeypatch.setattr(
        package_derivation_receipt,
        "read_json",
        lambda _path: {"schema_version": 1},
    )
    monkeypatch.setattr(
        package_derivation_receipt,
        "package_derivation_receipt_sha256",
        lambda _receipt: "sha256:" + ("b" * 64),
    )
    monkeypatch.setattr(
        package_derivation_receipt,
        "_source_authority_state",
        lambda _package: ([], 1),
    )
    monkeypatch.setattr(
        package_derivation_receipt,
        "source_apply_eligibility_reasons",
        lambda _package: [],
    )
    monkeypatch.setattr(
        package_derivation_receipt,
        "deck_input_apply_eligibility_reasons",
        lambda _package: [],
    )
    context = package_derivation_receipt.build_package_authority_context(tmp_path)
    assert context["derivation_receipt_verified"] is False
    assert context["receipt_sha256"] == "sha256:" + ("b" * 64)
    monkeypatch.setattr(package_derivation_receipt, "read_json", lambda _path: [])
    no_receipt_context = package_derivation_receipt.build_package_authority_context(
        tmp_path
    )
    assert no_receipt_context["receipt_sha256"] is None
    monkeypatch.setattr(package_derivation_receipt, "read_json", real_read_json)

    monkeypatch.setattr(
        package_derivation_receipt, "_AUTHORITATIVE_JSON_PATHS", ()
    )
    (tmp_path / "reports").mkdir(exist_ok=True)
    (tmp_path / "reports" / "guide_claim_bundle.json").write_text(
        "[]", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="source receipt container"):
        package_derivation_receipt._authoritative_input_digests(tmp_path)

    invalid_guide = _quality_package_root(
        {"reports/guide_claim_bundle.json": []}
    ).package
    with pytest.raises(ValueError, match="source receipt container"):
        package_derivation_receipt._authoritative_input_digests_from_view(
            invalid_guide
        )

    missing_behavior = _quality_package_root(
        {"reports/guide_claim_bundle.json": {}}
    ).package
    monkeypatch.setattr(
        package_derivation_receipt,
        "_AUTHORITATIVE_JSON_PATHS",
        ("reports/card_behavior_plan_report.json",),
    )
    digests = package_derivation_receipt._authoritative_input_digests_from_view(
        missing_behavior
    )
    assert "reports/card_behavior_plan_report.json" in digests

    invalid_input = _quality_package_root(
        {
            "reports/input_manifest.json": [],
            "reports/guide_claim_bundle.json": {},
        }
    ).package
    monkeypatch.setattr(
        package_derivation_receipt,
        "_AUTHORITATIVE_JSON_PATHS",
        ("reports/input_manifest.json",),
    )
    with pytest.raises(ValueError, match="Authoritative package input"):
        package_derivation_receipt._authoritative_input_digests_from_view(
            invalid_input
        )

    verification = _quality_package_root(
        {
            "reports/guide_claim_bundle.json": {},
            "reports/deck_input_verification.json": {"verified": True},
        }
    ).package
    monkeypatch.setattr(
        package_derivation_receipt, "_AUTHORITATIVE_JSON_PATHS", ()
    )
    assert "deck_input_verification" in (
        package_derivation_receipt._authoritative_input_digests_from_view(
            verification
        )
    )
    assert package_derivation_receipt._linked_runtime_owners_from_view(
        _quality_package_root({}).package
    ) == []


def test_publication_parent_and_directory_identity_helpers_are_fail_closed(
    tmp_path: PurePath,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    root_identity = package_publication._directory_identity(root)
    assert package_publication._parent_chain_matches(((root, root_identity),))
    assert not package_publication._parent_chain_matches(())
    with pytest.raises(ValueError, match="published_package_parent_identity_mismatch"):
        package_publication._require_parent_chain(())
    package_publication._require_directory_identity(root, root_identity)
    with pytest.raises(ValueError, match="published_package_root_identity_mismatch"):
        package_publication._require_directory_identity(root, (0, 0))
    assert package_publication._normal_directory_exists(root)
    assert not package_publication._normal_directory_exists(root / "missing")

    nested = root / "a" / "b"
    created = package_publication._ensure_parent(nested)
    assert nested.is_dir()
    assert set(created) == {root / "a", nested}
    package_publication._remove_created_parents(created)
    assert not (root / "a").exists()
    file_parent = root / "file"
    file_parent.touch()
    with pytest.raises(ValueError, match="publication_parent_invalid"):
        package_publication._ensure_parent(file_parent)


def test_publication_tree_shape_and_owned_directory_resolution(tmp_path: PurePath) -> None:
    root = tmp_path / "tree"
    nested = root / "reports" / "nested"
    nested.mkdir(parents=True)
    (root / "top.json").write_text("{}", encoding="utf-8")
    (nested / "row.json").write_text("{}", encoding="utf-8")
    root_identity = package_publication._directory_identity(root)
    files, directories = package_publication._physical_tree_shape(
        root,
        root_identity=root_identity,
    )
    assert files == {"top.json", "reports/nested/row.json"}
    assert directories == {"reports", "reports/nested"}

    directory_identities = {
        "reports": package_publication._directory_identity(root / "reports"),
        "reports/nested": package_publication._directory_identity(nested),
    }
    located = package_publication._locate_owned_directories(
        root,
        root_identity=root_identity,
        directory_identities=directory_identities,
    )
    assert located == {"reports": root / "reports", "reports/nested": nested}
    assert package_publication._locate_owned_directories(
        root,
        root_identity=(0, 0),
        directory_identities=directory_identities,
    ) == {}
    package_publication._require_owned_directory(
        root,
        PurePosixPath("."),
        root_identity=root_identity,
        directory_identities=directory_identities,
    )
    with pytest.raises(ValueError, match="published_package_tree_shape_mismatch"):
        package_publication._require_owned_directory(
            root,
            PurePosixPath("missing"),
            root_identity=root_identity,
            directory_identities=directory_identities,
        )


def test_publication_artifact_lookup_and_verification_bind_parent_and_bytes(
    tmp_path: PurePath,
) -> None:
    root = tmp_path / "artifacts"
    reports = root / "reports"
    reports.mkdir(parents=True)
    target = reports / "row.json"
    target.write_bytes(b"{}")
    root_identity = package_publication._directory_identity(root)
    reports_identity = package_publication._directory_identity(reports)
    identities = {"reports": reports_identity}
    actual = {"reports": reports}
    artifact = package_publication.AuthorityArtifact.from_content(
        relative_path="reports/row.json",
        content=b"{}",
    )
    node_identity = package_publication._node_identity(target.lstat())

    assert package_publication._actual_artifact_target(
        root,
        "reports/row.json",
        root_identity=root_identity,
        directory_identities=identities,
        actual_directories=actual,
    ) == target
    assert package_publication._actual_artifact_target(
        root,
        "reports/row.json",
        root_identity=(0, 0),
        directory_identities=identities,
        actual_directories=actual,
    ) is None
    assert package_publication._actual_artifact_target(
        root,
        "missing/row.json",
        root_identity=root_identity,
        directory_identities=identities,
        actual_directories=actual,
    ) is None
    assert package_publication._verified_owned_regular_file(
        root,
        artifact,
        root_identity=root_identity,
        expected_identity=node_identity,
        directory_identities=identities,
        actual_directories=actual,
    ) == target
    assert package_publication._verified_owned_regular_file(
        root,
        artifact,
        root_identity=root_identity,
        expected_identity=None,
        directory_identities=identities,
        actual_directories=actual,
    ) is None
    target.write_bytes(b"changed")
    assert package_publication._verified_owned_regular_file(
        root,
        artifact,
        root_identity=root_identity,
        expected_identity=package_publication._node_identity(target.lstat()),
        directory_identities=identities,
        actual_directories=actual,
    ) is None


def test_publication_pruning_observer_and_reparse_cleanup_are_scoped(tmp_path: PurePath) -> None:
    root = tmp_path / "prune"
    empty = root / "empty"
    empty.mkdir(parents=True)
    root_identity = package_publication._directory_identity(root)
    empty_identity = package_publication._directory_identity(empty)
    package_publication._prune_owned_directories(
        root,
        root_identity=root_identity,
        directory_identities={"missing": (0, 0), "empty": empty_identity},
        actual_directories={"empty": empty},
    )
    assert not empty.exists()
    package_publication._prune_owned_directories(
        root,
        root_identity=(0, 0),
        directory_identities={},
        actual_directories={},
    )

    observed: list[tuple[object, object]] = []
    package_publication._observe(
        lambda point, active: observed.append((point, active)),
        "after_staging_created",
        root,
    )
    package_publication._observe(None, "after_staging_created", root)
    assert observed == [("after_staging_created", root)]


def test_publication_remaining_identity_and_cleanup_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: PurePath,
) -> None:
    root = tmp_path / "publication-edges"
    reports = root / "reports"
    reports.mkdir(parents=True)
    target = reports / "row.json"
    target.write_bytes(b"{}")
    root_identity = package_publication._directory_identity(root)
    reports_identity = package_publication._directory_identity(reports)

    located = package_publication._locate_owned_directories(
        root,
        root_identity=root_identity,
        directory_identities={"reports/nested": reports_identity},
    )
    assert located == {}

    package_publication._remove_safe_unbound_nodes_in_owned_directories(
        root,
        root_identity=(0, 0),
        directory_identities={"reports": reports_identity},
        actual_directories={"reports": reports},
    )
    with pytest.raises(ValueError, match="published_package_tree_shape_mismatch"):
        package_publication._require_normal_directory(root / "missing")

    artifact = package_publication.AuthorityArtifact.from_content(
        relative_path="reports/row.json",
        content=b"[]",
    )
    assert package_publication._verified_owned_regular_file(
        root,
        artifact,
        root_identity=root_identity,
        expected_identity=package_publication._node_identity(target.lstat()),
        directory_identities={"reports": reports_identity},
        actual_directories={"reports": reports},
    ) is None

    fake_rendered = SimpleNamespace(
        artifacts=SimpleNamespace(file_names=lambda: ("reports/row.json",))
    )
    with pytest.raises(ValueError, match="published_package_artifact_identity_mismatch"):
        package_publication._verify_owned_identities(
            fake_rendered,
            root,
            root_identity=root_identity,
            file_identities={},
            directory_identities={},
        )

    outside = tmp_path / "outside" / "staging"
    with pytest.raises(RuntimeError, match="publication_rollback_target_invalid"):
        package_publication._remove_staging_tree(
            fake_rendered,
            outside,
            parent=root,
            root_identity=None,
            file_identities={},
            directory_identities={},
        )

    empty_dir = root / "empty-dir"
    empty_dir.mkdir()
    package_publication._remove_reparse_node(empty_dir, empty_dir.lstat())
    assert not empty_dir.exists()
    regular = root / "regular"
    regular.write_text("x", encoding="utf-8")
    package_publication._remove_reparse_node(regular, regular.lstat())
    assert not regular.exists()

    stray = root / "stray"
    stray.write_text("x", encoding="utf-8")
    monkeypatch.setattr(
        package_publication,
        "_stat_is_reparse",
        lambda status: stat.S_ISREG(status.st_mode) and status.st_size == 1,
    )
    package_publication._remove_safe_unbound_nodes_in_owned_directories(
        root,
        root_identity=root_identity,
        directory_identities={"reports": reports_identity},
        actual_directories={"reports": reports},
    )
    assert not stray.exists()

    removable = root / "removable"
    removable.touch()
    package_publication._remove_reparse_node(removable, removable.lstat())
    assert not removable.exists()


def test_publication_final_identity_checks_fail_closed_at_each_observation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: PurePath,
) -> None:
    with pytest.raises(TypeError, match="rendered_authority_package_required"):
        package_publication.publish_rendered_package(object(), tmp_path / "out")  # type: ignore[arg-type]

    root = tmp_path / "publication-final-edges"
    reports = root / "reports"
    reports.mkdir(parents=True)
    target = reports / "row.json"
    target.write_bytes(b"{}")
    root_identity = package_publication._directory_identity(root)
    reports_identity = package_publication._directory_identity(reports)
    target_identity = package_publication._node_identity(target.lstat())
    fake_rendered = SimpleNamespace(
        artifacts=SimpleNamespace(file_names=lambda: ("reports/row.json",))
    )

    with pytest.raises(ValueError, match="published_package_artifact_identity_mismatch"):
        package_publication._verify_owned_identities(
            fake_rendered,
            root,
            root_identity=root_identity,
            file_identities={"reports/row.json": target_identity},
            directory_identities={"reports": (0, 0)},
        )
    with pytest.raises(ValueError, match="published_package_artifact_identity_mismatch"):
        package_publication._verify_owned_identities(
            fake_rendered,
            root,
            root_identity=root_identity,
            file_identities={},
            directory_identities={"reports": reports_identity},
        )
    with pytest.raises(ValueError, match="published_package_artifact_identity_mismatch"):
        package_publication._verify_owned_identities(
            fake_rendered,
            root,
            root_identity=root_identity,
            file_identities={"reports/row.json": (0, 0)},
            directory_identities={"reports": reports_identity},
        )

    artifact = package_publication.AuthorityArtifact.from_content(
        relative_path="reports/row.json", content=b"{}"
    )
    common = {
        "root_identity": root_identity,
        "expected_identity": target_identity,
        "directory_identities": {"reports": reports_identity},
        "actual_directories": {"reports": reports},
    }
    real_target_lookup = package_publication._actual_artifact_target
    monkeypatch.setattr(
        package_publication,
        "_actual_artifact_target",
        lambda *_args, **_kwargs: None,
    )
    assert package_publication._verified_owned_regular_file(
        root, artifact, **common
    ) is None
    monkeypatch.setattr(
        package_publication, "_actual_artifact_target", real_target_lookup
    )

    real_fstat = package_publication.os.fstat
    monkeypatch.setattr(
        package_publication.os,
        "fstat",
        lambda _descriptor: SimpleNamespace(
            st_mode=stat.S_IFDIR, st_dev=0, st_ino=0
        ),
    )
    assert package_publication._verified_owned_regular_file(
        root, artifact, **common
    ) is None
    monkeypatch.setattr(package_publication.os, "fstat", real_fstat)

    lookups = iter((target, None))
    monkeypatch.setattr(
        package_publication,
        "_actual_artifact_target",
        lambda *_args, **_kwargs: next(lookups),
    )
    assert package_publication._verified_owned_regular_file(
        root, artifact, **common
    ) is None

    monkeypatch.setattr(
        package_publication,
        "_actual_artifact_target",
        lambda *_args, **_kwargs: target,
    )
    path_type = type(target)
    real_lstat = path_type.lstat
    target_lstat_calls = 0

    def changing_lstat(path: object) -> object:
        nonlocal target_lstat_calls
        if path == target:
            target_lstat_calls += 1
            if target_lstat_calls > 1:
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_dev=0, st_ino=0)
        return real_lstat(path)  # type: ignore[arg-type]

    monkeypatch.setattr(path_type, "lstat", changing_lstat)
    assert package_publication._verified_owned_regular_file(
        root, artifact, **common
    ) is None

    staging = root / "staging"
    staging.mkdir()
    package_publication._remove_staging_tree(
        fake_rendered,
        staging,
        parent=root,
        root_identity=None,
        file_identities={},
        directory_identities={},
    )
    assert staging.is_dir()

    removed: list[bool] = []
    fake_path = SimpleNamespace(
        unlink=lambda: removed.append(True),
        rmdir=lambda: removed.append(False),
    )
    real_islink = package_publication.stat.S_ISLNK
    monkeypatch.setattr(package_publication.stat, "S_ISLNK", lambda _mode: True)
    package_publication._remove_reparse_node(
        fake_path, SimpleNamespace(st_mode=0)
    )
    monkeypatch.setattr(package_publication.stat, "S_ISLNK", real_islink)
    assert removed == [True]


def test_config_quality_declared_surfaces_prefer_typed_ledger_then_disposition() -> None:
    package = _quality_package_root(
        {
            "reports/runtime_surface_ledger.json": {
                "cards": {
                    "bad": "invalid",
                    "CARD_001": {"runtime_surfaces": ["CARD_001.json", "Combo.json"]},
                },
                "linked_runtime_entities": {
                    "bad": "invalid",
                    "NOT_EMITTED": {"runtime_emitted": False},
                    "CARD_002": {"runtime_emitted": True, "runtime_surface": ""},
                    "CARD_003": {
                        "runtime_emitted": True,
                        "runtime_surface": "Combo.json",
                    },
                },
            }
        }
    ).package
    inputs = SimpleNamespace(package=package, disposition_ledger={})
    assert config_quality_checks._declared_runtime_surfaces(inputs) == {
        "CARD_001.json",
        "CARD_002.json",
    }

    fallback = SimpleNamespace(
        package=_quality_package_root({}).package,
        disposition_ledger={
            "cards": [
                {"runtime_paths": ["CARD_004.json", "Combo.json", ""]},
                "invalid",
            ]
        },
    )
    assert config_quality_checks._declared_runtime_surfaces(fallback) == {
        "CARD_004.json"
    }


def test_config_quality_arc_specific_empty_and_malformed_rows_are_ignored() -> None:
    assert config_quality_checks.semantic_handoff_projection(
        {
            "checks": {
                "runtime_row_trace_inventory": "invalid",
                "visionai_semantic_surface": "invalid",
            }
        }
    )["semantic_handoff_status"] == "closed"
    assert config_quality_checks._traced_card_ids(
        {
            "card_rows": [
                {
                    "source_lane": "deck_matched_public_guide",
                    "emitted_runtime_files": ["CARD_005.json"],
                }
            ]
        }
    ) == {"CARD_005"}
    assert config_quality_checks._runtime_row_claim_ids(
        {"source_claim_ids": [""]}
    ) == set()
    assert config_quality_checks._deck_identity_card_ids(
        {"sideboards": "invalid"}
    ) == set()

    discipline = config_quality_checks._mechanic_runtime_discipline_check(
        {
            "rows": [
                {
                    "card_id": "CARD_001",
                    "surface_family": "CARDID.json",
                    "behavior_block": "OnBoardBonus",
                    "mechanic_families": ["future_unregistered_mechanic"],
                }
            ]
        }
    )
    assert discipline["status"] == "attention"
    assert discipline["unregistered_mechanics"] == ["future_unregistered_mechanic"]


def test_config_quality_surface_role_and_source_metadata_skip_identityless_rows() -> None:
    roles = config_quality_checks._semantic_surface_roles_by_card(
        {
            "rows": [
                {
                    "surface_family": "CARDID.json",
                    "behavior_block": "OnBoardBonus",
                }
            ]
        },
        {
            "cards": [{"roles": ["engine"]}],
            "card_role_map": [{"roles": ["payoff"]}],
        },
        {"cards": [{"roles": ["draw"]}]},
    )
    assert roles == {}
    assert config_quality_checks._card_specific_source_metadata_cards(
        {
            "cards": [{"source_claim_ids": ["claim"]}],
            "card_role_map": [{"roles": ["engine"]}],
        },
        {"cards": [{"semantic_families": ["draw"]}]},
    ) == set()


def test_config_quality_public_guide_and_mulligan_acceptance_require_exact_links(
) -> None:
    refs = config_quality_checks._eligible_public_guide_source_refs(
        {
            "source_evidence_index": [
                {"missing_source_keys": ["url"], "source_ref": "missing"},
                {"source_family": "private", "source_ref": "private"},
                {
                    "source_family": "guide",
                    "source_url": "https://example.invalid",
                    "source_title": "Guide",
                    "retrieved_at": "2026-08-01",
                    "source_ref": "",
                },
            ]
        }
    )
    assert refs == set()
    assert not config_quality_checks._is_source_backed_opening_hand_claim(
        {"claim_readiness": "runtime_blocked"}, {"source"}
    )
    assert not config_quality_checks._is_source_backed_opening_hand_claim(
        {"claim_readiness": "guide_backed", "text": "play later"}, {"source"}
    )
    assert not config_quality_checks._is_source_backed_opening_hand_claim(
        {
            "claim_readiness": "guide_backed",
            "text": "keep in opening hand",
            "source_lane": "runtime_lowered",
            "source_ref": "source",
        },
        {"source"},
    )

    package = _quality_package_root(
        {"reports/mulligan_plan_report.json": []}
    )
    assert not config_quality_checks._mulligan_plan_accepts_claim(
        package,
        "CARD_001",
        {"claim"},
    )
    package = _quality_package_root(
        {
            "reports/mulligan_plan_report.json": {
                "rules": [
                    {"action": "discard", "card_id": "CARD_001", "claim_id": "claim"},
                    {"action": "hold", "card_id": "OTHER", "claim_id": "claim"},
                    {"action": "hold", "card_id": "CARD_001", "claim_id": "other"},
                ]
            }
        }
    )
    assert not config_quality_checks._mulligan_plan_accepts_claim(
        package,
        "CARD_001",
        {"claim"},
    )


def test_config_quality_attention_and_surface_intent_branch_edges() -> None:
    assert config_quality_checks._normal_apply_authority_drift(
        {"runtime_apply_contract": {}}
    ) is None
    assert not config_quality_checks._is_canonical_surface_intent_row(
        {"required_surfaces": ["nested/Combo.json"]},
        {"surface": "nested/Combo.json", "intent": "combo"},
    )
    assert not config_quality_checks._is_canonical_surface_intent_row(
        {"required_surfaces": ["Concede.json"]},
        {"surface": "Concede.json", "intent": "concede"},
    )
    assert config_quality_checks._surface_intent_runtime_files(
        {
            "required_surfaces": ["GlobalValues.json"],
            "rows": [
                {
                    "surface": "GlobalValues.json",
                    "intent": "",
                    "rule_id": "globalvalues_full_key_profile",
                }
            ],
        }
    ) == set()
    with pytest.raises(KeyError, match="source_to_runtime_explainability"):
        config_quality_checks._problems(
            {
                "operator_summary": {
                    "source_status_apply_blocking": True,
                    "default_only_runtime_surfaces": [],
                },
                "closure_freshness": {
                    "present": True,
                    "closure_schema_current": True,
                    "cards_missing_closure": 0,
                },
            }
        )


def test_source_acquisition_visible_text_respects_primary_and_excluded_content() -> None:
    parsed = source_acquisition.extract_visible_text(
        """
        <html><head><title> Deck Guide </title>
        <meta property="article:published_time" content="2026-08-01" /></head>
        <body>fallback <nav>excluded</nav><main>primary <time datetime="2026-08-02"></time></main></body></html>
        """
    )
    assert parsed == {
        "title": "Deck Guide",
        "text": "primary",
        "publication_values": ["2026-08-01", "2026-08-02"],
        "content_scope": "main_or_article",
    }
    fallback = source_acquisition.extract_visible_text(
        "<html><body> visible <script>hidden</script></body></html>"
    )
    assert fallback["text"] == "visible"
    assert fallback["content_scope"] == "visible_body_fallback"
    empty_dates = source_acquisition.extract_visible_text(
        '<meta property="article:published_time" content=""><time></time>'
    )
    assert empty_dates["publication_values"] == []


def test_source_acquisition_classifies_family_visibility_lane_and_kind() -> None:
    assert source_acquisition._infer_source_family("https://hsguru.com/deck", "") == "stats"
    assert source_acquisition._infer_source_family("https://example.com/decklist", "") == "decklist"
    assert source_acquisition._infer_source_family("https://example.com/guide", "mulligan") == "guide"
    assert source_acquisition._infer_source_family("https://example.com", "not a guide") == "public_page"
    assert source_acquisition._infer_source_family("https://example.com", "aggregate statistics") == "stats"
    assert source_acquisition._infer_source_family("https://example.com", "deck code") == "decklist"

    assert source_acquisition._source_visibility("decklist", "") == "decklist_only"
    assert source_acquisition._source_visibility("stats", "") == "stats_only"
    assert source_acquisition._source_visibility("guide", "short") == "snippet_only"
    assert source_acquisition._source_visibility("guide", "mulligan " * 30) == "full_text"
    assert source_acquisition._source_visibility("public_page", "plain " * 40) == "unknown"

    for family, visibility, expected in (
        ("guide", "full_text", "public_guide"),
        ("decklist", "full_text", "decklist"),
        ("stats", "full_text", "stats"),
        ("static_semantics", "full_text", "static_semantics"),
        ("public_page", "snippet_only", "unknown"),
        ("public_page", "full_text", "public_page"),
    ):
        assert source_acquisition._source_lane_hint(family, visibility) == expected

    for family, visibility, expected in (
        ("decklist", "full_text", "decklist"),
        ("stats", "full_text", "stats"),
        ("guide", "snippet_only", "snippet"),
        ("guide", "full_text", "guide"),
        ("static_semantics", "full_text", "static_semantics"),
        ("public_page", "full_text", "public_page"),
    ):
        assert source_acquisition._source_document_kind(family, visibility) == expected
    assert source_acquisition._source_category(
        "static_semantics",
        "full_text",
        "unknown",
    ) == "static_semantics"
    assert source_acquisition._source_category(
        "public_page",
        "snippet_only",
        "unknown",
    ) == "diagnostic"


def test_source_acquisition_dates_urls_and_redaction_are_canonical() -> None:
    assert source_acquisition._publication_year_from_metadata(
        ["no date", "published 2025", "future 2027"], current_date="2026-08-01"
    ) == 2025
    assert source_acquisition._publication_year_from_metadata(
        ["future 2027"], current_date="2026-08-01"
    ) is None
    assert source_acquisition._current_year(date(2026, 8, 1)) == 2026
    assert source_acquisition._current_year("2025-01-01") == 2025
    assert source_acquisition._dedupe_urls([" a ", "a", "", "b"]) == ["a", "b"]
    assert source_acquisition.fetchable_source_url(
        "https://www.reddit.com/r/test/comments/abc/post"
    ).startswith("https://old.reddit.com/")
    assert source_acquisition.fetchable_source_url(
        "https://reddit.com/r/test/comments/abc/post.json"
    ).startswith("https://reddit.com/")
    nested = source_acquisition._redact_persisted_deckstrings(
        {"rows": ("AAECA" + ("A" * 50), ["plain"])}
    )
    assert isinstance(nested["rows"], tuple)


def test_source_acquisition_url_validation_rejects_local_and_invalid_dns() -> None:
    assert source_acquisition._public_source_url_validation(
        "http://example.com", resolver=lambda host: ["8.8.8.8"]
    ) == ("non_public_https_url", ())
    assert source_acquisition._public_source_url_validation(
        "https://localhost/path", resolver=lambda host: ["8.8.8.8"]
    ) == ("non_public_https_url", ())
    assert source_acquisition._public_source_url_validation(
        "https://127.0.0.1/path", resolver=lambda host: ["8.8.8.8"]
    ) == ("non_public_https_url", ())
    assert source_acquisition._public_source_url_validation(
        "https://8.8.8.8/path", resolver=lambda host: []
    ) == (None, ("8.8.8.8",))
    assert source_acquisition._hostname_validation_result(
        "example.com", lambda host: []
    ) == ("dns_resolution_failed", ())
    assert source_acquisition._hostname_validation_result(
        "example.com", lambda host: ["invalid"]
    ) == ("dns_resolution_failed", ())
    assert source_acquisition._hostname_validation_result(
        "example.com", lambda host: ["127.0.0.1"]
    ) == ("non_public_https_url", ())
    assert source_acquisition._hostname_validation_result(
        "example.com", lambda host: ["8.8.8.8"]
    ) == (None, ("8.8.8.8",))
    assert source_acquisition._hostname_validation_result(
        "example.com", lambda host: (_ for _ in ()).throw(OSError())
    ) == ("dns_resolution_failed", ())

    assert source_acquisition._location_from_content_type("text/html") == ""
    assert source_acquisition._location_from_content_type(
        "text/html; location=https://example.com/path"
    ) == "https://example.com/path"
    assert source_acquisition._redirect_validation_error(
        "text/html", resolver=lambda host: ["8.8.8.8"]
    ) is None
    assert source_acquisition._redirect_validation_error(
        "text/html; location=http://localhost", resolver=lambda host: []
    ) == "redirect_target_non_public_https_url"
    assert source_acquisition._redirect_validation_error(
        "text/html; location=https://example.com/path",
        resolver=lambda host: ["8.8.8.8"],
    ) is None


def test_source_acquisition_fetch_boundaries_reject_invalid_or_nontext_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid = source_acquisition.collect_public_source_records(
        deck_name="Deck",
        deck_identity={"cards": []},
        source_urls=["http://localhost"],
        current_date="2026-08-01",
        resolver=lambda _host: [],
        fetcher=lambda _url, _timeout: (200, "text/html", b"ok"),
    )
    assert invalid["source_acquisition_report"]["failures"][0]["error"] == (
        "non_public_https_url"
    )

    nontext = source_acquisition.collect_public_source_records(
        deck_name="Deck",
        deck_identity={"cards": []},
        source_urls=["https://example.com/image"],
        current_date="2026-08-01",
        resolver=lambda _host: ["8.8.8.8"],
        fetcher=lambda _url, _timeout: (200, "image/png", b"png"),
    )
    assert nontext["source_acquisition_report"]["failures"][0]["error"] == (
        "unsupported_content_type:image/png"
    )

    monkeypatch.setattr(
        source_acquisition,
        "_public_source_url_validation",
        lambda _url, resolver: ("blocked", ()),
    )
    with pytest.raises(ValueError, match="blocked"):
        source_acquisition._default_fetcher("https://example.com", 1.0)
    with pytest.raises(ValueError, match="non_public_https_url"):
        source_acquisition._fetch_with_validated_address(
            "http://example.com",
            1.0,
            "8.8.8.8",
        )
    assert source_acquisition._iso_datetime(date(2026, 8, 1)).startswith(
        "2026-08-01T00:00:00"
    )


def test_source_acquisition_card_overlap_and_missing_action_are_stable() -> None:
    deck = {
        "cards": [
            "invalid",
            {"card_id": "CARD_001", "name": "First Card"},
            {"card_id": "", "name": "No Id"},
        ]
    }
    assert source_acquisition._matched_card_ids(deck, "play First Card") == ["CARD_001"]
    evidence, scope = source_acquisition._deck_match_evidence(
        "Fixture Deck", deck, "Fixture Deck guide", "play First Card"
    )
    assert scope == "card_overlap"
    assert evidence["matched_card_count"] == 1
    unknown, scope = source_acquisition._deck_match_evidence(
        "", {"cards": []}, "", ""
    )
    assert scope == "unknown"
    assert unknown["card_overlap_ratio"] == 0.0
    assert source_acquisition._report_first_missing_source_action([]) == (
        "add_public_guide_url_or_use_static_semantics"
    )
    assert source_acquisition._report_first_missing_source_action(
        [{"first_missing_source_action": "none"}]
    ) == "none"
    assert source_acquisition._report_first_missing_source_action(
        [{"first_missing_source_action": "research"}]
    ) == "research"


def test_explainability_disposition_and_ledger_helpers_project_physical_truth() -> None:
    assert source_to_runtime_explainability._claim_disposition_fields(None) == {}
    assert source_to_runtime_explainability._card_disposition_fields(None) == {}
    rows = [{"claim_id": "claim", "emitted_runtime_files": ["CARD_001.json"]}]
    assert source_to_runtime_explainability._apply_runtime_surface_ledger_to_claim_rows(
        rows,
        {},
        None,
    ) is rows
    projected = source_to_runtime_explainability._apply_runtime_surface_ledger(
        [
            {
                "card_id": "CARD_001",
                "strongest_claim_id": "claim",
                "strongest_claim_kind": "card_role",
                "runtime_eligible": True,
                "emitted_runtime_files": ["CARD_001.json", "CARD_001.json"],
                "not_emitted_runtime_files": ["CARD_001.json", "CARD_002.json"],
                "strong_ready": True,
                "closure": {"claim_kinds": ["card_role"], "source_lanes": ["runtime_lowered"]},
            },
            {
                "card_id": "CARD_002",
                "runtime_eligible": False,
                "emitted_runtime_files": [],
            },
        ],
        {"cards": {"CARD_001": {"runtime_surfaces": ["CARD_001.json"]}}},
    )
    assert projected[0]["runtime_lowering_status"] == "source_backed_runtime"
    assert projected[0]["not_emitted_runtime_files"] == ["CARD_002.json"]
    assert projected[1]["runtime_lowering_status"] == "report_only_supported"
    assert projected[1]["first_missing_link"] == "none"

    assert source_to_runtime_explainability._linked_files_by_source("invalid") == {}
    assert source_to_runtime_explainability._linked_files_by_source(
        {
            "bad": "invalid",
            "not-emitted": {"runtime_emitted": False},
            "missing": {"runtime_emitted": True},
            "linked": {
                "runtime_emitted": True,
                "source_card_id": "CARD_001",
                "runtime_surface": "HERO_POWER.json",
            },
        }
    ) == {"CARD_001": ["HERO_POWER.json"]}


def test_explainability_claim_physical_files_validate_each_runtime_family() -> None:
    function = source_to_runtime_explainability._claim_physical_files
    assert function(
        raw_claim={"claim_kind": "mulligan_keep", "cards": ["CARD_001"]},
        expected_files=["Mulligan.json"],
        physical_files=["Mulligan.json"],
        ledger={},
    ) == ["Mulligan.json"]
    assert function(
        raw_claim={"claim_kind": "mulligan_keep", "selector": "unsupported selector"},
        expected_files=["Mulligan.json"],
        physical_files=["Mulligan.json"],
        ledger={"mulligan": {"rules": []}},
    ) == []
    assert function(
        raw_claim={"claim_kind": "combo_sequence", "cards": ["A", "B"]},
        expected_files=["Combo.json"],
        physical_files=["Combo.json"],
        ledger={},
    ) == ["Combo.json"]
    assert function(
        raw_claim={"claim_kind": "combo_sequence", "cards": ["A", "B"]},
        expected_files=["Combo.json"],
        physical_files=["Combo.json"],
        ledger={"combo": {"rows": ["A >> B"]}},
    ) == ["Combo.json"]
    assert function(
        raw_claim={"claim_kind": "gameplan_posture", "key": "Aggro"},
        expected_files=["GlobalValues.json"],
        physical_files=["GlobalValues.json"],
        ledger={"globalvalues": {"changed_keys": ["Aggro"]}},
    ) == ["GlobalValues.json"]
    assert function(
        raw_claim={},
        expected_files=["CARD_001.json"],
        physical_files=["CARD_001.json"],
        ledger={"cardid": {"entities": []}},
    ) == []
    assert function(
        raw_claim={},
        expected_files=["Presume.json"],
        physical_files=["Presume.json", "Other.json"],
        ledger={},
    ) == ["Presume.json"]


def test_explainability_selector_combo_mapping_and_evidence_chain_helpers() -> None:
    assert source_to_runtime_explainability._mulligan_rule_selector_identity(
        {"selector_kind": "card", "selector_cards": ["CARD_001"]}
    ) == ("card", ("CARD_001",))
    assert source_to_runtime_explainability._mulligan_rule_selector_identity(
        {"mulligan": "unsupported selector"}
    ) == ("", ())
    assert source_to_runtime_explainability._mapping_dict("invalid") == {}
    assert source_to_runtime_explainability._combo_row_identity("A >-> B") == {
        "operator": ">->",
        "cards": ["A", "B"],
    }
    assert source_to_runtime_explainability._combo_row_identity("invalid") == {
        "operator": "",
        "cards": [],
    }
    assert source_to_runtime_explainability._ledger_evidence_chain(
        "invalid", [], None
    ) == []
    assert source_to_runtime_explainability._ledger_evidence_chain(
        ["invalid", {"source_lane": "D"}], ["CARD_001.json"], None
    ) == [
        {
            "source_lane": "D",
            "runtime_files": ["CARD_001.json"],
            "runtime_surface": "cardid",
            "resolution_reason": "emitted",
        }
    ]


def test_explainability_operator_attention_and_compact_audit_cover_all_lanes() -> None:
    for row, expected in (
        ({"runtime_eligible": False}, "report_only"),
        ({"first_missing_link": "source"}, "source_action_needed"),
        ({"emitted_runtime_files": ["A.json"]}, "runtime_backed"),
        ({}, "baseline_only_visible"),
        ({"strongest_claim_id": "claim", "best_source_lane": "report_only"}, "diagnostic_only"),
    ):
        assert source_to_runtime_explainability._operator_attention_status(row) == expected

    compact = source_to_runtime_explainability._normalized_audit(
        {
            "claim_rows": [
                "invalid",
                {"card_id": ""},
                {
                    "card_id": "CARD_001",
                    "claim_kind": "mulligan_keep",
                    "runtime_backed": "true",
                    "claim_lanes": "invalid",
                },
                {
                    "card": "CARD_001",
                    "claim_id": "claim-2",
                    "claim_kind": "combo_sequence",
                },
            ]
        },
        runtime_files={"Mulligan.json"},
    )
    assert set(compact["claim_rows"]) == {"claim_3", "claim-2"}
    assert len(compact["claim_lifecycle_rows"]) == 2
    assert source_to_runtime_explainability._normalized_audit(None, runtime_files=None) == {}
    assert source_to_runtime_explainability._runtime_surfaces_from_files(
        ["Mulligan.json", "Combo.json", "GlobalValues.json", "CARD_001.json", "note.txt"]
    ) == ["cardid", "combo", "globalvalues", "mulligan"]
    assert source_to_runtime_explainability._compact_source_lane(
        {"source_type": "versioned_internal_policy"}
    ) == "versioned_internal_policy"


def test_explainability_claim_ranking_expected_files_and_closure_boundaries() -> None:
    assert source_to_runtime_explainability._matching_claim([], None) is None
    assert source_to_runtime_explainability._matching_claim(
        [{"claim_id": "one"}], "missing"
    ) is None
    assert source_to_runtime_explainability._strongest_claim_id(
        ["invalid"], {"invalid": "not-a-row"}
    ) is None
    assert source_to_runtime_explainability._strongest_claim_id(
        ["low", "high"],
        {
            "low": {"lane": "report_only", "claim_kind": "card_role"},
            "high": {"lane": "runtime_lowered", "claim_kind": "card_role"},
        },
    ) == "high"
    assert source_to_runtime_explainability._best_source_lane(
        {"claim_lanes": {"report_only": 1, "runtime_lowered": 1}}, None, {}
    ) == "runtime_lowered"
    assert source_to_runtime_explainability._best_source_lane(
        {}, "claim", {"claim": {"lane": "deck_matched_public_guide"}}
    ) == "deck_matched_public_guide"

    assert source_to_runtime_explainability._card_expected_runtime_files(
        "CARD_001", None
    ) == []
    assert source_to_runtime_explainability._card_expected_runtime_files(
        "CARD_001",
        {
            "runtime_entity_owners": [
                {
                    "source_card_id": "CARD_001",
                    "runtime_card_id": "HERO_POWER",
                }
            ]
        },
    ) == ["HERO_POWER.json"]
    assert source_to_runtime_explainability._card_expected_runtime_files(
        "CARD_001", {"claim_kind": "mulligan_keep"}
    ) == ["Mulligan.json"]
    assert source_to_runtime_explainability._card_expected_runtime_files(
        "CARD_001", {"claim_kind": "combo_sequence", "cards": ["A"]}
    ) == []

    assert not source_to_runtime_explainability._combo_claim_is_runtime_lowerable(
        {"suppressed_reason": "blocked"}
    )
    assert source_to_runtime_explainability._combo_claim_is_runtime_lowerable(
        {"runtime_lowering_status": "emitted"}
    )
    assert source_to_runtime_explainability._combo_claim_is_runtime_lowerable(
        {"runtime_surface": "Combo.json"}
    )
    assert source_to_runtime_explainability._combo_claim_is_runtime_lowerable(
        {"timing_kind": "ordered", "cards": ["A", "B"]}
    )

    assert not source_to_runtime_explainability._is_source_backed_strong_claim(
        {"builder_or_router_decision": "physical_partial"}
    )
    assert source_to_runtime_explainability._is_source_backed_strong_claim(
        {"promotion_eligible": True}
    )
    assert not source_to_runtime_explainability._is_source_backed_strong_claim(
        {"source_type": "versioned_internal_policy"}
    )


def test_explainability_collection_helpers_fail_closed_on_malformed_rows() -> None:
    assert source_to_runtime_explainability._apply_runtime_surface_ledger_to_claim_rows(
        [],
        {"cards": [], "linked_runtime_entities": []},
        {"claim_rows": {}},
    ) == []
    assert source_to_runtime_explainability._apply_runtime_surface_ledger(
        [], {"cards": []}
    ) == []
    assert source_to_runtime_explainability._claim_rows(
        {"claim_lifecycle_rows": "invalid", "claim_rows": []}
    ) == []
    assert source_to_runtime_explainability._claim_rows(
        {"claim_lifecycle_rows": ["invalid"], "claim_rows": []}
    ) == []
    assert source_to_runtime_explainability._card_rows(
        {"claim_rows": [], "card_rows": {}}, []
    ) == []
    assert source_to_runtime_explainability._card_rows(
        {
            "claim_rows": {"bad": "invalid", "good": {"cards": ["CARD_001"]}},
            "card_rows": {"CARD_000": "invalid", "CARD_001": {}},
        },
        [],
    )[0]["card_id"] == "CARD_001"
    assert source_to_runtime_explainability._audit_from_compact_claim_rows(
        {"claim_rows": "invalid"}, runtime_files=None
    )["claim_rows"] == {}
    assert source_to_runtime_explainability._runtime_entity_transitions(
        {"rows": "invalid"}
    ) == []
    assert source_to_runtime_explainability._runtime_entity_transitions(
        {"rows": ["invalid"]}
    ) == []


def test_explainability_claim_rows_project_multiple_owners_and_behaviors() -> None:
    audit = {
        "claim_lifecycle_rows": [
            {
                "claim_id": "claim",
                "claim_kind": "mulligan_keep",
                "emitted_files": ["SOURCE.json"],
                "condition": "unsupported condition",
            },
            {"claim_id": "plain", "claim_kind": "card_role"},
        ],
        "claim_rows": {
            "claim": {
                "condition": "unsupported condition",
                "source_lane": ["one", "two"],
            },
            "plain": "invalid",
        },
    }
    ownerships = {
        "claim": [
            {
                "source_card_id": "SOURCE",
                "runtime_card_id": "ONE",
                "link_kind": "transform",
                "runtime_file": "ONE.json",
            },
            {
                "source_card_id": "SOURCE",
                "runtime_card_id": "TWO",
                "link_kind": "transform",
                "runtime_file": "TWO.json",
            },
        ]
    }
    behaviors = {
        "claim": [
            {
                "behavior_block": "first",
                "source_card_id": "SOURCE",
                "runtime_card_id": "ONE",
                "link_kind": "transform",
            },
            {
                "behavior_block": "second",
                "source_card_id": "SOURCE",
                "runtime_card_id": "TWO",
                "link_kind": "transform",
            },
        ]
    }

    rows = source_to_runtime_explainability._claim_rows(
        audit,
        ownership_by_claim_id=ownerships,
        behavior_by_claim_id=behaviors,
    )

    assert len(rows[0]["runtime_entity_owners"]) == 2
    assert len(rows[0]["behavior_identities"]) == 2
    assert rows[0]["condition"] == "unsupported condition"
    assert rows[0]["source_lane"] == ["one", "two"]


def test_explainability_source_metadata_and_fallback_helpers_cover_absent_metadata() -> None:
    assert source_to_runtime_explainability._related_claims_with_source_lanes(
        [{"claim_id": "missing"}], {"missing": "invalid"}
    ) == [{"claim_id": "missing"}]
    assert source_to_runtime_explainability._related_claims_with_source_metadata(
        [{"claim_id": "missing"}], {"missing": "invalid"}
    ) == [{"claim_id": "missing"}]
    assert source_to_runtime_explainability._related_claims_with_source_metadata(
        [{"claim_id": "claim"}],
        {"claim": {"source_type": "", "source_lane": "", "runtime_backed": "false"}},
    ) == [{"claim_id": "claim", "runtime_backed": False}]
    assert source_to_runtime_explainability._best_source_lane(
        {}, "claim", {"claim": "invalid"}
    ) == "report_only"
    assert source_to_runtime_explainability._operator_attention_status(
        {"strongest_claim_id": "claim", "best_source_lane": "source", "why_not_emitted": "other"}
    ) == "baseline_only_visible"
    assert source_to_runtime_explainability._card_expected_runtime_files(
        "CARD_001", {"claim_kind": "combo_sequence", "cards": ["A"]}
    ) == []


def test_configure_workflow_small_normalizers_fail_closed_at_input_edges(
    tmp_path: PurePath,
) -> None:
    assert configure_workflow._first_source_status_reason(
        {"source_status_reasons": ["first", "second"]}
    ) == "first"
    assert configure_workflow._first_source_status_reason(
        {"source_status_reasons": "invalid"}
    ) == ""
    today = date.today()
    assert configure_workflow._normalize_operator_date(today) is today
    with pytest.raises(ValueError, match="current_date_invalid"):
        configure_workflow._normalize_operator_date("not-a-date")

    assert not configure_workflow._source_candidate_plan_is_usable([], [])
    assert not configure_workflow._source_candidate_plan_is_usable(
        {
            "authority": "diagnostic_source_candidate_plan",
            "candidate_urls": [],
            "source_urls": "invalid",
        },
        [],
    )
    assert not configure_workflow._source_candidate_plan_is_usable(
        {
            "authority": "diagnostic_source_candidate_plan",
            "candidate_urls": [1],
            "source_urls": [],
        },
        [],
    )
    assert configure_workflow._plan_urls({}, "candidate_urls") == []
    assert configure_workflow._raw_plan_candidate_row_urls({}) == []
    assert configure_workflow._source_search_records(None) == []

    invalid_records = tmp_path / "invalid-records.json"
    invalid_records.write_text('{"records": {}}', encoding="utf-8")
    assert configure_workflow._source_search_records(invalid_records) == []
    assert configure_workflow._dedupe_preserve_order(
        [" one ", "", "one", "two"]
    ) == ["one", "two"]


def test_configure_workflow_compact_summaries_cover_malformed_optional_blocks() -> (
    None
):
    compact = configure_workflow._compact_config_quality_summary(
        {
            "problems": ["invalid", {"check": "quality"}],
            "checks": {
                "darkbishop_boundary": {
                    "mulligan_keep_present": True,
                    "effect_runtime_present": True,
                },
                "source_to_runtime_explainability": {"present": False},
            },
        }
    )
    assert compact["problem_checks"] == ["quality"]
    assert compact["darkbishop_boundary_status"] == "mulligan_keep_present"
    assert compact["source_to_runtime_status"] == "missing"

    without_checks = configure_workflow._compact_config_quality_summary(
        {"checks": []}
    )
    assert without_checks["problem_count"] == 0

    acceptance = configure_workflow._build_acceptance_summary(
        operator_summary={"runtime_apply_contract": []},
        apply_requested=False,
        apply_status=None,
        config_quality_summary={},
    )
    assert acceptance["normal_apply_authority"] == "reports/operator_summary.json"

    proof = configure_workflow._build_config_proof_summary(
        operator_summary={
            "runtime_apply_contract": [],
            "mechanic_visibility_summary": [],
        },
        validate_status=0,
        apply_requested=False,
        apply_status=None,
        config_quality_summary={"legacy_surfaces_present": []},
    )
    assert proof["forbidden_normal_surfaces_status"] == "clean"

    handoff = configure_workflow._build_handoff_contract(
        operator_summary={"runtime_apply_contract": []},
        acceptance_summary={},
        config_proof_summary={},
        config_quality_summary={},
    )
    assert handoff["normal_apply_authority"] == "reports/operator_summary.json"


_SEMANTIC_FIXTURE_ROOT = (
    Path(__file__).parent / "fixtures" / "near100"
)
_AUDITED_CATALOG_PATH = (
    Path(__file__).parents[1]
    / "docs"
    / "operator"
    / "audited-deck-catalog.json"
)


def _semantic_inventory_inputs() -> tuple[dict[str, object], list[object]]:
    inventory = json.loads(
        (_SEMANTIC_FIXTURE_ROOT / "current_semantic_inventory.json").read_text(
            encoding="utf-8"
        )
    )
    catalog = json.loads(
        _AUDITED_CATALOG_PATH.read_text(encoding="utf-8")
    )["decks"]
    return inventory, catalog


def _refresh_semantic_inventory_checksum(
    inventory: dict[str, object],
) -> None:
    content = {
        key: value
        for key, value in inventory.items()
        if key != "canonical_content_sha256"
    }
    canonical = json.dumps(content, separators=(",", ":"), sort_keys=True)
    inventory["canonical_content_sha256"] = hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


@pytest.mark.parametrize(
    ("case", "message"),
    (
        ("schema", "semantic_inventory_schema_invalid"),
        ("catalog_mismatch", "semantic_inventory_catalog_mismatch"),
        ("catalog_duplicate", "semantic_inventory_deck_identity_invalid"),
        ("deck_claim_count", "semantic_inventory_deck_claim_count_invalid"),
        ("checksum_shape", "semantic_inventory_content_sha256_invalid"),
        ("catalog_row", "semantic_inventory_deck_identity_invalid"),
        ("catalog_fields", "semantic_inventory_deck_identity_invalid"),
        ("deck_row", "semantic_inventory_deck_row_invalid"),
        ("fingerprint", "semantic_inventory_fingerprint_invalid"),
        ("claim_row", "semantic_inventory_claim_identity_invalid"),
        ("claim_key", "semantic_inventory_claim_identity_invalid"),
        ("card_row", "semantic_inventory_main_cards_invalid"),
        ("deck_rows", "semantic_inventory_deck_row_invalid"),
        ("required_string", "semantic_inventory_schema_invalid"),
    ),
)
def test_semantic_inventory_rejects_each_malformed_domain_boundary(
    case: str,
    message: str,
) -> None:
    inventory, catalog = _semantic_inventory_inputs()
    decks = inventory["decks"]
    assert isinstance(decks, list)
    first_deck = decks[0]
    assert isinstance(first_deck, dict)
    claims = first_deck["claims"]
    main_cards = first_deck["main_cards"]
    assert isinstance(claims, list)
    assert isinstance(main_cards, list)
    assert case in {
        "schema",
        "catalog_mismatch",
        "catalog_duplicate",
        "deck_claim_count",
        "checksum_shape",
        "catalog_row",
        "catalog_fields",
        "deck_row",
        "fingerprint",
        "claim_row",
        "claim_key",
        "card_row",
        "deck_rows",
        "required_string",
    }

    if case == "schema":
        inventory["schema_version"] = 2
    elif case == "catalog_mismatch":
        assert isinstance(catalog[0], dict)
        catalog[0]["deck_name"] = "DifferentDeck"
    elif case == "catalog_duplicate":
        second_deck = decks[1]
        assert isinstance(second_deck, dict)
        assert isinstance(catalog[0], dict)
        assert isinstance(catalog[1], dict)
        second_deck["deck_name"] = first_deck["deck_name"]
        catalog[1]["deck_name"] = catalog[0]["deck_name"]
    elif case == "deck_claim_count":
        claims.pop()
    elif case == "checksum_shape":
        inventory["canonical_content_sha256"] = None
    elif case == "catalog_row":
        catalog[0] = None
    elif case == "catalog_fields":
        assert isinstance(catalog[0], dict)
        catalog[0]["deck_name"] = ""
    elif case == "deck_row":
        first_deck.pop("globalvalues_decisions")
    elif case == "fingerprint":
        first_deck["deck_fingerprint"] = "0" * 64
    elif case == "claim_row":
        assert isinstance(claims[0], dict)
        claims[0]["unexpected"] = True
    elif case == "claim_key":
        assert isinstance(claims[0], dict)
        claims[0]["claim_key"] = "noncanonical-but-unique"
    elif case == "card_row":
        assert isinstance(main_cards[0], dict)
        main_cards[0]["unexpected"] = True
    elif case == "deck_rows":
        inventory["decks"] = {}
    elif case == "required_string":
        first_deck["deck_name"] = None

    if case != "checksum_shape":
        _refresh_semantic_inventory_checksum(inventory)
    with pytest.raises(ValueError, match=message):
        semantic_inventory.validate_semantic_inventory(
            inventory,
            audited_catalog=catalog,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "case",
    (
        "not_mapping",
        "blank_required_string",
        "string_collection",
        "non_string_collection_member",
        "wrong_existing_identity",
    ),
)
def test_canonical_semantic_claim_rejects_noncanonical_claim_shapes(
    case: str,
) -> None:
    raw: object = {
        "claim_kind": "card_role",
        "evidence_text_short": "Draw a card.",
        "cards": ["CARD_001"],
        "lowered_surfaces": ["cardid"],
        "source_title": "Fixture source",
    }
    if case == "not_mapping":
        raw = None
    else:
        assert isinstance(raw, dict)
        if case == "blank_required_string":
            raw["claim_kind"] = " "
        elif case == "string_collection":
            raw["cards"] = "CARD_001"
        elif case == "non_string_collection_member":
            raw["cards"] = [1]
        elif case == "wrong_existing_identity":
            raw["claim_key"] = "0" * 64

    with pytest.raises(ValueError, match="semantic_inventory_semantic_claim"):
        semantic_inventory.canonical_semantic_claim(  # type: ignore[arg-type]
            raw
        )


def test_semantic_inventory_rejects_a_non_thirty_card_catalog_deck() -> None:
    inventory, catalog = _semantic_inventory_inputs()
    catalog_row = catalog[0]
    assert isinstance(catalog_row, dict)
    parsed = _parse_deckstring(str(catalog_row["deck_code"]))
    cards = list(parsed["cards"])
    dbf_id, count = cards[0]
    if count == 1:
        cards.pop(0)
    else:
        cards[0] = (dbf_id, count - 1)
    catalog_row["deck_code"] = write_deckstring(
        cards,
        parsed["heroes"],
        parsed["format"],
        parsed["sideboards"],
    )
    decoded = decode_deck_code(str(catalog_row["deck_code"]))
    assert decoded["card_count_total"] == 29
    fingerprint = stable_deck_fingerprint(
        (str(card["card_id"]), int(card["count"]))
        for card in decoded["main_deck"]
    )
    decks = inventory["decks"]
    assert isinstance(decks, list)
    deck = decks[0]
    assert isinstance(deck, dict)
    deck["deck_fingerprint"] = fingerprint
    deck["main_cards"] = [
        {
            "card_id": str(card["card_id"]),
            "count": int(card["count"]),
            "composite_card_key": (
                f"{fingerprint}:main_deck:{card['card_id']}"
            ),
        }
        for card in decoded["main_deck"]
    ]

    with pytest.raises(
        ValueError,
        match="semantic_inventory_main_slot_count_invalid",
    ):
        semantic_inventory._validate_deck_row(deck, catalog_row)


def test_semantic_inventory_positive_count_primitive_rejects_bool_and_zero() -> None:
    for value in (False, 0):
        with pytest.raises(ValueError, match="semantic_inventory_schema_invalid"):
            semantic_inventory._required_positive_int(
                {"count": value},
                "count",
            )


def _write_runtime_match_deck(root: Path, config_dir: str) -> None:
    write_json(
        root / "CustomConfig" / config_dir / "GlobalValues.json",
        {"GameCardId": "GlobalValues"},
    )


def _write_runtime_match_manifest(
    package: Path,
    *,
    deck_name: str = "FixtureDeck",
) -> None:
    write_json(
        package / "reports" / "input_manifest.json",
        {
            "deck_name": deck_name,
            "deck_code": "fixture-code",
            "runtime_root": "unused",
        },
    )


def test_runtime_match_rejects_absent_or_ambiguous_package_config_roots(
    tmp_path: Path,
) -> None:
    missing_package = tmp_path / "missing-package"
    with pytest.raises(ValueError, match="Expected package CustomConfig"):
        runtime_package_match.build_runtime_package_match_report(
            package_root=missing_package,
            runtime_root=tmp_path / "unused-runtime",
        )

    ambiguous_package = tmp_path / "ambiguous-package"
    _write_runtime_match_deck(ambiguous_package, "first")
    _write_runtime_match_deck(ambiguous_package, "second")
    with pytest.raises(ValueError, match="exactly one package config directory"):
        runtime_package_match.build_runtime_package_match_report(
            package_root=ambiguous_package,
            runtime_root=tmp_path / "unused-runtime-two",
        )


def test_runtime_match_reports_an_absent_explicit_runtime_config(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    _write_runtime_match_deck(package, "fixture")
    _write_runtime_match_manifest(package)

    report = runtime_package_match.build_runtime_package_match_report(
        package_root=package,
        runtime_root=tmp_path / "absent-runtime",
        config_dir="fixture",
    )

    assert report["status"] == "mismatch"
    assert report["package_config_exists"] is True
    assert report["runtime_config_exists"] is False
    assert report["runtime_config_dir"] == "fixture"


@pytest.mark.skipif(
    os.name != "nt",
    reason="casefold collisions are a Windows filesystem contract",
)
def test_runtime_match_rejects_a_casefold_ambiguous_snapshot_directory() -> None:
    snapshot = BoundedFilesystemPackageView(
        files={},
        directories=("Fixture", "fixture"),
    )

    with pytest.raises(ValueError, match="filesystem_directory_name_ambiguous"):
        runtime_package_match._resolve_snapshot_directory_name(
            snapshot,
            "FIXTURE",
        )


def test_runtime_match_rejects_a_config_name_bound_to_a_plain_file(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    custom_config = package / "CustomConfig"
    custom_config.mkdir(parents=True)
    (custom_config / "fixture").write_bytes(b"not a directory")

    with pytest.raises(ValueError, match="filesystem_directory_invalid"):
        runtime_package_match.build_runtime_package_match_report(
            package_root=package,
            runtime_root=tmp_path / "runtime",
            logical_config_dir="fixture",
            runtime_config_dir="fixture",
        )


def test_runtime_match_rejects_a_deck_name_unsafe_for_ini_mapping(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    _write_runtime_match_deck(package, "fixture")
    _write_runtime_match_deck(runtime, "fixture")
    _write_runtime_match_manifest(package, deck_name="Unsafe=Deck")

    with pytest.raises(ValueError, match="not safe for deck_config.ini"):
        runtime_package_match.build_runtime_package_match_report(
            package_root=package,
            runtime_root=runtime,
            config_dir="fixture",
        )


def test_runtime_match_assertion_returns_the_verified_matching_report(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"
    _write_runtime_match_deck(package, "fixture")
    _write_runtime_match_deck(runtime, "fixture")
    _write_runtime_match_manifest(package)
    (runtime / "CustomConfig" / "deck_config.ini").write_text(
        "FixtureDeck=fixture\n",
        encoding="utf-8",
    )

    report = runtime_package_match.assert_runtime_matches_package(
        package_root=package,
        runtime_root=runtime,
        config_dir="fixture",
    )

    assert report["status"] == "matched"
    assert report["semantic_mismatch_count"] == 0


_AUDITED_BUILD_INPUTS_PATH = Path(
    "src/hsconfig/resources/audited_build_inputs.json"
)
_AUDITED_BUILD_RESOURCES_PATH = Path(
    "src/hsconfig/resources/audited_build_resources.json"
)


def _release_verification_materials() -> tuple[
    CanonicalBuildInputs,
    FrozenBuildResourceStore,
    str,
]:
    audited = load_audited_build_inputs(_AUDITED_BUILD_INPUTS_PATH)
    resources = load_audited_build_resource_store(
        _AUDITED_BUILD_RESOURCES_PATH,
        audited_inputs=audited,
    )
    inputs = audited.builds[0]
    deck_codes = {
        str(row["deck_name"]): str(row["deck_code"])
        for row in load_audited_deck_catalog()
    }
    return inputs, resources, deck_codes[inputs.deck_name]


def test_release_verification_rejects_divergent_cold_build_tree_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs, resources, deck_code = _release_verification_materials()
    left = (tmp_path / "first-cold-root").resolve()
    right = (tmp_path / "second-cold-root").resolve()
    left.mkdir()
    right.mkdir()
    real_write = release_verification.write_rendered_configure_run
    write_count = 0

    def write_with_second_tree_divergence(
        rendered: RenderedConfigureRun,
        destination: Path,
    ) -> None:
        nonlocal write_count
        real_write(rendered, destination)
        write_count += 1
        if write_count == 2:
            (destination / "unexpected-artifact.bin").write_bytes(b"diverged")

    monkeypatch.setattr(
        release_verification,
        "write_rendered_configure_run",
        write_with_second_tree_divergence,
    )

    with pytest.raises(ValueError, match="audited_build_tree_bytes_mismatch"):
        release_verification._verify_one_audited_deck(
            inputs=inputs,
            resource_store=resources,
            deck_code=deck_code,
            work_root_a=left,
            work_root_b=right,
        )

    assert write_count == 2


def test_release_verification_rejects_a_missing_runtime_fault_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs, resources, deck_code = _release_verification_materials()
    left = (tmp_path / "first-runtime-root").resolve()
    right = (tmp_path / "second-runtime-root").resolve()
    left.mkdir()
    right.mkdir()
    real_install = release_verification.install_runtime_package
    faulted_install_seen = False

    def install_without_fault_injection(
        plan: RuntimeInstallPlan,
        *,
        fault_hook: object | None = None,
    ) -> RuntimeInstallResult:
        nonlocal faulted_install_seen
        if fault_hook is not None:
            faulted_install_seen = True
        return real_install(plan)

    monkeypatch.setattr(
        release_verification,
        "install_runtime_package",
        install_without_fault_injection,
    )

    with pytest.raises(ValueError, match="runtime_exception_recovery_unsafe"):
        release_verification._verify_one_audited_deck(
            inputs=inputs,
            resource_store=resources,
            deck_code=deck_code,
            work_root_a=left,
            work_root_b=right,
        )

    assert faulted_install_seen


def test_release_verification_reraises_a_foreign_runtime_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs, resources, deck_code = _release_verification_materials()
    rendered = _render_selected_run(
        inputs=inputs,
        resources=resources,
        deck_code=deck_code,
    )
    real_install = release_verification.install_runtime_package

    def install_with_foreign_failure(
        plan: RuntimeInstallPlan,
        *,
        fault_hook: object | None = None,
    ) -> RuntimeInstallResult:
        if fault_hook is not None:
            raise RuntimeError("foreign-runtime-failure")
        return real_install(plan)

    monkeypatch.setattr(
        release_verification,
        "install_runtime_package",
        install_with_foreign_failure,
    )

    with pytest.raises(RuntimeError, match="foreign-runtime-failure"):
        release_verification._verify_exception_recovery(
            rendered=rendered,
            inputs=inputs,
            resource_store=resources,
            deck_code=deck_code,
            publication_root=tmp_path / "foreign-publication",
            runtime_root=tmp_path / "foreign-runtime",
            checkpoint="after_state_write",
            expect_new=True,
        )


def test_release_verification_rejects_a_missing_prior_runtime_journal(
    tmp_path: Path,
) -> None:
    inputs, resources, deck_code = _release_verification_materials()
    rendered = _render_selected_run(
        inputs=inputs,
        resources=resources,
        deck_code=deck_code,
    )
    published = publish_configure_run(
        rendered,
        tmp_path / "journal-publication",
    )
    runtime_root = tmp_path / "journal-runtime"
    runtime_root.mkdir()
    plan = plan_runtime_install(
        published_output=published,
        runtime_root=runtime_root,
    )
    install_runtime_package(plan)
    transaction_root = runtime_root / ".hsconfig" / "transactions"
    journals = tuple(transaction_root.glob("*.json"))
    assert len(journals) == 1
    journals[0].unlink()

    with pytest.raises(RuntimeError, match="prior_runtime_journal_invalid"):
        release_verification._capture_prior_runtime(plan)
