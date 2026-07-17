from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main
from hsconfig.source_evidence_closure import build_source_evidence_closure_report


SHADOWPRIEST_DECK_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def prepare_fixture_package(
    tmp_path: Path,
    *,
    deck_name: str,
    source_documents_fixture: str,
) -> Path:
    package_dir = tmp_path / deck_name
    code = main(
        [
            "prepare",
            "--deck-name",
            deck_name,
            "--deck-code",
            SHADOWPRIEST_DECK_CODE,
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package_dir),
            "--source-documents-json",
            str(Path("tests/fixtures") / source_documents_fixture),
            "--json",
        ]
    )

    assert code == 0
    return package_dir


def test_source_evidence_closure_reports_profile_verdict(tmp_path: Path):
    package_dir = prepare_fixture_package(
        tmp_path,
        deck_name="ShadowPriest",
        source_documents_fixture="source_documents_shadowpriest_strong.json",
    )

    report = read_json(package_dir / "reports" / "source_evidence_closure.json")

    assert report["closure_profile"] == "aggro_burn_hero_power"
    assert report["closure_profile_closed"] is True
    assert report["closure_profile_first_missing_link"] == "none"
    assert report["source_backed_status"] == "SOURCE_BACKED_STRONG"
    assert report["source_strong_ready"] is True
    assert report["first_missing_source_action"] == "none"
    assert report["source_missing_source_actions"] == []
    assert report["source_status_reasons"] == ["source_backed_strong_ready"]
    assert report["source_status_diagnostic_only"] is True
    assert report["source_status_apply_blocking"] is False
    assert report["apply_blocking"] is False


def test_source_evidence_closure_recomputes_source_status_from_gap_report():
    stale_operator_summary = {
        "technical_status": "VALID_PACKAGE",
        "semantic_status": "SOURCE_BACKED_STRONG",
        "next_action": "READY_TO_APPLY_OR_HANDOFF",
        "semantic_blockers": [],
        "source_backed_status": "SOURCE_BACKED_STRONG",
        "source_strong_ready": True,
        "first_missing_source_action": "none",
        "source_missing_source_actions": [],
        "source_status_reasons": ["source_backed_strong_ready"],
        "source_status_diagnostic_only": True,
        "source_status_apply_blocking": False,
        "default_only_runtime_surfaces": [],
        "source_backed_strong_closure": {
            "closure_profile": "aggro_burn_hero_power",
            "closure_profile_closed": True,
            "closure_profile_first_missing_link": "none",
            "closure_profile_apply_blocking": False,
        },
    }
    source_claim_gap_report = {
        "summary": {
            "blocked_cards": 0,
            "deck_surface_gap_count": 1,
            "first_missing_chain": {
                "surface": "mulligan",
                "first_missing_link": "needs_mulligan_claim",
                "recommended_source_claim_kind": "mulligan_claim",
                "next_action": "build_source_or_policy_backed_mulligan",
            },
        },
        "cards": {},
    }

    report = build_source_evidence_closure_report(
        deck_name="ShadowPriest",
        deck_code=SHADOWPRIEST_DECK_CODE,
        operator_summary=stale_operator_summary,
        source_to_runtime_explainability_report={"summary": {}},
        source_claim_gap_report=source_claim_gap_report,
    )

    assert report["source_backed_status"] == "SOURCE_BACKED_PARTIAL"
    assert report["source_strong_ready"] is False
    assert (
        report["first_missing_source_action"]
        == "build_source_or_policy_backed_mulligan"
    )
    assert report["source_missing_source_actions"] == [
        "build_source_or_policy_backed_mulligan"
    ]
    assert report["source_status_reasons"] == ["first_missing_claim_chain"]
    assert report["source_status_diagnostic_only"] is True
    assert report["source_status_apply_blocking"] is False
