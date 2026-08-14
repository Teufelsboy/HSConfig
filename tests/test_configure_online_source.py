from __future__ import annotations

import json
from pathlib import Path

import pytest

from hsconfig.cli import main
from hsconfig.commands import configure as configure_command
from hsconfig.source_candidate_registry import SourceCandidate
from tests.helpers.verified_deck_input import VERIFIED_TEST_DECK_CODE

from tests.test_configure_auto_source import (
    TARGETED_SHADOWPRIEST_CODE,
    _read_json,
    _stub_empty_fetches,
    _write_shadow_cards_json,
    _write_thin_cards_json,
)


FIXTURES = Path(__file__).parent / "fixtures"


def assert_darkbishop_effect_semantics_without_mulligan_keep(
    darkbishop: dict, mulligan: dict
) -> None:
    hero_power_bonus = darkbishop["BeforeUseHeroPowerBonus"]["values"]
    assert hero_power_bonus
    assert any(
        row.get("value") and _has_shadow_hero_power_transform_semantics(row)
        for row in hero_power_bonus
    )
    assert not any(
        row.get("mulligan") == "SW_448" or row.get("card_id") == "SW_448"
        for row in mulligan["Mulligan"]["values"]
    )


def _has_shadow_hero_power_transform_semantics(row: dict) -> bool:
    text = " ".join(
        str(row.get(key, ""))
        for key in ("comment", "condition", "target", "value", "name")
    ).lower()
    return any(
        token in text
        for token in ("enable_shadow", "shadowform", "mind spike", "shadow hero")
    ) or any(
        token in text
        for token in ("enable_transformed_hero_power", "transformed_hero_power")
    )


