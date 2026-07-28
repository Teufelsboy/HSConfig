from pathlib import Path

import pytest

from hsconfig.compile_combo import compile_combo
from hsconfig.io import write_json
from hsconfig.source_claim_compiler import compile_source_search_records
from hsconfig.validate_package import validate_config_package


def test_compile_combo_returns_valid_segment_parity_payload(tmp_path: Path):
    contract = {
        "deck_name": "Fixture Aggro",
        "combos": [
            {
                "rule_id": "combo_1",
                "cards": ["EX1_001", "EX1_002"],
                "values": ["12", "8"],
                "source_claim_ids": ["claim_a"],
            }
        ],
    }

    combo = compile_combo(contract)

    assert combo is not None
    row = combo["ComboList"]["values"][0]
    assert row["combo"] == "EX1_001>>EX1_002"
    assert row["value"] == "12>>8"
    assert set(row) == {"comment", "condition", "combo", "value"}

    deck_dir = tmp_path / "CustomConfig" / "deck"
    write_json(deck_dir / "Combo.json", combo)

    assert validate_config_package(tmp_path)["status"] == "passed"


def test_compile_combo_returns_none_without_combos():
    assert compile_combo({"deck_name": "Fixture", "combos": []}) is None


def test_compile_combo_rejects_invalid_segment_parity():
    with pytest.raises(ValueError, match="Invalid combo sequence"):
        compile_combo(
            {
                "deck_name": "Fixture",
                "combos": [{"rule_id": "bad", "cards": ["EX1_001", "EX1_002"], "values": ["10"]}],
            }
        )


def test_compile_combo_accepts_combo_plan_rows():
    combo = compile_combo(
        {"deck_name": "Fixture"},
        sequences=[
            {
                "rule_id": "combo_plan_1",
                "cards": ["CARD_A", "CARD_B"],
                "values": ["10", "10"],
                "operator": ">>",
                "source_claim_ids": ["claim_a"],
            }
        ],
    )

    assert combo is not None
    assert combo["ComboList"]["values"][0] == {
        "comment": "Fixture: combo_plan_1",
        "condition": "*",
        "combo": "CARD_A>>CARD_B",
        "value": "10>>10",
    }


@pytest.mark.parametrize(
    "connector",
    ["then", "into", "followed by", "->"],
)
def test_source_combo_compiler_preserves_directed_text_order_without_inferred_timing(
    connector,
):
    deck_identity = {
        "deck_name": "Fixture",
        "cards": [
            {"card_id": "CARD_B", "name": "Card B"},
            {"card_id": "CARD_A", "name": "Card A"},
        ],
    }

    payload = compile_source_search_records(
        deck_name="Fixture",
        deck_identity=deck_identity,
        acquired_records=[
            {
                "source_url": "https://example.test/fixture-guide",
                "source_title": "Fixture Guide",
                "source_family": "guide",
                "source_visibility": "full_text",
                "normalized_text": f"Card A {connector} Card B.",
            }
        ],
        current_date="2026-07-28",
    )

    combo_claims = [
        claim
        for claim in payload["records"][0]["claims"]
        if claim["claim_kind"] == "combo_sequence"
    ]
    assert len(combo_claims) == 1
    assert combo_claims[0]["sequence"] == ["CARD_A", "CARD_B"]
    assert "timing" not in combo_claims[0]


@pytest.mark.parametrize(
    "text",
    [
        "Card AX then Card B.",
        "Card A draws one, then discards one; Card B remains available.",
        "Card A shuffles junk into your deck while Card B remains available.",
        "Card A then Card B draws one, then discards one; Card C remains available.",
    ],
)
def test_source_combo_compiler_rejects_prefix_and_effect_clause_false_positives(text):
    deck_identity = {
        "deck_name": "Fixture",
        "cards": [
            {"card_id": "CARD_A", "name": "Card A"},
            {"card_id": "CARD_B", "name": "Card B"},
            {"card_id": "CARD_C", "name": "Card C"},
        ],
    }

    payload = compile_source_search_records(
        deck_name="Fixture",
        deck_identity=deck_identity,
        acquired_records=[
            {
                "source_url": "https://example.test/fixture-guide",
                "source_title": "Fixture Guide",
                "source_family": "guide",
                "source_visibility": "full_text",
                "normalized_text": text,
            }
        ],
        current_date="2026-07-28",
    )

    assert [
        claim
        for claim in payload["records"][0]["claims"]
        if claim["claim_kind"] == "combo_sequence"
    ] == []


def test_source_combo_compiler_resolves_boundary_safe_card_ids():
    deck_identity = {
        "deck_name": "Fixture",
        "cards": [
            {"card_id": "CARD_A", "name": "Fixture Alpha"},
            {"card_id": "CARD_B", "name": "Fixture Beta"},
        ],
    }

    payload = compile_source_search_records(
        deck_name="Fixture",
        deck_identity=deck_identity,
        acquired_records=[
            {
                "source_url": "https://example.test/fixture-guide",
                "source_title": "Fixture Guide",
                "source_family": "guide",
                "source_visibility": "full_text",
                "normalized_text": "CARD_A then CARD_B.",
            }
        ],
        current_date="2026-07-28",
    )

    combo_claims = [
        claim
        for claim in payload["records"][0]["claims"]
        if claim["claim_kind"] == "combo_sequence"
    ]
    assert len(combo_claims) == 1
    assert combo_claims[0]["sequence"] == ["CARD_A", "CARD_B"]
