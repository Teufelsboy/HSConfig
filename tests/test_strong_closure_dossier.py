from __future__ import annotations

import hashlib
from pathlib import Path

from hsconfig.io import write_json
from hsconfig.strong_closure_dossier import build_strong_closure_dossier


SHADOW_DECK_CODE = "AAEBAa0GExample"


def _package(
    tmp_path: Path,
    *,
    deck_name: str = "ShadowPriest",
    deck_code: str = SHADOW_DECK_CODE,
    source_status: str = "SOURCE_BACKED_STRONG",
    source_strong_ready: bool = True,
    first_missing_source_action: str = "none",
    default_only_runtime_surfaces: list[str] | None = None,
) -> Path:
    package_dir = tmp_path / "04_package"
    write_json(
        package_dir / "reports" / "operator_summary.json",
        {
            "deck": {
                "name": deck_name,
                "deck_code_hash": (
                    f"sha256:{hashlib.sha256(deck_code.encode('utf-8')).hexdigest()}"
                ),
            },
            "technical_status": "VALID_PACKAGE",
            "semantic_status": source_status,
            "source_backed_status": source_status,
            "source_strong_ready": source_strong_ready,
            "first_missing_source_action": first_missing_source_action,
            "source_status_apply_blocking": False,
            "source_status_diagnostic_only": True,
            "default_only_runtime_surfaces": default_only_runtime_surfaces or [],
            "no_default_only_runtime_status": (
                "blocked" if default_only_runtime_surfaces else "clean"
            ),
            "runtime_apply_allowed": True,
            "runtime_apply_mode": "load_safe_apply",
            "next_action": (
                "READY_TO_APPLY_OR_HANDOFF"
                if source_status == "SOURCE_BACKED_STRONG"
                else "READY_TO_APPLY_WITH_WARNINGS"
            ),
        },
    )
    write_json(
        package_dir / "reports" / "source_claim_gap_report.json",
        {
            "summary": {
                "blocked_cards": 0 if source_status == "SOURCE_BACKED_STRONG" else 1,
                "first_missing_chain": (
                    None
                    if source_status == "SOURCE_BACKED_STRONG"
                    else {
                        "card_id": "CARD_A",
                        "first_missing_link": "needs_guide_claim",
                        "recommended_source_claim_kind": "card_role",
                        "next_action": first_missing_source_action,
                    }
                ),
            },
            "cards": {},
        },
    )
    return package_dir


def test_dossier_confirms_strong_without_becoming_apply_authority(
    tmp_path: Path,
) -> None:
    package_dir = _package(tmp_path)

    report = build_strong_closure_dossier(package_dir)

    assert report["authority"] == "diagnostic_only"
    assert report["operator_gate_impact"] == "diagnostic_only"
    assert report["normal_apply_authority"] == "reports/operator_summary.json"
    assert report["deck_name"] == "ShadowPriest"
    assert report["promotion_verdict"] == "SOURCE_BACKED_STRONG_CONFIRMED"
    assert report["strong_contract_closed"] is True
    assert report["source_status_apply_blocking"] is False
    assert report["first_missing_source_action"] == "none"
    assert report["default_only_runtime_surfaces"] == []
    assert report["runtime_apply_mode"] == "load_safe_apply"


