import pytest

from hsconfig.source_document_builder import build_source_document_bundle
from hsconfig.source_document_drafter import draft_source_documents
from hsconfig.source_document_model import can_lower_to_mulligan
from hsconfig.source_acquisition_provenance import (
    CAPTURED_RECORD,
    build_acquisition_provenance,
)
from tests.helpers.live_acquisition import acquire_live_test_provenance


DECK_IDENTITY = {
    "deck_name": "ShadowPriest",
    "deck_code_hash": "sha256:shadow",
    "cards": [
        {"card_id": "BAR_735", "name": "Darkbishop Benedictus", "count": 1},
        {"card_id": "SW_446", "name": "Mind Spike Enabler", "count": 2},
    ],
}

INVALID_EXACT_COUNT_VALUES = [
    pytest.param("not-an-int", id="nonnumeric-string"),
    pytest.param(True, id="boolean"),
    pytest.param(-1, id="negative"),
    pytest.param([], id="list"),
    pytest.param({}, id="dictionary"),
    pytest.param(1.5, id="float"),
    pytest.param("9" * 5000, id="oversized-decimal-string"),
]


def _exact_mulligan_evidence_row(
    *,
    fingerprint: str,
    count_field: str,
    count_value,
):
    exact = {
        "candidate_count": 1,
        "decoded_candidate_count": 1,
        "matched": True,
        "matched_deck_fingerprint": fingerprint,
        "candidate_deck_code_hashes": ["sha256:source-code"],
    }
    exact[count_field] = count_value
    return {
        "source_url": "https://example.test/strict-count-guide",
        "source_title": "Strict Count Guide",
        "source_family": "guide",
        "retrieved_at": "2026-07-26T00:00:00Z",
        "acquisition_provenance": acquire_live_test_provenance(),
        "deck_name": "StrictCountDeck",
        "archetype": "strictcountdeck",
        "source_lane": "deck_matched_public_guide",
        "source_rank_lane": "guide_current_deck_match",
        "deck_match_scope": "exact_deck_matched",
        "source_visibility": "full_text",
        "promotion_eligible": True,
        "first_missing_source_action": "none",
        "deck_match": {"exact_deck_evidence": exact},
        "claim_kind": "mulligan_keep",
        "cards": ["EX1_001"],
        "scope": "card",
        "stance": "keep",
        "evidence_text_short": "Keep Fixture One.",
        "source_confidence": "high",
    }


@pytest.mark.parametrize(
    ("is_live_acquisition", "expected_receipt_count"),
    [
        (True, 1),
        (False, 0),
    ],
)
def test_strategic_receipt_minting_is_bound_to_acquisition_provenance(
    is_live_acquisition,
    expected_receipt_count,
):
    content_provenance = (
        acquire_live_test_provenance()
        if is_live_acquisition
        else build_acquisition_provenance(
            mode=CAPTURED_RECORD,
            content=b"Captured source response.",
        )
    )
    fingerprint = "sha256:provenance-target"
    deck_identity = {
        "deck_name": "ProvenanceDeck",
        "deck_fingerprint": fingerprint,
        "cards": [{"card_id": "EX1_001", "name": "Fixture One", "count": 1}],
    }
    row = _exact_mulligan_evidence_row(
        fingerprint=fingerprint,
        count_field="candidate_count",
        count_value=1,
    )
    row["acquisition_provenance"] = content_provenance

    draft = draft_source_documents(
        deck_name="ProvenanceDeck",
        deck_identity=deck_identity,
        evidence_rows=[row],
    )
    document = draft["source_documents"][0]
    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=[document],
        current_date="2026-07-26",
    )

    assert document["acquisition_provenance"] == content_provenance
    assert bundle["claims"][0]["acquisition_provenance"] == content_provenance
    assert len(bundle["canonical_source_receipts"]) == expected_receipt_count
    if expected_receipt_count:
        assert bundle["canonical_source_receipts"][0][
            "acquisition_provenance"
        ] == content_provenance
        assert bundle["strategic_receipt_diagnostics"] == []
    else:
        assert bundle["strategic_receipt_diagnostics"] == [
            {
                "claim_id": bundle["claims"][0]["claim_id"],
                "source_ref": "source:1",
                "code": "strategic_provenance_not_live_verified",
            }
        ]


