import copy
import json
from pathlib import Path

from hsconfig.apply_gate import evaluate_apply_gate
from hsconfig.cli import main
from hsconfig.io import write_json
from hsconfig.operator_summary import build_operator_summary


REPO_ROOT = Path(__file__).resolve().parents[1]

ACTIVE_APPLY_PATHS = [
    "src/hsconfig/apply_gate.py",
    "src/hsconfig/runtime_apply.py",
    "src/hsconfig/commands/apply.py",
]

DIAGNOSTIC_ONLY_TOKENS = [
    "source_contract_audit",
    "source_to_runtime_explainability",
    "source_evidence_closure",
    "contract_spine_rows",
    "claim_lifecycle_rows",
    "source_contract_conformance",
]

FORBIDDEN_DIAGNOSTIC_IMPORTS = [
    "from hsconfig.contract_doctor",
    "import hsconfig.contract_doctor",
    "from hsconfig.source_contract_audit",
    "import hsconfig.source_contract_audit",
    "from hsconfig.source_to_runtime_explainability",
    "import hsconfig.source_to_runtime_explainability",
    "from hsconfig.source_evidence_closure",
    "import hsconfig.source_evidence_closure",
    "from hsconfig.source_contract_conformance",
    "import hsconfig.source_contract_conformance",
]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_active_apply_paths_do_not_consume_source_contract_diagnostics():
    for relative_path in ACTIVE_APPLY_PATHS:
        content = _read(relative_path)
        for token in DIAGNOSTIC_ONLY_TOKENS:
            assert token not in content, (relative_path, token)


def test_apply_gate_uses_operator_summary_as_single_authority():
    content = _read("src/hsconfig/apply_gate.py")

    assert 'package / "reports" / "operator_summary.json"' in content
    assert "technical_status" in content
    assert '"VALID_PACKAGE"' in content
    assert "source_contract_audit" not in content
    assert "source_to_runtime_explainability" not in content


def test_active_apply_paths_do_not_import_diagnostic_authorities():
    for relative_path in ACTIVE_APPLY_PATHS:
        content = _read(relative_path)
        for token in FORBIDDEN_DIAGNOSTIC_IMPORTS:
            assert token not in content, (relative_path, token)


def test_report_ownership_has_no_second_apply_gate():
    from hsconfig.report_ownership import build_report_ownership

    gate_rows = [row for row in build_report_ownership() if row.get("classification") == "gate"]

    assert [row["file"] for row in gate_rows] == ["reports/operator_summary.json"]


def _write_minimal_runtime_package(package: Path) -> None:
    write_json(
        package / "CustomConfig" / "deck" / "GlobalValues.json",
        {"GameCardId": "GlobalValues", "ConfigComment": "fixture"},
    )
    write_json(
        package / "CustomConfig" / "deck" / "Mulligan.json",
        {
            "GameCardId": "Mulligan",
            "ConfigComment": "fixture",
            "Mulligan": {"values": []},
        },
    )
    write_json(
        package / "reports" / "input_manifest.json",
        {"deck_name": "deck", "deck_code": "fixture", "runtime_root": "unused"},
    )


def test_configuration_assurance_does_not_change_apply_gate_result(tmp_path: Path):
    package = tmp_path / "package"
    _write_minimal_runtime_package(package)
    summary = build_operator_summary(
        deck_name="deck",
        deck_code="fixture",
        technical_validation={"status": "passed", "errors": []},
        generated_files=[
            "CustomConfig/deck/GlobalValues.json",
            "CustomConfig/deck/Mulligan.json",
        ],
    )
    assurance = summary["configuration_assurance"]
    authority_before = {
        key: summary[key]
        for key in (
            "technical_status",
            "runtime_apply_mode",
            "runtime_apply_allowed",
        )
    }
    write_json(package / "reports" / "operator_summary.json", summary)
    gate_before = evaluate_apply_gate(package)

    changed_assurance_summary = copy.deepcopy(summary)
    changed_assurance_summary["configuration_assurance"] = {
        **assurance,
        "load_safety": "not_validated",
        "runtime_gate_impact": "diagnostic_mutation",
    }
    write_json(
        package / "reports" / "operator_summary.json",
        changed_assurance_summary,
    )
    gate_after = evaluate_apply_gate(package)

    assert authority_before == {
        "technical_status": "VALID_PACKAGE",
        "runtime_apply_mode": "load_safe_apply",
        "runtime_apply_allowed": True,
    }
    assert gate_before == gate_after
    assert gate_after["allowed"] is True


def test_prepared_package_projects_configuration_assurance_to_operator_outputs(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(
        "hsconfig.package_builder.fetch_latest_cards",
        lambda timeout=10.0: [],
    )
    out = tmp_path / "ShadowPriest"

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
            str(out),
            "--source-documents-json",
            "tests/fixtures/source_documents_shadowpriest_strong.json",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    summary = json.loads(
        (out / "reports" / "operator_summary.json").read_text(encoding="utf-8")
    )
    markdown = (out / "reports" / "card_semantic_audit.md").read_text(
        encoding="utf-8"
    )
    assurance = summary["configuration_assurance"]

    assert code == 0
    assert payload["operator_summary"]["configuration_assurance"] == assurance
    assert summary["operator_guidance"]["configuration_assurance"] == assurance
    assert summary["operator_guidance"]["first_report_to_open"] == (
        "reports/operator_summary.json"
    )
    assert summary["runtime_apply_mode"] == "load_safe_apply"
    assert summary["runtime_apply_allowed"] is True
    assert f"- Load safety: `{assurance['load_safety']}`" in markdown
    assert f"- Source authority: `{assurance['source_authority']}`" in markdown
    assert f"- Semantic closure: `{assurance['semantic_closure']}`" in markdown
    assert "- Runtime gate impact: `none`" in markdown
