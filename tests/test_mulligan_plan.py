from hsconfig.compile_mulligan import compile_mulligan
from hsconfig.mulligan_plan import build_mulligan_plan as _build_mulligan_plan
from hsconfig.source_document_model import (
    globalvalues_claim_signature,
    normalized_claim_kind,
)
from tests.helpers.live_acquisition import acquire_live_test_provenance


_TEST_DECK_FINGERPRINT = "sha256:mulligan-plan-unit-fixture"


def build_mulligan_plan(**kwargs):
    claims = []
    receipts = []
    for raw_claim in kwargs.get("claims", []):
        claim = dict(raw_claim)
        if normalized_claim_kind(claim) in {
            "mulligan_keep",
            "mulligan_discard",
        }:
            claim.setdefault("source_family", "guide")
            claim.setdefault("deck_match_scope", "exact_deck_matched")
            claim.setdefault("promotion_eligible", True)
            claim.setdefault("source_visibility", "full_text")
            claim.setdefault("source_lane", "deck_matched_public_guide")
            claim.setdefault(
                "acquisition_provenance",
                acquire_live_test_provenance(),
            )
            claim.setdefault(
                "deck_match",
                {
                    "exact_deck_evidence": {
                        "candidate_count": 1,
                        "decoded_candidate_count": 1,
                        "matched": True,
                        "matched_deck_fingerprint": _TEST_DECK_FINGERPRINT,
                        "candidate_deck_code_hashes": [
                            "sha256:mulligan-plan-unit-source"
                        ],
                    }
                },
            )
            receipts.append(
                {
                    "receipt_kind": "canonical_exact_deck_source_document",
                    "matched_deck_fingerprint": _TEST_DECK_FINGERPRINT,
                    "claim_id": str(claim.get("claim_id", "")),
                    "claim_signature": globalvalues_claim_signature(claim),
                    "acquisition_provenance": claim[
                        "acquisition_provenance"
                    ],
                }
            )
        claims.append(claim)
    return _build_mulligan_plan(
        **{
            **kwargs,
            "claims": claims,
            "deck_identity": {
                "deck_fingerprint": _TEST_DECK_FINGERPRINT,
            },
            "verified_source_receipts": receipts,
        }
    )


def test_mulligan_plan_reports_non_mulligan_claim_surface_rejection():
    plan = build_mulligan_plan(
        deck_name="ShadowPriest",
        claims=[
            {
                "claim_kind": "hero_power_transform",
                "claim_readiness": "source_backed_static_semantics",
                "trust_ceiling": "runtime_candidate",
                "cards": ["SW_448"],
                "claim_id": "darkbishop_transform",
            }
        ],
        card_roles={
            "SW_448": {
                "roles": ["start_of_game", "hero_power_transform"],
                "semantic_families": ["start_of_game", "hero_power_transform"],
            }
        },
    )

    assert plan["rules"] == []
    assert plan["suppressed_rules"][0]["reason"] == "claim_kind_not_mulligan_surface"
    assert plan["suppressed_rules"][0]["card"] == "SW_448"
    assert plan["quality"]["first_gap_reason"] == "no_source_backed_mulligan_keeps"


def test_mulligan_plan_rows_use_lifecycle_claim_id_without_rewriting_source_claim_ids():
    plan = build_mulligan_plan(
        deck_name="Deck",
        claims=[
            {
                "claim_id": "raw_keep",
                "claim_kind": "mulligan_keep",
                "cards": ["CARD_A"],
                "source_claim_ids": ["raw_keep"],
                "_claim_lifecycle": {
                    "claim_id": "lifecycle_keep",
                    "surface": "mulligan",
                },
            },
            {
                "claim_id": "raw_bad_selector",
                "claim_kind": "mulligan_keep",
                "cards": ["CARD_B"],
                "selector": "CARD_B | CARD_C",
                "source_claim_ids": ["raw_bad_selector"],
                "_claim_lifecycle": {
                    "claim_id": "lifecycle_bad_selector",
                    "surface": "mulligan",
                },
            },
        ],
        card_roles={},
    )

    rule = next(row for row in plan["rules"] if row["card"] == "CARD_A")
    assert rule["claim_id"] == "lifecycle_keep"
    assert rule["source_claim_ids"] == ["raw_keep"]

    suppressed = plan["suppressed_rules"][0]
    assert suppressed["claim_id"] == "lifecycle_bad_selector"
    assert suppressed["source_claim_ids"] == ["raw_bad_selector"]


