from copy import deepcopy

import hsconfig.mechanic_support as mechanic_support
from hsconfig.mechanic_support import (
    MECHANIC_SUPPORT,
    operator_visibility_bucket,
    support_for_roles,
    summarize_mechanic_visibility,
    summarize_mechanic_support,
)
from hsconfig.visionai_registry import CARD_BEHAVIOR_BLOCKS


def _helper(name):
    assert hasattr(mechanic_support, name), f"{name} helper is required"
    return getattr(mechanic_support, name)


def test_support_for_roles_classifies_direct_partial_warning_only_and_unknown():
    rows = support_for_roles(
        [
            "battlecry",
            "location",
            "dredge",
            "tradeable",
            "future_keyword",
            "pressure",
            "spell_generation",
            "payoff_summon",
        ]
    )

    by_mechanic = {row["mechanic"]: row for row in rows}
    assert by_mechanic["battlecry"]["support_level"] == "direct"
    assert by_mechanic["location"]["support_level"] == "partial"
    assert by_mechanic["dredge"]["support_level"] == "warning_only"
    assert by_mechanic["tradeable"]["support_level"] == "warning_only"
    assert by_mechanic["future_keyword"]["support_level"] == "warning_only"
    assert by_mechanic["future_keyword"]["normal_path_surfaces"] == ["report-only"]
    assert by_mechanic["future_keyword"]["registered"] is False
    assert "pressure" not in by_mechanic
    assert by_mechanic["dredge"]["normal_path_surfaces"] == ["report-only"]
    assert by_mechanic["generated_entity"]["support_level"] == "partial"
    assert by_mechanic["generated_entity"]["normal_path_surfaces"] == [
        "CARDID.json:resolved_identity",
        "CARDID.json:OnDiscoverCardBonus",
    ]


def test_support_for_roles_returns_defensive_copies_for_registered_specs():
    first = support_for_roles(["battlecry"])
    original_battlecry_row = deepcopy(first[0])
    original_battlecry_lowering = deepcopy(MECHANIC_SUPPORT["battlecry"]["lowering"])

    first[0]["normal_path_surfaces"].append("MUTATED_SURFACE")
    first[0]["lowering"]["policy"] = "mutated_policy"

    second = support_for_roles(["battlecry"])

    assert MECHANIC_SUPPORT["battlecry"]["lowering"] == original_battlecry_lowering
    assert second[0] == original_battlecry_row

    unknown_first = support_for_roles(["future_keyword"])
    original_unknown_row = deepcopy(unknown_first[0])
    unknown_first[0]["lowering"]["policy"] = "mutated_unknown_policy"

    assert support_for_roles(["future_keyword"])[0] == original_unknown_row


def test_summarize_mechanic_support_counts_warning_only_cards():
    summary = summarize_mechanic_support(
        [
            {
                "card_id": "CARD_001",
                "mechanic_support": [
                    {"mechanic": "dredge", "support_level": "warning_only"},
                    {"mechanic": "battlecry", "support_level": "direct"},
                ],
            },
            {
                "card_id": "CARD_002",
                "mechanic_support": [
                    {"mechanic": "location", "support_level": "partial"},
                ],
            },
        ]
    )

    assert summary["support_level_counts"] == {
        "direct": 1,
        "partial": 1,
        "warning_only": 1,
    }
    assert summary["warning_only_mechanics"] == ["dredge"]
    assert summary["warning_only_card_count"] == 1


def test_operator_visibility_bucket_marks_identity_gated_direct_mechanics():
    rows = support_for_roles(
        ["discover", "hero_power_transform", "battlecry", "spell_generation"]
    )
    buckets = {row["mechanic"]: operator_visibility_bucket(row) for row in rows}

    assert buckets["battlecry"] == "direct"
    assert buckets["discover"] == "identity_gated_direct"
    assert buckets["hero_power_transform"] == "identity_gated_direct"
    assert buckets["generated_entity"] == "partial"


