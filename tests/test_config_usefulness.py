from hsconfig.config_usefulness import build_config_usefulness


def test_config_usefulness_marks_rich_source_backed_package_guide_aligned():
    payload = build_config_usefulness(
        technical_status="VALID_PACKAGE",
        semantic_status="SOURCE_BACKED_STRONG",
        config_readiness_summary={
            "total_cards": 3,
            "runtime_emitted": 3,
            "mulligan_only": 0,
            "globalvalues_only": 0,
            "report_only_supported": 0,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        config_readiness_report={"cards": {}},
        mulligan_plan_report={
            "rules": [{"action": "keep", "card": "CARD_A"}],
            "suppressed_rules": [],
            "quality": {"has_concrete_keeps": True},
        },
        card_behavior_plan_report={
            "rows": [
                {
                    "card_id": "CARD_A",
                    "surface_family": "CARDID.json",
                    "meaningful_runtime_surface": True,
                    "behavior_block": {"BeforePlayCardBonus": {"values": []}},
                },
                {
                    "card_id": "CARD_B",
                    "surface_family": "CARDID.json",
                    "meaningful_runtime_surface": True,
                    "behavior_block": {"OnBoardBonus": {"values": []}},
                },
            ]
        },
        combo_plan_report={"combos": [{"cards": ["CARD_A", "CARD_B"]}], "suppressed": []},
        globalvalues_profile_report={
            "changed_keys": ["FirstTurnValueWeight", "SecondTurnValueWeight"],
            "unchanged_keys": ["EnemySecretValue"],
        },
    )

    assert payload["status"] == "guide_aligned"
    assert payload["runtime_permission_impact"] == "none"
    assert payload["surfaces"]["mulligan"]["status"] == "rich"
    assert payload["surfaces"]["cardid_behavior"]["meaningful_cardid_row_count"] == 2
    assert payload["surfaces"]["globalvalues"]["changed_key_count"] == 2
    assert payload["surfaces"]["combo"]["status"] == "rich"
    assert payload["first_usefulness_gap"] == "none"


def test_config_usefulness_marks_source_gap_package_usable_with_targeted_gaps():
    payload = build_config_usefulness(
        technical_status="VALID_PACKAGE",
        semantic_status="VALID_BUT_NOT_GUIDE_STRONG",
        config_readiness_summary={
            "total_cards": 10,
            "runtime_emitted": 8,
            "mulligan_only": 1,
            "globalvalues_only": 0,
            "report_only_supported": 1,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 1,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        config_readiness_report={"cards": {}},
        mulligan_plan_report={
            "rules": [{"action": "keep", "card": "CARD_A"}],
            "suppressed_rules": [{"card_id": "CARD_B", "reason": "claim_not_runtime_lowerable"}],
            "quality": {"has_concrete_keeps": True},
        },
        card_behavior_plan_report={"rows": []},
        combo_plan_report={"combos": [], "suppressed": []},
        globalvalues_profile_report={"changed_keys": ["FirstTurnValueWeight"]},
    )

    assert payload["status"] == "usable_with_targeted_gaps"
    assert payload["first_usefulness_gap"] == "mulligan_gap"
    assert payload["next_report_to_open"] == "reports/mulligan_plan_report.json"


def test_config_usefulness_surfaces_actionable_nonblocking_mulligan_gap():
    payload = build_config_usefulness(
        technical_status="VALID_PACKAGE",
        semantic_status="VALID_BUT_NOT_GUIDE_STRONG",
        config_readiness_summary={
            "total_cards": 10,
            "runtime_emitted": 8,
            "report_only_supported": 0,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 1,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        mulligan_plan_report={
            "rules": [],
            "suppressed_rules": [
                {"card": "CARD_A", "reason": "unsupported_mulligan_condition"}
            ],
            "quality": {
                "has_concrete_keeps": False,
                "status": "thin",
                "first_gap_reason": "unsupported_mulligan_condition",
                "source_backed_rule_count": 0,
                "suppressed_rule_count": 1,
                "suppressed_reasons": {"unsupported_mulligan_condition": 1},
            },
        },
        card_behavior_plan_report={"rows": [{"meaningful_runtime_surface": True, "behavior_block": {"x": []}}]},
        combo_plan_report={"combos": [], "suppressed": []},
        globalvalues_profile_report={"changed_keys": ["FirstTurnValueWeight"]},
    )

    mulligan = payload["surfaces"]["mulligan"]
    assert payload["blocking"] is False
    assert payload["runtime_permission_impact"] == "none"
    assert payload["first_usefulness_gap"] == "mulligan_gap"
    assert mulligan["status"] == "thin"
    assert mulligan["first_gap_reason"] == "unsupported_mulligan_condition"
    assert mulligan["next_source_need"] == "source_backed_or_policy_backed_mulligan_keeps"
    assert mulligan["suppressed_reasons"] == {"unsupported_mulligan_condition": 1}


def test_policy_backed_mulligan_is_not_default_only_or_blocking():
    result = build_config_usefulness(
        technical_status="VALID_PACKAGE",
        semantic_status="STATIC_SEMANTICS_USABLE",
        config_readiness_summary={},
        mulligan_plan_report={
            "rules": [
                {
                    "card": "CARD_1",
                    "action": "hold",
                    "selector_kind": "card",
                    "source_type": "policy_backed_autonomous_mulligan",
                }
            ],
            "quality": {
                "status": "policy_backed",
                "has_concrete_keeps": True,
                "source_backed_rule_count": 0,
                "source_backed_keep_rule_count": 0,
                "policy_backed_rule_count": 1,
                "policy_backed_keep_rule_count": 1,
                "first_gap_reason": "policy_backed_autonomous_mulligan",
            },
        },
        card_behavior_plan_report={"rows": []},
        combo_plan_report={"combos": []},
        globalvalues_profile_report={"changed_keys": [], "unchanged_keys": []},
    )

    mulligan = result["surfaces"]["mulligan"]
    assert mulligan["status"] == "policy_backed"
    assert mulligan["default_only"] is False
    assert mulligan["next_source_need"] == "none"
    assert mulligan["policy_backed_rule_count"] == 1
    assert result["blocking"] is False


def test_config_usefulness_marks_valid_sparse_package_load_safe_but_thin():
    payload = build_config_usefulness(
        technical_status="VALID_PACKAGE",
        semantic_status="STATIC_SEMANTICS_USABLE",
        config_readiness_summary={
            "total_cards": 10,
            "runtime_emitted": 1,
            "mulligan_only": 0,
            "globalvalues_only": 0,
            "report_only_supported": 8,
            "generic_low_confidence": 1,
            "cards_needing_guide_claims": 1,
            "cards_needing_runtime_surface": 5,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        config_readiness_report={"cards": {}},
        mulligan_plan_report={"rules": [], "suppressed_rules": [], "quality": {"has_concrete_keeps": False}},
        card_behavior_plan_report={"rows": []},
        combo_plan_report={"combos": [], "suppressed": []},
        globalvalues_profile_report={"changed_keys": [], "unchanged_keys": ["EnemySecretValue"]},
    )

    assert payload["status"] == "load_safe_but_thin"
    assert payload["surfaces"]["mulligan"]["default_only"] is True
    assert payload["surfaces"]["globalvalues"]["status"] == "thin"
    assert payload["surfaces"]["cardid_behavior"]["status"] == "report_only"
    assert payload["first_usefulness_gap"] == "runtime_surface_gap"


def test_config_usefulness_marks_report_only_cardid_surface_when_only_report_only_support_exists():
    payload = build_config_usefulness(
        technical_status="VALID_PACKAGE",
        semantic_status="STATIC_SEMANTICS_USABLE",
        config_readiness_summary={
            "total_cards": 4,
            "runtime_emitted": 0,
            "mulligan_only": 0,
            "globalvalues_only": 0,
            "report_only_supported": 2,
            "generic_low_confidence": 0,
            "cards_needing_guide_claims": 0,
            "cards_needing_runtime_surface": 0,
            "cards_needing_mulligan_claims": 0,
            "cards_needing_combo_sequence": 0,
            "cards_needing_condition_lowering": 0,
            "cards_needing_mechanic_lowering": 0,
        },
        config_readiness_report={"cards": {}},
        mulligan_plan_report={"rules": [], "suppressed_rules": [], "quality": {"has_concrete_keeps": False}},
        card_behavior_plan_report={"rows": []},
        combo_plan_report={"combos": [], "suppressed": []},
        globalvalues_profile_report={"changed_keys": [], "unchanged_keys": []},
    )

    assert payload["surfaces"]["cardid_behavior"]["status"] == "report_only"
    assert payload["surfaces"]["cardid_behavior"]["meaningful_cardid_row_count"] == 0


def test_config_usefulness_marks_invalid_package_without_affecting_gate_fields():
    payload = build_config_usefulness(
        technical_status="INVALID_PACKAGE",
        semantic_status="INVALID_PACKAGE",
        config_readiness_summary={},
        config_readiness_report={},
        mulligan_plan_report={},
        card_behavior_plan_report={},
        combo_plan_report={},
        globalvalues_profile_report={},
    )

    assert payload["status"] == "invalid_package"
    assert payload["headline"] == "Package is technically invalid; config richness is not evaluated."
    assert payload["runtime_permission_impact"] == "none"
