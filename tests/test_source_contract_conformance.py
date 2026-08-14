from __future__ import annotations

import pytest

from hsconfig import source_contract_conformance
from hsconfig.source_contract_conformance import (
    build_source_contract_conformance_snapshot,
    render_source_contract_conformance_markdown,
)
from hsconfig.source_document_model import SUPPORTED_ATOMIC_CLAIM_KINDS


def test_contract_spine_projection_skips_invalid_rows_and_defaults_lifecycle() -> None:
    rows = source_contract_conformance._contract_spine_rows(
        {
            "ignored": "not-a-row",
            "claim": {
                "semantic_lane": "diagnostic",
                "required_fields": ["cards"],
                "runtime_lowerable": True,
                "lifecycle": "not-a-mapping",
            },
        }
    )

    assert rows == [
        {
            "claim_kind": "claim",
            "policy_lane": "",
            "semantic_lane": "diagnostic",
            "allowed_surfaces": [],
            "required_fields": ["cards"],
            "runtime_lowerable": True,
            "surface_gate_status": "",
            "builder_status": "",
            "final_runtime_effect": "",
            "default_suppression_reason": "",
            "operator_gate_impact": "diagnostic_only",
        }
    ]


def test_surface_and_builder_statuses_name_missing_and_complete_states() -> None:
    assert source_contract_conformance._surface_gate_status(
        {"allowed_surfaces": []}
    ) == "no_allowed_surface"
    assert source_contract_conformance._surface_gate_status(
        {"allowed_surfaces": ["combo"], "surface_gates": []}
    ) == "missing_surface_gates"
    assert source_contract_conformance._surface_gate_status(
        {"allowed_surfaces": ["combo"], "surface_gates": {"combo": []}}
    ) == "combo:missing"
    assert source_contract_conformance._surface_gate_status(
        {
            "allowed_surfaces": ["combo", "cardid"],
            "surface_gates": {
                "combo": {"decision": "allowed"},
                "cardid": {"decision": "rejected"},
            },
        }
    ) == "combo:allowed; cardid:rejected"

    assert source_contract_conformance._builder_status([]) == "no_builder_router"
    assert source_contract_conformance._builder_status(
        {"runner": "combo", "complete": []}
    ) == "combo:missing_complete_exemplar"
    assert source_contract_conformance._builder_status(
        {
            "runner": "combo",
            "complete": {"outcome": "emitted"},
            "incomplete": {"outcome": "suppressed", "reason": "sequence_missing"},
        }
    ) == "combo:emitted; incomplete:suppressed:sequence_missing"
    assert source_contract_conformance._builder_status(
        {
            "runner": "cardid",
            "complete": {"outcome": "suppressed", "reason": "missing_card"},
        }
    ) == "cardid:suppressed:missing_card"


def test_final_runtime_effect_maps_every_runtime_surface_and_suppression() -> None:
    assert source_contract_conformance._final_runtime_effect(
        {"claim_kind": "globalvalue_numeric_tuning"}
    ) == "suppressed_until_runtime_evidence"
    for claim_kind in ("archetype", "tech_slot", "replacement_option"):
        assert source_contract_conformance._final_runtime_effect(
            {"claim_kind": claim_kind}
        ) == "report_only_no_runtime_row"
    assert source_contract_conformance._final_runtime_effect(
        {"claim_kind": "card_role", "builder_router": []}
    ) == "unknown_runtime_effect"
    assert source_contract_conformance._final_runtime_effect(
        {
            "claim_kind": "card_role",
            "builder_router": {"surface": "cardid", "complete": []},
        }
    ) == "unknown_runtime_effect"
    assert source_contract_conformance._final_runtime_effect(
        {
            "claim_kind": "card_role",
            "builder_router": {
                "surface": "cardid",
                "complete": {"outcome": "suppressed", "reason": "missing_card"},
            },
        }
    ) == "suppressed:missing_card"
    expected = {
        "mulligan": "emits_mulligan_runtime_row",
        "globalvalues": "emits_globalvalues_posture_overlay",
        "cardid": "emits_cardid_runtime_row",
        "combo": "emits_combo_runtime_row",
        "unknown": "report_only_no_runtime_row",
    }
    assert {
        surface: source_contract_conformance._final_runtime_effect(
            {
                "claim_kind": "card_role",
                "builder_router": {
                    "surface": surface,
                    "complete": {"outcome": "emitted"},
                },
            }
        )
        for surface in expected
    } == expected


