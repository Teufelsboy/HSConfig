from hsconfig.matrix_closure import build_matrix_closure_summary


def test_matrix_closure_counts_strong_and_source_informed_rows():
    summary = build_matrix_closure_summary(
        matrix_rows=[
            {"deck_name": "ShadowPriest", "fixture_stage": "core_source_backed_fixture"},
            {"deck_name": "CtAPaladin", "fixture_stage": "source_informed_valid_fixture"},
        ],
        results={
            "ShadowPriest": {
                "operator": {
                    "technical_status": "VALID_PACKAGE",
                    "semantic_status": "SOURCE_BACKED_STRONG",
                },
                "source_gap": {"summary": {"blocked_cards": 0}},
            },
            "CtAPaladin": {
                "operator": {
                    "technical_status": "VALID_PACKAGE",
                    "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
                },
                "source_gap": {
                    "summary": {
                        "blocked_cards": 2,
                        "first_missing_chain": {
                            "card_id": "CARD_001",
                            "next_action": "add_card_specific_source_claim",
                        },
                    }
                },
            },
        },
    )

    assert summary["summary"] == {
        "deck_count": 2,
        "valid_package_count": 2,
        "source_backed_strong_count": 1,
        "source_informed_count": 1,
        "blocked_card_count": 2,
    }
    assert summary["decks"]["CtAPaladin"]["first_missing_chain"]["card_id"] == "CARD_001"
