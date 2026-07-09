from hsconfig.mechanic_support import (
    operator_visibility_bucket,
    support_for_roles,
    summarize_mechanic_visibility,
    summarize_mechanic_support,
)


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
        "warning_only": 1,
    }
    assert summary["mechanics_by_bucket"]["identity_gated_direct"] == ["discover"]
    assert summary["mechanics_by_bucket"]["partial"] == ["aura"]
    assert summary["mechanics_by_bucket"]["warning_only"] == ["dredge"]
    assert summary["warning_only_card_count"] == 1
    assert summary["first_warning_boundary"]["mechanic"] == "dredge"
