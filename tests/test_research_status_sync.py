from __future__ import annotations

import json
from pathlib import Path

from hsconfig.research_status_sync import build_research_status_sync_report


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _package(tmp_path: Path, status: str) -> Path:
    package_dir = tmp_path / "package"
    _write_json(
        package_dir / "reports" / "operator_summary.json",
        {
            "source_status": status,
            "source_status_apply_blocking": False,
        },
    )
    return package_dir


def _research_result(tmp_path: Path, deck: str, payload: dict) -> Path:
    path = tmp_path / "research" / f"{deck}.json"
    _write_json(path, payload)
    return path


def test_seed_only_research_snapshot_cannot_downgrade_strong_package(tmp_path: Path) -> None:
    package_dir = _package(tmp_path, "SOURCE_BACKED_STRONG")
    seed_result = _research_result(
        tmp_path,
        "ShadowPriest",
        {
            "deck_name": "ShadowPriest",
            "source_status": "SOURCE_BACKED_PARTIAL",
            "source_strength": "decklist_only",
            "items": [{"kind": "candidate_url_only"}],
        },
    )

    report = build_research_status_sync_report(package_dir, [seed_result])

    row = report["research_snapshots"][0]
    assert row["canonical_status"] == "SOURCE_BACKED_STRONG"
    assert row["research_status"] == "SOURCE_BACKED_PARTIAL"
    assert row["snapshot_kind"] == "seed_only"
    assert row["relation_to_canonical"] == "stale_or_seed_only"
    assert row["canonical_downgrade_allowed"] is False
    assert row["canonical_promotion_allowed"] is False
    assert row["source_status_apply_blocking"] is False
    assert report["summary"]["authoritative_status"] == "SOURCE_BACKED_STRONG"
    assert report["summary"]["normal_apply_authority"] == "reports/operator_summary.json"
    assert report["summary"]["research_snapshot_authority"] == "diagnostic_only"


def test_matching_strong_research_snapshot_is_current_with_canonical(tmp_path: Path) -> None:
    package_dir = _package(tmp_path, "SOURCE_BACKED_STRONG")
    strong_result = _research_result(
        tmp_path,
        "ShadowPriest",
        {
            "deck_name": "ShadowPriest",
            "source_status": "SOURCE_BACKED_STRONG",
            "source_strength": "fetched_current_full_text_guide",
        },
    )

    report = build_research_status_sync_report(package_dir, [strong_result])

    row = report["research_snapshots"][0]
    assert row["snapshot_kind"] == "strong_snapshot"
    assert row["relation_to_canonical"] == "current_with_canonical"
    assert row["recommended_refresh_action"] == "none"
    assert report["summary"]["counts"]["current_with_canonical"] == 1


def test_research_snapshot_cannot_promote_partial_package(tmp_path: Path) -> None:
    package_dir = _package(tmp_path, "SOURCE_BACKED_PARTIAL")
    strong_result = _research_result(
        tmp_path,
        "CtAPaladin",
        {
            "deck_name": "CtAPaladin",
            "source_status": "SOURCE_BACKED_STRONG",
            "source_strength": "fetched_current_full_text_guide",
        },
    )

    report = build_research_status_sync_report(package_dir, [strong_result])

    row = report["research_snapshots"][0]
    assert row["canonical_status"] == "SOURCE_BACKED_PARTIAL"
    assert row["research_status"] == "SOURCE_BACKED_STRONG"
    assert row["relation_to_canonical"] == "conflicts_with_canonical"
    assert row["canonical_promotion_allowed"] is False
    assert row["recommended_refresh_action"] == "refresh_package_or_research_snapshot"
    assert report["summary"]["authoritative_status"] == "SOURCE_BACKED_PARTIAL"


def test_missing_research_snapshot_is_visible_but_not_apply_blocking(tmp_path: Path) -> None:
    package_dir = _package(tmp_path, "SOURCE_BACKED_STRONG")

    report = build_research_status_sync_report(package_dir, [])

    assert report["research_snapshots"] == [
        {
            "path": None,
            "deck_name": None,
            "canonical_status": "SOURCE_BACKED_STRONG",
            "research_status": None,
            "snapshot_kind": "missing",
            "relation_to_canonical": "missing",
            "recommended_refresh_action": "run_research_deep_snapshot_refresh",
            "canonical_downgrade_allowed": False,
            "canonical_promotion_allowed": False,
            "source_status_apply_blocking": False,
        }
    ]
    assert report["summary"]["counts"]["missing"] == 1
    assert report["summary"]["source_status_apply_blocking"] is False
