from __future__ import annotations

import json
from pathlib import Path

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


def test_source_closure_optimizer_rejects_operator_summary_overwrite(
    tmp_path: Path,
) -> None:
    package = _write_package(tmp_path, "ShadowPriest")
    unsafe = package / "reports" / "operator_summary.json"

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
