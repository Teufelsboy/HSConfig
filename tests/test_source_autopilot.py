from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from hsconfig import source_autopilot
from hsconfig.audited_deck_catalog import load_audited_role_manifest
from hsconfig.deck_identity import build_deck_identity, stable_deck_fingerprint
from hsconfig.deckstring_decode import decode_deck_code
from hsconfig.source_document_builder import build_source_document_bundle
from hsconfig.source_autopilot import (
    _action_from_profile_gap,
    build_source_autopilot_bundle,
    extract_source_evidence_rows,
    rank_public_sources,
)
from tests.helpers.live_acquisition import acquire_live_test_provenance


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
    pytest.param(257, id="above-maximum"),
    pytest.param([], id="list"),
    pytest.param({}, id="dictionary"),
    pytest.param(1.5, id="float"),
    pytest.param("+1", id="positive-sign"),
    pytest.param("1e2", id="exponent"),
    pytest.param(" 1 ", id="surrounding-whitespace"),
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


def test_mulligan_projection_ignores_invalid_rows_and_keeps_canonical_cards() -> None:
    assert source_autopilot._mulligan_rows({}, {"mulligan": []}, {}) == []

    rows = source_autopilot._mulligan_rows(
        {
            "cards": [
                "not-a-card-row",
                {"card_id": "LOW", "cost": 1},
                {"card_id": "HIGH", "cost": 5},
            ]
        },
        {
            "mulligan": {
                "keep_card_ids": ["", "KEEP"],
                "discard_card_ids": ["", "DISCARD"],
                "discard_cost_min": "4",
                "evidence_text_short": " Fixture guidance ",
            }
        },
        {"source_url": "https://example.invalid/guide"},
    )

    assert [(row["claim_kind"], row["cards"]) for row in rows] == [
        ("mulligan_keep", ["KEEP"]),
        ("mulligan_discard", ["DISCARD"]),
        ("mulligan_discard", ["HIGH"]),
    ]
    assert all(row["evidence_text_short"] == "Fixture guidance" for row in rows)


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"claim_kind": "unknown"}, False),
        ({"claim_kind": "mulligan_keep"}, False),
        ({"claim_kind": "mulligan_keep", "cards": ["A"]}, True),
        ({"claim_kind": "combo_sequence", "cards": ["A"]}, False),
        (
            {
                "claim_kind": "combo_sequence",
                "cards": ["A"],
                "sequence": ["A"],
            },
            True,
        ),
        ({"claim_kind": "discover_choice", "cards": ["A"]}, False),
        (
            {
                "claim_kind": "discover_choice",
                "cards": ["A"],
                "option_card_id": "B",
            },
            True,
        ),
        ({"claim_kind": "card_role", "cards": ["A"]}, False),
        (
            {
                "claim_kind": "card_role",
                "cards": ["A"],
                "runtime_block": "Role",
            },
            True,
        ),
    ],
)
def test_runtime_contract_candidate_requires_kind_specific_lowering_inputs(
    row: dict[str, object],
    expected: bool,
) -> None:
    assert source_autopilot._is_runtime_contract_candidate(row) is expected


def test_rank_lane_and_source_lane_classify_public_evidence_shapes() -> None:
    assert source_autopilot._rank_lane(
        "guide",
        3,
        2026,
        {"publication_year": 2026},
        deck_match_scope="exact_deck_matched",
    ) == "guide_current_deck_match"
    assert source_autopilot._rank_lane(
        "guide",
        3,
        2026,
        {"publication_year": 2026},
        deck_match_scope="archetype_matched",
    ) == "guide_current_archetype_match"
    assert source_autopilot._rank_lane(
        "guide",
        3,
        2026,
        {"publication_year": 2020, "format_scope": "wild"},
        deck_match_scope="exact_deck_matched",
    ) == "guide_evergreen_wild_archetype"
    assert source_autopilot._rank_lane(
        "guide",
        1,
        None,
        {},
        deck_match_scope="unknown",
    ) == "guide_card_overlap"
    assert source_autopilot._rank_lane(
        "decklist",
        0,
        None,
        {},
        deck_match_scope="unknown",
    ) == "decklist_only"
    assert source_autopilot._rank_lane(
        "hearthstonejson_static_semantics",
        0,
        None,
        {},
        deck_match_scope="unknown",
    ) == "static_semantics_only"
    assert source_autopilot._rank_lane(
        "other",
        0,
        None,
        {},
        deck_match_scope="unknown",
    ) == "source_unclassified"

    assert source_autopilot._source_lane_for_rank(
        "guide_current_deck_match",
        "exact_deck_matched",
    ) == "deck_matched_public_guide"
    assert source_autopilot._source_lane_for_rank(
        "guide_current_archetype_match",
        "archetype_matched",
    ) == "archetype_matched_public_guide"
    assert source_autopilot._source_lane_for_rank("", "unknown") == "unknown"


