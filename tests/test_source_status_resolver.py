from __future__ import annotations

import dataclasses
import json

import pytest

from hsconfig.source_status_resolver import (
    SourceStatusResolution,
    resolve_source_status,
)


def test_strong_ready_path_exports_operator_fields() -> None:
    resolution = resolve_source_status(
        technical_status="VALID_PACKAGE",
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        semantic_blockers=[],
        default_only_runtime_surfaces=[],
        source_claim_gap_report={"summary": {"first_missing_chain": None}},
        closure_profile_closed=True,
    )

    assert resolution == SourceStatusResolution(
        source_backed_status="SOURCE_BACKED_STRONG",
        strong_ready=True,
        first_missing_source_action="none",
        default_only_runtime_surfaces=(),
        missing_source_actions=(),
        reasons=("source_backed_strong_ready",),
    )
    assert resolution.as_operator_fields() == {
        "source_backed_status": "SOURCE_BACKED_STRONG",
        "source_strong_ready": True,
        "first_missing_source_action": "none",
        "source_missing_source_actions": (),
        "source_status_reasons": ("source_backed_strong_ready",),
        "source_status_diagnostic_only": True,
        "source_status_apply_blocking": False,
    }
    json.dumps(dataclasses.asdict(resolution))
    json.dumps(resolution.as_operator_fields())


