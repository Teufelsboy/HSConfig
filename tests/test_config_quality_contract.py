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
        "runtime_rows_missing_trace": [],
        "semantic_score_missing_rows": [],
        "semantic_default_rows": [],
        "report_only_runtime_rows": [],
        "warning_only_card_count": 0,
        "warning_only_mechanics": [],
        "attention": [],
        "first_attention": None,
    }
    assert report["checks"]["closure_freshness"] == {
        "present": True,
        "closure_schema_current": True,
        "cards_missing_closure": 0,
        "cards_total": 1,
        "cards_with_closure": 1,
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


def test_config_quality_allows_deck_identity_card_runtime_file_without_emitted_trace(
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
    assert report["status"] == "clean"
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


def test_config_quality_semantic_intent_coverage_counts_warning_only_semantics(
    tmp_path: Path,
):
    package = minimal_clean_package(tmp_path)
    write_json(
        package / "reports" / "semantic_enrichment_report.json",
        {
            "cards": {
                "BAR_880": {
                    "card_id": "BAR_880",
                    "name": "Tradeable Test Card",
                    "warning_only_mechanics": ["tradeable"],
                },
                "LOC_001": {
                    "card_id": "LOC_001",
                    "name": "Location Test Card",
                    "warning_only_mechanics": ["location_activation"],
                },
            }
        },
    )

    report = build_config_quality_report(package)

    assert report["status"] == "clean"
    assert report["checks"]["semantic_intent_coverage"]["warning_only_card_count"] == 2
    assert report["checks"]["semantic_intent_coverage"]["warning_only_mechanics"] == [
        "location_activation",
        "tradeable",
    ]
    assert report["checks"]["semantic_intent_coverage"]["attention"] == []


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
    }
    assert report["problems"] == []
