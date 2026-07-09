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


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_documented_operator_chain_reaches_guarded_apply(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    monkeypatch.setattr(
        "hsconfig.commands.source_workflow.fetch_latest_cards",
        lambda timeout=10.0: [],
    )

    runtime_root = tmp_path / "runtime"
    manifest_out = tmp_path / "01_manifest"
    draft_out = tmp_path / "02_draft"
    research_out = tmp_path / "03_research"
    package_out = tmp_path / "04_package"
    evidence_json = tmp_path / "source_evidence.json"

    _write_json(
        evidence_json,
        {
            "evidence_rows": [
                {
                    "source_url": "https://example.invalid/shadowpriest-guide",
                    "source_title": "ShadowPriest Guide",
                    "source_family": "guide",
                    "retrieved_at": "2026-07-08T00:00:00Z",
                    "deck_name": "ShadowPriest",
                    "archetype": "aggro_burn_hero_power_transform",
                    "scope": "deck",
                    "claim_kind": "gameplan_posture",
                    "stance": "aggressive_burn",
                    "evidence_text_short": "ShadowPriest pressures face damage and burn.",
                    "source_confidence": "high",
                }
            ]
        },
    )

    assert main(
        [
            "source-manifest",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--out",
            str(manifest_out),
            "--json",
        ]
    ) == 0
    assert (manifest_out / "source_research_manifest.json").exists()

    assert main(
        [
            "draft-source-documents",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--source-evidence-json",
            str(evidence_json),
            "--out",
            str(draft_out),
            "--json",
        ]
    ) == 0
    source_documents = draft_out / "source_documents.json"
    assert source_documents.exists()

    assert main(
        [
            "research-deck",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--source-documents-json",
            str(source_documents),
            "--out",
            str(research_out),
            "--json",
        ]
    ) == 0
    guide_sources = research_out / "guide_sources.json"
    assert guide_sources.exists()

    assert main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            SHADOWPRIEST_CODE,
            "--runtime-root",
            str(runtime_root),
            "--out",
            str(package_out),
            "--guide-sources-json",
            str(guide_sources),
            "--json",
        ]
    ) == 0

    operator = _read_json(package_out / "reports" / "operator_summary.json")
    assert operator["technical_status"] == "VALID_PACKAGE"
    assert "runtime_apply_mode" in operator
    assert "generated_files" in operator

    assert main(["validate", "--package", str(package_out), "--json"]) == 0

    fake_code = main(
        [
            "apply",
            "--package",
            str(package_out),
            "--runtime-root",
            str(runtime_root),
            "--fake",
            "--json",
        ]
    )
    can_apply = (
        operator["runtime_apply_allowed"]
        and operator["runtime_apply_mode"] == "load_safe_apply"
    ) or operator["apply_policy"] in {"ALLOWED", "ALLOWED_WITH_WARNINGS"}

    if can_apply:
        assert fake_code == 0
        assert not list(runtime_root.rglob("*.json"))
        assert main(
            [
                "apply",
                "--package",
                str(package_out),
                "--runtime-root",
                str(runtime_root),
                "--json",
            ]
        ) == 0
        assert list(runtime_root.rglob("*.json"))
    else:
        assert fake_code == 1
        assert not list(runtime_root.rglob("*.json"))
