from hsconfig.mechanic_support import support_for_roles, summarize_mechanic_support


def test_support_for_roles_classifies_direct_partial_warning_only_and_unknown():
    rows = support_for_roles(
        ["battlecry", "location", "dredge", "tradeable", "future_keyword", "pressure"]
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
