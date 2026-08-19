from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

import hsconfig.starter_compiler as starter_compiler
from hsconfig.globalvalues_decisions import GLOBALVALUES_BASELINE_DECISION_KEYS
from hsconfig.package_compiler import compile_package, compile_package_decisions
from hsconfig.package_domain import GlobalValueDecisionKind
from hsconfig.package_request import ResolvedPackageRequest
from hsconfig.starter_context import build_starter_context
from hsconfig.starter_decision import load_validated_starter_selection
from tests.helpers.audited_package_request import audited_request
from tests.test_starter_candidate import sealed_candidate
from tests.test_starter_decision import three_candidates, write_selection_bundle


OPTIMIZED_REPORT_PATHS = (
    "reports/optimized_start/starter_context.json",
    "reports/optimized_start/candidate-1.json",
    "reports/optimized_start/candidate-2.json",
    "reports/optimized_start/candidate-3.json",
    "reports/optimized_start/starter_config_decision.json",
)


def _optimized_request(
    tmp_path: Path,
    *,
    mutate_selected: Callable[[dict[str, Any]], None] | None = None,
) -> ResolvedPackageRequest:
    base = audited_request(tmp_path / "request", "ShadowPriest")
    context = build_starter_context(base.snapshot)
    candidates = three_candidates(context)
    if mutate_selected is not None:
        candidates[0] = sealed_candidate(
            context,
            candidate_id="candidate-1",
            role="proactive_tempo",
            changed_globalvalue_key="FirstTurnValueWeight",
            changed_globalvalue_value="0.75",
            mutate=mutate_selected,
        )
    decision_path = write_selection_bundle(
        tmp_path / "starter-bundle",
        context,
        candidates,
    )
    selection = load_validated_starter_selection(
        decision_path,
        current_context=context,
    )
    return ResolvedPackageRequest(
        snapshot=base.snapshot,
        invocation=replace(
            base.invocation,
            configuration_mode="LLM_OPTIMIZED_START",
        ),
        plan_overrides=base.plan_overrides,
        acquisition_closure_input=base.acquisition_closure_input,
        mulligan_gap_input=base.mulligan_gap_input,
        starter_selection=selection,
    )


def _expected_optimized_documents(request: ResolvedPackageRequest) -> dict[str, bytes]:
    selection = request.starter_selection
    assert selection is not None
    return {
        OPTIMIZED_REPORT_PATHS[0]: selection.context.document.canonical_json,
        **{
            path: candidate.document.canonical_json
            for path, candidate in zip(
                OPTIMIZED_REPORT_PATHS[1:4],
                selection.candidates,
                strict=True,
            )
        },
        OPTIMIZED_REPORT_PATHS[4]: selection.decision.canonical_json,
    }


def test_lower_optimized_start_builds_one_neutral_frozen_authority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    # Break caught: lowering rebuilds the optimized ledger or leaks mutable/path input.
    request = _optimized_request(tmp_path)
    selection = request.starter_selection
    assert selection is not None
    calls = 0
    original = starter_compiler.build_optimized_globalvalues_decision_ledger

    def counted(**kwargs):
        nonlocal calls
        calls += 1
        return original(**kwargs)

    monkeypatch.setattr(
        starter_compiler,
        "build_optimized_globalvalues_decision_ledger",
        counted,
    )

    lowered = starter_compiler.lower_optimized_start(
        request=request,
        selection=selection,
    )

    assert calls == 1
    assert lowered.authority_id == f"starter:{selection.selected.document.content_sha256}"
    assert lowered.mulligan_plan is selection.selected.mulligan_plan
    assert lowered.combo_plan is selection.selected.combo_plan
    assert tuple(row.key for row in lowered.globalvalues_ledger.decisions) == (
        GLOBALVALUES_BASELINE_DECISION_KEYS
    )
    changed = next(
        row
        for row in lowered.globalvalues_ledger.decisions
        if row.key == "FirstTurnValueWeight"
    )
    assert changed.kind is GlobalValueDecisionKind.LLM_OPTIMIZED_START
    assert changed.authority_id == lowered.authority_id
    assert changed.claim_ids == ()
    unchanged = next(
        row
        for row in lowered.globalvalues_ledger.decisions
        if row.key == "SecondTurnValueWeight"
    )
    assert unchanged.kind is GlobalValueDecisionKind.COPY_BASELINE
    card_plan = lowered.card_behavior_plan.to_value()
    assert card_plan["rows"] == [
        {
            "authority_id": "LLM_OPTIMIZED_START",
            "behavior_block": "BeforeUseHeroPowerBonus",
            "card_id": "EX1_625t",
            "condition": "*",
            "confidence": "llm_optimized_start",
            "claim_id": (
                "starter:"
                f"{selection.selected.document.content_sha256}:"
                "candidate-1:darkbishop-mind-spike"
            ),
            "link_kind": "hero_power_transform",
            "meaningful_runtime_surface": True,
            "rule_id_suffix": "darkbishop-mind-spike",
            "runtime_card_id": "EX1_625t",
            "source_card_id": "SW_448",
            "source_claim_ids": [],
            "surface_family": "CARDID.json",
            "value": "12",
        }
    ]
    expected = _expected_optimized_documents(request)
    assert tuple(path for path, _document in lowered.optimized_projections) == (
        OPTIMIZED_REPORT_PATHS
    )
    assert {
        path: document.canonical_json
        for path, document in lowered.optimized_projections
    } == expected


