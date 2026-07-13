from __future__ import annotations

from hsconfig.source_contract_conformance import (
    build_source_contract_conformance_snapshot,
    render_source_contract_conformance_markdown,
)
from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS


def test_conformance_snapshot_covers_every_supported_claim_kind():
    snapshot = build_source_contract_conformance_snapshot()

    assert snapshot["schema_version"] == 1
    assert snapshot["operator_gate_impact"] == "diagnostic_only"
    assert set(snapshot["claim_kind_rows"]) == set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    assert snapshot["summary"]["claim_kinds_total"] == len(SUPPORTED_ATOMIC_CLAIM_KINDS)
    assert snapshot["summary"]["missing_claim_kinds"] == []
    assert snapshot["summary"]["extra_claim_kinds"] == []


def test_conformance_snapshot_keeps_key_boundaries_explicit():
    rows = build_source_contract_conformance_snapshot()["claim_kind_rows"]

    assert rows["mulligan_keep"]["policy_lane"] == "runtime_lowerable"
    assert rows["mulligan_keep"]["surface_gates"]["mulligan"]["decision"] == "allowed"
    assert rows["mulligan_keep"]["surface_gates"]["cardid"]["decision"] == "rejected"

    assert rows["hero_power_transform"]["policy_lane"] == "suppressed_or_conditional"
    assert rows["hero_power_transform"]["surface_gates"]["cardid"]["decision"] == "allowed"
    assert rows["hero_power_transform"]["surface_gates"]["mulligan"]["decision"] == "rejected"

    assert rows["globalvalue_numeric_tuning"]["policy_lane"] == "runtime_evidence_required"
    assert rows["globalvalue_numeric_tuning"]["surface_gates"]["globalvalues"]["decision"] == "rejected"
    assert rows["globalvalue_numeric_tuning"]["surface_gates"]["globalvalues"]["reason"] == (
        "requires_runtime_evidence"
    )


def test_conformance_snapshot_reports_no_policy_gate_mismatches_for_representative_context():
    snapshot = build_source_contract_conformance_snapshot()

    assert snapshot["summary"]["policy_gate_mismatch_count"] == 0
    assert snapshot["summary"]["policy_gate_mismatches"] == []


def test_conformance_snapshot_records_builder_router_expectations_and_combo_prerequisites():
    snapshot = build_source_contract_conformance_snapshot()
    rows = snapshot["claim_kind_rows"]

    assert all("builder_router" in row for row in rows.values())

    combo = rows["combo_sequence"]["builder_router"]
    assert combo["surface"] == "combo"
    assert combo["runner"] == "build_combo_plan"
    assert combo["complete"]["expected_outcome"] == "emitted"
    assert combo["complete"]["outcome"] == "emitted"
    assert combo["incomplete"]["expected_outcome"] == "suppressed"
    assert combo["incomplete"]["outcome"] == "suppressed"
    assert combo["incomplete"]["reason"] == "sequence_too_short"

    assert snapshot["summary"]["builder_prerequisite_gap_count"] >= 1
    assert {
        "claim_kind": "combo_sequence",
        "surface": "combo",
        "builder_outcome": "suppressed",
        "reason": "sequence_too_short",
    } in [
        {
            key: value
            for key, value in row.items()
            if key in {"claim_kind", "surface", "builder_outcome", "reason"}
        }
        for row in snapshot["summary"]["builder_prerequisite_gaps"]
    ]


def test_conformance_snapshot_describes_a_policy_gate_mismatch(monkeypatch):
    from hsconfig import source_contract_conformance as conformance

    original = conformance.surface_gate_decision

    def mismatching_gate(claim, surface, context=None):
        decision = original(claim, surface, context=context)
        if decision.claim_kind == "mulligan_keep" and surface == "mulligan":
            return type(decision)(False, "forced_test_mismatch", decision.claim_kind, surface)
        return decision

    monkeypatch.setattr(conformance, "surface_gate_decision", mismatching_gate)
    mismatches = build_source_contract_conformance_snapshot()["summary"][
        "policy_gate_mismatches"
    ]

    assert mismatches == [
        {
            "claim_kind": "mulligan_keep",
            "surface": "mulligan",
            "policy_allowed": True,
            "gate_decision": "rejected",
            "gate_reason": "forced_test_mismatch",
        }
    ]


