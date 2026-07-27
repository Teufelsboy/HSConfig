import json
from pathlib import Path

from hsconfig.cli import main
from hsconfig.config_quality_contract import build_config_quality_report
from hsconfig.source_closure_intake import build_source_closure_intake_receipt


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def test_shadowpriest_source_closure_intake_keeps_benedictus_effect_diagnostic_only():
    receipt = build_source_closure_intake_receipt("ShadowPriest", SHADOWPRIEST_CODE)
    rows_text = json.dumps(receipt["source_rows"], sort_keys=True)

    assert receipt["authority"] == "diagnostic_only"
    assert receipt["source_status_apply_blocking"] is False
    assert receipt["first_missing_source_action"] == "none"
    assert receipt["promotion_eligible_seed_count"] >= 1
    assert "hero_power_transform" in rows_text
    assert all(row["authority"] == "candidate_seed_only" for row in receipt["source_rows"])
    assert all(row["can_promote_runtime_claim"] is False for row in receipt["source_rows"])
    assert all(row["can_write_runtime_config"] is False for row in receipt["source_rows"])


def test_shadowpriest_semantic_qualifiers_preserve_effect_without_mulligan_keep(tmp_path: Path):
    out = tmp_path / "pkg"
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
            str(out),
        ]
    )

    reports = out / "reports"
    operator = json.loads((reports / "operator_summary.json").read_text(encoding="utf-8"))
    mulligan = json.loads(
        (out / "CustomConfig" / "shadowpriest" / "Mulligan.json").read_text(
            encoding="utf-8"
        )
    )

    assert code == 0
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert not any(
        row.get("mulligan") == "SW_448" and row.get("value") == "hold"
        for row in mulligan["Mulligan"]["values"]
    )


def test_semantically_gated_shadowpriest_keeps_benedictus_effect_not_opening_hand(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    out = tmp_path / "pkg"
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
            str(out),
            "--source-documents-json",
            "tests/fixtures/source_documents_shadowpriest_strong.json",
        ]
    )

    deck_dir = out / "CustomConfig" / "shadowpriest"
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    benedictus_source = json.loads(
        (deck_dir / "SW_448.json").read_text(encoding="utf-8")
    )
    benedictus_behavior = json.loads(
        (deck_dir / "EX1_625t.json").read_text(encoding="utf-8")
    )
    summary = json.loads(
        (out / "reports" / "operator_summary.json").read_text(encoding="utf-8")
    )
    behavior_report = json.loads(
        (out / "reports" / "card_behavior_plan_report.json").read_text(
            encoding="utf-8"
        )
    )
    quality = build_config_quality_report(out)
    mind_sear_rows = [
        row
        for row in behavior_report["rows"]
        if row.get("card_id") == "NX2_019"
        and row.get("surface_family") == "CARDID.json"
        and row.get("behavior_block")
        and row.get("meaningful_runtime_surface", True) is not False
    ]

    assert code == 0
    assert summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert quality["authority"] == "diagnostic_only"
    assert quality["apply_blocking"] is False
    assert quality["runtime_write_performed"] is False
    assert quality["checks"]["trace_completeness"]["runtime_rows_missing_trace"] == []
    assert quality["checks"]["closure_freshness"]["closure_schema_current"] is True
    assert quality["checks"]["closure_freshness"]["cards_missing_closure"] == 0
    assert quality["checks"]["darkbishop_boundary"]["mulligan_keep_present"] is False
    assert quality["checks"]["runtime_json"]["stray_cardid_files"] == []
    assert quality["checks"]["runtime_json"]["metadata_leaks"] == []
    assert quality["checks"]["mechanic_runtime_discipline"][
        "report_only_runtime_rows"
    ] == []
    assert not quality["checks"]["operator_summary"]["source_status_apply_blocking"]
    assert mind_sear_rows == []
    assert any(
        row["cards"] == ["NX2_019"]
        and row["reason"] == "semantic_surface_not_expressible"
        for row in behavior_report["suppressed"]
    )
    assert "SW_448" not in json.dumps(mulligan, sort_keys=True)
    assert benedictus_source["GameCardId"] == "SW_448"
    assert "BeforeUseHeroPowerBonus" not in benedictus_source
    assert benedictus_behavior["GameCardId"] == "EX1_625t"
    assert (
        "hero_power_transform" in json.dumps(benedictus_behavior, sort_keys=True)
        or "BeforeUseHeroPowerBonus" in benedictus_behavior
    )


