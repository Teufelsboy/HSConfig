import json
from pathlib import Path

import pytest

from hsconfig.commands.configure import _compact_config_quality_summary
from hsconfig.config_quality_contract import (
    _file_card_id,
    _runtime_value_row_keys,
    build_config_quality_report,
    semantic_handoff_projection,
)
from hsconfig.visionai_registry import is_supported_card_behavior_block
from tests.helpers.fixture_prepare import (
    load_archetype_matrix,
    prepare_fixture_deck,
)


DECK_SLUG = "shadowpriest"


def _physical_blocks(card_files: dict[str, dict], card_id: str) -> list[str]:
    payload = card_files.get(f"{card_id}.json", {})
    return sorted(
        block
        for block in payload
        if is_supported_card_behavior_block(block)
    )


def test_shadowpriest_fixture_has_exact_runtime_owned_physical_blocks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    shadow = next(
        row
        for row in load_archetype_matrix()
        if row["deck_name"] == "ShadowPriest"
    )
    prepared = prepare_fixture_deck(tmp_path, shadow)
    assert prepared["exit_code"] == 0

    deck_dir = next((prepared["out"] / "CustomConfig").iterdir())
    card_files = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in deck_dir.glob("*.json")
    }
    assert _physical_blocks(card_files, "GVG_009") == []
    assert _physical_blocks(card_files, "VAC_419") == []
    assert _physical_blocks(card_files, "TOY_518") == ["OnBoardBonus"]
    assert _physical_blocks(card_files, "WON_065") == ["OnBoardBonus"]
    assert _physical_blocks(card_files, "SW_448") == []
    assert _physical_blocks(card_files, "EX1_625t") == ["BeforeUseHeroPowerBonus"]

    behavior_plan = json.loads(
        (prepared["out"] / "reports" / "card_behavior_plan_report.json").read_text(
            encoding="utf-8"
        )
    )

    def emitted_actions(runtime_card_id: str, behavior_block: str) -> list[dict]:
        return [
            row
            for row in behavior_plan["rows"]
            if str(row.get("runtime_card_id", row.get("card_id", "")))
            == runtime_card_id
            and row.get("behavior_block") == behavior_block
        ]

    for card_id in ("TOY_518", "WON_065"):
        rows = emitted_actions(card_id, "OnBoardBonus")
        assert len(rows) == 1
        assert rows[0]["source_card_id"] == card_id

    hero_power_rows = emitted_actions("EX1_625t", "BeforeUseHeroPowerBonus")
    assert len(hero_power_rows) == 1
    assert hero_power_rows[0]["source_card_id"] == "SW_448"
    assert hero_power_rows[0]["link_kind"] == "hero_power_transform"


def test_semantic_handoff_projection_collects_semantic_parity_reasons() -> None:
    projection = semantic_handoff_projection(
        {
            "checks": {
                "runtime_row_trace_inventory": {
                    "unreported_runtime_rows": [{"card_id": "EX1_001"}],
                    "reported_rows_missing_runtime": [{"card_id": "EX1_002"}],
                },
                "visionai_semantic_surface": {
                    "attention": ["semantic_surface_not_expressible"],
                },
                "globalvalues": {
                    "missing_overlay_keys": ["GlobalMinionAttack"],
                },
            }
        }
    )

    assert projection == {
        "semantic_handoff_status": "attention",
        "semantic_handoff_reasons": [
            "missing_globalvalues_overlay_keys",
            "reported_rows_missing_runtime",
            "semantic_surface_not_expressible",
            "unreported_runtime_rows",
        ],
    }


def test_semantic_handoff_projection_marks_fallback_only_evidence_insufficient() -> None:
    projection = semantic_handoff_projection(
        {
            "checks": {
                "source_evidence": {
                    "source_lanes": ["generic_low_confidence", "policy_fallback"],
                    "semantic_runtime_rows": 0,
                }
            }
        }
    )

    assert projection["semantic_handoff_status"] == "insufficient_evidence"
    assert "semantic_runtime_evidence_missing" in projection[
        "semantic_handoff_reasons"
    ]


def test_semantic_handoff_projection_closes_with_semantic_runtime_evidence() -> None:
    assert semantic_handoff_projection(
        {
            "checks": {
                "source_evidence": {
                    "source_lanes": ["deck_matched_public_guide"],
                    "semantic_runtime_rows": 1,
                }
            }
        }
    ) == {
        "semantic_handoff_status": "closed",
        "semantic_handoff_reasons": [],
    }


def test_config_quality_missing_operator_has_insufficient_semantic_handoff(
    tmp_path: Path,
) -> None:
    report = build_config_quality_report(tmp_path / "missing-package")

    assert report["semantic_handoff_status"] == "insufficient_evidence"
    assert "operator_summary_missing_or_invalid" in report[
        "semantic_handoff_reasons"
    ]


