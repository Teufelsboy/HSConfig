from __future__ import annotations

import json
from pathlib import Path

import pytest

from hsconfig.cli import main
from hsconfig.config_quality_contract import build_config_quality_report


DECK_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


@pytest.fixture
def package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    output = tmp_path / "shadowpriest"
    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            DECK_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(output),
            "--source-documents-json",
            "tests/fixtures/source_documents_shadowpriest_strong.json",
            "--json",
        ]
    )
    assert code == 0
    return output


def _card(package: Path, card_id: str) -> dict:
    path = package / "CustomConfig" / "shadowpriest" / f"{card_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _report(package: Path, name: str) -> dict:
    path = package / "reports" / name
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "card_id",
    ["CFM_637", "DRG_056", "YOD_032", "SCH_514", "SW_444", "NX2_019", "VAC_512"],
)
def test_risky_static_cards_have_no_unconditional_action_row(package, card_id):
    payload = _card(package, card_id)

    assert "InHandPlayPriority" not in payload
    assert "BeforePlayCardBonus" not in payload
    assert "BeforeBattlecryTargetBonus" not in payload


def test_cathedral_only_keeps_supported_deploy_semantics(package):
    payload = _card(package, "REV_290")

    assert "BeforePlayCardBonus" in payload
    assert "BeforeBattlecryTargetBonus" not in payload
    assert "BeforeUseHeroPowerBonus" not in payload


def test_supported_burn_aura_and_hero_power_rows_remain(package):
    assert "BeforePlayCardBonus" in _card(package, "DS1_233")
    assert "BeforePlayCardBonus" in _card(package, "GVG_009")
    assert "OnBoardBonus" in _card(package, "SW_446")
    assert "OnBoardBonus" in _card(package, "TOY_381")
    assert "BeforePlayCardBonus" in _card(package, "VAC_419")
    assert "BeforeUseHeroPowerBonus" in _card(package, "SW_448")


def test_shadowpriest_runtime_rows_are_report_traced(package):
    quality = build_config_quality_report(package)
    trace = quality["checks"]["runtime_row_trace_inventory"]

    assert trace["status"] == "clean"
    assert trace["unreported_runtime_rows"] == []
    assert trace["reported_rows_missing_runtime"] == []
    assert trace["physical_cardid_runtime_rows"] == trace["reported_cardid_runtime_rows"]


def test_shadowpriest_is_load_safe_without_claiming_semantic_closure(package):
    operator = _report(package, "operator_summary.json")

    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_allowed"] is True
    assert operator["load_safe_to_install"] is True
    assert operator["semantic_handoff_status"] in {"attention", "insufficient_evidence"}
    assert "semantic_surface_not_expressible" in operator["semantic_handoff_reasons"]


def test_darkbishop_effect_does_not_become_mulligan_or_body_priority(package):
    mulligan = _card(package, "Mulligan")
    darkbishop = _card(package, "SW_448")

    selectors = [
        row["mulligan"]
        for row in mulligan["Mulligan"]["values"]
        if row["value"] == "hold"
    ]
    assert "SW_448" not in selectors
    assert "BeforeUseHeroPowerBonus" in darkbishop
    assert "InHandPlayPriority" not in darkbishop
    assert "BeforePlayCardBonus" not in darkbishop