def test_semantically_gated_shadowpriest_has_no_known_semantic_intent_fallbacks(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    out = tmp_path / "pkg"
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
            str(out),
            "--source-documents-json",
            "tests/fixtures/source_documents_shadowpriest_strong.json",
        ]
    )

    reports = out / "reports"
    behavior_report = json.loads(
        (reports / "card_behavior_plan_report.json").read_text(encoding="utf-8")
    )
    surface_intent = json.loads(
        (reports / "surface_intent.json").read_text(encoding="utf-8")
    )
    quality = build_config_quality_report(out)

    known_cards = {
        "DS1_233",
        "GVG_009",
        "NX2_019",
        "SCH_514",
        "SW_446",
        "TOY_381",
        "VAC_419",
        "VAC_512",
        "YOD_032",
    }
    semantic_default_rows = [
        {
            "card_id": row.get("card_id"),
            "behavior_block": row.get("behavior_block"),
            "intent": row.get("intent"),
            "reason": row.get("semantic_score", {}).get("reason"),
        }
        for row in behavior_report["rows"]
        if row.get("card_id") in known_cards
        and row.get("semantic_score", {}).get("reason") == "semantic_default"
    ]
    fallback_surface_rows = [
        {
            "card_id": row.get("card_id"),
            "surface": row.get("surface"),
            "intent": row.get("intent"),
            "intent_source": row.get("intent_source"),
        }
        for row in surface_intent["rows"]
        if row.get("card_id") in known_cards
        and row.get("intent_source") == "fallback"
    ]
    known_behavior_card_ids = {
        row.get("card_id")
        for row in behavior_report["rows"]
        if row.get("card_id") in known_cards
        and row.get("surface_family") == "CARDID.json"
        and row.get("behavior_block")
        and row.get("meaningful_runtime_surface", True) is not False
    }
    known_report_only_card_ids = known_cards - known_behavior_card_ids
    known_surface_intent_card_ids = {
        row.get("card_id")
        for row in surface_intent["rows"]
        if row.get("card_id") in known_cards
        and row.get("surface_family") == "CARDID.json"
    }

    assert code == 0
    assert known_behavior_card_ids == {
        "DS1_233",
        "SW_446",
        "TOY_381",
    }
    assert known_report_only_card_ids == {
        "GVG_009",
        "NX2_019",
        "SCH_514",
        "VAC_419",
        "VAC_512",
        "YOD_032",
    }
    assert known_surface_intent_card_ids == known_cards
    assert semantic_default_rows == []
    assert fallback_surface_rows == []
    assert quality["authority"] == "diagnostic_only"
    assert quality["apply_blocking"] is False
    assert quality["checks"]["card_behavior"]["semantic_default_rows"] == []


def test_captured_shadowpriest_mulligan_runtime_rows_are_policy_unique(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    out = tmp_path / "pkg"
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
            str(out),
            "--source-documents-json",
            "tests/fixtures/source_documents_shadowpriest_strong.json",
        ]
    )

    deck_dir = out / "CustomConfig" / "shadowpriest"
    reports = out / "reports"
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    plan_report = json.loads(
        (reports / "mulligan_plan_report.json").read_text(encoding="utf-8")
    )
    runtime_rows = mulligan["Mulligan"]["values"]
    runtime_keys = [
        (row.get("mulligan"), row.get("condition", "*"), row.get("value"))
        for row in runtime_rows
    ]

    assert code == 0
    assert runtime_keys == [
        ("SCH_514", "*", "hold"),
        ("NX2_019", "*", "hold"),
        ("VAC_419", "*", "hold"),
        ("*", "*", "discard"),
    ]
    assert len(runtime_keys) == len(set(runtime_keys))
    assert not any(
        row.get("mulligan") == "SW_448" and row.get("value") == "hold"
        for row in runtime_rows
    )
    assert plan_report["quality"]["merged_duplicate_rule_count"] == 0
    assert plan_report["quality"]["source_backed_keep_rule_count"] == 0
    assert plan_report["quality"]["policy_backed_keep_rule_count"] == 3
    assert plan_report["quality"]["suppressed_reasons"][
        "strategic_provenance_not_live_verified"
    ] == 2
    assert plan_report["quality"]["default_only"] is False


