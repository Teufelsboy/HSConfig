from __future__ import annotations

import json
from pathlib import Path

import pytest

from hsconfig.acceptance_matrix import build_acceptance_matrix
from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.cli import main
from hsconfig.current_output import resolve_current_package
from hsconfig.runtime_apply import apply_package

from tests.test_configure_auto_source import (
    SHADOWPRIEST_CODE,
    TARGETED_SHADOWPRIEST_CODE,
    _stub_empty_fetches,
    _write_shadow_cards_json,
)


FIXTURES = Path(__file__).parent / "fixtures"
def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_configure_shadowpriest_fixture_is_diagnostic_not_strategic_authority(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_shadow_cards_json(cards_json)
    out = tmp_path / "configure"
    source_url = "https://example.test/current-shadowpriest-guide"
    source_fixture = tmp_path / "shadowpriest_current_guide.html"
    source_fixture.write_text(
        (FIXTURES / "source_pages" / "shadowpriest_current_guide.html")
        .read_text(encoding="utf-8")
        .replace(SHADOWPRIEST_CODE, TARGETED_SHADOWPRIEST_CODE),
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
            TARGETED_SHADOWPRIEST_CODE,
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

    summary = json.loads(capsys.readouterr().out)
    package = resolve_current_package(out)
    run_root = package.parent
    acquisition = _read_json(
        run_root / "02_source_acquisition" / "source_search_results.json"
    )
    source_documents = _read_json(
        run_root / "03_source_autopilot" / "source_documents.json"
    )
    autopilot = _read_json(
        run_root / "03_source_autopilot" / "source_autopilot_report.json"
    )
    operator = _read_json(package / "reports" / "operator_summary.json")
    claim_bundle = _read_json(package / "reports" / "guide_claim_bundle.json")
    deck_dir = next((package / "CustomConfig").iterdir())
    mulligan = _read_json(deck_dir / "Mulligan.json")
    darkbishop = _read_json(deck_dir / "SW_448.json")
    shadow_hero_power = _read_json(deck_dir / "EX1_625t.json")

    assert summary["status"] == "OK"
    assert autopilot["semantic_status"] == "SOURCE_BACKED_PARTIAL"
    assert autopilot["strong_candidate"] is False
    assert autopilot["first_missing_source_action"] == (
        "acquire_strategic_source_via_live_http"
    )
    assert autopilot["source_backed_strong_closure"]["closed"] is False
    assert "strategic_provenance_not_live_verified" in autopilot[
        "strong_candidate_blockers"
    ]
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_allowed"] is False
    assert operator["source_apply_eligible"] is False
    assert operator["source_apply_eligibility_reasons"] == [
        "diagnostic_source_not_apply_eligible"
    ]
    assert operator["source_backed_status"] == "SOURCE_BACKED_PARTIAL"
    assert operator["source_strong_ready"] is False
    assert operator["first_missing_source_action"] == (
        "add_runtime_lowerable_claim_or_router_support"
    )
    assert operator["source_status_reasons"] == [
        "first_missing_claim_chain",
        "diagnostic_source_not_apply_eligible",
    ]
    assert operator["default_only_runtime_surfaces"] == []
    assert operator["source_status_apply_blocking"] is False
    assert operator["no_block_failure_mode_summary"]["hard_block"] is False
    assert operator["no_block_failure_mode_summary"]["overall"] == (
        "runtime_apply_not_allowed"
    )
    assert operator["no_block_failure_mode_summary"]["runtime_apply_reason"] == (
        "diagnostic_source_not_apply_eligible"
    )
    assert acquisition["records"][0]["source_visibility"] == "full_text"
    assert acquisition["records"][0]["acquisition_provenance"]["mode"] == (
        "fixture_map"
    )
    assert acquisition["records"][0]["acquisition_provenance"]["authority"] == (
        "fixture_only"
    )
    assert claim_bundle["canonical_source_receipts"] == []

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
        assert expected_card_id not in mulligan_text

    assert darkbishop["GameCardId"] == "SW_448"
    assert "BeforeUseHeroPowerBonus" not in darkbishop
    shadow_hero_power_text = json.dumps(shadow_hero_power, sort_keys=True).lower()
    assert shadow_hero_power["GameCardId"] == "EX1_625t"
    assert "beforeuseheropowerbonus" in shadow_hero_power_text
    assert (
        "enable_shadow_hero_power" in shadow_hero_power_text
        or "shadow hero" in shadow_hero_power_text
    )
    assert "shadow" in shadow_hero_power_text

    gate = evaluate_apply_gate(package)
    acceptance = build_acceptance_matrix([package])
    assert gate["allowed"] is False
    assert gate["reasons"][0]["reason"] == (
        "diagnostic_source_not_apply_eligible"
    )
    assert acceptance["status"] == "failed"
    acceptance_row = acceptance["packages"][0]
    assert acceptance["summary"]["technical_hard_block_count"] == 0
    assert acceptance_row["technical_hard_block_count"] == 0
    assert "technical_hard_block_present" not in acceptance_row[
        "matrix_row_failure_reasons"
    ]
    assert acceptance_row["runtime_load_safe"] is True
    assert acceptance_row["runtime_apply_mode"] == "blocked"
    assert acceptance_row["runtime_apply_allowed"] is False
    assert acceptance_row["runtime_apply_reason"] == (
        "diagnostic_source_not_apply_eligible"
    )
    assert acceptance_row["fixture_classification"] == "load_safe_fixture"
    assert acceptance_row["apply_eligibility_classification"] == (
        "diagnostic_source_apply_ineligible"
    )
    assert acceptance_row["apply_gate_allowed"] is False
    assert acceptance_row["apply_gate_reasons"][0]["reason"] == (
        "diagnostic_source_not_apply_eligible"
    )

    monkeypatch.setattr(
        "hsconfig.runtime_apply._single_config_dir",
        lambda _package: pytest.fail("runtime writer preparation must not run"),
    )
    with pytest.raises(
        ValueError,
        match="diagnostic_source_not_apply_eligible",
    ):
        apply_package(
            package_root=package,
            runtime_root=tmp_path / "blocked-runtime",
            write_history=False,
        )
    assert not (tmp_path / "blocked-runtime").exists()


def test_configure_shadowpriest_live_verified_source_remains_apply_eligible(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_shadow_cards_json(cards_json)
    out = tmp_path / "configure-live"
    source_url = "https://example.test/current-shadowpriest-guide"
    source_body = (
        (FIXTURES / "source_pages" / "shadowpriest_current_guide.html")
        .read_text(encoding="utf-8")
        .replace(SHADOWPRIEST_CODE, TARGETED_SHADOWPRIEST_CODE)
        .encode("utf-8")
    )
    monkeypatch.setattr(
        "hsconfig.source_acquisition._default_resolver",
        lambda _hostname: ["93.184.216.34"],
    )
    monkeypatch.setattr(
        "hsconfig.source_acquisition._fetch_with_validated_address",
        lambda _url, _timeout, _address: (200, "text/html", source_body),
    )

    assert main(
        [
            "configure",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            TARGETED_SHADOWPRIEST_CODE,
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
            "--json",
        ]
    ) == 0

    package = resolve_current_package(out)
    run_root = package.parent
    acquisition = _read_json(
        run_root / "02_source_acquisition" / "source_search_results.json"
    )
    source_documents = _read_json(
        run_root / "03_source_autopilot" / "source_documents.json"
    )
    operator = _read_json(package / "reports" / "operator_summary.json")
    claim_bundle = _read_json(package / "reports" / "guide_claim_bundle.json")
    gate = evaluate_apply_gate(package)

    assert claim_bundle["canonical_source_receipts"]
    assert acquisition["records"][0]["acquisition_provenance"]["mode"] == "live_http"
    assert source_documents["source_documents"][0]["acquisition_provenance"][
        "authority"
    ] == "live_verified"
    assert all(
        receipt["acquisition_provenance"]["authority"] == "live_verified"
        for receipt in claim_bundle["canonical_source_receipts"]
    )
    assert operator["source_apply_eligible"] is True
    assert operator["source_apply_eligibility_reasons"] == []
    assert operator["runtime_apply_allowed"] is True
    assert operator["source_status_apply_blocking"] is False
    assert gate["allowed"] is True
