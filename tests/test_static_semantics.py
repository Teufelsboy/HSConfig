from hsconfig.static_semantics import infer_static_semantics


def _families(card):
    return set(infer_static_semantics(card)["families"])


def test_infers_mechanics_from_type_mechanics_referenced_tags_and_text():
    card = {
        "id": "TEST_001",
        "type": "WEAPON",
        "mechanics": ["TRADEABLE"],
        "referenced_tags": ["OVERLOAD"],
        "text": "Battlecry: Discover a spell. Dredge. Silence an enemy minion.",
    }

    families = _families(card)

    assert {"weapon", "tradeable", "overload", "battlecry", "discover", "dredge", "silence"} <= families


def test_infers_location_secret_and_generated_entity_patterns():
    card = {
        "id": "TEST_002",
        "type": "LOCATION",
        "mechanics": ["SECRET"],
        "text": "Secret: When your opponent plays a minion, summon a random minion.",
    }

    families = _families(card)

    assert {"location", "secret", "summon", "generated_entity", "generated_entity_random_pool"} <= families


def test_infers_hero_power_transform_and_start_of_game_from_tags_and_text():
    card = {
        "id": "SW_448",
        "type": "MINION",
        "referenced_tags": ["START_OF_GAME_KEYWORD"],
        "text": "Start of Game: If the spells in your deck are all Shadow, enter Shadowform.",
    }

    families = _families(card)

    assert {"start_of_game", "shadowform", "hero_power", "hero_power_transform"} <= families


def test_warning_only_contains_unlowerable_choice_surfaces():
    result = infer_static_semantics(
        {
            "id": "TEST_003",
            "type": "SPELL",
            "text": "Dredge. Tradeable. Choose One - Summon a minion; or Draw a card.",
        }
    )

    assert "dredge" in result["families"]
    assert "tradeable" in result["families"]
    assert "choose_one" in result["families"]
    assert "dredge" in result["warning_only"]
    assert "tradeable" in result["warning_only"]