def test_conformance_snapshot_proves_start_of_game_effect_is_not_hand_keep():
    snapshot = build_source_contract_conformance_snapshot()
    row = snapshot["start_of_game_mulligan_suppression"]

    assert row["claim_kind"] == "mulligan_keep"
    assert row["surface"] == "mulligan"
    assert row["decision"] == "rejected"
    assert row["reason"] == "start_of_game_effect_does_not_require_opening_hand"
    assert row["operator_meaning"] == (
        "Start-of-game effects remain effect-visible but do not become opening-hand keeps."
    )


def test_darkbishop_effect_boundary_is_visible_in_conformance_contract():
    snapshot = build_source_contract_conformance_snapshot()
    hero_power_row = snapshot["claim_kind_rows"]["hero_power_transform"]
    suppression = snapshot["start_of_game_mulligan_suppression"]

    assert hero_power_row["surface_gates"]["cardid"]["decision"] == "allowed"
    assert hero_power_row["surface_gates"]["mulligan"]["decision"] == "rejected"
    assert suppression["reason"] == "start_of_game_effect_does_not_require_opening_hand"


def test_conformance_markdown_is_compact_and_diagnostic_only():
    markdown = render_source_contract_conformance_markdown(
        build_source_contract_conformance_snapshot()
    )

    assert "# Source Contract Conformance Snapshot" in markdown
    assert "Diagnostic only" in markdown
    assert "| mulligan_keep | runtime_lowerable | mulligan |" in markdown
    assert "| globalvalue_numeric_tuning | runtime_evidence_required | none |" in markdown
    assert "operator_summary.json remains the apply authority" in markdown


def test_conformance_markdown_exposes_combo_builder_router_outcomes():
    markdown = render_source_contract_conformance_markdown(
        build_source_contract_conformance_snapshot()
    )

    assert "## Builder/Router Outcomes" in markdown
    assert (
        "| combo_sequence | combo | build_combo_plan | emitted | suppressed: sequence_too_short |"
        in markdown
    )


def test_pipeline_mismatch_count_includes_builder_router_expectation_mismatches(monkeypatch):
    from hsconfig import source_contract_conformance as conformance

    monkeypatch.setitem(
        conformance._BUILDER_ROUTER_EXPECTATIONS["mulligan_keep"],
        "outcome",
        "suppressed",
    )

    summary = build_source_contract_conformance_snapshot()["summary"]

    assert summary["policy_gate_mismatch_count"] == 0
    assert summary["builder_router_expectation_mismatch_count"] == 1
    assert summary["surface_gate_builder_mismatch_count"] == 1
    assert summary["pipeline_mismatch_count"] == 2


def test_conformance_snapshot_contains_no_apply_authority_fields():
    snapshot = build_source_contract_conformance_snapshot()

    forbidden_keys = {
        "runtime_apply_allowed",
        "runtime_apply_mode",
        "apply_policy",
        "next_action",
        "technical_status",
    }
    assert forbidden_keys.isdisjoint(snapshot)
    assert snapshot["operator_gate_impact"] == "diagnostic_only"


def test_conformance_snapshot_distinguishes_drift_from_builder_prerequisites():
    summary = build_source_contract_conformance_snapshot()["summary"]

    assert summary["policy_gate_mismatch_count"] == 0
    assert summary["builder_router_expectation_mismatch_count"] == 0
    assert summary["unexpected_contract_drift_count"] == 0
    assert summary["unexpected_contract_drifts"] == []

    assert summary["builder_prerequisite_gap_count"] == 1
    assert summary["builder_prerequisite_gaps"] == [
        {
            "claim_kind": "combo_sequence",
            "surface": "combo",
            "builder_outcome": "suppressed",
            "reason": "sequence_too_short",
            "operator_meaning": (
                "Surface gate allows this claim kind, but the builder still needs "
                "a complete sequence before runtime JSON can be emitted."
            ),
        }
    ]
    assert summary["pipeline_attention_count"] == 1


def test_conformance_snapshot_keeps_legacy_mismatch_keys_as_attention_aliases():
    summary = build_source_contract_conformance_snapshot()["summary"]

    assert summary["surface_gate_builder_mismatch_count"] == summary[
        "builder_prerequisite_gap_count"
    ]
    assert summary["surface_gate_builder_mismatches"] == summary[
        "builder_prerequisite_gaps"
    ]
    assert summary["pipeline_mismatch_count"] == summary["pipeline_attention_count"]