def test_summarize_mechanic_visibility_is_non_blocking_and_operator_readable():
    summary = summarize_mechanic_visibility(
        [
            {
                "card_id": "DISCOVER_001",
                "mechanic_support": support_for_roles(["discover"]),
            },
            {
                "card_id": "POSITION_001",
                "mechanic_support": support_for_roles(["board_position"]),
            },
            {
                "card_id": "DREDGE_001",
                "mechanic_support": support_for_roles(["dredge"]),
            },
            {
                "card_id": "AURA_001",
                "mechanic_support": support_for_roles(["magnetic"]),
            },
        ]
    )

    assert summary["non_blocking"] is True
    assert summary["bucket_counts"] == {
        "direct": 0,
        "identity_gated_direct": 1,
        "partial": 1,
        "warning_only": 2,
    }
    assert summary["mechanics_by_bucket"]["identity_gated_direct"] == ["discover"]
    assert summary["mechanics_by_bucket"]["partial"] == ["aura"]
    assert summary["mechanics_by_bucket"]["warning_only"] == ["board_position", "dredge"]
    assert summary["warning_only_card_count"] == 2
    assert summary["first_warning_boundary"]["mechanic"] == "board_position"
    assert summary["warning_boundaries"] == [
        {
            "mechanic": "board_position",
            "warning_boundary": "Exact minion placement has no documented normal-path VisionAI positioning surface.",
        },
        {
            "mechanic": "dredge",
            "warning_boundary": "Dredge option selection has no documented normal-path VisionAI choice surface.",
        },
    ]


def test_mixed_mechanic_visibility_fixture_keeps_runtime_surface_narrow():
    rows = support_for_roles(
        [
            "discover",
            "choose_one",
            "hero_power_transform",
            "generated_entity",
            "secret_timing",
            "location_activation",
            "kindred",
            "rewind",
        ]
    )
    by_mechanic = {row["mechanic"]: row for row in rows}

    for mechanic in ["discover", "choose_one", "hero_power_transform"]:
        assert operator_visibility_bucket(by_mechanic[mechanic]) == "identity_gated_direct"
        assert by_mechanic[mechanic]["support_level"] == "direct"

    assert operator_visibility_bucket(by_mechanic["generated_entity"]) == "partial"
    assert by_mechanic["generated_entity"]["support_level"] == "partial"

    for mechanic in ["secret_timing", "location_activation", "kindred", "rewind"]:
        assert operator_visibility_bucket(by_mechanic[mechanic]) == "warning_only"
        assert by_mechanic[mechanic]["support_level"] == "warning_only"
        assert by_mechanic[mechanic]["normal_path_surfaces"] == ["report-only"]

    summary = summarize_mechanic_visibility(
        [
            {"card_id": "DISCOVER_CARD", "mechanic_support": support_for_roles(["discover"])},
            {"card_id": "CHOOSE_CARD", "mechanic_support": support_for_roles(["choose_one"])},
            {
                "card_id": "TRANSFORM_CARD",
                "mechanic_support": support_for_roles(["hero_power_transform"]),
            },
            {
                "card_id": "GENERATED_CARD",
                "mechanic_support": support_for_roles(["generated_entity"]),
            },
            {
                "card_id": "WARNING_CARD",
                "mechanic_support": support_for_roles(
                    ["secret_timing", "location_activation", "kindred", "rewind"]
                ),
            },
        ]
    )

    assert summary["non_blocking"] is True
    assert summary["bucket_counts"]["identity_gated_direct"] == 3
    assert summary["bucket_counts"]["partial"] == 1
    assert summary["bucket_counts"]["warning_only"] == 4
    assert summary["mechanics_by_bucket"]["warning_only"] == [
        "kindred",
        "location_activation",
        "rewind",
        "secret_timing",
    ]


