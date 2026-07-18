from __future__ import annotations

import json
from pathlib import Path

from hsconfig.research_status_sync import build_research_status_sync_report


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _strong_package(tmp_path: Path, deck_name: str = "ShadowPriest") -> Path:
    package_dir = tmp_path / "04_package"
    _write_json(
        package_dir / "reports" / "operator_summary.json",
        {
            "deck": {"name": deck_name},
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "source_strong_ready": True,
            "first_missing_source_action": "none",
            "source_status_apply_blocking": False,
            "source_status_diagnostic_only": True,
            "default_only_runtime_surfaces": [],
            "no_default_only_runtime_status": "clean",
        },
    )
    return package_dir


def _research_result(
    tmp_path: Path,
    deck: str,
    payload: dict[str, object],
) -> Path:
    path = tmp_path / "research" / f"{deck}.json"
    _write_json(path, payload)
    return path


def test_seed_only_research_snapshot_cannot_downgrade_strong_package(
    tmp_path: Path,
) -> None:
    package_dir = _strong_package(tmp_path)
    seed_result = _research_result(
        tmp_path,
        "ShadowPriest",
        {
            "deck_name": "ShadowPriest",
            "deck_code": "AAEBAa0GExample",
            "source_strength": "unfetched_acquisition_seed",
            "first_missing_source_action": "fetch_and_normalize_candidate_full_text_claims",
            "lowerable_claim_kinds": [],
        },
    )

    report = build_research_status_sync_report(package_dir, [seed_result])

    assert report["authority"] == "diagnostic_only"
    assert report["operator_gate_impact"] == "diagnostic_only"
    assert report["normal_apply_authority"] == "reports/operator_summary.json"
    assert report["summary"]["canonical_source_backed_status"] == "SOURCE_BACKED_STRONG"
    assert report["summary"]["stale_or_seed_snapshot_count"] == 1
    assert report["summary"]["canonical_downgrade_allowed"] is False
    assert report["summary"]["source_status_apply_blocking"] is False
    row = report["research_snapshot_rows"][0]
    assert row["snapshot_relation"] == "stale_or_seed_only"
    assert row["research_snapshot_kind"] == "seed_only"
    assert row["canonical_downgrade_allowed"] is False
    assert row["canonical_promotion_allowed"] is False
    assert row["source_status_apply_blocking"] is False
    assert (
        row["recommended_refresh_action"]
        == "refresh_research_snapshot_from_canonical_package"
    )


def test_decklist_or_stats_research_snapshot_matches_partial_package_as_seed(
    tmp_path: Path,
) -> None:
    package_dir = tmp_path / "04_package"
    _write_json(
        package_dir / "reports" / "operator_summary.json",
        {
            "deck": {"name": "CtAPaladin"},
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "source_backed_status": "SOURCE_BACKED_PARTIAL",
            "source_strong_ready": False,
            "first_missing_source_action": "add_explicit_mulligan_source",
            "source_status_apply_blocking": False,
            "source_status_diagnostic_only": True,
            "default_only_runtime_surfaces": [],
        },
    )
    decklist_result = _research_result(
        tmp_path,
        "CtAPaladin",
        {
            "deck_name": "CtAPaladin",
            "deck_code": "AAEBAZ8FExample",
            "source_strength": "decklist_or_stats_only",
            "first_missing_source_action": "add_explicit_mulligan_source",
            "lowerable_claim_kinds": [],
        },
    )

    report = build_research_status_sync_report(package_dir, [decklist_result])

    row = report["research_snapshot_rows"][0]
    assert row["research_source_backed_status"] == "SOURCE_BACKED_PARTIAL"
    assert row["research_snapshot_kind"] == "seed_only"
    assert row["snapshot_relation"] == "current_with_canonical"
    assert row["canonical_promotion_allowed"] is False


