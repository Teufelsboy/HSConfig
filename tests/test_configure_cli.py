from __future__ import annotations

import json
from pathlib import Path

from hsconfig.cli import main


SHADOWPRIEST_CODE = (
    "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/"
    "KgG17oG1cEGAAA="
)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_configure_builds_valid_load_safe_package_without_source_evidence(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_cards",
        lambda timeout=10.0: [],
    )

    out = tmp_path / "configure"
    runtime_root = tmp_path / "runtime"

    assert main(
        [
            "configure",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(runtime_root),
            "--out",
            str(out),
            "--json",
        ]
    ) == 0

    package = out / "04_package"
    operator = _read_json(package / "reports" / "operator_summary.json")
    summary = _read_json(out / "configure_summary.json")

    assert summary["status"] == "OK"
    assert summary["package_path"] == str(package)
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert operator["runtime_load_safe"] is True
    assert operator["runtime_apply_mode"] == "load_safe_apply"
    assert (package / "CustomConfig").exists()
    assert list(package.glob("CustomConfig/*/GlobalValues.json"))
    assert list(package.glob("CustomConfig/*/Mulligan.json"))
