from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from hsconfig.cli import main
from hsconfig.current_output import resolve_current_package
from hsconfig.deck_identity import build_deck_identity
from tests.helpers.verified_deck_input import (
    VERIFIED_TEST_CARDS,
    VERIFIED_TEST_DECK_CODE,
)


FIXTURES = Path(__file__).parent / "fixtures"
AUDITED_CATALOG = Path("docs/operator/audited-deck-catalog.json")
AUDITED_CARD_DB = FIXTURES / "audited_deck_card_db.json"
SOURCE_SEARCH_MATRIX = FIXTURES / "source_search_11_deck_matrix.json"
SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)
TARGETED_SHADOWPRIEST_CODE = "AAEBAa0GAbv3AwWRD9fOA6P3A633A8SoBgAA"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_json_stdout(capsys: pytest.CaptureFixture[str]) -> dict:
    return json.loads(capsys.readouterr().out)


def _published_run(out: Path) -> tuple[Path, Path]:
    package = resolve_current_package(out)
    return package.parent, package


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
                    {
                        "card_id": "TOY_381",
                        "name": "Papercraft Angel",
                        "cost": 3,
                        "count": 2,
                    },
                    {
                        "card_id": "SW_444",
                        "name": "Twilight Deceptor",
                        "cost": 2,
                        "count": 2,
                    },
                    {
                        "card_id": "SCH_514",
                        "name": "Raise Dead",
                        "cost": 0,
                        "count": 2,
                    },
                    {
                        "card_id": "GVG_009",
                        "name": "Shadowbomber",
                        "cost": 1,
                        "count": 2,
                    },
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
                        **VERIFIED_TEST_CARDS[0],
                        "name": "Fixture Card",
                        "cost": 1,
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


def _install_audited_decoder_db(monkeypatch) -> None:
    cards = {}
    for row in _read_json(AUDITED_CARD_DB)["cards"]:
        (
            dbf_id,
            card_id,
            name,
            cost,
            card_type,
            card_class,
            text,
            mechanics,
        ) = row
        card = SimpleNamespace(
            card_class=card_class,
            card_id=card_id,
            cost=cost,
            english_description=text,
            english_name=name,
            name=name,
            type=card_type,
        )
        for mechanic in mechanics:
            setattr(card, str(mechanic), True)
        cards[int(dbf_id)] = card
    monkeypatch.setattr(
        "hsconfig.deckstring_decode.cardxml.load_dbf",
        lambda: (cards, None),
    )


@pytest.mark.parametrize(
    ("deck_name", "gap_card_id"),
    [
        ("Kingslayer", "DEEP_014"),
        ("Boarlock", "WW_092"),
    ],
)
def test_configure_preserves_explicit_mulligan_source_gap_through_policy_fallback(
    tmp_path: Path,
    monkeypatch,
    deck_name: str,
    gap_card_id: str,
) -> None:
    _stub_empty_fetches(monkeypatch)
    _install_audited_decoder_db(monkeypatch)
    deck = next(
        row
        for row in _read_json(AUDITED_CATALOG)["decks"]
        if row["deck_name"] == deck_name
    )
    matrix = _read_json(SOURCE_SEARCH_MATRIX)
    source_records_path = tmp_path / f"{deck_name}-source-search.json"
    source_records_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "records": matrix["records_by_deck"][deck_name],
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / deck_name

    code = main(
        [
            "configure",
            "--deck-name",
            deck_name,
            "--deck-code",
            deck["deck_code"],
            "--runtime-root",
            str(tmp_path / "nonexistent-runtime"),
            "--out",
            str(out),
            "--auto-source",
            "--source-search-results-json",
            str(source_records_path),
            "--current-date",
            "2026-07-28",
            "--json",
        ]
    )

    assert code == 0
    run_root, package = _published_run(out)
    autopilot = _read_json(
        run_root / "02_source_autopilot" / "source_autopilot_report.json"
    )
    identity = _read_json(package / "reports" / "deck_identity.json")
    report = _read_json(package / "reports" / "mulligan_plan_report.json")
    holds = {
        str(row["card"])
        for row in report["rules"]
        if row.get("action") == "hold"
        and row.get("selector_kind") != "wildcard"
    }
    physical = _read_json(
        next((package / "CustomConfig").glob("*/Mulligan.json"))
    )
    physical_holds = {
        str(row["mulligan"])
        for row in physical["Mulligan"]["values"]
        if row.get("value") == "hold"
        and row.get("mulligan") != "*"
    }

    assert gap_card_id not in holds
    assert gap_card_id not in physical_holds
    assert holds == set()
    assert physical_holds == set()
    assert gap_card_id in {
        str(row["card_id"]) for row in report["bot_delegated"]
    }
    gap = next(
        row
        for row in autopilot["explicit_mulligan_source_gaps"]
        if row["card_id"] == gap_card_id
    )
    assert gap["target_deck_name"] == deck_name
    assert gap["target_deck_fingerprint"] == identity["deck_fingerprint"]
    assert gap["target_deck_code_hash"] == identity["deck_code_hash"]


