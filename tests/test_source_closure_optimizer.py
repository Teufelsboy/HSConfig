from __future__ import annotations

import json
from pathlib import Path

from hsconfig.source_closure_optimizer import build_source_closure_optimizer_report


def _write_package(tmp_path: Path, operator: dict) -> Path:
    package = tmp_path / "04_package"
    reports = package / "reports"
    reports.mkdir(parents=True)
    (reports / "operator_summary.json").write_text(
        json.dumps(operator, indent=2),
        encoding="utf-8",
    )
    return package


def _operator(**overrides: object) -> dict:
    payload = {
        "deck_name": "ShadowPriest",
        "technical_status": "VALID_PACKAGE",
        "runtime_load_safe": True,
        "source_status_apply_blocking": False,
        "source_backed_status": "SOURCE_BACKED_STRONG",
        "semantic_status": "SOURCE_BACKED_STRONG",
        "default_only_runtime_surfaces": [],
        "default_only_runtime_surface_details": [],
        "no_default_only_runtime_status": "clean",
        "source_backed_strong_closure": {
            "closed": True,
            "first_missing_source_action": "none",
        },
    }
    payload.update(overrides)
    return payload


def test_shadowpriest_strong_when_operator_closure_is_clean(tmp_path: Path) -> None:
    package = _write_package(tmp_path, _operator())

    report = build_source_closure_optimizer_report(package)

    assert report["decision"] == "strong"
    assert report["source_status_apply_blocking"] is False
    assert report["runtime_package_usable"] is True
    assert report["default_only_blocks_strong"] is False
    assert report["first_missing_source_action"] == "none"


def test_default_only_never_promotes_to_strong(tmp_path: Path) -> None:
    package = _write_package(
        tmp_path,
        _operator(
            source_backed_status="SOURCE_BACKED_STRONG",
            semantic_status="SOURCE_BACKED_STRONG",
            default_only_runtime_surfaces=["Mulligan.json"],
            default_only_runtime_surface_details=[
                {
                    "surface": "Mulligan.json",
                    "reason": "default_only_surface_not_strong_evidence",
                }
            ],
            no_default_only_runtime_status="blocked",
        ),
    )

    report = build_source_closure_optimizer_report(package)

    assert report["decision"] == "partial_source_action_needed"
    assert report["source_status_apply_blocking"] is False
    assert report["runtime_package_usable"] is True
    assert report["default_only_blocks_strong"] is True
    assert report["blocking_reasons"] == ["default_only_runtime_surfaces_present"]


def test_preserves_known_partial_stop_conditions(tmp_path: Path) -> None:
    package = _write_package(
        tmp_path,
        _operator(
            deck_name="Kingslayer",
            source_backed_status="SOURCE_BACKED_PARTIAL",
            semantic_status="VALID_BUT_NOT_GUIDE_STRONG",
            source_backed_strong_closure={
                "closed": False,
                "first_missing_source_action": "add_kingslayer_quick_pick_mulligan_source",
            },
        ),
    )

    report = build_source_closure_optimizer_report(package)

    assert report["decision"] == "preserved_partial_stop_condition"
    assert report["first_missing_source_action"] == "add_kingslayer_quick_pick_mulligan_source"
    assert report["source_status_apply_blocking"] is False
    assert report["runtime_package_usable"] is True


def test_context_only_candidate_is_load_safe_not_strong(tmp_path: Path) -> None:
    package = _write_package(
        tmp_path,
        _operator(
            deck_name="SyntheticContextOnly",
            source_backed_status="STATIC_SEMANTICS_USABLE",
            semantic_status="VALID_BUT_NOT_GUIDE_STRONG",
            source_backed_strong_closure={
                "closed": False,
                "first_missing_source_action": "fetch_runtime_lowerable_public_guide",
            },
        ),
    )
    manifest = tmp_path / "source-candidate-proof-decks.json"
    manifest.write_text(
        json.dumps(
            {
                "decks": [
                    {
                        "deck_name": "SyntheticContextOnly",
                        "expected_strength_ceiling": "context_only",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = build_source_closure_optimizer_report(
        package,
        candidate_proof_path=manifest,
    )

    assert report["decision"] == "context_only_load_safe"
    assert report["runtime_package_usable"] is True
    assert report["source_status_apply_blocking"] is False


def test_invalid_package_is_invalid_even_if_source_fields_are_present(tmp_path: Path) -> None:
    package = _write_package(
        tmp_path,
        _operator(
            technical_status="INVALID_PACKAGE",
            runtime_load_safe=False,
        ),
    )

    report = build_source_closure_optimizer_report(package)

    assert report["decision"] == "invalid_package"
    assert report["runtime_package_usable"] is False