@pytest.mark.parametrize(
    ("extra_key", "sensitive_value"),
    [
        ("raw_html", "<main>private source text</main>"),
        ("local_path", "C:/Users/operator/private/source.html"),
        ("source_url", "https://example.test/guide?token=super-secret"),
    ],
)
def test_strategic_receipt_rejects_noncanonical_provenance_fields(
    extra_key,
    sensitive_value,
):
    fingerprint = "sha256:strict-provenance-target"
    deck_identity = {
        "deck_name": "StrictProvenanceDeck",
        "deck_fingerprint": fingerprint,
        "cards": [{"card_id": "EX1_001", "name": "Fixture One", "count": 1}],
    }
    row = _exact_mulligan_evidence_row(
        fingerprint=fingerprint,
        count_field="candidate_count",
        count_value=1,
    )
    row["acquisition_provenance"] = {
        **acquire_live_test_provenance(),
        extra_key: sensitive_value,
    }

    draft = draft_source_documents(
        deck_name="StrictProvenanceDeck",
        deck_identity=deck_identity,
        evidence_rows=[row],
    )
    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=draft["source_documents"],
        current_date="2026-07-26",
    )

    assert bundle["canonical_source_receipts"] == []
    assert bundle["strategic_receipt_diagnostics"] == [
        {
            "claim_id": bundle["claims"][0]["claim_id"],
            "source_ref": "source:1",
            "code": "strategic_provenance_not_live_verified",
        }
    ]
    assert sensitive_value not in str(bundle["canonical_source_receipts"])


def test_drafter_preserves_consensus_exact_deck_evidence():
    fingerprint = "sha256:exact-shadowpriest"
    row = {
        "source_url": "https://example.test/shadowpriest-exact",
        "source_title": "Exact ShadowPriest Guide",
        "source_family": "guide",
        "retrieved_at": "2026-07-26T00:00:00Z",
        "deck_name": "ShadowPriest",
        "archetype": "shadowpriest",
        "source_lane": "deck_matched_public_guide",
        "source_rank_lane": "guide_current_deck_match",
        "deck_match_scope": "exact_deck_matched",
        "source_visibility": "full_text",
        "promotion_eligible": True,
        "strong_promotion_eligible": True,
        "deck_match": {
            "exact_deck_evidence": {
                "candidate_count": 1,
                "decoded_candidate_count": 1,
                "matched": True,
                "matched_deck_fingerprint": fingerprint,
                "candidate_deck_code_hashes": ["sha256:source-code"],
            }
        },
        "claim_kind": "mulligan_keep",
        "cards": ["TOY_381"],
        "scope": "card",
        "stance": "keep",
        "evidence_text_short": "Keep Papercraft Angel.",
        "source_confidence": "high",
    }

    result = draft_source_documents(
        deck_name="ShadowPriest",
        deck_identity={
            "deck_name": "ShadowPriest",
            "deck_fingerprint": fingerprint,
            "cards": [{"card_id": "TOY_381", "name": "Papercraft Angel"}],
        },
        evidence_rows=[row],
    )

    document = result["source_documents"][0]
    assert document["deck_match"] == row["deck_match"]
    assert "AAEBA" not in str(document)


def test_drafter_excludes_raw_deckstring_from_exact_evidence():
    fingerprint = "sha256:exact-shadowpriest"
    raw_deckstring = (
        "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
        "KgG17oG1cEGAAA="
    )
    row = {
        "source_url": "https://example.test/shadowpriest-exact",
        "source_title": "Exact ShadowPriest Guide",
        "source_family": "guide",
        "retrieved_at": "2026-07-26T00:00:00Z",
        "deck_name": "ShadowPriest",
        "archetype": "shadowpriest",
        "source_lane": "deck_matched_public_guide",
        "source_rank_lane": "guide_current_deck_match",
        "deck_match_scope": "exact_deck_matched",
        "source_visibility": "full_text",
        "deck_match": {
            "exact_deck_evidence": {
                "candidate_count": 1,
                "decoded_candidate_count": 1,
                "matched": True,
                "matched_deck_fingerprint": fingerprint,
                "candidate_deck_code_hashes": ["sha256:source-code"],
                "raw_deckstring": raw_deckstring,
            }
        },
        "claim_kind": "mulligan_keep",
        "cards": ["TOY_381"],
        "scope": "card",
        "stance": "keep",
        "evidence_text_short": "Keep Papercraft Angel.",
        "source_confidence": "high",
    }

    result = draft_source_documents(
        deck_name="ShadowPriest",
        deck_identity={
            "deck_name": "ShadowPriest",
            "deck_fingerprint": fingerprint,
            "cards": [{"card_id": "TOY_381", "name": "Papercraft Angel"}],
        },
        evidence_rows=[row],
    )

    exact = result["source_documents"][0]["deck_match"]["exact_deck_evidence"]
    assert exact == {
        "candidate_count": 1,
        "decoded_candidate_count": 1,
        "matched": True,
        "matched_deck_fingerprint": fingerprint,
        "candidate_deck_code_hashes": ["sha256:source-code"],
    }
    assert raw_deckstring not in str(result)