def test_darkbishop_transform_semantic_guard_rejects_generic_hero_power_rows():
    assert _has_shadow_hero_power_transform_semantics(
        {"comment": "ShadowPriest: SW_448_enable_shadow_hero_power", "value": "6"}
    )
    assert _has_shadow_hero_power_transform_semantics(
        {"comment": "ShadowPriest: SW_448_enable_transformed_hero_power", "value": "6"}
    )
    assert not _has_shadow_hero_power_transform_semantics(
        {"comment": "generic hero_power priority", "value": "1"}
    )
    assert not _has_shadow_hero_power_transform_semantics(
        {"comment": "generic transform hero_power priority", "value": "1"}
    )


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
            TARGETED_SHADOWPRIEST_CODE,
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
    package = Path(result["package_path"])
    operator = _read_json(package / "reports" / "operator_summary.json")
    source_evidence_closure_path = Path(result["source_evidence_closure_path"])
    receipt_path = (
        package
        / "reports"
        / "02_source_acquisition"
        / "source_closure_intake_receipt.json"
    )
    receipt = _read_json(receipt_path)
    source_closure_receipt = result["source_closure_receipt"]

    assert bundle["schema_version"] == 1
    assert bundle["promotion"]["source_backed_status"] == operator[
        "source_backed_status"
    ]
    assert bundle["promotion"]["semantic_status"] == operator["source_backed_status"]
    assert bundle["promotion"]["first_missing_source_action"] == operator[
        "first_missing_source_action"
    ]
    assert source_evidence_closure_path == package / "reports" / "source_evidence_closure.json"
    assert source_evidence_closure_path.is_file()
    assert result["source_backed_status"] == operator["source_backed_status"]
    assert result["source_status_reasons"] == operator["source_status_reasons"]
    assert result["source_status_apply_blocking"] is False
    assert result["source_status_apply_blocking"] == operator["source_status_apply_blocking"]
    assert result["first_missing_source_action"] == operator["first_missing_source_action"]
    assert result["default_only_runtime_surfaces"] == operator[
        "default_only_runtime_surfaces"
    ]
    assert result["source_closure_intake_receipt_path"] == str(receipt_path)
    assert receipt["authority"] == "diagnostic_only"
    assert receipt["source_status_apply_blocking"] is False
    assert receipt["first_missing_source_action"] == "none"
    assert receipt["promotion_eligible_seed_count"] >= 1
    assert receipt["fetched_record_count"] >= 1
    assert source_closure_receipt["authority"] == "diagnostic_only"
    assert source_closure_receipt["source_candidate_url_count"] == len(
        result["source_candidate_urls"]
    )
    assert source_closure_receipt["source_url_count"] == len(result["source_urls"])
    assert source_closure_receipt["source_intake_candidate_count"] == receipt[
        "candidate_count"
    ]
    assert source_closure_receipt["fetched_record_count"] == receipt[
        "fetched_record_count"
    ]
    assert source_closure_receipt["source_status_apply_blocking"] is False
    assert source_closure_receipt["normal_apply_authority"] == (
        "reports/operator_summary.json"
    )
    assert operator["source_closure_intake"] == {
        "authority": "diagnostic_only",
        "candidate_count": receipt["candidate_count"],
        "promotion_eligible_seed_count": receipt["promotion_eligible_seed_count"],
        "first_missing_source_action": receipt["first_missing_source_action"],
        "source_status_apply_blocking": False,
        "receipt_path": (
            "reports/02_source_acquisition/source_closure_intake_receipt.json"
        ),
    }
    assert operator["source_status_apply_blocking"] is False
    assert operator["runtime_apply_contract"]["apply_authority"] == (
        "reports/operator_summary.json"
    )

    ownership = _read_json(package / "reports" / "output_ownership_manifest.json")
    ownership_rows = {row["file"]: row for row in ownership["files"]}

    assert "reports/source_bundle.json" in operator["generated_files"]
    assert (
        "reports/02_source_acquisition/source_closure_intake_receipt.json"
        in operator["generated_files"]
    )
    assert any(
        row["file"] == "reports/source_bundle.json"
        and row["classification"] == "diagnostic"
        for row in operator["report_ownership"]
    )
    assert any(
        row["file"]
        == "reports/02_source_acquisition/source_closure_intake_receipt.json"
        and row["classification"] == "diagnostic"
        for row in operator["report_ownership"]
    )
    assert ownership_rows["reports/source_bundle.json"]["diagnostic_only"] is True
    receipt_ownership = ownership_rows[
        "reports/02_source_acquisition/source_closure_intake_receipt.json"
    ]
    assert receipt_ownership["diagnostic_only"] is True
    assert receipt_ownership["can_block_apply"] is False


