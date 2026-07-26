from __future__ import annotations

import json
from pathlib import Path

import pytest

from hsconfig.deck_identity import build_deck_identity, stable_deck_fingerprint
from hsconfig.deckstring_decode import decode_deck_code
from hsconfig.source_document_builder import build_source_document_bundle
from hsconfig.source_autopilot import (
    _action_from_profile_gap,
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
SHADOW_DECK_IDENTITY["deck_fingerprint"] = stable_deck_fingerprint(
    (card["card_id"], card["count"]) for card in SHADOW_DECK_IDENTITY["cards"]
)

INVALID_EXACT_COUNT_VALUES = [
    pytest.param("not-an-int", id="nonnumeric-string"),
    pytest.param(True, id="boolean"),
    pytest.param(-1, id="negative"),
    pytest.param([], id="list"),
    pytest.param({}, id="dictionary"),
    pytest.param(1.5, id="float"),
    pytest.param("9" * 5000, id="oversized-decimal-string"),
]


def _shadowpriest_identity() -> dict:
    return SHADOW_DECK_IDENTITY


def _strong_ranked_source(*, normalized_text: str) -> dict:
    return {
        "source_url": "https://example.test/shadow-priest",
        "source_title": "Shadow Priest Guide",
        "source_family": "guide",
        "source_visibility": "full_text",
        "source_record_strength": "candidate_strong",
        "source_rank_lane": "guide_current_deck_match",
        "source_lane": "deck_matched_public_guide",
        "deck_match_scope": "exact_deck_matched",
        "publication_year": 2026,
        "deck_match": {
            "deck_name": "ShadowPriest",
            "archetype": "shadowpriest",
            "matched_card_ids": ["SW_446", "TOY_381"],
            "exact_deck_evidence": {
                "candidate_count": 1,
                "decoded_candidate_count": 1,
                "matched": True,
                "matched_deck_fingerprint": SHADOW_DECK_IDENTITY["deck_fingerprint"],
                "candidate_deck_code_hashes": ["sha256:shadow-source-code"],
            },
        },
        "normalized_text": normalized_text,
    }


def test_autopilot_does_not_turn_keep_alive_into_mulligan_keep():
    ranked = [
        _strong_ranked_source(
            normalized_text=(
                "Strategy: Keep Voidtouched Attendant alive on the board "
                "so its aura continues."
            )
        )
    ]

    rows = extract_source_evidence_rows(
        deck_name="ShadowPriest",
        deck_identity=_shadowpriest_identity(),
        ranked_sources=ranked,
        current_date="2026-07-25",
    )

    assert [row for row in rows if row["claim_kind"] == "mulligan_keep"] == []


def test_autopilot_does_not_carry_mulligan_context_to_later_keep_sentence():
    ranked = [
        _strong_ranked_source(
            normalized_text=(
                "Mulligan: Keep Papercraft Angel. "
                "Keep Voidtouched Attendant alive on the board."
            )
        )
    ]

    rows = extract_source_evidence_rows(
        deck_name="ShadowPriest",
        deck_identity=_shadowpriest_identity(),
        ranked_sources=ranked,
        current_date="2026-07-26",
    )

    assert [
        row["cards"]
        for row in rows
        if row["claim_kind"] == "mulligan_keep"
    ] == [["TOY_381"]]


def test_rank_public_sources_overrides_claimed_exact_scope_without_overlap():
    ranked = rank_public_sources(
        deck_name="ShadowPriest",
        deck_identity=SHADOW_DECK_IDENTITY,
        source_search_records=[
            {
                "source_url": "https://example.test/shadow-priest",
                "source_title": "Shadow Priest Guide 2026",
                "source_family": "guide",
                "source_visibility": "full_text",
                "source_record_strength": "candidate_strong",
                "publication_year": 2026,
                "deck_match_scope": "deck_matched",
                "deck_match": {
                    "deck_name": "ShadowPriest",
                    "matched_card_ids": ["SW_446"],
                    "matched_card_count": 6,
                    "unique_deck_card_count": 6,
                    "card_overlap_ratio": 1.0,
                },
                "normalized_text": "Shadow Priest Guide 2026.",
            }
        ],
        current_date="2026-07-26",
    )

    assert ranked[0]["deck_match_scope"] == "archetype_matched"
    assert ranked[0]["source_rank_lane"] == "guide_current_archetype_match"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _matrix_deck_identity(deck_name: str) -> dict:
    matrix = json.loads(
        Path("docs/operator/archetype-fixture-matrix.json").read_text(encoding="utf-8")
    )
    deck = next(row for row in matrix["decks"] if row["deck_name"] == deck_name)
    decoded = decode_deck_code(deck["deck_code"])
    return build_deck_identity(
        deck_name=deck["deck_name"],
        deck_code=deck["deck_code"],
        cards=decoded["cards"],
        hero_dbf_id=decoded["hero_dbf_id"],
        format=decoded["format"],
        sideboards=decoded["sideboards"],
    )


def run_source_autopilot_fixture(name: str) -> dict:
    payload = _fixture(name)
    bundle = build_source_autopilot_bundle(
        deck_name=payload["deck_name"],
        deck_identity=SHADOW_DECK_IDENTITY,
        source_search_records=payload["records"],
        current_date="2026-07-15",
    )
    return bundle["source_autopilot_report"]


def _current_guide_record(claims: list[dict], *, archetype: str = "aggro_fixture") -> dict:
    return {
        "source_url": "https://example.com/profile-guide",
        "source_title": "Profile Fixture Guide 2026",
        "source_family": "guide",
        "source_visibility": "full_text",
        "publication_year": 2026,
        "normalized_text": (
            "Profile Fixture Guide 2026 explains current mulligan decisions, "
            "gameplan posture, target priorities, combo sequence planning, "
            "runtime surfaces, card behavior, and source-backed play patterns "
            "for this exact ladder deck across common matchups."
        ),
        "deck_match": {
            "deck_name": "ProfileDeck",
            "archetype": archetype,
            "matched_card_ids": ["CARD_001", "CARD_002"],
        },
        "deck_match_scope": "deck_or_archetype_matched",
        "claims": claims,
    }


def _profile_report(claims: list[dict], *, archetype: str = "aggro_fixture") -> dict:
    deck_identity = {
        "deck_name": "ProfileDeck",
        "deck_code_hash": "sha256:profile",
        "deck_slug": "profiledeck",
        "cards": [
            {"card_id": "CARD_001", "name": "Fixture One", "cost": 1, "count": 2},
            {"card_id": "CARD_002", "name": "Fixture Two", "cost": 2, "count": 2},
        ],
    }
    deck_identity["deck_fingerprint"] = stable_deck_fingerprint(
        (card["card_id"], card["count"]) for card in deck_identity["cards"]
    )
    source = _current_guide_record(claims, archetype=archetype)
    source["deck_match_scope"] = "exact_deck_matched"
    source["deck_match"]["exact_deck_evidence"] = {
        "candidate_count": 1,
        "decoded_candidate_count": 1,
        "matched": True,
        "matched_deck_fingerprint": deck_identity["deck_fingerprint"],
        "candidate_deck_code_hashes": ["sha256:profile-source-code"],
    }
    bundle = build_source_autopilot_bundle(
        deck_name="ProfileDeck",
        deck_identity=deck_identity,
        source_search_records=[source],
        current_date="2026-07-15",
    )
    return bundle["source_autopilot_report"]


def _strict_count_autopilot_fixture(
    *,
    count_field: str,
    count_value,
) -> tuple[dict, dict]:
    deck_identity = {
        "deck_name": "StrictCountDeck",
        "deck_slug": "strictcountdeck",
        "cards": [
            {
                "card_id": "CARD_001",
                "name": "Fixture One",
                "cost": 1,
                "count": 2,
            }
        ],
    }
    deck_identity["deck_fingerprint"] = stable_deck_fingerprint(
        (card["card_id"], card["count"]) for card in deck_identity["cards"]
    )
    exact = {
        "candidate_count": 1,
        "decoded_candidate_count": 1,
        "matched": True,
        "matched_deck_fingerprint": deck_identity["deck_fingerprint"],
        "candidate_deck_code_hashes": ["sha256:strict-count-source-code"],
    }
    exact[count_field] = count_value
    record = {
        "source_url": "https://example.test/strict-count-guide",
        "source_title": "StrictCountDeck Guide 2026",
        "source_family": "guide",
        "source_type": "public_guide",
        "source_visibility": "full_text",
        "publication_year": 2026,
        "source_record_strength": "candidate_strong",
        "source_lane": "deck_matched_public_guide",
        "source_rank_lane": "guide_current_deck_match",
        "deck_match_scope": "exact_deck_matched",
        "deck_match": {
            "deck_name": "StrictCountDeck",
            "archetype": "strictcountdeck",
            "matched_card_ids": ["CARD_001"],
            "exact_deck_evidence": exact,
        },
        "mulligan": {
            "keep_card_ids": ["CARD_001"],
            "evidence_text_short": "Keep Fixture One.",
        },
        "normalized_text": (
            "StrictCountDeck Guide 2026. Mulligan: keep Fixture One. "
            "Use Fixture One as the opening pressure card."
        ),
    }
    return deck_identity, record


@pytest.mark.parametrize(
    "count_field",
    ["candidate_count", "decoded_candidate_count"],
)
@pytest.mark.parametrize("invalid_value", INVALID_EXACT_COUNT_VALUES)
def test_autopilot_invalid_exact_counts_fail_closed_without_exception(
    count_field,
    invalid_value,
):
    deck_identity, record = _strict_count_autopilot_fixture(
        count_field=count_field,
        count_value=invalid_value,
    )

    try:
        autopilot = build_source_autopilot_bundle(
            deck_name="StrictCountDeck",
            deck_identity=deck_identity,
            source_search_records=[record],
            current_date="2026-07-26",
        )
    except (TypeError, ValueError) as exc:
        pytest.fail(f"invalid exact evidence must fail closed, not raise: {exc}")

    ranked = autopilot["ranked_sources"][0]
    document = autopilot["source_documents_payload"]["source_documents"][0]
    source_bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=[document],
        current_date="2026-07-26",
    )

    assert ranked["deck_match_scope"] == "archetype_matched"
    assert document["deck_match_scope"] == "archetype_matched"
    assert document["source_lane"] == "archetype_matched_public_guide"
    assert document["first_missing_source_action"] == (
        "add_exact_deck_matched_source"
    )
    assert "deck_match" not in document
    assert source_bundle["globalvalues_source_receipts"] == []