def test_conformance_diagnostics_report_real_policy_builder_disagreements() -> None:
    rows = {
        "ignored": "not-a-row",
        "claim": {
            "allowed_surfaces": ["combo"],
            "surface_gates": {
                "mulligan": [],
                "combo": {"decision": "rejected", "reason": "unexpected"},
                "cardid": {"decision": "allowed", "reason": "allowed"},
            },
            "builder_router": {
                "surface": "cardid",
                "complete": {
                    "expected_outcome": "emitted",
                    "outcome": "suppressed",
                    "reason": "missing_card",
                },
                "incomplete": {
                    "expected_outcome": "suppressed",
                    "outcome": "suppressed",
                },
            },
        },
        "invalid-containers": {
            "surface_gates": [],
            "builder_router": [],
        },
    }
    policy = source_contract_conformance._policy_gate_mismatches(rows)
    assert [(row["surface"], row["policy_allowed"]) for row in policy] == [
        ("cardid", False),
        ("combo", True),
    ]
    builder = source_contract_conformance._builder_expectation_mismatches(rows)
    assert builder == [
        {
            "claim_kind": "claim",
            "exemplar": "complete",
            "expected_outcome": "emitted",
            "builder_outcome": "suppressed",
            "reason": "missing_card",
        }
    ]


def test_builder_prerequisite_gaps_require_allowed_gate_and_suppressed_exemplar() -> None:
    rows = {
        "ignored": "invalid",
        "claim": {
            "surface_gates": {"combo": {"decision": "allowed"}},
            "builder_router": {
                "surface": "combo",
                "complete": {"outcome": "emitted"},
                "incomplete": {"outcome": "suppressed", "reason": "sequence_missing"},
            },
        },
        "invalid-router": {"builder_router": []},
        "invalid-gates": {"builder_router": {"surface": 3}, "surface_gates": []},
    }
    gaps = source_contract_conformance._builder_prerequisite_gaps(rows)
    assert len(gaps) == 1
    assert gaps[0]["claim_kind"] == "claim"
    assert gaps[0]["surface"] == "combo"
    assert gaps[0]["builder_outcome"] == "suppressed"
    assert gaps[0]["reason"] == "sequence_missing"


def test_gate_and_builder_summaries_ignore_malformed_rows() -> None:
    assert source_contract_conformance._gate_summary([]) == ""
    assert source_contract_conformance._gate_summary(
        {
            "mulligan": [],
            "cardid": {"decision": "allowed", "reason": "allowed"},
        }
    ) == (
        "globalvalues:None:None; cardid:allowed:allowed; combo:None:None"
    )
    assert source_contract_conformance._builder_outcome_summary([]) == "-"
    assert source_contract_conformance._builder_outcome_summary(
        {"outcome": "emitted", "reason": "emitted"}
    ) == "emitted"
    assert source_contract_conformance._builder_outcome_summary(
        {"outcome": "suppressed", "reason": "missing_card"}
    ) == "suppressed: missing_card"


def test_conformance_markdown_ignores_malformed_optional_sections() -> None:
    markdown = render_source_contract_conformance_markdown(
        {
            "claim_kind_rows": {
                "invalid": "not-a-row",
                "invalid-router": {"builder_router": "not-a-router"},
                "invalid-lifecycle": {"lifecycle": "not-a-lifecycle"},
            },
            "summary": "not-a-summary",
            "contract_spine_rows": [
                "invalid",
                {
                    "claim_kind": "claim|one",
                    "policy_lane": "diagnostic",
                    "surface_gate_status": "none",
                    "builder_status": "none",
                    "final_runtime_effect": "none",
                    "operator_gate_impact": "diagnostic_only",
                },
            ],
            "start_of_game_mulligan_suppression": "invalid",
        }
    )

    assert "| claim\\|one | diagnostic | none | none | none | diagnostic_only |" in markdown
    assert "| none | none | none | none | none |" in markdown
    assert "## Start-of-Game Mulligan Boundary" not in markdown


def test_conformance_builder_adapter_recognizes_each_success_shape(monkeypatch) -> None:
    class MulliganPlan:
        def to_report(self) -> dict[str, object]:
            return {
                "rules": [{"source_claim_ids": ["claim"]}],
                "suppressed_rules": [],
            }

    monkeypatch.setattr(
        source_contract_conformance,
        "build_combo_plan",
        lambda **_kwargs: {"combos": [{"claim_id": "claim"}], "suppressed": []},
    )
    monkeypatch.setattr(
        source_contract_conformance,
        "build_mulligan_plan",
        lambda **_kwargs: MulliganPlan(),
    )
    monkeypatch.setattr(
        source_contract_conformance,
        "build_globalvalues_authority_matrix",
        lambda **_kwargs: {
            "allowed_step1_overlays": [{"claim_refs": ["claim"]}],
            "blocked_until_runtime_evidence": [],
        },
    )
    monkeypatch.setattr(
        source_contract_conformance,
        "route_card_behavior_surfaces",
        lambda *_args, **_kwargs: {
            "rows": [{"claim_id": "claim"}],
            "suppressed": [],
        },
    )

    cases = [
        ("combo_sequence", "build_combo_plan"),
        ("mulligan_keep", "build_mulligan_plan"),
        ("gameplan_posture", "build_globalvalues_authority_matrix"),
        ("card_role", "route_card_behavior_surfaces"),
    ]
    for claim_kind, runner in cases:
        claim = {
            "claim_id": "claim",
            "claim_kind": claim_kind,
            "cards": ["CARD_001", "CARD_002"],
        }
        assert source_contract_conformance._builder_runner_result(
            claim_kind,
            claim,
            {"runner": runner},
        ) == {"outcome": "emitted", "reason": "emitted"}


