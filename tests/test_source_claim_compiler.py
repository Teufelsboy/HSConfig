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
                "Keep Papercraft Angel, Twilight Deceptor, Raise Dead, and "
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
            "reason": "unsupported_broad_claim",
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
            "normalized_text": "Do not keep Darkbishop Benedictus. Keep Papercraft Angel.",
        }
    ]

    payload = compile_source_search_records(
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        acquired_records=acquired,
        current_date="2026-07-15",
    )

    assert payload["records"][0]["mulligan"]["keep_card_ids"] == ["TOY_381"]
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
                "Keep Papercraft Angel and Twilight Deceptor."
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
    } in claims