def test_configure_auto_source_builds_load_safe_package_without_darkbishop_mulligan(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
):
    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_shadow_cards_json(cards_json)
    out = tmp_path / "configure"
    source_records = _read_json(FIXTURES / "source_search_shadowpriest_2026.json")
    deck_identity = build_deck_identity(
        deck_name="ShadowPriest",
        deck_code=TARGETED_SHADOWPRIEST_CODE,
        cards=_read_json(cards_json)["cards"],
    )
    source_record = source_records["records"][0]
    source_record["deck_match_scope"] = "exact_deck_matched"
    source_record["deck_match"]["exact_deck_evidence"] = {
        "candidate_count": 1,
        "decoded_candidate_count": 1,
        "matched": True,
        "matched_deck_fingerprint": deck_identity["deck_fingerprint"],
        "candidate_deck_code_hashes": ["sha256:configure-auto-source"],
    }
    source_records_path = tmp_path / "source_search_shadowpriest_exact.json"
    source_records_path.write_text(json.dumps(source_records), encoding="utf-8")

    code = main(
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
            "--auto-source",
            "--source-search-results-json",
            str(source_records_path),
            "--json",
        ]
    )

    summary = _read_json_stdout(capsys)
    run_root, package = _published_run(out)
    autopilot_report = _read_json(
        run_root / "02_source_autopilot" / "source_autopilot_report.json"
    )
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
    assert summary["source_autopilot_path"] == str(run_root / "02_source_autopilot")
    assert summary["source_documents_json"] == str(
        run_root / "02_source_autopilot" / "source_documents.json"
    )
    assert autopilot_report["strong_candidate"] is False
    assert autopilot_report["semantic_status"] == "SOURCE_BACKED_PARTIAL"
    assert (
        autopilot_report["first_missing_source_action"]
        == "acquire_strategic_source_via_live_http"
    )
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["semantic_status"] == "VALID_BUT_NOT_GUIDE_STRONG"
    assert operator["runtime_apply_mode"] == "blocked"
    assert operator["runtime_apply_allowed"] is False
    assert source_closure_receipt["authority"] == "diagnostic_only"
    assert source_closure_receipt["operator_gate"] == "reports/operator_summary.json"
    assert source_closure_receipt["normal_apply_authority"] == (
        "reports/operator_summary.json"
    )
    assert source_closure_receipt["apply_blocking"] is False
    assert source_closure_receipt["runtime_write_performed"] is False
    assert source_closure_receipt["source_backed_status"] == operator["source_backed_status"]
    assert source_closure_receipt["source_status_apply_blocking"] is False
    assert (
        source_closure_receipt["first_missing_source_action"]
        == "add_runtime_lowerable_claim_or_router_support"
    )
    assert source_closure_receipt["default_only_clean"] is True
    assert source_closure_receipt["default_only_runtime_surfaces"] == []
    assert source_closure_receipt["source_closure_lane"] == "runtime_surface_needed"
    assert source_closure_receipt["compiled_claim_count"] >= 1
    assert source_closure_receipt["runtime_lowerable_claim_count"] >= 1
    for key in (
        "generic_low_confidence_cards",
        "uncovered_cards",
        "source_evidence_warnings",
        "cards_needing_guide_claims",
        "cards_needing_mulligan_claims",
        "cards_needing_combo_sequence",
        "cards_needing_condition_lowering",
        "cards_needing_invalid_target_scope",
        "cards_needing_target_surface",
        "cards_needing_mechanic_lowering",
    ):
        assert operator["guide_strength_summary"][key] == 0
    assert operator["guide_strength_summary"]["cards_needing_runtime_surface"] == 2
    assert operator["guide_strength_summary"]["cards_needing_target_scope"] == 0
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


