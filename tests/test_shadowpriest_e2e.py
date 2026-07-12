import json
from pathlib import Path

from hsconfig.cli import main


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
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
    mulligan = json.loads((deck_dir / "Mulligan.json").read_text(encoding="utf-8"))
    darkbishop_contract = contract["cards"]["SW_448"]
    darkbishop_card_config = deck_dir / "SW_448.json"
    darkbishop_runtime_config = json.loads(
        darkbishop_card_config.read_text(encoding="utf-8")
    )
    mulligan_values = mulligan["Mulligan"]["values"]
    mulligan_text = json.dumps(mulligan, sort_keys=True)

    assert build_code == 0
    assert validate_code == 0
    assert validate_out["status"] == "passed"
    assert operator_summary["technical_status"] == "VALID_PACKAGE"
    assert operator_summary["semantic_status"] == "STATIC_SEMANTICS_USABLE"
    assert operator_summary["next_action"] == "READY_TO_APPLY_WITH_WARNINGS"
    assert operator_summary["apply_policy"] == "ALLOWED_WITH_WARNINGS"
    assert operator_summary["runtime_load_safe"] is True
    assert operator_summary["runtime_apply_mode"] == "load_safe_apply"
    assert operator_summary["runtime_apply_allowed"] is True
    assert operator_summary["source_informed_apply_readiness"]["status"] == "not_applicable"
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
    hero_power_profile = globalvalues_profile["keys"]["MyHeroPowerValue"]
    assert hero_power_profile["decision"] != "overlay_changed"
    assert (deck_dir / "GlobalValues.json").exists()
    assert (deck_dir / "Mulligan.json").exists()
    assert (deck_dir / "DS1_233.json").exists()
    assert darkbishop_card_config.exists()
    assert darkbishop_runtime_config["GameCardId"] == "SW_448"
    assert darkbishop_runtime_config["BeforeUseHeroPowerBonus"]["values"]
    assert not any(row.get("mulligan") == "SW_448" for row in mulligan_values)
    assert "SW_448" not in mulligan_text
    assert not (deck_dir / "Presume.json").exists()
    assert not (deck_dir / "Concede.json").exists()
    assert runtime.exists()
    assert (runtime / "CustomConfig").exists()
    assert runtime_deck_dir.exists()
    assert runtime_deck_config.exists()