@pytest.mark.parametrize(
    "count_field",
    ["candidate_count", "decoded_candidate_count"],
)
@pytest.mark.parametrize("invalid_value", INVALID_EXACT_COUNT_VALUES)
def test_drafter_invalid_exact_counts_fail_closed_without_exception(
    count_field,
    invalid_value,
):
    fingerprint = "sha256:strict-count-target"
    deck_identity = {
        "deck_name": "StrictCountDeck",
        "deck_fingerprint": fingerprint,
        "cards": [{"card_id": "EX1_001", "name": "Fixture One", "count": 1}],
    }
    try:
        draft = draft_source_documents(
            deck_name="StrictCountDeck",
            deck_identity=deck_identity,
            evidence_rows=[
                _exact_mulligan_evidence_row(
                    fingerprint=fingerprint,
                    count_field=count_field,
                    count_value=invalid_value,
                )
            ],
        )
    except (TypeError, ValueError) as exc:
        pytest.fail(f"invalid exact evidence must fail closed, not raise: {exc}")

    document = draft["source_documents"][0]
    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=draft["source_documents"],
        current_date="2026-07-26",
    )

    assert document["deck_match_scope"] == "archetype_matched"
    assert document["source_lane"] == "archetype_matched_public_guide"
    assert document["first_missing_source_action"] == "add_exact_deck_matched_source"
    assert "deck_match" not in document
    assert bundle["globalvalues_source_receipts"] == []


@pytest.mark.parametrize(
    "accepted_value",
    [pytest.param(1, id="integer"), pytest.param("1", id="decimal-string")],
)
def test_drafter_accepts_strict_positive_integer_count_forms(accepted_value):
    fingerprint = "sha256:strict-count-target"
    deck_identity = {
        "deck_name": "StrictCountDeck",
        "deck_fingerprint": fingerprint,
        "cards": [{"card_id": "EX1_001", "name": "Fixture One", "count": 1}],
    }
    draft = draft_source_documents(
        deck_name="StrictCountDeck",
        deck_identity=deck_identity,
        evidence_rows=[
            _exact_mulligan_evidence_row(
                fingerprint=fingerprint,
                count_field="candidate_count",
                count_value=accepted_value,
            )
        ],
    )
    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=draft["source_documents"],
        current_date="2026-07-26",
    )

    assert draft["source_documents"][0]["deck_match_scope"] == "exact_deck_matched"
    assert len(bundle["globalvalues_source_receipts"]) == 1


def test_drafter_downgrades_conflicting_exact_evidence():
    rows = []
    for fingerprint in ("sha256:first", "sha256:second"):
        rows.append(
            {
                "source_url": "https://example.test/shared-guide",
                "source_title": "Shared Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-26T00:00:00Z",
                "deck_name": "ShadowPriest",
                "archetype": "shadowpriest",
                "source_lane": "deck_matched_public_guide",
                "source_rank_lane": "guide_current_deck_match",
                "deck_match_scope": "exact_deck_matched",
                "source_visibility": "full_text",
                "deck_match": {
                    "exact_deck_evidence": {
                        "matched": True,
                        "matched_deck_fingerprint": fingerprint,
                    }
                },
                "claim_kind": "mulligan_keep",
                "cards": ["TOY_381"],
                "scope": "card",
                "stance": "keep",
                "source_confidence": "high",
            }
        )

    result = draft_source_documents(
        deck_name="ShadowPriest",
        deck_identity={
            "deck_name": "ShadowPriest",
            "cards": [{"card_id": "TOY_381", "name": "Papercraft Angel"}],
        },
        evidence_rows=rows,
    )

    document = result["source_documents"][0]
    assert document["deck_match_scope"] == "archetype_matched"
    assert document["source_lane"] == "archetype_matched_public_guide"
    assert "deck_match" not in document


