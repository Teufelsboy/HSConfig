import importlib.util

from hsconfig.card_behavior_router import route_card_behavior_claims
from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces


def test_risky_static_semantics_stay_report_only_after_candidate_scoring():
    plan = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_mind_sear_static",
                "claim_kind": "card_role",
                "cards": ["NX2_019"],
                "stance": "play_for_conditional_burn",
                "claim_readiness": "source_backed_static_semantics",
                "source_lane": "official_static_semantics",
                "source_refs": ["hearthstonejson_static_semantics"],
                "runtime_block": "BeforePlayCardBonus",
                "condition": "*",
            }
        ]
    )

    assert plan["rows"] == []
    assert plan["suppressed"] == [
        {
            "claim_id": "claim_mind_sear_static",
            "claim_kind": "card_role",
            "cards": ["NX2_019"],
            "reason": "semantic_surface_not_expressible",
        }
    ]


def test_static_source_ref_maps_to_official_lane_for_semantic_gate():
    plan = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_raise_dead_static",
                "claim_kind": "card_role",
                "cards": ["SCH_514"],
                "stance": "use_conditional_resource",
                "claim_readiness": "source_backed_static_semantics",
                "source_refs": ["hearthstonejson_static_semantics"],
                "runtime_block": "BeforePlayCardBonus",
                "condition": "*",
            }
        ]
    )

    assert plan["rows"] == []
    assert plan["suppressed"][0]["reason"] == "semantic_surface_not_expressible"


def test_supported_direct_burn_static_semantics_can_emit_candidate_row():
    plan = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_mind_blast_static",
                "claim_kind": "card_role",
                "cards": ["DS1_233"],
                "stance": "direct_enemy_hero_burn",
                "claim_readiness": "source_backed_static_semantics",
                "source_lane": "official_static_semantics",
                "source_refs": ["hearthstonejson_static_semantics"],
                "runtime_block": "BeforePlayCardBonus",
                "condition": "*",
            }
        ]
    )

    assert plan["suppressed"] == []
    assert plan["rows"][0]["semantic_score"]["reason"] == "direct_enemy_hero_burn"
    assert plan["rows"][0]["behavior_block"] == "BeforePlayCardBonus"


def test_twilight_deceptor_real_text_stays_report_only_on_official_static_lane():
    plan = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_twilight_deceptor_static",
                "claim_kind": "card_role",
                "cards": ["SW_444"],
                "stance": "enemy hero damage",
                "claim_readiness": "source_backed_static_semantics",
                "source_lane": "official_static_semantics",
                "source_refs": ["hearthstonejson_static_semantics"],
                "runtime_block": "BeforePlayCardBonus",
                "condition": "*",
                "evidence_text_short": (
                    "If any hero took damage this turn, Twilight Deceptor draws "
                    "a Shadow spell."
                ),
            }
        ]
    )

    assert plan["rows"] == []
    assert plan["suppressed"] == [
        {
            "claim_id": "claim_twilight_deceptor_static",
            "claim_kind": "card_role",
            "cards": ["SW_444"],
            "reason": "semantic_surface_not_expressible",
        }
    ]


def test_papercraft_angel_static_aura_routes_to_on_board_bonus():
    plan = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_papercraft_angel_static",
                "claim_kind": "card_role",
                "cards": ["TOY_381"],
                "stance": "hero_power_support",
                "claim_readiness": "source_backed_static_semantics",
                "source_lane": "official_static_semantics",
                "source_refs": ["hearthstonejson_static_semantics"],
                "runtime_block": "OnBoardBonus",
                "condition": "*",
                "evidence_text_short": (
                    "Papercraft Angel makes your Hero Power cost (0)."
                ),
            }
        ]
    )

    assert plan["suppressed"] == []
    assert len(plan["rows"]) == 1
    assert plan["rows"][0]["card_id"] == "TOY_381"
    assert plan["rows"][0]["behavior_block"] == "OnBoardBonus"
    assert (
        plan["rows"][0]["semantic_score"]["reason"]
        == "hero_power_cost_aura"
    )


def test_card_behavior_router_routes_specific_runtime_blocks():
    claims = [
        {
            "claim_id": "claim_target",
            "claim_kind": "targeting_rule",
            "cards": ["CARD_A"],
            "stance": "prefer_enemy_hero",
            "target_scope": "enemy_hero",
            "runtime_block": "BeforeBattlecryTargetBonus",
            "condition": {"runtime_condition": "my_target(count(),hero=true) > 0"},
            "runtime_value": "12",
            "source_lane": "deck_matched_public_guide",
        },
        {
            "claim_id": "claim_discover",
            "claim_kind": "mechanic_usage",
            "cards": ["CARD_B"],
            "mechanic": "discover",
            "runtime_block": "OnDiscoverCardBonus",
            "condition": {"runtime_condition": "my_discover(count(),cardid=CARD_C) > 0"},
            "runtime_value": "10",
            "source_lane": "deck_matched_public_guide",
        },
    ]

    plan = route_card_behavior_claims(claims)

    assert plan["rows"][0]["behavior_block"] == "BeforeBattlecryTargetBonus"
    assert plan["rows"][0]["condition"] == "my_target(count(),hero=true) > 0"
    assert plan["rows"][1]["behavior_block"] == "OnDiscoverCardBonus"
    assert plan["rows"][1]["condition"] == "my_discover(count(),cardid=CARD_C) > 0"


