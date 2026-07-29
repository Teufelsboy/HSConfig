from __future__ import annotations

from datetime import date

from hsconfig.source_evidence_policy import classify_source_evidence

EXACT_FIXTURE_IDENTITY = {"deck_fingerprint": "fixture-fingerprint"}


def test_current_full_text_deck_matched_guide_can_promote():
    row = classify_source_evidence(
        {
            "source_family": "public_guide",
            "source_title": "ShadowPriest Guide",
            "normalized_text": (
                "ShadowPriest guide. Mulligan: keep Voidtouched Attendant "
                "and Mind Blast against slow decks. "
            )
            * 4,
            "publication_year": 2026,
            "source_visibility": "full_text",
            "deck_match": {
                "deck_name": "ShadowPriest",
                "matched_card_ids": ["SW_448"],
                "exact_deck_evidence": {
                    "matched": True,
                    "matched_deck_fingerprint": "fixture-fingerprint",
                },
            },
            "deck_match_scope": "exact_deck_matched",
        },
        deck_name="ShadowPriest",
        current_date=date(2026, 7, 15),
        deck_identity=EXACT_FIXTURE_IDENTITY,
    )

    assert row["source_visibility"] == "full_text"
    assert row["source_lane"] == "deck_matched_public_guide"
    assert row["source_rank_lane"] == "guide_current_deck_match"
    assert row["promotion_eligible"] is True
    assert row["strong_promotion_eligible"] is True
    assert row["promotion_blockers"] == []
    assert row["first_missing_source_action"] == "none"


def test_structured_current_deck_guide_claims_need_explicit_full_text_visibility():
    row = classify_source_evidence(
        {
            "source_family": "guide",
            "source_title": "Voidburn Wild Aggro Shadow Priest",
            "source_url": "https://example.test/shadowpriest",
            "source_visibility": "full_text",
            "normalized_text": "A current ShadowPriest guide with mulligan and sequencing advice.",
            "published_at": "2026-07-01T00:00:00Z",
            "deck_match": {
                "deck_name": "ShadowPriest",
                "matched_card_ids": ["SW_448", "SW_446"],
                "exact_deck_evidence": {
                    "matched": True,
                    "matched_deck_fingerprint": "fixture-fingerprint",
                },
            },
            "deck_match_scope": "exact_deck_matched",
            "mulligan": {"keep_card_ids": ["SW_446"]},
            "claims": [
                {
                    "claim_kind": "hero_power_transform",
                    "cards": ["SW_448"],
                    "stance": "enable_mind_spike_shadow_hero_power",
                }
            ],
        },
        deck_name="ShadowPriest",
        current_date=date(2026, 7, 15),
        deck_identity=EXACT_FIXTURE_IDENTITY,
    )

    assert row["source_visibility"] == "full_text"
    assert row["source_lane"] == "deck_matched_public_guide"
    assert row["promotion_eligible"] is True
    assert row["strong_promotion_eligible"] is True
    assert row["first_missing_source_action"] == "none"


def test_metadata_only_full_text_guide_cannot_promote_without_acquired_source_text():
    row = classify_source_evidence(
        {
            "source_family": "guide",
            "source_title": "Voidburn Wild Aggro Shadow Priest",
            "source_url": "https://example.test/shadowpriest",
            "source_visibility": "full_text",
            "published_at": "2026-07-01T00:00:00Z",
            "source_record_strength": "candidate_strong",
            "deck_match": {
                "deck_name": "ShadowPriest",
                "matched_card_ids": ["SW_448", "SW_446"],
                "exact_deck_evidence": {
                    "matched": True,
                    "matched_deck_fingerprint": "fixture-fingerprint",
                },
            },
            "deck_match_scope": "exact_deck_matched",
        },
        deck_name="ShadowPriest",
        current_date=date(2026, 7, 15),
        deck_identity=EXACT_FIXTURE_IDENTITY,
    )

    assert row["promotion_eligible"] is False
    assert row["strong_promotion_eligible"] is False
    assert row["trust_ceiling"] != "source_backed_strong"
    assert "missing_acquired_source_text" in row["promotion_blockers"]
    assert row["first_missing_source_action"] == "add_current_or_evergreen_wild_public_guide"
    assert row["next_source_action"] == "add_current_or_evergreen_wild_public_guide"


