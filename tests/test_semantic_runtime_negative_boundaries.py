import pytest

from hsconfig.card_behavior_router import route_card_behavior_claims
from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces
from hsconfig.combo_plan import build_combo_plan as _build_combo_plan
from hsconfig.static_semantics import infer_static_semantics
from hsconfig.source_document_model import (
    can_lower_to_globalvalues,
    can_lower_to_mulligan,
    surface_gate_decision,
)
from tests.combo_authority_fixtures import build_canonical_combo_case


AUDITED_UNEXPRESSIBLE_CASES = [
    (
        "WW_336",
        "BeforePlayCardBonus",
        "variable_cost_condition_not_encoded",
        "SPELL",
        "Deal 3 damage to all enemies. Costs (1) less for each enemy minion.",
    ),
    (
        "WW_051",
        "BeforePlayCardBonus",
        "symmetric_board_condition_not_encoded",
        "SPELL",
        "Both players summon three 3/3 Outlaws. Give yours Rush.",
    ),
    (
        "CATA_479",
        "BeforePlayCardBonus",
        "shatter_state_not_encoded",
        "SPELL",
        "Shatter. Summon two 4/2 Drakes.",
    ),
    (
        "CS2_073",
        "BeforePlayCardBonus",
        "combo_target_condition_not_encoded",
        "SPELL",
        "Give a minion +2 Attack. Combo: +4 Attack instead.",
    ),
    (
        "DMF_519",
        "BeforeBattlecryTargetBonus",
        "combo_count_condition_not_encoded",
        "MINION",
        "Combo: Deal 1 damage to a minion for each other card you've played this turn.",
    ),
    (
        "TTN_922",
        "BeforePlayCardBonus",
        "hand_position_condition_not_encoded",
        "SPELL",
        "Shuffle the two left-most cards in your hand into your deck. Draw 3 cards.",
    ),
    (
        "GVG_029",
        "BeforePlayCardBonus",
        "symmetric_summon_condition_not_encoded",
        "SPELL",
        "Put a random minion from each player's hand into the battlefield.",
    ),
    (
        "CS2_038",
        "BeforeBattlecryTargetBonus",
        "spell_cannot_use_battlecry_target",
        "SPELL",
        'Give a minion "Deathrattle: Resummon this minion."',
    ),
    (
        "WON_335",
        "BeforeBattlecryTargetBonus",
        "spell_cannot_use_battlecry_target",
        "SPELL",
        "Destroy a minion, then return it to life with full Health.",
    ),
    (
        "TOY_877",
        "OnBoardBonus",
        "spell_cannot_own_on_board",
        "SPELL",
        "Give +2/+3 to all minions in your hand, deck, and battlefield.",
    ),
    (
        "JAM_028",
        "BeforePlayCardBonus",
        "health_cost_condition_not_encoded",
        "MINION",
        "Costs Health instead of Mana.",
    ),
    (
        "TTN_954",
        "OnBoardBonus",
        "spell_cannot_own_on_board",
        "SPELL",
        "Give your minions +2/+2. Costs (1) less for each Treant summoned.",
    ),
    (
        "NX2_006",
        "BeforePhysicalAttackBonus",
        "trigger_owner_does_not_attack",
        "MINION",
        "After your hero attacks, summon a 1/1 Undead Pirate.",
    ),
    (
        "VAC_938",
        "BeforePhysicalAttackBonus",
        "buff_target_owner_mismatch",
        "MINION",
        "Whenever another friendly Pirate attacks, give it +1/+1.",
    ),
    (
        "VAC_701",
        "BeforePhysicalAttackBonus",
        "battlecry_owner_does_not_attack",
        "MINION",
        "Battlecry: Set the Attack and Durability of your weapon to 3.",
    ),
]


def build_authorized_combo_case(*, deck_cards, case_id):
    bundle, deck_identity = build_canonical_combo_case(case_id)
    return _build_combo_plan(
        deck_cards=deck_cards,
        claims=bundle["claims"],
        deck_identity=deck_identity,
        verified_source_receipts=bundle["canonical_source_receipts"],
    )


