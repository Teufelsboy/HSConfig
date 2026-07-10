from hsconfig.source_research_manifest import build_source_research_manifest


def test_manifest_emits_aliases_and_required_source_families():
    manifest = build_source_research_manifest(
        deck_name="MechPala",
        deck_identity={
            "deck_name": "MechPala",
            "deck_code_hash": "sha256:abc",
            "cards": [{"card_id": "BOT_001", "name": "Mech Example", "count": 2}],
        },
        candidate_archetypes={
            "primary_archetype": "mech_board_scaling",
            "candidates": [{"archetype": "mech_board_scaling", "confidence": "source_backed"}],
        },
        fixture_row={
            "deck_name": "MechPala",
            "archetype_bucket": "mech_board_scaling",
            "primary_mechanics": ["mech", "magnetic", "board_scaling"],
        },
    )

    assert manifest["deck_name"] == "MechPala"
    assert "Mech Paladin" in manifest["search_aliases"]
    assert manifest["required_source_families"] == [
        "guide",
        "mulligan_guide",
        "card_text",
        "metadata",
    ]
    assert manifest["research_questions"][0]["claim_kind"] == "card_role"
    assert manifest["card_targets"][0] == {
        "card_id": "BOT_001",
        "name": "Mech Example",
        "required_claims": ["card_role", "mechanic_usage"],
    }


def test_manifest_asks_for_source_backed_mulligan_specifics():
    manifest = build_source_research_manifest(
        deck_name="MechPala",
        deck_identity={
            "deck_name": "MechPala",
            "deck_code_hash": "sha256:abc",
            "cards": [{"card_id": "BOT_001", "name": "Mech Example", "count": 2}],
        },
        candidate_archetypes={"primary_archetype": "mech_board_scaling"},
        fixture_row=None,
    )

    questions = [row["question"].lower() for row in manifest["research_questions"]]

    assert any("always keep" in question for question in questions)
    assert any("coin" in question and "mulligan" in question for question in questions)
    assert any("opponent class" in question for question in questions)
    assert any(
        "hand partner" in question or "with another card" in question
        for question in questions
    )
    assert any("throw" in question or "discard" in question for question in questions)
    assert any(
        "source confidence" in question
        and "guide" in question
        and "static card semantics" in question
        for question in questions
    )


def test_manifest_uses_repo_deck_name_when_no_known_alias_exists():
    manifest = build_source_research_manifest(
        deck_name="UnknownDeck",
        deck_identity={"deck_name": "UnknownDeck", "deck_code_hash": "sha256:x", "cards": []},
        candidate_archetypes={"primary_archetype": "generic_low_confidence", "candidates": []},
        fixture_row=None,
    )

    assert manifest["search_aliases"] == ["UnknownDeck"]
    assert manifest["mechanic_focus"] == ["generic_low_confidence"]


def test_manifest_splits_non_matrix_archetype_tokens_into_useful_mechanics():
    manifest = build_source_research_manifest(
        deck_name="CustomPirateWeapon",
        deck_identity={
            "deck_name": "CustomPirateWeapon",
            "deck_code_hash": "sha256:custom",
            "cards": [{"card_id": "CS2_106", "name": "Weapon Example", "count": 1}],
        },
        candidate_archetypes={"primary_archetype": "pirate_weapon_pressure"},
        fixture_row=None,
    )

    assert manifest["mechanic_focus"] == ["pirate", "weapon_pressure"]
    assert manifest["card_targets"][0]["required_claims"] == ["card_role", "targeting_rule"]


def test_manifest_covers_representative_matrix_aliases_and_mechanics():
    manifest = build_source_research_manifest(
        deck_name="BigShaman",
        deck_identity={
            "deck_name": "BigShaman",
            "deck_code_hash": "sha256:big",
            "cards": [{"card_id": "EX1_259", "name": "Lightning Storm", "count": 1}],
        },
        candidate_archetypes={"primary_archetype": "big_recruit_deathrattle_cheat"},
        fixture_row={
            "deck_name": "BigShaman",
            "archetype_bucket": "big_recruit_deathrattle_cheat",
            "primary_mechanics": ["big_minion", "recruit", "deathrattle", "cheat"],
        },
    )

    assert "Big Shaman" in manifest["search_aliases"]
    assert manifest["card_targets"][0]["required_claims"] == ["card_role", "mechanic_usage"]