def test_matching_strong_research_snapshot_is_current_with_canonical(
    tmp_path: Path,
) -> None:
    package_dir = _strong_package(tmp_path)
    strong_result = _research_result(
        tmp_path,
        "ShadowPriest",
        {
            "deck_name": "ShadowPriest",
            "deck_code": "AAEBAa0GExample",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "source_strength": "SOURCE_BACKED_STRONG",
            "first_missing_source_action": "none",
            "source_visibility": "full_text",
            "freshness_status": "current",
            "lowerable_claim_kinds": ["mulligan_keep"],
        },
    )

    report = build_research_status_sync_report(package_dir, [strong_result])

    assert report["summary"]["stale_or_seed_snapshot_count"] == 0
    assert report["summary"]["status_mismatch_count"] == 0
    row = report["research_snapshot_rows"][0]
    assert row["research_snapshot_kind"] == "strong"
    assert row["snapshot_relation"] == "current_with_canonical"
    assert row["recommended_refresh_action"] == "none"


def test_mixed_results_only_treat_matching_deck_snapshot_as_current(
    tmp_path: Path,
) -> None:
    package_dir = _strong_package(tmp_path)
    matching_result = _research_result(
        tmp_path,
        "ShadowPriest",
        {
            "deck_name": "Shadow Priest",
            "deck_code": "AAEBAa0GExample",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "source_strength": "SOURCE_BACKED_STRONG",
            "first_missing_source_action": "none",
            "source_visibility": "full_text",
            "freshness_status": "current",
            "lowerable_claim_kinds": ["mulligan_keep"],
        },
    )
    other_deck_result = _research_result(
        tmp_path,
        "CtAPaladin",
        {
            "deck_name": "CtAPaladin",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "source_strength": "SOURCE_BACKED_STRONG",
        },
    )

    report = build_research_status_sync_report(
        package_dir,
        [matching_result, other_deck_result],
    )

    rows_by_deck = {
        row["deck_name"]: row for row in report["research_snapshot_rows"]
    }
    assert rows_by_deck["Shadow Priest"]["snapshot_relation"] == "current_with_canonical"
    assert rows_by_deck["CtAPaladin"]["snapshot_relation"] == "different_deck_snapshot"
    assert report["summary"]["missing_research_snapshot"] is False
    assert report["summary"]["matching_research_snapshot_count"] == 1


def test_strong_looking_contract_partial_snapshot_is_not_current_with_canonical(
    tmp_path: Path,
) -> None:
    package_dir = _strong_package(tmp_path)
    partial_strong_result = _research_result(
        tmp_path,
        "ShadowPriest",
        {
            "deck_name": "ShadowPriest",
            "deck_code": "AAEBAa0GExample",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "source_strength": "SOURCE_BACKED_STRONG",
            "source_visibility": "snippet_only",
            "first_missing_source_action": "none",
            "lowerable_claim_kinds": ["mulligan_keep"],
        },
    )

    report = build_research_status_sync_report(package_dir, [partial_strong_result])

    row = report["research_snapshot_rows"][0]
    assert row["research_snapshot_kind"] == "partial"
    assert row["snapshot_relation"] == "stale_or_seed_only"
    assert (
        row["recommended_refresh_action"]
        == "refresh_research_snapshot_from_canonical_package"
    )


def test_different_deck_strong_snapshot_is_not_current_with_canonical(
    tmp_path: Path,
) -> None:
    package_dir = _strong_package(tmp_path)
    other_deck_result = _research_result(
        tmp_path,
        "CtAPaladin",
        {
            "deck_name": "CtAPaladin",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "source_strength": "SOURCE_BACKED_STRONG",
        },
    )

    report = build_research_status_sync_report(package_dir, [other_deck_result])

    row = report["research_snapshot_rows"][0]
    assert row["snapshot_relation"] == "different_deck_snapshot"
    assert row["recommended_refresh_action"] == "inspect_research_snapshot_deck_identity"
    assert row["canonical_downgrade_allowed"] is False
    assert row["canonical_promotion_allowed"] is False


def test_other_deck_results_do_not_hide_missing_matching_research_snapshot(
    tmp_path: Path,
) -> None:
    package_dir = _strong_package(tmp_path)
    other_deck_result = _research_result(
        tmp_path,
        "CtAPaladin",
        {
            "deck_name": "CtAPaladin",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "source_strength": "SOURCE_BACKED_STRONG",
        },
    )

    report = build_research_status_sync_report(package_dir, [other_deck_result])

    assert report["summary"]["research_snapshot_count"] == 1
    assert report["summary"]["matching_research_snapshot_count"] == 0
    assert report["summary"]["missing_research_snapshot"] is True


