from __future__ import annotations

import json
from pathlib import Path

from hsconfig.source_document_builder import build_source_document_bundle
from hsconfig.source_autopilot import (
    build_source_autopilot_bundle,
    extract_source_evidence_rows,
    rank_public_sources,
)


FIXTURES = Path(__file__).parent / "fixtures"

SHADOW_DECK_IDENTITY = {
    "deck_name": "ShadowPriest",
    "deck_code_hash": "sha256:shadow",
    "deck_slug": "shadowpriest",
    "cards": [
        {"card_id": "SW_448", "name": "Darkbishop Benedictus", "cost": 5, "count": 1},
        {"card_id": "SW_446", "name": "Voidtouched Attendant", "cost": 1, "count": 2},
        {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2},
        {"card_id": "SW_444", "name": "Twilight Deceptor", "cost": 2, "count": 2},
        {"card_id": "SCH_514", "name": "Raise Dead", "cost": 0, "count": 2},
        {"card_id": "GVG_009", "name": "Shadowbomber", "cost": 1, "count": 2},
    ],
}


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_rank_public_sources_prefers_current_matching_guides_over_decklists():
    guide = _fixture("source_search_shadowpriest_2026.json")["records"][0]
    decklist = _fixture("source_search_decklist_only.json")["records"][0]

    ranked = rank_public_sources(
        deck_name="ShadowPriest",
        deck_identity=SHADOW_DECK_IDENTITY,
        source_search_records=[decklist, guide],
        current_date="2026-07-15",
    )

    assert ranked[0]["source_url"] == guide["source_url"]
    assert ranked[0]["source_rank_lane"] == "guide_current_deck_match"
    assert ranked[1]["source_rank_lane"] == "decklist_only"


def test_rank_public_sources_does_not_treat_retrieval_time_as_publication_currency():
    ranked = rank_public_sources(
        deck_name="ShadowPriest",
        deck_identity=SHADOW_DECK_IDENTITY,
        source_search_records=[
            {
                "source_url": "https://example.test/shadowpriest",
                "source_title": "Shadow Priest guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-15T00:00:00Z",
                "deck_match": {
                    "deck_name": "ShadowPriest",
                    "matched_card_ids": ["SW_448", "SW_446"],
                },
            }
        ],
        current_date="2026-07-15",
    )

    assert ranked[0]["source_rank_lane"] == "guide_card_overlap"


def test_extract_source_evidence_rows_preserves_darkbishop_effect_without_mulligan_row():
    records = _fixture("source_search_shadowpriest_2026.json")["records"]

    rows = extract_source_evidence_rows(
        deck_name="ShadowPriest",
        deck_identity=SHADOW_DECK_IDENTITY,
        ranked_sources=rank_public_sources(
            deck_name="ShadowPriest",
            deck_identity=SHADOW_DECK_IDENTITY,
            source_search_records=records,
            current_date="2026-07-15",
        ),
        current_date="2026-07-15",
    )

    darkbishop_rows = [
        row
        for row in rows
        if row.get("cards") == ["SW_448"] or row.get("card_mentions") == ["Darkbishop Benedictus"]
    ]
    assert any(row["claim_kind"] == "hero_power_transform" for row in darkbishop_rows)
    assert not any(row["claim_kind"] == "mulligan_keep" for row in darkbishop_rows)
    assert not any(row["claim_kind"] == "mulligan_discard" for row in darkbishop_rows)


def test_extract_source_evidence_rows_preserves_darkbishop_effect_not_mulligan_keep():
    test_extract_source_evidence_rows_preserves_darkbishop_effect_without_mulligan_row()