def test_shadowpriest_darkbishop_effect_visible_but_not_mulligan_keep_after_lifecycle(
    tmp_path: Path,
):
    out = tmp_path / "pkg"
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
            str(out),
        ]
    )

    deck_dir = out / "CustomConfig" / "shadowpriest"
    reports = out / "reports"
    mulligan_text = (deck_dir / "Mulligan.json").read_text(encoding="utf-8")
    darkbishop_source = json.loads(
        (deck_dir / "SW_448.json").read_text(encoding="utf-8")
    )
    shadow_hero_power_text = (deck_dir / "EX1_625t.json").read_text(encoding="utf-8")
    audit = json.loads((reports / "source_contract_audit.json").read_text(encoding="utf-8"))
    claim_rows = audit["claim_rows"]
    darkbishop_claim_ids = {
        claim_id
        for claim_id, row in claim_rows.items()
        if "SW_448" in row.get("cards", [])
    }
    darkbishop_lifecycle_rows = [
        row
        for row in audit["claim_lifecycle_rows"]
        if row.get("claim_id") in darkbishop_claim_ids
    ]

    assert code == 0
    assert "SW_448" not in mulligan_text
    assert darkbishop_source["GameCardId"] == "SW_448"
    assert "BeforeUseHeroPowerBonus" not in darkbishop_source
    assert "BeforeUseHeroPowerBonus" in shadow_hero_power_text
    assert not (deck_dir / "Presume.json").exists()
    assert not (deck_dir / "Concede.json").exists()
    assert any(
        row["claim_kind"] == "hero_power_transform"
        and row["builder_or_router_decision"] == "emitted"
        and "EX1_625t.json" in row["emitted_files"]
        for row in darkbishop_lifecycle_rows
    )
    assert not any(
        row["claim_kind"] == "mulligan_keep"
        and row["builder_or_router_decision"] == "emitted"
        for row in darkbishop_lifecycle_rows
    )


