from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from hsconfig.cli import main
from hsconfig.commands.source_workflow import source_acquire_payload


def test_source_acquire_cli_writes_compiled_source_search_results(tmp_path):
    fixture_map = tmp_path / "fixture_map.json"
    page = Path(__file__).parent / "fixtures" / "source_pages" / "shadowpriest_voidburn.html"
    fixture_map.write_text(
        json.dumps({"https://example.test/shadowpriest": str(page)}),
        encoding="utf-8",
    )
    out = tmp_path / "out"

    status = main(
        [
            "source-acquire",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
            "--source-url",
            "https://example.test/shadowpriest",
            "--source-fixture-url-map-json",
            str(fixture_map),
            "--out",
            str(out),
            "--json",
        ]
    )

    assert status == 0
    source_search = json.loads(
        (out / "source_search_results.json").read_text(encoding="utf-8")
    )
    assert source_search["records"][0]["source_family"] == "guide"
    assert source_search["records"][0]["mulligan"]["keep_card_ids"]
    assert (out / "source_acquisition_report.json").exists()
    assert (out / "source_claim_compiler_report.json").exists()


def test_source_acquire_payload_embeds_report_objects(tmp_path):
    fixture_map = tmp_path / "fixture_map.json"
    page = Path(__file__).parent / "fixtures" / "source_pages" / "shadowpriest_voidburn.html"
    fixture_map.write_text(
        json.dumps({"https://example.test/shadowpriest": str(page)}),
        encoding="utf-8",
    )
    out = tmp_path / "out"

    args = SimpleNamespace(
        deck_name="ShadowPriest",
        deck_code="AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG17oG1cEGAAA=",
        source_url=["https://example.test/shadowpriest"],
        source_fixture_url_map_json=str(fixture_map),
        source_fetch_timeout_seconds=6.0,
        current_date="2026-07-15",
        out=str(out),
        cards_json=None,
        allow_placeholder=False,
        json=True,
    )

    payload, status = source_acquire_payload(args)

    assert status == 0
    assert payload["source_acquisition_report"]["source_record_count"] == 1
    assert payload["source_claim_compiler_report"]["record_count"] == 1
    assert payload["source_acquisition_report_json"].endswith("source_acquisition_report.json")
    assert payload["source_claim_compiler_report_json"].endswith(
        "source_claim_compiler_report.json"
    )