def test_build_source_autopilot_bundle_outputs_strict_source_documents():
    payload = _fixture("source_search_shadowpriest_2026.json")

    bundle = build_source_autopilot_bundle(
        deck_name="ShadowPriest",
        deck_identity=SHADOW_DECK_IDENTITY,
        source_search_records=payload["records"],
        current_date="2026-07-15",
    )

    assert bundle["source_autopilot_report"]["status"] == "OK"
    assert bundle["source_autopilot_report"]["source_rank_summary"]["guide_current_deck_match"] == 1
    assert bundle["source_autopilot_report"]["claim_kind_counts"]["mulligan_keep"] == 4
    summary = bundle["source_autopilot_report"]["strong_closure_summary"]
    assert summary["technical_no_block"] is True
    assert summary["source_backed_strong_ready"] is True
    assert summary["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert summary["first_missing_source_action"] == "none"
    assert bundle["source_documents_payload"]["source_documents"]

    strict_bundle = build_source_document_bundle(
        deck_identity=SHADOW_DECK_IDENTITY,
        card_metadata={"cards": SHADOW_DECK_IDENTITY["cards"]},
        source_documents=bundle["source_documents_payload"]["source_documents"],
        current_date="2026-07-15",
    )
    assert strict_bundle["unsupported_claims"] == []
    assert any(claim["claim_kind"] == "hero_power_transform" for claim in strict_bundle["claims"])


def test_build_source_autopilot_bundle_keeps_weak_sources_non_blocking_and_visible():
    payload = _fixture("source_search_decklist_only.json")
    deck_identity = {
        "deck_name": "ThinDeck",
        "deck_code_hash": "sha256:thin",
        "deck_slug": "thindeck",
        "cards": [{"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}],
    }

    bundle = build_source_autopilot_bundle(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        source_search_records=payload["records"],
        current_date="2026-07-15",
    )

    report = bundle["source_autopilot_report"]
    assert report["status"] == "OK"
    assert report["source_rank_summary"]["decklist_only"] == 1
    assert report["strong_candidate"] is False
    assert report["strong_closure_summary"]["technical_no_block"] is True
    assert report["strong_closure_summary"]["source_backed_strong_ready"] is False
    assert report["strong_closure_summary"]["semantic_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["strong_closure_summary"]["first_missing_source_action"] == "add_explicit_mulligan_source"
    assert report["first_missing_source_action"] == report["strong_closure_summary"]["first_missing_source_action"]


def test_build_source_autopilot_bundle_does_not_call_deck_scoped_guide_strong():
    deck_identity = {
        "deck_name": "ThinDeck",
        "deck_code_hash": "sha256:thin",
        "deck_slug": "thindeck",
        "cards": [{"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}],
    }
    record = {
        "source_url": "https://example.com/thin-guide",
        "source_title": "Thin Guide",
        "source_family": "guide",
        "retrieved_at": "2026-07-15T00:00:00Z",
        "deck_match": {
            "deck_name": "ThinDeck",
            "archetype": "aggro_fixture",
            "matched_card_ids": ["CARD_001"],
        },
        "claims": [
            {
                "claim_kind": "archetype",
                "scope": "deck",
                "stance": "aggressive",
                "evidence_text_short": "The deck is an aggressive strategy.",
                "source_confidence": "high",
            }
        ],
    }

    bundle = build_source_autopilot_bundle(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        source_search_records=[record],
        current_date="2026-07-15",
    )

    report = bundle["source_autopilot_report"]
    assert report["strong_candidate"] is False
    assert report["runtime_contract_candidate_count"] == 0
    assert report["card_specific_runtime_contract_candidate_count"] == 0
    assert report["strong_closure_summary"]["source_backed_strong_ready"] is False
    assert report["strong_closure_summary"]["semantic_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["strong_closure_summary"]["first_missing_source_action"] == "add_explicit_mulligan_source"
    assert report["first_missing_source_action"] == report["strong_closure_summary"]["first_missing_source_action"]


def test_extract_source_evidence_rows_infers_visibility_for_legacy_and_thin_records():
    deck_identity = {
        "deck_name": "ThinDeck",
        "deck_code_hash": "sha256:thin",
        "deck_slug": "thindeck",
        "cards": [{"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}],
    }
    record = {
        "source_url": "https://example.com/thin-guide",
        "source_title": "ThinDeck Guide 2026",
        "source_family": "guide",
        "publication_year": 2026,
        "normalized_text": (
            "ThinDeck Guide 2026 explains the current mulligan plan, card roles, "
            "targeting priorities, matchup pressure, sequencing, resource use, "
            "runtime-relevant play patterns, source-backed card expectations, "
            "opening hand decisions, and direct runtime contract guidance for "
            "this exact deck across common ladder matchups."
        ),
        "deck_match": {
            "deck_name": "ThinDeck",
            "archetype": "thindeck",
            "matched_card_ids": ["CARD_001"],
        },
        "deck_match_scope": "deck_or_archetype_matched",
        "claims": [
            {
                "claim_kind": "mulligan_keep",
                "cards": ["CARD_001"],
                "source_confidence": "high",
            }
        ],
    }

    rows = extract_source_evidence_rows(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        ranked_sources=rank_public_sources(
            deck_name="ThinDeck",
            deck_identity=deck_identity,
            source_search_records=[record],
            current_date="2026-07-15",
        ),
        current_date="2026-07-15",
    )

    assert rows[0]["source_visibility"] == "full_text"

    thin_record = dict(record)
    thin_record.pop("claims")
    rows = extract_source_evidence_rows(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        ranked_sources=rank_public_sources(
            deck_name="ThinDeck",
            deck_identity=deck_identity,
            source_search_records=[thin_record],
            current_date="2026-07-15",
        ),
        current_date="2026-07-15",
    )

    assert rows == []


def test_rank_public_sources_uses_publication_year_field():
    deck_identity = {
        "deck_name": "ThinDeck",
        "deck_code_hash": "sha256:thin",
        "deck_slug": "thindeck",
        "cards": [{"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}],
    }

    ranked = rank_public_sources(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        source_search_records=[
            {
                "source_url": "https://example.com/thin-guide",
                "source_title": "ThinDeck Guide 2026",
                "source_family": "guide",
                "publication_year": 2026,
                "normalized_text": "ThinDeck guide with a current mulligan plan.",
                "deck_match": {
                    "deck_name": "ThinDeck",
                    "archetype": "thindeck",
                    "matched_card_ids": ["CARD_001"],
                },
            }
        ],
        current_date="2026-07-15",
    )

    assert ranked[0]["source_rank_lane"] == "guide_current_deck_match"


def test_source_autopilot_does_not_call_snippet_structured_claims_strong():
    deck_identity = {
        "deck_name": "ThinDeck",
        "deck_code_hash": "sha256:thin",
        "deck_slug": "thindeck",
        "cards": [{"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}],
    }

    bundle = build_source_autopilot_bundle(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        source_search_records=[
            {
                "source_url": "https://example.com/thin-snippet",
                "source_title": "ThinDeck Guide 2026",
                "source_family": "guide",
                "source_visibility": "snippet_only",
                "publication_year": 2026,
                "normalized_text": "ThinDeck guide.",
                "deck_match": {
                    "deck_name": "ThinDeck",
                    "archetype": "thindeck",
                    "matched_card_ids": ["CARD_001"],
                },
                "deck_match_scope": "deck_or_archetype_matched",
                "claims": [
                    {
                        "claim_kind": "targeting_rule",
                        "cards": ["CARD_001"],
                        "stance": "prefer_enemy_hero",
                        "source_confidence": "high",
                    }
                ],
            }
        ],
        current_date="2026-07-15",
    )

    assert bundle["source_autopilot_report"]["runtime_contract_candidate_count"] == 1
    assert bundle["source_autopilot_report"]["strong_candidate"] is False


def test_source_autopilot_infers_legacy_short_text_claims_as_snippet_only():
    deck_identity = {
        "deck_name": "ThinDeck",
        "deck_code_hash": "sha256:thin",
        "deck_slug": "thindeck",
        "cards": [{"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}],
    }

    bundle = build_source_autopilot_bundle(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        source_search_records=[
            {
                "source_url": "https://example.com/thin-legacy-snippet",
                "source_title": "ThinDeck Guide 2026",
                "source_family": "guide",
                "publication_year": 2026,
                "normalized_text": "ThinDeck guide.",
                "deck_match": {
                    "deck_name": "ThinDeck",
                    "archetype": "thindeck",
                    "matched_card_ids": ["CARD_001"],
                },
                "deck_match_scope": "deck_or_archetype_matched",
                "claims": [
                    {
                        "claim_kind": "targeting_rule",
                        "cards": ["CARD_001"],
                        "stance": "prefer_enemy_hero",
                        "source_confidence": "high",
                    }
                ],
            }
        ],
        current_date="2026-07-15",
    )

    rows = bundle["source_evidence_rows"]
    assert rows[0]["source_visibility"] == "snippet_only"
    assert bundle["source_autopilot_report"]["runtime_contract_candidate_count"] == 1
    assert bundle["source_autopilot_report"]["strong_candidate"] is False


def test_source_autopilot_does_not_call_stale_structured_guide_claims_strong():
    deck_identity = {
        "deck_name": "ThinDeck",
        "deck_code_hash": "sha256:thin",
        "deck_slug": "thindeck",
        "cards": [{"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}],
    }

    bundle = build_source_autopilot_bundle(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        source_search_records=[
            {
                "source_url": "https://example.com/thin-guide",
                "source_title": "ThinDeck Guide 2025",
                "source_family": "guide",
                "source_visibility": "full_text",
                "publication_year": 2025,
                "normalized_text": "ThinDeck current style guide with target priorities.",
                "deck_match": {
                    "deck_name": "ThinDeck",
                    "archetype": "thindeck",
                    "matched_card_ids": ["CARD_001"],
                },
                "deck_match_scope": "deck_or_archetype_matched",
                "claims": [
                    {
                        "claim_kind": "targeting_rule",
                        "cards": ["CARD_001"],
                        "stance": "prefer_enemy_hero",
                        "source_confidence": "high",
                    }
                ],
            }
        ],
        current_date="2026-07-15",
    )

    assert bundle["ranked_sources"][0]["source_rank_lane"] == "guide_card_overlap"
    assert bundle["source_autopilot_report"]["runtime_contract_candidate_count"] == 1
    assert bundle["source_autopilot_report"]["strong_candidate"] is False


def test_source_autopilot_never_blocks_config_creation_for_thin_or_empty_sources():
    thin_payload = _fixture("source_search_decklist_only.json")
    deck_identity = {
        "deck_name": "ThinDeck",
        "deck_code_hash": "sha256:thin",
        "deck_slug": "thindeck",
        "cards": [{"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}],
    }

    thin_bundle = build_source_autopilot_bundle(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        source_search_records=thin_payload["records"],
        current_date="2026-07-15",
    )
    empty_bundle = build_source_autopilot_bundle(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        source_search_records=[],
        current_date="2026-07-15",
    )

    assert thin_bundle["source_autopilot_report"]["status"] == "OK"
    assert empty_bundle["source_autopilot_report"]["status"] == "OK"
    assert thin_bundle["source_autopilot_report"]["strong_candidate"] is False
    assert (
        empty_bundle["source_autopilot_report"]["first_missing_source_action"]
        == "add_explicit_mulligan_source"
    )


def test_source_autopilot_reports_strong_blockers_per_card():
    payload = _fixture("source_search_decklist_only.json")
    deck_identity = {
        "deck_name": "ThinDeck",
        "deck_code_hash": "sha256:thin",
        "deck_slug": "thindeck",
        "cards": [{"card_id": "CARD_001", "name": "Fixture Card", "cost": 1, "count": 2}],
    }

    bundle = build_source_autopilot_bundle(
        deck_name="ThinDeck",
        deck_identity=deck_identity,
        source_search_records=payload["records"],
        current_date="2026-07-15",
    )

    report = bundle["source_autopilot_report"]
    assert report["strong_candidate"] is False
    assert "no_card_specific_runtime_contract_candidate" in report["strong_candidate_blockers"]
    assert (
        report["first_missing_source_action_by_card"]["CARD_001"]
        == "add_current_deck_guide_or_mulligan_guide"
    )
    assert report["non_promoting_claim_count"] >= 1
