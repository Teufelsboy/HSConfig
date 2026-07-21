import json
from pathlib import Path

from hsconfig.config_quality_contract import build_config_quality_report


DECK_SLUG = "shadowpriest"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def minimal_clean_package(tmp_path: Path) -> Path:
    package = tmp_path / "package"
    deck_dir = package / "CustomConfig" / DECK_SLUG
    write_json(
        package / "reports" / "operator_summary.json",
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "source_status_apply_blocking": False,
            "default_only_runtime_surfaces": [],
            "no_default_only_runtime_status": {
                "status": "clean",
                "default_only_runtime_surfaces": [],
            },
            "surface_status_ledger": [
                {"surface": "cardid_behavior", "status": "emitted"},
                {"surface": "globalvalues", "status": "emitted"},
                {"surface": "mulligan", "status": "emitted"},
                {"surface": "combo", "status": "not_applicable"},
            ],
        },
    )
    write_json(
        package / "reports" / "card_behavior_plan_report.json",
        {
            "rows": [
                {
                    "card_id": "NX2_019",
                    "surface_family": "CARDID.json",
                    "behavior_block": "BeforeBattlecryTargetBonus",
                    "value": "10",
                    "meaningful_runtime_surface": True,
                    "semantic_score": {
                        "band": "high",
                        "reason": "conditional_minion_death_burn",
                        "profile": "semantic_intent",
                        "matched_signals": ["enemy_hero_damage", "death_condition"],
                    },
                }
            ]
        },
    )
    write_json(
        package / "reports" / "source_to_runtime_explainability.json",
        {
            "default_only_runtime_surfaces": [],
            "card_rows": [
                {
                    "card_id": "NX2_019",
                    "first_missing_link": "none",
                    "runtime_surfaces": ["NX2_019.json"],
                }
            ],
        },
    )
    write_json(
        deck_dir / "NX2_019.json",
        {
            "GameCardId": "NX2_019",
            "ConfigComment": "ShadowPriest: generated behavior for NX2_019",
            "BeforeBattlecryTargetBonus": {
                "values": [
                    {
                        "comment": "ShadowPriest: NX2_019_prefer_enemy_minion",
                        "condition": "*",
                        "value": "10",
                    }
                ]
            },
        },
    )
    write_json(deck_dir / "GlobalValues.json", {"GameCardId": "GlobalValues"})
    write_json(
        deck_dir / "Mulligan.json",
        {"GameCardId": "Mulligan", "Mulligan": {"values": []}},
    )
    return package


def test_config_quality_report_is_clean_for_source_backed_runtime_lean_package(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)

    report = build_config_quality_report(package)

    assert report["schema_version"] == 1
    assert report["status"] == "clean"
    assert report["authority"] == "diagnostic_only"
    assert report["apply_blocking"] is False
    assert report["runtime_write_performed"] is False
    assert report["problems"] == []
    assert report["checks"]["operator_summary"]["present"] is True
    assert report["checks"]["operator_summary"]["default_only_runtime_surfaces"] == []
    assert report["checks"]["card_behavior"]["semantic_score_missing_rows"] == []
    assert report["checks"]["card_behavior"]["semantic_default_rows"] == []
    assert report["checks"]["card_behavior"]["out_of_range_value_rows"] == []
    assert report["checks"]["runtime_json"]["metadata_leaks"] == []
    assert report["checks"]["legacy_surfaces"]["present"] == []


def test_config_quality_flags_default_only_runtime_surfaces(tmp_path: Path):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "reports" / "operator_summary.json",
        {
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "source_status_apply_blocking": False,
            "default_only_runtime_surfaces": ["cardid_behavior"],
        },
    )

    report = build_config_quality_report(package)

    assert report["status"] == "attention"
    assert {
        "check": "operator_default_only_runtime_surfaces",
        "value": ["cardid_behavior"],
    } in report["problems"]
    assert report["apply_blocking"] is False