def test_mulligan_plan_rejects_start_of_game_deckbuilding_modifier_keep():
    plan = build_mulligan_plan(
        deck_name="RenathalDeck",
        claims=[
            {
                "claim_kind": "mulligan_keep",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_candidate",
                "cards": ["REV_018"],
                "claim_id": "renathal_effect_keep",
            }
        ],
        card_roles={
            "REV_018": {
                "roles": ["start_of_game", "deckbuilding_modifier"],
                "semantic_families": ["start_of_game", "deckbuilding_modifier"],
            }
        },
    )

    assert plan["rules"] == []
    assert plan["suppressed_rules"] == [
        {
            "card": "REV_018",
            "action": "hold",
            "reason": "start_of_game_effect_does_not_require_opening_hand",
            "source_claim_ids": ["renathal_effect_keep"],
            "claim_id": "renathal_effect_keep",
        }
    ]
    assert plan["quality"]["first_gap_reason"] == (
        "start_of_game_effect_does_not_require_opening_hand"
    )


def test_mulligan_plan_has_concrete_keeps_before_wildcard_discard():
    claims = [
        {"claim_kind": "mulligan_keep", "cards": ["SW_448"], "stance": "keep", "claim_confidence": "high"},
        {
            "claim_kind": "mulligan_keep",
            "cards": ["CARD_002"],
            "stance": "keep",
            "claim_confidence": "medium",
        },
    ]

    plan = build_mulligan_plan(deck_name="ShadowPriest", claims=claims, card_roles={})

    assert [row["card"] for row in plan["rules"][:2]] == ["SW_448", "CARD_002"]
    assert plan["rules"][-1] == {
        "card": "*",
        "selector_kind": "wildcard",
        "selector": "*",
        "action": "discard",
        "condition": "*",
        "reason": "discard_unlisted_cards_after_source_backed_keeps",
    }
    assert plan["quality"]["has_concrete_keeps"] is True


def test_mulligan_plan_blocks_lone_wildcard_discard():
    plan = build_mulligan_plan(deck_name="UnknownDeck", claims=[], card_roles={})

    assert plan["rules"] == []
    assert plan["quality"]["blocked_reason"] == "no_source_backed_mulligan_keeps"


def test_mulligan_plan_does_not_create_holds_from_early_roles_without_source_claims():
    plan = build_mulligan_plan(
        deck_name="CurveDeck",
        claims=[],
        card_roles={
            "CARD_001": {
                "roles": ["one_drop", "early_pressure"],
                "confidence": "archetype_inferred",
                "source_claim_ids": [],
            }
        },
    )

    assert plan["rules"] == []
    assert plan["quality"]["status"] == "thin"
    assert plan["quality"]["first_gap_reason"] == "no_source_backed_mulligan_keeps"
    assert plan["quality"]["source_backed_rule_count"] == 0


def test_mulligan_plan_preserves_multiple_conditions_for_same_card():
    claims = [
        {
            "claim_kind": "mulligan_keep",
            "cards": ["SW_448"],
            "conditions": {"coin": True},
            "claim_id": "keep_coin",
        },
        {
            "claim_kind": "mulligan_discard",
            "cards": ["SW_448"],
            "conditions": {"nocoin": True},
            "claim_id": "discard_no_coin",
        },
    ]

    plan = build_mulligan_plan(deck_name="ShadowPriest", claims=claims, card_roles={})

    sw448_rules = [row for row in plan["rules"] if row["card"] == "SW_448"]
    assert [(row["action"], row["condition"]) for row in sw448_rules] == [
        ("hold", "coin"),
        ("discard", "nocoin"),
    ]
    assert plan["suppressed_rules"] == []