def test_targeting_behavior_row_receives_semantic_score_value():
    mind_sear_claim = {
        "claim_kind": "targeting_rule",
        "cards": ["NX2_019"],
        "stance": "prefer_enemy_minion",
        "target_scope": "enemy_minion",
        "runtime_block": "BeforeBattlecryTargetBonus",
        "evidence_text_short": (
            "Mind Sear deals 2 damage to a minion and deals 3 damage "
            "to the enemy hero if it dies."
        ),
        "source_claim_ids": ["mind_sear_source"],
        "source_lane": "deck_matched_public_guide",
    }

    plan = route_card_behavior_surfaces([mind_sear_claim])

    assert plan["suppressed"] == []
    row = plan["rows"][0]
    assert row["behavior_block"] == "BeforeBattlecryTargetBonus"
    assert row["value"] == "10"
    assert row["semantic_score"]["reason"] == "conditional_target_kill_burn"
    assert row["semantic_score"]["band"] == "high"
    assert row["semantic_score"]["profile"] == "semantic_intent"
    assert "enemy_hero_damage" in row["semantic_score"]["matched_signals"]
    assert "death_condition" in row["semantic_score"]["matched_signals"]


def test_targeting_claim_without_target_scope_is_suppressed():
    claim = {
        "claim_id": "target-missing-scope",
        "claim_kind": "targeting_rule",
        "cards": ["NX2_019"],
        "stance": "prefer_enemy_minion",
        "source_claim_ids": ["target-missing-scope"],
    }

    report = route_card_behavior_surfaces([claim])

    assert report["rows"] == []
    assert report["suppressed"] == [
        {
            "claim_id": "target-missing-scope",
            "claim_kind": "targeting_rule",
            "cards": ["NX2_019"],
            "reason": "missing_target_scope",
        }
    ]


def test_targeting_claim_with_no_target_scope_is_suppressed():
    claim = {
        "claim_id": "target-no-target-scope",
        "claim_kind": "targeting_rule",
        "cards": ["NX2_019"],
        "target_scope": "no_target",
        "runtime_block": "BeforeBattlecryTargetBonus",
        "source_claim_ids": ["target-no-target-scope"],
    }

    report = route_card_behavior_surfaces([claim])

    assert report["rows"] == []
    assert report["suppressed"][0]["reason"] == "no_target_scope"


def test_targeting_claim_with_unknown_target_scope_is_suppressed():
    claim = {
        "claim_id": "target-unknown-scope",
        "claim_kind": "targeting_rule",
        "cards": ["NX2_019"],
        "target_scope": "random_target_category",
        "runtime_block": "BeforeBattlecryTargetBonus",
        "source_claim_ids": ["target-unknown-scope"],
    }

    report = route_card_behavior_surfaces([claim])

    assert report["rows"] == []
    assert report["suppressed"][0]["reason"] == "invalid_target_scope"


def test_targeting_claim_requires_compatible_target_block():
    claim = {
        "claim_id": "target-wrong-block",
        "claim_kind": "targeting_rule",
        "cards": ["CARD_TARGET"],
        "target_scope": "enemy_minion",
        "runtime_block": "BeforePlayCardBonus",
        "source_claim_ids": ["target-wrong-block"],
    }

    report = route_card_behavior_surfaces([claim])

    assert report["rows"] == []
    assert report["suppressed"][0]["reason"] == "target_scope_not_encoded"


def test_targeting_claim_with_scope_and_target_block_is_meaningful():
    claim = {
        "claim_id": "target-complete",
        "claim_kind": "targeting_rule",
        "cards": ["CARD_TARGET"],
        "target_scope": "enemy_minion",
        "runtime_block": "BeforeBattlecryTargetBonus",
        "condition": "my_target(count(),minion=true) > 0",
        "source_claim_ids": ["target-complete"],
        "source_lane": "deck_matched_public_guide",
    }

    report = route_card_behavior_surfaces([claim])

    assert report["suppressed"] == []
    assert report["rows"][0]["behavior_block"] == "BeforeBattlecryTargetBonus"
    assert report["rows"][0]["meaningful_runtime_surface"] is True


def test_explicit_target_runtime_block_is_preserved():
    plan = route_card_behavior_surfaces(
        [
            {
                "claim_kind": "targeting_rule",
                "cards": ["TARGET_CARD"],
                "stance": "prefer_enemy_minion",
                "runtime_block": "BeforeBattlecryTargetBonus",
                "target_scope": "enemy_minion",
                "source_lane": "deck_matched_public_guide",
            }
        ]
    )

    assert plan["suppressed"] == []
    assert plan["rows"][0]["behavior_block"] == "BeforeBattlecryTargetBonus"


def test_explicit_runtime_value_wins_over_semantic_score():
    mind_sear_claim = {
        "claim_kind": "targeting_rule",
        "cards": ["NX2_019"],
        "stance": "prefer_enemy_minion",
        "target_scope": "enemy_minion",
        "runtime_block": "BeforeBattlecryTargetBonus",
        "runtime_value": "8",
        "evidence_text_short": (
            "Mind Sear deals 2 damage to a minion and deals 3 damage "
            "to the enemy hero if it dies."
        ),
        "source_claim_ids": ["mind_sear_source"],
        "source_lane": "deck_matched_public_guide",
    }

    plan = route_card_behavior_surfaces([mind_sear_claim])

    assert plan["suppressed"] == []
    explicit_row = plan["rows"][0]
    assert explicit_row["value"] == "8"
    assert explicit_row["semantic_score"]["reason"] == "explicit_runtime_value"
    assert explicit_row["semantic_score"]["band"] == "explicit"
    assert explicit_row["semantic_score"]["profile"] == "source_claim"
    assert explicit_row["semantic_score"]["matched_signals"] == ["explicit_value"]