def test_configure_auto_source_invalid_exact_count_stays_load_safe_partial(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
):
    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_shadow_cards_json(cards_json)
    out = tmp_path / "configure"
    source_records = _read_json(FIXTURES / "source_search_shadowpriest_2026.json")
    deck_identity = build_deck_identity(
        deck_name="ShadowPriest",
        deck_code=TARGETED_SHADOWPRIEST_CODE,
        cards=_read_json(cards_json)["cards"],
    )
    source_record = source_records["records"][0]
    source_record["deck_match_scope"] = "exact_deck_matched"
    source_record["deck_match"]["exact_deck_evidence"] = {
        "candidate_count": "not-an-integer",
        "decoded_candidate_count": 1,
        "matched": True,
        "matched_deck_fingerprint": deck_identity["deck_fingerprint"],
        "candidate_deck_code_hashes": ["sha256:invalid-count-source"],
    }
    source_records_path = tmp_path / "source_search_invalid_count.json"
    source_records_path.write_text(
        json.dumps(source_records),
        encoding="utf-8",
    )

    code = main(
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
            "--auto-source",
            "--source-search-results-json",
            str(source_records_path),
            "--json",
        ]
    )

    summary = _read_json_stdout(capsys)
    run_root, package = _published_run(out)
    autopilot = _read_json(
        run_root / "02_source_autopilot" / "source_autopilot_report.json"
    )
    source_documents = _read_json(
        run_root / "02_source_autopilot" / "source_documents.json"
    )["source_documents"]
    package_reports = package / "reports"
    guide_bundle = _read_json(package_reports / "guide_claim_bundle.json")
    operator = _read_json(package_reports / "operator_summary.json")

    assert code == 0
    assert summary["status"] == "OK"
    assert summary["config_proof_summary"]["runtime_write_performed"] is False
    assert autopilot["strong_candidate"] is False
    assert source_documents[0]["deck_match_scope"] == "archetype_matched"
    assert source_documents[0]["first_missing_source_action"] == (
        "add_exact_deck_matched_source"
    )
    assert "deck_match" not in source_documents[0]
    assert guide_bundle["canonical_source_receipts"] == []
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_load_safe"] is True
    assert operator["runtime_apply_mode"] == "blocked"
    assert operator["runtime_apply_allowed"] is False
    assert operator["source_backed_status"] == "SOURCE_BACKED_PARTIAL"