def test_shadowpriest_deckinput_only_build_validate_and_apply(tmp_path: Path, capsys):
    package = tmp_path / "shadowpriest_package"
    runtime = tmp_path / "runtime"

    build_code = main(
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

    validate_code = main(["validate", "--package", str(package), "--json"])
    validate_out = json.loads(capsys.readouterr().out)

    apply_code = main(
        [
            "apply",
            "--package",
            str(package),
            "--runtime-root",
            str(runtime),
            "--json",
        ]
    )
    apply_out = json.loads(capsys.readouterr().out)

    reports = package / "reports"
    deck_dir = package / "CustomConfig" / "shadowpriest"
    runtime_deck_dir = runtime / "CustomConfig" / "shadowpriest"
    runtime_deck_config = runtime / "CustomConfig" / "deck_config.ini"
    deck_identity = json.loads((reports / "deck_identity.json").read_text(encoding="utf-8"))
    manifest = json.loads((reports / "input_manifest.json").read_text(encoding="utf-8"))
    receipt = json.loads((reports / "deckstring_decode_receipt.json").read_text(encoding="utf-8"))
    card_id_map = json.loads((reports / "card_id_map.json").read_text(encoding="utf-8"))
    operator_summary = json.loads((reports / "operator_summary.json").read_text(encoding="utf-8"))
    source_contract_audit = json.loads(
        (reports / "source_contract_audit.json").read_text(encoding="utf-8")
    )
    source_to_runtime_explainability = json.loads(
        (reports / "source_to_runtime_explainability.json").read_text(
            encoding="utf-8"
        )
    )
    semantic_report = json.loads(
        (reports / "semantic_enrichment_report.json").read_text(encoding="utf-8")
    )
    semantic_audit = (reports / "card_semantic_audit.md").read_text(encoding="utf-8")
    research_card_roles = json.loads(
        (reports / "research" / "card_role_map.json").read_text(encoding="utf-8")
    )
    research_globalvalues = json.loads(
        (reports / "research" / "globalvalue_intent.json").read_text(encoding="utf-8")
    )
    contract = json.loads((reports / "gameplan_contract.json").read_text(encoding="utf-8"))
    globalvalues_authority = json.loads(
        (reports / "global_values_authority_matrix.json").read_text(encoding="utf-8")
    )
    globalvalues_profile = json.loads(
        (reports / "globalvalues_profile.json").read_text(encoding="utf-8")
    )
    plan_report = json.loads(
        (reports / "mulligan_plan_report.json").read_text(encoding="utf-8")
    )
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    darkbishop_contract = contract["cards"]["SW_448"]
    darkbishop_source_config = deck_dir / "SW_448.json"
    darkbishop_source = json.loads(
        darkbishop_source_config.read_text(encoding="utf-8")
    )
    shadow_hero_power_config = deck_dir / "EX1_625t.json"
    shadow_hero_power_runtime = json.loads(
        shadow_hero_power_config.read_text(encoding="utf-8")
    )
    mulligan_values = mulligan["Mulligan"]["values"]
    policy_hold_rows = [
        row
        for row in mulligan_values
        if row.get("value") == "hold" or row.get("action") == "hold"
    ]
    policy_hold_text = json.dumps(policy_hold_rows, sort_keys=True)
    mulligan_text = json.dumps(mulligan, sort_keys=True)

    assert build_code == 0
    assert validate_code == 0
    assert validate_out["status"] == "passed"
    assert operator_summary["technical_status"] == "VALID_PACKAGE"
    assert operator_summary["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert operator_summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert operator_summary["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    assert operator_summary["runtime_load_safe"] is True
    assert operator_summary["runtime_apply_mode"] == "load_safe_apply"
    assert operator_summary["runtime_apply_allowed"] is True
    assert operator_summary["source_contract_audit_summary"]["non_blocking"] is True
    assert (
        operator_summary["source_to_runtime_explainability_summary"]["non_blocking"]
        is True
    )
    assert (
        operator_summary["source_to_runtime_explainability_summary"]["claims_total"]
        == source_to_runtime_explainability["summary"]["claims_total"]
    )
    assert source_to_runtime_explainability["authority"] == "diagnostic_only"
    assert source_to_runtime_explainability["apply_blocking"] is False
    assert source_contract_audit["card_rows"]["SW_448"]["runtime_surfaces"] == []
    assert (
        operator_summary["source_informed_apply_readiness"]["status"]
        == "blocked"
    )
    assert operator_summary["source_informed_apply_readiness"]["blocking_reasons"] == [
        "cards_need_condition_lowering",
        "contract_gap_not_strong_evidence",
    ]
    assert apply_code == 0
    assert apply_out["status"] == "applied"
    assert apply_out["apply_gate"]["status"] == "allowed"
    assert apply_out["apply_gate"]["mode"] == "load_safe_apply"
    assert (
        apply_out["apply_gate"]["reasons"][0]["reason"]
        == "runtime_load_safe_package"
    )
    assert deck_identity["deck_name"] == "ShadowPriest"
    assert deck_identity["deck_slug"] == "shadowpriest"
    assert deck_identity["hero_dbf_id"] == 813
    assert deck_identity["format"] == "FT_WILD"
    assert deck_identity["card_count_total"] == 30
    assert manifest["card_source"] == "deckstring"
    assert manifest["format"] == "FT_WILD"
    assert receipt["unresolved_card_count"] == 0
    assert card_id_map["545"]["card_id"] == "DS1_233"
    assert any(card["card_id"] == "SW_448" for card in semantic_report["cards"])
    assert (reports / "card_semantic_audit.md").exists()
    assert "SW_448 Darkbishop Benedictus" in semantic_audit
    assert "EX1_625t Mind Spike" in semantic_audit
    assert "Mind Spike is a damage Hero Power" in semantic_audit
    assert "hero_power_transform" in darkbishop_contract["roles"]
    assert "hero_power_pressure" in darkbishop_contract["roles"]
    assert darkbishop_contract["linked_entities"][0]["card_id"] == "EX1_625t"
    assert contract["deckwide_effects"][0]["target_name"] == "Mind Spike"
    assert (
        contract["card_usage_expectations"]["SW_448"]["expected_use"]
        == "start_of_game_shadowform_enables_hero_power_pressure"
    )
    assert research_card_roles["SW_448"]["confidence"] == "source_backed_static_semantics"
    assert "hero_power_transform" in research_card_roles["SW_448"]["roles"]
    assert research_globalvalues["overlays"]["MyHeroPowerValue"] == "increase"
    assert globalvalues_authority["posture"] == "baseline"
    assert globalvalues_authority["allowed_step1_overlays"][0]["key"] == "baseline"
    assert (
        globalvalues_authority["allowed_step1_overlays"][0]["reason"]
        == "no_source_backed_posture_overlay"
    )
    assert "MyHeroPowerValue" not in {
        row["key"] for row in globalvalues_authority["allowed_step1_overlays"]
    }
    assert "MyHeroPowerValue" not in globalvalues_profile["keys"]
    assert (deck_dir / "GlobalValues.json").exists()
    assert (deck_dir / "Mulligan.json").exists()
    assert policy_hold_rows
    assert "SW_448" not in policy_hold_text
    assert operator_summary["config_usefulness"]["surfaces"]["mulligan"]["default_only"] is False
    assert operator_summary["default_only_runtime_surfaces"] == []
    assert operator_summary["mulligan_policy_status"]["default_only"] is False
    assert plan_report["quality"]["policy_backed_keep_rule_count"] >= 1
    assert (deck_dir / "DS1_233.json").exists()
    assert darkbishop_source_config.exists()
    assert shadow_hero_power_config.exists()
    assert darkbishop_source["GameCardId"] == "SW_448"
    assert "BeforeUseHeroPowerBonus" not in darkbishop_source
    assert shadow_hero_power_runtime["GameCardId"] == "EX1_625t"
    assert shadow_hero_power_runtime["BeforeUseHeroPowerBonus"]["values"]
    darkbishop_claims = [
        row
        for row in source_contract_audit["claim_rows"].values()
        if "SW_448" in row.get("cards", [])
    ]
    darkbishop_claim_ids = {row["claim_id"] for row in darkbishop_claims}
    darkbishop_lifecycle_rows = [
        row
        for row in source_contract_audit["claim_lifecycle_rows"]
        if row.get("claim_id") in darkbishop_claim_ids
    ]
    darkbishop_mulligan_lifecycle = [
        row
        for row in darkbishop_lifecycle_rows
        if row["claim_kind"] == "mulligan_keep"
    ]
    darkbishop_effect_lifecycle = [
        row
        for row in darkbishop_lifecycle_rows
        if row["claim_kind"] == "hero_power_transform"
    ]
    explainability_card_rows = {
        row["card_id"]: row for row in source_to_runtime_explainability["card_rows"]
    }
    darkbishop_explainability = explainability_card_rows["SW_448"]
    darkbishop_explainability_claims = [
        row
        for row in source_to_runtime_explainability["claim_rows"]
        if row["claim_id"] in darkbishop_claim_ids
    ]

    assert darkbishop_effect_lifecycle
    assert darkbishop_explainability["strongest_claim_kind"] == "hero_power_transform"
    assert "EX1_625t.json" in darkbishop_explainability["emitted_runtime_files"]
    assert "Mulligan.json" not in darkbishop_explainability["emitted_runtime_files"]
    assert darkbishop_explainability["apply_blocked"] is False
    assert darkbishop_explainability["next_source_action"] == "none"
    assert any(
        row["claim_kind"] == "hero_power_transform"
        and row["builder_or_router_decision"] == "emitted"
        and "EX1_625t.json" in row["emitted_runtime_files"]
        for row in darkbishop_explainability_claims
    )
    assert not any(
        row["claim_kind"] == "mulligan_keep"
        for row in darkbishop_explainability_claims
    )
    assert all(
        row["builder_or_router_decision"] == "emitted"
        for row in darkbishop_effect_lifecycle
    )
    assert all(
        row["runtime_surface"] in {"EX1_625t.json", "<CARDID>.json", "CARDID.json"}
        or "EX1_625t.json" in row["emitted_files"]
        for row in darkbishop_effect_lifecycle
    )
    assert darkbishop_mulligan_lifecycle == []
    assert "Darkbishop Benedictus" not in mulligan_text
    assert "Mind Spike" in semantic_audit
    assert any(
        row["claim_kind"] == "hero_power_transform"
        and row["lane"] == "runtime_lowered"
        and "cardid" in row["lowered_surfaces"]
        for row in darkbishop_claims
    )
    assert not any(
        row["claim_kind"] == "mulligan_keep"
        and row["lane"] == "runtime_lowered"
        for row in darkbishop_claims
    )
    assert any(
        row["claim_kind"] == "hero_power_transform"
        and row["builder_or_router_decision"] == "emitted"
        and (
            row["runtime_surface"] in {"EX1_625t.json", "<CARDID>.json", "CARDID.json"}
            or "EX1_625t.json" in row["emitted_files"]
        )
        for row in darkbishop_lifecycle_rows
    )
    assert not any(
        row["claim_kind"] == "mulligan_keep"
        and row["builder_or_router_decision"] == "emitted"
        for row in darkbishop_lifecycle_rows
    )
    assert not any(row.get("mulligan") == "SW_448" for row in mulligan_values)
    assert "SW_448" not in mulligan_text
    assert not (deck_dir / "Presume.json").exists()
    assert not (deck_dir / "Concede.json").exists()
    assert runtime.exists()
    assert (runtime / "CustomConfig").exists()
    assert runtime_deck_dir.exists()
    assert runtime_deck_config.exists()