def test_suppressed_behavior_row_is_not_semantically_scored():
    plan = route_card_behavior_surfaces(
        [
            {
                "claim_kind": "targeting_rule",
                "cards": ["NX2_019"],
                "stance": "prefer_enemy_minion",
                "runtime_block": "NotARealVisionAIBlock",
                "evidence_text_short": (
                    "Mind Sear deals 2 damage to a minion and deals 3 damage "
                    "to the enemy hero if it dies."
                ),
            }
        ]
    )

    assert plan["rows"] == []
    assert plan["suppressed"][0]["reason"] == "unsupported_card_behavior_block"
    assert "semantic_score" not in plan["suppressed"][0]


def test_standalone_static_discover_without_exact_semantics_is_report_only():
    plan = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_discover_standalone",
                "claim_kind": "mechanic_usage",
                "cards": ["DISCOVER_CARD"],
                "mechanic": "discover",
                "claim_readiness": "source_backed_static_semantics",
                "runtime_value": "6",
            }
        ]
    )

    assert plan["rows"] == []
    assert plan["suppressed"][0]["reason"] == "semantic_surface_not_proven"


def test_card_behavior_surface_router_rows_use_lifecycle_claim_id():
    plan = route_card_behavior_surfaces(
        [
            {
                "claim_id": "raw_target",
                "claim_kind": "targeting_rule",
                "cards": ["CARD_A"],
                "stance": "prefer_enemy_hero",
                "target_scope": "enemy_hero",
                "runtime_block": "BeforeBattlecryTargetBonus",
                "source_claim_ids": ["raw_target"],
                "source_lane": "deck_matched_public_guide",
                "_claim_lifecycle": {
                    "claim_id": "lifecycle_target",
                    "surface": "cardid",
                },
            },
            {
                "claim_id": "raw_bad",
                "claim_kind": "known_bad_pattern",
                "cards": ["CARD_B"],
                "_claim_lifecycle": {
                    "claim_id": "lifecycle_bad",
                    "surface": "cardid",
                },
            },
        ]
    )

    assert plan["rows"][0]["claim_id"] == "lifecycle_target"
    assert plan["rows"][0]["source_claim_ids"] == ["raw_target"]
    assert plan["suppressed"][0]["claim_id"] == "lifecycle_bad"


def test_card_behavior_surface_router_routes_claim_kinds_in_input_order():
    spec = importlib.util.find_spec("hsconfig.card_behavior_surface_router")
    assert spec is not None, "card behavior surface router module is required"
    from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces

    claims = [
        {
            "claim_id": "claim_choose_one",
            "claim_kind": "choose_one_choice",
            "cards": ["CARD_Z"],
            "choice_card_id": "CHOICE_ALPHA",
            "runtime_value": "9",
            "source_lane": "deck_matched_public_guide",
        },
        {
            "claim_id": "claim_hero_power",
            "claim_kind": "hero_power_transform",
            "cards": ["CARD_A"],
            "stance": "use_hero_power_pressure",
            "runtime_value": "4",
            "source_lane": "deck_matched_public_guide",
        },
        {
            "claim_id": "claim_target",
            "claim_kind": "targeting_rule",
            "cards": ["CARD_B"],
            "stance": "prefer_enemy_minion",
            "target_scope": "enemy_minion",
            "runtime_block": "BeforeBattlecryTargetBonus",
            "runtime_value": "8",
            "source_lane": "deck_matched_public_guide",
        },
    ]

    plan = route_card_behavior_surfaces(
        claims,
        identity_links={"CARD_Z": [{"link_kind": "entourage", "card_id": "CHOICE_ALPHA"}]},
    )

    assert [row["claim_id"] for row in plan["rows"]] == [
        "claim_choose_one",
        "claim_hero_power",
        "claim_target",
    ]
    assert [row["card_id"] for row in plan["rows"]] == ["CARD_Z", "CARD_A", "CARD_B"]
    assert [row["behavior_block"] for row in plan["rows"]] == [
        "OnChooseOneCardBonus",
        "BeforeUseHeroPowerBonus",
        "BeforeBattlecryTargetBonus",
    ]
    assert plan["option_resolution"] == [
        {
            "claim_id": "claim_choose_one",
            "card_id": "CARD_Z",
            "option_card_id": "CHOICE_ALPHA",
            "status": "resolved",
        }
    ]
    assert plan["suppressed"] == []