def test_research_snapshot_cannot_promote_partial_package(tmp_path: Path) -> None:
    package_dir = tmp_path / "04_package"
    _write_json(
        package_dir / "reports" / "operator_summary.json",
        {
            "deck": {"name": "CtAPaladin"},
            "technical_status": "VALID_PACKAGE",
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "source_backed_status": "SOURCE_BACKED_PARTIAL",
            "source_strong_ready": False,
            "first_missing_source_action": "add_current_cta_paladin_mulligan_keep_source",
            "source_status_apply_blocking": False,
            "source_status_diagnostic_only": True,
            "default_only_runtime_surfaces": [],
        },
    )
    strong_result = _research_result(
        tmp_path,
        "CtAPaladin",
        {
            "deck_name": "CtAPaladin",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "source_strength": "SOURCE_BACKED_STRONG",
            "first_missing_source_action": "none",
        },
    )

    report = build_research_status_sync_report(package_dir, [strong_result])

    row = report["research_snapshot_rows"][0]
    assert row["snapshot_relation"] == "conflicts_with_canonical"
    assert row["canonical_promotion_allowed"] is False
    assert (
        row["recommended_refresh_action"]
        == "inspect_package_and_research_snapshot_before_updating_docs"
    )
    assert report["summary"]["canonical_source_backed_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["summary"]["source_status_apply_blocking"] is False


def test_missing_research_snapshot_is_visible_but_not_apply_blocking(
    tmp_path: Path,
) -> None:
    package_dir = _strong_package(tmp_path)

    report = build_research_status_sync_report(package_dir, [])

    assert report["research_snapshot_rows"] == []
    assert report["summary"]["missing_research_snapshot"] is True
    assert report["summary"]["source_status_apply_blocking"] is False


def test_sync_row_includes_research_result_contract_diagnostics(tmp_path: Path) -> None:
    package_dir = _strong_package(tmp_path)
    seed_result = _research_result(
        tmp_path,
        "ShadowPriest",
        {
            "deck_name": "ShadowPriest",
            "deck_code": "AAEBAa0GExample",
            "source_strength": "unfetched_acquisition_seed",
            "first_missing_source_action": "fetch_and_normalize_candidate_full_text_claims",
            "lowerable_claim_kinds": [],
        },
    )

    report = build_research_status_sync_report(package_dir, [seed_result])

    row = report["research_snapshot_rows"][0]
    assert row["research_contract_valid"] is True
    assert row["research_snapshot_kind"] == "seed_only"
    assert row["research_canonical_promotion_allowed"] is False
    assert row["research_canonical_downgrade_allowed"] is False
    assert row["research_contract_errors"] == []
    assert report["summary"]["canonical_source_backed_status"] == "SOURCE_BACKED_STRONG"


def test_invalid_research_payload_stays_diagnostic_and_non_blocking(tmp_path: Path) -> None:
    package_dir = _strong_package(tmp_path)
    invalid_result = _research_result(
        tmp_path,
        "invalid",
        {
            "source_strength": "unfetched_acquisition_seed",
            "lowerable_claim_kinds": [],
        },
    )

    report = build_research_status_sync_report(package_dir, [invalid_result])

    row = report["research_snapshot_rows"][0]
    assert row["research_contract_valid"] is False
    assert row["research_snapshot_kind"] == "invalid"
    assert row["research_contract_errors"] == ["missing_deck_identity"]
    assert row["source_status_apply_blocking"] is False
    assert report["summary"]["source_status_apply_blocking"] is False


def test_research_status_sync_includes_strict_validation_without_blocking(
    tmp_path: Path,
) -> None:
    package_dir = _strong_package(tmp_path)
    research_path = _research_result(
        tmp_path,
        "ShadowPriest",
        {
            "deck_name": "ShadowPriest",
            "source_strength": "decklist_or_stats_only",
            "first_missing_source_action": "add_explicit_mulligan_source",
        },
    )

    report = build_research_status_sync_report(package_dir, [research_path])
    row = report["research_snapshot_rows"][0]

    assert row["strict_research_result_valid"] is False
    assert "missing_field:archetype" in row["strict_research_result_errors"]
    assert row["strict_research_result_field_count"] == 3
    assert row["source_status_apply_blocking"] is False
    assert report["summary"]["source_status_apply_blocking"] is False
