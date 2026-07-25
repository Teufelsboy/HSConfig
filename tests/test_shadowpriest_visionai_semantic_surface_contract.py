import json
from pathlib import Path

import pytest

from hsconfig.cli import main
from hsconfig.config_quality_contract import build_config_quality_report


SHADOWPRIEST_DECK_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)
SHADOWPRIEST_DECK_NAME = "ShadowPriest"


@pytest.fixture
def shadowpriest_package(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    package = tmp_path / "shadowpriest"
    code = main(
        [
            "prepare",
            "--deck-name",
            SHADOWPRIEST_DECK_NAME,
            "--deck-code",
            SHADOWPRIEST_DECK_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--source-documents-json",
            "tests/fixtures/source_documents_shadowpriest_strong.json",
            "--json",
        ]
    )
    assert code == 0

    reports_root = package / "reports"
    reports = {
        report_name: json.loads(
            (reports_root / filename).read_text(encoding="utf-8")
        )
        for report_name, filename in {
            "operator_summary": "operator_summary.json",
            "card_behavior_plan_report": "card_behavior_plan_report.json",
            "semantic_enrichment_report": "semantic_enrichment_report.json",
            "source_to_runtime_explainability": "source_to_runtime_explainability.json",
        }.items()
    }
    return package, reports


def read_card_json(package_root, card_id):
    path = package_root / "CustomConfig" / "shadowpriest" / f"{card_id}.json"
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_shadowpriest_package_is_source_backed_strong_without_default_only_surfaces(shadowpriest_package):
    package_root, reports = shadowpriest_package
    operator = reports["operator_summary"]

    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert operator["source_backed_status"] == "SOURCE_BACKED_STRONG"
    assert operator["runtime_apply_allowed"] is True
    assert operator["source_status_apply_blocking"] is False
    assert operator["default_only_runtime_surfaces"] == []
    assert operator["source_backed_strong_closure"]["status"] == "ready"


def test_shadowpriest_runtime_rows_match_card_semantics(shadowpriest_package):
    package_root, reports = shadowpriest_package

    shadowbomber = read_card_json(package_root, "GVG_009")
    twilight_deceptor = read_card_json(package_root, "SW_444")
    darkbishop = read_card_json(package_root, "SW_448")
    mind_sear = read_card_json(package_root, "NX2_019")
    cathedral = read_card_json(package_root, "REV_290")
    voidtouched = read_card_json(package_root, "SW_446")

    assert "BeforeBattlecryTargetBonus" not in shadowbomber
    assert "BeforeBattlecryTargetBonus" not in twilight_deceptor

    assert "BeforeUseHeroPowerBonus" in darkbishop
    assert "InHandPlayPriority" not in darkbishop
    assert "BeforePlayCardBonus" not in darkbishop

    assert "BeforePlayCardBonus" in mind_sear
    assert "BeforeBattlecryTargetBonus" not in mind_sear

    assert "BeforePlayCardBonus" in cathedral
    assert "BeforeBattlecryTargetBonus" not in cathedral
    assert "BeforeUseHeroPowerBonus" not in cathedral

    assert "OnBoardBonus" in voidtouched
    assert "BeforePlayCardBonus" in voidtouched


def test_shadowpriest_report_only_claims_do_not_create_runtime_gaps(shadowpriest_package):
    package_root, reports = shadowpriest_package
    operator = reports["operator_summary"]

    usefulness = operator["config_usefulness"]
    combo = usefulness["surfaces"]["combo"]
    explainability = operator["source_to_runtime_explainability_summary"]
    mechanic_visibility = operator["mechanic_visibility_summary"]

    assert usefulness["first_usefulness_gap"] != "combo_gap"
    assert combo["combo_expected"] is False
    assert combo["combo_row_count"] == 0
    assert explainability["cards_with_first_missing_link"] == 0

    warning_only = set(mechanic_visibility["warning_only_mechanics"])
    assert "location_activation" in warning_only
    assert "deckbuilding_modifier" not in warning_only
    assert "passive_start_effect" not in warning_only
    assert "shadowform" not in warning_only
    assert "start_of_game_keyword" not in warning_only
    assert "start_of_game_modifier" not in warning_only
    assert "trigger_visual" not in warning_only


def test_shadowpriest_quality_report_has_clean_visionai_semantic_surface_check(
    shadowpriest_package,
):
    package_root, _reports = shadowpriest_package

    quality = build_config_quality_report(package_root)
    check = quality["checks"]["visionai_semantic_surface"]

    assert check["status"] == "clean"
    assert check["non_targeted_battlecry_target_rows"] == []
    assert check["effect_only_body_rows"] == []
    assert check["unsupported_report_only_runtime_rows"] == []
    assert check["semantic_default_runtime_rows"] == []