def test_structured_current_deck_guide_claims_without_source_text_do_not_self_certify():
    row = classify_source_evidence(
        {
            "source_family": "guide",
            "source_title": "Voidburn Wild Aggro Shadow Priest",
            "source_url": "https://example.test/shadowpriest",
            "published_at": "2026-07-01T00:00:00Z",
            "deck_match": {
                "deck_name": "ShadowPriest",
                "matched_card_ids": ["SW_448", "SW_446"],
            },
            "mulligan": {"keep_card_ids": ["SW_446"]},
            "claims": [
                {
                    "claim_kind": "hero_power_transform",
                    "cards": ["SW_448"],
                    "stance": "enable_mind_spike_shadow_hero_power",
                }
            ],
        },
        deck_name="ShadowPriest",
        current_date=date(2026, 7, 15),
    )

    assert row["source_visibility"] == "unknown"
    assert row["promotion_eligible"] is False
    assert row["strong_promotion_eligible"] is False
    assert "source_visibility_unknown_not_strong" in row["promotion_blockers"]
    assert row["first_missing_source_action"] == "add_full_text_public_guide_source"


def test_decklist_stats_snippet_policy_and_partial_records_never_promote():
    cases = [
        {"source_family": "decklist", "source_visibility": "decklist_only"},
        {"source_family": "stats", "source_visibility": "full_text"},
        {"source_family": "public_guide", "source_visibility": "snippet_only"},
        {
            "source_type": "versioned_internal_policy",
            "source_visibility": "full_text",
        },
        {
            "source_family": "public_guide",
            "source_visibility": "full_text",
            "source_record_strength": "partial",
        },
    ]

    for case in cases:
        row = classify_source_evidence(
            {
                **case,
                "source_title": "ShadowPriest",
                "normalized_text": "ShadowPriest guide text " * 20,
                "publication_year": 2026,
                "deck_match": {
                    "deck_name": "ShadowPriest",
                    "matched_card_ids": ["SW_448"],
                },
            },
            deck_name="ShadowPriest",
            current_date=date(2026, 7, 15),
        )

        assert row["strong_promotion_eligible"] is False
        assert row["first_missing_source_action"] != "none"


def test_retrieved_at_does_not_count_as_publication_year():
    row = classify_source_evidence(
        {
            "source_family": "public_guide",
            "source_title": "ShadowPriest Guide",
            "normalized_text": "ShadowPriest guide text " * 20,
            "retrieved_at": "2026-07-15T12:00:00Z",
            "source_visibility": "full_text",
            "deck_match": {
                "deck_name": "ShadowPriest",
                "matched_card_ids": ["SW_448"],
            },
        },
        deck_name="ShadowPriest",
        current_date=date(2026, 7, 15),
    )

    assert row["source_rank_lane"] != "guide_current_deck_match"
    assert "missing_publication_year" in row["promotion_blockers"]


def test_official_static_semantics_can_support_cardid_but_not_deck_strategy():
    record = {
        "source_family": "official_static_semantics",
        "source_type": "official_static_semantics",
        "source_visibility": "full_text",
        "publication_year": 2026,
        "source_record_strength": "candidate_strong",
        "deck_match_scope": "deck_or_archetype_matched",
        "deck_match": {
            "deck_name": "ShadowPriest",
            "matched_card_ids": ["SW_448"],
        },
        "claim_kind": "hero_power_transform",
        "cards": ["SW_448"],
        "normalized_text": (
            "Darkbishop Benedictus has Start of Game text that enters "
            "Shadowform when the deck's spells are all Shadow."
        ),
    }

    result = classify_source_evidence(
        record,
        deck_name="ShadowPriest",
        current_date=date(2026, 7, 16),
    )

    assert result["trust_ceiling"] == "static_semantics_only"
    assert result["strong_promotion_eligible"] is False
    assert result["static_runtime_surface_eligible"] is True
    assert result["static_runtime_surface_scope"] == "cardid_effect"
    assert result["static_runtime_surface_limit"] == (
        "static_semantics_supports_cardid_effects_only"
    )
    assert "static_semantics_not_deck_strategy" in result["promotion_blockers"]


