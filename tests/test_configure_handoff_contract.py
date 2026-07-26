from __future__ import annotations

from hsconfig.commands.configure import _build_handoff_contract


def test_handoff_contract_reports_clean_single_authority_package() -> None:
    contract = _build_handoff_contract(
        operator_summary={
            "runtime_apply_contract": {
                "apply_authority": "reports/operator_summary.json",
            },
            "source_status_apply_blocking": False,
            "first_missing_source_action": "none",
        },
        acceptance_summary={
            "use_config_now": True,
            "normal_apply_authority": "reports/operator_summary.json",
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "technical_status": "VALID_PACKAGE",
            "source_strength": "SOURCE_BACKED_STRONG",
            "source_gaps_apply_blocking": False,
            "default_only_clean": True,
            "default_only_runtime_surfaces": [],
            "next_report_to_open": "reports/operator_summary.json",
        },
        config_proof_summary={
            "authority": "diagnostic_only",
            "apply_blocking": False,
            "normal_apply_authority": "reports/operator_summary.json",
            "no_default_only_clean": True,
            "default_only_runtime_surfaces": [],
            "forbidden_normal_surfaces_absent": True,
            "forbidden_normal_surfaces_status": "clean",
            "runtime_surface_boundary": [
                "GlobalValues.json",
                "Mulligan.json",
                "per-card <CARDID>.json",
                "Combo.json",
            ],
            "darkbishop_boundary_status": "effect_without_mulligan_keep",
            "source_to_runtime_status": "clean",
            "currentness_status": "clean",
            "closure_schema_current": True,
            "cards_missing_closure": 0,
            "semantic_intent_status": "clean",
            "surface_intent_status": "clean",
            "surface_intent_present": True,
            "surface_intent_surface_count": 3,
            "surface_intent_fallback_intent_rows": 0,
            "surface_intent_legacy_policy_surface_rows": [],
            "surface_intent_first_attention": None,
            "runtime_json_status": "clean",
        },
        config_quality_summary={
            "status": "clean",
            "problem_checks": [],
            "mechanic_runtime_discipline_status": "clean",
        },
    )

    assert contract == {
        "schema_version": 1,
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "status": "clean",
        "normal_apply_authority": "reports/operator_summary.json",
        "single_apply_authority_confirmed": True,
        "load_safe_to_install": True,
        "use_config_now": True,
        "use_config_now_scope": "load_safety_only",
        "semantic_handoff_status": "closed",
        "semantic_handoff_reasons": [],
        "runtime_apply_allowed": True,
        "runtime_apply_mode": "load_safe_apply",
        "technical_status": "VALID_PACKAGE",
        "source_strength": "SOURCE_BACKED_STRONG",
        "source_status_apply_blocking": False,
        "source_gaps_apply_blocking": False,
        "first_missing_source_action": "none",
        "default_only_clean": True,
        "default_only_runtime_surfaces": [],
        "forbidden_normal_surfaces_absent": True,
        "forbidden_normal_surfaces_status": "clean",
        "runtime_surface_boundary": [
            "GlobalValues.json",
            "Mulligan.json",
            "per-card <CARDID>.json",
            "Combo.json",
        ],
        "darkbishop_boundary_status": "effect_without_mulligan_keep",
        "runtime_json_status": "clean",
        "source_to_runtime_status": "clean",
        "currentness_status": "clean",
        "closure_schema_current": True,
        "cards_missing_closure": 0,
        "semantic_intent_status": "clean",
        "surface_intent_status": "clean",
        "surface_intent_present": True,
        "surface_intent_surface_count": 3,
        "surface_intent_fallback_intent_rows": 0,
        "surface_intent_legacy_policy_surface_rows": [],
        "surface_intent_first_attention": None,
        "mechanic_runtime_discipline_status": "clean",
        "config_quality_status": "clean",
        "config_quality_problem_checks": [],
        "next_report_to_open": "reports/operator_summary.json",
    }


def test_handoff_contract_surfaces_attention_without_blocking_apply() -> None:
    contract = _build_handoff_contract(
        operator_summary={
            "runtime_apply_contract": {
                "apply_authority": "reports/operator_summary.json",
            },
            "source_status_apply_blocking": False,
            "first_missing_source_action": "fetch_and_normalize_candidate_full_text_claims",
        },
        acceptance_summary={
            "use_config_now": True,
            "normal_apply_authority": "reports/operator_summary.json",
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "technical_status": "VALID_PACKAGE",
            "source_strength": "SOURCE_BACKED_PARTIAL",
            "source_gaps_apply_blocking": False,
            "default_only_clean": False,
            "default_only_runtime_surfaces": ["Mulligan.json"],
            "next_report_to_open": "reports/contract_doctor.json",
        },
        config_proof_summary={
            "authority": "diagnostic_only",
            "apply_blocking": False,
            "normal_apply_authority": "reports/operator_summary.json",
            "no_default_only_clean": False,
            "default_only_runtime_surfaces": ["Mulligan.json"],
            "forbidden_normal_surfaces_absent": False,
            "forbidden_normal_surfaces_status": "attention",
            "runtime_surface_boundary": [
                "GlobalValues.json",
                "Mulligan.json",
                "per-card <CARDID>.json",
                "Combo.json",
            ],
            "darkbishop_boundary_status": "mulligan_keep_present",
            "source_to_runtime_status": "attention",
            "currentness_status": "attention",
            "closure_schema_current": False,
            "cards_missing_closure": 2,
            "semantic_intent_status": "attention",
            "surface_intent_status": "attention",
            "surface_intent_present": True,
            "surface_intent_surface_count": 4,
            "surface_intent_fallback_intent_rows": 1,
            "surface_intent_legacy_policy_surface_rows": ["Presume.json"],
            "surface_intent_first_attention": "surface_intent_fallback_visible",
            "runtime_json_status": "attention",
        },
        config_quality_summary={
            "status": "attention",
            "problem_checks": ["operator_default_only_runtime_surfaces"],
            "mechanic_runtime_discipline_status": "attention",
        },
    )

    assert contract["status"] == "attention"
    assert contract["apply_blocking"] is False
    assert contract["source_status_apply_blocking"] is False
    assert contract["single_apply_authority_confirmed"] is True
    assert contract["default_only_clean"] is False
    assert contract["default_only_runtime_surfaces"] == ["Mulligan.json"]
    assert contract["next_report_to_open"] == "reports/contract_doctor.json"
    assert contract["surface_intent_status"] == "attention"
    assert contract["surface_intent_present"] is True
    assert contract["surface_intent_surface_count"] == 4
    assert contract["surface_intent_fallback_intent_rows"] == 1
    assert contract["surface_intent_legacy_policy_surface_rows"] == ["Presume.json"]
    assert contract["surface_intent_first_attention"] == (
        "surface_intent_fallback_visible"
    )