def test_evergreen_wild_and_non_opening_effect_boundaries_are_explicit() -> None:
    assert not source_autopilot._is_evergreen_wild_source(
        {},
        current_year=2026,
    )
    assert not source_autopilot._is_evergreen_wild_source(
        {"publication_year": 2026, "format_scope": "wild"},
        current_year=2026,
    )
    assert not source_autopilot._is_evergreen_wild_source(
        {"publication_year": 2015, "format_scope": "wild"},
        current_year=2026,
    )
    assert not source_autopilot._is_evergreen_wild_source(
        {"publication_year": 2020, "format_scope": "standard"},
        current_year=2026,
    )
    assert source_autopilot._is_evergreen_wild_source(
        {
            "publication_year": 2020,
            "format_scope": "standard",
            "evergreen_wild_archetype": "yes",
        },
        current_year=2026,
    )
    assert source_autopilot._is_evergreen_wild_source(
        {"publication_year": 2020, "format_scope": "wild"},
        current_year=2026,
    )

    assert source_autopilot._truthy(True)
    assert not source_autopilot._truthy(False)
    assert source_autopilot._truthy("Y")
    assert not source_autopilot._truthy("no")
    assert source_autopilot._is_non_opening_hand_effect_card(
        {"roles": ["START_OF_GAME"]}
    )
    assert source_autopilot._is_non_opening_hand_effect_card(
        {"text": "At the start of game, transform."}
    )
    assert source_autopilot._is_non_opening_hand_effect_card(
        {"name": "Darkbishop Benedictus"}
    )
    assert not source_autopilot._is_non_opening_hand_effect_card(
        {"name": "Ordinary Minion", "text": "Battlecry"}
    )


def test_match_scope_and_date_helpers_preserve_deterministic_inputs() -> None:
    assert source_autopilot._quantitative_deck_match_scope(
        deck_name_match=True,
        card_overlap=2,
        unique_deck_card_count=5,
    ) == "archetype_matched"
    assert source_autopilot._quantitative_deck_match_scope(
        deck_name_match=False,
        card_overlap=1,
        unique_deck_card_count=5,
    ) == "card_overlap"
    assert source_autopilot._quantitative_deck_match_scope(
        deck_name_match=True,
        card_overlap=0,
        unique_deck_card_count=5,
    ) == "unknown"
    assert source_autopilot._publication_year({"publication_year": "2026"}) == 2026
    assert source_autopilot._publication_year({"published_at": "2025-01-02"}) == 2025
    assert source_autopilot._publication_year({"published_at": "unknown"}) is None
    assert source_autopilot._iso_datetime("2026-08-01") == "2026-08-01T00:00:00Z"
    assert source_autopilot._iso_datetime("2026-08-01T12:30:00Z") == (
        "2026-08-01T12:30:00Z"
    )


def test_strong_guide_lane_requires_shape_and_verified_promotion_authority() -> None:
    row = {
        **_strong_ranked_source(normalized_text="A" * 200),
        "source_freshness_lane": "current",
        "freshness_status": "current",
        "acquisition_provenance": acquire_live_test_provenance(),
        "promotion_eligible": True,
        "strong_promotion_eligible": True,
        "promotion_blockers": [],
        "source_record_strength": "candidate_strong",
        "claim_kind": "mulligan_keep",
        "cards": ["SW_446"],
    }
    assert source_autopilot._is_strong_guide_lane_shape(row, "2026-08-01")
    assert source_autopilot._strong_lane_blockers(row) == []
    assert source_autopilot._is_strong_guide_lane(row, "2026-08-01")

    shape_mutations = [
        {"source_lane": "unknown"},
        {"deck_match_scope": "archetype_matched"},
        {"freshness_status": "stale"},
        {"source_rank_lane": "guide_card_overlap"},
        {"source_visibility": "snippet_only"},
    ]
    for mutation in shape_mutations:
        assert not source_autopilot._is_strong_guide_lane_shape(
            {**row, **mutation},
            "2026-08-01",
        )
    blockers = source_autopilot._strong_lane_blockers(
        {
            **row,
            "acquisition_provenance": {},
            "promotion_eligible": False,
            "strong_promotion_eligible": False,
            "promotion_blockers": ["missing_exact_deck_match", ""],
            "source_family": "decklist",
            "claim_kind": "card_role",
            "source_record_strength": "weak",
        }
    )
    assert blockers == sorted(
        {
            source_autopilot.STRATEGIC_PROVENANCE_NOT_LIVE_VERIFIED,
            "promotion_explicitly_disabled",
            "missing_exact_deck_match",
            "non_promoting_source_record",
            "non_strong_source_record_strength_weak",
        }
    )