def test_visibility_slice_classifies_choose_one_and_warning_boundaries():
    rows = support_for_roles(
        [
            "choose_one_choice",
            "choose_one",
            "board_position",
            "generic_spell_target",
            "location_activation",
            "secret_timing",
            "generated_entity_random_pool",
            "spell_generation",
        ]
    )

    by_mechanic = {row["mechanic"]: row for row in rows}

    assert by_mechanic["choose_one"]["support_level"] == "direct"
    assert operator_visibility_bucket(by_mechanic["choose_one"]) == "identity_gated_direct"
    assert by_mechanic["choose_one"]["normal_path_surfaces"] == [
        "CARDID.json:OnChooseOneCardBonus",
        "CARDID.json:BeforePlayCardBonus",
    ]

    for mechanic in [
        "board_position",
        "generic_spell_target",
        "location_activation",
        "secret_timing",
        "generated_entity_random_pool",
    ]:
        assert by_mechanic[mechanic]["support_level"] == "warning_only"
        assert by_mechanic[mechanic]["normal_path_surfaces"] == ["report-only"]
        assert operator_visibility_bucket(by_mechanic[mechanic]) == "warning_only"

    assert by_mechanic["generated_entity"]["support_level"] == "partial"
    assert operator_visibility_bucket(by_mechanic["generated_entity"]) == "partial"


def test_mechanic_support_covers_static_semantic_families_without_blocking():
    rows = support_for_roles(
        [
            "choose_one",
            "spell_damage",
            "start_of_game",
            "location_activation",
            "secret_timing",
            "generated_entity_random_pool",
        ]
    )
    by_mechanic = {row["mechanic"]: row for row in rows}

    assert by_mechanic["choose_one"]["support_level"] == "direct"
    assert by_mechanic["spell_damage"]["support_level"] == "partial"
    assert by_mechanic["start_of_game"]["support_level"] == "partial"
    assert by_mechanic["location_activation"]["support_level"] == "warning_only"
    assert by_mechanic["secret_timing"]["support_level"] == "warning_only"
    assert by_mechanic["generated_entity_random_pool"]["support_level"] == "warning_only"


def test_future_wild_mechanics_are_registered_without_blocking():
    rows = support_for_roles(
        [
            "questline",
            "highlander",
            "outcast",
            "infuse",
            "corrupt",
            "finale",
            "manathirst",
            "forge",
            "excavate",
            "plague",
            "titan",
            "colossal",
            "dormant",
            "invoke",
            "jade",
            "cthun_package",
            "spell_school",
        ]
    )
    by_mechanic = {row["mechanic"]: row for row in rows}

    expected = {
        "questline": "partial",
        "highlander": "partial",
        "outcast": "warning_only",
        "infuse": "partial",
        "corrupt": "partial",
        "finale": "partial",
        "manathirst": "partial",
        "forge": "warning_only",
        "excavate": "warning_only",
        "plague": "partial",
        "titan": "warning_only",
        "colossal": "partial",
        "dormant": "partial",
        "invoke": "partial",
        "jade": "partial",
        "cthun_package": "partial",
        "spell_school": "partial",
    }
    assert set(by_mechanic) == set(expected)
    for mechanic, support_level in expected.items():
        assert by_mechanic[mechanic]["support_level"] == support_level
        assert by_mechanic[mechanic].get("registered", True) is True