@pytest.mark.parametrize(
    "accepted_value",
    [pytest.param(1, id="integer"), pytest.param("1", id="decimal-string")],
)
def test_autopilot_accepts_strict_positive_integer_count_forms(accepted_value):
    deck_identity, record = _strict_count_autopilot_fixture(
        count_field="candidate_count",
        count_value=accepted_value,
    )

    autopilot = build_source_autopilot_bundle(
        deck_name="StrictCountDeck",
        deck_identity=deck_identity,
        source_search_records=[record],
        current_date="2026-07-26",
    )
    document = autopilot["source_documents_payload"]["source_documents"][0]
    source_bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=[document],
        current_date="2026-07-26",
    )

    assert document["deck_match_scope"] == "exact_deck_matched"
    assert source_bundle["globalvalues_source_receipts"]
    assert {
        receipt["claim_id"]
        for receipt in source_bundle["globalvalues_source_receipts"]
    } == {
        claim["claim_id"] for claim in source_bundle["claims"]
    }


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
    assert ranked[0]["source_rank_lane"] == "guide_current_archetype_match"
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
    assert any(row["claim_kind"] == "mulligan_discard" for row in darkbishop_rows)


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

    report = bundle["source_autopilot_report"]
    assert report["status"] == "OK"
    assert report["source_rank_summary"]["guide_current_archetype_match"] == 1
    assert report["claim_kind_counts"]["mulligan_keep"] == 4
    summary = report["strong_closure_summary"]
    assert summary["technical_no_block"] is True
    assert summary["source_backed_strong_ready"] is False
    assert summary["semantic_status"] == "SOURCE_BACKED_PARTIAL"
    assert summary["first_missing_source_action"] == "add_current_card_specific_runtime_source"
    preview = report["source_readiness_preview"]

    assert preview["authority"] == "diagnostic_source_readiness_preview"
    assert preview["diagnostic_only"] is True
    assert preview["runtime_apply_authority"] == "reports/operator_summary.json"
    assert preview["apply_blocking"] is False
    assert preview["runtime_write_performed"] is False
    assert preview["source_status_apply_blocking"] is False
    assert preview["source_autopilot_report_present"] is True
    assert preview["operator_summary_present"] is False
    assert preview["semantic_status"] == report["semantic_status"]
    assert preview["default_only_evaluated"] is False
    assert preview["default_only_clean"] is False
    assert preview["default_only_runtime_surface_status"] == (
        "not_evaluated_in_source_preflight"
    )
    assert preview["source_backed_strong_ready"] is False
    assert preview["readiness_lane"] == "source_partial_no_block"
    assert preview["first_missing_source_action"] == report[
        "first_missing_source_action"
    ]
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
    assert (
        report["strong_closure_summary"]["first_missing_source_action"]
        == "add_current_card_specific_runtime_source"
    )
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
    assert (
        report["strong_closure_summary"]["first_missing_source_action"]
        == "add_current_card_specific_runtime_source"
    )
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

    assert ranked[0]["source_rank_lane"] == "guide_current_archetype_match"


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
        == "add_current_card_specific_runtime_source"
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
        == "add_current_card_specific_runtime_source"
    )
    assert report["non_promoting_claim_count"] >= 1


