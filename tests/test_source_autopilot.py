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


def test_extract_source_evidence_rows_preserves_darkbishop_effect_not_mulligan_keep():
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
    assert any(
        row["claim_kind"] == "mulligan_discard" and row.get("cards") == ["SW_448"]
        for row in darkbishop_rows
    )


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
    assert report["first_missing_source_action"] == "add_current_deck_guide_or_mulligan_guide"


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
        == "add_current_deck_guide_or_mulligan_guide"
    )