def test_full_text_public_guide_can_be_strong_candidate_only_after_fetch(
    tmp_path: Path, monkeypatch
):
    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_shadow_cards_json(cards_json)
    source_url = "https://example.test/current-shadowpriest-guide"
    current_guide = tmp_path / "current_shadowpriest_guide.html"
    current_guide.write_text(
        """
        <html>
          <head>
            <meta property="article:published_time" content="2026-07-18T00:00:00Z">
            <title>ShadowPriest 2026 Full Mulligan Guide</title>
          </head>
          <body>
            <h1>ShadowPriest 2026 Full Mulligan Guide</h1>
            <p>Mulligan: Keep Papercraft Angel, Twilight Deceptor, Raise Dead,
            and Shadowbomber for current Wild ShadowPriest openings.</p>
            <p>Darkbishop Benedictus enables the Shadow hero power and Mind
            Spike plan as a start-of-game effect, but this guide text does not
            say to keep Darkbishop in the opening hand.</p>
            <p>This full-text public guide discusses the deck plan, early burn
            pressure, matchup posture, current Wild ladder context, and enough
            card-specific overlap to be fetched and claim-normalized before any
            runtime package can treat it as source-backed evidence.</p>
          </body>
        </html>
        """,
        encoding="utf-8",
    )
    fixture_map = tmp_path / "fixture_map.json"
    fixture_map.write_text(json.dumps({source_url: str(current_guide)}), encoding="utf-8")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    out = tmp_path / "configure"

    status = main(
        [
            "configure",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            TARGETED_SHADOWPRIEST_CODE,
            "--runtime-root",
            str(runtime),
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
            "--current-date",
            "2026-07-18",
            "--json",
        ]
    )

    assert status == 0
    acquisition = _read_json(out / "02_source_acquisition" / "source_search_results.json")
    autopilot = _read_json(out / "03_source_autopilot" / "source_autopilot_report.json")
    operator = _read_json(out / "04_package" / "reports" / "operator_summary.json")

    record = acquisition["records"][0]

    assert record["source_category"] == "public_guide"
    assert record["source_visibility"] == "full_text"
    assert record["source_record_strength"] == "partial"
    assert record["retrieved_at"] == "2026-07-18"
    assert record["promotion_eligible"] is False
    assert record["strong_promotion_eligible"] is False
    assert record["first_missing_source_action"] == "add_exact_deck_matched_source"
    assert autopilot["strong_candidate"] is False
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["source_status_apply_blocking"] is False


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
    preview = summary["source_readiness_preview"]
    autopilot_preview = autopilot["source_readiness_preview"]
    deck_dirs = [path for path in (package / "CustomConfig").iterdir() if path.is_dir()]
    assert len(deck_dirs) == 1
    deck_dir = deck_dirs[0]
    mulligan = _read_json(deck_dir / "Mulligan.json")

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
    assert operator["runtime_apply_mode"] == "blocked"
    assert operator["runtime_apply_allowed"] is False
    assert preview["authority"] == "diagnostic_source_readiness_preview"
    assert preview["diagnostic_only"] is True
    assert preview["runtime_apply_authority"] == "reports/operator_summary.json"
    assert preview["apply_blocking"] is False
    assert preview["runtime_write_performed"] is False
    assert preview["source_status_apply_blocking"] is False
    assert preview["source_candidate_plan_present"] is True
    assert preview["source_autopilot_report_present"] is True
    assert preview["operator_summary_present"] is True
    assert preview["semantic_status"] == operator["semantic_status"]
    assert preview["first_missing_source_action"] == operator[
        "first_missing_source_action"
    ]
    assert preview["recommended_next_source_action"] == preview[
        "first_missing_source_action"
    ]
    assert preview["default_only_runtime_surfaces"] == []
    assert preview["default_only_evaluated"] is True
    assert preview["default_only_clean"] is True
    assert preview["default_only_runtime_surface_status"] == "clean"
    assert preview["runtime_apply_allowed"] is False
    assert preview["runtime_apply_mode"] == "blocked"
    assert autopilot_preview["authority"] == "diagnostic_source_readiness_preview"
    assert autopilot_preview["default_only_evaluated"] is False
    assert autopilot_preview["default_only_clean"] is False
    assert autopilot_preview["default_only_runtime_surface_status"] == (
        "not_evaluated_in_source_preflight"
    )
    blocker_reasons = {
        str(blocker.get("reason", ""))
        for blocker in operator["semantic_blockers"]
    }
    assert blocker_reasons == {
        "cards_need_runtime_surface",
        "contract_gap_not_strong_evidence",
        "unsupported_conditions_present",
    }
    rejected_mulligan_attention = [
        row
        for row in explainability["operator_attention"]
        if row["strongest_claim_kind"] == "mulligan_keep"
        and row["source_lane"] == "archetype_matched_public_guide"
    ]
    assert {
        row["card_id"] for row in rejected_mulligan_attention
    } == {"GVG_009", "SCH_514", "SW_444", "TOY_381"}
    assert all(
        row["first_missing_link"] == "needs_runtime_surface"
        and row["first_missing_source_action"]
        == "add_runtime_lowerable_claim_or_router_support"
        and row["next_source_action"]
        == "add_runtime_lowerable_claim_or_router_support"
        for row in rejected_mulligan_attention
    )
    assert operator["default_only_runtime_surfaces"] == []
    assert operator["source_contract_audit_summary"]["non_blocking"] is True
    assert operator["no_block_failure_mode_summary"]["hard_block"] is False
    assert explainability["apply_blocking"] is False

    darkbishop_source_path = deck_dir / "SW_448.json"
    hero_power_owner_path = deck_dir / "EX1_625t.json"
    assert darkbishop_source_path.is_file()
    assert hero_power_owner_path.is_file()
    darkbishop_source = _read_json(darkbishop_source_path)
    hero_power_owner = _read_json(hero_power_owner_path)
    assert darkbishop_source["GameCardId"] == "SW_448"
    assert "BeforeUseHeroPowerBonus" not in darkbishop_source
    assert hero_power_owner["GameCardId"] == "EX1_625t"
    assert_darkbishop_effect_semantics_without_mulligan_keep(hero_power_owner, mulligan)

    behavior_plan = _read_json(package / "reports" / "card_behavior_plan_report.json")
    hero_power_rows = [
        row
        for row in behavior_plan["rows"]
        if row.get("runtime_card_id") == "EX1_625t"
        and row.get("behavior_block") == "BeforeUseHeroPowerBonus"
    ]
    assert len(hero_power_rows) == 1
    assert hero_power_rows[0]["source_card_id"] == "SW_448"
    assert hero_power_rows[0]["link_kind"] == "hero_power_transform"

    source_documents = _read_json(out / "03_source_autopilot" / "source_documents.json")
    flat_claims = [
        claim
        for document in source_documents["source_documents"]
        for claim in document.get("claims", [])
    ]
    assert any(
        claim.get("claim_kind") == "hero_power_transform"
        and "SW_448" in claim.get("cards", [])
        for claim in flat_claims
    )
    assert not any(
        claim.get("claim_kind") == "mulligan_keep"
        and "SW_448" in claim.get("cards", [])
        for claim in flat_claims
    )


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
            VERIFIED_TEST_DECK_CODE,
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
    assert (
        autopilot["first_missing_source_action"]
        == "add_current_card_specific_runtime_source"
    )
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_mode"] == "blocked"
    assert operator["runtime_apply_allowed"] is False
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
            VERIFIED_TEST_DECK_CODE,
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
    summary = _read_json(out / "configure_summary.json")
    preview = summary["source_readiness_preview"]

    assert status == 0
    assert acquisition["failed_fetch_count"] == 1
    assert acquisition["first_missing_source_action"] == "add_public_guide_url_or_use_static_semantics"
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["runtime_apply_allowed"] is True
    assert operator["semantic_status"] != "SOURCE_BACKED_STRONG"
    assert preview["authority"] == "diagnostic_source_readiness_preview"
    assert preview["diagnostic_only"] is True
    assert preview["readiness_lane"] in {
        "source_partial_no_block",
        "acquisition_plan_ready_no_block",
    }
    assert preview["source_status_apply_blocking"] is False
    assert preview["runtime_apply_allowed"] is True
    assert operator["semantic_status"] != "SOURCE_BACKED_STRONG"


