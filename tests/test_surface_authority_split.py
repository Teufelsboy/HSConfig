from hsconfig.source_contract_matrix import source_contract_policy_by_claim_kind
from hsconfig.source_document_builder import build_source_document_bundle
from hsconfig.source_document_model import (
    SUPPORTED_ATOMIC_CLAIM_KINDS,
    can_lower_to_cardid,
    can_lower_to_combo,
    can_lower_to_globalvalues,
    can_lower_to_mulligan,
    normalized_claim_kind,
    runtime_claim_kind,
    surface_gate_decision,
)


def _canonical_posture_bundle():
    deck_identity = {
        "deck_name": "FixtureDeck",
        "deck_fingerprint": "fixture-deck-fingerprint",
        "cards": [{"card_id": "CARD_001", "name": "Fixture Card", "count": 1}],
    }
    return build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=[
            {
                "source_url": "https://example.invalid/fixture-guide",
                "source_title": "Fixture exact-deck guide",
                "source_family": "guide",
                "source_type": "public_guide",
                "retrieved_at": "2026-07-26T00:00:00Z",
                "source_visibility": "full_text",
                "source_lane": "deck_matched_public_guide",
                "deck_match_scope": "exact_deck_matched",
                "deck_match": {
                    "exact_deck_evidence": {
                        "candidate_count": 1,
                        "decoded_candidate_count": 1,
                        "matched": True,
                        "matched_deck_fingerprint": "fixture-deck-fingerprint",
                        "candidate_deck_code_hashes": ["sha256:fixture-source"],
                    }
                },
                "claims": [
                    {
                        "claim_kind": "gameplan_posture",
                        "cards": ["CARD_001"],
                        "scope": "deck",
                        "stance": "aggro_burn",
                        "evidence_text_short": "Use an aggro burn posture.",
                        "source_confidence": "high",
                        "promotion_eligible": True,
                    }
                ],
            }
        ],
        current_date="2026-07-26",
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


def test_effect_only_start_of_game_transform_is_not_opening_hand_keep():
    claim = {
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["SW_448"],
        "evidence_text_short": "Darkbishop Benedictus changes the starting Hero Power.",
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


def test_explicit_opening_hand_start_of_game_transform_can_be_mulligan_keep():
    claim = {
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["CARD_START"],
        "evidence_text_short": "Always keep CARD_START in your opening hand.",
    }
    decision = can_lower_to_mulligan(
        claim,
        card_roles={
            "CARD_START": {
                "roles": ["start_of_game", "hero_power_transform"],
                "semantic_families": ["start_of_game", "hero_power_transform"],
            }
        },
    )

    assert decision.allowed is True
    assert decision.reason == "allowed"


def test_globalvalues_surface_accepts_only_gameplan_posture_and_reports_numeric_runtime_tuning():
    bundle = _canonical_posture_bundle()
    posture = bundle["claims"][0]
    tuning = {
        "claim_kind": "globalvalue_numeric_tuning",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "key": "LowHpBoardValuePenalty",
    }

    assert can_lower_to_globalvalues(
        posture,
        deck_identity={"deck_fingerprint": "fixture-deck-fingerprint"},
        verified_source_receipts=bundle["globalvalues_source_receipts"],
    ).allowed is True
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


def test_contract_policy_allowed_surfaces_match_surface_gate_decisions():
    policy = source_contract_policy_by_claim_kind()
    surfaces = ("mulligan", "globalvalues", "cardid", "combo")
    card_roles = {
        "CARD_001": {
            "roles": ["mulligan_anchor"],
            "semantic_families": [],
        }
    }

    unconditional_allowed = {
        "mulligan_keep": ("mulligan",),
        "mulligan_discard": ("mulligan",),
        "targeting_rule": ("cardid",),
        "combo_sequence": ("combo",),
        "gameplan_posture": ("globalvalues",),
    }

    for claim_kind, row in policy.items():
        claim = {
            "claim_kind": claim_kind,
            "claim_readiness": "guide_backed",
            "trust_ceiling": "runtime_candidate",
            "cards": ["CARD_001"],
        }
        context = {"card_roles": card_roles}
        if claim_kind == "gameplan_posture":
            bundle = _canonical_posture_bundle()
            claim = bundle["claims"][0]
            context["deck_identity"] = {
                "deck_fingerprint": "fixture-deck-fingerprint"
            }
            context["verified_source_receipts"] = bundle[
                "globalvalues_source_receipts"
            ]
        for surface in surfaces:
            decision = surface_gate_decision(
                claim,
                surface,
                context=context,
            )
            expected_unconditional = surface in unconditional_allowed.get(claim_kind, ())
            if expected_unconditional:
                assert decision.allowed is True, (claim_kind, surface, decision.reason)
            elif surface not in row["allowed_surfaces"]:
                assert decision.allowed is False, (claim_kind, surface)