def test_drafter_resolves_card_mentions_to_strict_source_documents():
    draft = draft_source_documents(
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        evidence_rows=[
            {
                "source_url": "https://example.invalid/shadow-priest",
                "source_title": "Shadow Priest Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-07T12:00:00Z",
                "archetype": "aggro_burn_hero_power_transform",
                "claim_kind": "hero_power_transform",
                "card_mentions": ["Darkbishop Benedictus"],
                "stance": "enable_transformed_hero_power",
                "evidence_text_short": "The deck wants the Shadow hero power online.",
                "source_confidence": "high",
            }
        ],
        current_date="2026-07-07",
    )

    documents = draft["source_documents"]
    assert documents[0]["claims"][0]["cards"] == ["BAR_735"]
    assert documents[0]["claims"][0]["claim_kind"] == "hero_power_transform"
    assert draft["draft_summary"]["resolved_claims"] == 1
    assert draft["unresolved_mentions"] == []

    bundle = build_source_document_bundle(
        deck_identity=DECK_IDENTITY,
        card_metadata={"cards": DECK_IDENTITY["cards"]},
        source_documents=documents,
        current_date="2026-07-07",
    )
    assert bundle["unsupported_claims"] == []


def test_drafter_reports_unresolved_mentions_without_dropping_source_context():
    draft = draft_source_documents(
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        evidence_rows=[
            {
                "source_url": "https://example.invalid/shadow-priest",
                "source_title": "Shadow Priest Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-07T12:00:00Z",
                "claim_kind": "card_role",
                "card_mentions": ["Missing Card"],
                "stance": "core_card",
                "evidence_text_short": "Missing Card is important.",
                "source_confidence": "medium",
            }
        ],
        current_date="2026-07-07",
    )

    assert draft["source_documents"][0]["claims"] == []
    assert draft["unresolved_mentions"][0]["mention"] == "Missing Card"
    assert draft["draft_summary"]["unresolved_mentions"] == 1


def test_drafter_drops_partially_resolved_claims_until_all_mentions_are_resolved():
    draft = draft_source_documents(
        deck_name="ShadowPriest",
        deck_identity=DECK_IDENTITY,
        evidence_rows=[
            {
                "source_url": "https://example.invalid/shadow-priest",
                "source_title": "Shadow Priest Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-07T12:00:00Z",
                "claim_kind": "card_role",
                "card_mentions": ["Darkbishop Benedictus", "Missing Card"],
                "stance": "core_card",
                "evidence_text_short": "These cards are important together.",
                "source_confidence": "medium",
            }
        ],
        current_date="2026-07-07",
    )

    assert draft["source_documents"][0]["claims"] == []
    assert [row["mention"] for row in draft["unresolved_mentions"]] == ["Missing Card"]
    assert draft["draft_summary"]["dropped_claims"] == 1


def test_drafter_preserves_non_hand_semantic_qualifiers_through_mulligan_gate():
    deck_identity = {
        "deck_name": "HighlanderFixture",
        "cards": [
            {"card_id": "HIGHLANDER_001", "name": "Highlander Payoff", "count": 1},
        ],
    }

    draft = draft_source_documents(
        deck_name="HighlanderFixture",
        deck_identity=deck_identity,
        evidence_rows=[
            {
                "source_url": "https://example.invalid/highlander",
                "source_title": "Highlander Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-14T00:00:00Z",
                "claim_kind": "mulligan_keep",
                "card_mentions": ["Highlander Payoff"],
                "evidence_text_short": "Core payoff for the no-duplicates game plan.",
                "source_confidence": "high",
                "semantic_qualifiers": {
                    "zone_scope": "Deck",
                    "state_requirements": ["deckbuilding_effect"],
                },
                "deck_evaluation": "No Duplicates",
                "generation_scope": "Generated Card",
            }
        ],
        current_date="2026-07-14",
    )

    drafted_claim = draft["source_documents"][0]["claims"][0]
    assert drafted_claim["semantic_qualifiers"] == {
        "zone_scope": "Deck",
        "state_requirements": ["deckbuilding_effect"],
    }
    assert drafted_claim["deck_evaluation"] == "No Duplicates"
    assert drafted_claim["generation_scope"] == "Generated Card"

    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=draft["source_documents"],
        current_date="2026-07-14",
    )
    claim = bundle["claims"][0]

    assert claim["semantic_qualifiers"] == {
        "zone_scope": "deck",
        "state_requirements": ["deckbuilding_effect"],
        "generation_scope": "generated",
        "deck_evaluation": ["highlander"],
    }
    decision = can_lower_to_mulligan(claim)
    assert decision.allowed is False
    assert decision.reason == "mulligan_requires_exact_deck_match"