def test_dossier_keeps_partial_load_safe_and_actionable(tmp_path: Path) -> None:
    package_dir = _package(
        tmp_path,
        deck_name="PirateDH",
        source_status="SOURCE_BACKED_PARTIAL",
        source_strong_ready=False,
        first_missing_source_action="add_card_specific_source_claim",
    )

    report = build_strong_closure_dossier(package_dir)

    assert report["deck_name"] == "PirateDH"
    assert report["promotion_verdict"] == "PROMOTION_BLOCKED"
    assert report["source_backed_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["strong_contract_closed"] is False
    assert report["runtime_package_usable"] is True
    assert report["source_status_apply_blocking"] is False
    assert report["first_missing_source_action"] == "add_card_specific_source_claim"
    assert report["first_missing_chain"]["card_id"] == "CARD_A"


def test_dossier_blocks_strong_when_default_only_surface_is_present(
    tmp_path: Path,
) -> None:
    package_dir = _package(
        tmp_path,
        source_status="SOURCE_BACKED_STRONG",
        source_strong_ready=True,
        default_only_runtime_surfaces=["mulligan"],
    )

    report = build_strong_closure_dossier(package_dir)

    assert report["promotion_verdict"] == "PROMOTION_BLOCKED"
    assert report["source_backed_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["strong_contract_closed"] is False
    assert report["default_only_runtime_surfaces"] == ["mulligan"]
    assert report["source_status_apply_blocking"] is False
    assert report["first_missing_source_action"] == (
        "replace_default_only_runtime_surface_with_source_or_policy_claim"
    )


def test_dossier_keeps_seed_only_research_snapshot_diagnostic_only(
    tmp_path: Path,
) -> None:
    package_dir = _package(tmp_path)
    research_path = tmp_path / "shadowpriest_research_seed.json"
    write_json(
        research_path,
        {
            "deck_name": "ShadowPriest",
            "source_strength": "decklist_or_stats_only",
            "first_missing_source_action": "add_explicit_mulligan_source",
        },
    )

    report = build_strong_closure_dossier(package_dir, [research_path])
    row = report["research_snapshot_rows"][0]

    assert row["snapshot_kind"] == "seed_only"
    assert row["canonical_promotion_allowed"] is False
    assert row["source_status_apply_blocking"] is False
    assert report["summary"]["research_snapshot_count"] == 1
    assert report["summary"]["research_promoting_snapshot_count"] == 0


def test_dossier_does_not_count_other_deck_research_as_promoting(
    tmp_path: Path,
) -> None:
    package_dir = _package(tmp_path, deck_name="ShadowPriest")
    research_path = tmp_path / "other_deck_strong.json"
    write_json(
        research_path,
        {
            "deck_name": "CtAPaladin",
            "deck_code": "AAEBAZ8FExample",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "source_strength": "SOURCE_BACKED_STRONG",
            "source_visibility": "full_text",
            "freshness_status": "current",
            "lowerable_claim_kinds": ["mulligan_keep"],
            "first_missing_source_action": "none",
        },
    )

    report = build_strong_closure_dossier(package_dir, [research_path])
    row = report["research_snapshot_rows"][0]

    assert row["package_deck_match"] is False
    assert row["snapshot_relation"] == "different_deck_snapshot"
    assert row["canonical_promotion_allowed"] is False
    assert report["summary"]["research_snapshot_count"] == 1
    assert report["summary"]["research_promoting_snapshot_count"] == 0


def test_dossier_does_not_count_same_name_different_deck_code_as_promoting(
    tmp_path: Path,
) -> None:
    package_dir = _package(
        tmp_path,
        deck_name="ShadowPriest",
        deck_code=SHADOW_DECK_CODE,
    )
    research_path = tmp_path / "same_name_other_code_strong.json"
    write_json(
        research_path,
        {
            "deck_name": "ShadowPriest",
            "deck_code": "AAEBAa0GDifferentExample",
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "source_strength": "SOURCE_BACKED_STRONG",
            "source_visibility": "full_text",
            "freshness_status": "current",
            "lowerable_claim_kinds": ["mulligan_keep"],
            "first_missing_source_action": "none",
        },
    )

    report = build_strong_closure_dossier(package_dir, [research_path])
    row = report["research_snapshot_rows"][0]

    assert row["package_deck_name_match"] is True
    assert row["package_deck_match"] is False
    assert row["snapshot_relation"] == "unverified_package_deck_snapshot"
    assert row["snapshot_kind"] == "strong"
    assert row["canonical_promotion_allowed"] is False
    assert report["summary"]["research_promoting_snapshot_count"] == 0


def test_dossier_does_not_promote_strict_invalid_matching_strong_snapshot(
    tmp_path: Path,
) -> None:
    package_dir = _package(tmp_path)
    research_path = tmp_path / "matching_incomplete_strong.json"
    write_json(
        research_path,
        {
            "deck_name": "ShadowPriest",
            "deck_code": SHADOW_DECK_CODE,
            "source_backed_status": "SOURCE_BACKED_STRONG",
            "source_strength": "SOURCE_BACKED_STRONG",
            "source_visibility": "full_text",
            "freshness_status": "current",
            "lowerable_claim_kinds": ["mulligan_keep"],
            "default_only_runtime_surfaces": [],
            "first_missing_source_action": "none",
        },
    )

    report = build_strong_closure_dossier(package_dir, [research_path])
    row = report["research_snapshot_rows"][0]

    assert row["package_deck_match"] is True
    assert row["strict_research_result_valid"] is False
    assert row["snapshot_relation"] == "requires_research_result_repair"
    assert row["canonical_promotion_allowed"] is False
    assert row["source_status_apply_blocking"] is False
    assert report["summary"]["research_promoting_snapshot_count"] == 0