@pytest.mark.parametrize(
    "case_id",
    [
        "combo-plus-coexistence",
        "combo-marker-unordered-list",
        "combo-undirected-sentence",
        "combo-exact-decklist-coexistence",
        "combo-prefix-collision",
        "combo-effect-clause-then",
        "combo-effect-clause-into",
    ],
)
def test_exact_source_combo_claim_without_directed_evidence_is_suppressed(case_id):
    result = build_authorized_combo_case(
        deck_cards={"CARD_A", "CARD_B"},
        case_id=case_id,
    )

    assert result["combos"] == []
    assert result["suppressed"] == [
        {
            "claim_id": case_id,
            "cards": ["CARD_A", "CARD_B"],
            "reason": "combo_requires_directed_source_evidence",
        }
    ]


def test_every_gap_in_exact_source_three_card_combo_requires_directed_evidence():
    result = build_authorized_combo_case(
        deck_cards={"CARD_A", "CARD_B", "CARD_C"},
        case_id="combo-three-step-effect-clause",
    )

    assert result["combos"] == []
    assert result["suppressed"] == [
        {
            "claim_id": "combo-three-step-effect-clause",
            "cards": ["CARD_A", "CARD_B", "CARD_C"],
            "reason": "combo_requires_directed_source_evidence",
        }
    ]


def test_combo_deck_membership_reason_precedes_directed_evidence_reason():
    result = build_authorized_combo_case(
        deck_cards={"CARD_A"},
        case_id="claim-missing-undirected",
    )

    assert result["combos"] == []
    assert result["suppressed"] == [
        {
            "claim_id": "claim-missing-undirected",
            "cards": ["CARD_A", "CARD_MISSING"],
            "reason": "card_not_in_deck",
            "missing_cards": ["CARD_MISSING"],
        }
    ]


