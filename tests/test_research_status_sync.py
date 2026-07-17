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
            "source_strength": "unfetched_acquisition_seed",
            "first_missing_source_action": "fetch_and_normalize_candidate_full_text_claims",
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


def test_matching_strong_research_snapshot_is_current_with_canonical(
    tmp_path: Path,
) -> None:
    package_dir = _strong_package(tmp_path)
    strong_result = _research_result(
        tmp_path,
        "ShadowPriest",
        {
            "deck_name": "ShadowPriest",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "source_strength": "SOURCE_BACKED_STRONG",
            "first_missing_source_action": "none",
        },
    )

    report = build_research_status_sync_report(package_dir, [strong_result])

    assert report["summary"]["stale_or_seed_snapshot_count"] == 0
    assert report["summary"]["status_mismatch_count"] == 0
    row = report["research_snapshot_rows"][0]
    assert row["research_snapshot_kind"] == "canonical_like"
    assert row["snapshot_relation"] == "current_with_canonical"
    assert row["recommended_refresh_action"] == "none"


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