def test_resolved_discover_choice_derives_my_discover_condition():
    plan = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_pick_option_alpha",
                "claim_kind": "discover_choice",
                "cards": ["DISCOVER_CARD"],
                "option_card_id": "OPTION_ALPHA",
                "stance": "pick_option_alpha",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "guide",
                "runtime_value": "11",
            }
        ],
        identity_links={
            "DISCOVER_CARD": [
                {"link_kind": "entourage", "card_id": "OPTION_ALPHA"},
            ]
        },
    )

    assert plan["suppressed"] == []
    assert plan["option_resolution"] == [
        {
            "claim_id": "claim_pick_option_alpha",
            "card_id": "DISCOVER_CARD",
            "option_card_id": "OPTION_ALPHA",
            "status": "resolved",
        }
    ]
    row = plan["card_rows"]["DISCOVER_CARD"][0]
    assert row["behavior_block"] == "OnDiscoverCardBonus"
    assert row["condition"] == "my_discover(count(),cardid=OPTION_ALPHA) > 0"
    assert row["intent"] == "pick_option_alpha"
    assert row["value"] == "11"
    assert row["meaningful_runtime_surface"] is True


def test_resolved_discover_choice_suppresses_generic_discover_fallback():
    spec = importlib.util.find_spec("hsconfig.card_behavior_surface_router")
    assert spec is not None, "card behavior surface router module is required"
    from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces

    plan = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_pick_option_alpha",
                "claim_kind": "discover_choice",
                "cards": ["DISCOVER_CARD"],
                "option_card_id": "OPTION_ALPHA",
                "stance": "pick_option_alpha",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "guide",
                "runtime_value": "11",
            },
            {
                "claim_id": "claim_generic_discover",
                "claim_kind": "mechanic_usage",
                "cards": ["DISCOVER_CARD"],
                "mechanic": "discover",
                "claim_readiness": "source_backed_static_semantics",
                "runtime_value": "6",
            },
        ],
        identity_links={
            "DISCOVER_CARD": [
                {"link_kind": "entourage", "card_id": "OPTION_ALPHA"},
            ]
        },
    )

    assert [row["claim_id"] for row in plan["rows"]] == ["claim_pick_option_alpha"]
    assert plan["rows"][0]["condition"] == "my_discover(count(),cardid=OPTION_ALPHA) > 0"
    assert plan["suppressed"] == [
        {
            "claim_id": "claim_generic_discover",
            "claim_kind": "mechanic_usage",
            "cards": ["DISCOVER_CARD"],
            "reason": "covered_by_resolved_choice_surface",
        }
    ]
    assert plan["option_resolution"] == [
        {
            "claim_id": "claim_pick_option_alpha",
            "card_id": "DISCOVER_CARD",
            "option_card_id": "OPTION_ALPHA",
            "status": "resolved",
        }
    ]


def test_modern_report_first_mechanics_do_not_emit_generic_cardid_rows():
    claims = [
        {
            "claim_id": f"claim_{mechanic}",
            "claim_kind": "mechanic_usage",
            "cards": [f"{mechanic.upper()}_CARD"],
            "mechanic": mechanic,
            "claim_readiness": "source_backed_static_semantics",
        }
        for mechanic in ("titan", "tourist", "imbue", "forge", "excavate")
    ]

    plan = route_card_behavior_surfaces(claims)

    assert plan["rows"] == []
    assert {
        (row["claim_id"], row["mechanic"], row["lowering_policy"], row["reason"])
        for row in plan["suppressed"]
    } == {
        (
            f"claim_{mechanic}",
            mechanic,
            "report_only",
            f"{mechanic}_has_no_documented_runtime_block",
        )
        for mechanic in ("titan", "tourist", "imbue", "forge", "excavate")
    }


def test_partial_discover_choice_resolution_suppresses_only_resolved_cards():
    plan = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_pick_option_alpha",
                "claim_kind": "discover_choice",
                "cards": ["CARD_RESOLVED", "CARD_UNRESOLVED"],
                "option_card_id": "OPTION_ALPHA",
                "stance": "pick_option_alpha",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "guide",
                "runtime_value": "11",
            },
            {
                "claim_id": "claim_generic_discover",
                "claim_kind": "mechanic_usage",
                "cards": ["CARD_RESOLVED", "CARD_UNRESOLVED"],
                "mechanic": "discover",
                "claim_readiness": "source_backed_static_semantics",
                "runtime_value": "6",
            },
        ],
        identity_links={
            "CARD_RESOLVED": [
                {"link_kind": "entourage", "card_id": "OPTION_ALPHA"},
            ],
            "CARD_UNRESOLVED": [
                {"link_kind": "entourage", "card_id": "OPTION_BETA"},
            ],
        },
    )

    assert [row["card_id"] for row in plan["rows"]] == ["CARD_RESOLVED"]
    assert [row["claim_id"] for row in plan["rows"]] == [
        "claim_pick_option_alpha",
    ]
    assert plan["rows"][0]["behavior_block"] == "OnDiscoverCardBonus"
    assert plan["rows"][0]["condition"] == "my_discover(count(),cardid=OPTION_ALPHA) > 0"
    assert plan["suppressed"] == [
        {
            "claim_id": "claim_pick_option_alpha",
            "claim_kind": "discover_choice",
            "cards": ["CARD_UNRESOLVED"],
            "reason": "unresolved_option_identity",
        },
        {
            "claim_id": "claim_generic_discover",
            "claim_kind": "mechanic_usage",
            "cards": ["CARD_RESOLVED"],
            "reason": "covered_by_resolved_choice_surface",
        },
        {
            "claim_id": "claim_generic_discover",
            "claim_kind": "mechanic_usage",
            "cards": ["CARD_UNRESOLVED"],
            "reason": "semantic_surface_not_proven",
        },
    ]
    assert plan["option_resolution"] == [
        {
            "claim_id": "claim_pick_option_alpha",
            "card_id": "CARD_RESOLVED",
            "option_card_id": "OPTION_ALPHA",
            "status": "resolved",
        },
        {
            "claim_id": "claim_pick_option_alpha",
            "card_id": "CARD_UNRESOLVED",
            "option_card_id": "OPTION_ALPHA",
            "status": "unresolved",
        },
    ]