def test_start_of_game_hero_power_transform_does_not_lower_to_mulligan_keep():
    claim = {
        "claim_id": "darkbishop_wrong_keep",
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


def test_globalvalue_numeric_tuning_requires_runtime_evidence_in_step1():
    claim = {
        "claim_id": "numeric_tuning_from_guide",
        "claim_kind": "globalvalue_numeric_tuning",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "key": "LowHpBoardValuePenalty",
    }

    decision = can_lower_to_globalvalues(claim)

    assert decision.allowed is False
    assert decision.reason == "requires_runtime_evidence"


def test_unresolved_discover_choice_stays_suppressed_until_option_identity_is_linked():
    claim = {
        "claim_id": "discover_without_identity_link",
        "claim_kind": "discover_choice",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["CARD_001"],
        "option_card_id": "OPTION_001",
    }

    result = route_card_behavior_surfaces([claim], identity_links={})

    assert result["rows"] == []
    assert result["suppressed"][0]["claim_id"] == "discover_without_identity_link"
    assert result["suppressed"][0]["reason"] == "unresolved_option_identity"


def test_vague_combo_sequence_without_two_cards_stays_suppressed():
    result = build_authorized_combo_case(
        deck_cards={"CARD_001"},
        case_id="vague_combo",
    )

    assert result["combos"] == []
    assert result["suppressed"][0]["claim_id"] == "vague_combo"
    assert result["suppressed"][0]["reason"] == "sequence_too_short"


@pytest.mark.parametrize(
    ("claim", "surface", "expected_reason"),
    [
        (
            {
                "claim_id": "darkbishop_effect_only",
                "claim_kind": "hero_power_transform",
                "claim_readiness": "guide_backed",
                "cards": ["SW_448"],
                "semantic_qualifiers": {
                    "timing": "start_of_game",
                    "state_requirements": "hero_power_transform",
                },
            },
            "mulligan",
            "claim_kind_not_mulligan_surface",
        ),
        (
            {
                "claim_id": "deck_effect_misread_as_keep",
                "claim_kind": "mulligan_keep",
                "claim_readiness": "guide_backed",
                "cards": ["SW_448"],
                "semantic_qualifiers": {
                    "timing": "start_of_game",
                    "zone_scope": "deck",
                },
            },
            "mulligan",
            "start_of_game_effect_does_not_require_opening_hand",
        ),
        (
            {
                "claim_id": "runtime_only_globalvalue",
                "claim_kind": "globalvalue_numeric_tuning",
                "claim_readiness": "guide_backed",
                "key": "FirstTurnValueWeight",
                "runtime_value": 1.2,
            },
            "globalvalues",
            "requires_runtime_evidence",
        ),
        (
            {
                "claim_id": "discover_without_option",
                "claim_kind": "discover_choice",
                "claim_readiness": "guide_backed",
                "cards": ["DISCOVER_TEST_CARD"],
            },
            "mulligan",
            "claim_kind_not_mulligan_surface",
        ),
        (
            {
                "claim_id": "vague_combo_not_mulligan",
                "claim_kind": "combo_sequence",
                "claim_readiness": "guide_backed",
                "cards": ["CARD_A"],
                "sequence": ["CARD_A"],
            },
            "mulligan",
            "claim_kind_not_mulligan_surface",
        ),
    ],
)
def test_false_runtime_lowering_boundaries_do_not_cross_surfaces(
    claim,
    surface,
    expected_reason,
):
    decision = surface_gate_decision(claim, surface)

    assert decision.allowed is False
    assert decision.reason == expected_reason


def test_discover_choice_without_option_identity_is_suppressed_not_lowered():
    claims = [
        {
            "claim_id": "discover_generic_burn",
            "claim_kind": "discover_choice",
            "claim_readiness": "guide_backed",
            "cards": ["DISCOVER_TEST_CARD"],
            "evidence_text_short": "Choose burn from Discover.",
        }
    ]

    routed = route_card_behavior_claims(claims, identity_links={})

    assert routed["card_rows"] == {}
    assert routed["suppressed"][0]["claim_id"] == "discover_generic_burn"
    assert routed["suppressed"][0]["reason"] in {
        "requires_exact_option_identity",
        "unresolved_option_identity",
    }


def test_one_card_or_vague_combo_sequence_does_not_emit_combo_json_rows():
    combo = build_authorized_combo_case(
        deck_cards={"CARD_001"},
        case_id="vague_combo",
    )

    assert combo["combos"] == []
    assert combo["suppressed"][0]["claim_id"] == "vague_combo"
    assert combo["suppressed"][0]["reason"] == "sequence_too_short"


def test_deckbuilding_effect_does_not_lower_to_opening_hand_keep():
    claim = {
        "claim_id": "highlander_effect_not_keep",
        "claim_kind": "mulligan_keep",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["HIGHLANDER_FIXTURE"],
        "semantic_qualifiers": {
            "timing": "start_of_game",
            "state_requirements": "deckbuilding_effect",
            "zone_scope": "deck",
        },
    }

    decision = can_lower_to_mulligan(
        claim,
        card_roles={
            "HIGHLANDER_FIXTURE": {
                "roles": ["start_of_game", "deckbuilding_modifier"],
                "semantic_families": ["start_of_game", "deckbuilding_modifier"],
            }
        },
    )

    assert decision.allowed is False
    assert decision.reason == "start_of_game_effect_does_not_require_opening_hand"


def test_generated_random_pool_does_not_become_deterministic_cardid_behavior():
    claim = {
        "claim_id": "random_generate_claim",
        "claim_kind": "mechanic_usage",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_candidate",
        "cards": ["RANDOM_POOL_CARD"],
        "mechanic": "generated_entity_random_pool",
        "evidence_text_short": "Generate a random minion.",
    }

    result = route_card_behavior_surfaces([claim], identity_links={})

    assert result["rows"] == []
    assert result["suppressed"][0]["claim_id"] == "random_generate_claim"
    assert result["suppressed"][0]["reason"] == "requires_supported_cardid_surface"
    assert result["suppressed"][0]["lowering_policy"] == "report_only"


def test_choice_claim_with_unresolved_option_identity_stays_diagnostic():
    claim = {
        "claim_id": "choose_option_without_identity",
        "claim_kind": "choose_one_choice",
        "claim_readiness": "guide_backed",
        "cards": ["CHOOSE_ONE_CARD"],
        "option_card_id": "UNRESOLVED_OPTION",
    }

    decision = surface_gate_decision(claim, "card_behavior")
    routed = route_card_behavior_surfaces([claim], identity_links={})

    assert decision.allowed is False
    assert decision.reason == "requires_exact_option_identity"
    assert routed["rows"] == []
    assert routed["suppressed"][0]["claim_id"] == "choose_option_without_identity"


def test_choice_claim_with_resolved_option_identity_uses_cardid_gate():
    claim = {
        "claim_id": "choose_option_with_identity",
        "claim_kind": "choose_one_choice",
        "claim_readiness": "guide_backed",
        "cards": ["CHOOSE_ONE_CARD"],
        "option_card_id": "OPTION_001",
    }

    decision = surface_gate_decision(
        claim,
        "card_behavior",
        context={
            "identity_links": {
                "CHOOSE_ONE_CARD": [{"card_id": "OPTION_001"}],
            }
        },
    )

    assert decision.allowed is True
    assert decision.reason == "allowed"
    assert decision.surface == "cardid"


def test_timing_mechanics_are_warning_first_not_cross_surface_claims():
    cards = [
        {
            "id": "SECRET_FIXTURE",
            "type": "SPELL",
            "mechanics": ["SECRET"],
            "text": "Secret: When your opponent casts a spell, summon a random minion.",
        },
        {
            "id": "LOCATION_FIXTURE",
            "type": "LOCATION",
            "text": "Summon two Treants.",
        },
        {
            "id": "WEAPON_FIXTURE",
            "type": "WEAPON",
            "text": "After your hero attacks, Discover a spell.",
        },
    ]

    semantics_by_id = {card["id"]: infer_static_semantics(card) for card in cards}
    families_by_id = {
        card_id: set(semantics["families"])
        for card_id, semantics in semantics_by_id.items()
    }
    warning_only_by_id = {
        card_id: set(semantics["warning_only"])
        for card_id, semantics in semantics_by_id.items()
    }

    assert {"secret", "generated_entity_random_pool"} <= families_by_id["SECRET_FIXTURE"]
    assert {"secret_timing", "generated_entity_random_pool"} <= warning_only_by_id[
        "SECRET_FIXTURE"
    ]
    assert "location" in families_by_id["LOCATION_FIXTURE"]
    assert "location_activation" in warning_only_by_id["LOCATION_FIXTURE"]
    assert {"weapon", "discover"} <= families_by_id["WEAPON_FIXTURE"]


def test_modern_wild_keywords_remain_report_first_until_surface_exists():
    for keyword in ("Titan", "Tourist", "Imbue", "Forge", "Excavate"):
        result = infer_static_semantics(
            {
                "id": f"{keyword.upper()}_FIXTURE",
                "type": "MINION",
                "text": f"{keyword}: fixture text.",
            }
        )

        assert keyword.lower() in result["families"]
        assert keyword.lower() in result["warning_only"]


@pytest.mark.parametrize(
    ("card_id", "runtime_block", "expected_reason", "card_type", "card_text"),
    AUDITED_UNEXPRESSIBLE_CASES,
)
def test_audited_unexpressible_hearthstone_semantics_stay_suppressed(
    card_id,
    runtime_block,
    expected_reason,
    card_type,
    card_text,
):
    claim = {
        "claim_id": f"audit_{card_id}",
        "claim_kind": "card_role",
        "claim_readiness": "guide_backed",
        "trust_ceiling": "runtime_lowerable",
        "cards": [card_id],
        "stance": "audited_semantic_intent",
        "runtime_block": runtime_block,
        "condition": "*",
        "evidence_text_short": card_text,
        "source_claim_ids": [f"source_{card_id}"],
        "source_refs": [f"https://example.test/{card_id}"],
        "acquisition_provenance": {
            "authority": "fixture",
            "content_sha256": f"sha256:{card_id.lower()}",
        },
    }
    routed = route_card_behavior_claims(
        [claim],
        card_metadata={
            "cards": [
                {
                    "card_id": card_id,
                    "type": card_type,
                    "text": card_text,
                }
            ]
        },
    )

    assert routed["card_rows"] == {}
    assert routed["rows"] == []
    assert routed["suppressed"] == [
        {
            "claim_id": f"audit_{card_id}",
            "claim_kind": claim["claim_kind"],
            "cards": [card_id],
            "reason": expected_reason,
            "source_claim_ids": [f"source_{card_id}"],
            "source_refs": [f"https://example.test/{card_id}"],
            "acquisition_provenance": {
                "authority": "fixture",
                "content_sha256": f"sha256:{card_id.lower()}",
            },
        }
    ]


@pytest.mark.parametrize("card_id", ["RLK_532", "WON_098"])
def test_discard_payoff_trigger_does_not_become_manual_play_bonus(card_id):
    text = "If you discard this minion, summon it."
    routed = route_card_behavior_claims(
        [
            {
                "claim_id": f"discard_payoff_{card_id}",
                "claim_kind": "card_role",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_lowerable",
                "cards": [card_id],
                "stance": "discard_summon_payoff",
                "runtime_block": "BeforePlayCardBonus",
                "condition": "*",
                "evidence_text_short": text,
            }
        ],
        card_metadata={
            "cards": [{"card_id": card_id, "type": "MINION", "text": text}]
        },
    )

    assert routed["rows"] == []
    assert routed["suppressed"][0]["reason"] == "discard_trigger_not_manual_play"


def test_unrelated_lowered_condition_does_not_prove_variable_cost_semantics():
    routed = route_card_behavior_claims(
        [
            {
                "claim_id": "variable_cost_with_coin",
                "claim_kind": "card_role",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_lowerable",
                "cards": ["VARIABLE_COST_CARD"],
                "runtime_block": "BeforePlayCardBonus",
                "condition": "coin",
                "evidence_text_short": "Costs (1) less for each enemy minion.",
            }
        ],
        card_metadata={
            "cards": [
                {
                    "card_id": "VARIABLE_COST_CARD",
                    "type": "SPELL",
                    "text": "Costs (1) less for each enemy minion.",
                }
            ]
        },
    )

    assert routed["rows"] == []
    assert routed["suppressed"][0]["reason"] == (
        "variable_cost_condition_not_encoded"
    )


def test_discover_option_identity_cannot_authorize_wrong_runtime_block():
    routed = route_card_behavior_claims(
        [
            {
                "claim_id": "discover_wrong_block",
                "claim_kind": "discover_choice",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_lowerable",
                "cards": ["DISCOVER_CARD"],
                "option_card_id": "OPTION_ALPHA",
                "runtime_block": "BeforePlayCardBonus",
                "evidence_text_short": "Discover a spell.",
            }
        ],
        identity_links={
            "DISCOVER_CARD": [{"link_kind": "entourage", "card_id": "OPTION_ALPHA"}]
        },
        card_metadata={
            "cards": [
                {
                    "card_id": "DISCOVER_CARD",
                    "type": "MINION",
                    "text": "Discover a spell.",
                }
            ]
        },
    )

    assert routed["rows"] == []
    assert routed["suppressed"][0]["reason"] == "discover_condition_not_encoded"


def test_discover_identity_cannot_authorize_unrelated_condition():
    routed = route_card_behavior_claims(
        [
            {
                "claim_id": "discover_with_coin",
                "claim_kind": "discover_choice",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_lowerable",
                "cards": ["CHOICE_CARD"],
                "option_card_id": "OPTION_ALPHA",
                "condition": "coin",
                "evidence_text_short": "Discover an exact option.",
            }
        ],
        identity_links={
            "CHOICE_CARD": [{"link_kind": "entourage", "card_id": "OPTION_ALPHA"}]
        },
    )

    assert routed["rows"] == []
    assert routed["suppressed"][0]["reason"] == "discover_condition_not_encoded"


def test_choose_one_identity_cannot_authorize_wrong_runtime_block():
    routed = route_card_behavior_claims(
        [
            {
                "claim_id": "choose_one_wrong_block",
                "claim_kind": "choose_one_choice",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_lowerable",
                "cards": ["CHOICE_CARD"],
                "choice_card_id": "OPTION_ALPHA",
                "runtime_block": "BeforePlayCardBonus",
                "condition": "*",
                "evidence_text_short": "Choose an exact option.",
            }
        ],
        identity_links={
            "CHOICE_CARD": [{"link_kind": "entourage", "card_id": "OPTION_ALPHA"}]
        },
    )

    assert routed["rows"] == []
    assert routed["suppressed"][0]["reason"] == "choose_one_condition_not_encoded"


def test_opponent_attack_trigger_cannot_be_owned_by_physical_attack_surface():
    routed = route_card_behavior_claims(
        [
            {
                "claim_id": "opponent_attack_trigger",
                "claim_kind": "card_role",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_lowerable",
                "cards": ["ATTACK_TRIGGER_CARD"],
                "runtime_block": "BeforePhysicalAttackBonus",
                "condition": "*",
                "evidence_text_short": "After your opponent attacks, draw a card.",
            }
        ],
        card_metadata={
            "cards": [
                {
                    "card_id": "ATTACK_TRIGGER_CARD",
                    "type": "MINION",
                    "text": "After your opponent attacks, draw a card.",
                }
            ]
        },
    )

    assert routed["rows"] == []
    assert routed["suppressed"][0]["reason"] == "trigger_owner_does_not_attack"


def test_weapon_metadata_proves_physical_attack_surface_owner():
    routed = route_card_behavior_claims(
        [
            {
                "claim_id": "weapon_owner",
                "claim_kind": "mechanic_usage",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_lowerable",
                "cards": ["WEAPON_CARD"],
                "mechanic": "weapon",
                "runtime_block": "BeforePhysicalAttackBonus",
                "condition": "*",
                "evidence_text_short": "Attack with this weapon.",
            }
        ],
        card_metadata={
            "WEAPON_CARD": {
                "type": "WEAPON",
                "text": "Has +2 Attack.",
            }
        },
    )

    assert routed["suppressed"] == []
    assert routed["rows"][0]["behavior_block"] == "BeforePhysicalAttackBonus"


def test_card_id_keyed_metadata_enforces_spell_surface_ownership():
    routed = route_card_behavior_claims(
        [
            {
                "claim_id": "keyed_spell_metadata",
                "claim_kind": "card_role",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_lowerable",
                "cards": ["KEYED_SPELL"],
                "runtime_block": "OnBoardBonus",
                "condition": "*",
            }
        ],
        card_metadata={
            "KEYED_SPELL": {
                "type": "SPELL",
                "text": "Give your minions +1/+1.",
            }
        },
    )

    assert routed["rows"] == []
    assert routed["suppressed"][0]["reason"] == "spell_cannot_own_on_board"


def test_string_source_ref_is_preserved_as_one_provenance_element():
    routed = route_card_behavior_claims(
        [
            {
                "claim_id": "string_source_ref",
                "claim_kind": "card_role",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_lowerable",
                "cards": ["SPELL_CARD"],
                "runtime_block": "OnBoardBonus",
                "source_refs": "https://example.test/source",
            }
        ],
        card_metadata={
            "cards": [{"card_id": "SPELL_CARD", "type": "SPELL", "text": ""}]
        },
    )

    assert routed["suppressed"][0]["source_refs"] == [
        "https://example.test/source"
    ]