def test_emitted_surface_and_suppression_summaries_ignore_empty_rows() -> None:
    rows = [
        {"claim_kind": "combo_sequence", "cards": ["A"], "sequence": ["A"]},
        {"claim_kind": "card_role", "cards": ["", "CARD"], "runtime_block": "Role"},
        {"claim_kind": "hero_power_transform", "cards": []},
    ]
    surfaces = source_autopilot._expected_emitted_surfaces(rows)
    assert "Combo.json" in surfaces
    assert "CARD.json" in surfaces

    assert source_autopilot._suppressed_claim_kinds(
        [
            {"claim_kind": "ignored"},
            {"suppressed": True, "claim_kind": ""},
            {"suppressed": True, "claim_kind": "card_role"},
            {"runtime_lowering": "suppressed", "claim_kind": "card_role"},
            {"runtime_lowering": "suppressed", "claim_kind": "combo_sequence"},
        ]
    ) == ["card_role", "combo_sequence"]


def test_profile_gap_actions_name_the_exact_missing_evidence_family() -> None:
    expectations = {
        "none": "none",
        "default_only_surface:combo": (
            "replace_default_only_surface_with_source_or_policy_row"
        ),
        "claim_kind:mulligan_keep|mulligan_discard": (
            "add_current_mulligan_keep_or_discard_source"
        ),
        "claim_kind:targeting_rule": (
            "add_current_targeting_or_card_behavior_source"
        ),
        "claim_kind:combo_sequence": "add_current_combo_sequence_source",
        "missing_surface:Combo.json": "emit_or_explain_missing_runtime_surface",
        "claim_kind:hero_power_transform": (
            "add_current_card_specific_runtime_source"
        ),
        "unexpected_gap": "add_current_card_specific_runtime_source",
    }

    assert {
        gap: _action_from_profile_gap(gap)
        for gap in expectations
    } == expectations


def test_source_projection_helpers_fail_closed_on_malformed_optional_shapes() -> None:
    base = {"source_url": "https://example.test/guide"}
    rows = source_autopilot._explicit_claim_rows(
        {"claims": ["invalid", {"claim_kind": "card_role", "cards": ["A"]}]},
        base,
    )
    assert rows == [
        {
            **base,
            "claim_kind": "card_role",
            "cards": ["A"],
            "source_confidence": "medium",
            "scope": "card",
            "evidence_text_short": "Structured public source claim.",
        }
    ]
    assert source_autopilot._runtime_surfaces_for_row(
        {"claim_kind": "missing"}
    ) == set()
    assert source_autopilot._source_action_for_claim_kind("discover_choice") == (
        "add_generated_entity_or_option_identity_source"
    )
    assert not source_autopilot._is_apply_surface_candidate(
        {"claim_kind": "archetype"}
    )
    assert source_autopilot._as_list(None) == []
    original = ["A"]
    assert source_autopilot._as_list(original) is original