def test_choose_one_choice_with_resolved_option_lowers_to_choose_one_block():
    plan = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_choose_option_alpha",
                "claim_kind": "choose_one_choice",
                "cards": ["CHOOSE_CARD"],
                "choice_card_id": "OPTION_ALPHA",
                "stance": "choose_option_alpha",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "guide",
                "runtime_value": "9",
            }
        ],
        identity_links={
            "CHOOSE_CARD": [
                {"link_kind": "entourage", "card_id": "OPTION_ALPHA"},
            ]
        },
    )

    assert plan["suppressed"] == []
    row = plan["card_rows"]["CHOOSE_CARD"][0]
    assert row["behavior_block"] == "OnChooseOneCardBonus"
    assert row["condition"] == "*"
    assert row["intent"] == "choose_option_alpha"
    assert row["meaningful_runtime_surface"] is True


def test_card_behavior_surface_router_suppresses_unresolved_option_identity():
    spec = importlib.util.find_spec("hsconfig.card_behavior_surface_router")
    assert spec is not None, "card behavior surface router module is required"
    from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces

    plan = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_discover_option",
                "claim_kind": "discover_choice",
                "cards": ["CARD_A"],
                "option_card_id": "CARD_MISSING",
            }
        ],
        identity_links={"CARD_A": [{"link_kind": "entourage", "card_id": "CARD_PRESENT"}]},
    )

    assert plan["rows"] == []
    assert plan["suppressed"] == [
        {
            "claim_id": "claim_discover_option",
            "claim_kind": "discover_choice",
            "cards": ["CARD_A"],
            "reason": "unresolved_option_identity",
        }
    ]
    assert plan["option_resolution"] == [
        {
            "claim_id": "claim_discover_option",
            "card_id": "CARD_A",
            "option_card_id": "CARD_MISSING",
            "status": "unresolved",
        }
    ]


def test_card_behavior_surface_router_suppresses_option_claim_without_identity_links():
    spec = importlib.util.find_spec("hsconfig.card_behavior_surface_router")
    assert spec is not None, "card behavior surface router module is required"
    from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces

    plan = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_choose_one",
                "claim_kind": "choose_one_choice",
                "cards": ["CARD_A"],
                "choice_card_id": "CARD_OPTION",
            }
        ]
    )

    assert plan["rows"] == []
    assert plan["suppressed"] == [
        {
            "claim_id": "claim_choose_one",
            "claim_kind": "choose_one_choice",
            "cards": ["CARD_A"],
            "reason": "unresolved_option_identity",
        }
    ]
    assert plan["option_resolution"] == [
        {
            "claim_id": "claim_choose_one",
            "card_id": "CARD_A",
            "option_card_id": "CARD_OPTION",
            "status": "unresolved",
        }
    ]


def test_hero_power_transform_claim_routes_to_hero_power_surface():
    spec = importlib.util.find_spec("hsconfig.card_behavior_surface_router")
    assert spec is not None, "card behavior surface router module is required"
    from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces

    plan = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_darkbishop",
                "claim_kind": "hero_power_transform",
                "cards": ["SW_448"],
                "claim_readiness": "source_backed_static_semantics",
                "stance": "shadow_hero_power_pressure",
                "runtime_block": "BeforeUseHeroPowerBonus",
                "condition": "*",
            }
        ]
    )

    assert plan["suppressed"] == []
    assert plan["rows"][0]["card_id"] == "SW_448"
    assert plan["rows"][0]["behavior_block"] == "BeforeUseHeroPowerBonus"
    assert plan["rows"][0]["meaningful_runtime_surface"] is True


def test_known_bad_pattern_stays_report_only_without_documented_block():
    spec = importlib.util.find_spec("hsconfig.card_behavior_surface_router")
    assert spec is not None, "card behavior surface router module is required"
    from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces

    plan = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_bad",
                "claim_kind": "known_bad_pattern",
                "cards": ["CARD_A"],
                "claim_readiness": "guide_backed",
                "stance": "do_not_target_enemy_minion",
                "condition": "*",
            }
        ]
    )

    assert plan["rows"] == []
    assert plan["suppressed"][0]["reason"] == "no_documented_card_behavior_surface"


def test_known_bad_pattern_routes_with_explicit_documented_block():
    spec = importlib.util.find_spec("hsconfig.card_behavior_surface_router")
    assert spec is not None, "card behavior surface router module is required"
    from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces

    plan = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_bad",
                "claim_kind": "known_bad_pattern",
                "cards": ["CARD_A"],
                "claim_readiness": "guide_backed",
                "stance": "do_not_target_enemy_minion",
                "runtime_block": "BeforePlayCardBonus",
                "condition": "*",
            }
        ]
    )

    assert plan["suppressed"] == []
    assert plan["rows"][0]["card_id"] == "CARD_A"
    assert plan["rows"][0]["behavior_block"] == "BeforePlayCardBonus"
    assert plan["rows"][0]["meaningful_runtime_surface"] is True