def test_mulligan_plan_merges_runtime_duplicate_source_keeps_preserving_provenance():
    claims = [
        {
            "claim_kind": "mulligan_keep",
            "cards": ["SW_444"],
            "conditions": "*",
            "claim_id": "keep_twilight_guide_a",
            "source_claim_ids": ["raw_keep_twilight_a"],
            "evidence_text_short": "Keep Twilight Deceptor",
        },
        {
            "claim_kind": "mulligan_keep",
            "cards": ["SW_444"],
            "conditions": "*",
            "claim_id": "keep_twilight_guide_b",
            "source_claim_ids": ["raw_keep_twilight_b"],
            "evidence_text_short": "Twilight Deceptor is a keep",
        },
    ]

    plan = build_mulligan_plan(deck_name="ShadowPriest", claims=claims, card_roles={})

    sw444_rules = [
        row
        for row in plan["rules"]
        if row["card"] == "SW_444" and row["action"] == "hold"
    ]
    assert len(sw444_rules) == 1
    assert sw444_rules[0]["condition"] == "*"
    assert sw444_rules[0]["source_claim_ids"] == [
        "raw_keep_twilight_a",
        "raw_keep_twilight_b",
    ]
    assert sw444_rules[0]["merged_claim_ids"] == [
        "keep_twilight_guide_a",
        "keep_twilight_guide_b",
    ]
    assert sw444_rules[0]["merged_reasons"] == [
        "Keep Twilight Deceptor",
        "Twilight Deceptor is a keep",
    ]
    assert plan["quality"]["source_backed_keep_rule_count"] == 1
    assert plan["quality"]["merged_duplicate_rule_count"] == 1
    assert plan["quality"]["default_only"] is False


def test_mulligan_plan_does_not_merge_same_card_with_different_condition_or_action():
    claims = [
        {
            "claim_kind": "mulligan_keep",
            "cards": ["SW_444"],
            "conditions": {"coin": True},
            "claim_id": "keep_coin",
        },
        {
            "claim_kind": "mulligan_keep",
            "cards": ["SW_444"],
            "conditions": {"nocoin": True},
            "claim_id": "keep_no_coin",
        },
        {
            "claim_kind": "mulligan_discard",
            "cards": ["SW_444"],
            "conditions": {"coin": True},
            "claim_id": "discard_coin",
        },
    ]

    plan = build_mulligan_plan(deck_name="ShadowPriest", claims=claims, card_roles={})

    sw444_rules = [
        (row["action"], row["condition"])
        for row in plan["rules"]
        if row["card"] == "SW_444"
    ]
    assert sw444_rules == [
        ("discard", "coin"),
        ("hold", "coin"),
        ("hold", "nocoin"),
    ]
    assert plan["quality"]["source_backed_keep_rule_count"] == 2
    assert plan["quality"]["merged_duplicate_rule_count"] == 0


def test_mulligan_plan_suppresses_unsupported_conditions_instead_of_broadening_to_wildcard():
    claims = [
        {
            "claim_kind": "mulligan_keep",
            "cards": ["CARD_001"],
            "conditions": "keep if the hand feels good",
            "claim_id": "bad_condition",
        }
    ]

    plan = build_mulligan_plan(deck_name="Deck", claims=claims, card_roles={})

    assert plan["rules"] == []
    assert plan["suppressed_rules"][0]["card"] == "CARD_001"
    assert plan["suppressed_rules"][0]["reason"] == "unsupported_mulligan_condition"
    assert plan["quality"]["blocked_reason"] == "no_source_backed_mulligan_keeps"
    assert plan["quality"]["first_gap_reason"] == "unsupported_mulligan_condition"


