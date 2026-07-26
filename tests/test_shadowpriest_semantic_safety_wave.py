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
DECK_CODE_HASH = "fd7afada1f4a7f60bb269dc56188ddf83603e4bb0147a163d3e337be388917f2"
EXPECTED_CARD_COUNTS = {
    "CFM_637": 1,
    "DRG_056": 2,
    "DS1_233": 2,
    "GVG_009": 2,
    "NX2_019": 2,
    "REV_290": 2,
    "SCH_514": 2,
    "SW_444": 2,
    "SW_446": 2,
    "SW_448": 1,
    "TOY_381": 2,
    "TOY_518": 2,
    "VAC_419": 2,
    "VAC_512": 2,
    "WON_065": 2,
    "YOD_032": 2,
}
EXPECTED_CARD_IDS = frozenset(EXPECTED_CARD_COUNTS)
EXPECTED_CARD_JSON_FILES = frozenset(
    f"{card_id}.json" for card_id in EXPECTED_CARD_IDS
)
EXPECTED_RUNTIME_JSON_FILES = EXPECTED_CARD_JSON_FILES | {
    "GlobalValues.json",
    "Mulligan.json",
}


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


def _assert_runtime_rows(
    payload: dict,
    block_name: str,
    expected_signatures: list[tuple[str, str]],
) -> None:
    assert block_name in payload
    values = payload[block_name].get("values")
    assert isinstance(values, list) and values, f"{block_name} values must be non-empty"
    assert [
        (str(row["condition"]), str(row["value"]))
        for row in values
    ] == expected_signatures


def _assert_expected_cardid_coverage(
    roster_card_ids: set[str],
    runtime_json_files: set[str],
) -> None:
    assert roster_card_ids == EXPECTED_CARD_IDS
    assert runtime_json_files == EXPECTED_RUNTIME_JSON_FILES


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

    _assert_runtime_rows(
        payload,
        "BeforePlayCardBonus",
        [("*", "8"), ("*", "8"), ("*", "8")],
    )
    assert "BeforeBattlecryTargetBonus" not in payload
    assert "BeforeUseHeroPowerBonus" not in payload


@pytest.mark.parametrize(
    ("card_id", "block_name", "expected_signatures"),
    [
        ("DS1_233", "BeforePlayCardBonus", [("*", "12")]),
        (
            "GVG_009",
            "BeforePlayCardBonus",
            [("*", "10"), ("*", "10"), ("*", "10")],
        ),
        ("SW_446", "OnBoardBonus", [("*", "10")]),
        ("TOY_381", "OnBoardBonus", [("*", "8")]),
        ("VAC_419", "BeforePlayCardBonus", [("*", "10")]),
        (
            "SW_448",
            "BeforeUseHeroPowerBonus",
            [("*", "10"), ("*", "10"), ("*", "10")],
        ),
    ],
)
def test_supported_burn_aura_and_hero_power_rows_remain(
    package,
    card_id,
    block_name,
    expected_signatures,
):
    _assert_runtime_rows(
        _card(package, card_id),
        block_name,
        expected_signatures,
    )


def test_supported_runtime_row_proof_rejects_empty_values(package):
    payload = _card(package, "TOY_381")
    payload["OnBoardBonus"]["values"] = []

    with pytest.raises(AssertionError, match="values must be non-empty"):
        _assert_runtime_rows(payload, "OnBoardBonus", [("*", "8")])


def test_shadowpriest_package_identity_and_globalvalues_are_exact(package):
    identity = _report(package, "deck_identity.json")
    decode = _report(package, "deckstring_decode_receipt.json")
    validation = _report(package, "validation_report.json")
    baseline = _report(package, "globalvalues_baseline.json")
    baseline_receipt = _report(package, "globalvalues_baseline_receipt.json")
    profile = _report(package, "global_values_key_profile_report.json")
    globalvalues = _card(package, "GlobalValues")
    deck_dir = package / "CustomConfig" / "shadowpriest"

    roster_counts = {
        str(card["card_id"]): int(card["count"])
        for card in identity["cards"]
    }
    runtime_json_files = {path.name for path in deck_dir.glob("*.json")}
    _assert_expected_cardid_coverage(set(roster_counts), runtime_json_files)

    assert roster_counts == EXPECTED_CARD_COUNTS
    assert identity["card_count_total"] == 30
    assert identity["deck_code_hash"] == DECK_CODE_HASH
    assert identity["deck_name"] == "ShadowPriest"
    assert identity["deck_slug"] == "shadowpriest"
    assert identity["format"] == "FT_WILD"
    assert identity["hero_dbf_id"] == 813
    assert identity["sideboard_count"] == 0
    assert identity["unresolved_card_count"] == 0
    assert decode["card_count_total"] == 30
    assert decode["unique_card_count"] == 16
    assert decode["unresolved_card_count"] == 0
    assert decode["deck_code_length"] == len(DECK_CODE)

    assert validation["status"] == "passed"
    assert validation["errors"] == []
    assert validation["checked_files"] == len(EXPECTED_RUNTIME_JSON_FILES)

    baseline_keys = set(baseline)
    assert len(baseline_keys) == 38
    assert baseline_receipt["key_count"] == 38
    assert baseline_receipt["snapshot_status"] == "known_runtime_snapshot"
    assert baseline_receipt["source"] == "bundled_fallback"
    assert set(globalvalues) == baseline_keys | {"MyHeroPowerValue"}
    assert profile["key_count"] == 39
    assert set(profile["keys"]) == set(globalvalues)
    assert profile["expected_overlay_keys"] == []
    assert profile["generated_overlay_keys"] == ["MyHeroPowerValue"]
    assert profile["missing_overlay_keys"] == []
    assert profile["all_expected_overlay_keys_accounted_for"] is True
    assert profile["summary"] == {
        "all_baseline_keys_accounted_for": True,
        "all_expected_overlay_keys_accounted_for": True,
        "changed_key_count": 0,
        "expected_overlay_key_count": 0,
        "generated_overlay_key_count": 1,
        "key_count": 39,
        "missing_overlay_keys": [],
        "runtime_permission_impact": "none",
        "status": "baseline_confirmed",
        "unchanged_key_count": 39,
    }


def test_cardid_coverage_proof_rejects_missing_roster_or_file(package):
    identity = _report(package, "deck_identity.json")
    roster_card_ids = {str(card["card_id"]) for card in identity["cards"]}
    deck_dir = package / "CustomConfig" / "shadowpriest"
    runtime_json_files = {path.name for path in deck_dir.glob("*.json")}

    with pytest.raises(AssertionError):
        _assert_expected_cardid_coverage(
            roster_card_ids - {"WON_065"},
            runtime_json_files,
        )
    with pytest.raises(AssertionError):
        _assert_expected_cardid_coverage(
            roster_card_ids,
            runtime_json_files - {"TOY_518.json"},
        )


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
    _assert_runtime_rows(
        darkbishop,
        "BeforeUseHeroPowerBonus",
        [("*", "10"), ("*", "10"), ("*", "10")],
    )
    assert "InHandPlayPriority" not in darkbishop
    assert "BeforePlayCardBonus" not in darkbishop