def test_configure_propagates_operator_date_to_final_guide_claims(
    tmp_path: Path,
    monkeypatch,
):
    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_shadow_cards_json(cards_json)
    out = tmp_path / "configure"
    source_records_path = tmp_path / "source_search_frozen_date.json"
    source_records_path.write_text(
        json.dumps(
            _read_json(FIXTURES / "source_search_shadowpriest_2026.json")
        ),
        encoding="utf-8",
    )

    code = main(
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
            "--auto-source",
            "--source-search-results-json",
            str(source_records_path),
            "--current-date",
            "2030-01-15",
            "--json",
        ]
    )

    run_root, package = _published_run(out)
    ranked_sources = _read_json(
        run_root / "02_source_autopilot" / "ranked_sources.json"
    )["ranked_sources"]
    source_documents = _read_json(
        run_root / "02_source_autopilot" / "source_documents.json"
    )["source_documents"]
    research_sources = _read_json(run_root / "03_research" / "guide_sources.json")
    final_guide_bundle = _read_json(
        package / "reports" / "guide_claim_bundle.json"
    )
    guide_claims = [
        claim
        for claim in final_guide_bundle["claims"]
        if claim.get("source_url")
        == "https://www.hearthpwn.com/decks/1461644-voidburn-wild-aggro-shadow-priest"
    ]

    assert code == 0
    assert ranked_sources[0]["freshness_status"] == "stale"
    assert source_documents[0]["retrieved_at"] == "2026-07-15T00:00:00Z"
    assert research_sources["summary"]["stale_source_count"] == 1
    assert guide_claims
    assert {claim["freshness_status"] for claim in guide_claims} == {"stale"}
    assert {claim["claim_confidence"] for claim in guide_claims} == {"medium"}
    assert {claim["retrieved_at"] for claim in guide_claims} == {
        "2026-07-15T00:00:00Z"
    }


def test_configure_auto_source_keeps_decklist_only_non_strong_but_load_safe(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
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
            VERIFIED_TEST_DECK_CODE,
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

    summary = _read_json_stdout(capsys)
    run_root, package = _published_run(out)
    autopilot_report = _read_json(
        run_root / "02_source_autopilot" / "source_autopilot_report.json"
    )
    operator = _read_json(package / "reports" / "operator_summary.json")
    source_closure_receipt = summary["source_closure_receipt"]

    assert code == 0
    assert autopilot_report["strong_candidate"] is False
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_mode"] == "blocked"
    assert operator["runtime_apply_allowed"] is False
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
        "default_only_runtime_surface",
    }
    assert source_closure_receipt["next_report_to_open"] in {
        "reports/source_to_runtime_explainability.json",
        "reports/contract_doctor.json",
    }


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
            VERIFIED_TEST_DECK_CODE,
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

    run_root, package = _published_run(out)
    autopilot_report = _read_json(
        run_root / "02_source_autopilot" / "source_autopilot_report.json"
    )
    operator = _read_json(package / "reports" / "operator_summary.json")

    assert code == 0
    assert autopilot_report["strong_candidate"] is False
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["runtime_apply_allowed"] is True
    assert operator["semantic_status"] != "SOURCE_BACKED_STRONG"


def test_configure_online_source_uses_registry_when_source_url_is_omitted(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
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
            TARGETED_SHADOWPRIEST_CODE,
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

    summary = _read_json_stdout(capsys)
    run_root, package = _published_run(out)
    acquisition = _read_json(
        run_root / "02_source_acquisition" / "source_acquisition_report.json"
    )
    autopilot = _read_json(
        run_root / "03_source_autopilot" / "source_autopilot_report.json"
    )
    operator = _read_json(package / "reports" / "operator_summary.json")

    assert code == 0
    assert any(
        "voidburn-wild-aggro-shadow-priest" in url
        for url in summary["source_candidate_urls"]
    )
    assert summary["source_urls"] == summary["source_candidate_urls"]
    assert summary["source_candidate_plan_path"] == str(
        run_root / "01_manifest" / "source_candidate_plan.json"
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
    capsys: pytest.CaptureFixture[str],
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
            TARGETED_SHADOWPRIEST_CODE,
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

    summary = _read_json_stdout(capsys)

    assert code == 1
    assert not out.exists()
    assert summary["status"] == "failed"
    assert summary["stage"] == "source-autopilot"
    assert "--source-search-results-json is required when --auto-source is used" in summary[
        "errors"
    ]