def test_mulligan_plan_reports_lifecycle_rejected_claim_without_compiling_rule():
    plan = build_mulligan_plan(
        deck_name="Deck",
        claims=[
            {
                "claim_id": "archetype-guide-keep",
                "claim_kind": "mulligan_keep",
                "source_family": "guide",
                "cards": ["TOY_381"],
                "deck_match_scope": "archetype_matched",
                "promotion_eligible": True,
                "source_visibility": "full_text",
                "source_lane": "archetype_matched_public_guide",
                "claim_readiness": "guide_backed",
                "_claim_lifecycle": {
                    "claim_id": "archetype-guide-keep",
                    "surface": "mulligan",
                    "policy_lane": "runtime_lowerable",
                    "surface_gate_allowed": False,
                    "surface_gate_reason": "mulligan_requires_exact_deck_match",
                },
            }
        ],
        card_roles={},
    )

    assert plan["rules"] == []
    assert len(plan["suppressed_rules"]) == 1
    suppressed = plan["suppressed_rules"][0]
    assert {
        key: suppressed[key]
        for key in (
            "card",
            "action",
            "reason",
            "source_claim_ids",
            "claim_id",
            "source_type",
            "claim_readiness",
        )
    } == {
        "card": "TOY_381",
        "action": "hold",
        "reason": "mulligan_requires_exact_deck_match",
        "source_claim_ids": ["archetype-guide-keep"],
        "claim_id": "archetype-guide-keep",
        "source_type": "source_claim",
        "claim_readiness": "guide_backed",
    }
    assert suppressed["acquisition_provenance"]["authority"] == "live_verified"
    assert plan["quality"]["blocked_reason"] == "no_source_backed_mulligan_keeps"


def test_policy_vetoes_exact_card_from_lifecycle_rejected_guide_claim():
    plan = build_mulligan_plan(
        deck_name="Deck",
        claims=[
            {
                "claim_id": "archetype-guide-keep",
                "claim_kind": "mulligan_keep",
                "cards": ["TOY_381"],
                "_claim_lifecycle": {
                    "surface_gate_allowed": False,
                    "surface_gate_reason": "mulligan_requires_exact_deck_match",
                },
            }
        ],
        card_roles={"TOY_381": {"roles": ["one_drop", "early_pressure"]}},
        deck_cards={"TOY_381": {"name": "Policy Candidate", "cost": 1}},
        allow_policy_backed=True,
    )

    assert not any(
        row.get("card") == "TOY_381" and row.get("action") == "hold"
        for row in plan["rules"]
    )
    assert {
        "card": "TOY_381",
        "reason": "explicit_source_gap_requires_resolution",
        "policy_lane": "source_veto",
        "source_type": "policy_backed_autonomous_mulligan",
    } in plan["quality"]["policy_result"]["suppressed"]


def test_non_card_specific_lifecycle_rejection_keeps_safe_policy_fallback():
    plan = build_mulligan_plan(
        deck_name="Deck",
        claims=[
            {
                "claim_id": "generic-guide-reject",
                "claim_kind": "mulligan_keep",
                "cards": [],
                "_claim_lifecycle": {
                    "surface_gate_allowed": False,
                    "surface_gate_reason": "mulligan_requires_exact_deck_match",
                },
            }
        ],
        card_roles={},
        deck_cards={"SAFE_002": {"name": "Safe Two Drop", "cost": 2}},
        allow_policy_backed=True,
    )

    hold = next(row for row in plan["rules"] if row["action"] == "hold")

    assert hold["card"] == "SAFE_002"
    assert hold["source_type"] == "policy_backed_autonomous_mulligan"


def test_mulligan_plan_rejects_runtime_condition_wrapper_with_condition_sibling():
    claims = [
        {
            "claim_kind": "mulligan_keep",
            "cards": ["CARD_001"],
            "conditions": {
                "runtime_condition": "coin",
                "hand_contains": "BAD-ID",
            },
            "claim_id": "wrapped_bad_condition",
        }
    ]

    plan = build_mulligan_plan(deck_name="Deck", claims=claims, card_roles={})

    assert plan["rules"] == []
    assert plan["suppressed_rules"][0]["card"] == "CARD_001"
    assert plan["suppressed_rules"][0]["reason"] == "unsupported_mulligan_condition"


def test_mulligan_plan_orders_conflicting_exact_rules_by_precedence():
    claims = [
        {
            "claim_kind": "mulligan_keep",
            "cards": ["CARD_001"],
            "conditions": {"coin": True},
            "claim_id": "keep_coin",
        },
        {
            "claim_kind": "mulligan_discard",
            "cards": ["CARD_001"],
            "conditions": {"coin": True},
            "claim_id": "discard_coin",
        },
    ]

    plan = build_mulligan_plan(deck_name="Deck", claims=claims, card_roles={})

    exact_rules = [
        (row["action"], row["condition"])
        for row in plan["rules"]
        if row["card"] == "CARD_001"
    ]
    assert exact_rules == [("discard", "coin"), ("hold", "coin")]