def test_compile_package_uses_selected_candidate_for_every_runtime_authority(
    tmp_path: Path,
) -> None:
    # Break caught: an optimized request falls through to conservative plans or patches output.
    request = _optimized_request(tmp_path)
    selection = request.starter_selection
    assert selection is not None

    compiled = compile_package(request)
    runtime = {
        surface.file_name: surface.document.to_value()
        for surface in compiled.runtime_surfaces
    }

    assert compiled.decision_snapshot.optimized_start_lowering is not None
    assert runtime["Mulligan.json"]["Mulligan"]["values"] == [
        {
            "comment": (
                "ShadowPriest: starter:"
                f"{selection.selected.document.content_sha256}:"
                "candidate-1:keep-toy-518"
            ),
            "mulligan": "TOY_518",
            "condition": "*",
            "value": "hold",
        }
    ]
    assert runtime["GlobalValues.json"] == selection.selected.globalvalues.to_value()
    assert set(runtime["GlobalValues.json"]) == set(
        GLOBALVALUES_BASELINE_DECISION_KEYS
    )
    assert runtime["EX1_625t.json"]["BeforeUseHeroPowerBonus"]["values"] == [
        {
            "comment": "ShadowPriest: EX1_625t_darkbishop-mind-spike",
            "condition": "*",
            "value": "12",
        }
    ]
    assert "Combo.json" not in runtime
    assert {"Presume.json", "Concede.json", "CardBehavior.json"}.isdisjoint(runtime)

    card_plan = next(
        row.document.to_value()
        for row in compiled.json_projections
        if row.relative_path == "reports/card_behavior_plan_report.json"
    )
    assert card_plan["rows"][0]["authority_id"] == "LLM_OPTIMIZED_START"
    assert card_plan["rows"][0]["source_claim_ids"] == []
    assert compiled.mulligan_plan.rules[0].source_claim_ids == ()
    assert compiled.combo_plan.decisions == ()
    assert any(
        row.kind is GlobalValueDecisionKind.LLM_OPTIMIZED_START
        and row.authority_id
        == f"starter:{selection.selected.document.content_sha256}"
        and row.claim_ids == ()
        for row in compiled.globalvalues_ledger.decisions
    )
    globalvalues_profile = next(
        row.document.to_value()
        for row in compiled.json_projections
        if row.relative_path == "reports/globalvalues_profile.json"
    )
    assert globalvalues_profile["changed_keys"] == ["FirstTurnValueWeight"]
    assert globalvalues_profile["keys"]["FirstTurnValueWeight"] == {
        "authority_id": f"starter:{selection.selected.document.content_sha256}",
        "baseline_value": "0",
        "category": "turn_weight",
        "authority_category": "step1_posture_overlay_allowed",
        "board_value_component": "turn_weight",
        "decision": "llm_optimized_start",
        "new_value": "0.75",
        "reason": "selected optimized starter desired state",
        "status": "llm_optimized_start",
    }

    darkbishop = next(
        row
        for row in compiled.disposition_ledger.cards
        if row.composite_card_key.endswith(":SW_448")
    )
    assert darkbishop.physical_owner == "EX1_625t"
    assert darkbishop.runtime_paths == ("EX1_625t.json",)
    expected_card_claim = (
        f"starter:{selection.selected.document.content_sha256}:"
        "candidate-1:darkbishop-mind-spike"
    )
    expected_mulligan_claim = (
        f"starter:{selection.selected.document.content_sha256}:"
        "candidate-1:keep-toy-518"
    )
    assert darkbishop.evidence_ids == (
        f"starter:{selection.selected.document.content_sha256}",
    )
    assert darkbishop.claim_ids == (expected_card_claim,)
    starter_claims = {
        row.claim_id: row
        for row in compiled.disposition_ledger.claims
        if row.evidence_id.startswith("starter:")
    }
    assert set(starter_claims) == {
        expected_card_claim,
        expected_mulligan_claim,
    }
    assert starter_claims[expected_card_claim].runtime_paths == (
        "EX1_625t.json",
    )
    assert starter_claims[expected_mulligan_claim].runtime_paths == (
        "Mulligan.json",
    )
    assert all(
        not row.runtime_paths
        for row in compiled.disposition_ledger.claims
        if not row.evidence_id.startswith("starter:")
    )
    semantic = compiled.semantic_runtime_ledger.to_value()
    assert semantic["linked_runtime_entities"]["EX1_625t"] == {
        "link_kind": "hero_power_transform",
        "runtime_card_id": "EX1_625t",
        "runtime_emitted": True,
        "runtime_surface": "EX1_625t.json",
        "source_card_id": "SW_448",
    }
    explainability = next(
        row.document.to_value()
        for row in compiled.json_projections
        if row.relative_path == "reports/source_to_runtime_explainability.json"
    )
    assert explainability["runtime_entity_transitions"] == [
        {
            "authority_id": "LLM_OPTIMIZED_START",
            "source_card_id": "SW_448",
            "source_role": "hero_power_transform_source",
            "runtime_card_id": "EX1_625t",
            "runtime_owner_role": "hero_power",
            "link_kind": "hero_power_transform",
            "runtime_file": "EX1_625t.json",
        }
    ]
    explainability_claims = {
        row["claim_id"]: row
        for row in explainability["claim_rows"]
        if row.get("authority_id", "").startswith("starter:")
    }
    assert set(explainability_claims) == {
        expected_card_claim,
        expected_mulligan_claim,
    }
    assert explainability_claims[expected_card_claim][
        "emitted_runtime_files"
    ] == ["EX1_625t.json"]
    assert explainability_claims[expected_card_claim]["source_claim_ids"] == []

    expected = _expected_optimized_documents(request)
    projections = {
        row.relative_path: row.document.canonical_json
        for row in compiled.json_projections
        if row.relative_path in expected
    }
    assert projections == expected


