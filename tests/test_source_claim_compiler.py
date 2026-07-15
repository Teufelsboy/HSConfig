from __future__ import annotations

from hsconfig.source_claim_compiler import compile_source_search_records


DECK_IDENTITY = {
    "deck_name": "ShadowPriest",
    "deck_slug": "shadowpriest",
    "deck_code_hash": "sha256:shadow",
    "cards": [
        {"card_id": "BAR_735", "name": "Darkbishop Benedictus", "cost": 5, "count": 1},
        {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2},
        {"card_id": "SW_444", "name": "Twilight Deceptor", "cost": 2, "count": 2},
        {"card_id": "SCH_514", "name": "Raise Dead", "cost": 0, "count": 2},
        {"card_id": "GVG_009", "name": "Shadowbomber", "cost": 1, "count": 2},
    ],
}


def test_compile_source_search_records_extracts_atomic_shadowpriest_claims():
    acquired = [
        {
            "source_url": "https://example.test/shadowpriest",
            "source_title": "Voidburn Wild Aggro Shadow Priest",
            "source_family": "guide",
            "retrieved_at": "2026-07-15T00:00:00Z",
            "deck_match": {
                "deck_name": "ShadowPriest",
                "archetype": "shadowpriest",
                "matched_card_ids": [
                    "TOY_381",
                    "SW_444",
                    "SCH_514",
                    "GVG_009",
                    "BAR_735",
                ],
            },
            "normalized_text": (
                "Mulligan: Keep Papercraft Angel, Twilight Deceptor, Raise Dead, and "
                "Shadowbomber. Do not keep any 4 cost or higher cards. "
                "Darkbishop Benedictus enables the Shadow hero power. Mind "
                "Spike can clear the enemy board or go face against slower decks."
            ),
        }
    ]

    payload = compile_source_search_records(
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        acquired_records=acquired,
        current_date="2026-07-15",
    )

    record = payload["records"][0]
    assert record["mulligan"]["keep_card_ids"] == [
        "TOY_381",
        "SW_444",
        "SCH_514",
        "GVG_009",
    ]
    assert record["mulligan"]["discard_cost_min"] == 4
    claim_kinds = [claim["claim_kind"] for claim in record["claims"]]
    assert "hero_power_transform" in claim_kinds
    assert "gameplan_posture" in claim_kinds
    assert not any(
        claim["claim_kind"] == "mulligan_keep" and claim.get("cards") == ["BAR_735"]
        for claim in record["claims"]
    )