def test_candidate_registry_url_does_not_promote_without_full_text_claims(
    tmp_path: Path,
    monkeypatch,
):
    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_thin_cards_json(cards_json)
    source_url = "https://example.test/thin-mech-paladin"
    thin_page = tmp_path / "thin_mech_paladin.html"
    thin_page.write_text(
        "<html><title>Thin Mech Paladin Decklist</title>"
        "<body>Mech Paladin decklist only. Deck code and card list only.</body></html>",
        encoding="utf-8",
    )
    fixture_map = tmp_path / "fixture_map.json"
    fixture_map.write_text(json.dumps({source_url: str(thin_page)}), encoding="utf-8")
    monkeypatch.setattr(
        "hsconfig.source_candidate_plan.source_candidates_for_deck",
        lambda deck_name: [
            SourceCandidate(
                url=source_url,
                source_family="guide",
                deck_name=str(deck_name),
                archetype="wild_mech_paladin",
                reason="test candidate with a strong ceiling but thin fetched text",
                priority=10,
                expected_strength="guide_current_deck_match",
                strength_ceiling="candidate_strong",
                first_missing_source_action="none",
            )
        ],
    )
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    out = tmp_path / "configure"

    status = main(
        [
            "configure",
            "--deck-name",
            "MechPala",
            "--deck-code",
            VERIFIED_TEST_DECK_CODE,
            "--runtime-root",
            str(runtime),
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

    assert status == 0
    assert summary["source_candidate_urls"] == [source_url]
    assert acquisition["candidate_registry_url_count"] == 1
    assert acquisition["source_record_count"] == 1
    assert autopilot["strong_candidate"] is False
    assert autopilot["first_missing_source_action"] != "none"
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert operator["semantic_status"] != "SOURCE_BACKED_STRONG"


def test_configure_online_source_uses_explicit_urls_before_registry_urls(
    tmp_path: Path,
    monkeypatch,
):
    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_thin_cards_json(cards_json)
    explicit_url = "https://example.test/explicit-guide"
    registry_url = "https://example.test/registry-guide"
    fixture_map = tmp_path / "fixture_map.json"
    fixture_map.write_text(
        json.dumps(
            {
                explicit_url: str(FIXTURES / "source_pages" / "decklist_only.html"),
                registry_url: str(FIXTURES / "source_pages" / "decklist_only.html"),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "hsconfig.source_candidate_plan.source_candidates_for_deck",
        lambda deck_name: [
            SourceCandidate(
                url=registry_url,
                source_family="guide",
                deck_name=str(deck_name),
                archetype="test_archetype",
                reason="test registry candidate",
                priority=10,
                expected_strength="guide_current_deck_match",
            ),
            SourceCandidate(
                url=explicit_url,
                source_family="guide",
                deck_name=str(deck_name),
                archetype="test_archetype",
                reason="duplicate explicit URL",
                priority=20,
                expected_strength="guide_current_deck_match",
            ),
        ],
    )
    out = tmp_path / "configure"

    status = main(
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
            "--online-source",
            "--source-url",
            explicit_url,
            "--source-fixture-url-map-json",
            str(fixture_map),
            "--json",
        ]
    )

    summary = _read_json(out / "configure_summary.json")

    assert status == 0
    assert summary["source_candidate_urls"] == [registry_url, explicit_url]
    assert summary["source_urls"] == [explicit_url, registry_url]
    acquisition = _read_json(
        out / "02_source_acquisition" / "source_acquisition_report.json"
    )
    assert acquisition["explicit_source_url_count"] == 1
    assert acquisition["candidate_registry_url_count"] == 1


@pytest.mark.parametrize(
    "broken_plan",
    ["missing", "invalid", "malformed", "query", "query_row"],
)
def test_configure_online_source_rebuilds_registry_candidates_when_plan_is_unusable(
    tmp_path: Path,
    monkeypatch,
    broken_plan: str,
):
    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_thin_cards_json(cards_json)
    explicit_url = "https://example.test/explicit-guide"
    registry_url = "https://example.test/registry-guide"
    fixture_map = tmp_path / "fixture_map.json"
    fixture_map.write_text(
        json.dumps(
            {
                explicit_url: str(FIXTURES / "source_pages" / "decklist_only.html"),
                registry_url: str(FIXTURES / "source_pages" / "decklist_only.html"),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "hsconfig.source_candidate_plan.source_candidates_for_deck",
        lambda deck_name: [
            SourceCandidate(
                url=registry_url,
                source_family="guide",
                deck_name=str(deck_name),
                archetype="test_archetype",
                reason="test registry candidate",
                priority=10,
                expected_strength="guide_current_deck_match",
            ),
            SourceCandidate(
                url=explicit_url,
                source_family="guide",
                deck_name=str(deck_name),
                archetype="test_archetype",
                reason="duplicate explicit URL",
                priority=20,
                expected_strength="guide_current_deck_match",
            ),
        ],
    )
    original_manifest_payload = configure_command.source_manifest_payload

    def write_unusable_candidate_plan(args):
        payload, status = original_manifest_payload(args)
        plan_path = Path(args.out) / "source_candidate_plan.json"
        if broken_plan == "missing":
            plan_path.unlink()
        elif broken_plan == "invalid":
            plan_path.write_text("{", encoding="utf-8")
        else:
            if broken_plan == "query":
                plan = {
                    "authority": "diagnostic_source_candidate_plan",
                    "candidate_urls": ["ThinDeck deck guide 2026"],
                    "source_urls": [explicit_url, "ThinDeck deck guide 2026"],
                }
            elif broken_plan == "query_row":
                plan = {
                    "authority": "diagnostic_source_candidate_plan",
                    "candidate_urls": [],
                    "source_urls": [],
                    "candidate_url_rows": [
                        {"url": "ThinDeck deck guide 2026"},
                    ],
                }
            else:
                plan = {
                    "candidate_urls": "not-a-list",
                    "source_urls": ["ThinDeck deck guide 2026"],
                }
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
        return payload, status

    acquire_calls: list[list[str]] = []
    original_acquire_payload = configure_command.source_acquire_for_configure

    def capture_acquire_urls(args):
        acquire_calls.append(list(args.source_url))
        return original_acquire_payload(args)

    monkeypatch.setattr(
        configure_command,
        "source_manifest_payload",
        write_unusable_candidate_plan,
    )
    monkeypatch.setattr(
        configure_command,
        "source_acquire_for_configure",
        capture_acquire_urls,
    )
    out = tmp_path / "configure"

    status = main(
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
            "--online-source",
            "--source-url",
            explicit_url,
            "--source-fixture-url-map-json",
            str(fixture_map),
            "--json",
        ]
    )

    summary = _read_json(out / "configure_summary.json")

    assert status == 0
    assert acquire_calls == [[explicit_url, registry_url]]
    assert all(
        url.startswith("https://") and "?" not in url
        for url in acquire_calls[0]
    )
    assert summary["source_urls"] == [explicit_url, registry_url]


def test_configure_online_source_filters_invalid_explicit_source_url_before_acquisition(
    tmp_path: Path,
    monkeypatch,
):
    _stub_empty_fetches(monkeypatch)
    cards_json = tmp_path / "cards.json"
    _write_thin_cards_json(cards_json)
    invalid_source_url = "ThinDeck deck guide 2026"
    registry_url = "https://example.test/registry-guide"
    fixture_map = tmp_path / "fixture_map.json"
    fixture_map.write_text(
        json.dumps(
            {
                registry_url: str(FIXTURES / "source_pages" / "decklist_only.html"),
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "hsconfig.source_candidate_plan.source_candidates_for_deck",
        lambda deck_name: [
            SourceCandidate(
                url=registry_url,
                source_family="guide",
                deck_name=str(deck_name),
                archetype="test_archetype",
                reason="test registry candidate",
                priority=10,
                expected_strength="guide_current_deck_match",
            ),
        ],
    )
    acquire_calls: list[list[str]] = []
    original_acquire_payload = configure_command.source_acquire_for_configure

    def capture_acquire_urls(args):
        acquire_calls.append(list(args.source_url))
        return original_acquire_payload(args)

    monkeypatch.setattr(
        configure_command,
        "source_acquire_for_configure",
        capture_acquire_urls,
    )
    out = tmp_path / "configure"

    status = main(
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
            "--online-source",
            "--source-url",
            invalid_source_url,
            "--source-fixture-url-map-json",
            str(fixture_map),
            "--json",
        ]
    )

    summary = _read_json(out / "configure_summary.json")

    assert status == 0
    assert acquire_calls == [[registry_url]]
    assert summary["source_urls"] == [registry_url]
    assert summary["source_candidate_plan_summary"]["explicit_source_url_count"] == 0