def test_optimized_globalvalues_profile_has_no_step1_overlay_authority(
    tmp_path: Path,
) -> None:
    # Break caught: a synthetic/conservative matrix becomes a second authority.
    request = _optimized_request(tmp_path)
    selection = request.starter_selection
    assert selection is not None

    compiled = compile_package(request)
    state = compiled.decision_snapshot.compiler_state.to_value()
    profile = next(
        row.document.to_value()
        for row in compiled.json_projections
        if row.relative_path == "reports/globalvalues_profile.json"
    )
    runtime = next(
        row.document.to_value()
        for row in compiled.runtime_surfaces
        if row.file_name == "GlobalValues.json"
    )

    assert state["global_values_authority_matrix"] == {
        "allowed_step1_overlays": [],
        "blocked_until_runtime_evidence": [],
    }
    assert profile["expected_overlay_keys"] == []
    assert profile["missing_overlay_keys"] == []
    assert profile["all_expected_overlay_keys_accounted_for"] is True
    assert profile["summary"]["all_expected_overlay_keys_accounted_for"] is True
    assert profile["authority_parity"] == {
        "authorized_overlay_keys": [],
        "emitted_overlay_keys": [],
        "status": "matched",
    }
    assert profile["baseline_overlay_parity"] == {
        "authorized_overlay_keys": [],
        "emitted_overlay_keys": [],
        "status": "matched",
    }
    assert all(
        "claim_id" not in row and "claim_refs" not in row
        for row in profile["keys"].values()
    )
    assert runtime == selection.selected.globalvalues.to_value()
    assert set(runtime) == set(GLOBALVALUES_BASELINE_DECISION_KEYS)


def _add_combo(draft: dict[str, Any]) -> None:
    draft["combo"] = {
        "rule_id": "pressure-sequence",
        "cards": ["TOY_518", "SW_446"],
        "timing": "same_turn",
        "values": ["8", "12"],
        "condition": "*",
    }
    draft["rule_rationales"]["pressure-sequence"] = (
        "Use the ordered same-turn pressure sequence."
    )
    for row in draft["card_dispositions"]:
        if row["card_id"] in {"TOY_518", "SW_446"}:
            row["rule_ids"].append("pressure-sequence")
            row["rule_ids"].sort()
            row["disposition"] = "configured"
            row["reason"] = "Candidate contains a bounded explicit rule."


def test_compile_package_emits_combo_only_for_selected_expressible_combo(
    tmp_path: Path,
) -> None:
    # Break caught: candidate Combo is dropped or an absent Combo is fabricated.
    request = _optimized_request(tmp_path, mutate_selected=_add_combo)

    decisions = compile_package_decisions(request)
    compiled = compile_package(request)
    runtime = {
        surface.file_name: surface.document.to_value()
        for surface in compiled.runtime_surfaces
    }

    assert len(decisions.combo_plan.decisions) == 1
    assert decisions.combo_plan.decisions[0].source_claim_ids == ()
    assert decisions.combo_plan.decisions[0].confidence == "llm_optimized_start"
    assert runtime["Combo.json"]["ComboList"]["values"] == [
        {
            "combo": "TOY_518>>SW_446",
            "comment": "ShadowPriest: pressure-sequence",
            "condition": "*",
            "value": "8>>12",
        }
    ]
