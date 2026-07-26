from hsconfig.globalvalues_key_authority import authority_for_key
from hsconfig.globalvalues_authority import build_globalvalues_authority_matrix
from hsconfig.source_document_model import can_lower_to_globalvalues


def test_globalvalues_key_authority_classifies_core_keys():
    assert authority_for_key("FirstTurnValueWeight")["category"] == "step1_posture_overlay_allowed"
    assert authority_for_key("SecondTurnValueWeight")["category"] == "step1_posture_overlay_allowed"
    assert authority_for_key("MyHeroPowerValue")["category"] == "step1_posture_overlay_allowed"
    assert authority_for_key("OpponentSpecificMatchupTuning")["category"] == "runtime_evidence_required"


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


def test_globalvalues_rows_use_lifecycle_claim_id_without_rewriting_claim_refs():
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="baseline",
        claims=[
            {
                "claim_id": "raw_posture",
                "claim_kind": "gameplan_posture",
                "stance": "weapon_pressure",
                "_claim_lifecycle": {
                    "claim_id": "lifecycle_posture",
                    "surface": "globalvalues",
                },
            },
            {
                "claim_id": "raw_numeric",
                "claim_kind": "globalvalue_numeric_tuning",
                "key": "LowHpBoardValuePenalty",
                "_claim_lifecycle": {
                    "claim_id": "lifecycle_numeric",
                    "surface": "globalvalues",
                },
            },
        ],
    )

    allowed = {row["key"]: row for row in matrix["allowed_step1_overlays"]}
    assert allowed["MyWeaponValue"]["claim_id"] == "lifecycle_posture"
    assert allowed["MyWeaponValue"]["claim_refs"] == ["raw_posture"]

    numeric_row = next(
        row
        for row in matrix["blocked_until_runtime_evidence"]
        if row["key"] == "LowHpBoardValuePenalty"
        and row.get("claim_refs") == ["raw_numeric"]
    )
    assert numeric_row["claim_id"] == "lifecycle_numeric"


def test_globalvalues_authority_matrix_embeds_per_key_authority():
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="aggressive",
        claims=[{"claim_kind": "gameplan_posture", "stance": "aggressive", "claim_confidence": "high"}],
    )

    allowed = {row["key"]: row for row in matrix["allowed_step1_overlays"]}
    blocked = {row["key"]: row for row in matrix["blocked_until_runtime_evidence"]}

    assert allowed["FirstTurnValueWeight"]["key_authority"] == authority_for_key("FirstTurnValueWeight")
    assert allowed["MyHeroPowerValue"]["key_authority"] == authority_for_key("MyHeroPowerValue")
    assert blocked["OpponentSpecificMatchupTuning"]["key_authority"] == authority_for_key(
        "OpponentSpecificMatchupTuning"
    )


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


def test_posture_overlay_matrix_supports_named_step1_postures():
    cases = {
        "aggro_burn": {"FirstTurnValueWeight", "MyHeroPowerValue"},
        "token_board": {"GlobalMinionAttack", "GlobalMinionIntrinsicValue"},
        "weapon_pressure": {"MyWeaponValue"},
        "deathrattle_recruit": {"GlobalMinionIntrinsicValue"},
        "control_value": {"SecondTurnValueWeight"},
    }

    for posture, expected_keys in cases.items():
        matrix = build_globalvalues_authority_matrix(
            aggression_profile=posture,
            claims=[
                {
                    "claim_kind": "gameplan_posture",
                    "stance": posture,
                    "claim_id": f"claim_{posture}",
                }
            ],
        )

        rows_by_key = {row["key"]: row for row in matrix["allowed_step1_overlays"]}
        assert expected_keys <= set(rows_by_key), posture
        for key in expected_keys:
            assert rows_by_key[key]["operation"] in {"set", "increase", "decrease"}
            assert "reason" in rows_by_key[key]


def test_unknown_posture_keeps_baseline_default():
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="unknown",
        claims=[{"claim_kind": "gameplan_posture", "stance": "unknown"}],
    )

    assert matrix["allowed_step1_overlays"] == [
        {
            "key": "baseline",
            "overlay": "none",
            "operation": "none",
            "value": None,
            "authority": "baseline_default",
            "key_authority": authority_for_key("baseline"),
            "claim_refs": [],
            "reason": "no_source_backed_posture_overlay",
        }
    ]