def test_current_modern_wild_mechanics_are_registered_without_blocking():
    rows = support_for_roles(
        [
            "kindred",
            "tourist",
            "starship",
            "spellburst",
            "spell_burst",
            "miniaturize",
            "quickdraw",
            "honorable_kill",
            "honorablekill",
            "elusive",
            "poisonous",
            "imbue",
            "hero_power_imbue",
            "rewind",
            "herald",
            "shatter",
        ]
    )
    by_mechanic = {row["mechanic"]: row for row in rows}

    expected = {
        "kindred": "warning_only",
        "tourist": "warning_only",
        "starship": "warning_only",
        "spellburst": "partial",
        "miniaturize": "partial",
        "quickdraw": "partial",
        "honorable_kill": "partial",
        "elusive": "partial",
        "poisonous": "partial",
        "imbue": "warning_only",
        "rewind": "warning_only",
        "herald": "warning_only",
        "shatter": "warning_only",
    }

    assert set(by_mechanic) == set(expected)
    for mechanic, support_level in expected.items():
        assert by_mechanic[mechanic]["support_level"] == support_level
        assert by_mechanic[mechanic].get("registered", True) is True
        if support_level == "warning_only":
            assert by_mechanic[mechanic]["normal_path_surfaces"] == ["report-only"]
            assert operator_visibility_bucket(by_mechanic[mechanic]) == "warning_only"
    for mechanic in ["rewind", "herald", "shatter"]:
        summary = by_mechanic[mechanic]
        assert summary.get("registered", True) is True
        assert summary["support_level"] == "warning_only"
        assert summary["normal_path_surfaces"] == ["report-only"]
        assert operator_visibility_bucket(summary) == "warning_only"


def test_prepare_and_starship_aliases_are_registered_without_blocking():
    rows = support_for_roles(["prepare", "prepare_keyword", "starship_piece_tag"])
    by_mechanic = {row["mechanic"]: row for row in rows}

    assert set(by_mechanic) == {"prepare", "starship"}
    assert by_mechanic["prepare"]["support_level"] == "warning_only"
    assert by_mechanic["prepare"]["normal_path_surfaces"] == ["report-only"]
    assert by_mechanic["prepare"].get("registered", True) is True
    assert operator_visibility_bucket(by_mechanic["prepare"]) == "warning_only"
    assert by_mechanic["starship"]["support_level"] == "warning_only"


def test_cthun_alias_accepts_apostrophe_punctuation():
    rows = support_for_roles(["C'THUN"])

    assert rows[0]["mechanic"] == "cthun_package"
    assert rows[0]["support_level"] == "partial"
    assert rows[0].get("registered", True) is True


def test_every_cardid_surface_mechanic_has_lowering_policy():
    mechanic_lowering_policy = _helper("mechanic_lowering_policy")
    mechanic_allowed_runtime_blocks = _helper("mechanic_allowed_runtime_blocks")
    mechanic_default_runtime_block = _helper("mechanic_default_runtime_block")

    for mechanic, spec in MECHANIC_SUPPORT.items():
        if spec["support_level"] == "warning_only":
            continue
        if not any(
            str(surface).startswith("CARDID.json:")
            for surface in spec["normal_path_surfaces"]
        ):
            continue

        policy = mechanic_lowering_policy(mechanic)
        assert policy["policy"] in {"lowerable", "identity_gated"}, mechanic
        assert "lowering" in spec, mechanic
        assert policy == spec["lowering"]
        assert mechanic_default_runtime_block(mechanic) in (
            mechanic_allowed_runtime_blocks(mechanic) | {None}
        )

    deathrattle_policy = mechanic_lowering_policy("deathrattle")
    assert deathrattle_policy["policy"] == "lowerable"
    assert deathrattle_policy["default_block"] == "BeforePlayCardBonus"
    assert mechanic_allowed_runtime_blocks("deathrattle") == {
        "BeforePlayCardBonus",
        "OnBoardBonus",
    }