def test_conformance_snapshot_exposes_claim_lifecycle_for_key_claims():
    rows = build_source_contract_conformance_snapshot()["claim_kind_rows"]

    assert rows["hero_power_transform"]["lifecycle"] == {
        "policy_lane": "suppressed_or_conditional",
        "allowed_surfaces": ["cardid"],
        "surface_gate_status": "cardid:allowed",
        "builder_status": "route_card_behavior_surfaces:emitted",
        "final_runtime_effect": "emits_cardid_runtime_row",
        "operator_meaning": (
            "Preserve hero-power-transform semantics; it is not a mulligan keep by itself."
        ),
    }
    assert rows["globalvalue_numeric_tuning"]["lifecycle"] == {
        "policy_lane": "runtime_evidence_required",
        "allowed_surfaces": [],
        "surface_gate_status": "no_allowed_surface",
        "builder_status": "build_globalvalues_authority_matrix:suppressed:requires_runtime_evidence",
        "final_runtime_effect": "suppressed_until_runtime_evidence",
        "operator_meaning": (
            "Valid evidence, but Step 1 must wait for runtime evidence before numeric tuning."
        ),
    }
    assert rows["combo_sequence"]["lifecycle"] == {
        "policy_lane": "runtime_lowerable",
        "allowed_surfaces": ["combo"],
        "surface_gate_status": "combo:allowed",
        "builder_status": "build_combo_plan:emitted; incomplete:suppressed:sequence_too_short",
        "final_runtime_effect": "emits_when_builder_prerequisites_are_complete",
        "operator_meaning": "Can lower only as an explicit ordered Combo.json sequence.",
    }


def test_conformance_snapshot_exposes_flat_contract_spine_rows():
    snapshot = build_source_contract_conformance_snapshot()
    spine_rows = snapshot["contract_spine_rows"]

    assert len(spine_rows) == len(SUPPORTED_ATOMIC_CLAIM_KINDS)
    assert {row["claim_kind"] for row in spine_rows} == set(SUPPORTED_ATOMIC_CLAIM_KINDS)

    hero_power = next(
        row for row in spine_rows if row["claim_kind"] == "hero_power_transform"
    )
    assert hero_power == {
        "claim_kind": "hero_power_transform",
        "policy_lane": "suppressed_or_conditional",
        "semantic_lane": "suppressed_or_conditional",
        "allowed_surfaces": ["cardid"],
        "required_fields": ["claim_kind", "claim_readiness", "trust_ceiling", "cards"],
        "runtime_lowerable": True,
        "surface_gate_status": "cardid:allowed",
        "builder_status": "route_card_behavior_surfaces:emitted",
        "final_runtime_effect": "emits_cardid_runtime_row",
        "default_suppression_reason": "requires_supported_cardid_surface",
        "operator_gate_impact": "diagnostic_only",
    }

    numeric = next(
        row for row in spine_rows if row["claim_kind"] == "globalvalue_numeric_tuning"
    )
    assert numeric["surface_gate_status"] == "no_allowed_surface"
    assert numeric["final_runtime_effect"] == "suppressed_until_runtime_evidence"
    assert numeric["runtime_lowerable"] is False
    assert numeric["default_suppression_reason"] == "requires_runtime_evidence"
    assert numeric["operator_gate_impact"] == "diagnostic_only"


def test_contract_spine_rows_are_exact_lifecycle_projection():
    snapshot = build_source_contract_conformance_snapshot()
    claim_rows = snapshot["claim_kind_rows"]
    spine_rows = snapshot["contract_spine_rows"]
    expected_keys = {
        "claim_kind",
        "policy_lane",
        "semantic_lane",
        "allowed_surfaces",
        "required_fields",
        "runtime_lowerable",
        "surface_gate_status",
        "builder_status",
        "final_runtime_effect",
        "default_suppression_reason",
        "operator_gate_impact",
    }

    assert len(spine_rows) == len(SUPPORTED_ATOMIC_CLAIM_KINDS)
    assert [row["claim_kind"] for row in spine_rows] == sorted(SUPPORTED_ATOMIC_CLAIM_KINDS)

    for row in spine_rows:
        claim_kind = row["claim_kind"]
        lifecycle = claim_rows[claim_kind]["lifecycle"]

        assert set(row) == expected_keys
        assert row["policy_lane"] == lifecycle["policy_lane"]
        assert row["semantic_lane"] == claim_rows[claim_kind]["semantic_lane"]
        assert row["allowed_surfaces"] == lifecycle["allowed_surfaces"]
        assert row["required_fields"] == claim_rows[claim_kind]["required_fields"]
        assert row["runtime_lowerable"] == claim_rows[claim_kind]["runtime_lowerable"]
        assert row["surface_gate_status"] == lifecycle["surface_gate_status"]
        assert row["builder_status"] == lifecycle["builder_status"]
        assert row["final_runtime_effect"] == lifecycle["final_runtime_effect"]
        assert row["default_suppression_reason"] == claim_rows[claim_kind][
            "default_suppression_reason"
        ]
        assert row["operator_gate_impact"] == "diagnostic_only"