def test_config_quality_projects_suppressed_semantic_surface_attention(
    tmp_path: Path,
) -> None:
    package = minimal_clean_package(tmp_path)
    card_behavior_path = package / "reports" / "card_behavior_plan_report.json"
    card_behavior = json.loads(card_behavior_path.read_text(encoding="utf-8"))
    card_behavior["suppressed"] = [
        {
            "claim_id": "claim_patches_trigger",
            "claim_kind": "mechanic_usage",
            "cards": ["CFM_637"],
            "reason": "semantic_surface_not_expressible",
        },
        {
            "claim_id": "claim_target_scope",
            "claim_kind": "targeting_rule",
            "cards": ["NX2_019"],
            "reason": "missing_target_scope",
        },
    ]
    write_json(card_behavior_path, card_behavior)

    report = build_config_quality_report(package)

    assert report["checks"]["visionai_semantic_surface"]["attention"] == [
        "missing_target_scope",
        "semantic_surface_not_expressible",
    ]
    assert report["semantic_handoff_status"] == "attention"
    assert report["semantic_handoff_reasons"] == [
        "missing_target_scope",
        "semantic_surface_not_expressible",
    ]


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
            "source_to_runtime_explainability_summary": {
                "non_blocking": True,
                "cards_total": 1,
                "claims_total": 1,
                "runtime_lowered_claims": 1,
                "closure_lane_counts": {"source_backed_runtime_lowered": 1},
                "cards_with_closure": 1,
                "cards_missing_closure": 0,
                "closure_schema_current": True,
                "next_report_to_open": "reports/source_to_runtime_explainability.json",
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
                    "condition": "*",
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
            "summary": {
                "cards_total": 1,
                "claims_total": 1,
                "runtime_lowered_claims": 1,
                "next_report_to_open": "reports/source_to_runtime_explainability.json",
            },
            "claim_rows": [
                {
                    "claim_id": "claim_mind_sear_effect",
                    "claim_kind": "targeting_rule",
                    "target_scope": "enemy_minion",
                    "builder_or_router_decision": "emitted",
                    "emitted_runtime_files": ["NX2_019.json"],
                    "first_missing_link": None,
                }
            ],
            "card_rows": [
                {
                    "card_id": "NX2_019",
                    "first_missing_link": None,
                    "source_lane": "runtime_lowered",
                    "emitted_runtime_files": ["NX2_019.json"],
                    "runtime_surfaces": ["cardid"],
                    "closure": {
                        "lane": "source_backed_runtime_lowered",
                        "runtime_surfaces": ["NX2_019.json"],
                        "default_only_risk": False,
                    },
                    "evidence_chain": [
                        {
                            "claim_id": "claim_mind_sear_effect",
                            "claim_kind": "targeting_rule",
                            "target_scope": "enemy_minion",
                            "source_lane": "runtime_lowered",
                            "source_type": "deck_matched_public_guide",
                            "runtime_files": ["NX2_019.json"],
                            "resolution_reason": "emitted",
                        }
                    ],
                }
            ],
        },
    )
    write_json(
        package / "reports" / "guide_claim_bundle.json",
        {
            "claims": [
                {
                    "claim_id": "claim_mind_sear_effect",
                    "claim_kind": "targeting_rule",
                    "cards": ["NX2_019"],
                    "stance": "prefer_enemy_minion",
                    "target_scope": "enemy_minion",
                    "runtime_block": "BeforeBattlecryTargetBonus",
                    "source_claim_ids": ["claim_mind_sear_effect"],
                }
            ],
            "unsupported_claims": [],
            "source_evidence_index": [],
        },
    )
    write_json(
        package / "reports" / "gameplan_contract.json",
        {
            "cards": {
                "NX2_019": {
                    "card_id": "NX2_019",
                    "roles": ["prefer_enemy_minion"],
                    "semantic_families": ["targeting_rule"],
                    "source_claim_ids": ["claim_mind_sear_effect"],
                }
            },
            "card_role_map": [
                {
                    "card_id": "NX2_019",
                    "roles": ["prefer_enemy_minion"],
                    "semantic_families": ["targeting_rule"],
                    "source_claim_ids": ["claim_mind_sear_effect"],
                }
            ],
            "source_claims": [
                {
                    "claim_id": "claim_mind_sear_effect",
                    "claim_kind": "targeting_rule",
                    "cards": ["NX2_019"],
                    "stance": "prefer_enemy_minion",
                    "target_scope": "enemy_minion",
                    "runtime_block": "BeforeBattlecryTargetBonus",
                    "source_claim_ids": ["claim_mind_sear_effect"],
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
    write_json(
        package / "reports" / "surface_intent.json",
        {
            "rows": [
                {
                    "rule_id": "globalvalues_full_key_profile",
                    "card_id": None,
                    "surface": "GlobalValues.json",
                    "intent": "profile_and_overlay_full_global_values",
                    "source_claim_ids": ["claim_mind_sear_effect"],
                },
                {
                    "rule_id": "NX2_019_card_behavior",
                    "card_id": "NX2_019",
                    "surface": "NX2_019.json",
                    "surface_family": "CARDID.json",
                    "intent": "conditional_minion_death_burn",
                    "intent_source": "card_intent_taxonomy",
                    "source_claim_ids": ["claim_mind_sear_effect"],
                },
            ],
            "required_surfaces": [
                "GlobalValues.json",
                "Mulligan.json",
                "NX2_019.json",
            ],
            "optional_surfaces": [],
            "minimum_required_runtime_surfaces": [
                "GlobalValues.json",
                "Mulligan.json",
            ],
            "rich_optional_runtime_surfaces": ["NX2_019.json"],
            "surface_count": 3,
        },
    )
    return package


def test_quality_contract_flags_unreported_physical_cardid_row(tmp_path):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "CustomConfig" / DECK_SLUG / "EX1_001.json",
        {
            "GameCardId": "EX1_001",
            "ConfigComment": "Fixture: generated behavior for EX1_001",
            "InHandPlayPriority": {
                "values": [
                    {
                        "comment": "Fixture: EX1_001_unreported",
                        "condition": "*",
                        "value": "5",
                    }
                ]
            },
        },
    )

    report = build_config_quality_report(package)
    check = report["checks"]["runtime_row_trace_inventory"]

    assert check["status"] == "attention"
    assert check["unreported_runtime_rows"][0]["card_id"] == "EX1_001"
    assert (
        check["unreported_runtime_rows"][0]["behavior_block"]
        == "InHandPlayPriority"
    )


def test_quality_contract_flags_reported_cardid_row_missing_runtime(tmp_path):
    package = minimal_clean_package(tmp_path)
    card_behavior_path = package / "reports" / "card_behavior_plan_report.json"
    card_behavior = json.loads(card_behavior_path.read_text(encoding="utf-8"))
    card_behavior["rows"].append(
        {
            "card_id": "EX1_002",
            "surface_family": "CARDID.json",
            "behavior_block": "BeforePlayCardBonus",
            "condition": "*",
            "value": "9",
            "meaningful_runtime_surface": True,
            "semantic_score": {
                "band": "high",
                "reason": "direct_enemy_hero_burn",
                "profile": "semantic_intent",
                "matched_signals": ["enemy_hero_targeting", "damage"],
            },
        }
    )
    write_json(card_behavior_path, card_behavior)

    report = build_config_quality_report(package)
    check = report["checks"]["runtime_row_trace_inventory"]

    assert check["status"] == "attention"
    assert check["reported_rows_missing_runtime"] == [
        {
            "card_id": "EX1_002",
            "behavior_block": "BeforePlayCardBonus",
            "condition": "*",
            "value": "9",
        }
    ]


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
    assert report["checks"]["mechanic_runtime_discipline"]["status"] == "clean"
    assert _compact_config_quality_summary(report)[
        "mechanic_runtime_discipline_status"
    ] == "clean"
    assert report["checks"]["trace_completeness"] == {
        "runtime_rows_missing_trace": [],
        "traced_card_ids": ["NX2_019"],
        "runtime_card_ids": ["NX2_019"],
    }
    assert report["checks"]["semantic_intent_coverage"] == {
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "status": "clean",
        "meaningful_cardid_runtime_rows": 1,
        "taxonomy_reason_counts": {"conditional_minion_death_burn": 1},
        "runtime_rows_missing_trace": [],
        "semantic_score_missing_rows": [],
        "semantic_default_rows": [],
        "report_only_runtime_rows": [],
        "warning_only_card_count": 0,
        "warning_only_mechanics": [],
        "attention": [],
        "first_attention": None,
    }
    assert report["checks"]["surface_intent_projection"] == {
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "present": True,
        "status": "clean",
        "surface_count": 3,
        "row_count": 2,
        "required_surfaces": [
            "GlobalValues.json",
            "Mulligan.json",
            "NX2_019.json",
        ],
        "optional_surfaces": [],
        "rich_optional_runtime_surfaces": ["NX2_019.json"],
        "fallback_intent_rows": [],
        "legacy_policy_surface_rows": [],
        "malformed_rows": [],
        "attention": [],
        "first_attention": None,
    }
    assert report["checks"]["visionai_semantic_surface"] == {
        "status": "clean",
        "non_targeted_battlecry_target_rows": [],
        "effect_only_body_rows": [],
        "unsupported_report_only_runtime_rows": [],
        "semantic_default_runtime_rows": [],
        "attention": [],
    }
    assert report["checks"]["closure_freshness"] == {
        "present": True,
        "closure_schema_current": True,
        "cards_missing_closure": 0,
        "cards_total": 1,
        "cards_with_closure": 1,
    }


def test_config_quality_summarizes_semantic_taxonomy_reasons(tmp_path: Path):
    package = minimal_clean_package(tmp_path)
    card_behavior = json.loads(
        (package / "reports" / "card_behavior_plan_report.json").read_text(
            encoding="utf-8"
        )
    )
    card_behavior["rows"].append(
        {
            "card_id": "LOC_001",
            "surface_family": "CARDID.json",
            "behavior_block": "BeforePlayCardBonus",
            "value": "8",
            "meaningful_runtime_surface": True,
            "semantic_score": {
                "band": "medium",
                "reason": "location_tempo",
                "profile": "semantic_intent",
                "matched_signals": ["location"],
            },
        }
    )
    write_json(package / "reports" / "card_behavior_plan_report.json", card_behavior)

    report = build_config_quality_report(package)

    semantic = report["checks"]["semantic_intent_coverage"]
    assert semantic["taxonomy_reason_counts"] == {
        "conditional_minion_death_burn": 1,
        "location_tempo": 1,
    }
    assert semantic["authority"] == "diagnostic_only"
    assert semantic["apply_blocking"] is False
    assert report["apply_blocking"] is False


def test_config_quality_flags_non_targeted_battlecry_target_runtime_row(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    card_behavior = json.loads(
        (package / "reports" / "card_behavior_plan_report.json").read_text(
            encoding="utf-8"
        )
    )
    card_behavior["rows"][0].update(
        {
            "claim_id": "claim_generic_battlecry",
            "source_claim_ids": ["claim_generic_battlecry"],
            "roles": ["battlecry"],
            "mechanic": "battlecry",
        }
    )
    write_json(package / "reports" / "card_behavior_plan_report.json", card_behavior)
    generic_claim = {
        "claim_id": "claim_generic_battlecry",
        "claim_kind": "mechanic_usage",
        "cards": ["NX2_019"],
        "mechanic": "battlecry",
        "stance": "battlecry",
        "source_claim_ids": ["claim_generic_battlecry"],
    }
    write_json(
        package / "reports" / "guide_claim_bundle.json",
        {"claims": [generic_claim], "unsupported_claims": []},
    )
    write_json(
        package / "reports" / "gameplan_contract.json",
        {
            "cards": {
                "NX2_019": {
                    "card_id": "NX2_019",
                    "roles": ["battlecry"],
                    "semantic_families": ["battlecry"],
                    "source_claim_ids": ["claim_generic_battlecry"],
                }
            },
            "source_claims": [generic_claim],
        },
    )

    report = build_config_quality_report(package)

    check = report["checks"]["visionai_semantic_surface"]
    assert check["status"] == "failed"
    assert check["non_targeted_battlecry_target_rows"] == [
        {
            "card_id": "NX2_019",
            "behavior_block": "BeforeBattlecryTargetBonus",
            "value": "10",
        }
    ]
    assert {
        "check": "visionai_semantic_surface_failed",
        "value": {
            "non_targeted_battlecry_target_rows": 1,
            "effect_only_body_rows": 0,
            "unsupported_report_only_runtime_rows": 0,
            "semantic_default_runtime_rows": 0,
        },
    } in report["problems"]
    assert report["apply_blocking"] is False


def test_config_quality_flags_effect_only_start_game_body_runtime_rows(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    card_behavior = json.loads(
        (package / "reports" / "card_behavior_plan_report.json").read_text(
            encoding="utf-8"
        )
    )
    card_behavior["rows"].extend(
        [
            {
                "card_id": "SW_448",
                "surface_family": "CARDID.json",
                "behavior_block": "InHandPlayPriority",
                "value": "7",
                "meaningful_runtime_surface": True,
                "source_claim_ids": ["claim_darkbishop_effect"],
                "semantic_score": {
                    "band": "medium",
                    "reason": "source_backed_darkbishop_effect",
                    "profile": "semantic_intent",
                },
            },
            {
                "card_id": "SW_448",
                "surface_family": "CARDID.json",
                "behavior_block": "BeforePlayCardBonus",
                "value": "8",
                "meaningful_runtime_surface": True,
                "roles": ["pressure"],
                "source_claim_ids": [],
                "semantic_score": {
                    "band": "medium",
                    "reason": "pressure_play_bonus",
                    "profile": "semantic_intent",
                },
            },
        ]
    )
    write_json(package / "reports" / "card_behavior_plan_report.json", card_behavior)
    write_json(
        package / "CustomConfig" / DECK_SLUG / "SW_448.json",
        {
            "GameCardId": "SW_448",
            "InHandPlayPriority": {
                "values": [
                    {
                        "comment": "generic hand priority",
                        "condition": "*",
                        "value": "7",
                    }
                ]
            },
            "BeforePlayCardBonus": {
                "values": [
                    {
                        "comment": "generic body timing",
                        "condition": "*",
                        "value": "8",
                    }
                ]
            },
        },
    )
    write_json(
        package / "reports" / "gameplan_contract.json",
        {
            "cards": {
                "SW_448": {
                    "card_id": "SW_448",
                    "roles": [
                        "deckbuilding_modifier",
                        "hero_power_transform",
                        "passive_start_effect",
                        "shadowform",
                        "start_of_game_keyword",
                    ],
                    "semantic_families": ["start_of_game", "hero_power_transform"],
                    "source_claim_ids": ["claim_darkbishop_effect"],
                }
            }
        },
    )

    report = build_config_quality_report(package)

    check = report["checks"]["visionai_semantic_surface"]
    assert check["status"] == "failed"
    assert check["effect_only_body_rows"] == [
        {
            "card_id": "SW_448",
            "behavior_block": "BeforePlayCardBonus",
            "value": "8",
        },
        {
            "card_id": "SW_448",
            "behavior_block": "InHandPlayPriority",
            "value": "7",
        },
    ]
    assert report["apply_blocking"] is False


def test_config_quality_flags_report_only_location_activation_runtime_row(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "reports" / "card_behavior_plan_report.json",
        {
            "rows": [
                {
                    "card_id": "REV_290",
                    "surface_family": "CARDID.json",
                    "behavior_block": "BeforePlayCardBonus",
                    "value": "6",
                    "meaningful_runtime_surface": True,
                    "mechanic": "location_activation",
                    "semantic_score": {
                        "band": "medium",
                        "reason": "location_activation",
                        "profile": "semantic_intent",
                    },
                }
            ]
        },
    )
    write_json(
        package / "CustomConfig" / DECK_SLUG / "REV_290.json",
        {
            "GameCardId": "REV_290",
            "BeforePlayCardBonus": {
                "values": [
                    {
                        "comment": "unsupported location activation",
                        "condition": "*",
                        "value": "6",
                    }
                ]
            },
        },
    )

    report = build_config_quality_report(package)

    check = report["checks"]["visionai_semantic_surface"]
    assert check["status"] == "failed"
    assert check["unsupported_report_only_runtime_rows"] == [
        {
            "card_id": "REV_290",
            "mechanic": "location_activation",
            "behavior_block": "BeforePlayCardBonus",
            "value": "6",
        }
    ]
    assert report["apply_blocking"] is False


def test_config_quality_flags_report_only_location_activation_from_roles(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "reports" / "card_behavior_plan_report.json",
        {
            "rows": [
                {
                    "card_id": "REV_290",
                    "surface_family": "CARDID.json",
                    "behavior_block": "BeforePlayCardBonus",
                    "value": "6",
                    "meaningful_runtime_surface": True,
                    "roles": ["location_activation"],
                    "semantic_score": {
                        "band": "medium",
                        "reason": "location_activation",
                        "profile": "semantic_intent",
                    },
                }
            ]
        },
    )
    write_json(
        package / "CustomConfig" / DECK_SLUG / "REV_290.json",
        {
            "GameCardId": "REV_290",
            "BeforePlayCardBonus": {
                "values": [
                    {
                        "comment": "unsupported role-only location activation",
                        "condition": "*",
                        "value": "6",
                    }
                ]
            },
        },
    )

    report = build_config_quality_report(package)

    expected_row = {
        "card_id": "REV_290",
        "mechanic": "location_activation",
        "behavior_block": "BeforePlayCardBonus",
        "value": "6",
    }
    assert report["checks"]["mechanic_runtime_discipline"][
        "report_only_runtime_rows"
    ] == [expected_row]
    check = report["checks"]["visionai_semantic_surface"]
    assert check["status"] == "failed"
    assert check["unsupported_report_only_runtime_rows"] == [expected_row]
    assert {
        "check": "visionai_semantic_surface_failed",
        "value": {
            "non_targeted_battlecry_target_rows": 0,
            "effect_only_body_rows": 0,
            "unsupported_report_only_runtime_rows": 1,
            "semantic_default_runtime_rows": 0,
        },
    } in report["problems"]
    assert report["apply_blocking"] is False


def test_config_quality_surfaces_surface_intent_attention_without_new_problem(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "reports" / "surface_intent.json",
        {
            "rows": [
                {
                    "rule_id": "GENERIC_001_card_behavior",
                    "card_id": "GENERIC_001",
                    "surface": "GENERIC_001.json",
                    "surface_family": "CARDID.json",
                    "intent": "aggressive_card_behavior",
                    "intent_source": "fallback",
                    "source_claim_ids": [],
                },
                {
                    "rule_id": "legacy_presume",
                    "card_id": None,
                    "surface": "Presume.json",
                    "intent": "legacy_policy_surface",
                    "source_claim_ids": [],
                },
            ],
            "required_surfaces": [
                "GlobalValues.json",
                "Mulligan.json",
                "GENERIC_001.json",
            ],
            "optional_surfaces": ["Presume.json"],
            "minimum_required_runtime_surfaces": [
                "GlobalValues.json",
                "Mulligan.json",
            ],
            "rich_optional_runtime_surfaces": ["GENERIC_001.json"],
            "surface_count": 4,
        },
    )

    report = build_config_quality_report(package)

    surface_intent = report["checks"]["surface_intent_projection"]
    assert surface_intent["authority"] == "diagnostic_only"
    assert surface_intent["apply_blocking"] is False
    assert surface_intent["runtime_write_performed"] is False
    assert surface_intent["status"] == "attention"
    assert surface_intent["first_attention"] == "surface_intent_fallback_visible"
    assert surface_intent["fallback_intent_rows"] == [
        {
            "card_id": "GENERIC_001",
            "surface": "GENERIC_001.json",
            "intent": "aggressive_card_behavior",
        }
    ]
    assert surface_intent["legacy_policy_surface_rows"] == [
        {
            "card_id": "",
            "surface": "Presume.json",
            "intent": "legacy_policy_surface",
        }
    ]
    assert report["apply_blocking"] is False
    assert not any(
        problem["check"].startswith("surface_intent_")
        for problem in report["problems"]
    )
    compact = _compact_config_quality_summary(report)
    assert compact["surface_intent_status"] == "attention"
    assert compact["surface_intent_present"] is True
    assert compact["surface_intent_surface_count"] == 4
    assert compact["surface_intent_fallback_intent_rows"] == 1
    assert compact["surface_intent_legacy_policy_surface_rows"] == ["Presume.json"]
    assert compact["surface_intent_first_attention"] == (
        "surface_intent_fallback_visible"
    )


def test_config_quality_missing_surface_intent_is_non_blocking_diagnostic(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    (package / "reports" / "surface_intent.json").unlink()

    report = build_config_quality_report(package)

    assert report["apply_blocking"] is False
    assert report["problems"] == []
    assert report["checks"]["surface_intent_projection"] == {
        "authority": "diagnostic_only",
        "apply_blocking": False,
        "runtime_write_performed": False,
        "present": False,
        "status": "missing",
        "surface_count": 0,
        "row_count": 0,
        "required_surfaces": [],
        "optional_surfaces": [],
        "rich_optional_runtime_surfaces": [],
        "fallback_intent_rows": [],
        "legacy_policy_surface_rows": [],
        "attention": [],
        "first_attention": None,
    }


def test_config_quality_flags_report_only_mechanic_runtime_emission(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "reports" / "card_behavior_plan_report.json",
        {
            "rows": [
                {
                    "card_id": "TRADEABLE_001",
                    "surface_family": "CARDID.json",
                    "behavior_block": "BeforePlayCardBonus",
                    "value": "6",
                    "meaningful_runtime_surface": True,
                    "mechanic": "tradeable",
                    "semantic_score": {
                        "band": "default",
                        "reason": "semantic_default",
                        "profile": "semantic_intent",
                    },
                }
            ]
        },
    )
    write_json(
        package / "reports" / "source_to_runtime_explainability.json",
        {
            "default_only_runtime_surfaces": [],
            "summary": {
                "cards_total": 1,
                "claims_total": 1,
                "runtime_lowered_claims": 1,
                "next_report_to_open": "reports/source_to_runtime_explainability.json",
            },
            "claim_rows": [
                {
                    "claim_id": "claim_tradeable",
                    "claim_kind": "mechanic_usage",
                    "builder_or_router_decision": "emitted",
                    "emitted_runtime_files": ["TRADEABLE_001.json"],
                    "first_missing_link": None,
                }
            ],
            "card_rows": [
                {
                    "card_id": "TRADEABLE_001",
                    "source_lane": "runtime_lowered",
                    "emitted_runtime_files": ["TRADEABLE_001.json"],
                    "closure": {
                        "lane": "source_backed_runtime_lowered",
                        "runtime_surfaces": ["TRADEABLE_001.json"],
                    },
                    "evidence_chain": [
                        {
                            "claim_id": "claim_tradeable",
                            "claim_kind": "mechanic_usage",
                            "source_lane": "runtime_lowered",
                            "runtime_files": ["TRADEABLE_001.json"],
                            "resolution_reason": "emitted",
                        }
                    ],
                }
            ],
        },
    )
    write_json(
        package / "CustomConfig" / DECK_SLUG / "TRADEABLE_001.json",
        {
            "GameCardId": "TRADEABLE_001",
            "BeforePlayCardBonus": {
                "values": [
                    {
                        "comment": "should not lower tradeable generically",
                        "condition": "*",
                        "value": "6",
                    }
                ]
            },
        },
    )

    report = build_config_quality_report(package)

    assert report["status"] == "attention"
    assert report["checks"]["mechanic_runtime_discipline"]["status"] == "attention"
    assert _compact_config_quality_summary(report)[
        "mechanic_runtime_discipline_status"
    ] == "attention"
    assert report["checks"]["mechanic_runtime_discipline"][
        "report_only_runtime_rows"
    ] == [
        {
            "card_id": "TRADEABLE_001",
            "mechanic": "tradeable",
            "behavior_block": "BeforePlayCardBonus",
            "value": "6",
        }
    ]
    assert {
        "check": "report_only_mechanic_emitted_runtime",
        "value": [
            {
                "card_id": "TRADEABLE_001",
                "mechanic": "tradeable",
                "behavior_block": "BeforePlayCardBonus",
                "value": "6",
            }
        ],
    } in report["problems"]
    semantic_intent = report["checks"]["semantic_intent_coverage"]

    assert semantic_intent["status"] == "attention"
    assert {
        "check": "report_only_mechanic_emitted_runtime",
        "count": 1,
    } in semantic_intent["attention"]
    assert semantic_intent["report_only_runtime_rows"] == [
        {
            "card_id": "TRADEABLE_001",
            "mechanic": "tradeable",
            "behavior_block": "BeforePlayCardBonus",
            "value": "6",
        }
    ]
    assert report["apply_blocking"] is False


def test_config_quality_flags_stray_cardid_runtime_file_without_report_trace(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "CustomConfig" / DECK_SLUG / "STRAY_001.json",
        {
            "GameCardId": "STRAY_001",
            "BeforePlayCardBonus": {
                "values": [
                    {
                        "comment": "unexpected stale card runtime",
                        "condition": "*",
                        "value": "6",
                    }
                ]
            },
        },
    )

    report = build_config_quality_report(package)

    assert report["status"] == "attention"
    assert report["checks"]["runtime_json"]["stray_cardid_files"] == [
        "CustomConfig/shadowpriest/STRAY_001.json"
    ]
    assert {
        "check": "stray_cardid_runtime_files",
        "value": ["CustomConfig/shadowpriest/STRAY_001.json"],
    } in report["problems"]
    assert report["apply_blocking"] is False


def test_config_quality_flags_stray_cardid_runtime_file_by_filename(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "CustomConfig" / DECK_SLUG / "STRAY_001.json",
        {
            "GameCardId": "NX2_019",
            "BeforePlayCardBonus": {
                "values": [
                    {
                        "comment": "stale filename with valid payload card id",
                        "condition": "*",
                        "value": "6",
                    }
                ]
            },
        },
    )

    report = build_config_quality_report(package)

    assert report["status"] == "attention"
    assert report["checks"]["runtime_json"]["stray_cardid_files"] == [
        "CustomConfig/shadowpriest/STRAY_001.json"
    ]
    assert {
        "check": "stray_cardid_runtime_files",
        "value": ["CustomConfig/shadowpriest/STRAY_001.json"],
    } in report["problems"]
    assert report["apply_blocking"] is False


def test_config_quality_flags_deck_identity_runtime_row_without_reported_row(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "reports" / "deck_identity.json",
        {
            "deck_name": "ShadowPriest",
            "cards": [{"card_id": "NX2_019"}, {"card_id": "TOY_381"}],
        },
    )
    explainability = json.loads(
        (package / "reports" / "source_to_runtime_explainability.json").read_text(
            encoding="utf-8"
        )
    )
    explainability["card_rows"].append(
        {
            "card_id": "TOY_381",
            "first_missing_link": "claim_kind_runtime_surface",
            "source_lane": "report_only",
            "emitted_runtime_files": [],
            "runtime_surfaces": [],
            "closure": {
                "lane": "report_only",
                "runtime_surfaces": [],
                "default_only_risk": False,
            },
            "evidence_chain": [],
        }
    )
    write_json(
        package / "reports" / "source_to_runtime_explainability.json",
        explainability,
    )
    write_json(
        package / "CustomConfig" / DECK_SLUG / "TOY_381.json",
        {
            "GameCardId": "TOY_381",
            "BeforePlayCardBonus": {
                "values": [
                    {
                        "comment": "deck card runtime row emitted by rich output",
                        "condition": "*",
                        "value": "6",
                    }
                ]
            },
        },
    )

    report = build_config_quality_report(package)

    assert report["checks"]["runtime_json"]["stray_cardid_files"] == []
    assert report["status"] == "attention"
    assert report["checks"]["runtime_row_trace_inventory"][
        "unreported_runtime_rows"
    ] == [
        {
            "card_id": "TOY_381",
            "behavior_block": "BeforePlayCardBonus",
            "condition": "*",
            "value": "6",
        }
    ]
    assert not any(
        problem["check"] == "stray_cardid_runtime_files"
        for problem in report["problems"]
    )


def test_config_quality_flags_stale_source_to_runtime_closure_summary(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    operator = json.loads(
        (package / "reports" / "operator_summary.json").read_text(encoding="utf-8")
    )
    operator["source_to_runtime_explainability_summary"] = {
        "non_blocking": True,
        "cards_total": 2,
        "cards_with_closure": 1,
        "cards_missing_closure": 1,
        "closure_schema_current": False,
        "next_report_to_open": "reports/source_to_runtime_explainability.json",
    }
    write_json(package / "reports" / "operator_summary.json", operator)

    report = build_config_quality_report(package)

    assert report["status"] == "attention"
    assert report["checks"]["closure_freshness"] == {
        "present": True,
        "closure_schema_current": False,
        "cards_missing_closure": 1,
        "cards_total": 2,
        "cards_with_closure": 1,
    }
    assert {
        "check": "source_to_runtime_closure_not_current",
        "value": False,
    } in report["problems"]
    assert {
        "check": "source_to_runtime_closure_rows_missing",
        "value": 1,
    } in report["problems"]
    assert report["apply_blocking"] is False


def test_config_quality_flags_missing_source_to_runtime_closure_summary(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    operator = json.loads(
        (package / "reports" / "operator_summary.json").read_text(encoding="utf-8")
    )
    operator.pop("source_to_runtime_explainability_summary")
    write_json(package / "reports" / "operator_summary.json", operator)

    report = build_config_quality_report(package)

    assert report["status"] == "attention"
    assert report["checks"]["closure_freshness"] == {
        "present": False,
        "closure_schema_current": False,
        "cards_missing_closure": 0,
        "cards_total": 0,
        "cards_with_closure": 0,
    }
    assert {
        "check": "source_to_runtime_closure_summary_missing",
        "value": "operator_summary.json",
    } in report["problems"]
    assert report["apply_blocking"] is False


def test_config_quality_flags_cardid_runtime_rows_without_source_trace(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "reports" / "source_to_runtime_explainability.json",
        {
            "default_only_runtime_surfaces": [],
            "summary": {
                "cards_total": 1,
                "claims_total": 0,
                "runtime_lowered_claims": 0,
                "next_report_to_open": "reports/source_to_runtime_explainability.json",
            },
            "claim_rows": [],
            "card_rows": [
                {
                    "card_id": "NX2_019",
                    "first_missing_link": None,
                    "source_lane": "report_only",
                    "emitted_runtime_files": [],
                    "runtime_surfaces": [],
                    "closure": {
                        "lane": "baseline_only_visible",
                        "runtime_surfaces": [],
                        "default_only_risk": True,
                    },
                    "evidence_chain": [],
                }
            ],
        },
    )

    report = build_config_quality_report(package)

    assert report["status"] == "attention"
    assert report["checks"]["trace_completeness"]["runtime_rows_missing_trace"] == [
        {
            "card_id": "NX2_019",
            "behavior_block": "BeforeBattlecryTargetBonus",
            "value": "10",
        }
    ]
    assert {
        "check": "card_behavior_runtime_row_missing_trace",
        "value": [
            {
                "card_id": "NX2_019",
                "behavior_block": "BeforeBattlecryTargetBonus",
                "value": "10",
            }
        ],
    } in report["problems"]
    semantic_intent = report["checks"]["semantic_intent_coverage"]

    assert semantic_intent["status"] == "attention"
    assert semantic_intent["authority"] == "diagnostic_only"
    assert semantic_intent["apply_blocking"] is False
    assert semantic_intent["runtime_write_performed"] is False
    assert semantic_intent["first_attention"] == "card_behavior_runtime_row_missing_trace"
    assert {
        "check": "card_behavior_runtime_row_missing_trace",
        "count": 1,
    } in semantic_intent["attention"]
    assert report["apply_blocking"] is False


def test_config_quality_flags_same_card_runtime_row_without_claim_trace(
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
                    "claim_id": "claim_mind_sear_targeting",
                    "source_claim_ids": ["claim_mind_sear_targeting"],
                    "semantic_score": {
                        "band": "high",
                        "reason": "conditional_minion_death_burn",
                        "profile": "semantic_intent",
                    },
                },
                {
                    "card_id": "NX2_019",
                    "surface_family": "CARDID.json",
                    "behavior_block": "BeforePlayCardBonus",
                    "value": "8",
                    "meaningful_runtime_surface": True,
                    "claim_id": "claim_mind_sear_play_bonus",
                    "source_claim_ids": ["claim_mind_sear_play_bonus"],
                    "semantic_score": {
                        "band": "high",
                        "reason": "source_backed_play_timing",
                        "profile": "semantic_intent",
                    },
                },
            ]
        },
    )
    write_json(
        package / "CustomConfig" / DECK_SLUG / "NX2_019.json",
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
            "BeforePlayCardBonus": {
                "values": [
                    {
                        "comment": "ShadowPriest: NX2_019_play_bonus",
                        "condition": "*",
                        "value": "8",
                    }
                ]
            },
        },
    )
    write_json(
        package / "reports" / "source_to_runtime_explainability.json",
        {
            "default_only_runtime_surfaces": [],
            "summary": {
                "cards_total": 1,
                "claims_total": 1,
                "runtime_lowered_claims": 1,
                "next_report_to_open": "reports/source_to_runtime_explainability.json",
            },
            "claim_rows": [
                {
                    "claim_id": "claim_mind_sear_targeting",
                    "claim_kind": "targeting_rule",
                    "builder_or_router_decision": "emitted",
                    "emitted_runtime_files": ["NX2_019.json"],
                    "first_missing_link": None,
                }
            ],
            "card_rows": [
                {
                    "card_id": "NX2_019",
                    "first_missing_link": None,
                    "source_lane": "runtime_lowered",
                    "emitted_runtime_files": ["NX2_019.json"],
                    "runtime_surfaces": ["cardid"],
                    "closure": {
                        "lane": "source_backed_runtime_lowered",
                        "runtime_surfaces": ["NX2_019.json"],
                        "default_only_risk": False,
                    },
                    "evidence_chain": [
                        {
                            "claim_id": "claim_mind_sear_targeting",
                            "claim_kind": "targeting_rule",
                            "source_lane": "runtime_lowered",
                            "source_type": "deck_matched_public_guide",
                            "runtime_files": ["NX2_019.json"],
                            "resolution_reason": "emitted",
                        }
                    ],
                }
            ],
        },
    )

    report = build_config_quality_report(package)

    assert report["status"] == "attention"
    assert report["checks"]["trace_completeness"]["runtime_rows_missing_trace"] == [
        {
            "card_id": "NX2_019",
            "behavior_block": "BeforePlayCardBonus",
            "value": "8",
        }
    ]
    assert report["checks"]["trace_completeness"]["traced_card_ids"] == ["NX2_019"]
    assert report["checks"]["trace_completeness"]["runtime_card_ids"] == ["NX2_019"]
    assert {
        "check": "card_behavior_runtime_row_missing_trace",
        "value": [
            {
                "card_id": "NX2_019",
                "behavior_block": "BeforePlayCardBonus",
                "value": "8",
            }
        ],
    } in report["problems"]
    assert report["apply_blocking"] is False


def test_config_quality_accepts_official_static_semantics_runtime_trace(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "reports" / "source_to_runtime_explainability.json",
        {
            "default_only_runtime_surfaces": [],
            "summary": {
                "cards_total": 1,
                "claims_total": 1,
                "runtime_lowered_claims": 1,
                "next_report_to_open": "reports/source_to_runtime_explainability.json",
            },
            "claim_rows": [
                {
                    "claim_id": "claim_static_mind_sear",
                    "claim_kind": "targeting_rule",
                    "builder_or_router_decision": "emitted",
                    "emitted_runtime_files": ["NX2_019.json"],
                    "first_missing_link": None,
                }
            ],
            "card_rows": [
                {
                    "card_id": "NX2_019",
                    "first_missing_link": None,
                    "source_lane": "official_static_semantics",
                    "emitted_runtime_files": ["NX2_019.json"],
                    "closure": {
                        "lane": "source_backed_runtime_lowered",
                        "runtime_surfaces": ["NX2_019.json"],
                        "default_only_risk": False,
                    },
                    "evidence_chain": [
                        {
                            "claim_id": "claim_static_mind_sear",
                            "claim_kind": "targeting_rule",
                            "source_lane": "official_static_semantics",
                            "source_type": "official_static_semantics",
                            "runtime_files": ["NX2_019.json"],
                            "resolution_reason": "emitted",
                        }
                    ],
                }
            ],
        },
    )

    report = build_config_quality_report(package)

    assert report["checks"]["trace_completeness"]["runtime_rows_missing_trace"] == []
    assert report["status"] == "clean"


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
    semantic_intent = report["checks"]["semantic_intent_coverage"]

    assert semantic_intent["status"] == "attention"
    assert semantic_intent["first_attention"] == "card_behavior_semantic_score_missing"
    assert {
        "check": "card_behavior_semantic_score_missing",
        "count": 1,
    } in semantic_intent["attention"]
    assert semantic_intent["semantic_score_missing_rows"] == [
        {
            "card_id": "NX2_019",
            "behavior_block": "BeforeBattlecryTargetBonus",
            "value": "10",
        }
    ]


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
    semantic_intent = report["checks"]["semantic_intent_coverage"]

    assert semantic_intent["status"] == "attention"
    assert {
        "check": "card_behavior_semantic_default_visible",
        "count": 1,
    } in semantic_intent["attention"]
    assert semantic_intent["semantic_default_rows"] == [
        {
            "card_id": "CARD_DEFAULT",
            "behavior_block": "BeforePlayCardBonus",
            "value": "6",
            "reason": "semantic_default",
        }
    ]
    assert report["checks"]["visionai_semantic_surface"][
        "semantic_default_runtime_rows"
    ] == []


def test_config_quality_flags_semantic_default_when_card_specific_source_roles_exist(
    tmp_path: Path,
):
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
    write_json(
        package / "CustomConfig" / DECK_SLUG / "CARD_DEFAULT.json",
        {
            "GameCardId": "CARD_DEFAULT",
            "BeforePlayCardBonus": {
                "values": [
                    {
                        "comment": "semantic default despite roles",
                        "condition": "*",
                        "value": "6",
                    }
                ]
            },
        },
    )
    write_json(
        package / "reports" / "gameplan_contract.json",
        {
            "cards": {
                "CARD_DEFAULT": {
                    "card_id": "CARD_DEFAULT",
                    "roles": ["pressure"],
                    "semantic_families": ["damage"],
                    "source_claim_ids": ["claim_card_default"],
                }
            }
        },
    )

    report = build_config_quality_report(package)

    check = report["checks"]["visionai_semantic_surface"]
    assert check["status"] == "failed"
    assert check["semantic_default_runtime_rows"] == [
        {
            "card_id": "CARD_DEFAULT",
            "behavior_block": "BeforePlayCardBonus",
            "value": "6",
            "reason": "semantic_default",
        }
    ]
    assert report["apply_blocking"] is False


def test_config_quality_semantic_intent_coverage_counts_warning_only_semantics(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "reports" / "semantic_enrichment_report.json",
        {
            "cards": [
                {
                    "card_id": "BAR_880",
                    "name": "Tradeable Test Card",
                    "warning_only_mechanics": [
                        "tradeable",
                        "location_activation",
                        "tradeable",
                    ],
                },
                {
                    "card_id": "LOC_001",
                    "name": "Location Test Card",
                    "warning_only_mechanics": ["location_activation"],
                },
            ]
        },
    )

    report = build_config_quality_report(package)

    assert report["status"] == "clean"
    assert report["checks"]["visionai_semantic_surface"][
        "unsupported_report_only_runtime_rows"
    ] == []
    assert report["checks"]["semantic_intent_coverage"]["warning_only_card_count"] == 2
    assert report["checks"]["semantic_intent_coverage"]["warning_only_mechanics"] == [
        "location_activation",
        "tradeable",
    ]
    assert report["checks"]["semantic_intent_coverage"]["first_attention"] is None
    assert report["checks"]["semantic_intent_coverage"]["attention"] == []


@pytest.mark.parametrize("semantic_enrichment_text", ["{ invalid json", "[]"])
def test_config_quality_ignores_malformed_semantic_enrichment(
    tmp_path: Path, semantic_enrichment_text: str
):
    package = minimal_clean_package(tmp_path)
    semantic_enrichment_path = (
        package / "reports" / "semantic_enrichment_report.json"
    )
    semantic_enrichment_path.write_text(semantic_enrichment_text, encoding="utf-8")

    report = build_config_quality_report(package)
    semantic_intent = report["checks"]["semantic_intent_coverage"]

    assert report["status"] == "clean"
    assert report["authority"] == "diagnostic_only"
    assert report["apply_blocking"] is False
    assert report["runtime_write_performed"] is False
    assert semantic_intent["authority"] == "diagnostic_only"
    assert semantic_intent["apply_blocking"] is False
    assert semantic_intent["runtime_write_performed"] is False
    assert semantic_intent["warning_only_card_count"] == 0
    assert semantic_intent["warning_only_mechanics"] == []
    assert report["apply_blocking"] is False


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


def test_config_quality_allows_lean_special_runtime_surfaces(tmp_path: Path):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "CustomConfig" / DECK_SLUG / "GlobalValues.json",
        {
            "GameCardId": "GlobalValues",
            "DeckStrategy": {
                "values": [
                    {
                        "comment": "ShadowPriest: pressure posture",
                        "condition": "*",
                        "value": "9",
                    }
                ]
            },
        },
    )
    write_json(
        package / "CustomConfig" / DECK_SLUG / "Mulligan.json",
        {
            "GameCardId": "Mulligan",
            "Mulligan": {
                "values": [
                    {
                        "comment": "ShadowPriest: keep one-drop pressure",
                        "condition": "*",
                        "mulligan": "CORE_CS2_235",
                        "value": "hold",
                    }
                ]
            },
        },
    )
    write_json(
        package / "CustomConfig" / DECK_SLUG / "Combo.json",
        {
            "GameCardId": "Combo",
            "Combos": [
                {
                    "comment": "ShadowPriest: source-backed sequence",
                    "condition": "*",
                    "combo": ["CARD_A", "CARD_B"],
                    "value": "10",
                }
            ],
        },
    )

    report = build_config_quality_report(package)

    assert report["checks"]["runtime_json"]["metadata_leaks"] == []
    assert report["apply_blocking"] is False


def test_config_quality_flags_special_runtime_surface_metadata_leaks(
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
                        "comment": "bad metadata row",
                        "condition": "*",
                        "mulligan": "CARD_A",
                        "value": "hold",
                        "source_claim_ids": ["claim_a"],
                    }
                ]
            },
        },
    )
    write_json(
        package / "CustomConfig" / DECK_SLUG / "Combo.json",
        {
            "GameCardId": "Combo",
            "Combos": [
                {
                    "comment": "bad combo metadata row",
                    "condition": "*",
                    "combo": ["CARD_A", "CARD_B"],
                    "value": "10",
                    "claim_id": "claim_combo",
                }
            ],
        },
    )

    report = build_config_quality_report(package)

    assert report["status"] == "attention"
    assert report["checks"]["runtime_json"]["metadata_leaks"] == [
        {
            "file": "CustomConfig/shadowpriest/Combo.json",
            "block": "Combos",
            "row_index": 0,
            "extra_keys": ["claim_id"],
        },
        {
            "file": "CustomConfig/shadowpriest/Mulligan.json",
            "block": "Mulligan",
            "row_index": 0,
            "extra_keys": ["source_claim_ids"],
        },
    ]
    assert report["apply_blocking"] is False


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
        "runtime_owner_card_id": "SW_448",
        "explicit_mulligan_keep_evidence_present": False,
    }
    assert {
        "check": "darkbishop_mulligan_keep_without_explicit_evidence",
        "value": {"card_id": "SW_448"},
    } in report["problems"]