def test_warning_only_mechanics_have_report_only_policy():
    mechanic_lowering_policy = _helper("mechanic_lowering_policy")
    mechanic_static_claim_allowed = _helper("mechanic_static_claim_allowed")
    mechanic_allowed_runtime_blocks = _helper("mechanic_allowed_runtime_blocks")
    mechanic_default_runtime_block = _helper("mechanic_default_runtime_block")
    mechanic_report_only_reason = _helper("mechanic_report_only_reason")

    for mechanic, spec in MECHANIC_SUPPORT.items():
        if spec["support_level"] != "warning_only":
            continue

        policy = mechanic_lowering_policy(mechanic)
        assert policy["policy"] == "report_only", mechanic
        assert policy == spec["lowering"]
        assert policy["static_claim_allowed"] is False
        assert policy["default_block"] is None
        assert mechanic_static_claim_allowed(mechanic) is False
        assert mechanic_allowed_runtime_blocks(mechanic) == set()
        assert mechanic_default_runtime_block(mechanic) is None
        assert mechanic_report_only_reason(mechanic) == policy["suppression_reason"]
        assert policy["suppression_reason"] != "unregistered_mechanic_runtime_surface"

    unknown_policy = mechanic_lowering_policy("future_keyword")
    assert unknown_policy["policy"] == "report_only"
    assert unknown_policy["suppression_reason"] == "unregistered_mechanic_runtime_surface"
    assert mechanic_report_only_reason("future_keyword") == (
        "unregistered_mechanic_runtime_surface"
    )


def test_static_claim_allowed_only_for_executable_or_identity_gated_mechanics():
    mechanic_lowering_policy = _helper("mechanic_lowering_policy")
    mechanic_static_claim_allowed = _helper("mechanic_static_claim_allowed")
    mechanics_with_executable_lowering = _helper("mechanics_with_executable_lowering")

    executable = mechanics_with_executable_lowering()
    assert "deathrattle" in executable
    assert "discover" in executable
    assert "tradeable" not in executable
    assert "future_keyword" not in executable

    for mechanic in MECHANIC_SUPPORT:
        policy = mechanic_lowering_policy(mechanic)
        static_allowed = mechanic_static_claim_allowed(mechanic)
        if static_allowed:
            assert policy["policy"] in {"lowerable", "identity_gated"}, mechanic
        if policy["policy"] == "report_only":
            assert static_allowed is False, mechanic

    assert mechanic_static_claim_allowed("deathrattle") is True
    assert mechanic_static_claim_allowed("choose_one") is False
    assert mechanic_static_claim_allowed("tradeable") is False
    assert mechanic_static_claim_allowed("future_keyword") is False


def test_choose_one_identity_gated_policy_has_no_generic_default_lowering():
    mechanic_lowering_policy = _helper("mechanic_lowering_policy")
    mechanic_allowed_runtime_blocks = _helper("mechanic_allowed_runtime_blocks")
    mechanic_default_runtime_block = _helper("mechanic_default_runtime_block")

    policy = mechanic_lowering_policy("choose_one")

    assert policy["policy"] == "identity_gated"
    assert policy["static_claim_allowed"] is False
    assert policy["default_block"] is None
    assert "OnChooseOneCardBonus" in mechanic_allowed_runtime_blocks("choose_one")
    assert mechanic_default_runtime_block("choose_one") is None


def test_runtime_block_allowlist_matches_documented_card_behavior_blocks():
    mechanic_lowering_policy = _helper("mechanic_lowering_policy")
    mechanic_allowed_runtime_blocks = _helper("mechanic_allowed_runtime_blocks")
    mechanic_default_runtime_block = _helper("mechanic_default_runtime_block")

    for mechanic in MECHANIC_SUPPORT:
        policy = mechanic_lowering_policy(mechanic)
        allowed_blocks = mechanic_allowed_runtime_blocks(mechanic)
        assert allowed_blocks == set(policy["allowed_blocks"]), mechanic
        assert allowed_blocks <= CARD_BEHAVIOR_BLOCKS, mechanic
        default_block = mechanic_default_runtime_block(mechanic)
        assert default_block is None or default_block in allowed_blocks, mechanic
        if policy["policy"] == "report_only":
            assert allowed_blocks == set(), mechanic
            assert default_block is None, mechanic

    assert mechanic_allowed_runtime_blocks("future_keyword") == set()
    assert mechanic_default_runtime_block("future_keyword") is None