def test_mulligan_plan_source_discard_prevents_role_fallback_for_same_card():
    plan = build_mulligan_plan(
        deck_name="Deck",
        claims=[
            {
                "claim_kind": "mulligan_discard",
                "cards": ["CARD_001"],
                "conditions": {"nocoin": True},
                "claim_id": "discard_no_coin",
            }
        ],
        card_roles={
            "CARD_001": {
                "roles": ["one_drop"],
                "confidence": "archetype_inferred",
                "source_claim_ids": [],
            }
        },
    )

    card_rules = [row for row in plan["rules"] if row["card"] == "CARD_001"]
    assert len(card_rules) == 1
    assert card_rules[0]["action"] == "discard"
    assert card_rules[0]["condition"] == "nocoin"


def test_policy_backed_mulligan_does_not_hold_explicit_source_discard_card():
    plan = build_mulligan_plan(
        deck_name="Deck",
        claims=[
            {
                "claim_kind": "mulligan_discard",
                "cards": ["CARD_001"],
                "conditions": "*",
                "claim_id": "discard_card_001",
            }
        ],
        card_roles={
            "CARD_001": {"roles": ["one_drop"]},
            "CARD_002": {"roles": ["one_drop"]},
        },
        deck_cards={
            "CARD_001": {"name": "Discarded One Drop", "cost": 1},
            "CARD_002": {"name": "Safe One Drop", "cost": 1},
        },
        allow_policy_backed=True,
    )

    card_001_rules = [row for row in plan["rules"] if row["card"] == "CARD_001"]
    assert [(row["action"], row["condition"]) for row in card_001_rules] == [
        ("discard", "*")
    ]
    assert all(
        row["card"] != "CARD_001"
        for row in plan["quality"]["policy_result"]["rules"]
    )
    assert {
        "card": "CARD_001",
        "reason": "excluded_source_mulligan_intent",
        "policy_lane": "source_veto",
        "source_type": "policy_backed_autonomous_mulligan",
    } in plan["quality"]["policy_result"]["suppressed"]


def test_policy_backed_mulligan_does_not_hold_suppressed_source_discard_card():
    plan = build_mulligan_plan(
        deck_name="Deck",
        claims=[
            {
                "claim_kind": "mulligan_discard",
                "cards": ["CARD_001"],
                "conditions": {"unsupported": True},
                "claim_id": "discard_card_001",
            }
        ],
        card_roles={
            "CARD_001": {"roles": ["one_drop"]},
            "CARD_002": {"roles": ["one_drop"]},
        },
        deck_cards={
            "CARD_001": {"name": "Suppressed Discard One Drop", "cost": 1},
            "CARD_002": {"name": "Safe One Drop", "cost": 1},
        },
        allow_policy_backed=True,
    )

    card_001_rules = [row for row in plan["rules"] if row["card"] == "CARD_001"]
    assert card_001_rules == []
    assert {
        "card": "CARD_001",
        "reason": "excluded_source_mulligan_intent",
        "policy_lane": "source_veto",
        "source_type": "policy_backed_autonomous_mulligan",
    } in plan["quality"]["policy_result"]["suppressed"]


def test_mulligan_plan_preserves_source_claim_selector_depth():
    plan = build_mulligan_plan(
        deck_name="Deck",
        claims=[
            {
                "claim_kind": "mulligan_keep",
                "cards": ["CARD_A", "CARD_B"],
                "selector_kind": "plus_combo",
                "selector": "CARD_A + CARD_B",
                "conditions": {"coin": True},
                "claim_id": "keep_combo_coin",
            }
        ],
        card_roles={},
    )

    rule = plan["rules"][0]
    assert rule["selector_kind"] == "plus_combo"
    assert rule["selector"] == "CARD_A + CARD_B"
    assert rule["selector_cards"] == ["CARD_A", "CARD_B"]
    assert rule["condition"] == "coin"


