from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main


FIXTURES = Path(__file__).parent / "fixtures"
SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_shadow_cards_json(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "cards": [
                    {
                        "card_id": "SW_448",
                        "name": "Darkbishop Benedictus",
                        "cost": 5,
                        "count": 1,
                        "text": "Start of Game: If the spells in your deck are all Shadow, enter Shadowform.",
                    },
                    {
                        "card_id": "SW_446",
                        "name": "Voidtouched Attendant",
                        "cost": 1,
                        "count": 2,
                    },
                    {"card_id": "TOY_381", "name": "Papercraft Angel", "cost": 3, "count": 2},
                    {"card_id": "SW_444", "name": "Twilight Deceptor", "cost": 2, "count": 2},
                    {"card_id": "SCH_514", "name": "Raise Dead", "cost": 0, "count": 2},
                    {"card_id": "GVG_009", "name": "Shadowbomber", "cost": 1, "count": 2},
                ]
            }
        ),
        encoding="utf-8",
    )


def _write_thin_cards_json(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "cards": [
                    {
                        "card_id": "CARD_001",
                        "name": "Fixture Card",
                        "cost": 1,
                        "count": 2,
                        "text": "Battlecry: Deal 1 damage.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def _stub_empty_fetches(monkeypatch) -> None:
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_collectible_cards",
        lambda timeout=10.0: [],
    )


def test_configure_auto_source_builds_load_safe_package_without_darkbishop_mulligan(
    tmp_path: Path,
    monkeypatch,
):
    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_shadow_cards_json(cards_json)
    out = tmp_path / "configure"

    code = main(
        [
            "configure",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--auto-source",
            "--source-search-results-json",
            str(FIXTURES / "source_search_shadowpriest_2026.json"),
            "--json",
        ]
    )

    summary = _read_json(out / "configure_summary.json")
    autopilot_report = _read_json(out / "02_source_autopilot" / "source_autopilot_report.json")
    package = out / "04_package"
    operator = _read_json(package / "reports" / "operator_summary.json")
    source_closure_receipt = summary["source_closure_receipt"]
    source_evidence_closure = _read_json(
        package / "reports" / "source_evidence_closure.json"
    )
    ownership = _read_json(package / "reports" / "output_ownership_manifest.json")
    mulligan_text = "\n".join(
        path.read_text(encoding="utf-8") for path in package.glob("CustomConfig/*/Mulligan.json")
    )
    ownership_rows = {row["file"]: row for row in ownership["files"]}
    generated_files = {path.replace("\\", "/") for path in operator["generated_files"]}

    assert code == 0
    assert summary["status"] == "OK"
    assert summary["source_autopilot_path"] == str(out / "02_source_autopilot")
    assert summary["source_documents_json"] == str(out / "02_source_autopilot" / "source_documents.json")
    assert autopilot_report["strong_candidate"] is True
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] == "STATIC_SEMANTICS_USABLE"
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert source_closure_receipt["authority"] == "diagnostic_only"
    assert source_closure_receipt["operator_gate"] == "reports/operator_summary.json"
    assert source_closure_receipt["normal_apply_authority"] == (
        "reports/operator_summary.json"
    )
    assert source_closure_receipt["apply_blocking"] is False
    assert source_closure_receipt["runtime_write_performed"] is False
    assert source_closure_receipt["source_backed_status"] == operator["source_backed_status"]
    assert source_closure_receipt["source_status_apply_blocking"] is False
    assert source_closure_receipt["first_missing_source_action"] == "inspect_card_gap"
    assert source_closure_receipt["default_only_clean"] is True
    assert source_closure_receipt["default_only_runtime_surfaces"] == []
    assert source_closure_receipt["source_closure_lane"] == "source_action_needed"
    assert source_closure_receipt["compiled_claim_count"] >= 1
    assert source_closure_receipt["runtime_lowerable_claim_count"] >= 1
    for key in (
        "generic_low_confidence_cards",
        "uncovered_cards",
        "source_evidence_warnings",
        "cards_needing_guide_claims",
        "cards_needing_runtime_surface",
        "cards_needing_mulligan_claims",
        "cards_needing_combo_sequence",
        "cards_needing_condition_lowering",
        "cards_needing_mechanic_lowering",
    ):
        assert operator["guide_strength_summary"][key] == 0
    assert "SW_448" not in mulligan_text
    assert list(package.glob("CustomConfig/*/SW_448.json"))
    assert source_evidence_closure["authority"] == "diagnostic_only"
    assert source_evidence_closure["apply_blocking"] is False
    assert source_evidence_closure["operator_gate"] == "reports/operator_summary.json"
    assert source_evidence_closure["semantic_status"] == operator["semantic_status"]
    assert "reports/source_evidence_closure.json" in generated_files
    assert (
        ownership_rows["reports/source_evidence_closure.json"]["authority"]
        == "diagnostic_source_evidence_closure"
    )
    assert (
        ownership_rows["reports/source_evidence_closure.json"]["classification"]
        == "diagnostic"
    )
    assert ownership_rows["reports/source_evidence_closure.json"]["can_block_apply"] is False


def test_configure_auto_source_keeps_decklist_only_non_strong_but_load_safe(
    tmp_path: Path,
    monkeypatch,
):
    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_thin_cards_json(cards_json)
    out = tmp_path / "configure"

    code = main(
        [
            "configure",
            "--deck-name",
            "ThinDeck",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--auto-source",
            "--source-search-results-json",
            str(FIXTURES / "source_search_decklist_only.json"),
            "--json",
        ]
    )

    autopilot_report = _read_json(out / "02_source_autopilot" / "source_autopilot_report.json")
    operator = _read_json(out / "04_package" / "reports" / "operator_summary.json")
    source_closure_receipt = _read_json(out / "configure_summary.json")[
        "source_closure_receipt"
    ]

    assert code == 0
    assert autopilot_report["strong_candidate"] is False
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["semantic_status"] != "SOURCE_BACKED_STRONG"
    assert source_closure_receipt["authority"] == "diagnostic_only"
    assert source_closure_receipt["apply_blocking"] is False
    assert source_closure_receipt["source_status_apply_blocking"] is False
    assert source_closure_receipt["source_backed_status"] == operator["source_backed_status"]
    assert source_closure_receipt["source_strong_ready"] is False
    assert source_closure_receipt["source_closure_lane"] in {
        "mulligan_claim_needed",
        "runtime_lowerable_claim_needed",
        "source_action_needed",
    }
    assert source_closure_receipt["next_report_to_open"] == (
        "reports/source_to_runtime_explainability.json"
    )


def test_configure_auto_source_keeps_empty_source_records_non_strong_but_load_safe(
    tmp_path: Path,
    monkeypatch,
):
    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_thin_cards_json(cards_json)
    source_json = tmp_path / "empty_sources.json"
    source_json.write_text(json.dumps({"records": []}), encoding="utf-8")
    out = tmp_path / "configure"

    code = main(
        [
            "configure",
            "--deck-name",
            "ThinDeck",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--auto-source",
            "--source-search-results-json",
            str(source_json),
            "--json",
        ]
    )

    autopilot_report = _read_json(out / "02_source_autopilot" / "source_autopilot_report.json")
    operator = _read_json(out / "04_package" / "reports" / "operator_summary.json")

    assert code == 0
    assert autopilot_report["strong_candidate"] is False
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["semantic_status"] != "SOURCE_BACKED_STRONG"


def test_configure_online_source_uses_registry_when_source_url_is_omitted(
    tmp_path: Path,
    monkeypatch,
):
    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_shadow_cards_json(cards_json)
    fixture_map = tmp_path / "fixture_url_map.json"
    fixture_map.write_text(
        json.dumps(
            {
                "https://www.hearthpwn.com/decks/1461644-voidburn-wild-aggro-shadow-priest": str(
                    FIXTURES / "source_guides" / "shadowpriest_current_guide.html"
                )
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "configure"

    code = main(
        [
            "configure",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--online-source",
            "--source-fixture-url-map-json",
            str(fixture_map),
            "--json",
        ]
    )

    summary = _read_json(out / "configure_summary.json")
    acquisition = _read_json(out / "02_source_acquisition" / "source_acquisition_report.json")
    autopilot = _read_json(out / "03_source_autopilot" / "source_autopilot_report.json")
    operator = _read_json(out / "04_package" / "reports" / "operator_summary.json")

    assert code == 0
    assert any(
        "voidburn-wild-aggro-shadow-priest" in url
        for url in summary["source_candidate_urls"]
    )
    assert summary["source_urls"] == summary["source_candidate_urls"]
    assert summary["source_candidate_plan_path"] == str(
        out / "01_manifest" / "source_candidate_plan.json"
    )
    assert summary["source_candidate_plan_summary"]["authority"] == (
        "diagnostic_source_candidate_plan"
    )
    assert summary["source_candidate_plan_summary"]["apply_blocking"] is False
    assert summary["source_candidate_plan_summary"]["source_status_apply_blocking"] is False
    assert summary["source_candidate_plan_summary"]["query_count"] >= 1
    assert acquisition["candidate_registry_url_count"] == 1
    assert acquisition["attempted_url_count"] == 1
    assert acquisition["source_record_count"] == 1
    assert autopilot["runtime_apply_authority"] == "reports/operator_summary.json"
    assert operator["runtime_apply_contract"]["apply_authority"] == (
        "reports/operator_summary.json"
    )
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["default_only_runtime_surfaces"] == []


def test_configure_auto_source_requires_source_search_results_json(
    tmp_path: Path,
    monkeypatch,
):
    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_shadow_cards_json(cards_json)
    out = tmp_path / "configure"

    code = main(
        [
            "configure",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--auto-source",
            "--json",
        ]
    )

    summary = _read_json(out / "configure_summary.json")

    assert code == 1
    assert summary["status"] == "failed"
    assert summary["stage"] == "source-autopilot"
    assert "--source-search-results-json is required when --auto-source is used" in summary[
        "errors"
    ]
