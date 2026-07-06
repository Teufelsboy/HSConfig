from hsconfig.globalvalues_authority import build_globalvalues_authority_matrix


def test_aggressive_posture_allows_selected_step1_keys():
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="aggressive",
        claims=[{"claim_kind": "gameplan_posture", "stance": "aggressive", "claim_confidence": "high"}],
    )

    allowed = {row["key"] for row in matrix["allowed_step1_overlays"]}
    blocked = {row["key"] for row in matrix["blocked_until_runtime_evidence"]}
    assert "FirstTurnValueWeight" in allowed
    assert "SecondTurnValueWeight" in allowed
    assert "LowHpBoardValuePenalty" in blocked


def test_runtime_only_numeric_tuning_is_reported_not_applied():
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="aggressive",
        claims=[
            {
                "claim_kind": "globalvalue_numeric_tuning",
                "stance": "decrease_low_hp_penalty",
                "cards": [],
                "claim_confidence": "medium",
            }
        ],
    )

    assert any(
        row["reason"] == "requires_runtime_evidence"
        for row in matrix["blocked_until_runtime_evidence"]
    )
