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
    mulligan_text = "\n".join(
        path.read_text(encoding="utf-8") for path in package.glob("CustomConfig/*/Mulligan.json")
    )

    assert code == 0
    assert summary["status"] == "OK"
    assert summary["source_autopilot_path"] == str(out / "02_source_autopilot")
    assert summary["source_documents_json"] == str(out / "02_source_autopilot" / "source_documents.json")
    assert autopilot_report["strong_candidate"] is True
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert operator["runtime_apply_mode"] == "load_safe_apply"
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

    assert code == 0
    assert autopilot_report["strong_candidate"] is False
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["semantic_status"] != "SOURCE_BACKED_STRONG"


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