def test_resolution_is_frozen() -> None:
    resolution = resolve_source_status(
        technical_status="VALID_PACKAGE",
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        semantic_blockers=[],
        default_only_runtime_surfaces=[],
        source_claim_gap_report=None,
        closure_profile_closed=True,
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        resolution.strong_ready = False  # type: ignore[misc]


def test_default_only_surface_prevents_strong_status() -> None:
    resolution = resolve_source_status(
        technical_status="VALID_PACKAGE",
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        semantic_blockers=[],
        default_only_runtime_surfaces=["mulligan"],
        source_claim_gap_report=None,
        closure_profile_closed=True,
    )

    assert resolution.source_backed_status == "SOURCE_BACKED_PARTIAL"
    assert resolution.strong_ready is False
    assert (
        resolution.first_missing_source_action
        == "replace_default_only_runtime_surface_with_source_or_policy_claim"
    )
    assert resolution.default_only_runtime_surfaces == ("mulligan",)
    assert resolution.missing_source_actions == (
        "replace_default_only_runtime_surface_with_source_or_policy_claim",
    )
    assert "default_only_runtime_surface" in resolution.reasons


def test_default_only_surface_prevents_strong_when_technical_status_is_invalid() -> None:
    resolution = resolve_source_status(
        technical_status="INVALID_PACKAGE",
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        semantic_blockers=[],
        default_only_runtime_surfaces=["mulligan"],
        source_claim_gap_report=None,
        closure_profile_closed=True,
    )

    assert resolution.source_backed_status != "SOURCE_BACKED_STRONG"
    assert resolution.strong_ready is False
    assert (
        resolution.first_missing_source_action
        == "replace_default_only_runtime_surface_with_source_or_policy_claim"
    )


def test_invalid_technical_status_cannot_resolve_as_source_backed_strong() -> None:
    resolution = resolve_source_status(
        technical_status="INVALID_PACKAGE",
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="FIX_PACKAGE_BEFORE_APPLY",
        semantic_blockers=[],
        default_only_runtime_surfaces=[],
        source_claim_gap_report=None,
        closure_profile_closed=True,
    )

    assert resolution.source_backed_status == "INVALID_PACKAGE"
    assert resolution.strong_ready is False
    assert resolution.first_missing_source_action == "FIX_PACKAGE_BEFORE_APPLY"
    assert resolution.reasons == ("technical_status_not_valid",)


def test_first_missing_claim_chain_prevents_strong_and_preserves_next_action() -> None:
    resolution = resolve_source_status(
        technical_status="VALID_PACKAGE",
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        semantic_blockers=[],
        default_only_runtime_surfaces=[],
        source_claim_gap_report={
            "next_action": "close_missing_source_chain",
            "summary": {
                "first_missing_chain": {
                    "card_id": "SW_448",
                    "first_missing_link": "needs_mulligan_claim",
                    "next_action": "add_explicit_mulligan_source",
                }
            },
        },
        closure_profile_closed=True,
    )

    assert resolution.source_backed_status == "SOURCE_BACKED_PARTIAL"
    assert resolution.strong_ready is False
    assert resolution.first_missing_source_action == "close_missing_source_chain"
    assert resolution.missing_source_actions == ("close_missing_source_chain",)
    assert "first_missing_claim_chain" in resolution.reasons


def test_first_missing_claim_chain_uses_summary_source_builder_action() -> None:
    resolution = resolve_source_status(
        technical_status="VALID_PACKAGE",
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        semantic_blockers=[],
        default_only_runtime_surfaces=[],
        source_claim_gap_report={
            "summary": {
                "next_source_builder_action": "add_current_full_text_source",
                "first_missing_chain": {
                    "card_id": "SW_448",
                    "first_missing_link": "needs_guide_claim",
                    "next_action": "add_card_specific_source_claim",
                },
            },
        },
        closure_profile_closed=True,
    )

    assert resolution.source_backed_status == "SOURCE_BACKED_PARTIAL"
    assert resolution.first_missing_source_action == "add_current_full_text_source"


def test_missing_claim_chain_falls_back_to_chain_action() -> None:
    resolution = resolve_source_status(
        technical_status="VALID_PACKAGE",
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        semantic_blockers=[],
        default_only_runtime_surfaces=[],
        source_claim_gap_report={
            "summary": {
                "first_missing_chain": {
                    "card_id": "SW_448",
                    "first_missing_link": "needs_mulligan_claim",
                    "next_action": "add_explicit_mulligan_source",
                }
            }
        },
        closure_profile_closed=True,
    )

    assert resolution.first_missing_source_action == "add_explicit_mulligan_source"
    assert resolution.missing_source_actions == ("add_explicit_mulligan_source",)


def test_semantic_blocker_prevents_strong_and_uses_source_action() -> None:
    resolution = resolve_source_status(
        technical_status="VALID_PACKAGE",
        semantic_status="VALID_BUT_NOT_GUIDE_STRONG",
        next_action="READY_TO_APPLY_WITH_WARNINGS",
        semantic_blockers=[
            {
                "reason": "cards_need_runtime_surface",
                "count": 1,
            }
        ],
        default_only_runtime_surfaces=[],
        source_claim_gap_report=None,
        closure_profile_closed=True,
    )

    assert resolution.source_backed_status == "SOURCE_BACKED_PARTIAL"
    assert resolution.strong_ready is False
    assert (
        resolution.first_missing_source_action
        == "add_runtime_lowerable_claim_or_router_support"
    )
    assert resolution.reasons == ("semantic_blocker",)


def test_invalid_technical_status_is_not_strong() -> None:
    resolution = resolve_source_status(
        technical_status="INVALID_PACKAGE",
        semantic_status="INVALID_PACKAGE",
        next_action="FIX_PACKAGE_BEFORE_APPLY",
        semantic_blockers=[],
        default_only_runtime_surfaces=[],
        source_claim_gap_report={
            "summary": {
                "first_missing_chain": {
                    "card_id": "EX1_001",
                    "first_missing_link": "needs_guide_claim",
                    "next_action": "add_card_specific_source_claim",
                }
            }
        },
        closure_profile_closed=False,
    )

    assert resolution.source_backed_status == "INVALID_PACKAGE"
    assert resolution.strong_ready is False
    assert resolution.first_missing_source_action == "FIX_PACKAGE_BEFORE_APPLY"
    assert resolution.missing_source_actions == ("FIX_PACKAGE_BEFORE_APPLY",)
    assert resolution.reasons == ("technical_status_not_valid",)


def test_profile_miss_preserves_specific_source_action() -> None:
    resolution = resolve_source_status(
        technical_status="VALID_PACKAGE",
        semantic_status="SOURCE_BACKED_STRONG",
        next_action="READY_TO_APPLY_OR_HANDOFF",
        semantic_blockers=[],
        default_only_runtime_surfaces=[],
        source_claim_gap_report={"summary": {"first_missing_chain": None}},
        closure_profile_closed=False,
        closure_profile_first_missing_link=(
            "missing_claim_group:targeting_rule|hero_power_transform|card_role"
        ),
    )

    assert resolution.source_backed_status == "SOURCE_BACKED_PARTIAL"
    assert resolution.strong_ready is False
    assert resolution.first_missing_source_action == "add_profile_claim_group_source"
    assert resolution.missing_source_actions == ("add_profile_claim_group_source",)
    assert resolution.reasons == ("closure_profile_not_closed",)


def test_source_failures_are_diagnostic_only_and_never_apply_blocking() -> None:
    scenarios = [
        {"default_only_runtime_surfaces": ["mulligan"], "source_claim_gap_report": None},
        {
            "default_only_runtime_surfaces": [],
            "source_claim_gap_report": {
                "summary": {
                    "first_missing_chain": {
                        "first_missing_link": "needs_runtime_surface",
                    }
                }
            },
        },
        {
            "default_only_runtime_surfaces": [],
            "source_claim_gap_report": None,
            "semantic_blockers": [{"reason": "cards_need_guide_claims", "count": 1}],
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
        },
    ]

    for scenario in scenarios:
        resolution = resolve_source_status(
            technical_status="VALID_PACKAGE",
            semantic_status=scenario.get("semantic_status", "SOURCE_BACKED_STRONG"),
            next_action=scenario.get("next_action", "READY_TO_APPLY_OR_HANDOFF"),
            semantic_blockers=scenario.get("semantic_blockers", []),
            default_only_runtime_surfaces=scenario["default_only_runtime_surfaces"],
            source_claim_gap_report=scenario["source_claim_gap_report"],
            closure_profile_closed=True,
        )

        assert resolution.strong_ready is False
        assert resolution.diagnostic_only is True
        assert resolution.apply_blocking is False
        assert resolution.as_operator_fields()["source_status_apply_blocking"] is False