def test_card_behavior_router_preserves_claim_row_order_across_cards():
    plan = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_z",
                "claim_kind": "card_role",
                "cards": ["CARD_Z"],
                "runtime_block": "OnBoardBonus",
                "source_lane": "deck_matched_public_guide",
            },
            {
                "claim_id": "claim_a",
                "claim_kind": "card_role",
                "cards": ["CARD_A"],
                "runtime_block": "InHandBonus",
                "source_lane": "deck_matched_public_guide",
            },
        ]
    )

    assert [row["card_id"] for row in plan["rows"]] == ["CARD_Z", "CARD_A"]


def test_routes_targeting_claim_to_cardid_surface():
    claims = [
        {
            "claim_kind": "targeting_rule",
            "cards": ["DMF_090"],
            "stance": "prefer_enemy_hero",
            "target_scope": "enemy_hero",
            "runtime_block": "BeforeBattlecryTargetBonus",
            "conditions": {"phase": "burn"},
            "claim_confidence": "high",
            "source_refs": ["guide:1"],
            "source_lane": "deck_matched_public_guide",
        }
    ]

    routed = route_card_behavior_claims(claims)

    assert routed["card_rows"]["DMF_090"]
    assert routed["card_rows"]["DMF_090"][0]["surface"] == "CardID.json"
    assert routed["card_rows"]["DMF_090"][0]["intent"] == "prefer_enemy_hero"
    assert routed["suppressed"] == []


def test_blocks_unsupported_claim_from_runtime_rows():
    routed = route_card_behavior_claims(
        [
            {
                "claim_kind": "global_gameplan_advice",
                "cards": ["CARD_001"],
                "stance": "be aggressive",
                "claim_confidence": "medium",
            }
        ]
    )

    assert routed["card_rows"] == {}
    assert routed["suppressed"][0]["reason"] == "claim_kind_not_cardid_surface"


def test_card_role_fallback_does_not_override_stronger_targeting_row():
    routed = route_card_behavior_claims(
        [
            {
                "claim_kind": "targeting_rule",
                "cards": ["CARD_001"],
                "stance": "prefer_enemy_hero",
                "target_scope": "enemy_hero",
                "runtime_block": "BeforeBattlecryTargetBonus",
                "claim_confidence": "high",
                "source_lane": "deck_matched_public_guide",
            },
            {
                "claim_kind": "card_role",
                "cards": ["CARD_001"],
                "stance": "pressure",
                "claim_confidence": "medium",
            },
        ]
    )

    intents = [row["intent"] for row in routed["card_rows"]["CARD_001"]]
    assert "prefer_enemy_hero" in intents
    assert "in_hand_priority" not in intents


def test_deathrattle_static_mechanic_without_supported_semantics_is_report_only():
    routed = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_deathrattle_static",
                "claim_kind": "mechanic_usage",
                "cards": ["CARD_DEATHRATTLE"],
                "mechanic": "deathrattle",
                "claim_confidence": "high",
            }
        ]
    )

    assert routed["card_rows"] == {}
    assert routed["suppressed"][0]["reason"] == "semantic_surface_not_proven"


def test_rush_static_mechanic_without_supported_semantics_is_report_only():
    routed = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_rush_static",
                "claim_kind": "mechanic_usage",
                "cards": ["CARD_RUSH"],
                "mechanic": "rush",
                "claim_confidence": "high",
            }
        ]
    )

    assert routed["card_rows"] == {}
    assert routed["suppressed"][0]["reason"] == "semantic_surface_not_proven"


def test_tradeable_static_mechanic_stays_report_only():
    routed = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_tradeable_static",
                "claim_kind": "mechanic_usage",
                "cards": ["CARD_TRADEABLE"],
                "mechanic": "tradeable",
                "claim_confidence": "high",
            }
        ]
    )

    assert routed["card_rows"] == {}
    assert routed["suppressed"] == [
        {
            "claim_id": "claim_tradeable_static",
            "claim_kind": "mechanic_usage",
            "cards": ["CARD_TRADEABLE"],
            "reason": "tradeable_has_no_documented_runtime_block",
            "mechanic": "tradeable",
            "lowering_policy": "report_only",
        }
    ]


def test_dredge_static_mechanic_stays_report_only():
    routed = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_dredge_static",
                "claim_kind": "mechanic_usage",
                "cards": ["CARD_DREDGE"],
                "mechanic": "dredge",
                "claim_confidence": "high",
            }
        ]
    )

    assert routed["card_rows"] == {}
    assert routed["suppressed"] == [
        {
            "claim_id": "claim_dredge_static",
            "claim_kind": "mechanic_usage",
            "cards": ["CARD_DREDGE"],
            "reason": "dredge_has_no_documented_runtime_block",
            "mechanic": "dredge",
            "lowering_policy": "report_only",
        }
    ]


