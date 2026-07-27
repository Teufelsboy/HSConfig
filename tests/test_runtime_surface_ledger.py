from hsconfig.runtime_surface_ledger import build_runtime_surface_ledger
from hsconfig.config_readiness import build_config_readiness_report
from hsconfig.config_usefulness import build_config_usefulness
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
        compiled_globalvalues={
            "GlobalAggroValue": {"values": [{"condition": "*", "value": "100"}]}
        },
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
        compiled_mulligan={
            "Mulligan": {"values": [{"mulligan": "FIR_911", "value": "hold"}]}
        },
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


def test_runtime_surface_ledger_parses_only_valid_combo_rows_and_fails_closed():
    ledger = build_runtime_surface_ledger(
        deck_identity={
            "deck_name": "Combo Fixture",
            "cards": [
                {"card_id": "A_001", "count": 1},
                {"card_id": "B_002", "count": 1},
                {"card_id": "C_003", "count": 1},
            ],
        },
        compiled_mulligan={},
        compiled_globalvalues={},
        compiled_combo={
            "ComboList": {
                "values": [
                    {"combo": "A_001 >> B_002"},
                    {"combo": "B_002 >-> C_003"},
                    {"combo": "A_001"},
                    {"combo": "A_001 >>  >> C_003"},
                    {"cardid": "C_003"},
                ]
            }
        },
        compiled_cardid_files={},
        linked_runtime_owners=[],
    )

    assert ledger["cards"]["A_001"]["runtime_surfaces"] == ["Combo.json"]
    assert ledger["cards"]["C_003"]["runtime_surfaces"] == ["Combo.json"]
    assert ledger["physical_errors"] == [
        "combo_malformed:2",
        "combo_malformed:3",
        "combo_malformed:4",
    ]


def test_runtime_surface_ledger_rejects_invalid_cardid_and_records_sideboard_emission():
    ledger = build_runtime_surface_ledger(
        deck_identity={
            "deck_name": "Physical Fixture",
            "cards": [
                {"card_id": "MAIN_001", "count": 1},
                {"card_id": "BAD_001", "count": 1},
            ],
            "sideboards": [
                {
                    "owner_card_id": "MAIN_001",
                    "cards": [{"card_id": "SIDE_001", "count": 1}],
                }
            ],
        },
        compiled_mulligan={},
        compiled_globalvalues={"ConfigComment": "metadata only"},
        compiled_combo=None,
        compiled_cardid_files={
            "MAIN_001.json": {
                "GameCardId": "OTHER_001",
                "BeforePlayCardBonus": {"values": [{"Value": "1"}]},
            },
            "SIDE_001.json": {
                "GameCardId": "SIDE_001",
                "BeforePlayCardBonus": {"values": [{"Value": "1"}]},
            },
            "BAD_001.json": {
                "GameCardId": "BAD_001",
                "BeforePlayCardBonus": {"values": ["not a behavior row"]},
            },
        },
        linked_runtime_owners=[],
    )

    assert ledger["cards"]["MAIN_001"]["runtime_surfaces"] == []
    assert ledger["cards"]["SIDE_001"]["runtime_surfaces"] == ["SIDE_001.json"]
    assert ledger["physical_errors"] == [
        "cardid_identity_invalid:MAIN_001.json",
        "cardid_runtime_block_invalid:BAD_001.json",
    ]
    assert ledger["unexpected_runtime_emissions"] == [
        {"card_id": "SIDE_001", "reason": "ineligible_card_runtime_emitted"}
    ]
    assert ledger["globalvalues_emitted"] is False


def test_runtime_surface_ledger_rejects_owner_collisions_independent_of_input_order():
    common = {
        "deck_identity": {"deck_name": "Owner Fixture", "cards": [{"card_id": "A_001", "count": 1}, {"card_id": "B_002", "count": 1}]},
        "compiled_mulligan": {},
        "compiled_globalvalues": {},
        "compiled_combo": None,
        "compiled_cardid_files": {
            "TOKEN_001.json": {
                "GameCardId": "TOKEN_001",
                "BeforePlayCardBonus": {"values": [{"Value": "1"}]},
            }
        },
    }
    forward = build_runtime_surface_ledger(
        **common,
        linked_runtime_owners=[
            {"source_card_id": "A_001", "runtime_card_id": "TOKEN_001", "link_kind": "token"},
            {"source_card_id": "B_002", "runtime_card_id": "TOKEN_001", "link_kind": "token"},
        ],
    )
    reversed_owners = build_runtime_surface_ledger(
        **common,
        linked_runtime_owners=list(reversed([
            {"source_card_id": "A_001", "runtime_card_id": "TOKEN_001", "link_kind": "token"},
            {"source_card_id": "B_002", "runtime_card_id": "TOKEN_001", "link_kind": "token"},
        ])),
    )

    assert forward["linked_runtime_entities"] == reversed_owners["linked_runtime_entities"] == {}
    assert forward["linked_runtime_owner_collisions"] == reversed_owners["linked_runtime_owner_collisions"]


