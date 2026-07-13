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
