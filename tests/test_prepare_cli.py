import json
from datetime import datetime, timezone
from pathlib import Path

from hsconfig.cli import main


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def _today_utc_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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
    assert operator_summary["semantic_status"] == "STATIC_SEMANTICS_USABLE"
    assert operator_summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert operator_summary["runtime_load_safe"] is True
    assert operator_summary["runtime_apply_mode"] == "load_safe_apply"
    assert operator_summary["runtime_apply_allowed"] is True
    assert payload["operator_summary"]["next_action"] == operator_summary["next_action"]
    assert payload["next_action"] == operator_summary["next_action"]
    assert (package / "CustomConfig" / "shadowpriest" / "GlobalValues.json").exists()
    assert (package / "CustomConfig" / "shadowpriest" / "Mulligan.json").exists()
    assert card_roles["SW_448"]["confidence"] == "source_backed_static_semantics"


def test_prepare_fetch_failure_keeps_semantic_warning_counts_consistent(
    tmp_path: Path, capsys, monkeypatch
):
    package = tmp_path / "shadowpriest_package"
    runtime = tmp_path / "runtime"

    def raise_fetch_failure(timeout: float = 10.0):
        raise RuntimeError("offline fixture")

    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", raise_fetch_failure)

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

    reports = package / "reports"
    semantic_report = json.loads(
        (reports / "semantic_enrichment_report.json").read_text(encoding="utf-8")
    )
    operator_summary = json.loads(
        (reports / "operator_summary.json").read_text(encoding="utf-8")
    )
    warnings = semantic_report["semantic_enrichment_warnings"]

    assert code == 0
    assert semantic_report["semantic_enrichment_status"] == "partial"
    assert any("hearthstonejson_fetch_failed: offline fixture" in row["warning"] for row in warnings)
    assert semantic_report["summary"]["warning_count"] == len(warnings)
    assert operator_summary["semantic_enrichment_summary"]["warning_count"] == len(warnings)


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
    assert operator_summary["guide_strength_summary"]["cards_needing_runtime_surface"] == 0
    assert operator_summary["guide_strength_summary"]["cards_needing_mechanic_lowering"] == 0
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
                        "retrieved_at": _today_utc_iso(),
                        "deck_name": "ShadowPriest",
                        "archetype": "aggro_burn",
                        "claims": [
                            {
                                "claim_kind": "mulligan_keep",
                                "cards": ["SW_446"],
                                "condition": {"coin": True},
                                "reason": "Keep Voidtouched Attendant as an early pressure amplifier.",
                                "source_confidence": "high",
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
    source_report = json.loads(
        (reports / "source_evidence_verification_report.json").read_text(encoding="utf-8")
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert guide_sources["source_depth_status"] == "source_backed"
    assert receipt["source_depth_status"] == "source_backed"
    assert operator_summary["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert operator_summary["next_action"] == "READY_TO_APPLY_OR_HANDOFF"
    assert "reports/guide_builder_receipt.json" in {
        path.replace("\\", "/") for path in operator_summary["generated_files"]
    }
    assert source_report["status"] == "passed"
    assert source_report["warnings"] == []


def test_prepare_low_confidence_source_documents_do_not_lower_runtime_rows(
    tmp_path: Path, capsys, monkeypatch
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])

    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {"card_id": "CARD_001", "dbf_id": 1, "count": 2, "name": "Card A"},
                    {"card_id": "CARD_002", "dbf_id": 2, "count": 2, "name": "Card B"},
                    {"card_id": "CARD_003", "dbf_id": 3, "count": 2, "name": "Card C"},
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
                        "source_url": "https://example.invalid/weak-guide",
                        "source_title": "Weak Guide",
                        "source_family": "guide",
                        "retrieved_at": _today_utc_iso(),
                        "claims": [
                            {
                                "claim_kind": "mulligan_keep",
                                "cards": ["CARD_001"],
                                "stance": "keep",
                                "evidence_text_short": "Card A might be a keep.",
                                "source_confidence": "low",
                            },
                            {
                                "claim_kind": "targeting_rule",
                                "cards": ["CARD_002"],
                                "stance": "prefer_enemy_hero",
                                "evidence_text_short": "Card B might go face.",
                                "source_confidence": "low",
                            },
                            {
                                "claim_kind": "card_role",
                                "cards": ["CARD_003"],
                                "stance": "maybe_core",
                                "evidence_text_short": "Card C might be part of the plan.",
                                "source_confidence": "low",
                            },
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
            "WeakDeck",
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

    payload = json.loads(capsys.readouterr().out)
    reports = package / "reports"
    guide_bundle = json.loads((reports / "guide_claim_bundle.json").read_text(encoding="utf-8"))
    coverage = json.loads((reports / "claim_coverage_report.json").read_text(encoding="utf-8"))
    card_behavior = json.loads(
        (reports / "card_behavior_plan_report.json").read_text(encoding="utf-8")
    )
    mulligan_plan = json.loads((reports / "mulligan_plan_report.json").read_text(encoding="utf-8"))
    readiness = json.loads(
        (reports / "per_card_config_readiness_report.json").read_text(encoding="utf-8")
    )
    operator_summary = json.loads((reports / "operator_summary.json").read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "passed"
    source_claims = [
        claim for claim in guide_bundle["claims"] if claim["source_family"] == "guide"
    ]
    source_claim_ids = {claim["claim_id"] for claim in source_claims}
    assert {claim["claim_readiness"] for claim in source_claims} == {"explicit_low_confidence"}
    assert {claim["trust_ceiling"] for claim in source_claims} == {"report_only"}
    assert coverage["summary"]["guide_backed"] == 0
    assert coverage["summary"]["uncovered_low_confidence"] == 3
    assert card_behavior["rows"] == []
    assert not any(
        source_claim_ids & set(row.get("source_claim_ids", []))
        for row in mulligan_plan["rules"]
    )
    assert not any(
        source_claim_ids & set(row.get("source_claim_ids", []))
        for row in card_behavior["rows"]
    )
    assert readiness["summary"]["runtime_emitted"] == 0
    assert readiness["summary"]["mulligan_only"] == 0
    assert readiness["summary"]["generic_low_confidence"] == 3
    assert operator_summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert operator_summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"


def test_prepare_low_confidence_claims_json_does_not_lower_runtime_rows(
    tmp_path: Path, capsys, monkeypatch
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])

    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {"card_id": "EX1_001", "dbf_id": 1, "count": 2, "name": "Card A"},
                    {"card_id": "EX1_002", "dbf_id": 2, "count": 2, "name": "Card B"},
                ]
            }
        ),
        encoding="utf-8",
    )
    claims_json = tmp_path / "claims.json"
    claims_json.write_text(
        json.dumps(
            [
                {
                    "source": "guide",
                    "url": "https://example.invalid/weak-legacy-guide",
                    "claim": "Always keep Card A.",
                    "cards": ["EX1_001"],
                    "claim_type": "mulligan",
                    "confidence": "low",
                },
                {
                    "source": "guide",
                    "url": "https://example.invalid/weak-legacy-guide",
                    "claim": "Target the enemy hero with Card B.",
                    "cards": ["EX1_002"],
                    "claim_type": "targeting_rule",
                    "confidence": "low",
                },
            ]
        ),
        encoding="utf-8",
    )
    package = tmp_path / "package"

    code = main(
        [
            "prepare",
            "--deck-name",
            "WeakLegacyDeck",
            "--deck-code",
            "fixture-code",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--cards-json",
            str(cards_json),
            "--claims-json",
            str(claims_json),
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    reports = package / "reports"
    guide_bundle = json.loads((reports / "guide_claim_bundle.json").read_text(encoding="utf-8"))
    card_behavior = json.loads(
        (reports / "card_behavior_plan_report.json").read_text(encoding="utf-8")
    )
    mulligan_plan = json.loads((reports / "mulligan_plan_report.json").read_text(encoding="utf-8"))
    readiness = json.loads(
        (reports / "per_card_config_readiness_report.json").read_text(encoding="utf-8")
    )
    operator_summary = json.loads((reports / "operator_summary.json").read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "passed"
    source_claims = [
        claim for claim in guide_bundle["claims"] if claim["source_family"] == "guide"
    ]
    source_claim_ids = {claim["claim_id"] for claim in source_claims}
    assert {claim["source_confidence"] for claim in source_claims} == {"low"}
    assert {claim["claim_readiness"] for claim in source_claims} == {"explicit_low_confidence"}
    assert {claim["trust_ceiling"] for claim in source_claims} == {"report_only"}
    assert card_behavior["rows"] == []
    assert not any(
        source_claim_ids & set(row.get("source_claim_ids", []))
        for row in mulligan_plan["rules"]
    )
    assert readiness["summary"]["runtime_emitted"] == 0
    assert readiness["summary"]["mulligan_only"] == 0
    assert readiness["summary"]["generic_low_confidence"] == 2
    assert operator_summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"


def test_prepare_source_documents_missing_source_confidence_stays_unsupported(tmp_path: Path, capsys):
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {"card_id": "EX1_001", "dbf_id": 1, "count": 2, "name": "Card A"},
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
                        "source_url": "https://example.invalid/missing-confidence",
                        "source_title": "Missing Confidence Guide",
                        "source_family": "guide",
                        "retrieved_at": _today_utc_iso(),
                        "claims": [
                            {
                                "claim_kind": "mulligan_keep",
                                "cards": ["EX1_001"],
                                "evidence_text_short": "Keep Card A.",
                            },
                            {
                                "claim_kind": "mulligan_keep",
                                "cards": ["EX1_001"],
                                "evidence_text_short": "Keep Card A when on the coin.",
                                "source_confidence": "   ",
                            },
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

    payload = json.loads(capsys.readouterr().out)
    reports = package / "reports"
    guide_sources = json.loads((reports / "guide_sources.json").read_text(encoding="utf-8"))
    receipt = json.loads((reports / "guide_builder_receipt.json").read_text(encoding="utf-8"))
    guide_bundle = json.loads((reports / "guide_claim_bundle.json").read_text(encoding="utf-8"))
    unsupported = json.loads((reports / "unsupported_claims_report.json").read_text(encoding="utf-8"))
    operator_summary = json.loads((reports / "operator_summary.json").read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "passed"
    assert payload["guide_claims_count"] == 1
    assert guide_sources["source_depth_status"] == "needs_more_research"
    assert guide_sources["summary"]["claim_count"] == 0
    assert guide_sources["sources"][0]["claims"] == []
    assert receipt["source_depth_status"] == "needs_more_research"
    assert receipt["claim_count"] == 0
    assert not [
        claim for claim in guide_bundle["claims"] if claim.get("source_family") == "guide"
    ]
    assert [row["missing_claim_keys"] for row in unsupported] == [
        ["source_confidence"],
        ["source_confidence"],
    ]
    assert operator_summary["semantic_status"] == "STATIC_SEMANTICS_USABLE"
    assert operator_summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"


def test_prepare_source_document_timed_combo_emits_combo_json(tmp_path: Path, capsys):
    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {"card_id": "EX1_001", "dbf_id": 1, "count": 2, "name": "Card A"},
                    {"card_id": "EX1_002", "dbf_id": 2, "count": 2, "name": "Card B"},
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
                        "source_url": "https://example.invalid/timed-combo",
                        "source_title": "Timed Combo Guide",
                        "source_family": "guide",
                        "retrieved_at": "2026-07-06T00:00:00Z",
                        "deck_name": "Timed Combo",
                        "claims": [
                            {
                                "claim_kind": "combo_sequence",
                                "cards": ["EX1_001", "EX1_002"],
                                "sequence": ["EX1_001", "EX1_002"],
                                "timing_kind": "same_turn",
                                "operator": ">>",
                                "values": ["8", "14"],
                                "evidence_text_short": "Play Card A into Card B on the same turn.",
                                "source_confidence": "high",
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
            "Timed Combo",
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

    payload = json.loads(capsys.readouterr().out)
    deck_dir = package / "CustomConfig" / "timed_combo"
    reports = package / "reports"
    combo = json.loads((deck_dir / "Combo.json").read_text(encoding="utf-8"))
    combo_plan = json.loads((reports / "combo_plan_report.json").read_text(encoding="utf-8"))
    combo_suppressions = json.loads(
        (reports / "combo_suppression_report.json").read_text(encoding="utf-8")
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert combo["ComboList"]["values"] == [
        {
            "comment": "Timed Combo: " + combo_plan["combos"][0]["rule_id"],
            "condition": "*",
            "combo": "EX1_001>>EX1_002",
            "value": "8>>14",
        }
    ]
    assert combo_plan["combos"][0]["operator"] == ">>"
    assert combo_plan["combos"][0]["source_refs"] == [
        "source:1",
        "https://example.invalid/timed-combo",
    ]
    assert combo_suppressions == []


def test_prepare_no_auto_research_fallback_requests_research_before_strong_config(
    tmp_path: Path, capsys, monkeypatch
):
    package = tmp_path / "package"

    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])

    def _shared_fallback(deck_name: str, deck_identity: dict[str, object]) -> dict[str, object]:
        return {
            "schema_version": 1,
            "deck_name": deck_name,
            "deck_code_hash": str(deck_identity.get("deck_code_hash", "")),
            "source_depth_status": "needs_more_research",
            "sources": [],
            "summary": {
                "source_count": 0,
                "claim_count": 0,
                "stale_source_count": 0,
                "downgraded_source_count": 0,
                "static_card_semantics_used": False,
            },
            "research_fallback_source": "shared_module",
        }

    monkeypatch.setattr("hsconfig.package_builder._research_required_guide_sources", _shared_fallback)

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
    guide_sources = json.loads((package / "reports" / "guide_sources.json").read_text(encoding="utf-8"))

    assert code == 0
    assert operator_summary["technical_status"] == "VALID_PACKAGE"
    assert operator_summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert operator_summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert payload["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert guide_sources["source_depth_status"] == "needs_more_research"
    assert guide_sources["summary"]["source_count"] == 0
    assert guide_sources["research_fallback_source"] == "shared_module"


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
                                "source_confidence": "high",
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
    globalvalues_profile = json.loads(
        (reports / "globalvalues_profile.json").read_text(encoding="utf-8")
    )
    key_profile_report = json.loads(
        (reports / "global_values_key_profile_report.json").read_text(encoding="utf-8")
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
    assert key_profile_report == globalvalues_profile
    assert key_profile_report["keys"]["MyWeaponValue"]["authority_category"] == (
        "step1_posture_overlay_allowed"
    )
    assert (reports / "card_behavior_plan_report.json").exists()
    assert (reports / "combo_plan_report.json").exists()
    assert (reports / "global_values_authority_matrix.json").exists()
    assert (reports / "global_values_key_profile_report.json").exists()
    assert card_behavior_suppressions == card_behavior.get("suppressed", [])


def test_prepare_source_numeric_globalvalue_tuning_is_runtime_evidence_only(
    tmp_path: Path, capsys
):
    runtime_default = tmp_path / "runtime" / "CustomConfig" / "default"
    runtime_default.mkdir(parents=True)
    runtime_default.joinpath("GlobalValues.json").write_text(
        json.dumps(
            {
                "GameCardId": "GlobalValues",
                "ConfigComment": "Runtime baseline",
                "LowHpBoardValuePenalty": {
                    "values": [{"condition": "*", "value": "1.00"}]
                },
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
                        "source_url": "https://example.invalid/runtime-notes",
                        "source_title": "Runtime Notes",
                        "source_family": "guide",
                        "retrieved_at": "2026-07-06T00:00:00Z",
                        "deck_name": "ShadowPriest",
                        "claims": [
                            {
                                "claim_kind": "globalvalue_numeric_tuning",
                                "scope": "deck",
                                "key": "LowHpBoardValuePenalty",
                                "runtime_value": "0.25",
                                "reason": "Lower low-health board penalty only after runtime evidence.",
                                "source_confidence": "high",
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
    unsupported = json.loads(
        (reports / "unsupported_claims_report.json").read_text(encoding="utf-8")
    )
    globalvalues = json.loads(
        (
            package / "CustomConfig" / "shadowpriest" / "GlobalValues.json"
        ).read_text(encoding="utf-8")
    )
    blocked = [
        row
        for row in authority["blocked_until_runtime_evidence"]
        if row["key"] == "LowHpBoardValuePenalty"
    ]

    assert code == 0
    assert unsupported == []
    assert any(
        row["reason"] == "requires_runtime_evidence" and row["claim_refs"]
        for row in blocked
    )
    assert globalvalues["LowHpBoardValuePenalty"]["values"][0]["value"] == "1.00"


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


def test_prepare_suppresses_option_claim_without_identity_resolution(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])

    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {"card_id": "DISCOVER_CARD", "dbf_id": 1, "count": 2, "name": "Discover Card"},
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
                        "source_url": "https://example.invalid/discover-guide",
                        "source_title": "Discover Guide",
                        "source_family": "guide",
                        "retrieved_at": _today_utc_iso(),
                        "claims": [
                            {
                                "claim_kind": "discover_choice",
                                "cards": ["DISCOVER_CARD"],
                                "option_card_id": "OPTION_ALPHA",
                                "stance": "pick_option_alpha",
                                "evidence_text_short": "Prefer Option Alpha from this discover pool.",
                                "source_confidence": "high",
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
            "Discover Deck",
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

    payload = json.loads(capsys.readouterr().out)
    reports = package / "reports"
    card_behavior = json.loads((reports / "card_behavior_plan_report.json").read_text(encoding="utf-8"))
    suppressions = json.loads(
        (reports / "card_behavior_suppression_report.json").read_text(encoding="utf-8")
    )

    assert code == 1
    assert payload["status"] == "failed"
    suppressed_claim_id = card_behavior["suppressed"][0]["claim_id"]
    assert all(row.get("claim_id") != suppressed_claim_id for row in card_behavior["rows"])
    assert all(row.get("claim_kind") != "discover_choice" for row in card_behavior["rows"])
    assert card_behavior["option_resolution"] == [
        {
            "claim_id": card_behavior["suppressed"][0]["claim_id"],
            "card_id": "DISCOVER_CARD",
            "option_card_id": "OPTION_ALPHA",
            "status": "unresolved",
        }
    ]
    assert suppressions == [
        {
            "claim_id": card_behavior["suppressed"][0]["claim_id"],
            "claim_kind": "discover_choice",
            "cards": ["DISCOVER_CARD"],
            "reason": "unresolved_option_identity",
        }
    ]


def test_prepare_routes_option_claim_with_identity_links(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [
            {
                "id": "DISCOVER_CARD",
                "dbf_id": 1,
                "name": "Discover Card",
                "type": "MINION",
                "text": "Discover a spell.",
                "entourage": ["OPTION_ALPHA"],
            },
            {
                "id": "OPTION_ALPHA",
                "dbf_id": 2,
                "name": "Option Alpha",
                "type": "SPELL",
                "text": "Deal damage.",
            },
        ],
    )

    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {"card_id": "DISCOVER_CARD", "dbf_id": 1, "count": 2, "name": "Discover Card"},
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
                        "source_url": "https://example.invalid/discover-guide",
                        "source_title": "Discover Guide",
                        "source_family": "guide",
                        "retrieved_at": _today_utc_iso(),
                        "claims": [
                            {
                                "claim_kind": "discover_choice",
                                "cards": ["DISCOVER_CARD"],
                                "option_card_id": "OPTION_ALPHA",
                                "stance": "pick_option_alpha",
                                "evidence_text_short": "Prefer Option Alpha from this discover pool.",
                                "source_confidence": "high",
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
            "Discover Deck",
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

    payload = json.loads(capsys.readouterr().out)
    reports = package / "reports"
    card_behavior = json.loads((reports / "card_behavior_plan_report.json").read_text(encoding="utf-8"))
    guide_bundle = json.loads((reports / "guide_claim_bundle.json").read_text(encoding="utf-8"))
    discover_claim = next(
        claim for claim in guide_bundle["claims"] if claim["claim_kind"] == "discover_choice"
    )
    discover_config = json.loads(
        (package / "CustomConfig" / "discover_deck" / "DISCOVER_CARD.json").read_text(
            encoding="utf-8"
        )
    )

    assert code == 1
    assert payload["status"] == "failed"
    assert [row["claim_id"] for row in card_behavior["rows"]] == [discover_claim["claim_id"]]
    assert card_behavior["suppressed"] == [
        {
            "claim_id": card_behavior["suppressed"][0]["claim_id"],
            "claim_kind": "mechanic_usage",
            "cards": ["DISCOVER_CARD"],
            "reason": "covered_by_resolved_choice_surface",
        }
    ]
    assert card_behavior["option_resolution"] == [
        {
            "claim_id": discover_claim["claim_id"],
            "card_id": "DISCOVER_CARD",
            "option_card_id": "OPTION_ALPHA",
            "status": "resolved",
        }
    ]
    assert discover_config["OnDiscoverCardBonus"]["values"] == [
        {
            "comment": "Discover Deck: DISCOVER_CARD_pick_option_alpha",
            "condition": "my_discover(count(),cardid=OPTION_ALPHA) > 0",
            "value": "6",
        }
    ]


def test_prepare_partial_discover_choice_resolution_preserves_unresolved_generic_fallback(
    tmp_path: Path, capsys, monkeypatch
):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [
            {
                "id": "CARD_RESOLVED",
                "dbf_id": 1,
                "name": "Resolved Discover Card",
                "type": "MINION",
                "text": "Discover a spell.",
                "entourage": ["OPTION_ALPHA"],
            },
            {
                "id": "CARD_UNRESOLVED",
                "dbf_id": 2,
                "name": "Unresolved Discover Card",
                "type": "MINION",
                "text": "Discover a spell.",
                "entourage": ["OPTION_BETA"],
            },
            {
                "id": "OPTION_ALPHA",
                "dbf_id": 3,
                "name": "Option Alpha",
                "type": "SPELL",
                "text": "Deal damage.",
            },
            {
                "id": "OPTION_BETA",
                "dbf_id": 4,
                "name": "Option Beta",
                "type": "SPELL",
                "text": "Draw a card.",
            },
        ],
    )

    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {
                        "card_id": "CARD_RESOLVED",
                        "dbf_id": 1,
                        "count": 2,
                        "name": "Resolved Discover Card",
                    },
                    {
                        "card_id": "CARD_UNRESOLVED",
                        "dbf_id": 2,
                        "count": 2,
                        "name": "Unresolved Discover Card",
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
                        "source_url": "https://example.invalid/discover-guide",
                        "source_title": "Discover Guide",
                        "source_family": "guide",
                        "retrieved_at": _today_utc_iso(),
                        "claims": [
                            {
                                "claim_kind": "discover_choice",
                                "cards": ["CARD_RESOLVED", "CARD_UNRESOLVED"],
                                "option_card_id": "OPTION_ALPHA",
                                "stance": "pick_option_alpha",
                                "evidence_text_short": (
                                    "Prefer Option Alpha from this discover pool."
                                ),
                                "source_confidence": "high",
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
            "Discover Split Deck",
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

    payload = json.loads(capsys.readouterr().out)
    reports = package / "reports"
    card_behavior = json.loads((reports / "card_behavior_plan_report.json").read_text(encoding="utf-8"))
    suppressions = json.loads(
        (reports / "card_behavior_suppression_report.json").read_text(encoding="utf-8")
    )
    resolved_config = json.loads(
        (package / "CustomConfig" / "discover_split_deck" / "CARD_RESOLVED.json").read_text(
            encoding="utf-8"
        )
    )
    unresolved_config = json.loads(
        (package / "CustomConfig" / "discover_split_deck" / "CARD_UNRESOLVED.json").read_text(
            encoding="utf-8"
        )
    )
    resolved_choice_claim_id = card_behavior["option_resolution"][0]["claim_id"]
    generic_discover_claim_id = next(
        row["claim_id"] for row in card_behavior["rows"] if row["card_id"] == "CARD_UNRESOLVED"
    )

    assert code == 1
    assert payload["status"] == "failed"
    assert [
        (row["claim_id"], row["card_id"], row["condition"])
        for row in card_behavior["rows"]
        if row["card_id"] in {"CARD_RESOLVED", "CARD_UNRESOLVED"}
        ] == [
        (
            resolved_choice_claim_id,
            "CARD_RESOLVED",
            "my_discover(count(),cardid=OPTION_ALPHA) > 0",
        ),
        (generic_discover_claim_id, "CARD_UNRESOLVED", "*"),
    ]
    assert suppressions[0] == {
        "claim_id": resolved_choice_claim_id,
        "claim_kind": "discover_choice",
        "cards": ["CARD_UNRESOLVED"],
        "reason": "unresolved_option_identity",
    }
    assert suppressions[1]["claim_kind"] == "mechanic_usage"
    assert suppressions[1]["cards"] == ["CARD_RESOLVED"]
    assert suppressions[1]["reason"] == "covered_by_resolved_choice_surface"
    assert resolved_config["OnDiscoverCardBonus"]["values"] == [
        {
            "comment": "Discover Split Deck: CARD_RESOLVED_pick_option_alpha",
            "condition": "my_discover(count(),cardid=OPTION_ALPHA) > 0",
            "value": "6",
        }
    ]
    assert unresolved_config["OnDiscoverCardBonus"]["values"] == [
        {
            "comment": "Discover Split Deck: CARD_UNRESOLVED_use_discover_according_to_card_text",
            "condition": "*",
            "value": "6",
        }
    ]


def test_prepare_routes_choose_one_claim_with_identity_links(
    tmp_path: Path, capsys, monkeypatch
):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [
            {
                "id": "CHOOSE_CARD",
                "dbf_id": 1,
                "name": "Choose Card",
                "type": "SPELL",
                "text": "Choose One - Option Alpha; or Option Beta.",
                "entourage": ["OPTION_ALPHA", "OPTION_BETA"],
            },
            {
                "id": "OPTION_ALPHA",
                "dbf_id": 2,
                "name": "Option Alpha",
                "type": "SPELL",
                "text": "Primary option.",
            },
            {
                "id": "OPTION_BETA",
                "dbf_id": 3,
                "name": "Option Beta",
                "type": "SPELL",
                "text": "Secondary option.",
            },
        ],
    )

    cards_json = tmp_path / "cards.json"
    cards_json.write_text(
        json.dumps(
            {
                "cards": [
                    {"card_id": "CHOOSE_CARD", "dbf_id": 1, "count": 2, "name": "Choose Card"},
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
                        "source_url": "https://example.invalid/choose-guide",
                        "source_title": "Choose Guide",
                        "source_family": "guide",
                        "retrieved_at": _today_utc_iso(),
                        "claims": [
                            {
                                "claim_kind": "choose_one_choice",
                                "cards": ["CHOOSE_CARD"],
                                "choice_card_id": "OPTION_ALPHA",
                                "stance": "choose_option_alpha",
                                "evidence_text_short": (
                                    "Prefer Option Alpha when resolving Choose One."
                                ),
                                "source_confidence": "high",
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
            "Choice Deck",
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

    payload = json.loads(capsys.readouterr().out)
    reports = package / "reports"
    card_behavior = json.loads((reports / "card_behavior_plan_report.json").read_text(encoding="utf-8"))
    choose_claim = next(
        row for row in card_behavior["rows"] if row["claim_id"] and row["card_id"] == "CHOOSE_CARD"
    )
    choose_config = json.loads(
        (package / "CustomConfig" / "choice_deck" / "CHOOSE_CARD.json").read_text(
            encoding="utf-8"
        )
    )

    assert code == 1
    assert payload["status"] == "failed"
    assert choose_claim["behavior_block"] == "OnChooseOneCardBonus"
    assert card_behavior["suppressed"] == []
    assert card_behavior["option_resolution"] == [
        {
            "claim_id": choose_claim["claim_id"],
            "card_id": "CHOOSE_CARD",
            "option_card_id": "OPTION_ALPHA",
            "status": "resolved",
        }
    ]
    assert {
        "comment": "Choice Deck: CHOOSE_CARD_choose_option_alpha",
        "condition": "*",
        "value": "6",
    } in choose_config["OnChooseOneCardBonus"]["values"]


def test_prepare_json_mirrors_operator_summary_guide_strength_fields(
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
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    operator_summary = json.loads(
        (package / "reports" / "operator_summary.json").read_text(encoding="utf-8")
    )

    assert code == 0
    assert payload["guide_strength_summary"] == operator_summary["guide_strength_summary"]
    assert payload["semantic_blockers"] == operator_summary["semantic_blockers"]
    assert operator_summary["guide_strength_summary"]["source_backed_strong_requires"]


def test_prepare_writes_source_gap_and_promotion_reports(tmp_path: Path, capsys, monkeypatch):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
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
            "tests/fixtures/source_documents_shadowpriest_strong.json",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    reports = package / "reports"
    source_gap = json.loads(
        (reports / "source_claim_gap_report.json").read_text(encoding="utf-8")
    )
    promotion = json.loads(
        (reports / "strong_promotion_report.json").read_text(encoding="utf-8")
    )

    assert code == 0
    assert payload["status"] == "passed"
    assert source_gap["summary"]["blocked_cards"] == 0
    assert promotion["promotion_ready"] is True
    assert promotion["verdict"] == "SOURCE_BACKED_STRONG_CONFIRMED"


def test_prepare_clears_stale_reports_before_operator_summary_generated_files(
    tmp_path: Path, capsys, monkeypatch
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    package = tmp_path / "package"
    reports = package / "reports"
    reports.mkdir(parents=True)
    stale_report = reports / "stale_report.json"
    stale_report.write_text('{"stale": true}', encoding="utf-8")

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
            "tests/fixtures/source_documents_shadowpriest_strong.json",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    operator_summary = json.loads(
        (reports / "operator_summary.json").read_text(encoding="utf-8")
    )
    generated = {path.replace("\\", "/") for path in operator_summary["generated_files"]}

    assert code == 0
    assert payload["status"] == "passed"
    assert not stale_report.exists()
    assert "reports/stale_report.json" not in generated


def test_prepare_writes_source_contract_audit_and_operator_summary_pointer(
    tmp_path: Path, capsys, monkeypatch
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
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
            "tests/fixtures/source_documents_shadowpriest_strong.json",
            "--json",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    reports = package / "reports"
    audit = json.loads(
        (reports / "source_contract_audit.json").read_text(encoding="utf-8")
    )
    operator_summary = json.loads(
        (reports / "operator_summary.json").read_text(encoding="utf-8")
    )
    generated = {path.replace("\\", "/") for path in operator_summary["generated_files"]}

    assert code == 0
    assert payload["status"] == "passed"
    assert audit["schema_version"] == 1
    assert audit["summary"]["claims_total"] > 0
    assert audit["summary"]["runtime_lowered_claims"] > 0
    assert "claim_kind_policy_counts" in audit["summary"]
    assert all("policy_lane" in row for row in audit["claim_rows"].values())
    lifecycle_rows = audit["claim_lifecycle_rows"]
    assert lifecycle_rows
    assert all(row["operator_impact"] == "diagnostic_only" for row in lifecycle_rows)
    assert any(
        row["builder_or_router_decision"] in {"emitted", "suppressed"}
        for row in lifecycle_rows
    )
    assert "SW_448" in audit["card_rows"]
    assert (reports / "source_contract_audit.md").is_file()
    assert "reports/source_contract_audit.json" in generated
    assert "reports/source_contract_audit.md" in generated
    assert "claim_lifecycle_rows" not in operator_summary
    assert operator_summary["source_contract_audit_summary"]["non_blocking"] is True
    assert (
        operator_summary["source_contract_audit_summary"]["next_report_to_open"]
        in {None, "reports/source_contract_audit.json"}
    )
    assert (
        operator_summary["source_contract_audit_summary"]["runtime_lowered_claims"]
        == audit["summary"]["runtime_lowered_claims"]
    )


def test_prepare_writes_mechanic_drift_report_and_operator_summary(
    tmp_path: Path, capsys
):
    out = tmp_path / "package"
    runtime = tmp_path / "runtime"
    cards = tmp_path / "cards.json"
    cards.write_text(
        json.dumps(
            [
                {
                    "card_id": "SW_001",
                    "id": "SW_001",
                    "name": "Text Trade Card",
                    "type": "SPELL",
                    "mechanics": [],
                    "text": "Tradeable. Deal 2 damage.",
                },
                {
                    "card_id": "FUTURE_001",
                    "id": "FUTURE_001",
                    "name": "Future Card",
                    "type": "LETTUCE_ABILITY",
                    "mechanics": ["FUTURE_KEYWORD"],
                    "text": "Future Keyword: Do something.",
                },
            ]
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "prepare",
            "--deck-name",
            "DriftDeck",
            "--deck-code",
            "AAECAf0EAAAA",
            "--out",
            str(out),
            "--runtime-root",
            str(runtime),
            "--cards-json",
            str(cards),
            "--allow-placeholder",
            "--json",
        ]
    )

    assert exit_code == 0
    reports = out / "reports"
    drift_report = json.loads(
        (reports / "mechanic_drift_report.json").read_text(encoding="utf-8")
    )
    operator = json.loads(
        (reports / "operator_summary.json").read_text(encoding="utf-8")
    )
    assert drift_report["non_blocking"] is True
    assert drift_report["text_only_mechanics"] == ["tradeable"]
    assert drift_report["unknown_mechanics"] == ["future_keyword"]
    assert drift_report["unknown_card_types"] == ["lettuce_ability"]
    assert operator["mechanic_drift_summary"]["unknown_mechanic_count"] == 1
    assert operator["mechanic_drift_summary"]["unknown_card_type_count"] == 1
    assert operator["runtime_apply_mode"] == "load_safe_apply"
