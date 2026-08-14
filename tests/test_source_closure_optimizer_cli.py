from __future__ import annotations

import json
from pathlib import Path

import pytest

from hsconfig.cli import main


def _write_package(root: Path, deck_name: str) -> Path:
    package = root / deck_name / "04_package"
    reports = package / "reports"
    reports.mkdir(parents=True)
    (reports / "operator_summary.json").write_text(
        json.dumps(
            {
                "deck_name": deck_name,
                "technical_status": "VALID_PACKAGE",
                "runtime_load_safe": True,
                "source_status_apply_blocking": False,
                "source_backed_status": "SOURCE_BACKED_STRONG",
                "semantic_status": "SOURCE_BACKED_STRONG",
                "default_only_runtime_surfaces": [],
                "source_backed_strong_closure": {
                    "closed": True,
                    "first_missing_source_action": "none",
                },
            }
        ),
        encoding="utf-8",
    )
    return package


def test_source_closure_optimizer_writes_batch_json_and_markdown(
    tmp_path: Path,
) -> None:
    package = _write_package(tmp_path, "ShadowPriest")
    out_json = tmp_path / "diagnostics" / "source_closure_optimizer.json"
    out_md = tmp_path / "diagnostics" / "source_closure_optimizer.md"

    exit_code = main(
        [
            "source-closure-optimizer",
            "--package",
            str(package),
            "--out",
            str(out_json),
            "--markdown-out",
            str(out_md),
        ]
    )

    assert exit_code == 0
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["authority"] == "diagnostic_only"
    assert payload["source_status_apply_blocking"] is False
    assert payload["reports"][0]["decision"] == "strong"
    assert "ShadowPriest" in out_md.read_text(encoding="utf-8")


def test_source_closure_optimizer_cli_includes_research_snapshot_relation(
    tmp_path: Path,
) -> None:
    package = _write_package(tmp_path, "ShadowPriest")
    research = tmp_path / "research"
    research.mkdir()
    (research / "ShadowPriest.json").write_text(
        json.dumps(
            {
                "deck_name": "ShadowPriest",
                "deck_code": "AAEBAa0GExample",
                "archetype": "Wild Shadow Priest",
                "current_deck_sources": [],
                "guide_sources": [],
                "source_strength": "unfetched_acquisition_seed",
                "lowerable_claim_kinds": [],
                "non_promoting_support": [],
                "first_missing_source_action": (
                    "fetch_and_normalize_candidate_full_text_claims"
                ),
                "notes": "Seed-only snapshot.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    out_json = tmp_path / "diagnostics" / "source_closure_optimizer.json"
    out_md = tmp_path / "diagnostics" / "source_closure_optimizer.md"

    exit_code = main(
        [
            "source-closure-optimizer",
            "--package",
            str(package),
            "--research-results-dir",
            str(research),
            "--out",
            str(out_json),
            "--markdown-out",
            str(out_md),
        ]
    )

    assert exit_code == 0
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    report = payload["reports"][0]
    assert report["decision"] == "strong"
    assert report["source_status_apply_blocking"] is False
    assert report["research_snapshot_relation"] == "stale_or_seed_only"
    assert report["research_recommended_refresh_action"] == (
        "refresh_research_snapshot_from_canonical_package"
    )
    assert "Research relation" in out_md.read_text(encoding="utf-8")


def test_source_closure_optimizer_cli_accepts_single_research_result_file(
    tmp_path: Path,
) -> None:
    package = _write_package(tmp_path, "ShadowPriest")
    research = tmp_path / "ShadowPriest.json"
    research.write_text(
        json.dumps(
            {
                "deck_name": "ShadowPriest",
                "deck_code": "AAEBAa0GExample",
                "archetype": "Wild Shadow Priest",
                "current_deck_sources": [],
                "guide_sources": [],
                "source_strength": "unfetched_acquisition_seed",
                "lowerable_claim_kinds": [],
                "non_promoting_support": [],
                "first_missing_source_action": (
                    "fetch_and_normalize_candidate_full_text_claims"
                ),
                "notes": "Seed-only snapshot.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    out_json = tmp_path / "diagnostics" / "source_closure_optimizer.json"

    exit_code = main(
        [
            "source-closure-optimizer",
            "--package",
            str(package),
            "--research-results-dir",
            str(research),
            "--out",
            str(out_json),
        ]
    )

    assert exit_code == 0
    report = json.loads(out_json.read_text(encoding="utf-8"))["reports"][0]
    assert report["research_result_found"] is True
    assert report["research_snapshot_relation"] == "stale_or_seed_only"


def test_source_closure_optimizer_rejects_operator_summary_overwrite(
    tmp_path: Path,
) -> None:
    package = _write_package(tmp_path, "ShadowPriest")
    unsafe = tmp_path / "operator_summary.json"

    try:
        main(
            [
                "source-closure-optimizer",
                "--package",
                str(package),
                "--out",
                str(unsafe),
            ]
        )
    except ValueError as exc:
        assert "operator_summary.json" in str(exc)
    else:
        raise AssertionError("expected diagnostic overwrite guard")


def test_source_closure_optimizer_rejects_package_operator_summary_overwrite(
    tmp_path: Path,
) -> None:
    package = _write_package(tmp_path, "ShadowPriest")
    unsafe = package / "reports" / "operator_summary.json"

    with pytest.raises(ValueError, match="operator_summary.json"):
        main(
            [
                "source-closure-optimizer",
                "--package",
                str(package),
                "--out",
                str(unsafe),
            ]
        )


@pytest.mark.parametrize(
    "unsafe_parts",
    [
        ("CustomConfig", "source_closure_optimizer.json"),
        ("Mulligan.json",),
        ("GlobalValues.json",),
        ("Combo.json",),
        ("Presume.json",),
        ("Concede.json",),
        ("deck_config.ini",),
        ("12345.json",),
    ],
)
def test_source_closure_optimizer_rejects_runtime_output_paths(
    tmp_path: Path,
    unsafe_parts: tuple[str, ...],
) -> None:
    package = _write_package(tmp_path, "ShadowPriest")
    unsafe = tmp_path.joinpath(*unsafe_parts)

    with pytest.raises(ValueError, match="runtime|diagnostic"):
        main(
            [
                "source-closure-optimizer",
                "--package",
                str(package),
                "--out",
                str(unsafe),
            ]
        )


@pytest.mark.parametrize(
    "unsafe_parts",
    [
        ("operator_summary.json",),
        ("CustomConfig", "source_closure_optimizer.md"),
        ("Mulligan.json",),
    ],
)
def test_source_closure_optimizer_rejects_unsafe_markdown_output_paths(
    tmp_path: Path,
    unsafe_parts: tuple[str, ...],
) -> None:
    package = _write_package(tmp_path, "ShadowPriest")
    out_json = tmp_path / "diagnostics" / "source_closure_optimizer.json"
    unsafe = tmp_path.joinpath(*unsafe_parts)

    with pytest.raises(ValueError, match="runtime|operator_summary"):
        main(
            [
                "source-closure-optimizer",
                "--package",
                str(package),
                "--out",
                str(out_json),
                "--markdown-out",
                str(unsafe),
            ]
        )
