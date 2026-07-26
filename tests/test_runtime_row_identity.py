from hsconfig.runtime_row_identity import canonicalize_runtime_rows


def test_exact_duplicate_rows_merge_provenance():
    result = canonicalize_runtime_rows(
        [
            {
                "card_id": "REV_290",
                "behavior_block": "BeforePlayCardBonus",
                "condition": "*",
                "value": "8",
                "claim_id": "claim-a",
            },
            {
                "card_id": "REV_290",
                "behavior_block": "BeforePlayCardBonus",
                "condition": "*",
                "value": "8",
                "claim_id": "claim-b",
            },
        ]
    )

    assert len(result["rows"]) == 1
    assert result["merged_duplicate_count"] == 1
    assert result["rows"][0]["source_claim_ids"] == ["claim-a", "claim-b"]
    assert result["conflicts"] == []


def test_same_surface_condition_with_different_values_fails_closed():
    result = canonicalize_runtime_rows(
        [
            {
                "card_id": "REV_290",
                "behavior_block": "BeforePlayCardBonus",
                "condition": "*",
                "value": "6",
                "claim_id": "claim-a",
            },
            {
                "card_id": "REV_290",
                "behavior_block": "BeforePlayCardBonus",
                "condition": "*",
                "value": "8",
                "claim_id": "claim-b",
            },
        ]
    )

    assert result["rows"] == []
    assert result["conflicts"][0]["key"] == [
        "REV_290",
        "BeforePlayCardBonus",
        "*",
    ]
    assert result["conflicts"][0]["values"] == ["6", "8"]
