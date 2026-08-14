import json
from itertools import permutations

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


def test_exact_duplicate_result_is_byte_identical_for_every_input_permutation():
    rows = [
        {
            "card_id": "REV_290",
            "behavior_block": "BeforePlayCardBonus",
            "condition": "*",
            "value": "8",
            "claim_id": "claim-shared",
            "rule_id_suffix": "deploy",
            "comment": comment,
            "source_claim_ids": [source_claim_id],
        }
        for comment, source_claim_id in (
            ("z-source", "source-z"),
            ("a-source", "source-a"),
            ("m-source", "source-m"),
        )
    ]

    encoded_results = {
        json.dumps(
            canonicalize_runtime_rows(permutation),
            sort_keys=True,
            separators=(",", ":"),
        )
        for permutation in permutations(rows)
    }

    assert len(encoded_results) == 1


def test_exact_duplicates_union_all_existing_provenance():
    result = canonicalize_runtime_rows(
        [
            {
                "card_id": "REV_290",
                "behavior_block": "BeforePlayCardBonus",
                "condition": "*",
                "value": "8",
                "claim_id": "lifecycle-a",
                "source_claim_ids": ["raw-a", "raw-shared"],
                "merged_claim_ids": ["prior-a", "prior-shared"],
            },
            {
                "card_id": "REV_290",
                "behavior_block": "BeforePlayCardBonus",
                "condition": "*",
                "value": "8",
                "claim_id": "lifecycle-b",
                "source_claim_ids": ["raw-b", "raw-shared"],
                "merged_claim_ids": ["prior-b", "prior-shared"],
            },
        ]
    )

    assert result["rows"][0]["source_claim_ids"] == [
        "raw-a",
        "raw-b",
        "raw-shared",
    ]
    assert result["rows"][0]["merged_claim_ids"] == [
        "lifecycle-a",
        "lifecycle-b",
        "prior-a",
        "prior-b",
        "prior-shared",
        "raw-a",
        "raw-b",
        "raw-shared",
    ]
    assert result["merged_provenance"][0]["source_claim_ids"] == [
        "raw-a",
        "raw-b",
        "raw-shared",
    ]
    assert result["merged_provenance"][0]["merged_claim_ids"] == [
        "lifecycle-a",
        "lifecycle-b",
        "prior-a",
        "prior-b",
        "prior-shared",
        "raw-a",
        "raw-b",
        "raw-shared",
    ]


def test_conflict_reports_complete_stable_provenance():
    result = canonicalize_runtime_rows(
        [
            {
                "card_id": "REV_290",
                "behavior_block": "BeforePlayCardBonus",
                "condition": "*",
                "value": value,
                "claim_id": claim_id,
                "source_claim_ids": source_claim_ids,
                "merged_claim_ids": merged_claim_ids,
            }
            for value, claim_id, source_claim_ids, merged_claim_ids in (
                ("6", "lifecycle-a", ["raw-a", "raw-shared"], ["prior-a"]),
                ("8", "lifecycle-b", ["raw-b", "raw-shared"], ["prior-b"]),
            )
        ]
    )

    assert result["rows"] == []
    assert result["conflicts"][0]["source_claim_ids"] == [
        "raw-a",
        "raw-b",
        "raw-shared",
    ]
    assert result["conflicts"][0]["merged_claim_ids"] == [
        "lifecycle-a",
        "lifecycle-b",
        "prior-a",
        "prior-b",
        "raw-a",
        "raw-b",
        "raw-shared",
    ]


def test_exact_duplicate_source_refs_are_merged_for_every_input_permutation():
    rows = [
        {
            "card_id": "REV_290",
            "behavior_block": "BeforePlayCardBonus",
            "condition": "*",
            "value": "8",
            "claim_id": claim_id,
            "source_refs": source_refs,
        }
        for claim_id, source_refs in (
            ("claim-a", ["guide:z", "guide:shared"]),
            ("claim-b", ["guide:a", "guide:shared"]),
            ("claim-c", ["guide:m"]),
        )
    ]

    encoded_results = set()
    for permutation in permutations(rows):
        result = canonicalize_runtime_rows(permutation)
        assert result["rows"][0]["source_refs"] == [
            "guide:a",
            "guide:m",
            "guide:shared",
            "guide:z",
        ]
        assert result["merged_provenance"][0]["source_refs"] == [
            "guide:a",
            "guide:m",
            "guide:shared",
            "guide:z",
        ]
        encoded_results.add(
            json.dumps(
                result,
                sort_keys=True,
                separators=(",", ":"),
            )
        )

    assert len(encoded_results) == 1