def test_generic_spell_target_uses_report_only_policy_reason_before_explicit_block_requirement():
    result = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_generic_spell_target",
                "claim_kind": "mechanic_usage",
                "cards": ["SPELL_TARGET_001"],
                "mechanic": "generic_spell_target",
                "claim_readiness": "source_backed_static_semantics",
            }
        ]
    )

    assert result["rows"] == []
    assert result["suppressed"] == [
        {
            "claim_id": "claim_generic_spell_target",
            "claim_kind": "mechanic_usage",
            "cards": ["SPELL_TARGET_001"],
            "reason": "generic_spell_target_has_no_documented_runtime_block",
            "mechanic": "generic_spell_target",
            "lowering_policy": "report_only",
        }
    ]


def test_choose_one_mechanic_usage_requires_resolved_option_identity():
    routed = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_choose_one_generic",
                "claim_kind": "mechanic_usage",
                "cards": ["CARD_CHOOSE_ONE"],
                "mechanic": "choose_one",
                "runtime_block": "OnChooseOneCardBonus",
                "claim_confidence": "high",
            }
        ]
    )

    assert routed["card_rows"] == {}
    assert routed["suppressed"] == [
        {
            "claim_id": "claim_choose_one_generic",
            "claim_kind": "mechanic_usage",
            "cards": ["CARD_CHOOSE_ONE"],
            "reason": "identity_gated_mechanic_requires_option_identity",
            "mechanic": "choose_one",
            "lowering_policy": "identity_gated",
        }
    ]


def test_warning_only_mechanic_with_explicit_supported_block_stays_suppressed_unless_policy_allows_explicit_override():
    routed = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_tradeable_explicit",
                "claim_kind": "mechanic_usage",
                "cards": ["CARD_TRADEABLE"],
                "mechanic": "tradeable",
                "runtime_block": "BeforePlayCardBonus",
                "claim_confidence": "high",
            }
        ]
    )

    assert routed["card_rows"] == {}
    assert routed["suppressed"] == [
        {
            "claim_id": "claim_tradeable_explicit",
            "claim_kind": "mechanic_usage",
            "cards": ["CARD_TRADEABLE"],
            "reason": "tradeable_has_no_documented_runtime_block",
            "mechanic": "tradeable",
            "lowering_policy": "report_only",
        }
    ]


def test_report_only_modern_mechanics_ignore_explicit_runtime_block_hints():
    routed = route_card_behavior_claims(
        [
            {
                "claim_id": f"claim_{mechanic}_explicit",
                "claim_kind": "mechanic_usage",
                "cards": [f"CARD_{mechanic.upper()}"],
                "mechanic": mechanic,
                "runtime_block": "BeforePlayCardBonus",
                "claim_confidence": "high",
            }
            for mechanic in ("imbue", "forge", "excavate")
        ]
    )

    assert routed["card_rows"] == {}
    assert {
        (row["claim_id"], row["mechanic"], row["lowering_policy"], row["reason"])
        for row in routed["suppressed"]
    } == {
        (
            f"claim_{mechanic}_explicit",
            mechanic,
            "report_only",
            f"{mechanic}_has_no_documented_runtime_block",
        )
        for mechanic in ("imbue", "forge", "excavate")
    }
    assert all("runtime_block" not in row for row in routed["suppressed"])


def test_unmapped_mechanic_claim_with_explicit_documented_block_lowers():
    routed = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_discard_payoff",
                "claim_kind": "mechanic_usage",
                "cards": ["DISCARD_PAYOFF"],
                "mechanic": "discard",
                "stance": "convert_discard_pressure",
                "runtime_block": "BeforePlayCardBonus",
                "runtime_value": "10",
                "condition": "*",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_lowerable",
            }
        ]
    )

    row = routed["card_rows"]["DISCARD_PAYOFF"][0]

    assert routed["suppressed"] == []
    assert row["behavior_block"] == "BeforePlayCardBonus"
    assert row["intent"] == "convert_discard_pressure"
    assert row["roles"] == ["discard"]
    assert row["meaningful_runtime_surface"] is True


def test_recruit_claim_can_lower_to_before_play_when_explicit_block_is_supported():
    spec = importlib.util.find_spec("hsconfig.card_behavior_surface_router")
    assert spec is not None, "card behavior surface router module is required"
    from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces

    result = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_recruit",
                "claim_kind": "mechanic_usage",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "guide",
                "cards": ["CARD_RECRUIT"],
                "mechanic": "recruit",
                "runtime_block": "BeforePlayCardBonus",
                "runtime_value": "9",
                "condition": "*",
                "source_claim_ids": ["claim_recruit"],
            }
        ]
    )

    assert result["suppressed"] == []
    assert result["rows"][0]["card_id"] == "CARD_RECRUIT"
    assert result["rows"][0]["behavior_block"] == "BeforePlayCardBonus"
    assert result["rows"][0]["value"] == "9"
    assert result["rows"][0]["meaningful_runtime_surface"] is True


def test_deathrattle_claim_can_lower_to_on_board_when_explicit_block_is_supported():
    spec = importlib.util.find_spec("hsconfig.card_behavior_surface_router")
    assert spec is not None, "card behavior surface router module is required"
    from hsconfig.card_behavior_surface_router import route_card_behavior_surfaces

    result = route_card_behavior_surfaces(
        [
            {
                "claim_id": "claim_deathrattle",
                "claim_kind": "mechanic_usage",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "guide",
                "cards": ["CARD_DEATHRATTLE"],
                "mechanic": "deathrattle",
                "runtime_block": "OnBoardBonus",
                "runtime_value": "7",
                "condition": "*",
                "source_claim_ids": ["claim_deathrattle"],
            }
        ]
    )

    assert result["suppressed"] == []
    assert result["rows"][0]["card_id"] == "CARD_DEATHRATTLE"
    assert result["rows"][0]["behavior_block"] == "OnBoardBonus"
    assert result["rows"][0]["value"] == "7"