def test_contract_spine_rows_never_carry_apply_authority_fields():
    snapshot = build_source_contract_conformance_snapshot()
    forbidden_keys = {
        "apply_allowed",
        "apply_gate",
        "apply_policy",
        "next_action",
        "runtime_apply_allowed",
        "runtime_apply_mode",
        "technical_status",
    }

    for row in snapshot["contract_spine_rows"]:
        assert forbidden_keys.isdisjoint(row), row
        assert row["operator_gate_impact"] == "diagnostic_only"


def test_conformance_markdown_uses_drift_and_prerequisite_language():
    markdown = render_source_contract_conformance_markdown(
        build_source_contract_conformance_snapshot()
    )

    assert "## Summary" in markdown
    assert "- Unexpected contract drift: 0" in markdown
    assert "- Builder prerequisite gaps: 1" in markdown
    assert "## Builder Prerequisite Gaps" in markdown
    assert (
        "| combo_sequence | combo | suppressed | sequence_too_short | "
        "Surface gate allows this claim kind, but the builder still needs a complete "
        "sequence before runtime JSON can be emitted. |"
    ) in markdown
    assert "## Claim Lifecycle" in markdown
    assert (
        "| hero_power_transform | suppressed_or_conditional | cardid:allowed | "
        "route_card_behavior_surfaces:emitted | emits_cardid_runtime_row |"
    ) in markdown


def test_conformance_markdown_renders_contract_spine_section():
    markdown = render_source_contract_conformance_markdown(
        build_source_contract_conformance_snapshot()
    )

    assert "## Contract Spine" in markdown
    assert (
        "| hero_power_transform | suppressed_or_conditional | cardid:allowed | "
        "route_card_behavior_surfaces:emitted | emits_cardid_runtime_row | "
        "diagnostic_only |"
    ) in markdown
    assert (
        "| globalvalue_numeric_tuning | runtime_evidence_required | "
        "no_allowed_surface | "
        "build_globalvalues_authority_matrix:suppressed:requires_runtime_evidence | "
        "suppressed_until_runtime_evidence | diagnostic_only |"
    ) in markdown


def _spine_row(snapshot: dict, claim_kind: str) -> dict:
    for row in snapshot["contract_spine_rows"]:
        if row["claim_kind"] == claim_kind:
            return row
    raise AssertionError(f"missing contract spine row for {claim_kind}")


def test_contract_spine_keeps_critical_runtime_boundaries_explicit():
    snapshot = build_source_contract_conformance_snapshot()

    assert snapshot["operator_gate_impact"] == "diagnostic_only"

    expectations = {
        "mulligan_keep": {
            "policy_lane": "runtime_lowerable",
            "allowed_surfaces": ["mulligan"],
            "surface_gate_status": "mulligan:allowed",
            "final_runtime_effect": "emits_mulligan_runtime_row",
        },
        "hero_power_transform": {
            "policy_lane": "suppressed_or_conditional",
            "allowed_surfaces": ["cardid"],
            "surface_gate_status": "cardid:allowed",
            "final_runtime_effect": "emits_cardid_runtime_row",
        },
        "globalvalue_numeric_tuning": {
            "policy_lane": "runtime_evidence_required",
            "allowed_surfaces": [],
            "surface_gate_status": "no_allowed_surface",
            "final_runtime_effect": "suppressed_until_runtime_evidence",
        },
        "combo_sequence": {
            "policy_lane": "runtime_lowerable",
            "allowed_surfaces": ["combo"],
            "surface_gate_status": "combo:allowed",
            "final_runtime_effect": "emits_when_builder_prerequisites_are_complete",
        },
        "archetype": {
            "policy_lane": "report_only",
            "allowed_surfaces": [],
            "surface_gate_status": "no_allowed_surface",
            "final_runtime_effect": "report_only_no_runtime_row",
        },
    }

    for claim_kind, expected in expectations.items():
        row = _spine_row(snapshot, claim_kind)
        for key, value in expected.items():
            assert row[key] == value, (claim_kind, key, row)
        assert row["operator_gate_impact"] == "diagnostic_only"