def test_compile_source_search_records_keeps_decklist_only_non_promoting():
    acquired = [
        {
            "source_url": "https://example.test/decklist",
            "source_title": "Thin Public Decklist",
            "source_family": "decklist",
            "retrieved_at": "2026-07-15T00:00:00Z",
            "deck_match": {
                "deck_name": "ThinDeck",
                "archetype": "thindeck",
                "matched_card_ids": ["CARD_001"],
            },
            "normalized_text": "Deck code: AAEBA-example Fixture Card Second Fixture Card",
        }
    ]
    deck_identity = {
        "deck_name": "ThinDeck",
        "deck_slug": "thindeck",
        "deck_code_hash": "sha256:thin",
        "cards": [{"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}],
    }

    payload = compile_source_search_records(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        acquired_records=acquired,
        current_date="2026-07-15",
    )

    assert payload["records"][0]["source_family"] == "decklist"
    assert payload["records"][0]["mulligan"]["keep_card_ids"] == []
    assert payload["records"][0]["claims"][0]["claim_kind"] == "card_role"
    assert payload["records"][0]["claims"][0]["source_confidence"] == "medium"
    assert payload["source_claim_compiler_report"]["promotion_candidate_count"] == 0


def test_compile_source_search_records_reports_unsupported_broad_claims():
    acquired = [
        {
            "source_url": "https://example.test/broad",
            "source_title": "Broad Shadow Priest Tips",
            "source_family": "guide",
            "retrieved_at": "2026-07-15T00:00:00Z",
            "deck_match": {
                "deck_name": "ShadowPriest",
                "archetype": "shadowpriest",
                "matched_card_ids": ["TOY_381"],
            },
            "normalized_text": (
                "This deck should play aggressively and pressure the opponent "
                "without describing exact cards, targets, or mulligan choices."
            ),
        }
    ]

    payload = compile_source_search_records(
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        acquired_records=acquired,
        current_date="2026-07-15",
    )

    assert payload["records"][0]["claims"] == []
    assert payload["source_claim_compiler_report"]["promotion_candidate_count"] == 0
    assert payload["source_claim_compiler_report"]["unsupported_claims"] == [
        {
            "source_url": "https://example.test/broad",
            "source_title": "Broad Shadow Priest Tips",
            "source_family": "guide",
            "reason": "unsupported_or_non_runtime_claim",
            "evidence_text_short": (
                "This deck should play aggressively and pressure the opponent "
                "without describing exact cards, targets, or mulligan choices."
            ),
        }
    ]


def test_compile_source_search_records_does_not_keep_negative_mulligan_mentions():
    acquired = [
        {
            "source_url": "https://example.test/shadowpriest",
            "source_title": "Voidburn Wild Aggro Shadow Priest",
            "source_family": "guide",
            "retrieved_at": "2026-07-15T00:00:00Z",
            "deck_match": {
                "deck_name": "ShadowPriest",
                "archetype": "shadowpriest",
                "matched_card_ids": ["TOY_381", "BAR_735"],
            },
            "normalized_text": (
                "Mulligan: Do not keep Darkbishop Benedictus. "
                "Mulligan: Keep Papercraft Angel."
            ),
        }
    ]

    payload = compile_source_search_records(
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        acquired_records=acquired,
        current_date="2026-07-15",
    )

    assert payload["records"][0]["mulligan"]["keep_card_ids"] == ["TOY_381"]
    assert payload["records"][0]["mulligan"]["evidence_text_short"] == (
        "Mulligan: Keep Papercraft Angel"
    )
    assert {
        "claim_kind": "mulligan_keep",
        "stance": "keep",
        "scope": "card",
        "evidence_text_short": "Mulligan: Keep Papercraft Angel",
        "source_confidence": "high",
        "promotion_eligible": True,
        "cards": ["TOY_381"],
        "timing": "mulligan",
    } in payload["records"][0]["claims"]
    assert not any(
        claim["claim_kind"] == "mulligan_keep" and claim.get("cards") == ["BAR_735"]
        for claim in payload["records"][0]["claims"]
    )


def test_compile_source_search_records_limits_hero_power_transform_to_enabler():
    acquired = [
        {
            "source_url": "https://example.test/shadowpriest",
            "source_title": "Voidburn Wild Aggro Shadow Priest",
            "source_family": "guide",
            "retrieved_at": "2026-07-15T00:00:00Z",
            "deck_match": {
                "deck_name": "ShadowPriest",
                "archetype": "shadowpriest",
                "matched_card_ids": ["BAR_735", "TOY_381", "SW_444"],
            },
            "normalized_text": (
                "Darkbishop Benedictus enables the Shadow hero power. "
                "Mulligan: Keep Papercraft Angel and Twilight Deceptor."
            ),
        }
    ]

    payload = compile_source_search_records(
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        acquired_records=acquired,
        current_date="2026-07-15",
    )

    transform_claims = [
        claim
        for claim in payload["records"][0]["claims"]
        if claim["claim_kind"] == "hero_power_transform"
    ]
    assert transform_claims == [
        {
            "claim_kind": "hero_power_transform",
            "stance": "enable_shadow_hero_power",
            "scope": "card",
            "evidence_text_short": "Darkbishop Benedictus enables the Shadow hero power",
            "source_confidence": "high",
            "promotion_eligible": True,
            "cards": ["BAR_735"],
            "timing": "start_of_game",
        }
    ]


def test_compile_source_search_records_uses_gameplan_for_hero_power_target_text():
    acquired = [
        {
            "source_url": "https://example.test/shadowpriest",
            "source_title": "Voidburn Wild Aggro Shadow Priest",
            "source_family": "guide",
            "retrieved_at": "2026-07-15T00:00:00Z",
            "deck_match": {
                "deck_name": "ShadowPriest",
                "archetype": "shadowpriest",
                "matched_card_ids": ["BAR_735"],
            },
            "normalized_text": "Mind Spike can clear the enemy board or go face against slower decks.",
        }
    ]

    payload = compile_source_search_records(
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        acquired_records=acquired,
        current_date="2026-07-15",
    )

    claims = payload["records"][0]["claims"]
    assert not any(claim["claim_kind"] == "targeting_rule" for claim in claims)
    assert {
        "claim_kind": "gameplan_posture",
        "stance": "hero_power_board_or_face_pressure",
        "scope": "deck",
        "evidence_text_short": (
            "Mind Spike can clear the enemy board or go face against slower decks"
        ),
        "source_confidence": "high",
        "promotion_eligible": True,
    } in claims


def test_compile_source_search_records_does_not_treat_generic_gameplay_keep_prose_as_mulligan():
    deck_identity = {
        "deck_name": "FireMage",
        "cards": [{"card_id": "CS2_029", "name": "Fireball", "cost": 4, "count": 2}],
    }
    acquired = [
        {
            "source_url": "https://example.test/firemage",
            "source_title": "Fire Mage gameplay notes",
            "source_family": "guide",
            "normalized_text": "Use Fireball to keep pressure on the opponent.",
        }
    ]

    payload = compile_source_search_records(
        deck_name="FireMage",
        deck_identity=deck_identity,
        acquired_records=acquired,
        current_date="2026-07-15",
    )

    assert payload["records"][0]["mulligan"]["keep_card_ids"] == []
    assert not any(
        claim["claim_kind"] == "mulligan_keep"
        for claim in payload["records"][0]["claims"]
    )


def test_compile_preserves_acquisition_classification_fields():
    acquired = [
        {
            "source_url": "https://example.test/shadowpriest",
            "source_title": "Shadow Priest Mulligan Guide 2026",
            "source_family": "guide",
            "source_visibility": "full_text",
            "source_lane_hint": "public_guide",
            "source_record_strength": "candidate_strong",
            "publication_year": 2026,
            "deck_match": {
                "deck_name": "ShadowPriest",
                "archetype": "shadowpriest",
                "matched_card_ids": ["TOY_381"],
            },
            "deck_match_scope": "deck_or_archetype_matched",
            "normalized_text": "Mulligan: Keep Papercraft Angel.",
        }
    ]

    payload = compile_source_search_records(
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        acquired_records=acquired,
        current_date="2026-07-15",
    )

    record = payload["records"][0]
    assert record["source_visibility"] == "full_text"
    assert record["source_lane_hint"] == "public_guide"
    assert record["source_record_strength"] == "candidate_strong"
    assert record["publication_year"] == 2026
    assert record["deck_match_scope"] == "deck_or_archetype_matched"


def test_compile_keeps_snippet_only_guides_diagnostic_only():
    deck_identity = {
        "deck_name": "ThinDeck",
        "deck_slug": "thindeck",
        "deck_code_hash": "sha256:thin",
        "cards": [{"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}],
    }
    acquired = [
        {
            "source_url": "https://example.test/thin-snippet",
            "source_title": "ThinDeck Mulligan Guide",
            "source_family": "guide",
            "source_visibility": "snippet_only",
            "source_lane_hint": "unknown",
            "source_record_strength": "diagnostic_only",
            "publication_year": 2026,
            "deck_match": {
                "deck_name": "ThinDeck",
                "archetype": "thindeck",
                "matched_card_ids": ["CARD_001"],
            },
            "deck_match_scope": "deck_or_archetype_matched",
            "normalized_text": "Mulligan: Keep Fixture Card.",
        }
    ]

    payload = compile_source_search_records(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        acquired_records=acquired,
        current_date="2026-07-15",
    )

    record = payload["records"][0]
    assert record["source_visibility"] == "snippet_only"
    assert record["mulligan"]["keep_card_ids"] == []
    assert record["claims"] == []
    assert payload["source_claim_compiler_report"]["promotion_candidate_count"] == 0
    assert payload["source_claim_compiler_report"]["unsupported_claims"][0]["reason"] == (
        "snippet_only_source_not_lowerable"
    )


def test_compile_ignores_keep_without_mulligan_context():
    deck_identity = {
        "deck_name": "EffectDeck",
        "deck_slug": "effectdeck",
        "deck_code_hash": "sha256:effect",
        "cards": [{"card_id": "CARD_001", "name": "Keepable Name", "cost": 1, "count": 2}],
    }
    acquired = [
        {
            "source_url": "https://example.test/no-mulligan",
            "source_title": "EffectDeck Strategy",
            "source_family": "guide",
            "source_visibility": "full_text",
            "source_record_strength": "candidate_strong",
            "deck_match": {"deck_name": "EffectDeck", "archetype": "effectdeck", "matched_card_ids": ["CARD_001"]},
            "deck_match_scope": "deck_or_archetype_matched",
            "normalized_text": "Keepable Name is important later. This page does not discuss mulligan or opening hand.",
        }
    ]

    compiled = compile_source_search_records(
        deck_name="EffectDeck",
        deck_identity=deck_identity,
        acquired_records=acquired,
        current_date="2026-07-15",
    )

    assert compiled["records"][0]["mulligan"]["keep_card_ids"] == []
    assert not any(claim["claim_kind"] == "mulligan_keep" for claim in compiled["records"][0]["claims"])
    assert compiled["source_claim_compiler_report"]["unsupported_claims"]


def test_compile_decklist_card_role_is_non_promoting():
    deck_identity = {
        "deck_name": "PirateDH",
        "deck_slug": "piratedh",
        "deck_code_hash": "sha256:pirate",
        "cards": [{"card_id": "CARD_001", "name": "Patches the Pirate", "cost": 1, "count": 1}],
    }
    acquired = [
        {
            "source_url": "https://example.test/decklist",
            "source_title": "Pirate Demon Hunter Decklist",
            "source_family": "decklist",
            "source_visibility": "decklist_only",
            "source_record_strength": "partial",
            "deck_match": {"deck_name": "PirateDH", "archetype": "piratedh", "matched_card_ids": ["CARD_001"]},
            "deck_match_scope": "deck_or_archetype_matched",
            "normalized_text": "Deck code and card list.",
        }
    ]

    compiled = compile_source_search_records(
        deck_name="PirateDH",
        deck_identity=deck_identity,
        acquired_records=acquired,
        current_date="2026-07-15",
    )

    claim = compiled["records"][0]["claims"][0]
    assert claim["claim_kind"] == "card_role"
    assert claim["source_confidence"] == "medium"
    assert claim["promotion_eligible"] is False