def test_conformance_builder_adapter_rejects_unknown_runner() -> None:
    with pytest.raises(RuntimeError, match="Unsupported conformance runner: unknown"):
        source_contract_conformance._builder_runner_result(
            "card_role",
            {"claim_id": "claim", "cards": ["CARD_001"]},
            {"runner": "unknown"},
        )


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
    assert rows["mulligan_keep"]["surface_gates"]["mulligan"] == {
        "claim_kind": "mulligan_keep",
        "surface": "mulligan",
        "decision": "rejected",
        "reason": "strategic_provenance_not_live_verified",
    }
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
    assert combo["complete"]["expected_outcome"] == "suppressed"
    assert combo["complete"]["outcome"] == "suppressed"
    assert combo["complete"]["reason"] == "strategic_provenance_not_live_verified"
    assert combo["incomplete"]["expected_outcome"] == "suppressed"
    assert combo["incomplete"]["outcome"] == "suppressed"
    assert combo["incomplete"]["reason"] == "strategic_provenance_not_live_verified"
    assert snapshot["summary"]["builder_prerequisite_gaps"] == []


def test_conformance_strategic_examples_remain_diagnostic_only():
    rows = build_source_contract_conformance_snapshot()["claim_kind_rows"]

    expected_reasons = {
        "mulligan_keep": "strategic_provenance_not_live_verified",
        "mulligan_discard": "strategic_provenance_not_live_verified",
        "targeting_rule": "strategic_provenance_not_live_verified",
        "combo_sequence": "strategic_provenance_not_live_verified",
        "gameplan_posture": "requires_runtime_evidence",
    }
    for claim_kind, expected_reason in expected_reasons.items():
        exemplar = rows[claim_kind]["builder_router"]["complete"]
        assert exemplar["expected_outcome"] == "suppressed"
        assert exemplar["outcome"] == "suppressed"
        assert exemplar["reason"] == expected_reason


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


def test_rendered_conformance_snapshot_is_complete_reference_material():
    snapshot = build_source_contract_conformance_snapshot()
    markdown = render_source_contract_conformance_markdown(snapshot)

    for claim_kind in SUPPORTED_ATOMIC_CLAIM_KINDS:
        assert f"| {claim_kind} |" in markdown

    assert "Diagnostic only" in markdown
    assert "operator_summary.json remains the apply authority" in markdown
    assert "## Contract Spine" in markdown
    assert "## Start-of-Game Mulligan Boundary" in markdown
    assert "start_of_game_effect_does_not_require_opening_hand" in markdown
    assert "runtime_apply_allowed" not in markdown
    assert "technical_status" not in markdown


def test_conformance_markdown_exposes_combo_builder_router_outcomes():
    markdown = render_source_contract_conformance_markdown(
        build_source_contract_conformance_snapshot()
    )

    assert "## Builder/Router Outcomes" in markdown
    assert (
        "| combo_sequence | combo | build_combo_plan | "
        "suppressed: strategic_provenance_not_live_verified | "
        "suppressed: strategic_provenance_not_live_verified |"
        in markdown
    )


def test_pipeline_mismatch_count_includes_builder_router_expectation_mismatches(monkeypatch):
    from hsconfig import source_contract_conformance as conformance

    monkeypatch.setitem(
        conformance._BUILDER_ROUTER_EXPECTATIONS["mulligan_keep"],
        "outcome",
        "emitted",
    )

    summary = build_source_contract_conformance_snapshot()["summary"]

    assert summary["policy_gate_mismatch_count"] == 0
    assert summary["builder_router_expectation_mismatch_count"] == 1
    assert summary["surface_gate_builder_mismatch_count"] == 0
    assert summary["pipeline_mismatch_count"] == 1


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

    assert summary["builder_prerequisite_gap_count"] == 0
    assert summary["builder_prerequisite_gaps"] == []
    assert summary["pipeline_attention_count"] == 0


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
        "surface_gate_status": "combo:rejected",
        "builder_status": (
            "build_combo_plan:suppressed; "
            "incomplete:suppressed:strategic_provenance_not_live_verified"
        ),
        "final_runtime_effect": (
            "suppressed:strategic_provenance_not_live_verified"
        ),
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
    assert "- Builder prerequisite gaps: 0" in markdown
    assert "## Builder Prerequisite Gaps" in markdown
    assert "| none | none | none | none | none |" in markdown
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
            "surface_gate_status": "mulligan:rejected",
            "final_runtime_effect": (
                "suppressed:strategic_provenance_not_live_verified"
            ),
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
            "surface_gate_status": "combo:rejected",
            "final_runtime_effect": (
                "suppressed:strategic_provenance_not_live_verified"
            ),
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
        "target_scope is diagnostic metadata for supported CardID targeting claims"
    )
    assert policy["combo_sequence"]["semantic_qualifier_usage"] == (
        "timing and state requirements are diagnostic metadata for Combo.json claims"
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