def test_date_and_document_shape_helpers_keep_defaults_deterministic() -> None:
    day = date(2026, 8, 1)
    assert source_autopilot._current_year(day) == 2026
    assert source_autopilot._iso_datetime(day) == "2026-08-01T00:00:00Z"
    assert source_autopilot._source_family_for_documents(
        {"source_family": "hearthstonejson_static_semantics"}
    ) == "static_semantics"
    assert source_autopilot._source_family_for_documents(
        {"source_family": "metadata"}
    ) == "metadata"
    assert source_autopilot._source_family_for_documents({}) == "guide"
    assert source_autopilot._source_visibility_for_documents(
        {"source_family": "decklist"}
    ) == "decklist_only"
    assert source_autopilot._source_visibility_for_documents(
        {"source_family": "guide", "normalized_text": "short"}
    ) == "snippet_only"
    assert source_autopilot._source_visibility_for_documents(
        {"source_family": "guide"}
    ) == "unknown"


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
    deck = next(
        row
        for row in load_audited_role_manifest(
            Path("docs/operator/archetype-fixture-matrix.json")
        )
        if row["deck_name"] == deck_name
    )
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
        "acquisition_provenance": acquire_live_test_provenance(),
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
        "acquisition_provenance": acquire_live_test_provenance(),
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