def test_static_semantics_never_promotes_mulligan_claims():
    record = {
        "source_family": "official_static_semantics",
        "source_type": "official_static_semantics",
        "source_visibility": "full_text",
        "publication_year": 2026,
        "source_record_strength": "candidate_strong",
        "deck_match_scope": "deck_or_archetype_matched",
        "claim_kind": "mulligan_keep",
        "cards": ["SW_448"],
    }

    result = classify_source_evidence(
        record,
        deck_name="ShadowPriest",
        current_date="2026-07-16",
    )

    assert result["strong_promotion_eligible"] is False
    assert result["static_runtime_surface_eligible"] is False
    assert result["static_runtime_surface_scope"] == "not_runtime_surface_static"


def test_evergreen_wild_archetype_guide_can_be_strong_when_deck_matched():
    row = classify_source_evidence(
        {
            "source_family": "public_guide",
            "source_title": "Wild ShadowPriest Guide",
            "source_url": "https://example.test/wild-shadowpriest",
            "source_visibility": "full_text",
            "publication_year": 2021,
            "format_scope": "wild",
            "evergreen_wild_archetype": True,
            "source_record_strength": "candidate_strong",
            "normalized_text": (
                "Wild ShadowPriest guide. The deck is aggressive, starts with "
                "Mind Spike from Darkbishop Benedictus, and keeps early pressure "
                "cards such as Voidtouched Attendant and Shadowbomber."
            ) * 4,
            "deck_match": {
                "deck_name": "ShadowPriest",
                "matched_card_ids": ["SW_448", "SW_446", "GVG_009"],
                "exact_deck_evidence": {
                    "matched": True,
                    "matched_deck_fingerprint": "fixture-fingerprint",
                },
            },
            "deck_match_scope": "exact_deck_matched",
        },
        deck_name="ShadowPriest",
        current_date=date(2026, 7, 16),
        deck_identity=EXACT_FIXTURE_IDENTITY,
    )

    assert row["source_freshness_lane"] == "evergreen_wild_archetype"
    assert row["source_rank_lane"] == "guide_evergreen_wild_archetype"
    assert row["source_lane"] == "deck_matched_public_guide"
    assert row["promotion_eligible"] is True
    assert row["strong_promotion_eligible"] is False


def test_evergreen_wild_archetype_requires_two_unique_matched_cards():
    row = classify_source_evidence(
        {
            "source_family": "public_guide",
            "source_title": "Wild ShadowPriest Guide",
            "source_url": "https://example.test/wild-shadowpriest",
            "source_visibility": "full_text",
            "publication_year": 2021,
            "format_scope": "wild",
            "evergreen_wild_archetype": True,
            "source_record_strength": "candidate_strong",
            "normalized_text": (
                "Wild ShadowPriest guide. The deck is aggressive, starts with "
                "Mind Spike from Darkbishop Benedictus, and keeps early pressure "
                "cards such as Voidtouched Attendant and Shadowbomber."
            )
            * 4,
            "deck_match": {
                "deck_name": "ShadowPriest",
                "matched_card_ids": ["SW_448", "SW_448"],
            },
        },
        deck_name="ShadowPriest",
        current_date=date(2026, 7, 16),
    )

    assert row["source_freshness_lane"] == "stale_or_not_current"
    assert row["source_rank_lane"] == "guide_full_text_not_current"
    assert row["strong_promotion_eligible"] is False
    assert "source_not_current_or_evergreen_wild" in row["promotion_blockers"]


def test_old_non_wild_guide_stays_partial_and_requests_current_or_evergreen_source():
    row = classify_source_evidence(
        {
            "source_family": "public_guide",
            "source_title": "Old Standard Guide",
            "source_visibility": "full_text",
            "publication_year": 2021,
            "source_record_strength": "candidate_strong",
            "normalized_text": "Old guide text for a deck that no longer matches the current format. " * 8,
            "deck_match": {
                "deck_name": "ShadowPriest",
                "matched_card_ids": ["SW_448", "SW_446"],
            },
        },
        deck_name="ShadowPriest",
        current_date=date(2026, 7, 16),
    )

    assert row["source_freshness_lane"] == "stale_or_not_current"
    assert row["source_rank_lane"] == "guide_full_text_not_current"
    assert row["strong_promotion_eligible"] is False
    assert "source_not_current_or_evergreen_wild" in row["promotion_blockers"]
    assert row["first_missing_source_action"] == "add_current_or_evergreen_wild_public_guide"