def test_source_posture_claim_overrides_generic_aggro_profile():
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="aggro",
        claims=[
            {
                "claim_kind": "gameplan_posture",
                "stance": "weapon_pressure",
                "claim_id": "claim_weapon",
            }
        ],
    )

    allowed = {row["key"] for row in matrix["allowed_step1_overlays"]}
    assert matrix["posture"] == "weapon_pressure"
    assert "MyWeaponValue" in allowed
    assert "MyHeroPowerValue" not in allowed


def test_globalvalues_ignores_card_role_claims_even_when_source_backed():
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="unknown",
        claims=[
            {
                "claim_kind": "card_role",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_candidate",
                "stance": "aggro_burn",
                "cards": ["CARD_001"],
            }
        ],
    )

    assert matrix["posture"] == "baseline"
    assert matrix["allowed_step1_overlays"][0]["reason"] == "no_source_backed_posture_overlay"


def test_globalvalues_ignores_aggro_profile_without_authorized_posture_claims():
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="aggro",
        claims=[
            {
                "claim_kind": "card_role",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_candidate",
                "stance": "aggro_burn",
                "cards": ["CARD_001"],
                "source_refs": ["guide:1"],
            }
        ],
    )

    assert matrix["posture"] == "baseline"
    assert matrix["allowed_step1_overlays"] == [
        {
            "key": "baseline",
            "overlay": "none",
            "operation": "none",
            "value": None,
            "authority": "baseline_default",
            "key_authority": authority_for_key("baseline"),
            "claim_refs": [],
            "reason": "no_source_backed_posture_overlay",
        }
    ]


def _public_guide_posture_claim(
    *,
    deck_match_scope: str,
    source_lane: str,
) -> dict[str, object]:
    return {
        "claim_id": f"{deck_match_scope}-posture",
        "claim_kind": "gameplan_posture",
        "stance": "aggressive",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "source_type": "public_guide",
        "source_family": "guide",
        "deck_match_scope": deck_match_scope,
        "promotion_eligible": True,
        "source_visibility": "full_text",
        "source_lane": source_lane,
        "source_refs": [f"guide:{deck_match_scope}"],
    }


def test_archetype_only_public_guide_posture_is_visibly_suppressed() -> None:
    claim = _public_guide_posture_claim(
        deck_match_scope="archetype_matched",
        source_lane="archetype_matched_public_guide",
    )

    decision = can_lower_to_globalvalues(claim)
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="aggressive",
        claims=[claim],
    )

    assert decision.allowed is False
    assert decision.reason == "globalvalues_requires_exact_deck_match"
    assert matrix["posture"] == "baseline"
    assert matrix["allowed_step1_overlays"][0]["reason"] == (
        "no_source_backed_posture_overlay"
    )
    suppression = next(
        row
        for row in matrix["blocked_until_runtime_evidence"]
        if row.get("claim_refs") == [
            "archetype_matched-posture",
            "guide:archetype_matched",
        ]
    )
    assert suppression["authority"] == "source_contract_suppressed"
    assert suppression["reason"] == "globalvalues_requires_exact_deck_match"


def test_exact_public_guide_posture_remains_authorized() -> None:
    claim = _public_guide_posture_claim(
        deck_match_scope="exact_deck_matched",
        source_lane="deck_matched_public_guide",
    )

    decision = can_lower_to_globalvalues(claim)
    matrix = build_globalvalues_authority_matrix(
        aggression_profile="aggressive",
        claims=[claim],
    )

    assert decision.allowed is True
    assert decision.reason == "allowed"
    assert matrix["posture"] == "aggro"
    assert {
        row["key"] for row in matrix["allowed_step1_overlays"]
    } >= {"FirstTurnValueWeight", "MyHeroPowerValue"}
    assert not any(
        row.get("authority") == "source_contract_suppressed"
        for row in matrix["blocked_until_runtime_evidence"]
    )