def test_ledger_empty_physical_payload_cannot_inherit_plan_runtime_lane():
    readiness = build_config_readiness_report(
        deck_identity={"deck_name": "Empty Physical", "cards": [{"card_id": "A_001", "count": 1}]},
        claim_coverage={},
        gameplan_contract={"cards": {}},
        mulligan_plan={"rules": [{"card_id": "A_001", "action": "hold"}]},
        card_behavior_plan={"rows": [{"card_id": "A_001", "meaningful_runtime_surface": True, "behavior_block": "BeforePlayCardBonus"}]},
        combo_plan={"combos": [{"cards": ["A_001", "B_002"]}]},
        global_values_authority_matrix={},
        emitted_cardid_files={"A_001.json": {"GameCardId": "A_001", "BeforePlayCardBonus": {"values": [{"Value": "1"}]}}},
        runtime_surface_ledger={
            "cards": {"A_001": {"runtime_surfaces": []}},
            "linked_runtime_entities": {},
            "surface_ledger_sha256": "b" * 64,
        },
    )

    assert readiness["cards"]["A_001"]["runtime_surfaces"] == []
    assert readiness["cards"]["A_001"]["readiness_lane"] == "report_only_supported"
    assert readiness["cards"]["A_001"]["first_missing_link"] == "needs_runtime_surface"


def test_config_usefulness_counts_only_authoritative_ledger_surfaces():
    usefulness = build_config_usefulness(
        technical_status="VALID_PACKAGE",
        semantic_status="",
        config_readiness_summary={"runtime_emitted": 1, "report_only_supported": 0},
        config_readiness_report={"surface_ledger_sha256": "c" * 64},
        mulligan_plan_report={"rules": [{"card_id": "A_001", "action": "hold"}]},
        card_behavior_plan_report={"rows": [{"card_id": "A_001", "meaningful_runtime_surface": True, "behavior_block": "BeforePlayCardBonus"}]},
        combo_plan_report={"combos": [{"cards": ["A_001", "B_002"]}]},
        globalvalues_profile_report={"changed_keys": ["GlobalAggroValue"]},
        runtime_surface_ledger={
            "cards": {"A_001": {"runtime_surfaces": []}},
            "globalvalues_emitted": False,
        },
    )

    assert usefulness["surfaces"]["mulligan"]["rule_count"] == 0
    assert usefulness["surfaces"]["mulligan"]["status"] == "thin"
    assert usefulness["surfaces"]["cardid_behavior"]["cards_with_meaningful_cardid_rows"] == 0
    assert usefulness["surfaces"]["cardid_behavior"]["status"] == "thin"
    assert usefulness["surfaces"]["combo"]["combo_row_count"] == 0
    assert usefulness["surfaces"]["combo"]["status"] == "not_expected"
    assert usefulness["surfaces"]["globalvalues"]["changed_key_count"] == 0
    assert usefulness["surfaces"]["globalvalues"]["status"] == "thin"


def test_runtime_surface_ledger_tracks_exact_surface_metrics_and_baseline_only_globalvalues():
    ledger = build_runtime_surface_ledger(
        deck_identity={
            "deck_name": "Metric Fixture",
            "cards": [
                {"card_id": "A_001", "count": 1},
                {"card_id": "B_002", "count": 1},
                {"card_id": "C_003", "count": 1},
            ],
        },
        compiled_mulligan={
            "Mulligan": {
                "values": [
                    {"mulligan": "A_001", "value": "hold"},
                    {"mulligan": "B_002", "value": "hold"},
                ]
            }
        },
        compiled_globalvalues={
            "GlobalAggroValue": {"values": [{"condition": "*", "value": "100"}]}
        },
        globalvalues_baseline={"GlobalAggroValue": "100"},
        compiled_combo={
            "ComboList": {
                "values": [
                    {"combo": "A_001 >> B_002"},
                    {"combo": "B_002 >-> C_003"},
                ]
            }
        },
        compiled_cardid_files={},
        linked_runtime_owners=[],
    )

    assert ledger["mulligan"]["rule_count"] == 2
    assert ledger["mulligan"]["card_ids"] == ["A_001", "B_002"]
    assert ledger["combo"]["row_count"] == 2
    assert ledger["combo"]["card_ids"] == ["A_001", "B_002", "C_003"]
    assert ledger["globalvalues"]["changed_key_count"] == 0
    assert ledger["globalvalues"]["changed_keys"] == []