def test_mulligan_plan_suppresses_selector_cards_not_in_claim_before_runtime():
    plan = build_mulligan_plan(
        deck_name="Deck",
        claims=[
            {
                "claim_kind": "mulligan_keep",
                "cards": ["CARD_A"],
                "selector_kind": "plus_combo",
                "selector": "CARD_A + OFF_DECK",
                "claim_id": "off_deck_selector",
            }
        ],
        card_roles={},
    )

    assert plan["rules"] == []
    assert plan["suppressed_rules"][0]["reason"] == "selector_cards_not_in_claim"
    assert plan["suppressed_rules"][0]["selector"] == "CARD_A + OFF_DECK"

    runtime = compile_mulligan({"deck_name": "Deck", "mulligan_plan": plan})
    assert runtime["Mulligan"]["values"] == []


def test_mulligan_plan_suppresses_unsupported_selectors():
    plan = build_mulligan_plan(
        deck_name="Deck",
        claims=[
            {
                "claim_kind": "mulligan_keep",
                "cards": ["CARD_A"],
                "selector": "CARD_A | CARD_B",
                "claim_id": "bad_selector",
            }
        ],
        card_roles={},
    )

    assert plan["rules"] == []
    assert plan["suppressed_rules"][0]["reason"] == "unsupported_mulligan_selector"
    assert plan["suppressed_rules"][0]["selector"] == "CARD_A | CARD_B"


def test_mulligan_plan_quality_reports_counts_status_and_first_gap():
    plan = build_mulligan_plan(
        deck_name="Deck",
        claims=[
            {
                "claim_kind": "mulligan_keep",
                "cards": ["CARD_A"],
                "selector": "CARD_A",
                "conditions": {"coin": True},
                "claim_id": "keep_coin",
                "claim_readiness": "guide_backed",
            },
            {
                "claim_kind": "mulligan_keep",
                "cards": ["CARD_B"],
                "selector": "CARD_B | CARD_C",
                "claim_id": "bad_selector",
                "claim_readiness": "guide_backed",
            },
        ],
        card_roles={},
    )

    assert plan["quality"]["status"] == "rich"
    assert plan["quality"]["first_gap_reason"] == "unsupported_mulligan_selector"
    assert plan["quality"]["source_backed_rule_count"] == 1
    assert plan["quality"]["suppressed_rule_count"] == 1
    assert plan["quality"]["suppressed_reasons"] == {"unsupported_mulligan_selector": 1}


def test_mulligan_plan_quality_reports_no_source_backed_keeps_when_empty():
    plan = build_mulligan_plan(deck_name="UnknownDeck", claims=[], card_roles={})

    assert plan["quality"]["status"] == "thin"
    assert plan["quality"]["first_gap_reason"] == "no_source_backed_mulligan_keeps"
    assert plan["quality"]["source_backed_rule_count"] == 0
    assert plan["quality"]["suppressed_rule_count"] == 0
    assert plan["quality"]["suppressed_reasons"] == {}


def test_mulligan_plan_discard_only_source_keeps_mulligan_thin():
    plan = build_mulligan_plan(
        deck_name="Deck",
        claims=[
            {
                "claim_kind": "mulligan_discard",
                "cards": ["CARD_A"],
                "claim_id": "discard_card_a",
                "claim_readiness": "guide_backed",
            }
        ],
        card_roles={},
    )

    assert plan["rules"][0]["action"] == "discard"
    assert plan["quality"]["status"] == "thin"
    assert plan["quality"]["first_gap_reason"] == "no_source_backed_mulligan_keeps"
    assert plan["quality"]["source_backed_rule_count"] == 1
    assert plan["quality"]["source_backed_keep_rule_count"] == 0
    assert plan["quality"]["blocked_reason"] == "no_source_backed_mulligan_keeps"


def test_mulligan_plan_can_use_policy_backed_keeps_when_source_keeps_are_absent():
    plan = build_mulligan_plan(
        deck_name="CurveDeck",
        claims=[],
        card_roles={"CARD_001": {"roles": ["one_drop", "early_pressure"]}},
        deck_cards={"CARD_001": {"name": "One Drop", "cost": 1}},
        allow_policy_backed=True,
    )

    assert plan["rules"][0]["card"] == "CARD_001"
    assert plan["rules"][0]["source_type"] == "policy_backed_autonomous_mulligan"
    assert plan["rules"][-1]["selector_kind"] == "wildcard"
    assert plan["rules"][-1]["reason"] == "discard_unlisted_cards_after_policy_backed_keeps"
    assert plan["quality"]["status"] == "policy_backed"
    assert plan["quality"]["policy_backed_keep_rule_count"] == 1
    assert plan["quality"]["default_only"] is False