def test_partial_deck_reports_specific_missing_card_and_surface_actions():
    deck_identity = {
        "cards": [
            {"card_id": "DEEP_014", "name": "Quick Pick", "cost": 2, "text": "Draw a card."},
            {"card_id": "CARD_002", "name": "Kingsbane", "cost": 1, "text": ""},
        ]
    }
    records = [
        {
            "source_url": "https://example.test/kingslayer",
            "source_title": "2026 Wild Kingsbane Rogue Guide",
            "source_family": "community_guide",
            "source_visibility": "full_text",
            "publication_year": 2026,
            "source_record_strength": "candidate_partial",
            "deck_match": {
                "deck_name": "Kingslayer",
                "matched_card_ids": ["CARD_002"],
            },
            "normalized_text": "Kingsbane Rogue buffs weapon and attacks face. The guide does not mention Quick Pick mulligan.",
        }
    ]

    bundle = build_source_autopilot_bundle(
        deck_name="Kingslayer",
        deck_identity=deck_identity,
        source_search_records=records,
        current_date="2026-07-16",
    )

    report = bundle["source_autopilot_report"]

    assert report["semantic_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["source_backed_strong_closure"]["closed"] is False
    assert report["first_missing_source_action"] != "none"
    assert report["first_missing_source_action_by_card"]["DEEP_014"] == (
        "add_kingslayer_quick_pick_mulligan_source"
    )
    assert "Mulligan.json" in report["first_missing_source_action_by_surface"]


def test_profile_card_missing_actions_cover_known_deck_specific_cards():
    cases = [
        (
            "Kingslayer",
            "DEEP_014",
            "Quick Pick",
            "add_kingslayer_quick_pick_mulligan_source",
        ),
        (
            "Boarlock",
            "WW_092",
            "Fracking",
            "add_boarlock_fracking_mulligan_source",
        ),
    ]

    for deck_name, card_id, card_name, expected_action in cases:
        bundle = build_source_autopilot_bundle(
            deck_name=deck_name,
            deck_identity={
                "cards": [
                    {
                        "card_id": card_id,
                        "name": card_name,
                        "cost": 2,
                        "text": "Fixture card needing exact source closure.",
                    },
                    {
                        "card_id": "CARD_002",
                        "name": f"{deck_name} Core Card",
                        "cost": 1,
                        "text": "",
                    },
                ]
            },
            source_search_records=[
                {
                    "source_url": f"https://example.test/{deck_name.lower()}",
                    "source_title": f"2026 Wild {deck_name} Guide",
                    "source_family": "community_guide",
                    "source_visibility": "full_text",
                    "publication_year": 2026,
                    "source_record_strength": "candidate_partial",
                    "deck_match": {
                        "deck_name": deck_name,
                        "matched_card_ids": ["CARD_002"],
                    },
                    "normalized_text": (
                        f"{deck_name} guide covers the core gameplan but not the target card."
                    ),
                }
            ],
            current_date="2026-07-16",
        )

        report = bundle["source_autopilot_report"]

        assert report["semantic_status"] == "SOURCE_BACKED_PARTIAL"
        assert report["first_missing_source_action_by_card"][card_id] == expected_action


def test_partial_claim_kind_action_wins_before_profile_card_fallback():
    cases = [
        ("Kingslayer", "DEEP_014", "Quick Pick"),
        ("Boarlock", "WW_092", "Fracking"),
    ]

    for deck_name, card_id, card_name in cases:
        bundle = build_source_autopilot_bundle(
            deck_name=deck_name,
            deck_identity={
                "cards": [
                    {
                        "card_id": card_id,
                        "name": card_name,
                        "cost": 2,
                        "text": "Fixture card with a partial targeting claim.",
                    }
                ]
            },
            source_search_records=[
                {
                    "source_url": f"https://example.test/{deck_name.lower()}-partial",
                    "source_title": f"2026 Wild {deck_name} Partial Guide",
                    "source_family": "community_guide",
                    "source_visibility": "full_text",
                    "publication_year": 2026,
                    "source_record_strength": "candidate_partial",
                    "deck_match": {
                        "deck_name": deck_name,
                        "matched_card_ids": [card_id],
                    },
                    "claims": [
                        {
                            "claim_kind": "targeting_rule",
                            "cards": [card_id],
                            "evidence_text_short": "Target the opponent unless trading is lethal-safe.",
                        }
                    ],
                }
            ],
            current_date="2026-07-16",
        )

        report = bundle["source_autopilot_report"]

        assert report["semantic_status"] == "SOURCE_BACKED_PARTIAL"
        assert report["first_missing_source_action_by_card"][card_id] == (
            "add_card_specific_targeting_source"
        )


def test_source_autopilot_report_contains_strong_closure_summary_and_surfaces():
    bundle = build_source_autopilot_bundle(
        deck_name="FixtureDeck",
        deck_identity={
            "cards": [
                {
                    "card_id": "CARD_001",
                    "name": "Fixture Card",
                    "cost": 1,
                    "count": 2,
                }
            ]
        },
        source_search_records=[],
        current_date="2026-07-15",
    )

    report = bundle["source_autopilot_report"]
    summary = report["strong_closure_summary"]
    assert summary["technical_no_block"] is True
    assert summary["source_backed_strong_ready"] is False
    assert summary["first_missing_source_action"] != "none"
    assert report["first_missing_source_action_by_surface"]["Mulligan.json"] == (
        "add_exact_mulligan_keep_or_discard_source"
    )


def test_source_autopilot_does_not_require_extra_non_mulligan_surface_when_profile_closed():
    report = run_source_autopilot_fixture("source_search_shadowpriest_2026.json")

    assert report["semantic_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["first_missing_source_action"] == "add_current_card_specific_runtime_source"
    assert report["source_backed_strong_closure"]["closure_profile"] == "aggro_burn_hero_power"
    assert report["source_backed_strong_closure"]["closure_profile_closed"] is False


def test_source_autopilot_routes_missing_mulligan_group_through_profile_gap():
    report = _profile_report(
        [
            {"claim_kind": "gameplan_posture", "scope": "deck", "stance": "aggressive"},
            {
                "claim_kind": "targeting_rule",
                "cards": ["CARD_001"],
                "stance": "prefer_enemy_hero",
            },
        ],
        archetype="aggro_burn_fixture",
    )

    assert report["first_missing_source_action"] == (
        "add_current_mulligan_keep_or_discard_source"
    )


def test_source_autopilot_routes_missing_targeting_group_through_profile_gap():
    report = _profile_report(
        [
            {"claim_kind": "gameplan_posture", "scope": "deck", "stance": "aggressive"},
            {"claim_kind": "mulligan_keep", "cards": ["CARD_001"], "stance": "keep"},
        ],
        archetype="aggro_burn_fixture",
    )

    assert report["first_missing_source_action"] == (
        "add_current_targeting_or_card_behavior_source"
    )


def test_source_autopilot_routes_missing_combo_sequence_through_profile_gap():
    report = _profile_report(
        [
            {"claim_kind": "gameplan_posture", "scope": "deck", "stance": "setup"},
            {"claim_kind": "mulligan_keep", "cards": ["CARD_001"], "stance": "keep"},
        ],
        archetype="combo_setup_fixture",
    )

    assert report["first_missing_source_action"] == "add_current_combo_sequence_source"


def test_source_autopilot_routes_missing_surface_gap_mapping():
    assert (
        _action_from_profile_gap("missing_surface:GlobalValues.json")
        == "emit_or_explain_missing_runtime_surface"
    )


def test_source_autopilot_no_strong_rows_uses_profile_gap_not_mulligan_fallback():
    bundle = build_source_autopilot_bundle(
        deck_name="FixtureDeck",
        deck_identity={
            "cards": [
                {
                    "card_id": "CARD_001",
                    "name": "Fixture Card",
                    "cost": 1,
                    "count": 2,
                }
            ]
        },
        source_search_records=[],
        current_date="2026-07-15",
    )

    assert bundle["source_autopilot_report"]["first_missing_source_action"] == (
        "add_current_card_specific_runtime_source"
    )


def test_source_autopilot_marks_runtime_default_only_surfaces_not_evaluated():
    report = run_source_autopilot_fixture("source_search_shadowpriest_2026.json")
    closure = report["source_backed_strong_closure"]

    assert "default_only_runtime_surfaces" not in closure
    assert (
        closure["default_only_runtime_surface_status"]
        == "not_evaluated_in_source_preflight"
    )
    assert closure["default_only_runtime_surfaces_scope"] == (
        "source_preflight_not_runtime_proof"
    )


def test_source_autopilot_names_targeting_missing_action():
    deck_identity = {
        "deck_name": "TargetDeck",
        "cards": [
            {"card_id": "CARD_001", "name": "Face Spell", "cost": 1, "count": 2},
        ],
    }
    bundle = build_source_autopilot_bundle(
        deck_name="TargetDeck",
        deck_identity=deck_identity,
        source_search_records=[
            {
                "source_url": "https://example.com/target-deck",
                "source_title": "Target Deck Current Guide",
                "source_family": "guide",
                "source_visibility": "snippet_only",
                "publication_year": 2026,
                "deck_match": {
                    "deck_name": "TargetDeck",
                    "matched_card_ids": ["CARD_001"],
                },
                "claims": [
                    {
                        "claim_kind": "targeting_rule",
                        "cards": ["CARD_001"],
                        "stance": "prefer_enemy_hero",
                    }
                ],
            }
        ],
        current_date="2026-07-16",
    )

    report = bundle["source_autopilot_report"]

    assert report["semantic_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["first_missing_source_action_by_card"]["CARD_001"] == (
        "add_card_specific_targeting_source"
    )
    assert report["first_missing_source_action_by_surface"]["CardID.json"] == (
        "add_card_specific_targeting_source"
    )


def test_source_autopilot_names_combo_sequence_missing_action():
    deck_identity = {
        "deck_name": "ComboDeck",
        "cards": [
            {"card_id": "CARD_001", "name": "Combo Piece", "cost": 1, "count": 2},
        ],
    }
    bundle = build_source_autopilot_bundle(
        deck_name="ComboDeck",
        deck_identity=deck_identity,
        source_search_records=[
            {
                "source_url": "https://example.com/combo-deck",
                "source_title": "Combo Deck Current Guide",
                "source_family": "guide",
                "source_visibility": "full_text",
                "publication_year": 2026,
                "deck_match": {
                    "deck_name": "ComboDeck",
                    "matched_card_ids": ["CARD_001"],
                },
                "deck_match_scope": "deck_or_archetype_matched",
                "normalized_text": "Combo Deck Current Guide. " * 20,
                "claims": [
                    {
                        "claim_kind": "combo_sequence",
                        "cards": ["CARD_001"],
                        "stance": "assemble_combo",
                    }
                ],
            }
        ],
        current_date="2026-07-16",
    )

    report = bundle["source_autopilot_report"]

    assert report["semantic_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["first_missing_source_action_by_card"]["CARD_001"] == (
        "add_combo_sequence_source"
    )
    assert report["first_missing_source_action_by_surface"]["Combo.json"] == (
        "add_combo_sequence_source"
    )


def test_rank_public_sources_accepts_evergreen_wild_archetype_as_strong_lane():
    deck_identity = {
        "deck_name": "ShadowPriest",
        "deck_code_hash": "sha256:shadow",
        "deck_slug": "shadowpriest",
        "cards": [
            {"card_id": "SW_448", "name": "Darkbishop Benedictus", "cost": 5, "count": 1},
            {"card_id": "SW_446", "name": "Voidtouched Attendant", "cost": 1, "count": 2},
            {"card_id": "GVG_009", "name": "Shadowbomber", "cost": 1, "count": 2},
        ],
    }
    deck_identity["deck_fingerprint"] = stable_deck_fingerprint(
        (card["card_id"], card["count"]) for card in deck_identity["cards"]
    )

    ranked = rank_public_sources(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        source_search_records=[
            {
                "source_url": "https://example.com/wild-shadowpriest",
                "source_title": "Wild ShadowPriest Guide",
                "source_family": "guide",
                "source_visibility": "full_text",
                "publication_year": 2021,
                "format_scope": "wild",
                "evergreen_wild_archetype": True,
                "source_record_strength": "candidate_strong",
                "normalized_text": (
                    "Wild ShadowPriest full guide text with mulligan and gameplan. " * 8
                ),
                "deck_match": {
                    "deck_name": "ShadowPriest",
                    "matched_card_ids": ["SW_448", "SW_446", "GVG_009"],
                    "exact_deck_evidence": {
                        "candidate_count": 1,
                        "decoded_candidate_count": 1,
                        "matched": True,
                        "matched_deck_fingerprint": deck_identity["deck_fingerprint"],
                        "candidate_deck_code_hashes": [
                            "sha256:evergreen-shadow-source"
                        ],
                    },
                },
                "deck_match_scope": "exact_deck_matched",
                "claims": [
                    {
                        "claim_kind": "gameplan_posture",
                        "stance": "aggressive_burn",
                        "source_confidence": "high",
                    },
                    {
                        "claim_kind": "mulligan_keep",
                        "cards": ["SW_446"],
                        "stance": "keep",
                        "source_confidence": "high",
                    },
                    {
                        "claim_kind": "hero_power_transform",
                        "cards": ["SW_448"],
                        "stance": "mind_spike_start_effect",
                        "source_confidence": "high",
                    },
                ],
            }
        ],
        current_date="2026-07-16",
    )

    assert ranked[0]["source_freshness_lane"] == "evergreen_wild_archetype"
    assert ranked[0]["source_rank_lane"] == "guide_evergreen_wild_archetype"
    assert ranked[0]["source_lane"] == "deck_matched_public_guide"
    assert ranked[0]["strong_promotion_eligible"] is False


def test_source_autopilot_evergreen_wild_guide_can_close_strong_summary():
    deck_identity = {
        "deck_name": "ShadowPriest",
        "deck_code_hash": "sha256:shadow",
        "deck_slug": "shadowpriest",
        "archetype_bucket": "aggro_burn_hero_power",
        "primary_mechanics": ["shadow_hero_power", "burn"],
        "cards": [
            {"card_id": "SW_448", "name": "Darkbishop Benedictus", "cost": 5, "count": 1},
            {"card_id": "SW_446", "name": "Voidtouched Attendant", "cost": 1, "count": 2},
            {"card_id": "GVG_009", "name": "Shadowbomber", "cost": 1, "count": 2},
        ],
    }
    deck_identity["deck_fingerprint"] = stable_deck_fingerprint(
        (card["card_id"], card["count"]) for card in deck_identity["cards"]
    )

    bundle = build_source_autopilot_bundle(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        source_search_records=[
            {
                "source_url": "https://example.com/wild-shadowpriest",
                "source_title": "Wild ShadowPriest Guide",
                "source_family": "guide",
                "source_visibility": "full_text",
                "publication_year": 2021,
                "format_scope": "wild",
                "evergreen_wild_archetype": True,
                "source_record_strength": "candidate_strong",
                "normalized_text": (
                    "Wild ShadowPriest full guide text with mulligan and gameplan. " * 8
                ),
                "deck_match": {
                    "deck_name": "ShadowPriest",
                    "matched_card_ids": ["SW_448", "SW_446", "GVG_009"],
                    "exact_deck_evidence": {
                        "candidate_count": 1,
                        "decoded_candidate_count": 1,
                        "matched": True,
                        "matched_deck_fingerprint": deck_identity["deck_fingerprint"],
                        "candidate_deck_code_hashes": [
                            "sha256:evergreen-shadow-source"
                        ],
                    },
                },
                "deck_match_scope": "exact_deck_matched",
                "claims": [
                    {
                        "claim_kind": "gameplan_posture",
                        "stance": "aggressive_burn",
                        "source_confidence": "high",
                    },
                    {
                        "claim_kind": "mulligan_keep",
                        "cards": ["SW_446"],
                        "stance": "keep",
                        "source_confidence": "high",
                    },
                    {
                        "claim_kind": "hero_power_transform",
                        "cards": ["SW_448"],
                        "stance": "mind_spike_start_effect",
                        "source_confidence": "high",
                    },
                ],
            }
        ],
        current_date="2026-07-16",
    )

    report = bundle["source_autopilot_report"]
    assert bundle["ranked_sources"][0]["source_rank_lane"] == "guide_evergreen_wild_archetype"
    assert report["source_rank_summary"]["guide_evergreen_wild_archetype"] == 1
    assert report["strong_candidate"] is False
    assert report["strong_closure_summary"]["source_backed_strong_ready"] is False
    assert report["strong_closure_summary"]["semantic_status"] == "SOURCE_BACKED_PARTIAL"


def test_source_autopilot_routes_imbuemage_source_search_to_hero_power_imbue():
    payload = _fixture("source_search_11_deck_matrix.json")
    bundle = build_source_autopilot_bundle(
        deck_name="ImbueMage",
        deck_identity=_matrix_deck_identity("ImbueMage"),
        source_search_records=payload["records_by_deck"]["ImbueMage"],
        current_date="2026-07-15",
    )

    report = bundle["source_autopilot_report"]
    closure = report["source_backed_strong_closure"]
    assert closure["closure_profile"] == "hero_power_imbue"
    assert closure["closure_profile_closed"] is False
    assert report["strong_candidate"] is False


def test_source_autopilot_old_non_wild_guide_requests_current_or_evergreen_source():
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
                "source_title": "ThinDeck Guide 2021",
                "source_family": "guide",
                "source_visibility": "full_text",
                "publication_year": 2021,
                "format_scope": "standard",
                "source_record_strength": "candidate_strong",
                "normalized_text": (
                    "ThinDeck old non-Wild guide with target priorities and play patterns. " * 8
                ),
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
        current_date="2026-07-16",
    )

    report = bundle["source_autopilot_report"]
    assert bundle["ranked_sources"][0]["source_freshness_lane"] == "stale_or_not_current"
    assert report["strong_candidate"] is False
    assert report["strong_closure_summary"]["semantic_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["strong_closure_summary"]["first_missing_source_action"] == (
        "add_current_or_evergreen_wild_public_guide"
    )
    assert report["first_missing_source_action"] == (
        "add_current_or_evergreen_wild_public_guide"
    )


def test_source_autopilot_stale_guide_without_claims_requests_current_or_evergreen_source():
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
                "source_title": "ThinDeck Guide 2021",
                "source_family": "guide",
                "source_visibility": "full_text",
                "publication_year": 2021,
                "format_scope": "standard",
                "source_record_strength": "candidate_strong",
                "normalized_text": (
                    "ThinDeck old non-Wild guide with target priorities and play patterns. " * 8
                ),
                "deck_match": {
                    "deck_name": "ThinDeck",
                    "archetype": "thindeck",
                    "matched_card_ids": ["CARD_001"],
                },
                "deck_match_scope": "deck_or_archetype_matched",
            }
        ],
        current_date="2026-07-16",
    )

    report = bundle["source_autopilot_report"]
    assert bundle["ranked_sources"][0]["source_freshness_lane"] == "stale_or_not_current"
    assert "source_not_current_or_evergreen_wild" in bundle["ranked_sources"][0]["promotion_blockers"]
    assert bundle["source_evidence_rows"] == []
    assert report["strong_closure_summary"]["semantic_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["strong_closure_summary"]["first_missing_source_action"] == (
        "add_current_or_evergreen_wild_public_guide"
    )
    assert report["first_missing_source_action"] == (
        "add_current_or_evergreen_wild_public_guide"
    )


