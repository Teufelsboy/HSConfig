from hsconfig.compile_mulligan import compile_mulligan
from hsconfig.mulligan_plan import build_mulligan_plan


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