def test_config_quality_flags_explainability_default_only_issues(tmp_path: Path):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "reports" / "source_to_runtime_explainability.json",
        {
            "default_only_runtime_surfaces": "Mulligan.json",
            "records": [{"default_only_runtime_surfaces": ["cardid_behavior"]}],
        },
    )

    report = build_config_quality_report(package)

    assert report["status"] == "attention"
    assert report["checks"]["source_to_runtime_explainability"] == {
        "present": True,
        "has_default_only_runtime_surfaces": True,
        "default_only_runtime_surface_errors": [
            "default_only_runtime_surfaces_must_be_list"
        ],
    }
    assert {
        "check": "explainability_default_only_runtime_surfaces",
        "value": True,
    } in report["problems"]
    assert {
        "check": "explainability_default_only_runtime_surface_errors",
        "value": ["default_only_runtime_surfaces_must_be_list"],
    } in report["problems"]


def test_config_quality_flags_meaningful_cardid_rows_without_semantic_score(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "reports" / "card_behavior_plan_report.json",
        {
            "rows": [
                {
                    "card_id": "NX2_019",
                    "surface_family": "CARDID.json",
                    "behavior_block": "BeforeBattlecryTargetBonus",
                    "value": "10",
                    "meaningful_runtime_surface": True,
                }
            ]
        },
    )

    report = build_config_quality_report(package)

    assert report["status"] == "attention"
    assert report["checks"]["card_behavior"]["semantic_score_missing_rows"] == [
        {
            "card_id": "NX2_019",
            "behavior_block": "BeforeBattlecryTargetBonus",
            "value": "10",
        }
    ]
    assert {
        "check": "card_behavior_semantic_score_missing",
        "value": [
            {
                "card_id": "NX2_019",
                "behavior_block": "BeforeBattlecryTargetBonus",
                "value": "10",
            }
        ],
    } in report["problems"]


def test_config_quality_flags_semantic_default_rows(tmp_path: Path):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "reports" / "card_behavior_plan_report.json",
        {
            "rows": [
                {
                    "card_id": "CARD_DEFAULT",
                    "surface_family": "CARDID.json",
                    "behavior_block": "BeforePlayCardBonus",
                    "value": "6",
                    "meaningful_runtime_surface": True,
                    "semantic_score": {
                        "band": "default",
                        "reason": "semantic_default",
                        "profile": "semantic_intent",
                    },
                }
            ]
        },
    )

    report = build_config_quality_report(package)

    assert report["status"] == "attention"
    assert report["checks"]["card_behavior"]["semantic_default_rows"] == [
        {
            "card_id": "CARD_DEFAULT",
            "behavior_block": "BeforePlayCardBonus",
            "value": "6",
            "reason": "semantic_default",
        }
    ]
    assert {
        "check": "card_behavior_semantic_default_visible",
        "value": [
            {
                "card_id": "CARD_DEFAULT",
                "behavior_block": "BeforePlayCardBonus",
                "value": "6",
                "reason": "semantic_default",
            }
        ],
    } in report["problems"]


def test_config_quality_flags_numeric_cardid_values_outside_runtime_range(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "reports" / "card_behavior_plan_report.json",
        {
            "rows": [
                {
                    "card_id": "CARD_LOW",
                    "surface_family": "CARDID.json",
                    "behavior_block": "BeforePlayCardBonus",
                    "value": "3",
                    "meaningful_runtime_surface": True,
                    "semantic_score": {"reason": "explicit_runtime_value"},
                },
                {
                    "card_id": "CARD_HIGH",
                    "surface_family": "CARDID.json",
                    "behavior_block": "BeforePlayCardBonus",
                    "value": "13",
                    "meaningful_runtime_surface": True,
                    "semantic_score": {"reason": "explicit_runtime_value"},
                },
                {
                    "card_id": "CARD_TEXT",
                    "surface_family": "CARDID.json",
                    "behavior_block": "BeforePlayCardBonus",
                    "value": "hold",
                    "meaningful_runtime_surface": True,
                    "semantic_score": {"reason": "explicit_runtime_value"},
                },
            ]
        },
    )

    report = build_config_quality_report(package)

    assert report["status"] == "attention"
    assert report["checks"]["card_behavior"]["out_of_range_value_rows"] == [
        {
            "card_id": "CARD_LOW",
            "behavior_block": "BeforePlayCardBonus",
            "value": "3",
        },
        {
            "card_id": "CARD_HIGH",
            "behavior_block": "BeforePlayCardBonus",
            "value": "13",
        },
    ]
    assert {
        "check": "card_behavior_value_out_of_range",
        "value": [
            {
                "card_id": "CARD_LOW",
                "behavior_block": "BeforePlayCardBonus",
                "value": "3",
            },
            {
                "card_id": "CARD_HIGH",
                "behavior_block": "BeforePlayCardBonus",
                "value": "13",
            },
        ],
    } in report["problems"]


