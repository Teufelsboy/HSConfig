from hsconfig.source_claim_lifecycle import (
    build_initial_lifecycle_rows,
    runtime_claims_for_surface,
)
from hsconfig.source_document_model import strict_claim_kind


def test_lifecycle_migrates_legacy_claim_type_once_and_stores_claim_kind():
    rows = build_initial_lifecycle_rows(
        [
            {
                "claim_id": "legacy_combo",
                "claim_type": "combo",
                "cards": ["CARD_001", "CARD_002"],
                "combo": "CARD_001 >> CARD_002",
                "value": "20 >> 20",
                "source_confidence": "guide_backed",
            }
        ]
    )

    assert rows[0]["claim_id"] == "legacy_combo"
    assert rows[0]["claim_kind"] == "combo_sequence"
    assert rows[0]["legacy_claim_type"] == "combo"
    assert rows[0]["migration_status"] == "legacy_claim_type_migrated"
    assert "claim_type" not in runtime_claims_for_surface(rows, "combo")[0]


def test_strict_claim_kind_requires_stored_modern_claim_kind_after_ingestion():
    assert strict_claim_kind({"claim_kind": "mulligan_keep"}) == "mulligan_keep"
    assert strict_claim_kind({"claim_type": "mulligan"}) == ""


def test_runtime_claims_for_surface_excludes_quarantined_report_only_claims():
    rows = build_initial_lifecycle_rows(
        [
            {
                "claim_id": "keep_1",
                "claim_kind": "mulligan_keep",
                "card_id": "CARD_001",
                "source_confidence": "guide_backed",
            },
            {
                "claim_id": "keep_2",
                "claim_kind": "mulligan_keep",
                "card_id": "CARD_002",
                "source_confidence": "guide_backed",
            },
            {
                "claim_id": "role_1",
                "claim_kind": "card_role",
                "card_id": "CARD_003",
                "source_confidence": "report_only",
            },
        ],
        conflict_report={
            "conflicts": [
                {
                    "claim_ids": ["keep_2"],
                    "reason": "contradictory_mulligan_keep_discard",
                }
            ]
        },
    )

    runtime_claims = runtime_claims_for_surface(rows, "mulligan")
    assert [claim["claim_id"] for claim in runtime_claims] == ["keep_1"]
    by_id = {row["claim_id"]: row for row in rows}
    assert by_id["keep_2"]["quarantine_status"] == "quarantined"
    assert by_id["role_1"]["runtime_eligibility"] == "report_only"


def test_unknown_confidence_targeting_rule_remains_lifecycle_only():
    rows = build_initial_lifecycle_rows(
        [
            {
                "claim_id": "unknown_targeting",
                "claim_kind": "targeting_rule",
                "card_id": "CARD_004",
                "source_confidence": "unknown",
            },
            {
                "claim_id": "missing_confidence_targeting",
                "claim_kind": "targeting_rule",
                "card_id": "CARD_005",
            },
        ]
    )

    assert [row["claim_id"] for row in rows] == [
        "unknown_targeting",
        "missing_confidence_targeting",
    ]
    assert {row["runtime_eligibility"] for row in rows} == {"report_only"}
    assert runtime_claims_for_surface(rows, "cardid") == []


def test_lifecycle_mulligan_surface_suppresses_start_of_game_transform_roles():
    rows = build_initial_lifecycle_rows(
        [
            {
                "claim_id": "darkbishop_keep",
                "claim_kind": "mulligan_keep",
                "cards": ["SW_448"],
                "source_confidence": "guide_backed",
                "evidence_text_short": "Darkbishop Benedictus changes the starting Hero Power.",
            }
        ]
    )

    runtime_claims = runtime_claims_for_surface(
        rows,
        "mulligan",
        card_roles={
            "SW_448": {
                "roles": [
                    "start_of_game",
                    "hero_power_transform",
                    "deckbuilding_effect",
                ],
                "semantic_families": [
                    "start_of_game",
                    "hero_power_transform",
                    "deckbuilding_effect",
                ],
            }
        },
    )

    assert rows[0]["claim_id"] == "darkbishop_keep"
    assert rows[0]["runtime_eligibility"] == "runtime_candidate"
    assert runtime_claims == []
