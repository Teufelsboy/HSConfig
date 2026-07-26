from __future__ import annotations

import inspect
import json
from pathlib import Path

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.cli import main
from hsconfig.contract_spine_sentinel import build_contract_spine_sentinel_report
from hsconfig.io import write_json
from hsconfig.output_ownership_manifest import build_output_ownership_manifest
from hsconfig.package_derivation_receipt import (
    DERIVATION_RECEIPT_PATH,
    refresh_package_derivation_authority,
)
import hsconfig.package_builder as package_builder
from hsconfig.surface_intent import build_surface_intent


LEGACY_SURFACES = {"Presume.json", "Concede.json", "CardBehavior.json"}


ACTIVE_DOC_PATHS = [
    Path("docs/operator/README.md"),
    Path("docs/operator/guide-research-policy.md"),
    Path("docs/operator/universal-wild-no-block-contract.md"),
    Path(".agents/skills/hsconfig/SKILL.md"),
    Path(".agents/skills/hsconfig/references/workflow.md"),
    Path(".agents/skills/hsconfig/references/visionai-surfaces.md"),
]


def test_active_docs_describe_legacy_surfaces_as_non_normal_only():
    allowed_diagnostic_boundary = (
        "`semantic_handoff_status` is diagnostic and never creates a second apply gate."
    )
    for path in ACTIVE_DOC_PATHS:
        text = path.read_text(encoding="utf-8")
        assert "operator_summary.json" in text
        assert "legacy/diagnostic" in text or "outside the normal HSConfig output path" in text
        assert "emit Presume.json" not in text
        assert "emit Concede.json" not in text
        assert "second apply gate" not in text.replace(
            allowed_diagnostic_boundary, ""
        ).lower()


def test_contract_spine_sentinel_covers_subtractive_contract_polish():
    report = build_contract_spine_sentinel_report()
    checks = report["checks"]

    assert "legacy_surface_normal_routing" in checks
    assert "source_informed_apply_flag_policy" in checks
    assert "report_ownership_gate_files" in checks
    assert "report_ownership_unclassified_files" in checks
    assert checks["legacy_surface_normal_routing"] == []
    assert checks["source_informed_apply_flag_policy"]["behavior"] == "legacy_no_op"
    assert checks["report_ownership_gate_files"] == ["reports/operator_summary.json"]


def test_surface_intent_ignores_legacy_policy_surfaces_in_normal_path():
    contract = {
        "cards": {},
        "mulligan_anchors": [],
        "combos": [],
        "legacy_policy_surfaces_enabled": True,
        "policies": {
            "presume": [{"source_claim_ids": ["claim-presume"]}],
            "concede": [{"source_claim_ids": ["claim-concede"]}],
        },
    }

    intent = build_surface_intent(contract)

    assert set(intent["optional_surfaces"]).isdisjoint(LEGACY_SURFACES)
    assert all(row["surface"] not in LEGACY_SURFACES for row in intent["rows"])
    assert set(intent["required_surfaces"]) == {"GlobalValues.json", "Mulligan.json"}


def _write_minimal_package(
    package: Path,
    *,
    technical_status: str = "VALID_PACKAGE",
) -> None:
    deck_dir = package / "CustomConfig" / "deck"
    reports = package / "reports"
    deck_dir.mkdir(parents=True)
    reports.mkdir(parents=True)
    globalvalues = {"GameCardId": "GlobalValues", "ConfigComment": "fixture"}
    write_json(deck_dir / "GlobalValues.json", globalvalues)
    write_json(
        deck_dir / "Mulligan.json",
        {
            "GameCardId": "Mulligan",
            "ConfigComment": "fixture",
            "Mulligan": {"values": []},
        },
    )
    write_json(reports / "input_manifest.json", {"deck_name": "deck"})
    write_json(reports / "globalvalues_baseline.json", globalvalues)
    write_json(
        reports / "globalvalues_profile.json",
        {
            "key_count": len(globalvalues),
            "keys": {key: {"status": "unchanged"} for key in globalvalues},
            "generated_overlay_keys": [],
            "summary": {"all_expected_overlay_keys_accounted_for": True},
            "expected_overlay_keys": [],
            "missing_overlay_keys": [],
        },
    )
    deck_fingerprint = "sha256:" + ("0" * 64)
    write_json(
        reports / "deck_identity.json",
        {"deck_name": "deck", "deck_fingerprint": deck_fingerprint},
    )
    write_json(
        reports / "deck_fingerprint.json",
        {"deck_fingerprint": deck_fingerprint},
    )
    write_json(
        reports / "guide_claim_bundle.json",
        {"canonical_source_receipts": []},
    )
    generated_files = [
        "CustomConfig/deck/GlobalValues.json",
        "CustomConfig/deck/Mulligan.json",
    ]
    write_json(
        reports / "output_ownership_manifest.json",
        build_output_ownership_manifest(
            [
                *generated_files,
                DERIVATION_RECEIPT_PATH,
                "reports/operator_summary.json",
                "reports/output_ownership_manifest.json",
            ]
        ),
    )
    package_derivation = refresh_package_derivation_authority(package)
    write_json(
        reports / "operator_summary.json",
        {
            "technical_status": technical_status,
            "semantic_status": "VALID_BUT_NOT_GUIDE_STRONG",
            "next_action": "READY_TO_APPLY_WITH_WARNINGS",
            "apply_policy": "ALLOWED_WITH_WARNINGS",
            "generated_files": generated_files,
            "package_derivation": package_derivation,
        },
    )


