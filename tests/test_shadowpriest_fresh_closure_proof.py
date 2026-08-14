import json
from pathlib import Path

from hsconfig.cli import main


SHADOWPRIEST_DECK_NAME = "ShadowPriest"
SHADOWPRIEST_DECK_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)
DARKBISHOP_CARD_ID = "SW_448"
SHADOW_HERO_POWER_CARD_ID = "EX1_625t"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_fresh_shadowpriest_package_has_complete_closure_and_darkbishop_boundary(
    tmp_path: Path,
    capsys,
):
    research = tmp_path / "research"
    package = tmp_path / "package"
    runtime = tmp_path / "runtime"

    research_code = main(
        [
            "research-deck",
            "--deck-name",
            SHADOWPRIEST_DECK_NAME,
            "--deck-code",
            SHADOWPRIEST_DECK_CODE,
            "--out",
            str(research),
            "--json",
        ]
    )
    research_payload = json.loads(capsys.readouterr().out)

    prepare_code = main(
        [
            "prepare",
            "--deck-name",
            SHADOWPRIEST_DECK_NAME,
            "--deck-code",
            SHADOWPRIEST_DECK_CODE,
            "--runtime-root",
            str(runtime),
            "--out",
            str(package),
            "--guide-sources-json",
            str(research / "guide_sources.json"),
            "--json",
        ]
    )
    prepare_payload = json.loads(capsys.readouterr().out)

    reports = package / "reports"
    operator = _json(reports / "operator_summary.json")
    explainability = _json(reports / "source_to_runtime_explainability.json")
    deck_slug = prepare_payload["deck_slug"]
    deck_dir = package / "CustomConfig" / deck_slug
    mulligan = _json(deck_dir / "Mulligan.json")
    darkbishop = _json(deck_dir / f"{DARKBISHOP_CARD_ID}.json")
    shadow_hero_power = _json(deck_dir / f"{SHADOW_HERO_POWER_CARD_ID}.json")

    assert research_code == 0
    assert research_payload["status"] == "OK"
    assert prepare_code == 0
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["runtime_apply_allowed"] is True

    explainability_summary = operator["source_to_runtime_explainability_summary"]
    assert explainability["authority"] == "diagnostic_only"
    assert explainability["apply_blocking"] is False
    assert explainability_summary["non_blocking"] is True
    assert explainability_summary["cards_missing_closure"] == 0
    assert explainability_summary["closure_schema_current"] is True

    card_rows = explainability["card_rows"]
    assert card_rows
    assert len(card_rows) == explainability["summary"]["cards_total"]
    assert all(isinstance(row.get("closure"), dict) for row in card_rows)
    assert {
        row["closure"]["lane"]
        for row in card_rows
    } <= {
        "source_backed_runtime_lowered",
        "explicit_gap",
        "runtime_backed",
        "source_action_needed",
        "diagnostic_only",
        "baseline_only_visible",
    }
    assert not [
        row["card_id"]
        for row in card_rows
        if row["closure"]["lane"] == "baseline_only_visible"
        and row["closure"]["default_only_risk"] is not True
    ]

    assert operator["default_only_runtime_surfaces"] == []
    assert operator["default_only_runtime_surface_details"] == []
    surface_rows = {row["surface"]: row for row in operator["surface_status_ledger"]}
    assert surface_rows["mulligan"]["status"] in {
        "source_backed",
        "policy_backed",
        "static_semantics_backed",
        "warning_only",
    }
    assert all(
        row["status"] != "default_only"
        for row in operator["surface_status_ledger"]
    )
    assert all(
        row["operator_impact"] == "diagnostic_only"
        for row in operator["surface_status_ledger"]
    )

    mulligan_text = json.dumps(mulligan, sort_keys=True)
    assert DARKBISHOP_CARD_ID not in mulligan_text
    assert darkbishop["GameCardId"] == DARKBISHOP_CARD_ID
    assert "BeforeUseHeroPowerBonus" not in darkbishop
    assert shadow_hero_power["GameCardId"] == SHADOW_HERO_POWER_CARD_ID
    shadow_hero_power_text = json.dumps(shadow_hero_power, sort_keys=True)
    assert "BeforeUseHeroPowerBonus" in shadow_hero_power_text
    assert "hero_power" in shadow_hero_power_text.lower()