def test_mulligan_plan_preserves_policy_lane_metadata():
    plan = build_mulligan_plan(
        deck_name="PirateRogue",
        claims=[],
        card_roles={
            "PIRATE": {"roles": ["one_drop", "pirate_pressure"]},
        },
        deck_cards={
            "PIRATE": {"name": "Pirate", "cost": 1},
        },
        allow_policy_backed=True,
    )

    keep = next(row for row in plan["rules"] if row["action"] == "hold")
    assert keep["source_type"] == "policy_backed_autonomous_mulligan"
    assert keep["policy_lane"] == "aggro"
    assert keep["policy_reason"] in {"one_drop", "pirate_pressure"}
    assert plan["quality"]["policy_lanes"] == ["aggro"]
    assert plan["quality"]["policy_reasons"] == [keep["policy_reason"]]


def test_source_backed_keep_suppresses_policy_fallback_even_for_better_curve_card():
    plan = build_mulligan_plan(
        deck_name="PirateRogue",
        claims=[
            {
                "claim_id": "source-keep",
                "claim_kind": "mulligan_keep",
                "cards": ["SOURCE_KEEP"],
                "conditions": "*",
                "claim_confidence": "source_backed",
            }
        ],
        card_roles={
            "SOURCE_KEEP": {"roles": ["tempo_draw"]},
            "POLICY_ONE": {"roles": ["one_drop", "pirate_pressure"]},
        },
        deck_cards={
            "SOURCE_KEEP": {"name": "Source Keep", "cost": 2},
            "POLICY_ONE": {"name": "Policy One", "cost": 1},
        },
        allow_policy_backed=True,
    )

    holds = [row for row in plan["rules"] if row["action"] == "hold"]
    assert [row["card"] for row in holds] == ["SOURCE_KEEP"]
    assert all(row.get("source_type") == "source_claim" for row in holds)
    assert plan["quality"]["policy_backed_keep_rule_count"] == 0
    assert plan["quality"]["status"] == "rich"


def test_mulligan_plan_policy_does_not_run_when_source_backed_keep_exists():
    plan = build_mulligan_plan(
        deck_name="CurveDeck",
        claims=[
            {
                "claim_kind": "mulligan_keep",
                "claim_readiness": "guide_backed",
                "cards": ["CARD_SOURCE"],
                "claim_id": "source_keep",
            }
        ],
        card_roles={"CARD_POLICY": {"roles": ["one_drop", "early_pressure"]}},
        deck_cards={"CARD_POLICY": {"name": "Policy Card", "cost": 1}},
        allow_policy_backed=True,
    )

    assert [row["card"] for row in plan["rules"] if row["action"] == "hold"] == [
        "CARD_SOURCE"
    ]
    assert plan["quality"]["status"] == "rich"
    assert plan["quality"]["policy_backed_keep_rule_count"] == 0


def test_mulligan_plan_policy_keeps_darkbishop_out_of_mulligan():
    plan = build_mulligan_plan(
        deck_name="ShadowPriest",
        claims=[],
        card_roles={
            "SW_448": {"roles": ["start_of_game", "hero_power_transform"]},
            "SW_446": {"roles": ["one_drop", "early_pressure"]},
        },
        deck_cards={
            "SW_448": {"name": "Darkbishop Benedictus", "cost": 5},
            "SW_446": {"name": "Voidtouched Attendant", "cost": 1},
        },
        allow_policy_backed=True,
    )

    assert "SW_446" in {row["card"] for row in plan["rules"]}
    assert "SW_448" not in {row["card"] for row in plan["rules"]}
    assert any(
        row["card"] == "SW_448"
        and row["reason"] == "excluded_non_hand_start_of_game_effect"
        for row in plan["suppressed_rules"]
    )
