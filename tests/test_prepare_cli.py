import json
from pathlib import Path

from hsconfig.cli import main


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def test_research_contract_command_writes_contract_only(tmp_path: Path, capsys):
    out = tmp_path / "research"

    code = main(
        [
            "research-contract",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--out",
            str(out),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    archetype = json.loads((out / "archetype_research.json").read_text(encoding="utf-8"))
    card_roles = json.loads((out / "card_role_map.json").read_text(encoding="utf-8"))
    globalvalue_intent = json.loads((out / "globalvalue_intent.json").read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "passed"
    assert payload["research_dir"] == str(out)
    assert archetype["deck_name"] == "ShadowPriest"
    assert card_roles["SW_448"]["confidence"] == "source_backed_static_semantics"
    assert "hero_power_transform" in card_roles["SW_448"]["roles"]
    assert globalvalue_intent["overlays"]["MyHeroPowerValue"] == "increase"
    assert not (out / "CustomConfig").exists()


def test_research_contract_refuses_existing_nonempty_output_directory(tmp_path: Path, capsys):
    out = tmp_path / "package_root"
    out.mkdir()
    sentinel = out / "do_not_delete.txt"
    sentinel.write_text("keep", encoding="utf-8")

    code = main(
        [
            "research-contract",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--out",
            str(out),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["status"] == "failed"
    assert "Refusing to overwrite non-empty research output directory" in payload["errors"][0]
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_research_contract_refuses_existing_artifact_named_output_directory(
    tmp_path: Path, capsys
):
    out = tmp_path / "looks_like_research"
    out.mkdir()
    claims = out / "claims.json"
    claims.write_text('{"claims": "keep"}', encoding="utf-8")

    code = main(
        [
            "research-contract",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--out",
            str(out),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["status"] == "failed"
    assert "Refusing to overwrite non-empty research output directory" in payload["errors"][0]
    assert claims.read_text(encoding="utf-8") == '{"claims": "keep"}'


def test_prepare_builds_valid_package_with_research_artifacts(tmp_path: Path, capsys):
    package = tmp_path / "shadowpriest_package"
    runtime = tmp_path / "runtime"

    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(runtime),
            "--out",
            str(package),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    reports = package / "reports"
    research_dir = reports / "research"
    validation = json.loads((reports / "validation_report.json").read_text(encoding="utf-8"))
    operator_summary = json.loads((reports / "operator_summary.json").read_text(encoding="utf-8"))
    card_roles = json.loads((research_dir / "card_role_map.json").read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "passed"
    assert payload["command"] == "prepare"
    assert payload["package"] == str(package)
    assert validation["status"] == "passed"
    assert operator_summary["technical_status"] == "VALID_PACKAGE"
    assert operator_summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert operator_summary["next_action"] == "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY"
    assert payload["operator_summary"]["next_action"] == operator_summary["next_action"]
    assert payload["next_action"] == operator_summary["next_action"]
    assert (package / "CustomConfig" / "shadowpriest" / "GlobalValues.json").exists()
    assert (package / "CustomConfig" / "shadowpriest" / "Mulligan.json").exists()
    assert card_roles["SW_448"]["confidence"] == "source_backed_static_semantics"


def test_build_and_research_contract_agree_on_shadowpriest_research(tmp_path: Path, capsys):
    research_out = tmp_path / "research_only"
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"

    assert (
        main(
            [
                "research-contract",
                "--deck-name",
                "ShadowPriest",
                "--deck-code",
                SHADOWPRIEST_CODE,
                "--out",
                str(research_out),
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "build",
                "--deck-name",
                "ShadowPriest",
                "--deck-code",
                SHADOWPRIEST_CODE,
                "--runtime-root",
                str(runtime),
                "--out",
                str(package),
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()

    research_only = json.loads((research_out / "archetype_research.json").read_text(encoding="utf-8"))
    build_research = json.loads(
        (package / "reports" / "research" / "archetype_research.json").read_text(
            encoding="utf-8"
        )
    )

    assert build_research["confidence"] == research_only["confidence"]
    assert build_research["deck_name"] == research_only["deck_name"]


def test_prepare_gameplan_uses_research_bundle_intent(tmp_path: Path, capsys):
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"

    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(runtime),
            "--out",
            str(package),
            "--json",
        ]
    )
    capsys.readouterr()

    research_roles = json.loads(
        (package / "reports" / "research" / "card_role_map.json").read_text(encoding="utf-8")
    )
    research_globalvalues = json.loads(
        (package / "reports" / "research" / "globalvalue_intent.json").read_text(
            encoding="utf-8"
        )
    )
    gameplan = json.loads((package / "reports" / "gameplan_contract.json").read_text(encoding="utf-8"))

    assert code == 0
    assert gameplan["cards"]["SW_448"]["confidence"] == research_roles["SW_448"]["confidence"]
    assert set(research_roles["SW_448"]["roles"]) <= set(gameplan["cards"]["SW_448"]["roles"])
    assert set(research_globalvalues["overlays"]).issubset(
        set(gameplan["aggression_profile"]["global_value_overlays"])
    )


def test_prepare_accepts_guide_sources_json_and_writes_depth_artifacts(tmp_path: Path, capsys):
    package = tmp_path / "package"

    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--guide-sources-json",
            "tests/fixtures/shadowpriest_guide_sources.json",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    reports = package / "reports"
    coverage = json.loads((reports / "claim_coverage_report.json").read_text(encoding="utf-8"))
    guide_bundle = json.loads((reports / "guide_claim_bundle.json").read_text(encoding="utf-8"))
    source_index = json.loads((reports / "source_evidence_index.json").read_text(encoding="utf-8"))
    unsupported = json.loads((reports / "unsupported_claims_report.json").read_text(encoding="utf-8"))
    operator_summary = json.loads((reports / "operator_summary.json").read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "passed"
    assert payload["guide_claims_count"] >= 12
    assert payload["guide_backed_cards"] >= 8
    assert payload["uncovered_cards_count"] <= 4
    assert coverage["guide_backed_cards"] >= 8
    assert guide_bundle["claims"]
    assert source_index[0]["claim_count"] >= 12
    assert unsupported == []
    assert operator_summary["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert (reports / "mulligan_plan_report.json").exists()


def test_prepare_accepts_source_documents_json_and_writes_generated_guide_builder_artifacts(
    tmp_path: Path, capsys
):
    source_documents = tmp_path / "source_documents.json"
    source_documents.write_text(
        json.dumps(
            {
                "source_documents": [
                    {
                        "source_url": "https://example.invalid/shadow-priest",
                        "source_title": "Shadow Priest Guide",
                        "source_family": "guide",
                        "retrieved_at": "2026-07-06T00:00:00Z",
                        "deck_name": "ShadowPriest",
                        "archetype": "aggro_burn",
                        "claims": [
                            {
                                "claim_kind": "mulligan_keep",
                                "cards": ["SW_448"],
                                "condition": {"coin": True},
                                "reason": "Keep Darkbishop Benedictus.",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    package = tmp_path / "package"

    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--source-documents-json",
            str(source_documents),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    reports = package / "reports"
    guide_sources = json.loads((reports / "guide_sources.json").read_text(encoding="utf-8"))
    receipt = json.loads((reports / "guide_builder_receipt.json").read_text(encoding="utf-8"))
    operator_summary = json.loads((reports / "operator_summary.json").read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "passed"
    assert guide_sources["source_depth_status"] == "source_backed"
    assert receipt["source_depth_status"] == "source_backed"
    assert operator_summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert operator_summary["next_action"] == "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY"
    assert "reports/guide_builder_receipt.json" in {
        path.replace("\\", "/") for path in operator_summary["generated_files"]
    }


def test_prepare_no_auto_research_fallback_requests_research_before_strong_config(
    tmp_path: Path, capsys
):
    package = tmp_path / "package"

    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--no-auto-research-fallback",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    operator_summary = json.loads(
        (package / "reports" / "operator_summary.json").read_text(encoding="utf-8")
    )

    assert code == 0
    assert operator_summary["technical_status"] == "VALID_PACKAGE"
    assert operator_summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert operator_summary["next_action"] == "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY"
    assert payload["next_action"] == "IMPROVE_GUIDE_SOURCES_BEFORE_STRONG_APPLY"


def test_prepare_source_posture_drives_globalvalues_authority_matrix(
    tmp_path: Path, capsys
):
    source_documents = tmp_path / "source_documents.json"
    source_documents.write_text(
        json.dumps(
            {
                "source_documents": [
                    {
                        "source_url": "https://example.invalid/weapon-guide",
                        "source_title": "Weapon Guide",
                        "source_family": "guide",
                        "retrieved_at": "2026-07-06T00:00:00Z",
                        "deck_name": "ShadowPriest",
                        "archetype": "weapon_pressure",
                        "claims": [
                            {
                                "claim_kind": "gameplan_posture",
                                "scope": "deck",
                                "stance": "weapon_pressure",
                                "reason": "Prioritize weapon pressure.",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    package = tmp_path / "package"

    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--source-documents-json",
            str(source_documents),
            "--json",
        ]
    )

    capsys.readouterr()
    reports = package / "reports"
    authority = json.loads(
        (reports / "global_values_authority_matrix.json").read_text(
            encoding="utf-8"
        )
    )
    card_behavior = json.loads(
        (reports / "card_behavior_plan_report.json").read_text(encoding="utf-8")
    )
    card_behavior_suppressions = json.loads(
        (reports / "card_behavior_suppression_report.json").read_text(encoding="utf-8")
    )
    allowed = {row["key"] for row in authority["allowed_step1_overlays"]}

    assert code == 0
    assert authority["posture"] == "weapon_pressure"
    assert "MyWeaponValue" in allowed
    assert "MyHeroPowerValue" not in allowed
    assert (reports / "card_behavior_plan_report.json").exists()
    assert (reports / "combo_plan_report.json").exists()
    assert (reports / "global_values_authority_matrix.json").exists()
    assert card_behavior_suppressions == card_behavior.get("suppressed", [])


def test_prepare_writes_readiness_and_depth_reports(tmp_path: Path, capsys):
    cards_json = tmp_path / "shadow_cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {
                        "card_id": "SW_448",
                        "dbf_id": 1,
                        "count": 1,
                        "name": "Darkbishop Benedictus",
                        "text": "At the start of the game, if the spells in your deck are all Shadow, enter Shadowform.",
                    },
                    {
                        "card_id": "BAR_311",
                        "dbf_id": 2,
                        "count": 2,
                        "name": "Frazzled Freshman",
                        "text": "A strong early minion.",
                    },
                    {
                        "card_id": "SW_446",
                        "dbf_id": 3,
                        "count": 1,
                        "name": "Mind Spike",
                        "text": "Hero Power: Deal 2 damage.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    package = tmp_path / "package"

    result = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--cards-json",
            str(cards_json),
            "--guide-sources-json",
            "tests/fixtures/shadowpriest_guide_sources.json",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    reports = package / "reports"
    readiness = json.loads(
        (reports / "per_card_config_readiness_report.json").read_text(encoding="utf-8")
    )
    depth = json.loads(
        (reports / "guide_source_depth_report.json").read_text(encoding="utf-8")
    )
    deck_dir = package / "CustomConfig" / "shadowpriest"
    actual_cardid_files = sorted(
        path.name
        for path in deck_dir.glob("*.json")
        if path.name not in {"Combo.json", "GlobalValues.json", "Mulligan.json"}
    )
    reported_cardid_files = sorted(
        {
            surface
            for row in readiness["cards"].values()
            for surface in row["runtime_surfaces"]
            if surface not in {"Combo.json", "GlobalValues.json", "Mulligan.json"}
        }
    )

    assert result == 0
    assert readiness["summary"]["total_cards"] == 3
    assert "depth_status" in depth
    assert payload["config_readiness_summary"] == readiness["summary"]
    assert payload["guide_source_depth_status"] == depth["depth_status"]
    assert actual_cardid_files == reported_cardid_files
    for filename in actual_cardid_files:
        card_id = filename.removesuffix(".json")
        assert filename in readiness["cards"][card_id]["runtime_surfaces"]


def test_prepare_writes_claim_conflict_and_coverage_reports(tmp_path: Path, capsys):
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {
                        "card_id": "CARD_A",
                        "dbf_id": 1,
                        "count": 2,
                        "name": "Card A",
                        "text": "Fixture card.",
                    },
                    {
                        "card_id": "CARD_B",
                        "dbf_id": 2,
                        "count": 2,
                        "name": "Card B",
                        "text": "Fixture card.",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    source_documents = tmp_path / "source_documents.json"
    source_documents.write_text(
        json.dumps(
            {
                "source_documents": [
                    {
                        "source_url": "https://example.invalid/keep",
                        "source_title": "Keep Guide",
                        "source_family": "guide",
                        "retrieved_at": "2026-07-07T00:00:00Z",
                        "claims": [
                            {
                                "claim_kind": "mulligan_keep",
                                "cards": ["CARD_A"],
                                "stance": "keep",
                                "evidence_text_short": "Keep Card A.",
                                "source_confidence": "high",
                            }
                        ],
                    },
                    {
                        "source_url": "https://example.invalid/discard",
                        "source_title": "Discard Guide",
                        "source_family": "guide",
                        "retrieved_at": "2026-07-07T00:00:00Z",
                        "claims": [
                            {
                                "claim_kind": "mulligan_discard",
                                "cards": ["CARD_A"],
                                "stance": "discard",
                                "evidence_text_short": "Discard Card A.",
                                "source_confidence": "high",
                            }
                        ],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    package = tmp_path / "package"

    code = main(
        [
            "prepare",
            "--deck-name",
            "Fixture",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--cards-json",
            str(cards_json),
            "--source-documents-json",
            str(source_documents),
            "--json",
        ]
    )

    capsys.readouterr()
    reports = package / "reports"
    coverage = json.loads((reports / "claim_coverage_report.json").read_text(encoding="utf-8"))
    conflicts = json.loads((reports / "claim_conflict_report.json").read_text(encoding="utf-8"))
    operator_summary = json.loads((reports / "operator_summary.json").read_text(encoding="utf-8"))

    assert code == 1
    assert coverage["cards"]["CARD_A"]["coverage_status"] == "guide_backed"
    assert coverage["cards"]["CARD_B"]["coverage_status"] == "uncovered_low_confidence"
    assert conflicts["conflict_count"] == 1
    assert conflicts["conflicts"][0]["card_id"] == "CARD_A"
    assert {"reason": "claim_conflicts_present", "conflict_count": 1} in operator_summary["warnings"]
    assert {"reason": "cards_still_low_confidence", "card_count": 1} in operator_summary["warnings"]
