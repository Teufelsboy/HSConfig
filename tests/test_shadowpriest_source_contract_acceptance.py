from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main

from tests.test_configure_auto_source import (
    SHADOWPRIEST_CODE,
    _stub_empty_fetches,
    _write_shadow_cards_json,
)


FIXTURES = Path(__file__).parent / "fixtures"
SOURCE_MATCHING_SHADOWPRIEST_CODE = "AAEBAa0GAbv3AwWRD9fOA6P3A633A8SoBgAA"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_configure_shadowpriest_closes_strong_source_contract(tmp_path: Path, monkeypatch):
    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_shadow_cards_json(cards_json)
    out = tmp_path / "configure"
    source_url = "https://example.test/current-shadowpriest-guide"
    source_fixture = tmp_path / "shadowpriest_current_guide.html"
    source_fixture.write_text(
        (FIXTURES / "source_pages" / "shadowpriest_current_guide.html")
        .read_text(encoding="utf-8")
        .replace(SHADOWPRIEST_CODE, SOURCE_MATCHING_SHADOWPRIEST_CODE),
        encoding="utf-8",
    )
    fixture_map = tmp_path / "fixture_map.json"
    fixture_map.write_text(
        json.dumps(
            {
                source_url: str(
                    source_fixture
                )
            }
        ),
        encoding="utf-8",
    )

    assert main(
        [
            "configure",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SOURCE_MATCHING_SHADOWPRIEST_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--online-source",
            "--auto-source",
            "--source-url",
            source_url,
            "--source-fixture-url-map-json",
            str(fixture_map),
            "--json",
        ]
    ) == 0

    summary = _read_json(out / "configure_summary.json")
    acquisition = _read_json(out / "02_source_acquisition" / "source_search_results.json")
    source_documents = _read_json(out / "03_source_autopilot" / "source_documents.json")
    autopilot = _read_json(out / "03_source_autopilot" / "source_autopilot_report.json")
    package = out / "04_package"
    operator = _read_json(package / "reports" / "operator_summary.json")
    deck_dir = next((package / "CustomConfig").iterdir())
    mulligan = _read_json(deck_dir / "Mulligan.json")
    darkbishop = _read_json(deck_dir / "SW_448.json")

    assert summary["status"] == "OK"
    assert autopilot["semantic_status"] == "SOURCE_BACKED_STRONG"
    assert autopilot["strong_candidate"] is True
    assert autopilot["first_missing_source_action"] == "none"
    assert autopilot["source_backed_strong_closure"]["closed"] is True
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["source_backed_status"] == "SOURCE_BACKED_STRONG"
    assert operator["source_strong_ready"] is True
    assert operator["first_missing_source_action"] == "none"
    assert operator["source_status_reasons"] == ["source_backed_strong_ready"]
    assert operator["default_only_runtime_surfaces"] == []
    assert operator["source_status_apply_blocking"] is False
    assert acquisition["records"][0]["source_visibility"] == "full_text"

    flat_claims = [
        claim
        for document in source_documents["source_documents"]
        for claim in document.get("claims", [])
    ]
    assert {
        card_id
        for claim in flat_claims
        if claim.get("claim_kind") == "mulligan_keep"
        for card_id in claim.get("cards", [])
    } == {"SW_446", "TOY_381", "SW_444", "SCH_514", "GVG_009"}
    assert any(claim.get("claim_kind") == "gameplan_posture" for claim in flat_claims)
    assert any(
        claim.get("claim_kind") == "hero_power_transform"
        and claim.get("cards") == ["SW_448"]
        for claim in flat_claims
    )

    mulligan_text = json.dumps(mulligan, sort_keys=True)
    assert "SW_448" not in mulligan_text
    for expected_card_id in ("SW_446", "TOY_381", "SW_444", "SCH_514", "GVG_009"):
        assert expected_card_id in mulligan_text

    darkbishop_text = json.dumps(darkbishop, sort_keys=True).lower()
    assert "beforeuseheropowerbonus" in darkbishop_text
    assert "enable_shadow_hero_power" in darkbishop_text or "shadow hero" in darkbishop_text
    assert "shadow" in darkbishop_text
