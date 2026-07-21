from hsconfig.package_builder import _filter_runtime_rows_by_claim_ids


def test_filter_runtime_rows_keeps_rows_referenced_by_merged_claim_ids():
    row = {
        "card": "SW_444",
        "action": "hold",
        "claim_id": "keep_twilight_guide_a",
        "source_claim_ids": ["raw_keep_twilight_a", "raw_keep_twilight_b"],
        "merged_claim_ids": ["keep_twilight_guide_a", "keep_twilight_guide_b"],
    }

    assert _filter_runtime_rows_by_claim_ids([row], {"keep_twilight_guide_b"}) == [row]