def test_public_stats_families_are_stats_only_support_lanes():
    for family in ["stats", "statistical_enrichment", "hsguru", "hs_guru", "hs-guru"]:
        row = classify_source_evidence(
            {
                "source_family": family,
                "source_visibility": "full_text",
                "publication_year": 2026,
                "source_record_strength": "candidate_strong",
                "normalized_text": "Aggregate stats can support diagnostics but are not a full guide.",
                "deck_match": {
                    "deck_name": "ShadowPriest",
                    "matched_card_ids": ["SW_448", "SW_446"],
                },
            },
            deck_name="ShadowPriest",
            current_date=date(2026, 7, 16),
        )

        assert row["source_rank_lane"] == "statistical_enrichment"
        assert row["promotion_eligible"] is False
        assert row["strong_promotion_eligible"] is False
        assert "stats_only_not_strong_evidence" in row["promotion_blockers"]


def test_current_full_text_deck_matched_guide_is_strong_eligible():
    record = {
        "source_url": "https://example.test/shadowpriest-guide",
        "source_title": "2026 Wild ShadowPriest Guide",
        "source_family": "guide",
        "source_visibility": "full_text",
        "publication_year": 2026,
        "deck_match": {
            "deck_name": "ShadowPriest",
            "matched_card_ids": ["SW_448", "TOY_381"],
            "exact_deck_evidence": {
                "matched": True,
                "matched_deck_fingerprint": "fixture-fingerprint",
            },
        },
        "deck_match_scope": "exact_deck_matched",
        "normalized_text": "ShadowPriest guide with mulligan, burn posture, and Mind Spike plan.",
        "source_record_strength": "candidate_strong",
    }

    result = classify_source_evidence(
        record,
        deck_name="ShadowPriest",
        current_date="2026-07-16",
        deck_identity=EXACT_FIXTURE_IDENTITY,
    )

    assert result["source_visibility"] == "full_text"
    assert result["source_rank_lane"] == "guide_current_deck_match"
    assert result["source_lane"] == "deck_matched_public_guide"
    assert result["promotion_eligible"] is True
    assert result["strong_promotion_eligible"] is True
    assert result["trust_ceiling"] == "source_backed_strong"
    assert result["promotion_blockers"] == []
    assert result["first_missing_source_action"] == "none"


def test_decklist_only_source_never_promotes_to_strong():
    record = {
        "source_url": "https://example.test/mech-paladin",
        "source_title": "Mech Paladin Decklist",
        "source_family": "decklist",
        "source_visibility": "decklist_only",
        "publication_year": 2026,
        "deck_match": {
            "deck_name": "MechPala",
            "matched_card_ids": ["GVG_058", "BOT_906"],
        },
        "source_record_strength": "candidate_strong",
    }

    result = classify_source_evidence(record, deck_name="MechPala", current_date="2026-07-16")

    assert result["source_rank_lane"] == "decklist_only"
    assert result["source_lane"] == "decklist_only"
    assert result["promotion_eligible"] is False
    assert result["strong_promotion_eligible"] is False
    assert result["trust_ceiling"] == "decklist_informed"
    assert "decklist_only_not_strong_evidence" in result["promotion_blockers"]
    assert result["first_missing_source_action"] == "add_current_or_evergreen_wild_public_guide"


def test_static_semantics_supports_cardid_effects_but_not_strategy_surfaces():
    effect_record = {
        "source_family": "hearthstonejson_static_semantics",
        "claim_kind": "hero_power_transform",
        "source_visibility": "full_text",
        "deck_match_scope": "deck_or_archetype_matched",
        "publication_year": 2026,
    }
    strategy_record = {
        "source_family": "hearthstonejson_static_semantics",
        "claim_kind": "mulligan_keep",
        "source_visibility": "full_text",
        "deck_match_scope": "deck_or_archetype_matched",
        "publication_year": 2026,
    }

    effect = classify_source_evidence(effect_record, deck_name="ShadowPriest", current_date="2026-07-16")
    strategy = classify_source_evidence(strategy_record, deck_name="ShadowPriest", current_date="2026-07-16")

    assert effect["static_runtime_surface_eligible"] is True
    assert effect["static_runtime_surface_scope"] == "cardid_effect"
    assert effect["trust_ceiling"] == "static_semantics_only"
    assert effect["strong_promotion_eligible"] is False

    assert strategy["static_runtime_surface_eligible"] is False
    assert strategy["static_runtime_surface_scope"] == "not_runtime_surface_static"
    assert strategy["static_runtime_surface_limit"] == "static_semantics_does_not_prove_strategy_surface"
    assert strategy["strong_promotion_eligible"] is False
