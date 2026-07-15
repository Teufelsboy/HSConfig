from hsconfig.static_semantics import build_static_semantics_source_records


def test_static_semantics_records_preserve_darkbishop_effect_without_mulligan_keep():
    records = build_static_semantics_source_records(
        {
            "deck_name": "ShadowPriest",
            "cards": [{"card_id": "SW_448", "count": 1}],
        },
        {
            "SW_448": {
                "id": "SW_448",
                "name": "Darkbishop Benedictus",
                "type": "MINION",
                "referenced_tags": ["START_OF_GAME_KEYWORD"],
                "text": (
                    "Start of Game: If the spells in your deck are all Shadow, "
                    "enter Shadowform."
                ),
            }
        },
        build_id="hsjson-20260715",
    )

    assert len(records) == 1
    record = records[0]
    assert record["source_family"] == "hearthstonejson_static_semantics"
    assert record["source_type"] == "official_card_data"
    assert record["source_record_strength"] == "static_semantics"
    assert record["source_visibility"] == "full_text"
    assert record["deck_name"] == "ShadowPriest"
    assert record["source_url"] == "hearthstonejson://hsjson-20260715/SW_448"

    claim_kinds = {claim["claim_kind"] for claim in record["claims"]}
    assert "hero_power_transform" in claim_kinds
    assert "mulligan_keep" not in claim_kinds
    assert "mulligan_discard" not in claim_kinds
    assert not any(
        claim["claim_kind"] == "mechanic_usage" and claim["mechanic"] == "hero_power"
        for claim in record["claims"]
    )

    transform_claim = next(
        claim for claim in record["claims"] if claim["claim_kind"] == "hero_power_transform"
    )
    assert transform_claim["cards"] == ["SW_448"]
    assert transform_claim["source_family"] == "hearthstonejson_static_semantics"
    assert transform_claim["source_type"] == "official_card_data"
    assert transform_claim["claim_readiness"] == "source_backed_static_semantics"
    assert transform_claim["opening_hand_relevant"] is False
    assert transform_claim["stance"] == "enable_transformed_hero_power"


def test_static_semantics_records_only_emit_for_cards_in_deck_identity():
    records = build_static_semantics_source_records(
        {
            "deck_name": "ShadowPriest",
            "cards": [{"card_id": "SW_448", "count": 1}],
        },
        {
            "SW_448": {
                "id": "SW_448",
                "name": "Darkbishop Benedictus",
                "type": "MINION",
                "referenced_tags": ["START_OF_GAME_KEYWORD"],
                "text": (
                    "Start of Game: If the spells in your deck are all Shadow, "
                    "enter Shadowform."
                ),
            },
            "OFF_DECK": {
                "id": "OFF_DECK",
                "name": "Off Deck Battlecry",
                "type": "MINION",
                "text": "Battlecry: Deal 2 damage.",
            },
        },
        build_id="hsjson-20260715",
    )

    assert [record["card_id"] for record in records] == ["SW_448"]


def test_static_semantics_records_emit_mechanic_usage_for_supported_families():
    records = build_static_semantics_source_records(
        {
            "deck_name": "FixtureDeck",
            "cards": [
                {"card_id": "TEST_BATTLECRY", "count": 1},
                {"card_id": "TEST_DREDGE", "count": 1},
            ],
        },
        {
            "TEST_BATTLECRY": {
                "id": "TEST_BATTLECRY",
                "name": "Battlecry Fixture",
                "type": "MINION",
                "mechanics": ["BATTLECRY"],
                "text": "Battlecry: Deal 2 damage.",
            },
            "TEST_DREDGE": {
                "id": "TEST_DREDGE",
                "name": "Dredge Fixture",
                "type": "SPELL",
                "text": "Dredge.",
            },
        },
        build_id="hsjson-20260715",
    )

    by_card = {record["card_id"]: record for record in records}

    battlecry_claims = by_card["TEST_BATTLECRY"]["claims"]
    assert any(
        claim["claim_kind"] == "mechanic_usage" and claim["mechanic"] == "battlecry"
        for claim in battlecry_claims
    )
    assert all(claim["claim_kind"] != "mulligan_keep" for claim in battlecry_claims)

    dredge_claims = by_card["TEST_DREDGE"]["claims"]
    dredge_claim = next(claim for claim in dredge_claims if claim["mechanic"] == "dredge")
    assert dredge_claim["claim_kind"] == "mechanic_usage"
    assert dredge_claim["runtime_block"] == ""
    assert dredge_claim["runtime_suppression_reason"]


def test_static_semantics_records_do_not_fallback_to_full_card_map_without_deck_cards():
    records = build_static_semantics_source_records(
        {"deck_name": "FixtureDeck"},
        {
            "TEST_BATTLECRY": {
                "id": "TEST_BATTLECRY",
                "name": "Battlecry Fixture",
                "type": "MINION",
                "mechanics": ["BATTLECRY"],
                "text": "Battlecry: Deal 2 damage.",
            },
        },
        build_id="hsjson-20260715",
    )

    assert records == []
