from hsconfig.runtime_surface_ledger import build_runtime_surface_ledger
from hsconfig.config_readiness import build_config_readiness_report
from hsconfig.source_to_runtime_explainability import (
    build_source_to_runtime_explainability_report,
)


def test_runtime_surface_ledger_uses_compiled_artifacts_and_keeps_linked_records_separate():
    ledger = build_runtime_surface_ledger(
        deck_identity={
            "deck_name": "Ledger Fixture",
            "cards": [
                {"card_id": "FIR_911", "count": 1},
                {"card_id": "SW_448", "count": 1},
                {"card_id": "TOY_330", "count": 1},
            ],
            "sideboards": [
                {
                    "owner_card_id": "TOY_330",
                    "cards": [
                        {"card_id": "TOY_330t11", "count": 1},
                        {"card_id": "TOY_330t95", "count": 1},
                        {"card_id": "TOY_330t98", "count": 1},
                    ],
                }
            ],
        },
        compiled_mulligan={
            "Mulligan": {"values": [{"mulligan": "FIR_911", "value": "hold"}]}
        },
        compiled_globalvalues={"GlobalAggroValue": "100"},
        compiled_combo=None,
        compiled_cardid_files={
            "EX1_625t.json": {
                "GameCardId": "EX1_625t",
                "BeforeUseHeroPowerBonus": {"values": [{"Value": "9"}]},
            }
        },
        linked_runtime_owners=[
            {
                "source_card_id": "SW_448",
                "runtime_card_id": "EX1_625t",
                "link_kind": "hero_power_transform",
            }
        ],
    )

    assert ledger["cards"]["FIR_911"]["runtime_surfaces"] == ["Mulligan.json"]
    assert ledger["cards"]["FIR_911"]["runtime_emitted"] is True
    assert ledger["cards"]["SW_448"]["runtime_surfaces"] == []
    assert ledger["linked_runtime_entities"]["EX1_625t"] == {
        "source_card_id": "SW_448",
        "runtime_card_id": "EX1_625t",
        "link_kind": "hero_power_transform",
        "runtime_surface": "EX1_625t.json",
        "runtime_emitted": True,
    }
    for card_id in ("TOY_330t11", "TOY_330t95", "TOY_330t98"):
        assert ledger["cards"][card_id]["deck_zone"] == "sideboard"
        assert ledger["cards"][card_id]["runtime_surfaces"] == []
    assert len(ledger["surface_ledger_sha256"]) == 64


def test_readiness_uses_ledger_mulligan_surface_over_plan_inference():
    ledger = build_runtime_surface_ledger(
        deck_identity={"deck_name": "Ledger Fixture", "cards": [{"card_id": "FIR_911", "count": 1}]},
        compiled_mulligan={"Mulligan": {"values": [{"CardID": "FIR_911"}]}},
        compiled_globalvalues={},
        compiled_combo=None,
        compiled_cardid_files={},
        linked_runtime_owners=[],
    )
    readiness = build_config_readiness_report(
        deck_identity={"deck_name": "Ledger Fixture", "cards": [{"card_id": "FIR_911", "count": 1}]},
        claim_coverage={},
        gameplan_contract={"cards": {}},
        mulligan_plan={"rules": []},
        card_behavior_plan={"rows": []},
        combo_plan={"combos": []},
        global_values_authority_matrix={},
        emitted_cardid_files={},
        runtime_surface_ledger=ledger,
    )

    assert readiness["cards"]["FIR_911"]["runtime_surfaces"] == ["Mulligan.json"]
    assert readiness["cards"]["FIR_911"]["readiness_lane"] == "mulligan_only"
    assert readiness["surface_ledger_sha256"] == ledger["surface_ledger_sha256"]


def test_explainability_carries_the_canonical_ledger_hash():
    report = build_source_to_runtime_explainability_report(
        {"claim_lifecycle_rows": [], "claim_rows": {}, "card_rows": {}},
        runtime_surface_ledger={"surface_ledger_sha256": "a" * 64},
    )

    assert report["surface_ledger_sha256"] == "a" * 64