def test_autopilot_extracts_full_text_claims_before_closure_evaluation():
    deck_identity = {
        "cards": [
            {
                "card_id": "SW_448",
                "name": "Darkbishop Benedictus",
                "cost": 5,
                "text": "Start of Game: If the spells in your deck are all Shadow, enter Shadowform.",
            },
            {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "text": ""},
        ]
    }
    deck_identity["deck_fingerprint"] = stable_deck_fingerprint(
        (card["card_id"], card.get("count", 1)) for card in deck_identity["cards"]
    )
    records = [
        {
            "source_url": "https://example.test/shadowpriest",
            "source_title": "2026 Wild ShadowPriest Guide",
            "source_family": "guide",
            "source_visibility": "full_text",
            "publication_year": 2026,
            "source_record_strength": "candidate_strong",
                "deck_match": {
                    "deck_name": "ShadowPriest",
                    "matched_card_ids": ["SW_448", "TOY_381"],
                    "exact_deck_evidence": {
                        "candidate_count": 1,
                        "decoded_candidate_count": 1,
                        "matched": True,
                        "matched_deck_fingerprint": deck_identity["deck_fingerprint"],
                        "candidate_deck_code_hashes": [
                            "sha256:full-text-shadow-source"
                        ],
                    },
                },
                "deck_match_scope": "exact_deck_matched",
            "normalized_text": (
                "Mulligan: keep Papercraft Angel. "
                "Do not keep any 4-cost or higher card. "
                "Darkbishop Benedictus turns your hero power into Mind Spike at the start of the game."
            ),
        }
    ]

    bundle = build_source_autopilot_bundle(
        deck_name="ShadowPriest",
        deck_identity=deck_identity,
        source_search_records=records,
        current_date="2026-07-16",
    )

    claims = bundle["source_evidence_rows"]
    claim_pairs = {
        (claim["claim_kind"], tuple(claim.get("cards", [])))
        for claim in claims
    }

    assert ("mulligan_keep", ("TOY_381",)) in claim_pairs
    assert ("mulligan_discard", ("SW_448",)) in claim_pairs
    assert ("hero_power_transform", ("SW_448",)) in claim_pairs
    assert ("mulligan_keep", ("SW_448",)) not in claim_pairs
    assert bundle["source_autopilot_report"]["default_only_runtime_surfaces"] == []