def test_config_quality_allows_darkbishop_mulligan_keep_with_explicit_source_evidence(
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
                        "comment": "ShadowPriest: explicit source keeps SW_448",
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
    write_json(
        package / "reports" / "guide_claim_bundle.json",
        {
            "claims": [
                {
                    "claim_id": "claim_keep_darkbishop",
                    "claim_kind": "mulligan_keep",
                    "claim": "Always keep Darkbishop Benedictus in your opening hand.",
                    "evidence_text_short": (
                        "Always keep Darkbishop Benedictus in your opening hand."
                    ),
                    "cards": ["SW_448"],
                    "runtime_lowerable": True,
                    "support_status": "source_backed",
                    "claim_readiness": "guide_backed",
                    "source_family": "guide",
                    "source_lane": "deck_matched_public_guide",
                    "source_type": "public_guide",
                    "source_visibility": "full_text",
                    "source_refs": ["source:1"],
                }
            ],
            "source_evidence_index": [
                {
                    "source_ref": "source:1",
                    "source_url": "https://example.invalid/darkbishop-guide",
                    "source_title": "Darkbishop mulligan guide",
                    "source_family": "guide",
                    "retrieved_at": "2026-07-22",
                    "missing_source_keys": [],
                }
            ],
        },
    )
    write_json(
        package / "reports" / "mulligan_plan_report.json",
        {
            "rules": [
                {
                    "action": "hold",
                    "card": "SW_448",
                    "selector": "SW_448",
                    "selector_cards": ["SW_448"],
                    "claim_id": "claim_keep_darkbishop",
                    "source_claim_ids": ["claim_keep_darkbishop"],
                    "source_type": "source_claim",
                }
            ],
            "suppressed_rules": [],
        },
    )
    write_json(
        package / "reports" / "source_contract_audit.json",
        {
            "claim_rows": [
                {
                    "claim_id": "claim_keep_darkbishop",
                    "claim_kind": "mulligan_keep",
                    "cards": ["SW_448"],
                    "surface_gate_decision": "allowed",
                    "builder_or_router_decision": "emitted",
                    "runtime_surfaces": ["Mulligan.json"],
                    "emitted_runtime_files": ["Mulligan.json"],
                }
            ],
            "claim_lifecycle_rows": [],
        },
    )

    report = build_config_quality_report(package)

    assert report["checks"]["darkbishop_boundary"] == {
        "seen": True,
        "mulligan_keep_present": True,
        "effect_runtime_present": True,
        "runtime_owner_card_id": "SW_448",
        "explicit_mulligan_keep_evidence_present": True,
    }
    assert not any(
        problem["check"] == "darkbishop_mulligan_keep_without_explicit_evidence"
        for problem in report["problems"]
    )


@pytest.mark.parametrize(
    ("claim_fields", "plan_key"),
    [
        (
            {
                "source_type": "policy_backed_autonomous_mulligan",
                "source_lane": "policy_fallback",
                "claim_readiness": "guide_backed",
                "evidence_text_short": "Always keep Darkbishop in the opening hand.",
            },
            "rules",
        ),
        (
            {
                "source_type": "public_guide",
                "source_lane": "policy_fallback",
                "claim_readiness": "guide_backed",
                "evidence_text_short": "Always keep Darkbishop in the opening hand.",
            },
            "rules",
        ),
        (
            {
                "source_type": "default_runtime",
                "source_lane": "default_runtime",
                "claim_readiness": "generic_low_confidence",
                "evidence_text_short": "Default-only generated keep for SW_448.",
            },
            "rules",
        ),
        (
            {
                "source_type": "public_guide",
                "source_lane": "deck_matched_public_guide",
                "claim_readiness": "guide_backed",
                "trust_ceiling": "report_only",
                "evidence_text_short": (
                    "Start of Game: transform the hero power when SW_448 is in the deck."
                ),
            },
            "suppressed_rules",
        ),
    ],
    ids=[
        "policy-backed-autonomous-mulligan",
        "policy-fallback",
        "default-runtime",
        "effect-only-suppressed",
    ],
)
def test_config_quality_rejects_non_source_darkbishop_keep_exceptions(
    tmp_path: Path,
    claim_fields: dict,
    plan_key: str,
) -> None:
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "CustomConfig" / DECK_SLUG / "Mulligan.json",
        {
            "GameCardId": "Mulligan",
            "Mulligan": {
                "values": [
                    {
                        "comment": "invalid Darkbishop keep exception",
                        "condition": "*",
                        "mulligan": "SW_448",
                        "value": "hold",
                    }
                ]
            },
        },
    )
    claim = {
        "claim_id": "claim_keep_darkbishop",
        "claim_kind": "mulligan_keep",
        "cards": ["SW_448"],
        "source_claim_ids": ["claim_keep_darkbishop"],
        "source_refs": ["source:1"],
        **claim_fields,
    }
    write_json(
        package / "reports" / "guide_claim_bundle.json",
        {
            "claims": [claim],
            "source_evidence_index": [
                {
                    "source_ref": "source:1",
                    "source_url": "https://example.invalid/not-a-guide-keep",
                    "source_title": "Non-guide Darkbishop evidence",
                    "source_family": "guide",
                    "retrieved_at": "2026-07-22",
                    "missing_source_keys": [],
                }
            ],
        },
    )
    plan_row = {
        "action": "hold",
        "card": "SW_448",
        "selector": "SW_448",
        "source_claim_ids": ["claim_keep_darkbishop"],
    }
    write_json(
        package / "reports" / "mulligan_plan_report.json",
        {
            "rules": [plan_row] if plan_key == "rules" else [],
            "suppressed_rules": [plan_row] if plan_key == "suppressed_rules" else [],
        },
    )
    write_json(
        package / "reports" / "source_contract_audit.json",
        {
            "claim_rows": [
                {
                    **claim,
                    "builder_or_router_decision": "emitted",
                    "runtime_surfaces": ["Mulligan.json"],
                    "emitted_runtime_files": ["Mulligan.json"],
                }
            ]
        },
    )

    report = build_config_quality_report(package)

    assert report["checks"]["darkbishop_boundary"][
        "explicit_mulligan_keep_evidence_present"
    ] is False
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
    card_behavior = json.loads(
        (package / "reports" / "card_behavior_plan_report.json").read_text(
            encoding="utf-8"
        )
    )
    card_behavior["rows"].append(
        {
            "card_id": "SW_448",
            "surface_family": "CARDID.json",
            "behavior_block": "BeforeUseHeroPowerBonus",
            "condition": "*",
            "value": "10",
            "meaningful_runtime_surface": True,
            "semantic_score": {
                "band": "high",
                "reason": "source_backed_darkbishop_effect",
                "profile": "semantic_intent",
            },
        }
    )
    write_json(package / "reports" / "card_behavior_plan_report.json", card_behavior)
    explainability = json.loads(
        (package / "reports" / "source_to_runtime_explainability.json").read_text(
            encoding="utf-8"
        )
    )
    explainability["claim_rows"].append(
        {
            "claim_id": "claim_darkbishop_effect",
            "claim_kind": "effect_runtime",
            "builder_or_router_decision": "emitted",
            "emitted_runtime_files": ["SW_448.json"],
            "first_missing_link": None,
        }
    )
    explainability["card_rows"].append(
        {
            "card_id": "SW_448",
            "first_missing_link": None,
            "source_lane": "official_static_semantics",
            "emitted_runtime_files": ["SW_448.json"],
            "runtime_surfaces": ["cardid"],
            "closure": {
                "lane": "source_backed_runtime_lowered",
                "runtime_surfaces": ["SW_448.json"],
                "default_only_risk": False,
            },
            "evidence_chain": [
                {
                    "claim_id": "claim_darkbishop_effect",
                    "claim_kind": "effect_runtime",
                    "source_lane": "official_static_semantics",
                    "source_type": "official_static_semantics",
                    "runtime_files": ["SW_448.json"],
                    "resolution_reason": "emitted",
                }
            ],
        }
    )
    write_json(
        package / "reports" / "source_to_runtime_explainability.json",
        explainability,
    )

    report = build_config_quality_report(package)

    assert report["checks"]["darkbishop_boundary"] == {
        "seen": True,
        "mulligan_keep_present": False,
        "effect_runtime_present": True,
        "runtime_owner_card_id": "SW_448",
        "explicit_mulligan_keep_evidence_present": False,
    }
    assert report["problems"] == []


