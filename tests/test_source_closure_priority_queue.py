from __future__ import annotations

import json
from pathlib import Path

from hsconfig.source_closure_optimizer import build_source_closure_priority_queue


def _package(tmp_path: Path, deck_name: str, operator: dict) -> Path:
    package = tmp_path / deck_name / "04_package"
    reports = package / "reports"
    reports.mkdir(parents=True)
    payload = {
        "deck": {"name": deck_name},
        "technical_status": "VALID_PACKAGE",
        "runtime_load_safe": True,
        "source_status_apply_blocking": False,
        "source_backed_status": "SOURCE_BACKED_PARTIAL",
        "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
        "default_only_runtime_surfaces": [],
        "source_backed_strong_closure": {
            "status": "needs_source_closure",
            "promotion_ready": False,
            "first_missing_source_action": "add_card_specific_source_claim",
            "diagnostic_only": True,
            "closure_profile_closed": False,
        },
    }
    payload.update(operator)
    (reports / "operator_summary.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    return package


def test_priority_queue_orders_partial_before_strong(tmp_path: Path) -> None:
    partial = _package(tmp_path, "BigShaman", {})
    strong = _package(
        tmp_path,
        "ShadowPriest",
        {
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "source_backed_strong_closure": {
                "status": "ready",
                "promotion_ready": True,
                "first_missing_source_action": "none",
                "diagnostic_only": True,
                "closure_profile_closed": True,
            },
        },
    )

    report = build_source_closure_priority_queue([strong, partial])

    assert report["schema_version"] == 1
    assert report["authority"] == "diagnostic_only"
    assert report["summary"]["deck_count"] == 2
    assert report["summary"]["strong_count"] == 1
    assert report["summary"]["apply_blocker_count"] == 0
    assert report["summary"]["default_only_count"] == 0
    assert [row["deck_name"] for row in report["priority_rows"]] == ["BigShaman"]


def test_priority_queue_keeps_operator_strong_when_research_snapshot_is_stale(
    tmp_path: Path,
) -> None:
    package = _package(
        tmp_path,
        "ShadowPriest",
        {
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "semantic_status": "SOURCE_BACKED_STRONG",
            "first_missing_source_action": "none",
            "source_backed_strong_closure": {
                "status": "ready",
                "promotion_ready": True,
                "first_missing_source_action": "none",
                "diagnostic_only": True,
                "closure_profile_closed": True,
            },
        },
    )
    research = tmp_path / "research-results"
    research.mkdir()
    (research / "ShadowPriest.json").write_text(
        json.dumps(
            {
                "deck_name": "ShadowPriest",
                "source_strength": "unfetched_acquisition_seed",
                "first_missing_source_action": (
                    "fetch_and_normalize_candidate_full_text_claims"
                ),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    report = build_source_closure_priority_queue([package], research_results_dir=research)

    assert report["summary"]["strong_count"] == 1
    assert report["summary"]["partial_count"] == 0
    assert report["records"][0]["decision"] == "strong"
    assert report["records"][0]["research_first_missing_source_action"] == (
        "fetch_and_normalize_candidate_full_text_claims"
    )
    assert report["priority_rows"] == []


def test_priority_queue_surfaces_default_only_as_strong_blocker_not_apply_blocker(
    tmp_path: Path,
) -> None:
    package = _package(
        tmp_path,
        "Synthetic",
        {
            "default_only_runtime_surfaces": ["Mulligan.json"],
            "first_missing_source_action": (
                "replace_default_only_runtime_surface_with_source_or_policy_claim"
            ),
        },
    )

    report = build_source_closure_priority_queue([package])

    row = report["records"][0]
    assert row["default_only_runtime_surfaces"] == ["Mulligan.json"]
    assert row["source_status_apply_blocking"] is False
    assert row["recommended_operator_action"] == (
        "replace default-only runtime surfaces with source-backed, "
        "policy-backed, or static-semantics-backed rows"
    )