def test_config_quality_flags_diagnostic_metadata_leaking_into_runtime_json(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "CustomConfig" / DECK_SLUG / "NX2_019.json",
        {
            "GameCardId": "NX2_019",
            "BeforeBattlecryTargetBonus": {
                "values": [
                    {
                        "comment": "ShadowPriest: NX2_019_prefer_enemy_minion",
                        "condition": "*",
                        "value": "10",
                        "semantic_score": {"reason": "conditional_minion_death_burn"},
                    }
                ]
            },
        },
    )

    report = build_config_quality_report(package)

    assert report["status"] == "attention"
    assert report["checks"]["runtime_json"]["metadata_leaks"] == [
        {
            "file": "CustomConfig/shadowpriest/NX2_019.json",
            "block": "BeforeBattlecryTargetBonus",
            "row_index": 0,
            "extra_keys": ["semantic_score"],
        }
    ]


def test_config_quality_flags_forbidden_legacy_runtime_surfaces(tmp_path: Path):
    package = minimal_clean_package(tmp_path)
    write_json(package / "CustomConfig" / DECK_SLUG / "Presume.json", {})
    write_json(package / "CustomConfig" / "controlpriest" / "Concede.json", {})
    write_json(package / "CustomConfig" / "controlpriest" / "CardBehavior.json", {})

    report = build_config_quality_report(package)

    assert report["status"] == "attention"
    assert report["checks"]["legacy_surfaces"]["present"] == [
        "CustomConfig/controlpriest/CardBehavior.json",
        "CustomConfig/controlpriest/Concede.json",
        "CustomConfig/shadowpriest/Presume.json",
    ]
    assert {
        "check": "forbidden_legacy_runtime_surfaces",
        "value": [
            "CustomConfig/controlpriest/CardBehavior.json",
            "CustomConfig/controlpriest/Concede.json",
            "CustomConfig/shadowpriest/Presume.json",
        ],
    } in report["problems"]


def test_config_quality_flags_darkbishop_mulligan_keep_drift(tmp_path: Path):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "CustomConfig" / DECK_SLUG / "Mulligan.json",
        {
            "GameCardId": "Mulligan",
            "Mulligan": {
                "values": [
                    {
                        "comment": "ShadowPriest: SW_448 should not be kept",
                        "condition": "*",
                        "mulligan": "SW_448",
                        "value": "hold",
                    }
                ]
            },
        },
    )
    write_json(
        package / "CustomConfig" / DECK_SLUG / "SW_448.json",
        {
            "GameCardId": "SW_448",
            "BeforeUseHeroPowerBonus": {
                "values": [
                    {
                        "comment": "ShadowPriest: SW_448_hero_power_transform",
                        "condition": "*",
                        "value": "10",
                    }
                ]
            },
        },
    )

    report = build_config_quality_report(package)

    assert report["status"] == "attention"
    assert report["checks"]["darkbishop_boundary"] == {
        "seen": True,
        "mulligan_keep_present": True,
        "effect_runtime_present": True,
    }
    assert {
        "check": "darkbishop_mulligan_keep_without_explicit_evidence",
        "value": {"card_id": "SW_448"},
    } in report["problems"]


def test_config_quality_allows_darkbishop_effect_runtime_without_mulligan_keep(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "CustomConfig" / DECK_SLUG / "Mulligan.json",
        {
            "GameCardId": "Mulligan",
            "Mulligan": {
                "values": [
                    {
                        "comment": "ShadowPriest: discard 4-cost or higher cards",
                        "condition": "*",
                        "mulligan": "SW_448",
                        "value": "discard",
                    }
                ]
            },
        },
    )
    write_json(
        package / "CustomConfig" / DECK_SLUG / "SW_448.json",
        {
            "GameCardId": "SW_448",
            "BeforeUseHeroPowerBonus": {
                "values": [
                    {
                        "comment": "ShadowPriest: SW_448_hero_power_transform",
                        "condition": "*",
                        "value": "10",
                    }
                ]
            },
        },
    )

    report = build_config_quality_report(package)

    assert report["checks"]["darkbishop_boundary"] == {
        "seen": True,
        "mulligan_keep_present": False,
        "effect_runtime_present": True,
    }
    assert report["problems"] == []
