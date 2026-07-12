from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_document_model import (
    SUPPORTED_ATOMIC_CLAIM_KINDS,
    can_lower_to_cardid,
    can_lower_to_combo,
    can_lower_to_globalvalues,
    can_lower_to_mulligan,
    normalized_claim_kind,
    runtime_claim_kind,
)


def test_normalized_claim_kind_keeps_exact_legacy_compatibility():
    assert normalized_claim_kind({"claim_type": "combo"}) == "combo_sequence"
    assert normalized_claim_kind({"claim_type": "bad_pattern"}) == "known_bad_pattern"
    assert normalized_claim_kind({"claim_type": "mulligan_throw"}) == "mulligan_discard"
    assert normalized_claim_kind({"claim_type": "mulligan_and_gameplan"}) == ""
    assert runtime_claim_kind({"claim_type": "combo"}) == "combo_sequence"


def test_mulligan_surface_accepts_only_explicit_mulligan_claims():
    keep = {
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["CARD_001"],
    }
    effect = {
        "claim_kind": "hero_power_transform",
        "claim_readiness": "source_backed_static_semantics",
        "trust_ceiling": "runtime_candidate",
        "cards": ["SW_448"],
    }

    assert can_lower_to_mulligan(keep).allowed is True
    decision = can_lower_to_mulligan(effect)
    assert decision.allowed is False
    assert decision.reason == "claim_kind_not_mulligan_surface"


def test_start_of_game_transform_is_never_opening_hand_keep_even_when_claim_says_keep():
    claim = {
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["SW_448"],
    }
    decision = can_lower_to_mulligan(
        claim,
        card_roles={
            "SW_448": {
                "roles": ["start_of_game", "hero_power_transform"],
                "semantic_families": ["start_of_game", "hero_power_transform"],
            }
        },
    )

    assert decision.allowed is False
    assert decision.reason == "start_of_game_effect_does_not_require_opening_hand"


def test_globalvalues_surface_accepts_only_gameplan_posture_and_reports_numeric_runtime_tuning():
    posture = {
        "claim_kind": "gameplan_posture",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "stance": "aggro_burn",
    }
    tuning = {
        "claim_kind": "globalvalue_numeric_tuning",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "key": "LowHpBoardValuePenalty",
    }

    assert can_lower_to_globalvalues(posture).allowed is True
    decision = can_lower_to_globalvalues(tuning)
    assert decision.allowed is False
    assert decision.reason == "requires_runtime_evidence"


def test_combo_surface_accepts_only_combo_sequences():
    combo = {
        "claim_kind": "combo_sequence",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["A", "B"],
    }
    card_role = {
        "claim_kind": "card_role",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["A"],
    }

    assert can_lower_to_combo(combo).allowed is True
    decision = can_lower_to_combo(card_role)
    assert decision.allowed is False
    assert decision.reason == "claim_kind_not_combo_surface"


def test_cardid_surface_accepts_behavior_claims_but_not_mulligan_or_globalvalues():
    targeting = {
        "claim_kind": "targeting_rule",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["CARD_001"],
    }
    mulligan = {
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["CARD_001"],
    }

    assert can_lower_to_cardid(targeting).allowed is True
    decision = can_lower_to_cardid(mulligan)
    assert decision.allowed is False
    assert decision.reason == "claim_kind_not_cardid_surface"


def test_every_supported_claim_kind_has_contract_policy():
    policy = source_contract_policy_by_claim_kind()

    assert set(policy) == set(SUPPORTED_ATOMIC_CLAIM_KINDS)
    for claim_kind, row in policy.items():
        assert row["lane"] in {
            "runtime_lowerable",
            "runtime_evidence_required",
            "report_only",
            "suppressed_or_conditional",
        }, claim_kind
        assert isinstance(row["allowed_surfaces"], tuple), claim_kind
        assert all(
            surface in {"mulligan", "globalvalues", "cardid", "combo"}
            for surface in row["allowed_surfaces"]
        ), claim_kind
        assert row["operator_meaning"], claim_kind


def test_contract_policy_keeps_numeric_tuning_and_start_effect_boundaries_explicit():
    policy = source_contract_policy_by_claim_kind()

    assert policy["globalvalue_numeric_tuning"]["lane"] == "runtime_evidence_required"
    assert policy["globalvalue_numeric_tuning"]["allowed_surfaces"] == ()
    assert policy["hero_power_transform"]["lane"] == "suppressed_or_conditional"
    assert policy["hero_power_transform"]["allowed_surfaces"] == ("cardid",)
    assert "not a mulligan keep" in policy["hero_power_transform"]["operator_meaning"]
