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


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_configure_shadowpriest_closes_strong_source_contract(tmp_path: Path, monkeypatch):
    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_shadow_cards_json(cards_json)
    out = tmp_path / "configure"

    assert main(
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
    ) == 0

    summary = _read_json(out / "configure_summary.json")
    package = out / "04_package"
    operator = _read_json(package / "reports" / "operator_summary.json")
    deck_dir = next((package / "CustomConfig").iterdir())
    mulligan = _read_json(deck_dir / "Mulligan.json")
    darkbishop = _read_json(deck_dir / "SW_448.json")

    assert summary["status"] == "OK"
    assert operator["source_backed_status"] == "SOURCE_BACKED_STRONG"
    assert operator["source_strong_ready"] is True
    assert operator["first_missing_source_action"] == "none"
    assert operator["default_only_runtime_surfaces"] == []
    assert operator["source_status_apply_blocking"] is False

    mulligan_text = json.dumps(mulligan, sort_keys=True)
    assert "SW_448" not in mulligan_text

    darkbishop_text = json.dumps(darkbishop, sort_keys=True).lower()
    assert "beforeuseheropowerbonus" in darkbishop_text
    assert "hero_power" in darkbishop_text or "hero power" in darkbishop_text
    assert "mind_spike" in darkbishop_text or "mind spike" in darkbishop_text
    assert "shadow" in darkbishop_text
