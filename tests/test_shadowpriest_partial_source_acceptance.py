from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main
from hsconfig.current_output import resolve_current_package

from tests.test_configure_auto_source import (
    SHADOWPRIEST_CODE,
    _stub_empty_fetches,
    _write_shadow_cards_json,
)


FIXTURES = Path(__file__).parent / "fixtures"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_configure_shadowpriest_keeps_archetype_only_guide_mulligan_diagnostic(
    tmp_path: Path,
    monkeypatch,
):
    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_shadow_cards_json(cards_json)
    out = tmp_path / "configure"
    source_url = "https://example.test/shadowpriest-archetype"
    source_fixture = tmp_path / "shadowpriest_archetype_only_guide.html"
    source_fixture.write_text(
        (
            FIXTURES / "source_pages" / "shadowpriest_archetype_only_guide.html"
        ).read_text(encoding="utf-8").replace(
            "</main>",
            "<p>This full-text guide is current Wild archetype context, but it "
            "does not provide an exact deck code or exact deck-list match.</p></main>",
        ),
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
            SHADOWPRIEST_CODE,
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

    package = resolve_current_package(out)
    operator = _read_json(package / "reports" / "operator_summary.json")
    global_profile = _read_json(package / "reports" / "globalvalues_profile.json")
    mulligan_plan = _read_json(package / "reports" / "mulligan_plan_report.json")

    assert operator["source_backed_status"] != "SOURCE_BACKED_STRONG"
    assert global_profile["changed_keys"] == []
    assert mulligan_plan["quality"]["source_backed_keep_rule_count"] == 0
    assert {
        row["reason"] for row in mulligan_plan["suppressed_rules"]
    } >= {"mulligan_requires_exact_deck_match"}
    assert not any(
        row["action"] == "hold" for row in mulligan_plan["rules"]
    )