def test_runtime_surface_ledger_counts_linked_owner_cardid_entity():
    ledger = build_runtime_surface_ledger(
        deck_identity={"deck_name": "Linked Metric", "cards": [{"card_id": "SOURCE_001", "count": 1}]},
        compiled_mulligan={},
        compiled_globalvalues={},
        compiled_combo=None,
        compiled_cardid_files={
            "TOKEN_001.json": {
                "GameCardId": "TOKEN_001",
                "BeforePlayCardBonus": {"values": [{"condition": "*", "value": "1"}]},
            }
        },
        linked_runtime_owners=[
            {"source_card_id": "SOURCE_001", "runtime_card_id": "TOKEN_001", "link_kind": "token"}
        ],
    )

    assert ledger["cardid"]["entity_count"] == 1
    assert ledger["cardid"]["card_ids"] == ["TOKEN_001"]
    assert ledger["cardid"]["behavior_row_count"] == 1


def test_runtime_surface_ledger_preserves_combo_operators_and_single_row_is_rich():
    ledger = build_runtime_surface_ledger(
        deck_identity={
            "deck_name": "Combo Identity",
            "cards": [
                {"card_id": "A_001", "count": 1},
                {"card_id": "B_002", "count": 1},
            ],
        },
        compiled_mulligan={},
        compiled_globalvalues={},
        compiled_combo={
            "ComboList": {
                "values": [
                    {"combo": "A_001 >-> B_002"},
                    {"combo": "A_001 >> A_001"},
                ]
            }
        },
        compiled_cardid_files={},
        linked_runtime_owners=[],
    )
    single_row = {
        **ledger,
        "combo": {"row_count": 1, "rows": ["A_001>>A_001"], "card_ids": ["A_001"]},
    }
    usefulness = build_config_usefulness(
        technical_status="VALID_PACKAGE",
        semantic_status="",
        config_readiness_summary={},
        runtime_surface_ledger=single_row,
    )

    assert ledger["combo"]["rows"] == ["A_001>->B_002", "A_001>>A_001"]
    assert usefulness["surfaces"]["combo"]["combo_row_count"] == 1
    assert usefulness["surfaces"]["combo"]["status"] == "rich"


def test_runtime_surface_ledger_rejects_orphan_cardid_and_out_of_deck_mulligan_combo_ids():
    ledger = build_runtime_surface_ledger(
        deck_identity={"deck_name": "Ownership", "cards": [{"card_id": "A_001", "count": 1}]},
        compiled_mulligan={"Mulligan": {"values": [{"mulligan": "ORPHAN_001", "value": "hold"}]}},
        compiled_globalvalues={},
        compiled_combo={"ComboList": {"values": [{"combo": "A_001 >> ORPHAN_001"}]}},
        compiled_cardid_files={
            "ORPHAN_001.json": {
                "GameCardId": "ORPHAN_001",
                "BeforePlayCardBonus": {"values": [{"condition": "*", "value": "1"}]},
            }
        },
        linked_runtime_owners=[],
    )

    assert ledger["physical_errors"] == [
        "cardid_orphan_runtime_entity:ORPHAN_001",
        "combo_out_of_deck_card:ORPHAN_001",
        "mulligan_out_of_deck_card:ORPHAN_001",
    ]


def test_config_usefulness_keeps_discard_only_mulligan_thin():
    usefulness = build_config_usefulness(
        technical_status="VALID_PACKAGE",
        semantic_status="",
        config_readiness_summary={},
        runtime_surface_ledger={
            "mulligan": {
                "rule_count": 1,
                "rules": [{"mulligan": "A_001", "value": "discard", "condition": "*"}],
                "card_ids": ["A_001"],
            },
            "combo": {"row_count": 0},
            "cardid": {},
            "globalvalues": {},
        },
    )

    assert usefulness["surfaces"]["mulligan"]["rule_count"] == 1
    assert usefulness["surfaces"]["mulligan"]["has_concrete_keeps"] is False
    assert usefulness["surfaces"]["mulligan"]["status"] == "thin"
