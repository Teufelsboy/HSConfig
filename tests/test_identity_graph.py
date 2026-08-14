from hsconfig.identity_graph import build_identity_gap_report, build_identity_graph_report


def test_identity_graph_reports_main_and_sideboard_multisets():
    deck_identity = {
        "deck_name": "Example",
        "deck_code_hash": "abc",
        "hero_dbf_id": 7,
        "format": "FT_WILD",
        "cards": [{"card_id": "CARD_001", "count": 2}],
        "sideboards": [{"owner_card_id": "CARD_001", "cards": [{"card_id": "CARD_002", "count": 1}]}],
    }

    report = build_identity_graph_report(
        deck_identity=deck_identity,
        hearthstonejson_receipt={"source": "mock", "card_count": 2},
    )
    gap_report = build_identity_gap_report(report)

    assert report["main_deck_multiset"] == {"CARD_001": 2}
    assert report["sideboard_multiset"] == {"CARD_002": 1}
    assert report["generated_token_closure"] == "not_in_scope_for_step1_identity_graph"
    assert "starting_hero_power_id" in gap_report["missing_identity_fields"]