def test_drafter_preserves_evidence_policy_fields():
    draft = draft_source_documents(
        deck_name="ShadowPriest",
        deck_identity={
            **DECK_IDENTITY,
            "deck_fingerprint": "sha256:shadow",
        },
        evidence_rows=[
            {
                "source_url": "https://example.invalid/shadow-priest",
                "source_title": "Shadow Priest Guide",
                "source_family": "guide",
                "retrieved_at": "2026-07-15T00:00:00Z",
                "claim_kind": "mulligan_keep",
                "card_mentions": ["Mind Spike Enabler"],
                "stance": "keep",
                "evidence_text_short": "Mulligan: keep Mind Spike Enabler.",
                "source_confidence": "high",
                "source_visibility": "full_text",
                "source_lane": "deck_matched_public_guide",
                "source_rank_lane": "guide_current_deck_match",
                "deck_match_scope": "exact_deck_matched",
                "deck_match": {
                    "exact_deck_evidence": {
                        "candidate_count": 1,
                        "decoded_candidate_count": 1,
                        "matched": True,
                        "matched_deck_fingerprint": "sha256:shadow",
                        "candidate_deck_code_hashes": [
                            "sha256:shadow-source-code"
                        ],
                    }
                },
                "source_record_strength": "candidate_strong",
                "promotion_eligible": True,
                "strong_promotion_eligible": True,
                "promotion_blockers": [],
                "first_missing_source_action": "none",
            }
        ],
        current_date="2026-07-15",
    )

    document = draft["source_documents"][0]
    claim = document["claims"][0]

    assert document["source_rank_lane"] == "guide_current_deck_match"
    assert document["first_missing_source_action"] == "none"
    assert claim["source_rank_lane"] == "guide_current_deck_match"
    assert claim["strong_promotion_eligible"] is True
    assert claim["promotion_blockers"] == []
    assert claim["first_missing_source_action"] == "none"


@pytest.mark.parametrize("timing", ["Opening Hand", "mulligan"])
def test_drafter_preserves_explicit_mulligan_timing_for_real_opening_hand_claim(timing):
    deck_identity = {
        "deck_name": "HighlanderFixture",
        "cards": [
            {"card_id": "HIGHLANDER_001", "name": "Highlander Payoff", "count": 1},
        ],
    }

    draft = draft_source_documents(
        deck_name="HighlanderFixture",
        deck_identity=deck_identity,
        evidence_rows=[
            {
                "source_url": "https://example.invalid/highlander-mulligan",
                "source_title": "Highlander Mulligan Guide",
                "source_family": "mulligan_guide",
                "retrieved_at": "2026-07-14T00:00:00Z",
                "claim_kind": "mulligan_keep",
                "card_mentions": ["Highlander Payoff"],
                "evidence_text_short": "Keep the payoff.",
                "source_confidence": "high",
                "deck_evaluation": "No Duplicates",
                "timing": timing,
            }
        ],
        current_date="2026-07-14",
    )

    drafted_claim = draft["source_documents"][0]["claims"][0]
    assert drafted_claim["timing"] == timing

    bundle = build_source_document_bundle(
        deck_identity=deck_identity,
        card_metadata={"cards": deck_identity["cards"]},
        source_documents=draft["source_documents"],
        current_date="2026-07-14",
    )
    claim = bundle["claims"][0]

    assert claim["semantic_qualifiers"]["deck_evaluation"] == ["highlander"]
    assert claim["semantic_qualifiers"]["timing"] == "mulligan"
    decision = can_lower_to_mulligan(claim)
    assert decision.allowed is False
    assert decision.reason == "mulligan_requires_exact_deck_match"