def test_config_quality_exposes_clean_config_intent_self_audit(tmp_path: Path):
    package = minimal_clean_package(tmp_path)

    report = build_config_quality_report(package)

    audit = report["checks"]["config_intent_self_audit"]
    assert audit["schema_version"] == 1
    assert audit["authority"] == "diagnostic_only"
    assert audit["apply_blocking"] is False
    assert audit["runtime_write_performed"] is False
    assert audit["status"] == "clean"
    assert audit["normal_apply_authority"] == "reports/operator_summary.json"
    assert audit["runtime_surface_boundary"] == [
        "GlobalValues.json",
        "Mulligan.json",
        "per-card <CARDID>.json",
        "Combo.json",
    ]
    assert audit["runtime_files_total"] == 3
    assert audit["runtime_files_without_intent"] == []
    assert audit["unsupported_runtime_files"] == []
    assert audit["default_only_runtime_surfaces"] == []
    assert audit["source_status_apply_blocking"] is False
    assert audit["attention"] == []
    assert audit["first_attention"] is None


@pytest.mark.parametrize(
    "file_name",
    ("FutureOptionalSurface.json", "notes.json"),
)
def test_config_quality_runtime_helpers_fail_closed_for_unknown_json_names(
    file_name: str,
):
    assert _file_card_id(file_name) == ""
    with pytest.raises(KeyError):
        _runtime_value_row_keys(file_name)


