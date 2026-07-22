from __future__ import annotations

import json
from pathlib import Path

import yaml

from hsconfig.research_result_contract_sentinel import (
    build_research_result_contract_sentinel,
)


FIELDS = {
    "fields": {
        "deck_name": {"type": "string"},
        "archetype": {"type": "string"},
        "current_deck_sources": {"type": "array"},
        "guide_sources": {"type": "array"},
        "source_strength": {"type": "string"},
        "lowerable_claim_kinds": {"type": "array"},
        "non_promoting_support": {"type": "array"},
        "first_missing_source_action": {"type": "string"},
        "notes": {"type": "string"},
    }
}


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_sentinel_reports_valid_partial_results_without_apply_blocking(
    tmp_path: Path,
) -> None:
    fields_path = tmp_path / "fields.yaml"
    fields_path.write_text(yaml.safe_dump(FIELDS), encoding="utf-8")
    results_dir = tmp_path / "results"
    _write_json(
        results_dir / "ShadowPriest.json",
        {
            "deck_name": "ShadowPriest",
            "archetype": "Wild Shadow Priest",
            "current_deck_sources": [],
            "guide_sources": [],
            "source_strength": "unfetched_acquisition_seed",
            "lowerable_claim_kinds": [],
            "non_promoting_support": [],
            "first_missing_source_action": (
                "fetch_and_normalize_candidate_full_text_claims"
            ),
            "source_status_apply_blocking_expected": False,
            "default_only_runtime_surfaces_expected": "none",
            "notes": "Seed snapshots are diagnostic only.",
        },
    )

    report = build_research_result_contract_sentinel(fields_path, results_dir)

    assert report["authority"] == "diagnostic_only"
    assert report["operator_gate_impact"] == "diagnostic_only"
    assert report["normal_apply_authority"] == "reports/operator_summary.json"
    assert report["source_status_apply_blocking"] is False
    assert report["summary"] == {
        "status": "clean",
        "field_contract_valid": True,
        "result_count": 1,
        "strict_valid_count": 1,
        "strict_invalid_count": 0,
        "contract_invalid_count": 0,
        "seed_only_count": 1,
        "strong_promoting_count": 0,
        "no_op_validation_risk": False,
        "source_status_apply_blocking": False,
    }
    assert report["result_rows"][0]["deck_name"] == "ShadowPriest"
    assert report["result_rows"][0]["snapshot_kind"] == "seed_only"
    assert report["result_rows"][0]["strict_research_result_valid"] is True


def test_sentinel_surfaces_invalid_strong_result_without_blocking(
    tmp_path: Path,
) -> None:
    fields_path = tmp_path / "fields.yaml"
    fields_path.write_text(yaml.safe_dump(FIELDS), encoding="utf-8")
    results_dir = tmp_path / "results"
    _write_json(
        results_dir / "CtAPaladin.json",
        {
            "deck_name": "CtAPaladin",
            "archetype": "Wild Call to Arms Paladin",
            "current_deck_sources": [],
            "guide_sources": [],
            "source_strength": "exact_full_text_guide",
            "source_visibility": "full_text",
            "lowerable_claim_kinds": ["mulligan_keep"],
            "non_promoting_support": [],
            "default_only_runtime_surfaces": [],
            "first_missing_source_action": "none",
            "notes": "Missing freshness metadata must remain visible.",
        },
    )

    report = build_research_result_contract_sentinel(fields_path, results_dir)

    assert report["summary"]["status"] == "attention"
    assert report["summary"]["strict_invalid_count"] == 1
    assert report["source_status_apply_blocking"] is False
    assert report["result_rows"][0]["strict_research_result_valid"] is False
    assert (
        "strong_requires_current_or_evergreen_freshness"
        in report["result_rows"][0]["strict_research_result_errors"]
    )


def test_sentinel_detects_no_op_validation_risk_when_fields_are_malformed(
    tmp_path: Path,
) -> None:
    fields_path = tmp_path / "fields.yaml"
    fields_path.write_text("fields: []\n", encoding="utf-8")
    results_dir = tmp_path / "results"
    _write_json(
        results_dir / "PirateDH.json",
        {
            "deck_name": "PirateDH",
            "source_strength": "decklist_or_stats_only",
            "first_missing_source_action": "add_card_specific_source_claim",
        },
    )

    report = build_research_result_contract_sentinel(fields_path, results_dir)

    assert report["summary"]["status"] == "attention"
    assert report["summary"]["field_contract_valid"] is False
    assert report["summary"]["no_op_validation_risk"] is True
    assert report["source_status_apply_blocking"] is False


def test_sentinel_surfaces_strict_valid_but_contract_invalid_rows(
    tmp_path: Path,
) -> None:
    fields_path = tmp_path / "fields.yaml"
    fields_path.write_text(yaml.safe_dump(FIELDS), encoding="utf-8")
    results_dir = tmp_path / "results"
    _write_json(
        results_dir / "Boarlock.json",
        {
            "deck_name": "Boarlock",
            "archetype": "Wild Boar Warlock",
            "current_deck_sources": [],
            "guide_sources": [],
            "source_strength": "snippet_only",
            "lowerable_claim_kinds": [],
            "non_promoting_support": [],
            "first_missing_source_action": "fetch_full_text_guide",
            "notes": "Strict fields are present, but exact deck identity is missing.",
        },
    )

    report = build_research_result_contract_sentinel(fields_path, results_dir)

    assert report["summary"]["status"] == "attention"
    assert report["summary"]["strict_invalid_count"] == 0
    assert report["summary"]["contract_invalid_count"] == 1
    assert report["result_rows"][0]["strict_research_result_valid"] is True
    assert report["result_rows"][0]["contract_valid"] is False
    assert report["source_status_apply_blocking"] is False
