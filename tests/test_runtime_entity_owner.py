import pytest

from hsconfig.compile_cardid import compile_cardid_behaviors
from hsconfig.config_readiness import build_config_readiness_report
from hsconfig.output_ownership_manifest import build_output_ownership_manifest
from hsconfig.source_to_runtime_explainability import (
    build_source_to_runtime_explainability_report,
)
from hsconfig.surface_intent import build_surface_intent


@pytest.mark.parametrize(
    ("second_behavior_block", "second_value"),
    [
        ("BeforePlayCardBonus", "7"),
        ("BeforeUseHeroPowerBonus", "9"),
    ],
    ids=["same_physical_signature", "different_physical_signature"],
)
def test_competing_sources_for_one_runtime_owner_fail_closed_across_consumers(
    second_behavior_block: str,
    second_value: str,
):
    rows = [
        {
            "surface": "CardID.json",
            "surface_family": "CARDID.json",
            "claim_id": "claim_source_a",
            "card_id": "SOURCE_A",
            "source_card_id": "SOURCE_A",
            "runtime_card_id": "RUNTIME_SHARED",
            "link_kind": "synthetic_link",
            "behavior_block": "BeforePlayCardBonus",
            "condition": "*",
            "value": "7",
        },
        {
            "surface": "CardID.json",
            "surface_family": "CARDID.json",
            "claim_id": "claim_source_b",
            "card_id": "SOURCE_B",
            "source_card_id": "SOURCE_B",
            "runtime_card_id": "RUNTIME_SHARED",
            "link_kind": "synthetic_link",
            "behavior_block": second_behavior_block,
            "condition": "*",
            "value": second_value,
        },
    ]
    plan = {"rows": rows, "suppressed": []}
    expected_collision = [
        {
            "status": "linked_runtime_entity_owner_collision",
            "runtime_card_id": "RUNTIME_SHARED",
            "source_card_ids": ["SOURCE_A", "SOURCE_B"],
        }
    ]

    compiled = compile_cardid_behaviors(
        {"deck_name": "Corrupt fixture", "cards": {}},
        rows=rows,
    )
    readiness = build_config_readiness_report(
        deck_identity={"deck_name": "Corrupt fixture", "cards": []},
        claim_coverage={"uncovered_cards": []},
        gameplan_contract={"deck_name": "Corrupt fixture", "cards": {}},
        mulligan_plan={"rules": []},
        card_behavior_plan=plan,
        combo_plan={"combos": []},
        global_values_authority_matrix={"allowed_step1_overlays": []},
        emitted_cardid_files=compiled,
    )
    explainability = build_source_to_runtime_explainability_report(
        {},
        card_behavior_plan=plan,
    )
    surface_intent = build_surface_intent(
        {
            "cards": {},
            "card_behavior_plan": plan,
        }
    )
    manifest = build_output_ownership_manifest(
        ["CustomConfig/corrupt/RUNTIME_SHARED.json"],
        card_behavior_plan=plan,
    )

    assert "RUNTIME_SHARED.json" not in compiled
    assert compiled.runtime_entity_owner_collisions == expected_collision
    assert readiness["linked_runtime_entities"] == {}
    assert explainability["runtime_entity_transitions"] == []
    assert "RUNTIME_SHARED.json" not in surface_intent["required_surfaces"]
    assert manifest["runtime_entity_ownership"] == []
    assert [row["file"] for row in manifest["files"]].count(
        "CustomConfig/corrupt/RUNTIME_SHARED.json"
    ) == 1
    assert [
        readiness["runtime_entity_owner_collisions"],
        explainability["runtime_entity_owner_collisions"],
        surface_intent["runtime_entity_owner_collisions"],
        manifest["runtime_entity_owner_collisions"],
    ] == [expected_collision] * 4