def test_config_quality_reports_unknown_json_names_as_unsupported(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    unknown_paths = [
        package / "CustomConfig" / DECK_SLUG / "FutureOptionalSurface.json",
        package / "CustomConfig" / DECK_SLUG / "notes.json",
    ]
    for path in unknown_paths:
        write_json(
            path,
            {
                "GameCardId": path.stem,
                "BeforePlayCardBonus": {
                    "values": [{"condition": "*", "value": "6"}]
                },
            },
        )

    report = build_config_quality_report(package)
    audit = report["checks"]["config_intent_self_audit"]

    assert audit["unsupported_runtime_files"] == [
        "CustomConfig/shadowpriest/FutureOptionalSurface.json",
        "CustomConfig/shadowpriest/notes.json",
    ]
    assert {
        "check": "config_intent_unsupported_runtime_files",
        "value": audit["unsupported_runtime_files"],
    } in report["problems"]


def test_config_quality_accepts_surface_intent_for_special_runtime_file_intent(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    operator = json.loads(
        (package / "reports" / "operator_summary.json").read_text(encoding="utf-8")
    )
    operator["surface_status_ledger"] = [
        {"surface": "cardid_behavior", "status": "emitted"},
        {"surface": "mulligan", "status": "emitted"},
        {"surface": "combo", "status": "not_applicable"},
    ]
    write_json(package / "reports" / "operator_summary.json", operator)

    report = build_config_quality_report(package)

    audit = report["checks"]["config_intent_self_audit"]
    assert audit["status"] == "clean"
    assert audit["runtime_files_without_intent"] == []
    assert audit["attention"] == []
    assert report["problems"] == []


def test_config_quality_flags_runtime_file_without_intent_in_self_audit(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "CustomConfig" / DECK_SLUG / "UNTRACED_001.json",
        {
            "GameCardId": "UNTRACED_001",
            "BeforePlayCardBonus": {
                "values": [
                    {
                        "comment": "unexpected untraced runtime file",
                        "condition": "*",
                        "value": "6",
                    }
                ]
            },
        },
    )

    report = build_config_quality_report(package)

    audit = report["checks"]["config_intent_self_audit"]
    assert audit["status"] == "attention"
    assert audit["runtime_files_total"] == 4
    assert audit["runtime_files_without_intent"] == [
        "CustomConfig/shadowpriest/UNTRACED_001.json"
    ]
    assert audit["unsupported_runtime_files"] == []
    assert audit["first_attention"] == "runtime_file_without_intent"
    assert {
        "check": "runtime_file_without_intent",
        "count": 1,
    } in audit["attention"]
    assert {
        "check": "config_intent_runtime_file_without_intent",
        "value": ["CustomConfig/shadowpriest/UNTRACED_001.json"],
    } in report["problems"]
    assert report["apply_blocking"] is False


def test_config_quality_does_not_accept_nested_surface_intent_row_as_globalvalues_intent(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    operator = json.loads(
        (package / "reports" / "operator_summary.json").read_text(encoding="utf-8")
    )
    operator["surface_status_ledger"] = [
        {"surface": "cardid_behavior", "status": "emitted"},
        {"surface": "mulligan", "status": "emitted"},
        {"surface": "combo", "status": "not_applicable"},
    ]
    write_json(package / "reports" / "operator_summary.json", operator)
    write_json(
        package / "reports" / "surface_intent.json",
        {
            "rows": [
                {
                    "rule_id": "globalvalues_full_key_profile",
                    "card_id": None,
                    "surface": "nested/GlobalValues.json",
                    "intent": "bogus",
                },
                {
                    "rule_id": "NX2_019_card_behavior",
                    "card_id": "NX2_019",
                    "surface": "NX2_019.json",
                    "surface_family": "CARDID.json",
                    "intent": "conditional_minion_death_burn",
                },
            ],
            "required_surfaces": [
                "GlobalValues.json",
                "Mulligan.json",
                "NX2_019.json",
            ],
            "optional_surfaces": [],
        },
    )

    report = build_config_quality_report(package)

    audit = report["checks"]["config_intent_self_audit"]
    projection = report["checks"]["surface_intent_projection"]
    assert audit["status"] == "attention"
    assert audit["runtime_files_without_intent"] == [
        "CustomConfig/shadowpriest/GlobalValues.json"
    ]
    assert projection["status"] == "attention"
    assert projection["first_attention"] == "surface_intent_malformed_row_visible"
    assert projection["malformed_rows"] == [
        {
            "card_id": "",
            "rule_id": "globalvalues_full_key_profile",
            "surface": "nested/GlobalValues.json",
        }
    ]
    assert report["apply_blocking"] is False


def test_config_quality_does_not_accept_card_bearing_globalvalues_intent(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    operator = json.loads(
        (package / "reports" / "operator_summary.json").read_text(encoding="utf-8")
    )
    operator["surface_status_ledger"] = [
        {"surface": "cardid_behavior", "status": "emitted"},
        {"surface": "mulligan", "status": "emitted"},
        {"surface": "combo", "status": "not_applicable"},
    ]
    write_json(package / "reports" / "operator_summary.json", operator)
    write_json(
        package / "reports" / "surface_intent.json",
        {
            "rows": [
                {
                    "rule_id": "globalvalues_full_key_profile",
                    "card_id": "UNRELATED_001",
                    "surface": "GlobalValues.json",
                    "intent": "bogus",
                },
                {
                    "rule_id": "NX2_019_card_behavior",
                    "card_id": "NX2_019",
                    "surface": "NX2_019.json",
                    "surface_family": "CARDID.json",
                    "intent": "conditional_minion_death_burn",
                },
            ],
            "required_surfaces": [
                "GlobalValues.json",
                "Mulligan.json",
                "NX2_019.json",
            ],
            "optional_surfaces": [],
        },
    )

    report = build_config_quality_report(package)

    audit = report["checks"]["config_intent_self_audit"]
    projection = report["checks"]["surface_intent_projection"]
    assert audit["status"] == "attention"
    assert audit["runtime_files_without_intent"] == [
        "CustomConfig/shadowpriest/GlobalValues.json"
    ]
    assert projection["status"] == "attention"
    assert projection["first_attention"] == "surface_intent_malformed_row_visible"
    assert projection["malformed_rows"] == [
        {
            "card_id": "UNRELATED_001",
            "rule_id": "globalvalues_full_key_profile",
            "surface": "GlobalValues.json",
        }
    ]
    assert report["apply_blocking"] is False


def test_config_quality_reports_authority_drift_without_changing_normal_apply_authority(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    operator = json.loads(
        (package / "reports" / "operator_summary.json").read_text(encoding="utf-8")
    )
    operator["runtime_apply_contract"] = {
        "apply_authority": "reports/drifted_runtime_apply_contract.json"
    }
    write_json(package / "reports" / "operator_summary.json", operator)

    report = build_config_quality_report(package)

    audit = report["checks"]["config_intent_self_audit"]
    assert audit["normal_apply_authority"] == "reports/operator_summary.json"
    assert audit["authority"] == "diagnostic_only"
    assert audit["apply_blocking"] is False
    assert audit["runtime_write_performed"] is False
    assert audit["normal_apply_authority_drift"] == {
        "expected": "reports/operator_summary.json",
        "reported": "reports/drifted_runtime_apply_contract.json",
    }
    assert audit["first_attention"] == "normal_apply_authority_drift"
    assert {
        "check": "normal_apply_authority_drift",
        "count": 1,
    } in audit["attention"]
    assert {
        "check": "config_intent_normal_apply_authority_drift",
        "value": {
            "expected": "reports/operator_summary.json",
            "reported": "reports/drifted_runtime_apply_contract.json",
        },
    } in report["problems"]
    assert report["apply_blocking"] is False


def test_config_quality_does_not_explain_combo_with_suppressed_evidence_chain(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "CustomConfig" / DECK_SLUG / "Combo.json",
        {"GameCardId": "Combo", "Combos": []},
    )
    explainability = json.loads(
        (package / "reports" / "source_to_runtime_explainability.json").read_text(
            encoding="utf-8"
        )
    )
    explainability["claim_rows"].append(
        {
            "claim_id": "claim_combo_without_timing",
            "claim_kind": "combo_sequence",
            "builder_or_router_decision": "suppressed",
            "runtime_surfaces": ["Combo.json"],
            "emitted_runtime_files": [],
            "first_missing_link": "combo_timing",
            "suppressed_reason": "missing_timing",
        }
    )
    explainability["card_rows"].append(
        {
            "card_id": "NX2_019",
            "first_missing_link": "combo_timing",
            "source_lane": "report_only",
            "runtime_surfaces": ["Combo.json"],
            "closure": {
                "lane": "suppressed_with_reason",
                "runtime_surfaces": ["Combo.json"],
                "default_only_risk": False,
            },
            "evidence_chain": [
                {
                    "claim_id": "claim_combo_without_timing",
                    "claim_kind": "combo_sequence",
                    "builder_or_router_decision": "suppressed",
                    "runtime_files": ["Combo.json"],
                    "resolution_reason": "missing_timing",
                    "suppressed_reason": "missing_timing",
                }
            ],
        }
    )
    write_json(
        package / "reports" / "source_to_runtime_explainability.json",
        explainability,
    )

    report = build_config_quality_report(package)

    audit = report["checks"]["config_intent_self_audit"]
    assert audit["runtime_files_without_intent"] == [
        "CustomConfig/shadowpriest/Combo.json"
    ]
    assert audit["first_attention"] == "runtime_file_without_intent"
    assert {
        "check": "config_intent_runtime_file_without_intent",
        "value": ["CustomConfig/shadowpriest/Combo.json"],
    } in report["problems"]
    assert report["apply_blocking"] is False


def test_config_quality_accepts_static_semantics_backed_operator_ledger_status(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    operator = json.loads(
        (package / "reports" / "operator_summary.json").read_text(encoding="utf-8")
    )
    operator["surface_status_ledger"] = [
        {"surface": "cardid_behavior", "status": "emitted"},
        {"surface": "globalvalues", "status": "static_semantics_backed"},
        {"surface": "mulligan", "status": "static_semantics_backed"},
        {"surface": "combo", "status": "not_applicable"},
    ]
    write_json(package / "reports" / "operator_summary.json", operator)

    report = build_config_quality_report(package)

    audit = report["checks"]["config_intent_self_audit"]
    assert audit["status"] == "clean"
    assert audit["runtime_files_without_intent"] == []
    assert audit["attention"] == []
    assert report["problems"] == []