def test_contract_spine_start_of_game_boundary_is_not_a_mulligan_exception():
    snapshot = build_source_contract_conformance_snapshot()
    suppression = snapshot["start_of_game_mulligan_suppression"]

    assert suppression["decision"] == "rejected"
    assert suppression["reason"] == "start_of_game_effect_does_not_require_opening_hand"
    assert "do not become opening-hand keeps" in suppression["operator_meaning"]


def test_source_contract_policy_rows_expose_complete_runtime_contract_metadata():
    from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind

    policy = source_contract_policy_by_claim_kind()
    required_keys = {
        "lane",
        "semantic_lane",
        "allowed_surfaces",
        "required_fields",
        "runtime_lowerable",
        "default_suppression_reason",
        "operator_meaning",
        "operator_gate_impact",
    }

    assert set(policy) == set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    for claim_kind, row in policy.items():
        assert required_keys <= set(row), claim_kind
        assert row["semantic_lane"] == row["lane"]
        assert row["operator_gate_impact"] == "diagnostic_only"
        assert isinstance(row["required_fields"], tuple), claim_kind
        assert isinstance(row["runtime_lowerable"], bool), claim_kind

    assert policy["mulligan_keep"]["required_fields"] == (
        "claim_kind",
        "claim_readiness",
        "trust_ceiling",
        "cards",
    )
    assert policy["mulligan_keep"]["runtime_lowerable"] is True
    assert policy["hero_power_transform"]["runtime_lowerable"] is True
    assert policy["hero_power_transform"]["default_suppression_reason"] == (
        "requires_supported_cardid_surface"
    )
    assert policy["globalvalue_numeric_tuning"]["runtime_lowerable"] is False
    assert policy["globalvalue_numeric_tuning"]["default_suppression_reason"] == (
        "requires_runtime_evidence"
    )
    assert policy["archetype"]["runtime_lowerable"] is False
    assert policy["archetype"]["default_suppression_reason"] == "report_only"


def test_contract_policy_documents_semantic_qualifier_usage_without_new_gate():
    from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind

    policy = source_contract_policy_by_claim_kind()

    assert policy["mulligan_keep"]["semantic_qualifier_usage"] == (
        "timing and zone qualifiers may suppress start-of-game non-hand effects"
    )
    assert policy["targeting_rule"]["semantic_qualifier_usage"] == (
        "target_scope may refine CardID targeting behavior"
    )
    assert policy["combo_sequence"]["semantic_qualifier_usage"] == (
        "timing and state requirements may refine Combo.json eligibility"
    )
    assert all(row["operator_gate_impact"] == "diagnostic_only" for row in policy.values())


def test_contract_spine_rows_include_policy_metadata_without_apply_authority():
    snapshot = build_source_contract_conformance_snapshot()
    rows_by_kind = {row["claim_kind"]: row for row in snapshot["contract_spine_rows"]}

    required_keys = {
        "claim_kind",
        "policy_lane",
        "semantic_lane",
        "allowed_surfaces",
        "required_fields",
        "runtime_lowerable",
        "surface_gate_status",
        "builder_status",
        "final_runtime_effect",
        "default_suppression_reason",
        "operator_gate_impact",
    }
    forbidden_keys = {
        "apply_allowed",
        "apply_gate",
        "apply_policy",
        "next_action",
        "runtime_apply_allowed",
        "runtime_apply_mode",
        "technical_status",
    }

    for row in rows_by_kind.values():
        assert set(row) == required_keys
        assert forbidden_keys.isdisjoint(row)
        assert row["operator_gate_impact"] == "diagnostic_only"

    assert rows_by_kind["hero_power_transform"]["runtime_lowerable"] is True
    assert rows_by_kind["hero_power_transform"]["default_suppression_reason"] == (
        "requires_supported_cardid_surface"
    )
    assert rows_by_kind["globalvalue_numeric_tuning"]["runtime_lowerable"] is False
    assert rows_by_kind["globalvalue_numeric_tuning"]["final_runtime_effect"] == (
        "suppressed_until_runtime_evidence"
    )