def test_unmapped_mechanic_claim_with_unsupported_explicit_block_stays_report_only():
    routed = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_unknown",
                "claim_kind": "mechanic_usage",
                "cards": ["UNKNOWN_MECHANIC_CARD"],
                "mechanic": "unknown_combo_window",
                "runtime_block": "BeforePlayCardBonus",
                "condition": "*",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_lowerable",
            }
        ]
    )

    assert routed["card_rows"] == {}
    assert routed["suppressed"] == [
        {
            "claim_id": "claim_unknown",
            "claim_kind": "mechanic_usage",
            "cards": ["UNKNOWN_MECHANIC_CARD"],
            "reason": "unregistered_mechanic_runtime_surface",
            "mechanic": "unknown_combo_window",
            "lowering_policy": "report_only",
        }
    ]


def test_mapped_mechanic_claim_rejects_wrong_explicit_runtime_block():
    routed = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_weapon_wrong_block",
                "claim_kind": "mechanic_usage",
                "cards": ["WEAPON_CARD"],
                "mechanic": "weapon",
                "runtime_block": "OnBoardBonus",
                "condition": "*",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_lowerable",
            }
        ]
    )

    assert routed["card_rows"] == {}
    assert routed["suppressed"] == [
        {
            "claim_id": "claim_weapon_wrong_block",
            "claim_kind": "mechanic_usage",
            "cards": ["WEAPON_CARD"],
            "reason": "unsupported_mechanic_runtime_block",
            "mechanic": "weapon",
            "runtime_block": "OnBoardBonus",
        }
    ]


def test_unsupported_structured_condition_is_suppressed():
    routed = route_card_behavior_claims(
        [
            {
                "claim_kind": "targeting_rule",
                "cards": ["CARD_001"],
                "stance": "prefer_enemy_hero",
                "conditions": {"board_state": {"minions": 3}},
            }
        ]
    )

    assert routed["card_rows"] == {}
    assert routed["suppressed"][0]["reason"] == "unsupported_condition"


def test_router_keeps_unproven_overkill_semantics_report_only():
    report = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_overkill",
                "claim_kind": "mechanic_usage",
                "cards": ["EX1_001"],
                "mechanic": "overkill",
                "source_confidence": "high",
            }
        ]
    )

    assert report["card_rows"] == {}
    assert report["suppressed"][0]["reason"] == "semantic_surface_not_proven"


def test_router_replaces_dredge_discover_cardid_fallback_with_report_only_suppression():
    report = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_dredge",
                "claim_kind": "mechanic_usage",
                "cards": ["TSC_001"],
                "mechanic": "dredge",
                "source_confidence": "high",
            }
        ]
    )

    assert report["card_rows"] == {}
    assert report["suppressed"] == [
        {
            "claim_id": "claim_dredge",
            "claim_kind": "mechanic_usage",
            "cards": ["TSC_001"],
            "reason": "dredge_has_no_documented_runtime_block",
            "mechanic": "dredge",
            "lowering_policy": "report_only",
        }
    ]


def test_router_accepts_explicit_documented_runtime_block():
    report = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_on_board",
                "claim_kind": "card_role",
                "cards": ["EX1_002"],
                "stance": "keep_on_board",
                "runtime_block": "OnBoardBonus",
                "runtime_value": "9",
                "condition": "my_minion(count(),cardid=EX1_002) > 0",
                "source_lane": "deck_matched_public_guide",
            }
        ]
    )

    row = report["card_rows"]["EX1_002"][0]

    assert row["behavior_block"] == "OnBoardBonus"
    assert row["intent"] == "keep_on_board"
    assert row["roles"] == ["keep_on_board"]
    assert row["condition"] == "my_minion(count(),cardid=EX1_002) > 0"
    assert row["value"] == "9"
    assert row["meaningful_runtime_surface"] is True


def test_router_suppresses_unsupported_explicit_runtime_block():
    report = route_card_behavior_claims(
        [
            {
                "claim_id": "claim_bad_block",
                "claim_kind": "card_role",
                "cards": ["EX1_003"],
                "runtime_block": "NotARealVisionAIBlock",
            }
        ]
    )

    assert "EX1_003" not in report["card_rows"]
    assert report["suppressed"] == [
        {
            "claim_id": "claim_bad_block",
            "claim_kind": "card_role",
            "cards": ["EX1_003"],
            "reason": "unsupported_card_behavior_block",
            "runtime_block": "NotARealVisionAIBlock",
        }
    ]


def test_cardid_router_reports_mulligan_claim_as_wrong_surface():
    routed = route_card_behavior_surfaces(
        [
            {
                "claim_kind": "mulligan_keep",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "runtime_candidate",
                "cards": ["CARD_001"],
                "claim_id": "keep_card",
            }
        ]
    )

    assert routed["rows"] == []
    assert routed["suppressed"][0]["reason"] == "claim_kind_not_cardid_surface"
    assert routed["suppressed"][0]["claim_kind"] == "mulligan_keep"