def test_rank_public_sources_exposes_current_or_evergreen_provenance() -> None:
    ranked = rank_public_sources(
        deck_name="ShadowPriest",
        deck_identity=SHADOW_DECK_IDENTITY,
        source_search_records=[
            {
                "source_url": "https://example.test/shadow-current",
                "source_title": "ShadowPriest Guide 2026",
                "source_family": "guide",
                "source_visibility": "full_text",
                "publication_year": 2026,
                "normalized_text": "x" * 220,
                "deck_match": {
                    "deck_name": "ShadowPriest",
                    "matched_card_ids": ["SW_448", "SW_446"],
                },
                "claims": [
                    {
                        "claim_kind": "mulligan_keep",
                        "cards": ["SW_446"],
                        "evidence_text_short": "Keep Voidtouched Attendant.",
                    }
                ],
            }
        ],
        current_date="2026-07-22",
    )

    assert ranked[0]["freshness_status"] == "current"
    assert ranked[0]["current_or_evergreen"] is True
    assert ranked[0]["current_or_evergreen_reason"] == "publication_year_matches_current_year"
    assert ranked[0]["deck_identity_match"] is True
    assert ranked[0]["source_status_apply_blocking"] is False


def test_source_evidence_rows_preserve_provenance_projection() -> None:
    ranked = rank_public_sources(
        deck_name="ShadowPriest",
        deck_identity=SHADOW_DECK_IDENTITY,
        source_search_records=[
            {
                "source_url": "https://example.test/shadow-current",
                "source_title": "ShadowPriest Guide 2026",
                "source_family": "guide",
                "source_visibility": "full_text",
                "publication_year": 2026,
                "normalized_text": "x" * 220,
                "deck_match": {
                    "deck_name": "ShadowPriest",
                    "matched_card_ids": ["SW_448", "SW_446"],
                },
                "claims": [
                    {
                        "claim_kind": "mulligan_keep",
                        "cards": ["SW_446"],
                        "evidence_text_short": "Keep Voidtouched Attendant.",
                    }
                ],
            }
        ],
        current_date="2026-07-22",
    )
    rows = extract_source_evidence_rows(
        deck_name="ShadowPriest",
        deck_identity=SHADOW_DECK_IDENTITY,
        ranked_sources=ranked,
        current_date="2026-07-22",
    )

    assert rows
    assert rows[0]["freshness_status"] == "current"
    assert rows[0]["current_or_evergreen"] is True
    assert rows[0]["current_or_evergreen_reason"] == "publication_year_matches_current_year"
    assert rows[0]["source_status_apply_blocking"] is False
