from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main

from tests.test_configure_auto_source import (
    SHADOWPRIEST_CODE,
    _read_json,
    _stub_empty_fetches,
    _write_shadow_cards_json,
    _write_thin_cards_json,
)


FIXTURES = Path(__file__).parent / "fixtures"


def _write_fixture_map(path: Path, url: str, page_name: str) -> None:
    page = FIXTURES / "source_pages" / page_name
    path.write_text(json.dumps({url: str(page)}), encoding="utf-8")


def run_configure_with_fixture_online_source(tmp_path: Path, monkeypatch) -> dict:
    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_shadow_cards_json(cards_json)
    fixture_map = tmp_path / "fixture_map.json"
    _write_fixture_map(
        fixture_map,
        "https://example.test/shadowpriest",
        "shadowpriest_voidburn.html",
    )
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    out = tmp_path / "configure"

    status = main(
        [
            "configure",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(runtime),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--online-source",
            "--auto-source",
            "--source-url",
            "https://example.test/shadowpriest",
            "--source-fixture-url-map-json",
            str(fixture_map),
            "--json",
        ]
    )

    assert status == 0
    return _read_json(out / "configure_summary.json")


def test_configure_writes_source_bundle_for_online_source(tmp_path: Path, monkeypatch):
    result = run_configure_with_fixture_online_source(tmp_path, monkeypatch)
    bundle_path = Path(result["source_bundle_path"])
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

    assert bundle["schema_version"] == 1
    assert bundle["promotion"]["first_missing_source_action"] in {
        "none",
        "replace_default_only_runtime_surface_with_source_or_policy_claim",
        "add_explicit_mulligan_source",
        "map_claim_kind_or_keep_report_only",
    }

    package = Path(result["package_path"])
    operator = _read_json(package / "reports" / "operator_summary.json")
    ownership = _read_json(package / "reports" / "output_ownership_manifest.json")
    ownership_rows = {row["file"]: row for row in ownership["files"]}

    assert "reports/source_bundle.json" in operator["generated_files"]
    assert any(
        row["file"] == "reports/source_bundle.json"
        and row["classification"] == "diagnostic"
        for row in operator["report_ownership"]
    )
    assert ownership_rows["reports/source_bundle.json"]["diagnostic_only"] is True


def test_configure_online_source_builds_source_backed_shadowpriest_package(
    tmp_path: Path,
    monkeypatch,
):
    summary = run_configure_with_fixture_online_source(tmp_path, monkeypatch)
    out = Path(summary["package_path"]).parent
    acquisition = _read_json(out / "02_source_acquisition" / "source_search_results.json")
    autopilot = _read_json(out / "03_source_autopilot" / "source_autopilot_report.json")
    package = out / "04_package"
    operator = _read_json(package / "reports" / "operator_summary.json")
    explainability = _read_json(package / "reports" / "source_to_runtime_explainability.json")
    mulligan_text = "\n".join(
        path.read_text(encoding="utf-8") for path in package.glob("CustomConfig/*/Mulligan.json")
    )

    assert summary["status"] == "OK"
    assert summary["source_acquisition_path"] == str(out / "02_source_acquisition")
    assert summary["source_autopilot_path"] == str(out / "03_source_autopilot")
    assert summary["source_documents_json"] == str(
        out / "03_source_autopilot" / "source_documents.json"
    )
    assert acquisition["records"][0]["source_family"] == "guide"
    assert autopilot["strong_candidate"] is False
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    blocker_reasons = {
        str(blocker.get("reason", ""))
        for blocker in operator["semantic_blockers"]
    }
    assert "cards_need_guide_claims" in blocker_reasons
    assert "generic_low_confidence_not_strong_evidence" in blocker_reasons
    assert explainability["operator_attention"][0]["first_missing_link"] == "needs_runtime_surface"
    assert operator["default_only_runtime_surfaces"] == []
    assert "SW_448" not in mulligan_text


def test_configure_online_source_keeps_thin_sources_load_safe_and_visible(
    tmp_path: Path,
    monkeypatch,
):
    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_thin_cards_json(cards_json)
    fixture_map = tmp_path / "fixture_map.json"
    _write_fixture_map(
        fixture_map,
        "https://example.test/decklist",
        "decklist_only.html",
    )
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    out = tmp_path / "configure"

    status = main(
        [
            "configure",
            "--deck-name",
            "ThinDeck",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(runtime),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--online-source",
            "--auto-source",
            "--source-url",
            "https://example.test/decklist",
            "--source-fixture-url-map-json",
            str(fixture_map),
            "--json",
        ]
    )

    summary = _read_json(out / "configure_summary.json")
    autopilot = _read_json(out / "03_source_autopilot" / "source_autopilot_report.json")
    operator = _read_json(out / "04_package" / "reports" / "operator_summary.json")

    assert status == 0
    assert summary["status"] == "OK"
    assert summary["source_acquisition_path"] == str(out / "02_source_acquisition")
    assert summary["source_autopilot_path"] == str(out / "03_source_autopilot")
    assert autopilot["strong_candidate"] is False
    assert autopilot["first_missing_source_action"] == "add_explicit_mulligan_source"
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["semantic_status"] != "SOURCE_BACKED_STRONG"


def test_configure_online_source_without_usable_guide_stays_load_safe_non_strong(
    tmp_path: Path,
    monkeypatch,
):
    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_thin_cards_json(cards_json)
    fixture_map = tmp_path / "empty_map.json"
    fixture_map.write_text("{}", encoding="utf-8")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    out = tmp_path / "configure"

    status = main(
        [
            "configure",
            "--deck-name",
            "ThinDeck",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(runtime),
            "--out",
            str(out),
            "--cards-json",
            str(cards_json),
            "--online-source",
            "--auto-source",
            "--source-url",
            "https://example.test/missing",
            "--source-fixture-url-map-json",
            str(fixture_map),
            "--json",
        ]
    )

    acquisition = _read_json(out / "02_source_acquisition" / "source_acquisition_report.json")
    operator = _read_json(out / "04_package" / "reports" / "operator_summary.json")

    assert status == 0
    assert acquisition["failed_fetch_count"] == 1
    assert acquisition["first_missing_source_action"] == "add_public_guide_url_or_use_static_semantics"
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["semantic_status"] != "SOURCE_BACKED_STRONG"