def test_fixture_provenance_keeps_diagnostic_claims_but_mints_no_strategic_receipt():
    deck_identity, record = _strict_count_autopilot_fixture(
        count_field="candidate_count",
        count_value=1,
    )
    record["acquisition_provenance"] = {
        "mode": "fixture_map",
        "content_sha256": (
            "sha256:c6d0c3944dcf75fdae82b0bf055bf02c90e6a35bf7df439b"
            "acf671a119c7f828"
        ),
        "authority": "fixture_only",
    }

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

    assert document["acquisition_provenance"] == record["acquisition_provenance"]
    assert source_bundle["claims"]
    assert source_bundle["canonical_source_receipts"] == []
    diagnostics = source_bundle["strategic_receipt_diagnostics"]
    assert {
        diagnostic["claim_id"] for diagnostic in diagnostics
    } == {
        claim["claim_id"]
        for claim in source_bundle["claims"]
        if claim["claim_kind"] in {"mulligan_keep", "gameplan_posture"}
    }
    assert {
        diagnostic["code"] for diagnostic in diagnostics
    } == {"strategic_provenance_not_live_verified"}
    report = autopilot["source_autopilot_report"]
    assert report["semantic_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["strong_candidate"] is False
    assert "strategic_provenance_not_live_verified" in report[
        "strong_candidate_blockers"
    ]


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
        deck_identity = {
            "deck_code_hash": f"{deck_name.lower()}-code-hash",
            "cards": [
                {
                    "card_id": card_id,
                    "name": card_name,
                    "cost": 2,
                    "count": 1,
                    "text": "Fixture card needing exact source closure.",
                },
                {
                    "card_id": "CARD_002",
                    "name": f"{deck_name} Core Card",
                    "cost": 1,
                    "count": 1,
                    "text": "",
                },
            ],
        }
        deck_identity["deck_fingerprint"] = stable_deck_fingerprint(
            (card["card_id"], card["count"])
            for card in deck_identity["cards"]
        )
        bundle = build_source_autopilot_bundle(
            deck_name=deck_name,
            deck_identity=deck_identity,
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
        assert report["explicit_mulligan_source_gaps"] == [
            {
                "card_id": card_id,
                "first_missing_source_action": expected_action,
                "reason": "explicit_source_gap_requires_resolution",
                "target_deck_code_hash": deck_identity["deck_code_hash"],
                "target_deck_fingerprint": deck_identity["deck_fingerprint"],
                "target_deck_name": deck_name,
            }
        ]


def test_exact_mulligan_source_closes_registered_explicit_gap():
    deck_identity = {
        "deck_code_hash": "kingslayer-exact-code-hash",
        "cards": [
            {
                "card_id": "DEEP_014",
                "name": "Quick Pick",
                "cost": 2,
                "count": 2,
            },
            {
                "card_id": "CARD_002",
                "name": "Kingslayer Core Card",
                "cost": 1,
                "count": 2,
            },
        ]
    }
    deck_identity["deck_fingerprint"] = stable_deck_fingerprint(
        (card["card_id"], card["count"])
        for card in deck_identity["cards"]
    )
    bundle = build_source_autopilot_bundle(
        deck_name="Kingslayer",
        deck_identity=deck_identity,
        source_search_records=[
            {
                "source_url": "https://example.test/kingslayer-exact",
                "source_title": "2026 Exact Kingslayer Guide",
                "source_family": "guide",
                "source_visibility": "full_text",
                "publication_year": 2026,
                "source_record_strength": "candidate_strong",
                "acquisition_provenance": acquire_live_test_provenance(),
                "deck_match_scope": "exact_deck_matched",
                "deck_match": {
                    "deck_name": "Kingslayer",
                    "matched_card_ids": ["DEEP_014", "CARD_002"],
                    "exact_deck_evidence": {
                        "candidate_count": 1,
                        "decoded_candidate_count": 1,
                        "matched": True,
                        "matched_deck_fingerprint": deck_identity[
                            "deck_fingerprint"
                        ],
                        "candidate_deck_code_hashes": [
                            "sha256:kingslayer-exact-source"
                        ],
                    },
                },
                "mulligan": {
                    "keep_card_ids": ["DEEP_014"],
                    "evidence_text_short": (
                        "Keep Quick Pick in this exact deck."
                    ),
                },
                "normalized_text": (
                    "Mulligan: Keep Quick Pick in this exact Kingslayer deck."
                ),
            }
        ],
        current_date="2026-07-28",
    )

    assert bundle["source_autopilot_report"][
        "explicit_mulligan_source_gaps"
    ] == []


def test_partial_claim_kind_action_wins_before_profile_card_fallback():
    cases = [
        ("Kingslayer", "DEEP_014", "Quick Pick"),
        ("Boarlock", "WW_092", "Fracking"),
    ]

    for deck_name, card_id, card_name in cases:
        deck_identity = {
            "deck_code_hash": f"{deck_name.lower()}-partial-code-hash",
            "cards": [
                {
                    "card_id": card_id,
                    "name": card_name,
                    "cost": 2,
                    "count": 1,
                    "text": "Fixture card with a partial targeting claim.",
                }
            ],
        }
        deck_identity["deck_fingerprint"] = stable_deck_fingerprint(
            (card["card_id"], card["count"])
            for card in deck_identity["cards"]
        )
        bundle = build_source_autopilot_bundle(
            deck_name=deck_name,
            deck_identity=deck_identity,
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
        assert report["explicit_mulligan_source_gaps"] == [
            {
                "card_id": card_id,
                "first_missing_source_action": (
                    "add_kingslayer_quick_pick_mulligan_source"
                    if deck_name == "Kingslayer"
                    else "add_boarlock_fracking_mulligan_source"
                ),
                "reason": "explicit_source_gap_requires_resolution",
                "target_deck_code_hash": deck_identity["deck_code_hash"],
                "target_deck_fingerprint": deck_identity["deck_fingerprint"],
                "target_deck_name": deck_name,
            }
        ]


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


def test_source_autopilot_small_value_helpers_cover_documented_fallbacks() -> None:
    assert source_autopilot._source_visibility_for_documents(
        {"source_visibility": " Snippet_Only "}
    ) == "snippet_only"
    assert source_autopilot._source_visibility_for_documents(
        {"source_family": "decklist"}
    ) == "decklist_only"
    assert source_autopilot._source_visibility_for_documents(
        {"source_family": "guide", "normalized_text": "x" * 180}
    ) == "full_text"
    assert source_autopilot._source_visibility_for_documents(
        {"source_family": "guide", "normalized_text": "brief"}
    ) == "snippet_only"
    assert source_autopilot._source_visibility_for_documents({}) == "unknown"

    assert source_autopilot._source_family_for_documents(
        {"source_family": "decklist"}
    ) == "metadata"
    assert source_autopilot._source_family_for_documents(
        {"source_family": "hearthstonejson_static_semantics"}
    ) == "static_semantics"
    assert source_autopilot._source_family_for_documents({}) == "guide"

    assert source_autopilot._current_year(date(2025, 1, 2)) == 2025
    assert source_autopilot._current_year("2024-09-01") == 2024
    assert isinstance(source_autopilot._current_year(None), int)
    assert source_autopilot._iso_datetime(date(2025, 1, 2)) == (
        "2025-01-02T00:00:00Z"
    )
    assert source_autopilot._iso_datetime("2025-01-02") == (
        "2025-01-02T00:00:00Z"
    )
    assert source_autopilot._iso_datetime("2025-01-02T03:04:05Z") == (
        "2025-01-02T03:04:05Z"
    )
    assert source_autopilot._iso_datetime(None).endswith("Z")
    assert source_autopilot._int_or_none("7") == 7
    assert source_autopilot._int_or_none("invalid") is None
    assert source_autopilot._as_list(None) == []
    assert source_autopilot._as_list([1]) == [1]
    assert source_autopilot._as_list(1) == [1]


def test_source_autopilot_policy_action_and_profile_mechanics_cover_each_lane() -> None:
    assert source_autopilot._source_policy_missing_action(
        [{"promotion_blockers": [source_autopilot.STRATEGIC_PROVENANCE_NOT_LIVE_VERIFIED]}]
    ) == "acquire_strategic_source_via_live_http"
    assert source_autopilot._source_policy_missing_action(
        [{"promotion_blockers": ["source_not_current_or_evergreen_wild"]}]
    ) == "add_current_or_evergreen_wild_public_guide"
    assert source_autopilot._source_policy_missing_action([{}]) == ""

    mechanics = source_autopilot._primary_mechanics_for_profile(
        deck_name="Shadow Priest",
        evidence_rows=[
            {
                "mechanic": "Weapon Pirate",
                "mechanics": ["Mech Magnetic", ""],
                "deck_name": "Discard Warlock",
                "archetype": "Big Cheat Hunter",
            }
        ],
        claim_kinds=["hero_power_transform", "targeting_rule", "combo_sequence"],
    )
    assert {
        "aggro",
        "burn",
        "combo",
        "discard",
        "hero_power",
        "magnetic",
        "mech",
        "pirate",
        "shadow_hero_power",
        "weapon",
    } <= set(mechanics)


def test_source_autopilot_card_and_surface_repair_maps_filter_invalid_rows() -> None:
    deck_identity = {
        "cards": [
            "invalid",
            {"card_id": ""},
            {"card_id": "A", "name": "Quick Pick"},
            {"card_id": "B", "name": "Second"},
        ]
    }
    evidence = [
        {
            "cards": ["B"],
            "claim_kind": "targeting_rule",
            "runtime_surfaces": ["CardID.json"],
            "source_family": "guide",
        },
        {
            "cards": ["A"],
            "claim_kind": "mulligan_keep",
            "runtime_surfaces": ["Mulligan.json"],
            "suppressed": True,
        },
    ]

    by_card = source_autopilot._first_missing_source_action_by_card(
        "Fixture",
        deck_identity,
        evidence,
        current_date="2026-08-01",
        profile_first_missing="",
    )
    assert by_card == {
        "A": "add_exact_mulligan_keep_or_discard_source",
        "B": "add_card_specific_targeting_source",
    }

    assert source_autopilot._first_missing_source_action_by_surface(
        evidence,
        current_date="2026-08-01",
        summary={"first_missing_source_action": "add_current_guide"},
    ) == {
        "CardID.json": "add_card_specific_targeting_source",
        "Mulligan.json": "add_exact_mulligan_keep_or_discard_source",
    }
    assert source_autopilot._first_missing_source_action_by_surface(
        [],
        current_date="2026-08-01",
        summary={"first_missing_source_action": "none"},
    ) == {}

    lanes = source_autopilot._card_lane_rows(
        deck_identity,
        evidence,
        current_date="2026-08-01",
    )
    assert [row["card_id"] for row in lanes] == ["A", "B"]
    assert source_autopilot._card_lane(
        [{"suppressed": True}], current_date="2026-08-01"
    ) == "suppressed"
    assert source_autopilot._card_lane(
        [{"source_family": "hearthstonejson_static_semantics"}],
        current_date="2026-08-01",
    ) == "static_only"
    assert source_autopilot._card_lane([], current_date="2026-08-01") == (
        "source_gap"
    )


def test_source_autopilot_identity_dedupe_and_policy_projection_fail_softly() -> None:
    rows: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    row = {
        "source_url": "https://example.test/guide",
        "claim_kind": "card_role",
        "cards": ["A"],
        "card_mentions": [],
        "stance": "role",
        "condition": "always",
        "runtime_block": "CastSpellsModifiers",
    }
    source_autopilot._append_unique(rows, seen, row)
    source_autopilot._append_unique(rows, seen, dict(row))
    assert rows == [row]

    assert not source_autopilot._has_independent_deck_match(
        {}, "", card_overlap=1
    )
    assert not source_autopilot._has_exact_deck_evidence(
        {"deck_match": []}, {"deck_fingerprint": "sha256:fixture"}
    )
    policy = source_autopilot._policy_fields(
        {
            "source_rank_lane": "guide_current_deck_match",
            "promotion_eligible": True,
        },
        include_rank_lane=False,
    )
    assert policy == {"promotion_eligible": True}

    base = source_autopilot._source_base(
        "Fixture",
        {"cards": []},
        {
            "source_url": "http://localhost/private",
            "source_family": "static",
            "deck_match": "invalid",
        },
        "2026-08-01",
    )
    assert "deck_match" not in base
    assert base["deck_name"] == ""
    assert base["archetype"] == ""
    assert base["source_visibility"] == "unknown"


def test_rank_public_sources_penalizes_static_private_sources_with_bad_match_shape() -> None:
    ranked = rank_public_sources(
        deck_name="",
        deck_identity={"cards": []},
        source_search_records=[
            {
                "source_family": "hearthstonejson_static_semantics",
                "source_url": "http://localhost/private",
                "deck_match": "invalid",
            }
        ],
        current_date="2026-08-01",
    )

    assert ranked[0]["deck_match"] == {
        "matched_card_ids": [],
        "matched_card_count": 0,
        "unique_deck_card_count": 0,
        "card_overlap_ratio": 0.0,
    }
    assert ranked[0]["source_rank_score"] == -120
    assert ranked[0]["source_visibility"] == "unknown"


def test_surface_lane_projection_preserves_suppression_and_missing_profile_surface() -> None:
    verdict = source_autopilot.ClosureProfileVerdict(
        profile_name="fixture",
        closed=False,
        strong_eligible=False,
        first_missing_link="missing_surface:Combo.json",
        missing_claim_groups=(),
        missing_surfaces=("Combo.json",),
    )

    rows = source_autopilot._surface_lane_rows(
        [
            {
                "claim_kind": "mulligan_keep",
                "cards": ["A"],
                "suppressed": True,
            },
            {
                "claim_kind": "targeting_rule",
                "cards": ["B"],
                "source_family": "guide",
            },
        ],
        current_date="2026-08-01",
        profile_verdict=verdict,
    )

    assert rows == [
        {
            "surface": "CardID.json",
            "lane": "source_gap",
            "claim_kinds": ["targeting_rule"],
            "source_families": ["guide"],
            "first_missing_source_action": (
                "add_current_deck_guide_or_mulligan_guide"
            ),
        },
        {
            "surface": "Combo.json",
            "lane": "source_gap",
            "claim_kinds": [],
            "source_families": [],
            "first_missing_source_action": "emit_or_explain_missing_runtime_surface",
        },
        {
            "surface": "Mulligan.json",
            "lane": "suppressed",
            "claim_kinds": ["mulligan_keep"],
            "source_families": [],
            "first_missing_source_action": "emit_or_explain_missing_runtime_surface",
        },
    ]


def test_strong_guide_shape_requires_current_year_for_current_lane() -> None:
    row = {
        "source_family": "guide",
        "source_lane": "deck_matched_public_guide",
        "deck_match_scope": "exact_deck_matched",
        "freshness_status": "current",
        "source_rank_lane": "guide_current_deck_match",
        "source_visibility": "full_text",
        "publication_year": 2026,
    }

    assert source_autopilot._is_strong_guide_lane_shape(row, "2026-08-01")
    assert not source_autopilot._is_strong_guide_lane_shape(
        {**row, "publication_year": 2025},
        "2026-08-01",
    )
    assert source_autopilot._policy_fields(
        {"source_rank_lane": "guide_current_deck_match"},
        include_rank_lane=True,
    ) == {"source_rank_lane": "guide_current_deck_match"}

    evergreen = {
        **row,
        "source_rank_lane": "guide_evergreen_wild_archetype",
        "source_freshness_lane": "evergreen_wild_archetype",
    }
    assert source_autopilot._is_strong_guide_lane_shape(
        evergreen,
        "2026-08-01",
    )


def test_candidate_blockers_and_card_repair_preserve_actionable_diagnostics() -> None:
    assert source_autopilot._strong_candidate_blockers(
        card_specific_lowerable_guide_rows=[{}],
        apply_surface_guide_rows=[{}],
        strong_shaped_non_promoting_rows=[],
        draft={"unresolved_mentions": ["Unknown Card"]},
        verification={"status": "passed", "warnings": []},
    ) == ["unresolved_source_mentions"]
    assert source_autopilot._card_missing_action_from_profile(
        "UnregisteredDeck",
        {"card_id": "UNREGISTERED", "name": "Quick Pick Fixture"},
        "",
    ) == "add_exact_mulligan_keep_or_discard_source"