def test_allow_source_informed_does_not_change_apply_gate(tmp_path):
    package = tmp_path / "package"
    _write_minimal_package(package)

    normal = evaluate_apply_gate(package)
    legacy_flag = evaluate_apply_gate(package, allow_source_informed=True)

    assert legacy_flag == normal
    assert normal["status"] == "allowed"


def test_output_ownership_manifest_classifies_every_generated_file():
    from hsconfig.output_ownership_manifest import build_output_ownership_manifest

    generated_files = [
        "CustomConfig/deck/GlobalValues.json",
        "CustomConfig/deck/Mulligan.json",
        "CustomConfig/deck/SW_448.json",
        "CustomConfig/deck/Combo.json",
        "reports/operator_summary.json",
        "reports/source_contract_audit.json",
        "reports/source_to_runtime_explainability.json",
        "reports/source_evidence_closure.json",
        "reports/mechanic_drift_report.json",
        "reports/strong_promotion_report.json",
        "reports/output_ownership_manifest.json",
    ]

    manifest = build_output_ownership_manifest(generated_files)

    assert manifest["summary"]["generated_file_count"] == len(generated_files)
    assert manifest["summary"]["unclassified_file_count"] == 0
    gate_rows = [row for row in manifest["files"] if row["classification"] == "gate"]
    assert [row["file"] for row in gate_rows] == ["reports/operator_summary.json"]
    runtime_rows = {
        row["file"]: row for row in manifest["files"] if row["file"].startswith("CustomConfig/")
    }
    assert runtime_rows["CustomConfig/deck/GlobalValues.json"]["runtime_surface"] == "GlobalValues.json"
    assert runtime_rows["CustomConfig/deck/Mulligan.json"]["runtime_surface"] == "Mulligan.json"
    assert runtime_rows["CustomConfig/deck/SW_448.json"]["runtime_surface"] == "CARDID.json"
    assert runtime_rows["CustomConfig/deck/Combo.json"]["runtime_surface"] == "Combo.json"


def test_output_ownership_manifest_marks_unknown_report_unclassified():
    from hsconfig.output_ownership_manifest import build_output_ownership_manifest

    manifest = build_output_ownership_manifest(
        [
            "reports/operator_summary.json",
            "reports/new_unregistered_report.json",
            "reports/research/new_unregistered_report.json",
        ]
    )
    by_file = {row["file"]: row for row in manifest["files"]}

    assert by_file["reports/new_unregistered_report.json"]["classification"] == (
        "unclassified"
    )
    assert by_file["reports/research/new_unregistered_report.json"]["classification"] == (
        "unclassified"
    )
    assert manifest["summary"]["unclassified_file_count"] == 2


def test_output_ownership_manifest_marks_legacy_surfaces_as_forbidden_drift():
    from hsconfig.output_ownership_manifest import build_output_ownership_manifest

    manifest = build_output_ownership_manifest(
        [
            "CustomConfig/deck/Presume.json",
            "CustomConfig/deck/Concede.json",
        ]
    )
    by_file = {row["file"]: row for row in manifest["files"]}

    for path in (
        "CustomConfig/deck/Presume.json",
        "CustomConfig/deck/Concede.json",
    ):
        assert by_file[path]["classification"] == "forbidden_legacy_surface"
        assert by_file[path]["runtime_surface"] == "legacy_non_normal_surface"
    assert manifest["summary"]["forbidden_legacy_surface_count"] == 2
    assert not any(
        row["classification"] == "runtime_surface" for row in manifest["files"]
    )


def test_package_builder_calls_build_operator_summary_once_in_prepare_flow():
    source = inspect.getsource(package_builder.build_package_payload)

    assert source.count("build_operator_summary(") == 1


def test_prepared_package_keeps_operator_manifest_and_emitted_files_in_sync(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr("hsconfig.package_builder.fetch_latest_cards", lambda timeout=10.0: [])
    package = tmp_path / "package"

    code = main(
        [
            "prepare",
            "--deck-name",
            "ShadowPriest",
            "--deck-code",
            "AAEBAa0GApG8Arv3Aw6hBJEP6bADurYD184Do/cDrfcDhoMF3aQFyKEGxKgG/KgG17oG1cEGAAA=",
            "--runtime-root",
            str(tmp_path / "runtime"),
            "--out",
            str(package),
            "--source-documents-json",
            "tests/fixtures/source_documents_shadowpriest_strong.json",
            "--json",
        ]
    )

    reports = package / "reports"
    operator_summary = json.loads(
        (reports / "operator_summary.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (reports / "output_ownership_manifest.json").read_text(encoding="utf-8")
    )
    emitted_files = {
        str(path.relative_to(package)).replace("\\", "/")
        for path in package.rglob("*")
        if path.is_file()
    }
    predicted_files = {
        str(path).replace("\\", "/") for path in operator_summary["generated_files"]
    }
    manifest_files = {row["file"] for row in manifest["files"]}

    assert code == 0
    assert predicted_files == emitted_files
    assert manifest_files == emitted_files
    assert {
        "reports/operator_summary.json",
        "reports/strong_promotion_report.json",
        "reports/output_ownership_manifest.json",
    }.issubset(predicted_files)
    assert manifest["summary"]["generated_file_count"] == len(emitted_files)
    assert manifest["summary"]["unclassified_file_count"] == 0
    assert operator_summary["output_ownership_summary"] == {
        "non_blocking": True,
        "generated_file_count": len(emitted_files),
        "unclassified_file_count": 0,
        "gate_count": 1,
    }
