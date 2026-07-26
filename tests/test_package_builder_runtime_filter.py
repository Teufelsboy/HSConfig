from hsconfig.package_builder import _filter_runtime_rows_by_claim_ids
from hsconfig.runtime_row_identity import canonicalize_runtime_rows


def test_filter_runtime_rows_keeps_rows_referenced_by_merged_claim_ids():
    row = {
        "card": "SW_444",
        "action": "hold",
        "claim_id": "keep_twilight_guide_a",
        "source_claim_ids": ["raw_keep_twilight_a", "raw_keep_twilight_b"],
        "merged_claim_ids": ["keep_twilight_guide_a", "keep_twilight_guide_b"],
    }

    assert _filter_runtime_rows_by_claim_ids([row], {"keep_twilight_guide_b"}) == [row]


def test_filter_runtime_rows_keeps_canonical_row_when_only_second_claim_is_allowed():
    canonical = canonicalize_runtime_rows(
        [
            {
                "card_id": "REV_290",
                "behavior_block": "BeforePlayCardBonus",
                "condition": "*",
                "value": "8",
                "claim_id": claim_id,
                "source_claim_ids": [source_claim_id],
            }
            for claim_id, source_claim_id in (
                ("lifecycle-a", "raw-a"),
                ("lifecycle-b", "raw-b"),
            )
        ]
    )

    assert _filter_runtime_rows_by_claim_ids(
        canonical["rows"],
        {"lifecycle-b"},
    ) == canonical["rows"]
